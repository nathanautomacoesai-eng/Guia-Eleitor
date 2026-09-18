"""
app.py

Backend FastAPI do Guia Eleitor (recorte Piaui, eleicoes 2026).

Uso local:
    uvicorn backend.app:app --reload
    (depois abra http://127.0.0.1:8000 no navegador)

A logica de busca/consulta fica em backend/busca.py, testada de forma
isolada (sem precisar do FastAPI rodando) em backend/testes_busca.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import busca  # noqa: E402
from scripts import config, db  # noqa: E402

app = FastAPI(
    title="Guia Eleitor - Piaui 2026",
    description=(
        "Consulta publica e nao-partidaria de propostas de governo e "
        "trajetoria de gestao (emendas, gastos, proposicoes) de candidatos "
        "do Piaui nas eleicoes de 2026. Todos os dados vem de fontes "
        "oficiais: TSE, Camara dos Deputados, Senado Federal e Portal da "
        "Transparencia."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent / "static"


@app.get("/api/candidatos/busca")
def api_buscar_candidatos(
    q: str = Query(..., min_length=2, description="Nome (ou parte do nome) do candidato"),
    cargo: str | None = Query(None, description="Filtra por cargo, ex.: GOVERNADOR"),
):
    try:
        resultados = busca.buscar_candidatos(q, cargo=cargo)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"total": len(resultados), "resultados": resultados}


@app.get("/api/candidatos/{sq_candidato}")
def api_detalhar_candidato(sq_candidato: str):
    try:
        candidato = busca.detalhar_candidato(sq_candidato)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if candidato is None:
        raise HTTPException(status_code=404, detail="Candidato nao encontrado")
    return candidato


@app.get("/api/propostas/{nome_arquivo}")
def api_baixar_pdf_proposta(nome_arquivo: str):
    caminho = config.PROPOSTAS_PDF_DIR / nome_arquivo
    if ".." in nome_arquivo or "/" in nome_arquivo or "\\" in nome_arquivo:
        raise HTTPException(status_code=400, detail="Nome de arquivo invalido")
    if not caminho.exists() or caminho.suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    return FileResponse(caminho, media_type="application/pdf")


@app.get("/api/saude")
def api_saude():
    """Endpoint simples pra checar se a conexao com o Postgres (Supabase)
    esta funcionando."""
    try:
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM candidatos")
            total = cur.fetchone()[0]
        conn.close()
        return {"banco_conectado": True, "total_candidatos": total}
    except Exception as exc:
        return {"banco_conectado": False, "erro": str(exc)}


# Frontend estatico (HTML/CSS/JS puro) servido na raiz. Precisa ficar
# DEPOIS das rotas /api/..., senao o mount em "/" engoliria tudo.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
