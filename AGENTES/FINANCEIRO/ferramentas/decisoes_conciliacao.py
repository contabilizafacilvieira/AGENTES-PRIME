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
- ASSOCIAÇÃO MANUAL ASSISTIDA (exceções que o motor recusou): só para NAO_CONCILIADO com 1 movimento bancário e nenhum
  registro auxiliar; o Supervisor seleciona explicitamente de 1 a 5 registros da MESMA conciliação, de natureza compatível,
  ainda disponíveis e com soma EXATA (Decimal, tolerância zero). A classificação do motor continua NAO_CONCILIADO; o estado
  operacional passa a ASSOCIACAO_CONFIRMADA_PELO_SUPERVISOR. O limite 5 é proteção da ferramenta manual; a Política V1
  (agrupamento automático até 3) não muda.
"""
import datetime as dt
import hashlib
from decimal import Decimal, InvalidOperation
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
ORIGEM_MANUAL = "ASSOCIACAO_MANUAL_ASSISTIDA"
ORIGENS = ("INDIVIDUAL", "LOTE", ORIGEM_MANUAL)
LIMITE_MANUAL = 5                      # registros por associação manual (proteção da ferramenta; NÃO é a Política V1)
FERRAMENTA_MANUAL = "ASSOCIACAO_MANUAL_ASSISTIDA_V1"
NATUREZA_COMPATIVEL = {"CREDITO": "ENTRADA", "DEBITO": "SAIDA"}
CAMPOS_MANUAL = ("associacao_manual",)  # campo ADICIONAL só dos eventos de associação manual (eventos antigos seguem válidos)

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
        manual = isinstance(ev, dict) and ev.get("origem") == ORIGEM_MANUAL
        if not isinstance(ev, dict) or set(ev) != set(CAMPOS_EVENTO) | (set(CAMPOS_MANUAL) if manual else set()):
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


def universo_auxiliar(conciliacao: dict) -> set:
    """Todos os registros auxiliares da conciliação (o motor lista cada um em alguma associação, inclusive 0x1)."""
    return {i for x in (conciliacao or {}).get("associacoes") or [] for i in x["auxiliares"]}


def _ainda_valida(ev: dict, assoc, universo=None) -> bool:
    """A decisão só vale para a MESMA associação que o Supervisor viu (mesma classificação do motor e mesmos movimentos)."""
    if not assoc or assoc["classificacao"] != ev["classificacao_motor"]:
        return False
    if sorted(assoc["bancarios"]) != ev["bancarios"] or sorted(assoc["auxiliares"]) != ev["auxiliares"]:
        return False
    if ev.get("origem") == ORIGEM_MANUAL:          # registros escolhidos precisam existir na MESMA conciliação
        escolhido = ev.get("candidato_escolhido") or {}
        return (ev["decisao"] == APROVADO and escolhido.get("bancarios") == ev["bancarios"]
                and bool(escolhido.get("auxiliares")) and set(escolhido["auxiliares"]) <= (universo or set()))
    if ev["candidato_escolhido"] is not None:
        return any(_candidato_igual(c, ev["candidato_escolhido"]) for c in assoc.get("candidatos") or [])
    return True


def _escolha_ambiguo(ev) -> bool:
    return ev["decisao"] == APROVADO and ev.get("classificacao_motor") == "AMBIGUO" and bool(ev.get("candidato_escolhido"))


def vigentes_listas(dados: dict) -> dict:
    """Decisões vigentes por associação (sem conferir contra a conciliação atual). AMBIGUO aceita VÁRIAS escolhas parciais
    (candidatos disjuntos, uma por evento) até cobrir todos os seus movimentos bancários; REVOGADO desfaz a escolha indicada em
    decisao_anterior (ou tudo, se ela não for uma escolha vigente). Histórico nunca é apagado."""
    atual = {}
    for ev in (dados or {}).get("eventos") or []:
        aid = ev["associacao"]
        lista = atual.get(aid) or []
        if _escolha_ambiguo(ev) and lista and all(_escolha_ambiguo(e) for e in lista):
            atual[aid] = lista + [ev]                     # escolha parcial adicional do mesmo grupo ambíguo
        elif ev["decisao"] in (APROVADO, REJEITADO):
            atual[aid] = [ev]
        elif ev["decisao"] == REVOGADO:
            resto = [e for e in lista if e.get("id") != ev.get("decisao_anterior")]
            if resto and len(resto) < len(lista):
                atual[aid] = resto
            else:
                atual.pop(aid, None)
    return atual


def vigentes_brutas(dados: dict) -> dict:
    """Compatibilidade: última decisão vigente por associação."""
    return {aid: lista[-1] for aid, lista in vigentes_listas(dados).items()}


def _agregar(lista: list) -> dict:
    """Uma escolha → o próprio evento (formato de sempre). Várias escolhas parciais → visão agregada (união dos candidatos)."""
    if len(lista) == 1:
        return lista[0]
    ev = dict(lista[-1])
    ev["candidato_escolhido"] = {"bancarios": sorted({i for e in lista for i in e["candidato_escolhido"]["bancarios"]}),
                                 "auxiliares": sorted({i for e in lista for i in e["candidato_escolhido"]["auxiliares"]})}
    ev["escolhas"] = list(lista)
    return ev


def escolhas(decisao) -> list:
    """Eventos de escolha vigentes de um AMBIGUO (vazio se não for o caso)."""
    if not decisao or not _escolha_ambiguo(decisao):
        return []
    return list(decisao.get("escolhas") or [decisao])


def decisoes_efetivas(dados: dict, conciliacao: dict) -> tuple:
    """(efetivas, desatualizadas): efetivas = decisões vigentes que ainda correspondem à conciliação atual."""
    por_id = _assoc_por_id(conciliacao)
    universo = universo_auxiliar(conciliacao)
    efetivas, desatualizadas = {}, []
    for aid, lista in vigentes_listas(dados).items():
        validas = [ev for ev in lista if _ainda_valida(ev, por_id.get(aid), universo)]
        desatualizadas += [ev for ev in lista if ev not in validas]
        if validas:
            efetivas[aid] = _agregar(validas)
    return efetivas, desatualizadas


def parcial(assoc: dict, decisao=None) -> bool:
    """AMBIGUO com escolha(s) confirmada(s) que ainda NÃO cobrem todos os movimentos bancários do grupo."""
    if assoc["classificacao"] != "AMBIGUO" or not escolhas(decisao):
        return False
    return not set(assoc["bancarios"]) <= set(decisao["candidato_escolhido"]["bancarios"])


def candidatos_disponiveis(assoc: dict, decisao=None, consumidos_fora=()) -> list:
    """Candidatos ORIGINAIS de um AMBIGUO ainda possíveis: nenhum banco/registro já usado por escolha vigente deste grupo nem
    registro consumido por outra associação confirmada. Nada é escolhido automaticamente, mesmo que reste só um."""
    usados = decisao["candidato_escolhido"] if escolhas(decisao) else {"bancarios": [], "auxiliares": []}
    bloq_b, bloq_a = set(usados["bancarios"]), set(usados["auxiliares"]) | set(consumidos_fora or ())
    return [c for c in assoc.get("candidatos") or [] if not set(c["bancarios"]) & bloq_b and not set(c["auxiliares"]) & bloq_a]


def estado_operacional(assoc: dict, decisao=None) -> str:
    """ÚNICO lugar que traduz classificação do motor + decisão do Supervisor em estado operacional."""
    classe = assoc["classificacao"]
    if classe == "CONCILIADO":
        return CONFIRMADA_AUTO
    if classe == "NAO_CONCILIADO":
        if decisao is not None and decisao.get("origem") == ORIGEM_MANUAL and decisao["decisao"] == APROVADO \
                and (decisao.get("candidato_escolhido") or {}).get("auxiliares"):
            return CONFIRMADA_SUPERVISOR           # associação manual assistida; a classificação do motor NÃO muda
        return SEM_ASSOCIACAO
    if classe in ("PROVAVEL", "AMBIGUO"):
        if decisao is None:
            return AGUARDANDO
        if decisao["decisao"] == APROVADO and classe == "PROVAVEL":
            return CONFIRMADA_SUPERVISOR
        if decisao["decisao"] == APROVADO and decisao.get("candidato_escolhido"):
            # o grupo só está resolvido quando TODOS os seus movimentos bancários têm associação confirmada
            return AGUARDANDO if parcial(assoc, decisao) else CONFIRMADA_SUPERVISOR
        if decisao["decisao"] == REJEITADO:
            return REJEITADA
    return AGUARDANDO


def ids_confirmados(assoc: dict, decisao=None) -> tuple:
    """(bancários, auxiliares) com associação confirmada por esta associação (automática ou pelo Supervisor)."""
    estado = estado_operacional(assoc, decisao)
    if estado == CONFIRMADA_AUTO:
        return list(assoc["bancarios"]), list(assoc["auxiliares"])
    if escolhas(decisao):                             # AMBIGUO: só o que as escolhas vigentes cobrem (mesmo se parcial)
        return list(decisao["candidato_escolhido"]["bancarios"]), list(decisao["candidato_escolhido"]["auxiliares"])
    if estado == CONFIRMADA_SUPERVISOR:
        alvo = decisao["candidato_escolhido"] or {"bancarios": assoc["bancarios"], "auxiliares": assoc["auxiliares"]}
        return list(alvo["bancarios"]), list(alvo["auxiliares"])
    return [], []


def bancarios_liberados(conciliacao: dict, efetivas: dict) -> set:
    out = set()
    for x in (conciliacao or {}).get("associacoes") or []:
        out.update(ids_confirmados(x, efetivas.get(x["id"]))[0])
    return out


def auxiliares_confirmados(conciliacao: dict, efetivas: dict) -> set:
    """Registros auxiliares JÁ consumidos por associação confirmada (automática ou pelo Supervisor): indisponíveis."""
    out = set()
    for x in (conciliacao or {}).get("associacoes") or []:
        out.update(ids_confirmados(x, efetivas.get(x["id"]))[1])
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
        "ambiguos_parciais": contar(lambda x, e: parcial(x, efetivas.get(x["id"]))),
        "nao_conciliados": contar(lambda x, e: e == SEM_ASSOCIACAO and x["bancarios"]),
        "relatorio_sem_banco": contar(lambda x, e: e == SEM_ASSOCIACAO and not x["bancarios"]
                                      and not set(x["auxiliares"]) & auxiliares_confirmados(conciliacao, efetivas)),
        "associacoes_manuais": contar(lambda x, e: e == CONFIRMADA_SUPERVISOR and x["classificacao"] == "NAO_CONCILIADO"),
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
        ativos = escolhas(atual) or [atual]
        alvo = p.get("alvo")
        if alvo is not None and alvo not in {e["id"] for e in ativos}:
            raise DecisaoRecusada("ALVO_INVALIDO", "A decisão indicada não está vigente nesta associação. Atualize a tela.")
        if alvo is None and len(ativos) > 1:
            raise DecisaoRecusada("ALVO_OBRIGATORIO", "Há mais de uma escolha vigente neste grupo: indique qual escolha desfazer.")
        return
    if classe == "CONCILIADO":
        raise DecisaoRecusada("JA_CONCILIADO", "Associação conciliada automaticamente: não precisa de aprovação nem de rejeição.")
    if classe == "NAO_CONCILIADO":
        raise DecisaoRecusada("SEM_ASSOCIACAO", "Não há associação segura para confirmar ou rejeitar; o sistema não cria associação.")
    if atual is not None and classe == "AMBIGUO" and dec == APROVADO and escolhas(atual):
        c = p.get("candidato")
        if not isinstance(c, dict) or not any(_candidato_igual(x, c) for x in assoc.get("candidatos") or []):
            raise DecisaoRecusada("CANDIDATO_OBRIGATORIO", "Associação ambígua: escolha explicitamente UM candidato válido para confirmar.")
        if any(_candidato_igual(e["candidato_escolhido"], c) for e in escolhas(atual)):
            raise DecisaoRecusada("DECISAO_REPETIDA", "Esta escolha já está registrada para este grupo; nada foi alterado.")
        if not parcial(assoc, atual):
            raise DecisaoRecusada("JA_DECIDIDA", "Todos os movimentos deste grupo já têm associação confirmada. Desfaça uma escolha antes de registrar outra.")
        usados = atual["candidato_escolhido"]
        if set(c["bancarios"]) & set(usados["bancarios"]) or set(c["auxiliares"]) & set(usados["auxiliares"]):
            raise DecisaoRecusada("CANDIDATO_INDISPONIVEL", "Este candidato usa movimento ou registro já confirmado em outra escolha deste grupo. "
                                                            "Atualize a tela; nada foi gravado.")
        return                                          # escolha parcial adicional (disjunta) permitida
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


def _dinheiro(v) -> Decimal:
    if isinstance(v, (float, bool)) or v is None:
        raise DecisaoRecusada("REGISTRO_INVALIDO", "Valor ausente ou inválido em registro selecionado.")
    try:
        d = Decimal(str(v))
    except InvalidOperation as exc:
        raise DecisaoRecusada("REGISTRO_INVALIDO", "Valor inválido em registro selecionado.") from exc
    if d != d.quantize(Decimal("0.01")):
        raise DecisaoRecusada("REGISTRO_INVALIDO", "Valor com mais de duas casas decimais.")
    return d.quantize(Decimal("0.01"))


def _mascarar_doc(doc) -> str | None:
    d = re.sub(r"\D", "", str(doc or ""))
    return (f"{d[:2]}{'*' * max(len(d) - 4, 0)}{d[-2:]}" if len(d) > 4 else "*" * len(d)) if d else None


def validar_manual(assoc, escolhidos, registros: dict, conciliacao: dict, efetivas: dict) -> dict:
    """Regras da associação manual assistida. Devolve o detalhamento auditável (registros, soma, diferença). Recusa = nada gravado."""
    if not assoc or assoc["classificacao"] != "NAO_CONCILIADO" or len(assoc["bancarios"]) != 1 or assoc["auxiliares"]:
        raise DecisaoRecusada("MANUAL_INDISPONIVEL", "A associação manual só se aplica a movimento bancário que o sistema não conseguiu associar.")
    if not isinstance(escolhidos, list) or not escolhidos or not all(isinstance(i, str) and i for i in escolhidos) \
            or len(set(escolhidos)) != len(escolhidos):
        raise DecisaoRecusada("SELECAO_INVALIDA", "Selecione os registros do relatório (sem repetição).")
    if len(escolhidos) > LIMITE_MANUAL:
        raise DecisaoRecusada("LIMITE_MANUAL", f"A associação manual aceita no máximo {LIMITE_MANUAL} registros do relatório por movimento.")
    universo = universo_auxiliar(conciliacao)
    consumidos = auxiliares_confirmados(conciliacao, efetivas)
    natureza = NATUREZA_COMPATIVEL.get(assoc.get("natureza_bancaria"))
    itens, soma = [], Decimal("0.00")
    for i in escolhidos:
        r = registros.get(i)
        if i not in universo or not r:
            raise DecisaoRecusada("REGISTRO_INEXISTENTE", "Registro selecionado não pertence a esta conciliação. Atualize a tela.")
        if i in consumidos:
            raise DecisaoRecusada("REGISTRO_INDISPONIVEL", "Um registro selecionado já foi usado em outra associação confirmada. "
                                                           "Atualize a tela; nada foi gravado.")
        if not natureza or r.get("natureza") != natureza:
            raise DecisaoRecusada("NATUREZA_INCOMPATIVEL", "Natureza incompatível: entrada no banco só com recebimento; saída só com pagamento.")
        sha = r.get("sha") or r.get("sha256")
        if not sha:
            raise DecisaoRecusada("SEM_RASTREIO", "Registro selecionado sem rastreabilidade (origem/SHA); não pode ser associado.")
        v = _dinheiro(r.get("valor"))
        soma += v
        cp = r.get("contraparte") or {}
        itens.append({"id": i, "valor": f"{v:.2f}", "natureza": r.get("natureza"), "data_quitacao": r.get("data_quitacao"), "data": r.get("data"),
                      "contraparte": mascarar_documentos(str(cp.get("nome") or cp.get("nome_fantasia") or ""))[:120] or None,
                      "contraparte_documento": _mascarar_doc(cp.get("documento")), "documento": mascarar_documentos(str(r.get("documento") or ""))[:60] or None,
                      "sha256_origem": sha, "origem": r.get("origem")})
    valor_banco = _dinheiro(assoc.get("valor_bancario"))
    if soma != valor_banco:
        raise DecisaoRecusada("SOMA_DIFERENTE", f"A soma dos registros selecionados (R$ {soma:.2f}) é diferente do valor do banco "
                                                f"(R$ {valor_banco:.2f}). Diferença: R$ {abs(valor_banco - soma):.2f}. A associação exige soma exata.")
    return {"tipo": ORIGEM_MANUAL, "ferramenta": FERRAMENTA_MANUAL, "limite_manual": LIMITE_MANUAL, "registros": itens,
            "quantidade": len(itens), "valor_bancario": f"{valor_banco:.2f}", "soma_relatorio": f"{soma:.2f}", "diferenca": "0.00",
            "natureza_bancaria": assoc.get("natureza_bancaria"), "origem_bancaria_sha256": (assoc.get("origem") or {}).get("bancaria_sha256")}


def registrar(dados: dict, contexto: dict, conciliacao: dict, pedidos: list, *, revisao_conciliacao_cliente: str,
              revisao_decisoes_cliente: str, justificativa, origem: str = "INDIVIDUAL", responsavel: str = RESPONSAVEL_PADRAO,
              em: str | None = None, registros: dict | None = None) -> tuple:
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
    if origem in ("INDIVIDUAL", ORIGEM_MANUAL) and len(pedidos) != 1:
        raise DecisaoRecusada("PEDIDO_INVALIDO", "Decisão individual trata uma associação por vez.")
    if origem == ORIGEM_MANUAL and (not isinstance(pedidos[0], dict) or pedidos[0].get("decisao") != APROVADO or pedidos[0].get("candidato") is not None):
        raise DecisaoRecusada("PEDIDO_INVALIDO", "Associação manual: confirme os registros selecionados.")
    if origem != ORIGEM_MANUAL and any(isinstance(p, dict) and p.get("manual") is not None for p in pedidos):
        raise DecisaoRecusada("PEDIDO_INVALIDO", "Seleção manual só é aceita pela associação manual assistida.")
    alvos = [p.get("associacao") if isinstance(p, dict) else None for p in pedidos]
    if any(not isinstance(a, str) or not RE_ASSOC.fullmatch(a) for a in alvos) or len(set(alvos)) != len(alvos):
        raise DecisaoRecusada("PEDIDO_INVALIDO", "Associação repetida ou identificador inválido no pedido.")
    por_id = _assoc_por_id(conciliacao)
    efetivas, _ = decisoes_efetivas(dados, conciliacao)
    brutas = {aid: _agregar(l) for aid, l in vigentes_listas(dados).items()}
    for p in pedidos:
        assoc = por_id.get(p["associacao"])
        if origem == "LOTE" and (p.get("decisao") != APROVADO or not assoc or assoc["classificacao"] != "PROVAVEL" or p.get("candidato") is not None):
            raise DecisaoRecusada("LOTE_SO_PROVAVEIS", "A aprovação em lote aceita somente associações PROVÁVEIS; nenhum item do lote foi gravado.")
        if origem == ORIGEM_MANUAL:
            atual = efetivas.get(p["associacao"])
            if atual is not None:
                igual = atual.get("origem") == ORIGEM_MANUAL and sorted((atual.get("candidato_escolhido") or {}).get("auxiliares") or []) \
                    == sorted(((p.get("manual") or {}).get("auxiliares")) or [])
                raise DecisaoRecusada("DECISAO_REPETIDA" if igual else "JA_DECIDIDA",
                                      "Esta associação manual já está registrada; nada foi alterado." if igual
                                      else "Este movimento já tem uma decisão vigente. Desfaça a decisão antes de registrar outra.")
            continue
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
    manual = (validar_manual(por_id[pedidos[0]["associacao"]], (pedidos[0].get("manual") or {}).get("auxiliares"), registros or {},
                             conciliacao, efetivas) if origem == ORIGEM_MANUAL else None)
    for p in pedidos:
        assoc = por_id[p["associacao"]]
        antes_ev = efetivas.get(assoc["id"])
        anterior_bruto = brutas.get(assoc["id"])
        if p["decisao"] == REVOGADO and anterior_bruto is not None:
            anterior_bruto = next(e for e in (escolhas(anterior_bruto) or [anterior_bruto])
                                  if p.get("alvo") in (None, e["id"]))
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
        if manual is not None:
            ev["candidato_escolhido"] = {"bancarios": sorted(assoc["bancarios"]), "auxiliares": sorted(r["id"] for r in manual["registros"])}
            ev["associacao_manual"] = manual
        # estado posterior recalculado pela MESMA regra de leitura (inclui escolhas parciais e revogação de uma escolha)
        ev["id"] = "DS-" + _sha([ev["sequencia"], ev["associacao"], ev["decisao"], ev["hash_anterior"], momento])[:12].upper()
        nova_efetiva = decisoes_efetivas({"eventos": eventos + [dict(ev)]}, conciliacao)[0]
        ev["estado_posterior"] = estado_operacional(assoc, nova_efetiva.get(assoc["id"]))
        ev = {k: ev[k] for k in CAMPOS_EVENTO + (CAMPOS_MANUAL if manual is not None else ()) if k != "hash"}
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
