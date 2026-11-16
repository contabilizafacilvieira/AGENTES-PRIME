# AGENTES PRIME — Checklist mestre do projeto

Atualizado em 16/11/2026. Este checklist consolida estados de etapa e aponta para evidências detalhadas; resultados históricos não substituem validação do checkout atual. Etapas pendentes não são consideradas concluídas.

## Ambiente e base de desenvolvimento

- [x] Workspace definitivo: `/Users/priscilavieiralino/Documents/PROJETO GABRIEL - ESCRITORIO VIRTUAL/AGENTES-PRIME`.
- [x] Repositório oficial: `https://github.com/contabilizafacilvieira/AGENTES-PRIME.git`, branch `master`.
- [x] Python oficial da `.venv`: 3.12.16; `pip check` limpo no checkpoint.
- [x] Gate completo 03F: 79/79 baterias, zero falhas, estado operacional intocado. Evidência detalhada em `TESTES/ETAPA-03F-CHECKLIST.md`.
- [x] Conferência local somente leitura durante handoff: servidor ativo em REAL na porta 8765; 0 empresas visíveis, 0 solicitações recentes/abertas, 0 execuções ativas; 8766/8767 sem listener. Runtime não alterado.
- [x] Fixture `TESTES/LOCAL/fixtures/plano-dominio-ficticio.xlsx` auditada como inteiramente fictícia, sem metadados de autor, necessária ao teste e explicitamente permitida pelo `.gitignore`.
- [ ] Auditoria independente contínua das fichas normativas por especialista; um gate verde não confirma interpretação contábil/fiscal/trabalhista.

## Etapas

| Etapa | Estado | Evidência / observação |
|---|---|---|
| 01 — Estabilização | APROVADA | Ambiente reproduzível; Python 3.12.16; fixture fictícia Domínio; gate histórico reportado pelo Supervisor. `TESTES/ETAPA-01-CHECKLIST.md`, se disponível |
| 02 — Ambiente operacional limpo | APROVADA | Perfil REAL novo vazio, backup consistente/hash/restauração, Brasil Protec preservada e isolamentos REAL/DEMO/TESTE. `TESTES/ETAPA-02-CHECKLIST.md` |
| 03A — Estrutura normativa | CONCLUÍDA | Base central estruturada e consultável; consultar checklist 03 |
| 03B — Priorização | CONCLUÍDA | Inventário de 158 tópicos preservado; cobertura normativa geral incompleta; consultar checklist 03B |
| 03C — Contábil | APROVADA NO ESCOPO | 20 fundamentos verificados no escopo delimitado; 12 casos fictícios; checklist 03C |
| 03D — Financeiro | APROVADA NO ESCOPO | 20 fundamentos verificados no escopo delimitado; 15 casos fictícios; checklist 03D |
| 03E — Fiscal | APROVADA COM RESSALVAS | 5 verificados, 20 parciais; 20 casos fictícios; limites por contexto e jurisdição; checklist 03E |
| 03F — DP | BLOQUEADA | 3 verificados em escopo técnico limitado, 17 parciais; 15 casos fictícios. Falta estudo substantivo NBC TG 33 e benefícios nos referenciais simplificados; checklist 03F |
| 03G — Conciliação | PENDENTE / NÃO INICIADA | Aguardar revisão da 03F |
| 04 — Métodos de contabilização | PENDENTE | Não iniciada |
| 05 — Integração dos agentes | PENDENTE | Não iniciada |
| 06 — Cadastro e onboarding | PENDENTE | Não iniciada |
| 07 — Inicialização automática e atalho | PENDENTE | Não iniciada |
| 08 — Segurança e testes finais | PENDENTE | Não iniciada |
| 09 — Operação real | PENDENTE | Requer validação e autorização próprias futuras; não inferir prontidão pelo gate de fixtures |
| Hospedagem externa | ADIADA | O projeto permanece local; não publicar/implantar como serviço online |

## Limites e pendências transversais

- [x] Base geral separa norma oficial, interpretação, procedimento interno e exemplo; consultas não aprovam regras nem autorizam lançamentos automáticos.
- [x] Sugestões históricas permanecem distintas de regras aprovadas; regra de empresa não se generaliza.
- [x] Ressalvas Fiscais 03E preservadas: operação, regime, atividade, UF, município e competência definem aplicabilidade; créditos, incidências, tabelas e regras locais permanecem contextuais/parciais.
- [ ] Realizar auditoria independente das fichas e fontes normativas, mantendo estados de verificação honestos.
- [ ] Concluir 03F com aprofundamento DP; só então submeter ao Supervisor.
- [ ] Validar qualquer futura operação REAL em etapa separada, com dados e autorização específicos; gate fictício não é validação real.
- [x] Publicação deste checkpoint não inclui documentos, dados pessoais, decisões operacionais, runtime, backups ou segredos; runtime preservado fora do Git.
- [x] O projeto não continuará Brasil Protec. O desenvolvimento continuará LOCAL e sem hospedagem nesta fase.

## Próxima missão autorizada

Claude Code retoma exclusivamente a complementação da **Etapa 03F — DP**: estudar diretamente NBC TG 33 e tratamento nos referenciais simplificados; aprofundar os 17 fundamentos parciais; preservar fichas/casos; atualizar fontes, limitações, testes e gate. Não iniciar 03G sem revisão da 03F. Não iniciar Etapa 04 nem executar fechamento real.
