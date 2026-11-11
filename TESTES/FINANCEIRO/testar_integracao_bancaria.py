"""Integração Documentos → Normalizador Bancário → Financeiro (FIN-BANK-01..15 + duas fontes). Somente dados FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/FINANCEIRO/testar_integracao_bancaria.py
Cadastro simulado, pasta CLIENTES temporária vazia, documentos no formato do extrator. Sem Conciliação, sem Contabilidade.
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
sys.path.insert(0, str(RAIZ / "AGENTES/FINANCEIRO/ferramentas"))
sys.path.insert(0, str(RAIZ / "TESTES/FINANCEIRO"))
import conferencia_financeira as f
import normalizador_bancario as nb
import testar_integracao_normalizador as aux           # relatório financeiro fictício (fonte auxiliar), outubro/2026
import testar_normalizador_bancario as fx              # extrato fictício (Extrato Consolidado), outubro/2026

CONTA = f.chave_conta("033", "0001", "00.000001-0")
CAD = {"cnpjs": ["00000000000191"], "cnpjs_outras_empresas": {},
       "contas": {CONTA: {"banco": "033", "agencia": "0001", "conta": "00.000001-0", "titular": "00000000000191", "situacao": "ATIVA"}}}
NAO_IDENTIFICADO = {"arquivo": "RECEBIDOS/2026-10/anotacao.pdf", "extensao": ".pdf", "sha256": "f" * 64, "leitura": "EXTRAIDO_PDF",
                    "conteudo": {"paginas_total": 1, "paginas": [{"pagina": 1, "situacao": "TEXTO", "texto": "Anotação fictícia sem natureza."}]}}


def conferir(arquivos, cadastro=CAD):
    with tempfile.TemporaryDirectory() as vazio, patch.dict(os.environ, {"AGENTES_PRIME_CLIENTES": vazio}), \
            patch.object(f, "cadastro", return_value=copy.deepcopy(cadastro)):
        c = f.Conferencia("EMPRESA-FICTICIA", "2026-10", "SOL-2099-999999")
        c.carregar(arquivos)
        c.preparar_movimentos()
        bloqueios = c.triagem()
        if bloqueios:
            return c, c.montar_bloqueado(bloqueios, [])
        c.corresponder({})
        return c, c.montar({})


def tipos(r):
    return [p["tipo"] for p in r["pendencias"]]


class IntegracaoBancaria(unittest.TestCase):
    def test_fin_bank_01_normalizado_utilizavel(self):
        _, r = conferir([fx.extrato()])
        fb = r["fonte_bancaria"]
        self.assertEqual((fb["extratos_recebidos"], fb["extratos_utilizaveis"], fb["contrato"]), (1, 1, "MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1"))
        fonte = fb["fontes_normalizadas"][0]
        self.assertEqual((fonte["utilizavel"], fonte["adaptador"], fonte["situacao"]), (True, "SANTANDER_EXTRATO_CONSOLIDADO_PJ", "NORMALIZADO"))
        self.assertEqual(r["verificacao_extratos"][0]["situacao"], "CONCLUIDA")    # cobertura + aritmética do Financeiro

    def test_fin_bank_02_movimentos_bancarios(self):
        _, r = conferir([fx.extrato()])
        self.assertEqual(len(r["movimentos"]), 5)
        # o Financeiro ordena por conta, data e id (regra existente); a natureza vem do contrato bancário de cada movimento
        self.assertTrue(all(m["direcao"] == m["rastreio_bancario"]["natureza"] for m in r["movimentos"]))
        self.assertEqual(sorted(m["direcao"] for m in r["movimentos"]), ["CREDITO"] * 2 + ["DEBITO"] * 3)
        self.assertTrue(all(m["id"].startswith("MOV-") and m["rastreio_bancario"]["id"].startswith("BM-") for m in r["movimentos"]))

    def test_fin_bank_03_auxiliar_separada(self):
        _, r = conferir([fx.extrato(), aux.relatorio()])
        self.assertEqual((len(r["movimentos"]), len(r["movimentos_financeiros_auxiliares"])), (5, 2))
        self.assertTrue(all(m["fonte"] == "FONTE_AUXILIAR_FINANCEIRA" and m["id"].startswith("RF-") for m in r["movimentos_financeiros_auxiliares"]))

    def test_fin_bank_04_sem_casamento_nao_ha_suporte(self):
        # v1.6: o motor roda, mas neste cenário nada casa (datas/valores distintos); nenhum suporte/relação é criado
        _, r = conferir([fx.extrato(), aux.relatorio()])
        self.assertTrue(all(m["conciliacao_financeira"]["classificacao"] == "NAO_CONCILIADO" for m in r["movimentos"]))
        self.assertTrue(all(m["relacao"] == [] and m["conciliacao_financeira"]["auxiliares"] == [] for m in r["movimentos"]))

    def test_fin_bank_05_aritmetica_divergente_recusada(self):
        p3 = fx.P3.replace("SALDO EM 31/10 1.300,00", "SALDO EM 31/10 1.300,01")
        c, r = conferir([fx.extrato([fx.P1, fx.P2, p3, fx.P4])])
        self.assertEqual((c.extratos, r["fonte_bancaria"]["extratos_utilizaveis"]), ([], 0))
        self.assertIn("EXTRATO_BANCARIO_RECUSADO", tipos(r))
        recusa = next(p for p in r["pendencias"] if p["tipo"] == "EXTRATO_BANCARIO_RECUSADO")["descricao"]
        self.assertTrue("Impacto:" in recusa and "O que fazer:" in recusa and "ARITMETICA_DIVERGENTE" in recusa)
        self.assertTrue(r["bloqueio_lote"][0].startswith("Nenhum extrato utilizável"))

    def test_fin_bank_06_ambigua_recusada(self):
        with patch.object(nb, "ADAPTADORES", [nb.SantanderExtratoConsolidadoPJ(), nb.SantanderExtratoConsolidadoPJ()]):
            c, r = conferir([fx.extrato()])
        self.assertEqual(c.extratos, [])
        self.assertIn("FONTE_AMBIGUA", next(p for p in r["pendencias"] if p["tipo"] == "EXTRATO_BANCARIO_RECUSADO")["descricao"])

    def test_fin_bank_07_sem_adaptador_nao_vira_extrato(self):
        c, r = conferir([NAO_IDENTIFICADO])
        self.assertEqual((c.extratos, r["fonte_bancaria"]["fontes_normalizadas"]), ([], []))
        self.assertIn("DOCUMENTO_NAO_IDENTIFICADO", tipos(r))           # segue o caminho comum de documentos

    def test_fin_bank_08_sha_ausente_recusado(self):
        c, r = conferir([fx.extrato(sha=None)])
        self.assertEqual(c.extratos, [])
        self.assertIn("ORIGEM_SEM_SHA", json.dumps(r["pendencias"], ensure_ascii=False))

    def test_fin_bank_09_incompleto_recusado(self):
        c, r = conferir([fx.extrato([fx.P1, fx.P2, fx.P3], total=4)])
        self.assertEqual(c.extratos, [])
        self.assertIn("DOCUMENTO_INCOMPLETO", json.dumps(r["pendencias"], ensure_ascii=False))

    def test_fin_bank_10_rastreabilidade(self):
        _, r = conferir([fx.extrato()])
        for m in r["movimentos"]:
            t = m["rastreio_bancario"]
            self.assertEqual((t["contrato"], t["sha256"]), ("MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1", fx.SHA))
            self.assertTrue(t["pagina"] in (2, 3) and t["linhas"]["linha_inicial"])
            self.assertIn(f"página {t['pagina']}, linha {t['linhas']['linha_inicial']}", m["origens"][0])

    def test_fin_bank_11_remove_bloqueio_sem_extrato(self):
        _, r = conferir([fx.extrato()])
        # o bloqueio "nenhum extrato utilizável" sai; entra o bloqueio fail-closed (movimentos sem associação confirmada)
        self.assertFalse(any(b.startswith("Nenhum extrato utilizável") for b in r["bloqueio_lote"]))
        self.assertEqual(len(r["bloqueio_lote"]), 1)
        self.assertIn("sem associação financeira confirmada", r["bloqueio_lote"][0])
        # mesmo extrato com conta NÃO cadastrada: titularidade não é presumida
        sem_conta = dict(CAD, contas={})
        _, r = conferir([fx.extrato()], cadastro=sem_conta)
        self.assertIn("CONTA_NAO_CADASTRADA", tipos(r))
        self.assertTrue(r["bloqueio_lote"][0].startswith("Nenhum extrato utilizável"))

    def test_fin_bank_12_outras_pendencias_permanecem(self):
        _, r = conferir([fx.extrato(), NAO_IDENTIFICADO])
        self.assertIn("DOCUMENTO_NAO_IDENTIFICADO", tipos(r))
        self.assertIn("ASSOCIACAO_FINANCEIRA_NAO_CONFIRMADA", tipos(r))

    def test_fin_bank_13_auxiliar_nao_substitui_bancaria(self):
        _, r = conferir([aux.relatorio()])
        self.assertEqual((r["fonte_bancaria"]["extratos_utilizaveis"], r["movimentos"]), (0, []))
        self.assertTrue(r["bloqueio_lote"])

    def test_fin_bank_14_bancaria_nao_substitui_auxiliar(self):
        _, so_aux = conferir([aux.relatorio()])
        _, ambos = conferir([fx.extrato(), aux.relatorio()])
        self.assertEqual(ambos["movimentos_financeiros_auxiliares"], so_aux["movimentos_financeiros_auxiliares"])
        self.assertEqual(ambos["fonte_auxiliar_financeira"]["resumo"], so_aux["fonte_auxiliar_financeira"]["resumo"])

    def test_fin_bank_15_legado_nao_escolhido(self):
        with patch.object(f, "ler_santander_pdf", wraps=f.ler_santander_pdf) as legado:
            conferir([fx.extrato()])
        self.assertEqual(legado.call_count, 0)
        legado_layout = aux.extrato()                                   # leiaute antigo: sem adaptador → leitor legado
        with patch.object(f, "ler_santander_pdf", wraps=f.ler_santander_pdf) as legado:
            c, _ = conferir([legado_layout], cadastro=aux.CAD)
        self.assertEqual(legado.call_count, 1)
        self.assertEqual(c.extratos[0]["formato"], "PDF_SANTANDER")

    def test_duas_fontes_simultaneas(self):
        _, r = conferir([fx.extrato(), aux.relatorio()])
        fb, fa = r["fonte_bancaria"], r["fonte_auxiliar_financeira"]
        self.assertEqual((fb["extratos_utilizaveis"], fb["movimentos_bancarios"]), (1, 5))
        self.assertEqual((fa["resumo"]["relatorios"], fa["resumo"]["movimentos"]), (1, 2))
        self.assertEqual((len(r["movimentos"]), len(r["movimentos_financeiros_auxiliares"])), (5, 2))
        self.assertFalse({m["id"] for m in r["movimentos"]} & {m["id"] for m in r["movimentos_financeiros_auxiliares"]})
        self.assertEqual(r["conciliacao_financeira"]["resumo"]["movimentos_bancarios"], 5)
        json.dumps(r, ensure_ascii=False)                                # resultado serializável (sem Decimal solto)



# ---------------------------------------------------------------- v1.6: motor de conciliação no Financeiro (FIN-CONC)
def extrato_identificado():
    """Mesmo extrato fictício, com documento/contraparte identificáveis (aritmética e saldos inalterados)."""
    p2 = (fx.P2.replace("TARIFA FICTICIA -  10,00-", "TARIFA FICTICIA 778899  10,00-")
          .replace("PIX RECEBIDO CLIENTE TESTE - 500,00", "PIX RECEBIDO OMEGA ALIMENTOS - 500,00")
          .replace("LANCAMENTO QUALQUER XYZ - 100,00", "LANCAMENTO QUALQUER XYZ 445566 100,00"))
    p3 = fx.P3.replace("PIX ENVIADO FORNECEDOR TESTE LTDA", "PIX ENVIADO SIGMA METALURGICA")
    return fx.extrato([fx.P1, p2, p3, fx.P4])


def relatorio_casavel(sem=()):
    def linha(cod, quit, entrada, saida, doc=None, razao=None):
        return [cod, quit, quit, "Não" if entrada else "Sim", entrada, saida, entrada or saida, "Foi Pago", None, razao, doc,
                "Plano Teste", "Banco Teste", "Lançamento fictício", "00.000.000/0001-91", "10/2026"]
    linhas = {1: linha(1, "2026-10-01", None, "10,00", doc="778899"), 2: linha(2, "2026-10-01", "500,00", None, razao="OMEGA ALIMENTOS LTDA"),
              3: linha(3, "2026-10-05", None, "90,00", doc="123456"), 4: linha(4, "2026-10-07", "100,00", None, doc="445566"),
              5: linha(5, "2026-10-07", None, "200,00", razao="SIGMA METALURGICA LTDA")}
    return aux.relatorio([aux.CAB] + [v for k, v in linhas.items() if k not in sem])


class ConciliacaoNoFinanceiro(unittest.TestCase):
    def test_fin_conc_01_todos_conciliados_liberam_associacao(self):
        _, r = conferir([extrato_identificado(), relatorio_casavel()])
        cl = [m["conciliacao_financeira"]["classificacao"] for m in r["movimentos"]]
        self.assertEqual(cl, ["CONCILIADO"] * 5)
        self.assertEqual(r["bloqueio_lote"], [])
        self.assertNotIn("ASSOCIACAO_FINANCEIRA_NAO_CONFIRMADA", tipos(r))
        # conciliar não é suporte documental: situação e documentos dos movimentos não mudam
        self.assertTrue(all(m["situacao"] == "SEM_SUPORTE" and m["documentos"] == [] for m in r["movimentos"]))
        self.assertTrue(all(m["conciliacao_financeira"]["suporte_documental"] is False for m in r["movimentos"]))
        self.assertEqual(r["conciliacao_financeira"]["resumo"]["percentual_quantidade"], "100.00")

    def test_fin_conc_02_um_nao_conciliado_bloqueia_com_mensagem_agrupada(self):
        _, r = conferir([extrato_identificado(), relatorio_casavel(sem=(5,))])
        self.assertEqual(len(r["bloqueio_lote"]), 1)
        self.assertIn("1 não conciliadas", r["bloqueio_lote"][0])
        agrupadas = [p for p in r["pendencias"] if p["tipo"] == "ASSOCIACAO_FINANCEIRA_NAO_CONFIRMADA"]
        self.assertEqual(len(agrupadas), 1)                               # causa raiz agrupada, sem uma por movimento
        d = agrupadas[0]["descricao"]
        self.assertTrue(d.startswith("Problema:") and "Impacto:" in d and "O que fazer:" in d)

    def test_fin_conc_03_sem_fonte_auxiliar_bloqueia(self):
        _, r = conferir([extrato_identificado()])
        self.assertEqual(r["conciliacao_financeira"]["situacao"], "SEM_FONTE_AUXILIAR")
        self.assertIn("5 não conciliadas", r["bloqueio_lote"][0])         # risco da v1.5.0 corrigido

    def test_fin_conc_04_provavel_bloqueia(self):
        rel = aux.relatorio([aux.CAB, aux.lin(9, "Não", "500,00", None, quit="2026-10-01")])   # sem documento/contraparte compatível
        _, r = conferir([extrato_identificado(), rel])
        m = next(x for x in r["movimentos"] if x["valor"] == "500.00")
        self.assertEqual(m["conciliacao_financeira"]["classificacao"], "PROVAVEL")
        self.assertIn("prováveis", r["bloqueio_lote"][0])

    def test_fin_conc_05_legado_nao_afetado(self):
        _, r = conferir([aux.extrato()], cadastro=aux.CAD)                  # leiaute antigo: sem contrato bancário comum
        self.assertIsNone(r["conciliacao_financeira"])
        self.assertNotIn("ASSOCIACAO_FINANCEIRA_NAO_CONFIRMADA", tipos(r))
        self.assertFalse(any("associação financeira" in b for b in r["bloqueio_lote"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
