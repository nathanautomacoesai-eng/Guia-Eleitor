"""
Configuracoes centrais do Guia Eleitor - recorte Piaui (PI), eleicoes 2026.

Ajuste aqui o ano, a UF e os cargos incluidos, se um dia quiser expandir
para outro estado ou incluir mais cargos.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Recorte do projeto ---
ANO_ELEICAO = 2026
UF = "PI"

# Valores de DS_CARGO como aparecem no TSE que queremos manter.
CARGOS_DESEJADOS = {
    "GOVERNADOR",
    "SENADOR",
    "DEPUTADO FEDERAL",
    "DEPUTADO ESTADUAL",
}

# --- Caminhos ---
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
PROPOSTAS_PDF_DIR = RAW_DIR / "propostas_pdf"
PROPOSTAS_TXT_DIR = PROCESSED_DIR / "propostas_texto"
DB_PATH = PROCESSED_DIR / "guia_eleitor.db"  # nao usado mais (era do SQLite) - mantido so por referencia

# Pasta de dados mantidos A MAO (nao gerados por script, nao apagar/
# sobrescrever): hoje so' o CSV de links externos de candidatos sem
# proposta de governo no TSE (ver 07_montar_banco.py). Ao contrario de
# raw/ e processed/, isso DEVE ser versionado no git.
MANUAL_DIR = DATA_DIR / "manual"
LINKS_EXTERNOS_CSV = MANUAL_DIR / "links_externos_pi.csv"

# --- Banco de dados (Postgres / Supabase) ---
# Connection string do seu projeto Supabase: Project Settings > Database >
# Connection string > URI. Cole em .env (copie de .env.example).
DATABASE_URL = os.getenv("DATABASE_URL", "")
SCHEMA_SQL_PATH = BASE_DIR / "db" / "schema.sql"

# --- Supabase Storage (PDFs das propostas de governo) ---
# Pegue em Project Settings > API no seu projeto Supabase.
# SUPABASE_URL e' publico (ex.: https://xxxxxxxx.supabase.co).
# SUPABASE_SERVICE_ROLE_KEY e' SECRETA - nunca exponha em frontend/navegador.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "propostas-governo")

for d in (RAW_DIR, PROCESSED_DIR, PROPOSTAS_PDF_DIR, PROPOSTAS_TXT_DIR, MANUAL_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- Fontes oficiais (TSE - Portal de Dados Abertos) ---
# Confirmadas em set/2026 em https://dadosabertos.tse.jus.br/dataset/candidatos-2026
TSE_CANDIDATOS_ZIP_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/"
    f"consulta_cand_{ANO_ELEICAO}.zip"
)
TSE_PROPOSTA_GOVERNO_ZIP_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/proposta_governo/"
    f"proposta_governo_{ANO_ELEICAO}_{UF}.zip"
)
TSE_BENS_ZIP_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/"
    f"bem_candidato_{ANO_ELEICAO}.zip"
)
TSE_FOTOS_ZIP_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes"
    f"{ANO_ELEICAO}/fotos/foto_cand{ANO_ELEICAO}_{UF}_div.zip"
)

# --- Camara dos Deputados (dados abertos) ---
CAMARA_API_BASE = "https://dadosabertos.camara.leg.br/api/v2"

# --- Senado Federal (dados abertos legislativos) ---
SENADO_API_BASE = "https://legis.senado.leg.br/dadosabertos"

# --- Portal da Transparencia (CGU) ---
PORTAL_TRANSPARENCIA_BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
PORTAL_TRANSPARENCIA_API_KEY = os.getenv("PORTAL_TRANSPARENCIA_API_KEY", "")

USER_AGENT = "GuiaEleitorPI/0.1 (uso publico e nao comercial; contato: projeto pessoal)"

# --- Portal da Transparencia do Piaui (Poder Executivo estadual) ---
# Usado para a "ficha de gestao" de candidatos a Governador que ja sao
# o titular atual do cargo (analogo as emendas/despesas de deputado,
# mas aqui e' execucao orcamentaria do estado: despesa, receita,
# contrato, licitacao, convenio). Descoberta via inspecao do trafego de
# rede do site (o site e' uma SPA que consome essa API separada, o
# dominio publico transparencia.pi.gov.br so' serve o front-end).
# Sem necessidade de chave. Ver scripts/09_diagnostico_transparencia_pi.py.
TRANSPARENCIA_PI_API_BASE = "https://api.transparencia.pi.gov.br/api"

# Identificador sintetico usado na tabela "parlamentares" (origem
# 'executivo_estadual') pra representar o titular atual do Executivo
# estadual, do mesmo jeito que deputados/senadores tem um id vindo da
# Camara/Senado. Nao vem de nenhuma API externa, e' definido aqui mesmo.
GOVERNADOR_ATUAL_ID = "PI-EXEC-GOVERNADOR"

# Nome civil (aproximado) do governador atual do Piaui, usado para
# vincular o candidato a Governador que e' o titular do cargo, do
# mesmo jeito que se faz com deputados/senadores (ver
# scripts/07_montar_banco.py -> vincular_candidatos_a_parlamentares).
# Se o TSE registrar o nome completo de forma diferente, a comparacao
# por similaridade (limiar 92%) ainda deve casar.
GOVERNADOR_ATUAL_NOME_CIVIL = "RAFAEL TAJRA FONTELES"
GOVERNADOR_ATUAL_NOME_ELEITORAL = "Rafael Fonteles"
GOVERNADOR_ATUAL_PARTIDO = "PT"

# Anos do mandato atual a varrer na ingestao (2023 = inicio do mandato,
# ate o ano corrente da eleicao). Ajuste se o mandato mudar.
TRANSPARENCIA_PI_ANOS = [2023, 2024, 2025, 2026]

# --- TSE - DivulgaCandContas (API oficial por tras da pagina publica de
# "Divulgacao de Candidaturas e Contas Eleitorais",
# https://divulgacandcontas.tse.jus.br/divulga/) ---
# Achada inspecionando o trafego de rede da propria pagina do TSE (nao e'
# documentada publicamente, mas e' a mesma API que qualquer pessoa usa
# ao abrir a pagina de um candidato no site do TSE). Da' acesso, por
# candidato, a dados pessoais (grau de instrucao, ocupacao, estado civil,
# foto, bens declarados, sites/redes sociais que o proprio candidato
# informou) e ao resumo da prestacao de contas de campanha (total
# arrecadado, total gasto, maiores doadores/fornecedores).
DIVULGACANDCONTAS_API_BASE = "https://divulgacandcontas.tse.jus.br/divulga/rest/v1"

# Identificador da eleicao usado pela API do TSE acima. CONFIRMADO
# identico para candidatos de cargos diferentes (Deputado Federal,
# Deputado Estadual, Governador) do PI em 2026 via chamada direta a
# API - e' um id por eleicao/UF, nao por candidato ou cargo. Se um dia
# a comparacao neste projeto passar a incluir 2º turno de Governador ou
# outra eleicao, verifique se esse id muda.
TSE_ID_ELEICAO_PI = "20322002026"

# Codigo interno do TSE para cada cargo, usado para montar a URL da
# prestacao de contas (endpoint /prestador/consulta/.../{codigoCargo}/...).
# Confirmado contra a API real pra cada um dos 4 cargos do recorte deste
# projeto.
TSE_CODIGO_CARGO = {
    "GOVERNADOR": 3,
    "SENADOR": 5,
    "DEPUTADO FEDERAL": 6,
    "DEPUTADO ESTADUAL": 7,
}


# --- Assembleia Legislativa do Piaui (ALEPI) ---
# API publica do sistema SAPL (usado por varias casas legislativas
# brasileiras) que a propria ALEPI usa no site dela. Confirmada via
# chamada direta em set/2026: https://sapl.al.pi.leg.br/api/parlamentares/parlamentar/
# Devolve TODOS os parlamentares do historico (paginado); filtramos pelo
# campo "ativo" == true para pegar so quem esta no mandato atual. Nao
# expoe CPF, entao o vinculo com candidatos usa so' comparacao de nome
# (mesmo mecanismo ja usado pra deputado federal/senador quando o CPF
# nao bate).
SAPL_ALEPI_API_BASE = "https://sapl.al.pi.leg.br/api"

