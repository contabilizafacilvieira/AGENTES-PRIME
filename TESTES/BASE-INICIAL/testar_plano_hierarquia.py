"""Árvore do plano de contas (regra GERAL): tipo sintética/analítica pela hierarquia, grupo contábil herdado da estrutura,
elegibilidade para composição no book e REANÁLISE de base já gravada. Dados 100% FICTÍCIOS; ambiente ISOLADO.

Casos: HIER-01..10, GROUP-01..12, BOOK-01..15, BOOK-SEV-01..07 (severidade ATENÇÃO da composição ausente), DUP-01,
PLANO-REAL-01 (plano fictício no formato observado) e BASE-RECALC-01..09
(snapshot fictício pré-v2 reanalisado sem novo envio).

Uso: .venv/Scripts/python.exe -I TESTES/BASE-INICIAL/testar_plano_hierarquia.py
"""
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
from decimal import Decimal as D
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
TMP = Path(tempfile.mkdtemp(prefix="prime-plano-hierarquia-"))
for k, v in {"AGENTES_PRIME_RUNTIME": TMP / "runtime", "AGENTES_PRIME_REGISTRO_SOL": TMP / "registro.json",
             "AGENTES_PRIME_ORDEM_ATIVA": TMP / "ordem.json", "AGENTES_PRIME_CLIENTES": TMP / "CLIENTES",
             "AGENTES_PRIME_LIBERADOS": TMP / "LIBERADOS", "LOCALAPPDATA": TMP / "lad"}.items():
    os.environ[k] = str(v)
(TMP / "CLIENTES").mkdir()
for p in ("API-LOCAL", "TESTES/BASE-INICIAL"):
    sys.path.insert(0, str(RAIZ / p))
import balancete_anterior as ba  # noqa: E402
import base_inicial as bi  # noqa: E402
import book_contabil as bk  # noqa: E402
import empresas_local as el  # noqa: E402
import ficticios as f  # noqa: E402
import plano_hierarquia as ph  # noqa: E402

resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:400]))


def conta(k, desc, saldo="0.00", cod=None):
    return {"codigo": cod or k.replace(".", ""), "classificacao": k, "descricao": desc, "saldo_atual": saldo}


def por_class(contas, a):
    return {c["classificacao"]: a["contas"][i] for i, c in enumerate(contas)}


# ---------------------------------------------------------------- plano FICTÍCIO no formato observado (5 ramos principais)
PLANO_REAL = [
    ("1", "ATIVO"), ("1.1", "ATIVO CIRCULANTE"), ("1.1.1", "DISPONIVEL"), ("1.1.1.01", "BANCOS CONTA MOVIMENTO"),
    ("1.1.1.01.0001", "BANCO FICTICIO ALFA", "5000.00"), ("1.1.2", "CLIENTES"), ("1.1.2.01", "CLIENTE FICTICIO A", "3000.00"),
    ("1.1.2.02", "CLIENTE FICTICIO B", "2000.00"), ("1.1.3", "IMPOSTOS A RECUPERAR"), ("1.1.3.01", "ICMS A RECUPERAR", "0.00"),
    ("2", "PASSIVO"), ("2.1", "PASSIVO CIRCULANTE"), ("2.1.1", "FORNECEDORES"), ("2.1.1.0001", "FORNECEDOR FICTICIO", "-4000.00"),
    ("2.3", "PATRIMÔNIO LÍQUIDO"), ("2.3.1", "CAPITAL SOCIAL"), ("2.3.1.01", "CAPITAL SUBSCRITO", "-6000.00"),
    ("3", "CONTAS DE RESULTADO - RECEITAS"), ("3.1", "RECEITA BRUTA"), ("3.1.1", "VENDAS DE MERCADORIAS", "-9000.00"),
    ("3.1.2", "DEDUÇÕES DA RECEITA"), ("3.1.2.01", "ICMS SOBRE VENDAS", "1200.00"), ("3.1.2.02", "PIS", "150.00"),
    ("3.1.2.03", "COFINS", "690.00"),
    ("4", "CONTAS DE RESULTADO - CUSTOS E DESPESAS"), ("4.1", "CUSTOS"), ("4.1.1", "CUSTO DAS MERCADORIAS VENDIDAS", "4500.00"),
    ("4.2", "DESPESAS OPERACIONAIS"), ("4.2.1", "FRETES E CARRETOS", "300.00"), ("4.2.2", "COMISSÕES", "860.00"),
    ("4.2.3", "TAXAS DIVERSAS", "300.00"), ("4.2.4", "ALUGUÉIS"), ("4.2.4.01", "IMÓVEIS"), ("4.2.4.01.0001", "ALUGUEL DA SEDE", "500.00"),
    ("4.3", "RESULTADO FINANCEIRO"), ("4.3.1", "RECEITAS FINANCEIRAS", "-200.00"),
    ("4.3.2", "DESPESAS FINANCEIRAS", "0.00"),
    ("5", "CONTAS DE APURAÇÃO"), ("5.1", "APURAÇÃO DO RESULTADO", "1600.00"),
]


def plano_real():
    contas = [conta(x[0], x[1], x[2] if len(x) > 2 else None) for x in PLANO_REAL]
    # sintéticas: saldo = soma das analíticas descendentes (como num balancete real)
    for c in contas:
        if c["saldo_atual"] is None:
            c["saldo_atual"] = f"{sum((D(o['saldo_atual']) for o in contas if o['classificacao'].startswith(c['classificacao'] + '.') and len(o) and o['saldo_atual'] is not None and not any(x['classificacao'].startswith(o['classificacao'] + '.') for x in contas)), D('0')):.2f}"
    return contas


def casos_hier():
    contas = plano_real()
    a = ph.analisar(contas)
    x = por_class(contas, a)
    registrar("HIER-01 conta raiz com descendentes → SINTÉTICA", x["1"]["tipo"] == "SINTETICA" and x["4"]["tipo"] == "SINTETICA")
    registrar("HIER-02 conta intermediária com descendentes → SINTÉTICA", x["1.1.1"]["tipo"] == "SINTETICA" and x["4.2"]["tipo"] == "SINTETICA")
    registrar("HIER-03 folha → ANALÍTICA", x["1.1.1.01.0001"]["tipo"] == "ANALITICA" and x["4.2.1"]["tipo"] == "ANALITICA")
    registrar("HIER-04 classificação mais detalhada sem descendentes → ANALÍTICA; folha em nível intermediário também é ANALÍTICA "
              "(sem regra global de 'mais longa vence')",
              x["2.1.1.0001"]["tipo"] == "ANALITICA" and x["1.1.2.01"]["tipo"] == "ANALITICA" and x["5.1"]["tipo"] == "ANALITICA")
    fmt = [conta("1.", "ATIVO"), conta("1.1.", "ATIVO CIRCULANTE"), conta(" 1.1.01 ", "CAIXA", "10.00")]
    af = ph.analisar(fmt)
    registrar("HIER-05 variações de formato ('1.', '1.1.', espaços) não quebram a hierarquia; original preservado",
              af["contas"][2]["superior"] == 1 and af["contas"][1]["superior"] == 0 and af["contas"][0]["tipo"] == "SINTETICA"
              and af["contas"][2]["classificacao"] == " 1.1.01 " and af["contas"][2]["classificacao_normalizada"] == "1.1.01")
    zeros = [conta("1", "ATIVO"), conta("1.1", "A"), conta("1.01", "B", "1.00")]
    az = ph.analisar(zeros)
    registrar("HIER-05b segmentos diferentes não são fundidos ('1.1' ≠ '1.01')",
              az["contas"][1]["classificacao_normalizada"] != az["contas"][2]["classificacao_normalizada"] and az["contas"][2]["superior"] == 0)
    mal = [conta("1", "ATIVO"), conta("1.1", "CIRCULANTE"), conta("1.1.A", "QUEBRADA", "5.00"), conta("1.1.1", "CAIXA", "5.00")]
    am = ph.analisar(mal)
    registrar("HIER-06 classificação malformada → revisão daquela conta (nada é inventado); demais seguem automáticas",
              am["contas"][2]["tipo"] == "" and am["contas"][2]["revisao"] and am["contas"][3]["tipo"] == "ANALITICA"
              and len(am["revisao"]) == 1, am["revisao"])
    outra = [dict(c, descricao=c["descricao"] + " RENOMEADA") for c in contas]
    ao = ph.analisar(outra)
    registrar("HIER-07 mudar a descrição não muda sintética/analítica (hierarquia igual)",
              [v["tipo"] for v in ao["contas"].values()] == [v["tipo"] for v in a["contas"].values()])
    enganosa = [conta("1", "ATIVO"), conta("1.1", "TOTAL ANALITICO"), conta("1.1.1", "CONTA SINTETICA DE NOME", "1.00")]
    ae = ph.analisar(enganosa)
    registrar("HIER-08 tipo não depende do nome da conta", ae["contas"][1]["tipo"] == "SINTETICA" and ae["contas"][2]["tipo"] == "ANALITICA")
    com_saldo = [conta("1", "ATIVO", "10.00"), conta("1.1", "CIRCULANTE", "10.00"), conta("1.1.1", "CAIXA", "10.00")]
    registrar("HIER-09 conta intermediária com saldo próprio continua SINTÉTICA", ph.analisar(com_saldo)["contas"][1]["tipo"] == "SINTETICA")
    filhos_ok = all((x[k]["superior"] is None) == ("." not in k) for k in x) and all(
        contas[x[k]["superior"]]["classificacao"] == k.rsplit(".", 1)[0] for k in x if "." in k)
    soma_desc = all(v["descendentes"] == sum(1 for o in x if o.startswith(k + ".")) for k, v in x.items())
    registrar("HIER-10 árvore consistente: cada conta aponta para a superior certa; descendentes e nível coerentes",
              filhos_ok and soma_desc and x["1.1.1.01.0001"]["nivel"] == 5)


def casos_grupos():
    contas = plano_real()
    x = por_class(contas, ph.analisar(contas))
    registrar("GROUP-01 ramo ATIVO → Ativo", x["1.1.2.01"]["grupo_contabil"] == "ATIVO")
    registrar("GROUP-02 ramo PASSIVO → Passivo", x["2.1.1.0001"]["grupo_contabil"] == "PASSIVO")
    registrar("GROUP-03 ramo PATRIMÔNIO LÍQUIDO (dentro de Passivo) → Patrimônio Líquido", x["2.3.1.01"]["grupo_contabil"] == "PATRIMONIO_LIQUIDO")
    registrar("GROUP-04 CONTAS DE RESULTADO - RECEITAS → Contas de Resultado (natureza receita)",
              x["3.1.1"]["grupo_contabil"] == "RESULTADO" and x["3.1.2.01"]["natureza_resultado"] == "RECEITA")
    registrar("GROUP-05 CONTAS DE RESULTADO - CUSTOS E DESPESAS → Contas de Resultado (custo/despesa pelo ramo mais próximo)",
              x["4.1.1"]["grupo_contabil"] == "RESULTADO" and x["4.1.1"]["natureza_resultado"] == "CUSTO"
              and x["4.2.2"]["natureza_resultado"] == "DESPESA" and x["4.3.1"]["natureza_resultado"] == "RECEITA")
    registrar("GROUP-06 CONTAS DE APURAÇÃO → Outros", x["5.1"]["grupo_contabil"] == "OUTROS")
    registrar("GROUP-07 descendentes herdam o grupo do ramo", all(v["grupo_contabil"] == "ATIVO" for k, v in x.items() if k.startswith("1")))
    alt = [conta("10", "ATIVO TOTAL"), conta("10.1", "CAIXA", "1.00"), conta("70", "PASSIVO"), conta("70.1", "FORNECEDOR", "-1.00"),
           conta("80", "PATRIMONIO LIQUIDO"), conta("80.1", "CAPITAL", "-1.00"), conta("90", "RESULTADO DO PERIODO"), conta("90.1", "VENDAS", "-1.00")]
    xa = por_class(alt, ph.analisar(alt))
    registrar("GROUP-08 numeração diferente (10/70/80/90) classificada pela hierarquia e descrição",
              [xa[k]["grupo_contabil"] for k in ("10.1", "70.1", "80.1", "90.1")] == ["ATIVO", "PASSIVO", "PATRIMONIO_LIQUIDO", "RESULTADO"])
    amb = [conta("1", "ATIVO"), conta("1.1", "CAIXA", "1.00"), conta("6", "GRUPO ESPECIAL"), conta("6.1", "CONTA ESPECIAL A", "2.00"),
           conta("6.2", "CONTA ESPECIAL B", "3.00")]
    aa = ph.analisar(amb)
    xb = por_class(amb, aa)
    registrar("GROUP-09 raiz realmente ambígua pede confirmação (nada é presumido)",
              xb["6.1"]["grupo_contabil"] == "" and aa["resumo"]["ramos_para_confirmar"] == [{"classificacao": "6", "descricao": "GRUPO ESPECIAL"}])
    registrar("GROUP-10 um ramo ambíguo não invalida os ramos determinísticos",
              xb["1.1"]["grupo_contabil"] == "ATIVO" and aa["resumo"]["precisam_confirmacao"] == 3 and aa["resumo"]["classificadas_automaticamente"] == 2)
    conf = ph.analisar(amb, grupos_confirmados={"6": "OUTROS"})
    registrar("GROUP-09b confirmação do Supervisor para o ramo ambíguo é herdada pelas contas do ramo (origem registrada)",
              conf["contas"][3]["grupo_contabil"] == "OUTROS" and conf["contas"][3]["grupo_origem"] == "CONFIRMADO_SUPERVISOR"
              and not conf["revisao"])
    var = [conta("1", "Ativo"), conta("1.1", "a", "1"), conta("2", "PASSIVO E PATRIMÔNIO-LÍQUIDO"), conta("2.1", "b", "-1"),
           conta("3", "Contas de Resultados"), conta("3.1", "c", "1"), conta("4", "P.L."), conta("4.1", "d", "-1"),
           conta("5", "Apuração"), conta("5.1", "e", "0")]
    xv = por_class(var, ph.analisar(var))
    registrar("GROUP-11 variações razoáveis (maiúsculas, acentos, separadores, plural, abreviação PL) reconhecidas",
              [xv[k]["grupo_contabil"] for k in ("1.1", "2.1", "3.1", "4.1", "5.1")] == ["ATIVO", "PASSIVO", "RESULTADO", "PATRIMONIO_LIQUIDO", "OUTROS"],
              [xv[k]["grupo_contabil"] for k in ("1.1", "2.1", "3.1", "4.1", "5.1")])
    contra = [conta("1", "CONTAS DE RESULTADO - RECEITAS"), conta("1.1", "VENDAS", "-5.00"), conta("2", "ATIVO"), conta("2.1", "CAIXA", "5.00")]
    xc = por_class(contra, ph.analisar(contra))
    registrar("GROUP-12 número da conta nunca define o grupo quando a estrutura diz outra coisa (raiz 1 = resultado; raiz 2 = ativo)",
              xc["1.1"]["grupo_contabil"] == "RESULTADO" and xc["2.1"]["grupo_contabil"] == "ATIVO")


def balancete_e_book(composicoes):
    contas = plano_real()
    lido = {"formato": "TESTE", "meta": {}, "contas": [dict(c, saldo_anterior=c["saldo_atual"], debitos="0.00", creditos="0.00", problemas=[])
                                                      for c in contas], "linhas_ignoradas": {}, "limites": []}
    bal = ba.analisar(lido)
    book = {"composicoes": [{"aba": aba, "conta": {"classificacao": k, "codigo": None}, "metodo": "ITENS_EM_ABERTO", "metodo_informado": "Itens em aberto",
                             "data_base": "2026-09-30", "colunas": ["debito", "credito"], "itens": [], "situacao_fonte": [], "assinaturas_fonte": [],
                             "alertas": [], "rodape": {}, "saldo_coluna": "POR ITEM",
                             "totais_recalculados": {"saldo": saldo, "itens": 1, "regra": "Σ"}} for aba, k, saldo in composicoes],
            "pendencias": [], "evidencias": [], "balancete_book": []}
    return bal, bk.confrontar(book, bal["contas"], "2026-09-30")


def casos_book():
    comp = [("A-CLI", "1.1.2.01", "3000.00"), ("FORN", "2.1.1.0001", "-4000.00"), ("CAP", "2.3.1.01", "-6000.00"),
            ("DIVERG", "1.1.1.01.0001", "4999.00")]
    bal, conf = balancete_e_book(comp)
    faltando = {c["classificacao"] for c in conf["contas_com_saldo_sem_composicao"]}
    c = {x["classificacao"]: x for x in bal["contas"]}
    registrar("BOOK-01 analítica patrimonial com saldo e sem composição → apontada", "1.1.2.02" in faltando, sorted(faltando))
    registrar("BOOK-02 receita (resultado) sem composição → NÃO apontada", not faltando & {"3.1.1", "4.3.1"})
    registrar("BOOK-03 custo (resultado) sem composição → NÃO apontada", "4.1.1" not in faltando)
    registrar("BOOK-04 despesa (resultado) sem composição → NÃO apontada", not faltando & {"4.2.1", "4.2.2", "4.2.3", "4.2.4.01.0001"})
    registrar("BOOK-05 sintética de resultado → NÃO apontada", not faltando & {"3", "3.1", "4", "4.2"})
    registrar("BOOK-06 sintética patrimonial com saldo e sem composição → NÃO apontada", not faltando & {"1", "1.1", "1.1.2", "2", "2.1.1"})
    registrar("BOOK-07 sintética com uma analítica descoberta → SÓ a analítica é apontada", "1.1.2.02" in faltando and "1.1.2" not in faltando)
    bal2, conf2 = balancete_e_book(comp + [("B-CLI", "1.1.2.02", "2000.00")])
    falt2 = {x["classificacao"] for x in conf2["contas_com_saldo_sem_composicao"]}
    registrar("BOOK-08 sintética cujas analíticas estão compostas → nenhuma pendência de composição no ramo", not falt2 & {"1.1.2", "1.1.2.01", "1.1.2.02"})
    registrar("BOOK-09 analítica com saldo zero e sem composição → sem aviso", "1.1.3.01" not in faltando and "4.3.2" not in faltando)
    x = {y["aba"]: y for y in conf["composicoes"]}
    registrar("BOOK-10 composição válida continua reconhecida", x["A-CLI"]["conferencia_numerica"] == "IGUAL_AO_BALANCETE")
    registrar("BOOK-11 composição divergente continua apontada", x["DIVERG"]["conferencia_numerica"] == "DIVERGENTE" and x["DIVERG"]["diferenca"] == "-1.00")
    registrar("BOOK-12 problemas patrimoniais genuínos não são escondidos (só analíticas patrimoniais com saldo descobertas)",
              faltando == {"1.1.2.02"}, sorted(faltando))
    registrar("BOOK-13 nenhuma pendência duplicada para sintética e analítica do mesmo ramo",
              not any(k.startswith(o + ".") for k in faltando for o in faltando))
    registrar("BOOK-14 sintéticas continuam na validação de saldos (soma das filhas e linha anterior + D − C)",
              c["1.1.2"]["confere"] is True and not any("soma das subordinadas" in o for o in c["1.1.2"].get("observacoes", []))
              and c["1.1.2"]["exige_composicao"] is False)
    errada = plano_real()
    lido = {"formato": "TESTE", "meta": {}, "contas": [dict(o, saldo_anterior=o["saldo_atual"], debitos="0.00", creditos="0.00", problemas=[])
                                                      for o in errada], "linhas_ignoradas": {}, "limites": []}
    lido["contas"][5]["saldo_atual"] = "9999.00"           # sintética 1.1.2 com saldo incoerente com as filhas
    lido["contas"][5]["saldo_anterior"] = "9999.00"
    b3 = {x["classificacao"]: x for x in ba.analisar(lido)["contas"]}
    registrar("BOOK-14b sintética incoerente com as filhas continua sinalizada na validação (sem virar exigência de composição)",
              any("soma das subordinadas" in o for o in b3["1.1.2"].get("observacoes", [])) and not b3["1.1.2"]["exige_composicao"])
    res = [v for v in c.values() if v["grupo_contabil"] == "RESULTADO"]
    registrar("BOOK-15 contas de resultado totalmente fora da elegibilidade para composição",
              res and not any(v["exige_composicao"] for v in res) and all("Resultado" in v["motivo_composicao"] or "sintética" in v["motivo_composicao"] for v in res))
    return faltando


def caso_plano_real():
    contas = plano_real()
    a = ph.analisar(contas)
    x = por_class(contas, a)
    sint = [k for k, v in x.items() if v["tipo"] == "SINTETICA"]
    exige = sorted(k for k, v in x.items() if v["exige_composicao"])
    registrar("PLANO-REAL-01 plano fictício no formato observado: raízes e intermediárias sintéticas, folhas analíticas, grupos herdados "
              "(Receitas e Custos/Despesas = Contas de Resultado; Apuração = Outros), composição só em analíticas patrimoniais com saldo",
              set(sint) >= {"1", "2", "3", "4", "5", "1.1", "2.3", "4.2"} and a["resumo"]["precisam_confirmacao"] == 0
              and a["resumo"]["por_grupo"]["RESULTADO"] == 20 and x["5.1"]["grupo_contabil"] == "OUTROS"
              and exige == ["1.1.1.01.0001", "1.1.2.01", "1.1.2.02", "2.1.1.0001", "2.3.1.01"], (a["resumo"], exige))


def casos_recalc():
    """Snapshot pré-v2 totalmente fictício é reanalisado SEM novo envio."""
    g = el.Empresas(RAIZ, TMP / "runtime")
    B = bi.BaseInicial(g)
    EMP, CNPJ, COMP = "RECALC-FICTICIA-TMP", "90.080.080/0001-25", "2026-10"
    g.cadastrar({"id": EMP, "nome": "EMPRESA RECALC FICTICIA LTDA", "cnpj": CNPJ, "regime": "LUCRO PRESUMIDO (FICTICIO)"})
    contas = plano_real()
    linhas = [(c["codigo"], c["classificacao"], c["descricao"], D(c["saldo_atual"]), D("0"), D("0"), D(c["saldo_atual"])) for c in contas]
    pdf = f.pdf_balancete("EMPRESA RECALC FICTICIA LTDA", CNPJ, "01/09/2026", "30/09/2026", linhas, por_pagina=20)
    prev = B.balancete(EMP, {"competencia": COMP, "nome": "balancete.pdf", "conteudo": base64.b64encode(pdf).decode()})
    B.balancete(EMP, {"competencia": COMP, "token": prev["token"], "salvar": True, "confirmado": True})
    comp_book = [("A-CLI", "1.1.2.01", "CLIENTE FICTICIO A", "Itens em aberto", [("2026-09-10", "NF 1", "Cliente A", 3000.0, 0, "")]),
                 ("FORN", "2.1.1.0001", "FORNECEDOR FICTICIO", "Itens em aberto", [("2026-09-11", "NF 2", "Fornecedor", 0, 4000.0, "")])]
    book = f.book_padrao("EMPRESA RECALC FICTICIA LTDA", CNPJ, "09/2026", "2026-09-30", linhas, comp_book)
    pb = B.book(EMP, {"competencia": COMP, "nome": "book.xlsx", "conteudo": base64.b64encode(book).decode()})
    B.book(EMP, {"competencia": COMP, "token": pb["token"], "salvar": True, "confirmado": True})
    # --- carrega snapshot pré-v2 versionado; não depende de tags nem do histórico local do Git
    pasta = TMP / "CLIENTES" / EMP / "BASE-INICIAL" / COMP
    base = json.loads((pasta / "base.json").read_text(encoding="utf-8"))
    snapshot = json.loads((RAIZ / "TESTES/BASE-INICIAL/fixtures/pre_v2_classificacao.json").read_text(encoding="utf-8"))
    assert snapshot["fixture"] == "TESTE_FICTICIO_PRE_V2"
    assert [c["classificacao"] for c in snapshot["contas"]] == [c["classificacao"] for c in base["balancete"]["contas"]]
    antigo_por_class = {c["classificacao"]: c for c in snapshot["contas"]}
    for c in base["balancete"]["contas"]:
        antigo = antigo_por_class[c["classificacao"]]
        for chave in ("tipo", "grupo_contabil", "grupo_ancora", "exige_composicao"):
            if chave in antigo:
                c[chave] = antigo[chave]
            else:
                c.pop(chave, None)
        c.pop("grupo", None)
        c.pop("natureza_resultado", None)
    # Comportamento antigo: toda conta marcada ANALÍTICA e com saldo != 0 exigia composição.
    base["balancete"]["contas"] = [dict(c, exige_composicao=(c.get("tipo") == "ANALITICA" and D(c["saldo_atual"]) != 0))
                                      for c in base["balancete"]["contas"]]
    contas_antigas = base["balancete"]["contas"]
    for k in ("analise_plano", "analise_versao"):
        base["balancete"].pop(k, None)
    base["book"]["confronto"] = bk.confrontar(base["book"], contas_antigas, base["data_base"])
    ancoras = snapshot["grupos_confirmados"]
    plano = []
    for c in contas_antigas:
        grupo = ancoras.get(c.get("grupo_ancora"), "") if c.get("grupo_ancora") else ""
        plano.append({"linha": c.get("origem"), "codigo": c["codigo"], "classificacao": c["classificacao"], "descricao": c["descricao"],
                      "grupo": grupo, "tipo": c.get("tipo") or "", "observacao": "", "origem": "BALANCETE FICTICIO DE TESTE (snapshot pre-v2)",
                      "dominio": "CONSTA_NO_BALANCETE"})
    base["contas_aplicadas"] = {"em": "2026-11-06T10:00:00-03:00", "balancete_sha256": base["balancete"]["sha256"], "incluidas": len(plano),
                                "adotadas": [], "grupos_confirmados": ancoras, "nao_adotadas": [], "grupos_preenchidos": 0}
    el.gravar(pasta / "base.json", base)
    (pasta / "analise.json").unlink(missing_ok=True)
    dados = json.loads((TMP / "CLIENTES" / EMP / "empresa-local.json").read_text(encoding="utf-8"))
    dados["plano"] = plano
    el.gravar(TMP / "CLIENTES" / EMP / "empresa-local.json", dados)
    B._indice(EMP)
    originais = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (pasta / "fontes").iterdir()}
    antes = {x["chave"]: x for x in B.definicoes(EMP, COMP) if not x.get("resolvida")}
    sit_antes = B.situacao(EMP, COMP)
    sem_comp_antes = {c["classificacao"] for c in base["book"]["confronto"]["contas_com_saldo_sem_composicao"]}
    # --- reanálise
    r = B.reanalisar(EMP, {"competencia": COMP, "confirmado": True})
    depois = {x["chave"]: x for x in B.definicoes(EMP, COMP) if not x.get("resolvida")}
    base2 = json.loads((pasta / "base.json").read_text(encoding="utf-8"))
    p2 = {c["codigo"]: c for c in g.obter(EMP)["plano"]}
    sem_comp_depois = {c["classificacao"] for c in base2["book"]["confronto"]["contas_com_saldo_sem_composicao"]}
    registrar("BASE-RECALC-01 snapshot pré-v2 reanalisado sem novo envio (botão disponível antes, ação executada)",
              sit_antes.get("reanalise_disponivel") is True and r["reanalise"]["mudou"] and not r.get("reanalise_disponivel"),
              r["reanalise"])
    registrar("BASE-RECALC-02 balancete original intocado", all(hashlib.sha256((pasta / "fontes" / n).read_bytes()).hexdigest() == h
                                                               for n, h in originais.items() if n.startswith("balancete")))
    registrar("BASE-RECALC-03 book original intocado", all(hashlib.sha256((pasta / "fontes" / n).read_bytes()).hexdigest() == h
                                                          for n, h in originais.items() if n.startswith("book")))
    registrar("BASE-RECALC-04 tipos recalculados (folhas intermediárias viram analíticas pela hierarquia)",
              antes.get("tipos") and "tipos" not in depois and p2["11201"]["tipo"] == "ANALITICA" and p2["11201"]["tipo_origem"].startswith("AUTOMATICO"),
              (antes.get("tipos", {}).get("quantidade"), p2["11201"]))
    registrar("BASE-RECALC-05 grupos recalculados (Contas de Resultado e Apuração deixam de ficar sem grupo)",
              antes.get("grupos") and "grupos" not in depois and p2["311"]["grupo"] == "RECEITA" and p2["51"]["grupo"] == "OUTROS",
              (antes.get("grupos", {}).get("quantidade"), p2["311"].get("grupo"), p2["51"].get("grupo")))
    registrar("BASE-RECALC-06 elegibilidade para composição recalculada (sintéticas, resultado e apuração saem da lista)",
              sem_comp_depois == {"1.1.1.01.0001", "1.1.2.02", "2.3.1.01"},
              (sorted(sem_comp_antes), sorted(sem_comp_depois)))
    falsos = (antes.get("tipos", {}).get("quantidade", 0) + antes.get("grupos", {}).get("quantidade", 0)
              + len(sem_comp_antes - sem_comp_depois))
    registrar("BASE-RECALC-07 falsos positivos anteriores desaparecem", falsos > 0 and not (sem_comp_depois - sem_comp_antes - {"1.1.1.01.0001", "1.1.2.02", "2.3.1.01"}),
              f"{falsos} item(ns) removido(s)")
    registrar("BASE-RECALC-08 pendências verdadeiras continuam (analíticas patrimoniais com saldo sem composição)",
              {"1.1.2.02", "1.1.1.01.0001", "2.3.1.01"} <= sem_comp_depois and "sem_composicao" in depois)
    hist = base2["historico"][-1]["motivo"]
    registrar("BASE-RECALC-09 auditoria: histórico e registro da reanálise indicam recálculo AUTOMÁTICO (não decisão do Supervisor)",
              "reanálise automática" in hist and base2["reanalises"][-1]["origem"].startswith("REANALISE_AUTOMATICA")
              and p2["51"].get("grupo_origem", "").startswith("AUTOMATICO") and p2["11201"].get("tipo_origem", "").startswith("AUTOMATICO"), hist)
    return falsos


def casos_book_severidade():
    """Composição ausente no book para conta ANALÍTICA patrimonial com saldo ≠ 0: ATENÇÃO (não Informativo, não Bloqueio), contada
    no resumo da base, conferível pelo mecanismo existente (Marcar como conferido + justificativa). Sintéticas, Contas de Resultado
    e saldo zero nunca entram."""
    g = el.Empresas(RAIZ, TMP / "runtime")
    B = bi.BaseInicial(g)
    EMP, CNPJ, COMP = "SEVERIDADE-FICTICIA-TMP", "90.606.060/0001-45", "2026-10"
    g.cadastrar({"id": EMP, "nome": "EMPRESA SEVERIDADE FICTICIA LTDA", "cnpj": CNPJ, "regime": "LUCRO PRESUMIDO (FICTICIO)"})
    contas = plano_real()
    linhas = [(c["codigo"], c["classificacao"], c["descricao"], D(c["saldo_atual"]), D("0"), D("0"), D(c["saldo_atual"])) for c in contas]
    pdf = f.pdf_balancete("EMPRESA SEVERIDADE FICTICIA LTDA", CNPJ, "01/09/2026", "30/09/2026", linhas, por_pagina=20)
    prev = B.balancete(EMP, {"competencia": COMP, "nome": "balancete.pdf", "conteudo": base64.b64encode(pdf).decode()})
    B.balancete(EMP, {"competencia": COMP, "token": prev["token"], "salvar": True, "confirmado": True})
    comp_book = [("A-CLI", "1.1.2.01", "CLIENTE FICTICIO A", "Itens em aberto", [("2026-09-10", "NF 1", "Cliente A", 3000.0, 0, "")]),
                 ("FORN", "2.1.1.0001", "FORNECEDOR FICTICIO", "Itens em aberto", [("2026-09-11", "NF 2", "Fornecedor", 0, 4000.0, "")])]
    book = f.book_padrao("EMPRESA SEVERIDADE FICTICIA LTDA", CNPJ, "09/2026", "2026-09-30", linhas, comp_book)
    pb = B.book(EMP, {"competencia": COMP, "nome": "book.xlsx", "conteudo": base64.b64encode(book).decode()})
    B.book(EMP, {"competencia": COMP, "token": pb["token"], "salvar": True, "confirmado": True})
    base = B.ler(EMP, COMP)
    bal = {c["codigo"]: c for c in base["balancete"]["contas"]}
    defs = {x["chave"]: x for x in B.definicoes(EMP, COMP)}
    sc = defs.get("sem_composicao") or {}
    cods = [i.split(" ")[0] for i in sc.get("itens", [])]
    sit = B.situacao(EMP, COMP)
    registrar("BOOK-SEV-01 analítica patrimonial com saldo ≠ 0 e sem composição → ATENÇÃO, com Problema/Impacto/O que fazer em pt-BR "
              "e ação de conferência",
              sc.get("nivel") == "ATENCAO" and sc.get("acao") == "CIENCIA" and sorted(cods) == ["111010001", "11202", "23101"]
              and sc.get("problema") == "A conta possui saldo no fechamento, mas não foi encontrada uma composição correspondente no Book."
              and sc.get("impacto") == "O saldo existe contabilmente, porém sua composição ainda não foi confirmada."
              and sc.get("o_que_fazer") == "Confira o saldo e informe/valide a composição ou registre a justificativa da conferência.",
              (sc.get("nivel"), sc.get("acao"), cods))
    pr, ra = sit["pendencias_resumo"], sit["resumo_analise"]
    registrar("BOOK-SEV-02 item contado no resumo de pendências (Atenção) e as 3 contas contadas em 'precisam de atenção'",
              pr["ATENCAO"] >= 1 and pr["INFORMATIVO"] == 0 and ra["precisam_atencao"] >= 3 and ra["pendencias_abertas"] >= 1, (pr, ra))
    registrar("BOOK-SEV-03 não é Bloqueio automático: não impede confirmar a base",
              sc.get("bloqueia_confirmacao") is False and sc.get("nivel") != "BLOQUEIO"
              and all(x["chave"] != "sem_composicao" for x in B.definicoes(EMP, COMP) if x["bloqueia_confirmacao"]))
    registrar("BOOK-SEV-04 conta sintética → nunca pendência de composição",
              not any(bal[c]["tipo"] == "SINTETICA" for c in cods) and any(c["tipo"] == "SINTETICA" and c["saldo_atual"] not in ("0", "0.00")
                                                                            for c in bal.values()))
    registrar("BOOK-SEV-05 Contas de Resultado → nunca pendência de composição",
              not any(bal[c]["grupo_contabil"] == "RESULTADO" for c in cods)
              and any(c["grupo_contabil"] == "RESULTADO" and c["tipo"] == "ANALITICA" and c["saldo_atual"] not in ("0", "0.00")
                      for c in bal.values()))
    registrar("BOOK-SEV-06 analítica patrimonial com saldo zero → sem pendência desnecessária",
              "11301" not in cods and bal["11301"]["tipo"] == "ANALITICA" and bal["11301"]["grupo_contabil"] == "ATIVO")
    B.ciencia(EMP, {"competencia": COMP, "chave": "sem_composicao", "justificativa": "Saldos conferidos com os razões (ficticio).",
                    "confirmado": True})
    sit2 = B.situacao(EMP, COMP)
    sc2 = {x["chave"]: x for x in sit2["definicoes"]}["sem_composicao"]
    mudada = B.ler(EMP, COMP)
    mudada["book"]["confronto"]["contas_com_saldo_sem_composicao"][0]["saldo"] = "1.00"      # cópia em memória: saldo diferente
    reaberta = {x["chave"]: x for x in B.definicoes(EMP, COMP, mudada)}["sem_composicao"]
    registrar("BOOK-SEV-07 conferido pelo Supervisor (justificativa) segue o comportamento de item resolvido: sai das abertas e do "
              "resumo; volta a ficar aberto se a lista ou os saldos mudarem; nenhum valor ou ajuste é gerado",
              sc2.get("resolvida") and sc2["ciencia"]["justificativa"].startswith("Saldos conferidos")
              and sc2["ciencia"]["por"].startswith("Supervisor") and sit2["pendencias_resumo"]["ATENCAO"] == pr["ATENCAO"] - 1
              and sit2["resumo_analise"]["precisam_atencao"] == ra["precisam_atencao"] - 3 and not reaberta.get("resolvida")
              and B.ler(EMP, COMP).get("saldos_definidos") == base.get("saldos_definidos")
              and B.ler(EMP, COMP)["book"]["confronto"] == base["book"]["confronto"],
              (sit2["pendencias_resumo"], sit2["resumo_analise"]))


def casos_duplicada():
    """Duas contas com a MESMA classificação: item próprio de Bloqueio (Problema/Impacto/O que fazer); nada renumerado, fundido ou
    posicionado na hierarquia; as demais contas seguem automáticas."""
    g = el.Empresas(RAIZ, TMP / "runtime")
    B = bi.BaseInicial(g)
    EMP, CNPJ = "DUPLICADA-FICTICIA-TMP", "90.707.070/0001-77"
    g.cadastrar({"id": EMP, "nome": "EMPRESA DUPLICADA FICTICIA LTDA", "cnpj": CNPJ, "regime": "LUCRO PRESUMIDO (FICTICIO)"})
    linhas = [("1", "1", "ATIVO", D("30"), D("0"), D("0"), D("30")), ("2", "1.1", "CIRCULANTE", D("30"), D("0"), D("0"), D("30")),
              ("3", "1.1.1", "CAIXA FICTICIO", D("10"), D("0"), D("0"), D("10")), ("4", "1.1.2", "CONTA A", D("10"), D("0"), D("0"), D("10")),
              ("5", "1.1.2", "CONTA B", D("10"), D("0"), D("0"), D("10"))]
    pdf = f.pdf_balancete("EMPRESA DUPLICADA FICTICIA LTDA", CNPJ, "01/09/2026", "30/09/2026", linhas, por_pagina=20)
    prev = B.balancete(EMP, {"competencia": "2026-10", "nome": "b.pdf", "conteudo": base64.b64encode(pdf).decode()})
    B.balancete(EMP, {"competencia": "2026-10", "token": prev["token"], "salvar": True, "confirmado": True})
    defs = {x["chave"]: x for x in B.definicoes(EMP, "2026-10")}
    rep = defs.get("classificacao_repetida") or {}
    bal = {c["codigo"]: c for c in B.ler(EMP, "2026-10")["balancete"]["contas"]}
    registrar("DUP-01 classificação repetida → Bloqueio próprio com Problema/Impacto/O que fazer; contas não renumeradas nem fundidas; "
              "hierarquia não presumida para elas; demais contas automáticas; sem duplicar em 'saldos que não conferem'",
              rep.get("nivel") == "BLOQUEIO" and rep.get("problema") == "Duas contas possuem a mesma classificação contábil."
              and rep.get("impacto") == "A hierarquia não pode determinar com segurança a posição dessas contas."
              and rep.get("o_que_fazer") == "Conferir no plano contábil qual classificação está correta."
              and rep.get("quantidade") == 2 and bal["4"]["classificacao"] == bal["5"]["classificacao"] == "1.1.2"
              and bal["4"]["tipo"] == "" and bal["5"]["tipo"] == "" and bal["3"]["tipo"] == "ANALITICA"
              and "problemas_balancete" not in defs, (rep.get("quantidade"), sorted(defs)))


def main():
    antes = sorted(str(p) for p in (RAIZ / "CLIENTES").rglob("*") if p.is_file())
    falsos = None
    try:
        casos_hier()
        casos_grupos()
        casos_book()
        caso_plano_real()
        casos_duplicada()
        casos_book_severidade()
        falsos = casos_recalc()
    except Exception as exc:
        import traceback
        registrar("bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-500:]}")
    finally:
        registrar("ambiente operacional intocado (CLIENTES/ real)", sorted(str(p) for p in (RAIZ / "CLIENTES").rglob("*") if p.is_file()) == antes)
        shutil.rmtree(TMP, ignore_errors=True)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {c}" + (f"  — {d}" if d else ""))
    print(f"\nFalsos positivos removidos na reanálise do cenário fictício: {falsos}")
    print(f"TOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
