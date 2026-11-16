# DP — conferência documental local da folha

## Responsabilidade

Receber o pacote de Documentos da área DP, ler os demonstrativos de folha nos layouts documentados e entregar fatos,
fontes e pendências à Contabilidade/DP. Execução local em SIMULAÇÃO, sem Claude, OpenAI ou outros modelos.
Este módulo não calcula folha, alíquotas, bases, encargos ou provisões: apenas confere, por igualdade exata (Decimal,
sem tolerância), as somas declaradas no próprio documento.

Ferramenta: `AGENTES/DP/ferramentas/analise_dp.py`
```
.venv/Scripts/python.exe -I AGENTES/DP/ferramentas/analise_dp.py --empresa <EMP> --competencia AAAA-MM --sol <SOL>
    --pasta <pasta do lote> --documentos-local <documentos-local.json> --extracao-local <extracao-local.json> --saida <dir>
```
Lê o pacote com `receber_pacote_local(..., area='DP', exigir_hash=True)` (hash da extração, originais e inventário
conferidos; pacote sem registro da área DP é recusado) e os CNPJs da empresa em `CLIENTES/<EMP>/CADASTRO.md`.
Códigos de saída: 0 = `resultado.json` gravado (pode conter pendências); 1 = pacote recusado/erro de leitura (mensagem
"ERRO: ..." no stderr, nenhum resultado gravado); 2 = empresa/competência inválidas.

## Layouts aceitos (texto .txt UTF-8, CSV `;` ou planilha com as mesmas linhas; valores BR 1.234,56)

- RESUMO DA FOLHA DE PAGAMENTO → `RESUMO_FOLHA`: tabela `RUBRICA;TIPO;VALOR` (TIPO PROVENTO|DESCONTO);
  totais `TOTAL DE PROVENTOS`, `TOTAL DE DESCONTOS`, `LIQUIDO A PAGAR`. Confere soma de proventos, soma de descontos e
  proventos − descontos = líquido. Desconto com "INSS" → RETENCAO_INSS; com "IRRF" → RETENCAO_IRRF; outro desconto →
  pendência (sem evento, documento não aproveitado).
- RESUMO DE ENCARGOS DA FOLHA → `ENCARGOS_FOLHA`: tabela `ENCARGO;BASE;VALOR` (INSS EMPRESA, INSS RAT E TERCEIROS,
  FGTS); totais `TOTAL INSS A RECOLHER` = INSS EMPRESA + INSS RAT E TERCEIROS + INSS retido na folha da mesma
  competência/CNPJ, e `TOTAL FGTS A RECOLHER` = linha FGTS. Folha ausente, pendente ou não única → pendência.
  Base é informativa (registrada em `base_informada`); nenhuma alíquota é calculada.
- DEMONSTRATIVO DE PROVISOES (DE FERIAS E 13 SALARIO) → `PROVISOES`: tabela `PROVISAO;VALOR DO MES` (FERIAS…,
  13 SALARIO); `TOTAL DAS PROVISOES` = soma. `ENCARGOS SOBRE PROVISOES: NAO INFORMADOS` vira limite (não calculado);
  valor informado vira pendência até o Supervisor definir evento/regra.

Todos exigem rótulos `CNPJ`, `COMPETENCIA` (MM/AAAA) e `NUMERO DO DOCUMENTO`; `EMPRESA` é opcional. Rótulo repetido
com valores divergentes, linha fora do layout, cabeçalho ausente, tabela vazia ou mais de um demonstrativo no
arquivo → pendência. Outros layouts → `NAO_RECONHECIDO` com pendência (não inferir pelo nome do arquivo).

## Resumo mensal da folha do Domínio (rotina CAIXINHA)

`ferramentas/resumo_folha_dominio.py` lê o relatório emitido pelo Domínio (rubricas por descrição; somas exatas = totais declarados;
proventos − descontos = líquido), separa pró-labore bruto, INSS, IRRF, outros descontos e líquido; folha mista não separa o líquido
do pró-labore (pendência). Etapa `CAIXINHA_DP` (`ferramentas/caixinha_dp.py`) só no fluxo CONCILIACAO_CAIXINHA; os layouts
documentados acima continuam com `analise_dp.py`.

## Pendências que impedem o aproveitamento

Documento com qualquer pendência não é elegível e não gera fatos (nenhum fato parcial):
leitura diferente de `EXTRAIDO_*`, PDF protegido, `requer_conferencia_ocr`, `leitura_incompleta`; competência ≠ SOL;
CNPJ fora do cadastro da empresa; totais incoerentes; rubrica/encargo/provisão desconhecidos; layout não reconhecido;
duplicidade — cópia idêntica (mesmo sha256) ou mesmo `NUMERO DO DOCUMENTO` com conteúdo diferente: **nenhuma** das
versões é aproveitada; mais de um demonstrativo do mesmo tipo/CNPJ/competência com números diferentes também bloqueia.

## Resultado `DP_LOCAL_V1` (`<saida>/resultado.json`)

`{contrato, agente:'DP', empresa, competencia, sol, modo:'SIMULACAO', documentos[], fatos[], pendencias[], limites[],
resumo{documentos, aptos, fatos, pendencias}}`.
- documento: `{id ('DPD-'+12 hex de sha256(arquivo|sha256)), arquivo, sha256, tipo, competencia, cnpj, numero,
  rubricas[], totais{rótulo: '1234.56'}, pendencias[], elegivel_contabilidade}`.
- fato (somente de documento elegível e valor > 0): `{id (<documento>-<EVENTO>), evento, natureza, valor ('1234.56'),
  competencia, documento, arquivo, sha256, origem{tipo_documento, numero, rubricas|rotulo}}`.
  Eventos/naturezas: FOLHA_PROVENTOS (RECONHECIMENTO), RETENCAO_INSS/RETENCAO_IRRF (RETENCAO), ENCARGO_INSS_EMPRESA
  (INSS EMPRESA + RAT E TERCEIROS) e ENCARGO_FGTS (ENCARGO), PROVISAO_FERIAS/PROVISAO_13 (PROVISAO), LIQUIDO_A_PAGAR
  (OBRIGACAO_A_PAGAR, `origem.gera_lancamento=false`: informativo para Financeiro/Conciliação).
- pendência: `{documento, arquivo, descricao}`; pacote sem documentos de DP gera pendência com `documento: null`.

Pagamento de salários e encargos é fato do Financeiro (extrato), nunca do DP. Nada é aprovado ou escriturado.
Testes: `TESTES/DP/testar_dp.py` (fictícios, empresa criada só em diretório temporário).
