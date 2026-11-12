"""PRÉVIA DO FECHAMENTO (MOTOR GERAL, somente leitura) — consolida os cinco departamentos de UMA SOL de UMA empresa.

FECHAMENTO não é departamento: é o processo coordenado que consolida FISCAL, FINANCEIRO, CONTÁBIL, DP e CONCILIAÇÃO.
Fontes: pacote de Documentos vigente (âncora conferida pelo servidor), resultados REGISTRADOS pelo Coordenador (via intercâmbio,
sha256 conferido) e documentos contábeis lidos pelos adapters (balancete, razão, book). Nada é gravado, aprovado ou escriturado.

STATUS POR DEPARTAMENTO (fórmula determinística; sem percentual — um percentual seria enganoso nesta fase):
  EM_PROCESSAMENTO      etapa do departamento em andamento agora;
  AGUARDANDO_SUPERVISOR checkpoint pendente que envolve o departamento, ou decisão do Supervisor necessária (ex.: propostas);
  NAO_INICIADO          nenhuma etapa do departamento executada (e, na Conciliação, balanço sem book+balancete);
  COM_PENDENCIAS        executou e restou pendência BLOQUEIO ou ATENÇÃO do departamento;
  CONCLUIDO             executou, sem pendências e sem decisão necessária.
PENDÊNCIA: PROBLEMA · IMPACTO · O QUE FAZER · INFORMATIVO/ATENÇÃO/BLOQUEIO · empresa · competência · departamento responsável
(quem deve agir — não quem detectou) · origem · evidência.
"""
import calendar
import datetime as dt
import json
import re
from decimal import Decimal
from pathlib import Path

import adaptadores_fechamento as af
import book_contabil
import intercambio as ic

CONTRATO = "PREVIA_FECHAMENTO_V1"
NOME_ETAPA = {"FINANCEIRO": "Financeiro", "BANCOS": "Contábil (bancos)", "DP": "DP", "FISCAL": "Fiscal",
              "CONTABILIDADE_DP": "Contábil (DP)", "CONTABILIDADE_FISCAL": "Contábil (fiscal)", "CONCILIACAO": "Conciliação"}
ETAPAS_DEP = {"FISCAL": ("FISCAL",), "FINANCEIRO": ("FINANCEIRO",), "CONTABIL": ("BANCOS", "CONTABILIDADE_FISCAL", "CONTABILIDADE_DP"),
              "DP": ("DP",), "CONCILIACAO": ("CONCILIACAO",)}
STATUS_TEXTO = {"NAO_INICIADO": "Não iniciado", "EM_PROCESSAMENTO": "Em processamento", "AGUARDANDO_SUPERVISOR": "Aguardando Supervisor",
                "COM_PENDENCIAS": "Com pendências", "CONCLUIDO": "Concluído"}
STATUS_CONTA = ("CONCILIADA", "DIVERGENTE", "SEM_COMPOSICAO", "COMPOSICAO_INCOMPLETA", "AGUARDANDO_DOCUMENTO", "AGUARDANDO_SUPERVISOR")
LIMITE_LISTA = 80
# área responsável declarada pela Conciliação (CONCILIACAO_V1) → departamento
AREA_CONCILIACAO = {"BANCOS": "CONTABIL", "CONTABILIDADE": "CONTABIL", "CONTABILIDADE/BANCOS": "CONTABIL", "CONTABILIDADE/DP": "CONTABIL",
                    "CONTABILIDADE/FISCAL": "CONTABIL", "CONTABILIDADE_DP": "CONTABIL", "CONTABILIDADE_FISCAL": "CONTABIL",
                    "FINANCEIRO": "FINANCEIRO", "FISCAL": "FISCAL", "DP": "DP", "CONCILIACAO": "CONCILIACAO", "DOCUMENTOS": "COORDENADOR",
                    "COORDENADOR": "COORDENADOR", "SUPERVISOR": "SUPERVISOR"}
# Responsável ESPERADO por divergência de conta (sugestão determinística pela descrição; o Supervisor pode reatribuir).
RESPONSAVEL_CONTA = ((("SALARIO", "FERIAS", "PRO LABORE", "PROLABORE", "RESCIS", "FGTS", "INSS", "ENCARGO", "13 SALARIO", "13O"), "DP"),
                     (("ISS", "PIS", "COFINS", "IRPJ", "CSLL", "ICMS", "IPI", "IMPOSTO", "TRIBUT", "IRRF", "SIMPLES"), "FISCAL"),
                     (("BANCO", "CAIXA", "APLICAC", "INVESTIMENTO"), "FINANCEIRO"),
                     (("FORNECEDOR", "CLIENTE", "DUPLICATA"), "FISCAL"))


def responsavel_conta(descricao: str) -> str:
    d = " " + ic.norm(descricao) + " "
    for marcas, dep in RESPONSAVEL_CONTA:
        if any(re.search(r"(?<![A-Z])" + re.escape(m) + r"(?:S|ES)?(?![A-Z])", d) for m in marcas):
            return dep
    return "CONTABIL"


def ultimo_dia(comp: str) -> str:
    a, m = map(int, comp.split("-"))
    return dt.date(a, m, calendar.monthrange(a, m)[1]).isoformat()


def pend(classificacao, departamento, problema, impacto, oque, origem, evidencia=None, ctx=None, responsavel=None):
    return {"classificacao": classificacao, "departamento": departamento, "responsavel_esperado": responsavel or departamento,
            "problema": problema, "impacto": impacto, "o_que_fazer": oque, "origem": origem, "evidencia": evidencia or {},
            "empresa": (ctx or {}).get("empresa"), "competencia": (ctx or {}).get("competencia")}


# ---------------------------------------------------------------- CONCILIAÇÃO DO BALANÇO (book × balancete × razão)
def conciliar_balanco(balancete, book, razao, competencia, docs=None) -> dict:
    """Resultado por conta: CONCILIADA | DIVERGENTE | SEM_COMPOSICAO | COMPOSICAO_INCOMPLETA | AGUARDANDO_DOCUMENTO |
    AGUARDANDO_SUPERVISOR, com PROBLEMA/IMPACTO/O QUE FAZER e departamento responsável. Igualdade exata (Decimal)."""
    docs = docs or {}
    contas, avisos = {}, []
    if not balancete and not book:
        return {"situacao": "AGUARDANDO_DOCUMENTO", "contas": [], "resumo": {k: 0 for k in STATUS_CONTA},
                "avisos": ["Balancete e book do período não recebidos: a conciliação do balanço aguarda os documentos."]}
    if not balancete:
        for c in book["contas"]:
            contas[c["conta"]] = _conta(c["conta"], c.get("descricao"), "AGUARDANDO_DOCUMENTO", "Book recebido sem o balancete do período.",
                                        "Sem balancete não há saldo contábil para confrontar a composição.",
                                        "Enviar o balancete do período (Contábil).", "CONTABIL", saldo_composicao=c.get("saldo_composicao"))
        return _fechar(contas, ["Balancete do período não recebido."])
    bal = {c["conta"]: c for c in balancete["contas"]}
    if not book:
        for c in balancete["contas"]:
            if c.get("exige_composicao"):
                contas[c["conta"]] = _conta(c["conta"], c.get("descricao"), "AGUARDANDO_DOCUMENTO", "Conta patrimonial com saldo sem book recebido.",
                                            "Saldo sem composição: o balanço não pode ser validado.", "Enviar o book de conciliação (Conciliação).",
                                            "CONCILIACAO", saldo_balancete=c.get("saldo_final"))
        avisos.append("Book do período não recebido.")
    else:
        conf = book_contabil.confrontar(book["_lido"], balancete["_contas_leitor"], ultimo_dia(competencia))
        for x in conf["composicoes"]:
            k = (x.get("conta") or {}).get("classificacao") or str((x.get("identificador") or {}).get("classificacao") or x["aba"])
            desc = (x.get("conta") or {}).get("descricao") or ""
            resp = responsavel_conta(desc)
            cn, ident = x["conferencia_numerica"], x["identificacao_itens"]
            base = dict(saldo_balancete=x.get("saldo_balancete"), saldo_composicao=x.get("saldo_composicao"), diferenca=x.get("diferenca"),
                        aba=x["aba"], itens=len(x["itens"]) if isinstance(x.get("itens"), list) else x.get("itens"))
            if cn == "IGUAL_AO_BALANCETE" and ident == "ITENS_IDENTIFICADOS_NA_FONTE" and not x["pendencias_book"]:
                contas[k] = _conta(k, desc, "CONCILIADA", "Saldo da composição igual ao balancete; itens identificados na fonte.",
                                   "Conferência numérica concluída; evidências e confirmação do Supervisor continuam separadas.",
                                   "Nenhuma ação numérica; conferir evidências na revisão.", resp, **base)
            elif cn == "IGUAL_AO_BALANCETE":
                contas[k] = _conta(k, desc, "COMPOSICAO_INCOMPLETA", "Saldo igual ao balancete, mas a composição tem itens sem identificação "
                                   "ou pendências declaradas no book.", "A conta não pode ser dada como conciliada.",
                                   f"Completar a composição (documento/terceiro dos itens) — {af.NOME_DEPARTAMENTO[resp]}.", resp, **base)
            elif cn == "DIVERGENTE":
                contas[k] = _conta(k, desc, "DIVERGENTE", x["explicacao"],
                                   "Saldo contábil não comprovado pela composição; o balanço não fecha nesta conta.",
                                   f"Investigar a diferença ({'possível documento faltante' if resp == 'FISCAL' else 'lançamento/composição'})"
                                   f" — responsável esperado: {af.NOME_DEPARTAMENTO[resp]}. Nenhum ajuste automático.", resp, **base)
            else:
                contas[k] = _conta(k, desc, "AGUARDANDO_SUPERVISOR", x["explicacao"], "Sem decisão não é possível concluir a conta.",
                                   "Confirmar com o Supervisor (conta/sinal da composição).", "CONCILIACAO", responsavel="SUPERVISOR", **base)
        for c in conf["contas_com_saldo_sem_composicao"]:
            resp = responsavel_conta(c.get("descricao"))
            contas[c["classificacao"]] = _conta(c["classificacao"], c.get("descricao"), "SEM_COMPOSICAO",
                                                "Conta patrimonial analítica com saldo e sem composição no book.",
                                                "Saldo não comprovado; o balanço não pode ser validado nesta conta.",
                                                f"Incluir a composição no book (responsável esperado: {af.NOME_DEPARTAMENTO[resp]}).", resp,
                                                saldo_balancete=c.get("saldo"))
        avisos.append(conf["aviso"])
    if razao:
        soma = {}
        for l in razao["lancamentos"]:
            d, c = soma.get(l["conta"], (Decimal("0"), Decimal("0")))
            soma[l["conta"]] = (d + Decimal(l["debito"]), c + Decimal(l["credito"]))
        por_codigo = {str(c.get("codigo")): c for c in balancete["contas"] if c.get("codigo")}
        for conta, (d, c) in soma.items():
            b = bal.get(conta) or por_codigo.get(conta)
            if not b:
                avisos.append(f"Razão: conta {conta} não consta no balancete.")
                continue
            if b.get("debitos") is None or b.get("creditos") is None:
                continue
            if (Decimal(b["debitos"]), Decimal(b["creditos"])) != (d, c):
                k = b["conta"]
                prev = contas.get(k)
                contas[k] = _conta(k, b.get("descricao"), "DIVERGENTE",
                                   f"Razão (D {d:.2f} / C {c:.2f}) ≠ movimento do balancete (D {b['debitos']} / C {b['creditos']}).",
                                   "Movimento contábil sem rastreabilidade completa entre razão e balancete.",
                                   "Conferir os lançamentos da conta no razão e no balancete (Contábil).", "CONTABIL",
                                   saldo_balancete=b.get("saldo_final"), anterior=(prev or {}).get("status"))
            elif k_ok := contas.get(b["conta"]):
                k_ok.setdefault("verificacoes", []).append("Razão confere com o movimento do balancete.")
    return _fechar(contas, avisos)


def _conta(conta, descricao, status, problema, impacto, oque, departamento, responsavel=None, **extra):
    return {"conta": conta, "descricao": descricao, "status": status, "problema": problema, "impacto": impacto, "o_que_fazer": oque,
            "departamento_responsavel": responsavel or departamento, **{k: v for k, v in extra.items() if v is not None}}


def _fechar(contas, avisos):
    lista = sorted(contas.values(), key=lambda c: (STATUS_CONTA.index(c["status"]) if c["status"] != "CONCILIADA" else 99, c["conta"]))
    resumo = {k: sum(c["status"] == k for c in lista) for k in STATUS_CONTA}
    return {"situacao": "CALCULADA", "contas": lista, "resumo": resumo, "avisos": avisos}


# ---------------------------------------------------------------- montagem da prévia
def _ler(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8")) if p and Path(p).is_file() else None
    except (OSError, ValueError):
        return None


def montar(runtime, clientes, sol, s, manifesto_path, extracao_path, registro=None, tentativa=None, tentativas=None,
           ambiente="REAL", em_execucao=False, problema_ancora=None, central=None) -> dict:
    ctx0 = {"empresa": s.get("empresa"), "competencia": s.get("competencia")}
    pendencias, decisoes, avisos = [], [], []
    plano = s.get("plano_etapas") or []
    situacoes = {e["etapa"]: e["situacao"] for e in plano}
    estado = s.get("estado") or ""
    ck = s.get("checkpoint") if (s.get("checkpoint") or {}).get("situacao") in ("AGUARDANDO_FINANCEIRO", "AGUARDANDO_AUTORIZACAO") else None

    # ---- documentos (pacote vigente) e reconhecimento pelos adapters
    manifesto = None if problema_ancora else _ler(manifesto_path)
    extracao = None if problema_ancora else _ler(extracao_path)
    if problema_ancora:
        pendencias.append(pend("BLOQUEIO", "COORDENADOR", problema_ancora, "Nenhum documento do pacote é usado na prévia.",
                               "Recriar a tentativa/pacote a partir dos originais (Coordenador).", "COORDENADOR", ctx=ctx0))
    por_arquivo = {a["arquivo"]: a for a in (extracao or {}).get("arquivos", [])}
    res_area = {}
    for etapa in ("FISCAL", "DP"):
        r, _ = ic.resultado_registrado(runtime, sol, s, etapa)
        for d in (r or {}).get("documentos", []):
            res_area[d.get("arquivo")] = d.get("tipo")
    documentos, normalizados = [], {}
    for item in (manifesto or {}).get("itens", []):
        rec = af.reconhecer(item, por_arquivo.get(item["arquivo"]), clientes, s["empresa"], res_area)
        n = rec.pop("normalizado", None)
        if n:
            chave = {"BALANCETE_NORMALIZADO_V1": "BALANCETE", "RAZAO_CONTABIL_NORMALIZADO_V1": "RAZAO",
                     "BOOK_CONCILIACAO_CONTABIL_V1": "BOOK"}[n["contrato"]]
            if chave in normalizados:
                rec["observacao"] = f"Mais de um {chave.lower()} no pacote: somente o primeiro foi usado na conciliação do balanço."
                pendencias.append(pend("ATENCAO", rec["departamento"], f"Mais de um documento do tipo {chave.lower()} no fechamento "
                                       f"({rec['arquivo']}).", "Somente o primeiro é usado na conciliação do balanço.",
                                       "Manter só a versão correta do documento.", "DOCUMENTOS", {"documento": rec["arquivo"]}, ctx0))
            else:
                normalizados[chave] = n
                normalizados[chave + "_DOC"] = {"arquivo": item["arquivo"], "sha256": item["sha256"]}
                rec["resumo_normalizado"] = ({"contas": len(n["contas"])} if chave != "RAZAO" else {"lancamentos": len(n["lancamentos"])})
        rec["nome"] = str(item["arquivo"]).rsplit("/", 1)[-1]
        documentos.append(rec)
        if rec["situacao"] == af.NAO_RECONHECIDO:
            pendencias.append(pend("ATENCAO", "COORDENADOR", f"{rec['nome']}: {rec.get('motivo')}",
                                   "O documento não foi distribuído a nenhum departamento.",
                                   "Supervisor: classificar o documento (ou retirá-lo do fechamento). Não adivinhar.", "DOCUMENTOS",
                                   {"documento": rec["arquivo"], "sha256": rec["sha256"]}, ctx0, responsavel="SUPERVISOR"))
        elif rec["situacao"] == af.LAYOUT_NOVO:
            pendencias.append(pend("ATENCAO", rec["departamento"], f"{rec['nome']}: layout novo — {rec.get('motivo')}",
                                   "Os dados deste documento não entram no fechamento até existir um adapter validado.",
                                   "AGUARDANDO ARQUIVO REAL PARA CRIAR/VALIDAR ADAPTER: inspecionar o layout → adapter determinístico "
                                   "→ testar → processar.", "DOCUMENTOS", {"documento": rec["arquivo"], "sha256": rec["sha256"]}, ctx0))
    classificacao = {}
    for d in documentos:
        dep = classificacao.setdefault(d["departamento"], {"total": 0, "categorias": {}})
        dep["total"] += 1
        dep["categorias"][d["categoria"]] = dep["categorias"].get(d["categoria"], 0) + 1

    # ---- intercâmbio (resultados registrados, isolamento por empresa)
    try:
        ctx = ic.contexto(runtime, clientes, registro or {sol: s}, sol, normalizados)
        liberados = set((central or {}).get("liberados") or [])
        fin_x = ic.analisar_financeiro(ctx, liberados)
    except ic.IsolamentoViolado as exc:
        ctx = {"empresa": s.get("empresa"), "competencia": s.get("competencia"), "itens": [], "movimentos": [], "avisos": [str(exc)],
               "resultados": {}, "brutos": {}, "politica_temporal": {}}
        fin_x = {"movimentos": [], "pendencias_cruzadas": [], "obrigacoes_com_pagamento": {}}
        liberados = set()
        pendencias.append(pend("BLOQUEIO", "COORDENADOR", str(exc), "Consulta entre departamentos interrompida.",
                               "Acionar o responsável técnico; nenhum dado de outra empresa foi usado.", "INTERCAMBIO", ctx=ctx0))
    for a in ctx["avisos"]:
        pendencias.append(pend("BLOQUEIO", "COORDENADOR", a, "O resultado da etapa não é usado na prévia.",
                               "Reexecutar a etapa por nova tentativa (Coordenador).", "INTERCAMBIO", ctx=ctx0))
    pendencias += fin_x["pendencias_cruzadas"]
    brutos = ctx["brutos"]

    # ---- pendências das áreas (resultados registrados)
    for etapa, motivo in (s.get("falhas_areas") or {}).items():
        dep = ic.DEPARTAMENTO_ETAPA.get(etapa, "COORDENADOR")
        pendencias.append(pend("BLOQUEIO", dep, f"Etapa {NOME_ETAPA.get(etapa, etapa)} falhou: {str(motivo)[:240]}",
                               "As etapas que dependem dela não executaram.", "Corrigir a causa e reexecutar por nova tentativa.",
                               "COORDENADOR", ctx=ctx0))
    for dep, etapa in (("FISCAL", "FISCAL"), ("DP", "DP")):
        for p in ((brutos.get(etapa) or {}).get("pendencias") or [])[:LIMITE_LISTA]:
            pendencias.append(pend("ATENCAO", dep, f"{str(p.get('arquivo', '')).rsplit('/', 1)[-1]}: {p.get('descricao')}",
                                   "O documento não gera proposta contábil enquanto a pendência existir.",
                                   f"Conferir o documento no {af.NOME_DEPARTAMENTO[dep]}.", dep,
                                   {"documento": p.get("arquivo"), **(ctx.get("resultados", {}).get(etapa) or {})}, ctx0))
    fin = brutos.get("FINANCEIRO") or {}
    resumo_central = (central or {}).get("resumo") or {}
    central_resolveu = bool(central and not central.get("corrompido") and resumo_central.get("movimentos_bancarios")
                            and resumo_central.get("bloqueios_restantes") == 0)
    if central and central.get("corrompido"):
        pendencias.append(pend("BLOQUEIO", "FINANCEIRO", "Registro de decisões da Central inconsistente.", "Nenhuma decisão é considerada.",
                               "Avisar o responsável técnico (nada foi alterado).", "FINANCEIRO", ctx=ctx0))
    for b in fin.get("bloqueio_lote") or []:
        if central_resolveu:
            pendencias.append(pend("INFORMATIVO", "FINANCEIRO", f"Bloqueio registrado na última execução do Financeiro: {b}",
                                   f"Já resolvido na Central: {resumo_central.get('movimentos_confirmados')}/{resumo_central.get('movimentos_bancarios')} "
                                   "movimentos com associação confirmada pelas decisões vigentes do Supervisor.",
                                   'A próxima tentativa ("Reprocessar fechamento") executa o Financeiro com essas decisões.', "FINANCEIRO", ctx=ctx0))
            continue
        pendencias.append(pend("BLOQUEIO", "FINANCEIRO", b, "Nada segue automaticamente para a proposta contábil dos bancos.",
                               "Revisar as associações na Central de Revisão (Supervisor) ou enviar suporte.", "FINANCEIRO", ctx=ctx0))
    for p in (fin.get("pendencias") or [])[:LIMITE_LISTA]:
        if p.get("tipo") == "ASSOCIACAO_FINANCEIRA_NAO_CONFIRMADA":
            continue
        pendencias.append(pend("ATENCAO", "FINANCEIRO", str(p.get("descricao"))[:300], "Movimento sem suporte completo.",
                               "Conferir no Financeiro (suporte, natureza ou decisão).", "FINANCEIRO", {"referencia": p.get("referencia")}, ctx0))
    cruzados = {(p.get("evidencia") or {}).get("movimento") for p in fin_x["pendencias_cruzadas"]}
    for x in fin_x["movimentos"]:
        if x["resolvido"] or x["movimento"] in cruzados:
            continue
        cand = f"{len(x['candidatos'])} candidato(s) de outras áreas para revisão" if x["candidatos"] else "nenhum candidato nas outras áreas"
        pendencias.append(pend("ATENCAO", "FINANCEIRO", f"Movimento sem suporte ou associação confirmada: {x['data']} · {x['descricao']} · "
                               f"R$ {x['valor']} ({cand}).", "A liquidação não tem suporte confirmado para a proposta contábil.",
                               "Revisar o movimento no Financeiro (suporte, natureza ou decisão do Supervisor).", "FINANCEIRO",
                               {"movimento": x["movimento"]}, ctx0))
    propostas = [it for it in ctx["itens"] if it["tipo"] == "PROPOSTA_CONTABIL" and it["proveniencia"]["sol"] == sol]
    for l in propostas:
        if l.get("status") == "INCOMPLETO":
            pendencias.append(pend("ATENCAO", "CONTABIL", f"Proposta {l['id']} incompleta: {'; '.join(l.get('pendencias') or [])[:240]}",
                                   "A proposta não pode ser aprovada.", "Completar a informação faltante (regra, conta ou documento).",
                                   NOME_ETAPA.get(l["etapa"], l["etapa"]), {"proposta": l["id"], **l["proveniencia"]}, ctx0))
    conc = brutos.get("CONCILIACAO") or {}
    for v in conc.get("verificacoes") or []:
        if v.get("resultado") in ("DIVERGENTE", "PENDENTE", "NAO_DETERMINADO"):
            area = str(v.get("area_responsavel") or "COORDENADOR").upper()
            dep = AREA_CONCILIACAO.get(area, AREA_CONCILIACAO.get(area.split("/")[0], "COORDENADOR"))
            pendencias.append(pend("BLOQUEIO" if v["resultado"] == "DIVERGENTE" else "ATENCAO", dep if dep in af.DEPARTAMENTOS else "COORDENADOR",
                                   f"{v.get('titulo')}: {str(v.get('justificativa'))[:240]}", "Verificação da Conciliação não concluída.",
                                   str(v.get("acao") or "Tratar com o departamento responsável."), "CONCILIACAO", {"verificacao": v.get("id")}, ctx0))

    # ---- conciliação do balanço
    balanco = conciliar_balanco(normalizados.get("BALANCETE"), normalizados.get("BOOK"), normalizados.get("RAZAO"), s["competencia"])
    for c in balanco["contas"]:
        if c["status"] == "CONCILIADA":
            continue
        pendencias.append(pend("BLOQUEIO" if c["status"] == "DIVERGENTE" else "ATENCAO",
                               c["departamento_responsavel"] if c["departamento_responsavel"] in af.DEPARTAMENTOS else "CONCILIACAO",
                               f"Conta {c['conta']} {c.get('descricao') or ''}: {c['problema']}", c["impacto"], c["o_que_fazer"],
                               "CONCILIACAO (balanço)", {"conta": c["conta"], **(normalizados.get("BALANCETE_DOC") or {})}, ctx0,
                               responsavel=c["departamento_responsavel"]))
        if c["status"] == "AGUARDANDO_SUPERVISOR":
            decisoes.append({"departamento": "CONCILIACAO", "decisao": f"Confirmar a conta {c['conta']} no balanço", "detalhe": c["problema"]})

    # ---- impostos
    pagas = fin_x["obrigacoes_com_pagamento"]
    obrig = [it for it in ctx["itens"] if it["tipo"] == "OBRIGACAO"]
    etapa_prov = {"FISCAL": "CONTABILIDADE_FISCAL", "DP": "CONTABILIDADE_DP"}
    impostos = []
    for o in obrig:
        prov = [p for p in propostas if p.get("etapa") == etapa_prov.get(o["departamento"]) and ic.dec(p.get("valor")) == ic.dec(o.get("total"))]
        impostos.append({"id": o["id"], "tributo": o.get("tributo"), "codigo": o.get("codigo"), "competencia": o.get("competencia"),
                         "vencimento": o.get("vencimento"), "total": o.get("total"), "departamento": o["departamento"], "papel": o.get("papel"),
                         "provisao_proposta": [p["id"] for p in prov], "pagamento_identificado": pagas.get(o["id"], []),
                         "pendencias": o.get("pendencias") or [], "proveniencia": o["proveniencia"]})

    # ---- departamentos
    def docs_dep(dep):
        return [d for d in documentos if d["departamento"] == dep]

    def pend_dep(dep):
        return [p for p in pendencias if p["departamento"] == dep]

    movs = ctx["movimentos"]
    resolvidos = sum(ic.movimento_resolvido(m, liberados) for m in movs)
    status_ck = (ck or {}).get("situacao")
    if status_ck == "AGUARDANDO_AUTORIZACAO":
        decisoes.insert(0, {"departamento": "FINANCEIRO", "decisao": "Autorizar a continuação após o Financeiro (checkpoint)",
                            "detalhe": "Revise o Financeiro e as consultas às outras áreas; a Contabilidade e a Conciliação só começam "
                                       "com a sua autorização."})
    if fin.get("bloqueio_lote") and not central_resolveu:
        decisoes.append({"departamento": "FINANCEIRO", "decisao": "Revisar associações na Central de Revisão", "detalhe": fin["bloqueio_lote"][0]})
    completas = [p for p in propostas if str(p.get("status", "")).startswith("PROPOSTO")]
    if completas and not s.get("aprovacao") and not ck:
        decisoes.append({"departamento": "CONTABIL", "decisao": f"Revisar {len(completas)} proposta(s) contábil(eis) (SIMULAÇÃO)",
                         "detalhe": "Propostas não são lançamentos: só valem com a aprovação explícita do Supervisor."})
    acf = classificacao.get("A_CONFERIR", {}).get("total", 0)
    if acf:
        decisoes.append({"departamento": "SUPERVISOR", "decisao": f"Classificar {acf} documento(s) não reconhecido(s)", "detalhe": "Não adivinhar."})
    for q in ((s.get("conciliacao") or [{}])[-1].get("perguntas_supervisor") or [])[:10]:
        decisoes.append({"departamento": "CONCILIACAO", "decisao": "Pergunta da Conciliação", "detalhe": str(q.get("pergunta") if isinstance(q, dict) else q)[:240]})

    def status_dep(dep, executou_extra=False):
        etapas = [e for e in ETAPAS_DEP[dep] if e in situacoes]
        if any(estado == e + "_EM_ANDAMENTO" for e in etapas):
            return "EM_PROCESSAMENTO"
        if dep == "FINANCEIRO" and status_ck == "AGUARDANDO_AUTORIZACAO":
            return "AGUARDANDO_SUPERVISOR"
        if ck and any(situacoes.get(e) == "PENDENTE" for e in etapas) and status_ck == "AGUARDANDO_AUTORIZACAO":
            return "AGUARDANDO_SUPERVISOR"
        executou = executou_extra or any(situacoes.get(e) in ("CONCLUIDA", "FALHOU", "BLOQUEADA", "BLOQUEADA_POR_DEPENDENCIA") for e in etapas)
        if not executou:
            return "NAO_INICIADO"
        ps = pend_dep(dep) + (detectadas_conciliacao() if dep == "CONCILIACAO" else [])
        if any(p["classificacao"] == "BLOQUEIO" for p in ps):
            return "COM_PENDENCIAS"
        if any(d["departamento"] == dep for d in decisoes):
            return "AGUARDANDO_SUPERVISOR"
        return "COM_PENDENCIAS" if ps else "CONCLUIDO"

    def detectadas_conciliacao():
        return [p for p in pendencias if str(p.get("origem", "")).startswith("CONCILIACAO") and p["departamento"] != "CONCILIACAO"]

    def acao(dep, st):
        if st == "AGUARDANDO_SUPERVISOR" and status_ck == "AGUARDANDO_AUTORIZACAO" and dep != "FINANCEIRO":
            return "Aguardando a sua autorização no checkpoint após o Financeiro."
        if dep == "CONCILIACAO" and detectadas_conciliacao():
            return (f"{len(detectadas_conciliacao())} pendência(s) detectada(s) pela Conciliação e encaminhada(s) aos departamentos "
                    "responsáveis (ver Pendências).")
        if st == "EM_PROCESSAMENTO":
            return "Aguarde: a etapa está em execução."
        if st == "NAO_INICIADO":
            return ("Nenhum documento recebido para este departamento." if not docs_dep(dep) and dep != "CONTABIL"
                    else 'Documentos recebidos; use "Preparar fechamento" para iniciar.' if not plano else "Aguardando as etapas anteriores.")
        d = next((x for x in decisoes if x["departamento"] == dep), None)
        if d:
            return d["decisao"] + "."
        ps = pend_dep(dep)
        if ps:
            return f"Tratar {len(ps)} pendência(s) — começando por: {ps[0]['o_que_fazer']}"
        return "Nenhuma ação pendente."

    fis = brutos.get("FISCAL") or {}
    dpr = brutos.get("DP") or {}
    deps = {
        "FISCAL": {"documentos_recebidos": len(docs_dep("FISCAL")), "processados": len(fis.get("documentos") or []),
                   "aptos_para_proposta": (fis.get("resumo") or {}).get("aptos_proposta", 0),
                   "notas_fiscais": [{"numero": it.get("numero"), "tipo": it.get("subtipo"), "sentido": it.get("sentido"), "valor": it.get("valor"),
                                      "pendencias": len(it.get("pendencias") or []), "proveniencia": it["proveniencia"]}
                                     for it in ctx["itens"] if it["tipo"] == "DOCUMENTO_FISCAL"][:LIMITE_LISTA],
                   "obrigacoes": sum(o["departamento"] == "FISCAL" for o in obrig),
                   "propostas": sum(p.get("etapa") == "CONTABILIDADE_FISCAL" for p in propostas)},
        "FINANCEIRO": {"documentos_recebidos": len(docs_dep("FINANCEIRO")), "movimentos": len(movs), "conciliados_ou_confirmados": resolvidos,
                       "pendentes": len(movs) - resolvidos, "com_suporte": (fin.get("resumo") or {}).get("com_suporte", 0),
                       "checkpoint": status_ck or ("AUTORIZADO" if s.get("checkpoints") else None),
                       "central": {k: resumo_central.get(k) for k in ("movimentos_bancarios", "movimentos_confirmados", "bloqueios_restantes",
                                                                     "aprovados_supervisor", "conciliados_automaticamente")} if resumo_central else None,
                       "consultas_outras_areas": [x for x in fin_x["movimentos"] if not x["resolvido"]][:LIMITE_LISTA],
                       "candidatos_encontrados": sum(len(x["candidatos"]) for x in fin_x["movimentos"])},
        "CONTABIL": {"documentos_recebidos": len(docs_dep("CONTABIL")), "propostas": len(propostas), "completas": len(completas),
                     "incompletas": sum(p.get("status") == "INCOMPLETO" for p in propostas),
                     "aguardando_supervisor": 0 if s.get("aprovacao") else len(completas),
                     "lancamentos_efetivados": 0, "balancete": bool(normalizados.get("BALANCETE")), "razao": bool(normalizados.get("RAZAO")),
                     "lista_propostas": [{k: p.get(k) for k in ("id", "etapa", "data", "debito", "credito", "valor", "historico", "status")}
                                         | {"proveniencia": p["proveniencia"]} for p in propostas][:LIMITE_LISTA]},
        "DP": {"documentos_recebidos": len(docs_dep("DP")), "processados": len(dpr.get("documentos") or []),
               "pendentes": len(dpr.get("pendencias") or []), "obrigacoes": sum(o["departamento"] == "DP" for o in obrig),
               "propostas": sum(p.get("etapa") == "CONTABILIDADE_DP" for p in propostas)},
        "CONCILIACAO": {"documentos_recebidos": len(docs_dep("CONCILIACAO")), "contas": len(balanco["contas"]), **balanco["resumo"],
                        "verificacoes_conciliacao": (s.get("conciliacao") or [{}])[-1].get("resumo") if s.get("conciliacao") else None},
    }
    for dep, d in deps.items():
        extra = dep == "CONCILIACAO" and balanco["situacao"] == "CALCULADA"
        d["status"] = status_dep(dep, extra)
        d["status_texto"] = STATUS_TEXTO[d["status"]]
        d["pendencias"] = len(pend_dep(dep))
        d["bloqueios"] = sum(p["classificacao"] == "BLOQUEIO" for p in pend_dep(dep))
        if dep == "CONCILIACAO":
            d["pendencias_detectadas_para_outros"] = len(detectadas_conciliacao())
        d["acao_necessaria"] = acao(dep, d["status"])
        d["nome"] = af.NOME_DEPARTAMENTO[dep]

    # ---- status geral e checkpoints
    executadas = [e for e in plano if e["situacao"] != "PENDENTE"]
    if em_execucao or estado.endswith("_EM_ANDAMENTO"):
        geral = ("EM_PROCESSAMENTO", "Fechamento em processamento")
    elif status_ck == "AGUARDANDO_AUTORIZACAO":
        geral = ("AGUARDANDO_SUPERVISOR", "Checkpoint após o Financeiro: aguardando a autorização do Supervisor")
    elif estado == "FECHAMENTO_APROVADO":
        geral = ("APROVADO_SIMULACAO", "Fechamento aprovado em SIMULAÇÃO (nada escriturado)")
    elif not executadas:
        geral = ("NAO_INICIADO", 'Documentos recebidos e classificados; aguardando "Preparar fechamento"')
    elif any(e["situacao"] in ("FALHOU", "BLOQUEADA", "BLOQUEADA_POR_DEPENDENCIA") for e in plano):
        geral = ("EXECUCAO_INTERROMPIDA", 'Execução anterior interrompida (etapa bloqueada ou com falha): trate as pendências e use '
                                          '"Reprocessar fechamento" para uma nova tentativa')
    else:
        geral = ("PREVIA_PRONTA", "Prévia pronta para a revisão do Supervisor (checkpoint final)")
    checkpoints = [{"nome": "Checkpoint 1 — após o Financeiro", "situacao": c.get("situacao"), "em": c.get("atingido_em") or c.get("solicitado_em"),
                    "autorizado_em": c.get("autorizado_em"), "tentativa": c.get("tentativa")} for c in (s.get("checkpoints") or [])]
    if ck:
        checkpoints.append({"nome": "Checkpoint 1 — após o Financeiro", "situacao": ck.get("situacao"),
                            "em": ck.get("atingido_em") or ck.get("solicitado_em"), "tentativa": ck.get("tentativa"),
                            "proximas_etapas": [NOME_ETAPA.get(e, e) for e in ck.get("proximas_etapas") or []]})
    checkpoints.append({"nome": "Checkpoint final — prévia pronta para revisão", "situacao": "ATINGIDO" if geral[0] == "PREVIA_PRONTA"
                        else "APROVADO" if geral[0] == "APROVADO_SIMULACAO" else "NAO_ATINGIDO"})
    if geral[0] == "EXECUCAO_INTERROMPIDA":
        decisoes.append({"departamento": "SUPERVISOR", "decisao": 'Reprocessar o fechamento (nova tentativa)',
                         "detalhe": "A última execução parou numa etapa bloqueada ou com falha; a prévia não está completa."})
    if geral[0] == "PREVIA_PRONTA":
        decisoes.append({"departamento": "SUPERVISOR", "decisao": "Revisar a prévia do fechamento (checkpoint final)",
                         "detalhe": "Nenhum lançamento foi efetivado; aprovar ou não é decisão exclusiva do Supervisor."})
    t = tentativa or ((tentativas or [None])[-1] if tentativas else None)
    for i, p in enumerate(pendencias, 1):
        p["id"] = f"PEN-{i:03d}"
    return {"contrato": CONTRATO, "versao": "1.0", "modo": "SIMULACAO", "ambiente": ambiente,
            "empresa": s.get("empresa"), "competencia": s.get("competencia"), "sol": sol, "estado_sol": estado,
            "tentativa": {"numero": t.get("numero"), "status": t.get("status")} if t else None,
            "gerada_em": dt.datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "status_geral": geral[0], "status_geral_texto": geral[1],
            "plano": [{"etapa": e["etapa"], "nome": NOME_ETAPA.get(e["etapa"], e["etapa"]), "situacao": e["situacao"],
                       "departamento": ic.DEPARTAMENTO_ETAPA.get(e["etapa"])} for e in plano],
            "departamentos": deps, "coordenador": {"estado": estado, "etapa": s.get("etapa"), "eventos": len(s.get("eventos") or [])},
            "supervisor": {"decisoes_necessarias": decisoes},
            "documentos": {"itens": documentos, "classificacao": classificacao, "a_conferir": acf, "total": len(documentos)},
            "conciliacao_balanco": balanco, "impostos": {"obrigacoes": impostos, "provisoes_propostas": sum(bool(i["provisao_proposta"]) for i in impostos),
                                                         "pagamentos_identificados": sum(bool(i["pagamento_identificado"]) for i in impostos),
                                                         "pendencias": sum(len(i["pendencias"]) for i in impostos)},
            "checkpoints": checkpoints, "pendencias": pendencias,
            "intercambio": {"publicacoes": {dep: sum(it["proveniencia"]["departamento"] == dep for it in ctx["itens"]) for dep in af.DEPARTAMENTOS},
                            "politica_temporal": ctx.get("politica_temporal"), "resultados_usados": ctx.get("resultados")},
            "lancamentos_efetivados": 0,
            "avisos": ["Prévia em SIMULAÇÃO: nenhum lançamento foi efetivado, aprovado ou enviado ao Domínio.",
                       "Status por departamento (sem percentual): fórmula determinística documentada em previa_fechamento.py.",
                       "Consultas entre departamentos geram CANDIDATOS; nenhuma associação é confirmada automaticamente."] + balanco["avisos"]}
