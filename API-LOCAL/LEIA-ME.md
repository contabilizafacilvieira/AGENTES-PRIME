# API LOCAL CONTROLADA · Escritório Virtual ↔ Coordenador Geral

Liga o Escritório Virtual ao fluxo real, sem dar ao navegador acesso a shell, caminhos, agentes ou estados:

```
ESCRITÓRIO VIRTUAL → API LOCAL (127.0.0.1) → coordenador.py abrir (SOL + ordem ativa)
  → documentos_local.py (extrator + OCR local conservador) → contrato DOCUMENTOS_LOCAL_V1
  → coordenador.py encerrar-local → Financeiro/Bancos (quando solicitado) → Supervisor
```

## Como usar
```
.venv/Scripts/python.exe -I API-LOCAL/servidor.py
```
Abrir o endereço impresso (`http://127.0.0.1:8765/`) no navegador **deste** computador → **Nova solicitação** →
empresa, competência, documentos, instrução → confirmar a conferência humana → **Iniciar**. A tela acompanha a SOL
até a decisão do Coordenador (documentos, códigos do extrator, pendências, motivos, auditoria e relatório).
Ctrl+C encerra a API. Aberto direto do disco, o `index.html` continua só com a simulação.

Requisitos: `.venv` e bibliotecas de `requirements.txt`. Não exige Claude CLI, login ou assinatura para operar.
O arquivo `executor.py` é legado, sem uso/fallback no servidor padrão. Cadastros, históricos e limitações:
consulte `GUIA-PILOTO-LOCAL.md`. Seções abaixo que descrevem a delegação Claude documentam o contrato legado.

Rotas adicionais: `GET /api/solicitacoes` (consulta completa), `GET/POST /api/empresas`,
`GET /api/empresas/<id>` e `POST /api/empresas/<id>/<acao>` para previa, plano, definir-conta,
bancos e piloto. As rotas de estudo por razão e parametros-bancos foram removidas e respondem 410. Não há classificação automática em adiantamentos. Mesmos controles de origem e sessão.

## Rotas (todas exigem o token de sessão no cabeçalho `X-Prime-Sessao`)
| Rota | Função |
|---|---|
| `GET /api/estado` | Empresas autorizadas, limites, solicitação em execução e recentes |
| `GET /api/empresas/<id>/base-inicial?competencia=AAAA-MM` | Base inicial: 6 etapas (feito/falta), próxima ação, definições, balancete, book, saldos |
| `POST /api/empresas/<id>/base-balancete` | Balancete de encerramento de M−1: prévia (`{competencia, nome, conteudo}`) e `{token, salvar, confirmado}` |
| `POST /api/empresas/<id>/base-contas` | Contas extraídas × plano (prévia); aplicar: `{salvar, confirmado, grupos: {âncora: grupo}, adotar: [códigos]}` |
| `POST /api/empresas/<id>/base-book` | Book do mesmo período: prévia e salvar (composições confrontadas com o balancete) |
| `POST /api/empresas/<id>/base-ciencia` | Ciência do Supervisor (`chave`, `justificativa`, `confirmado`) — nada é ajustado |
| `POST /api/empresas/<id>/base-saldo-inicial` | Saldo inicial EXPRESSO de conta ausente do balancete ou criada (inclusive zero) |
| `POST /api/empresas/<id>/base-reanalisar` | Reanálise da base já gravada com o algoritmo atual da árvore do plano (`{competencia, confirmado}`); originais intocados |
| `POST /api/empresas/<id>/base-confirmar` | Confirmação: frase `CONFIRMO BASE INICIAL <EMP> <AAAA-MM>` |
| `GET /api/empresas?excluidas=1` | Lista também os cadastros EXCLUÍDOS (histórico); sem o parâmetro, só os ativos, com competência atual da base |
| `GET /api/empresas/<id>/exclusao` · `POST .../excluir` | Prévia e exclusão LÓGICA do cadastro (`{frase: "EXCLUIR <ID>", confirmado}`); 409 com operação em andamento; nada é apagado |
| `POST /api/empresas/<id>/criar-conta` · `.../conta-dominio` | Criação expressa de conta/subconta; declaração de que existe no Domínio |
| `POST /api/lotes` | Cria lote: `{empresa, competencia (AAAA-MM), instrucao}` (nenhum outro campo) |
| `PUT /api/lotes/<lote>/arquivos` | Um arquivo por chamada: corpo bruto, `X-Nome-Arquivo`, `X-Sha256`, `Content-Length` |
| `DELETE /api/lotes/<lote>` | Descarta lote ainda não iniciado |
| `POST /api/lotes/<lote>/iniciar` | `{conferencia_humana: true}` → Coordenador abre a SOL e o processamento começa |
| `GET /api/solicitacoes/<SOL>` | Situação, motivos, documentos, inventário do extrator, pendências, auditoria e relatório |
| `POST /api/lotes` com `fluxo` | `DOCUMENTOS` (padrão) ou `FINANCEIRO_BANCOS` (empresa fictícia ou piloto real autorizado, sempre SIMULAÇÃO) |
| `GET /api/solicitacoes/<SOL>/financeiro` | Conferência do Financeiro, proposta de Bancos, tentativas, decisões e regras da empresa |
| `POST /api/solicitacoes/<SOL>/financeiro/decisoes` | Decisão do Supervisor para UM movimento (`VINCULAR` ou `CONTRAPARTIDA`) → nova tentativa |
| `POST /api/solicitacoes/<SOL>/financeiro/regras` | Proposta de regra a partir de um caso (fica PROPOSTA) |
| `POST /api/solicitacoes/<SOL>/financeiro/regras/aprovar` | Aprovação com a frase exata `VALIDADO REGRA <EMPRESA> <RB-NNN>` → nova tentativa |
| `GET /api/solicitacoes/<SOL>/financeiro/<n>/csv` | Proposta de lançamentos da tentativa n (CSV, SIMULAÇÃO) |
| `POST /api/solicitacoes/<SOL>/aprovacao` | Aprovar (frase exata `APROVO FECHAMENTO <SOL>`; `ciente_exportados: true` quando há fatos que já saíram em TXT revogado) ou revogar o fechamento. Ao aprovar, gera o TXT do Domínio (`exportacao_dominio.py`, partida simples ainda NÃO validada no Domínio) em `LIBERADOS/<EMPRESA>/<AAAA-MM>/`, só para empresa fictícia. São duas fases registradas (PREPARANDO → LIBERADO); falha fica visível e um arquivo sem registro é retirado de uso. Ao revogar, o download é bloqueado e o TXT é renomeado `_REVOGADO-<data-hora>` (nunca apagado). Se estiver travado, fica registrado que o arquivo NÃO foi movido. Revogar não estorna importação no Domínio |
| `GET /api/solicitacoes/<SOL>/txt-dominio` | Download do TXT liberado. Exige: fechamento aprovado, liberação registrada, sha256 igual ao registrado e fontes da empresa iguais às aprovadas. Senão responde 404 (sem liberação) ou 409 (bloqueado, com o motivo). Importação no Domínio sempre manual |
| `GET /api/solicitacoes/<SOL>/saidas/excel` e `.../saidas/balancete` | Excel dos lançamentos e balancete de verificação da MESMA liberação do TXT (mesmas exigências do download do TXT) |
| `GET/POST /api/solicitacoes/<SOL>/exclusao-definitiva` | Prévia (impedimentos, consequências, o que é apagado e o que permanece) e exclusão DEFINITIVA de SOL que está na lixeira, com a frase `EXCLUIR DEFINITIVAMENTE <SOL>`. Recusada com aprovação vigente |
| `/api/solicitacoes/<SOL>/importacao...` | 410: Importação VGROW desativada (código e histórico preservados) |
| `POST /api/solicitacoes/<SOL>/txt-dominio/gerar` | `{confirmado, justificativa}`: gera o TXT de novo por ação EXPLÍCITA depois de uma falha (nunca automático; nunca sobrescreve) |
| `POST /api/solicitacoes/<SOL>/txt-dominio/mover-revogado` | `{confirmado, justificativa}`: tenta de novo renomear o TXT de aprovação revogada que estava travado |
| `POST /api/empresas/<id>/regras-area` | `{area, chave, frase, confirmado}`: confirmação do Supervisor de UMA regra (DP, FISCAL, CONCILIACAO) com a frase `VALIDADO REGRA <AREA> <EMPRESA> <CHAVE>` |
| `GET /api/solicitacoes/<SOL>/conciliacao-financeira` | Central de Revisão: cards, lista e bloqueios restantes da conciliação banco × relatório da última conferência concluída do Financeiro |
| `GET /api/solicitacoes/<SOL>/conciliacao-financeira/<CF-…>` | Detalhe banco × relatório, motivos da sugestão, candidatos (ambíguo), ações permitidas |
| `POST /api/solicitacoes/<SOL>/conciliacao-financeira/<CF-…>/decisao` | `{decisao: APROVADO/REJEITADO/REVOGADO/OBSERVACAO, justificativa, revisao_conciliacao, revisao_decisoes[, candidato]}`; estado obsoleto → 409 |
| `POST /api/solicitacoes/<SOL>/conciliacao-financeira/decisoes-lote` | `{associacoes, justificativa, revisao_conciliacao, revisao_decisoes}`: aprova SOMENTE prováveis; item inválido recusa o lote inteiro |
| `GET /api/solicitacoes/<SOL>/conciliacao-financeira/<CF-…>/busca-manual` | Busca assistida (somente leitura) de registros do relatório e combinações de soma exata (até 5) para movimento NÃO CONCILIADO |
| `POST …/<CF-…>/decisao` com `manual: {auxiliares: [...]}` | Associação manual assistida: seleção explícita, soma exata, natureza compatível, registros disponíveis; estado obsoleto → 409 |
| `/api/demonstracao/associacao-manual…` | DEMONSTRAÇÃO fictícia da associação manual (pasta própria `demonstracao-associacao-manual`, irmã do runtime; `…/reiniciar`) |
| `GET /api/solicitacoes/<SOL>/conciliacao-financeira/historico` | Histórico das decisões (lote agrupado; detalhes por decisão) |
| `/api/demonstracao/conciliacao-financeira…` | Mesmas rotas para a DEMONSTRAÇÃO fictícia (motor real, dados inventados), gravada numa pasta própria irmã do runtime (`demonstracao-conciliacao`, ou `AGENTES_PRIME_DEMO_CONCILIACAO`); `POST …/reiniciar` `{confirmado: true}` apaga só essa pasta |
| `POST /api/solicitacoes/<SOL>/complementos` | `{motivo}`: abre um LOTE COMPLEMENTAR da SOL (empresa ativa, SOL não encerrada, sem processamento ativo). Os arquivos seguem pelo `PUT /api/lotes/<lote>/arquivos` de sempre (staging, formato, assinatura, tamanho, SHA) |
| `GET /api/solicitacoes/<SOL>/complementos[/<lote>]` | Complementos concluídos (classificação, SHA, tentativas que os usaram) e revisão de um lote antes de concluir (duplicidade pelo SHA: mesma SOL / mesma empresa e competência / lote anterior / novo) |
| `POST /api/solicitacoes/<SOL>/complementos/<lote>/concluir` | `{confirmado: true}`: staging → `CLIENTES/<EMP>/RECEBIDOS/<AAAA-MM>/<lote>/` (somente leitura) → Documentos → registro auditável. NÃO reprocessa; o original não muda. Falha desfaz tudo |
| `GET/POST /api/solicitacoes/<SOL>/tentativas/<NNNN>/reconciliacao-legada` | Avaliação e reconciliação auditada de tentativa ANTIGA (sem ciclo V2) que ficou ativa embora executada: evidência = motivo idêntico da retomada + `resultado_sha256` do registro = resultado da pasta; estado final derivado; frase `RECONCILIAR TENTATIVA <NNNN> <SOL>`; nada é apagado |

| `POST /api/solicitacoes/<SOL>/retomar-rota-financeira` com `parar_apos_financeiro: true` | Executa o Financeiro e PARA: Financeiro sem bloqueio → SOL aguardando o Supervisor, Contabilidade/Bancos pendente, tentativa PAUSADA. Recusada (409, nada gravado) se a SOL estiver ancorada no pacote de uma tentativa e não houver tentativa PREPARADA com pacote, se houver checkpoint pendente ou tentativa em execução |
| `POST /api/solicitacoes/<SOL>/continuar-apos-financeiro` | `{justificativa, confirmado}`: autorização do Supervisor; continua a MESMA tentativa (Bancos → Conciliação), sem repetir o Financeiro; segunda chamada recusada |
| `POST /api/lotes` com `fluxo: "FECHAMENTO"` | Upload único do fechamento do mês: Documentos recebe, confere SHA/duplicidade, classifica e distribui por departamento; NENHUMA área executa. O fechamento começa só com "Preparar fechamento" (`…/reprocessar` + `…/retomar-rota-financeira`), que planeja Fiscal → DP → Financeiro → Contábil (bancos, fiscal, DP) → Conciliação pelo pacote ancorado/congelado (o manifesto original nunca é reescrito) e, com `parar_apos_financeiro`, para no checkpoint antes de toda a Contabilidade |
| `GET /api/solicitacoes/<SOL>/previa-fechamento` | PRÉVIA DO FECHAMENTO (contrato `PREVIA_FECHAMENTO_V1`, somente leitura): status por departamento (Fiscal, Financeiro, Contábil, DP, Conciliação; sem percentual), decisões do Supervisor, checkpoints, documentos com reconhecimento (adapter existente / layout novo / não reconhecido), conciliação do balanço (book × balancete × razão), impostos, consultas do Financeiro às outras áreas (candidatos, nunca confirmação), propostas contábeis e pendências (problema, impacto, o que fazer, responsável) com proveniência. Lê só resultados REGISTRADOS desta SOL/empresa (sha256 conferido) |
| `GET /api/estado` → `ambiente` | `REAL` (padrão) ou `DEMONSTRACAO` (somente servidores de demonstração, `AGENTES_PRIME_AMBIENTE=DEMONSTRACAO`); a página recebe `<meta name="prime-ambiente">` e mostra a faixa no topo |

Tentativa nova (`POST …/reprocessar`) congela o MANIFESTO EFETIVO (lote original + complementares concluídos até aquele momento) e, havendo
complementares, um PACOTE EFETIVO imutável em `tentativas/NNNN/pacote/`. Ao iniciar a execução, o Coordenador confere e ancora esse pacote
(`reancorar-pacote`); todas as áreas usam o pacote da âncora. Complemento recebido depois só entra numa próxima tentativa.

Não existe rota para executar comando, ler arquivo por caminho, escolher agente ou alterar estado.

## Garantias
- **Rede:** escuta só em `127.0.0.1` (constante). `Host` diferente de `127.0.0.1`/`localhost` na porta é recusado
  (DNS rebinding). `Origin`/`Sec-Fetch-Site` de outra origem são recusados. Token novo a cada início, entregue só na
  página servida. Cabeçalhos: CSP restrita a `'self'`, `frame-ancestors 'none'`, `nosniff`, `no-store`.
- **Página:** lista fixa de arquivos `.html/.css/.js` do Escritório; nada fora dela é servido.
- **Upload:** formatos `pdf xml xlsx xlsm txt csv ofx png jpg jpeg`; assinatura do conteúdo conferida; 20 MB por
  arquivo, 30 arquivos e 100 MB por lote; SHA-256 calculado pelo navegador e conferido (incompleto ou corrompido
  falha sem resíduo); nome saneado com prefixo de ordem; gravação sem sobrescrita; arquivo idêntico no mesmo lote
  recusado; idêntico a outra SOL da mesma empresa sinalizado.
- **Instrução:** se citar outra empresa ou outra competência que não as selecionadas, o início é recusado.
- **Documentos:** copiados para `CLIENTES/<EMPRESA>/RECEBIDOS/<AAAA-MM>/<LOTE>/` (fora do Git), conferidos por hash
  e marcados somente leitura; o vínculo lote ↔ empresa ↔ competência ↔ SOL é gravado no runtime e conferido de novo
  no encerramento.
- **Execução:** uma por vez (trava + ordem ativa), com o executor LOCAL (`documentos_local.py`), sem modelo, e as etapas do
  plano do Coordenador (áreas → Contabilidade → Conciliação). Antes de cada etapa, o servidor fotografa o sha256 das fontes da
  empresa (`fontes.json`). Se uma fonte muda durante a execução, o resultado é recusado.
- **Registro:** só o Coordenador (CLI) grava o registro, sempre sob trava exclusiva entre processos; prazo esgotado é recusado
  explicitamente (TRAVA_REGISTRO_INDISPONIVEL) e a operação não é repetida sozinha.
- **Legado:** o executor `claude -p` (`executor.py`, guarda `agente-documentos`, SubagentHandback) não é usado e não serve de
  fallback. Esta descrição fica só como histórico do contrato anterior.
- **Runtime:** `%LOCALAPPDATA%\AgentesPrime\runtime` (lotes, transcrições, resultados). Recusado se apontar para o
  projeto ou para pasta do OneDrive.

## Testes
```
.venv/Scripts/python.exe -I TESTES/AMOSTRA-COMPLETA/testar_percurso_completo.py   # percurso integrado ISOLADO (API real)
.venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_interface_api_real.py         # TELA + API real + executores reais (isolado)
.venv/Scripts/python.exe -I TESTES/REGISTRO/testar_concorrencia_registro.py        # trava do registro entre processos
.venv/Scripts/python.exe -I TESTES/AMOSTRA-COMPLETA/testar_saidas_exclusao.py      # TXT+Excel+balancete, exclusão definitiva, limpeza
.venv/Scripts/python.exe -I TESTES/GOVERNANCA/testar_governanca_regras.py          # confirmação bancária e políticas de data
.venv/Scripts/python.exe -I TESTES/EXPORTACAO/testar_exportacao_dominio.py        # exportação TXT (unitário)
.venv/Scripts/python.exe -I TESTES/BASE-INICIAL/testar_base_inicial.py           # balancete/book/contas/base (fictícios gerados)
.venv/Scripts/python.exe -I TESTES/BASE-INICIAL/testar_percurso_base_inicial.py  # base → SOL → aprovação → 3 arquivos (API real)
.venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_interface_base_inicial.py   # cadastro e base (4 fases) pela TELA (API real)
.venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_simplificacao_empresas.py   # UI-01..12, EMP-DEL-01..12, UX-01..10 (API real)
.venv/Scripts/python.exe -I TESTES/API/testar_api.py                 # LEGADO: depende de fixture EMPRESA-TESTE removida
.venv/Scripts/python.exe -I -u TESTES/API/e2e_navegador.py <pasta>   # navegador + agente REAL (API já rodando)
```

## Riscos residuais
- Qualquer programa do mesmo usuário do Windows pode ler o token na página ou o runtime (fronteira de confiança =
  a conta do usuário).
- O Escritório agora exibe dados reais (relatório, nomes de arquivos, pendências) para o usuário local; não use em
  compartilhamento de tela com terceiros.
- O executor padrão é local, sem chamadas a modelos. O executor Claude permanece legado, sem fallback automático.
- Empresas reais do cadastro local exigem plano, vínculos bancários e autorização específica do piloto em SIMULAÇÃO;
  produção continua bloqueada. Veja `GUIA-PILOTO-LOCAL.md` para os layouts e limites.
- OCR local com confiança mínima 0,90; conteúdo não aproveitável continua pendente de conferência.

## Exclusão recuperável de solicitações

`DELETE /api/solicitacoes/<SOL>` move para a lixeira; `POST /api/solicitacoes/<SOL>/restaurar` restaura.
`POST /api/solicitacoes/limpar` move todas as ativas, de forma indivisível. Todas exigem `{"confirmado": true}`,
autenticação e ausência de execução/ordem ativa. Execuções interrompidas com status de andamento impedem a exclusão.
`GET /api/solicitacoes/lixeira` consulta a lixeira. As excluídas saem da consulta ativa, resumo e escritório.
Os metadados e eventos de exclusão/restauração ficam em `lixeira-solicitacoes.json`, no runtime.
Nenhum documento, SOL original, resultado, regra ou marca de escrituração é apagado. A numeração SOL não reinicia.
Decisões e execuções em SOL excluída são recusadas até restauração. Testes: `TESTES/LOCAL/testar_lixeira.py`.
