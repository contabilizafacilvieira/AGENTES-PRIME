# SEGURANÇA · contrato de estado operacional 1.0

> Status V2.0: somente documentação. Complementa as proteções já homologadas (guarda do Agente de Documentos,
> ordem ativa, isolamento entre empresas), que **não mudam** nesta etapa.

## 1. Princípios
1. **Somente leitura na exibição.** O Escritório Virtual não cria nem altera ordens, não chama agentes, não executa
   ferramentas, não grava em `CLIENTES/` ou `LIBERADOS/`, não altera pendências, não aprova nada, não lê documentos de
   clientes nem `ordem-ativa.json`, e não contorna o Coordenador Geral nem o guarda.
2. **Um único gravador.** Só o publicador determinístico (futuro) grava o estado; o Coordenador decide, agentes nunca publicam.
3. **Minimização garantida por estrutura.** O publicador só aceita identificadores, códigos de catálogo, inteiros e
   datas. Texto livre não tem por onde passar.
4. **Desconfiança em cada etapa.** O frontend revalida tudo o que recebe.
5. **O Escritório não é canal de decisão.** Aprovações e validações continuam exclusivamente na conversa.

## 2. Proibições explícitas
- Ler, copiar ou resumir **transcrições** de sessões/subagentes (`~/.claude/projects/...`) para compor estado.
- Enviar ao frontend **relatórios de agentes**, documentos, nomes de arquivos ou caminhos.
- Enviar ao frontend CNPJ, razão social, dados fiscais/cadastrais, descrição de pendência, valores, números de nota.
- Expor `ordem-ativa.json` ao frontend (o publicador apenas o **lê** para conferência).
- Guardar o estado real ou o log de eventos no repositório, em `CLIENTES/`, em `TESTES/` ou em pastas sincronizadas.

## 3. Isolamento entre empresas
- O estado identifica empresas **só por `empresa_id`**; o nome amigável vem do catálogo de exibição.
- **SOL global** (`SOL-AAAA-NNNNNN`), única no projeto, nunca reutilizada.
- **Vínculo imutável** `solicitacao_id ↔ empresa_id`, registrado pelo publicador na criação e conferido a cada publicação.
- Todo trabalho é identificado pelo par (`empresa_id`, `solicitacao_id`).
- Cada publicação substitui o retrato inteiro; o frontend não mescla nem guarda dados entre retratos.
- **V2: 1 agente em execução, 1 ordem ativa, 1 solicitação operacional ativa.** Multiagente simultâneo exige
  ordem ativa por instância de agente no guarda e **nova homologação de segurança** (fase futura).

## 4. Modelo de ameaças
| Ameaça | Impacto | Mitigação |
|---|---|---|
| Frontend adulterado | Exibe informação falsa (não consegue gravar nem agir) | Escritório apenas informativo; decisões só na conversa; integridade do frontend pelo Git |
| Arquivo de estado adulterado | Tela enganosa; no canal JS, possível execução de código | Mesma fronteira de confiança do próprio frontend; serialização segura; validação estrita; `sequencia`; runtime com acesso restrito ao usuário; **spike obrigatório** antes de dados reais |
| Estado antigo | Supervisor acredita que algo está em andamento | `gerado_em` + `valido_por_segundos`; aviso "desatualizado"; OFFLINE derivado |
| Path traversal | Leitura de arquivos indevidos | Navegador não recebe caminhos; publicador não aceita caminhos; servidor futuro com lista fixa de caminhos |
| Injeção de HTML/script | Execução na página | Sem texto livre no contrato; frontend usa apenas `textContent`; textos vêm de catálogos locais |
| Agente publicando dados | Vazamento ou falsificação | Agentes sem ferramenta de gravação; publicador só aceita códigos |
| Mistura de empresas | Dado associado à empresa errada | Par (empresa, SOL) imutável; conferência com a ordem ativa; retrato substituído inteiro |
| Concorrência entre publicações | Retrato inconsistente | Publicador único com trava em `travas/`; `sequencia` estritamente crescente |
| Duas solicitações para o mesmo agente | Estado ambíguo | Publicador recusa; guarda já impõe uma ordem ativa |
| Arquivo parcialmente escrito | Página quebrada ou retrato corrompido | Escrita em temporário + renomeação atômica; frontend mantém o último retrato válido |
| Queda durante a atualização | Retrato velho | Renomeação atômica; reconciliação ao reiniciar |
| Reinício do computador | `TRABALHANDO` órfão | Reconciliação → `ERRO` / `INTERROMPIDO`; Supervisor decide |
| Duas abas abertas | Nenhum (só leitura) | — |
| Dados sensíveis na tela | Exposição em compartilhamento de tela | Nenhum dado fiscal no estado; modo discreto opcional |
| Sincronização em nuvem | Estado operacional enviado à nuvem; conflitos de arquivo | Runtime fora do OneDrive e de outras pastas sincronizadas |
| Configuração de runtime inválida | Gravação em local indevido | Falha fechada: o publicador recusa e informa, sem alternativa silenciosa |
| Parâmetro de URL apontando arquivo | Carregar script arbitrário | Proibido indicar o arquivo de estado por URL |

## 5. Escrita atômica (futura)
1. Validar o documento completo em memória.
2. Gravar em arquivo temporário na mesma pasta do destino.
3. Forçar a gravação em disco.
4. Renomear para o nome final (substituição atômica no mesmo volume).
5. Em qualquer falha: não renomear; o retrato anterior continua válido; registrar o erro.

## 6. Sequência e validade
- `sequencia` estritamente crescente dentro da mesma `instancia` do runtime; o frontend descarta retratos com
  sequência menor ou igual.
- `instancia` muda quando o runtime é recriado; o frontend reinicia a referência de sequência.
- Validade e OFFLINE conforme CONTRATO-ESTADO.md §7.

## 7. Verificações obrigatórias antes de usar dados reais
- Spike do canal aprovado (CONTRATO-ESTADO.md §11).
- Testes do publicador: formatos, campos proibidos, transições, vínculo SOL/empresa, limite de concorrência, escrita atômica.
- Auditoria de vazamento: busca por padrões de CNPJ, CPF, valores e texto livre em todos os retratos de teste.
- Testes de isolamento com EMPRESA-TESTE e EMPRESA-ISOLAMENTO.
- Aprovação explícita do Supervisor para a mudança no protocolo do Coordenador.
