"""ESPECIALISTA DP · RESUMO MENSAL DA FOLHA emitido pelo Domínio → RESUMO_FOLHA_DOMINIO_V1 (folha e pró-labore).

Complementa os layouts documentados do DP (AGENTES/DP/PROCEDIMENTO.md) sem alterá-los. Leitura local por rótulos:
- cabeçalho: "Empresa:", "CNPJ:", "Competência:" (MM/AAAA) e, quando houver, "Empregado:/Contribuinte:/Sócio:/Nome:";
- linhas de rubrica: código, descrição, [referência], valor;
- totais: "Total de Proventos", "Total de Descontos", "Líquido" (ou "Total Líquido"/"Líquido a Receber").
A coluna (provento × desconto) não é confiável no texto extraído do PDF: cada rubrica é classificada pela DESCRIÇÃO (pró-labore,
salário, horas e adicionais = provento; INSS, IRRF, contribuições, adiantamentos e descontos = desconto). A classificação só é aceita
se as somas conferirem EXATAMENTE com os totais declarados e Proventos − Descontos = Líquido; senão, pendência (nada é presumido).
Variante por SEÇÕES (relatório "Resumo da Folha" do Domínio conferido com o arquivo real em 16/11/2026): blocos PROVENTOS e
DESCONTOS, cada um com "<valor>Total:", e "<valor>Líquido Geral:"; linha de rubrica "<NOME><código> <nº contribuintes> <referência>
<valor>". Nessa variante o tipo (provento/desconto) vem da SEÇÃO do próprio relatório; o restante (Resumo Geral) não é lido como rubrica.
Não calcula folha, alíquota ou encargo. Layout a homologar com o arquivo real (leitor marcado LAYOUT_A_HOMOLOGAR).
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ / "API-LOCAL") not in sys.path:
    sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import caixinha_comum as cc  # noqa: E402

CONTRATO = "RESUMO_FOLHA_DOMINIO_V1"
LEITOR = "DOMINIO_RESUMO_FOLHA_ROTULOS_V1"
SITUACAO_LEITOR = "CONFERIDO_COM_ARQUIVO_REAL_PILOTO"
PROLABORE = ("PRO-LABORE", "PRO LABORE", "PROLABORE", "RETIRADA PRO", "RETIRADA DE SOCIO")
PROVENTOS = PROLABORE + ("SALARIO", "HORAS EXTRAS", "HORA EXTRA", "ADICIONAL", "COMISS", "GRATIFICA", "FERIAS", "13", "DSR", "AUXILIO",
                         "PREMIO", "INSALUBRIDADE", "PERICULOSIDADE", "SALARIO FAMILIA")
DESCONTOS = {"INSS": "RETENCAO_INSS", "I.N.S.S": "RETENCAO_INSS", "IRRF": "RETENCAO_IRRF", "I.R.R.F": "RETENCAO_IRRF", "IMPOSTO DE RENDA": "RETENCAO_IRRF",
             "CONTRIBUICAO": "OUTRO_DESCONTO", "ADIANTAMENTO": "ADIANTAMENTO", "DESCONTO": "OUTRO_DESCONTO", "FALTA": "OUTRO_DESCONTO",
             "VALE": "OUTRO_DESCONTO", "PENSAO": "OUTRO_DESCONTO", "EMPRESTIMO": "OUTRO_DESCONTO", "CONSIGNADO": "OUTRO_DESCONTO"}
RE_RUBRICA = re.compile(r"^(\d{1,5})\s+(.+?)\s+((?:" + cc.DINHEIRO + r"|\d+(?:,\d+)?)\s+)?(" + cc.DINHEIRO + r")$")
RE_TOTAL = {"proventos": re.compile(r"TOTAL (?:DE |DOS )?PROVENTOS\s*:?\s*(" + cc.DINHEIRO + ")"),
            "descontos": re.compile(r"TOTAL (?:DE |DOS )?DESCONTOS\s*:?\s*(" + cc.DINHEIRO + ")"),
            "liquido": re.compile(r"(?:TOTAL )?LIQUIDO(?: A RECEBER| A PAGAR)?\s*:?\s*(" + cc.DINHEIRO + ")")}
RE_PESSOA = re.compile(r"(?:EMPREGADO|CONTRIBUINTE|SOCIO|NOME)\s*:\s*(?:(\d+)\s*-?\s*)?([A-Z][A-Z .'-]{2,80}?)(?:\s{2,}|\s+(?:CPF|CARGO|ADMISSAO)|$)")


def reconhece(texto: str) -> bool:
    t = cc.norm(texto)
    if "RUBRICA;TIPO;VALOR" in t:          # layout documentado do DP (analise_dp.py) — não é o relatório do Domínio
        return False
    titulo = "RESUMO MENSAL" in t or "RESUMO DA FOLHA" in t or "RESUMO GERAL DA FOLHA" in t
    return titulo and "PROVENTOS" in t and "DESCONTOS" in t and "LIQUIDO" in t


RE_RUBRICA_SECAO = re.compile(r"^(.+?)(\d{1,5})\s+(\d+)\s+(\d+(?:,\d+)?)\s+(" + cc.DINHEIRO + r")$")
RE_TOTAL_SECAO = re.compile(r"^(" + cc.DINHEIRO + r")\s*TOTAL:?$")
RE_LIQUIDO_SECAO = re.compile(r"^(" + cc.DINHEIRO + r")\s*LIQUIDO GERAL:?$")


def _por_secoes(a: dict):
    """(rubricas, totais) da variante por seções, ou None se o documento não tiver essa estrutura."""
    linhas = [(pg, n, cc.norm(x)) for pg, conteudo in cc.paginas(a) for n, x in enumerate(conteudo.splitlines(), 1)]
    if not any(x == "PROVENTOS" for _, _, x in linhas) or not any(RE_LIQUIDO_SECAO.match(x) for _, _, x in linhas):
        return None
    rubricas, totais, secao = [], {}, None
    for pg, n, x in linhas:
        if x in ("PROVENTOS", "DESCONTOS"):
            secao = x
            continue
        ml = RE_LIQUIDO_SECAO.match(x)
        if ml:
            totais["liquido"] = {"valor": cc.valor(ml.group(1)), "pagina": pg, "linha": n}
            break                                            # depois do Líquido Geral vem o Resumo Geral (bases, encargos)
        mt = RE_TOTAL_SECAO.match(x)
        if mt and secao:
            totais["proventos" if secao == "PROVENTOS" else "descontos"] = {"valor": cc.valor(mt.group(1)), "pagina": pg, "linha": n}
            secao = None
            continue
        mr = RE_RUBRICA_SECAO.match(x)
        if mr and secao:
            desc = mr.group(1).strip()
            _, evento = _natureza(desc)
            if secao == "PROVENTOS":
                tipo, evento = "PROVENTO", ("PRO_LABORE" if evento == "PRO_LABORE" else "OUTRO_PROVENTO")
            else:
                tipo, evento = "DESCONTO", (evento if evento in ("RETENCAO_INSS", "RETENCAO_IRRF", "ADIANTAMENTO") else "OUTRO_DESCONTO")
            rubricas.append({"codigo": mr.group(2), "descricao": desc, "referencia": mr.group(4), "contribuintes": mr.group(3),
                             "valor": cc.valor(mr.group(5)), "tipo": tipo, "evento": evento, "pagina": pg, "linha": n})
    return rubricas, totais


def _natureza(desc: str):
    d = cc.norm(desc)
    if any(x in d for x in PROLABORE):
        return "PROVENTO", "PRO_LABORE"
    for k, v in DESCONTOS.items():
        if re.search(r"(?<![A-Z])" + re.escape(k) + r"(?![A-Z])", d):
            return "DESCONTO", v
    if any(x in d for x in PROVENTOS):
        return "PROVENTO", "OUTRO_PROVENTO"
    return None, None


def ler(a: dict, empresa: str, cnpjs_empresa) -> dict:
    f = cc.ficha(a, "RESUMO_FOLHA_DOMINIO", empresa)
    f["leitor"], f["situacao_leitor"] = LEITOR, SITUACAO_LEITOR
    vazio = {"rubricas": [], "totais": {}, "pessoas": [], "pro_labore": None}
    motivo = cc.leitura_utilizavel(a)
    if motivo:
        f["pendencias"].append(f"Pendência de leitura: {motivo}. Nenhum valor aproveitado.")
        return dict(f, **vazio)
    texto = cc.texto_total(a)
    if not reconhece(texto):
        f["pendencias"].append("Estrutura do Resumo Mensal da Folha do Domínio não reconhecida pelo conteúdo.")
        return dict(f, **vazio)
    f["reconhecimento"] = "RECONHECIDO"
    t = cc.norm(texto)
    cnpjs = cc.cnpjs_no_texto(texto)
    if not cnpjs:
        f["pendencias"].append("CNPJ não identificado no resumo da folha.")
    elif not cc.cnpj_confere(cnpjs, cnpjs_empresa):
        f["pendencias"].append("CNPJ do resumo não é da empresa selecionada: documento não aproveitado (isolamento entre empresas).")
        return dict(f, **vazio)
    f["cnpj"] = next((c for c in cnpjs if cc.cnpj_confere([c], cnpjs_empresa)), None)
    comps = set(re.findall(r"COMPETENCIA\s*:?\s*(\d{2}/\d{4})", t)) | set(re.findall(r"REFERENCIA\s*:?\s*(?:MENSAL\s*)?(\d{2}/\d{4})", t))
    if len(comps) != 1:
        f["pendencias"].append("Competência (MM/AAAA) ausente ou mais de uma no documento.")
    else:
        f["competencia"] = cc.periodo_apuracao(comps.pop())["competencia"]
    m = re.search(r"(?:EMITIDO EM|DATA DE EMISSAO|EMISSAO)\s*:?\s*(\d{2}/\d{2}/\d{4})", t)
    f["emissao"] = cc.data_iso(m.group(1)) if m else None
    rubricas, totais, pessoas, pend = [], {}, [], f["pendencias"]
    secoes = _por_secoes(a)
    if secoes:
        rubricas, totais = secoes
        f["leitor"] = LEITOR + "+SECOES"
    for pagina, conteudo in ([] if secoes else cc.paginas(a)):
        for n, bruta in enumerate(conteudo.splitlines(), 1):
            linha = cc.norm(bruta)
            if not linha:
                continue
            achou_total = False
            for k, rx in RE_TOTAL.items():
                for mt in rx.finditer(linha):
                    achou_total = True
                    v = cc.valor(mt.group(1))
                    if k in totais and totais[k]["valor"] != v:
                        pend.append(f"Total de {k} declarado com valores diferentes (páginas {totais[k]['pagina']} e {pagina}).")
                    totais.setdefault(k, {"valor": v, "pagina": pagina, "linha": n})
            if achou_total:
                continue
            mp = RE_PESSOA.search(linha)
            if mp:
                pessoas.append({"codigo": mp.group(1), "nome": mp.group(2).strip(), "pagina": pagina, "linha": n})
                continue
            mr = RE_RUBRICA.match(linha)
            if mr and not linha.startswith("TOTAL"):
                tipo, evento = _natureza(mr.group(2))
                rubricas.append({"codigo": mr.group(1), "descricao": mr.group(2).strip(), "referencia": (mr.group(3) or "").strip() or None,
                                 "valor": cc.valor(mr.group(4)), "tipo": tipo, "evento": evento, "pagina": pagina, "linha": n})
    for r in rubricas:
        if r["tipo"] is None:
            pend.append(f"Rubrica {r['codigo']} {r['descricao']}: natureza (provento/desconto) não reconhecida; nada presumido.")
    faltam = [k for k in ("proventos", "descontos", "liquido") if k not in totais]
    if faltam:
        pend.append("Totais não identificados: " + ", ".join(faltam) + ".")
    if not rubricas:
        pend.append("Nenhuma rubrica identificada.")
    prov = sum((r["valor"] for r in rubricas if r["tipo"] == "PROVENTO"), cc.Z)
    desc = sum((r["valor"] for r in rubricas if r["tipo"] == "DESCONTO"), cc.Z)
    if not faltam:
        tp, td, tl = (totais[k]["valor"] for k in ("proventos", "descontos", "liquido"))
        if prov != tp:
            pend.append(f"Soma dos proventos ({prov:.2f}) ≠ Total de Proventos ({tp:.2f}).")
        if desc != td:
            pend.append(f"Soma dos descontos ({desc:.2f}) ≠ Total de Descontos ({td:.2f}).")
        if tp - td != tl:
            pend.append(f"Proventos − Descontos ({tp - td:.2f}) ≠ Líquido ({tl:.2f}).")
    so_prolabore = bool(rubricas) and all(r["evento"] == "PRO_LABORE" for r in rubricas if r["tipo"] == "PROVENTO")
    pro = None
    if not pend and not faltam:
        bruto = sum((r["valor"] for r in rubricas if r["evento"] == "PRO_LABORE"), cc.Z)
        ret = lambda ev: sum((r["valor"] for r in rubricas if r["evento"] == ev), cc.Z)  # noqa: E731
        pro = {"bruto": cc.txt(bruto), "inss": cc.txt(ret("RETENCAO_INSS")), "irrf": cc.txt(ret("RETENCAO_IRRF")),
               "outros_descontos": cc.txt(desc - ret("RETENCAO_INSS") - ret("RETENCAO_IRRF")),
               "liquido": cc.txt(totais["liquido"]["valor"]) if so_prolabore else None,
               "somente_pro_labore": so_prolabore, "socios": [p["nome"] for p in pessoas],
               "origem": {"documento": f["id"], "arquivo": f["arquivo"], "sha256": f["sha256"], "pagina": totais["liquido"]["pagina"],
                          "linha": totais["liquido"]["linha"], "leitor": LEITOR}}
        if not so_prolabore:
            pend.append("Folha com proventos além de pró-labore: o líquido do pró-labore não é separável neste resumo (envie o resumo só "
                        "do pró-labore ou por contribuinte).")
    for r in rubricas:
        r["valor"] = cc.txt(r["valor"])
    f["dados"] = {"rubricas": len(rubricas), "total_proventos": cc.txt(totais.get("proventos", {}).get("valor")),
                  "total_descontos": cc.txt(totais.get("descontos", {}).get("valor")), "liquido": cc.txt(totais.get("liquido", {}).get("valor"))}
    return dict(f, rubricas=rubricas, totais={k: dict(v, valor=cc.txt(v["valor"])) for k, v in totais.items()}, pessoas=pessoas,
                pro_labore=pro)
