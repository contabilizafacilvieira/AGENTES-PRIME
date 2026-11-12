/*
 * DOCUMENTOS E TENTATIVAS de uma solicitação (modo operação local).
 * - "Adicionar documento complementar": arquivo → motivo → revisar → enviar → classificação por Documentos. NÃO reprocessa.
 * - "Reconciliar tentativa legada": somente para tentativa antiga pendente; Problema / Impacto / O que será feito + frase.
 * Tudo exibido com textContent. Estados e elegibilidade vêm do servidor.
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
  async function api(metodo, rota, corpo, extras) {
    const binario = corpo instanceof ArrayBuffer;
    let r;
    try {
      r = await fetch("/api" + rota, {
        method: metodo, cache: "no-store", credentials: "same-origin",
        headers: Object.assign({ "X-Prime-Sessao": TOKEN }, corpo !== undefined && !binario ? { "Content-Type": "application/json" } : {}, extras || {}),
        body: corpo === undefined ? undefined : binario ? corpo : JSON.stringify(corpo)
      });
    } catch (_) {
      throw new Error("Não foi possível falar com o aplicativo. Confira se o servidor local está em execução.");
    }
    const dados = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(dados.erro || dados.mensagem || (dados.motivos || []).join(" ") || `Não foi possível concluir (erro ${r.status}).`);
    return dados;
  }
  async function sha256(buffer) {
    const d = await crypto.subtle.digest("SHA-256", buffer);
    return Array.from(new Uint8Array(d)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  const hora = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "");
  const AREA = { FINANCEIRO: "Financeiro", FISCAL: "Fiscal", DP: "DP", CONCILIACAO: "Conciliação", CONTABIL: "Contábil", TRIAGEM: "A conferir" };

  // ---------------------------------------------------------------- janela (camada) reutilizando o visual da Central
  const camada = el("div", "sd-camada");
  camada.hidden = true;
  const caixa = el("section", "sd-caixa");
  caixa.setAttribute("role", "dialog");
  camada.append(caixa);
  document.body.append(camada);
  let aoFechar = null;
  function abrirJanela(titulo) {
    caixa.replaceChildren(el("h2", "cr-conf-titulo", titulo));
    camada.hidden = false;
    return caixa;
  }
  function fecharJanela() {
    camada.hidden = true;
    if (aoFechar) aoFechar();
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !camada.hidden) { e.stopPropagation(); fecharJanela(); } }, true);
  function mensagem(alvo, texto, tipo) {
    alvo.textContent = texto || "";
    alvo.dataset.tipo = tipo || "";
  }
  function pio(problema, impacto, oQue) {
    const d = el("dl", "cr-pio");
    [["Problema", problema], ["Impacto", impacto], ["O que será feito", oQue]].forEach(([t, x]) => d.append(el("dt", null, t), el("dd", null, x)));
    return d;
  }

  // ---------------------------------------------------------------- documento complementar
  function fluxoComplemento(sol) {
    const c = abrirJanela("Adicionar documentos ao fechamento");
    c.dataset.fluxo = "complemento";
    c.append(el("p", "cr-conf-texto", "Selecione um ou VÁRIOS arquivos (notas fiscais, extratos, relatório financeiro, book, balancete, razão, impostos, "
      + "folha). Eles são guardados sem alterar os documentos originais e passam pela classificação do Agente de Documentos, que separa por "
      + "departamento. O envio NÃO inicia o fechamento: depois de conferir a classificação, use \"Preparar fechamento\"."));
    const lArq = el("label", "cr-justificativa");
    lArq.append(el("span", null, "Arquivos"));
    const arquivo = el("input");
    arquivo.type = "file";
    arquivo.multiple = true;
    arquivo.className = "sd-arquivo";
    lArq.append(arquivo);
    const lMot = el("label", "cr-justificativa");
    lMot.append(el("span", null, "Motivo do complemento (obrigatório)"));
    const motivo = el("textarea");
    motivo.rows = 2;
    motivo.maxLength = 300;
    motivo.placeholder = "Ex.: extrato bancário da competência recebido depois.";
    lMot.append(motivo);
    const msg = el("p", "cr-msg");
    msg.setAttribute("role", "status");
    const revisao = el("div", "sd-revisao");
    const linha = el("div", "cr-acoes-botoes");
    let lote = null;
    const cancelar = botao("Cancelar", "cr-botao cr-botao-sec", async () => {
      if (lote) { try { await api("DELETE", `/lotes/${lote}`); } catch (_) { /* rascunho já descartado */ } }
      fecharJanela();
    });
    const revisar = botao("Revisar", "cr-botao cr-pri", async () => {
      const fs = Array.from(arquivo.files || []);
      if (!fs.length) return mensagem(msg, "Selecione um arquivo (ou vários).", "erro");
      if ((motivo.value || "").trim().length < 5) return mensagem(msg, "Informe o motivo do complemento (mínimo de 5 caracteres).", "erro");
      revisar.disabled = true;
      try {
        const r = await api("POST", `/solicitacoes/${sol}/complementos`, { motivo: motivo.value.trim() });
        lote = r.lote;
        for (let i = 0; i < fs.length; i++) {
          mensagem(msg, `Enviando ${i + 1} de ${fs.length} com conferência de integridade (SHA-256)…`);
          const buffer = await fs[i].arrayBuffer();
          await api("PUT", `/lotes/${lote}/arquivos`, buffer, { "X-Nome-Arquivo": encodeURIComponent(fs[i].name), "X-Sha256": await sha256(buffer) });
        }
        const v = await api("GET", `/solicitacoes/${sol}/complementos/${lote}`);
        revisao.replaceChildren(el("h3", "cr-secao-titulo", "Revisão antes de enviar"));
        v.arquivos.forEach((a) => {
          const p = el("p", "sd-dup sd-dup-" + a.duplicidade.categoria.toLowerCase(), `${a.nome_original} · ${(a.tamanho / 1024).toFixed(0)} KB · ${a.duplicidade.explicacao}`);
          p.dataset.categoria = a.duplicidade.categoria;
          revisao.append(p);
        });
        arquivo.disabled = true;
        motivo.disabled = true;
        revisar.hidden = true;
        enviar.hidden = !v.pode_concluir;
        mensagem(msg, v.pode_concluir ? `Confira e confirme o envio de ${v.arquivos.length} arquivo(s).` : "Os documentos já fazem parte da solicitação; cancele para descartar.", v.pode_concluir ? "" : "erro");
      } catch (e) {
        mensagem(msg, e.message, "erro");
        revisar.disabled = false;
      }
    });
    const enviar = botao("Enviar documento", "cr-botao cr-pri", async () => {
      enviar.disabled = true;
      cancelar.disabled = true;
      mensagem(msg, "Recebendo e classificando pelo Agente de Documentos…");
      try {
        const r = await api("POST", `/solicitacoes/${sol}/complementos/${lote}/concluir`, { confirmado: true });
        lote = null;
        revisao.replaceChildren(el("h3", "cr-secao-titulo", "Documentos recebidos — classificação por departamento"));
        const grupos = {};
        r.complemento.documentos.forEach((d) => (grupos[AREA[d.area] || "A conferir"] = grupos[AREA[d.area] || "A conferir"] || []).push(d));
        Object.entries(grupos).forEach(([dep, docs]) => {
          revisao.append(el("p", "sd-classificacao-dep", `${dep}: ${docs.length}`));
          docs.forEach((d) => revisao.append(el("p", "sd-classificacao",
            `${d.nome_original}: ${d.tipo || "tipo não identificado"} · área: ${AREA[d.area] || d.area || "a identificar (aguardando classificação do Supervisor)"}`)));
        });
        mensagem(msg, r.mensagem, "ok");
        enviar.hidden = true;
        cancelar.textContent = "Fechar";
        cancelar.disabled = false;
      } catch (e) {
        mensagem(msg, e.message, "erro");
        enviar.disabled = false;
        cancelar.disabled = false;
      }
    });
    enviar.hidden = true;
    enviar.textContent = "Enviar documentos";
    enviar.dataset.acao = "enviar-complemento";
    linha.append(cancelar, revisar, enviar);
    c.append(lArq, lMot, revisao, msg, linha);
    arquivo.focus();
  }

  // ---------------------------------------------------------------- reconciliação de tentativa legada
  async function fluxoLegada(sol, numero) {
    const c = abrirJanela(`Reconciliar tentativa legada ${String(numero).padStart(4, "0")}`);
    c.dataset.fluxo = "legada";
    const msg = el("p", "cr-msg");
    msg.setAttribute("role", "status");
    let av;
    try {
      av = await api("GET", `/solicitacoes/${sol}/tentativas/${String(numero).padStart(4, "0")}/reconciliacao-legada`);
    } catch (e) {
      c.append(el("p", "cr-erro-fixo", e.message), botao("Fechar", "cr-botao", fecharJanela));
      return;
    }
    if (!av.elegivel) {
      c.append(el("p", "cr-erro-fixo", `Não é possível reconciliar com segurança: ${av.motivos.join(" ")}`), botao("Fechar", "cr-botao", fecharJanela));
      return;
    }
    c.append(pio(av.problema, av.impacto, av.o_que_sera_feito));
    c.append(el("p", "cr-nota", `Execuções comprovadas: ${av.execucoes.map((e) => e.execucao).join(", ")}. Evidência: motivo idêntico da retomada e resultado com o mesmo conteúdo (hash) registrado pelo Coordenador.`));
    const lJ = el("label", "cr-justificativa");
    lJ.append(el("span", null, "Justificativa (obrigatória)"));
    const just = el("textarea");
    just.rows = 2;
    just.maxLength = 500;
    lJ.append(just);
    const lF = el("label", "cr-justificativa");
    lF.append(el("span", null, `Para confirmar, digite: ${av.frase}`));
    const frase = el("input");
    frase.type = "text";
    frase.className = "sd-frase";
    lF.append(frase);
    const linha = el("div", "cr-acoes-botoes");
    const ok = botao("Reconciliar", "cr-botao cr-pri", async () => {
      ok.disabled = true;
      try {
        const r = await api("POST", `/solicitacoes/${sol}/tentativas/${String(numero).padStart(4, "0")}/reconciliacao-legada`,
          { justificativa: just.value, frase: frase.value, confirmado: true });
        mensagem(msg, r.mensagem, "ok");
        ok.hidden = true;
      } catch (e) {
        mensagem(msg, e.message, "erro");
        ok.disabled = false;
      }
    });
    ok.dataset.acao = "reconciliar-legada";
    linha.append(botao("Cancelar", "cr-botao cr-botao-sec", fecharJanela), ok);
    c.append(lJ, lF, msg, linha);
  }

  // ---------------------------------------------------------------- reprocessar o fechamento (rotas OFICIAIS: reprocessar → retomar-rota-financeira)
  const num = (n) => String(n).padStart(4, "0");
  // opção recomendada no primeiro ciclo controlado: o Financeiro executa e a SOL PARA antes da Contabilidade/Bancos
  function opcaoParar() {
    const l = el("label", "sd-parar");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.className = "sd-parar-check";
    l.append(cb, el("span", null, " Executar o Financeiro e parar para revisão (recomendado): Fiscal, DP e Financeiro executam; a Contabilidade e a "
      + "Conciliação só começam com a sua autorização."));
    return [l, cb];
  }
  function iniciarExecucao(sol, numero, alvo, msg, parar) {
    const b = botao(`Iniciar execução da tentativa ${num(numero)}`, "cr-botao cr-pri", async () => {
      b.disabled = true;
      mensagem(msg, "Iniciando o fechamento com os documentos congelados…");
      try {
        const r = await api("POST", `/solicitacoes/${sol}/retomar-rota-financeira`, { justificativa: `Execução da tentativa ${num(numero)} de reprocessamento do fechamento.`,
          confirmado: true, parar_apos_financeiro: !!(parar && parar.checked) });
        if (parar) parar.disabled = true;
        mensagem(msg, `${r.mensagem || "Execução iniciada."} A tela atualiza sozinha; ao terminar, abra a revisão da conciliação financeira.`, "ok");
        b.hidden = true;
      } catch (e) {
        mensagem(msg, e.message, "erro");
        b.disabled = false;
      }
    });
    b.dataset.acao = "iniciar-execucao";
    alvo.append(b);
    return b;
  }
  async function fluxoReprocessar(sol, primeira) {
    const c = abrirJanela(primeira ? "Preparar fechamento" : "Reprocessar fechamento");
    c.dataset.fluxo = "reprocessar";
    const msg = el("p", "cr-msg");
    msg.setAttribute("role", "status");
    let lista;
    try {
      lista = await api("GET", `/solicitacoes/${sol}/complementos`);
    } catch (e) {
      c.append(el("p", "cr-erro-fixo", e.message), botao("Fechar", "cr-botao", fecharJanela));
      return;
    }
    const comps = lista.complementos.flatMap((x) => x.documentos.map((d) => ({ ...d, em: x.concluido_em })));
    const resumo = el("div", "sd-resumo-reprocessar");
    resumo.append(el("p", null, "Será criada uma NOVA tentativa (as anteriores ficam preservadas) com os documentos do envio original"
      + (comps.length ? ` e ${comps.length} documento(s) complementar(es):` : ".")));
    if (comps.length) {
      resumo.append(el("p", "sd-aviso-congelar", "Os documentos disponíveis serão congelados em uma nova tentativa de reprocessamento."));
      const ul = el("ul", "sd-lista");
      comps.forEach((d) => ul.append(el("li", null, `${d.nome_original} · ${d.tipo || "tipo não identificado"} · recebido em ${hora(d.em)}`)));
      resumo.append(ul);
    }
    resumo.append(el("p", "cr-nota", "Depois de criar a tentativa, você inicia a execução (Fiscal, DP e Financeiro; depois Contábil e Conciliação). Nada é aprovado nem escriturado; "
      + "movimentos sem associação confirmada continuam bloqueando a Contabilidade."));
    const [lParar, parar] = opcaoParar();
    const lM = el("label", "cr-justificativa");
    lM.append(el("span", null, "Motivo do reprocessamento (obrigatório)"));
    const motivo = el("textarea");
    motivo.rows = 2;
    motivo.maxLength = 500;
    lM.append(motivo);
    const linha = el("div", "cr-acoes-botoes");
    const ok = botao("Criar nova tentativa", "cr-botao cr-pri", async () => {
      if ((motivo.value || "").trim().length < 5) return mensagem(msg, "Informe o motivo do reprocessamento (mínimo de 5 caracteres).", "erro");
      ok.disabled = true;
      try {
        const r = await api("POST", `/solicitacoes/${sol}/reprocessar`, { confirmado: true, motivo: motivo.value.trim(), solicitante: "Supervisor" });
        const t = r.tentativa;
        const docs = ((t.manifesto_efetivo || {}).documentos || []);
        mensagem(msg, `Tentativa ${num(t.numero)} criada com ${docs.length} documento(s) congelado(s) `
          + `(${docs.filter((x) => x.origem === "COMPLEMENTAR").length} complementar(es)). Nada foi executado ainda.`, "ok");
        ok.hidden = true;
        motivo.disabled = true;
        iniciarExecucao(sol, t.numero, linha, msg, parar);
      } catch (e) {
        mensagem(msg, e.message, "erro");
        ok.disabled = false;
      }
    });
    ok.dataset.acao = "criar-tentativa";
    linha.append(botao("Fechar", "cr-botao cr-botao-sec", fecharJanela), ok);
    c.append(resumo, lM, lParar, msg, linha);
    motivo.focus();
  }
  function fluxoExecutar(sol, numero) {
    const c = abrirJanela(`Executar tentativa ${num(numero)}`);
    const msg = el("p", "cr-msg");
    msg.setAttribute("role", "status");
    c.append(el("p", "cr-conf-texto", "A tentativa já está criada com os documentos congelados. Nada é aprovado nem escriturado."));
    const [lParar, parar] = opcaoParar();
    c.append(lParar);
    const linha = el("div", "cr-acoes-botoes");
    linha.append(botao("Fechar", "cr-botao cr-botao-sec", fecharJanela));
    iniciarExecucao(sol, numero, linha, msg, parar);
    c.append(msg, linha);
  }

  // ---------------------------------------------------------------- bloco na tela da solicitação
  function bloco(d, atualizar, opcoes) {
    const s = el("div", "ac-bloco sd-bloco");
    s.dataset.solDocumentos = "true";
    s.append(el("h3", "ac-titulo-bloco", "Documentos complementares e tentativas"));
    const corpo = el("div");
    s.append(corpo);
    aoFechar = () => { if (atualizar) atualizar(); };
    const legadas = (d.tentativas || []).filter((t) => t.legada_pendente);
    legadas.forEach((t) => {
      const p = el("div", "sd-legada");
      p.append(el("p", null, `Tentativa antiga ${String(t.numero).padStart(4, "0")} ainda aparece como ${t.status === "PREPARADA" ? "preparada" : "em execução"}; isso impede novas tentativas.`),
        botao("Reconciliar tentativa legada", "botao-sec sd-botao-legada", () => fluxoLegada(d.sol, t.numero)));
      corpo.append(p);
    });
    const tentativas = d.tentativas || [];
    const ultima = tentativas[tentativas.length - 1];
    const ativa = ultima && ["PREPARADA", "EM_EXECUCAO", "PAUSADA"].includes(ultima.status);
    const ck = d.checkpoint;
    if (fluxoFinanceiroPedido(opcoes) && ck && ck.situacao === "AGUARDANDO_AUTORIZACAO") corpo.append(painelCheckpoint(d, ck));
    const fluxoFinanceiro = !!(opcoes && opcoes.reprocessar);         // a tela simples já tem "Reprocessar solicitação"
    if (!fluxoFinanceiro) { /* sem ações de reprocessamento aqui */ }
    else if (ultima && ultima.ciclo_vida === "V2" && ultima.status === "PREPARADA" && d.estado === "AGUARDANDO_SUPERVISOR") {
      corpo.append(botao(`Executar tentativa ${num(ultima.numero)}`, "botao-sec sd-botao-executar", () => fluxoExecutar(d.sol, ultima.numero)));
    } else if (!ativa && !legadas.length && d.estado === "AGUARDANDO_SUPERVISOR") {
      const primeira = !tentativas.length && (d.fluxo === "FECHAMENTO" || d.fluxo_origem === "FECHAMENTO");
      corpo.append(botao(primeira ? "Preparar fechamento" : "Reprocessar fechamento", "botao-sec sd-botao-reprocessar", () => fluxoReprocessar(d.sol, primeira)));
    }
    api("GET", `/solicitacoes/${d.sol}/complementos`).then((r) => {
      const ul = el("ul", "sd-lista");
      r.complementos.forEach((c) => c.documentos.forEach((x) => ul.append(el("li", null,
        `${hora(c.concluido_em)} · ${x.nome_original} · ${x.tipo || "tipo não identificado"} · ${c.tentativas.length ? `usado na(s) tentativa(s) ${c.tentativas.join(", ")}` : "ainda não usado em tentativa"}`))));
      if (ul.childNodes.length) corpo.append(ul);
      else corpo.append(el("p", "nd", "Nenhum documento complementar."));
      if (r.pode_receber) corpo.append(botao("Adicionar documentos ao fechamento", "botao-sec sd-botao-complemento", () => fluxoComplemento(d.sol)));
      else if (r.motivo) corpo.append(el("p", "nd", r.motivo));
    }).catch((e) => corpo.append(el("p", "cr-erro-fixo", e.message)));
    return s;
  }

  // ---------------------------------------------------------------- checkpoint após o Financeiro
  function fluxoFinanceiroPedido(opcoes) { return !!(opcoes && opcoes.reprocessar); }
  const ETAPA = { BANCOS: "Contábil (bancos)", CONTABILIDADE_FISCAL: "Contábil (fiscal)", CONTABILIDADE_DP: "Contábil (DP)", CONCILIACAO: "Conciliação",
    DP: "DP", FISCAL: "Fiscal", FINANCEIRO: "Financeiro" };
  function painelCheckpoint(d, ck) {
    const p = el("div", "sd-checkpoint");
    p.dataset.checkpoint = ck.situacao;
    const r = ck.resumo_financeiro || {};
    p.append(el("p", "sd-ck-linha sd-ck-ok", "FINANCEIRO — Concluído"),
      el("p", "sd-ck-linha sd-ck-espera", "PRÓXIMA ETAPA — Contabilidade/Bancos aguardando sua autorização"),
      el("p", "cr-nota sd-ck-proximas", `Próximas etapas do fechamento: ${(ck.proximas_etapas || ["BANCOS", "CONCILIACAO"]).map((e) => ETAPA[e] || e).join(" → ")}.`),
      el("p", "cr-nota", `Financeiro concluído em ${hora(ck.atingido_em)}${ck.tentativa ? ` na tentativa ${num(ck.tentativa)}` : ""}`
        + `${r.movimentos !== undefined ? ` · ${r.movimentos} movimento(s), ${r.pendencias} pendência(s)` : ""}. Nada foi encaminhado à Contabilidade.`));
    const linha = el("div", "cr-acoes-botoes");
    const rev = botao("Revisar resultado do Financeiro", "botao-sec sd-botao-revisar-fin", () => {
      if (window.EV.operacao && window.EV.operacao.aba) window.EV.operacao.aba("decisoes");
    });
    const cont = botao("Continuar para Contabilidade/Bancos", "botao-sec sd-botao-continuar", () => fluxoContinuar(d, ck));
    linha.append(rev, cont);
    p.append(linha);
    return p;
  }
  function fluxoContinuar(d, ck) {
    const c = abrirJanela("Continuar para Contabilidade/Bancos");
    c.dataset.fluxo = "continuar";
    c.append(el("p", "cr-conf-texto", `A mesma tentativa${ck.tentativa ? " " + num(ck.tentativa) : ""} continua: o Contábil prepara as propostas `
      + "(SIMULAÇÃO) e a Conciliação confere em seguida. O Financeiro NÃO é executado de novo. Nada é aprovado, escriturado nem enviado ao Domínio."));
    const lJ = el("label", "cr-justificativa");
    lJ.append(el("span", null, "Justificativa da autorização (obrigatória)"));
    const just = el("textarea");
    just.rows = 2;
    just.maxLength = 500;
    lJ.append(just);
    const msg = el("p", "cr-msg");
    msg.setAttribute("role", "status");
    const linha = el("div", "cr-acoes-botoes");
    const ok = botao("Autorizar e continuar", "cr-botao cr-pri", async () => {
      if ((just.value || "").trim().length < 5) return mensagem(msg, "Informe a justificativa (mínimo de 5 caracteres).", "erro");
      ok.disabled = true;
      try {
        const r = await api("POST", `/solicitacoes/${d.sol}/continuar-apos-financeiro`, { justificativa: just.value.trim(), confirmado: true });
        mensagem(msg, r.mensagem, "ok");
        ok.hidden = true;
      } catch (e) {
        mensagem(msg, e.message, "erro");
        ok.disabled = false;
      }
    });
    ok.dataset.acao = "autorizar-continuacao";
    linha.append(botao("Fechar", "cr-botao cr-botao-sec", fecharJanela), ok);
    c.append(lJ, msg, linha);
  }

  window.EV.solDocumentos = { bloco, fluxoComplemento, fluxoLegada, fluxoReprocessar };
})();
