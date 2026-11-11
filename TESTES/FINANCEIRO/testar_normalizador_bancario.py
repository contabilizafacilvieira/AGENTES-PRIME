"""Normalizador Bancário + adaptador Santander Extrato Consolidado PJ (BANCO-01..26). Somente textos FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/FINANCEIRO/testar_normalizador_bancario.py
Os documentos são dicionários no formato devolvido pelo extrator (texto por página). Empresa, agência, conta e valores
são inventados; nenhum documento real é lido.
"""
import copy
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "AGENTES/FINANCEIRO/ferramentas"))
import normalizador_bancario as nb

SHA = "d" * 64
TOPO = "EXTRATO CONSOLIDADO \noutubro/2026\nExtrato_PJ_A4_Basico  - 1/1/2020\nBALP_TESTE_FICTICIO.PIM - \nPagina:  {n}/4\n"
CAB = "Data Descrição Nº Documento   Movimentos (R$) Saldo (R$)\nCréditos Débitos\n"
P1 = (TOPO.format(n=1) + "Prezado Cliente, \nSoluções Santander Empresas para o seu negócio.\n - Pagamento a fornecedores: use PAGFOR.\n"
      "01/10  OFERTA ESPECIAL DE TARIFA - 99,00 \n - Cobranças: emita boletos; confira o Beneficiário e a linha digitável.\n")
P2 = (TOPO.format(n=2) + "Fale Conosco\nResumo - outubro/2026\nNome\nEMPRESA FICTICIA LTDA\nAgência\n0001\nConta Corrente\n00.000001-0\n"
      "(=) Saldo Disponível de Conta Corrente em 30/09 1.000,00 \n(=) Saldo Disponível de Conta Corrente em 31/10 1.300,00 \n"
      "Conta Corrente\nMovimentação\n" + CAB +
      "SALDO EM 30/09 1.000,00 \n"
      "01/10  TARIFA FICTICIA -  10,00-   \n"
      " PIX RECEBIDO CLIENTE TESTE - 500,00  1.490,00 \n"
      "05/10  PAGAMENTO DE TITULO\n0001.000000001\n123456  90,00- 1.400,00 \n"
      "07/10  LANCAMENTO QUALQUER XYZ - 100,00    \n")
P3 = (TOPO.format(n=3) + CAB +
      " PIX ENVIADO FORNECEDOR TESTE LTDA -  200,00- 1.300,00 \n"
      "SALDO EM 31/10 1.300,00 \nA - Bloqueio Dia / ADM\n“Se sua empresa não tiver limite ... 1% e multa de 2%.”\n"
      "Saldos por Período\nDia\nSaldo de\nConta\nCorrente\n(+)\nSaldo\nDisponível\n(=)\n"
      "01 1.490,00 0,00 0,00 0,00 0,00 0,00 1.490,00\n05 1.400,00 0,00 0,00 0,00 0,00 0,00 1.400,00\n"
      "07 1.300,00 0,00 0,00 0,00 0,00 0,00 1.300,00\n* Valores deduzidos do saldo disponível para contas sem limite.\n")
P4 = (TOPO.format(n=4) + "Pacote de Serviços\nPACOTE FICTICIO\nCONTA CORRENTE EXTRATO PJ - AUTOATENDIMENTO 20\nTED - PIX 6\n"
      "Valor da Mensalidade (R$) 358,00\n10/10  MENSALIDADE PROMOCIONAL - 12,00 \nDia de Débito 10\n")


def extrato(paginas=None, sha=SHA, nome="arquivo-0001.pdf", total=None):
    paginas = paginas or [P1, P2, P3, P4]
    return {"arquivo": f"RECEBIDOS/2026-10/{nome}", "extensao": ".pdf", "sha256": sha, "leitura": "EXTRAIDO_PDF",
            "conteudo": {"paginas_total": total or len(paginas), "paginas_requer_ocr": [], "paginas_vazias": [],
                         "paginas": [{"pagina": i, "situacao": "TEXTO", "origem": "PYPDF", "texto": t} for i, t in enumerate(paginas, 1)]}}


def codigos(r):
    return [p["codigo"] for p in r["pendencias"]]


class NormalizadorBancario(unittest.TestCase):
    def setUp(self):
        self.r = nb.normalizar(extrato())
        self.m = self.r["movimentos"]

    def test_01_extrato_valido(self):
        self.assertEqual((self.r["situacao"], self.r["adaptador"], self.r["contrato"]),
                         ("NORMALIZADO", "SANTANDER_EXTRATO_CONSOLIDADO_PJ", "MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1"))
        self.assertEqual((self.r["titular"], self.r["agencia"], self.r["conta"], self.r["banco"]["codigo"]),
                         ("EMPRESA FICTICIA LTDA", "0001", "00.000001-0", "033"))
        self.assertEqual((self.r["periodo_inicio"], self.r["periodo_fim"]), ("2026-10-01", "2026-10-31"))
        self.assertEqual(len(self.m), 5)
        for m in self.m:
            self.assertEqual(tuple(m), nb.CAMPOS_MOVIMENTO)

    def test_02_nome_santander_conteudo_nao_extrato(self):
        r = nb.normalizar(extrato([P1, P4], nome="Extrato Santander CC.pdf"))
        self.assertEqual((r["situacao"], codigos(r), r["movimentos"]), ("BLOQUEADO", ["FONTE_SEM_ADAPTADOR"], []))

    def test_03_pagfor_nao_e_extrato(self):
        pagfor = ("Santander Empresas\nCOMPROVANTE DE PAGAMENTO - PAGFOR\nBENEFICIARIO: FORNECEDOR TESTE LTDA\nPAGADOR: EMPRESA FICTICIA LTDA\n"
                  "Agência: 0001 Conta: 00.000001-0\nVALOR NOMINAL: 1.000,00\nBLQ OUTROS\n10/10/2026 PAGAMENTO BOLETO 1.000,00\nPagina: 1/1")
        r = nb.normalizar(extrato([pagfor], nome="EXTRATO-SANTANDER-CC-PagFor.pdf"))
        self.assertEqual(codigos(r), ["FONTE_SEM_ADAPTADOR"])

    def test_04_nome_generico_reconhecido(self):
        a = nb.normalizar(extrato(nome="documento.pdf"))
        b = nb.normalizar(extrato(nome="Santander-Extrato.pdf"))
        sem_origem = lambda r: [{k: v for k, v in m.items() if k != "origem_documento"} for m in r["movimentos"]]
        self.assertEqual(a["situacao"], "NORMALIZADO")
        self.assertEqual(sem_origem(a), sem_origem(b))                       # o nome não altera reconhecimento nem identidade

    def test_05_aritmetica_consistente(self):
        v = self.r["validacao_aritmetica"]
        self.assertEqual((v["saldo_inicial"], v["total_creditos"], v["total_debitos"], v["saldo_calculado"], v["saldo_final_informado"]),
                         (Decimal("1000.00"), Decimal("600.00"), Decimal("300.00"), Decimal("1300.00"), Decimal("1300.00")))
        self.assertEqual((v["diferenca"], v["situacao"], v["tolerancia"]), (Decimal("0.00"), "CONSISTENTE", Decimal("0.00")))

    def test_06_divergencia_aritmetica(self):
        p3 = P3.replace("SALDO EM 31/10 1.300,00", "SALDO EM 31/10 1.300,01")
        r = nb.normalizar(extrato([P1, P2, p3, P4]))
        self.assertEqual(r["situacao"], "BLOQUEADO")
        self.assertIn("ARITMETICA_DIVERGENTE", codigos(r))
        self.assertEqual((r["validacao_aritmetica"]["diferenca"], r["movimentos"]), (Decimal("-0.01"), []))
        self.assertEqual(len(r["movimentos_nao_confirmados"]), 5)                 # preservados só para diagnóstico

    def test_07_credito(self):
        m = self.m[1]
        self.assertEqual((m["natureza"], m["valor"], m["descricao"], m["documento"]), ("CREDITO", Decimal("500.00"), "PIX RECEBIDO CLIENTE TESTE", None))

    def test_08_debito(self):
        m = self.m[0]
        self.assertEqual((m["natureza"], m["valor"], m["data"]), ("DEBITO", Decimal("10.00"), "2026-10-01"))

    def test_09_descricao_multilinha(self):
        m = self.m[2]
        self.assertEqual(m["descricao"], "PAGAMENTO DE TITULO 0001.000000001")
        self.assertEqual((m["linhas"]["linha_inicial"], m["linhas"]["linha_final"]), (23, 25))

    def test_10_data_herdada_somente_em_grupo_aberto(self):
        self.assertEqual((self.m[1]["data"], self.m[1]["evidencias"][0]), ("2026-10-01", "DATA_HERDADA_DO_GRUPO"))
        # movimento sem data depois de um saldo (grupo fechado): a data NÃO é herdada
        p2 = P2.replace("123456  90,00- 1.400,00 \n", "123456  90,00- 1.400,00 \n PIX SEM DATA TESTE - 5,00  1.405,00 \n")
        r = nb.normalizar(extrato([P1, p2, P3, P4]))
        self.assertEqual((r["situacao"], codigos(r)), ("BLOQUEADO", ["DATA_NAO_COMPROVADA"]))

    def test_11_continuacao_entre_paginas(self):
        m = self.m[4]                                                            # grupo de 07/10 continua na página 3
        self.assertEqual((m["data"], m["pagina"], m["saldo_apos"]), ("2026-10-07", 3, Decimal("1300.00")))
        # descrição que começa numa página e termina na seguinte
        p2 = P2.replace("07/10  LANCAMENTO QUALQUER XYZ - 100,00    \n", "07/10  LANCAMENTO EM DUAS PAGINAS\n")
        p3 = P3.replace(CAB, CAB + "PARTE FINAL TESTE\n- 100,00    \n")
        r = nb.normalizar(extrato([P1, p2, p3, P4]))
        x = r["movimentos"][3]
        self.assertEqual((r["situacao"], x["descricao"], x["linhas"]["pagina_inicial"], x["linhas"]["pagina_final"]),
                         ("NORMALIZADO", "LANCAMENTO EM DUAS PAGINAS PARTE FINAL TESTE", 2, 3))
        self.assertIn("CONTINUACAO_ENTRE_PAGINAS", x["evidencias"])

    def test_12_saldo_inicial_nao_e_movimento(self):
        self.assertEqual(self.r["saldo_inicial"]["data"], "2026-09-30")
        self.assertNotIn("SALDO EM", " ".join(m["descricao"] for m in self.m))

    def test_13_saldo_final_nao_e_movimento(self):
        self.assertEqual((self.r["saldo_final"]["data"], self.r["saldo_final"]["valor"]), ("2026-10-31", Decimal("1300.00")))
        self.assertTrue(all(m["valor"] != Decimal("1300.00") for m in self.m))

    def test_14_publicidade_ignorada(self):
        self.assertTrue(all(m["pagina"] in (2, 3) for m in self.m))
        self.assertNotIn("OFERTA", " ".join(m["descricao"] for m in self.m))

    def test_15_pacote_de_servicos_ignorado(self):
        self.assertFalse(any("MENSALIDADE" in m["descricao"] or m["valor"] in (Decimal("358.00"), Decimal("12.00")) for m in self.m))

    def test_16_documento_preservado(self):
        self.assertEqual([m["documento"] for m in self.m], [None, None, "123456", None, None])

    def test_17_pagina_e_evidencia(self):
        for m in self.m:
            self.assertTrue(m["pagina"] and m["linhas"]["linha_inicial"] and m["evidencias"])
            self.assertEqual((m["sha256_origem"], m["banco"]["nome"], m["agencia"], m["conta"]), (SHA, "SANTANDER", "0001", "00.000001-0"))
        self.assertEqual([m["indice_origem"] for m in self.m], [1, 2, 3, 4, 5])

    def test_18_ids_deterministicos(self):
        self.assertEqual([m["id"] for m in nb.normalizar(extrato())["movimentos"]], [m["id"] for m in self.m])
        self.assertEqual(len({m["id"] for m in self.m}), 5)
        self.assertRegex(self.m[0]["id"], r"^BM-[0-9A-F]{12}$")
        outro = nb.normalizar(extrato(sha="e" * 64))["movimentos"]
        self.assertFalse({m["id"] for m in outro} & {m["id"] for m in self.m})

    def test_19_sha_obrigatorio(self):
        r = nb.normalizar(extrato(sha=None))
        self.assertEqual((r["situacao"], codigos(r)), ("BLOQUEADO", ["ORIGEM_SEM_SHA"]))

    def test_20_nenhum_adaptador(self):
        r = nb.normalizar(extrato(["Documento qualquer\nPagina: 1/1"]))
        self.assertEqual((codigos(r), r["adaptador"]), (["FONTE_SEM_ADAPTADOR"], None))

    def test_21_dois_adaptadores_ambiguo(self):
        with patch.object(nb, "ADAPTADORES", [nb.SantanderExtratoConsolidadoPJ(), nb.SantanderExtratoConsolidadoPJ()]):
            r = nb.normalizar(extrato())
        self.assertEqual((r["situacao"], codigos(r), r["movimentos"]), ("BLOQUEADO", ["FONTE_AMBIGUA"], []))

    def test_22_documento_incompleto(self):
        casos = {"falta_pagina": extrato([P1, P2, P3], total=4),
                 "pagina_ocr": copy.deepcopy(extrato()),
                 "numeracao": extrato([P1, P2, P3.replace("Pagina:  3/4", "Pagina:  9/4"), P4])}
        casos["pagina_ocr"]["conteudo"]["paginas"][3]["situacao"] = "REQUER_OCR"
        for nome, a in casos.items():
            r = nb.normalizar(a)
            self.assertEqual(r["situacao"], "BLOQUEADO", nome)
            self.assertTrue(set(codigos(r)) & {"DOCUMENTO_INCOMPLETO", "PAGINACAO_NAO_CONFIRMADA"}, nome)
        # trecho da movimentação sem valor (linha não interpretável): nada é inventado
        p3 = P3.replace("SALDO EM 31/10", "31/10  TEXTO SEM VALOR TESTE\nSALDO EM 31/10")
        self.assertEqual(codigos(nb.normalizar(extrato([P1, P2, p3, P4]))), ["LINHA_NAO_INTERPRETADA"])

    def test_23_saldos_diarios_consistentes(self):
        v = self.r["validacao_saldos_diarios"]
        self.assertEqual((v["dias_informados"], v["dias_conferidos"], v["divergencias"], v["situacao"], v["comparado_com"]),
                         (3, 3, [], "CONSISTENTE", "saldo_disponivel"))
        self.assertEqual(self.r["validacao_saldos_impressos"], {"conferidos": 3, "divergencias": []})

    def test_24_saldo_diario_divergente(self):
        p3 = P3.replace("05 1.400,00 0,00 0,00 0,00 0,00 0,00 1.400,00", "05 1.410,00 0,00 0,00 0,00 0,00 0,00 1.410,00")
        r = nb.normalizar(extrato([P1, P2, p3, P4]))
        self.assertEqual((r["situacao"], codigos(r)), ("BLOQUEADO", ["SALDO_DIARIO_DIVERGENTE"]))
        self.assertEqual(r["validacao_saldos_diarios"]["divergencias"][0]["data"], "2026-10-05")
        self.assertEqual(r["validacao_aritmetica"]["situacao"], "CONSISTENTE")     # nada foi "ajustado" para concordar

    def test_25_decimal_sem_float(self):
        textos = json.dumps(nb.para_json(self.r), ensure_ascii=False)
        self.assertEqual(json.loads(textos)["movimentos"][1]["valor"], "500.00")
        for m in self.m:
            self.assertIsInstance(m["valor"], Decimal)
            self.assertEqual(m["valor"], m["valor"].quantize(Decimal("0.01")))
        with self.assertRaises(ValueError):
            nb.dinheiro("12.5")

    def test_26_descricao_livre_sem_lista_fechada(self):
        m = self.m[3]
        self.assertEqual((m["descricao"], m["natureza"], m["valor"]), ("LANCAMENTO QUALQUER XYZ", "CREDITO", Decimal("100.00")))
        self.assertEqual(self.m[2]["descricao"].split()[0], "PAGAMENTO")
        self.assertEqual(self.m[4]["descricao"], "PIX ENVIADO FORNECEDOR TESTE LTDA")


if __name__ == "__main__":
    unittest.main(verbosity=2)
