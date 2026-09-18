"""
busca.py

Logica pura de busca e montagem de detalhe de candidato, separada dos
endpoints do FastAPI para ser facil de testar sem precisar subir um
servidor web. Le do Postgres (Supabase) via scripts/db.py.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config, db  # noqa: E402

try:
    from rapidfuzz import fuzz

    def _similaridade(a: str, b: str) -> float:
        return fuzz.token_sort_ratio(a, b)
except ImportError:
    from difflib import SequenceMatcher

    def _similaridade(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100

LIMIAR_SCORE_BUSCA = 55.0


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", texto)).strip().upper()


def _sem_decimal(valor):
    """psycopg2 devolve colunas NUMERIC como Decimal, que nao serializa em
    JSON por padrao. Convertemos pra float na saida da consulta."""
    return float(valor) if isinstance(valor, Decimal) else valor


def _linha_para_dict(linha) -> dict:
    return {chave: _sem_decimal(valor) for chave, valor in dict(linha).items()}


def buscar_candidatos(termo: str, cargo: str | None = None, limite: int = 20) -> list[dict]:
    termo_norm = normalizar(termo)
    if not termo_norm:
        return []

    conn = db.get_connection()
    try:
        with db.dict_cursor(conn) as cur:
            if cargo:
                cur.execute("SELECT * FROM candidatos WHERE cargo = %s", (cargo.upper(),))
            else:
                cur.execute("SELECT * FROM candidatos")
            linhas = [_linha_para_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    resultados = []
    for candidato in linhas:
        nome_urna_norm = normalizar(candidato.get("nome_urna", "") or "")
        nome_civil_norm = normalizar(candidato.get("nome_civil", "") or "")

        score = max(
            _similaridade(termo_norm, nome_urna_norm),
            _similaridade(termo_norm, nome_civil_norm),
        )
        if termo_norm in nome_urna_norm or termo_norm in nome_civil_norm:
            score = max(score, 90.0)

        if score >= LIMIAR_SCORE_BUSCA:
            candidato["_score"] = score
            # mantem o mesmo contrato "1"/"0" que o frontend ja espera
            candidato["incumbente"] = "1" if candidato.get("incumbente") else "0"
            resultados.append(candidato)

    resultados.sort(key=lambda c: c["_score"], reverse=True)
    return resultados[:limite]


def _consulta_opcional(conn, tabela: str, parlamentar_id: str, ordem: str) -> list[dict]:
    try:
        with db.dict_cursor(conn) as cur:
            cur.execute(
                f"SELECT * FROM {tabela} WHERE parlamentar_id = %s ORDER BY {ordem}",
                (parlamentar_id,),
            )
            return [_linha_para_dict(r) for r in cur.fetchall()]
    except Exception:
        # tabela pode nao existir/estar vazia se aquele passo de coleta nao
        # foi rodado ainda - nao deve quebrar a pagina do candidato por isso.
        conn.rollback()
        return []


def detalhar_candidato(sq_candidato: str) -> dict | None:
    conn = db.get_connection()
    try:
        with db.dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM candidatos WHERE sq_candidato = %s", (sq_candidato,))
            linha = cur.fetchone()
        if not linha:
            return None

        candidato = _linha_para_dict(linha)
        pid = candidato.get("parlamentar_id") or ""

        candidato["gestao_despesas"] = []
        candidato["gestao_receitas"] = []
        candidato["gestao_contratos"] = []
        candidato["gestao_licitacoes"] = []
        candidato["gestao_convenios"] = []

        if candidato.get("incumbente") and pid:
            candidato["despesas"] = _consulta_opcional(conn, "despesas", pid, "ano DESC, mes DESC")
            candidato["proposicoes"] = _consulta_opcional(conn, "proposicoes", pid, "ano DESC")
            candidato["emendas"] = _consulta_opcional(conn, "emendas", pid, "ano DESC")

            # Ficha de gestao do Executivo estadual (Governador titular) -
            # fontes diferentes das de deputado/senador (Portal da
            # Transparencia do Piaui em vez de Camara/Senado/CGU), entao
            # ficam em tabelas proprias (ver scripts/10_baixar_transparencia_pi.py).
            if candidato.get("parlamentar_origem") == "executivo_estadual":
                candidato["gestao_despesas"] = _consulta_opcional(conn, "gestao_despesas", pid, "ano DESC, total_empenhado DESC")
                candidato["gestao_receitas"] = _consulta_opcional(conn, "gestao_receitas", pid, "ano DESC, total_realizado DESC")
                candidato["gestao_contratos"] = _consulta_opcional(conn, "gestao_contratos", pid, "ano DESC, valor_contratado DESC")
                candidato["gestao_licitacoes"] = _consulta_opcional(conn, "gestao_licitacoes", pid, "ano DESC, valor_total_previsto DESC")
                candidato["gestao_convenios"] = _consulta_opcional(conn, "gestao_convenios", pid, "ano DESC, valor_total DESC")
        else:
            candidato["despesas"] = []
            candidato["proposicoes"] = []
            candidato["emendas"] = []

        texto_arquivo = candidato.get("proposta_texto_arquivo")
        candidato["proposta_texto_completo"] = ""
        if texto_arquivo:
            caminho = config.PROPOSTAS_TXT_DIR / texto_arquivo
            if caminho.exists():
                candidato["proposta_texto_completo"] = caminho.read_text(encoding="utf-8")

        # No front, o campo "incumbente" era comparado como string "1"/"0";
        # aqui ja e' bool nativo do Postgres. Normalizamos pra "1"/"0" na
        # saida da API so pra manter o mesmo contrato que o frontend usa.
        candidato["incumbente"] = "1" if candidato.get("incumbente") else "0"

        return candidato
    finally:
        conn.close()
