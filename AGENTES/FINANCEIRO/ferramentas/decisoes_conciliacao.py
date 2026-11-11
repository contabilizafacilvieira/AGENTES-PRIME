"""Decisões do Supervisor sobre a conciliação financeira banco × relatório (camada SEPARADA do motor).

Contrato: DECISOES_SUPERVISOR_CONCILIACAO_V1 (versão 1.0). Biblioteca pura: não lê o extrato, não chama o motor e nunca
altera CONCILIACAO_FINANCEIRA_V1, movimentos bancários ou movimentos auxiliares. A política V1 do motor não muda.

Princípio: DECISÃO DA MÁQUINA ≠ DECISÃO DO SUPERVISOR.
  classificacao_motor (CONCILIADO/PROVAVEL/AMBIGUO/NAO_CONCILIADO) é preservada como veio do motor;
  decisao_supervisor (SEM_DECISAO/APROVADO/REJEITADO) é uma camada própria;
  estado_operacional é calculado AQUI (função única), nunca na interface.

Regras:
- CONCILIADO não recebe aprovação/rejeição (já é confirmação automática).
- PROVAVEL: APROVADO ou REJEITADO, com justificativa. Aprovação em lote somente de PROVAVEIS.
- AMBIGUO: aprovação SOMENTE com a escolha explícita de UM candidato; os demais ficam registrados como não escolhidos.
  REJEITADO (nenhum candidato serve) é permitido. Nunca em lote.
- NAO_CONCILIADO: nenhuma associação é criada; só OBSERVACAO (não muda o estado).
- REVOGADO desfaz a decisão vigente SEM apagar nada: histórico encadeado e imutável (hash de cada evento + anterior).
- Antes de gravar: revisão da conciliação e revisão das decisões precisam ser as mesmas que a tela viu (estado obsoleto →
  recusa) e nenhum movimento bancário/auxiliar pode ficar confirmado em duas associações (conflito → recusa do pedido todo).
- Uma decisão confirma SOMENTE a associação BANCO ↔ FONTE AUXILIAR: nunca é suporte documental/fiscal, conferência de nota,
  guia ou lançamento contábil.
- Fail-closed: registro ilegível, de outra SOL/empresa/competência ou com cadeia quebrada → EstadoCorrompido (nada é aceito
  nem aplicado).
"""
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

CONTRATO = "DECISOES_SUPERVISOR_CONCILIACAO_V1"
VERSAO = "1.0"
CONTRATO_CONCILIACAO = "CONCILIACAO_FINANCEIRA_V1"
POLITICA = "CONCILIACAO_FINANCEIRA_POLITICA_V1"

SEM_DECISAO, APROVADO, REJEITADO, REVOGADO, OBSERVACAO = "SEM_DECISAO", "APROVADO", "REJEITADO", "REVOGADO", "OBSERVACAO"
DECISOES = (APROVADO, REJEITADO, REVOGADO, OBSERVACAO)
ORIGENS = ("INDIVIDUAL", "LOTE")

CONFIRMADA_AUTO = "ASSOCIACAO_CONFIRMADA_AUTOMATICAMENTE"
CONFIRMADA_SUPERVISOR = "ASSOCIACAO_CONFIRMADA_PELO_SUPERVISOR"
AGUARDANDO = "AGUARDANDO_SUPERVISOR"
REJEITADA = "ASSOCIACAO_REJEITADA"
SEM_ASSOCIACAO = "SEM_ASSOCIACAO"
ESTADOS_OPERACIONAIS = (CONFIRMADA_AUTO, CONFIRMADA_SUPERVISOR, AGUARDANDO, REJEITADA, SEM_ASSOCIACAO)

RESPONSAVEL_PADRAO = "Supervisor Contábil"
JUSTIFICATIVA_MIN, JUSTIFICATIVA_MAX = 10, 500
LIMITE_LOTE = 200
EFEITO = ("Confirma somente a associação entre o movimento bancário e a fonte auxiliar. Não é suporte documental ou fiscal, "
          "não confere nota, guia ou documento e não cria nem aprova lançamento contábil.")
RE_ASSOC = re.compile(r"CF-[0-9A-F]{12}")
CAMPOS_EVENTO = ("id", "sequencia", "sol", "empresa", "competencia", "tentativa", "associacao", "classificacao_motor", "cardinalidade",
                 "bancarios", "auxiliares", "decisao", "candidato_escolhido", "candidatos_nao_escolhidos", "justificativa", "responsavel",
                 "em", "origem", "lote", "politica", "contrato_conciliacao", "revisao_conciliacao", "decisao_anterior", "estado_anterior",
                 "estado_posterior", "efeito", "suporte_documental", "suporte_fiscal", "lancamento_contabil", "hash_anterior", "hash")


class DecisaoRecusada(Exception):
    """Pedido recusado sem nenhuma gravação. `codigo` é estável (testes/API); `mensagem` é texto pt-BR para a tela."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo, self.mensagem = codigo, mensagem


class EstadoObsoleto(DecisaoRecusada):
    def __init__(self):
        super().__init__("ESTADO_OBSOLETO", "As informações mudaram desde que a tela foi aberta. Atualize a tela e revise de novo; "
                                            "nenhuma decisão foi gravada.")


class EstadoCorrompido(Exception):
    """Registro de decisões ilegível ou inconsistente: nada é aceito nem aplicado (fail-closed)."""


# ---------------------------------------------------------------- utilidades
def canonico(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(obj) -> str:
    return hashlib.sha256(canonico(obj).encode("utf-8")).hexdigest()


def revisao_conciliacao(conciliacao: dict) -> str:
    """Identifica o CONTEÚDO da conciliação (associações, política, contrato). Nova execução com resultado diferente → nova revisão."""
    if not isinstance(conciliacao, dict):
        return "RC-AUSENTE"
    base = {k: conciliacao.get(k) for k in ("contrato", "versao", "politica", "associacoes")}
    return "RC-" + _sha(base)[:20]


def revisao_decisoes(dados: dict) -> str:
    eventos = (dados or {}).get("eventos") or []
    return "RD-" + (eventos[-1]["hash"][:20] if eventos else "INICIAL")


def mascarar_documentos(texto: str) -> str:
    """CPF/CNPJ (com ou sem pontuação) digitados em texto livre nunca são gravados por inteiro."""
    def troca(m):
        d = re.sub(r"\D", "", m.group(0))
        return f"{d[:2]}{'*' * (len(d) - 4)}{d[-2:]}" if len(d) in (11, 14) else m.group(0)
    return re.sub(r"\d[\d./-]{9,}\d", troca, texto)


def agora() -> str:
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _assoc_por_id(conciliacao: dict) -> dict:
    return {x["id"]: x for x in (conciliacao or {}).get("associacoes") or []}


# ---------------------------------------------------------------- armazenamento (camada separada, gravação atômica)
def vazio(contexto: dict) -> dict:
    return {"contrato": CONTRATO, "versao": VERSAO, "sol": contexto["sol"], "empresa": contexto["empresa"],
            "competencia": contexto["competencia"], "eventos": []}


def _hash_evento(ev: dict) -> str:
    return _sha({k: v for k, v in ev.items() if k != "hash"})


def validar(dados, contexto: dict) -> dict:
    """Confere contrato, SOL/empresa/competência e a cadeia de eventos. Qualquer problema → EstadoCorrompido."""
    if not isinstance(dados, dict) or dados.get("contrato") != CONTRATO or dados.get("versao") != VERSAO:
        raise EstadoCorrompido("contrato do registro de decisões inválido")
    for k in ("sol", "empresa", "competencia"):
        if dados.get(k) != contexto.get(k):
            raise EstadoCorrompido(f"registro de decisões pertence a outra {k}")
    eventos = dados.get("eventos")
    if not isinstance(eventos, list):
        raise EstadoCorrompido("lista de eventos ausente")
    anterior = None
    for i, ev in enumerate(eventos, 1):
        if not isinstance(ev, dict) or set(ev) != set(CAMPOS_EVENTO):
            raise EstadoCorrompido(f"evento {i} com campos inválidos")
        if ev["sequencia"] != i or ev["hash_anterior"] != anterior or ev["hash"] != _hash_evento(ev):
            raise EstadoCorrompido(f"cadeia de eventos quebrada no evento {i}")
        if any(ev[k] != contexto[k] for k in ("sol", "empresa", "competencia")) or ev["decisao"] not in DECISOES:
            raise EstadoCorrompido(f"evento {i} de outro contexto ou decisão desconhecida")
        if ev["suporte_documental"] or ev["suporte_fiscal"] or ev["lancamento_contabil"]:
            raise EstadoCorrompido(f"evento {i} marca suporte/lançamento (proibido)")
        anterior = ev["hash"]
    return dados


def carregar(caminho: Path, contexto: dict) -> dict:
    caminho = Path(caminho)
    if not caminho.exists():
        return vazio(contexto)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EstadoCorrompido(f"registro de decisões ilegível ({type(exc).__name__})") from exc
    return validar(dados, contexto)


def gravar_atomico(caminho: Path, dados: dict) -> None:
    """Temporário completo na MESMA pasta + fsync + os.replace: leitor nunca vê arquivo pela metade; falha não deixa resto."""
    caminho = Path(caminho)
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


# ---------------------------------------------------------------- decisão vigente e estado operacional (lógica central)
def _candidato_igual(c: dict, escolhido: dict) -> bool:
    return sorted(c.get("bancarios") or []) == sorted(escolhido.get("bancarios") or []) and \
        sorted(c.get("auxiliares") or []) == sorted(escolhido.get("auxiliares") or [])


def _ainda_valida(ev: dict, assoc) -> bool:
    """A decisão só vale para a MESMA associação que o Supervisor viu (mesma classificação do motor e mesmos movimentos)."""
    if not assoc or assoc["classificacao"] != ev["classificacao_motor"]:
        return False
    if sorted(assoc["bancarios"]) != ev["bancarios"] or sorted(assoc["auxiliares"]) != ev["auxiliares"]:
        return False
    if ev["candidato_escolhido"] is not None:
        return any(_candidato_igual(c, ev["candidato_escolhido"]) for c in assoc.get("candidatos") or [])
    return True


def vigentes_brutas(dados: dict) -> dict:
    """Última decisão APROVADO/REJEITADO não revogada por associação (sem conferir contra a conciliação atual)."""
    atual = {}
    for ev in (dados or {}).get("eventos") or []:
        if ev["decisao"] in (APROVADO, REJEITADO):
            atual[ev["associacao"]] = ev
        elif ev["decisao"] == REVOGADO:
            atual.pop(ev["associacao"], None)
    return atual


def decisoes_efetivas(dados: dict, conciliacao: dict) -> tuple:
    """(efetivas, desatualizadas): efetivas = decisões vigentes que ainda correspondem à conciliação atual."""
    por_id = _assoc_por_id(conciliacao)
    efetivas, desatualizadas = {}, []
    for aid, ev in vigentes_brutas(dados).items():
        (efetivas.__setitem__(aid, ev) if _ainda_valida(ev, por_id.get(aid)) else desatualizadas.append(ev))
    return efetivas, desatualizadas


def estado_operacional(assoc: dict, decisao=None) -> str:
    """ÚNICO lugar que traduz classificação do motor + decisão do Supervisor em estado operacional."""
    classe = assoc["classificacao"]
    if classe == "CONCILIADO":
        return CONFIRMADA_AUTO
    if classe == "NAO_CONCILIADO":
        return SEM_ASSOCIACAO
    if classe in ("PROVAVEL", "AMBIGUO"):
        if decisao is None:
            return AGUARDANDO
        if decisao["decisao"] == APROVADO and (classe == "PROVAVEL" or decisao.get("candidato_escolhido")):
            return CONFIRMADA_SUPERVISOR
        if decisao["decisao"] == REJEITADO:
            return REJEITADA
    return AGUARDANDO


def ids_confirmados(assoc: dict, decisao=None) -> tuple:
    """(bancários, auxiliares) com associação confirmada por esta associação (automática ou pelo Supervisor)."""
    estado = estado_operacional(assoc, decisao)
    if estado == CONFIRMADA_AUTO:
        return list(assoc["bancarios"]), list(assoc["auxiliares"])
    if estado == CONFIRMADA_SUPERVISOR:
        alvo = decisao["candidato_escolhido"] or {"bancarios": assoc["bancarios"], "auxiliares": assoc["auxiliares"]}
        return list(alvo["bancarios"]), list(alvo["auxiliares"])
    return [], []


def bancarios_liberados(conciliacao: dict, efetivas: dict) -> set:
    out = set()
    for x in (conciliacao or {}).get("associacoes") or []:
        out.update(ids_confirmados(x, efetivas.get(x["id"]))[0])
    return out


def bloqueios(conciliacao: dict, efetivas: dict, suporte_independente=()) -> list:
    """Movimentos bancários que AINDA impedem o avanço: sem associação confirmada (automática ou pelo Supervisor) e sem
    suporte independente (regras já existentes do Financeiro). PROVAVEL/AMBIGUO sem decisão, REJEITADO e NAO_CONCILIADO
    continuam bloqueando."""
    liberados = bancarios_liberados(conciliacao, efetivas) | set(suporte_independente or ())
    todos = sorted({i for x in (conciliacao or {}).get("associacoes") or [] for i in x["bancarios"]})
    return [i for i in todos if i not in liberados]


def _conflitos(conciliacao: dict, efetivas: dict) -> list:
    vistos, repetidos = {}, []
    for x in (conciliacao or {}).get("associacoes") or []:
        bids, aids = ids_confirmados(x, efetivas.get(x["id"]))
        for chave in [("B", i) for i in bids] + [("A", i) for i in aids]:
            if chave in vistos and vistos[chave] != x["id"]:
                repetidos.append(chave[1])
            vistos.setdefault(chave, x["id"])
    return sorted(set(repetidos))


def resumo(conciliacao: dict, efetivas: dict, suporte_independente=()) -> dict:
    """Números dos cards (mesma lógica central): contagens por associação e por movimento bancário."""
    assocs = (conciliacao or {}).get("associacoes") or []
    estados = {x["id"]: estado_operacional(x, efetivas.get(x["id"])) for x in assocs}
    contar = lambda f: sum(1 for x in assocs if f(x, estados[x["id"]]))
    total_b = len({i for x in assocs for i in x["bancarios"]})
    liberados = bancarios_liberados(conciliacao, efetivas)
    bloq = bloqueios(conciliacao, efetivas, suporte_independente)
    return {
        "conciliados_automaticamente": contar(lambda x, e: e == CONFIRMADA_AUTO),
        "para_revisar": contar(lambda x, e: x["classificacao"] == "PROVAVEL" and e == AGUARDANDO),
        "ambiguos": contar(lambda x, e: x["classificacao"] == "AMBIGUO" and e == AGUARDANDO),
        "nao_conciliados": contar(lambda x, e: e == SEM_ASSOCIACAO and x["bancarios"]),
        "relatorio_sem_banco": contar(lambda x, e: e == SEM_ASSOCIACAO and not x["bancarios"]),
        "aprovados_supervisor": contar(lambda x, e: e == CONFIRMADA_SUPERVISOR),
        "rejeitados": contar(lambda x, e: e == REJEITADA),
        "movimentos_bancarios": total_b,
        "movimentos_confirmados": len(liberados),
        "bloqueios_restantes": len(bloq),
        "percentual_confirmado": round(100 * len(liberados) / total_b) if total_b else 0,
    }


# ---------------------------------------------------------------- registro de decisões (validação + evento auditável)
def _justificativa(texto) -> str:
    if not isinstance(texto, str):
        raise DecisaoRecusada("JUSTIFICATIVA_OBRIGATORIA", "Informe a justificativa da decisão.")
    t = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", texto)).strip()
    if len(t) < JUSTIFICATIVA_MIN:
        raise DecisaoRecusada("JUSTIFICATIVA_OBRIGATORIA", f"Informe a justificativa da decisão (mínimo de {JUSTIFICATIVA_MIN} caracteres).")
    if len(t) > JUSTIFICATIVA_MAX:
        raise DecisaoRecusada("JUSTIFICATIVA_LONGA", f"Justificativa muito longa (máximo de {JUSTIFICATIVA_MAX} caracteres).")
    return mascarar_documentos(t)


def _validar_pedido(p: dict, assoc, atual) -> None:
    if not assoc:
        raise DecisaoRecusada("ASSOCIACAO_INEXISTENTE", "Associação inexistente nesta conciliação. Atualize a tela.")
    classe, dec = assoc["classificacao"], p["decisao"]
    if dec not in DECISOES:
        raise DecisaoRecusada("DECISAO_INVALIDA", "Decisão desconhecida.")
    if dec == OBSERVACAO:
        if p.get("candidato") is not None:
            raise DecisaoRecusada("CANDIDATO_INDEVIDO", "Observação não escolhe candidato.")
        return
    if dec == REVOGADO:
        if atual is None:
            raise DecisaoRecusada("NADA_A_REVOGAR", "Não há decisão vigente para desfazer nesta associação.")
        return
    if classe == "CONCILIADO":
        raise DecisaoRecusada("JA_CONCILIADO", "Associação conciliada automaticamente: não precisa de aprovação nem de rejeição.")
    if classe == "NAO_CONCILIADO":
        raise DecisaoRecusada("SEM_ASSOCIACAO", "Não há associação segura para confirmar ou rejeitar; o sistema não cria associação.")
    if atual is not None:
        if atual["decisao"] == dec and (dec != APROVADO or canonico(atual["candidato_escolhido"]) == canonico(p.get("candidato"))):
            raise DecisaoRecusada("DECISAO_REPETIDA", "Esta decisão já está registrada para esta associação; nada foi alterado.")
        raise DecisaoRecusada("JA_DECIDIDA", "Esta associação já tem uma decisão vigente. Desfaça a decisão antes de registrar outra.")
    if classe == "PROVAVEL" and p.get("candidato") is not None:
        raise DecisaoRecusada("CANDIDATO_INDEVIDO", "Associação provável não tem candidatos a escolher.")
    if classe == "AMBIGUO" and dec == APROVADO:
        c = p.get("candidato")
        if not isinstance(c, dict) or not any(_candidato_igual(x, c) for x in assoc.get("candidatos") or []):
            raise DecisaoRecusada("CANDIDATO_OBRIGATORIO", "Associação ambígua: escolha explicitamente UM candidato válido para confirmar.")
    if classe == "AMBIGUO" and dec == REJEITADO and p.get("candidato") is not None:
        raise DecisaoRecusada("CANDIDATO_INDEVIDO", "Rejeição da ambiguidade não escolhe candidato.")


def registrar(dados: dict, contexto: dict, conciliacao: dict, pedidos: list, *, revisao_conciliacao_cliente: str,
              revisao_decisoes_cliente: str, justificativa, origem: str = "INDIVIDUAL", responsavel: str = RESPONSAVEL_PADRAO,
              em: str | None = None) -> tuple:
    """Valida TUDO antes de gravar e devolve (novos_dados, eventos_novos). Nenhum efeito colateral: quem chama grava.
    Lote: só APROVADO de PROVAVEIS sem decisão; um item inválido recusa o lote inteiro (fail-closed)."""
    validar(dados, contexto)
    if not isinstance(conciliacao, dict) or conciliacao.get("contrato") != CONTRATO_CONCILIACAO or conciliacao.get("politica") != POLITICA:
        raise DecisaoRecusada("CONCILIACAO_INDISPONIVEL", "Conciliação financeira indisponível ou de outra política; nada foi gravado.")
    if revisao_conciliacao_cliente != revisao_conciliacao(conciliacao) or revisao_decisoes_cliente != revisao_decisoes(dados):
        raise EstadoObsoleto()
    if origem not in ORIGENS:
        raise DecisaoRecusada("ORIGEM_INVALIDA", "Origem da decisão inválida.")
    texto = _justificativa(justificativa)
    if not isinstance(pedidos, list) or not pedidos:
        raise DecisaoRecusada("PEDIDO_VAZIO", "Nenhuma associação selecionada.")
    if origem == "LOTE" and len(pedidos) > LIMITE_LOTE:
        raise DecisaoRecusada("LOTE_GRANDE", f"Selecione no máximo {LIMITE_LOTE} associações por vez.")
    if origem == "INDIVIDUAL" and len(pedidos) != 1:
        raise DecisaoRecusada("PEDIDO_INVALIDO", "Decisão individual trata uma associação por vez.")
    alvos = [p.get("associacao") if isinstance(p, dict) else None for p in pedidos]
    if any(not isinstance(a, str) or not RE_ASSOC.fullmatch(a) for a in alvos) or len(set(alvos)) != len(alvos):
        raise DecisaoRecusada("PEDIDO_INVALIDO", "Associação repetida ou identificador inválido no pedido.")
    por_id = _assoc_por_id(conciliacao)
    efetivas, _ = decisoes_efetivas(dados, conciliacao)
    brutas = vigentes_brutas(dados)
    for p in pedidos:
        assoc = por_id.get(p["associacao"])
        if origem == "LOTE" and (p.get("decisao") != APROVADO or not assoc or assoc["classificacao"] != "PROVAVEL" or p.get("candidato") is not None):
            raise DecisaoRecusada("LOTE_SO_PROVAVEIS", "A aprovação em lote aceita somente associações PROVÁVEIS; nenhum item do lote foi gravado.")
        try:
            _validar_pedido(p, assoc, brutas.get(p["associacao"]) if p.get("decisao") == REVOGADO else efetivas.get(p["associacao"]))
        except DecisaoRecusada as exc:
            if origem == "LOTE":
                raise DecisaoRecusada(exc.codigo, f"Lote recusado: {exc.mensagem} Nenhum item do lote foi gravado.") from exc
            raise
    # simula o estado posterior e revalida conflitos (nenhum movimento confirmado em duas associações)
    eventos = list(dados["eventos"])
    novos, nova_efetiva = [], dict(efetivas)
    lote = ("LT-" + _sha([alvos, revisao_decisoes(dados), em or ""])[:12].upper()) if origem == "LOTE" else None
    momento = em or agora()
    for p in pedidos:
        assoc = por_id[p["associacao"]]
        antes_ev = efetivas.get(assoc["id"])
        anterior_bruto = brutas.get(assoc["id"])
        estado_antes = estado_operacional(assoc, antes_ev)
        ev = {"sequencia": len(eventos) + 1, "sol": contexto["sol"], "empresa": contexto["empresa"], "competencia": contexto["competencia"],
              "tentativa": contexto.get("tentativa"), "associacao": assoc["id"], "classificacao_motor": assoc["classificacao"],
              "cardinalidade": assoc.get("cardinalidade"), "bancarios": sorted(assoc["bancarios"]), "auxiliares": sorted(assoc["auxiliares"]),
              "decisao": p["decisao"], "candidato_escolhido": None, "candidatos_nao_escolhidos": [],
              "justificativa": texto, "responsavel": str(responsavel)[:80], "em": momento, "origem": origem, "lote": lote,
              "politica": POLITICA, "contrato_conciliacao": CONTRATO_CONCILIACAO, "revisao_conciliacao": revisao_conciliacao(conciliacao),
              "decisao_anterior": anterior_bruto["id"] if (p["decisao"] == REVOGADO and anterior_bruto) else None,
              "estado_anterior": estado_antes, "estado_posterior": None, "efeito": EFEITO,
              "suporte_documental": False, "suporte_fiscal": False, "lancamento_contabil": False,
              "hash_anterior": eventos[-1]["hash"] if eventos else None}
        if p["decisao"] == APROVADO and assoc["classificacao"] == "AMBIGUO":
            esc = next(c for c in assoc["candidatos"] if _candidato_igual(c, p["candidato"]))
            ev["candidato_escolhido"] = {"bancarios": sorted(esc["bancarios"]), "auxiliares": sorted(esc["auxiliares"])}
            ev["candidatos_nao_escolhidos"] = [{"bancarios": sorted(c["bancarios"]), "auxiliares": sorted(c["auxiliares"])}
                                               for c in assoc["candidatos"] if not _candidato_igual(c, esc)]
        if p["decisao"] in (APROVADO, REJEITADO):
            nova_efetiva[assoc["id"]] = ev
        elif p["decisao"] == REVOGADO:
            nova_efetiva.pop(assoc["id"], None)
        ev["estado_posterior"] = estado_operacional(assoc, nova_efetiva.get(assoc["id"]))
        ev["id"] = "DS-" + _sha([ev["sequencia"], ev["associacao"], ev["decisao"], ev["hash_anterior"], momento])[:12].upper()
        ev = {k: ev[k] for k in CAMPOS_EVENTO if k != "hash"}
        ev["hash"] = _hash_evento(ev)
        eventos.append(ev)
        novos.append(ev)
    conflito = _conflitos(conciliacao, nova_efetiva)
    if conflito:
        raise DecisaoRecusada("CONFLITO", f"Recusado: {len(conflito)} movimento(s) ficariam confirmados em mais de uma associação. "
                                          "Nada foi gravado; revise as decisões conflitantes.")
    novo = dict(dados, eventos=eventos)
    validar(novo, contexto)
    return novo, novos


def decidir_e_gravar(caminho: Path, contexto: dict, conciliacao: dict, pedidos: list, **kw) -> list:
    """Lê o estado ATUAL do disco, revalida tudo e grava atomicamente. Quem chama deve serializar (trava do servidor)."""
    dados = carregar(caminho, contexto)
    novo, eventos = registrar(dados, contexto, conciliacao, pedidos, **kw)
    gravar_atomico(caminho, novo)
    return eventos
