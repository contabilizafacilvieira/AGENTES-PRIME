# AGENTES PRIME — Etapa 02: ambiente operacional limpo

Data: 16/11/2026. Estado: preparado para revisão do Supervisor. Etapa 03 não iniciada.

## Workspace e Git

- [x] Workspace definitivo: `~/Documents/PROJETO GABRIEL - ESCRITORIO VIRTUAL/AGENTES-PRIME`.
- [x] Branch `master`, HEAD `f084245`, acompanhando `origin/master` no início da etapa.
- [x] Alterações da Etapa 01 preservadas e sem commit/push.
- [x] Fixture `TESTES/LOCAL/fixtures/plano-dominio-ficticio.xlsx` aparece como não rastreada e `git check-ignore -q` retorna código 1 (não ignorada); a exceção de `.gitignore` cobre somente este XLSX.

## Backup e ambiente anterior

- [x] Nenhum servidor do projeto ativo nas portas 8765, 8766 ou 8767; nenhum processo `servidor.py` ativo antes do backup.
- [x] Backup consistente em `~/Library/Application Support/AgentesPrime/backups/etapa-02-pre-mudanca-20261116-005555/`.
- [x] Manifesto: `manifest.json`; manifesto e hashes validados localmente, sem conteúdo publicado.
- [x] Conteúdo e manifesto do backup conferidos por hashes com as fontes locais; nenhum conteúdo de backup é versionado.
- [x] Restauração simulada em diretório temporário: itens do manifesto foram recopiados e revalidados; fontes originais permaneceram intactas.
- [x] Runtime anterior preservado em `~/Library/Application Support/AgentesPrime/runtime`.
- [x] Os dados e históricos operacionais arquivados foram preservados no backup local, sem remoção ou cópia para o Git. Nenhum dado operacional foi movido ou apagado.
- [x] Situação anterior preservada: cadastro e solicitações arquivadas preservados no ambiente anterior.

## Perfil REAL novo

- [x] Diretório-base: `~/Library/Application Support/AgentesPrime/ambientes/REAL/`.
- [x] Runtime novo: `~/Library/Application Support/AgentesPrime/ambientes/REAL/runtime/`.
- [x] Raízes separadas para `CLIENTES`, `CONTROLE` e `LIBERADOS`; registro inicial vazio (`solicitacoes={}`, `sequencia_sol={}`).
- [x] Lançador fora do Git: `~/Library/Application Support/AgentesPrime/launchers/iniciar-agentes-prime-real.command`.
- [x] 0 empresas ativas, 0 solicitações ativas, 0 fechamentos, 0 documentos, 0 pendências e 0 execuções no perfil REAL novo.
- [x] A preparação da amostra fictícia está bloqueada pela API e oculta na interface quando o perfil é REAL.
- [x] DEMO fica em raízes próprias dos servidores de demonstração; TESTE usa diretórios temporários de `TESTES/ambiente_isolado.py`. Nenhum arquivo real foi copiado para DEMO ou TESTE.
- [x] Interface inicial validada como escritório vazio, sem tarefas; a ação principal é “Cadastrar empresa”.

## Validação

- [x] Fixture Domínio em TESTE: 14/14.
- [x] Separação de ambientes: bloqueio REAL, permissão DEMONSTRAÇÃO/TESTE e recusa HTTP de GET/POST fictício no REAL.
- [x] Backup, hash e simulação de restauração aprovados.
- [x] Gate completo final: 75 baterias, 75 aprovadas, 0 falhas; estado do workspace anterior intocado.
- [x] Nenhum fechamento real; empresa piloto arquivada não continuada; nenhuma comunicação externa; nenhum commit/push.
- [ ] Revisão e aceite do Supervisor.

Próxima ação: aguardar a revisão do Supervisor. Não iniciar a Etapa 03 antes do aceite explícito.
