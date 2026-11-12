"""ISOLAMENTO MULTIEMPRESA (MULTI-01..15 + MULTI-ISO). Duas empresas FICTÍCIAS (A e B), MESMA competência, mesmos bancos/valores/
fornecedores, fechamentos completos simultâneos. Servidor REAL em ambiente ISOLADO.

A empresa é isolamento RÍGIDO: documento, regra, consulta entre departamentos, balancete, decisão, tentativa, pendência e falha de uma
empresa nunca aparecem nem atuam na outra. Adapter (tradução de formato) é compartilhado; dados e regras não.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/API/testar_multiempresa.py
"""
import copy
import hashlib
import json
import sys
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(RAIZ / "TESTES"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import ambiente_isolado as ai  # noqa: E402
AMB = ai.criar("prime-multiempresa-")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import amostra_ficticia  # noqa: E402
import adaptadores_fechamento as af  # noqa: E402
import intercambio as ic  # noqa: E402
import reprocessamento as rp  # noqa: E402
import cenario_complementar as cc  # noqa: E402
import cenario_fechamento as cf  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:400]))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def reg(sol):
    return ai.registro_isolado()["solicitacoes"][sol]


def estavel(p):
    """Prévia sem o horário de geração (para comparar antes × depois)."""
    p = copy.deepcopy(p)
    p.pop("gerada_em", None)
    return json.dumps(p, sort_keys=True, ensure_ascii=False)


def main():
    foto = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c = cc.Cliente(srv.server_address[1])
    espera = lambda: cc.ocioso(servidor, ai.registro_isolado)  # noqa: E731
    previa = lambda sol: c.j("GET", f"/api/solicitacoes/{sol}/previa-fechamento")[1]  # noqa: E731
    CL = servidor.coordenador.CLIENTES
    contexto = lambda sol: ic.contexto(servidor.RUNTIME, CL, ai.registro_isolado()["solicitacoes"], sol)  # noqa: E731
    try:
        amostra_ficticia.preparar(servidor.RUNTIME)
        solA = cf.abrir_fechamento(c, cf.A, cf.documentos("A"))
        espera()
        solB = cf.abrir_fechamento(c, cf.B, cf.documentos("B"))
        espera()
        assert cf.preparar_fechamento(c, solA)[0] == 202
        espera()
        assert cf.preparar_fechamento(c, solB)[0] == 202
        espera()
        regB_ck = json.dumps(reg(solB), sort_keys=True)
        tentB = json.dumps(rp.listar(servidor.RUNTIME, solB), sort_keys=True)
        st, _ = c.j("POST", f"/api/solicitacoes/{solA}/continuar-apos-financeiro", {"justificativa": "Autorizo a empresa A (fictício).", "confirmado": True})
        espera()
        registrar("MULTI-06 decisão do Supervisor na empresa A (autorizar checkpoint) não afeta B: B continua aguardando, registro idêntico",
                  st == 202 and json.dumps(reg(solB), sort_keys=True) == regB_ck and reg(solB)["checkpoint"]["situacao"] == "AGUARDANDO_AUTORIZACAO"
                  and reg(solA).get("checkpoints"), reg(solB)["checkpoint"]["situacao"])
        registrar("MULTI-07 tentativa da empresa A (continuada e concluída) não altera as tentativas de B",
                  json.dumps(rp.listar(servidor.RUNTIME, solB), sort_keys=True) == tentB
                  and rp.listar(servidor.RUNTIME, solB)[-1]["status"] == "PAUSADA" and rp.listar(servidor.RUNTIME, solA)[-1]["status"] == "CONCLUIDA", "")
        c.j("POST", f"/api/solicitacoes/{solB}/continuar-apos-financeiro", {"justificativa": "Autorizo a empresa B (fictício).", "confirmado": True})
        espera()
        pA, pB = previa(solA), previa(solB)
        sA, sB = reg(solA), reg(solB)

        docsA = {d["arquivo"] for d in pA["documentos"]["itens"]}
        docsB = {d["arquivo"] for d in pB["documentos"]["itens"]}
        shaA = {d["sha256"] for d in pA["documentos"]["itens"]}
        manB = json.loads((servidor.RUNTIME / "execucoes" / solB / "documentos-local.json").read_text(encoding="utf-8"))
        registrar("MULTI-01 documento da empresa A não aparece em B (prévia, pacote e pasta de documentos de B)",
                  docsA and docsB and not docsA & docsB and all(x.startswith(sB["pasta"]) for x in docsB)
                  and not any(i["arquivo"] in docsA for i in manB["itens"]) and not any((CL / cf.B / x).exists() for x in docsA), len(docsB))
        antesB = estavel(previa(solB))
        (CL / cf.A / "REGRAS-INTERCAMBIO.json").write_text(json.dumps({"contrato": "REGRAS_INTERCAMBIO_V1", "empresa": cf.A, "situacao": "APROVADA",
                                                                      "janela_meses": 1}), encoding="utf-8")
        registrar("MULTI-02 regra aprovada da empresa A (janela de intercâmbio) não afeta B: política de B continua padrão e a prévia de B "
                  "é idêntica", ic.politica_temporal(CL, cf.A)["janela_meses"] == 1 and ic.politica_temporal(CL, cf.B)["janela_meses"] == 0
                  and estavel(previa(solB)) == antesB, "")
        ctxA, ctxB = contexto(solA), contexto(solB)
        fisA = [it for it in ctxA["itens"] if it["proveniencia"]["departamento"] == "FISCAL"]
        fxA = ic.analisar_financeiro(ctxA)
        candA = [x for m in fxA["movimentos"] for x in m["candidatos"]]
        registrar("MULTI-03 Financeiro de A consulta SOMENTE o Fiscal de A (B tem as mesmas NFs 102/103 e a mesma guia; nenhuma aparece em A)",
                  fisA and all(it["proveniencia"]["empresa"] == cf.A and it["proveniencia"]["sol"] == solA for it in fisA)
                  and candA and all(x["proveniencia"]["empresa"] == cf.A and x["proveniencia"]["sol"] == solA for x in candA), len(candA))
        dpA = [it for it in ctxA["itens"] if it["proveniencia"]["departamento"] == "DP"]
        dpB = [it for it in ctxB["itens"] if it["proveniencia"]["departamento"] == "DP"]
        sal = lambda fx: next(m for m in fx["movimentos"] if m["descricao"].startswith("PAGTO SALARIOS"))  # noqa: E731
        registrar("MULTI-04 Financeiro de A consulta SOMENTE o DP de A (B tem folha com os MESMOS valores; nenhum documento/obrigação de B em A)",
                  dpA and dpB and all(it["proveniencia"]["sol"] == solA for it in dpA)
                  and not {it["proveniencia"]["sha256"] for it in dpA} & {it["proveniencia"]["sha256"] for it in dpB}
                  and sorted(it.get("total") for it in dpA) == sorted(it.get("total") for it in dpB)
                  and all(x["proveniencia"]["sol"] == solA for x in sal(fxA)["candidatos"]) and sal(fxA)["candidatos"],
                  sorted(it.get("total") for it in dpA))
        evA = [p["evidencia"] for p in pA["pendencias"] if str(p["origem"]).startswith("CONCILIACAO (balanço)")]
        itemB = next(i for i in manB["itens"] if i["arquivo"].endswith("_balancete_2026-10.pdf"))
        registrar("MULTI-05 Conciliação de A usa SOMENTE o balancete de A (evidência = arquivo/sha de A); o balancete de B não é lido no "
                  "contexto de A (caminho fora da empresa → recusado)",
                  evA and all(e.get("arquivo", "").startswith(sA["pasta"]) for e in evA) and af.original(CL, cf.A, itemB) is None
                  and af.original(CL, cf.B, itemB) is not None, evA[:1])

        def iss(sol):
            r, _ = ic.resultado_registrado(servidor.RUNTIME, sol, reg(sol), "BANCOS")
            return next(l for l in r["lancamentos"] if "ISS" in str(l.get("historico", "")).upper())
        lA, lB = iss(solA), iss(solB)
        registrar("MULTI-08 mesma obrigação/fornecedor (ISS da prefeitura fictícia) com CONTA DIFERENTE por empresa: A aplica a regra de A "
                  "(2131, proposta); B aplica a SUA regra (4202) — recusada por incompatibilidade, nunca trocada pela conta de A",
                  (lA.get("debito") or {}).get("codigo") == "2131" and lA["status"] == "PROPOSTO" and lB["status"] == "INCOMPLETO"
                  and lB.get("debito") is None and any("Conta 4202" in x for x in lB["pendencias"]),
                  ((lA.get("debito") or {}).get("codigo"), lB["status"], lB["pendencias"][:1]))
        contasA = {m["conta"] for m in ctxA["movimentos"]}
        contasB = {m["conta"] for m in ctxB["movimentos"]}
        registrar("MULTI-09 mesmo banco (001, agência 1234) permanece isolado: movimentos de A só da conta de A; de B só da conta de B",
                  contasA and contasB and not contasA & contasB and all("55555" in x for x in contasA) and all("66666" in x for x in contasB),
                  (contasA, contasB))
        registrar("MULTI-10 mesma competência (2026-10) sem colisão: SOLs, pastas de execução, pastas de documentos e registros distintos",
                  solA != solB and sA["competencia"] == sB["competencia"] == cf.COMPETENCIA and sA["pasta"] != sB["pasta"]
                  and sA["empresa"] == cf.A and sB["empresa"] == cf.B and sA["financeiro"][-1]["resultado_sha256"] != sB["financeiro"][-1]["resultado_sha256"]
                  and (servidor.RUNTIME / "execucoes" / solA) != (servidor.RUNTIME / "execucoes" / solB),
                  (solA, solB))
        ted = lambda fx: next(m for m in fx["movimentos"] if m["descricao"] == "TED RECEBIDA GAMA COMERCIO NF 102")  # noqa: E731
        fxB = ic.analisar_financeiro(ctxB)
        registrar("MULTI-11 mesmo valor e mesma data (TED 6.000,00 em 25/10, NF 102 nas duas empresas) não cruzam empresas",
                  ted(fxA)["candidatos"] and ted(fxB)["candidatos"] and all(x["proveniencia"]["sol"] == solA for x in ted(fxA)["candidatos"])
                  and all(x["proveniencia"]["sol"] == solB for x in ted(fxB)["candidatos"]), "")
        nomesA = {d["nome"] for d in pA["documentos"]["itens"]}
        registrar("MULTI-12 pendência de B não aparece em A (empresa/competência em toda pendência; documento de outra empresa ficou só em B)",
                  all(p["empresa"] == cf.A for p in pA["pendencias"]) and all(p["empresa"] == cf.B for p in pB["pendencias"])
                  and pB["documentos"]["a_conferir"] >= 1 and pA["documentos"]["a_conferir"] == 0
                  and not any(cf.B in json.dumps(p, ensure_ascii=False) for p in pA["pendencias"]), (pA["documentos"]["a_conferir"], pB["documentos"]["a_conferir"]))
        recA = {d["tipo"]: d for d in pA["documentos"]["itens"]}
        recB = {d["tipo"]: d for d in pB["documentos"]["itens"]}
        t = "Balancete contábil do período"
        registrar("MULTI-13 adapter COMPARTILHADO sem compartilhar dados: o mesmo adapter lê o balancete de A e o de B, cada um com o próprio "
                  "documento/sha (o módulo não guarda dados entre chamadas)",
                  recA[t]["adapter"] == recB[t]["adapter"] == "BALANCETE_PDF_COLUNAS_V1" and recA[t]["sha256"] != recB[t]["sha256"]
                  and not any(isinstance(v, (dict, list)) and v and k.isupper() and k not in ("CONTRATOS", "CATEGORIA_TIPO", "DEPARTAMENTOS", "NOME_DEPARTAMENTO",
                              "AREA_PARA_DEPARTAMENTO", "TEXTO_RECONHECIMENTO", "ADAPTERS", "LEITOR_DA_AREA", "SIN_RAZAO") for k, v in vars(af).items()),
                  (recA[t]["sha256"][:12], recB[t]["sha256"][:12]))
        (CL / cf.B / "REGRAS-INTERCAMBIO.json").write_text((CL / cf.A / "REGRAS-INTERCAMBIO.json").read_text(encoding="utf-8"), encoding="utf-8")
        regrasB = (CL / cf.B / "REGRAS-BANCOS.md").read_text(encoding="utf-8")
        registrar("MULTI-14 regra específica permanece específica: a regra de A copiada para a pasta de B NÃO vale em B (empresa da regra ≠ B); "
                  "a regra de liquidação do ISS de B (4202) não existe em A",
                  ic.politica_temporal(CL, cf.B)["janela_meses"] == 0 and "| 4202 |" in regrasB.split("RB-003")[1].split("\n")[0]
                  and "| 2131 |" in (CL / cf.A / "REGRAS-BANCOS.md").read_text(encoding="utf-8").split("RB-003")[1].split("\n")[0], "")
        antesB = estavel(previa(solB))
        alvo = servidor.RUNTIME / "execucoes" / solA / "fiscal-1" / "resultado.json"
        original = alvo.read_bytes()
        try:
            alvo.write_bytes(original + b" ")
            pA_falha = previa(solA)
            registrar("MULTI-15 falha na empresa A (resultado do Fiscal adulterado → recusado, BLOQUEIO) não altera B (prévia de B idêntica)",
                      any("FISCAL: resultado registrado não encontrado ou alterado" in p["problema"] for p in pA_falha["pendencias"])
                      and estavel(previa(solB)) == antesB and "CONTABILIDADE_DP" in (sB.get("falhas_areas") or {}) and not sA.get("falhas_areas"),
                      sorted((sB.get("falhas_areas") or {}).keys()))
        finally:
            alvo.write_bytes(original)
        falso = copy.deepcopy(ai.registro_isolado()["solicitacoes"])
        falso[solA]["empresa"] = cf.B                       # registro adulterado: SOL de A "declarada" como de B
        ctx_falso = ic.contexto(servidor.RUNTIME, CL, falso, solA)
        registrar("MULTI-ISO registro adulterado (SOL de A declarada como de B): nenhum resultado de A é usado (isolamento fail-closed)",
                  not ctx_falso["itens"] and not ctx_falso["movimentos"] and any("outra empresa" in a for a in ctx_falso["avisos"]), ctx_falso["avisos"][:2])
    finally:
        srv.shutdown()
    registrar("MULTI-RT estado operacional real (CLIENTES/, registro, ordem ativa, LIBERADOS/) intocado", foto == foto_operacional(), "")
    falhas = [r for r in resultados if not r[1]]
    for caso, ok, det in resultados:
        print(("PASSOU " if ok else "FALHOU ") + caso + ("" if ok else f" — {det}"))
    print(f"\nTOTAL: {len(resultados)} · PASSARAM: {len(resultados) - len(falhas)} · FALHARAM: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
