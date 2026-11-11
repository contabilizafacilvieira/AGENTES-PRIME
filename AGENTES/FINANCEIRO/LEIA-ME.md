# AGENTE FINANCEIRO

Status: **IMPLEMENTADO EM SIMULAÇÃO** (31/10/2026), somente para empresa fictícia. Conferência humana obrigatória.

- Papel: conferência das movimentações financeiras (extrato × relação × comprovantes × suportes). Não é conciliação
  contábil completa (a Conciliação independente é etapa futura).
- Execução: código local determinístico (`ferramentas/conferencia_financeira.py`), **sem chamar o Claude**; lê os
  documentos somente pelo extrator do Agente de Documentos.
- Acionado SOMENTE pelo Coordenador, depois da etapa de Documentos de uma SOL do fluxo `FINANCEIRO_BANCOS`. Devolve o
  resultado ao Coordenador, que o encaminha a Contabilidade/Bancos.
- Procedimento geral (versionado): `PROCEDIMENTO.md`. Regras específicas de cliente ficam em `CLIENTES/<EMPRESA>/`.
- Testes: `.venv/Scripts/python.exe -I TESTES/FINANCEIRO/testar_financeiro.py` (somente dados fictícios).

## Normalizador Financeiro (v1.2) e fonte auxiliar (Financeiro v1.3)
`ferramentas/normalizador_financeiro.py`: Documento extraído → adaptador → contrato comum
`MOVIMENTOS_FINANCEIROS_NORMALIZADOS_V1`. Adaptadores ficam registrados em `ADAPTADORES` (um por fonte; todos devolvem o
mesmo contrato). Nesta versão: `PLANILHA_FINANCEIRA_GENERICA` (relatório financeiro em planilha extraída, inclusive pela
leitura alternativa de XLSX com estilo inválido). Reconhecimento pelo cabeçalho e conteúdo, nunca pelo nome do arquivo;
valores em Decimal; campo ausente fica vazio e listado; linha duvidosa vira pendência (Problema / Impacto / O que fazer).
- v1.1: `data_competencia` (separada de vencimento/quitação), `situacao` (REALIZADO, EM_ABERTO, CANCELADO, INDETERMINADO;
  só valores exatos testados; célula vazia = AUSENTE, com pendência `SITUACAO_AUSENTE`), `contraparte` {nome, nome_fantasia, documento} só com o que existir. Linhas não realizadas
  ficam em `linhas_nao_realizadas`, nunca nos movimentos. "É Despesa" e "Valor Pago" são validação cruzada: divergência
  gera `DIVERGENCIA_NATUREZA` / `DIVERGENCIA_VALOR_PAGO` e a linha não entra (nada é corrigido em silêncio).
- Integração: documento classificado por Documentos como "Relatório financeiro de lançamentos" + `EXTRAIDO_PLANILHA` passa
  pelo normalizador em `Conferencia.carregar()`. O resultado ganha, sem alterar campos antigos: `fonte_bancaria`,
  `fonte_auxiliar_financeira` (relatórios, resumo, pendências, não realizadas) e `movimentos_financeiros_auxiliares`
  (marcados `FONTE_AUXILIAR_FINANCEIRA`). **Relatório financeiro NÃO é extrato**: não entra em `movimentos`, não conclui a
  conferência bancária e sem extrato utilizável o lote continua bloqueado. Não há conciliação nem lançamento a partir dele.
- Extrato bancário ainda não tem adaptador no normalizador (aguarda o extrato correto).
- Testes: `TESTES/FINANCEIRO/testar_normalizador_financeiro.py` e `testar_integracao_normalizador.py` (somente fictícios).

## Limitações conhecidas
- CSV de extrato e relação somente no leiaute do projeto (sem mapeamento por banco); OFX sem saldo inicial não permite a
  verificação aritmética (aparece como "sem verificação aritmética").
- Campos de PDF/TXT (valor, data, favorecido, identificadores) lidos por rótulo no texto; layouts reais de bancos podem
  exigir novos rótulos. PDF escaneado e imagem não são lidos (sem OCR neste fluxo).
- Sem tolerância de valor ou data (nenhuma regra aprovada): pagamento com data diferente aparece como sugestão.
- Identificação de transferência própria depende de o histórico citar a outra conta.
