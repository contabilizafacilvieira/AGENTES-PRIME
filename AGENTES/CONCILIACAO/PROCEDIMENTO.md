# PROCEDIMENTO GERAL · CONCILIAÇÃO · versão 1.1 (05/11/2026)

Mudanças da versão 1.1 (correções do relatório de 05/11/2026; aguardam a aprovação do Supervisor como nova versão):
evidência classificada por verificação; resultado NAO_DETERMINADO; exigências de posição e confirmação definidas por regra da
empresa; data do lançamento de DP e Fiscal conferida; extração e fontes da empresa registradas para a vigência.

Procedimento GERAL, válido para qualquer empresa. Implementação: `ferramentas/conciliacao.py` (código local,
determinístico, sem modelo de linguagem). Mudança = nova versão aprovada pelo Supervisor.

## Papel
A Conciliação é a última etapa antes do Coordenador e do Supervisor. Ela verifica se os lançamentos propostos e os
saldos resultantes concordam com os documentos de suporte, com o extrato bancário e com as posições ou confirmações de
terceiros. **SIMULAÇÃO:** a Conciliação verifica e aponta problemas. Ela **não corrige, não cria tolerância, não aprova,
não escritura e não libera nada** para o Domínio. A decisão é do Supervisor Contábil, e toda divergência vai ao
Coordenador Geral.

## Entradas (ENTRADAS_CONCILIACAO_V1, montadas pelo servidor)
- `etapas`: para FINANCEIRO, BANCOS, DP, CONTABILIDADE_DP, FISCAL e CONTABILIDADE_FISCAL, informa `situacao`, o caminho do
  `resultado` e o `sha256_registrado` pelo Coordenador. Etapa ausente (ou NAO_PLANEJADA) fica fora do plano, e as
  verificações dela não se aplicam.
- `pacote`: `pasta`, `documentos_local` e `extracao_local`. Os documentos destinados à CONCILIACAO são lidos com
  `receber_pacote_local(..., area='CONCILIACAO', exigir_hash=True)`:
  - SALDOS DE ABERTURA (CSV `CONTA;DESCRICAO;SALDO;NATUREZA;DATA_BASE;FONTE`, controle INTERNO). A data-base deve ser a
    véspera da competência, a natureza D ou C e o saldo ≥ 0. Conta sem linha válida fica **sem abertura**, e o saldo nunca
    é presumido zero: uma conta zerada precisa de uma linha `0,00`.
  - POSIÇÃO DE TÍTULOS (CSV `TIPO;POSICAO;DATA_BASE;CONTRAPARTE;CNPJ;TITULO;VENCIMENTO;VALOR`, controle INTERNO). A posição
    FINAL ou INICIAL de um TIPO só existe se houver ao menos uma linha daquele TIPO/POSIÇÃO. A posição sem títulos é
    declarada pela linha `TITULO = SEM TITULOS EM ABERTO`, `VALOR = 0,00`.
  - CONFIRMAÇÃO DE SALDO (texto: EMITENTE, CNPJ DO EMITENTE, CNPJ DO CLIENTE, DATA BASE, SALDO EM ABERTO), evidência
    EXTERNA de terceiro.
  - A cópia do extrato é apenas registrada. O saldo inicial e final do extrato vêm do resultado do Financeiro
    (`verificacao_extratos`, `movimentos`) e são fonte EXTERNA.
- `cadastro`: CADASTRO.md, com a seção "Contas bancárias" (coluna Conta contábil) e os CNPJs da empresa.
- `plano`: PLANO-DE-CONTAS.md, com a tabela "Contas utilizadas" (Código reduzido, Descrição, Grupo, Tipo).
- `regras_conciliacao`: REGRAS-CONCILIACAO.json da empresa (EXIGENCIAS_CONCILIACAO_V1), com as exigências
  POSICAO_TITULOS_PAGAR, POSICAO_TITULOS_RECEBER e CONFIRMACAO_TERCEIROS (EXIGIDA ou DISPENSADA com justificativa). Só vale
  a regra APROVADA (confirmação do Supervisor) ou TESTE_FICTICIO (empresa fictícia).
- `pendencias_anteriores`: são preservadas e listadas.
- `base_inicial`: `CLIENTES/<EMP>/BASE-INICIAL/<competência>/base.json`. Só a base CONFIRMADA pelo Supervisor é usada
  (verificação CONC-A-BASE-INICIAL): saldos de abertura das contas ANALÍTICAS (balancete de encerramento de M−1, D/C como
  informado, e saldos definidos expressamente). Documento SALDOS DE ABERTURA divergente da base torna a abertura da conta
  inválida (nenhum dos dois prevalece). Base em RASCUNHO não é usada. O resumo das composições do book (iguais, divergentes,
  sem conta) e as ciências do Supervisor são informados; composições e saldos de abertura não são lançamentos. A vigência usa a
  fonte BASE_INICIAL (`BASE-INICIAL/INDICE.json`).

## Verificações (cada uma tem id estável por chave de negócio, grupo, título, item, contas, lançamentos, fontes, valores esperado/encontrado/diferença, resultado, justificativa, área responsável e ação)

Evidência (sem pontuação). Cada fonte recebe uma categoria:
- DOCUMENTO_EXTERNO: extrato bancário, confirmação de terceiro;
- CONTROLE_INTERNO: demonstrativos, posições, cadastro, plano, regras;
- CONSISTENCIA_SISTEMA: resultados das outras etapas, registro do Coordenador, pacote.

Cada verificação informa todas as categorias usadas (`evidencias`) e a mais forte (`evidencia`). O resumo separa as conferidas
por categoria. Concordância interna não é confirmação independente.
- **A — integridade e origem.** Para cada etapa, verifica a situação CONCLUIDA, a igualdade entre o sha256 do arquivo e o
  registrado, e a correspondência de empresa, SOL, competência, contrato, agente e modo SIMULACAO. Verifica também o pacote
  de Documentos, o cadastro e o plano. As pendências anteriores continuam abertas (PENDENTE, listadas). Um resultado
  adulterado, de outra origem ou de etapa não concluída **não é usado**.
- **B — cada lançamento** de Bancos, Contabilidade/Fiscal e Contabilidade/DP:
  - débito e crédito definidos, em contas analíticas do plano;
  - grupos compatíveis com a natureza;
  - lado bancário igual à conta contábil do cadastro;
  - valor > 0 e igual ao da fonte (movimento, documento fiscal ou fato do DP);
  - data ou competência dentro da SOL;
  - suporte localizado e elegível;
  - ausência de duplicidade (mesmo movimento, ou mesmo documento + evento);
  - separação entre reconhecimento e liquidação: uma despesa ou receita no banco sobre documento já reconhecido no
    Fiscal ou no DP é DIVERGENTE;
  - guia nunca é suporte de provisão.

  Lançamento INCOMPLETO resulta em PENDENTE.
- **C — bancos e posições:**
  - a aritmética do extrato: saldo inicial + movimentos = saldo final;
  - abertura (INTERNA) × saldo inicial do extrato (EXTERNA);
  - saldo contábil (abertura + débitos − créditos dos lançamentos propostos) × saldo final do extrato;
  - cada movimento com exatamente um lançamento proposto do mesmo valor;
  - transferência própria em lançamento único;
  - títulos da posição × liquidações do Financeiro;
  - saldo contábil × total da posição FINAL e abertura × posição INICIAL. Estes últimos são **controles INTERNOS**: a
    concordância é marcada INTERNA e não equivale a confirmação independente.
- **D — folha, provisões e tributos:**
  - lançamentos de DP × fatos dos demonstrativos, por evento;
  - pagamento de salários no extrato × LÍQUIDO A PAGAR;
  - saldo das obrigações (PASSIVO) = abertura + valores das fontes + liquidações do extrato. Saldo devedor em passivo é
    DIVERGENTE;
  - provisão tributária × apuração declarada;
  - liquidação × guia × extrato (sem guia, vale somente a quitação integral da obrigação de abertura);
  - guia não gera provisão.
- **E — confirmações de terceiros.** A confirmação é comparada com a posição FINAL do mesmo CNPJ. A conta contábil
  aparece apenas como informação. Confirmação de outro cliente é DIVERGENTE. Data-base diferente do fim da competência
  fica PENDENTE. Saldo em aberto com terceiro e sem confirmação depende da regra da empresa:
  - exigida: PENDENTE;
  - dispensada com justificativa: NAO_APLICAVEL, citando a regra;
  - sem regra aplicável: NAO_DETERMINADO.
- **Falta de documento nunca vira NAO_APLICAVEL.** Posição de títulos ausente de um TIPO segue a regra da empresa:
  - exigida: PENDENTE;
  - dispensada com justificativa: NAO_APLICAVEL;
  - sem regra: NAO_DETERMINADO, com a pergunta ao Supervisor.

  Sem posição alguma, as confirmações seguem a mesma lógica. Só sem saldo em aberto, com as duas posições FINAIS recebidas, o
  item é NAO_APLICAVEL pela própria natureza.

## Resultados e limites
- Os resultados possíveis são:
  - CONFERIDO, DIVERGENTE e PENDENTE (falta informação para concluir uma verificação aplicável);
  - NAO_APLICAVEL: só com justificativa pela natureza do item ou por regra documentada;
  - NAO_DETERMINADO: os documentos e as regras não permitem saber se o item é exigido. Gera a pergunta ao Supervisor
    (`perguntas_supervisor`) e torna o alcance parcial: não há fechamento integral.

  Uma verificação não executada **nunca** aparece como CONFERIDO.
- DP e Fiscal: data do lançamento ausente ou fora da competência é DIVERGENTE. A data vem da política da empresa e nunca é
  presumida.
- A igualdade é exata, com Decimal e sem tolerância. Saldos são assinados: positivo = devedor, negativo = credor.
- Saldo de abertura ausente deixa PENDENTE tudo o que depende dele (nunca vale zero). Lançamento incompleto que afeta a
  conta, ou que tem contrapartida indefinida, também deixa a conta PENDENTE.
- Etapa FALHOU/BLOQUEADA deixa PENDENTE o grupo afetado, e `alcance.parcial = true` informa o que não foi executado
  (conciliação parcial).
- A concordância entre dois controles internos não é confirmação independente.
- Não há consulta externa (banco, prefeitura, eSocial). As contas de títulos a pagar/receber são identificadas pelos
  lançamentos de liquidação/reconhecimento ligados à posição: se não houver uma única conta, a verificação fica PENDENTE.
- Saída: `<saida>/resultado.json` (CONCILIACAO_V1) com:
  - `verificacoes`, `resumo` (inclui `conferidas_por_evidencia`) e `alcance` (inclui `indeterminadas`);
  - `perguntas_supervisor` e `exigencias_utilizadas`;
  - `versoes_entradas` (resultados, PACOTE e EXTRACAO);
  - `saldos_contas` e `aviso`.
- Vigência: o Coordenador registra o sha256 das fontes da empresa usadas por esta execução. Qualquer mudança de resultado,
  pacote, extração, cadastro, plano ou regra a torna DESATUALIZADA e indica as etapas a rever.
