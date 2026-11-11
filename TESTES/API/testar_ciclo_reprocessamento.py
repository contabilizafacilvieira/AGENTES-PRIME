"""Ciclo de vida da tentativa auditada de reprocessamento (REPROC-LIFE-01..12). Somente dados FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/API/testar_ciclo_reprocessamento.py
Runtime temporário; registro do Coordenador e execução das etapas simulados (as pastas de etapa são criadas pela função
oficial servidor.nova_execucao). Não lê CLIENTES/, runtime operacional nem SOL real.
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import reprocessamento
import servidor

SOL = "SOL-2099-000001"


def gravar(caminho: Path, dados: dict):
    caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


class CicloReprocessamento(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="prime-ciclo-"))
        (self.base / "execucoes" / SOL).mkdir(parents=True)
        doc = self.base / "documento-ficticio.txt"
        doc.write_text("DADO FICTÍCIO\n", encoding="utf-8")
        self.docs = [{"nome": doc.name, "caminho": str(doc), "sha256": reprocessamento.sha256(doc)}]
        self.estado = {"estado": "AGUARDANDO_SUPERVISOR"}
        self.plano = []
        self.patches = [patch.object(servidor, "RUNTIME", self.base),
                        patch.object(servidor.coordenador, "ler_registro", lambda: {"solicitacoes": {SOL: dict(self.estado)}}),
                        patch.object(servidor.coordenador, "plano_de", lambda s: list(self.plano))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def criar(self, motivo="Reprocessamento fictício"):
        origem = (reprocessamento.listar(self.base, SOL) or [{"numero": 1}])[-1]
        return reprocessamento.criar(self.base, SOL, origem=origem, motivo=motivo, solicitante="Supervisor",
                                     documentos=self.docs, raiz=RAIZ)

    def executar(self, etapas):
        """Roda o caminho oficial iniciar_execucao com etapas simuladas e espera o término da thread."""
        vistos = {}

        def pendentes(sol):
            lista = reprocessamento.listar(self.base, sol)
            vistos["status_durante"] = lista[-1]["status"] if lista else None
            for etapa in etapas:
                etapa(sol)
        with patch.object(servidor, "executar_pendentes", pendentes):
            self.assertTrue(servidor.iniciar_execucao(SOL))
            for _ in range(500):
                if servidor.EM_EXECUCAO["sol"] is None:
                    break
                time.sleep(0.01)
        self.assertIsNone(servidor.EM_EXECUCAO["sol"])
        return vistos

    @staticmethod
    def financeiro(bloqueio=None):
        def etapa(sol):
            pasta = servidor.nova_execucao(sol, "financeiro")
            gravar(pasta / "resultado.json", {"resumo": {"movimentos": 0, "pendencias": 1}, "bloqueio_lote": bloqueio or [],
                                              "fonte_bancaria": {"extratos_utilizaveis": 0},
                                              "fonte_auxiliar_financeira": {"resumo": {"movimentos": 3}}})
        return etapa

    @staticmethod
    def conciliacao(sol):
        pasta = servidor.nova_execucao(sol, "conciliacao")
        gravar(pasta / "resultado.json", {"resumo": {"conferido": 1, "pendente": 2}})

    def ultima(self):
        return reprocessamento.listar(self.base, SOL)[-1]

    # ------------------------------------------------------------------
    def test_life_01_reprocessar_cria_preparada(self):
        t = self.criar()
        self.assertEqual((t["status"], t["ciclo_vida"], t["execucoes"]), ("PREPARADA", "V2", []))
        self.assertEqual(t["eventos"][0]["evento"], "Tentativa criada (PREPARADA).")

    def test_life_02_inicio_oficial_em_execucao(self):
        self.criar()
        vistos = self.executar([self.financeiro()])
        self.assertEqual(vistos["status_durante"], "EM_EXECUCAO")
        self.assertTrue(self.ultima()["iniciada_em"])

    def test_life_03_sucesso_concluida(self):
        self.criar()
        self.plano = [{"etapa": "FINANCEIRO", "situacao": "CONCLUIDA"}, {"etapa": "CONCILIACAO", "situacao": "CONCLUIDA"}]
        self.executar([self.financeiro(), self.conciliacao])
        t = self.ultima()
        self.assertEqual((t["status"], t["resultado"]["bloqueio_lote"]), ("CONCLUIDA", []))
        self.assertNotIn("erro", t)

    def test_life_04_bloqueio_funcional_bloqueada(self):
        self.criar()
        self.estado = {"estado": "AGUARDANDO_SUPERVISOR"}
        self.plano = [{"etapa": "FINANCEIRO", "situacao": "BLOQUEADA"}, {"etapa": "BANCOS", "situacao": "BLOQUEADA_POR_DEPENDENCIA"},
                      {"etapa": "CONCILIACAO", "situacao": "CONCLUIDA"}]
        self.executar([self.financeiro(["Nenhum extrato utilizável (fictício)."]), self.conciliacao])
        t = self.ultima()
        self.assertEqual(t["status"], "BLOQUEADA")                 # bloqueio funcional NÃO é falha técnica
        self.assertNotIn("erro", t)
        self.assertEqual(t["estado_sol_final"], "AGUARDANDO_SUPERVISOR")

    def test_life_05_erro_tecnico_falhou(self):
        self.criar()

        def quebra(sol):
            servidor.nova_execucao(sol, "financeiro")
            raise RuntimeError("detalhe interno que não deve aparecer")
        self.executar([quebra])
        t = self.ultima()
        self.assertEqual(t["status"], "FALHOU")
        self.assertEqual(t["erro"]["tipo"], "RuntimeError")
        self.assertNotIn("detalhe interno", json.dumps(t, ensure_ascii=False))   # sem detalhe/rastreamento interno
        # etapa que termina sem resultado também é falha técnica
        self.criar("Segunda tentativa fictícia")
        self.executar([lambda sol: servidor.nova_execucao(sol, "financeiro")])
        self.assertEqual(self.ultima()["status"], "FALHOU")

    def test_life_06_execucoes_vinculadas_explicitamente(self):
        (self.base / "execucoes" / SOL / "financeiro-1").mkdir()      # execução antiga, de antes da tentativa
        self.criar()
        self.executar([self.financeiro(), self.conciliacao])
        t = self.ultima()
        self.assertEqual([(e["execucao"], e["etapa"]) for e in t["execucoes"]], [("financeiro-2", "financeiro"), ("conciliacao-1", "conciliacao")])
        self.assertTrue(all(e["vinculada_em"] for e in t["execucoes"]))
        self.assertNotIn("financeiro-1", json.dumps(t["execucoes"]))   # nada inferido pela ordem das pastas

    def test_life_07_resumo_e_bloqueio_registrados(self):
        self.criar()
        self.plano = [{"etapa": "FINANCEIRO", "situacao": "BLOQUEADA"}]
        self.executar([self.financeiro(["Bloqueio fictício."]), self.conciliacao])
        r = self.ultima()["resultado"]
        fin, conc = r["execucoes"]
        self.assertEqual((fin["resultado"], len(fin["resultado_sha256"])), ("financeiro-1/resultado.json", 64))
        self.assertEqual((fin["resumo"]["pendencias"], fin["fonte_auxiliar_resumo"]["movimentos"]), (1, 3))
        self.assertEqual(conc["resumo"], {"conferido": 1, "pendente": 2})
        self.assertEqual((r["bloqueio_lote"], r["motivo_bloqueio"]), (["Bloqueio fictício."], "Bloqueio fictício."))
        self.assertEqual(r["plano"], [{"etapa": "FINANCEIRO", "situacao": "BLOQUEADA"}])
        t = self.ultima()
        for campo in ("numero", "sol", "motivo", "solicitante", "auditoria", "tag", "versao_codigo", "criada_em", "iniciada_em",
                      "finalizada_em", "documentos", "estado_sol_final"):
            self.assertIn(campo, t)

    def test_life_08_finalizada_nao_impede_nova(self):
        self.criar()
        self.executar([self.financeiro(["Bloqueio fictício."])])
        self.assertIsNone(reprocessamento.ativa(self.base, SOL))
        self.assertEqual(self.criar("Nova tentativa fictícia")["numero"], 2)

    def test_life_09_ativa_impede_concorrencia(self):
        self.criar()
        self.assertEqual(reprocessamento.ativa(self.base, SOL)["status"], "PREPARADA")
        reprocessamento.iniciar(self.base, SOL)
        self.assertEqual(reprocessamento.ativa(self.base, SOL)["status"], "EM_EXECUCAO")
        servidor.EM_EXECUCAO["sol"] = SOL                                 # execução em curso: segunda é recusada
        try:
            self.assertFalse(servidor.iniciar_execucao(SOL))
        finally:
            servidor.EM_EXECUCAO["sol"] = None

    def test_life_10_segunda_finalizacao_idempotente(self):
        t = self.criar()
        self.executar([self.financeiro(["Bloqueio fictício."])])
        arquivo = self.base / "execucoes" / SOL / "tentativas" / "0001" / "tentativa.json"
        antes = arquivo.read_bytes()
        repetida = servidor.finalizar_tentativa(SOL, t)
        self.assertTrue(repetida["finalizacao_repetida"])
        direta = reprocessamento.finalizar(self.base, SOL, 1, "CONCLUIDA", resultado={}, estado_sol="X")
        self.assertEqual((direta["status"], direta["finalizacao_repetida"]), ("BLOQUEADA", True))
        self.assertEqual(arquivo.read_bytes(), antes)                    # nada reescrito (eventos, horários, resultado)
        self.assertEqual(sorted(p.name for p in (self.base / "execucoes" / SOL).iterdir()), ["financeiro-1", "tentativas"])
        with self.assertRaises(ValueError):
            reprocessamento.finalizar(self.base, SOL, 1, "EM_EXECUCAO", resultado={}, estado_sol=None)

    def test_life_11_anterior_nunca_sobrescrita(self):
        self.criar()
        self.executar([self.financeiro(["Bloqueio fictício."])])
        arquivo1 = self.base / "execucoes" / SOL / "tentativas" / "0001" / "tentativa.json"
        antes = arquivo1.read_bytes()
        self.criar("Segunda tentativa fictícia")
        self.executar([self.financeiro(), self.conciliacao])
        self.assertEqual(arquivo1.read_bytes(), antes)
        t1, t2 = reprocessamento.listar(self.base, SOL)
        self.assertEqual([e["execucao"] for e in t1["execucoes"]], ["financeiro-1"])
        self.assertEqual([e["execucao"] for e in t2["execucoes"]], ["financeiro-2", "conciliacao-1"])
        # tentativa ANTIGA (sem ciclo de vida) nunca é assumida automaticamente por uma execução nova
        legado = {"numero": 3, "sol": SOL, "status": "PREPARADA", "motivo": "legado fictício", "documentos": self.docs}
        reprocessamento.gravar(self.base / "execucoes" / SOL / "tentativas" / "0003" / "tentativa.json", legado)
        self.executar([self.financeiro()])
        self.assertEqual(self.ultima(), legado)

    def test_life_13_execucao_normal_sem_tentativa(self):
        # compatibilidade: execução comum (sem reprocessamento) não exige nem cria tentativa e não falha por isso
        self.executar([self.financeiro(["Bloqueio fictício."]), self.conciliacao])
        pasta = self.base / "execucoes" / SOL
        self.assertEqual(sorted(p.name for p in pasta.iterdir()), ["conciliacao-1", "financeiro-1"])
        self.assertTrue((pasta / "financeiro-1" / "resultado.json").is_file())
        self.assertFalse((pasta / "tentativas").exists())
        self.assertEqual(reprocessamento.listar(self.base, SOL), [])
        self.assertIsNone(reprocessamento.vincular_execucao(self.base, SOL, "financeiro-1"))

    def test_life_14_execucao_normal_nao_se_vincula_a_tentativa_finalizada(self):
        self.criar()
        self.executar([self.financeiro(["Bloqueio fictício."])])
        arquivo = self.base / "execucoes" / SOL / "tentativas" / "0001" / "tentativa.json"
        antes = arquivo.read_bytes()
        self.executar([self.financeiro(), self.conciliacao])              # execução comum posterior
        self.assertEqual(arquivo.read_bytes(), antes)                      # nenhum vínculo artificial
        self.assertTrue((self.base / "execucoes" / SOL / "financeiro-2" / "resultado.json").is_file())

    def test_life_12_documentos_e_sha_vinculados(self):
        self.criar()
        self.executar([self.financeiro(["Bloqueio fictício."])])
        t = self.ultima()
        self.assertEqual(t["documentos"], self.docs)
        self.assertEqual(reprocessamento.sha256(Path(t["documentos"][0]["caminho"])), self.docs[0]["sha256"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
