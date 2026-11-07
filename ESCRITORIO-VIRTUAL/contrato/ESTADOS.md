# ESTADOS OPERACIONAIS · contrato 1.0

> Os 8 estados visuais do Escritório Virtual V1 continuam os mesmos. Este documento define **de onde cada um vem**
> quando houver estado real. Status V2.0: somente documentação.

## 1. Classificação
| Grupo | Estados | Origem |
|---|---|---|
| **Publicáveis** | `LIVRE`, `TRABALHANDO`, `AGUARDANDO_SUPERVISOR`, `PENDENCIA`, `CONCLUIDO`, `ERRO` | Publicador, por decisão do Coordenador Geral |
| **Derivado** | `OFFLINE` | Calculado pelo frontend a partir da validade do estado. **Nunca publicado** |
| **Catálogo** | `NAO_IMPLEMENTADO` | Vem do catálogo de agentes (`implementado: false`). **Nunca publicado** |

Se um documento de estado trouxer `OFFLINE` ou `NAO_IMPLEMENTADO`, o publicador recusa e o frontend descarta o documento.

## 2. Significado e autoridade
| Estado | Significado operacional exato | Quem decide | Exigências no estado |
|---|---|---|---|
| **LIVRE** | Agente sem solicitação atribuída | Coordenador (encerramento) ou estado inicial | `trabalho = null` |
| **TRABALHANDO** | Solicitação delegada e em execução | Coordenador, ao delegar | Ordem ativa válida para a mesma empresa e SOL; `etapa` |
| **AGUARDANDO_SUPERVISOR** | Trabalho parado à espera de decisão ou aprovação do Supervisor | Coordenador | `codigo` de aguardo; `lote_id` quando for aprovação de lote |
| **PENDENCIA** | Execução parou ou terminou com informação ausente ou divergência registrada | Coordenador, após o relatório | `codigo` de pendência; `pendencias ≥ 1` |
| **CONCLUIDO** | Resultado entregue ao Coordenador, sem pendência que bloqueie | Coordenador | Permanece até o encerramento da SOL |
| **ERRO** | Execução falhou, foi bloqueada, expirou ou foi interrompida | Coordenador ou reconciliação | `codigo` de erro |
| **OFFLINE** | Sem sessão ativa do Coordenador ou estado vencido | Frontend (derivação, CONTRATO-ESTADO.md §7) | — |
| **NAO_IMPLEMENTADO** | Agente previsto, ainda não existente | Catálogo de agentes | — |

O Coordenador Geral também aparece em `agentes` (id `coordenador`) com os mesmos estados; seu `trabalho` descreve a
solicitação que ele está coordenando.

## 3. Matriz de transições (por agente, mesma SOL)
| De ↓ / Para → | LIVRE | TRABALHANDO | AGUARDANDO | PENDENCIA | CONCLUIDO | ERRO |
|---|---|---|---|---|---|---|
| **LIVRE** | — | ✅ início | ❌ | ❌ | ❌ | ⚠️ só reconciliação |
| **TRABALHANDO** | ⚠️ só cancelamento | — | ✅ | ✅ | ✅ | ✅ |
| **AGUARDANDO** | ✅ cancelamento | ✅ retomada | — | ✅ | ✅ aprovação | ✅ |
| **PENDENCIA** | ✅ encerramento | ✅ retomada com a informação | ✅ | — | ✅ aceite com pendência registrada | ✅ |
| **CONCLUIDO** | ✅ encerramento | ❌ (nova SOL) | ❌ | ❌ | — | ❌ |
| **ERRO** | ✅ ciência ou cancelamento | ✅ só com nova ordem ativa | ❌ | ❌ | ❌ | — |

Legenda: ✅ permitida · ⚠️ permitida só no caso indicado · ❌ recusada pelo publicador.

## 4. Transições suspeitas ou proibidas (recusar e registrar)
- Trocar `empresa_id` ou `solicitacao_id` sem passar por `LIVRE`.
- `TRABALHANDO` sem ordem ativa correspondente (empresa e SOL) ou com ordem vencida.
- Segundo agente entrando em `TRABALHANDO` enquanto outro já está (limite da V2: um por vez).
- Reutilizar uma SOL encerrada, ou uma SOL com outra empresa.
- `CONCLUIDO → TRABALHANDO` na mesma SOL.
- `sequencia` menor ou igual à última publicada na mesma `instancia`.
- Qualquer tentativa de publicar `OFFLINE` ou `NAO_IMPLEMENTADO`.
- Publicar estado de agente com `implementado: false` no catálogo.

## 5. Situações especiais
| Situação | Tratamento previsto |
|---|---|
| **Erro do agente** | Coordenador recebe a falha e publica `ERRO` com `FALHA_AGENTE` (ou `GUARDA_BLOQUEIO` se o guarda recusou) |
| **Cancelamento** | Supervisor cancela na conversa; Coordenador publica `LIVRE` (evento de cancelamento no futuro log) e remove a ordem ativa pelo protocolo homologado |
| **Ordem expirada** | `TRABALHANDO` com `valida_ate` vencido → `ERRO` / `ORDEM_EXPIRADA` na próxima publicação ou reconciliação |
| **Timeout** | Duração acima do limite configurado → frontend sinaliza "possivelmente travado"; Coordenador decide `ERRO` / `TIMEOUT` |
| **Agente encerrado inesperadamente** | Tratado como erro (`FALHA_AGENTE`); nunca deixar `TRABALHANDO` sem dono |
| **Coordenador reiniciado** | Ao iniciar, **reconciliação**: se o estado diz `TRABALHANDO` e não há agente em execução → `ERRO` / `INTERROMPIDO`; o Supervisor decide reemitir (nova ordem) ou cancelar |
| **Frontend aberto depois do fim** | Mostra o último retrato com "atualizado há X"; se vencido, `OFFLINE` com "último estado conhecido" |
| **Recuperação após erro** | `ERRO → LIVRE` (ciência/cancelamento) ou `ERRO → TRABALHANDO` apenas com **nova** ordem ativa válida |
