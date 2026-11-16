# AGENTES PRIME — HANDOFF DE DESENVOLVIMENTO PARA CLAUDE CODE

Atualizado em 16/11/2026 para checkpoint de desenvolvimento. Este documento resume o código e as decisões de etapa sem copiar conteúdo de clientes, runtimes ou backups.

## Identidade e localização

- Repositório: `https://github.com/contabilizafacilvieira/AGENTES-PRIME.git`
- Workspace definitivo: `/Users/priscilavieiralino/Documents/PROJETO GABRIEL - ESCRITORIO VIRTUAL/AGENTES-PRIME`
- Branch: `master`
- Base anterior conhecida: `f08424541b087c7fe917c0e403234aa4f8885ac9` (`origin/master` antes deste checkpoint).
- Tag operacional existente `v1.8.0-interno` aponta para `e009995a5b2be86b433744a36fef74954162a44b`, anterior à base `master`. Não mover, recriar ou substituir a tag. Este envio é checkpoint de desenvolvimento, não release operacional.
- O checkpoint publicado deve ser o novo ponto de continuidade quando o push terminar. Consulte `git log`, `git status` e o commit corrente em vez de usar este SHA-base como estado atualizado.

## Instruções essenciais

Ler primeiro `AGENTS.md`, `CLAUDE.md`, `ORGANOGRAMA-E-FLUXO.md`, procedimentos dos departamentos envolvidos, `GUIA-PILOTO-LOCAL.md`, `TESTES/GATE-RELEASE.md` e `TESTES/CHECKLIST-MESTRE.md`. Preservar todo o histórico e alterações anteriores. Não executar `reset --hard`, não forçar push e não tratar conhecimento histórico, sugestão ou regra de empresa como regra geral aprovada.

**O projeto NÃO continuará Brasil Protec.** Não acessar, anexar, reprocessar ou divulgar documentos/dados da empresa piloto arquivada. Não generalizar regras específicas de empresa. O desenvolvimento permanecerá **LOCAL**; não haverá hospedagem online nesta fase. GitHub é apenas o repositório de código, documentação e testes fictícios.

## Arquitetura e responsabilidades

Fluxo: Supervisor → Coordenador Geral → Documentos → Fiscal / DP / Financeiro → Contábil (especialidades) → Conciliação → Supervisor. Fechamento é processo, não departamento.

- Coordenador: orquestra e mantém estado auditável.
- Documentos: recepção, proveniência e roteamento; não determina natureza nem lança.
- Fiscal: identifica fatos fiscais e documentos; não decide classificação contábil.
- DP: confere somente layouts documentados de folha e entrega fatos/pendências; não calcula folha, taxas, encargos ou rescisões.
- Financeiro: identifica liquidações/evidências; movimento bancário não determina natureza.
- Contábil: produz propostas supervisionadas.
- Conciliação: valida saldos, composição e evidência; conciliação aritmética não prova suporte suficiente.

Componentes centrais: `COORDENADOR-GERAL/ferramentas/coordenador.py`, API local `API-LOCAL/servidor.py`, contratos/adapters `API-LOCAL/adaptadores_fechamento.py`, roteamento `API-LOCAL/documentos_local.py`, intercâmbio `API-LOCAL/intercambio.py`, prévia `API-LOCAL/previa_fechamento.py`, reprocessamento/complementos e interface em `ESCRITORIO-VIRTUAL/`.

## Ambiente de desenvolvimento e execução

- Python oficial verificado: 3.12.16.
- Ambiente virtual reproduzível: `.venv/` na raiz, ignorado pelo Git. Instale dependências a partir dos arquivos versionados `requirements*.txt`/instruções do projeto; valide com `.venv/bin/pip check` (macOS/Linux) ou `.venv\\Scripts\\python.exe -m pip check` (Windows).
- Gate oficial: `.venv/bin/python -I TESTES/executar_gate.py` (macOS/Linux) ou `.venv\\Scripts\\python.exe -I TESTES\\executar_gate.py` (Windows). O script seleciona o interpretador da `.venv` por plataforma.
- O projeto permanecerá LOCAL. Não adicionar hospedagem, serviços externos, chamadas de modelos externos ou upload de dados.
- Runtime é dado operacional local fora do Git. Nunca copie, limpe, regenere ou inclua runtime em commits.
- Runtime anterior: `$HOME/Library/Application Support/AgentesPrime/runtime`.
- Perfil REAL limpo: `$HOME/Library/Application Support/AgentesPrime/ambientes/REAL/runtime` (diretório-base do ambiente em `.../ambientes/REAL/`). Lançador: `$HOME/Library/Application Support/AgentesPrime/launchers/iniciar-agentes-prime-real.command`.
- Backup Etapa 02: `$HOME/Library/Application Support/AgentesPrime/backups/etapa-02-pre-mudanca-20261116-005555/`; manifesto e hashes foram validados localmente. Não publicar nem copiar seu conteúdo.
- Auditoria read-only deste handoff: listener REAL ativo em 127.0.0.1:8765; portas 8766/8767 sem listener. API reportou 0 empresas visíveis, 0 solicitações recentes/abertas e nenhuma execução ativa. Nenhum documento foi consultado e runtime não foi alterado. Revalidar contagens antes de assumir operação.
- Para contagens atuais do REAL, use somente consulta local/read-only e exponha apenas agregados. Não use o REAL para fixtures ou testes.
- Servidores de demonstração têm raízes próprias. Testes devem usar `TESTES/ambiente_isolado.py` e diretórios temporários. Consulte processos/portas antes de iniciar servidor; PIDs não são estáveis.

## Isolamento REAL / DEMONSTRAÇÃO / TESTE

`API-LOCAL/servidor.py` define `AMBIENTE` (`REAL`, `DEMONSTRACAO`, `TESTE`); o perfil REAL é padrão e fail-closed. DEMONSTRAÇÃO/TESTE usam raízes separadas. A preparação da amostra fictícia é recusada na API e ocultada na interface quando REAL. O gate coloca `AGENTES_PRIME_MODO_TESTE=1` nos processos filhos. Não promova dados de uma raiz para outra. Cadastro/fechamento real só sob autorização específica aplicável e supervisão; esta etapa de handoff não autoriza tais operações.

Interface existente é o Escritório Virtual local. No perfil REAL novo, a página inicial deve estar vazia e destacar “Cadastrar empresa”; agentes aguardam solicitação e não simulam trabalho. Identificação de ambiente fica visível na interface. Preserve o design e os contratos existentes.

## Estado da base normativa e departamentos

`BASE_CONHECIMENTO_CONTABIL/` possui sete categorias, esquema JSON, catálogo de fontes oficiais, inventário, interface Python somente leitura e fichas/casos consultáveis. Fichas não autorizam decisões automáticas.

| Etapa | Estado do Supervisor / escopo registrado |
|---|---|
| 01 | APROVADA — ambiente reproduzível, Python 3.12.16, fixture fictícia Domínio |
| 02 | APROVADA — ambiente REAL limpo; backup íntegro; separação REAL/DEMO/TESTE; Brasil Protec preservada fora deste repo |
| 03A | Estrutura normativa consultável concluída |
| 03B | Priorização do inventário de 158 tópicos concluída; cobertura normativa geral incompleta |
| 03C | Contábil aprovado no escopo: 20 fundamentos, 12 casos fictícios |
| 03D | Financeiro aprovado no escopo: 20 fundamentos, 15 casos fictícios |
| 03E | Fiscal aprovado com ressalvas: 5 fundamentos verificados, 20 parciais, 20 casos fictícios; ver checklist específico |
| 03F | **BLOQUEADA**: DP 3 fundamentos verificados de forma limitada, 17 parciais, 15 casos fictícios. Falta estudo substantivo de NBC TG 33 e de benefícios a empregados nos referenciais simplificados aplicáveis |
| 03G | Conciliação PENDENTE; NÃO INICIADA |
| 04 | Métodos de contabilização PENDENTE |
| 05 | Integração dos agentes PENDENTE |
| 06 | Cadastro e onboarding PENDENTE |
| 07 | Inicialização automática e atalho PENDENTE |
| 08 | Segurança e testes finais PENDENTE |
| 09 | Operação real PENDENTE, depende de validação e autorização futura |
| Hospedagem externa | ADIADA; projeto continua LOCAL |

FISC-01–25 e DP-01–20 são consultáveis em `consulta.py`; casos fictícios em `casos_fiscais.json` e `casos_dp.json`. DP mantém `STATUS_DP_CONTEXTUAL_V1`: `NAO_APLICAVEL` exige motivo/decisão do Supervisor; evidência contraditória gera conflito e aguarda Supervisor. O parser DP, seus adapters e procedimento não foram reconstruídos.

Ressalvas fiscais persistem: UF/município, competência, regime, atividade, operação, regras CONFAZ e créditos/incidências específicos exigem contexto e fonte competente; tratamento parcial não é fundamento suficiente. As fichas normativas ainda necessitam auditoria independente e revisão por especialista. Sucesso com fixtures não valida fechamento real. Qualquer validação operacional real futura será uma etapa própria, supervisionada e expressamente autorizada.

## Contratos, adapters e limites

- Preserve interfaces normalizadas e adapters existentes; uma alteração de contrato exige testes de compatibilidade e atualização coordenada de consumidores.
- DP aceita apenas os layouts e campos descritos em `AGENTES/DP/PROCEDIMENTO.md`, valida somas declaradas com igualdade Decimal e mantém pendências; não infere zeros ou rubricas.
- Fiscal/Financeiro/Contábil mantêm propriedade de fatos e intercâmbio conforme procedimentos; um departamento não altera o fato publicado por outro.
- Regras de empresa ficam isoladas em `CLIENTES/<EMP>/`; estados `REFERENCIA`/`PROPOSTA` não são `APROVADA`. Não converter sugestão em regra aprovada.
- Aprovação humana é obrigatória; exportado não significa importado ou escriturado. Nesta fase não executar fechamentos, particularmente nenhum fechamento real.

## Testes e gate

Antes do checkpoint, o gate completo da Etapa 03F foi executado uma única vez com `.venv` Python 3.12.16: **79/79 baterias aprovadas, zero falhas, estado operacional intocado; `GATE DE RELEASE: APROVADO`**. `pip check` não encontrou dependências quebradas; `git diff --check` limpo. Saídas temporárias locais, não versionadas.

Esse gate não aprova conteúdo normativo incompleto: Etapa 03F continua BLOQUEADA e 03G não pode começar antes da revisão da complementação DP. Não enfraquecer testes nem relatar aprovações fora do escopo.

## Git e publicação

- Branch alvo: `master`; remoto `origin` é o repositório oficial acima.
- Última base antes do handoff: commit `f08424541b087c7fe917c0e403234aa4f8885ac9`; `origin/master` estava alinhada.
- `v1.8.0-interno` é uma tag histórica imutável no commit anterior. Não criar tags operacionais neste checkpoint.
- O Supervisor autorizou o commit/push apenas para esta transferência depois das auditorias e gate. Mensagem: `feat: consolida base normativa e preparacao multiempresa`.
- Adicionar arquivos explicitamente auditados; revisar `git diff --cached --check`, `--stat` e `--name-status`. Não usar `git add .`.
- Nunca publicar documentos reais, nomes/identificadores de cliente, CNPJ/CPF reais, dados pessoais, decisões ou regras específicas, logs sensíveis, runtime, backups, snapshots, credenciais, `.env` ou `.venv`.
- Sem `--force`. Depois do push: `git fetch origin`, comparar `git rev-parse HEAD` e `git rev-parse origin/master`, conferir `git status` limpo e confirmar que a tag permaneceu intocada.

## Próxima missão exata do Claude Code

Retomar **ETAPA 03F — COMPLEMENTAÇÃO NORMATIVA DP**, e somente após este checkpoint ser recebido e o Supervisor revisar a publicação. Priorizar leitura direta dos textos oficiais CFC NBC TG 33 e tratamentos correspondentes nos referenciais simplificados aplicáveis; aprofundar os 17 fundamentos parciais; preservar 20 fichas e 15 casos fictícios; atualizar fontes/limitações; testar consultas, regressões e gate; atualizar checklist com evidência. Não é necessário cobrir toda a legislação trabalhista antes de qualquer avanço, mas é necessária fundamentação contábil suficiente para folha, encargos, férias e 13º.

Não iniciar Etapa 03G antes da revisão/aprovação da complementação DP. Não iniciar Etapa 04. Não continuar Brasil Protec. Não migrar para hospedagem externa. Não executar fechamento real.
