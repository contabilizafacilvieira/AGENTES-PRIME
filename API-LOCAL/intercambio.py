"""INTERCÂMBIO ENTRE DEPARTAMENTOS (MOTOR GERAL): PRODUTOR → CONTRATO → CAMADA DE INTERCÂMBIO → CONSUMIDOR.

Departamentos têm responsabilidades separadas, mas consultam informações ESTRUTURADAS uns dos outros. Nenhum agente vasculha
arquivos internos de outro: a camada só lê RESULTADOS REGISTRADOS pelo Coordenador (sha256 conferido com o registro) e publica
itens com PROVENIÊNCIA completa (empresa, competência, SOL, departamento de origem, documento, sha256, registro, versão, status).

Regras invioláveis (fail-closed):
- ISOLAMENTO: toda consulta é feita num CONTEXTO (empresa, SOL). Publicação de outra empresa nunca entra; se entrasse por erro de
  programação, IsolamentoViolado interrompe a consulta inteira (nada parcial é devolvido).
- COMPETÊNCIA: por padrão só a própria SOL. SOLs anteriores da MESMA empresa só com política explícita e aprovada da empresa
  (CLIENTES/<EMP>/REGRAS-INTERCAMBIO.json: {"contrato": "REGRAS_INTERCAMBIO_V1", "situacao": "APROVADA", "janela_meses": N}).
- CONSULTA GERA CANDIDATOS, nunca confirmação: valor exato é obrigatório; data/vencimento, número do documento, CNPJ, código do
  tributo e nome (apoio) são critérios registrados. Texto parecido sozinho jamais associa.
- FATO GERADOR ≠ LIQUIDAÇÃO: a obrigação (Fiscal/DP), a provisão (Contábil) e o pagamento (Financeiro) continuam fatos separados.
"""
import datetime as dt
import hashlib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

import adaptadores_fechamento as af

CONTRATO_PUBLICACAO = "PUBLICACAO_INTERCAMBIO_V1"
JANELA_DIAS = 5                     # proximidade de data registrada como critério (não decide sozinha)
CHAVES_RESULTADO = {"FISCAL": "fiscal", "DP": "dp", "FINANCEIRO": "financeiro", "BANCOS": "bancos",
                    "CONTABILIDADE_FISCAL": "contabilfiscal", "CONTABILIDADE_DP": "contabdp", "CONCILIACAO": "conciliacao"}
DEPARTAMENTO_ETAPA = {"FISCAL": "FISCAL", "DP": "DP", "FINANCEIRO": "FINANCEIRO", "BANCOS": "CONTABIL",
                      "CONTABILIDADE_FISCAL": "CONTABIL", "CONTABILIDADE_DP": "CONTABIL", "CONCILIACAO": "CONCILIACAO"}
MARCAS_TRIBUTO = ("DARF", "DAS ", "GPS", "FGTS", "ISS", "INSS", "IRRF", "PIS", "COFINS", "IMPOSTO", "TRIBUTO", "GUIA", "SIMPLES", "ICMS",
                  "CSLL", "IRPJ", "DCTF")
MARCAS_DP_TRIBUTO = ("FGTS", "INSS", "GPS")
MARCAS_FOLHA = ("SALARIO", "FOLHA", "PRO LABORE", "PROLABORE", "FERIAS", "RESCISAO", "13O", "DECIMO TERCEIRO", "ADIANTAMENTO SALARIAL")


class IsolamentoViolado(Exception):
    """Publicação ou consulta fora da empresa do contexto: a consulta inteira é interrompida."""


def norm(t) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().upper()).strip()


def dec(v):
    try:
        return None if v in (None, "") else Decimal(str(v)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def data(v):
    try:
        return dt.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---------------------------------------------------------------- resultados REGISTRADOS (hash conferido com o Coordenador)
def resultado_registrado(runtime: Path, sol: str, s: dict, etapa: str):
    """(resultado, registro) do último resultado REGISTRADO da etapa; (None, motivo) se ausente, alterado ou de outra empresa/SOL."""
    chave = CHAVES_RESULTADO[etapa]
    reg = s.get(chave) or []
    if not reg:
        return None, None
    esperado = reg[-1].get("resultado_sha256")
    pasta = Path(runtime) / "execucoes" / sol
    candidatas = sorted((p for p in pasta.glob(f"{chave}-*") if p.name.split("-")[-1].isdigit()),
                        key=lambda p: int(p.name.split("-")[-1]), reverse=True)
    for p in candidatas:
        f = p / "resultado.json"
        if f.is_file() and sha(f) == esperado:
            r = json.loads(f.read_text(encoding="utf-8"))
            if r.get("empresa") != s.get("empresa") or r.get("sol") != sol:
                return None, f"{etapa}: resultado registrado pertence a outra empresa/SOL; não usado (isolamento)."
            return r, {"execucao": p.name, "resultado_sha256": esperado, "registrado_em": reg[-1].get("em"), "versao": len(reg)}
    return None, f"{etapa}: resultado registrado não encontrado ou alterado após o registro (sha256 não confere); não usado."


def politica_temporal(clientes: Path, empresa: str) -> dict:
    """Janela de competências anteriores consultáveis — SOMENTE por política explícita e aprovada da própria empresa."""
    p = Path(clientes) / empresa / "REGRAS-INTERCAMBIO.json"
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"janela_meses": 0, "fonte": "padrão (somente a própria SOL)"}
    if (r.get("contrato"), r.get("situacao"), r.get("empresa")) != ("REGRAS_INTERCAMBIO_V1", "APROVADA", empresa):
        return {"janela_meses": 0, "fonte": "REGRAS-INTERCAMBIO.json sem aprovação válida desta empresa (ignorado)"}
    n = r.get("janela_meses")
    return {"janela_meses": n if isinstance(n, int) and 0 <= n <= 12 else 0, "fonte": "REGRAS-INTERCAMBIO.json (APROVADA)"}


def _meses(a: str, b: str) -> int:
    (ya, ma), (yb, mb) = map(int, a.split("-")), map(int, b.split("-"))
    return (ya - yb) * 12 + (ma - mb)


def sols_consultaveis(registro: dict, empresa: str, sol: str, competencia: str, politica: dict) -> list:
    """A própria SOL + SOLs da MESMA empresa dentro da janela aprovada (competências anteriores). Outra empresa: nunca."""
    sols = [sol]
    janela = politica.get("janela_meses") or 0
    if janela:
        for outra, x in sorted((registro or {}).items()):
            if outra == sol or x.get("empresa") != empresa or x.get("estado") == "CANCELADA" or not x.get("competencia"):
                continue
            if 0 < _meses(competencia, x["competencia"]) <= janela:
                sols.append(outra)
    return sols


# ---------------------------------------------------------------- publicações por departamento produtor
def conta_txt(v):
    """Conta da proposta como texto ('2131 ISS A RECOLHER'); ausente → None (nunca presumida)."""
    if isinstance(v, dict):
        return " ".join(str(x) for x in (v.get("codigo"), v.get("descricao")) if x) or None
    return None if v in (None, "") else str(v)


def _prov(empresa, competencia, sol, departamento, reg, documento=None, sha256=None, status=None):
    return {"empresa": empresa, "competencia": competencia, "sol": sol, "departamento": departamento, "documento": documento,
            "sha256": sha256, "registro": (reg or {}).get("execucao"), "resultado_sha256": (reg or {}).get("resultado_sha256"),
            "versao": (reg or {}).get("versao"), "status": status}


def publicacoes_da_sol(runtime: Path, sol: str, s: dict, normalizados: dict = None) -> dict:
    """Itens publicados pelos departamentos de UMA SOL a partir dos resultados registrados. {"itens": [...], "avisos": [...]}."""
    empresa, comp = s.get("empresa"), s.get("competencia")
    itens, avisos = [], []
    res = {}
    for etapa in CHAVES_RESULTADO:
        r, reg = resultado_registrado(runtime, sol, s, etapa)
        if r is None and reg:
            avisos.append(reg)
        res[etapa] = (r, reg)
    fis, reg_f = res["FISCAL"]
    for d in (fis or {}).get("documentos", []):
        if d.get("tipo") not in ("NFE", "NFSE") or d.get("duplicado_de"):
            continue
        papel = d.get("papel_empresa")
        sentido = "SAIDA" if papel == "PRESTADOR_EMITENTE" else "ENTRADA" if papel == "TOMADOR_DESTINATARIO" else "INDETERMINADO"
        contraparte = d.get("destinatario_cnpj") if sentido == "SAIDA" else d.get("emitente_cnpj") if sentido == "ENTRADA" else None
        itens.append({"contrato": CONTRATO_PUBLICACAO, "tipo": "DOCUMENTO_FISCAL", "subtipo": d["tipo"], "id": d["id"], "sentido": sentido,
                      "valor": d.get("valor"), "data": (d.get("emissao") or "")[:10] or None, "competencia_fato": d.get("competencia")
                      or d.get("competencia_documental"), "numero": d.get("numero"), "contraparte_cnpj": contraparte,
                      "pendencias": d.get("pendencias") or [],
                      "proveniencia": _prov(empresa, comp, sol, "FISCAL", reg_f, d.get("arquivo"), d.get("sha256"),
                                            "COM_PENDENCIAS" if d.get("pendencias") else "ESTRUTURADO")})
    dp_r, reg_d = res["DP"]
    prov = lambda dep, d: _prov(empresa, comp, sol, dep, reg_f if dep == "FISCAL" else reg_d, d.get("arquivo"), d.get("sha256"),  # noqa: E731
                                "COM_PENDENCIAS" if d.get("pendencias") else "ESTRUTURADO")
    for o in af.obrigacoes_de_resultados(fis, dp_r, prov):
        itens.append(dict(o, tipo="OBRIGACAO", contrato_item=o["contrato"], contrato=CONTRATO_PUBLICACAO, valor=o["total"],
                          data=o.get("vencimento"), competencia_fato=o.get("competencia")))
    for etapa in ("BANCOS", "CONTABILIDADE_FISCAL", "CONTABILIDADE_DP"):
        r, reg = res[etapa]
        for l in (r or {}).get("lancamentos", []):
            itens.append({"contrato": CONTRATO_PUBLICACAO, "tipo": "PROPOSTA_CONTABIL", "id": l.get("id"), "etapa": etapa,
                          "valor": l.get("valor"), "data": l.get("data"), "debito": conta_txt(l.get("debito")), "credito": conta_txt(l.get("credito")),
                          "historico": l.get("historico"), "status": l.get("status"), "pendencias": l.get("pendencias") or [],
                          "proveniencia": _prov(empresa, comp, sol, "CONTABIL", reg, None, None, l.get("status"))})
    book = ((normalizados or {}).get("BOOK") or {}).get("_lido")
    if book:
        doc = (normalizados or {}).get("BOOK_DOC") or {}
        for c in book.get("composicoes", []):
            for it in c.get("itens", []):
                if it.get("tipo"):
                    continue
                v = it.get("valor")
                if v is None and (it.get("debito") is not None or it.get("credito") is not None):
                    v = (dec(it.get("debito")) or Decimal("0")) - (dec(it.get("credito")) or Decimal("0"))
                itens.append({"contrato": CONTRATO_PUBLICACAO, "tipo": "ITEM_EM_ABERTO", "id": f"BOOK-{c['aba']}-{it.get('linha')}",
                              "conta": c["conta"].get("classificacao"), "valor": None if v is None else f"{abs(Decimal(str(v))):.2f}",
                              "data": it.get("data"), "numero": it.get("documento"), "contraparte_nome": it.get("terceiro"),
                              "historico": it.get("descricao"),
                              "proveniencia": _prov(empresa, comp, sol, "CONCILIACAO", None, doc.get("arquivo"), doc.get("sha256"), "BOOK_FONTE")})
    fin, reg_fin = res["FINANCEIRO"]
    movimentos = []
    for m in (fin or {}).get("movimentos", []):
        movimentos.append(dict(m, proveniencia=_prov(empresa, comp, sol, "FINANCEIRO", reg_fin, ", ".join(m.get("origens") or []), None,
                                                     m.get("situacao"))))
    return {"itens": itens, "movimentos": movimentos, "avisos": avisos, "resultados": {k: v[1] for k, v in res.items() if v[1]},
            "brutos": {k: v[0] for k, v in res.items()}}


def contexto(runtime: Path, clientes: Path, registro: dict, sol: str, normalizados: dict = None) -> dict:
    """Contexto de consulta de UMA SOL: publicações da própria SOL + (política aprovada) SOLs anteriores da MESMA empresa."""
    s = (registro or {}).get(sol)
    if not s:
        raise IsolamentoViolado(f"{sol} não consta no registro.")
    empresa = s["empresa"]
    pol = politica_temporal(clientes, empresa)
    base = publicacoes_da_sol(runtime, sol, s, normalizados)
    itens, avisos = list(base["itens"]), list(base["avisos"])
    for outra in sols_consultaveis(registro, empresa, sol, s["competencia"], pol)[1:]:
        extra = publicacoes_da_sol(runtime, outra, registro[outra])
        itens += extra["itens"]
        avisos += extra["avisos"]
    for it in itens + base["movimentos"]:
        if (it.get("proveniencia") or {}).get("empresa") != empresa:
            raise IsolamentoViolado(f"Publicação de outra empresa no contexto de {empresa}; consulta interrompida.")
    return {"empresa": empresa, "sol": sol, "competencia": s["competencia"], "politica_temporal": pol, "itens": itens,
            "movimentos": base["movimentos"], "avisos": avisos, "resultados": base["resultados"], "brutos": base["brutos"]}


def consultar(ctx: dict, consumidor: str, produtores=None, tipos=None) -> list:
    """Consulta estruturada de um consumidor (ex.: FINANCEIRO) aos produtores. O próprio contexto já é de UMA empresa."""
    if consumidor not in af.DEPARTAMENTOS:
        raise ValueError(f"Departamento consumidor desconhecido: {consumidor}")
    saida = []
    for it in ctx["itens"]:
        p = it["proveniencia"]
        if p["empresa"] != ctx["empresa"]:
            raise IsolamentoViolado("Publicação de outra empresa na consulta; interrompida.")
        if (produtores and p["departamento"] not in produtores) or (tipos and it["tipo"] not in tipos):
            continue
        saida.append(it)
    return saida


# ---------------------------------------------------------------- candidatos para um movimento bancário (nunca confirmação)
def _texto_mov(m: dict) -> str:
    return norm(" ".join([m.get("descricao") or "", *[str(v) for v in (m.get("identificadores") or {}).values()]]))


def candidatos(m: dict, itens: list) -> list:
    """Candidatos de outras áreas para UM movimento. Valor EXATO obrigatório; demais critérios registrados. Situação sempre CANDIDATO."""
    valor = dec(m.get("valor"))
    if valor is None:
        return []
    txt = _texto_mov(m)
    dm = data(m.get("data"))
    saida = []
    for it in itens:
        if dec(it.get("valor")) != valor:
            continue
        if it["tipo"] == "PROPOSTA_CONTABIL":
            continue                                   # proposta não é fato a liquidar; a provisão é consultada via obrigação
        if m.get("direcao") == "CREDITO" and it["tipo"] == "OBRIGACAO":
            continue
        if m.get("direcao") == "CREDITO" and it.get("sentido") == "ENTRADA":
            continue
        if m.get("direcao") == "DEBITO" and it.get("sentido") == "SAIDA":
            continue
        criterios = ["VALOR_EXATO"]
        di = data(it.get("data"))
        if dm and di and abs((dm - di).days) <= JANELA_DIAS:
            criterios.append(f"DATA_PROXIMA({abs((dm - di).days)}d)")
        numero = norm(it.get("numero"))
        if numero and len(numero) >= 3 and re.search(r"(?<![A-Z0-9])" + re.escape(numero) + r"(?![A-Z0-9])", txt):
            criterios.append("NUMERO_DOCUMENTO")
        cnpj = re.sub(r"\D", "", str(it.get("contraparte_cnpj") or it.get("cnpj") or ""))
        if len(cnpj) == 14 and cnpj in re.findall(r"\d{14}", re.sub(r"(?<=\d)[./-](?=\d)", "", txt)):
            criterios.append("CNPJ")
        if it.get("codigo") and re.search(r"\b" + re.escape(str(it["codigo"])) + r"\b", txt):
            criterios.append("CODIGO_TRIBUTO")
        if it.get("tributo") and norm(it["tributo"]).split(" ")[0] in txt:
            criterios.append("NOME_TRIBUTO(apoio)")
        if it.get("competencia_fato") and re.sub(r"(\d{4})-(\d{2})", r"\2/\1", str(it["competencia_fato"])) in txt:
            criterios.append("COMPETENCIA")
        nome = [w for w in norm(it.get("contraparte_nome")).split() if len(w) >= 4]
        if nome and sum(w in txt for w in nome) >= 2:
            criterios.append("NOME_CONTRAPARTE(apoio)")
        fortes = [c for c in criterios if c not in ("VALOR_EXATO",) and "(apoio)" not in c]
        saida.append({"item": it["id"], "tipo": it["tipo"], "departamento": it["proveniencia"]["departamento"],
                      "descricao": _descr(it), "valor": it.get("valor"), "criterios": criterios,
                      "forca": "CANDIDATO_COM_EVIDENCIA" if fortes else "CANDIDATO_SO_VALOR",
                      "situacao": "CANDIDATO", "proveniencia": it["proveniencia"]})
    return sorted(saida, key=lambda c: (-len(c["criterios"]), c["item"]))


def _descr(it: dict) -> str:
    if it["tipo"] == "OBRIGACAO":
        return f"{it.get('tributo') or 'código ' + str(it.get('codigo') or '?')} · competência {it.get('competencia') or '?'} · {it.get('total') or '?'}"
    if it["tipo"] == "DOCUMENTO_FISCAL":
        return f"{it.get('subtipo')} {it.get('numero') or '?'} ({it.get('sentido', '').lower()}) · {it.get('valor') or '?'}"
    if it["tipo"] == "ITEM_EM_ABERTO":
        return f"Item do book conta {it.get('conta')} · {it.get('numero') or ''} {it.get('contraparte_nome') or ''}".strip()
    return it.get("historico") or it["tipo"]


ASSOCIADO = ("CONCILIADO",)


def movimento_resolvido(m: dict, liberados=()) -> bool:
    """Movimento com suporte/associação confirmada (motor CONCILIADO, decisão do Supervisor — registrada no resultado ou VIGENTE na
    Central (liberados) — ou suporte independente)."""
    if (m.get("rastreio_bancario") or {}).get("id") in set(liberados or ()):
        return True
    cf = m.get("conciliacao_financeira") or {}
    dec_sup = (cf.get("decisao_supervisor") or {}).get("estado_operacional") or ""
    return (m.get("situacao") in ("COM_SUPORTE", "TRANSFERENCIA_PROPRIA") or cf.get("classificacao") in ASSOCIADO
            or "CONFIRMADA" in dec_sup)


def analisar_financeiro(ctx: dict, liberados=()) -> dict:
    """Para cada movimento do Financeiro: candidatos de Fiscal/DP/Contábil/Conciliação e pendências cruzadas para o departamento
    RESPONSÁVEL (não para quem detectou). Pagamentos identificados de obrigações = obrigação com candidato COM evidência."""
    itens = consultar(ctx, "FINANCEIRO", produtores=("FISCAL", "DP", "CONTABIL", "CONCILIACAO"))
    por_mov, cruzadas = [], []
    pagas = {}
    for m in ctx["movimentos"]:
        cands = candidatos(m, itens)
        for c in cands:
            if c["tipo"] == "OBRIGACAO" and c["forca"] == "CANDIDATO_COM_EVIDENCIA":
                pagas.setdefault(c["item"], []).append(m["id"])
        por_mov.append({"movimento": m["id"], "data": m.get("data"), "valor": m.get("valor"), "direcao": m.get("direcao"),
                        "descricao": m.get("descricao"), "resolvido": movimento_resolvido(m, liberados), "candidatos": cands[:5]})
        if movimento_resolvido(m, liberados) or m.get("direcao") != "DEBITO":
            continue
        t = _texto_mov(m) + " "
        obrig = [c for c in cands if c["tipo"] == "OBRIGACAO"]
        if any(x in t for x in MARCAS_FOLHA) and not obrig:
            cruzadas.append(_pend_cruzada(ctx, m, "DP", "Pagamento possivelmente de folha sem obrigação correspondente publicada pelo DP",
                                          "Enviar ao DP a folha/obrigação da competência (ou confirmar a natureza do pagamento)."))
        elif any(x in t for x in MARCAS_TRIBUTO) and not obrig:
            dep = "DP" if any(x in t for x in MARCAS_DP_TRIBUTO) else "FISCAL"
            cruzadas.append(_pend_cruzada(ctx, m, dep, "Pagamento possivelmente tributário sem obrigação correspondente publicada",
                                          f"Enviar ao {af.NOME_DEPARTAMENTO[dep]} a guia/apuração/memória do tributo (ou confirmar a natureza)."))
    return {"movimentos": por_mov, "pendencias_cruzadas": cruzadas, "obrigacoes_com_pagamento": pagas}


def _pend_cruzada(ctx, m, dep, problema, oque):
    return {"classificacao": "ATENCAO", "departamento": dep, "responsavel_esperado": dep, "origem": "FINANCEIRO (intercâmbio)",
            "problema": f"{problema}: {m.get('data')} · {m.get('descricao')} · R$ {m.get('valor')}.",
            "impacto": "O pagamento não pode ser relacionado a uma obrigação; a proposta contábil da liquidação fica incompleta.",
            "o_que_fazer": oque + " A indicação veio do histórico bancário: é só um indício, não uma associação.",
            "evidencia": {"movimento": m.get("id"), **(m.get("proveniencia") or {})},
            "empresa": ctx["empresa"], "competencia": ctx["competencia"]}
