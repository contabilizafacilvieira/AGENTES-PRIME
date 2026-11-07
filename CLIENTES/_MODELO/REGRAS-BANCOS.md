# REGRAS DE LANÇAMENTOS BANCÁRIOS - <EMPRESA>
Regras ESPECÍFICAS desta empresa para Contabilidade/Bancos. O procedimento geral fica em
AGENTES/CONTABILIDADE/BANCOS/PROCEDIMENTO.md e não é alterado por regras de cliente.

- Somente regras VALIDADAS são usadas. PROPOSTA não é usada; REVOGADA fica como histórico.
- Condições: `chave=valor; chave=valor` com chaves `direcao`, `tipo_banco`, `historico_contem`, `favorecido_cnpj`, `suporte`,
  `conta`, `obrigacao_contabilizada`. Todas precisam ser atendidas.
- Tipo: `LIQUIDACAO_OBRIGACAO`, `DESPESA`, `RECEBIMENTO` ou `RECEITA`. A conta do banco vem do CADASTRO.md.
- Contrapartida: código reduzido existente no PLANO-DE-CONTAS. Conta transitória/genérica só com regra aprovada.
- Origem: TREINAMENTO ou SUPERVISOR (com SOL e movimento de origem). Aprovação: frase exata
  `VALIDADO REGRA <EMPRESA> <RB-NNN>` e data. Mudança de regra = nova versão aprovada.

## Regras
| Regra | Versão | Condições | Tipo | Contrapartida | Exige suporte | Histórico | Origem | Situação | Aprovação |
|---|---|---|---|---|---|---|---|---|---|
