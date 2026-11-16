"""Leitura do BALANCETE de encerramento (mês anterior) para a base inicial da empresa. Somente leitura, código local.

- PDF do Domínio: colunas reconhecidas pela POSIÇÃO do cabeçalho de cada página (pypdfium2, caixas dos caracteres), não pela
  ordem do texto extraído (que mistura descrição, saldo atual e saldo anterior). Trata cabeçalhos repetidos, mudança de página,
  descrições quebradas, texto auxiliar duplicado fora da coluna de descrição e rodapés.
- Planilha (XLSX/XLS) ou CSV: cabeçalho reconhecido por sinônimos em qualquer linha das primeiras 30.
Verificações por conta: saldo anterior + débitos − créditos = saldo atual (exato, Decimal). Saldo zero sem D/C fica sem natureza.
Tipo sintética/analítica, grupo contábil e elegibilidade para composição no book pela ÁRVORE do plano (plano_hierarquia):
com descendentes = sintética; folha = analítica; grupo herdado das contas principais. O resultado é "contas extraídas do balancete" — filtros de emissão podem omitir contas.
"""
import io
import re
import unicodedata
from decimal import Decimal

PEDACO = re.compile(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}[DC]?")
VALOR = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?:[DC])?$")
CLASSIF = re.compile(r"^\d+(?:\.\d+)*$")
GRUPOS_POR_NOME = (("PATRIMONIO LIQUIDO", "PATRIMONIO_LIQUIDO"), ("ATIVO", "ATIVO"), ("PASSIVO", "PASSIVO"), ("RECEITA", "RECEITA"),
                   ("CUSTO", "CUSTO"), ("DESPESA", "DESPESA"))


def chave(t) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().upper()).strip()


def valor(texto):
    """'29.001.040,70D' → (Decimal ASSINADO devedor positivo, 'D'); '0,00' → (0, None). Inválido → (None, None)."""
    t = str(texto or "").strip().replace(" ", "")
    if not VALOR.fullmatch(t):
        return None, None
    nat = t[-1] if t[-1] in "DC" else None
    numero = Decimal(t.rstrip("DC").replace(".", "").replace(",", "."))
    if nat == "C":
        numero = -numero
    return numero, nat


def numero_tabela(v):
    """Célula de planilha: número ou texto com D/C. Número sem D/C = ASSINADO como informado (natureza não presumida)."""
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        d = Decimal(str(v))
        return d, None
    return valor(v)


# ---------------------------------------------------------------- PDF do Domínio (posições)
def _palavras(pagina):
    tp = pagina.get_textpage()
    palavras, atual = [], None
    for i in range(tp.count_chars()):
        ch = tp.get_text_range(i, 1)
        if not ch or ch in " \r\n\t":
            atual = None
            continue
        e, b, d, t = tp.get_charbox(i, loose=True)   # caixa pelo avanço do glifo: letras da mesma palavra encostam
        if atual and abs(atual["y"] - b) < 1.5 and e - atual["x1"] < 1.2:
            atual["t"] += ch
            atual["x1"] = d
            atual["c"].append((ch, e, d))
        else:
            atual = {"t": ch, "x0": e, "x1": d, "y": b, "c": [(ch, e, d)]}
            palavras.append(atual)
    linhas = []
    for p in sorted(palavras, key=lambda p: (-p["y"], p["x0"])):
        if linhas and abs(linhas[-1]["y"] - p["y"]) <= 1.0:
            linhas[-1]["p"].append(p)
        else:
            linhas.append({"y": p["y"], "p": [p]})
    # pontuação isolada (hífen, ponto, barra têm base diferente das letras): volta para a linha de texto mais próxima (até 3 pt)
    com_texto = [l for l in linhas if any(ch.isalnum() for p in l["p"] for ch in p["t"]) and sum(len(p["t"]) for p in l["p"]) > 2]
    for l in [l for l in linhas if l not in com_texto]:
        perto = min(com_texto, key=lambda x: abs(x["y"] - l["y"]), default=None)
        if perto is not None and abs(perto["y"] - l["y"]) <= 3:
            perto["p"].extend(l["p"])
            l["p"] = []
    linhas = [l for l in linhas if l["p"]]
    for l in linhas:
        l["p"].sort(key=lambda p: p["x0"])
        l["texto"] = " ".join(p["t"] for p in l["p"])
    return linhas


def _cabecalho(linhas):
    """Colunas pela posição das palavras do cabeçalho: Código, Classificação, Descrição, Saldo Anterior, Débito, Crédito, Saldo Atual."""
    for i, l in enumerate(linhas):
        k = [chave(p["t"]) for p in l["p"]]
        if "CODIGO" in k and any(x.startswith("CLASSIFICA") for x in k) and "DEBITO" in k and "CREDITO" in k:
            ps = {chave(p["t"]): p for p in l["p"]}
            saldos = sorted([p for p in l["p"] if chave(p["t"]) == "SALDO"], key=lambda p: p["x0"])
            ant = next((p for p in l["p"] if chave(p["t"]) == "ANTERIOR"), None)
            atu = next((p for p in l["p"] if chave(p["t"]) == "ATUAL"), None)
            desc = next((p for p in l["p"] if chave(p["t"]).startswith("DESCRI")), None)
            clas = next(p for p in l["p"] if chave(p["t"]).startswith("CLASSIFICA"))
            if not (ant and atu and desc and len(saldos) == 2):
                continue
            return i, {"sem_classificacao": False,"codigo_ate": clas["x0"] - 0.5, "classif_de": clas["x0"] - 1.5, "descricao_de": desc["x0"] - 1.5,
                       "valores_de": saldos[0]["x0"] - 40,
                       "direitas": {"saldo_anterior": ant["x1"], "debitos": ps["DEBITO"]["x1"], "creditos": ps["CREDITO"]["x1"],
                                    "saldo_atual": atu["x1"]}}
        # Variante do Domínio SEM coluna "Classificação" (Código · Descrição da conta · Saldo Anterior · Débito · Crédito · Saldo Atual):
        # a hierarquia vem do RECUO da descrição; a classificação é DERIVADA (sinalizada em cada conta), nunca inventada como oficial.
        if "CODIGO" in k and not any(x.startswith("CLASSIFICA") for x in k) and "DEBITO" in k and "CREDITO" in k:
            ps = {chave(p["t"]): p for p in l["p"]}
            saldos = sorted([p for p in l["p"] if chave(p["t"]) == "SALDO"], key=lambda p: p["x0"])
            ant = next((p for p in l["p"] if chave(p["t"]) == "ANTERIOR"), None)
            atu = next((p for p in l["p"] if chave(p["t"]) == "ATUAL"), None)
            desc = next((p for p in l["p"] if chave(p["t"]).startswith("DESCRI")), None)
            if not (ant and atu and desc and len(saldos) == 2):
                continue
            return i, {"sem_classificacao": True, "codigo_ate": desc["x0"] - 1, "classif_de": desc["x0"] - 1.5,
                       "descricao_de": desc["x0"] - 1.5, "valores_de": saldos[0]["x0"] - 40,
                       "direitas": {"saldo_anterior": ant["x1"], "debitos": ps["DEBITO"]["x1"], "creditos": ps["CREDITO"]["x1"],
                                    "saldo_atual": atu["x1"]}}
    return None, None


def _classificacao_por_recuo(pilha: list, recuo: float, passo: float = 5.0) -> str:
    """Classificação DERIVADA do recuo da descrição (relatório sem a coluna): nível = posição do recuo entre os já vistos."""
    while pilha and pilha[-1]["recuo"] > recuo + 1.5:
        pilha.pop()
    if pilha and abs(pilha[-1]["recuo"] - recuo) <= 1.5:
        pilha[-1]["n"] += 1
    else:
        pilha.append({"recuo": recuo, "n": 1})
    return ".".join(str(x["n"]) for x in pilha)


def _valores_da_zona(palavras):
    """Zona numérica da linha caractere a caractere: espaçamento pode separar "4" de ".195,74C" ou colar valores vizinhos
    ("113.186,20D113.186,20D"). Os valores são separados pela ESTRUTURA (2 decimais, D/C opcional); cada um recebe a borda
    direita do seu último caractere (é ela que indica a coluna). Sobra que não forma valor é devolvida como texto inválido."""
    chars = sorted((c for p in palavras for c in p["c"]), key=lambda c: c[1])
    texto = "".join(c[0] for c in chars)
    saida, fim_ant = [], 0
    for m in PEDACO.finditer(texto):
        if texto[fim_ant:m.start()].strip():
            saida.append({"t": texto[fim_ant:m.start()], "x0": chars[fim_ant][1], "x1": chars[m.start() - 1][2]})
        saida.append({"t": m.group(0), "x0": chars[m.start()][1], "x1": chars[m.end() - 1][2]})
        fim_ant = m.end()
    if texto[fim_ant:].strip():
        saida.append({"t": texto[fim_ant:], "x0": chars[fim_ant][1], "x1": chars[-1][2]})
    return saida


def _meta_texto(dados: bytes) -> dict:
    """Cabeçalho do relatório (empresa, CNPJ, período, abrangência) pelo texto da 1ª página (pypdf)."""
    from pypdf import PdfReader
    t = PdfReader(io.BytesIO(dados)).pages[0].extract_text() or ""
    meta = {}
    m = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", t)
    if m:
        meta["cnpj"] = m.group(0)
    m = re.search(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", t)
    if m:
        meta["periodo"] = {"inicio": _iso(m.group(1)), "fim": _iso(m.group(2))}
    m = re.search(r"CONSOLIDADO\s*\(\s*Empresas?:\s*([\d,\s]+)\)", t, re.I)
    meta["abrangencia"] = ({"tipo": "CONSOLIDADO", "estabelecimentos": [x.strip() for x in m.group(1).split(",") if x.strip()]} if m
                           else {"tipo": "NAO_INFORMADA", "estabelecimentos": []})
    return meta


def ler_pdf(dados: bytes) -> dict:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(io.BytesIO(dados))
    meta_texto = _meta_texto(dados)
    contas, ignoradas, limites, meta = [], {"cabecalho_repetido": 0, "texto_auxiliar": 0, "rodape_ou_titulo": 0}, [], {}
    for n in range(len(pdf)):
        linhas = _palavras(pdf[n])
        if "empresa" not in meta:
            linha_emp = next((l for l in linhas[:6] if l["p"] and chave(l["p"][0]["t"]) == "EMPRESA:"), None)
            if linha_emp:
                fim = next((p["x0"] for p in linha_emp["p"] if chave(p["t"]).startswith("FOLHA")), 10 ** 6)
                meta["empresa"] = " ".join(p["t"] for p in linha_emp["p"][1:] if p["x0"] < fim).strip()
        i_cab, col = _cabecalho(linhas)
        if col is None:
            limites.append(f"Página {n + 1}: cabeçalho de colunas não reconhecido; página não lida.")
            continue
        if n > 0:
            ignoradas["cabecalho_repetido"] += 1
        ignoradas["rodape_ou_titulo"] += i_cab
        anterior = None
        if col.get("sem_classificacao") and "_pilha" not in meta:
            meta["_pilha"] = []
        for l in linhas[i_cab + 1:]:
            cod = [p for p in l["p"] if p["x1"] <= col["codigo_ate"] and p["t"].isdigit()]
            if col.get("sem_classificacao"):
                desc = [p for p in l["p"] if col["descricao_de"] <= p["x0"] < col["valores_de"]]
                nums = _valores_da_zona([p for p in l["p"] if p["x0"] >= col["valores_de"]])
                codigo = "".join(p["t"] for p in cod)
                if codigo.isdigit() and desc and nums:
                    classificacao = _classificacao_por_recuo(meta["_pilha"], desc[0]["x0"])
                    vals, ok = {}, True
                    for p in nums:
                        alvo = min(col["direitas"], key=lambda k: abs(col["direitas"][k] - p["x1"]))
                        if abs(col["direitas"][alvo] - p["x1"]) > 8 or alvo in vals:
                            ok = False
                            continue
                        vals[alvo] = p["t"]
                    conta = _conta(codigo, classificacao, " ".join(p["t"] for p in desc), vals, f"p.{n + 1}")
                    conta["classificacao_derivada"] = True
                    conta.setdefault("observacoes", []).append("classificação derivada do recuo da descrição (relatório sem a coluna "
                                                               "Classificação)")
                    if not ok:
                        conta["problemas"].append("valor fora das colunas reconhecidas; conferir no relatório")
                    contas.append(conta)
                    anterior = conta
                elif l["p"][0]["x0"] < col["descricao_de"] and not codigo.isdigit():
                    ignoradas["texto_auxiliar"] += 1
                else:
                    ignoradas["rodape_ou_titulo"] += 1
                continue
            cla = [p for p in l["p"] if col["classif_de"] <= p["x0"] < col["descricao_de"] and re.fullmatch(r"[\d.]+", p["t"])]
            desc = [p for p in l["p"] if col["descricao_de"] <= p["x0"] < col["valores_de"]]
            # pontuação solta sobreposta a uma palavra vem de outra camada de texto (descrição auxiliar duplicada): descartada
            desc = [p for p in desc if any(ch.isalnum() for ch in p["t"])
                    or not any(q is not p and any(ch.isalnum() for ch in q["t"]) and q["x0"] < p["x1"] and p["x0"] < q["x1"] for q in desc)]
            nums = _valores_da_zona([p for p in l["p"] if p["x0"] >= col["valores_de"]])
            classificacao = "".join(p["t"] for p in cla)
            codigo = "".join(p["t"] for p in cod)
            if codigo.isdigit() and CLASSIF.fullmatch(classificacao):
                vals, ok = {}, True
                for p in nums:
                    alvo = min(col["direitas"], key=lambda k: abs(col["direitas"][k] - p["x1"]))
                    if abs(col["direitas"][alvo] - p["x1"]) > 8 or alvo in vals:
                        ok = False
                        continue
                    vals[alvo] = p["t"]
                conta = _conta(codigo, classificacao, " ".join(p["t"] for p in desc), vals, f"p.{n + 1}")
                if not ok:
                    conta["problemas"].append("valor fora das colunas reconhecidas; conferir no relatório")
                contas.append(conta)
                anterior = conta
                continue
            if not cod and not cla and desc and not nums and anterior and l["p"][0]["x0"] >= col["descricao_de"]:
                anterior["descricao"] = (anterior["descricao"] + " " + " ".join(p["t"] for p in desc)).strip()   # descrição quebrada
                anterior.setdefault("observacoes", []).append("descrição continuada na linha seguinte")
                continue
            if l["p"][0]["x0"] < col["classif_de"] and not codigo.isdigit():
                ignoradas["texto_auxiliar"] += 1        # texto duplicado/auxiliar fora das colunas (não é conta)
            else:
                ignoradas["rodape_ou_titulo"] += 1
    for c in contas:
        c.pop("_y", None)
    if meta.pop("_pilha", None) is not None:
        limites.append("Relatório sem a coluna Classificação: hierarquia derivada do recuo das descrições (conferir o plano da empresa).")
    meta.update(meta_texto)
    return {"formato": "PDF_DOMINIO_BALANCETE", "meta": meta, "contas": contas, "linhas_ignoradas": ignoradas, "limites": limites}


def _iso(d):
    dd, mm, aa = d.split("/")
    return f"{aa}-{mm}-{dd}"


def _conta(codigo, classificacao, descricao, vals, origem):
    descricao = re.sub(r"\(\s*-\s*\)", "(-)", descricao)
    descricao = re.sub(r"(\d)\s+([ºª])", r"\1\2", descricao)
    c = {"codigo": codigo, "classificacao": classificacao, "descricao": descricao.strip(), "origem": origem, "problemas": [], "_y": None}
    for k in ("saldo_anterior", "debitos", "creditos", "saldo_atual"):
        v, nat = valor(vals.get(k))
        if k in ("debitos", "creditos"):
            if v is not None and (nat or v < 0):
                c["problemas"].append(f"{k} com sinal/natureza inesperado ({vals.get(k)})")
            c[k] = None if v is None else f"{abs(v):.2f}"
        else:
            c[k] = None if v is None else f"{v:.2f}"
            c[k.replace("saldo_", "natureza_")] = nat
        if vals.get(k) is None:
            c["problemas"].append(f"{k} ausente")
    return c


# ---------------------------------------------------------------- planilha / CSV
SINONIMOS = {"codigo": ("CODIGO", "COD", "CODIGO REDUZIDO", "REDUZIDO", "CONTA REDUZIDA"),
             "classificacao": ("CLASSIFICACAO", "CONTA", "CLASSIF"),
             "descricao": ("DESCRICAO", "DESCRICAO DA CONTA", "NOME DA CONTA", "NOME"),
             "saldo_anterior": ("SALDO ANTERIOR", "SALDO INICIAL"), "debitos": ("DEBITO", "DEBITOS"),
             "creditos": ("CREDITO", "CREDITOS"), "saldo_atual": ("SALDO ATUAL", "SALDO FINAL")}


def ler_tabela(linhas: list) -> dict:
    for i, l in enumerate(linhas[:30]):
        k = [chave(x) for x in l]
        mapa = {}
        for campo, sins in SINONIMOS.items():
            pos = [j for j, x in enumerate(k) if x in sins]
            if pos:
                mapa[campo] = pos[0]
        if {"classificacao", "descricao", "saldo_atual", "debitos", "creditos"} <= set(mapa):
            break
    else:
        return {"formato": "TABELA", "meta": {}, "contas": [], "linhas_ignoradas": {}, "limites": ["Cabeçalho do balancete não reconhecido "
                "(exige classificação, descrição, débito, crédito e saldo atual)."]}
    contas, ignoradas = [], 0
    for n, l in enumerate(linhas[i + 1:], i + 2):
        get = lambda c: l[mapa[c]] if c in mapa and mapa[c] < len(l) else None  # noqa: E731
        classificacao = str(get("classificacao") or "").strip()
        if not CLASSIF.fullmatch(classificacao):
            ignoradas += 1
            continue
        codigo = re.sub(r"\D", "", str(get("codigo") or ""))
        c = {"codigo": codigo or None, "classificacao": classificacao, "descricao": str(get("descricao") or "").strip(),
             "origem": f"linha {n}", "problemas": [] if codigo else ["código reduzido ausente"]}
        for k in ("saldo_anterior", "debitos", "creditos", "saldo_atual"):
            v, nat = numero_tabela(get(k)) if get(k) not in (None, "") else (None, None)
            c[k] = None if v is None else f"{(abs(v) if k in ('debitos', 'creditos') else v):.2f}"
            if k.startswith("saldo_"):
                c[k.replace("saldo_", "natureza_")] = nat or ("D" if v and v > 0 else "C" if v and v < 0 else None)
                if v is not None and nat is None and v != 0:
                    c["problemas"].append(f"{k}: natureza D/C não informada; sinal da planilha usado como informado")
        contas.append(c)
    return {"formato": "TABELA", "meta": {}, "contas": contas, "linhas_ignoradas": {"fora_do_padrao": ignoradas}, "limites": []}


# ---------------------------------------------------------------- estrutura e verificações (qualquer formato)
_DERIVADOS_PROBLEMA = ("classificação ", )
_DERIVADOS_OBSERVACAO = ("conta superior ", "soma das subordinadas")


def analisar(lido: dict) -> dict:
    """Estrutura e verificações do balancete. Tipo (sintética/analítica), grupo contábil, hierarquia e elegibilidade para
    composição no book vêm da árvore do plano (plano_hierarquia — regra geral do sistema). Idempotente: pode ser reaplicada
    sobre uma base já gravada (reanálise) sem duplicar apontamentos."""
    import plano_hierarquia
    contas = lido["contas"]
    for c in contas:                 # apontamentos DERIVADOS são recalculados (os da leitura do arquivo são preservados)
        c["problemas"] = [x for x in c.get("problemas", []) if not (x.startswith(_DERIVADOS_PROBLEMA) and "repetida" in x)]
        c["observacoes"] = [x for x in c.get("observacoes", []) if not x.startswith(_DERIVADOS_OBSERVACAO)]
        if not c["observacoes"]:
            c.pop("observacoes")
    por_class = {}
    for c in contas:
        if c["classificacao"] in por_class:
            c["problemas"].append(f"classificação {c['classificacao']} repetida no relatório")
        por_class.setdefault(c["classificacao"], c)
    codigos = {}
    for c in contas:
        if c.get("codigo"):
            codigos.setdefault(c["codigo"], []).append(c["classificacao"])
    duvidas = [f"Código reduzido {k} repetido nas classificações {', '.join(v)}." for k, v in codigos.items() if len(v) > 1]
    arvore = plano_hierarquia.anotar(contas)
    for c in contas:
        # verificação aritmética da linha (vale para TODAS as contas, inclusive sintéticas)
        try:
            ant, deb, cre, atu = (Decimal(c[x]) for x in ("saldo_anterior", "debitos", "creditos", "saldo_atual"))
            c["confere"] = ant + deb - cre == atu
            if not c["confere"]:
                msg = f"saldo anterior + débitos − créditos ({ant + deb - cre:.2f}) ≠ saldo atual ({atu:.2f})"
                if msg not in c["problemas"]:
                    c["problemas"].append(msg)
        except (TypeError, ValueError, ArithmeticError):
            c["confere"] = None
        n = c.get("classificacao_normalizada")
        if n and "." in n and not c.get("superior"):
            c.setdefault("observacoes", []).append(f"conta superior {n.rsplit('.', 1)[0]} não consta no relatório (filtro de emissão?)")
    # hierarquia: soma das filhas DIRETAS presentes = conta sintética (validação de saldo; não é exigência de composição)
    filhas = {}
    for idx, x in arvore["contas"].items():
        if x["superior"] is not None:
            filhas.setdefault(x["superior"], []).append(contas[idx])
    for idx, fs in filhas.items():
        c = contas[idx]
        if c.get("saldo_atual") is not None and all(f.get("saldo_atual") is not None for f in fs):
            soma = sum(Decimal(f["saldo_atual"]) for f in fs)
            if soma != Decimal(c["saldo_atual"]):
                c.setdefault("observacoes", []).append(f"soma das subordinadas presentes ({soma:.2f}) ≠ saldo da conta ({c['saldo_atual']}); "
                                                      "pode haver conta omitida pelo filtro do relatório")
    totais = {"contas_extraidas": len(contas), "analiticas": sum(c["tipo"] == "ANALITICA" for c in contas),
              "sinteticas": sum(c["tipo"] == "SINTETICA" for c in contas), "tipo_indefinido": sum(not c["tipo"] for c in contas),
              "linhas_que_nao_conferem": sum(c.get("confere") is False for c in contas)}
    # soma geral SÓ das analíticas (nunca soma sintética + filhas)
    an = [c for c in contas if c["tipo"] == "ANALITICA" and c.get("saldo_atual") is not None]
    totais["soma_saldos_analiticas"] = f"{sum((Decimal(c['saldo_atual']) for c in an), Decimal('0')):.2f}"
    # ramos sem grupo identificável: o Supervisor confirma só esses (as demais contas são classificadas automaticamente)
    ramos = [{"classificacao": r["classificacao"], "descricao": r["descricao"], "grupo_sugerido": ""} for r in arvore["resumo"]["ramos_para_confirmar"]]
    return dict(lido, contas=contas, duvidas=duvidas, ancoras_grupo=ramos, analise_plano=arvore["resumo"],
                analise_versao=plano_hierarquia.VERSAO_ANALISE, totais=totais,
                aviso="Contas EXTRAÍDAS do balancete: filtros de emissão podem omitir contas; não é necessariamente o plano completo.")


def ler(nome: str, dados: bytes, linhas_tabela=None) -> dict:
    if nome.lower().endswith(".pdf"):
        return analisar(ler_pdf(dados))
    if linhas_tabela is None:
        raise ValueError("Formato não suportado para o balancete.")
    return analisar(ler_tabela(linhas_tabela))
