"""Reconciliação de tentativa LEGADA (LEG-01..15). Runtime e registro 100% FICTÍCIOS em pasta temporária.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/API/testar_reconciliacao_legada.py
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import reprocessamento as rp  # noqa: E402

SOL, OUTRA = "SOL-2099-000301", "SOL-2099-000302"
MOTIVO = "Reprocessamento fictício após atualização do leitor."
T0, T1, T2 = "2099-01-10T10:00:00-03:00", "2099-01-10T10:00:05-03:00", "2099-01-11T09:00:00-03:00"
JUST = "Execução comprovada pelos resultados registrados (teste fictício)."


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Cenario:
    """Runtime fictício: tentativa legada PREPARADA, executada (financeiro-1 bloqueado + conciliacao-1)."""

    def __init__(self, bloqueio=True, sol=SOL):
        self.tmp = Path(tempfile.mkdtemp(prefix="leg-"))
        self.sol = sol
        self.pasta = self.tmp / "execucoes" / sol
        self.res("financeiro-1", {"resumo": {"movimentos": 0}, "bloqueio_lote": ["Nenhum extrato utilizável (fictício)."] if bloqueio else []})
        self.res("conciliacao-1", {"resumo": {"conferidos": 1}})
        self.tentativa({"numero": 1, "sol": sol, "tentativa_origem": 1, "criada_em": T0, "motivo": MOTIVO, "solicitante": "Supervisor",
                        "versao_codigo": "0" * 40, "tag": None, "documentos": [], "status": "PREPARADA", "pendencias": [],
                        "auditoria": {"origem": "REPROCESSAMENTO_AUDITADO"}})
        self.registro = {"sol": sol, "empresa": "EMPRESA-LEGADA-FICTICIA", "competencia": "2099-01",
                         "retomadas": [{"em": T1, "motivo": MOTIVO, "origem": "ROTA_DETERMINISTICA"}],
                         "financeiro": [{"em": T1, "resultado_sha256": sha(self.pasta / "financeiro-1" / "resultado.json")}],
                         "conciliacao": [{"em": T1, "tentativa": 1, "resultado_sha256": sha(self.pasta / "conciliacao-1" / "resultado.json")}],
                         "eventos": [{"em": T1, "evento": "FINANCEIRO: lote bloqueado (fictício)."}]}

    def res(self, nome, dados):
        (self.pasta / nome).mkdir(parents=True, exist_ok=True)
        (self.pasta / nome / "resultado.json").write_text(json.dumps(dict(dados, sol=self.sol)), encoding="utf-8")

    def tentativa(self, t, numero=1):
        p = self.pasta / "tentativas" / f"{numero:04d}" / "tentativa.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(t), encoding="utf-8")

    def arq(self, numero=1):
        return self.pasta / "tentativas" / f"{numero:04d}" / "tentativa.json"

    def avaliar(self, registro=None, numero=1):
        return rp.avaliar_legada(self.tmp, self.sol, numero, self.registro if registro is None else registro)

    def reconciliar(self, **kw):
        args = dict(justificativa=JUST, frase=rp.frase_reconciliacao(self.sol, 1), responsavel="Supervisor", raiz=RAIZ)
        args.update(kw)
        return rp.reconciliar_legada(self.tmp, self.sol, 1, self.registro, **args)

    def foto(self):
        return {p.relative_to(self.tmp).as_posix(): sha(p) for p in self.tmp.rglob("*") if p.is_file()}


class ReconciliacaoLegada(unittest.TestCase):
    def test_leg_01_legada_executada_e_bloqueada_e_elegivel(self):
        c = Cenario()
        av = c.avaliar()
        self.assertTrue(av["elegivel"], av["motivos"])
        self.assertEqual((av["estado_derivado"], sorted(e["execucao"] for e in av["execucoes"])), ("BLOQUEADA", ["conciliacao-1", "financeiro-1"]))
        self.assertIsNone(rp.ativa(c.tmp, SOL) and None)

    def test_leg_02_nao_executada_nao_e_reconciliada(self):
        c = Cenario()
        sem_retomada = dict(c.registro, retomadas=[])
        self.assertEqual(c.avaliar(sem_retomada)["codigo"], "SEM_EVIDENCIA_DE_EXECUCAO")
        sem_execucao = dict(c.registro, financeiro=[], conciliacao=[])
        self.assertEqual(c.avaliar(sem_execucao)["codigo"], "SEM_EVIDENCIA_DE_EXECUCAO")
        with self.assertRaises(ValueError):
            rp.reconciliar_legada(c.tmp, SOL, 1, sem_retomada, justificativa=JUST, frase=rp.frase_reconciliacao(SOL, 1))
        self.assertEqual(json.loads(c.arq().read_text())["status"], "PREPARADA")

    def test_leg_03_tentativa_v2_nao_aceita(self):
        c = Cenario()
        t = json.loads(c.arq().read_text())
        c.tentativa(dict(t, ciclo_vida="V2"))
        self.assertEqual(c.avaliar()["codigo"], "NAO_LEGADA")

    def test_leg_04_evidencia_insuficiente_fail_closed(self):
        c = Cenario()
        sem_hash = copy.deepcopy(c.registro)
        del sem_hash["financeiro"][0]["resultado_sha256"]
        self.assertEqual(c.avaliar(sem_hash)["codigo"], "EVIDENCIA_INSUFICIENTE")
        hash_errado = copy.deepcopy(c.registro)
        hash_errado["financeiro"][0]["resultado_sha256"] = "f" * 64
        self.assertEqual(c.avaliar(hash_errado)["codigo"], "EVIDENCIA_INSUFICIENTE")
        anterior = dict(c.registro, retomadas=[{"em": "2099-01-09T10:00:00-03:00", "motivo": MOTIVO}])
        self.assertEqual(c.avaliar(anterior)["codigo"], "EVIDENCIA_INSUFICIENTE")       # retomada antes da tentativa

    def test_leg_05_execucoes_conflitantes_fail_closed(self):
        c = Cenario()
        duas = dict(c.registro, retomadas=c.registro["retomadas"] + [{"em": T2, "motivo": MOTIVO}])
        self.assertEqual(c.avaliar(duas)["codigo"], "EVIDENCIA_CONFLITANTE")
        outra_tentativa = copy.deepcopy(c.registro)
        outra_tentativa["conciliacao"][0]["tentativa"] = 7
        self.assertEqual(c.avaliar(outra_tentativa)["codigo"], "EVIDENCIA_CONFLITANTE")
        com_falha = dict(c.registro, eventos=[{"em": T1, "evento": "Falha na etapa FINANCEIRO: erro fictício"}])
        self.assertEqual(c.avaliar(com_falha)["codigo"], "EVIDENCIA_CONFLITANTE")
        c.tentativa({"numero": 2, "sol": SOL, "ciclo_vida": "V2", "status": "CONCLUIDA", "motivo": "x",
                     "execucoes": [{"execucao": "financeiro-1"}]}, numero=2)
        self.assertEqual(c.avaliar()["codigo"], "EVIDENCIA_CONFLITANTE")      # pasta já vinculada a outra tentativa

    def test_leg_06_estado_final_derivado_das_evidencias(self):
        self.assertEqual(Cenario(bloqueio=True).avaliar()["estado_derivado"], "BLOQUEADA")
        self.assertEqual(Cenario(bloqueio=False).avaliar()["estado_derivado"], "CONCLUIDA")    # nada fixo em BLOQUEADA
        c = Cenario(bloqueio=False)
        self.assertEqual(c.reconciliar()["tentativa"]["status"], "CONCLUIDA")

    def test_leg_07_historico_preservado(self):
        c = Cenario()
        original = c.arq().read_bytes()
        c.reconciliar()
        camada = json.loads((c.arq().parent / "reconciliacao-legada.json").read_text())
        self.assertEqual(camada["tentativa_original"], json.loads(original))
        self.assertEqual(camada["tentativa_original_sha256"], hashlib.sha256(original).hexdigest())
        t = json.loads(c.arq().read_text())
        self.assertEqual({k: t[k] for k in ("numero", "criada_em", "motivo", "versao_codigo", "documentos")},
                         {k: json.loads(original)[k] for k in ("numero", "criada_em", "motivo", "versao_codigo", "documentos")})
        self.assertNotIn("ciclo_vida", t)                                  # não finge ter sido do ciclo V2

    def test_leg_08_evento_auditavel(self):
        c = Cenario()
        c.reconciliar()
        camada = json.loads((c.arq().parent / "reconciliacao-legada.json").read_text())
        for k in ("origem", "sol", "empresa", "competencia", "tentativa", "estado_legado_anterior", "estado_reconciliado", "execucoes_vinculadas",
                  "motivo_tentativa", "justificativa", "responsavel", "em", "versao_codigo", "evidencias"):
            self.assertIn(k, camada)
        self.assertEqual((camada["origem"], camada["estado_legado_anterior"], camada["estado_reconciliado"], camada["empresa"]),
                         ("RECONCILIACAO_LEGADA", "PREPARADA", "BLOQUEADA", "EMPRESA-LEGADA-FICTICIA"))
        t = json.loads(c.arq().read_text())
        self.assertTrue(any("Reconciliação legada" in e["evento"] for e in t["eventos"]))
        self.assertEqual(t["reconciliacao_legada"]["arquivo_sha256"], sha(c.arq().parent / "reconciliacao-legada.json"))

    def test_leg_09_justificativa_obrigatoria(self):
        c = Cenario()
        for j in ("", "curta", None, "   "):
            with self.assertRaises(ValueError):
                c.reconciliar(justificativa=j)
        self.assertFalse((c.arq().parent / "reconciliacao-legada.json").exists())

    def test_leg_10_frase_obrigatoria(self):
        c = Cenario()
        for f in ("", "RECONCILIAR TENTATIVA 0001", f"RECONCILIAR TENTATIVA 0002 {SOL}", rp.frase_reconciliacao(SOL, 1).lower()):
            with self.assertRaises(ValueError):
                c.reconciliar(frase=f)
        self.assertEqual(json.loads(c.arq().read_text())["status"], "PREPARADA")

    def test_leg_11_repeticao_nao_duplica(self):
        c = Cenario()
        c.reconciliar()
        antes = c.foto()
        r = c.reconciliar()
        self.assertEqual(r["resultado"], "JA_RECONCILIADA")
        self.assertEqual(c.foto(), antes)
        self.assertEqual(c.avaliar()["codigo"], "JA_RECONCILIADA")

    def test_leg_12_nao_cria_execucao(self):
        c = Cenario()
        pastas = sorted(p.name for p in c.pasta.iterdir())
        c.reconciliar()
        self.assertEqual(sorted(p.name for p in c.pasta.iterdir()), pastas)
        self.assertIsNone(rp.ativa(c.tmp, SOL))                           # deixa de impedir nova tentativa

    def test_leg_13_resultados_intactos(self):
        c = Cenario()
        antes = {k: v for k, v in c.foto().items() if "/tentativas/" not in k}
        c.reconciliar()
        self.assertEqual({k: v for k, v in c.foto().items() if "/tentativas/" not in k}, antes)

    def test_leg_14_nenhum_lancamento(self):
        c = Cenario()
        antes = set(c.foto())
        c.reconciliar()
        novos = set(c.foto()) - antes
        self.assertEqual({Path(n).name for n in novos}, {"reconciliacao-legada.json"})
        self.assertFalse(any("bancos" in n or "lancament" in n or "exportacao" in n for n in c.foto()))

    def test_leg_15_isolamento(self):
        c = Cenario()
        self.assertEqual(rp.avaliar_legada(c.tmp, OUTRA, 1, dict(c.registro, sol=OUTRA))["codigo"], "TENTATIVA_INEXISTENTE")
        self.assertEqual(c.avaliar(dict(c.registro, sol=OUTRA))["codigo"], "SOL_INEXISTENTE")   # registro de outra SOL
        d = Cenario(sol=OUTRA)                                             # evidências de outra SOL não servem
        self.assertEqual(c.avaliar(dict(d.registro, sol=SOL))["codigo"], "EVIDENCIA_INSUFICIENTE")
        c.reconciliar()
        camada = json.loads((c.arq().parent / "reconciliacao-legada.json").read_text())
        self.assertEqual((camada["sol"], camada["empresa"], camada["competencia"]), (SOL, "EMPRESA-LEGADA-FICTICIA", "2099-01"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
