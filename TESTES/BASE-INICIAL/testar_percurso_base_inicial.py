"""Percurso completo com BASE INICIAL pela API REAL e executores locais reais — ambiente ISOLADO, dados FICTÍCIOS (amostra A).

Empresa fictícia → balancete de encerramento de 30/09/2026 (PDF no layout do Domínio, gerado) → contas aplicadas (sintéticas da
hierarquia incluídas) → book (gerado) → ciências → confirmação → documentos de outubro → Conciliação usa a base confirmada →
aprovação → TXT + Excel dos lançamentos + balancete (hierarquia, saldo inicial/final D/C, versão da base) da MESMA versão aprovada →
mudança na base depois da aprovação bloqueia a entrega (vigência). Nada é importado no Domínio.

Uso: .venv/Scripts/python.exe -I TESTES/BASE-INICIAL/testar_percurso_base_inicial.py
"""
import base64
import hashlib
import http.client
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
TMP = Path(tempfile.mkdtemp(prefix="prime-percurso-base-"))
for k, v in {"AGENTES_PRIME_RUNTIME": TMP / "runtime", "AGENTES_PRIME_REGISTRO_SOL": TMP / "controle" / "solicitacoes.json",
             "AGENTES_PRIME_ORDEM_ATIVA": TMP / "ordem-ativa.json", "AGENTES_PRIME_CLAUDE": TMP / "claude-inexistente.exe",
             "LOCALAPPDATA": TMP / "localappdata", "AGENTES_PRIME_LIBERADOS": TMP / "LIBERADOS", "AGENTES_PRIME_CLIENTES": TMP / "CLIENTES"}.items():
    os.environ[k] = str(v)
(TMP / "CLIENTES").mkdir()
(TMP / "controle").mkdir()
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(RAIZ / "TESTES" / "BASE-INICIAL"))
import amostra_ficticia as am  # noqa: E402
import ficticios as f  # noqa: E402
import servidor  # noqa: E402
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado as _ai  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

D = Decimal
EMP = {"id": "AMOSTRA-BASE-TMP", "nome": "EMPRESA AMOSTRA BASE FICTICIA LTDA", "cnpj": "90.080.080/0001-25", "conta": "55555-5"}
ORIGINAL_A = dict(am.EMPRESAS["A"])
resultados = []
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


def registro():
    return _ai.registro_isolado()["solicitacoes"]


def ocioso(limite=600):
    fim = time.time() + limite
    while time.time() < fim:
        if not servidor.EM_EXECUCAO["sol"] and not servidor.EM_FINANCEIRO["sol"] and not any(
                str(s.get("estado", "")).endswith("_EM_ANDAMENTO") or s.get("estado") == "DOCUMENTOS_EM_ANDAMENTO" for s in registro().values()):
            return True
        time.sleep(0.3)
    return False


def enviar(docs):
    ocioso()
    c, d = req("POST", "/lotes", {"empresa": EMP["id"], "competencia": "2026-10", "fluxo": "DOCUMENTOS",
                                  "instrucao": "Receber os documentos de outubro/2026 e preparar o fechamento (SIMULAÇÃO)."})
    assert c == 201, (c, d)
    for nome, conteudo in docs.items():
        c, r = req("PUT", f"/lotes/{d['lote']}/arquivos", conteudo, {"X-Nome-Arquivo": nome, "X-Sha256": hashlib.sha256(conteudo).hexdigest(),
                                                                       "Content-Type": "application/octet-stream"})
        assert c == 201, (nome, c, r)
    c, r = req("POST", f"/lotes/{d['lote']}/iniciar", {"conferencia_humana": True})
    assert c == 202, (c, r)
    time.sleep(0.5)
    ocioso()
    return r["sol"]


def balancete_da_amostra():
    """Balancete FICTÍCIO de 30/09/2026 coerente com a amostra A: analíticas do plano da amostra (saldos do documento de abertura
    da amostra) + sintéticas da hierarquia (códigos 9xxx, inexistentes no plano). Sintética = soma das analíticas."""
    analiticas = {k: (cod, desc) for cod, k, desc, _ in am.PLANO}
    saldo = {k: (D(am.ABERTURA[cod][0]) * (1 if am.ABERTURA[cod][1] == "D" else -1) if cod in am.ABERTURA else D("0"))
             for k, (cod, _) in analiticas.items()}
    nomes = {"1": "ATIVO", "1.1": "ATIVO CIRCULANTE", "1.1.1": "DISPONIBILIDADES", "1.1.2": "CREDITOS", "2": "PASSIVO",
             "2.1": "PASSIVO CIRCULANTE", "2.1.1": "FORNECEDORES", "2.1.2": "OBRIGACOES TRABALHISTAS", "2.1.3": "PROVISOES",
             "2.1.4": "OBRIGACOES TRIBUTARIAS", "3": "RECEITAS", "3.1": "RECEITA BRUTA", "3.1.1": "SERVICOS", "3.1.9": "DEDUCOES",
             "4": "DESPESAS", "4.1": "DESPESAS OPERACIONAIS", "4.1.1": "PESSOAL", "4.2": "OUTRAS DESPESAS", "4.2.1": "GERAIS"}
    sint = sorted(nomes, key=lambda k: [int(x) for x in k.split(".")])
    codigos = {k: str(9000 + i) for i, k in enumerate(sint, 1)}
    linhas = []
    for k in sorted(list(nomes) + list(analiticas), key=lambda k: [int(x) for x in k.split(".")]):
        if k in nomes:
            s = sum((v for a, v in saldo.items() if a.startswith(k + ".")), D("0"))
            linhas.append((codigos[k], k, nomes[k], s, D("0"), D("0"), s))
        else:
            cod, desc = analiticas[k]
            linhas.append((cod, k, desc, saldo[k], D("0"), D("0"), saldo[k]))
    return linhas


def b64(x):
    return base64.b64encode(x).decode()


def percurso():
    am.EMPRESAS["A"].update(EMP)
    am.preparar(servidor.pasta_runtime(), cenarios=["A"])
    emp = EMP["id"]
    contas = balancete_da_amostra()
    pdf = f.pdf_balancete(EMP["nome"], EMP["cnpj"], "01/09/2026", "30/09/2026", contas, por_pagina=16)
    c, prev = req("POST", f"/empresas/{emp}/base-balancete", {"competencia": "2026-10", "nome": "balancete-2026-09.pdf", "conteudo": b64(pdf)})
    registrar("P-01 balancete do mês anterior lido pela API: contas extraídas, período e CNPJ conferidos, pronto para salvar",
              c == 200 and prev["pode_salvar"] and prev["totais"]["contas_extraidas"] == len(contas) and not prev["conferencia"]["bloqueios"],
              (c, prev.get("totais"), prev.get("conferencia")))
    req("POST", f"/empresas/{emp}/base-balancete", {"competencia": "2026-10", "token": prev["token"], "salvar": True, "confirmado": True})
    c, cmp_ = req("POST", f"/empresas/{emp}/base-contas", {"competencia": "2026-10"})
    grupos = {a["classificacao"]: a["grupo_sugerido"] for a in cmp_["ancoras_grupo"]}
    c, sit = req("POST", f"/empresas/{emp}/base-contas", {"competencia": "2026-10", "salvar": True, "confirmado": True, "grupos": grupos})
    c, e = req("GET", f"/empresas/{emp}")
    plano = {x["codigo"]: x for x in e["plano"]}
    registrar("P-02 contas aplicadas: as 23 analíticas da amostra ficam iguais (nada substituído) e as sintéticas da hierarquia entram no "
              "plano; piloto suspenso até reconferir o cadastro",
              len(cmp_["iguais"]) == 23 and len(cmp_["novas"]) == len(contas) - 23 and plano["9001"]["tipo"] == "SINTETICA"
              and plano["1101"]["grupo"] == "ATIVO" and not e["piloto"], (len(cmp_["iguais"]), len(cmp_["novas"])))
    comp = [("1121-CLIENTES", "1.1.2.01", "CLIENTES", "Itens em aberto",
             [("2026-08-20", "NF 90", "Cliente Ficticio", 10000.0, 0, "")]),
            ("2101-FORNECEDORES", "2.1.1.01", "FORNECEDORES", "Itens em aberto", [("2026-09-10", "NF 7", "Fornecedor Ficticio", 0, 3000.0, "")])]
    book = f.book_padrao(EMP["nome"], EMP["cnpj"], "09/2026", "2026-09-30", contas, comp)
    c, pb = req("POST", f"/empresas/{emp}/base-book", {"competencia": "2026-10", "nome": "book-2026-09.xlsx", "conteudo": b64(book)})
    req("POST", f"/empresas/{emp}/base-book", {"competencia": "2026-10", "token": pb["token"], "salvar": True, "confirmado": True})
    c, s = req("GET", f"/empresas/{emp}/base-inicial?competencia=2026-10")
    pend = [x["chave"] for x in s["definicoes"] if x["bloqueia_confirmacao"] and not x.get("resolvida")]
    c2, recusa = req("POST", f"/empresas/{emp}/base-confirmar", {"competencia": "2026-10", "frase": f"CONFIRMO BASE {emp}"})
    comp_conf = pb["confronto"]["composicoes"]
    registrar("P-03 book confrontado: 2 composições iguais ao balancete com evidência e confirmação PENDENTES; sem definições "
              "bloqueantes a próxima ação é a confirmação; frase errada recusada",
              pb["confronto"]["resumo"]["iguais_ao_balancete"] == 2 and all(x["documentos_suporte"]["situacao"] == "PENDENTE" for x in comp_conf)
              and c2 == 400 and "CONFIRMO BASE INICIAL" in s["proxima_acao"] and not pend and s["situacao"] == "RASCUNHO",
              (pb["confronto"]["resumo"], s["proxima_acao"], recusa))
    for chave in pend:
        req("POST", f"/empresas/{emp}/base-ciencia", {"competencia": "2026-10", "chave": chave, "justificativa": "Ciência de teste fictício.",
                                                      "confirmado": True})
    c, s = req("POST", f"/empresas/{emp}/base-confirmar", {"competencia": "2026-10", "frase": f"CONFIRMO BASE INICIAL {emp} 2026-10"})
    registrar("P-04 base inicial CONFIRMADA com a frase exata; as 6 etapas concluídas", c == 200 and s["situacao"] == "CONFIRMADA"
              and all(x["feito"] for x in s["etapas"]), (c, s.get("situacao"), [x["falta"] for x in s.get("etapas", [])]))
    req("POST", f"/empresas/{emp}/piloto", {"frase": f"CONFIRMO PILOTO {emp}"})
    sol = enviar(am.documentos("A"))
    conc = json.loads(servidor.ultimo_concluido_caminho(sol, "conciliacao").read_text(encoding="utf-8"))
    vb = next((v for v in conc["verificacoes"] if v["id"] == "CONC-A-BASE-INICIAL"), {})
    registrar("P-05 Conciliação usa a base CONFIRMADA (saldos de abertura do balancete anterior; documento de abertura da amostra "
              "coerente, sem conflito)",
              vb.get("resultado") == "CONFERIDO" and conc["base_inicial"]["versao"] == s["versao"], vb.get("justificativa", "")[:200])
    c, r = req("POST", f"/solicitacoes/{sol}/aprovacao", {"acao": "aprovar", "frase": f"APROVO FECHAMENTO {sol}",
                                                          "justificativa": "Fechamento ficticio conferido.", "confirmado": True})
    ap = registro()[sol].get("aprovacao") or {}
    anexos = {t: servidor.caminho_registrado(a["arquivo"]) for t, a in (ap.get("anexos") or {}).items()}
    txt = servidor.caminho_registrado(ap["arquivo_txt"]) if ap.get("arquivo_txt") else None
    ok = c == 200 and txt and txt.is_file() and set(anexos) == {"excel", "balancete"}
    registrar("P-06 aprovação gera TXT, Excel dos lançamentos e balancete da MESMA versão (sha256 registrados juntos)",
              ok and all(hashlib.sha256(anexos[t].read_bytes()).hexdigest() == ap["anexos"][t]["sha256"] for t in anexos),
              (c, (r.get("liberacao") or {}).get("situacao") if isinstance(r, dict) else r))
    if not ok:
        return
    wb = load_workbook(io.BytesIO(anexos["balancete"].read_bytes()))
    rows = [x for x in wb["Balancete"].iter_rows(min_row=2, values_only=True) if x[0] and str(x[0]).isdigit()]
    lin = {str(x[0]): x for x in rows}
    ident = {k: v for k, v in wb["Identificação"].iter_rows(values_only=True)}
    saldos = {x["conta"]: x for x in conc["saldos_contas"]}
    final_1101 = D(saldos["1101"]["saldo_final"])
    soma_ativo = sum((D(str(x[9])) * (-1 if x[10] == "C" else 1) for x in rows if x[3] == "A" and str(x[1]).startswith("1.")), D("0"))
    linha_ativo = lin["9001"]
    registrar("P-07 balancete final: saldo inicial da base + movimento aprovado = saldo final (exato); sintética ATIVO = soma das "
              "analíticas do grupo; identifica a versão da base inicial e a SIMULAÇÃO",
              (D(str(lin["1101"][5])), lin["1101"][6]) == (D("40000.00"), "D") and D(str(lin["1101"][9])) * (1 if lin["1101"][10] == "D" else -1) == final_1101
              and linha_ativo[3] == "S" and D(str(linha_ativo[9])) * (1 if linha_ativo[10] == "D" else -1) == soma_ativo
              and f"versão {s['versao']}" in str(ident.get("Base inicial")) and "SIMULAÇÃO" in str(ident.get("Aviso")),
              (lin["1101"], linha_ativo, str(ident.get("Base inicial"))[:80]))
    # mudança na base depois da aprovação: a entrega fica bloqueada (vigência), nada é revogado automaticamente
    req("POST", f"/empresas/{emp}/base-saldo-inicial", {"competencia": "2026-10", "codigo": "9001", "saldo": "0", "justificativa": "x" * 6,
                                                        "confirmado": True})                     # recusado (sintética do balancete)
    book2 = f.book_padrao(EMP["nome"], EMP["cnpj"], "09/2026", "2026-09-30", contas, comp[:1])
    c, pb2 = req("POST", f"/empresas/{emp}/base-book", {"competencia": "2026-10", "nome": "book-v2.xlsx", "conteudo": b64(book2)})
    req("POST", f"/empresas/{emp}/base-book", {"competencia": "2026-10", "token": pb2["token"], "salvar": True, "confirmado": True})
    c, baixa = req("GET", f"/solicitacoes/{sol}/txt-dominio")
    c3, _ = req("GET", f"/solicitacoes/{sol}/saidas/balancete")
    registrar("P-08 base alterada depois da aprovação (novo book): base volta a RASCUNHO e o download do TXT/balancete fica bloqueado "
              "(fonte 'base inicial' alterada); aprovação não é revogada automaticamente",
              c != 200 and c3 != 200 and registro()[sol]["estado"] == "FECHAMENTO_APROVADO"
              and req("GET", f"/empresas/{emp}/base-inicial?competencia=2026-10")[1]["situacao"] == "RASCUNHO",
              (c, str(baixa)[:200]))


def foto_operacional():
    arqs = sorted((str(p.relative_to(RAIZ)), p.stat().st_size, p.stat().st_mtime_ns) for p in (RAIZ / "CLIENTES").rglob("*") if p.is_file())
    reg = RAIZ / "COORDENADOR-GERAL" / "controle" / "solicitacoes.json"
    return arqs, hashlib.sha256(reg.read_bytes()).hexdigest() if reg.is_file() else None, (RAIZ / "LIBERADOS").exists()


def main():
    global srv
    antes = foto_operacional()
    try:
        srv = servidor.iniciar(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        percurso()
    except Exception as exc:
        import traceback
        registrar("P-XX percurso interrompido", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-700:]}")
    finally:
        if srv:
            srv.shutdown()
            srv.server_close()
        am.EMPRESAS["A"].clear()
        am.EMPRESAS["A"].update(ORIGINAL_A)
        registrar("P-09 ambiente operacional intocado (CLIENTES/, registro e LIBERADOS/ reais)", foto_operacional() == antes)
        shutil.rmtree(TMP, ignore_errors=True)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {c}  — {d}")
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
