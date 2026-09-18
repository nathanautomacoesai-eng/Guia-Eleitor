"""
06_baixar_transparencia.py

Busca emendas parlamentares (por autor) no Portal da Transparencia (CGU)
para cada parlamentar do PI (deputados federais + senadores) coletados
pelos scripts 04 e 05.

Gera:
  data/processed/emendas_pi.csv

REQUISITO: uma chave de API gratuita. Cadastre seu e-mail em
https://www.portaldatransparencia.gov.br/api-de-dados/cadastrar-email
e coloque a chave recebida no arquivo .env (copie de .env.example),
na variavel PORTAL_TRANSPARENCIA_API_KEY.

DESCOBERTA (validada contra a API real via scripts/debug_emendas.py e
depois contra os dados reais dos 13 parlamentares do PI):
  1. O parametro certo e 'nomeAutor', mas o valor precisa estar em
     MAIUSCULAS (a base guarda os nomes assim).
  2. O nome tem que ser o NOME ELEITORAL/USUAL (ex.: "Ciro Nogueira"),
     nao o nome civil completo do TSE/Camara (ex.: "Ciro Nogueira Lima
     Filho" ou "Atila de Melo Lira") - o nome civil completo nao bate
     com nada porque a base do Portal da Transparencia usa o nome
     "publico" mais curto de cada parlamentar.
  3. O casamento parece ser por substring, entao filtramos o resultado
     comparando o campo 'nomeAutor'/'autor' de cada emenda (normalizado)
     contra o nome pesquisado, pra nao aceitar emendas de outra pessoa
     que so compartilhe um pedaco do nome.

Por isso o script tenta, para cada parlamentar, o nome_eleitoral primeiro
(o que resolveu o problema nos testes reais) e cai para o nome_civil como
reserva, caso um dia falte nome_eleitoral para alguem.

Uso:
    python scripts/06_baixar_transparencia.py
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

DEBUG_DIR = config.RAW_DIR / "debug_transparencia"

# Titulos que as vezes aparecem no nome_eleitoral (ex.: "Dr. Francisco") mas
# provavelmente nao fazem parte do nome como a base de emendas guarda.
_PREFIXOS_TITULO = re.compile(r"^(dr|dra|pe|sr|sra|prof|profa)\.?\s+", re.IGNORECASE)


def _headers() -> dict:
    if not config.PORTAL_TRANSPARENCIA_API_KEY:
        print(
            "ERRO: PORTAL_TRANSPARENCIA_API_KEY nao configurada. Copie .env.example "
            "para .env e cole sua chave (cadastro gratuito em "
            "https://www.portaldatransparencia.gov.br/api-de-dados/cadastrar-email)."
        )
        raise SystemExit(1)
    return {
        "chave-api-dados": config.PORTAL_TRANSPARENCIA_API_KEY,
        "User-Agent": config.USER_AGENT,
    }


def carregar_parlamentares() -> pd.DataFrame:
    partes = []
    for nome_arquivo in ("parlamentares_camara_pi.csv", "parlamentares_senado_pi.csv"):
        caminho = config.PROCESSED_DIR / nome_arquivo
        if caminho.exists():
            partes.append(pd.read_csv(caminho, dtype=str).fillna(""))
        else:
            print(f"AVISO: {caminho} nao existe ainda - rode os scripts 04/05 antes.")
    if not partes:
        print("ERRO: nenhum arquivo de parlamentares encontrado. Nada a fazer.")
        raise SystemExit(1)
    return pd.concat(partes, ignore_index=True)


def _normalizar(txt: str) -> str:
    """Maiusculas, sem acento, sem espacos duplicados - para comparar nomes
    vindos de fontes diferentes (TSE/Camara/Senado x Portal da Transparencia)
    de forma tolerante a diferencas de acentuacao/capitalizacao."""
    txt = txt.upper().strip()
    txt = "".join(
        c for c in unicodedata.normalize("NFKD", txt) if not unicodedata.combining(c)
    )
    return " ".join(txt.split())


def _candidatos_de_nome(nome_eleitoral: str, nome_civil: str) -> list[str]:
    """Monta a lista de nomes a tentar, na ordem de maior chance de acerto:
    nome eleitoral (o que resolveu nos testes reais) primeiro, depois o
    mesmo sem titulo tipo 'Dr.', e por fim o nome civil completo como
    ultimo recurso."""
    candidatos = []
    if nome_eleitoral:
        candidatos.append(nome_eleitoral)
        sem_titulo = _PREFIXOS_TITULO.sub("", nome_eleitoral).strip()
        if sem_titulo and sem_titulo != nome_eleitoral:
            candidatos.append(sem_titulo)
    if nome_civil:
        candidatos.append(nome_civil)

    vistos = set()
    unicos = []
    for c in candidatos:
        chave = _normalizar(c)
        if c and chave not in vistos:
            vistos.add(chave)
            unicos.append(c)
    return unicos


def _registrar_debug(nome_autor: str, ano: int, conteudo: dict) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    arquivo_debug = DEBUG_DIR / f"erro_{nome_autor.replace(' ', '_')}_{ano}.json"
    try:
        arquivo_debug.write_text(json.dumps(conteudo, ensure_ascii=False))
    except Exception:
        pass


def _buscar_paginado(nome_query: str, ano: int) -> list[dict]:
    """Busca todas as paginas de /emendas para um dado valor de nomeAutor+ano."""
    url = f"{config.PORTAL_TRANSPARENCIA_BASE}/emendas"
    resultados: list[dict] = []
    pagina = 1
    while True:
        try:
            resp = requests.get(
                url,
                params={"ano": ano, "nomeAutor": nome_query, "pagina": pagina},
                headers=_headers(),
                timeout=60,
            )
            resp.raise_for_status()
            dados = resp.json()
        except (requests.HTTPError, ValueError) as exc:
            print(f"  [AVISO] falha ao buscar emendas de '{nome_query}' em {ano} (pagina {pagina}): {exc}")
            _registrar_debug(nome_query, ano, {"erro": str(exc)})
            break
        if not isinstance(dados, list) or not dados:
            break
        resultados.extend(dados)
        pagina += 1
        if pagina > 20:
            break
        time.sleep(0.3)
    return resultados


def buscar_emendas_por_autor(nomes_candidatos: list[str], ano: int) -> list[dict]:
    """Tenta, em ordem, cada nome candidato do parlamentar (nome eleitoral,
    variacoes sem titulo, nome civil), cada um em maiusculas e sem acento,
    ate achar emendas cujo autor bate (normalizado) com o nome pesquisado.
    Para no primeiro candidato que der resultado."""
    for nome in nomes_candidatos:
        nome_alvo_normalizado = _normalizar(nome)
        tentativas = []
        for t in (nome.upper(), _normalizar(nome)):
            if t not in tentativas:
                tentativas.append(t)

        for tentativa in tentativas:
            brutos = _buscar_paginado(tentativa, ano)
            if not brutos:
                continue
            filtrados = [
                registro
                for registro in brutos
                if _normalizar(str(registro.get("nomeAutor") or registro.get("autor") or ""))
                == nome_alvo_normalizado
            ]
            if filtrados:
                return filtrados
    return []


def main() -> None:
    parlamentares = carregar_parlamentares()
    linhas_emendas = []

    anos = [config.ANO_ELEICAO - 3, config.ANO_ELEICAO - 2, config.ANO_ELEICAO - 1]

    for _, parlamentar in parlamentares.iterrows():
        nome_eleitoral = parlamentar.get("nome_eleitoral", "") or ""
        nome_civil = parlamentar.get("nome_civil", "") or ""
        candidatos = _candidatos_de_nome(nome_eleitoral, nome_civil)
        if not candidatos:
            continue
        nome_exibicao = candidatos[0]
        print(f"\nBuscando emendas de: {nome_exibicao}")

        total_parlamentar = 0
        for ano in anos:
            emendas = buscar_emendas_por_autor(candidatos, ano)
            total_parlamentar += len(emendas)
            for emenda in emendas:
                linhas_emendas.append({
                    "parlamentar_id": parlamentar.get("id", ""),
                    "parlamentar_nome": nome_exibicao,
                    "ano": ano,
                    "numero_emenda": emenda.get("numeroEmenda", emenda.get("codigoEmenda", "")),
                    "tipo": emenda.get("tipoEmenda", ""),
                    "funcao": emenda.get("funcao", ""),
                    "valor_empenhado": emenda.get("valorEmpenhado", ""),
                    "valor_pago": emenda.get("valorPago", ""),
                    "municipio_beneficiario": emenda.get("municipio", emenda.get("localidadeDoGasto", "")),
                })
            time.sleep(0.5)  # respeita o limite de requisicoes/minuto da API
        print(f"  -> {total_parlamentar} emenda(s) encontrada(s) em {anos[0]}-{anos[-1]}")

    df = pd.DataFrame(linhas_emendas)
    destino = config.PROCESSED_DIR / "emendas_pi.csv"
    df.to_csv(destino, index=False)
    print(f"\nPronto! {len(df)} emenda(s) salvas em {destino}")
    if df.empty:
        print(
            "\nNenhuma emenda encontrada para nenhum parlamentar. Isso pode ser "
            "normal (parlamentares do PI podem realmente nao ter emendas "
            "registradas nesses anos), mas se voce esperava encontrar, confira "
            "os arquivos em data/raw/debug_transparencia/ (se existirem) e me avise."
        )


if __name__ == "__main__":
    main()
