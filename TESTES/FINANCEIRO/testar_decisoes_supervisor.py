"""Decisões do Supervisor sobre a conciliação financeira (SUP-01..30) + regressão da POLÍTICA V1. Somente dados FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/FINANCEIRO/testar_decisoes_supervisor.py
Base: cenário fictício da demonstração (conciliado pelo motor real) e o extrato/relatório fictícios das baterias do Financeiro.
Nada do runtime, de CLIENTES/ ou do registro operacional é lido ou gravado (pastas temporárias).
"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "AGENTES/FINANCEIRO/ferramentas"))
sys.path.insert(0, str(RAIZ / "TESTES/FINANCEIRO"))
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import conciliador_financeiro as cf  # noqa: E402
import decisoes_conciliacao as dcs  # noqa: E402
import central_conciliacao as central  # noqa: E402
import testar_integracao_bancaria as ib  # noqa: E402
import conferencia_financeira as f  # noqa: E402

CTX = {"sol": "SOL-2099-000001", "empresa": "EMPRESA-FICTICIA-SUP", "competencia": "2026-09", "tentativa": "financeiro-1"}
EM = "2026-11-11T10:00:00-03:00"
JUST = "Conferi data, valor e favorecido (teste fictício)."
CONC, BANC, AUXS = central.montar_demo()


def assoc_de(conc, banco=None, aux=None):
    return next(x for x in conc["associacoes"] if (banco and f"DEMO-{banco}" in x["bancarios"]) or (aux and f"DEMO-{aux}" in x["auxiliares"]))


def decidir(dados, pedidos, origem="INDIVIDUAL", just=JUST, conc=None, ctx=CTX, rc=None, rd=None):
    conc = conc or CONC
    return dcs.registrar(dados, ctx, conc, pedidos, revisao_conciliacao_cliente=rc or dcs.revisao_conciliacao(conc),
                         revisao_decisoes_cliente=rd or dcs.revisao_decisoes(dados), justificativa=just, origem=origem, em=EM)


def pedido(x, decisao="APROVADO", candidato=None):
    return {"associacao": x["id"], "decisao": decisao, "candidato": candidato}


def efetivas(dados, conc=None):
    return dcs.decisoes_efetivas(dados, conc or CONC)[0]


PROV = [x for x in CONC["associacoes"] if x["classificacao"] == "PROVAVEL"]
B04, B05, B10, B11, B01, B15 = (assoc_de(CONC, b) for b in ("B04", "B05", "B10", "B11", "B01", "B15"))


# ---------------------------------------------------------------- Financeiro real com decisões (SUP-13..17, 21..23, 25, 30)
CTX_FIN = {"sol": "SOL-2099-999999", "empresa": "EMPRESA-FICTICIA", "competencia": "2026-10"}


def relatorio_com_provavel():
    """Relatório fictício em que o crédito de 500,00 fica PROVÁVEL (sem contraparte) e os demais CONCILIADOS."""
    base = ib.relatorio_casavel(sem=(2,))
    extra = ib.aux.relatorio([ib.aux.CAB, ib.aux.lin(9, "Não", "500,00", None, quit="2026-10-01")], sha="c" * 64)
    return base, extra


def conferir_com(decisoes=None, arquivos=None):
    with tempfile.TemporaryDirectory() as vazio, patch.dict(os.environ, {"AGENTES_PRIME_CLIENTES": vazio}), \
            patch.object(f, "cadastro", return_value=copy.deepcopy(ib.CAD)):
        c = f.Conferencia(CTX_FIN["empresa"], CTX_FIN["competencia"], CTX_FIN["sol"])
        if decisoes is not None:
            c.decisoes_conciliacao = decisoes
        c.carregar(arquivos or [ib.extrato_identificado(), *relatorio_com_provavel()])
        c.preparar_movimentos()
        assert not c.triagem()
        c.corresponder({})
        return c.montar({})


def decisao_financeiro(decisao="APROVADO", ctx=CTX_FIN):
    r = conferir_com()
    conc = r["conciliacao_financeira"]
    x = next(a for a in conc["associacoes"] if a["classificacao"] == "PROVAVEL")
    dados, _ = dcs.registrar(dcs.vazio(ctx), ctx, conc, [pedido(x, decisao)], revisao_conciliacao_cliente=dcs.revisao_conciliacao(conc),
                             revisao_decisoes_cliente="RD-INICIAL", justificativa=JUST, em=EM)
    return r, dados, x


class DecisoesSupervisor(unittest.TestCase):
    def test_sup_01_provavel_aprovado(self):
        dados, evs = decidir(dcs.vazio(CTX), [pedido(B04)])
        ev = evs[0]
        self.assertEqual((ev["classificacao_motor"], ev["decisao"], ev["estado_anterior"], ev["estado_posterior"]),
                         ("PROVAVEL", "APROVADO", dcs.AGUARDANDO, dcs.CONFIRMADA_SUPERVISOR))
        self.assertEqual(dcs.estado_operacional(B04, efetivas(dados)[B04["id"]]), dcs.CONFIRMADA_SUPERVISOR)

    def test_sup_02_provavel_rejeitado(self):
        dados, evs = decidir(dcs.vazio(CTX), [pedido(B04, "REJEITADO")])
        self.assertEqual(evs[0]["estado_posterior"], dcs.REJEITADA)
        self.assertEqual(B04["classificacao"], "PROVAVEL")                    # candidato preservado, nada apagado
        self.assertIn(B04, CONC["associacoes"])

    def test_sup_03_conciliado_nao_precisa_decisao(self):
        self.assertEqual(dcs.estado_operacional(B01), dcs.CONFIRMADA_AUTO)
        for dec in ("APROVADO", "REJEITADO"):
            with self.assertRaises(dcs.DecisaoRecusada) as cm:
                decidir(dcs.vazio(CTX), [pedido(B01, dec)])
            self.assertEqual(cm.exception.codigo, "JA_CONCILIADO")
        self.assertNotIn("DEMO-B01", dcs.bloqueios(CONC, {}))

    def test_sup_04_ambiguo_exige_escolha_explicita(self):
        for cand in (None, {"bancarios": ["DEMO-B10"], "auxiliares": ["DEMO-R99"]}, "1"):
            with self.assertRaises(dcs.DecisaoRecusada) as cm:
                decidir(dcs.vazio(CTX), [pedido(B10, candidato=cand)])
            self.assertEqual(cm.exception.codigo, "CANDIDATO_OBRIGATORIO")
        c = B10["candidatos"][0]
        dados, evs = decidir(dcs.vazio(CTX), [pedido(B10, candidato={"bancarios": c["bancarios"], "auxiliares": c["auxiliares"]})])
        self.assertEqual(evs[0]["estado_posterior"], dcs.CONFIRMADA_SUPERVISOR)
        self.assertEqual(len(evs[0]["candidatos_nao_escolhidos"]), 1)        # o outro fica registrado como não escolhido

    def test_sup_05_ambiguo_nao_aceita_dois_candidatos(self):
        c1, c2 = B10["candidatos"]
        uniao = {"bancarios": ["DEMO-B10"], "auxiliares": sorted(c1["auxiliares"] + c2["auxiliares"])}
        with self.assertRaises(dcs.DecisaoRecusada) as cm:
            decidir(dcs.vazio(CTX), [pedido(B10, candidato=uniao)])
        self.assertEqual(cm.exception.codigo, "CANDIDATO_OBRIGATORIO")
        dados, _ = decidir(dcs.vazio(CTX), [pedido(B10, candidato={k: c1[k] for k in ("bancarios", "auxiliares")})])
        with self.assertRaises(dcs.DecisaoRecusada) as cm:
            decidir(dados, [pedido(B10, candidato={k: c2[k] for k in ("bancarios", "auxiliares")})])
        self.assertEqual(cm.exception.codigo, "JA_DECIDIDA")

    def test_sup_06_nao_conciliado_sem_associacao_ficticia(self):
        for dec in ("APROVADO", "REJEITADO"):
            with self.assertRaises(dcs.DecisaoRecusada) as cm:
                decidir(dcs.vazio(CTX), [pedido(B15, dec)])
            self.assertEqual(cm.exception.codigo, "SEM_ASSOCIACAO")
        dados, evs = decidir(dcs.vazio(CTX), [pedido(B15, "OBSERVACAO")])
        self.assertEqual((evs[0]["estado_anterior"], evs[0]["estado_posterior"]), (dcs.SEM_ASSOCIACAO, dcs.SEM_ASSOCIACAO))
        self.assertEqual(dcs.ids_confirmados(B15, efetivas(dados).get(B15["id"])), ([], []))
        self.assertIn("DEMO-B15", dcs.bloqueios(CONC, efetivas(dados)))

    def test_sup_07_lote_de_provaveis(self):
        dados, evs = decidir(dcs.vazio(CTX), [pedido(x) for x in PROV], origem="LOTE",
                             just="Revisei os registros selecionados e confirmo as associações.")
        self.assertEqual(len(evs), len(PROV))
        self.assertEqual(len({e["lote"] for e in evs}), 1)
        self.assertTrue(all(e["associacao"] == x["id"] and e["decisao"] == "APROVADO" for e, x in zip(evs, PROV)))   # um evento por item
        self.assertEqual(dcs.resumo(CONC, efetivas(dados))["para_revisar"], 0)

    def test_sup_08_lote_com_item_invalido_falha_inteiro(self):
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "decisoes.json"
            dcs.gravar_atomico(arq, dcs.vazio(CTX))
            original = arq.read_bytes()
            for intruso in (B10, B01, B15):                               # ambíguo, conciliado, não conciliado
                with self.assertRaises(dcs.DecisaoRecusada) as cm:
                    dcs.decidir_e_gravar(arq, CTX, CONC, [pedido(x) for x in PROV[:3]] + [pedido(intruso)], origem="LOTE",
                                         revisao_conciliacao_cliente=dcs.revisao_conciliacao(CONC), revisao_decisoes_cliente="RD-INICIAL",
                                         justificativa=JUST)
                self.assertEqual(cm.exception.codigo, "LOTE_SO_PROVAVEIS")
            for ruim in ([pedido(PROV[0]), pedido(PROV[0])], [pedido(PROV[0]), {"associacao": "CF-000000000000", "decisao": "APROVADO"}]):
                with self.assertRaises(dcs.DecisaoRecusada):
                    dcs.decidir_e_gravar(arq, CTX, CONC, ruim, origem="LOTE", revisao_conciliacao_cliente=dcs.revisao_conciliacao(CONC),
                                         revisao_decisoes_cliente="RD-INICIAL", justificativa=JUST)
            self.assertEqual(arq.read_bytes(), original)                  # nada gravado

    def test_sup_09_justificativa_obrigatoria(self):
        for j in (None, "", "   ", "curta", "\n\t \n", 123):
            with self.assertRaises(dcs.DecisaoRecusada) as cm:
                decidir(dcs.vazio(CTX), [pedido(B04)], just=j)
            self.assertEqual(cm.exception.codigo, "JUSTIFICATIVA_OBRIGATORIA")
        with self.assertRaises(dcs.DecisaoRecusada) as cm:
            decidir(dcs.vazio(CTX), [pedido(B04)], just="x" * 501)
        self.assertEqual(cm.exception.codigo, "JUSTIFICATIVA_LONGA")

    def test_sup_10_auditoria_criada(self):
        _, evs = decidir(dcs.vazio(CTX), [pedido(B04)])
        ev = evs[0]
        self.assertEqual(set(ev), set(dcs.CAMPOS_EVENTO))
        self.assertEqual((ev["sol"], ev["empresa"], ev["competencia"], ev["tentativa"]), (CTX["sol"], CTX["empresa"], CTX["competencia"], "financeiro-1"))
        self.assertEqual((ev["responsavel"], ev["em"], ev["origem"], ev["politica"]), ("Supervisor Contábil", EM, "INDIVIDUAL", cf.POLITICA))
        self.assertEqual((ev["bancarios"], ev["auxiliares"], ev["justificativa"]), (B04["bancarios"], B04["auxiliares"], JUST))
        self.assertTrue(ev["id"].startswith("DS-") and len(ev["hash"]) == 64 and ev["hash_anterior"] is None)
        self.assertEqual(ev["revisao_conciliacao"], dcs.revisao_conciliacao(CONC))

    def test_sup_11_historico_preservado_e_imutavel(self):
        d1, e1 = decidir(dcs.vazio(CTX), [pedido(B04)])
        d2, e2 = decidir(d1, [pedido(B04, "REVOGADO")], just="Aprovei por engano (teste fictício).")
        d3, _ = decidir(d2, [pedido(B04, "REJEITADO")])
        self.assertEqual([e["decisao"] for e in d3["eventos"]], ["APROVADO", "REVOGADO", "REJEITADO"])
        self.assertEqual(d3["eventos"][0], e1[0])                          # primeiro evento intacto
        self.assertEqual(e2[0]["decisao_anterior"], e1[0]["id"])
        self.assertEqual(d3["eventos"][1]["hash_anterior"], e1[0]["hash"])
        adulterado = copy.deepcopy(d3)
        adulterado["eventos"][0]["justificativa"] = "trocada depois"
        with self.assertRaises(dcs.EstadoCorrompido):
            dcs.validar(adulterado, CTX)
        apagado = copy.deepcopy(d3)
        del apagado["eventos"][1]
        with self.assertRaises(dcs.EstadoCorrompido):
            dcs.validar(apagado, CTX)

    def test_sup_12_decisao_nao_altera_classificacao_do_motor(self):
        conc = copy.deepcopy(CONC)
        antes = json.dumps(conc, sort_keys=True)
        dados, _ = decidir(dcs.vazio(CTX), [pedido(assoc_de(conc, "B04"))], conc=conc)
        decidir(dados, [pedido(assoc_de(conc, "B05"), "REJEITADO")], conc=conc)
        self.assertEqual(json.dumps(conc, sort_keys=True), antes)
        self.assertEqual(assoc_de(conc, "B04")["classificacao"], "PROVAVEL")    # nunca PROVAVEL → CONCILIADO

    def test_sup_13_decisao_nao_altera_movimento_bancario(self):
        r0 = conferir_com()
        _, dados, _ = decisao_financeiro()
        r1 = conferir_com(dados)
        limpar = lambda ms: [{k: v for k, v in m.items() if k != "conciliacao_financeira"} for m in ms]
        self.assertEqual(limpar(r1["movimentos"]), limpar(r0["movimentos"]))
        self.assertEqual([m["conciliacao_financeira"]["classificacao"] for m in r1["movimentos"]],
                         [m["conciliacao_financeira"]["classificacao"] for m in r0["movimentos"]])

    def test_sup_14_decisao_nao_altera_auxiliar(self):
        r0 = conferir_com()
        _, dados, _ = decisao_financeiro()
        r1 = conferir_com(dados)
        self.assertEqual(r1["movimentos_financeiros_auxiliares"], r0["movimentos_financeiros_auxiliares"])
        self.assertEqual(r1["conciliacao_financeira"], r0["conciliacao_financeira"])

    def test_sup_15_decisao_nao_vira_suporte_fiscal(self):
        _, dados, x = decisao_financeiro()
        r1 = conferir_com(dados)
        m = next(m for m in r1["movimentos"] if m["conciliacao_financeira"]["associacao"] == x["id"])
        self.assertEqual((m["situacao"], m["documentos"], m["conciliacao_financeira"]["suporte_documental"]), ("SEM_SUPORTE", [], False))
        self.assertEqual(m["conciliacao_financeira"]["decisao_supervisor"]["estado_operacional"], dcs.CONFIRMADA_SUPERVISOR)
        ev = dados["eventos"][0]
        self.assertEqual((ev["suporte_documental"], ev["suporte_fiscal"], ev["lancamento_contabil"]), (False, False, False))
        falso = copy.deepcopy(dados)
        falso["eventos"][0]["suporte_fiscal"] = True
        falso["eventos"][0]["hash"] = dcs._hash_evento(falso["eventos"][0])
        with self.assertRaises(dcs.EstadoCorrompido):
            dcs.validar(falso, CTX_FIN)

    def test_sup_16_aprovacao_remove_bloqueio(self):
        r0, dados, _ = decisao_financeiro("APROVADO")
        self.assertTrue(r0["bloqueio_lote"])
        r1 = conferir_com(dados)
        self.assertEqual(r1["bloqueio_lote"], [])
        self.assertNotIn("ASSOCIACAO_FINANCEIRA_NAO_CONFIRMADA", [p["tipo"] for p in r1["pendencias"]])
        d, _ = decidir(dcs.vazio(CTX), [pedido(B04)])
        self.assertEqual(len(dcs.bloqueios(CONC, efetivas(d))), len(dcs.bloqueios(CONC, {})) - 1)

    def test_sup_17_rejeicao_mantem_bloqueio(self):
        _, dados, _ = decisao_financeiro("REJEITADO")
        r1 = conferir_com(dados)
        self.assertTrue(r1["bloqueio_lote"] and "prováveis" in r1["bloqueio_lote"][0])
        d, _ = decidir(dcs.vazio(CTX), [pedido(B04, "REJEITADO")])
        self.assertIn("DEMO-B04", dcs.bloqueios(CONC, efetivas(d)))

    def test_sup_18_ambiguo_aprovado_resolve_conflito(self):
        c1, c2 = B11["candidatos"]
        d, _ = decidir(dcs.vazio(CTX), [pedido(B11, candidato={k: c2[k] for k in ("bancarios", "auxiliares")})])
        ef = efetivas(d)
        bids, aids = dcs.ids_confirmados(B11, ef[B11["id"]])
        self.assertEqual((bids, aids), (c2["bancarios"], c2["auxiliares"]))
        self.assertNotIn(c1["auxiliares"][0], aids)                        # candidato não escolhido não é confirmado
        self.assertNotIn("DEMO-B11", dcs.bloqueios(CONC, ef))
        self.assertEqual(dcs.resumo(CONC, ef)["ambiguos"], 1)

    def test_sup_19_movimento_nao_aprovado_duas_vezes(self):
        conc = copy.deepcopy(CONC)                                        # conflito artificial: duas prováveis com o MESMO banco
        x, y = assoc_de(conc, "B04"), assoc_de(conc, "B05")
        y["bancarios"] = list(x["bancarios"])
        d, _ = decidir(dcs.vazio(CTX), [pedido(x)], conc=conc)
        with self.assertRaises(dcs.DecisaoRecusada) as cm:
            decidir(d, [pedido(y)], conc=conc)
        self.assertEqual(cm.exception.codigo, "CONFLITO")
        with self.assertRaises(dcs.DecisaoRecusada) as cm:
            decidir(dcs.vazio(CTX), [pedido(x), pedido(y)], conc=conc, origem="LOTE")
        self.assertEqual(cm.exception.codigo, "CONFLITO")

    def test_sup_20_estado_obsoleto_recusado(self):
        d1, _ = decidir(dcs.vazio(CTX), [pedido(B04)])
        with self.assertRaises(dcs.EstadoObsoleto):                       # tela aberta antes da decisão anterior
            decidir(d1, [pedido(B05)], rd="RD-INICIAL")
        with self.assertRaises(dcs.EstadoObsoleto):                       # conciliação mudou depois da tela aberta
            decidir(d1, [pedido(B05)], rc="RC-0000")
        conc2 = copy.deepcopy(CONC)                                       # nova execução: a associação mudou → decisão desatualizada
        assoc_de(conc2, "B04")["auxiliares"] = ["DEMO-R99"]
        ef, desat = dcs.decisoes_efetivas(d1, conc2)
        self.assertNotIn(B04["id"], ef)
        self.assertEqual(len(desat), 1)
        self.assertIn("DEMO-B04", dcs.bloqueios(conc2, ef))

    def _isolamento(self, campo, valor):
        d, _ = decidir(dcs.vazio(CTX), [pedido(B04)])
        outro = dict(CTX, **{campo: valor})
        with self.assertRaises(dcs.EstadoCorrompido):
            dcs.validar(d, outro)
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "decisoes.json"
            dcs.gravar_atomico(arq, d)
            with self.assertRaises(dcs.EstadoCorrompido):
                dcs.carregar(arq, outro)
        _, dados, _ = decisao_financeiro()                                # decisões de outro contexto no Financeiro → nada liberado
        dados = copy.deepcopy(dados)
        dados[campo] = valor
        r = conferir_com(dados)
        self.assertTrue(r["bloqueio_lote"])
        self.assertIn("DECISOES_SUPERVISOR_INVALIDAS", [p["tipo"] for p in r["pendencias"]])

    def test_sup_21_isolamento_por_sol(self):
        self._isolamento("sol", "SOL-2099-000002")
        self.assertNotEqual(central.pasta_decisoes_sol(Path("/x"), "SOL-2099-000001"), central.pasta_decisoes_sol(Path("/x"), "SOL-2099-000002"))

    def test_sup_22_isolamento_por_empresa(self):
        self._isolamento("empresa", "OUTRA-EMPRESA-FICTICIA")

    def test_sup_23_isolamento_por_competencia(self):
        self._isolamento("competencia", "2026-08")

    def test_sup_24_escrita_atomica(self):
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "decisoes.json"
            dcs.decidir_e_gravar(arq, CTX, CONC, [pedido(B04)], revisao_conciliacao_cliente=dcs.revisao_conciliacao(CONC),
                                 revisao_decisoes_cliente="RD-INICIAL", justificativa=JUST)
            original = arq.read_bytes()
            atual = dcs.revisao_decisoes(json.loads(original))
            with patch.object(dcs.os, "replace", side_effect=OSError("disco cheio (simulado)")):
                with self.assertRaises(OSError):
                    dcs.decidir_e_gravar(arq, CTX, CONC, [pedido(B05)], revisao_conciliacao_cliente=dcs.revisao_conciliacao(CONC),
                                         revisao_decisoes_cliente=atual, justificativa=JUST)
            self.assertEqual(arq.read_bytes(), original)                  # arquivo anterior intacto
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["decisoes.json"])   # nenhum temporário largado

    def test_sup_25_estado_corrompido_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "demonstracao-conciliacao"
            fonte = central.fonte_demo(pasta)
            pasta.mkdir()
            for lixo in (b"{nao e json", json.dumps({"contrato": "OUTRO"}).encode(), b""):
                fonte.caminho.write_bytes(lixo)
                with self.assertRaises(dcs.EstadoCorrompido):
                    dcs.carregar(fonte.caminho, fonte.contexto)
                v = central.visao(fonte)
                self.assertTrue(v["acoes_bloqueadas"])
                self.assertEqual(v["resumo"]["bloqueios_restantes"], v["resumo"]["movimentos_bancarios"])
                self.assertFalse(any(central.detalhe(fonte, B04["id"])["acoes"].values()))
                with self.assertRaises(dcs.EstadoCorrompido):
                    central.decidir(fonte, [pedido(B04)], {"revisao_conciliacao": v["revisao_conciliacao"], "revisao_decisoes": "RD-INICIAL",
                                                           "justificativa": JUST}, "INDIVIDUAL")
        r = conferir_com({"contrato": "ILEGIVEL"})
        self.assertTrue(r["bloqueio_lote"])
        self.assertIn("DECISOES_SUPERVISOR_INVALIDAS", [p["tipo"] for p in r["pendencias"]])

    def test_sup_26_cpf_cnpj_nao_vazam(self):
        just = "Comprovante do CPF 123.456.789-09 e CNPJ 12.345.678/0001-95 e 98765432100 conferidos."
        d, evs = decidir(dcs.vazio(CTX), [pedido(B04)], just=just)
        texto = json.dumps(d, ensure_ascii=False)
        for inteiro in ("123.456.789-09", "12345678909", "12.345.678/0001-95", "12345678000195", "98765432100"):
            self.assertNotIn(inteiro, texto)
        self.assertIn("12*******09", evs[0]["justificativa"])
        with tempfile.TemporaryDirectory() as tmp:                         # tela: contraparte com CNPJ só aparece mascarada
            fonte = central.fonte_demo(Path(tmp) / "demonstracao-conciliacao")
            fonte.auxiliares["DEMO-R04"] = dict(fonte.auxiliares["DEMO-R04"], contraparte={"nome": "DELTA", "documento": "12345678000195"})
            dcs.gravar_atomico(fonte.caminho, d)
            saida = json.dumps([central.visao(fonte), central.detalhe(fonte, B04["id"]), central.historico(fonte)], ensure_ascii=False)
            self.assertNotIn("12345678000195", saida)
            self.assertNotIn("12345678909", saida)
            self.assertIn("12**********95", saida)

    def test_sup_27_resultado_operacional(self):
        aprov = {"decisao": "APROVADO", "candidato_escolhido": None}
        rej = {"decisao": "REJEITADO", "candidato_escolhido": None}
        esc = {"decisao": "APROVADO", "candidato_escolhido": {"bancarios": ["x"], "auxiliares": ["y"]}}
        casos = [(B01, None, dcs.CONFIRMADA_AUTO), (B04, None, dcs.AGUARDANDO), (B04, aprov, dcs.CONFIRMADA_SUPERVISOR),
                 (B04, rej, dcs.REJEITADA), (B10, None, dcs.AGUARDANDO), (B10, aprov, dcs.AGUARDANDO),   # ambíguo sem candidato: não confirma
                 (B10, esc, dcs.CONFIRMADA_SUPERVISOR), (B10, rej, dcs.REJEITADA), (B15, None, dcs.SEM_ASSOCIACAO),
                 (B15, aprov, dcs.SEM_ASSOCIACAO)]
        for x, ev, esperado in casos:
            self.assertEqual(dcs.estado_operacional(x, ev), esperado, (x["classificacao"], ev))

    def test_sup_28_cards_apos_decisoes(self):
        r = dcs.resumo(CONC, {})
        self.assertEqual((r["conciliados_automaticamente"], r["para_revisar"], r["ambiguos"], r["nao_conciliados"], r["bloqueios_restantes"]),
                         (4, 7, 2, 1, 10))
        d, _ = decidir(dcs.vazio(CTX), [pedido(B04)])
        r = dcs.resumo(CONC, efetivas(d))
        self.assertEqual((r["para_revisar"], r["bloqueios_restantes"], r["aprovados_supervisor"]), (6, 9, 1))
        d, _ = decidir(d, [pedido(B05, "REJEITADO")])
        r = dcs.resumo(CONC, efetivas(d))
        self.assertEqual((r["para_revisar"], r["rejeitados"], r["bloqueios_restantes"]), (5, 1, 9))
        c = B10["candidatos"][0]
        d, _ = decidir(d, [pedido(B10, candidato={k: c[k] for k in ("bancarios", "auxiliares")})])
        r = dcs.resumo(CONC, efetivas(d))
        self.assertEqual((r["ambiguos"], r["bloqueios_restantes"], r["movimentos_confirmados"]), (1, 8, 7))

    def test_sup_29_decisao_repetida_recusada_explicitamente(self):
        d, _ = decidir(dcs.vazio(CTX), [pedido(B04)])
        with self.assertRaises(dcs.DecisaoRecusada) as cm:
            decidir(d, [pedido(B04)])
        self.assertEqual(cm.exception.codigo, "DECISAO_REPETIDA")
        with self.assertRaises(dcs.DecisaoRecusada) as cm:
            decidir(d, [pedido(B04, "REJEITADO")])
        self.assertEqual(cm.exception.codigo, "JA_DECIDIDA")
        with self.assertRaises(dcs.DecisaoRecusada) as cm:
            decidir(d, [pedido(B05, "REVOGADO")])
        self.assertEqual(cm.exception.codigo, "NADA_A_REVOGAR")
        self.assertEqual(len(d["eventos"]), 1)

    def test_sup_30_nenhum_lancamento_contabil(self):
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "sol" / "supervisor-conciliacao" / "decisoes.json"
            dcs.decidir_e_gravar(arq, CTX, CONC, [pedido(x) for x in PROV], origem="LOTE", revisao_conciliacao_cliente=dcs.revisao_conciliacao(CONC),
                                 revisao_decisoes_cliente="RD-INICIAL", justificativa=JUST)
            self.assertEqual([p.relative_to(tmp).as_posix() for p in Path(tmp).rglob("*") if p.is_file()], ["sol/supervisor-conciliacao/decisoes.json"])
            self.assertFalse(any(e["lancamento_contabil"] for e in json.loads(arq.read_text(encoding="utf-8"))["eventos"]))
        _, dados, _ = decisao_financeiro()
        r0, r1 = conferir_com(), conferir_com(dados)
        self.assertEqual(set(r1), set(r0))                                 # nenhum campo novo de lançamento/proposta no Financeiro
        self.assertFalse([k for k in r1 if "lancament" in k.lower()])
        self.assertEqual(r1["bloqueio_lote"], [])                          # só o bloqueio de associação muda; nada é escriturado


class PoliticaV1(unittest.TestCase):
    """CONCILIACAO_FINANCEIRA_POLITICA_V1 idêntica à publicada em v1.6.0-interno (arquivo e parâmetros)."""
    SHA_ARQUIVO_V160 = "bb9fda04a3fe8553007176c9b1c5b24f657e8d0a393e65b8bc27f3f83d20baec"
    SHA_PARAMETROS_V160 = "af71f4e29a0df338b7c08a0cb587ec17db59eef8ecbd18ecd90595100515768c"

    def test_pol_01_arquivo_do_motor_identico_ao_publicado(self):
        arq = RAIZ / "AGENTES/FINANCEIRO/ferramentas/conciliador_financeiro.py"
        self.assertEqual(hashlib.sha256(arq.read_bytes()).hexdigest(), self.SHA_ARQUIVO_V160)

    def test_pol_02_parametros_identicos(self):
        p = {"janela": cf.JANELA_DIAS, "grupo": cf.LIMITE_GRUPO, "cand": cf.LIMITE_CANDIDATOS_GRUPO, "tol": str(cf.TOLERANCIA),
             "nat": cf.NATUREZA_COMPATIVEL, "fortes": list(cf.FORTES), "todas": list(cf.TODAS), "pesos": cf.PESOS,
             "gen": sorted(cf.GENERICAS), "suf": sorted(cf.SUFIXOS), "pol": cf.POLITICA, "contrato": cf.CONTRATO, "versao": cf.VERSAO}
        self.assertEqual(hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest(), self.SHA_PARAMETROS_V160)
        self.assertEqual((cf.POLITICA, cf.JANELA_DIAS, cf.LIMITE_GRUPO, cf.LIMITE_CANDIDATOS_GRUPO), ("CONCILIACAO_FINANCEIRA_POLITICA_V1", 2, 3, 12))

    def test_pol_03_igual_a_tag_quando_git_disponivel(self):
        try:
            p = subprocess.run(["git", "show", "v1.6.0-interno:AGENTES/FINANCEIRO/ferramentas/conciliador_financeiro.py"], cwd=RAIZ,
                               capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            self.skipTest("git indisponível")
        if p.returncode != 0:
            self.skipTest("tag v1.6.0-interno indisponível neste clone")
        self.assertEqual(hashlib.sha256(p.stdout).hexdigest(), self.SHA_ARQUIVO_V160)


if __name__ == "__main__":
    unittest.main(verbosity=2)
