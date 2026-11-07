/*
 * Percurso completo no Escritório (mapeamento + caminhada): DP e Conciliação como agentes implementados.
 * Documentos → Financeiro/DP/Fiscal → Contabilidade (Bancos, DP, Fiscal) → Conciliação → Coordenador.
 * Somente dados fictícios em memória: não acessa a API, documentos, registros nem o runtime.
 *
 * Uso (a partir da raiz AGENTES-PRIME):  node TESTES/ESCRITORIO/testar_percurso_mapa.js
 */
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const raiz = path.resolve(__dirname, "..", "..");
const { operacao: mapear } = require(path.join(raiz, "ESCRITORIO-VIRTUAL/js/mapa.js"));
// ausência de um personagem no mapeamento vira falha do caso (não exceção)
const IDS = ["coordenador", "documentos", "financeiro", "dp", "fiscal", "bancos", "conciliacao", "importacao"];
const operacao = (e) => { const x = mapear(e); IDS.forEach((k) => { x[k] = Object.assign({ eventos: [], pendencias: [], tarefa: "", mensagem: "" }, x[k] || {}); }); return x; };
const pose = (cam, id) => (cam.corpo(id) || {}).pose;
const sandbox = { window: {}, console };
vm.runInNewContext(fs.readFileSync(path.join(raiz, "ESCRITORIO-VIRTUAL/js/cena.js"), "utf8"), sandbox);
const I = sandbox.window.EV.cena._interno;
const sb = {}; sb.window = sb;
vm.runInNewContext(fs.readFileSync(path.join(raiz, "ESCRITORIO-VIRTUAL/dados/estado-simulado.js"), "utf8"), sb);
const DADOS = sb.window.ESCRITORIO_DADOS || sb.ESCRITORIO_DADOS;

const resultados = [];
const registrar = (caso, ok, detalhe = "") => resultados.push([caso, !!ok, detalhe]);
const T = (n) => new Date(1793470000000 + n * 1000).toISOString();
const NA = { status: "NAO_APLICAVEL" };
const NE = { status: "NAO_EXECUTADA" };
const sol = (id, estado, etapas, extra = {}) => Object.assign({ sol: id, empresa: "AMOSTRA-COMPLETA-FICTICIA", competencia: "2026-10", estado, etapas }, extra);
const C = (i, f, resumo, n = 1) => ({ status: "CONCLUIDA", n, inicio: T(i), fim: T(f), resumo: resumo || {} });

// Percurso completo (sequência real do plano: Financeiro → DP → Fiscal → Bancos → Contabilidade/DP → Contabilidade/Fiscal → Conciliação)
function percurso(ate, conc = { conferido: 30, divergente: 0, pendente: 0, nao_aplicavel: 2, total: 32 }) {
  const ord = ["financeiro", "dp", "fiscal", "bancos", "contabdp", "contabilfiscal", "conciliacao"];
  const resumos = { financeiro: { movimentos: 6 }, dp: { documentos: 3, fatos: 7, pendencias: 0 }, fiscal: { documentos: 2, pendencias: 0 },
    bancos: { propostos: 6, incompletos: 0 }, contabdp: { propostos: 7, incompletos: 0 }, contabilfiscal: { propostos: 4, incompletos: 0 }, conciliacao: conc };
  const et = { documentos: C(1, 2), reconhecimento: NA, importacao: NA };
  ord.forEach((k, i) => {
    const pos = ord.indexOf(ate);
    et[k] = i < pos ? C(2 + i, 3 + i, resumos[k]) : i === pos ? { status: "EM_ANDAMENTO", n: 1, inicio: T(2 + i) } : NE;
  });
  if (ate === "fim") ord.forEach((k, i) => { et[k] = C(2 + i, 3 + i, resumos[k]); });
  const estado = ate === "fim" ? "AGUARDANDO_SUPERVISOR" : { contabdp: "CONTABILIDADE_DP", contabilfiscal: "CONTABILIDADE_FISCAL" }[ate] ? `${{ contabdp: "CONTABILIDADE_DP", contabilfiscal: "CONTABILIDADE_FISCAL" }[ate]}_EM_ANDAMENTO` : `${ate.toUpperCase()}_EM_ANDAMENTO`;
  return sol("SOL-2026-920001", estado, et);
}

// ---------------- dados: DP e Conciliação implementados
const ag = (id) => DADOS.agentes.find((a) => a.id === id) || {};
registrar("PC-01 dados: DP e Conciliação são agentes IMPLEMENTADOS (não \"Em breve\")", ag("dp").implementado === true && ag("conciliacao").implementado === true,
  `dp ${ag("dp").implementado} · conciliacao ${ag("conciliacao").implementado}`);
registrar("PC-02 cena: DP e Conciliação caminham, têm ponto de entrega e placas sem \"em breve\"",
  !!(I.POSTOS.dp.caminha && I.POSTOS.conciliacao.caminha && I.ENTREGA.dp && I.ENTREGA.conciliacao),
  JSON.stringify({ dp: I.POSTOS.dp.caminha, conc: I.POSTOS.conciliacao.caminha, entrega: Object.keys(I.ENTREGA) }));

// ---------------- mapeamento
let r = operacao({ recentes: [percurso("dp")] });
registrar("PC-03 DP em andamento: DP TRABALHANDO na mesa; Coordenador TRABALHANDO acompanhando o DP; Conciliação (não acionada) na copa",
  r.dp && r.dp.status === "TRABALHANDO" && r.dp.local === "mesa" && r.coordenador.status === "TRABALHANDO" && /DP/.test(r.coordenador.tarefa)
  && r.conciliacao && r.conciliacao.local === "copa" && r.financeiro.local === "mesa", JSON.stringify({ dp: r.dp, c: r.coordenador.tarefa, conc: r.conciliacao && r.conciliacao.local }));
registrar("PC-04 Documentos entrega a pasta ao DP (evento real no fim de Documentos); DP trabalha no início da etapa",
  r.documentos.eventos.some((e) => e.tipo === "entregar" && e.destino === "dp" && e.em === T(2))
  && (r.dp.eventos || []).some((e) => e.tipo === "trabalhar" && e.destino === "dp" && e.em === T(3)), JSON.stringify([r.documentos.eventos, r.dp.eventos]));
r = operacao({ recentes: [percurso("contabdp")] });
registrar("PC-05 Contabilidade/DP em andamento: personagem da Contabilidade trabalha; DP entregou à Contabilidade; pasta na Contabilidade",
  r.bancos.status === "TRABALHANDO" && /DP/.test(r.bancos.tarefa) && r.dp.eventos.some((e) => e.tipo === "entregar" && e.destino === "bancos")
  && r.bancos.pasta && r.dp.local === "mesa", `${r.bancos.tarefa} · ${JSON.stringify(r.dp.eventos)}`);
r = operacao({ recentes: [percurso("conciliacao")] });
registrar("PC-06 Conciliação em andamento: TRABALHANDO na mesa com a pasta; Contabilidade entregou à Conciliação no início dela",
  r.conciliacao.status === "TRABALHANDO" && r.conciliacao.local === "mesa" && r.conciliacao.pasta
  && r.bancos.eventos.some((e) => e.tipo === "entregar" && e.destino === "conciliacao" && e.em === T(8))
  && !r.bancos.eventos.some((e) => e.tipo === "entregar" && e.destino === "coordenador") && /Concilia/.test(r.coordenador.tarefa),
  JSON.stringify({ c: r.conciliacao.status, ev: r.bancos.eventos, coord: r.coordenador.tarefa }));
r = operacao({ recentes: [percurso("fim")] });
registrar("PC-07 fim: Conciliação entrega ao Coordenador; todos os acionados permanecem na mesa (SOL aberta); pasta no Coordenador",
  r.conciliacao.eventos.some((e) => e.tipo === "entregar" && e.destino === "coordenador" && e.em === T(9))
  && ["documentos", "financeiro", "dp", "fiscal", "bancos", "conciliacao"].every((k) => r[k].local === "mesa") && r.coordenador.pasta
  && r.importacao.local === "copa", JSON.stringify(Object.fromEntries(Object.entries(r).map(([k, v]) => [k, v.local]))));
registrar("PC-08 conciliação toda CONFERIDA: Conciliação não aparece como aprovação; mensagem cita SIMULAÇÃO e alcance",
  r.conciliacao.status !== "AGUARDANDO_SUPERVISOR" && /SIMULAÇÃO/.test(r.conciliacao.mensagem || "") && /alcance/i.test(r.conciliacao.mensagem || "")
  && !/aprovad[oa](?! )|fechamento concluído/i.test(r.conciliacao.tarefa), `${r.conciliacao.status} · ${r.conciliacao.tarefa} · ${r.conciliacao.mensagem}`);
r = operacao({ recentes: [percurso("fim", { conferido: 20, divergente: 2, pendente: 3, nao_aplicavel: 1, total: 26 })] });
registrar("PC-09 conciliação com divergências/pendências: status PENDÊNCIA (nunca ✓) e pendências citadas na Conciliação e no Coordenador",
  r.conciliacao.status === "PENDENCIA" && r.conciliacao.pendencias.some((p) => /2 verificações divergentes/.test(p)) && r.conciliacao.pendencias.some((p) => /3 verificações pendentes/.test(p))
  && r.coordenador.pendencias.some((p) => /Concilia/.test(p)), JSON.stringify([r.conciliacao, r.coordenador.pendencias]));
const falhaDp = percurso("fim"); falhaDp.etapas.contabdp = { status: "FALHOU", n: 1, inicio: T(6) };
r = operacao({ recentes: [falhaDp] });
registrar("PC-10 Contabilidade/DP FALHOU: Contabilidade em ERRO com a falha visível (Bancos e Fiscal concluídos continuam listados)",
  r.bancos.status === "ERRO" && /DP/.test(r.bancos.tarefa) && /Bancos/.test(r.bancos.tarefa) && r.bancos.pendencias.some((p) => /DP.*falha/i.test(p)),
  `${r.bancos.tarefa} · ${JSON.stringify(r.bancos.pendencias)}`);
r = operacao({ recentes: [Object.assign(percurso("fim"), { estado: "ENCERRADA" })] });
registrar("PC-11 ENCERRADA: DP e Conciliação na copa sem ✓ Concluído; copa não indica aprovação",
  ["dp", "conciliacao"].every((k) => r[k].local === "copa" && r[k].status !== "CONCLUIDO" && /não indica aprovação/.test(r[k].disponibilidade || "")),
  JSON.stringify([r.dp, r.conciliacao].map((x) => [x.status, x.disponibilidade])));
r = operacao({ recentes: [] });
registrar("PC-12 sem solicitações: DP e Conciliação LIVRES na copa", r.dp && r.dp.local === "copa" && r.dp.status === "LIVRE" && r.conciliacao && r.conciliacao.local === "copa",
  JSON.stringify([r.dp, r.conciliacao]));

// ---------------- caminhada (fila visual) do percurso completo
function caminhada(leituras, reduzido = false, carregadoEm = 0) {
  let est = operacao({ recentes: [] });
  const ids = ["documentos", "financeiro", "dp", "fiscal", "bancos", "conciliacao", "importacao"];
  const app = { agentes: ids.map((id) => ({ id, implementado: true })), estadoDe: (id) => est[id] };
  const cam = I.criarCaminhada(app, I.grade(), reduzido, carregadoEm);
  cam.sincronizar();
  const visitas = {}, primeiroTrabalho = {}, entregasEm = {};
  let tempo = 0;
  for (const s of leituras) {
    est = operacao({ recentes: [s] });
    cam.sincronizar();
    for (const fim = tempo + 120000; tempo < fim; tempo += 100) {
      cam.avancar(100, tempo);
      for (const id of ids) {
        const c = cam._corpos[id];
        if (!c) continue;
        if (pose(cam, id) === "mesa" && c.visita && c.visita.tipo === "trabalhar" && primeiroTrabalho[id] === undefined) primeiroTrabalho[id] = tempo;
        if (c.visita && c.visita.tipo === "entregar") {
          (visitas[id] = visitas[id] || []);
          if (visitas[id][visitas[id].length - 1] !== c.visita.destino) visitas[id].push(c.visita.destino);
          entregasEm[`${id}>${c.visita.destino}`] = tempo;
        }
      }
      if (tempo % 1000 === 0) cam.sincronizar();
    }
  }
  return { cam, est, visitas, primeiroTrabalho, entregasEm };
}
const leituras = ["financeiro", "dp", "fiscal", "bancos", "contabdp", "contabilfiscal", "conciliacao", "fim"].map((k) => percurso(k));
const w = caminhada(leituras);
registrar("PC-13 caminhada: Documentos → Financeiro, DP, Fiscal; DP → Contabilidade; Contabilidade → Conciliação; Conciliação → Coordenador",
  JSON.stringify(w.visitas.documentos) === JSON.stringify(["financeiro", "dp", "fiscal"]) && (w.visitas.dp || []).join() === "bancos"
  && (w.visitas.bancos || []).join() === "conciliacao" && (w.visitas.conciliacao || []).join() === "coordenador", JSON.stringify(w.visitas));
registrar("PC-14 ordem: DP só trabalha depois da entrega de Documentos; Conciliação só depois da entrega da Contabilidade",
  w.primeiroTrabalho.dp >= w.entregasEm["documentos>dp"] && w.primeiroTrabalho.conciliacao >= w.entregasEm["bancos>conciliacao"],
  JSON.stringify({ trabalho: w.primeiroTrabalho, entregas: w.entregasEm }));
registrar("PC-15 após o percurso: acionados na própria mesa; Importação (não acionada) na copa",
  ["documentos", "financeiro", "dp", "fiscal", "bancos", "conciliacao"].every((id) => pose(w.cam, id) === "mesa") && ["assento", "copa-em-pe"].includes(((w.cam._corpos.importacao || {}).alvo || {}).tipo),
  JSON.stringify(Object.fromEntries(["dp", "conciliacao", "importacao"].map((id) => [id, pose(w.cam, id)]))));
const antes = JSON.stringify(w.cam._corpos); w.cam.sincronizar();
registrar("PC-16 mesma leitura de novo não repete eventos", JSON.stringify(w.cam._corpos) === antes);
const rec = caminhada([percurso("fim")], false, Date.parse(T(100)));
registrar("PC-17 recarga: eventos anteriores ao carregamento não são encenados; DP e Conciliação direto na mesa",
  !Object.keys(rec.visitas).length && pose(rec.cam, "dp") === "mesa" && pose(rec.cam, "conciliacao") === "mesa", JSON.stringify(rec.visitas));
const red = caminhada([percurso("conciliacao")], true);
registrar("PC-18 movimento reduzido: sem caminhada; DP e Conciliação direto na mesa",
  !Object.keys(red.visitas).length && pose(red.cam, "dp") === "mesa" && pose(red.cam, "conciliacao") === "mesa", JSON.stringify(red.visitas));
// Retomada da Contabilidade/DP: nova tentativa (D2) e nova Conciliação (C2) entregue de novo, sem repetir as anteriores
const retom = percurso("fim"); retom.etapas.contabdp = C(20, 21, { propostos: 7, incompletos: 0 }, 2); retom.etapas.conciliacao = C(22, 23, { conferido: 30, divergente: 0, pendente: 0, nao_aplicavel: 2, total: 32 }, 2);
r = operacao({ recentes: [retom] });
registrar("PC-19 retomada: nova tentativa da Contabilidade/DP e nova Conciliação geram eventos próprios (tentativa 2), com horário real",
  r.bancos.eventos.some((e) => /:ban:D2:trabalhar/.test(e.id) && e.em === T(20)) && r.bancos.eventos.some((e) => /:ban:C2:entregar:conciliacao/.test(e.id) && e.em === T(22))
  && r.conciliacao.eventos.some((e) => /:con:2:entregar:coordenador/.test(e.id)), JSON.stringify(r.bancos.eventos.map((e) => e.id)));
// Vigência e alcance só existem no detalhe da SOL acompanhada (foco): conciliação desatualizada ou parcial nunca aparece como ✓
const fim = percurso("fim");
r = operacao({ recentes: [fim], foco: { sol: fim.sol, pendencias: [], conciliacao_vigente: false } });
registrar("PC-20 Conciliação desatualizada (detalhe da SOL): PENDÊNCIA, nunca ✓; Coordenador cita a desatualização",
  r.conciliacao.status === "PENDENCIA" && r.conciliacao.pendencias.some((p) => /desatualizada/.test(p)) && r.coordenador.pendencias.some((p) => /desatualizada/.test(p)),
  JSON.stringify([r.conciliacao.status, r.conciliacao.pendencias, r.coordenador.pendencias]));
r = operacao({ recentes: [fim], foco: { sol: fim.sol, pendencias: [], conciliacao_parcial: true } });
registrar("PC-21 Conciliação com alcance parcial (detalhe da SOL): PENDÊNCIA, nunca ✓",
  r.conciliacao.status === "PENDENCIA" && r.conciliacao.pendencias.some((p) => /alcance parcial/.test(p)), JSON.stringify([r.conciliacao.status, r.conciliacao.pendencias]));

let falhas = 0;
resultados.forEach(([caso, ok, det]) => { if (!ok) falhas++; console.log(`${ok ? "OK   " : "FALHA"} ${caso}${det && !ok ? " — " + det.slice(0, 600) : ""}`); });
console.log(`\nPercurso completo (mapa/caminhada): ${resultados.length - falhas}/${resultados.length}`);
process.exit(falhas ? 1 : 0);
