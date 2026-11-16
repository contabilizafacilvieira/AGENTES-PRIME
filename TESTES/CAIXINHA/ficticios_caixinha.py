"""Documentos 100% FICTÍCIOS da rotina CAIXINHA (nada copiado de arquivo real; empresas, CNPJs e valores inventados).

Gera, para uma empresa fictícia e a competência 2026-10, os cinco documentos da rotina nos layouts suportados pelos leitores:
balancete (PDF em colunas do Domínio), razão (PDF em colunas do Domínio), pagamentos do e-CAC (PDF com blocos e composição),
relatório de situação fiscal (PDF) e resumo mensal da folha do Domínio (PDF). A escrituração é montada a partir de PARTIDAS
fictícias (janeiro a outubro/2026), de modo que razão e balancete concordem e os valores esperados sejam calculáveis.

Cenário (esperado na conciliação, competência 10/2026):
- Simples Nacional: jan–jun provisionados, pagos e baixados; jul, ago e set pagos no e-CAC SEM baixa no razão; out a vencer.
- INSS/IRRF (retenções do pró-labore): jan–jul pagos e baixados (o DARF de jul consta no e-CAC e no razão: "paga e contabilizada");
  ago e set pagos no e-CAC em DARF com DOIS tributos (composição informada) sem baixa no razão; out a vencer.
- Pró-labore: bruto 5.000,00, INSS 550,00, IRRF 402,35, líquido 4.047,65; líquidos de jan–mar pagos e baixados; abr–out em aberto.
"""
import sys
from decimal import Decimal as D
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "TESTES" / "BASE-INICIAL"))
import ficticios as fx  # noqa: E402

COMPETENCIA = "2026-10"


def cnpj(base12: str) -> str:
    def dv(n):
        pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if len(n) == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        r = sum(int(a) * b for a, b in zip(n, pesos)) % 11
        return "0" if r < 2 else str(11 - r)
    n = base12 + dv(base12)
    n += dv(n)
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


EMPRESAS = {
    "A": {"id": "CAIXINHA-ALFA-FICTICIA", "nome": "CAIXINHA ALFA FICTICIA LTDA", "cnpj": cnpj("917171710001")},
    "B": {"id": "CAIXINHA-BETA-FICTICIA", "nome": "CAIXINHA BETA FICTICIA LTDA", "cnpj": cnpj("928282820001")},
}
# código reduzido, classificação, descrição, grupo, tipo
PLANO = [
    ("1", "1", "ATIVO", "ATIVO", "S"), ("2", "1.1", "ATIVO CIRCULANTE", "ATIVO", "S"), ("3", "1.1.1", "DISPONIVEL", "ATIVO", "S"),
    ("11", "1.1.1.01", "CAIXA GERAL", "ATIVO", "A"), ("12", "1.1.1.02", "BANCO FICTICIO SEM MOVIMENTO", "ATIVO", "A"),
    ("20", "2", "PASSIVO", "PASSIVO", "S"), ("21", "2.1", "PASSIVO CIRCULANTE", "PASSIVO", "S"),
    ("22", "2.1.2", "OBRIGACOES TRABALHISTAS", "PASSIVO", "S"), ("301", "2.1.2.01", "PRO-LABORE A PAGAR", "PASSIVO", "A"),
    ("23", "2.1.3", "OBRIGACOES TRIBUTARIAS", "PASSIVO", "S"), ("401", "2.1.3.01", "SIMPLES NACIONAL A RECOLHER", "PASSIVO", "A"),
    ("402", "2.1.3.02", "INSS A RECOLHER", "PASSIVO", "A"), ("403", "2.1.3.03", "IRRF A RECOLHER", "PASSIVO", "A"),
    ("404", "2.1.3.04", "FGTS A RECOLHER", "PASSIVO", "A"),
    ("29", "2.3", "PATRIMONIO LIQUIDO", "PATRIMONIO_LIQUIDO", "S"), ("291", "2.3.1", "CAPITAL SOCIAL", "PATRIMONIO_LIQUIDO", "A"),
    ("30", "3", "RECEITAS", "RECEITA", "S"), ("601", "3.1", "RECEITA DE SERVICOS", "RECEITA", "A"),
    ("40", "4", "DESPESAS", "DESPESA", "S"), ("501", "4.1", "SIMPLES NACIONAL (DESPESA)", "DESPESA", "A"),
    ("502", "4.2", "PRO-LABORE (DESPESA)", "DESPESA", "A"), ("503", "4.3", "MULTAS FISCAIS", "DESPESA", "A"),
    ("504", "4.4", "JUROS PASSIVOS", "DESPESA", "A"),
]
ROTINA = {"CAIXA_GERAL": "11", "SIMPLES_NACIONAL": "401", "INSS": "402", "IRRF": "403", "PRO_LABORE": "301", "FGTS": None,
          "MULTAS_FISCAIS": "503", "JUROS_FISCAIS": "504"}
CLASSIF = {c: k for c, k, *_ in PLANO}
DESC = {c: d for c, _, d, *_ in PLANO}

SIMPLES = {1: "2900.00", 2: "2900.00", 3: "2900.00", 4: "2900.00", 5: "2900.00", 6: "2900.00", 7: "3100.00", 8: "3250.40", 9: "3400.55",
           10: "3500.00"}
BRUTO, INSS, IRRF = D("5000.00"), D("550.00"), D("402.35")
LIQ = BRUTO - INSS - IRRF


def fim_mes(m):
    import calendar
    return f"{calendar.monthrange(2026, m)[1]:02d}/{m:02d}/2026"


PARTIDAS_EXTRAS = []          # testes: lançamentos adicionais (ex.: baixas importadas no Domínio) — [(data, débito, crédito, valor, hist)]


def partidas(cenario="A"):
    """[(data dd/mm/aaaa, débito, crédito, valor Decimal, histórico)] da escrituração fictícia de jan–out/2026."""
    p = [("02/01/2026", "11", "291", D("40000.00"), "INTEGRALIZACAO DE CAPITAL EM DINHEIRO")] + list(PARTIDAS_EXTRAS)
    for m in range(1, 11):
        mm = f"{m:02d}/2026"
        p.append((f"10/{m:02d}/2026", "11", "601", D("12000.00"), f"RECEBIMENTO DE SERVICOS {mm}"))
        p.append((fim_mes(m), "501", "401", D(SIMPLES[m]), f"SIMPLES NACIONAL COMPETENCIA {mm}"))
        p.append((fim_mes(m), "502", "301", BRUTO, f"PRO-LABORE COMPETENCIA {mm}"))
        p.append((fim_mes(m), "301", "402", INSS, f"INSS S/ PRO-LABORE {mm}"))
        p.append((fim_mes(m), "301", "403", IRRF, f"IRRF S/ PRO-LABORE {mm}"))
    for m in range(1, 7):            # Simples jan–jun pago e baixado no dia 20 do mês seguinte
        p.append((f"20/{m + 1:02d}/2026", "401", "11", D(SIMPLES[m]), f"PAGTO DAS SIMPLES NACIONAL {m:02d}/2026"))
    for m in range(1, 8):            # DARF INSS/IRRF jan–jul pago e baixado
        p.append((f"20/{m + 1:02d}/2026", "402", "11", INSS, f"PAGTO DARF INSS {m:02d}/2026"))
        p.append((f"20/{m + 1:02d}/2026", "403", "11", IRRF, f"PAGTO DARF IRRF {m:02d}/2026"))
    for m in range(1, 4):            # líquido do pró-labore jan–mar pago e baixado
        p.append((f"05/{m + 1:02d}/2026", "301", "11", LIQ, f"PAGTO PRO-LABORE {m:02d}/2026"))
    return sorted(p, key=lambda x: (x[0][6:], x[0][3:5], x[0][:2]))


def _iso(d):
    return f"{d[6:]}-{d[3:5]}-{d[:2]}"


def razao_contas(contas=("11", "301", "401", "402", "403"), cenario="A"):
    """{conta: [(data, lote, historico, debito, credito, saldo assinado, contrapartida)]} com saldo anterior 0 em 01/01/2026."""
    saida = {}
    for n, (data, deb, cre, v, hist) in enumerate(partidas(cenario), 1):
        for conta, lado, outra in ((deb, "D", cre), (cre, "C", deb)):
            if conta in contas:
                saida.setdefault(conta, []).append((data, n, hist, v if lado == "D" else D("0"), v if lado == "C" else D("0"), outra))
    for conta, linhas in saida.items():
        s = D("0")
        novas = []
        for data, lote, hist, d, c, outra in linhas:
            s += d - c
            novas.append((data, lote, hist, d, c, s, outra))
        saida[conta] = novas
    return saida


def razao_pdf(cenario="A", contas=("11", "301", "401", "402", "403"), por_pagina=40) -> bytes:
    e = EMPRESAS[cenario]
    pdf = fx.PDF()
    linhas = []
    for conta in contas:
        movs = razao_contas(contas, cenario).get(conta, [])
        linhas.append(("CONTA", f"Conta: {conta} - {CLASSIF[conta]} {DESC[conta]}"))
        linhas.append(("ANT", "0,00"))
        for m in movs:
            linhas.append(("MOV", m))
        td = sum((m[3] for m in movs), D("0"))
        tc = sum((m[4] for m in movs), D("0"))
        linhas.append(("TOT", (td, tc)))
    blocos = [linhas[i:i + por_pagina] for i in range(0, len(linhas), por_pagina)]
    for n, bloco in enumerate(blocos, 1):
        p = pdf.pagina()
        fx.PDF.texto(p, 10, 570, f"Empresa: {e['nome']}", 9)
        fx.PDF.texto(p, 700, 570, f"Folha: {n:04d}", 8)
        fx.PDF.texto(p, 10, 558, f"C.N.P.J.: {e['cnpj']}", 8)
        fx.PDF.texto(p, 380, 558, "RAZÃO", 10)
        fx.PDF.texto(p, 10, 546, "Período: 01/01/2026 - 31/10/2026", 8)
        y = 530
        for x, t, dir_ in ((10, "Data", False), (62, "Lote", False), (95, "Histórico", False), (520, "Débito", True), (610, "Crédito", True),
                           (700, "Saldo", True), (760, "C.Part.", False)):
            fx.PDF.texto(p, x, y, t, 7, direita=dir_)
        y -= 13
        for tipo, conteudo in bloco:
            if tipo == "CONTA":
                fx.PDF.texto(p, 10, y, conteudo, 7)
            elif tipo == "ANT":
                fx.PDF.texto(p, 95, y, "Saldo anterior", 7)
                fx.PDF.texto(p, 700, y, conteudo, 7, direita=True)
            elif tipo == "MOV":
                data, lote, hist, d, c, s, outra = conteudo
                fx.PDF.texto(p, 10, y, data, 7)
                fx.PDF.texto(p, 62, y, str(lote), 7)
                fx.PDF.texto(p, 95, y, hist, 7)
                if d:
                    fx.PDF.texto(p, 520, y, fx.br(d, False), 7, direita=True)
                if c:
                    fx.PDF.texto(p, 610, y, fx.br(c, False), 7, direita=True)
                fx.PDF.texto(p, 700, y, fx.br(s) if s else "0,00", 7, direita=True)
                fx.PDF.texto(p, 760, y, outra, 7)
            else:
                td, tc = conteudo
                fx.PDF.texto(p, 95, y, "Total da conta", 7)
                fx.PDF.texto(p, 520, y, fx.br(td, False), 7, direita=True)
                fx.PDF.texto(p, 610, y, fx.br(tc, False), 7, direita=True)
            y -= 11
        fx.PDF.texto(p, 10, 20, "Sistema contábil fictício para testes - relatório de demonstração", 6)
    return pdf.bytes()


def balancete_linhas(cenario="A"):
    """[(código, classificação, descrição, anterior, débitos, créditos, atual)] de OUTUBRO, sintéticas = soma das analíticas."""
    ant, deb, cre = {}, {}, {}
    for data, d, c, v, _ in partidas(cenario):
        mes = int(data[3:5])
        for conta, sinal in ((d, 1), (c, -1)):
            if mes < 10:
                ant[conta] = ant.get(conta, D("0")) + sinal * v
            elif sinal > 0:
                deb[conta] = deb.get(conta, D("0")) + v
            else:
                cre[conta] = cre.get(conta, D("0")) + v
    analiticas = [(c, k, d) for c, k, d, _, t in PLANO if t == "A"]
    linhas = {c: (c, k, d, ant.get(c, D("0")), deb.get(c, D("0")), cre.get(c, D("0")),
                  ant.get(c, D("0")) + deb.get(c, D("0")) - cre.get(c, D("0"))) for c, k, d in analiticas}
    saida = []
    for c, k, d, _, t in PLANO:
        if t == "A":
            saida.append(linhas[c])
        else:
            f = [x for x in linhas.values() if x[1].startswith(k + ".")]
            saida.append((c, k, d, *(sum((x[i] for x in f), D("0")) for i in (3, 4, 5, 6))))
    return sorted(saida, key=lambda x: [int(p) for p in x[1].split(".")])


def balancete_pdf(cenario="A") -> bytes:
    e = EMPRESAS[cenario]
    return fx.pdf_balancete(e["nome"], e["cnpj"], "01/10/2026", "31/10/2026", balancete_linhas(cenario))


def _pdf_texto(linhas_por_pagina, tam=8) -> bytes:
    pdf = fx.PDF()
    for linhas in linhas_por_pagina:
        p = pdf.pagina()
        y = 570
        for l in linhas:
            fx.PDF.texto(p, 20, y, l, tam)
            y -= 12
    return pdf.bytes()


def _brl(v):
    return fx.br(D(v), False)


SIMPLES_COMPOSICAO = (("1001", "IRPJ - SIMPLES NACIONAL", "0.055"), ("1002", "CSLL - SIMPLES NACIONAL", "0.035"),
                      ("1004", "COFINS - SIMPLES NACIONAL", "0.1274"), ("1005", "PIS - SIMPLES NACIONAL", "0.0276"),
                      ("1006", "INSS - SIMPLES NACIONAL", "0.434"))


def _comp_das(total: D):
    partes, acumulado = [], D("0")
    for i, (cod, den, frac) in enumerate(SIMPLES_COMPOSICAO):
        v = (total * D(frac)).quantize(D("0.01")) if i < len(SIMPLES_COMPOSICAO) - 1 else total - acumulado
        acumulado += v
        partes.append((cod, den, v))
    partes.append(("1010", "ISS - SIMPLES NACIONAL", total - acumulado)) if acumulado != total else None
    return [x for x in partes if x[2]]


def ecac_blocos(cenario="A", extras=()):
    """Pagamentos do e-CAC: DAS jul/ago/set e DARF (INSS+IRRF) jul/ago/set. extras: blocos adicionais (testes)."""
    blocos = []
    for m, pago in ((7, "20/08/2026"), (8, "21/09/2026"), (9, "20/10/2026")):
        total = D(SIMPLES[m])
        blocos.append({"tipo": "DAS", "numero": f"07.20.26{m:02d}.0000{m:03d}-{m}", "pa": f"{m:02d}/2026", "pago": pago, "venc": pago,
                       "total": total, "comp": _comp_das(total)})
    for m, pago in ((7, "20/08/2026"), (8, "18/09/2026"), (9, "20/10/2026")):
        blocos.append({"tipo": "DARF", "numero": f"07.01.26{m:02d}.5555{m:03d}-{m}", "pa": fim_mes(m), "pago": pago, "venc": f"20/{m + 1:02d}/2026",
                       "total": INSS + IRRF, "comp": [("1082", "CP SEGURADOS - CONTRIBUINTE INDIVIDUAL", INSS),
                                                      ("0561", "IRRF - RENDIMENTO DO TRABALHO", IRRF)]})
    return blocos + list(extras)


def ecac_pdf(cenario="A", extras=(), blocos=None) -> bytes:
    e = EMPRESAS[cenario]
    cab = ["MINISTÉRIO DA FAZENDA - RECEITA FEDERAL DO BRASIL", "e-CAC - Centro Virtual de Atendimento",
           "CONSULTA DE PAGAMENTOS - Pagamentos Efetuados", f"CNPJ: {e['cnpj']} - {e['nome']}", "Data da consulta: 05/11/2026", ""]
    paginas, atual = [], list(cab)
    for b in (blocos if blocos is not None else ecac_blocos(cenario, extras)):
        linhas = [f"Tipo do Documento: {b['tipo']}   Número do Documento: {b['numero']}",
                  f"Período de Apuração: {b['pa']}   Data de Vencimento: {b['venc']}"
                  + (f"   Data de Arrecadação: {b['pago']}" if b.get("pago") else ""),
                  f"Valor Total: {_brl(b['total'])}"]
        if b.get("codigo"):
            linhas.append(f"Código de Receita: {b['codigo']}")
        if b.get("comp"):
            linhas += ["Composição do Documento de Arrecadação", "Código Denominação Principal Multa Juros Total"]
            linhas += [f"{c} {den} {_brl(v)} 0,00 0,00 {_brl(v)}" if len(x) == 3 else f"{c} {den} {_brl(x[2])} {_brl(x[3])} {_brl(x[4])} {_brl(x[5])}"
                       for x in b["comp"] for c, den, v in [x[:3]]]
            linhas.append(f"Totais {_brl(b['total'])}")
        linhas.append("")
        if len(atual) + len(linhas) > 44:
            paginas.append(atual)
            atual = list(cab)
        atual += linhas
    paginas.append(atual)
    return _pdf_texto(paginas)


def situacao_fiscal_pdf(cenario="A", itens=None, emissao="05/11/2026", sem_pendencias=False) -> bytes:
    e = EMPRESAS[cenario]
    raiz = e["cnpj"][:10]
    linhas = ["MINISTÉRIO DA FAZENDA", "SECRETARIA ESPECIAL DA RECEITA FEDERAL DO BRASIL", "PROCURADORIA-GERAL DA FAZENDA NACIONAL",
              "INFORMAÇÕES DE APOIO PARA EMISSÃO DE CERTIDÃO", f"Data: {emissao}", f"CNPJ: {raiz} - {e['nome']}",
              "Diagnóstico Fiscal na Receita Federal e Procuradoria-Geral da Fazenda Nacional"]
    if sem_pendencias:
        linhas.append("Não foram detectadas pendências/exigibilidades suspensas nos controles da Receita Federal e da Procuradoria-Geral da Fazenda Nacional.")
    else:
        linhas += ["Pendência - Débito (SIMPLES NACIONAL)", "Receita PA/Exerc. Dt. Vcto Vl.Original Sdo.Devedor Situação"]
        for it in itens if itens is not None else [("", "SIMPLES NACIONAL", "10/2026", "20/11/2026", D(SIMPLES[10]), "A VENCER")]:
            cod, den, pa, venc, v, sit = it
            linhas.append(f"{(cod + ' - ') if cod else ''}{den} {pa} {venc} {_brl(v)} {_brl(v)} {sit}")
    return _pdf_texto([linhas])


def folha_pdf(cenario="A", competencia="10/2026", bruto=BRUTO, inss=INSS, irrf=IRRF, extra_provento=None) -> bytes:
    e = EMPRESAS[cenario]
    prov = bruto + (extra_provento[1] if extra_provento else D("0"))
    desc = inss + irrf
    linhas = [f"Empresa: {e['nome']}", f"CNPJ: {e['cnpj']}", "RESUMO MENSAL DA FOLHA", f"Competência: {competencia}   Cálculo: Pró-labore",
              "Contribuinte: 1 - SOCIO FICTICIO UM", "Código Descrição Referência Proventos Descontos",
              f"8781 PRO-LABORE 30,00 {_brl(bruto)}"]
    if extra_provento:
        linhas.append(f"0001 {extra_provento[0]} 30,00 {_brl(extra_provento[1])}")
    linhas += [f"8111 INSS 11,00 {_brl(inss)}", f"8121 IRRF 27,50 {_brl(irrf)}",
               f"Total de Proventos: {_brl(prov)}", f"Total de Descontos: {_brl(desc)}", f"Líquido: {_brl(prov - desc)}",
               "Emitido em: 05/11/2026"]
    return _pdf_texto([linhas])


def documentos(cenario="A") -> list:
    return [("01_balancete_2026-10.pdf", balancete_pdf(cenario)), ("02_razao_2026.pdf", razao_pdf(cenario)),
            ("03_pagamentos_ecac.pdf", ecac_pdf(cenario)), ("04_situacao_fiscal.pdf", situacao_fiscal_pdf(cenario)),
            ("05_resumo_folha_2026-10.pdf", folha_pdf(cenario))]


def esperado(cenario="A") -> dict:
    """Valores esperados do cenário, calculados das PARTIDAS fictícias (nada fixado à mão)."""
    bal = {x[0]: x[6] for x in balancete_linhas(cenario)}
    # Simples: jul, ago e set pagos no e-CAC e não baixados; DARF de jul já baixado no razão (paga e contabilizada).
    baixas = {"401": D(SIMPLES[7]) + D(SIMPLES[8]) + D(SIMPLES[9]), "402": INSS * 2, "403": IRRF * 2}
    folha_saldo = -bal["301"]
    total = sum(baixas.values(), D("0"))
    return {"saldos": {k: -bal[k] for k in ("401", "402", "403", "301")}, "caixa": bal["11"], "baixas_tributarias": baixas,
            "restantes": {k: -bal[k] - v for k, v in baixas.items()}, "total_tributarias": total, "ultimo_liquido": LIQ,
            "baixa_folha": folha_saldo - LIQ, "caixa_projetado": bal["11"] - total - (folha_saldo - LIQ)}


# ---------------------------------------------------------------- LAYOUTS conferidos com arquivos reais (dados FICTÍCIOS)
def ecac_comprovantes_pdf(cenario="A", blocos=None) -> bytes:
    """e-CAC "Comprovante de Arrecadação": um documento por página, rótulos numa linha e valores na seguinte; composição em
    Principal · Multa · Juros · Total ('-' = sem valor); data de arrecadação e valor reservado/restituído no rodapé."""
    e = EMPRESAS[cenario]
    paginas = []
    for b in (blocos if blocos is not None else ecac_blocos(cenario)):
        rotulo_pa = "Competência" if b["tipo"] == "DAS" else "Período Apuração"
        linhas = ["Data de Vencimento", f"{e['cnpj']} {e['nome']}", f"{b['pa']} {b['venc']} {cnpj_digitos(b['numero'])}", "CNPJ", rotulo_pa,
                  f"Comprovamos que consta nos sistemas da Receita Federal registro de arrecadação de {b['tipo']} com os dados a seguir:",
                  "Razão Social", "Número do Documento", "Comprovante de Arrecadação", "Código Descrição TotalJurosMultaPrincipal",
                  "Composição do Documento de Arrecadação"]
        for x in b.get("comp") or []:
            linhas.append(f"{x[0]} {x[1]} {_brl(x[2])} - - {_brl(x[2])}")
        linhas += [f"Totais {_brl(b['total'])} 0,00 0,00 {_brl(b['total'])}",
                   "Comprovante emitido às 12:00:00 de 05/11/2026 (horário de Brasília), sob o código de controle",
                   "Banco Data de Arrecadação", "Agência Estabelecimento Valor Reservado/Restituído Referência",
                   (f"{b['pago']}Documento pago via PIX" if b.get("pago") else "Documento não pago"), "0,00"]
        paginas.append(linhas)
    return _pdf_texto(paginas)


def cnpj_digitos(numero):
    return "".join(ch for ch in str(numero) if ch.isdigit())


def folha_secoes_pdf(cenario="A", competencia="10/2026", bruto=BRUTO, inss=INSS, irrf=IRRF) -> bytes:
    """Resumo da Folha do Domínio por SEÇÕES: PROVENTOS / DESCONTOS com '<valor>Total:' e '<valor>Líquido Geral:'."""
    e = EMPRESAS[cenario]
    linhas = ["1/1Página:", "RESUMO DA FOLHA", f"Empresa: 1 - {e['nome']}", f"CNPJ: {e['cnpj']} Emissão: 05/11/2026",
              "Cálculo: Folha Mensal e Complementar", f"Competência: {competencia}", "Folha Mensal", "PROVENTOS",
              f"PRO-LABORE DIAS9380 1 30,00 {_brl(bruto)}", f"{_brl(bruto)}Total:", "DESCONTOS",
              f"INSS EMPREGADOR843 1 11,00 {_brl(inss)}", f"IRRF FOLHA8121 1 27,50 {_brl(irrf)}", f"{_brl(inss + irrf)}Total:",
              f"{_brl(bruto - inss - irrf)}Líquido Geral:", "Total: Resumo Geral Mensal e Complementar",
              f"Salário contribuição contribuintes: {_brl(bruto)}", f"Total INSS: {_brl(inss)}"]
    return _pdf_texto([linhas])


def balancete_sem_classificacao_pdf(cenario="A") -> bytes:
    """Balancete do Domínio SEM a coluna Classificação: hierarquia pelo RECUO da descrição; camada de texto duplicada à esquerda."""
    e = EMPRESAS[cenario]
    pdf = fx.PDF()
    p = pdf.pagina()
    fx.PDF.texto(p, 0, 833 - 260, f"Empresa: {e['nome']}", 8)
    fx.PDF.texto(p, 0, 824 - 260, f"C.N.P.J.: {e['cnpj']}", 8)
    fx.PDF.texto(p, 0, 815 - 260, "Período: 01/10/2026 - 31/10/2026", 8)
    fx.PDF.texto(p, 261, 796 - 260, "BALANCETE", 9)
    y = 778 - 260
    fx.PDF.texto(p, 1, y, "Código", 7)
    fx.PDF.texto(p, 28, y, "Descrição da conta", 7)
    fx.PDF.texto(p, 301, y, "Saldo Anterior", 7)
    fx.PDF.texto(p, 422, y, "Débito", 7, direita=True)
    fx.PDF.texto(p, 493, y, "Crédito", 7, direita=True)
    fx.PDF.texto(p, 524, y, "Saldo Atual", 7)
    y -= 11
    for cod, k, desc, ant, deb, cre, atu in balancete_linhas(cenario):
        nivel = k.count(".") + 1
        fx.PDF.texto(p, 25, y, cod, 7, direita=True)
        fx.PDF.texto(p, 35 + 6.4 * (nivel - 1), y, desc, 7)
        fx.PDF.texto(p, 352, y, fx.br(ant) if ant else "0,00", 7, direita=True)
        fx.PDF.texto(p, 422, y, fx.br(deb, False), 7, direita=True)
        fx.PDF.texto(p, 493, y, fx.br(cre, False), 7, direita=True)
        fx.PDF.texto(p, 564, y, fx.br(atu) if atu else "0,00", 7, direita=True)
        if any(x[1].startswith(k + ".") for x in balancete_linhas(cenario)):
            fx.PDF.texto(p, 1, y - 2, desc, 7)              # camada auxiliar duplicada (sintéticas), como no relatório real
        y -= 9.5
    return pdf.bytes()


def razao_xlsx(cenario="A", contas=("11", "301", "401", "402", "403")) -> bytes:
    """Razão do Domínio exportado em planilha: cabeçalho (Empresa, C.N.P.J., Período, RAZÃO), linha de colunas e seções 'Conta:'
    com SALDO ANTERIOR e lançamentos (Data, Número, Histórico, Cta.C.Part., Débito, Crédito, Saldo, Saldo-Exercício)."""
    import datetime as dt
    import io
    from openpyxl import Workbook
    e = EMPRESAS[cenario]
    wb = Workbook()
    ws = wb.active
    ws.title = "Razão"
    ws.append(["Empresa:", "", e["nome"], "", "", "", "", "", "", "", "", "Folha:", "", 1])
    ws.append(["C.N.P.J.:", "", e["cnpj"]])
    ws.append(["Período:", "", "01/01/2026 - 31/10/2026"])
    ws.append([])
    ws.append(["RAZÃO"])
    ws.append([])
    ws.append(["Data", "Número", "Histórico", "", "", "", "Cta.C.Part.", "Débito", "Crédito", "Saldo", "", "", "Saldo-Exercício"])
    movs = razao_contas(contas, cenario)
    for conta in contas:
        ws.append(["Conta:", float(conta), CLASSIF[conta], "", DESC[conta]])
        ws.append(["", "", "SALDO ANTERIOR", "", "", "", "", "", "", "", "", "", 0.0])
        for data, lote, hist, d, c, s, outra in movs.get(conta, []):
            ws.append([dt.date(int(data[6:]), int(data[3:5]), int(data[:2])), float(lote), hist, "", "", "", float(outra),
                       float(d) if d else "", float(c) if c else "", float(d - c), "", "", float(s)])
    ws.append([])
    ws.append(["Sistema contábil fictício para testes."])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def documentos_layout_real(cenario="A") -> list:
    """Os cinco documentos nos LAYOUTS conferidos com os arquivos reais (valores fictícios do cenário)."""
    return [("01_balancete.pdf", balancete_sem_classificacao_pdf(cenario)), ("02_razao.xlsx", razao_xlsx(cenario)),
            ("03_comprovantes_ecac.pdf", ecac_comprovantes_pdf(cenario)), ("04_situacao_fiscal.pdf", situacao_fiscal_pdf(cenario)),
            ("05_resumo_folha.pdf", folha_secoes_pdf(cenario))]
