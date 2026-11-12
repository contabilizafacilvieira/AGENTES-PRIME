"""Classificação HISTÓRICA × VIGENTE no pacote efetivo da tentativa (CLASS-SNAPSHOT-01..10). Dados 100% FICTÍCIOS.

O defeito reproduzido: o manifesto histórico da SOL guarda um rótulo antigo de EXTRATO para um comprovante (classificador anterior).
Uma nova tentativa deve usar a classificação VIGENTE (regras atuais sobre a mesma leitura e o mesmo SHA), registrar a histórica
ao lado e nunca herdar o rótulo antigo; ambíguo ou erro → fail-closed. O passado não é reescrito.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/API/testar_classificacao_snapshot.py
"""
import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(RAIZ / "TESTES"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import ambiente_isolado as ai  # noqa: E402
AMB = ai.criar("prime-class-snapshot-")
os.environ["AGENTES_PRIME_DEMO_CONCILIACAO"] = str(AMB.raiz / "demonstracao-conciliacao")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import complementos  # noqa: E402
import documentos_local  # noqa: E402
import reprocessamento as rp  # noqa: E402
import cenario_complementar as cc  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

ROTULO_ANTIGO = "Extrato PDF Santander Empresas (leitura pelo Financeiro)"
resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:400]))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def plantar_rotulo_historico(sol):
    """Simula o HISTÓRICO real: o classificador antigo rotulou o comprovante como extrato no manifesto e na triagem."""
    E = servidor.RUNTIME / "execucoes" / sol
    m = json.loads((E / "documentos-local.json").read_text(encoding="utf-8"))
    for i in m["itens"]:
        if i["arquivo"].endswith("pagamentos-lote.pdf"):
            i["roteamento_anterior"] = {"tipo": ROTULO_ANTIGO}
            i["tipo"] = ROTULO_ANTIGO
            i["encaminhamento"] = dict(i["encaminhamento"], tipo=ROTULO_ANTIGO, area="FINANCEIRO")
    (E / "documentos-local.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    reg = ai.registro_isolado()
    s = reg["solicitacoes"][sol]
    s["triagem_documentos"] = [dict(x, tipo=ROTULO_ANTIGO) if x["arquivo"].endswith("pagamentos-lote.pdf") else x for x in s["triagem_documentos"]]
    s["ancora_documentos"]["manifesto_sha256"] = sha(E / "documentos-local.json")
    AMB.registro.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")


def doc(t, sufixo):
    return next(d for d in t["manifesto_efetivo"]["documentos"] if d["arquivo"].endswith(sufixo))


def bateria(c):
    R = servidor.RUNTIME
    sol, _ = c.abrir_sol([("relatorio-financeiro.xlsx", cc.relatorio_xlsx()), ("pagamentos-lote.pdf", cc.pagfor_pdf())])
    assert cc.ocioso(servidor, ai.registro_isolado)
    E = R / "execucoes" / sol
    plantar_rotulo_historico(sol)
    manifesto_hist = (E / "documentos-local.json").read_bytes()
    pasta_orig = AMB.clientes / cc.EMPRESA / ai.registro_isolado()["solicitacoes"][sol]["pasta"]
    shas_orig = {p.name: sha(p) for p in pasta_orig.iterdir()}
    lote = c.complementar(sol, "documento-recebido.pdf", cc.extrato_pdf())
    assert c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote}/concluir", {"confirmado": True})[0] == 201
    lote_n = c.complementar(sol, "extrato-consolidado.pdf", cc.pagfor_pdf("OUTRA VIA FICTICIA"), motivo="Comprovante com nome enganoso (fictício).")
    assert c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_n}/concluir", {"confirmado": True})[0] == 201

    # ---------------- CLASS-03/04: fail-closed (nenhuma tentativa, nenhum pacote) — antes da tentativa válida
    with patch.object(documentos_local, "avaliar_extrato", side_effect=lambda a, texto=None: {"decisao": "AMBIGUO", "evidencias": [],
                                                                                              "contra_evidencias": ["BENEFICIARIO", "PAGADOR"]}):
        s3, r3 = c.j("POST", f"/api/solicitacoes/{sol}/reprocessar", {"confirmado": True, "motivo": "Teste ambíguo (fictício).", "solicitante": "Supervisor"})
    registrar("CLASS-SNAPSHOT-03 classificação vigente ambígua → fail-closed (sem tentativa, sem pacote)",
              s3 == 409 and "AMBIGUO" in " ".join(r3.get("motivos", [])) and rp.listar(R, sol) == [] and not (E / "tentativas").exists(), (s3, r3))
    with patch.object(documentos_local, "classificar", side_effect=RuntimeError("falha simulada do classificador")):
        s4, r4 = c.j("POST", f"/api/solicitacoes/{sol}/reprocessar", {"confirmado": True, "motivo": "Teste falha (fictício).", "solicitante": "Supervisor"})
    registrar("CLASS-SNAPSHOT-04 classificador falha → não herda o rótulo histórico (sem tentativa)",
              s4 == 409 and "não é herdado" in " ".join(r4.get("motivos", [])) and rp.listar(R, sol) == [] and not (E / "tentativas").exists(), (s4, r4))

    # ---------------- tentativa válida
    s, rt = c.j("POST", f"/api/solicitacoes/{sol}/reprocessar", {"confirmado": True, "motivo": "Reprocessar com extrato complementar (fictício).", "solicitante": "Supervisor"})
    assert s == 201, rt
    t1 = rt["tentativa"]
    pacote = json.loads((E / "tentativas" / "0001" / "pacote" / "documentos-local.json").read_text(encoding="utf-8"))
    item_pf = next(i for i in pacote["itens"] if i["arquivo"].endswith("pagamentos-lote.pdf"))
    pf = doc(t1, "pagamentos-lote.pdf")
    s, rr = c.j("POST", f"/api/solicitacoes/{sol}/retomar-rota-financeira", {"justificativa": "Executar tentativa fictícia.", "confirmado": True})
    assert s == 202, rr
    assert cc.ocioso(servidor, ai.registro_isolado)
    fin = sorted(E.glob("financeiro-*"), key=lambda p: int(p.name.split("-")[1]))[-1]
    rf = json.loads((fin / "resultado.json").read_text(encoding="utf-8"))
    fontes = json.dumps(rf["fonte_bancaria"], ensure_ascii=False)
    tri = {x["arquivo"].rsplit("/", 1)[-1]: x for x in ai.registro_isolado()["solicitacoes"][sol]["triagem_documentos"]}
    registrar("CLASS-SNAPSHOT-01 histórico EXTRATO × vigente NAO_EXTRATO: snapshot registra os dois; roteamento vigente e Financeiro não tratam como extrato",
              (E / "documentos-local.json").read_bytes() == manifesto_hist
              and pf["classificacao_historica"]["tipo"] == ROTULO_ANTIGO and pf["classificacao_vigente"]["decisao_extrato"] == "NAO_EXTRATO"
              and not pf["tipo"].startswith("Extrato") and pf["divergencia_historica"] is True
              and not item_pf["tipo"].startswith("Extrato") and not tri["01_pagamentos-lote.pdf" if "01_pagamentos-lote.pdf" in tri else "02_pagamentos-lote.pdf"]["tipo"].startswith("Extrato")
              and rf["fonte_bancaria"]["extratos_recebidos"] == 1 and "pagamentos-lote" not in fontes,
              (pf.get("classificacao_historica"), pf.get("classificacao_vigente"), rf["fonte_bancaria"]["extratos_recebidos"]))
    rel = doc(t1, "relatorio-financeiro.xlsx")
    registrar("CLASS-SNAPSHOT-02 histórico e vigente iguais → fluxo normal", rel["divergencia_historica"] is False
              and rel["tipo"] == "Relatório financeiro de lançamentos" and rf["fonte_auxiliar_financeira"]["resumo"]["movimentos"] == 5, rel.get("tipo"))
    registrar("CLASS-SNAPSHOT-05 SHA dos originais idêntico (e igual no snapshot)", {p.name: sha(p) for p in pasta_orig.iterdir()} == shas_orig
              and pf["sha256"] == shas_orig[next(n for n in shas_orig if n.endswith("pagamentos-lote.pdf"))])
    registrar("CLASS-SNAPSHOT-06 manifesto histórico byte a byte intacto (após criar e executar a tentativa)", (E / "documentos-local.json").read_bytes() == manifesto_hist)
    arq_t1 = (E / "tentativas" / "0001" / "tentativa.json").read_bytes()
    lote_tarde = c.complementar(sol, "comprovante.pdf", cc.comprovante_pdf())
    c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_tarde}/concluir", {"confirmado": True})
    s, rt2 = c.j("POST", f"/api/solicitacoes/{sol}/reprocessar", {"confirmado": True, "motivo": "Segunda tentativa fictícia.", "solicitante": "Supervisor"})
    t1d = json.loads((E / "tentativas" / "0001" / "tentativa.json").read_text(encoding="utf-8"))
    registrar("CLASS-SNAPSHOT-07 tentativa histórica intacta (snapshot e classificação congelados)", s == 201
              and t1d["manifesto_efetivo"] == json.loads(arq_t1)["manifesto_efetivo"] and t1d["manifesto_efetivo_sha256"] == t1["manifesto_efetivo_sha256"])
    registrar("CLASS-SNAPSHOT-08 nova tentativa registra versão e evidências da classificação vigente",
              pf["classificacao_vigente"]["classificador"].startswith("documentos_local@") and pacote["classificacao"]["classificador"] == pf["classificacao_vigente"]["classificador"]
              and item_pf["classificacao_vigente"]["contra_evidencias"] and doc(t1, "documento-recebido.pdf")["classificacao_vigente"]["decisao_extrato"] == "EXTRATO",
              item_pf["classificacao_vigente"].get("contra_evidencias"))
    enganoso = doc(t1, "extrato-consolidado.pdf")
    neutro = doc(t1, "documento-recebido.pdf")
    registrar("CLASS-SNAPSHOT-09 nome do arquivo não determina a classificação", not enganoso["tipo"].startswith("Extrato")
              and enganoso["classificacao_vigente"]["decisao_extrato"] == "NAO_EXTRATO" and neutro["tipo"].startswith("Extrato"),
              (enganoso["tipo"], neutro["tipo"]))
    registrar("CLASS-SNAPSHOT-10 complementar já classificado corretamente continua correto (sem divergência)",
              neutro["divergencia_historica"] is False and neutro["classificacao_historica"]["tipo"] == neutro["tipo"] == "Extrato bancário PDF (leitura pelo Financeiro)",
              (neutro["classificacao_historica"], neutro["tipo"]))


def main():
    antes = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cc.preparar_empresa(servidor, servidor.RUNTIME)
        bateria(cc.Cliente(srv.server_port))
    except Exception as exc:  # noqa: BLE001
        import traceback
        registrar("CLASS-SNAPSHOT-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-600:]}")
    finally:
        srv.shutdown()
        srv.server_close()
    registrar("CLASS-SNAPSHOT-99 ambiente operacional intocado", foto_operacional() == antes)
    falhas = 0
    for caso, ok, d in resultados:
        falhas += not ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {caso}" + ("" if ok else f"  → {d}"))
    print(f"TOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
