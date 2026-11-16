/*
 * CONCILIAÇÃO CAIXINHA (modo operação local) — mesma aplicação, mesma API, mesmo padrão visual do Escritório Virtual.
 * Empresas com rotina CAIXINHA: configuração (contas, tributos, datas, política da folha) com aprovação por frase; envio dos cinco
 * documentos; acompanhamento; painel TRIBUTOS · FOLHA · CAIXA · PENDÊNCIAS; evidências (documento e página); simulação do TXT;
 * aprovação; execução em lote. Todos os números vêm do servidor. Exibição somente com textContent.
 * Ordem da tela: RESUMO → STATUS → PENDÊNCIAS → AÇÃO NECESSÁRIA → DETALHES.
 */
(function () {
  "use strict";
  const meta = document.querySelector('meta[name="prime-sessao"]');
  if (!meta || !meta.content || !window.EV || !window.EV.operacao) return;
  const TOKEN = meta.content;
  const op = window.EV.operacao;

  function el(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined && texto !== null) e.textContent = String(texto);
    return e;
  }
  async function api(metodo, rota, corpo, cab) {
    let r;
    const bruto = corpo instanceof ArrayBuffer;
    try {
      r = await fetch("/api" + rota, { method: metodo, cache: "no-store", credentials: "same-origin",
        headers: Object.assign({ "X-Prime-Sessao": TOKEN }, bruto || corpo === undefined ? {} : { "Content-Type": "application/json" }, cab || {}),
        body: corpo === undefined ? undefined : bruto ? corpo : JSON.stringify(corpo) });
    } catch (_) {
      throw new Error("Não foi possível falar com o aplicativo. Confira se o servidor local está em execução.");
    }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.erro || d.mensagem || `Operação não concluída (erro ${r.status}).`);
    return d;
  }
  async function baixar(rota, nome, pagina) {
    const r = await fetch("/api" + rota, { cache: "no-store", credentials: "same-origin", headers: { "X-Prime-Sessao": TOKEN } });
    if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.erro || `Documento indisponível (erro ${r.status}).`); }
    const url = URL.createObjectURL(await r.blob());
    const a = el("a");
    a.href = url + (pagina ? `#page=${pagina}` : "");
    if (nome) a.download = nome; else a.target = "_blank";
    a.rel = "noopener";
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  async function sha256(buffer) {
    const d = await crypto.subtle.digest("SHA-256", buffer);
    return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  const brl = (v) => (v === null || v === undefined || v === "" ? "—" : Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }));
  const dmy = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—");
  const compAtual = () => { const d = new Date(); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };
  const CLASSE = { PAGA_E_CONTABILIZADA: ["Paga e contabilizada", "verde"], PAGA_NAO_CONTABILIZADA: ["Paga e não contabilizada", "azul"],
    EM_ABERTO: ["Em aberto", "cinza"], DIVERGENTE: ["Divergente", "vermelho"], SEM_PROVISAO_IDENTIFICADA: ["Sem provisão identificada", "ambar"],
    PAGAMENTO_DUPLICADO: ["Pagamento duplicado", "vermelho"], NECESSITA_REVISAO: ["Necessita revisão", "ambar"] };
  const CATEGORIA_TOM = { CONCILIADA: "verde", COM_DIVERGENCIAS: "vermelho", DOCUMENTOS_INSUFICIENTES: "ambar", AGUARDANDO_APROVACAO: "azul",
    PRONTA_PARA_EXPORTACAO: "verde", EM_PROCESSAMENTO: "azul", SEM_SOLICITACAO: "cinza" };
  const SITUACAO_FOLHA = { REGULARIZACAO_PROPOSTA: "Regularização proposta (política)", REGULARIZACAO_INCOMPLETA: "Regularização incompleta",
    PAGA_E_CONTABILIZADA: "Nada a regularizar", NECESSITA_REVISAO: "Necessita revisão", DIVERGENTE: "Divergente" };
  const ETAPA = { CAIXINHA_CONTABIL: "Contábil · balancete e razão", CAIXINHA_FISCAL: "Fiscal · e-CAC e situação fiscal",
    CAIXINHA_DP: "DP · resumo da folha", CAIXINHA_CONCILIACAO: "Conciliação Caixinha" };
  const chip = (texto, tom) => el("span", "pf-chip pf-" + (tom || "cinza"), texto);
  function tabela(cab, linhas) {
    const w = el("div", "gestao-tabela");
    const t = el("table");
    const h = el("tr");
    cab.forEach((c) => h.append(el("th", null, c)));
    t.append(el("thead"), el("tbody"));
    t.tHead.append(h);
    linhas.forEach((cels) => {
      const tr = el("tr");
      cels.forEach((c) => { const td = el("td"); if (c instanceof Node) td.append(c); else td.textContent = c === null || c === undefined ? "—" : String(c); tr.append(td); });
      t.tBodies[0].append(tr);
    });
    w.append(t);
    return w;
  }
  function detalhes(titulo, aberto, ...filhos) {
    const d = el("details");
    d.open = !!aberto;
    d.append(el("summary", null, titulo), ...filhos);
    return d;
  }
  function campo(pai, rotulo, tipo, valor) {
    const l = el("label", "gestao-campo");
    const i = el(tipo === "select" ? "select" : tipo === "textarea" ? "textarea" : "input");
    if (i.tagName === "INPUT") i.type = tipo || "text";
    if (valor !== undefined && valor !== null) i.value = valor;
    l.append(el("span", null, rotulo), i);
    pai.append(l);
    return i;
  }
  function opcoes(sel, pares, atual) {
    pares.forEach(([v, t]) => { const o = el("option", null, t); o.value = v; sel.append(o); });
    if (atual !== undefined && atual !== null) sel.value = atual;
  }

  // ---------------------------------------------------------------- área própria (largura total) e navegação
  const area = el("section", "gestao cxn");
  area.hidden = true;
  area.setAttribute("aria-label", "Conciliação Caixinha");
  const cabeca = el("div", "gestao-cabeca");
  const fechar = el("button", "fechar", "✕");
  fechar.type = "button";
  fechar.setAttribute("aria-label", "Recolher Conciliação Caixinha");
  fechar.addEventListener("click", () => esconder());
  cabeca.append(el("span", null, "Conciliação Caixinha · empresas sem extrato bancário"), fechar);
  const aviso = el("p", "gestao-mensagem");
  aviso.setAttribute("role", "status");
  const corpo = el("div", "gestao-conteudo");
  area.append(cabeca, aviso, corpo);
  document.body.append(area);
  let versao = 0;
  const lotesPreparados = {};          // empresa → {lote, competencia, arquivos} (envio feito; ainda não iniciado)
  function esconder() { versao++; area.hidden = true; const b = document.querySelector('.gestao-nav [data-pagina="caixinha"]'); if (b) b.setAttribute("aria-current", "false"); }
  function erro(t) { aviso.textContent = t; aviso.dataset.tipo = "erro"; aviso.scrollIntoView({ block: "nearest" }); }
  function informar(t) { aviso.textContent = t; aviso.dataset.tipo = "ok"; }
  function limpar(titulo, intro) {
    versao++;
    area.hidden = false;
    op.fechar();
    const g = document.querySelector("section.gestao:not(.cxn)");
    if (g) g.hidden = true;
    aviso.textContent = "";
    delete aviso.dataset.tipo;
    corpo.replaceChildren(el("h1", null, titulo), el("p", "gestao-intro", intro));
    return versao;
  }
  function botao(texto, fn, classe) {
    const b = el("button", "gestao-botao " + (classe || ""), texto);
    b.type = "button";
    b.addEventListener("click", async () => { b.disabled = true; try { await fn(); } catch (e) { erro(e.message); } finally { b.disabled = false; } });
    return b;
  }
  const nav = document.querySelector(".gestao-nav");
  if (nav) {
    const b = el("button", null, "Caixinha");
    b.type = "button";
    b.dataset.pagina = "caixinha";
    b.dataset.icone = "◧";
    b.title = "Conciliação Caixinha (empresas sem extrato bancário)";
    b.addEventListener("click", () => { if (!area.hidden) { esconder(); return; } nav.querySelectorAll("button").forEach((x) => x.setAttribute("aria-current", x === b ? "page" : "false")); inicio().catch((e) => erro(e.message)); });
    const recolher = nav.querySelector('[data-pagina="escritorio"]');
    nav.insertBefore(b, recolher || null);
    nav.addEventListener("click", (ev) => { const alvo = ev.target.closest("button"); if (alvo && alvo !== b && !area.hidden) esconder(); }, true);
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !area.hidden) esconder(); });

  // ---------------------------------------------------------------- INÍCIO: empresas Caixinha da competência (lote)
  async function inicio(comp) {
    comp = comp || compAtual();
    const v = limpar("Conciliação Caixinha", "Baixas das obrigações (tributos e pró-labore) contra o Caixa Geral, a partir de balancete, razão, pagamentos do "
      + "e-CAC, situação fiscal e resumo da folha. Não exige extrato bancário. Tudo em SIMULAÇÃO até a sua aprovação.");
    const filtro = el("div", "gestao-filtros");
    const c = campo(filtro, "Competência", "month", comp);
    c.addEventListener("change", () => inicio(c.value).catch((e) => erro(e.message)));
    corpo.append(filtro);
    const d = await api("GET", `/caixinha/lote?competencia=${comp}`);
    if (v !== versao) return;
    const totais = el("div", "cxn-cards");
    Object.entries(d.categorias).forEach(([k, t]) => { const x = el("div", "cxn-card pf-borda-" + CATEGORIA_TOM[k]); x.dataset.categoria = k; x.append(el("strong", null, String(d.totais[k] || 0)), el("span", null, t)); totais.append(x); });
    corpo.append(totais);
    if (!d.empresas.length) {
      corpo.append(el("p", "gestao-nota", "Nenhuma empresa com rotina CAIXINHA. Abra Empresas → (empresa) e use “Configurar Conciliação Caixinha” abaixo."));
    }
    const lista = el("div", "gestao-lista");
    const selecionadas = new Set();
    d.empresas.forEach((x) => {
      const a = el("article", "gestao-item");
      a.dataset.empresa = x.empresa;
      a.dataset.categoria = x.categoria;
      a.append(el("h2", null, `${x.empresa} · ${x.nome}`), chip(d.categorias[x.categoria], CATEGORIA_TOM[x.categoria]), el("p", null, x.texto || ""));
      if (!x.autorizada) a.append(el("p", "gestao-nota", "Piloto Caixinha ainda não habilitado: configure a empresa."));
      if (x.sol) a.append(botao(`Abrir ${x.sol}`, () => painel(x.sol)));
      a.append(botao("Configurar", () => configurar(x.empresa, comp)));
      if (x.autorizada) a.append(botao(x.sol ? "Nova conciliação (reenviar documentos)" : "Enviar documentos", () => enviar(x.empresa, comp)));
      const prep = lotesPreparados[x.empresa];
      if (prep && prep.competencia === comp) {
        const l = el("label", "cxn-sel");
        const cb = el("input");
        cb.type = "checkbox";
        cb.addEventListener("change", () => (cb.checked ? selecionadas.add(prep.lote) : selecionadas.delete(prep.lote)));
        l.append(cb, el("span", null, ` Documentos enviados (${prep.arquivos}) — incluir na execução em lote`));
        a.append(l);
      }
      lista.append(a);
    });
    corpo.append(lista);
    const lote = el("div", "gestao-card");
    lote.append(el("h2", null, "Execução em lote"), el("p", "gestao-nota", "Envie os documentos de cada empresa (sem iniciar), marque-as e execute: cada empresa é "
      + "processada na própria solicitação, uma de cada vez, com os mesmos controles do fluxo individual."));
    const conf = el("label", "cxn-sel");
    const cbc = el("input");
    cbc.type = "checkbox";
    conf.append(cbc, el("span", null, " Conferirei os resultados de cada empresa antes de aprovar."));
    lote.append(conf, botao("Executar empresas selecionadas", async () => {
      if (!selecionadas.size) throw new Error("Selecione ao menos uma empresa com documentos enviados.");
      if (!cbc.checked) throw new Error("Confirme que conferirá os resultados.");
      const r = await api("POST", "/caixinha/lote/executar", { lotes: [...selecionadas], confirmado: true });
      [...selecionadas].forEach((l) => Object.keys(lotesPreparados).forEach((k) => { if (lotesPreparados[k].lote === l) delete lotesPreparados[k]; }));
      informar(`Fila iniciada (${r.lotes.length} empresa(s)). Acompanhe aqui; atualize em alguns instantes.`);
      await inicio(comp);
    }, "gestao-primario"));
    if (d.fila && d.fila.lotes && d.fila.lotes.length) {
      lote.append(el("p", "gestao-nota", `Última fila: ${d.fila.resultados.length}/${d.fila.lotes.length} concluída(s)${d.fila.fim ? " · finalizada" : " · em execução"}.`));
    }
    lote.append(botao("Atualizar", () => inicio(comp)));
    corpo.append(lote);
  }

  // ---------------------------------------------------------------- ENVIO DOS DOCUMENTOS
  async function enviar(emp, comp) {
    const v = limpar(`Enviar documentos · ${emp}`, "Envie, de uma vez, os cinco documentos do mês: balancete, razão, pagamentos do e-CAC, relatório de situação "
      + "fiscal e resumo mensal da folha do Domínio. O sistema identifica cada um pelo CONTEÚDO (o nome do arquivo não importa).");
    const f = el("div", "gestao-card");
    const c = campo(f, "Competência", "month", comp);
    const arq = campo(f, "Documentos (PDF, TXT, CSV ou planilha)", "file");
    arq.multiple = true;
    const conf = el("label", "cxn-sel");
    const cb = el("input");
    cb.type = "checkbox";
    conf.append(cb, el("span", null, " Conferirei o resultado antes de qualquer aprovação (SIMULAÇÃO)."));
    f.append(conf);
    const status = el("p", "gestao-nota");
    async function preparar() {
      if (!arq.files.length) throw new Error("Selecione os documentos.");
      const [a, m] = c.value.split("-");
      const r = await api("POST", "/lotes", { empresa: emp, competencia: c.value, fluxo: "CONCILIACAO_CAIXINHA", instrucao: `Conciliação Caixinha de ${m}/${a}.` });
      for (const file of arq.files) {
        status.textContent = `Enviando ${file.name}…`;
        const buffer = await file.arrayBuffer();
        await api("PUT", `/lotes/${r.lote}/arquivos`, buffer, { "X-Nome-Arquivo": encodeURIComponent(file.name), "X-Sha256": await sha256(buffer) });
      }
      status.textContent = `${arq.files.length} documento(s) recebido(s) e conferido(s) por SHA-256.`;
      return r.lote;
    }
    f.append(status, botao("Enviar e iniciar a conciliação", async () => {
      if (!cb.checked) throw new Error("Confirme a conferência humana do resultado.");
      const lote = await preparar();
      const r = await api("POST", `/lotes/${lote}/iniciar`, { conferencia_humana: true });
      informar(`${r.sol} aberta. Acompanhe o processamento.`);
      await acompanhar(r.sol);
    }, "gestao-primario"), botao("Só enviar (incluir depois na execução em lote)", async () => {
      const lote = await preparar();
      lotesPreparados[emp] = { lote, competencia: c.value, arquivos: arq.files.length };
      informar("Documentos enviados. Marque a empresa na execução em lote.");
      await inicio(c.value);
    }), botao("Voltar", () => inicio(comp)));
    if (v === versao) corpo.append(f);
  }
  async function acompanhar(sol) {
    for (let i = 0; i < 240; i++) {
      const p = await api("GET", `/solicitacoes/${sol}/caixinha`).catch(() => null);
      if (p && !String(p.estado).endsWith("_EM_ANDAMENTO") && !p.em_execucao && p.estado !== "DOCUMENTOS_EM_ANDAMENTO") return painel(sol);
      if (i === 0) limpar(`Processando ${sol}`, "Documentos → Contábil (balancete e razão) → Fiscal (e-CAC e situação fiscal) → DP (folha) → Conciliação Caixinha.");
      await new Promise((r) => setTimeout(r, 1500));
    }
    return painel(sol);
  }

  // ---------------------------------------------------------------- PAINEL DA SOLICITAÇÃO
  async function painel(sol) {
    const v = limpar(`Conciliação Caixinha · ${sol}`, "Carregando…");
    const p = await api("GET", `/solicitacoes/${sol}/caixinha`);
    if (v !== versao) return;
    const c = p.conciliacao;
    corpo.replaceChildren(el("h1", null, `Conciliação Caixinha · ${p.empresa} · ${p.competencia.slice(5)}/${p.competencia.slice(0, 4)}`),
      el("p", "gestao-intro", `${sol} · ${p.estado.replace(/_/g, " ").toLowerCase()} · ${p.aviso}`));
    // RESUMO
    if (c) {
      const t = c.tributos, f = c.folha || {}, x = c.caixa || {};
      const grade = el("div", "cxn-resumo");
      const bloco = (titulo, linhas, tom) => {
        const s = el("section", "cxn-bloco pf-borda-" + (tom || "cinza"));
        s.append(el("h3", null, titulo));
        const dl = el("dl", "gestao-dados");
        linhas.forEach(([k, val]) => dl.append(el("dt", null, k), el("dd", null, val)));
        s.append(dl);
        return s;
      };
      grade.append(
        bloco("TRIBUTOS", [["Total provisionado (saldo)", brl(t.total_provisionado)], ["Total pago (e-CAC)", brl(t.total_pago)],
          ["Já contabilizado", brl(t.total_ja_contabilizado)], ["Baixas propostas", brl(t.baixas_propostas)], ["Saldo restante", brl(t.saldo_restante)],
          ["Divergências", String(t.divergencias)]], t.divergencias ? "ambar" : "verde"),
        bloco("FOLHA (pró-labore)", [["Saldo contábil", brl(f.saldo_contabil)], ["Último líquido", f.ultimo ? `${brl(f.ultimo.liquido)} (${(f.ultimo.competencia || "").slice(5)}/${(f.ultimo.competencia || "").slice(0, 4)})` : "—"],
          ["Competências antigas em aberto", String((f.competencias || []).filter((x2) => f.ultimo && x2.competencia < f.ultimo.competencia && Number(x2.liquido_em_aberto) !== 0).length)],
          ["Baixas propostas", brl(f.baixa)], ["Saldo esperado", brl(f.saldo_esperado)], ["Situação", SITUACAO_FOLHA[f.situacao] || (f.situacao || "—").replace(/_/g, " ").toLowerCase()]],
          f.situacao === "REGULARIZACAO_PROPOSTA" || f.situacao === "PAGA_E_CONTABILIZADA" ? "verde" : "ambar"),
        bloco("CAIXA", [["Saldo inicial", brl(x.saldo_inicial)], ["Baixas tributárias", brl(x.baixas_tributarias)], ["Baixas de folha", brl(x.baixas_folha)],
          ["Saldo contábil projetado", brl(x.saldo_projetado)]], Number(x.saldo_projetado) < 0 ? "vermelho" : "verde"),
        bloco("PENDÊNCIAS", [["Itens para revisão humana", String(c.resumo.revisao)], ["Verificações bloqueantes", String(c.resumo.bloqueantes)],
          ["Propostas completas", String(c.resumo.propostos)], ["Propostas incompletas", String(c.resumo.incompletos)],
          ["Alcance", c.alcance.parcial ? "PARCIAL" : "completo"]], c.resumo.revisao || c.resumo.bloqueantes || c.resumo.incompletos ? "ambar" : "verde"));
      corpo.append(grade, el("p", "gestao-nota", x.aviso || ""));
    } else {
      corpo.append(el("p", "gestao-nota", "Conciliação ainda não registrada (veja o status das etapas)."));
    }
    // STATUS
    const st = el("div", "gestao-card");
    st.append(el("h2", null, "Status das etapas"));
    st.append(tabela(["Etapa", "Situação", "Tentativas", "Observação"], Object.entries(p.plano).map(([k, e]) => [ETAPA[k] || k, e.situacao, e.tentativas,
      e.falha || (e.pendencias || []).slice(0, 2).join(" · ") || "—"])));
    if (p.vigencia && !p.vigencia.vigente) {
      st.append(el("p", "gestao-mensagem", "Conciliação DESATUALIZADA: " + p.vigencia.motivos.join(" ")));
      (p.vigencia.rever || []).forEach((etapa) => st.append(botao(`Executar de novo: ${ETAPA[etapa] || etapa}`, async () => {
        const just = window.prompt("Justificativa da nova tentativa (5 a 500 caracteres):", "Regras/documentos atualizados.");
        if (!just) return;
        await api("POST", `/solicitacoes/${sol}/areas/${etapa}/retomar`, { justificativa: just, confirmado: true });
        await acompanhar(sol);
      })));
    }
    Object.entries(p.plano).filter(([, e]) => e.situacao === "FALHOU").forEach(([k]) => st.append(botao(`Nova tentativa: ${ETAPA[k] || k}`, async () => {
      const just = window.prompt("Justificativa da nova tentativa:", "Nova tentativa autorizada.");
      if (!just) return;
      await api("POST", `/solicitacoes/${sol}/areas/${k}/retomar`, { justificativa: just, confirmado: true });
      await acompanhar(sol);
    })));
    corpo.append(st);
    if (!c) { corpo.append(botao("Atualizar", () => painel(sol))); return; }
    // PENDÊNCIAS
    const pend = el("div", "gestao-card");
    pend.dataset.pendencias = String(c.revisao.length);
    pend.append(el("h2", null, `Pendências para revisão humana (${c.revisao.length})`));
    if (!c.revisao.length) pend.append(el("p", "nd", "Nenhum item para revisão."));
    else pend.append(tabela(["Tipo", "Problema", "Impacto", "O que fazer", "Responsável"], c.revisao.map((r) => [chip((CLASSE[r.tipo] || [r.tipo])[0], (CLASSE[r.tipo] || [0, "ambar"])[1]),
      r.problema, r.impacto, r.o_que_fazer, r.responsavel])));
    const bloq = c.verificacoes.filter((x2) => x2.resultado !== "CONFERIDO" && x2.resultado !== "NAO_APLICAVEL");
    if (bloq.length) pend.append(el("h3", null, "Verificações não conferidas"), tabela(["Resultado", "Verificação", "Detalhe", "Ação", "Bloqueia"],
      bloq.map((x2) => [x2.resultado, x2.titulo, x2.detalhe, x2.acao, x2.bloqueia ? "sim" : "não (alerta)"])));
    corpo.append(pend);
    // AÇÃO NECESSÁRIA
    corpo.append(acao(p));
    // DETALHES
    corpo.append(contas(p), lancamentos(p), documentos(p), detalhes(`Verificações (${c.verificacoes.length})`, false,
      tabela(["Grupo", "Verificação", "Resultado", "Evidência", "Esperado", "Encontrado"], c.verificacoes.map((x2) => [x2.grupo, x2.titulo, x2.resultado,
        x2.evidencia.replace(/_/g, " ").toLowerCase(), x2.esperado, x2.encontrado]))), botao("Voltar à lista", () => inicio(p.competencia)));
  }
  function origemBotao(p, o) {
    const doc = (p.documentos || []).find((d) => o && (d.id === o.documento || d.arquivo === o.arquivo));
    if (!doc) return o && o.pagina ? `página ${o.pagina}` : "—";
    const b = el("button", "gestao-botao gestao-link", `${doc.nome}${o.pagina ? ` · p. ${o.pagina}` : ""}`);
    b.type = "button";
    b.title = "Abrir o documento de origem (original conferido por SHA-256)";
    b.addEventListener("click", () => baixar(`/solicitacoes/${p.sol}/caixinha/documento/${doc.id}`, null, o.pagina).catch((e) => erro(e.message)));
    return b;
  }
  function contas(p) {
    const c = p.conciliacao;
    const caixa = el("div");
    (c.tributos.por_conta || []).forEach((x) => {
      const obs = c.obrigacoes.filter((o) => x.obrigacoes.includes(o.id) || (o.conta === x.conta.codigo && !o.pagamento));
      const linhas = obs.map((o) => [chip((CLASSE[o.classificacao] || [o.classificacao])[0], (CLASSE[o.classificacao] || [0, "cinza"])[1]),
        `${o.tipo_documento || "provisão"} ${o.numero_documento || ""}`.trim(), o.periodo_apuracao || (o.data_provisao ? dmy(o.data_provisao) : "—"),
        dmy(o.data_pagamento), brl(o.valor_total), (o.criterios || []).concat(o.motivos || []).join(" · ") || "—", origemBotao(p, o.origem)]);
      caixa.append(detalhes(`${x.conta.codigo} · ${x.conta.descricao} — saldo ${brl(x.saldo_contabil)} · pago ${brl(x.pagamentos_identificados)} · já contabilizado `
        + `${brl(x.ja_contabilizado)} · baixas ${brl(x.baixas_propostas)} · restante ${brl(x.saldo_restante)}`, false,
      tabela(["Classificação", "Documento", "Período", "Pagamento", "Valor", "Critérios / motivos", "Origem"], linhas)));
    });
    const f = c.folha;
    if (f) {
      caixa.append(detalhes(`${f.conta.codigo} · ${f.conta.descricao} — saldo ${brl(f.saldo_contabil)} · último líquido ${f.ultimo ? brl(f.ultimo.liquido) : "—"} · baixa ${brl(f.baixa)}`, false,
        el("p", "gestao-nota", "Retenções (INSS/IRRF) e pagamentos já lançados no razão foram identificados e NÃO são descontados de novo. Regularização por "
          + "POLÍTICA OPERACIONAL aprovada (não é pagamento individualmente comprovado)."),
        tabela(["Competência", "Bruto", "Retenções", "Pagamentos já lançados", "Outros débitos", "Líquido em aberto"],
          (f.competencias || []).map((x2) => [x2.competencia, brl(x2.bruto), brl(x2.retencoes), brl(x2.pagamentos), brl(x2.outros_debitos), brl(x2.liquido_em_aberto)])),
        f.ultimo ? el("p", null, "Último líquido: ") : el("span"), f.ultimo ? origemBotao(p, f.ultimo.origem) : el("span"),
        el("p", "gestao-nota", (f.motivos || []).join(" · "))));
    }
    return detalhes("Contas — abra uma conta para ver os pagamentos associados e a origem de cada valor", true, caixa);
  }
  function lancamentos(p) {
    const ls = p.conciliacao.lancamentos;
    return detalhes(`Lançamentos propostos (${ls.length}) — SIMULAÇÃO, nenhum efetivado`, false, tabela(["Status", "Data", "Débito", "Crédito", "Valor", "Histórico", "Evidência", "Origem"],
      ls.map((l) => [l.status === "PROPOSTO" ? "proposto" : `incompleto: ${(l.motivos_incompleto || []).join("; ")}`, dmy(l.data),
        l.debito ? `${l.debito.codigo} ${l.debito.descricao || ""}` : "—", l.credito ? `${l.credito.codigo} ${l.credito.descricao || ""}` : "—", brl(l.valor), l.historico,
        l.evidencia === "POLITICA_OPERACIONAL" ? "política operacional" : l.evidencia === "DOCUMENTO_EXTERNO" ? "e-CAC (externa)" : l.evidencia,
        origemBotao(p, { documento: l.documento, arquivo: l.arquivo, pagina: l.pagina })])));
  }
  function documentos(p) {
    return detalhes(`Documentos (${p.documentos.length}) — identificados pelo conteúdo`, false, tabela(["Documento", "Tipo", "Reconhecimento", "Leitor", "CNPJ", "Período/competência", "Emissão", "SHA-256", "Pendências de leitura"],
      p.documentos.map((d) => [origemBotao(p, { documento: d.id }), d.tipo.replace(/_/g, " ").toLowerCase(), d.reconhecimento, `${d.leitor || "—"}${d.situacao_leitor ? ` (${d.situacao_leitor.replace(/_/g, " ").toLowerCase()})` : ""}`,
        d.cnpj, d.periodo ? `${dmy(d.periodo.inicio)} a ${dmy(d.periodo.fim)}` : d.competencia, dmy(d.emissao), `${String(d.sha256).slice(0, 12)}…`, (d.pendencias || []).join(" · ") || "—"])));
  }
  function acao(p) {
    const b = el("div", "gestao-card cxn-acao");
    b.append(el("h2", null, "Ação necessária"));
    b.append(botao("Simular o TXT do Domínio (não grava arquivo)", async () => {
      const s = await api("GET", `/solicitacoes/${p.sol}/caixinha/simulacao-txt`);
      sim.replaceChildren(el("p", "gestao-mensagem", s.aviso), el("p", null, `${s.linhas.length} linha(s) · total ${brl(s.total)} · ${s.balanceado ? "balanceado por pagamento" : "NÃO balanceado"}`),
        el("pre", "gestao-json cxn-marca", [s.cabecalho, ...s.linhas.map((l) => l.linha)].join("\n")), ...(s.problemas.length ? [el("p", "gestao-mensagem", s.problemas.join("\n"))] : []));
    }));
    const sim = el("div");
    b.append(sim);
    if (p.estado === "FECHAMENTO_APROVADO") {
      b.append(el("p", null, `Aprovada em ${new Date(p.aprovacao.em).toLocaleString("pt-BR")} (SIMULAÇÃO). ${p.situacao_txt.texto || ""}`));
      if (p.situacao_txt.download) b.append(botao("Baixar TXT liberado (importação manual no Domínio)", () => baixar(`/solicitacoes/${p.sol}/txt-dominio`, `lanctos_${p.empresa}_${p.competencia}_${p.sol}.txt`)));
      if (!p.exportacao_permitida) b.append(el("p", "gestao-nota", "Empresa real: TXT bloqueado até a homologação do layout de partida simples no Domínio e uma autorização específica por empresa."));
      return b;
    }
    if (p.aprovacao_impedimentos.length) {
      b.append(el("p", "gestao-mensagem", "Aprovação ainda não é possível:"));
      const ul = el("ul");
      p.aprovacao_impedimentos.forEach((x) => ul.append(el("li", null, x)));
      b.append(ul);
      return b;
    }
    b.append(el("p", "gestao-nota", "Ao aprovar, só as baixas PROPOSTAS (completas) entram; itens em revisão ficam fora. Nada é escriturado; a importação no Domínio é manual."));
    const frase = campo(b, `Digite ${p.frase_aprovacao}`);
    const just = campo(b, "Justificativa");
    let cr = null, ce = null;
    if (p.aprovacao_exige_ciencia_revisao) {
      const l = el("label", "cxn-sel");
      cr = el("input"); cr.type = "checkbox";
      l.append(cr, el("span", null, ` Estou ciente de ${p.conciliacao.resumo.revisao} item(ns) em revisão que NÃO geram lançamento.`));
      b.append(l);
    }
    if (p.aprovacao_exige_ciencia_exportados.length) {
      const l = el("label", "cxn-sel");
      ce = el("input"); ce.type = "checkbox";
      l.append(ce, el("span", null, " Estou ciente de fatos já exportados em TXT revogado: " + p.aprovacao_exige_ciencia_exportados.join(" ")));
      b.append(l);
    }
    b.append(botao("Aprovar as baixas propostas", async () => {
      const corpoAp = { acao: "aprovar", frase: frase.value.trim(), justificativa: just.value.trim(), confirmado: true };
      if (cr) corpoAp.ciente_pendencias = cr.checked;
      if (ce) corpoAp.ciente_exportados = ce.checked;
      const r = await api("POST", `/solicitacoes/${p.sol}/aprovacao`, corpoAp);
      informar(`Aprovado (SIMULAÇÃO). ${(r.liberacao || {}).mensagem || ""}`);
      await painel(p.sol);
    }, "gestao-primario"));
    return b;
  }

  // ---------------------------------------------------------------- CONFIGURAÇÃO DA EMPRESA
  async function configurar(emp, comp) {
    const v = limpar(`Configurar Conciliação Caixinha · ${emp}`, "Rotina, contas (códigos reduzidos do plano DESTA empresa), tributos, datas e política da folha. "
      + "O sistema sugere pela descrição das contas; nada vale sem a sua confirmação com a frase exata.");
    const d = await api("GET", `/empresas/${emp}/caixinha?competencia=${comp || compAtual()}`);
    if (v !== versao) return;
    const rot = el("div", "gestao-card");
    rot.append(el("h2", null, "1. Rotina da empresa"), el("p", null, `Atual: ${d.tipo_rotina}${d.rotina && d.rotina.definida_em ? ` (definida em ${new Date(d.rotina.definida_em).toLocaleString("pt-BR")})` : ""}`));
    if (d.tipo_rotina !== "CAIXINHA") {
      const j = campo(rot, "Justificativa");
      rot.append(botao("Definir rotina CAIXINHA (empresa sem extrato bancário)", async () => {
        if (!window.confirm("Definir a rotina CAIXINHA? A habilitação do piloto é revogada e precisa ser refeita.")) return;
        await api("POST", `/empresas/${emp}/caixinha-rotina`, { rotina: "CAIXINHA", justificativa: j.value.trim(), confirmado: true });
        await configurar(emp, comp);
      }, "gestao-primario"));
      corpo.append(rot);
      return;
    }
    corpo.append(rot);
    const atual = (d.regras && d.regras.configuracao) || d.proposta_inicial.configuracao;
    const folhaAtual = (d.regras && d.regras.politica_folha) || d.proposta_inicial.politica_folha;
    const analiticas = d.plano.filter((c) => (c.tipo || "").toUpperCase().startsWith("ANAL"));
    const cfg = el("div", "gestao-card");
    cfg.append(el("h2", null, "2. Contas, tributos e datas"));
    const sel = {};
    Object.entries(d.contas_rotina).forEach(([k, rot2]) => {
      const s = campo(cfg, rot2 + (d.proposta_inicial.sugestoes[k] && d.proposta_inicial.sugestoes[k].sugerida ? ` (sugerida: ${d.proposta_inicial.sugestoes[k].sugerida})` : ""), "select");
      opcoes(s, [["", "— não se aplica / não definida —"], ...analiticas.map((c) => [c.codigo, `${c.codigo} · ${c.classificacao} · ${c.descricao} (${c.grupo || "sem grupo"})`])],
        (atual.contas || {})[k] || "");
      sel[k] = s;
    });
    const tribs = (atual.tributos || []).map((t) => {
      const i = campo(cfg, `Códigos de receita · ${t.chave.replace(/_/g, " ")} (separados por vírgula)`, "text", (t.codigos_receita || []).join(", "));
      return [t, i];
    });
    const pol = campo(cfg, "Data das baixas tributárias", "select");
    opcoes(pol, [["", "— defina —"], ...Object.entries(d.politicas_datas)], (atual.politica_datas || {}).tributos || "");
    const janela = campo(cfg, "Janela (dias) para reconhecer baixa já contabilizada no razão", "number", (atual.criterios_baixa || {}).janela_dias_baixa_razao ?? 3);
    const desde = campo(cfg, "Vigência a partir de (competência)", "month", atual.competencia_desde || comp);
    const situ = d.regras && d.regras.configuracao ? `${d.regras.configuracao.situacao} · versão ${d.regras.configuracao.versao}` : "não gravada";
    cfg.append(el("p", "gestao-nota", `Situação: ${situ}. ${d.avaliacao.configuracao && d.avaliacao.configuracao.aplicavel ? "Aplicável na competência." : (d.avaliacao.configuracao || {}).motivo || ""}`));
    corpo.append(cfg);
    const fol = el("div", "gestao-card");
    fol.append(el("h2", null, "3. Política da folha (pró-labore)"), el("p", "gestao-nota", "Manter em aberto somente o líquido da última competência da folha; "
      + "as competências anteriores são baixadas como REGULARIZAÇÃO CONFORME POLÍTICA CAIXINHA. Exige aprovação PRÉVIA e data definida."));
    const dpol = campo(fol, "Data da regularização", "select");
    opcoes(dpol, [["", "— defina —"], ...Object.entries(d.politicas_folha)], (folhaAtual.data_lancamento || {}).politica || "");
    const dfixa = campo(fol, "Data fixa (somente DATA_FIXA)", "date", (folhaAtual.data_lancamento || {}).data || "");
    const fdesde = campo(fol, "Vigência a partir de (competência)", "month", folhaAtual.competencia_desde || comp);
    const fsitu = d.regras && d.regras.politica_folha ? `${d.regras.politica_folha.situacao} · versão ${d.regras.politica_folha.versao}` : "não gravada";
    fol.append(el("p", "gestao-nota", `Situação: ${fsitu}.`));
    corpo.append(fol);
    const salvar = el("div", "gestao-card");
    salvar.append(el("h2", null, "4. Gravar como PROPOSTA"), el("p", "gestao-nota", "Gravar cria uma nova versão (a anterior fica preservada) e NÃO aprova nada."));
    salvar.append(botao("Gravar proposta", async () => {
      const contasCfg = {};
      Object.entries(sel).forEach(([k, s]) => { contasCfg[k] = s.value || null; });
      const tributos = tribs.map(([t, i]) => Object.assign({}, t, { codigos_receita: i.value.split(",").map((x) => x.trim()).filter(Boolean) }));
      const dl = { politica: dpol.value || null };
      if (dpol.value === "DATA_FIXA") dl.data = dfixa.value;
      const r = await api("POST", `/empresas/${emp}/caixinha-regras`, { confirmado: true,
        configuracao: { contas: contasCfg, tributos, politica_datas: { tributos: pol.value || null }, criterios_baixa: { janela_dias_baixa_razao: Number(janela.value), exigir_provisao_identificada: true },
          competencia_desde: desde.value, competencia_ate: null },
        politica_folha: { regra: "MANTER_ULTIMO_LIQUIDO", conta: "PRO_LABORE", data_lancamento: dl, competencia_desde: fdesde.value,
          competencia_ate: dpol.value === "DATA_FIXA" ? fdesde.value : null } });
      informar(r.resultado === "SEM_ALTERACAO" ? "Nada mudou." : r.aviso);
      await configurar(emp, comp);
    }, "gestao-primario"));
    corpo.append(salvar);
    const apr = el("div", "gestao-card");
    apr.append(el("h2", null, "5. Confirmação do Supervisor (frase exata)"));
    Object.entries(d.frases).forEach(([chave, f]) => {
      const reg = d.regras && d.regras[chave === "CONFIGURACAO" ? "configuracao" : "politica_folha"];
      if (!reg || reg.situacao !== "PROPOSTA") return;
      const i = campo(apr, `Digite ${f}`);
      apr.append(botao(`Confirmar ${chave === "CONFIGURACAO" ? "configuração" : "política da folha"} (versão ${reg.versao})`, async () => {
        await api("POST", `/empresas/${emp}/caixinha-aprovar`, { chave, frase: i.value.trim(), confirmado: true });
        informar("Regra confirmada. Conciliações que usaram a versão anterior ficam desatualizadas.");
        await configurar(emp, comp);
      }));
    });
    if (!apr.querySelector("button")) apr.append(el("p", "nd", "Nada aguardando confirmação."));
    corpo.append(apr);
    const pil = el("div", "gestao-card");
    pil.append(el("h2", null, "6. Piloto em SIMULAÇÃO"), el("p", null, d.caixinha_autorizada ? "Conciliação Caixinha habilitada (SIMULAÇÃO)." : "Ainda não habilitada."));
    if (!d.caixinha_autorizada) {
      const i = campo(pil, `Digite ${d.frase_piloto}`);
      pil.append(botao("Habilitar piloto (exige plano e conta Caixa Geral; não exige vínculo bancário)", async () => {
        await api("POST", `/empresas/${emp}/piloto`, { frase: i.value.trim() });
        await configurar(emp, comp);
      }));
    }
    corpo.append(pil, botao("Voltar", () => inicio(comp)));
  }

  window.EV.caixinha = { inicio, painel, configurar };
})();
