"""REGRAS DA ROTINA CAIXINHA por empresa (CLIENTES/<EMP>/REGRAS-CAIXINHA.json, contrato REGRAS_CAIXINHA_V1).

Rotina CAIXINHA: empresas que NÃO fornecem extrato bancário. O Domínio já integra notas, provisões tributárias, folha, pró-labore e
retenções; faltam as BAIXAS das obrigações. A contrapartida das baixas é a conta Caixa Geral da própria empresa.

O arquivo tem duas regras governadas (mesmo mecanismo de AGENTES/CONTABILIDADE/governanca_regras.py, área "CAIXINHA"):
- CONFIGURACAO: contas (códigos reduzidos do plano DA EMPRESA), tributos ↔ códigos de receita, política de datas e critérios de baixa;
- POLITICA_FOLHA: regra operacional do pró-labore (manter em aberto só o líquido da última competência da folha), conta, data do
  lançamento e classificação "REGULARIZAÇÃO CONFORME POLÍTICA CAIXINHA".
Situações: PROPOSTA (não aplicada) → APROVADA só pelo comando do Coordenador com a frase exata
"VALIDADO REGRA CAIXINHA <EMPRESA> <CHAVE>"; TESTE_FICTICIO só vale em empresa com AMOSTRA-FICTICIA.json.
A confirmação fica vinculada à versão e ao sha256 do conteúdo: qualquer mudança volta a regra para PROPOSTA (versão anterior
preservada em VERSOES/). Sugestões de contas pela descrição do plano NUNCA são gravadas como aprovadas.
Regras de uma empresa nunca valem em outra (empresa e CNPJ conferidos).
"""
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "AGENTES" / "CONTABILIDADE") not in sys.path:
    sys.path.insert(0, str(RAIZ / "AGENTES" / "CONTABILIDADE"))
import governanca_regras as gov  # noqa: E402

ARQUIVO = "REGRAS-CAIXINHA.json"
CONTRATO = "REGRAS_CAIXINHA_V1"
AREA = "CAIXINHA"
ROTINAS = ("TRADICIONAL", "CAIXINHA")
CHAVES = ("CONFIGURACAO", "POLITICA_FOLHA")
RESPONSAVEL = "Supervisor Contábil"

# Contas da rotina: (rótulo, grupos aceitos, obrigatória, termos para SUGESTÃO pela descrição do plano)
CONTAS = {
    "CAIXA_GERAL": ("Caixa Geral", {"ATIVO"}, True, ("caixa geral", "caixa")),
    "SIMPLES_NACIONAL": ("Simples Nacional a Recolher", {"PASSIVO"}, False, ("simples nacional a recolher", "simples nacional", "das a recolher")),
    "INSS": ("INSS a Recolher", {"PASSIVO"}, False, ("inss a recolher", "inss a pagar", "inss")),
    "IRRF": ("IRRF a Recolher", {"PASSIVO"}, False, ("irrf a recolher", "irrf a pagar", "irrf", "imposto de renda retido")),
    "PRO_LABORE": ("Pró-labore a Pagar", {"PASSIVO"}, False, ("pro-labore a pagar", "pro labore a pagar", "pro-labore", "pro labore")),
    "FGTS": ("FGTS a Recolher", {"PASSIVO"}, False, ("fgts a recolher", "fgts a pagar", "fgts")),
    "MULTAS_FISCAIS": ("Multas sobre tributos (despesa)", {"DESPESA", "RESULTADO", "CUSTO"}, False, ("multas fiscais", "multa", "multas")),
    "JUROS_FISCAIS": ("Juros sobre tributos (despesa)", {"DESPESA", "RESULTADO", "CUSTO"}, False, ("juros passivos", "juros de mora", "juros")),
}
RE_CHAVE = re.compile(r"[A-Z][A-Z0-9_]{1,39}")

# SUGESTÕES de vínculo tributo ↔ códigos de receita (precisam de confirmação do Supervisor; nunca aprovadas em silêncio)
TRIBUTOS_SUGERIDOS = [
    {"chave": "SIMPLES_NACIONAL", "conta": "SIMPLES_NACIONAL", "tipos_documento": ["DAS"],
     "codigos_receita": ["1001", "1002", "1004", "1005", "1006", "1007", "1008", "1010", "3333"], "descricoes": ["SIMPLES NACIONAL"]},
    {"chave": "INSS", "conta": "INSS", "tipos_documento": [],
     "codigos_receita": ["1082", "1099", "1138", "1141", "1170", "1176", "1191", "1196", "1200", "1213", "1646", "2003", "2100", "2208"],
     "descricoes": ["CP SEGURADOS", "CP PATRONAL", "CP DESCONTADA", "CONTRIBUICAO PREVIDENCIARIA"]},
    {"chave": "IRRF", "conta": "IRRF", "tipos_documento": [], "codigos_receita": ["0561", "0588", "1708", "3208", "8045"],
     "descricoes": ["IRRF"]},
]
POLITICAS_DATA_TRIBUTOS = {
    "DATA_PAGAMENTO": "data do pagamento (e-CAC); pagamento fora da competência em análise vai à revisão (competência encerrada)",
    "ULTIMO_DIA_COMPETENCIA": "último dia da competência em análise (regularização), com a data do pagamento no histórico",
    "DATA_PAGAMENTO_OU_ULTIMO_DIA": "data do pagamento quando dentro da competência; senão, último dia da competência (regularização)",
}
POLITICAS_DATA_FOLHA = {"ULTIMO_DIA_COMPETENCIA": "último dia da competência em análise", "DATA_FIXA": "data definida pelo Supervisor"}
CRITERIOS_PADRAO = {"janela_dias_baixa_razao": 3, "exigir_provisao_identificada": True}


def agora() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _norm(t) -> str:
    return " ".join(unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower().replace("-", " ").split())


def caminho(base) -> Path:
    return Path(base) / ARQUIVO


def ler(base):
    """REGRAS-CAIXINHA.json da pasta da empresa; None se ausente; ValueError se ilegível ou de outro contrato."""
    p = caminho(base)
    if not p.is_file():
        return None
    if p.is_symlink() or p.stat().st_size > 500_000:
        raise ValueError("REGRAS-CAIXINHA.json inválido.")
    d = json.loads(gov.ler_texto(p))
    if not isinstance(d, dict) or d.get("contrato") != CONTRATO:
        raise ValueError("REGRAS-CAIXINHA.json com contrato desconhecido.")
    return d


def conteudo_sha(regra: dict) -> str:
    """sha256 do CONTEÚDO operacional da regra (sem situação, confirmação e histórico): a confirmação vale só para ele."""
    ignorar = {"situacao", "confirmacao", "historico_situacoes", "conteudo_sha256", "versao", "origem", "atualizada_em", "atualizada_por"}
    nucleo = {k: v for k, v in sorted((regra or {}).items()) if k not in ignorar}
    return hashlib.sha256(json.dumps(nucleo, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- plano da empresa
def _analiticas(plano: list) -> dict:
    classes = [str(c.get("classificacao") or "") for c in plano]
    saida = {}
    for c in plano:
        k = str(c.get("classificacao") or "")
        tem_filha = bool(k) and any(x != k and x.startswith(k + ".") for x in classes)
        tipo = str(c.get("tipo") or "").upper().replace("Í", "I")
        if (tipo == "ANALITICA" or (not tipo and not tem_filha)) and c.get("codigo"):
            saida[str(c["codigo"])] = c
    return saida


def sugerir_contas(plano: list) -> dict:
    """SUGESTÃO pela descrição das contas ANALÍTICAS do plano da própria empresa. Empate ou ausência = sem sugestão."""
    analiticas = _analiticas(plano)
    saida = {}
    for chave, (rotulo, grupos, _, termos) in CONTAS.items():
        candidatas = []
        for cod, c in analiticas.items():
            desc = _norm(c.get("descricao"))
            grupo = str(c.get("grupo") or "").upper()
            if grupo and grupo not in grupos:
                continue
            for peso, termo in enumerate(termos):
                t = _norm(termo)
                if desc == t or re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", desc):
                    candidatas.append((peso, -len(t), desc != t, cod, c))
                    break
        candidatas.sort(key=lambda x: x[:3])
        melhor = candidatas[0] if candidatas else None
        empate = bool(melhor and len(candidatas) > 1 and candidatas[1][:3] == melhor[:3])
        saida[chave] = {"rotulo": rotulo, "sugerida": None if (not melhor or empate) else melhor[3],
                        "situacao": "SUGERIDA_PRECISA_CONFIRMACAO" if melhor and not empate else "PRECISA_DEFINICAO",
                        "motivo": ("mais de uma conta com a mesma correspondência; escolha a correta" if empate else
                                   None if melhor else "nenhuma conta analítica com descrição compatível no plano"),
                        "candidatas": [{"codigo": x[3], "classificacao": x[4].get("classificacao"), "descricao": x[4].get("descricao"),
                                        "grupo": x[4].get("grupo")} for x in candidatas[:5]]}
    return saida


def validar_configuracao(cfg: dict, plano: list) -> list:
    """Problemas da configuração (vazio = pode ser salva como PROPOSTA). Contas sempre do plano DESTA empresa."""
    problemas = []
    analiticas = _analiticas(plano)
    todas = {str(c.get("codigo")): c for c in plano if c.get("codigo")}
    contas = cfg.get("contas")
    if not isinstance(contas, dict):
        return ["Contas da rotina ausentes."]
    for chave, cod in contas.items():
        if not RE_CHAVE.fullmatch(str(chave)):
            problemas.append(f"Chave de conta inválida: {chave}.")
            continue
        if cod in (None, ""):
            if chave in CONTAS and CONTAS[chave][2]:
                problemas.append(f"{CONTAS[chave][0]}: conta obrigatória não definida.")
            continue
        cod = str(cod)
        if cod not in todas:
            problemas.append(f"{chave}: conta {cod} não existe no plano desta empresa.")
        elif cod not in analiticas:
            problemas.append(f"{chave}: conta {cod} não é analítica no plano desta empresa.")
        else:
            grupo = str(todas[cod].get("grupo") or "").upper()
            aceitos = CONTAS[chave][1] if chave in CONTAS else {"PASSIVO"}
            if grupo and grupo not in aceitos:
                problemas.append(f"{chave}: conta {cod} é do grupo {grupo}; esperado {'/'.join(sorted(aceitos))}.")
            elif not grupo:
                problemas.append(f"{chave}: conta {cod} sem grupo definido no plano; defina o grupo antes de usar.")
    usados = [str(v) for v in contas.values() if v not in (None, "")]
    repetidos = sorted({c for c in usados if usados.count(c) > 1})
    if repetidos:
        problemas.append("A mesma conta foi indicada para mais de uma finalidade: " + ", ".join(repetidos) + ".")
    tributos = cfg.get("tributos")
    if not isinstance(tributos, list):
        problemas.append("Lista de tributos ausente.")
        tributos = []
    codigos = {}
    for t in tributos:
        if not isinstance(t, dict) or not RE_CHAVE.fullmatch(str(t.get("chave") or "")):
            problemas.append("Tributo sem chave válida.")
            continue
        if str(t.get("conta") or "") not in contas or contas.get(str(t.get("conta"))) in (None, ""):
            problemas.append(f"Tributo {t['chave']}: conta da rotina '{t.get('conta')}' não definida.")
        for c in t.get("codigos_receita") or []:
            if not re.fullmatch(r"\d{4}", str(c)):
                problemas.append(f"Tributo {t['chave']}: código de receita '{c}' inválido (4 dígitos).")
            elif str(c) in codigos and codigos[str(c)] != t["chave"]:
                problemas.append(f"Código de receita {c} vinculado a dois tributos ({codigos[str(c)]} e {t['chave']}).")
            codigos[str(c)] = t["chave"]
    pol = (cfg.get("politica_datas") or {}).get("tributos")
    if pol not in POLITICAS_DATA_TRIBUTOS:
        problemas.append("Política de data das baixas tributárias não definida (" + ", ".join(POLITICAS_DATA_TRIBUTOS) + ").")
    crit = cfg.get("criterios_baixa") or {}
    j = crit.get("janela_dias_baixa_razao")
    if not isinstance(j, int) or isinstance(j, bool) or not 0 <= j <= 10:
        problemas.append("Critério: janela de dias para reconhecer baixa já contabilizada deve ser inteiro de 0 a 10.")
    for k, v in (("competencia_desde", cfg.get("competencia_desde")), ("competencia_ate", cfg.get("competencia_ate"))):
        if v is not None and not gov.COMPETENCIA.fullmatch(str(v)):
            problemas.append(f"Vigência ({k}) inválida: use AAAA-MM.")
    if not cfg.get("competencia_desde"):
        problemas.append("Vigência: informe a competência inicial (AAAA-MM).")
    return problemas


def validar_politica_folha(pf: dict, cfg: dict) -> list:
    problemas = []
    if pf.get("regra") != "MANTER_ULTIMO_LIQUIDO":
        problemas.append("Regra da folha: somente MANTER_ULTIMO_LIQUIDO (manter em aberto o líquido da última competência da folha).")
    if pf.get("conta") != "PRO_LABORE" or not (cfg.get("contas") or {}).get("PRO_LABORE"):
        problemas.append("Política da folha exige a conta Pró-labore a Pagar definida na configuração.")
    d = pf.get("data_lancamento") or {}
    if d.get("politica") not in POLITICAS_DATA_FOLHA:
        problemas.append("Data do lançamento da regularização da folha não definida (ULTIMO_DIA_COMPETENCIA ou DATA_FIXA).")
    elif d.get("politica") == "DATA_FIXA":
        try:
            dt.date.fromisoformat(str(d.get("data")))
        except ValueError:
            problemas.append("DATA_FIXA exige a data (AAAA-MM-DD).")
    if not pf.get("competencia_desde") or not gov.COMPETENCIA.fullmatch(str(pf.get("competencia_desde"))):
        problemas.append("Vigência da política da folha: informe a competência inicial (AAAA-MM).")
    if pf.get("competencia_ate") is not None and not gov.COMPETENCIA.fullmatch(str(pf.get("competencia_ate"))):
        problemas.append("Vigência final da política da folha inválida (AAAA-MM).")
    if pf.get("data_lancamento", {}).get("politica") == "DATA_FIXA" and pf.get("competencia_ate") != pf.get("competencia_desde"):
        problemas.append("DATA_FIXA vale para UMA competência: informe competência inicial = final.")
    return problemas


# ---------------------------------------------------------------- gravação (sempre PROPOSTA) e confirmação (só Coordenador)
def _preservar(base: Path) -> None:
    p = caminho(base)
    if not p.is_file():
        return
    (base / "VERSOES").mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        copia = base / "VERSOES" / f"REGRAS-CAIXINHA-{dt.datetime.now():%Y%m%d-%H%M%S}-{n:03d}.json"
        try:
            with open(copia, "xb") as f:
                f.write(p.read_bytes())
            return
        except FileExistsError:
            n += 1


def _gravar(base: Path, dados: dict) -> None:
    import secrets
    p = caminho(base)
    tmp = p.with_name(p.name + "." + secrets.token_hex(4) + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


CAMPOS_CONFIG = ("contas", "tributos", "politica_datas", "criterios_baixa", "competencia_desde", "competencia_ate")
CAMPOS_FOLHA = ("regra", "conta", "data_lancamento", "competencia_desde", "competencia_ate")


def salvar_proposta(base, empresa: str, cnpj: str, plano: list, configuracao: dict = None, politica_folha: dict = None,
                    origem: str = "Supervisor Contábil (tela Conciliação Caixinha)") -> dict:
    """Grava uma NOVA VERSÃO como PROPOSTA (nada é aprovado aqui). Seção sem mudança de conteúdo mantém a situação/confirmação.
    Versão anterior do arquivo preservada em VERSOES/."""
    base = Path(base)
    atual = ler(base) or {"contrato": CONTRATO, "empresa": empresa, "cnpj": cnpj, "versao": 0, "historico": []}
    if atual.get("empresa") != empresa or re.sub(r"\D", "", str(atual.get("cnpj"))) != re.sub(r"\D", "", str(cnpj)):
        raise ValueError("REGRAS-CAIXINHA.json pertence a outra empresa/CNPJ; nada foi gravado.")
    novo = json.loads(json.dumps(atual))
    mudou = []
    for chave, recebido, campos, validar in (("CONFIGURACAO", configuracao, CAMPOS_CONFIG, None), ("POLITICA_FOLHA", politica_folha, CAMPOS_FOLHA, None)):
        if recebido is None:
            continue
        if not isinstance(recebido, dict) or set(recebido) - set(campos):
            raise ValueError(f"{chave}: campos não permitidos.")
        secao = "configuracao" if chave == "CONFIGURACAO" else "politica_folha"
        regra = {k: recebido.get(k) for k in campos}
        if chave == "CONFIGURACAO":
            regra["contas"] = {str(k): (None if v in (None, "") else str(v)) for k, v in (regra.get("contas") or {}).items()}
            problemas = validar_configuracao(regra, plano)
        else:
            problemas = validar_politica_folha(regra, (novo.get("configuracao") or {}))
        if problemas:
            raise ValueError(f"{chave} não salva: " + " ".join(problemas))
        anterior = atual.get(secao) or {}
        if anterior and conteudo_sha(anterior) == conteudo_sha(regra):
            continue
        regra.update(situacao="PROPOSTA", origem=origem, versao=int(anterior.get("versao") or 0) + 1, atualizada_em=agora(),
                     atualizada_por=RESPONSAVEL, historico_situacoes=list(anterior.get("historico_situacoes") or []))
        regra["historico_situacoes"].append({"de": anterior.get("situacao"), "para": "PROPOSTA", "em": regra["atualizada_em"],
                                             "motivo": "nova versão do conteúdo"})
        regra["conteudo_sha256"] = conteudo_sha(regra)
        novo[secao] = regra
        mudou.append(chave)
    if not mudou:
        return {"resultado": "SEM_ALTERACAO", "regras": atual}
    novo["versao"] = int(atual.get("versao") or 0) + 1
    novo["historico"] = list(atual.get("historico") or []) + [{"versao": novo["versao"], "em": agora(), "por": RESPONSAVEL,
                                                                "evento": "PROPOSTA: " + ", ".join(mudou)}]
    _preservar(base)
    _gravar(base, novo)
    return {"resultado": "PROPOSTA_GRAVADA", "alteradas": mudou, "regras": novo,
            "aviso": "Regras em PROPOSTA não são aplicadas: confirme com a frase " + " e ".join(
                f'"{gov.frase(AREA, empresa, c)}"' for c in mudou) + "."}


def aprovar(base, empresa: str, chave: str, frase: str) -> dict:
    """Confirmação EXPLÍCITA (chamada SOMENTE pelo comando do Coordenador 'aprovar-regra-caixinha'). Vincula versão e sha256."""
    base = Path(base)
    if chave not in CHAVES:
        raise ValueError(f"Chave inválida; use {', '.join(CHAVES)}.")
    esperado = gov.frase(AREA, empresa, chave)
    if (frase or "").strip() != esperado:
        raise PermissionError(f'Confirmação exige a frase exata: "{esperado}".')
    dados = ler(base)
    if dados is None or dados.get("empresa") != empresa:
        raise ValueError("REGRAS-CAIXINHA.json ausente ou de outra empresa: nada a confirmar.")
    secao = "configuracao" if chave == "CONFIGURACAO" else "politica_folha"
    regra = dados.get(secao)
    if not isinstance(regra, dict):
        raise ValueError(f"{chave} não definida: salve a proposta antes de confirmar.")
    if str(regra.get("situacao")).upper() != "PROPOSTA":
        raise ValueError(f"{chave} está em {regra.get('situacao')}; só PROPOSTA pode ser confirmada.")
    if regra.get("conteudo_sha256") != conteudo_sha(regra):
        raise ValueError(f"{chave}: conteúdo alterado fora do aplicativo (sha256 não confere); salve uma nova proposta.")
    if chave == "POLITICA_FOLHA":
        cfg = dados.get("configuracao") or {}
        if not (cfg.get("contas") or {}).get("PRO_LABORE"):
            raise ValueError("POLITICA_FOLHA exige a conta Pró-labore definida na configuração.")
    momento = agora()
    _preservar(base)
    regra["historico_situacoes"] = list(regra.get("historico_situacoes") or []) + [{"de": "PROPOSTA", "para": "APROVADA", "em": momento}]
    regra.update(situacao="APROVADA", confirmacao={"frase": esperado, "em": momento, "por": RESPONSAVEL, "versao": regra.get("versao"),
                                                   "conteudo_sha256": regra["conteudo_sha256"]})
    dados["historico"] = list(dados.get("historico") or []) + [{"versao": dados.get("versao"), "em": momento, "por": RESPONSAVEL,
                                                                "evento": f"APROVADA: {chave} v{regra.get('versao')}"}]
    _gravar(base, dados)
    return {"resultado": "REGRA_CONFIRMADA", "empresa": empresa, "area": AREA, "chave": chave, "versao": regra.get("versao"),
            "aviso": "Conciliações Caixinha e aprovações que usaram a versão anterior ficam desatualizadas (rever as etapas indicadas)."}


# ---------------------------------------------------------------- avaliação (o que vale para a competência)
def avaliar(base, empresa: str, cnpjs, competencia: str) -> dict:
    """{'configuracao': {...}, 'politica_folha': {...}, 'contas': {chave: codigo} só se a configuração for aplicável, 'problemas'}.
    Nada é aplicado sem APROVADA (ou TESTE_FICTICIO em empresa fictícia), vigente e com conteúdo igual ao confirmado."""
    base = Path(base)
    saida = {"arquivo": ARQUIVO, "configuracao": None, "politica_folha": None, "contas": {}, "tributos": [], "problemas": [],
             "versao": None, "sha256": None}
    try:
        dados = ler(base)
    except (OSError, ValueError) as exc:
        saida["problemas"].append(f"Regras da rotina Caixinha ilegíveis: {exc}")
        return saida
    if dados is None:
        saida["problemas"].append("Regras da rotina Caixinha não definidas para esta empresa (REGRAS-CAIXINHA.json ausente).")
        return saida
    saida["versao"] = dados.get("versao")
    saida["sha256"] = hashlib.sha256(caminho(base).read_bytes()).hexdigest()
    digs = {re.sub(r"\D", "", str(c)) for c in (cnpjs or [])}
    if dados.get("empresa") != empresa or re.sub(r"\D", "", str(dados.get("cnpj"))) not in digs:
        saida["problemas"].append("REGRAS-CAIXINHA.json não corresponde à empresa/CNPJ selecionados: regras NÃO aplicadas.")
        return saida
    for chave, secao in (("CONFIGURACAO", "configuracao"), ("POLITICA_FOLHA", "politica_folha")):
        regra = dados.get(secao)
        if not isinstance(regra, dict):
            saida[secao] = {"aplicavel": False, "motivo": f"{chave} não definida.", "governanca": None, "frase": gov.frase(AREA, empresa, chave)}
            continue
        r = gov.avaliar(regra, AREA, empresa, chave, competencia, base)
        if r["aplicavel"] and regra.get("conteudo_sha256") != conteudo_sha(regra):
            r = dict(r, aplicavel=False, motivo=f"{AREA}/{chave}: conteúdo diferente do registrado (sha256); não aplicada.")
        c = regra.get("confirmacao") or {}
        if r["aplicavel"] and str(regra.get("situacao")).upper() == "APROVADA" and (
                c.get("versao") != regra.get("versao") or c.get("conteudo_sha256") != regra.get("conteudo_sha256")):
            r = dict(r, aplicavel=False, motivo=f"{AREA}/{chave}: confirmação de outra versão do conteúdo; reconfirme a versão atual.")
        saida[secao] = dict(r, versao=regra.get("versao"), situacao=regra.get("situacao"), frase=gov.frase(AREA, empresa, chave))
        if not r["aplicavel"]:
            saida["problemas"].append(r["motivo"])
    cfg = dados.get("configuracao") or {}
    if (saida["configuracao"] or {}).get("aplicavel"):
        saida["contas"] = {k: str(v) for k, v in (cfg.get("contas") or {}).items() if v not in (None, "")}
        saida["tributos"] = cfg.get("tributos") or []
        saida["politica_datas"] = cfg.get("politica_datas") or {}
        saida["criterios_baixa"] = dict(CRITERIOS_PADRAO, **(cfg.get("criterios_baixa") or {}))
    if (saida["politica_folha"] or {}).get("aplicavel"):
        saida["folha"] = {k: (dados["politica_folha"]).get(k) for k in CAMPOS_FOLHA}
    return saida


def proposta_inicial(empresa: str, plano: list, competencia: str) -> dict:
    """Formulário inicial (NÃO gravado): contas sugeridas pela descrição + vínculos tributários sugeridos + políticas vazias."""
    sug = sugerir_contas(plano)
    return {"configuracao": {"contas": {k: v["sugerida"] for k, v in sug.items()}, "tributos": json.loads(json.dumps(TRIBUTOS_SUGERIDOS)),
                             "politica_datas": {"tributos": None}, "criterios_baixa": dict(CRITERIOS_PADRAO),
                             "competencia_desde": competencia, "competencia_ate": None},
            "politica_folha": {"regra": "MANTER_ULTIMO_LIQUIDO", "conta": "PRO_LABORE", "data_lancamento": {"politica": None},
                               "competencia_desde": competencia, "competencia_ate": None},
            "sugestoes": sug, "aviso": "Sugestões pela descrição do plano desta empresa: confira cada conta. Nada é gravado nem aprovado "
                                       "sem a sua confirmação."}
