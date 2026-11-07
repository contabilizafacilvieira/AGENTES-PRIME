# Contabilidade/Fiscal

Recebe `FISCAL_LOCAL_V1` e prepara propostas de competência em SIMULAÇÃO, sem movimentação bancária ou escrituração.
Referências: `CLIENTES/<EMPRESA>/REGRAS-FISCAIS.json`; exige identidade/CNPJ, vigência, origem e contas analíticas de grupo compatível.
Guia não vira nova despesa/provisão. Retenções sem composição e notas tomadas sem natureza permanecem incompletas.
Salvaguardas (03/11/2026): país estrangeiro do tomador por lista explícita e sem conflito com CNPJ/identificador;
tributo sobre receita só debita conta de RECEITA redutora ("(-)" no plano ou `conta_redutora_receita` documentada);
fim de vigência (`competencia_ate`) respeitado e sua ausência registrada em `limites`; propostas repetidas do mesmo fato ficam incompletas.
Propostas não dispensam conferência humana nem substituem a Conciliação independente.

Procedimento e limites completos: `AGENTES/FISCAL/PROCEDIMENTO.md`.
