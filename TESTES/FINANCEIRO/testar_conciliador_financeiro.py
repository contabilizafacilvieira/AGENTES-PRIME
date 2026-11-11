"""Motor genérico de conciliação financeira banco × relatório (MATCH-01..40). Somente dados FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/FINANCEIRO/testar_conciliador_financeiro.py
Os dois lados são contratos fictícios (MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1 e MOVIMENTOS_FINANCEIROS_NORMALIZADOS_V1).
"""
import copy
import json
import os
import random
import sys
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "AGENTES/FINANCEIRO/ferramentas"))
sys.path.insert(0, str(RAIZ / "TESTES/FINANCEIRO"))
import conciliador_financeiro as cf

CNPJ = "00000000000191"          # fictício
D = Decimal


def b(i, data, valor, nat="DEBITO", desc="LANCAMENTO", doc=None):
    return {"id": f"BM-{i}", "data": data, "valor": D(valor), "natureza": nat, "descricao": desc, "documento": doc, "sha256_origem": "a" * 64}


def a(i, quit, valor, nat="SAIDA", doc=None, cp=None, desc=None, data=None, comp=None):
    return {"id": f"RF-{i}", "data": data, "data_quitacao": quit, "data_competencia": comp, "valor": D(valor), "natureza": nat,
            "documento": doc, "contraparte": cp, "descricao": desc, "sha": "b" * 64}


def banco(*movs, situacao="NORMALIZADO"):
    return [{"contrato": cf.CONTRATO_BANCARIO, "situacao": situacao, "adaptador": "ADAPTADOR_FICTICIO", "origem": {"sha256": "a" * 64}, "movimentos": list(movs)}]


def aux(*movs, situacao="NORMALIZADO"):
    return [{"contrato": cf.CONTRATO_AUXILIAR, "situacao": situacao, "adaptador": "PLANILHA_FINANCEIRA_GENERICA", "origem": {"sha256": "b" * 64}, "movimentos": list(movs)}]


def rodar(bs, as_):
    return cf.conciliar(banco(*bs), aux(*as_))


def classe(r, bid=None, aid=None):
    for x in r["associacoes"]:
        if (bid and bid in x["bancarios"]) or (aid and aid in x["auxiliares"]):
            return x
    raise AssertionError("associação não encontrada")


class Conciliador(unittest.TestCase):
    def test_match_01_documento_exato(self):
        r = rodar([b(1, "2026-10-05", "100.00", doc="123456")], [a(1, "2026-10-05", "100.00", doc="123456")])
        x = classe(r, "BM-1")
        self.assertEqual((x["classificacao"], x["cardinalidade"], x["auxiliares"]), ("CONCILIADO", "1x1", ["RF-1"]))
        self.assertIn("DOCUMENTO_EXATO", x["criterios_atendidos"])

    def test_match_02_contraparte_forte(self):
        r = rodar([b(1, "2026-10-05", "250.00", desc="PIX ENVIADO ALFA COMERCIO LTDA")],
                  [a(1, "2026-10-05", "250.00", cp={"nome": "ALFA COMERCIO LTDA"})])
        x = classe(r, "BM-1")
        self.assertEqual(x["classificacao"], "CONCILIADO")
        self.assertIn("CONTRAPARTE_NOME_FORTE", x["criterios_atendidos"])

    def test_match_03_sem_evidencia_extra_provavel(self):
        x = classe(rodar([b(1, "2026-10-05", "80.00")], [a(1, "2026-10-05", "80.00")]), "BM-1")
        self.assertEqual((x["classificacao"], x["decisao"], x["libera_associacao_financeira"]), ("PROVAVEL", "PENDENTE_SUPERVISOR", False))

    def test_match_04_dois_candidatos_identicos(self):
        r = rodar([b(1, "2026-10-05", "80.00")], [a(1, "2026-10-05", "80.00"), a(2, "2026-10-05", "80.00")])
        x = classe(r, "BM-1")
        self.assertEqual((x["classificacao"], x["auxiliares"], len(x["candidatos"])), ("AMBIGUO", ["RF-1", "RF-2"], 2))

    def test_match_05_valor_diferente(self):
        self.assertEqual(classe(rodar([b(1, "2026-10-05", "80.00", doc="1234")], [a(1, "2026-10-05", "80.01", doc="1234")]), "BM-1")["classificacao"], "NAO_CONCILIADO")

    def test_match_06_natureza_incompativel(self):
        r = rodar([b(1, "2026-10-05", "80.00", nat="CREDITO", doc="1234")], [a(1, "2026-10-05", "80.00", nat="SAIDA", doc="1234")])
        self.assertEqual(classe(r, "BM-1")["classificacao"], "NAO_CONCILIADO")
        self.assertEqual(classe(r, aid="RF-1")["classificacao"], "NAO_CONCILIADO")

    def test_match_07_um_dia_com_evidencia_forte(self):
        # política: ±1 dia + 1 evidência forte = CONCILIADO; ±2 dias exige 2 fortes
        x = classe(rodar([b(1, "2026-10-06", "90.00", doc="777888")], [a(1, "2026-10-05", "90.00", doc="777888")]), "BM-1")
        self.assertEqual((x["classificacao"], x["diferenca_dias_maxima"]), ("CONCILIADO", 1))
        dois = classe(rodar([b(1, "2026-10-07", "90.00", doc="777888")], [a(1, "2026-10-05", "90.00", doc="777888")]), "BM-1")
        self.assertEqual(dois["classificacao"], "PROVAVEL")
        dois_fortes = classe(rodar([b(1, "2026-10-07", "90.00", doc="777888", desc=f"PIX {CNPJ}")],
                                   [a(1, "2026-10-05", "90.00", doc="777888", cp={"documento": "00.000.000/0001-91"})]), "BM-1")
        self.assertEqual(dois_fortes["classificacao"], "CONCILIADO")

    def test_match_08_fora_da_janela(self):
        r = rodar([b(1, "2026-10-09", "90.00", doc="777888")], [a(1, "2026-10-05", "90.00", doc="777888")])
        self.assertEqual(classe(r, "BM-1")["classificacao"], "NAO_CONCILIADO")

    def test_match_09_documento_normalizado(self):
        self.assertEqual(cf.norm_documento(" 00123-45 "), cf.norm_documento("12345"))
        self.assertEqual(cf.norm_documento("nf.a-17"), "NFA17")
        self.assertIsNone(cf.norm_documento("1"))
        x = classe(rodar([b(1, "2026-10-05", "60.00", doc="0012345")], [a(1, "2026-10-05", "60.00", doc="12.345")]), "BM-1")
        self.assertEqual(x["classificacao"], "CONCILIADO")

    def test_match_10_contraparte_acento_pontuacao(self):
        x = classe(rodar([b(1, "2026-10-05", "70.00", desc="PIX ENVIADO ALFA COMERCIO LTDA")],
                         [a(1, "2026-10-05", "70.00", cp={"nome": "Álfa Comércio Ltda."})]), "BM-1")
        self.assertEqual(x["classificacao"], "CONCILIADO")

    def test_match_11_substring_curta_nao_e_forte(self):
        x = classe(rodar([b(1, "2026-10-05", "70.00", desc="PIX ENVIADO ALFA SERVICOS INDUSTRIAIS")],
                         [a(1, "2026-10-05", "70.00", cp={"nome": "ALFA"})]), "BM-1")
        self.assertEqual(x["classificacao"], "PROVAVEL")
        self.assertIn("CONTRAPARTE_NOME_PARCIAL", x["criterios_atendidos"])
        self.assertNotIn("CONTRAPARTE_NOME_FORTE", x["criterios_atendidos"])

    def test_match_12_descricao_generica(self):
        x = classe(rodar([b(1, "2026-10-05", "70.00", desc="PIX ENVIADO PAGAMENTO TRANSFERENCIA")],
                         [a(1, "2026-10-05", "70.00", desc="PIX PAGAMENTO BOLETO TRANSFERENCIA")]), "BM-1")
        self.assertEqual(x["classificacao"], "PROVAVEL")
        self.assertNotIn("DESCRICAO_COMPATIVEL", x["criterios_atendidos"])
        so_descricao = classe(rodar([b(1, "2026-10-05", "70.00", desc="SERVICO MANUTENCAO GERADOR")],
                                    [a(1, "2026-10-05", "70.00", desc="MANUTENCAO GERADOR")]), "BM-1")
        self.assertEqual(so_descricao["classificacao"], "PROVAVEL")           # descrição sozinha nunca concilia
        self.assertIn("DESCRICAO_COMPATIVEL", so_descricao["criterios_atendidos"])

    def test_match_13_um_banco_dois_auxiliares_forte(self):
        cp = {"documento": "00.000.000/0001-91"}
        x = classe(rodar([b(1, "2026-10-05", "300.00", desc=f"PIX ENVIADO {CNPJ}")],
                         [a(1, "2026-10-05", "100.00", cp=cp), a(2, "2026-10-05", "200.00", cp=cp)]), "BM-1")
        self.assertEqual((x["classificacao"], x["cardinalidade"], x["auxiliares"]), ("CONCILIADO", "1xN", ["RF-1", "RF-2"]))
        self.assertIn("SOMA_EXATA", x["criterios_atendidos"])

    def test_match_14_um_banco_dois_auxiliares_so_soma(self):
        x = classe(rodar([b(1, "2026-10-05", "300.00")], [a(1, "2026-10-05", "100.00"), a(2, "2026-10-05", "200.00")]), "BM-1")
        self.assertEqual((x["classificacao"], x["cardinalidade"], x["libera_associacao_financeira"]), ("PROVAVEL", "1xN", False))

    def test_match_15_dois_bancos_um_auxiliar_forte(self):
        r = rodar([b(1, "2026-10-05", "100.00", desc="PIX ENVIADO BETA TRANSPORTES"), b(2, "2026-10-05", "200.00", desc="PIX ENVIADO BETA TRANSPORTES")],
                  [a(1, "2026-10-05", "300.00", cp={"nome": "BETA TRANSPORTES LTDA"})])
        x = classe(r, aid="RF-1")
        self.assertEqual((x["classificacao"], x["cardinalidade"], x["bancarios"]), ("CONCILIADO", "Nx1", ["BM-1", "BM-2"]))

    def test_match_16_combinacao_ambigua(self):
        r = rodar([b(1, "2026-10-05", "300.00")],
                  [a(1, "2026-10-05", "100.00"), a(2, "2026-10-05", "200.00"), a(3, "2026-10-05", "150.00"), a(4, "2026-10-05", "150.00")])
        x = classe(r, "BM-1")
        self.assertEqual((x["classificacao"], len(x["candidatos"])), ("AMBIGUO", 2))

    def test_match_17_auxiliar_nao_consumido_duas_vezes(self):
        r = rodar([b(1, "2026-10-05", "50.00", doc="9999"), b(2, "2026-10-05", "50.00", doc="9999")], [a(1, "2026-10-05", "50.00", doc="9999")])
        usos = [x for x in r["associacoes"] if "RF-1" in x["auxiliares"] and x["classificacao"] == "CONCILIADO"]
        self.assertEqual(usos, [])
        self.assertEqual(classe(r, aid="RF-1")["classificacao"], "AMBIGUO")

    def test_match_18_banco_nao_consumido_duas_vezes(self):
        r = rodar([b(1, "2026-10-05", "50.00", doc="9999")], [a(1, "2026-10-05", "50.00", doc="9999"), a(2, "2026-10-05", "50.00", doc="9999")])
        self.assertEqual(sum(1 for x in r["associacoes"] if "BM-1" in x["bancarios"]), 1)
        self.assertEqual(classe(r, "BM-1")["classificacao"], "AMBIGUO")

    def test_match_19_conflito_global(self):
        # B1 casa forte com A1; B2 também casa forte com A1 e com A2 → componente único disputado = AMBÍGUO
        r = rodar([b(1, "2026-10-05", "40.00", doc="5555"), b(2, "2026-10-05", "40.00", doc="5555")],
                  [a(1, "2026-10-05", "40.00", doc="5555"), a(2, "2026-10-06", "40.00", doc="5555")])
        x = classe(r, "BM-1")
        self.assertEqual((x["classificacao"], x["bancarios"], x["auxiliares"]), ("AMBIGUO", ["BM-1", "BM-2"], ["RF-1", "RF-2"]))

    def test_match_20_ids_deterministicos(self):
        x = classe(rodar([b(1, "2026-10-05", "100.00", doc="123456")], [a(1, "2026-10-05", "100.00", doc="123456")]), "BM-1")
        self.assertEqual(x["id"], cf._id_assoc(["BM-1"], ["RF-1"]))
        self.assertRegex(x["id"], r"^CF-[0-9A-F]{12}$")

    def cenario(self):
        cp = {"nome": "GAMA SERVICOS TECNICOS"}
        bs = [b(1, "2026-10-05", "100.00", doc="123456"), b(2, "2026-10-06", "80.00"), b(3, "2026-10-07", "300.00", desc="PIX GAMA SERVICOS TECNICOS"),
              b(4, "2026-10-08", "55.00", nat="CREDITO"), b(5, "2026-10-09", "12.34")]
        as_ = [a(1, "2026-10-05", "100.00", doc="123456"), a(2, "2026-10-06", "80.00"), a(3, "2026-10-07", "100.00", cp=cp),
               a(4, "2026-10-07", "200.00", cp=cp), a(5, "2026-10-08", "55.00", nat="ENTRADA"), a(6, "2026-10-08", "55.00", nat="ENTRADA"),
               a(7, "2026-10-20", "999.00")]
        return bs, as_

    def test_match_21_segunda_execucao_igual(self):
        bs, as_ = self.cenario()
        self.assertEqual(rodar(bs, as_), rodar(copy.deepcopy(bs), copy.deepcopy(as_)))

    def test_match_22_ordem_de_entrada(self):
        bs, as_ = self.cenario()
        base = json.dumps(cf.para_json(rodar(bs, as_)), sort_keys=True)
        for semente in range(5):
            random.Random(semente).shuffle(bs)
            random.Random(semente + 10).shuffle(as_)
            self.assertEqual(json.dumps(cf.para_json(rodar(bs, as_)), sort_keys=True), base)

    def test_match_23_decimal_sem_float(self):
        bs, as_ = self.cenario()
        r = rodar(bs, as_)
        self.assertIsInstance(r["resumo"]["valor_bancario_total"], Decimal)
        self.assertEqual(json.loads(json.dumps(cf.para_json(r)))["resumo"]["valor_bancario_total"], "547.34")
        with self.assertRaises(ValueError):
            cf.dinheiro(10.5)
        r = cf.conciliar(banco(dict(b(1, "2026-10-05", "1.00"), valor=1.0)), aux())
        self.assertEqual(r["situacao"], "ENTRADA_INVALIDA")

    def test_match_24_cpf_cnpj_nao_integral(self):
        cp = {"nome": "DELTA LTDA", "documento": "00.000.000/0001-91"}
        r = rodar([b(1, "2026-10-05", "10.00", desc=f"PIX RECEBIDO {CNPJ}", nat="CREDITO")], [a(1, "2026-10-05", "10.00", nat="ENTRADA", cp=cp)])
        self.assertEqual(classe(r, "BM-1")["classificacao"], "CONCILIADO")
        texto = json.dumps(cf.para_json(r), ensure_ascii=False)
        self.assertNotIn(CNPJ, texto)
        self.assertNotIn("00.000.000/0001-91", texto)
        self.assertEqual(cf.mascarar(CNPJ), "00**********91")

    def test_match_25_competencia_nao_e_data_bancaria(self):
        r = rodar([b(1, "2026-10-05", "10.00", doc="4444")], [a(1, None, "10.00", doc="4444", comp="2026-10-05")])
        self.assertEqual(classe(r, "BM-1")["classificacao"], "NAO_CONCILIADO")
        self.assertIn("Sem data", classe(r, aid="RF-1")["motivo"])

    def test_match_26_quitacao_tem_prioridade(self):
        r = rodar([b(1, "2026-10-05", "10.00", doc="4444")], [a(1, "2026-10-05", "10.00", doc="4444", data="2026-10-20")])
        self.assertEqual(classe(r, "BM-1")["classificacao"], "CONCILIADO")
        so_data = rodar([b(1, "2026-10-20", "10.00", doc="4444")], [a(1, None, "10.00", doc="4444", data="2026-10-20")])
        self.assertEqual(classe(so_data, "BM-1")["classificacao"], "CONCILIADO")       # sem quitação, usa `data`

    def test_match_27_28_29_somente_conciliado_libera(self):
        bs, as_ = self.cenario()
        r = rodar(bs, as_)
        por = {i: x for x in r["associacoes"] for i in x["bancarios"]}
        self.assertEqual({i: por[i]["classificacao"] for i in por},
                         {"BM-1": "CONCILIADO", "BM-2": "PROVAVEL", "BM-3": "CONCILIADO", "BM-4": "AMBIGUO", "BM-5": "NAO_CONCILIADO"})
        self.assertEqual(r["bloqueantes"], ["BM-2", "BM-4", "BM-5"])                  # PROVÁVEL, AMBÍGUO e NÃO CONCILIADO
        for i in ("BM-2", "BM-4", "BM-5"):
            self.assertFalse(por[i]["libera_associacao_financeira"])
            self.assertEqual(por[i]["decisao"], "PENDENTE_SUPERVISOR")

    def test_match_30_conciliado_nao_e_suporte_fiscal(self):
        r = rodar([b(1, "2026-10-05", "100.00", doc="123456")], [a(1, "2026-10-05", "100.00", doc="123456")])
        x = classe(r, "BM-1")
        self.assertEqual((x["libera_associacao_financeira"], x["suporte_documental"]), (True, False))

    def test_match_31_fonte_bancaria_ausente(self):
        r = cf.conciliar([], aux(a(1, "2026-10-05", "10.00")))
        self.assertEqual((r["situacao"], r["resumo"]["movimentos_bancarios"], r["resumo"]["auxiliar_sem_associacao"]), ("SEM_FONTE_BANCARIA", 0, 1))

    def test_match_32_fonte_auxiliar_ausente(self):
        r = cf.conciliar(banco(b(1, "2026-10-05", "10.00")), [])
        self.assertEqual((r["situacao"], r["bloqueantes"]), ("SEM_FONTE_AUXILIAR", ["BM-1"]))

    def test_match_33_contrato_bancario_bloqueado(self):
        r = cf.conciliar(banco(b(1, "2026-10-05", "10.00", doc="4444"), situacao="BLOQUEADO"), aux(a(1, "2026-10-05", "10.00", doc="4444")))
        self.assertEqual((r["resumo"]["movimentos_bancarios"], r["fontes"]["bancarias"][0]["usada"]), (0, False))
        self.assertIn("FONTE_BANCARIA_NAO_USADA", [p["codigo"] for p in r["pendencias"]])

    def test_match_34_contrato_auxiliar_com_divergencia(self):
        r = cf.conciliar(banco(b(1, "2026-10-05", "10.00", doc="4444")), aux(a(1, "2026-10-05", "10.00", doc="4444"), situacao="NAO_NORMALIZADO"))
        self.assertEqual((r["resumo"]["movimentos_auxiliares"], classe(r, "BM-1")["classificacao"]), (0, "NAO_CONCILIADO"))
        # linha com divergência (É Despesa/Valor Pago) nunca chega ao motor: não está em `movimentos` do contrato auxiliar
        import normalizador_financeiro as nf
        import testar_normalizador_financeiro as tnf
        contrato = nf.normalizar(tnf.planilha([tnf.CAB2, tnf.linha2(pago="1,00"), tnf.linha2()]))
        self.assertEqual([m["indice_linha"] for m in contrato["movimentos"]], [3])
        r = cf.conciliar(banco(), [contrato])
        self.assertEqual(r["resumo"]["movimentos_auxiliares"], 1)

    def test_match_35_36_37_resumo(self):
        bs, as_ = self.cenario()
        s = rodar(bs, as_)["resumo"]
        self.assertEqual((s["movimentos_bancarios"], s["movimentos_auxiliares"]), (5, 7))
        self.assertEqual(s["bancarios"], {"conciliado": 2, "provavel": 1, "ambiguo": 1, "nao_conciliado": 1})
        self.assertEqual((s["banco_sem_associacao"], s["auxiliar_sem_associacao"]), (1, 1))
        self.assertEqual((s["grupos_1x1"], s["grupos_1xN"], s["grupos_Nx1"]), (2, 1, 0))
        self.assertEqual((s["valor_bancario_conciliado"], s["valor_bancario_nao_conciliado"]), (D("400.00"), D("147.34")))
        self.assertEqual((s["percentual_quantidade"], s["percentual_valor"]), (D("40.00"), D("73.08")))
        self.assertEqual(s["por_natureza"]["ENTRADAS"], {"movimentos_bancarios": 1, "conciliados": 0, "valor_bancario": D("55.00"), "valor_conciliado": D("0.00")})
        self.assertEqual((s["por_natureza"]["SAIDAS"]["movimentos_bancarios"], s["por_natureza"]["SAIDAS"]["valor_conciliado"]), (4, D("400.00")))

    def test_match_38_39_limite_cardinalidade(self):
        auxs = [a(i, "2026-10-05", "1.00") for i in range(1, 20)]                       # 19 candidatos > limite
        inicio = time.perf_counter()
        r = rodar([b(1, "2026-10-05", "3.50")], auxs)
        self.assertLess(time.perf_counter() - inicio, 2.0)
        x = classe(r, "BM-1")
        self.assertEqual((x["classificacao"], x["necessita_analise_manual"]), ("NAO_CONCILIADO", True))
        self.assertIn("excede o limite", x["motivo"])
        # 4 auxiliares somando o valor (acima do LIMITE_GRUPO=3) não são tentados
        r = rodar([b(1, "2026-10-05", "4.00")], [a(i, "2026-10-05", "1.00") for i in range(1, 5)])
        self.assertEqual((classe(r, "BM-1")["classificacao"], classe(r, "BM-1")["cardinalidade"]), ("NAO_CONCILIADO", "1x0"))

    def test_match_40_score_explicavel(self):
        x = classe(rodar([b(1, "2026-10-06", "100.00", doc="123456")], [a(1, "2026-10-05", "100.00", doc="123456")]), "BM-1")
        self.assertEqual(x["score"]["componentes"], {"VALOR_EXATO": 40, "NATUREZA_COMPATIVEL": 20, "DATA_1_DIA": 15, "DOCUMENTO_EXATO": 15})
        self.assertEqual(x["score"]["total"], 90)
        self.assertIn("regras", x["score"]["observacao"])
        self.assertIn("CONTRAPARTE_DOCUMENTO", x["criterios_ausentes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
