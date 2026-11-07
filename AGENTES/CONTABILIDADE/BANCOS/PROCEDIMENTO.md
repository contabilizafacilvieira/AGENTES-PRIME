# PROCEDIMENTO GERAL · CONTABILIDADE/BANCOS · versão 1.1 (01/11/2026)

Procedimento GERAL, válido para qualquer empresa. Regras específicas ficam em `CLIENTES/<EMPRESA>/REGRAS-BANCOS.md`.
Implementação: `ferramentas/lancamentos_bancarios.py` (código local, sem Claude). Mudança = nova versão aprovada.

## Papel
Especialista interno da Contabilidade: preparar a escrituração dos movimentos bancários conferidos pelo Financeiro.
SIMULAÇÃO com conferência humana; nada é liberado nem importado no Domínio.

## Fontes (somente da empresa selecionada)
- CADASTRO.md, seção "Contas bancárias": conta contábil de cada conta bancária.
- PLANO-DE-CONTAS/PLANO-DE-CONTAS.md: conta fora do plano nunca é usada. A coluna **Grupo** (ATIVO, PASSIVO,
  PATRIMONIO_LIQUIDO, RECEITA, DESPESA ou CUSTO) é definida pelo Supervisor; conta sem grupo não é usada como contrapartida.
- REGRAS-BANCOS.md: somente regras **VALIDADAS** (com origem, versão e aprovação).
- Uma condição `competencia_desde=AAAA-MM` restringe a regra à competência indicada e seguintes; não altera propostas ou lançamentos anteriores.
- O método em `CLIENTES/<EMPRESA>/MANUAL-FECHAMENTO.md` e `PERFIL-FECHAMENTO.json`, quando existente e correspondente ao CNPJ, é contexto de conferência. Não aprova regras, não substitui documentos atuais e não executa áreas futuras.
- Decisões do Supervisor registradas na SOL (valem só para o movimento decidido).

## Passos
1. Movimento com lançamento EFETIVAMENTE escriturado (registro "escriturados" do Coordenador, gravado só pela etapa futura
   de aprovação/liberação) → sem nova proposta. Proposta anterior em SIMULAÇÃO (desta ou de outra SOL) não bloqueia: a nova
   proposta é marcada como revisão (`revisao_de`: SOL e tentativa). Todo lançamento desta fase é `PROPOSTA_SIMULACAO`.
2. Transferência entre contas próprias com as duas pontas → UM lançamento (débito na conta de destino, crédito na de
   origem) ligado aos dois movimentos; sem a outra ponta → proposta INCOMPLETA com pendência.
3. Decisão do Supervisor para o caso (contrapartida) → usada só neste movimento, com origem registrada.
4. Regras VALIDADAS cujas condições são todas atendidas. Tipos:
   - `LIQUIDACAO_OBRIGACAO`: paga obrigação já reconhecida (débito no passivo, crédito no banco) — **não gera despesa**;
   - `DESPESA`: reconhece e paga no mesmo ato (débito na despesa, crédito no banco);
   - `RECEBIMENTO` / `RECEITA`: crédito no banco (débito no banco, crédito na contrapartida).
   Relação com `obrigacao_contabilizada=SIM` → regras de DESPESA desconsideradas (evita segunda despesa).
5. Compatibilidade da contrapartida (vale para regra e para decisão do caso; o Coordenador recusa antes de registrar e
   este agente confere de novo):

   | Natureza | Direção no extrato | Contrapartida | Grupo exigido |
   |---|---|---|---|
   | `LIQUIDACAO_OBRIGACAO` | saída (DEBITO) | débito | PASSIVO |
   | `DESPESA` | saída (DEBITO) | débito | DESPESA ou CUSTO |
   | `RECEBIMENTO` | entrada (CREDITO) | crédito | ATIVO (valor a receber), nunca a conta contábil de banco da empresa |
   | `RECEITA` | entrada (CREDITO) | crédito | RECEITA |

   Combinação incompatível → sem contrapartida, pendência "não é compatível". Grupo não definido → pendência "não pode
   ser verificada": o Supervisor define o grupo no plano. Sem conta compatível no plano, a decisão fica pendente de
   definição no cadastro; nenhuma classificação é presumida.
6. Sem regra, regras conflitantes, conta inexistente, suporte exigido ausente, ambiguidade ou divergência →
   lançamento **INCOMPLETO** com pendência. Nunca se inventa conta e nunca se usa conta transitória/genérica para "fechar"
   o lote (só com regra expressamente aprovada para a empresa).

### Ausência de suporte — orientação atual do Supervisor

A classificação automática em adiantamento a fornecedores ou de clientes foi removida.
Configurações sem_suporte antigas ficam preservadas como histórico, sem efeito na geração.
Regras automáticas dos tipos ADIANTAMENTO_FORNECEDOR/ADIANTAMENTO_CLIENTE não são aplicadas.
Sem regra válida ou decisão específica, a contrapartida fica pendente e a proposta INCOMPLETA.
O Supervisor ainda pode escolher adiantamento explicitamente para um movimento; essa decisão
não supre documento e não cria regra automática. Contas do plano e resultados anteriores são preservados.

O aprendizado por razão está removido. Regras por empresa e decisões dos casos permanecem rastreáveis.

## Adiantamento, dependências e leitura pendente
- Adiantamento (ADIANTAMENTO_FORNECEDOR / ADIANTAMENTO_CLIENTE) só por decisão específica do movimento e somente na conta indicada
  pelo Supervisor em CADASTRO.md, seção "Contas de adiantamento indicadas pelo Supervisor" (gravada pela tela Empresas). Outra conta,
  mesmo de grupo compatível, não é proposta. A falta de documento continua pendência: lançamento INCOMPLETO.
- `--areas`: documento do movimento que também foi destinado a outra área (ex.: nota ao Fiscal) cuja análise falhou ou não foi
  entregue torna a proposta dependente dessa área (código DEPENDE_AREA).
- Documento recebido com leitura pendente impede afirmar ausência de suporte quando a proposta depende de suporte (sem regra ou
  regra que exige documento); regra VALIDADA que dispensa suporte (ex.: tarifa) não é afetada.

## Saída
Cada lançamento: débito, crédito, valor, histórico, fato (reconhecimento × liquidação), origem (regra e versão ou
decisão), movimentos e documentos vinculados, status PROPOSTO/INCOMPLETO e pendências. Arquivo CSV de conferência
(SIMULAÇÃO). O TXT do Domínio não é gerado por Bancos: depois da aprovação do fechamento integral, a API gera o TXT (partida simples,
decisão de 04/11/2026, ainda não validada no Domínio) só para empresa fictícia.

## Ensino de regras
Correção do Supervisor em um caso → pode virar **PROPOSTA** de regra (origem: SOL e movimento). Só passa a valer com a
frase exata `VALIDADO REGRA <EMPRESA> <RB-NNN>`; a aprovação dispara nova tentativa da SOL. Nada vira regra em silêncio.
