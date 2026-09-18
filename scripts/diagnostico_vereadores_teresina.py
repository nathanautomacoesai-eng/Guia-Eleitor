"""
diagnostico_vereadores_teresina.py

Script AD-HOC (nao faz parte do pipeline principal): compara a lista de
vereadores atuais da Camara Municipal de Teresina (coletada manualmente
em https://www.teresina.pi.leg.br/vereadores, pois o portal deles nao tem
API/dados abertos) contra os 348 candidatos do PI ja no nosso banco, para
achar quem provavelmente e' a mesma pessoa.

A comparacao e' por substring (nome de urna dentro do nome completo do
site, ou vice-versa) e por similaridade de texto, porque o nome usado no
site da Camara costuma ser um apelido/nome de urna diferente do nome
civil completo do TSE (ex.: site mostra "Eduardo Draga Alana", TSE/nome
de urna e' "DRAGA ALANA").

Uso:
    python scripts/diagnostico_vereadores_teresina.py
"""
from __future__ import annotations

import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

try:
    from rapidfuzz import fuzz

    def _similaridade(a: str, b: str) -> float:
        return fuzz.token_sort_ratio(a, b)
except ImportError:
    def _similaridade(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100

# Coletado manualmente em https://www.teresina.pi.leg.br/vereadores
# (Legislatura no 20) - o portal da Camara de Teresina nao tem API/CSV,
# entao nao da pra automatizar essa coleta como fizemos com Camara Federal
# e Senado. Atualize esta lista manualmente se a legislatura mudar.
VEREADORES_TERESINA_ATUAIS = [
    "Ana Fidelis", "Bruno Vilarinho", "Carlos Ribeiro", "Carpejanne Gomes",
    "Daniel Carvalho", "Delegado James Guerra", "Deolindo Moura",
    "Dr Leonardo Eulalio", "Dudu", "Eduardo Draga Alana", "Elzuila Calisto",
    "Enzo Samuel", "Fernanda Gomes", "Fernando Lima", "Geraldin",
    "Inacio Carvalho", "Joao Pereira", "Joaquim do Arroz", "Juca Alves",
    "Leondidas Junior", "Lucy Soares", "Pedro Alcantara", "Petrus Evelyn",
    "Samantha Cavalca", "Teresinha Medeiros", "Valdemir Virgino",
    "Venancio", "Ze Filho",
]

VEREADORES_TERESINA_LICENCIADOS = [
    "Aluisio Sampaio", "Gustavo de Carvalho", "Ismael Silva", "Luis Andre",
    "Roncallin", "Samuel Alencar", "Tatiana Medeiros", "Ze Neto",
]


def _normalizar(txt: str) -> str:
    txt = (txt or "").upper().strip()
    txt = "".join(c for c in unicodedata.normalize("NFKD", txt) if not unicodedata.combining(c))
    return " ".join(txt.split())


def _bate(nome_vereador: str, nome_urna: str, nome_civil: str) -> tuple[bool, float, str]:
    v = _normalizar(nome_vereador)
    urna = _normalizar(nome_urna)
    civil = _normalizar(nome_civil)

    for candidato_nome, origem in ((urna, "nome_urna"), (civil, "nome_civil")):
        if not candidato_nome:
            continue
        if candidato_nome in v or v in candidato_nome:
            return True, 100.0, f"substring ({origem})"

    melhor_score = max(_similaridade(v, urna), _similaridade(v, civil))
    return melhor_score >= 70, melhor_score, "similaridade"


def main() -> None:
    candidatos = pd.read_csv(config.PROCESSED_DIR / "candidatos_pi.csv", dtype=str).fillna("")

    for titulo, lista in (
        ("VEREADORES ATUAIS", VEREADORES_TERESINA_ATUAIS),
        ("VEREADORES LICENCIADOS/SUPLENTES EM EXERCICIO", VEREADORES_TERESINA_LICENCIADOS),
    ):
        print("\n" + "=" * 78)
        print(f"{titulo} DE TERESINA x CANDIDATOS DO BANCO")
        print("=" * 78)
        algum_match = False
        for nome_vereador in lista:
            melhores = []
            for _, candidato in candidatos.iterrows():
                bateu, score, motivo = _bate(nome_vereador, candidato.get("nome_urna", ""), candidato.get("nome_civil", ""))
                if bateu:
                    melhores.append((score, candidato.get("nome_urna", ""), candidato.get("cargo", ""), motivo))
            if melhores:
                algum_match = True
                melhores.sort(reverse=True)
                for score, nome_urna, cargo, motivo in melhores:
                    print(f"  {nome_vereador!r:35s} -> candidato {nome_urna!r} ({cargo}) [{motivo}, score={score:.0f}]")
        if not algum_match:
            print("  (nenhum candidato do banco bateu com essa lista)")


if __name__ == "__main__":
    main()
