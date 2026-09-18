"""
05_baixar_senado.py

Baixa da API de Dados Abertos do Senado Federal os senadores em exercicio
pelo Piaui.

Gera:
  data/processed/parlamentares_senado_pi.csv

AVISO: assim como o script da Camara, este NAO foi testado ao vivo (rede
bloqueada no ambiente onde foi escrito). A API do Senado responde XML por
padrao; pedimos JSON via header Accept, mas se isso nao funcionar, o
script cai para tentar interpretar XML. Se der erro, me manda a resposta
que aparecer no terminal.

Uso:
    python scripts/05_baixar_senado.py
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402


def listar_senadores_pi() -> list[dict]:
    url = f"{config.SENADO_API_BASE}/senador/lista/atual"
    print(f"Buscando senadores em exercicio por {config.UF}...")
    resp = requests.get(
        url,
        params={"uf": config.UF},
        headers={"Accept": "application/json", "User-Agent": config.USER_AGENT},
        timeout=60,
    )
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "json" in content_type:
        return _parlamentares_do_json(resp.json())

    print(
        "AVISO: a API do Senado respondeu em formato diferente de JSON "
        f"(Content-Type: {content_type}). Tentando interpretar como XML..."
    )
    return _parlamentares_do_xml(resp.text)


def _parlamentares_do_json(dados: dict) -> list[dict]:
    # Estrutura tipica: ListaParlamentarEmExercicio -> Parlamentares -> Parlamentar
    try:
        parlamentares = (
            dados.get("ListaParlamentarEmExercicio", {})
            .get("Parlamentares", {})
            .get("Parlamentar", [])
        )
    except AttributeError:
        parlamentares = []
    if isinstance(parlamentares, dict):
        parlamentares = [parlamentares]

    resultado = []
    for p in parlamentares:
        ident = p.get("IdentificacaoParlamentar", {})
        resultado.append({
            "id": ident.get("CodigoParlamentar", ""),
            "origem": "senado",
            "nome_civil": ident.get("NomeCompletoParlamentar", ident.get("NomeParlamentar", "")),
            "nome_eleitoral": ident.get("NomeParlamentar", ""),
            "cargo_atual": "SENADOR",
            "uf": ident.get("UfParlamentar", config.UF),
            "partido": ident.get("SiglaPartidoParlamentar", ""),
            "foto_url": ident.get("UrlFotoParlamentar", ""),
            "cpf": "",  # a API de lista nao traz CPF; ficaria por vinculo via nome
        })
    return resultado


def _parlamentares_do_xml(xml_text: str) -> list[dict]:
    resultado = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"ERRO: nao consegui interpretar a resposta do Senado como XML: {exc}")
        return resultado

    for parlamentar in root.iter("Parlamentar"):
        ident = parlamentar.find("IdentificacaoParlamentar")
        if ident is None:
            continue

        def texto(tag: str) -> str:
            el = ident.find(tag)
            return el.text if el is not None and el.text else ""

        resultado.append({
            "id": texto("CodigoParlamentar"),
            "origem": "senado",
            "nome_civil": texto("NomeCompletoParlamentar") or texto("NomeParlamentar"),
            "nome_eleitoral": texto("NomeParlamentar"),
            "cargo_atual": "SENADOR",
            "uf": texto("UfParlamentar") or config.UF,
            "partido": texto("SiglaPartidoParlamentar"),
            "foto_url": texto("UrlFotoParlamentar"),
            "cpf": "",
        })
    return resultado


def main() -> None:
    senadores = listar_senadores_pi()
    df = pd.DataFrame(senadores)
    destino = config.PROCESSED_DIR / "parlamentares_senado_pi.csv"
    df.to_csv(destino, index=False)
    print(f"\nPronto! {len(df)} senador(es) do PI salvos em {destino}")
    if df.empty:
        print(
            "AVISO: nenhum senador encontrado. Confira manualmente em "
            f"{config.SENADO_API_BASE}/senador/lista/atual?uf={config.UF}"
        )


if __name__ == "__main__":
    main()
