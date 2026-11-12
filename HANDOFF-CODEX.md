# AGENTES PRIME — HANDOFF PARA CODEX

## Versão
`v1.8.0-interno` (branch `master`, remote `origin` = https://github.com/contabilizafacilvieira/AGENTES-PRIME.git).
Release anterior: `v1.7.0-interno` (commit `34c90b5`). O commit e a tag desta versão estão na seção **Git**.

## Objetivo atual
Executar o **primeiro fechamento real completo supervisionado** da **BRASIL-PROTEC-AGRO**, competência **2026-09**.
O sistema é **multiempresa**: a Brasil Protec é só o piloto.

## Arquitetura
```
Supervisor → Coordenador Geral → Fiscal · Financeiro · Contábil · DP · Conciliação → agentes especializados
```
**FECHAMENTO é processo, não departamento.** É o processo que coordena e consolida os cinco departamentos.

| Departamento | Responsável por |
|---|---|
| Fiscal | NFs, guias, apurações e retenções |
| Financeiro | Extrato (fonte oficial), relatório financeiro (fonte auxiliar) e conciliação **banco × financeiro** |
| Contábil | Propostas, provisões, balancete e razão |
| DP | Folha e encargos |
| Conciliação | Book e **conciliação do balanço** (book × balancete × razão) |

Ordem do fechamento completo: Fiscal → DP → Financeiro → **checkpoint** → Contábil (bancos, fiscal, DP) → Conciliação →
prévia (checkpoint final). Detalhes em `GUIA-FECHAMENTO-PILOTO.md`.

Arquivos principais:

| Papel | Arquivo |
|---|---|
| Coordenação | `COORDENADOR-GERAL/ferramentas/coordenador.py` |
| API local | `API-LOCAL/servidor.py` |
| Roteamento | `API-LOCAL/documentos_local.py` |
| Adapters e contratos | `API-LOCAL/adaptadores_fechamento.py` |
| Intercâmbio | `API-LOCAL/intercambio.py` |
| Prévia | `API-LOCAL/previa_fechamento.py` |
| Tentativas e pacote | `API-LOCAL/reprocessamento.py`, `API-LOCAL/complementos.py` |
| Interface | `ESCRITORIO-VIRTUAL/js/previa-fechamento.js`, `ESCRITORIO-VIRTUAL/js/sol-documentos.js` |

## Multiempresa
- **Motor geral**: comportamento válido para qualquer empresa (ingestão, SHA, classificação, roteamento, conciliação, checkpoints, prévia,
  intercâmbio).
- **Adapter**: tradução de um formato para um contrato normalizado. Pode ser compartilhado e não guarda dados. Fica registrado em
  `ADAPTERS` de `adaptadores_fechamento.py`.
- **Regra da empresa**: conhecimento do cliente. Fica em `CLIENTES/<EMP>/REGRAS-*`, governada pelo Supervisor e **nunca** é reaplicada
  em outra empresa.
- **Isolamento obrigatório e fail-closed:**
  - toda consulta acontece no contexto (empresa, SOL);
  - só resultados **registrados** são lidos, com sha256 conferido contra o registro do Coordenador;
  - leitura fora da pasta da empresa é recusada;
  - competências anteriores só entram com política aprovada em `REGRAS-INTERCAMBIO.json`.
- **Testes**: `TESTES/API/testar_multiempresa.py`.

## Runtime real
Fica em `$HOME/Library/Application Support/AgentesPrime/runtime`, **fora do Git**.
- Código: GitHub. Dados operacionais: runtime local.
- Nunca copie o runtime para o repositório e nunca tente reconstruí-lo pelo GitHub.
- Testes e demonstrações usam ambientes isolados.

## SOL piloto
BRASIL-PROTEC-AGRO · `SOL-2026-000002` · competência 2026-09.

## Estado antes do próximo passo
- 43/43 associações bancárias confirmadas: 11 automáticas e as demais por decisões vigentes do Supervisor na Central.
- Tentativas 0001 e 0002 finalizadas como BLOQUEADA (histórico preservado).
- Tentativa **0003 ainda NÃO criada**; **financeiro-6 ainda NÃO executado**; nenhum fechamento real novo nesta rodada.
- A prévia real (somente leitura) mostra "Execução anterior interrompida — reprocessar".
- PagFor: **sem desenvolvimento específico** (decisão do Supervisor). O documento histórico PagFor **não é extrato** e permanece
  "Tipo a conferir".

## Próximo passo EXATO
O próximo passo **não** é reprocessar imediatamente.
1. O Supervisor baixa os documentos reais.
2. "Adicionar documentos ao fechamento" na SOL-2026-000002, com vários arquivos de uma vez.
3. O upload acontece **sem execução**.
4. O Agente de Documentos classifica.
5. Conferir o roteamento por departamento na aba "Prévia do fechamento".
6. Identificar os layouts reais. A prévia mostra "adapter existente", "layout novo — adapter necessário" ou "não reconhecido".
7. Criar e validar os adapters determinísticos, sempre com fixture **fictícia** do mesmo layout. Arquivo real nunca entra no Git.
8. Só então criar a tentativa 0003 ("Reprocessar fechamento").
9. Executar Fiscal + DP + Financeiro.
10. **PARAR** no checkpoint ("parar após o Financeiro" marcado).
11. O Supervisor revisa, incluindo as consultas do Financeiro às outras áreas (só candidatos).
12. Só depois o Supervisor autoriza Contábil e Conciliação.
13. Produzir a prévia do fechamento (checkpoint final).

## Documentos que serão fornecidos
- Notas fiscais.
- Extratos.
- Relatório financeiro.
- Book.
- Balancete.
- Razão.
- Impostos, guias e memórias.
- Folha/DP, quando aplicável.

## Regra de segurança
- Nenhum lançamento definitivo automático. Tudo é SIMULAÇÃO: proposta não é lançamento.
- Nada vai ao Domínio sem aprovação explícita do Supervisor.
- Não inventar valores nem layouts. Fail-closed sempre.
- Commit, tag e push só com autorização explícita.

## Git
| Item | Valor |
|---|---|
| Branch | `master` |
| Remote | `origin` = https://github.com/contabilizafacilvieira/AGENTES-PRIME.git |
| Tag | `v1.8.0-interno` (anotada), aponta para o commit `feat: prepara fechamento completo multiempresa`. Confira com `git rev-parse v1.8.0-interno^{commit}` |
| Gate | `TESTES/executar_gate.py`: 73 baterias, 73 PASS, 0 falhas, GATE DE RELEASE APROVADO |

## Servidores
| Porta | Ambiente | Como iniciar |
|---|---|---|
| 8765 | **REAL** | `AGENTES_PRIME_RUNTIME="$HOME/Library/Application Support/AgentesPrime/runtime" .venv/bin/python -I -u API-LOCAL/servidor.py` |
| 8767 | DEMONSTRAÇÃO — fechamento completo | `TESTES/DEMONSTRACOES/servidor_demo_fechamento.py` (`--recriar` recria a demonstração) |
| 8766 | DEMONSTRAÇÃO — checkpoint | `TESTES/DEMONSTRACOES/servidor_demo_checkpoint.py` |

A página mostra a faixa AMBIENTE REAL ou DEMONSTRAÇÃO. Os **PIDs são transitórios**: confira com `lsof -nP -iTCP:<porta> -sTCP:LISTEN`,
nunca presuma.

## Working tree
Depois da publicação, a working tree fica limpa. Nenhum arquivo foi deixado intencionalmente fora do controle de versão.

## Dívidas técnicas conhecidas
- Nome histórico "Contabilidade/Bancos" no checkpoint, em rotas e na tarefa interna `CONTABILIDADE` (especialista de bancos). A prévia já
  separa Financeiro, Contábil e Conciliação.
- Adapters dependentes dos arquivos reais:
  - balancete e book reais precisam ser validados (os leitores atuais são os da base inicial);
  - razão em PDF não tem adapter;
  - memórias de impostos em planilha;
  - guias de folha (FGTS Digital/DCTFWeb);
  - layouts de DP além dos documentados.
- No intercâmbio, a soma de vários itens ainda não entra como critério de candidato. A associação manual da Central continua disponível.
- O responsável esperado por divergência de conta é uma sugestão pela descrição da conta; o Supervisor pode reatribuir.
- Política V1 da conciliação financeira congelada (`conciliador_financeiro.py`). P1–P8 não foram implementados.
