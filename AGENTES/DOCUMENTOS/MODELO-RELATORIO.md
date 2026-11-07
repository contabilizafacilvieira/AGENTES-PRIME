# MODELO DE RELATÓRIO - AGENTE DE DOCUMENTOS

O relatório é devolvido ao Coordenador Geral exatamente nesta estrutura. Seções sem conteúdo recebem "Nenhum".
Não inventar dados: campo não encontrado no documento = "NÃO CONSTA". Leitura incerta = marcar "Confiança: BAIXA".

---

```
▶ EMPRESA: <ID> | CNPJ: <CNPJ> | COMPETÊNCIA: AAAA-MM | MODO: REAL/SIMULAÇÃO
RELATÓRIO DO AGENTE DE DOCUMENTOS - <SOL-XXX>
Executado por: Agente de Documentos (subagente agente-documentos)
Data/hora da execução: <data/hora informada pela ferramenta extrair_documentos.py>
Pasta analisada: CLIENTES/<EMPRESA>/<pasta>
```

## 1. Inventário
| # | Arquivo | Tamanho (bytes) | SHA-256 (12 primeiros) | Leitura (código do extrator) | Marcações | Partes recebidas/total | Analisado? |
|---|---|---|---|---|---|---|---|

"Analisado? SIM" somente se todas as partes foram recebidas (ex.: 9/9). Faltando parte = PARCIAL, com o código na seção 6.

Leitura — copiar o código exatamente como veio do extrator:
- Extraído (vai para a seção 2): EXTRAIDO_TEXTO | EXTRAIDO_PDF | EXTRAIDO_PLANILHA | EXTRAIDO_NFE | EXTRAIDO_EVENTO_NFE
- Não extraído (vai para a seção 6, com pendência controlada): DOCUMENTO_REQUER_OCR | DOCUMENTO_VAZIO | PDF_PROTEGIDO |
  PROTEGIDO | ARQUIVO_CORROMPIDO | LIMITE_EXCEDIDO | EXTENSAO_INCOMPATIVEL | XML_DTD_PROIBIDO | XML_TIPO_NAO_SUPORTADO |
  NAO_SUPORTADO | ERRO_LEITURA
- Erros da interface (arquivo PARCIAL ou não lido, seção 6): ID_DESCONHECIDO | ARQUIVO_ALTERADO | PARTE_INEXISTENTE

Marcações possíveis: PAGINAS_REQUEREM_OCR | PAGINAS_VAZIAS | CONTEM_JAVASCRIPT |
ABA_OCULTA | FORMULA_SEM_VALOR | CELULAS_MESCLADAS | CONTEM_MACROS | PROTEGIDO | LINKS_EXTERNOS | LIMITE_EXCEDIDO |
CHAVE_INVALIDA | CHAVE_DIVERGENTE | CAMPO_AUSENTE | TOTAL_DIVERGENTE | NOTA_CANCELADA | NOTA_NAO_ENCONTRADA_NA_PASTA

## 2. Ficha dos documentos analisados
Uma ficha por documento:

```
Doc <#> - <arquivo>
Tipo: <NF-e de compra | NF-e de venda | NFS-e | comprovante bancário | extrato | boleto | recibo | guia de imposto | planilha | outro: ...>
Número: <nº ou NÃO CONSTA>
Data de emissão/movimento: <DD/MM/AAAA ou NÃO CONSTA>
Competência atribuída: <AAAA-MM> (critério: <data de emissão | data do movimento | ...>)
Valor total: <R$ ou NÃO CONSTA>
Participantes:
  - <papel: emitente/destinatário/tomador/prestador/fornecedor/titular/terceiro>: <nome> - <CNPJ/CPF ou NÃO CONSTA> - <cliente? SIM (matriz/filial cadastrada) | NÃO>
Descrição/natureza: <resumo do conteúdo>
Evidências: <trechos/campos devolvidos pelo extrator que sustentam a classificação>
Cálculos do agente: <"nenhum" ou CALCULO_DO_AGENTE: <valores extraídos> <operação> = <resultado>; diferença em relação ao documento = divergência>
Partes recebidas: <n>/<total>
Leitura / marcações do extrator: <código> / <marcações ou "nenhuma"> (ex.: PAGINAS_REQUEREM_OCR, FORMULA_SEM_VALOR, CAMPO_AUSENTE)
Confiança: ALTA | MÉDIA | BAIXA (<motivo, se não for ALTA>)
Situação: OK | COM PENDÊNCIA (<nº provisório>)
```

## 3. Classificação por tipo e competência
| Competência | Tipo | Quantidade | Valor total | Documentos |
|---|---|---|---|---|

Documentos com competência diferente da solicitada devem ser destacados.

## 4. Duplicidades
| Tipo | Documentos | Evidência |
|---|---|---|

Tipo: EXATA (mesmo SHA-256) | PROVÁVEL (mesmo emitente + número + valor, arquivos diferentes)

## 5. Pendências propostas (para PENDENCIAS.md - gravação pelo Coordenador)
| Nº provisório | Competência | Tipo | Descrição | Documento | Responsável sugerido | Status sugerido |
|---|---|---|---|---|---|---|

Tipos: Informação ausente | Divergência | Identificação/Titularidade | Esclarecimento
Status: Aguardando informação | Aguardando documento

## 6. Documentos não analisados
| Arquivo | Código do extrator | Motivo (observação do extrator) | Pendência proposta |
|---|---|---|---|

Nenhum conteúdo de documento não extraído pode aparecer no relatório (ex.: DOCUMENTO_REQUER_OCR = nenhum valor,
CNPJ, data ou texto da imagem). O tratamento é manual, pelo Supervisor.

## 7. Tarefas da ordem de serviço
| Tarefa | Situação | Observação |
|---|---|---|

Situação: EXECUTADA | PARCIAL | NÃO EXECUTADA (com motivo)

## 8. Limitações e premissas
- <limites de leitura, truncamentos, premissas adotadas, pontos que dependem do Supervisor>

## 9. Declaração
- Nenhum arquivo foi criado, alterado, movido ou apagado por este agente.
- Nenhum lançamento contábil foi gerado. Nada foi colocado em LIBERADOS. Nenhuma importação foi feita no Domínio.
- Foram acessados somente arquivos de CLIENTES/<EMPRESA>/ e AGENTES/DOCUMENTOS/.
