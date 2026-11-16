"""RAZÃO CONTÁBIL em PDF do Domínio → RAZAO_CONTABIL_NORMALIZADO_V1 (adapter do MOTOR GERAL; sem dado nem regra de empresa).

Mesma técnica do leitor do balancete (balancete_anterior._palavras): as colunas são reconhecidas pela POSIÇÃO do cabeçalho de cada
página (Data · Lote · Histórico · Débito · Crédito · Saldo · C.Part.), não pela ordem do texto extraído — no texto corrido não há como
saber se um valor isolado é débito ou crédito.
- seção de cada conta: linha "Conta: <código> - <classificação> <descrição>" (ou "Conta: <classificação> <descrição> ... Código: <n>");
- "Saldo anterior" da conta (D/C); lançamentos com data dd/mm/aaaa, lote, histórico (inclusive continuado na linha seguinte),
  débito/crédito pela coluna, saldo D/C e contrapartida quando informada;
- conferência aritmética exata: saldo anterior + débitos − créditos = saldo de cada linha (positivo = devedor, negativo = credor).
Página sem cabeçalho reconhecido fica registrada como limite (nada é presumido). Layout a homologar com o arquivo real.
"""
import io
import re
from decimal import Decimal

import balancete_anterior as ba

LEITOR = "RAZAO_PDF_DOMINIO_COLUNAS_V1"
SITUACAO_LEITOR = "LAYOUT_A_HOMOLOGAR"
DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
Z = Decimal("0")


def _cabecalho(linhas):
    for i, l in enumerate(linhas):
        k = [ba.chave(p["t"]) for p in l["p"]]
        if "DATA" in k and any(x.startswith("HIST") for x in k) and any(x.startswith("DEBITO") for x in k) \
                and any(x.startswith("CREDITO") for x in k) and any(x.startswith("SALDO") for x in k):
            ps = l["p"]
            achar = lambda pref: next((p for p in ps if ba.chave(p["t"]).startswith(pref)), None)  # noqa: E731
            data, hist, deb, cre, saldo = achar("DATA"), achar("HIST"), achar("DEBITO"), achar("CREDITO"), achar("SALDO")
            lote = achar("LOTE")
            cpart = next((p for p in ps if ba.chave(p["t"]).replace(" ", "") in ("C.PART.", "C.PART", "CPART", "CONTRAPARTIDA", "CTA.C.PART.",
                                                                                  "CONTRA-PARTIDA")), None)
            return i, {"lote_de": lote["x0"] - 2 if lote else None, "hist_de": hist["x0"] - 2,
                       "valores_de": min(deb["x0"], cre["x0"]) - 60,
                       "direitas": {"debito": deb["x1"], "credito": cre["x1"], "saldo": max(p["x1"] for p in ps if ba.chave(p["t"]).startswith("SALDO"))},
                       "cpart_de": cpart["x0"] - 4 if cpart else None}
    return None, None


RE_CONTA_A = re.compile(r"^CONTA\s*:?\s*(\d+)\s*-?\s*(\d+(?:\.\d+)+)?\s*-?\s*(.*)$")
RE_CONTA_B = re.compile(r"^CONTA\s*:?\s*(\d+(?:\.\d+)+)\s*-?\s*(.*?)(?:\s+(?:CODIGO|COD\.?|REDUZIDO)\s*:?\s*(\d+))?$")


def _conta(texto):
    t = ba.chave(texto)
    m = RE_CONTA_B.match(t)
    if m and "." in m.group(1):
        return {"codigo": m.group(3), "classificacao": m.group(1), "descricao": m.group(2).strip(" -")}
    m = RE_CONTA_A.match(t)
    if m:
        return {"codigo": m.group(1), "classificacao": m.group(2), "descricao": m.group(3).strip(" -")}
    return None


def _assinado(t):
    v, nat = ba.valor(t)
    return v, nat


def ler(dados: bytes) -> dict:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(io.BytesIO(dados))
    meta = ba._meta_texto(dados)
    contas, lancamentos, limites = [], [], []
    atual, ultimo = None, None
    for n in range(len(pdf)):
        linhas = ba._palavras(pdf[n])
        i_cab, col = _cabecalho(linhas)
        if col is None:
            limites.append(f"Página {n + 1}: cabeçalho de colunas do razão não reconhecido; página não lida.")
            continue
        # contas abertas ANTES do cabeçalho da página (cabeçalho de conta acima das colunas)
        for l in linhas[:i_cab]:
            c = _conta(l["texto"]) if ba.chave(l["p"][0]["t"]).startswith("CONTA") else None
            if c:
                atual = dict(c, saldo_anterior=None, natureza_anterior=None, debitos=Z, creditos=Z, saldo_final=None, lancamentos=0,
                             problemas=[], pagina=n + 1, totais_declarados=None)
                contas.append(atual)
                ultimo = None
        for l in linhas[i_cab + 1:]:
            ps = l["p"]
            primeiro = ba.chave(ps[0]["t"])
            if primeiro.startswith("CONTA"):
                c = _conta(l["texto"])
                if c:
                    atual = dict(c, saldo_anterior=None, natureza_anterior=None, debitos=Z, creditos=Z, saldo_final=None, lancamentos=0,
                                 problemas=[], pagina=n + 1, totais_declarados=None)
                    contas.append(atual)
                    ultimo = None
                    continue
            nums = ba._valores_da_zona([p for p in ps if p["x0"] >= col["valores_de"] and (col["cpart_de"] is None or p["x0"] < col["cpart_de"])])
            nums = [x for x in nums if ba.VALOR.fullmatch(x["t"].strip())]
            texto = ba.chave(l["texto"])
            if "SALDO ANTERIOR" in texto and atual is not None:
                if nums:
                    v, nat = _assinado(nums[-1]["t"].strip())
                    atual["saldo_anterior"], atual["natureza_anterior"] = v, nat
                continue
            if texto.startswith("TOTA") and atual is not None:
                vals = {}
                for x in nums:
                    alvo = min(col["direitas"], key=lambda k: abs(col["direitas"][k] - x["x1"]))
                    vals[alvo] = x["t"].strip()
                atual["totais_declarados"] = vals
                continue
            if DATA.fullmatch(ps[0]["t"]) and atual is not None:
                vals, problemas = {}, []
                for x in nums:
                    alvo = min(col["direitas"], key=lambda k: abs(col["direitas"][k] - x["x1"]))
                    if abs(col["direitas"][alvo] - x["x1"]) > 10 or alvo in vals:
                        problemas.append(f"valor {x['t']} fora das colunas reconhecidas")
                        continue
                    vals[alvo] = x["t"].strip()
                lote = [p["t"] for p in ps[1:] if col["lote_de"] is not None and col["lote_de"] <= p["x0"] < col["hist_de"] and p["t"].isdigit()]
                hist = [p["t"] for p in ps[1:] if col["hist_de"] <= p["x0"] < col["valores_de"]]
                hist += [p["t"] for p in ps if col["valores_de"] <= p["x0"] and not any(ch.isdigit() for ch in p["t"])
                         and (col["cpart_de"] is None or p["x0"] < col["cpart_de"])]
                cpart = [p["t"] for p in ps if col["cpart_de"] is not None and p["x0"] >= col["cpart_de"] and re.fullmatch(r"[\d.]+", p["t"])]
                deb = ba.valor(vals.get("debito"))[0] if vals.get("debito") else Z
                cre = ba.valor(vals.get("credito"))[0] if vals.get("credito") else Z
                if deb is None or cre is None or (deb and deb < 0) or (cre and cre < 0):
                    problemas.append("débito/crédito ilegível")
                    deb, cre = deb or Z, cre or Z
                saldo = ba.valor(vals["saldo"])[0] if vals.get("saldo") else None
                if not deb and not cre:
                    problemas.append("lançamento sem débito nem crédito")
                lan = {"pagina": n + 1, "data": ba._iso(ps[0]["t"]), "lote": lote[0] if lote else None, "historico": " ".join(hist).strip(),
                       "debito": f"{abs(deb):.2f}", "credito": f"{abs(cre):.2f}", "saldo": None if saldo is None else f"{saldo:.2f}",
                       "contrapartida": "".join(cpart) or None, "conta": atual.get("codigo") or atual.get("classificacao"),
                       "codigo": atual.get("codigo"), "classificacao": atual.get("classificacao"), "descricao_conta": atual.get("descricao"),
                       "problemas": problemas}
                atual["debitos"] += abs(deb)
                atual["creditos"] += abs(cre)
                atual["lancamentos"] += 1
                esperado = (atual["saldo_anterior"] if atual["saldo_anterior"] is not None else None)
                if esperado is not None:
                    esperado = esperado + atual["debitos"] - atual["creditos"]
                    if saldo is not None and saldo != esperado:
                        lan["problemas"].append(f"saldo da linha ({saldo:.2f}) ≠ anterior + débitos − créditos ({esperado:.2f})")
                if saldo is not None:
                    atual["saldo_final"] = saldo
                lancamentos.append(lan)
                ultimo = lan
                continue
            if ultimo is not None and not nums and all(col["hist_de"] <= p["x0"] < col["valores_de"] for p in ps):
                ultimo["historico"] = (ultimo["historico"] + " " + l["texto"]).strip()      # histórico continuado
    for c in contas:
        if c["saldo_anterior"] is None:
            c["problemas"].append("saldo anterior não identificado na seção da conta")
        elif c["saldo_final"] is None:
            c["saldo_final"] = c["saldo_anterior"] + c["debitos"] - c["creditos"]
        td = c.get("totais_declarados") or {}
        for lado, campo in (("debito", "debitos"), ("credito", "creditos")):
            if td.get(lado):
                v = ba.valor(td[lado])[0]
                if v is not None and abs(v) != c[campo]:
                    c["problemas"].append(f"total de {campo} declarado ({abs(v):.2f}) ≠ soma das linhas ({c[campo]:.2f})")
        for k in ("saldo_anterior", "debitos", "creditos", "saldo_final"):
            c[k] = None if c[k] is None else f"{c[k]:.2f}"
    return {"formato": "PDF_DOMINIO_RAZAO", "leitor": LEITOR, "situacao_leitor": SITUACAO_LEITOR, "meta": meta, "contas": contas,
            "lancamentos": lancamentos, "limites": limites}


def reconhece(texto: str) -> bool:
    t = ba.chave(texto)
    topo = " ".join(t.split()[:60])
    return bool(re.search(r"\bRAZAO\b(?! SOCIAL)", topo)) and "DEBITO" in t and "CREDITO" in t and "HISTORICO" in t
