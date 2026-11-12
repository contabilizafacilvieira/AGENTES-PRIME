"""Associação MANUAL ASSISTIDA pelo Supervisor (MANUAL-01..30, BUSCA-01..10, CENARIO-1x4). Somente dados FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/FINANCEIRO/testar_associacao_manual.py
O motor (Política V1) classifica; a associação manual é uma decisão POSTERIOR do Supervisor, em camada separada
(DECISOES_SUPERVISOR_CONCILIACAO_V1, origem ASSOCIACAO_MANUAL_ASSISTIDA). Nada real é lido ou gravado.
"""
import copy
import hashlib
import json
import sys
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "AGENTES/FINANCEIRO/ferramentas"))
sys.path.insert(0, str(RAIZ / "TESTES/FINANCEIRO"))
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import conciliador_financeiro as cf  # noqa: E402
import decisoes_conciliacao as dcs  # noqa: E402
import central_conciliacao as central  # noqa: E402
import testar_decisoes_supervisor as sup  # noqa: E402

CTX = {"sol": "SOL-2099-000501", "empresa": "EMPRESA-MANUAL-FICTICIA", "competencia": "2026-09", "tentativa": "financeiro-1"}
JUST = "Conferi os registros selecionados; soma, natureza e contraparte conferem (teste fictício)."
SHA_B, SHA_A = "b" * 64, "a" * 64


def b(i, dia, valor, nat="DEBITO", desc="PIX ENVIADO EMPRESA FICTICIA", doc=None):
    return {"id": f"BX-{i}", "data": f"2026-09-{dia:02d}", "valor": Decimal(valor), "natureza": nat, "descricao": desc, "documento": doc,
            "sha256_origem": SHA_B}


def a(i, dia, valor, nat="SAIDA", cp="FORNECEDOR FICTICIO", doc=None, desc="Lançamento fictício", sha=SHA_A, cpdoc=None):
    return {"id": f"AX-{i}", "data": f"2026-09-{dia:02d}", "data_quitacao": f"2026-09-{dia:02d}", "data_competencia": None, "valor": Decimal(valor),
            "natureza": nat, "documento": doc, "contraparte": {"nome": cp, **({"documento": cpdoc} if cpdoc else {})}, "descricao": desc,
            "plano_contas": "Despesas gerais", "banco": "BANCO FICTICIO", "sha": sha}


def fonte(bancos, auxs, ctx=CTX):
    conc = cf.para_json(cf.conciliar(
        [{"contrato": cf.CONTRATO_BANCARIO, "situacao": "NORMALIZADO", "adaptador": "FICTICIO", "origem": {"sha256": SHA_B}, "movimentos": bancos}],
        [{"contrato": cf.CONTRATO_AUXILIAR, "situacao": "NORMALIZADO", "adaptador": "FICTICIO", "origem": {"sha256": SHA_A}, "movimentos": auxs}]))
    bancarios = {m["id"]: {"data": m["data"], "valor": f"{m['valor']:.2f}", "natureza": "ENTRADA" if m["natureza"] == "CREDITO" else "SAIDA",
                           "descricao": m["descricao"], "documento": m["documento"], "suporte": False} for m in bancos}
    auxiliares = {m["id"]: dict(m, valor=f"{m['valor']:.2f}") for m in auxs}
    pasta = Path(tempfile.mkdtemp(prefix="manual-")) / "decisoes"
    return central.Fonte(ctx, conc, bancarios, auxiliares, [], pasta / "decisoes.json", "Fictícia", demonstracao=False)


def assoc(f, banco=None, aux=None):
    return next(x for x in f.conciliacao["associacoes"] if (banco and f"BX-{banco}" in x["bancarios"]) or (aux and f"AX-{aux}" in x["auxiliares"]))


def revisoes(f):
    dados = dcs.carregar(f.caminho, f.contexto)
    return {"revisao_conciliacao": dcs.revisao_conciliacao(f.conciliacao), "revisao_decisoes": dcs.revisao_decisoes(dados)}


def manual(f, banco, auxs, just=JUST, rev=None):
    x = assoc(f, banco)
    corpo = dict(rev or revisoes(f), justificativa=just)
    return central.decidir(f, [{"associacao": x["id"], "decisao": dcs.APROVADO, "candidato": None, "manual": {"auxiliares": [f"AX-{i}" for i in auxs]}}],
                           corpo, dcs.ORIGEM_MANUAL)


def individual(f, x, decisao, candidato=None):
    return central.decidir(f, [{"associacao": x["id"], "decisao": decisao, "candidato": candidato}], dict(revisoes(f), justificativa=JUST), "INDIVIDUAL")


def efetivas(f):
    return dcs.decisoes_efetivas(dcs.carregar(f.caminho, f.contexto), f.conciliacao)[0]


def recusa(test, codigo, fn):
    with test.assertRaises(dcs.DecisaoRecusada) as cm:
        fn()
    test.assertEqual(cm.exception.codigo, codigo, cm.exception.mensagem)


def base():
    """Cenário fictício principal: 1×4 (12.000 = 2.000+3.000+1.500+5.500), NAO_CONCILIADO pelo limite automático (3)."""
    return fonte([b(1, 3, "12000.00"), b(2, 10, "80.00", desc="PAGAMENTO DIVERSOS"), b(3, 12, "150.00", desc="PAGTO BOLETO 778899", doc="778899"),
                  b(4, 20, "777.77", desc="TARIFA DIVERSA"), b(5, 15, "300.00", desc="PIX ENVIADO")],
                 [a("A", 2, "2000.00", cp="EMPRESA FICTICIA COMERCIO", doc="NF 1"), a("B", 3, "3000.00", cp="EMPRESA FICTICIA COMERCIO", doc="NF 2"),
                  a("C", 4, "1500.00", cp="EMPRESA FICTICIA COMERCIO", doc="NF 3"), a("D", 5, "5500.00", cp="EMPRESA FICTICIA COMERCIO", doc="NF 4"),
                  a("P", 10, "80.00", cp="PRESTADOR FICTICIO"), a("K", 12, "150.00", doc="778899"),
                  a("G1", 15, "300.00", cp="GAMA FICTICIA"), a("G2", 15, "300.00", cp="DELTA FICTICIA")])


class AssociacaoManual(unittest.TestCase):
    def test_cenario_1x4_obrigatorio(self):
        f = base()
        x = assoc(f, 1)
        self.assertEqual((x["classificacao"], x["cardinalidade"]), ("NAO_CONCILIADO", "1x0"))      # motor V1 recusa (4 > 3)
        busca = central.busca_manual(f, x["id"])
        combo = next(c for c in busca["combinacoes"] if c["quantidade"] == 4)
        self.assertEqual((sorted(combo["registros"]), combo["total"], combo["diferenca"]), (["AX-A", "AX-B", "AX-C", "AX-D"], "12000.00", "0.00"))
        self.assertIn("BX-1", dcs.bloqueios(f.conciliacao, efetivas(f)))
        ev = manual(f, 1, ["A", "B", "C", "D"])[0]
        ef = efetivas(f)
        self.assertEqual(assoc(f, 1)["classificacao"], "NAO_CONCILIADO")
        self.assertEqual((ev["classificacao_motor"], dcs.estado_operacional(x, ef[x["id"]])), ("NAO_CONCILIADO", dcs.CONFIRMADA_SUPERVISOR))
        self.assertNotIn("BX-1", dcs.bloqueios(f.conciliacao, ef))
        self.assertEqual((ev["suporte_documental"], ev["suporte_fiscal"], ev["lancamento_contabil"]), (False, False, False))

    def test_manual_01_nao_conciliado_permite_busca(self):
        f = base()
        x = assoc(f, 1)
        self.assertTrue(central.detalhe(f, x["id"])["acoes"]["buscar_manual"])
        self.assertTrue(central.busca_manual(f, x["id"])["disponivel"])

    def test_manual_02_provavel_nao_usa_fluxo(self):
        f = base()
        x = assoc(f, 2)
        self.assertEqual(x["classificacao"], "PROVAVEL")
        d = central.detalhe(f, x["id"])
        self.assertFalse(d["acoes"]["buscar_manual"])
        self.assertTrue(d["acoes"]["confirmar"])
        self.assertFalse(central.busca_manual(f, x["id"])["disponivel"])
        recusa(self, "MANUAL_INDISPONIVEL", lambda: manual(f, 2, ["P"]))

    def test_manual_03_ambiguo_continua_no_fluxo_existente(self):
        f = base()
        x = assoc(f, 5)
        self.assertEqual(x["classificacao"], "AMBIGUO")
        d = central.detalhe(f, x["id"])
        self.assertTrue(d["acoes"]["escolher_candidato"] and not d["acoes"]["buscar_manual"])
        recusa(self, "MANUAL_INDISPONIVEL", lambda: manual(f, 5, ["G1"]))

    def test_manual_04_conciliado_nao_aceita(self):
        f = base()
        x = assoc(f, 3)
        self.assertEqual(x["classificacao"], "CONCILIADO")
        self.assertFalse(central.detalhe(f, x["id"])["acoes"]["buscar_manual"])
        recusa(self, "MANUAL_INDISPONIVEL", lambda: manual(f, 3, ["K"]))

    def _n(self, valores):
        alvo = sum(Decimal(v) for v in valores)
        f = fonte([b(1, 3, f"{alvo:.2f}")], [a(i, 20 + i, v) for i, v in enumerate(valores, 1)])   # fora da janela: motor não associa
        self.assertEqual(assoc(f, 1)["classificacao"], "NAO_CONCILIADO")
        ev = manual(f, 1, list(range(1, len(valores) + 1)))[0]
        self.assertEqual((ev["associacao_manual"]["quantidade"], ev["associacao_manual"]["diferenca"]), (len(valores), "0.00"))
        self.assertEqual(ev["estado_posterior"], dcs.CONFIRMADA_SUPERVISOR)

    def test_manual_05_1x1(self):
        self._n(["250.00"])

    def test_manual_06_1x2(self):
        self._n(["250.00", "100.50"])

    def test_manual_07_1x3(self):
        self._n(["250.00", "100.50", "49.50"])

    def test_manual_08_1x4(self):
        self._n(["250.00", "100.50", "49.50", "0.01"])

    def test_manual_09_1x5(self):
        self._n(["250.00", "100.50", "49.50", "0.01", "999.99"])

    def test_manual_10_1x6_nao_permitido(self):
        f = fonte([b(1, 3, "6.00")], [a(i, 20, "1.00") for i in range(1, 7)])
        recusa(self, "LIMITE_MANUAL", lambda: manual(f, 1, list(range(1, 7))))
        self.assertFalse(f.caminho.exists())

    def test_manual_11_diferenca_de_um_centavo_recusada(self):
        f = fonte([b(1, 3, "100.00")], [a(1, 20, "60.00"), a(2, 21, "39.99")])
        with self.assertRaises(dcs.DecisaoRecusada) as cm:
            manual(f, 1, [1, 2])
        self.assertEqual(cm.exception.codigo, "SOMA_DIFERENTE")
        self.assertIn("0,01", cm.exception.mensagem.replace(".", ","))

    def test_manual_12_natureza_incompativel(self):
        f = fonte([b(1, 3, "100.00")], [a(1, 20, "100.00", nat="ENTRADA")])
        recusa(self, "NATUREZA_INCOMPATIVEL", lambda: manual(f, 1, [1]))

    def test_manual_13_registro_consumido_recusado(self):
        f = base()
        recusa(self, "REGISTRO_INDISPONIVEL", lambda: manual(f, 4, ["K"]))          # já usado pelo CONCILIADO automático
        g = fonte([b(1, 3, "100.00"), b(2, 4, "100.00", desc="PIX ENVIADO OUTRO")], [a(1, 25, "100.00")])
        manual(g, 1, [1])
        recusa(self, "REGISTRO_INDISPONIVEL", lambda: manual(g, 2, [1]))             # já usado por associação manual

    def test_manual_14_conflito_entre_associacoes(self):
        f = base()
        individual(f, assoc(f, 2), dcs.APROVADO)                                   # P confirmado para BX-2
        recusa(self, "REGISTRO_INDISPONIVEL", lambda: manual(f, 4, ["P"]))
        g = base()
        h = fonte([b(1, 3, "80.00"), b(2, 10, "80.00", desc="PAGAMENTO DIVERSOS")], [a("P", 10, "80.00", cp="PRESTADOR FICTICIO")])
        manual(h, 1, ["P"])                                                        # sugerido ao BX-2 (PROVAVEL), ainda sem decisão
        recusa(self, "CONFLITO", lambda: individual(h, assoc(h, 2), dcs.APROVADO))
        self.assertTrue(g)

    def test_manual_15_varias_combinacoes_sem_escolha(self):
        f = fonte([b(1, 3, "900.00", nat="CREDITO", desc="PIX RECEBIDO")],
                  [a(1, 8, "400.00", nat="ENTRADA"), a(2, 8, "500.00", nat="ENTRADA"), a(3, 9, "300.00", nat="ENTRADA"), a(4, 10, "600.00", nat="ENTRADA")])
        busca = central.busca_manual(f, assoc(f, 1)["id"])
        self.assertEqual(sorted(sorted(c["registros"]) for c in busca["combinacoes"]), [["AX-1", "AX-2"], ["AX-3", "AX-4"]])
        self.assertFalse(f.caminho.exists())
        self.assertEqual(dcs.estado_operacional(assoc(f, 1), efetivas(f).get(assoc(f, 1)["id"])), dcs.SEM_ASSOCIACAO)

    def test_manual_16_sem_combinacao_mantem_nao_conciliado(self):
        f = base()
        x = assoc(f, 4)
        self.assertEqual(central.busca_manual(f, x["id"])["combinacoes"], [])
        recusa(self, "SOMA_DIFERENTE", lambda: manual(f, 4, ["G1"]))
        self.assertEqual(dcs.estado_operacional(x, efetivas(f).get(x["id"])), dcs.SEM_ASSOCIACAO)
        self.assertIn("BX-4", dcs.bloqueios(f.conciliacao, efetivas(f)))

    def test_manual_17_classificacao_original_preservada(self):
        f = base()
        antes = json.dumps(f.conciliacao, sort_keys=True)
        manual(f, 1, ["A", "B", "C", "D"])
        self.assertEqual(json.dumps(f.conciliacao, sort_keys=True), antes)
        item = next(i for i in central.visao(f)["itens"] if i["id"] == assoc(f, 1)["id"])
        self.assertEqual(item["classificacao_motor"], "NAO_CONCILIADO")

    def test_manual_18_estado_operacional_confirmado(self):
        f = base()
        manual(f, 1, ["A", "B", "C", "D"])
        v = central.visao(f)
        item = next(i for i in v["itens"] if i["id"] == assoc(f, 1)["id"])
        self.assertEqual((item["estado_operacional"], item["status"], item["associacao_manual"]), (dcs.CONFIRMADA_SUPERVISOR, "APROVADO", True))
        self.assertEqual(len(item["relatorio"]), 4)
        self.assertEqual(v["resumo"]["associacoes_manuais"], 1)
        usados = [i for i in v["itens"] if i["status"] == "RELATORIO_ASSOCIADO_MANUAL"]
        self.assertEqual(len(usados), 4)

    def test_manual_19_justificativa_obrigatoria(self):
        f = base()
        for j in ("", "  ", "curta", None):
            recusa(self, "JUSTIFICATIVA_OBRIGATORIA", lambda j=j: manual(f, 1, ["A", "B", "C", "D"], just=j))
        self.assertFalse(f.caminho.exists())

    def test_manual_20_cpf_cnpj_mascarados(self):
        f = fonte([b(1, 3, "100.00")], [a(1, 20, "100.00", cpdoc="12.345.678/0001-95")])
        ev = manual(f, 1, [1], just="Conferi o comprovante do CNPJ 12.345.678/0001-95 e CPF 123.456.789-09.")[0]
        texto = f.caminho.read_text(encoding="utf-8")
        for inteiro in ("12.345.678/0001-95", "12345678000195", "123.456.789-09", "12345678909"):
            self.assertNotIn(inteiro, texto)
        self.assertEqual(ev["associacao_manual"]["registros"][0]["contraparte_documento"], "12**********95")

    def test_manual_21_auditoria_com_todos_os_registros(self):
        f = base()
        ev = manual(f, 1, ["A", "B", "C", "D"])[0]
        m = ev["associacao_manual"]
        self.assertEqual(sorted(r["id"] for r in m["registros"]), ["AX-A", "AX-B", "AX-C", "AX-D"])
        self.assertEqual(sorted(r["valor"] for r in m["registros"]), ["1500.00", "2000.00", "3000.00", "5500.00"])
        self.assertTrue(all(r["sha256_origem"] == SHA_A and r["data_quitacao"] for r in m["registros"]))
        self.assertEqual((m["valor_bancario"], m["soma_relatorio"], m["diferenca"], m["tipo"], m["ferramenta"]),
                         ("12000.00", "12000.00", "0.00", "ASSOCIACAO_MANUAL_ASSISTIDA", "ASSOCIACAO_MANUAL_ASSISTIDA_V1"))
        self.assertEqual((ev["origem"], ev["decisao"], ev["politica"], ev["sol"], ev["empresa"], ev["competencia"], ev["tentativa"]),
                         ("ASSOCIACAO_MANUAL_ASSISTIDA", "APROVADO", cf.POLITICA, CTX["sol"], CTX["empresa"], CTX["competencia"], "financeiro-1"))
        self.assertEqual((ev["estado_anterior"], ev["estado_posterior"]), (dcs.SEM_ASSOCIACAO, dcs.CONFIRMADA_SUPERVISOR))
        self.assertEqual(ev["candidato_escolhido"], {"bancarios": ["BX-1"], "auxiliares": ["AX-A", "AX-B", "AX-C", "AX-D"]})
        self.assertTrue(len(ev["hash"]) == 64 and dcs.validar(dcs.carregar(f.caminho, CTX), CTX))

    def test_manual_22_auditoria_preserva_classificacao_original(self):
        f = base()
        ev = manual(f, 1, ["A", "B", "C", "D"])[0]
        self.assertEqual((ev["classificacao_motor"], ev["bancarios"], ev["auxiliares"]), ("NAO_CONCILIADO", ["BX-1"], []))

    def test_manual_23_estado_obsoleto(self):
        f = base()
        velha = revisoes(f)
        individual(f, assoc(f, 2), dcs.APROVADO)                                 # outra decisão muda o estado
        with self.assertRaises(dcs.EstadoObsoleto):
            manual(f, 1, ["A", "B", "C", "D"], rev=velha)
        with self.assertRaises(dcs.EstadoObsoleto):
            manual(f, 1, ["A", "B", "C", "D"], rev=dict(revisoes(f), revisao_conciliacao="RC-000"))
        self.assertEqual(len(dcs.carregar(f.caminho, CTX)["eventos"]), 1)

    def test_manual_24_decisao_repetida_nao_duplica(self):
        f = base()
        manual(f, 1, ["A", "B", "C", "D"])
        recusa(self, "DECISAO_REPETIDA", lambda: manual(f, 1, ["D", "C", "B", "A"]))
        recusa(self, "JA_DECIDIDA", lambda: manual(f, 1, ["A", "B"]))
        self.assertEqual(len(dcs.carregar(f.caminho, CTX)["eventos"]), 1)

    def test_manual_25_revogacao_restaura_bloqueio(self):
        f = base()
        manual(f, 1, ["A", "B", "C", "D"])
        x = assoc(f, 1)
        self.assertNotIn("BX-1", dcs.bloqueios(f.conciliacao, efetivas(f)))
        individual(f, x, dcs.REVOGADO)
        self.assertIn("BX-1", dcs.bloqueios(f.conciliacao, efetivas(f)))
        self.assertEqual(sorted(c["registros"] for c in central.busca_manual(f, x["id"])["combinacoes"] if c["quantidade"] == 4)[0],
                         ["AX-B", "AX-A", "AX-C", "AX-D"])                       # registros disponíveis de novo
        self.assertTrue(central.detalhe(f, x["id"])["acoes"]["buscar_manual"])

    def test_manual_26_revogacao_preserva_historico(self):
        f = base()
        e1 = manual(f, 1, ["A", "B", "C", "D"])[0]
        e2 = individual(f, assoc(f, 1), dcs.REVOGADO)[0]
        d = dcs.carregar(f.caminho, CTX)
        self.assertEqual([e["decisao"] for e in d["eventos"]], ["APROVADO", "REVOGADO"])
        self.assertEqual(d["eventos"][0], e1)
        self.assertEqual((e2["decisao_anterior"], e2["hash_anterior"], e2["classificacao_motor"]), (e1["id"], e1["hash"], "NAO_CONCILIADO"))

    def _financeiro(self):
        """Financeiro REAL (código) com extrato e relatório fictícios: o débito de 200,00 só fecha com 4 registros (70+55+45+30)."""
        rel = sup.ib.relatorio_casavel(sem=(5,))
        extra = sup.ib.aux.relatorio([sup.ib.aux.CAB] + [sup.ib.aux.lin(90 + i, "Sim", None, v, quit="2026-10-07")
                                                         for i, v in enumerate(("70,00", "55,00", "45,00", "30,00"))], sha="e" * 64)
        arquivos = [sup.ib.extrato_identificado(), rel, extra]
        r0 = sup.conferir_com(None, arquivos)
        conc = r0["conciliacao_financeira"]
        x = next(z for z in conc["associacoes"] if z["classificacao"] == "NAO_CONCILIADO" and z["bancarios"])
        regs = {m["id"]: m for m in r0["movimentos_financeiros_auxiliares"]}
        escolhidos = sorted(z["auxiliares"][0] for z in conc["associacoes"] if not z["bancarios"])
        dados, evs = dcs.registrar(dcs.vazio(sup.CTX_FIN), sup.CTX_FIN, conc, [{"associacao": x["id"], "decisao": dcs.APROVADO, "manual": {"auxiliares": escolhidos}}],
                                   revisao_conciliacao_cliente=dcs.revisao_conciliacao(conc), revisao_decisoes_cliente="RD-INICIAL",
                                   justificativa=JUST, origem=dcs.ORIGEM_MANUAL, registros=regs)
        return arquivos, r0, dados, x

    def test_manual_27_nao_cria_suporte_documental(self):
        arquivos, r0, dados, x = self._financeiro()
        self.assertTrue(r0["bloqueio_lote"])
        r1 = sup.conferir_com(dados, arquivos)
        self.assertEqual(r1["bloqueio_lote"], [])                                   # deixou de bloquear pela associação
        m = next(m for m in r1["movimentos"] if m["conciliacao_financeira"]["associacao"] == x["id"])
        self.assertEqual((m["situacao"], m["documentos"], m["conciliacao_financeira"]["suporte_documental"]), ("SEM_SUPORTE", [], False))
        self.assertEqual((m["conciliacao_financeira"]["classificacao"], m["conciliacao_financeira"]["decisao_supervisor"]["estado_operacional"]),
                         ("NAO_CONCILIADO", dcs.CONFIRMADA_SUPERVISOR))

    def test_manual_28_nao_executa_contabilidade(self):
        arquivos, r0, dados, x = self._financeiro()
        r1 = sup.conferir_com(dados, arquivos)
        self.assertFalse([k for k in r1 if "bancos" in k.lower() or "lancament" in k.lower()])
        f = base()
        manual(f, 1, ["A", "B", "C", "D"])
        self.assertEqual([p.name for p in f.caminho.parent.iterdir()], ["decisoes.json"])

    def test_manual_29_nao_gera_lancamento_txt(self):
        f = base()
        manual(f, 1, ["A", "B", "C", "D"])
        raiz = f.caminho.parent.parent
        self.assertFalse([p for p in raiz.rglob("*") if p.suffix.lower() in (".txt", ".csv", ".xlsx")])
        ev = dcs.carregar(f.caminho, CTX)["eventos"][0]
        self.assertFalse(ev["lancamento_contabil"])

    def test_manual_30_isolamento(self):
        f = base()
        manual(f, 1, ["A", "B", "C", "D"])
        dados = json.loads(f.caminho.read_text(encoding="utf-8"))
        for campo, valor in (("sol", "SOL-2099-000502"), ("empresa", "OUTRA-EMPRESA"), ("competencia", "2026-08"), ("tentativa", None)):
            if campo == "tentativa":
                continue
            with self.assertRaises(dcs.EstadoCorrompido):
                dcs.validar(dados, dict(CTX, **{campo: valor}))
        outra = fonte([b(1, 3, "100.00")], [a("Z", 20, "100.00")], ctx=dict(CTX, sol="SOL-2099-000502"))
        g = base()
        g.auxiliares = dict(g.auxiliares, **{"AX-Z": outra.auxiliares["AX-Z"]})      # registro de OUTRA conciliação/tentativa
        recusa(self, "REGISTRO_INEXISTENTE", lambda: manual(g, 4, ["Z"]))
        ids = {c["id"] for c in central.busca_manual(outra, assoc(outra, 1)["id"])["candidatos"]}
        self.assertEqual(ids, {"AX-Z"})


class BuscaAssistida(unittest.TestCase):
    def test_busca_01_registro_individual_exato(self):
        f = fonte([b(1, 3, "321.45")], [a(1, 20, "321.45"), a(2, 21, "100.00")])
        bus = central.busca_manual(f, assoc(f, 1)["id"])
        self.assertEqual([(c["quantidade"], c["registros"]) for c in bus["combinacoes"]], [(1, ["AX-1"])])
        self.assertTrue(next(c for c in bus["candidatos"] if c["id"] == "AX-1")["valor_exato"])

    def test_busca_02_combinacao_de_quatro(self):
        f = base()
        combos = central.busca_manual(f, assoc(f, 1)["id"])["combinacoes"]
        self.assertIn(["AX-A", "AX-B", "AX-C", "AX-D"], [sorted(c["registros"]) for c in combos if c["quantidade"] == 4])

    def test_busca_03_duas_combinacoes_sem_escolha(self):
        f = fonte([b(1, 3, "900.00", nat="CREDITO", desc="PIX RECEBIDO")],
                  [a(i, 8 + i, v, nat="ENTRADA") for i, v in enumerate(("400.00", "500.00", "300.00", "600.00"), 1)])
        bus = central.busca_manual(f, assoc(f, 1)["id"])
        self.assertEqual(len(bus["combinacoes"]), 2)
        self.assertFalse(any("escolhid" in json.dumps(c) or "correta" in json.dumps(c) for c in bus["combinacoes"]))
        self.assertIn("nenhuma é escolhida pelo sistema", " ".join(bus["explicacao"]))
        self.assertFalse(f.caminho.exists())

    def test_busca_04_decimal_exato(self):
        f = fonte([b(1, 3, "0.30")], [a(1, 20, "0.10"), a(2, 21, "0.20"), a(3, 22, "0.21")])
        combos = [sorted(c["registros"]) for c in central.busca_manual(f, assoc(f, 1)["id"])["combinacoes"]]
        self.assertEqual(combos, [["AX-1", "AX-2"]])                                # 0,10 + 0,20 = 0,30 exato; 0,10 + 0,21 não
        self.assertEqual(central.combinacoes_exatas(30, [10, 21]), ([], True))

    def test_busca_05_consumido_nao_aparece(self):
        f = base()
        manual(f, 1, ["A", "B", "C", "D"])
        bus = central.busca_manual(f, assoc(f, 4)["id"])
        ids = {c["id"] for c in bus["candidatos"]}
        self.assertFalse(ids & {"AX-A", "AX-B", "AX-C", "AX-D", "AX-K"})
        self.assertGreaterEqual(bus["ignorados"]["indisponivel"], 5)

    def test_busca_06_ordenacao_por_data(self):
        f = fonte([b(1, 15, "999.00")], [a(1, 1, "10.00"), a(2, 14, "10.00"), a(3, 30, "10.00"), a(4, 17, "10.00")])
        dias = [c["dias"] for c in central.busca_manual(f, assoc(f, 1)["id"])["candidatos"]]
        self.assertEqual(dias, sorted(dias))
        self.assertEqual(dias[:2], [1, 2])

    def test_busca_07_data_distante_com_alerta(self):
        f = fonte([b(1, 3, "999.00")], [a(1, 4, "10.00"), a(2, 30, "10.00")])
        c = {x["id"]: x for x in central.busca_manual(f, assoc(f, 1)["id"])["candidatos"]}
        self.assertEqual((c["AX-1"]["alerta_data"], c["AX-2"]["alerta_data"]), (False, True))   # distante aparece, com alerta

    def test_busca_08_contraparte_e_documento_sao_evidencia_nao_decisao(self):
        f = base()
        bus = central.busca_manual(f, assoc(f, 1)["id"])
        c = next(x for x in bus["candidatos"] if x["id"] == "AX-A")
        self.assertEqual((c["contraparte"], c["documento"], c["plano_contas"], c["banco_relatorio"]),
                         ("EMPRESA FICTICIA COMERCIO", "NF 1", "Despesas gerais", "BANCO FICTICIO"))
        self.assertFalse(f.caminho.exists())
        self.assertEqual(assoc(f, 1)["classificacao"], "NAO_CONCILIADO")

    def test_busca_09_limite_combinatorio(self):
        f = fonte([b(1, 3, "5.00")], [a(i, 20, "1.00") for i in range(1, 61)])
        ini = time.time()
        bus = central.busca_manual(f, assoc(f, 1)["id"])
        self.assertLess(time.time() - ini, 5)
        self.assertLessEqual(len(bus["combinacoes"]), central.LIMITE_COMBINACOES)
        self.assertFalse(bus["busca_completa"])
        self.assertTrue(all(c["quantidade"] <= dcs.LIMITE_MANUAL for c in bus["combinacoes"]))
        self.assertEqual(central.combinacoes_exatas(5, [1] * 60, passos=10)[1], False)

    def test_busca_10_deterministica(self):
        f = base()
        x = assoc(f, 1)["id"]
        self.assertEqual(json.dumps(central.busca_manual(f, x), sort_keys=True), json.dumps(central.busca_manual(f, x), sort_keys=True))


class PoliticaV1Congelada(unittest.TestCase):
    def test_conciliador_identico_ao_publicado(self):
        arq = RAIZ / "AGENTES/FINANCEIRO/ferramentas/conciliador_financeiro.py"
        self.assertEqual(hashlib.sha256(arq.read_bytes()).hexdigest(), "bb9fda04a3fe8553007176c9b1c5b24f657e8d0a393e65b8bc27f3f83d20baec")
        self.assertEqual((cf.LIMITE_GRUPO, cf.JANELA_DIAS, cf.LIMITE_CANDIDATOS_GRUPO), (3, 2, 12))


if __name__ == "__main__":
    unittest.main(verbosity=2)
