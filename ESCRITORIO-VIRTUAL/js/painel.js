/*
 * Interface ao redor do escritório: menus do topo (Simulação e Legenda), resumo, relógio
 * e o painel recolhível do Supervisor. Usa somente textContent (sem HTML vindo dos dados).
 */
(function () {
  "use strict";
  const EV = (window.EV = window.EV || {});

  const $ = (id) => document.getElementById(id);

  function el(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  function chipEstado(status, texto) {
    const info = EV.ESTADOS[status];
    const chip = el("span", "chip est-" + status, texto || `${info.simbolo} ${info.rotulo}`);
    chip.style.setProperty("--cor-estado", info.cor);
    return chip;
  }

  // ---------------------------------------------------------------- menus suspensos do topo
  function criarMenus() {
    const menus = Array.from(document.querySelectorAll("[data-menu]")).map((botao) => ({
      botao,
      pop: $(botao.getAttribute("aria-controls"))
    }));

    function fechar(exceto) {
      menus.forEach((m) => {
        if (m === exceto) return;
        m.pop.hidden = true;
        m.botao.setAttribute("aria-expanded", "false");
      });
    }

    menus.forEach((m) => {
      m.botao.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const abrir = m.pop.hidden;
        fechar();
        m.pop.hidden = !abrir;
        m.botao.setAttribute("aria-expanded", abrir ? "true" : "false");
      });
      m.pop.addEventListener("click", (ev) => ev.stopPropagation());
    });
    document.addEventListener("click", () => fechar());

    return {
      algumAberto: () => menus.some((m) => !m.pop.hidden),
      fecharTodos: () => {
        const aberto = menus.find((m) => !m.pop.hidden);
        fechar();
        if (aberto) aberto.botao.focus();
      }
    };
  }

  function criar(app) {
    const menus = criarMenus();
    const area = $("area");
    const gaveta = $("gaveta");

    // ---------------------------------------------------------------- cenários (menu Simulação)
    const caixaCenarios = $("cenarios");
    app.cenarios.forEach((cen, i) => {
      const b = el("button", "cenario");
      b.type = "button";
      b.setAttribute("role", "radio");
      b.dataset.id = cen.id;
      b.append(el("span", "cenario-num", String(i + 1)), el("span", null, cen.titulo));
      b.addEventListener("click", () => app.aplicarCenario(cen.id));
      caixaCenarios.appendChild(b);
    });

    // ---------------------------------------------------------------- legenda (menu Legenda)
    const legenda = $("legenda");
    EV.ORDEM_ESTADOS.forEach((st) => {
      const li = el("li");
      li.append(chipEstado(st), el("span", "legenda-desc", EV.ESTADOS[st].descricao));
      legenda.appendChild(li);
    });

    // ---------------------------------------------------------------- controles de desenvolvimento
    const seletor = $("dev-status");
    EV.ORDEM_ESTADOS.filter((s) => s !== "NAO_IMPLEMENTADO").forEach((st) => {
      const o = el("option", null, `${EV.ESTADOS[st].simbolo} ${EV.ESTADOS[st].rotulo}`);
      o.value = st;
      seletor.appendChild(o);
    });
    seletor.addEventListener("change", () => app.definirStatus(app.selecionado, seletor.value));
    $("dev-restaurar").addEventListener("click", () => app.aplicarCenario(app.cenario.id));

    // ---------------------------------------------------------------- painel
    $("fechar-gaveta").addEventListener("click", () => app.fecharPainel());
    document.addEventListener("keydown", (ev) => {
      if (ev.key !== "Escape") return;
      if (menus.algumAberto()) menus.fecharTodos();
      else app.fecharPainel();
    });

    // ---------------------------------------------------------------- relógio
    const relogio = $("relogio");
    const tic = () => {
      relogio.textContent = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    };
    tic();
    setInterval(tic, 15000);

    // Área representada (Contabilidade): função e especialistas internos (funcionais, executados em outra mesa ou "em breve").
    function renderizarArea(area) {
      const ficha = $("ficha");
      const topo = el("div", "ficha-topo");
      topo.append(el("h2", null, area.nome), el("span", "chip", "Área"));
      ficha.append(topo, el("p", "ficha-funcao", area.funcao));
      const lista = el("div", "pendencias");
      lista.appendChild(el("h3", null, `Especialistas internos (${(area.especialistas || []).length})`));
      const ul = el("ul", "especialistas");
      (area.especialistas || []).forEach((e) => {
        const ag = e.agente && app.agentes.find((a) => a.id === e.agente);
        const li = el("li");
        if (ag) {
          const b = el("button", "especialista", ag.nome);
          b.type = "button";
          b.addEventListener("click", () => app.selecionar(ag.id));
          li.append(b, chipEstado(app.estadoDe(ag.id).status));
        } else if (e.via && app.agentes.find((a) => a.id === e.via)) {
          // parte executada por outro especialista (ex.: Contabilidade/DP na mesa de Bancos): mostra o estado dele
          const b = el("button", "especialista", e.nome);
          b.type = "button";
          b.addEventListener("click", () => app.selecionar(e.via));
          li.append(b, chipEstado(app.estadoDe(e.via).status));
        } else {
          li.append(el("span", null, e.nome), chipEstado("NAO_IMPLEMENTADO"));
        }
        ul.appendChild(li);
      });
      lista.appendChild(ul);
      ficha.appendChild(lista);
      ficha.appendChild(el("p", "ficha-aviso", "Fluxo do fechamento: Coordenador → Documentos → Financeiro/DP/Fiscal → Contabilidade → Conciliação → Coordenador e Supervisor. Documentos distribui; as áreas analisam; Contabilidade prepara a escrituração; Conciliação confere. Financeiro, DP, Fiscal, Contabilidade (Bancos, DP e Fiscal) e Conciliação funcionam em SIMULAÇÃO: geram análises, propostas e verificações para a sua conferência; nada é aprovado nem escriturado."));
    }

    function renderizarFicha(ag) {
      const ficha = $("ficha");
      ficha.textContent = "";
      const area = !ag && app.areas.find((a) => a.id === app.selecionado);
      if (area) {
        renderizarArea(area);
        return;
      }
      if (!ag) {
        ficha.appendChild(el("p", "vazio", "Selecione um agente no escritório."));
        return;
      }
      const est = app.estadoDe(ag.id);
      const topo = el("div", "ficha-topo");
      topo.append(el("h2", null, ag.nome), chipEstado(est.status));
      ficha.append(topo, el("p", "ficha-funcao", ag.funcao));
      const areaDoAgente = ag.area && app.areas.find((a) => a.id === ag.area);
      if (areaDoAgente) {
        const b = el("button", "especialista", `Especialista interno da ${areaDoAgente.nome}`);
        b.type = "button";
        b.addEventListener("click", () => app.selecionar(areaDoAgente.id));
        ficha.appendChild(b);
      }
      if (ag.relacao) ficha.appendChild(el("p", "ficha-funcao", ag.relacao));

      if (est.status === "NAO_IMPLEMENTADO") {
        ficha.appendChild(el("p", "ficha-aviso", "Agente ainda não implementado. A estação está reservada no escritório."));
        return;
      }
      const dl = el("dl", "campos");
      const campo = (rotulo, valor) => dl.append(el("dt", null, rotulo), el("dd", valor ? null : "nd", valor || "—"));
      // disponibilidade do personagem (onde está) é separada do resultado da tarefa (histórico)
      campo("Disponibilidade", est.disponibilidade);
      campo("Empresa", est.empresa);
      campo("Competência", est.competencia);
      campo("Solicitação", est.solicitacao);
      campo("Tarefa / resultado", est.tarefa);
      campo("Início", est.inicio);
      if (est.fim) campo("Fim", est.fim);
      campo("Última atualização", est.atualizacao);
      ficha.appendChild(dl);

      const pend = el("div", "pendencias");
      const lista = est.pendencias || [];
      pend.appendChild(el("h3", null, `Pendências (${lista.length})`));
      if (lista.length) {
        const ul = el("ul");
        lista.forEach((p) => ul.appendChild(el("li", null, p)));
        pend.appendChild(ul);
      } else {
        pend.appendChild(el("p", "nd", "Nenhuma."));
      }
      ficha.appendChild(pend);

      if (est.mensagem) {
        const msg = el("blockquote", "mensagem");
        msg.append(el("span", "mensagem-rotulo", "Mensagem do agente"), el("p", null, est.mensagem));
        ficha.appendChild(msg);
      }
    }

    function renderizar() {
      // painel aberto/fechado
      area.classList.toggle("com-painel", app.painelAberto);
      gaveta.toggleAttribute("inert", !app.painelAberto);
      gaveta.setAttribute("aria-hidden", app.painelAberto ? "false" : "true");

      // cenário ativo
      caixaCenarios.querySelectorAll(".cenario").forEach((b) => {
        const ativo = b.dataset.id === app.cenario.id;
        b.classList.toggle("ativo", ativo);
        b.setAttribute("aria-checked", ativo ? "true" : "false");
      });
      $("cenario-desc").textContent = app.cenario.descricao + (app.alterado ? " (alterado manualmente)" : "");
      $("cenario-atual").textContent = app.cenario.titulo;

      // resumo no topo
      const resumo = $("resumo");
      resumo.textContent = "";
      const contagem = {};
      app.agentes.forEach((a) => {
        const s = app.estadoDe(a.id).status;
        contagem[s] = (contagem[s] || 0) + 1;
      });
      EV.ORDEM_ESTADOS.filter((s) => contagem[s]).forEach((s) => {
        const info = EV.ESTADOS[s];
        resumo.appendChild(chipEstado(s, `${info.simbolo} ${contagem[s]} ${info.rotulo}`));
      });

      const ag = app.agentes.find((a) => a.id === app.selecionado);
      renderizarFicha(ag);

      // controles de desenvolvimento seguem o agente selecionado
      const editavel = ag && ag.implementado;
      seletor.disabled = !editavel;
      $("dev-agente").textContent = ag ? ag.nome : "nenhum";
      if (editavel) seletor.value = app.estadoDe(ag.id).status;
      $("dev-nota").textContent = editavel
        ? "Altera apenas os dados fictícios em memória. Recarregar a página desfaz."
        : "Agentes não implementados permanecem como \"Em breve\".";
    }

    app.aoMudar(renderizar);
    renderizar();
  }

  EV.painel = { criar };
})();
