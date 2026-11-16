# PROCEDIMENTO · CONCILIAÇÃO CAIXINHA · versão 1.0 (16/11/2026) — aguarda aprovação do Supervisor

Rotina para empresas que **não fornecem extrato bancário** e cuja escrituração é feita "pelo caixinha". O Domínio já integra notas,
provisões tributárias, folha, pró-labore e retenções; faltam as **baixas** das obrigações. Esta rotina identifica pagamentos já
realizados, verifica se a baixa já está contabilizada e prepara os lançamentos contra a conta **Caixa Geral** — em SIMULAÇÃO, para a
aprovação explícita do Supervisor. Fluxo do Coordenador: `CONCILIACAO_CAIXINHA` (por empresa). Empresas TRADICIONAIS continuam nos
fluxos existentes (Financeiro/Bancos e Conciliação), que não foram alterados.

## 1. Habilitação por empresa
1. Empresas → (empresa) → **Conciliação Caixinha → Configurar** (ou navegação "Caixinha" → Configurar).
2. **Rotina**: TRADICIONAL (padrão, ausência de definição) ou CAIXINHA — definição expressa, versionada no `empresa-local.json`
   (cadastro existente; nenhuma segunda estrutura) e escrita no `CADASTRO.md` (`- Rotina: CAIXINHA`). Trocar a rotina revoga o piloto.
3. **Regras** em `CLIENTES/<EMP>/REGRAS-CAIXINHA.json` (contrato `REGRAS_CAIXINHA_V1`, `API-LOCAL/regras_caixinha.py`), duas regras
   governadas pelo mecanismo existente (`governanca_regras.avaliar`, área `CAIXINHA`):
   - `CONFIGURACAO`: contas da rotina pelos **códigos reduzidos do plano da própria empresa** (Caixa Geral obrigatória; Simples
     Nacional, INSS, IRRF, Pró-labore a Pagar, FGTS, Multas e Juros quando aplicáveis; grupo e tipo ANALÍTICA conferidos), vínculos
     **tributo ↔ códigos de receita / tipo de documento / denominação**, política de datas das baixas tributárias, critérios de baixa
     (janela de dias; provisão individualizada exigida) e vigência (`competencia_desde/ate`).
   - `POLITICA_FOLHA`: `MANTER_ULTIMO_LIQUIDO`, conta Pró-labore, data da regularização (`ULTIMO_DIA_COMPETENCIA` ou `DATA_FIXA`)
     e vigência.
   O sistema **sugere** contas pela descrição do plano (empate ou ausência = sem sugestão); gravar cria uma **PROPOSTA** (nova versão;
   a anterior vai para `VERSOES/`). Só vale depois da frase exata `VALIDADO REGRA CAIXINHA <EMPRESA> <CHAVE>`, executada pelo
   Coordenador (`aprovar-regra-caixinha`), que vincula **versão + sha256 do conteúdo**. Conteúdo alterado fora do aplicativo, regra
   de outra empresa/CNPJ, vigência fora da competência ou TESTE_FICTICIO em empresa real → **não aplicada**.
4. **Piloto em SIMULAÇÃO**: frase `CONFIRMO PILOTO <EMPRESA>`. Para rotina CAIXINHA exige plano + conta Caixa Geral (no lugar do
   vínculo bancário, que continua exigido para empresas tradicionais). Escreve `- Conciliação Caixinha: PILOTO SIMULACAO AUTORIZADO`.

## 2. Documentos (cinco) — identificação pelo CONTEÚDO
| Documento | Tipo em Documentos | Área | Leitor (contrato) |
|---|---|---|---|
| Balancete contábil (PDF Domínio) | Balancete contábil do período | Contábil | `balancete_anterior` por colunas → `BALANCETE_NORMALIZADO_V1` |
| Razão contábil (PDF Domínio) | Razão contábil | Contábil | `razao_pdf_dominio` por colunas → `RAZAO_CONTABIL_NORMALIZADO_V1` |
| Pagamentos efetuados no e-CAC | Pagamentos efetuados (e-CAC) | Fiscal | `pagamentos_ecac` → `PAGAMENTOS_TRIBUTARIOS_NORMALIZADOS_V1` |
| Relatório de Situação Fiscal | Relatório de situação fiscal | Fiscal | `situacao_fiscal` → `SITUACAO_FISCAL_NORMALIZADA_V1` |
| Resumo mensal da folha (Domínio) | Resumo mensal da folha (Domínio) | DP | `resumo_folha_dominio` → `RESUMO_FOLHA_DOMINIO_V1` |

Cada documento recebe a ficha comum: empresa, CNPJ, competência/período, emissão/consulta, tipo, identificador (`CXD-…`), SHA-256,
reconhecimento, dados extraídos, pendências de leitura e proveniência (arquivo, página, linha, leitor). Originais preservados
(somente leitura) e conferidos por sha256 antes de qualquer leitura; documento de outro CNPJ não é distribuído nem lido.
Conferência com os arquivos REAIS da empresa piloto (16/11/2026; documentos fora do Git): comprovantes de arrecadação do e-CAC (um por
página), Relatório de Situação Fiscal (emissão no cabeçalho, sem rótulo), Resumo da Folha do Domínio por seções (PROVENTOS/DESCONTOS/
Líquido Geral), balancete do Domínio SEM a coluna Classificação (hierarquia derivada do recuo, sinalizada) e razão do Domínio em
planilha `.xls` (Excel antigo, lido só pelos valores). Leitores marcados `CONFERIDO_COM_ARQUIVO_REAL_PILOTO` (uma empresa); o razão em
PDF continua a homologar. Homologação da piloto: 18/18 valores de referência conferidos (tributos, folha e Caixa), 0 itens em revisão.

## 3. Etapas (plano do Coordenador; cada uma com resultado registrado, sha256, fontes e tentativas)
`Documentos → CAIXINHA_CONTABIL (leitores) → CAIXINHA_FISCAL (e-CAC + situação fiscal) → CAIXINHA_DP (resumo da folha) →
CAIXINHA_CONCILIACAO (tributário, folha, geral, Caixa) → Coordenador + Supervisor → TXT (somente empresa fictícia nesta versão)`.
A Conciliação Caixinha espera as demais e informa o **alcance** (parcial quando falta etapa/documento). Falha não é repetida
automaticamente; retomada por ação do Supervisor (`/areas/<ETAPA>/retomar`). Nenhuma etapa do Financeiro/Bancos é exigida.

## 4. Pagamentos do e-CAC (especialista Fiscal)
- Evidência de pagamento = **data de arrecadação**. Bloco sem ela = `GUIA_SEM_COMPROVACAO` → nunca gera baixa.
- Composição (Código · Denominação · Principal · Multa · Juros · Total): principal + multa + juros = total de cada componente e soma
  dos componentes = valor total (igualdade exata). Sem composição: um único código pago até o vencimento → total = principal
  (critério registrado); demais casos → pendência (a divisão entre tributos **nunca** é presumida).
- Identidade do pagamento = empresa + CNPJ + tipo + número do documento (sem número: código + PA + data + valor) — não depende do
  nome/sha256 do arquivo. Mesmo pagamento em dois documentos = UM pagamento (registrado). Mesmo PA + código + valor com números
  diferentes = **possível pagamento duplicado** (revisão; nada baixado em dobro).

## 5. Conciliador tributário
Para cada pagamento comprovado: tributo/conta pela configuração; o razão precisa **cobrir a data do pagamento**.
1. **Já contabilizado?** débito na conta do tributo com o valor exato (por conta, somando os componentes da mesma conta) **e** data a
   até N dias do pagamento **ou** referência do período/número do documento no histórico; associação única. Valor igual sem critério
   (débito sem referência a outro período e posterior ao PA) → revisão. Parte baixada e parte não → DIVERGENTE.
2. **Provisão** (integrada pelo Domínio; nunca criada aqui): crédito de mesmo valor com referência do período no histórico ou data no
   mês do PA/seguinte; mais de uma possibilidade → revisão; não identificada → SEM_PROVISÃO_IDENTIFICADA (revisão), salvo critério
   expresso da empresa que dispense a individualização.
3. **Baixa proposta**: D Tributo a Recolher × C Caixa Geral por conta (DARF INSS + IRRF = dois débitos, soma = crédito no Caixa,
   mesmo grupo); multa/juros só com as contas de despesa configuradas. Data pela política: `DATA_PAGAMENTO` (fora da competência →
   revisão), `ULTIMO_DIA_COMPETENCIA` ou `DATA_PAGAMENTO_OU_ULTIMO_DIA` (regularização no último dia, histórico com a data do
   pagamento). Competências encerradas nunca são alteradas. Pagamento após o fim da competência → EM ABERTO nesta competência.
4. Classificação: PAGA_E_CONTABILIZADA · PAGA_NAO_CONTABILIZADA · EM_ABERTO · DIVERGENTE · SEM_PROVISAO_IDENTIFICADA ·
   PAGAMENTO_DUPLICADO · NECESSITA_REVISAO. Provisões do razão sem pagamento no e-CAC (cada débito quita no máximo uma provisão, por
   referência de período) aparecem como EM ABERTO.
5. **Situação fiscal** (conferência adicional): débito vencido para período com pagamento no e-CAC → divergência informada (não
   bloqueia a baixa comprovada); sem pagamento → EM ABERTO confirmado; vencimento posterior à emissão = A VENCER. "Sem pendências"
   não significa baixa contábil.

## 6. Conciliador de folha (pró-labore) — política operacional
Exige `POLITICA_FOLHA` APROVADA e vigente (aprovação PRÉVIA, data definida). Saldo credor do Pró-labore a Pagar (balancete) −
último líquido (resumo do Domínio da última competência) = **REGULARIZAÇÃO CONFORME POLÍTICA CAIXINHA** (D Pró-labore × C Caixa;
evidência POLÍTICA_OPERACIONAL — não é pagamento individualmente comprovado). Segurança: o razão é interpretado por competência
(bruto, **retenções** — débitos contra INSS/IRRF —, pagamentos já lançados e outros débitos); bruto e retenções da última competência
precisam conferir com o resumo e o líquido em aberto dela = último líquido; caso contrário, revisão. Retenções não são descontadas
de novo (a baixa parte do saldo). Regularização já aprovada/exportada em outra solicitação e ainda não vista no razão → revisão.

## 7. Conciliador geral e Caixa
Integridade das etapas (sha256 do registro), regras vigentes, saldo final razão × balancete por conta (divergência = bloqueio e
propostas da conta INCOMPLETAS), idempotência (uma baixa por identidade), saldo projetado de cada conta (obrigação que ficaria devedora
→ propostas INCOMPLETAS; nunca forçado a zero). **Caixa**: saldo do balancete − baixas tributárias − baixas de folha = saldo
**contábil** projetado (não é conferência de dinheiro físico); saldo credor → alerta e item de revisão. Evidências separadas:
DOCUMENTO_EXTERNO (e-CAC, situação fiscal), CONTROLE_INTERNO (balancete, razão, resumo), POLITICA_OPERACIONAL (folha),
CONSISTENCIA_SISTEMA (registro).

## 8. Aprovação, exportação e duplicidade
Aprovação: frase `APROVO FECHAMENTO <SOL>`; exige plano concluído, conciliação vigente, nenhuma verificação bloqueante, nenhuma
proposta incompleta, ao menos uma baixa proposta e **ciência** dos itens em revisão (que não geram lançamento). As identidades das
baixas (`CXN-TRIB|…`, `CXN-FOLHA|…`) entram no controle existente de duplicidade entre solicitações (aprovadas/exportadas/registro
mínimo). O TXT usa o exportador existente (`exportacao_dominio.py`, partida simples, cp1252, CRLF): **somente empresa fictícia**;
empresa real fica BLOQUEADA até a homologação do layout no Domínio e uma autorização específica, auditável e por empresa (ainda não
implementada). "Simular o TXT" mostra as linhas sem gravar arquivo. Depois da importação (manual), reenvie razão e balancete: as
baixas passam a PAGAS E CONTABILIZADAS.

## 9. Lote
Navegação "Caixinha": painel da competência por empresa (conciliadas, com divergências, documentos insuficientes, aguardando
aprovação, aprovadas/prontas para exportação). Execução em lote: cada empresa na própria solicitação, uma de cada vez, pelo mesmo
início do fluxo individual (`iniciar_lote`).

## 10. Homologação com a empresa piloto (dados reais fora do Git)
`TESTES/CAIXINHA/homologar_caixinha_local.py` roda o fluxo completo numa pasta TEMPORÁRIA isolada com os documentos reais e compara com
um JSON de referência guardado fora do repositório. Nada vai a `CLIENTES/`, runtime real, `LIBERADOS/` ou Git.

## Limites desta versão
Leitores conferidos com os arquivos de UMA empresa piloto (outras empresas podem ter variações do Domínio/e-CAC; razão em PDF a homologar); FGTS (FGTS Digital) e outros tributos fora do e-CAC não são comprovados por esta rotina;
TXT de empresa real bloqueado; sem consulta externa (e-CAC/RFB) — só documentos enviados; folha mista (salários + pró-labore)
exige resumo por contribuinte.
