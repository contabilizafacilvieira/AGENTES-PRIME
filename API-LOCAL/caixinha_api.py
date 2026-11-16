"""CONCILIAÇÃO CAIXINHA na API local — executores das etapas, painel, evidências, simulação do TXT e execução em lote.

Reaproveita a infraestrutura do servidor (servidor.py): lotes/upload, Coordenador (abrir → encerrar-local → plano de etapas),
tentativas (nova_execucao/reprocessamento), fotografia das fontes, registro sob trava, sha256 e vigência. Este módulo só acrescenta
o que é específico da rotina; o servidor vincula-se a ele com `vincular(sys.modules[__name__])` (sem segunda cópia do servidor).
Nada aqui aprova, escritura ou importa no Domínio. Empresa real: TXT bloqueado (exportacao_dominio.liberacao_permitida).
"""
import datetime as dt
import hashlib
import json
import subprocess
import threading
from decimal import Decimal
from pathlib import Path

S = None                                    # módulo do servidor (vinculado na importação do servidor)
RAIZ = Path(__file__).resolve().parents[1]
FERRAMENTAS = {
    "CAIXINHA_CONTABIL": (RAIZ / "AGENTES/CONTABILIDADE/CAIXINHA/ferramentas/leitores_contabeis.py", "caixinha_contabil"),
    "CAIXINHA_FISCAL": (RAIZ / "AGENTES/FISCAL/ferramentas/caixinha_fiscal.py", "caixinha_fiscal"),
    "CAIXINHA_DP": (RAIZ / "AGENTES/DP/ferramentas/caixinha_dp.py", "caixinha_dp"),
}
FERRAMENTA_CONCILIACAO = RAIZ / "AGENTES/CONCILIACAO/CAIXINHA/ferramentas/conciliacao_caixinha.py"
FILA = {"lotes": [], "atual": None, "inicio": None, "fim": None, "resultados": []}
TRAVA_FILA = threading.Lock()


def vincular(servidor_modulo) -> None:
    global S
    S = servidor_modulo


# ---------------------------------------------------------------- execução das etapas (plano do Coordenador)
def executar_leitura(sol: str, etapa: str) -> None:
    """Contábil/leitores, Fiscal ou DP da Caixinha sobre o pacote de Documentos com âncora (mesmo protocolo das áreas)."""
    s = S.coordenador.ler_registro()["solicitacoes"][sol]
    pasta = S.RUNTIME / "execucoes" / sol
    ferramenta, prefixo = FERRAMENTAS[etapa]
    saida = S.nova_execucao(sol, prefixo)
    S.gravar_json(saida / "origem.json", {"sol": sol, "etapa": etapa, "inicio": S.agora()})
    S.fotografar_fontes(saida, s["empresa"], etapa)
    try:
        S.EM_FINANCEIRO.update(sol=sol, etapa=etapa)
        if (motivo := S.problema_ancora(s, pasta)):
            raise ValueError(motivo)
        man, ext = S.pacote_vigente(pasta, s)
        p = subprocess.run([S.PY, "-I", str(ferramenta), "--empresa", s["empresa"], "--competencia", s["competencia"], "--sol", sol,
                            "--pasta", s["pasta"], "--documentos-local", str(man), "--extracao-local", str(ext), "--saida", str(saida)],
                           cwd=RAIZ, capture_output=True, encoding="utf-8", errors="replace", timeout=600)
        if p.returncode or not (saida / "resultado.json").exists():
            raise ValueError((p.stderr or p.stdout or "Resultado ausente")[-250:])
        codigo, r = S.coordenador_cli("registrar-caixinha", "--sol", sol, "--etapa", etapa, "--resultado", str(saida / "resultado.json"))
        if codigo:
            raise ValueError(r.get("motivo", "Registro recusado"))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        S.gravar_json(saida / "falha.json", {"em": S.agora(), "motivo": str(exc)[-300:]})
        S.coordenador_cli("registrar-falha-etapa", "--sol", sol, "--etapa", etapa, "--motivo", f"{saida.name}: {str(exc)[-300:]}")
    finally:
        S.EM_FINANCEIRO.update(sol=None, etapa=None)


def fatos_outras_sols(sol: str) -> list:
    """Baixas Caixinha APROVADAS ou EXPORTADAS em OUTRAS solicitações da MESMA empresa (qualquer competência), inclusive registros
    mínimos de SOL excluída: a Conciliação não prepara a mesma baixa de novo enquanto o razão não a mostrar."""
    todos = S.coordenador.ler_registro()
    s = todos["solicitacoes"][sol]
    saida = []
    for outra, o in todos["solicitacoes"].items():
        if outra == sol or o.get("empresa") != s["empresa"]:
            continue
        for ap, situacao in [(o.get("aprovacao"), "APROVADA")] + [(a, "EXPORTADA") for a in o.get("aprovacoes_anteriores", [])]:
            fatos = (ap or {}).get("fatos_aprovados" if situacao == "APROVADA" else "fatos_exportados") or {}
            for ident, f in fatos.items():
                if ident.startswith("CXN-"):
                    saida.append({"identidade": ident, "sol": outra, "competencia": o.get("competencia"), "situacao": situacao,
                                  "valor": f.get("valor"), "debito": f.get("debito"), "credito": f.get("credito")})
    for outra, m in (todos.get("registros_minimos") or {}).items():
        if m.get("empresa") == s["empresa"]:
            for ident, f in (m.get("fatos_exportados") or {}).items():
                if ident.startswith("CXN-"):
                    saida.append({"identidade": ident, "sol": outra, "competencia": m.get("competencia"), "situacao": "EXPORTADA",
                                  "valor": (f or {}).get("valor") if isinstance(f, dict) else None})
    return saida


def executar_conciliacao(sol: str) -> None:
    """Conciliação Caixinha sobre os resultados REGISTRADOS (caminho + sha256 do registro) e as regras da empresa."""
    s = S.coordenador.ler_registro()["solicitacoes"][sol]
    pasta = S.RUNTIME / "execucoes" / sol
    saida = S.nova_execucao(sol, "caixinha_conciliacao")
    S.gravar_json(saida / "origem.json", {"sol": sol, "etapa": "CAIXINHA_CONCILIACAO", "inicio": S.agora()})
    S.fotografar_fontes(saida, s["empresa"], "CAIXINHA_CONCILIACAO")
    try:
        S.EM_FINANCEIRO.update(sol=sol, etapa="CAIXINHA_CONCILIACAO")
        if (motivo := S.problema_ancora(s, pasta)):
            raise ValueError(motivo)
        situacoes = {e["etapa"]: e["situacao"] for e in S.coordenador.plano_de(s)}
        etapas = {}
        for etapa, (_, prefixo) in FERRAMENTAS.items():
            caminho = S.ultimo_concluido_caminho(sol, prefixo)
            etapas[etapa] = {"situacao": situacoes.get(etapa, "NAO_ACIONADA"), "resultado": str(caminho) if caminho and s.get(prefixo) else None,
                             "sha256_registrado": (s.get(prefixo) or [{}])[-1].get("resultado_sha256")}
        ancora = s.get("ancora_documentos") or {}
        entradas = {"contrato": "ENTRADAS_CONCILIACAO_CAIXINHA_V1", "empresa": s["empresa"], "sol": sol, "competencia": s["competencia"],
                    "etapas": etapas, "pacote": {"manifesto_sha256": ancora.get("manifesto_sha256"), "extracao_sha256": ancora.get("extracao_sha256")},
                    "fatos_outras_sols": fatos_outras_sols(sol)}
        S.gravar_json(saida / "entradas.json", entradas)
        p = subprocess.run([S.PY, "-I", str(FERRAMENTA_CONCILIACAO), "--empresa", s["empresa"], "--sol", sol, "--competencia", s["competencia"],
                            "--entradas", str(saida / "entradas.json"), "--saida", str(saida)],
                           cwd=RAIZ, capture_output=True, encoding="utf-8", errors="replace", timeout=600)
        if p.returncode or not (saida / "resultado.json").exists():
            raise ValueError((p.stderr or p.stdout or "Resultado ausente")[-250:])
        codigo, r = S.coordenador_cli("registrar-caixinha", "--sol", sol, "--etapa", "CAIXINHA_CONCILIACAO", "--resultado", str(saida / "resultado.json"))
        if codigo:
            raise ValueError(r.get("motivo", "Registro recusado"))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        S.gravar_json(saida / "falha.json", {"em": S.agora(), "motivo": str(exc)[-300:]})
        S.coordenador_cli("registrar-falha-etapa", "--sol", sol, "--etapa", "CAIXINHA_CONCILIACAO", "--motivo", f"{saida.name}: {str(exc)[-300:]}")
    finally:
        S.EM_FINANCEIRO.update(sol=None, etapa=None)


EXECUTORES = {"CAIXINHA_CONTABIL_EM_ANDAMENTO": lambda sol: executar_leitura(sol, "CAIXINHA_CONTABIL"),
              "CAIXINHA_FISCAL_EM_ANDAMENTO": lambda sol: executar_leitura(sol, "CAIXINHA_FISCAL"),
              "CAIXINHA_DP_EM_ANDAMENTO": lambda sol: executar_leitura(sol, "CAIXINHA_DP"),
              "CAIXINHA_CONCILIACAO_EM_ANDAMENTO": executar_conciliacao}


# ---------------------------------------------------------------- leitura dos resultados REGISTRADOS (sha256 conferido)
def resultado_registrado(sol: str, s: dict, prefixo: str):
    """Último resultado da etapa SOMENTE se o sha256 confere com o registro do Coordenador (senão None: nada é exibido como válido)."""
    caminho = S.ultimo_concluido_caminho(sol, prefixo)
    registrado = (s.get(prefixo) or [{}])[-1].get("resultado_sha256")
    if not caminho or not registrado or hashlib.sha256(caminho.read_bytes()).hexdigest() != registrado:
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def documentos_da_sol(sol: str, s: dict) -> list:
    docs = []
    for etapa, (_, prefixo) in FERRAMENTAS.items():
        r = resultado_registrado(sol, s, prefixo) or {}
        for d in r.get("documentos") or []:
            docs.append({k: d.get(k) for k in ("id", "arquivo", "sha256", "tipo", "cnpj", "competencia", "periodo", "emissao", "reconhecimento",
                                                "leitor", "situacao_leitor", "dados", "pendencias", "proveniencia")} | {"etapa": etapa,
                                                                                                                       "nome": str(d.get("arquivo")).rsplit("/", 1)[-1]})
    return docs


def painel(sol: str) -> dict:
    todos = S.coordenador.ler_registro()
    s = todos["solicitacoes"].get(sol)
    if not s or not S.coordenador.eh_caixinha(s):
        raise LookupError("Solicitação inexistente ou não é da Conciliação Caixinha.")
    conc = resultado_registrado(sol, s, "caixinha_conciliacao")
    etapas = {}
    for e in s.get("plano_etapas", []):
        prefixo = S.coordenador.RESULTADOS_ETAPA[e["etapa"]]
        r = resultado_registrado(sol, s, prefixo)
        etapas[e["etapa"]] = {"situacao": e["situacao"], "tentativas": e.get("tentativas", 0), "resumo": (r or {}).get("resumo"),
                              "falha": (s.get("falhas_areas") or {}).get(e["etapa"]), "pendencias": [
                                  p.get("descricao") if isinstance(p, dict) else str(p) for p in (r or {}).get("pendencias", [])][:40]}
    vig = S.coordenador.vigencia(s) if s.get("caixinha_conciliacao") else None
    aprovado = s.get("estado") == "FECHAMENTO_APROVADO"
    return {"contrato": "PAINEL_CAIXINHA_V1", "sol": sol, "empresa": s["empresa"], "competencia": s["competencia"], "estado": s["estado"],
            "fluxo": s.get("fluxo"), "plano": etapas, "documentos": documentos_da_sol(sol, s), "conciliacao": conc,
            "vigencia": vig, "aprovacao": s.get("aprovacao"),
            "aprovacao_impedimentos": [] if aprovado else S.coordenador.impedimentos_aprovacao(s, todos, True, True),
            "aprovacao_exige_ciencia_revisao": bool(((conc or {}).get("resumo") or {}).get("revisao")),
            "aprovacao_exige_ciencia_exportados": [r["texto"] for r in S.coordenador.relacao_outras_sols(todos, sol)
                                                   if r["classificacao"] == "FATOS_JA_EXPORTADOS"] if not aprovado else [],
            "relacao_outras_sols": S.coordenador.relacao_outras_sols(todos, sol), "frase_aprovacao": f"APROVO FECHAMENTO {sol}",
            "situacao_txt": S.situacao_txt(s), "exportacao_permitida": S.exportacao_dominio.liberacao_permitida(s["empresa"]),
            "em_execucao": S.EM_EXECUCAO["sol"] == sol,
            "aviso": "SIMULAÇÃO. Pagamentos do e-CAC são a evidência das baixas tributárias; baixas de folha seguem a política operacional "
                     "aprovada (não são pagamentos individualmente comprovados). O saldo do Caixa é CONTÁBIL projetado, não conferência de "
                     "dinheiro físico. Importação no Domínio sempre manual."}


def documento_original(sol: str, doc_id: str):
    """(bytes, tipo, nome) do original de UM documento desta SOL, identificado pelo id da ficha (nunca por caminho do navegador),
    somente se o sha256 confere com o manifesto. Leitura apenas."""
    import adaptadores_fechamento as af
    s = S.coordenador.ler_registro()["solicitacoes"].get(sol)
    if not s or not S.coordenador.eh_caixinha(s):
        raise LookupError("Solicitação inexistente ou não é da Conciliação Caixinha.")
    doc = next((d for d in documentos_da_sol(sol, s) if d["id"] == doc_id), None)
    if not doc:
        raise LookupError("Documento não pertence a esta solicitação.")
    dados = af.original(S.coordenador.CLIENTES, s["empresa"], {"arquivo": doc["arquivo"], "sha256": doc["sha256"]})
    if dados is None:
        raise PermissionError("Original ausente ou alterado (sha256 não confere): documento não exibido.")
    ext = str(doc["arquivo"]).rsplit(".", 1)[-1].lower()
    tipo = {"pdf": "application/pdf", "txt": "text/plain; charset=utf-8", "csv": "text/plain; charset=utf-8"}.get(ext, "application/octet-stream")
    return dados, tipo, doc["nome"]


# ---------------------------------------------------------------- simulação do TXT (empresa real: NADA é gravado)
def simular_txt(sol: str) -> dict:
    """Validação, em SIMULAÇÃO, das baixas no layout do Domínio (mesmas regras do exportador): balanceamento por pagamento, datas na
    competência, contas analíticas, histórico. NÃO grava arquivo nem libera nada; serve para conferência antes da homologação."""
    import exportacao_dominio as ex
    s = S.coordenador.ler_registro()["solicitacoes"].get(sol)
    if not s or not S.coordenador.eh_caixinha(s):
        raise LookupError("Solicitação inexistente ou não é da Conciliação Caixinha.")
    conc = resultado_registrado(sol, s, "caixinha_conciliacao")
    if not conc:
        raise LookupError("Conciliação Caixinha ainda não registrada.")
    plano = ex.plano_empresa(s["empresa"])
    inicio, fim = s["competencia"] + "-01", ex._fim(s["competencia"]).isoformat()
    linhas, problemas, grupos = [], [], {}
    for l in conc["lancamentos"]:
        if l["status"] != "PROPOSTO":
            problemas.append(f"{l['id']}: proposta INCOMPLETA ({'; '.join(l.get('motivos_incompleto') or [])}) — fora do TXT.")
            continue
        erros = []
        try:
            v = ex.valor_exato(l["valor"])
        except ValueError as e:
            erros.append(str(e))
            v = None
        for lado in ("debito", "credito"):
            cod = (l.get(lado) or {}).get("codigo")
            c = plano.get(str(cod))
            if not c:
                erros.append(f"conta de {lado} {cod} inexistente no plano")
            elif c["tipo"] not in ("ANALITICA", "A"):
                erros.append(f"conta de {lado} {cod} não analítica")
        if not (l.get("data") and inicio <= l["data"] <= fim):
            erros.append(f"data {l.get('data')} fora da competência")
        try:
            texto, _ = ex.complemento(l.get("historico"))
        except ValueError as e:
            erros.append(str(e))
            texto = None
        if erros:
            problemas += [f"{l['id']}: {e}" for e in erros]
            continue
        g = grupos.setdefault(l["grupo"], {"debitos": Decimal("0"), "creditos": Decimal("0")})
        g["debitos"] += v
        g["creditos"] += v
        data = dt.date.fromisoformat(l["data"])
        linhas.append({"linha": ";".join([data.strftime("%d/%m/%Y"), l["debito"]["codigo"], l["credito"]["codigo"], ex.fmt_valor(v), "",
                                          texto, "1", "", "", ""]), "lancamento": l["id"], "origem": l["origem"], "valor": f"{v:.2f}"})
    total = sum((Decimal(x["valor"]) for x in linhas), Decimal("0"))
    return {"contrato": "SIMULACAO_TXT_CAIXINHA_V1", "sol": sol, "cabecalho": ex.CABECALHO, "linhas": linhas, "total": f"{total:.2f}",
            "partidas_simples": True, "balanceado": all(g["debitos"] == g["creditos"] for g in grupos.values()), "problemas": problemas,
            "exportacao_permitida": ex.liberacao_permitida(s["empresa"]),
            "aviso": "SIMULAÇÃO — NÃO IMPORTAR. Layout de partida simples ainda NÃO homologado no Domínio; TXT de empresa real bloqueado até "
                     "a homologação e uma autorização específica, auditável e por empresa. Nenhum arquivo foi gravado."}


# ---------------------------------------------------------------- execução em lote (várias empresas, uma de cada vez)
CATEGORIAS = {"CONCILIADA": "Conciliadas (nada a baixar, sem pendências)", "COM_DIVERGENCIAS": "Com divergências ou itens para revisão",
              "DOCUMENTOS_INSUFICIENTES": "Documentos insuficientes", "AGUARDANDO_APROVACAO": "Aguardando aprovação",
              "PRONTA_PARA_EXPORTACAO": "Aprovadas (prontas para exportação)", "EM_PROCESSAMENTO": "Em processamento",
              "SEM_SOLICITACAO": "Sem solicitação na competência"}


def categoria(sol: str, s: dict) -> tuple:
    estado = str(s.get("estado") or "")
    if estado.endswith("_EM_ANDAMENTO"):
        return "EM_PROCESSAMENTO", "Processando."
    if estado == "FECHAMENTO_APROVADO":
        return "PRONTA_PARA_EXPORTACAO", S.situacao_txt(s).get("texto") or "Aprovada."
    conc = (s.get("caixinha_conciliacao") or [None])[-1]
    if not conc:
        falhas = "; ".join((s.get("falhas_areas") or {}).values())
        return "DOCUMENTOS_INSUFICIENTES", falhas or "Conciliação não executada."
    res, alc = conc.get("resumo") or {}, conc.get("alcance") or {}
    if alc.get("parcial"):
        return "DOCUMENTOS_INSUFICIENTES", "; ".join(alc.get("motivos") or [])
    if res.get("bloqueantes") or res.get("incompletos") or res.get("revisao"):
        return "COM_DIVERGENCIAS", (f"{res.get('bloqueantes', 0)} bloqueio(s), {res.get('incompletos', 0)} proposta(s) incompleta(s), "
                                    f"{res.get('revisao', 0)} item(ns) em revisão")
    if res.get("propostos"):
        return "AGUARDANDO_APROVACAO", f"{res['propostos']} baixa(s) proposta(s)."
    return "CONCILIADA", "Sem baixas a propor e sem pendências."


def painel_lote(competencia: str) -> dict:
    registro = S.coordenador.ler_registro()["solicitacoes"]
    cadastradas = S.coordenador.empresas_cadastradas()
    empresas = []
    for ident, e in sorted(cadastradas.items()):
        if not S.coordenador.rotina_caixinha(e):
            continue
        sols = sorted((sol for sol, s in registro.items() if s.get("empresa") == ident and s.get("competencia") == competencia
                       and S.coordenador.eh_caixinha(s) and s.get("estado") != "CANCELADA" and not S.solicitacao_excluida(sol)))
        item = {"empresa": ident, "nome": e["razao_social"], "autorizada": S.coordenador.caixinha_permitido(e), "sol": None,
                "categoria": "SEM_SOLICITACAO", "texto": "Envie os documentos da competência.", "solicitacoes": sols}
        if sols:
            sol = sols[-1]
            cat, texto = categoria(sol, registro[sol])
            conc = (registro[sol].get("caixinha_conciliacao") or [{}])[-1]
            item.update(sol=sol, categoria=cat, texto=texto, estado=registro[sol].get("estado"), resumo=conc.get("resumo"))
        empresas.append(item)
    with TRAVA_FILA:
        fila = json.loads(json.dumps(FILA))
    return {"competencia": competencia, "categorias": CATEGORIAS, "empresas": empresas,
            "totais": {k: sum(1 for x in empresas if x["categoria"] == k) for k in CATEGORIAS}, "fila": fila,
            "aviso": "Cada empresa é processada isoladamente (uma solicitação por empresa), uma de cada vez, com os mesmos controles do "
                     "fluxo individual."}


def executar_fila(lotes: list) -> dict:
    """Valida TODOS os lotes antes (Caixinha, recebendo, com arquivos, empresas distintas) e inicia a fila em segundo plano: cada
    lote abre a SUA solicitação pelo mesmo caminho do início individual; o próximo só começa quando o anterior terminar."""
    if not isinstance(lotes, list) or not 1 <= len(lotes) <= 50 or len(set(lotes)) != len(lotes):
        raise ValueError("Informe de 1 a 50 lotes distintos.")
    empresas = set()
    for lote in lotes:
        if not isinstance(lote, str) or not S.RE_LOTE.fullmatch(lote):
            raise ValueError("Lote inválido.")
        d = S.ler_json(S.pasta_lote(lote) / "lote.json")
        if not d or d.get("estado") != "RECEBENDO" or d.get("fluxo") != "CONCILIACAO_CAIXINHA" or not d.get("arquivos"):
            raise ValueError(f"Lote {lote}: inexistente, já iniciado, sem arquivos ou de outro fluxo.")
        if d["empresa"] in empresas:
            raise ValueError(f"Mais de um lote da empresa {d['empresa']}: uma solicitação por empresa na fila.")
        empresas.add(d["empresa"])
    with TRAVA_FILA:
        if FILA["atual"] or (FILA["lotes"] and not FILA["fim"]):
            raise RuntimeError("Já há uma fila de conciliações em execução.")
        FILA.update(lotes=list(lotes), atual=None, inicio=S.agora(), fim=None, resultados=[])

    def rodar():
        import time
        for lote in lotes:
            with TRAVA_FILA:
                FILA["atual"] = lote
            fim = time.time() + 1800
            while (S.EM_EXECUCAO["sol"] or S.coordenador.ler_ordem() is not None) and time.time() < fim:
                time.sleep(0.5)
            codigo, dados = S.iniciar_lote(lote)
            sol = dados.get("sol")
            while sol and S.EM_EXECUCAO["sol"] == sol and time.time() < fim:
                time.sleep(0.5)
            with TRAVA_FILA:
                FILA["resultados"].append({"lote": lote, "codigo": codigo, "sol": sol, "erro": dados.get("erro")})
        with TRAVA_FILA:
            FILA.update(atual=None, fim=S.agora())
    threading.Thread(target=rodar, daemon=True).start()
    return {"resultado": "FILA_INICIADA", "lotes": lotes}
