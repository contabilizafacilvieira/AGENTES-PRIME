/*
 * Mapeamento PURO do estado real (API local) para os personagens do Escritório Virtual.
 * Não acessa rede, DOM nem relógio: recebe os dados e devolve os estados. Testável isoladamente (node).
 *
 * Entrada: { recentes: [{ sol, empresa, competencia, estado, etapas }], foco: detalhe da SOL acompanhada ou null }
 *   etapas = { documentos: {status, inicio, fim}, reconhecimento: {status, inicio, fim},
 *              importacao: {status, n, inicio, fim, resumo} }   (status: EM_ANDAMENTO, CONCLUIDA, FALHOU, PRONTO, ...)
 * Saída: { coordenador, documentos, importacao } no formato de estado do app, mais:
 *   local         "mesa" | "copa"          onde o personagem deve estar (disponibilidade)
 *   disponibilidade  texto exibido no painel, SEPARADO do resultado da tarefa (histórico)
 *   eventos       [{ id, tipo: "buscar" | "trabalhar" | "entregar", em }]  transições com horário
 * Regras: disponibilidade considera TODAS as tarefas ativas; o Coordenador mostra o estado real da SOL
 * (nunca "Aguardando Supervisor" com etapa em andamento); o resultado de uma etapa fica no painel depois que o
 * etapa termina; os participantes permanecem no posto até a conclusão global. Os eventos nunca disparam operações.
 * SOL FECHAMENTO_APROVADO (aprovação do Supervisor em SIMULAÇÃO) é fechada: participantes liberados para a copa; o texto nunca diz
 * "escriturado" nem "liberado". SOL ENCERRADA (revisão parcial) ou CANCELADA nunca vira "Concluído": pendências históricas de todas as áreas ficam
 * visíveis e a copa indica só disponibilidade. Bancos e Contabilidade/Fiscal aparecem lado a lado (nenhuma substitui a outra).
 * Percurso completo: Documentos → áreas acionadas (Financeiro, DP, Fiscal) → Contabilidade (Bancos, Contabilidade/DP,
 * Contabilidade/Fiscal) → Conciliação → Coordenador. Cada entrega visual corresponde a um horário registrado (inicio/fim) das
 * etapas; nada é inventado. Conciliação concluída nunca é aprovação: com divergência, pendência ou alcance parcial vira PENDÊNCIA.
 */
(function (raiz) {
  "use strict";

  const ROTULO_SOL = {
    DOCUMENTOS_EM_ANDAMENTO: "Documentos em andamento",
    AGUARDANDO_SUPERVISOR: "Aguardando Supervisor",
    PRONTO_PARA_FINANCEIRO: "Pronto para o Financeiro",
    FINANCEIRO_EM_ANDAMENTO: "Financeiro conferindo",
    BANCOS_EM_ANDAMENTO: "Contabilidade/Bancos preparando os lançamentos",
    DP_EM_ANDAMENTO: "DP analisando folha, encargos e provisões",
    FISCAL_EM_ANDAMENTO: "Fiscal analisando notas e guias",
    CONTABILIDADE_DP_EM_ANDAMENTO: "Contabilidade preparando propostas do DP",
    CONTABILIDADE_FISCAL_EM_ANDAMENTO: "Contabilidade preparando propostas do Fiscal",
    CONCILIACAO_EM_ANDAMENTO: "Conciliação conferindo a escrituração proposta",
    CANCELADA: "Cancelada",
    ENCERRADA: "Revisão parcial do piloto encerrada",
    FECHAMENTO_APROVADO: "Fechamento aprovado (SIMULAÇÃO)"
  };

  const etapa = (s, nome) => ((s && s.etapas) || {})[nome] || {};
  const emAndamento = (s, nome) => etapa(s, nome).status === "EM_ANDAMENTO";
  const base = (s) => (s ? { empresa: s.empresa, competencia: s.competencia, solicitacao: s.sol } : {});
  const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;
  const ETAPAS = ["documentos", "reconhecimento", "importacao", "financeiro", "dp", "fiscal", "bancos", "contabdp", "contabilfiscal", "conciliacao"];
  // SOL encerrada (revisão parcial do piloto) ou cancelada: NUNCA é fechamento integral concluído/aprovado/conciliado.
  const FECHADAS = ["ENCERRADA", "CANCELADA"];
  const fechada = (s) => !!s && FECHADAS.includes(s.estado);
  // Fechamento APROVADO pelo Supervisor (SIMULAÇÃO): SOL fechada — participantes liberados; nunca "escriturado" nem "liberado".
  const aprovada = (s) => !!s && s.estado === "FECHAMENTO_APROVADO";
  // A Contabilidade (personagem "bancos") atende duas etapas independentes: Bancos (do Financeiro) e Contabilidade/Fiscal.
  const PARTES_CONTABILIDADE = [["bancos", "Bancos"], ["contabdp", "Contabilidade/DP"], ["contabilfiscal", "Contabilidade/Fiscal"]];
  // prefixo das tentativas de cada parte da Contabilidade nos identificadores dos eventos (numerações independentes)
  const PREFIXO_PARTE = { bancos: "", contabdp: "D", contabilfiscal: "F" };
  // Resumo da Conciliação (CONCILIACAO_V1 em minúsculas; o histórico do Coordenador pode trazer maiúsculas)
  const contagem = (r, k) => Number((r || {})[k] ?? (r || {})[k.toUpperCase()] ?? 0);
  function pendenciasConciliacao(r, parcial) {
    return [contagem(r, "divergente") && `${plural(contagem(r, "divergente"), "verificação divergente", "verificações divergentes")}`,
            contagem(r, "pendente") && `${plural(contagem(r, "pendente"), "verificação pendente", "verificações pendentes")} (evidência ausente)`,
            parcial && "alcance parcial (verificações não executadas)"].filter(Boolean);
  }
  // pendências da Conciliação de uma SOL: resumo da etapa + vigência e alcance (estes só no detalhe da SOL acompanhada)
  const pendenciasConciliacaoDe = (s) => pendenciasConciliacao(etapa(s, "conciliacao").resumo, s.conciliacao_parcial)
    .concat(s.conciliacao_vigente === false ? ["Conciliação desatualizada — lançamentos alterados depois dela"] : []);
  // etapa planejada (consta no plano da SOL), mesmo que ainda não executada
  const planejada = (s, n) => { const st = etapa(s, n).status; return st !== undefined && st !== "NAO_APLICAVEL"; };

  // Pendências históricas de TODAS as áreas da SOL (resumos das etapas, falhas, tarefas das áreas e relatório).
  function pendenciasHistoricas(s) {
    const lista = [];
    const st = (n) => etapa(s, n).status;
    const r = (n) => etapa(s, n).resumo || {};
    if (st("documentos") === "FALHOU") lista.push("Documentos: execução com falha");
    if (etapa(s, "financeiro").bloqueado) lista.push("Financeiro: lote bloqueado (nada conferido nem escriturado)");
    if (st("financeiro") === "FALHOU") lista.push("Financeiro: falha — resultado não devolvido");
    pendenciasFinanceiro(r("financeiro")).forEach((p) => lista.push(`Financeiro: ${p}`));
    if (st("bancos") === "FALHOU") lista.push("Bancos: falha — propostas não entregues");
    if (r("bancos").incompletos) lista.push(`Bancos: ${plural(r("bancos").incompletos, "lançamento incompleto", "lançamentos incompletos")}`);
    if (st("fiscal") === "FALHOU") lista.push("Fiscal: falha — análise não entregue");
    if (r("fiscal").pendencias) lista.push(`Fiscal: ${r("fiscal").pendencias} pendência(s) fiscal(is)`);
    if (st("contabilfiscal") === "FALHOU") lista.push("Contabilidade/Fiscal: falha — propostas não entregues");
    if (st("dp") === "FALHOU") lista.push("DP: falha — análise não entregue");
    if (r("dp").pendencias) lista.push(`DP: ${plural(r("dp").pendencias, "pendência", "pendências")}`);
    if (st("contabdp") === "FALHOU") lista.push("Contabilidade/DP: falha — propostas não entregues");
    if (r("contabdp").incompletos) lista.push(`Contabilidade/DP: ${plural(r("contabdp").incompletos, "proposta incompleta", "propostas incompletas")}`);
    if (st("conciliacao") === "FALHOU") lista.push("Conciliação: falha — verificações não entregues");
    if (st("conciliacao") === "CONCLUIDA") pendenciasConciliacaoDe(s).forEach((p) => lista.push(`Conciliação: ${p}`));
    if (r("contabilfiscal").incompletos) lista.push(`Contabilidade/Fiscal: ${plural(r("contabilfiscal").incompletos, "proposta incompleta", "propostas incompletas")}`);
    if (r("importacao").bloqueios) lista.push(`Importação: ${plural(r("importacao").bloqueios, "processo bloqueado", "processos bloqueados")}`);
    if (r("importacao").aguardando_aceite) lista.push(`Importação: ${plural(r("importacao").aguardando_aceite, "processo aguardando", "processos aguardando")} aceite`);
    Object.values(s.falhas_areas || {}).forEach((m) => lista.push(String(m)));
    Object.values(s.tarefas_areas || {}).filter((t) => ["BLOQUEADO", "BLOQUEADO_POR_DEPENDENCIA", "FALHOU"].includes(t.estado))
      .forEach((t) => lista.push(`${t.area}: ${t.estado === "BLOQUEADO_POR_DEPENDENCIA" ? `aguarda ${t.dependencia || "outra área"}` : t.estado === "FALHOU" ? "falhou" : "bloqueado"}${t.motivo ? ` — ${t.motivo}` : ""}`));
    (s.pendencias || []).forEach((p) => lista.push(p));
    return [...new Set(lista)];
  }

  function pendenciasFinanceiro(r) {
    return [r.sem_suporte && `${plural(r.sem_suporte, "movimento sem suporte", "movimentos sem suporte")}`,
            r.comprovante_sem_natureza && `${plural(r.comprovante_sem_natureza, "comprovante sem documento da natureza", "comprovantes sem documento da natureza")}`,
            r.ambiguos && `${plural(r.ambiguos, "correspondência ambígua", "correspondências ambíguas")} (decisão do Supervisor)`,
            r.relacionados_sem_movimento && `${plural(r.relacionados_sem_movimento, "pagamento/documento sem movimento", "pagamentos/documentos sem movimento")}`]
      .filter(Boolean);
  }

  // SOL de referência para o histórico: a acompanhada, se tiver a etapa; senão a mais recente que tenha.
  function referencia(sols, foco, nome, temEtapa) {
    const f = foco && sols.find((s) => s.sol === foco);
    if (f && temEtapa(etapa(f, nome))) return f;
    return sols.filter((s) => temEtapa(etapa(s, nome)))
      .sort((a, b) => String(etapa(b, nome).inicio || "").localeCompare(String(etapa(a, nome).inicio || "")))[0] || null;
  }

  // ---- passagem da pasta de trabalho (somente visual; cada evento corresponde a uma mudança de etapa registrada)
  //   Coordenador → Documentos → Financeiro → Contabilidade/Bancos → Coordenador (fluxo FINANCEIRO_BANCOS)
  //   Coordenador → Documentos → Coordenador (fluxo DOCUMENTOS) · Coordenador ⇄ Importação (VGROW)
  // Bloqueio: nenhuma entrega; a pasta fica na área responsável.
  const INICIADA = ["EM_ANDAMENTO", "CONCLUIDA", "FALHOU"];
  const fluxoFinanceiro = (s) => etapa(s, "financeiro").status !== undefined && etapa(s, "financeiro").status !== "NAO_APLICAVEL";

  function evento(lista, s, prefixo, n, tipo, destino, em) {
    if (em) lista.push({ id: `${s.sol}:${prefixo}${n ? `:${n}` : ""}:${tipo}:${destino}`, tipo, destino, em });
  }

  function eventosDocumentos(sols) {
    const lista = [];
    sols.forEach((s) => {
      const e = etapa(s, "documentos");
      if (INICIADA.includes(e.status)) evento(lista, s, "doc", 0, "buscar", "coordenador", e.inicio);
      if (INICIADA.includes(e.status)) evento(lista, s, "doc", 0, "trabalhar", "documentos", e.inicio);
      if (e.status !== "CONCLUIDA" && e.status !== "FALHOU") return;
      const temFiscal = INICIADA.includes(etapa(s,'fiscal').status);
      const temDp = INICIADA.includes(etapa(s, "dp").status);
      // ordem de apresentação: Financeiro → DP → Fiscal (mesmo horário: a ordem de inclusão é preservada)
      if (fluxoFinanceiro(s) && (INICIADA.includes(etapa(s, "financeiro").status) || ["FINANCEIRO_EM_ANDAMENTO", "BANCOS_EM_ANDAMENTO"].includes(s.estado))) {
        evento(lista, s, "doc", 0, "entregar", "financeiro", e.fim);
      }
      if (temDp) evento(lista, s, "doc", 0, "entregar", "dp", e.fim);
      if (temFiscal) evento(lista,s,'doc',0,'entregar','fiscal',e.fim);
      if (!fluxoFinanceiro(s) && !temFiscal && !temDp) evento(lista, s, "doc", 0, "entregar", "coordenador", e.fim);
    });
    return lista.sort((a, b) => String(a.em).localeCompare(String(b.em)));
  }

  function eventosFinanceiro(sols) {
    const lista = [];
    sols.filter(fluxoFinanceiro).forEach((s) => {
      const e = etapa(s, "financeiro");
      const b = etapa(s, "bancos");
      // nova tentativa (decisão ou regra aprovada): a pasta volta do Coordenador para o Financeiro
      if (INICIADA.includes(e.status) && e.n > 1) evento(lista, s, "fin", e.n, "buscar", "coordenador", e.inicio);
      if (INICIADA.includes(e.status)) evento(lista, s, "fin", e.n, "trabalhar", "financeiro", e.inicio);
      if (e.status === "CONCLUIDA" && !e.bloqueado && (INICIADA.includes(b.status) || s.estado === "BANCOS_EM_ANDAMENTO")) {
        evento(lista, s, "fin", e.n, "entregar", "bancos", e.fim);
      }
    });
    return lista.sort((a, b) => String(a.em).localeCompare(String(b.em)));
  }

  // Contabilidade: Bancos (tentativas 1, 2…) e Contabilidade/Fiscal (tentativas F1, F2…) ficam LADO A LADO, cada uma com o
  // próprio resultado; nenhuma substitui a outra (eventos já emitidos não somem) e a fila segue a ordem dos horários.
  function eventosBancos(sols) {
    const lista = [];
    sols.forEach((s) => {
      // com Conciliação no plano, as partes não voltam ao Coordenador: a Contabilidade entrega o conjunto à Conciliação
      // quando ela começa (horário real de início da Conciliação)
      const comConciliacao = planejada(s, "conciliacao");
      PARTES_CONTABILIDADE.forEach(([n]) => {
        const e = etapa(s, n);
        if (n === "bancos" && !fluxoFinanceiro(s)) return;
        const k = n === "bancos" ? e.n : `${PREFIXO_PARTE[n]}${e.n || 1}`;
        if (INICIADA.includes(e.status)) evento(lista, s, "ban", k, "trabalhar", "bancos", e.inicio);
        if (e.status === "CONCLUIDA" && !comConciliacao) evento(lista, s, "ban", k, "entregar", "coordenador", e.fim);
      });
      const c = etapa(s, "conciliacao");
      if (comConciliacao && INICIADA.includes(c.status)) evento(lista, s, "ban", `C${c.n || 1}`, "entregar", "conciliacao", c.inicio);
    });
    return lista.sort((a, b) => String(a.em).localeCompare(String(b.em)));
  }

  // Onde está a pasta da SOL (desenhada na mesa, também no movimento reduzido) e se está parada por bloqueio.
  const DONO_ETAPA = [["documentos", "documentos"], ["financeiro", "financeiro"], ["dp", "dp"], ["fiscal", "fiscal"], ["bancos", "bancos"],
    ["contabdp", "bancos"], ["contabilfiscal", "bancos"], ["conciliacao", "conciliacao"]];
  function pastaDe(s) {
    if (!s) return null;
    const st = (n) => etapa(s, n).status;
    // etapa em andamento tem precedência (o plano executa uma etapa por vez)
    const ativa = DONO_ETAPA.find(([n]) => st(n) === "EM_ANDAMENTO");
    if (ativa) return { agente: ativa[1] };
    if (st("dp") === "FALHOU") return { agente: "dp", bloqueada: true, motivo: "Falha na análise do DP" };
    if (st("contabdp") === "FALHOU") return { agente: "bancos", bloqueada: true, motivo: "Falha na proposta do DP" };
    if (st("conciliacao") === "FALHOU") return { agente: "conciliacao", bloqueada: true, motivo: "Falha na Conciliação" };
    if(st('fiscal')==='EM_ANDAMENTO') return {agente:'fiscal'};
    if(st('fiscal')==='FALHOU') return {agente:'fiscal',bloqueada:true,motivo:'Falha na análise fiscal'};
    if(st('contabilfiscal')==='EM_ANDAMENTO') return {agente:'bancos'};
    if(st('contabilfiscal')==='FALHOU') return {agente:'bancos',bloqueada:true,motivo:'Falha na proposta fiscal'};
    if (fluxoFinanceiro(s)) {
      if (st("financeiro") === "EM_ANDAMENTO" || s.estado === "FINANCEIRO_EM_ANDAMENTO") return { agente: "financeiro" };
      if (st("bancos") === "EM_ANDAMENTO" || s.estado === "BANCOS_EM_ANDAMENTO") return { agente: "bancos" };
      if (etapa(s, "financeiro").bloqueado) return { agente: "financeiro", bloqueada: true, motivo: "Lote bloqueado pelo Financeiro" };
      if (st("financeiro") === "FALHOU") return { agente: "financeiro", bloqueada: true, motivo: "Falha no Financeiro" };
      if (st("bancos") === "FALHOU") return { agente: "bancos", bloqueada: true, motivo: "Falha em Contabilidade/Bancos" };
      if (st("financeiro") === "NAO_EXECUTADA") return { agente: "documentos", bloqueada: true, motivo: "Etapa de Documentos parou (problema estrutural)" };
      return { agente: "coordenador" };
    }
    if (st("importacao") === "EM_ANDAMENTO") return { agente: "importacao" };
    return { agente: "coordenador" };
  }

  function eventosDe(sols, nome, prefixo) {
    const lista = [];
    sols.forEach((s) => {
      const e = etapa(s, nome);
      const n = e.n ? `:${e.n}` : "";
      if (e.inicio && ["EM_ANDAMENTO", "CONCLUIDA", "FALHOU"].includes(e.status)) {
        lista.push({ id: `${s.sol}:${prefixo}${n}:buscar`, tipo: "buscar", destino: "coordenador", em: e.inicio });
        lista.push({ id: `${s.sol}:${prefixo}${n}:trabalhar`, tipo: "trabalhar", destino: nome, em: e.inicio });
      }
      if (e.fim && (e.status === "CONCLUIDA" || e.status === "FALHOU")) {
        lista.push({ id: `${s.sol}:${prefixo}${n}:entregar`, tipo: "entregar", destino: "coordenador", em: e.fim });
      }
    });
    return lista.sort((a, b) => String(a.em).localeCompare(String(b.em)));
  }

  function coordenador(sols, foco) {
    const f = foco && sols.find((s) => s.sol === foco);
    const ordem = f ? [f].concat(sols.filter((s) => s !== f)) : sols;
    const aguardando = sols.filter((s) => s.estado === "AGUARDANDO_SUPERVISOR" && !ETAPAS.some((n) => emAndamento(s, n)));
    const listaAguardando = aguardando.map((s) => `${s.sol} · ${s.empresa} · ${s.competencia}: aguardando decisão do Supervisor`);
    // resultado da Conciliação de cada SOL aguardando: divergências, pendências e falha ficam no painel do Coordenador
    aguardando.forEach((s) => {
      const c = etapa(s, "conciliacao");
      if (c.status === "FALHOU") listaAguardando.push(`${s.sol}: Conciliação falhou — verificações não entregues`);
      const p = pendenciasConciliacaoDe(s);
      if (c.status === "CONCLUIDA" && p.length) listaAguardando.push(`${s.sol}: Conciliação com ${p.join(", ")}`);
    });
    for (const s of ordem) {
      let tarefa = null;
      if (emAndamento(s, "documentos")) tarefa = "Delegou a ordem de serviço; acompanhando o Agente de Documentos";
      else if (emAndamento(s, "reconhecimento")) tarefa = "Reconhecimento automático dos campos (DUIMP/NFs) em andamento";
      else if (emAndamento(s, "importacao")) tarefa = "Encaminhou à Importação VGROW; acompanhando o cálculo";
      else if (emAndamento(s, "financeiro")) tarefa = "Encaminhou ao Financeiro; acompanhando a conferência das movimentações";
      else if (emAndamento(s, "bancos")) tarefa = "Encaminhou à Contabilidade/Bancos; acompanhando a preparação dos lançamentos";
      else if (emAndamento(s, 'fiscal')) tarefa = 'Fiscal analisando notas, guias e competências';
      else if (emAndamento(s, 'contabilfiscal')) tarefa = 'Contabilidade preparando propostas a partir do Fiscal';
      else if (emAndamento(s, "dp")) tarefa = "Encaminhou ao DP; acompanhando a análise de folha, encargos e provisões";
      else if (emAndamento(s, "contabdp")) tarefa = "Contabilidade preparando propostas a partir do DP";
      else if (emAndamento(s, "conciliacao")) tarefa = "Conciliação conferindo a escrituração proposta com suportes e terceiros";
      if (tarefa) {
        return Object.assign(base(s), {
          status: "TRABALHANDO", tarefa, inicio: etapa(s, "documentos").inicio || "",
          pendencias: listaAguardando, local: "mesa", disponibilidade: "No posto (sala do Coordenador)",
          mensagem: `${s.sol}: etapa em andamento. A SOL só vai ao Supervisor quando todas as etapas terminarem.`
        });
      }
    }
    const alvo = (f && aguardando.includes(f) && f) || aguardando[0];
    if (alvo) {
      return Object.assign(base(alvo), {
        status: "AGUARDANDO_SUPERVISOR", tarefa: `${alvo.sol}: ${ROTULO_SOL[alvo.estado] || alvo.estado}`,
        inicio: etapa(alvo, "documentos").inicio || "", pendencias: listaAguardando, local: "mesa",
        disponibilidade: "No posto (sala do Coordenador)", mensagem: "Resultado consolidado. Nada é liberado nem importado sem aprovação explícita do Supervisor."
      });
    }
    const ultima = f || sols[0];
    if (aprovada(ultima)) {
      return Object.assign(base(ultima), {
        status: "CONCLUIDO", tarefa: `${ultima.sol}: Fechamento aprovado (SIMULAÇÃO) — nada escriturado; TXT do Domínio só para importação manual`,
        inicio: etapa(ultima, "documentos").inicio || "", pendencias: [], local: "mesa", disponibilidade: "No posto (sala do Coordenador)",
        mensagem: "Aprovação do Supervisor registrada em SIMULAÇÃO. A situação efetiva do TXT do Domínio (só empresa fictícia; empresa real fica bloqueada) aparece no acompanhamento da SOL; a importação no Domínio é manual, pelo Supervisor."
      });
    }
    if (fechada(ultima)) {
      // Revisão parcial encerrada ou SOL cancelada: nunca "Concluído"; as pendências históricas continuam visíveis.
      const pend = pendenciasHistoricas(ultima);
      const cancelada = ultima.estado === "CANCELADA";
      return Object.assign(base(ultima), {
        status: pend.length && !cancelada ? "PENDENCIA" : "LIVRE",
        tarefa: cancelada ? `${ultima.sol}: Cancelada — nada aprovado, escriturado nem liberado`
          : `${ultima.sol}: Revisão parcial encerrada — não é fechamento integral; nada aprovado nem escriturado`,
        inicio: etapa(ultima, "documentos").inicio || "", pendencias: pend, local: "mesa", disponibilidade: "No posto (sala do Coordenador)",
        mensagem: cancelada ? "Solicitação cancelada. O histórico e as pendências registradas ficam preservados apenas para consulta."
          : "Revisão parcial do piloto encerrada pelo Supervisor. Pendências históricas preservadas; é possível reabrir a revisão."
      });
    }
    if (ultima && ultima.estado) {
      return Object.assign(base(ultima), {
        status: "CONCLUIDO", tarefa: `${ultima.sol}: ${ROTULO_SOL[ultima.estado] || ultima.estado}`, inicio: etapa(ultima, "documentos").inicio || "",
        pendencias: [], local: "mesa", disponibilidade: "No posto (sala do Coordenador)"
      });
    }
    return { status: "LIVRE", tarefa: "Aguardando solicitação do Supervisor", pendencias: [], local: "mesa", disponibilidade: "No posto (sala do Coordenador)" };
  }

  function documentos(sols, foco) {
    const ativa = sols.find((s) => emAndamento(s, "documentos"));
    const eventos = eventosDocumentos(sols);
    if (ativa) {
      return Object.assign(base(ativa), {
        status: "TRABALHANDO", tarefa: "Analisando os documentos do lote pelo extrator", inicio: etapa(ativa, "documentos").inicio,
        pendencias: [], local: "mesa", disponibilidade: "Ocupado · na mesa", eventos
      });
    }
    const ref = referencia(sols, foco, "documentos", (e) => e.status === "CONCLUIDA" || e.status === "FALHOU");
    const disp = { local: "copa", disponibilidade: "Disponível · na copa", eventos };
    if (!ref) return Object.assign({ status: "LIVRE", tarefa: "Aguardando ordem de serviço", pendencias: [] }, disp);
    const e = etapa(ref, "documentos");
    const pend = (foco && ref.sol === foco && ref.pendencias) || [];
    // a quem Documentos entregou (mesma regra da passagem da pasta): áreas acionadas; sem área acionada, ao Coordenador
    const destinos = [INICIADA.includes(etapa(ref, "financeiro").status) && "Financeiro", INICIADA.includes(etapa(ref, "fiscal").status) && "Fiscal"].filter(Boolean);
    const entrega = destinos.length ? `Documentos distribuídos ao ${destinos.join(" e ao ")}; o relatório fica com o Coordenador Geral.`
      : "Relatório entregue ao Coordenador Geral.";
    return Object.assign(base(ref), e.status === "CONCLUIDA"
      ? { status: "CONCLUIDO", tarefa: "Concluído — relatório entregue", mensagem: `${entrega} Nenhum arquivo foi alterado.` }
      : { status: "ERRO", tarefa: "Falhou — relatório não entregue", mensagem: "Execução com falha comunicada ao Coordenador; decisão do Supervisor." },
    { inicio: e.inicio, fim: e.fim, pendencias: pend }, disp);
  }

  function importacao(sols, foco) {
    const vgrow = sols.filter((s) => etapa(s, "importacao").status && etapa(s, "importacao").status !== "NAO_APLICAVEL");
    const ativa = vgrow.find((s) => emAndamento(s, "importacao"));
    const eventos = eventosDe(vgrow, "importacao", "imp");
    if (ativa) {
      return Object.assign(base(ativa), {
        status: "TRABALHANDO", tarefa: "Calculando o fechamento das importações (SIMULAÇÃO)", inicio: etapa(ativa, "importacao").inicio,
        pendencias: [], local: "mesa", disponibilidade: "Ocupado · na mesa", eventos
      });
    }
    const disp = { local: "copa", disponibilidade: "Disponível · na copa", eventos };
    const ref = referencia(vgrow, foco, "importacao", (e) => e.status === "CONCLUIDA" || e.status === "FALHOU");
    const pronta = vgrow.find((s) => etapa(s, "reconhecimento").status === "PRONTO" && etapa(s, "importacao").status === "NAO_SOLICITADA"
      && s.estado === "AGUARDANDO_SUPERVISOR");
    if (ref && !(pronta && foco === pronta.sol && ref.sol !== foco)) {
      const e = etapa(ref, "importacao");
      if (e.status === "FALHOU") {
        return Object.assign(base(ref), { status: "ERRO", tarefa: "Falhou — a Importação não devolveu resultado", inicio: e.inicio, pendencias: [] }, disp);
      }
      const r = e.resumo || {};
      const pend = [];
      if (r.bloqueios) pend.push(`${plural(r.bloqueios, "processo bloqueado", "processos bloqueados")} (fora do TXT)`);
      if (r.aguardando_aceite) pend.push(`${plural(r.aguardando_aceite, "processo aguardando", "processos aguardando")} aceite do Supervisor`);
      return Object.assign(base(ref), {
        status: "CONCLUIDO", tarefa: "Concluído — aguardando conferência", inicio: e.inicio, fim: e.fim, pendencias: pend,
        mensagem: `Retorno nº ${e.n} entregue ao Coordenador: ${plural(r.fechados || 0, "processo fechado", "processos fechados")}. SIMULAÇÃO — nada liberado nem importado.`
      }, disp);
    }
    if (pronta) {
      return Object.assign(base(pronta), {
        status: "LIVRE", tarefa: "Campos reconhecidos; aguardando conferência e encaminhamento do Supervisor", pendencias: []
      }, disp);
    }
    return Object.assign({ status: "LIVRE", tarefa: "Desativado — Importação VGROW fora de uso por decisão do Supervisor (código e histórico "
      + "preservados); a exportação TXT do Domínio segue com a Contabilidade", pendencias: [] }, disp);
  }

  // Financeiro e Contabilidade/Bancos: mesma lógica de disponibilidade e histórico dos demais (etapas reais da SOL).
  function especialista(sols, foco, nome, prefixo, textos) {
    const comEtapa = sols.filter((s) => etapa(s, nome).status && etapa(s, nome).status !== "NAO_APLICAVEL");
    const ativa = comEtapa.find((s) => emAndamento(s, nome));
    const eventos = textos.eventos(sols);
    if (ativa) {
      return Object.assign(base(ativa), { status: "TRABALHANDO", tarefa: textos.trabalhando, inicio: etapa(ativa, nome).inicio,
                                          pendencias: [], local: "mesa", disponibilidade: "Ocupado · na mesa", eventos });
    }
    const disp = { local: "copa", disponibilidade: "Disponível · na copa", eventos };
    const ref = referencia(comEtapa, foco, nome, (e) => e.status === "CONCLUIDA" || e.status === "FALHOU");
    if (!ref) return Object.assign({ status: "LIVRE", tarefa: textos.livre, pendencias: [] }, disp);
    const e = etapa(ref, nome);
    if (e.status === "FALHOU") {
      return Object.assign(base(ref), { status: "ERRO", tarefa: "Falhou — resultado não devolvido (tentativa preservada)", inicio: e.inicio, pendencias: [] }, disp);
    }
    if (e.bloqueado) {
      return Object.assign(base(ref), { status: "PENDENCIA", tarefa: "Lote bloqueado — devolvido ao Coordenador (nada conferido nem escriturado)",
                                        inicio: e.inicio, fim: e.fim, pendencias: [] }, disp);
    }
    return Object.assign(base(ref), { status: "CONCLUIDO", tarefa: textos.concluido, inicio: e.inicio, fim: e.fim,
                                      pendencias: textos.pendencias(e.resumo || {}), mensagem: textos.mensagem(e) }, disp);
  }

  function financeiro(sols, foco) {
    return especialista(sols, foco, "financeiro", "fin", {
      eventos: eventosFinanceiro,
      trabalhando: "Conferindo extrato × relação × comprovantes × suportes", livre: "Aguardando solicitação Financeiro → Contabilidade/Bancos",
      concluido: "Concluído — conferência entregue à Contabilidade/Bancos",
      pendencias: pendenciasFinanceiro,
      mensagem: (e) => `Tentativa nº ${e.n}: ${(e.resumo || {}).movimentos || 0} movimento(s) conferido(s). Não é conciliação contábil completa.`
    });
  }

  function fiscal(sols,foco) {
    return especialista(sols,foco,'fiscal','fis',{
      eventos: entrada=>{const r=[];entrada.forEach(s=>{const f=etapa(s,'fiscal');
        if(INICIADA.includes(f.status)) evento(r,s,'fis',f.n,'trabalhar','fiscal',f.inicio);
        if(f.status==='CONCLUIDA'&&INICIADA.includes(etapa(s,'contabilfiscal').status)) evento(r,s,'fis',f.n,'entregar','bancos',f.fim);
      });return r;},
      trabalhando:'Analisando documentos fiscais e competências',livre:'Aguardando notas e guias de Documentos',
      concluido:'Análise fiscal entregue à Contabilidade',pendencias:r=>r.pendencias?[`${r.pendencias} pendência(s) fiscal(is)`]:[],
      mensagem:e=>`${(e.resumo||{}).documentos||0} documento(s) analisado(s). Sem apuração completa ou escrituração.`
    });
  }

  // DP: recebe de Documentos (folha, encargos, provisões); entrega os fatos à Contabilidade (Contabilidade/DP).
  // Nova tentativa (retomada): a pasta volta do Coordenador para o DP.
  function dp(sols, foco) {
    return especialista(sols, foco, "dp", "dpa", {
      eventos: (entrada) => {
        const r = [];
        entrada.forEach((s) => {
          const e = etapa(s, "dp");
          if (INICIADA.includes(e.status) && e.n > 1) evento(r, s, "dpa", e.n, "buscar", "coordenador", e.inicio);
          if (INICIADA.includes(e.status)) evento(r, s, "dpa", e.n, "trabalhar", "dp", e.inicio);
          if (e.status === "CONCLUIDA" && INICIADA.includes(etapa(s, "contabdp").status)) evento(r, s, "dpa", e.n, "entregar", "bancos", e.fim);
        });
        return r.sort((a, b) => String(a.em).localeCompare(String(b.em)));
      },
      trabalhando: "Analisando folha, encargos e provisões (conferência de totais)", livre: "Aguardando documentos de pessoal de Documentos",
      concluido: "Análise do DP entregue à Contabilidade",
      pendencias: (r) => (r.pendencias ? [`${plural(r.pendencias, "pendência de DP", "pendências de DP")}`] : []),
      mensagem: (e) => `Tentativa nº ${e.n || 1}: ${(e.resumo || {}).documentos || 0} documento(s), ${(e.resumo || {}).fatos || 0} fato(s) para a Contabilidade. `
        + "Sem cálculo de folha, alíquota ou encargo presumido. SIMULAÇÃO."
    });
  }

  // Conciliação: recebe da Contabilidade (todas as propostas) e entrega o resultado ao Coordenador. Concluída NÃO é aprovação:
  // com divergência, pendência ou alcance parcial aparece como PENDÊNCIA; tudo conferido = SIMULAÇÃO conciliada no alcance.
  function conciliacao(sols, foco) {
    const est = especialista(sols, foco, "conciliacao", "con", {
      eventos: (entrada) => {
        const r = [];
        entrada.forEach((s) => {
          const e = etapa(s, "conciliacao");
          if (INICIADA.includes(e.status)) evento(r, s, "con", e.n || 1, "trabalhar", "conciliacao", e.inicio);
          if (e.status === "CONCLUIDA") evento(r, s, "con", e.n || 1, "entregar", "coordenador", e.fim);
        });
        return r.sort((a, b) => String(a.em).localeCompare(String(b.em)));
      },
      trabalhando: "Conferindo a escrituração proposta com suportes, saldos e documentos de terceiros",
      livre: "Aguardando as propostas da Contabilidade",
      concluido: "Verificações entregues ao Coordenador — conciliada no alcance da SIMULAÇÃO (não é aprovação)",
      pendencias: (r) => pendenciasConciliacao(r),
      mensagem: (e) => {
        const r = e.resumo || {};
        return `Tentativa nº ${e.n || 1}: ${contagem(r, "conferido")} conferida(s), ${contagem(r, "divergente")} divergente(s), `
          + `${contagem(r, "pendente")} pendente(s), ${contagem(r, "nao_aplicavel")} não aplicável(is). SIMULAÇÃO: o resultado vale só no alcance `
          + "verificado; não corrige, não aprova, não escritura e não libera.";
      }
    });
    const s = est.solicitacao && sols.find((x) => x.sol === est.solicitacao);
    if (s && est.status === "CONCLUIDO") est.pendencias = pendenciasConciliacaoDe(s);
    if (est.status === "CONCLUIDO" && est.pendencias.length) {
      est.status = "PENDENCIA";
      est.tarefa = "Verificações entregues ao Coordenador com divergências/pendências (nada foi corrigido nem aprovado)";
    }
    return est;
  }

  // Contabilidade (personagem "bancos"): Bancos e Contabilidade/Fiscal são etapas independentes da mesma SOL. As duas
  // aparecem, cada uma com o seu resultado; uma falha de Bancos continua visível mesmo com a Contabilidade/Fiscal concluída.
  const iniciadas = (s) => PARTES_CONTABILIDADE.filter(([n]) => INICIADA.includes(etapa(s, n).status));
  const contabilidadeAtiva = (s) => emAndamento(s, "bancos") || emAndamento(s, "contabdp") || emAndamento(s, "contabilfiscal");

  function bancos(sols, foco) {
    const eventos = eventosBancos(sols);
    const comEtapa = sols.filter((s) => iniciadas(s).length);
    const ativa = comEtapa.find(contabilidadeAtiva);
    if (ativa) {
      return Object.assign(base(ativa), {
        status: "TRABALHANDO", tarefa: emAndamento(ativa, "bancos") ? "Preparando as propostas da Contabilidade (SIMULAÇÃO)"
          : emAndamento(ativa, "contabdp") ? "Preparando as propostas da Contabilidade a partir do DP (SIMULAÇÃO)"
          : "Preparando as propostas da Contabilidade a partir do Fiscal (SIMULAÇÃO)",
        inicio: etapa(ativa, ["bancos", "contabdp", "contabilfiscal"].find((n) => emAndamento(ativa, n))).inicio, pendencias: [], local: "mesa",
        disponibilidade: "Ocupado · na mesa", eventos });
    }
    const disp = { local: "copa", disponibilidade: "Disponível · na copa", eventos };
    const terminou = (s) => iniciadas(s).some(([n]) => ["CONCLUIDA", "FALHOU"].includes(etapa(s, n).status));
    const recente = (s) => iniciadas(s).map(([n]) => String(etapa(s, n).inicio || "")).sort().pop() || "";
    const f = foco && comEtapa.find((s) => s.sol === foco && terminou(s));
    const ref = f || comEtapa.filter(terminou).sort((a, b) => recente(b).localeCompare(recente(a)))[0];
    if (!ref) return Object.assign({ status: "LIVRE", tarefa: "Sem resultado de área encaminhado à Contabilidade", pendencias: [] }, disp);
    const partes = iniciadas(ref).map(([n, nome]) => ({ n, nome, e: etapa(ref, n) }));
    const resultado = ({ n, e }) => e.status === "FALHOU" ? "Falhou — resultado não devolvido (tentativa preservada)"
      : e.status === "EM_ANDAMENTO" ? "em andamento"
      : n === "bancos" ? "Concluído — proposta de lançamentos aguardando conferência"
      : n === "contabdp" ? "Concluído — propostas a partir do DP aguardando conferência" : "Concluído — propostas a partir do Fiscal aguardando conferência";
    const pendencias = [];
    partes.forEach(({ n, nome, e }) => {
      const r = e.resumo || {};
      if (e.status === "FALHOU") pendencias.push(`${nome}: falha — propostas não entregues (tentativa preservada)`);
      if (r.incompletos) pendencias.push(`${partes.length > 1 ? `${nome}: ` : ""}${plural(r.incompletos, "lançamento incompleto", "lançamentos incompletos")}`
        + `${n === "bancos" ? " (falta regra, conta ou suporte)" : ""}`);
    });
    const ultimo = partes.map((p) => p.e).sort((a, b) => String(b.fim || b.inicio || "").localeCompare(String(a.fim || a.inicio || "")))[0];
    return Object.assign(base(ref), {
      status: partes.some((p) => p.e.status === "FALHOU") ? "ERRO" : "CONCLUIDO",
      tarefa: partes.length === 1 ? resultado(partes[0]) : partes.map((p) => `${p.nome}: ${resultado(p)}`).join(" · "),
      inicio: partes.map((p) => String(p.e.inicio || "")).sort()[0], fim: ultimo.fim, pendencias,
      mensagem: partes.map(({ nome, e }) => e.status === "FALHOU" ? `${nome} (tentativa nº ${e.n || 1}): falhou; nada foi entregue.`
        : `${nome} (tentativa nº ${e.n || 1}): ${(e.resumo || {}).propostos || 0} proposto(s), ${(e.resumo || {}).incompletos || 0} incompleto(s).`).join(" ")
        + " SIMULAÇÃO — nada liberado nem importado."
    }, disp);
  }

  function operacao(entrada) {
    const sols = ((entrada && entrada.recentes) || []).slice();
    const foco = entrada && entrada.foco;
    if (foco && foco.sol) {
      const i = sols.findIndex((s) => s.sol === foco.sol);
      // a lista geral é lida continuamente; o detalhe da SOL acompanhada só completa o que falta (pendências)
      // tarefas e falhas por área só existem no detalhe: completam as pendências históricas
      const atual = Object.assign({}, foco, i >= 0 ? sols[i] : {}, { pendencias: foco.pendencias, tarefas_areas: foco.tarefas_areas, falhas_areas: foco.falhas_areas,
                                                                     conciliacao_vigente: foco.conciliacao_vigente, conciliacao_parcial: foco.conciliacao_parcial });
      if (i >= 0) sols[i] = atual;
      else sols.unshift(atual);
    }
    // O mesmo personagem da Contabilidade recebe Bancos e Contabilidade/Fiscal: as duas etapas continuam separadas
    // (nenhuma substitui a outra; ver bancos() e eventosBancos()).
    const idFoco = foco && foco.sol;
    const estados = {
      coordenador: coordenador(sols, idFoco),
      documentos: documentos(sols, idFoco),
      importacao: importacao(sols, idFoco),
      financeiro: financeiro(sols, idFoco),
      fiscal: fiscal(sols,idFoco),
      dp: dp(sols, idFoco),
      bancos: bancos(sols, idFoco),
      conciliacao: conciliacao(sols, idFoco)
    };
    // Encerrar uma etapa não encerra a solicitação. Quem participou permanece no posto até a conclusão global.
    const encerrada = s => ['CONCLUIDA','ENCERRADA','FINALIZADA','CANCELADA','FECHAMENTO_APROVADO'].includes(s.estado);
    const funcoes = {documentos, financeiro, dp, fiscal, bancos, conciliacao, importacao};
    const acionado = (s, nome) => nome === 'bancos' ? iniciadas(s).length > 0 : INICIADA.includes(etapa(s,nome).status);
    const ocupado = (s, nome) => nome === 'bancos' ? contabilidadeAtiva(s) : emAndamento(s,nome);
    for (const nome of Object.keys(funcoes)) {
      const acionadas = sols.filter(s => !encerrada(s) && acionado(s,nome));
      const alvo = acionadas.find(s=>ocupado(s,nome)) || acionadas.find(s=>s.sol===idFoco) || acionadas[0];
      if (alvo) {
        const eventos = estados[nome].eventos;
        estados[nome] = funcoes[nome]([alvo], alvo.sol);
        Object.assign(estados[nome], {eventos, local:'mesa', disponibilidade: ocupado(alvo,nome)
          ? 'Ocupado · trabalhando na mesa' : 'Na mesa · solicitação ainda não concluída'});
        if (!ocupado(alvo,nome)) estados[nome].mensagem = (estados[nome].mensagem || '') +
          ' Permanece no posto até a conclusão integral da solicitação, incluindo a conferência do Supervisor.';
      }
    }
    // Resultado de etapa de SOL encerrada/cancelada: histórico, nunca "Concluído". Disponibilidade (copa) ≠ resultado contábil.
    for (const nome of Object.keys(funcoes)) {
      const est = estados[nome];
      const s = est.solicitacao && sols.find((x) => x.sol === est.solicitacao);
      if (aprovada(s) && est.status !== 'TRABALHANDO' && est.local === 'copa') {
        if (est.status === 'CONCLUIDO') est.tarefa = 'Etapa concluída — fechamento aprovado pelo Supervisor (SIMULAÇÃO; nada escriturado)';
        est.disponibilidade = 'Disponível · na copa (fechamento aprovado em SIMULAÇÃO)';
        continue;
      }
      if (!fechada(s) || est.status === 'TRABALHANDO' || est.local !== 'copa') continue;
      const cancelada = s.estado === 'CANCELADA';
      const motivo = cancelada ? 'solicitação cancelada' : 'revisão parcial encerrada';
      if (est.status === 'CONCLUIDO') {
        est.status = est.pendencias && est.pendencias.length && !cancelada ? 'PENDENCIA' : 'LIVRE';
        est.tarefa = `${cancelada ? 'Cancelada' : 'Revisão parcial encerrada'} — resultado da etapa preservado como histórico`
          + `${est.pendencias && est.pendencias.length ? '; pendências preservadas' : ''} (não é fechamento integral)`;
      }
      est.disponibilidade = `Disponível · na copa (${motivo}; estar na copa não indica aprovação)`;
    }
    // pasta: SOL com etapa em andamento; senão a acompanhada; senão a mais recente
    const ativa = sols.find((s) => ETAPAS.some((n) => emAndamento(s, n)) || (/_EM_ANDAMENTO$/.test(s.estado || "") && s.estado !== "DOCUMENTOS_EM_ANDAMENTO"));
    const p = pastaDe(ativa || (idFoco && sols.find((s) => s.sol === idFoco)) || sols[0]);
    if (p && estados[p.agente]) Object.assign(estados[p.agente], { pasta: true, pasta_bloqueada: !!p.bloqueada, pasta_motivo: p.motivo || "" });
    return estados;
  }

  const api = { operacao, pastaDe };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else (raiz.EV = raiz.EV || {}).mapa = api;
})(typeof window !== "undefined" ? window : this);
