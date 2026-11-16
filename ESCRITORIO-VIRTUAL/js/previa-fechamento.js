/*
 * PRÉVIA DO FECHAMENTO (modo operação local) + identificação visível do AMBIENTE (REAL × DEMONSTRAÇÃO).
 * Tudo vem do servidor (GET /api/solicitacoes/<SOL>/previa-fechamento, somente leitura). Exibição só com textContent.
 * Ordem da tela: RESUMO → STATUS POR DEPARTAMENTO → DECISÕES DO SUPERVISOR → PENDÊNCIAS → DETALHES (sob demanda).
 */
(function () {
  "use strict";
  const meta = document.querySelector('meta[name="prime-sessao"]');
  const ambiente = (document.querySelector('meta[name="prime-ambiente"]') || {}).content || "";

  // ---------------------------------------------------------------- identificação do ambiente (segurança: P0)
  if (ambiente) {
    const faixa = document.createElement("div");
    faixa.className = "amb-faixa amb-" + (ambiente === "DEMONSTRACAO" ? "demo" : ambiente === "TESTE" ? "teste" : "real");
    faixa.setAttribute("role", "status");
    faixa.dataset.ambiente = ambiente;
    faixa.textContent = ambiente === "DEMONSTRACAO"
      ? "DEMONSTRAÇÃO · dados fictícios · nada aqui afeta o ambiente real"
      : ambiente === "TESTE"
        ? "AMBIENTE DE TESTE · dados fictícios isolados · nada aqui afeta o ambiente real"
        : "AMBIENTE REAL · dados reais das empresas · toda ação é auditada";
    document.body.prepend(faixa);
    document.title = (ambiente === "DEMONSTRACAO" ? "[DEMONSTRAÇÃO] " : ambiente === "TESTE" ? "[TESTE] " : "[REAL] ") + document.title;
  }
  if (!meta || !meta.content || !window.EV) return;
  const TOKEN = meta.content;

  function el(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined && texto !== null) e.textContent = String(texto);
    return e;
  }
  async function api(rota) {
    let r;
    try {
      r = await fetch("/api" + rota, { cache: "no-store", credentials: "same-origin", headers: { "X-Prime-Sessao": TOKEN } });
    } catch (_) {
      throw new Error("Não foi possível falar com o aplicativo. Confira se o servidor local está em execução.");
    }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.erro || d.mensagem || `Não foi possível carregar a prévia (erro ${r.status}).`);
    return d;
  }
  const DEP = { FISCAL: "Fiscal", FINANCEIRO: "Financeiro", CONTABIL: "Contábil", DP: "DP", CONCILIACAO: "Conciliação",
    COORDENADOR: "Coordenador", SUPERVISOR: "Supervisor", A_CONFERIR: "A conferir" };
  const ORDEM = ["FISCAL", "FINANCEIRO", "CONTABIL", "DP", "CONCILIACAO"];
  const TOM = { NAO_INICIADO: "cinza", EM_PROCESSAMENTO: "azul", AGUARDANDO_SUPERVISOR: "ambar", COM_PENDENCIAS: "vermelho", CONCLUIDO: "verde",
    PREVIA_PRONTA: "verde", APROVADO_SIMULACAO: "verde", EXECUCAO_INTERROMPIDA: "vermelho" };
  const STATUS_CONTA = { CONCILIADA: "Conciliada", DIVERGENTE: "Divergente", SEM_COMPOSICAO: "Sem composição", COMPOSICAO_INCOMPLETA: "Composição incompleta",
    AGUARDANDO_DOCUMENTO: "Aguardando documento", AGUARDANDO_SUPERVISOR: "Aguardando Supervisor" };
  const REC = { RECONHECIDO_ADAPTER_EXISTENTE: "Reconhecido · adapter existente", RECONHECIDO_LAYOUT_NOVO_ADAPTER_NECESSARIO: "Layout novo · adapter necessário",
    NAO_RECONHECIDO_AGUARDANDO_SUPERVISOR: "Não reconhecido · aguardando Supervisor" };
  const CLASSE = { BLOQUEIO: "Bloqueio", ATENCAO: "Atenção", INFORMATIVO: "Informativo" };
  const ORIGEM = { "CONCILIACAO (balanço)": "Conciliação (balanço)", CONCILIACAO: "Conciliação", FINANCEIRO: "Financeiro", "FINANCEIRO (intercâmbio)": "Financeiro (consulta às áreas)",
    FISCAL: "Fiscal", DP: "DP", DOCUMENTOS: "Documentos", COORDENADOR: "Coordenador", INTERCAMBIO: "Intercâmbio" };
  // código técnico → texto legível (ex.: AGUARDANDO_SUPERVISOR → "Aguardando supervisor")
  const legivel = (s) => (s ? String(s).replace(/_/g, " ").toLowerCase().replace(/^./, (x) => x.toUpperCase()) : "—");
  const hora = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");
  const brl = (v) => (v === null || v === undefined || v === "" ? "—" : Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }));
  const origem = (p) => (p ? `Origem: ${DEP[p.departamento] || p.departamento} · ${p.documento ? String(p.documento).split("/").pop() : "resultado da área"}`
    + `${p.registro ? ` · registro ${p.registro}` : ""}${p.resultado_sha256 ? ` · sha256 ${String(p.resultado_sha256).slice(0, 12)}…` : p.sha256 ? ` · sha256 ${String(p.sha256).slice(0, 12)}…` : ""}`
    + ` · ${p.empresa} · ${p.competencia}` : "");
  function detalhes(titulo, aberto, ...filhos) {
    const d = el("details", "pf-det");
    d.open = !!aberto;
    d.append(el("summary", null, titulo), ...filhos);
    return d;
  }
  function tabela(cabecalhos, linhas, classe) {
    const t = el("table", "pf-tabela " + (classe || ""));
    const h = el("tr");
    cabecalhos.forEach((c) => h.append(el("th", null, c)));
    t.append(el("thead"), el("tbody"));
    t.tHead.append(h);
    linhas.forEach((cels) => {
      const tr = el("tr");
      cels.forEach((c) => {
        const td = el("td");
        if (c instanceof Node) td.append(c); else td.textContent = c === null || c === undefined ? "—" : String(c);
        tr.append(td);
      });
      t.tBodies[0].append(tr);
    });
    return t;
  }
  function chip(texto, tom) { return el("span", "pf-chip pf-" + (tom || "cinza"), texto); }

  // ---------------------------------------------------------------- blocos
  function cabecalho(p) {
    const c = el("div", "pf-cabecalho");
    c.dataset.statusGeral = p.status_geral;
    c.append(el("h3", "pf-titulo", "PRÉVIA DO FECHAMENTO"),
      el("p", "pf-ident", `${p.empresa} · competência ${p.competencia} · ${p.sol}${p.tentativa ? ` · tentativa ${String(p.tentativa.numero).padStart(4, "0")} (${legivel(p.tentativa.status)})` : ""} · gerada em ${hora(p.gerada_em)}`),
      chip(p.status_geral_texto, TOM[p.status_geral]),
      el("p", "pf-nota", `Lançamentos efetivados: ${p.lancamentos_efetivados}. Tudo em SIMULAÇÃO: propostas não são lançamentos; nada é enviado ao Domínio sem a sua aprovação.`));
    return c;
  }
  function geral(p) {
    const g = el("div", "pf-geral");
    const dec = p.supervisor.decisoes_necessarias.length;
    [["Supervisor", dec ? `${dec} decisão(ões) necessária(s)` : "Nenhuma decisão pendente", dec ? "ambar" : "verde"],
      ["Coordenador", `Estado: ${legivel(p.coordenador.estado)}`, "azul"],
      ["Fechamento geral", p.status_geral_texto, TOM[p.status_geral]]].forEach(([n, t, tom]) => {
      const x = el("div", "pf-geral-item pf-borda-" + tom);
      x.append(el("strong", null, n), el("span", null, t));
      g.append(x);
    });
    return g;
  }
  const NUMEROS = {
    FISCAL: (d) => [["Documentos", d.documentos_recebidos], ["Processados", d.processados], ["Obrigações", d.obrigacoes], ["Propostas (Contábil)", d.propostas]],
    FINANCEIRO: (d) => [["Movimentos", d.movimentos], ["Conciliados/confirmados", d.conciliados_ou_confirmados], ["Pendentes", d.pendentes], ["Candidatos de outras áreas", d.candidatos_encontrados]]
      .concat(d.central ? [["Central: confirmados", `${d.central.movimentos_confirmados}/${d.central.movimentos_bancarios}`], ["Central: bloqueios", d.central.bloqueios_restantes]] : []),
    CONTABIL: (d) => [["Propostas", d.propostas], ["Completas", d.completas], ["Incompletas", d.incompletas], ["Aguardando Supervisor", d.aguardando_supervisor], ["Lançamentos efetivados", d.lancamentos_efetivados]],
    DP: (d) => [["Documentos", d.documentos_recebidos], ["Processados", d.processados], ["Obrigações", d.obrigacoes], ["Propostas (Contábil)", d.propostas]],
    CONCILIACAO: (d) => [["Contas", d.contas], ["Conciliadas", d.CONCILIADA], ["Divergentes", d.DIVERGENTE], ["Sem composição", d.SEM_COMPOSICAO], ["Aguardando documento", d.AGUARDANDO_DOCUMENTO]]
  };
  function departamentos(p, filtrar) {
    const g = el("div", "pf-deps");
    ORDEM.forEach((k) => {
      const d = p.departamentos[k];
      const c = el("section", "pf-dep pf-borda-" + (TOM[d.status] || "cinza"));
      c.dataset.departamento = k;
      c.dataset.status = d.status;
      c.append(el("h4", null, d.nome), chip(d.status_texto, TOM[d.status]));
      const dl = el("dl", "pf-num");
      NUMEROS[k](d).forEach(([t, v]) => dl.append(el("dt", null, t), el("dd", null, v === undefined || v === null ? "—" : v)));
      c.append(dl, el("p", "pf-pend-n", `Pendências: ${d.pendencias}${d.bloqueios ? ` (${d.bloqueios} bloqueio)` : ""}`
        + (d.pendencias_detectadas_para_outros ? ` · detectadas para outras áreas: ${d.pendencias_detectadas_para_outros}` : "")),
      el("p", "pf-acao", `Ação: ${d.acao_necessaria}`));
      const ver = el("button", "botao-sec pf-ver", "Ver pendências");
      ver.type = "button";
      ver.addEventListener("click", () => filtrar(k));
      c.append(ver);
      g.append(c);
    });
    return g;
  }
  function decisoes(p) {
    const b = el("div", "ac-bloco pf-decisoes");
    b.append(el("h3", "ac-titulo-bloco", "Decisões necessárias do Supervisor"));
    if (!p.supervisor.decisoes_necessarias.length) b.append(el("p", "nd", "Nenhuma decisão pendente agora."));
    const ul = el("ul", "pf-lista");
    p.supervisor.decisoes_necessarias.forEach((d) => {
      const li = el("li");
      li.append(el("strong", null, `${DEP[d.departamento] || d.departamento}: ${d.decisao}`), el("span", "pf-sub", d.detalhe || ""));
      ul.append(li);
    });
    b.append(ul);
    const ck = el("ul", "pf-lista pf-checkpoints");
    p.checkpoints.forEach((c) => ck.append(el("li", null, `${c.nome}: ${legivel(c.situacao)}${c.em ? ` · ${hora(c.em)}` : ""}${c.autorizado_em ? ` · autorizado em ${hora(c.autorizado_em)}` : ""}`
      + (c.proximas_etapas && c.proximas_etapas.length ? ` · próximas: ${c.proximas_etapas.join(", ")}` : ""))));
    b.append(el("h4", "pf-sub-titulo", "Checkpoints"), ck);
    return b;
  }
  function pendencias(p) {
    const b = el("div", "ac-bloco pf-pendencias");
    const titulo = el("h3", "ac-titulo-bloco", `Pendências (${p.pendencias.length})`);
    const filtro = el("select", "pf-filtro");
    [["", "Todos os departamentos"], ...[...ORDEM, "COORDENADOR", "SUPERVISOR"].map((k) => [k, DEP[k]])].forEach(([v, t]) => {
      const o = el("option", null, t);
      o.value = v;
      filtro.append(o);
    });
    const corpo = el("div");
    const desenhar = () => {
      const lista = p.pendencias.filter((x) => !filtro.value || x.departamento === filtro.value);
      corpo.replaceChildren(lista.length ? tabela(["Classificação", "Departamento responsável", "Problema", "Impacto", "O que fazer", "Origem"],
        lista.map((x) => [chip(CLASSE[x.classificacao] || x.classificacao, x.classificacao === "BLOQUEIO" ? "vermelho" : x.classificacao === "ATENCAO" ? "ambar" : "azul"),
          DEP[x.responsavel_esperado] || x.responsavel_esperado, x.problema, x.impacto, x.o_que_fazer, ORIGEM[x.origem] || x.origem]), "pf-tab-pend") : el("p", "nd", "Nenhuma pendência neste filtro."));
    };
    filtro.addEventListener("change", desenhar);
    desenhar();
    b.append(titulo, filtro, corpo);
    b.filtrar = (k) => { filtro.value = k; desenhar(); b.scrollIntoView({ block: "start" }); };
    return b;
  }
  function documentos(p) {
    const c = p.documentos.classificacao;
    const resumo = el("div", "pf-docs-resumo");
    [...ORDEM, "A_CONFERIR"].forEach((k) => {
      const x = c[k];
      const caixa = el("div", "pf-docs-dep" + (k === "A_CONFERIR" && x ? " pf-borda-ambar" : ""));
      caixa.append(el("strong", null, `${DEP[k]}: ${x ? x.total : 0}`));
      if (x) Object.entries(x.categorias).forEach(([cat, n]) => caixa.append(el("span", null, `${cat}: ${n}`)));
      resumo.append(caixa);
    });
    const lista = tabela(["Documento", "Tipo", "Departamento", "Consumidores", "Leitura"],
      p.documentos.itens.map((d) => [d.nome, d.tipo, DEP[d.departamento] || d.departamento, (d.consumidores || []).map((x) => DEP[x] || x).join(", ") || "—",
        `${REC[d.situacao] || d.situacao}${d.adapter ? ` (${d.adapter})` : ""}${d.motivo ? ` — ${d.motivo}` : ""}`]), "pf-tab-docs");
    return detalhes(`Documentos recebidos (${p.documentos.total}) — classificação por departamento`, true, resumo, detalhes("Ver cada documento", false, lista));
  }
  function balanco(p) {
    const b = p.conciliacao_balanco;
    const r = b.resumo || {};
    const linhas = b.contas.map((x) => [x.conta, x.descricao, chip(STATUS_CONTA[x.status] || x.status, x.status === "CONCILIADA" ? "verde" : x.status === "DIVERGENTE" ? "vermelho" : "ambar"),
      brl(x.saldo_balancete), brl(x.saldo_composicao), DEP[x.departamento_responsavel] || x.departamento_responsavel, x.problema, x.o_que_fazer]);
    return detalhes(`Conciliação do balanço — ${Object.entries(STATUS_CONTA).map(([k, t]) => `${t}: ${r[k] || 0}`).join(" · ")}`, false,
      ...(b.avisos || []).map((a) => el("p", "pf-nota", a)),
      linhas.length ? tabela(["Conta", "Descrição", "Status", "Saldo balancete", "Saldo composição", "Responsável", "Problema", "O que fazer"], linhas, "pf-tab-balanco")
        : el("p", "nd", "Sem balancete/book do período: a conciliação do balanço aguarda os documentos."));
  }
  function impostos(p) {
    const i = p.impostos;
    return detalhes(`Impostos e obrigações — ${i.obrigacoes.length} obrigação(ões) · ${i.provisoes_propostas} com provisão proposta · ${i.pagamentos_identificados} com pagamento identificado (candidato)`, false,
      i.obrigacoes.length ? tabela(["Tributo/obrigação", "Código", "Competência", "Total", "Departamento", "Provisão proposta", "Pagamento (candidato)", "Pendências", "Origem"],
        i.obrigacoes.map((o) => [o.tributo || "não identificado", o.codigo, o.competencia, brl(o.total), DEP[o.departamento], o.provisao_proposta.length ? "sim" : "não",
          o.pagamento_identificado.length ? `sim (${o.pagamento_identificado.join(", ")})` : "não", o.pendencias.join(" · ") || "—", origem(o.proveniencia)]), "pf-tab-impostos")
        : el("p", "nd", "Nenhuma obrigação publicada por Fiscal ou DP."));
  }
  function consultas(p) {
    const f = p.departamentos.FINANCEIRO.consultas_outras_areas || [];
    const ul = el("div", "pf-consultas");
    f.forEach((m) => {
      const x = el("div", "pf-consulta");
      x.append(el("strong", null, `${m.data} · ${m.descricao} · ${brl(m.valor)} (${m.direcao === "DEBITO" ? "saída" : "entrada"})`));
      if (!m.candidatos.length) x.append(el("span", "pf-sub", "Nenhum candidato encontrado em Fiscal, DP, Contábil ou Conciliação."));
      m.candidatos.forEach((c) => x.append(el("span", "pf-sub", `Candidato ${DEP[c.departamento]}: ${c.descricao} · critérios: ${c.criterios.join(", ")} · ${c.forca === "CANDIDATO_COM_EVIDENCIA" ? "com evidência" : "só valor"} — NÃO confirmado`)));
      ul.append(x);
    });
    return detalhes(`Financeiro consultando as outras áreas (${f.length} movimento(s) em aberto)`, false,
      el("p", "pf-nota", "Fato gerador ≠ liquidação: a consulta só sugere candidatos (valor exato + critérios registrados). Nenhuma associação é confirmada automaticamente."),
      f.length ? ul : el("p", "nd", "Todos os movimentos têm suporte ou associação confirmada."));
  }
  function propostas(p) {
    const l = p.departamentos.CONTABIL.lista_propostas || [];
    return detalhes(`Propostas contábeis (${l.length}) — SIMULAÇÃO, nenhuma efetivada`, false,
      l.length ? tabela(["Origem", "Data", "Débito", "Crédito", "Valor", "Histórico", "Status", "De onde veio"],
        l.map((x) => [x.etapa, x.data, x.debito, x.credito, brl(x.valor), x.historico, x.status, origem(x.proveniencia)]), "pf-tab-propostas")
        : el("p", "nd", "Nenhuma proposta ainda (a Contabilidade executa depois do checkpoint)."));
  }

  // ---------------------------------------------------------------- painel
  function painel(sol) {
    const s = el("div", "pf-painel");
    s.dataset.previaFechamento = sol;
    const msg = el("p", "nd", "Carregando a prévia do fechamento…");
    s.append(msg);
    api(`/solicitacoes/${sol}/previa-fechamento`).then((p) => {
      const pend = pendencias(p);
      s.replaceChildren(cabecalho(p), geral(p), departamentos(p, (k) => pend.filtrar(k)), decisoes(p), pend,
        documentos(p), consultas(p), propostas(p), impostos(p), balanco(p),
        detalhes("Avisos e limites", false, ...p.avisos.map((a) => el("p", "pf-nota", a))));
    }).catch((e) => s.replaceChildren(el("p", "cr-erro-fixo", e.message)));
    return s;
  }
  window.EV.previa = { painel, ambiente };
})();
