"""Estado contextual do DP, sem persistência."""

CONTRATO = "STATUS_DP_CONTEXTUAL_V1"


def nao_aplicavel(empresa, competencia, *, justificativa, origem="SUPERVISOR"):
    if not justificativa or origem != "SUPERVISOR":
        raise ValueError("NAO_APLICAVEL exige justificativa e origem SUPERVISOR")
    return {"contrato": CONTRATO, "empresa": empresa, "competencia": competencia,
            "departamento": "DP", "status": "NAO_APLICAVEL", "motivo": justificativa,
            "origem": origem, "pendencias": []}


def conflito(estado, evidencias):
    if (estado or {}).get("status") == "NAO_APLICAVEL" and evidencias:
        return {"codigo": "DP_NAO_APLICAVEL_CONTRADITORIO", "status": "AGUARDANDO_SUPERVISOR",
                "mensagem": "DP marcado como não aplicável, mas há evidência de movimentação de DP.",
                "evidencias": list(evidencias)}
    return None
