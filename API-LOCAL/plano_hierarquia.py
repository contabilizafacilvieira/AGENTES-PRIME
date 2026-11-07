"""Árvore do PLANO DE CONTAS — regra GERAL do sistema (não é ajuste de empresa). Código local, determinístico, sem modelo.

Para cada conta, a partir SOMENTE da classificação e das descrições das contas (nunca do número do grupo nem do nome da
própria conta para o tipo):
- classificação original (preservada) e normalizada (para a análise);
- conta superior (o ancestral presente mais próximo), filhas diretas, descendentes, nível e ramo raiz;
- TIPO: SINTÉTICA quando há descendentes na árvore; ANALÍTICA quando é folha (nenhuma conta mais detalhada abaixo).
  Não é "a classificação mais longa vence": vale a relação real de pai e filha.
- GRUPO CONTÁBIL (estrutura do plano): ATIVO, PASSIVO, PATRIMONIO_LIQUIDO, RESULTADO (Contas de Resultado) ou OUTROS
  (Contas de Apuração/compensação), reconhecido pela DESCRIÇÃO das contas principais e HERDADO pelos descendentes. Numeração
  (1, 2, 3...) nunca é usada como prova. Ramo sem evidência suficiente → revisão do Supervisor (só aquele ramo).
- NATUREZA DE RESULTADO (RECEITA, CUSTO, DESPESA) pelo ancestral mais próximo cuja descrição é inequívoca; usada no campo
  `grupo` que os agentes (Bancos, DP, Fiscal, Conciliação) já consomem para checar contas compatíveis.
- ELEGIBILIDADE PARA COMPOSIÇÃO NO BOOK: só conta ANALÍTICA, PATRIMONIAL (Ativo, Passivo, PL) e com saldo final diferente de
  zero. Conta SINTÉTICA nunca exige composição individual; Contas de Resultado e Outros nunca exigem; saldo zero não exige.
Validação de saldos (soma das filhas, anterior + D − C) continua valendo para TODAS as contas, inclusive as sintéticas.
"""
import re
import unicodedata
from decimal import Decimal, InvalidOperation

VERSAO_ANALISE = 2            # versão do algoritmo; bases analisadas antes ganham "Reanalisar base"
GRUPOS_CONTABEIS = ("ATIVO", "PASSIVO", "PATRIMONIO_LIQUIDO", "RESULTADO", "OUTROS")
NOME_GRUPO = {"ATIVO": "Ativo", "PASSIVO": "Passivo", "PATRIMONIO_LIQUIDO": "Patrimônio Líquido", "RESULTADO": "Contas de Resultado",
              "OUTROS": "Outros"}
PATRIMONIAIS = {"ATIVO", "PASSIVO", "PATRIMONIO_LIQUIDO"}
_CLASSIF = re.compile(r"^\d+(?:\.\d+)*$")


def texto_chave(t) -> str:
    """Maiúsculas, sem acentos, separadores como espaço (para reconhecer 'Patrimônio-Líquido', 'CONTAS DE RESULTADO - RECEITAS')."""
    s = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", s)).strip()


def normalizar(classificacao):
    """'1.1.01.' → '1.1.01'; ' 1 . 1 ' → '1.1'. Segmentos preservados como texto ('01' ≠ '1': nada é fundido).
    Devolve None quando não é uma classificação segura (letras, separadores estranhos, vazio)."""
    t = re.sub(r"\s+", "", str(classificacao or "")).rstrip(".")
    return t if _CLASSIF.fullmatch(t) else None


def grupo_por_descricao(descricao):
    """Grupo contábil reconhecido pela descrição de uma conta agrupadora; None se não houver evidência."""
    k = texto_chave(descricao)
    if not k:
        return None
    palavras = k.split()
    if "APURACAO" in palavras or "COMPENSACAO" in palavras:
        return "OUTROS"
    if k.startswith("PATRIMONIO LIQUIDO") or palavras[0] == "PL" or palavras[:2] == ["P", "L"]:
        return "PATRIMONIO_LIQUIDO"
    if {"RESULTADO", "RESULTADOS"} & set(palavras) or palavras[0] in ("RECEITA", "RECEITAS", "CUSTO", "CUSTOS", "DESPESA", "DESPESAS", "DEDUCAO", "DEDUCOES"):
        return "RESULTADO"
    if palavras[0] == "PASSIVO":
        return "PASSIVO"
    if palavras[0] == "ATIVO":
        return "ATIVO"
    return None


def natureza_por_descricao(descricao):
    """Natureza dentro de Contas de Resultado (RECEITA, CUSTO, DESPESA) quando a descrição é inequívoca; None se mista/ausente."""
    p = set(texto_chave(descricao).split())
    receita = bool(p & {"RECEITA", "RECEITAS", "DEDUCAO", "DEDUCOES", "VENDAS", "FATURAMENTO"})
    custo = bool(p & {"CUSTO", "CUSTOS"})
    despesa = bool(p & {"DESPESA", "DESPESAS"})
    if receita + custo + despesa != 1:
        return None
    return "RECEITA" if receita else "CUSTO" if custo else "DESPESA"


def _saldo(v):
    try:
        return Decimal(str(v)) if v not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


def analisar(contas, chave_classificacao="classificacao", chave_descricao="descricao", grupos_confirmados=None):
    """Monta a árvore e devolve {'contas': {id: info}, 'revisao': [...], 'resumo': {...}}. `contas` é uma lista de dicts com
    classificação e descrição (e, opcionalmente, codigo e saldo_atual). id = índice na lista. `grupos_confirmados`:
    {classificação normalizada do ramo: grupo} confirmados pelo Supervisor para ramos ambíguos."""
    grupos_confirmados = {normalizar(k): v for k, v in (grupos_confirmados or {}).items() if v in GRUPOS_CONTABEIS and normalizar(k)}
    info, por_norm, revisao = {}, {}, []
    for i, c in enumerate(contas):
        n = normalizar(c.get(chave_classificacao))
        info[i] = {"classificacao": c.get(chave_classificacao), "classificacao_normalizada": n, "superior": None, "filhas": [],
                   "descendentes": 0, "nivel": None, "tipo": "", "ramo": None, "grupo_contabil": "", "grupo_origem": "",
                   "natureza_resultado": None, "exige_composicao": False, "motivo_composicao": "", "revisao": []}
        if n is None:
            info[i]["revisao"].append("classificação que não pode ser lida com segurança (hierarquia não presumida)")
            continue
        por_norm.setdefault(n, []).append(i)
    for n, ids in por_norm.items():
        if len(ids) > 1:
            for i in ids:
                info[i]["revisao"].append(f"classificação {n} repetida em mais de uma conta")
    validas = {n: ids[0] for n, ids in por_norm.items() if len(ids) == 1}
    for n, i in validas.items():
        partes = n.split(".")
        info[i]["nivel"] = len(partes)
        pai = next((".".join(partes[:k]) for k in range(len(partes) - 1, 0, -1) if ".".join(partes[:k]) in validas), None)
        if pai:
            info[i]["superior"] = validas[pai]
            info[validas[pai]]["filhas"].append(i)
    def descendentes(i):
        return sum(1 + descendentes(f) for f in info[i]["filhas"])
    for n, i in validas.items():
        info[i]["descendentes"] = descendentes(i)
        info[i]["tipo"] = "SINTETICA" if info[i]["filhas"] else "ANALITICA"
        raiz = i
        while info[raiz]["superior"] is not None:
            raiz = info[raiz]["superior"]
        info[i]["ramo"] = raiz
    # grupo contábil: a conta agrupadora mais próxima com evidência na descrição define o ramo; filhas herdam.
    # Exceção aceita da estrutura: Patrimônio Líquido dentro de Passivo. Qualquer outra contradição → revisão do ramo.
    for n, i in sorted(validas.items(), key=lambda x: x[0].count(".")):
        sup = info[i]["superior"]
        herdado, origem = (info[sup]["grupo_contabil"], info[sup]["grupo_origem"]) if sup is not None else ("", "")
        proprio = grupo_por_descricao(contas[i].get(chave_descricao)) if info[i]["filhas"] else None
        confirmado = grupos_confirmados.get(n)
        if confirmado and not herdado:
            g, o = confirmado, "CONFIRMADO_SUPERVISOR"
        elif proprio and (not herdado or (herdado == "PASSIVO" and proprio == "PATRIMONIO_LIQUIDO")):
            g, o = proprio, f"AUTOMATICO: {contas[i].get(chave_descricao)}"
        else:                     # dentro de um ramo identificado, o grupo herdado prevalece (nomes internos não mudam o grupo)
            g, o = herdado, origem
        info[i]["grupo_contabil"], info[i]["grupo_origem"] = g, o
    for n, i in validas.items():
        if not info[i]["grupo_contabil"]:
            info[i]["revisao"].append("grupo contábil não identificado com segurança pela estrutura do plano")
        if info[i]["grupo_contabil"] == "RESULTADO":
            atual = i
            while atual is not None:
                nat = natureza_por_descricao(contas[atual].get(chave_descricao))
                if nat:
                    info[i]["natureza_resultado"] = nat
                    break
                atual = info[atual]["superior"]
    # elegibilidade para composição no book
    for i, x in info.items():
        saldo = _saldo(contas[i].get("saldo_atual"))
        if x["tipo"] != "ANALITICA":
            x["motivo_composicao"] = "conta sintética: consolida as analíticas (não exige composição individual)" if x["tipo"] else "tipo não identificado"
        elif x["grupo_contabil"] not in PATRIMONIAIS:
            x["motivo_composicao"] = ("Contas de Resultado não exigem composição no book" if x["grupo_contabil"] == "RESULTADO" else
                                      "conta fora do patrimônio (Outros) não exige composição" if x["grupo_contabil"] == "OUTROS" else
                                      "grupo contábil não identificado")
        elif not saldo:
            x["motivo_composicao"] = "saldo final zero: composição não exigida"
        else:
            x["exige_composicao"], x["motivo_composicao"] = True, "conta analítica patrimonial com saldo"
    for i, x in info.items():
        if x["revisao"]:
            revisao.append({"id": i, "classificacao": x["classificacao"], "descricao": contas[i].get(chave_descricao),
                            "codigo": contas[i].get("codigo"), "motivos": x["revisao"]})
    ramos_ambiguos = sorted({info[i]["ramo"] for i in validas.values() if not info[i]["grupo_contabil"] and info[i]["ramo"] is not None})
    resumo = {"contas": len(contas), "classificadas_automaticamente": len(contas) - len(revisao), "precisam_confirmacao": len(revisao),
              "sinteticas": sum(x["tipo"] == "SINTETICA" for x in info.values()), "analiticas": sum(x["tipo"] == "ANALITICA" for x in info.values()),
              "exigem_composicao": sum(x["exige_composicao"] for x in info.values()),
              "por_grupo": {g: sum(x["grupo_contabil"] == g for x in info.values()) for g in GRUPOS_CONTABEIS},
              "ramos_para_confirmar": [{"classificacao": contas[r].get(chave_classificacao), "descricao": contas[r].get(chave_descricao)} for r in ramos_ambiguos]}
    return {"contas": info, "revisao": revisao, "resumo": resumo}


def grupo_para_agentes(x) -> str:
    """Valor do campo `grupo` do plano consumido pelos agentes: ATIVO/PASSIVO/PATRIMONIO_LIQUIDO; para resultado, a natureza
    (RECEITA/CUSTO/DESPESA) quando identificada, senão RESULTADO; OUTROS; '' quando não identificado."""
    g = x.get("grupo_contabil") or ""
    if g == "RESULTADO":
        return x.get("natureza_resultado") or "RESULTADO"
    return g


def anotar(contas, chave_classificacao="classificacao", chave_descricao="descricao", grupos_confirmados=None):
    """Aplica a análise sobre a própria lista (campos derivados, marcados como AUTOMÁTICOS) e devolve o resultado da análise."""
    r = analisar(contas, chave_classificacao, chave_descricao, grupos_confirmados)
    for i, c in enumerate(contas):
        x = r["contas"][i]
        sup = x["superior"]
        c.update(tipo=x["tipo"], tipo_origem="AUTOMATICO: hierarquia da classificação" if x["tipo"] else "revisão necessária",
                 superior=contas[sup].get(chave_classificacao) if sup is not None else None, nivel=x["nivel"],
                 classificacao_normalizada=x["classificacao_normalizada"], grupo_contabil=x["grupo_contabil"],
                 grupo_origem=x["grupo_origem"], natureza_resultado=x["natureza_resultado"], grupo_sugerido=grupo_para_agentes(x),
                 exige_composicao=x["exige_composicao"], motivo_composicao=x["motivo_composicao"], revisao_plano=x["revisao"])
    return r
