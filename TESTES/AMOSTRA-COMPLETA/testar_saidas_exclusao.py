"""Saídas do fechamento (TXT + Excel + balancete), exclusão definitiva pela lixeira, Importação VGROW desativada e limpeza do
ambiente — API REAL e executores locais reais, ambiente 100% ISOLADO (cadastros, registro, runtime, ordem ativa, LIBERADOS e
arquivo de limpeza temporários). Dados fictícios. Nada é importado no Domínio.

Uso: .venv/Scripts/python.exe -I TESTES/AMOSTRA-COMPLETA/testar_saidas_exclusao.py
"""
import hashlib
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
TMP = Path(tempfile.mkdtemp(prefix="prime-saidas-"))
for k, v in {"AGENTES_PRIME_RUNTIME": TMP / "runtime", "AGENTES_PRIME_REGISTRO_SOL": TMP / "controle" / "solicitacoes.json",
             "AGENTES_PRIME_ORDEM_ATIVA": TMP / "ordem-ativa.json", "AGENTES_PRIME_CLAUDE": TMP / "claude-inexistente.exe",
             "LOCALAPPDATA": TMP / "localappdata", "AGENTES_PRIME_LIBERADOS": TMP / "LIBERADOS", "AGENTES_PRIME_CLIENTES": TMP / "CLIENTES"}.items():
    os.environ[k] = str(v)
(TMP / "CLIENTES").mkdir()
(TMP / "controle").mkdir()
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import amostra_ficticia as am  # noqa: E402
import servidor  # noqa: E402
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado as _ai  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

EMP = {"id": "AMOSTRA-SAIDAS-TMP", "nome": "EMPRESA AMOSTRA SAIDAS FICTICIA LTDA", "cnpj": "90.080.080/0001-25", "conta": "55555-5"}
ORIGINAL_A = dict(am.EMPRESAS["A"])
resultados, INFO = [], []
srv = None


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:450]))


def req(metodo, rota, dados=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=300)
    h = {"X-Prime-Sessao": srv.token, "Content-Type": "application/json"}
    h.update(cab or {})
    c.request(metodo, "/api" + rota, dados if isinstance(dados, bytes) else json.dumps(dados).encode() if dados is not None else None, h)
    r = c.getresponse()
    bruto = r.read()
    c.close()
    try:
        return r.status, json.loads(bruto)
    except ValueError:
        return r.status, bruto


def todos():
    return _ai.registro_isolado()


def registro():
    return todos()["solicitacoes"]


def ocioso(limite=600):
    fim = time.time() + limite
    while time.time() < fim:
        if not servidor.EM_EXECUCAO["sol"] and not servidor.EM_FINANCEIRO["sol"] and not any(
                str(s.get("estado", "")).endswith("_EM_ANDAMENTO") or s.get("estado") == "DOCUMENTOS_EM_ANDAMENTO" for s in registro().values()):
            return True
        time.sleep(0.3)
    return False


def lote(docs, instrucao="Receber os documentos de outubro/2026 e preparar o fechamento (SIMULAÇÃO)."):
    c, d = req("POST", "/lotes", {"empresa": EMP["id"], "competencia": "2026-10", "fluxo": "DOCUMENTOS", "instrucao": instrucao})
    assert c == 201, (c, d)
    for nome, conteudo in docs.items():
        c, r = req("PUT", f"/lotes/{d['lote']}/arquivos", conteudo, {"X-Nome-Arquivo": nome, "X-Sha256": hashlib.sha256(conteudo).hexdigest(),
                                                                       "Content-Type": "application/octet-stream"})
        assert c == 201, (nome, c, r)
    return d["lote"]


def enviar(docs, instrucao=None):
    ocioso()
    lt = lote(docs, *( [instrucao] if instrucao else []))
    c, r = req("POST", f"/lotes/{lt}/iniciar", {"conferencia_humana": True})
    assert c == 202, (c, r)
    time.sleep(0.5)
    ocioso()
    return r["sol"]


def aprovar(sol, ciente=False):
    corpo = {"acao": "aprovar", "frase": f"APROVO FECHAMENTO {sol}", "justificativa": "Fechamento ficticio conferido.", "confirmado": True}
    if ciente:
        corpo["ciente_exportados"] = True
    return req("POST", f"/solicitacoes/{sol}/aprovacao", corpo)


def revogar(sol):
    return req("POST", f"/solicitacoes/{sol}/aprovacao", {"acao": "revogar", "justificativa": "Revogacao de teste ficticio.", "confirmado": True})


def lixeira(sol):
    return req("DELETE", f"/solicitacoes/{sol}", {"confirmado": True})


def excluir(sol, frase=None):
    return req("POST", f"/solicitacoes/{sol}/exclusao-definitiva", {"frase": frase or f"EXCLUIR DEFINITIVAMENTE {sol}",
                                                                   "justificativa": "Exclusão definitiva de teste fictício.", "confirmado": True})


def nota_104():
    return {"01_nfse_104_beta.txt": (f"NFS-E - NOTA FISCAL DE SERVICOS ELETRONICA (FICTICIA)\nPRESTADOR: {EMP['nome']}\nCNPJ DO PRESTADOR: "
                                     f"{EMP['cnpj']}\nTOMADOR: {am.BETA[0]}\nCNPJ DO TOMADOR: {am.BETA[1]}\nNUMERO DA NOTA: 104\n"
                                     "DATA DE EMISSAO: 30/10/2026\nCOMPETENCIA: 10/2026\nVALOR DOS SERVICOS: R$ 1.500,00\n"
                                     "VALOR TOTAL DA NOTA: R$ 1.500,00\n").encode("utf-8")}


def saidas_e_revogacao():
    sol = enviar(am.documentos("A"))
    c, r = aprovar(sol)
    ap = registro()[sol]["aprovacao"]
    txt = servidor.caminho_registrado(ap["arquivo_txt"])
    anexos = {t: servidor.caminho_registrado(a["arquivo"]) for t, a in (ap.get("anexos") or {}).items()}
    linhas = txt.read_bytes().decode("cp1252").split("\r\n")[:-1]
    wb = load_workbook(io.BytesIO(anexos["excel"].read_bytes()))
    rows = [r_ for r_ in wb["Lançamentos"].iter_rows(min_row=2, values_only=True) if isinstance(r_[0], int)]
    igual = len(rows) == len(linhas) and all(
        (r_[1].strftime("%d/%m/%Y"), r_[2], r_[4], Decimal(str(r_[6])).quantize(Decimal("0.01")), r_[7])
        == (l.split(";")[0], l.split(";")[1], l.split(";")[2], Decimal(l.split(";")[3].replace(",", ".")).quantize(Decimal("0.01")), l.split(";")[5])
        for r_, l in zip(rows, linhas))
    ident_x = {k: v for k, v in load_workbook(io.BytesIO(anexos["excel"].read_bytes()))["Identificação"].iter_rows(values_only=True)}
    wbb = load_workbook(io.BytesIO(anexos["balancete"].read_bytes()))
    bal = {str(r_[0]): r_ for r_ in wbb["Balancete"].iter_rows(min_row=2, values_only=True) if r_[0] and str(r_[0]).isdigit()}
    ident_b = {k: v for k, v in wbb["Identificação"].iter_rows(values_only=True)}
    conc = json.loads(servidor.ultimo_concluido_caminho(sol, "conciliacao").read_text(encoding="utf-8"))
    saldo_conc = {s["conta"]: s for s in conc["saldos_contas"]}
    mov = {}
    for l in linhas:
        d_, c_, v = l.split(";")[1], l.split(";")[2], Decimal(l.split(";")[3].replace(",", "."))
        mov.setdefault(d_, [Decimal(0), Decimal(0)])[0] += v
        mov.setdefault(c_, [Decimal(0), Decimal(0)])[1] += v
    fmt = lambda v: f"{abs(v):,.2f} {'D' if v > 0 else 'C' if v < 0 else ''}".strip().replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
    confere_mov = all(Decimal(str(bal[k][7])) == m[0] and Decimal(str(bal[k][8])) == m[1] for k, m in mov.items())
    confere_saldos = all(fmt(Decimal(str(bal[k][9])) * (-1 if bal[k][10] == "C" else 1)) == fmt(Decimal(s["saldo_final"]))
                         for k, s in saldo_conc.items() if s.get("saldo_final") is not None and k in bal)
    total_linha = [r_ for r_ in wbb["Balancete"].iter_rows(values_only=True) if str(r_[0]).startswith("Total do movimento")][0]
    registrar("S-01 aprovação gera TXT, Excel dos lançamentos e balancete da MESMA versão: Excel idêntico ao TXT linha a linha; "
              "identificação com o sha256 do TXT; sha256 dos três registrados",
              c == 200 and r["liberacao"]["situacao"] == "LIBERADO_PARA_IMPORTACAO_MANUAL" and set(anexos) == {"excel", "balancete"}
              and igual and ident_x["sha256 do TXT correspondente"] == ap["txt_sha256"] == ident_b["sha256 do TXT correspondente"]
              and all(hashlib.sha256(anexos[t].read_bytes()).hexdigest() == ap["anexos"][t]["sha256"] for t in anexos),
              f"{r.get('liberacao', {}).get('situacao')} linhas={len(linhas)} excel={len(rows)}")
    registrar("S-02 balancete: abertura documentada (Conciliação aprovada) + movimento dos lançamentos aprovados = saldo final; "
              "total do movimento separado dos saldos; só analíticas; abrangência INTEGRAL; aviso de SIMULAÇÃO",
              confere_mov and confere_saldos and Decimal(str(total_linha[7])) == Decimal(str(total_linha[8])) == Decimal(ap["txt_total"])
              and str(ident_b["Abrangência"]).startswith("INTEGRAL") and "não comprova importação" in str(ident_b["Aviso"]).lower()
              and (Decimal(str(bal["1101"][9])), bal["1101"][10]) == (Decimal("45455.00"), "D"), f"1101={bal.get('1101')} total={total_linha[7:9]}")
    INFO.append(f"Balancete (amostra A): 1101 {bal['1101'][5]} {bal['1101'][6]} → {bal['1101'][9]} {bal['1101'][10]}; "
                f"1121 {bal['1121'][5]} {bal['1121'][6]} → {bal['1121'][9]} {bal['1121'][10]}; movimento total {total_linha[7]}")
    downloads = {t: req("GET", f"/solicitacoes/{sol}/saidas/{t}") for t in ("excel", "balancete")}
    registrar("S-03 downloads do Excel e do balancete devolvem exatamente os arquivos registrados",
              all(downloads[t][0] == 200 and downloads[t][1] == anexos[t].read_bytes() for t in anexos), {t: d[0] for t, d in downloads.items()})
    plano_md = TMP / "CLIENTES" / EMP["id"] / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md"
    original = plano_md.read_bytes()
    plano_md.write_bytes(original + b"\n")
    bloqueados = [req("GET", r_)[0] for r_ in (f"/solicitacoes/{sol}/txt-dominio", f"/solicitacoes/{sol}/saidas/excel", f"/solicitacoes/{sol}/saidas/balancete")]
    plano_md.write_bytes(original)
    registrar("S-04 fonte alterada depois da aprovação bloqueia os TRÊS downloads (409)", bloqueados == [409, 409, 409], bloqueados)
    trava = open(anexos["balancete"], "rb")
    try:
        c4, r4 = revogar(sol)
    finally:
        trava.close()
    c5, r5 = req("POST", f"/solicitacoes/{sol}/txt-dominio/mover-revogado", {"confirmado": True, "justificativa": "Arquivo fechado; mover."})
    restantes = sorted(p.name for p in txt.parent.iterdir())
    registrar("S-05 revogação renomeia TXT, Excel e balancete como REVOGADO; anexo travado = 'não movido' até a nova tentativa explícita; "
              "downloads 404", r4["liberacao"]["situacao"] == "REVOGADO_ARQUIVO_NAO_MOVIDO" and r5["liberacao"]["situacao"] == "REVOGADO"
              and all("_REVOGADO-" in n for n in restantes) and len(restantes) == 3
              and [req("GET", f"/solicitacoes/{sol}/saidas/{t}")[0] for t in ("excel", "balancete")] == [404, 404], restantes)
    return sol


def exclusoes(sol_a):
    # rascunho: lote enviado e não iniciado
    lt = lote(nota_104())
    pasta = TMP / "runtime" / "lotes" / lt
    existia = pasta.is_dir()
    c, _ = req("DELETE", f"/lotes/{lt}")
    registrar("E-01 rascunho (lote não iniciado) excluído: arquivos enviados apagados, nenhuma SOL criada", existia and c == 200 and not pasta.exists(), c)

    # SOL com pendências (só uma nota: Conciliação parcial)
    sol_p = enviar(nota_104(), "Complemento de outubro/2026 com uma nota (SIMULAÇÃO).")
    s = registro()[sol_p]
    recebidos = TMP / "CLIENTES" / EMP["id"] / s["pasta"]
    c0, r0 = req("POST", f"/solicitacoes/{sol_p}/exclusao-definitiva", {"frase": f"EXCLUIR DEFINITIVAMENTE {sol_p}", "justificativa": "teste ficticio",
                                                                       "confirmado": True})
    lixeira(sol_p)
    cp, pv = req("GET", f"/solicitacoes/{sol_p}/exclusao-definitiva")
    c1, _ = excluir(sol_p, "excluir")
    c2, r2 = excluir(sol_p)
    t = todos()
    m = t["registros_minimos"].get(sol_p, {})
    registrar("E-02 SOL com pendências: exige estar na lixeira e a frase exata; prévia lista o que será apagado e o que permanece; "
              "documentos, resultados e lote apagados; fica SÓ o registro mínimo (sem documentos)",
              c0 == 409 and cp == 200 and pv["permitida"] and pv["sera_removido"] and pv["permanece"] and c1 == 409 and c2 == 200
              and sol_p not in t["solicitacoes"] and not recebidos.exists() and not (TMP / "runtime" / "execucoes" / sol_p).exists()
              and m.get("fatos_exportados") == {} and m.get("remocao_pendente") == [] and "pasta_documentos" in m,
              f"{c0} {c1} {c2} {r2.get('mensagem') if isinstance(r2, dict) else r2}")
    novo = enviar(nota_104(), "Reenvio do complemento de outubro/2026 (SIMULAÇÃO).")
    registrar("E-03 número da SOL excluída não é reutilizado", int(novo.rsplit("-", 1)[1]) > int(sol_p.rsplit("-", 1)[1]), f"{sol_p} → {novo}")

    # SOL relacionada a outra (mesmos fatos da SOL A)
    sol_r = enviar(am.documentos("A"), "Reenvio de outubro/2026 para revisão (SIMULAÇÃO).")
    rel = {x["sol"]: x["classificacao"] for x in req("GET", f"/solicitacoes/{sol_r}")[1]["relacao_outras_sols"]}
    lixeira(sol_r)
    _, pv = req("GET", f"/solicitacoes/{sol_r}/exclusao-definitiva")
    c3, _ = excluir(sol_r)
    estado_a = registro()[sol_a]["estado"]
    registrar("E-04 SOL relacionada: prévia informa a relação com a original; exclusão não altera a outra SOL",
              sol_a in rel and any(sol_a in x for x in pv["consequencias"]) and c3 == 200 and estado_a == "AGUARDANDO_SUPERVISOR", rel)

    # SOL aprovada e com exportação anterior
    c4, _ = aprovar(sol_a, ciente=True)
    c5, r5 = lixeira(sol_a)
    c6, r6 = req("GET", f"/solicitacoes/{sol_a}/exclusao-definitiva")
    revogar(sol_a)
    lixeira(sol_a)
    _, pv = req("GET", f"/solicitacoes/{sol_a}/exclusao-definitiva")
    arquivos_antes = sorted(p.name for p in (TMP / "LIBERADOS" / EMP["id"] / "2026-10").iterdir())
    c7, r7 = excluir(sol_a)
    m = todos()["registros_minimos"].get(sol_a, {})
    restantes = sorted(p.name for p in (TMP / "LIBERADOS" / EMP["id"] / "2026-10").iterdir()) if (TMP / "LIBERADOS" / EMP["id"] / "2026-10").exists() else []
    registrar("E-05 SOL com aprovação VIGENTE: lixeira e exclusão recusadas (revogar antes). Depois de revogada: prévia informa os "
              "fatos exportados e que não estorna o Domínio; TXT/Excel/balancete apagados; registro mínimo guarda identidades e sha256",
              c4 == 200 and c5 == 409 and "revogue" in r5.get("erro", "") and not r6["permitida"] and c7 == 200
              and any("NÃO estorna nada no Domínio" in x for x in pv["consequencias"]) and len(m.get("fatos_exportados", {})) == 18
              and m["exportacoes"] and all(e.get("txt_sha256") for e in m["exportacoes"]) and arquivos_antes and restantes == [],
              f"{c4} {c5} {c7} antes={len(arquivos_antes)} depois={restantes}")
    sol_n = enviar(am.documentos("A"), "Novo envio de outubro/2026 depois da exclusão (SIMULAÇÃO).")
    d = req("GET", f"/solicitacoes/{sol_n}")[1]
    rel = {x["sol"]: x for x in d["relacao_outras_sols"]}
    c8, _ = aprovar(sol_n)
    c9, _ = aprovar(sol_n, ciente=True)
    registrar("E-06 depois da exclusão os fatos NÃO voltam a parecer inéditos: nova SOL com os mesmos fatos aparece como 'fatos já "
              "exportados' (pela SOL excluída) e a aprovação exige ciência",
              rel.get(sol_a, {}).get("classificacao") == "FATOS_JA_EXPORTADOS" and any(sol_a in x for x in d["aprovacao_exige_ciencia"])
              and c8 == 409 and c9 == 200, f"{rel.get(sol_a, {}).get('texto')} {c8} {c9}")
    _, lx = req("GET", "/solicitacoes/lixeira")
    registrar("E-07 lixeira lista as excluídas definitivamente com o que permanece (registro mínimo)",
              {sol_p, sol_r, sol_a} <= {x["sol"] for x in lx.get("excluidas_definitivamente", [])}, [x["sol"] for x in lx.get("excluidas_definitivamente", [])])
    return sol_n


def importacao_desativada(sol):
    c, r = req("GET", f"/solicitacoes/{sol}/importacao")
    c2, r2 = req("POST", f"/solicitacoes/{sol}/importacao", {})
    p = subprocess.run([sys.executable, "-I", str(RAIZ / "COORDENADOR-GERAL" / "ferramentas" / "coordenador.py"), "registrar-aceite", "--sol", sol,
                        "--processo", "X", "--chave", "Y", "--diferenca", "0"], capture_output=True, encoding="utf-8")
    registrar("V-01 Importação VGROW desativada: rotas respondem 410 e o Coordenador recusa os comandos exclusivos; exportação TXT continua",
              c == 410 and c2 == 410 and json.loads(p.stdout).get("resultado") == "ESPECIALISTA_DESATIVADO"
              and (TMP / "LIBERADOS" / EMP["id"]).exists(), f"{c} {c2} {p.stdout[:120]}")


def limpeza():
    ocioso()
    srv.shutdown()
    srv.server_close()
    antes = todos()
    sols = sorted(antes["solicitacoes"])
    previa = subprocess.run([sys.executable, "-I", str(RAIZ / "COORDENADOR-GERAL" / "ferramentas" / "arquivar_demonstracoes.py")],
                            capture_output=True, encoding="utf-8")
    nada_mudou = todos() == antes and (TMP / "CLIENTES" / EMP["id"]).exists()
    p = subprocess.run([sys.executable, "-I", str(RAIZ / "COORDENADOR-GERAL" / "ferramentas" / "arquivar_demonstracoes.py"), "--executar",
                        "--destino", str(TMP / "arquivo")], capture_output=True, encoding="utf-8")
    r = json.loads(p.stdout)
    depois = todos()
    copia = Path(r["copia"])
    man = json.loads((copia / "MANIFESTO.json").read_text(encoding="utf-8"))
    conferida = all(hashlib.sha256((copia / a["copia"]).read_bytes()).hexdigest() == a["sha256"] for a in man["arquivos"])
    reg_arq = json.loads((copia / "registro" / "solicitacoes.json").read_text(encoding="utf-8"))
    registrar("L-01 limpeza: prévia não altera nada; execução arquiva SÓ a empresa fictícia e suas SOLs com cópia de recuperação "
              "conferida (manifesto sha256); registro ativo vazio; nada sobra em CLIENTES/LIBERADOS/runtime",
              json.loads(previa.stdout).get("executado") is False and nada_mudou and r["executado"] and r["sols"] == sols and conferida
              and not man["divergentes"] and depois["solicitacoes"] == {} and not (TMP / "CLIENTES" / EMP["id"]).exists()
              and not (TMP / "LIBERADOS" / EMP["id"]).exists() and not list((TMP / "runtime" / "execucoes").iterdir())
              and sorted(reg_arq["solicitacoes"]) == sols and r["remocao_pendente"] == [],
              f"copiados={r.get('arquivos_copiados')} sols={r.get('sols')}")
    maior = max(int(s.rsplit("-", 1)[1]) for s in sols + list(antes.get("registros_minimos", {})))
    minimos = depois.get("registros_minimos", {})
    registrar("L-02 limpeza preserva a proteção contra duplicação (registro mínimo dos fatos exportados) e a sequência de números SOL",
              int(depois["sequencia_sol"]["2026"]) == maior and any(m.get("situacao") == "ARQUIVADA_LIMPEZA" and m.get("fatos_exportados")
                                                                    for m in minimos.values()), f"seq={depois.get('sequencia_sol')} minimos={sorted(minimos)}")
    return maior


def main():
    global srv
    try:
        am.EMPRESAS["A"].update(EMP)
        am.preparar(servidor.pasta_runtime(), cenarios=["A"])
        srv = servidor.iniciar(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        sol_a = saidas_e_revogacao()
        sol_n = exclusoes(sol_a)
        importacao_desativada(sol_n)
        limpeza()
    except Exception as exc:
        import traceback
        registrar("X-00 execução interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-600:]}")
    finally:
        try:
            srv.shutdown()
            srv.server_close()
        except Exception:
            pass
        am.EMPRESAS["A"].clear()
        am.EMPRESAS["A"].update(ORIGINAL_A)
        shutil.rmtree(TMP, ignore_errors=True)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {c}  — {d}")
    for i in INFO:
        print("INFO  " + i)
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
