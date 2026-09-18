"""
03_subir_pdfs_storage.py

Envia os PDFs de proposta de governo (baixados por 01_baixar_tse.py) para
o Supabase Storage, e atualiza data/processed/candidatos_pi.csv com a URL
publica de cada um (coluna proposta_pdf_url). Isso deixa os PDFs
acessiveis de qualquer lugar - necessario quando o site for publicado na
internet (o servidor que roda o backend pode nao ter os arquivos locais).

REQUISITO: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY configurados no .env
(veja .env.example). A service_role key fica em Project Settings > API >
Project API keys > service_role no seu projeto Supabase - e' secreta,
nunca cole ela em codigo que roda no navegador.

AVISO: nao pude testar isso contra o Storage real do Supabase (sem
acesso a rede externa no ambiente onde foi escrito) - so com requests
simulados (veja scripts/storage.py). Se der erro, me manda a mensagem.

Uso:
    python scripts/03_subir_pdfs_storage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config, storage  # noqa: E402


def main() -> None:
    csv_path = config.PROCESSED_DIR / "candidatos_pi.csv"
    if not csv_path.exists():
        print(f"ERRO: {csv_path} nao existe. Rode antes o 01_baixar_tse.py.")
        raise SystemExit(1)

    df = pd.read_csv(csv_path, dtype=str).fillna("")
    if "proposta_pdf_arquivo" not in df.columns:
        print("ERRO: coluna proposta_pdf_arquivo nao existe no CSV. Rode 01_baixar_tse.py de novo.")
        raise SystemExit(1)

    df["proposta_pdf_url"] = ""

    try:
        storage.garantir_bucket_publico()
    except RuntimeError as exc:
        print(f"ERRO: {exc}")
        raise SystemExit(1)

    total_enviados = 0
    total_com_pdf = (df["proposta_pdf_arquivo"] != "").sum()
    print(f"Candidatos com PDF local para enviar: {total_com_pdf}")

    for idx, row in df.iterrows():
        nome_pdf = row.get("proposta_pdf_arquivo", "")
        if not nome_pdf:
            continue

        caminho_local = config.PROPOSTAS_PDF_DIR / nome_pdf
        if not caminho_local.exists():
            print(f"  [AVISO] PDF listado mas nao encontrado em disco: {caminho_local}")
            continue

        print(f"Enviando: {nome_pdf}")
        # organiza dentro do bucket por ano/UF, ex.: 2026/PI/arquivo.pdf
        caminho_no_bucket = f"{config.ANO_ELEICAO}/{config.UF}/{nome_pdf}"
        url_publica = storage.enviar_pdf(caminho_local, caminho_no_bucket)
        if url_publica:
            df.at[idx, "proposta_pdf_url"] = url_publica
            total_enviados += 1

    df.to_csv(csv_path, index=False)
    print(f"\nPronto! {total_enviados}/{total_com_pdf} PDF(s) enviados ao Supabase Storage.")
    print(f"{csv_path} atualizado com a coluna proposta_pdf_url.")
    if total_enviados < total_com_pdf:
        print(
            "Alguns PDFs nao foram enviados - confira as mensagens de erro acima "
            "(geralmente e' chave/URL do Supabase errada, ou bucket sem permissao)."
        )


if __name__ == "__main__":
    main()
