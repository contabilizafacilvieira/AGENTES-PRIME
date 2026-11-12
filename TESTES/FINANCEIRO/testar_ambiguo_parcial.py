"""Ambiguidade PARCIALMENTE resolvida e visibilidade dos bloqueios (AMB-PARCIAL-01..20, BLOCK-VIS-01..08). Dados FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/FINANCEIRO/testar_ambiguo_parcial.py
Cenário: 2 movimentos bancários (B1 15/09, B2 16/09) × 2 registros (R1 15/09, R2 16/09), todos R$ 10,00 → AMBIGUO 2x2 com 4
candidatos. Escolher B2↔R2 confirma SÓ B2; B1 continua visível, bloqueando e com caminho na Central. Motor (Política V1) intacto.
"""
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "TESTES/FINANCEIRO"))
import testar_associacao_manual as tm  # noqa: E402  (mesmos construtores fictícios)
from testar_associacao_manual import a, b, assoc, central, dcs, efetivas, fonte, individual, manual, revisoes  # noqa: E402

C = lambda bi, ai: {"bancarios": [f"BX-{bi}"], "auxiliares": [f"AX-{ai}"]}


def cenario(extra_b=(), extra_a=()):
    return fonte([b(1, 15, "10.00", desc="TARIFA AVULSA"), b(2, 16, "10.00", desc="TARIFA AVULSA"), *extra_b],
                 [a(1, 15, "10.00", cp="BANCO DEMO"), a(2, 16, "10.00", cp="BANCO DEMO"), *extra_a])


def escolher(f, bi, ai):
    return individual(f, assoc(f, 1), dcs.APROVADO, candidato=C(bi, ai))


def revogar(f, alvo=None):
    x = assoc(f, 1)
    corpo = dict(revisoes(f), justificativa=tm.JUST)
    return central.decidir(f, [{"associacao": x["id"], "decisao": dcs.REVOGADO, "candidato": None, **({"alvo": alvo} if alvo else {})}],
                           corpo, "INDIVIDUAL")


def recusa(test, codigo, fn):
    with test.assertRaises(dcs.DecisaoRecusada) as cm:
        fn()
    test.assertEqual(cm.exception.codigo, codigo, cm.exception.mensagem)


def cand(d, bi, ai):
    return next(c for c in d["candidatos"] if c["bancarios"] == [f"BX-{bi}"] and c["auxiliares"] == [f"AX-{ai}"])


class AmbiguoParcial(unittest.TestCase):
    def test_amb_parcial_01_dois_por_dois_quatro_candidatos(self):
        x = assoc(cenario(), 1)
        self.assertEqual((x["classificacao"], x["cardinalidade"], len(x["candidatos"])), ("AMBIGUO", "2x2", 4))

    def test_amb_parcial_02_confirma_somente_b2(self):
        f = cenario()
        escolher(f, 2, 2)
        x, ev = assoc(f, 1), efetivas(f)[assoc(f, 1)["id"]]
        self.assertEqual(dcs.ids_confirmados(x, ev), (["BX-2"], ["AX-2"]))
        self.assertEqual(dcs.estado_operacional(x, ev), dcs.AGUARDANDO)          # grupo NÃO resolvido
        self.assertTrue(dcs.parcial(x, ev))

    def test_amb_parcial_03_b1_continua_bloqueando(self):
        f = cenario()
        escolher(f, 2, 2)
        self.assertEqual(dcs.bloqueios(f.conciliacao, efetivas(f)), ["BX-1"])

    def test_amb_parcial_04_r2_indisponivel(self):
        f = cenario()
        escolher(f, 2, 2)
        d = central.detalhe(f, assoc(f, 1)["id"])
        self.assertFalse(cand(d, 1, 2)["disponivel"])
        self.assertFalse(cand(d, 2, 1)["disponivel"])
        self.assertIn("AX-2", dcs.auxiliares_confirmados(f.conciliacao, efetivas(f)))

    def test_amb_parcial_05_r1_continua_disponivel(self):
        f = cenario()
        escolher(f, 2, 2)
        d = central.detalhe(f, assoc(f, 1)["id"])
        self.assertTrue(cand(d, 1, 1)["disponivel"])
        self.assertTrue(d["acoes"]["escolher_candidato"])
        self.assertNotIn("AX-1", dcs.auxiliares_confirmados(f.conciliacao, efetivas(f)))

    def test_amb_parcial_06_b1_visivel_na_central(self):
        f = cenario()
        escolher(f, 2, 2)
        v = central.visao(f)
        item = next(i for i in v["itens"] if i["id"] == assoc(f, 1)["id"])
        self.assertEqual((item["status"], item["parcial"], item["movimentos_resolvidos"], item["movimentos_total"]), ("AMBIGUO", True, 1, 2))
        self.assertEqual(v["resumo"]["ambiguos"], 1)
        self.assertEqual([x["associacao"] for x in v["bloqueios_lista"]], [assoc(f, 1)["id"]])

    def test_amb_parcial_07_classificacao_b1_continua_ambiguo(self):
        f = cenario()
        escolher(f, 2, 2)
        self.assertEqual(central.visao(f)["bloqueios_lista"][0]["classificacao_motor"], "AMBIGUO")
        self.assertEqual(assoc(f, 1)["classificacao"], "AMBIGUO")

    def test_amb_parcial_08_classificacao_b2_continua_ambiguo(self):
        f = cenario()
        ev = escolher(f, 2, 2)[0]
        self.assertEqual(ev["classificacao_motor"], "AMBIGUO")
        self.assertEqual(next(i for i in central.visao(f)["itens"] if i["id"] == assoc(f, 1)["id"])["classificacao_motor"], "AMBIGUO")

    def test_amb_parcial_09_resta_um_sem_confirmacao_automatica(self):
        f = cenario()
        escolher(f, 2, 2)
        d = central.detalhe(f, assoc(f, 1)["id"])
        self.assertEqual(sum(c["disponivel"] for c in d["candidatos"]), 1)
        self.assertIn("resta 1 associação possível", d["aviso_candidatos"])
        self.assertIn("BX-1", dcs.bloqueios(f.conciliacao, efetivas(f)))
        self.assertEqual(len(dcs.carregar(f.caminho, tm.CTX)["eventos"]), 1)

    def test_amb_parcial_10_supervisor_confirma_b1_r1(self):
        f = cenario()
        escolher(f, 2, 2)
        ev = escolher(f, 1, 1)[0]
        self.assertEqual((ev["decisao"], ev["candidato_escolhido"]), ("APROVADO", C(1, 1)))

    def test_amb_parcial_11_dois_de_dois_confirmados(self):
        f = cenario()
        escolher(f, 2, 2)
        ev2 = escolher(f, 1, 1)[0]
        x, ev = assoc(f, 1), efetivas(f)[assoc(f, 1)["id"]]
        self.assertEqual(dcs.ids_confirmados(x, ev), (["BX-1", "BX-2"], ["AX-1", "AX-2"]))
        self.assertEqual((dcs.estado_operacional(x, ev), ev2["estado_posterior"]), (dcs.CONFIRMADA_SUPERVISOR, dcs.CONFIRMADA_SUPERVISOR))

    def test_amb_parcial_12_nenhum_bloqueio(self):
        f = cenario()
        escolher(f, 2, 2)
        escolher(f, 1, 1)
        v = central.visao(f)
        self.assertEqual((v["resumo"]["bloqueios_restantes"], v["resumo"]["ambiguos"], v["bloqueios_lista"]), (0, 0, []))

    def test_amb_parcial_13_revogacao_restaura_disponibilidade(self):
        f = cenario()
        e22 = escolher(f, 2, 2)[0]
        revogar(f)                                                                  # única escolha: alvo implícito
        d = central.detalhe(f, assoc(f, 1)["id"])
        self.assertEqual(sum(c["disponivel"] for c in d["candidatos"]), 4)
        self.assertEqual(dcs.bloqueios(f.conciliacao, efetivas(f)), ["BX-1", "BX-2"])
        g = cenario()
        e22 = escolher(g, 2, 2)[0]
        escolher(g, 1, 1)
        recusa(self, "ALVO_OBRIGATORIO", lambda: revogar(g))                         # duas escolhas: precisa dizer qual
        rv = revogar(g, e22["id"])[0]
        x, ev = assoc(g, 1), efetivas(g)[assoc(g, 1)["id"]]
        self.assertEqual((rv["decisao_anterior"], dcs.ids_confirmados(x, ev)), (e22["id"], (["BX-1"], ["AX-1"])))
        self.assertEqual(dcs.bloqueios(g.conciliacao, efetivas(g)), ["BX-2"])
        self.assertTrue(cand(central.detalhe(g, x["id"]), 2, 2)["disponivel"])

    def test_amb_parcial_14_double_consumption_recusado(self):
        f = cenario()
        escolher(f, 2, 2)
        recusa(self, "CANDIDATO_INDISPONIVEL", lambda: escolher(f, 1, 2))           # R2 já consumido
        recusa(self, "CANDIDATO_INDISPONIVEL", lambda: escolher(f, 2, 1))           # B2 já confirmado
        recusa(self, "DECISAO_REPETIDA", lambda: escolher(f, 2, 2))
        g = cenario(extra_b=[b(9, 28, "10.00", desc="PIX OUTRO")])                 # R1 usado em associação manual de outro banco
        manual(g, 9, [1])
        recusa(self, "CONFLITO", lambda: escolher(g, 1, 1))
        self.assertEqual(len(dcs.carregar(f.caminho, tm.CTX)["eventos"]), 1)

    def test_amb_parcial_15_estado_obsoleto(self):
        f = cenario()
        velha = revisoes(f)
        escolher(f, 2, 2)
        with self.assertRaises(dcs.EstadoObsoleto):
            central.decidir(f, [{"associacao": assoc(f, 1)["id"], "decisao": dcs.APROVADO, "candidato": C(1, 1)}],
                            dict(velha, justificativa=tm.JUST), "INDIVIDUAL")

    def test_amb_parcial_16_auditoria_preservada(self):
        f = cenario()
        e1 = escolher(f, 2, 2)[0]
        e2 = escolher(f, 1, 1)[0]
        e3 = revogar(f, e1["id"])[0]
        d = dcs.carregar(f.caminho, tm.CTX)
        self.assertEqual([e["decisao"] for e in d["eventos"]], ["APROVADO", "APROVADO", "REVOGADO"])
        self.assertEqual(d["eventos"][:2], [e1, e2])
        self.assertEqual((e1["estado_posterior"], e2["estado_posterior"], e3["estado_posterior"]), (dcs.AGUARDANDO, dcs.CONFIRMADA_SUPERVISOR, dcs.AGUARDANDO))
        self.assertTrue(dcs.validar(d, tm.CTX))

    def test_amb_parcial_17_classificacao_do_motor_intacta(self):
        f = cenario()
        antes = json.dumps(f.conciliacao, sort_keys=True)
        e1 = escolher(f, 2, 2)[0]
        escolher(f, 1, 1)
        revogar(f, e1["id"])
        self.assertEqual(json.dumps(f.conciliacao, sort_keys=True), antes)

    def test_amb_parcial_18_sem_suporte_documental(self):
        f = cenario()
        escolher(f, 2, 2)
        escolher(f, 1, 1)
        for ev in dcs.carregar(f.caminho, tm.CTX)["eventos"]:
            self.assertEqual((ev["suporte_documental"], ev["suporte_fiscal"], ev["lancamento_contabil"]), (False, False, False))

    def test_amb_parcial_19_20_nao_executa_financeiro_nem_contabilidade(self):
        f = cenario()
        escolher(f, 2, 2)
        escolher(f, 1, 1)
        raiz = f.caminho.parent.parent
        self.assertEqual(sorted(p.relative_to(raiz).as_posix() for p in raiz.rglob("*") if p.is_file()), ["decisoes/decisoes.json"])


class VisibilidadeBloqueios(unittest.TestCase):
    def grande(self):
        """43 movimentos fictícios: 40 conciliados (documento exato) + 1 não conciliado + ambíguo 2x2 com B2↔R2 escolhido."""
        bs = [b(100 + i, 1 + i % 27, f"{1000 + i}.00", desc=f"PAGTO BOLETO DOC{i:05d}", doc=f"DOC{i:05d}") for i in range(40)]
        as_ = [a(100 + i, 1 + i % 27, f"{1000 + i}.00", doc=f"DOC{i:05d}") for i in range(40)]
        f = cenario(extra_b=bs + [b(7, 3, "54321.98", desc="PIX ENVIADO SEM PAR")], extra_a=as_)
        escolher(f, 2, 2)
        return f

    def test_block_vis_01_43_menos_41_igual_2(self):
        v = central.visao(self.grande())
        r = v["resumo"]
        self.assertEqual((r["movimentos_bancarios"], r["movimentos_confirmados"], r["bloqueios_restantes"]), (43, 41, 2))
        self.assertTrue(v["invariante"]["ok"])

    def test_block_vis_02_dois_bloqueios_visiveis(self):
        v = central.visao(self.grande())
        self.assertEqual(len(v["bloqueios_lista"]), 2)
        self.assertTrue(v["invariante"]["todos_visiveis"])
        ids = {i["id"] for i in v["itens"]}
        self.assertTrue(all(x["associacao"] in ids for x in v["bloqueios_lista"]))

    def test_block_vis_03_decisao_parcial_nao_esconde(self):
        v = central.visao(self.grande())
        sit = sorted((x["classificacao_motor"], x["situacao"]) for x in v["bloqueios_lista"])
        self.assertEqual(sit, [("AMBIGUO", "Ambíguo — parcialmente resolvido"), ("NAO_CONCILIADO", "Não conciliado")])

    def test_block_vis_04_zero_ambiguos_nao_coexiste_com_remanescente(self):
        v = central.visao(self.grande())
        ambiguos_remanescentes = [x for x in v["bloqueios_lista"] if x["classificacao_motor"] == "AMBIGUO"]
        self.assertTrue(ambiguos_remanescentes)
        self.assertGreaterEqual(v["resumo"]["ambiguos"], 1)
        self.assertEqual(sum(1 for i in v["itens"] if i["status"] == "AMBIGUO"), v["resumo"]["ambiguos"])

    def test_block_vis_05_ver_bloqueios_lista_todos(self):
        f = self.grande()
        v = central.visao(f)
        self.assertEqual(len(v["bloqueios_lista"]), v["resumo"]["bloqueios_restantes"])
        por_b = {i: x["id"] for x in f.conciliacao["associacoes"] for i in x["bancarios"]}
        self.assertEqual(sorted(x["associacao"] for x in v["bloqueios_lista"]),
                         sorted(por_b[i] for i in dcs.bloqueios(f.conciliacao, efetivas(f))))

    def test_block_vis_06_problema_impacto_o_que_fazer(self):
        for x in central.visao(self.grande())["bloqueios_lista"]:
            self.assertTrue(x["problema"] and x["impacto"] and x["o_que_fazer"] and x["acao"])
            self.assertTrue(x["data"] and x["valor"] and x["natureza"] and x["estado_operacional"])

    def test_block_vis_07_observacao_nao_resolve(self):
        f = self.grande()
        individual(f, assoc(f, 7), dcs.OBSERVACAO)
        individual(f, assoc(f, 1), dcs.OBSERVACAO)
        v = central.visao(f)
        self.assertEqual(v["resumo"]["bloqueios_restantes"], 2)

    def test_block_vis_08_contagem_por_movimento_unico(self):
        f = self.grande()
        v = central.visao(f)
        bancos = {i for x in f.conciliacao["associacoes"] for i in x["bancarios"]}
        self.assertEqual(v["resumo"]["movimentos_bancarios"], len(bancos))
        grupos_bloqueio = {x["associacao"] for x in v["bloqueios_lista"]}
        self.assertEqual(len(grupos_bloqueio), 2)                                  # 2 movimentos, 2 linhas — nunca por card/grupo
        self.assertEqual(len(dcs.bloqueios(f.conciliacao, efetivas(f))), v["resumo"]["bloqueios_restantes"])


class PoliticaV1(unittest.TestCase):
    def test_motor_inalterado(self):
        import hashlib
        arq = RAIZ / "AGENTES/FINANCEIRO/ferramentas/conciliador_financeiro.py"
        self.assertEqual(hashlib.sha256(arq.read_bytes()).hexdigest()[:12], "bb9fda04a3fe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
