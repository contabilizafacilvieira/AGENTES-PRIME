# Roteiro — teste de importação do TXT no Domínio (empresa de TESTE)

Objetivo: validar no Domínio a variante **partida simples** escolhida pelo Supervisor em 04/11/2026 (uma linha por lançamento,
débito e crédito na mesma linha, `IniciaLote = 1` em todas as linhas). A referência já validada na VGROW
(`REGRAS_Vgrow_Importacoes.md` §7) é **partida múltipla**. Por isso a variante simples **ainda não está validada**: um TXT gerado
corretamente pelo aplicativo não prova que o Domínio o aceita.

Quem executa: o Supervisor, manualmente. O aplicativo nunca importa nada no Domínio.

## 1. Pré-condições

- Use uma **empresa de teste do Domínio**, nunca um cliente real.
- O plano da empresa de teste deve ter os códigos reduzidos da amostra, todos analíticos:
  - 1101, 1121, 2101, 2111, 2112, 2113, 2114, 2121, 2122, 2131, 2132, 2133;
  - 3101, 3191, 3192, 3193, 4101, 4102, 4103, 4104, 4105, 4201, 4202.
- A lista completa, com descrições, está em `API-LOCAL/amostra_ficticia.py` (`PLANO`). Se os códigos forem outros, a importação
  vai recusar as contas; isso é falha do ambiente de teste, não do layout.
- A competência 10/2026 deve estar aberta na empresa de teste, e sem lançamentos dela.

## 2. Gerar o arquivo no aplicativo

1. Confirme que não há processamento em andamento e inicie a API: `.venv/Scripts/python.exe -I API-LOCAL/servidor.py`.
2. Em **Empresas → Amostra fictícia**, use **Preparar amostra fictícia** com "recriar".
   - Equivale a `amostra_ficticia.py preparar --recriar --somente A`.
   - É obrigatório, porque as regras da amostra agora são `TESTE_FICTICIO`, com política de data de teste. A versão anterior da
     amostra fica preservada no runtime.
3. Abra uma **Nova solicitação**:
   - empresa `AMOSTRA-COMPLETA-FICTICIA`, competência 10/2026;
   - os 16 arquivos de `TESTES/AMOSTRA-COMPLETA/CENARIO-A`;
   - aguarde até ver a faixa "Tudo conferido".
4. Aprove com a frase `APROVO FECHAMENTO <SOL>`.
5. Confira no bloco de aprovação: "TXT liberado para importação MANUAL — 18 lançamento(s), total R$ 50.516,67".
6. Clique em **Baixar TXT para o Domínio**.
   - O mesmo arquivo fica em `LIBERADOS/AMOSTRA-COMPLETA-FICTICIA/2026-10/`.
   - A auditoria (linha → lançamento → documento) fica em `%LOCALAPPDATA%\AgentesPrime\runtime\execucoes\<SOL>\exportacao-N\`.

Junto com o TXT ficam disponíveis o **Excel dos lançamentos** (as mesmas 18 linhas do TXT, com descrições das contas) e o
**balancete de verificação** (abertura documentada + movimento aprovado = saldo final), use-os para conferir o resultado no Domínio.

## 3. Conferir o arquivo antes de importar

Abra o arquivo **no Bloco de Notas**. Não abra no Excel, que pode alterar datas e separadores ao salvar. Confira:

- não há linha de cabeçalho;
- há 18 linhas, cada uma com 10 campos separados por `;`;
- a codificação é Windows-1252 (ANSI) e a quebra de linha é CRLF;
- cada linha segue o formato `dd/mm/aaaa;DÉBITO;CRÉDITO;VALOR;;COMPLEMENTO;1;;;`:
  - o valor tem vírgula decimal e não tem separador de milhar;
  - CódHist, Matriz/Filial e os centros de custo ficam vazios.

Lançamentos esperados, na ordem do arquivo (data, depois Bancos → DP → Fiscal):

| # | Data | Débito | Crédito | Valor | Origem |
|---|---|---|---|---|---|
| 1 | 03/10/2026 | 1101 | 1121 | 10000 | Bancos: recebimento ALFA (NF 101) |
| 2 | 05/10/2026 | 2101 | 1101 | 3000 | Bancos: pagamento BETA (NF 555) |
| 3 | 15/10/2026 | 2131 | 1101 | 500 | Bancos: pagamento da guia ISS 09/2026 |
| 4 | 25/10/2026 | 1101 | 1121 | 6000 | Bancos: recebimento GAMA (NFS-e 102) |
| 5 | 30/10/2026 | 2111 | 1101 | 7000 | Bancos: pagamento de salários (FP-2026-10) |
| 6 | 31/10/2026 | 4202 | 1101 | 45 | Bancos: tarifa bancária |
| 7 | 31/10/2026 | 4103 | 2113 | 640 | DP: FGTS sobre folha |
| 8 | 31/10/2026 | 4102 | 2112 | 2100 | DP: INSS patronal e terceiros |
| 9 | 31/10/2026 | 4101 | 2111 | 8000 | DP: folha — proventos |
| 10 | 31/10/2026 | 4105 | 2122 | 666,67 | DP: provisão de 13º |
| 11 | 31/10/2026 | 4104 | 2121 | 1000 | DP: provisão de férias com 1/3 |
| 12 | 31/10/2026 | 2111 | 2112 | 700 | DP: retenção INSS segurados |
| 13 | 31/10/2026 | 2111 | 2114 | 300 | DP: retenção IRRF |
| 14 | 31/10/2026 | 3193 | 2133 | 300 | Fiscal: COFINS (apuração) |
| 15 | 31/10/2026 | 3191 | 2131 | 200 | Fiscal: ISS (apuração) |
| 16 | 31/10/2026 | 3192 | 2132 | 65 | Fiscal: PIS (apuração) |
| 17 | 31/10/2026 | 1121 | 3101 | 6000 | Fiscal: receita NFS-e 102 |
| 18 | 31/10/2026 | 1121 | 3101 | 4000 | Fiscal: receita NFS-e 103 |

O total de débitos é igual ao de créditos: **50.516,67**.

Nas linhas 7 a 18, a data 31/10/2026 vem da política de **teste** da amostra (último dia da competência). Isso não é decisão
para nenhum cliente.

## 4. Importar e observar

1. No Domínio, use o mesmo caminho de importação de lançamentos por TXT que você usa com os arquivos da VGROW.
2. Escolha o arquivo baixado e a empresa de **teste**.
3. Antes de confirmar, anote o que o Domínio mostrar na pré-visualização ou nos avisos, em especial:
   - se aceita **débito e crédito na mesma linha** (partida simples);
   - se aceita **IniciaLote = 1 em todas as linhas**, e se isso gera 18 lotes de 1 lançamento ou outra forma de agrupamento;
   - se Complemento, datas e valores aparecem exatamente como no arquivo;
   - se há aviso de tamanho máximo do Complemento. Nesta amostra o maior tem cerca de 70 caracteres; o limite do Domínio ainda não
     está comprovado.

## 5. Resultado esperado depois da importação (competência 10/2026)

Movimento por conta (D = débito, C = crédito):

| Conta | Débitos | Créditos | Saldo do mês |
|---|---|---|---|
| 1101 Banco | 16.000,00 | 10.545,00 | 5.455,00 D |
| 1121 Clientes | 10.000,00 | 16.000,00 | 6.000,00 C |
| 2101 Fornecedores | 3.000,00 | — | 3.000,00 D |
| 2111 Salários a pagar | 8.000,00 | 8.000,00 | 0,00 |
| 2112 INSS a recolher | — | 2.800,00 | 2.800,00 C |
| 2113 FGTS a recolher | — | 640,00 | 640,00 C |
| 2114 IRRF a recolher | — | 300,00 | 300,00 C |
| 2121 Provisão de férias | — | 1.000,00 | 1.000,00 C |
| 2122 Provisão de 13º | — | 666,67 | 666,67 C |
| 2131 ISS a recolher | 500,00 | 200,00 | 300,00 D |
| 2132 PIS a recolher | — | 65,00 | 65,00 C |
| 2133 COFINS a recolher | — | 300,00 | 300,00 C |
| 3101 Receita de serviços | — | 10.000,00 | 10.000,00 C |
| 3191 (-) ISS | 200,00 | — | 200,00 D |
| 3192 (-) PIS | 65,00 | — | 65,00 D |
| 3193 (-) COFINS | 300,00 | — | 300,00 D |
| 4101 Salários | 8.000,00 | — | 8.000,00 D |
| 4102 INSS patronal | 2.100,00 | — | 2.100,00 D |
| 4103 FGTS | 640,00 | — | 640,00 D |
| 4104 Férias | 1.000,00 | — | 1.000,00 D |
| 4105 13º salário | 666,67 | — | 666,67 D |
| 4202 Tarifas bancárias | 45,00 | — | 45,00 D |
| **Total** | **50.516,67** | **50.516,67** | |

Somando os saldos de abertura da amostra (1101 = 40.000 D; 1121 = 10.000 D; 2101 = 3.000 C; 2131 = 500 C), os saldos finais
batem com os da Conciliação: 1101 = 45.455,00 D; 1121 = 4.000,00 D; 2101 = 0,00; 2131 = 200,00 C.

## 6. Registrar a evidência

Use a ficha `TESTES/EXPORTACAO/FICHA-TESTE-DOMINIO.md`.


- Data e hora, a empresa de teste usada e o nome e o sha256 do arquivo (o sha aparece no registro da aprovação).
- Aceito ou recusado, com print ou relatório do Domínio, e a quantidade de lançamentos e lotes criados.
- Se houve recusa, a mensagem exata, a linha indicada e o campo.

## 7. Depois do teste

- Estorne ou exclua os lançamentos **na empresa de teste do Domínio**, manualmente. Revogar a aprovação no aplicativo não
  estorna nada no Domínio.
- Leve o resultado ao orquestrador. Ele traz a decisão do Supervisor: manter a partida simples (registrando a validação com a
  evidência) ou mudar o exportador para a partida múltipla da VGROW.

## O que este teste NÃO cobre

- Acentos e caracteres especiais: os históricos da amostra são sem acento.
- Limite de tamanho do Complemento.
- Centros de custo, filiais e CódHist.
- Volumes grandes.
- Lançamentos de empresa real: a exportação deles continua bloqueada nesta versão.
