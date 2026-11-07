/*
 * Fechamento APROVADO (SIMULAÇÃO) no mapeamento do escritório: estado fechado, participantes liberados (copa), rótulo
 * "Fechamento aprovado (SIMULAÇÃO)" e nunca "escriturado"/"liberado" como afirmação. Revogação volta ao posto.
 * Somente dados fictícios em memória: não acessa a API, documentos, registros nem o runtime.
 *
 * Uso (a partir da raiz AGENTES-PRIME):  node TESTES/ESCRITORIO/testar_aprovacao_mapa.js
 */
"use strict";
const path = require("path");
const raiz = path.resolve(__dirname, "..", "..");
const { operacao } = require(path.join(raiz, "ESCRITORIO-VIRTUAL/js/mapa.js"));

const resultados = [];
const registrar = (caso, ok, detalhe = "") => resultados.push([caso, !!ok, detalhe]);
const T = (n) => new Date(1793470000000 + n * 1000).toISOString();
const NA = { status: "NAO_APLICAVEL" };
const PARTICIPANTES = ["documentos", "financeiro", "dp", "fiscal", "bancos", "conciliacao"];
const fim = (i, resumo) => ({ status: "CONCLUIDA", n: 1, inicio: T(i), fim: T(i + 1), resumo });
// percurso completo fictício, tudo conferido
const ETAPAS = { documentos: { status: "CONCLUIDA", inicio: T(1), fim: T(2) }, reconhecimento: NA, importacao: NA,
  financeiro: fim(2, { movimentos: 6, sem_suporte: 0 }), dp: fim(3, { documentos: 3, pendencias: 0 }), fiscal: fim(4, { documentos: 2, pendencias: 0 }),
  bancos: fim(5, { propostos: 6, incompletos: 0 }), contabdp: fim(6, { propostos: 7, incompletos: 0 }), contabilfiscal: fim(7, { propostos: 4, incompletos: 0 }),
  conciliacao: fim(8, { conferido: 78, divergente: 0, pendente: 0, nao_aplicavel: 2, total: 80 }) };
const sol = (id, estado) => ({ sol: id, empresa: "EMPRESA-FICTICIA", competencia: "2026-10", estado, etapas: ETAPAS });
// afirmação de escrituração/liberação: toda menção precisa ser negada ("nada … escriturado nem liberado", "não … liberado")
const NEGADAS = /(nada|não|nem)( foi| é)? (escriturad[oa]s?|liberad[oa]s?)( nem (escriturad[oa]s?|liberad[oa]s?))?/gi;
const afirma = (x) => /escriturad|liberad/i.test(String(x).replace(NEGADAS, ""));

let r = operacao({ recentes: [sol("SOL-2026-930001", "FECHAMENTO_APROVADO")], foco: null });
registrar("AP-01 FECHAMENTO_APROVADO: Coordenador mostra \"Fechamento aprovado (SIMULAÇÃO)\" e que nada foi escriturado nem liberado",
  /Fechamento aprovado \(SIMULAÇÃO\)/.test(r.coordenador.tarefa) && /nada escriturado; TXT do Domínio só para importação manual/.test(r.coordenador.tarefa)
  && r.coordenador.status === "CONCLUIDO" && r.coordenador.pendencias.length === 0, `${r.coordenador.status} · ${r.coordenador.tarefa}`);
registrar("AP-02 estado fechado: participantes liberados (copa), ninguém preso ao posto nem trabalhando",
  PARTICIPANTES.every((k) => r[k].local === "copa" && r[k].status !== "TRABALHANDO"),
  PARTICIPANTES.map((k) => `${k}=${r[k].status}/${r[k].local}`).join(" "));
registrar("AP-03 disponibilidade cita o fechamento aprovado em SIMULAÇÃO; nenhum texto afirma escrituração ou liberação",
  PARTICIPANTES.every((k) => /fechamento aprovado em SIMULAÇÃO/.test(r[k].disponibilidade || ""))
  && Object.values(r).every((e) => ![e.tarefa, e.mensagem].some((x) => x && afirma(x))),
  PARTICIPANTES.map((k) => r[k].disponibilidade).join(" | "));
// mesma SOL aguardando o Supervisor: participantes permanecem no posto (regra anterior preservada)
r = operacao({ recentes: [sol("SOL-2026-930001", "AGUARDANDO_SUPERVISOR")], foco: null });
registrar("AP-04 revogada (volta a AGUARDANDO_SUPERVISOR): participantes voltam a permanecer na mesa até a conclusão",
  PARTICIPANTES.every((k) => r[k].local === "mesa") && r.coordenador.status === "AGUARDANDO_SUPERVISOR",
  PARTICIPANTES.map((k) => `${k}=${r[k].local}`).join(" "));
// outra SOL aberta continua prendendo quem participa dela; a aprovada não prende ninguém
const outra = Object.assign(sol("SOL-2026-930002", "AGUARDANDO_SUPERVISOR"), { etapas: Object.assign({}, ETAPAS, { dp: NA, contabdp: NA, fiscal: NA, contabilfiscal: NA, conciliacao: NA }) });
r = operacao({ recentes: [sol("SOL-2026-930001", "FECHAMENTO_APROVADO"), outra], foco: null });
registrar("AP-05 com outra SOL aberta: só quem participa da aberta fica na mesa; DP/Fiscal/Conciliação (só da aprovada) na copa",
  r.financeiro.local === "mesa" && r.bancos.local === "mesa" && ["dp", "fiscal", "conciliacao"].every((k) => r[k].local === "copa"),
  ["financeiro", "bancos", "dp", "fiscal", "conciliacao"].map((k) => `${k}=${r[k].local}`).join(" "));

let falhas = 0;
for (const [caso, ok, det] of resultados) {
  falhas += !ok;
  console.log(`${ok ? "PASS" : "FAIL"}  ${caso}${!ok && det ? `  — ${det}` : ""}`);
}
console.log(`\nAprovação (mapa): ${resultados.length - falhas}/${resultados.length}`);
process.exit(falhas ? 1 : 0);
