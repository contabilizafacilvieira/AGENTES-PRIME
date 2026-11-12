# PROCEDIMENTO GERAL · AGENTE FINANCEIRO · versão 1.5 (11/11/2026)
> 1.1: bloqueio do lote × pendência individual; divergência entre extratos sobrepostos; ressalvas de Documentos.
> 1.2: relação com TIPO (pagamentos e recebimentos), posição de títulos (controle interno), resumo da folha como natureza
>      do pagamento de salários, isolamento de documento de outra empresa não cadastrada.
> 1.3: relatório financeiro normalizado como FONTE AUXILIAR (Normalizador Financeiro); não substitui extrato bancário.
> 1.4: extrato bancário lido pelo Normalizador Bancário (contrato comum); leitor Santander antigo vira legado.
> 1.5: conciliação financeira banco × relatório (motor genérico) e regra fail-closed para o extrato do contrato comum.

Procedimento GERAL, válido para qualquer empresa. Regras específicas de cliente NÃO entram aqui (ficam em
`CLIENTES/<EMPRESA>/`). Implementação: `ferramentas/conferencia_financeira.py` (código local, sem Claude).
Mudança neste procedimento = nova versão, aprovada pelo Supervisor.

## Papel
Conferir as movimentações financeiras de UMA empresa e UMA competência e devolver o resultado ao Coordenador.
**Não é conciliação contábil completa**: a Conciliação independente é etapa futura.

## Entradas (somente pelo extrator, somente da pasta da SOL)
| Documento | Formatos | Observação |
|---|---|---|
| Extrato bancário | OFX; CSV no leiaute do projeto; PDF digital Santander Empresas reconhecido | fonte das movimentações EFETIVAS |
| Relação de pagamentos/recebimentos | CSV ou XLSX com cabeçalho | informação AUXILIAR: não comprova pagamento sozinha |
| Posição de títulos a pagar/receber | CSV com cabeçalho | controle INTERNO da empresa; não é confirmação de terceiros |
| Resumo da folha de pagamento | TXT ou PDF digital (cópia de suporte do DP) | sustenta a NATUREZA do pagamento de salários |
| Comprovante de pagamento | TXT ou PDF digital | prova a LIQUIDAÇÃO, não a natureza |
| Nota fiscal, guia, recibo | NF-e XML; TXT ou PDF digital | sustentam a NATUREZA |
| Boleto | TXT ou PDF digital | identifica a COBRANÇA; a natureza vem da nota/guia/recibo/contrato |
PDF escaneado, imagem, formato não suportado, conteúdo truncado: pendência explícita, nada é inferido.

### Leitura local do PDF Santander Empresas
O leitor reconhece agência, conta, período, páginas numeradas e linhas com data, histórico, valor assinado e saldo.
Exige todas as páginas e a ordem decrescente do layout; confere os saldos sucessivos sem tolerância. Linha de
movimento inválida ou divergência impede o aproveitamento parcial do arquivo, com motivo explícito e alternativa OFX.
Banco 033 e conta são conferidos com o cadastro. CNPJ ausente no cabeçalho não é inventado.
O saldo disponível/ContaMax da posição atual não substitui o saldo da última movimentação do período.
Saldo inicial ausente permanece pendente: não é deduzido para declarar uma conferência integral concluída.
Esta leitura não classifica a natureza contábil pelo histórico e não altera regras de adiantamentos ou vínculos.

### Leiaute CSV do extrato (separador `;`)
`conta;titular_cnpj;data;tipo;historico;identificador;valor;saldo` — `conta` = `banco-agência-conta`; `tipo` =
`SALDO_INICIAL`, `MOVIMENTO` ou `SALDO_FINAL`; `valor` com sinal (negativo = débito); datas `dd/mm/aaaa`.
### Leiaute da relação de pagamentos (CSV `;` ou XLSX)
`data_pagamento;favorecido;cnpj_cpf;valor;documentos;conta_pagadora;pagamento_id;obrigacao_contabilizada;natureza` —
`documentos` = referências separadas por `,` (ex.: `NF 1001`); `pagamento_id` agrupa itens pagos juntos;
`obrigacao_contabilizada` = `SIM` quando a obrigação já foi reconhecida (a liquidação não gera nova despesa).
Cabeçalho atual (v1.2): `TIPO;DATA;FAVORECIDO;CNPJ;VALOR;DOCUMENTOS;TITULO;CONTA;OBRIGACAO_CONTABILIZADA`.
`TIPO` = `PAGAMENTO` (padrão; casa com DÉBITO) ou `RECEBIMENTO` (casa com CRÉDITO; FAVORECIDO = pagador); outro valor =
pendência e item não usado. `CONTA` = conta bancária da empresa (pagadora/recebedora); `TITULO` = título da posição.
Aliases aceitos: `DATA` = `DATA_PAGAMENTO`, `CONTA` = `CONTA_PAGADORA`, `CNPJ` = `CNPJ_CPF`. Recebimento segue as mesmas
regras do pagamento (conta da relação = conta do extrato + identificador comum; faltando um deles = SUGESTÃO); o item
confirmado entra em `relacao` do movimento e o CNPJ do pagador fica em `favorecido_cnpj` (usado pela Contabilidade/Bancos).
### Posição de títulos (CSV `;`)
`TIPO;POSICAO;DATA_BASE;CONTRAPARTE;CNPJ;TITULO;VENCIMENTO;VALOR` — `TIPO` = `PAGAR`|`RECEBER`; `POSICAO` = `INICIAL`
(data-base = último dia do mês anterior) | `FINAL` (último dia da competência). Data-base diferente = linha não usada.
Posição sem títulos é DECLARADA por linha `TITULO` = `SEM TITULOS EM ABERTO` e `VALOR` 0,00 (não é título). Sem nenhuma
linha INICIAL/FINAL de um TIPO, a posição é tratada como NÃO RECEBIDA (pendência), nunca presumida vazia.

### Posição de títulos — conferência (controle INTERNO)
Liquidação = item da relação com `TITULO` + movimento confirmado (mesmo TIPO: pagar ↔ pagamento, receber ↔ recebimento).
- título da posição inicial ausente da final com liquidação de mesmo valor → `LIQUIDADO_CONFERIDO`;
- título da inicial ausente da final sem liquidação → `SEM_LIQUIDACAO` (pendência `TITULO_SEM_LIQUIDACAO`);
- título liquidado no mês que permanece na final, valor liquidado ≠ valor do título, CNPJ divergente, título repetido ou
  valor alterado sem liquidação → `DIVERGENTE` (pendência `DIVERGENCIA_TITULO`);
- título em aberto na final sem liquidação (inclusive emitido no mês) → `EM_ABERTO`, sem pendência;
- posição inicial ou final do TIPO não recebida → `EM_ABERTO` com observação + pendência `POSICAO_TITULOS_INCOMPLETA`;
- liquidação com TITULO fora da posição enviada → pendência `TITULO_FORA_DA_POSICAO`.
Saída: `posicoes_titulos` [{tipo, titulo, contraparte, cnpj, vencimento, valor_inicial, valor_final, liquidacao {movimento,
valor, data, relacao}|null, situacao, observacao, origens, controle: INTERNO}] e `posicoes_titulos_resumo` {controle,
titulos, liquidado_conferido, em_aberto, divergente, sem_liquidacao, totais, aviso}. A posição é controle interno: não
substitui confirmação de terceiros (atribuição da Conciliação).
Liquidação conferida de título da posição INICIAL com `OBRIGACAO_CONTABILIZADA=SIM`: a nota anterior não é exigida no lote;
o movimento recebe `liquidacao_titulo` e a referência ao título não é listada como documento ausente. A situação do
movimento não é alterada (a regra bancária decide).
### Resumo da folha (cópia de suporte do DP)
Documento com `RESUMO DA FOLHA DE PAGAMENTO` → tipo `FOLHA`: valor = `LIQUIDO A PAGAR`, número = `NUMERO DO DOCUMENTO`,
competência = `COMPETENCIA`. Sustenta a NATUREZA do pagamento de salários somente por referência explícita da relação
(ex.: `DOCUMENTOS=FP-2026-10`); valor igual sem referência é apenas candidato. O Financeiro não analisa a folha.
Outros documentos do DP (encargos, provisões, folha genérica) e da Conciliação são ignorados quando não há cópia
destinada ao Financeiro.

## Conciliação financeira banco × relatório — v1.5
Motor `ferramentas/conciliador_financeiro.py` (`CONCILIACAO_FINANCEIRA_V1`, política `CONCILIACAO_FINANCEIRA_POLITICA_V1`),
executado pelo Financeiro quando há extrato do contrato comum ACEITO (conta cadastrada). Não é a Conciliação geral do
sistema e não gera lançamento, conta contábil ou aprovação.
- **Elegível** (obrigatório): natureza compatível (CRÉDITO↔ENTRADA, DÉBITO↔SAÍDA), data do auxiliar = data de quitação
  (senão `data`; nunca competência/vencimento) a até 2 dias corridos, valor exato (1×1) ou soma exata (grupos). Tolerância R$ 0,00.
- **Evidências fortes:** documento exato (normalizado: caixa, espaços, pontuação, zeros à esquerda numéricos), CPF/CNPJ da
  contraparte no histórico bancário, nome da contraparte com 2+ termos informativos presentes. **Fracas:** nome parcial,
  descrição com 2+ termos informativos (termos genéricos como PIX/PAGAMENTO/BOLETO não contam).
- **CONCILIADO (1×1):** elegível + (data ≤ 1 dia e ≥ 1 forte, ou 2 dias e ≥ 2 fortes) + sem concorrente. **PROVÁVEL:** único,
  sem evidência forte suficiente. **AMBÍGUO:** dois ou mais candidatos disputando o mesmo movimento (componentes conexos; nada
  é escolhido). **NÃO CONCILIADO:** nenhum candidato elegível.
- **Grupos 1×N e N×1** (até 3 itens; mais de 12 candidatos = análise manual, sem força bruta): soma exata; CONCILIADO só com
  evidência forte em todos os membros e data ≤ 1 dia; só a soma = PROVÁVEL; mais de uma combinação = AMBÍGUO.
- Score com componentes só ordena/explica; a classificação vem das regras. Cada associação guarda id determinístico, ids dos
  dois lados, cardinalidade, critérios atendidos/ausentes, versão da política e SHA das origens.
- **Fail-closed:** cada movimento do extrato normalizado recebe `conciliacao_financeira`. Movimento que não está CONCILIADO e
  não tem suporte independente (COM_SUPORTE ou transferência própria) BLOQUEIA o lote para a proposta contábil, com uma
  pendência agrupada `ASSOCIACAO_FINANCEIRA_NAO_CONFIRMADA` (problema, impacto, o que fazer). PROVÁVEL exige decisão futura do
  Supervisor. CONCILIADO libera só a associação financeira: **não** é suporte documental/fiscal (situação e documentos do
  movimento não mudam). Extratos de leiaute antigo (CSV/OFX/PDF legado) seguem a regra anterior.
- **Linha de base (11/11/2026):** a política V1 foi validada em cenário operacional real, somente leitura, sem alteração do
  estado operacional, e não foram identificados falsos positivos entre as associações automáticas revisadas. Calibrações
  futuras serão uma nova versão de política (V2), com testes próprios, sem alterar a V1 em silêncio.

## Decisões do Supervisor sobre a conciliação (Central de Revisão)
Camada SEPARADA do motor: `ferramentas/decisoes_conciliacao.py`, contrato `DECISOES_SUPERVISOR_CONCILIACAO_V1`. A política V1
do motor não muda e a classificação do motor nunca é sobrescrita (PROVÁVEL aprovado continua PROVÁVEL; o que muda é o estado
operacional, calculado numa única função).
- **Quem decide o quê:** CONCILIADO não precisa de decisão. PROVÁVEL: aprovar ou rejeitar (individual ou em lote). AMBÍGUO:
  aprovar só escolhendo explicitamente UM candidato (os demais ficam registrados como não escolhidos) ou rejeitar todos; nunca
  em lote. NÃO CONCILIADO: nenhuma associação é criada; só observação. Decisão vigente pode ser desfeita (REVOGADO).
- **Estados operacionais:** `ASSOCIACAO_CONFIRMADA_AUTOMATICAMENTE`, `AGUARDANDO_SUPERVISOR`, `ASSOCIACAO_CONFIRMADA_PELO_SUPERVISOR`,
  `ASSOCIACAO_REJEITADA`, `SEM_ASSOCIACAO`.
- **Bloqueio:** o movimento bancário deixa de bloquear com CONCILIADO automático, associação aprovada pelo Supervisor ou suporte
  independente já aceito. PROVÁVEL/AMBÍGUO sem decisão, REJEITADO e NÃO CONCILIADO sem suporte continuam bloqueando. O
  Financeiro aplica as decisões na execução seguinte (cópia fiel em `financeiro-N/decisoes-conciliacao.json`).
- **Não é suporte:** a decisão confirma só BANCO ↔ FONTE AUXILIAR; nunca marca nota/guia/documento conferido nem cria ou aprova
  lançamento contábil.
- **Auditoria e persistência:** um evento por decisão (quem, quando, SOL, empresa, competência, tentativa, associação,
  classificação do motor, ids envolvidos, decisão, justificativa obrigatória, política, estado anterior/posterior), encadeado
  por hash e imutável, em `<runtime>/execucoes/<SOL>/supervisor-conciliacao/decisoes.json` (fora do Git), gravação atômica.
  CPF/CNPJ digitados na justificativa são mascarados.
- **Concorrência e fail-closed:** a decisão leva a revisão da conciliação e a revisão das decisões vistas na tela; se algo mudou,
  é recusada (atualizar e decidir de novo). Conflito (movimento confirmado em duas associações), lote com item inválido,
  registro corrompido ou de outra SOL/empresa/competência: nada é gravado nem aplicado. Decisão feita sobre uma associação que
  mudou numa nova execução fica desatualizada (não vale).

### Checkpoint após o Financeiro (primeiro ciclo controlado)
Conclusão técnica do Financeiro ≠ autorização para a Contabilidade/Bancos. Com "Executar o Financeiro e parar para revisão" (padrão na
tela), o Financeiro executa normalmente; se bloquear, o bloqueio segue como sempre (tentativa BLOQUEADA). Se concluir sem bloqueio, o
Coordenador NÃO avança: SOL "aguardando Supervisor" (etapa FINANCEIRO_CONCLUIDO_AGUARDANDO_AUTORIZACAO), Bancos e Conciliação
pendentes, tentativa PAUSADA (ativa, não finalizada), checkpoint auditado (tentativa, resultado do Financeiro, data/hora, origem,
próxima etapa). "Continuar para Contabilidade/Bancos" registra a autorização com justificativa e continua a MESMA tentativa, sem repetir o
Financeiro. Retomada direta da rota sem tentativa ativa numa SOL ancorada a pacote de tentativa é recusada antes de qualquer escrita.

### Ambiguidade com vários movimentos bancários (decisão parcial)
Um AMBIGUO pode reunir mais de um movimento bancário (ex.: 2 movimentos × 2 registros = 4 candidatos). Cada escolha do Supervisor
confirma SÓ o candidato escolhido; o grupo aceita novas escolhas disjuntas (nenhum movimento ou registro já confirmado) até cobrir
todos os seus movimentos. Enquanto houver movimento do grupo sem associação, o estado operacional do grupo é AGUARDANDO_SUPERVISOR
("Ambíguo — parcialmente resolvido"), ele aparece nos Ambíguos e em "Ver bloqueios", e os candidatos já consumidos aparecem como
indisponíveis. Mesmo que reste um único candidato, nada é confirmado sozinho. "Desfazer esta escolha" revoga só aquela escolha
(evento REVOGADO apontando a escolha). A classificação do motor continua AMBIGUO. "Ver bloqueios" lista cada movimento que impede o
avanço (por movimento, não por grupo), com Problema/Impacto/O que fazer; total = liberados + bloqueadores.

### Associação manual assistida (exceções que o motor recusou)
Só para movimento bancário NAO_CONCILIADO (1 banco, nenhum registro auxiliar) e sem decisão vigente. A Central busca, SOMENTE na mesma
conciliação/tentativa, registros do relatório de natureza compatível, ainda não usados em associação confirmada e rastreáveis; ordena pela
proximidade de data (sem esconder os fora da janela automática; mais de 15 dias = alerta) e sugere combinações de soma EXATA (Decimal,
tolerância zero) de até 5 registros, entre os 40 mais próximos, com orçamento de busca. Nenhuma sugestão é escolhida pelo sistema.
O Supervisor seleciona explicitamente, confere e confirma com justificativa: evento `APROVADO` com origem `ASSOCIACAO_MANUAL_ASSISTIDA`
(registros, valores, SHA, soma, diferença 0,00), na mesma cadeia auditável. A classificação do motor continua NAO_CONCILIADO; o estado
operacional passa a `ASSOCIACAO_CONFIRMADA_PELO_SUPERVISOR`; registro usado fica indisponível para outra associação; revogação devolve o
bloqueio. O limite 5 é da ferramenta manual: o agrupamento automático da Política V1 continua até 3. Não é suporte documental/fiscal nem
lançamento; o bloqueio do lote só muda numa nova execução autorizada do Financeiro.

## Extrato bancário pelo contrato comum (Normalizador Bancário) — v1.4
- Todo PDF extraído passa primeiro por `ferramentas/normalizador_bancario.py`, que devolve
  `MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1`. O Financeiro consome o contrato; não há leitor por banco no Financeiro.
- **Fonte utilizável** somente se: um único adaptador reconheceu a estrutura, SHA presente, documento completo,
  aritmética (saldo inicial + créditos − débitos = saldo final) sem diferença e validações do adaptador aprovadas
  (saldos impressos e saldos diários). Depois disso valem as regras de sempre: conta do extrato no CADASTRO.md
  (titularidade não é presumida), cobertura da competência e verificação aritmética do Financeiro.
- **Fonte recusada** (sem SHA, incompleta, aritmética ou saldo divergente, linha não interpretável, mais de um
  adaptador): pendência `EXTRATO_BANCARIO_RECUSADO` (problema, impacto, o que fazer) e nenhum movimento usado.
- Documento sem adaptador bancário segue os caminhos já existentes (inclusive o leitor Santander LEGADO do leiaute
  "Agência: … Conta: …", mantido por compatibilidade).
- Movimentos bancários ficam em `movimentos` (com `rastreio_bancario`: id do contrato, SHA, página, linhas, natureza);
  o resumo das fontes em `fonte_bancaria.fontes_normalizadas`. Fonte auxiliar continua separada. Nesta versão não há
  casamento automático entre extrato e relatório financeiro.
- **Limitação da v1.4 (decisão do Supervisor, 11/11/2026; tratada pela regra fail-closed da v1.5):** Enquanto não houver mecanismo aprovado de associação entre movimentos bancários e fontes auxiliares, a existência de um extrato bancário normalizado não constitui suporte documental/contábil para os movimentos.
  O relatório financeiro auxiliar não dá suporte a nenhum movimento bancário só por ambos existirem; os movimentos sem
  comprovante/nota/guia/relação vinculados continuam `SEM_SUPORTE`. A política fail-closed para a etapa seguinte será
  implementada junto com o casamento banco × relatório.

## Relatório financeiro normalizado (fonte AUXILIAR) — v1.3
Ordem geral inalterada: Coordenador → Documentos → Financeiro → Contabilidade; a Conciliação continua como suporte.
- **Entrada:** documento classificado por Documentos como "Relatório financeiro de lançamentos" e lido como planilha
  (`EXTRAIDO_PLANILHA`, inclusive pela leitura alternativa de XLSX com estilo inválido). Passa pelo Normalizador
  Financeiro (`ferramentas/normalizador_financeiro.py`), que devolve o contrato `MOVIMENTOS_FINANCEIROS_NORMALIZADOS_V1`.
  O reconhecimento usa cabeçalho e conteúdo, nunca o nome do arquivo. Valores em Decimal; nada é presumido.
- **Fonte auxiliar:** os movimentos ficam em `movimentos_financeiros_auxiliares` (marca `FONTE_AUXILIAR_FINANCEIRA`, id
  `RF-…`), SEPARADOS dos movimentos bancários (`movimentos`, id `MOV-…`). Resumo e relatórios em `fonte_auxiliar_financeira`;
  extratos em `fonte_bancaria`. Campos antigos do resultado não mudam.
- **Relatório financeiro NÃO substitui extrato bancário:** não entra na verificação de extratos, não conclui a conferência
  bancária e não gera conciliação nem lançamento. Sem extrato utilizável, o LOTE CONTINUA BLOQUEADO, com o aviso
  "Relatório financeiro processado como fonte auxiliar, porém nenhum extrato bancário utilizável foi localizado".
- **Competência:** `data_competencia` (data ou mês explícito) é campo próprio; nunca substitui data, vencimento ou quitação.
- **Situação:** só valores exatos testados. Pago/quitado/recebido = `REALIZADO`; em aberto/pendente/não pago = `EM_ABERTO`;
  cancelado = `CANCELADO`; texto não reconhecido = `INDETERMINADO` (pendência `SITUACAO_NAO_RECONHECIDA`); coluna existente
  com célula vazia = `AUSENTE` (pendência ATENÇÃO `SITUACAO_AUSENTE`). Sem a coluna, a situação fica vazia (não inventada).
- **Linhas não realizadas:** `EM_ABERTO`, `CANCELADO`, `INDETERMINADO` e `AUSENTE` não entram como movimento realizado; ficam
  em `linhas_nao_realizadas` com linha, situação, motivo, evidência, valor, natureza, datas, origem e SHA. Nenhuma regra
  promove automaticamente uma dessas linhas a realizada.
- **"É Despesa" (validação cruzada):** Valor Entrada/Saída continuam a fonte principal. Conflito = `DIVERGENCIA_NATUREZA`;
  só define a natureza quando nenhuma outra coluna a define.
- **"Valor Pago" (validação cruzada):** comparado com o valor do movimento; diferença = `DIVERGENCIA_VALOR_PAGO`, com os dois
  valores preservados. Linha com qualquer divergência NÃO entra nos movimentos confiáveis, gera pendência e nunca é
  corrigida silenciosamente (decisão do Supervisor, 11/11/2026).
- **Contraparte:** estruturada {nome, nome_fantasia, documento}, só com campos existentes; não é obrigatória e não aparece
  em mensagens de pendência.
- **Rastreabilidade:** cada movimento/linha guarda SHA-256 do original, arquivo, aba e número da linha na planilha.
- **Falha do normalizador** (sem SHA, cabeçalho ambíguo, sem leitor, erro inesperado): pendência
  `RELATORIO_FINANCEIRO_NAO_NORMALIZADO`; nenhum movimento auxiliar; nunca convertido em extrato. Pendências de linha chegam
  agrupadas por tipo (`RELATORIO_FINANCEIRO_<CÓDIGO>`).

## Bloqueio do lote × pendência individual
- **Bloqueio do LOTE inteiro** (nada é conferido; Bancos não roda; nova solicitação necessária):
  - no Coordenador, ao encerrar Documentos: relatório com outra empresa, sem a SOL, fora do modelo, ordem ativa trocada
    ou relatório ilegível (risco de misturar dados);
  - no Financeiro (triagem determinística, antes de qualquer correspondência): competência da SOL sem correspondência nos
    extratos enviados; nenhum extrato utilizável de conta cadastrada da empresa (titularidade do lote indeterminada ou
    arquivo essencial indisponível).
- **Pendência de documento/movimento** (o lote segue; o item fica pendente): ressalvas do Agente de Documentos (repassadas
  pelo Coordenador e exibidas no resultado; documentos citados não são tratados como validados), imagem/PDF sem OCR,
  comprovante ausente, divergência entre extratos, pagamento sem suporte, correspondência ambígua, documento ou extrato de
  outra empresa (isolado, fora dos cálculos).

## Passos
1. **Conta e titular:** banco/agência/conta do extrato precisa constar na seção "Contas bancárias" do CADASTRO.md da
   empresa; titular diferente ou conta ausente = extrato não usado (pendência). Documento que identifica outra empresa
   cadastrada e não esta = não usado (isolamento). Documento de texto com CNPJs identificados (com '/' ou rótulo CNPJ) e
   nenhum desta empresa, mesmo de empresa não cadastrada = não usado (pendência `ISOLAMENTO`).
2. **Movimentos:** identificador estável (`MOV-…`, por FITID ou pelos dados do movimento); o mesmo movimento em extratos
   sobrepostos é contado UMA vez (duplicidade reportada); movimento do período comum presente em um extrato e ausente no
   outro = divergência entre extratos (pendência do movimento); mesmos valor/data com identificadores diferentes = possível
   duplicidade a confirmar (mantidos separados).
3. **Extratos:** cobertura da competência e consistência aritmética (saldo inicial + movimentos = saldo final). Sem os dois
   saldos, faltando dias ou com diferença: verificação NÃO concluída (pendência).
4. **Correspondências (somente igualdade exata, sem tolerância de valor ou data).** Valor e data iguais apenas
   SELECIONAM candidatos; **não comprovam o vínculo**. Confirmação exige também:
   - titularidade/empresa: o comprovante identifica esta empresa como pagadora; a relação informa a conta pagadora, igual
     à conta do extrato (que já é conta cadastrada da empresa);
   - identificador comum: autenticação/ID/número do documento, CNPJ ou nome do favorecido presente no extrato.
   Faltando titularidade ou identificador → SUGESTÃO; mais de um candidato → AMBÍGUA.
   - comprovante × movimento e relação × movimento (item ou grupo `pagamento_id`, pela soma) pelas regras acima;
   - natureza: referência explícita (relação ou comprovante) ao número/chave/linha digitável do documento; sem referência,
     CNPJ do favorecido + valor iguais e documento único;
   - transferência entre contas próprias: histórico cita outra conta própria + crédito de mesmo valor e data nela.
   Igualdade parcial (ex.: mesmo valor, data diferente) = SUGESTÃO, apresentada à parte, nunca confirmada.
   Muitos-para-muitos: um pagamento pode ter vários documentos e um documento vários pagamentos (parciais), desde que haja
   referência explícita.
5. **Situação de cada movimento:** COM_SUPORTE · COMPROVANTE_SEM_NATUREZA · SEM_SUPORTE · AMBIGUO ·
   TRANSFERENCIA_PROPRIA(_SEM_PAR). Créditos, tarifas, juros, estornos e transferências aparecem sempre; o tipo informado
   pelo banco (OFX TRNTYPE) é exibido, mas nada é classificado só pelo texto do histórico.
6. **Reenvio/reprocessamento:** o histórico do Coordenador separa "lançamento efetivamente ESCRITURADO" (bloqueia nova
   proposta) de "proposta gerada em SIMULAÇÃO" (não bloqueia: a nova proposta sai como revisão, com SOL e tentativa
   anteriores). Nesta fase não há escrituração efetiva (aprovação/liberação é etapa futura).

## Decisões do Supervisor
O confronto também pesquisa diretamente documentos legíveis com valor igual à saída ou entrada do extrato,
mesmo sem relação de pagamentos ou comprovante intermediário. Esses pares são SUGESTÕES, com indicação de
identificador comum/titularidade disponíveis ou ausentes. Emissão e vencimento não são data de pagamento.
Ausência de nome ou número no extrato não impede a comparação por valor. Mais de um movimento com o mesmo valor
mantém as alternativas para conferência. O papel da NF-e delimita a direção: compra → saída bancária, venda → entrada.
Documento sem direção identificada é apenas candidato, com ressalva explícita. Igualdade de valor, isoladamente,
nunca confirma o vínculo. O Supervisor pode confirmar o vínculo deste caso.
Boletos continuam sendo cobrança, não documento da natureza. Documentos bloqueados por titularidade ou cancelamento
não participam dessas sugestões. Valores não são obtidos do nome do arquivo.

Vínculo escolhido para um caso (ambíguo ou sugestão) vale SOMENTE para aquele movimento, fica registrado na SOL e gera
nova tentativa (as anteriores são preservadas). Nunca vira regra geral sozinho.

## Saída (para o Coordenador → Contabilidade/Bancos)
O foco atual é a conferência de extratos e documentos do mês; não há aprendizado por importação de razão.
Não há destino automático de adiantamento por ausência de suporte. Sem regra aplicável, a classificação fica pendente de decisão específica na Contabilidade/Bancos.
O Financeiro mantém a ausência do documento apontada mesmo quando a Contabilidade propõe adiantamento.
Cada movimento: empresa, competência, conta, identificador, data, valor, direção, descrição original, documentos
vinculados (papel: liquidação, cobrança, natureza), fundamento, confirmados/divergentes/ausentes, decisões.
Separadamente: com suporte, sem suporte, sem movimento localizado, ambíguas, sugestões, duplicidades, verificação dos
extratos, pendências e limitações.
