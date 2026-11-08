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
    registro = {"numero": numero, "sol": sol, "tentativa_origem": origem.get("numero", 1),
                "criada_em": agora(), "motivo": motivo.strip(), "solicitante": solicitante or "Supervisor",
                "versao_codigo": commit, "tag": tag, "documentos": documentos,
                "status": "PREPARADA", "pendencias": [], "auditoria": {"origem": "REPROCESSAMENTO_AUDITADO"}}
    gravar(pasta / f"{numero:04d}" / "tentativa.json", registro)
    return registro


def comparar(tentativas: list[dict]) -> list[dict]:
    return [{"numero": x.get("numero"), "status": x.get("status"), "motivo": x.get("motivo"),
             "criada_em": x.get("criada_em"), "resultado": x.get("resultado"),
             "documentos": x.get("documentos", [])} for x in tentativas]
