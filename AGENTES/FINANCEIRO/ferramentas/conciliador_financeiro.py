"""Motor genérico de conciliação financeira: MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1 ↔ MOVIMENTOS_FINANCEIROS_NORMALIZADOS_V1.

Extrato → Normalizador Bancário ─┐
                                 ├→ MOTOR DE CONCILIAÇÃO → CONCILIACAO_FINANCEIRA_V1
Relatório → Normalizador Financ. ┘

- Biblioteca pura, determinística, sem banco, empresa, cliente ou mês específicos; não lê arquivos e não grava nada.
- Responde SOMENTE "este movimento bancário corresponde a este(s) movimento(s) financeiro(s)?". Não cria lançamento,
  não escolhe conta contábil, não confere documento fiscal e não aprova nada.
- Classificação por REGRAS explícitas (política abaixo). O score existe só para ordenar/explicar e é devolvido com os
  componentes; nunca decide sozinho.
- Fail-closed: só CONCILIADO libera a associação financeira; PROVAVEL, AMBIGUO e NAO_CONCILIADO ficam para o Supervisor.
  Conciliar banco × relatório NÃO é suporte documental/fiscal (`suporte_documental` é sempre False).

POLÍTICA (CONCILIACAO_FINANCEIRA_POLITICA_V1)
Elegibilidade de um par banco × auxiliar (todas obrigatórias):
  natureza compatível (CREDITO↔ENTRADA, DEBITO↔SAIDA; INDETERMINADA nunca entra), data do auxiliar = data_quitacao (senão
  `data`; nunca data_competencia nem vencimento) a no máximo JANELA_DIAS dias corridos, e valor exato (1×1) ou soma exata
  (grupos). Tolerância monetária: R$ 0,00.
Evidências fortes: DOCUMENTO_EXATO, CONTRAPARTE_DOCUMENTO (CPF/CNPJ), CONTRAPARTE_NOME_FORTE (2+ termos informativos).
Evidências fracas: CONTRAPARTE_NOME_PARCIAL, DESCRICAO_COMPATIVEL (nunca concilia sozinha).
1×1  CONCILIADO = par elegível + (data ≤ 1 dia e ≥ 1 forte, ou data = 2 dias e ≥ 2 fortes) + sem concorrente forte.
     PROVAVEL   = par elegível único sem evidência forte suficiente (exige Supervisor).
     AMBIGUO    = dois ou mais pares/grupos plausíveis disputando o mesmo movimento (nenhum é escolhido).
     NAO_CONCILIADO = nenhum par elegível.
Grupos (1×N e N×1, até LIMITE_GRUPO itens): soma exata + todos os membros elegíveis; CONCILIADO só se TODOS os membros
     têm evidência forte com o outro lado e data ≤ 1 dia; só a soma = PROVAVEL; mais de uma combinação = AMBIGUO.
     Mais de LIMITE_CANDIDATOS_GRUPO candidatos = sem força bruta: NAO_CONCILIADO com análise manual.
Conflito global: componentes conexos de pares/grupos; qualquer movimento disputado = AMBIGUO. Nada é consumido duas vezes.
"""

import datetime as dt
import hashlib
import itertools
import re
import unicodedata
from decimal import Decimal

CONTRATO = "CONCILIACAO_FINANCEIRA_V1"
VERSAO = "1.0"
POLITICA = "CONCILIACAO_FINANCEIRA_POLITICA_V1"
CONTRATO_BANCARIO = "MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1"
CONTRATO_AUXILIAR = "MOVIMENTOS_FINANCEIROS_NORMALIZADOS_V1"
JANELA_DIAS = 2
LIMITE_GRUPO = 3                    # até 3 movimentos do lado agrupado (C(12,3)=220 combinações no pior caso)
LIMITE_CANDIDATOS_GRUPO = 12        # acima disso não se tenta combinação: análise manual
TOLERANCIA = Decimal("0.00")
NATUREZA_COMPATIVEL = {"CREDITO": "ENTRADA", "DEBITO": "SAIDA"}
SITUACOES_BANCARIAS_ACEITAS = ("NORMALIZADO", "NORMALIZADO_COM_PENDENCIAS")
SITUACOES_AUXILIARES_ACEITAS = ("NORMALIZADO", "NORMALIZADO_COM_PENDENCIAS")
FORTES = ("DOCUMENTO_EXATO", "CONTRAPARTE_DOCUMENTO", "CONTRAPARTE_NOME_FORTE")
TODAS = ("VALOR_EXATO", "NATUREZA_COMPATIVEL", "DATA_EXATA", "DATA_1_DIA", "DATA_2_DIAS") + FORTES + (
    "CONTRAPARTE_NOME_PARCIAL", "DESCRICAO_COMPATIVEL")
PESOS = {"VALOR_EXATO": 40, "SOMA_EXATA": 40, "NATUREZA_COMPATIVEL": 20, "DATA_EXATA": 20, "DATA_1_DIA": 15, "DATA_2_DIAS": 10,
         "DOCUMENTO_EXATO": 15, "CONTRAPARTE_DOCUMENTO": 15, "CONTRAPARTE_NOME_FORTE": 10, "CONTRAPARTE_NOME_PARCIAL": 3,
         "DESCRICAO_COMPATIVEL": 5}
# Termos que não identificam ninguém: nunca contam como evidência.
GENERICAS = {"PIX", "TED", "DOC", "TEF", "PAGAMENTO", "PAGTO", "PGTO", "RECEBIMENTO", "RECEBIDO", "RECEBIDA", "ENVIADO", "ENVIADA",
             "TRANSFERENCIA", "TRANSF", "BOLETO", "TITULO", "TIT", "TARIFA", "CREDITO", "DEBITO", "DEPOSITO", "SAQUE", "CONTA",
             "OUTRA", "INST", "OUTROS", "VALOR", "REF", "NF", "NOTA", "FISCAL", "FORNEC", "FORNECEDOR", "CLIENTE", "COBRANCA",
             "COB", "LIQUIDACAO", "DEVOLVIDO", "DEVOLUCAO", "ESTORNO", "AVULSA", "ENVIO", "PROPRIOS"}
SUFIXOS = {"LTDA", "ME", "EPP", "EIRELI", "SA", "S", "A", "CIA", "COMPANHIA", "DE", "DA", "DO", "DAS", "DOS", "E", "EM", "PARA"}


# ---------------------------------------------------------------- normalizações seguras
def sem_acento(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().upper()


def tokens(t) -> list:
    return re.findall(r"[A-Z0-9]+", sem_acento(t))


def informativos(t) -> set:
    return {x for x in tokens(t) if len(x) >= 2 and x not in GENERICAS and x not in SUFIXOS and not x.isdigit()}


def norm_documento(t):
    """Documento/referência: só caixa, espaços e pontuação são ignorados; zeros à esquerda só em referência numérica."""
    x = re.sub(r"[^A-Z0-9]", "", sem_acento(t))
    if x.isdigit():
        x = x.lstrip("0") or "0"
    return x if len(x) >= 3 else None


def dinheiro(v) -> Decimal:
    if isinstance(v, (float, bool)) or v is None:
        raise ValueError("valor monetário ausente ou em ponto flutuante (não aceito)")
    d = v if isinstance(v, Decimal) else Decimal(str(v))
    if d != d.quantize(Decimal("0.01")):
        raise ValueError("valor com mais de duas casas")
    return d.quantize(Decimal("0.01"))


def mascarar(doc) -> str:
    d = re.sub(r"\D", "", str(doc or ""))
    return f"{d[:2]}{'*' * max(len(d) - 4, 0)}{d[-2:]}" if len(d) > 4 else "*" * len(d)


def _data(t):
    try:
        return dt.date.fromisoformat(str(t)[:10]) if t else None
    except ValueError:
        return None


# ---------------------------------------------------------------- preparação das fontes
def _preparar(fontes_bancarias, fontes_auxiliares):
    bancos, auxs, fontes, pend = [], [], {"bancarias": [], "auxiliares": []}, []
    for f in fontes_bancarias or []:
        usada = f.get("situacao") in SITUACOES_BANCARIAS_ACEITAS and f.get("contrato", CONTRATO_BANCARIO) == CONTRATO_BANCARIO
        sha = (f.get("origem") or {}).get("sha256")
        fontes["bancarias"].append({"sha256": sha, "adaptador": f.get("adaptador"), "situacao": f.get("situacao"), "usada": usada})
        if not usada:
            pend.append({"codigo": "FONTE_BANCARIA_NAO_USADA", "problema": f"Fonte bancária {f.get('situacao')}: não entra na conciliação."})
            continue
        for m in f.get("movimentos") or []:
            bancos.append({"id": m["id"], "data": _data(m["data"]), "valor": dinheiro(m["valor"]), "natureza": m["natureza"],
                           "documento": m.get("documento"), "descricao": m.get("descricao") or "", "sha256": m.get("sha256_origem") or sha})
    for f in fontes_auxiliares or []:
        usada = f.get("situacao") in SITUACOES_AUXILIARES_ACEITAS and f.get("contrato", CONTRATO_AUXILIAR) == CONTRATO_AUXILIAR
        sha = (f.get("origem") or {}).get("sha256")
        fontes["auxiliares"].append({"sha256": sha, "adaptador": f.get("adaptador"), "situacao": f.get("situacao"), "usada": usada})
        if not usada:
            pend.append({"codigo": "FONTE_AUXILIAR_NAO_USADA", "problema": f"Fonte auxiliar {f.get('situacao')}: não entra na conciliação."})
            continue
        for m in f.get("movimentos") or []:
            data, origem = (_data(m.get("data_quitacao")), "DATA_QUITACAO") if m.get("data_quitacao") else (_data(m.get("data")), "DATA")
            auxs.append({"id": m["id"], "data": data, "origem_data": origem if data else None, "valor": dinheiro(m["valor"]),
                         "natureza": m.get("natureza"), "documento": m.get("documento"), "descricao": m.get("descricao") or "",
                         "contraparte": m.get("contraparte") or {}, "sha256": m.get("sha") or sha})
    bancos.sort(key=lambda x: x["id"])
    auxs.sort(key=lambda x: x["id"])
    return bancos, auxs, fontes, pend


# ---------------------------------------------------------------- evidências de um par (sem valor)
def evidencias_par(b, a):
    """None = par inelegível (natureza incompatível, sem data ou fora da janela). Senão {criterios, delta_dias, fortes}."""
    if NATUREZA_COMPATIVEL.get(b["natureza"]) != a["natureza"] or not b["data"] or not a["data"]:
        return None
    delta = abs((b["data"] - a["data"]).days)
    if delta > JANELA_DIAS:
        return None
    crit = ["NATUREZA_COMPATIVEL", {0: "DATA_EXATA", 1: "DATA_1_DIA", 2: "DATA_2_DIAS"}[delta]]
    toks_b = set(tokens(b["descricao"]))
    docs_b = {d for d in [norm_documento(b["documento"])] + [norm_documento(t) for t in toks_b if len(t) >= 5] if d}
    doc_a = norm_documento(a["documento"])
    if doc_a and (doc_a == norm_documento(b["documento"]) or (len(doc_a) >= 5 and doc_a in docs_b)):
        crit.append("DOCUMENTO_EXATO")
    cp = a["contraparte"]
    dig = re.sub(r"\D", "", str(cp.get("documento") or ""))
    numeros_b = set(re.findall(r"\d+", f"{b['descricao']} {b['documento'] or ''}"))
    if len(dig) in (11, 14) and dig in numeros_b:
        crit.append("CONTRAPARTE_DOCUMENTO")
    inf_b = informativos(b["descricao"])
    nome = None
    for campo in ("nome", "nome_fantasia"):
        inf = informativos(cp.get(campo))
        if len(inf) >= 2 and inf <= inf_b:
            nome = "CONTRAPARTE_NOME_FORTE"
            break
        if inf & inf_b and not nome:
            nome = "CONTRAPARTE_NOME_PARCIAL"
    if nome:
        crit.append(nome)
    nomes_cp = informativos(f"{cp.get('nome') or ''} {cp.get('nome_fantasia') or ''}")
    if len((informativos(a["descricao"]) - nomes_cp) & inf_b) >= 2:
        crit.append("DESCRICAO_COMPATIVEL")
    return {"criterios": crit, "delta_dias": delta, "fortes": [c for c in crit if c in FORTES]}


def _score(criterios):
    comp = {c: PESOS[c] for c in criterios if c in PESOS}
    return {"total": sum(comp.values()), "componentes": comp,
            "observacao": "Score só ordena e explica; a classificação vem das regras da política."}


def _id_assoc(bancarios, auxiliares):
    chave = "|".join(sorted(bancarios)) + "#" + "|".join(sorted(auxiliares))
    return "CF-" + hashlib.sha256(chave.encode()).hexdigest()[:12].upper()


def _componentes(arestas):
    """Componentes conexos (union-find) sobre nós ('B', id) / ('A', id); ordem determinística."""
    pai = {}

    def raiz(x):
        pai.setdefault(x, x)
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x
    for i, nos in enumerate(arestas):
        for n in nos:
            pai[raiz(n)] = raiz(nos[0])
    grupos = {}
    for i, nos in enumerate(arestas):
        grupos.setdefault(raiz(nos[0]), []).append(i)
    return sorted(grupos.values(), key=lambda idx: min(idx))


# ---------------------------------------------------------------- motor
def conciliar(fontes_bancarias, fontes_auxiliares) -> dict:
    try:
        bancos, auxs, fontes, pend = _preparar(fontes_bancarias, fontes_auxiliares)
    except (ValueError, KeyError, TypeError) as exc:
        return {"contrato": CONTRATO, "versao": VERSAO, "politica": POLITICA, "situacao": "ENTRADA_INVALIDA",
                "associacoes": [], "pendencias": [{"codigo": "ENTRADA_INVALIDA", "problema": f"Contrato de entrada inválido ({type(exc).__name__})."}],
                "resumo": None, "bloqueantes": []}
    B = {b["id"]: b for b in bancos}
    A = {a["id"]: a for a in auxs}
    associacoes, resolvidos_b, resolvidos_a = [], set(), set()
    sem_data = [a["id"] for a in auxs if not a["data"]]
    indeterminados = [a["id"] for a in auxs if a["natureza"] not in ("ENTRADA", "SAIDA")]

    def assoc(classif, bids, aids, card, criterios=None, fortes_ok=None, candidatos=None, motivo=None, delta=None, extra=None):
        bids, aids = sorted(bids), sorted(aids)
        crit = sorted(set(criterios or []), key=lambda c: (list(PESOS).index(c) if c in PESOS else 99, c))
        return {"id": _id_assoc(bids, aids), "classificacao": classif, "cardinalidade": card, "bancarios": bids, "auxiliares": aids,
                "natureza_bancaria": B[bids[0]]["natureza"] if bids else None,
                "valor_bancario": sum((B[i]["valor"] for i in bids), Decimal("0.00")),
                "valor_auxiliar": sum((A[i]["valor"] for i in aids), Decimal("0.00")),
                "criterios_atendidos": crit, "criterios_ausentes": [c for c in TODAS if c not in crit and not c.startswith("DATA_")]
                + ([] if any(c.startswith("DATA_") for c in crit) else ["DATA_NA_JANELA"]),
                "score": _score(crit), "candidatos": candidatos or [], "motivo": motivo, "diferenca_dias_maxima": delta,
                "politica": POLITICA, "decisao": "AUTOMATICA" if classif == "CONCILIADO" else "PENDENTE_SUPERVISOR",
                "libera_associacao_financeira": classif == "CONCILIADO", "suporte_documental": False,
                "origem": {"bancaria_sha256": sorted({B[i]["sha256"] for i in bids if B[i]["sha256"]}),
                           "auxiliar_sha256": sorted({A[i]["sha256"] for i in aids if A[i]["sha256"]})}, **(extra or {})}

    # ---- 1×1: pares elegíveis com valor exato
    pares = []
    for b in bancos:
        for a in auxs:
            if b["valor"] == a["valor"] and (ev := evidencias_par(b, a)):
                forte = (ev["delta_dias"] <= 1 and ev["fortes"]) or (ev["delta_dias"] == 2 and len(ev["fortes"]) >= 2)
                pares.append({"b": b["id"], "a": a["id"], "ev": ev, "forte": bool(forte)})

    def resolver(lista, classif_unico):
        for idx in _componentes([[("B", p["b"]), ("A", p["a"])] for p in lista]):
            comp = [lista[i] for i in idx]
            bids = {p["b"] for p in comp}
            aids = {p["a"] for p in comp}
            cands = [{"bancarios": [p["b"]], "auxiliares": [p["a"]], "criterios": ["VALOR_EXATO"] + p["ev"]["criterios"],
                      "score": _score(["VALOR_EXATO"] + p["ev"]["criterios"])} for p in comp]
            cands.sort(key=lambda c: (-c["score"]["total"], c["bancarios"], c["auxiliares"]))
            if len(comp) == 1:
                p = comp[0]
                associacoes.append(assoc(classif_unico, [p["b"]], [p["a"]], "1x1", ["VALOR_EXATO"] + p["ev"]["criterios"],
                                         delta=p["ev"]["delta_dias"],
                                         motivo=None if classif_unico == "CONCILIADO" else
                                         "Valor, natureza e data compatíveis, mas sem evidência forte suficiente (documento ou contraparte)."))
            else:
                associacoes.append(assoc("AMBIGUO", bids, aids, f"{len(bids)}x{len(aids)}", candidatos=cands,
                                         motivo="Mais de um candidato plausível disputa o(s) mesmo(s) movimento(s); nenhum foi escolhido."))
            resolvidos_b.update(bids)
            resolvidos_a.update(aids)

    resolver([p for p in pares if p["forte"]], "CONCILIADO")
    resolver([p for p in pares if not p["forte"] and p["b"] not in resolvidos_b and p["a"] not in resolvidos_a], "PROVAVEL")
    # Um par fraco que envolva movimento já resolvido por par forte é descartado; o outro movimento segue para os grupos.

    # ---- grupos (1×N e N×1) entre movimentos ainda NÃO resolvidos pelas fases 1×1 (nenhum é consumido duas vezes)
    b0 = [b for b in bancos if b["id"] not in resolvidos_b]
    a0 = [a for a in auxs if a["id"] not in resolvidos_a]
    grupos, limite = [], {}
    for ancora, outros, lado in [(b, a0, "1xN") for b in b0] + [(a, b0, "Nx1") for a in a0]:
        def ev_de(o):
            return evidencias_par(ancora, o) if lado == "1xN" else evidencias_par(o, ancora)
        pool = [(o, e) for o in outros if (e := ev_de(o))]
        if len(pool) > LIMITE_CANDIDATOS_GRUPO:
            limite[("B" if lado == "1xN" else "A", ancora["id"])] = len(pool)
            continue
        for n in range(2, LIMITE_GRUPO + 1):
            for combo in itertools.combinations(pool, n):
                if sum((o["valor"] for o, _ in combo), Decimal("0.00")) == ancora["valor"]:
                    grupos.append({"lado": lado, "ancora": ancora["id"], "membros": [o["id"] for o, _ in combo],
                                   "evs": [e for _, e in combo]})
    for idx in _componentes([[("B", g["ancora"]) if g["lado"] == "1xN" else ("A", g["ancora"])] +
                             [("A", m) if g["lado"] == "1xN" else ("B", m) for m in g["membros"]] for g in grupos]):
        comp = [grupos[i] for i in idx]
        def ids(g):
            return ([g["ancora"]], g["membros"]) if g["lado"] == "1xN" else (g["membros"], [g["ancora"]])
        if len(comp) == 1:
            g = comp[0]
            bids, aids = ids(g)
            crit = ["SOMA_EXATA", "NATUREZA_COMPATIVEL"] + sorted({c for e in g["evs"] for c in e["criterios"] if c != "NATUREZA_COMPATIVEL"})
            forte = all(e["fortes"] for e in g["evs"]) and all(e["delta_dias"] <= 1 for e in g["evs"])
            associacoes.append(assoc("CONCILIADO" if forte else "PROVAVEL", bids, aids, g["lado"], crit,
                                     delta=max(e["delta_dias"] for e in g["evs"]),
                                     motivo=None if forte else "Combinação matemática exata sem evidência forte em todos os membros.",
                                     extra={"evidencias_por_membro": [{"membro": m, "criterios": e["criterios"]} for m, e in zip(g["membros"], g["evs"])]}))
            resolvidos_b.update(bids)
            resolvidos_a.update(aids)
        else:
            todos_b = sorted({x for g in comp for x in ids(g)[0]})
            todos_a = sorted({x for g in comp for x in ids(g)[1]})
            cands = [{"bancarios": ids(g)[0], "auxiliares": ids(g)[1], "cardinalidade": g["lado"],
                      "criterios": sorted({c for e in g["evs"] for c in e["criterios"]})} for g in comp]
            associacoes.append(assoc("AMBIGUO", todos_b, todos_a, "GRUPO", candidatos=cands,
                                     motivo="Mais de uma combinação de valores fecha a soma; nenhuma foi escolhida."))
            resolvidos_b.update(todos_b)
            resolvidos_a.update(todos_a)

    # ---- sem associação
    for b in bancos:
        if b["id"] not in resolvidos_b:
            lim = limite.get(("B", b["id"]))
            associacoes.append(assoc("NAO_CONCILIADO", [b["id"]], [], "1x0",
                                     motivo=(f"Agrupamento com {lim} candidatos excede o limite de {LIMITE_CANDIDATOS_GRUPO}; análise manual."
                                             if lim else "Nenhum movimento auxiliar com valor, natureza e data compatíveis."),
                                     extra={"necessita_analise_manual": bool(lim)}))
    for a in auxs:
        if a["id"] not in resolvidos_a:
            lim = limite.get(("A", a["id"]))
            motivo = ("Sem data de quitação/lançamento; não comparável." if a["id"] in sem_data else
                      "Natureza indeterminada; não comparável." if a["id"] in indeterminados else
                      f"Agrupamento com {lim} candidatos excede o limite de {LIMITE_CANDIDATOS_GRUPO}; análise manual." if lim else
                      "Nenhum movimento bancário com valor, natureza e data compatíveis.")
            associacoes.append(assoc("NAO_CONCILIADO", [], [a["id"]], "0x1", motivo=motivo, extra={"necessita_analise_manual": bool(lim)}))
    associacoes.sort(key=lambda x: (x["bancarios"][:1] or ["~"], x["auxiliares"][:1] or ["~"], x["id"]))
    situacao = ("SEM_FONTE_BANCARIA" if not bancos and not any(f["usada"] for f in fontes["bancarias"]) else
                "SEM_FONTE_AUXILIAR" if not auxs and not any(f["usada"] for f in fontes["auxiliares"]) else "EXECUTADA")
    return {"contrato": CONTRATO, "versao": VERSAO, "politica": POLITICA, "situacao": situacao,
            "parametros": {"janela_dias": JANELA_DIAS, "limite_grupo": LIMITE_GRUPO, "limite_candidatos_grupo": LIMITE_CANDIDATOS_GRUPO,
                           "tolerancia_monetaria": TOLERANCIA, "data_auxiliar": "data_quitacao, senão data (nunca competência/vencimento)"},
            "fontes": fontes, "associacoes": associacoes, "pendencias": pend,
            "resumo": _resumo(bancos, auxs, associacoes),
            "bloqueantes": sorted(i for x in associacoes if x["classificacao"] != "CONCILIADO" for i in x["bancarios"])}


def _resumo(bancos, auxs, associacoes):
    classe_b = {i: x["classificacao"] for x in associacoes for i in x["bancarios"]}
    classe_a = {i: x["classificacao"] for x in associacoes for i in x["auxiliares"]}
    contar = lambda d, c: sum(1 for v in d.values() if v == c)
    total_v = sum((b["valor"] for b in bancos), Decimal("0.00"))
    conc_v = sum((b["valor"] for b in bancos if classe_b.get(b["id"]) == "CONCILIADO"), Decimal("0.00"))
    pct = lambda p, t: (Decimal(p) * 100 / Decimal(t)).quantize(Decimal("0.01")) if t else Decimal("0.00")
    conc_q = contar(classe_b, "CONCILIADO")
    por_natureza = {}
    for nat in ("CREDITO", "DEBITO"):
        bs = [b for b in bancos if b["natureza"] == nat]
        por_natureza["ENTRADAS" if nat == "CREDITO" else "SAIDAS"] = {
            "movimentos_bancarios": len(bs), "conciliados": sum(1 for b in bs if classe_b.get(b["id"]) == "CONCILIADO"),
            "valor_bancario": sum((b["valor"] for b in bs), Decimal("0.00")),
            "valor_conciliado": sum((b["valor"] for b in bs if classe_b.get(b["id"]) == "CONCILIADO"), Decimal("0.00"))}
    ativos = [x for x in associacoes if x["classificacao"] in ("CONCILIADO", "PROVAVEL")]
    return {"movimentos_bancarios": len(bancos), "movimentos_auxiliares": len(auxs),
            "bancarios": {c.lower(): contar(classe_b, c) for c in ("CONCILIADO", "PROVAVEL", "AMBIGUO", "NAO_CONCILIADO")},
            "auxiliares": {c.lower(): contar(classe_a, c) for c in ("CONCILIADO", "PROVAVEL", "AMBIGUO", "NAO_CONCILIADO")},
            "associacoes": {c.lower(): sum(1 for x in associacoes if x["classificacao"] == c) for c in ("CONCILIADO", "PROVAVEL", "AMBIGUO", "NAO_CONCILIADO")},
            "banco_sem_associacao": contar(classe_b, "NAO_CONCILIADO"), "auxiliar_sem_associacao": contar(classe_a, "NAO_CONCILIADO"),
            "grupos_1x1": sum(1 for x in ativos if x["cardinalidade"] == "1x1"),
            "grupos_1xN": sum(1 for x in ativos if x["cardinalidade"] == "1xN"),
            "grupos_Nx1": sum(1 for x in ativos if x["cardinalidade"] == "Nx1"),
            "valor_bancario_total": total_v, "valor_bancario_conciliado": conc_v, "valor_bancario_nao_conciliado": total_v - conc_v,
            "percentual_quantidade": pct(conc_q, len(bancos)), "percentual_valor": pct(conc_v, total_v) if total_v else Decimal("0.00"),
            "por_natureza": por_natureza}


def para_json(obj):
    if isinstance(obj, Decimal):
        return f"{obj:.2f}"
    if isinstance(obj, dict):
        return {k: para_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [para_json(v) for v in obj]
    return obj
