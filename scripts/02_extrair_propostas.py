"""
02_extrair_propostas.py

Extrai o texto de cada PDF de "proposta de governo" baixado pelo
01_baixar_tse.py e atualiza data/processed/candidatos_pi.csv com:
  - proposta_texto_arquivo: caminho do .txt com o texto extraido
  - proposta_resumo: um resumo bem simples (primeiros paragrafos nao vazios)

OBS: PDFs escaneados como imagem (sem camada de texto) vao gerar um .txt
vazio, porque a biblioteca usada aqui (pypdf) nao faz OCR. Se isso
acontecer com muitos candidatos, me avise que ajustamos com OCR depois.

Uso:
    python scripts/02_extrair_propostas.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402


def extrair_texto_pdf(caminho_pdf: Path) -> str:
    try:
        reader = PdfReader(str(caminho_pdf))
    except Exception as exc:  # arquivo corrompido, protegido por senha, etc.
        print(f"  [ERRO] nao consegui abrir {caminho_pdf.name}: {exc}")
        return ""

    partes = []
    for pagina in reader.pages:
        try:
            partes.append(pagina.extract_text() or "")
        except Exception as exc:
            print(f"  [AVISO] falha ao extrair uma pagina de {caminho_pdf.name}: {exc}")
    return "\n".join(partes).strip()


def montar_resumo(texto: str, tamanho_max: int = 600) -> str:
    """Resumo bem simples: pega os primeiros paragrafos ate um tamanho
    maximo. Nao substitui um resumo feito com IA, mas serve pra dar uma
    previa na listagem de busca sem abrir o PDF inteiro."""
    if not texto:
        return ""
    paragrafos = [p.strip() for p in texto.split("\n") if p.strip()]
    resumo = ""
    for p in paragrafos:
        candidato = (resumo + " " + p).strip()
        if len(candidato) > tamanho_max:
            break
        resumo = candidato
    return resumo or texto[:tamanho_max]


def main() -> None:
    csv_path = config.PROCESSED_DIR / "candidatos_pi.csv"
    if not csv_path.exists():
        print(f"ERRO: {csv_path} nao existe. Rode antes o 01_baixar_tse.py.")
        raise SystemExit(1)

    df = pd.read_csv(csv_path, dtype=str).fillna("")
    df["proposta_texto_arquivo"] = ""
    df["proposta_resumo"] = ""

    total_com_pdf = (df["proposta_pdf_arquivo"] != "").sum()
    print(f"Candidatos com PDF de proposta vinculado: {total_com_pdf}")

    vazios = 0
    for idx, row in df.iterrows():
        nome_pdf = row.get("proposta_pdf_arquivo", "")
        if not nome_pdf:
            continue

        caminho_pdf = config.PROPOSTAS_PDF_DIR / nome_pdf
        if not caminho_pdf.exists():
            print(f"  [AVISO] PDF listado mas nao encontrado em disco: {caminho_pdf}")
            continue

        print(f"Extraindo texto de: {nome_pdf}")
        texto = extrair_texto_pdf(caminho_pdf)
        if not texto:
            vazios += 1

        nome_txt = caminho_pdf.stem + ".txt"
        caminho_txt = config.PROPOSTAS_TXT_DIR / nome_txt
        caminho_txt.write_text(texto, encoding="utf-8")

        df.at[idx, "proposta_texto_arquivo"] = nome_txt
        df.at[idx, "proposta_resumo"] = montar_resumo(texto)

    df.to_csv(csv_path, index=False)
    print(f"\nPronto! {csv_path} atualizado com texto/resumo das propostas.")
    if vazios:
        print(
            f"AVISO: {vazios} PDF(s) resultaram em texto vazio (provavelmente "
            "sao paginas escaneadas como imagem, sem OCR)."
        )


if __name__ == "__main__":
    main()
