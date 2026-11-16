"""Detecção de padrões históricos sem promoção automática a regra."""
from collections import defaultdict
import re

CONTRATO = "APRENDIZADO_CONTABIL_EMPRESA_V1"


def _chave(texto):
    return re.sub(r"\s+", " ", str(texto or "").strip().upper())


def sugerir(lancamentos, *, empresa):
    grupos = defaultdict(list)
    for l in lancamentos or []:
        deb, cre = l.get("debito_conta") or l.get("conta_debito"), l.get("credito_conta") or l.get("conta_credito")
        if not deb or not cre:
            continue
        padrao = _chave(l.get("tipo_operacao") or l.get("historico"))
        grupos[(str(deb), str(cre), padrao)].append(l)
    saida = []
    for n, ((deb, cre, padrao), xs) in enumerate(sorted(grupos.items()), 1):
        comps = sorted({str(x.get("competencia")) for x in xs if x.get("competencia")})
        confianca = "ALTA" if len(xs) >= 3 and len(comps) >= 2 else ("MEDIA" if len(xs) >= 2 else "BAIXA")
        saida.append({"empresa": empresa, "id": f"HIST-{n:04d}", "padrao_observado": padrao,
                      "tipo_operacao": xs[0].get("tipo_operacao"), "condicao": padrao,
                      "conta_debito_sugerida": deb, "conta_credito_sugerida": cre,
                      "historico_sugerido": xs[0].get("historico"), "ocorrencias": len(xs),
                      "competencias_observadas": comps, "evidencias": [x.get("proveniencia") for x in xs],
                      "confianca": confianca, "risco": "Histórico sugere padrão; não comprova regra.",
                      "status": "AGUARDANDO_SUPERVISOR", "precisa_supervisor": True})
    return {"contrato": CONTRATO, "versao": "1.0", "empresa": empresa,
            "sugestoes": saida, "regra_registrada": False}
