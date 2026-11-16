"""ADAPTADORES DO FECHAMENTO — registro único de "quem lê qual formato" e contratos normalizados (MOTOR GERAL + ADAPTER).

Classificação obrigatória de tudo que está aqui (pergunta da arquitetura multiempresa):
- MOTOR GERAL: categorias de documento, departamento responsável/consumidores, reconhecimento (adapter existente / layout novo /
  não reconhecido), contratos *_NORMALIZADO_V1 e validação. Vale para QUALQUER empresa.
- ADAPTER: tradução de UM formato para um contrato (ex.: balancete em tabela com sinônimos de cabeçalho → BALANCETE_NORMALIZADO_V1).
  Adapter pode ser compartilhado entre empresas; NUNCA carrega dado nem regra de empresa.
- REGRA DA EMPRESA: não existe neste módulo (fica em CLIENTES/<EMPRESA>/REGRAS-*.json, governada pelo Supervisor).

Nenhum layout real é inventado: um documento cuja estrutura nenhum adapter lê fica "RECONHECIDO — LAYOUT NOVO, ADAPTER NECESSÁRIO"
(ou "NÃO RECONHECIDO — AGUARDANDO SUPERVISOR"), com a pendência correspondente. Valores ausentes nunca são preenchidos.
Somente leitura: nada aqui grava, aprova ou escritura.
"""
import hashlib
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import balancete_anterior
import book_contabil
import documentos_local as dl

VERSAO = "1.0"

# ---------------------------------------------------------------- departamentos (FECHAMENTO não é departamento: é o processo)
DEPARTAMENTOS = ("FISCAL", "FINANCEIRO", "CONTABIL", "DP", "CONCILIACAO")
NOME_DEPARTAMENTO = {"FISCAL": "Fiscal", "FINANCEIRO": "Financeiro", "CONTABIL": "Contábil", "DP": "DP", "CONCILIACAO": "Conciliação",
                     "COORDENADOR": "Coordenador", "SUPERVISOR": "Supervisor", "A_CONFERIR": "A conferir"}

# Categoria da prévia de classificação: (departamento responsável, categoria, consumidores). Pela rota técnica de Documentos.
CATEGORIA_TIPO = [
    (lambda t: t in ("Nota fiscal XML", "Possível nota fiscal", "Evento fiscal"), ("FISCAL", "Notas fiscais", ("CONTABIL", "FINANCEIRO"))),
    (lambda t: t in ("Possível guia", "Demonstrativo de apuração"), ("FISCAL", "Impostos, guias e apurações", ("CONTABIL", "FINANCEIRO"))),
    (lambda t: t.startswith("Extrato "), ("FINANCEIRO", "Extratos bancários", ("CONCILIACAO",))),
    (lambda t: t == "Relatório financeiro de lançamentos", ("FINANCEIRO", "Relatórios financeiros", ("CONCILIACAO",))),
    (lambda t: t in ("Possível comprovante", "Possível boleto", "Possível recibo", "Possível relação de pagamentos", "Posição de títulos",
                     "Posição de investimentos", "Contrato de câmbio"), ("FINANCEIRO", "Comprovantes, títulos e posições", ("CONCILIACAO",))),
    (lambda t: t == dl.TIPO_BALANCETE, ("CONTABIL", "Balancete", ("CONCILIACAO",))),
    (lambda t: t == dl.TIPO_RAZAO, ("CONTABIL", "Razão", ("CONCILIACAO",))),
    (lambda t: t in ("Folha / documento de pessoal", "Resumo da folha de pagamento", "Resumo de encargos da folha",
                     "Demonstrativo de provisões"), ("DP", "Folha e documentos de pessoal", ("CONTABIL", "FINANCEIRO"))),
    (lambda t: t == dl.TIPO_BOOK, ("CONCILIACAO", "Book de conciliação", ())),
    (lambda t: t == dl.TIPO_PAGAMENTOS_ECAC, ("FISCAL", "Pagamentos e-CAC", ("CONCILIACAO",))),
    (lambda t: t == dl.TIPO_SITUACAO_FISCAL, ("FISCAL", "Situação fiscal", ("CONCILIACAO",))),
    (lambda t: t == dl.TIPO_RESUMO_FOLHA_DOMINIO, ("DP", "Folha e documentos de pessoal", ("CONCILIACAO",))),
    (lambda t: t in ("Confirmação de saldo", "Saldos de abertura"), ("CONCILIACAO", "Confirmações e saldos de abertura", ())),
]
AREA_PARA_DEPARTAMENTO = {"FISCAL": "FISCAL", "FINANCEIRO": "FINANCEIRO", "CONTABIL": "CONTABIL", "DP": "DP", "CONCILIACAO": "CONCILIACAO"}

ADAPTER_EXISTENTE = "RECONHECIDO_ADAPTER_EXISTENTE"
LAYOUT_NOVO = "RECONHECIDO_LAYOUT_NOVO_ADAPTER_NECESSARIO"
NAO_RECONHECIDO = "NAO_RECONHECIDO_AGUARDANDO_SUPERVISOR"
TEXTO_RECONHECIMENTO = {ADAPTER_EXISTENTE: "Reconhecido · adapter existente",
                        LAYOUT_NOVO: "Reconhecido · layout novo — adapter necessário (aguardando arquivo real para criar/validar)",
                        NAO_RECONHECIDO: "Não reconhecido · aguardando classificação do Supervisor"}

# ---------------------------------------------------------------- contratos normalizados (campos obrigatórios por item)
CONTRATOS = {
    "BALANCETE_NORMALIZADO_V1": ("conta", "descricao", "saldo_inicial", "debitos", "creditos", "saldo_final"),
    "RAZAO_CONTABIL_NORMALIZADO_V1": ("data", "conta", "historico", "debito", "credito"),
    "BOOK_CONCILIACAO_CONTABIL_V1": ("conta", "saldo_composicao"),
    "OBRIGACAO_TRIBUTARIA_NORMALIZADA_V1": ("tributo_ou_codigo", "competencia", "total", "departamento"),
}


def categoria(item: dict) -> dict:
    """Departamento responsável, categoria e consumidores do documento (pela rota de Documentos; área nula → A CONFERIR)."""
    enc = item.get("encaminhamento") or {}
    tipo = str(item.get("tipo") or enc.get("tipo") or "")
    if not enc.get("area") or item.get("leitura_pendente"):
        return {"departamento": "A_CONFERIR", "categoria": "A conferir" if not item.get("leitura_pendente") else "Leitura pendente",
                "consumidores": []}
    # o departamento é o da ROTA efetiva de Documentos (verdade do roteamento); o tipo dá só a categoria e os consumidores
    dep_rota = AREA_PARA_DEPARTAMENTO.get(enc.get("area"), "A_CONFERIR")
    for teste, (dep, cat, cons) in CATEGORIA_TIPO:
        if teste(tipo):
            return {"departamento": dep_rota, "categoria": cat, "consumidores": [c for c in cons if c != dep_rota],
                    **({"divergencia_rota": f"esperado {dep}, roteado a {dep_rota}"} if dep != dep_rota else {})}
    dep = AREA_PARA_DEPARTAMENTO.get(enc.get("area"), "A_CONFERIR")
    return {"departamento": dep, "categoria": "Outros documentos", "consumidores": [AREA_PARA_DEPARTAMENTO.get(c, c) for c in enc.get("copias_suporte", [])]}


# ---------------------------------------------------------------- leitura segura do original (sha256 conferido)
def original(clientes: Path, empresa: str, item: dict):
    """Bytes do documento original SOMENTE se o sha256 confere com o manifesto. None = ausente/alterado (fail-closed)."""
    base = (Path(clientes) / empresa).resolve()
    alvo = (base / str(item.get("arquivo") or "")).resolve()
    try:
        alvo.relative_to(base)
    except ValueError:
        return None
    if not alvo.is_file():
        return None
    dados = alvo.read_bytes()
    return dados if hashlib.sha256(dados).hexdigest() == item.get("sha256") else None


def linhas_tabulares(extraido: dict) -> list:
    """Linhas (listas de células) do CSV ';' ou das abas visíveis da planilha, como lidas pelo extrator de Documentos."""
    c = (extraido or {}).get("conteudo") or {}
    if extraido.get("leitura") == "EXTRAIDO_PLANILHA":
        linhas = []
        for aba in c.get("abas", []):
            if not aba.get("oculta"):
                linhas += [list(l.get("valores") or []) for l in aba.get("linhas", [])]
        return linhas
    texto = c.get("texto", "") or "\n".join(p.get("texto", "") for p in c.get("paginas", []))
    return [[x.strip() for x in l.split(";")] for l in texto.splitlines() if l.strip()]


def numero(v):
    """'1.234,56' | '1234.56' | número → Decimal exato; vazio → None; inválido → ValueError (nunca vira zero)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    n = book_contabil.numero(v)
    if n is None:
        raise ValueError(f"valor ilegível: {str(v)[:30]}")
    return Decimal(n)


# ---------------------------------------------------------------- ADAPTERS
def adapter_balancete(item, extraido, clientes, empresa):
    """Balancete do período: leitor do motor geral (PDF no layout de colunas do Domínio ou tabela com sinônimos)."""
    nome = str(item.get("arquivo") or "")
    try:
        if nome.lower().endswith(".pdf"):
            dados = original(clientes, empresa, item)
            if dados is None:
                return None, "Original ausente ou alterado (sha256 não confere); balancete não lido."
            lido = balancete_anterior.ler(nome, dados)
            adapter = "BALANCETE_PDF_COLUNAS_V1"
        else:
            lido = balancete_anterior.ler(nome, b"", linhas_tabela=linhas_tabulares(extraido))
            adapter = "BALANCETE_TABELA_SINONIMOS_V1"
    except Exception as exc:                       # noqa: BLE001 — leitor recusou: layout novo (nunca valor presumido)
        return None, f"Leitor do balancete recusou o arquivo ({type(exc).__name__})."
    contas = [c for c in lido.get("contas", []) if c.get("classificacao")]
    if not contas:
        return None, "; ".join(lido.get("limites") or []) or "Nenhuma conta reconhecida no layout."
    norm = []
    for c in contas:
        norm.append({"conta": c["classificacao"], "codigo": c.get("codigo"), "descricao": c.get("descricao"),
                     "saldo_inicial": c.get("saldo_anterior"), "debitos": c.get("debitos"), "creditos": c.get("creditos"),
                     "saldo_final": c.get("saldo_atual"), "tipo": c.get("tipo"), "grupo": c.get("grupo"),
                     "exige_composicao": c.get("exige_composicao"), "confere": c.get("confere"), "problemas": c.get("problemas") or []})
    return {"contrato": "BALANCETE_NORMALIZADO_V1", "adapter": adapter, "contas": norm, "totais": lido.get("totais", {}),
            "meta": lido.get("meta", {}), "_contas_leitor": contas}, None


SIN_RAZAO = {"data": ("DATA", "DATA LANCTO", "DATA LANCAMENTO"), "conta": ("CONTA", "CLASSIFICACAO", "CODIGO", "CONTA CONTABIL"),
             "contrapartida": ("CONTRAPARTIDA", "CONTRA PARTIDA", "CONTA CONTRAPARTIDA", "CTA.C.PART.", "CTA C PART"),
             "historico": ("HISTORICO", "DESCRICAO", "COMPLEMENTO"), "debito": ("DEBITO", "DEBITOS", "VALOR DEBITO"),
             "credito": ("CREDITO", "CREDITOS", "VALOR CREDITO"), "saldo": ("SALDO", "SALDO ATUAL"),
             "documento": ("DOCUMENTO", "DOC", "NF", "NUMERO DOCUMENTO"), "lote": ("LOTE",), "referencia": ("REFERENCIA", "REF")}


def _secao_razao(linha):
    """Reconhece o marcador ``Conta:`` do Razão exportado pelo Domínio."""
    vals = [str(x or "").strip() for x in linha]
    if not vals or not vals[0].upper().startswith("CONTA"):
        return None
    classificacao = next((x for x in vals[1:] if re.fullmatch(r"\d+(?:\.\d+){2,}", x)), None)
    if not classificacao:
        return None
    codigo = re.sub(r"\.0+$", "", vals[1]) if len(vals) > 1 and re.fullmatch(r"\d+(?:\.0+)?", vals[1]) else None
    pos = vals.index(classificacao)
    descricao = next((x for x in vals[pos + 1:] if x), None)
    return {"conta": classificacao, "codigo": codigo, "descricao": descricao}


def adapter_razao_pdf(item, clientes, empresa):
    """Razão em PDF do Domínio (colunas pela posição do cabeçalho; razao_pdf_dominio)."""
    import razao_pdf_dominio
    dados = original(clientes, empresa, item)
    if dados is None:
        return None, "Original ausente ou alterado (sha256 não confere); razão não lido."
    try:
        lido = razao_pdf_dominio.ler(dados)
    except Exception as exc:                       # noqa: BLE001 — leitor recusou: layout novo (nunca valor presumido)
        return None, f"Leitor do razão em PDF recusou o arquivo ({type(exc).__name__})."
    if not lido["lancamentos"] and not lido["contas"]:
        return None, "; ".join(lido.get("limites") or []) or "Nenhuma conta/lançamento reconhecido no razão em PDF."
    lancs = [dict(l, conta_principal=l.get("conta")) for l in lido["lancamentos"]]
    return {"contrato": "RAZAO_CONTABIL_NORMALIZADO_V1", "adapter": razao_pdf_dominio.LEITOR, "lancamentos": lancs,
            "contas": lido["contas"], "meta": lido["meta"], "limites": lido["limites"],
            "problemas": [f"p.{l['pagina']} {l['data']}: {x}" for l in lancs for x in l.get("problemas", [])]}, None


def adapter_razao(item, extraido, clientes, empresa):
    """Razão tabular, incluindo o layout Domínio com seções ``Conta:``; PDF do Domínio pelo leitor de colunas."""
    if str(item.get("arquivo") or "").lower().endswith(".pdf"):
        return adapter_razao_pdf(item, clientes, empresa)
    linhas = linhas_tabulares(extraido) if extraido.get("leitura") in ("EXTRAIDO_PLANILHA", "EXTRAIDO_TEXTO") else []
    secao_layout = False
    for i, l in enumerate(linhas[:30]):
        k = [book_contabil.chave(x) for x in l]
        mapa = {campo: next(j for j, x in enumerate(k) if x in sins) for campo, sins in SIN_RAZAO.items() if any(x in sins for x in k)}
        if {"data", "historico", "debito", "credito"} <= set(mapa) and ("conta" in mapa or any(_secao_razao(x) for x in linhas[:30])):
            secao_layout = "conta" not in mapa
            break
    else:
        return None, "Razão sem cabeçalho tabular reconhecido (data, conta, histórico, débito, crédito)."
    lancamentos, problemas = [], []
    secao = None
    resumo = {}                                      # seção "Conta:" → saldo anterior, débitos, créditos, último saldo acumulado
    for n, l in enumerate(linhas[i + 1:], i + 2):
        marcador = _secao_razao(l)
        if marcador:
            secao = marcador
            resumo[id(secao)] = {**secao, "saldo_anterior": None, "debitos": Decimal("0"), "creditos": Decimal("0"), "ultimo": None,
                                 "lancamentos": 0, "problemas": []}
            continue
        get = lambda c: l[mapa[c]] if c in mapa and mapa[c] < len(l) else None  # noqa: E731
        conta = str(get("conta") or (secao or {}).get("conta") or "").strip()
        if not conta:
            continue
        rs = resumo.get(id(secao)) if secao else None
        if rs is not None and "SALDO ANTERIOR" in book_contabil.chave(get("historico") or ""):
            numeros = [x for x in l if isinstance(x, (int, float)) and not isinstance(x, bool)]
            rs["saldo_anterior"] = Decimal(str(numeros[-1])) if numeros else None
            continue
        try:
            deb, cre = numero(get("debito")) or Decimal("0"), numero(get("credito")) or Decimal("0")
            saldo = numero(get("saldo"))
        except ValueError as exc:
            problemas.append(f"linha {n}: {exc}; lançamento não aproveitado")
            continue
        data = book_contabil.data_iso(get("data"))
        if not data and not deb and not cre and saldo is None:
            continue                         # linha sem data e sem valores (rodapé/texto do relatório): não é lançamento
        if not data:
            problemas.append(f"linha {n}: data ausente ou inválida; lançamento não aproveitado")
            continue
        if rs is not None:
            rs["debitos"] += deb
            rs["creditos"] += cre
            rs["lancamentos"] += 1
            numeros = [x for x in l if isinstance(x, (int, float)) and not isinstance(x, bool)]
            rs["ultimo"] = Decimal(str(numeros[-1])) if numeros else None
        lancamentos.append({"linha": n, "data": data, "conta": conta, "conta_principal": conta,
                            "codigo": (secao or {}).get("codigo"),
                            "contrapartida": re.sub(r"\.0+$", "", str(get("contrapartida") or "").strip()) or None,
                            "historico": str(get("historico") or "").strip(), "debito": f"{deb:.2f}", "credito": f"{cre:.2f}",
                            "saldo": None if saldo is None else f"{saldo:.2f}", "documento": str(get("documento") or "").strip() or None,
                            "lote": str(get("lote") or "").strip() or None, "referencia": str(get("referencia") or "").strip() or None,
                            "secao": dict(secao) if secao else None})
    if not lancamentos:
        return None, "Nenhum lançamento aproveitável no razão."
    contas = []
    for rs in resumo.values():              # resumo por conta (layout com seções): saldo final = anterior + débitos − créditos
        final = None if rs["saldo_anterior"] is None else rs["saldo_anterior"] + rs["debitos"] - rs["creditos"]
        if rs["saldo_anterior"] is None:
            rs["problemas"].append("saldo anterior não identificado na seção da conta")
        elif rs["ultimo"] is not None and rs["lancamentos"] and rs["ultimo"] != final:
            rs["problemas"].append(f"saldo acumulado da última linha ({rs['ultimo']:.2f}) ≠ anterior + débitos − créditos ({final:.2f})")
        contas.append({"codigo": rs.get("codigo"), "classificacao": rs.get("conta"), "descricao": rs.get("descricao"),
                       "saldo_anterior": None if rs["saldo_anterior"] is None else f"{rs['saldo_anterior']:.2f}",
                       "debitos": f"{rs['debitos']:.2f}", "creditos": f"{rs['creditos']:.2f}",
                       "saldo_final": None if final is None else f"{final:.2f}", "lancamentos": rs["lancamentos"], "problemas": rs["problemas"]})
    meta = {}
    for l in linhas[:i]:                    # cabeçalho do relatório: CNPJ e período (Domínio: "C.N.P.J.:" e "Período:")
        k = [book_contabil.chave(x) for x in l]
        vals = [str(x).strip() for x in l if str(x or "").strip()]
        if k and k[0].startswith("C.N.P.J") and len(vals) > 1:
            meta["cnpj"] = vals[1]
        if k and k[0].startswith("PERIODO") and len(vals) > 1:
            m = re.search(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", vals[1])
            if m:
                meta["periodo"] = {"inicio": book_contabil.data_iso(m.group(1)), "fim": book_contabil.data_iso(m.group(2))}
    return {"contrato": "RAZAO_CONTABIL_NORMALIZADO_V1", "adapter": "RAZAO_SECOES_CONTA_V1" if secao_layout else "RAZAO_TABELA_SINONIMOS_V1", "lancamentos": lancamentos,
            "problemas": problemas, "contas": contas, "meta": meta}, None


def adapter_book(item, extraido, clientes, empresa):
    """Book (composições): leitor do motor geral (planilha por conteúdo; fórmulas nunca executadas)."""
    dados = original(clientes, empresa, item)
    if dados is None:
        return None, "Original ausente ou alterado (sha256 não confere); book não lido."
    try:
        lido = book_contabil.ler(str(item.get("arquivo")), dados)
    except Exception as exc:                       # noqa: BLE001
        return None, f"Leitor do book recusou o arquivo ({type(exc).__name__}: {str(exc)[:80]})."
    if not lido.get("composicoes"):
        return None, "Nenhuma composição reconhecida no book."
    contas = [{"conta": c["conta"].get("classificacao") or c["conta"].get("codigo"), "descricao": c["conta"].get("descricao"),
               "aba": c["aba"], "saldo_composicao": c["totais_recalculados"]["saldo"], "metodo": c["metodo"],
               "itens": len(c["itens"]), "data_base": c["data_base"], "alertas": c["alertas"], "situacao_fonte": c["situacao_fonte"]}
              for c in lido["composicoes"]]
    return {"contrato": "BOOK_CONCILIACAO_CONTABIL_V1", "adapter": "BOOK_PLANILHA_CONTEUDO_V1", "contas": contas,
            "pendencias_fonte": len(lido.get("pendencias", [])), "alertas": lido.get("alertas", []), "_lido": lido}, None


def _adapter_caixinha(modulo, contrato, campo):
    def adapter(item, extraido, clientes, empresa):
        import caixinha_comum as cc
        cnpjs = cc.cnpjs_no_texto(cc.texto_total(extraido or {}))
        lido = modulo.ler(dict(extraido or {}, arquivo=item.get("arquivo"), sha256=item.get("sha256")), empresa, cnpjs)
        if lido["reconhecimento"] != "RECONHECIDO":
            return None, "; ".join(lido["pendencias"]) or "Estrutura não reconhecida."
        return {"contrato": contrato, "adapter": modulo.LEITOR, campo: lido.get(campo), "pendencias_leitura": lido["pendencias"]}, None
    return adapter


ADAPTERS = {dl.TIPO_BALANCETE: adapter_balancete, dl.TIPO_RAZAO: adapter_razao, dl.TIPO_BOOK: adapter_book,
            dl.TIPO_PAGAMENTOS_ECAC: _adapter_caixinha(dl._ecac, "PAGAMENTOS_TRIBUTARIOS_NORMALIZADOS_V1", "pagamentos"),
            dl.TIPO_SITUACAO_FISCAL: _adapter_caixinha(dl._situacao, "SITUACAO_FISCAL_NORMALIZADA_V1", "itens"),
            dl.TIPO_RESUMO_FOLHA_DOMINIO: _adapter_caixinha(dl._folha_dominio, "RESUMO_FOLHA_DOMINIO_V1", "rubricas")}

# Documentos lidos pelos agentes já existentes (o reconhecimento final vem do resultado da área: NAO_RECONHECIDO → layout novo).
LEITOR_DA_AREA = {"Notas fiscais": "Fiscal (NF-e XML / NFS-e por rótulos)", "Impostos, guias e apurações": "Fiscal (guias e apurações por rótulos)",
                  "Extratos bancários": "Normalizador bancário do Financeiro", "Relatórios financeiros": "Normalizador financeiro",
                  "Comprovantes, títulos e posições": "Financeiro (suportes por rótulos)",
                  "Folha e documentos de pessoal": "DP (layouts documentados de folha, encargos e provisões)",
                  "Confirmações e saldos de abertura": "Conciliação (layouts documentados)"}


def reconhecer(item: dict, extraido: dict, clientes, empresa: str, resultados_area: dict = None) -> dict:
    """Situação de leitura de UM documento: adapter existente, layout novo (adapter necessário) ou não reconhecido.
    resultados_area: {arquivo: tipo devolvido pelo agente da área} — NAO_RECONHECIDO no agente vira LAYOUT_NOVO."""
    cat = categoria(item)
    tipo = str(item.get("tipo") or "")
    base = {"arquivo": item.get("arquivo"), "sha256": item.get("sha256"), "tipo": tipo, **cat}
    if cat["departamento"] == "A_CONFERIR":
        return dict(base, situacao=NAO_RECONHECIDO, adapter=None, contrato=None,
                    motivo="Leitura pendente; conferir o original." if item.get("leitura_pendente") else
                           (item.get("encaminhamento") or {}).get("observacao") or "Área não identificada; destino não presumido.")
    if tipo in ADAPTERS:
        normal, motivo = ADAPTERS[tipo](item, extraido or {}, clientes, empresa)
        if normal:
            return dict(base, situacao=ADAPTER_EXISTENTE, adapter=normal["adapter"], contrato=normal["contrato"], normalizado=normal)
        return dict(base, situacao=LAYOUT_NOVO, adapter=None, contrato=None, motivo=motivo)
    leitor = LEITOR_DA_AREA.get(cat["categoria"])
    devolvido = (resultados_area or {}).get(item.get("arquivo"))
    if devolvido == "NAO_RECONHECIDO":
        return dict(base, situacao=LAYOUT_NOVO, adapter=None, contrato=None,
                    motivo=f"O agente da área ({leitor or cat['departamento']}) não reconheceu o layout; adapter necessário.")
    return dict(base, situacao=ADAPTER_EXISTENTE, adapter=leitor or "Leitura da área", contrato=None,
                observacao=None if devolvido else "Leitura confirmada quando a área executar.")


# ---------------------------------------------------------------- obrigações (OBRIGACAO_TRIBUTARIA_NORMALIZADA_V1)
def _dec(v):
    try:
        return None if v in (None, "") else Decimal(str(v))
    except InvalidOperation:
        return None


def obrigacoes_de_resultados(fiscal: dict = None, dp: dict = None, proveniencia=None) -> list:
    """ADAPTER de contrato: resultados FISCAL_LOCAL_V1 (apurações e guias) e DP_LOCAL_V1 (encargos/folha) → obrigações
    normalizadas. Só campos lidos pelos agentes; o que faltar fica None com pendência (nada é deduzido)."""
    saida = []
    prov = proveniencia or (lambda dep, d: {})
    for d in (fiscal or {}).get("documentos", []):
        if d.get("tipo") not in ("APURACAO_TRIBUTO", "GUIA") or d.get("duplicado_de"):
            continue
        total = _dec(d.get("valor"))
        pend = []
        if d.get("tipo") == "GUIA" and not d.get("tributo"):
            pend.append("Tributo não identificado pelo leitor da guia (somente o código da receita).")
        if total is None:
            pend.append("Valor total não identificado.")
        saida.append({"contrato": "OBRIGACAO_TRIBUTARIA_NORMALIZADA_V1", "id": f"OBR-{d['id']}", "departamento": "FISCAL",
                      "origem_tipo": "APURACAO" if d["tipo"] == "APURACAO_TRIBUTO" else "GUIA",
                      "tributo": d.get("tributo"), "codigo": d.get("codigo_receita"), "competencia": d.get("competencia"),
                      "periodo": d.get("competencia"), "vencimento": d.get("vencimento"), "principal": None, "multa": None, "juros": None,
                      "total": None if total is None else f"{total:.2f}", "cnpj": d.get("titular_cnpj"), "numero": d.get("numero"),
                      "documento": d.get("arquivo"), "sha256": d.get("sha256"), "pendencias": pend + list(d.get("pendencias") or []),
                      "papel": "PROVISAO" if d["tipo"] == "APURACAO_TRIBUTO" else "COBRANCA",
                      "proveniencia": prov("FISCAL", d)})
    rotulos = {"TOTAL INSS A RECOLHER": "INSS (folha)", "TOTAL FGTS A RECOLHER": "FGTS", "LIQUIDO A PAGAR": "Salários líquidos a pagar"}
    for d in (dp or {}).get("documentos", []):
        for chave, nome in rotulos.items():
            v = _dec((d.get("totais") or {}).get(chave))
            if v is None:
                continue
            saida.append({"contrato": "OBRIGACAO_TRIBUTARIA_NORMALIZADA_V1" if chave != "LIQUIDO A PAGAR" else "OBRIGACAO_TRABALHISTA_V1",
                          "id": f"OBR-{d['id']}-{re.sub(r'[^A-Z]', '', chave)[:12]}", "departamento": "DP", "origem_tipo": d.get("tipo"),
                          "tributo": nome, "codigo": None, "competencia": d.get("competencia"), "periodo": d.get("competencia"),
                          "vencimento": None, "principal": None, "multa": None, "juros": None, "total": f"{v:.2f}", "cnpj": d.get("cnpj"),
                          "numero": d.get("numero"), "documento": d.get("arquivo"), "sha256": d.get("sha256"),
                          "pendencias": list(d.get("pendencias") or []), "papel": "PROVISAO", "proveniencia": prov("DP", d)})
    return saida


def validar(contrato: str, itens: list) -> list:
    """Campos obrigatórios ausentes por item (lista de problemas). Contrato desconhecido → erro explícito."""
    if contrato not in CONTRATOS:
        raise ValueError(f"Contrato desconhecido: {contrato}")
    obrig = CONTRATOS[contrato]
    probs = []
    for n, it in enumerate(itens, 1):
        faltam = [c for c in obrig if (it.get(c) if c != "tributo_ou_codigo" else (it.get("tributo") or it.get("codigo"))) in (None, "")]
        if faltam:
            probs.append(f"item {n}: campo(s) ausente(s) {', '.join(faltam)}")
    return probs
