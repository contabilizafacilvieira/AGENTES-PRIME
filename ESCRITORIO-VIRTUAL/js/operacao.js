/*
 * Modo OPERAÇÃO LOCAL do Escritório Virtual.
 * Só é ativado quando a página é servida pela API local (127.0.0.1), que entrega o token de sessão em
 * <meta name="prime-sessao">. Aberta direto do disco, a página continua apenas com a simulação.
 *
 * O navegador envia somente: empresa (identificador da lista da API), competência (AAAA-MM), instrução e o
 * conteúdo dos arquivos com o SHA-256 calculado aqui. Ele não escolhe caminhos, agentes nem estados: quem decide
 * é o Coordenador (servidor). Tudo o que vem da API é exibido com textContent.
 */
(function () {
  "use strict";
  const EV = window.EV;
  const meta = document.querySelector('meta[name="prime-sessao"]');
  if (!meta || !meta.content || !EV || !EV.app) return;
  const TOKEN = meta.content;
  const app = EV.app;

  const ROTULOS = {
    DOCUMENTOS_EM_ANDAMENTO: "Documentos em andamento",
    AGUARDANDO_SUPERVISOR: "Aguardando Supervisor",
    PRONTO_PARA_FINANCEIRO: "Pronto para o Financeiro (fluxo Documentos)",
    FINANCEIRO_EM_ANDAMENTO: "Financeiro conferindo",
    FISCAL_EM_ANDAMENTO: 'Fiscal analisando documentos',
    CONTABILIDADE_FISCAL_EM_ANDAMENTO: 'Contabilidade preparando propostas fiscais',
    BANCOS_EM_ANDAMENTO: "Contabilidade/Bancos preparando os lançamentos",
    DP_EM_ANDAMENTO: "DP analisando folha, encargos e provisões",
    CONTABILIDADE_DP_EM_ANDAMENTO: "Contabilidade preparando propostas do DP",
    CONCILIACAO_EM_ANDAMENTO: "Conciliação conferindo a escrituração proposta",
    CANCELADA: "Cancelada",
    ENCERRADA: "Revisão parcial encerrada",
    // aprovação do Supervisor em SIMULAÇÃO: nada escriturado nem liberado ao Domínio
    FECHAMENTO_APROVADO: "Fechamento aprovado (SIMULAÇÃO)"
  };

  function el(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined && texto !== null) e.textContent = String(texto);
    return e;
  }

  async function api(metodo, rota, corpo, cabecalhos) {
    const binario = corpo instanceof ArrayBuffer;
    const h = Object.assign({ "X-Prime-Sessao": TOKEN }, corpo !== undefined && !binario ? { "Content-Type": "application/json" } : {}, cabecalhos || {});
    const r = await fetch("/api" + rota, {
      method: metodo, headers: h, cache: "no-store", credentials: "same-origin",
      body: corpo === undefined ? undefined : binario ? corpo : JSON.stringify(corpo)
    });
    const dados = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(dados.erro || `Erro ${r.status}`);
    return dados;
  }

  async function sha256(buffer) {
    const d = await crypto.subtle.digest("SHA-256", buffer);
    return Array.from(new Uint8Array(d)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  const hora = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" }) : "");
  const mb = (n) => `${(n / (1024 * 1024)).toFixed(1)} MB`;

  // ---------------------------------------------------------------- topo: modo operação
  const topo = document.querySelector(".topo");
  const menuSim = document.getElementById("botao-sim").closest(".menu");
  menuSim.hidden = true;
  document.querySelector(".gaveta .dev").hidden = true;   // controles da simulação não existem no modo operação
  const modo = el("span", "op-modo", "OPERAÇÃO LOCAL · 127.0.0.1");
  const botao = el("button", "botao-topo op-botao", "Nova solicitação");
  botao.type = "button";
  topo.insertBefore(botao, menuSim);
  topo.insertBefore(modo, botao);

  // ---------------------------------------------------------------- painel de operação
  const painel = el("section", "op-painel");
  painel.setAttribute("role", "dialog");
  painel.setAttribute("aria-label", "Solicitação ao Coordenador");
  painel.hidden = true;
  const cabeca = el("div", "op-cabeca");
  const titulo = el("h2", "op-titulo", "Nova solicitação ao Coordenador Geral");
  const fechar = el("button", "fechar", "✕");
  fechar.type = "button";
  fechar.setAttribute("aria-label", "Fechar");
  // "Ampliar painel": alarga o acompanhamento para analisar as tabelas; o escritório encolhe mas continua visível
  const ampliar = el("button", "ac-ampliar", "Ampliar painel");
  ampliar.type = "button";
  ampliar.hidden = true;
  ampliar.setAttribute("aria-pressed", "false");
  const acoesCabeca = el("div", "op-cabeca-acoes");
  acoesCabeca.append(ampliar, fechar);
  cabeca.append(titulo, acoesCabeca);

  const form = el("div", "op-form");
  const campo = (rotulo, controle, ajuda) => {
    const l = el("label", "op-campo");
    l.append(el("span", "op-rotulo", rotulo), controle);
    if (ajuda !== undefined) l.append(el("span", "op-ajuda", ajuda));
    form.append(l);
    return controle;
  };
  const selEmpresa = campo("Empresa", el("select"));
  const avisoCadastro = el('div','op-cadastro-pendente');avisoCadastro.hidden=true;form.append(avisoCadastro);
  const motivoCadastro = el('p');const concluirCadastro=el('button',null,'Concluir cadastro da empresa');concluirCadastro.type='button';
  avisoCadastro.append(motivoCadastro,concluirCadastro);
  concluirCadastro.addEventListener('click',()=>window.dispatchEvent(new CustomEvent(selEmpresa.value?'prime-empresa':'prime-empresas',{detail:selEmpresa.value})));
  const selFluxo = campo("Tipo de solicitação", el("select"));
  [["", "Selecione o fluxo de trabalho"], ["DOCUMENTOS", "Receber documentos e distribuir por área"], ["FINANCEIRO_BANCOS", "Financeiro → Contabilidade/Bancos (SIMULAÇÃO)"]].forEach(([v, t]) => {
    const o = el("option", null, t);
    o.value = v;
    selFluxo.append(o);
  });
  selFluxo.value = "DOCUMENTOS";
  const avisoFluxo = el("p", "op-ajuda");
  const explicarFluxo = () => {
    avisoFluxo.textContent = selFluxo.value === "DOCUMENTOS"
      ? "Documentos identifica e distribui por área: extratos ao Financeiro, folha/encargos/provisões ao DP, notas e guias ao Fiscal (piloto da empresa autorizado). Depois, Contabilidade prepara as propostas e a Conciliação confere o conjunto — tudo em SIMULAÇÃO."
      : "O Coordenador encaminhará Documentos → Financeiro → Contabilidade/Bancos; bloqueios serão apresentados para conferência.";
  };
  selFluxo.addEventListener("change", explicarFluxo);
  explicarFluxo();
  // explicação longa sob demanda ("Saiba mais"): a tela mostra só o essencial
  const saibaFluxo = el("details", "op-saiba-mais");
  saibaFluxo.append(el("summary", null, "Saiba mais sobre o tipo de solicitação"), avisoFluxo,
    el("p", "op-ajuda", "Financeiro → Contabilidade/Bancos: envie extratos (OFX, CSV ou PDF digital Santander Empresas), relação de pagamentos, comprovantes e notas/boletos/guias/recibos. "
      + "Execução local; empresa real exige cadastro conferido e piloto autorizado em Empresas."));
  form.append(saibaFluxo);
  const inpComp = campo("Competência", el("input"));
  inpComp.type = "month";
  const inpArq = campo("Documentos", el("input"), "");
  inpArq.type = "file";
  inpArq.multiple = true;
  const ajudaArq = inpArq.nextSibling;
  const listaArq = el("ul", "op-arquivos");
  form.append(listaArq);
  const txtInstr = campo("Instrução ao Coordenador", el("textarea"), "Ex.: Chegaram documentos referentes a esta competência. Inicie o processamento.");
  txtInstr.rows = 3;
  txtInstr.maxLength = 2000;
  const conf = el("label", "op-confirma");
  const chk = el("input");
  chk.type = "checkbox";
  conf.append(chk, el("span", null, "Vou conferir manualmente 100% do resultado. O processamento para em AGUARDANDO SUPERVISOR; nada é lançado nem importado."));
  form.append(conf);
  // resumo antes de iniciar: evita empresa ou competência erradas
  const resumoEnvio = el("div", "op-resumo-envio");
  resumoEnvio.dataset.resumoEnvio = "true";
  form.append(resumoEnvio);
  const MESES_ENVIO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  function atualizarResumoEnvio() {
    resumoEnvio.textContent = "";
    const emp = empresasDoFormulario.find((e) => e.id === selEmpresa.value);
    const comp = /^\d{4}-\d{2}$/.test(inpComp.value) ? `${MESES_ENVIO[+inpComp.value.slice(5) - 1]}/${inpComp.value.slice(0, 4)}` : "não informada";
    resumoEnvio.append(el("strong", null, "Você está iniciando"));
    const dl = el("dl");
    [["Empresa", emp ? emp.nome : "não selecionada"], ["Competência", comp.charAt(0).toUpperCase() + comp.slice(1)], ["Documentos", String(inpArq.files.length)]]
      .forEach(([k, v]) => dl.append(el("dt", null, k), el("dd", null, v)));
    resumoEnvio.append(dl, el("p", "op-ajuda", "O Coordenador irá analisar e distribuir o trabalho. Você acompanha cada etapa na tela seguinte."));
  }
  const acoes = el("div", "op-acoes");
  const btnIniciar = el("button", "op-iniciar", "Iniciar processamento");
  btnIniciar.type = "button";
  acoes.append(btnIniciar);
  form.append(acoes);
  const msg = el("p", "op-msg");
  msg.setAttribute("role", "status");
  form.append(msg);
  const recentes = el("div", "op-recentes");
  recentes.hidden = true;
  document.body.append(recentes);

  const visao = el("div", "op-sol");
  visao.hidden = true;
  painel.append(cabeca, form, visao);
  document.body.append(painel);

  let limites = { arquivo: 0, lote: 0, arquivos: 0, formatos: [] };
  let acompanhando = null;
  let temporizador = null;
  let empresasDoFormulario = [];
  let enviando = false;

  function conferirDisponibilidade() {
    const emp = empresasDoFormulario.find(e=>e.id===selEmpresa.value);
    const pendente = !!emp?.cadastro_pendente;
    const vazio = empresasDoFormulario.length===0;
    avisoCadastro.hidden=!(pendente||vazio);
    motivoCadastro.textContent=vazio?'Nenhuma empresa cadastrada. Cadastre a primeira empresa para começar.':pendente?'A empresa está cadastrada. Para solicitar o serviço: '+emp.motivos.join(' '):'';
    concluirCadastro.textContent=vazio?'Cadastrar primeira empresa':'Concluir cadastro da empresa';
    inpArq.disabled=pendente||vazio||enviando;
    btnIniciar.disabled=pendente||vazio||enviando;
    return !(pendente||vazio);
  }
  selEmpresa.addEventListener('change',conferirDisponibilidade);
  [selEmpresa, inpComp, inpArq].forEach((x) => { x.addEventListener("change", atualizarResumoEnvio); x.addEventListener("input", atualizarResumoEnvio); });

  let ampliado = false;
  function sincronizarLargura() {
    const sol = !painel.hidden && !visao.hidden;
    document.body.classList.toggle("prime-acomp", sol);
    document.body.classList.toggle("prime-ampliado", sol && ampliado);
    painel.classList.toggle("ampliado", sol && ampliado);
    ampliar.hidden = !sol;
    ampliar.textContent = ampliado ? "Recolher painel" : "Ampliar painel";
    ampliar.setAttribute("aria-pressed", String(ampliado));
    ampliar.title = ampliado ? "Volta à largura normal" : "Alarga o painel para analisar as tabelas; o escritório continua visível";
  }
  ampliar.addEventListener("click", () => { ampliado = !ampliado; sincronizarLargura(); });
  new MutationObserver(sincronizarLargura).observe(painel, { attributes: true, attributeFilter: ["hidden"] });

  function abrir(modoVisao) {
    painel.hidden = false;
    form.hidden = modoVisao === "sol";
    visao.hidden = modoVisao !== "sol";
    titulo.textContent = modoVisao === "sol" ? "Acompanhamento da solicitação" : "Nova solicitação ao Coordenador Geral";
    sincronizarLargura();
  }
  botao.addEventListener("click", () => { carregarEstado(); abrir("form"); });
  fechar.addEventListener("click", () => { painel.hidden = true; });

  inpArq.addEventListener("change", () => {
    listaArq.textContent = "";
    Array.from(inpArq.files).forEach((f) => listaArq.append(el("li", null, `${f.name} · ${mb(f.size)}`)));
  });

  async function carregarEstado() {
    try {
      const e = await api("GET", "/estado");
      limites = e.limites;
      ajudaArq.textContent = `Formatos: ${limites.formatos.join(" ")} · até ${mb(limites.arquivo)} por arquivo, ${limites.arquivos} arquivos e ${mb(limites.lote)} por lote.`;
      inpArq.accept = limites.formatos.join(",");
      const atual = selEmpresa.value;
      selEmpresa.textContent = "";
      empresasDoFormulario=[...e.empresas,...(e.empresas_pendentes||[])];
      empresasDoFormulario.forEach((emp) => {
        const o = el("option", null, `${emp.id} · ${emp.nome} (${emp.cadastro_pendente?'CADASTRO PENDENTE':emp.piloto ? "PILOTO REAL SUPERVISIONADO" : emp.modo + " · fictícia"})`);
        o.value = emp.id;
        selEmpresa.append(o);
      });
      if (atual) selEmpresa.value = atual;
      conferirDisponibilidade();
      atualizarResumoEnvio();
      recentes.textContent = "";
      if (e.recentes.length) {
        recentes.append(el("h3", null, "Solicitações recentes"));
        e.recentes.forEach((r) => {
          const b = el("button", "op-recente", `${r.sol} · ${r.empresa} · ${r.competencia} · ${ROTULOS[r.estado] || r.estado}`);
          b.type = "button";
          b.addEventListener("click", () => acompanhar(r.sol));
          recentes.append(b);
        });
      }
      recentesApi = e.recentes;
      refletir();
      // A atualização de estado não altera a navegação escolhida pelo usuário.
    } catch (err) {
      msg.textContent = err.message;
    }
  }

  btnIniciar.addEventListener("click", async () => {
    if(!conferirDisponibilidade())return;
    const arquivos = Array.from(inpArq.files);
    msg.textContent = "";
    if (!selEmpresa.value || !selFluxo.value || !inpComp.value || !arquivos.length || !txtInstr.value.trim()) {
      msg.textContent = "Selecione empresa e fluxo; preencha competência, documentos e instrução.";
      return;
    }
    if (!chk.checked) {
      msg.textContent = "Confirme a conferência humana do resultado.";
      return;
    }
    enviando=true;conferirDisponibilidade();
    let lote = null;
    try {
      lote = (await api("POST", "/lotes", { empresa: selEmpresa.value, competencia: inpComp.value, instrucao: txtInstr.value, fluxo: selFluxo.value })).lote;
      const itens = listaArq.querySelectorAll("li");
      for (let i = 0; i < arquivos.length; i++) {
        const f = arquivos[i];
        itens[i].textContent = `${f.name} · enviando…`;
        msg.textContent = `Enviando documento ${i + 1} de ${arquivos.length}…`;
        const buffer = await f.arrayBuffer();
        const r = await api("PUT", `/lotes/${lote}/arquivos`, buffer, { "X-Nome-Arquivo": encodeURIComponent(f.name), "X-Sha256": await sha256(buffer) });
        itens[i].textContent = `${f.name} → ${r.nome_interno} · recebido` + (r.duplicado_de ? ` · ATENÇÃO: idêntico a arquivo da ${r.duplicado_de.sol}` : "");
      }
      msg.textContent = "Documentos recebidos. Encaminhando ao Coordenador…";
      const r = await api("POST", `/lotes/${lote}/iniciar`, { conferencia_humana: true });
      inpArq.value = "";
      listaArq.textContent = "";
      acompanhar(r.sol);
    } catch (err) {
      msg.textContent = err.message;
      if (lote) {
        try { await api("DELETE", `/lotes/${lote}`); } catch (e) { /* lote já iniciado ou removido */ }
      }
    } finally {
      enviando=false;conferirDisponibilidade();
    }
  });

  // ---------------------------------------------------------------- acompanhamento
  function acompanhar(sol) {
    acompanhando = sol;
    abrir("sol");
    clearTimeout(temporizador);
    atualizar();
  }

  async function atualizar() {
    if (!acompanhando) return;
    try {
      const d = await api("GET", `/solicitacoes/${acompanhando}`);
      renderizar(d);
      foco = d;
      refletir();
      // qualquer etapa em andamento (Documentos, áreas, Contabilidade, Conciliação): a tela se atualiza sozinha
      if (d.execucao.status === "EM_EXECUCAO" || /_EM_ANDAMENTO$/.test(d.estado || "")) temporizador = setTimeout(atualizar, 3000);
    } catch (err) {
      visao.textContent = "";
      visao.append(el("p", "op-msg", err.message));
      temporizador = setTimeout(atualizar, 5000);
    }
  }

  function tabela(cabecalho, linhas) {
    const t = el("table", "op-tabela");
    const tr = el("tr");
    cabecalho.forEach((c) => tr.append(el("th", null, c)));
    t.append(tr);
    linhas.forEach((l) => {
      const r = el("tr");
      l.forEach((c) => r.append(el("td", null, c)));
      t.append(r);
    });
    return t;
  }

  function renderizar(d) {
    if (d.fluxo === "FINANCEIRO_BANCOS" || (d.etapas && d.etapas.fiscal && d.etapas.fiscal.status !== 'NAO_APLICAVEL') || (d.plano_etapas || []).length) {
      renderizarFluxoFinanceiro(d);         // tela própria: resumo, decisões, trabalho por área, auditoria
      return;
    }
    visao.textContent = "";
    const voltar = el("button", "op-recente", "← Solicitações");
    voltar.type = "button";
    voltar.addEventListener("click", () => { acompanhando = null; clearTimeout(temporizador); painel.hidden = true; window.dispatchEvent(new CustomEvent('prime-consulta')); });
    const exec = d.execucao.status === 'INDISPONIVEL' ? 'Registro preservado; arquivos da execução indisponíveis' : d.execucao.status === "EM_EXECUCAO" ? "Em processamento pelo Agente de Documentos…" : d.execucao.status === "FALHOU" ? "Execução com falha"
      : d.estado === "FINANCEIRO_EM_ANDAMENTO" ? "Documentos concluído · Financeiro conferindo…"
      : d.estado === "BANCOS_EM_ANDAMENTO" ? "Financeiro concluído · Contabilidade/Bancos preparando os lançamentos…" : "Execução concluída";
    visao.append(voltar, el("h3", "op-sol-id", `${d.sol} · ${ROTULOS[d.estado] || d.estado}`));
    const dl = el("dl", "campos");
    [["Empresa", d.empresa], ["Competência", d.competencia], ["Modo", d.modo + (d.piloto ? ` · ${d.piloto}` : "")], ["Execução", exec],
     ["Início", hora(d.execucao.inicio)], ["Fim", hora(d.execucao.fim)], ["Instrução", d.instrucao]].forEach(([k, v]) => {
      dl.append(el("dt", null, k), el("dd", null, v || "—"));
    });
    visao.append(dl);
    const tentativas = d.tentativas || [];
    const hist = el("section", "op-tentativas");
    hist.append(el("h4", null, "Tentativas auditadas"));
    if (tentativas.length) hist.append(lista(tentativas.map(t => `Tentativa ${t.numero} · ${t.status || "registrada"} · ${hora(t.criada_em)}${t.motivo ? ` · ${t.motivo}` : ""}`)));
    const pode = d.execucao.status !== "EM_EXECUCAO" && !(tentativas.length && ["PREPARADA", "EM_EXECUCAO"].includes(tentativas[tentativas.length - 1].status));
    if (pode) {
      const b = el("button", "op-acao", "Reprocessar solicitação");
      b.type = "button";
      b.addEventListener("click", async () => {
        const motivo = window.prompt("Motivo do reprocessamento auditado:", "Atualização do leitor de documentos.");
        if (motivo === null) return;
        if (!window.confirm("Uma nova tentativa será criada. O resultado anterior será preservado.")) return;
        try { await api("POST", `/solicitacoes/${d.sol}/reprocessar`, { confirmado: true, motivo, solicitante: "Supervisor" }); await atualizar(); }
        catch (err) { window.alert(err.message); }
      });
      hist.append(b);
    }
    visao.append(hist);
    if (d.documentos_local) visao.append(detalhes('Evidências da execução local e limitações', false,
      lista(d.documentos_local.itens.map(i => `${i.arquivo}: ${i.tipo} · ${i.leitura} · ${i.conteudo_utilizavel ? 'conteúdo extraído para conferência' : 'conteúdo não utilizável'}`)),
      lista(d.documentos_local.limitacoes)));
    if (d.mensagem) visao.append(el("blockquote", "mensagem", d.mensagem));
    if (d.motivos.length) {
      visao.append(el("h4", null, `Motivos da decisão do Coordenador (${d.motivos.length})`));
      const ul = el("ul", "op-lista");
      d.motivos.forEach((m) => ul.append(el("li", null, m)));
      visao.append(ul);
    }
    visao.append(el("h4", null, `Documentos recebidos (${d.arquivos.length})`));
    const codigo = (nome) => d.inventario.find((i) => i.nome === nome) || {};
    visao.append(tabela(["Arquivo enviado", "Nome interno", "Leitura do extrator", "Marcações", "SHA-256"],
      d.arquivos.map((a) => [a.nome_original, a.nome_interno, codigo(a.nome_interno).leitura || "—",
        (codigo(a.nome_interno).marcacoes || []).join(", ") || "—", a.sha256.slice(0, 12) + (a.duplicado_de ? ` (idêntico: ${a.duplicado_de.sol})` : "")])));
    if (d.execucao.status !== "EM_EXECUCAO") {
      visao.append(el("h4", null, `Pendências propostas pelo agente (${d.pendencias.length})`));
      if (d.pendencias.length) visao.append(tabela(["Nº", "Competência", "Tipo", "Descrição", "Documento", "Responsável", "Status"], d.pendencias));
      else visao.append(el("p", "nd", "Nenhuma."));
      const a = d.execucao.auditoria || {};
      visao.append(el("h4", null, "Auditoria da execução"));
      const au = el("ul", "op-lista");
      au.append(el("li", null, `Ferramentas do agente: ${Object.entries(a.ferramentas || {}).map(([k, v]) => `${k} ${v}`).join(", ") || "—"}`));
      au.append(el("li", null, `Chamadas bloqueadas pelo guarda: ${a.bloqueios ?? "—"}`));
      au.append(el("li", null, `Duração: ${a.duracao_s ?? "—"} s`));
      (a.problemas || []).forEach((p) => au.append(el("li", "op-problema", p)));
      if ((d.execucao.documentos_alterados || []).length) au.append(el("li", "op-problema", `Documentos alterados após o recebimento: ${d.execucao.documentos_alterados.join(", ")}`));
      visao.append(au);
      if (d.relatorio) {
        const det = el("details", "op-relatorio");
        det.append(el("summary", null, "Relatório do Agente de Documentos (entregue ao Coordenador)"), el("pre", null, d.relatorio));
        visao.append(det);
      }
      if (d.empresa === "VGROW" && d.piloto) carregarImportacao(d.sol);
    }
  }

  // ---------------------------------------------------------------- Importação (ESPECÍFICA DA VGROW)
  const ROTULOS_CAMPOS = {
    fob: "FOB R$ (DUIMP)", frete: "Frete R$ (DUIMP)", chegada: "Data de chegada (DUIMP)", fatura: "Fatura (ex.: GG/INV/240005007)",
    nfs: "NFs Capital Trade (ex.: 375055/376526)", icms_nf: "ICMS destacado nas NFs R$"
  };

  const STATUS_CAMPO = { OK: "reconhecido", ILEGIVEL: "ILEGÍVEL — confirme ou corrija", AUSENTE: "AUSENTE — informe", CONFLITO: "CONFLITO — escolha/corrija" };

  function exibir(campo, valor) {
    if (valor === null || valor === undefined) return "";
    if (Array.isArray(valor)) return valor.join("/");
    if (["fob", "frete", "icms_nf"].includes(campo)) return Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return String(valor);
  }

  async function carregarImportacao(sol, secaoExistente) {
    const secao = secaoExistente || el("section", "op-importacao");
    if (!secaoExistente) visao.append(secao);
    secao.textContent = "";
    let e;
    try {
      e = await api("GET", `/solicitacoes/${sol}/importacao`);
    } catch (err) {
      secao.append(el("p", "op-msg", err.message));
      return;
    }
    secao.append(el("h4", null, "Importação VGROW (área específica · encaminhamento somente por ação do Supervisor)"));
    if (!e.disponivel) {
      secao.append(el("p", "nd", e.motivo));
      return;
    }
    const rec = e.reconhecimento || { status: "NAO_EXECUTADO", processos: {} };
    if (rec.status === "EM_ANDAMENTO") {
      secao.append(el("p", "op-msg", "Reconhecendo automaticamente FOB, frete, chegada, fatura, NFs e ICMS (texto do PDF ou OCR local)…"));
      setTimeout(() => { if (acompanhando === sol) carregarImportacao(sol, secao); }, 4000);
      return;
    }
    secao.append(el("p", "op-ajuda", rec.status === "PRONTO"
      ? "Campos reconhecidos automaticamente no \"Documentos.pdf\" (DUIMP e NFs). Confira; intervenha só nos campos destacados. Comparativo e numerário são lidos pelo extrator."
      : "Reconhecimento automático indisponível para esta SOL: informe os campos conferindo o documento."));
    mostrarEvidencias(secao, sol, e);
    const entradas = {};
    const confirmacoes = {};
    e.processos.forEach((p) => {
      const caixa = el("fieldset", "op-processo");
      caixa.append(el("legend", null, p.processo));
      caixa.append(el("p", "op-ajuda", p.documentos.map((x) => `${x.tipo}: ${x.nome}`).join(" · ")));
      (rec.pendencias || {})[p.processo] && caixa.append(el("p", "op-problema", rec.pendencias[p.processo].join(" ")));
      entradas[p.processo] = {};
      confirmacoes[p.processo] = {};
      e.campos.forEach((c) => {
        const r = (rec.processos[p.processo] || {})[c] || { status: "AUSENTE", valor: null };
        const inp = el("input");
        inp.type = c === "chegada" ? "date" : "text";
        inp.maxLength = 60;
        inp.value = exibir(c, r.valor);
        const l = el("label", "op-campo" + (r.status === "OK" ? "" : " op-atencao"));
        l.append(el("span", "op-rotulo", ROTULOS_CAMPOS[c]), inp,
          el("span", "op-ajuda", `${STATUS_CAMPO[r.status] || r.status}${r.origem ? " · " + r.origem : ""}${r.confianca ? " · confiança " + Number(r.confianca).toFixed(2) : ""}`
            + (r.candidatos ? ` · candidatos: ${r.candidatos.join(" | ")}` : "") + (r.evidencia ? ` · "${r.evidencia}"` : "")));
        if (r.status !== "OK" && r.valor !== null && r.valor !== undefined) {
          const chk = el("input");
          chk.type = "checkbox";
          const lc = el("label", "op-confirma");
          lc.append(chk, el("span", null, "Confirmo este valor sugerido"));
          l.append(lc);
          confirmacoes[p.processo][c] = chk;
        }
        caixa.append(l);
        entradas[p.processo][c] = inp;
      });
      secao.append(caixa);
    });
    if (e.sem_processo.length) secao.append(el("p", "op-ajuda", `Documentos sem número de processo (OCCT): ${e.sem_processo.join(", ")}`));
    const conferi = el("label", "op-confirma");
    const chkGeral = el("input");
    chkGeral.type = "checkbox";
    conferi.append(chkGeral, el("span", null, "Conferi os campos reconhecidos com o documento. Encaminhar à área de Importação via Coordenador."));
    const msgImp = el("p", "op-msg");
    const botaoImp = el("button", "op-iniciar", "Encaminhar à Importação (via Coordenador)");
    botaoImp.type = "button";
    secao.append(conferi, botaoImp, msgImp);
    const resultados = el("div");
    secao.append(resultados);
    e.execucoes.forEach((x) => mostrarImportacao(resultados, sol, x.n, x.resultado, e.aceites));
    botaoImp.addEventListener("click", async () => {
      if (!chkGeral.checked) {
        msgImp.textContent = "Confirme que conferiu os campos reconhecidos.";
        return;
      }
      const corpo = { processos: {}, confirmados: {}, conferencia_supervisor: true };
      Object.entries(entradas).forEach(([proc, campos]) => {
        corpo.processos[proc] = {};
        corpo.confirmados[proc] = Object.entries(confirmacoes[proc]).filter(([, chk]) => chk.checked).map(([c]) => c);
        Object.entries(campos).forEach(([c, inp]) => { if (inp.value.trim()) corpo.processos[proc][c] = inp.value.trim(); });
      });
      botaoImp.disabled = true;
      msgImp.textContent = "Coordenador encaminhou à Importação. Aguarde…";
      setTimeout(vigiar, 400);
      try {
        const r = await api("POST", `/solicitacoes/${sol}/importacao`, corpo);
        msgImp.textContent = r.coordenador.mensagem_supervisor;
        mostrarImportacao(resultados, sol, r.n, r.resultado, e.aceites);
      } catch (err) {
        msgImp.textContent = err.message;
      } finally {
        botaoImp.disabled = false;
        vigiar();
      }
    });
  }

  async function baixar(sol, n, tipo, nome) {
    const r = await fetch(`/api/solicitacoes/${sol}/importacao/${n}/${tipo}`, { headers: { "X-Prime-Sessao": TOKEN }, cache: "no-store" });
    if (!r.ok) return;
    const url = URL.createObjectURL(await r.blob());
    const a = el("a");
    a.href = url;
    a.download = nome;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }

  function mostrarEvidencias(secao, sol, e) {
    if (e.trava_cadastral) secao.append(el("p", "op-problema", `${e.trava_cadastral.estado}: ${e.trava_cadastral.descricao}`));
    const ev = el("details", "op-relatorio");
    ev.open = true;
    ev.append(el("summary", null, "Evidências complementares (o relatório original de Documentos é preservado acima)"));
    ev.append(tabela(["Documento", "Estado", "Extrator", "Leitura específica"], e.evidencias_complementares.map((x) => [x.arquivo, x.estado, x.leitura_extrator || "—",
      x.leitura_especifica ? `${x.leitura_especifica.paginas} pág. · submetidas ao OCR: ${x.leitura_especifica.submetidas_ocr.length} · campos identificados nas págs `
        + `${x.leitura_especifica.com_campos_identificados.join(", ") || "—"} · sem campos: ${x.leitura_especifica.sem_campos_identificados.length} pág. — `
        + x.leitura_especifica.observacao : "—"])));
    secao.append(ev);
    const qp = el("details", "op-relatorio");
    qp.open = true;
    qp.append(el("summary", null, `Quadro de pendências (${e.quadro_pendencias.length}) · texto original preservado; atualizações só por identificador; resolução só por decisão do Supervisor`));
    e.quadro_pendencias.forEach((q) => {
      const bloco = el("div", "op-processo");
      bloco.append(el("p", null, `${q.pendencia} · ${q.estado} · ${q.texto_original.slice(1).join(" | ")}`));
      if (q.atualizacoes.length) bloco.append(tabela(["Item", "Estado", "Evidência", "Não verificado"], q.atualizacoes.map((a) => [a.item, a.estado, a.evidencia, a.nao_verificado])));
      q.decisoes.forEach((d) => bloco.append(el("p", "op-ajuda", `Supervisor: ${d.decisao} em ${hora(d.em)} — ${d.justificativa}`)));
      const sel = el("select");
      ["RESOLVIDA", "REABERTA"].forEach((v) => { const o = el("option", null, v); o.value = v; sel.append(o); });
      const just = el("input");
      just.maxLength = 500;
      just.placeholder = "Justificativa da decisão";
      const b = el("button", "op-recente", "Registrar decisão");
      b.type = "button";
      const m = el("span", "op-msg");
      b.addEventListener("click", async () => {
        try {
          await api("POST", `/solicitacoes/${sol}/pendencias`, { pendencia: q.pendencia, decisao: sel.value, justificativa: just.value });
          carregarImportacao(sol, secao);
        } catch (err) { m.textContent = err.message; }
      });
      bloco.append(sel, just, b, m);
      qp.append(bloco);
    });
    secao.append(qp);
  }

  // Só o ÚLTIMO retorno pode receber aceite. Retornos anteriores mostram o aceite já registrado (mesma chave de valores e
  // documentos) ou que foram substituídos — nunca um botão que o servidor recusaria.
  function mostrarImportacao(caixa, sol, n, r, aceites) {
    const bloco = el("div", "op-imp-resultado");
    bloco.append(el("h4", null, `Retorno da Importação nº ${n} · ${r.modo} · D = C: ${r.validacao_debito_igual_credito ? "SIM" : "NÃO / sem lote fechado"}`));
    bloco.append(tabela(["Processo fechado", "Data", "Histórico", "Débito", "Crédito", "D = C"],
      r.processos_fechados.map((p) => [p.processo, p.data, p.historico, p.debito, p.credito, p.confere ? "SIM" : "NÃO"])));
    r.processos_fechados.forEach((p) => {
      const det = el("details", "op-relatorio");
      det.append(el("summary", null, `${p.processo}: valores, cálculos e lançamentos`));
      det.append(tabela(["Campo", "Valor", "Origem"], Object.entries(p.valores).map(([k, v]) => [k, Array.isArray(v.valor) ? v.valor.join("/") : v.valor, v.origem])));
      det.append(tabela(["Cálculo", "Valor"], Object.entries(p.calculos)));
      det.append(tabela(["Seq", "Conta", "Descrição", "D/C", "Valor", "Histórico"], p.lancamentos.map((l) => [l.seq, l.conta, l.descricao, l.dc, l.valor, l.historico])));
      bloco.append(det);
    });
    if (r.processos_pendentes.length) {
      bloco.append(el("h4", null, "Bloqueios (o processo não entra no TXT)"));
      bloco.append(tabela(["Processo", "Motivos", "Documentos não recebidos"],
        r.processos_pendentes.map((p) => [p.processo, p.motivos.join(" | "), p.documentos_ausentes.join(", ") || "—"])));
    }
    (r.processos_aguardando_aceite || []).forEach((p) => {
      const a = p.aceite_necessario;
      const caixaA = el("div", "op-processo op-atencao");
      caixaA.append(el("p", null, `${p.processo}: AGUARDANDO ACEITE — numerário ${a.num} − saldo ${a.saldo} − total REAL ${a.total_real} = ${a.diferenca}. ${a.motivo}`));
      caixaA.append(el("p", "op-ajuda", `Fontes: numerário ${a.fontes.num}; saldo ${a.fontes.saldo}; total REAL ${a.fontes.total_real}. Valores não ajustados. `
        + "O aceite vale só para estes valores e documentos e não libera bloqueios; débito = crédito continua obrigatório."));
      const registrado = (aceites || {})[p.processo];
      if (registrado && registrado.chave === a.chave) {
        caixaA.append(el("p", "op-ajuda", `Aceite registrado pelo Supervisor em ${hora(registrado.em)} (diferença ${registrado.diferenca}). `
          + "Um retorno posterior já considera este aceite."));
        bloco.append(caixaA);
        return;
      }
      const acao = el("div", "op-aceite-acao");
      const b = el("button", "op-iniciar", `Aceitar a diferença de R$ ${a.diferenca} para ${p.processo}`);
      b.type = "button";
      const m = el("span", "op-msg");
      b.addEventListener("click", async () => {
        b.disabled = true;
        try {
          const x = await api("POST", `/solicitacoes/${sol}/importacao/aceites`, { processo: p.processo, chave: a.chave });
          acao.replaceWith(el("p", "op-ajuda", `Aceite registrado (diferença ${a.diferenca}); veja o retorno nº ${x.n}.`));
          mostrarImportacao(caixa, sol, x.n, x.resultado, aceites);
        } catch (err) { m.textContent = err.message; b.disabled = false; }
      });
      acao.append(b, m);
      caixaA.append(acao);
      bloco.append(caixaA);
    });
    [...r.processos_fechados, ...(r.processos_aguardando_aceite || []), ...r.processos_pendentes].forEach((p) => {
      if (!p.numerario) return;
      const c = p.calculos || {};
      bloco.append(tabela([`${p.processo}`, "Valor", "Fonte / observação"], [
        ["Numerário do PDF", p.numerario.pdf || "—", "padrão da regra"],
        ["Depósito efetivo (Prestação de contas)", p.numerario.deposito_prestacao || "—", "ENTRADA DE NUMERÁRIO"],
        ["VALOR PAGO (comparativo)", p.numerario.pago_comparativo || "—", "somente alerta"],
        ["Numerário usado", p.numerario.usado || "—", p.numerario.motivo || ""],
        ["ICMS cobrado (comparativo)", c.icms_cobrado_comparativo || "—", "campo distinto do destacado"],
        ["ICMS destacado (NFs)", c.icms_destacado_nfs || "—", p.verificacao_nfs ? (p.verificacao_nfs.confere ? "verificado na Prestação de contas" : "diverge da Prestação") : ""],
        ["Desconto 50% s/ destacado", c.desconto_icms_50_sobre_destacado || "—", "arredondamento do gerador validado"]]));
      (p.acompanhamentos || []).forEach((x) => bloco.append(el("p", "op-ajuda", `ACOMPANHAMENTO ${p.processo}: ${x}`)));
    });
    const lista = el("ul", "op-lista");
    r.alertas.forEach((a) => lista.append(el("li", null, `ALERTA: ${a}`)));
    r.divergencias.forEach((a) => lista.append(el("li", "op-problema", `DIVERGÊNCIA: ${a}`)));
    if (r.documentos_sem_processo.length) lista.append(el("li", null, `Sem processo: ${r.documentos_sem_processo.join(", ")}`));
    bloco.append(lista);
    const acoes = el("div", "op-acoes");
    Object.entries(r.arquivos || {}).forEach(([tipo, nome]) => {
      const b = el("button", "op-recente", tipo === "txt" ? `Baixar TXT (SIMULAÇÃO): ${nome}` : `Baixar planilha de conferência: ${nome}`);
      b.type = "button";
      b.addEventListener("click", () => baixar(sol, n, tipo, nome));
      acoes.append(b);
    });
    bloco.append(acoes, el("p", "op-ajuda", "Nada foi liberado nem importado no Domínio. Conferência e aprovação manual do Supervisor."));
    caixa.querySelectorAll(".op-aceite-acao").forEach((x) => x.replaceWith(el("p", "op-ajuda",
      `Substituído pelo retorno nº ${n}: o aceite só vale para a diferença do último retorno.`)));
    caixa.prepend(bloco);
  }

  // ---------------------------------------------------------------- Financeiro → Contabilidade/Bancos (SIMULAÇÃO)
  // Tela em três níveis: (1) resumo e próxima ação; (2) decisões do Supervisor e trabalho por área; (3) evidências e
  // auditoria. A tela só mostra o resultado e envia as decisões; quem registra é o Coordenador (servidor). Nada aqui
  // aprova lançamento, escritura ou importa no Domínio.
  const fmtValor = (v) => (v === null || v === undefined || v === "" ? "—" : Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }));
  const fmtData = (d) => (d && /^\d{4}-\d{2}-\d{2}/.test(d) ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : d || "—");
  const fmtConta = (c) => (c ? `${c.codigo} · ${c.descricao}` : "a definir");
  const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

  // O que falta em um lançamento: decisão possível agora × depende de documento adicional.
  const FALTAS = {
    SEM_REGRA: { agora: true, texto: "regra aprovada ou contrapartida informada para este caso" },
    REGRA_CONFLITANTE: { agora: true, texto: "escolha entre regras conflitantes (informe a contrapartida deste caso)" },
    CONTA: { agora: true, texto: "conta contábil existente no plano de contas" },
    AMBIGUO: { agora: true, texto: "indicação de qual documento corresponde a este movimento" },
    VINCULO_PENDENTE: { agora: true, texto: "conferência do documento candidato e confirmação do vínculo com o pagamento" },
    LEITURA_PENDENTE: { agora: false, texto: "leitura/conferência dos documentos já recebidos; não é ausência de documento" },
    DECISAO_INCOMPATIVEL: { agora: true, texto: "decisão compatível com a direção do movimento" },
    INCOMPATIVEL: { agora: true, texto: "contrapartida compatível com a natureza (a combinação anterior não é válida)" },
    GRUPO_INDEFINIDO: { agora: false, texto: "grupo da conta definido no plano de contas (definição do Supervisor no cadastro)" },
    SUPORTE: { agora: false, texto: "documento que comprove a natureza (nota, guia, recibo ou contrato)" },
    TRANSFERENCIA_SEM_PAR: { agora: false, texto: "extrato da outra conta própria (outra ponta da transferência)" },
    DIVERGENCIA: { agora: false, texto: "documento ou esclarecimento para a divergência apontada" },
    // conta de adiantamento só existe se o Supervisor a indicar em Empresas; a indicação não supre documento
    ADIANTAMENTO_NAO_INDICADO: { agora: false, cadastro: true,
      texto: "conta de adiantamento indicada pelo Supervisor em Empresas (definição no cadastro; não supre o documento)" },
    // documento compartilhado com outra área (Fiscal) cuja análise falhou ou não foi entregue: não é decisão possível agora
    DEPENDE_AREA: { agora: false, area: true, texto: "análise de outra área (documento compartilhado com o Fiscal, ainda sem análise entregue)" },
    OUTRO: { agora: false, texto: "verificação manual (ver detalhes)" }
  };
  // resultados gravados antes da classificação estruturada: mesma regra, aplicada ao texto da pendência
  function codigoFalta(texto) {
    const t = String(texto).normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
    const pares = [["NAO PODE SER VERIFICADA", "GRUPO_INDEFINIDO"], ["NAO E COMPATIVEL", "INCOMPATIVEL"], ["SEM REGRA APROVADA", "SEM_REGRA"], ["REGRAS CONFLITANTES", "REGRA_CONFLITANTE"], ["OUTRA PONTA", "TRANSFERENCIA_SEM_PAR"],
      ["AMBIGUA", "AMBIGUO"], ["INCOMPATIVEL", "DECISAO_INCOMPATIVEL"], ["NAO EXISTE NO PLANO", "CONTA"], ["SEM CONTA CONTABIL", "CONTA"],
      ["EXIGE DOCUMENTO DA NATUREZA", "SUPORTE"], ["SEM DOCUMENTO DE SUPORTE", "SUPORTE"], ["SEM DOCUMENTO DA NATUREZA", "SUPORTE"],
      ["COMPROVE A ORIGEM", "SUPORTE"], ["DIVERGENCIA", "DIVERGENCIA"]];
    const achado = pares.find(([k]) => t.includes(k));
    return achado ? achado[1] : "OUTRO";
  }
  const codigosDe = (l) => (l.faltas_codigos && l.faltas_codigos.length ? l.faltas_codigos : [...new Set(l.pendencias.map(codigoFalta))]);
  // texto do que falta, no caso concreto (recebimento: origem; pagamento: natureza)
  const textoFalta = (c, m) => (c === "SUPORTE" && m.direcao === "CREDITO" ? "documento que comprove a origem do recebimento"
    : c === "SUPORTE" && m.situacao === "COMPROVANTE_SEM_NATUREZA" ? "documento da natureza do pagamento (nota, guia, recibo ou contrato)"
      : (FALTAS[c] || FALTAS.OUTRO).texto);
  const TIPO_DECISAO = { VINCULAR: "confirmação de vínculo", CONTRAPARTIDA: "contrapartida deste caso" };

  const GLOSSARIO = [
    ["Proposto", "Lançamento montado com regra aprovada, conta do plano e documento de suporte. Pronto para a sua conferência; ainda não foi escriturado."],
    ["Incompleto", "Falta algo (regra, conta, documento ou decisão sua). Aparece na fila de decisões com o que falta."],
    ["Aguardando Supervisor", "O processamento terminou e nada avança sem a sua conferência ou decisão."],
    ["Concluído (etapa)", "A área terminou e entregou o resultado. Não significa aprovado nem escriturado."],
    ["Conciliação", "Confere as propostas com suportes, saldos e terceiros (grupos A–E). Conferido no alcance da SIMULAÇÃO não é aprovação nem escrituração."]
  ];
  const NATUREZAS = {
    LIQUIDACAO_OBRIGACAO: ["DEBITO", "Pagamento de obrigação já registrada (sem nova despesa)"],
    DESPESA: ["DEBITO", "Despesa reconhecida e paga no ato"],
    RECEBIMENTO: ["CREDITO", "Recebimento de valor já registrado a receber"],
    RECEITA: ["CREDITO", "Receita reconhecida e recebida no ato"],
    ADIANTAMENTO_FORNECEDOR: ['DEBITO', 'Adiantamento a fornecedor; documento pendente'],
    ADIANTAMENTO_CLIENTE: ['CREDITO', 'Adiantamento de cliente; documento pendente']
  };
  const SITUACAO_TXT = {
    COM_SUPORTE: "com documento de suporte",
    COMPROVANTE_SEM_NATUREZA: "pagamento comprovado, sem documento da natureza",
    SEM_SUPORTE: "sem documento de suporte",
    AMBIGUO: "correspondência ambígua",
    TRANSFERENCIA_PROPRIA: "transferência entre contas próprias",
    TRANSFERENCIA_PROPRIA_SEM_PAR: "transferência para conta própria sem a outra ponta"
  };
  const PENDENCIAS_INFORMATIVAS = new Set(["DOCUMENTO_ILEGIVEL", "CONTA_NAO_CADASTRADA", "ISOLAMENTO", "DOCUMENTO_NAO_IDENTIFICADO",
    "FORMATO_NAO_SUPORTADO", "DOCUMENTO_INCOMPLETO", "DADO_AUSENTE", "DOCUMENTO_CANCELADO", "EXTRATO_INCOMPLETO", "EXTRATO_INCONSISTENTE"]);

  function lista(itens, classe) {
    const ul = el("ul", "op-lista");
    itens.forEach((t) => ul.append(el("li", classe || null, t)));
    return ul;
  }

  function detalhes(titulo, aberto, ...filhos) {
    const d = el("details", "op-relatorio");
    d.open = !!aberto;
    d.append(el("summary", null, titulo), ...filhos);
    return d;
  }

  function campoRotulado(rotulo, controle) {
    const l = el("label", "ac-campo");
    l.append(el("span", "op-rotulo", rotulo), controle);
    return l;
  }

  function entradaJustificativa() {
    const j = el("textarea");
    j.rows = 2;
    j.maxLength = 500;
    j.placeholder = "Justificativa (obrigatória, fica registrada na SOL)";
    return j;
  }

  async function enviarDecisao(sol, corpo, msg) {
    try {
      const r = await api("POST", `/solicitacoes/${sol}/financeiro/decisoes`, corpo);
      msg.textContent = `${r.mensagem} Ao terminar, este cartão mostra o novo estado do movimento e as pendências restantes.`;
      setTimeout(vigiar, 300);
      setTimeout(() => { if (acompanhando === sol) atualizar(); }, 800);
    } catch (err) { msg.textContent = err.message; }
  }

  // Fila: um item por movimento (sem repetir o mesmo problema em vários lugares).
  const PRECISA_CONTRAPARTIDA = ["SEM_REGRA", "REGRA_CONFLITANTE", "CONTA", "DECISAO_INCOMPATIVEL", "INCOMPATIVEL"];
  const GRUPO_TXT = { ATIVO: "ativo", PASSIVO: "passivo", RECEITA: "receita", DESPESA: "despesa", CUSTO: "custo" };

  const ehAdiantamento = (natureza) => String(natureza).startsWith("ADIANTAMENTO_");
  // conta(s) de adiantamento indicadas EXPRESSAMENTE pelo Supervisor em Empresas (nada é presumido pelo grupo do plano)
  const contasAdiantamento = (e, natureza) => ((e.contas_adiantamento || {})[natureza] || []).map(String);

  function contasCompativeis(e, natureza) {
    const regra = (e.compatibilidade || {})[natureza];
    if (!regra) return [];
    const indicadas = contasAdiantamento(e, natureza);
    return (e.plano_contas || []).filter((c) => regra.grupos.includes(c.grupo) && !(e.contas_banco || []).includes(c.codigo)
      && (!ehAdiantamento(natureza) || indicadas.includes(String(c.codigo))));
  }

  // naturezas de adiantamento da direção sem conta indicada: explicadas no cartão, nunca oferecidas
  function adiantamentoSemIndicacao(e, direcao) {
    const nomes = { ADIANTAMENTO_FORNECEDOR: "adiantamento a fornecedor", ADIANTAMENTO_CLIENTE: "adiantamento de cliente" };
    const faltam = Object.entries(NATUREZAS).filter(([k, [dir]]) => dir === direcao && ehAdiantamento(k) && !contasCompativeis(e, k).length).map(([k]) => nomes[k] || k);
    return faltam.length ? `Classificar como ${faltam.join(" ou ")} não está disponível: o Supervisor precisa indicar a conta de adiantamento desta `
      + "natureza em Empresas (contas de adiantamento). Sem essa indicação, nada é presumido. Mesmo com a conta indicada, o adiantamento não supre "
      + "o documento: o lançamento continua incompleto até o documento chegar." : "";
  }

  // naturezas da direção do movimento e se há ao menos uma conta compatível no plano
  function opcoesContrapartida(e, direcao) {
    return Object.entries(NATUREZAS).filter(([tipo, [dir]]) => dir === direcao)
      .map(([k, [, texto]]) => ({ natureza: k, texto, grupos: ((e.compatibilidade || {})[k] || { grupos: [] }).grupos, contas: contasCompativeis(e, k) }));
  }

  function semContaCompativel(opcoes, direcao) {
    return `Para informar a contrapartida deste ${direcao === "CREDITO" ? "recebimento" : "pagamento"} é preciso uma conta do plano de contas desta `
      + `empresa compatível com a natureza: ${opcoes.map((o) => `${o.texto.toLowerCase()} → ${ehAdiantamento(o.natureza) ? "conta indicada pelo Supervisor em Empresas (grupo "
        + o.grupos.map((g) => GRUPO_TXT[g] || g).join(" ou ") + ")" : `grupo ${o.grupos.map((g) => GRUPO_TXT[g] || g).join(" ou ")}`}`).join("; ")}. `
      + "O plano atual não tem nenhuma conta compatível (contas bancárias não contam). O Supervisor precisa definir ou incluir essa conta no "
      + "plano de contas do cliente. A decisão fica pendente; nenhuma classificação foi presumida.";
  }

  // seletor natureza → conta: só contas compatíveis com a natureza escolhida; sem conta compatível, nada a enviar
  function seletorNaturezaConta(e, direcao, regraAutomatica = false) {
    const opcoes = opcoesContrapartida(e, direcao).filter((o) => o.contas.length && (!regraAutomatica || !o.natureza.startsWith('ADIANTAMENTO_')));
    const natureza = el("select");
    const vazio = el("option", null, "— selecione a natureza —");
    vazio.value = "";
    natureza.append(vazio);
    opcoes.forEach((o) => { const x = el("option", null, `${o.texto} (conta do grupo ${o.grupos.map((g) => GRUPO_TXT[g] || g).join(" ou ")})`); x.value = o.natureza; natureza.append(x); });
    const conta = el("select");
    const preencher = () => {
      conta.textContent = "";
      const o = opcoes.find((x) => x.natureza === natureza.value);
      const v = el("option", null, o ? "— selecione a conta —" : "— escolha a natureza primeiro —");
      v.value = "";
      conta.append(v);
      (o ? o.contas : []).forEach((c) => { const x = el("option", null, `${c.codigo} · ${c.descricao} (${GRUPO_TXT[c.grupo] || c.grupo})`); x.value = c.codigo; conta.append(x); });
      conta.disabled = !o;
    };
    natureza.addEventListener("change", preencher);
    preencher();
    return { natureza, conta, possivel: opcoes.length > 0 };
  }

  function montarFila(e) {
    const f = e.financeiro;
    const b = e.bancos;
    if (!f || !b) return [];
    const movs = Object.fromEntries(f.movimentos.map((m) => [m.id, m]));
    return b.lancamentos.filter((l) => l.status !== "PROPOSTO").map((l) => {
      const m = movs[l.movimentos[0]] || {};
      const codigos = codigosDe(l);
      const sugestoes = f.sugestoes.filter((s) => s.movimento === m.id);
      const ambiguas = f.ambiguas.filter((a) => a.origem === m.id || (a.candidatos || []).includes(m.id));
      const transferencia = l.movimentos.length > 1 || m.situacao === "TRANSFERENCIA_PROPRIA_SEM_PAR";
      const precisaContra = !transferencia && codigos.some((c) => PRECISA_CONTRAPARTIDA.includes(c));
      const contraPossivel = precisaContra && opcoesContrapartida(e, m.direcao).some((o) => o.contas.length);
      // decisão parcial só quando há algo que o Supervisor pode registrar agora (vínculo ou contrapartida compatível)
      const vinculo = sugestoes.length > 0 || ambiguas.length > 0;
      // depende de outra área (análise fiscal não entregue): nenhuma decisão é possível agora
      const area = codigos.some((c) => (FALTAS[c] || {}).area);
      const agora = (vinculo || contraPossivel) && !area;
      const cadastro = (precisaContra && !contraPossivel) || codigos.includes("GRUPO_INDEFINIDO") || codigos.some((c) => (FALTAS[c] || {}).cadastro);
      return { l, m, codigos, sugestoes, ambiguas, agora, cadastro, area, precisaContra, contraPossivel, transferencia,
               documento: codigos.some((c) => !(FALTAS[c] || {}).agora && !(FALTAS[c] || {}).cadastro && !(FALTAS[c] || {}).area) };
    }).sort((a, b) => String(a.m.data).localeCompare(String(b.m.data)));
  }

  function oQueAconteceu(item) {
    const { m, l } = item;
    const valor = fmtValor(m.valor);
    if (m.documentacao_inconclusiva?.length) return `Movimento de ${valor} com documentos já recebidos cuja leitura ou identificação ainda está pendente. Não foi considerado ausência confirmada de suporte.`;
    if (m.situacao === "AMBIGUO") return `Um documento corresponde a mais de um movimento de ${valor} (mesmo valor e data). É preciso indicar qual.`;
    if (m.situacao === "TRANSFERENCIA_PROPRIA_SEM_PAR") return `Transferência de ${valor} para conta própria sem a outra ponta no lote.`;
    if (m.direcao === "CREDITO") return `Entrada de ${valor} no extrato sem documento que identifique a origem.`;
    if (m.situacao === "COMPROVANTE_SEM_NATUREZA") return `Pagamento de ${valor} comprovado pelo comprovante, mas sem documento que mostre a natureza da despesa.`;
    if (m.situacao === "SEM_SUPORTE") return `Pagamento de ${valor} saiu do extrato sem documento de suporte identificado.`;
    if (item.codigos.includes("CONTA")) return `Pagamento de ${valor} com suporte, mas a regra aponta uma conta que não existe no plano.`;
    if (item.codigos.includes("DIVERGENCIA")) return `Movimento de ${valor} com divergência na conferência financeira.`;
    return `A proposta de ${valor} não pôde ser completada (${l.status.toLowerCase()}).`;
  }

  function cartaoDecisao(sol, item, n, e) {
    const { m, l } = item;
    const art = el("article", "ac-decisao" + (item.agora ? " agora" : " documento"));
    art.dataset.movimento = m.id;
    const cab = el("header", "ac-decisao-cab");
    // o que continua aberto mesmo depois de uma decisão sua (documento/divergência não se resolvem por decisão)
    // sem conta compatível no plano, "informar contrapartida" não é possível: a falta passa a ser a definição no cadastro
    const semConta = item.precisaContra && !item.contraPossivel;
    const contaCadastro = "conta compatível no plano de contas (definição do Supervisor)";
    const faltas = item.codigos.filter((c) => !(semConta && PRECISA_CONTRAPARTIDA.includes(c))).map((c) => textoFalta(c, m))
      .concat(semConta ? [contaCadastro] : []);
    const abertas = item.codigos.filter((c) => !(FALTAS[c] || {}).agora).map((c) => textoFalta(c, m))
      .concat(semConta ? [contaCadastro] : []);
    cab.append(el("span", "ac-num", `#${n}`), el("strong", "ac-valor", fmtValor(m.valor)), el("span", null, fmtData(m.data)),
      el("span", "ac-chip " + (item.agora ? "ac-chip-agora" : "ac-chip-doc"),
        item.agora ? "Decisão parcial possível agora" : item.area ? "Depende de outra área" : item.cadastro ? "Depende de definição no cadastro" : "Depende de documento"));
    art.append(cab);
    if (item.agora) {
      art.append(el("p", "ac-restante" + (abertas.length ? "" : " ok"), abertas.length
        ? `Mesmo após a sua decisão, continuará aberto: ${abertas.join("; ")}.`
        : "Após a sua decisão, a proposta pode ficar completa (confirmado na nova tentativa)."));
    }
    // estado do movimento depois das decisões já registradas
    const registradas = (e.decisoes || {})[m.id] || [];
    if (registradas.length) {
      const ult = registradas[registradas.length - 1];
      const conta = ult.conta ? (e.plano_contas || []).find((c) => c.codigo === ult.conta) : null;
      const caixaD = el("div", "ac-pos-decisao");
      caixaD.append(el("p", "ac-pos-titulo", `Situação após a sua decisão (${hora(ult.em)})`),
        el("p", null, `Você registrou: ${TIPO_DECISAO[ult.tipo] || ult.tipo}${conta ? ` — ${conta.codigo} · ${conta.descricao}` : ""}`
          + `${ult.natureza_tipo ? ` (${(NATUREZAS[ult.natureza_tipo] || [null, ult.natureza_tipo])[1]})` : ""}. Vale só para este movimento.`),
        el("p", null, `Estado atual do movimento: ${l.status === "PROPOSTO" ? "Proposto" : "Incompleto"} · Débito ${fmtConta(l.debito)} · Crédito ${fmtConta(l.credito)}.`),
        el("p", null, `Pendências restantes: ${faltas.join("; ") || "nenhuma"}.`));
      art.append(caixaD);
    }
    art.append(el("p", "ac-oque", oQueAconteceu(item)));
    const dl = el("dl", "ac-dl");
    const linha = (k, v) => dl.append(el("dt", null, k), el("dd", null, v));
    linha("Movimento", `${m.direcao === "DEBITO" ? "Saída" : "Entrada"} · conta ${m.conta} · “${m.descricao}”${m.tipo_banco ? ` [${m.tipo_banco}]` : ""}`);
    linha("Sustentam", (m.documentos || []).map((d) => `${d.arquivo} (${{ LIQUIDACAO: "comprovante", NATUREZA: "natureza", COBRANCA: "cobrança" }[d.papel] || d.papel})`).join(" · ")
      || "nenhum documento vinculado");
    const contra = [...(m.divergencias || []), ...item.ambiguas.map((a) => a.descricao), ...item.sugestoes.map((s) => s.descricao)];
    if (contra.length) linha("Contradizem / alertas", contra.join(" · "));
    linha("Falta", faltas.join(" · "));
    linha("Proposta atual", `Débito ${fmtConta(l.debito)} · Crédito ${fmtConta(l.credito)} · ${l.status === "INCOMPLETO" ? "Incompleto" : l.status}`);
    art.append(dl);

    const acoes = el("div", "ac-acoes");
    // 1) confirmar vínculo — somente este caso
    const candidatos = [];
    item.ambiguas.forEach((a) => {
      if (/^(DOC|REL)-/.test(a.origem) && a.origem !== m.id) candidatos.push({ vinculos: [a.origem], texto: `${a.arquivo || a.origem} pertence a este movimento` });
      else (a.candidatos || []).filter((c) => /^(DOC|REL)-/.test(c)).forEach((c) => {
        const d = (e.financeiro.documentos || []).find((x) => x.id === c);
        candidatos.push({ vinculos: [c], texto: `${(d && d.arquivo) || c} pertence a este movimento` });
      });
    });
    item.sugestoes.forEach((s) => candidatos.push({ vinculos: s.documento ? [s.documento] : s.relacao, texto: `confirmar a sugestão: ${s.descricao}` }));
    if (candidatos.length) {
      const sel = el("select");
      candidatos.forEach((c, i) => { const o = el("option", null, c.texto); o.value = String(i); sel.append(o); });
      const j = entradaJustificativa();
      const b = el("button", "op-iniciar", "Confirmar vínculo (somente este caso)");
      b.type = "button";
      const msg = el("p", "op-msg");
      b.addEventListener("click", () => enviarDecisao(sol, { movimento: m.id, tipo: "VINCULAR", dados: { vinculos: candidatos[Number(sel.value)].vinculos },
        justificativa: j.value }, msg));
      acoes.append(detalhes("Confirmar vínculo — somente este caso", false, campoRotulado("Vínculo", sel), campoRotulado("Justificativa", j),
        el("p", "ac-depois", "Depois: só este movimento passa a ter o vínculo; nova tentativa Financeiro → Bancos. Outros movimentos não mudam. Nada é escriturado."),
        b, msg));
    }
    // 2) contrapartida deste caso e 3) proposta de regra (uso futuro)
    if (item.precisaContra && !item.contraPossivel) {
      acoes.append(el("p", "ac-cadastro", semContaCompativel(opcoesContrapartida(e, m.direcao), m.direcao)));
    }
    if (item.codigos.includes("ADIANTAMENTO_NAO_INDICADO")) {
      acoes.append(el("p", "ac-cadastro", "A conta de adiantamento desta natureza não foi indicada pelo Supervisor. Indique-a em Empresas "
        + "(contas de adiantamento) se for o caso; nada é classificado automaticamente. A indicação não supre o documento: o lançamento continua "
        + "incompleto até o documento chegar."));
    }
    if (item.area) {
      acoes.append(el("p", "ac-depois", "Depende de outra área: o documento é compartilhado com o Fiscal, cuja análise falhou ou ainda não foi "
        + "entregue. Consulte a etapa fiscal (Trabalho por área e Evidências); não há decisão possível agora e nada foi presumido."));
    }
    if (item.precisaContra && item.contraPossivel && !item.area) {
      const semAdiantamento = adiantamentoSemIndicacao(e, m.direcao);
      if (semAdiantamento) acoes.append(el("p", "op-ajuda ac-adiantamento", semAdiantamento));
      else if (opcoesContrapartida(e, m.direcao).some((o) => ehAdiantamento(o.natureza) && o.contas.length)) {
        acoes.append(el("p", "op-ajuda", "Adiantamento: somente a conta indicada pelo Supervisor em Empresas é oferecida. Classificar em adiantamento "
          + "não supre o documento; o lançamento continua incompleto até o documento chegar."));
      }
      // natureza primeiro; a conta só lista contas do grupo compatível (nada pré-selecionado; o servidor valida de novo)
      const { natureza: tipo, conta } = seletorNaturezaConta(e, m.direcao);
      const hist = el("input");
      hist.maxLength = 120;
      hist.placeholder = "Histórico (opcional)";
      const j = entradaJustificativa();
      const b = el("button", "op-iniciar", "Informar contrapartida deste caso");
      b.type = "button";
      const msg = el("p", "op-msg");
      const restante = item.codigos.filter((c) => !(FALTAS[c] || {}).agora).map((c) => textoFalta(c, m));
      b.addEventListener("click", () => enviarDecisao(sol, { movimento: m.id, tipo: "CONTRAPARTIDA",
        dados: { conta: conta.value, natureza_tipo: tipo.value, historico: hist.value }, justificativa: j.value }, msg));
      acoes.append(detalhes("Informar contrapartida deste caso — vale só para este movimento", false,
        campoRotulado("Natureza", tipo), campoRotulado("Conta da contrapartida (somente contas compatíveis)", conta), campoRotulado("Histórico", hist),
        campoRotulado("Justificativa", j),
        el("p", "ac-depois", "Depois: só este movimento usa a conta informada (não vira regra); nova tentativa Financeiro → Bancos. "
          + (restante.length ? `Continuará incompleto enquanto faltar: ${restante.join("; ")}.` : "") + " Nada é escriturado."), b, msg));

      const cond = el("input");
      cond.maxLength = 300;
      cond.value = `direcao=${m.direcao}; historico_contem=${(m.descricao || "").slice(0, 30)}`;
      const { natureza: tipoR, conta: contaR } = seletorNaturezaConta(e, m.direcao, true);
      const exige = el("select");
      [["SIM", "Exige documento de suporte"], ["NAO", "Não exige documento (ex.: tarifa)"]].forEach(([v, t]) => { const o = el("option", null, t); o.value = v; exige.append(o); });
      const histR = el("input");
      histR.maxLength = 120;
      histR.value = m.descricao || "";
      const bp = el("button", "op-recente", "Propor regra (fica PROPOSTA até a sua aprovação)");
      bp.type = "button";
      const mp = el("p", "op-msg");
      bp.addEventListener("click", async () => {
        try {
          const r = await api("POST", `/solicitacoes/${sol}/financeiro/regras`, { condicoes: cond.value, tipo: tipoR.value, contrapartida: contaR.value,
            exige_suporte: exige.value, historico: histR.value, movimento: m.id });
          mp.textContent = `${r.regra} registrada como PROPOSTA. Ela só vale depois da aprovação na seção "Regras propostas".`;
          setTimeout(() => { if (acompanhando === sol) atualizar(); }, 600);
        } catch (err) { mp.textContent = err.message; }
      });
      acoes.append(detalhes("Propor regra para uso futuro — não altera este movimento agora", false,
        campoRotulado("Quando (condições: direcao, tipo_banco, historico_contem, favorecido_cnpj, suporte, conta, obrigacao_contabilizada, competencia_desde)", cond),
        campoRotulado("Natureza", tipoR), campoRotulado("Conta da contrapartida (somente contas compatíveis)", contaR), campoRotulado("Suporte", exige),
        campoRotulado("Histórico", histR),
        el("p", "ac-depois", "Depois: a regra fica PROPOSTA e não é usada. Só passa a valer para movimentos futuros quando você a aprovar com a frase exata."),
        bp, mp));
    }
    if (!item.agora && item.documento) {
      acoes.append(el("p", "ac-depois", "Ação: enviar o documento que falta em uma nova solicitação desta competência. "
        + "O movimento será proposto de novo como revisão (esta proposta fica registrada)."));
    }
    art.append(acoes);
    const extra = detalhes("Origem e trilha deste item", false, lista([
      `Movimento ${m.id} · origem: ${(m.origens || []).join(" | ")}`,
      `Lançamento ${l.id} (${l.natureza_registro || "PROPOSTA_SIMULACAO"}) · ${l.origem || "sem regra aplicada"}`,
      ...(m.fundamentos || []).map((x) => `Fundamento: ${x}`),
      ...l.pendencias.map((x) => `Pendência: ${x}`),
      ...(m.decisoes || []).map((x) => `Decisão registrada em ${hora(x.em)}: ${x.tipo} — ${x.justificativa}`),
      ...(l.revisao_de || []).map((x) => `Revisão de proposta em simulação: ${x.sol}, tentativa nº ${x.tentativa}`)]));
    art.append(extra);
    return art;
  }

  function cartaoRegra(sol, r, e) {
    const conta = (e.plano_contas || []).find((c) => c.codigo === String(r.contrapartida).replace(/\D/g, ""));
    const art = el("article", "ac-decisao regra");
    art.append(el("header", "ac-decisao-cab", `Regra ${r.regra} · PROPOSTA (ainda não é usada)`));
    const dl = el("dl", "ac-dl");
    const linha = (k, v) => dl.append(el("dt", null, k), el("dd", null, v));
    linha("Quando", r.condicoes);
    linha("Lançar", `${(NATUREZAS[r.tipo] || [null, r.tipo])[1]} · contrapartida ${conta ? `${conta.codigo} · ${conta.descricao}` : `${r.contrapartida} (não existe no plano)`}`);
    linha("Suporte", r.exige_suporte === "NAO" ? "não exige documento" : "exige documento de suporte");
    linha("Origem", r.origem);
    art.append(dl);
    const frase = el("input");
    frase.maxLength = 120;
    frase.placeholder = e.frase_aprovacao.replace("<RB-NNN>", r.regra);
    const b = el("button", "op-iniciar", `Aprovar regra ${r.regra} para uso futuro`);
    b.type = "button";
    const msg = el("p", "op-msg");
    b.addEventListener("click", async () => {
      try {
        const x = await api("POST", `/solicitacoes/${sol}/financeiro/regras/aprovar`, { regra: r.regra, frase: frase.value });
        msg.textContent = x.mensagem;
        setTimeout(vigiar, 300);
        setTimeout(() => { if (acompanhando === sol) atualizar(); }, 800);
      } catch (err) { msg.textContent = err.message; }
    });
    art.append(detalhes(`Aprovar regra ${r.regra}`, false, campoRotulado(`Digite a frase exata: ${e.frase_aprovacao.replace("<RB-NNN>", r.regra)}`, frase),
      el("p", "ac-depois", "Depois: a regra passa a valer para os movimentos desta empresa que atenderem às condições, e esta SOL é refeita "
        + "(nova tentativa). Aprovar a regra não aprova lançamentos nem escritura nada."), b, msg));
    return art;
  }

  // Etapas em andamento (estado da SOL) → texto e passo do indicador (① Documentos · ② áreas · ③ Contabilidade · ④ Conciliação · ⑤ Coordenador)
  const ANDAMENTO = {
    FINANCEIRO_EM_ANDAMENTO: ["② Financeiro conferindo as movimentações", 2], DP_EM_ANDAMENTO: ["② DP analisando folha, encargos e provisões", 2],
    FISCAL_EM_ANDAMENTO: ["② Fiscal analisando notas, guias e competências", 2], BANCOS_EM_ANDAMENTO: ["③ Contabilidade/Bancos preparando as propostas", 3],
    CONTABILIDADE_DP_EM_ANDAMENTO: ["③ Contabilidade/DP preparando as propostas a partir do DP", 3],
    CONTABILIDADE_FISCAL_EM_ANDAMENTO: ["③ Contabilidade/Fiscal preparando propostas com o resultado do Fiscal", 3],
    CONCILIACAO_EM_ANDAMENTO: ["④ Conciliação conferindo a escrituração proposta", 4]
  };

  function etapaAtual(d, e) {
    const plano = d.plano_etapas || [];
    if (d.estado === "FECHAMENTO_APROVADO") return ["fim", "⑤ Fechamento aprovado pelo Supervisor (SIMULAÇÃO; nada escriturado)", 5];
    if (plano.length) {
      if (d.revisao_parcial_encerrada) return ['fim', 'Revisão parcial do piloto encerrada — histórico preservado', 5];
      if (d.execucao.status === "EM_EXECUCAO" || d.estado === "DOCUMENTOS_EM_ANDAMENTO") return ["andamento", "① Documentos analisando o lote", 1];
      if (ANDAMENTO[d.estado]) return ["andamento", ...ANDAMENTO[d.estado]];
      const falhas = plano.filter((p) => p.situacao === "FALHOU");
      if (falhas.length) return ["bloqueio", `${falhas.map((p) => NOME_ETAPA[p.etapa]).join(", ")}: falhou (tentativa preservada) — resultado com o ⑤ Supervisor para a sua conferência`,
        PASSO_AREA[falhas[0].etapa] || 3];
      if (d.estado === "AGUARDANDO_SUPERVISOR") return ["fim", "⑤ Supervisor — aguardando a sua conferência e aprovação (nada aprovado nem escriturado)", 5];
    }
    if(d.etapas && ['fiscal','contabilfiscal'].some(k=>d.etapas[k]?.status==='FALHOU')) return ['bloqueio','Etapa fiscal falhou; consulte a causa e os documentos. Tentativa preservada',3];
    if(d.estado==='FISCAL_EM_ANDAMENTO') return ['andamento','Fiscal analisando notas, guias e competências',2];
    if(d.estado==='CONTABILIDADE_FISCAL_EM_ANDAMENTO') return ['andamento','Contabilidade preparando propostas com o resultado do Fiscal',3];
    if(!e && d.fiscal && d.estado==='AGUARDANDO_SUPERVISOR') return ['fim','Resultado fiscal aguardando sua conferência',5];
    const f = e && e.financeiro;
    if (d.revisao_parcial_encerrada) return ['fim', 'Revisão parcial do piloto encerrada — histórico preservado', 5];
    if (d.execucao.status === "EM_EXECUCAO" || d.estado === "DOCUMENTOS_EM_ANDAMENTO") return ["andamento", "① Documentos analisando o lote", 1];
    if (d.estado === "FINANCEIRO_EM_ANDAMENTO") return ["andamento", "② Financeiro conferindo as movimentações", 2];
    if (d.estado === "BANCOS_EM_ANDAMENTO") return ["andamento", "③ Contabilidade/Bancos preparando as propostas", 3];
    if (f && f.bloqueio_lote && f.bloqueio_lote.length) return ["bloqueio", "Lote bloqueado no ② Financeiro", 2];
    if (String(d.motivos[0] || "").startsWith("FALHA_")) return ["bloqueio", `Falha na etapa ${String(d.motivos[0]).split(":")[0].replace("FALHA_", "")}`, d.motivos[0].includes("BANCOS") ? 3 : 2];
    if (!e || !e.financeiro) return ["bloqueio", "Parado em ① Documentos (problema estrutural)", 1];
    return ["fim", "⑤ Supervisor — aguardando a sua conferência", 5];
  }

  // Situação de TODAS as áreas (não só a fila de decisões): falhas, bloqueios, dependências e pendências por etapa do
  // indicador (1 Documentos · 2 Financeiro/Fiscal/DP · 3 Contabilidade). Etapa com falha/bloqueio/pendência não recebe ✓.
  const PASSO_AREA = { DOCUMENTOS: 1, TRIAGEM: 1, FINANCEIRO: 2, FISCAL: 2, DP: 2, BANCOS: 3, CONTABILIDADE: 3, CONTABILIDADE_FISCAL: 3, CONTABILFISCAL: 3,
                       CONTABILIDADE_DP: 3, CONCILIACAO: 4 };
  const NOME_AREA = { DOCUMENTOS: "Documentos", TRIAGEM: "Triagem de Documentos", FINANCEIRO: "Financeiro", FISCAL: "Fiscal", DP: "DP", BANCOS: "Bancos",
                      CONTABILIDADE: "Contabilidade/Bancos", CONTABILIDADE_FISCAL: "Contabilidade/Fiscal", CONTABILFISCAL: "Contabilidade/Fiscal",
                      CONTABILIDADE_DP: "Contabilidade/DP", CONCILIACAO: "Conciliação" };
  // etapas do plano (nomes do Coordenador) → nome exibido e chave de etapas_de
  const NOME_ETAPA = { FINANCEIRO: "Financeiro", DP: "DP", FISCAL: "Fiscal", BANCOS: "Contabilidade/Bancos", CONTABILIDADE_DP: "Contabilidade/DP",
                       CONTABILIDADE_FISCAL: "Contabilidade/Fiscal", CONCILIACAO: "Conciliação" };
  const NOME_CURTO_ETAPA = { FINANCEIRO: "Financeiro", DP: "DP", FISCAL: "Fiscal", BANCOS: "Bancos", CONTABILIDADE_DP: "Contabilidade/DP",
                             CONTABILIDADE_FISCAL: "Contabilidade/Fiscal", CONCILIACAO: "Conciliação" };
  const TAREFA_ETAPA = { FINANCEIRO: "FINANCEIRO", DP: "DP", FISCAL: "FISCAL", BANCOS: "CONTABILIDADE", CONTABILIDADE_DP: "CONTABILIDADE_DP",
                         CONTABILIDADE_FISCAL: "CONTABILIDADE_FISCAL", CONCILIACAO: "CONCILIACAO" };
  const SITUACAO_ETAPA = { PENDENTE: "aguardando execução", CONCLUIDA: "concluída", FALHOU: "falhou (tentativa preservada)", BLOQUEADA: "bloqueada" };
  const etapaPlano = (d, nome) => (d.plano_etapas || []).find((p) => p.etapa === nome);
  const cont = (r, k) => Number((r || {})[k] ?? (r || {})[k.toUpperCase()] ?? 0);

  // Tudo o que impede dizer "conciliada": falha, ausência de resultado, divergência, pendência, alcance parcial, desatualização.
  function problemasConciliacao(d) {
    const p = etapaPlano(d, "CONCILIACAO");
    const c = d.conciliacao;
    const out = [];
    if (!p && !c) return out;
    if (p && p.situacao === "FALHOU") out.push("Conciliação: falhou — verificações não entregues (tentativa preservada).");
    if (!c || !c.resultado) {
      if (!p || p.situacao !== "FALHOU") out.push("Conciliação: ainda sem resultado.");
      return out;
    }
    const r = c.resultado.resumo || {};
    if (cont(r, "divergente")) out.push(`Conciliação: ${plural(cont(r, "divergente"), "verificação divergente", "verificações divergentes")}.`);
    if (cont(r, "pendente")) out.push(`Conciliação: ${plural(cont(r, "pendente"), "verificação pendente", "verificações pendentes")} (evidência ausente; nada foi presumido).`);
    if ((c.resultado.alcance || {}).parcial) out.push("Conciliação: alcance parcial — há verificações não executadas.");
    if (c.vigente === false) out.push("Conciliação desatualizada — lançamentos alterados depois dela.");
    return out;
  }
  const TIPO_PEND = { EXTRATO_INCOMPLETO: "extrato incompleto", EXTRATO_INCONSISTENTE: "extrato inconsistente", DOCUMENTO_ILEGIVEL: "documento ilegível",
                      DOCUMENTO_INCOMPLETO: "documento incompleto", DADO_AUSENTE: "dado ausente", CONTA_NAO_CADASTRADA: "conta não cadastrada" };

  function situacaoAreas(d, e, fila) {
    const passos = { 1: null, 2: null, 3: null, 4: null };
    const itens = [];
    const marcar = (n, tipo, texto) => {
      if (!n) n = 3;
      if (tipo === "falha" || !passos[n]) passos[n] = tipo;
      if (texto && !itens.includes(texto)) itens.push(texto);
    };
    const et = d.etapas || {};
    const f = e && e.financeiro;
    const b = e && e.bancos;
    if ((et.documentos || {}).status === "FALHOU") marcar(1, "falha", "Documentos: execução com falha.");
    if (f && f.bloqueio_lote && f.bloqueio_lote.length) marcar(2, "falha", "Financeiro: lote bloqueado antes da conferência.");
    [["financeiro", "Financeiro", 2], ["dp", "DP", 2], ["fiscal", "Fiscal", 2], ["bancos", "Bancos", 3], ["contabdp", "Contabilidade/DP", 3],
     ["contabilfiscal", "Contabilidade/Fiscal", 3]].forEach(([k, nome, n]) => {
      if ((et[k] || {}).status === "FALHOU") marcar(n, "falha", `${nome}: falhou — resultado não entregue (tentativa preservada).`);
    });
    // plano de etapas: falha e bloqueio por dependência (mesmo texto da etapa acima: sem repetição)
    (d.plano_etapas || []).forEach((p) => {
      const nome = NOME_CURTO_ETAPA[p.etapa] || p.etapa;
      if (p.situacao === "FALHOU" && p.etapa !== "CONCILIACAO") marcar(PASSO_AREA[p.etapa], "falha", `${nome}: falhou — resultado não entregue (tentativa preservada).`);
      if (p.situacao === "BLOQUEADA") marcar(PASSO_AREA[p.etapa], "falha", `${nome}: bloqueada.`);
      if (p.situacao === "BLOQUEADA_POR_DEPENDENCIA") marcar(PASSO_AREA[p.etapa], "pendencia",
        `${nome}: bloqueada — depende de ${(p.depende || []).map((x) => NOME_CURTO_ETAPA[x] || x).join(", ")}, que não concluiu; nada foi preparado.`);
    });
    if (d.dp && d.dp.resumo && d.dp.resumo.pendencias) marcar(2, "pendencia", `DP: ${plural(d.dp.resumo.pendencias, "pendência", "pendências")}.`);
    if (d.contabdp && d.contabdp.resumo && d.contabdp.resumo.incompletos)
      marcar(3, "pendencia", `Contabilidade/DP: ${plural(d.contabdp.resumo.incompletos, "proposta incompleta", "propostas incompletas")}.`);
    problemasConciliacao(d).forEach((t) => marcar(4, /falhou/.test(t) ? "falha" : "pendencia", t));
    Object.entries(d.falhas_areas || {}).forEach(([area, motivo]) => marcar(PASSO_AREA[area], "falha", `${NOME_AREA[area] || area}: ${motivo}`));
    (d.motivos || []).filter((x) => String(x).startsWith("FALHA_")).forEach((x) => {
      const area = String(x).split(":")[0].replace("FALHA_", "");
      marcar(PASSO_AREA[area], "falha", `${NOME_AREA[area] || area}: ${x}`);
    });
    Object.values(d.tarefas_areas || {}).forEach((t) => {
      const nome = NOME_AREA[t.area] || t.area;
      if (t.estado === "FALHOU" || t.estado === "BLOQUEADO") marcar(PASSO_AREA[t.area], "falha", `${nome}: ${t.estado === "FALHOU" ? "falhou" : "bloqueado"}${t.motivo ? ` — ${t.motivo}` : "."}`);
      if (t.estado === "BLOQUEADO_POR_DEPENDENCIA") marcar(PASSO_AREA[t.area], "pendencia", `${nome}: aguarda ${NOME_AREA[t.dependencia] || t.dependencia || "outra área"}${t.motivo ? ` — ${t.motivo}` : "."}`);
      if (t.estado === "ENTREGUE_COM_PENDENCIAS") marcar(PASSO_AREA[t.area], "pendencia", null);
    });
    if (f && f.pendencias && f.pendencias.length) {
      const tipos = [...new Set(f.pendencias.map((p) => TIPO_PEND[p.tipo] || String(p.tipo).toLowerCase().replace(/_/g, " ")))];
      marcar(2, "pendencia", `Financeiro: ${plural(f.pendencias.length, "pendência", "pendências")} (${tipos.join(", ")}).`);
    }
    if (f) (f.verificacao_extratos || []).filter((v) => v.cobertura_competencia && v.cobertura_competencia !== "COMPLETA").forEach((v) =>
      marcar(2, "pendencia", `Financeiro: extrato da conta ${v.conta} não cobre a competência inteira (limitação da conferência).`));
    if (d.fiscal && d.fiscal.resumo && d.fiscal.resumo.pendencias) marcar(2, "pendencia", `Fiscal: ${plural(d.fiscal.resumo.pendencias, "pendência fiscal", "pendências fiscais")}.`);
    if (b && b.resumo && b.resumo.incompletos) marcar(3, "pendencia", `Bancos: ${plural(b.resumo.incompletos, "lançamento incompleto", "lançamentos incompletos")}.`);
    if (d.contabilfiscal && d.contabilfiscal.resumo && d.contabilfiscal.resumo.incompletos)
      marcar(3, "pendencia", `Contabilidade/Fiscal: ${plural(d.contabilfiscal.resumo.incompletos, "proposta incompleta", "propostas incompletas")}.`);
    if ((fila || []).some((x) => x.area)) marcar(3, "pendencia", `Contabilidade/Bancos: ${plural(fila.filter((x) => x.area).length, "lançamento depende", "lançamentos dependem")} de outra área (Fiscal).`);
    return { passos, itens };
  }

  // Indicador: ① Documentos · ② áreas acionadas · ③ Contabilidade · ④ Conciliação · ⑤ Supervisor. Com plano de etapas, cada passo
  // reflete a situação real das etapas dele; ⑤ só recebe ✓ com o fechamento APROVADO (SIMULAÇÃO); ④ só recebe ✓ conferida no alcance e vigente.
  function stepper(passo, tipo, temFiscal = false, situacao = { passos: {} }, d = {}) {
    const plano = d.plano_etapas || [];
    const acionadas = ["FINANCEIRO", "DP", "FISCAL"].filter((x) => etapaPlano(d, x)).map((x) => NOME_CURTO_ETAPA[x]);
    const nomes = ["① Documentos", plano.length ? `② ${acionadas.join(" · ") || "Áreas"}` : temFiscal ? '② Fiscal / áreas acionadas' : "② Financeiro",
                   "③ Contabilidade", "④ Conciliação", "⑤ Supervisor"];
    const ol = el("ol", "ac-passos");
    const encerrada = d.revisao_parcial_encerrada || d.estado === "CANCELADA";
    const aprovado = d.estado === "FECHAMENTO_APROVADO";
    const grupo = (etapas) => {
      const g = plano.filter((p) => etapas.includes(p.etapa));
      if (!g.length) return "naoexec";
      if (g.some((p) => ["FALHOU", "BLOQUEADA", "BLOQUEADA_POR_DEPENDENCIA"].includes(p.situacao))) return "bloqueado";
      if (g.some((p) => d.estado === `${p.etapa}_EM_ANDAMENTO`)) return "atual";
      if (g.some((p) => p.situacao === "PENDENTE")) return "futuro";
      return "feito";
    };
    nomes.forEach((nome, i) => {
      const n = i + 1;
      let st;
      if (plano.length) {
        const docs = ((d.etapas || {}).documentos || {}).status;
        st = n === 1 ? (docs === "FALHOU" ? "bloqueado" : docs === "EM_ANDAMENTO" ? "atual" : "feito")
          : n === 2 ? grupo(["FINANCEIRO", "DP", "FISCAL"]) : n === 3 ? grupo(["BANCOS", "CONTABILIDADE_DP", "CONTABILIDADE_FISCAL"])
          : n === 4 ? grupo(["CONCILIACAO"]) : d.estado === "AGUARDANDO_SUPERVISOR" || aprovado ? "feito" : "futuro";
      } else {
        const p = passo === 4 ? 5 : passo;   // SOL sem plano: ④ Conciliação não foi executada
        st = n === 4 ? "naoexec" : n < p ? "feito" : n > p ? "futuro" : tipo === "bloqueio" ? "bloqueado" : tipo === "fim" ? "feito" : "atual";
      }
      const sit = situacao.passos[n];
      if (sit === "falha" && !["futuro", "naoexec"].includes(st)) st = "bloqueado";
      else if (sit === "pendencia" && st === "feito") st = "pendente";
      // ⑤ Supervisor: ✓ somente com o fechamento aprovado (SIMULAÇÃO); antes, aguardando a sua conferência; encerrada/cancelada ■
      if (n === 5 && st === "feito" && !aprovado) st = encerrada ? "encerrado" : "atual";
      if (n === 5 && encerrada && st !== "encerrado") st = "encerrado";
      const sufixo = n === 5 && encerrada ? (d.estado === "CANCELADA" ? " (cancelada)" : " (revisão parcial encerrada)")
        : n === 5 && aprovado ? " (aprovado · SIMULAÇÃO)" : n === 5 && st === "atual" && d.estado === "AGUARDANDO_SUPERVISOR" ? " (sua conferência)"
        : n === 4 && st === "naoexec" ? " (não executada nesta SOL)" : n === 4 && st === "feito" ? " (no alcance; SIMULAÇÃO)" : "";
      const li = el("li", `ac-passo ${st}`);
      li.title = `${nome}${sufixo}`;
      li.append(el("span", "ac-passo-ic", { feito: "✓", atual: "●", bloqueado: "✕", futuro: "○", pendente: "!", encerrado: "■", naoexec: "–" }[st]),
        document.createTextNode(" "), el("span", "ac-passo-nome", nome));
      if (sufixo) li.append(el("span", "ac-passo-nota", sufixo));
      ol.append(li);
    });
    return ol;
  }

  // ---------------------------------------------------------------- percurso completo: áreas, propostas, Conciliação e retomada
  const ESCOPO_TXT = { SIMULACAO_CONCILIADA_NO_ALCANCE: "SIMULAÇÃO conciliada no alcance verificado",
                       SIMULACAO_CONCILIACAO_PARCIAL: "SIMULAÇÃO com conciliação parcial (divergências, pendências ou alcance parcial)",
                       PARCIAL_PILOTO_SEM_CONCILIACAO: "entrega parcial do piloto, sem Conciliação" };
  const GRUPOS_CONC = { A: "A · Integridade das entradas (SOL, empresa, competência e versões)", B: "B · Lançamentos propostos (contas, valor, suporte, duplicidade)",
                        C: "C · Bancos e contas a pagar/receber (saldos)", D: "D · Folha, provisões e tributos", E: "E · Confirmações de terceiros" };
  const RESULTADO_ICONE = { CONFERIDO: "✓", DIVERGENTE: "✕", PENDENTE: "!", NAO_APLICAVEL: "–", NAO_DETERMINADO: "?" };
  const EVIDENCIA_TXT = { DOCUMENTO_EXTERNO: "documento externo", CONTROLE_INTERNO: "controle interno", CONSISTENCIA_SISTEMA: "consistência do sistema",
    NENHUMA: "sem fonte" };
  const valorConc = (v) => (v === null || v === undefined || v === "" ? "—" : isNaN(Number(v)) ? String(v) : fmtValor(v));
  let avisoRetomada = { sol: null, texto: "" };

  // Tabela que vira cartões na coluna lateral (rótulo de cada célula em data-rotulo; cabeçalho só para leitores de tela).
  function tabelaCartoes(cabecalho, linhas, atributo) {
    const t = el("table", "op-tabela ac-tabela-cartoes");
    const cab = el("tr", "ac-cab");
    cabecalho.forEach((c) => cab.append(el("th", null, c)));
    t.append(cab);
    linhas.forEach(({ chave, celulas, classe }) => {
      const tr = el("tr", classe || null);
      if (atributo) tr.dataset[atributo] = chave;
      celulas.forEach((c, i) => {
        const td = el("td", i === 0 ? "largo" : null, c);
        td.dataset.rotulo = cabecalho[i];
        tr.append(td);
      });
      t.append(tr);
    });
    return t;
  }

  function situacaoEtapaTxt(d, nome) {
    const p = etapaPlano(d, nome);
    if (!p) return "não acionada nesta SOL";
    if (d.estado === `${nome}_EM_ANDAMENTO`) return "em andamento";
    if (p.situacao === "BLOQUEADA_POR_DEPENDENCIA") return `bloqueada — depende de ${(p.depende || []).map((x) => NOME_CURTO_ETAPA[x] || x).join(", ")}`;
    return `${SITUACAO_ETAPA[p.situacao] || p.situacao}${p.tentativas > 1 ? ` · tentativa nº ${p.tentativas}` : ""}`;
  }

  function motivoFalha(d, nome) {
    const t = (d.tarefas_areas || {})[TAREFA_ETAPA[nome]] || {};
    return (d.falhas_areas || {})[nome] || (d.falhas_areas || {})[TAREFA_ETAPA[nome]] || t.motivo || "";
  }

  function secaoSituacaoAreas(d, e) {
    const f = e && e.financeiro;
    const b = e && e.bancos;
    const props = (r) => (r ? `${plural(r.resumo.propostos, "proposta", "propostas")}, ${plural(r.resumo.incompletos, "incompleta", "incompletas")}` : "");
    const pendOu = (nome, texto) => (etapaPlano(d, nome) && etapaPlano(d, nome).situacao === "FALHOU" ? motivoFalha(d, nome) || "resultado não entregue" : texto || "—");
    const conc = problemasConciliacao(d);
    const linhas = [
      ["FINANCEIRO", "② Financeiro", pendOu("FINANCEIRO", f ? `${plural(f.pendencias.length, "pendência", "pendências")}` : ""), "Agente Financeiro · decisões: Supervisor"],
      ["DP", "② DP", pendOu("DP", d.dp ? plural(d.dp.resumo.pendencias || 0, "pendência", "pendências") : ""), "Agente de DP"],
      ["FISCAL", "② Fiscal", pendOu("FISCAL", d.fiscal ? plural(d.fiscal.resumo.pendencias || 0, "pendência", "pendências") : ""), "Agente Fiscal"],
      ["BANCOS", "③ Contabilidade · Bancos", pendOu("BANCOS", props(b)), "Contabilidade (especialista Bancos)"],
      ["CONTABILIDADE_DP", "③ Contabilidade · DP", pendOu("CONTABILIDADE_DP", props(d.contabdp)), "Contabilidade (Contabilidade/DP, mesa de Bancos)"],
      ["CONTABILIDADE_FISCAL", "③ Contabilidade · Fiscal", pendOu("CONTABILIDADE_FISCAL", props(d.contabilfiscal)), "Contabilidade (Contabilidade/Fiscal, mesa de Bancos)"],
      ["CONCILIACAO", "④ Conciliação", conc.join(" ") || (d.conciliacao && d.conciliacao.resultado ? "nenhuma divergência ou pendência no alcance verificado" : "—"),
       "Agente de Conciliação → Coordenador Geral"]
    ].map(([chave, nome, pend, resp]) => {
      const sit = situacaoEtapaTxt(d, chave);
      const classe = /falhou|bloqueada/.test(sit) ? "ac-linha-falha" : /não acionada/.test(sit) ? "ac-linha-nd" : null;
      return { chave, classe, celulas: [nome, sit, pend, resp] };
    });
    // recolhido no Resumo: o indicador de etapas já mostra a situação; aqui ficam responsável e pendências por área
    const sec = el("details", "ac-det ac-situacao");
    sec.dataset.situacaoAreas = "true";
    sec.append(el("summary", null, "Situação de cada área (responsável e pendências)"),
      tabelaCartoes(["Área", "Situação", "Pendências", "Responsável"], linhas, "areaSituacao"),
      el("p", "op-ajuda", "Responsável = quem executa ou corrige; nenhuma área aprova lançamentos. A decisão é sempre do Supervisor."));
    return sec;
  }

  // ---------------- tabelas de análise (viram cartões quando o painel está estreito; ver .ac-grade no CSS)
  const NOME_AREA_CURTO = { BANCOS: "Bancos", DP: "DP", FISCAL: "Fiscal", CONTABILIDADE: "Contabilidade", FINANCEIRO: "Financeiro", COORDENADOR: "Coordenador",
                            CONCILIACAO: "Conciliação", CONTABILIDADE_DP: "Contabilidade/DP", CONTABILIDADE_FISCAL: "Contabilidade/Fiscal" };
  const fmtComp = (c) => (c && /^\d{4}-\d{2}/.test(c) ? `${c.slice(5, 7)}/${c.slice(0, 4)}` : "—");

  function celula(rotulo, conteudo, classe) {
    const td = el("td", classe || null);
    td.dataset.rotulo = rotulo;
    if (conteudo instanceof Node) td.append(conteudo);
    else td.textContent = conteudo === undefined || conteudo === null ? "—" : String(conteudo);
    return td;
  }

  function conteudoConta(c) {
    if (!c) return el("span", "ac-conta-pend", "a definir");
    const s = el("span", "ac-conta");
    s.append(el("strong", null, String(c.codigo)), el("span", "ac-conta-sep", " · "), el("span", "ac-conta-nome", c.descricao || ""));
    return s;
  }

  function cabecalhoGrade(colunas) {
    const thead = el("thead");
    const tr = el("tr", "ac-cab");
    colunas.forEach((c) => { const th = el("th", null, c); th.scope = "col"; tr.append(th); });
    thead.append(tr);
    return thead;
  }

  function seletorFiltro(rotulo, opcoes, valor, aoMudar) {
    const l = el("label", "ac-filtro");
    const s = el("select");
    opcoes.forEach(([v, t]) => { const o = el("option", null, t); o.value = v; s.append(o); });
    s.value = opcoes.some(([v]) => v === valor) ? valor : "";
    s.addEventListener("change", () => aoMudar(s.value));
    l.append(el("span", null, rotulo), s);
    return { l, s };
  }

  // Todas as propostas contábeis (Bancos, DP, Fiscal) em uma linha por lançamento
  function linhasLancamentos(d, e) {
    const b = e && e.bancos;
    const linhas = [];
    ((b && b.lancamentos) || []).forEach((l) => linhas.push({ area: "BANCOS", data: fmtData(l.data), debito: l.debito, credito: l.credito, valor: l.valor,
      incompleto: l.status !== "PROPOSTO", origem: `${l.historico || ""}${l.origem ? ` · regra ${l.origem}` : " · sem regra aprovada"}` }));
    ((d.contabdp && d.contabdp.lancamentos) || []).forEach((l) => linhas.push({ area: "DP", data: fmtComp(l.competencia || d.competencia),
      debito: l.debito, credito: l.credito, valor: l.valor, incompleto: l.status === "INCOMPLETO",
      origem: `${l.evento || ""} · ${l.documento || ""}${l.arquivo ? ` (${l.arquivo})` : ""}` }));
    ((d.contabilfiscal && d.contabilfiscal.lancamentos) || []).forEach((l) => linhas.push({ area: "FISCAL", data: fmtComp(l.competencia || d.competencia),
      debito: l.debito, credito: l.credito, valor: l.valor, incompleto: l.status === "INCOMPLETO",
      origem: `${l.historico || ""}${l.arquivo ? ` · ${l.arquivo}` : ""}${l.origem_regra ? ` · ${l.origem_regra}` : ""}` }));
    const ordem = ["BANCOS", "DP", "FISCAL"];
    return linhas.sort((x, y) => ordem.indexOf(x.area) - ordem.indexOf(y.area));
  }

  function painelLancamentos(d, e) {
    const b = e && e.bancos;
    const linhas = linhasLancamentos(d, e);
    const sec = el("section", "ac-bloco ac-lancamentos");
    sec.dataset.propostas = "true";
    const areas = ["BANCOS", "DP", "FISCAL"].filter((a) => linhas.some((l) => l.area === a));
    sec.append(el("p", "ac-nota", "Propostas para a sua conferência. Nada foi aprovado, escriturado nem liberado para o Domínio."));
    ["BANCOS", "CONTABILIDADE_DP", "CONTABILIDADE_FISCAL"].filter((x) => (etapaPlano(d, x) || {}).situacao === "FALHOU").forEach((x) =>
      sec.append(el("p", "ac-cadastro", `${NOME_ETAPA[x]}: sem propostas — a etapa falhou${motivoFalha(d, x) ? ` (${motivoFalha(d, x)})` : ""}.`)));
    if (!linhas.length) {
      sec.append(el("p", "nd", "Nenhum lançamento proposto até agora."));
      return sec;
    }
    // totais por origem (todos os status)
    const totais = el("div", "ac-totais");
    areas.forEach((a) => {
      const ls = linhas.filter((l) => l.area === a);
      const inc = ls.filter((l) => l.incompleto).length;
      const soma = ls.reduce((s, l) => s + (Number(l.valor) || 0), 0);
      const t = el("div", "ac-total" + (inc ? " com-pendencia" : ""));
      t.dataset.totalOrigem = a;
      t.append(el("span", "ac-total-nome", NOME_AREA_CURTO[a]), el("strong", "ac-total-valor", fmtValor(soma)),
        el("span", "ac-total-sub", `${plural(ls.length, "lançamento", "lançamentos")}${inc ? ` · ${plural(inc, "incompleto", "incompletos")}` : ""}`));
      totais.append(t);
    });
    sec.append(totais);
    // filtros (o estado do filtro sobrevive à atualização automática da tela)
    const filtro = telaAc.filtroLanc;
    const barra = el("div", "ac-barra");
    const contagem = el("span", "ac-barra-n");
    contagem.setAttribute("aria-live", "polite");
    const linhasTr = [];
    const filtrar = () => {
      let n = 0;
      linhasTr.forEach(({ tr, l }) => {
        const ok = (!filtro.origem || l.area === filtro.origem) && (!filtro.status || (filtro.status === "INCOMPLETO") === l.incompleto);
        tr.hidden = !ok;
        n += ok;
      });
      contagem.textContent = n === linhas.length ? `${plural(n, "lançamento", "lançamentos")}` : `${n} de ${linhas.length} lançamentos`;
      vazio.hidden = n > 0;
    };
    const fo = seletorFiltro("Origem", [["", "Todas"], ...areas.map((a) => [a, NOME_AREA_CURTO[a]])], filtro.origem, (v) => { filtro.origem = v; filtrar(); });
    const fs = seletorFiltro("Status", [["", "Todos"], ["PROPOSTO", "Propostos"], ["INCOMPLETO", "Incompletos"]], filtro.status, (v) => { filtro.status = v; filtrar(); });
    filtro.origem = fo.s.value;
    filtro.status = fs.s.value;
    barra.append(fo.l, fs.l, contagem);
    if (b) {
      const csv = el("button", "ac-botao-sec", `Baixar CSV de Bancos (tentativa nº ${b.n})`);
      csv.type = "button";
      csv.addEventListener("click", async () => {
        const resp = await fetch(`/api/solicitacoes/${d.sol}/financeiro/${b.n}/csv`, { headers: { "X-Prime-Sessao": TOKEN }, cache: "no-store" });
        if (!resp.ok) return;
        const url = URL.createObjectURL(await resp.blob());
        const a = el("a");
        a.href = url;
        a.download = `lancamentos_SIMULACAO_${d.sol}_tentativa${b.n}.csv`;
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
      });
      barra.append(csv);
    }
    sec.append(barra);
    const colunas = ["Origem", "Data / comp.", "Débito", "Crédito", "Valor", "Status", "Origem / regra"];
    const t = el("table", "ac-grade ac-grade-lanc");
    t.append(el("caption", "ac-oculto", "Lançamentos propostos em SIMULAÇÃO"), cabecalhoGrade(colunas));
    const corpo = el("tbody");
    linhas.forEach((l) => {
      const tr = el("tr", l.incompleto ? "ac-linha-falha" : null);
      tr.dataset.areaProposta = l.area;
      const status = el("span", `ac-status ${l.incompleto ? "pend" : "ok"}`, l.incompleto ? "Incompleto" : "Proposto");
      tr.append(celula(colunas[0], el("span", `ac-origem ac-origem-${l.area.toLowerCase()}`, NOME_AREA_CURTO[l.area]), "ac-c-origem"),
        celula(colunas[1], l.data, "ac-c-data"), celula(colunas[2], conteudoConta(l.debito)), celula(colunas[3], conteudoConta(l.credito)),
        celula(colunas[4], l.valor ? fmtValor(l.valor) : "valor pendente", "ac-c-valor"), celula(colunas[5], status), celula(colunas[6], l.origem, "ac-c-regra"));
      corpo.append(tr);
      linhasTr.push({ tr, l });
    });
    t.append(corpo);
    const rolagem = el("div", "ac-rolagem");
    rolagem.append(t);
    const vazio = el("p", "nd", "Nenhum lançamento com este filtro.");
    sec.append(rolagem, vazio);
    filtrar();
    return sec;
  }

  const SEVERIDADE = { DIVERGENTE: 0, PENDENTE: 1, NAO_DETERMINADO: 2, CONFERIDO: 3, NAO_APLICAVEL: 4 };
  const RESULTADO_TXT = { CONFERIDO: "Conferida", DIVERGENTE: "Divergente", PENDENTE: "Pendente", NAO_APLICAVEL: "Não aplicável",
    NAO_DETERMINADO: "Exigência não determinada" };

  function detalheVerificacao(v) {
    const caixa = el("div", "ac-verif-detalhe");
    const fontes = el("ul", "ac-fontes");
    (v.fontes || []).forEach((f) => {
      const li = el("li");
      const chip = el("span", `ac-fonte ${String(f.natureza || "").toLowerCase()}`, EVIDENCIA_TXT[f.categoria] || f.natureza || "?");
      chip.dataset.naturezaFonte = f.natureza || "";
      chip.dataset.categoriaFonte = f.categoria || "";
      li.append(chip, document.createTextNode(` ${f.referencia || ""}${f.tipo ? ` (${f.tipo})` : ""}`));
      fontes.append(li);
    });
    if (!(v.fontes || []).length) fontes.append(el("li", "op-problema", "Sem fonte — evidência ausente (nada foi presumido)."));
    const dl = el("dl", "ac-dl");
    const linha = (k, val) => dl.append(el("dt", null, k), el("dd", null, val));
    dl.append(el("dt", null, "Fontes confrontadas"));
    const dd = el("dd");
    dd.append(fontes);
    dl.append(dd);
    linha("Verificada contra", (v.evidencias || []).length ? v.evidencias.map((x) => EVIDENCIA_TXT[x] || x).join(" + ") : EVIDENCIA_TXT[v.evidencia] || "—");
    linha("Justificativa", v.justificativa || "—");
    linha("Ação", v.acao || "—");
    linha("Área responsável", v.area_responsavel || "—");
    linha("Identificador", v.id);
    caixa.append(dl);
    return caixa;
  }

  function painelConciliacao(d) {
    const p = etapaPlano(d, "CONCILIACAO");
    const c = d.conciliacao;
    const sec = el("section", "ac-bloco ac-conciliacao");
    sec.dataset.conciliacao = "true";
    if (!p && !c) {
      sec.append(el("p", "nd", "A Conciliação não faz parte desta solicitação (sem plano de etapas). Nenhuma verificação foi executada."));
      return sec;
    }
    const historico = () => {
      const h = (c && c.historico) || [];
      const ul = lista(h.slice().reverse().map((x) => `${hora(x.em)} · tentativa nº ${x.tentativa} · ${cont(x.resumo, "conferido")} conferida(s), `
        + `${cont(x.resumo, "divergente")} divergente(s), ${cont(x.resumo, "pendente")} pendente(s) · alcance ${(x.alcance || {}).parcial ? "parcial" : "completo"}`
        + ` · ${x.vigente ? "vigente" : "desatualizada"}`));
      ul.dataset.historicoConciliacao = "true";
      sec.append(detalhes(`Histórico das conciliações (${h.length})`, false, h.length ? ul : el("p", "nd", "Nenhuma execução registrada.")));
    };
    if (!c || !c.resultado) {
      sec.append(el("p", "nd", p && p.situacao === "FALHOU" ? "A Conciliação falhou nesta tentativa: nenhuma verificação foi entregue (tentativa preservada)."
        : d.estado === "CONCILIACAO_EM_ANDAMENTO" ? "Conciliação em andamento." : "Conciliação ainda não executada: roda depois que as áreas e a Contabilidade terminam."));
      historico();
      return sec;
    }
    const r = c.resultado;
    const res = r.resumo || {};
    const al = r.alcance || {};
    const verifs = (r.verificacoes || []).slice().sort((x, y) => String(x.grupo).localeCompare(String(y.grupo))
      || (SEVERIDADE[x.resultado] ?? 9) - (SEVERIDADE[y.resultado] ?? 9));
    // vigência e alcance
    const topo = el("div", "ac-conc-topo");
    const vig = el("span", `ac-selo ${c.vigente === false ? "ac-selo-vermelho" : "ac-selo-verde"}`, c.vigente === false ? "Desatualizada" : "Vigente");
    topo.append(el("p", "ac-conc-resumo", `Tentativa nº ${r.n || "—"} · ${cont(res, "conferido")} conferida(s) · ${cont(res, "divergente")} divergente(s) · `
      + `${cont(res, "pendente")} pendente(s) · ${cont(res, "nao_aplicavel")} não aplicável(is)`
      + (cont(res, "nao_determinado") ? ` · ${cont(res, "nao_determinado")} com exigência não determinada` : "") + ` · total ${cont(res, "total") || verifs.length}`), vig);
    sec.append(topo);
    const pe = res.conferidas_por_evidencia;
    if (pe) sec.append(el("p", "op-ajuda", `Conferidas contra: documento externo ${pe.DOCUMENTO_EXTERNO || 0} · controle interno ${pe.CONTROLE_INTERNO || 0} · `
      + `consistência do sistema ${pe.CONSISTENCIA_SISTEMA || 0}. Concordância interna não é confirmação independente; não há pontuação.`));
    if (c.vigente === false) {
      const aviso = el("div", "ac-alerta");
      aviso.dataset.desatualizada = "true";
      aviso.append(el("p", null, "Conciliação DESATUALIZADA — algo que ela conferiu mudou depois (resultado, documento, cadastro, plano ou regra). "
        + "Ela não vale para a situação atual; o histórico fica preservado."));
      if ((c.motivos || []).length) aviso.append(lista(c.motivos));
      if ((c.rever || []).length) aviso.append(el("p", null, `Rever (aba Decisões → Retomada de etapa): ${c.rever.map((x) => NOME_ETAPA[x] || x).join(", ")}.`));
      sec.append(aviso);
    }
    if ((r.perguntas_supervisor || []).length) {
      const q = el("div", "ac-alerta");
      q.dataset.perguntasSupervisor = "true";
      q.append(el("p", null, "Perguntas ao Supervisor (sem resposta não há fechamento integral):"), lista(r.perguntas_supervisor.map((x) => x.pergunta)));
      sec.append(q);
    }
    const alc = el("div", "ac-alcance" + (al.parcial ? " parcial" : ""));
    alc.append(el("p", "ac-pos-titulo", `Alcance: ${al.parcial ? "PARCIAL" : "completo — todas as verificações previstas foram executadas sobre as entradas recebidas"}`));
    if (al.texto && al.parcial && !(al.nao_executadas || []).length) alc.append(el("p", null, al.texto));
    if ((al.nao_executadas || []).length) alc.append(el("p", null, "Não executado (e por quê):"),
      lista(al.nao_executadas.map((x) => `${x.grupo}${x.item ? ` / ${x.item}` : ""}: ${x.motivo}`)));
    sec.append(alc);
    // resumo por grupo A–E
    const tg = el("table", "ac-grade ac-grade-grupos");
    const colG = ["Grupo", "Conferidas", "Divergentes", "Pendentes", "Não aplicáveis"];
    tg.append(el("caption", "ac-oculto", "Resumo da Conciliação por grupo"), cabecalhoGrade(colG));
    const cg = el("tbody");
    ["A", "B", "C", "D", "E"].forEach((g) => {
      const vs = verifs.filter((v) => v.grupo === g);
      const n = (k) => vs.filter((v) => v.resultado === k).length;
      const tr = el("tr", n("DIVERGENTE") ? "ac-linha-falha" : n("PENDENTE") || n("NAO_DETERMINADO") ? "ac-linha-pend" : null);
      tr.dataset.grupo = g;
      const num = (k, classe) => el("span", n(k) ? classe : "ac-zero", String(n(k)));
      tr.append(celula(colG[0], GRUPOS_CONC[g], "ac-c-grupo"), celula(colG[1], num("CONFERIDO", "ac-num-ok")), celula(colG[2], num("DIVERGENTE", "ac-num-falha")),
        celula(colG[3], num("PENDENTE", "ac-num-pend")), celula(colG[4], num("NAO_APLICAVEL", "ac-num-nd")));
      cg.append(tr);
    });
    tg.append(cg);
    const rg = el("div", "ac-rolagem");
    rg.append(tg);
    sec.append(rg);
    // filtro: padrão = somente divergentes e pendentes
    const abertas = verifs.filter((v) => ["DIVERGENTE", "PENDENTE", "NAO_DETERMINADO"].includes(v.resultado)).length;
    const seg = el("div", "ac-segmento");
    seg.setAttribute("role", "group");
    seg.setAttribute("aria-label", "Filtrar verificações");
    const opcoes = [["abertas", `Divergentes e pendentes (${abertas})`], ["todas", `Todas (${verifs.length})`]];
    const botoes = opcoes.map(([v, t]) => { const b = el("button", null, t); b.type = "button"; b.dataset.filtroConc = v; seg.append(b); return b; });
    sec.append(seg);
    const colunas = ["Grupo", "Verificação", "Conta / item", "Esperado", "Encontrado", "Diferença", "Resultado", "Área"];
    const t = el("table", "ac-grade ac-grade-conc");
    t.append(el("caption", "ac-oculto", "Verificações da Conciliação"), cabecalhoGrade(colunas));
    const corpos = [];
    verifs.forEach((v) => {
      const corpo = el("tbody", `ac-vgrupo res-${String(v.resultado || "").toLowerCase()}`);
      corpo.dataset.verificacao = v.id;
      corpo.dataset.resultado = v.resultado || "";
      const tr = el("tr", "ac-v-linha");
      const det = el("tr", "ac-v-detalhe");
      const tdDet = el("td");
      tdDet.colSpan = colunas.length;
      tdDet.append(detalheVerificacao(v));
      det.append(tdDet);
      const aberto = telaAc.abertas.has(v.id);
      det.hidden = !aberto;
      const exp = el("button", "ac-expandir");
      exp.type = "button";
      exp.setAttribute("aria-expanded", String(aberto));
      exp.append(el("span", "ac-seta", "▸"), el("span", null, v.titulo || v.id));
      exp.addEventListener("click", () => {
        const abrirDet = det.hidden;
        det.hidden = !abrirDet;
        exp.setAttribute("aria-expanded", String(abrirDet));
        if (abrirDet) telaAc.abertas.add(v.id); else telaAc.abertas.delete(v.id);
      });
      const val = v.valores || {};
      const contaItem = [(v.contas || []).join(", "), v.item].filter(Boolean).join(" · ") || "—";
      tr.append(celula(colunas[0], v.grupo, "ac-c-grupo"), celula(colunas[1], exp, "ac-c-verif"), celula(colunas[2], contaItem),
        celula(colunas[3], valorConc(val.esperado), "ac-c-valor"), celula(colunas[4], valorConc(val.encontrado), "ac-c-valor"),
        celula(colunas[5], valorConc(val.diferenca), "ac-c-valor"),
        celula(colunas[6], el("span", `ac-res ${String(v.resultado || "").toLowerCase()}`, `${RESULTADO_ICONE[v.resultado] || ""} ${RESULTADO_TXT[v.resultado] || v.resultado}`)),
        celula(colunas[7], NOME_AREA_CURTO[v.area_responsavel] || v.area_responsavel || "—"));
      corpo.append(tr, det);
      t.append(corpo);
      corpos.push(corpo);
    });
    const rolagem = el("div", "ac-rolagem");
    rolagem.append(t);
    const vazio = el("p", "nd", "");
    const aplicar = () => {
      const filtro = telaAc.filtroConc;
      let n = 0;
      corpos.forEach((x) => { const ok = filtro === "todas" || ["DIVERGENTE", "PENDENTE", "NAO_DETERMINADO"].includes(x.dataset.resultado); x.hidden = !ok; n += ok; });
      botoes.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.filtroConc === filtro)));
      rolagem.hidden = n === 0;
      vazio.hidden = n > 0;
      vazio.textContent = `Nenhuma verificação divergente ou pendente. ${plural(verifs.length, "verificação", "verificações")} no total — escolha “Todas” para conferir.`;
    };
    botoes.forEach((b) => b.addEventListener("click", () => { telaAc.filtroConc = b.dataset.filtroConc; aplicar(); }));
    sec.append(rolagem, vazio);
    aplicar();
    sec.append(el("p", "op-ajuda", "Evidência de cada fonte: documento externo (extrato bancário, confirmação de terceiro); controle interno (demonstrativos, posições, cadastro, plano, regras da empresa — não é confirmação independente); consistência do sistema (resultados de outras etapas). Não aplicável só com justificativa pela natureza do item ou por regra documentada; exigência não determinada = falta definição do Supervisor. Clique na verificação para ver fontes, justificativa e ação."),
      el("p", "op-ajuda", r.aviso || "SIMULAÇÃO: a Conciliação verifica e aponta; não corrige, não aprova, não escritura e não libera."));
    historico();
    return sec;
  }

  // Retomada AUTORIZADA de etapa que falhou (mesmo pacote íntegro): reexecuta a etapa, os dependentes e a Conciliação.
  function secaoRetomada(d) {
    const plano = d.plano_etapas || [];
    const rever = d.conciliacao && d.conciliacao.vigente === false ? (d.conciliacao.rever || []) : [];
    const desatualizadas = plano.filter((p) => p.situacao === "CONCLUIDA" && rever.includes(p.etapa) && (p.etapa !== "CONCILIACAO" || rever.length === 1));
    const falhas = plano.filter((p) => p.situacao === "FALHOU").concat(desatualizadas);
    const bloqueadas = plano.filter((p) => p.situacao === "BLOQUEADA_POR_DEPENDENCIA");
    const anteriores = d.retomadas || [];
    if (!falhas.length && !bloqueadas.length && !anteriores.length) return null;
    const sec = el("section", "ac-secao ac-retomada");
    sec.dataset.retomada = "true";
    sec.append(el("h3", "ac-titulo", "Retomada de etapa"));
    if (avisoRetomada.sol === d.sol && avisoRetomada.texto) sec.append(el("p", "ac-restante ok", avisoRetomada.texto));
    if (falhas.length && !d.retomada_disponivel) {
      sec.append(el("p", "ac-cadastro", "A retomada não está disponível nesta solicitação: ela não tem o pacote de Documentos íntegro (âncora) registrado. "
        + "Para reprocessar, abra uma nova solicitação com os documentos da competência. O histórico desta SOL fica preservado."));
    } else if (falhas.length && d.estado !== "AGUARDANDO_SUPERVISOR") {
      sec.append(el("p", "op-ajuda", "A retomada fica disponível quando a solicitação estiver aguardando a sua conferência (sem processamento em andamento)."));
    } else {
      falhas.forEach((p) => {
        const nome = NOME_ETAPA[p.etapa] || p.etapa;
        const reexec = [p.etapa, ...plano.filter((x) => (x.depende || []).includes(p.etapa)).map((x) => x.etapa)];
        if (p.etapa !== "CONCILIACAO" && plano.some((x) => x.etapa === "CONCILIACAO")) reexec.push("CONCILIACAO");
        const art = el("div", "ac-decisao");
        art.dataset.etapaRetomada = p.etapa;
        const motivo = motivoFalha(d, p.etapa);
        const desat = p.situacao === "CONCLUIDA";
        art.append(el("p", "ac-decisao-cab", desat ? `${nome}: desatualizada — fonte alterada depois da execução (tentativa nº ${p.tentativas || 1}, preservada)`
          : `${nome}: falhou (tentativa nº ${p.tentativas || 1}, preservada)`));
        if (desat) art.append(el("p", "op-problema", `Motivo: ${(d.conciliacao.motivos || []).join(" ")}`));
        else if (motivo) art.append(el("p", "op-problema", `Causa registrada: ${motivo}`));
        art.append(el("p", null, `Será reexecutado: ${reexec.map((x) => NOME_ETAPA[x] || x).join(" → ")}. Resultados válidos das demais áreas e todas as tentativas anteriores ficam preservados; nada é aprovado nem escriturado.`),
          el("p", "op-ajuda", "Corrija antes a causa (por exemplo, a configuração da empresa). A nova tentativa usa o mesmo pacote de documentos já recebido."));
        const just = entradaJustificativa();
        just.placeholder = "Justificativa (obrigatória, 5 a 500 caracteres; fica registrada na SOL)";
        just.setAttribute("aria-label", `Justificativa para retomar ${nome}`);
        const conf = el("label", "op-confirma");
        const chk = el("input");
        chk.type = "checkbox";
        conf.append(chk, el("span", null, `Confirmo a nova tentativa de ${nome} (reexecuta as etapas acima).`));
        const b = el("button", "op-iniciar", `Retomar ${nome}`);
        b.type = "button";
        b.dataset.retomar = p.etapa;
        b.disabled = true;
        const msg = el("p", "op-msg");
        msg.setAttribute("role", "status");
        const validar = () => { b.disabled = just.value.trim().length < 5 || just.value.trim().length > 500 || !chk.checked; };
        just.addEventListener("input", validar);
        chk.addEventListener("change", validar);
        b.addEventListener("click", async () => {
          validar();
          if (b.disabled) return;
          b.disabled = true;
          try {
            const r = await api("POST", `/solicitacoes/${d.sol}/areas/${p.etapa}/retomar`, { justificativa: just.value.trim(), confirmado: true });
            avisoRetomada = { sol: d.sol, texto: r.mensagem || `Nova tentativa de ${nome} iniciada; tentativas anteriores preservadas.` };
            msg.textContent = avisoRetomada.texto;
            setTimeout(() => { if (acompanhando === d.sol) atualizar(); }, 800);
          } catch (erro) {
            msg.textContent = erro.message;
            validar();
          }
        });
        art.append(campoRotulado("Justificativa", just), conf, b, msg);
        sec.append(art);
      });
    }
    bloqueadas.forEach((p) => sec.append(el("p", "op-ajuda", `${NOME_ETAPA[p.etapa]}: bloqueada porque depende de `
      + `${(p.depende || []).map((x) => NOME_ETAPA[x] || x).join(", ")}; é reexecutada junto com a retomada da etapa de que depende.`)));
    if (anteriores.length) sec.append(detalhes(`Retomadas anteriores (${anteriores.length})`, !falhas.length,
      lista(anteriores.slice().reverse().map((x) => `${hora(x.em)} · ${NOME_ETAPA[x.etapa] || x.etapa} · reexecutou: `
        + `${(x.reexecuta || []).map((y) => NOME_ETAPA[y] || y).join(", ") || "—"} · justificativa: ${x.justificativa}`))));
    return sec;
  }

  // Resumo do percurso completo: considera TODAS as áreas e a Conciliação. Nunca diz "sem pendências" havendo divergência,
  // pendência, alcance parcial, falha/bloqueio ou desatualização; tudo conferido = SIMULAÇÃO conciliada no alcance, sem aprovação.
  function resumoPercurso(d, e, situacao, decisoes) {
    const plano = d.plano_etapas || [];
    const f = e && e.financeiro;
    const b = e && e.bancos;
    const partes = [];
    if (f) partes.push(`Financeiro conferiu ${plural(f.resumo.movimentos, "movimento", "movimentos")}`);
    if (d.dp) partes.push(`DP analisou ${plural(d.dp.resumo.documentos || 0, "documento", "documentos")} (${plural(d.dp.resumo.fatos || 0, "fato", "fatos")})`);
    if (d.fiscal) partes.push(`Fiscal analisou ${plural(d.fiscal.resumo.documentos || 0, "documento", "documentos")}`);
    const props = [[b, "Bancos"], [d.contabdp, "DP"], [d.contabilfiscal, "Fiscal"]].filter(([r]) => r)
      .map(([r, nome]) => `${nome}: ${plural(r.resumo.propostos, "proposta", "propostas")} e ${plural(r.resumo.incompletos, "incompleta", "incompletas")}`);
    const falhas = plano.filter((p) => p.situacao === "FALHOU").map((p) => NOME_ETAPA[p.etapa]);
    const bloq = plano.filter((p) => p.situacao === "BLOQUEADA_POR_DEPENDENCIA").map((p) => NOME_ETAPA[p.etapa]);
    const loteBloqueado = f && f.bloqueio_lote && f.bloqueio_lote.length ? f.bloqueio_lote : [];
    const c = d.conciliacao;
    const r = c && c.resultado;
    const div = r ? cont(r.resumo, "divergente") : 0;
    const pen = r ? cont(r.resumo, "pendente") : 0;
    const parcial = !!(r && (r.alcance || {}).parcial);
    const desat = !!(c && c.vigente === false);
    let resultado = (loteBloqueado.length ? `Lote bloqueado: ${loteBloqueado.join(" ")} Nada foi conferido pelo Financeiro. ` : "")
      + (partes.length && !loteBloqueado.length ? `${partes.join("; ")}. ` : "") + (props.length ? `Propostas contábeis: ${props.join("; ")}. ` : "");
    if (falhas.length) resultado += `${falhas.join(", ")}: falhou — resultado não entregue (tentativa preservada). `;
    if (bloq.length) resultado += `${bloq.join(", ")}: bloqueada por dependência. `;
    if (r) resultado += `Conciliação: ${cont(r.resumo, "conferido")} conferida(s), ${div} divergente(s), ${pen} pendente(s), `
      + `${cont(r.resumo, "nao_aplicavel")} não aplicável(is)${parcial ? "; alcance PARCIAL" : ""}. `;
    else if (etapaPlano(d, "CONCILIACAO")) resultado += "Conciliação sem resultado entregue. ";
    if (desat) resultado += "Conciliação desatualizada — lançamentos alterados depois dela. ";
    const problemas = loteBloqueado.length || falhas.length || bloq.length || problemasConciliacao(d).length || situacao.itens.length || decisoes.total
      || d.escopo_resultado !== "SIMULACAO_CONCILIADA_NO_ALCANCE";
    const escopo = desat ? "Conciliação desatualizada (não vale para os lançamentos atuais)" : ESCOPO_TXT[d.escopo_resultado] || d.escopo_resultado || "sem Conciliação";
    resultado += problemas
      ? `Resultado: ${escopo}. Há pendências, divergências ou limitações para a sua análise (listadas abaixo). Nada foi aprovado nem escriturado.`
      : "Nenhuma divergência ou pendência apontada no alcance verificado: SIMULAÇÃO conciliada no alcance da amostra, sem aprovação nem escrituração. A decisão continua sendo sua.";
    const verifs = (r && r.verificacoes) || [];
    const areas = (k) => [...new Set(verifs.filter((v) => v.resultado === k).map((v) => v.area_responsavel).filter(Boolean))].join(", ");
    const acoes = [];
    if (loteBloqueado.length) acoes.push("abrir nova solicitação com a competência e os documentos corretos (esta SOL fica registrada como está)");
    if (falhas.length) acoes.push(d.retomada_disponivel ? `corrigir a causa e usar ${falhas.map((x) => `"Retomar ${x}"`).join(", ")} (seção Retomada de etapa)`
      : "abrir nova solicitação para reprocessar (a retomada não está disponível nesta SOL)");
    if (div) acoes.push(`analisar ${plural(div, "verificação divergente", "verificações divergentes")} da Conciliação com as áreas responsáveis (${areas("DIVERGENTE")})`);
    if (pen) acoes.push(`providenciar a evidência de ${plural(pen, "verificação pendente", "verificações pendentes")} (${areas("PENDENTE")})`);
    if (parcial) acoes.push("considerar o alcance parcial (itens não executados listados na Conciliação)");
    if (desat) acoes.push("não usar a Conciliação desatualizada para os lançamentos alterados (nova Conciliação a cada retomada)");
    acoes.push(...decisoes.partes);
    if (props.length) acoes.push("conferir as propostas contábeis (Bancos, DP e Fiscal) e as verificações da Conciliação");
    const proxima = (acoes.length ? acoes.join("; ").replace(/^./, (x) => x.toUpperCase()) + ". " : "")
      + "Nada é aprovado, escriturado ou liberado sem a sua decisão explícita.";
    return [resultado, proxima, escopo];
  }

  // ---------------------------------------------------------------- acompanhamento em abas (Resumo · Lançamentos · Conciliação · Decisões · Histórico)
  // O estado da tela (aba, filtros, linhas abertas) sobrevive às atualizações automáticas da mesma SOL.
  const ABAS = [["resumo", "Resumo"], ["lancamentos", "Lançamentos"], ["conciliacao", "Conciliação"], ["decisoes", "Decisões"], ["historico", "Histórico"]];
  let telaAc = { sol: null, aba: "resumo", filtroLanc: { origem: "", status: "" }, filtroConc: "abertas", abertas: new Set() };
  let ativarAba = null;
  const dataHora = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");
  const ESTADOS_FECHADOS = ["FECHAMENTO_APROVADO", "ENCERRADA", "CANCELADA"];

  function montarAbas(paineis, contadores) {
    const barra = el("div", "ac-abas");
    barra.setAttribute("role", "tablist");
    barra.setAttribute("aria-label", "Seções do acompanhamento");
    const botoes = {};
    const ativar = (id, focar) => {
      if (!paineis[id]) return;
      telaAc.aba = id;
      Object.entries(botoes).forEach(([k, b]) => {
        const sel = k === id;
        b.setAttribute("aria-selected", String(sel));
        b.tabIndex = sel ? 0 : -1;
        paineis[k].hidden = !sel;
      });
      if (focar) botoes[id].focus();
    };
    ABAS.forEach(([id, nome]) => {
      const b = el("button", "ac-aba");
      b.type = "button";
      b.id = `ac-aba-${id}`;
      b.dataset.aba = id;
      b.setAttribute("role", "tab");
      b.setAttribute("aria-controls", `ac-painel-${id}`);
      b.append(el("span", null, nome));
      const c = contadores[id];
      if (c && c.n) b.append(el("span", `ac-aba-n ${c.tom || ""}`, String(c.n)));
      b.addEventListener("click", () => ativar(id));
      botoes[id] = b;
      barra.append(b);
      paineis[id].id = `ac-painel-${id}`;
      paineis[id].setAttribute("role", "tabpanel");
      paineis[id].setAttribute("aria-labelledby", b.id);
      paineis[id].tabIndex = -1;
    });
    barra.addEventListener("keydown", (ev) => {
      const ids = ABAS.map(([id]) => id);
      const i = ids.indexOf(telaAc.aba);
      const alvo = { ArrowRight: ids[(i + 1) % ids.length], ArrowLeft: ids[(i - 1 + ids.length) % ids.length], Home: ids[0], End: ids[ids.length - 1] }[ev.key];
      if (alvo) { ev.preventDefault(); ativar(alvo, true); }
    });
    return { barra, ativar };
  }

  // Faixa de status: UMA frase, por cor. Verde = pronto para aprovar; âmbar = itens que impedem; azul = em processamento;
  // verde escuro = aprovado (SIMULAÇÃO); cinza = revisão parcial encerrada / cancelada.
  function faixaStatus(d, tipo, textoEtapa, locais, escopo) {
    const imp = Array.isArray(d.aprovacao_impedimentos) ? d.aprovacao_impedimentos : null;
    let tom, icone, titulo, sub = "", itens = [];
    if (d.estado === "FECHAMENTO_APROVADO") {
      tom = "aprovado"; icone = "✓";
      titulo = `Fechamento aprovado em ${dataHora(d.aprovacao && d.aprovacao.em)} (SIMULAÇÃO — ${textoTxtCurto(d)}; nada escriturado)`;
      sub = d.aprovacao && d.aprovacao.justificativa ? `Justificativa: ${d.aprovacao.justificativa}` : "";
    } else if (d.estado === "CANCELADA") {
      tom = "cinza"; icone = "■"; titulo = "Solicitação cancelada — histórico preservado";
      sub = "Nada aprovado, nada escriturado, nada liberado.";
    } else if (d.revisao_parcial_encerrada || d.estado === "ENCERRADA") {
      tom = "cinza"; icone = "■"; titulo = "Revisão parcial encerrada — histórico preservado";
      sub = "Não é fechamento integral; pendências e propostas preservadas; nada aprovado nem escriturado.";
      itens = locais;
    } else if (tipo === "andamento") {
      tom = "azul"; icone = "●"; titulo = `Em processamento — ${textoEtapa.replace(/^[①-⑤]\s*/, "")}`;
      sub = "A tela atualiza sozinha. Nada é escriturado.";
    } else if (imp && !imp.length && !locais.length && d.estado === "AGUARDANDO_SUPERVISOR") {
      tom = "verde"; icone = "✓"; titulo = "Tudo conferido — pronto para a sua aprovação";
      sub = `${escopo || "SIMULAÇÃO conciliada no alcance verificado"} · sem aprovação nem escrituração até a sua decisão.`;
    } else {
      tom = "ambar"; icone = "!";
      itens = imp && imp.length ? imp : locais;
      titulo = imp && imp.length ? `${plural(imp.length, "item impede", "itens impedem")} a aprovação`
        : itens.length ? `${plural(itens.length, "ponto", "pontos")} para conferir antes de aprovar` : "Aguardando a sua conferência";
      sub = `${escopo ? `${escopo} · ` : ""}nada foi aprovado nem escriturado.`;
    }
    const f = el("div", `ac-faixa ac-faixa-${tom}`);
    f.dataset.faixa = tom;
    f.setAttribute("role", "status");
    const corpo = el("div", "ac-faixa-corpo");
    corpo.append(el("p", "ac-faixa-titulo", titulo));
    if (sub) corpo.append(el("p", "ac-faixa-sub", sub));
    if (itens.length) {
      const ul = el("ul", "ac-faixa-lista");
      itens.slice(0, 4).forEach((t) => ul.append(el("li", null, t)));
      if (itens.length > 4) ul.append(el("li", "ac-faixa-mais", `e mais ${itens.length - 4} — ver abaixo`));
      corpo.append(ul);
    }
    f.append(el("span", "ac-faixa-icone", icone), corpo);
    f.firstChild.setAttribute("aria-hidden", "true");
    return f;
  }

  // Situação EFETIVA do TXT (servidor: situacao_txt). Aprovação anterior ao TXT nunca aparece como arquivo entregue.
  function textoTxtCurto(d) {
    const t = d.situacao_txt || {};
    if (t.situacao === "LIBERADO_PARA_IMPORTACAO_MANUAL") return t.download ? "TXT liberado para importação MANUAL no Domínio" : "TXT registrado, download BLOQUEADO";
    return ({ BLOQUEADA_NESTA_VERSAO: "aprovada antes da exportação TXT: nenhum arquivo gerado",
      BLOQUEADA_PRODUCAO: "empresa real: exportação TXT bloqueada nesta versão", FALHOU: "geração do TXT FALHOU, nada liberado",
      PREPARANDO: "geração do TXT não concluída, nada liberado", AGUARDANDO_GERACAO_TXT: "TXT ainda não gerado" })[t.situacao] || "nenhum arquivo TXT entregue";
  }

  function indicadores(d, e) {
    const f = e && e.financeiro;
    const b = e && e.bancos;
    const res = [[b, "Bancos"], [d.contabdp, "DP"], [d.contabilfiscal, "Fiscal"]].filter(([r]) => r && r.resumo);
    const prop = res.reduce((s, [r]) => s + Number(r.resumo.propostos || 0), 0);
    const inc = res.reduce((s, [r]) => s + Number(r.resumo.incompletos || 0), 0);
    const r = d.conciliacao && d.conciliacao.resultado;
    const pendFin = f ? (f.pendencias || []).length : 0;
    const pendDp = d.dp && d.dp.resumo ? Number(d.dp.resumo.pendencias || 0) : 0;
    const pendFis = d.fiscal && d.fiscal.resumo ? Number(d.fiscal.resumo.pendencias || 0) : 0;
    const falhas = (d.plano_etapas || []).filter((p) => ["FALHOU", "BLOQUEADA", "BLOQUEADA_POR_DEPENDENCIA"].includes(p.situacao)).length;
    const pendTotal = pendFin + pendDp + pendFis + falhas;
    const grade = el("div", "ac-indicadores");
    const cartao = (chave, rotulo, valor, sub, tom, legenda) => {
      const c = el("div", `ac-ind ${tom || ""}`);
      c.dataset.indicador = chave;
      c.append(el("span", "ac-ind-rotulo", rotulo));
      const v = el("span", "ac-ind-valor");
      if (valor instanceof Node) v.append(valor); else v.textContent = valor;
      c.append(v);
      if (legenda) c.append(el("span", "ac-ind-legenda", legenda));
      c.append(el("span", "ac-ind-sub", sub));
      grade.append(c);
    };
    cartao("movimentos", "Movimentos conferidos", f ? String(f.resumo.movimentos) : "—",
      f ? `${f.resumo.com_suporte ?? 0} com suporte · ${f.resumo.sem_suporte ?? 0} sem suporte` : "Financeiro não acionado");
    const lanc = el("span");
    lanc.append(el("strong", null, String(prop)), el("span", "ac-ind-sep", " / "), el("strong", inc ? "ac-num-falha" : "ac-zero", String(inc)));
    cartao("lancamentos", "Lançamentos", res.length ? lanc : "—",
      res.length ? res.map(([x, nome]) => `${nome} ${Number(x.resumo.propostos || 0) + Number(x.resumo.incompletos || 0)}`).join(" · ") : "Nenhuma proposta ainda", inc ? "alerta" : "",
      res.length ? "propostos / incompletos" : "");
    if (r) {
      const conc = el("span");
      const div = cont(r.resumo, "divergente");
      const pen = cont(r.resumo, "pendente");
      conc.append(el("strong", null, String(cont(r.resumo, "conferido"))), el("span", "ac-ind-sep", " / "), el("strong", div ? "ac-num-falha" : "ac-zero", String(div)),
        el("span", "ac-ind-sep", " / "), el("strong", pen ? "ac-num-pend" : "ac-zero", String(pen)));
      cartao("conciliacao", "Conciliação", conc,
        `${cont(r.resumo, "nao_aplicavel")} não aplicável(is) · ${d.conciliacao.vigente === false ? "desatualizada" : "vigente"}${(r.alcance || {}).parcial ? " · alcance parcial" : ""}`,
        div || pen || d.conciliacao.vigente === false || (r.alcance || {}).parcial ? "alerta" : "", "conferidas / divergentes / pendentes");
    } else {
      cartao("conciliacao", "Conciliação", "—", etapaPlano(d, "CONCILIACAO") ? ((etapaPlano(d, "CONCILIACAO").situacao === "FALHOU") ? "falhou nesta tentativa" : "ainda sem resultado")
        : "não executada nesta SOL", etapaPlano(d, "CONCILIACAO") && etapaPlano(d, "CONCILIACAO").situacao === "FALHOU" ? "alerta" : "");
    }
    cartao("pendencias", "Pendências abertas", String(pendTotal),
      [f && `Financeiro ${pendFin}`, d.dp && `DP ${pendDp}`, d.fiscal && `Fiscal ${pendFis}`, falhas && `${plural(falhas, "etapa com falha", "etapas com falha")}`].filter(Boolean).join(" · ") || "por área",
      pendTotal ? "alerta" : "");
    return grade;
  }

  // Ação EXPLÍCITA sobre o TXT (gerar de novo após falha corrigida; mover arquivo de aprovação revogada): justificativa obrigatória.
  function acaoTxt(d, acao, rotulo, ajuda, msg) {
    const box = el("div", "ac-confirmacao");
    box.dataset.acaoTxt = acao;
    const just = entradaJustificativa();
    just.placeholder = "Justificativa (5 a 300 caracteres; fica registrada)";
    just.setAttribute("aria-label", `Justificativa: ${rotulo}`);
    const b = el("button", "ac-botao-sec", rotulo);
    b.type = "button";
    b.disabled = true;
    just.addEventListener("input", () => { const n = just.value.trim().length; b.disabled = n < 5 || n > 300; });
    b.addEventListener("click", async () => {
      b.disabled = true;
      msg.textContent = "Enviando…";
      try {
        const r = await api("POST", `/solicitacoes/${d.sol}/txt-dominio/${acao}`, { confirmado: true, justificativa: just.value.trim() });
        msg.textContent = ((r && r.liberacao) || {}).mensagem || "Ação registrada.";
        if (acompanhando === d.sol) atualizar();
      } catch (erro) {
        msg.textContent = erro.message;
        b.disabled = false;
      }
    });
    box.append(el("p", "op-ajuda", ajuda), campoRotulado("Justificativa", just), b);
    return box;
  }

  // Aprovação EXPLÍCITA do fechamento (SIMULAÇÃO): o servidor decide se é possível (aprovacao_impedimentos) e registra.
  function blocoAprovacao(d) {
    const caixa = el("div", "ac-aprovacao");
    caixa.dataset.aprovacao = d.estado === "FECHAMENTO_APROVADO" ? "aprovado" : "pendente";
    const msg = el("p", "op-msg");
    msg.setAttribute("role", "status");
    const enviar = async (corpo, botao) => {
      botao.disabled = true;
      msg.textContent = "Enviando ao Coordenador…";
      try {
        const r = await api("POST", `/solicitacoes/${d.sol}/aprovacao`, corpo);
        const lib = (r && r.liberacao) || {};
        msg.textContent = (corpo.acao === "aprovar" ? "Aprovação registrada. " : "Aprovação revogada. ")
          + (lib.situacao === "LIBERADO_PARA_IMPORTACAO_MANUAL" ? `TXT para o Domínio liberado (${lib.linhas} lançamento(s)).`
            : lib.mensagem || "");
        setTimeout(vigiar, 200);
        if (acompanhando === d.sol) atualizar();
      } catch (erro) {
        msg.textContent = erro.message;
        botao.disabled = false;
      }
    };
    if (d.estado === "FECHAMENTO_APROVADO" && d.aprovacao) {
      const a = d.aprovacao;
      const dl = el("dl", "ac-dl");
      [["Aprovado em", `${dataHora(a.em)} · ${a.por || "Supervisor Contábil"}`], ["Justificativa", a.justificativa || "—"],
       ["Escopo", "SIMULAÇÃO — aprovação da conferência"], ["Escrituração", a.escrituracao === "NAO_REALIZADA" ? "não realizada" : a.escrituracao || "—"],
       ["Domínio", a.liberacao_dominio === "LIBERADO_PARA_IMPORTACAO_MANUAL" && (d.situacao_txt || {}).download
         ? `TXT liberado para importação MANUAL — ${a.txt_linhas} lançamento(s), total R$ ${Number(a.txt_total || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`
         : ((d.situacao_txt || {}).texto || textoTxtCurto(d))],
       ["Importação no Domínio", "não registrada pelo aplicativo (manual, por você)"],
       ["Conciliação aprovada", a.conciliacao_tentativa ? `tentativa nº ${a.conciliacao_tentativa}` : "—"]].forEach(([k, v]) => dl.append(el("dt", null, k), el("dd", null, v)));
      caixa.append(dl);
      const st = d.situacao_txt || {};
      if (st.pode_gerar) caixa.append(acaoTxt(d, "gerar", "Gerar o TXT novamente", "Use depois de corrigir a causa da falha. Nada é repetido automaticamente; arquivos anteriores não são sobrescritos.", msg));
      if (a.liberacao_dominio === "LIBERADO_PARA_IMPORTACAO_MANUAL" && !st.download) {
        caixa.append(el("p", "op-problema", st.texto || "Download bloqueado."));
      }
      if (a.liberacao_dominio === "LIBERADO_PARA_IMPORTACAO_MANUAL" && st.download) {
        const nome = String(a.arquivo_txt || "").split("/").pop();
        const baixar = el("button", "ac-aprovar", "Baixar TXT para o Domínio");
        baixar.type = "button";
        baixar.dataset.acaoAprovacao = "baixar-txt";
        baixar.addEventListener("click", async () => {
          const resp = await fetch(`/api/solicitacoes/${d.sol}/txt-dominio`, { headers: { "X-Prime-Sessao": TOKEN }, cache: "no-store" });
          if (!resp.ok) { msg.textContent = "TXT indisponível (revogado ou alterado). Atualize a tela."; return; }
          const url = URL.createObjectURL(await resp.blob());
          const link = el("a");
          link.href = url;
          link.download = nome || `lanctos_${d.sol}.txt`;
          document.body.append(link);
          link.click();
          link.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        });
        caixa.append(el("p", "ac-aprovacao-nota",
          `Arquivo também gravado em ${String(a.arquivo_txt || "").replace(/^.*?(LIBERADOS\/)/, "$1")}. Partida simples (1 linha por lançamento, ` +
          "IniciaLote 1) — variante AINDA NÃO VALIDADA no Domínio: teste antes numa empresa de teste do Domínio. A importação é MANUAL, feita por você; "
          + "revogar aqui não estorna o que já tiver sido importado."), baixar);
        // Excel dos lançamentos e balancete: MESMA versão aprovada do TXT (sha256 registrados juntos)
        [["excel", "Baixar Excel dos lançamentos"], ["balancete", "Baixar balancete de verificação"]].forEach(([tipo, rotulo]) => {
          const anexo = (a.anexos || {})[tipo];
          if (!anexo) return;
          const b = el("button", "ac-botao-sec", rotulo);
          b.type = "button";
          b.dataset.acaoAprovacao = `baixar-${tipo}`;
          b.addEventListener("click", async () => {
            const resp = await fetch(`/api/solicitacoes/${d.sol}/saidas/${tipo}`, { headers: { "X-Prime-Sessao": TOKEN }, cache: "no-store" });
            if (!resp.ok) { msg.textContent = `${rotulo.replace("Baixar ", "")} indisponível (revogado ou alterado). Atualize a tela.`; return; }
            const url = URL.createObjectURL(await resp.blob());
            const link = el("a");
            link.href = url;
            link.download = String(anexo.arquivo).split("/").pop();
            document.body.append(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          });
          caixa.append(b);
        });
        if (a.anexos) caixa.append(el("p", "ac-aprovacao-nota", "Excel e balancete correspondem exatamente ao TXT aprovado. O balancete é calculado pelo "
          + "aplicativo (abertura documentada + movimento aprovado) em SIMULAÇÃO; não comprova importação nem escrituração no Domínio."));
      }
      const abrir = el("button", "ac-botao-sec", "Revogar aprovação");
      abrir.type = "button";
      abrir.dataset.acaoAprovacao = "abrir-revogar";
      const form = el("div", "ac-confirmacao");
      form.hidden = true;
      const just = entradaJustificativa();
      just.placeholder = "Motivo da revogação (5 a 500 caracteres; fica registrado na SOL)";
      just.setAttribute("aria-label", "Justificativa da revogação");
      const conf = el("label", "op-confirma");
      const chk = el("input");
      chk.type = "checkbox";
      conf.append(chk, el("span", null, "Confirmo a revogação: a solicitação volta a aguardar a sua conferência."));
      const ok = el("button", "ac-botao-perigo", "Confirmar revogação");
      ok.type = "button";
      ok.dataset.acaoAprovacao = "revogar";
      ok.disabled = true;
      const cancelar = el("button", "ac-botao-sec", "Cancelar");
      cancelar.type = "button";
      const validar = () => { const n = just.value.trim().length; ok.disabled = n < 5 || n > 500 || !chk.checked; };
      just.addEventListener("input", validar);
      chk.addEventListener("change", validar);
      abrir.addEventListener("click", () => { form.hidden = false; abrir.hidden = true; just.focus(); });
      cancelar.addEventListener("click", () => { form.hidden = true; abrir.hidden = false; });
      ok.addEventListener("click", () => { validar(); if (!ok.disabled) enviar({ acao: "revogar", justificativa: just.value.trim(), confirmado: true }, ok); });
      const acoes = el("div", "ac-confirmacao-acoes");
      acoes.append(ok, cancelar);
      form.append(campoRotulado("Justificativa", just), conf, acoes);
      caixa.append(abrir, form, msg);
      return caixa;
    }
    const naoAprovado = el("div");
    const ultima = (d.aprovacoes_anteriores || []).slice(-1)[0];
    if ((d.situacao_txt || {}).situacao === "REVOGADO_ARQUIVO_NAO_MOVIDO") {
      naoAprovado.append(el("p", "op-problema", d.situacao_txt.texto),
        acaoTxt(d, "mover-revogado", "Mover arquivo revogado", "Tenta de novo renomear o TXT da aprovação revogada (feche-o no Excel/OneDrive antes).", msg));
    } else if (ultima && ultima.liberacao_dominio === "REVOGADO") {
      naoAprovado.append(el("p", "op-ajuda", "Aprovação anterior revogada: o TXT foi renomeado como REVOGADO (preservado) e não pode mais ser baixado. "
        + "Revogar no aplicativo não estorna importação já feita no Domínio."));
    }
    const rel = d.relacao_outras_sols || [];
    if (rel.length) {
      const q = el("div", "ac-alerta");
      q.dataset.relacaoSols = "true";
      q.append(el("p", null, "Outras solicitações da mesma empresa e competência:"),
        lista(rel.map((x) => `${x.sol === d.sol ? "Esta SOL" : x.sol} (${x.estado}): ${({ REPETICAO_DE_APROVADA: "repetição de fatos aprovados",
          SUBSTITUICAO_DE_APROVADA: "substituição de aprovada", FATOS_JA_EXPORTADOS: "fatos já exportados", REVISAO_DE_PROPOSTA: "revisão de proposta",
          COMPLEMENTO: "complemento", SEM_IDENTIDADES: "sem identidades (anterior)" })[x.classificacao] || x.classificacao} — ${x.texto}`)));
      naoAprovado.append(q);
    }
    if ((d.definicoes_necessarias || []).length) {
      const q = el("div", "ac-alerta");
      q.dataset.definicoesNecessarias = "true";
      const ir = el("button", "ac-botao-sec", "Confirmar em Empresas");
      ir.type = "button";
      ir.dataset.irDefinicoes = d.empresa;
      ir.addEventListener("click", () => window.dispatchEvent(new CustomEvent("prime-empresa", { detail: { id: d.empresa, foco: "regras" } })));
      q.append(el("p", null, "Definições necessárias do Supervisor para esta empresa (regras não aplicadas até a confirmação):"),
        lista(d.definicoes_necessarias.map((x) => `${x.area}${x.chave ? ` / ${x.chave}` : ""} (${x.situacao}): ${x.pergunta}`)), ir);
      naoAprovado.append(q);
    }
    caixa.append(naoAprovado);
    const ciencia = d.aprovacao_exige_ciencia || [];
    const imp = Array.isArray(d.aprovacao_impedimentos) ? d.aprovacao_impedimentos
      : ["O servidor não informou se a aprovação é possível nesta solicitação."];
    const pode = !imp.length && d.estado === "AGUARDANDO_SUPERVISOR";
    const linha = el("div", "ac-aprovacao-linha");
    const botao = el("button", "ac-aprovar", "Aprovar fechamento");
    botao.type = "button";
    botao.dataset.acaoAprovacao = "abrir-aprovar";
    botao.disabled = !pode;
    linha.append(botao, el("span", "ac-aprovacao-nota", pode ? "Registra a sua aprovação do fechamento integral conferido e gera o TXT para você importar MANUALMENTE no Domínio (somente empresa fictícia nesta versão; empresa real: TXT bloqueado). Nada é escriturado."
      : "Indisponível enquanto houver impedimentos."));
    caixa.append(linha);
    if (!pode) {
      botao.setAttribute("aria-describedby", "ac-impedimentos");
      const ul = el("ul", "ac-impedimentos");
      ul.id = "ac-impedimentos";
      (imp.length ? imp : ["A solicitação não está aguardando o Supervisor."]).forEach((t) => ul.append(el("li", null, t)));
      caixa.append(el("p", "ac-pos-titulo", "O que impede a aprovação"), ul);
      return caixa;
    }
    const form = el("div", "ac-confirmacao");
    form.hidden = true;
    form.setAttribute("role", "group");
    form.setAttribute("aria-label", "Confirmar aprovação do fechamento");
    const fraseEsperada = d.frase_aprovacao || `APROVO FECHAMENTO ${d.sol}`;
    const fraseTxt = el("p", "ac-frase-guia");
    fraseTxt.append(document.createTextNode("Digite a frase: "), el("code", "ac-frase", fraseEsperada));
    const frase = el("input");
    frase.type = "text";
    frase.maxLength = 80;
    frase.autocomplete = "off";
    frase.spellcheck = false;
    frase.setAttribute("aria-label", "Frase de aprovação");
    const just = entradaJustificativa();
    just.placeholder = "Justificativa da aprovação (5 a 500 caracteres; fica registrada na SOL)";
    just.setAttribute("aria-label", "Justificativa da aprovação");
    const conf = el("label", "op-confirma");
    const chk = el("input");
    chk.type = "checkbox";
    conf.append(chk, el("span", null, "Entendo que é SIMULAÇÃO: nada é escriturado; o TXT (empresa fictícia) só serve para importação MANUAL no Domínio, ainda não validada"));
    const confCiencia = el("label", "op-confirma");
    const chkCiencia = el("input");
    chkCiencia.type = "checkbox";
    confCiencia.append(chkCiencia, el("span", null, `Estou ciente: ${ciencia.join(" ")}`));
    confCiencia.hidden = !ciencia.length;
    const ok = el("button", "ac-aprovar", "Confirmar aprovação");
    ok.type = "button";
    ok.dataset.acaoAprovacao = "aprovar";
    ok.disabled = true;
    const cancelar = el("button", "ac-botao-sec", "Cancelar");
    cancelar.type = "button";
    const validar = () => {
      const n = just.value.trim().length;
      ok.disabled = frase.value.trim() !== fraseEsperada || n < 5 || n > 500 || !chk.checked || (ciencia.length > 0 && !chkCiencia.checked);
    };
    [frase, just].forEach((x) => x.addEventListener("input", validar));
    [chk, chkCiencia].forEach((x) => x.addEventListener("change", validar));
    botao.addEventListener("click", () => { form.hidden = false; botao.hidden = true; frase.focus(); });
    cancelar.addEventListener("click", () => { form.hidden = true; botao.hidden = false; botao.focus(); });
    ok.addEventListener("click", () => {
      validar();
      if (!ok.disabled) enviar({ acao: "aprovar", frase: frase.value.trim(), justificativa: just.value.trim(), confirmado: true,
        ...(ciencia.length ? { ciente_exportados: true } : {}) }, ok);
    });
    const acoes = el("div", "ac-confirmacao-acoes");
    acoes.append(ok, cancelar);
    form.append(fraseTxt, campoRotulado("Frase de aprovação", frase), campoRotulado("Justificativa", just), conf, confCiencia, acoes);
    caixa.append(form, msg);
    return caixa;
  }

  // Próxima ação em poucas palavras (o texto completo fica em "Resultado por extenso")
  function proximaCurta(d, tipo, ctx) {
    if (d.estado === "FECHAMENTO_APROVADO") return "Nada pendente. Se precisar corrigir algo, revogue a aprovação.";
    if (d.estado === "CANCELADA") return "Somente consulta.";
    if (d.revisao_parcial_encerrada) return "Consultar o histórico ou reabrir a revisão parcial.";
    if (tipo === "andamento") return "Aguardar: a etapa termina sozinha.";
    if (ctx.loteBloqueado) return "Abrir nova solicitação com a competência e os documentos corretos.";
    const p = [];
    const r = d.conciliacao && d.conciliacao.resultado;
    const falhas = (d.plano_etapas || []).filter((x) => x.situacao === "FALHOU").map((x) => NOME_ETAPA[x.etapa] || x.etapa);
    if (falhas.length) p.push(d.retomada_disponivel ? `corrigir a causa e retomar ${falhas.join(", ")} (aba Decisões)` : "abrir nova solicitação para reprocessar");
    if (ctx.agora) p.push(`decidir ${plural(ctx.agora, "caso", "casos")} (aba Decisões)`);
    if (ctx.regras) p.push(`avaliar ${plural(ctx.regras, "regra proposta", "regras propostas")} (aba Decisões)`);
    if (r && cont(r.resumo, "divergente")) p.push(`analisar ${plural(cont(r.resumo, "divergente"), "divergência", "divergências")} (aba Conciliação)`);
    if (r && cont(r.resumo, "pendente")) p.push(`providenciar ${plural(cont(r.resumo, "pendente"), "evidência pendente", "evidências pendentes")} (aba Conciliação)`);
    if (r && cont(r.resumo, "nao_determinado")) p.push(`responder ${plural(cont(r.resumo, "nao_determinado"), "pergunta sobre exigência", "perguntas sobre exigências")} (aba Conciliação)`);
    if (d.conciliacao && d.conciliacao.vigente === false) p.push(`rever as etapas desatualizadas: ${(d.conciliacao.rever || []).map((x) => NOME_ETAPA[x] || x).join(", ")} (aba Decisões)`);
    if (ctx.documento) p.push(`acompanhar ${plural(ctx.documento, "item que depende", "itens que dependem")} de documento ou cadastro`);
    if (!p.length && Array.isArray(d.aprovacao_impedimentos) && !d.aprovacao_impedimentos.length && d.estado === "AGUARDANDO_SUPERVISOR")
      return "Conferir os lançamentos e aprovar o fechamento (botão abaixo).";
    if (!p.length) p.push("conferir os lançamentos e as pendências por área");
    return p.join(" · ").replace(/^./, (x) => x.toUpperCase()) + ".";
  }

  function blocoRevisaoParcial(d) {
    const justificativa = el("textarea");
    justificativa.maxLength = 500;
    justificativa.rows = 2;
    justificativa.setAttribute("aria-label", "Justificativa da revisão parcial");
    const acao = d.revisao_parcial_encerrada ? "reabrir" : "encerrar";
    const botao = el("button", "op-recente", acao === "encerrar" ? "Encerrar revisão parcial do piloto" : "Reabrir revisão parcial");
    botao.dataset.revisaoPiloto = acao;
    botao.type = "button";
    botao.disabled = true;
    justificativa.addEventListener("input", () => { botao.disabled = justificativa.value.trim().length < 5; });
    const msg = el("p", "op-ajuda");
    botao.addEventListener("click", async () => {
      botao.disabled = true;
      try {
        await api("POST", `/solicitacoes/${d.sol}/revisao-piloto`, { acao, justificativa: justificativa.value.trim(), confirmado: true });
        atualizar();
      } catch (erro) { msg.textContent = erro.message; botao.disabled = false; }
    });
    return detalhes("Revisão parcial do piloto", false,
      el("p", "op-ajuda", "Encerrar esta revisão não aprova lançamentos, não elimina pendências e não conclui o fechamento integral. É possível reabrir."),
      justificativa, botao, msg);
  }

  async function renderizarFluxoFinanceiro(d) {
    const versao = (renderizarFluxoFinanceiro.versao = (renderizarFluxoFinanceiro.versao || 0) + 1);
    let e = null;
    try {
      e = await api("GET", `/solicitacoes/${d.sol}/financeiro`);
    } catch (err) { /* sem resultado financeiro ainda */ }
    if (versao !== renderizarFluxoFinanceiro.versao) return;
    if (e && !e.disponivel) e = null;
    if (telaAc.sol !== d.sol) telaAc = { sol: d.sol, aba: "resumo", filtroLanc: { origem: "", status: "" }, filtroConc: "abertas", abertas: new Set() };
    visao.textContent = "";
    const voltar = el("button", "op-recente ac-voltar", "← Solicitações");
    voltar.type = "button";
    voltar.addEventListener("click", () => { acompanhando = null; clearTimeout(temporizador); painel.hidden = true; window.dispatchEvent(new CustomEvent('prime-consulta')); });
    visao.append(voltar);

    const [tipo, textoEtapa, passo] = etapaAtual(d, e);
    const f = e && e.financeiro;
    const b = e && e.bancos;
    const fila = e ? montarFila(e) : [];
    const agora = fila.filter((x) => x.agora);
    const documento = fila.filter((x) => !x.agora);
    const regrasPropostas = e ? e.regras.filter((r) => r.situacao === "PROPOSTA") : [];
    const situacao = situacaoAreas(d, e, fila);
    const bancosFalhou = ((d.etapas || {}).bancos || {}).status === "FALHOU";
    const comPlano = (d.plano_etapas || []).length > 0;
    const encerrada = !!d.revisao_parcial_encerrada;
    const loteBloqueado = !!(f && f.bloqueio_lote && f.bloqueio_lote.length);

    // ---------------- cabeçalho compacto: SOL · empresa · competência · selo
    const cab = el("header", "ac-cab");
    const tomSelo = d.estado === "FECHAMENTO_APROVADO" ? "aprovado" : ["CANCELADA", "ENCERRADA"].includes(d.estado) || encerrada ? "cinza"
      : /_EM_ANDAMENTO$/.test(d.estado || "") || tipo === "andamento" ? "azul" : "ambar";
    const linhaCab = el("div", "ac-cab-linha");
    linhaCab.append(el("h3", "ac-sol", d.sol), el("span", `ac-selo ac-selo-${tomSelo}`, ROTULOS[d.estado] || d.estado));
    cab.append(linhaCab, el("p", "ac-cab-meta", `${d.empresa} · competência ${fmtComp(d.competencia)} · ${comPlano ? "percurso completo" : d.fiscal || d.estado === "FISCAL_EM_ANDAMENTO" ? "Fiscal / áreas acionadas" : "Financeiro → Contabilidade/Bancos"} · SIMULAÇÃO`));
    visao.append(cab);

    // ---------------- textos completos (mesma lógica de antes; ficam em "Resultado por extenso")
    let resultado;
    let proxima;
    if (tipo === "andamento") {
      resultado = "Em processamento. A tela atualiza sozinha.";
      proxima = "Aguarde: a etapa termina sozinha. Nada é escriturado.";
    } else if (tipo === "bloqueio" && loteBloqueado) {
      resultado = `Lote bloqueado: ${f.bloqueio_lote.join(" ")} Nada foi conferido nem escriturado.`;
      proxima = "Abrir nova solicitação com a competência e os documentos corretos. Esta SOL fica registrada como está.";
    } else if (tipo === "bloqueio") {
      resultado = `A solicitação parou: ${d.motivos.filter((m) => !m.startsWith("Relatório: pendência")).slice(0, 2).join(" ")} Nada foi escriturado.`;
      proxima = "Revisar os motivos (aba Histórico) e abrir nova solicitação se necessário.";
    } else {
      const haPendencias = agora.length || documento.length || regrasPropostas.length || situacao.itens.length
        || Object.values(situacao.passos).some(Boolean);
      resultado = f ? `Financeiro conferiu ${plural(f.resumo.movimentos, "movimento", "movimentos")}. `
        + (b ? `Bancos preparou ${plural(b.resumo.propostos, "proposta", "propostas")} e deixou ${plural(b.resumo.incompletos, "incompleta", "incompletas")}. `
          : bancosFalhou ? "Bancos falhou: as propostas não foram entregues (tentativa preservada). " : "Bancos ainda não entregou propostas. ")
        + (haPendencias ? "Há pendências para sua análise. " : "Nenhuma pendência apontada no alcance desta conferência. ")
        + "Nada foi escriturado." : 'Análise fiscal disponível para conferência. Nada foi escriturado.';
      const partes = [];
      if (agora.length) partes.push(`decidir ${plural(agora.length, "caso", "casos")} na aba Decisões`);
      if (regrasPropostas.length) partes.push(`avaliar ${plural(regrasPropostas.length, "regra proposta", "regras propostas")}`);
      if (b && b.resumo.propostos) partes.push(`conferir ${plural(b.resumo.propostos, "proposta pronta", "propostas prontas")}`);
      if (situacao.itens.length) partes.push("conferir as pendências e falhas por área");
      proxima = (partes.length ? partes.join(", ").replace(/^./, (c) => c.toUpperCase()) + "." : "Nenhuma ação pendente.")
        + (documento.length ? ` ${plural(documento.length, "item depende", "itens dependem")} de documento adicional, de definição no cadastro ou de outra área (sem decisão possível agora).` : "");
    }
    if (encerrada) {
      resultado = 'Revisão parcial encerrada pelo Supervisor. Pendências e propostas preservadas; nenhum lançamento foi aprovado ou escriturado.';
      proxima = 'Consulte o histórico ou reabra a revisão para registrar novos ajustes.';
    }
    if (d.fiscal && tipo !== 'andamento' && !encerrada) {
      const cf = d.contabilfiscal;
      if (!f) resultado = `Fiscal analisou ${d.fiscal.resumo.documentos} documento(s), com ${d.fiscal.resumo.pendencias} pendência(s). ${cf ? `Contabilidade preparou ${cf.resumo.propostos} proposta(s) e deixou ${cf.resumo.incompletos} incompleta(s).` : 'Propostas fiscais ainda não concluídas.'} Nada foi escriturado.`;
      else resultado += ` Fiscal: ${d.fiscal.resumo.documentos} documento(s), ${d.fiscal.resumo.pendencias} pendência(s). ${cf ? `Propostas fiscais: ${cf.resumo.propostos}; incompletas: ${cf.resumo.incompletos}.` : ''}`;
      proxima = f ? 'Confira também os documentos e as propostas do Fiscal. ' + proxima
        : cf && !cf.resumo.incompletos && !d.fiscal.resumo.pendencias ? 'Confira a proposta fiscal e os documentos. Encerrar a revisão não aprova nem escritura o lançamento.'
        : 'Confira as pendências fiscais. Campos ausentes, divergentes ou layouts não reconhecidos precisam de documentos legíveis e esclarecimento; não foram estimados.';
    }
    let escopoPercurso = null;
    if (comPlano && tipo !== "andamento" && !encerrada) {
      const partesDec = [];
      if (agora.length) partesDec.push(`decidir ${plural(agora.length, "caso", "casos")} na fila de decisões`);
      if (regrasPropostas.length) partesDec.push(`avaliar ${plural(regrasPropostas.length, "regra proposta", "regras propostas")}`);
      if (documento.length) partesDec.push(`acompanhar ${plural(documento.length, "item que depende", "itens que dependem")} de documento, cadastro ou outra área`);
      [resultado, proxima, escopoPercurso] = resumoPercurso(d, e, situacao, { partes: partesDec, total: agora.length + documento.length + regrasPropostas.length });
    }
    if (d.estado === "FECHAMENTO_APROVADO") {
      resultado = `Fechamento aprovado pelo Supervisor em ${dataHora(d.aprovacao && d.aprovacao.em)} (SIMULAÇÃO). ${resultado} `
        + `A aprovação não escritura nada. Domínio: ${textoTxtCurto(d)}. Exportado não significa importado: a importação é sempre manual, por você.`;
    }

    // ---------------- painéis das abas (ordem no DOM: Resumo, Decisões, Lançamentos, Conciliação, Histórico)
    const paineis = {
      resumo: el("section", "ac-resumo ac-painel"),
      decisoes: el("section", "ac-painel ac-painel-decisoes"),
      lancamentos: el("section", "ac-painel"),
      conciliacao: el("section", "ac-painel"),
      historico: el("section", "ac-painel ac-painel-historico")
    };

    // Resumo: status, indicadores, etapas, próxima ação, aprovação
    const R = paineis.resumo;
    const locais = [...new Set([...situacao.itens, ...(loteBloqueado ? [`Lote bloqueado: ${f.bloqueio_lote.join(" ")}`] : [])])];
    R.append(faixaStatus(d, tipo, textoEtapa, locais, escopoPercurso), indicadores(d, e));
    const etapas = el("div", "ac-etapas");
    etapas.append(stepper(passo, tipo, !!d.fiscal || d.estado === 'FISCAL_EM_ANDAMENTO', situacao, d), el("p", "ac-etapa ac-" + tipo, `Etapa atual: ${textoEtapa}`));
    R.append(etapas);
    R.append(el("p", "ac-proxima", `Próxima ação: ${proximaCurta(d, tipo, { agora: agora.length, regras: regrasPropostas.length, documento: documento.length, loteBloqueado })}`));
    const cfin = f && f.conciliacao_financeira;
    if (cfin && cfin.situacao === "EXECUTADA" && window.EV.central) {
      // Central de Revisão: os números e as decisões vêm do servidor; aqui só o acesso
      const bc = cfin.resumo && cfin.resumo.bancarios ? cfin.resumo.bancarios : {};
      const bloco = el("div", "ac-bloco ac-conc-fin");
      bloco.dataset.centralRevisao = "true";
      bloco.append(el("h3", "ac-titulo-bloco", "Conciliação financeira banco × relatório"),
        el("p", null, `Sistema: ${bc.conciliado || 0} conciliada(s), ${bc.provavel || 0} provável(is), ${bc.ambiguo || 0} ambígua(s), ${bc.nao_conciliado || 0} não conciliada(s). Abra a revisão para confirmar ou rejeitar as sugestões.`));
      const abrirC = el("button", "botao-sec", "Abrir revisão da conciliação financeira");
      abrirC.type = "button";
      abrirC.addEventListener("click", () => window.EV.central.abrirSolicitacao(d.sol));
      bloco.append(abrirC);
      R.append(bloco);
    }
    if (["AGUARDANDO_SUPERVISOR", "FECHAMENTO_APROVADO"].includes(d.estado) && tipo !== "andamento" && !encerrada) R.append(blocoAprovacao(d));
    if (situacao.itens.length) {
      const caixa = el("div", "ac-pend-areas");
      caixa.append(el("p", "ac-pos-titulo", `Pendências e falhas por área (${situacao.itens.length})${encerrada ? " — histórico preservado" : ""}`),
        lista(situacao.itens));
      R.append(caixa);
    }
    if (comPlano) R.append(secaoSituacaoAreas(d, e));
    const extenso = detalhes("Resultado por extenso", false, el("p", "ac-resultado", resultado), el("p", null, `Próxima ação (completa): ${proxima}`));
    extenso.classList.add("ac-det");
    R.append(extenso);
    if ((b || d.contabilfiscal) && ['AGUARDANDO_SUPERVISOR', 'ENCERRADA'].includes(d.estado)) R.append(blocoRevisaoParcial(d));
    R.append(detalhes("O que significam Proposto, Incompleto, Aguardando Supervisor e Concluído", false, lista(GLOSSARIO.map(([k, v]) => `${k}: ${v}`))));
    R.append(el('p', 'ac-nota', escopoPercurso ? `Escopo: ${escopoPercurso}. SIMULAÇÃO: análises, propostas e verificações para a sua conferência; não é escrituração efetiva.`
      : 'SIMULAÇÃO · entrega parcial do piloto: análises e propostas para conferência. Não representa fechamento integral, escrituração efetiva ou Conciliação independente concluída.'));

    // Decisões: retomada de etapa, fila de decisões, regras propostas, itens que dependem de documento
    const D = paineis.decisoes;
    const retomada = comPlano ? secaoRetomada(d) : null;
    if (retomada) D.append(retomada);
    if (e && e.em_execucao) setTimeout(() => { if (acompanhando === d.sol) atualizar(); }, 2500);
    if (f && !encerrada && !loteBloqueado) {
      const sAgora = el("section", "ac-secao");
      sAgora.append(el("h3", "ac-titulo", `Decisões que exigem a sua ação (${agora.length})`));
      if (agora.length) agora.forEach((x, i) => sAgora.append(cartaoDecisao(d.sol, x, i + 1, e)));
      else sAgora.append(el("p", "nd", "Nenhuma decisão pendente."));
      D.append(sAgora);
      if (regrasPropostas.length) {
        const sR = el("section", "ac-secao");
        sR.append(el("h3", "ac-titulo", `Regras propostas aguardando aprovação (${regrasPropostas.length}) — uso futuro, não este caso`));
        regrasPropostas.forEach((r) => sR.append(cartaoRegra(d.sol, r, e)));
        D.append(sR);
      }
      const sDoc = el("section", "ac-secao");
      sDoc.append(el("h3", "ac-titulo", `Dependem de documento adicional, de definição no cadastro ou de outra área (${documento.length})`));
      if (documento.length) documento.forEach((x, i) => sDoc.append(cartaoDecisao(d.sol, x, agora.length + i + 1, e)));
      else sDoc.append(el("p", "nd", "Nenhum."));
      D.append(sDoc);
    } else if (!retomada) {
      D.append(el("p", "nd", encerrada ? "Revisão parcial encerrada: nenhuma decisão em aberto nesta tela (histórico preservado)."
        : loteBloqueado ? "Lote bloqueado: nenhuma decisão é possível nesta solicitação." : "Nenhuma decisão em aberto nesta solicitação."));
    }
    if (f) {
      const grupos = {};
      const add = (chave, texto, origem) => {
        grupos[chave] = grupos[chave] || { textos: [], origens: new Set() };
        if (!grupos[chave].textos.includes(texto)) grupos[chave].textos.push(texto);
        grupos[chave].origens.add(origem);
      };
      const ressalvasF = f.ressalvas_documentos || [];
      f.pendencias.filter((p) => PENDENCIAS_INFORMATIVAS.has(p.tipo)).forEach((p) => add(p.referencia || p.tipo, p.descricao, "Financeiro"));
      f.relacionados_sem_movimento.filter((x) => !x.descricao.startsWith("documento identifica")).forEach((x) =>
        add(x.origem || x.arquivo, `${x.favorecido || x.tipo} · ${fmtValor(x.valor)} · ${fmtData(x.data)}: ${x.descricao}`, "Financeiro"));
      const sobre = f.duplicidades.filter((x) => x.tipo === "SOBREPOSICAO_DE_EXTRATOS");
      if (sobre.length) add("Extratos sobrepostos", `${plural(sobre.length, "movimento repetido", "movimentos repetidos")} entre extratos da mesma conta, contados uma vez.`, "Financeiro");
      ressalvasF.forEach((r) => Object.keys(grupos).forEach((k) => { if (r.includes(k)) grupos[k].origens.add("Agente de Documentos"); }));
      const sInfo = el("section", "ac-secao");
      const itens = Object.entries(grupos).map(([k, g]) => `${k}: ${g.textos.join(" ")} (origem: ${[...g.origens].join(" e ")})`);
      sInfo.append(detalhes(`Para conhecimento — sem ação sua (${itens.length})`, false, lista(itens)));
      D.append(sInfo);
    }

    // Lançamentos e Conciliação (tabelas)
    paineis.lancamentos.append(painelLancamentos(d, e));
    paineis.conciliacao.append(painelConciliacao(d));

    // Histórico: aprovações, eventos, retomadas, conciliações, tentativas, trabalho por área e auditoria
    paineis.historico.append(...painelHistorico(d, e, f, b));

    // ---------------- abas
    const r = d.conciliacao && d.conciliacao.resultado;
    const nConcAbertas = r ? cont(r.resumo, "divergente") + cont(r.resumo, "pendente") : 0;
    const nLanc = linhasLancamentos(d, e).length;
    const nLancInc = linhasLancamentos(d, e).filter((l) => l.incompleto).length;
    const nDec = agora.length + regrasPropostas.length + (d.plano_etapas || []).filter((p) => p.situacao === "FALHOU").length;
    const { barra, ativar } = montarAbas(paineis, {
      lancamentos: { n: nLanc, tom: nLancInc ? "alerta" : "" },
      conciliacao: nConcAbertas ? { n: nConcAbertas, tom: "alerta" } : r ? { n: cont(r.resumo, "conferido"), tom: "ok" } : null,
      decisoes: nDec ? { n: nDec, tom: "alerta" } : documento.length ? { n: documento.length, tom: "" } : null
    });
    ativarAba = ativar;
    visao.append(barra, paineis.resumo, paineis.decisoes, paineis.lancamentos, paineis.conciliacao, paineis.historico);
    ativar(telaAc.aba);
  }

  function painelHistorico(d, e, f, b) {
    const out = [];
    const ap = el("section", "ac-bloco ac-hist-aprovacoes");
    ap.dataset.historicoAprovacoes = "true";
    ap.append(el("h3", "ac-titulo-bloco", "Aprovações do fechamento"));
    const linhasAp = [];
    if (d.aprovacao) linhasAp.push(`${dataHora(d.aprovacao.em)} · APROVADO (SIMULAÇÃO) por ${d.aprovacao.por || "Supervisor Contábil"} · ${d.aprovacao.justificativa || ""} · vigente`);
    (d.aprovacoes_anteriores || []).slice().reverse().forEach((x) => linhasAp.push(`${dataHora(x.em)} · aprovado (SIMULAÇÃO) · ${x.justificativa || ""} · `
      + `REVOGADO em ${dataHora(x.revogada_em)}: ${x.motivo_revogacao || "—"}`));
    ap.append(linhasAp.length ? lista(linhasAp) : el("p", "nd", "Nenhuma aprovação registrada."));
    out.push(ap);
    const ev = el("section", "ac-bloco");
    ev.append(el("h3", "ac-titulo-bloco", `Eventos da solicitação (${(d.eventos || []).length})`));
    const ol = el("ol", "ac-linha-tempo");
    (d.eventos || []).slice().reverse().forEach((x) => { const li = el("li"); li.append(el("time", null, hora(x.em)), el("span", null, x.evento)); ol.append(li); });
    ev.append((d.eventos || []).length ? ol : el("p", "nd", "Nenhum evento registrado."));
    out.push(ev);
    const outros = el("section", "ac-bloco");
    outros.append(el("h3", "ac-titulo-bloco", "Retomadas, conciliações e tentativas"));
    const ret = d.retomadas || [];
    outros.append(detalhes(`Retomadas de etapa (${ret.length})`, false, ret.length ? lista(ret.slice().reverse().map((x) => `${hora(x.em)} · ${NOME_ETAPA[x.etapa] || x.etapa} · reexecutou: `
      + `${(x.reexecuta || []).map((y) => NOME_ETAPA[y] || y).join(", ") || "—"} · justificativa: ${x.justificativa}`)) : el("p", "nd", "Nenhuma.")));
    const hc = (d.conciliacao && d.conciliacao.historico) || [];
    outros.append(detalhes(`Conciliações executadas (${hc.length})`, false, hc.length ? lista(hc.slice().reverse().map((x) => `${hora(x.em)} · tentativa nº ${x.tentativa} · `
      + `${cont(x.resumo, "conferido")} conferida(s), ${cont(x.resumo, "divergente")} divergente(s), ${cont(x.resumo, "pendente")} pendente(s) · ${x.vigente ? "vigente" : "desatualizada"}`))
      : el("p", "nd", "Nenhuma.")));
    if (e) {
      outros.append(detalhes("Tentativas do Financeiro e de Bancos (preservadas)", false, lista([
        `Financeiro: ${e.tentativas.financeiro.map((x) => `nº ${x.n}${x.concluida ? "" : " (falhou)"}`).join(", ") || "—"}`,
        `Bancos: ${e.tentativas.bancos.map((x) => `nº ${x.n}${x.concluida ? "" : " (falhou)"}`).join(", ") || "—"}`])));
      const dec = Object.entries(e.decisoes || {}).flatMap(([mov, l]) => l.map((x) => `${hora(x.em)} · ${mov} · ${x.tipo} (${x.escopo}) · ${x.justificativa}`));
      outros.append(detalhes(`Decisões registradas (${dec.length})`, false, dec.length ? lista(dec) : el("p", "nd", "Nenhuma.")));
    }
    out.push(outros);
    out.push(secaoTrabalhoPorArea(d, f, b));
    const aud = el("section", "ac-secao");
    aud.append(el("h3", "ac-titulo", "Evidências e auditoria"));
    aud.append(detalhes(`Motivos técnicos do Coordenador (${d.motivos.length})`, false, lista(d.motivos)));
    if (e) {
      aud.append(detalhes(`Regras de lançamentos bancários da empresa (${e.regras.length})`, false, lista(e.regras.map((r) =>
        `${r.regra} v${r.versao} · ${r.situacao} · quando ${r.condicoes} → ${r.tipo} contrapartida ${r.contrapartida} · origem: ${r.origem} · aprovação: ${r.aprovacao}`))));
      if (f) {
        aud.append(detalhes(`Pendências completas do Financeiro (${f.pendencias.length})`, false, lista(f.pendencias.map((x) => `${x.id} · ${x.tipo}: ${x.descricao}`))));
        aud.append(detalhes("Limitações da conferência", false, lista(f.limitacoes || [])));
      }
      if (b) aud.append(detalhes(`Pendências completas de Contabilidade/Bancos (${b.pendencias.length})`, false, lista(b.pendencias.map((x) => `${x.id} · ${x.movimento}: ${x.descricao}`))));
    }
    const a = d.execucao.auditoria || {};
    aud.append(detalhes("Auditoria da execução do Agente de Documentos", false, lista([
      `Ferramentas: ${Object.entries(a.ferramentas || {}).map(([k, v]) => `${k} ${v}`).join(", ") || "—"}`,
      `Chamadas bloqueadas pelo guarda: ${a.bloqueios ?? "—"}`, `Duração: ${a.duracao_s ?? "—"} s`, ...(a.problemas || [])])));
    out.push(aud);
    return out;
  }

  // Trabalho por área (Documentos, Financeiro, DP, Fiscal, Contabilidade/Bancos): evidências de cada área
  function secaoTrabalhoPorArea(d, f, b) {
    const areas = el("section", "ac-secao");
    areas.append(el("h3", "ac-titulo", "Trabalho por área"));
    if (d.tarefas_areas && Object.keys(d.tarefas_areas).length) {
      const nomes = {FINANCEIRO:'Financeiro',FISCAL:'Fiscal',DP:'DP',TRIAGEM:'Triagem de Documentos',CONTABILIDADE:'Contabilidade/Bancos',CONTABILIDADE_FISCAL:'Contabilidade/Fiscal',CONTABILIDADE_DP:'Contabilidade/DP',CONCILIACAO:'Conciliação'};
      const estados = {PRONTO_PARA_ENCAMINHAMENTO:'pacote separado',EM_ANDAMENTO:'em andamento',ENTREGUE:'entregue',
        ENTREGUE_COM_PENDENCIAS:'entregue com pendências',AGUARDANDO_IMPLEMENTACAO:'área ainda não implementada',
        AGUARDANDO_IDENTIFICACAO:'aguardando identificação',BLOQUEADO:'bloqueado',
        PROPOSTAS_PARCIAIS_AGUARDANDO_SUPERVISOR:'propostas parciais aguardando sua conferência',FALHOU:'falhou (tentativa preservada)',
        BLOQUEADO_POR_DEPENDENCIA:'bloqueado por dependência'};
      areas.append(detalhes('Distribuição e situação das áreas', false, lista(Object.values(d.tarefas_areas).map(t =>
        `${nomes[t.area] || t.area}: ${estados[t.estado] || t.estado} · ${(t.documentos || []).length} documento(s)`))));
    }
    const grade = el("div", "ac-areas");
    if(d.fiscal){
      const fis=el('article','ac-area');fis.dataset.areaFiscal='true';
      fis.append(el('h4',null,'Fiscal → Contabilidade'),el('p',null,`${d.fiscal.resumo.documentos} documento(s) · ${d.fiscal.resumo.pendencias} pendência(s). Conferência documental local; sem consulta externa ou apuração tributária completa.`));
      for(const x of d.fiscal.documentos){
        const nomeTipo={NFSE:'NFS-e',NFE:'NF-e',GUIA:'Guia',APURACAO_TRIBUTO:'Demonstrativo de apuração',EVENTO_CANCELAMENTO:'Cancelamento'}[x.tipo]||'Documento a conferir';
        const papel={PRESTADOR_EMITENTE:'empresa emitente/prestadora',TOMADOR_DESTINATARIO:'empresa destinatária/tomadora',CONTRIBUINTE:'empresa contribuinte'}[x.papel_empresa]||'titularidade a conferir';
        const v=el('div','ac-prop');v.append(el('p','ac-prop-cab',`${nomeTipo} · ${x.numero||'número não identificado'} · ${x.valor?fmtValor(x.valor):'valor a conferir'}`),
          el('p',null,`Competência: ${x.competencia ? x.competencia.slice(5)+'/'+x.competencia.slice(0,4) : 'não identificada'} · ${papel}`),
          detalhes('Documento, retenções e pendências',false,lista([x.arquivo,...Object.entries(x.retencoes||{}).map(([k,v])=>`${k} retido: ${fmtValor(v)}`),...x.pendencias])));
        fis.append(v);
      }
      fis.append(detalhes('Limites da análise fiscal',false,lista(d.fiscal.limitacoes || [])));
      if(d.contabilfiscal) for(const l of d.contabilfiscal.lancamentos){
        const c=el('div','ac-prop');c.append(el('p','ac-prop-cab',`${l.status==='INCOMPLETO'?'Incompleto':'Proposto para conferência'} · ${l.valor?fmtValor(l.valor):'valor pendente'}`),
          el('p',null,`Débito: ${fmtConta(l.debito)} · Crédito: ${fmtConta(l.credito)}`),el('p',null,l.historico),
          detalhes('Origem e pontos para conferir',l.status==='INCOMPLETO',lista([l.arquivo,l.origem_regra||'Referência contábil ausente',...l.pendencias])));fis.append(c);
      }
      grade.append(fis);
    }
    // DP: documentos de pessoal, fatos para a Contabilidade/DP e pendências (sem cálculo de folha ou encargo presumido)
    if (d.dp || etapaPlano(d, "DP")) {
      const dpa = el("article", "ac-area");
      dpa.dataset.areaDp = "true";
      dpa.append(el("h4", null, "② DP → Contabilidade/DP"));
      if (d.dp) {
        const rd = d.dp.resumo || {};
        dpa.append(el("p", null, `${plural(rd.documentos || 0, "documento", "documentos")} · ${plural(rd.fatos || 0, "fato", "fatos")} para a Contabilidade · `
          + `${plural(rd.pendencias || 0, "pendência", "pendências")}. Conferência dos totais da folha, encargos e provisões; sem cálculo de alíquota ou encargo presumido.`));
        dpa.append(detalhes("Documentos do DP", false, lista((d.dp.documentos || []).map((x) => `${x.arquivo} · ${x.tipo || "tipo a conferir"} · `
          + `${x.numero || "número não identificado"} · ${x.elegivel_contabilidade ? "apto para a Contabilidade" : "não aproveitado"}`
          + `${(x.pendencias || []).length ? ` · ${x.pendencias.join(" ")}` : ""}`))));
        if ((d.dp.pendencias || []).length) dpa.append(detalhes(`Pendências do DP (${d.dp.pendencias.length})`, true,
          lista(d.dp.pendencias.map((x) => (x && x.descricao) || String(x)))));
        if ((d.dp.limites || []).length) dpa.append(detalhes("Limites da análise do DP", false, lista(d.dp.limites)));
      } else dpa.append(el("p", "nd", (etapaPlano(d, "DP") || {}).situacao === "FALHOU" ? "Falhou — análise não entregue (tentativa preservada)." : "Ainda sem resultado."));
      grade.append(dpa);
    }
    // Documentos
    const docs = el("article", "ac-area");
    if (d.documentos_local) docs.append(el('p', 'op-ajuda', 'Execução local, sem modelos externos. Extração de texto não comprova veracidade nem correção contábil.'),
      detalhes('Distribuição dos documentos por área', true,
        lista(d.documentos_local.itens.map(i => {
          const enc = i.encaminhamento;
          return enc ? `${i.arquivo} → ${enc.area || 'Área a identificar'} · ${enc.observacao}`
            : `${i.arquivo}: distribuição por área não registrada nesta execução anterior.`;
        }))),
      detalhes('Evidências locais (incluindo OCR quando aproveitado)', false,
        lista(d.documentos_local.itens.map(i => `${i.arquivo}: ${i.leitura} · ${i.conteudo_utilizavel ? 'conteúdo disponível para conferência' : 'conteúdo não utilizável'}`)),
        lista(d.documentos_local.limitacoes)));
    if (d.documentos_local) for (const i of d.documentos_local.itens) {
      if (i.texto_para_conferencia) docs.append(detalhes(`Texto para conferir — ${i.arquivo}`, false,
        el('p', 'op-ajuda', 'Texto parcial ou OCR com confiança insuficiente. Não utilizado como suporte confirmado.'),
        el('pre', 'op-texto-extraido', i.texto_para_conferencia)));
    }
    const naoLidos = d.inventario.filter((i) => !String(i.leitura || "").startsWith("EXTRAIDO_"));
    const ressalvas = (f && f.ressalvas_documentos) || [];
    docs.append(el("h4", null, "① Documentos"), el("p", null, `Recebeu ${plural(d.arquivos.length, "documento", "documentos")}; `
      + `${d.inventario.length - naoLidos.length} lidos pelo extrator, ${naoLidos.length} não lidos. `
      + `${plural(ressalvas.length, "ressalva encaminhada", "ressalvas encaminhadas")} ao Financeiro (sem bloquear o lote; documentos citados não são tratados como validados).`));
    docs.append(detalhes("Documentos recebidos", false, lista(d.arquivos.map((a) => {
      const inv = d.inventario.find((i) => i.nome === a.nome_interno) || {};
      return `${a.nome_original} → ${a.nome_interno} · ${inv.leitura || "—"}${a.duplicado_de ? ` · idêntico a arquivo da ${a.duplicado_de.sol}` : ""}`;
    }))));
    if (ressalvas.length) docs.append(detalhes("Ressalvas do Agente de Documentos", false, lista(ressalvas)));
    if (d.relatorio) docs.append(detalhes("Relatório completo do Agente de Documentos", false, el("pre", null, d.relatorio)));
    grade.append(docs);
    // Financeiro
    const fin = el("article", "ac-area");
    fin.append(el("h4", null, "② Financeiro"));
    if (f) {
      const r = f.resumo;
      fin.append(el("p", null, f.bloqueio_lote && f.bloqueio_lote.length ? "Lote bloqueado antes da conferência (ver Resumo)."
        : `Conferiu ${plural(r.movimentos, "movimento", "movimentos")}: ${r.com_suporte} com suporte, ${r.sem_suporte} sem suporte, `
          + `${r.comprovante_sem_natureza} com comprovante sem natureza, ${r.ambiguos} ambíguos, ${r.transferencias_proprias} em transferências próprias.`));
      fin.append(lista(f.verificacao_extratos.map((v) => `Conta ${v.conta}: ${v.cobertura_competencia === "COMPLETA" ? "mês completo" : "mês incompleto"} · `
        + ({ CONCLUIDA: "saldos conferidos", SEM_VERIFICACAO_ARITMETICA: "sem saldo inicial para conferir a aritmética", INCOMPLETA: "verificação não concluída" }[v.situacao] || v.situacao))));
      fin.append(el("p", "op-ajuda", "Conferência financeira; não é conciliação contábil completa."));
      fin.append(el('p', 'op-ajuda', `${f.documentos.length} documentos de suporte examinados; `
        + `${f.sugestoes.filter(s => s.documento).length} vínculos documentais sugeridos para conferência. Leitura não significa vínculo confirmado.`));
      fin.append(detalhes('Leitura dos documentos para confronto', false, lista(f.documentos.map(x =>
        `${x.arquivo} · ${x.tipo} · valor: ${x.valor ? fmtValor(x.valor) : 'não identificado'} · `
        + `data do documento: ${x.data ? fmtData(x.data) : 'não identificada'}${x.papel_data ? ' (' + x.papel_data + ')' : ''}`
        + `${x.bloqueado ? ' · não utilizado: ' + x.bloqueado : ''}`))));
      fin.append(detalhes("Movimentos conferidos", false, lista(f.movimentos.map((m) => `${fmtData(m.data)} · ${m.direcao === "DEBITO" ? "saída" : "entrada"} `
        + `${fmtValor(m.valor)} · ${m.descricao} · ${SITUACAO_TXT[m.situacao] || m.situacao}`))));
    } else fin.append(el("p", "nd", "Ainda não acionado."));
    grade.append(fin);
    // Contabilidade/Bancos
    const ban = el("article", "ac-area");
    ban.append(el("h4", null, "③ Contabilidade/Bancos"));
    if (b) {
      ban.append(el("p", null, `Preparou ${plural(b.resumo.propostos, "proposta", "propostas")} (${fmtValor(b.resumo.valor_propostos)}) e deixou `
        + `${plural(b.resumo.incompletos, "incompleta", "incompletas")} (${fmtValor(b.resumo.valor_incompletos)}). Todas são PROPOSTAS em SIMULAÇÃO; nada foi escriturado. `
        + "A tabela completa está na aba Lançamentos."));
      const props = el("div", "ac-props");
      b.lancamentos.filter((l) => l.status === "PROPOSTO").forEach((l) => {
        const c = el("div", "ac-prop");
        c.append(el("p", "ac-prop-cab", `${fmtData(l.data)} · ${fmtValor(l.valor)} · Proposto`), el("p", null, `Débito: ${fmtConta(l.debito)}`),
          el("p", null, `Crédito: ${fmtConta(l.credito)}`), el("p", "op-ajuda", `${l.historico} · ${l.fato}`),
          detalhes("Documentos e origem", false, lista([...l.documentos.map((x) => `${x.arquivo} (${x.papel})`), `Origem: ${l.origem}`,
            `Movimentos: ${l.movimentos.join(" + ")}`])));
        if(l.acompanhamentos?.length)c.append(el('strong',null,'Documento pendente · classificação em adiantamento'),lista(l.acompanhamentos));
        props.append(c);
      });
      ban.append(detalhes(`Propostas prontas para conferência (${b.resumo.propostos}) — documentos e origem`, false, props));
    } else ban.append(el("p", "nd", f && f.bloqueio_lote && f.bloqueio_lote.length ? "Não acionado (lote bloqueado)." : "Ainda não acionado."));
    grade.append(ban);
    areas.append(grade);
    return areas;
  }

  // ---------------------------------------------------------------- escritório reflete o estado real
  // Todas as SOLs recentes entram no cálculo (disponibilidade considera todas as tarefas ativas); a SOL acompanhada
  // define o histórico exibido. O mapeamento é puro (js/mapa.js) e as animações só acompanham estes dados.
  let recentesApi = [];
  let foco = null;
  let ultimoAplicado = "";
  let vigia = null;

  function refletir() {
    const f = foco && { sol: foco.sol, empresa: foco.empresa, competencia: foco.competencia, estado: foco.estado, etapas: foco.etapas,
                        pendencias: foco.pendencias.map((p) => `${p[0]} · ${p[2] || ""} · ${p[4] || ""}`),
                        tarefas_areas: foco.tarefas_areas, falhas_areas: foco.falhas_areas,
                        // vigência e alcance da Conciliação só existem no detalhe: o escritório nunca mostra ✓ para conciliação desatualizada/parcial
                        conciliacao_vigente: foco.conciliacao ? foco.conciliacao.vigente : undefined,
                        conciliacao_parcial: !!(foco.conciliacao && foco.conciliacao.resultado && (foco.conciliacao.resultado.alcance || {}).parcial) };
    const estados = EV.mapa.operacao({ recentes: recentesApi, foco: f });
    Object.values(estados).forEach((e) => {
      e.atualizacao = hora(e.fim || e.inicio);
      e.inicio = hora(e.inicio);
      e.fim = hora(e.fim);
    });
    const chave = JSON.stringify(estados);
    if (chave === ultimoAplicado) return;
    ultimoAplicado = chave;
    app.aplicarOperacao(estados, foco ? `Operação local · ${foco.sol}` : "Operação local");
  }

  const algoAtivo = () => recentesApi.some((r) => Object.values(r.etapas || {}).some((e) => e && e.status === "EM_ANDAMENTO"));

  // Leitura periódica do estado (somente GET): mais frequente enquanto alguma etapa estiver em andamento.
  async function vigiar() {
    clearTimeout(vigia);
    try {
      const e = await api("GET", "/estado");
      recentesApi = e.recentes;
      refletir();
    } catch (err) { /* a próxima leitura tenta de novo */ }
    vigia = setTimeout(vigiar, algoAtivo() ? 2000 : 8000);
  }

  app.aplicarOperacao({ coordenador: { status: "LIVRE", tarefa: "Aguardando solicitação do Supervisor", local: "mesa" },
                        documentos: { status: "LIVRE", tarefa: "Aguardando ordem de serviço", local: "copa" },
                        importacao: { status: "LIVRE", tarefa: "Sem SOL encaminhada (somente VGROW)", local: "copa" },
                        financeiro: { status: "LIVRE", tarefa: "Aguardando solicitação Financeiro → Contabilidade/Bancos", local: "copa" },
                        bancos: { status: "LIVRE", tarefa: "Sem conferência financeira encaminhada", local: "copa" },
                        fiscal: { status: "LIVRE", tarefa: "Aguardando notas e guias de Documentos", local: "copa" },
                        dp: { status: "LIVRE", tarefa: "Aguardando documentos de pessoal de Documentos", local: "copa" },
                        conciliacao: { status: "LIVRE", tarefa: "Aguardando as propostas da Contabilidade", local: "copa" } },
  "Operação local: aguardando solicitação.");
  EV.operacao = { acompanhar, nova: () => { carregarEstado(); abrir('form'); }, fechar: () => { painel.hidden = true; },
                  aba: (id) => { if (ativarAba) ativarAba(id); }, ampliar: (sim) => { ampliado = !!sim; sincronizarLargura(); },
                  atualizar: () => { foco=null;acompanhando=null;clearTimeout(temporizador);vigiar();carregarEstado(); } };
  carregarEstado();
  vigiar();
})();
