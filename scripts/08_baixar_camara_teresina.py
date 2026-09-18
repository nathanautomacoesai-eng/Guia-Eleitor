"""
08_baixar_camara_teresina.py

Busca despesas de atividade parlamentar e emendas parlamentares dos
candidatos do PI que confirmamos MANUALMENTE serem vereadores atuais da
Camara Municipal de Teresina.

Por que uma lista fixa (nao automatica): o portal da Camara de Teresina
nao tem CPF nem nenhum identificador em comum com o TSE para cruzar
candidatos automaticamente, e o nome usado la (nome civil completo) e
diferente do nome de urna do TSE. O vinculo abaixo foi conferido a mao
comparando:
  - a lista de vereadores do site oficial
    (https://www.teresina.pi.leg.br/vereadores);
  - o campo nome_civil de cada candidato em candidatos_pi.csv;
  - a lista de nomes do dropdown "Emendas Parlamentares" do portal de
    transparencia da Camara (que usa nome civil completo).
Se quiser adicionar mais nomes no futuro, confirme manualmente (o nome
civil tem que bater EXATO, sem contar acento, com o que a Camara usa) e
adicione uma tupla em VEREADORES_CONFIRMADOS.

Por que Playwright em vez de requests: o portal usa JSF (JavaServer
Faces) com postback/ViewState via AJAX - nao existe API JSON nem export
CSV publico (so PDF/Excel gerados sob demanda pela tela). Simular isso
com requests puro exigiria replicar o protocolo interno do JSF a cada
chamada (bem mais fragil). Deixamos um navegador de verdade
(Playwright) fazer a navegacao, do jeito que um humano faria.

Gera:
  data/processed/parlamentares_camara_teresina_pi.csv
  data/processed/despesas_camara_teresina_pi.csv
  data/processed/emendas_camara_teresina_pi.csv

REQUISITO: playwright instalado (ja no requirements.txt) e o browser do
Playwright baixado uma vez com:
    playwright install chromium

Uso:
    python scripts/08_baixar_camara_teresina.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

BASE_URL = "https://transparencia.teresina.pi.leg.br/project6-war/ext"

# (nome_urna no nosso banco, nome_civil no TSE, sq_candidato) - confirmado
# manualmente em set/2026.
VEREADORES_CONFIRMADOS = [
    ("ANA FIDELIS", "ANA FLAVIA TEIXEIRA FIDELIS", "180002544099"),
    ("DRAGA ALANA", "EDUARDO DA SILVA OLIVEIRA", "180002534810"),
    ("ELZUILA CALISTO", "ELZUILA ALVES CALISTO", "180002533563"),
    ("ENZO SAMUEL", "ENZO SAMUEL ALENCAR SILVA", "180002533557"),
    ("GERALDIN", "GERALDO JARQUES PEREIRA FILHO", "180002539131"),
    ("PEDRO ALCÂNTARA", "PEDRO ALCANTARA CARVALHO DO NASCIMENTO", "180002539039"),
    ("PETRUS EVELYN (O PIAUIENSE)", "PETRUS EVELYN MARTINS", "180002539014"),
    ("SAMANTHA CAVALCA", "SAMANTHA CAVALCA SOBREIRA DUTRA", "180002539134"),
    ("VENÂNCIO", "JOSE VENANCIO CARDOSO NETO", "180002536459"),
]


def _para_float_brasileiro(txt: str) -> float | None:
    txt = (txt or "").strip()
    if not txt or txt == "-":
        return None
    negativo = txt.startswith("-")
    if negativo:
        txt = txt[1:].strip()
    txt = txt.replace(".", "").replace(",", ".")
    try:
        numero = float(txt)
    except ValueError:
        return None
    return -numero if negativo else numero


def _extrair_linhas_tabela(page) -> list[list[str]]:
    return page.eval_on_selector_all(
        "#dataTable table tbody tr",
        "trs => trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))",
    )


def _selecionar_30_por_pagina(page) -> None:
    try:
        page.select_option("select[name='dataTable_rppDD']", "30")
        page.wait_for_timeout(800)
    except Exception:
        pass


def _tem_proxima_pagina(page) -> bool:
    """True se o link 'proxima pagina' do paginador (PrimeFaces) existe e
    nao esta desabilitado (ultima pagina)."""
    return page.query_selector(".ui-paginator-next:not(.ui-state-disabled)") is not None


def buscar_despesas(page, nome_civil: str) -> list[dict]:
    page.goto(f"{BASE_URL}/consultarDespesaAtividade.jsf")
    page.fill("#nome", nome_civil)
    page.click("#btConsultar")
    page.wait_for_timeout(1200)
    _selecionar_30_por_pagina(page)

    linhas_total: list[list[str]] = []
    while True:
        linhas_total.extend(_extrair_linhas_tabela(page))
        if not _tem_proxima_pagina(page):
            break
        page.click(".ui-paginator-next")
        page.wait_for_timeout(800)

    resultado = []
    for linha in linhas_total:
        # colunas reais (confirmadas via inspecao): [indice, NOME,
        # NOTA_EMPENHO, NOTA_LIQUIDACAO, DATA_PAGAMENTO, VALOR, EXERCICIO, ACOES]
        if len(linha) < 7 or "Nenhum registro" in " ".join(linha):
            continue
        _indice, _nome, _empenho, _liquidacao, data_pagamento, valor, exercicio = linha[:7]
        mes = None
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", data_pagamento or "")
        if m:
            mes = int(m.group(2))
        resultado.append({
            "ano": exercicio.strip(),
            "mes": mes,
            "tipo_despesa": "Cota para exercício parlamentar (Câmara Municipal de Teresina)",
            "valor_liquido": _para_float_brasileiro(valor),
            "fornecedor": "",
        })
    return resultado


def buscar_emendas(page, nome_civil: str) -> list[dict]:
    page.goto(f"{BASE_URL}/consultarEmendasParlamentares.jsf")
    opcoes = page.eval_on_selector_all(
        "#vereador_input option", "opts => opts.map(o => o.textContent.trim())"
    )
    if nome_civil not in opcoes:
        print(f"    (sem opcao '{nome_civil}' no dropdown de emendas - provavelmente ainda nao apresentou emenda)")
        return []

    page.select_option("#vereador_input", label=nome_civil)
    page.click("#btConsultar")
    page.wait_for_timeout(1200)
    _selecionar_30_por_pagina(page)

    linhas_total: list[list[str]] = []
    while True:
        linhas_total.extend(_extrair_linhas_tabela(page))
        if not _tem_proxima_pagina(page):
            break
        page.click(".ui-paginator-next")
        page.wait_for_timeout(800)

    resultado = []
    for linha in linhas_total:
        # colunas reais: [indice, EXERCICIO, NUMERO, PARLAMENTAR/PARTIDO,
        # ORGAO, EXECUCAO, BENEFICIARIO, OBJETO, VALOR]
        if len(linha) < 9 or "Nenhum registro" in " ".join(linha):
            continue
        _indice, exercicio, numero, _parlamentar_partido, orgao, _execucao, beneficiario, objeto, valor = linha[:9]
        beneficiario = beneficiario.strip()
        resultado.append({
            "ano": exercicio.strip(),
            "numero_emenda": numero.strip(),
            "tipo": "Emenda Impositiva Municipal",
            "funcao": f"{objeto.strip()} (órgão: {orgao.strip()})",
            "valor_empenhado": _para_float_brasileiro(valor),
            "valor_pago": None,
            "municipio_beneficiario": beneficiario if beneficiario and beneficiario != "-" else "Teresina",
        })
    return resultado


def main() -> None:
    linhas_parlamentares = []
    linhas_despesas = []
    linhas_emendas = []

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page()

        for nome_urna, nome_civil, sq_candidato in VEREADORES_CONFIRMADOS:
            parlamentar_id = f"cmt-{sq_candidato}"
            print(f"\nBuscando vereador de Teresina: {nome_urna} ({nome_civil})")

            linhas_parlamentares.append({
                "id": parlamentar_id,
                "origem": "camara_municipal_teresina",
                "cpf": "",
                "nome_civil": nome_civil,
                "nome_eleitoral": nome_urna,
                "cargo_atual": "VEREADOR(A) - CÂMARA MUNICIPAL DE TERESINA",
                "uf": "PI",
                "partido": "",
                "email": "",
                "foto_url": "",
            })

            despesas = buscar_despesas(page, nome_civil)
            for d in despesas:
                d["parlamentar_id"] = parlamentar_id
            linhas_despesas.extend(despesas)
            print(f"  -> {len(despesas)} despesa(s) de atividade parlamentar")

            emendas = buscar_emendas(page, nome_civil)
            for e in emendas:
                e["parlamentar_id"] = parlamentar_id
                e["parlamentar_nome"] = nome_civil
            linhas_emendas.extend(emendas)
            print(f"  -> {len(emendas)} emenda(s) impositiva(s)")

        navegador.close()

    pd.DataFrame(linhas_parlamentares).to_csv(
        config.PROCESSED_DIR / "parlamentares_camara_teresina_pi.csv", index=False
    )
    pd.DataFrame(linhas_despesas).to_csv(
        config.PROCESSED_DIR / "despesas_camara_teresina_pi.csv", index=False
    )
    pd.DataFrame(linhas_emendas).to_csv(
        config.PROCESSED_DIR / "emendas_camara_teresina_pi.csv", index=False
    )
    print(
        f"\nPronto! {len(linhas_parlamentares)} parlamentar(es), "
        f"{len(linhas_despesas)} despesa(s), {len(linhas_emendas)} emenda(s) "
        "salvas em data/processed/*_camara_teresina_pi.csv"
    )


if __name__ == "__main__":
    main()
