"""
storage.py

Upload de PDFs (propostas de governo) para o Supabase Storage, usando so
a biblioteca requests contra a API REST de Storage do Supabase (sem
precisar do pacote supabase-py). Documentacao oficial:
https://supabase.com/docs/guides/storage

AVISO: nao pude testar isso contra o Storage real do Supabase (sem
acesso a rede externa no ambiente onde foi escrito). A logica de
montagem de URL/headers foi testada com requests simulados (mocks); a
chamada de rede em si (requests.post) segue a API REST documentada pelo
Supabase. Se algo vier diferente do esperado, me manda o erro que eu
ajusto.
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402


def _headers(content_type: str | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _checar_configuracao() -> None:
    faltando = [
        nome
        for nome, valor in (
            ("SUPABASE_URL", config.SUPABASE_URL),
            ("SUPABASE_SERVICE_ROLE_KEY", config.SUPABASE_SERVICE_ROLE_KEY),
        )
        if not valor
    ]
    if faltando:
        raise RuntimeError(
            "Faltando no .env: " + ", ".join(faltando) + ". Pegue em "
            "Project Settings > API no seu projeto Supabase (a "
            "service_role key e' secreta, nunca exponha no frontend)."
        )


def url_publica(caminho_no_bucket: str) -> str:
    return f"{config.SUPABASE_URL}/storage/v1/object/public/{config.SUPABASE_STORAGE_BUCKET}/{caminho_no_bucket}"


def garantir_bucket_publico() -> None:
    """Cria o bucket de Storage se ele ainda nao existir (idempotente -
    seguro chamar toda vez que o script roda)."""
    _checar_configuracao()
    url = f"{config.SUPABASE_URL}/storage/v1/bucket"
    resp = requests.post(
        url,
        headers=_headers("application/json"),
        json={"name": config.SUPABASE_STORAGE_BUCKET, "public": True},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        print(f"Bucket '{config.SUPABASE_STORAGE_BUCKET}' criado.")
        return
    if resp.status_code in (400, 409) and "already exists" in resp.text.lower():
        return  # ja existe, sem problema
    print(
        f"AVISO ao garantir o bucket '{config.SUPABASE_STORAGE_BUCKET}': "
        f"{resp.status_code} - {resp.text}"
    )


def enviar_pdf(caminho_local: Path, caminho_no_bucket: str) -> str | None:
    """Envia um PDF para o Storage e devolve a URL publica, ou None se
    falhar (o chamador decide se trata isso como erro fatal ou nao)."""
    _checar_configuracao()
    url = f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_STORAGE_BUCKET}/{caminho_no_bucket}"

    with open(caminho_local, "rb") as f:
        conteudo = f.read()

    headers = _headers("application/pdf")
    headers["x-upsert"] = "true"  # permite sobrescrever se o script rodar de novo

    resp = requests.post(url, headers=headers, data=conteudo, timeout=60)
    if resp.status_code not in (200, 201):
        print(f"  [ERRO] falha ao enviar {caminho_local.name}: {resp.status_code} - {resp.text}")
        return None

    return url_publica(caminho_no_bucket)
