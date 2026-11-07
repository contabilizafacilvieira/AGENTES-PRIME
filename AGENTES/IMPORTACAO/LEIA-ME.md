> **DESATIVADO em 05/11/2026 por decisão do Supervisor.** Rotas da API respondem 410, o reconhecimento automático não roda e o
> Coordenador recusa `registrar-importacao`/`registrar-aceite`. Código, regras e histórico preservados abaixo. A exportação
> contábil TXT para importação manual no Domínio (API-LOCAL/exportacao_dominio.py) é outra funcionalidade e continua ativa.

# AGENTE DE IMPORTAÇÃO · SOMENTE VGROW

Status: **IMPLEMENTADO EM SIMULAÇÃO, específico da VGROW** (importação por conta e ordem, Capital Trade, DUIMP).
**Evolução PAUSADA em 31/10/2026** por decisão do Supervisor (prioridade: fluxo Financeiro → Contabilidade/Bancos).

## Estado entregue (31/10/2026)
- Commits: `a61860c` (motor + reconhecimento), `4d83398` (evidências, pendências, conferência), `ea600a2` (nova tentativa
  com número próprio após falha), `df903a6` (aceite já registrado não aparece como desatualizado). Testes: 70/70.
- SOL-2026-000015 (real, VGROW 10/2026): documentos, reconhecimento, retornos nº 1 e nº 2, aceite de 15:26:11 e decisões
  preservados; OCCT12680/26 fechado no retorno nº 2 (SIMULAÇÃO), aguardando a conferência do Supervisor.
- Limitações conhecidas: ver "Limitações" e "Melhorias pendentes" abaixo; trava cadastral do piloto (CNPJ "a confirmar")
  continua impedindo liberação real. Nenhuma evolução nova até o Supervisor retomar.
Contas, percentuais, documentos e decisões NÃO valem para outras empresas, áreas ou tipos de importação.
Fonte das regras: `REGRAS_Vgrow_Importacoes.md` (pasta externa "Agente VGrow", validadas em 30/10/2026),
transcritas em `ferramentas/importacao_vgrow.py` sem recriar nem generalizar o processo.

## Fluxo e autoridade
```
Supervisor → Coordenador → Agente de Documentos → Coordenador (AGUARDANDO_SUPERVISOR)
  → Supervisor informa os campos da DUIMP/NFs e encaminha → Coordenador → Importação → Coordenador → Supervisor
```
- O usuário não aciona o agente diretamente; o Agente de Documentos nunca aciona a Importação.
- Só para SOL **piloto da VGROW** cuja etapa de Documentos terminou (`coordenador.py registrar-importacao` recusa o resto).
- O agente é determinístico (sem modelo de linguagem): lê os documentos SOMENTE pelo extrator.
- Resultado consolidado na SOL, que continua em **AGUARDANDO_SUPERVISOR**. Nada vai para LIBERADOS; nada é importado.
  O fechamento só está pronto depois da conferência e aprovação manual do Supervisor.

## Entradas por processo (agrupadas pelo número OCCT no nome dos arquivos)
| Dado | Origem |
|---|---|
| IPI, diferença de IPI, PIS, COFINS, ICMS cobrado, total REAL, saldo, valor pago, serviço bruto (col. NUMERÁRIO) | Comparativo `.xlsx` (extrator) |
| Numerário ("Total a pagar para CAPITAL TRADE") | Numerário `.pdf` (extrator) |
| FOB R$, frete R$, data de chegada, fatura, nº das NFs, ICMS destacado | **Reconhecidos automaticamente** no "Documentos.pdf" por `ferramentas/reconhecer_documentos_vgrow.py` (texto do PDF; se ilegível — fontes Type3 da DUIMP —, OCR local pypdfium2 + RapidOCR, offline). Leitura visual por modelo continua proibida |

### Conferência dos campos reconhecidos (decisão de 31/10/2026)
- O reconhecimento roda sozinho quando a etapa de Documentos de uma SOL piloto da VGROW termina; o resultado aparece
  na tela da SOL, já preenchido, com status por campo: OK, ILEGÍVEL (confiança < 0,80 ou separador decimal duvidoso),
  AUSENTE ou CONFLITO (valores diferentes no documento, ou DUIMP de outro processo OCCT).
- O Supervisor confere; só intervém nos campos que não estão OK (confirma a sugestão ou corrige). O servidor recusa
  campo duvidoso não confirmado e registra a origem de cada valor: `RECONHECIDO (…) · CONFERIDO_PELO_SUPERVISOR`,
  `… · CONFIRMADO_PELO_SUPERVISOR (estava ILEGIVEL)`, `CORRIGIDO_PELO_SUPERVISOR (reconhecido: X)` ou `INFORMADO_PELO_SUPERVISOR`.
- NFs: número pela chave de acesso (44 dígitos, DV conferido) das DANFEs da Capital Trade **destinadas à VGROW**
  (DANFE de outro destinatário — ex.: entrada por conta e ordem — é ignorada). ICMS destacado = soma do "VALOR DO ICMS".
- O encaminhamento à Importação continua manual (botão "Encaminhar à Importação").

Obrigatórios (§3): comparativo, numerário e "Documentos.pdf". Faltando → processo PENDENTE (não lançado).

## Saída devolvida ao Coordenador
Processos fechados (valores com origem, cálculos, 15 lançamentos, D = C) · pendentes (motivos, documentos ausentes) ·
documentos sem processo · alertas · divergências · TXT do Domínio (§7, cp1252, CRLF) · planilha de conferência ·
validação débito = crédito. Arquivos no runtime da API (`%LOCALAPPDATA%\AgentesPrime\runtime\execucoes\<SOL>\importacao-N\`),
nomeados `..._SIMULACAO_<SOL>`; download pela tela da SOL.

## Decisões conservadoras (sem suposição) — atualizadas em 31/10/2026
- **Numerário (§4):** padrão = numerário do PDF. Substituído SOMENTE quando a Prestação de contas do MESMO processo
  ("Registro:" com a mesma OCCT) traz exatamente uma linha "ENTRADA DE NUMERÁRIO" com valor diferente; os dois valores,
  as fontes e o motivo ficam registrados. "SOLICITAÇÃO DE NUMERÁRIO", TOTAL(1) e SALDO nunca são tratados como depósito.
  Mais de uma ENTRADA, mais de uma Prestação ou Prestação de outro processo → BLOQUEIO para decisão do Supervisor.
  Diferença com o "VALOR PAGO EM NUMERÁRIO" do comparativo → só ALERTA, com valores e fontes (sem tolerância).
- **Total realizado:** usa o total REAL do comparativo (§4); TOTAL(1) da Prestação diferente → ALERTA com as duas fontes.
- **ICMS:** "ICMS cobrado" (comparativo, REAL) e "ICMS destacado" (NFs) são campos distintos, mostrados lado a lado,
  sem julgamento de igualdade. O desconto (conta 434) é 50% do destacado, com o arredondamento do gerador validado.
  Quando a Prestação lista as NFs, nº e ICMS são verificados nela; divergência → BLOQUEIO para o Supervisor.
- **Checagem numerário − saldo − total REAL:** valor exato; diferente de zero → processo calculado e exibido, mas
  AGUARDANDO ACEITE (fora do TXT). O aceite do Supervisor fica registrado no Coordenador, amarrado a uma chave dos
  valores, fontes e documentos; se algo mudar, novo aceite é exigido. O aceite não libera bloqueios; D = C continua obrigatório.
- **Classificação por processo:** BLOQUEIO (documento obrigatório ausente, campo não confirmado, data fora da regra,
  conflito de identificação/fonte, valores incoerentes) · AGUARDANDO ACEITE · ALERTA · ACOMPANHAMENTO (só o que não
  sustenta nenhum valor lançado: reembolso — opcional na regra —, Prestação ausente com numerário do PDF como padrão,
  liquidação do saldo a receber/pagar).
- **Trava cadastral:** cadastro não validado / CNPJ "a confirmar" é TRAVA OPERACIONAL DO PILOTO (impede liberação real),
  não regra contábil do material VGROW, e nunca é resolvida pelo reconhecimento automático.
- **Evidências e pendências:** o relatório original de Documentos é preservado; o reconhecimento entra como evidência
  complementar (páginas submetidas ao OCR × páginas com campos identificados; o documento nunca é dado como analisado
  por inteiro). Pendências do relatório recebem atualizações só por identificador exato (nº da NF, nº da DUIMP, nome do
  arquivo), com estados NAO_RECEBIDO · RECEBIDO_NAO_LIDO · RECONHECIDO_AGUARDANDO_CONFERENCIA · CONFIRMADO_PELO_SUPERVISOR;
  RESOLVIDA só por decisão registrada do Supervisor, com justificativa.
- Chegada em mês anterior à competência ou antes de set/26 → BLOQUEIO para o Supervisor; posterior à competência → BLOQUEIO.
- Comparativo nos dois leiautes conhecidos (Honorários + Serviços Capital Trade, ou Serviço de Desembaraço); ambos juntos → BLOQUEIO.

## Duplicidade, complementar e setembro/26 (CLAUDE.md e §2/§6 da VGROW)
- O Coordenador guarda no registro os processos fechados de cada execução. Processo já fechado em outra SOL da VGROW
  vira PENDENTE ("já lançado … não gerar de novo").
- Competência que já teve fechamento → o TXT sai como `lanctos_Vgrow_AAAA-MM_complementar_...` (só com os novos).
- Competência 2026-09: alerta de que setembro/26 já foi lançado manualmente (TXT apenas de teste, não importar).

## Paridade com o gerador validado
Verificada contra os arquivos validados de out/26 (sem copiar dados reais para o projeto): o TXT gerado pelo motor é
idêntico byte a byte (45 linhas) e a planilha de conferência é idêntica célula a célula, inclusive fórmulas, nas abas
Entradas, Lançamentos e Contas. A aba extra "Origem" mostra EXTRAÍDO x INFORMADO_PELO_SUPERVISOR.

## Testes
`.venv/Scripts/python.exe -I TESTES/IMPORTACAO/testar_importacao.py` (motor, Coordenador e API; somente fixtures fictícias).

## Limitações
- Sem OCR: os campos da DUIMP e das NFs dependem da digitação do Supervisor (conferir antes de aprovar).
- Histórico de lançamentos anteriores não é consultado (por isso a regra de mês anterior vira pendência).
- TXT complementar (§6, reprocessamento com processos novos) não automatizado: cada execução gera o TXT completo da
  SOL; evitar importar duas vezes o mesmo processo é responsabilidade da conferência do Supervisor.

## Melhorias pendentes (registradas em 31/10/2026)
- **Distinguir "extração executada" de "conteúdo utilizável".** Hoje um arquivo que o extrator processou sem erro aparece
  como "LIDO_PELO_EXTRATOR" mesmo quando o texto saiu em códigos sem sentido (ex.: `04_OCCT12680-26.pdf` da
  SOL-2026-000015, fontes Type3 sem tabela de caracteres). A evidência deve indicar também se o conteúdo é utilizável,
  para que um PDF nessas condições não pareça efetivamente analisado.
- Ressalvas da SOL-2026-000015 (preservadas, sem reprocessamento): o reconhecimento foi gravado antes do registro do nº da
  DUIMP e das listas de páginas; por isso as pendências dessa SOL não são atualizadas pela DUIMP e as páginas
  lidas são deduzidas do que ficou registrado.
