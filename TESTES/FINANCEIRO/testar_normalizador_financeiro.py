"""Normalizador Financeiro: planilha financeira extraída → MOVIMENTOS_FINANCEIROS_NORMALIZADOS (somente dados FICTÍCIOS).

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/FINANCEIRO/testar_normalizador_financeiro.py
Não lê CLIENTES/, runtime nem SOL: as planilhas são dicionários montados aqui, no formato devolvido pelo extrator, e a
fixture fictícia TESTES/FIXTURES-FICTICIAS/XLSX-FALLBACK/styles_invalido.xlsx (lida pelo extrator, sem alteração).
"""
import copy
import hashlib
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "AGENTES/FINANCEIRO/ferramentas"))
sys.path.insert(0, str(RAIZ / "AGENTES/DOCUMENTOS/ferramentas"))
import normalizador_financeiro as nf

SHA = "f" * 64                                   # impressão digital fictícia
CAB = ["Código", "Data", "Data de Vencimento", "Data de Quitação", "Descrição", "Valor Entrada", "Valor Saída",
       "Plano de Contas", "Banco", "Empresa", "Documento"]


def planilha(linhas, marcacoes=(), nome="RECEBIDOS/2026-09/arquivo-sem-nome-util.xlsx", sha=SHA, primeira=1, **aba):
    """Arquivo no formato do extrator. `linhas` = listas de células; a numeração começa em `primeira`."""
    return {"arquivo": nome, "extensao": ".xlsx", "sha256": sha, "leitura": "EXTRAIDO_PLANILHA", "marcacoes": list(marcacoes),
            "conteudo": {"abas": [{"aba": "Lançamentos", "oculta": False, "protegida": False, "truncado": False,
                                   "celulas_mescladas": [], "formulas_sem_valor": [], **aba,
                                   "linhas": [{"linha": primeira + i, "valores": v} for i, v in enumerate(linhas) if v is not None]}],
                         "links_externos": 0, "contem_macros": False}}


ENTRADA = [101, "2026-09-01", "2026-09-05", "2026-09-04", "Recebimento Cliente Fictício Alfa", 1500.5, None,
           "Receita de Serviços", "Banco Fictício 999", "EMPRESA FICTICIA LTDA", "NF 10"]
SAIDA = [102, "02/09/2026", "10/09/2026", "09/09/2026", "Pagamento Fornecedor Fictício Beta", None, "1.234,56",
         "Despesas Gerais", "Banco Fictício 999", "EMPRESA FICTICIA LTDA", "BOL 77"]


def codigos(r):
    return [p["codigo"] for p in r["pendencias"]]


class NormalizadorFinanceiro(unittest.TestCase):
    def test_01_planilha_financeira_valida(self):
        r = nf.normalizar(planilha([CAB, ENTRADA, SAIDA]))
        self.assertEqual((r["contrato"], r["tipo_fonte"], r["situacao"]), ("MOVIMENTOS_FINANCEIROS_NORMALIZADOS_V1", "RELATORIO_FINANCEIRO", "NORMALIZADO"))
        self.assertEqual(r["adaptador"], "PLANILHA_FINANCEIRA_GENERICA")
        self.assertEqual(len(r["movimentos"]), 2)
        self.assertEqual(r["pendencias"], [])
        self.assertEqual(r["campos_ausentes"], [])
        for m in r["movimentos"]:
            self.assertEqual(tuple(m), nf.CAMPOS_MOVIMENTO_RELATORIO)          # contrato comum, campos e ordem fixos
        self.assertEqual(r["resumo"]["total_entradas"], Decimal("1500.50"))
        self.assertEqual(r["resumo"]["total_saidas"], Decimal("1234.56"))

    def test_02_extraido_planilha_aceito_e_outras_leituras_recusadas(self):
        self.assertTrue(nf.reconhece_planilha_financeira(planilha([CAB, ENTRADA])))
        for leitura in ("ARQUIVO_CORROMPIDO", "EXTRAIDO_PDF", "PROTEGIDO"):
            a = planilha([CAB, ENTRADA]); a["leitura"] = leitura
            r = nf.normalizar(a)
            self.assertEqual((r["situacao"], r["movimentos"]), ("NAO_NORMALIZADO", []))
            self.assertEqual(r["pendencias"][0]["nivel"], "BLOQUEIO")
        # leitura parcial nunca é aproveitada
        r = nf.normalizar(planilha([CAB, ENTRADA], marcacoes=["LIMITE_EXCEDIDO"]))
        self.assertEqual((r["situacao"], codigos(r)), ("NAO_NORMALIZADO", ["PLANILHA_INCOMPLETA"]))

    def test_03_calamine_fallback_aceito(self):
        # datas como número de série do Excel (como o leitor alternativo devolve): 46266 = 01/09/2026
        linha = [101, 46266.0, 46270.0, 46269.0, "Recebimento Fictício", 2500.5, None, "Receita", "Banco 999", "FICTICIA", 55.0]
        r = nf.normalizar(planilha([CAB, linha], marcacoes=["ESTILO_XLSX_INVALIDO", "LEITOR_CALAMINE_FALLBACK"]))
        m = r["movimentos"][0]
        self.assertEqual((m["data"], m["data_vencimento"], m["data_quitacao"]), ("2026-09-01", "2026-09-05", "2026-09-04"))
        self.assertIn("DATA_SERIAL_EXCEL", m["evidencias"])
        self.assertEqual((m["valor"], m["documento"]), (Decimal("2500.50"), "55"))
        self.assertEqual(r["origem"]["marcacoes"], ["ESTILO_XLSX_INVALIDO", "LEITOR_CALAMINE_FALLBACK"])
        # ponta a ponta com o extrator real sobre a fixture FICTÍCIA de estilo inválido (original não é alterado)
        import extrair_documentos
        fix = RAIZ / "TESTES/FIXTURES-FICTICIAS/XLSX-FALLBACK/styles_invalido.xlsx"
        antes = hashlib.sha256(fix.read_bytes()).hexdigest()
        a = {"arquivo": fix.name, "extensao": ".xlsx", "sha256": antes, **extrair_documentos.ler_planilha(fix)}
        self.assertIn("LEITOR_CALAMINE_FALLBACK", a["marcacoes"])
        r = nf.normalizar(a)
        self.assertNotEqual(r["situacao"], "NAO_NORMALIZADO")
        self.assertEqual(r["movimentos"][0]["data"], "2026-09-01")
        self.assertTrue(all(m["sha"] == antes and isinstance(m["valor"], Decimal) for m in r["movimentos"]))
        self.assertEqual(hashlib.sha256(fix.read_bytes()).hexdigest(), antes)

    def test_04_estilo_invalido_nao_bloqueia_dados_integros(self):
        r = nf.normalizar(planilha([CAB, ENTRADA, SAIDA], marcacoes=["ESTILO_XLSX_INVALIDO", "LEITOR_CALAMINE_FALLBACK"]))
        self.assertEqual(r["situacao"], "NORMALIZADO")
        self.assertEqual(len(r["movimentos"]), 2)
        self.assertEqual([(p["codigo"], p["nivel"]) for p in r["pendencias"]], [("LEITURA_ALTERNATIVA", "INFORMATIVO")])
        self.assertEqual(r["resumo"]["bloqueios"], 0)

    def test_05_entrada(self):
        m = nf.normalizar(planilha([CAB, ENTRADA]))["movimentos"][0]
        self.assertEqual((m["natureza"], m["valor"]), ("ENTRADA", Decimal("1500.50")))
        self.assertIsInstance(m["valor"], Decimal)
        self.assertEqual((m["codigo"], m["data"], m["data_vencimento"], m["data_quitacao"]), ("101", "2026-09-01", "2026-09-05", "2026-09-04"))
        self.assertEqual((m["descricao"], m["plano_contas"], m["banco"], m["empresa"], m["documento"]),
                         ("Recebimento Cliente Fictício Alfa", "Receita de Serviços", "Banco Fictício 999", "EMPRESA FICTICIA LTDA", "NF 10"))
        self.assertIn("COLUNA_VALOR_ENTRADA", m["evidencias"])

    def test_06_saida(self):
        m = nf.normalizar(planilha([CAB, SAIDA]))["movimentos"][0]
        self.assertEqual((m["natureza"], m["valor"]), ("SAIDA", Decimal("1234.56")))
        self.assertEqual((m["data"], m["data_quitacao"]), ("2026-09-02", "2026-09-09"))
        # 0,00 na coluna do outro lado é coluna sem valor, não "entrada e saída"
        com_zero = list(SAIDA); com_zero[5] = 0
        r = nf.normalizar(planilha([CAB, com_zero]))
        self.assertEqual((r["movimentos"][0]["natureza"], r["pendencias"]), ("SAIDA", []))

    def test_07_linha_sem_valor(self):
        sem = list(ENTRADA); sem[5] = None
        r = nf.normalizar(planilha([CAB, ENTRADA, sem]))
        self.assertEqual(len(r["movimentos"]), 1)
        p = r["pendencias"][0]
        self.assertEqual((p["codigo"], p["nivel"], p["indice_linha"]), ("LINHA_SEM_VALOR", "ATENCAO", 3))
        self.assertTrue(p["problema"] and p["impacto"] and p["o_que_fazer"])
        self.assertEqual(r["situacao"], "NORMALIZADO_COM_PENDENCIAS")

    def test_08_entrada_e_saida_simultaneas(self):
        ambas = list(ENTRADA); ambas[6] = 20
        r = nf.normalizar(planilha([CAB, ambas, SAIDA]))
        self.assertEqual([m["indice_linha"] for m in r["movimentos"]], [3])       # nenhum lado foi escolhido
        self.assertEqual((codigos(r), r["pendencias"][0]["indice_linha"]), (["ENTRADA_E_SAIDA_SIMULTANEAS"], 2))

    def test_09_colunas_fora_de_ordem(self):
        ordem = [6, 4, 10, 0, 3, 8, 5, 1, 9, 7, 2]
        embaralhar = lambda l: [l[i] for i in ordem]
        normal = nf.normalizar(planilha([CAB, ENTRADA, SAIDA]))["movimentos"]
        trocado = nf.normalizar(planilha([embaralhar(CAB), embaralhar(ENTRADA), embaralhar(SAIDA)]))["movimentos"]
        self.assertEqual(normal, trocado)

    def test_10_variacoes_de_cabecalho(self):
        cab = ["cód.", "DATA LANÇAMENTO", "Vencimento", "Data Pagamento", "  Histórico ", "ENTRADAS", "saídas",
               "Categoria", "Conta Bancária", "Empresa.CNPJ", "Nº Documento"]
        # cabeçalho só na 4ª linha, depois de título e linha de emissão
        r = nf.normalizar(planilha([["Relatório Financeiro Fictício"], ["Emitido em 30/09/2026"], None, cab, ENTRADA, SAIDA]))
        self.assertEqual(r["abas"][0]["linha_cabecalho"], 4)
        self.assertEqual(r["campos_ausentes"], [])
        self.assertEqual(r["mapeamento"]["Lançamentos"]["documento"], {"coluna": 10, "cabecalho": "Nº Documento"})
        self.assertEqual([(m["natureza"], m["valor"], m["indice_linha"]) for m in r["movimentos"]],
                         [("ENTRADA", Decimal("1500.50"), 5), ("SAIDA", Decimal("1234.56"), 6)])
        self.assertEqual([i["motivo"] for i in r["linhas_ignoradas"]], ["ANTES_DO_CABECALHO"] * 2)
        # coluna única de valor: sem coluna de tipo a natureza NÃO é presumida; com tipo, vem da coluna
        r = nf.normalizar(planilha([["Data de Vencimento", "Valor Pago", "Plano de Contas", "Banco", "Empresa CNPJ"],
                                    ["2026-09-10", 300, "Despesa", "999", "00.000.000/0001-91"]]))
        self.assertEqual((r["movimentos"][0]["natureza"], r["movimentos"][0]["valor"]), ("INDETERMINADA", Decimal("300.00")))
        self.assertIn("NATUREZA_INDETERMINADA", codigos(r))
        r = nf.normalizar(planilha([["Data", "Tipo", "Valor", "Histórico"], ["2026-09-10", "Pagamento", "45,00", "Tarifa fictícia"],
                                    ["2026-09-11", "Receita", 80, "Venda fictícia"]]))
        self.assertEqual([m["natureza"] for m in r["movimentos"]], ["SAIDA", "ENTRADA"])
        # duas colunas para o mesmo campo: não escolhe uma em silêncio
        r = nf.normalizar(planilha([["Data", "Valor", "Valor Total", "Descrição"], ["2026-09-10", 1, 2, "x"]]))
        self.assertEqual((r["situacao"], codigos(r)), ("NAO_NORMALIZADO", ["CABECALHO_AMBIGUO"]))

    def test_11_campo_inexistente(self):
        r = nf.normalizar(planilha([["Data de Quitação", "Descrição", "Valor Entrada", "Valor Saída", "Coluna Extra"],
                                    ["2026-09-03", "Recebimento fictício", "10,00", None, "abc"]]))
        m = r["movimentos"][0]
        ausentes = ["data", "data_vencimento", "plano_contas", "banco", "empresa", "documento", "codigo"]
        self.assertEqual(r["campos_ausentes"], ausentes)
        self.assertTrue(all(m[c] is None for c in ausentes))                     # nada inventado (nem a data pela quitação)
        self.assertEqual(m["data_quitacao"], "2026-09-03")
        self.assertEqual(r["abas"][0]["colunas_nao_mapeadas"], ["Coluna Extra"])
        # sem coluna de data ou de valor não é relatório financeiro reconhecido
        r = nf.normalizar(planilha([["Nome", "Telefone", "Cidade"], ["Fulano Fictício", "0000", "Lugar"]]))
        self.assertEqual((r["situacao"], codigos(r)), ("NAO_NORMALIZADO", ["CABECALHO_NAO_RECONHECIDO"]))

    def test_12_valor_invalido(self):
        for ruim in ("abc", "12,345", "1.234", 10.129, True):
            l = list(ENTRADA); l[5] = ruim
            r = nf.normalizar(planilha([CAB, l, SAIDA]))
            self.assertEqual((codigos(r), [m["indice_linha"] for m in r["movimentos"]]), (["VALOR_INVALIDO"], [3]), ruim)
        negativo = list(ENTRADA); negativo[5] = -5
        self.assertEqual(codigos(nf.normalizar(planilha([CAB, negativo]))), ["VALOR_NEGATIVO"])
        # Decimal exato: float da planilha não entra em conta de ponto flutuante
        l1, l2 = list(ENTRADA), list(ENTRADA); l1[5], l2[5] = 0.1, 0.2
        r = nf.normalizar(planilha([CAB, l1, l2]))
        self.assertEqual(r["resumo"]["total_entradas"], Decimal("0.30"))
        self.assertEqual(nf.decimal_seguro("R$ 1.234.567,89"), (Decimal("1234567.89"), None))
        self.assertEqual(nf.decimal_seguro("(1.000,00)")[0], Decimal("-1000.00"))
        j = json.loads(json.dumps(nf.para_json(r)))                              # serialização sem float
        self.assertEqual((j["movimentos"][0]["valor"], j["resumo"]["total_entradas"]), ("0.10", "0.30"))

    def test_13_data_invalida(self):
        for ruim in ("31/02/2026", "setembro", 12.5, "2026-13-01"):
            l = list(ENTRADA); l[3] = ruim
            r = nf.normalizar(planilha([CAB, l, SAIDA]))
            self.assertEqual((codigos(r), [m["indice_linha"] for m in r["movimentos"]]), (["DATA_INVALIDA"], [3]), ruim)
            self.assertIn("Data de Quitação", r["pendencias"][0]["problema"])

    def test_14_linha_informativa(self):
        titulo = [None, None, None, None, "Movimentos de setembro (observação)", None, None, None, None, None, None]
        total = [None, None, None, None, "TOTAL GERAL", 1500.5, 1234.56, None, None, None, None]
        em_branco = ["", None, None, None, "  ", None, None, None, None, None, None]
        r = nf.normalizar(planilha([CAB, titulo, ENTRADA, SAIDA, em_branco, total]))
        self.assertEqual(len(r["movimentos"]), 2)
        self.assertEqual([(i["indice_linha"], i["motivo"]) for i in r["linhas_ignoradas"]],
                         [(2, "LINHA_INFORMATIVA"), (5, "LINHA_VAZIA"), (6, "LINHA_TOTALIZADORA")])
        self.assertEqual(r["pendencias"], [])                                    # total não vira movimento nem pendência
        self.assertEqual(r["resumo"]["total_entradas"], Decimal("1500.50"))

    def test_15_rastreabilidade_ate_linha_e_sha(self):
        a = planilha([CAB, ENTRADA, None, None, SAIDA], primeira=7)               # linhas vazias puladas pelo extrator
        original = copy.deepcopy(a)
        r = nf.normalizar(a)
        self.assertEqual(a, original)                                            # a extração recebida não é alterada
        self.assertEqual([m["indice_linha"] for m in r["movimentos"]], [8, 11])  # número da linha NA PLANILHA
        for m in r["movimentos"]:
            self.assertEqual(m["sha"], SHA)
            self.assertEqual(m["origem"], {"arquivo": a["arquivo"], "aba": "Lançamentos", "linha": m["indice_linha"]})
            self.assertRegex(m["id"], r"^RF-[0-9A-F]{12}$")
        self.assertEqual(r["origem"]["sha256"], SHA)
        self.assertEqual([m["id"] for m in nf.normalizar(a)["movimentos"]], [m["id"] for m in r["movimentos"]])   # determinístico
        outro = nf.normalizar(planilha([CAB, ENTRADA, None, None, SAIDA], primeira=7, sha="e" * 64))
        self.assertNotEqual(outro["movimentos"][0]["id"], r["movimentos"][0]["id"])
        sem_sha = planilha([CAB, ENTRADA]); del sem_sha["sha256"]
        self.assertEqual(codigos(nf.normalizar(sem_sha)), ["ORIGEM_SEM_SHA"])     # sem origem rastreável, nada é normalizado

    def test_16_nome_do_arquivo_nao_decide(self):
        a = nf.normalizar(planilha([CAB, ENTRADA], nome="extrato-santander.xlsx"))["movimentos"]
        b = nf.normalizar(planilha([CAB, ENTRADA], nome="qualquer.xlsx"))["movimentos"]
        self.assertEqual([{k: v for k, v in m.items() if k != "origem"} for m in a], [{k: v for k, v in m.items() if k != "origem"} for m in b])
        r = nf.normalizar(planilha([["Nome", "Telefone"]], nome="relatorio-financeiro.xlsx"))
        self.assertEqual(r["situacao"], "NAO_NORMALIZADO")
        # PDF (ex.: comprovantes de pagamento) não tem leitor aqui: nada é inferido
        r = nf.normalizar({"arquivo": "x.pdf", "sha256": SHA, "leitura": "EXTRAIDO_PDF", "conteudo": {"paginas": [{"texto": "EXTRATO"}]}})
        self.assertEqual((r["situacao"], r["movimentos"], codigos(r)), ("NAO_NORMALIZADO", [], ["FONTE_SEM_ADAPTADOR"]))

    def test_17_aba_oculta_nao_usada(self):
        a = planilha([CAB, ENTRADA])
        oculta = copy.deepcopy(a["conteudo"]["abas"][0]); oculta.update(aba="Rascunho", oculta=True)
        a["conteudo"]["abas"].append(oculta)
        r = nf.normalizar(a)
        self.assertEqual((len(r["movimentos"]), codigos(r)), (1, ["ABA_OCULTA_NAO_USADA"]))


# ---------------------------------------------------------------- v1.1: competência, situação, validações cruzadas, contraparte
DOC_FICTICIO = "00.000.000/0001-00"
CAB2 = ["Código", "Data de Vencimento", "Data de Quitação", "É Despesa", "Valor Entrada", "Valor Saída", "Valor Pago",
        "Situação", "Cliente.CPF/CNPJ", "Cliente.Nome Fantasia", "Cliente.Razão Social", "Nº Documento", "Plano de Contas",
        "Banco", "Breve Descrição", "Empresa.CNPJ", "Data de Competência"]


def linha2(despesa="Sim", entrada=None, saida="250,00", pago="250,00", situacao="Foi Pago", competencia="15/08/2026",
           doc=DOC_FICTICIO, fantasia="FORNECEDOR TESTE", razao="FORNECEDOR TESTE LTDA"):
    return [201, "2026-09-10", "2026-09-12", despesa, entrada, saida, pago, situacao, doc, fantasia, razao, "NF 900",
            "Despesas Gerais", "Banco Fictício 999", "Serviço fictício", "00.000.000/0001-91", competencia]


class NormalizadorV11(unittest.TestCase):
    def test_18_competencia_mapeada_separadamente(self):
        r = nf.normalizar(planilha([CAB2, linha2()]))
        self.assertEqual(r["mapeamento"]["Lançamentos"]["data_competencia"], {"coluna": 16, "cabecalho": "Data de Competência"})
        self.assertEqual(r["movimentos"][0]["data_competencia"], "2026-08-15")
        mensal = nf.normalizar(planilha([CAB2, linha2(competencia="08/2026")]))["movimentos"][0]
        self.assertEqual(mensal["data_competencia"], "2026-08")
        self.assertIn("COMPETENCIA_MENSAL", mensal["evidencias"])
        r = nf.normalizar(planilha([[c if c != "Data de Competência" else "Competência" for c in CAB2], linha2()]))
        self.assertEqual(r["movimentos"][0]["data_competencia"], "2026-08-15")
        ruim = nf.normalizar(planilha([CAB2, linha2(competencia="13/2026")]))
        self.assertEqual((codigos(ruim), ruim["movimentos"]), (["DATA_INVALIDA"], []))

    def test_19_competencia_nao_substitui_quitacao(self):
        m = nf.normalizar(planilha([CAB2, linha2()]))["movimentos"][0]
        self.assertEqual((m["data"], m["data_vencimento"], m["data_quitacao"], m["data_competencia"]),
                         (None, "2026-09-10", "2026-09-12", "2026-08-15"))
        sem_quit = linha2(); sem_quit[2] = None
        m = nf.normalizar(planilha([CAB2, sem_quit]))["movimentos"][0]
        self.assertEqual((m["data"], m["data_quitacao"], m["data_competencia"]), (None, None, "2026-08-15"))

    def test_20_foi_pago_realizado(self):
        for s in ("Foi Pago", "PAGO", "quitado", "Recebido"):
            r = nf.normalizar(planilha([CAB2, linha2(situacao=s)]))
            self.assertEqual((r["movimentos"][0]["situacao"], r["linhas_nao_realizadas"]), ("REALIZADO", []), s)
            self.assertIn("SITUACAO_REALIZADO", r["movimentos"][0]["evidencias"])

    def test_21_em_aberto_nao_vira_movimento(self):
        r = nf.normalizar(planilha([CAB2, linha2(situacao="Em aberto", pago=None), linha2()]))
        self.assertEqual([m["indice_linha"] for m in r["movimentos"]], [3])
        nr = r["linhas_nao_realizadas"][0]
        self.assertEqual((nr["indice_linha"], nr["situacao"], nr["situacao_origem"], nr["valor"], nr["natureza"]),
                         (2, "EM_ABERTO", "Em aberto", Decimal("250.00"), "SAIDA"))
        self.assertTrue(nr["motivo"] and "Situação" in nr["evidencia"] and nr["sha"] == SHA)
        self.assertEqual(r["situacao"], "NORMALIZADO")                          # não é erro estrutural do arquivo
        self.assertEqual([(p["codigo"], p["nivel"]) for p in r["pendencias"]], [("LINHAS_NAO_REALIZADAS", "INFORMATIVO")])
        self.assertEqual(r["resumo"]["nao_realizadas"], 1)

    def test_22_cancelado_nao_vira_movimento(self):
        r = nf.normalizar(planilha([CAB2, linha2(situacao="Cancelado")]))
        self.assertEqual((r["movimentos"], r["linhas_nao_realizadas"][0]["situacao"]), ([], "CANCELADO"))

    def test_23_situacao_desconhecida_conservadora(self):
        for s in ("Pago parcialmente", "Não pago?", "Pago?", "Pagamento agendado"):     # sem heurística por trecho do texto
            r = nf.normalizar(planilha([CAB2, linha2(situacao=s)]))
            self.assertEqual(r["movimentos"], [], s)
            self.assertEqual(r["linhas_nao_realizadas"][0]["situacao"], "INDETERMINADO", s)
            self.assertEqual((codigos(r), r["situacao"]), (["SITUACAO_NAO_RECONHECIDA"], "NORMALIZADO_COM_PENDENCIAS"), s)

    def test_32_situacao_vazia_e_ausente(self):
        for vazia in ("", "   ", None):
            r = nf.normalizar(planilha([CAB2, linha2(situacao=vazia)]))
            self.assertEqual(r["linhas_nao_realizadas"][0]["situacao"], "AUSENTE", repr(vazia))
            self.assertEqual(codigos(r), ["SITUACAO_AUSENTE"], repr(vazia))

    def test_33_situacao_ausente_nao_entra_como_realizado(self):
        r = nf.normalizar(planilha([CAB2, linha2(situacao=None), linha2()]))
        self.assertEqual([(m["indice_linha"], m["situacao"]) for m in r["movimentos"]], [(3, "REALIZADO")])
        self.assertEqual(r["resumo"]["nao_realizadas"], 1)

    def test_34_situacao_ausente_gera_atencao(self):
        p = nf.normalizar(planilha([CAB2, linha2(situacao="")]))["pendencias"][0]
        self.assertEqual((p["nivel"], p["codigo"], p["indice_linha"]), ("ATENCAO", "SITUACAO_AUSENTE", 2))
        self.assertIn("não informada", p["problema"])
        self.assertIn("Não é possível confirmar", p["impacto"])
        self.assertIn("Validar a situação ou utilizar outra evidência estruturada aprovada", p["o_que_fazer"])

    def test_35_situacao_ausente_rastreavel(self):
        nr = nf.normalizar(planilha([CAB2, linha2(situacao=None)], primeira=9))["linhas_nao_realizadas"][0]
        self.assertEqual((nr["indice_linha"], nr["valor"], nr["natureza"], nr["data_vencimento"], nr["data_quitacao"],
                          nr["data_competencia"], nr["sha"]),
                         (10, Decimal("250.00"), "SAIDA", "2026-09-10", "2026-09-12", "2026-08-15", SHA))
        self.assertEqual(nr["origem"], {"arquivo": "RECEBIDOS/2026-09/arquivo-sem-nome-util.xlsx", "aba": "Lançamentos", "linha": 10})
        self.assertIn("Situação", nr["evidencia"])
        self.assertIsNone(nr["situacao_origem"])

    def test_36_texto_desconhecido_diferente_de_ausente(self):
        r = nf.normalizar(planilha([CAB2, linha2(situacao="Agendado"), linha2(situacao="")]))
        self.assertEqual([x["situacao"] for x in r["linhas_nao_realizadas"]], ["INDETERMINADO", "AUSENTE"])
        self.assertEqual(codigos(r), ["SITUACAO_NAO_RECONHECIDA", "SITUACAO_AUSENTE"])

    def test_37_sem_coluna_situacao_compativel(self):
        sem = [c for c in CAB2 if c != "Situação"]
        lin = linha2(); del lin[CAB2.index("Situação")]
        r = nf.normalizar(planilha([sem, lin]))
        m = r["movimentos"][0]
        self.assertEqual((m["situacao"], r["linhas_nao_realizadas"], r["pendencias"]), (None, [], []))   # nada inventado
        self.assertNotIn("SITUACAO_REALIZADO", m["evidencias"])
        self.assertIn("situacao", r["campos_complementares_ausentes"])

    def test_24_saida_e_despesa_sim_consistente(self):
        r = nf.normalizar(planilha([CAB2, linha2(despesa="Sim")]))
        self.assertEqual((r["movimentos"][0]["natureza"], r["pendencias"]), ("SAIDA", []))
        self.assertIn("E_DESPESA_CONSISTENTE", r["movimentos"][0]["evidencias"])

    def test_25_entrada_e_despesa_nao_consistente(self):
        r = nf.normalizar(planilha([CAB2, linha2(despesa="Não", entrada="250,00", saida=None)]))
        self.assertEqual((r["movimentos"][0]["natureza"], r["pendencias"]), ("ENTRADA", []))
        self.assertIn("E_DESPESA_CONSISTENTE", r["movimentos"][0]["evidencias"])

    def test_26_divergencia_e_despesa(self):
        r = nf.normalizar(planilha([CAB2, linha2(despesa="Não"), linha2(despesa="Sim", entrada="10,00", saida=None, pago="10,00")]))
        self.assertEqual(r["movimentos"], [])                                   # natureza nunca é trocada em silêncio
        self.assertEqual(codigos(r), ["DIVERGENCIA_NATUREZA", "DIVERGENCIA_NATUREZA"])
        self.assertEqual((r["pendencias"][0]["natureza_movimento"], r["pendencias"][0]["e_despesa"]), ("SAIDA", "Não"))
        # sem colunas de entrada/saída nem tipo, "É Despesa" pode definir a natureza (registrado na evidência)
        r = nf.normalizar(planilha([["Data", "Valor", "É Despesa"], ["2026-09-01", "70,00", "Sim"]]))
        self.assertEqual(r["movimentos"][0]["natureza"], "SAIDA")
        self.assertIn("NATUREZA_PELA_COLUNA_E_DESPESA", r["movimentos"][0]["evidencias"])

    def test_27_valor_pago_igual_consistente(self):
        m = nf.normalizar(planilha([CAB2, linha2(saida="1.250,00", pago=1250)]))["movimentos"][0]
        self.assertEqual(m["valor"], Decimal("1250.00"))
        self.assertIn("VALOR_PAGO_CONSISTENTE", m["evidencias"])

    def test_28_valor_pago_divergente(self):
        r = nf.normalizar(planilha([CAB2, linha2(saida="250,00", pago="240,00")]))
        self.assertEqual((r["movimentos"], codigos(r)), ([], ["DIVERGENCIA_VALOR_PAGO"]))
        p = r["pendencias"][0]
        self.assertEqual((p["valor_movimento"], p["valor_pago"]), (Decimal("250.00"), Decimal("240.00")))   # ambos preservados

    def test_29_contraparte_mapeada(self):
        m = nf.normalizar(planilha([CAB2, linha2()]))["movimentos"][0]
        self.assertEqual(m["contraparte"], {"nome": "FORNECEDOR TESTE LTDA", "nome_fantasia": "FORNECEDOR TESTE", "documento": DOC_FICTICIO})
        self.assertEqual(tuple(m), nf.CAMPOS_MOVIMENTO_RELATORIO)
        # só os campos que existem: sem nome fantasia na linha, a chave não aparece (nada inventado)
        m = nf.normalizar(planilha([CAB2, linha2(fantasia=None, doc=None)]))["movimentos"][0]
        self.assertEqual(m["contraparte"], {"nome": "FORNECEDOR TESTE LTDA"})
        self.assertEqual(nf.mascarar_documento(DOC_FICTICIO), "00**********00")

    def test_30_sem_contraparte_nao_bloqueia(self):
        r = nf.normalizar(planilha([CAB, ENTRADA]))
        self.assertEqual((r["situacao"], r["movimentos"][0]["contraparte"]), ("NORMALIZADO", None))
        self.assertIn("contraparte", r["campos_complementares_ausentes"])
        r = nf.normalizar(planilha([CAB2, linha2(fantasia=None, doc=None, razao=None)]))
        self.assertEqual((r["situacao"], r["movimentos"][0]["contraparte"]), ("NORMALIZADO", None))

    def test_31_dados_pessoais_fora_das_mensagens(self):
        cpf = "000.000.000-00"
        linhas = [CAB2, linha2(doc=cpf, saida="250,00", pago="1,00"), linha2(doc=cpf, despesa="Não"),
                  linha2(doc=cpf, situacao="??"), linha2(doc=cpf, competencia="xx")]
        r = nf.normalizar(planilha(linhas))
        self.assertEqual(len(r["pendencias"]), 4)
        textos = json.dumps(nf.para_json(r["pendencias"]), ensure_ascii=False)
        for sensivel in (cpf, "00000000000", "FORNECEDOR TESTE"):
            self.assertNotIn(sensivel, textos)


if __name__ == "__main__":
    unittest.main(verbosity=2)
