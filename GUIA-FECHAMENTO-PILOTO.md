# Fechamento completo supervisionado — guia do piloto (multiempresa)

A BRASIL-PROTEC-AGRO é o **primeiro piloto real**. O AGENTES PRIME é **multiempresa**: nada aqui é específico de um cliente.
Tudo roda em **SIMULAÇÃO**. Proposta não é lançamento, e nada vai ao Domínio sem a aprovação explícita do Supervisor.

## 1. Organização

```
SUPERVISOR
   ↓
COORDENADOR GERAL
   ↓
FISCAL · FINANCEIRO · CONTÁBIL · DP · CONCILIAÇÃO   (departamentos)
   ↓
agentes especializados (Documentos, normalizadores, Fiscal, DP, Financeiro, Contábil/bancos·fiscal·DP, Conciliação)
```

**FECHAMENTO não é departamento.** É o processo coordenado que consolida os cinco departamentos.

| Departamento | Responsável por | Recebe (exemplos) |
|---|---|---|
| Fiscal | NFs de entrada e saída, guias, apurações e retenções | NF-e/NFS-e, guias, demonstrativos de apuração |
| Financeiro | Extratos, relatório financeiro, pagamentos e recebimentos; conciliação **banco × financeiro** | extrato (fonte oficial), relatório financeiro (fonte auxiliar), comprovantes |
| Contábil | Propostas de lançamento, provisões, plano de contas, balancete e razão | balancete e razão do período; resultados de Fiscal, DP e Financeiro |
| DP | Folha, encargos (INSS, FGTS, IRRF), provisões de pessoal | resumo da folha, encargos, provisões |
| Conciliação | Book, composição das contas, validação do **balanço** (book × balancete × razão) | book, confirmações de saldo, saldos de abertura |

A conciliação bancária é função do **Financeiro**. A conciliação do balanço é do departamento **Conciliação**.

## 2. Passo a passo do fechamento

1. **Escritório Virtual → Nova solicitação → "Fechamento do mês".** Para uma SOL que já existe, use "Adicionar documentos ao fechamento".
2. Selecione **todos** os arquivos do mês de uma vez: NFs, extratos, relatório financeiro, book, balancete, razão, impostos/guias e folha.
3. O Agente de Documentos recebe os arquivos (staging, SHA-256, duplicidade, empresa, competência), classifica e distribui por departamento.
   **Nada executa.**
4. Na aba **"Prévia do fechamento"**, confira "Documentos recebidos — classificação por departamento".
   Cada documento mostra uma destas situações:
   - **Reconhecido · adapter existente**;
   - **Layout novo · adapter necessário**: aguardando o arquivo real para criar/validar o adapter;
   - **Não reconhecido · aguardando Supervisor**: o destino não é presumido.
5. Clique em **"Preparar fechamento"** (ou em "Reprocessar fechamento", se a SOL já tem tentativas) e deixe marcado **"parar após o Financeiro"**.
   O sistema congela os documentos numa tentativa e executa **Fiscal → DP → Financeiro**. Depois **PARA** (checkpoint 1).
6. Revise na prévia o Financeiro e as **consultas do Financeiro às outras áreas**: candidatos de Fiscal, DP, Contábil e Conciliação, com os critérios usados.
   Nenhum candidato é confirmado automaticamente.
7. Clique em **"Continuar para Contabilidade/Bancos"** e informe a justificativa.
   A mesma tentativa segue para **Contábil (bancos, fiscal, DP) → Conciliação**. O Financeiro não é repetido.
8. A prévia fica **"Prévia pronta para a revisão do Supervisor"** (checkpoint final). Ela mostra:
   - status por departamento;
   - decisões necessárias;
   - pendências (problema · impacto · o que fazer · responsável);
   - propostas contábeis;
   - impostos (obrigação, provisão proposta, pagamento identificado);
   - conciliação do balanço por conta.

   **Lançamentos efetivados: 0.**

### No ambiente real da BRASIL-PROTEC-AGRO

- **SOL-2026-000002 (competência 2026-09)**
  - Use "Adicionar documentos ao fechamento" (vários arquivos) e depois "Reprocessar fechamento".
  - A nova tentativa (0003) congela o original e os complementares. As decisões do Supervisor já registradas (43/43) continuam valendo.
- **Outra competência**
  - Abra uma solicitação nova com "Fechamento do mês".
- **Identificação do ambiente**
  - A faixa vermelha **AMBIENTE REAL** fica no topo. A demonstração mostra a faixa **DEMONSTRAÇÃO**.

## 3. Motor geral × adapter × regra da empresa

| Camada | O que é | Onde |
|---|---|---|
| Motor geral | Ingestão, SHA, classificação e roteamento, normalização, conciliação, checkpoints, auditoria, propostas, decisões, tentativas, pendências, prévia, intercâmbio | `API-LOCAL/documentos_local.py`, `previa_fechamento.py`, `intercambio.py`, `adaptadores_fechamento.py` (registro e contratos), Coordenador |
| Adapter | Tradução de um formato para um contrato normalizado. Compartilhável, sem dados | `adaptadores_fechamento.py` (balancete PDF em colunas / tabela, razão em tabela, book em planilha, obrigações a partir dos resultados de Fiscal/DP), normalizadores bancário e financeiro |
| Regra da empresa | Conhecimento do cliente (ex.: fornecedor X → conta Y). Vale **só** para a empresa | `CLIENTES/<EMPRESA>/REGRAS-*.json` / `REGRAS-BANCOS.md`, governadas pelo Supervisor |

**Contratos normalizados:**
- `BALANCETE_NORMALIZADO_V1`
- `RAZAO_CONTABIL_NORMALIZADO_V1`
- `BOOK_CONCILIACAO_CONTABIL_V1`
- `OBRIGACAO_TRIBUTARIA_NORMALIZADA_V1`
- `PUBLICACAO_INTERCAMBIO_V1`
- `PREVIA_FECHAMENTO_V1`

Os contratos `MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1` e `MOVIMENTOS_FINANCEIROS_NORMALIZADOS_V1` foram preservados.

### Novo layout real ("LAYOUT NOVO — ADAPTER NECESSÁRIO")

1. **Inspecionar** o arquivo real, só localmente: o real nunca vai para o Git nem para fixture.
2. **Escrever o adapter determinístico** em `adaptadores_fechamento.py` (ou no normalizador da área) e registrá-lo em `ADAPTERS`.
3. **Testar** com uma fixture **fictícia** de mesmo layout.
4. **Processar**: a prévia passa a mostrar "adapter existente".

Nenhum layout real foi inventado nesta versão.

## 4. Intercâmbio entre departamentos

`PRODUTOR → CONTRATO → camada de intercâmbio → CONSUMIDOR`. A camada lê somente resultados **registrados** pelo Coordenador e confere
o sha256 contra o registro. Cada item publicado leva proveniência: empresa, competência, SOL, departamento, documento, sha256, registro,
versão e status.

**O Financeiro consulta:**
- Fiscal: NFs, guias e apurações;
- DP: folha e encargos;
- Contábil: propostas e provisões;
- Conciliação: itens em aberto do book.

**A consulta gera candidatos, nunca confirmações:**
- O valor exato é obrigatório.
- Data e vencimento, número do documento, CNPJ, código do tributo e competência são critérios registrados.
- Nome da contraparte e nome do tributo valem só como apoio.
- Texto parecido sozinho nunca associa.

**Fato gerador ≠ liquidação.**

**Pendências cruzadas:** um pagamento com indício tributário sem obrigação vira pendência para o Fiscal (ou o DP). Um pagamento com
indício de folha sem obrigação vira pendência para o DP. A pendência fica com quem deve agir, não com quem detectou.

**Competências cruzadas:** por padrão, só a própria SOL é consultada. SOLs anteriores da **mesma** empresa só entram com política
explícita e aprovada em `CLIENTES/<EMP>/REGRAS-INTERCAMBIO.json`:

```json
{"contrato": "REGRAS_INTERCAMBIO_V1", "empresa": "<EMP>", "situacao": "APROVADA", "janela_meses": N}
```

## 5. Multiempresa (fail-closed)

- Toda consulta é feita no contexto (empresa, SOL).
- Resultado de outra empresa ou SOL nunca é usado.
- Registro adulterado não libera dados.
- Leitura de original fora da pasta da empresa é recusada.
- Regra copiada para outra empresa não vale lá.

O teste `TESTES/API/testar_multiempresa.py` (MULTI-01..15) prova isso com duas empresas fictícias na mesma competência, com os mesmos
bancos, valores e fornecedores.

## 6. Status por departamento (sem percentual)

| Status | Quando |
|---|---|
| EM PROCESSAMENTO | A etapa está executando |
| AGUARDANDO SUPERVISOR | Há checkpoint ou decisão pendente |
| NÃO INICIADO | Nenhuma etapa executada |
| COM PENDÊNCIAS | Há bloqueio ou atenção |
| CONCLUÍDO | Executou, sem pendência e sem decisão necessária |

Fórmula: `API-LOCAL/previa_fechamento.py`.

## 7. Dívida técnica e limites conhecidos

- **Nome histórico "Contabilidade/Bancos":** o nome continua no checkpoint e em rotas e tarefas internas (tarefa `CONTABILIDADE` = especialista de bancos).
  A interface nova (prévia) separa Financeiro, Contábil e Conciliação; o departamento de documentos contábeis é `CONTABIL`.
  Não houve renomeação destrutiva.
- **PagFor:** continua "Tipo a conferir" por decisão do Supervisor. Não é extrato e não tem adapter.
- **Ainda sem adapter, aguardando arquivo real:**
  - razão em PDF;
  - memória de impostos em planilha;
  - guias de folha (FGTS Digital/DCTFWeb);
  - layouts de folha diferentes dos documentados.

  O balancete em PDF usa o leitor de colunas da base inicial, e o book usa o leitor de planilhas da base inicial. Os dois serão
  validados com os arquivos reais.
- **Soma de vários itens para um pagamento:** ainda não entra como critério de candidato no intercâmbio. A associação manual da Central
  continua disponível.
- **Responsável esperado por divergência de conta:** é uma sugestão determinística pela descrição da conta. O Supervisor pode reatribuir.
