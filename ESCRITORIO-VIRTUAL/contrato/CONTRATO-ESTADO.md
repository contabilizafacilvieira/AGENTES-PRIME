# CONTRATO DE ESTADO OPERACIONAL · versão 1.0

> Documento normativo. Status V2.0: **nenhum componente deste contrato está implementado.**
> Todos os exemplos são **fictícios**.

## 1. Objetivo
Permitir que o Escritório Virtual represente visualmente o trabalho real do Coordenador Geral e dos agentes,
recebendo **apenas o mínimo necessário**: quem está fazendo o quê, para qual empresa (por identificador), em que
competência, em que estado e desde quando. Nada além disso.

## 2. Fronteiras de confiança
```
[ZONA DE DADOS DO CLIENTE]            [ZONA DE CONTROLE]                 [ZONA DE EXIBIÇÃO]
 CLIENTES/, LIBERADOS/,               Coordenador Geral                  Escritório Virtual
 relatórios dos agentes,      ──►     + Publicador (futuro)      ──►     (navegador, somente leitura)
 transcrições, ordem-ativa.json        valida e reduz a códigos
         NUNCA atravessa                    ÚNICO ponto que              confia apenas no que
         para a exibição                    atravessa a fronteira        passa na validação
```
- Nada da zona de dados do cliente chega à exibição, nem resumido: só identificadores e códigos de catálogo.
- O Escritório **não é canal de decisão**. Aprovações (`APROVADO LOTE-XXX`) e validações continuam somente na conversa
  com o Coordenador Geral.

## 3. Papéis
| Papel | Responsabilidade | Proibições |
|---|---|---|
| **Coordenador Geral** | Autoridade semântica: decide início, etapa, espera, pendência, conclusão, erro, encerramento | Escrever o arquivo de estado diretamente; enviar texto livre ao publicador |
| **Publicador (futuro)** | Único gravador. Recebe comandos com argumentos controlados, valida formato e transição, confere a ordem ativa, grava de forma atômica, incrementa a sequência | Aceitar campo fora do schema, texto livre, caminho de arquivo; ler conteúdo de `CLIENTES/` |
| **Agentes** | Executam a tarefa; relatam ao Coordenador | Publicar estado; ter ferramenta de gravação (já é assim) |
| **Frontend** | Lê, valida de novo, exibe; deriva OFFLINE e tempos | Gravar qualquer coisa; aceitar dado fora do contrato; interpretar dado como HTML |

## 4. Schema 1.0

### 4.1 Documento (raiz)
| Campo | Tipo | Obrig. | Regra |
|---|---|---|---|
| `contrato` | string | ✅ | Exatamente `agentes-prime/estado-operacional` |
| `versao` | string | ✅ | `MAIOR.MENOR`; esta especificação é `1.0` |
| `modo` | enum | ✅ | `SIMULACAO` ou `REAL` |
| `instancia` | string | ✅ | Identificador aleatório do runtime (`^[a-f0-9]{16}$`), muda se o runtime for recriado |
| `sequencia` | inteiro | ✅ | ≥ 1, estritamente crescente dentro da mesma `instancia` |
| `gerado_em` | data-hora | ✅ | ISO 8601 com fuso (ex.: `2026-10-31T09:14:05-03:00`) |
| `valido_por_segundos` | inteiro | ✅ | 60 a 3600 |
| `agentes` | lista | ✅ | 1 a 32 itens, `id` únicos |

### 4.2 Agente (item de `agentes`)
| Campo | Tipo | Obrig. | Regra |
|---|---|---|---|
| `id` | string | ✅ | `^[a-z][a-z0-9-]{1,30}$` e presente no **catálogo de agentes** |
| `status` | enum | ✅ | Apenas os **publicáveis**: `LIVRE`, `TRABALHANDO`, `AGUARDANDO_SUPERVISOR`, `PENDENCIA`, `CONCLUIDO`, `ERRO` |
| `atualizado_em` | data-hora | ✅ | ISO 8601 com fuso; não posterior a `gerado_em` |
| `trabalho` | objeto ou `null` | ✅ | `null` se `LIVRE`; objeto obrigatório nos demais |

### 4.3 Trabalho
| Campo | Tipo | Obrig. | Regra |
|---|---|---|---|
| `solicitacao_id` | string | ✅ | `^SOL-\d{4}-\d{6}$` (ex.: `SOL-2026-000001`) |
| `empresa_id` | string | ✅ | `^[A-Z0-9][A-Z0-9-]{1,40}$`, presente no **catálogo de exibição de empresas** e vinculado à SOL |
| `competencia` | string | ✅ | `^\d{4}-(0[1-9]\|1[0-2])$` |
| `etapa` | enum | ✅ | Código do **catálogo de etapas**, compatível com o tipo do agente |
| `iniciado_em` | data-hora | ✅ | ISO 8601 com fuso; ≤ `atualizado_em` |
| `pendencias` | inteiro | ✅ | 0 a 999 (apenas a quantidade) |
| `codigo` | enum ou `null` | ✅ | Código do **catálogo de códigos**, compatível com o `status`; obrigatório em `AGUARDANDO_SUPERVISOR`, `PENDENCIA` e `ERRO` |
| `lote_id` | string ou `null` | ❌ (opcional) | `^LOTE-\d{3,6}$`; só com código de aguardo de aprovação de lote |

### 4.4 Campos e conteúdos PROIBIDOS
Rejeitados pelo publicador e ignorados pelo frontend, mesmo que apareçam:
- CNPJ, CPF, razão social, inscrição estadual/municipal, regime tributário, endereço, contatos;
- `nome`, `tipo`, `implementado` de agente (vêm do catálogo);
- `progresso` / percentuais;
- `prioridade` (conceito ainda inexistente);
- qualquer **texto livre**: tarefa descrita, mensagem, descrição de pendência, motivo de erro;
- caminhos de arquivo, nomes de documentos, conteúdo de documento, conteúdo ou trecho de relatório de agente;
- valores monetários, números de nota, chaves de acesso;
- os status `OFFLINE` e `NAO_IMPLEMENTADO` (são derivados ou de catálogo, ver ESTADOS.md);
- qualquer campo não listado neste schema.

### 4.5 Exemplo fictício
```json
{
  "contrato": "agentes-prime/estado-operacional",
  "versao": "1.0",
  "modo": "SIMULACAO",
  "instancia": "0f3a9c7e51b2d4a8",
  "sequencia": 12,
  "gerado_em": "2026-10-31T09:14:05-03:00",
  "valido_por_segundos": 900,
  "agentes": [
    {
      "id": "coordenador",
      "status": "TRABALHANDO",
      "atualizado_em": "2026-10-31T09:12:40-03:00",
      "trabalho": {
        "solicitacao_id": "SOL-2026-000001",
        "empresa_id": "EMPRESA-TESTE",
        "competencia": "2026-09",
        "etapa": "ACOMPANHAMENTO",
        "iniciado_em": "2026-10-31T09:10:00-03:00",
        "pendencias": 0,
        "codigo": null,
        "lote_id": null
      }
    },
    {
      "id": "documentos",
      "status": "TRABALHANDO",
      "atualizado_em": "2026-10-31T09:14:05-03:00",
      "trabalho": {
        "solicitacao_id": "SOL-2026-000001",
        "empresa_id": "EMPRESA-TESTE",
        "competencia": "2026-09",
        "etapa": "ANALISE_DOCUMENTAL",
        "iniciado_em": "2026-10-31T09:12:40-03:00",
        "pendencias": 0,
        "codigo": null,
        "lote_id": null
      }
    }
  ]
}
```
Observação: `fiscal`, `dp`, `financeiro` e `conciliacao` **não aparecem** no estado; o frontend os mostra como "Em breve"
porque o catálogo de agentes os marca como não implementados.

## 5. Validações
**No publicador (futuro), antes de gravar:**
1. Formato de cada campo (regras das tabelas acima); rejeitar campos extras.
2. `id` e `empresa_id` existem nos catálogos; `etapa` e `codigo` existem e são compatíveis com agente e status.
3. Transição permitida pela matriz de ESTADOS.md.
4. **Concorrência V2:** no máximo **um** agente (além do Coordenador) em `TRABALHANDO`, e no máximo **uma**
   solicitação operacional ativa.
5. `TRABALHANDO` exige ordem ativa válida **para a mesma empresa e a mesma SOL** (conferência somente leitura).
6. Vínculo `solicitacao_id ↔ empresa_id` imutável: uma SOL nunca é aceita com outra empresa, nem depois de encerrada.
7. `sequencia` = anterior + 1; gravação atômica (arquivo temporário + renomeação); tamanho máximo 64 KB.

**No frontend, antes de exibir:**
1. Validar o documento inteiro de novo; se inválido, **manter o último retrato válido** e mostrar aviso.
2. Aceitar só `sequencia` maior que a atual dentro da mesma `instancia`; mudança de `instancia` reinicia a referência.
3. Ignorar campos desconhecidos; status desconhecido → "Estado desconhecido" (sem quebrar a tela).
4. Montar textos apenas a partir dos catálogos locais; nunca usar HTML a partir de dados.

## 6. Versionamento
- `versao` = `MAIOR.MENOR`.
- **MENOR**: só acrescenta campos **opcionais**; leitores 1.x continuam funcionando.
- **MAIOR**: qualquer mudança incompatível (remoção, renomeação, mudança de tipo ou de significado).
  O frontend recusa versões maiores que não conhece e mostra "versão de estado não suportada".
- Catálogos têm versão própria; um código novo exige catálogo atualizado no frontend antes de ser publicado.

## 7. Validade e estado desatualizado
- O Coordenador não é um processo contínuo; por isso o estado tem prazo de validade.
- O publicador emitirá um **pulso** (republicação sem mudança de status, nova `sequencia`) a cada interação do
  Coordenador e ao iniciar a sessão. Na V2.6, hooks de sessão poderão automatizar o pulso.
- No frontend, com `idade = agora − gerado_em`:
  - `idade ≤ valido_por_segundos` → estado atual;
  - até 2× a validade → exibe o estado com aviso **"desatualizado há X"**;
  - acima de 2× → todos os agentes implementados aparecem como **OFFLINE** ("último estado conhecido: …").
- `gerado_em` mais de 120 s no futuro em relação ao relógio local → documento inválido.

## 8. Minimização de dados
A pergunta para qualquer campo novo: *"a tela precisa disto para representar o trabalho?"* Se a resposta envolver
conteúdo, identificação fiscal ou texto produzido por agente, o campo não entra. Textos vistos pelo usuário são
**traduções locais de códigos** (CATALOGOS.md). Pendências entram só como quantidade.

## 9. Runtime (requisitos para implementação futura — nada criado na V2.0)
**Requisitos:**
1. Fora do repositório AGENTES-PRIME.
2. Preferencialmente fora de pastas sincronizadas (OneDrive, Dropbox, Google Drive etc.).
3. Configurável; **proibido caminho pessoal fixo** no código ou na documentação.
4. Acesso restrito ao usuário local.
5. **Falha fechada:** configuração ausente, inválida ou proibida → o publicador recusa e informa; nunca escolhe um local alternativo silenciosamente.
6. Funcionar futuramente em Windows e Linux.

**Estratégia proposta de resolução (ordem):**
1. Variável de ambiente `AGENTES_PRIME_RUNTIME` com caminho **absoluto**.
2. Sem a variável: diretório padrão de dados locais do sistema —
   Windows: `%LOCALAPPDATA%\AgentesPrime\runtime` · Linux: `$XDG_STATE_HOME/agentes-prime` (ou `~/.local/state/agentes-prime`).

**Validações do caminho resolvido:**
- absoluto, normalizado, sem links/junções;
- **não** dentro do repositório (comparar com a raiz do projeto resolvida);
- **não** dentro de raízes sincronizadas conhecidas (ex.: variáveis `OneDrive`, `OneDriveCommercial`, `OneDriveConsumer`);
- já existente e criado por um comando explícito de inicialização (aprovado pelo Supervisor), nunca criado automaticamente;
- permissões: Windows herda o perfil do usuário em `%LOCALAPPDATA%`; Linux exige `0700`.

**Estrutura prevista:** `estado/` (retrato atual), `eventos/` (log futuro), `travas/` (exclusão mútua do publicador).

**Ponto em aberto para o spike:** com o runtime fora do repositório, uma página aberta por `file://` precisa saber
onde está o arquivo de estado. Não é aceitável indicar o arquivo por parâmetro de URL (permitiria carregar um script
arbitrário) nem fixar um caminho pessoal. Se o spike não encontrar forma segura e portável, isso reforça a antecipação
do servidor local somente leitura, que resolve o runtime pelo mesmo procedimento do publicador.

## 10. Canal de leitura
| Opção | Situação |
|---|---|
| Arquivo JS gerado + `file://` | **CANDIDATO V2.1, sujeito a spike técnico** (seção 11). Não aprovado para dados reais |
| JSON + servidor HTTP local somente leitura (`127.0.0.1`, lista fixa de caminhos, só GET, SSE no futuro) | Alternativa a antecipar se o spike reprovar; arquitetura alvo para multiagente |
| JSON lido por `file://` | Inviável (o Chrome bloqueia leitura de arquivos locais por `fetch`) |
| WebSocket | Não recomendado (canal bidirecional desnecessário) |

## 11. Spike obrigatório antes da V2.1 real
Prova técnica **somente com dados fictícios**, em pasta temporária, sem tocar no runtime real. Precisa demonstrar no Chrome:

| # | Teste | Critério de aprovação |
|---|---|---|
| 1 | Releitura automática | Mudança no arquivo aparece na tela em ≤ 5 s sem recarregar a página |
| 2 | Cache | Releituras sempre obtêm a versão nova (verificar com `sequencia`) |
| 3 | CSP | Política restritiva da página continua bloqueando conexões; o script de estado carrega |
| 4 | Arquivo inexistente | Tela mostra "sem estado" / OFFLINE, sem erro JavaScript |
| 5 | Arquivo parcialmente escrito | Erro de sintaxe não derruba a página; último retrato válido é mantido |
| 6 | Atualização de sequência | Sequência menor ou igual é ignorada; mudança de `instancia` é tratada |
| 7 | Recuperação após estado inválido | Após um arquivo inválido, o próximo válido é aplicado normalmente |
| 8 | Ausência de execução arbitrária | Arquivo com código extra (além de `window.__ESTADO_OPERACIONAL__ = {...}`) é detectável/neutralizado; demonstrar o limite real dessa proteção |
| 9 | Localização portável do arquivo | Forma de a página achar o estado sem caminho fixo e sem parâmetro de URL (ver seção 9) |
| 10 | Duas abas | Ambas atualizam; nenhuma interfere na outra |

Resultado: relatório com aprovado/reprovado por item. Reprovação nos itens 5, 8 ou 9 → adotar o servidor local
somente leitura na V2.1.
