# Ficha — teste de importação do TXT no Domínio (empresa de TESTE)

Preencha durante o teste. Ele valida a variante **partida simples** decidida em 04/11/2026: uma linha por lançamento, débito e
crédito na mesma linha e IniciaLote = 1. **Arquivo gerado não é layout homologado**: só o resultado no Domínio decide.

| Campo | Registro |
|---|---|
| Data e hora do teste | |
| Responsável (Supervisor) | |
| Empresa de TESTE no Domínio (código/nome) | |
| Caminho/rotina de importação usada no Domínio | |
| Configuração/layout escolhido na importação (separador, formato de data, partida, lote) | |
| SOL do aplicativo | |
| Nome do arquivo TXT | |
| sha256 do arquivo (Histórico da SOL → aprovação) | |
| Lançamentos no arquivo / esperados | ___ / 18 |
| Total do arquivo / esperado | ___ / 50.516,67 |
| Lançamentos criados no Domínio | |
| Lotes criados no Domínio (com IniciaLote = 1 em todas as linhas) | |
| Avisos apresentados (texto exato) | |
| Erros apresentados (texto exato, linha e campo) | |
| Acentos/complementos apareceram iguais ao arquivo? | |

## Comparação dos movimentos por conta (outubro/2026)

| Conta | Débitos esperados | Débitos no Domínio | Créditos esperados | Créditos no Domínio | Confere? |
|---|---|---|---|---|---|
| 1101 | 16.000,00 | | 10.545,00 | | |
| 1121 | 10.000,00 | | 16.000,00 | | |
| 2101 | 3.000,00 | | — | | |
| 2111 | 8.000,00 | | 8.000,00 | | |
| 2112 | — | | 2.800,00 | | |
| 2113 | — | | 640,00 | | |
| 2114 | — | | 300,00 | | |
| 2121 | — | | 1.000,00 | | |
| 2122 | — | | 666,67 | | |
| 2131 | 500,00 | | 200,00 | | |
| 2132 | — | | 65,00 | | |
| 2133 | — | | 300,00 | | |
| 3101 | — | | 10.000,00 | | |
| 3191 | 200,00 | | — | | |
| 3192 | 65,00 | | — | | |
| 3193 | 300,00 | | — | | |
| 4101 | 8.000,00 | | — | | |
| 4102 | 2.100,00 | | — | | |
| 4103 | 640,00 | | — | | |
| 4104 | 1.000,00 | | — | | |
| 4105 | 666,67 | | — | | |
| 4202 | 45,00 | | — | | |
| **Total** | **50.516,67** | | **50.516,67** | | |

## Resultado

- [ ] **Aceito**: todos os lançamentos e totais iguais ao esperado.
- [ ] **Rejeitado**: o Domínio recusou o arquivo (anote o erro exato acima).
- [ ] **Aceito com diferenças**: importou, mas com diferenças (descreva-as).

## Evidências anexadas

- [ ] Print ou relatório da tela de importação (avisos e erros).
- [ ] Relatório de lançamentos ou razão da competência na empresa de teste.
- [ ] Cópia do TXT importado (o mesmo sha256 do registro).

Depois do teste, o estorno ou a exclusão na empresa de teste é manual, feito no Domínio. Revogar no aplicativo não estorna nada
no Domínio. Leve esta ficha ao orquestrador para a análise do resultado.
