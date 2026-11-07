# Contrato de estado operacional · Escritório Virtual

> **Status: V2.0 — somente documentação.** Nada nesta pasta é executado. O publicador, o arquivo de estado real
> e o canal de leitura **ainda não existem**. O Escritório Virtual V1 continua usando apenas dados fictícios
> (`../dados/estado-simulado.js`).

## Para que serve
Definir como o Escritório Virtual poderá, no futuro, refletir o estado **real** do Coordenador Geral e dos agentes
sem receber dados de clientes, sem poder agir sobre o sistema e sem misturar empresas.

## Arquitetura
```
Supervisor Contábil
      ↓  pedidos e aprovações (somente na conversa com o Coordenador)
Coordenador Geral            ← autoridade semântica: o que está acontecendo
      ↓  delega (ordem ativa + guarda, já homologados)
Agentes                      ← nunca publicam estado
      ↓  relatório volta ao Coordenador
Publicador determinístico    ← (FUTURO) único gravador; aceita só IDs, códigos, números e datas
      ↓  grava de forma atômica
Estado operacional sanitizado ← (FUTURO) fora do repositório e fora de pastas sincronizadas
      ↓  somente leitura
Escritório Virtual           ← só exibe; não decide, não grava, não aprova
```

## Documentos
| Arquivo | Conteúdo |
|---|---|
| [CONTRATO-ESTADO.md](CONTRATO-ESTADO.md) | Fronteiras de confiança, papéis, schema 1.0, validações, versionamento, validade, runtime, spike obrigatório |
| [ESTADOS.md](ESTADOS.md) | Os 8 estados: publicáveis, derivado e de catálogo; autoridade e transições |
| [CATALOGOS.md](CATALOGOS.md) | Catálogos de agentes, exibição de empresas, etapas e códigos (textos são traduções locais) |
| [SEGURANCA.md](SEGURANCA.md) | Modelo de ameaças, minimização, isolamento e proibições |

## Decisões aprovadas pelo Supervisor (31/10/2026)
1. **Publicador determinístico** será o único gravador do estado. O Coordenador é a autoridade semântica, mas não
   escreve o arquivo livremente. Agentes e frontend nunca publicam.
2. **Solicitações** no formato global `SOL-AAAA-NNNNNN`, únicas no projeto, com vínculo imutável `solicitacao_id ↔ empresa_id`.
3. **Empresas:** o estado recebe só `empresa_id`; o nome amigável vem de catálogo separado. Nenhum dado fiscal ou cadastral.
4. **Runtime** real fora do repositório e fora do OneDrive, descoberto por configuração portável (sem caminho pessoal fixo).
5. **Canal arquivo JS + `file://`**: apenas **candidato da V2.1**, sujeito a spike técnico com dados fictícios.
6. **Concorrência V2:** 1 agente em execução, 1 ordem ativa, 1 solicitação operacional ativa. Multiagente simultâneo
   é fase futura e exige nova homologação de segurança (o guarda e a ordem ativa global não mudam agora).

## O que ainda NÃO existe (V2.0)
- publicador e sua pasta de runtime;
- arquivo de estado real e canal de leitura;
- alteração no protocolo do Coordenador, nos agentes ou no guarda.

## Próximas etapas previstas
V2.1 spike do canal + frontend lendo o formato do contrato com dados fictícios · V2.2 publicador com testes ·
V2.3 uso pelo Coordenador (exige aprovação de mudança de protocolo) · V2.4 atualização automática e reconciliação ·
V2.5 eventos · V2.6 sinais por hooks (opcional) · V3 servidor local somente leitura/SSE e multiagente (nova homologação).
