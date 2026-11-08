"""Sugestões e confirmação das referências contábeis por área.

As sugestões são somente uma prévia derivada do plano da própria empresa. Nenhuma
referência é gravada como regra aplicável sem confirmação explícita do Supervisor.
"""
import datetime as dt
import json
import re
from pathlib import Path

AREAS = {
    "DP": ("Departamento Pessoal", "REGRAS-DP.json"),
    "FISCAL": ("Fiscal", "REGRAS-FISCAIS.json"),
    "CONCILIACAO": ("Conciliação", "REGRAS-CONCILIACAO.json"),
}
DP = {
    "FOLHA_PROVENTOS": ["salário", "salarios", "ordenado", "pró-labore", "pro labore"],
    "RETENCAO_INSS": ["inss", "inss a recolher"], "ENCARGO_INSS_EMPRESA": ["inss patronal", "encargos sociais"],
    "ENCARGO_FGTS": ["fgts"], "PROVISAO_FERIAS": ["provisão de férias", "provisao ferias"],
    "PROVISAO_13": ["provisão de 13", "provisao 13", "13º salário", "13 salario"],
    "BENEFICIOS": ["benefício", "vale transporte", "vale refeição", "vale refeicao", "adiantamento salarial"],
}
FISCAL = {
    "ICMS_RECUPERAR": ["icms a recuperar", "icms recuperar"], "ICMS_RECOLHER": ["icms a recolher", "icms recolher"],
    "IPI": ["ipi"], "PIS": ["pis"], "COFINS": ["cofins"], "ISS": ["iss"], "IRPJ": ["irpj"], "CSLL": ["csll"],
    "RETENCOES": ["impostos retidos", "retenções federais", "retencoes federais", "retenções municipais", "retencoes municipais", "retenções previdenciárias"],
}
CONC = {
    "BANCOS": ["banco", "bancos", "conta corrente"], "APLICACOES": ["aplicação", "aplicacoes", "investimento"],
    "CLIENTES": ["cliente", "duplicatas a receber", "contas a receber"], "FORNECEDORES": ["fornecedor", "duplicatas a pagar", "contas a pagar"],
    "EMPRESTIMOS": ["empréstimo", "emprestimo", "financiamento"], "IMPOSTOS": ["imposto", "tributo", "icms", "iss", "pis", "cofins"],
    "ADIANTAMENTOS": ["adiantamento"],
}

def _norm(v):
    import unicodedata
    return " ".join(unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower().split())

def _analiticas(plano):
    pais = {str(c.get("classificacao") or ""): c for c in plano}
    saida = []
    for c in plano:
        tipo = _norm(c.get("tipo"))
        classificacao = str(c.get("classificacao") or "")
        descendente = any(x.startswith(classificacao + ".") for x in pais if x != classificacao and classificacao)
        if tipo in ("analitica", "analitica") or (not descendente and tipo != "sintetica"):
            saida.append(c)
    return saida

def _candidatos(plano, termos):
    termos = [_norm(t) for t in termos]
    candidatos = []
    for c in _analiticas(plano):
        texto = _norm(f"{c.get('descricao')} {c.get('observacao')} {c.get('grupo')}")
        hits = [t for t in termos if t in texto]
        if hits:
            candidatos.append((len(max(hits, key=len)), c))
    candidatos.sort(key=lambda x: (-x[0], str(x[1].get("classificacao") or x[1].get("codigo") or "")))
    return [c for _, c in candidatos]

def sugerir(empresa, plano, competencia):
    resultado = {"empresa": empresa, "competencia": competencia, "gerado_em": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "areas": {}}
    for area, (nome, _) in AREAS.items():
        mapa = DP if area == "DP" else FISCAL if area == "FISCAL" else CONC
        itens = []
        for chave, termos in mapa.items():
            cs = _candidatos(plano, termos)
            # Obrigações fiscais devem preferir PASSIVO; uma conta de resultado com o mesmo nome
            # é evidência insuficiente e não pode virar referência operacional silenciosa.
            if area == "FISCAL" and chave in {"ICMS_RECOLHER", "PIS", "COFINS", "ISS", "IRPJ", "CSLL", "RETENCOES"}:
                passivos = [c for c in cs if _norm(c.get("grupo")) == "passivo"]
                cs = passivos
            if area == "CONCILIACAO":
                cs = [c for c in cs if _norm(c.get("grupo")) in {"ativo", "passivo"}]
            conta = cs[0] if cs else None
            empate = bool(len(cs) > 1 and _norm(cs[0].get("descricao")) and
                          len(_norm(cs[0].get("descricao"))) == len(_norm(cs[1].get("descricao"))))
            if empate: conta = None
            confianca = "ALTA CONFIANÇA" if conta and max(len(_norm(t)) for t in termos) > 5 else "ATENÇÃO" if conta else "PRECISA DE CONFIRMAÇÃO"
            itens.append({"chave": chave, "rotulo": chave.replace("_", " "), "conta": conta and {"codigo": conta.get("codigo"), "classificacao": conta.get("classificacao"), "descricao": conta.get("descricao"), "tipo": conta.get("tipo"), "grupo": conta.get("grupo")}, "candidatas": [{"codigo": c.get("codigo"), "classificacao": c.get("classificacao"), "descricao": c.get("descricao"), "tipo": c.get("tipo"), "grupo": c.get("grupo")} for c in cs[:5]], "confianca": confianca, "status": "SUGERIDA" if conta else "PRECISA_CONFIRMACAO", "origem": "AUTOMATICO"})
        resultado["areas"][area] = {"nome": nome, "itens": itens, "status": "PENDENTE"}
    return resultado

def _salvar(path, obj):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def confirmar(base, sugestao, area, decisoes, competencia, por="Supervisor Contábil"):
    if area not in AREAS or not isinstance(decisoes, list):
        raise ValueError("Área ou referências inválidas.")
    plano = {str(c.get("codigo")): c for c in sugestao.get("plano", [])}
    itens = []
    for item in sugestao["areas"][area]["itens"]:
        decisao = next((x for x in decisoes if x.get("chave") == item["chave"]), {})
        escolha = decisao.get("codigo") if decisao.get("acao") == "CONFIRMAR" else None
        if decisao.get("acao") == "NAO_APLICA":
            if len(str(decisao.get("justificativa") or "").strip()) < 5: raise ValueError("Informe uma justificativa para 'Não se aplica'.")
            itens.append({"chave": item["chave"], "situacao": "APROVADA", "nao_aplicavel": True, "status": "NAO_APLICA", "justificativa": decisao["justificativa"], "origem": "SUPERVISOR", "confirmado_em": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "por": por}); continue
        if escolha and str(escolha) not in plano:
            raise ValueError("A conta escolhida não pertence ao plano desta empresa.")
        conta = plano.get(str(escolha)) if escolha else item.get("conta")
        if not conta: continue
        itens.append({"chave": item["chave"], "situacao": "APROVADA", "debito": conta["codigo"], "credito": conta["codigo"], "conta": conta, "status": "CONFIRMADA", "origem": "SUPERVISOR", "sugestao_original": item.get("conta"), "confirmado_em": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "por": por})
    nome, arquivo = AREAS[area]
    cnpj = ""
    cadastro = (base / "CADASTRO.md")
    if cadastro.exists():
        m = re.search(r"CNPJ[^:]*:\s*([^\n]+)", cadastro.read_text(encoding="utf-8")); cnpj = re.sub(r"\D", "", m.group(1)) if m else ""
    if area == "DP": dados = {"contrato": "REFERENCIAS_DP_V1", "empresa": sugestao["empresa"], "cnpj": cnpj, "competencia_desde": competencia, "referencias": {x["chave"]: x for x in itens}}
    elif area == "FISCAL": dados = {"contrato": "REFERENCIAS_FISCAIS_V1", "empresa": sugestao["empresa"], "cnpj": cnpj, "competencia_desde": competencia, "referencias": {x["chave"]: x for x in itens}}
    else: dados = {"contrato": "EXIGENCIAS_CONCILIACAO_V1", "empresa": sugestao["empresa"], "competencia_desde": competencia, "exigencias": {x["chave"]: x for x in itens}}
    destino = base / arquivo
    if destino.exists():
        historico = base / "VERSOES" / f"{arquivo}-{dt.datetime.now():%Y%m%d-%H%M%S}.json"
        historico.parent.mkdir(parents=True, exist_ok=True)
        historico.write_text(destino.read_text(encoding="utf-8"), encoding="utf-8")
    _salvar(destino, dados)
    return dados
