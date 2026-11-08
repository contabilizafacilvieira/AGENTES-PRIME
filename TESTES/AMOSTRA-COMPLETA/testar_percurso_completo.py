"""Percurso completo integrado (API real + executores locais reais) — amostra fictícia, ambiente 100% ISOLADO.

Documentos → Financeiro / DP / Fiscal → Contabilidade (Bancos, DP, Fiscal) → Conciliação → Coordenador → Supervisor → TXT.
Somente dados fictícios. Cadastros (AGENTES_PRIME_CLIENTES), registro, runtime, ordem ativa e LIBERADOS ficam numa pasta
temporária: nada é criado em CLIENTES/, no registro real nem em LIBERADOS/ do projeto (conferido em P-03). Nada é importado
no Domínio. Falhas de gravação/registro são simuladas por substituição de função no processo do teste; o arquivo travado na
revogação é um handle real aberto (Windows).

Uso: .venv/Scripts/python.exe -I TESTES/AMOSTRA-COMPLETA/testar_percurso_completo.py
"""
import hashlib
import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
TMP = Path(tempfile.mkdtemp(prefix="prime-percurso-"))
os.environ["AGENTES_PRIME_RUNTIME"] = str(TMP / "runtime")
os.environ["AGENTES_PRIME_REGISTRO_SOL"] = str(TMP / "registro.json")
os.environ["AGENTES_PRIME_ORDEM_ATIVA"] = str(TMP / "ordem-ativa.json")
os.environ["AGENTES_PRIME_CLAUDE"] = str(TMP / "claude-inexistente.exe")
os.environ["LOCALAPPDATA"] = str(TMP / "localappdata")
os.environ["AGENTES_PRIME_LIBERADOS"] = str(TMP / "LIBERADOS")
os.environ["AGENTES_PRIME_CLIENTES"] = str(TMP / "CLIENTES")
(TMP / "CLIENTES").mkdir()
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import amostra_ficticia as am  # noqa: E402
import servidor  # noqa: E402
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado as _ai  # noqa: E402

ORIGINAIS = {k: dict(v) for k, v in am.EMPRESAS.items()}
TESTE = {"A": {"id": "AMOSTRA-A-TESTE-TMP", "cnpj": "90.080.080/0001-25"}, "B": {"id": "AMOSTRA-B-TESTE-TMP", "cnpj": "90.090.090/0001-41"}}
CLIENTES_TMP = TMP / "CLIENTES"
resultados = []
srv = None
INFORMACOES = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:500]))


def informar(rotulo, d):
    """Números reais do percurso (para conferência com o LEIA-ME); não são verificações."""
    r = (d.get("conciliacao") or {}).get("resultado") or {}
    INFORMACOES.append(f"{rotulo}: conciliação {r.get('resumo')} parcial={r.get('alcance', {}).get('parcial')} · "
                       f"Contab/Fiscal {d.get('contabilfiscal', {}).get('resumo') if d.get('contabilfiscal') else None} · "
                       f"Contab/DP {d.get('contabdp', {}).get('resumo') if d.get('contabdp') else None} · não aplicáveis "
                       f"{[v['id'] for v in r.get('verificacoes', []) if v['resultado'] == 'NAO_APLICAVEL']}")


def dv_cnpj(base12: str) -> str:
    def d(n):
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(n):]
        r = sum(int(a) * b for a, b in zip(n, pesos)) % 11
        return "0" if r < 2 else str(11 - r)
    n = base12 + d(base12)
    n += d(n)
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


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


def livre(limite=300):
    fim = time.time() + limite
    while time.time() < fim:
        if not servidor.EM_EXECUCAO["sol"] and not servidor.EM_FINANCEIRO["sol"]:
            return True
        time.sleep(0.3)
    return False


def esperar(sol, limite=600):
    fim = time.time() + limite
    while time.time() < fim:
        s = registro().get(sol, {})
        if livre(5) and not str(s.get("estado", "")).endswith("_EM_ANDAMENTO") and s.get("estado") not in (None, "DOCUMENTOS_EM_ANDAMENTO"):
            return s
        time.sleep(0.3)
    return registro().get(sol, {})


def enviar(cenario, docs=None, instrucao=None):
    livre()
    e = am.EMPRESAS[cenario]
    c, d = req("POST", "/lotes", {"empresa": e["id"], "competencia": "2026-10", "fluxo": "DOCUMENTOS",
                                  "instrucao": instrucao or "Receber os documentos de outubro/2026, distribuir por área e preparar o fechamento (SIMULAÇÃO)."})
    assert c == 201, (c, d)
    for nome, conteudo in (docs or am.documentos(cenario)).items():
        c, r = req("PUT", f"/lotes/{d['lote']}/arquivos", conteudo, {"X-Nome-Arquivo": nome, "X-Sha256": hashlib.sha256(conteudo).hexdigest(),
                                                                       "Content-Type": "application/octet-stream"})
        assert c == 201, (nome, c, r)
    c, r = req("POST", f"/lotes/{d['lote']}/iniciar", {"conferencia_humana": True})
    assert c == 202, (c, r)
    return r["sol"], esperar(r["sol"])


def detalhe(sol):
    c, d = req("GET", f"/solicitacoes/{sol}")
    assert c == 200 and isinstance(d, dict) and "plano_etapas" in d, f"detalhe {sol}: {c} {str(d)[:300]}"
    return d


def aprovar(sol, ciente=False):
    corpo = {"acao": "aprovar", "frase": f"APROVO FECHAMENTO {sol}", "justificativa": "Fechamento ficticio conferido.", "confirmado": True}
    if ciente:
        corpo["ciente_exportados"] = True
    return req("POST", f"/solicitacoes/{sol}/aprovacao", corpo)


def revogar(sol):
    return req("POST", f"/solicitacoes/{sol}/aprovacao", {"acao": "revogar", "justificativa": "Revogacao de teste ficticio.", "confirmado": True})


def acao_txt(sol, acao):
    return req("POST", f"/solicitacoes/{sol}/txt-dominio/{acao}", {"confirmado": True, "justificativa": "Ação explícita de teste fictício."})


def baixar(sol):
    return req("GET", f"/solicitacoes/{sol}/txt-dominio")


def liberados(emp):
    pasta = TMP / "LIBERADOS" / emp / "2026-10"
    return sorted(p.name for p in pasta.iterdir()) if pasta.exists() else []


def lib(sol):
    return (registro()[sol].get("aprovacao") or {}).get("liberacao_dominio")


def chaves(lancamentos, status):
    return sorted(((l.get("debito") or {}).get("codigo"), (l.get("credito") or {}).get("codigo"), f"{Decimal(str(l['valor'])):.2f}")
                  for l in lancamentos if l["status"] in status)


ESPERADO_BANCOS = sorted([("1101", "1121", "10000.00"), ("2101", "1101", "3000.00"), ("2131", "1101", "500.00"),
                          ("1101", "1121", "6000.00"), ("2111", "1101", "7000.00"), ("4202", "1101", "45.00")])
ESPERADO_FISCAL = sorted([("1121", "3101", "6000.00"), ("1121", "3101", "4000.00"), ("3191", "2131", "200.00"),
                          ("3192", "2132", "65.00"), ("3193", "2133", "300.00")])
ESPERADO_DP = sorted([("4101", "2111", "8000.00"), ("2111", "2112", "700.00"), ("2111", "2114", "300.00"), ("4102", "2112", "2100.00"),
                      ("4103", "2113", "640.00"), ("4104", "2121", "1000.00"), ("4105", "2122", "666.67")])
PROPOSTO = ("PROPOSTO", "PROPOSTO_PARA_CONFERENCIA")
TECNICO = re.compile(r"RECEBIDOS|\.txt|\.csv|L-\d{8}|MOV-|DPD-|\\", re.I)


class Falha:
    """Substitui temporariamente uma função do servidor (falha simulada); restaura sempre."""
    def __init__(self, nome, nova):
        self.nome, self.nova = nome, nova

    def __enter__(self):
        self.original = getattr(servidor, self.nome)
        setattr(servidor, self.nome, self.nova(self.original))

    def __exit__(self, *a):
        setattr(servidor, self.nome, self.original)


def recusar_registro(situacao):
    def fabrica(original):
        def cli(*args):
            if "registrar-liberacao" in args and situacao in args:
                return 1, {"resultado": "ERRO_SIMULADO", "motivo": f"falha simulada no registro ({situacao})"}
            return original(*args)
        return cli
    return fabrica


def cenario_a():
    emp = TESTE["A"]["id"]
    sol, s = enviar("A")
    d = detalhe(sol)
    plano = {e["etapa"]: e["situacao"] for e in s.get("plano_etapas", [])}
    registrar("A-01 percurso completo: todas as etapas do plano concluídas e a SOL volta ao Supervisor (SIMULAÇÃO)",
              s.get("estado") == "AGUARDANDO_SUPERVISOR" and plano == {e: "CONCLUIDA" for e in
              ("FINANCEIRO", "DP", "FISCAL", "BANCOS", "CONTABILIDADE_DP", "CONTABILIDADE_FISCAL", "CONCILIACAO")}, plano)
    t = s.get("tarefas_areas", {})
    registrar("A-02 Documentos distribuiu por área sem triagem pendente",
              all(t.get(a, {}).get("documentos") for a in ("FINANCEIRO", "DP", "FISCAL", "CONCILIACAO"))
              and not (t.get("TRIAGEM") or {}).get("documentos") and not s.get("pendencias_documentos"),
              {a: len(v.get("documentos", [])) for a, v in t.items()})
    fin = req("GET", f"/solicitacoes/{sol}/financeiro")[1]
    ban = fin["bancos"]["lancamentos"]
    registrar("A-03 Financeiro conferiu 6 movimentos e Bancos propôs os 6 lançamentos esperados (regras de TESTE fictício, identidade = movimento)",
              fin["financeiro"]["resumo"]["movimentos"] == 6 and chaves(ban, PROPOSTO) == ESPERADO_BANCOS and len(ban) == 6
              and all(l.get("identidade", "").startswith("BANCO:MOV-") and l.get("regra_situacao") == "TESTE_FICTICIO" for l in ban),
              chaves(ban, PROPOSTO) + [l["pendencias"] for l in ban if l["status"] != "PROPOSTO"])
    registrar("A-04 Contabilidade/Fiscal: receitas das NFS-e e provisões pelas apurações; guia sem provisão",
              chaves(d["contabilfiscal"]["lancamentos"], PROPOSTO) == ESPERADO_FISCAL
              and all(x["tipo"] == "GUIA" for x in d["contabilfiscal"].get("documentos_sem_proposta", [])),
              [(l["evento"], l["status"], l["pendencias"][:1]) for l in d["contabilfiscal"]["lancamentos"]])
    registrar("A-05 DP leu os demonstrativos e Contabilidade/DP propôs os 7 lançamentos esperados",
              d["dp"]["resumo"]["pendencias"] == 0 and chaves(d["contabdp"]["lancamentos"], PROPOSTO) == ESPERADO_DP,
              [(l["evento"], l["status"], l["pendencias"][:1]) for l in d["contabdp"]["lancamentos"]] + d["dp"]["pendencias"][:2])
    dpf = d["contabdp"]["lancamentos"] + d["contabilfiscal"]["lancamentos"]
    registrar("A-05b DP/Fiscal: competência do fato separada da data do lançamento (política de TESTE da amostra, identificada); "
              "histórico sem caminho técnico; identidade rastreável",
              all(l["competencia"] == "2026-10" and l["data"] == "2026-10-31" and "TESTE_FICTICIO" in (l.get("data_origem") or "")
                  and not TECNICO.search(l["historico"]) and l.get("identidade") for l in dpf),
              [(l["evento"], l.get("data"), l.get("data_origem"), l["historico"]) for l in dpf][:3])
    informar("Cenário A", d)
    conc = d["conciliacao"]
    r = conc["resultado"]
    contagem = {k: sum(v["resultado"] == k for v in r["verificacoes"]) for k in ("CONFERIDO", "DIVERGENTE", "PENDENTE", "NAO_APLICAVEL", "NAO_DETERMINADO")}
    saldo_banco = next((v for v in r["verificacoes"] if v["id"] == "CONC-C-SALDO-1101"), {})
    pe = r["resumo"].get("conferidas_por_evidencia") or {}
    registrar("A-06 Conciliação integral: sem divergência/pendência/indeterminação; saldo do banco 45.455,00 contra o extrato; "
              "conferências separadas por evidência (externa, controle interno, consistência do sistema)",
              contagem["DIVERGENTE"] == contagem["PENDENTE"] == contagem["NAO_DETERMINADO"] == 0 and contagem["CONFERIDO"] > 0
              and not r["alcance"].get("parcial") and saldo_banco.get("resultado") == "CONFERIDO" and saldo_banco.get("evidencia") == "DOCUMENTO_EXTERNO"
              and Decimal(str(saldo_banco["valores"]["encontrado"])) == Decimal("45455.00") and conc["vigente"]
              and sum(pe.values()) == contagem["CONFERIDO"] and pe.get("DOCUMENTO_EXTERNO", 0) > 0 and pe.get("CONTROLE_INTERNO", 0) > 0,
              f"{contagem} evidencias={pe} " + str([(v["id"], v["resultado"], v["justificativa"][:90]) for v in r["verificacoes"]
                                                    if v["resultado"] in ("DIVERGENTE", "PENDENTE", "NAO_DETERMINADO")][:6]))
    saldos = {x["conta"]: x for x in (r.get("saldos_contas") or [])}
    esperado_saldos = {"1101": "45455.00", "1121": "4000.00", "2101": "0.00", "2111": "0.00", "2112": "-2800.00", "2113": "-640.00",
                       "2114": "-300.00", "2121": "-1000.00", "2122": "-666.67", "2131": "-200.00", "2132": "-65.00", "2133": "-300.00"}
    obtidos = {c: f"{Decimal(str((saldos.get(c) or {}).get('saldo_final'))):.2f}" if (saldos.get(c) or {}).get("saldo_final") is not None else None
               for c in esperado_saldos}
    registrar("A-07 saldos finais calculados pela Conciliação conferem com a amostra (positivo = devedor)", obtidos == esperado_saldos, obtidos)
    nada = (not (TMP / "LIBERADOS").exists() and all(not l.get("aprovado") and not l.get("escriturado") for l in dpf)
            and s.get("escopo_resultado") == "SIMULACAO_CONCILIADA_NO_ALCANCE")
    registrar("A-08 nada aprovado, escriturado ou liberado antes da aprovação", nada, s.get("escopo_resultado"))
    registrar("A-09 aprovação disponível (sem impedimentos) e nenhuma definição pendente na amostra (regras de TESTE identificadas)",
              d.get("aprovacao_impedimentos") == [] and d.get("definicoes_necessarias") == [] and d["situacao_txt"]["situacao"] == "SEM_APROVACAO_VIGENTE",
              f"{d.get('aprovacao_impedimentos')} {d.get('definicoes_necessarias')}")
    c1, _ = req("POST", f"/solicitacoes/{sol}/aprovacao", {"acao": "aprovar", "frase": "aprovo", "justificativa": "teste ficticio", "confirmado": True})
    c2, r2 = aprovar(sol)
    s2 = registro()[sol]
    mov = req("GET", f"/solicitacoes/{sol}/financeiro")[1]["financeiro"]["movimentos"][0]
    c3, _ = req("POST", f"/solicitacoes/{sol}/financeiro/decisoes", {"movimento": mov["id"], "tipo": "CONTRAPARTIDA",
                 "dados": {"conta": "4202", "natureza_tipo": "DESPESA"}, "justificativa": "tentativa apos aprovacao"})
    ap = s2.get("aprovacao") or {}
    registrar("A-10 aprovação explícita: frase exata; registra fontes e fatos aprovados; não escritura; decisões bloqueadas depois",
              c1 == 409 and c2 == 200 and s2["estado"] == "FECHAMENTO_APROVADO" and ap.get("escrituracao") == "NAO_REALIZADA"
              and ap.get("tipo") == "FECHAMENTO_INTEGRAL_CONCILIADO" and len(ap.get("fatos_aprovados", {})) == 18
              and set(ap.get("fontes_aprovadas", {})) >= {"CADASTRO", "PLANO", "REGRAS_DP"} and c3 == 409, f"{c1} {c2} {r2} {c3}")
    txt = Path(ap.get("arquivo_txt", "-"))
    bruto = txt.read_bytes() if txt.is_file() else b""
    linhas = bruto.decode("cp1252").split("\r\n")[:-1] if bruto else []
    esperadas = {"25/10/2026;1101;1121;6000;;", "31/10/2026;4105;2122;666,67;;PROVISAO DE 13 SALARIO COMPETENCIA 10/2026 REF. PR-2026-10;1;;;",
                 "31/10/2026;3192;2132;65;;"}
    layout = all(len(l.split(";")) == 10 and l.split(";")[6] == "1" and l.split(";")[7:] == ["", "", ""]
                 and re.fullmatch(r"\d{2}/\d{2}/\d{4}", l.split(";")[0]) and "." not in l.split(";")[3] and l.split(";")[5]
                 and not TECNICO.search(l.split(";")[5]) for l in linhas)
    auditoria = json.loads((TMP / "runtime" / "execucoes" / sol / ap.get("txt_auditoria", "-") / "auditoria.json").read_text(encoding="utf-8")) \
        if ap.get("txt_auditoria") else {}
    registrar("A-10b TXT liberado SÓ após a aprovação (duas fases registradas): 18 linhas em partida simples, IniciaLote=1, cp1252/CRLF, "
              "valores exatos, Complemento sem caminho técnico; auditoria linha → lançamento/documento fora do TXT",
              lib(sol) == "LIBERADO_PARA_IMPORTACAO_MANUAL" and txt.parent == TMP / "LIBERADOS" / emp / "2026-10"
              and len(linhas) == 18 == ap.get("txt_linhas") and layout and b"\r\n" in bruto and b"\n\n" not in bruto
              and all(any(l.startswith(e) for l in linhas) for e in esperadas)
              and Decimal(ap.get("txt_total")) == sum(Decimal(l.split(";")[3].replace(",", ".")) for l in linhas)
              and hashlib.sha256(bruto).hexdigest() == ap.get("txt_sha256") and len(auditoria.get("linhas", [])) == 18
              and all(a.get("lancamento") and a.get("identidade") for a in auditoria["linhas"]) and "NÃO validada" in auditoria.get("variante", "")
              and [t["situacao"] for t in ap.get("tentativas_exportacao", [])] == ["LIBERADO"] and "não significa importado" in r2["liberacao"]["mensagem"],
              f"{lib(sol)} {txt} {linhas[:3]} {r2.get('liberacao')}")
    cd, corpo = baixar(sol)
    registrar("A-10c download pela interface devolve exatamente o arquivo liberado", cd == 200 and corpo == bruto, cd)
    cg, _ = acao_txt(sol, "gerar")
    registrar("A-10d nova geração/sobrescrita recusada com TXT já liberado (sem repetição de exportação)",
              cg == 409 and [n for n in liberados(emp) if n.endswith(".txt")] == [txt.name] and len(liberados(emp)) == 3 and txt.read_bytes() == bruto, f"{cg} {liberados(emp)}")
    plano_md = CLIENTES_TMP / emp / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md"
    original = plano_md.read_bytes()
    plano_md.write_bytes(original + b"\n")
    cd1, r1 = baixar(sol)
    d1 = detalhe(sol)
    plano_md.write_bytes(original)
    cd2, _ = baixar(sol)
    registrar("A-10e plano de contas alterado DEPOIS da aprovação: download bloqueado com o motivo; volta ao restaurar o mesmo conteúdo",
              cd1 == 409 and "plano de contas" in str(r1) and d1["situacao_txt"]["download"] is False and cd2 == 200, f"{cd1} {r1} {cd2}")

    # ---- revogação simples
    c4, r4 = revogar(sol)
    s4 = registro()[sol]
    revogados = list(txt.parent.glob("*_REVOGADO-*.txt"))
    cd3, _ = baixar(sol)
    registrar("A-11 revogação: download bloqueado, TXT renomeado REVOGADO (preservado), aviso de que não estorna importação no Domínio",
              c4 == 200 and s4["estado"] == "AGUARDANDO_SUPERVISOR" and len(s4.get("aprovacoes_anteriores", [])) == 1 and not txt.exists()
              and len(revogados) == 1 and revogados[0].read_bytes() == bruto and cd3 == 404
              and s4["aprovacoes_anteriores"][-1].get("liberacao_dominio") == "REVOGADO" and "não estorna" in r4["liberacao"]["mensagem"],
              f"{s4['estado']} {revogados} {r4.get('liberacao')}")

    # ---- reaprovação da mesma SOL: fatos já exportados exigem ciência explícita
    c5, r5 = aprovar(sol)
    c6, r6 = aprovar(sol, ciente=True)
    registrar("A-12 reaprovar fatos que já saíram em TXT revogado exige ciência explícita; novo TXT sem sobrescrever o REVOGADO",
              c5 == 409 and "já exportados" in str(r5) and c6 == 200 and lib(sol) == "LIBERADO_PARA_IMPORTACAO_MANUAL"
              and registro()[sol]["aprovacao"]["ciente_fatos_ja_exportados"] is True and len([n for n in liberados(emp) if n.endswith(".txt")]) == 2 and len(liberados(emp)) == 6
              and revogados[0].exists(), f"{c5} {r5} {c6} {liberados(emp)}")

    # ---- arquivo travado na revogação
    txt = servidor.caminho_registrado(registro()[sol]["aprovacao"]["arquivo_txt"])
    trava = open(txt, "rb")
    try:
        c7, r7 = revogar(sol)
        cd4, _ = baixar(sol)
        d7 = detalhe(sol)
        c8, r8 = acao_txt(sol, "mover-revogado")
    finally:
        trava.close()
    c9, r9 = acao_txt(sol, "mover-revogado")
    ant = registro()[sol]["aprovacoes_anteriores"][-1]
    posix_rename = r7["liberacao"]["situacao"] == "REVOGADO"
    registrar("A-13 arquivo travado: aprovação revogada e download bloqueado na hora; registro diz que o arquivo NÃO foi movido; "
              "nova tentativa explícita depois de liberar o arquivo renomeia e registra",
              (posix_rename and c7 == 200 and cd4 == 404 and not txt.exists()) or
              (not posix_rename and c7 == 200 and r7["liberacao"]["situacao"] == "REVOGADO_ARQUIVO_NAO_MOVIDO" and "NÃO pôde ser renomeado" in r7["liberacao"]["mensagem"]
               and cd4 == 404 and d7["situacao_txt"]["situacao"] == "REVOGADO_ARQUIVO_NAO_MOVIDO" and c8 == 200
               and r8["liberacao"]["situacao"] == "REVOGADO_ARQUIVO_NAO_MOVIDO" and c9 == 200 and r9["liberacao"]["situacao"] == "REVOGADO"
               and not txt.exists() and ant["liberacao_dominio"] == "REVOGADO"
               and [m["movimentacao"] for m in ant["movimentacoes_revogacao"]] == ["FALHOU", "FALHOU", "RENOMEADO"]),
              f"{r7.get('liberacao')} {cd4} {r8.get('liberacao', {}).get('situacao')} {r9.get('liberacao')} {liberados(emp)}")

    # ---- falha na gravação do TXT
    def disco_cheio(_original):
        def falhar(arquivo, conteudo):
            raise OSError("disco cheio (simulado)")
        return falhar
    with Falha("gravar_exclusivo", disco_cheio):
        c10, r10 = aprovar(sol, ciente=True)
    time.sleep(1.5)
    antes = liberados(emp)
    cd5, _ = baixar(sol)
    d10 = detalhe(sol)
    c11, r11 = acao_txt(sol, "gerar")
    registrar("A-14 falha na gravação: aprovação registrada, liberação FALHOU visível, nenhum TXT novo, sem repetição automática; "
              "nova geração só por ação explícita",
              c10 == 200 and r10["liberacao"]["situacao"] == "FALHOU" and "disco cheio" in r10["liberacao"]["mensagem"]
              and not any(n.endswith(f"{sol}.txt") for n in antes) and cd5 == 404 and d10["situacao_txt"]["situacao"] == "FALHOU"
              and d10["situacao_txt"]["pode_gerar"] is True and c11 == 200 and r11["liberacao"]["situacao"] == "LIBERADO_PARA_IMPORTACAO_MANUAL",
              f"{r10.get('liberacao')} {antes} {r11.get('liberacao', {}).get('situacao')}")

    # ---- falha no registro da liberação (arquivo já gravado): retirado de uso, nunca acessível como liberado
    revogar(sol)
    with Falha("coordenador_cli", recusar_registro("LIBERADO_PARA_IMPORTACAO_MANUAL")):
        c12, r12 = aprovar(sol, ciente=True)
    nomes = liberados(emp)
    t12 = registro()[sol]["aprovacao"]["tentativas_exportacao"][-1]
    cd6, _ = baixar(sol)
    registrar("A-15 registro da liberação recusado: o arquivo gravado é retirado de uso (sem extensão .txt, preservado) e a falha registrada",
              c12 == 200 and r12["liberacao"]["situacao"] == "FALHOU" and lib(sol) == "FALHOU" and not any(n.endswith(f"{sol}.txt") for n in nomes)
              and any(n.endswith(".bloqueado") for n in nomes) and str(t12.get("arquivo_residual") or "").endswith(".bloqueado") and cd6 == 404,
              f"{r12.get('liberacao')} {nomes} {t12}")
    with Falha("coordenador_cli", recusar_registro("PREPARANDO")):
        c13, _ = acao_txt(sol, "gerar")
        s13 = registro()[sol]["aprovacao"]
    nomes13 = liberados(emp)
    c14, r14 = acao_txt(sol, "gerar")
    registrar("A-16 registro da preparação recusado: nada gravado em LIBERADOS; depois, geração explícita libera normalmente",
              c13 == 200 and s13["liberacao_dominio"] == "FALHOU" and "nenhum arquivo foi gravado" in s13.get("liberacao_motivo", "")
              and nomes13 == nomes and c14 == 200 and r14["liberacao"]["situacao"] == "LIBERADO_PARA_IMPORTACAO_MANUAL"
              and baixar(sol)[0] == 200, f"{s13.get('liberacao_motivo')} {nomes13} {r14.get('liberacao')}")

    # ---- fontes alteradas depois da Conciliação: desatualizada, etapas a rever, retomada explícita
    revogar(sol)
    regras_conc = CLIENTES_TMP / emp / "REGRAS-CONCILIACAO.json"
    dados = json.loads(regras_conc.read_text(encoding="utf-8"))
    dados["observacao"] = "versao 2 (teste)"
    regras_conc.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    d15 = detalhe(sol)
    c15, _ = req("POST", f"/solicitacoes/{sol}/areas/FINANCEIRO/retomar", {"justificativa": "teste fictício", "confirmado": True})
    c16, _ = req("POST", f"/solicitacoes/{sol}/areas/CONCILIACAO/retomar", {"justificativa": "Exigências da Conciliação alteradas.", "confirmado": True})
    esperar(sol)
    d16 = detalhe(sol)
    hist = d16["conciliacao"]["historico"]
    registrar("A-17 regra da Conciliação alterada: conferência anterior DESATUALIZADA (só Conciliação a rever), aprovação impedida; "
              "retomada explícita reexecuta só a Conciliação e preserva o histórico",
              d15["conciliacao"]["vigente"] is False and d15["conciliacao"]["rever"] == ["CONCILIACAO"]
              and any("desatualizada" in x for x in d15["aprovacao_impedimentos"]) and c15 == 409 and c16 == 202
              and d16["conciliacao"]["vigente"] is True and len(hist) == 2 and hist[0]["vigente"] is False
              and not any("desatualizada" in x for x in d16["aprovacao_impedimentos"]),
              f"{d15['conciliacao'].get('rever')} {d15['aprovacao_impedimentos'][:1]} {c15} {c16} {[h['vigente'] for h in hist]}")
    original = plano_md.read_bytes()
    plano_md.write_bytes(original + b"\n<!-- alteracao de teste -->\n")
    d17 = detalhe(sol)
    c17, r17 = aprovar(sol, ciente=True)
    cad = CLIENTES_TMP / emp / "CADASTRO.md"
    cad_original = cad.read_bytes()
    cad.write_bytes(cad_original + b"\n")
    d18 = detalhe(sol)
    plano_md.write_bytes(original)
    cad.write_bytes(cad_original)
    d19 = detalhe(sol)
    registrar("A-18 plano/cadastro alterados: etapas que os usaram indicadas para revisão e aprovação recusada; conteúdo restaurado volta a valer",
              d17["conciliacao"]["rever"] == ["BANCOS", "CONTABILIDADE_DP", "CONTABILIDADE_FISCAL", "CONCILIACAO"] and c17 == 409
              and "plano de contas" in str(r17) and "FINANCEIRO" in d18["conciliacao"]["rever"]
              and any("cadastro" in m for m in d18["conciliacao"]["motivos"]) and d19["conciliacao"]["vigente"] is True,
              f"{d17['conciliacao'].get('rever')} {c17} {d18['conciliacao'].get('rever')}")
    c20, r20 = aprovar(sol, ciente=True)
    registrar("A-19 aprovação final da SOL A (com ciência dos fatos já exportados) e TXT liberado",
              c20 == 200 and lib(sol) == "LIBERADO_PARA_IMPORTACAO_MANUAL" and baixar(sol)[0] == 200, r20.get("liberacao"))
    return sol


def cenario_duplicacao(sol_a):
    emp = TESTE["A"]["id"]
    sol2, _ = enviar("A")
    d2 = detalhe(sol2)
    rel = {r["sol"]: r for r in d2["relacao_outras_sols"]}
    c1, r1 = aprovar(sol2, ciente=True)
    registrar("D-01 segunda SOL com os MESMOS fatos de SOL aprovada: classificada como REPETIÇÃO (identidade do movimento/documento) e "
              "aprovação/exportação bloqueadas", rel.get(sol_a, {}).get("classificacao") == "REPETICAO_DE_APROVADA"
              and len(rel[sol_a].get("repetidos", [])) == 18 and any("Duplicação" in x for x in d2["aprovacao_impedimentos"]) and c1 == 409
              and liberados(emp) and not any(sol2 in n for n in liberados(emp)), f"{rel.get(sol_a)} {c1} {r1}")
    revogar(sol_a)
    d3 = detalhe(sol2)
    rel3 = {r["sol"]: r for r in d3["relacao_outras_sols"]}
    c2, _ = aprovar(sol2)
    c3, r3 = aprovar(sol2, ciente=True)
    dA = detalhe(sol_a)
    relA = {r["sol"]: r for r in dA["relacao_outras_sols"]}
    registrar("D-02 substituição: com a SOL anterior revogada, os fatos aparecem como JÁ EXPORTADOS (exigem ciência); aprovada a nova, "
              "a anterior fica bloqueada por repetição", rel3.get(sol_a, {}).get("classificacao") == "FATOS_JA_EXPORTADOS" and c2 == 409
              and c3 == 200 and lib(sol2) == "LIBERADO_PARA_IMPORTACAO_MANUAL" and relA.get(sol2, {}).get("classificacao") == "REPETICAO_DE_APROVADA"
              and any("Duplicação" in x for x in dA["aprovacao_impedimentos"]), f"{rel3.get(sol_a)} {c2} {c3} {r3.get('liberacao')}")
    e = am.EMPRESAS["A"]
    nota = (f"NFS-E - NOTA FISCAL DE SERVICOS ELETRONICA (FICTICIA)\nPRESTADOR: {e['nome']}\nCNPJ DO PRESTADOR: {e['cnpj']}\n"
            f"TOMADOR: {am.BETA[0]}\nCNPJ DO TOMADOR: {am.BETA[1]}\nNUMERO DA NOTA: 104\nDATA DE EMISSAO: 30/10/2026\n"
            "COMPETENCIA: 10/2026\nVALOR DOS SERVICOS: R$ 1.500,00\nVALOR TOTAL DA NOTA: R$ 1.500,00\n").encode("utf-8")
    sol3, _ = enviar("A", {"01_nfse_104_beta.txt": nota}, "Complemento de outubro/2026: nota emitida depois do fechamento (SIMULAÇÃO).")
    d4 = detalhe(sol3)
    rel4 = {r["sol"]: r for r in d4["relacao_outras_sols"]}
    lan = [l for l in d4["contabilfiscal"]["lancamentos"] if l["status"] in PROPOSTO]
    registrar("D-03 complemento legítimo (fato novo, NFS-e 104): classificado COMPLEMENTO em relação às SOLs aprovadas, sem impedimento "
              "de duplicação", len(lan) == 1 and rel4.get(sol2, {}).get("classificacao") == "COMPLEMENTO"
              and rel4.get(sol_a, {}).get("classificacao") == "COMPLEMENTO" and not any("Duplicação" in x for x in d4["aprovacao_impedimentos"]),
              f"{[(k, v['classificacao']) for k, v in rel4.items()]} {d4['aprovacao_impedimentos'][:2]}")
    registrar("D-04 exportado ≠ importado ≠ escriturado: nenhuma aprovação registra escrituração ou importação",
              all((x.get("aprovacao") or {}).get("escrituracao") in (None, "NAO_REALIZADA")
                  and (x.get("aprovacao") or {}).get("importacao_dominio") in (None, "NAO_REGISTRADA_PELO_APLICATIVO")
                  for x in registro().values()), "")


def empresa_real():
    """Empresa SEM o marcador fictício (tratada como real, piloto em SIMULAÇÃO) numa pasta temporária: regras propostas e confirmadas
    pelo Supervisor pela API (frase exata); percurso completo; aprovação registrada e exportação BLOQUEADA."""
    am.EMPRESAS["R"] = {"id": "EMPRESA-REAL-TESTE-TMP", "nome": "EMPRESA REAL DE TESTE TMP LTDA", "cnpj": dv_cnpj("901201200001"), "conta": "77777-7"}
    e = am.EMPRESAS["R"]
    am.preparar(servidor.RUNTIME, cenarios=["R"])
    base = CLIENTES_TMP / e["id"]
    (base / am.MARCA).unlink()
    texto = am.regras_bancos(e, "A").replace("TESTE_FICTICIO", "VALIDADA")
    for n in range(1, 7):
        texto = texto.replace("Regra de TESTE da amostra fictícia (não é aprovação do Supervisor)",
                              f'"VALIDADO REGRA {e["id"]} RB-00{n}" em 2026-11-05', 1)
    (base / "REGRAS-BANCOS.md").write_text(texto, encoding="utf-8")

    def proposta(dados):
        for grupo in ("referencias", "exigencias"):
            for x in (dados.get(grupo) or {}).values():
                x.update(situacao="PROPOSTA", origem="Referência proposta para teste (empresa real temporária)", escopo=e["id"])
        if dados.get("data_lancamento"):
            dados["data_lancamento"].update(situacao="PROPOSTA", origem="Política proposta para teste", escopo=e["id"])
        return dados
    (base / "REGRAS-DP.json").write_text(json.dumps(proposta(json.loads(am.regras_dp(e))), ensure_ascii=False), encoding="utf-8")
    (base / "REGRAS-FISCAIS.json").write_text(json.dumps(proposta(am.regras_fiscais(e)), ensure_ascii=False), encoding="utf-8")
    (base / "REGRAS-CONCILIACAO.json").write_text(json.dumps(proposta(am.regras_conciliacao(e)), ensure_ascii=False), encoding="utf-8")
    c0, emp = req("GET", f"/empresas/{e['id']}")
    pend = emp.get("definicoes_necessarias", [])
    cx, rx = req("POST", f"/empresas/{e['id']}/regras-area", {"area": "DP", "chave": "DATA_LANCAMENTO", "frase": "aprovo", "confirmado": True})
    ok = []
    for item in pend:
        c, r = req("POST", f"/empresas/{e['id']}/regras-area", {"area": item["area"], "chave": item["chave"], "frase": item["frase"], "confirmado": True})
        ok.append(c == 200)
    c1, emp2 = req("GET", f"/empresas/{e['id']}")
    versoes = list((base / "VERSOES").glob("REGRAS-*"))
    registrar("R-01 empresa real: definições necessárias listadas (data de DP/Fiscal; regras bancárias com aprovação no formato antigo, "
              "sem versão/responsável, NÃO aplicadas e a reconfirmar); confirmação exige a frase exata; cada confirmação preserva a versão anterior",
              c0 == 200 and len(pend) == 6 + 7 + 1 + 4 + 1 + 3 and {"DP/DATA_LANCAMENTO", "FISCAL/DATA_LANCAMENTO"} <= {f"{p['area']}/{p['chave']}" for p in pend}
              and sorted({p["situacao"] for p in pend if p["area"] == "BANCOS"}) == ["LEGADA_SEM_VERSAO"]
              and cx == 409 and all(ok) and emp2.get("definicoes_necessarias") == [] and len(versoes) == len(pend),
              f"{len(pend)} {cx} {rx} {sum(ok)} {emp2.get('definicoes_necessarias')}")
    sol, s = enviar("R")
    d = detalhe(sol)
    c2, r2 = aprovar(sol)
    sit = detalhe(sol)["situacao_txt"]
    cg, _ = acao_txt(sol, "gerar")
    registrar("R-02 empresa real em piloto SIMULAÇÃO: percurso completo, aprovação registrada e exportação TXT BLOQUEADA (nenhum arquivo, "
              "sem download, sem geração manual)",
              s.get("estado") == "AGUARDANDO_SUPERVISOR" and d["aprovacao_impedimentos"] == [] and c2 == 200
              and r2["liberacao"]["situacao"] == "BLOQUEADA_PRODUCAO" and lib(sol) == "BLOQUEADA_PRODUCAO" and liberados(e["id"]) == []
              and baixar(sol)[0] == 404 and sit["situacao"] == "BLOQUEADA_PRODUCAO" and sit["download"] is False and cg == 409,
              f"{s.get('estado')} {d['aprovacao_impedimentos'][:3]} {c2} {r2} {sit}")


def cenario_b():
    sol, s = enviar("B")
    d = detalhe(sol)
    informar("Cenário B (antes das correções)", d)
    plano = {e["etapa"]: e["situacao"] for e in s.get("plano_etapas", [])}
    triagem = {x["arquivo"].rsplit("/", 1)[-1]: x for x in (s.get("tarefas_areas", {}).get("TRIAGEM") or {}).get("documentos", [])}
    registrar("B-01 Documentos: comprovante de outra empresa e PDF protegido apontados na triagem (sem bloquear o lote)",
              any("17_comprovante_outra_empresa" in n for n in triagem) and any("18_documento_protegido" in n for n in triagem)
              and plano.get("FINANCEIRO") == "CONCLUIDA", list(triagem))
    fin = req("GET", f"/solicitacoes/{sol}/financeiro")[1]
    por_valor = {l["valor"]: l for l in fin["bancos"]["lancamentos"]}

    def falta(v, codigo):
        return codigo in (por_valor.get(v) or {}).get("faltas_codigos", []) and por_valor[v]["status"] == "INCOMPLETO"
    registrar("B-02 Bancos mantém incompletos: sem suporte (250), sem origem (1.500), salários 7.100 × folha 7.000 e regra incompatível no ISS",
              falta("250.00", "SUPORTE") and falta("1500.00", "SUPORTE") and falta("7100.00", "DIVERGENCIA") and falta("500.00", "INCOMPATIVEL")
              and por_valor["45.00"]["status"] == "PROPOSTO", {v: (l["status"], l["faltas_codigos"]) for v, l in por_valor.items()})
    iss = [l for l in d["contabilfiscal"]["lancamentos"] if l.get("evento") == "ISS"]
    registrar("B-03 Fiscal: apuração de ISS duplicada com valores diferentes — nenhuma provisão de ISS proposta",
              iss and all(l["status"] == "INCOMPLETO" for l in iss), [(l["status"], l["pendencias"][:1]) for l in iss])
    prov = [x for x in d["dp"]["documentos"] if x["tipo"] == "PROVISOES"]
    registrar("B-04 DP: demonstrativo de provisões de competência diferente não aproveitado",
              prov and not prov[0]["elegivel_contabilidade"] and any("ompet" in p for p in prov[0]["pendencias"]), prov[:1])
    registrar("B-05 falha real de configuração (referências de DP inválidas): Contabilidade/DP FALHOU, demais áreas preservadas, alcance PARCIAL",
              plano.get("CONTABILIDADE_DP") == "FALHOU" and plano.get("DP") == "CONCLUIDA" and plano.get("CONCILIACAO") == "CONCLUIDA"
              and d["conciliacao"]["resultado"]["alcance"].get("parcial") is True and s.get("estado") == "AGUARDANDO_SUPERVISOR", plano)
    r = d["conciliacao"]["resultado"]
    v = {x["id"]: x for x in r["verificacoes"]}
    salarios = v.get("CONC-D-PAGTO-SALARIOS", {})
    conf_alfa = v.get("CONC-E-CONF-" + "".join(ch for ch in am.ALFA[1] if ch.isdigit()), {})
    registrar("B-06 evidência necessária ausente: confirmação do cliente ALFA (saldo 4.000,00) exigida pela regra e não recebida = PENDENTE "
              "(nunca NÃO APLICÁVEL); nada de DP conferido",
              salarios.get("resultado") == "PENDENTE" and conf_alfa.get("resultado") == "PENDENTE"
              and not any(x["id"].startswith("CONC-D-DP-") and x["resultado"] == "CONFERIDO" for x in r["verificacoes"]),
              f"salarios={salarios.get('resultado')} alfa={conf_alfa.get('resultado')} {conf_alfa.get('justificativa', '')[:120]}")
    ca, _ = aprovar(sol)
    registrar("B-06b com divergências/pendências/falha a aprovação é recusada e os impedimentos são listados",
              ca == 409 and len(d.get("aprovacao_impedimentos", [])) >= 3, f"{ca} {d.get('aprovacao_impedimentos')}")
    c, rec = req("POST", f"/solicitacoes/{sol}/areas/FINANCEIRO/retomar", {"justificativa": "teste fictício", "confirmado": True})
    registrar("B-07 retomada só para etapa que falhou ou desatualizada (Financeiro concluído e vigente: recusada)", c == 409, rec)
    c1, _ = req("POST", "/amostra/corrigir-dp-b", {"confirmado": True})
    pasta = TMP / "runtime" / "execucoes" / sol
    antes = sorted(p.name for p in pasta.iterdir() if p.is_dir())
    c2, r2 = req("POST", f"/solicitacoes/{sol}/areas/CONTABILIDADE_DP/retomar",
                 {"justificativa": "Referências do DP corrigidas na amostra fictícia B.", "confirmado": True})
    s2 = esperar(sol)
    d2 = detalhe(sol)
    plano2 = {e["etapa"]: e["situacao"] for e in s2.get("plano_etapas", [])}
    depois = sorted(p.name for p in pasta.iterdir() if p.is_dir())
    hist = d2["conciliacao"]["historico"]
    registrar("B-08 retomada da Contabilidade/DP após a correção: etapa e Conciliação reexecutadas, tentativas anteriores preservadas, "
              "conciliação anterior desatualizada",
              c1 == 200 and c2 == 202 and plano2.get("CONTABILIDADE_DP") == "CONCLUIDA" and set(antes) <= set(depois)
              and sorted(set(depois) - set(antes)) == ["conciliacao-2", "contabdp-2"] and len(hist) == 2
              and hist[0]["vigente"] is False and hist[1]["vigente"] is True
              and chaves(d2["contabdp"]["lancamentos"], PROPOSTO) == sorted(x for x in ESPERADO_DP if x[1] not in ("2121", "2122")),
              f"{c1} {c2} {r2} {plano2} novos={sorted(set(depois) - set(antes))} vigencia={[h['vigente'] for h in hist]}")
    informar("Cenário B (após retomada da Contabilidade/DP)", d2)
    v2 = {x["id"]: x for x in d2["conciliacao"]["resultado"]["verificacoes"]}
    sal2 = v2.get("CONC-D-PAGTO-SALARIOS", {})
    registrar("B-08b após a retomada: salários 7.100 × líquido 7.000 DIVERGENTE (100,00); provisões sem demonstrativo PENDENTE",
              sal2.get("resultado") == "DIVERGENTE" and Decimal(str(sal2["valores"]["diferenca"])).copy_abs() == Decimal("100.00")
              and any(x["resultado"] == "PENDENTE" and x["id"].startswith("CONC-D-DP-PROVISAO") for x in v2.values()),
              f"{sal2.get('resultado')} {sal2.get('valores')}")
    iss_pag = next(l for l in req("GET", f"/solicitacoes/{sol}/financeiro")[1]["bancos"]["lancamentos"] if l["valor"] == "500.00")
    livre()
    c3, r3 = req("POST", f"/solicitacoes/{sol}/financeiro/decisoes", {"movimento": iss_pag["movimentos"][0], "tipo": "CONTRAPARTIDA",
                 "dados": {"conta": "2131", "natureza_tipo": "LIQUIDACAO_OBRIGACAO"},
                 "justificativa": "Pagamento do ISS de 09/2026: liquidação da obrigação (correção da regra B)."})
    s3 = esperar(sol)
    d3 = detalhe(sol)
    informar("Cenário B (após decisão do ISS)", d3)
    iss3 = next(l for l in req("GET", f"/solicitacoes/{sol}/financeiro")[1]["bancos"]["lancamentos"] if l["valor"] == "500.00")
    registrar("B-09 decisão do caso corrige o pagamento do ISS (D2131/C1101); Financeiro → Bancos → Conciliação reexecutados",
              c3 == 202 and iss3["status"] == "PROPOSTO" and (iss3["debito"] or {}).get("codigo") == "2131"
              and len(d3["conciliacao"]["historico"]) == 3 and s3.get("estado") == "AGUARDANDO_SUPERVISOR", f"{c3} {r3} {iss3['status']}")
    c4, r4 = req("POST", f"/solicitacoes/{sol}/revisao-piloto", {"acao": "encerrar", "justificativa": "Revisão parcial da amostra B (fictícia).",
                                                                  "confirmado": True})
    s4 = registro()[sol]
    registrar("B-10 encerramento da revisão parcial: ENCERRADA, nada aprovado, escopo da Conciliação preservado (parcial, não integral)",
              c4 == 200 and s4["estado"] == "ENCERRADA" and s4["motivos"] and len(s4["conciliacao"]) == 3 and not s4.get("aprovacao")
              and s4.get("escopo_resultado") == "SIMULACAO_CONCILIACAO_PARCIAL"
              and all(not x.get("escrituracao_aprovada") for x in s4.get("revisoes_piloto", [])), f"{r4} {s4.get('escopo_resultado')}")


def foto_operacional():
    """Estado do que NÃO pode ser tocado: CLIENTES/ real, registro real, LIBERADOS/ real."""
    clientes = sorted((str(p.relative_to(RAIZ)), p.stat().st_size, p.stat().st_mtime_ns) for p in (RAIZ / "CLIENTES").rglob("*") if p.is_file())
    reg = RAIZ / "COORDENADOR-GERAL" / "controle" / "solicitacoes.json"
    return clientes, hashlib.sha256(reg.read_bytes()).hexdigest() if reg.is_file() else None, (RAIZ / "LIBERADOS").exists()


def main():
    global srv
    divergentes = [f"{c}/{n}" for c in ("A", "B") for n, b in am.documentos(c).items()
                   if not n.endswith(".pdf") and (am.PASTA_AMOSTRA / f"CENARIO-{c}" / n).read_bytes() != b]
    pdf = am.PASTA_AMOSTRA / "CENARIO-B" / "18_documento_protegido.pdf"
    registrar("P-01 arquivos permanentes da amostra (CENARIO-A/B) são exatamente os do gerador; PDF de B é protegido",
              not divergentes and pdf.is_file() and b"/Encrypt" in pdf.read_bytes(), divergentes)
    antes = foto_operacional()
    for c, v in TESTE.items():
        am.EMPRESAS[c].update(v)
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c, r = req("POST", "/amostra/preparar", {"confirmado": True})
        regras = (CLIENTES_TMP / TESTE["A"]["id"] / "REGRAS-BANCOS.md").read_text(encoding="utf-8")
        dp = json.loads((CLIENTES_TMP / TESTE["A"]["id"] / "REGRAS-DP.json").read_text(encoding="utf-8"))
        registrar("P-02 preparação explícita em CLIENTES temporário: regras identificadas como TESTE_FICTICIO (sem aprovação inventada), "
                  "política de data e exigências da Conciliação de teste",
                  c == 200 and "VALIDADA" not in regras and "TESTE_FICTICIO" in regras and "preparada explicitamente pelo Supervisor" not in regras
                  and all(x["situacao"] == "TESTE_FICTICIO" for x in dp["referencias"].values()) and dp["data_lancamento"]["situacao"] == "TESTE_FICTICIO"
                  and (CLIENTES_TMP / TESTE["A"]["id"] / "REGRAS-CONCILIACAO.json").is_file() and not (RAIZ / "CLIENTES" / TESTE["A"]["id"]).exists(), r)
        sol_a = cenario_a()
        cenario_duplicacao(sol_a)
        empresa_real()
        cenario_b()
    except Exception as exc:          # registra e segue para a limpeza
        import traceback
        registrar("X-00 execução interrompida por erro", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-600:]}")
    finally:
        srv.shutdown()
        srv.server_close()
        for c, v in ORIGINAIS.items():
            am.EMPRESAS[c].update(v)
        am.EMPRESAS.pop("R", None)
        registrar("P-03 ambiente operacional intocado: CLIENTES/ real, registro real e LIBERADOS/ do projeto iguais ao início",
                  foto_operacional() == antes, "")
        shutil.rmtree(TMP, ignore_errors=True)
    largura = max(len(c) for c, _, _ in resultados)
    for c, ok, d in resultados:
        print(f"{'PASS' if ok else 'FAIL'}  {c.ljust(largura)}  {d}")
    for i in INFORMACOES:
        print("INFO  " + i)
    falhas = sum(1 for _, ok, _ in resultados if not ok)
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
