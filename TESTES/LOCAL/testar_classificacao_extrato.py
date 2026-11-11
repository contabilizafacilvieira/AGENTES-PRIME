"""Classificação de extrato bancário pelo CONTEÚDO, nunca pelo nome do arquivo (DOC-CLASS-01..10). Somente textos FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/LOCAL/testar_classificacao_extrato.py
"""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(RAIZ / "AGENTES/FINANCEIRO/ferramentas"))
import conferencia_financeira as f
import documentos_local as d

EXTRATO = ("BANCO FICTICIO S.A.\nEXTRATO DE CONTA CORRENTE\nEMPRESA FICTICIA LTDA Agência: 0001 Conta: 99999-9\n"
           "Período: 01/09/2026 a 30/09/2026\nSALDO ANTERIOR 1.000,00\n"
           "02/09/2026 TARIFA FICTICIA -10,00 990,00\n05/09/2026 PIX RECEBIDO FICTICIO 500,00 1.490,00\n"
           "10/09/2026 PAGAMENTO FICTICIO -90,00 1.400,00\nSALDO FINAL 1.400,00")
PAGFOR = ("RELATORIO DE PAGAMENTOS FICTICIO\nCOMPROVANTE DE PAGAMENTO DE BOLETO\nBENEFICIARIO: FORNECEDOR TESTE LTDA\n"
          "PAGADOR: EMPRESA FICTICIA LTDA\nAgência: 0001 Conta: 99999-9\nVALOR NOMINAL: 1.000,00\nBLQ OUTROS\n"
          "DATA DO PAGAMENTO: 10/09/2026\nLINHA DIGITAVEL 00000.00000 00000.000000 00000.000000 0 00000000000000")
PROMO = ("Banco Fictício — abra sua conta corrente!\nAgência digital 0001, conta sem tarifa.\nExtrato sempre à mão no aplicativo.\n"
         "Promoção válida de 01/09/2026 a 30/09/2026.")


def pdf(texto, nome="documento.pdf"):
    return {"arquivo": f"RECEBIDOS/2026-09/{nome}", "extensao": ".pdf", "leitura": "EXTRAIDO_PDF", "sha256": "c" * 64,
            "conteudo": {"paginas_total": 1, "paginas": [{"pagina": 1, "texto": texto}]}}


def eh_extrato(a):
    return d.classificar(a).startswith("Extrato ")


class ClassificacaoExtrato(unittest.TestCase):
    def test_doc_class_01_nome_extrato_conteudo_boleto(self):
        a = pdf(PAGFOR, "Extrato Santander.pdf")
        self.assertFalse(eh_extrato(a))
        self.assertNotEqual(d.encaminhamento(a).get("tipo", "")[:8], "Extrato ")

    def test_doc_class_02_nome_generico_estrutura_de_extrato(self):
        a = pdf(EXTRATO, "arquivo-0001.pdf")
        self.assertEqual(d.classificar(a), d.TIPO_EXTRATO_PDF)
        self.assertEqual(d.encaminhamento(a)["area"], "FINANCEIRO")

    def test_doc_class_03_nome_santander_cc_sozinho_insuficiente(self):
        for texto in ("", "Documento sem conteúdo útil.", "Movimentação bancária"):
            a = pdf(texto, "BPX-FIN-SANTANDER-CC-202609.pdf")
            self.assertFalse(eh_extrato(a), texto)
            self.assertEqual(d.avaliar_extrato(a)["nome_arquivo"], "SINAL_AUXILIAR_COMPATIVEL")

    def test_doc_class_04_pagfor_prevalece_sobre_nome(self):
        # mesmo com linhas de pagamento datadas e saldo, marcas de comprovante impedem a decisão automática de extrato
        texto = PAGFOR + "\nPeríodo: 01/09/2026 a 30/09/2026\n10/09/2026 PAGAMENTO BOLETO 1.000,00\n11/09/2026 PAGAMENTO BOLETO 250,00"
        a = pdf(texto, "Extrato-Santander-CC.pdf")
        av = d.avaliar_extrato(a)
        self.assertEqual(av["decisao"], "AMBIGUO")
        self.assertTrue(d.classificar(a).startswith(d.AMBIGUO))
        self.assertIsNone(d.encaminhamento(a)["area"])                  # vai à triagem, sem área presumida

    def test_doc_class_05_ambiguo_sem_confianca_pelo_nome(self):
        texto = "Agência: 0001 Conta: 99999-9\n05/09/2026 PIX RECEBIDO FICTICIO 500,00"     # 1 movimento, sem período/saldo
        com_nome, sem_nome = d.avaliar_extrato(pdf(texto, "extrato-banco.pdf")), d.avaliar_extrato(pdf(texto, "x.pdf"))
        self.assertEqual((com_nome["decisao"], sem_nome["decisao"]), ("NAO_EXTRATO", "NAO_EXTRATO"))
        self.assertEqual(com_nome["evidencias"], sem_nome["evidencias"])   # o nome não acrescenta evidência estrutural

    def test_doc_class_06_extrato_ficticio_valido(self):
        santander = ("Santander Empresas\nEMPRESA FICTICIA Agência: 1234 Conta: 11111-1\nPeríodos: 01/10/2026 a 31/10/2026\n"
                     "20/10/2026 PIX RECEBIDO FICTICIO 12345678 50,00 950,00\n10/10/2026 PAGAMENTO FICTICIO 0000000000 -20,00 900,00\n1/1")
        self.assertEqual(d.classificar(pdf(santander)), d.TIPO_EXTRATO_SANTANDER)   # leitor específico do Financeiro
        self.assertEqual(d.classificar(pdf(EXTRATO, "Extrato Banco.pdf")), d.TIPO_EXTRATO_PDF)

    def test_doc_class_07_promocional_sem_movimentacao(self):
        a = pdf(PROMO, "extrato-santander-promocao.pdf")
        self.assertFalse(eh_extrato(a))
        self.assertEqual(d.avaliar_extrato(a)["decisao"], "NAO_EXTRATO")

    def test_doc_class_08_evidencias_preservadas(self):
        rota = d.encaminhamento(pdf(EXTRATO, "arquivo.pdf"))
        ev = rota["evidencias_extrato"]
        self.assertEqual(ev["decisao"], "EXTRATO")
        self.assertTrue({"AGENCIA", "CONTA", "PERIODO", "SALDO"} <= set(ev["evidencias"]))
        self.assertIn("MOVIMENTACAO_DATADA:3", ev["evidencias"])
        self.assertIn("nome do arquivo não decide", ev["criterio"])
        recusado = d.encaminhamento(pdf(PAGFOR, "Extrato Santander.pdf"))["evidencias_extrato"]
        self.assertEqual((recusado["decisao"], recusado["nome_arquivo"]), ("NAO_EXTRATO", "SINAL_AUXILIAR_COMPATIVEL"))
        self.assertIn("BENEFICIARIO", recusado["contra_evidencias"])

    def test_doc_class_09_nao_depende_da_empresa(self):
        outra = EXTRATO.replace("EMPRESA FICTICIA LTDA", "OUTRA EMPRESA TESTE SA")
        self.assertEqual(d.classificar(pdf(EXTRATO)), d.classificar(pdf(outra)))
        self.assertEqual(d.avaliar_extrato(pdf(EXTRATO))["evidencias"], d.avaliar_extrato(pdf(outra))["evidencias"])

    def test_doc_class_10_financeiro_recusa_mesmo_com_metadado_errado(self):
        a = pdf(PAGFOR, "Extrato Santander.pdf")
        falso = {"area": "FINANCEIRO", "situacao": "DISPONIVEL_PARA_ENCAMINHAMENTO", "copias_suporte": [], "tipo": d.TIPO_EXTRATO_SANTANDER}
        cad = {"cnpjs": ["00000000000191"], "contas": {}, "cnpjs_outras_empresas": {}}
        with tempfile.TemporaryDirectory() as vazio, patch.dict(os.environ, {"AGENTES_PRIME_CLIENTES": vazio}), \
                patch.object(f, "cadastro", return_value=copy.deepcopy(cad)), patch.object(f, "encaminhamento", return_value=falso):
            c = f.Conferencia("EMPRESA-FICTICIA", "2026-09", "SOL-2099-999999")
            c.carregar([a])
            c.preparar_movimentos()
            bloqueios = c.triagem()
        self.assertEqual((c.extratos, c.movimentos), ([], []))          # defesa em profundidade: o Financeiro revalida
        self.assertTrue(bloqueios and bloqueios[0].startswith("Nenhum extrato utilizável"))


# ---------------------------------------------------------------- v1.4.2: precedência estrutural (DOC-BANK-01..10)
sys.path.insert(0, str(RAIZ / "TESTES/FINANCEIRO"))
import testar_normalizador_bancario as fx        # extrato fictício no leiaute Extrato Consolidado (adaptador bancário)

PUBLICIDADE = ("Banco Fictício — soluções para sua empresa\nPagamento a fornecedores: use PAGFOR no internet banking.\n"
               "Cuidado com o golpe do boleto: confira o Beneficiário e o código de barras antes de pagar.")


def pdf_paginas(textos, nome="documento.pdf"):
    return {"arquivo": f"RECEBIDOS/2026-09/{nome}", "extensao": ".pdf", "leitura": "EXTRAIDO_PDF", "sha256": "c" * 64,
            "conteudo": {"paginas_total": len(textos), "paginas": [{"pagina": i, "texto": x} for i, x in enumerate(textos, 1)]}}


class PrecedenciaEstrutural(unittest.TestCase):
    def test_doc_bank_01_pagfor_em_pagina_publicitaria(self):
        a = pdf_paginas([PUBLICIDADE, EXTRATO])                     # leiaute genérico, sem adaptador específico
        av = d.avaliar_extrato(a)
        self.assertEqual((av["decisao"], d.classificar(a)), ("EXTRATO", d.TIPO_EXTRATO_PDF))
        self.assertIn("PAGFOR", av["marcas_isoladas_fora_da_movimentacao"])
        self.assertEqual(av["contra_evidencias"], [])

    def test_doc_bank_02_beneficiario_em_aviso(self):
        av = d.avaliar_extrato(pdf_paginas([EXTRATO, PUBLICIDADE]))
        self.assertEqual(av["decisao"], "EXTRATO")
        self.assertTrue({"BENEFICIARIO", "CODIGO DE BARRAS"} <= set(av["marcas_isoladas_fora_da_movimentacao"]))
        # leiaute com adaptador bancário (publicidade com PAGFOR/Beneficiário/linha digitável): extrato
        a = fx.extrato()
        self.assertEqual((d.classificar(a), d.encaminhamento(a)["area"]), (d.TIPO_EXTRATO_PDF, "FINANCEIRO"))

    def test_doc_bank_03_pagfor_real_nao_e_extrato(self):
        self.assertFalse(eh_extrato(pdf(PAGFOR)))
        self.assertFalse(eh_extrato(pdf_paginas([PAGFOR, PAGFOR])))

    def test_doc_bank_04_comprovante_com_agencia_conta(self):
        comprovante = "COMPROVANTE DE TRANSFERENCIA\nAgência: 0001 Conta: 99999-9\nVALOR: 150,00\nDATA: 10/09/2026\nAUTENTICACAO 0A1B2C"
        av = d.avaliar_extrato(pdf(comprovante))
        self.assertEqual(av["decisao"], "NAO_EXTRATO")
        self.assertTrue({"AGENCIA", "CONTA"} <= set(av["evidencias"]))

    def test_doc_bank_05_nome_extrato_conteudo_pagfor(self):
        a = pdf_paginas([PAGFOR, PUBLICIDADE], "Extrato Santander.pdf")
        self.assertFalse(eh_extrato(a))
        self.assertEqual(d.avaliar_extrato(a)["adaptadores_bancarios"], [])

    def test_doc_bank_06_nome_generico_estrutura(self):
        self.assertEqual(d.classificar(pdf_paginas([PUBLICIDADE, EXTRATO], "scan-0007.pdf")), d.TIPO_EXTRATO_PDF)
        self.assertEqual(d.classificar(fx.extrato(nome="arquivo.pdf")), d.TIPO_EXTRATO_PDF)

    def test_doc_bank_07_estrutura_insuficiente_nao_promovida(self):
        pouco = "Agência: 0001 Conta: 99999-9\n05/09/2026 PIX RECEBIDO FICTICIO 500,00"
        self.assertEqual(d.avaliar_extrato(pdf_paginas([pouco, PUBLICIDADE]))["decisao"], "NAO_EXTRATO")
        # marcas de pagamento DENTRO da página de movimentação continuam impedindo a decisão automática
        misturado = EXTRATO + "\nBENEFICIARIO: FORNECEDOR TESTE LTDA\nPAGADOR: EMPRESA FICTICIA LTDA"
        self.assertEqual(d.avaliar_extrato(pdf_paginas([misturado]))["decisao"], "AMBIGUO")

    def test_doc_bank_08_evidencias_registradas(self):
        ev = d.encaminhamento(fx.extrato())["evidencias_extrato"]
        self.assertEqual(ev["decisao"], "EXTRATO")
        self.assertIn("ADAPTADOR_BANCARIO:SANTANDER_EXTRATO_CONSOLIDADO_PJ", ev["evidencias"])
        self.assertEqual(ev["adaptadores_bancarios"], ["SANTANDER_EXTRATO_CONSOLIDADO_PJ"])
        self.assertTrue(ev["marcas_isoladas_fora_da_movimentacao"] or ev["contra_evidencias"])
        self.assertIn("páginas com movimentação", ev["criterio"])

    def test_doc_bank_09_nao_depende_da_empresa(self):
        outra = [x.replace("EMPRESA FICTICIA LTDA", "OUTRA EMPRESA TESTE SA") for x in (fx.P1, fx.P2, fx.P3, fx.P4)]
        self.assertEqual(d.classificar(fx.extrato(outra)), d.classificar(fx.extrato()))
        self.assertEqual(d.avaliar_extrato(fx.extrato(outra))["decisao"], "EXTRATO")

    def test_doc_bank_10_nao_depende_do_santander(self):
        a = pdf_paginas([PUBLICIDADE, EXTRATO.replace("BANCO FICTICIO S.A.", "COOPERATIVA TESTE")])
        av = d.avaliar_extrato(a)
        self.assertEqual((av["decisao"], av["adaptadores_bancarios"]), ("EXTRATO", []))
        self.assertNotIn("SANTANDER", sem := d.sem_acento(json.dumps(av)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
