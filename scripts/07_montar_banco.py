"""
07_montar_banco.py

Consolida todos os CSVs processados (TSE + Camara + Senado + Transparencia)
no banco Postgres (Supabase) usado pelo backend. Recria as tabelas do zero
a cada execucao (veja db/schema.sql).

O passo mais delicado aqui e' descobrir quais candidatos ja ocupam (ou
ocuparam recentemente) um cargo de deputado federal/senador, para
mostrar a "ficha de gestor" (emendas, gastos, proposicoes) junto da
proposta de governo. Isso e' feito em duas etapas, da mais para a menos
confiavel:

  1) Por CPF: o CPF do TSE pode vir parcialmente mascarado (ex.: alguns
     digitos trocados por '*'), entao comparamos apenas os digitos que
     estao visiveis nos dois lados. Se todos os digitos visiveis
     baterem (com um minimo de digitos revelados), consideramos vinculo
     de alta confianca.
  2) Por nome: se nao bateu por CPF, comparamos o nome civil normalizado
     (sem acento, maiusculo) com um limiar de similaridade. Isso e'
     marcado como confianca media - pode gerar algum falso positivo em
     nomes muito comuns, entao o backend deixa isso visivel ao usuario.

Uso:
    python scripts/07_montar_banco.py
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config, db  # noqa: E402

try:
    from rapidfuzz import fuzz

    def similaridade(a: str, b: str) -> float:
        return fuzz.token_sort_ratio(a, b)
except ImportError:
    from difflib import SequenceMatcher

    def similaridade(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100

    print(
        "AVISO: rapidfuzz nao instalado, usando comparador de nomes mais "
        "simples (difflib) como alternativa. Para melhor qualidade de "
        "casamento por nome, rode: pip install rapidfuzz"
    )

LIMIAR_SIMILARIDADE_NOME = 92.0
MINIMO_DIGITOS_CPF_REVELADOS = 4


def normalizar_nome(nome: str) -> str:
    nome = nome or ""
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome = re.sub(r"[^A-Za-z ]", " ", nome).upper()
    return re.sub(r"\s+", " ", nome).strip()


def _apenas_relevantes(cpf: str) -> str:
    return re.sub(r"[.\-/ ]", "", cpf or "")


def cpf_compativel(cpf_a: str, cpf_b: str) -> bool:
    """Compara dois CPFs que podem estar parcialmente mascarados,
    considerando so as posicoes onde AMBOS tem digito."""
    a = _apenas_relevantes(cpf_a)
    b = _apenas_relevantes(cpf_b)
    if len(a) != 11 or len(b) != 11:
        return False

    digitos_revelados = 0
    for ca, cb in zip(a, b):
        if ca.isdigit() and cb.isdigit():
            if ca != cb:
                return False
            digitos_revelados += 1
    return digitos_revelados >= MINIMO_DIGITOS_CPF_REVELADOS


def carregar_csv_opcional(nome_arquivo: str) -> pd.DataFrame:
    caminho = config.PROCESSED_DIR / nome_arquivo
    if not caminho.exists():
        print(f"(info) {nome_arquivo} nao encontrado - seguindo sem esses dados.")
        return pd.DataFrame()
    return pd.read_csv(caminho, dtype=str).fillna("")


def carregar_links_externos() -> pd.DataFrame:
    """CSV mantido a mao (nao gerado por nenhum script) com links de
    candidatos que nao tem proposta de governo registrada no TSE - por
    exemplo Deputado Federal/Estadual, cargos pra que o TSE nao exige
    esse documento (so' e' obrigatorio pra Governador). Ver
    data/manual/links_externos_pi.csv."""
    if not config.LINKS_EXTERNOS_CSV.exists():
        return pd.DataFrame(columns=["sq_candidato", "url", "rotulo"])
    df = pd.read_csv(config.LINKS_EXTERNOS_CSV, dtype=str).fillna("")
    return df[["sq_candidato", "url", "rotulo"]]


def aplicar_links_externos(candidatos: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    candidatos = candidatos.copy()
    candidatos["link_externo_url"] = ""
    candidatos["link_externo_rotulo"] = ""
    if links.empty:
        return candidatos

    links_por_sq = links.set_index("sq_candidato")
    encontrados = 0
    for idx, candidato in candidatos.iterrows():
        sq = str(candidato.get("sq_candidato", ""))
        if sq in links_por_sq.index:
            candidatos.at[idx, "link_externo_url"] = links_por_sq.at[sq, "url"]
            candidatos.at[idx, "link_externo_rotulo"] = links_por_sq.at[sq, "rotulo"] or "Site do candidato"
            encontrados += 1
    if encontrados:
        print(f"Links externos manuais aplicados: {encontrados}/{len(links)}.")
    faltando = set(links["sq_candidato"]) - set(candidatos["sq_candidato"].astype(str))
    if faltando:
        print(f"(aviso) sq_candidato de links_externos_pi.csv nao encontrado em candidatos_pi.csv: {faltando}")
    return candidatos


def montar_parlamentares() -> pd.DataFrame:
    partes = [
        carregar_csv_opcional("parlamentares_camara_pi.csv"),
        carregar_csv_opcional("parlamentares_senado_pi.csv"),
        carregar_csv_opcional("parlamentares_camara_teresina_pi.csv"),
        carregar_csv_opcional("parlamentares_executivo_pi.csv"),
    ]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(
            columns=["id", "origem", "cpf", "nome_civil", "cargo_atual", "uf", "partido"]
        )
    # fillna() de novo depois do concat: se uma coluna existe so' numa
    # das duas fontes (camara/senado), o concat cria NaN (float) pras
    # linhas da outra fonte, mesmo cada CSV ja tendo passado por fillna("")
    # individualmente antes de juntar.
    return pd.concat(partes, ignore_index=True).fillna("")


def vincular_candidatos_a_parlamentares(
    candidatos: pd.DataFrame, parlamentares: pd.DataFrame
) -> pd.DataFrame:
    candidatos = candidatos.copy()
    candidatos["parlamentar_id"] = ""
    candidatos["parlamentar_origem"] = ""
    candidatos["incumbente"] = "0"
    candidatos["vinculo_confianca"] = ""

    if parlamentares.empty:
        return candidatos

    parlamentares = parlamentares.copy()
    parlamentares["nome_normalizado"] = parlamentares["nome_civil"].apply(normalizar_nome)

    for idx, candidato in candidatos.iterrows():
        cpf_candidato = candidato.get("cpf", "")
        nome_candidato_norm = normalizar_nome(candidato.get("nome_civil", ""))

        melhor_id = ""
        melhor_origem = ""
        melhor_confianca = ""
        melhor_score = 0.0

        for _, parlamentar in parlamentares.iterrows():
            if cpf_candidato and parlamentar.get("cpf") and cpf_compativel(
                cpf_candidato, parlamentar["cpf"]
            ):
                melhor_id = parlamentar["id"]
                melhor_origem = parlamentar["origem"]
                melhor_confianca = "alta (CPF)"
                melhor_score = 100.0
                break

            score = similaridade(nome_candidato_norm, parlamentar["nome_normalizado"])
            if score > melhor_score and score >= LIMIAR_SIMILARIDADE_NOME:
                melhor_id = parlamentar["id"]
                melhor_origem = parlamentar["origem"]
                melhor_confianca = f"media (nome, {score:.0f}%)"
                melhor_score = score

        if melhor_id:
            candidatos.at[idx, "parlamentar_id"] = melhor_id
            candidatos.at[idx, "parlamentar_origem"] = melhor_origem
            candidatos.at[idx, "incumbente"] = "1"
            candidatos.at[idx, "vinculo_confianca"] = melhor_confianca

    total_vinculados = (candidatos["incumbente"] == "1").sum()
    print(f"Candidatos vinculados a um mandato atual: {total_vinculados}/{len(candidatos)}")
    return candidatos


# --- Conversao de tipos: os CSVs vem tudo como string (dtype=str), aqui
# convertemos pro tipo real de cada coluna do Postgres antes de inserir. ---

def _para_bool(valor: str) -> bool:
    return str(valor).strip() == "1"


def _para_numero(valor, tipo=float):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    valor = str(valor).strip()
    if valor in ("", "nan", "None"):
        return None
    try:
        return tipo(float(valor))
    except (TypeError, ValueError):
        return None


def _para_inteiro(valor):
    return _para_numero(valor, tipo=int)


def _para_numero_brasileiro(valor) -> float | None:
    """Converte numero no formato brasileiro (ponto = milhar, virgula =
    decimal - ex.: '1.099.900,00' ou '- 26.002,00') para float. Usado nos
    valores de emendas, que a API do Portal da Transparencia devolve como
    texto formatado assim (diferente da API da Camara, que ja manda numero
    puro tipo 4000.0 - por isso essa funcao e' separada de _para_numero)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    txt = str(valor).strip()
    if txt in ("", "nan", "None"):
        return None
    negativo = txt.startswith("-")
    if negativo:
        txt = txt[1:].strip()
    txt = txt.replace(".", "").replace(",", ".")
    try:
        numero = float(txt)
    except ValueError:
        return None
    return -numero if negativo else numero


def _vazio_para_none(valor) -> str | None:
    """Converte string vazia (ou NaN/None/qualquer coisa 'vazia') em None,
    do jeito que o Postgres espera para colunas opcionais. Aceita qualquer
    tipo de entrada (nao so string) porque pandas pode entregar float('nan')
    em colunas que ficaram sem valor depois de um concat/merge entre fontes
    com colunas diferentes."""
    if valor is None:
        return None
    if isinstance(valor, float) and pd.isna(valor):
        return None
    valor = str(valor).strip()
    if valor in ("", "nan", "None", "NaT"):
        return None
    return valor


COLUNAS_CANDIDATOS = [
    "sq_candidato", "numero", "nome_civil", "nome_urna", "nome_social", "cargo",
    "partido_sigla", "partido_nome", "coligacao", "coligacao_nome",
    "situacao_totalizacao", "situacao_candidatura", "cpf", "email", "uf",
    "ano_eleicao", "proposta_pdf_arquivo", "proposta_pdf_url",
    "proposta_texto_arquivo", "proposta_resumo", "parlamentar_id",
    "parlamentar_origem", "incumbente", "vinculo_confianca",
    "link_externo_url", "link_externo_rotulo",
]

COLUNAS_PARLAMENTARES = [
    "id", "origem", "cpf", "nome_civil", "nome_eleitoral", "cargo_atual", "uf",
    "partido", "email", "foto_url",
]

COLUNAS_GESTAO_DESPESAS = [
    "parlamentar_id", "ano", "orgao_titulo", "funcao_titulo",
    "total_empenhado", "total_liquidado", "total_pago", "qtd_lancamentos",
]
COLUNAS_GESTAO_RECEITAS = [
    "parlamentar_id", "ano", "categoria_titulo", "total_previsto", "total_realizado",
]
COLUNAS_GESTAO_CONTRATOS = [
    "parlamentar_id", "ano", "num_contrato", "orgao", "nome_contratada",
    "valor_contratado", "objeto", "status",
]
COLUNAS_GESTAO_LICITACOES = [
    "parlamentar_id", "ano", "modalidade", "qtd", "valor_total_previsto",
]
COLUNAS_GESTAO_CONVENIOS = [
    "parlamentar_id", "ano", "numero_ano", "nome_proponente", "nome_concedente",
    "valor_total", "objeto", "situacao", "tipo_termo",
]


def _linha_candidato_para_tupla(row: dict) -> tuple:
    valores = []
    for col in COLUNAS_CANDIDATOS:
        val = row.get(col, "")
        if col == "incumbente":
            valores.append(_para_bool(val))
        else:
            valores.append(_vazio_para_none(val))
    return tuple(valores)


def _linha_parlamentar_para_tupla(row: dict) -> tuple:
    return tuple(_vazio_para_none(row.get(col, "")) for col in COLUNAS_PARLAMENTARES)


def _linha_despesa_para_tupla(row: dict) -> tuple:
    return (
        _vazio_para_none(row.get("parlamentar_id", "")),
        _para_inteiro(row.get("ano", "")),
        _para_inteiro(row.get("mes", "")),
        _vazio_para_none(row.get("tipo_despesa", "")),
        _para_numero(row.get("valor_liquido", "")),
        _vazio_para_none(row.get("fornecedor", "")),
    )


def _linha_proposicao_para_tupla(row: dict) -> tuple:
    return (
        _vazio_para_none(row.get("parlamentar_id", "")),
        _vazio_para_none(row.get("id_proposicao", "")),
        _vazio_para_none(row.get("tipo", "")),
        _vazio_para_none(row.get("numero", "")),
        _para_inteiro(row.get("ano", "")),
        _vazio_para_none(row.get("ementa", "")),
    )


def _linha_emenda_para_tupla(row: dict) -> tuple:
    return (
        _vazio_para_none(row.get("parlamentar_id", "")),
        _vazio_para_none(row.get("parlamentar_nome", "")),
        _para_inteiro(row.get("ano", "")),
        _vazio_para_none(row.get("numero_emenda", "")),
        _vazio_para_none(row.get("tipo", "")),
        _vazio_para_none(row.get("funcao", "")),
        _para_numero_brasileiro(row.get("valor_empenhado", "")),
        _para_numero_brasileiro(row.get("valor_pago", "")),
        _vazio_para_none(row.get("municipio_beneficiario", "")),
    )


def _linha_gestao_despesa_para_tupla(row: dict) -> tuple:
    return (
        _vazio_para_none(row.get("parlamentar_id", "")),
        _para_inteiro(row.get("ano", "")),
        _vazio_para_none(row.get("orgao_titulo", "")),
        _vazio_para_none(row.get("funcao_titulo", "")),
        _para_numero(row.get("total_empenhado", "")),
        _para_numero(row.get("total_liquidado", "")),
        _para_numero(row.get("total_pago", "")),
        _para_inteiro(row.get("qtd_lancamentos", "")),
    )


def _linha_gestao_receita_para_tupla(row: dict) -> tuple:
    return (
        _vazio_para_none(row.get("parlamentar_id", "")),
        _para_inteiro(row.get("ano", "")),
        _vazio_para_none(row.get("categoria_titulo", "")),
        _para_numero(row.get("total_previsto", "")),
        _para_numero(row.get("total_realizado", "")),
    )


def _linha_gestao_contrato_para_tupla(row: dict) -> tuple:
    return (
        _vazio_para_none(row.get("parlamentar_id", "")),
        _para_inteiro(row.get("ano", "")),
        _vazio_para_none(row.get("num_contrato", "")),
        _vazio_para_none(row.get("orgao", "")),
        _vazio_para_none(row.get("nome_contratada", "")),
        _para_numero(row.get("valor_contratado", "")),
        _vazio_para_none(row.get("objeto", "")),
        _vazio_para_none(row.get("status", "")),
    )


def _linha_gestao_licitacao_para_tupla(row: dict) -> tuple:
    return (
        _vazio_para_none(row.get("parlamentar_id", "")),
        _para_inteiro(row.get("ano", "")),
        _vazio_para_none(row.get("modalidade", "")),
        _para_inteiro(row.get("qtd", "")),
        _para_numero(row.get("valor_total_previsto", "")),
    )


def _linha_gestao_convenio_para_tupla(row: dict) -> tuple:
    return (
        _vazio_para_none(row.get("parlamentar_id", "")),
        _para_inteiro(row.get("ano", "")),
        _vazio_para_none(row.get("numero_ano", "")),
        _vazio_para_none(row.get("nome_proponente", "")),
        _vazio_para_none(row.get("nome_concedente", "")),
        _para_numero(row.get("valor_total", "")),
        _vazio_para_none(row.get("objeto", "")),
        _vazio_para_none(row.get("situacao", "")),
        _vazio_para_none(row.get("tipo_termo", "")),
    )


def montar_banco(
    candidatos: pd.DataFrame,
    parlamentares: pd.DataFrame,
    despesas: pd.DataFrame,
    proposicoes: pd.DataFrame,
    emendas: pd.DataFrame,
    gestao_despesas: pd.DataFrame,
    gestao_receitas: pd.DataFrame,
    gestao_contratos: pd.DataFrame,
    gestao_licitacoes: pd.DataFrame,
    gestao_convenios: pd.DataFrame,
) -> None:
    conn = db.get_connection()
    try:
        db.aplicar_schema(conn)

        with conn.cursor() as cur:
            if not parlamentares.empty:
                tuplas = [_linha_parlamentar_para_tupla(r) for r in parlamentares.to_dict("records")]
                execute_values(
                    cur,
                    f"INSERT INTO parlamentares ({', '.join(COLUNAS_PARLAMENTARES)}) VALUES %s",
                    tuplas,
                )
                print(f"Inseridos {len(tuplas)} parlamentar(es).")

            tuplas = [_linha_candidato_para_tupla(r) for r in candidatos.to_dict("records")]
            execute_values(
                cur,
                f"INSERT INTO candidatos ({', '.join(COLUNAS_CANDIDATOS)}) VALUES %s",
                tuplas,
            )
            print(f"Inseridos {len(tuplas)} candidato(s).")

            if not despesas.empty:
                tuplas = [_linha_despesa_para_tupla(r) for r in despesas.to_dict("records")]
                execute_values(
                    cur,
                    "INSERT INTO despesas (parlamentar_id, ano, mes, tipo_despesa, "
                    "valor_liquido, fornecedor) VALUES %s",
                    tuplas,
                )
                print(f"Inseridas {len(tuplas)} linha(s) de despesas.")

            if not proposicoes.empty:
                tuplas = [_linha_proposicao_para_tupla(r) for r in proposicoes.to_dict("records")]
                execute_values(
                    cur,
                    "INSERT INTO proposicoes (parlamentar_id, id_proposicao, tipo, "
                    "numero, ano, ementa) VALUES %s",
                    tuplas,
                )
                print(f"Inseridas {len(tuplas)} proposicao(oes).")

            if not emendas.empty:
                tuplas = [_linha_emenda_para_tupla(r) for r in emendas.to_dict("records")]
                execute_values(
                    cur,
                    "INSERT INTO emendas (parlamentar_id, parlamentar_nome, ano, "
                    "numero_emenda, tipo, funcao, valor_empenhado, valor_pago, "
                    "municipio_beneficiario) VALUES %s",
                    tuplas,
                )
                print(f"Inseridas {len(tuplas)} emenda(s).")

            if not gestao_despesas.empty:
                tuplas = [_linha_gestao_despesa_para_tupla(r) for r in gestao_despesas.to_dict("records")]
                execute_values(
                    cur,
                    f"INSERT INTO gestao_despesas ({', '.join(COLUNAS_GESTAO_DESPESAS)}) VALUES %s",
                    tuplas,
                )
                print(f"Inseridas {len(tuplas)} linha(s) de gestao_despesas.")

            if not gestao_receitas.empty:
                tuplas = [_linha_gestao_receita_para_tupla(r) for r in gestao_receitas.to_dict("records")]
                execute_values(
                    cur,
                    f"INSERT INTO gestao_receitas ({', '.join(COLUNAS_GESTAO_RECEITAS)}) VALUES %s",
                    tuplas,
                )
                print(f"Inseridas {len(tuplas)} linha(s) de gestao_receitas.")

            if not gestao_contratos.empty:
                tuplas = [_linha_gestao_contrato_para_tupla(r) for r in gestao_contratos.to_dict("records")]
                execute_values(
                    cur,
                    f"INSERT INTO gestao_contratos ({', '.join(COLUNAS_GESTAO_CONTRATOS)}) VALUES %s",
                    tuplas,
                )
                print(f"Inseridos {len(tuplas)} contrato(s) de gestao.")

            if not gestao_licitacoes.empty:
                tuplas = [_linha_gestao_licitacao_para_tupla(r) for r in gestao_licitacoes.to_dict("records")]
                execute_values(
                    cur,
                    f"INSERT INTO gestao_licitacoes ({', '.join(COLUNAS_GESTAO_LICITACOES)}) VALUES %s",
                    tuplas,
                )
                print(f"Inseridas {len(tuplas)} linha(s) de gestao_licitacoes.")

            if not gestao_convenios.empty:
                tuplas = [_linha_gestao_convenio_para_tupla(r) for r in gestao_convenios.to_dict("records")]
                execute_values(
                    cur,
                    f"INSERT INTO gestao_convenios ({', '.join(COLUNAS_GESTAO_CONVENIOS)}) VALUES %s",
                    tuplas,
                )
                print(f"Inseridos {len(tuplas)} convenio(s)/parceria(s) de gestao.")

        conn.commit()
    finally:
        conn.close()


def main() -> None:
    candidatos = carregar_csv_opcional("candidatos_pi.csv")
    if candidatos.empty:
        print("ERRO: data/processed/candidatos_pi.csv nao existe ou esta vazio.")
        print("Rode antes: python scripts/01_baixar_tse.py")
        raise SystemExit(1)

    candidatos = aplicar_links_externos(candidatos, carregar_links_externos())

    parlamentares = montar_parlamentares()
    despesas = pd.concat(
        [carregar_csv_opcional("despesas_camara_pi.csv"), carregar_csv_opcional("despesas_camara_teresina_pi.csv")],
        ignore_index=True,
    ).fillna("")
    proposicoes = carregar_csv_opcional("proposicoes_camara_pi.csv")
    emendas = pd.concat(
        [carregar_csv_opcional("emendas_pi.csv"), carregar_csv_opcional("emendas_camara_teresina_pi.csv")],
        ignore_index=True,
    ).fillna("")

    gestao_despesas = carregar_csv_opcional("gestao_despesas_pi.csv")
    gestao_receitas = carregar_csv_opcional("gestao_receitas_pi.csv")
    gestao_contratos = carregar_csv_opcional("gestao_contratos_pi.csv")
    gestao_licitacoes = carregar_csv_opcional("gestao_licitacoes_pi.csv")
    gestao_convenios = carregar_csv_opcional("gestao_convenios_pi.csv")

    candidatos = vincular_candidatos_a_parlamentares(candidatos, parlamentares)
    montar_banco(
        candidatos,
        parlamentares.drop(columns=["nome_normalizado"], errors="ignore"),
        despesas, proposicoes, emendas,
        gestao_despesas, gestao_receitas, gestao_contratos, gestao_licitacoes, gestao_convenios,
    )

    print("\nPronto! Banco Postgres (Supabase) atualizado.")


if __name__ == "__main__":
    main()
