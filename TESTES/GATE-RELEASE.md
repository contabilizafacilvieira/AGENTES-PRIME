# Gate de release — AGENTES PRIME v1.0.0-interno

Comando único (a partir da raiz `AGENTES-PRIME`; pode rodar com a API operacional no ar):

```
.venv\Scripts\python.exe -I TESTES\executar_gate.py
```

Resultado esperado: todas as baterias `PASSOU`, "Estado operacional ... intocado: SIM" e `GATE DE RELEASE: APROVADO`.
Para rodar só algumas áreas: `... executar_gate.py FISCAL LOCAL`.

## Regras do gate

- **Isolamento**: toda bateria roda em ambiente temporário (CLIENTES, registro, ordem ativa, runtime, LIBERADOS e LOCALAPPDATA
  próprios). Empresas de teste são FICTÍCIAS (`TESTES/FIXTURES-FICTICIAS/`, `TESTES/FINANCEIRO/FIXTURE-EMPRESA-DEMO/`, amostras e
  geradores). O gate compara o estado operacional antes e depois; qualquer diferença reprova o release.
- O guarda é testado por uma CÓPIA dele numa raiz temporária (`TESTES/ambiente_isolado.py`), sem alterar o código do guarda.
- Nenhuma regra de negócio foi afrouxada para um teste passar: fixtures antigas foram atualizadas para o contrato vigente.
- Leituras de referências reais (STATE-BANK) ficam desligadas por padrão; só com `AGENTES_PRIME_TESTE_REFERENCIAS_REAIS=1`.

## Validação manual (v1.7.0-interno)

A Central de Revisão do Supervisor foi validada por teste manual do fluxo de demonstração, além das baterias automatizadas.

## Baterias ATIVAS (73)

| Área | Baterias |
|---|---|
| Governança / Registro | `GOVERNANCA/testar_governanca_regras.py`, `REGISTRO/testar_concorrencia_registro.py` (C-01..06, REG-ATOMIC-01..06) |
| Extrator, interface do extrator e Guarda | `T004/testar_extrator.py`, `T004/testar_interface.py`, `T004/testar_guarda.py` |
| Coordenador | `COORD/testar_coordenador.py` |
| API local / Segurança | `API/testar_api.py` (127.0.0.1, token, Host, origem, upload, limites), `API/testar_central_revisao_api.py` (Central de Revisão: rotas, segurança, estado obsoleto, lote, isolamento por SOL, demonstração isolada, CR-API-01..20) |
| Reprocessamento auditado | `API/testar_ciclo_reprocessamento.py` (ciclo de vida da tentativa: PREPARADA → EM_EXECUCAO → CONCLUIDA/BLOQUEADA/FALHOU, vínculo explícito das execuções, idempotência), `API/testar_reconciliacao_legada.py` (reconciliação auditada de tentativa legada por evidência estrutural, LEG-01..15), `API/testar_documento_complementar.py` (documento complementar, manifesto/pacote efetivo imutável da tentativa e percurso integrado fictício até a Central, DOC-COMP-01..30 e INT-01..11), `API/testar_classificacao_snapshot.py` (classificação histórica × vigente no pacote da tentativa; rótulo antigo nunca herdado; ambíguo/erro fail-closed, CLASS-SNAPSHOT-01..10), `API/testar_checkpoint_financeiro.py` (checkpoint após o Financeiro e proteção da retomada de rota sem tentativa ativa, CHECK-FIN-01..20, ROTA-SEG-01..15) |
| Fechamento completo / multiempresa | `API/testar_previa_fechamento.py` (mini fechamento fictício completo: upload único que só classifica, "Preparar fechamento", Fiscal → DP → Financeiro → checkpoint → Contábil → Conciliação, prévia por departamento, conciliação do balanço book × balancete × razão, impostos, intercâmbio com candidatos, proveniência, adapters/layout novo, fail-closed e ambiente, FECH-01..28), `API/testar_multiempresa.py` (duas empresas fictícias na mesma competência: documento, regra, consulta entre áreas, balancete, decisão, tentativa, pendência e falha nunca cruzam empresas, MULTI-01..15 + MULTI-ISO) |
| Documentos | `LOCAL/testar_pdf_local.py`, `testar_triagem_documentos.py`, `testar_salvaguardas_documentos.py`, `testar_pacotes_areas.py`, `testar_encaminhamento_automatico.py`, `testar_classificacao_extrato.py` (extrato pelo conteúdo; nome do arquivo não decide) |
| Cadastro | `LOCAL/testar_local.py`, `testar_plano_dominio.py`, `testar_metodo_empresa.py`, `testar_lixeira.py`, `testar_revisao_piloto.py` |
| Financeiro | `LOCAL/testar_extrato_santander.py`, `testar_confronto_suportes.py`, `testar_adiantamentos.py`, `testar_financeiro_percurso.py`, `FINANCEIRO/testar_correcoes_fluxo.py`, `FINANCEIRO/testar_financeiro.py`, `FINANCEIRO/testar_normalizador_financeiro.py` (Normalizador Financeiro: planilha → contrato comum), `FINANCEIRO/testar_integracao_normalizador.py` (relatório financeiro como fonte AUXILIAR do Financeiro), `FINANCEIRO/testar_normalizador_bancario.py` (Normalizador Bancário: contrato comum, adaptador Santander Extrato Consolidado PJ, aritmética e saldos diários), `FINANCEIRO/testar_integracao_bancaria.py` (extrato pelo contrato comum no Financeiro; fonte bancária × auxiliar; conciliação no Financeiro e fail-closed), `FINANCEIRO/testar_conciliador_financeiro.py` (motor de conciliação banco × relatório, MATCH-01..40), `FINANCEIRO/testar_decisoes_supervisor.py` (decisões do Supervisor em camada separada, SUP-01..30, e regressão da POLÍTICA V1 publicada em v1.6.0-interno), `FINANCEIRO/testar_associacao_manual.py` (associação manual assistida pelo Supervisor para NÃO CONCILIADO, MANUAL-01..30, BUSCA-01..10, cenário 1×4; motor inalterado), `FINANCEIRO/testar_ambiguo_parcial.py` (ambiguidade parcialmente resolvida e visibilidade de todos os bloqueios, AMB-PARCIAL-01..20, BLOCK-VIS-01..08) |
| Fiscal | `FISCAL/testar_fiscal.py`, `testar_salvaguardas_fiscais.py`, `testar_coordenador_fiscal.py`, `testar_fluxo_fiscal.py` |
| DP / Conciliação / Exportação | `DP/testar_dp.py`, `CONCILIACAO/testar_conciliacao.py`, `EXPORTACAO/testar_exportacao_dominio.py` |
| Base inicial e árvore do plano | `BASE-INICIAL/testar_base_inicial.py`, `BASE-INICIAL/testar_percurso_base_inicial.py`, `BASE-INICIAL/testar_plano_hierarquia.py` (HIER, GROUP, BOOK, BOOK-SEV, DUP, reanálise) |
| Saídas e percursos | `AMOSTRA-COMPLETA/testar_saidas_exclusao.py`, `AMOSTRA-COMPLETA/testar_percurso_completo.py`, `LOCAL/testar_fluxo_local.py` |
| Escritório Virtual | `ESCRITORIO/testar_mapa.js`, `testar_percurso_mapa.js`, `testar_aprovacao_mapa.js`, `testar_auditoria_mapa.js`, `testar_ciclo_solicitacao.js`, `testar_estado_recentes.py`, `testar_escritorio.py`, `testar_central_revisao_navegador.py` (Central de Revisão pela tela, UI-CR-01..18), `testar_associacao_manual_navegador.py` (associação manual pela tela, UI-MANUAL-01..12), `testar_ambiguo_parcial_navegador.py` (ambiguidade parcial e "Ver bloqueios" pela tela, UI-AMB-01..10), `testar_checkpoint_navegador.py` (parar após o Financeiro e continuar na mesma tentativa, UI-CK-01..10), `testar_previa_navegador.py` (faixa AMBIENTE REAL/DEMONSTRAÇÃO, aba "Prévia do fechamento" com os cinco departamentos, Preparar fechamento, checkpoint, pendências por departamento, proveniência e envio de vários documentos, UI-PF-01..13), `testar_documentos_sol_navegador.py` (documento complementar e reconciliação legada pela tela da SOL, UI-DOC-01..08), `testar_operacao_escritorio.py`, `testar_acompanhamento_navegador.py`, `testar_auditoria_navegador.py`, `testar_percurso_navegador.py`, `testar_interface_api_real.py` |
| Empresas / Base inicial (tela) / Isolamento | `ESCRITORIO/testar_interface_base_inicial.py`, `ESCRITORIO/testar_simplificacao_empresas.py` (exclusão lógica, isolamento entre empresas) |

## Baterias restauradas ou atualizadas nesta versão

| Bateria | Situação anterior | O que foi feito |
|---|---|---|
| `T004/testar_extrator.py`, `T004/testar_interface.py`, `T004/testar_guarda.py` | Abortavam: fixtures fictícias removidas de `CLIENTES/` (e o `KeyError: 'itens'` era só a fixture ausente) | Fixtures fictícias restauradas do histórico do Git em `TESTES/FIXTURES-FICTICIAS/` e copiadas para um CLIENTES temporário; guarda testado por cópia isolada |
| `COORD/testar_coordenador.py` | Abortava: exigia fixture removida e lia o cadastro de uma empresa REAL | Isolado; a empresa-piloto passou a ser um cadastro FICTÍCIO criado pelo teste (mesmo formato de autorização) |
| `API/testar_api.py`, `ESCRITORIO/testar_operacao_escritorio.py` | Abortavam: fixture removida; lista esperada citava empresas antigas | Isolados; lista esperada = empresas fictícias do ambiente do teste (autorizada, piloto e sem autorização) |
| `FINANCEIRO/testar_financeiro.py` | 9 falhas: regras bancárias "VALIDADA" sem confirmação estruturada; empresa criada no CLIENTES/ real | A cópia temporária recebe a confirmação ESTRUTURADA exigida pelo contrato vigente; CLIENTES/LIBERADOS isolados; espera da tela T-10 sem tempo fixo |
| `FISCAL/testar_fluxo_fiscal.py` | Esperava proposta sem política de data | Cenário válido do contrato vigente: referência e política de DATA com situação PROPOSTA, confirmadas pela frase exata (mesmo caminho da tela); isolado |
| `FINANCEIRO/testar_correcoes_fluxo.py`, `LOCAL/testar_fluxo_local.py` | Criavam empresa temporária no CLIENTES/ real | Isolados (CLIENTES e LIBERADOS temporários) |
| `FISCAL/testar_salvaguardas_fiscais.py` | Lia referências reais da STATE-BANK quando presentes | Leitura real só com autorização explícita (padrão: pulado) |
| `FINANCEIRO/testar_correcoes_fluxo.py` e demais baterias que leem o registro | Falha intermitente: `PermissionError` ao ler o `registro.json` temporário no instante em que o servidor de teste o substituía (`os.replace`, Windows) | Leitura pelo helper `ambiente_isolado.registro_isolado()` (repetição limitada só para violação de compartilhamento; JSON inválido e falha persistente continuam como erro); produção já gravava de forma atômica e não foi alterada |

## Baterias LEGADAS (fora do gate)

| Bateria | Motivo |
|---|---|
| `IMPORTACAO/testar_importacao.py` (+ `fixtures_reconhecimento.py`) | Importação VGROW DESATIVADA por decisão do Supervisor (05/11/2026): rotas 410, Coordenador recusa os comandos. Dependia do cadastro real da empresa. Mantida no repositório como histórico; o script sai com a mensagem "LEGADO". |
| `API/e2e_navegador.py` (execução direta) | Ponta a ponta com o executor Claude REAL (legado, sem fallback; tem custo). O arquivo continua usado como biblioteca de navegador pelas baterias ativas. |
| `T004/verificar_t004_6.py` | Verificador manual de transcrições do subagente (homologação T-004.6); não é bateria automática. |
