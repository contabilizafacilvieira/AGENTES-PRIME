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

    def test_fin_bank_04_nenhum_matching(self):
        _, r = conferir([fx.extrato(), aux.relatorio()])
        texto = json.dumps(r["movimentos"], ensure_ascii=False)
        self.assertNotIn("RF-", texto)                                   # nenhum movimento auxiliar ligado a um bancário
        self.assertTrue(all(m["relacao"] == [] for m in r["movimentos"]))

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
        self.assertEqual(r["bloqueio_lote"], [])
        self.assertFalse(r["aviso"].startswith("LOTE BLOQUEADO"))
        # mesmo extrato com conta NÃO cadastrada: titularidade não é presumida
        sem_conta = dict(CAD, contas={})
        _, r = conferir([fx.extrato()], cadastro=sem_conta)
        self.assertIn("CONTA_NAO_CADASTRADA", tipos(r))
        self.assertTrue(r["bloqueio_lote"][0].startswith("Nenhum extrato utilizável"))

    def test_fin_bank_12_outras_pendencias_permanecem(self):
        _, r = conferir([fx.extrato(), NAO_IDENTIFICADO])
        self.assertEqual(r["bloqueio_lote"], [])
        self.assertIn("DOCUMENTO_NAO_IDENTIFICADO", tipos(r))

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
        self.assertEqual(r["bloqueio_lote"], [])
        json.dumps(r, ensure_ascii=False)                                # resultado serializável (sem Decimal solto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
