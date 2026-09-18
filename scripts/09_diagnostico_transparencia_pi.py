"""
09_diagnostico_transparencia_pi.py

Script de DIAGNOSTICO (nao faz parte da pipeline ainda). A API de dados
abertos do Portal da Transparencia do Piaui (transparencia.pi.gov.br)
nao tem documentacao publica do formato de resposta, entao antes de
escrever o ingestor de verdade (parecido com o 06_baixar_transparencia.py
e o 08_baixar_camara_teresina.py) precisamos ver uma amostra real de
cada endpoint: quantos registros vem, quais campos existem, se pagina
ou devolve tudo de uma vez.

Endpoints conhecidos (confirmados via busca, ainda nao testados de
verdade):
    https://transparencia.pi.gov.br/ords/portal/api/despesa/:ano
    https://transparencia.pi.gov.br/ords/portal/api/receita/:ano
    https://transparencia.pi.gov.br/ords/portal/api/contrato/:ano
    https://transparencia.pi.gov.br/ords/portal/api/licitacao/:ano
    https://transparencia.pi.gov.br/ords/portal/api/convenio/:ano
    https://transparencia.pi.gov.br/ords/portal/api/parceria/:ano

Uso:
    python scripts/09_diagnostico_transparencia_pi.py

Depois de rodar, me manda a saida completa (ou um print da tela) que eu
escrevo o script de ingestao de verdade com base no formato real.
"""
from __future__ import annotations

import json

import requests

# NOTA (resolvido): as URLs originais deste diagnostico (baseadas em
# .../ords/portal/api/...) estavam erradas - foram um chute a partir do
# texto da pagina, e devolviam so' o HTML da SPA, nao JSON. A API real
# foi encontrada inspecionando o trafego de rede do site (fica num
# dominio separado, api.transparencia.pi.gov.br) e ja esta em uso em
# scripts/10_baixar_transparencia_pi.py. Este script fica so' de
# referencia/checagem rapida de conectividade.
BASE = "https://api.transparencia.pi.gov.br/api"
ANO_TESTE = 2025  # ano recente, dentro do mandato do governador atual

ENDPOINTS = ["v2/despesas", "v1/receitas", "v1/contratos", "v1/licitacoes"]

HEADERS = {
    "User-Agent": "GuiaEleitorPI/0.1 (uso publico e nao comercial; contato: projeto pessoal)",
    "Accept": "application/json",
}


def testar_endpoint(nome: str, ano: int) -> None:
    url = f"{BASE}/{nome}/{ano}/1/12/"
    print(f"\n{'=' * 70}\n{nome.upper()} -> {url}\n{'=' * 70}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except Exception as exc:
        print(f"ERRO de conexao: {exc}")
        return

    print(f"Status HTTP: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('content-type')}")
    print(f"Tamanho da resposta: {len(resp.content)} bytes")

    if resp.status_code != 200:
        print(f"Corpo da resposta (nao-200): {resp.text[:1000]}")
        return

    try:
        dados = resp.json()
    except ValueError:
        print("Resposta nao e' JSON valido. Primeiros 1000 caracteres:")
        print(resp.text[:1000])
        return

    if isinstance(dados, dict):
        print(f"Chaves do objeto raiz: {list(dados.keys())}")
        # ORDS costuma devolver {"items": [...], "hasMore": bool, "limit": N, "offset": N, "count": N}
        if "hasMore" in dados:
            print(f"hasMore: {dados.get('hasMore')} | limit: {dados.get('limit')} | offset: {dados.get('offset')} | count: {dados.get('count')}")
        itens = dados.get("items")
        if isinstance(itens, list):
            print(f"Total de itens nesta pagina: {len(itens)}")
            if itens:
                print("\nCampos do primeiro item:")
                print(list(itens[0].keys()))
                print("\nPrimeiro item completo:")
                print(json.dumps(itens[0], ensure_ascii=False, indent=2, default=str)[:2000])
        else:
            print("\nConteudo completo (objeto sem 'items'):")
            print(json.dumps(dados, ensure_ascii=False, indent=2, default=str)[:2000])
    elif isinstance(dados, list):
        print(f"Resposta e' uma lista direta. Total de itens: {len(dados)}")
        if dados:
            print("\nCampos do primeiro item:")
            print(list(dados[0].keys()))
            print("\nPrimeiro item completo:")
            print(json.dumps(dados[0], ensure_ascii=False, indent=2, default=str)[:2000])
    else:
        print(f"Formato inesperado ({type(dados)}): {str(dados)[:500]}")


def main() -> None:
    print(f"Testando endpoints do Portal da Transparencia do Piaui para o ano {ANO_TESTE}...\n")
    for nome in ENDPOINTS:
        testar_endpoint(nome, ANO_TESTE)
    print("\n\nFIM DO DIAGNOSTICO. Copie toda essa saida e me mande de volta.")


if __name__ == "__main__":
    main()
