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

## Limitações conhecidas
- CSV de extrato e relação somente no leiaute do projeto (sem mapeamento por banco); OFX sem saldo inicial não permite a
  verificação aritmética (aparece como "sem verificação aritmética").
- Campos de PDF/TXT (valor, data, favorecido, identificadores) lidos por rótulo no texto; layouts reais de bancos podem
  exigir novos rótulos. PDF escaneado e imagem não são lidos (sem OCR neste fluxo).
- Sem tolerância de valor ou data (nenhuma regra aprovada): pagamento com data diferente aparece como sugestão.
- Identificação de transferência própria depende de o histórico citar a outra conta.
