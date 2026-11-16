# AGENTES PRIME — Etapa 03F: Agente DP

Data de consulta às fontes: 16/11/2026. Escopo: conhecimento consultivo de DP para interpretação documental e intercâmbio com Contábil, Financeiro e Conciliação. Não é sistema de folha e não calcula folha, rescisão, taxas, incidências ou lançamentos.

## Preservação e segurança

- [x] Instruções consultadas: `AGENTS.md`, `CLAUDE.md`, `AGENTES/DP/PROCEDIMENTO.md`, procedimento Contábil/DP, `API-LOCAL/estado_dp.py` e contratos de intercâmbio.
- [x] Checkout em `master`, HEAD `f08424541b087c7fe917c0e403234aa4f8885ac9`; alterações da etapa anterior pré-existiam e foram preservadas.
- [x] Mantidos parser DP, adapters, contratos, status `STATUS_DP_CONTEXTUAL_V1`, integração e responsabilidades departamentais.
- [x] Nenhum runtime REAL, documento de empregado ou cadastro real foi acessado ou alterado; nenhum fechamento, empresa piloto arquivada, commit ou push.
- [x] Dados de todos os casos são inventados e didáticos; nenhuma alíquota ou valor operacional real foi acrescentado.

## Fontes oficiais efetivamente consultadas

- [x] CFC — catálogo de normas completas e catálogo simplificado. NBC TG 33 (R2) e seções de benefícios a empregados nos referenciais simplificados foram mapeadas com aplicabilidade condicionada ao referencial confirmado. O catálogo estabelece correspondência, mas não substitui leitura integral nem determina qual referencial vale para empresa.
- [x] eSocial — documentação técnica, MOS S-1.3 consolidado até NO 12/2026 e página de leiautes/NT. MOS 10.3.3 separa remuneração devida (S-1200/S-1202/S-1207) e pagamento (S-1210); versões posteriores exibidas na página não foram presumidas vigentes antes da implantação.
- [x] Planalto — CLT compilada, Lei 8.212/1991 compilada, Lei 8.036/1990 e Constituição Federal; dispositivos são relacionados por hipótese, sem universalizar alíquotas ou incidências.
- [x] Receita Federal — IN RFB 2.110/2022, IN RFB 2.005/2021, FAQ EFD-Reinf/DCTFWeb (atualizada em 13/04/2026), orientação IRRF e tabelas 2026; tabelas são competência-dependentes.
- [x] MTE — Manual FGTS Digital v1.70 de 12/06/2026 e FAQ. Informações declaradas no eSocial formam bases no sistema; manual descreve uso, não interpreta direito trabalhista.
- [x] Receita Federal — SC Cosit 228/2023 consultada para distinção contextual de pró-labore e distribuição; ficha parcial, sem generalizar.
- [ ] Casos concretos, rubricas, incidências, categoria de empregado, convenções coletivas, regras locais ou percentuais não foram decididos, pois não há empresa/vínculo/competência operacional alvo.

## Fichas DP (20 avaliadas)

| ID | Fundamento | Fonte/dispositivo | Vigência / aplicabilidade | Status |
|---|---|---|---|---|
| DP-01 | Folha e competência | NBC TG 33 (R2); NBC TG 1001/1002 §28; MOS 10.3.3 | Serviço prestado; referencial a confirmar | PARCIAL |
| DP-02 | Salário bruto e líquido | MOS; Lei 8.212 arts. 20/22; IRRF | Tabela, rubrica e vínculo por competência | PARCIAL |
| DP-03 | Salários a pagar | NBC TG 33; simplificadas §28; CLT art. 459 | Vínculo e obrigação documentados | PARCIAL |
| DP-04 | Pró-labore | Lei 8.212 arts. 12 V/22 III; IN 2.110; SC Cosit 228/2023 | Serviço e condição do sócio dependentes de prova | PARCIAL |
| DP-05 | INSS descontado | Lei 8.212 arts. 20/30; IN 2.110 | Categoria, tabela e competência | PARCIAL |
| DP-06 | Encargos patronais | Lei 8.212 art. 22; IN 2.110 | Regime, atividade e substituições | PARCIAL |
| DP-07 | FGTS | Lei 8.036 arts. 15/18; Manual FGTS Digital v1.70 | Vínculo, rubrica, evento e competência | PARCIAL |
| DP-08 | IRRF do trabalho | Lei 7.713; IN 1.500 e alterações; tabelas RFB | Rendimento, pagamento/crédito, beneficiário e tabela | PARCIAL |
| DP-09 | Benefícios e descontos | NBC TG 33; CLT arts. 457–458; Lei 8.212 | Natureza e incidência pela rubrica/fato | PARCIAL |
| DP-10 | Adiantamentos salariais | CLT art. 462; NBC TG 33; MOS | Prova do adiantamento e compensação | PARCIAL |
| DP-11 | Férias | CLT arts. 129–145; CF art. 7 XVII; NBC TG 33 | Vínculo, períodos e redação vigente | PARCIAL |
| DP-12 | Provisão de férias | NBC TG 33; NBC TG 1001/1002 §28 | Estimativa e encargos suportados | PARCIAL |
| DP-13 | 13º salário | CF art. 7 VIII; Leis 4.090/1962 e 4.749/1965; MOS 10.3.4 | Regras e competência anual/mensal | PARCIAL |
| DP-14 | Provisão de 13º | NBC TG 33; simplificadas §28; Leis 4.090/4.749 | Acumulação, base e encargos contextualizados | PARCIAL |
| DP-15 | Rescisões | CLT art. 477; MOS eventos S-2299/S-2399; Lei 8.036 | Motivo, vínculo, histórico e evento | PARCIAL |
| DP-16 | Pagamento/liquidação | MOS 10.3.3 (S-1210); CONT-19; FIN-05/06 | Liquidação não duplica obrigação reconhecida | VERIFICADO |
| DP-17 | eSocial | Decreto 8.373/2014; MOS 10.3.3 | Leiaute/implantação por competência | VERIFICADO |
| DP-18 | DCTFWeb/arrecadação | IN 2.005/2021; FAQ RFB EFD-Reinf 1.4 | Obrigatoriedade e débitos conforme contribuinte | VERIFICADO |
| DP-19 | Conciliação trabalhista | ITG 2000 (R1), itens 5–8; CONT-18/19; procedimento interno | Composição/evidência; procedimento não é norma | PARCIAL |
| DP-20 | Não aplicável/sem movimento | `STATUS_DP_CONTEXTUAL_V1`; MOS por contexto | Empresa e competência; decisão do Supervisor | PARCIAL |

**Resultado:** 20 fundamentos avaliados; 3 VERIFICADOS (DP-16/17/18, documentação técnica delimitada), 17 PARCIAIS, 0 PENDENTES e 0 NAO_VERIFICADOS. O fundamento de benefícios/competência fica parcial enquanto não houver estudo substantivo direto do texto CFC NBC TG 33 e tratamento simplificado; a fonte CFC encontrada é catálogo, não conteúdo suficiente por si. A classificação parcial é intencional: não há perfil de empresa/vínculo para confirmar tratamentos específicos.

## Casos e consulta

- [x] 15 casos `DP-CASO-01..15` consultáveis; exemplos integralmente fictícios, fontes, dispositivos, vigência, documentação, limites, risco e revisão humana.
- [x] Caso DP-CASO-01 apresenta bruto R$ 10.000,00, descontos R$ 1.500,00 e líquido R$ 8.500,00 como exemplo aritmético, sem representar parâmetro fiscal/trabalhista.
- [x] Separados reconhecimento da folha, retenções, encargo patronal, obrigação e pagamento; pagamento não cria despesa duplicada.
- [x] Caso de encargo sem provisão mantém pesquisa/pendência; caso `NAO_APLICAVEL` contradito usa o contrato existente e aguarda Supervisor.
- [x] API em `consulta.py`: consulta por assunto, referencial, competência, status, ID/caso; `exigir_verificado` recusa parcial; nenhuma ficha ou caso autoriza decisão automática.

## Testes e gate

- [x] Teste específico 03F: 8 testes cobrindo fichas, 15 casos, consulta, vigência/competência, bloqueio de parcial, bruto/líquido, retenção/encargo, provisão/liquidação, eSocial/DCTFWeb, conflito e intercâmbio conceitual.
- [x] Regressão DP existente: `TESTES/DP/testar_dp.py` permanece no gate.
- [x] Gate completo 03F: execução única com `.venv/bin/python -I TESTES/executar_gate.py`; 79/79 baterias aprovadas, zero falhas; estado operacional intocado.
- [x] Nenhum teste existente foi enfraquecido.

## Checklist mestre e resultado

- [x] Etapas 01/02 preservadas como aprovadas; 03 geral continua em complementação; ressalvas FISC 03E (5 verificadas, 20 parciais) mantidas.
- [ ] Revisão do Supervisor pendente.
- [x] Etapa 03G não iniciada.

**Classificação:** ETAPA_03F_BLOQUEADA: 17 fundamentos permanecem parciais; o estudo material de benefícios e referenciais contábeis CFC é insuficiente. O gate de código passou (79/79), mas não substitui esse critério. Próxima ação: consultar os textos oficiais integrais pertinentes e aprofundar fundamentos, sem iniciar 03G.
