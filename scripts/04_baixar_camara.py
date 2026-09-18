"""
04_baixar_camara.py

Baixa da API de Dados Abertos da Camara dos Deputados:
  - os deputados federais em exercicio pelo Piaui;
  - despesas de gabinete (cota parlamentar) recentes de cada um;
  - proposicoes de autoria de cada um (BLOCO MARCADO COMO EXPERIMENTAL,
    veja aviso abaixo).

Gera:
  data/processed/parlamentares_camara_pi.csv
  data/processed/despesas_camara_pi.csv
  data/processed/proposicoes_camara_pi.csv

JA VALIDADO CONTRA A API REAL (17/set/2026): listagem de deputados,
proposicoes por autor (parametro idDeputadoAutor) e despesas por
legislatura (parametro idLegislatura, com paginacao) - os tres já
retornaram dados reais e corretos pros deputados federais do PI. Se algo
mudar no futuro (a API pode alterar parametros sem aviso), rode com
--debug para salvar a resposta bruta em data/raw/debug_camara/ e me manda
esse arquivo.

Uso:
    python scripts/04_baixar_camara.py [--debug]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

DEBUG_DIR = config.RAW_DIR / "debug_camara"


def _get_json(path: str, params: dict | None = None) -> dict:
    url = f"{config.CAMARA_API_BASE}{path}"
    resp = requests.get(
        url,
        params=params or {},
        headers={"Accept": "application/json", "User-Agent": config.USER_AGENT},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def listar_deputados_pi() -> list[dict]:
    print(f"Buscando deputados federais em exercicio por {config.UF}...")
    dados = _get_json("/deputados", {"siglaUf": config.UF, "itens": 100})
    deputados = dados.get("dados", [])
    print(f"Encontrados: {len(deputados)}")
    return deputados


def detalhar_deputado(id_deputado: int) -> dict:
    dados = _get_json(f"/deputados/{id_deputado}")
    return dados.get("dados", {})


def despesas_deputado(id_deputado: int, id_legislatura: str) -> list[dict]:
    """Busca TODAS as despesas do deputado na legislatura atual, paginando.

    CONFIRMADO CONTRA A API REAL (nao e' mais so um palpite): o filtro que
    funciona e' 'idLegislatura', nao 'ano' sozinho - passar so 'ano' faz a
    API devolver "dados": [] mesmo para deputados com despesas reais (isso
    foi testado e reproduzido tanto pelo usuario quanto por mim,
    inclusive contra um ID de deputado usado num tutorial de terceiros).
    Cada item retornado ja traz os campos 'ano' e 'mes' proprios, entao nao
    precisamos mais pedir ano por ano.
    """
    despesas: list[dict] = []
    pagina = 1
    while True:
        try:
            dados = _get_json(
                f"/deputados/{id_deputado}/despesas",
                {
                    "idLegislatura": id_legislatura,
                    "itens": 100,
                    "pagina": pagina,
                    "ordem": "ASC",
                    "ordenarPor": "ano",
                },
            )
        except requests.HTTPError as exc:
            print(f"  [AVISO] falha ao buscar despesas do deputado {id_deputado} (pagina {pagina}): {exc}")
            break

        pagina_dados = dados.get("dados", [])
        if not pagina_dados:
            break
        despesas.extend(pagina_dados)
        pagina += 1
        if pagina > 50:  # protecao contra loop infinito, bem acima do necessario
            break
        time.sleep(0.2)

    return despesas


def proposicoes_deputado_experimental(id_deputado: int, debug: bool) -> list[dict]:
    """EXPERIMENTAL: o parametro certo para filtrar proposicoes por autor
    pode variar. Tentamos 'idDeputadoAutor'; se a API devolver algo
    inesperado, salvamos a resposta bruta para investigar."""
    try:
        dados = _get_json(
            "/proposicoes",
            {
                "idDeputadoAutor": id_deputado,
                "itens": 50,
                "ordem": "DESC",
                "ordenarPor": "id",
            },
        )
        return dados.get("dados", [])
    except requests.HTTPError as exc:
        print(f"  [AVISO] falha ao buscar proposicoes do deputado {id_deputado}: {exc}")
        if debug:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            (DEBUG_DIR / f"erro_proposicoes_{id_deputado}.txt").write_text(str(exc))
        return []


def main() -> None:
    debug = "--debug" in sys.argv

    deputados_base = listar_deputados_pi()

    linhas_parlamentares = []
    linhas_despesas = []
    linhas_proposicoes = []

    for dep in deputados_base:
        id_dep = dep["id"]
        print(f"\nProcessando: {dep.get('nome')} (id={id_dep})")

        detalhe = detalhar_deputado(id_dep)
        time.sleep(0.3)  # gentileza com a API publica

        linhas_parlamentares.append({
            "id": str(id_dep),
            "origem": "camara",
            "cpf": detalhe.get("cpf", ""),
            "nome_civil": detalhe.get("nomeCivil", dep.get("nome", "")),
            "nome_eleitoral": dep.get("nome", ""),
            "cargo_atual": "DEPUTADO FEDERAL",
            "uf": config.UF,
            "partido": dep.get("siglaPartido", ""),
            "email": detalhe.get("ultimoStatus", {}).get("gabinete", {}).get("email", ""),
            "foto_url": dep.get("urlFoto", ""),
        })

        id_legislatura = detalhe.get("ultimoStatus", {}).get("idLegislatura", "")
        for despesa in despesas_deputado(id_dep, id_legislatura):
            linhas_despesas.append({
                "parlamentar_id": str(id_dep),
                "ano": despesa.get("ano"),
                "mes": despesa.get("mes"),
                "tipo_despesa": despesa.get("tipoDespesa"),
                "valor_liquido": despesa.get("valorLiquido"),
                "fornecedor": despesa.get("nomeFornecedor"),
            })

        for prop in proposicoes_deputado_experimental(id_dep, debug):
            linhas_proposicoes.append({
                "parlamentar_id": str(id_dep),
                "id_proposicao": prop.get("id"),
                "tipo": prop.get("siglaTipo"),
                "numero": prop.get("numero"),
                "ano": prop.get("ano"),
                "ementa": prop.get("ementa"),
            })
        time.sleep(0.3)

    pd.DataFrame(linhas_parlamentares).to_csv(
        config.PROCESSED_DIR / "parlamentares_camara_pi.csv", index=False
    )
    pd.DataFrame(linhas_despesas).to_csv(
        config.PROCESSED_DIR / "despesas_camara_pi.csv", index=False
    )
    pd.DataFrame(linhas_proposicoes).to_csv(
        config.PROCESSED_DIR / "proposicoes_camara_pi.csv", index=False
    )

    print("\nPronto!")
    print(f"Deputados: {len(linhas_parlamentares)}")
    print(f"Linhas de despesas: {len(linhas_despesas)}")
    print(f"Proposicoes: {len(linhas_proposicoes)}")
    if not linhas_proposicoes:
        print(
            "\nNenhuma proposicao encontrada - o parametro 'idDeputadoAutor' pode "
            "precisar de ajuste. Rode com --debug e verifique "
            "https://dadosabertos.camara.leg.br/swagger/api.html para o nome "
            "correto do parametro, ou me manda o erro que eu ajusto."
        )


if __name__ == "__main__":
    main()
