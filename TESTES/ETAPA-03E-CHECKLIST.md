# AGENTES PRIME — Etapa 03E: fundamentação do Agente Fiscal

Data das consultas: 16/11/2026. Escopo: conhecimento técnico consultivo para documentos e fatos fiscais. A classificação abaixo limita-se ao que a ficha declara; não significa aptidão para apurar toda operação nem conclusão sobre qualquer empresa. Etapas 01 e 02 aprovadas; 03C e 03D aprovadas nos escopos delimitados conforme Supervisor. Etapa 03 geral continua em complementação.

## Preservação

- [x] Repositório iniciado em `master`, HEAD `f084245`; working tree já continha alterações dos estágios anteriores, preservadas.
- [x] Mecanismo Fiscal, `AGENTES/FISCAL/PROCEDIMENTO.md`, parser `analise_fiscal.py`, adapters, contratos, intercâmbio, referências históricas e conhecimento empresa piloto arquivada preservados.
- [x] Nenhum dado real usado; nenhum runtime REAL acessado/alterado; nenhum cadastro ou fechamento; nenhum documento enviado; sem commit/push.
- [x] Nenhuma regra específica de empresa copiada para a base geral.

## Fontes oficiais consultadas

- [x] Receita Federal: página IRPJ; IN RFB 1.700/2017; IN RFB 2.121/2022; EFD-Reinf/retenções; ECF Q&A Pessoa Jurídica 2025; orientação de importação e manual DUIMP.
- [x] SPED: página oficial ECF e seu papel de suporte aos dados de IRPJ/CSLL e e-Lalur/e-Lacs.
- [x] Planalto/legislação federal: LC 87/1996, LC 116/2003, LC 123/2006, Leis 10.637/2002 e 10.833/2003, LC 214/2025; na data consultada a RFB listava também LC 227/2026 e Decreto 12.955/2026 na legislação da reforma.
- [x] Portal nacional NF-e: MOC versão 7.0, visão geral e Anexo I de leiaute/validação.
- [x] Portal nacional NFS-e: documentação atual e FAQ versão 1.3 de 06/11/2026; assunto municipal depende de lei/local e competência.
- [ ] CONFAZ: página e atos específicos de CFOP/CST/CSOSN não foram individualizados; essas fichas permanecem PARCIAL e requerem consulta conforme operação/competência.
- [x] CFC/CPC: reutilizados CONT-01, 03, 04–11, 17–20 verificados na Etapa 03C para reconhecimento, evidência, estoque, apresentação e tributos sobre lucro; nenhuma norma contábil foi tratada como legislação fiscal.
- [ ] Legislação estadual e municipal por ente: PENDENTE por não haver UF/município/empresa-alvo, conforme limite explícito da etapa.

## Fichas fiscais: inventário (25 avaliados)

| ID | Fundamento | Fonte/dispositivo principal | Vigência/aplicabilidade | Status |
|---|---|---|---|---|
| FISC-01 | Documento fiscal e fato econômico | MOC NF-e 7.0, visão geral/Anexo I | Leiaute técnico; aplicação depende do documento/operação | VERIFICADO |
| FISC-02 | Notas fiscais de entrada | MOC 7.0 Anexo I; LC 87/1996 conforme hipótese | UF, regime, mercadoria e competência pendentes | PARCIAL |
| FISC-03 | Notas fiscais de saída | MOC 7.0 Anexo I; reconhecimento NBC depende de referencial | Reconhecimento não decorre só da emissão | VERIFICADO |
| FISC-04 | Notas fiscais de serviços | LC 116/2003, arts. 3º–4º/lista; FAQ NFS-e v1.3 | Município e competência dependentes | PARCIAL |
| FISC-05 | CFOP, CST, CSOSN e natureza | MOC 7.0 Anexo I; tabela/legislação correspondente | Fonte CONFAZ/ente por operação não individualizada | PARCIAL |
| FISC-06 | Cancelamentos e devoluções | MOC 7.0/eventos; LC 87/1996 ou LC 116/2003 | Prazo, evento, tributo e UF/município dependentes | PARCIAL |
| FISC-07 | Receita versus emissão fiscal | NBC TG 1001, itens 23.1–23.8; NBC TG 1002, itens 23.1–23.7 | Referencial contábil confirmado e fatos do contrato | VERIFICADO |
| FISC-08 | Tributos próprios | IN 1.700/2017, IN 2.121/2022, LC 87/1996/116/2003, RIPI | Tributo/regime/operação/competência necessários | PARCIAL |
| FISC-09 | Tributos retidos | Lei 10.833/2003, arts. 30–36 em hipóteses próprias; EFD-Reinf | Responsável/natureza/regime necessários | PARCIAL |
| FISC-10 | Tributos recuperáveis | IN 2.121/2022; LC 87/1996 conforme hipótese | Destaque não prova crédito; condições pendentes | PARCIAL |
| FISC-11 | Tributos não recuperáveis | NBC TG 1001/1002 sobre custo; legislação própria | Classificação depende de direito fiscal e referencial | PARCIAL |
| FISC-12 | ICMS e ICMS-ST | LC 87/1996, arts. 2º–3º, 6º–12, 19–23 | UF, NCM, regime, convênio e competência | PARCIAL |
| FISC-13 | IPI | Decreto 7.212/2010/RIPI; TIPI | NCM/produto/operação/vigência pendentes | PARCIAL |
| FISC-14 | ISS | LC 116/2003, arts. 1º–3º/lista; FAQ NFS-e | Serviço e município necessários | PARCIAL |
| FISC-15 | PIS e COFINS | IN 2.121/2022; Leis 10.637/2002 e 10.833/2003 | Regime, produto, receita e transição necessários | PARCIAL |
| FISC-16 | IRRF, CSRF e INSS retido | Lei 10.833/2003 arts. 30–36; RIR/2018 art. 714 em hipótese; IN 2.110/2022 | Caso não autoriza generalização | PARCIAL |
| FISC-17 | Importação/aduana | Manual DUIMP aba Tributos; II/NCM/TEC e normas de cada tributo | DI/DUIMP, NCM, valor e operação necessários | PARCIAL |
| FISC-18 | Apuração, provisão e pagamento | IN 1.700/2017; EFD-Reinf FAQ itens 1.4–1.5; FIN-05/13 e CONT-19 | Fluxo declaratório documentado; reconhecimento e pagamento não concluídos universalmente | PARCIAL |
| FISC-19 | Obrigações acessórias/SPED | IN RFB 2.004/2021; leiaute ECF e EFD-Reinf por versão | Obrigação e competência definem versão aplicável | VERIFICADO |
| FISC-20 | Simples, Presumido, Real | LC 123/2006; IN 1.700/2017; RIR/2018 | Elegibilidade e opção dependem do contribuinte | PARCIAL |
| FISC-21 | IRPJ | IN 1.700/2017, arts. 27–29 conforme regime; RIR/2018 | Base requer ajustes, regime e competência | PARCIAL |
| FISC-22 | CSLL | IN 1.700/2017, arts. 27–30 conforme versão/regime | Alterações e perfil do contribuinte exigem revisão | PARCIAL |
| FISC-23 | ECF/e-Lalur/e-Lacs | IN 2.004/2021; IN 1.700/2017; Manual/Q&A ECF 2025 | Ajuste concreto exige lei e evidência próprias | VERIFICADO |
| FISC-24 | Reforma: IBS/CBS/IS | LC 214/2025, LC 227/2026, Decreto 12.955/2026 listados pela RFB | Transição/regulamentação por competência | PARCIAL |
| FISC-25 | Conciliação fiscal-contábil | ITG 2000 (R1), itens 5–8; fontes por declaração/jurisdição ainda devem ser selecionadas | Procedimento de controle não é exigência geral comprovada | PARCIAL |

**Status:** 5 VERIFICADO; 20 PARCIAL; 0 PENDENTE; 0 NAO_VERIFICADO. Todas as fichas usam `STATUS_APLICABILIDADE=DEPENDENTE_DE_CONTEXTO`; VERIFICADO significa o fundamento geral limitado descrito, nunca autorização para aplicação fiscal ou contabilização automática.

## Consultas demonstrativas

- [x] 20 casos integralmente fictícios, FISC-CASO-01–20, com fato, evidência necessária, fonte/dispositivo, vigência, aplicabilidade, tratamento conceitual, riscos, limites, responsável e aprovação humana.
- [x] Abrangidos créditos potenciais sem presumir direito, emissão versus reconhecimento, retenção, apuração versus provisão/pagamento, resultado contábil versus base fiscal, LALUR, importação, divergências e transição da reforma.
- [x] Nenhum caso gera lançamento, cálculo ou apuração automática.

## Consulta pelo código e testes

- [x] API de consulta em `BASE_CONHECIMENTO_CONTABIL/consulta.py`: por ID, assunto, regime, competência, UF, município, tipo de operação, status e por caso. Contexto ausente aparece como alerta; filtros fornecidos não significam regra local verificada.
- [x] Fontes gerais adicionadas ao catálogo `fontes.json`.
- [x] Teste 03E: 6/6; regressões de consulta geral e etapas 03C/03D: 24/24; total dessas três baterias: 30/30.
- [x] Gate completo: 78/78 baterias aprovadas, zero falhas; estado operacional intocado. Execução única final usa Python 3.12.16; saídas temporárias locais, não versionadas.

## Limitações explícitas e próxima ação

- CFOP/CST/CSOSN, regras de CONFAZ e tabelas por estado não foram individualizadas, pois não havia operação/UF definida. Próxima ação é pesquisa por hipótese concreta.
- ISS, NFS-e e retenções locais dependem do município e de sua legislação vigente; nenhum município foi configurado.
- Crédito, ICMS-ST, IPI, PIS/Cofins, IRRF/CSRF/INSS, importação, Simples/Presumido/Real e estimativas fiscais são PARCIAIS e exigem cadastro legal da empresa, competência, documentos e revisão técnica.
- A fonte oficial pode consolidar atos em datas diferentes. A ficha registra consulta 16/11/2026 e exige reconferência da redação e efeitos temporais antes de qualquer uso.
- Referência normativa identificada não substitui prova do fato, validação de autenticidade de documento, apuração ou decisão do Supervisor.

## Resultado e entrega

- [x] Motor Fiscal, adapters, contratos e intercâmbio preservados; nenhuma funcionalidade anterior removida.
- [x] Runtime REAL, dados reais e arquivos históricos arquivados preservados sem acesso/modificação nesta etapa.
- [x] Gate completo: 78/78 baterias aprovadas, zero falhas; estado operacional intocado.
- [x] Classificação técnica no escopo delimitado: ETAPA_03E_APROVADA, aguardando revisão do Supervisor. Não iniciar Etapa 03F até revisão.
