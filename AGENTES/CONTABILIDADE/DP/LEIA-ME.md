# Contabilidade/DP — propostas de competência da folha (SIMULAÇÃO)

Recebe o resultado `DP_LOCAL_V1` do DP e prepara propostas de lançamento para conferência do Supervisor.
Código local, sem modelos externos. Nada é aprovado, escriturado ou liberado para o Domínio.

```
.venv/Scripts/python.exe -I AGENTES/CONTABILIDADE/DP/ferramentas/propostas_dp.py --empresa <EMP> --competencia AAAA-MM
    --sol <SOL> --dp <resultado.json do DP> --saida <dir>
```
Códigos: 0 = `<saida>/resultado.json` gravado (pode ter INCOMPLETOS); 1 = falha real com "ERRO: ..." no stderr e nada
gravado (resultado do DP de outra empresa/SOL/competência ou contrato diferente, `REGRAS-DP.json` inválido, CADASTRO.md
ausente, entrada ilegível); 2 = empresa/competência inválidas.

## Fontes da empresa (somente da empresa selecionada)
- `CLIENTES/<EMP>/REGRAS-DP.json` (REFERENCIAS_DP_V1): `{contrato, empresa, cnpj, competencia_desde, [competencia_ate],
  referencias{EVENTO:{debito, credito, fonte}}}`. Inválido (JSON ilegível, contrato, empresa, CNPJ fora do CADASTRO.md,
  `referencias` não objeto, vigência fora de AAAA-MM) → erro (etapa FALHOU). Ausente → todas as propostas INCOMPLETAS com
  "Referências contábeis de DP não definidas pelo Supervisor" (não é falha). Sem `competencia_desde`, ainda não vigente ou
  encerrada → INCOMPLETAS. Evento ausente/malformado → aquela proposta INCOMPLETA.
- `PLANO-DE-CONTAS/PLANO-DE-CONTAS.md`, seção "Contas utilizadas" (Código reduzido, Descrição, Grupo, Tipo).
- `CADASTRO.md`: CNPJs e "Contas bancárias" (coluna Conta contábil) — contas bancárias não podem ser contrapartida.

## Validação por lançamento (qualquer falha → INCOMPLETO, nunca escolhe outra conta)
Conta inexistente, não ANALITICA, grupo incompatível (FOLHA_PROVENTOS/ENCARGO_*/PROVISAO_*: débito DESPESA|CUSTO,
crédito PASSIVO; RETENCAO_*: débito e crédito PASSIVO), conta bancária, débito = crédito, referência sem `fonte`,
plano ausente, fato sem documento elegível correspondente (sha256), competência ≠ SOL, valor ≤ 0 ou fora do formato,
mesmo documento+evento repetido. LIQUIDO_A_PAGAR é informativo e não gera lançamento (pagamento é Bancos/extrato).

## Saída `CONTABILIDADE_DP_V1`
`{contrato, agente:'CONTABILIDADE/DP', empresa, competencia, sol, modo:'SIMULACAO', origem_dp_sha256 (sha256 do arquivo
de entrada), lancamentos[], documentos_nao_aproveitados[{documento, arquivo, pendencias}], pendencias[{lancamento,
descricao}], resumo{propostos, incompletos, valor_propostos}, limites[]}`.
Lançamento: `{id ('DP-'+documento+'-'+evento), evento, natureza (RECONHECIMENTO|RETENCAO|ENCARGO|PROVISAO),
status PROPOSTO_PARA_CONFERENCIA|INCOMPLETO, competencia, valor ('1234.56'), debito{codigo,descricao}|null,
credito{...}|null, documento, arquivo, sha256, origem{fato, ...origem do fato}, regra{fonte}, pendencias[],
aprovado:false, escriturado:false}`.

Testes: `TESTES/DP/testar_dp.py`.
