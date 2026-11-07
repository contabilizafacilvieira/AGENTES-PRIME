/*
 * Catálogo dos estados visuais do Escritório Virtual.
 * Cada estado tem símbolo, texto e animação próprios: a cor nunca é a única indicação.
 */
(function () {
  "use strict";
  const EV = (window.EV = window.EV || {});

  EV.ESTADOS = {
    LIVRE: {
      rotulo: "Livre",
      simbolo: "●",
      cor: "#5cbf86",
      descricao: "Disponível para receber tarefas. Personagem em repouso, xícara no balão."
    },
    TRABALHANDO: {
      rotulo: "Trabalhando",
      simbolo: "⚙",
      cor: "#5aa7e6",
      descricao: "Executando uma tarefa. Digita no teclado e a tela do computador rola."
    },
    AGUARDANDO_SUPERVISOR: {
      rotulo: "Aguardando Supervisor",
      simbolo: "⏳",
      cor: "#e9a94b",
      descricao: "Precisa de decisão ou aprovação do Supervisor. Mão levantada, ampulheta."
    },
    PENDENCIA: {
      rotulo: "Pendência",
      simbolo: "!",
      cor: "#e8cf52",
      descricao: "Encontrou informação ausente ou divergência. Balão com exclamação pulando."
    },
    CONCLUIDO: {
      rotulo: "Concluído",
      simbolo: "✓",
      cor: "#4fc98d",
      descricao: "Tarefa finalizada. Visto no balão e brilho rápido."
    },
    ERRO: {
      rotulo: "Erro",
      simbolo: "✕",
      cor: "#e25d5d",
      descricao: "A execução falhou ou foi bloqueada. Tela piscando e personagem tremendo."
    },
    OFFLINE: {
      rotulo: "Offline",
      simbolo: "⏻",
      cor: "#8a93a0",
      descricao: "Agente desligado. Personagem acinzentado, tela apagada, \"Zz\"."
    },
    NAO_IMPLEMENTADO: {
      rotulo: "Em breve",
      simbolo: "◌",
      cor: "#9a8fc4",
      descricao: "Agente ainda não implementado. Silhueta translúcida e placa \"em breve\"."
    }
  };

  EV.ORDEM_ESTADOS = Object.keys(EV.ESTADOS);
})();
