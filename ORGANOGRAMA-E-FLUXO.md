# Organograma e fluxo do fechamento

Definição do Supervisor em 02/11/2026. Este documento descreve as responsabilidades e o fluxo desejado.
As funções futuras não passam a estar implementadas pela existência deste organograma.

## Fluxo oficial

```text
Supervisor dá a ordem
        ↓
Coordenador registra a solicitação e aciona Documentos
        ↓
Documentos recebe, identifica, separa e distribui por área
        ├── Extratos e documentos de pagamentos → Financeiro
        ├── Folha e documentos de pessoal      → DP
        └── Notas e documentos fiscais         → Fiscal
                         ↓
Financeiro / DP / Fiscal analisam os documentos da própria área
e repassam os resultados, evidências e pendências à Contabilidade
                         ↓
Contabilidade prepara a escrituração com seus especialistas
                         ↓
Conciliação verifica os lançamentos e saldos contra os documentos
de suporte e as posições/documentos de terceiros, quando houver
                         ↓
Coordenador recebe o fechamento e o analisa com o Supervisor
```

Financeiro, DP e Fiscal são áreas paralelas de análise, não uma sequência obrigatória entre elas. Na versão atual elas
podem ser executadas uma após a outra, mas cada uma tem resultado, falha e pendências próprios: a falha de uma não descarta nem
impede a análise da outra. A Contabilidade distingue as propostas que dependem do resultado de outra área.
O Coordenador acompanha todo o percurso e mantém o vínculo com a SOL, a empresa e a competência.
O acompanhamento central não exige que cada entrega física volte à mesa do Coordenador: os documentos
e resultados seguem para a próxima área responsável.

## Responsabilidades

| Responsável | Recebe | Faz | Entrega |
|---|---|---|---|
| Coordenador | Ordem do Supervisor | Registra, aciona, acompanha, consolida e revisa | Trabalho para Documentos; fechamento para revisão com o Supervisor |
| Documentos | Arquivos do lote | Inventário, leitura técnica necessária à identificação, classificação e distribuição | Pacotes identificados para Financeiro, DP e Fiscal |
| Financeiro | Extratos, relação de pagamentos, comprovantes e suportes | Confere movimentações efetivas, vínculos e ausências de suporte | Informações financeiras, evidências e pendências à Contabilidade |
| DP | Folha e documentos de pessoal | Analisa os documentos da área | Informações da folha e pendências à Contabilidade |
| Fiscal | Notas e documentos fiscais | Analisa os documentos da área | Informações fiscais e pendências à Contabilidade |
| Contabilidade | Resultados das áreas | Prepara os lançamentos segundo o plano e as regras da empresa | Escrituração e respectivos suportes à Conciliação |
| Conciliação | Escrituração, suportes e posições externas disponíveis | Verifica concordância e identifica divergências | Resultado da conferência e pendências para consolidação do fechamento |
| Coordenador + Supervisor | Fechamento consolidado | Analisam resultados e pendências; Supervisor decide | Aprovação ou solicitação de ajustes |

Documentos não decide natureza contábil, não valida cálculos fiscais ou de folha e não produz lançamentos.
Uma nota pode ter o Fiscal como destino principal e ser compartilhada como suporte do pagamento no Financeiro;
isso não substitui a análise fiscal. Arquivo não identificado ou ilegível exige apontamento, sem destino presumido.
Conciliação não pode considerar validada uma posição de terceiro que não foi recebida ou conferida.
Divergências devem retornar para correção com rastreabilidade pelo Coordenador.

## Implementação atual e limites

- Funcionam localmente: Coordenador, Documentos, Financeiro, DP documental, Fiscal documental, os especialistas Bancos, DP e
  Fiscal da Contabilidade e a Conciliação (AGENTES/CONCILIACAO/PROCEDIMENTO.md), todos em SIMULAÇÃO.
- O Coordenador executa um plano de etapas por solicitação: áreas acionadas (Financeiro → DP → Fiscal, independentes) →
  Contabilidade (cada especialista depende só da própria área) → Conciliação (depois de todas, informando o alcance).
  Etapa que falhou pode ser retomada pela interface sobre o mesmo pacote íntegro; dependentes e Conciliação são reexecutados.
- Importação VGROW é outro especialista da Contabilidade, exclusivo da VGROW, com evolução pausada.
- Fiscal documental analisa notas/guias e entrega fatos/pendências; Contabilidade/Fiscal prepara propostas de competência
  com referências específicas da empresa, sem aprovar ou escriturar. Não é apuração tributária completa.
- DP lê demonstrativos documentados de folha, encargos e provisões (AGENTES/DP/PROCEDIMENTO.md); não calcula folha.
  Os demais especialistas contábeis aguardam implementação; destinos futuros ficam pendentes, sem simular entrega concluída.
- No piloto atual, Contabilidade/Bancos gera **propostas em SIMULAÇÃO**. Não há escrituração efetiva no Domínio.
- A Conciliação confere lançamentos, saldos, suportes e confirmações de terceiros recebidas; informa o alcance (parcial
  quando falta etapa, evidência ou posição) e não corrige nem aprova. O retorno ao Supervisor continua sendo SIMULAÇÃO para
  conferência: "conciliado no alcance da amostra" não significa fechamento integral de uma empresa real nem escrituração.
- Adiantamentos automáticos foram removidos pelo Supervisor. Ausência de suporte continua apontada; sem regra aplicável ou decisão específica, manter a classificação pendente.
- Aprovações humanas, isolamento por empresa e preservação dos originais continuam obrigatórios.
