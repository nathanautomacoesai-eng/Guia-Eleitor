"""
debug_emendas.py

Script de diagnostico temporario para descobrir por que
scripts/06_baixar_transparencia.py esta retornando 0 emendas para todos
os parlamentares.

A documentacao oficial (swagger) confirma que 'nomeAutor' e o parametro
certo, entao o problema provavelmente e o FORMATO do nome esperado (ex.:
maiusculas, com/sem acento, nome completo x nome de urna, etc.).

Estrategia:
  1. Chama /emendas SOMENTE com ano+pagina (sem nomeAutor) para 2023, 2024
     e 2025, so pra confirmar que a base tem dados nesses anos.
  2. Se achar resultados, imprime os campos de autor do primeiro registro
     (pra sabermos o formato exato esperado).
  3. Tenta varias variacoes do nome de um parlamentar conhecido
     (Ciro Nogueira) para ver qual formato retorna resultado.

Uso:
    python scripts/debug_emendas.py
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402


def _headers() -> dict:
    return {"chave-api-dados": config.PORTAL_TRANSPARENCIA_API_KEY, "User-Agent": config.USER_AGENT}


def _chamar(params: dict) -> tuple[int, object]:
    url = f"{config.PORTAL_TRANSPARENCIA_BASE}/emendas"
    resp = requests.get(url, params=params, headers=_headers(), timeout=60)
    try:
        corpo = resp.json()
    except ValueError:
        corpo = resp.text[:500]
    return resp.status_code, corpo


def sem_acento(txt: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", txt) if not unicodedata.combining(c)
    )


def main() -> None:
    print("=" * 70)
    print("PASSO 1: /emendas so com ano+pagina (sem nomeAutor)")
    print("=" * 70)
    algum_ano_com_dados = None
    for ano in (2023, 2024, 2025):
        status, corpo = _chamar({"ano": ano, "pagina": 1})
        qtd = len(corpo) if isinstance(corpo, list) else "N/A"
        print(f"ano={ano} -> status={status} qtd_resultados={qtd}")
        if isinstance(corpo, list) and corpo:
            algum_ano_com_dados = (ano, corpo)

    if algum_ano_com_dados is None:
        print("\nNenhum ano trouxe resultado algum SEM filtro de autor.")
        print("Isso sugere que o problema pode ser: chave de API, ou o")
        print("endpoint /emendas exige outro parametro obrigatorio junto.")
        return

    ano_exemplo, registros = algum_ano_com_dados
    print(f"\nEncontrei {len(registros)} registro(s) em {ano_exemplo} sem filtro de autor.")
    print("Campos do primeiro registro (para ver o nome exato dos campos de autor):")
    primeiro = registros[0]
    if isinstance(primeiro, dict):
        for chave, valor in primeiro.items():
            valor_str = str(valor)
            if len(valor_str) > 80:
                valor_str = valor_str[:80] + "..."
            print(f"  {chave}: {valor_str}")

    print("\n" + "=" * 70)
    print("PASSO 2: variacoes de nomeAutor para um parlamentar conhecido")
    print("=" * 70)
    nome_base = "Ciro Nogueira"
    variacoes = {
        "como esta (Ciro Nogueira)": nome_base,
        "maiusculas (CIRO NOGUEIRA)": nome_base.upper(),
        "minusculas (ciro nogueira)": nome_base.lower(),
        "sem acento": sem_acento(nome_base),
        "sobrenome (Nogueira)": "Nogueira",
        "sobrenome maiusculo (NOGUEIRA)": "NOGUEIRA",
        "nome completo (Ciro Eduardo Dias Nogueira)": "Ciro Eduardo Dias Nogueira",
        "com titulo (Senador Ciro Nogueira)": "Senador Ciro Nogueira",
    }
    for descricao, valor in variacoes.items():
        status, corpo = _chamar({"ano": ano_exemplo, "nomeAutor": valor, "pagina": 1})
        qtd = len(corpo) if isinstance(corpo, list) else f"resposta nao-lista: {corpo}"
        print(f"{descricao!r:55s} -> status={status} qtd={qtd}")

    print("\nDica: compare a qtd de cada variacao. A que retornar > 0 e o")
    print("formato certo pra usar em scripts/06_baixar_transparencia.py.")


if __name__ == "__main__":
    main()
