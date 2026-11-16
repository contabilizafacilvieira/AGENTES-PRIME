"""ESPECIALISTA FISCAL · PAGAMENTOS EFETUADOS NO e-CAC → PAGAMENTOS_TRIBUTARIOS_NORMALIZADOS_V1 (contrato próprio; NÃO é extrato).

Leitura local, determinística, por rótulos do próprio documento (nunca pelo nome do arquivo). Layouts aceitos (texto do PDF/TXT):
  A) Comprovante / consulta com blocos por documento: "Tipo do Documento:", "Número do Documento:", "Período de Apuração:",
     "Data de Arrecadação:", "Data de Vencimento:", "Valor Total:" (+ opcionais "Código de Receita:", "Número de Referência:") e
     a seção "Composição do Documento de Arrecadação" com linhas "Código Denominação Principal Multa Juros Total".
  C) "Comprovante de Arrecadação" emitido pelo e-CAC (um documento por página): "Comprovamos que consta nos sistemas da Receita
     Federal registro de arrecadação de <DAS|DARF>"; rótulos (Competência/Período Apuração · Data de Vencimento · Número do Documento)
     numa linha e os valores na linha seguinte; composição; "Totais"; data de arrecadação e valor reservado/restituído no rodapé
     (layout conferido com o arquivo real da empresa piloto em 16/11/2026).
  B) Lista tabular "Tipo · Número do Documento · Período de Apuração · Data de Arrecadação · Data de Vencimento · Código de
     Receita · [Número de Referência] · Valor Total · [Saldo]" (uma linha por pagamento, sem composição).
ATENÇÃO: os layouts acima seguem os rótulos publicados pelo e-CAC; a homologação com o arquivo real da empresa piloto é obrigatória
antes do uso real (leitor marcado LAYOUT_A_HOMOLOGAR até lá).

Regras (nada é inventado):
- Evidência de PAGAMENTO = "Data de Arrecadação" do e-CAC. Bloco sem ela é GUIA_SEM_COMPROVACAO e nunca gera baixa.
- Composição: soma principal+multa+juros = total do componente e soma dos componentes = valor total (igualdade exata). Composição
  incoerente ou ausente em documento com mais de um tributo → pendência; a divisão NUNCA é presumida.
- Sem composição e com UM código de receita: o total pertence a esse tributo; principal = total só se pago até o vencimento
  (critério registrado). Pago após o vencimento sem composição → pendência (multa/juros não separados).
- Identidade do pagamento = dados de negócio (empresa + CNPJ + tipo + número do documento; sem número: código + PA + data + valor).
  O mesmo pagamento em documentos diferentes é UM pagamento (duplicidade registrada); nome/sha256 do arquivo não identificam pagamento.
"""
import re
import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ / "API-LOCAL") not in sys.path:
    sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import caixinha_comum as cc  # noqa: E402

CONTRATO = "PAGAMENTOS_TRIBUTARIOS_NORMALIZADOS_V1"
CONTRATO_ITEM = "PAGAMENTO_TRIBUTARIO_V1"
LEITOR = "ECAC_PAGAMENTOS_ROTULOS_V1"
SITUACAO_LEITOR = "CONFERIDO_COM_ARQUIVO_REAL_PILOTO"
TIPOS_DOC = ("DARF", "DAS", "DASN", "GPS", "DAE", "DJE", "DARF NUMERADO")
ROTULOS = {"TIPO DO DOCUMENTO": "tipo", "NUMERO DO DOCUMENTO": "numero", "PERIODO DE APURACAO": "pa", "DATA DE ARRECADACAO": "arrecadacao",
           "DATA DE VENCIMENTO": "vencimento", "VALOR TOTAL": "total", "CODIGO DE RECEITA": "codigo", "NUMERO DE REFERENCIA": "referencia",
           "VALOR DO PRINCIPAL": "principal", "VALOR DA MULTA": "multa", "VALOR DOS JUROS": "juros"}
RE_ROTULO = re.compile(r"(" + "|".join(sorted(ROTULOS, key=len, reverse=True)) + r")\s*:\s*")
RE_COMPONENTE = re.compile(r"^(\d{4})(?:-\d{2})?\s+(.+?)\s+(" + cc.DINHEIRO + r"|-)\s+(" + cc.DINHEIRO + r"|-)\s+(" + cc.DINHEIRO
                           + r"|-)\s+(" + cc.DINHEIRO + r")$")
RE_LINHA_LISTA = re.compile(r"^(DARF NUMERADO|DARF|DAS|DASN|GPS|DAE|DJE)\s+([\d./-]{6,})\s+(\d{2}/\d{2}/\d{4}|\d{2}/\d{4}|\d{4})\s+"
                            r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(.*)$")


def reconhece(texto: str) -> bool:
    """Estrutura de relatório/comprovante de PAGAMENTOS do e-CAC (rótulo de arrecadação + identificação do documento)."""
    t = cc.norm(texto)
    if "INFORMACOES DE APOIO PARA EMISSAO DE CERTIDAO" in t or "SITUACAO FISCAL" in t:
        return False
    fonte = any(x in t for x in ("RECEITA FEDERAL", "E-CAC", "ECAC", "CENTRO VIRTUAL DE ATENDIMENTO", "COMPROVANTE DE ARRECADACAO",
                                 "CONSULTA DE PAGAMENTOS", "PAGAMENTOS EFETUADOS"))
    return fonte and "DATA DE ARRECADACAO" in t and "NUMERO DO DOCUMENTO" in t


def _rotulos(linha: str) -> dict:
    t = cc.norm(linha)
    achados = list(RE_ROTULO.finditer(t))
    saida = {}
    for i, m in enumerate(achados):
        fim = achados[i + 1].start() if i + 1 < len(achados) else len(t)
        saida[ROTULOS[m.group(1)]] = t[m.end():fim].strip(" ;|")
    return saida


def _dec(s, campo, pend):
    try:
        return cc.valor(s)
    except ValueError:
        pend.append(f"{campo}: valor ilegível ({str(s)[:20]}).")
        return None


def _novo_bloco(pagina, linha):
    return {"campos": {}, "componentes": [], "pagina": pagina, "linha": linha, "pend": [], "em_composicao": False, "totais_composicao": None}


def ler(a: dict, empresa: str, cnpjs_empresa) -> dict:
    """Ficha documental + pagamentos normalizados de UM documento já extraído por Documentos."""
    f = cc.ficha(a, "PAGAMENTOS_ECAC", empresa)
    f["leitor"], f["situacao_leitor"] = LEITOR, SITUACAO_LEITOR
    motivo = cc.leitura_utilizavel(a)
    if motivo:
        f["pendencias"].append(f"Pendência de leitura: {motivo}. Nenhum pagamento aproveitado.")
        return dict(f, pagamentos=[])
    texto = cc.texto_total(a)
    if not reconhece(texto):
        f["pendencias"].append("Estrutura de pagamentos do e-CAC não reconhecida pelo conteúdo; nenhum pagamento aproveitado.")
        return dict(f, pagamentos=[])
    f["reconhecimento"] = "RECONHECIDO"
    cnpjs = cc.cnpjs_no_texto(texto)
    f["cnpj"] = next((c for c in cnpjs if cc.cnpj_confere([c], cnpjs_empresa)), cnpjs[0] if cnpjs else None)
    if not cnpjs:
        f["pendencias"].append("CNPJ do contribuinte não identificado no documento.")
    elif not cc.cnpj_confere(cnpjs, cnpjs_empresa):
        f["pendencias"].append("CNPJ do documento não é da empresa selecionada: nenhum pagamento aproveitado (isolamento entre empresas).")
        return dict(f, pagamentos=[])
    m = re.search(r"(?:DATA DA CONSULTA|EMITIDO EM|GERADO EM|DATA DE EMISSAO|CONSULTA REALIZADA EM|COMPROVANTE EMITIDO AS [\d:]+ DE)\s*:?\s*(\d{2}/\d{2}/\d{4})", cc.norm(texto))
    f["emissao"] = cc.data_iso(m.group(1)) if m else None
    blocos, lista = [], []
    if "COMPROVAMOS QUE CONSTA" in cc.norm(texto):
        blocos = [b for b in (_comprovante_pagina(pg, conteudo) for pg, conteudo in cc.paginas(a)) if b]
    for pagina, conteudo in ([] if blocos else cc.paginas(a)):
        bloco = blocos[-1] if blocos else None
        for n, bruta in enumerate(conteudo.splitlines(), 1):
            linha = cc.norm(bruta)
            if not linha:
                continue
            ml = RE_LINHA_LISTA.match(linha)
            if ml:
                lista.append((pagina, n, ml))
                continue
            r = _rotulos(linha)
            if r and (bloco is None or any(k in r and k in bloco["campos"] for k in ("numero", "tipo"))
                      or (bloco["componentes"] and not bloco["em_composicao"] and ("numero" in r or "tipo" in r))):
                bloco = _novo_bloco(pagina, n)
                blocos.append(bloco)
            if r and bloco is not None:
                for k, v in r.items():
                    if k in bloco["campos"] and bloco["campos"][k] != v:
                        bloco["pend"].append(f"Rótulo {k} repetido com valores diferentes no mesmo documento.")
                    bloco["campos"][k] = v
                continue
            if bloco is None:
                continue
            if "COMPOSICAO DO DOCUMENTO DE ARRECADACAO" in linha:
                bloco["em_composicao"] = True
                continue
            if bloco["em_composicao"]:
                mc = RE_COMPONENTE.match(linha)
                if mc:
                    pend = bloco["pend"]
                    vals = [_dec(mc.group(i), f"componente {mc.group(1)}", pend) for i in (3, 4, 5, 6)]
                    bloco["componentes"].append({"codigo": mc.group(1), "denominacao": mc.group(2).strip(), "principal": vals[0],
                                                 "multa": vals[1], "juros": vals[2], "total": vals[3], "pagina": pagina, "linha": n})
                elif linha.startswith("TOTA"):
                    vs = cc.RE_DINHEIRO.findall(linha)
                    bloco["totais_composicao"] = vs
                    bloco["em_composicao"] = False
    pagamentos = [_pagamento_bloco(b, f, empresa) for b in blocos if b["campos"]]
    pagamentos += [_pagamento_lista(p, n, ml, f, empresa) for p, n, ml in lista]
    if not pagamentos:
        f["pendencias"].append("Nenhum pagamento identificado no documento.")
    f["dados"] = {"pagamentos": len(pagamentos), "comprovados": sum(p["evidencia"] == "PAGAMENTO_REGISTRADO_ECAC" for p in pagamentos),
                  "guias_sem_comprovacao": sum(p["evidencia"] == "GUIA_SEM_COMPROVACAO" for p in pagamentos)}
    datas = sorted(p["data_pagamento"] for p in pagamentos if p.get("data_pagamento"))
    f["periodo"] = {"inicio": datas[0], "fim": datas[-1]} if datas else None
    return dict(f, pagamentos=pagamentos)


RE_VALORES_COMPROVANTE = re.compile(r"^(\d{2}/\d{4}|\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d{10,20})$")


def _comprovante_pagina(pagina, conteudo):
    """Layout C: um Comprovante de Arrecadação por página. Valores sem rótulo na mesma linha → posição fixa (PA, vencimento,
    número); data de arrecadação = primeira data depois do rótulo "Data de Arrecadação"; nada é deduzido além disso."""
    t = cc.norm(conteudo)
    if "COMPROVAMOS QUE CONSTA" not in t:
        return None
    b = _novo_bloco(pagina, 1)
    m = re.search(r"ARRECADACAO DE (DARF NUMERADO|DARF|DAS|DASN|GPS|DAE|DJE)\b", t)
    if m:
        b["campos"]["tipo"] = m.group(1)
    linhas = [cc.norm(x) for x in conteudo.splitlines()]
    for n, linha in enumerate(linhas, 1):
        mv = RE_VALORES_COMPROVANTE.match(linha)
        if mv and "numero" not in b["campos"]:
            b["campos"].update(pa=mv.group(1), vencimento=mv.group(2), numero=mv.group(3))
            b["linha"] = n
            continue
        mc = RE_COMPONENTE.match(linha)
        if mc:
            pend = b["pend"]
            vals = [_dec(mc.group(i), f"componente {mc.group(1)}", pend) for i in (3, 4, 5, 6)]
            b["componentes"].append({"codigo": mc.group(1), "denominacao": mc.group(2).strip(), "principal": vals[0], "multa": vals[1],
                                     "juros": vals[2], "total": vals[3], "pagina": pagina, "linha": n})
            continue
        if linha.startswith("TOTAIS"):
            vs = cc.RE_DINHEIRO.findall(linha)
            if vs:
                b["campos"]["total"] = vs[-1]
    i = t.find("DATA DE ARRECADACAO")
    if i >= 0:
        resto = t[i:]
        md = cc.RE_DATA.search(resto)
        if md:
            b["campos"]["arrecadacao"] = md.group(0)
            reservado = cc.RE_DINHEIRO.findall(resto[md.end():])
            if reservado and cc.valor(reservado[-1]) != 0:
                b["pend"].append(f"Valor reservado/restituído informado ({reservado[-1]}): conferir antes da baixa.")
    if "numero" not in b["campos"]:
        b["pend"].append("Linha com período de apuração, vencimento e número do documento não identificada no comprovante.")
    return b


def _identidade(empresa, cnpj, tipo, numero, codigo, pa, data, total) -> str:
    if numero and len(cc.digitos(numero)) >= 6:
        return "PAG-" + cc.chave_hash(empresa, cc.digitos(cnpj), tipo, cc.digitos(numero))
    return "PAG-" + cc.chave_hash(empresa, cc.digitos(cnpj), tipo, codigo, pa, data, total)


def _base(f, empresa, pagina, linha):
    return {"contrato": CONTRATO_ITEM, "empresa": empresa, "cnpj": f["cnpj"], "documento": f["id"],
            "origem": {"documento": f["id"], "arquivo": f["arquivo"], "sha256": f["sha256"], "pagina": pagina, "linha": linha,
                       "leitor": LEITOR}, "pendencias": []}


def _finalizar(p):
    p["valor_total"] = cc.txt(p["valor_total"]) if p["valor_total"] is not None else None
    for c in p["componentes"]:
        for k in ("principal", "multa", "juros", "total"):
            c[k] = cc.txt(c[k]) if c.get(k) is not None else None
    p["utilizavel"] = p["evidencia"] == "PAGAMENTO_REGISTRADO_ECAC" and not p["pendencias"] and bool(p["componentes"])
    return p


def _pagamento_bloco(b, f, empresa):
    c = b["campos"]
    p = _base(f, empresa, b["pagina"], b["linha"])
    pend = p["pendencias"] + b["pend"]
    p["pendencias"] = pend
    tipo = next((t for t in TIPOS_DOC if c.get("tipo", "").startswith(t)), c.get("tipo") or None)
    pa = cc.periodo_apuracao(c.get("pa"))
    total = _dec(c.get("total"), "valor total", pend) if c.get("total") else None
    data = cc.data_iso(c.get("arrecadacao"))
    venc = cc.data_iso(c.get("vencimento"))
    codigo = (re.match(r"(\d{4})", c.get("codigo") or "") or [None, None])[1] if c.get("codigo") else None
    p.update(tipo_documento=tipo, numero_documento=c.get("numero") or None, periodo_apuracao=pa, data_pagamento=data, data_vencimento=venc,
             valor_total=total, referencia=c.get("referencia") or None, codigo_receita=codigo,
             evidencia="PAGAMENTO_REGISTRADO_ECAC" if data else "GUIA_SEM_COMPROVACAO")
    if not data:
        pend.append("Sem data de arrecadação: guia sem comprovação de pagamento (não gera baixa).")
    if total is None:
        pend.append("Valor total não identificado.")
    if not pa:
        pend.append("Período de apuração não identificado.")
    comps = b["componentes"]
    if comps:
        for x in comps:
            soma = sum(((x.get(k) or cc.Z) for k in ("principal", "multa", "juros")), cc.Z)
            if x["total"] is None or soma != x["total"]:
                pend.append(f"Componente {x['codigo']}: principal + multa + juros ({soma:.2f}) ≠ total ({x['total']}); composição não utilizada.")
        soma_total = sum((x["total"] or cc.Z for x in comps), cc.Z)
        if total is not None and soma_total != total:
            pend.append(f"Soma da composição ({soma_total:.2f}) ≠ valor total do documento ({total:.2f}); divisão não utilizada.")
        p["composicao"] = "INFORMADA"
        p["componentes"] = [dict(x, criterio="composição informada no documento") for x in comps]
    elif codigo and total is not None:
        if data and venc and data <= venc and not any(c.get(k) for k in ("multa", "juros")):
            p["composicao"] = "CODIGO_UNICO_PAGO_NO_PRAZO"
            p["componentes"] = [{"codigo": codigo, "denominacao": None, "principal": total, "multa": cc.Z, "juros": cc.Z, "total": total,
                                 "pagina": b["pagina"], "linha": b["linha"],
                                 "criterio": "um único código de receita e pagamento até o vencimento: total = principal (sem acréscimos)"}]
        else:
            p["composicao"] = "NAO_INFORMADA"
            p["componentes"] = []
            pend.append("Pagamento após o vencimento (ou vencimento ausente) sem composição: principal, multa e juros não separados.")
    else:
        p["composicao"] = "NAO_INFORMADA"
        p["componentes"] = []
        pend.append("Composição do documento não disponível e código de receita não único: a divisão entre tributos NÃO é presumida.")
    p["id"] = _identidade(empresa, f["cnpj"], tipo, p["numero_documento"], codigo or ",".join(x["codigo"] for x in p["componentes"]),
                          (pa or {}).get("texto"), data, c.get("total"))
    return _finalizar(p)


def _pagamento_lista(pagina, n, ml, f, empresa):
    p = _base(f, empresa, pagina, n)
    pend = p["pendencias"]
    resto = ml.group(6).split()
    valores = [x for x in resto if re.fullmatch(cc.DINHEIRO, x)]
    outros = [x for x in resto if not re.fullmatch(cc.DINHEIRO, x)]
    codigo = next((x for x in outros if re.fullmatch(r"\d{4}(?:-\d{2})?", x)), None)
    codigo = codigo[:4] if codigo else None
    total = _dec(valores[0], "valor total", pend) if valores else None
    if total is None:
        pend.append("Valor total não identificado na linha da lista.")
    pa = cc.periodo_apuracao(ml.group(3))
    data, venc = cc.data_iso(ml.group(4)), cc.data_iso(ml.group(5))
    p.update(tipo_documento=ml.group(1), numero_documento=ml.group(2), periodo_apuracao=pa, data_pagamento=data, data_vencimento=venc,
             valor_total=total, referencia=None, codigo_receita=codigo, evidencia="PAGAMENTO_REGISTRADO_ECAC" if data else "GUIA_SEM_COMPROVACAO")
    if codigo and total is not None and data and venc and data <= venc:
        p["composicao"] = "CODIGO_UNICO_PAGO_NO_PRAZO"
        p["componentes"] = [{"codigo": codigo, "denominacao": None, "principal": total, "multa": cc.Z, "juros": cc.Z, "total": total,
                             "pagina": pagina, "linha": n,
                             "criterio": "um único código de receita e pagamento até o vencimento: total = principal (sem acréscimos)"}]
    else:
        p["composicao"] = "NAO_INFORMADA"
        p["componentes"] = []
        pend.append("Lista sem composição: código de receita ausente/múltiplo ou pagamento após o vencimento; divisão NÃO presumida "
                    "(envie o comprovante com a composição).")
    p["id"] = _identidade(empresa, f["cnpj"], ml.group(1), ml.group(2), codigo, ml.group(3), data, valores[0] if valores else None)
    return _finalizar(p)


def consolidar(fichas: list) -> dict:
    """Pagamentos de TODOS os documentos: a mesma identidade em documentos diferentes é UM pagamento (duplicidade documental,
    registrada). Mesma identidade com valores diferentes → conflito (nenhuma versão aproveitada). Mesmo código + PA + valor com
    números de documento DIFERENTES → possível PAGAMENTO DUPLICADO (para revisão; nada é baixado em dobro)."""
    por_id, conflitos, repetidos = {}, [], []
    for f in fichas:
        for p in f.get("pagamentos", []):
            if p["id"] in por_id:
                q = por_id[p["id"]]
                assinatura = lambda x: (x["valor_total"], x["data_pagamento"], tuple((c["codigo"], c["total"]) for c in x["componentes"]))  # noqa: E731
                if assinatura(q) == assinatura(p) or not p["componentes"] or not q["componentes"]:
                    q.setdefault("tambem_em", []).append(p["origem"])
                    repetidos.append({"pagamento": p["id"], "documentos": [q["origem"]["arquivo"], p["origem"]["arquivo"]],
                                      "tipo": "MESMO_PAGAMENTO_EM_MAIS_DE_UM_DOCUMENTO"})
                    if p["componentes"] and not q["componentes"]:
                        q.update(componentes=p["componentes"], composicao=p["composicao"], pendencias=[x for x in q["pendencias"] if "omposi" not in x],
                                 utilizavel=p["utilizavel"])
                else:
                    conflitos.append(p["id"])
                    q["pendencias"].append("Mesmo documento de arrecadação com valores diferentes em outro arquivo: nenhuma versão aproveitada.")
                    q["utilizavel"] = False
                continue
            por_id[p["id"]] = p
    pagamentos = list(por_id.values())
    grupos = {}
    for p in pagamentos:
        if p["evidencia"] != "PAGAMENTO_REGISTRADO_ECAC":
            continue
        chave = ((p.get("periodo_apuracao") or {}).get("texto"), p.get("valor_total"),
                 tuple(sorted(c["codigo"] for c in p["componentes"])) or p.get("codigo_receita"))
        grupos.setdefault(chave, []).append(p)
    duplicados = []
    for chave, ps in grupos.items():
        if len(ps) > 1 and chave[0] and chave[1]:
            ids = [p["id"] for p in ps]
            for p in ps:
                p["possivel_duplicidade"] = [i for i in ids if i != p["id"]]
            duplicados.append({"pagamentos": ids, "periodo": chave[0], "valor": chave[1],
                               "texto": "Mais de um pagamento com o mesmo período, código e valor e números de documento diferentes: "
                                        "possível pagamento em duplicidade (revisão do Supervisor; nenhuma baixa em dobro)."})
    return {"contrato": CONTRATO, "pagamentos": sorted(pagamentos, key=lambda p: (p.get("data_pagamento") or "", p["id"])),
            "repetidos_entre_documentos": repetidos, "conflitos": conflitos, "possiveis_duplicidades": duplicados}
