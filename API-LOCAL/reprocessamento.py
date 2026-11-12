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


def proximo_numero(base: Path, sol: str) -> int:
    anteriores = listar(base, sol)
    return (anteriores[-1]["numero"] if anteriores else 0) + 1


def criar(base: Path, sol: str, *, origem: dict, motivo: str, solicitante: str,
          documentos: list[dict], raiz: Path | None = None, manifesto_efetivo: dict | None = None) -> dict:
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
    if manifesto_efetivo is not None:
        # SNAPSHOT IMUTÁVEL: documentos que esta tentativa pode usar (original + complementares existentes AGORA).
        # Documento complementar recebido depois só entra numa próxima tentativa.
        if manifesto_efetivo.get("tentativa") != numero:
            raise ValueError("Manifesto efetivo montado para outra tentativa.")
        registro["manifesto_efetivo"] = manifesto_efetivo
        registro["manifesto_efetivo_sha256"] = hashlib.sha256(json.dumps(manifesto_efetivo, ensure_ascii=False, sort_keys=True)
                                                              .encode("utf-8")).hexdigest()
    gravar(pasta / f"{numero:04d}" / "tentativa.json", registro)
    return registro


# ---------------------------------------------------------------- ciclo de vida (v2)
# PREPARADA → EM_EXECUCAO → CONCLUIDA | BLOQUEADA | FALHOU
#   BLOQUEADA = execução correta cujo resultado impede prosseguir (ex.: falta de extrato) — NÃO é falha técnica.
#   FALHOU    = erro técnico (exceção, etapa sem resultado, registro recusado).
# Tentativas antigas (sem "ciclo_vida") nunca são assumidas automaticamente por uma execução nova: a reconciliação delas é
# uma ação explícita, para não atribuir execuções à tentativa errada.
#   PAUSADA = checkpoint do Supervisor (ex.: Financeiro concluído, Contabilidade/Bancos aguardando autorização). Continua ATIVA:
#             não é falha nem fim; a MESMA tentativa volta a EM_EXECUCAO quando o Supervisor autoriza a continuação.
CICLO_VIDA = "V2"
ATIVOS = ("PREPARADA", "EM_EXECUCAO", "PAUSADA")
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
    elif t["status"] == "PAUSADA":                      # continuação autorizada após checkpoint: MESMA tentativa
        momento = agora()
        t.update(status="EM_EXECUCAO", retomada_em=momento)
        t.setdefault("eventos", []).append({"em": momento, "evento": "Continuação autorizada após o checkpoint (EM_EXECUCAO)."})
        gravar(_arquivo(base, sol, t["numero"]), t)
    return t


def pausar(base: Path, sol: str, numero: int, *, checkpoint: dict, estado_sol: str | None) -> dict:
    """EM_EXECUCAO → PAUSADA no checkpoint do Supervisor (não finaliza, não falha). Repetição não altera nada."""
    caminho = _arquivo(base, sol, numero)
    t = ler(caminho)
    if not t:
        raise ValueError("Tentativa não encontrada.")
    if t.get("status") == "PAUSADA":
        return dict(t, pausa_repetida=True)
    if t.get("status") != "EM_EXECUCAO":
        raise ValueError("Somente uma tentativa EM_EXECUCAO pode ser pausada.")
    momento = agora()
    t.update(status="PAUSADA", pausada_em=momento, estado_sol_pausa=estado_sol, checkpoint=checkpoint)
    t.setdefault("eventos", []).append({"em": momento, "evento": f"Pausada no checkpoint após {checkpoint.get('apos')}: "
                                                              f"{checkpoint.get('proxima_etapa')} aguardando autorização do Supervisor."})
    gravar(caminho, t)
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
             "estado_sol_final": x.get("estado_sol_final"), "ciclo_vida": x.get("ciclo_vida"),
             "legada_pendente": x.get("ciclo_vida") != CICLO_VIDA and x.get("status") in ATIVOS and not x.get("reconciliacao_legada"),
             "reconciliacao_legada": x.get("reconciliacao_legada"),
             "manifesto_efetivo": {k: (x.get("manifesto_efetivo") or {}).get(k) for k in ("lote_original", "lotes_complementares", "documentos")}
             if x.get("manifesto_efetivo") else None} for x in tentativas]


# ---------------------------------------------------------------- reconciliação de tentativa LEGADA (ação explícita e auditada)
# Tentativa anterior ao ciclo V2 que ficou PREPARADA/EM_EXECUCAO embora tenha sido executada (o vínculo não era gravado).
# Evidência ESTRUTURAL, nunca só horário:
#   1. exatamente UMA retomada no registro do Coordenador com o MESMO motivo da tentativa (texto exato);
#   2. registros de execução do Coordenador no intervalo dessa retomada (até a retomada seguinte);
#   3. cada registro aponta, pelo resultado_sha256, para UMA pasta de execução existente cujo resultado.json tem esse hash;
#   4. nenhuma dessas pastas está vinculada a outra tentativa; nenhuma falha registrada no mesmo intervalo (evidência mista).
# O estado final é DERIVADO das execuções comprovadas (status_final); nada é presumido.
ORIGEM_LEGADA = "RECONCILIACAO_LEGADA"
REGISTROS_EXECUCAO = {"financeiro": "financeiro", "bancos": "bancos", "conciliacao": "conciliacao", "fiscal": "fiscal",
                      "contabilidade_fiscal": "contabilfiscal", "dp": "dp", "contabilidade_dp": "contabdp"}


def frase_reconciliacao(sol: str, numero: int) -> str:
    return f"RECONCILIAR TENTATIVA {int(numero):04d} {sol}"


def _ts(valor):
    try:
        return datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None


def avaliar_legada(base: Path, sol: str, numero: int, registro: dict | None) -> dict:
    """Somente leitura. {elegivel, codigo, motivos, estado_derivado, execucoes, evidencias, ja_reconciliada}."""
    def recusa(codigo, motivo, **extra):
        return dict({"elegivel": False, "codigo": codigo, "motivos": [motivo], "estado_derivado": None, "execucoes": [],
                     "evidencias": {}, "ja_reconciliada": False, "sol": sol, "numero": int(numero)}, **extra)
    t = ler(_arquivo(base, sol, numero))
    if not t or t.get("sol") != sol:
        return recusa("TENTATIVA_INEXISTENTE", "Tentativa não encontrada nesta solicitação.")
    if t.get("reconciliacao_legada"):
        return recusa("JA_RECONCILIADA", "Esta tentativa já foi reconciliada; nada a fazer.", ja_reconciliada=True,
                      reconciliacao=t["reconciliacao_legada"], estado_derivado=t.get("status"))
    if t.get("ciclo_vida") == CICLO_VIDA:
        return recusa("NAO_LEGADA", "Tentativa do ciclo de vida atual (V2): o encerramento é automático, não há reconciliação legada.")
    if t.get("status") not in ATIVOS:
        return recusa("ESTADO_JA_FINAL", f"Tentativa já está em estado final ({t.get('status')}); nada incompatível a reconciliar.")
    if not registro or registro.get("sol", sol) != sol:
        return recusa("SOL_INEXISTENTE", "Registro da solicitação não encontrado.")
    motivo = str(t.get("motivo") or "").strip()
    retomadas = sorted(registro.get("retomadas") or [], key=lambda r: str(r.get("em")))
    iguais = [r for r in retomadas if str(r.get("motivo") or "").strip() == motivo and motivo]
    if not iguais:
        return recusa("SEM_EVIDENCIA_DE_EXECUCAO", "Nenhuma retomada do Coordenador com o motivo desta tentativa: não há prova de que "
                                                  "ela foi executada. Nada é marcado como executado.")
    if len(iguais) > 1:
        return recusa("EVIDENCIA_CONFLITANTE", "Mais de uma retomada com o mesmo motivo: não é possível saber qual execução pertence "
                                              "a esta tentativa.")
    ret = iguais[0]
    ini, criada = _ts(ret.get("em")), _ts(t.get("criada_em"))
    if not ini or not criada or ini < criada:
        return recusa("EVIDENCIA_INSUFICIENTE", "A retomada não é posterior à criação da tentativa; vínculo não comprovado.")
    seguinte = next((_ts(r.get("em")) for r in retomadas if _ts(r.get("em")) and _ts(r.get("em")) > ini), None)
    no_intervalo = lambda em: (x := _ts(em)) is not None and x >= ini and (seguinte is None or x < seguinte)
    pasta = _pasta(base, sol)
    vinculadas_outras = {e.get("execucao") for o in listar(base, sol) if o.get("numero") != t.get("numero") for e in o.get("execucoes", [])}
    execucoes, evid = [], []
    for chave, prefixo in REGISTROS_EXECUCAO.items():
        for reg in registro.get(chave) or []:
            if not no_intervalo(reg.get("em")):
                continue
            alvo = reg.get("resultado_sha256")
            if not alvo:
                return recusa("EVIDENCIA_INSUFICIENTE", f"Registro de {chave} sem hash do resultado; vínculo não comprovado.")
            pastas = [p for p in pasta.glob(f"{prefixo}-*") if p.name.split("-")[-1].isdigit() and (p / "resultado.json").is_file()
                      and sha256(p / "resultado.json") == alvo]
            if len(pastas) != 1:
                return recusa("EVIDENCIA_INSUFICIENTE" if not pastas else "EVIDENCIA_CONFLITANTE",
                              f"Registro de {chave} não aponta para exatamente uma pasta de execução com o mesmo resultado.")
            nome = pastas[0].name
            if reg.get("tentativa") is not None and str(reg["tentativa"]) != nome.split("-")[-1]:
                return recusa("EVIDENCIA_CONFLITANTE", f"Registro de {chave} indica outra execução ({reg['tentativa']}).")
            if nome in vinculadas_outras:
                return recusa("EVIDENCIA_CONFLITANTE", f"{nome} já está vinculada a outra tentativa.")
            execucoes.append({"execucao": nome, "etapa": prefixo})
            evid.append({"registro": chave, "em": reg.get("em"), "resultado_sha256": alvo, "execucao": nome})
    if not execucoes:
        return recusa("SEM_EVIDENCIA_DE_EXECUCAO", "Nenhum resultado de execução registrado após a retomada: não há prova de execução.")
    falhas = [e for e in registro.get("eventos") or [] if isinstance(e, dict) and no_intervalo(e.get("em"))
              and str(e.get("evento") or "").startswith("Falha na etapa")]
    if falhas:
        return recusa("EVIDENCIA_CONFLITANTE", "Há falhas registradas no mesmo intervalo das execuções: resultado não determinável com segurança.")
    resumo = resumir_execucoes(base, sol, execucoes)
    estado = status_final(resumo, [])
    return {"elegivel": True, "codigo": "ELEGIVEL", "motivos": [], "estado_derivado": estado, "execucoes": resumo,
            "evidencias": {"retomada": {"em": ret.get("em"), "motivo": motivo, "origem": ret.get("origem")}, "registros": evid,
                           "criterio": "motivo idêntico da retomada + resultado_sha256 do registro do Coordenador = resultado.json da pasta"},
            "ja_reconciliada": False, "sol": sol, "numero": int(t["numero"]), "estado_legado": t.get("status")}


def reconciliar_legada(base: Path, sol: str, numero: int, registro: dict, *, justificativa: str, frase: str,
                       responsavel: str = "Supervisor", raiz: Path | None = None) -> dict:
    """Ação explícita. Acrescenta uma CAMADA administrativa: o registro original fica copiado (com hash) em
    reconciliacao-legada.json (criação exclusiva) e a tentativa passa ao estado derivado das evidências. Nada é apagado."""
    av = avaliar_legada(base, sol, numero, registro)
    if av.get("ja_reconciliada"):
        return dict(av, resultado="JA_RECONCILIADA")
    if not av["elegivel"]:
        raise ValueError(av["motivos"][0])
    if frase != frase_reconciliacao(sol, numero):
        raise ValueError(f"Digite exatamente a frase de confirmação: {frase_reconciliacao(sol, numero)}")
    texto = " ".join(str(justificativa or "").split())
    if not 10 <= len(texto) <= 500:
        raise ValueError("Informe a justificativa (10 a 500 caracteres).")
    caminho = _arquivo(base, sol, numero)
    original_bytes = caminho.read_bytes()
    original = json.loads(original_bytes)
    commit, tag = _codigo_atual(raiz or Path.cwd())
    momento = agora()
    auditoria = {"origem": ORIGEM_LEGADA, "sol": sol, "empresa": registro.get("empresa"), "competencia": registro.get("competencia"),
                 "tentativa": int(numero), "estado_legado_anterior": original.get("status"), "estado_reconciliado": av["estado_derivado"],
                 "execucoes_vinculadas": [e["execucao"] for e in av["execucoes"]], "motivo_tentativa": original.get("motivo"),
                 "justificativa": texto, "responsavel": str(responsavel or "Supervisor")[:80], "em": momento,
                 "versao_codigo": commit, "tag": tag, "evidencias": av["evidencias"], "execucoes": av["execucoes"],
                 "tentativa_original_sha256": hashlib.sha256(original_bytes).hexdigest(), "tentativa_original": original}
    camada = caminho.with_name("reconciliacao-legada.json")
    with open(camada, "x", encoding="utf-8") as f:                       # criação exclusiva: nunca sobrescreve
        f.write(json.dumps(auditoria, ensure_ascii=False, indent=2))
    t = dict(original)
    t.update(status=av["estado_derivado"], finalizada_em=momento,
             execucoes=[{"execucao": e["execucao"], "etapa": e["etapa"], "vinculada_em": momento, "origem": ORIGEM_LEGADA}
                        for e in av["execucoes"]],
             resultado={"execucoes": av["execucoes"], "origem": ORIGEM_LEGADA},
             reconciliacao_legada={k: auditoria[k] for k in ("origem", "estado_legado_anterior", "estado_reconciliado", "execucoes_vinculadas",
                                                             "justificativa", "responsavel", "em", "versao_codigo", "tag",
                                                             "tentativa_original_sha256")}
             | {"arquivo": camada.name, "arquivo_sha256": sha256(camada)})
    t.setdefault("eventos", []).append({"em": momento, "evento": f"Reconciliação legada: {original.get('status')} → {av['estado_derivado']} "
                                                              f"(execuções comprovadas: {', '.join(auditoria['execucoes_vinculadas'])})."})
    gravar(caminho, t)
    return dict(av, resultado="RECONCILIADA", tentativa=t)
