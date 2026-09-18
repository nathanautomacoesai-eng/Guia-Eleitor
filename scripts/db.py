"""
db.py

Conexao com o banco Postgres (Supabase) compartilhada pelo pipeline de
coleta (scripts/07_montar_banco.py) e pelo backend (backend/busca.py).

AVISO: escrito num ambiente sem acesso a rede a servidores Postgres
externos, entao a conexao de verdade com o Supabase nao pode ser testada
por mim. O que foi validado: o schema (db/schema.sql) foi aplicado e
testado contra um Postgres real (versao 16); as funcoes de transformacao
de dados (scripts/07_montar_banco.py) tem testes unitarios proprios. Se a
conexao der erro, confira se DATABASE_URL em .env esta exatamente igual
ao que o Supabase mostra em Project Settings > Database > Connection
string > URI (trocando [YOUR-PASSWORD] pela senha real).
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402


def _dividir_dsn(url: str) -> tuple[str, str, str, str, str, str]:
    """Quebra uma connection string postgresql://usuario:senha@host:porta/banco?query
    nas suas partes, na mao (sem usar urllib.parse.urlsplit).

    Por que na mao: urlsplit() do Python valida se colchetes '[' ']' estao
    balanceados em QUALQUER parte da URL (pensando em host IPv6), e explode
    com 'ValueError: Invalid IPv6 URL' se sobrar um colchete solto em algum
    lugar - por exemplo, se ao colar a senha no .env sobrou um '[' ou ']' do
    placeholder original do Supabase ("[YOUR-PASSWORD]"). Como o Supabase
    sempre usa host por nome (nunca IPv6 literal), fazemos a divisao manual
    e evitamos essa checagem completamente.
    """
    resto = url.split("://", 1)[1] if "://" in url else url

    if "@" in resto:
        userinfo, resto_host = resto.rsplit("@", 1)
    else:
        userinfo, resto_host = "", resto

    if ":" in userinfo:
        usuario, senha = userinfo.split(":", 1)
    else:
        usuario, senha = userinfo, ""

    query = ""
    if "?" in resto_host:
        resto_host, query = resto_host.split("?", 1)

    dbname = ""
    if "/" in resto_host:
        hostport, dbname = resto_host.split("/", 1)
    else:
        hostport = resto_host

    if ":" in hostport:
        host, porta = hostport.rsplit(":", 1)
    else:
        host, porta = hostport, ""

    return usuario, senha, host, porta, dbname, query


def get_connection() -> "psycopg2.extensions.connection":
    """Conecta no Postgres (Supabase).

    Em vez de passar a DATABASE_URL inteira (uma unica string) para
    psycopg2.connect(), quebramos ela em host/porta/usuario/senha/etc e
    passamos cada pedaco separado. Isso evita um bug conhecido do
    psycopg2/libpq no Windows em que uma connection string com qualquer
    caractere fora do ASCII (por exemplo um acento que tenha entrado sem
    querer no .env, ou um caractere especial na senha) causa
    'UnicodeDecodeError: invalid continuation byte' ao conectar - mesmo
    quando o .env em si foi lido certinho como UTF-8.
    """
    if not config.DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL nao configurada. Copie .env.example para .env e "
            "cole a connection string do seu projeto Supabase (Project "
            "Settings > Database > Connection string > URI)."
        )

    usuario, senha, host, porta, nome_banco, query = _dividir_dsn(config.DATABASE_URL)
    parametros_extra = {chave: valores[0] for chave, valores in parse_qs(query).items()}

    try:
        return psycopg2.connect(
            host=host,
            port=int(porta) if porta else 5432,
            dbname=nome_banco or "postgres",
            user=unquote(usuario) if usuario else None,
            password=unquote(senha) if senha else None,
            **parametros_extra,
        )
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            "Erro de codificacao ao conectar no banco (UnicodeDecodeError). "
            "Isso costuma acontecer quando o .env foi salvo em um formato "
            "diferente de UTF-8 no Windows, ou quando a senha do banco tem "
            "algum caractere especial/acentuado. Tente: 1) reabrir o .env no "
            "VS Code e salvar de novo escolhendo 'Save with Encoding > UTF-8' "
            "(sem BOM); 2) se persistir, redefinir a senha do banco no "
            "Supabase (Database > Settings > Reset database password) usando "
            "so letras e numeros, e atualizar o DATABASE_URL no .env."
        ) from exc


def aplicar_schema(conn: "psycopg2.extensions.connection") -> None:
    """Recria as tabelas do zero a partir de db/schema.sql. Chamado sempre
    que o pipeline de coleta e' rodado de novo - o banco e' reconstruido
    inteiro a cada rodada, entao nao guarde nada manualmente nele."""
    sql = config.SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def dict_cursor(conn: "psycopg2.extensions.connection"):
    """Cursor que devolve cada linha como dict (nome_coluna -> valor),
    equivalente ao sqlite3.Row usado antes na versao SQLite."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
