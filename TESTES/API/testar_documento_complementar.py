"""Documento complementar + manifesto/pacote efetivo da tentativa (DOC-COMP-01..30, exceto 29 = tela) e teste INTEGRADO
fictício (INT-01..11). Servidor REAL em ambiente ISOLADO; empresa, documentos e valores 100% FICTÍCIOS (cenario_complementar).

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/API/testar_documento_complementar.py
"""
import hashlib
import json
import os
import stat
import sys
import threading
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(RAIZ / "TESTES"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import ambiente_isolado as ai  # noqa: E402
AMB = ai.criar("prime-complementar-")
os.environ["AGENTES_PRIME_DEMO_CONCILIACAO"] = str(AMB.raiz / "demonstracao-conciliacao")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import complementos  # noqa: E402
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


def bateria(c):
    R = servidor.RUNTIME
    sol, lote_a = c.abrir_sol([("relatorio-financeiro.xlsx", cc.relatorio_xlsx()), ("pagamentos-lote.pdf", cc.pagfor_pdf())])
    assert cc.ocioso(servidor, ai.registro_isolado), "processamento inicial não terminou"
    sol_b, _ = c.abrir_sol([("relatorio-b.xlsx", cc.relatorio_xlsx() + b"")], instrucao="Segunda solicitação fictícia de outubro/2026.")
    assert cc.ocioso(servidor, ai.registro_isolado)
    E = R / "execucoes" / sol
    s0 = reg(sol)
    registrar("INT-01 SOL fictícia inicialmente bloqueada por falta de extrato", s0["estado"] == "AGUARDANDO_SUPERVISOR"
              and any("Nenhum extrato utilizável" in m for m in s0["motivos"]), s0["motivos"][:2])
    pagfor = next(x for x in s0["triagem_documentos"] if x["arquivo"].endswith("pagamentos-lote.pdf"))
    lote_orig_json = (R / "lotes" / lote_a / "lote.json").read_bytes()
    pasta_orig = AMB.clientes / cc.EMPRESA / s0["pasta"]
    arq_orig = arvore(pasta_orig)
    reg_antes = json.dumps(s0, sort_keys=True)
    execs_antes = sorted(p.name for p in E.iterdir())
    manifesto_orig = sha(E / "documentos-local.json")

    # ---------------- DOC-COMP-01..04, 10, 11, 13: extrato com nome neutro
    lote_c1 = c.complementar(sol, "arquivo-0001.pdf", cc.extrato_pdf(), motivo="Extrato bancário da competência recebido depois (fictício).")
    s, rev = c.j("GET", f"/api/solicitacoes/{sol}/complementos/{lote_c1}")
    s, r1 = c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_c1}/concluir", {"confirmado": True})
    comp1 = json.loads((E / "complementos" / lote_c1 / "complemento.json").read_text(encoding="utf-8"))
    registrar("DOC-COMP-01 upload complementar válido", s == 201 and r1["reprocessado"] is False and "crie uma nova tentativa" in r1["mensagem"], (s, r1.get("mensagem")))
    registrar("DOC-COMP-02 lote original intacto", (R / "lotes" / lote_a / "lote.json").read_bytes() == lote_orig_json
              and sha(E / "documentos-local.json") == manifesto_orig)
    registrar("DOC-COMP-03 arquivos originais intactos", arvore(pasta_orig) == arq_orig)
    arq_c1 = AMB.clientes / cc.EMPRESA / comp1["pasta"]
    registrar("DOC-COMP-04 SHA registrado (e conferido com o arquivo guardado)", comp1["documentos"][0]["sha256"] == hashlib.sha256(cc.extrato_pdf()).hexdigest()
              == sha(next(arq_c1.iterdir())) and rev["arquivos"][0]["duplicidade"]["categoria"] == "NOVO")
    doc1 = comp1["documentos"][0]
    registrar("DOC-COMP-10 classificação por Documentos executada", doc1["tipo"] == "Extrato bancário PDF (leitura pelo Financeiro)" and doc1["area"] == "FINANCEIRO"
              and json.loads((E / "complementos" / lote_c1 / "documentos-local.json").read_text(encoding="utf-8"))["contrato"] == "DOCUMENTOS_LOCAL_V1", doc1)
    registrar("DOC-COMP-13 extrato reconhecido pela estrutura (nome neutro 'arquivo-0001.pdf')", doc1["tipo"].startswith("Extrato"), doc1["tipo"])

    # ---------------- DOC-COMP-14..16: nada reprocessado, nenhuma área, nenhum lançamento
    registrar("DOC-COMP-14 upload não reprocessa (registro, execuções e tentativas inalterados)",
              json.dumps(reg(sol), sort_keys=True) == reg_antes and sorted(p.name for p in E.iterdir() if p.name != "complementos") == execs_antes
              and rp.listar(R, sol) == [])
    registrar("DOC-COMP-15 upload não executa Contabilidade", not list(E.glob("bancos-*")) and reg(sol)["plano_etapas"] == s0["plano_etapas"])
    registrar("DOC-COMP-16 upload não cria lançamento", not any(p.suffix in (".csv", ".txt") for p in E.rglob("*")) and not (AMB.raiz / "LIBERADOS").exists())

    # ---------------- DOC-COMP-11/12: nome não decide; PagFor continua PagFor
    lote_n = c.complementar(sol, "extrato-santander-cc.pdf", cc.pagfor_pdf("SEGUNDA VIA FICTICIA"), motivo="Comprovante com nome enganoso (fictício).")
    s, rn = c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_n}/concluir", {"confirmado": True})
    tipo_n = rn["complemento"]["documentos"][0]["tipo"]
    registrar("DOC-COMP-11 nome do arquivo não decide a classificação", s == 201 and not tipo_n.startswith("Extrato"), tipo_n)
    registrar("DOC-COMP-12 PagFor não vira extrato (original e complementar)", not pagfor["tipo"].startswith("Extrato") and not tipo_n.startswith("Extrato"),
              (pagfor["tipo"], tipo_n))

    # ---------------- DOC-COMP-05/06: duplicidade pelo SHA
    lote_d = c.complementar(sol, "copia-relatorio.xlsx", cc.relatorio_xlsx())
    s, rd = c.j("GET", f"/api/solicitacoes/{sol}/complementos/{lote_d}")
    s2, rd2 = c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_d}/concluir", {"confirmado": True})
    lote_d2 = c.complementar(sol, "outro-nome.pdf", cc.extrato_pdf())
    s3, rd3 = c.j("GET", f"/api/solicitacoes/{sol}/complementos/{lote_d2}")
    registrar("DOC-COMP-05 mesmo SHA na mesma SOL detectado e recusado com explicação",
              rd["arquivos"][0]["duplicidade"]["categoria"] == "MESMA_SOL" and not rd["pode_concluir"] and s2 == 409 and "já faz parte" in rd2["erro"]
              and rd3["arquivos"][0]["duplicidade"]["categoria"] == "MESMA_SOL", (rd["arquivos"][0]["duplicidade"], s2))
    for lt in (lote_d, lote_d2):
        c.j("DELETE", f"/api/lotes/{lt}")
    lote_mn = c.complementar(sol, "pagamentos-lote.pdf", cc.comprovante_pdf(), motivo="Mesmo nome, outro conteúdo (fictício).")
    s, rmn = c.j("GET", f"/api/solicitacoes/{sol}/complementos/{lote_mn}")
    lote_b = c.complementar(sol_b, "extrato-b.pdf", cc.extrato_pdf())
    s4, rb = c.j("GET", f"/api/solicitacoes/{sol_b}/complementos/{lote_b}")
    registrar("DOC-COMP-06 mesmo nome com SHA diferente = documento novo; SHA de outra SOL da empresa/competência identificado",
              rmn["arquivos"][0]["duplicidade"]["categoria"] == "NOVO" and rb["arquivos"][0]["duplicidade"]["categoria"] == "MESMA_EMPRESA_COMPETENCIA",
              (rmn["arquivos"][0]["duplicidade"], rb["arquivos"][0]["duplicidade"]))
    c.j("DELETE", f"/api/lotes/{lote_mn}")
    c.j("DELETE", f"/api/lotes/{lote_b}")

    # ---------------- DOC-COMP-07..09: validações de contexto
    registrar("DOC-COMP-07 SOL inexistente recusada", c.j("POST", "/api/solicitacoes/SOL-2026-999999/complementos", {"motivo": "Teste fictício."})[0] == 404)
    lote_x = c.complementar(sol, "x.pdf", cc.comprovante_pdf())
    caminho_x = R / "lotes" / lote_x / "lote.json"
    original_x = json.loads(caminho_x.read_text(encoding="utf-8"))
    caminho_x.write_text(json.dumps(dict(original_x, empresa="OUTRA-EMPRESA-FICTICIA")), encoding="utf-8")
    s_emp = c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_x}/concluir", {"confirmado": True})[0]
    s_rota = c.j("POST", f"/api/solicitacoes/{sol_b}/complementos/{lote_x}/concluir", {"confirmado": True})[0]
    registrar("DOC-COMP-08 empresa incompatível recusada (e lote de uma SOL não conclui por outra)", s_emp == 409 and s_rota == 404, (s_emp, s_rota))
    caminho_x.write_text(json.dumps(dict(original_x, competencia="2026-09")), encoding="utf-8")
    s_comp = c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_x}/concluir", {"confirmado": True})[0]
    registrar("DOC-COMP-09 competência incompatível recusada", s_comp == 409, s_comp)
    caminho_x.write_text(json.dumps(original_x), encoding="utf-8")

    # ---------------- DOC-COMP-24/25/26/27/28: concorrência, interrupção, atomicidade, staging, caminhos
    servidor.EM_EXECUCAO["sol"] = sol
    try:
        conc = (c.j("POST", f"/api/solicitacoes/{sol}/complementos", {"motivo": "Concorrência fictícia."})[0],
                c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_x}/concluir", {"confirmado": True})[0])
    finally:
        servidor.EM_EXECUCAO["sol"] = None
    registrar("DOC-COMP-24 concorrência: recusa com processamento ativo", conc == (409, 409), conc)
    s_sha = c.enviar(lote_x, "y.pdf", cc.comprovante_pdf(), sha="0" * 64)[0]
    parciais = list((R / "lotes" / lote_x / "arquivos").glob(".parcial-*"))
    with patch.object(complementos, "triagem", side_effect=RuntimeError("queda simulada")):
        s_falha = c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_x}/concluir", {"confirmado": True})[0]
    lx = json.loads(caminho_x.read_text(encoding="utf-8"))
    sem_resto = not (E / "complementos" / lote_x).exists() and not (AMB.clientes / cc.EMPRESA / "RECEBIDOS" / cc.COMPETENCIA / lote_x).exists()
    s_ret = c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_x}/concluir", {"confirmado": True})[0]
    registrar("DOC-COMP-25 upload/conclusão interrompidos não deixam estado parcial (e nova tentativa de concluir funciona)",
              s_sha == 400 and not parciais and s_falha == 500 and sem_resto and lx["estado"] == "RECEBENDO" and s_ret == 201,
              (s_sha, len(parciais), s_falha, sem_resto, lx["estado"], s_ret))
    alvo = AMB.raiz / "atomico" / "complemento.json"
    complementos.gravar_atomico(alvo, {"versao": 1})
    with patch.object(complementos.os, "replace", side_effect=OSError("disco cheio simulado")):
        try:
            complementos.gravar_atomico(alvo, {"versao": 2})
            falhou = False
        except OSError:
            falhou = True
    registrar("DOC-COMP-26 escrita atômica (falha preserva o anterior, sem temporário)", falhou and json.loads(alvo.read_text())["versao"] == 1
              and [p.name for p in alvo.parent.iterdir()] == ["complemento.json"])
    guardados = list((AMB.clientes / cc.EMPRESA / comp1["pasta"]).iterdir())
    registrar("DOC-COMP-27 staging seguro (fora de CLIENTES, removido após concluir; guardado somente leitura)",
              not (R / "lotes" / lote_c1 / "arquivos").exists() and str(R) not in str(AMB.clientes)
              and all(not (p.stat().st_mode & stat.S_IWUSR) for p in guardados))
    lote_p = c.complementar(sol, "../../../../etc/arquivo.pdf", cc.comprovante_pdf())
    nome_p = json.loads((R / "lotes" / lote_p / "lote.json").read_text(encoding="utf-8"))["arquivos"][0]["nome_interno"]
    rotas = [c.j("POST", f"/api/solicitacoes/{sol}/complementos", {"motivo": "Teste fictício.", "pasta": "/etc"})[0],
             c.j("GET", f"/api/solicitacoes/{sol}/complementos/../../lotes")[0],
             c.j("POST", f"/api/solicitacoes/{sol}/complementos/L-00000000-000000-000000/concluir", {"confirmado": True})[0],
             c.j("POST", f"/api/lotes/{lote_p}/iniciar", {"conferencia_humana": True})[0]]
    registrar("DOC-COMP-28 caminho arbitrário recusado (nome saneado, campos extras, rotas e abertura de SOL pelo lote complementar)",
              "/" not in nome_p and ".." not in nome_p and rotas[0] == 400 and rotas[1] in (400, 404) and rotas[2] == 404 and rotas[3] == 409,
              (nome_p, rotas))
    c.j("DELETE", f"/api/lotes/{lote_p}")

    # ---------------- INT-02..11 + DOC-COMP-17..23, 30: tentativa com snapshot efetivo
    registrar("INT-02 após o complemento, a SOL continua com o resultado anterior", reg(sol)["estado"] == "AGUARDANDO_SUPERVISOR"
              and sorted(p.name for p in E.glob("financeiro-*")) == ["financeiro-1"])
    s, rt = c.j("POST", f"/api/solicitacoes/{sol}/reprocessar", {"confirmado": True, "motivo": "Extrato complementar recebido (fictício).", "solicitante": "Supervisor"})
    t1 = rt["tentativa"]
    docs1 = t1["manifesto_efetivo"]["documentos"]
    origens = sorted(d["origem"] for d in docs1)
    registrar("DOC-COMP-17 nova tentativa inclui original + complementares concluídos", s == 201 and origens.count("ORIGINAL") == 2
              and origens.count("COMPLEMENTAR") == 3, origens)
    registrar("INT-03/04 nova tentativa criada; snapshot = lote original + complementares", t1["status"] == "PREPARADA" and t1["ciclo_vida"] == "V2"
              and t1["manifesto_efetivo"]["lote_original"] == lote_a and lote_c1 in t1["manifesto_efetivo"]["lotes_complementares"])
    arq_t1 = E / "tentativas" / "0001" / "tentativa.json"
    pacote1 = arvore(E / "tentativas" / "0001" / "pacote")
    snap1 = t1["manifesto_efetivo_sha256"]
    lote_tarde = c.complementar(sol, "comprovante-tardio.pdf", cc.comprovante_pdf().replace(b"200,00", b"201,00"), motivo="Chegou depois da tentativa (fictício).")
    c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote_tarde}/concluir", {"confirmado": True})
    t1b = json.loads(arq_t1.read_text(encoding="utf-8"))
    registrar("DOC-COMP-19 documento adicionado depois não invade a tentativa existente",
              lote_tarde not in t1b["manifesto_efetivo"]["lotes_complementares"] and arvore(E / "tentativas" / "0001" / "pacote") == pacote1)
    s, rr = c.j("POST", f"/api/solicitacoes/{sol}/retomar-rota-financeira", {"justificativa": "Executar com o extrato complementar (fictício).", "confirmado": True})
    assert s == 202, rr
    assert cc.ocioso(servidor, ai.registro_isolado), "execução não terminou"
    s1 = reg(sol)
    t1c = json.loads(arq_t1.read_text(encoding="utf-8"))
    fin = sorted(E.glob("financeiro-*"), key=lambda p: int(p.name.split("-")[1]))[-1]
    rf = json.loads((fin / "resultado.json").read_text(encoding="utf-8"))
    cf = rf.get("conciliacao_financeira") or {}
    registrar("DOC-COMP-18 snapshot imutável (pacote somente leitura; manifesto e hash iguais após a execução)",
              arvore(E / "tentativas" / "0001" / "pacote") == pacote1 and t1c["manifesto_efetivo"] == t1b["manifesto_efetivo"]
              and t1c["manifesto_efetivo_sha256"] == snap1
              and all(not (p.stat().st_mode & stat.S_IWUSR) for p in (E / "tentativas" / "0001" / "pacote").iterdir()))
    registrar("DOC-COMP-30 reprocessamento usa o manifesto efetivo (âncora no pacote da tentativa; execução ligada à tentativa)",
              s1["ancora_documentos"].get("origem") == "PACOTE_EFETIVO_TENTATIVA" and s1["ancora_documentos"].get("tentativa") == 1
              and fin.name in [e["execucao"] for e in t1c["execucoes"]], (s1["ancora_documentos"].get("origem"), t1c.get("execucoes")))
    registrar("INT-05/06 fluxo executado; Documentos reconheceu o extrato (triagem da SOL inclui o complementar)",
              any(x["arquivo"] == doc1["arquivo"] and x.get("tipo", "").startswith("Extrato") for x in s1["triagem_documentos"]))
    registrar("INT-07 Financeiro utilizou o extrato complementar", rf["fonte_bancaria"]["extratos_utilizaveis"] == 1 and rf["fonte_bancaria"]["movimentos_bancarios"] == 5,
              rf["fonte_bancaria"].get("extratos_utilizaveis"))
    registrar("INT-08 conciliação financeira criada (motor V1)", cf.get("situacao") == "EXECUTADA" and cf.get("politica") == "CONCILIACAO_FINANCEIRA_POLITICA_V1",
              (cf.get("situacao"), (cf.get("resumo") or {}).get("bancarios")))
    s, vc = c.j("GET", f"/api/solicitacoes/{sol}/conciliacao-financeira")
    registrar("INT-09 Central de Revisão disponível para a SOL", s == 200 and vc.get("disponivel") and vc["resumo"]["movimentos_bancarios"] == 5, vc.get("resumo"))
    registrar("INT-10 movimentos sem decisão continuam bloqueando", vc["resumo"]["bloqueios_restantes"] > 0 and rf["bloqueio_lote"]
              and s1["estado"] == "AGUARDANDO_SUPERVISOR", (vc["resumo"]["bloqueios_restantes"], rf["bloqueio_lote"][:1]))
    plano = {p["etapa"]: p["situacao"] for p in s1["plano_etapas"]}
    registrar("INT-11 Contabilidade não recebe movimentos indevidos", plano.get("BANCOS") == "BLOQUEADA_POR_DEPENDENCIA" and not list(E.glob("bancos-*"))
              and t1c["status"] == "BLOQUEADA", (plano, t1c["status"]))
    s, rt2 = c.j("POST", f"/api/solicitacoes/{sol}/reprocessar", {"confirmado": True, "motivo": "Incluir comprovante tardio (fictício).", "solicitante": "Supervisor"})
    t2 = rt2.get("tentativa", {})
    registrar("DOC-COMP-20 próxima tentativa inclui o documento posterior", s == 201 and t2["numero"] == 2
              and lote_tarde in t2["manifesto_efetivo"]["lotes_complementares"], (s, rt2.get("mensagem")))
    t1d = json.loads(arq_t1.read_text(encoding="utf-8"))
    registrar("DOC-COMP-21 tentativa histórica não muda", t1d["manifesto_efetivo_sha256"] == snap1 and t1d["status"] == "BLOQUEADA"
              and arvore(E / "tentativas" / "0001" / "pacote") == pacote1)
    s, lista = c.j("GET", f"/api/solicitacoes/{sol}/complementos")
    c1 = next(x for x in lista["complementos"] if x["lote"] == lote_c1)
    ct = next(x for x in lista["complementos"] if x["lote"] == lote_tarde)
    registrar("DOC-COMP-22 rastreabilidade lote → documento → tentativa", c1["tentativas"] == [1, 2] and ct["tentativas"] == [2]
              and all(c1.get(k) for k in ("sol", "empresa", "competencia", "lote", "lote_original", "motivo", "responsavel", "recebido_em", "concluido_em"))
              and c1["documentos"][0]["sha256"] == doc1["sha256"], (c1["tentativas"], ct["tentativas"]))
    s, lb = c.j("GET", f"/api/solicitacoes/{sol_b}/complementos")
    registrar("DOC-COMP-23 isolamento entre SOLs", lb["complementos"] == [] and not (R / "execucoes" / sol_b / "complementos").exists()
              and reg(sol_b)["ancora_documentos"].get("origem") != "PACOTE_EFETIVO_TENTATIVA")
    s, lg = c.j("GET", f"/api/solicitacoes/{sol}/tentativas/0001/reconciliacao-legada")
    registrar("LEG-API tentativa V2 não oferece reconciliação legada (rota)", s == 200 and lg["codigo"] == "JA_RECONCILIADA" or lg["codigo"] in ("NAO_LEGADA", "ESTADO_JA_FINAL"),
              lg.get("codigo"))


def main():
    antes = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cc.preparar_empresa(servidor, servidor.RUNTIME)
        bateria(cc.Cliente(srv.server_port))
    except Exception as exc:  # noqa: BLE001
        import traceback
        registrar("DOC-COMP-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-600:]}")
    finally:
        srv.shutdown()
        srv.server_close()
    registrar("DOC-COMP-99 ambiente operacional intocado", foto_operacional() == antes)
    falhas = 0
    for caso, ok, d in resultados:
        falhas += not ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {caso}" + ("" if ok else f"  → {d}"))
    print(f"TOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
