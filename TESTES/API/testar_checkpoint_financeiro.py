"""Checkpoint após o Financeiro (CHECK-FIN-01..20) e proteção da retomada de rota (ROTA-SEG-01..15). Dados 100% FICTÍCIOS.

Servidor REAL em ambiente ISOLADO (cenario_complementar). Conclusão técnica do Financeiro ≠ autorização para Contabilidade/Bancos:
com parar_apos_financeiro a SOL para, a tentativa fica PAUSADA e só a continuação autorizada executa Bancos (uma vez, mesma tentativa).

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/API/testar_checkpoint_financeiro.py
"""
import hashlib
import json
import os
import sys
import threading
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(RAIZ / "TESTES"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import ambiente_isolado as ai  # noqa: E402
AMB = ai.criar("prime-checkpoint-")
os.environ["AGENTES_PRIME_DEMO_CONCILIACAO"] = str(AMB.raiz / "demonstracao-conciliacao")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import reprocessamento as rp  # noqa: E402
import cenario_complementar as cc  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:400]))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def arvore(p):
    p = Path(p)
    return {x.relative_to(p).as_posix(): sha(x) for x in p.rglob("*") if x.is_file()} if p.exists() else {}


def reg(sol):
    return ai.registro_isolado()["solicitacoes"][sol]


def pastas(sol, prefixo):
    return sorted(p.name for p in (servidor.RUNTIME / "execucoes" / sol).glob(f"{prefixo}-*"))


class Cenario:
    def __init__(self, c, identificado=True):
        self.c = c
        self.sol, _ = c.abrir_sol([("relatorio.xlsx", cc.relatorio_xlsx())])
        assert cc.ocioso(servidor, ai.registro_isolado)
        lote = c.complementar(self.sol, "documento.pdf", cc.extrato_identificado_pdf() if identificado else cc.extrato_pdf())
        assert c.j("POST", f"/api/solicitacoes/{self.sol}/complementos/{lote}/concluir", {"confirmado": True})[0] == 201
        self.E = servidor.RUNTIME / "execucoes" / self.sol

    def reprocessar(self, motivo="Reprocessamento fictício."):
        return self.c.j("POST", f"/api/solicitacoes/{self.sol}/reprocessar", {"confirmado": True, "motivo": motivo, "solicitante": "Supervisor"})

    def retomar(self, parar=None, esperar=True):
        corpo = {"justificativa": "Execução fictícia da rota financeira.", "confirmado": True}
        if parar is not None:
            corpo["parar_apos_financeiro"] = parar
        r = self.c.j("POST", f"/api/solicitacoes/{self.sol}/retomar-rota-financeira", corpo)
        if esperar:
            assert cc.ocioso(servidor, ai.registro_isolado)
        return r

    def continuar(self, esperar=True):
        r = self.c.j("POST", f"/api/solicitacoes/{self.sol}/continuar-apos-financeiro", {"justificativa": "Autorizo a continuação (fictício).", "confirmado": True})
        if esperar:
            assert cc.ocioso(servidor, ai.registro_isolado)
        return r

    def tentativa(self):
        return rp.listar(servidor.RUNTIME, self.sol)[-1]

    def foto(self):
        return {"registro": json.dumps(reg(self.sol), sort_keys=True), "runtime": arvore(self.E),
                "clientes": arvore(AMB.clientes / cc.EMPRESA)}


def bateria(c):
    # ---------------- cenário A: Financeiro sem bloqueio + checkpoint
    a = Cenario(c)
    assert a.reprocessar()[0] == 201
    docs_antes = arvore(AMB.clientes / cc.EMPRESA)
    pacote_antes = arvore(a.E / "tentativas" / "0001" / "pacote")
    s, r = a.retomar(parar=True)
    sa, t = reg(a.sol), a.tentativa()
    fin = json.loads((a.E / "financeiro-2" / "resultado.json").read_text(encoding="utf-8"))
    registrar("CHECK-FIN-02 Financeiro aprovado + checkpoint: Bancos NÃO executa", s == 202 and fin["bloqueio_lote"] == [] and pastas(a.sol, "bancos") == [],
              (s, fin["bloqueio_lote"], pastas(a.sol, "bancos")))
    registrar("CHECK-FIN-03 nenhum CSV de propostas gerado", not [p for p in a.E.rglob("*.csv")])
    registrar("CHECK-FIN-04 Conciliação posterior NÃO executa", pastas(a.sol, "conciliacao") == ["conciliacao-1"]
              and {p["etapa"]: p["situacao"] for p in sa["plano_etapas"]}["CONCILIACAO"] == "PENDENTE")
    registrar("CHECK-FIN-05 SOL aguardando Supervisor", sa["estado"] == "AGUARDANDO_SUPERVISOR" and sa["etapa"] == "FINANCEIRO_CONCLUIDO_AGUARDANDO_AUTORIZACAO")
    s_novo, r_novo = a.reprocessar("Tentar criar outra (fictício).")
    registrar("CHECK-FIN-06 tentativa fica PAUSADA, ativa e retomável (não finalizada, não falha; nova tentativa recusada)",
              t["status"] == "PAUSADA" and rp.ativa(servidor.RUNTIME, a.sol)["numero"] == t["numero"] and s_novo == 409, (t["status"], s_novo))
    ck = sa["checkpoint"]
    registrar("CHECK-FIN-07 execução do Financeiro auditada (tentativa, registro, evento, checkpoint)",
              [x["execucao"] for x in t["execucoes"]] == ["financeiro-2"] and ck["resultado_financeiro_sha256"] == sha(a.E / "financeiro-2" / "resultado.json")
              and all(ck.get(k) for k in ("solicitado_em", "atingido_em", "origem", "solicitante", "motivo")) and ck["tentativa"] == t["numero"]
              and any("aguardando autorização do Supervisor para Contabilidade/Bancos" in e["evento"] for e in sa["eventos"])
              and t["checkpoint"]["situacao"] == "AGUARDANDO_AUTORIZACAO", ck)
    registrar("CHECK-FIN-08 próxima etapa registrada: Contabilidade/Bancos aguardando autorização",
              ck["proxima_etapa"] == "BANCOS" and {p["etapa"]: p["situacao"] for p in sa["plano_etapas"]}["BANCOS"] == "PENDENTE"
              and sa["tarefas_areas"]["CONTABILIDADE"]["estado"] == "AGUARDANDO_AUTORIZACAO_SUPERVISOR")
    s, det = c.j("GET", f"/api/solicitacoes/{a.sol}")
    registrar("CHECK-FIN-09/10 tela recebe o checkpoint (Financeiro concluído, próxima etapa aguardando autorização)",
              s == 200 and det["checkpoint"]["situacao"] == "AGUARDANDO_AUTORIZACAO" and det["checkpoint"]["proxima_etapa"] == "BANCOS"
              and next(x for x in det["tentativas"] if x["numero"] == t["numero"])["status"] == "PAUSADA")
    registrar("CHECK-FIN-13 checkpoint não altera documentos nem o pacote", arvore(AMB.clientes / cc.EMPRESA) == docs_antes
              and arvore(a.E / "tentativas" / "0001" / "pacote") == pacote_antes)
    registrar("CHECK-FIN-20 nenhuma Contabilidade antes da autorização", not pastas(a.sol, "bancos") and not reg(a.sol).get("bancos"))
    s19, r19 = a.retomar(parar=True, esperar=False)
    s_cedo = c.j("POST", "/api/solicitacoes/" + a.sol + "/continuar-apos-financeiro", {"justificativa": "x", "confirmado": True})[0]
    # continuação: concorrência (duas chamadas simultâneas) → exatamente uma aceita
    respostas = []
    th = [threading.Thread(target=lambda: respostas.append(a.continuar(esperar=False)[0])) for _ in range(2)]
    [x.start() for x in th]
    [x.join() for x in th]
    assert cc.ocioso(servidor, ai.registro_isolado)
    t2, sa2 = a.tentativa(), reg(a.sol)
    registrar("CHECK-FIN-18 continuação concorrente: só uma aceita, Bancos uma única vez", sorted(respostas) == [202, 409] and pastas(a.sol, "bancos") == ["bancos-1"],
              (respostas, pastas(a.sol, "bancos")))
    registrar("CHECK-FIN-11 continuar não repete o Financeiro", pastas(a.sol, "financeiro") == ["financeiro-1", "financeiro-2"])
    registrar("CHECK-FIN-12 continuar usa a MESMA tentativa (que então conclui)", t2["numero"] == t["numero"] and t2["status"] in ("CONCLUIDA", "BLOQUEADA")
              and [x["execucao"] for x in t2["execucoes"]] == ["financeiro-2", "bancos-1", "conciliacao-2"], (t2["status"], t2["execucoes"]))
    s_rep = a.continuar()[0]
    registrar("CHECK-FIN-19 checkpoint repetido é fail-closed (retomar no checkpoint, continuar 2x, continuar com justificativa inválida)",
              s19 == 409 and r19.get("codigo") == "CHECKPOINT_PENDENTE" and s_cedo == 409 and s_rep == 409 and sa2.get("checkpoint") is None
              and sa2["checkpoints"][-1]["situacao"] == "AUTORIZADO", (s19, s_cedo, s_rep))

    # ---------------- cenário B: Financeiro BLOQUEADO com checkpoint pedido → comportamento normal de bloqueio
    b = Cenario(c, identificado=False)
    b.reprocessar()
    b.retomar(parar=True)
    sb, tb = reg(b.sol), b.tentativa()
    registrar("CHECK-FIN-01 Financeiro bloqueado para normalmente (tentativa BLOQUEADA, sem pausa, sem Bancos)",
              tb["status"] == "BLOQUEADA" and sb.get("checkpoint") is None and sb["checkpoints"][-1]["situacao"] == "ENCERRADO_FINANCEIRO_BLOQUEADO"
              and not pastas(b.sol, "bancos") and {p["etapa"]: p["situacao"] for p in sb["plano_etapas"]}["FINANCEIRO"] == "BLOQUEADA", tb["status"])
    # decisões reais da Central entram na nova tentativa; checkpoint não as altera; suporte preservado
    s, v = c.j("GET", f"/api/solicitacoes/{b.sol}/conciliacao-financeira")
    prov = [i["id"] for i in v["itens"] if i["status"] == "REVISAR"]
    s_lote, _ = c.j("POST", f"/api/solicitacoes/{b.sol}/conciliacao-financeira/decisoes-lote",
                    {"associacoes": prov, "justificativa": "Conferi os prováveis fictícios.", "revisao_conciliacao": v["revisao_conciliacao"], "revisao_decisoes": v["revisao_decisoes"]})
    dec = b.E / "supervisor-conciliacao" / "decisoes.json"
    dec_antes = sha(dec)
    fin_bloq = json.loads((b.E / pastas(b.sol, "financeiro")[-1] / "resultado.json").read_text(encoding="utf-8"))
    assert b.reprocessar()[0] == 201
    b.retomar(parar=True)
    fin_ck = json.loads((b.E / sorted(pastas(b.sol, "financeiro"), key=lambda n: int(n.split("-")[1]))[-1] / "resultado.json").read_text(encoding="utf-8"))
    registrar("CHECK-FIN-14 checkpoint não altera as decisões da conciliação (e elas liberam o Financeiro da nova tentativa)",
              s_lote == 201 and sha(dec) == dec_antes and fin_ck["bloqueio_lote"] == [] and reg(b.sol)["checkpoint"]["situacao"] == "AGUARDANDO_AUTORIZACAO",
              (s_lote, fin_ck["bloqueio_lote"][:1]))
    registrar("CHECK-FIN-15 checkpoint preserva a situação de suporte dos movimentos",
              Counter(m["situacao"] for m in fin_ck["movimentos"]) == Counter(m["situacao"] for m in fin_bloq["movimentos"]),
              (Counter(m["situacao"] for m in fin_ck["movimentos"]), Counter(m["situacao"] for m in fin_bloq["movimentos"])))

    # ---------------- cenário C: sem checkpoint, fluxo legado contínuo (compatibilidade)
    d = Cenario(c)
    d.reprocessar()
    d.retomar()                                                     # sem parar_apos_financeiro
    registrar("CHECK-FIN-16 sem checkpoint, fluxo legado continua (Financeiro → Bancos → Conciliação na mesma rodada)",
              pastas(d.sol, "bancos") == ["bancos-1"] and d.tentativa()["status"] in ("CONCLUIDA", "BLOQUEADA") and reg(d.sol).get("checkpoint") is None)

    # ---------------- cenário E: duplo clique ao iniciar
    e = Cenario(c)
    e.reprocessar()
    rs = []
    th = [threading.Thread(target=lambda: rs.append(e.retomar(parar=True, esperar=False)[0])) for _ in range(2)]
    [x.start() for x in th]
    [x.join() for x in th]
    assert cc.ocioso(servidor, ai.registro_isolado)
    registrar("CHECK-FIN-17 duplo clique / chamada duplicada não duplica execução", sorted(rs) == [202, 409] and pastas(e.sol, "financeiro") == ["financeiro-1", "financeiro-2"]
              and e.tentativa()["status"] == "PAUSADA", (rs, pastas(e.sol, "financeiro")))

    # ---------------- ROTA-SEG
    f1 = Cenario(c)
    registrar("ROTA-SEG-01 SOL sem tentativa nem pacote: primeira retomada válida segue", f1.retomar()[0] == 202)
    f2 = Cenario(c)
    f2.reprocessar()
    registrar("ROTA-SEG-02 tentativa recém-criada pode iniciar", f2.retomar(parar=True)[0] == 202 and f2.tentativa()["status"] == "PAUSADA")
    registrar("ROTA-SEG-04 tentativa pausada no checkpoint pode continuar", f2.continuar()[0] == 202 and pastas(f2.sol, "bancos") == ["bancos-1"])
    # f2 agora: ancorada no pacote da tentativa 1, finalizada, sem tentativa ativa → caminho perigoso
    antes = f2.foto()
    man_hist = (f2.E / "documentos-local.json").read_bytes()
    ancora = json.dumps(reg(f2.sol)["ancora_documentos"], sort_keys=True)
    controle = AMB.registro.read_bytes()
    s5, r5 = f2.retomar(parar=False, esperar=False)
    s5b, r5b = f2.retomar(parar=True, esperar=False)
    registrar("ROTA-SEG-05 tentativa finalizada sem ativa: retomada direta RECUSADA", s5 == 409 and r5.get("codigo") == "TENTATIVA_FINALIZADA"
              and s5b == 409, (s5, r5))
    depois = f2.foto()
    registrar("ROTA-SEG-06 recusa antes de qualquer escrita (runtime da SOL idêntico)", depois["runtime"] == antes["runtime"])
    registrar("ROTA-SEG-07 âncora idêntica após a recusa", json.dumps(reg(f2.sol)["ancora_documentos"], sort_keys=True) == ancora)
    registrar("ROTA-SEG-08 manifesto (pacote vigente) idêntico", arvore(f2.E / "tentativas") == {k[len("tentativas/"):]: v for k, v in antes["runtime"].items() if k.startswith("tentativas/")})
    registrar("ROTA-SEG-09 registro histórico de documentos idêntico", (f2.E / "documentos-local.json").read_bytes() == man_hist)
    registrar("ROTA-SEG-10 Coordenador idêntico", AMB.registro.read_bytes() == controle and depois["registro"] == antes["registro"])
    registrar("ROTA-SEG-11 mensagem orienta criar nova tentativa", r5.get("erro") == servidor.MSG_TENTATIVA_FINALIZADA)
    s12a = c.j("POST", f"/api/solicitacoes/{f2.sol}/retomar-rota-financeira", {"justificativa": "Direto.", "confirmado": True, "tentativa": 1})[0]
    s12b = c.j("POST", f"/api/solicitacoes/{f2.sol}/areas/FINANCEIRO/retomar", {"justificativa": "Contornar.", "confirmado": True})[0]
    s12c = c.j("POST", f"/api/solicitacoes/{f2.sol}/continuar-apos-financeiro", {"justificativa": "Contornar.", "confirmado": True})[0]
    registrar("ROTA-SEG-12 API não permite contornar (campo extra, retomada de etapa, continuação sem checkpoint)", (s12a, s12b, s12c) == (400, 409, 409)
              and f2.foto()["runtime"] == antes["runtime"], (s12a, s12b, s12c))
    js = (RAIZ / "ESCRITORIO-VIRTUAL" / "js" / "sol-documentos.js").read_text(encoding="utf-8")
    op = (RAIZ / "ESCRITORIO-VIRTUAL" / "js" / "operacao.js").read_text(encoding="utf-8")
    registrar("ROTA-SEG-13 interface usa o caminho oficial (retomada só após criar/ter tentativa; parada marcada por padrão)",
              "retomar-rota-financeira" not in op and js.count("/retomar-rota-financeira`") == 1 and "cb.checked = true" in js
              and "parar_apos_financeiro" in js)
    s14, r14 = f2.reprocessar("Nova tentativa depois da finalizada (fictício).")
    registrar("ROTA-SEG-14 reprocessamento oficial continua funcionando (nova tentativa)", s14 == 201 and r14["tentativa"]["numero"] == 2)
    s15, _ = f2.retomar(parar=True)
    registrar("ROTA-SEG-15 retomada legítima com a nova tentativa funciona e reancora o pacote novo", s15 == 202
              and reg(f2.sol)["ancora_documentos"].get("tentativa") == 2 and f2.tentativa()["status"] == "PAUSADA")
    f3 = Cenario(c)
    f3.reprocessar()
    f3.retomar()                                                    # t1 finalizada (legado contínuo)
    f3.reprocessar("Segunda tentativa (fictício).")
    registrar("ROTA-SEG-03 tentativa ativa (nova, após uma finalizada) pode seguir", f3.retomar(parar=True)[0] == 202 and f3.tentativa()["numero"] == 2)


def main():
    antes = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cc.preparar_empresa(servidor, servidor.RUNTIME)
        bateria(cc.Cliente(srv.server_port))
    except Exception as exc:  # noqa: BLE001
        import traceback
        registrar("CHECK-FIN-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-700:]}")
    finally:
        srv.shutdown()
        srv.server_close()
    registrar("CHECK-FIN-99 ambiente operacional intocado", foto_operacional() == antes)
    falhas = 0
    for caso, ok, d in sorted(resultados, key=lambda x: x[0]):
        falhas += not ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {caso}" + ("" if ok else f"  → {d}"))
    print(f"TOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
