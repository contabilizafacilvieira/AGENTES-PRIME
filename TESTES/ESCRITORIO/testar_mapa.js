/*
 * Bateria da função PURA de mapeamento do Escritório Virtual (ESCRITORIO-VIRTUAL/js/mapa.js).
 * Somente dados fictícios em memória: não acessa a API, documentos, registros nem o runtime.
 *
 * Uso (a partir da raiz AGENTES-PRIME):  node TESTES/ESCRITORIO/testar_mapa.js
 */
"use strict";
const path = require("path");
const { operacao: mapear } = require(path.join(__dirname, "..", "..", "ESCRITORIO-VIRTUAL", "js", "mapa.js"));
// Esta bateria confere eventos de passagem; as ações de trabalho e sua ordem são testadas em testar_ciclo_solicitacao.js.
function operacao(entrada) { const r=mapear(entrada);Object.values(r).forEach(e=>{if(e.eventos)e.eventos=e.eventos.filter(v=>v.tipo!=='trabalhar');});return r; }

const resultados = [];
const registrar = (caso, ok, detalhe = "") => resultados.push([caso, !!ok, detalhe]);

const T = (m) => `2026-10-31T10:${String(m).padStart(2, "0")}:00-03:00`;
function sol(id, estado, etapas, extra = {}) {
  return Object.assign({ sol: id, empresa: "EMPRESA-FICTICIA", competencia: "2026-09", estado, etapas }, extra);
}
const docs = (status, i, f) => ({ status, inicio: T(i), fim: f === undefined ? null : T(f) });
const NA = { status: "NAO_APLICAVEL" };

function congelar(o) {
  Object.values(o).forEach((v) => v && typeof v === "object" && congelar(v));
  return Object.freeze(o);
}

// M-01 sem dados
let r = operacao({ recentes: [], foco: null });
registrar("M-01 sem solicitações: Coordenador livre no posto; Documentos e Importação disponíveis na copa",
  r.coordenador.status === "LIVRE" && r.coordenador.local === "mesa" && r.documentos.status === "LIVRE" && r.documentos.local === "copa"
  && r.importacao.status === "LIVRE" && r.importacao.local === "copa");

// M-02 Documentos em andamento
const A1 = sol("SOL-2026-900001", "DOCUMENTOS_EM_ANDAMENTO", { documentos: docs("EM_ANDAMENTO", 1), reconhecimento: { status: "NAO_EXECUTADO" }, importacao: { status: "NAO_SOLICITADA" } });
r = operacao({ recentes: [A1], foco: { sol: A1.sol, pendencias: [] } });
registrar("M-02 Documentos trabalhando: Coordenador TRABALHANDO (nunca Aguardando Supervisor); Documentos na mesa",
  r.coordenador.status === "TRABALHANDO" && r.documentos.status === "TRABALHANDO" && r.documentos.local === "mesa"
  && r.documentos.eventos.length === 1 && r.documentos.eventos[0].tipo === "buscar" && r.documentos.eventos[0].em === T(1));

// M-03 Documentos concluído, reconhecimento em andamento (SOL já em AGUARDANDO_SUPERVISOR no registro)
const A2 = sol("SOL-2026-900001", "AGUARDANDO_SUPERVISOR", { documentos: docs("CONCLUIDA", 1, 6), reconhecimento: { status: "EM_ANDAMENTO", inicio: T(6) }, importacao: { status: "NAO_SOLICITADA" } });
r = operacao({ recentes: [A2], foco: { sol: A2.sol, pendencias: ["P-01 · Documento · NF 1001"] } });
registrar("M-03 reconhecimento em andamento: Coordenador TRABALHANDO, não Aguardando Supervisor",
  r.coordenador.status === "TRABALHANDO" && /Reconhecimento/.test(r.coordenador.tarefa), r.coordenador.tarefa);
registrar("M-04 Documentos preserva resultado e permanece na mesa enquanto a SOL não terminou",
  r.documentos.status === "CONCLUIDO" && r.documentos.tarefa === "Concluído — relatório entregue" && r.documentos.local === "mesa"
  && r.documentos.disponibilidade.includes('não concluída') && r.documentos.pendencias.length === 1
  && r.documentos.eventos.map((e) => e.tipo).join() === "buscar,entregar");

// M-05 Importação em andamento
const A3 = sol("SOL-2026-900001", "AGUARDANDO_SUPERVISOR", { documentos: docs("CONCLUIDA", 1, 6), reconhecimento: { status: "PRONTO", fim: T(8) },
  importacao: { status: "EM_ANDAMENTO", n: 1, inicio: T(20), fim: null } });
r = operacao({ recentes: [A3], foco: { sol: A3.sol, pendencias: [] } });
registrar("M-05 Importação calculando: na mesa; Coordenador TRABALHANDO; Documentos permanece na mesa",
  r.importacao.status === "TRABALHANDO" && r.importacao.local === "mesa" && r.coordenador.status === "TRABALHANDO"
  && r.documentos.local === "mesa" && r.documentos.tarefa === "Concluído — relatório entregue");

// M-06 Importação concluída: resultado da etapa separado do estado da SOL
const A4 = sol("SOL-2026-900001", "AGUARDANDO_SUPERVISOR", { documentos: docs("CONCLUIDA", 1, 6), reconhecimento: { status: "PRONTO", fim: T(8) },
  importacao: { status: "CONCLUIDA", n: 1, inicio: T(20), fim: T(21), resumo: { fechados: 1, bloqueios: 1, aguardando_aceite: 1 } } });
r = operacao({ recentes: [A4], foco: { sol: A4.sol, pendencias: [] } });
registrar("M-06 Importação \"Concluído — aguardando conferência\" enquanto a SOL fica AGUARDANDO_SUPERVISOR",
  r.importacao.status === "CONCLUIDO" && r.importacao.tarefa === "Concluído — aguardando conferência" && r.importacao.local === "mesa"
  && r.importacao.pendencias.length === 2 && r.coordenador.status === "AGUARDANDO_SUPERVISOR"
  && r.importacao.eventos.map((e) => e.id).join() === "SOL-2026-900001:imp:1:buscar,SOL-2026-900001:imp:1:entregar", r.importacao.pendencias.join(" | "));

// M-07 disponibilidade considera TODAS as tarefas ativas
const B1 = sol("SOL-2026-900002", "DOCUMENTOS_EM_ANDAMENTO", { documentos: docs("EM_ANDAMENTO", 30), reconhecimento: NA, importacao: NA });
r = operacao({ recentes: [B1, A4], foco: { sol: A4.sol, pendencias: [] } });
registrar("M-07 etapa concluída na SOL acompanhada não manda Documentos à copa se outra SOL o ocupa",
  r.documentos.local === "mesa" && r.documentos.status === "TRABALHANDO" && r.documentos.solicitacao === "SOL-2026-900002"
  && r.coordenador.status === "TRABALHANDO" && r.coordenador.pendencias.some((p) => p.startsWith("SOL-2026-900001")));

// M-08 aguardando decisão do Supervisor nunca aparece como "sem tarefa"
const A5 = sol("SOL-2026-900003", "AGUARDANDO_SUPERVISOR", { documentos: docs("CONCLUIDA", 1, 6), reconhecimento: { status: "PRONTO", fim: T(8) }, importacao: { status: "NAO_SOLICITADA" } });
r = operacao({ recentes: [A5], foco: { sol: A5.sol, pendencias: [] } });
registrar("M-08 campos reconhecidos aguardando o Supervisor: Importação mostra a espera, não \"sem tarefa\"",
  r.importacao.status === "LIVRE" && /aguardando conferência e encaminhamento do Supervisor/.test(r.importacao.tarefa)
  && r.coordenador.status === "AGUARDANDO_SUPERVISOR" && r.coordenador.solicitacao === A5.sol, r.importacao.tarefa);

// M-09 falha da etapa de Documentos
const A6 = sol("SOL-2026-900004", "AGUARDANDO_SUPERVISOR", { documentos: docs("FALHOU", 1, 3), reconhecimento: NA, importacao: NA });
r = operacao({ recentes: [A6], foco: null });
registrar("M-09 falha: Documentos ERRO permanece na mesa; Coordenador aguarda o Supervisor",
  r.documentos.status === "ERRO" && r.documentos.local === "mesa" && r.coordenador.status === "AGUARDANDO_SUPERVISOR"
  && r.importacao.tarefa.startsWith("Desativado — Importação VGROW"));

// M-10 empresa que não é VGROW não envolve a Importação
const C1 = sol("SOL-2026-900005", "PRONTO_PARA_FINANCEIRO", { documentos: docs("CONCLUIDA", 1, 2), reconhecimento: NA, importacao: NA });
r = operacao({ recentes: [C1], foco: { sol: C1.sol, pendencias: [] } });
const semFoco = operacao({ recentes: [C1], foco: null });
registrar("M-10 SOL de outra empresa: Importação sem eventos; Coordenador mostra o estado real da SOL acompanhada",
  r.importacao.eventos.length === 0 && r.importacao.status === "LIVRE" && r.coordenador.status === "CONCLUIDO"
  && /Pronto para o Financeiro/.test(r.coordenador.tarefa) && semFoco.coordenador.status === "CONCLUIDO"
  && /Pronto para o Financeiro/.test(semFoco.coordenador.tarefa), r.coordenador.tarefa);

// M-11 função pura: não altera a entrada e devolve sempre o mesmo resultado
const entrada = congelar({ recentes: [B1, A4, A6], foco: { sol: A4.sol, pendencias: ["x"] } });
let ok = true;
try {
  const a = JSON.stringify(operacao(entrada));
  const b = JSON.stringify(operacao(entrada));
  ok = a === b;
} catch (e) {
  ok = false;
}
registrar("M-11 função pura (entrada congelada intacta; mesma entrada, mesma saída)", ok);

// M-12 o detalhe defasado da SOL acompanhada não sobrepõe a lista geral (lida continuamente)
r = operacao({ recentes: [A4], foco: { sol: A4.sol, estado: "DOCUMENTOS_EM_ANDAMENTO", etapas: A1.etapas, pendencias: [] } });
registrar("M-12 estado mais recente prevalece sobre o detalhe antigo da SOL acompanhada",
  r.documentos.status === "CONCLUIDO" && r.importacao.status === "CONCLUIDO");

// M-13 eventos só descrevem o que aconteceu (identificadores únicos e horário real)
r = operacao({ recentes: [A4, A6, B1], foco: null });
const ids = r.documentos.eventos.map((e) => e.id);
registrar("M-13 eventos com identificador único e horário da etapa (sem horário → sem evento)",
  new Set(ids).size === ids.length && r.documentos.eventos.every((e) => e.em) && ids.length === 5, ids.join(" "));

// M-14/M-15 fluxo Financeiro → Contabilidade/Bancos
const FB = (fin, ban, estado) => sol("SOL-2026-900020", estado, { documentos: docs("CONCLUIDA", 1, 2), reconhecimento: NA, importacao: NA, financeiro: fin, bancos: ban });
r = operacao({ recentes: [FB({ status: "EM_ANDAMENTO", n: 1, inicio: T(3) }, { status: "NAO_EXECUTADA" }, "FINANCEIRO_EM_ANDAMENTO")], foco: null });
registrar("M-14 Financeiro conferindo: na mesa; Coordenador TRABALHANDO; Bancos disponível",
  r.financeiro.status === "TRABALHANDO" && r.financeiro.local === "mesa" && r.coordenador.status === "TRABALHANDO"
  && /Financeiro/.test(r.coordenador.tarefa) && r.bancos.status === "LIVRE" && r.bancos.local === "copa");
r = operacao({ recentes: [FB({ status: "CONCLUIDA", n: 1, inicio: T(3), fim: T(4), resumo: { movimentos: 13, sem_suporte: 3, ambiguos: 2 } },
  { status: "CONCLUIDA", n: 1, inicio: T(4), fim: T(5), resumo: { propostos: 6, incompletos: 6 } }, "AGUARDANDO_SUPERVISOR")], foco: { sol: "SOL-2026-900020", pendencias: [] } });
registrar("M-15 Financeiro e Bancos permanecem na mesa até conclusão da SOL; Coordenador aguarda o Supervisor",
  r.financeiro.status === "CONCLUIDO" && r.financeiro.local === "mesa" && r.financeiro.pendencias.length === 2
  && r.bancos.tarefa === "Concluído — proposta de lançamentos aguardando conferência" && r.bancos.pendencias.length === 1
  && r.coordenador.status === "AGUARDANDO_SUPERVISOR"
  && r.financeiro.eventos.map((e) => `${e.tipo}>${e.destino}`).join() === "entregar>bancos"
  && r.bancos.eventos.map((e) => `${e.tipo}>${e.destino}`).join() === "entregar>coordenador");

// M-16 passagem da pasta: Coordenador → Documentos → Financeiro → Bancos → Coordenador (uma entrega por etapa registrada)
r = operacao({ recentes: [FB({ status: "CONCLUIDA", n: 1, inicio: T(3), fim: T(4), resumo: {} }, { status: "CONCLUIDA", n: 1, inicio: T(4), fim: T(5), resumo: {} },
  "AGUARDANDO_SUPERVISOR")], foco: null });
registrar("M-16 passagem da pasta entre mesas conforme as etapas: Documentos→Financeiro, Financeiro→Bancos, Bancos→Coordenador; pasta no Coordenador",
  r.documentos.eventos.map((e) => `${e.tipo}>${e.destino}`).join() === "buscar>coordenador,entregar>financeiro"
  && r.financeiro.eventos.length === 1 && r.bancos.eventos.length === 1 && r.coordenador.pasta === true && !r.financeiro.pasta);
// M-17 bloqueio no Financeiro: nenhuma entrega ao Bancos; pasta parada no Financeiro com o motivo
r = operacao({ recentes: [FB({ status: "CONCLUIDA", n: 1, inicio: T(3), fim: T(4), bloqueado: true, resumo: {} }, { status: "NAO_EXECUTADA" }, "AGUARDANDO_SUPERVISOR")], foco: null });
registrar("M-17 lote bloqueado no Financeiro: não há entrega inventada; a pasta permanece no Financeiro com o motivo",
  r.financeiro.eventos.length === 0 && r.bancos.eventos.length === 0 && r.financeiro.pasta === true && r.financeiro.pasta_bloqueada
  && /bloqueado/.test(r.financeiro.pasta_motivo) && r.financeiro.status === "PENDENCIA");
// M-18 parada estrutural em Documentos (fluxo financeiro): sem entrega; pasta em Documentos
r = operacao({ recentes: [FB({ status: "NAO_EXECUTADA" }, { status: "NAO_EXECUTADA" }, "AGUARDANDO_SUPERVISOR")], foco: null });
registrar("M-18 Documentos parado por problema estrutural: Documentos não entrega a pasta; ela fica em Documentos",
  r.documentos.eventos.map((e) => e.tipo).join() === "buscar" && r.documentos.pasta && r.documentos.pasta_bloqueada);
// M-19 nova tentativa (decisão do Supervisor): o Financeiro busca a pasta no Coordenador
r = operacao({ recentes: [FB({ status: "EM_ANDAMENTO", n: 2, inicio: T(9) }, { status: "CONCLUIDA", n: 1, inicio: T(4), fim: T(5), resumo: {} }, "FINANCEIRO_EM_ANDAMENTO")], foco: null });
registrar("M-19 nova tentativa: Financeiro busca a pasta no Coordenador; pasta no Financeiro durante a conferência",
  r.financeiro.eventos.map((e) => `${e.tipo}>${e.destino}`).join() === "buscar>coordenador" && r.financeiro.pasta && r.financeiro.status === "TRABALHANDO");
// M-20 fluxo Documentos: entrega ao Coordenador como antes
r = operacao({ recentes: [C1], foco: null });
registrar("M-20 fluxo só de Documentos: Documentos entrega a pasta ao Coordenador",
  r.documentos.eventos.map((e) => `${e.tipo}>${e.destino}`).join() === "buscar>coordenador,entregar>coordenador" && r.coordenador.pasta);

// Fiscal documental e o mesmo personagem da Contabilidade, sem atividade futura inventada.
const F1=sol('SOL-2026-900090','FISCAL_EM_ANDAMENTO',{documentos:docs('CONCLUIDA',1,2),fiscal:{status:'EM_ANDAMENTO',n:1,inicio:T(2)},contabilfiscal:{status:'NAO_EXECUTADA'}});
r=operacao({recentes:[F1]});
registrar('M-21 Fiscal trabalha na própria mesa; Documentos entrega ao Fiscal',r.fiscal.status==='TRABALHANDO'&&r.fiscal.local==='mesa'&&r.coordenador.status==='TRABALHANDO'&&r.documentos.eventos.some(e=>e.destino==='fiscal')&&!r.documentos.eventos.some(e=>e.tipo==='entregar'&&e.destino==='coordenador'));
const F2=sol('SOL-2026-900090','CONTABILIDADE_FISCAL_EM_ANDAMENTO',{documentos:docs('CONCLUIDA',1,2),fiscal:{status:'CONCLUIDA',n:1,inicio:T(2),fim:T(3),resumo:{documentos:1,pendencias:0}},contabilfiscal:{status:'EM_ANDAMENTO',n:1,inicio:T(4)}});
r=operacao({recentes:[F2]});
registrar('M-22 Fiscal entrega à Contabilidade; permanece na mesa enquanto a SOL está aberta',r.fiscal.local==='mesa'&&r.fiscal.eventos.some(e=>e.destino==='bancos')&&r.bancos.status==='TRABALHANDO'&&r.bancos.local==='mesa');
const F3=JSON.parse(JSON.stringify(F2));F3.estado='AGUARDANDO_SUPERVISOR';Object.assign(F3.etapas.contabilfiscal,{status:'CONCLUIDA',fim:T(5),resumo:{propostos:1,incompletos:0}});
r=operacao({recentes:[F3]});
registrar('M-23 Contabilidade devolve ao Coordenador, Fiscal aguarda conferência na mesa',r.bancos.eventos.some(e=>e.tipo==='entregar'&&e.destino==='coordenador')&&r.fiscal.local==='mesa'&&r.bancos.local==='mesa'&&r.coordenador.status==='AGUARDANDO_SUPERVISOR');
const F4=JSON.parse(JSON.stringify(F3));F4.estado='ENCERRADA';r=operacao({recentes:[F4]});
registrar('M-24 revisão encerrada libera Fiscal e Contabilidade para a copa',r.fiscal.local==='copa'&&r.bancos.local==='copa');
r=operacao({recentes:[]});registrar('M-25 Fiscal não acionado fica livre na copa',r.fiscal.status==='LIVRE'&&r.fiscal.local==='copa'&&r.fiscal.eventos.length===0);

let falhas = 0;
resultados.forEach(([caso, ok, det]) => {
  if (!ok) falhas++;
  console.log(`${ok ? "OK   " : "FALHA"} ${caso}${det ? " — " + det : ""}`);
});
console.log(`\nMapeamento: ${resultados.length - falhas}/${resultados.length}`);
process.exit(falhas ? 1 : 0);
