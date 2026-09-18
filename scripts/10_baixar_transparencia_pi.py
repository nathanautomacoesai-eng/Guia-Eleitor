"""
10_baixar_transparencia_pi.py

Baixa dados de execucao orcamentaria do Poder Executivo estadual do
Piaui (Portal da Transparencia do Piaui) pra montar a "ficha de gestao"
do Governador titular, do mesmo jeito que 06_baixar_transparencia.py e
08_baixar_camara_teresina.py fazem pra deputados/senadores/vereadores.

A API real (achada inspecionando o trafego de rede do site, ver
scripts/09_diagnostico_transparencia_pi.py) fica em
api.transparencia.pi.gov.br, separada do dominio publico do portal
(que so' serve o front-end).

IMPORTANTE sobre volume: despesa e' um dataset enorme (mais de 160 mil
lancamentos SO' NO ANO de 2025, pro estado inteiro) - baixar linha a
linha e agregar aqui no script, como a primeira versao deste arquivo
fazia, levaria mais de uma hora so' nessa parte (a API limita a 100
linhas por pagina). A correcao: o proprio site usa, na aba "Informacoes
Agrupadas", um endpoint de AGREGACAO que soma os valores no servidor e
devolve so' o resultado ja somado (poucas dezenas de linhas por ano, uma
requisicao so). Usamos esse mesmo endpoint aqui pra despesa e receita:

  despesa (agregado)   -> /api/v2/despesas/agregacao/{ano}/{mes_de}/{mes_ate}/?groups=...&metrics=...
  receita (agregado)   -> /api/v1/receitas/agregacao/{ano}/{mes_de}/{mes_ate}/?groups=...&metrics=...

Licitacao, contrato e convenio/parceria nao tem endpoint de agregacao
(nao tem aba "Informacoes Agrupadas" no site pra eles), mas o volume
bruto e' bem menor (na faixa de 1 a 6 mil linhas/ano) - esses continuam
paginando o endpoint "detalhado" normal, so' que com page_size=100 (o
maximo aceito) pra minimizar o numero de requisicoes:

  licitacao  -> /api/v1/licitacoes/{ano}/{mes_de}/{mes_ate}/?page=N&page_size=100
  contrato   -> /api/v1/contratos/{ano}/{mes_de}/{mes_ate}/?page=N&page_size=100
  transferencia (convenio/parceria) -> /api/v1/transferencias-realizadas/{ano}/?page=N&page_size=100

Uso:
    python scripts/10_baixar_transparencia_pi.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

HEADERS = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
TIMEOUT = 30
PAUSA_ENTRE_PAGINAS = 0.1
PAGE_SIZE = 100

# Contratos sao guardados linha a linha, mas com um teto por ano pra nao
# inflar o banco com milhares de contratos pequenos - ficamos so com os
# maiores valores, que sao os mais relevantes pro eleitor.
TETO_CONTRATOS_POR_ANO = 40


def _numero(valor) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _agregacao(endpoint: str, ano: int, mes_de: int, mes_ate: int, groups: list[str], metrics: list[str]) -> list[dict]:
    """Chama o endpoint de agregacao (soma no servidor, uma requisicao so
    por ano) usado pela aba 'Informacoes Agrupadas' do site."""
    url = f"{config.TRANSPARENCIA_PI_API_BASE}/{endpoint}/agregacao/{ano}/{mes_de}/{mes_ate}/"
    params = {"groups": ",".join(groups), "metrics": ",".join(metrics)}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        print(f"  (aviso) erro de conexao em {url}: {exc}")
        return []

    if resp.status_code != 200:
        print(f"  (aviso) {url} devolveu HTTP {resp.status_code}")
        return []

    try:
        dados = resp.json()
    except ValueError:
        print(f"  (aviso) {url} nao devolveu JSON valido")
        return []

    return dados.get("results", [])


def _paginar(endpoint: str, ano: int, mes_de: int | None = None, mes_ate: int | None = None) -> list[dict]:
    """Percorre todas as paginas de um endpoint DETALHADO (nao agregado)
    da API do Piaui e devolve a lista completa de resultados, usando o
    maior page_size aceito (100) pra minimizar o numero de requisicoes."""
    if mes_de is not None:
        url_base = f"{config.TRANSPARENCIA_PI_API_BASE}/{endpoint}/{ano}/{mes_de}/{mes_ate}/"
    else:
        url_base = f"{config.TRANSPARENCIA_PI_API_BASE}/{endpoint}/{ano}/"

    resultados: list[dict] = []
    pagina = 1
    while True:
        try:
            resp = requests.get(
                url_base, params={"page": pagina, "page_size": PAGE_SIZE}, headers=HEADERS, timeout=TIMEOUT
            )
        except requests.RequestException as exc:
            print(f"  (aviso) erro de conexao em {url_base} pagina {pagina}: {exc}")
            break

        if resp.status_code == 404 and pagina == 1:
            break
        if resp.status_code != 200:
            print(f"  (aviso) {url_base} pagina {pagina} devolveu HTTP {resp.status_code}")
            break

        try:
            dados = resp.json()
        except ValueError:
            print(f"  (aviso) {url_base} pagina {pagina} nao devolveu JSON valido")
            break

        itens = dados.get("results", [])
        resultados.extend(itens)

        if not dados.get("next"):
            break
        pagina += 1
        time.sleep(PAUSA_ENTRE_PAGINAS)

    return resultados


def baixar_despesas_agregadas() -> pd.DataFrame:
    """Despesa empenhada/liquidada/paga por (ano, orgao, funcao), ja
    somada no servidor (ver endpoint de agregacao no topo do arquivo)."""
    linhas = []
    for ano in config.TRANSPARENCIA_PI_ANOS:
        print(f"Despesas {ano} (agregado no servidor)...")
        registros = _agregacao(
            "v2/despesas", ano, 1, 12,
            groups=["orgao_titulo", "funcao_titulo"],
            metrics=["orig_empenhado_saldo", "temp_liquidado_saldo", "temp_pago_saldo"],
        )
        print(f"  {len(registros)} combinacao(oes) de orgao/area.")
        for r in registros:
            linhas.append({
                "parlamentar_id": config.GOVERNADOR_ATUAL_ID,
                "ano": ano,
                "orgao_titulo": r.get("orgao_titulo") or "-",
                "funcao_titulo": r.get("funcao_titulo") or "-",
                "total_empenhado": _numero(r.get("orig_empenhado_saldo")),
                "total_liquidado": _numero(r.get("temp_liquidado_saldo")),
                "total_pago": _numero(r.get("temp_pago_saldo")),
                "qtd_lancamentos": None,  # o endpoint agregado nao devolve contagem de linhas
            })

    return pd.DataFrame(linhas)


def baixar_receitas_agregadas() -> pd.DataFrame:
    """Receita prevista/realizada por (ano, categoria), ja somada no
    servidor."""
    linhas = []
    for ano in config.TRANSPARENCIA_PI_ANOS:
        print(f"Receitas {ano} (agregado no servidor)...")
        registros = _agregacao(
            "v1/receitas", ano, 1, 12,
            groups=["categoria_receita_titulo"],
            metrics=["previsao_atualizada", "receita_realizada"],
        )
        print(f"  {len(registros)} categoria(s) de receita.")
        for r in registros:
            linhas.append({
                "parlamentar_id": config.GOVERNADOR_ATUAL_ID,
                "ano": ano,
                "categoria_titulo": r.get("categoria_receita_titulo") or "-",
                "total_previsto": _numero(r.get("previsao_atualizada")),
                "total_realizado": _numero(r.get("receita_realizada")),
            })

    return pd.DataFrame(linhas)


def baixar_licitacoes_agregadas() -> pd.DataFrame:
    """Conta e soma valor previsto de licitacoes por (ano, modalidade).
    Nao tem endpoint de agregacao pra licitacao, entao paginamos o
    detalhado (volume moderado, ~1 a 2 mil/ano) e agregamos aqui mesmo."""
    from collections import defaultdict

    linhas = []
    for ano in config.TRANSPARENCIA_PI_ANOS:
        print(f"Licitacoes {ano}...")
        registros = _paginar("v1/licitacoes", ano, 1, 12)
        print(f"  {len(registros)} licitacoes brutas.")

        agregado = defaultdict(lambda: {"qtd": 0, "valor": 0.0})
        for r in registros:
            modalidade = r.get("modalidade") or "-"
            agregado[modalidade]["qtd"] += 1
            agregado[modalidade]["valor"] += _numero(r.get("valor_total_previsto"))

        for modalidade, soma in agregado.items():
            linhas.append({
                "parlamentar_id": config.GOVERNADOR_ATUAL_ID,
                "ano": ano,
                "modalidade": modalidade,
                "qtd": soma["qtd"],
                "valor_total_previsto": soma["valor"],
            })

    return pd.DataFrame(linhas)


def baixar_contratos() -> pd.DataFrame:
    """Guarda os N contratos de maior valor por ano (detalhado). Volume
    bruto na faixa de alguns milhares/ano, tranquilo de paginar."""
    linhas = []
    for ano in config.TRANSPARENCIA_PI_ANOS:
        print(f"Contratos {ano}...")
        registros = _paginar("v1/contratos", ano, 1, 12)
        print(f"  {len(registros)} contratos brutos.")

        registros.sort(key=lambda r: _numero(r.get("valor_contratado")), reverse=True)
        for r in registros[:TETO_CONTRATOS_POR_ANO]:
            linhas.append({
                "parlamentar_id": config.GOVERNADOR_ATUAL_ID,
                "ano": ano,
                "num_contrato": r.get("num_contrato") or "",
                "orgao": r.get("orgao") or "",
                "nome_contratada": r.get("nome_contratada") or "",
                "valor_contratado": _numero(r.get("valor_contratado")),
                "objeto": r.get("objeto") or "",
                "status": r.get("status") or "",
            })

    return pd.DataFrame(linhas)


def baixar_convenios() -> pd.DataFrame:
    """Convenios/parcerias (transferencias realizadas pelo estado). Volume
    baixo (dezenas a poucas centenas por ano) pra guardar tudo."""
    linhas = []
    for ano in config.TRANSPARENCIA_PI_ANOS:
        print(f"Convenios/parcerias {ano}...")
        registros = _paginar("v1/transferencias-realizadas", ano)
        print(f"  {len(registros)} convenios/parcerias.")

        for r in registros:
            linhas.append({
                "parlamentar_id": config.GOVERNADOR_ATUAL_ID,
                "ano": ano,
                "numero_ano": r.get("numero_ano") or "",
                "nome_proponente": r.get("nome_proponente") or "",
                "nome_concedente": r.get("nome_concedente") or "",
                "valor_total": _numero(r.get("valor_total")),
                "objeto": r.get("objeto") or "",
                "situacao": r.get("situacao_termo_colaboracao") or "",
                "tipo_termo": r.get("tipo_termo") or "",
            })

    return pd.DataFrame(linhas)


def gravar_parlamentar_executivo() -> pd.DataFrame:
    """Uma unica linha representando o Governador titular atual, no mesmo
    formato da tabela parlamentares - assim o vinculo com o candidato a
    Governador acontece pelo mesmo mecanismo ja usado pra deputado/
    senador (comparacao de nome civil), sem precisar de logica separada."""
    return pd.DataFrame([{
        "id": config.GOVERNADOR_ATUAL_ID,
        "origem": "executivo_estadual",
        "cpf": "",
        "nome_civil": config.GOVERNADOR_ATUAL_NOME_CIVIL,
        "nome_eleitoral": config.GOVERNADOR_ATUAL_NOME_ELEITORAL,
        "cargo_atual": "GOVERNADOR",
        "uf": config.UF,
        "partido": config.GOVERNADOR_ATUAL_PARTIDO,
        "email": "",
        "foto_url": "",
    }])


def main() -> None:
    gravar_parlamentar_executivo().to_csv(
        config.PROCESSED_DIR / "parlamentares_executivo_pi.csv", index=False
    )
    print("Parlamentar (Executivo estadual) gravado.\n")

    baixar_despesas_agregadas().to_csv(
        config.PROCESSED_DIR / "gestao_despesas_pi.csv", index=False
    )
    baixar_receitas_agregadas().to_csv(
        config.PROCESSED_DIR / "gestao_receitas_pi.csv", index=False
    )
    baixar_licitacoes_agregadas().to_csv(
        config.PROCESSED_DIR / "gestao_licitacoes_pi.csv", index=False
    )
    baixar_contratos().to_csv(
        config.PROCESSED_DIR / "gestao_contratos_pi.csv", index=False
    )
    baixar_convenios().to_csv(
        config.PROCESSED_DIR / "gestao_convenios_pi.csv", index=False
    )

    print("\nPronto! CSVs de gestao do Executivo estadual (PI) gerados em data/processed/.")


if __name__ == "__main__":
    main()
