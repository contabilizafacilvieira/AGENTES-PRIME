"""Contrato puro da base de abertura contábil.

Não lê nem grava runtime. Recebe somente resultados já normalizados pelos
leitores e preserva saldos e pendências sem tentar corrigir divergências.
"""
from decimal import Decimal, InvalidOperation

CONTRATO = "BASE_ABERTURA_CONTABIL_V1"
STATUS = ("COMPOSICAO_CONFERIDA", "SEM_COMPOSICAO", "COMPOSICAO_SEM_CONTA", "DIVERGENTE", "AGUARDANDO_SUPERVISOR")


def _dec(v):
    try:
        return Decimal(str(v)) if v is not None else None
    except (InvalidOperation, ValueError):
        return None


def construir(balancete, confronto, *, empresa, competencia_base, data_base,
              proveniencia=None):
    """Monta a abertura a partir do saldo oficial e do confronto do book."""
    balancete = balancete or {}
    confronto = confronto or {}
    por_conta = {}
    for c in balancete.get("contas") or []:
        if c.get("tipo") == "SINTETICA":
            continue
        conta = c.get("classificacao") or c.get("conta")
        if conta:
            por_conta[str(conta)] = c
    composicoes = {}
    for c in confronto.get("composicoes") or []:
        ident = c.get("identificador") or {}
        conta = (c.get("conta") or {}).get("classificacao") or ident.get("classificacao")
        composicoes[str(conta)] = c if conta else c
    itens = []
    for conta, c in por_conta.items():
        comp = composicoes.get(conta)
        saldo = c.get("saldo_atual") or c.get("saldo_final")
        if not comp:
            status = "SEM_COMPOSICAO"
            diferenca = None
            pend = ["Saldo contábil sem composição correspondente no book."]
            saldo_comp = None
        else:
            saldo_comp = comp.get("saldo_composicao")
            diferenca = comp.get("diferenca")
            if diferenca is None and _dec(saldo) is not None and _dec(saldo_comp) is not None:
                diferenca = f"{(_dec(saldo) - _dec(saldo_comp)):.2f}"
            status = "COMPOSICAO_CONFERIDA" if _dec(diferenca) == 0 else "DIVERGENTE"
            pend = [] if status == "COMPOSICAO_CONFERIDA" else ["Saldo do book diverge do saldo do balancete."]
        itens.append({"empresa": empresa, "competencia_base": competencia_base, "data_base": data_base,
                      "conta": conta, "descricao": c.get("descricao"), "saldo_contabil": saldo,
                      "composicao_conhecida": bool(comp), "saldo_composicao": saldo_comp,
                      "diferenca": diferenca, "status_composicao": status, "pendencias": pend,
                      "proveniencia": proveniencia or {}})
    for conta, comp in composicoes.items():
        if conta in por_conta or conta == "None":
            continue
        itens.append({"empresa": empresa, "competencia_base": competencia_base, "data_base": data_base,
                      "conta": conta, "descricao": (comp.get("conta") or {}).get("descricao"),
                      "saldo_contabil": None, "composicao_conhecida": True,
                      "saldo_composicao": comp.get("saldo_composicao"), "diferenca": None,
                      "status_composicao": "COMPOSICAO_SEM_CONTA",
                      "pendencias": ["Composição do book sem conta correspondente no balancete."],
                      "proveniencia": proveniencia or {}})
    counts = {s: sum(x["status_composicao"] == s for x in itens) for s in STATUS}
    return {"contrato": CONTRATO, "versao": "1.0", "empresa": empresa,
            "competencia_base": competencia_base, "data_base": data_base,
            "itens": itens, "resumo": counts,
            "pendencias": [x for x in itens if x["pendencias"]]}
