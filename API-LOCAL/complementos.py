"""DOCUMENTO COMPLEMENTAR de uma SOL existente (genérico: extrato recebido depois, nota, comprovante, guia, relatório...).

Princípios:
- O lote ORIGINAL, seus arquivos e o manifesto histórico nunca são alterados. Cada complemento é um LOTE COMPLEMENTAR próprio
  (mesmo upload seguro: staging, formato, assinatura, tamanho, SHA conferido, sem sobrescrita), guardado em
  CLIENTES/<EMPRESA>/RECEBIDOS/<AAAA-MM>/<LOTE>/ (somente leitura) e ligado à SOL por um registro auditável no runtime:
  <runtime>/execucoes/<SOL>/complementos/<LOTE>/complemento.json (+ o pacote de Documentos daquele lote).
- Documentos classifica o complemento como qualquer documento (estrutura do conteúdo; o nome do arquivo não decide).
- Receber um complemento NÃO reprocessa, NÃO executa área nenhuma e NÃO muda resultado anterior.
- Uma tentativa nova congela o MANIFESTO EFETIVO (original + complementares concluídos até aquele instante) e recebe um PACOTE
  EFETIVO próprio (tentativas/NNNN/pacote/). Complemento recebido depois só entra numa próxima tentativa.
"""
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

import documentos_local

CONTRATO = "DOCUMENTO_COMPLEMENTAR_V1"
RE_LOTE = re.compile(r"L-\d{8}-\d{6}-[0-9a-f]{6}")
MENSAGEM_RECEBIDO = ("Documento complementar recebido. Para utilizá-lo no fechamento, crie uma nova tentativa de reprocessamento. "
                     "Nada foi reprocessado e nenhum resultado anterior mudou.")
DUPLICIDADE = {
    "MESMA_SOL": "Este arquivo (mesmo conteúdo) já faz parte desta solicitação; não foi adicionado de novo.",
    "MESMA_EMPRESA_COMPETENCIA": "Conteúdo idêntico já recebido para esta empresa e competência em outra solicitação; será ligado também a esta.",
    "LOTE_ANTERIOR": "Conteúdo idêntico já recebido pela empresa em lote anterior (outra competência); será ligado a esta solicitação.",
    "NOVO": "Documento novo."}


def agora() -> str:
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def sha256_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def gravar_atomico(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=caminho.name + ".", suffix=".tmp", dir=caminho.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(dados, ensure_ascii=False, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, caminho)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ler(caminho: Path):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8")) if Path(caminho).is_file() else None
    except (OSError, ValueError):
        return None


def pasta_complementos(runtime: Path, sol: str) -> Path:
    return Path(runtime) / "execucoes" / sol / "complementos"


# ---------------------------------------------------------------- inventário e duplicidade (SHA prevalece sobre nome)
def concluidos(runtime: Path, sol: str) -> list:
    """Complementos CONCLUÍDOS da SOL, em ordem de inclusão. Registro ilegível → erro (fail-closed)."""
    out = []
    for p in sorted(pasta_complementos(runtime, sol).glob("L-*/complemento.json")):
        c = ler(p)
        if not c or c.get("contrato") != CONTRATO or c.get("sol") != sol:
            raise ValueError(f"Registro de complemento ilegível ou de outra solicitação: {p.parent.name}.")
        out.append(c)
    return sorted(out, key=lambda c: (c["concluido_em"], c["lote"]))


def documentos_da_sol(runtime: Path, sol: str, lote_original: dict) -> dict:
    """sha256 → origem, para TODOS os documentos já ligados à SOL (lote original + complementos concluídos)."""
    docs = {a["sha256"]: {"lote": lote_original["lote"], "origem": "ORIGINAL"} for a in lote_original.get("arquivos", [])}
    for c in concluidos(runtime, sol):
        for d in c["documentos"]:
            docs.setdefault(d["sha256"], {"lote": c["lote"], "origem": "COMPLEMENTAR"})
    return docs


def classificar_duplicidade(runtime: Path, sol: str, empresa: str, competencia: str, sha: str, lote_original: dict, lote_atual: str) -> dict:
    """A) MESMA_SOL  B) MESMA_EMPRESA_COMPETENCIA  C) LOTE_ANTERIOR  D) NOVO — sempre pelo SHA-256, nunca pelo nome."""
    na_sol = documentos_da_sol(runtime, sol, lote_original).get(sha)
    if na_sol:
        return {"categoria": "MESMA_SOL", "explicacao": DUPLICIDADE["MESMA_SOL"], **na_sol}
    achado = None
    for outro in (Path(runtime) / "lotes").glob("L-*/lote.json"):
        o = ler(outro)
        if not o or o.get("lote") == lote_atual or o.get("empresa") != empresa or o.get("estado") not in ("INICIADO", "CONCLUIDO"):
            continue
        if any(a.get("sha256") == sha for a in o.get("arquivos", [])):
            cat = "MESMA_EMPRESA_COMPETENCIA" if o.get("competencia") == competencia else "LOTE_ANTERIOR"
            if achado is None or cat == "MESMA_EMPRESA_COMPETENCIA":
                achado = {"categoria": cat, "explicacao": DUPLICIDADE[cat], "lote": o["lote"], "sol": o.get("sol") or o.get("sol_destino")}
    return achado or {"categoria": "NOVO", "explicacao": DUPLICIDADE["NOVO"]}


# ---------------------------------------------------------------- triagem por Documentos (mesmo código do lote original)
def triagem(empresa: str, sol: str, competencia: str, pasta_relativa: str, saida: Path) -> dict:
    """Roda o MESMO executor local de Documentos sobre a pasta do lote complementar (extrator homologado + classificação +
    encaminhamento). Grava documentos-local.json/extracao-local.json do complemento em `saida`."""
    ordem = (f"- Empresa: {empresa}\n- SOL: {sol}\n- Competência: {competencia}\n"
             f"- Pasta dos documentos (relativa à pasta da empresa): {pasta_relativa}\n")
    documentos_local.executar(ordem, saida)
    return json.loads((Path(saida) / "documentos-local.json").read_text(encoding="utf-8"))


def registrar_complemento(runtime: Path, *, sol: str, registro: dict, lote: dict, lote_original: dict, motivo: str, responsavel: str,
                          pasta_relativa: str, manifesto: dict, duplicidades: dict) -> dict:
    """complemento.json: rastreabilidade completa (SOL, empresa, competência, lote, arquivos, SHA, classificação, motivo...)."""
    pasta = pasta_complementos(runtime, sol) / lote["lote"]
    por_arquivo = {i["arquivo"]: i for i in manifesto["itens"]}
    documentos = []
    for a in lote["arquivos"]:
        rel = f"{pasta_relativa}/{a['nome_interno']}"
        item = por_arquivo.get(rel) or {}
        documentos.append({"arquivo": rel, "nome_original": a["nome_original"], "sha256": a["sha256"], "tamanho": a["tamanho"],
                           "tipo": item.get("tipo"), "area": (item.get("encaminhamento") or {}).get("area"),
                           "situacao": (item.get("encaminhamento") or {}).get("situacao"),
                           "conteudo_utilizavel": item.get("conteudo_utilizavel"), "duplicidade": duplicidades.get(a["sha256"])})
    c = {"contrato": CONTRATO, "sol": sol, "empresa": registro["empresa"], "competencia": registro["competencia"], "lote": lote["lote"],
         "lote_original": lote_original["lote"], "pasta": pasta_relativa, "motivo": motivo, "responsavel": responsavel,
         "recebido_em": lote.get("criado_em"), "concluido_em": agora(), "documentos": documentos,
         "documentos_local_sha256": sha256_arquivo(pasta / "documentos-local.json"),
         "extracao_sha256": manifesto.get("extracao_sha256"), "classificador": "documentos_local (Documentos — execução local)",
         "efeitos": {"reprocessamento": False, "areas_executadas": [], "lancamentos": 0}}
    gravar_atomico(pasta / "complemento.json", c)
    return c


# ---------------------------------------------------------------- manifesto efetivo e pacote da tentativa
def manifesto_efetivo(runtime: Path, sol: str, numero: int, lote_original: dict, pasta_original: str) -> dict:
    """Snapshot do que a tentativa `numero` pode usar: lote original + complementos concluídos ATÉ AGORA."""
    docs = [{"arquivo": f"{pasta_original}/{a['nome_interno']}", "sha256": a["sha256"], "lote": lote_original["lote"],
             "origem": "ORIGINAL", "incluido_em": lote_original.get("iniciado_em") or lote_original.get("criado_em"), "tipo": None}
            for a in lote_original.get("arquivos", [])]
    comps = concluidos(runtime, sol)
    for c in comps:
        docs += [{"arquivo": d["arquivo"], "sha256": d["sha256"], "lote": c["lote"], "origem": "COMPLEMENTAR",
                  "incluido_em": c["concluido_em"], "tipo": d.get("tipo"), "area": d.get("area")} for d in c["documentos"]]
    return {"tentativa": int(numero), "montado_em": agora(), "lote_original": lote_original["lote"],
            "lotes_complementares": [c["lote"] for c in comps], "pastas_complementares": [c["pasta"] for c in comps],
            "documentos": docs, "classificador": "documentos_local"}


def versao_classificador() -> str:
    """Identifica o classificador VIGENTE pelo conteúdo do código de Documentos (muda se a regra mudar)."""
    return "documentos_local@" + sha256_arquivo(Path(documentos_local.__file__))[:16]


def reclassificar(item: dict, origem: dict, cnpjs) -> dict:
    """Classificação VIGENTE de um item do pacote, pela leitura JÁ extraída (mesmo SHA; nada é relido nem alterado) e pelas
    regras ATUAIS de Documentos. Guarda a classificação HISTÓRICA ao lado. Ambíguo/erro → ValueError (fail-closed): o rótulo
    histórico NUNCA é herdado para resolver a dúvida."""
    if not origem or origem.get("sha256") != item.get("sha256"):
        raise ValueError(f"{item.get('arquivo')}: leitura do documento ausente ou de outro conteúdo; pacote não montado.")
    try:
        avaliacao = documentos_local.avaliar_extrato(origem)
        tipo = documentos_local.classificar(origem)
        encaminhamento = documentos_local.encaminhamento(origem, cnpjs)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{item.get('arquivo')}: classificação vigente falhou ({type(exc).__name__}); o rótulo histórico não é herdado; "
                         "pacote não montado.") from exc
    if avaliacao.get("decisao") not in ("EXTRATO", "NAO_EXTRATO") or not tipo:
        raise ValueError(f"{item.get('arquivo')}: classificação vigente {avaliacao.get('decisao') or 'indeterminada'} "
                         f"({', '.join(avaliacao.get('contra_evidencias') or [])}); requer triagem do Supervisor; pacote não montado.")
    if not item.get("conteudo_utilizavel"):
        encaminhamento = dict(encaminhamento, situacao="AGUARDANDO_LEITURA")
    historica = {"tipo": item.get("tipo"), "area": (item.get("encaminhamento") or {}).get("area")}
    novo = dict(item, tipo=tipo, encaminhamento=encaminhamento)
    novo["classificacao_historica"] = historica
    novo["classificacao_vigente"] = {"tipo": tipo, "area": encaminhamento.get("area"), "decisao_extrato": avaliacao["decisao"],
                                     "evidencias": avaliacao.get("evidencias", []), "contra_evidencias": avaliacao.get("contra_evidencias", []),
                                     "classificador": versao_classificador()}
    novo["divergencia_historica"] = (historica["tipo"], historica["area"]) != (tipo, encaminhamento.get("area"))
    return novo


def montar_pacote(runtime: Path, sol: str, numero: int, efetivo: dict) -> dict | None:
    """Pacote efetivo (documentos-local.json + extracao-local.json) da tentativa: o pacote ORIGINAL da SOL (inalterado) somado
    aos pacotes de Documentos de cada complemento do snapshot. Sem complementos → None (a tentativa usa o pacote original).
    Gravado uma única vez em tentativas/NNNN/pacote/ (criação exclusiva); hashes registrados no snapshot."""
    if not efetivo["lotes_complementares"]:
        return None
    base = Path(runtime) / "execucoes" / sol
    manifesto = json.loads((base / "documentos-local.json").read_text(encoding="utf-8"))
    extracao = json.loads((base / "extracao-local.json").read_text(encoding="utf-8"))
    for lote in efetivo["lotes_complementares"]:
        pasta = pasta_complementos(runtime, sol) / lote
        m = json.loads((pasta / "documentos-local.json").read_text(encoding="utf-8"))
        x_bytes = (pasta / "extracao-local.json").read_bytes()
        if hashlib.sha256(x_bytes).hexdigest() != m.get("extracao_sha256"):
            raise ValueError(f"Extração do complemento {lote} alterada; pacote não montado.")
        x = json.loads(x_bytes)
        manifesto["itens"] += m["itens"]
        manifesto["pendencias"] = list(manifesto.get("pendencias", [])) + [f"[complemento {lote}] {p}" for p in m.get("pendencias", [])]
        extracao["arquivos"] += x["arquivos"]
        extracao["duplicados_exatos"] = list(extracao.get("duplicados_exatos", [])) + list(x.get("duplicados_exatos", []))
    # classificação VIGENTE de todos os itens (originais e complementares) para ESTA tentativa; histórico preservado ao lado
    por_arquivo = {a["arquivo"]: a for a in extracao["arquivos"]}
    cnpjs = documentos_local.cnpjs_cadastro(manifesto["empresa"])
    manifesto["itens"] = [reclassificar(i, por_arquivo.get(i["arquivo"]), cnpjs) for i in manifesto["itens"]]
    vigente = {i["arquivo"]: i for i in manifesto["itens"]}
    for d in efetivo["documentos"]:
        i = vigente.get(d["arquivo"])
        if not i or i["sha256"] != d["sha256"]:
            raise ValueError(f"{d['arquivo']}: documento do snapshot sem item correspondente no pacote; pacote não montado.")
        d.update(tipo=i["tipo"], area=i["encaminhamento"].get("area"), classificacao_historica=i["classificacao_historica"],
                 classificacao_vigente={k: i["classificacao_vigente"][k] for k in ("tipo", "area", "decisao_extrato", "classificador")},
                 divergencia_historica=i["divergencia_historica"])
    manifesto["classificacao"] = {"classificador": versao_classificador(), "criterio": "classificação vigente recalculada para a tentativa; "
                                  "classificação histórica preservada em cada item (classificacao_historica)"}
    manifesto["tarefas_areas"] = documentos_local.montar_tarefas(manifesto["itens"])
    manifesto["pastas_complementares"] = efetivo["pastas_complementares"]
    manifesto["pacote_efetivo"] = {"tentativa": int(numero), "lote_original": efetivo["lote_original"],
                                   "lotes_complementares": efetivo["lotes_complementares"], "montado_em": efetivo["montado_em"]}
    serial = json.dumps(extracao, ensure_ascii=False, indent=2)
    manifesto["extracao_sha256"] = hashlib.sha256(serial.encode("utf-8")).hexdigest()
    destino = base / "tentativas" / f"{int(numero):04d}" / "pacote"
    destino.mkdir(parents=True, exist_ok=False)                     # nunca sobrescreve um pacote existente
    (destino / "extracao-local.json").write_text(serial, encoding="utf-8", newline="")
    (destino / "documentos-local.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    for nome in ("extracao-local.json", "documentos-local.json"):
        os.chmod(destino / nome, 0o444)
    return {"pasta": destino.relative_to(base).as_posix(),
            "documentos_local_sha256": sha256_arquivo(destino / "documentos-local.json"),
            "extracao_sha256": manifesto["extracao_sha256"]}


def consumo(runtime: Path, sol: str, tentativas: list) -> dict:
    """Rastreabilidade lote complementar → tentativas que o consumiram (pelo snapshot de cada tentativa)."""
    uso = {}
    for t in tentativas:
        for lote in (t.get("manifesto_efetivo") or {}).get("lotes_complementares", []):
            uso.setdefault(lote, []).append(t["numero"])
    return uso
