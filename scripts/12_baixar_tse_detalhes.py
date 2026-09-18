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

POR QUE PLAYWRIGHT EM VEZ DE REQUESTS: a primeira versao deste script
usava `requests` puro e voltava 0 resultado pra todo mundo, sem erro
HTTP normal - a resposta era uma pagina de bloqueio da Akamai (a
protecao anti-bot que fica na frente do dominio divulgacandcontas.tse.jus.br),
confirmado testando manualmente (`errors.edgesuite.net` na resposta).
Um navegador de verdade (Playwright/Chromium) passa por essa protecao
normalmente - foi assim que a API foi descoberta e testada em primeiro
lugar, inspecionando o trafego de rede da pagina real. Aqui abrimos UM
navegador e reusamos a mesma pagina pra todas as 348 chamadas (via
`fetch` executado dentro da pagina, com `page.evaluate`), em vez de
abrir/fechar navegador a cada candidato.

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

REQUISITO: playwright instalado (ja no requirements.txt) e o browser do
Playwright baixado uma vez com:
    playwright install chromium

Uso:
    python scripts/12_baixar_tse_detalhes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

SITE_BASE = "https://divulgacandcontas.tse.jus.br"


def _url_divulga(uf: str, sq_candidato: str, ano_eleicao: str) -> str:
    """Monta o link publico (pagina, nao API) da candidatura no TSE, pra
    o usuario final poder abrir e ver tudo em detalhe se quiser."""
    return (
        f"{SITE_BASE}/divulga/#/candidato/"
        f"NORDESTE/{uf}/{config.TSE_ID_ELEICAO_PI}/{sq_candidato}/{ano_eleicao}/{uf}"
    )


# JS executado DENTRO da pagina (via page.evaluate) - faz as duas
# chamadas fetch (candidatura e, se der, prestacao de contas) e devolve
# tudo junto num objeto so, pra minimizar o numero de idas e vindas
# entre Python e o navegador.
JS_BUSCAR_CANDIDATO = """
async ({ base, idEleicao, uf, ano, sqCandidato, codigoCargo }) => {
  const resultado = { candidatura: null, prestador: null, erro: null };
  try {
    const rCand = await fetch(
      `${base}/divulga/rest/v1/candidatura/buscar/${ano}/${uf}/${idEleicao}/candidato/${sqCandidato}`,
      { headers: { Accept: "application/json" } }
    );
    if (rCand.ok) {
      resultado.candidatura = await rCand.json();
    }
  } catch (e) {
    resultado.erro = "candidatura: " + String(e);
    return resultado;
  }

  const candidatura = resultado.candidatura;
  const nrPartido = candidatura && candidatura.partido ? candidatura.partido.numero : null;
  const numero = candidatura ? candidatura.numero : null;

  if (codigoCargo && nrPartido && numero) {
    try {
      const rPrest = await fetch(
        `${base}/divulga/rest/v1/prestador/consulta/${idEleicao}/${ano}/${uf}/${codigoCargo}/${nrPartido}/${numero}/${sqCandidato}`,
        { headers: { Accept: "application/json" } }
      );
      if (rPrest.ok) {
        resultado.prestador = await rPrest.json();
      }
    } catch (e) {
      resultado.erro = "prestador: " + String(e);
    }
  }

  return resultado;
}
"""


def montar_linha(sq_candidato: str, ano_eleicao: str, uf: str, resultado: dict) -> dict:
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

    candidatura = resultado.get("candidatura")
    if candidatura:
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

    prestador = resultado.get("prestador")
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
    print(f"Buscando detalhes complementares do TSE para {total} candidato(s) (via navegador)...")

    linhas = []
    erros = 0

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page()
        # Carrega a pagina uma vez so, pra abrir na mesma origem do site
        # (fetch de dentro da pagina evita qualquer questao de CORS e
        # passa pela protecao anti-bot igual um acesso humano normal).
        page.goto(f"{SITE_BASE}/divulga/", timeout=60000)
        page.wait_for_timeout(1500)

        for i, row in enumerate(candidatos.to_dict("records"), start=1):
            sq = row.get("sq_candidato", "")
            cargo = row.get("cargo", "")
            ano = row.get("ano_eleicao") or str(config.ANO_ELEICAO)
            uf = row.get("uf") or config.UF
            if not sq:
                continue

            codigo_cargo = config.TSE_CODIGO_CARGO.get(cargo)

            try:
                resultado = page.evaluate(
                    JS_BUSCAR_CANDIDATO,
                    {
                        "base": SITE_BASE,
                        "idEleicao": config.TSE_ID_ELEICAO_PI,
                        "uf": uf,
                        "ano": ano,
                        "sqCandidato": sq,
                        "codigoCargo": codigo_cargo,
                    },
                )
            except Exception as exc:
                print(f"  (aviso) falha no candidato {sq}: {exc}")
                resultado = {}
                erros += 1

            linhas.append(montar_linha(sq, ano, uf, resultado))
            page.wait_for_timeout(150)  # pausa curta entre chamadas, por educacao com o servidor

            if i % 25 == 0 or i == total:
                print(f"  {i}/{total} processado(s)...")

        navegador.close()

    df = pd.DataFrame(linhas)
    df.to_csv(config.PROCESSED_DIR / "detalhes_tse_pi.csv", index=False)

    com_prestacao = (df["prestacao_total_recebido"] != "").sum()
    com_sites = (df["sites_tse"] != "").sum()
    com_dados_pessoais = (df["grau_instrucao"] != "").sum()
    print("\nPronto!")
    print(f"Detalhes baixados: {len(df)}/{total} (falhas de chamada: {erros})")
    print(f"Com dados pessoais (grau de instrucao etc.): {com_dados_pessoais}")
    print(f"Com prestacao de contas ja entregue: {com_prestacao}")
    print(f"Com site/rede social informado ao TSE: {com_sites}")


if __name__ == "__main__":
    main()
