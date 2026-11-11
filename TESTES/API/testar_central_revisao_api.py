"""API da Central de Revisão do Supervisor (CR-API-01..20). Ambiente ISOLADO, dados 100% FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/API/testar_central_revisao_api.py
Runtime, registro, CLIENTES, LIBERADOS e a pasta da demonstração são temporários. Duas SOLs fictícias recebem um resultado do
Financeiro gerado pelo código real com o extrato/relatório fictícios das baterias do Financeiro.
"""
import copy
import hashlib
import http.client
import json
import os
import re
import sys
import threading
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado  # noqa: E402
AMB = ambiente_isolado.criar("prime-central-api-")
DEMO = AMB.raiz / "demonstracao-conciliacao"
os.environ["AGENTES_PRIME_DEMO_CONCILIACAO"] = str(DEMO)
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(RAIZ / "TESTES" / "FINANCEIRO"))
import servidor  # noqa: E402
import testar_decisoes_supervisor as sup  # noqa: E402

SOL_A, SOL_B, SOL_SEM = "SOL-2099-000101", "SOL-2099-000102", "SOL-2099-000103"
BASE_DEMO = "/api/demonstracao/conciliacao-financeira"
JUST = "Conferi data, valor e favorecido no comprovante fictício."


def preparar_sols():
    registro = {"solicitacoes": {}}
    resultado = sup.conferir_com()
    for sol in (SOL_A, SOL_B, SOL_SEM):
        registro["solicitacoes"][sol] = {"sol": sol, "empresa": sup.CTX_FIN["empresa"], "competencia": sup.CTX_FIN["competencia"],
                                         "estado": "AGUARDANDO_SUPERVISOR", "fluxo": "FINANCEIRO_BANCOS", "eventos": [], "motivos": []}
        pasta = AMB.runtime / "execucoes" / sol / "financeiro-1"
        pasta.mkdir(parents=True)
        r = copy.deepcopy(resultado)
        if sol == SOL_SEM:
            r["conciliacao_financeira"] = None
        (pasta / "resultado.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    AMB.registro.write_text(json.dumps(registro, ensure_ascii=False), encoding="utf-8")


class CentralAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        preparar_sols()
        cls.srv = servidor.iniciar(0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.porta = cls.srv.server_port
        status, _, corpo = cls.http("GET", "/", token=False)
        cls.token = re.search(r'name="prime-sessao" content="([^"]+)"', corpo.decode()).group(1)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    @classmethod
    def http(cls, metodo, rota, corpo=None, token=True, cab=None):
        c = http.client.HTTPConnection("127.0.0.1", cls.porta, timeout=30)
        h = {"Host": f"127.0.0.1:{cls.porta}"}
        if token:
            h["X-Prime-Sessao"] = cls.token
        if corpo is not None:
            h["Content-Type"] = "application/json"
        h.update(cab or {})
        c.request(metodo, rota, body=None if corpo is None else json.dumps(corpo), headers=h)
        r = c.getresponse()
        dados = r.read()
        c.close()
        return r.status, dict(r.getheaders()), dados

    def j(self, metodo, rota, corpo=None, **kw):
        s, _, d = self.http(metodo, rota, corpo, **kw)
        return s, (json.loads(d) if d else {})

    def setUp(self):
        self.j("POST", BASE_DEMO + "/reiniciar", {"confirmado": True})

    def visao(self, base=BASE_DEMO):
        s, v = self.j("GET", base)
        self.assertEqual(s, 200)
        return v

    def item(self, v, status):
        return [i for i in v["itens"] if i["status"] == status]

    def decidir(self, v, assoc, decisao="APROVADO", base=BASE_DEMO, **extra):
        return self.j("POST", f"{base}/{assoc}/decisao", dict({"decisao": decisao, "justificativa": JUST, "revisao_conciliacao": v["revisao_conciliacao"],
                                                               "revisao_decisoes": v["revisao_decisoes"]}, **extra))

    # ------------------------------------------------------------------------------------------------ demonstração
    def test_cr_api_01_visao_demonstracao(self):
        v = self.visao()
        r = v["resumo"]
        self.assertTrue(v["demonstracao"])
        self.assertEqual(v["rotulo"], "DEMONSTRAÇÃO — Conciliação Financeira")
        self.assertEqual((r["conciliados_automaticamente"], r["para_revisar"], r["ambiguos"], r["nao_conciliados"], r["bloqueios_restantes"]),
                         (4, 7, 2, 1, 10))
        self.assertTrue(v["pendencia_bloqueio"]["problema"] and v["pendencia_bloqueio"]["impacto"] and v["pendencia_bloqueio"]["o_que_fazer"])

    def test_cr_api_02_seguranca(self):
        self.assertEqual(self.http("GET", BASE_DEMO, token=False)[0], 401)
        self.assertEqual(self.http("GET", BASE_DEMO, cab={"Host": "evil.example:80"})[0], 403)
        self.assertEqual(self.http("GET", BASE_DEMO, cab={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.http("GET", BASE_DEMO, cab={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.http("GET", BASE_DEMO, cab={"X-Prime-Sessao": "x" * 43})[0], 401)

    def test_cr_api_03_detalhe(self):
        v = self.visao()
        p = self.item(v, "REVISAR")[0]
        s, d = self.j("GET", f"{BASE_DEMO}/{p['id']}")
        self.assertEqual(s, 200)
        self.assertTrue(d["acoes"]["confirmar"] and d["acoes"]["rejeitar"] and not d["acoes"]["escolher_candidato"])
        self.assertTrue(any(x["ok"] for x in d["explicacao"]) and d["pendencia"]["o_que_fazer"])
        c = self.item(v, "CONCILIADO")[0]
        s, d = self.j("GET", f"{BASE_DEMO}/{c['id']}")
        self.assertFalse(any(d["acoes"].values()))                         # conciliado: nenhum botão de aprovação
        self.assertEqual(self.j("GET", f"{BASE_DEMO}/CF-000000000000")[0], 404)

    def test_cr_api_04_confirmar_atualiza_cards(self):
        v = self.visao()
        s, r = self.decidir(v, self.item(v, "REVISAR")[0]["id"])
        self.assertEqual(s, 201, r)
        self.assertEqual((r["visao"]["resumo"]["para_revisar"], r["visao"]["resumo"]["bloqueios_restantes"]), (6, 9))
        self.assertIn("não é aprovação fiscal nem contábil", r["mensagem"])

    def test_cr_api_05_estado_obsoleto(self):
        v = self.visao()
        prov = self.item(v, "REVISAR")
        self.assertEqual(self.decidir(v, prov[0]["id"])[0], 201)
        s, r = self.decidir(v, prov[1]["id"])                               # mesma revisão antiga
        self.assertEqual((s, r["codigo"]), (409, "ESTADO_OBSOLETO"))
        self.assertEqual(self.visao()["resumo"]["para_revisar"], 6)

    def test_cr_api_06_lote(self):
        v = self.visao()
        prov = [i["id"] for i in self.item(v, "REVISAR")]
        amb = self.item(v, "AMBIGUO")[0]["id"]
        corpo = {"associacoes": prov + [amb], "justificativa": JUST, "revisao_conciliacao": v["revisao_conciliacao"], "revisao_decisoes": v["revisao_decisoes"]}
        s, r = self.j("POST", BASE_DEMO + "/decisoes-lote", corpo)
        self.assertEqual((s, r["codigo"]), (409, "LOTE_SO_PROVAVEIS"))
        self.assertEqual(self.visao()["resumo"]["para_revisar"], 7)        # nada gravado
        corpo["associacoes"] = prov
        s, r = self.j("POST", BASE_DEMO + "/decisoes-lote", corpo)
        self.assertEqual(s, 201, r)
        self.assertEqual((r["registradas"], r["visao"]["resumo"]["para_revisar"], r["visao"]["resumo"]["bloqueios_restantes"]), (7, 0, 3))

    def test_cr_api_07_ambiguo_candidato(self):
        v = self.visao()
        a = self.item(v, "AMBIGUO")[0]["id"]
        s, d = self.j("GET", f"{BASE_DEMO}/{a}")
        self.assertTrue(d["acoes"]["escolher_candidato"] and not d["acoes"]["confirmar"])
        s, r = self.decidir(v, a)                                          # sem candidato
        self.assertEqual((s, r["codigo"]), (409, "CANDIDATO_OBRIGATORIO"))
        c1, c2 = d["candidatos"]
        s, r = self.decidir(v, a, candidato={"bancarios": c1["bancarios"], "auxiliares": c1["auxiliares"]})
        self.assertEqual(s, 201, r)
        s, r = self.decidir(r["visao"], a, candidato={"bancarios": c2["bancarios"], "auxiliares": c2["auxiliares"]})
        self.assertEqual((s, r["codigo"]), (409, "JA_DECIDIDA"))
        s, d = self.j("GET", f"{BASE_DEMO}/{a}")
        self.assertEqual([c["escolhido"] for c in d["candidatos"]], [True, False])

    def test_cr_api_08_historico_agrupado(self):
        v = self.visao()
        prov = [i["id"] for i in self.item(v, "REVISAR")][:3]
        s, r = self.j("POST", BASE_DEMO + "/decisoes-lote", {"associacoes": prov, "justificativa": JUST, "revisao_conciliacao": v["revisao_conciliacao"],
                                                             "revisao_decisoes": v["revisao_decisoes"]})
        s, r = self.decidir(r["visao"], self.item(r["visao"], "REVISAR")[0]["id"], "REJEITADO")
        s, h = self.j("GET", BASE_DEMO + "/historico")
        self.assertEqual((h["total_eventos"], len(h["grupos"])), (4, 2))
        self.assertEqual((h["grupos"][0]["acao"], h["grupos"][1]["acao"], h["grupos"][1]["quantidade"]),
                         ("Rejeitou associação", "Confirmou associação em lote", 3))
        self.assertEqual(len(h["grupos"][1]["itens"]), 3)                  # cada decisão do lote auditável

    def test_cr_api_09_entradas_invalidas(self):
        v = self.visao()
        a = self.item(v, "REVISAR")[0]["id"]
        base = {"decisao": "APROVADO", "justificativa": JUST, "revisao_conciliacao": v["revisao_conciliacao"], "revisao_decisoes": v["revisao_decisoes"]}
        self.assertEqual(self.j("POST", f"{BASE_DEMO}/{a}/decisao", dict(base, caminho="/etc/passwd"))[0], 400)
        self.assertEqual(self.j("POST", f"{BASE_DEMO}/{a}/decisao", {k: v_ for k, v_ in base.items() if k != "justificativa"})[0], 400)
        s, r = self.j("POST", f"{BASE_DEMO}/{a}/decisao", dict(base, justificativa="ok"))
        self.assertEqual((s, r["codigo"]), (409, "JUSTIFICATIVA_OBRIGATORIA"))
        for rota in (f"{BASE_DEMO}/cf-abc/decisao", f"{BASE_DEMO}/../../execucoes", "/api/demonstracao/outra", f"{BASE_DEMO}/{a}/apagar"):
            self.assertIn(self.j("POST", rota, base)[0], (400, 404))
        self.assertEqual(self.j("DELETE", BASE_DEMO)[0], 405)
        self.assertEqual(self.visao()["resumo"]["para_revisar"], 7)

    def test_cr_api_10_reiniciar_demonstracao(self):
        v = self.visao()
        self.decidir(v, self.item(v, "REVISAR")[0]["id"])
        self.assertEqual(self.j("POST", BASE_DEMO + "/reiniciar", {"confirmado": False})[0], 400)
        self.assertTrue((DEMO / "decisoes.json").is_file())
        s, r = self.j("POST", BASE_DEMO + "/reiniciar", {"confirmado": True})
        self.assertEqual((s, r["visao"]["resumo"]["para_revisar"]), (200, 7))
        self.assertFalse(DEMO.exists())

    def test_cr_api_11_demonstracao_fora_do_runtime(self):
        v = self.visao()
        self.decidir(v, self.item(v, "REVISAR")[0]["id"])
        self.assertEqual(sorted(p.name for p in DEMO.iterdir()), ["decisoes.json"])
        self.assertNotIn(servidor.RUNTIME, servidor.pasta_demonstracao().parents)
        self.assertFalse(any("demonstracao" in p.name.lower() for p in servidor.RUNTIME.rglob("*")))
        self.assertNotIn("DEMONSTRACAO", json.dumps(ambiente_isolado.registro_isolado()))

    # ------------------------------------------------------------------------------------------------ SOL (fictícia)
    def test_cr_api_12_sol_decisao_em_camada_separada(self):
        base = f"/api/solicitacoes/{SOL_A}/conciliacao-financeira"
        res = AMB.runtime / "execucoes" / SOL_A / "financeiro-1" / "resultado.json"
        antes = hashlib.sha256(res.read_bytes()).hexdigest()
        v = self.visao(base)
        self.assertFalse(v["demonstracao"])
        self.assertEqual(v["resumo"]["para_revisar"], 1)
        s, r = self.decidir(v, self.item(v, "REVISAR")[0]["id"], base=base)
        self.assertEqual(s, 201, r)
        self.assertEqual(r["visao"]["resumo"]["bloqueios_restantes"], 0)
        self.assertTrue((AMB.runtime / "execucoes" / SOL_A / "supervisor-conciliacao" / "decisoes.json").is_file())
        self.assertEqual(hashlib.sha256(res.read_bytes()).hexdigest(), antes)   # resultado do Financeiro intocado
        ev = json.loads((AMB.runtime / "execucoes" / SOL_A / "supervisor-conciliacao" / "decisoes.json").read_text(encoding="utf-8"))["eventos"][0]
        self.assertEqual((ev["sol"], ev["tentativa"], ev["classificacao_motor"]), (SOL_A, "financeiro-1", "PROVAVEL"))

    def test_cr_api_13_isolamento_entre_sols(self):
        a, b = (f"/api/solicitacoes/{s}/conciliacao-financeira" for s in (SOL_A, SOL_B))
        v = self.visao(a)
        if v["resumo"]["para_revisar"]:
            self.decidir(v, self.item(v, "REVISAR")[0]["id"], base=a)
        self.assertEqual(self.visao(b)["resumo"]["para_revisar"], 1)       # decisão da SOL A não afeta a SOL B
        self.assertEqual(self.visao(b)["revisao_decisoes"], "RD-INICIAL")

    def test_cr_api_14_sol_sem_conciliacao_e_inexistente(self):
        s, v = self.j("GET", f"/api/solicitacoes/{SOL_SEM}/conciliacao-financeira")
        self.assertEqual((s, v["disponivel"]), (200, False))
        self.assertEqual(self.j("POST", f"/api/solicitacoes/{SOL_SEM}/conciliacao-financeira/decisoes-lote",
                                {"associacoes": [], "justificativa": JUST, "revisao_conciliacao": "x", "revisao_decisoes": "y"})[0], 409)
        self.assertEqual(self.j("GET", "/api/solicitacoes/SOL-2099-000999/conciliacao-financeira")[0], 404)

    def test_cr_api_15_financeiro_em_execucao_recusa(self):
        base = f"/api/solicitacoes/{SOL_B}/conciliacao-financeira"
        v = self.visao(base)
        servidor.EM_FINANCEIRO.update(sol=SOL_B, etapa="FINANCEIRO")
        try:
            s, r = self.decidir(v, self.item(v, "REVISAR")[0]["id"], base=base)
        finally:
            servidor.EM_FINANCEIRO.update(sol=None, etapa=None)
        self.assertEqual(s, 409)
        self.assertEqual(self.visao(base)["resumo"]["para_revisar"], 1)

    def test_cr_api_16_registro_corrompido(self):
        DEMO.mkdir(parents=True, exist_ok=True)
        (DEMO / "decisoes.json").write_text("{corrompido", encoding="utf-8")
        v = self.visao()
        self.assertTrue(v["acoes_bloqueadas"] and v["aviso_corrompido"])
        s, r = self.decidir(v, self.item(v, "REVISAR")[0]["id"])
        self.assertEqual((s, r["codigo"]), (409, "ESTADO_CORROMPIDO"))
        self.assertEqual((DEMO / "decisoes.json").read_text(encoding="utf-8"), "{corrompido")

    def test_cr_api_17_rejeitar_e_desfazer(self):
        v = self.visao()
        a = self.item(v, "REVISAR")[0]["id"]
        s, r = self.decidir(v, a, "REJEITADO")
        self.assertEqual((s, r["visao"]["resumo"]["rejeitados"], r["visao"]["resumo"]["bloqueios_restantes"]), (201, 1, 10))
        s, r = self.decidir(r["visao"], a, "REVOGADO")
        self.assertEqual((s, r["visao"]["resumo"]["rejeitados"], r["visao"]["resumo"]["para_revisar"]), (201, 0, 7))
        self.assertEqual(self.j("GET", BASE_DEMO + "/historico")[1]["total_eventos"], 2)

    def test_cr_api_18_nao_conciliado_sem_associacao(self):
        v = self.visao()
        n = self.item(v, "NAO_CONCILIADO")[0]["id"]
        s, d = self.j("GET", f"{BASE_DEMO}/{n}")
        self.assertEqual(d["acoes"], {"confirmar": False, "rejeitar": False, "escolher_candidato": False, "desfazer": False, "observacao": True})
        s, r = self.decidir(v, n)
        self.assertEqual((s, r["codigo"]), (409, "SEM_ASSOCIACAO"))
        s, r = self.decidir(v, n, "OBSERVACAO")
        self.assertEqual((s, r["visao"]["resumo"]["bloqueios_restantes"]), (201, 10))

    def test_cr_api_19_respostas_sem_documento_integral(self):
        v = self.visao()
        self.decidir(v, self.item(v, "REVISAR")[0]["id"], justificativa="CNPJ 12.345.678/0001-95 conferido no comprovante.")
        tudo = b"".join(self.http("GET", r)[2] for r in (BASE_DEMO, BASE_DEMO + "/historico"))
        self.assertNotIn(b"12345678000195", tudo)
        self.assertNotIn("12.345.678/0001-95".encode(), tudo)

    def test_cr_api_20_cabecalhos_e_sem_json_tecnico_na_pagina(self):
        s, h, _ = self.http("GET", BASE_DEMO)
        self.assertEqual((h.get("Cache-Control"), h.get("X-Frame-Options")), ("no-store", "DENY"))
        s, _, pagina = self.http("GET", "/js/central-revisao.js", token=False)
        self.assertEqual(s, 200)
        self.assertNotIn(b"JSON.stringify(v", pagina)
        self.assertNotIn(b"innerHTML", pagina)


if __name__ == "__main__":
    unittest.main(verbosity=2)
