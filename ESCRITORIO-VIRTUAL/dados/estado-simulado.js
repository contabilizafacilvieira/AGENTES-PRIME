/*
 * ESTADO OPERACIONAL SIMULADO - Escritório Virtual (AGENTES PRIME)
 *
 * TODOS OS DADOS DESTE ARQUIVO SÃO FICTÍCIOS. Nenhuma informação vem de agentes reais,
 * de CLIENTES/ ou de LIBERADOS/. Este arquivo é o único lugar onde os dados da simulação ficam.
 *
 * Contrato (versão 2), pensado para ser gerado no futuro pelo Coordenador Geral:
 *   agentes[]  : quem existe no escritório (id, nome, nomeCurto, funcao, implementado; opcionais:
 *                area = área a que pertence como especialista interno, relacao = papel em relação à Contabilidade)
 *   areas[]    : áreas representadas (id, nome, funcao, especialistas[] = { agente } ou { nome } "em breve")
 *   cenarios[] : estados de demonstração; cada cenário declara a SOL exibida (solicitacao = { id, estado }: aberta,
 *                ENCERRADA ou CANCELADA) e tem estados[idDoAgente] com:
 *                status, empresa, competencia, solicitacao, tarefa, inicio,
 *                atualizacao, pendencias[], mensagem, local ("mesa" | "copa"), disponibilidade
 * Regras: quem participa de SOL aberta fica na mesa; SOL encerrada/cancelada nunca aparece como "Concluído" (copa ≠ aprovação).
 * Status reconhecidos: ver js/estados.js. Agentes com implementado=false são sempre
 * exibidos como NAO_IMPLEMENTADO, independentemente do cenário (sem personagem, sem estado, sem regras).
 * A posição das mesas na planta NÃO define ordem de execução: quem distribui as tarefas é o Coordenador.
 */
window.ESCRITORIO_DADOS = {
  versaoContrato: 2,
  fonte: "SIMULACAO",

  agentes: [
    {
      id: "coordenador",
      nome: "Coordenador Geral",
      nomeCurto: "Coordenador",
      funcao: "Recebe a ordem do Supervisor, aciona Documentos e acompanha as áreas. Recebe o fechamento após a Conciliação para análise junto ao Supervisor; no piloto atual, recebe propostas parciais para conferência.",
      implementado: true
    },
    {
      id: "documentos",
      nome: "Agente de Documentos",
      nomeCurto: "Documentos",
      funcao: "Recebe, identifica e distribui os documentos: extratos ao Financeiro, folha ao DP e notas ao Fiscal. Faz triagem técnica; a análise pertence a cada área.",
      implementado: true
    },
    {
      id: "importacao",
      nome: "Importação VGROW",
      nomeCurto: "Importação",
      funcao: "Especialista interno da Contabilidade: fechamento das importações por conta e ordem. SIMULAÇÃO, somente VGROW; acionado só pelo Coordenador, após encaminhamento do Supervisor.",
      implementado: true,
      area: "contabilidade"
    },
    {
      id: "bancos",
      nome: "Bancos (Contabilidade)",
      nomeCurto: "Bancos",
      funcao: "Especialista interno da Contabilidade: prepara os lançamentos bancários a partir da conferência do Financeiro e, na mesma mesa, as propostas da Contabilidade/DP e da Contabilidade/Fiscal, com o plano de contas e as referências aprovadas da empresa. Código local, SIMULAÇÃO.",
      implementado: true,
      area: "contabilidade"
    },
    {
      id: "fiscal",
      nome: "Agente Fiscal",
      nomeCurto: "Fiscal",
      funcao: "Analisa notas e guias recebidas de Documentos; identifica competência, valores, retenções e pendências e entrega à Contabilidade. Código local em SIMULAÇÃO, sem apuração tributária completa.",
      implementado: true,
      relacao: "Fornece informações à Contabilidade"
    },
    {
      id: "dp",
      nome: "Agente de Departamento Pessoal",
      nomeCurto: "DP",
      funcao: "Recebe de Documentos o resumo da folha, os encargos e as provisões; confere os totais (sem calcular alíquota ou encargo) e entrega fatos e pendências à Contabilidade/DP. Código local, SIMULAÇÃO.",
      implementado: true,
      relacao: "Fornece informações à Contabilidade"
    },
    {
      id: "financeiro",
      nome: "Agente Financeiro",
      nomeCurto: "Financeiro",
      funcao: "Confere as movimentações financeiras: extrato × relação de pagamentos × comprovantes × documentos de suporte. Código local, SIMULAÇÃO. Não é conciliação contábil completa.",
      implementado: true,
      relacao: "Recebe de Documentos; analisa e repassa à Contabilidade"
    },
    {
      id: "conciliacao",
      nome: "Agente de Conciliação",
      nomeCurto: "Conciliação",
      funcao: "Após a Contabilidade, confere os lançamentos propostos com os suportes, saldos de abertura, extratos e documentos de terceiros (grupos A–E). Informa o alcance; não corrige, não aprova e não escritura. Entrega o resultado ao Coordenador e ao Supervisor. Código local, SIMULAÇÃO.",
      implementado: true,
      relacao: "Após Contabilidade → conferência → Coordenador e Supervisor"
    }
  ],

  areas: [
    {
      id: "contabilidade",
      nome: "Contabilidade",
      funcao: "Recebe os resultados das áreas e prepara propostas em SIMULAÇÃO: Bancos (do Financeiro), Contabilidade/DP (do DP) e Contabilidade/Fiscal (do Fiscal). A Conciliação confere o conjunto depois. Nada é aprovado nem escriturado; não é fechamento integral.",
      especialistas: [
        { agente: "importacao" },
        { agente: "bancos" },
        { nome: "Contabilidade/DP (na mesa de Bancos)", via: "bancos" },
        { nome: "Contabilidade/Fiscal (na mesa de Bancos)", via: "bancos" },
        { nome: "Apuração tributária completa" },
        { nome: "Demais ajustes de fechamento" }
      ]
    }
  ],

  cenarios: [
    {
      id: "repouso",
      titulo: "Escritório em repouso",
      descricao: "Nenhuma solicitação em andamento. Agentes disponíveis na copa.",
      estados: {
        coordenador: {
          status: "LIVRE",
          tarefa: "Aguardando novas solicitações do Supervisor Contábil.",
          atualizacao: "30/10/2026 08:58",
          mensagem: "Sem solicitações abertas. Pendências da EMPRESA-TESTE (fictícia) seguem registradas.",
          local: "mesa"
        },
        documentos: {
          status: "LIVRE",
          atualizacao: "30/10/2026 08:58",
          tarefa: "Aguardando ordem de serviço.",
          mensagem: "Disponível para nova ordem de serviço.",
          local: "copa"
        },
        importacao: {
          status: "LIVRE",
          atualizacao: "30/10/2026 08:58",
          tarefa: "Sem SOL encaminhada (somente VGROW).",
          local: "copa"
        },
        financeiro: { status: "LIVRE", tarefa: "Aguardando solicitação Financeiro → Contabilidade/Bancos.", local: "copa" },
        bancos: { status: "LIVRE", tarefa: "Sem conferência financeira encaminhada.", local: "copa" }
      }
    },
    {
      id: "trabalhando",
      solicitacao: { id: "SOL-001", estado: "DOCUMENTOS_EM_ANDAMENTO" },
      titulo: "Documentos trabalhando",
      descricao: "O Coordenador delegou a SOL-001 ao Agente de Documentos.",
      estados: {
        coordenador: {
          status: "TRABALHANDO",
          empresa: "EMPRESA-TESTE (fictícia)",
          competencia: "2026-09",
          solicitacao: "SOL-001",
          tarefa: "Acompanhando a análise documental delegada.",
          inicio: "30/10/2026 09:10",
          atualizacao: "30/10/2026 09:14",
          mensagem: "Ordem de serviço SOL-001 emitida para EMPRESA-TESTE. Aguardando relatório do Agente de Documentos.",
          local: "mesa"
        },
        documentos: {
          status: "TRABALHANDO",
          empresa: "EMPRESA-TESTE (fictícia)",
          competencia: "2026-09",
          solicitacao: "SOL-001",
          tarefa: "Inventariar e classificar os documentos de 2026-09.",
          inicio: "30/10/2026 09:12",
          atualizacao: "30/10/2026 09:14",
          mensagem: "Extração concluída: 3 arquivos, sem duplicidade. Preenchendo as fichas D1 a D3.",
          local: "mesa",
          pasta: true
        },
        importacao: { status: "LIVRE", tarefa: "Sem SOL encaminhada (somente VGROW).", local: "copa" },
        financeiro: { status: "LIVRE", tarefa: "Aguardando solicitação Financeiro → Contabilidade/Bancos.", local: "copa" },
        bancos: { status: "LIVRE", tarefa: "Sem conferência financeira encaminhada.", local: "copa" }
      }
    },
    {
      id: "aguardando",
      solicitacao: { id: "SOL-001", estado: "AGUARDANDO_SUPERVISOR" },
      titulo: "Aguardando Supervisor",
      descricao: "Relatório entregue; Documentos permanece na mesa até a conclusão da SOL e o resultado continua no painel.",
      estados: {
        coordenador: {
          status: "AGUARDANDO_SUPERVISOR",
          empresa: "EMPRESA-TESTE (fictícia)",
          competencia: "2026-09",
          solicitacao: "SOL-001",
          tarefa: "LOTE-001 (SIMULAÇÃO) apresentado para validação.",
          inicio: "30/10/2026 09:10",
          atualizacao: "30/10/2026 09:31",
          pendencias: ["Validação do LOTE-001 (SIMULAÇÃO) pelo Supervisor Contábil"],
          mensagem: "Resultado consolidado. Nada segue para o Domínio sem aprovação explícita do Supervisor.",
          local: "mesa",
          pasta: true
        },
        documentos: {
          status: "CONCLUIDO",
          empresa: "EMPRESA-TESTE (fictícia)",
          competencia: "2026-09",
          solicitacao: "SOL-001",
          tarefa: "Concluído — relatório entregue",
          inicio: "30/10/2026 09:12",
          atualizacao: "30/10/2026 09:20",
          mensagem: "Relatório entregue ao Coordenador Geral. Nenhum arquivo foi alterado.",
          local: "mesa",
          disponibilidade: "Na mesa · solicitação ainda não concluída"
        },
        importacao: { status: "LIVRE", tarefa: "Sem SOL encaminhada (somente VGROW).", local: "copa" },
        financeiro: { status: "LIVRE", tarefa: "Aguardando solicitação Financeiro → Contabilidade/Bancos.", local: "copa" },
        bancos: { status: "LIVRE", tarefa: "Sem conferência financeira encaminhada.", local: "copa" }
      }
    },
    {
      id: "importacao",
      solicitacao: { id: "SOL-003", estado: "AGUARDANDO_SUPERVISOR" },
      titulo: "Importação calculando",
      descricao: "O Supervisor conferiu os campos e o Coordenador encaminhou à Importação (SIMULAÇÃO).",
      estados: {
        coordenador: {
          status: "TRABALHANDO",
          empresa: "EMPRESA-FICTICIA (VGROW de teste)",
          competencia: "2026-09",
          solicitacao: "SOL-003",
          tarefa: "Encaminhou à Importação VGROW; acompanhando o cálculo.",
          inicio: "30/10/2026 11:02",
          atualizacao: "30/10/2026 11:20",
          mensagem: "A SOL só volta ao Supervisor quando a Importação devolver o resultado.",
          local: "mesa"
        },
        documentos: {
          status: "CONCLUIDO",
          empresa: "EMPRESA-FICTICIA (VGROW de teste)",
          competencia: "2026-09",
          solicitacao: "SOL-003",
          tarefa: "Concluído — relatório entregue",
          inicio: "30/10/2026 11:03",
          atualizacao: "30/10/2026 11:09",
          local: "mesa",
          disponibilidade: "Na mesa · solicitação ainda não concluída"
        },
        importacao: {
          status: "TRABALHANDO",
          empresa: "EMPRESA-FICTICIA (VGROW de teste)",
          competencia: "2026-09",
          solicitacao: "SOL-003",
          tarefa: "Calculando o fechamento das importações (SIMULAÇÃO).",
          inicio: "30/10/2026 11:19",
          atualizacao: "30/10/2026 11:20",
          local: "mesa"
        },
        financeiro: { status: "LIVRE", tarefa: "Aguardando solicitação Financeiro → Contabilidade/Bancos.", local: "copa" },
        bancos: { status: "LIVRE", tarefa: "Sem conferência financeira encaminhada.", local: "copa" }
      }
    },
    {
      id: "conferencia",
      solicitacao: { id: "SOL-003", estado: "AGUARDANDO_SUPERVISOR" },
      titulo: "Importação aguardando conferência",
      descricao: "Importação concluída; a SOL aguarda a conferência e a decisão do Supervisor.",
      estados: {
        coordenador: {
          status: "AGUARDANDO_SUPERVISOR",
          empresa: "EMPRESA-FICTICIA (VGROW de teste)",
          competencia: "2026-09",
          solicitacao: "SOL-003",
          tarefa: "SOL-003: Aguardando Supervisor",
          inicio: "30/10/2026 11:02",
          atualizacao: "30/10/2026 11:21",
          pendencias: ["Conferência manual do retorno da Importação (SIMULAÇÃO)"],
          mensagem: "Nada é liberado nem importado sem aprovação explícita do Supervisor.",
          local: "mesa"
        },
        documentos: {
          status: "CONCLUIDO",
          empresa: "EMPRESA-FICTICIA (VGROW de teste)",
          competencia: "2026-09",
          solicitacao: "SOL-003",
          tarefa: "Concluído — relatório entregue",
          inicio: "30/10/2026 11:03",
          atualizacao: "30/10/2026 11:09",
          local: "mesa",
          disponibilidade: "Na mesa · solicitação ainda não concluída"
        },
        importacao: {
          status: "CONCLUIDO",
          empresa: "EMPRESA-FICTICIA (VGROW de teste)",
          competencia: "2026-09",
          solicitacao: "SOL-003",
          tarefa: "Concluído — aguardando conferência",
          inicio: "30/10/2026 11:19",
          atualizacao: "30/10/2026 11:21",
          pendencias: ["1 processo aguardando aceite do Supervisor"],
          mensagem: "Retorno nº 1 entregue ao Coordenador: 2 processos fechados. SIMULAÇÃO — nada liberado nem importado.",
          local: "mesa",
          disponibilidade: "Na mesa · solicitação ainda não concluída"
        },
        financeiro: { status: "LIVRE", tarefa: "Aguardando solicitação Financeiro → Contabilidade/Bancos.", local: "copa" },
        bancos: { status: "LIVRE", tarefa: "Sem conferência financeira encaminhada.", local: "copa" }
      }
    },
    {
      id: "financeiro",
      solicitacao: { id: "SOL-004", estado: "FINANCEIRO_EM_ANDAMENTO" },
      titulo: "Financeiro conferindo",
      descricao: "Documentos organizou o lote; o Coordenador encaminhou ao Financeiro (código local, SIMULAÇÃO).",
      estados: {
        coordenador: { status: "TRABALHANDO", empresa: "EMPRESA-DEMO-FINANCEIRO (fictícia)", competencia: "2026-09", solicitacao: "SOL-004",
                       tarefa: "Encaminhou ao Financeiro; acompanhando a conferência das movimentações.", local: "mesa" },
        documentos: { status: "CONCLUIDO", empresa: "EMPRESA-DEMO-FINANCEIRO (fictícia)", competencia: "2026-09", solicitacao: "SOL-004",
                      tarefa: "Concluído — relatório entregue", local: "mesa",
                      disponibilidade: "Na mesa · solicitação ainda não concluída",
                      mensagem: "Documentos distribuídos ao Financeiro; o relatório fica com o Coordenador Geral." },
        importacao: { status: "LIVRE", tarefa: "Sem SOL encaminhada (somente VGROW).", local: "copa" },
        financeiro: { status: "TRABALHANDO", empresa: "EMPRESA-DEMO-FINANCEIRO (fictícia)", competencia: "2026-09", solicitacao: "SOL-004",
                      tarefa: "Conferindo extrato × relação × comprovantes × suportes.", local: "mesa", pasta: true },
        bancos: { status: "LIVRE", tarefa: "Aguardando a conferência do Financeiro.", local: "copa" }
      }
    },
    {
      id: "pendencia",
      solicitacao: { id: "SOL-001", estado: "AGUARDANDO_SUPERVISOR" },
      titulo: "Pendência",
      descricao: "Documento com divergência de titularidade.",
      estados: {
        coordenador: {
          status: "PENDENCIA",
          empresa: "EMPRESA-TESTE (fictícia)",
          competencia: "2026-09",
          solicitacao: "SOL-001",
          tarefa: "Registrar pendência e solicitar informação ao Supervisor.",
          inicio: "30/10/2026 09:10",
          atualizacao: "30/10/2026 09:22",
          pendencias: ["P-001 · D3: CNPJ do destinatário não cadastrado"],
          mensagem: "D3 fica fora de lotes reais até a decisão do Supervisor.",
          local: "mesa"
        },
        documentos: {
          status: "PENDENCIA",
          empresa: "EMPRESA-TESTE (fictícia)",
          competencia: "2026-09",
          solicitacao: "SOL-001",
          tarefa: "Concluído — relatório entregue com pendência de titularidade.",
          inicio: "30/10/2026 09:12",
          atualizacao: "30/10/2026 09:19",
          pendencias: [
            "P-001 · D3: destinatário \"FILIAL\" com CNPJ 33.333.333/3333-33 (fictício) não cadastrado",
            "P-002 · Razão de 2026-09 não recebido"
          ],
          mensagem: "A raiz do CNPJ do D3 difere da matriz. Proposta de pendência enviada ao Coordenador.",
          local: "mesa",
          disponibilidade: "Na mesa · solicitação ainda não concluída"
        },
        importacao: { status: "LIVRE", tarefa: "Sem SOL encaminhada (somente VGROW).", local: "copa" },
        financeiro: { status: "LIVRE", tarefa: "Aguardando solicitação Financeiro → Contabilidade/Bancos.", local: "copa" },
        bancos: { status: "LIVRE", tarefa: "Sem conferência financeira encaminhada.", local: "copa" }
      }
    },
    {
      id: "encerrada",
      solicitacao: { id: "SOL-001", estado: "ENCERRADA" },
      titulo: "Revisão parcial encerrada",
      descricao: "O Supervisor encerrou a revisão parcial da SOL-001. Pendências históricas preservadas; não é fechamento integral.",
      estados: {
        coordenador: {
          status: "PENDENCIA",
          empresa: "EMPRESA-TESTE (fictícia)",
          competencia: "2026-09",
          solicitacao: "SOL-001",
          tarefa: "SOL-001: Revisão parcial encerrada — não é fechamento integral; nada aprovado nem escriturado.",
          inicio: "30/10/2026 09:10",
          atualizacao: "30/10/2026 09:40",
          pendencias: ["P-001 · D3: CNPJ do destinatário não cadastrado (histórico preservado)", "P-002 · Razão de 2026-09 não recebido (histórico preservado)"],
          mensagem: "Revisão parcial encerrada pelo Supervisor. As pendências continuam registradas; é possível reabrir a revisão.",
          local: "mesa"
        },
        documentos: {
          status: "PENDENCIA",
          empresa: "EMPRESA-TESTE (fictícia)",
          competencia: "2026-09",
          solicitacao: "SOL-001",
          tarefa: "Revisão parcial encerrada — resultado da etapa preservado como histórico; pendências preservadas (não é fechamento integral)",
          inicio: "30/10/2026 09:12",
          atualizacao: "30/10/2026 09:20",
          pendencias: ["P-001 · D3: CNPJ do destinatário não cadastrado", "P-002 · Razão de 2026-09 não recebido"],
          mensagem: "3 documentos analisados; P-001 e P-002 continuam abertas no histórico.",
          local: "copa",
          disponibilidade: "Disponível · na copa (revisão parcial encerrada; estar na copa não indica aprovação)"
        },
        importacao: { status: "LIVRE", tarefa: "Sem SOL encaminhada (somente VGROW).", local: "copa" },
        financeiro: { status: "LIVRE", tarefa: "Aguardando solicitação Financeiro → Contabilidade/Bancos.", local: "copa" },
        bancos: { status: "LIVRE", tarefa: "Sem conferência financeira encaminhada.", local: "copa" }
      }
    },
    {
      id: "erro",
      solicitacao: { id: "SOL-002", estado: "AGUARDANDO_SUPERVISOR" },
      titulo: "Erro",
      descricao: "Bloqueio de segurança durante a execução (simulado).",
      estados: {
        coordenador: {
          status: "AGUARDANDO_SUPERVISOR",
          empresa: "EMPRESA-TESTE (fictícia)",
          competencia: "2026-09",
          solicitacao: "SOL-002",
          tarefa: "Comunicar o erro e aguardar orientação.",
          inicio: "30/10/2026 10:02",
          atualizacao: "30/10/2026 10:05",
          pendencias: ["Decidir se a SOL-002 será reemitida"],
          mensagem: "Erro do Agente de Documentos comunicado ao Supervisor. Nenhuma correção automática foi feita.",
          local: "mesa"
        },
        documentos: {
          status: "ERRO",
          empresa: "EMPRESA-TESTE (fictícia)",
          competencia: "2026-09",
          solicitacao: "SOL-002",
          tarefa: "Falhou — relatório não entregue",
          inicio: "30/10/2026 10:03",
          atualizacao: "30/10/2026 10:04",
          mensagem: "Chamada recusada pelo guarda: pasta fora da empresa da ordem ativa (exemplo simulado).",
          local: "mesa",
          disponibilidade: "Na mesa · solicitação ainda não concluída"
        },
        importacao: { status: "LIVRE", tarefa: "Sem SOL encaminhada (somente VGROW).", local: "copa" },
        financeiro: { status: "LIVRE", tarefa: "Aguardando solicitação Financeiro → Contabilidade/Bancos.", local: "copa" },
        bancos: { status: "LIVRE", tarefa: "Sem conferência financeira encaminhada.", local: "copa" }
      }
    },
    {
      id: "percurso",
      solicitacao: { id: "SOL-005", estado: "CONCILIACAO_EM_ANDAMENTO" },
      titulo: "Percurso completo: Conciliação conferindo",
      descricao: "Documentos distribuiu a Financeiro, DP e Fiscal; a Contabilidade preparou as propostas; a Conciliação confere o conjunto (SIMULAÇÃO).",
      estados: {
        coordenador: { status: "TRABALHANDO", empresa: "AMOSTRA-COMPLETA-FICTICIA", competencia: "2026-10", solicitacao: "SOL-005",
                       tarefa: "Conciliação conferindo a escrituração proposta com suportes e terceiros.", local: "mesa" },
        documentos: { status: "CONCLUIDO", empresa: "AMOSTRA-COMPLETA-FICTICIA", competencia: "2026-10", solicitacao: "SOL-005",
                      tarefa: "Concluído — relatório entregue", local: "mesa", disponibilidade: "Na mesa · solicitação ainda não concluída",
                      mensagem: "Documentos distribuídos ao Financeiro, ao DP e ao Fiscal; o relatório fica com o Coordenador Geral." },
        financeiro: { status: "CONCLUIDO", empresa: "AMOSTRA-COMPLETA-FICTICIA", competencia: "2026-10", solicitacao: "SOL-005",
                      tarefa: "Concluído — conferência entregue à Contabilidade/Bancos", local: "mesa",
                      disponibilidade: "Na mesa · solicitação ainda não concluída" },
        dp: { status: "CONCLUIDO", empresa: "AMOSTRA-COMPLETA-FICTICIA", competencia: "2026-10", solicitacao: "SOL-005",
              tarefa: "Análise do DP entregue à Contabilidade", local: "mesa", disponibilidade: "Na mesa · solicitação ainda não concluída",
              mensagem: "3 documentos, 8 fatos para a Contabilidade. Sem cálculo de folha, alíquota ou encargo presumido." },
        fiscal: { status: "CONCLUIDO", empresa: "AMOSTRA-COMPLETA-FICTICIA", competencia: "2026-10", solicitacao: "SOL-005",
                  tarefa: "Análise fiscal entregue à Contabilidade", local: "mesa", disponibilidade: "Na mesa · solicitação ainda não concluída" },
        bancos: { status: "CONCLUIDO", empresa: "AMOSTRA-COMPLETA-FICTICIA", competencia: "2026-10", solicitacao: "SOL-005",
                  tarefa: "Bancos, Contabilidade/DP e Contabilidade/Fiscal: propostas entregues à Conciliação (aguardando conferência)", local: "mesa",
                  disponibilidade: "Na mesa · solicitação ainda não concluída" },
        conciliacao: { status: "TRABALHANDO", empresa: "AMOSTRA-COMPLETA-FICTICIA", competencia: "2026-10", solicitacao: "SOL-005",
                       tarefa: "Conferindo a escrituração proposta com suportes, saldos e documentos de terceiros", local: "mesa", pasta: true },
        importacao: { status: "LIVRE", tarefa: "Sem SOL encaminhada (somente VGROW).", local: "copa" }
      }
    },
    {
      id: "offline",
      titulo: "Fim do expediente",
      descricao: "Agentes desligados.",
      estados: {
        coordenador: { status: "OFFLINE", atualizacao: "30/10/2026 18:30", mensagem: "Sessão encerrada.", local: "mesa" },
        documentos: { status: "OFFLINE", atualizacao: "30/10/2026 18:30", mensagem: "Sessão encerrada.", local: "mesa" },
        importacao: { status: "OFFLINE", atualizacao: "30/10/2026 18:30", mensagem: "Sessão encerrada.", local: "mesa" },
        financeiro: { status: "OFFLINE", atualizacao: "30/10/2026 18:30", mensagem: "Sessão encerrada.", local: "mesa" },
        bancos: { status: "OFFLINE", atualizacao: "30/10/2026 18:30", mensagem: "Sessão encerrada.", local: "mesa" }
      }
    }
  ]
};

// Fiscal, DP e Conciliação só têm atividade nos cenários que a declaram; nos demais ficam disponíveis na copa.
[["fiscal", "Aguardando notas e guias"], ["dp", "Aguardando documentos de pessoal de Documentos"], ["conciliacao", "Aguardando as propostas da Contabilidade"]]
  .forEach(([id, tarefa]) => ESCRITORIO_DADOS.cenarios.forEach(c => { if(!c.estados[id]) c.estados[id] = c.estados.coordenador.status === "OFFLINE" ? {status:"OFFLINE",local:"mesa",pendencias:[]} : {status:"LIVRE",local:"copa",tarefa,pendencias:[]}; }));
