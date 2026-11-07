# REGRAS DE LANÇAMENTOS BANCÁRIOS - EMPRESA-DEMO-FINANCEIRO
> FICTÍCIO. As regras "VALIDADA" desta empresa de demonstração são exemplos de teste, sem aprovação real do Supervisor.

Somente regras VALIDADAS são usadas pela Contabilidade/Bancos (procedimento: AGENTES/CONTABILIDADE/BANCOS/PROCEDIMENTO.md).
- Condições: `chave=valor; chave=valor` com chaves `direcao`, `tipo_banco`, `historico_contem`, `favorecido_cnpj`, `suporte`,
  `conta`, `obrigacao_contabilizada`. Todas precisam ser atendidas.
- Tipo: `LIQUIDACAO_OBRIGACAO` (paga obrigação já reconhecida: débito no passivo, sem nova despesa), `DESPESA`
  (reconhece e paga no mesmo ato), `RECEBIMENTO`, `RECEITA`. A conta do banco vem do CADASTRO.md.
- Proposta nova entra como PROPOSTA e só é usada depois da frase exata `VALIDADO REGRA <EMPRESA> <RB-NNN>`.

## Regras
| Regra | Versão | Condições | Tipo | Contrapartida | Exige suporte | Histórico | Origem | Situação | Aprovação |
|---|---|---|---|---|---|---|---|---|---|
| RB-001 | 1 | direcao=DEBITO; favorecido_cnpj=22.222.222/0001-22; suporte=NOTA_FISCAL | LIQUIDACAO_OBRIGACAO | 2101 | SIM | PAGTO {documento} {favorecido} | DEMONSTRAÇÃO FICTÍCIA | VALIDADA | exemplo fictício (sem aprovação real) |
| RB-002 | 1 | direcao=DEBITO; suporte=GUIA | LIQUIDACAO_OBRIGACAO | 2102 | SIM | PAGTO {documento} | DEMONSTRAÇÃO FICTÍCIA | VALIDADA | exemplo fictício (sem aprovação real) |
| RB-003 | 1 | direcao=DEBITO; historico_contem=DARF | DESPESA | 4104 | SIM | IMPOSTO {documento} | DEMONSTRAÇÃO FICTÍCIA | VALIDADA | exemplo fictício (sem aprovação real) |
| RB-004 | 1 | direcao=DEBITO; tipo_banco=FEE | DESPESA | 4102 | NAO | TARIFA BANCARIA {data} | DEMONSTRAÇÃO FICTÍCIA | PROPOSTA | — |
| RB-005 | 1 | direcao=DEBITO; favorecido_cnpj=33.333.333/0001-33 | DESPESA | 9999 | SIM | SERVICOS {favorecido} | DEMONSTRAÇÃO FICTÍCIA (conta inexistente de propósito) | VALIDADA | exemplo fictício (sem aprovação real) |
| RB-006 | 1 | direcao=DEBITO; favorecido_cnpj=55.555.555/0001-55; suporte=NOTA_FISCAL | LIQUIDACAO_OBRIGACAO | 2101 | SIM | PAGTO {documento} {favorecido} | DEMONSTRAÇÃO FICTÍCIA | VALIDADA | exemplo fictício (sem aprovação real) |
| RB-007 | 1 | direcao=DEBITO; favorecido_cnpj=66.666.666/0001-66; suporte=NOTA_FISCAL | LIQUIDACAO_OBRIGACAO | 2101 | SIM | PAGTO {documento} {favorecido} | DEMONSTRAÇÃO FICTÍCIA | VALIDADA | exemplo fictício (sem aprovação real) |
