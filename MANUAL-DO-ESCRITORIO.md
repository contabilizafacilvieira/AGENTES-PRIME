# Manual do Escritório Virtual — AGENTES PRIME v1.0.0-interno

Versão de uso **interno e supervisionado**. O aplicativo prepara propostas e conferências; quem aprova é sempre o Supervisor
Contábil. Nada é lançado nem importado no Domínio automaticamente.

## A. Iniciar o Escritório Virtual

1. No computador do escritório, abra o **Prompt de Comando** na pasta `AGENTES-PRIME`.
2. Digite:

   ```
   .venv\Scripts\python.exe -I API-LOCAL\servidor.py
   ```

3. Abra no navegador: **http://127.0.0.1:8765/**
4. **Deixe a janela do Prompt aberta** enquanto usar o escritório. Fechá-la desliga o aplicativo.

O endereço só funciona neste computador (não fica disponível na rede).

## B. Empresas

Clique em **Empresas** no menu da esquerda. Cada empresa aparece num cartão com status, modo e competência atual.

- **Abrir**: entra na empresa.
- **⋯** (mais opções): Configurações, Editar cadastro, Histórico de solicitações e Excluir cadastro.
- **Como funciona**: resume o caminho em 6 passos.
- **Administração · Mais opções**: cadastrar empresa e consultar cadastros excluídos (uso do administrador).

## C. Abrir competência

Na empresa, o cartão **Base inicial — mês/ano** mostra a competência. Para mudar, use **Trocar competência**, escolha o mês
dos documentos e clique em **Abrir competência**.

## D. Base inicial

É o ponto de partida do mês: o balancete de encerramento do mês anterior e o book (composições dos saldos).
Clique em **Iniciar preparação** (ou **Continuar preparação**) e siga as 4 fases:

1. **Balancete anterior** — envie o arquivo, confira o resumo e salve. Depois, **Aplicar contas ao plano**.
2. **Book / composições** — envie o book do mesmo período e salve.
3. **Conferência** — resolva as pendências (veja G).
4. **Confirmação** — digite a frase pedida na tela e clique em **Confirmar base**.

Base confirmada: o botão principal vira **Enviar documentos do mês**.

Contas sintéticas/analíticas e o grupo contábil (Ativo, Passivo, Patrimônio Líquido, Contas de Resultado, Outros) são
identificados automaticamente pela estrutura do plano. Você só confirma os ramos que a estrutura não permite identificar.
Se aparecer **Reanalisar base**, use-o: recalcula tipos, grupos e pendências com os arquivos já enviados (nada é reenviado nem
alterado).

Se o resumo mostrar **⚠ N contas precisam de conferência**, são contas patrimoniais analíticas com saldo, mas sem composição
identificada no Book. Clique em **Revisar N contas**, confira os saldos e, depois de conferir, use **Marcar como conferido** com uma
justificativa. Isso não impede confirmar a base, mas deve ser revisado. Se a lista ou os saldos mudarem, a conferência volta a ser
pedida.

## E. Enviar documentos

Clique em **Nova solicitação** (menu da esquerda), escolha a empresa, a competência e os arquivos. Antes de começar, confira o
quadro **Você está iniciando** (empresa, competência e número de documentos). Marque a caixa de conferência e clique em
**Iniciar processamento**.

## F. Acompanhar processamento

A tela de acompanhamento mostra a etapa atual (Documentos, Financeiro, Fiscal, DP, Contabilidade, Conciliação) e se atualiza
sozinha. No escritório, os personagens indicam quem está trabalhando. Não é preciso esperar na tela: você pode voltar depois
em **Solicitações**.

## G. Resolver pendências

Cada pendência diz:

- **Problema** — o que aconteceu;
- **Impacto** — por que importa;
- **O que fazer** — a ação necessária.

Faça a ação indicada (por exemplo, informar um saldo ou **Marcar como conferido** com uma justificativa curta). Detalhes
técnicos ficam em **Ver detalhes técnicos** — normalmente não são necessários.

## H. Consultar solicitações

Menu **Solicitações**: filtre por número, empresa, competência ou estado. **Resumo** mostra o que está em processamento, o que
aguarda decisão e o que já terminou.

## I. Informativo, Atenção e Bloqueio

| Selo | Significa | O processo continua? |
|---|---|---|
| ℹ **Informativo** | Apenas para seu conhecimento | Sim |
| ⚠ **Atenção** | Recomenda revisão | Sim, mas revise |
| ⛔ **Bloqueio** | Precisa ser resolvido | Não, até resolver |

## J. Quando chamar o Supervisor

- Para **aprovar** um fechamento ou **confirmar** regras, base inicial e exceções (são ações do Supervisor).
- Quando uma pendência pede uma **decisão contábil** que você não tem segurança para tomar.
- Quando aparecer **divergência** de valores que você não consegue explicar.
- Para **excluir** um cadastro de empresa ou habilitar o piloto.
- Se o aplicativo mostrar erro inesperado ou ficar parado na mesma etapa por muito tempo.

## Limites desta versão

- Funciona em **SIMULAÇÃO**: prepara propostas para conferência; nada é escriturado.
- O arquivo TXT para o Domínio só é gerado para empresa fictícia; para empresa real, a aprovação fica registrada e o arquivo
  não é gerado. A importação no Domínio é sempre manual, feita pelo Supervisor.
- A Importação (VGROW) está desativada.
- Documentos digitalizados sem texto podem exigir conferência manual.
