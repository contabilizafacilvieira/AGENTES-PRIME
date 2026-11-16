"""Execução comum das ETAPAS DE LEITURA da Conciliação Caixinha (Contábil/leitores, Fiscal, DP). MOTOR GERAL; sem regra de empresa.

Cada etapa: recebe o pacote de Documentos da SUA área (receber_pacote_local com hash da extração, originais e inventário conferidos;
pacote sem a área é recusado), lê os documentos do tipo que lhe cabe e grava <saida>/resultado.json (contrato da etapa, modo
SIMULACAO). Códigos: 0 = resultado gravado (pode conter pendências); 1 = pacote recusado/erro de leitura; 2 = parâmetros inválidos.
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "AGENTES" / "FINANCEIRO" / "ferramentas"))
from conferencia_financeira import cadastro, receber_pacote_local  # noqa: E402


def tipos_do_manifesto(manifesto: str) -> dict:
    d = json.loads(Path(manifesto).read_text(encoding="utf-8"))
    return {i["arquivo"]: i for i in d.get("itens", [])}


def executar(area: str, contrato: str, agente: str, processar, argv=None) -> int:
    """processar(empresa, competencia, sol, arquivos, itens_manifesto, cnpjs) → dict com documentos/pendencias/resumo (+ campos)."""
    p = argparse.ArgumentParser(description=f"{agente} — Conciliação Caixinha (SIMULACAO).")
    for a in ("empresa", "competencia", "sol", "pasta", "documentos-local", "extracao-local", "saida"):
        p.add_argument("--" + a, required=True)
    a = p.parse_args(argv)
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", a.empresa) or not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", a.competencia):
        print("ERRO: empresa ou competência (AAAA-MM) inválida.", file=sys.stderr)
        return 2
    try:
        arquivos, _ = receber_pacote_local(a.empresa, a.competencia, a.sol, a.pasta, a.documentos_local, a.extracao_local,
                                           area=area, exigir_hash=True)
        itens = tipos_do_manifesto(a.documentos_local)
        corpo = processar(a.empresa, a.competencia, a.sol, arquivos, itens, cadastro(a.empresa)["cnpjs"])
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print(f"ERRO: pacote de {agente} recusado: {e}", file=sys.stderr)
        return 1
    r = {"contrato": contrato, "agente": agente, "empresa": a.empresa, "competencia": a.competencia, "sol": a.sol, "modo": "SIMULACAO",
         "fluxo": "CONCILIACAO_CAIXINHA", "executado_em": dt.datetime.now().astimezone().isoformat(timespec="seconds"), **corpo}
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "resultado.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0
