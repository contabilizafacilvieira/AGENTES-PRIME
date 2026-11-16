# AGENTES PRIME — Etapa 03D: fundamentação do Agente Financeiro

Data da consulta: 16/11/2026. Escopo restrito à fundamentação consultiva Financeira. A etapa não altera motor, leitores, critérios de associação, cardinalidade ou tolerâncias. Exemplos e dados desta complementação são integralmente fictícios. Não houve acesso ou gravação em runtime REAL, cadastro real, fechamento ou processamento de empresa piloto arquivada.

**Classificação técnica desta entrega: ETAPA_03D_APROVADA**, sujeita à revisão do Supervisor. A Etapa 03 geral continua em complementação; 03E não iniciada.

## Preservação e arquitetura

- [x] Preservadas Etapas 01 e 02 aprovadas e fundamentação Contábil 03C (CONT-01–CONT-20, 12 casos e testes existentes).
- [x] Integrada coleção distinta FIN-01–FIN-20 em BASE_CONHECIMENTO_CONTABIL/fundamentos_financeiros.json, sem duplicar os conceitos contábeis: fichas FIN referenciam os CONT pertinentes.
- [x] Adicionados 15 casos fictícios consultáveis em BASE_CONHECIMENTO_CONTABIL/casos_financeiros.json.
- [x] Consulta em consulta.py por ID, assunto, referencial, competência e caso; toda orientação é consultiva e AUTORIZA_DECISAO_AUTOMATICA=false.
- [x] Atualizado catálogo compartilhado de fontes oficiais.
- [x] Critérios do motor permanecem identificados como PROCEDIMENTO_INTERNO conforme AGENTES/FINANCEIRO/PROCEDIMENTO.md v1.5; nenhum arquivo do motor Financeiro foi editado.
- [x] Separados: norma contábil, regulamentação do arranjo Pix, orientação administrativa RFB, interpretação técnica e controles internos.

## Cobertura dos fundamentos

Todos os 20 foram avaliados e documentados no escopo descrito em suas fichas. Status: **20 VERIFICADO, 0 PARCIAL, 0 PENDENTE, 0 NAO_VERIFICADO**. “Verificado” não autoriza lançamento nem aplicação automática: significa que a afirmação consultiva e limitada tem referência, dispositivo/seção identificável ou procedimento interno rastreável. Aplicação a empresa exige referencial confirmado, competência, documentos e revisão humana.

| ID | Fundamento | Tipo | Fontes / dispositivo principal | Aplicabilidade | Status |
|---|---|---|---|---|---|
| FIN-01 | Extratos bancários | Documento fonte + interpretação | ITG 2000 (R1), itens 5–8; CONT-01/18/19 | Identificar fluxo e saldos, sem inferir natureza | VERIFICADO |
| FIN-02 | Conciliação bancária | Procedimento interno | ITG 2000 (R1), itens 5–8; procedimento Financeiro v1.5 | Aritmética, associação, natureza e suporte são verificações distintas | VERIFICADO |
| FIN-03 | Contas a pagar | Interpretação técnica | CONT-03/05/08/19; NBC TG 1001/1002, seção 11 conforme referencial | Direito/obrigação, documento e liquidação | VERIFICADO |
| FIN-04 | Contas a receber | Interpretação técnica | CONT-03/06/08/19; NBC TG 1001/1002, seções 11 e 23 quando aplicável | Fato/contrato, direito, recebimento | VERIFICADO |
| FIN-05 | Liquidação de fornecedores | Interpretação técnica | CONT-08/19; NBC TG 1001/1002, seção 11 | Baixa somente contra obrigação confirmada | VERIFICADO |
| FIN-06 | Liquidação de clientes | Interpretação técnica | CONT-08/19; NBC TG 1001/1002, seção 11 | Baixa somente contra recebível confirmado | VERIFICADO |
| FIN-07 | Adiantamentos a fornecedores | Interpretação técnica | CONT-09/19; Estrutura Conceitual e referencial aplicável | Direito, entrega, restituição ou consumo | VERIFICADO |
| FIN-08 | Adiantamentos de clientes | Interpretação técnica | CONT-09/14/19; referencial/contrato aplicável | Obrigação e execução do compromisso | VERIFICADO |
| FIN-09 | Transferências entre contas próprias | Interpretação técnica | CONT-01/19; evidência de titularidade e duas pontas | Apenas com identidade da entidade demonstrada | VERIFICADO |
| FIN-10 | Aplicações e resgates | Interpretação técnica | CONT-15/19; NBC TG 1001/1002, seção 11; CPC 48/NBC TG 48 se aplicável | Instrumento e referencial determinam mensuração | VERIFICADO |
| FIN-11 | Rendimentos de aplicações | Interpretação técnica | CONT-03/15; CPC 48/NBC TG 48 se aplicável | Contrato, período, bruto e retenções | VERIFICADO |
| FIN-12 | Tarifas bancárias | Interpretação técnica | CONT-03/07/19; documento/contrato | Serviço e período identificados | VERIFICADO |
| FIN-13 | Juros e multas | Interpretação técnica | CONT-03/07/15/20; norma/contrato conforme origem | Separar natureza, principal e período; fiscal em separado | VERIFICADO |
| FIN-14 | Empréstimos e financiamentos | Interpretação técnica | CONT-15/19; NBC TG 1001/1002 seção 11; CPC 48 se aplicável | Contrato, saldo e cronograma | VERIFICADO |
| FIN-15 | Separação de principal e juros | Interpretação técnica | CONT-03/15/19; demonstrativo do credor e norma aplicável | Composição por parcela e período | VERIFICADO |
| FIN-16 | Estornos e devoluções | Interpretação técnica | CONT-17/19; evidência das duas pontas e fato original | Vincular a origem e avaliar período | VERIFICADO |
| FIN-17 | Pix, TED, boleto e outros meios | Regulação financeira + interpretação | Res. BCB 1/2020 e requisito UX Pix 7.3; comprovantes RFB quando aplicável; CONT-08/09/19 | Meio comprova fluxo; natureza requer fonte do fato | VERIFICADO |
| FIN-18 | Cartões e intermediadores | Interpretação técnica | CONT-06/08/15/19; CPC 48 quando aplicável e contrato | Bruto, taxa, prazo e recebível conforme contrato | VERIFICADO |
| FIN-19 | Moeda estrangeira | Interpretação técnica | CONT-16/19; seções 30 simplificadas, ITG 21/NBC TG 02 quando aplicáveis | Moeda funcional, competência e contrato | VERIFICADO |
| FIN-20 | Evidências, duplicidades e rastreabilidade | Procedimento interno + interpretação | ITG 2000 (R1), itens 5–8; procedimento Financeiro v1.5 | Proveniência, identidade e trilha; valor/texto não bastam | VERIFICADO |

**Limite de abrangência:** a aprovação cobre estes 20 fundamentos introdutórios e controles de evidência. Não declara domínio de todos os produtos financeiros, operações de tesouraria, derivativos, factoring, securitização, regulação de instituições financeiras, instrumentos complexos, tributos incidentes, nem de todas as revisões/versionamentos das normas completas. Aplicabilidade NBC TG 48/CPC 48 é condicional e não automática para referenciais simplificados. BCB/COSIF e regras de arranjo regem instituições/sistemas em seus âmbitos; não foram convertidos em regras contábeis universais para empresas usuárias.

## Casos fictícios

- [x] 15 consultas: fornecedor provisionado; pagamento sem documento; recebimento de cliente; crédito sem identificação; adiantamentos de fornecedor/cliente; transferência própria; aplicação; resgate/rendimento; empréstimo com principal/juros; estorno; tributo; folha; cartão com taxa; pagamentos de mesmo valor a beneficiários distintos.
- [x] Cada caso informa natureza provável, evidência, departamento responsável, fundamento, tratamento conceitual, risco, limitações e necessidade de decisão humana.
- [x] Os exemplos não geram lançamentos nem contabilizações automáticas.

## Fontes oficiais efetivamente consultadas

- [x] CFC: catálogo atual das normas específicas e simplificadas; consulta ao texto oficial NBC TG 1001, seções 11 e 12; reutilizados os textos e evidências da Etapa 03C para ITG 2000 (R1), NBC TG 1002 e NBC TG 1000 (R1) nas fichas CONT referenciadas.
- [x] CPC: página CPC 48 identifica aprovação regulatória CFC/NBC TG 48; pronunciamento CPC 48 consultado para alcance e objetivo, com aplicabilidade expressamente condicional.
- [x] Banco Central: Resolução BCB nº 1/2020 em versão indicada como vigente em 02/10/2026 e requisitos Pix de experiência do usuário, versão 7.3/dezembro de 2025. Usados somente para características do sistema/comprovante.
- [x] Receita Federal: consulta oficial para comprovantes DARF, DAS, DAE e DJE e validação de arrecadação. Não utilizada para inferir reconhecimento contábil nem classificação de tributo.
- [x] Não foi necessário consultar legislação estadual/municipal nesta etapa delimitada; nenhuma regra local ou alíquota foi afirmada.

## Testes, motor e segurança

- [x] Testes específicos da base Financeiro: 6/6; bateria de isolamento REAL/DEMO/TESTE: 4/4. Testes existentes da consulta contábil: 10/10.
- [x] Regressões Financeiro: previstas no gate completo, incluindo testes de normalizador, integração, conciliação, decisões do Supervisor, associação manual, ambiguidades, percurso e suporte documental.
- [x] AGENTES/FINANCEIRO/ferramentas/* e AGENTES/FINANCEIRO/PROCEDIMENTO.md sem alteração nesta etapa; regras de associação v1.5, limites, tolerâncias e estados preservados.
- [x] Nenhum runtime REAL alterado, nenhum fechamento executado, nenhum cadastro real, nenhuma continuidade empresa piloto arquivada, sem commit/push.
- [x] Gate completo após inclusão do novo teste: 77/77 baterias aprovadas, zero falhas; estado operacional intocado; GATE DE RELEASE: APROVADO. Saídas temporárias locais não versionadas.
- [ ] Revisão e aceite do Supervisor.
- [x] Etapa 03E não iniciada.

## Checklist mestre

Etapas 01 e 02 permanecem aprovadas conforme registros anteriores; Etapa 03 geral permanece em complementação; 03C concluída no escopo delimitado; esta 03D aguarda revisão do Supervisor. Não iniciar 03E antes da revisão.
