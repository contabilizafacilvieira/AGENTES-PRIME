"""Leitura do BOOK CONTÁBIL (composições de saldo) do mesmo período do balancete de encerramento. Somente leitura, código local.

- Qualquer quantidade de abas, nomes e posições de cabeçalho: cada aba é classificada pelo CONTEÚDO (cabeçalhos reconhecidos por
  sinônimos em qualquer linha/coluna das primeiras 40 linhas). O nome da aba é só apoio (nunca a única prova da conta).
- Composição: conta (classificação ou código reduzido), data-base, método, itens (data, documento, terceiro, descrição, débito,
  crédito, saldo, observação), total, "saldo conforme balancete", diferença, observações, situação informada e assinaturas.
- Itens separados de totais, cabeçalhos repetidos, assinaturas e textos. Coluna de SALDO ACUMULADO nunca é somada: o saldo da
  composição é recalculado como Σ débitos − Σ créditos (ou Σ valores/saldos POR ITEM quando não há débito/crédito).
- Fórmula × valor armazenado: o valor armazenado na planilha NÃO é tratado como verificado; só fórmulas puramente aritméticas
  (números e + − * / parênteses) são recalculadas aqui. Referências a células, funções, vínculos externos e macros NUNCA são
  executados — são apenas informados.
- Situação ("fecha", "pendente"), nomes e assinaturas do book são INFORMAÇÃO DA FONTE, não aprovações do aplicativo; referência a
  arquivo em EVIDÊNCIAS não prova que o documento foi recebido. HISTÓRICO DE BAIXAS é histórico: nunca gera lançamento.
"""
import ast
import datetime as dt
import io
import operator
import re
import unicodedata
import zipfile
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")
LIMITE_DESCOMPACTADO = 150 * 1024 * 1024
LIMITE_ABAS, LIMITE_LINHAS, LIMITE_COLUNAS = 400, 20000, 60
CLASSIF = re.compile(r"\b\d+(?:\.\d+){1,}\b")


def chave(t) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", str(t if t is not None else "")).encode("ascii", "ignore").decode().upper()).strip()


# ---------------------------------------------------------------- números e fórmulas
def numero(v):
    """Célula → Decimal exato ou None. Aceita número, '1.234,56', '1234.56', '1.234,56 D/C' (C = negativo)."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if not t or t in ("-", "—"):
        return None
    sinal = 1
    if t[-1:] in ("D", "C") and re.search(r"\d", t[:-1] or ""):
        sinal = -1 if t[-1] == "C" else 1
        t = t[:-1]
    if t.startswith("(") and t.endswith(")"):
        sinal, t = -sinal, t[1:-1]
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*,\d+|-?\d+,\d+", t):
        t = t.replace(".", "").replace(",", ".")
    elif not re.fullmatch(r"-?\d+(?:\.\d+)?", t):
        return None
    try:
        return Decimal(t) * sinal
    except InvalidOperation:
        return None


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def avaliar_aritmetica(formula: str):
    """'=12835921.59-5509238.11' → Decimal. Qualquer coisa além de números e + − * / ( ) → None (não executado)."""
    f = str(formula or "").lstrip("=").strip()
    if not f or not re.fullmatch(r"[\d.,+\-*/() ]+", f) or "," in f:
        return None
    try:
        arvore = ast.parse(f, mode="eval")
    except SyntaxError:
        return None

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return Decimal(ast.get_source_segment(f, n) or str(n.value))
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        raise ValueError("expressão não aritmética")
    try:
        return ev(arvore)
    except (ValueError, ArithmeticError, TypeError):
        return None


def data_iso(v):
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    t = str(v or "").strip()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", t)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t)
    return m.group(0) if m else None


def texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    return str(v).strip()


# ---------------------------------------------------------------- célula: valor armazenado + fórmula
class Celula:
    __slots__ = ("v", "f")

    def __init__(self, valor, formula):
        self.v, self.f = valor, formula

    def num(self):
        """(Decimal|None, origem): número literal, fórmula aritmética recalculada, ou valor ARMAZENADO de fórmula não executada."""
        if self.f:
            calc = avaliar_aritmetica(self.f)
            if calc is not None:
                return calc, "FORMULA_ARITMETICA_RECALCULADA"
            arm = numero(self.v)
            return arm, ("VALOR_ARMAZENADO_DE_FORMULA" if arm is not None else "FORMULA_SEM_VALOR_ARMAZENADO")
        n = numero(self.v)
        return n, ("VALOR_DIGITADO" if n is not None else None)


# ---------------------------------------------------------------- reconhecimento de cabeçalhos
COLUNAS_COMPOSICAO = {
    "data": ("DATA", "DATA LANCTO", "DATA LANCAMENTO", "DATA DO LANCAMENTO", "DT", "DATA EMISSAO", "EMISSAO", "DATA DOC", "DATA DOCUMENTO"),
    "vencimento": ("VENCIMENTO", "DATA VENCIMENTO", "VENCTO"),
    "documento": ("NF", "DOCUMENTO", "DOC", "NUMERO", "N DOC", "NOTA", "NOTA FISCAL", "TITULO", "NF/DOC", "NUM DOC", "N DOCUMENTO"),
    "terceiro": ("TERCEIRO", "FORNECEDOR", "CLIENTE", "PARTICIPANTE", "FAVORECIDO", "RAZAO SOCIAL", "NOME", "CREDOR", "DEVEDOR"),
    "descricao": ("DESCRICAO", "HISTORICO", "HISTORICO DO LANCAMENTO", "DESCRICAO DO ITEM", "COMPLEMENTO"),
    "debito": ("DEBITO", "DEBITOS", "VALOR DEBITO", "DEB"),
    "credito": ("CREDITO", "CREDITOS", "VALOR CREDITO", "CRED"),
    "valor": ("VALOR", "VALOR EM ABERTO", "SALDO DO ITEM", "VALOR DO ITEM", "VALOR ORIGINAL"),
    "saldo": ("SALDO", "SALDO ACUMULADO", "SALDO CORRENTE"),
    "observacao": ("OBSERVACAO", "OBSERVACOES", "OBS", "NOTA EXPLICATIVA"),
}
COLUNAS_BALANCETE = {"conta": ("CONTA", "CLASSIFICACAO", "CODIGO"), "descricao": ("DESCRICAO", "NOME"),
                     "saldo_anterior": ("SALDO ANTERIOR", "SALDO INICIAL"), "debito": ("DEBITO", "DEBITOS"),
                     "credito": ("CREDITO", "CREDITOS"), "saldo_atual": ("SALDO ATUAL", "SALDO FINAL")}
COLUNAS_PENDENCIAS = {"conta": ("CONTA",), "tipo": ("TIPO",), "severidade": ("SEVERIDADE", "GRAVIDADE", "PRIORIDADE"),
                      "titulo": ("TITULO", "ASSUNTO", "PENDENCIA"), "detalhe": ("DETALHE", "DESCRICAO"),
                      "texto_original": ("TEXTO ORIGINAL",), "origem": ("ORIGEM",), "situacao": ("SITUACAO", "STATUS")}
COLUNAS_HISTORICO = {"conta": ("CONTA",), "titulo": ("TITULO",), "terceiro": ("TERCEIRO", "FORNECEDOR", "CLIENTE"),
                     "documento": ("DOCUMENTO", "NF"), "valor": ("VALOR BAIXADO", "VALOR"), "regra": ("REGRA",),
                     "justificativa": ("JUSTIFICATIVA",), "historico": ("HISTORICO DO MOVIMENTO", "HISTORICO")}
COLUNAS_EVIDENCIAS = {"conta": ("CONTA",), "conta_analitica": ("CONTA ANALITICA",), "arquivo": ("ARQUIVO", "DOCUMENTO", "EVIDENCIA"),
                      "tipo": ("TIPO RECONHECIDO", "TIPO"), "escopo": ("ESCOPO DECLARADO", "ESCOPO"),
                      "valor": ("VALOR CONFRONTADO", "VALOR"), "data_saldo": ("DATA DO SALDO",), "saldo_documento": ("SALDO NO DOCUMENTO",),
                      "diferenca": ("DIFERENCA",), "veredito": ("VEREDITO", "RESULTADO"), "validada": ("VALIDADA",),
                      "explicacao": ("EXPLICACAO",)}
RODAPES = (("total", ("TOTAL", "TOTAL GERAL", "TOTAIS", "SOMA")),
           ("saldo_conforme_balancete", ("SALDO CONFORME BALANCETE", "SALDO NO BALANCETE", "SALDO CONTABIL", "SALDO DO BALANCETE",
                                         "SALDO CONFORME RAZAO")),
           ("diferenca_herdada", ("DIFERENCA HERDADA", "DIFERENCA ANTERIOR")),
           ("diferenca", ("DIFERENCA",)))
ASSINATURAS = ("PREPARADO POR", "APROVADO POR", "REVISADO POR", "CONFERIDO POR", "ELABORADO POR", "ASSINATURA", "RESPONSAVEL")
METODOS = (("ITENS EM ABERTO", "ITENS_EM_ABERTO"), ("HISTORICO ACUMULADO", "HISTORICO_ACUMULADO"),
           ("POSICAO DE RELATORIO", "POSICAO_DE_RELATORIO"), ("POSICAO DO RELATORIO", "POSICAO_DE_RELATORIO"), ("HIBRIDO", "HIBRIDO"))


def _casar(cab: list, mapa: dict) -> dict:
    """Coluna de cada campo pelo cabeçalho (igualdade após normalização; primeira ocorrência)."""
    k = [chave(x).rstrip(":").strip() for x in cab]
    saida = {}
    for campo, sins in mapa.items():
        for j, x in enumerate(k):
            if x in sins and j not in saida.values():
                saida[campo] = j
                break
    return saida


def _achar_cabecalho(linhas, mapa, exigidos, minimo=3, ate=40):
    for i, l in enumerate(linhas[:ate]):
        m = _casar([c.v for c in l], mapa)
        if set(exigidos) <= set(m) and len(m) >= minimo:
            return i, m
    return None, None


def _rotulo_valor(linhas, rotulos, ate):
    """Procura 'Rótulo:' (na célula) com valor na mesma célula ou na(s) célula(s) à direita, nas linhas antes do cabeçalho."""
    for l in linhas[:ate]:
        for j, c in enumerate(l):
            t = texto(c.v)
            k = chave(t)
            for r in rotulos:
                if k == r or k == r + ":" or k.startswith(r + ":"):
                    resto = t.split(":", 1)[1].strip() if ":" in t else ""
                    if resto:
                        return resto, [texto(x.v) for x in l[j + 1:j + 3] if texto(x.v)]
                    vizinhos = [x.v for x in l[j + 1:] if texto(x.v)]
                    if vizinhos:
                        return vizinhos[0], [texto(x) for x in vizinhos[1:2]]
    return None, []


def _metodo(t):
    k = chave(t)
    if not k or k in ("-", "—", "NAO INFORMADO", "N/A"):
        return "NAO_INFORMADO"
    for nome, cod in METODOS:
        if nome in k:
            return cod
    return "DESCONHECIDO"


# ---------------------------------------------------------------- leitura da pasta de trabalho
def _carregar(dados: bytes, nome: str):
    alertas = []
    ext = nome.lower().rsplit(".", 1)[-1]
    if ext not in ("xlsx", "xlsm", "xls"):
        raise ValueError("Book: envie a planilha em XLSX, XLSM ou XLS.")
    if ext == "xls":
        from python_calamine import CalamineWorkbook
        abas = []
        with CalamineWorkbook.from_filelike(io.BytesIO(dados)) as wb:
            if len(wb.sheet_names) > LIMITE_ABAS:
                raise ValueError(f"Book acima de {LIMITE_ABAS} abas.")
            for n in wb.sheet_names:
                a = wb.get_sheet_by_name(n).to_python()[:LIMITE_LINHAS]
                abas.append((n, [[Celula(v if v != "" else None, None) for v in r[:LIMITE_COLUNAS]] for r in a]))
        alertas.append("XLS: somente valores armazenados (fórmulas não identificáveis neste formato).")
        return abas, alertas, {"macros": False, "vinculos_externos": []}
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            if sum(i.file_size for i in z.infolist()) > LIMITE_DESCOMPACTADO:
                raise ValueError("Book excede o limite descompactado.")
            nomes = z.namelist()
    except zipfile.BadZipFile as e:
        raise ValueError("Book: arquivo XLSX inválido.") from e
    seguranca = {"macros": any(n.lower().endswith("vbaproject.bin") for n in nomes),
                 "vinculos_externos": sorted(n for n in nomes if n.startswith("xl/externalLinks/") and n.endswith(".xml"))}
    if seguranca["macros"]:
        alertas.append("O arquivo contém macros (VBA): NÃO executadas; nenhuma ação do book foi realizada.")
    if seguranca["vinculos_externos"]:
        alertas.append(f"O arquivo contém {len(seguranca['vinculos_externos'])} vínculo(s) externo(s): NÃO atualizados nem seguidos; "
                       "valores dependentes ficam como armazenados (não verificados).")
    from openpyxl import load_workbook
    wf = load_workbook(io.BytesIO(dados), read_only=True, data_only=False, keep_links=False, keep_vba=False)
    wv = load_workbook(io.BytesIO(dados), read_only=True, data_only=True, keep_links=False, keep_vba=False)
    try:
        if len(wf.sheetnames) > LIMITE_ABAS:
            raise ValueError(f"Book acima de {LIMITE_ABAS} abas.")
        abas = []
        for n in wf.sheetnames:
            f_rows = list(wf[n].iter_rows(max_row=LIMITE_LINHAS, max_col=LIMITE_COLUNAS, values_only=True))
            v_rows = list(wv[n].iter_rows(max_row=LIMITE_LINHAS, max_col=LIMITE_COLUNAS, values_only=True))
            linhas = []
            for i, fr in enumerate(f_rows):
                vr = v_rows[i] if i < len(v_rows) else ()
                linha = []
                for j, f in enumerate(fr):
                    v = vr[j] if j < len(vr) else None
                    formula = f if isinstance(f, str) and f.startswith("=") else None
                    linha.append(Celula(v if formula else f, formula))
                linhas.append(linha)
            abas.append((n, linhas))
    finally:
        wf.close()
        wv.close()
    return abas, alertas, seguranca


def _vazia(l):
    return not any(texto(c.v) or c.f for c in l)


def _classificar(nome, linhas):
    k = chave(nome)
    if _achar_cabecalho(linhas, COLUNAS_BALANCETE, ("conta", "debito", "credito", "saldo_atual"), 4)[0] is not None:
        return "BALANCETE"
    if _achar_cabecalho(linhas, COLUNAS_EVIDENCIAS, ("arquivo",), 4)[0] is not None and ("EVID" in k or _achar_cabecalho(
            linhas, COLUNAS_EVIDENCIAS, ("arquivo", "veredito"), 3)[0] is not None):
        return "EVIDENCIAS"
    if _achar_cabecalho(linhas, COLUNAS_HISTORICO, ("valor",), 4)[0] is not None and ("BAIXA" in k or "HISTOR" in k or _achar_cabecalho(
            linhas, COLUNAS_HISTORICO, ("justificativa",), 4)[0] is not None):
        return "HISTORICO_BAIXAS"
    if _achar_cabecalho(linhas, COLUNAS_PENDENCIAS, ("conta",), 4)[0] is not None and ("PEND" in k or _achar_cabecalho(
            linhas, COLUNAS_PENDENCIAS, ("conta", "situacao"), 4)[0] is not None):
        return "PENDENCIAS"
    i, m = _achar_cabecalho(linhas, COLUNAS_COMPOSICAO, (), 3)
    if i is not None and (("debito" in m and "credito" in m) or "valor" in m or "saldo" in m):
        return "COMPOSICAO"
    if "INDICE" in k or "SUMARIO" in k or "CAPA" in k:
        return "INDICE"
    return "DESCONHECIDA"


def _tabela(linhas, mapa, exigidos, minimo):
    i, m = _achar_cabecalho(linhas, mapa, exigidos, minimo)
    if i is None:
        return []
    saida = []
    for n, l in enumerate(linhas[i + 1:], i + 2):
        if _vazia(l):
            continue
        r = {"linha": n}
        for campo, j in m.items():
            c = l[j] if j < len(l) else Celula(None, None)
            r[campo] = texto(c.v) if campo not in ("valor", "saldo_documento", "diferenca") else (
                None if c.num()[0] is None else f"{c.num()[0]:.2f}")
        if any(v for k, v in r.items() if k != "linha"):
            saida.append(r)
    return saida


def _identificar_conta(rotulo, extra, nome_aba):
    """Identificadores da conta da composição: classificação e/ou código reduzido do rótulo 'Conta:'; nome da aba só como apoio."""
    t = " ".join([texto(rotulo)] + list(extra))
    ident = {"classificacao": None, "codigo": None, "descricao": None, "fonte": None}
    m = CLASSIF.search(t)
    if m:
        ident.update(classificacao=m.group(0), fonte="rotulo Conta")
    else:
        m = re.match(r"\s*(\d+)\b", t)
        if m:
            ident.update(codigo=m.group(1), fonte="rotulo Conta")
    if ident["fonte"] is None:
        m = CLASSIF.search(nome_aba) or re.match(r"\s*(\d+)\s*[-–·. ]", nome_aba)
        if m:
            ident.update(**({"classificacao": m.group(0)} if "." in m.group(0) else {"codigo": m.group(1)}), fonte="nome da aba (apoio)")
    resto = re.sub(r"^[\s\d.\-–·]+", "", t).strip(" ·-–")
    ident["descricao"] = resto.split("·")[0].strip() or None
    return ident


def _composicao(nome, linhas):
    i, m = _achar_cabecalho(linhas, COLUNAS_COMPOSICAO, (), 3)
    rotulo, extra = _rotulo_valor(linhas, ("CONTA", "CONTA CONTABIL"), i)
    data_base, _ = _rotulo_valor(linhas, ("DATA BASE", "DATA-BASE", "DATABASE", "POSICAO EM", "SALDO EM"), i)
    metodo_txt, _ = _rotulo_valor(linhas, ("METODO", "METODO DE COMPOSICAO"), i)
    natureza, _ = _rotulo_valor(linhas, ("NATUREZA",), i)
    c = {"aba": nome, "conta": _identificar_conta(rotulo, extra, nome), "data_base": data_iso(data_base),
         "data_base_texto": texto(data_base) or None, "metodo_informado": texto(metodo_txt) or None, "metodo": _metodo(metodo_txt),
         "natureza_informada": texto(natureza) or None, "colunas": sorted(m), "itens": [], "rodape": {}, "situacao_fonte": [],
         "observacoes_fonte": [], "assinaturas_fonte": [], "alertas": [], "formulas": {"aritmeticas_recalculadas": 0,
                                                                                         "armazenadas_nao_verificadas": 0, "sem_valor": 0}}
    if c["metodo"] == "DESCONHECIDO":
        c["alertas"].append(f"Método '{c['metodo_informado']}' não reconhecido: informe ao Supervisor; nenhum método foi presumido.")
    cab_k = [chave(x.v) for x in linhas[i]]
    fim_itens = False
    for n, l in enumerate(linhas[i + 1:], i + 2):
        if _vazia(l):
            continue
        txts = [texto(x.v) for x in l if texto(x.v)]
        primeiro = chave(txts[0]).rstrip(":") if txts else ""
        if [chave(x.v) for x in l] == cab_k:
            continue                                                       # cabeçalho repetido
        rod = next((k for k, sins in RODAPES if primeiro in sins or any(primeiro.startswith(s + " ") for s in sins)), None)
        if rod:
            fim_itens = True
            valores = {}
            for campo in ("debito", "credito", "valor", "saldo"):
                if campo in m and m[campo] < len(l):
                    v, o = l[m[campo]].num()
                    if v is not None:
                        valores[campo] = {"valor": f"{v:.2f}", "origem": o, "formula": l[m[campo]].f}
            if not valores:                                                # rótulo e valor em colunas fora do mapa
                for x in l[1:]:
                    v, o = x.num()
                    if v is not None:
                        valores["valor"] = {"valor": f"{v:.2f}", "origem": o, "formula": x.f}
            c["rodape"].setdefault(rod, dict(valores, linha=n, observacao=" ".join(t for t in txts[1:] if numero(t) is None)[:200] or None))
            continue
        juntos = " ".join(chave(t) for t in txts)
        # linha com valor numérico nas colunas de débito/crédito/valor é ITEM (descrição pode conter "·", "saldo", nomes...)
        com_valor = any(m[k] < len(l) and l[m[k]].num()[0] is not None for k in ("debito", "credito", "valor") if k in m)
        if not com_valor and (any(chave(t).startswith(a) for t in txts for a in ASSINATURAS)
                              or primeiro in ("NOME", "DATA", "ASSINATURA", "CARGO")):
            c["assinaturas_fonte"].append({"linha": n, "texto": " | ".join(txts)[:200]})
            fim_itens = True
            continue
        if not com_valor and (any(re.match(r"(SALDO|IDENTIFICACAO|EVIDENCIA|PENDENCIAS|SITUACAO|STATUS)\s*[·:]", chave(t).replace("·", "·"))
                                  or re.match(r"(SALDO|IDENTIFICACAO|EVIDENCIA|PENDENCIAS)\s*·", t.upper().replace("Ç", "C").replace("Ã", "A").replace("Ê", "E"))
                                  for t in txts) or primeiro in ("STATUS", "SITUACAO")):
            c["situacao_fonte"] += [t for t in txts]
            fim_itens = True
            continue
        if not com_valor and (primeiro.startswith("OBSERVAC") or primeiro.startswith("NOTA")):
            c["observacoes_fonte"].append(" ".join(txts)[:500])
            fim_itens = True
            continue
        if fim_itens:
            c["observacoes_fonte"].append(" ".join(txts)[:300])
            continue
        item = {"linha": n}
        tem_valor = False
        for campo, j in m.items():
            cel = l[j] if j < len(l) else Celula(None, None)
            if campo in ("debito", "credito", "valor", "saldo"):
                v, o = cel.num()
                item[campo] = None if v is None else f"{v:.2f}"
                if cel.f:
                    item.setdefault("formulas", {})[campo] = cel.f
                    chave_f = {"FORMULA_ARITMETICA_RECALCULADA": "aritmeticas_recalculadas", "VALOR_ARMAZENADO_DE_FORMULA":
                               "armazenadas_nao_verificadas", "FORMULA_SEM_VALOR_ARMAZENADO": "sem_valor"}[o]
                    c["formulas"][chave_f] += 1
                    if o == "FORMULA_SEM_VALOR_ARMAZENADO":
                        item.setdefault("problemas", []).append(f"{campo}: fórmula sem valor armazenado (não executada)")
                tem_valor |= v is not None and campo != "saldo"
            elif campo in ("data", "vencimento"):
                item[campo] = data_iso(cel.v) or (texto(cel.v) or None)
            else:
                item[campo] = texto(cel.v) or None
        if not tem_valor and not any(item.get(k) for k in ("documento", "terceiro", "descricao")) and item.get("saldo") is None:
            c["observacoes_fonte"].append(" ".join(txts)[:300])
            continue
        if not tem_valor and item.get("saldo") is not None and ("debito" in m or "credito" in m):
            item["tipo"] = "SALDO_INICIAL_DA_COMPOSICAO" if "ANTERIOR" in juntos or "INICIAL" in juntos else "LINHA_SO_COM_SALDO"
        c["itens"].append(item)
    _recalcular(c, m, linhas)
    return c


def _acumulado(c, m, linhas):
    """A coluna SALDO é acumulada (corrente) quando as fórmulas referenciam a linha anterior da mesma coluna ou quando os valores
    obedecem saldo_i = saldo_{i-1} + débito_i − crédito_i em todas as linhas."""
    if "saldo" not in m:
        return False
    from openpyxl.utils import get_column_letter
    letra = get_column_letter(m["saldo"] + 1)
    refs = [it for it in c["itens"] if (it.get("formulas") or {}).get("saldo")]
    if refs and all(re.search(rf"\b{letra}\$?{it['linha'] - 1}\b", it["formulas"]["saldo"]) for it in refs[1:] or refs):
        if len(refs) > 1 or re.search(rf"\b{letra}\$?{refs[0]['linha'] - 1}\b", refs[0]["formulas"]["saldo"]):
            return True
    if "debito" in m or "credito" in m:
        ant, ok, n = None, True, 0
        for it in c["itens"]:
            if it.get("saldo") is None:
                continue
            s = Decimal(it["saldo"])
            d, cr = Decimal(it.get("debito") or 0), Decimal(it.get("credito") or 0)
            if ant is not None:
                n += 1
                ok &= s == ant + d - cr
            ant = s
        return ok and n >= 1
    return False


def _recalcular(c, m, linhas):
    itens = [it for it in c["itens"] if not it.get("tipo")]
    iniciais = [it for it in c["itens"] if it.get("tipo") == "SALDO_INICIAL_DA_COMPOSICAO"]
    acumulado = _acumulado(c, m, linhas)
    c["saldo_coluna"] = "ACUMULADO (não somado)" if acumulado else ("POR ITEM" if "saldo" in m else "AUSENTE")
    deb = sum((Decimal(it["debito"]) for it in itens if it.get("debito")), ZERO)
    cre = sum((Decimal(it["credito"]) for it in itens if it.get("credito")), ZERO)
    base_inicial = sum((Decimal(it["saldo"]) for it in iniciais if it.get("saldo")), ZERO)
    if "debito" in m or "credito" in m:
        calc, regra = base_inicial + deb - cre, "saldo inicial da composição (se houver) + Σ débitos − Σ créditos dos itens"
        if any(it.get("valor") for it in itens) and not any(it.get("debito") or it.get("credito") for it in itens):
            calc, regra = sum((Decimal(it["valor"]) for it in itens if it.get("valor")), ZERO), "Σ valores dos itens"
    elif "valor" in m:
        calc, regra = sum((Decimal(it["valor"]) for it in itens if it.get("valor")), ZERO), "Σ valores dos itens"
    elif "saldo" in m and not acumulado:
        calc, regra = sum((Decimal(it["saldo"]) for it in itens if it.get("saldo")), ZERO), "Σ saldos POR ITEM"
    elif acumulado:
        ultimos = [it for it in c["itens"] if it.get("saldo") is not None]
        calc, regra = (Decimal(ultimos[-1]["saldo"]) if ultimos else None), "último saldo acumulado (coluna corrente, sem débito/crédito)"
    else:
        calc, regra = None, "sem colunas de valor reconhecidas"
    c["totais_recalculados"] = {"debitos": f"{deb:.2f}", "creditos": f"{cre:.2f}", "saldo": None if calc is None else f"{calc:.2f}",
                                "regra": regra, "itens": len(itens)}
    if acumulado and c["itens"]:
        ult = next((it for it in reversed(c["itens"]) if it.get("saldo") is not None), None)
        if ult and calc is not None and Decimal(ult["saldo"]) != calc:
            c["alertas"].append(f"Último saldo acumulado da planilha ({ult['saldo']}) ≠ saldo recalculado ({calc:.2f}).")
    # total armazenado × recalculado (armazenado não é verificado)
    tot = c["rodape"].get("total") or {}
    for campo, ref in (("debito", deb), ("credito", cre)):
        if campo in tot and Decimal(tot[campo]["valor"]) != ref:
            c["alertas"].append(f"TOTAL de {campo} informado na planilha ({tot[campo]['valor']}) ≠ soma dos itens ({ref:.2f}).")
    t_saldo = (tot.get("saldo") or tot.get("valor") or {}).get("valor")
    if t_saldo is not None and calc is not None and Decimal(t_saldo) != calc:
        c["alertas"].append(f"TOTAL/saldo informado na planilha ({t_saldo}) ≠ saldo recalculado ({calc:.2f}).")
    datas = [it.get("data") for it in itens if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(it.get("data") or ""))]
    c["itens_datados"] = {"quantidade": len(datas), "mais_antigo": min(datas) if datas else None, "mais_recente": max(datas) if datas else None}
    if c["data_base"]:
        posteriores = [d for d in datas if d > c["data_base"]]
        if posteriores:
            c["alertas"].append(f"{len(posteriores)} item(ns) com data posterior à data-base {c['data_base']}.")


def _balancete_book(linhas):
    i, m = _achar_cabecalho(linhas, COLUNAS_BALANCETE, ("conta", "debito", "credito", "saldo_atual"), 4)
    saida = []
    for n, l in enumerate(linhas[i + 1:], i + 2):
        conta = texto(l[m["conta"]].v) if m["conta"] < len(l) else ""
        if not re.fullmatch(r"\d+(?:\.\d+)*", conta):
            continue
        r = {"linha": n, "conta": conta, "descricao": texto(l[m["descricao"]].v) if "descricao" in m and m["descricao"] < len(l) else ""}
        for k in ("saldo_anterior", "debito", "credito", "saldo_atual"):
            if k in m and m[k] < len(l):
                v, _ = l[m[k]].num()
                r[k] = None if v is None else f"{v:.2f}"
        saida.append(r)
    return saida


def _meta(abas):
    """CNPJ, empresa, período e abrangência mencionados nas primeiras linhas de qualquer aba (fonte informativa)."""
    cnpjs, competencias, consolidado, textos = set(), set(), [], []
    for nome, linhas in abas:
        for l in linhas[:8]:
            for c in l:
                t = texto(c.v)
                if not t:
                    continue
                textos.append(t)
                cnpjs.update(re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", t))
                for mm, aa in re.findall(r"COMPET[EÊ]NCIA\s*(\d{2})/(\d{4})", t, re.I):
                    competencias.add(f"{aa}-{mm}")
                if "CONSOLIDAD" in chave(t):
                    consolidado.append(t[:120])
    return {"cnpjs": sorted(cnpjs), "competencias_mencionadas": sorted(competencias), "mencoes_consolidado": consolidado[:5]}


def ler(nome: str, dados: bytes) -> dict:
    abas, alertas, seguranca = _carregar(dados, nome)
    r = {"formato": "BOOK_PLANILHA", "abas": [], "composicoes": [], "pendencias": [], "historico_baixas": [], "evidencias": [],
         "balancete_book": [], "alertas": alertas, "seguranca": seguranca, "meta": _meta(abas)}
    for n, linhas in abas:
        tipo = _classificar(n, linhas)
        r["abas"].append({"aba": n, "tipo": tipo, "linhas": len(linhas)})
        try:
            if tipo == "COMPOSICAO":
                r["composicoes"].append(_composicao(n, linhas))
            elif tipo == "PENDENCIAS":
                r["pendencias"] += [dict(x, aba=n) for x in _tabela(linhas, COLUNAS_PENDENCIAS, ("conta",), 4)]
            elif tipo == "HISTORICO_BAIXAS":
                r["historico_baixas"] += [dict(x, aba=n) for x in _tabela(linhas, COLUNAS_HISTORICO, ("valor",), 4)]
            elif tipo == "EVIDENCIAS":
                r["evidencias"] += [dict(x, aba=n, arquivo_recebido=False,
                                         aviso="referência a arquivo informada no book; o documento NÃO foi recebido pelo aplicativo")
                                    for x in _tabela(linhas, COLUNAS_EVIDENCIAS, ("arquivo",), 4)]
            elif tipo == "BALANCETE":
                r["balancete_book"] += _balancete_book(linhas)
        except (ValueError, IndexError, KeyError, ArithmeticError) as exc:
            r["alertas"].append(f"Aba '{n}': leitura interrompida ({type(exc).__name__}); conferir manualmente.")
    r["resumo"] = {"abas": len(abas), "por_tipo": {t: sum(a["tipo"] == t for a in r["abas"]) for t in sorted({a["tipo"] for a in r["abas"]})},
                   "composicoes": len(r["composicoes"]), "pendencias": len(r["pendencias"]),
                   "historico_baixas": len(r["historico_baixas"]), "evidencias": len(r["evidencias"]),
                   "metodos": {k: sum(c["metodo"] == k for c in r["composicoes"]) for k in sorted({c["metodo"] for c in r["composicoes"]})}}
    r["aviso"] = ("Situação, nomes e assinaturas do book são informação da FONTE, não aprovações do aplicativo. Diferença zero não "
                  "significa conciliação concluída. Histórico de baixas é histórico e nunca gera lançamento.")
    return r


# ---------------------------------------------------------------- confronto com o balancete da base
def confrontar(book: dict, contas_balancete: list, data_base: str) -> dict:
    """Relaciona cada composição a uma conta do balancete por IDENTIFICADOR (classificação ou código reduzido). Mantém separados:
    conferência numérica, identificação dos itens, documentos de suporte, pendências e confirmação do Supervisor."""
    por_class = {c["classificacao"]: c for c in contas_balancete}
    por_cod = {str(c.get("codigo")): c for c in contas_balancete if c.get("codigo")}
    pend_por_conta = {}
    for p in book.get("pendencias", []):
        pend_por_conta.setdefault(_id_conta(p.get("conta"), por_class, por_cod), []).append(p)
    evid_por_conta = {}
    for e in book.get("evidencias", []):
        evid_por_conta.setdefault(_id_conta(e.get("conta_analitica") or e.get("conta"), por_class, por_cod), []).append(e)
    saida, usadas = [], {}
    for c in book.get("composicoes", []):
        ident = c["conta"]
        conta = por_class.get(ident.get("classificacao")) or por_cod.get(str(ident.get("codigo")))
        x = {"aba": c["aba"], "identificador": ident, "metodo": c["metodo"], "metodo_informado": c["metodo_informado"],
             "data_base": c["data_base"], "itens": c["totais_recalculados"]["itens"], "saldo_composicao": c["totais_recalculados"]["saldo"],
             "regra_saldo": c["totais_recalculados"]["regra"], "saldo_coluna": c["saldo_coluna"], "alertas": list(c["alertas"]),
             "situacao_fonte": c["situacao_fonte"], "assinaturas_fonte": len(c["assinaturas_fonte"])}
        if conta is None:
            x.update(conta=None, conferencia_numerica="SEM_CONTA_CORRESPONDENTE",
                     explicacao="Composição sem conta correspondente no balancete (identificador não encontrado); nada foi presumido.")
        else:
            usadas.setdefault(conta["classificacao"], []).append(c["aba"])
            x["conta"] = {"codigo": conta.get("codigo"), "classificacao": conta["classificacao"], "descricao": conta.get("descricao"),
                          "tipo": conta.get("tipo")}
            bal = None if conta.get("saldo_atual") is None else Decimal(conta["saldo_atual"])
            comp = None if x["saldo_composicao"] is None else Decimal(x["saldo_composicao"])
            x["saldo_balancete"] = None if bal is None else f"{bal:.2f}"
            if comp is None or bal is None:
                x.update(conferencia_numerica="NAO_DETERMINADA", explicacao="Saldo da composição ou do balancete indisponível.")
            else:
                dif = comp - bal
                x["diferenca"] = f"{dif:.2f}"
                if dif == 0:
                    x.update(conferencia_numerica="IGUAL_AO_BALANCETE",
                             explicacao="Saldo recalculado da composição igual ao saldo do balancete (conferência numérica apenas).")
                elif comp == -bal and not any(it for it in c["colunas"] if it in ("debito", "credito")):
                    x.update(conferencia_numerica="SINAL_A_CONFIRMAR",
                             explicacao="Valores iguais com sinal oposto e sem colunas de débito/crédito: convenção de sinal do book não "
                                        "identificada; confirme com o Supervisor (nenhum ajuste automático).")
                else:
                    x.update(conferencia_numerica="DIVERGENTE", explicacao=(f"Composição ({comp:.2f}, aba {c['aba']}) difere do balancete "
                             f"({bal:.2f}) em {dif:.2f}." + (" A composição não tem itens." if not x["itens"] else "")
                             + " Nenhum ajuste automático."))
            ref = (c.get("rodape") or {}).get("saldo_conforme_balancete") or {}
            ref_v = next((v["valor"] for k, v in ref.items() if isinstance(v, dict) and "valor" in v), None)
            if ref_v is not None and bal is not None and Decimal(ref_v) != bal:
                x["alertas"].append(f"'Saldo conforme balancete' informado no book ({ref_v}) ≠ balancete recebido ({bal:.2f}).")
        if c["data_base"] and data_base and c["data_base"] != data_base:
            x["alertas"].append(f"Data-base da composição {c['data_base']} ≠ data-base da base inicial {data_base}.")
        chave_conta = x["conta"]["classificacao"] if x.get("conta") else None
        pend = pend_por_conta.get(chave_conta, []) if chave_conta else []
        evid = evid_por_conta.get(chave_conta, []) if chave_conta else []
        x["identificacao_itens"] = ("SEM_ITENS" if not x["itens"] else
                                    "ITENS_COM_IDENTIFICACAO_INCOMPLETA" if any(not (it.get("documento") or it.get("terceiro") or it.get("descricao"))
                                                                                 for it in c["itens"] if not it.get("tipo"))
                                    else "ITENS_IDENTIFICADOS_NA_FONTE")
        x["documentos_suporte"] = {"referencias_no_book": len(evid), "recebidos_pelo_aplicativo": 0,
                                   "situacao": "PENDENTE",
                                   "explicacao": "Referências a arquivos no book não comprovam recebimento; nenhum documento de suporte "
                                                 "foi recebido pelo aplicativo nesta etapa."}
        x["pendencias_book"] = [{"titulo": p.get("titulo"), "situacao": p.get("situacao"), "severidade": p.get("severidade")} for p in pend]
        x["confirmacao_supervisor"] = "PENDENTE"
        x["situacao"] = ("DIVERGENCIA" if x["conferencia_numerica"] in ("DIVERGENTE", "SINAL_A_CONFIRMAR") else
                         "SEM_CONTA" if x["conferencia_numerica"] == "SEM_CONTA_CORRESPONDENTE" else
                         "CONFERENCIA_NUMERICA_OK_EVIDENCIA_PENDENTE" if x["conferencia_numerica"] == "IGUAL_AO_BALANCETE" else
                         "NAO_DETERMINADA")
        saida.append(x)
    repetidas = {k: v for k, v in usadas.items() if len(v) > 1}
    # elegibilidade para composição: ANALÍTICA + PATRIMONIAL (Ativo, Passivo, PL) + saldo final ≠ 0 (plano_hierarquia).
    # Sintéticas nunca exigem composição individual; Contas de Resultado e Outros nunca exigem; saldo zero não exige.
    if any("exige_composicao" not in c for c in contas_balancete):
        import plano_hierarquia
        contas_balancete = [dict(c) for c in contas_balancete]
        plano_hierarquia.anotar(contas_balancete)
    sem_comp = [c for c in contas_balancete if c.get("exige_composicao") and c["classificacao"] not in usadas]
    bal_book = []
    for b in book.get("balancete_book", []):
        conta = por_class.get(b["conta"]) or por_cod.get(b["conta"])
        if conta and b.get("saldo_atual") is not None and conta.get("saldo_atual") is not None and Decimal(b["saldo_atual"]) != Decimal(conta["saldo_atual"]):
            bal_book.append({"conta": b["conta"], "no_book": b["saldo_atual"], "no_balancete": conta["saldo_atual"]})
    return {"composicoes": saida,
            "resumo": {"composicoes": len(saida),
                       "iguais_ao_balancete": sum(x["conferencia_numerica"] == "IGUAL_AO_BALANCETE" for x in saida),
                       "divergentes": sum(x["conferencia_numerica"] in ("DIVERGENTE", "SINAL_A_CONFIRMAR") for x in saida),
                       "sem_conta": sum(x["conferencia_numerica"] == "SEM_CONTA_CORRESPONDENTE" for x in saida),
                       "nao_determinadas": sum(x["conferencia_numerica"] == "NAO_DETERMINADA" for x in saida),
                       "metodo_desconhecido": sum(x["metodo"] == "DESCONHECIDO" for x in saida),
                       "contas_com_saldo_sem_composicao": len(sem_comp), "pendencias_book": len(book.get("pendencias", [])),
                       "evidencias_referenciadas": len(book.get("evidencias", [])), "historico_baixas": len(book.get("historico_baixas", []))},
            "contas_com_saldo_sem_composicao": [{"codigo": c.get("codigo"), "classificacao": c["classificacao"], "descricao": c.get("descricao"),
                                                 "saldo": c.get("saldo_atual")} for c in sem_comp],
            "composicoes_repetidas_para_a_mesma_conta": repetidas,
            "balancete_do_book_diferente": bal_book,
            "aviso": "Diferença zero não significa conciliação concluída: identificação dos itens, documentos de suporte, pendências e "
                     "confirmação do Supervisor são verificações separadas."}


def _id_conta(v, por_class, por_cod):
    t = texto(v)
    m = CLASSIF.search(t)
    if m and m.group(0) in por_class:
        return m.group(0)
    m = re.match(r"\s*(\d+)\b", t)
    if m and m.group(1) in por_cod:
        return por_cod[m.group(1)]["classificacao"]
    return None
