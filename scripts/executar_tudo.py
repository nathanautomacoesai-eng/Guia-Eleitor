"""
executar_tudo.py

Roda a pipeline inteira de coleta e montagem do banco, na ordem certa.
Os passos 04/05/06 (Camara, Senado, Transparencia) sao "melhor esforco":
se algum falhar, o script avisa e continua com o resto, porque o
07_montar_banco.py sabe lidar com dados incompletos. O passo 03 (upload
dos PDFs pro Supabase Storage) tambem e' melhor esforco - se a chave do
Supabase Storage nao estiver configurada, o site ainda funciona servindo
os PDFs localmente.

Uso:
    python scripts/executar_tudo.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PASTA_SCRIPTS = Path(__file__).resolve().parent

PASSOS_OBRIGATORIOS = [
    "01_baixar_tse.py",
]
PASSOS_MELHOR_ESFORCO = [
    "02_extrair_propostas.py",
    "03_subir_pdfs_storage.py",
    "04_baixar_camara.py",
    "05_baixar_senado.py",
    "06_baixar_transparencia.py",
    "08_baixar_camara_teresina.py",
    "10_baixar_transparencia_pi.py",
    "11_baixar_alepi.py",
    "12_baixar_tse_detalhes.py",
]
PASSO_FINAL = "07_montar_banco.py"


def rodar(script: str) -> bool:
    print(f"\n{'=' * 60}\nExecutando {script}\n{'=' * 60}")
    resultado = subprocess.run([sys.executable, str(PASTA_SCRIPTS / script)])
    return resultado.returncode == 0


def main() -> None:
    for script in PASSOS_OBRIGATORIOS:
        if not rodar(script):
            print(f"\nERRO CRITICO em {script}. Corrija antes de continuar.")
            raise SystemExit(1)

    for script in PASSOS_MELHOR_ESFORCO:
        ok = rodar(script)
        if not ok:
            print(f"\nAVISO: {script} falhou. Seguindo sem esses dados (o passo final tolera isso).")

    if not rodar(PASSO_FINAL):
        print(f"\nERRO CRITICO em {PASSO_FINAL}.")
        raise SystemExit(1)

    print("\nPipeline completa! Agora rode: uvicorn backend.app:app --reload")


if __name__ == "__main__":
    main()
