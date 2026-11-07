"""Limpeza do ambiente: ARQUIVA as demonstrações fictícias (empresas com o marcador AMOSTRA-FICTICIA.json e as SOLs delas).

Uso (a partir da raiz AGENTES-PRIME; API parada, sem processamento):
    .venv/Scripts/python.exe -I COORDENADOR-GERAL/ferramentas/arquivar_demonstracoes.py            # prévia (nada é alterado)
    .venv/Scripts/python.exe -I COORDENADOR-GERAL/ferramentas/arquivar_demonstracoes.py --executar

Regras:
- Só empresa FICTÍCIA (marcador obrigatório) e SOLs dessa empresa. Empresa real, State e pastas _ARQUIVO-* nunca são tocadas;
  nenhuma aprovação é revogada (a aprovação fica na cópia arquivada).
- Cópia de recuperação em %LOCALAPPDATA%/AgentesPrime/arquivo/LIMPEZA-<data-hora>/ com manifesto sha256; a cópia é conferida
  (re-hash) ANTES de remover qualquer original. Divergência = nada é removido.
- Registro: as SOLs arquivadas saem da lista ativa (não interferem em novas SOLs). Fica o REGISTRO MÍNIMO só dos fatos já
  exportados em TXT (identidade, valor, contas, sha do TXT) — SOLs futuras com os mesmos fatos continuam marcadas como "fatos já
  exportados" (exigem ciência). A sequência de números SOL é preservada (nunca reutilizada), inclusive a dos arquivos anteriores.
- Executado sob a trava exclusiva do registro.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coordenador as c  # noqa: E402

MARCA = "AMOSTRA-FICTICIA.json"


def runtime() -> Path:
    return Path(os.environ.get("AGENTES_PRIME_RUNTIME") or Path(os.environ.get("LOCALAPPDATA", "")) / "AgentesPrime" / "runtime")


def liberados() -> Path:
    return Path(os.environ.get("AGENTES_PRIME_LIBERADOS") or c.RAIZ / "LIBERADOS")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def numeros_conhecidos(registro: dict) -> dict:
    """Maior número SOL por ano entre o registro, os registros mínimos e os registros arquivados anteriores (controle/*.ARQUIVO-*)."""
    nomes = list(registro["solicitacoes"]) + list(registro.get("registros_minimos") or {})
    for arq in c.REGISTRO.parent.glob(c.REGISTRO.stem + ".ARQUIVO-*.json"):
        try:
            nomes += list(json.loads(arq.read_text(encoding="utf-8")).get("solicitacoes", {}))
        except (OSError, ValueError):
            pass
    maior = {str(a): int(n) for a, n in (registro.get("sequencia_sol") or {}).items()}
    for s in nomes:
        _, ano, n = s.split("-")
        maior[ano] = max(maior.get(ano, 0), int(n))
    return maior


def plano(registro: dict) -> dict:
    empresas = sorted(p.name for p in c.CLIENTES.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / MARCA).is_file())
    sols = sorted(s for s, x in registro["solicitacoes"].items() if x.get("empresa") in empresas)
    impedimentos = [f"{s} em processamento ({x['estado']})" for s, x in registro["solicitacoes"].items()
                    if s in sols and str(x.get("estado", "")).endswith("_EM_ANDAMENTO")]
    if c.ORDEM_ATIVA.exists():
        impedimentos.append("Há ordem ativa.")
    rt = runtime()
    itens = []                                    # (origem, destino relativo na cópia, remover depois?)
    itens.append((c.REGISTRO, "registro/" + c.REGISTRO.name, False))
    lixo = rt / "lixeira-solicitacoes.json"
    if lixo.is_file():
        itens.append((lixo, "runtime/lixeira-solicitacoes.json", False))
    lotes = []
    for s in sols:
        pasta = rt / "execucoes" / s
        if pasta.is_dir():
            itens.append((pasta, f"runtime/execucoes/{s}", True))
            lote = (json.loads((pasta / "execucao.json").read_text(encoding="utf-8")) if (pasta / "execucao.json").is_file() else {}).get("lote")
            if lote and (rt / "lotes" / lote).is_dir():
                lotes.append(lote)
                itens.append((rt / "lotes" / lote, f"runtime/lotes/{lote}", True))
    # rascunhos/lotes da empresa fictícia que não viraram SOL (lote.json indica a empresa)
    for p in sorted((rt / "lotes").glob("L-*")) if (rt / "lotes").is_dir() else []:
        try:
            emp_lote = json.loads((p / "lote.json").read_text(encoding="utf-8")).get("empresa")
        except (OSError, ValueError):
            continue
        if emp_lote in empresas and p.name not in lotes:
            lotes.append(p.name)
            itens.append((p, f"runtime/lotes/{p.name}", True))
    # versões anteriores da amostra (com os documentos recebidos das SOLs antigas), movidas pela preparação "recriar"
    anteriores = rt / "amostra-anterior"
    if anteriores.is_dir() and any(anteriores.iterdir()):
        itens.append((anteriores, "runtime/amostra-anterior", True))
    for e in empresas:
        itens.append((c.CLIENTES / e, f"CLIENTES/{e}", True))
        if (liberados() / e).is_dir():
            itens.append((liberados() / e, f"LIBERADOS/{e}", True))
    return {"empresas": empresas, "sols": sols, "lotes": lotes, "itens": itens, "impedimentos": impedimentos}


def copiar(itens, destino: Path) -> list:
    manifesto = []
    for origem, rel, _ in itens:
        arquivos = [origem] if origem.is_file() else sorted(p for p in origem.rglob("*") if p.is_file())
        for a in arquivos:
            alvo = destino / rel / (a.relative_to(origem) if origem.is_dir() else "")
            alvo = destino / rel if origem.is_file() else alvo
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(a, alvo)
            manifesto.append({"origem": str(a), "copia": str(alvo.relative_to(destino)).replace("\\", "/"), "sha256": sha(a),
                              "bytes": a.stat().st_size})
    return manifesto


def remover(p: Path) -> None:
    def permissao(fn, caminho, _exc):
        os.chmod(caminho, stat.S_IWRITE)
        fn(caminho)
    if p.is_dir():
        shutil.rmtree(p, onexc=permissao)
    elif p.exists():
        os.chmod(p, stat.S_IWRITE)
        p.unlink()


def executar(executar_: bool, base: Path) -> dict:
    with c.trava_registro():
        registro = c.ler_registro()
        pl = plano(registro)
        previa = {"empresas_ficticias": pl["empresas"], "sols": pl["sols"], "lotes": pl["lotes"], "impedimentos": pl["impedimentos"],
                  "itens": [{"origem": str(o), "copia": r, "remover_original": rem} for o, r, rem in pl["itens"]],
                  "sequencia_sol": numeros_conhecidos(registro)}
        if not executar_ or pl["impedimentos"] or not (pl["sols"] or pl["empresas"]):
            return dict(previa, executado=False)
        momento = c.agora()
        destino = base / f"LIMPEZA-{momento:%Y%m%d-%H%M%S}"
        destino.mkdir(parents=True, exist_ok=False)
        manifesto = copiar(pl["itens"], destino)
        divergentes = [m for m in manifesto if sha(destino / m["copia"]) != m["sha256"]]
        (destino / "MANIFESTO.json").write_text(json.dumps({"em": momento.isoformat(), "sols": pl["sols"], "empresas": pl["empresas"],
                                                            "arquivos": manifesto, "divergentes": divergentes}, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
        if divergentes:
            return dict(previa, executado=False, erro="Cópia de recuperação divergente; nada foi removido.", copia=str(destino))
        manifesto_sha = sha(destino / "MANIFESTO.json")
        minimos = registro.setdefault("registros_minimos", {})
        for s in pl["sols"]:
            x = registro["solicitacoes"].pop(s)
            exportados, exportacoes = {}, []
            for ap in x.get("aprovacoes_anteriores", []) + ([x["aprovacao"]] if x.get("aprovacao") else []):
                if ap.get("fatos_exportados"):
                    exportados.update(ap["fatos_exportados"])
                    exportacoes.append({"em": ap.get("liberacao_em"), "txt_sha256": ap.get("txt_sha256"), "linhas": ap.get("txt_linhas"),
                                        "total": ap.get("txt_total")})
            if exportados:
                minimos[s] = {"sol": s, "empresa": x.get("empresa"), "competencia": x.get("competencia"), "situacao": "ARQUIVADA_LIMPEZA",
                              "situacao_texto": f"demonstração arquivada na limpeza de {momento:%d/%m/%Y} (cópia {destino.name})",
                              "estado_final": x.get("estado"), "excluida_em": momento.isoformat(), "fatos_exportados": exportados,
                              "exportacoes": exportacoes, "justificativa": "Limpeza do ambiente: demonstração fictícia arquivada.",
                              "permanece": ["número, empresa, competência, estado final; identidades e valores dos fatos exportados; "
                                            "sha256/linhas/total dos TXT"], "remocao_pendente": []}
        seq = numeros_conhecidos(dict(registro, solicitacoes=dict(registro["solicitacoes"], **{s: {} for s in pl["sols"]})))
        registro["sequencia_sol"] = seq
        registro.setdefault("arquivamentos", []).append({"em": momento.isoformat(), "copia": str(destino), "manifesto_sha256": manifesto_sha,
                                                         "sols": pl["sols"], "empresas": pl["empresas"]})
        c.gravar_json(c.REGISTRO, registro)
        lixo = runtime() / "lixeira-solicitacoes.json"
        if lixo.is_file():
            dados = json.loads(lixo.read_text(encoding="utf-8"))
            for s in pl["sols"]:
                dados.get("itens", {}).pop(s, None)
            dados.setdefault("eventos", []).append({"acao": "arquivar_demonstracoes", "sols": pl["sols"], "em": momento.isoformat()})
            c.gravar_json(lixo, dados)
        pendentes = []
        for origem, _, rem in pl["itens"]:
            if rem:
                try:
                    remover(origem)
                except OSError as exc:
                    pendentes.append(f"{origem} ({type(exc).__name__})")
        return dict(previa, executado=True, copia=str(destino), manifesto_sha256=manifesto_sha, arquivos_copiados=len(manifesto),
                    registros_minimos=sorted(s for s in pl["sols"] if s in minimos), remocao_pendente=pendentes)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Arquiva as demonstrações fictícias com cópia de recuperação conferida.")
    p.add_argument("--executar", action="store_true")
    p.add_argument("--destino", default=str(Path(os.environ.get("LOCALAPPDATA", "")) / "AgentesPrime" / "arquivo"))
    a = p.parse_args()
    try:
        r = executar(a.executar, Path(a.destino))
    except c.TravaRegistroIndisponivel as e:
        r = {"executado": False, "erro": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("executado") or not a.executar else 1


if __name__ == "__main__":
    sys.exit(main())
