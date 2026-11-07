'use strict';
const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path');
const raiz=path.resolve(__dirname,'../..');
const {operacao}=require(path.join(raiz,'ESCRITORIO-VIRTUAL/js/mapa.js'));
const sandbox={window:{},console};vm.runInNewContext(fs.readFileSync(path.join(raiz,'ESCRITORIO-VIRTUAL/js/cena.js'),'utf8'),sandbox);
const I=sandbox.window.EV.cena._interno;
const t=n=>new Date(1793470000000+n*1000).toISOString();
const s={sol:'SOL-2026-999999',empresa:'FICTICIA',competencia:'2026-09',estado:'AGUARDANDO_SUPERVISOR',etapas:{
 documentos:{status:'CONCLUIDA',inicio:t(1),fim:t(2)},financeiro:{status:'CONCLUIDA',n:1,inicio:t(2),fim:t(3)},
 bancos:{status:'CONCLUIDA',n:1,inicio:t(3),fim:t(4),resumo:{}},importacao:{status:'NAO_APLICAVEL'}}};
let estados=operacao({recentes:[]});
const app={agentes:['documentos','financeiro','bancos','importacao'].map(id=>({id,implementado:true})),estadoDe:id=>estados[id]};
const cam=I.criarCaminhada(app,I.grade(),false,0);cam.sincronizar();
estados=operacao({recentes:[s]});cam.sincronizar();
for(const id of ['documentos','financeiro','bancos'])assert.equal(estados[id].local,'mesa',id+' não pode descansar em SOL pendente');
assert.equal(estados.importacao.local,'copa','não acionado permanece na copa');
let visitas={},primeiroTrabalho={},ultimaEntrega={};
for(let tempo=0;tempo<160000;tempo+=100){
 cam.avancar(100,tempo);
 for(const id of ['documentos','financeiro','bancos']){
  const c=cam._corpos[id];
  if(cam.corpo(id).pose==='mesa' && c.visita?.tipo==='trabalhar')primeiroTrabalho[id]??=tempo;
  if(c.visita?.tipo==='entregar') {visitas[id]=c.visita.destino;ultimaEntrega[id]=tempo;}
 }
 if(tempo%1000===0)cam.sincronizar(); // polling não deve reiniciar percursos nem apagar a fila
}
for(const id of ['documentos','financeiro','bancos']){
 assert.ok(primeiroTrabalho[id]!==undefined,id+' deve passar pela própria mesa mesmo se toda a etapa já terminou');
 assert.equal(cam.corpo(id).pose,'mesa',id+' volta à própria mesa enquanto aguarda a conclusão global');
}
assert.deepEqual(visitas,{documentos:'financeiro',financeiro:'bancos',bancos:'coordenador'});
assert.ok(primeiroTrabalho.financeiro>=ultimaEntrega.documentos);
assert.ok(primeiroTrabalho.bancos>=ultimaEntrega.financeiro);
const antes=JSON.stringify(cam._corpos);cam.sincronizar();assert.equal(JSON.stringify(cam._corpos),antes,'mesmos eventos não repetem');
const recarga=I.criarCaminhada(app,I.grade(),false,Date.parse(t(100)));recarga.sincronizar();
for(const id of ['documentos','financeiro','bancos'])assert.equal(recarga.corpo(id).pose,'mesa','recarga posiciona no estado real sem replay');
estados=operacao({recentes:[]});const apiTardia=I.criarCaminhada(app,I.grade(),false,Date.parse(t(100)));apiTardia.sincronizar();
estados=operacao({recentes:[s]});apiTardia.sincronizar();
for(const id of ['documentos','financeiro','bancos']){
 assert.equal(apiTardia.corpo(id).pose,'mesa','primeiro GET histórico posiciona diretamente na mesa');
 assert.equal(apiTardia._corpos[id].caminho.length,0);
}
estados=operacao({recentes:[{...s,estado:'CONCLUIDA'}]});cam.sincronizar();
for(let tempo=160000;tempo<210000;tempo+=100)cam.avancar(100,tempo);
for(const id of ['documentos','financeiro','bancos'])assert.equal(cam.corpo(id).pose,'sentado','somente conclusão global libera a copa');
estados=operacao({recentes:[s]});const reduzido=I.criarCaminhada(app,I.grade(),true,0);reduzido.sincronizar();
for(const id of ['documentos','financeiro','bancos'])assert.equal(reduzido.corpo(id).pose,'mesa');
const outra={...s,sol:'SOL-2026-999998'};estados=operacao({recentes:[{...s,estado:'CONCLUIDA'},outra]});
for(const id of ['documentos','financeiro','bancos'])assert.equal(estados[id].local,'mesa','outra SOL pendente mantém ocupação');
// Financeiro pode ter mais tentativas do que Bancos após uma falha.
estados=operacao({recentes:[]});const tentativa=I.criarCaminhada(app,I.grade(),false,0);tentativa.sincronizar();
const revisao={...s,etapas:{...s.etapas,financeiro:{...s.etapas.financeiro,n:3},bancos:{...s.etapas.bancos,n:2}}};
estados=operacao({recentes:[revisao]});tentativa.sincronizar();
for(let tempo=0;tempo<160000;tempo+=100)tentativa.avancar(100,tempo);
for(const id of ['documentos','financeiro','bancos']){
 assert.equal(tentativa._corpos[id].fila.length,0,'numerações independentes não travam a entrega para '+id);
 assert.equal(tentativa.corpo(id).pose,'mesa');
}
console.log('PASS: todos passam pela mesa; entregas ordenadas; mantidos no posto até conclusão global; não acionados na copa; recarga, polling, múltiplas SOLs e movimento reduzido.');
