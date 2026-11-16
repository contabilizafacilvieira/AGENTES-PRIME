"""CONTABILIDADE · LEITORES (rotina CAIXINHA) — etapa CAIXINHA_CONTABIL → CAIXINHA_CONTABIL_V1. SIMULAÇÃO, código local.

Normaliza o BALANCETE (leitor do motor geral: PDF do Domínio por colunas ou tabela; adaptadores_fechamento.adapter_balancete) e o
RAZÃO (PDF do Domínio por colunas — razao_pdf_dominio — ou tabela; adaptadores_fechamento.adapter_razao) do pacote da área CONTABIL.
Não calcula nem ajusta saldos: só lê, confere a aritmética de cada linha/conta e registra pendências e proveniência (página).

Uso: .venv/bin/python -I AGENTES/CONTABILIDADE/CAIXINHA/ferramentas/leitores_contabeis.py --empresa <EMP> --competencia AAAA-MM
     --sol <SOL> --pasta <pasta> --documentos-local <manifesto> --extracao-local <extração> --saida <dir>
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import adaptadores_fechamento as af  # noqa: E402
import caixinha_comum as cc  # noqa: E402
import caixinha_etapa  # noqa: E402
import documentos_local as dl  # noqa: E402

CONTRATO = "CAIXINHA_CONTABIL_V1"


def _periodo(meta):
    p = (meta or {}).get("periodo") or {}
    return {"inicio": p.get("inicio"), "fim": p.get("fim")} if p.get("inicio") and p.get("fim") else None


def processar(empresa, competencia, sol, arquivos, itens, cnpjs):
    clientes = dl.clientes()
    documentos, pendencias, balancetes, razoes = [], [], [], []
    fim = cc.fim_competencia(competencia).isoformat()
    for a in arquivos:
        item = itens.get(a["arquivo"]) or {}
        tipo = item.get("tipo")
        if tipo not in (dl.TIPO_BALANCETE, dl.TIPO_RAZAO):
            pendencias.append({"documento": None, "arquivo": a["arquivo"], "descricao": f"Documento do Contábil fora da rotina Caixinha ({tipo}); "
                               "não utilizado nesta conciliação."})
            continue
        f = cc.ficha(a, "BALANCETE" if tipo == dl.TIPO_BALANCETE else "RAZAO", empresa)
        motivo = cc.leitura_utilizavel(a)
        if motivo and not a["arquivo"].lower().endswith(".pdf"):
            f["pendencias"].append(f"Pendência de leitura: {motivo}.")
        adapter = af.adapter_balancete if tipo == dl.TIPO_BALANCETE else af.adapter_razao
        try:
            normal, falha = adapter(dict(item, arquivo=a["arquivo"], sha256=a["sha256"]), a, clientes, empresa)
        except Exception as exc:                                   # noqa: BLE001 — leitor recusou: nada presumido
            normal, falha = None, f"leitor recusou o arquivo ({type(exc).__name__})"
        if not normal:
            f["pendencias"].append(f"Layout não lido: {falha}")
            documentos.append(f)
            continue
        f.update(reconhecimento="RECONHECIDO", leitor=normal["adapter"])
        meta = normal.get("meta") or {}
        f["cnpj"] = cc.digitos(meta.get("cnpj")) or None
        f["periodo"] = _periodo(meta)
        f["competencia"] = (f["periodo"] or {}).get("fim", "")[:7] or None
        if f["cnpj"] and not cc.cnpj_confere([f["cnpj"]], cnpjs):
            f["pendencias"].append("CNPJ do relatório não é da empresa selecionada: documento não aproveitado (isolamento entre empresas).")
            documentos.append(f)
            continue
        if not f["cnpj"]:
            f["pendencias"].append("CNPJ não identificado no cabeçalho do relatório (conferir).")
        if not f["periodo"]:
            f["pendencias"].append("Período do relatório não identificado no cabeçalho.")
        elif f["periodo"]["fim"] != fim:
            f["pendencias"].append(f"Período do relatório termina em {f['periodo']['fim']}; a competência {competencia} termina em {fim}.")
        if tipo == dl.TIPO_BALANCETE:
            contas = [{k: c.get(k) for k in ("codigo", "conta", "descricao", "saldo_inicial", "debitos", "creditos", "saldo_final", "tipo",
                                               "grupo", "confere", "problemas")} for c in normal["contas"]]
            for c in normal.get("_contas_leitor", []):
                origem = c.get("origem")
                for x in contas:
                    if x["codigo"] == c.get("codigo") and x["conta"] == c.get("classificacao"):
                        x["pagina"] = int(str(origem).replace("p.", "")) if str(origem).startswith("p.") else None
            f["dados"] = {"contas": len(contas), "linhas_que_nao_conferem": sum(1 for c in contas if c.get("confere") is False)}
            balancetes.append({"documento": f["id"], "arquivo": a["arquivo"], "sha256": a["sha256"], "periodo": f["periodo"], "contas": contas,
                               "leitor": normal["adapter"]})
        else:
            lancs = normal.get("lancamentos", [])
            contas = normal.get("contas") or []
            f["dados"] = {"lancamentos": len(lancs), "contas": len(contas), "problemas": len(normal.get("problemas") or [])}
            for x in normal.get("problemas") or []:
                f["pendencias"].append(f"Razão: {x}")
            razoes.append({"documento": f["id"], "arquivo": a["arquivo"], "sha256": a["sha256"], "periodo": f["periodo"],
                           "contas": contas, "lancamentos": lancs, "leitor": normal["adapter"]})
        documentos.append(f)
    for nome, lista in (("balancete", balancetes), ("razão", razoes)):
        if len(lista) > 1:
            pendencias.append({"documento": None, "arquivo": None, "descricao": f"Mais de um {nome} no pacote: nenhum é escolhido automaticamente."})
        if not lista:
            pendencias.append({"documento": None, "arquivo": None, "descricao": f"{nome.capitalize()} do período não recebido ou não lido."})
    for f in documentos:
        pendencias += [{"documento": f["id"], "arquivo": f["arquivo"], "descricao": p} for p in f["pendencias"]]
    unico = lambda lista: lista[0] if len(lista) == 1 else None  # noqa: E731
    return {"documentos": documentos, "balancete": unico(balancetes), "razao": unico(razoes), "pendencias": pendencias,
            "limites": ["Leitores de layout do Domínio em homologação: conferir com o relatório original (página indicada).",
                        "Saldos como informados no relatório (D/C); nada é ajustado ou presumido."],
            "resumo": {"documentos": len(documentos), "balancetes": len(balancetes), "razoes": len(razoes), "pendencias": len(pendencias)}}


if __name__ == "__main__":
    sys.exit(caixinha_etapa.executar("CONTABIL", CONTRATO, "CONTABILIDADE/LEITORES", processar))
