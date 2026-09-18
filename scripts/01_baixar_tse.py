"""
01_baixar_tse.py

Baixa do Portal de Dados Abertos do TSE:
  - o cadastro de candidatos 2026 (nacional, filtramos para PI depois);
  - os PDFs de "proposta de governo" enviados pelos candidatos do PI.

Gera:
  data/processed/candidatos_pi.csv
  data/raw/propostas_pdf/*.pdf

IMPORTANTE: este script baixa arquivos grandes da internet. Rode-o no seu
computador, fora de ambientes com rede restrita (o ambiente do Cowork/Claude
bloqueou o acesso a esses dominios quando este projeto foi criado).

Uso:
    python scripts/01_baixar_tse.py
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402


def _get(url: str) -> bytes:
    print(f"Baixando: {url}")
    resp = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=120)
    resp.raise_for_status()
    return resp.content


def baixar_candidatos() -> pd.DataFrame:
    """Baixa o zip nacional de candidatos e retorna um DataFrame ja filtrado
    para a UF e os cargos configurados em scripts/config.py."""
    zip_bytes = _get(config.TSE_CANDIDATOS_ZIP_URL)
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))

    # O zip do TSE normalmente traz um CSV por UF, nomeado tipo
    # "consulta_cand_2026_PI.csv". Procuramos o arquivo certo dinamicamente
    # para nao depender de um nome exato.
    candidatos_uf = [
        n for n in zf.namelist()
        if n.lower().endswith(".csv") and config.UF.lower() in n.lower()
    ]
    if not candidatos_uf:
        # Fallback: as vezes vem um unico CSV nacional grande.
        candidatos_uf = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        print(
            "AVISO: nao achei um CSV especifico para "
            f"{config.UF} dentro do zip; usando o(s) arquivo(s): {candidatos_uf}"
        )

    dfs = []
    for nome in candidatos_uf:
        with zf.open(nome) as f:
            # TSE costuma usar ';' como separador e latin-1 como encoding.
            df = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str)
        dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)

    # Nomes de coluna podem variar um pouco de eleicao para eleicao; tentamos
    # localizar as colunas certas por um conjunto de nomes possiveis.
    def achar_coluna(possiveis: list[str]) -> str | None:
        for c in possiveis:
            if c in df.columns:
                return c
        return None

    col_uf = achar_coluna(["SG_UF", "SIGLA_UF"])
    col_cargo = achar_coluna(["DS_CARGO", "DESCRICAO_CARGO"])
    col_ano = achar_coluna(["ANO_ELEICAO"])

    if col_uf is None or col_cargo is None:
        print("ERRO: nao encontrei as colunas de UF/cargo esperadas.")
        print("Colunas disponiveis no CSV:", list(df.columns))
        raise SystemExit(1)

    if col_uf:
        df = df[df[col_uf].str.upper() == config.UF]
    if col_ano:
        df = df[df[col_ano] == str(config.ANO_ELEICAO)]
    df = df[df[col_cargo].str.upper().isin(config.CARGOS_DESEJADOS)]

    print(f"Candidatos encontrados para {config.UF} nos cargos desejados: {len(df)}")
    return df


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia/seleciona as colunas relevantes para um esquema estavel que
    o resto do projeto (montagem do banco, backend) vai consumir."""

    mapa_colunas = {
        "SQ_CANDIDATO": "sq_candidato",
        "NR_CANDIDATO": "numero",
        "NM_CANDIDATO": "nome_civil",
        "NM_URNA_CANDIDATO": "nome_urna",
        "NM_SOCIAL_CANDIDATO": "nome_social",
        "DS_CARGO": "cargo",
        "SG_PARTIDO": "partido_sigla",
        "NM_PARTIDO": "partido_nome",
        "DS_COMPOSICAO_COLIGACAO": "coligacao",
        "NM_COLIGACAO": "coligacao_nome",
        "DS_SIT_TOT_TURNO": "situacao_totalizacao",
        "DS_SITUACAO_CANDIDATURA": "situacao_candidatura",
        "NR_CPF_CANDIDATO": "cpf",
        "NM_EMAIL": "email",
        "SG_UF": "uf",
        "ANO_ELEICAO": "ano_eleicao",
    }
    colunas_presentes = {k: v for k, v in mapa_colunas.items() if k in df.columns}
    faltando = [k for k in mapa_colunas if k not in df.columns]
    if faltando:
        print(
            "AVISO: as colunas a seguir nao existem neste CSV do TSE e ficarao "
            f"vazias no resultado final: {faltando}"
        )

    out = df[list(colunas_presentes.keys())].rename(columns=colunas_presentes)
    for _, novo_nome in mapa_colunas.items():
        if novo_nome not in out.columns:
            out[novo_nome] = ""

    out = out.drop_duplicates(subset=["sq_candidato"])
    return out


def baixar_propostas_de_governo() -> dict[str, Path]:
    """Baixa o zip de propostas de governo do PI e extrai os PDFs.

    Retorna um dicionario {nome_do_arquivo_sem_extensao: caminho_do_pdf} para
    o script de montagem do banco tentar casar cada PDF com um candidato.
    """
    try:
        zip_bytes = _get(config.TSE_PROPOSTA_GOVERNO_ZIP_URL)
    except requests.HTTPError as exc:
        print(f"Nao consegui baixar as propostas de governo: {exc}")
        return {}

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    arquivos = {}
    for nome in zf.namelist():
        if not nome.lower().endswith(".pdf"):
            continue
        destino = config.PROPOSTAS_PDF_DIR / Path(nome).name
        destino.write_bytes(zf.read(nome))
        arquivos[Path(nome).stem] = destino
    print(f"Propostas de governo (PDF) salvas: {len(arquivos)} em {config.PROPOSTAS_PDF_DIR}")
    return arquivos


def _tokens_do_nome_arquivo(nome_arquivo: str) -> set[str]:
    """Quebra o nome do arquivo em tokens alfanumericos, ex.:
    'proposta_45_123456789012345' -> {'proposta', '45', '123456789012345'}.
    Usamos tokens exatos (nao substring) para evitar falso positivo, como um
    numero curto de candidato (ex.: '1234') batendo dentro de um
    SQ_CANDIDATO longo que por acaso comeca com os mesmos digitos.
    """
    return set(re.split(r"[^A-Za-z0-9]+", nome_arquivo)) - {""}


def vincular_pdf_ao_candidato(df: pd.DataFrame, pdfs: dict[str, Path]) -> pd.DataFrame:
    """Tenta casar cada PDF de proposta de governo com uma linha de
    candidato.

    Confirmado contra dados reais do TSE (eleicoes 2026): o nome do
    arquivo vem no formato "{ANO}{UF}{SQ_CANDIDATO}_{SEQ}.pdf", GRUDADO
    sem separador entre ano, UF e SQ_CANDIDATO (ex.: "2026PI180002532987_01.pdf").
    Por isso o casamento principal e' por SUBSTRING do SQ_CANDIDATO no nome
    do arquivo - seguro porque SQ_CANDIDATO tem sempre o mesmo tamanho (12
    digitos) e e' um identificador de alta entropia, sem risco pratico de
    colisao. So usamos substring para chaves com pelo menos 8 caracteres,
    como protecao extra.

    Como fallback (caso um dia o padrao de nomenclatura mude e volte a ter
    separador), tentamos tambem o NUMERO do candidato por TOKEN exato
    (nunca substring - um numero curto colidindo "por acaso" dentro de um
    SQ_CANDIDATO longo foi um bug real, ja visto e corrigido antes).
    """
    df = df.copy()
    df["proposta_pdf_arquivo"] = ""

    if not pdfs:
        return df

    tokens_por_arquivo = {
        nome_arquivo: _tokens_do_nome_arquivo(nome_arquivo)
        for nome_arquivo in pdfs
    }

    for idx, row in df.iterrows():
        sq_candidato = row.get("sq_candidato", "")
        numero = row.get("numero", "")
        encontrado = ""

        if sq_candidato and len(sq_candidato) >= 8:
            for nome_arquivo in pdfs:
                if sq_candidato in nome_arquivo:
                    encontrado = nome_arquivo
                    break

        if not encontrado and numero:
            for nome_arquivo, tokens in tokens_por_arquivo.items():
                if numero in tokens:
                    encontrado = nome_arquivo
                    break

        if encontrado:
            df.at[idx, "proposta_pdf_arquivo"] = pdfs[encontrado].name

    casados = (df["proposta_pdf_arquivo"] != "").sum()
    print(f"PDFs de proposta vinculados automaticamente a candidatos: {casados}/{len(df)}")
    if casados < len(pdfs):
        print(
            "Alguns PDFs podem nao ter sido vinculados. Se a heuristica pelo "
            "nome do arquivo falhar, abra um PDF de exemplo em "
            "data/raw/propostas_pdf/ para ver o padrao de nomenclatura e "
            "ajuste a funcao vincular_pdf_ao_candidato()."
        )
    return df


def main() -> None:
    df = baixar_candidatos()
    df = normalizar(df)
    pdfs = baixar_propostas_de_governo()
    df = vincular_pdf_ao_candidato(df, pdfs)

    destino = config.PROCESSED_DIR / "candidatos_pi.csv"
    df.to_csv(destino, index=False)
    print(f"\nPronto! Dados salvos em: {destino}")
    print(f"Total de candidatos: {len(df)}")
    print(df["cargo"].value_counts())


if __name__ == "__main__":
    main()
