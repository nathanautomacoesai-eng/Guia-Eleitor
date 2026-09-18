# Guia Eleitor - Piauí 2026

Sistema de consulta pública: o eleitor digita o nome de um candidato do
Piauí (Governador, Senador, Deputado Federal ou Deputado Estadual, eleições
2026) e o sistema mostra a **proposta de governo oficial** registrada no
TSE e, se o candidato já ocupa mandato, a **ficha de gestão**: para
deputado federal/senador, emendas parlamentares aplicadas, projetos
apresentados e gastos de gabinete; para o Governador titular, despesas,
receitas, maiores contratos, licitações e convênios do Executivo estadual
(ver "Ficha de gestão do Governador" abaixo); para vereadores de Teresina
que também são candidatos, despesas e emendas via o portal da Câmara
Municipal.

Todos os dados vêm de fontes públicas oficiais; nada é obtido varrendo
sites de campanha, justamente para ser confiável e verificável. O banco
de dados é Postgres hospedado no [Supabase](https://supabase.com), pensando
em publicar o site na internet (não só rodar localmente).

## Fontes de dados

| Dado | Fonte | Confiabilidade |
|---|---|---|
| Cadastro de candidatos, proposta de governo (PDF) | [Portal de Dados Abertos do TSE](https://dadosabertos.tse.jus.br/dataset/candidatos-2026) | Alta (documento oficial da candidatura) |
| Deputados federais, gastos de gabinete, projetos | [Dados Abertos da Câmara](https://dadosabertos.camara.leg.br/swagger/api.html) | Alta (cadastro/gastos) · **experimental** (projetos por autor, ver Limitações) |
| Senadores em exercício | [Dados Abertos do Senado](https://www12.senado.leg.br/dados-abertos) | Alta |
| Emendas parlamentares (federal) | [Portal da Transparência (CGU)](https://portaldatransparencia.gov.br/api-de-dados) | **Experimental**, ver Limitações |
| Vereadores de Teresina em exercício, despesas, emendas | [Portal da Transparência da Câmara Municipal de Teresina](https://transparencia.teresina.pi.leg.br) | Alta (site oficial, sem API - coletado via automação de navegador) |
| Governador titular: despesas, receitas, contratos, licitações, convênios | [Portal da Transparência do Piauí](https://transparencia.pi.gov.br) (API em `api.transparencia.pi.gov.br`, não documentada publicamente) | Alta (dado oficial do Executivo estadual) · ver "Ficha de gestão do Governador" |
| Deputados estaduais em exercício (ALEPI) e suas emendas parlamentares estaduais | [Assembleia Legislativa do Piauí](https://sapl.al.pi.leg.br) (API do sistema SAPL) + [Portal da Transparência do Piauí](https://transparencia.pi.gov.br) (`/api/v1/emendas-estaduais/{ano}/`) | Alta (dado oficial), vínculo por nome (ALEPI não expõe CPF) |

## Estrutura do projeto

```
Guia Eleitor/
  scripts/                 # pipeline de coleta de dados (rodar em ordem)
    config.py               # ano, UF, cargos, URLs: mexa aqui p/ mudar o recorte
    01_baixar_tse.py         # candidatos + proposta de governo (PDF)
    02_extrair_propostas.py  # extrai texto dos PDFs
    03_subir_pdfs_storage.py # envia os PDFs pro Supabase Storage
    04_baixar_camara.py      # deputados federais do PI, gastos, projetos
    05_baixar_senado.py      # senadores do PI
    06_baixar_transparencia.py  # emendas parlamentares (federal, CGU)
    07_montar_banco.py       # junta tudo e grava no Postgres (Supabase)
    08_baixar_camara_teresina.py  # vereadores de Teresina: despesas + emendas (automação de navegador, sem API)
    09_diagnostico_transparencia_pi.py  # script de diagnóstico da API do Piauí (não faz parte da pipeline)
    10_baixar_transparencia_pi.py  # ficha de gestão do Governador titular (despesas/receitas/contratos/licitações/convênios)
    11_baixar_alepi.py       # deputados estaduais em exercício (ALEPI) + emendas parlamentares estaduais
    executar_tudo.py         # roda os passos em sequência
    db.py                    # conexão com o Postgres, compartilhada por scripts e backend
    storage.py               # upload de PDFs pro Supabase Storage (API REST)
  data/
    raw/                    # arquivos baixados (PDFs, zips), não versionar
    processed/              # CSVs intermediários (o banco em si agora é no Supabase)
  db/
    schema.sql               # schema das tabelas (recriado do zero a cada coleta)
  backend/
    app.py                  # API FastAPI + serve o site
    busca.py                # lógica de busca/consulta (testável sem subir servidor)
    static/                 # site (HTML/CSS/JS puro, sem build step)
  requirements.txt
  .env.example              # copie para .env: chave da API da Transparência + DATABASE_URL do Supabase
```

## Como rodar

**Importante:** rode os passos abaixo no seu computador, com internet normal.
Este projeto foi montado num ambiente (Claude/Cowork) cujo acesso à rede
estava bloqueado para os domínios do TSE/Câmara/Senado/Transparência, por
isso os scripts de coleta não puderam ser testados contra os dados reais
(só contra dados simulados, veja "O que já foi testado" abaixo).

1. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

2. Configure o `.env` (copie de `.env.example`):
   - `DATABASE_URL`: no seu projeto Supabase, vá em **Project Settings >
     Database > Connection string > URI**, copie e cole aqui, trocando
     `[YOUR-PASSWORD]` pela senha do banco.
   - `PORTAL_TRANSPARENCIA_API_KEY` (opcional, mas recomendado para ter
     emendas parlamentares): cadastre um e-mail gratuito em
     https://www.portaldatransparencia.gov.br/api-de-dados/cadastrar-email
     e cole a chave recebida.
   - `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` (para os PDFs das
     propostas de governo ficarem no Supabase Storage, não só no seu
     computador): em **Project Settings > API**, copie a URL do projeto e
     a chave **service_role** (essa é secreta - nunca cole em código que
     roda no navegador). `SUPABASE_STORAGE_BUCKET` já vem com um nome
     padrão (`propostas-governo`); o script cria o bucket sozinho se ele
     não existir.

3. Rode a coleta de dados:
   ```
   python scripts/executar_tudo.py
   ```
   Isso baixa os dados do TSE (obrigatório), tenta Câmara/Senado/Transparência
   (melhor esforço: se algum falhar, o pipeline segue sem aquele pedaço) e,
   no final, recria as tabelas no Supabase e grava tudo lá
   (`scripts/07_montar_banco.py` roda `db/schema.sql`, que dá `DROP` e `CREATE`
   nas tabelas (rodar a coleta de novo substitui os dados antigos).

4. Suba o site:
   ```
   uvicorn backend.app:app --reload
   ```
   Abra http://127.0.0.1:8000 no navegador.

## O que já foi testado (e o que não)

Como o ambiente onde este projeto foi montado tinha a rede bloqueada, não
consegui baixar dados reais para validar tudo de ponta a ponta. O que eu
consegui testar com dados simulados, e que funcionou:

- Filtro de candidatos por UF/cargo e normalização de colunas do TSE.
- Vínculo entre PDF de proposta de governo e candidato (por token exato,
  sem falso positivo por substring. Um bug real foi pego e corrigido
  nesse teste).
- Extração de texto de PDF e geração do resumo.
- Parser do Senado em JSON e em XML (a API às vezes responde num formato,
  às vezes no outro).
- **O vínculo candidato → parlamentar em exercício** (por CPF parcialmente
  mascarado, com fallback por similaridade de nome); essa é a parte mais
  delicada do projeto e foi testada com vários casos, incluindo o caso de
  CPF batendo, CPF não batendo, e nome parecido mas não idêntico.
- Busca por nome (com acento, parcial, por cargo) e montagem do detalhe do
  candidato (proposta + emendas + projetos), tudo contra um banco de dados
  real gerado nos testes.
- **O schema do Postgres (`db/schema.sql`) foi aplicado e testado contra um
  Postgres 16 de verdade** (não o Supabase em si, que fica fora do alcance
  da rede daqui, mas o mesmo banco por baixo): criei as tabelas, inserí
  linhas com os mesmos tipos de dado que o `07_montar_banco.py` gera
  (booleano, numérico, valores nulos) e rodei as mesmas consultas que o
  `busca.py` faz (filtro por cargo, por `parlamentar_id`, ordenação):
  tudo bateu certo. O que não pude testar foi a conexão em si com o seu
  projeto Supabase (a biblioteca `psycopg2` não pôde ser instalada no
  ambiente onde isso foi escrito). Se a connection string estiver
  correta no `.env`, deve funcionar sem ajuste; se der erro de conexão,
  me manda a mensagem que eu ajudo a resolver.
- **O upload de PDFs pro Supabase Storage (`scripts/storage.py`)** foi
  testado simulando as respostas da API (sucesso, bucket já existente,
  falha de upload, chave faltando). A lógica de montagem de URL/headers
  está correta, mas a chamada de rede real contra o Storage do seu
  projeto não pôde ser testada aqui.

O que **não** pôde ser testado contra a API/serviço real, e é mais
provável de precisar de um ajuste na primeira execução:

- O parâmetro exato para "projetos apresentados por este deputado" na API
  da Câmara (`04_baixar_camara.py`, marcado como EXPERIMENTAL no código).
- O formato exato da consulta de emendas por autor no Portal da
  Transparência (`06_baixar_transparencia.py`, idem).
- O padrão de nomenclatura dos PDFs de proposta de governo dentro do zip
  do TSE (o script tenta casar pelo número do candidato ou pelo SQ_CANDIDATO
  aparecendo no nome do arquivo).
- A conexão real com o Postgres do Supabase (`DATABASE_URL`) e o upload
  real pro Supabase Storage (`SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`).

Se algum desses passos der erro ou vier com resultado vazio quando você
rodar, me manda a mensagem de erro (ou o arquivo salvo em
`data/raw/debug_camara/` ou `data/raw/debug_transparencia/`) que eu ajusto
rapidinho.

## Ficha de gestão do Governador

Governador não tem "emenda parlamentar" (isso é exclusivo de quem
legisla: deputado e senador). O equivalente pra quem ocupa o Executivo é
como o orçamento do estado foi executado, então a ficha do Governador
titular mostra:

- Despesas do Executivo estadual, agregadas por órgão e área (função de
  governo) por ano - não linha a linha, porque o volume bruto passa de
  160 mil lançamentos por ano só de despesa. A soma é feita pelo próprio
  servidor da API (o mesmo endpoint que a aba "Informações Agrupadas" do
  site usa), não pelo script, senão baixar tudo linha a linha levaria
  mais de uma hora.
- Receitas do estado, agregadas por categoria por ano (mesma ideia,
  também via endpoint de agregação do servidor).
- Os contratos de maior valor firmados pelo estado em cada ano do
  mandato (lista limitada, não é a lista completa).
- Licitações abertas pelo estado, agregadas por modalidade por ano.
- Convênios e parcerias firmados pelo estado (lista completa, o volume
  aqui é bem menor).

Fonte: Portal da Transparência do Piauí. O site público
(`transparencia.pi.gov.br`) é só o front-end; os dados de verdade vêm de
uma API separada (`api.transparencia.pi.gov.br`), achada inspecionando o
tráfego de rede do site (não tem documentação pública). O vínculo entre
o candidato a Governador e o titular atual do cargo usa o mesmo
mecanismo de comparação de nome já usado para deputado/senador (ver
`vincular_candidatos_a_parlamentares` em `07_montar_banco.py`); o nome
civil do governador atual (usado pra essa comparação) fica em
`GOVERNADOR_ATUAL_NOME_CIVIL`, em `scripts/config.py` - se um dia trocar
de governador, atualize essa constante.

O formato de todos os endpoints (inclusive o de agregação) foi
confirmado manualmente abrindo o site e inspecionando as chamadas reais
que ele faz, mas o script em si (`10_baixar_transparencia_pi.py`) ainda
não foi rodado de ponta a ponta contra a API real. Rode e me avise se
algum passo vier vazio ou der erro.

## Limitações conhecidas

- **Deputado Estadual (ALEPI):** desde a inclusão de `11_baixar_alepi.py`,
  deputados estaduais em exercício aparecem como "já tem mandato" e
  mostram as emendas parlamentares estaduais deles (fonte: Portal da
  Transparência do Piauí). Diferente da ficha de deputado federal, não
  há dados de despesas de gabinete nem de projetos apresentados: a ALEPI
  não tem uma API pública equivalente à da Câmara dos Deputados para
  isso. A API do SAPL (usada para a lista de deputados) também não expõe
  CPF, então o vínculo candidato-deputado e emenda-deputado é sempre por
  nome (ver "Vínculo por nome" abaixo) - nunca por CPF, diferente do que
  acontece com federais/senadores quando o CPF bate.
- **Vínculo por nome (quando não há CPF batendo):** é marcado no site como
  confiança "média" e mostra um aviso: em nomes muito comuns, pode
  raramente associar à pessoa errada. Vale conferir manualmente em casos
  sensíveis.
- **PDFs escaneados como imagem** (sem camada de texto) não têm o texto
  extraído automaticamente (a biblioteca usada não faz OCR).
- **Neutralidade:** o site só reproduz dados oficiais com a fonte indicada,
  sem ranking, nota ou opinião; importante para não esbarrar em regras do
  TSE sobre propaganda eleitoral.
## Ajustando o recorte

Para incluir outro estado ou outros cargos, edite `scripts/config.py`
(`UF` e `CARGOS_DESEJADOS`) e rode a pipeline de novo.
