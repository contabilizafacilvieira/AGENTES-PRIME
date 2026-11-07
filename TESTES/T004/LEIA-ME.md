# T-004 · Novos formatos do Agente de Documentos (extrator)

Status: **T-004.3 a T-004.6 concluídos** (fixtures, gabarito, extrator v2.1 com interface paginada, canal único
de conteúdo no guarda, instruções do agente, modelo de relatório, bateria final consolidada com o agente real e a
ferramenta do Coordenador). Agente HOMOLOGADO EM AMBIENTE FICTÍCIO; nenhum documento real foi processado.

## Arquivos
| Arquivo | Função |
|---|---|
| `gerar_fixtures.py` | Gera as 36 fixtures **fictícias** (byte a byte; reprodutíveis) em `CLIENTES/EMPRESA-TESTE/T004/` e `CLIENTES/EMPRESA-ISOLAMENTO/T004/` |
| `gabaritos.json` | Gabarito **escrito à mão**, independente do gerador e do extrator (valores, códigos, valores proibidos) |
| `testar_extrator.py` | Roda o extrator como o agente rodaria, compara com o gabarito e executa testes negativos; imprime PASS/FAIL |
| `testar_guarda.py` | Bateria isolada do guarda (G-01…G-42, H-01…H-06, Coordenador, regressão ISO); usa ordens fictícias e as remove ao final |
| `testar_interface.py` | Interface paginada (I-01…I-24): orçamento, partes, determinismo, `executado_em`, reconstrução sem perda |
| `verificar_t004_6.py` | Confere a transcrição real de uma execução do agente (protocolo, ferramentas, relatório, valores proibidos) |
| `../COORD/testar_coordenador.py` | Ferramenta do Coordenador (COORD-01…08): SOL, ordem ativa, transição de etapa |

```
.venv/Scripts/python.exe -I TESTES/T004/gerar_fixtures.py
.venv/Scripts/python.exe -I TESTES/T004/testar_extrator.py
.venv/Scripts/python.exe -I TESTES/T004/testar_guarda.py
.venv/Scripts/python.exe -I TESTES/T004/testar_interface.py
.venv/Scripts/python.exe -I TESTES/COORD/testar_coordenador.py
```

## Interface paginada (extrator v2.1)
O agente só pode usar: `--empresa <ID> --pasta "<pasta>" --resumo [--parte N]` (inventário sem conteúdo) e
`--empresa <ID> --arquivo <id do resumo> [--parte N]` (conteúdo de um arquivo). `--completo` existe só para testes e
é bloqueado pelo guarda. Toda resposta tem no máximo **12.000 caracteres** (margem ampla antes do limite em que a
saída do Bash é desviada para arquivo), traz `executado_em` (ISO 8601 com fuso) e indica `parte`, `partes_total`,
`tem_mais` e `intervalo`. A divisão em partes é determinística; até 200 arquivos por pasta.

## Canal único de conteúdo (T-004.5)
Para o `agente-documentos` (e só para ele), o guarda bloqueia `Read` de documentos (lista fechada em
`EXTENSOES_SO_PELO_EXTRATOR`, conteúdo de documento com extensão disfarçada, fluxo alternativo NTFS) e bloqueia `Grep`
(que leria o conteúdo bruto). O conteúdo de documentos entra somente pelo extrator; `Read` fica para os arquivos de
controle em Markdown. O Coordenador e outros agentes não são afetados.

## Escopo da V1 (decisão do Supervisor, T-004.2)
| Situação | Formatos | Resultado (`leitura`) |
|---|---|---|
| Suportado | TXT/CSV/JSON/OFX | `EXTRAIDO_TEXTO` |
| Suportado | PDF digital | `EXTRAIDO_PDF` (texto por página) |
| Suportado | XLSX/XLSM | `EXTRAIDO_PLANILHA` |
| Suportado | XML NF-e (55) e NFC-e (65) | `EXTRAIDO_NFE` |
| Suportado | Evento de cancelamento 110111 | `EXTRAIDO_EVENTO_NFE` (e marca a nota da mesma pasta com `NOTA_CANCELADA`) |
| Pendência controlada | PDF escaneado, PNG, JPG, JPEG | `DOCUMENTO_REQUER_OCR` (nada é interpretado) |
| Fora da V1 | XLS antigo, ZIP/RAR/7Z, outros | `NAO_SUPORTADO` |
| Fora da V1 | NFS-e, CT-e, outros XML, eventos ≠ 110111 | `XML_TIPO_NAO_SUPORTADO` |

Demais códigos: `DOCUMENTO_VAZIO`, `PDF_PROTEGIDO`, `PROTEGIDO`, `ARQUIVO_CORROMPIDO`, `LIMITE_EXCEDIDO`,
`EXTENSAO_INCOMPATIVEL`, `XML_DTD_PROIBIDO`, `ERRO_LEITURA` (inesperado).
Marcações: `PAGINAS_REQUEREM_OCR`, `PAGINAS_VAZIAS`, `CONTEM_JAVASCRIPT`,
`ABA_OCULTA`, `FORMULA_SEM_VALOR`, `CELULAS_MESCLADAS`, `CONTEM_MACROS`, `PROTEGIDO`, `LINKS_EXTERNOS`,
`LIMITE_EXCEDIDO`, `CHAVE_INVALIDA`, `CHAVE_DIVERGENTE`, `CAMPO_AUSENTE`, `TOTAL_DIVERGENTE`, `NOTA_CANCELADA`,
`NOTA_NAO_ENCONTRADA_NA_PASTA`.

## Limites e justificativa
| Limite | Valor | Justificativa |
|---|---|---|
| Bytes por arquivo | 20 MB | Documentos contábeis comuns (NF, extratos, planilhas) ficam muito abaixo; acima disso o risco de travamento e de exceder o contexto do agente cresce |
| Texto (TXT/CSV/JSON/OFX) | 100.000 caracteres | Comporta extratos OFX/CSV mensais; acima: texto parcial **com** `LIMITE_EXCEDIDO` |
| Páginas de PDF | 50 | Lote documental típico; acima: **sem conteúdo** e `LIMITE_EXCEDIDO` (dividir o arquivo) |
| Texto total de PDF | 150.000 caracteres | Mantém a saída utilizável pelo agente; acima: sem conteúdo e `LIMITE_EXCEDIDO` |
| Texto mínimo por página | 10 caracteres | Abaixo disso a página é tratada como sem texto (evita confundir número de página com conteúdo) |
| Abas / linhas / colunas | 20 / 2.000 por aba / 60 | Planilhas operacionais comuns; acima: parcial **com** `LIMITE_EXCEDIDO` e `truncado: true` |
| ZIP (XLSX) descompactado | 100 MB total, taxa ≤ 100:1 por parte > 1 MB, ≤ 2.000 partes | Barra bombas de descompactação **antes** de abrir |
| XML | 5 MB | NF-e reais têm poucos KB a centenas de KB |
| Itens de NF-e | 990 | Máximo do leiaute oficial; acima: sem conteúdo e `LIMITE_EXCEDIDO` |
| Tempo por arquivo (PDF, planilha, XML) | 60 s, em processo separado | Evita travamento por arquivo malicioso ou defeituoso |

## Garantias verificadas
- Nada inventado: PDF escaneado e imagens não são interpretados (o valor que existe **só** na imagem do SCAN-01 não aparece em nenhum resultado).
- Sem rede: planilhas abertas com `keep_links=False` (links não seguidos), XML com DOCTYPE/ENTITY recusado antes da leitura, nenhuma consulta à SEFAZ.
- Sem execução: macros não são carregadas (`keep_vba=False`), JavaScript de PDF apenas detectado, fórmulas não recalculadas (`data_only=True`).
- Assinatura digital da NF-e **não** é validada (declarado em `limitacoes` de cada nota).
- Isolamento de caminhos do extrator inalterado.

## Limitações conhecidas
- `SCAN-04` (JPG) é um arquivo estruturalmente mínimo, não decodificável: suficiente porque o extrator não decodifica imagens.
- Link simbólico de arquivo não pôde ser testado (o Windows exige privilégio); junção de pasta foi testada.
- Qualquer PDF criptografado (inclusive só com senha de proprietário) → `PDF_PROTEGIDO`, sem tentativa de senha (decisão do Supervisor, 03/11/2026).
  Criptografia AES exigiria a biblioteca `cryptography` (não instalada): nesse caso, também `PDF_PROTEGIDO` (falha fechada).
- Planilha com senha de abertura é identificada pelo formato OLE (`PROTEGIDO`); não há tentativa de abrir.
- Página de PDF sem texto mas com qualquer desenho é tratada como `REQUER_OCR` (conservador).

## Riscos residuais registrados (sem correção nesta etapa)
- OCR não implementado: imagens e PDFs escaneados ficam como `DOCUMENTO_REQUER_OCR` para tratamento manual.
- O `--resumo` não traz o campo `observacao`; o relatório mostra só o código dos arquivos não extraídos.
- Arquivo textual com extensão fora da lista fechada (ex.: `.htm` ou sem extensão) ainda pode ser lido por `Read`.
- Link simbólico de arquivo não testado no Windows (falta de privilégio).
- Sincronização do OneDrive pode travar a remoção de pastas temporárias dos testes (refazer a limpeza e repetir).
- O mecanismo `SubagentHandback` é do ambiente Claude Code; mudanças futuras no ambiente exigem repetir a bateria.
