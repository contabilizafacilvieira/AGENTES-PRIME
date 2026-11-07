/*
 * Bateria dos defeitos da auditoria da interface (mapeamento, caminhada e dados simulados).
 * Somente dados fictícios em memória: não acessa a API, documentos, registros nem o runtime.
 *
 * Uso (a partir da raiz AGENTES-PRIME):  node TESTES/ESCRITORIO/testar_auditoria_mapa.js
 */
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const raiz = path.resolve(__dirname, "..", "..");
const { operacao } = require(path.join(raiz, "ESCRITORIO-VIRTUAL/js/mapa.js"));
const sandbox = { window: {}, console };
vm.runInNewContext(fs.readFileSync(path.join(raiz, "ESCRITORIO-VIRTUAL/js/cena.js"), "utf8"), sandbox);
const I = sandbox.window.EV.cena._interno;

const resultados = [];
const registrar = (caso, ok, detalhe = "") => resultados.push([caso, !!ok, detalhe]);
const T = (n) => new Date(1793470000000 + n * 1000).toISOString();
const NA = { status: "NAO_APLICAVEL" };
const AGENTES = ["coordenador", "documentos", "financeiro", "fiscal", "bancos", "importacao"];
const sol = (id, estado, etapas, extra = {}) => Object.assign({ sol: id, empresa: "EMPRESA-FICTICIA", competencia: "2026-09", estado, etapas }, extra);
const resumoDe = (r) => AGENTES.map((k) => `${k}=${r[k].status}/${r[k].local}`).join(" ");

// fluxo Financeiro → Bancos com pendências históricas (3 sem suporte, 5 incompletos)
const FB = { documentos: { status: "CONCLUIDA", inicio: T(1), fim: T(2) }, reconhecimento: NA, importacao: NA,
  financeiro: { status: "CONCLUIDA", n: 1, inicio: T(2), fim: T(3), resumo: { movimentos: 10, sem_suporte: 3 } },
  bancos: { status: "CONCLUIDA", n: 1, inicio: T(3), fim: T(4), resumo: { propostos: 2, incompletos: 5 } }, fiscal: NA, contabilfiscal: NA };

// ---------------- Item 1: ENCERRADA e CANCELADA não aparecem como fechamento concluído
let r = operacao({ recentes: [sol("SOL-2026-910001", "ENCERRADA", FB)] });
registrar("AU-01 ENCERRADA: nenhum personagem com ✓ Concluído (revisão parcial não é fechamento integral)",
  AGENTES.every((k) => r[k].status !== "CONCLUIDO"), resumoDe(r));
registrar("AU-02 ENCERRADA: Coordenador mostra \"Revisão parcial encerrada\" com as pendências históricas preservadas",
  /Revisão parcial encerrada/.test(r.coordenador.tarefa) && r.coordenador.pendencias.some((p) => /5 lançamentos incompletos/.test(p))
  && r.coordenador.pendencias.some((p) => /3 movimentos sem suporte/.test(p)), `${r.coordenador.tarefa} | ${JSON.stringify(r.coordenador.pendencias)}`);
registrar("AU-03 ENCERRADA: Bancos na copa preserva as pendências da etapa; disponibilidade separada do resultado (copa não comprova aprovação)",
  r.bancos.local === "copa" && r.bancos.pendencias.length > 0 && /não (indica|comprova)/.test(r.bancos.disponibilidade || "")
  && !/Concluído/.test(r.bancos.tarefa), `${r.bancos.status} · ${r.bancos.tarefa} · ${r.bancos.disponibilidade} · ${JSON.stringify(r.bancos.pendencias)}`);
r = operacao({ recentes: [sol("SOL-2026-910002", "CANCELADA", FB)] });
registrar("AU-04 CANCELADA: Coordenador mostra \"Cancelada\" e nenhum personagem aparece com ✓ Concluído",
  /Cancelada/.test(r.coordenador.tarefa) && AGENTES.every((k) => r[k].status !== "CONCLUIDO"), `${r.coordenador.tarefa} · ${resumoDe(r)}`);

// ---------------- Item 3: etapa fiscal não esconde a falha nem as pendências de Bancos
const MISTO = Object.assign({}, FB, {
  fiscal: { status: "CONCLUIDA", n: 1, inicio: T(2), fim: T(3), resumo: { documentos: 2, pendencias: 0 } },
  contabilfiscal: { status: "CONCLUIDA", n: 1, inicio: T(5), fim: T(6), resumo: { propostos: 1, incompletos: 0 } } });
r = operacao({ recentes: [sol("SOL-2026-910003", "AGUARDANDO_SUPERVISOR", Object.assign({}, MISTO, { bancos: { status: "FALHOU", n: 1, inicio: T(3) } }))] });
registrar("AU-05 SOL mista: Bancos FALHOU aparece como falha mesmo com Contabilidade/Fiscal concluída (as duas aparecem)",
  r.bancos.status === "ERRO" && /Bancos/.test(r.bancos.tarefa) && /Fiscal/.test(r.bancos.tarefa) && r.bancos.pasta && r.bancos.pasta_bloqueada,
  `${r.bancos.status} · ${r.bancos.tarefa} · pasta ${r.bancos.pasta}/${r.bancos.pasta_bloqueada}`);
r = operacao({ recentes: [sol("SOL-2026-910004", "AGUARDANDO_SUPERVISOR", MISTO)] });
registrar("AU-06 SOL mista: pendências de Bancos (5 incompletos) não somem quando a Contabilidade/Fiscal termina",
  r.bancos.pendencias.some((p) => /5 lançamentos incompletos/.test(p)), JSON.stringify(r.bancos.pendencias));

// ---------------- Item 5: textos de entrega seguem o fluxo (Financeiro/Fiscal → Contabilidade)
r = operacao({ recentes: [sol("SOL-2026-910005", "AGUARDANDO_SUPERVISOR", FB)] });
registrar("AU-07 Financeiro entrega à Contabilidade/Bancos (não ao Coordenador)",
  /Contabilidade/.test(r.financeiro.tarefa) && !/Coordenador/.test(r.financeiro.tarefa), r.financeiro.tarefa);
registrar("AU-08 Documentos no fluxo financeiro entrega ao Financeiro (mensagem coerente com a passagem da pasta)",
  /Financeiro/.test(r.documentos.mensagem || "") && !/entregue ao Coordenador/.test(r.documentos.mensagem || ""), r.documentos.mensagem);

// ---------------- Item 7b: Bancos termina depois da etapa fiscal (polling em três leituras)
function caminhar(snapshots) {
  let est = operacao({ recentes: [] });
  const app = { agentes: ["documentos", "financeiro", "fiscal", "bancos", "importacao"].map((id) => ({ id, implementado: true })), estadoDe: (id) => est[id] };
  const cam = I.criarCaminhada(app, I.grade(), false, 0);
  cam.sincronizar();
  const idsPorLeitura = [], visitas = [], quando = {};
  let ultimo = null, tempo = 0;
  for (const s of snapshots) {
    est = operacao({ recentes: [s] });
    idsPorLeitura.push(est.bancos.eventos.map((e) => e.id));
    est.bancos.eventos.forEach((e) => { quando[e.id] = e.em; });
    cam.sincronizar();
    for (const fim = tempo + 60000; tempo < fim; tempo += 100) {
      cam.avancar(100, tempo);
      const v = cam._corpos.bancos.visita;
      const id = v ? v.id : null;
      if (id && id !== ultimo) visitas.push(id);
      ultimo = id;
    }
  }
  return { idsPorLeitura, visitas, quando, est };
}
const doc = { status: "CONCLUIDA", inicio: T(1), fim: T(2) };
const fis = { status: "CONCLUIDA", n: 1, inicio: T(2), fim: T(3), resumo: { documentos: 1, pendencias: 0 } };
const fin = { status: "CONCLUIDA", n: 1, inicio: T(2), fim: T(4), resumo: { movimentos: 2 } };
const base = (cf, ban, estado) => sol("SOL-2026-910007", estado, { documentos: doc, reconhecimento: NA, importacao: NA, fiscal: fis, financeiro: fin, contabilfiscal: cf, bancos: ban });
const leituras = [
  base({ status: "EM_ANDAMENTO", n: 1, inicio: T(3) }, { status: "EM_ANDAMENTO", n: 1, inicio: T(4) }, "BANCOS_EM_ANDAMENTO"),
  base({ status: "CONCLUIDA", n: 1, inicio: T(3), fim: T(5), resumo: { propostos: 1, incompletos: 0 } }, { status: "EM_ANDAMENTO", n: 1, inicio: T(4) }, "BANCOS_EM_ANDAMENTO"),
  base({ status: "CONCLUIDA", n: 1, inicio: T(3), fim: T(5), resumo: { propostos: 1, incompletos: 0 } },
    { status: "CONCLUIDA", n: 1, inicio: T(4), fim: T(6), resumo: { propostos: 2, incompletos: 1 } }, "AGUARDANDO_SUPERVISOR")];
const c = caminhar(leituras);
const somem = c.idsPorLeitura.slice(1).flatMap((ids, k) => c.idsPorLeitura[k].filter((x) => !ids.includes(x)));
registrar("AU-09 SOL mista: eventos de Bancos já emitidos não somem quando a Contabilidade/Fiscal termina (ban:1 não vira ban:F1)",
  !somem.length && c.idsPorLeitura[2].some((x) => /:ban:1:entregar/.test(x)), `somem: ${somem.join(", ") || "nenhum"} · leituras: ${JSON.stringify(c.idsPorLeitura)}`);
const tempos = c.visitas.map((id) => Date.parse(c.quando[id] || 0));
registrar("AU-10 SOL mista: a animação de Bancos segue a ordem dos horários registrados",
  c.visitas.length >= 3 && tempos.every((t, k) => !k || t >= tempos[k - 1]), c.visitas.join(" → "));

// ---------------- Item 8: dados simulados respeitam as regras
const sb = {}; sb.window = sb;
vm.runInNewContext(fs.readFileSync(path.join(raiz, "ESCRITORIO-VIRTUAL/dados/estado-simulado.js"), "utf8"), sb);
const dados = sb.window.ESCRITORIO_DADOS || sb.ESCRITORIO_DADOS;
const FECHADAS = ["ENCERRADA", "CANCELADA"];
const problemas = [], semDeclaracao = [];
dados.cenarios.forEach((cen) => {
  // SOL do cenário: a declarada; sem declaração, inferida pelo Coordenador (em andamento, aguardando ou com pendência = aberta)
  const co = cen.estados.coordenador || {};
  const s = cen.solicitacao || (co.solicitacao && ["TRABALHANDO", "AGUARDANDO_SUPERVISOR", "PENDENCIA"].includes(co.status)
    ? { id: co.solicitacao, estado: "ABERTA (inferida)" } : null);
  Object.entries(cen.estados).forEach(([id, e]) => {
    const participa = s && e.solicitacao === s.id;
    if (participa && !FECHADAS.includes(s.estado) && e.local === "copa") problemas.push(`${cen.id}: ${id} na copa com ${s.id} aberta (${s.estado})`);
    if (participa && FECHADAS.includes(s.estado) && e.status === "CONCLUIDO") problemas.push(`${cen.id}: ${id} com ✓ Concluído em ${s.id} ${s.estado}`);
    if (e.status === "CONCLUIDO" && /confirmad|pendente/i.test(`${e.mensagem || ""} ${e.tarefa || ""}`) && !/aguardando conferência/i.test(e.tarefa || ""))
      problemas.push(`${cen.id}: ${id} com ✓ Concluído e pendências citadas`);
  });
  const ativos = Object.values(cen.estados).some((e) => e.solicitacao && e.status !== "OFFLINE");
  if (ativos && !cen.solicitacao) semDeclaracao.push(cen.id);
});
registrar("AU-11 dados simulados: participantes de SOL aberta ficam na mesa; SOL encerrada não aparece como ✓ Concluído com pendências",
  !problemas.length, problemas.join(" | "));
registrar("AU-12 dados simulados: cada cenário com SOL declara { id, estado } (aberta, encerrada ou cancelada)", !semDeclaracao.length, semDeclaracao.join(", "));

let falhas = 0;
resultados.forEach(([caso, ok, det]) => { if (!ok) falhas++; console.log(`${ok ? "OK   " : "FALHA"} ${caso}${det ? " — " + det : ""}`); });
console.log(`\nAuditoria (mapa/caminhada/dados): ${resultados.length - falhas}/${resultados.length}`);
process.exit(falhas ? 1 : 0);
