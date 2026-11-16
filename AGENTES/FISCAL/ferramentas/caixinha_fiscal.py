"""FISCAL (rotina CAIXINHA) — etapa CAIXINHA_FISCAL → CAIXINHA_FISCAL_V1. SIMULAÇÃO, código local, sem consulta externa.

- Pagamentos efetuados no e-CAC (pagamentos_ecac.py): evidência documental das baixas tributárias; guia sem data de arrecadação
  nunca comprova pagamento; o mesmo pagamento em documentos diferentes é UM pagamento; possível pagamento em duplicidade vai à revisão.
- Relatório de Situação Fiscal (situacao_fiscal.py): conferência adicional (pendências, a vencer, exigibilidade suspensa,
  parcelamentos). Não comprova pagamento nem baixa contábil.
Outros documentos fiscais do pacote (notas, guias, apurações) não fazem parte desta rotina e ficam listados como não utilizados.

Uso: .venv/bin/python -I AGENTES/FISCAL/ferramentas/caixinha_fiscal.py --empresa <EMP> --competencia AAAA-MM --sol <SOL> --pasta <p>
     --documentos-local <manifesto> --extracao-local <extração> --saida <dir>
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import caixinha_etapa  # noqa: E402
import documentos_local as dl  # noqa: E402
import pagamentos_ecac  # noqa: E402
import situacao_fiscal  # noqa: E402

CONTRATO = "CAIXINHA_FISCAL_V1"


def processar(empresa, competencia, sol, arquivos, itens, cnpjs):
    documentos, pendencias, fichas_ecac, relatorios = [], [], [], []
    for a in arquivos:
        tipo = (itens.get(a["arquivo"]) or {}).get("tipo")
        if tipo == dl.TIPO_PAGAMENTOS_ECAC:
            f = pagamentos_ecac.ler(a, empresa, cnpjs)
            fichas_ecac.append(f)
        elif tipo == dl.TIPO_SITUACAO_FISCAL:
            f = situacao_fiscal.ler(a, empresa, cnpjs)
            relatorios.append(f)
        else:
            pendencias.append({"documento": None, "arquivo": a["arquivo"],
                               "descricao": f"Documento fiscal fora da rotina Caixinha ({tipo}); não utilizado (guia não comprova pagamento)."})
            continue
        documentos.append({k: v for k, v in f.items() if k not in ("pagamentos", "itens")})
    pag = pagamentos_ecac.consolidar(fichas_ecac)
    for d in documentos:
        pendencias += [{"documento": d["id"], "arquivo": d["arquivo"], "descricao": p} for p in d["pendencias"]]
    for p in pag["pagamentos"]:
        pendencias += [{"documento": p["documento"], "arquivo": p["origem"]["arquivo"], "pagamento": p["id"],
                        "descricao": f"Pagamento {p.get('tipo_documento')} {p.get('numero_documento') or ''} (página {p['origem']['pagina']}): {x}"}
                       for x in p["pendencias"]]
    if not fichas_ecac:
        pendencias.append({"documento": None, "arquivo": None, "descricao": "Relatório de pagamentos do e-CAC não recebido: nenhuma baixa "
                                                                           "tributária pode ser comprovada."})
    relatorio = None
    if len(relatorios) == 1:
        relatorio = relatorios[0]
    elif len(relatorios) > 1:
        emissoes = sorted((r.get("emissao") or "", i) for i, r in enumerate(relatorios))
        relatorio = relatorios[emissoes[-1][1]] if emissoes[-1][0] and emissoes[-1][0] != emissoes[-2][0] else None
        pendencias.append({"documento": None, "arquivo": None, "descricao": "Mais de um Relatório de Situação Fiscal: "
                           + ("usado o de emissão mais recente." if relatorio else "mesma data de emissão; nenhum escolhido.")})
    else:
        pendencias.append({"documento": None, "arquivo": None, "descricao": "Relatório de Situação Fiscal não recebido (conferência adicional "
                                                                           "não realizada)."})
    comprovados = [p for p in pag["pagamentos"] if p["evidencia"] == "PAGAMENTO_REGISTRADO_ECAC"]
    return {"documentos": documentos, "pagamentos": pag["pagamentos"], "repetidos_entre_documentos": pag["repetidos_entre_documentos"],
            "conflitos": pag["conflitos"], "possiveis_duplicidades": pag["possiveis_duplicidades"],
            "situacao_fiscal": None if relatorio is None else {"documento": relatorio["id"], "arquivo": relatorio["arquivo"],
                                                               "sha256": relatorio["sha256"], "emissao": relatorio["emissao"],
                                                               "itens": relatorio["itens"], "sem_pendencias_declaradas":
                                                                   relatorio["sem_pendencias_declaradas"], "aviso": relatorio.get("aviso")},
            "pendencias": pendencias,
            "limites": ["Somente pagamentos registrados no e-CAC (data de arrecadação) comprovam baixa tributária.",
                        "Situação fiscal é conferência adicional: 'sem pendências' não significa baixa contábil.",
                        "Leitores do e-CAC e da situação fiscal em homologação: conferir com o original (página indicada)."],
            "resumo": {"documentos": len(documentos), "pagamentos": len(pag["pagamentos"]), "comprovados": len(comprovados),
                       "utilizaveis": sum(p["utilizavel"] for p in pag["pagamentos"]),
                       "guias_sem_comprovacao": sum(p["evidencia"] == "GUIA_SEM_COMPROVACAO" for p in pag["pagamentos"]),
                       "possiveis_duplicidades": len(pag["possiveis_duplicidades"]), "pendencias": len(pendencias)}}


if __name__ == "__main__":
    sys.exit(caixinha_etapa.executar("FISCAL", CONTRATO, "FISCAL", processar))
