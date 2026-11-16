# BASE_CONHECIMENTO_CONTABIL

Base consultável de conhecimento normativo e técnico do AGENTES PRIME. Versão atual `1.2.1` (complementação 03C), consultada em **16/11/2026**. Os dados são índices e resumos curtos, sem cópia indiscriminada de normas. A base não contém documentos de cliente nem dados reais.

## Categorias

- `NORMAS_CONTABEIS/`: NBCs, ITGs e critérios de referencial.
- `LEGISLACAO_TRIBUTARIA/`: tributos, regimes, escriturações e reforma tributária.
- `LEGISLACAO_TRABALHISTA/`: legislação trabalhista e eSocial.
- `PROCEDIMENTOS_CONTABEIS/`: métodos internos de pesquisa e temas técnicos.
- `POLITICAS_CONTABEIS/`: hierarquia, limites de decisão e política de pendências.
- `CONTROLES_INTERNOS/`: integridade, evidência, conciliação e supervisão.
- `REFERENCIAS_NORMATIVAS/`: catálogo de fontes oficiais e notas de uso.
- `fontes.json`: fontes oficiais consultadas e seus URLs.
- `cobertura.json`: inventário dos temas solicitados, incluindo o trabalho ainda pendente.
- `esquema.json`: contrato de dados dos registros.
- `fundamentos_p0.json`: 17 fichas 03B preservadas e 20 fichas contábeis 03C CONT-01–CONT-20.
- `casos_contabeis.json`: 12 casos inteiramente fictícios consultáveis, sem contabilização automática.
- `consulta.py`: interface de consulta somente leitura.

## Contrato e estados

Cada registro contém os campos pedidos na Etapa 03 e, adicionalmente, tipo de conhecimento, escopo, fontes internas e o sinalizador fixo `AUTORIZA_DECISAO_AUTOMATICA=false`.

`TIPO_CONHECIMENTO` distingue `NORMA_OFICIAL`, `INTERPRETACAO_TECNICA`, `PROCEDIMENTO_INTERNO` e `EXEMPLO_ILUSTRATIVO`. Registro interno não é norma; referência a um documento CPC não substitui a NBC formalizada pelo CFC. Nenhum resumo ou correspondência de palavras pode decidir lançamento ou apuração.

- `VERIFICADO`: evidência oficial consultada sustenta exatamente a afirmação limitada que consta do resumo.
- `PARCIAL`: fonte localizada, mas conteúdo, versões, vigência, correlação ou aplicação ainda requerem validação.
- `PENDENTE`: tema catalogado, ainda sem pesquisa suficiente para uma orientação normativa.
- `NAO_VERIFICADO`: fonte oficial não foi consultada/acessada; nunca tratar como confirmado.

`VIGENCIA` não é uma garantia global de validade. Se início/fim forem nulos, conferir fonte consolidada e atos que produzem efeitos na competência. Consulte o filtro `competencia`; referências sem janela temporal conhecida aparecem como candidatas, não como vigência confirmada. Em matéria tributária, trabalhista, fiscal e de leiaute, competência/data e jurisdição podem alterar o resultado.

O referencial contábil é separado do regime tributário. Os critérios ITG 1000 são ponto de partida, sujeitos a ressalvas e confirmação do Supervisor; optar pelo Simples Nacional não seleciona automaticamente NBC TG 1002. Leia `APLICABILIDADE` e `LIMITACOES` antes de utilizar qualquer registro.

## Consultas

A partir da raiz do repositório:

```sh
.venv/bin/python -m BASE_CONHECIMENTO_CONTABIL.consulta --departamento FISCAL --assunto IBS --competencia 2026-11
.venv/bin/python -m BASE_CONHECIMENTO_CONTABIL.consulta --referencial 'NBC TG 1001' --status VERIFICADO
.venv/bin/python -m BASE_CONHECIMENTO_CONTABIL.consulta --departamento DP --assunto eSocial --competencia 2026-10 --somente-verificados
.venv/bin/python -m BASE_CONHECIMENTO_CONTABIL.consulta --cobertura --departamento CONTABILIDADE --assunto depreciação
```

A API Python `consultar(...)` aceita departamento, assunto, referencial, competência, tipo de operação, regime tributário, UF, município, ID da empresa e estado de verificação. `consultar_fundamento_id("CONT-10")` pesquisa um fundamento contábil; `consultar_fundamento_verificado(...)` bloqueia fichas abaixo de VERIFICADO. `consultar_casos_contabeis(caso_id="CASO-01")` retorna exemplo explicativo com aprovação obrigatória; não gera lançamento. Filtros são combinados por interseção. Regras com escopo `EMPRESA` ficam invisíveis sem o mesmo `empresa_id`; os registros desta primeira versão são gerais. `detectar_conflitos()` apresenta posições incompatíveis como `PENDENTE_REVISAO`, sem escolher uma. `autoriza_decisao_critica()` sempre retorna `False`.

`consultar_cobertura(...)` pesquisa `cobertura.json` para encontrar também assuntos ainda sem orientação normativa suficiente.

Exemplo:

```python
from BASE_CONHECIMENTO_CONTABIL.consulta import consultar
itens = consultar(departamento="CONTABILIDADE", assunto="imobilizado", competencia="2026-09")
```

## Fontes e atualização

A consulta foi feita diretamente nos portais oficiais CFC, CPC, Receita Federal, SPED, eSocial e Planalto. O CFC forneceu o texto da ITG 1000 e a situação cadastral das ITGs/NBCs simplificadas selecionadas. O CPC foi usado como índice de pronunciamentos, com a ressalva de formalização pelo CFC. Receita/SPED foram consultados para a separação entre resultado contábil e base fiscal e para a ECF/e-Lalur/e-Lacs. O portal eSocial foi consultado para MOS/leiautes e riscos de versionamento; a indexação exibiu documentos futuros, que não foram tratados como vigentes em 16/11/2026. A página automática do portal NF-e retornou redirecionamento; a versão atual do MOC permanece parcial.

Não foi indicada UF/município, entidade, atividade nem operação concreta; assim, nenhuma norma estadual ou municipal foi declarada aplicável. As fontes para CFOP/CST/CSOSN, ICMS, IPI, ISS, contribuições, retenções, NFS-e e CT-e precisam ser selecionadas conforme esses dados. Não há alíquota universal nesta base.

Atualize novos registros por mudança versionada, preserve versões anteriores e a origem oficial, registre data da consulta e as competências de efeito. Mudança de norma deve produzir novo registro/revisão com trilha de auditoria; não reescrever interpretações de empresa nem regras aprovadas. Cadastros específicos de cliente continuam no mecanismo `governanca_regras.py`, fora desta base geral.


## Etapa 03D — Financeiro

fundamentos_financeiros.json contém FIN-01–FIN-20 com fonte, dispositivo, vigência de consulta, referencial, evidências, tratamento conceitual, limites, procedimento interno relacionado e bloqueio automático. casos_financeiros.json contém 15 exemplos fictícios, sem contabilização automática.

Exemplos de consulta:

    from BASE_CONHECIMENTO_CONTABIL.consulta import (
        consultar_fundamento_financeiro_id,
        consultar_fundamentos_financeiros,
        consultar_casos_financeiros,
    )
    consultar_fundamento_financeiro_id("FIN-05")
    consultar_fundamentos_financeiros(assunto="transferência", referencial="NBC TG 1001", competencia="2026-11")
    consultar_casos_financeiros(caso_id="FIN-CASO-01")

Os critérios do motor de associação são procedimentos internos documentados em AGENTES/FINANCEIRO/PROCEDIMENTO.md, não prescrições contábeis. Associação financeira confirmada não confirma natureza nem suporte. Nenhuma ficha autoriza lançamento automático.

## Etapa 03E — Fiscal

`fundamentos_fiscais.json` reúne FISC-01–FISC-25; `casos_fiscais.json` contém 20 casos inteiramente fictícios. As fichas distinguem legislação, norma contábil e procedimento local do Fiscal, relacionam CONT/FIN existentes e carregam contexto para competência, regime, UF, município, atividade e operação. Status 03E: 5 fundamentos verificados no escopo delimitado e 20 parciais; nenhum pendente ou não verificado. Todas as fichas permanecem `DEPENDENTE_DE_CONTEXTO`, não autorizam apuração ou contabilização automática.

    from BASE_CONHECIMENTO_CONTABIL.consulta import (
        consultar_fundamento_fiscal_id,
        consultar_fundamentos_fiscais,
        consultar_casos_fiscais,
    )
    consultar_fundamento_fiscal_id("FISC-12")
    consultar_fundamentos_fiscais(assunto="ISS", competencia="2026-11", uf="SP", municipio="São Paulo")
    consultar_casos_fiscais(caso_id="FISC-CASO-10")

Filtros contextuais registram o contexto solicitado sem inferir incidência ou regra local. Sem identificação da empresa, jurisdição, regime, atividade e competência, o fundamento permanece orientativo e pode resultar em pendência. O procedimento `AGENTES/FISCAL/PROCEDIMENTO.md` e os contratos/adapters existentes foram preservados; consulte `TESTES/ETAPA-03E-CHECKLIST.md` para fontes, limitações, casos e testes.


## Etapa 03F — DP

`fundamentos_dp.json` contém DP-01–DP-20 e `casos_dp.json` contém 15 casos exclusivamente fictícios. Consulta é somente leitura e não calcula folha, rescisão, encargos, retenções, incidências ou lançamentos. O estado atual registra 3 VERIFICADO (DP-16/17/18, apenas documentação técnica delimitada) e 17 PARCIAL; referencial CFC de benefícios e tratamentos materiais demandam estudo adicional e enquadramento contextual.

    from BASE_CONHECIMENTO_CONTABIL.consulta import (
        consultar_fundamentos_dp, consultar_fundamento_dp_id, consultar_casos_dp,
    )
    consultar_fundamentos_dp(assunto="férias", referencial="NBC TG 1001", competencia="2026-11")
    consultar_fundamento_dp_id("DP-17")
    consultar_casos_dp(caso_id="DP-CASO-01")

O contrato `STATUS_DP_CONTEXTUAL_V1` e o procedimento `AGENTES/DP/PROCEDIMENTO.md` permanecem inalterados. Fontes de versão ou competência não determinam tratamento sem prova e revisão humana. Consulte `TESTES/ETAPA-03F-CHECKLIST.md` para o inventário e as limitações.
