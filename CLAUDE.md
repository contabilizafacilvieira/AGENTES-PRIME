
# AGENTES PRIME — Escritório Contábil Virtual

## 1. Objetivo
Coordenar e automatizar tarefas contábeis por meio de agentes de inteligência artificial, mantendo a supervisão humana obrigatória.

Versão atual: **v1.0.0-interno** — primeira versão operacional interna SUPERVISIONADA (não é produção autônoma).
Uso pelos funcionários: `MANUAL-DO-ESCRITORIO.md`. Testes oficiais: `TESTES/GATE-RELEASE.md` (`TESTES/executar_gate.py`).
Atualização operacional: o servidor padrão usa Documentos local, sem modelos externos, e Financeiro/Bancos locais.
Consulte `GUIA-PILOTO-LOCAL.md` e `AGENTS.md` para cadastro, conferência bancária e limitações. O executor Claude é legado,
sem fallback automático. O piloto real em SIMULAÇÃO exige autorização específica; produção continua bloqueada.

## 2. Estrutura Organizacional
Fluxo oficial e responsabilidades: `ORGANOGRAMA-E-FLUXO.md` (definição do Supervisor em 02/11/2026).
Coordenador → Documentos → Financeiro/DP/Fiscal → Contabilidade → Conciliação → Coordenador + Supervisor.
Documentos distribui; as áreas analisam; Contabilidade prepara a escrituração; Conciliação confere os resultados.
Na versão atual, Financeiro, DP, Fiscal, Contabilidade (Bancos, DP, Fiscal) e Conciliação executam localmente em SIMULAÇÃO:
propostas para conferência, sem aprovação, escrituração efetiva ou liberação. A Conciliação informa o alcance da conferência.

- Supervisor Contábil: responsável pelas decisões e aprovações.
- Coordenador Geral: responsável por distribuir, acompanhar e supervisionar as tarefas.
- Agentes Especializados: responsáveis pela execução das atividades de cada departamento.

## 3. Regras Principais
- Nenhum lançamento contábil poderá ser liberado para importação no sistema Domínio sem aprovação explícita do Supervisor Contábil.
- Cada cliente deverá possuir seu próprio histórico, plano de contas, regras e manual contábil.
- BASE INICIAL por empresa e competência (decisão do Supervisor em 05/11/2026): a competência M parte do balancete de ENCERRAMENTO
  de M−1 (contas e saldos; o balancete basta como fonte inicial das contas) e do book contábil do mesmo período (composições,
  títulos, evidências, pendências), enviados pela tela Empresas (6 etapas). Saldos D/C como informados; nada presumido (nem zero);
  composições e saldos de abertura não são lançamentos; divergência é mostrada, nunca ajustada; status/assinaturas do book são
  informação da fonte. Só a base CONFIRMADA (`CONFIRMO BASE INICIAL <EMP> <AAAA-MM>`) alimenta a Conciliação; mudar a base torna
  desatualizadas as conferências e aprovações que a usaram. Contas novas só por ação expressa do Supervisor, sem saldo presumido e
  com correspondência no Domínio pendente (bloqueia o TXT até a confirmação); o aplicativo nunca cria contas no Domínio.
- ÁRVORE DO PLANO (regra geral, `API-LOCAL/plano_hierarquia.py`): conta com descendentes = SINTÉTICA; folha = ANALÍTICA; grupo
  contábil (Ativo, Passivo, Patrimônio Líquido, Contas de Resultado, Outros) reconhecido pela descrição das contas principais e
  herdado pelos descendentes (numeração nunca é prova). Composição no book só para conta ANALÍTICA patrimonial com saldo ≠ 0;
  sintéticas, Contas de Resultado, Outros e saldo zero nunca geram falta de composição. Só ramos ambíguos vão ao Supervisor.
  Falta de composição de conta elegível = ATENÇÃO (não bloqueia a base; contada no resumo; o Supervisor marca como conferido com
  justificativa, que vale para aquela lista e aqueles saldos). Classificação repetida = Bloqueio próprio, nada é renumerado.
- Fluxo atual (organograma de 02/11/2026): Documentos → Financeiro/DP/Fiscal → Contabilidade (Bancos, DP, Fiscal) → Conciliação → Coordenador + Supervisor (aprovação explícita) → TXT para importação MANUAL no Domínio (somente empresa fictícia nesta versão). Estudo para aprendizado por razão foi removido por decisão do Supervisor em 01/11/2026.
- Regras por empresa (REGRAS-DP.json, REGRAS-FISCAIS.json, REGRAS-CONCILIACAO.json) têm situação: REFERENCIA e PROPOSTA não são aplicadas; APROVADA exige confirmação do Supervisor com a frase exata; TESTE_FICTICIO vale só em empresa com o marcador AMOSTRA-FICTICIA.json. Referência sem situação nunca vira regra aprovada em silêncio.
- A data do lançamento de DP/Fiscal é separada da competência do fato e só vem de política expressa da empresa; sem política, a proposta fica incompleta com a pergunta ao Supervisor (nada é presumido).
- Conciliação e aprovação valem só enquanto resultados, documentos, cadastro, plano e regras usados não mudarem; mudança torna a conferência desatualizada e indica as etapas a rever (retomada só por ação do Supervisor).
- Os agentes não poderão inventar informações ou valores ausentes.
- Toda divergência deverá ser comunicada ao Coordenador Geral.
- Os documentos originais deverão ser preservados.
- Produção permanece bloqueada nesta versão. Piloto com empresa real é permitido em SIMULAÇÃO, com autorização específica por empresa (CONFIRMO PILOTO <ID>); a exportação TXT de empresa real continua bloqueada (aprovação registrada, nenhum arquivo). O teste em SIMULAÇÃO exige cadastro e vínculos bancários conferidos; não exige razão nem três meses de treinamento. Destinos para ausência de suporte são definidos por empresa, com decisão expressa do Supervisor.

## 4. Funções do Coordenador Geral
O Coordenador Geral deverá:
1. Receber as solicitações do Supervisor Contábil.
2. Identificar a empresa e a competência contábil.
3. Distribuir as tarefas aos agentes especializados.
4. Acompanhar o andamento das atividades.
5. Identificar divergências e pendências.
6. Consolidar os resultados dos agentes.
7. Encaminhar os lançamentos para aprovação do Supervisor.
8. Liberar arquivos para importação somente após aprovação explícita, colocando-os em LIBERADOS/EMPRESA/AAAA-MM, sem importar no Domínio. Liberar não é importar nem escriturar.

As instruções detalhadas estão em:
COORDENADOR-GERAL/INSTRUCOES.md

## 5. Agentes Especializados
Os agentes serão organizados na pasta AGENTES.

O primeiro agente é o Agente de Documentos, responsável por receber, identificar, classificar e organizar documentos contábeis.
Status: HOMOLOGADO EM AMBIENTE FICTÍCIO; não liberado para produção com dados reais.

- Definição do subagente: .claude/agents/agente-documentos.md
- Componentes e status: AGENTES/DOCUMENTOS/LEIA-ME.TXT
- Protocolo de delegação: COORDENADOR-GERAL/INSTRUCOES.md (seção 4)
- Relatório de testes: TESTES/RELATORIO-TESTES.md

Financeiro, DP, Fiscal, Contabilidade (Bancos, DP, Fiscal) e Conciliação: IMPLEMENTADOS EM SIMULAÇÃO, código local, sem modelo
de linguagem (o executor Claude é legado, sem fallback). Empresa fictícia da amostra e piloto real autorizado em SIMULAÇÃO.
Agente de Importação (AGENTES/IMPORTACAO): exclusivo da VGROW; DESATIVADO por decisão do Supervisor (05/11/2026): rotas
respondem 410 e o Coordenador recusa os comandos exclusivos; código, regras e histórico preservados. Não confundir com a
exportação contábil TXT para importação manual no Domínio, que continua ativa.

## 6. Empresas (clientes)
O sistema é genérico e deve atender qualquer empresa cliente, sem vínculo com clientes específicos.

Cada cliente deverá possuir cadastro independente contendo:
- Razão social
- CNPJ
- Regime tributário
- Plano de contas
- Histórico
- Regras contábeis
- Treinamento inicial

Os agentes deverão utilizar exclusivamente as regras da empresa selecionada, sem misturar informações entre clientes.

"Excluir cadastro" (tela Empresas, menu ⋯) é exclusão LÓGICA do cadastro operacional: frase `EXCLUIR <CÓDIGO>`, recusada com
operação em andamento; documentos, solicitações, históricos, saídas e base inicial são preservados; o código não é reutilizado e
um novo cadastro não herda piloto, vínculos, plano ou regras. Padrão visual do Escritório: RESUMO → STATUS → PENDÊNCIAS →
AÇÃO NECESSÁRIA → DETALHES (detalhes técnicos só sob demanda; textos visíveis em pt-BR).

## 7. Integração com o Domínio
Os agentes poderão preparar arquivos TXT de lançamentos contábeis e planilhas Excel de validação.

Após aprovação explícita, os arquivos TXT serão colocados em LIBERADOS/EMPRESA/AAAA-MM. A importação no Domínio é sempre manual, feita pelo Supervisor Contábil.

Layout em uso (decisão do Supervisor em 04/11/2026): `Data;Débito;Crédito;Valor;CódHist;Complemento;IniciaLote;Matriz/Filial;CCDébito;CCCrédito`,
PARTIDA SIMPLES (uma linha por lançamento, débito e crédito na mesma linha, IniciaLote = 1 em todas), cp1252, CRLF. O cabeçalho e o
formato dos campos seguem a referência da VGROW, mas a referência da VGROW valida PARTIDA MÚLTIPLA; a variante simples AINDA NÃO
FOI VALIDADA no Domínio e exige o teste de importação numa empresa de teste (TESTES/EXPORTACAO/ROTEIRO-TESTE-DOMINIO.md).
Somente empresa fictícia gera TXT nesta versão. Junto com o TXT são gerados o Excel dos lançamentos e o balancete de verificação
(saldo inicial da base confirmada/abertura documentada + movimento aprovado = saldo final, D/C; sintéticas consolidadas pela
hierarquia sem entrar nos totais; versão da base identificada; entrega integral ou complementar), da MESMA versão aprovada (sha256
registrados juntos); o balancete é calculado pelo aplicativo em SIMULAÇÃO e não comprova escrituração no Domínio. Exportado não significa importado nem escriturado; revogar no aplicativo bloqueia o
download e renomeia o arquivo, mas não estorna importação eventualmente feita no Domínio.

Nenhum arquivo será importado no Domínio sem aprovação do Supervisor Contábil.

## 8. Diretriz de Funcionamento
O Coordenador Geral deverá seguir as instruções deste projeto, respeitar a hierarquia definida e solicitar aprovação humana sempre que necessário.

A existência dessas instruções não significa que os agentes já estejam automatizados. Suas funções deverão ser implementadas e testadas progressivamente.
