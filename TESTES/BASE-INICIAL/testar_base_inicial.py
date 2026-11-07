"""Base inicial (balancete de encerramento do mês anterior + book contábil), criação de contas, vigência e saídas — dados 100%
FICTÍCIOS gerados em memória (TESTES/BASE-INICIAL/ficticios.py). Ambiente ISOLADO: cadastros e runtime temporários; nenhum arquivo
de referência real é lido e o ambiente operacional não é tocado (conferido no final).

Uso: .venv/Scripts/python.exe -I TESTES/BASE-INICIAL/testar_base_inicial.py
"""
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
TMP = Path(tempfile.mkdtemp(prefix="prime-base-inicial-"))
for k, v in {"AGENTES_PRIME_RUNTIME": TMP / "runtime", "AGENTES_PRIME_REGISTRO_SOL": TMP / "registro.json",
             "AGENTES_PRIME_ORDEM_ATIVA": TMP / "ordem.json", "AGENTES_PRIME_CLIENTES": TMP / "CLIENTES",
             "AGENTES_PRIME_LIBERADOS": TMP / "LIBERADOS", "LOCALAPPDATA": TMP / "lad"}.items():
    os.environ[k] = str(v)
(TMP / "CLIENTES").mkdir()
for p in ("API-LOCAL", "TESTES/BASE-INICIAL", "COORDENADOR-GERAL/ferramentas", "AGENTES/CONCILIACAO/ferramentas"):
    sys.path.insert(0, str(RAIZ / p))
import balancete_anterior as ba  # noqa: E402
import base_inicial as bi  # noqa: E402
import book_contabil as bk  # noqa: E402
import empresas_local as el  # noqa: E402
import exportacao_dominio as ex  # noqa: E402
import ficticios as f  # noqa: E402

D = Decimal
resultados = []
EMP, CNPJ = "BASE-FICTICIA-TMP", "90.080.080/0001-25"
COMP = "2026-10"


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:500]))


def erro(fn, *a):
    try:
        fn(*a)
    except ValueError as e:
        return str(e)
    return None


def b64(dados):
    return base64.b64encode(dados).decode()


def foto_operacional():
    arqs = sorted((str(p.relative_to(RAIZ)), p.stat().st_size, p.stat().st_mtime_ns) for p in (RAIZ / "CLIENTES").rglob("*") if p.is_file())
    reg = RAIZ / "COORDENADOR-GERAL" / "controle" / "solicitacoes.json"
    return arqs, hashlib.sha256(reg.read_bytes()).hexdigest() if reg.is_file() else None


g = el.Empresas(RAIZ, TMP / "runtime")
B = bi.BaseInicial(g)
CONTAS = f.contas_ficticias(f.SALDOS_PADRAO, f.MOV_PADRAO)


def pdf(cnpj=CNPJ, inicio="01/09/2026", fim="30/09/2026", contas=None, consolidado=None, **kw):
    return f.pdf_balancete("EMPRESA BASE FICTICIA LTDA", cnpj, inicio, fim, contas or CONTAS, consolidado=consolidado, por_pagina=14, **kw)


def enviar_balancete(dados, nome="balancete.pdf", comp=COMP, salvar=True, emp=EMP):
    prev = B.balancete(emp, {"competencia": comp, "nome": nome, "conteudo": b64(dados)})
    if salvar and prev["pode_salvar"]:
        B.balancete(emp, {"competencia": comp, "token": prev["token"], "salvar": True, "confirmado": True})
    return prev


def grupos_sugeridos(comp=COMP, emp=EMP):
    p = B.contas(emp, {"competencia": comp})
    return {a["classificacao"]: a["grupo_sugerido"] for a in p["ancoras_grupo"]}, p


def casos_balancete():
    g.cadastrar({"id": EMP, "nome": "EMPRESA BASE FICTICIA LTDA", "cnpj": CNPJ, "regime": "LUCRO PRESUMIDO (FICTICIO)"})
    r = ba.ler("b.pdf", pdf(quebrar={"22"}, auxiliar={"12"}, hifen={"41"}))
    c = {x["codigo"]: x for x in r["contas"]}
    registrar("B-01 PDF no layout do Domínio (fictício): colunas pela posição; cabeçalho repetido, descrição quebrada, texto auxiliar, "
              "hífen solto e rodapé tratados; todas as linhas conferem (anterior + D − C = atual)",
              r["totais"]["contas_extraidas"] == len(CONTAS) and r["linhas_ignoradas"]["cabecalho_repetido"] == 2
              and r["totais"]["linhas_que_nao_conferem"] == 0 and c["22"]["descricao"].endswith("MATERIAIS DIVERSOS") and "41" in c
              and r["meta"]["periodo"] == {"inicio": "2026-09-01", "fim": "2026-09-30"} and r["meta"]["cnpj"] == CNPJ, r["totais"])
    registrar("B-02 D/C preservado como informado (inclusive saldo contrário à natureza) e zero sem D/C inventado; sintética/analítica "
              "pela hierarquia; soma só das analíticas (sem somar sintéticas)",
              (c["75"]["saldo_atual"], c["75"]["natureza_atual"]) == ("-150.00", "C") and (c["23"]["saldo_atual"], c["23"]["natureza_atual"]) == ("0.00", None)
              and c["1"]["tipo"] == "SINTETICA" and c["11"]["tipo"] == "ANALITICA" and r["totais"]["soma_saldos_analiticas"] == "0.00",
              [(c["75"]["saldo_atual"], c["75"]["natureza_atual"]), c["23"]["natureza_atual"]])
    # planilha com cabeçalho deslocado
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for _ in range(4):
        ws.append(["Balancete de verificação (fictício)"])
    ws.append([None, "Código", "Classificação", "Descrição", "Saldo anterior", "Débito", "Crédito", "Saldo atual"])
    for cod, k, d_, ant, deb, cre, atu in CONTAS:
        ws.append([None, cod, k, d_, f"{f.br(ant)}", float(deb), float(cre), f"{f.br(atu)}"])
    import io
    buf = io.BytesIO()
    wb.save(buf)
    prev = B.balancete(EMP, {"competencia": COMP, "nome": "balancete.xlsx", "conteudo": b64(buf.getvalue())})
    registrar("B-03 balancete em planilha com cabeçalho deslocado: lido por sinônimos; sem período/CNPJ no arquivo → ciência do Supervisor "
              "exigida (nada presumido)",
              prev["totais"]["contas_extraidas"] == len(CONTAS) and "identificacao_balancete" in prev["conferencia"]["ciencias_exigidas"],
              prev["conferencia"])
    outro = enviar_balancete(pdf(cnpj="90.090.090/0001-90"), salvar=False)
    periodo = enviar_balancete(pdf(inicio="01/08/2026", fim="31/08/2026"), salvar=False)
    tentativa = erro(B.balancete, EMP, {"competencia": COMP, "token": outro["token"], "salvar": True, "confirmado": True})
    registrar("B-04 empresa ou período incompatíveis: CNPJ de outra empresa e balancete de agosto (competência 10 exige 30/09) são "
              "recusados; nada é salvo",
              not outro["pode_salvar"] and not periodo["pode_salvar"] and tentativa and "OUTRA empresa" in tentativa
              and "exige o encerramento de 2026-09-30" in " ".join(periodo["conferencia"]["bloqueios"])
              and not (TMP / "CLIENTES" / EMP / "BASE-INICIAL" / COMP / "base.json").exists(), tentativa)
    filial = enviar_balancete(pdf(cnpj="90.080.080/0002-06"), salvar=False)
    cons = enviar_balancete(pdf(consolidado=["101", "102"]), salvar=False)
    registrar("B-05 outro estabelecimento da mesma raiz e balancete CONSOLIDADO exigem ciência; estabelecimentos listados",
              "estabelecimento" in filial["conferencia"]["ciencias_exigidas"] and "consolidado" in cons["conferencia"]["ciencias_exigidas"]
              and cons["meta"]["abrangencia"] == {"tipo": "CONSOLIDADO", "estabelecimentos": ["101", "102"]}, cons["conferencia"]["informacoes"])


def casos_contas():
    enviar_balancete(pdf(consolidado=["101", "102"]))
    sug, prev = grupos_sugeridos()
    B.contas(EMP, {"competencia": COMP, "salvar": True, "confirmado": True, "grupos": sug})
    e = g.obter(EMP)
    p = {c["codigo"]: c for c in e["plano"]}
    defs = {x["chave"]: x for x in B.definicoes(EMP, COMP)}
    registrar("C-01 1ª importação: contas extraídas do balancete viram o plano (códigos, classificações preservados); tipo e grupo "
              "AUTOMÁTICOS pela hierarquia (herdados da conta principal; PL dentro de Passivo; resultado com a natureza), sem pendência "
              "de tipo/grupo e sem ramos para confirmar",
              len(e["plano"]) == len(CONTAS) and p["41"]["grupo"] == "PASSIVO" and p["53"]["grupo"] == "PATRIMONIO_LIQUIDO"
              and p["11"]["grupo"] == "ATIVO" and p["64"]["grupo"] == "RECEITA" and p["74"]["grupo"] == "DESPESA"
              and p["64"]["grupo_contabil"] == "RESULTADO" and p["11"]["tipo"] == "ANALITICA" and p["1"]["tipo"] == "SINTETICA"
              and p["11"]["grupo_origem"].startswith("AUTOMATICO") and not sug and "grupos" not in defs and "tipos" not in defs
              and p["11"]["origem"].startswith("BALANCETE 2026-09-30") and p["11"]["dominio"] == "CONSTA_NO_BALANCETE",
              (p["41"]["grupo"], p["53"]["grupo"], p["11"]["grupo"], p["64"]["grupo"], sug))
    # reimportação: descrição alterada, conta ausente, classificação reaproveitada por outro código, saldo alterado
    contas2 = [c for c in CONTAS if c[0] != "12"]
    contas2 = [(c[0], c[1], "BANCO FICTICIO ALFA C/C NOVO NOME" if c[0] == "11" else c[2], *c[3:]) for c in contas2]
    contas2 = [("99" if c[0] == "23" else c[0], *c[1:]) for c in contas2]
    prev = B.balancete(EMP, {"competencia": COMP, "nome": "balancete-v2.pdf", "conteudo": b64(pdf(contas=contas2, consolidado=["101", "102"]))})
    dif = prev["reimportacao"]
    B.balancete(EMP, {"competencia": COMP, "token": prev["token"], "salvar": True, "confirmado": True})
    cmp_ = B.contas(EMP, {"competencia": COMP})
    B.contas(EMP, {"competencia": COMP, "salvar": True, "confirmado": True, "grupos": sug, "adotar": []})
    p = {c["codigo"]: c for c in g.obter(EMP)["plano"]}
    registrar("C-02 reimportação: diferenças mostradas antes de salvar; conta ausente NÃO é excluída; descrição alterada só com adoção "
              "expressa; classificação reaproveitada por outro código nunca substitui o código",
              "1.1.1.01.000002" in dif["ausentes_no_novo"] and any(a["classificacao"] == "1.1.1.01.000001" for a in dif["alteradas"])
              and "12" in p and p["11"]["descricao"] == "BANCO FICTICIO ALFA C/C" and "99" not in p and "23" in p
              and any(x["conta"]["codigo"] == "99" for x in cmp_["conflitos"]) and any(x["conta"]["codigo"] == "11" for x in cmp_["alteradas"]),
              {k: len(v) for k, v in cmp_.items() if isinstance(v, list)})
    B.contas(EMP, {"competencia": COMP, "salvar": True, "confirmado": True, "grupos": sug, "adotar": ["11"]})
    p = {c["codigo"]: c for c in g.obter(EMP)["plano"]}
    defs = {x["chave"]: x for x in B.definicoes(EMP, COMP)}
    registrar("C-03 adoção expressa da alteração (versão anterior guardada); conflitos não adotados e conta 12 (ausente, analítica) viram "
              "definições: ciência dos conflitos e saldo inicial NÃO presumido",
              p["11"]["descricao"] == "BANCO FICTICIO ALFA C/C NOVO NOME" and p["11"]["versoes_anteriores"][0]["descricao"] == "BANCO FICTICIO ALFA C/C"
              and "conflitos_contas" in defs and "12 1.1.1.01.000002" in " ".join(defs["saldos"]["itens"]), list(defs))
    # volta ao balancete completo para os próximos casos (reimportação da v1: nada é excluído)
    enviar_balancete(pdf(consolidado=["101", "102"]))
    B.contas(EMP, {"competencia": COMP, "salvar": True, "confirmado": True, "grupos": sug})


def casos_book():
    cb = {c[1]: c for c in CONTAS}
    comp_ok = [("21-CLIENTES NACIONAIS", "1.1.2.01.000001", "CLIENTES NACIONAIS", "Itens em aberto",
                [("2024-03-10", "NF 10", "Cliente Ficticio Um (título antigo)", 5000.0, 0, "vencido"),
                 ("2026-09-15", "NF 88", "Cliente Ficticio Dois", 3000.0, 0, ""), ("2026-09-20", "REC 5", "Recebimento parcial", 0, 0.0, "")]),
               ("41-FORNECEDORES", "2.1.1.01.000001", "FORNECEDORES NACIONAIS", "Histórico acumulado",
                [("2022-01-05", "NF 1", "Fornecedor Antigo", 0, 1000.0, ""), ("2026-08-01", "NF 50", "Fornecedor Ficticio", 0, 5000.0, ""),
                 ("2026-09-02", "PG 50", "Pagamento parcial", 150.0, 0, "")]),
               ("12-BANCO BETA", "1.1.1.01.000002", "BANCO FICTICIO BETA C/C", "Posição de relatório",
                [("2026-09-30", "EXTRATO", "Saldo do extrato", 2500.50, 0, "extrato pendente de envio")]),
               ("42-ISS", "2.1.1.02.000001", "ISS A RECOLHER", "Híbrido", [("2026-09-30", "GUIA", "ISS do mês", 0, 600.0, "")]),
               ("99-SEM CONTA", "9.9.9.99.000001", "CONTA INEXISTENTE", "", [("2026-09-30", "X", "Item", 10.0, 0, "")])]
    pend = [("1.1.2.01.000001", "TITULO", "ALTA", "Título antigo sem baixa", "NF 10 de 2024", "texto", "book", "ABERTA")]
    evid = [("1.1.1.01.000002", "1.1.1.01.000002", "extrato_beta_setembro.pdf", "EXTRATO", "manual", "saldo final", 2500.5, "2026-09-30",
             2500.5, 0, "CONFERE", "SIM", "fictício")]
    baixas = [("2.1.1.01.000001", "NF 49", "Fornecedor Ficticio", "NF 49", 800.0, "R1", "1:1", "ALTA", "L10", "PAGTO NF 49", "baixa de teste")]
    dados = f.book_padrao("EMPRESA BASE FICTICIA LTDA", CNPJ, "09/2026", "2026-09-30", CONTAS, comp_ok, pend, evid, baixas)
    lido = bk.ler("book.xlsx", dados)
    conf = bk.confrontar(lido, ba.ler("b.pdf", pdf())["contas"], "2026-09-30")
    x = {c["aba"]: c for c in conf["composicoes"]}
    comp_cli = next(c for c in lido["composicoes"] if c["aba"].startswith("21-"))
    comp_for = next(c for c in lido["composicoes"] if c["aba"].startswith("41-"))
    corrente, soma_coluna_saldo = D("0"), D("0")             # o que daria somar a coluna de saldo corrente (erro evitado)
    for it in comp_for["itens"]:
        corrente += D(it.get("debito") or 0) - D(it.get("credito") or 0)
        soma_coluna_saldo += corrente
    registrar("K-01 book padrão: abas classificadas pelo conteúdo; composição ligada à conta pela CLASSIFICAÇÃO; itens separados de "
              "totais, situação, observação e assinaturas; títulos antigos preservados",
              lido["resumo"]["por_tipo"] == {"BALANCETE": 1, "COMPOSICAO": 5, "EVIDENCIAS": 1, "HISTORICO_BAIXAS": 1, "INDICE": 1, "PENDENCIAS": 1}
              and len(comp_cli["itens"]) == 3 and comp_cli["itens_datados"]["mais_antigo"] == "2024-03-10" and comp_cli["assinaturas_fonte"]
              and comp_cli["situacao_fonte"] and "total" in comp_cli["rodape"], lido["resumo"])
    registrar("K-02 coluna de SALDO ACUMULADO nunca é somada: saldo = Σ débitos − Σ créditos dos itens; fórmula × valor armazenado "
              "identificados (armazenado não é tratado como verificado)",
              comp_for["saldo_coluna"].startswith("ACUMULADO") and comp_for["totais_recalculados"]["saldo"] == "-5850.00"
              and soma_coluna_saldo != D("-5850.00") and comp_for["formulas"]["armazenadas_nao_verificadas"] + comp_for["formulas"]["sem_valor"] > 0,
              (comp_for["saldo_coluna"], comp_for["totais_recalculados"], str(soma_coluna_saldo)))
    x21, x12, x42, x99 = x["21-CLIENTES NACIONAIS"], x["12-BANCO BETA"], x["42-ISS"], x["99-SEM CONTA"]
    registrar("K-03 diferença ZERO com evidência pendente: conferência numérica OK, mas documentos de suporte PENDENTES e confirmação do "
              "Supervisor PENDENTE (status 'fecha' do book é só informação da fonte)",
              x21["conferencia_numerica"] == "IGUAL_AO_BALANCETE" and x21["situacao"] == "CONFERENCIA_NUMERICA_OK_EVIDENCIA_PENDENTE"
              and x21["documentos_suporte"]["situacao"] == "PENDENTE" and x21["confirmacao_supervisor"] == "PENDENTE"
              and "SALDO · fecha" in x21["situacao_fonte"], x21["situacao"])
    registrar("K-04 divergência book × balancete: valores, diferença e fontes mostrados; nenhum ajuste; composição sem conta "
              "correspondente sinalizada; métodos mapeados (itens em aberto, histórico acumulado, posição, híbrido)",
              x42["conferencia_numerica"] == "DIVERGENTE" and x42["diferenca"] == "100.50" and "Nenhum ajuste" in x42["explicacao"]
              and x99["conferencia_numerica"] == "SEM_CONTA_CORRESPONDENTE" and x12["conferencia_numerica"] == "IGUAL_AO_BALANCETE"
              and {c["metodo"] for c in lido["composicoes"]} == {"ITENS_EM_ABERTO", "HISTORICO_ACUMULADO", "POSICAO_DE_RELATORIO", "HIBRIDO", "NAO_INFORMADO"},
              (x42.get("explicacao"), x99["conferencia_numerica"]))
    registrar("K-05 pendências, evidências (arquivo referenciado NÃO recebido) e histórico de baixas lidos como informação; histórico "
              "nunca gera lançamento",
              len(lido["pendencias"]) == 1 and lido["evidencias"][0]["arquivo_recebido"] is False and len(lido["historico_baixas"]) == 1
              and "lancamentos" not in lido and x12["documentos_suporte"]["recebidos_pelo_aplicativo"] == 0, lido["evidencias"][0]["aviso"])
    # estrutura variada: abas renomeadas, cabeçalho deslocado, código reduzido, sem débito/crédito, fórmula aritmética, método desconhecido
    var = f.book_variado(f"EMPRESA BASE FICTICIA LTDA {CNPJ}", "30/09/2026", [
        ("Fornec", 15, 4, "41 - FORNECEDORES NACIONAIS", "Itens em aberto",
         [("Fornecedor Ficticio", "NF 50", "01/08/2026", "30/08/2026", "=4000+1000"), ("Fornecedor Antigo", "NF 1", "05/01/2021", "05/02/2021", D("850.00")),
          ("Outro Fornecedor", "NF 77", "10/09/2026", "10/10/2026", D("0.00"))]),
        ("xyz", 7, 2, "21 CLIENTES", "Conferência por amostragem", [("Cliente", "NF 88", "15/09/2026", "15/10/2026", D("8000.00"))])],
        com_vinculo_externo=True)
    lv = bk.ler("variado.xlsx", var)
    cv = {c["aba"]: c for c in lv["composicoes"]}
    conf_v = {c["aba"]: c for c in bk.confrontar(lv, ba.ler("b.pdf", pdf())["contas"], "2026-09-30")["composicoes"]}
    registrar("K-06 estrutura diferente: abas renomeadas e vazias, cabeçalho deslocado (linha 15, coluna D), cabeçalho repetido, conta "
              "pelo CÓDIGO REDUZIDO, fórmula aritmética recalculada, título de 2021 preservado, total separado",
              set(cv) == {"Fornec", "xyz"} and cv["Fornec"]["conta"]["codigo"] == "41" and len(cv["Fornec"]["itens"]) == 3
              and cv["Fornec"]["formulas"]["aritmeticas_recalculadas"] == 1 and cv["Fornec"]["totais_recalculados"]["saldo"] == "5850.00"
              and cv["Fornec"]["itens_datados"]["mais_antigo"] == "2021-01-05" and "total" in cv["Fornec"]["rodape"],
              (cv["Fornec"]["conta"], cv["Fornec"]["totais_recalculados"]))
    registrar("K-07 método desconhecido sinalizado (nenhum escolhido); sinal oposto sem débito/crédito → 'sinal a confirmar' (sem ajuste); "
              "vínculo externo informado e NÃO seguido",
              cv["xyz"]["metodo"] == "DESCONHECIDO" and conf_v["Fornec"]["conferencia_numerica"] == "SINAL_A_CONFIRMAR"
              and lv["seguranca"]["vinculos_externos"] and any("vínculo" in a for a in lv["alertas"]), (conf_v["Fornec"]["explicacao"], lv["alertas"]))
    # tamanhos: 1 composição e 60 composições
    peq = bk.ler("p.xlsx", f.book_padrao("E", CNPJ, "09/2026", "2026-09-30", CONTAS[:3], comp_ok[:1]))
    grande_comp = [(f"{i:03d}-CONTA", "1.1.2.01.000001", "CLIENTES", "Itens em aberto",
                    [(f"2026-09-{(j % 28) + 1:02d}", f"NF {i}-{j}", f"Cliente {j}", 10.0, 0, "") for j in range(40)]) for i in range(60)]
    grd = bk.ler("g.xlsx", f.book_padrao("E", CNPJ, "09/2026", "2026-09-30", CONTAS, grande_comp))
    registrar("K-08 books de tamanhos diferentes: 1 composição e 60 composições × 40 itens, sem depender de nomes de abas",
              peq["resumo"]["composicoes"] == 1 and grd["resumo"]["composicoes"] == 60
              and all(c["totais_recalculados"]["itens"] == 40 and c["totais_recalculados"]["saldo"] == "400.00" for c in grd["composicoes"]),
              (peq["resumo"], grd["resumo"]["composicoes"]))
    # book na base (com ciências)
    prev = B.book(EMP, {"competencia": COMP, "nome": "book.xlsx", "conteudo": b64(dados)})
    B.book(EMP, {"competencia": COMP, "token": prev["token"], "salvar": True, "confirmado": True})
    defs = {x["chave"]: x for x in B.definicoes(EMP, COMP)}
    outro = f.book_padrao("E", "90.090.090/0001-90", "09/2026", "2026-09-30", CONTAS, comp_ok[:1])
    rec = B.book(EMP, {"competencia": COMP, "nome": "outro.xlsx", "conteudo": b64(outro)})
    registrar("K-09 book na base: divergências, composição sem conta e pendências do book viram ciências do Supervisor; book de OUTRA "
              "empresa (CNPJ) recusado",
              {"divergencias_book", "composicoes_sem_conta", "pendencias_book"} <= set(defs) and rec["conferencia"]["bloqueios"],
              (sorted(defs), rec["conferencia"]["bloqueios"]))


def casos_criacao_e_confirmacao():
    base = lambda **k: dict({"codigo": "24", "classificacao": "1.1.2.02.000003", "descricao": "ADIANTAMENTO DE VIAGEM", "superior": "1.1.2.02",  # noqa: E731
                             "tipo": "ANALITICA", "grupo": "ATIVO", "confirmado": True}, **k)
    recusas = {
        "codigo duplicado": erro(g.criar_conta, EMP, base(codigo="22")),
        "classificacao duplicada": erro(g.criar_conta, EMP, base(classificacao="1.1.2.02.000001")),
        "superior analitica": erro(g.criar_conta, EMP, base(superior="1.1.2.02.000001", classificacao="1.1.2.02.000001.01")),
        "nivel errado": erro(g.criar_conta, EMP, base(classificacao="1.1.2.02.000003.1")),
        "grupo diferente do superior": erro(g.criar_conta, EMP, base(grupo="PASSIVO")),
        "campo ausente": erro(g.criar_conta, EMP, base(descricao="")),
        "sem confirmacao": erro(g.criar_conta, EMP, base(confirmado=False)),
        "superior inexistente": erro(g.criar_conta, EMP, base(superior="1.9.9", classificacao="1.9.9.01")),
    }
    registrar("A-01 criação de conta recusada: código/classificação duplicados, superior analítica ou inexistente, nível errado, grupo "
              "diferente do superior, campo ausente, sem confirmação",
              all(recusas.values()), recusas)
    # resolve definições para confirmar a base antes da criação
    defs = B.definicoes(EMP, COMP)
    for x in defs:
        if "referencia" in x and not x.get("resolvida"):
            B.ciencia(EMP, {"competencia": COMP, "chave": x["chave"], "justificativa": "Ciência de teste fictício.", "confirmado": True})
    sem_frase = erro(B.confirmar, EMP, {"competencia": COMP, "frase": "CONFIRMO"})
    B.confirmar(EMP, {"competencia": COMP, "frase": f"CONFIRMO BASE INICIAL {EMP} {COMP}"})
    s = B.situacao(EMP, COMP)
    sys.path.insert(0, str(RAIZ / "COORDENADOR-GERAL" / "ferramentas"))
    import coordenador as co
    antes = co.fontes_atuais(EMP, co.FONTES_ETAPA["CONCILIACAO"])
    registrar("A-02 base confirmada só com a frase exata e sem definições pendentes; etapas 1–6 concluídas",
              sem_frase and s["situacao"] == "CONFIRMADA" and all(x["feito"] for x in s["etapas"]) and antes["BASE_INICIAL"] != "AUSENTE",
              [x["falta"] for x in s["etapas"]])
    g.criar_conta(EMP, base())
    p = {c["codigo"]: c for c in g.obter(EMP)["plano"]}
    s = B.situacao(EMP, COMP)
    depois = co.fontes_atuais(EMP, co.FONTES_ETAPA["CONCILIACAO"])
    defs = {x["chave"]: x for x in s["definicoes"]}
    registrar("A-03 conta criada: 'cadastrada no aplicativo' com Domínio PENDENTE; sem saldo presumido (definição exigida); a base "
              "confirmada volta a RASCUNHO e a fonte de vigência muda (conferências que a usaram ficam desatualizadas)",
              p["24"]["origem"] == "CRIADA_NO_APLICATIVO" and p["24"]["dominio"] == "PENDENTE_CONFERENCIA" and s["situacao"] == "RASCUNHO"
              and "24 1.1.2.02.000003" in " ".join(defs["saldos"]["itens"]) and "dominio" in defs and not defs["dominio"]["bloqueia_confirmacao"]
              and depois["BASE_INICIAL"] != antes["BASE_INICIAL"], (s["situacao"], list(defs)))
    recusas = {"conta do balancete": erro(B.saldo_inicial, EMP, {"competencia": COMP, "codigo": "11", "saldo": "0", "justificativa": "teste x", "confirmado": True}),
               "sem natureza": erro(B.saldo_inicial, EMP, {"competencia": COMP, "codigo": "24", "saldo": "10,00", "justificativa": "teste x", "confirmado": True}),
               "sintetica": None}
    g.criar_conta(EMP, base(codigo="25", classificacao="1.1.2.03", superior="1.1.2", tipo="SINTETICA", descricao="OUTROS CREDITOS"))
    recusas["sintetica"] = erro(B.saldo_inicial, EMP, {"competencia": COMP, "codigo": "25", "saldo": "0", "justificativa": "teste x", "confirmado": True})
    B.saldo_inicial(EMP, {"competencia": COMP, "codigo": "24", "saldo": "0,00", "justificativa": "Conta nova, sem saldo em 30/09.", "confirmado": True})
    s = B.situacao(EMP, COMP)
    registrar("A-04 saldo inicial: saldo do balancete nunca é substituído; valor ≠ 0 exige D/C; sintética recusada; ZERO explícito aceito",
              all(recusas.values()) and s["saldos"]["24"]["origem"] == "DEFINIDO_PELO_SUPERVISOR" and s["saldos"]["24"]["saldo"] == "0.00",
              recusas)
    B.confirmar(EMP, {"competencia": COMP, "frase": f"CONFIRMO BASE INICIAL {EMP} {COMP}"})
    # exportação recusa conta pendente no Domínio
    plano = ex.plano_empresa(EMP)
    registrar("A-05 exportador vê a correspondência pendente no Domínio da conta criada (o TXT recusa lançamentos nela)",
              plano["24"]["dominio"] == "PENDENTE_CONFERENCIA" and plano["11"]["dominio"] == "CONSTA_NO_BALANCETE", plano["24"])
    g.conta_dominio(EMP, {"codigo": "24", "justificativa": "Conta criada no Domínio pelo Supervisor (teste).", "confirmado": True})
    registrar("A-06 correspondência no Domínio confirmada por declaração do Supervisor (o aplicativo não cria contas no Domínio)",
              ex.plano_empresa(EMP)["24"]["dominio"] == "CONFIRMADA_NO_DOMINIO", ex.plano_empresa(EMP)["24"])


def casos_conciliacao_e_saidas():
    import conciliacao as cc
    arq = TMP / "CLIENTES" / EMP / "BASE-INICIAL" / COMP / "base.json"
    plano = {c["codigo"]: {"tipo": c["tipo"], "grupo": c["grupo"], "descricao": c["descricao"]} for c in g.obter(EMP)["plano"]}
    k = cc.Conciliacao({"empresa": EMP, "competencia": COMP, "sol": "SOL-2026-999999", "base_inicial": str(arq)})
    k.plano, k.abertura, k.abertura_invalida = plano, {}, {}
    k.ler_base_inicial()
    v = next(x for x in k.verificacoes if x["id"] == "CONC-A-BASE-INICIAL")
    k2 = cc.Conciliacao({"empresa": EMP, "competencia": COMP, "sol": "SOL-2026-999999", "base_inicial": str(arq)})
    k2.plano, k2.abertura_invalida = plano, {}
    k2.abertura = {"11": {"arquivo": "saldos.csv", "valor": D("1.00"), "data_base": "2026-09-30"}}
    k2.ler_base_inicial()
    v2 = next(x for x in k2.verificacoes if x["id"] == "CONC-A-BASE-INICIAL")
    registrar("Q-01 Conciliação usa a base CONFIRMADA (só analíticas, D/C como informado); documento SALDOS DE ABERTURA divergente torna "
              "a abertura da conta inválida (nenhum prevalece)",
              v["resultado"] == "CONFERIDO" and k.abertura["41"]["valor"] == D("-5850.00") and "1" not in k.abertura
              and k.abertura["24"]["valor"] == D("0.00") and v2["resultado"] == "DIVERGENTE" and "11" in k2.abertura_invalida and "11" not in k2.abertura,
              (v["justificativa"][:160], v2["justificativa"][-120:]))
    B.ciencia  # noqa: B018
    dados = json.loads(arq.read_text(encoding="utf-8"))
    dados["situacao"] = "RASCUNHO"
    rasc = TMP / "rascunho.json"
    rasc.write_text(json.dumps(dados), encoding="utf-8")
    k3 = cc.Conciliacao({"empresa": EMP, "competencia": COMP, "sol": "SOL-2026-999999", "base_inicial": str(rasc)})
    k3.plano, k3.abertura, k3.abertura_invalida = plano, {}, {}
    k3.ler_base_inicial()
    registrar("Q-02 base em RASCUNHO não é usada pela Conciliação (pendente, saldos não aplicados)",
              not k3.abertura and next(x for x in k3.verificacoes if x["id"] == "CONC-A-BASE-INICIAL")["resultado"] == "PENDENTE")
    # balancete final calculado com hierarquia, a partir dos saldos (abertura da base) + lançamentos aprovados
    saldos_conc = [{"conta": c, "abertura": f"{a['valor']:.2f}"} for c, a in k.abertura.items()]
    gerado = {"lancamentos": [{"debito": "11", "credito": "64", "valor": "1000.00"}, {"debito": "74", "credito": "11", "valor": "35.10"}],
              "linhas": 2, "total": "1035.10"}
    plano_ex = ex.plano_empresa(EMP)
    b = ex.calcular_balancete(gerado, saldos_conc, plano_ex, {"tipo": "INTEGRAL", "texto": "x"})
    lin = {x["conta"]: x for x in b["linhas"]}
    ab11 = D(next(c for c in CONTAS if c[0] == "11")[6])
    registrar("S-01 balancete final: saldo inicial (base) + débitos − créditos = saldo final, exato; sintéticas consolidadas pela "
              "hierarquia sem entrar nos totais (sem duplicação); totais só das analíticas",
              lin["11"]["saldo_final"] == ab11 + D("1000.00") - D("35.10") and lin["4"]["saldo_final"] == lin["11"]["saldo_final"] + lin["12"]["saldo_final"]
              and lin["1"]["tipo"] == "SINTETICA" and b["total_debitos"] == b["total_creditos"] == D("1035.10")
              and b["soma_saldos_finais"] == sum((x["saldo_final"] for x in b["contas"]), D("0")) == D("0.00"),
              (lin["11"]["saldo_final"], lin["4"]["saldo_final"], b["soma_saldos_finais"]))
    import io
    from openpyxl import load_workbook
    reg = {"empresa": EMP, "competencia": COMP, "aprovacao": {"em": "2026-11-05T10:00:00-03:00"}}
    conteudo, _ = ex.gerar_balancete("SOL-2026-999999", reg, gerado, saldos_conc, plano_ex, {"tipo": "INTEGRAL", "texto": "única"}, "a.txt", "0" * 64,
                                     k.base_info)
    wb = load_workbook(io.BytesIO(conteudo))
    rows = list(wb["Balancete"].iter_rows(values_only=True))
    ident = {r[0]: r[1] for r in wb["Identificação"].iter_rows(values_only=True)}
    r75 = next(r for r in rows if r[0] == "75")
    registrar("S-02 planilha do balancete: código, classificação, descrição, saldo inicial D/C, débitos, créditos, saldo final D/C; "
              "identifica empresa, competência e a VERSÃO da base inicial",
              list(rows[0]) == ex.COLUNAS_BALANCETE and (r75[5], r75[6]) == (150, "C") and ident["Empresa"] == EMP
              and ident["Competência"] == COMP and f"versão {k.base_info['versao']}" in ident["Base inicial"], (r75, ident["Base inicial"][:80]))


def independencia():
    referencias = ("Downloads", "Balancete.pdf", "VGROW - CONCILIACAO", "CONCILIACAO 10.2026")
    alvos = [RAIZ / "API-LOCAL", RAIZ / "ESCRITORIO-VIRTUAL", RAIZ / "AGENTES", RAIZ / "COORDENADOR-GERAL" / "ferramentas", RAIZ / "TESTES" / "BASE-INICIAL"]
    achados = []
    for a in alvos:
        for p in a.rglob("*"):
            if p.is_file() and p.suffix in (".py", ".js", ".html", ".json", ".css") and "__pycache__" not in p.parts:
                t = p.read_text(encoding="utf-8", errors="ignore")
                achados += [f"{p.relative_to(RAIZ)}: {r}" for r in referencias if r in t and p.name != "testar_base_inicial.py"]
    registrar("I-01 independência dos arquivos de referência: nenhum código do aplicativo, agente ou teste permanente cita os exemplos "
              "(caminho de Downloads ou nomes de arquivo); tudo acima rodou só com dados fictícios gerados",
              not achados, achados[:5])


def main():
    antes = foto_operacional()
    try:
        for bloco in (casos_balancete, casos_contas, casos_book, casos_criacao_e_confirmacao, casos_conciliacao_e_saidas, independencia):
            try:
                bloco()
            except Exception as exc:
                import traceback
                registrar(f"{bloco.__name__} interrompido", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-600:]}")
    finally:
        registrar("I-02 ambiente operacional intocado (CLIENTES/ e registro reais)", foto_operacional() == antes)
        shutil.rmtree(TMP, ignore_errors=True)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {c}  — {d}")
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
