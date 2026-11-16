# Fiscal — conferência documental local

## Responsabilidade

Receber o pacote de Documentos, analisar documentos fiscais e entregar fatos, fontes e pendências à Contabilidade.
Execução local em SIMULAÇÃO, sem Claude, OpenAI ou outros modelos. Este módulo não é um sistema completo de apuração tributária.

## Entrega entre áreas

1. Documentos identifica notas, guias, cancelamentos e demonstrativos de apuração. Uma nota/guia pode ter cópia no Financeiro.
2. Fiscal exige empresa, CNPJ, competência e SOL correspondentes; confere hashes dos originais e da extração.
3. Identifica emitente/tomador/contribuinte, valores declarados, competência explícita e retenções quando legíveis.
4. Contabilidade/Fiscal recebe o resultado e usa somente referências documentadas da própria empresa e seu plano.
5. Propostas e pendências retornam ao Coordenador e Supervisor. Conciliação independente e DP continuam futuros.

As áreas Fiscal e Financeiro têm responsabilidades independentes. O executor local pode executar as etapas em sequência;
isso não transforma o pagamento em pré-requisito da competência fiscal. Lote só de notas pode ser analisado sem extrato.
Uma falha estrutural de integridade impede o aproveitamento. Lote financeiro bloqueado não inventa entrega contábil concluída.

## Leituras e decisões

- NF-e/NFC-e XML: recebe a estrutura do extrator, identifica partes, totais e tributos destacados. Ambiente, chave,
  protocolo declarado e ressalvas são exibidos; não há consulta à SEFAZ nem validação de assinatura/autenticidade.
  Emissão/tpNF sozinhos não decidem competência de receita, classificação da compra ou crédito fiscal.
- NFS-e em PDF/TXT: aproveita rótulos explícitos de CNPJ do prestador/tomador, número, competência e valor dos serviços.
  Rótulos na mesma linha ou próxima linha são aceitos; conflitos não são escolhidos. Outros layouts ficam para conferência.
  Para proposta de receita exige empresa como prestadora, competência atual e valor positivo sem ressalvas.
- Retenções (correção de 03/11/2026): valor por tributo somente com rótulo unívoco — "<TRIB> RETIDO [NA FONTE]",
  "VALOR DO <TRIB> RETIDO", "RETENÇÃO DE <TRIB>", "IRRF (R$)", "IR RETIDO", "PIS/PASEP RETIDO" — na mesma linha ou na
  seguinte, ou tabela federal "INSS (R$) IRRF (R$) CSLL (R$) COFINS (R$) PIS/PASEP (R$)" com um valor ou "-" por coluna.
  "<TRIB> RETIDO: NÃO" e "-" na tabela registram ausência declarada (`retencoes_ausencia_declarada`), sem gravar zero.
  Qualquer outro indício (RETID, RETENÇ, "NA FONTE", IRRF, CSRF, "<tributo federal> (R$)", rótulos combinados como
  "PIS/COFINS/CSLL RETIDO", "VALOR RETIDO", "SIM" sem valor, valores divergentes, ausência declarada com valor) vira
  pendência e a nota não é elegível. Retenção não reconhecida nunca vale zero. Sem composição/contas confirmadas não
  cria partida composta; retenção positiva continua pendente para a Contabilidade.
- Nota × guia: a classificação usa estrutura, não menção. NFS-e que cita "DARF" continua nota. Documento com estrutura
  de nota (prestador/tomador/número/valor dos serviços) e de guia (código da receita, período de apuração, número do
  documento) ao mesmo tempo, ou com ambas as menções sem estrutura, fica NAO_RECONHECIDO com pendência de ambiguidade.
- Substituição de NFS-e: lê "SUBSTITUI A NOTA <n>", "SUBSTITUTA DA NOTA <n>" e "SUBSTITUÍDA PELA/POR NOTA <n>"
  (campos `substitui`, `substituida_por`). A substituída nunca é aproveitada. A substituta só segue quando substitui
  exatamente uma nota do mesmo emitente presente no lote, de mesma competência, sem outra substituta concorrente e com
  referências coerentes. Substituta sem número ("NOTA SUBSTITUTA") bloqueia todas as notas do mesmo emitente no lote.
  Substituída ausente do lote → pendência (pode já ter sido contabilizada). Substituição tributária não é tratada como
  substituição de nota.
- Apurações repetidas (mesmo contribuinte, competência e tributo, arquivos diferentes): nenhuma é aproveitada, mesmo com
  valores iguais. Única exceção: exatamente uma "RETIFICADORA" e as demais originais no lote — a retificadora
  prevalece (`prevalece_sobre`) e as originais ficam pendentes. Retificadora sem original no lote fica pendente.
- Guia/DARF: separa PA, código e total quando identificados. Guia não comprova pagamento e não cria automaticamente
  provisão. Uma guia pode agregar obrigações e pertencer a competência anterior.
- Demonstrativo de apuração: lê somente tributo, competência e valor expressamente declarados. Não calcula alíquotas,
  base legal, compensações ou benefícios fiscais. Proposta depende de referência contábil da empresa.
- Nota tomada: não infere despesa, custo, ativo, competência ou se a obrigação já foi contabilizada.
- Moeda estrangeira, estimativas, homologação, cancelamentos, falta de identificação e OCR duvidoso ficam pendentes.
- Cópias idênticas não são somadas; mesma identidade fiscal com conteúdos diferentes exige escolha do Supervisor.
  Evento de cancelamento relacionado impede aproveitamento da nota, sem estorno automático.
- Nenhuma regra de adiantamentos automáticos é reativada.

## Rotina CAIXINHA (especializações; não alteram as leituras acima)

- `ferramentas/pagamentos_ecac.py`: relatório/comprovante de PAGAMENTOS do e-CAC (data de arrecadação = evidência; composição por
  código de receita; guia sem arrecadação não comprova; divisão sem composição nunca presumida) → `PAGAMENTOS_TRIBUTARIOS_NORMALIZADOS_V1`.
- `ferramentas/situacao_fiscal.py`: Relatório de Situação Fiscal (conferência adicional; vencido × a vencer pela data de emissão).
- `ferramentas/caixinha_fiscal.py`: etapa `CAIXINHA_FISCAL` (somente no fluxo CONCILIACAO_CAIXINHA). Ver
  `AGENTES/CONCILIACAO/CAIXINHA/PROCEDIMENTO.md`.

## Resultado e limites

`FISCAL_LOCAL_V1` registra fatos, arquivo, hash, leitura/páginas, ressalvas e pendências por documento.
`CONTABILIDADE_FISCAL_V1` distingue propostas para conferência e incompletas, sempre com aprovado=false/escriturado=false.
Sem regra, conta analítica/grupo compatível, fonte ou documento elegível, não há proposta completa.
Não exporta escrituração para o Domínio, libera arquivos ou declara fechamento integral.

O Supervisor deve esclarecer: documento vigente/competência; titularidade; natureza de notas tomadas;
retenções/composição de guias; valor definitivo em reais e base de conversão; contas ausentes/incompatíveis.
Nesta versão, campos não reconhecidos exigem fonte mais legível/estruturada e nova solicitação: não existe editor de fatos fiscais.

## Referências da empresa

`CLIENTES/<EMPRESA>/REGRAS-FISCAIS.json`, contrato REFERENCIAS_FISCAIS_V1, identifica empresa/CNPJ, vigência e fontes.
Vigência: `competencia_desde` obrigatório e `competencia_ate` opcional (AAAA-MM), no arquivo e, opcionalmente, em cada
referência. Fim de vigência informado é respeitado; sem fim, a saída registra a limitação em `limites` (nenhuma data é
presumida). Formato inválido torna a referência inaplicável.

Critérios da Contabilidade/Fiscal (correção de 03/11/2026):
- Tomador no exterior (`tomador_exterior: true`): exige `PAIS DO TOMADOR` igual a um país da lista explícita de
  `propostas_fiscais.py` (nomes PT/EN e ISO alfa-3). Ausente, Brasil (BR/BRA/BRASIL/BRAZIL), "NÃO INFORMADO", cidade ou
  texto fora da lista → pendência. País estrangeiro com CNPJ brasileiro do tomador, ou Brasil com identificador fiscal
  estrangeiro (`NIF/TAX ID DO TOMADOR`), → pendência de conflito. Referência nacional com tomador estrangeiro → pendência.
- ISS/PIS/COFINS debitados em conta do grupo RECEITA somente se a conta for redutora identificada: descrição iniciada por
  "(-)" no plano (padrão do Domínio, ex.: 60201 "(-) ISS" da State) ou campo opcional `conta_redutora_receita` igual ao
  código do débito na referência documentada (`fonte`). Receita bruta no débito do tributo é recusada; receita de
  serviços não pode creditar conta "(-)". Contas DESPESA continuam aceitas para esses tributos.
- Defesa adicional: mais de uma proposta para o mesmo tributo/competência ou para a mesma nota fica INCOMPLETA.
São referências para propostas em SIMULAÇÃO, sem aprovação automática do lançamento. Não usar o plano de outro cliente.
As referências State derivam do estudo autorizado julho-setembro; não contêm alíquotas ou valores fixos para outubro.

Testes: `TESTES/FISCAL/testar_fiscal.py`, `testar_salvaguardas_fiscais.py`, `testar_fluxo_fiscal.py`, pacotes locais e Escritório.
