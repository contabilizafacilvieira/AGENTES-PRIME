"""Correções da auditoria (03/11/2026): adiantamento manual, áreas independentes, retomada e âncora do pacote.

Somente dados fictícios. Cria e remove apenas CLIENTES/CLIENTE-TESTE-FLUXO-TMP; registro, runtime e ordem ativa ficam em
pasta temporária (AGENTES_PRIME_ORDEM_ATIVA), sem disputar a ordem ativa real. Não usa a API principal (porta própria).

Uso: .venv/Scripts/python.exe -I TESTES/FINANCEIRO/testar_correcoes_fluxo.py
"""
import base64
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
EMP = "CLIENTE-TESTE-FLUXO-TMP"
TMP = Path(tempfile.mkdtemp(prefix="prime-fluxo-"))
# ambiente ISOLADO: CLIENTES e LIBERADOS temporários (o CLIENTES/ operacional nunca é tocado)
(TMP / "CLIENTES").mkdir()
os.environ["AGENTES_PRIME_CLIENTES"] = str(TMP / "CLIENTES")
os.environ["AGENTES_PRIME_LIBERADOS"] = str(TMP / "LIBERADOS")
BASE = TMP / "CLIENTES" / EMP
os.environ["AGENTES_PRIME_RUNTIME"] = str(TMP / "runtime")
os.environ["AGENTES_PRIME_REGISTRO_SOL"] = str(TMP / "registro.json")
os.environ["AGENTES_PRIME_ORDEM_ATIVA"] = str(TMP / "ordem-ativa.json")
os.environ["AGENTES_PRIME_CLAUDE"] = str(TMP / "claude-inexistente.exe")
os.environ["LOCALAPPDATA"] = str(TMP / "localappdata")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado as _ai  # noqa: E402

PY = sys.executable
BAN = RAIZ / "AGENTES" / "CONTABILIDADE" / "BANCOS" / "ferramentas" / "lancamentos_bancarios.py"
CNPJ = "11222333000181"
NOTA = ("NFS-E\nCNPJ DO PRESTADOR: 11.222.333/0001-81\nCNPJ DO TOMADOR: 04.252.011/0001-10\nNUMERO DA NOTA: {n}\n"
        "COMPETENCIA: 10/2026\nVALOR DOS SERVICOS: R$ 1.234,56\n")
OFX = ("<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><BANKID>033<BRANCHID>1234<ACCTID>11111-1</BANKACCTFROM>"
       "<BANKTRANLIST><DTSTART>20261001<DTEND>20261031"
       "<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261005<TRNAMT>-320.00<FITID>FX-{n}-1<MEMO>PIX ENVIADO FORNECEDOR FICTICIO</STMTTRN>"
       "<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20261007<TRNAMT>3000.00<FITID>FX-{n}-2<MEMO>PIX RECEBIDO CLIENTE FICTICIO</STMTTRN>"
       "</BANKTRANLIST><LEDGERBAL><BALAMT>3680.00<DTASOF>20261031</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>")
resultados = []
srv = None


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:300]))


def caso(nome):
    def envolver(fn):
        def rodar(*a):
            try:
                return fn(*a)
            except Exception as exc:   # o caso falha com o motivo; os demais continuam
                registrar(nome, False, f"{type(exc).__name__}: {exc}")
        return rodar
    return envolver


def req(metodo, rota, dados=None, cab=None, aceitar_erro=False):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=120)
    h = {"X-Prime-Sessao": srv.token, "Content-Type": "application/json"}
    h.update(cab or {})
    corpo = dados if isinstance(dados, bytes) else json.dumps(dados).encode() if dados is not None else None
    c.request(metodo, "/api" + rota, corpo, h)
    r = c.getresponse()
    bruto = r.read()
    c.close()
    try:
        j = json.loads(bruto)
    except ValueError:
        j = bruto
    if r.status >= 400 and not aceitar_erro:
        raise AssertionError(f"{metodo} {rota} → {r.status}: {j}")
    return (r.status, j) if aceitar_erro else j


def registro():
    return _ai.registro_isolado()["solicitacoes"]


def esperar(sol, limite=150):
    """Espera a SOL ficar livre: sem execução no servidor e fora dos estados *_EM_ANDAMENTO (ou devolve o estado travado)."""
    fim = time.time() + limite
    s = {}
    while time.time() < fim:
        s = registro().get(sol, {})
        livre = not servidor.EM_EXECUCAO["sol"] and not servidor.EM_FINANCEIRO["sol"]
        if livre and not str(s.get("estado", "")).endswith("_EM_ANDAMENTO"):
            return s
        time.sleep(0.25)
    return s


def livre(limite=150):
    fim = time.time() + limite
    while time.time() < fim:
        if not servidor.EM_EXECUCAO["sol"] and not servidor.EM_FINANCEIRO["sol"]:
            return True
        time.sleep(0.25)
    return False


def decidir(sol, corpo):
    """Envia uma decisão e espera a nova tentativa terminar (ou a recusa)."""
    livre()
    r = req("POST", f"/solicitacoes/{sol}/financeiro/decisoes", corpo, aceitar_erro=True)
    esperar(sol)
    return r


def iniciar(n, misto=True):
    livre()
    lote = req("POST", "/lotes", {"empresa": EMP, "competencia": "2026-10", "fluxo": "DOCUMENTOS",
                                  "instrucao": "Distribua por área (teste fictício)."})["lote"]
    fontes = [("extrato.ofx", OFX.format(n=n).encode())]
    if misto:
        fontes.append(("nota.txt", NOTA.format(n=n).encode()))
    for nome, d in fontes:
        req("PUT", f"/lotes/{lote}/arquivos", d, {"X-Nome-Arquivo": nome, "X-Sha256": hashlib.sha256(d).hexdigest(),
                                                 "Content-Type": "application/octet-stream"})
    sol = req("POST", f"/lotes/{lote}/iniciar", {"conferencia_humana": True})["sol"]
    return sol, esperar(sol)


def ferramenta_que_falha(nome):
    p = TMP / f"{nome}_falha.py"
    p.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    return p


def com_ferramenta(atributo, caminho, fn):
    original = getattr(servidor, atributo)
    setattr(servidor, atributo, caminho)
    try:
        return fn()
    finally:
        setattr(servidor, atributo, original)


def movimento(sol, direcao):
    e = req("GET", f"/solicitacoes/{sol}/financeiro")
    return next(m for m in e["financeiro"]["movimentos"] if m["direcao"] == direcao)


def lancamento(sol, mov_id):
    e = req("GET", f"/solicitacoes/{sol}/financeiro")
    return next(l for l in e["bancos"]["lancamentos"] if mov_id in l["movimentos"])


def preparar_empresa():
    req("POST", "/empresas", {"id": EMP, "nome": "CLIENTE FICTICIO FLUXO", "cnpj": CNPJ, "regime": "TESTE"})
    plano = ("codigo;classificacao;descricao;grupo;tipo\n5;1.1.1;BANCO FICTICIO;ATIVO;A\n11;1.1.2;CLIENTES;ATIVO;A\n"
             "1150;1.1.5;ADIANTAMENTO A FORNECEDORES;ATIVO;A\n2101;2.1.1;FORNECEDORES;PASSIVO;A\n"
             "2102;2.1.3;IMPOSTOS A RECOLHER;PASSIVO;A\n2150;2.1.5;ADIANTAMENTO DE CLIENTES;PASSIVO;A\n"
             "2199;2.1;PASSIVO CIRCULANTE;PASSIVO;S\n60;3.1;RECEITA DE SERVICOS;RECEITA;A\n4103;4.1;DESPESAS GERAIS;DESPESA;A\n")
    p = req("POST", f"/empresas/{EMP}/previa", {"nome": "plano.csv", "conteudo": base64.b64encode(plano.encode()).decode()})
    req("POST", f"/empresas/{EMP}/plano", {"token": p["token"], "salvar": True, "confirmado": True})
    req("POST", f"/empresas/{EMP}/bancos", {"contas": [{"banco": "033", "agencia": "1234", "conta": "11111-1", "titular": CNPJ, "contabil": "5"}]})
    req("POST", f"/empresas/{EMP}/piloto", {"frase": "CONFIRMO PILOTO " + EMP})
    cad = req("GET", f"/empresas/{EMP}")
    (BASE / "REGRAS-FISCAIS.json").write_text(json.dumps({
        "contrato": "REFERENCIAS_FISCAIS_V1", "empresa": EMP, "cnpj": cad["cnpj"], "competencia_desde": "2026-10",
        "referencias": {"RECEITA_SERVICOS": {"debito": "11", "credito": "60", "fonte": "Método fictício para teste"}}}), encoding="utf-8")


# ------------------------------------------------------------------ adiantamento manual

@caso("B-01 adiantamento sem conta indicada pelo Supervisor: decisão recusada (grupo compatível não basta)")
def b01(sol):
    deb, cred = movimento(sol, "DEBITO"), movimento(sol, "CREDITO")
    c1, r1 = decidir(sol, {"movimento": deb["id"], "tipo": "CONTRAPARTIDA",
                 "dados": {"conta": "1150", "natureza_tipo": "ADIANTAMENTO_FORNECEDOR"}, "justificativa": "teste sem indicação"})
    c2, r2 = decidir(sol, {"movimento": cred["id"], "tipo": "CONTRAPARTIDA",
                 "dados": {"conta": "2102", "natureza_tipo": "ADIANTAMENTO_CLIENTE"}, "justificativa": "teste 2102"})
    esperar(sol)
    registrar("B-01 adiantamento sem conta indicada pelo Supervisor: decisão recusada (grupo compatível não basta)",
              c1 == 409 and c2 == 409 and not registro()[sol].get("decisoes_movimentos"), f"{c1} {r1} | {c2} {r2}")


@caso("B-02 indicação expressa da conta de adiantamento pela tela: só conta analítica do grupo correto, fora dos bancos")
def b02():
    ruins = [("ADIANTAMENTO_FORNECEDOR", "5"), ("ADIANTAMENTO_FORNECEDOR", "2101"), ("ADIANTAMENTO_CLIENTE", "2199"),
             ("ADIANTAMENTO_CLIENTE", "9999")]
    codigos = [req("POST", f"/empresas/{EMP}/contas-adiantamento", {"natureza": n, "conta": c, "confirmado": True,
                                                                    "justificativa": "teste"}, aceitar_erro=True)[0] for n, c in ruins]
    sem_conf, _ = req("POST", f"/empresas/{EMP}/contas-adiantamento", {"natureza": "ADIANTAMENTO_FORNECEDOR", "conta": "1150",
                                                                         "justificativa": "teste"}, aceitar_erro=True)
    ok1 = req("POST", f"/empresas/{EMP}/contas-adiantamento", {"natureza": "ADIANTAMENTO_FORNECEDOR", "conta": "1150", "confirmado": True,
                                                              "justificativa": "Conta indicada pelo Supervisor (fictício)."})
    ok2 = req("POST", f"/empresas/{EMP}/contas-adiantamento", {"natureza": "ADIANTAMENTO_CLIENTE", "conta": "2150", "confirmado": True,
                                                              "justificativa": "Conta indicada pelo Supervisor (fictício)."})
    cad = (BASE / "CADASTRO.md").read_text(encoding="utf-8")
    registrar("B-02 indicação expressa da conta de adiantamento pela tela: só conta analítica do grupo correto, fora dos bancos",
              all(c == 400 for c in codigos) and sem_conf == 400
              and ok2.get("contas_adiantamento", {}).get("ADIANTAMENTO_FORNECEDOR", {}).get("conta") == "1150"
              and ok2["contas_adiantamento"]["ADIANTAMENTO_CLIENTE"]["conta"] == "2150"
              and "| ADIANTAMENTO_FORNECEDOR | 1150 |" in cad and "| ADIANTAMENTO_CLIENTE | 2150 |" in cad
              and ok1.get("piloto") is True, f"{codigos} {sem_conf} {ok2.get('contas_adiantamento')}")


@caso("B-03 adiantamento na conta indicada: lançamento INCOMPLETO com a falta de suporte visível (não vira acompanhamento)")
def b03(sol):
    deb, cred = movimento(sol, "DEBITO"), movimento(sol, "CREDITO")
    c0, _ = decidir(sol, {"movimento": cred["id"], "tipo": "CONTRAPARTIDA",
                "dados": {"conta": "2102", "natureza_tipo": "ADIANTAMENTO_CLIENTE"}, "justificativa": "outra conta do grupo"})
    decidir(sol, {"movimento": deb["id"], "tipo": "CONTRAPARTIDA",
        "dados": {"conta": "1150", "natureza_tipo": "ADIANTAMENTO_FORNECEDOR"}, "justificativa": "Adiantamento indicado (fictício)."})
    esperar(sol)
    decidir(sol, {"movimento": cred["id"], "tipo": "CONTRAPARTIDA",
        "dados": {"conta": "2150", "natureza_tipo": "ADIANTAMENTO_CLIENTE"}, "justificativa": "Adiantamento indicado (fictício)."})
    esperar(sol)
    ld, lc = lancamento(sol, deb["id"]), lancamento(sol, cred["id"])
    registrar("B-03 adiantamento na conta indicada: lançamento INCOMPLETO com a falta de suporte visível (não vira acompanhamento)",
              c0 == 409 and ld["status"] == lc["status"] == "INCOMPLETO" and "SUPORTE" in ld["faltas_codigos"] and "SUPORTE" in lc["faltas_codigos"]
              and (ld["debito"] or {}).get("codigo") == "1150" and (lc["credito"] or {}).get("codigo") == "2150"
              and any("sem documento" in p.lower() or "comprove a origem" in p for p in ld["pendencias"] + lc["pendencias"]),
              f"{c0} {ld['status']} {ld['faltas_codigos']} {lc['status']} {lc['faltas_codigos']}")


def financeiro_sintetico(sol, mov):
    return {"agente": "FINANCEIRO", "sol": sol, "empresa": EMP, "competencia": "2026-10", "movimentos": [mov], "documentos": [], "relacao": []}


def mov_base(**extra):
    m = {"id": "MOV-0000000000A1", "conta": "033-1234-111111", "data": "2026-10-05", "valor": "320.00", "direcao": "DEBITO",
         "descricao": "PIX ENVIADO", "identificadores": {}, "tipo_banco": "DEBIT", "situacao": "SEM_SUPORTE", "documentos": [],
         "relacao": [], "divergencias": [], "sugestoes": []}
    m.update(extra)
    return m


def rodar_bancos(nome, fin, decisoes, areas=None):
    pasta = TMP / "motor" / nome
    pasta.mkdir(parents=True)
    (pasta / "fin.json").write_text(json.dumps(fin), encoding="utf-8")
    (pasta / "dec.json").write_text(json.dumps(decisoes), encoding="utf-8")
    extra = []
    if areas is not None:
        (pasta / "areas.json").write_text(json.dumps(areas), encoding="utf-8")
        extra = ["--areas", str(pasta / "areas.json")]
    p = subprocess.run([PY, "-I", str(BAN), "--empresa", EMP, "--sol", fin["sol"], "--competencia", "2026-10", "--financeiro",
                        str(pasta / "fin.json"), "--saida", str(pasta / "saida"), "--decisoes", str(pasta / "dec.json"), *extra],
                       cwd=RAIZ, capture_output=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise AssertionError(f"Bancos rc={p.returncode}: {(p.stdout + p.stderr)[-200:]}")
    return json.loads((pasta / "saida" / "resultado.json").read_text(encoding="utf-8"))["lancamentos"][0]


@caso("B-04 motor: decisão de adiantamento em conta não indicada no cadastro não é proposta (mesmo que chegue ao motor)")
def b04():
    dec = {"MOV-0000000000A1": [{"tipo": "CONTRAPARTIDA", "conta": "2102", "natureza_tipo": "ADIANTAMENTO_FORNECEDOR",
                                 "justificativa": "x", "em": "2026-11-03"}]}
    l1 = rodar_bancos("b04a", financeiro_sintetico("SOL-2026-990001", mov_base()), dec)
    dec2 = {"MOV-0000000000A1": [{"tipo": "CONTRAPARTIDA", "conta": "1150", "natureza_tipo": "ADIANTAMENTO_FORNECEDOR",
                                  "justificativa": "x", "em": "2026-11-03"}]}
    l2 = rodar_bancos("b04b", financeiro_sintetico("SOL-2026-990001", mov_base()), dec2)
    registrar("B-04 motor: decisão de adiantamento em conta não indicada no cadastro não é proposta (mesmo que chegue ao motor)",
              l1["status"] == "INCOMPLETO" and l1["debito"] is None and any("indicada" in p for p in l1["pendencias"])
              and l2["status"] == "INCOMPLETO" and (l2["debito"] or {}).get("codigo") == "1150" and "SUPORTE" in l2["faltas_codigos"]
              and not l2.get("acompanhamentos"), f"{l1['status']} {l1['pendencias'][:2]} | {l2['status']} {l2['faltas_codigos']}")


@caso("B-05 Contabilidade distingue proposta que depende do Fiscal (documento da nota com análise fiscal falha/pendente)")
def b05():
    doc = {"arquivo": "nota.txt", "tipo": "NOTA_FISCAL", "papel": "NATUREZA", "numero": "77"}
    m = mov_base(situacao="COM_SUPORTE", documentos=[doc])
    dec = {"MOV-0000000000A1": [{"tipo": "CONTRAPARTIDA", "conta": "4103", "natureza_tipo": "DESPESA", "justificativa": "x", "em": "2026-11-03"}]}
    falhou = rodar_bancos("b05a", financeiro_sintetico("SOL-2026-990002", m), dec,
                          {"FISCAL": {"estado": "FALHOU", "documentos": ["RECEBIDOS/X/nota.txt"]}})
    entregue = rodar_bancos("b05b", financeiro_sintetico("SOL-2026-990002", m), dec,
                            {"FISCAL": {"estado": "ENTREGUE", "documentos": ["RECEBIDOS/X/nota.txt"]}})
    registrar("B-05 Contabilidade distingue proposta que depende do Fiscal (documento da nota com análise fiscal falha/pendente)",
              falhou["status"] == "INCOMPLETO" and "DEPENDE_AREA" in falhou["faltas_codigos"]
              and any("Fiscal" in p for p in falhou["pendencias"]) and "DEPENDE_AREA" not in entregue["faltas_codigos"],
              f"{falhou['status']} {falhou['faltas_codigos']} | {entregue['faltas_codigos']}")


# ------------------------------------------------------------------ áreas independentes e retomada

@caso("I-01 falha do Fiscal não impede o Financeiro; Contabilidade/Fiscal fica bloqueada com dependência explícita")
def i01():
    sol, s = com_ferramenta("FERRAMENTA_FISCAL", ferramenta_que_falha("fiscal"), lambda: iniciar(201))
    t = s.get("tarefas_areas", {})
    registrar("I-01 falha do Fiscal não impede o Financeiro; Contabilidade/Fiscal fica bloqueada com dependência explícita",
              s.get("estado") == "AGUARDANDO_SUPERVISOR" and t.get("FISCAL", {}).get("estado") == "FALHOU"
              and len(s.get("financeiro", [])) == 1 and len(s.get("bancos", [])) == 1 and not s.get("contabilfiscal")
              and t.get("CONTABILIDADE_FISCAL", {}).get("estado") == "BLOQUEADO_POR_DEPENDENCIA"
              and any("FISCAL" in m for m in s.get("motivos", [])),
              f"{s.get('estado')} fiscal={t.get('FISCAL', {}).get('estado')} fin={len(s.get('financeiro', []))} "
              f"cf={t.get('CONTABILIDADE_FISCAL', {}).get('estado')}")
    return sol


@caso("I-02 falha do Financeiro não descarta a análise fiscal: Contabilidade/Fiscal é preparada")
def i02():
    sol, s = com_ferramenta("FERRAMENTA_FINANCEIRO", ferramenta_que_falha("financeiro"), lambda: iniciar(202))
    t = s.get("tarefas_areas", {})
    registrar("I-02 falha do Financeiro não descarta a análise fiscal: Contabilidade/Fiscal é preparada",
              s.get("estado") == "AGUARDANDO_SUPERVISOR" and len(s.get("fiscal", [])) == 1 and len(s.get("contabilfiscal", [])) == 1
              and t.get("FINANCEIRO", {}).get("estado") == "FALHOU" and not s.get("bancos")
              and any("FALHA_FINANCEIRO" in m for m in s.get("motivos", [])),
              f"{s.get('estado')} fin={t.get('FINANCEIRO', {}).get('estado')} cf={len(s.get('contabilfiscal', []))}")


@caso("I-03 falha de Bancos + retomada por decisão: Contabilidade/Fiscal roda uma vez, nada fica em andamento sem executor")
def i03():
    sol, s = com_ferramenta("FERRAMENTA_BANCOS", ferramenta_que_falha("bancos"), lambda: iniciar(203))
    antes_cf = len(s.get("contabilfiscal", []))
    t = s.get("tarefas_areas", {})
    deb = movimento(sol, "DEBITO")
    decidir(sol, {"movimento": deb["id"], "tipo": "CONTRAPARTIDA",
        "dados": {"conta": "4103", "natureza_tipo": "DESPESA"}, "justificativa": "Despesa geral (fictício)."})
    s2 = esperar(sol, 120)
    pasta = TMP / "runtime" / "execucoes" / sol
    registrar("I-03 falha de Bancos + retomada por decisão: Contabilidade/Fiscal roda uma vez, nada fica em andamento sem executor",
              antes_cf == 1 and t.get("CONTABILIDADE", {}).get("estado") == "FALHOU"
              and s2.get("estado") == "AGUARDANDO_SUPERVISOR" and len(s2.get("contabilfiscal", [])) == 1
              and len(s2.get("bancos", [])) == 1 and sorted(p.name for p in pasta.glob("bancos-*")) == ["bancos-1", "bancos-2"]
              and sorted(p.name for p in pasta.glob("contabilfiscal-*")) == ["contabilfiscal-1"]
              and sorted(p.name for p in pasta.glob("fiscal-*")) == ["fiscal-1"],
              f"cf antes={antes_cf} contab={t.get('CONTABILIDADE', {}).get('estado')} depois={s2.get('estado')} "
              f"cf={len(s2.get('contabilfiscal', []))} pastas={sorted(p.name for p in pasta.iterdir() if p.is_dir())}")


# ------------------------------------------------------------------ âncora de integridade do pacote

@caso("A-01 pacote adulterado com hash recalculado no manifesto: recusado pela âncora registrada pelo Coordenador")
def a01(sol):
    pasta = TMP / "runtime" / "execucoes" / sol
    extr = pasta / "extracao-local.json"
    man = pasta / "documentos-local.json"
    texto = extr.read_text(encoding="utf-8").replace("-320.00", "-999.00")
    extr.write_text(texto, encoding="utf-8")
    m = json.loads(man.read_text(encoding="utf-8"))
    m["extracao_sha256"] = hashlib.sha256(extr.read_bytes()).hexdigest()
    man.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    n_fin = len(list(pasta.glob("financeiro-*")))
    deb = movimento(sol, "DEBITO")
    decidir(sol, {"movimento": deb["id"], "tipo": "CONTRAPARTIDA",
        "dados": {"conta": "4103", "natureza_tipo": "DESPESA"}, "justificativa": "Teste de adulteração (fictício)."})
    s = esperar(sol)
    e = req("GET", f"/solicitacoes/{sol}/financeiro")
    valores = {x["valor"] for x in e["financeiro"]["movimentos"]}
    registrar("A-01 pacote adulterado com hash recalculado no manifesto: recusado pela âncora registrada pelo Coordenador",
              any("integridade" in x.lower() or "âncora" in x.lower() for x in s.get("motivos", [])[:1])
              and "999.00" not in valores and len(list(pasta.glob("financeiro-*"))) == n_fin + 1,
              f"{s.get('motivos', [])[:1]} {valores}")


@caso("A-02 SOL antiga sem âncora registrada: pacote não é tratado como verificado (pendência explícita)")
def a02(sol):
    caminho = Path(os.environ["AGENTES_PRIME_REGISTRO_SOL"])
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["solicitacoes"][sol].pop("ancora_documentos", None)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    deb = movimento(sol, "DEBITO")
    decidir(sol, {"movimento": deb["id"], "tipo": "CONTRAPARTIDA",
        "dados": {"conta": "4103", "natureza_tipo": "DESPESA"}, "justificativa": "Teste sem âncora (fictício)."})
    s = esperar(sol)
    registrar("A-02 SOL antiga sem âncora registrada: pacote não é tratado como verificado (pendência explícita)",
              any("âncora" in x.lower() for x in s.get("motivos", [])[:1]) and s.get("estado") == "AGUARDANDO_SUPERVISOR",
              s.get("motivos", [])[:1])


@caso("R-01 reinício do servidor com etapa em andamento: falha registrada, sem repetição automática, nada fica sem executor")
def r01(sol):
    pasta = TMP / "runtime" / "execucoes" / sol
    antes = sorted(p.name for p in pasta.iterdir() if p.is_dir())
    caminho = Path(os.environ["AGENTES_PRIME_REGISTRO_SOL"])
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    # SOL interrompida no meio de uma nova tentativa: Financeiro em andamento, Bancos e Conciliação ainda pendentes no plano
    for e in dados["solicitacoes"][sol]["plano_etapas"]:
        if e["etapa"] in ("FINANCEIRO", "BANCOS", "CONCILIACAO"):
            e["situacao"] = "PENDENTE"
    dados["solicitacoes"][sol]["estado"] = "FINANCEIRO_EM_ANDAMENTO"
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    tratadas = servidor.reconciliar_interrompidas()
    s = registro()[sol]
    situacoes = {e["etapa"]: e["situacao"] for e in s["plano_etapas"]}
    registrar("R-01 reinício do servidor com etapa em andamento: falha registrada, sem repetição automática, nada fica sem executor",
              tratadas == [(sol, "FINANCEIRO"), (sol, "CONCILIACAO")] and s["estado"] == "AGUARDANDO_SUPERVISOR"
              and situacoes == {"FINANCEIRO": "FALHOU", "BANCOS": "BLOQUEADA_POR_DEPENDENCIA", "CONCILIACAO": "FALHOU"}
              and any("interrompida" in m for m in s["motivos"]) and sorted(p.name for p in pasta.iterdir() if p.is_dir()) == antes
              and not servidor.reconciliar_interrompidas(), f"{tratadas} {s['estado']}")


def remover_empresa_temporaria():
    """Remove só a empresa criada por este teste (originais recebidos ficam somente leitura)."""
    if BASE.exists() and BASE.resolve().parent == (TMP / "CLIENTES").resolve() and BASE.name == EMP and not BASE.is_symlink():
        def permissao(fn, caminho, _exc):
            os.chmod(caminho, 0o700)
            fn(caminho)
        shutil.rmtree(BASE, onexc=permissao)


def main():
    global srv
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        preparar_empresa()
        sol_b, s_b = iniciar(101, misto=False)
        registrar("P-00 preparação: lote financeiro fictício conferido e proposto", s_b.get("estado") == "AGUARDANDO_SUPERVISOR"
                  and len(s_b.get("bancos", [])) == 1, s_b.get("estado"))
        b01(sol_b)
        b02()
        b03(sol_b)
        b04()
        b05()
        i01()
        i02()
        i03()
        sol_a, _ = iniciar(301, misto=False)
        a01(sol_a)
        sol_c, _ = iniciar(302, misto=False)
        a02(sol_c)
        livre()
        r01(sol_b)
    finally:
        srv.shutdown()
        srv.server_close()
        remover_empresa_temporaria()
        shutil.rmtree(TMP, ignore_errors=True)
    largura = max(len(c) for c, _, _ in resultados)
    for c, ok, d in resultados:
        print(f"{'PASS' if ok else 'FAIL'}  {c.ljust(largura)}  {d}")
    falhas = sum(1 for _, ok, _ in resultados if not ok)
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    print(f"empresa temporária residual: {'sim' if BASE.exists() else 'não'}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
