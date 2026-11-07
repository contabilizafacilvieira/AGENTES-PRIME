/*
 * Controlador do Escritório Virtual.
 * Mantém o estado simulado em memória e avisa a cena e o painel quando ele muda.
 * Não chama agentes, não grava arquivos e não faz requisições de rede.
 *
 * Parâmetros opcionais na URL (úteis para demonstração e testes):
 *   ?cenario=<id ou número>   ex.: ?cenario=trabalhando  ou  ?cenario=2
 *   &agente=<id>              ex.: &agente=documentos
 */
(function () {
  "use strict";
  const EV = window.EV;
  const dados = window.ESCRITORIO_DADOS;

  const CAMPOS = ["status", "empresa", "competencia", "solicitacao", "tarefa", "inicio", "fim", "atualizacao", "pendencias", "mensagem",
    "local", "disponibilidade", "eventos", "pasta", "pasta_bloqueada", "pasta_motivo"];

  function validar(d) {
    const problemas = [];
    if (!d || !Array.isArray(d.agentes) || !Array.isArray(d.cenarios) || !d.cenarios.length) {
      return ["dados/estado-simulado.js ausente ou sem agentes/cenários."];
    }
    const ids = new Set();
    d.agentes.forEach((a) => {
      if (!a.id || ids.has(a.id)) problemas.push(`Agente com id inválido ou repetido: ${a.id}`);
      ids.add(a.id);
      if (!EV.cena._interno.POSTOS[a.id]) problemas.push(`Agente sem posto no escritório: ${a.id}`);
    });
    (d.areas || []).forEach((ar) => {
      if (!EV.cena._interno.AREAS[ar.id]) problemas.push(`Área sem lugar no escritório: ${ar.id}`);
      (ar.especialistas || []).forEach((e) => {
        if (e.agente && !ids.has(e.agente)) problemas.push(`Área "${ar.id}" cita agente inexistente: ${e.agente}`);
      });
    });
    d.cenarios.forEach((c) => {
      Object.entries(c.estados || {}).forEach(([id, e]) => {
        if (!ids.has(id)) problemas.push(`Cenário "${c.id}" cita agente inexistente: ${id}`);
        if (!EV.ESTADOS[e.status]) problemas.push(`Cenário "${c.id}", agente ${id}: status desconhecido "${e.status}"`);
      });
    });
    return problemas;
  }

  function copiar(estados) {
    const r = {};
    Object.entries(estados || {}).forEach(([id, e]) => {
      r[id] = {};
      CAMPOS.forEach((k) => {
        if (e[k] !== undefined) r[id][k] = Array.isArray(e[k]) ? e[k].map((x) => (x && typeof x === "object" ? Object.assign({}, x) : x)) : e[k];
      });
    });
    return r;
  }

  const problemas = validar(dados);
  if (problemas.length) {
    const aviso = document.getElementById("aviso-dados");
    aviso.hidden = false;
    aviso.textContent = "Problemas nos dados simulados: " + problemas.join(" | ");
  }

  const agentes = (dados.agentes || []).filter((a) => EV.cena._interno.POSTOS[a.id]);
  const ouvintes = [];

  const areas = (dados.areas || []).filter((a) => EV.cena._interno.AREAS[a.id]);

  const app = {
    agentes,
    areas,
    cenarios: dados.cenarios,
    cenario: dados.cenarios[0],
    estados: {},
    alterado: false,
    selecionado: null,
    painelAberto: false,

    estadoDe(id) {
      const ag = agentes.find((a) => a.id === id);
      if (!ag || !ag.implementado) {
        return { status: "NAO_IMPLEMENTADO", pendencias: [] };
      }
      const e = this.estados[id] || {};
      const status = EV.ESTADOS[e.status] && e.status !== "NAO_IMPLEMENTADO" ? e.status : "OFFLINE";
      return Object.assign({ pendencias: [] }, e, { status });
    },

    // Selecionar um agente (ou uma área, como a Contabilidade) abre o painel com os detalhes.
    selecionar(id) {
      this.selecionado = id;
      this.painelAberto = true;
      this.notificar();
    },

    // Fechar o painel mantém a seleção visível no escritório.
    fecharPainel() {
      if (!this.painelAberto) return;
      this.painelAberto = false;
      this.notificar();
      if (this.cena && this.selecionado) this.cena.focar(this.selecionado);
    },

    aplicarCenario(id) {
      const cen = this.cenarios.find((c) => c.id === id) || this.cenarios[0];
      this.cenario = cen;
      this.estados = copiar(cen.estados);
      this.alterado = false;
      this.notificar();
    },

    // Modo operação local (página servida pela API): estado vindo do processamento real, só para exibição.
    aplicarOperacao(estados, descricao) {
      this.cenario = { id: "operacao", titulo: "Operação local", descricao: descricao || "", estados: {} };
      this.estados = copiar(estados);
      this.alterado = false;
      this.notificar();
    },

    definirStatus(id, status) {
      const ag = agentes.find((a) => a.id === id);
      if (!ag || !ag.implementado || !EV.ESTADOS[status] || status === "NAO_IMPLEMENTADO") return;
      this.estados[id] = Object.assign({}, this.estados[id], { status });
      this.alterado = true;
      this.notificar();
    },

    aoMudar(fn) {
      ouvintes.push(fn);
    },

    notificar() {
      ouvintes.forEach((fn) => fn());
    }
  };

  // estado inicial (permite abrir direto em um cenário/agente pela URL)
  const params = new URLSearchParams(window.location.search);
  const pedido = params.get("cenario");
  const porNumero = pedido && /^\d+$/.test(pedido) ? dados.cenarios[Number(pedido) - 1] : null;
  const inicial = porNumero || dados.cenarios.find((c) => c.id === pedido) || dados.cenarios[0];
  app.cenario = inicial;
  app.estados = copiar(inicial.estados);
  const agentePedido = params.get("agente");
  if (agentes.some((a) => a.id === agentePedido) || areas.some((a) => a.id === agentePedido)) {
    app.selecionado = agentePedido;
    app.painelAberto = true;
  }

  EV.app = app;
  EV.painel.criar(app);
  app.cena = EV.cena.criar(document.getElementById("tela"), document.getElementById("camada"), app);
})();
