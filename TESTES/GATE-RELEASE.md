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

## Baterias ATIVAS (56)

| Área | Baterias |
|---|---|
| Governança / Registro | `GOVERNANCA/testar_governanca_regras.py`, `REGISTRO/testar_concorrencia_registro.py` (C-01..06, REG-ATOMIC-01..06) |
| Extrator, interface do extrator e Guarda | `T004/testar_extrator.py`, `T004/testar_interface.py`, `T004/testar_guarda.py` |
| Coordenador | `COORD/testar_coordenador.py` |
| API local / Segurança | `API/testar_api.py` (127.0.0.1, token, Host, origem, upload, limites) |
| Reprocessamento auditado | `API/testar_ciclo_reprocessamento.py` (ciclo de vida da tentativa: PREPARADA → EM_EXECUCAO → CONCLUIDA/BLOQUEADA/FALHOU, vínculo explícito das execuções, idempotência) |
| Documentos | `LOCAL/testar_pdf_local.py`, `testar_triagem_documentos.py`, `testar_salvaguardas_documentos.py`, `testar_pacotes_areas.py`, `testar_encaminhamento_automatico.py`, `testar_classificacao_extrato.py` (extrato pelo conteúdo; nome do arquivo não decide) |
| Cadastro | `LOCAL/testar_local.py`, `testar_plano_dominio.py`, `testar_metodo_empresa.py`, `testar_lixeira.py`, `testar_revisao_piloto.py` |
| Financeiro | `LOCAL/testar_extrato_santander.py`, `testar_confronto_suportes.py`, `testar_adiantamentos.py`, `testar_financeiro_percurso.py`, `FINANCEIRO/testar_correcoes_fluxo.py`, `FINANCEIRO/testar_financeiro.py`, `FINANCEIRO/testar_normalizador_financeiro.py` (Normalizador Financeiro: planilha → contrato comum), `FINANCEIRO/testar_integracao_normalizador.py` (relatório financeiro como fonte AUXILIAR do Financeiro), `FINANCEIRO/testar_normalizador_bancario.py` (Normalizador Bancário: contrato comum, adaptador Santander Extrato Consolidado PJ, aritmética e saldos diários), `FINANCEIRO/testar_integracao_bancaria.py` (extrato pelo contrato comum no Financeiro; fonte bancária × auxiliar) |
| Fiscal | `FISCAL/testar_fiscal.py`, `testar_salvaguardas_fiscais.py`, `testar_coordenador_fiscal.py`, `testar_fluxo_fiscal.py` |
| DP / Conciliação / Exportação | `DP/testar_dp.py`, `CONCILIACAO/testar_conciliacao.py`, `EXPORTACAO/testar_exportacao_dominio.py` |
| Base inicial e árvore do plano | `BASE-INICIAL/testar_base_inicial.py`, `BASE-INICIAL/testar_percurso_base_inicial.py`, `BASE-INICIAL/testar_plano_hierarquia.py` (HIER, GROUP, BOOK, BOOK-SEV, DUP, reanálise) |
| Saídas e percursos | `AMOSTRA-COMPLETA/testar_saidas_exclusao.py`, `AMOSTRA-COMPLETA/testar_percurso_completo.py`, `LOCAL/testar_fluxo_local.py` |
| Escritório Virtual | `ESCRITORIO/testar_mapa.js`, `testar_percurso_mapa.js`, `testar_aprovacao_mapa.js`, `testar_auditoria_mapa.js`, `testar_ciclo_solicitacao.js`, `testar_estado_recentes.py`, `testar_escritorio.py`, `testar_operacao_escritorio.py`, `testar_acompanhamento_navegador.py`, `testar_auditoria_navegador.py`, `testar_percurso_navegador.py`, `testar_interface_api_real.py` |
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
