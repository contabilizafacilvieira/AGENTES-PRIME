"""Preparação técnica: somente fixtures fictícias, sem runtime ou documentos reais."""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import adaptadores_fechamento as af  # noqa: E402
import aprendizado_contabil as ac  # noqa: E402
import base_abertura as ba  # noqa: E402
import estado_dp as dp  # noqa: E402


def linhas_razao():
    return [["Data", "Número", "Histórico", "Cta.C.Part.", "Débito", "Crédito", "Saldo"],
            ["Conta:", 539, "1.1.10.200.0005", "BANCO SANTANDER"],
            ["2026-08-01", 1, "PIX TESTE", "100", "10,00", "0,00", "10,00"],
            ["Conta:", 10000, "1.1.20.100.0001", "CLIENTES"],
            ["2026-08-02", 2, "CLIENTE TESTE", "200", "0,00", "5,00", "-5,00"]]


class Preparacao(unittest.TestCase):
    def test_razao_secoes_preserva_conta_e_contrapartida(self):
        extraido = {"leitura": "EXTRAIDO_PLANILHA", "conteudo": {"abas": [{"oculta": False,
            "linhas": [{"valores": x} for x in linhas_razao()]}]}}
        r, erro = af.adapter_razao({"arquivo": "fixture.xls"}, extraido, None, "EMP")
        self.assertIsNone(erro); self.assertEqual(r["adapter"], "RAZAO_SECOES_CONTA_V1")
        self.assertEqual([x["conta"] for x in r["lancamentos"]], ["1.1.10.200.0005", "1.1.20.100.0001"])
        self.assertEqual(r["lancamentos"][0]["contrapartida"], "100")

    def test_razao_linha_invalida_fail_closed(self):
        linhas = linhas_razao()[:2] + [["não é lançamento"]]
        extraido = {"leitura": "EXTRAIDO_PLANILHA", "conteudo": {"abas": [{"oculta": False,
            "linhas": [{"valores": x} for x in linhas]}]}}
        r, erro = af.adapter_razao({"arquivo": "fixture.xls"}, extraido, None, "EMP")
        self.assertIsNone(r); self.assertIn("Nenhum lançamento", erro)

    def test_base_sem_composicao_e_sem_conta(self):
        b = {"contas": [{"classificacao": "1.1", "descricao": "CAIXA", "tipo": "ANALITICA", "saldo_atual": "100.00"}]}
        c = {"composicoes": [{"identificador": {"classificacao": "9.9"}, "saldo_composicao": "2.00"}]}
        r = ba.construir(b, c, empresa="EMP", competencia_base="2026-08", data_base="2026-08-31")
        self.assertEqual({x["status_composicao"] for x in r["itens"]}, {"SEM_COMPOSICAO", "COMPOSICAO_SEM_CONTA"})

    def test_base_divergencia_nao_corrige(self):
        b = {"contas": [{"classificacao": "1.1", "tipo": "ANALITICA", "saldo_atual": "100.00"}]}
        c = {"composicoes": [{"conta": {"classificacao": "1.1"}, "saldo_composicao": "90.00", "diferenca": "10.00"}]}
        r = ba.construir(b, c, empresa="EMP", competencia_base="2026-08", data_base="2026-08-31")
        self.assertEqual(r["itens"][0]["status_composicao"], "DIVERGENTE")
        self.assertEqual(r["itens"][0]["saldo_contabil"], "100.00")

    def test_aprendizado_fica_aguardando_supervisor(self):
        r = ac.sugerir([{"conta_debito": "510", "conta_credito": "10001", "historico": "X", "competencia": "2026-07",
                         "proveniencia": {"linha": 1}}, {"conta_debito": "510", "conta_credito": "10001", "historico": "X", "competencia": "2026-08",
                         "proveniencia": {"linha": 2}}], empresa="BRASIL-PROTEC-AGRO")
        self.assertFalse(r["regra_registrada"]); self.assertEqual(r["sugestoes"][0]["status"], "AGUARDANDO_SUPERVISOR")
        self.assertEqual(r["sugestoes"][0]["confianca"], "MEDIA")

    def test_dp_nao_aplicavel_sem_pendencia(self):
        r = dp.nao_aplicavel("BRASIL-PROTEC-AGRO", "2026-09", justificativa="Supervisor confirmou inexistência de folha e encargos.")
        self.assertEqual(r["status"], "NAO_APLICAVEL"); self.assertEqual(r["pendencias"], [])

    def test_dp_conflito_futuro(self):
        r = dp.nao_aplicavel("EMP", "2026-09", justificativa="Sem folha nesta competência.")
        c = dp.conflito(r, ["DOC-DP-1"])
        self.assertEqual(c["status"], "AGUARDANDO_SUPERVISOR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
