"""
11_baixar_alepi.py

Baixa da Assembleia Legislativa do Piaui (ALEPI):
  - os deputados estaduais em exercicio (mandato atual);
  - as emendas parlamentares estaduais deles (Portal da Transparencia do
    Piaui, mesma API ja usada em 10_baixar_transparencia_pi.py).

Gera:
  data/processed/parlamentares_alepi_pi.csv
  data/processed/emendas_estaduais_pi.csv

CONTEXTO: ate esta versao, o projeto so tinha coleta de mandato atual
pra Camara dos Deputados, Senado, Camara Municipal de Teresina e o
Governador - nunca pra Deputado Estadual. Na pratica isso fazia todo
candidato a reeleicao pra Deputado Estadual aparecer como se fosse
candidato novo, sem "ja tem mandato" nem nenhuma informacao de gestao
(caso real encontrado: Ana Paula, deputada estadual em exercicio pela
ALEPI). Este script fecha essa lacuna.

FONTES (confirmadas contra a API real em set/2026, inspecionando o
trafego de rede dos sites publicos - nao adivinhadas):
  - Lista de parlamentares: API do sistema SAPL usado pela ALEPI,
    https://sapl.al.pi.leg.br/api/parlamentares/parlamentar/ (paginado,
    ~309 registros historicos; filtramos pelo campo "ativo").
    ATENCAO: o campo "next" de paginacao vem como "http://" (nao
    "https://"); reescrevemos pra https antes de seguir, senao pode
    dar erro de conteudo misto dependendo do cliente HTTP.
  - Emendas parlamentares estaduais: mesma API do Portal da
    Transparencia do Piaui usada pro Governador
    (config.TRANSPARENCIA_PI_API_BASE), endpoint
    /v1/emendas-estaduais/{ano}/?page=N&page_size=100 - o ano faz parte
    do CAMINHO da URL, nao e' um parametro de query.

VINCULO emenda -> deputado: a API de emendas so devolve o NOME do
parlamentar em texto livre (campo "parlamentar_nome", ex.:
"WILSON BRANDÃO"), sem nenhum ID. Comparamos esse nome com o
"nome_parlamentar" (nome de tratamento/urna) de cada deputado da ALEPI
- e' o campo mais parecido em formato com o que a API de emendas usa
(diferente do "nome_completo", que costuma ter nomes do meio a mais e
gerava similaridade mais baixa nos testes). Usamos um limiar de 90%
(rapidfuzz), levemente abaixo do limiar de 92% usado em
07_montar_banco.py pra candidato-parlamentar, porque aqui os dois lados
ja sao ambos dados de deputados em exercicio da mesma casa (risco de
homonimo bem menor).

Uso:
    python scripts/11_baixar_alepi.py
"""
from __future__ import annotations

import re
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

try:
    from rapidfuzz import fuzz

    def similaridade(a: str, b: str) -> float:
        return fuzz.token_sort_ratio(a, b)
except ImportError:
    from difflib import SequenceMatcher

    def similaridade(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100

LIMIAR_SIMILARIDADE_EMENDA = 90.0
HEADERS = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
TIMEOUT = 30
PAUSA = 0.1


def normalizar_nome(nome: str) -> str:
    nome = nome or ""
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome = re.sub(r"[^A-Za-z ]", " ", nome).upper()
    return re.sub(r"\s+", " ", nome).strip()


def listar_deputados_alepi_ativos() -> list[dict]:
    """Pagina a API do SAPL (formato {pagination: {links: {next, previous}, ...}, results: [...]})
    e devolve so os parlamentares com ativo == True."""
    url = f"{config.SAPL_ALEPI_API_BASE}/parlamentares/parlamentar/"
    ativos = []
    paginas = 0

    while url and paginas < 60:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException as exc:
            print(f"  (aviso) erro de conexao em {url}: {exc}")
            break

        if resp.status_code != 200:
            print(f"  (aviso) {url} devolveu HTTP {resp.status_code}")
            break

        dados = resp.json()
        paginas += 1
        for p in dados.get("results", []):
            if p.get("ativo") is True:
                ativos.append(p)

        proxima = dados.get("pagination", {}).get("links", {}).get("next")
        url = proxima.replace("http://", "https://") if proxima else None
        if url:
            time.sleep(PAUSA)

    print(f"ALEPI: {paginas} pagina(s) lidas, {len(ativos)} deputado(s) em exercicio encontrado(s).")
    return ativos


def montar_parlamentares_alepi(ativos: list[dict]) -> pd.DataFrame:
    linhas = []
    for p in ativos:
        linhas.append({
            "id": f"ALEPI-{p.get('id')}",
            "origem": "alepi",
            "cpf": "",  # nao exposto pela API do SAPL
            "nome_civil": p.get("nome_completo", "").strip(),
            "nome_eleitoral": p.get("nome_parlamentar", "").strip(),
            "cargo_atual": "DEPUTADO ESTADUAL",
            "uf": config.UF,
            "partido": "",  # preenchido depois, se aparecer nas emendas (baixar_emendas_estaduais)
            "email": p.get("email", "") or "",
            "foto_url": (p.get("fotografia") or "").replace("http://", "https://"),
        })
    return pd.DataFrame(linhas)


def _paginar_emendas(ano: int) -> list[dict]:
    url = f"{config.TRANSPARENCIA_PI_API_BASE}/v1/emendas-estaduais/{ano}/"
    resultados = []
    pagina = 1
    while True:
        try:
            resp = requests.get(
                url, params={"page": pagina, "page_size": 100}, headers=HEADERS, timeout=TIMEOUT
            )
        except requests.RequestException as exc:
            print(f"  (aviso) erro de conexao em {url} pagina {pagina}: {exc}")
            break

        if resp.status_code == 404 and pagina == 1:
            break
        if resp.status_code != 200:
            print(f"  (aviso) {url} pagina {pagina} devolveu HTTP {resp.status_code}")
            break

        dados = resp.json()
        itens = dados.get("results", [])
        resultados.extend(itens)

        if not dados.get("next"):
            break
        pagina += 1
        time.sleep(PAUSA)

    return resultados


def _numero(valor) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def baixar_emendas_estaduais(parlamentares: pd.DataFrame) -> pd.DataFrame:
    """Baixa as emendas parlamentares estaduais de todos os anos
    configurados e vincula cada uma a um deputado da ALEPI por
    similaridade de nome (ver explicacao no topo do arquivo)."""
    if parlamentares.empty:
        return pd.DataFrame()

    candidatos_nome = [
        (row["id"], normalizar_nome(row["nome_eleitoral"]))
        for _, row in parlamentares.iterrows()
    ]
    partido_por_id: dict[str, str] = {}

    linhas = []
    nao_vinculadas = 0
    total_bruto = 0

    for ano in config.TRANSPARENCIA_PI_ANOS:
        print(f"Emendas estaduais {ano}...")
        registros = _paginar_emendas(ano)
        print(f"  {len(registros)} emenda(s) bruta(s).")
        total_bruto += len(registros)

        for r in registros:
            nome_emenda_norm = normalizar_nome(r.get("parlamentar_nome", ""))

            melhor_id = ""
            melhor_score = 0.0
            for id_parlamentar, nome_norm in candidatos_nome:
                score = similaridade(nome_emenda_norm, nome_norm)
                if score > melhor_score and score >= LIMIAR_SIMILARIDADE_EMENDA:
                    melhor_id = id_parlamentar
                    melhor_score = score

            if not melhor_id:
                nao_vinculadas += 1
                continue

            if melhor_id not in partido_por_id and r.get("parlamentar_partido"):
                partido_por_id[melhor_id] = r["parlamentar_partido"]

            linhas.append({
                "parlamentar_id": melhor_id,
                "ano": ano,
                "emenda_numero": r.get("emenda_numero") or "",
                "status": r.get("status") or "",
                "modalidade": r.get("modalidade_emenda_nome") or r.get("modalidade") or "",
                "beneficiario_nome": (r.get("beneficiario_nome") or "").strip(),
                "localidade_beneficiada": r.get("localidade_beneficiada") or "",
                "objetivo_titulo": r.get("objetivo_titulo") or "",
                "valor": _numero(r.get("emenda_valor")),
            })

    print(
        f"Emendas estaduais vinculadas a um deputado da ALEPI: "
        f"{len(linhas)}/{total_bruto} (nao vinculadas: {nao_vinculadas})."
    )

    # preenche o partido dos parlamentares que a gente descobriu via emenda
    for idx, row in parlamentares.iterrows():
        if not row["partido"] and row["id"] in partido_por_id:
            parlamentares.at[idx, "partido"] = partido_por_id[row["id"]]

    return pd.DataFrame(linhas)


def main() -> None:
    ativos = listar_deputados_alepi_ativos()
    parlamentares = montar_parlamentares_alepi(ativos)

    emendas = baixar_emendas_estaduais(parlamentares)

    parlamentares.to_csv(config.PROCESSED_DIR / "parlamentares_alepi_pi.csv", index=False)
    emendas.to_csv(config.PROCESSED_DIR / "emendas_estaduais_pi.csv", index=False)

    print("\nPronto!")
    print(f"Deputados estaduais em exercicio: {len(parlamentares)}")
    print(f"Emendas estaduais vinculadas: {len(emendas)}")


if __name__ == "__main__":
    main()
