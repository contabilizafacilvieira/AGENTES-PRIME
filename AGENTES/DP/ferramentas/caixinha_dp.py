"""DP (rotina CAIXINHA) — etapa CAIXINHA_DP → CAIXINHA_DP_V1. SIMULAÇÃO, código local.

Lê o RESUMO MENSAL DA FOLHA emitido pelo Domínio (resumo_folha_dominio.py): pró-labore bruto, INSS, IRRF, outros descontos e
líquido (proventos − descontos = líquido, igualdade exata). Identifica a ÚLTIMA competência da folha recebida e o seu líquido de
pró-labore, que a política Caixinha mantém em aberto. Não calcula folha nem encargo; não registra liquidação.

Uso: .venv/bin/python -I AGENTES/DP/ferramentas/caixinha_dp.py --empresa <EMP> --competencia AAAA-MM --sol <SOL> --pasta <p>
     --documentos-local <manifesto> --extracao-local <extração> --saida <dir>
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import caixinha_etapa  # noqa: E402
import documentos_local as dl  # noqa: E402
import resumo_folha_dominio as rfd  # noqa: E402

CONTRATO = "CAIXINHA_DP_V1"


def processar(empresa, competencia, sol, arquivos, itens, cnpjs):
    documentos, pendencias, resumos = [], [], []
    for a in arquivos:
        tipo = (itens.get(a["arquivo"]) or {}).get("tipo")
        if tipo != dl.TIPO_RESUMO_FOLHA_DOMINIO:
            pendencias.append({"documento": None, "arquivo": a["arquivo"],
                               "descricao": f"Documento de pessoal fora da rotina Caixinha ({tipo}); não utilizado nesta conciliação."})
            continue
        f = rfd.ler(a, empresa, cnpjs)
        documentos.append({k: v for k, v in f.items() if k not in ("rubricas",)} | {"rubricas": f["rubricas"]})
        if f["pro_labore"] and not f["pendencias"]:
            resumos.append({"documento": f["id"], "arquivo": f["arquivo"], "sha256": f["sha256"], "competencia": f["competencia"],
                            **f["pro_labore"]})
    for d in documentos:
        pendencias += [{"documento": d["id"], "arquivo": d["arquivo"], "descricao": p} for p in d["pendencias"]]
    por_comp = {}
    for r in resumos:
        por_comp.setdefault(r["competencia"], []).append(r)
    ultimo = None
    for comp, rs in por_comp.items():
        if len({(r["bruto"], r["liquido"]) for r in rs}) > 1:
            pendencias.append({"documento": None, "arquivo": None, "descricao": f"Mais de um resumo da competência {comp} com valores "
                               "diferentes: nenhum é escolhido."})
            por_comp[comp] = []
    validas = sorted(c for c, rs in por_comp.items() if rs)
    if validas:
        c = validas[-1]
        ultimo = dict(por_comp[c][0], competencia=c, documentos=[r["documento"] for r in por_comp[c]])
        if c != competencia:
            pendencias.append({"documento": None, "arquivo": None,
                               "descricao": f"Última competência da folha recebida ({c}) ≠ competência em análise ({competencia}): conferir."})
    elif not documentos:
        pendencias.append({"documento": None, "arquivo": None, "descricao": "Resumo mensal da folha (Domínio) não recebido: último líquido "
                                                                           "do pró-labore não identificado."})
    return {"documentos": documentos, "resumos": [dict(r) for r in resumos], "ultimo": ultimo, "pendencias": pendencias,
            "limites": ["Leitor do resumo mensal do Domínio em homologação: conferir com o original (página indicada).",
                        "Retenções (INSS/IRRF) do resumo são informativas: a Conciliação confere no razão e não as desconta de novo."],
            "resumo": {"documentos": len(documentos), "resumos_validos": len(resumos), "ultima_competencia": (ultimo or {}).get("competencia"),
                       "ultimo_liquido": (ultimo or {}).get("liquido"), "pendencias": len(pendencias)}}


if __name__ == "__main__":
    sys.exit(caixinha_etapa.executar("DP", CONTRATO, "DP", processar))
