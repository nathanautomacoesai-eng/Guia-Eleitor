-- Schema do Guia Eleitor (Piaui, eleicoes 2026) no Postgres/Supabase.
-- Rodado do zero a cada execucao do scripts/07_montar_banco.py (DROP + CREATE),
-- entao nao guarde nada manualmente direto nessas tabelas - sera apagado.

DROP TABLE IF EXISTS emendas_estaduais CASCADE;
DROP TABLE IF EXISTS gestao_convenios CASCADE;
DROP TABLE IF EXISTS gestao_licitacoes CASCADE;
DROP TABLE IF EXISTS gestao_contratos CASCADE;
DROP TABLE IF EXISTS gestao_receitas CASCADE;
DROP TABLE IF EXISTS gestao_despesas CASCADE;
DROP TABLE IF EXISTS emendas CASCADE;
DROP TABLE IF EXISTS proposicoes CASCADE;
DROP TABLE IF EXISTS despesas CASCADE;
DROP TABLE IF EXISTS candidatos CASCADE;
DROP TABLE IF EXISTS parlamentares CASCADE;

CREATE TABLE parlamentares (
    id TEXT PRIMARY KEY,
    origem TEXT,              -- 'camara' ou 'senado'
    cpf TEXT,
    nome_civil TEXT,
    nome_eleitoral TEXT,
    cargo_atual TEXT,
    uf TEXT,
    partido TEXT,
    email TEXT,
    foto_url TEXT
);

CREATE TABLE candidatos (
    sq_candidato TEXT PRIMARY KEY,
    numero TEXT,
    nome_civil TEXT,
    nome_urna TEXT,
    nome_social TEXT,
    cargo TEXT,
    partido_sigla TEXT,
    partido_nome TEXT,
    coligacao TEXT,
    coligacao_nome TEXT,
    situacao_totalizacao TEXT,
    situacao_candidatura TEXT,
    cpf TEXT,
    email TEXT,
    uf TEXT,
    ano_eleicao TEXT,
    proposta_pdf_arquivo TEXT,
    proposta_pdf_url TEXT,       -- URL publica no Supabase Storage
    proposta_texto_arquivo TEXT,
    proposta_resumo TEXT,
    link_externo_url TEXT,       -- link informado manualmente (ver data/manual/links_externos_pi.csv), quando o candidato nao tem proposta no TSE
    link_externo_rotulo TEXT,
    parlamentar_id TEXT,
    parlamentar_origem TEXT,
    incumbente BOOLEAN DEFAULT FALSE,
    vinculo_confianca TEXT,

    -- Dados complementares direto da API do TSE (DivulgaCandContas),
    -- usados sobretudo pra dar algum contexto sobre candidatos que nao
    -- tem proposta de governo em PDF (ver scripts/12_baixar_tse_detalhes.py)
    grau_instrucao TEXT,
    ocupacao TEXT,
    estado_civil TEXT,
    cor_raca TEXT,
    data_nascimento TEXT,
    foto_url TEXT,
    sites_tse TEXT,               -- sites/redes sociais que o candidato informou ao TSE, separados por " | "
    bens_total NUMERIC,
    prestacao_total_recebido NUMERIC,
    prestacao_total_despesas_contratadas NUMERIC,
    prestacao_total_despesas_pagas NUMERIC,
    prestacao_data_atualizacao TEXT,
    tse_divulga_url TEXT          -- link publico da pagina do candidato no site do TSE
);
CREATE INDEX idx_candidatos_nome_urna ON candidatos (nome_urna);
CREATE INDEX idx_candidatos_cargo ON candidatos (cargo);

-- Sem FOREIGN KEY para parlamentares de proposito: os dados de Camara/Senado/
-- Transparencia sao "melhor esforco" (ver README) e uma FK travaria a carga
-- inteira se um dado vier inconsistente entre as fontes.

CREATE TABLE despesas (
    id SERIAL PRIMARY KEY,
    parlamentar_id TEXT,
    ano INTEGER,
    mes INTEGER,
    tipo_despesa TEXT,
    valor_liquido NUMERIC,
    fornecedor TEXT
);
CREATE INDEX idx_despesas_parlamentar ON despesas (parlamentar_id);

CREATE TABLE proposicoes (
    id SERIAL PRIMARY KEY,
    parlamentar_id TEXT,
    id_proposicao TEXT,
    tipo TEXT,
    numero TEXT,
    ano INTEGER,
    ementa TEXT
);
CREATE INDEX idx_proposicoes_parlamentar ON proposicoes (parlamentar_id);

CREATE TABLE emendas (
    id SERIAL PRIMARY KEY,
    parlamentar_id TEXT,
    parlamentar_nome TEXT,
    ano INTEGER,
    numero_emenda TEXT,
    tipo TEXT,
    funcao TEXT,
    valor_empenhado NUMERIC,
    valor_pago NUMERIC,
    municipio_beneficiario TEXT
);
CREATE INDEX idx_emendas_parlamentar ON emendas (parlamentar_id);


-- --- Ficha de gestao do Poder Executivo estadual (Governador titular) ---
-- Analogo as tabelas de despesas/emendas de deputado, mas aqui vem do
-- Portal da Transparencia do Piaui (transparencia.pi.gov.br), que e' uma
-- API bem mais rica (despesa, receita, contrato, licitacao, convenio).
-- Como o volume bruto e' grande demais pra guardar cada lancamento
-- (despesas/receitas passam de 90 mil linhas/ano so' do estado todo),
-- despesas/receitas/licitacoes vem AGREGADAS (somadas por orgao/categoria/
-- modalidade); contratos e convenios vem detalhados (volume bem menor e
-- sao os que mais interessam ao eleitor - quem recebeu e quanto).
-- Ver scripts/10_baixar_transparencia_pi.py.

CREATE TABLE gestao_despesas (
    id SERIAL PRIMARY KEY,
    parlamentar_id TEXT,
    ano INTEGER,
    orgao_titulo TEXT,
    funcao_titulo TEXT,
    total_empenhado NUMERIC,
    total_liquidado NUMERIC,
    total_pago NUMERIC,
    qtd_lancamentos INTEGER
);
CREATE INDEX idx_gestao_despesas_parlamentar ON gestao_despesas (parlamentar_id);

CREATE TABLE gestao_receitas (
    id SERIAL PRIMARY KEY,
    parlamentar_id TEXT,
    ano INTEGER,
    categoria_titulo TEXT,
    total_previsto NUMERIC,
    total_realizado NUMERIC
);
CREATE INDEX idx_gestao_receitas_parlamentar ON gestao_receitas (parlamentar_id);

CREATE TABLE gestao_contratos (
    id SERIAL PRIMARY KEY,
    parlamentar_id TEXT,
    ano INTEGER,
    num_contrato TEXT,
    orgao TEXT,
    nome_contratada TEXT,
    valor_contratado NUMERIC,
    objeto TEXT,
    status TEXT
);
CREATE INDEX idx_gestao_contratos_parlamentar ON gestao_contratos (parlamentar_id);

CREATE TABLE gestao_licitacoes (
    id SERIAL PRIMARY KEY,
    parlamentar_id TEXT,
    ano INTEGER,
    modalidade TEXT,
    qtd INTEGER,
    valor_total_previsto NUMERIC
);
CREATE INDEX idx_gestao_licitacoes_parlamentar ON gestao_licitacoes (parlamentar_id);

CREATE TABLE gestao_convenios (
    id SERIAL PRIMARY KEY,
    parlamentar_id TEXT,
    ano INTEGER,
    numero_ano TEXT,
    nome_proponente TEXT,
    nome_concedente TEXT,
    valor_total NUMERIC,
    objeto TEXT,
    situacao TEXT,
    tipo_termo TEXT
);
CREATE INDEX idx_gestao_convenios_parlamentar ON gestao_convenios (parlamentar_id);


-- --- Emendas parlamentares ESTADUAIS (Deputado Estadual em exercicio,
-- via ALEPI + Portal da Transparencia do Piaui) - analogo a tabela
-- "emendas" (que e' so de emenda parlamentar FEDERAL/CGU) ---
CREATE TABLE emendas_estaduais (
    id SERIAL PRIMARY KEY,
    parlamentar_id TEXT,
    ano INTEGER,
    emenda_numero TEXT,
    status TEXT,
    modalidade TEXT,
    beneficiario_nome TEXT,
    localidade_beneficiada TEXT,
    objetivo_titulo TEXT,
    valor NUMERIC
);
CREATE INDEX idx_emendas_estaduais_parlamentar ON emendas_estaduais (parlamentar_id);
