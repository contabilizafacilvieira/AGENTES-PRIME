# AGENTES PRIME

Leia `CLAUDE.md`, os procedimentos das áreas envolvidas e `GUIA-PILOTO-LOCAL.md`.
O organograma definido pelo Supervisor está em `ORGANOGRAMA-E-FLUXO.md`: Coordenador → Documentos →
Financeiro/DP/Fiscal → Contabilidade → Conciliação → Coordenador + Supervisor. Respeitar a separação de funções
e distinguir entrega parcial do piloto de fechamento integral conciliado.

- O servidor padrão usa `API-LOCAL/documentos_local.py`; não reintroduza chamadas a modelos externos como fallback silencioso.
- Preserve documentos, registros, regras propostas pelo Supervisor e alterações existentes. Testes usam somente dados fictícios.
- Não limpe RECEBIDOS, runtime ou históricos inteiros. Limpeza somente de artefatos identificados e criados pelo próprio teste.
- Piloto com empresa real permanece em SIMULAÇÃO, com autorização explícita por empresa e aprovação humana.
- Aprendizado por razão foi removido por decisão do Supervisor. Registros anteriores são preservados, sem rotas de execução.
- Histórico: em 02/11/2026 o Supervisor autorizou estudo específico do fechamento da STATE-BANK (julho-setembro). Em 03/11/2026 o
  cadastro foi ARQUIVADO em CLIENTES/_ARQUIVO-STATE-BANK-20261103-2333 (com manual, perfil e estudo); não está ativo e não deve ser
  restaurado sem decisão do Supervisor. O estudo não reativa importador de razão nem autoriza copiar saldos/valores para outubro.
- Adiantamentos automáticos foram removidos pelo Supervisor. Configurações antigas sem_suporte são inertes; não reativar. Sem classificação aplicável, manter proposta incompleta. Decisão específica por movimento permanece possível somente na conta de adiantamento indicada expressamente pelo Supervisor para a empresa (Empresas → Contas de adiantamento); grupo compatível não basta e a decisão não supre documento (lançamento INCOMPLETO).
- Não generalize as regras VGROW. Financeiro confere, Contabilidade/Bancos prepara propostas; Conciliação local confere (SIMULAÇÃO, com alcance).
- Documentos faz recepção e triagem técnica: extratos → Financeiro; folhas → DP; notas/guias → Fiscal.
  Fiscal faz conferência documental local (AGENTES/FISCAL/PROCEDIMENTO.md); DP lê demonstrativos documentados (AGENTES/DP/PROCEDIMENTO.md). Notas/guias podem ser copiadas ao Financeiro
  como suporte documental, sem simular validação fiscal. Documentos não decide natureza nem gera lançamentos.
- Fiscal não consulta autoridades, não calcula tributos por alíquotas presumidas e não usa guia como prova de pagamento/provisão.
  Contabilidade/Fiscal usa referências da própria empresa, em propostas não aprovadas. Retenções sem composição e naturezas
  ausentes permanecem pendentes. Fechamento integral de empresa real ainda depende de layouts, regras e posições não cobertos.
- Plano de etapas do Coordenador (COORDENADOR-GERAL/ferramentas/coordenador.py): áreas → Contabilidade → Conciliação; retomada
  de etapa que FALHOU ou DESATUALIZADA (fonte alterada) só pela ação do Supervisor, sobre pacote com âncora. Amostra fictícia do
  percurso completo: TESTES/AMOSTRA-COMPLETA/LEIA-ME.md (preparação explícita; nunca automática; regras marcadas TESTE_FICTICIO).
- Governança de regras (AGENTES/CONTABILIDADE/governanca_regras.py): REFERENCIA/PROPOSTA não se aplicam; APROVADA só com a frase
  "VALIDADO REGRA <AREA> <EMPRESA> <CHAVE>" (comando aprovar-regra-area / Empresas); TESTE_FICTICIO só com AMOSTRA-FICTICIA.json.
  Não invente aprovação retroativa nem converta referência histórica em regra aprovada.
- Vigência: cada etapa registra o sha256 das fontes usadas (cadastro, plano, regras); a Conciliação também a extração e o pacote.
  Fonte alterada = conferência/aprovação desatualizada, download do TXT bloqueado e etapas a rever indicadas; nunca reexecute sozinho.
- Duplicação entre SOLs da mesma empresa/competência: identidade do fato (movimento do extrato; documento + evento + competência;
  nota/apuração). Repetir fatos de SOL aprovada bloqueia; fatos que saíram em TXT revogado exigem ciência; complemento novo segue.
- TXT do Domínio (API-LOCAL/exportacao_dominio.py): partida simples por decisão de 04/11/2026, AINDA NÃO validada no Domínio;
  duas fases no registro (PREPARANDO → LIBERADO), sem sobrescrita, sem repetição automática, auditoria fora do TXT; empresa real
  (inclusive piloto) não exporta. Exportado ≠ importado ≠ escriturado.
- Documentos e dados reais de clientes nunca devem entrar em commits. Há alterações anteriores do Claude ainda pendentes de commit.
- Leitura local por página: `API-LOCAL/leitura_pdf_local.py`; PDFs mistos também passam por OCR quando necessário.
  Texto duvidoso/parcial exige conferência e não é suporte confirmado. Financeiro consome pacote e extração validados
  de Documentos. Recebido ilegível não equivale a não enviado para concluir proposta em adiantamento.
- Encerramento de revisão parcial do piloto não aprova escrituração, não resolve pendências e não conclui fechamento integral.
- Registro de solicitações: toda mutação roda sob trava EXCLUSIVA entre processos (`coordenador.trava_registro`, trava de arquivo
  do sistema operacional, prazo `AGENTES_PRIME_TRAVA_REGISTRO_TIMEOUT`, padrão 60 s). Prazo esgotado = recusa explícita
  TRAVA_REGISTRO_INDISPONIVEL, nada alterado e nada repetido automaticamente. Gravação atômica com temporário exclusivo por processo.
- Regras bancárias: VALIDADA só vale com confirmação estruturada vinculada a empresa, regra e versão (frase, responsável, data).
  Texto livre ou formato antigo ("frase" em data, sem versão/responsável) não é aplicado e aparece em Empresas → Definições
  necessárias para reconfirmar. Não altere regras da State arquivada.
- Exclusão DEFINITIVA só pela lixeira, com prévia e a frase "EXCLUIR DEFINITIVAMENTE <SOL>": recusada com aprovação vigente,
  processamento, ou TXT revogado ainda não movido. Apaga documentos, resultados, lote e saídas da SOL; fica só o REGISTRO MÍNIMO
  (número, empresa, competência, datas, justificativa e, se houve exportação, identidades/valores dos fatos e sha256 dos TXT), que
  mantém a proteção contra duplicação. Número SOL nunca é reutilizado (`sequencia_sol`). Exclusão não estorna nada no Domínio.
- Limpeza de demonstrações: `COORDENADOR-GERAL/ferramentas/arquivar_demonstracoes.py` (prévia; `--executar`), só empresas com
  AMOSTRA-FICTICIA.json, cópia de recuperação com manifesto sha256 conferido em %LOCALAPPDATA%/AgentesPrime/arquivo/.
- Importação VGROW DESATIVADA (código, regras e histórico preservados); a exportação TXT contábil continua.
- Árvore do plano: `API-LOCAL/plano_hierarquia.py` (tipo pela hierarquia, grupo contábil herdado, natureza de resultado para o
  campo `grupo` que os agentes usam, elegibilidade para composição no book). Bases antigas: ação "Reanalisar base"
  (`POST /api/empresas/<id>/base-reanalisar`), sem novo envio; o plano só recebe tipo/grupo onde estava vazio (origem AUTOMÁTICA).
  Empresa com cadastro excluído não é reanalisada (a API recusa). Conta elegível sem composição no book = ATENÇÃO (não bloqueia;
  "Marcar como conferido" com justificativa; reabre se a lista ou os saldos mudarem).
- Testes que leem o registro de solicitações usam `ambiente_isolado.registro_isolado()` / `ler_json_substituido()`: o registro é
  gravado por substituição atômica e, no Windows, abrir o arquivo no instante do `os.replace` gera PermissionError momentâneo
  (repetição limitada a ~2 s, igual à leitura de produção; JSON inválido nunca é repetido; o registro operacional é recusado).
- Excluir cadastro de empresa = exclusão LÓGICA (`empresa-local.json` com `excluida`, CADASTRO.md `Status: EXCLUIDO`, que o
  Coordenador recusa para novas solicitações). Nada é apagado; código não reutilizado. Interface de Empresas simplificada:
  importação de plano e contas de adiantamento fora da tela (código de backend preservado por compatibilidade e testes).
- BASE INICIAL (`API-LOCAL/base_inicial.py`, leitores `balancete_anterior.py` e `book_contabil.py`): competência M = balancete de
  encerramento de M−1 + book do mesmo período, por empresa, em `CLIENTES/<EMP>/BASE-INICIAL/<AAAA-MM>/` (originais em `fontes/`,
  versões em `VERSOES/`, `INDICE.json` = fonte de vigência BASE_INICIAL da Conciliação). Leitura do PDF do Domínio por posição;
  book com qualquer estrutura (fórmulas/macros/vínculos nunca executados). Nada é presumido; reimportação mostra diferenças e
  não exclui contas; só base CONFIRMADA alimenta a Conciliação. Os arquivos de referência usados para entender os layouts NÃO são
  necessários: testes usam `TESTES/BASE-INICIAL/ficticios.py` (gerados). Contas criadas no aplicativo: Domínio PENDENTE até a
  declaração do Supervisor (`conta-dominio`); o exportador recusa lançamentos nelas.
- Política de data DATA_EMISSAO_DOCUMENTO é indisponível nesta versão (os leitores não extraem a data de emissão): nunca é aplicada
  nem confirmável e não é substituída por outra data.
- Testes usam `AGENTES_PRIME_ORDEM_ATIVA` (arquivo temporário), registro e runtime temporários; nunca a ordem ativa real.
  O percurso integrado usa também `AGENTES_PRIME_CLIENTES` e `AGENTES_PRIME_LIBERADOS` temporários (nada em CLIENTES/ real).
- Fiscal e Financeiro são independentes: falha de uma área não descarta a outra; Contabilidade/Fiscal depende do Fiscal.
  O pacote de Documentos tem âncora de integridade registrada pelo Coordenador; pacote sem âncora não é tratado como verificado.
- PDF criptografado (inclusive só de proprietário) fica PDF_PROTEGIDO, sem tentativa de senha.
- O usuário zerou todos os cadastros e solicitações em 01/11/2026. As remoções em CLIENTES (exceto _MODELO) são intencionais;
  não restaure empresas de demonstração/teste por checkout ou inicialização automática. Dados anteriores estão fora do
  aplicativo, em `%LOCALAPPDATA%/AgentesPrime/backups`. Testes futuros devem preparar seus clientes fictícios de forma isolada.
