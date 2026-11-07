# Começar o piloto local

O fluxo padrão funciona com código e bibliotecas locais. O servidor não chama Claude, OpenAI ou outro modelo.
Estudos específicos autorizados podem documentar o método dentro da própria empresa. Em Empresas, a seção
**Método de fechamento desta empresa** mostra as confirmações e as áreas que ainda precisam ser implementadas.
O perfil é contexto; apenas regras bancárias validadas, com condições atendidas, orientam propostas novas.
Isso não reativa o importador geral de razão e não aprova nem escritura lançamentos.
`API-LOCAL/executor.py` permanece como componente legado, sem uso pelo servidor padrão.

## Abrir

Na raiz do projeto:

```powershell
.venv/Scripts/python.exe -I API-LOCAL/servidor.py
```

Acesse http://127.0.0.1:8765/ e atualize com Ctrl+F5 após uma atualização do programa.

- O escritório é sempre a tela inicial. Os botões ficam na lateral esquerda e abrem um painel ao lado da cena, sem cobri-la.
- **Resumo:** filas de trabalho, contadas uma vez por solicitação.
- **Solicitações:** pesquisa por empresa, competência, área, estado e SOL; acompanhamento separado do envio.
- **Excluir solicitação:** move para a lixeira após confirmação. **Limpar lista de solicitações** faz o mesmo para
  todas as ativas, quando não há processamento. Na **Lixeira**, use **Restaurar solicitação** para retomar.
  A exclusão não apaga documentos, decisões, regras ou histórico de escrituração e não permite reutilizar números SOL.
  Solicitações na lixeira saem do resumo e do escritório; novas decisões exigem restauração.
- **Nova solicitação:** envio de um lote operacional.
- O tipo inicial é **Receber documentos e distribuir por área**. Documentos encaminha os itens financeiros
  identificados ao Financeiro automaticamente quando a empresa tem piloto Financeiro/Bancos autorizado.
  O fluxo de origem fica preservado no registro. Falhas estruturais ou falta de autorização impedem o encaminhamento.
- Extratos aceitos: OFX, CSV no leiaute do projeto e PDF digital do layout Santander Empresas. Outros PDFs não
  se tornam extratos só porque o texto foi extraído. Ausências, páginas incompletas e divergências são apontadas.
- Documentos recebe, identifica e separa por área: extratos ao Financeiro, folha ao DP e notas/guias ao Fiscal.
  O acompanhamento mostra o destino. Fiscal e DP fazem conferência documental local (DP: resumo da folha, encargos e
  provisões nos layouts documentados, sem calcular folha). Saldos de abertura e confirmações de saldo de terceiros vão à
  Conciliação; posição de títulos a pagar/receber vai ao Financeiro (cópia à Conciliação).
- Depois das áreas, a Contabilidade prepara as propostas (Bancos, DP, Fiscal) e a **Conciliação** confere lançamentos, saldos,
  suportes e confirmações recebidas, com resultado CONFERIDO / DIVERGENTE / PENDENTE / NÃO APLICÁVEL e o alcance da conferência.
  Etapa que falhou tem o botão **Retomar** no acompanhamento (justificativa obrigatória; reexecuta a etapa, os dependentes e a
  Conciliação; tentativas anteriores preservadas). Conciliação anterior a uma alteração aparece como desatualizada.
- Para testar o percurso inteiro com dados fictícios: Empresas → **Preparar amostra fictícia** e siga
  `TESTES/AMOSTRA-COMPLETA/LEIA-ME.md` (cenário A completo; cenário B com pendências, correção e retomada).
  Notas/guias podem ser usadas como suporte de pagamento pelo Financeiro, sem constituir análise fiscal.
- Rótulo do documento prevalece sobre menções no corpo: nota fiscal vai ao Fiscal (cópia ao Financeiro) mesmo citando folha;
  guia DARF/documento de arrecadação vai ao Fiscal (cópia ao Financeiro) mesmo contendo "boleto", "recibo" ou "comprovante".
  Indícios fortes conflitantes (nota + holerite; guia + folha) vão para Triagem, sem área presumida.
- Fiscal e Financeiro são independentes: a falha ou o bloqueio de um não descarta nem impede a análise do outro.
  A Contabilidade/Fiscal depende do Fiscal; se ele falhar, fica **bloqueada por dependência** (explícito no acompanhamento).
  Uma proposta bancária cujo documento também foi ao Fiscal fica incompleta enquanto a análise fiscal não for entregue.
  Uma nova tentativa (decisão ou regra aprovada) também conclui a Contabilidade/Fiscal pendente, uma vez, sem repetir as demais.
- Notas/guias também seguem ao Fiscal, inclusive em lote sem extrato. O Fiscal entrega competência, valores,
  retenções e pendências à Contabilidade/Fiscal. Propostas usam referências da empresa e contas compatíveis;
  não aprovam nem escrituram. Competência ausente, layout não reconhecido, fonte duvidosa ou natureza não definida
  permanecem pendentes. Não calcula tributos por alíquotas presumidas, nem cria provisão só porque há uma guia.
- O Financeiro apresenta documentos legíveis de mesmo valor como candidatos à saída ou entrada, sem exigir nome
  ou número no histórico do extrato nem uma relação
  intermediária. Confira os identificadores, titularidade e a diferença entre emissão/vencimento e pagamento.
  A confirmação do vínculo vale para o caso. Com documento candidato ainda não confirmado, a proposta
  permanece pendente de conferência e classificação; não há adiantamento automático.
  PDF protegido exige uma cópia sem senha; OCR de baixa confiança permanece pendente, sem valores presumidos.
- **Empresas:** cadastro, plano, contas bancárias e piloto.
- **Recolher**, o X do painel ou Esc: fecham as ferramentas e ampliam novamente o escritório.
- **Zoom − / Ajustar / +:** altera o tamanho da cena. Ao ampliar além do espaço disponível, use a rolagem da cena; Ajustar mostra o escritório inteiro.
- Quem foi acionado permanece na própria mesa enquanto houver SOL não concluída, inclusive em Aguardando Supervisor.
  A conclusão de uma etapa não libera a copa. Eventos rápidos preservam a sequência buscar → trabalhar → entregar.

## Leitura de PDFs e entrega entre áreas

Documentos tenta texto por página com pypdf, uma alternativa por PDFium e OCR local para páginas sem texto utilizável,
inclusive em PDFs mistos. O OCR tenta rotações e guarda origem e confiança. Texto duvidoso fica disponível para conferência,
mas não é suporte confirmado. Qualquer PDF criptografado, inclusive com proteção apenas de proprietário, fica **PDF_PROTEGIDO**
e pendente: nenhuma senha é tentada (nem vazia), o arquivo não é desbloqueado nem alterado e não passa por OCR; envie cópia sem
proteção. PDF sem texto e com páginas em branco fica DOCUMENTO_VAZIO. Erros, páginas vazias e leitura parcial ficam registrados.
Limites técnicos: 500 páginas, 2 milhões de caracteres e 300 segundos por arquivo; ao atingir limite não se declara leitura integral.
Imagens irrecuperáveis e PDFs corrompidos podem continuar pendentes. Usam-se PDFium e RapidOCR já instalados, sem serviços externos.

Cada documento ganha referência no pacote da área responsável; notas/guias podem ter cópia de suporte para o Financeiro.
O Coordenador registra a **âncora de integridade** do pacote (hashes do manifesto e da extração) ao receber Documentos; antes de
cada área o servidor confere a âncora, e o Financeiro exige o hash da extração. Pacote alterado é recusado; SOL anterior a esta
versão (sem âncora) não é tratada como verificada: a nova tentativa para com pendência explícita e exige nova solicitação.
O Financeiro reutiliza a extração de Documentos e verifica identidade, hashes dos originais e da extração.
Caches de leitura de PDF e de OCR ficam em AGENTES_PRIME_RUNTIME (ou %LOCALAPPDATA%\AgentesPrime); só resultados válidos
são gravados e cache inválido é refeito.
Se há arquivos recebidos mas ainda ilegíveis/não identificados, os movimentos sem suporte ficam com documentação inconclusiva.
Documento ilegível não é ausência confirmada de suporte; não há classificação automática em adiantamentos.

Em uma entrega de Bancos, **Revisão parcial do piloto** permite encerrar a revisão com justificativa e reabri-la.
Isso preserva pendências, não aprova lançamentos e não representa fechamento integral. Os participantes ficam livres
daquela SOL após o encerramento da revisão; outra SOL aberta continua mantendo o agente ocupado.

## Empresas e base inicial

Em **Empresas**, cada empresa aparece num cartão com status, modo e competência atual. Use **Abrir**; as demais ações ficam no
menu **⋯** (Configurações, Editar cadastro, Histórico, Excluir cadastro). Cadastrar empresa, cadastros excluídos e a amostra
fictícia ficam em **Administração · Mais opções**. **Como funciona** resume o percurso em 6 passos.

Na empresa, o cartão **Base inicial — mês/ano** mostra o status, o que está concluído, quantas pendências existem e UMA ação
principal (**Iniciar/Continuar preparação**; depois de confirmada, **Enviar documentos do mês**). O detalhe só abre sob demanda,
em 4 fases (apenas a fase atual em destaque):

1. **Balancete anterior** — envie o balancete de ENCERRAMENTO do mês anterior (PDF do Domínio, XLSX, XLS ou CSV). A tela mostra
   primeiro o resumo (contas extraídas, analíticas, sintéticas, saldos que não conferem) e a tabela só em "Ver todas as contas".
   Em seguida, **Aplicar contas ao plano** (grupo das contas principais pré-preenchido; contas diferentes só se você marcar).
2. **Book / composições** — envie o book do mesmo período; resumo (iguais, diferentes, sem conta) e detalhes sob demanda.
3. **Conferência** — análise da base (contas analisadas, sem apontamentos, que precisam de atenção, que bloqueiam) e as
   pendências. Cada uma diz **Problema**, **Impacto** e **O que fazer**, com o nível: ⛔ **Bloqueio** (impede confirmar),
   ⚠ **Atenção** (recomenda revisão) e ℹ **Informativo** (não impede nada). Códigos internos só em "Ver detalhes técnicos".
4. **Confirmação** — resumo do que será confirmado; o botão só habilita com a frase `CONFIRMO BASE INICIAL <EMPRESA> <AAAA-MM>`.

**Configuração da empresa** (separada da operação): **Contas bancárias** (visão simples; edição em Editar), **Cadastro e piloto**
(dados e habilitação do piloto com `CONFIRMO PILOTO <EMPRESA>`) e **Plano contábil atual** (resumo, todas as contas com filtros,
definir grupo/tipo e criar conta). A importação do plano pela tela e as contas de adiantamento foram retiradas da interface:
as contas vêm do balancete da base inicial; nada é classificado automaticamente em adiantamentos.

**Excluir cadastro** (menu ⋯ › Excluir cadastro): exclusão LÓGICA do cadastro operacional. Exige digitar `EXCLUIR <CÓDIGO>`
e é recusada enquanto houver ordem ativa, processamento, solicitação da empresa em andamento ou exportação em preparação. A empresa
sai da lista ativa e de Nova solicitação; documentos, solicitações, históricos, TXT/Excel/balancetes e base inicial continuam
preservados; o código nunca é reutilizado. Um novo cadastro (novo código) não herda piloto, vínculos, plano nem regras.

Os arquivos reais usados para entender os layouts não são necessários: balancetes e books novos são enviados pela tela.

Em **Nova solicitação**, empresas locais ainda não habilitadas aparecem como **CADASTRO PENDENTE**.
Selecione a empresa para ver o que falta e use **Concluir cadastro da empresa**. Ela não recebe arquivos nem inicia
serviços até a autorização do piloto. Aparecer na lista não substitui a conferência do cadastro.

Aplicar contas, definir grupo/tipo, criar conta ou alterar vínculos suspende o piloto até reconferência. Versões anteriores
ficam preservadas.
Alterações de contas já utilizadas por regras exigem revisão dessas regras; não são aplicadas silenciosamente.

## Movimentos sem suporte

Não há classificação automática em adiantamentos. A função foi removida por decisão do Supervisor.
Movimentos sem regra aplicável ficam incompletos, aguardando classificação específica e documentos.
Adiantamento só por decisão específica do movimento e somente na conta indicada expressamente pelo Supervisor, por empresa,
em Empresas → **Contas de adiantamento** (uma por natureza; conta analítica do grupo ATIVO para fornecedor e PASSIVO para cliente,
fora das contas bancárias). Grupo compatível não basta; sem indicação, a classificação fica pendente. Mesmo na conta indicada,
a decisão não supre documento nem comprova a natureza: o lançamento permanece INCOMPLETO, com a falta de suporte visível.
Configurações anteriores são históricas e não são usadas. Decisão individual não cria regra futura.
Históricos usam somente direção, data, descrição bancária e referências efetivamente vinculadas.

O estudo por razão foi removido. Registros de estudos anteriores permanecem preservados; suas rotas de execução estão desativadas.
Não é necessário importar razão nem cumprir uma quantidade de meses para testar o fluxo financeiro em simulação.

## Enviar a competência em teste

Em Nova solicitação, selecione a empresa com piloto habilitado, o fluxo **Financeiro → Contabilidade/Bancos**
e a competência correta. Envie extratos OFX ou CSV no leiaute suportado, relação e documentos de suporte.
Confira o resultado, as correspondências sugeridas e as propostas de lançamento.

## Limitações explícitas

- O processamento é uma conferência bancária e preparação de propostas em SIMULAÇÃO; não é fechamento completo nem conciliação independente.
- Nem todo layout bancário ou documento pode ser interpretado. Prefira OFX e arquivos estruturados. Bancos com CSV diferente precisam de mapeamento/adaptação.
- O extrator digital mantém seus limites. OCR usa bibliotecas locais e só é aproveitado com confiança mínima 0,90;
  isso não garante exatidão. Confira valores no original. OCR sem confiança, erro ou limite mantém o documento pendente.
- OCR fica em cache por hash em `%LOCALAPPDATA%/AgentesPrime/ocr-local`, fora do OneDrive. Não há envio a terceiros.
- Planilhas: somente valores, sem executar fórmulas/macros; confira valores em cache e a primeira aba escolhida.
- O CNPJ é validado pelos dígitos verificadores, sem consulta à Receita Federal. Assinatura/situação de NF-e não são verificadas online.
- Não há aprendizado por razão nem chamadas a modelos. As decisões e regras expressamente aprovadas são reutilizadas somente na empresa correspondente.
- Testes e desenvolvimento usam somente dados fictícios. Histórico: o estudo da STATE-BANK (fontes reais de jul–set/2026,
  autorizado em 02/11/2026) foi ARQUIVADO com o cadastro em 03/11/2026 (`CLIENTES/_ARQUIVO-STATE-BANK-20261103-2333`, fora do
  Git); não está ativo e só volta por decisão do Supervisor. Não há importação no Domínio nem liberação automática.
- Empresa real em piloto (SIMULAÇÃO): antes de esperar propostas de DP, Fiscal e Conciliação completas, confira em
  **Empresas** a lista de **definições necessárias**. Cada regra de REGRAS-DP.json, REGRAS-FISCAIS.json e REGRAS-CONCILIACAO.json
  fica REFERENCIA ou PROPOSTA até a confirmação pela frase `VALIDADO REGRA <AREA> <EMPRESA> <CHAVE>`
  (`coordenador.py aprovar-regra-area` ou `POST /api/empresas/<id>/regras-area`). Isso vale também para a política de DATA
  dos lançamentos de DP e Fiscal (`DATA_LANCAMENTO`). A versão anterior do arquivo fica em `VERSOES/`.
- Regras bancárias de empresa real também passam por essa lista: VALIDADA sem confirmação vinculada à versão (texto livre ou
  formato antigo) não é aplicada até a reconfirmação pela frase `VALIDADO REGRA <EMPRESA> <RB-NNN>`.
- Política de data "data de emissão" não está disponível nesta versão (os leitores não extraem essa data); use outra política.
- A aprovação do fechamento de empresa real é registrada, mas a exportação TXT continua bloqueada nesta versão.
- Atualizações e commits anteriores do Claude foram preservados; o módulo VGROW continua específico e pausado para evolução.

## Verificação

```powershell
.venv/Scripts/python.exe -I TESTES/LOCAL/testar_local.py
.venv/Scripts/python.exe -I TESTES/LOCAL/testar_fluxo_local.py
```

O segundo teste cria e remove somente `CLIENTES/CLIENTE-CODEX-LOCAL-TMP`, usa registro, runtime e ordem ativa temporários
(`AGENTES_PRIME_ORDEM_ATIVA`) e aponta o CLI Claude para um executável inexistente; não disputa a ordem ativa real.
Recusa iniciar se a pasta temporária já existir. Correções da auditoria de 03/11/2026:
`TESTES/FINANCEIRO/testar_correcoes_fluxo.py`, `TESTES/FINANCEIRO/testar_financeiro.py` (fixture fictícia em
`TESTES/FINANCEIRO/FIXTURE-EMPRESA-DEMO`), `TESTES/FISCAL/testar_salvaguardas_fiscais.py` e
`TESTES/LOCAL/testar_salvaguardas_documentos.py`.
Para conferir também a navegação, defina `CAPTURAS_LOCAL` com uma pasta de saída antes de executar esse teste.
