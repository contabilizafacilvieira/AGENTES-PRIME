/* Gestão local; valores externos são exibidos somente como texto. */
(function () {
 'use strict';
 const meta=document.querySelector('meta[name="prime-sessao"]');
 if(!meta || !window.EV.operacao)return;
 const op=window.EV.operacao;
 document.body.classList.add('prime-gestao');
 new ResizeObserver(entries=>document.documentElement.style.setProperty('--prime-topo',Math.ceil(entries[0].target.getBoundingClientRect().height)+'px')).observe(document.querySelector('.topo'));
 function el(t,texto,classe){const e=document.createElement(t);if(texto!=null)e.textContent=texto;if(classe)e.className=classe;return e;}
 const area=el('section',null,'gestao'), aviso=el('p','','gestao-mensagem'), corpo=el('div',null,'gestao-conteudo');
 area.hidden=true;area.setAttribute('aria-label','Painel de gestão do escritório');
 const cabeca=el('div',null,'gestao-cabeca'),fechar=el('button','✕','fechar');fechar.type='button';fechar.setAttribute('aria-label','Recolher painel');fechar.addEventListener('click',()=>recolher());
 cabeca.append(el('span','Ferramentas do escritório'),fechar);
 aviso.setAttribute('role','status');area.append(cabeca,aviso,corpo);document.body.append(area);
 function erro(t){aviso.textContent=t;aviso.dataset.tipo='erro';aviso.scrollIntoView({block:'nearest'});}
 function informar(t){aviso.textContent=t;aviso.dataset.tipo='ok';}
 function botao(t,fn){const b=el('button',t,'gestao-botao');b.type='button';b.addEventListener('click',async()=>{b.disabled=true;try{await fn();}catch(e){erro(e.message);}finally{b.disabled=false;}});return b;}
 async function api(m,r,d){let resp;try{resp=await fetch('/api'+r,{method:m,cache:'no-store',headers:{'X-Prime-Sessao':meta.content,'Content-Type':'application/json'},body:d===undefined?undefined:JSON.stringify(d)});}catch(_){throw new Error('Não foi possível falar com o aplicativo. Confira se o servidor local está em execução e tente novamente.');}let a;try{a=await resp.json();}catch(_){throw new Error('O aplicativo respondeu de forma inesperada. Tente novamente; se persistir, avise o responsável técnico.');}if(!resp.ok)throw new Error(a.erro||'Não foi possível concluir.');return a;}
 function limpar(t,s){area.hidden=false;op.fechar();aviso.textContent='';delete aviso.dataset.tipo;corpo.replaceChildren(el('h1',t),el('p',s,'gestao-intro'));}
 function campo(p,t,tipo='text',v=''){const l=el('label',null,'gestao-campo'),i=el(tipo==='select'?'select':'input');if(i.tagName==='INPUT')i.type=tipo;i.value=v;l.append(el('span',t),i);p.append(l);return i;}
 function opcoes(s,a){a.forEach(([v,t])=>{const o=el('option',t);o.value=v;s.append(o);});}
 function detalhes(p,t,d){const x=el('details');x.append(el('summary',t),el('pre',JSON.stringify(d,null,2),'gestao-json'));p.append(x);return x;}
 const nav=el('nav',null,'gestao-nav');nav.setAttribute('aria-label','Navegação principal');
 document.body.append(nav);
 const estados={DOCUMENTOS_EM_ANDAMENTO:'Documentos em andamento',FISCAL_EM_ANDAMENTO:'Fiscal analisando',CONTABILIDADE_FISCAL_EM_ANDAMENTO:'Contabilidade preparando propostas fiscais',FINANCEIRO_EM_ANDAMENTO:'Financeiro conferindo',BANCOS_EM_ANDAMENTO:'Bancos preparando propostas',AGUARDANDO_SUPERVISOR:'Aguardando sua conferência',CANCELADA:'Cancelada',PRONTO_PARA_FINANCEIRO:'Documentos concluídos'};
 estados.ENCERRADA='Revisão parcial encerrada';
 Object.assign(estados,{DP_EM_ANDAMENTO:'DP analisando',CONTABILIDADE_DP_EM_ANDAMENTO:'Contabilidade preparando propostas do DP',CONCILIACAO_EM_ANDAMENTO:'Conciliação conferindo'});
 // aprovação do Supervisor em SIMULAÇÃO: estado fechado; nunca "escriturado" nem "liberado"
 estados.FECHAMENTO_APROVADO='Fechamento aprovado (SIMULAÇÃO)';
 const ESTADOS_FECHADOS=['FECHAMENTO_APROVADO','ENCERRADA','CANCELADA'];
 const fluxos={DOCUMENTOS:'Documentos',FINANCEIRO_BANCOS:'Financeiro / Bancos'};
 let pagina='',versao=0;
 function recolher(){versao++;area.hidden=true;op.fechar();pagina='';nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-current','false'));}
 async function navegar(t){
  if(pagina===t&&!area.hidden){recolher();return;}
  pagina=t;versao++;op.fechar();window.EV.app.fecharPainel();
  nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',b.dataset.pagina===t?'page':'false'));
  if(t==='escritorio'){recolher();return;}if(t==='empresas')return empresas();return consulta(t==='inicio');
 }
 [['inicio','Resumo','▦'],['solicitacoes','Solicitações','≡'],['empresas','Empresas','▣']].forEach(([id,t,icone])=>{const b=botao(t,()=>navegar(id));b.dataset.pagina=id;b.dataset.icone=icone;nav.append(b);});
 const nova=document.querySelector('.op-botao');nova.textContent='Nova solicitação';nova.dataset.icone='+';nova.title='Enviar novos documentos';nav.append(nova);
 nova.addEventListener('click',()=>{area.hidden=true;versao++;pagina='nova';window.EV.app.fecharPainel();nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',b===nova?'page':'false'));});
 const recolherBotao=botao('Recolher',recolher);recolherBotao.dataset.pagina='escritorio';recolherBotao.dataset.icone='‹';nav.append(recolherBotao);
 const sincronizarPainel=()=>{
  const aberto=!document.querySelector('.op-painel').hidden;
  if(aberto&&!area.hidden)area.hidden=true;
  document.body.classList.toggle('prime-painel-aberto',aberto||!area.hidden);
 };
 new MutationObserver(sincronizarPainel).observe(area,{attributes:true,attributeFilter:['hidden']});
 new MutationObserver(sincronizarPainel).observe(document.querySelector('.op-painel'),{attributes:true,attributeFilter:['hidden']});
 document.querySelector('.op-painel').setAttribute('role','region');
 document.addEventListener('keydown',e=>{if(e.key==='Escape')recolher();});
 window.EV.app.aoMudar(()=>{if(window.EV.app.painelAberto&&(!area.hidden||!document.querySelector('.op-painel').hidden))recolher();});
 window.addEventListener('prime-consulta',()=>navegar('solicitacoes'));
 window.addEventListener('prime-empresas',()=>navegar('empresas'));
 window.addEventListener('prime-empresa',e=>{
  pagina='empresas';versao++;op.fechar();window.EV.app.fecharPainel();
  nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',b.dataset.pagina==='empresas'?'page':'false'));
  const det=e.detail&&typeof e.detail==='object'?e.detail:{id:e.detail};
  abrirEmpresa(det.id,null,det.foco).catch(e=>erro(e.message));
 });
 function listar(lista,p){p.replaceChildren();if(!lista.length)p.append(el('p','Nenhuma solicitação neste filtro.'));lista.forEach(s=>{const a=el('article',null,'gestao-item'+(ESTADOS_FECHADOS.includes(s.estado)?' fechada':''));a.dataset.estado=s.estado;
   const proxima=s.estado==='FECHAMENTO_APROVADO'?'Consultar a aprovação, a situação do TXT e o histórico. Nada foi escriturado; o TXT (só empresa fictícia) é para importação manual no Domínio.':s.proxima_acao;
   a.append(el('h2',s.sol),el('p',`${s.empresa} · ${s.competencia} · ${fluxos[s.fluxo]||s.fluxo}`),el('strong',estados[s.estado]||s.estado,s.estado==='FECHAMENTO_APROVADO'?'gestao-aprovado':null),el('p',proxima),el('p',s.atualizado_em?'Atualizada em '+new Date(s.atualizado_em).toLocaleString('pt-BR'):'Sem horário registrado','gestao-nota'));
   if(!s.excluida)a.append(botao('Ver acompanhamento',()=>op.acompanhar(s.sol)));
   const b=botao(s.excluida?'Restaurar solicitação':'Excluir solicitação',async()=>{
    if(!window.confirm(s.excluida?`Restaurar ${s.sol} para a lista ativa?`:`Mover ${s.sol} para a lixeira? Documentos e regras serão preservados.`))return;
    await api(s.excluida?'POST':'DELETE','/solicitacoes/'+s.sol+(s.excluida?'/restaurar':''),{confirmado:true});op.atualizar();await consulta(false,s.excluida);
   });b.dataset.acao=s.excluida?'restaurar':'excluir';if(!s.excluida&&s.categoria==='processando')b.disabled=true;a.append(b);
   if(s.excluida){const area=el('div',null,'gestao-exclusao');area.dataset.exclusao=s.sol;
    const abrirEx=botao('Excluir definitivamente…',async()=>{await previaExclusao(s.sol,area);});abrirEx.dataset.acao='previa-exclusao';a.append(abrirEx,area);}
   p.append(a);});}
 // Exclusão DEFINITIVA (só da lixeira): prévia do servidor com impedimentos, consequências, o que é apagado e o que permanece; frase exata.
 async function previaExclusao(sol,area){
  const pv=await api('GET',`/solicitacoes/${sol}/exclusao-definitiva`);area.replaceChildren();
  const bloco=(t,itens,cls)=>{if(!itens||!itens.length)return;area.append(el('strong',t));const ul=el('ul',null,cls);itens.forEach(x=>ul.append(el('li',x)));area.append(ul);};
  area.append(el('p',pv.aviso,'gestao-nota'));
  bloco('Impedimentos (exclusão recusada):',pv.impedimentos,'gestao-impedimentos');bloco('Consequências:',pv.consequencias);
  bloco('Será apagado:',pv.sera_removido);bloco('Permanece (registro mínimo):',pv.permanece);
  if(!pv.permitida)return;
  const frase=campo(area,`Digite ${pv.frase}`);frase.setAttribute('aria-label',`Frase de exclusão definitiva de ${sol}`);
  const just=campo(area,'Justificativa (fica no registro mínimo)');just.setAttribute('aria-label',`Justificativa da exclusão de ${sol}`);
  const ok=botao('Confirmar exclusão definitiva',async()=>{const r=await api('POST',`/solicitacoes/${sol}/exclusao-definitiva`,{frase:frase.value,justificativa:just.value,confirmado:true});
   area.replaceChildren(el('p',r.mensagem,'gestao-nota'));op.atualizar();await consulta(false,true);});ok.dataset.acao='confirmar-exclusao';area.append(ok);
 }
 async function consulta(inicio,lixeira=false){
  limpar(lixeira?'Lixeira de solicitações':inicio?'Seu trabalho no escritório':'Consultar solicitações',lixeira?'Solicitações excluídas da lista ativa. Documentos, registros e regras continuam preservados. Restaure para retomar o acompanhamento.':inicio?'Veja o que está em andamento e o que precisa da sua atenção.':'Pesquise o histórico sem abrir um novo envio de documentos.');
  const v=versao,d=await api('GET','/solicitacoes'+(lixeira?'/lixeira':''));if(v!==versao)return;
  const alternar=botao(lixeira?'Voltar às solicitações':`Lixeira (${d.na_lixeira})`,()=>consulta(false,!lixeira));alternar.dataset.acao=lixeira?'ativas':'lixeira';corpo.append(alternar);
  if(!lixeira&&!inicio&&d.solicitacoes.length){const limparLista=botao('Limpar lista de solicitações',async()=>{
   if(!window.confirm(`Mover as ${d.solicitacoes.length} solicitações ativas para a lixeira? Você poderá restaurá-las. Documentos e regras serão preservados.`))return;
   await api('POST','/solicitacoes/limpar',{confirmado:true});op.atualizar();await consulta(false);
  });limparLista.dataset.acao='limpar-solicitacoes';corpo.append(limparLista);}
  const lista=el('div',null,'gestao-lista');
  if(inicio){const f=el('div',null,'gestao-filas');[['processando','Em processamento'],['decisoes','Decisões'],['documentos','Aguardando documentos'],['prontos','Propostas prontas'],['falhas','Falhas'],['historico','Histórico']].forEach(([k,t])=>f.append(botao(`${d.contagem[k]} · ${t}`,()=>listar(d.solicitacoes.filter(s=>s.categoria===k),lista))));corpo.append(f,el('p',d.criterio,'gestao-nota'));}
  const f=el('div',null,'gestao-filtros'),q=campo(f,'Número da SOL','search'),e=campo(f,'Empresa','select'),c=campo(f,'Competência','month'),a=campo(f,'Área','select'),s=campo(f,'Estado','select');
  opcoes(e,[['','Todas'],...[...new Set(d.solicitacoes.map(s=>s.empresa))].map(v=>[v,v])]);opcoes(a,[['','Todas'],...Object.entries(fluxos)]);opcoes(s,[['','Todos'],...[...new Set(d.solicitacoes.map(s=>s.estado))].map(v=>[v,estados[v]||v])]);
  const filtrar=()=>listar(d.solicitacoes.filter(r=>(!q.value||r.sol.includes(q.value.toUpperCase()))&&(!e.value||r.empresa===e.value)&&(!c.value||r.competencia===c.value)&&(!a.value||r.fluxo===a.value)&&(!s.value||r.estado===s.value)),lista);
  [q,e,c,a,s].forEach(i=>i.addEventListener('input',filtrar));corpo.append(f,lista,botao('Atualizar lista',()=>consulta(inicio,lixeira)));filtrar();
  if(lixeira&&(d.excluidas_definitivamente||[]).length){const x=el('details',null,'gestao-minimos');x.dataset.registrosMinimos='true';
   x.append(el('summary',`Excluídas definitivamente — registro mínimo (${d.excluidas_definitivamente.length})`));
   d.excluidas_definitivamente.forEach(m=>x.append(el('p',`${m.sol} · ${m.empresa} · ${m.competencia} · ${m.situacao_texto}${m.fatos_exportados?` · ${m.fatos_exportados} fato(s) exportado(s) mantidos para impedir duplicação`:''}${(m.remocao_pendente||[]).length?` · ATENÇÃO: ${m.remocao_pendente.length} item(ns) não apagados`:''}`)));
   corpo.append(x);}
 }
 // ================================================================ EMPRESAS (padrão: RESUMO → STATUS → PENDÊNCIAS → AÇÃO → DETALHES)
 // A complexidade fica no servidor; a tela mostra o resumo, a situação e UMA ação principal. Detalhes e opções avançadas sob demanda.
 const MESES=['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];
 function mes(comp){if(!comp||!/^\d{4}-\d{2}$/.test(comp))return comp||'';const [a,m]=comp.split('-');const n=MESES[+m-1];return n.charAt(0).toUpperCase()+n.slice(1)+'/'+a;}
 function competenciaPadrao(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;}
 const competenciaEmpresa={};
 function brl(v){if(v==null||v==='')return '—';const n=Number(v);return 'R$ '+Math.abs(n).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})+(n>0?' D':n<0?' C':'');}
 function fmtValor(v){if(v==null||v==='')return '—';const n=Number(v);return Math.abs(n).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})+(n>0?' D':n<0?' C':'');}
 // textos de negócio para códigos internos (o código fica em "Ver detalhes técnicos")
 const TXT_CONF={IGUAL_AO_BALANCETE:'Igual ao balancete',DIVERGENTE:'Diferente do balancete',SEM_CONTA_CORRESPONDENTE:'Conta não encontrada no balancete',SINAL_A_CONFIRMAR:'Mesmo valor com sinal invertido',NAO_DETERMINADA:'Não foi possível comparar'};
 const TXT_METODO={ITENS_EM_ABERTO:'Itens em aberto',HISTORICO_ACUMULADO:'Histórico acumulado',POSICAO_DE_RELATORIO:'Posição de relatório',HIBRIDO:'Híbrido',NAO_INFORMADO:'Não informado',DESCONHECIDO:'Não reconhecido'};
 const TXT_ABA={COMPOSICAO:'Composição',BALANCETE:'Balancete',PENDENCIAS:'Pendências',HISTORICO_BAIXAS:'Histórico de baixas',EVIDENCIAS:'Evidências',INDICE:'Índice',DESCONHECIDA:'Não identificada'};
 const NIVEL={BLOQUEIO:['⛔','Bloqueio','Precisa ser resolvido antes de confirmar.'],ATENCAO:['⚠','Atenção','Recomenda revisão; não impede seguir.'],INFORMATIVO:['ℹ','Informativo','Não impede seguir.']};
 const SITUACAO_EMPRESA={ATIVA:'Ativa',CADASTRO_PENDENTE:'Configuração pendente',EXCLUIDA:'Cadastro excluído'};
 const GRUPO_CONTABIL={ATIVO:'Ativo',PASSIVO:'Passivo',PATRIMONIO_LIQUIDO:'Patrimônio Líquido',RESULTADO:'Contas de Resultado',OUTROS:'Outros'};
 const GR={ATIVO:'Ativo',PASSIVO:'Passivo',PATRIMONIO_LIQUIDO:'Patrimônio Líquido',RECEITA:'Contas de Resultado · receita',CUSTO:'Contas de Resultado · custo',DESPESA:'Contas de Resultado · despesa',RESULTADO:'Contas de Resultado',OUTROS:'Outros'};
 const AJUDA_PLANO='Contas sintéticas e analíticas são identificadas automaticamente pela hierarquia da classificação contábil. O grupo contábil é herdado da estrutura principal do plano de contas. Você só precisa confirmar situações em que a estrutura não permite uma identificação segura. Contas sintéticas não exigem composição individual no book. A composição é analisada nas contas analíticas aplicáveis.';
 // resumo "Plano contábil": contas analisadas, classificadas automaticamente e que precisam de confirmação (só o ambíguo)
 function resumoPlano(p,a,revisar){if(!a)return;const box=el('div',null,'gestao-plano-resumo');box.dataset.resumoPlano='true';const tit=el('strong','Plano contábil');box.append(tit);ajuda(tit,AJUDA_PLANO);
  numeros(box,[[a.contas,'contas analisadas'],[a.classificadas_automaticamente,'classificadas automaticamente','ok'],[a.precisam_confirmacao,'precisam de confirmação',a.precisam_confirmacao?'atencao':'ok']]);
  if(a.precisam_confirmacao&&revisar){const b=secundario(`Revisar ${a.precisam_confirmacao} conta${a.precisam_confirmacao>1?'s':''}`,revisar);b.dataset.acao='revisar-contas-plano';box.append(b);}
  p.append(box);return box;}
 function chip(t,tipo){return el('span',t,'gestao-chip'+(tipo?' '+tipo:''));}
 function primario(t,fn){const b=botao(t,fn);b.classList.add('gestao-primario');return b;}
 function secundario(t,fn){const b=botao(t,fn);b.classList.add('gestao-link');return b;}
 function ajuda(p,texto){const w=el('span',null,'gestao-ajuda');const b=el('button','ⓘ','gestao-ajuda-botao');b.type='button';b.setAttribute('aria-label','Saiba mais');b.setAttribute('aria-expanded','false');b.title=texto;
  const s=el('span',texto,'gestao-ajuda-texto');s.hidden=true;b.addEventListener('click',()=>{s.hidden=!s.hidden;b.setAttribute('aria-expanded',String(!s.hidden));});w.append(b,s);p.append(w);return w;}
 function tecnico(p,dados){const d=el('details',null,'gestao-tecnico');d.append(el('summary','Ver detalhes técnicos'),el('pre',typeof dados==='string'?dados:JSON.stringify(dados,null,2),'gestao-json'));p.append(d);return d;}
 // menu de ações secundárias ("⋯")
 function menu(p,itens,rotulo='Mais opções'){
  const w=el('div',null,'gestao-menu');const b=el('button','⋯','gestao-botao gestao-menu-botao');b.type='button';b.setAttribute('aria-haspopup','true');b.setAttribute('aria-expanded','false');b.setAttribute('aria-label',rotulo);b.title=rotulo;
  const ul=el('ul',null,'gestao-menu-lista');ul.hidden=true;
  itens.forEach(([t,fn,perigo,acao])=>{const li=el('li');const x=el('button',t,perigo?'perigo':null);x.type='button';if(acao)x.dataset.acao=acao;x.addEventListener('click',async()=>{ul.hidden=true;b.setAttribute('aria-expanded','false');try{await fn();}catch(e){erro(e.message);}});li.append(x);ul.append(li);});
  b.addEventListener('click',ev=>{ev.stopPropagation();ul.hidden=!ul.hidden;b.setAttribute('aria-expanded',String(!ul.hidden));});
  document.addEventListener('click',ev=>{if(!w.contains(ev.target)){ul.hidden=true;b.setAttribute('aria-expanded','false');}});
  w.append(b,ul);p.append(w);return w;
 }
 function tabela(p,cab,linhas,limite=400){const w=el('div',null,'gestao-tabela');const tb=el('table');const th=el('tr');cab.forEach(c=>th.append(el('th',c)));tb.append(th);
  linhas.slice(0,limite).forEach(l=>{const tr=el('tr');l.forEach(c=>tr.append(el('td',c==null?'':String(c))));tb.append(tr);});w.append(tb);
  if(linhas.length>limite)w.append(el('p',`Exibidas ${limite} de ${linhas.length} linhas.`,'gestao-nota'));p.append(w);return w;}
 // tabela sob demanda com filtros simples (Todos / Pendentes / Divergentes / Conferidos)
 function tabelaFiltrada(p,rotulo,cab,linhas,filtros){
  const d=el('details',null,'gestao-sob-demanda');d.append(el('summary',`${rotulo} (${linhas.length})`));const barra=el('div',null,'gestao-filtro');const alvo=el('div');
  const mostrar=f=>{alvo.replaceChildren();tabela(alvo,cab,linhas.filter(l=>f[1](l)).map(l=>l.c),1000);barra.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.textContent.startsWith(f[0]))));};
  filtros.forEach(f=>{const b=el('button',`${f[0]} (${linhas.filter(l=>f[1](l)).length})`,'gestao-filtro-botao');b.type='button';b.addEventListener('click',()=>mostrar(f));barra.append(b);});
  d.append(barra,alvo);d.addEventListener('toggle',()=>{if(d.open&&!alvo.childNodes.length)mostrar(filtros[0]);},{once:false});p.append(d);return d;
 }
 function lista(p,titulo,itens){if(!itens||!itens.length)return;const d=el('details',null,'gestao-sob-demanda');d.append(el('summary',`${titulo} (${itens.length})`));const ul=el('ul');itens.slice(0,300).forEach(x=>ul.append(el('li',typeof x==='string'?x:JSON.stringify(x))));d.append(ul);p.append(d);return d;}

 // ---------------------------------------------------------------- lista de empresas
 async function empresas(){
  limpar('Empresas','Escolha a empresa para preparar a base inicial e acompanhar o trabalho do mês.');
  const comoFunciona=el('details',null,'gestao-como');comoFunciona.dataset.comoFunciona='true';comoFunciona.append(el('summary','Como funciona'));
  const passos=el('ol');['Escolha a empresa.','Abra a competência.','Prepare a base inicial.','Envie os documentos (Nova solicitação).','O Coordenador distribui o trabalho.','Confira somente o que precisa da sua atenção.'].forEach(t=>passos.append(el('li',t)));
  comoFunciona.append(passos);corpo.append(comoFunciona);
  const dados=await api('GET','/empresas');
  const listaEmp=el('div',null,'gestao-empresas');listaEmp.dataset.listaEmpresas='true';
  if(!dados.length){const vazio=el('div',null,'gestao-vazio');vazio.append(el('p','Nenhuma empresa cadastrada ainda.'),primario('Cadastrar empresa',()=>{admin.open=true;novo.open=true;novo.scrollIntoView({block:'center'});}));listaEmp.append(vazio);}
  dados.forEach(e=>{
   const c=el('article',null,'gestao-empresa');c.dataset.empresa=e.id;
   const topo=el('div',null,'gestao-empresa-topo');topo.append(el('h2',e.nome||e.id));
   const acoes=el('div',null,'gestao-empresa-acoes');const abrir=botao('Abrir',()=>abrirEmpresa(e.id));abrir.dataset.acao='abrir-empresa';acoes.append(abrir);
   menu(acoes,[['Configurações',()=>abrirEmpresa(e.id,null,'cadastro')],['Editar cadastro',()=>abrirEmpresa(e.id,null,'cadastro')],
               ['Histórico de solicitações',()=>historico(e.id)],['Excluir cadastro',()=>abrirEmpresa(e.id,null,'excluir'),true,'menu-excluir']],`Mais opções de ${e.nome||e.id}`);
   topo.append(acoes);c.append(topo);
   const linha=el('p',null,'gestao-empresa-linha');
   linha.append(chip(SITUACAO_EMPRESA[e.situacao]||'—',e.situacao==='ATIVA'?'ok':'atencao'),chip('Modo: Simulação'),
                chip(e.competencia_atual?`Competência atual: ${mes(e.competencia_atual)} · base ${e.situacao_base==='CONFIRMADA'?'confirmada':'em preparação'}`:'Base inicial não iniciada'));
   c.append(linha);listaEmp.append(c);
  });
  corpo.append(listaEmp);
  // administração (separada da operação)
  const admin=el('details',null,'gestao-admin');admin.dataset.maisOpcoes='true';admin.append(el('summary','Administração · Mais opções'));
  const novo=el('details');novo.dataset.cadastrarEmpresa='true';novo.open=dados.length===0;novo.append(el('summary','Cadastrar empresa'));
  const id=campo(novo,'Código da empresa (ex.: CLIENTE-ABC)'),nome=campo(novo,'Razão social'),cnpj=campo(novo,'CNPJ'),regime=campo(novo,'Regime tributário');
  ajuda(novo,'O código identifica a empresa no escritório e não pode ser reutilizado depois. O CNPJ é conferido pelos dígitos verificadores.');
  const criar=primario('Criar cadastro',async()=>{const r=await api('POST','/empresas',{id:id.value.trim().toUpperCase(),nome:nome.value,cnpj:cnpj.value,regime:regime.value});await abrirEmpresa(r.id);});criar.dataset.acao='criar-cadastro';novo.append(criar);
  const excluidas=el('details');excluidas.dataset.cadastrosExcluidos='true';excluidas.append(el('summary','Cadastros excluídos'));
  excluidas.addEventListener('toggle',async()=>{if(!excluidas.open||excluidas.dataset.carregado)return;excluidas.dataset.carregado='1';
   const todas=(await api('GET','/empresas?excluidas=1')).filter(x=>x.excluida);
   if(!todas.length){excluidas.append(el('p','Nenhum cadastro excluído.','gestao-nota'));return;}
   todas.forEach(x=>{const l=el('p',`${x.nome} (${x.id}) · excluído em ${new Date(x.excluida.em).toLocaleDateString('pt-BR')}`);l.append(' ',secundario('Ver histórico',()=>historico(x.id)));excluidas.append(l);});});
  if(dados.length===0)admin.open=true;
  admin.append(novo,excluidas,blocoAmostra());corpo.append(admin);
 }
 // histórico de solicitações da empresa (consulta com o filtro já aplicado)
 async function historico(id){await consulta(false);const s=corpo.querySelector('.gestao-filtros select');if(s){if(![...s.options].some(o=>o.value===id))opcoes(s,[[id,id]]);s.value=id;s.dispatchEvent(new Event('input'));}}

 // ---------------------------------------------------------------- empresa
 async function abrirEmpresa(id,comp,foco){
  const e=await api('GET','/empresas/'+id);
  limpar(e.nome||e.id,'');corpo.querySelector('.gestao-intro')?.remove();
  const voltar=secundario('‹ Empresas',empresas);voltar.dataset.acao='voltar-empresas';corpo.prepend(voltar);
  if(e.legado){corpo.append(el('p',e.aviso));return;}
  const cab=el('p',null,'gestao-empresa-linha');cab.append(chip(`CNPJ ${e.cnpj}`),chip(e.regime),chip(SITUACAO_EMPRESA[e.situacao]||'—',e.situacao==='ATIVA'?'ok':'atencao'),chip('Modo: Simulação'),chip(e.piloto?'Piloto habilitado':'Piloto bloqueado',e.piloto?'ok':'atencao'));corpo.append(cab);
  if(e.excluida){const x=el('div',null,'gestao-aviso-bloco');x.dataset.cadastroExcluido='true';
   x.append(el('strong','Cadastro excluído'),el('p',`Excluído em ${new Date(e.excluida.em).toLocaleString('pt-BR')}. A empresa não aceita novas solicitações. Documentos, solicitações e arquivos gerados continuam disponíveis.`),primario('Ver histórico de solicitações',()=>historico(id)));corpo.append(x);return;}
  comp=comp||competenciaEmpresa[id];
  const b=await api('GET',`/empresas/${id}/base-inicial`+(comp?`?competencia=${encodeURIComponent(comp)}`:''));
  comp=b.competencia||comp||competenciaPadrao();competenciaEmpresa[id]=comp;
  const recarregar=(f)=>abrirEmpresa(id,comp,f);
  // ---- OPERAÇÃO: resumo executivo da base inicial
  const res=el('section',null,'gestao-card gestao-base-resumo');res.dataset.baseResumo=comp;
  const titulo=el('div',null,'gestao-card-topo');titulo.append(el('h2',`Base inicial — ${mes(comp)}`));
  const trocar=secundario('Trocar competência',()=>{linhaComp.hidden=!linhaComp.hidden;});trocar.dataset.acao='trocar-competencia';titulo.append(trocar);res.append(titulo);
  const linhaComp=el('div',null,'gestao-linha');linhaComp.hidden=!!b.competencia;
  const cmp=campo(linhaComp,'Competência','month',comp);cmp.dataset.campo='competencia-base';ajuda(linhaComp,'Selecione o mês ao qual os documentos pertencem. A base usa o balancete de encerramento do mês anterior.');
  const abrirComp=botao('Abrir competência',async()=>{if(!/^\d{4}-\d{2}$/.test(cmp.value))throw new Error('Informe a competência no formato mês/ano.');await abrirEmpresa(id,cmp.value);});abrirComp.dataset.acao='abrir-competencia';linhaComp.append(abrirComp);res.append(linhaComp);
  const situ=b.situacao==='CONFIRMADA'?'Confirmada':b.situacao==='RASCUNHO'?'Em preparação':'Não iniciada';
  const st=el('p',null,'gestao-status');st.append('Status: ',el('strong',situ));st.dataset.situacaoBase=b.situacao||'NAO_INICIADA';res.append(st);
  const fases=b.fases||[];const fase=k=>fases.find(f=>f.fase===k)||{};const icone=s=>s==='CONCLUIDA'?'✓':s==='ATUAL'?'●':'○';
  const pr=b.pendencias_resumo||{};
  // contas patrimoniais analíticas com saldo sem composição no Book: contadas em CONTAS (Atenção), separadas das demais pendências
  const semComp=(b.definicoes||[]).find(x=>x.chave==='sem_composicao'&&!x.resolvida);const nComp=semComp?(semComp.quantidade||0):0;
  const nPend=(pr.BLOQUEIO||0)+(pr.ATENCAO||0)-(semComp?1:0);
  const ul=el('ul',null,'gestao-resumo-lista');
  [['balancete','Balancete anterior'],['book','Book anterior']].forEach(([k,t])=>{const s=fase(k).situacao;ul.append(el('li',`${icone(s)} ${t}: ${s==='CONCLUIDA'?'concluído':'pendente'}`,s==='CONCLUIDA'?'ok':''));});
  if(nPend||!nComp){const liP=el('li',nPend?`⚠ Pendências: ${nPend}`:'✓ Pendências: nenhuma',nPend?'atencao':'ok');liP.dataset.pendencias=String(nPend);ul.append(liP);}
  if(nComp){const liC=el('li',`⚠ ${nComp} conta${nComp>1?'s precisam':' precisa'} de conferência`,'atencao');liC.dataset.contasConferencia=String(nComp);ul.append(liC);}
  res.append(ul);
  const acoesRes=el('div',null,'gestao-acoes');
  const fluxo=el('section',null,'gestao-fluxo');fluxo.dataset.fluxoBase='true';fluxo.hidden=true;
  const abrirFluxo=(f)=>{fluxo.hidden=false;ver.textContent='Ocultar detalhes';acoesRes.querySelectorAll('.gestao-primario').forEach(x=>x.hidden=true);renderFluxo(fluxo,id,comp,b,e,recarregar,f);fluxo.scrollIntoView({block:'start'});};
  if(b.situacao==='CONFIRMADA'){const enviar=primario('Enviar documentos do mês',()=>{recolher();document.querySelector('.op-botao').click();});enviar.dataset.acao='enviar-documentos';acoesRes.append(enviar);}
  else{const cont=primario(b.situacao==='RASCUNHO'?'Continuar preparação':'Iniciar preparação',()=>abrirFluxo());cont.dataset.acao='continuar-base';acoesRes.append(cont);}
  const ver=secundario('Ver detalhes',()=>{if(fluxo.hidden)abrirFluxo();else{fluxo.hidden=true;ver.textContent='Ver detalhes';acoesRes.querySelectorAll('.gestao-primario').forEach(x=>x.hidden=false);}});ver.dataset.acao='ver-detalhes-base';acoesRes.append(ver);res.append(acoesRes);
  if(b.reanalise_disponivel){const ra=el('div',null,'gestao-reanalise');ra.dataset.reanalise='true';
   ra.append(el('p','A análise desta base foi feita por uma versão anterior do aplicativo. Reanalise para atualizar tipos, grupos e pendências.','gestao-nota'));
   const bt=botao('Reanalisar base',()=>reanalisarBase(id,comp));bt.dataset.acao='reanalisar-base';ra.append(bt);
   ra.append(el('p','Recalcula tipos, grupos e pendências usando os arquivos já enviados. Os arquivos originais não serão alterados.','gestao-nota'));res.append(ra);}
  if(nComp){const p=el('p',null,'gestao-pendencias-resumo');p.dataset.resumoSemComposicao=String(nComp);
   p.append('São contas patrimoniais analíticas com saldo, mas sem composição identificada no Book. ');
   const rv=secundario(`Revisar ${nComp} conta${nComp>1?'s':''}`,()=>{abrirFluxo('conferencia');const c=fluxo.querySelector('[data-definicao-base=sem_composicao]');if(c)c.scrollIntoView({block:'start'});});
   rv.dataset.acao='revisar-contas-book';p.append(rv);res.append(p);}
  if(nPend){const p=el('p',null,'gestao-pendencias-resumo');p.append(`${nPend} pendência${nPend>1?'s precisam':' precisa'} da sua atenção. `);const rv=secundario('Revisar pendências',()=>abrirFluxo('conferencia'));rv.dataset.acao='revisar-pendencias';p.append(rv);res.append(p);}
  corpo.append(res);
  corpo.append(fluxo);
  // regras das áreas a confirmar (configuração das áreas; fechadas, abertas só quando o usuário vem confirmar)
  const regras=definicoes(e,foco==='regras');corpo.append(regras);
  const nRegras=e.referencias_sugeridas||0;
  if(nRegras){const li=el('li',`${nRegras} referências sugeridas`,'gestao-nota');li.dataset.regrasSugeridas=String(nRegras);li.append(' ',secundario('Revisar referências',()=>{prepararReferencias(e);}));ul.append(li);}
  if(foco==='regras'&&nRegras)regras.scrollIntoView({block:'start'});
  if(foco==='base'||foco==='balancete'||foco==='book'||foco==='conferencia'||foco==='confirmacao')abrirFluxo(foco==='base'?null:foco);
  // ---- CONFIGURAÇÃO DA EMPRESA (administrativo, separado da operação)
  const cfg=el('section',null,'gestao-config');cfg.dataset.configEmpresa='true';cfg.append(el('h2','Configuração da empresa'));
  const abas=el('div',null,'gestao-config-abas');const painelCfg=el('div',null,'gestao-config-painel');
  const secoes={bancos:['Contas bancárias',()=>configBancos(painelCfg,e,recarregar)],cadastro:['Cadastro e piloto',()=>configCadastro(painelCfg,e,recarregar)],plano:['Plano contábil atual',()=>configPlano(painelCfg,e,b,recarregar)]};
  const mostrar=k=>{painelCfg.replaceChildren();abas.querySelectorAll('[data-config]').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.config===k)));if(secoes[k])secoes[k][1]();};
  Object.entries(secoes).forEach(([k,[t]])=>{const x=botao(t,()=>mostrar(painelCfg.dataset.aberto===k?(painelCfg.dataset.aberto='',null):(painelCfg.dataset.aberto=k)));x.dataset.config=k;x.setAttribute('aria-pressed','false');abas.append(x);});
  menu(abas,[['Histórico de solicitações',()=>historico(id)],['Detalhes técnicos do cadastro',()=>{painelCfg.replaceChildren();tecnico(painelCfg,{id:e.id,versao:e.versao,plano:e.plano.length+' contas',contas:e.contas}).open=true;}],
             ['Excluir cadastro',()=>exclusao(painelCfg,e),true,'excluir-cadastro']],'Mais opções da empresa');
  cfg.append(abas,painelCfg);corpo.append(cfg);
  if(foco==='bancos'||foco==='cadastro'||foco==='plano'){painelCfg.dataset.aberto=foco;mostrar(foco);cfg.scrollIntoView({block:'start'});}
  if(foco==='excluir'){exclusao(painelCfg,e);cfg.scrollIntoView({block:'start'});}
 }

 // ---------------------------------------------------------------- fluxo da base inicial em 4 fases (só a fase ativa em destaque)
 function renderFluxo(p,id,comp,b,e,recarregar,escolhida){
  p.replaceChildren();const fases=b.fases||[];
  const ativa=escolhida||(fases.find(f=>f.situacao==='ATUAL')||fases[fases.length-1]||{}).fase||'balancete';
  const ol=el('ol',null,'gestao-fases');
  fases.forEach((f,i)=>{const li=el('li',null,f.fase===ativa?'ativa':'');li.dataset.fase=f.fase;li.dataset.situacao=f.situacao;
   const x=el('button',`${f.situacao==='CONCLUIDA'?'✓':f.fase===ativa?'●':'○'} ${i+1}. ${f.titulo}`);x.type='button';x.addEventListener('click',()=>renderFluxo(p,id,comp,b,e,recarregar,f.fase));li.append(x);ol.append(li);});
  const corpoFase=el('div',null,'gestao-fase');corpoFase.dataset.faseAtiva=ativa;
  p.append(ol,corpoFase);
  ({balancete:faseBalancete,book:faseBook,conferencia:faseConferencia,confirmacao:faseConfirmacao}[ativa]||faseBalancete)(corpoFase,id,comp,b,e,(f)=>recarregar(f||ativa));
 }
 function enviarArquivo(p,rotulo,aceitar,acao,aoLer){
  const f=campo(p,rotulo,'file');f.accept=aceitar;f.dataset.arquivo=acao;const resultado=el('div',null,'previa-automatica');let leitura=0;
  f.addEventListener('change',async()=>{const atual=++leitura;resultado.replaceChildren();if(!f.files.length)return;resultado.append(el('p','Lendo o arquivo…','gestao-nota'));
   try{const r=await aoLer(await arquivo(f.files[0],45*1024*1024));if(atual!==leitura)return;resultado.replaceChildren();r(resultado);}
   catch(x){resultado.replaceChildren(erroBloco('Não foi possível ler este arquivo.',x.message,'Confira se é o arquivo certo (PDF ou planilha) e envie novamente.'));}});
  p.append(resultado);return f;
 }
 async function reanalisarBase(id,comp){
  if(!window.confirm('Reanalisar a base? Recalcula tipos, grupos e pendências usando os arquivos já enviados. Os arquivos originais não serão alterados. Se o plano receber tipo ou grupo, o piloto fica suspenso até a reconferência do cadastro.'))return;
  const r=await api('POST',`/empresas/${id}/base-reanalisar`,{competencia:comp,confirmado:true});
  await abrirEmpresa(id,comp);
  const x=r.reanalise||{};const antes=Object.values(x.pendencias_antes||{}).reduce((a,b)=>a+b,0),depois=Object.values(x.pendencias_depois||{}).reduce((a,b)=>a+b,0);
  const piloto=(x.tipos_preenchidos||x.grupos_preenchidos)?' Base reanalisada. Revise as pendências e confirme novamente o cadastro antes de continuar o piloto.':'';
  informar((x.mudou?`Base reanalisada: ${x.tipos_preenchidos} tipo(s) e ${x.grupos_preenchidos} grupo(s) preenchidos automaticamente; itens pendentes: ${antes} → ${depois}.`:'Base reanalisada: nada mudou.')+piloto);
 }
 function erroBloco(titulo,motivo,acao){const d=el('div',null,'gestao-erro');d.append(el('strong',titulo),el('p','Motivo: '+motivo),el('p','O que fazer: '+acao));return d;}
 function numeros(p,itens){const w=el('div',null,'gestao-numeros');itens.forEach(([n,t,cls])=>{const x=el('div',null,'gestao-numero'+(cls?' '+cls:''));x.append(el('strong',String(n)),el('span',t));w.append(x);});p.append(w);return w;}

 function faseBalancete(p,id,comp,b,e,recarregar){
  p.append(el('h3','Balancete anterior'));
  const db=b.data_base?new Date(b.data_base+'T12:00:00').toLocaleDateString('pt-BR'):'o último dia do mês anterior';
  if(b.balancete){const x=b.balancete,t=x.totais;
   p.append(el('p',`Recebido: ${x.arquivo} · ${new Date(x.recebido_em).toLocaleString('pt-BR')}`,'gestao-nota'));
   numeros(p,[[t.contas_extraidas,'contas extraídas'],[t.analiticas,'analíticas'],[t.sinteticas,'sintéticas'],[t.linhas_que_nao_conferem,'saldos que não conferem',t.linhas_que_nao_conferem?'atencao':'ok']]);
   resumoPlano(p,b.analise_plano,()=>renderFluxo(p.parentElement,id,comp,b,e,recarregar,'conferencia'));
   const aplicadas=b.contas_aplicadas&&b.fases&&b.fases[0].situacao==='CONCLUIDA';
   if(!aplicadas){p.append(el('p','Próximo passo: confira as contas e aplique-as ao plano da empresa.'));aplicarContas(p,id,comp,recarregar);}
   else p.append(el('p',`✓ Contas aplicadas ao plano em ${new Date(b.contas_aplicadas.em).toLocaleString('pt-BR')}.`,'ok'));
   tabelaFiltrada(p,'Ver todas as contas',['Código','Classificação','Descrição','Tipo','Grupo','Saldo anterior','Débitos','Créditos','Saldo atual','Situação'],
    (b.contas_extraidas||[]).map(c=>({ok:!(c.problemas||[]).length&&c.tipo&&c.grupo_contabil,c:[c.codigo,c.classificacao,c.descricao,c.tipo==='ANALITICA'?'Analítica':c.tipo==='SINTETICA'?'Sintética':'A confirmar',GRUPO_CONTABIL[c.grupo_contabil]||'A confirmar',fmtValor(c.saldo_anterior),fmtValor(c.debitos),fmtValor(c.creditos),fmtValor(c.saldo_atual),((c.problemas||[]).length||!c.tipo||!c.grupo_contabil)?'Precisa de atenção':'Conferida']})),
    [['Todas',()=>true],['Pendentes',l=>!l.ok],['Conferidas',l=>l.ok]]);
   const mais=el('details',null,'gestao-sob-demanda');mais.append(el('summary','Substituir o balancete'));
   mais.append(el('p','As diferenças são mostradas antes de salvar. Nenhuma conta é excluída e a confirmação anterior da base deixa de valer.','gestao-nota'));
   uploadBalancete(mais,id,comp,recarregar);p.append(mais);
   const re_=el('details',null,'gestao-sob-demanda');re_.append(el('summary','Reanalisar base'),el('p','Recalcula tipos, grupos e pendências usando os arquivos já enviados. Os arquivos originais não serão alterados.','gestao-nota'));
   const brn=botao('Reanalisar base',()=>reanalisarBase(id,comp));brn.dataset.acao='reanalisar-base-fase';re_.append(brn);p.append(re_);
   tecnico(p,{formato:x.formato,meta:x.meta,linhas_ignoradas:x.linhas_ignoradas,limites:x.limites,duvidas:x.duvidas,conferencia:x.conferencia});
  }else{
   const l=el('p',`Envie o balancete de encerramento de ${db} (PDF do Domínio ou planilha).`);p.append(l);ajuda(l,'O balancete do mês anterior traz as contas e os saldos iniciais. O layout do Domínio é reconhecido automaticamente.');
   uploadBalancete(p,id,comp,recarregar);
  }
 }
 function uploadBalancete(p,id,comp,recarregar){
  enviarArquivo(p,'Arquivo do balancete','.pdf,.xlsx,.xls,.csv,.txt','balancete',async a=>{
   const prev=await api('POST',`/empresas/${id}/base-balancete`,{...a,competencia:comp});
   return res=>{res.dataset.previa='balancete';const t=prev.totais,m=prev.meta||{},c=prev.conferencia||{};
    res.append(el('strong',`Contas extraídas do balancete: ${t.contas_extraidas}`));
    numeros(res,[[t.analiticas,'analíticas'],[t.sinteticas,'sintéticas'],[t.linhas_que_nao_conferem,'saldos que não conferem',t.linhas_que_nao_conferem?'atencao':'ok'],[t.tipo_indefinido,'contas com tipo a definir',t.tipo_indefinido?'atencao':'ok']]);
    const dl=el('dl',null,'gestao-dados');[['Empresa no relatório',m.empresa||'não identificada'],['CNPJ',m.cnpj||'não identificado'],['Período',m.periodo?`${m.periodo.inicio.split('-').reverse().join('/')} a ${m.periodo.fim.split('-').reverse().join('/')}`:'não identificado'],['Abrangência',m.abrangencia?.tipo==='CONSOLIDADO'?'Consolidado ('+m.abrangencia.estabelecimentos.join(', ')+')':'Individual / não informada']].forEach(([k,v])=>dl.append(el('dt',k),el('dd',v)));res.append(dl);
    (c.bloqueios||[]).forEach(x=>res.append(nivelLinha('BLOQUEIO',x)));
    if(prev.reimportacao){const r=prev.reimportacao;res.append(nivelLinha('ATENCAO',`Substituição: ${r.novas.length} conta(s) nova(s), ${r.alteradas.length} alterada(s), ${r.ausentes_no_novo.length} ausente(s). Contas ausentes não são excluídas.`));lista(res,'Ver contas alteradas',r.alteradas.map(x=>`${x.classificacao}: `+Object.entries(x.mudancas).map(([k,v])=>`${k} ${v[0]} → ${v[1]}`).join('; ')));}
    tabelaFiltrada(res,'Ver todas as contas',['Código','Classificação','Descrição','Tipo','Saldo anterior','Débitos','Créditos','Saldo atual','Situação'],
     prev.contas.map(c=>({ok:!(c.problemas||[]).length,c:[c.codigo,c.classificacao,c.descricao,c.tipo==='ANALITICA'?'Analítica':c.tipo==='SINTETICA'?'Sintética':'A definir',fmtValor(c.saldo_anterior),c.debitos,c.creditos,fmtValor(c.saldo_atual),(c.problemas||[]).length?'Precisa de atenção':'Conferida']})),
     [['Todas',()=>true],['Pendentes',l=>!l.ok],['Conferidas',l=>l.ok]]);
    tecnico(res,{formato:prev.formato,meta:prev.meta,conferencia:prev.conferencia,linhas_ignoradas:prev.linhas_ignoradas,limites:prev.limites,duvidas:prev.duvidas});
    if(!prev.pode_salvar)return;
    const ok=campo(res,'Conferi as contas e o período do balancete','checkbox');ok.dataset.campo='confirmar-balancete';
    const s=primario('Salvar balancete',async()=>{if(!ok.checked)throw new Error('Marque a conferência das contas e do período antes de salvar.');await api('POST',`/empresas/${id}/base-balancete`,{competencia:comp,token:prev.token,salvar:true,confirmado:true});await recarregar('balancete');});s.dataset.acao='salvar-balancete';res.append(s);};
  });
 }
 function aplicarContas(p,id,comp,recarregar){
  const area_=el('div',null,'gestao-aplicar');area_.dataset.previa='contas';p.append(area_);area_.append(el('p','Carregando as contas…','gestao-nota'));
  api('POST',`/empresas/${id}/base-contas`,{competencia:comp}).then(r=>{area_.replaceChildren();
   numeros(area_,[[r.novas.length,'contas novas'],[r.iguais.length,'iguais ao plano'],[r.alteradas.length+r.conflitos.length,'diferentes do plano',r.alteradas.length+r.conflitos.length?'atencao':'ok'],[r.ausentes_no_balancete.length,'do plano ausentes (mantidas)']]);
   resumoPlano(area_,r.analise_plano);
   const grupos={};if(r.ancoras_grupo.length){const g=el('div',null,'gestao-ancoras');const tg=el('strong',`Grupo de ${r.ancoras_grupo.length} ramo(s) que precisa(m) de confirmação`);g.append(tg);ajuda(tg,'A estrutura destes ramos não permite identificar o grupo com segurança. As contas subordinadas herdam o grupo confirmado.');
    r.ancoras_grupo.forEach(a=>{const s=campo(g,`${a.classificacao} · ${a.descricao}`,'select');opcoes(s,[['','Confirmar depois'],...Object.entries(GRUPO_CONTABIL)]);s.value='';s.dataset.ancora=a.classificacao;grupos[a.classificacao]=s;});area_.append(g);}
   const adotar={};const dif=[...r.alteradas.map(x=>[x,'mesmo código com classificação/descrição diferente']),...r.conflitos.map(x=>[x,x.motivo])];
   if(dif.length){const d=el('details',null,'gestao-sob-demanda');d.append(el('summary',`Contas diferentes do plano atual (${dif.length}) — marque só as que devem ser atualizadas`));
    dif.forEach(([x,m])=>{const cb=campo(d,`${x.conta.codigo||'sem código'} ${x.conta.classificacao} ${x.conta.descricao} — ${m}`,'checkbox');if(x.conta.codigo)adotar[x.conta.codigo]=cb;else cb.disabled=true;});area_.append(d);}
   const ok=campo(area_,'Conferi as contas e quero aplicá-las ao plano da empresa','checkbox');ok.dataset.campo='confirmar-contas';
   const s=primario('Aplicar contas ao plano',async()=>{if(!ok.checked)throw new Error('Marque a conferência das contas antes de aplicar.');
    if(!confirm('Aplicar as contas ao plano da empresa? O piloto fica suspenso até a reconferência do cadastro.'))return;
    await api('POST',`/empresas/${id}/base-contas`,{competencia:comp,salvar:true,confirmado:true,grupos:Object.fromEntries(Object.entries(grupos).filter(([,s])=>s.value).map(([k,s])=>[k,s.value])),adotar:Object.entries(adotar).filter(([,c])=>c.checked).map(([k])=>k)});await recarregar('book');});
   s.dataset.acao='aplicar-contas';area_.append(s);
  }).catch(x=>{area_.replaceChildren(erroBloco('Não foi possível carregar as contas.',x.message,'Tente novamente em instantes.'));});
 }
 function faseBook(p,id,comp,b,e,recarregar){
  p.append(el('h3','Book / composições'));
  if(!b.balancete){p.append(nivelLinha('BLOQUEIO','Envie primeiro o balancete anterior: as composições são comparadas com ele.'));return;}
  if(b.book){const x=b.book;p.append(el('p',`Recebido: ${x.arquivo} · ${new Date(x.recebido_em).toLocaleString('pt-BR')}`,'gestao-nota'));resumoBook(p,x.confronto,x.alertas,x.conferencia,x.abas);
   const mais=el('details',null,'gestao-sob-demanda');mais.append(el('summary','Substituir o book'));uploadBook(mais,id,comp,recarregar);p.append(mais);}
  else{const l=el('p','Envie o book do mesmo período (planilha com as composições dos saldos).');p.append(l);ajuda(l,'Arquivo utilizado para conferir a composição dos saldos do mês anterior. Qualquer organização de abas é aceita; fórmulas, macros e vínculos não são executados.');uploadBook(p,id,comp,recarregar);
   const semBook=(b.definicoes||[]).find(x=>x.chave==='sem_book');if(semBook&&!semBook.resolvida){const d=el('details',null,'gestao-sob-demanda');d.append(el('summary','Seguir sem o book'));pendenciaAcao(d,semBook,id,comp,e,recarregar);p.append(d);}}
 }
 function uploadBook(p,id,comp,recarregar){
  enviarArquivo(p,'Arquivo do book','.xlsx,.xlsm,.xls','book',async a=>{
   const prev=await api('POST',`/empresas/${id}/base-book`,{...a,competencia:comp});
   return res=>{res.dataset.previa='book';
    res.append(el('strong',`Book lido: ${prev.resumo.abas} aba(s), ${prev.resumo.composicoes} composição(ões)`));
    resumoBook(res,prev.confronto,prev.alertas,prev.conferencia,prev.abas);
    lista(res,'Ver evidências citadas no book (arquivos não recebidos pelo aplicativo)',prev.evidencias.map(x=>`${x.conta||''} · ${x.arquivo||''} · ${x.veredito||''}`));
    if(prev.conferencia.bloqueios.length){prev.conferencia.bloqueios.forEach(t=>res.append(nivelLinha('BLOQUEIO',t)));return;}
    const ok=campo(res,'Conferi a leitura do book','checkbox');ok.dataset.campo='confirmar-book';
    const s=primario('Salvar book',async()=>{if(!ok.checked)throw new Error('Marque a conferência da leitura antes de salvar.');await api('POST',`/empresas/${id}/base-book`,{competencia:comp,token:prev.token,salvar:true,confirmado:true});await recarregar('conferencia');});s.dataset.acao='salvar-book';res.append(s);};
  });
 }
 function resumoBook(p,conf,alertas,conferencia,abas){
  if(!conf)return;const r=conf.resumo;
  const resumo=el('div',null,'gestao-resumo-book');resumo.dataset.resumoBook='true';
  numeros(resumo,[[r.composicoes,'composições analisadas'],[r.iguais_ao_balancete,'iguais ao balancete','ok'],[r.divergentes,'diferentes do balancete',r.divergentes?'atencao':'ok'],[r.sem_conta,'sem conta no balancete',r.sem_conta?'atencao':'ok']]);
  resumo.append(el('p','Diferença zero não significa conciliação concluída: os documentos de suporte e a sua confirmação continuam pendentes.','gestao-nota'));
  (alertas||[]).forEach(t=>resumo.append(nivelLinha('ATENCAO',t)));
  p.append(resumo);
  tabelaFiltrada(p,'Ver todas as composições',['Aba','Conta','Método','Itens','Composição','Balancete','Diferença','Situação'],
   conf.composicoes.map(x=>({n:x.conferencia_numerica,c:[x.aba,x.conta?`${x.conta.codigo||''} ${x.conta.classificacao}`:(x.identificador.classificacao||x.identificador.codigo||'—'),TXT_METODO[x.metodo]||x.metodo,x.itens,fmtValor(x.saldo_composicao),fmtValor(x.saldo_balancete),x.diferenca==null?'—':fmtValor(x.diferenca),TXT_CONF[x.conferencia_numerica]||x.conferencia_numerica]})),
   [['Todas',()=>true],['Pendentes',l=>l.n!=='IGUAL_AO_BALANCETE'],['Divergentes',l=>l.n==='DIVERGENTE'||l.n==='SINAL_A_CONFIRMAR'],['Conferidas',l=>l.n==='IGUAL_AO_BALANCETE']]);
  lista(p,'Ver contas com saldo sem composição',conf.contas_com_saldo_sem_composicao.map(c=>`${c.codigo||''} ${c.classificacao} ${c.descricao} · ${fmtValor(c.saldo)}`));
  if(abas)lista(p,'Ver abas do arquivo',abas.map(a=>`${a.aba}: ${TXT_ABA[a.tipo]||a.tipo}`));
  tecnico(p,{resumo:r,conferencia:conferencia,composicoes:conf.composicoes.map(x=>({aba:x.aba,conferencia_numerica:x.conferencia_numerica,metodo:x.metodo,regra_saldo:x.regra_saldo,saldo_coluna:x.saldo_coluna,alertas:x.alertas}))});
 }
 function nivelLinha(nivel,texto){const [ic,t]=NIVEL[nivel];const x=el('p',null,'gestao-nivel '+nivel.toLowerCase());x.dataset.nivel=nivel;x.append(el('span',`${ic} ${t}`,'gestao-selo'),' '+texto);return x;}

 function faseConferencia(p,id,comp,b,e,recarregar){
  p.append(el('h3','Conferência'));
  const a=b.resumo_analise;const defs=(b.definicoes||[]).filter(x=>!['balancete','contas','sem_book'].includes(x.chave));
  if(a){const c=el('div',null,'gestao-analise');c.dataset.analiseBase='true';c.append(el('strong','Análise da base inicial'));
   numeros(c,[[a.contas_analisadas,'contas analisadas'],[a.sem_apontamentos,'sem apontamentos','ok'],[a.precisam_atencao,'precisam de atenção',a.precisam_atencao?'atencao':'ok'],[a.bloqueiam,'bloqueiam a confirmação',a.bloqueiam?'bloqueio':'ok']]);p.append(c);}
  const abertas=defs.filter(x=>!x.resolvida),feitas=defs.filter(x=>x.resolvida);
  const resumo=el('p',null,'gestao-pendencias-resumo');resumo.dataset.pendenciasAbertas=String(abertas.filter(x=>x.nivel!=='INFORMATIVO').length);
  resumo.textContent=abertas.length?`${abertas.filter(x=>x.nivel==='BLOQUEIO').length} bloqueio(s), ${abertas.filter(x=>x.nivel==='ATENCAO').length} ponto(s) de atenção e ${abertas.filter(x=>x.nivel==='INFORMATIVO').length} informativo(s).`:'Nenhuma pendência aberta.';p.append(resumo);
  const legenda=el('p',null,'gestao-legenda');['BLOQUEIO','ATENCAO','INFORMATIVO'].forEach(n=>legenda.append(el('span',`${NIVEL[n][0]} ${NIVEL[n][1]}: ${NIVEL[n][2]}`,'gestao-legenda-item '+n.toLowerCase())));p.append(legenda);
  const ordem={BLOQUEIO:0,ATENCAO:1,INFORMATIVO:2};
  abertas.sort((x,y)=>ordem[x.nivel]-ordem[y.nivel]).forEach(x=>p.append(pendencia(x,id,comp,e,recarregar)));
  if(feitas.length){const d=el('details',null,'gestao-sob-demanda');d.append(el('summary',`Conferidas (${feitas.length})`));feitas.forEach(x=>d.append(pendencia(x,id,comp,e,recarregar)));p.append(d);}
 }
 function pendencia(x,id,comp,e,recarregar){
  const art=el('article',null,'gestao-pendencia '+(x.nivel||'').toLowerCase());art.dataset.definicaoBase=x.chave;art.dataset.resolvida=x.resolvida?'sim':'nao';art.dataset.nivel=x.nivel||'';
  const [ic,t]=NIVEL[x.nivel]||NIVEL.ATENCAO;
  const topo=el('div',null,'gestao-pendencia-topo');topo.append(el('span',x.resolvida?'✓ Conferido':`${ic} ${t}`,'gestao-selo'),el('h4',(x.titulo_simples||x.titulo)+(x.quantidade?` (${x.quantidade})`:'')));art.append(topo);
  if(x.resolvida){art.append(el('p',`Conferido em ${new Date(x.ciencia.em).toLocaleString('pt-BR')}: ${x.ciencia.justificativa}`,'gestao-nota'));return art;}
  const dl=el('dl',null,'gestao-guia');[['Problema',x.problema||x.titulo],['Impacto',x.impacto||x.detalhe],['O que fazer',x.o_que_fazer||'']].forEach(([k,v])=>{if(v)dl.append(el('dt',k),el('dd',v));});art.append(dl);
  (x.saldos_nao_conferem||[]).filter(s=>s.calculavel).slice(0,3).forEach(s=>{const c=el('div',null,'gestao-saldo-nao-confere');c.dataset.saldoNaoConfere=s.codigo||s.classificacao;
   c.append(el('strong',`Saldo não confere · ${s.codigo||''} ${s.classificacao} ${s.descricao||''}`));const d=el('dl',null,'gestao-dados');
   [['Saldo anterior',brl(s.saldo_anterior)],['Débitos',brl(s.debitos)],['Créditos',brl(s.creditos)],['Saldo esperado',brl(s.saldo_esperado)],['Saldo informado',brl(s.saldo_informado)],['Diferença',brl(s.diferenca)]].forEach(([k,v])=>d.append(el('dt',k),el('dd',v)));c.append(d);
   const calc=el('details',null,'gestao-sob-demanda');calc.append(el('summary','Ver cálculo'),el('p',`${brl(s.saldo_anterior)} + ${brl(s.debitos)} − ${brl(s.creditos)} = ${brl(s.saldo_esperado)}; o balancete informa ${brl(s.saldo_informado)}.`));c.append(calc);art.append(c);});
  lista(art,'Ver itens',x.itens);
  pendenciaAcao(art,x,id,comp,e,recarregar);
  tecnico(art,{codigo:x.chave,acao:x.acao,nivel:x.nivel,bloqueia_confirmacao:x.bloqueia_confirmacao,detalhe:x.detalhe,titulo_original:x.titulo});
  return art;
 }
 function pendenciaAcao(art,x,id,comp,e,recarregar){
  const acao=el('div',null,'gestao-pendencia-acao');
  if(x.acao==='CIENCIA'||x.acao==='ETAPA_4_OU_CIENCIA'){
   const j=campo(acao,'Justificativa (o que você conferiu)');j.dataset.campo='justificativa';const ok=campo(acao,'Conferi e estou ciente (nada é ajustado automaticamente)','checkbox');
   const bt=botao('Marcar como conferido',async()=>{if(!ok.checked)throw new Error('Marque a caixa de conferência antes de continuar.');if(j.value.trim().length<5)throw new Error('Escreva uma justificativa curta (pelo menos 5 caracteres).');await api('POST',`/empresas/${id}/base-ciencia`,{competencia:comp,chave:x.chave,justificativa:j.value.trim(),confirmado:true});await recarregar();});bt.dataset.acao='ciencia-'+x.chave;acao.append(bt);}
  else if(x.acao==='SALDO_INICIAL'){
   const codigos=(x.itens||[]).map(s=>s.split(' ')[0]);const s=campo(acao,'Conta','select');opcoes(s,[['*',`Todas as ${codigos.length} contas listadas`],...codigos.map(c=>[c,(x.itens.find(i=>i.startsWith(c+' '))||c)])]);s.dataset.campo='saldo-conta';
   const v=campo(acao,'Saldo inicial (zero também precisa ser informado: 0,00)');v.dataset.campo='saldo-valor';const n=campo(acao,'Natureza','select');opcoes(n,[['','Saldo zero'],['D','Devedor (D)'],['C','Credor (C)']]);n.dataset.campo='saldo-natureza';
   const j=campo(acao,'Justificativa');j.dataset.campo='saldo-justificativa';const ok=campo(acao,'Confirmo o saldo inicial informado','checkbox');ok.dataset.campo='saldo-confirmar';
   const bt=botao('Salvar saldo inicial',async()=>{if(!ok.checked)throw new Error('Marque a confirmação do saldo antes de salvar.');await api('POST',`/empresas/${id}/base-saldo-inicial`,{competencia:comp,codigos:s.value==='*'?codigos:[s.value],saldo:v.value,natureza:n.value||null,justificativa:j.value,confirmado:true});await recarregar();});bt.dataset.acao='definir-saldo';acao.append(bt);}
  else if(x.acao==='CONTA_DOMINIO'){
   const codigos=(x.itens||[]).map(s=>s.split(' ')[0]);const s=campo(acao,'Conta','select');opcoes(s,codigos.map(c=>[c,x.itens.find(i=>i.startsWith(c+' '))]));
   const j=campo(acao,'Justificativa (ex.: criada no Domínio em 05/11)');const ok=campo(acao,'Confirmo que a conta existe no Domínio com o MESMO código','checkbox');
   const bt=botao('Confirmar no Domínio',async()=>{if(!ok.checked)throw new Error('Marque a confirmação antes de continuar.');await api('POST',`/empresas/${id}/conta-dominio`,{codigo:s.value,justificativa:j.value,confirmado:true});await recarregar();});bt.dataset.acao='conta-dominio';acao.append(bt);}
  else if(x.acao==='DEFINIR_CONTA'){acao.append(botao('Abrir Plano contábil atual',()=>abrirEmpresa(id,comp,'plano')));}
  else if(x.acao==='ETAPA_2'||x.acao==='ETAPA_3')acao.append(botao('Ir para Balancete anterior',()=>abrirEmpresa(id,comp,'balancete')));
  else return;
  art.append(acao);
 }
 function faseConfirmacao(p,id,comp,b,e,recarregar){
  p.append(el('h3','Confirmação'));
  if(b.situacao==='CONFIRMADA'){const c=b.confirmacao||{};p.append(el('p',`✓ Base inicial confirmada (versão ${c.versao}) em ${c.em?new Date(c.em).toLocaleString('pt-BR'):''}.`,'ok'),
   el('p','Se algo mudar (novo balancete, book, conta ou saldo), a base volta para "em preparação" e as conferências que a usaram ficam desatualizadas.','gestao-nota'));return;}
  const bloq=(b.definicoes||[]).filter(x=>x.bloqueia_confirmacao&&!x.resolvida);
  if(bloq.length){p.append(nivelLinha('BLOQUEIO',`Resolva antes: ${bloq.map(x=>x.titulo_simples||x.titulo).join('; ')}.`));const ir=primario('Revisar pendências',()=>renderFluxo(p.parentElement,id,comp,b,e,recarregar,'conferencia'));ir.dataset.acao='revisar-pendencias';p.append(ir);return;}
  const r=el('div',null,'gestao-confirmar');r.append(el('strong','Você está confirmando'));
  const dl=el('dl',null,'gestao-dados');[['Empresa',e.nome],['Competência',mes(comp)],['Saldos iniciais de',new Date(b.data_base+'T12:00:00').toLocaleDateString('pt-BR')],['Contas com saldo',Object.keys(b.saldos||{}).length]].forEach(([k,v])=>dl.append(el('dt',k),el('dd',String(v))));r.append(dl);
  const f=campo(r,`Para confirmar, digite: ${b.frase_confirmacao}`);f.dataset.campo='frase-base';
  const bt=primario('Confirmar base',async()=>{await api('POST',`/empresas/${id}/base-confirmar`,{competencia:comp,frase:f.value.trim()});await recarregar('confirmacao');});bt.dataset.acao='confirmar-base';bt.disabled=true;
  f.addEventListener('input',()=>{bt.disabled=f.value.trim()!==b.frase_confirmacao;});r.append(bt);p.append(r);
 }

 // ---------------------------------------------------------------- configuração da empresa
 function mascara(v){const s=String(v||'');return s.length<=3?s:'•••'+s.slice(-3);}
 function configBancos(p,e,recarregar){
  p.append(el('h3','Contas bancárias'));const plano=Object.fromEntries((e.plano||[]).map(c=>[String(c.codigo),c]));
  if(!e.contas.length)p.append(el('p','Nenhuma conta bancária vinculada.','gestao-nota'));
  e.contas.forEach(c=>{const card=el('div',null,'gestao-banco-card');card.dataset.banco=c.conta;const pc=plano[String(c.contabil)];
   card.append(el('strong',`Banco ${c.banco_informado||c.banco}`));const dl=el('dl',null,'gestao-dados');
   [['Agência',mascara(c.agencia)],['Conta',mascara(c.conta)],['Conta contábil',pc?`${c.contabil} · ${pc.descricao}`:c.contabil],['Status','Vinculada']].forEach(([k,v])=>dl.append(el('dt',k),el('dd',v)));card.append(dl);p.append(card);});
  const ed=el('details',null,'gestao-sob-demanda');ed.dataset.editarBancos='true';ed.append(el('summary',e.contas.length?'Editar':'Vincular conta bancária'));bancos(ed,e,recarregar);p.append(ed);
 }
 function bancos(p,e,recarregar){
  ajuda(p,'Informe qual conta contábil corresponde a cada conta do banco (conta analítica do Ativo). Em Banco, use o código (ex.: 033) ou o nome Santander.');
  const linhas=el('div'),inputs=[];
  function add(c={}){const row=el('div',null,'gestao-banco'),r={};[['banco','Banco'],['agencia','Agência'],['conta','Conta'],['titular','CNPJ do titular'],['contabil','Conta contábil (código)']].forEach(([k,t])=>r[k]=campo(row,t,'text',c[k]||(k==='titular'?e.cnpj:'')));inputs.push(r);row.append(secundario('Remover',()=>{inputs.splice(inputs.indexOf(r),1);row.remove();}));linhas.append(row);}
  e.contas.forEach(add);if(!e.contas.length)add();
  const salvar=primario('Salvar contas bancárias',async()=>{await api('POST',`/empresas/${e.id}/bancos`,{contas:inputs.map(r=>Object.fromEntries(Object.entries(r).map(([k,v])=>[k,v.value])))});await recarregar('bancos');});salvar.dataset.acao='salvar-bancos';
  p.append(linhas,secundario('+ Adicionar conta',()=>add()),salvar);
 }
 function configCadastro(p,e,recarregar){
  p.append(el('h3','Cadastro e piloto'));const dl=el('dl',null,'gestao-dados');
  [['Razão social',e.nome],['CNPJ',e.cnpj],['Regime tributário',e.regime],['Código',e.id],['Cadastro conferido',e.cadastro_confirmado?'Sim':'Ainda não'],['Piloto em simulação',e.piloto?'Habilitado':'Bloqueado'],['Produção','Bloqueada nesta versão']].forEach(([k,v])=>dl.append(el('dt',k),el('dd',v)));p.append(dl);
  if(!e.piloto){const box=el('div',null,'gestao-confirmar');box.append(el('strong','Habilitar piloto em simulação'),el('p','Confira contas, base inicial e contas bancárias. O processamento prepara propostas para conferência; nada é lançado nem importado.','gestao-nota'));
   const frase=campo(box,`Para habilitar, digite: CONFIRMO PILOTO ${e.id}`);frase.dataset.campo='frase-piloto';
   const bt=primario('Habilitar piloto',async()=>{await api('POST',`/empresas/${e.id}/piloto`,{frase:frase.value.trim()});await recarregar('cadastro');});bt.dataset.acao='habilitar-piloto';box.append(bt);p.append(box);}
  if(e.metodo_fechamento&&e.metodo_fechamento.disponivel!==false){const m=e.metodo_fechamento,d=el('details',null,'gestao-sob-demanda');d.dataset.metodoEmpresa='true';d.append(el('summary','Método de fechamento documentado'),el('p',m.resumo||'Método documentado para conferência.'));(m.confirmacoes_supervisor||[]).forEach(x=>d.append(el('p','Confirmado: '+x)));p.append(d);}
 }
 function configPlano(p,e,b,recarregar){
  p.append(el('h3','Plano contábil atual'));const pl=e.plano||[];
  if(b&&b.analise_plano)resumoPlano(p,b.analise_plano,()=>abrirEmpresa(e.id,b.competencia,'conferencia'));
  const an=pl.filter(c=>['ANALITICA','ANALÍTICA'].includes(c.tipo)).length,si=pl.filter(c=>['SINTETICA','SINTÉTICA'].includes(c.tipo)).length,pend=pl.filter(c=>!c.tipo||!c.grupo).length,cri=pl.filter(c=>c.origem==='CRIADA_NO_APLICATIVO').length;
  numeros(p,[[pl.length,'contas'],[an,'analíticas'],[si,'sintéticas'],[pend,'sem grupo ou tipo',pend?'atencao':'ok']]);
  if(!pl.length)p.append(el('p','As contas vêm do balancete anterior, na preparação da base inicial.','gestao-nota'));
  tabelaFiltrada(p,'Ver todas as contas',['Código','Classificação','Descrição','Grupo','Tipo','Situação'],
   pl.map(c=>({pend:!c.tipo||!c.grupo,cri:c.origem==='CRIADA_NO_APLICATIVO',c:[c.codigo,c.classificacao||'',c.descricao,GR[c.grupo]||'a definir',c.tipo==='SINTETICA'?'Sintética':c.tipo==='ANALITICA'?'Analítica':'a definir',c.dominio==='PENDENTE_CONFERENCIA'?'Criada aqui · Domínio pendente':c.origem==='CRIADA_NO_APLICATIVO'?'Criada aqui · confirmada no Domínio':(!c.tipo||!c.grupo)?'Precisa de definição':'Conferida']})),
   [['Todas',()=>true],['Pendentes',l=>l.pend],['Criadas no aplicativo',l=>l.cri]]);
  if(pl.length){const mais=el('div',null,'gestao-acoes');p.append(mais);
   const def=el('details',null,'gestao-sob-demanda');def.dataset.definirConta='true';def.append(el('summary','Definir grupo e tipo de uma conta'));
   const conta=campo(def,'Conta','select');opcoes(conta,[...pl.filter(c=>!c.tipo||!c.grupo),...pl.filter(c=>c.tipo&&c.grupo)].map(c=>[c.codigo,`${c.codigo} · ${c.classificacao||''} · ${c.descricao}${!c.tipo||!c.grupo?' (pendente)':''}`]));
   const grupo=campo(def,'Grupo','select');opcoes(grupo,[['','Selecione'],['ATIVO','Ativo'],['PASSIVO','Passivo'],['PATRIMONIO_LIQUIDO','Patrimônio Líquido'],['RECEITA','Contas de Resultado · receita'],['CUSTO','Contas de Resultado · custo'],['DESPESA','Contas de Resultado · despesa'],['RESULTADO','Contas de Resultado'],['OUTROS','Outros']]);
   const tipo=campo(def,'Tipo','select');opcoes(tipo,[['','Selecione'],['ANALITICA','Analítica (recebe lançamentos)'],['SINTETICA','Sintética (agrupa outras contas)']]);
   const ok=campo(def,'Conferi esta definição','checkbox');def.append(primario('Salvar definição',async()=>{await api('POST',`/empresas/${e.id}/definir-conta`,{codigo:conta.value,grupo:grupo.value,tipo:tipo.value,confirmado:ok.checked});await recarregar('plano');}));p.append(def);
   criarConta(p,e,recarregar);}
 }
 function criarConta(p,e,recarregar){
  const d=el('details',null,'gestao-sob-demanda');d.dataset.criarConta='true';d.append(el('summary','Criar conta ou subconta'));
  ajuda(d,'A conta fica cadastrada no aplicativo; ela não é criada no Domínio. Lançamentos nela só entram no TXT depois que você confirmar que ela existe no Domínio com o mesmo código. O saldo inicial precisa ser informado (inclusive zero).');
  const sup=campo(d,'Conta superior','select');opcoes(sup,[['','Selecione'],...e.plano.filter(c=>['SINTETICA','SINTÉTICA'].includes(c.tipo)&&c.classificacao).map(c=>[c.classificacao,`${c.classificacao} · ${c.descricao}`])]);
  const cod=campo(d,'Código reduzido'),cla=campo(d,'Classificação'),desc=campo(d,'Descrição');
  const tipo=campo(d,'Tipo','select');opcoes(tipo,[['ANALITICA','Analítica'],['SINTETICA','Sintética']]);
  const grupo=campo(d,'Grupo','select');opcoes(grupo,[['','Selecione'],['ATIVO','Ativo'],['PASSIVO','Passivo'],['PATRIMONIO_LIQUIDO','Patrimônio líquido'],['RECEITA','Receita'],['DESPESA','Despesa'],['CUSTO','Custo']]);
  sup.addEventListener('change',()=>{const s=e.plano.find(c=>c.classificacao===sup.value);if(s){if(!cla.value)cla.value=sup.value+'.';if(s.grupo)grupo.value=s.grupo;}});
  [sup,cod,cla,desc,tipo,grupo].forEach((x,i)=>x.dataset.campo='nova-conta-'+['superior','codigo','classificacao','descricao','tipo','grupo'][i]);
  const ok=campo(d,'Conferi os dados da nova conta','checkbox');ok.dataset.campo='nova-conta-confirmar';
  const bt=primario('Criar conta',async()=>{await api('POST',`/empresas/${e.id}/criar-conta`,{codigo:cod.value.trim(),classificacao:cla.value.trim(),descricao:desc.value.trim(),superior:sup.value,tipo:tipo.value,grupo:grupo.value,confirmado:ok.checked});await recarregar('plano');});
  bt.dataset.acao='criar-conta';d.append(bt);p.append(d);
 }
 // Excluir cadastro: exclusão LÓGICA (nada é apagado); frase exata; recusada com operação em andamento
 async function exclusao(p,e){
  p.replaceChildren();const pv=await api('GET',`/empresas/${e.id}/exclusao`);
  const box=el('div',null,'gestao-exclusao-empresa');box.dataset.exclusaoEmpresa=e.id;box.append(el('h3','Excluir cadastro'),el('p',pv.mensagem));
  lista(box,'O que continua disponível',pv.permanece);
  if(pv.bloqueio){box.append(nivelLinha('BLOQUEIO',pv.bloqueio));(pv.impedimentos||[]).forEach(x=>box.append(el('p',x,'gestao-nota')));p.append(box);return;}
  const f=campo(box,`Para confirmar, digite: ${pv.frase}`);f.dataset.campo='frase-exclusao';
  const bt=botao('Confirmar exclusão',async()=>{await api('POST',`/empresas/${e.id}/excluir`,{frase:f.value.trim(),confirmado:true});await empresas();informar(`Cadastro de ${pv.nome} excluído. Os documentos e históricos continuam disponíveis.`);});
  bt.classList.add('gestao-perigo');bt.dataset.acao='confirmar-exclusao-empresa';bt.disabled=true;f.addEventListener('input',()=>{bt.disabled=f.value.trim()!==pv.frase;});
  const cancelar=secundario('Cancelar',()=>p.replaceChildren());box.append(bt,cancelar);p.append(box);
 }

 // Definições necessárias do Supervisor: regras em REFERÊNCIA/PROPOSTA ou com confirmação insuficiente (inclusive bancárias no
 // formato antigo) NÃO são aplicadas; cada uma é confirmada pela frase exata. Políticas não suportadas aparecem sem botão.
 const AREA_NOME={BANCOS:'Bancos',DP:'Departamento Pessoal',FISCAL:'Fiscal',CONCILIACAO:'Conciliação'};
 function definicoes(e,aberto){
  const itens=e.definicoes_necessarias||[];const d=el('details',null,'gestao-definicoes');d.dataset.definicoes='true';d.open=!!aberto&&itens.length>0;
  d.append(el('summary',`Referências que podem precisar de confirmação (${itens.length})`));
  if(!itens.length){d.append(el('p','Nenhuma definição pendente: as regras desta empresa estão confirmadas (ou são regras de teste da amostra fictícia).','gestao-nota'));d.hidden=true;return d;}
  d.append(el('p','Referências sugeridas não bloqueiam a Base Inicial. A confirmação só será solicitada quando uma etapa precisar desta informação e não houver resolução segura.','gestao-nota'));
  itens.forEach(x=>{const art=el('div',null,'gestao-definicao');art.dataset.definicao=`${x.area}/${x.chave||''}`;
   art.append(el('strong',`${AREA_NOME[x.area]||x.area}${x.chave?' · '+x.chave:''}`),el('p',x.pergunta));
   if(x.situacao==='AUSENTE' || x.situacao==='INVALIDO'){
    art.replaceChildren(el('strong',`${AREA_NOME[x.area]||x.area}`),el('p','Referências ainda não configuradas.','gestao-nota'));
    const bt=botao('Preparar referências',()=>prepararReferencias(e));bt.dataset.acao='preparar-referencias';art.append(bt);
   } else if(x.frase){const f=campo(art,`Para confirmar, digite: ${x.frase}`);f.setAttribute('aria-label',`Frase para confirmar ${x.area} ${x.chave||''}`);
    art.append(botao('Confirmar esta regra',async()=>{await api('POST',`/empresas/${e.id}/regras-area`,{area:x.area,chave:x.chave,frase:f.value,confirmado:true});await abrirEmpresa(e.id,null,'regras');}));}
   else art.append(el('p','Esta referência precisa de revisão antes da confirmação. Abra os detalhes técnicos se necessário.','gestao-nota'));
   tecnico(art,{area:x.area,chave:x.chave,situacao:x.situacao});
   d.append(art);});
  return d;
 }

 async function prepararReferencias(e){
  const atual=document.querySelector('[data-regras-area]');if(atual){atual.scrollIntoView({block:'start'});return;}
  const comp=competenciaEmpresa[e.id]||competenciaPadrao();const s=await api('GET',`/empresas/${e.id}/regras-area?competencia=${encodeURIComponent(comp)}`);
  const p=el('section',null,'gestao-card');p.dataset.regrasArea='true';p.append(el('h2','Preparar referências das áreas'),el('p','As sugestões abaixo foram encontradas no plano contábil desta empresa. Elas não viram regras até a confirmação do Supervisor.','gestao-nota'));
  const escolhas={};
  Object.entries(s.areas).forEach(([area,dados])=>{
   const sec=el('details',null,'gestao-definicao');sec.open=false;sec.dataset.area=area;const resumo=el('summary',`${dados.nome} · ${dados.itens.filter(x=>x.conta).length} referências sugeridas`);sec.append(resumo);
   dados.itens.forEach(item=>{const art=el('div',null,'gestao-definicao');art.dataset.referencia=item.chave;art.append(el('strong',item.rotulo));
    const linha=el('div',null,'gestao-linha');const select=document.createElement('select');select.dataset.contaReferencia=item.chave;select.append(new Option(item.conta?`${item.conta.codigo||item.conta.classificacao} — ${item.conta.descricao}`:'Nenhuma conta encontrada',''));
    (s.plano||[]).filter(c=>String(c.tipo||'').toUpperCase().includes('ANAL')||!c.tipo).forEach(c=>select.append(new Option(`${c.codigo||c.classificacao} — ${c.descricao}`,c.codigo||'')));
    if(item.conta)select.value=item.conta.codigo||'';linha.append(select);art.append(linha,el('p',`Confiança: ${item.confianca}`,item.confianca==='ALTA CONFIANÇA'?'gestao-ok':'gestao-nota'));
    const na=el('label');const cb=document.createElement('input');cb.type='checkbox';cb.dataset.naoAplica=item.chave;na.append(cb,' Não se aplica');art.append(na);const just=campo(art,'Justificativa (quando não se aplica)');just.dataset.justificativa=item.chave;just.hidden=true;cb.addEventListener('change',()=>{just.hidden=!cb.checked;select.disabled=cb.checked;});sec.append(art);});
   const confirmar=botao('Confirmar referências',async()=>{const decisoes=[...sec.querySelectorAll('[data-referencia]')].map(a=>{const chave=a.dataset.referencia,cb=a.querySelector('[data-nao-aplica]'),just=a.querySelector('[data-justificativa]'),sel=a.querySelector('[data-conta-referencia]');return cb.checked?{chave,acao:'NAO_APLICA',justificativa:just.value}:{chave,acao:'CONFIRMAR',codigo:sel.value};});await api('POST',`/empresas/${e.id}/regras-area`,{area,competencia:comp,decisoes});informar(`${dados.nome}: referências confirmadas.`);await abrirEmpresa(e.id,comp,'regras');});confirmar.dataset.acao=`confirmar-referencias-${area}`;sec.append(confirmar);p.append(sec);
  });
  const cancelar=secundario('Fechar preparação',()=>p.remove());p.append(cancelar);corpo.append(p);p.scrollIntoView({block:'start'});
 }

 // Amostra FICTÍCIA do percurso completo (cenários A e B): situação, preparação e correção do caso B. Só atua nas duas empresas
 // fictícias da amostra; cada ação exige confirmação explícita. Nada é aprovado, escriturado ou liberado.
 function blocoAmostra(){
  const d=el('details',null,'gestao-amostra');d.dataset.amostra='true';d.open=true;
  d.append(el('summary','Amostra fictícia do percurso completo'));
  d.append(el('p','Dados inteiramente fictícios (empresas, CNPJs, valores e documentos). As ações abaixo só atuam nas duas empresas da amostra; nenhuma empresa real é alterada e nada é aprovado, escriturado ou liberado.','gestao-nota'));
  const sit=el('ul');d.append(el('strong','Situação'),sit);
  async function atualizarSituacao(){
   const a=await api('GET','/amostra');sit.replaceChildren();
   Object.entries(a).forEach(([k,x])=>sit.append(el('li',`Cenário ${k}: ${x.empresa} · ${x.preparada?'preparada':'ainda não preparada'} · documentos em ${x.documentos}`)));
  }
  atualizarSituacao().catch(e=>sit.replaceChildren(el('li',e.message)));
  d.append(el('p','Documentos: TESTES/AMOSTRA-COMPLETA/CENARIO-A (percurso conferido) e TESTES/AMOSTRA-COMPLETA/CENARIO-B (pendências e falha de configuração). Passo a passo: TESTES/AMOSTRA-COMPLETA/LEIA-ME.md.','gestao-nota'));
  const linha=el('label',null,'gestao-campo'),recriar=el('input');recriar.type='checkbox';recriar.dataset.recriar='true';
  linha.append(el('span','Recriar a amostra (a versão anterior das duas empresas fictícias é preservada no runtime, fora de CLIENTES; nada é apagado)'),recriar);
  const aviso=el('p','','gestao-nota');aviso.setAttribute('role','status');
  recriar.addEventListener('change',()=>{aviso.textContent=recriar.checked?'Atenção: recriar move a versão anterior das duas empresas fictícias para o runtime (preservada) e cria tudo de novo. Solicitações já abertas continuam registradas.':'';});
  const resultado=el('p',null,'gestao-resultado');resultado.setAttribute('role','status');
  const preparar=botao('Preparar amostra fictícia',async()=>{
   const pedido=recriar.checked?'Recriar a amostra fictícia? As duas empresas fictícias serão criadas de novo; a versão anterior fica preservada no runtime.':'Preparar a amostra fictícia? Cria (ou confirma) somente as duas empresas fictícias da amostra.';
   if(!window.confirm(pedido))return;
   const r=await api('POST','/amostra/preparar',recriar.checked?{confirmado:true,recriar:true}:{confirmado:true});
   resultado.textContent=`${r.resultado}: ${(r.empresas||[]).map(x=>`${x.empresa} ${x.situacao}`).join(' · ')} · competência ${r.competencia||'—'} · documentos em ${Object.values(r.documentos||{}).join(' e ')}.`;
   await atualizarSituacao();
  });preparar.dataset.acao='preparar-amostra';
  const corrigir=botao('Aplicar correção das referências do DP da amostra B',async()=>{
   if(!window.confirm('Aplicar a correção das referências do DP SOMENTE na empresa fictícia da amostra B? Depois retome a etapa na solicitação do cenário B.'))return;
   const r=await api('POST','/amostra/corrigir-dp-b',{confirmado:true});
   resultado.textContent=`${r.resultado} (${r.empresa}). Próximo passo: ${r.proximo_passo||'retomar a etapa na solicitação do cenário B.'}`;
  });corrigir.dataset.acao='corrigir-dp-b';
  d.append(linha,aviso,preparar,corrigir,resultado);
  return d;
 }

 async function arquivo(f,limite=20*1024*1024){if(f.size>limite)throw new Error(`Arquivo acima de ${Math.round(limite/1048576)} MB.`);const a=new Uint8Array(await f.arrayBuffer());let s='';for(let i=0;i<a.length;i+=32768)s+=String.fromCharCode(...a.subarray(i,i+32768));return {nome:f.name,conteudo:btoa(s)};}
 sincronizarPainel();
})();
