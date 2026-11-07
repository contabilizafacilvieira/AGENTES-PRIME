# CATÁLOGOS · contrato 1.0

> Catálogos são dados **controlados e versionados no projeto**, nunca produzidos por agentes. Todos os exemplos
> abaixo são **fictícios**. Status V2.0: somente documentação (nenhum arquivo de catálogo foi criado).

## Princípio
**Todo texto mostrado ao Supervisor é uma tradução local de um código controlado.** O estado operacional transporta
códigos (`etapa`, `codigo`, `empresa_id`, `id` de agente); o frontend procura cada código no catálogo e exibe o texto
correspondente. Código ausente no catálogo → texto neutro ("Etapa não reconhecida"), nunca o código cru como HTML e
nunca texto vindo de agente.

## 1. Catálogo de agentes
Fonte única de `nome`, `tipo` e `implementado`. O estado não pode alterar nenhum desses atributos.

| id | nome | tipo | implementado |
|---|---|---|---|
| `coordenador` | Coordenador Geral | coordenador | sim |
| `documentos` | Agente de Documentos | especialista | sim (piloto real supervisionado só na VGROW) |
| `importacao` | Importação VGROW | especialista interno da Contabilidade | sim (SIMULAÇÃO, só VGROW) |
| `fiscal` | Agente Fiscal | especialista (fornece informações à Contabilidade) | não |
| `dp` | Agente de Departamento Pessoal | especialista (fornece informações à Contabilidade) | não |
| `financeiro` | Agente Financeiro | especialista (fornece informações à Contabilidade) | não |
| `conciliacao` | Agente de Conciliação | especialista (confere os lançamentos; divergências via Coordenador) | não |

A Contabilidade é uma **área** (lançamentos), não um agente: seus especialistas internos são a Importação VGROW e,
no futuro, Bancos, Impostos, Folha, Notas de entrada e Notas de saída. Atualizado em 31/10/2026.

Agentes com `implementado: não` aparecem sempre como `NAO_IMPLEMENTADO` ("Em breve") e não podem aparecer no estado.
A posição na planta (postos) continua sendo dado visual do frontend, separado deste catálogo.

## 2. Catálogo de exibição de empresas
Única fonte do nome amigável. Contém **apenas** `empresa_id → empresa_exibicao`; proibido qualquer dado fiscal ou
cadastral (CNPJ, razão social, IE, regime, endereço, contato).

| empresa_id | empresa_exibicao |
|---|---|
| `EMPRESA-TESTE` | Empresa Teste |
| `EMPRESA-ISOLAMENTO` | Empresa Isolamento |

Mantido pelo Coordenador Geral; `empresa_id` desconhecido no catálogo invalida o documento de estado.
Opção futura de interface: "modo discreto", exibindo só o `empresa_id`.

## 3. Catálogo de etapas
| Código | Tipo de agente | Texto exibido |
|---|---|---|
| `TRIAGEM` | coordenador | Analisando a solicitação |
| `DELEGACAO` | coordenador | Preparando a ordem de serviço |
| `ACOMPANHAMENTO` | coordenador | Acompanhando o agente responsável |
| `CONSOLIDACAO` | coordenador | Consolidando resultados |
| `APRESENTACAO` | coordenador | Apresentando resultado ao Supervisor |
| `INVENTARIO` | documentos | Inventariando documentos |
| `ANALISE_DOCUMENTAL` | documentos | Analisando documentos |
| `RELATORIO` | documentos | Preparando relatório |

Etapa incompatível com o tipo do agente → recusada pelo publicador.

## 4. Catálogo de códigos
| Código | Status permitido | Texto exibido |
|---|---|---|
| `AGUARDA_APROVACAO_LOTE` | AGUARDANDO_SUPERVISOR | Aguardando aprovação do lote |
| `AGUARDA_DECISAO` | AGUARDANDO_SUPERVISOR | Aguardando decisão do Supervisor |
| `AGUARDA_INFORMACAO` | AGUARDANDO_SUPERVISOR, PENDENCIA | Aguardando informação |
| `AGUARDA_DOCUMENTO` | PENDENCIA | Aguardando documento |
| `DIVERGENCIA_REGISTRADA` | PENDENCIA | Divergência registrada |
| `CONCLUIDO_SEM_PENDENCIA` | CONCLUIDO | Concluído sem pendências |
| `CONCLUIDO_COM_PENDENCIA_ACEITA` | CONCLUIDO | Concluído com pendência registrada |
| `FALHA_AGENTE` | ERRO | Falha na execução do agente |
| `GUARDA_BLOQUEIO` | ERRO | Operação bloqueada pela proteção do sistema |
| `ORDEM_EXPIRADA` | ERRO | Ordem de serviço expirada |
| `TIMEOUT` | ERRO | Tempo limite excedido |
| `INTERROMPIDO` | ERRO | Execução interrompida |

Os textos dizem **o que** aconteceu, nunca **o conteúdo** (sem nomes de documentos, CNPJs, valores ou trechos de relatório).
Detalhes continuam disponíveis apenas na conversa com o Coordenador Geral.

## 5. Versionamento dos catálogos
Cada catálogo tem versão própria. Acrescentar código/etapa/empresa = versão menor; remover ou mudar significado =
versão maior. O frontend precisa conhecer um código **antes** de o publicador passar a usá-lo.
