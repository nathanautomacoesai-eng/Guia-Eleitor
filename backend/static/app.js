// Guia Eleitor - frontend simples, sem frameworks/bibliotecas externas.

const campoBusca = document.getElementById("campo-busca");
const filtroCargo = document.getElementById("filtro-cargo");
const areaMensagem = document.getElementById("mensagem");
const areaResultados = document.getElementById("resultados");
const areaDetalhe = document.getElementById("detalhe");

let temporizadorBusca = null;

function mostrarMensagem(texto) {
  areaMensagem.textContent = texto;
  areaMensagem.hidden = !texto;
}

function formatarMoeda(valor) {
  const numero = Number(valor);
  if (Number.isNaN(numero)) return valor || "-";
  return numero.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function cargoLegivel(cargo) {
  const mapa = {
    "GOVERNADOR": "Governador(a)",
    "SENADOR": "Senador(a)",
    "DEPUTADO FEDERAL": "Deputado(a) Federal",
    "DEPUTADO ESTADUAL": "Deputado(a) Estadual",
  };
  return mapa[cargo] || cargo || "-";
}

// O TSE usa alguns codigos de "placeholder" em campos que so fazem sentido
// depois da eleicao acontecer (ou antes do fim do periodo de registro de
// candidaturas) - por exemplo "#NE" (nao disponivel) ou "#NULO#". Como
// ainda estamos no periodo pre-eleitoral, isso aparece com frequencia e
// nao deve ser mostrado como se fosse um valor real.
const CODIGOS_TSE_NAO_DISPONIVEL = new Set(["#NE", "#NULO#", "#NI", ""]);

function situacaoLegivel(situacao) {
  if (!situacao || CODIGOS_TSE_NAO_DISPONIVEL.has(situacao.trim().toUpperCase())) {
    return null;
  }
  return situacao;
}

async function buscar() {
  const termo = campoBusca.value.trim();
  const cargo = filtroCargo.value;
  areaDetalhe.hidden = true;
  areaResultados.hidden = false;
  areaResultados.innerHTML = "";

  if (termo.length < 2) {
    mostrarMensagem("");
    return;
  }

  mostrarMensagem("Buscando...");

  const params = new URLSearchParams({ q: termo });
  if (cargo) params.set("cargo", cargo);

  try {
    const resp = await fetch(`/api/candidatos/busca?${params.toString()}`);
    if (resp.status === 503) {
      mostrarMensagem(
        "O banco de dados ainda não foi gerado. Rode os scripts de coleta " +
        "(veja o README do projeto) antes de usar a busca."
      );
      return;
    }
    if (!resp.ok) {
      mostrarMensagem("Não foi possível buscar agora. Tente novamente em instantes.");
      return;
    }
    const dados = await resp.json();
    mostrarMensagem("");
    renderizarResultados(dados.resultados || []);
  } catch (erro) {
    mostrarMensagem("Erro de conexão com o servidor local.");
  }
}

function renderizarResultados(resultados) {
  areaResultados.innerHTML = "";
  if (resultados.length === 0) {
    mostrarMensagem("Nenhum candidato encontrado com esse nome no recorte do Piauí.");
    return;
  }

  for (const candidato of resultados) {
    const cartao = document.createElement("div");
    cartao.className = "cartao-candidato";
    cartao.innerHTML = `
      <div class="info-principal">
        <strong>${candidato.nome_urna || candidato.nome_civil}</strong><br />
        <span class="meta">
          ${cargoLegivel(candidato.cargo)} · ${candidato.partido_sigla || "-"} ·
          nº ${candidato.numero || "-"}
        </span>
      </div>
      ${candidato.incumbente === "1"
        ? '<span class="selo-incumbente">Já ocupa mandato</span>'
        : ""}
    `;
    cartao.addEventListener("click", () => abrirDetalhe(candidato.sq_candidato));
    areaResultados.appendChild(cartao);
  }
}

async function abrirDetalhe(sqCandidato) {
  areaResultados.hidden = true;
  areaDetalhe.hidden = false;
  areaDetalhe.innerHTML = "<p>Carregando...</p>";
  areaDetalhe.scrollIntoView({ behavior: "smooth" });

  try {
    const resp = await fetch(`/api/candidatos/${encodeURIComponent(sqCandidato)}`);
    if (!resp.ok) {
      areaDetalhe.innerHTML = "<p>Não foi possível carregar este candidato.</p>";
      return;
    }
    const candidato = await resp.json();
    renderizarDetalhe(candidato);
  } catch (erro) {
    areaDetalhe.innerHTML = "<p>Erro de conexão com o servidor local.</p>";
  }
}

function calcularIdade(dataNascimentoIso) {
  if (!dataNascimentoIso) return null;
  const nascimento = new Date(dataNascimentoIso);
  if (isNaN(nascimento.getTime())) return null;
  const hoje = new Date();
  let idade = hoje.getFullYear() - nascimento.getFullYear();
  const aindaNaoFezAniversario =
    hoje.getMonth() < nascimento.getMonth() ||
    (hoje.getMonth() === nascimento.getMonth() && hoje.getDate() < nascimento.getDate());
  if (aindaNaoFezAniversario) idade -= 1;
  return idade;
}

function renderizarDetalhesTse(c) {
  // So aparece se o script 12_baixar_tse_detalhes.py ja rodou pra esse
  // candidato (senao esses campos nem existem no objeto retornado pela API).
  if (!c.tse_divulga_url) return "";

  const idade = calcularIdade(c.data_nascimento);
  const linhasPessoais = [
    c.grau_instrucao ? `<li><strong>Grau de instrução:</strong> ${c.grau_instrucao}</li>` : "",
    c.ocupacao ? `<li><strong>Ocupação declarada:</strong> ${c.ocupacao}</li>` : "",
    c.estado_civil ? `<li><strong>Estado civil:</strong> ${c.estado_civil}</li>` : "",
    idade !== null ? `<li><strong>Idade:</strong> ${idade} anos</li>` : "",
    c.bens_total ? `<li><strong>Bens declarados:</strong> ${formatarMoeda(c.bens_total)}</li>` : "",
  ].filter(Boolean).join("");

  const temPrestacaoContas = c.prestacao_total_recebido || c.prestacao_total_despesas_pagas;
  const blocoPrestacaoContas = temPrestacaoContas
    ? `
      <h3>Prestação de contas de campanha</h3>
      <ul>
        ${c.prestacao_total_recebido ? `<li><strong>Total arrecadado:</strong> ${formatarMoeda(c.prestacao_total_recebido)}</li>` : ""}
        ${c.prestacao_total_despesas_contratadas ? `<li><strong>Total de despesas contratadas:</strong> ${formatarMoeda(c.prestacao_total_despesas_contratadas)}</li>` : ""}
        ${c.prestacao_total_despesas_pagas ? `<li><strong>Total de despesas pagas:</strong> ${formatarMoeda(c.prestacao_total_despesas_pagas)}</li>` : ""}
      </ul>
      ${c.prestacao_data_atualizacao ? `<p class="fonte">Dados de contas atualizados pelo TSE em ${c.prestacao_data_atualizacao}.</p>` : ""}
    `
    : `<p class="meta">Prestação de contas de campanha ainda não entregue ao TSE (ou ainda não processada).</p>`;

  // O candidato preenche esse campo livremente no formulario do TSE -
  // as vezes vem uma URL de verdade, as vezes um texto solto tipo
  // "INSTAGRAM, YOUTUBE E X: @FULANO" (caso real ja visto). So' vira
  // link clicavel quando parece mesmo uma URL (sem espaco, com um "."
  // depois do host); senao mostra so' como texto.
  const sites = (c.sites_tse || "").split("|").map((s) => s.trim()).filter(Boolean);
  const pareceUrl = (s) => /^https?:\/\/[^\s]+\.[^\s]+$/i.test(s);
  const blocoSites = sites.length
    ? `
      <h3>Sites e redes sociais informados ao TSE</h3>
      <p class="meta">${sites.map((s) =>
        pareceUrl(s)
          ? `<a href="${s}" target="_blank" rel="noopener">${escaparHtml(s)}</a>`
          : escaparHtml(s)
      ).join("<br>")}</p>
    `
    : "";

  return `
    <div class="bloco">
      <h2>Dados do candidato no TSE</h2>
      ${linhasPessoais ? `<ul>${linhasPessoais}</ul>` : "<p class='meta'>Sem dados pessoais complementares disponíveis.</p>"}
      ${blocoPrestacaoContas}
      ${blocoSites}
      <p><a class="link-pdf" href="${c.tse_divulga_url}" target="_blank" rel="noopener">Ver todos os dados oficiais no TSE &rarr;</a></p>
      <p class="fonte">Fonte: TSE - Divulgação de Candidaturas e Contas Eleitorais.</p>
    </div>
  `;
}

function renderizarDetalhe(c) {
  const partes = [];

  partes.push(`
    <button class="botao-voltar" onclick="voltarParaBusca();">
      &larr; Voltar para a busca
    </button>
    <div class="bloco">
      <h2>${c.nome_urna || c.nome_civil}</h2>
      <p class="meta">
        ${cargoLegivel(c.cargo)} · ${c.partido_sigla || "-"} (${c.partido_nome || ""}) ·
        nº ${c.numero || "-"} ${c.coligacao_nome ? "· coligação: " + c.coligacao_nome : ""}
      </p>
      ${situacaoLegivel(c.situacao_candidatura) ? `<p class="meta">Situação da candidatura: ${situacaoLegivel(c.situacao_candidatura)}</p>` : ""}
    </div>
  `);

  // Proposta de governo
  const temProposta = c.proposta_pdf_url || c.proposta_pdf_arquivo;
  partes.push(`
    <div class="bloco">
      <h2>Proposta de governo (documento oficial no TSE)</h2>
      ${temProposta
        ? `<p><a class="link-pdf" href="${c.proposta_pdf_url || ("/api/propostas/" + encodeURIComponent(c.proposta_pdf_arquivo))}" target="_blank" rel="noopener">
             Abrir PDF da proposta de governo &rarr;
           </a></p>`
        : `<p>Nenhum PDF de proposta de governo foi localizado para este candidato.
           ${c.cargo !== "GOVERNADOR" ? "O TSE só exige esse documento para candidatos a Governador." : ""}</p>`}
      ${c.proposta_resumo
        ? `<h3>Trecho inicial</h3><div class="texto-proposta">${escaparHtml(c.proposta_resumo)}</div>`
        : ""}
      <p class="fonte">Fonte: Portal de Dados Abertos do TSE (candidatura ${c.ano_eleicao || "2026"}).</p>
      ${c.link_externo_url
        ? `<p><a class="link-pdf" href="${c.link_externo_url}" target="_blank" rel="noopener">
             ${c.link_externo_rotulo || "Site do candidato"} &rarr;
           </a></p>
           <p class="fonte">⚠️ Link informado manualmente pela equipe do projeto, não é um documento da candidatura no TSE.</p>`
        : ""}
    </div>
  `);

  partes.push(renderizarDetalhesTse(c));

  // Ficha de gestor (se for incumbente)
  if (c.incumbente === "1") {
    const avisoConfianca = (c.vinculo_confianca || "").startsWith("media")
      ? `<p class="fonte">⚠️ Este vínculo foi feito por semelhança de nome (${c.vinculo_confianca}),
         não por CPF, o que pode, em casos raros, associar à pessoa errada. Confira o nome completo.</p>`
      : "";

    const ehGovernadorAtual = c.cargo === "GOVERNADOR" && c.parlamentar_origem === "executivo_estadual";
    const ehDeputadoEstadualAtual = c.cargo === "DEPUTADO ESTADUAL" && c.parlamentar_origem === "alepi";

    let tituloFicha = "Ficha como gestor(a) / parlamentar em exercício";
    let conteudoFicha = [
      renderizarEmendas(c.emendas || []),
      renderizarProposicoes(c.proposicoes || []),
      renderizarDespesas(c.despesas || []),
    ].join("\n");

    if (ehGovernadorAtual) {
      tituloFicha = "Ficha de gestão (Governador titular)";
      conteudoFicha = [
        renderizarGestaoDespesas(c.gestao_despesas || []),
        renderizarGestaoReceitas(c.gestao_receitas || []),
        renderizarGestaoContratos(c.gestao_contratos || []),
        renderizarGestaoLicitacoes(c.gestao_licitacoes || []),
        renderizarGestaoConvenios(c.gestao_convenios || []),
      ].join("\n");
    } else if (ehDeputadoEstadualAtual) {
      tituloFicha = "Ficha como deputado(a) estadual em exercício";
      conteudoFicha = renderizarEmendasEstaduais(c.emendas_estaduais || []);
    }

    partes.push(`
      <div class="bloco">
        <h2>${tituloFicha}</h2>
        ${avisoConfianca}
        ${conteudoFicha}
      </div>
    `);
  }

  areaDetalhe.innerHTML = partes.join("\n");
}

function renderizarEmendas(emendas) {
  if (emendas.length === 0) {
    return "<h3>Emendas parlamentares</h3><p class='meta'>Nenhuma emenda encontrada no período consultado.</p>";
  }
  const linhas = emendas.map((e) => `
    <tr>
      <td>${e.ano || "-"}</td>
      <td>${e.numero_emenda || "-"}</td>
      <td>${e.municipio_beneficiario || "-"}</td>
      <td>${formatarMoeda(e.valor_empenhado)}</td>
      <td>${formatarMoeda(e.valor_pago)}</td>
    </tr>
  `).join("");
  return `
    <h3>Emendas parlamentares</h3>
    <table class="tabela-simples">
      <thead><tr><th>Ano</th><th>Nº</th><th>Município</th><th>Empenhado</th><th>Pago</th></tr></thead>
      <tbody>${linhas}</tbody>
    </table>
    <p class="fonte">Fonte: Portal da Transparência (CGU).</p>
  `;
}

function renderizarProposicoes(proposicoes) {
  if (proposicoes.length === 0) {
    return "<h3>Projetos apresentados</h3><p class='meta'>Nenhum projeto encontrado.</p>";
  }
  const itens = proposicoes.slice(0, 15).map((p) => `
    <li><strong>${p.tipo || ""} ${p.numero || ""}/${p.ano || ""}:</strong> ${p.ementa || "sem ementa"}</li>
  `).join("");
  return `
    <h3>Projetos apresentados (Câmara dos Deputados)</h3>
    <ul>${itens}</ul>
    <p class="fonte">Fonte: Dados Abertos da Câmara dos Deputados.</p>
  `;
}

function renderizarDespesas(despesas) {
  if (despesas.length === 0) return "";
  const totalPorAno = {};
  for (const d of despesas) {
    const valor = Number(d.valor_liquido) || 0;
    totalPorAno[d.ano] = (totalPorAno[d.ano] || 0) + valor;
  }
  const linhas = Object.entries(totalPorAno).map(
    ([ano, total]) => `<tr><td>${ano}</td><td>${formatarMoeda(total)}</td></tr>`
  ).join("");
  return `
    <h3>Gastos de gabinete (cota parlamentar) por ano</h3>
    <table class="tabela-simples">
      <thead><tr><th>Ano</th><th>Total gasto</th></tr></thead>
      <tbody>${linhas}</tbody>
    </table>
    <p class="fonte">Fonte: Dados Abertos da Câmara dos Deputados.</p>
  `;
}

function truncar(texto, tamanho) {
  if (!texto) return "";
  const t = String(texto);
  return t.length > tamanho ? t.slice(0, tamanho).trim() + "..." : t;
}

function renderizarGestaoDespesas(linhas) {
  if (linhas.length === 0) return "";
  const corpo = linhas.map((d) => `
    <tr>
      <td>${d.ano || "-"}</td>
      <td>${d.orgao_titulo || "-"}</td>
      <td>${d.funcao_titulo || "-"}</td>
      <td>${formatarMoeda(d.total_empenhado)}</td>
      <td>${formatarMoeda(d.total_liquidado)}</td>
      <td>${formatarMoeda(d.total_pago)}</td>
    </tr>
  `).join("");
  return `
    <h3>Despesas do Executivo estadual (por órgão e área)</h3>
    <p class="meta">Valores agregados por órgão e função de governo, somados a partir de cada empenho registrado no ano.</p>
    <table class="tabela-simples">
      <thead><tr><th>Ano</th><th>Órgão</th><th>Área</th><th>Empenhado</th><th>Liquidado</th><th>Pago</th></tr></thead>
      <tbody>${corpo}</tbody>
    </table>
    <p class="fonte">Fonte: Portal da Transparência do Piauí.</p>
  `;
}

function renderizarGestaoReceitas(linhas) {
  if (linhas.length === 0) return "";
  const corpo = linhas.map((r) => `
    <tr>
      <td>${r.ano || "-"}</td>
      <td>${r.categoria_titulo || "-"}</td>
      <td>${formatarMoeda(r.total_previsto)}</td>
      <td>${formatarMoeda(r.total_realizado)}</td>
    </tr>
  `).join("");
  return `
    <h3>Receitas do estado (por categoria)</h3>
    <table class="tabela-simples">
      <thead><tr><th>Ano</th><th>Categoria</th><th>Previsto (atualizado)</th><th>Realizado</th></tr></thead>
      <tbody>${corpo}</tbody>
    </table>
    <p class="fonte">Fonte: Portal da Transparência do Piauí.</p>
  `;
}

function renderizarGestaoContratos(linhas) {
  if (linhas.length === 0) return "";
  const corpo = linhas.map((ct) => `
    <tr>
      <td>${ct.ano || "-"}</td>
      <td>${ct.nome_contratada || "-"}</td>
      <td>${ct.orgao || "-"}</td>
      <td>${formatarMoeda(ct.valor_contratado)}</td>
      <td>${ct.status || "-"}</td>
      <td>${truncar(ct.objeto, 140)}</td>
    </tr>
  `).join("");
  return `
    <h3>Maiores contratos firmados pelo estado</h3>
    <p class="meta">Lista limitada aos contratos de maior valor de cada ano do mandato, não é a lista completa.</p>
    <table class="tabela-simples">
      <thead><tr><th>Ano</th><th>Contratada</th><th>Órgão</th><th>Valor</th><th>Situação</th><th>Objeto</th></tr></thead>
      <tbody>${corpo}</tbody>
    </table>
    <p class="fonte">Fonte: Portal da Transparência do Piauí.</p>
  `;
}

function renderizarGestaoLicitacoes(linhas) {
  if (linhas.length === 0) return "";
  const corpo = linhas.map((l) => `
    <tr>
      <td>${l.ano || "-"}</td>
      <td>${l.modalidade || "-"}</td>
      <td>${l.qtd || "0"}</td>
      <td>${formatarMoeda(l.valor_total_previsto)}</td>
    </tr>
  `).join("");
  return `
    <h3>Licitações abertas pelo estado (por modalidade)</h3>
    <table class="tabela-simples">
      <thead><tr><th>Ano</th><th>Modalidade</th><th>Quantidade</th><th>Valor total previsto</th></tr></thead>
      <tbody>${corpo}</tbody>
    </table>
    <p class="fonte">Fonte: Portal da Transparência do Piauí.</p>
  `;
}

function renderizarGestaoConvenios(linhas) {
  if (linhas.length === 0) return "";
  const corpo = linhas.map((cv) => `
    <tr>
      <td>${cv.ano || "-"}</td>
      <td>${cv.nome_proponente || "-"}</td>
      <td>${cv.nome_concedente || "-"}</td>
      <td>${formatarMoeda(cv.valor_total)}</td>
      <td>${cv.situacao || "-"}</td>
      <td>${truncar(cv.objeto, 140)}</td>
    </tr>
  `).join("");
  return `
    <h3>Convênios e parcerias do estado</h3>
    <table class="tabela-simples">
      <thead><tr><th>Ano</th><th>Proponente</th><th>Órgão concedente</th><th>Valor</th><th>Situação</th><th>Objeto</th></tr></thead>
      <tbody>${corpo}</tbody>
    </table>
    <p class="fonte">Fonte: Portal da Transparência do Piauí.</p>
  `;
}

function renderizarEmendasEstaduais(linhas) {
  if (linhas.length === 0) {
    return "<h3>Emendas parlamentares estaduais</h3><p class='meta'>Nenhuma emenda encontrada no período consultado.</p>";
  }
  const corpo = linhas.map((e) => `
    <tr>
      <td>${e.ano || "-"}</td>
      <td>${e.status || "-"}</td>
      <td>${e.modalidade || "-"}</td>
      <td>${truncar(e.beneficiario_nome, 100)}</td>
      <td>${e.localidade_beneficiada || "-"}</td>
      <td>${formatarMoeda(e.valor)}</td>
    </tr>
  `).join("");
  return `
    <h3>Emendas parlamentares estaduais</h3>
    <table class="tabela-simples">
      <thead><tr><th>Ano</th><th>Status</th><th>Modalidade</th><th>Beneficiário</th><th>Localidade</th><th>Valor</th></tr></thead>
      <tbody>${corpo}</tbody>
    </table>
    <p class="fonte">Fonte: Portal da Transparência do Piauí / Assembleia Legislativa do Piauí (ALEPI).</p>
  `;
}

function escaparHtml(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}

function voltarParaBusca() {
  areaDetalhe.hidden = true;
  areaDetalhe.innerHTML = "";
  areaResultados.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

campoBusca.addEventListener("input", () => {
  clearTimeout(temporizadorBusca);
  temporizadorBusca = setTimeout(buscar, 350);
});
filtroCargo.addEventListener("change", buscar);
