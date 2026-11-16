# AGENTES PRIME — Etapa 03: Base normativa contábil e técnica

Data da pesquisa: 16/11/2026. Versão inicial da base: 1.0.0. Resultado desta etapa: estrutura consultável implementada; cobertura temática inicial publicada com estados explícitos. Etapa 04 não iniciada.

**Classificação: ETAPA_03_BLOQUEADA.** A estrutura, testes e gate passaram, mas o conteúdo solicitado permanece incompleto: 158 tópicos estão inventariados (4 `VERIFICADO`, 35 `PARCIAL`, 114 `PENDENTE`, 5 `NAO_VERIFICADO`).

## Guardrails e estrutura

- [x] Inspecionados contratos e instruções existentes: `AGENTS.md`, `CLAUDE.md`, governança de regras e procedimentos de Contabilidade/Bancos, Fiscal, DP, Financeiro e Conciliação.
- [x] Criada `BASE_CONHECIMENTO_CONTABIL/` com sete categorias, catálogo de fontes, esquema de registro, consulta Python e inventário de cobertura.
- [x] Registros distinguem norma oficial, interpretação técnica e procedimento interno.
- [x] Registros gerais isolados de regras por empresa; consulta omite escopo de empresa quando não há o mesmo `empresa_id`.
- [x] Consulta é somente leitura; `AUTORIZA_DECISAO_AUTOMATICA=false` e conflito identificado vira `PENDENTE_REVISAO`.
- [x] Nenhum dado real, documento de cliente ou runtime foi copiado para a base.

## Fontes consultadas e conclusões verificadas

- [x] CFC: catálogo de normas simplificadas/específicas, FAQ sobre formalização de pronunciamentos CPC como NBC e sistema de resoluções para ITG 2000 (R1), ITG 1000, NBC TG 1001 e 1002.
- [x] ITG 1000, itens 1–10: critérios gerais de porte contábil e ressalvas para selecionar referencial; decisão final do referencial permanece com o Supervisor.
- [x] CPC: catálogo de pronunciamentos usado como índice; título CPC não tratado isoladamente como fundamento normativo obrigatório.
- [x] Receita Federal/SPED: distinção entre resultado contábil e lucro/base fiscal; arquitetura da ECF, e-Lalur e e-Lacs.
- [x] Planalto: LC 123, LC 214, RIR/2018, Lei 6.404 compilada e CLT como fontes localizadas. Conteúdo detalhado só foi registrado quando resumido no catálogo.
- [x] eSocial: MOS/leiautes e evolução por versão; materiais com data futura visíveis no índice foram excluídos de afirmações vigentes.
- [ ] Portal NF-e: fonte localizada, mas acesso automatizado ao índice redirecionou; versão corrente do MOC não confirmada.
- [ ] Fontes estaduais e municipais: jurisdição não foi informada e nenhuma legislação local foi aplicada.

## Conteúdo e status

Inventário completo dos assuntos em `BASE_CONHECIMENTO_CONTABIL/cobertura.json`. Estados agregados no primeiro catálogo: verifique este inventário por assunto; `VERIFICADO` é limitado ao resumo e à evidência do registro, `PARCIAL` não permite uso como fundamento suficiente, `PENDENTE` requer pesquisa e `NAO_VERIFICADO` indica que a fonte/jurisdição não foi consultada.

- [x] ITG 2000 (R1), NBC TG 1000, NBC TG 1001, NBC TG 1002 e ITG 1000 catalogadas; critérios gerais de enquadramento não confundem porte, regime tributário e referencial.
- [x] IRPJ/CSLL: resultado contábil separado da base fiscal; ajustes fiscais dependem de norma e caso.
- [x] e-Lalur/e-Lacs e ECF indexados por período/leiaute.
- [x] Reforma tributária IBS/CBS/IS registrada como parcialmente verificada, sem alíquotas universais.
- [x] Agentes Financeiro, DP, Fiscal, Conciliação, Coordenador/Documentos e Contabilidade têm temas e lacunas no inventário.
- [ ] Critérios detalhados para a maioria dos temas substantivos, versões por competência, temas estaduais/municipais e exemplos ilustrativos ainda precisam ser pesquisados.

## Testes e regressão

- [x] Testes unitários da estrutura, campos, referências, consulta por filtros, vigência, aplicabilidade, referencial, conflito, isolamento e não autorização automática: 10/10.
- [x] Gate completo: 76/76 baterias aprovadas, 0 falhas; estado operacional intocado: SIM; `GATE DE RELEASE: APROVADO`.
- [x] Regressões do projeto: incluídas no gate completo (76 baterias).
- [x] Runtime REAL não foi alterado; nenhum fechamento executado; empresa piloto arquivada e conhecimento histórico arquivado não foram acessados/alterados.
- [x] Nenhum commit ou push.

## Revisão

- [ ] Revisão e aceite do Supervisor.
- [x] Etapa 04 não iniciada.

Motivo do bloqueio da etapa: a maior parte dos critérios técnicos por tema/referencial ainda não foi pesquisada e verificada em texto oficial e por competência; legislação estadual/municipal depende de jurisdição não informada; a versão corrente do MOC NF-e não pôde ser confirmada pelo acesso automatizado. Não usar itens parciais, pendentes ou não verificados para decisões críticas.

Próxima ação: aguardar revisão do Supervisor. Não iniciar a Etapa 04. Não usar registros `PARCIAL`, `PENDENTE` ou `NAO_VERIFICADO` como fundamento suficiente para decisão crítica.


## Complementação Etapa 03B (16/11/2026)

Gate da complementação Etapa 03B: 76/76 baterias aprovadas, zero falhas; estado operacional intocado. Inventário priorizado sem exclusão de tópicos em `BASE_CONHECIMENTO_CONTABIL/cobertura.json`; distribuição: P0 4 verificados, 32 parciais, 94 pendentes; P1 3 parciais, 19 pendentes; P2 5 não verificados, 1 pendente. Dezessete fichas estruturadas e dez respostas demonstrativas estão disponíveis em `fundamentos_p0.json` e `respostas_demonstrativas.json`. Foram estudados diretamente ITG 2000 (R1), ITG 1000, NBC TG 1001 e NBC TG 1002, nos dispositivos listados. Estudos substantivos de NBC TG 1000, conjunto completo, fiscal e DP permanecem parciais/pendentes. Ver `TESTES/ETAPA-03B-CHECKLIST.md`; a classificação permanece `ETAPA_03_BLOQUEADA`.


## Complementação departamental 03C — Agente Contábil

Vinte fundamentos CONT-01–CONT-20 foram fichados em `BASE_CONHECIMENTO_CONTABIL/fundamentos_p0.json`, mapeados às 17 fichas preservadas e tratados em referencial simplificado conforme aplicabilidade. Doze casos fictícios consultáveis foram adicionados em `casos_contabeis.json`. Fonte e dispositivo oficial, vigência, referencial, mensuração, evidência, limitações e erros comuns constam por fundamento. A transição TG26/TG51 foi mantida por competência. Conferir o checklist detalhado `TESTES/ETAPA-03C-CHECKLIST.md`; esta complementação contábil não declara toda a Etapa 03 concluída e não inicia 03D.


Resultado Etapa 03C / Agente Contábil: 20/20 fundamentos essenciais verificados no escopo documental declarado; 12 casos fictícios; 18 testes específicos aprovados; gate completo 76/76, zero falhas, estado operacional intocado. As especialidades e aplicação de normas completas permanecem explicitamente limitadas no checklist 03C; a Etapa 03 geral continua em complementação.

## Complementação departamental 03D — Agente Financeiro

- [x] Fundamentação consultiva FIN-01–FIN-20 e 15 casos inteiramente fictícios integrados à base consultável; ver `TESTES/ETAPA-03D-CHECKLIST.md`.
- [x] Critérios do motor, leitores, cardinalidade, tolerâncias e procedimento Financeiro v1.5 preservados como regras internas; motor não alterado.
- [x] A Etapa 03D foi avaliada e entregue no escopo delimitado; aguarda revisão/aceite do Supervisor.
- [ ] A Etapa 03 geral continua em complementação; Etapa 03E não iniciada.

Resultado de gate da complementação 03D: 77/77 baterias aprovadas, zero falhas; estado operacional intocado. Ver checklist da 03D.

## Complementação departamental 03E — Agente Fiscal

- [x] Base consultável com FISC-01–FISC-25 e 20 casos fictícios; todos sem autorização de apuração/contabilização automática. Ver `TESTES/ETAPA-03E-CHECKLIST.md`.
- [x] Fichas mantêm separação de legislação, norma contábil e procedimento interno, e integram fundamentos CONT/FIN já existentes.
- [x] Status no escopo 03E: 5 VERIFICADO, 20 PARCIAL, 0 PENDENTE, 0 NAO_VERIFICADO; aplicação de todas depende de contexto da empresa/operação.
- [x] Parser Fiscal, adapters, contratos, intercâmbio, procedimentos, referências de empresa e rotinas de motor preservados.
- [x] Gate completo: 78/78 baterias aprovadas, zero falhas; estado operacional intocado. 03F não iniciada; revisão do Supervisor pendente.

Classificação técnica da Etapa 03E: ETAPA_03E_APROVADA no escopo delimitado; revisão do Supervisor pendente. Não iniciar a 03F.


## Complementação departamental 03F — Agente DP

- [x] 20 fichas DP-01–DP-20 e 15 casos fictícios consultáveis; sem cálculo de folha/rescisão ou contabilização automática.
- [x] Parser DP, adapters, contratos, procedimento e estado `STATUS_DP_CONTEXTUAL_V1` preservados.
- [x] Fontes eSocial/MOS, CFC, Planalto, RFB e MTE incorporadas; sem percentuais universais.
- [x] Consulta por assunto, referencial, competência, ID e caso; parcial bloqueia acesso que exige verificação.
- [x] Status: 3 VERIFICADO (DP-16/17/18, documentação técnica limitada), 17 PARCIAL. DP-01 e tratamentos trabalhistas substantivos dependem de estudo textual mais profundo e contexto empresarial.
- [x] Gate completo 03F: 79/79 baterias aprovadas, zero falhas; execução única via `.venv/bin/python -I TESTES/executar_gate.py`; estado operacional intocado.
- [x] Etapa 03 geral permanece em complementação; ressalvas FISC 03E (5 verificados/20 parciais) preservadas; 03G não iniciada.
- [x] Classificação técnica: ETAPA_03F_BLOQUEADA por insuficiência de fundamentos substantivamente verificados; gate 79/79 aprovado. Aguardar revisão do Supervisor.
