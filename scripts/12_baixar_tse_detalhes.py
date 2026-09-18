"""
12_baixar_tse_detalhes.py

Baixa, para CADA candidato do recorte (348 no PI), dados complementares
direto da API oficial por tras da pagina publica do TSE "Divulgacao de
Candidaturas e Contas Eleitorais" (https://divulgacandcontas.tse.jus.br):

  - dados pessoais: grau de instrucao, ocupacao, estado civil, cor/raca,
    data de nascimento, foto oficial, bens declarados (total), sites e
    redes sociais que o PROPRIO candidato informou ao TSE;
  - resumo da prestacao de contas de campanha: total arrecadado, total
    de despesas contratadas/pagas, data da ultima atualizacao.

MOTIVACAO: o TSE so exige "proposta de governo" (PDF) de candidatos a
Governador (ver 01_baixar_tse.py / 02_extrair_propostas.py). Pros outros
337 candidatos do recorte (Senador, Deputado Federal, Deputado
Estadual), a pagina do candidato no site ficava sem quase nenhuma
informacao alem do que ja vinha do cadastro basico. Essa API preenche
esse vazio com dados que o proprio TSE ja disponibiliza publicamente
pra cada candidato, sem precisar de scraping de terceiros (Google,
Instagram etc.) nem risco de linkar a pessoa errada.

Gera:
  data/processed/detalhes_tse_pi.csv

FONTE (confirmada contra a API real em set/2026, inspecionando o
trafego de rede da propria pagina do TSE - nao adivinhada):
  - Dados pessoais:
    {DIVULGACANDCONTAS_API_BASE}/candidatura/buscar/{ano}/{uf}/{idEleicao}/candidato/{sqCandidato}
  - Prestacao de contas:
    {DIVULGACANDCONTAS_API_BASE}/prestador/consulta/{idEleicao}/{ano}/{uf}/{codigoCargo}/{nrPartido}/{numero}/{sqCandidato}
    (nrPartido e numero saem da PROPRIA resposta de "candidatura/buscar",
    no campo "partido.numero" e "numero" - nao precisamos adivinhar nem
    derivar do numero de urna.)

Um candidato pode nao ter prestacao de contas entregue ainda (comum no
inicio da campanha) - nesse caso a chamada de prestador falha ou volta
vazia, e so' deixamos os campos de prestacao de contas em branco pra
aquele candidato (nao e' erro).

Uso:
    python scripts/12_baixar_tse_detalhes.py
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
PAUSA = 0.3


def _get_json(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _url_divulga(uf: str, sq_candidato: str, ano_eleicao: str) -> str:
    """Monta o link publico (pagina, nao API) da candidatura no TSE, pra
    o usuario final poder abrir e ver tudo em detalhe se quiser."""
    return (
        f"https://divulgacandcontas.tse.jus.br/divulga/#/candidato/"
        f"NORDESTE/{uf}/{config.TSE_ID_ELEICAO_PI}/{sq_candidato}/{ano_eleicao}/{uf}"
    )


def buscar_detalhe_candidato(sq_candidato: str, ano_eleicao: str, cargo: str) -> dict:
    base = config.DIVULGACANDCONTAS_API_BASE
    uf = config.UF

    candidatura = _get_json(
        f"{base}/candidatura/buscar/{ano_eleicao}/{uf}/{config.TSE_ID_ELEICAO_PI}/candidato/{sq_candidato}"
    )
    linha = {
        "sq_candidato": sq_candidato,
        "grau_instrucao": "",
        "ocupacao": "",
        "estado_civil": "",
        "cor_raca": "",
        "data_nascimento": "",
        "foto_url": "",
        "sites_tse": "",
        "bens_total": "",
        "prestacao_total_recebido": "",
        "prestacao_total_despesas_contratadas": "",
        "prestacao_total_despesas_pagas": "",
        "prestacao_data_atualizacao": "",
        "tse_divulga_url": _url_divulga(uf, sq_candidato, ano_eleicao),
    }

    if not candidatura:
        return linha

    linha["grau_instrucao"] = candidatura.get("grauInstrucao") or ""
    linha["ocupacao"] = candidatura.get("ocupacao") or ""
    linha["estado_civil"] = candidatura.get("descricaoEstadoCivil") or ""
    linha["cor_raca"] = candidatura.get("descricaoCorRaca") or ""
    linha["data_nascimento"] = candidatura.get("dataDeNascimento") or ""
    if candidatura.get("fotoUrlPublicavel"):
        linha["foto_url"] = candidatura.get("fotoUrl") or ""
    sites = candidatura.get("sites") or []
    linha["sites_tse"] = " | ".join(s for s in sites if s)
    linha["bens_total"] = candidatura.get("totalDeBens") or ""

    codigo_cargo = config.TSE_CODIGO_CARGO.get(cargo)
    partido = candidatura.get("partido") or {}
    nr_partido = partido.get("numero")
    numero = candidatura.get("numero")

    if codigo_cargo and nr_partido and numero:
        prestador = _get_json(
            f"{base}/prestador/consulta/{config.TSE_ID_ELEICAO_PI}/{ano_eleicao}/{uf}/"
            f"{codigo_cargo}/{nr_partido}/{numero}/{sq_candidato}"
        )
        if prestador:
            consolidados = prestador.get("dadosConsolidados") or {}
            despesas = prestador.get("despesas") or {}
            linha["prestacao_total_recebido"] = consolidados.get("totalRecebido") or ""
            linha["prestacao_total_despesas_contratadas"] = despesas.get("totalDespesasContratadas") or ""
            linha["prestacao_total_despesas_pagas"] = despesas.get("totalDespesasPagas") or ""
            linha["prestacao_data_atualizacao"] = prestador.get("dataUltimaAtualizacaoContas") or ""

    return linha


def main() -> None:
    caminho_candidatos = config.PROCESSED_DIR / "candidatos_pi.csv"
    if not caminho_candidatos.exists():
        print("ERRO: data/processed/candidatos_pi.csv nao existe.")
        print("Rode antes: python scripts/01_baixar_tse.py")
        raise SystemExit(1)

    candidatos = pd.read_csv(caminho_candidatos, dtype=str).fillna("")
    total = len(candidatos)
    print(f"Buscando detalhes complementares do TSE para {total} candidato(s)...")

    linhas = []
    for i, row in enumerate(candidatos.to_dict("records"), start=1):
        sq = row.get("sq_candidato", "")
        cargo = row.get("cargo", "")
        ano = row.get("ano_eleicao") or str(config.ANO_ELEICAO)
        if not sq:
            continue

        linhas.append(buscar_detalhe_candidato(sq, ano, cargo))

        if i % 25 == 0 or i == total:
            print(f"  {i}/{total} processado(s)...")
        time.sleep(PAUSA)

    df = pd.DataFrame(linhas)
    df.to_csv(config.PROCESSED_DIR / "detalhes_tse_pi.csv", index=False)

    com_prestacao = (df["prestacao_total_recebido"] != "").sum()
    com_sites = (df["sites_tse"] != "").sum()
    print("\nPronto!")
    print(f"Detalhes baixados: {len(df)}/{total}")
    print(f"Com prestacao de contas ja entregue: {com_prestacao}")
    print(f"Com site/rede social informado ao TSE: {com_sites}")


if __name__ == "__main__":
    main()
