"""
diagnostico_ocupacao_vereador.py

Script AD-HOC (nao faz parte do pipeline principal) para responder uma
pergunta pontual: quantos dos nossos 348 candidatos do PI se autodeclaram,
no cadastro do TSE, como tendo ocupacao "vereador"?

O TSE tem uma coluna DS_OCUPACAO no cadastro de candidatos (ocupacao
declarada pelo proprio candidato, usando uma tabela de codigos padronizada
do TSE) - mas essa coluna NAO faz parte do nosso candidatos_pi.csv hoje
(scripts/01_baixar_tse.py so guarda um subconjunto de colunas). Em vez de
alterar o pipeline principal (o que arriscaria perder o proposta_pdf_url
ja preenchido pelo script 03), este script baixa o zip do TSE de novo,
so pra cruzar essa coluna extra com os candidatos que ja temos.

NAO diz o MUNICIPIO onde a pessoa e vereador(a) - o TSE nao guarda isso
na candidatura a Deputado Estadual/Federal (a unidade eleitoral dessas
candidaturas e o estado inteiro, nao um municipio). Isso e' so uma
contagem de quantos merece a pena investigar, e uma lista de nomes pra
voce reconhecer visualmente de qual cidade cada um e.

Uso:
    python scripts/diagnostico_ocupacao_vereador.py
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402


def main() -> None:
    candidatos_atuais = pd.read_csv(
        config.PROCESSED_DIR / "candidatos_pi.csv", dtype=str
    ).fillna("")
    sq_candidatos_validos = set(candidatos_atuais["sq_candidato"])
    print(f"Candidatos no nosso banco: {len(sq_candidatos_validos)}")

    print(f"\nBaixando de novo: {config.TSE_CANDIDATOS_ZIP_URL}")
    resp = requests.get(
        config.TSE_CANDIDATOS_ZIP_URL,
        headers={"User-Agent": config.USER_AGENT},
        timeout=180,
    )
    resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))

    candidatos_uf = [
        n for n in zf.namelist()
        if n.lower().endswith(".csv") and config.UF.lower() in n.lower()
    ]
    dfs = []
    for nome in candidatos_uf:
        with zf.open(nome) as f:
            dfs.append(pd.read_csv(f, sep=";", encoding="latin-1", dtype=str))
    df = pd.concat(dfs, ignore_index=True)

    if "DS_OCUPACAO" not in df.columns:
        print("\nERRO: coluna DS_OCUPACAO nao existe neste CSV do TSE.")
        print("Colunas disponiveis:", list(df.columns))
        return

    df = df[df["SQ_CANDIDATO"].isin(sq_candidatos_validos)]
    df["DS_OCUPACAO"] = df["DS_OCUPACAO"].fillna("")

    print("\n" + "=" * 70)
    print("Distribuicao de ocupacao declarada (todas, ordenado por frequencia)")
    print("=" * 70)
    print(df["DS_OCUPACAO"].value_counts().head(20).to_string())

    colunas_mostrar = [c for c in ["NM_URNA_CANDIDATO", "NM_CANDIDATO", "DS_CARGO", "SG_PARTIDO", "DS_OCUPACAO"] if c in df.columns]

    for termo in ("VEREADOR", "PREFEITO"):
        filtrados = df[df["DS_OCUPACAO"].str.upper().str.contains(termo, na=False)]
        print("\n" + "=" * 70)
        print(f"Candidatos que se declaram {termo}: {len(filtrados)}")
        print("=" * 70)
        if not filtrados.empty:
            print(filtrados[colunas_mostrar].to_string(index=False))
        else:
            print("(nenhum)")


if __name__ == "__main__":
    main()
