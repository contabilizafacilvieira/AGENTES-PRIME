"""Tentativas auditadas de uma SOL.

Este módulo só manipula metadados no runtime externo. Os arquivos recebidos são
referenciados por caminho e SHA; nunca são regravados nem substituídos.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def agora() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def ler(caminho: Path, padrao=None):
    if not caminho.is_file():
        return padrao
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return padrao


def gravar(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, caminho)


def _pasta(base: Path, sol: str) -> Path:
    return base / "execucoes" / sol


def listar(base: Path, sol: str) -> list[dict]:
    pasta = _pasta(base, sol) / "tentativas"
    saida = []
    for item in pasta.glob("[0-9][0-9][0-9][0-9]"):
        registro = ler(item / "tentativa.json")
        if registro:
            saida.append(registro)
    return sorted(saida, key=lambda x: int(x["numero"]))


def _codigo_atual(raiz: Path) -> tuple[str, str | None]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=raiz, capture_output=True, text=True, check=True).stdout.strip()
        tag = subprocess.run(["git", "describe", "--tags", "--exact-match", "HEAD"], cwd=raiz, capture_output=True, text=True).stdout.strip() or None
        return commit, tag
    except (OSError, subprocess.CalledProcessError):
        return "DESCONHECIDO", None


def elegibilidade(base: Path, sol: str, registro: dict, execucao: dict, *, ordem_ativa: bool = False,
                  em_execucao: bool = False, raiz: Path | None = None,
                  documentos_override: list[dict] | None = None) -> dict:
    motivos = []
    if not registro:
        motivos.append("Solicitação não encontrada.")
    if registro and registro.get("empresa_excluida"):
        motivos.append("A empresa está excluída.")
    if ordem_ativa or em_execucao:
        motivos.append("Já existe uma execução ou ordem ativa incompatível.")
    if (execucao or {}).get("status") == "EM_EXECUCAO":
        motivos.append("A execução atual ainda está em andamento.")
    lote = {"arquivos": documentos_override} if documentos_override is not None else (ler(base / "lotes" / str((execucao or {}).get("lote", "")) / "lote.json") or {})
    documentos = []
    for item in lote.get("arquivos", []):
        nome = item.get("nome_interno") or item.get("nome_original")
        caminho = Path(item.get("caminho", "")) if item.get("caminho") else None
        if caminho is None and registro:
            pasta = registro.get("pasta_documentos")
            caminho = Path(pasta) / nome if pasta else None
        if not caminho or not caminho.is_file():
            motivos.append(f"Documento ausente: {nome or 'sem nome'}.")
            continue
        atual = sha256(caminho)
        esperado = item.get("sha256")
        if esperado and atual != esperado:
            motivos.append(f"SHA-256 divergente: {nome}.")
        documentos.append({"nome": nome, "caminho": str(caminho), "sha256": atual})
    if not documentos and lote.get("arquivos"):
        motivos.append("Nenhum documento original disponível.")
    return {"elegivel": not motivos, "motivos": motivos, "documentos": documentos,
            "tentativas": listar(base, sol), "sol": sol}


def criar(base: Path, sol: str, *, origem: dict, motivo: str, solicitante: str,
          documentos: list[dict], raiz: Path | None = None) -> dict:
    if not motivo or len(motivo.strip()) < 3:
        raise ValueError("Informe o motivo do reprocessamento.")
    pasta = _pasta(base, sol) / "tentativas"
    anteriores = listar(base, sol)
    numero = (anteriores[-1]["numero"] if anteriores else 0) + 1
    commit, tag = _codigo_atual(raiz or Path.cwd())
    criada = agora()
    registro = {"numero": numero, "sol": sol, "tentativa_origem": origem.get("numero", 1),
                "criada_em": criada, "motivo": motivo.strip(), "solicitante": solicitante or "Supervisor",
                "versao_codigo": commit, "tag": tag, "documentos": documentos,
                "status": "PREPARADA", "pendencias": [], "auditoria": {"origem": "REPROCESSAMENTO_AUDITADO"},
                "ciclo_vida": CICLO_VIDA, "execucoes": [],
                "eventos": [{"em": criada, "evento": "Tentativa criada (PREPARADA)."}]}
    gravar(pasta / f"{numero:04d}" / "tentativa.json", registro)
    return registro


# ---------------------------------------------------------------- ciclo de vida (v2)
# PREPARADA → EM_EXECUCAO → CONCLUIDA | BLOQUEADA | FALHOU
#   BLOQUEADA = execução correta cujo resultado impede prosseguir (ex.: falta de extrato) — NÃO é falha técnica.
#   FALHOU    = erro técnico (exceção, etapa sem resultado, registro recusado).
# Tentativas antigas (sem "ciclo_vida") nunca são assumidas automaticamente por uma execução nova: a reconciliação delas é
# uma ação explícita, para não atribuir execuções à tentativa errada.
CICLO_VIDA = "V2"
ATIVOS = ("PREPARADA", "EM_EXECUCAO")
FINAIS = ("CONCLUIDA", "BLOQUEADA", "FALHOU")


def _arquivo(base: Path, sol: str, numero: int) -> Path:
    return _pasta(base, sol) / "tentativas" / f"{int(numero):04d}" / "tentativa.json"


def ativa(base: Path, sol: str) -> dict | None:
    """Última tentativa em estado ativo (PREPARADA ou EM_EXECUCAO); finais nunca impedem uma nova tentativa."""
    lista = listar(base, sol)
    return lista[-1] if lista and lista[-1].get("status") in ATIVOS else None


def iniciar(base: Path, sol: str) -> dict | None:
    """Início efetivo da execução: PREPARADA → EM_EXECUCAO (somente tentativas do ciclo V2). Idempotente."""
    t = ativa(base, sol)
    if not t or t.get("ciclo_vida") != CICLO_VIDA:
        return None
    if t["status"] == "PREPARADA":
        momento = agora()
        t.update(status="EM_EXECUCAO", iniciada_em=momento)
        t.setdefault("eventos", []).append({"em": momento, "evento": "Execução iniciada (EM_EXECUCAO)."})
        gravar(_arquivo(base, sol, t["numero"]), t)
    return t


def vincular_execucao(base: Path, sol: str, execucao: str) -> dict | None:
    """Vínculo EXPLÍCITO entre a tentativa em execução e a pasta de etapa criada para ela (ex.: financeiro-5)."""
    t = ativa(base, sol)
    if not t or t.get("status") != "EM_EXECUCAO" or t.get("ciclo_vida") != CICLO_VIDA:
        return None
    if execucao not in [e["execucao"] for e in t.get("execucoes", [])]:
        momento = agora()
        t.setdefault("execucoes", []).append({"execucao": execucao, "etapa": execucao.rsplit("-", 1)[0], "vinculada_em": momento})
        t.setdefault("eventos", []).append({"em": momento, "evento": f"Execução vinculada: {execucao}."})
        gravar(_arquivo(base, sol, t["numero"]), t)
    return t


def resumir_execucoes(base: Path, sol: str, execucoes: list[dict]) -> list[dict]:
    """Resumo de cada execução vinculada, referenciando o resultado imutável pelo caminho relativo e SHA-256 (sem cópia)."""
    saida = []
    for item in execucoes:
        pasta = _pasta(base, sol) / item["execucao"]
        resultado, falha = pasta / "resultado.json", pasta / "falha.json"
        r = ler(resultado, {}) or {}
        resumo = {"execucao": item["execucao"], "etapa": item.get("etapa"),
                  "resultado": f"{item['execucao']}/resultado.json" if resultado.is_file() else None,
                  "resultado_sha256": sha256(resultado) if resultado.is_file() else None,
                  "resumo": r.get("resumo"), "bloqueio_lote": r.get("bloqueio_lote") or []}
        if "fonte_auxiliar_financeira" in r:
            resumo["fonte_bancaria"] = r.get("fonte_bancaria")
            resumo["fonte_auxiliar_resumo"] = (r.get("fonte_auxiliar_financeira") or {}).get("resumo")
        if falha.is_file():
            resumo["falha"] = str((ler(falha, {}) or {}).get("motivo", "falha registrada"))[:300]
        saida.append(resumo)
    return saida


def status_final(execucoes: list[dict], plano: list[dict], erro: bool = False) -> str:
    """FALHOU (erro técnico) > BLOQUEADA (bloqueio funcional) > CONCLUIDA."""
    situacoes = {e.get("situacao") for e in plano or []}
    if erro or not execucoes or "FALHOU" in situacoes or any(e.get("falha") or not e.get("resultado") for e in execucoes):
        return "FALHOU"
    if any(e.get("bloqueio_lote") for e in execucoes) or situacoes & {"BLOQUEADA", "BLOQUEADA_POR_DEPENDENCIA"}:
        return "BLOQUEADA"
    return "CONCLUIDA"


def finalizar(base: Path, sol: str, numero: int, status: str, *, resultado: dict, estado_sol: str | None,
              erro: dict | None = None) -> dict:
    """EM_EXECUCAO → estado final. Segunda finalização não altera nada (devolve o registro com finalizacao_repetida)."""
    if status not in FINAIS:
        raise ValueError(f"Estado final inválido: {status}.")
    caminho = _arquivo(base, sol, numero)
    t = ler(caminho)
    if not t:
        raise ValueError("Tentativa não encontrada.")
    if t.get("status") in FINAIS:
        return dict(t, finalizacao_repetida=True)
    if t.get("status") != "EM_EXECUCAO":
        raise ValueError("Somente uma tentativa EM_EXECUCAO pode ser finalizada.")
    momento = agora()
    t.update(status=status, finalizada_em=momento, resultado=resultado, estado_sol_final=estado_sol)
    if erro:
        t["erro"] = erro
    t.setdefault("eventos", []).append({"em": momento, "evento": f"Tentativa finalizada ({status})."})
    gravar(caminho, t)
    return t


def comparar(tentativas: list[dict]) -> list[dict]:
    return [{"numero": x.get("numero"), "status": x.get("status"), "motivo": x.get("motivo"),
             "criada_em": x.get("criada_em"), "resultado": x.get("resultado"),
             "documentos": x.get("documentos", []), "execucoes": x.get("execucoes", []),
             "iniciada_em": x.get("iniciada_em"), "finalizada_em": x.get("finalizada_em"),
             "estado_sol_final": x.get("estado_sol_final")} for x in tentativas]
