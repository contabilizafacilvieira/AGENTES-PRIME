/*
 * CENTRAL DE REVISÃO DO SUPERVISOR — conciliação financeira banco × relatório.
 * Só no modo operação local (token de sessão na página). A tela NÃO decide nada: estados, contagens e bloqueios vêm prontos
 * do servidor (lógica central em decisoes_conciliacao.py). Tudo é exibido com textContent; nenhum JSON aparece ao usuário.
 *
 * Abrir:  EV.central.abrirDemonstracao()  ·  EV.central.abrirSolicitacao("SOL-AAAA-NNNNNN")  ·  ?central=demonstracao
 */
(function () {
  "use strict";
  const meta = document.querySelector('meta[name="prime-sessao"]');
  if (!meta || !meta.content || !window.EV) return;
  const TOKEN = meta.content;

  function el(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined && texto !== null) e.textContent = String(texto);
    return e;
  }
  function botao(texto, classe, fn) {
    const b = el("button", classe || "cr-botao", texto);
    b.type = "button";
    if (fn) b.addEventListener("click", fn);
    return b;
  }
  async function api(metodo, rota, corpo) {
    let r;
    try {
      r = await fetch("/api" + rota, {
        method: metodo, cache: "no-store", credentials: "same-origin",
        headers: Object.assign({ "X-Prime-Sessao": TOKEN }, corpo !== undefined ? { "Content-Type": "application/json" } : {}),
        body: corpo === undefined ? undefined : JSON.stringify(corpo)
      });
    } catch (_) {
      throw Object.assign(new Error("Não foi possível falar com o aplicativo. Confira se o servidor local está em execução."), { codigo: "REDE" });
    }
    const dados = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(dados.erro || `Não foi possível concluir (erro ${r.status}).`), { codigo: dados.codigo || "" });
    return dados;
  }
  const fmtValor = (v) => (v === null || v === undefined || v === "" ? "—"
    : Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }));
  const fmtData = (d) => (d && /^\d{4}-\d{2}-\d{2}/.test(d) ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : "—");
  const fmtHora = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "");
  const plural = (n, s, p) => `${n} ${n === 1 ? s : p}`;
  const NATUREZA = { ENTRADA: "Entrada", SAIDA: "Saída" };

  // ---------------------------------------------------------------- estrutura
  const raiz = el("section", "cr");
  raiz.hidden = true;
  raiz.setAttribute("role", "dialog");
  raiz.setAttribute("aria-label", "Central de Revisão da conciliação financeira");
  const topo = el("header", "cr-topo");
  const voltar = botao("← Voltar", "cr-botao cr-voltar", () => fechar());
  const titulos = el("div", "cr-titulos");
  const h1 = el("h1", "cr-h1", "Conciliação financeira");
  const sub = el("p", "cr-sub");
  titulos.append(h1, sub);
  const selo = el("span", "cr-selo-demo", "DEMONSTRAÇÃO · dados 100% fictícios");
  const atualizarB = botao("Atualizar", "cr-botao", () => carregar());
  const reiniciarB = botao("Reiniciar demonstração", "cr-botao cr-botao-sec", () => pedirReinicio());
  topo.append(voltar, titulos, selo, atualizarB, reiniciarB);
  const msg = el("p", "cr-msg");
  msg.setAttribute("role", "status");
  msg.setAttribute("aria-live", "polite");
  const conteudo = el("div", "cr-conteudo");
  raiz.append(topo, msg, conteudo);

  const camadaDetalhe = el("div", "cr-camada");
  camadaDetalhe.hidden = true;
  const detalhe = el("section", "cr-detalhe");
  detalhe.setAttribute("role", "dialog");
  detalhe.setAttribute("aria-label", "Detalhe da associação");
  camadaDetalhe.append(detalhe);
  const camadaConfirmar = el("div", "cr-camada cr-camada-confirmar");
  camadaConfirmar.hidden = true;
  const confirmar = el("section", "cr-confirmar");
  confirmar.setAttribute("role", "alertdialog");
  confirmar.setAttribute("aria-label", "Confirmar decisão");
  camadaConfirmar.append(confirmar);
  raiz.append(camadaDetalhe, camadaConfirmar);
  document.body.append(raiz);

  const estado = { base: null, visao: null, filtro: "todos", natureza: "", selecionados: new Set(), aberto: null };

  function aviso(texto, tipo) {
    msg.textContent = texto || "";
    msg.dataset.tipo = tipo || "";
  }

  // ---------------------------------------------------------------- abrir / fechar / carregar
  async function abrir(base) {
    estado.base = base;
    estado.filtro = "todos";
    estado.natureza = "";
    estado.selecionados.clear();
    raiz.hidden = false;
    document.body.classList.add("cr-aberta");
    aviso("");
    await carregar();
    voltar.focus();
  }
  function fechar() {
    raiz.hidden = true;
    camadaDetalhe.hidden = true;
    camadaConfirmar.hidden = true;
    document.body.classList.remove("cr-aberta");
  }
  async function carregar(manterMensagem) {
    conteudo.replaceChildren(el("p", "cr-carregando", "Carregando a conciliação…"));
    try {
      const v = await api("GET", estado.base);
      if (!v.disponivel) {
        conteudo.replaceChildren(el("p", "cr-indisponivel", v.motivo || "Conciliação financeira indisponível."));
        return;
      }
      aplicarVisao(v);
      if (!manterMensagem) aviso("");
    } catch (e) {
      conteudo.replaceChildren(el("p", "cr-indisponivel", e.message));
    }
  }
  function aplicarVisao(v) {
    estado.visao = v;
    const validos = new Set(v.itens.filter((i) => i.selecionavel_lote).map((i) => i.id));
    [...estado.selecionados].forEach((id) => { if (!validos.has(id)) estado.selecionados.delete(id); });
    renderizar();
  }

  // ---------------------------------------------------------------- tela principal
  const FILTROS = [["todos", "Todos"], ["revisar", "Para revisar"], ["conciliados", "Conciliados"], ["ambiguos", "Ambíguos"],
    ["nao", "Não conciliados"], ["aprovados", "Aprovados por mim"], ["rejeitados", "Rejeitados"]];
  const PASSA = {
    todos: () => true, revisar: (i) => i.status === "REVISAR", conciliados: (i) => i.status === "CONCILIADO",
    ambiguos: (i) => i.status === "AMBIGUO", nao: (i) => i.status === "NAO_CONCILIADO",
    aprovados: (i) => i.status === "APROVADO", rejeitados: (i) => i.status === "REJEITADO"
  };

  function renderizar() {
    const v = estado.visao;
    const r = v.resumo;
    h1.textContent = v.rotulo;
    sub.textContent = `${v.titulo}`;
    selo.hidden = !v.demonstracao;
    reiniciarB.hidden = !v.demonstracao;
    raiz.classList.toggle("cr-demo", !!v.demonstracao);
    conteudo.replaceChildren();

    if (v.acoes_bloqueadas) conteudo.append(el("p", "cr-erro-fixo", v.aviso_corrompido));

    const cards = el("div", "cr-cards");
    [["conciliados", r.conciliados_automaticamente, "Conciliados automaticamente", "ok"],
      ["revisar", r.para_revisar, "Precisam da sua revisão", "atencao"],
      ["ambiguos", r.ambiguos, "Ambíguos", "atencao"],
      ["nao", r.nao_conciliados, "Não conciliados", "bloqueio"],
      ["bloqueios", r.bloqueios_restantes, "Bloqueios restantes", r.bloqueios_restantes ? "bloqueio" : "ok"]
    ].forEach(([chave, n, rotulo, tom]) => {
      const c = botao("", `cr-card cr-${tom}`, () => { if (chave !== "bloqueios") { estado.filtro = chave; renderizar(); } });
      c.dataset.card = chave;
      c.append(el("strong", "cr-card-n", n), el("span", "cr-card-rotulo", rotulo));
      if (chave === "bloqueios") c.disabled = true;
      cards.append(c);
    });
    conteudo.append(cards);

    const prog = el("div", "cr-progresso");
    const barra = el("div", "cr-barra");
    barra.setAttribute("role", "progressbar");
    barra.setAttribute("aria-valuemin", "0");
    barra.setAttribute("aria-valuemax", "100");
    barra.setAttribute("aria-valuenow", String(r.percentual_confirmado));
    barra.setAttribute("aria-label", "Movimentações do banco com associação confirmada");
    const preench = el("span", "cr-barra-cheia");
    preench.style.width = `${r.percentual_confirmado}%`;
    barra.append(preench);
    prog.append(barra, el("p", "cr-progresso-texto",
      `${r.movimentos_confirmados} de ${plural(r.movimentos_bancarios, "movimentação do banco", "movimentações do banco")} com associação confirmada (${r.percentual_confirmado}%)`
      + (r.aprovados_supervisor ? ` · ${plural(r.aprovados_supervisor, "aprovada", "aprovadas")} por você` : "")
      + (r.rejeitados ? ` · ${plural(r.rejeitados, "rejeitada", "rejeitadas")}` : "")));
    conteudo.append(prog);

    const imp = el("div", r.bloqueios_restantes ? "cr-impede cr-impede-sim" : "cr-impede cr-impede-nao");
    imp.dataset.bloqueios = String(r.bloqueios_restantes);
    if (r.bloqueios_restantes) {
      imp.append(el("p", "cr-impede-titulo", `✕ ${plural(r.bloqueios_restantes, "movimentação ainda impede", "movimentações ainda impedem")} o avanço.`));
      const p = v.pendencia_bloqueio;
      imp.append(pio(p.problema, p.impacto, p.o_que_fazer));
      // rede de segurança: TODO movimento que impede o avanço, um por linha, independente do filtro
      const ver = el("details", "cr-ver-bloqueios");
      ver.append(el("summary", null, `Ver bloqueios (${(v.bloqueios_lista || []).length})`));
      const ul = el("ul", "cr-bloqueios-lista");
      (v.bloqueios_lista || []).forEach((b) => {
        const li = el("li", "cr-bloqueio-item");
        li.dataset.associacao = b.associacao;
        li.append(el("strong", null, `${fmtData(b.data)} · ${NATUREZA[b.natureza] || "—"} · ${fmtValor(b.valor)} · ${b.descricao || "—"}`),
          el("p", "cr-suave", `Classificação do sistema: ${CLASSE[b.classificacao_motor] || b.classificacao_motor} · Situação: ${b.situacao}`),
          pio(b.problema, b.impacto, b.o_que_fazer), el("p", "cr-nota", `Ação disponível: ${b.acao}`));
        const ab = botao("Abrir", "cr-botao cr-abrir-bloqueio", () => abrirDetalhe(b.associacao));
        li.append(ab);
        ul.append(li);
      });
      ver.append(ul);
      imp.append(ver);
    } else {
      imp.append(el("p", "cr-impede-titulo", "✓ Nenhuma movimentação do banco impede o avanço por falta de associação."));
    }
    conteudo.append(imp);
    conteudo.append(el("p", "cr-nota", v.aviso_efeito));

    // filtros
    const filtros = el("div", "cr-filtros");
    filtros.setAttribute("role", "toolbar");
    filtros.setAttribute("aria-label", "Filtros");
    FILTROS.forEach(([id, rotulo]) => {
      const n = v.itens.filter(PASSA[id]).length;
      const b = botao(`${rotulo} (${n})`, "cr-filtro", () => { estado.filtro = id; renderizar(); });
      b.dataset.filtro = id;
      b.setAttribute("aria-pressed", String(estado.filtro === id));
      filtros.append(b);
    });
    const nat = el("select", "cr-natureza");
    nat.setAttribute("aria-label", "Entradas ou saídas");
    [["", "Entradas e saídas"], ["ENTRADA", "Só entradas"], ["SAIDA", "Só saídas"]].forEach(([val, t]) => {
      const o = el("option", null, t);
      o.value = val;
      nat.append(o);
    });
    nat.value = estado.natureza;
    nat.addEventListener("change", () => { estado.natureza = nat.value; renderizar(); });
    filtros.append(nat);
    conteudo.append(filtros);

    // barra contextual do lote
    const lote = el("div", "cr-lote");
    lote.hidden = !estado.selecionados.size;
    lote.append(el("span", "cr-lote-n", `${plural(estado.selecionados.size, "selecionado", "selecionados")}`),
      botao("Confirmar selecionados", "cr-botao cr-pri", () => pedirLote()),
      botao("Limpar seleção", "cr-botao cr-botao-sec", () => { estado.selecionados.clear(); renderizar(); }));
    conteudo.append(lote);

    // lista
    const itens = v.itens.filter(PASSA[estado.filtro]).filter((i) => !estado.natureza || i.natureza === estado.natureza);
    const selecionaveis = itens.filter((i) => i.selecionavel_lote && !v.acoes_bloqueadas);
    if (selecionaveis.length) {
      const todos = el("label", "cr-sel-todos");
      const cb = el("input");
      cb.type = "checkbox";
      cb.checked = selecionaveis.every((i) => estado.selecionados.has(i.id));
      cb.addEventListener("change", () => {
        selecionaveis.forEach((i) => (cb.checked ? estado.selecionados.add(i.id) : estado.selecionados.delete(i.id)));
        renderizar();
      });
      todos.append(cb, el("span", null, `Selecionar todos os prováveis desta lista (${selecionaveis.length})`));
      conteudo.append(todos);
    }
    const lista = el("ul", "cr-lista");
    if (!itens.length) lista.append(el("li", "cr-vazio", "Nenhum item neste filtro."));
    itens.forEach((i) => lista.append(linha(i, v.acoes_bloqueadas)));
    conteudo.append(lista);

    // histórico (sob demanda)
    const hist = el("details", "cr-historico");
    hist.append(el("summary", null, "Histórico de decisões"));
    const corpoHist = el("div", "cr-hist-corpo");
    hist.append(corpoHist);
    hist.addEventListener("toggle", () => { if (hist.open) carregarHistorico(corpoHist); });
    conteudo.append(hist);
  }

  function pio(problema, impacto, oQueFazer) {
    const d = el("dl", "cr-pio");
    [["Problema", problema], ["Impacto", impacto], ["O que fazer", oQueFazer]].forEach(([t, x]) => d.append(el("dt", null, t), el("dd", null, x)));
    return d;
  }
  function seloStatus(i) {
    const s = el("span", `cr-status cr-${i.tom}`);
    s.append(el("span", "cr-status-icone", i.icone), el("span", null, i.status_rotulo));
    s.dataset.status = i.status;
    return s;
  }
  function resumoLado(linhas, lado, item) {
    const c = el("div", "cr-lado");
    c.append(el("span", "cr-lado-titulo", lado === "banco" ? "Banco" : "Relatório"));
    if (lado === "relatorio" && item.status === "AMBIGUO") {
      c.append(el("span", "cr-lado-linha", item.parcial ? `${item.movimentos_resolvidos} de ${item.movimentos_total} movimentos resolvidos — revise o restante`
        : `${item.candidatos_quantidade} candidatos — escolha um`), el("span", "cr-lado-valor", fmtValor(linhas[0] && linhas[0].valor)));
      return c;
    }
    if (!linhas.length) {
      c.append(el("span", "cr-lado-linha cr-suave", lado === "banco" ? "Sem movimento no banco" : "Nenhum registro associado"));
      return c;
    }
    const x = linhas[0];
    const texto = lado === "banco" ? x.descricao : (x.contraparte || x.descricao);
    c.append(el("span", "cr-lado-linha", `${fmtData(x.data)} · ${texto || "—"}`),
      el("span", "cr-lado-valor", fmtValor(lado === "banco" ? item.valor_banco : item.valor_relatorio)));
    if (linhas.length > 1) c.append(el("span", "cr-lado-extra", `+ ${plural(linhas.length - 1, "outro registro", "outros registros")} (soma)`));
    return c;
  }
  function linha(i, bloqueado) {
    const li = el("li", `cr-item cr-item-${i.tom}`);
    li.dataset.id = i.id;
    li.dataset.status = i.status;
    li.dataset.natureza = i.natureza;
    const sel = el("div", "cr-item-sel");
    if (i.selecionavel_lote && !bloqueado) {
      const cb = el("input");
      cb.type = "checkbox";
      cb.className = "cr-check";
      cb.checked = estado.selecionados.has(i.id);
      cb.setAttribute("aria-label", "Selecionar para confirmação em lote");
      cb.addEventListener("change", () => { cb.checked ? estado.selecionados.add(i.id) : estado.selecionados.delete(i.id); renderizar(); });
      sel.append(cb);
    }
    const abrirB = botao("Abrir", "cr-botao cr-abrir", () => abrirDetalhe(i.id));
    li.append(sel, resumoLado(i.banco, "banco", i), el("span", "cr-seta", "↔"), resumoLado(i.relatorio, "relatorio", i), seloStatus(i), abrirB);
    return li;
  }

  async function carregarHistorico(alvo) {
    alvo.replaceChildren(el("p", "cr-suave", "Carregando…"));
    try {
      const h = await api("GET", estado.base + "/historico");
      alvo.replaceChildren();
      if (!h.disponivel) { alvo.append(el("p", "cr-erro-fixo", h.motivo)); return; }
      if (!h.grupos.length) { alvo.append(el("p", "cr-suave", "Nenhuma decisão registrada ainda.")); return; }
      const t = el("table", "cr-tabela-hist");
      const cab = el("tr");
      ["Data/hora", "Responsável", "Ação", "Quantidade", "Justificativa", ""].forEach((x) => cab.append(el("th", null, x)));
      t.append(cab);
      h.grupos.forEach((g) => {
        const tr = el("tr", "cr-hist-linha");
        tr.append(el("td", null, fmtHora(g.em)), el("td", null, g.responsavel), el("td", null, g.acao), el("td", null, g.quantidade),
          el("td", null, g.justificativa));
        const td = el("td");
        const det = el("details");
        det.append(el("summary", null, "Detalhes"));
        const ul = el("ul", "cr-hist-itens");
        g.itens.forEach((x) => ul.append(el("li", null,
          `${x.acao} · motor: ${CLASSE[x.classificacao_motor] || x.classificacao_motor} · antes: ${ESTADO[x.estado_anterior] || x.estado_anterior} · depois: ${ESTADO[x.estado_posterior] || x.estado_posterior}${x.candidato_escolhido ? " · candidato escolhido" : ""}`)));
        det.append(ul);
        td.append(det);
        tr.append(td);
        t.append(tr);
      });
      alvo.append(t);
    } catch (e) {
      alvo.replaceChildren(el("p", "cr-erro-fixo", e.message));
    }
  }
  const CLASSE = { CONCILIADO: "Conciliado", PROVAVEL: "Provável", AMBIGUO: "Ambíguo", NAO_CONCILIADO: "Não conciliado" };
  const ESTADO = {
    ASSOCIACAO_CONFIRMADA_AUTOMATICAMENTE: "confirmada automaticamente", ASSOCIACAO_CONFIRMADA_PELO_SUPERVISOR: "confirmada pelo Supervisor",
    AGUARDANDO_SUPERVISOR: "aguardando o Supervisor", ASSOCIACAO_REJEITADA: "rejeitada", SEM_ASSOCIACAO: "sem associação"
  };

  // ---------------------------------------------------------------- detalhe
  function tabelaLado(titulo, linhas, lado) {
    const s = el("div", "cr-coluna");
    s.append(el("h3", "cr-coluna-titulo", titulo));
    if (!linhas.length) s.append(el("p", "cr-suave", lado === "banco" ? "Sem movimento no banco." : "Nenhum registro associado."));
    linhas.forEach((x) => {
      const d = el("dl", "cr-ficha");
      const campos = lado === "banco"
        ? [["Data", fmtData(x.data)], ["Valor", fmtValor(x.valor)], ["Natureza", NATUREZA[x.natureza] || "—"], ["Descrição", x.descricao || "—"], ["Documento", x.documento || "—"]]
        : [["Data", fmtData(x.data)], ["Valor", fmtValor(x.valor)], ["Natureza", NATUREZA[x.natureza] || "—"], ["Contraparte", x.contraparte || "—"],
          ["Descrição", x.descricao || "—"], ["Documento", x.documento || "—"]].concat(x.documento_contraparte ? [["CPF/CNPJ (parcial)", x.documento_contraparte]] : []);
      campos.forEach(([k, val]) => d.append(el("dt", null, k), el("dd", null, val)));
      s.append(d);
    });
    return s;
  }
  function explicacao(itens) {
    const ul = el("ul", "cr-porque");
    itens.forEach((x) => {
      const li = el("li", x.ok ? "cr-ok-item" : "cr-aviso-item");
      li.append(el("span", "cr-porque-icone", x.ok ? "✓" : "⚠"), el("span", null, x.texto));
      ul.append(li);
    });
    return ul;
  }
  function campoJustificativa(inicial, exemplo) {
    const l = el("label", "cr-justificativa");
    l.append(el("span", null, "Justificativa da decisão (obrigatória)"));
    const t = el("textarea");
    t.rows = 2;
    t.maxLength = 500;
    t.value = inicial || "";
    t.placeholder = exemplo || "Ex.: conferi data, valor e favorecido no comprovante.";
    l.append(t);
    return [l, t];
  }

  async function abrirDetalhe(id, mensagem) {
    estado.aberto = id;
    camadaDetalhe.hidden = false;
    detalhe.replaceChildren(el("p", "cr-carregando", "Carregando…"));
    let d;
    try {
      d = await api("GET", `${estado.base}/${id}`);
    } catch (e) {
      detalhe.replaceChildren(el("p", "cr-erro-fixo", e.message), botao("Fechar", "cr-botao", fecharDetalhe));
      return;
    }
    detalhe.replaceChildren();
    const cab = el("div", "cr-det-cab");
    cab.append(el("h2", "cr-det-titulo", "Banco × relatório"), seloStatus(d), botao("✕", "cr-fechar", fecharDetalhe));
    cab.lastChild.setAttribute("aria-label", "Fechar detalhe");
    detalhe.append(cab);
    const erroDet = el("p", "cr-msg cr-msg-det");
    erroDet.setAttribute("role", "status");
    if (mensagem) { erroDet.textContent = mensagem; erroDet.dataset.tipo = "erro"; }
    detalhe.append(erroDet);
    if (d.cardinalidade && !["1x1", "1x0", "0x1"].includes(d.cardinalidade) && d.status !== "AMBIGUO") {
      detalhe.append(el("p", "cr-agrupamento", `Agrupamento: ${plural(d.banco.length, "movimento no banco", "movimentos no banco")} ↔ ${plural(d.relatorio.length, "registro no relatório", "registros no relatório")} (a soma fecha exatamente).`));
    }
    const grade = el("div", "cr-grade");
    grade.append(tabelaLado("MOVIMENTO NO BANCO", d.banco, "banco"));
    let escolhido = null;
    if (d.status === "AMBIGUO" || (d.classificacao_motor === "AMBIGUO" && d.candidatos.length)) {
      const col = el("div", "cr-coluna");
      col.append(el("h3", "cr-coluna-titulo", "CANDIDATOS NO RELATÓRIO"));
      const grupo = el("div", "cr-candidatos");
      grupo.setAttribute("role", "radiogroup");
      grupo.setAttribute("aria-label", "Candidatos");
      d.candidatos.forEach((c) => {
        const card = el("label", "cr-candidato" + (c.escolhido ? " cr-candidato-escolhido" : ""));
        card.dataset.candidato = String(c.numero);
        if (d.acoes.escolher_candidato && c.disponivel) {
          const r = el("input");
          r.type = "radio";
          r.name = "cr-candidato";
          r.addEventListener("change", () => { escolhido = c; atualizarBotoes(); });
          card.append(r);
        }
        const corpo = el("div");
        corpo.append(el("strong", null, `Candidato ${c.numero}${c.escolhido ? " — escolhido pelo Supervisor" : ""}`));
        if (!c.escolhido && !c.disponivel && d.parcial) corpo.append(el("p", "cr-manual-alerta", "Indisponível: usa movimento ou registro já confirmado em outra escolha."));
        c.relatorio.forEach((x) => corpo.append(el("p", "cr-cand-linha", `${fmtData(x.data)} · ${x.contraparte || x.descricao || "—"} · ${x.descricao && x.contraparte ? x.descricao + " · " : ""}${fmtValor(x.valor)}`)));
        if (c.banco.length > 1 || d.banco.length > 1) c.banco.forEach((x) => corpo.append(el("p", "cr-cand-linha cr-suave", `Banco: ${fmtData(x.data)} · ${x.descricao} · ${fmtValor(x.valor)}`)));
        corpo.append(explicacao(c.explicacao));
        if (c.pontuacao !== null && c.pontuacao !== undefined) corpo.append(el("p", "cr-pontuacao", `Pontuação de referência: ${c.pontuacao} (só ajuda a ordenar; quem decide são as regras)`));
        if (c.escolhido && c.escolha_evento && d.acoes.desfazer_escolha) {
          const desf = botao("Desfazer esta escolha", "cr-botao cr-botao-sec", (e) => { e.preventDefault(); pedirIndividual(d, "REVOGADO", null, "", c.escolha_evento); });
          desf.dataset.acao = "desfazer-escolha";
          corpo.append(desf);
        }
        card.append(corpo);
        grupo.append(card);
      });
      if (d.aviso_candidatos) col.append(el("p", "cr-manual-aviso cr-aviso-candidatos", d.aviso_candidatos));
      col.append(grupo);
      grade.append(col);
    } else {
      grade.append(tabelaLado("REGISTRO NO RELATÓRIO", d.relatorio, "relatorio"));
    }
    detalhe.append(grade);

    if (d.explicacao.length) {
      const sec = el("section", "cr-secao");
      sec.append(el("h3", "cr-secao-titulo", "POR QUE O SISTEMA SUGERIU?"), explicacao(d.explicacao));
      if (d.pontuacao !== null && d.pontuacao !== undefined) sec.append(el("p", "cr-pontuacao", `Pontuação de referência: ${d.pontuacao} (informação secundária: só ajuda a ordenar; quem decide são as regras)`));
      detalhe.append(sec);
    }
    if (d.pendencia) {
      const sec = el("section", "cr-secao cr-secao-pio");
      sec.append(pio(d.pendencia.problema, d.pendencia.impacto, d.pendencia.o_que_fazer));
      detalhe.append(sec);
    }
    if (d.decisao) {
      detalhe.append(el("p", "cr-decisao-atual", `Decisão vigente: ${d.decisao.acao} em ${fmtHora(d.decisao.em)} por ${d.decisao.responsavel}. Justificativa: ${d.decisao.justificativa}. Classificação do sistema mantida: ${CLASSE[d.classificacao_motor]}.`));
    }

    // ações (somente as que o servidor permite)
    const acoes = el("section", "cr-acoes");
    const [rotJust, just] = campoJustificativa("");
    const bConf = botao("Confirmar associação", "cr-botao cr-pri", () => pedirIndividual(d, "APROVADO", null, just.value));
    const bCand = botao("Confirmar candidato selecionado", "cr-botao cr-pri", () => pedirIndividual(d, "APROVADO", escolhido, just.value));
    const bRej = botao(d.classificacao_motor === "AMBIGUO" ? "Rejeitar todos os candidatos" : "Rejeitar", "cr-botao cr-rejeitar",
      () => pedirIndividual(d, "REJEITADO", null, just.value));
    const bDesf = botao("Desfazer decisão", "cr-botao cr-botao-sec", () => pedirIndividual(d, "REVOGADO", null, just.value));
    const bObs = botao("Registrar observação", "cr-botao cr-botao-sec", () => pedirIndividual(d, "OBSERVACAO", null, just.value));
    const painelManual = el("section", "cr-secao cr-manual");
    painelManual.hidden = true;
    const bBusca = botao("Buscar registros no relatório", "cr-botao cr-pri", () => { bBusca.disabled = true; abrirBusca(d, painelManual); });
    bBusca.dataset.acao = "buscar-manual";
    function atualizarBotoes() { bCand.disabled = !escolhido; }
    atualizarBotoes();
    const linhaB = el("div", "cr-acoes-botoes");
    if (d.acoes.confirmar) linhaB.append(bConf);
    if (d.acoes.escolher_candidato) linhaB.append(bCand);
    if (d.acoes.rejeitar) linhaB.append(bRej);
    if (d.acoes.desfazer) linhaB.append(bDesf);
    if (d.acoes.buscar_manual) linhaB.append(bBusca);
    if (d.acoes.observacao) linhaB.append(bObs);
    if (d.status === "CONCILIADO") acoes.append(el("p", "cr-auto", "✓ Conciliado automaticamente. Não precisa da sua aprovação."));
    if (d.status === "NAO_CONCILIADO") acoes.append(el("p", "cr-sem", "Não encontramos associação segura automaticamente. Se conseguir comprovar, "
      + "busque os registros no relatório e confirme uma associação manual; senão, registre uma observação."));
    if (d.status === "RELATORIO_ASSOCIADO_MANUAL") acoes.append(el("p", "cr-auto", "✓ Este registro do relatório já foi usado numa associação manual confirmada."));
    if (d.status === "RELATORIO_SEM_BANCO") acoes.append(el("p", "cr-sem", "Registro do relatório sem movimento no banco. Não há o que confirmar aqui."));
    if (linhaB.childNodes.length) acoes.append(rotJust, linhaB);
    detalhe.append(acoes, painelManual);

    if (d.historico.length) {
      const h = el("details", "cr-secao");
      h.append(el("summary", null, `Histórico desta associação (${d.historico.length})`));
      const ul = el("ul", "cr-hist-itens");
      d.historico.forEach((x) => ul.append(el("li", null, `${fmtHora(x.em)} · ${x.responsavel} · ${x.acao} · ${x.justificativa}`)));
      h.append(ul);
      detalhe.append(h);
    }
    detalhe.append(el("p", "cr-nota", d.aviso_efeito));
    detalhe.dataset.id = d.id;
    detalhe.dataset.status = d.status;
    estado.detalheAtual = d;
    (d.acoes.confirmar ? bConf : d.acoes.escolher_candidato ? detalhe.querySelector("input[type=radio]") || bCand : cab.lastChild).focus();
  }
  // ---------------------------------------------------------------- associação manual assistida (NAO_CONCILIADO)
  const centavos = (v) => Math.round(parseFloat(v) * 100);
  const reais = (c) => fmtValor((c / 100).toFixed(2));
  async function abrirBusca(d, alvo) {
    alvo.hidden = false;
    alvo.replaceChildren(el("p", "cr-carregando", "Buscando registros no relatório…"));
    let b;
    try {
      b = await api("GET", `${estado.base}/${d.id}/busca-manual`);
    } catch (e) {
      alvo.replaceChildren(el("p", "cr-erro-fixo", e.message));
      return;
    }
    if (!b.disponivel) { alvo.replaceChildren(el("p", "cr-erro-fixo", b.motivo)); return; }
    const sel = new Set();
    const porId = Object.fromEntries(b.candidatos.map((c) => [c.id, c]));
    const alvoC = centavos(b.valor_banco);
    alvo.replaceChildren(el("h3", "cr-secao-titulo", "REGISTROS DO RELATÓRIO PARA ASSOCIAÇÃO MANUAL"),
      el("p", "cr-nota", `Movimento no banco: ${fmtData(b.banco.data)} · ${b.banco.descricao || "—"} · ${fmtValor(b.valor_banco)}. `
        + `Selecione de 1 a ${b.limite_manual} registros cuja soma seja exatamente o valor do banco.`));
    const linhaRegistro = (c) => `${fmtData(c.data)} (${c.dias === null ? "sem data" : plural(c.dias, "dia", "dias") + " do banco"}) · `
      + `${c.contraparte || c.descricao || "—"}${c.descricao && c.contraparte ? " · " + c.descricao : ""}${c.documento ? " · doc. " + c.documento : ""} · ${fmtValor(c.valor)}`;
    // combinações sugeridas (nenhuma é escolhida pelo sistema)
    const sCombo = el("div", "cr-manual-combos");
    if (b.combinacoes.length) {
      sCombo.append(el("p", "cr-manual-aviso", b.combinacoes.length > 1
        ? `Encontramos ${b.combinacoes.length} combinações possíveis. O sistema não escolhe: confira e selecione uma.`
        : "Encontramos uma combinação possível. É uma sugestão para revisão: confira antes de confirmar."));
      b.combinacoes.forEach((cb, n) => {
        const card = el("div", "cr-candidato cr-manual-combo");
        card.dataset.combinacao = String(n + 1);
        const corpo = el("div");
        corpo.append(el("strong", null, `Sugestão para revisão ${n + 1} · ${plural(cb.quantidade, "registro", "registros")} · Total ${fmtValor(cb.total)} · Diferença ${fmtValor(cb.diferenca)}`));
        cb.registros.forEach((id) => corpo.append(el("p", "cr-cand-linha", linhaRegistro(porId[id]))));
        if (cb.com_alerta_data) corpo.append(el("p", "cr-manual-alerta", "Atenção: data distante do movimento bancário."));
        if (cb.com_sugestao_pendente) corpo.append(el("p", "cr-manual-alerta", "Contém registro sugerido pelo sistema para outro movimento (ainda sem decisão)."));
        const usar = botao("Selecionar esta combinação", "cr-botao cr-botao-sec", () => { sel.clear(); cb.registros.forEach((id) => sel.add(id)); atualizar(); });
        usar.dataset.acao = "selecionar-combinacao";
        corpo.append(usar);
        card.append(corpo);
        sCombo.append(card);
      });
    } else {
      sCombo.append(el("p", "cr-manual-aviso", `Nenhuma combinação de até ${b.limite_manual} registros fecha exatamente o valor do banco. `
        + "Sem soma exata a associação manual não é possível: o movimento continua não conciliado (você pode registrar uma observação)."));
    }
    if (!b.busca_completa) sCombo.append(el("p", "cr-manual-alerta", "A busca de combinações foi limitada por segurança; selecione os registros manualmente se necessário."));
    // registros elegíveis
    const lista = el("ul", "cr-manual-lista");
    const checks = {};
    if (!b.candidatos.length) lista.append(el("li", "cr-suave", "Nenhum registro elegível (natureza compatível e ainda disponível)."));
    b.candidatos.forEach((c) => {
      const li = el("li", "cr-manual-item");
      li.dataset.id = c.id;
      const lab = el("label");
      const cbx = el("input");
      cbx.type = "checkbox";
      cbx.className = "cr-manual-check";
      cbx.addEventListener("change", () => { cbx.checked ? sel.add(c.id) : sel.delete(c.id); atualizar(); });
      checks[c.id] = cbx;
      const txt = el("span", null, linhaRegistro(c));
      lab.append(cbx, txt);
      li.append(lab);
      const extra = [c.plano_contas ? `plano de contas: ${c.plano_contas}` : "", c.banco_relatorio ? `banco no relatório: ${c.banco_relatorio}` : "",
        c.data_origem].filter(Boolean).join(" · ");
      if (extra) li.append(el("p", "cr-suave cr-manual-extra", extra));
      if (c.alerta_data) li.append(el("p", "cr-manual-alerta", "Atenção: data distante do movimento bancário."));
      if (c.sugerido_em_outra) li.append(el("p", "cr-manual-alerta", "Sugerido pelo sistema para outro movimento (ainda sem decisão)."));
      lista.append(li);
    });
    const resumo = el("p", "cr-manual-resumo");
    const confirmarB = botao("Confirmar associação manual", "cr-botao cr-pri", () => pedirManual(d, b, [...sel]));
    confirmarB.dataset.acao = "confirmar-manual";
    function atualizar() {
      Object.entries(checks).forEach(([id, cbx]) => { cbx.checked = sel.has(id); });
      const soma = [...sel].reduce((s, id) => s + centavos(porId[id].valor), 0);
      const dif = alvoC - soma;
      resumo.textContent = `Selecionados: ${sel.size} de no máximo ${b.limite_manual} · Soma ${reais(soma)} · Valor do banco ${fmtValor(b.valor_banco)} · Diferença ${reais(Math.abs(dif))}`;
      resumo.dataset.diferenca = String(dif);
      confirmarB.disabled = !(sel.size >= 1 && sel.size <= b.limite_manual && dif === 0);
    }
    const porque = el("details", "cr-secao");
    porque.append(el("summary", null, "Por que estes registros apareceram?"));
    const ulp = el("ul", "cr-hist-itens");
    b.explicacao.forEach((x) => ulp.append(el("li", null, x)));
    porque.append(ulp);
    const linha = el("div", "cr-acoes-botoes");
    linha.append(confirmarB);
    alvo.append(sCombo, el("h3", "cr-secao-titulo", `REGISTROS ELEGÍVEIS (${b.candidatos.length})`), lista, resumo, linha, porque,
      el("p", "cr-nota", b.aviso_efeito));
    atualizar();
  }
  function pedirManual(d, b, ids) {
    const regs = ids.map((id) => b.candidatos.find((c) => c.id === id));
    const soma = regs.reduce((s, r) => s + centavos(r.valor), 0);
    pedirConfirmacao({
      titulo: "Confirmar associação manual",
      texto: `Você está associando manualmente 1 movimento do banco a ${plural(regs.length, "registro", "registros")} do relatório. `
        + "A classificação do sistema continua \"não conciliado\". Isso permitirá que a movimentação deixe de bloquear o Financeiro, "
        + "mas não é suporte documental nem aprovação fiscal ou contábil.",
      itens: [`Banco: ${fmtData(b.banco.data)} · ${b.banco.natureza === "ENTRADA" ? "entrada" : "saída"} · ${b.banco.descricao || "—"}`
        + `${b.banco.documento ? " · doc. " + b.banco.documento : ""} · ${fmtValor(b.valor_banco)}`]
        .concat(regs.map((r) => `Relatório: ${fmtData(r.data)} · ${r.contraparte || r.descricao || "—"}${r.documento ? " · doc. " + r.documento : ""} · ${fmtValor(r.valor)}`))
        .concat([`Valor do banco ${fmtValor(b.valor_banco)} · Soma do relatório ${reais(soma)} · Diferença ${reais(centavos(b.valor_banco) - soma)}`]),
      justificativa: "", editavel: true, rotulo: "Confirmar associação manual",
      exemplo: "Ex.: Conferi os registros selecionados; a soma, natureza e contraparte correspondem ao movimento bancário.",
      enviar: async (j) => {
        const r = await api("POST", `${estado.base}/${d.id}/decisao`, { decisao: "APROVADO", manual: { auxiliares: ids }, justificativa: j,
          revisao_conciliacao: b.revisao_conciliacao, revisao_decisoes: b.revisao_decisoes });
        aplicarVisao(r.visao);
        fecharDetalhe();
        aviso(r.mensagem, "ok");
      }
    });
  }

  function fecharDetalhe() {
    camadaDetalhe.hidden = true;
    estado.aberto = null;
  }

  // ---------------------------------------------------------------- confirmação e envio
  function textoJustificativaOk(t) {
    return (t || "").trim().length >= 10;
  }
  function pedirConfirmacao({ titulo, texto, itens, justificativa, editavel, rotulo, enviar, exemplo }) {
    confirmar.replaceChildren();
    confirmar.append(el("h2", "cr-conf-titulo", titulo), el("p", "cr-conf-texto", texto));
    if (itens && itens.length) {
      const ul = el("ul", "cr-conf-itens");
      itens.slice(0, 12).forEach((t) => ul.append(el("li", null, t)));
      if (itens.length > 12) ul.append(el("li", "cr-suave", `… e mais ${itens.length - 12}.`));
      confirmar.append(ul);
    }
    let campo = null;
    if (editavel) {
      const [l, t] = campoJustificativa(justificativa, exemplo);
      campo = t;
      confirmar.append(l);
    } else {
      confirmar.append(el("p", "cr-conf-just", `Justificativa: ${justificativa}`));
    }
    const erro = el("p", "cr-msg");
    erro.setAttribute("role", "alert");
    const linhaB = el("div", "cr-acoes-botoes");
    const cancelar = botao("Cancelar", "cr-botao cr-botao-sec", () => { camadaConfirmar.hidden = true; });
    const ok = botao(rotulo || "Confirmar", "cr-botao cr-pri", async () => {
      const j = campo ? campo.value : justificativa;
      if (!textoJustificativaOk(j)) { erro.textContent = "Informe a justificativa da decisão (mínimo de 10 caracteres)."; erro.dataset.tipo = "erro"; return; }
      ok.disabled = true;
      cancelar.disabled = true;
      try {
        await enviar(j.trim());
        camadaConfirmar.hidden = true;
      } catch (e) {
        camadaConfirmar.hidden = true;
        tratarErro(e);
      } finally {
        ok.disabled = false;
        cancelar.disabled = false;
      }
    });
    ok.dataset.acao = "confirmar-envio";
    linhaB.append(cancelar, ok);
    confirmar.append(erro, linhaB);
    camadaConfirmar.hidden = false;
    (campo || ok).focus();
  }
  function tratarErro(e) {
    const obsoleto = e.codigo === "ESTADO_OBSOLETO";
    const texto = obsoleto ? "As informações mudaram desde que a tela foi aberta. A tela foi atualizada; revise e decida de novo. Nada foi gravado." : e.message;
    if (obsoleto) {
      carregar(true).then(() => {
        aviso(texto, "erro");
        if (estado.aberto) abrirDetalhe(estado.aberto, texto);
      });
      return;
    }
    if (!camadaDetalhe.hidden) {
      const m = detalhe.querySelector(".cr-msg-det");
      if (m) { m.textContent = texto; m.dataset.tipo = "erro"; }
    }
    aviso(texto, "erro");
  }
  function descreverItem(i) {
    const b = i.banco[0];
    const a = i.relatorio[0];
    return `${b ? fmtData(b.data) + " · " + (b.descricao || "") : "—"} ↔ ${a ? (a.contraparte || a.descricao || "") : "—"} · ${fmtValor(i.valor_banco)}`;
  }

  function pedirIndividual(d, decisao, candidato, justificativa, alvo) {
    const textos = {
      APROVADO: candidato
        ? [`Confirmar o candidato ${candidato.numero}`, "Você está confirmando 1 associação (o candidato selecionado). Os demais candidatos ficarão registrados como não escolhidos. Isso permitirá que a movimentação deixe de bloquear o Financeiro, mas não representa aprovação fiscal ou contábil.", "Confirmar candidato"]
        : ["Confirmar associação", "Você está confirmando 1 associação. Isso permitirá que essa movimentação deixe de bloquear o Financeiro, mas não representa aprovação fiscal ou contábil.", "Confirmar"],
      REJEITADO: ["Rejeitar associação", "Você está rejeitando a sugestão do sistema. A sugestão continua registrada e a movimentação continuará bloqueando o Financeiro até receber outro suporte.", "Rejeitar"],
      REVOGADO: ["Desfazer decisão", "Você está desfazendo a decisão vigente. O histórico é preservado e a associação volta a aguardar a sua revisão (e a bloquear, se for o caso).", "Desfazer"],
      OBSERVACAO: ["Registrar observação", "A observação fica no histórico. Ela não cria associação nem remove o bloqueio.", "Registrar"]
    }[decisao];
    pedirConfirmacao({
      titulo: textos[0], texto: textos[1], itens: [descreverItem(d)], justificativa, editavel: true, rotulo: textos[2],
      enviar: async (j) => {
        const corpo = { decisao, justificativa: j, revisao_conciliacao: d.revisao_conciliacao, revisao_decisoes: d.revisao_decisoes };
        if (candidato) corpo.candidato = { bancarios: candidato.bancarios, auxiliares: candidato.auxiliares };
        if (alvo) corpo.alvo = alvo;
        const r = await api("POST", `${estado.base}/${d.id}/decisao`, corpo);
        aplicarVisao(r.visao);
        fecharDetalhe();
        aviso(r.mensagem, "ok");
      }
    });
  }
  function pedirLote() {
    const v = estado.visao;
    const itens = v.itens.filter((i) => estado.selecionados.has(i.id) && i.selecionavel_lote);
    if (!itens.length) return;
    pedirConfirmacao({
      titulo: "Confirmar associações selecionadas",
      texto: `Você está confirmando ${plural(itens.length, "associação", "associações")}. Isso permitirá que ${itens.length === 1 ? "essa movimentação deixe" : "essas movimentações deixem"} de bloquear o Financeiro, mas não representa aprovação fiscal ou contábil. Cada decisão fica registrada individualmente no histórico.`,
      itens: itens.map(descreverItem),
      justificativa: "Revisei os registros selecionados e confirmo as associações.", editavel: true, rotulo: "Confirmar",
      enviar: async (j) => {
        const r = await api("POST", `${estado.base}/decisoes-lote`, {
          associacoes: itens.map((i) => i.id), justificativa: j, revisao_conciliacao: v.revisao_conciliacao, revisao_decisoes: v.revisao_decisoes
        });
        estado.selecionados.clear();
        aplicarVisao(r.visao);
        aviso(r.mensagem, "ok");
      }
    });
  }
  function pedirReinicio() {
    confirmar.replaceChildren();
    confirmar.append(el("h2", "cr-conf-titulo", "Reiniciar a demonstração"),
      el("p", "cr-conf-texto", "Isso apaga SOMENTE as decisões fictícias desta demonstração e volta ao cenário inicial. Nenhuma solicitação, empresa ou dado real é tocado."));
    const linhaB = el("div", "cr-acoes-botoes");
    linhaB.append(botao("Cancelar", "cr-botao cr-botao-sec", () => { camadaConfirmar.hidden = true; }),
      botao("Reiniciar", "cr-botao cr-pri", async () => {
        try {
          const r = await api("POST", `${estado.base}/reiniciar`, { confirmado: true });
          camadaConfirmar.hidden = true;
          estado.selecionados.clear();
          estado.filtro = "todos";
          aplicarVisao(r.visao);
          aviso(r.mensagem, "ok");
        } catch (e) {
          camadaConfirmar.hidden = true;
          tratarErro(e);
        }
      }));
    confirmar.append(linhaB);
    camadaConfirmar.hidden = false;
  }

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || raiz.hidden) return;
    e.stopPropagation();
    if (!camadaConfirmar.hidden) camadaConfirmar.hidden = true;
    else if (!camadaDetalhe.hidden) fecharDetalhe();
    else fechar();
  }, true);

  // ---------------------------------------------------------------- pontos de entrada
  window.EV.central = {
    abrirDemonstracao: () => abrir("/demonstracao/conciliacao-financeira"),
    abrirDemonstracaoManual: () => abrir("/demonstracao/associacao-manual"),
    abrirDemonstracaoAmbiguo: () => abrir("/demonstracao/ambiguo-parcial"),
    abrirSolicitacao: (sol) => (/^SOL-20\d{2}-\d{6}$/.test(sol) ? abrir(`/solicitacoes/${sol}/conciliacao-financeira`) : null),
    fechar
  };
  const nav = document.querySelector(".gestao-nav");
  const entrada = botao("Demo conciliação", "gestao-botao cr-entrada-demo", () => window.EV.central.abrirDemonstracao());
  entrada.dataset.icone = "⇄";
  entrada.title = "DEMONSTRAÇÃO — Conciliação Financeira (dados fictícios)";
  entrada.setAttribute("aria-label", "DEMONSTRAÇÃO — Conciliação Financeira");
  if (nav) {
    const recolher = nav.querySelector('[data-pagina="escritorio"]');
    nav.insertBefore(entrada, recolher || null);
  } else {
    document.querySelector(".topo").append(entrada);
  }
  const entradaManual = botao("Demo assoc. manual", "gestao-botao cr-entrada-demo cr-entrada-demo-manual", () => window.EV.central.abrirDemonstracaoManual());
  entradaManual.dataset.icone = "✚";
  entradaManual.title = "DEMONSTRAÇÃO — Associação manual (dados fictícios)";
  entradaManual.setAttribute("aria-label", "DEMONSTRAÇÃO — Associação manual");
  entrada.after(entradaManual);
  const entradaAmb = botao("Demo ambíguo parcial", "gestao-botao cr-entrada-demo cr-entrada-demo-ambiguo", () => window.EV.central.abrirDemonstracaoAmbiguo());
  entradaAmb.dataset.icone = "⇆";
  entradaAmb.title = "DEMONSTRAÇÃO — Ambiguidade parcial (dados fictícios)";
  entradaAmb.setAttribute("aria-label", "DEMONSTRAÇÃO — Ambiguidade parcial");
  entradaManual.after(entradaAmb);
  const pedidoCentral = new URLSearchParams(window.location.search).get("central");
  if (pedidoCentral === "demonstracao") window.EV.central.abrirDemonstracao();
  if (pedidoCentral === "associacao-manual") window.EV.central.abrirDemonstracaoManual();
  if (pedidoCentral === "ambiguo-parcial") window.EV.central.abrirDemonstracaoAmbiguo();
})();
