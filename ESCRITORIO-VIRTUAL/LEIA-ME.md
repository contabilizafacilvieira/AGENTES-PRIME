# ESCRITÓRIO VIRTUAL - AGENTES PRIME

Camada de **visualização e supervisão** do AGENTES PRIME: um escritório contábil em pixel art isométrico em que
cada personagem representa um agente e mostra o estado dele.

Dois modos:
- **Simulação (aberto do disco):** somente dados fictícios; sem rede (`connect-src 'none'`).
- **Operação local (servido pela API em 127.0.0.1):** Nova solicitação → empresa, competência, upload, instrução →
  Iniciar. O Coordenador gera a SOL, delega ao Agente de Documentos e decide o estado; a tela mostra a SOL,
  documentos, códigos do extrator, pendências, motivos, auditoria e relatório, e o escritório reflete o estado real.
  O navegador não escolhe caminhos, agentes nem estados. Ver `API-LOCAL/LEIA-ME.md`.

## Como abrir
Simulação: dê dois cliques em `index.html`. Operação local: `.venv/Scripts/python.exe -I API-LOCAL/servidor.py`
e abra `http://127.0.0.1:8765/`.

Uso:
- **Clique em um agente** (ou Tab + Enter) para abrir o Painel do Supervisor com os detalhes. **✕ ou Esc** fecham o
  painel; a seleção continua marcada no escritório. Passar o mouse mostra nome e estado do agente.
- **SIMULAÇÃO** (topo) abre o menu de cenários de demonstração. **Legenda** explica os 8 estados.
- No painel, "Simulação · alterar status" muda o estado do agente selecionado (somente em memória).

Atalhos pela URL:
- `index.html?cenario=4` (número ou id do cenário, ex.: `?cenario=pendencia`)
- `index.html?cenario=2&agente=coordenador` (abre com um agente selecionado e o painel aberto)

## Estrutura
```
ESCRITORIO-VIRTUAL/
├── index.html                 página (topo com menus, palco do escritório, painel recolhível)
├── css/escritorio.css         visual da interface
├── js/estados.js              catálogo dos 8 estados (rótulo, símbolo, cor, descrição)
├── js/mapa.js                 função PURA: estado real das SOLs (API) → estado de cada personagem
├── js/cena.js                 escritório isométrico: planta, mobília, personagens, balões, caminhos e caminhada
├── js/painel.js               menus (Simulação, Legenda), resumo, relógio e Painel do Supervisor
├── js/app.js                  estado em memória, validação dos dados, seleção
├── js/operacao.js             modo operação local (só ativo quando servido pela API com token de sessão)
├── dados/estado-simulado.js   TODOS os dados fictícios (agentes, áreas e cenários)
└── LEIA-ME.md
```
Não há pasta `assets/`: todos os gráficos são desenhados por código (formas e sprites próprios),
sem imagens externas.

Os dados ficam em `.js`, e não em `.json`, porque o Chrome bloqueia a leitura de arquivos locais por `fetch`
quando a página é aberta direto do disco (`file://`).

## Princípios de arquitetura e segurança
```
AGENTES REAIS / COORDENADOR  →  estado operacional estruturado  →  ESCRITÓRIO VIRTUAL  →  Supervisor
                                    (hoje: dados/estado-simulado.js)     (somente leitura)
```
- O Escritório **só lê** um estado estruturado e o exibe. Ele não executa ferramentas, não chama agentes,
  não contorna o Coordenador, não grava ordem ativa e não altera nenhuma proteção do projeto.
- A página bloqueia conexões por política de segurança (`connect-src 'none'`). Não há `fetch`, armazenamento
  local, `eval` ou recursos externos.
- Os dados exibidos usam somente `textContent` (nada é interpretado como HTML).
- Agentes com `implementado: false` aparecem **sempre** como "Em breve", qualquer que seja o cenário.
- Os controles de desenvolvimento mudam apenas os dados fictícios em memória; recarregar a página desfaz.

## Contrato do estado (versão 2)
`dados/estado-simulado.js` define `window.ESCRITORIO_DADOS`:

| Campo | Descrição |
|---|---|
| `agentes[]` | `id`, `nome`, `nomeCurto`, `funcao`, `implementado`; opcionais `area` (especialista interno de uma área) e `relacao` (papel em relação à Contabilidade) |
| `areas[]` | `id`, `nome`, `funcao`, `especialistas[]` (`{ agente }` funcional, `{ nome, via }` executado na mesa de outro especialista ou `{ nome }` "em breve") |
| `cenarios[]` | `id`, `titulo`, `descricao`, `solicitacao` (`{ id, estado }` da SOL exibida: aberta, `ENCERRADA` ou `CANCELADA`), `estados` |
| `estados[idDoAgente]` | `status`, `empresa`, `competencia`, `solicitacao`, `tarefa`, `inicio`, `fim`, `atualizacao`, `pendencias[]`, `mensagem`, `local` (`mesa` ou `copa`), `disponibilidade`, `eventos[]` |

A posição de cada agente na planta é dado visual e fica em `js/cena.js` (`POSTOS`), separado dos dados operacionais.
**A posição das mesas não define a ordem de execução**: quem distribui as tarefas é sempre o Coordenador.

## Organização do escritório
A numeração das placas mostra a sequência do percurso: 1 Documentos → 2 áreas (Financeiro, Fiscal, DP) → 3 Contabilidade →
4 Conciliação → 5 Coordenador (e Supervisor). A posição das mesas não define a ordem de execução (quem distribui e acompanha
é sempre o Coordenador).

| Lugar | Quem | Situação |
|---|---|---|
| Sala de vidro | **5 · Coordenador** | funcional; fica no posto; recebe o resultado da Conciliação e apresenta ao Supervisor |
| Fileira norte | **1 · Documentos** → **2 · Financeiro** · **2 · Fiscal** · **2 · DP** (lado a lado) | todos funcionais (SIMULAÇÃO) |
| Ilha central | **3 · Contabilidade**: Bancos (logo abaixo do Financeiro; na mesma mesa prepara Contabilidade/DP e Contabilidade/Fiscal) e Importação VGROW (SIMULAÇÃO, só VGROW, pausada) | quadro clicável; "Apuração tributária completa" e "Demais ajustes" "em breve" no painel da área |
| Faixa sul | **4 · Conciliação** | funcional (SIMULAÇÃO): confere o conjunto e entrega ao Coordenador |
| Copa | sofá (3 lugares) e poltrona, separada por meia-parede | personagens disponíveis; quem sobrar fica em pé |

Placas da fileira norte e da copa ficam acima da parede; as da ilha e da faixa sul, no piso, fora dos personagens e dos
móveis (teste automático de sobreposição). Um tracejado discreto no piso mostra o percurso da pasta.

Representação apenas (sem personagem, estado ou regra): a Contabilidade como área e os especialistas futuros.

## Personagens que caminham (Documentos, Financeiro, Fiscal, DP, Contabilidade/Bancos, Conciliação e Importação VGROW)
- **Percurso completo** (cada entrega = horário registrado em `etapas`, nunca inventado): Documentos entrega a pasta às áreas
  acionadas na ordem Financeiro → DP → Fiscal (fim de Documentos); cada área trabalha na própria mesa (início da etapa) e entrega
  à Contabilidade (fim da etapa, quando a etapa contábil dela começou); a Contabilidade trabalha Bancos, Contabilidade/DP e
  Contabilidade/Fiscal (tentativas independentes: `ban:N`, `ban:DN`, `ban:FN`) e, com Conciliação no plano, entrega o conjunto à
  Conciliação no início dela (`ban:CN`); a Conciliação trabalha e entrega ao Coordenador (fim). Retomada: nova tentativa da etapa
  (DP volta a buscar a pasta no Coordenador) e nova Conciliação animadas uma única vez.
- Conciliação concluída com divergência, pendência, alcance parcial ou desatualizada aparece como **Pendência** (nunca ✓);
  tudo conferido = "conciliada no alcance da SIMULAÇÃO (não é aprovação)".
- **Passagem da pasta de trabalho** (fluxo Financeiro → Contabilidade/Bancos): Documentos busca a pasta no Coordenador,
  trabalha e a entrega na mesa do Financeiro; o Financeiro a entrega na mesa de Bancos; Bancos devolve ao Coordenador.
  Cada passagem corresponde a uma mudança de etapa registrada (horário da etapa); nova tentativa (decisão ou regra
  aprovada) começa com o Financeiro buscando a pasta no Coordenador. Fluxo só de Documentos e Importação VGROW: idas ao
  Coordenador como antes.
- **Bloqueio**: nenhuma entrega é inventada; a pasta fica na mesa da área responsável, marcada em vermelho, e a tela de
  acompanhamento explica o motivo.
- A pasta é desenhada na mesa de quem está com o trabalho (indicador estático, vale também no movimento reduzido).
- Sem solicitação pendente que o tenha acionado → senta na copa. Quem já participou permanece na própria mesa até a
  conclusão global da SOL, inclusive em Aguardando Supervisor. Caminhos calculados em uma grade sobre a planta (A*), contornando móveis, paredes,
  divisórias e a meia-parede da copa.
- A caminhada **só acompanha** o estado real (`js/mapa.js`): não atrasa o processamento e nunca dispara, aprova ou
  repete operações. Se a etapa terminar antes de o personagem chegar, a fila visual preserva buscar, trabalhar na
  própria mesa e entregar. A animação não prolonga nem altera a execução real.
- Estado da tarefa ≠ disponibilidade: quando a etapa termina e aguarda o Supervisor, o personagem não aparece
  "Trabalhando"; o resultado ("Concluído — conferência entregue à Contabilidade/Bancos" etc.) continua no painel.
- SOL **ENCERRADA** (revisão parcial do piloto) aparece como "Revisão parcial encerrada" e SOL **CANCELADA** como "Cancelada":
  nenhuma é fechamento integral, e nenhum personagem, placa ou contagem do topo mostra "✓ Concluído" para elas. As
  pendências históricas de todas as áreas (Financeiro, Bancos, Fiscal, Contabilidade/Fiscal, falhas e dependências) ficam
  no painel do Coordenador e dos agentes. Estar na copa é só disponibilidade: não comprova aprovação.
- Contabilidade (personagem "Bancos") atende Bancos e Contabilidade/Fiscal como etapas independentes: as duas aparecem,
  cada uma com o seu resultado; falha de Bancos continua visível mesmo com a Contabilidade/Fiscal concluída, e os eventos
  de uma etapa nunca substituem os da outra (a fila da animação segue os horários registrados).
- A disponibilidade considera toda SOL ainda aberta, inclusive fora das 10 mais recentes (`GET /api/estado`).
- Recarregar a página não repete entregas: os personagens aparecem direto no lugar atual e só eventos com horário
  posterior ao carregamento são animados.
- Com "reduzir movimento" no sistema: sem caminhada, sem envelope e sem animações; indicadores estáticos.
- Zoom − / Ajustar / + no canto inferior direito da área do escritório (à esquerda do Painel do Supervisor quando ele
  está aberto; nunca sobre os painéis): a cena aproveita o espaço disponível; ampliação adicional permite rolar o
  escritório. Ajustar restaura a visão inteira.

## Estados reconhecidos
Cada estado tem símbolo, texto e animação próprios; a cor nunca é a única indicação.

| Estado | Indicação visual |
|---|---|
| LIVRE | xícara no balão, tela em repouso |
| TRABALHANDO | engrenagem, pontinhos de progresso, mãos digitando, tela rolando |
| AGUARDANDO_SUPERVISOR | ampulheta, mão levantada, balão pulsando, halo âmbar no piso |
| PENDENCIA | exclamação pulando, tela com faixa amarela, halo amarelo no piso |
| CONCLUIDO | visto, brilho, braços para cima |
| ERRO | X, personagem tremendo, tela vermelha piscando, halo vermelho no piso |
| OFFLINE | "Z", personagem acinzentado, tela apagada (todos offline = modo noite) |
| NAO_IMPLEMENTADO | silhueta translúcida, cadeira vazia, placa "em breve" |

Com "reduzir movimento" ativado no sistema, as animações e a caminhada ficam desligadas.

## Cenários de demonstração
1. Escritório em repouso · 2. Documentos trabalhando · 3. Aguardando Supervisor · 4. Importação calculando ·
5. Importação aguardando conferência · 6. Financeiro conferindo · 7. Pendência · 8. Revisão parcial encerrada
(pendências históricas preservadas; sem ✓) · 9. Erro · 10. Percurso completo: Conciliação conferindo (DP e Conciliação) ·
11. Fim do expediente. Em todo cenário com SOL aberta, quem participou fica na mesa; Fiscal, DP e Conciliação não declarados
ficam disponíveis na copa.

## Testes
- `node TESTES/ESCRITORIO/testar_mapa.js` — mapeamento puro (estado real da SOL, disponibilidade, histórico, eventos).
- `node TESTES/ESCRITORIO/testar_ciclo_solicitacao.js` — ciclo completo da caminhada (fila, entregas, recarga).
- `node TESTES/ESCRITORIO/testar_auditoria_mapa.js` — ENCERRADA/CANCELADA, Bancos × Contabilidade/Fiscal, textos de
  entrega, ordem da animação e regras dos dados simulados.
- `.venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_estado_recentes.py` — SOL aberta antiga continua em
  `GET /api/estado` (runtime, registro e ordem ativa temporários; sem porta).
- `.venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_auditoria_navegador.py <pasta>` — navegador contra um mock em
  memória (`mock_api_escritorio.py`): resumo com pendências de todas as áreas, etapas sem ✓ indevido, zoom sem sobrepor
  painéis (1000×720 e 1280×800), adiantamento nas decisões e em Empresas.
- `.venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_escritorio.py <pasta>` — navegador: hierarquia, caminhos,
  caminhada por eventos (inclusive DP → Contabilidade → Conciliação → Coordenador), recarga sem repetição, movimento reduzido
  e capturas de tela (dados fictícios).
- `node TESTES/ESCRITORIO/testar_percurso_mapa.js` — percurso completo no mapeamento e na caminhada: DP e Conciliação
  implementados, entregas reais, retomada, recarga, movimento reduzido, Conciliação desatualizada/parcial nunca ✓.
- `.venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_percurso_navegador.py <pasta>` — navegador contra o mock (amostra A
  fictícia): acompanhamento com situação das áreas, propostas de Bancos/Fiscal/DP, Conciliação (A–E, fontes EXTERNA × INTERNA,
  alcance, vigência, histórico), retomada com justificativa e confirmação, SOL sem âncora, bloco da amostra em Empresas e
  legibilidade em 1000×720 e 1280×800.
- `node TESTES/ESCRITORIO/testar_aprovacao_mapa.js` — FECHAMENTO_APROVADO no escritório: rótulo, participantes liberados, nunca
  "escriturado"/"liberado" como afirmação; revogação volta ao posto.
- `.venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_acompanhamento_navegador.py <pasta>` — abas, faixa de status, indicadores,
  tabela de lançamentos com filtros, Conciliação filtrada/expansível, aprovação e revogação (POST com o contrato do servidor),
  Solicitações, "Ampliar painel" (1000×720 e 1280×800), ENCERRADA/CANCELADA.

## Acompanhamento da solicitação (painel lateral em abas) e aprovação do fechamento
O escritório continua sempre visível à direita. O painel abre mais largo que os formulários; **Ampliar painel** (no topo do painel)
alarga para analisar tabelas e deixa ~280px para o escritório; **Recolher painel** volta. Sem rolagem horizontal da página em
1000×720 e 1280×800: com o painel estreito as tabelas viram cartões; com o painel largo podem rolar só dentro do próprio contêiner.
- Cabeçalho compacto: SOL · empresa · competência · selo de situação (aviso de SIMULAÇÃO discreto).
- **Resumo**: faixa de status com uma frase, por cor: verde "Tudo conferido — pronto para a sua aprovação"; âmbar "N itens impedem a
  aprovação" (lista curta de `aprovacao_impedimentos`); azul "Em processamento — etapa X"; verde escuro "Fechamento aprovado em <data>
  (SIMULAÇÃO — <situação efetiva do TXT>; nada escriturado)"; cinza para revisão parcial encerrada/cancelada. Indicadores com os números do detalhe
  (movimentos conferidos · lançamentos propostos/incompletos · Conciliação conferidas/divergentes/pendentes · pendências abertas por área
  e etapas com falha). Etapas ① Documentos ② áreas acionadas ③ Contabilidade ④ Conciliação ⑤ Supervisor (④ só ✓ conferida no alcance e
  vigente; ⑤ só ✓ com o fechamento aprovado). Próxima ação curta, botão **Aprovar fechamento**, pendências por área, situação de cada
  área (recolhida), "Resultado por extenso" (texto completo, que nunca diz "sem pendências" havendo problema) e revisão parcial do piloto.
- **Lançamentos**: tabela única (origem Bancos/DP/Fiscal, data/competência, débito e crédito com código e nome, valor, status,
  origem/regra), filtros por origem e status, totais por origem e CSV de Bancos.
- **Conciliação**: tentativa, vigência, alcance (e o que não foi executado), resumo por grupo A–E e tabela de verificações (grupo,
  verificação, conta/item, esperado, encontrado, diferença, resultado com cor, área). Filtro padrão "Divergentes e pendentes"; "Todas"
  mostra o resto. Clique na verificação para ver fontes EXTERNA × INTERNA, justificativa e ação. Histórico das conciliações.
- **Decisões**: retomada de etapa (botão "Retomar <área>" só para etapa FALHOU com `retomada_disponivel`; justificativa 5–500 e
  confirmação; sem âncora orienta nova solicitação), fila de decisões por movimento, regras propostas, itens que dependem de documento,
  cadastro ou outra área, e "Para conhecimento".
- **Histórico**: aprovações (vigente e revogadas), eventos da SOL, retomadas, conciliações, tentativas, decisões, trabalho por área e
  evidências/auditoria.
- A aba, os filtros e as linhas abertas sobrevivem à atualização automática da mesma SOL.

### Como dizer ao Coordenador que aprovo
1. Abra a solicitação (Solicitações → Ver acompanhamento). Na aba **Resumo**, a faixa precisa estar verde ("Tudo conferido — pronto
   para a sua aprovação"). Se estiver âmbar, o botão fica desabilitado e a lista mostra o que impede (`aprovacao_impedimentos`).
2. Clique em **Aprovar fechamento**, digite a frase exibida (`APROVO FECHAMENTO <SOL>`), escreva a justificativa (5 a 500 caracteres)
   e marque "Entendo que é SIMULAÇÃO: nada é escriturado; o TXT (empresa fictícia) só serve para importação MANUAL no Domínio, ainda
   não validada" (e, se houver fatos que já saíram em TXT revogado, a caixa de ciência). **Confirmar aprovação** só habilita com tudo válido.
3. A tela envia `POST /api/solicitacoes/<SOL>/aprovacao` `{acao:'aprovar', frase, justificativa, confirmado:true}`; o Coordenador
   registra e a SOL passa a `FECHAMENTO_APROVADO` (recusa 409 aparece no painel). Faixa verde escura com data e justificativa.
4. Para desfazer: **Revogar aprovação** → justificativa + confirmação → `{acao:'revogar', justificativa, confirmado:true}`; a SOL volta a
   aguardar o Supervisor e a aprovação revogada fica no Histórico.
- `FECHAMENTO_APROVADO` é estado fechado: no escritório e em Solicitações aparece "Fechamento aprovado (SIMULAÇÃO)"; os participantes
  ficam liberados (copa). Nada é escriturado. TXT do Domínio só para empresa fictícia, com a situação EFETIVA mostrada (liberado,
  bloqueado por fonte alterada, falhou, empresa real bloqueada, aprovada antes da exportação); importação sempre manual.
- Empresas → **Amostra fictícia do percurso completo**: situação (`GET /api/amostra`), "Preparar amostra fictícia" (confirmação;
  opção recriar, com a versão anterior preservada no runtime) e "Aplicar correção das referências do DP da amostra B"
  (confirmação). Documentos em `TESTES/AMOSTRA-COMPLETA/CENARIO-A` e `CENARIO-B`; passo a passo em `TESTES/AMOSTRA-COMPLETA/LEIA-ME.md`.

## Adiantamentos (decisões e Empresas)
- Nas decisões, `ADIANTAMENTO_FORNECEDOR`/`ADIANTAMENTO_CLIENTE` só aparecem com a(s) conta(s) que o Supervisor indicou em
  **Empresas → Contas de adiantamento** (`contas_adiantamento`); sem indicação, a natureza não é oferecida e o cartão explica
  o motivo. A indicação exige conta analítica do grupo correto (ATIVO / PASSIVO), fora das contas bancárias, confirmação e
  justificativa; pode ser removida. Ela não classifica nada automaticamente e não supre documento.
- Pendências `ADIANTAMENTO_NAO_INDICADO` (depende de definição no cadastro) e `DEPENDE_AREA` (depende de outra área — o
  Fiscal) nunca aparecem como "decisão possível agora".
- O resumo do acompanhamento considera as pendências de todas as áreas (inclusive extrato incompleto), falhas e
  dependências; etapa com falha, bloqueio ou pendência não recebe ✓, e ⑤ Coordenador nunca aparece como fechamento concluído.

## Como evoluir
- **Novo cenário:** acrescentar um item em `cenarios[]` no arquivo de dados.
- **Novo agente:** acrescentar em `agentes[]` e definir um posto em `POSTOS` (`js/cena.js`); especialistas da
  Contabilidade usam `area: "contabilidade"` e a mesa reservada da ilha. Personagem funcional que caminha:
  `caminha: true` no posto. A identidade visual da estação fica em `ESTACOES` (`js/cena.js`): Documentos
  (bandeja, pastas, gaveteiro, verde-petróleo) e Importação (pastas por processo, calculadora, contêiner).
- **Dados reais (etapa futura, a autorizar):** o Coordenador geraria um arquivo de estado no mesmo contrato, e o
  Escritório continuaria apenas lendo esse arquivo. A forma de entrega (arquivo gerado + servidor local somente
  leitura) será definida e testada à parte, sem dar ao navegador acesso a `CLIENTES/` ou permissão de escrita.
