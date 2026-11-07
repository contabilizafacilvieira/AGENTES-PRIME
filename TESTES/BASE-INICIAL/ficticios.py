"""Geradores de dados 100% FICTÍCIOS para os testes da base inicial (balancete anterior + book contábil).

Nada aqui é copiado de arquivo real: o PDF é montado à mão (fluxo de conteúdo com texto posicionado em Helvetica, no LAYOUT de um
balancete do Domínio: cabeçalho de colunas, cabeçalho repetido por página, descrição quebrada, texto auxiliar, hífen solto e rodapé),
e os books são planilhas geradas com estruturas diferentes (abas renomeadas, cabeçalhos deslocados, títulos antigos, saldo acumulado,
fórmulas, pendências, evidências e histórico de baixas).
"""
import io
from decimal import Decimal

D = Decimal

# larguras Helvetica (1/1000 em) para alinhar valores à direita como no relatório
_L = dict(zip("abcdefghijklmnopqrstuvwxyz", [556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
                                              278, 556, 500, 722, 500, 500, 500]))
_L.update(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", [667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667,
                                              611, 722, 667, 944, 667, 667, 611]))
_L.update({c: 556 for c in "0123456789"})
_L.update({" ": 278, ".": 278, ",": 278, "-": 333, ":": 278, "/": 278, "(": 333, ")": 333, "é": 556, "ç": 500, "ã": 556, "í": 278,
           "ó": 556, "É": 667, "Ç": 722, "Ã": 667, "º": 365})


def largura(t, tam):
    return sum(_L.get(c, 556) for c in t) * tam / 1000


def br(v: Decimal, natureza=True) -> str:
    """Valor no formato do relatório: 1.234,56D / 1.234,56C; zero = 0,00 (sem natureza)."""
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + ("D" if v > 0 else "C" if v < 0 else "") if natureza else s


class PDF:
    """PDF mínimo, páginas em paisagem, Helvetica WinAnsi; texto posicionado (x, y) — sem bibliotecas externas."""

    def __init__(self):
        self.paginas = []

    def pagina(self):
        self.paginas.append([])
        return self.paginas[-1]

    @staticmethod
    def texto(p, x, y, t, tam=7, direita=False):
        if direita:
            x = x - largura(t, tam)
        e = t.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        p.append(b"BT /F1 %d Tf %.2f %.2f Td (" % (tam, x, y) + e + b") Tj ET")

    def bytes(self) -> bytes:
        objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
        kids = []
        for p in self.paginas:
            conteudo = b"\n".join(p)
            objs.append(b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream")
            objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>"
                        % len(objs))
            kids.append(len(objs))
        objs[1] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count %d >>" % len(kids)
        saida, pos = io.BytesIO(), []
        saida.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        for i, o in enumerate(objs, 1):
            pos.append(saida.tell())
            saida.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
        xref = saida.tell()
        saida.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % p for p in pos))
        saida.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
        return saida.getvalue()


COL = {"codigo": 40, "classif": 50, "descricao": 130, "saldo_anterior": 520, "debitos": 610, "creditos": 700, "saldo_atual": 790}


def pdf_balancete(empresa, cnpj, inicio, fim, contas, consolidado=None, por_pagina=22, quebrar=(), auxiliar=(), hifen=()) -> bytes:
    """contas: [(codigo, classificacao, descricao, saldo_anterior, debitos, creditos, saldo_atual)] com saldos ASSINADOS (D+).
    quebrar: códigos cuja descrição continua na linha seguinte; auxiliar: códigos seguidos de texto auxiliar fora das colunas;
    hifen: códigos com um hífen solto (outra camada de texto) na zona do código."""
    pdf = PDF()
    blocos = [contas[i:i + por_pagina] for i in range(0, len(contas), por_pagina)] or [[]]
    for n, bloco in enumerate(blocos, 1):
        p = pdf.pagina()
        PDF.texto(p, 10, 570, f"Empresa: {empresa}", 9)
        PDF.texto(p, 700, 570, f"Folha: {n:04d}", 8)
        PDF.texto(p, 10, 558, f"C.N.P.J.: {cnpj}", 8)
        PDF.texto(p, 300, 558, "BALANCETE", 10)
        PDF.texto(p, 10, 546, f"Período: {inicio} - {fim}", 8)
        if consolidado:
            PDF.texto(p, 300, 546, f"CONSOLIDADO (Empresas: {', '.join(consolidado)})", 8)
        y = 530
        PDF.texto(p, 10, y, "Código", 7)
        PDF.texto(p, COL["classif"], y, "Classificação", 7)
        PDF.texto(p, COL["descricao"], y, "Descrição da conta", 7)
        PDF.texto(p, COL["saldo_anterior"] - largura("Anterior", 7) - largura("Saldo ", 7), y, "Saldo", 7)
        PDF.texto(p, COL["saldo_anterior"], y, "Anterior", 7, direita=True)
        PDF.texto(p, COL["debitos"], y, "Débito", 7, direita=True)
        PDF.texto(p, COL["creditos"], y, "Crédito", 7, direita=True)
        PDF.texto(p, COL["saldo_atual"] - largura("Atual", 7) - largura("Saldo ", 7), y, "Saldo", 7)
        PDF.texto(p, COL["saldo_atual"], y, "Atual", 7, direita=True)
        y -= 14
        for cod, clas, desc, ant, deb, cre, atu in bloco:
            PDF.texto(p, COL["codigo"], y, cod, 7, direita=True)
            PDF.texto(p, COL["classif"], y, clas, 7)
            texto = desc[:28] if cod in quebrar else desc
            PDF.texto(p, COL["descricao"], y, texto, 7)
            PDF.texto(p, COL["saldo_anterior"], y, br(ant), 7, direita=True)
            PDF.texto(p, COL["debitos"], y, br(deb, False), 7, direita=True)
            PDF.texto(p, COL["creditos"], y, br(cre, False), 7, direita=True)
            PDF.texto(p, COL["saldo_atual"], y, br(atu), 7, direita=True)
            if cod in hifen:
                PDF.texto(p, 4.5, y + 2.4, "-", 7)
            y -= 10
            if cod in quebrar:
                PDF.texto(p, COL["descricao"], y, desc[28:].strip(), 7)
                y -= 10
            if cod in auxiliar:
                PDF.texto(p, 12, y + 4, "* conta com movimento no periodo", 5)
                y -= 6
        PDF.texto(p, 10, 20, "Sistema contábil fictício para testes - relatório de demonstração", 6)
        PDF.texto(p, 760, 20, f"Página {n}", 6)
    return pdf.bytes()


# ---------------------------------------------------------------- plano fictício com hierarquia (sintéticas + analíticas)
def contas_ficticias(saldos: dict, movimento: dict = None):
    """Hierarquia fictícia de 5 níveis. saldos: classificação analítica → saldo ANTERIOR assinado; movimento: classificação →
    (débitos, créditos). Sintéticas = soma das analíticas (como num balancete real)."""
    movimento = movimento or {}
    estrutura = [
        ("1", "1", "ATIVO"), ("2", "1.1", "ATIVO CIRCULANTE"), ("3", "1.1.1", "DISPONIBILIDADES"),
        ("4", "1.1.1.01", "BANCOS CONTA MOVIMENTO"), ("11", "1.1.1.01.000001", "BANCO FICTICIO ALFA C/C"),
        ("12", "1.1.1.01.000002", "BANCO FICTICIO BETA C/C"),
        ("5", "1.1.2", "CREDITOS"), ("6", "1.1.2.01", "CLIENTES"), ("21", "1.1.2.01.000001", "CLIENTES NACIONAIS"),
        ("7", "1.1.2.02", "ADIANTAMENTOS"), ("22", "1.1.2.02.000001", "ADIANTAMENTO A FORNECEDORES DE SERVICOS E MATERIAIS DIVERSOS"),
        ("23", "1.1.2.02.000002", "ADIANTAMENTO DE 13º SALARIO"),
        ("30", "2", "PASSIVO"), ("31", "2.1", "PASSIVO CIRCULANTE"), ("32", "2.1.1", "OBRIGACOES"), ("33", "2.1.1.01", "FORNECEDORES"),
        ("41", "2.1.1.01.000001", "FORNECEDORES NACIONAIS"), ("34", "2.1.1.02", "OBRIGACOES TRIBUTARIAS"),
        ("42", "2.1.1.02.000001", "ISS A RECOLHER"),
        ("50", "2.3", "PATRIMONIO LIQUIDO"), ("51", "2.3.1", "CAPITAL"), ("52", "2.3.1.01", "CAPITAL SOCIAL"),
        ("53", "2.3.1.01.000001", "CAPITAL SUBSCRITO"),
        ("60", "3", "RECEITAS"), ("61", "3.1", "RECEITA OPERACIONAL"), ("62", "3.1.1", "VENDAS"), ("63", "3.1.1.01", "SERVICOS"),
        ("64", "3.1.1.01.000001", "RECEITA DE SERVICOS"),
        ("70", "4", "DESPESAS"), ("71", "4.1", "DESPESAS OPERACIONAIS"), ("72", "4.1.1", "ADMINISTRATIVAS"), ("73", "4.1.1.01", "GERAIS"),
        ("74", "4.1.1.01.000001", "TARIFAS BANCARIAS"), ("75", "4.1.1.01.000002", "(-) RECUPERACAO DE DESPESAS"),
    ]
    folhas = {k for _, k, _ in estrutura if not any(o.startswith(k + ".") for _, o, _ in estrutura)}
    linhas = []
    for cod, k, desc in estrutura:
        filhas = [f for f in folhas if f == k or f.startswith(k + ".")]
        ant = sum((D(saldos.get(f, "0")) for f in filhas), D("0"))
        deb = sum((D(movimento.get(f, ("0", "0"))[0]) for f in filhas), D("0"))
        cre = sum((D(movimento.get(f, ("0", "0"))[1]) for f in filhas), D("0"))
        linhas.append((cod, k, desc, ant, deb, cre, ant + deb - cre))
    return linhas


SALDOS_PADRAO = {"1.1.1.01.000001": "15000.00", "1.1.1.01.000002": "2500.50", "1.1.2.01.000001": "8000.00",
                 "1.1.2.02.000001": "1200.00", "1.1.2.02.000002": "0", "2.1.1.01.000001": "-6000.00", "2.1.1.02.000001": "-700.50",
                 "2.3.1.01.000001": "-10000.00", "3.1.1.01.000001": "-30000.00", "4.1.1.01.000001": "20000.00",
                 "4.1.1.01.000002": "0"}
MOV_PADRAO = {"1.1.1.01.000001": ("5000.00", "3000.00"), "3.1.1.01.000001": ("0", "5000.00"), "4.1.1.01.000001": ("3000.00", "0"),
              "4.1.1.01.000002": ("0", "150.00"), "2.1.1.01.000001": ("150.00", "0")}
# depois do movimento: 4.1.1.01.000002 fica CREDORA (contrária à natureza de despesa) — preservada como informada


# ---------------------------------------------------------------- books (estruturas variadas)
def _wb():
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    return wb


def _bytes(wb) -> bytes:
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def book_padrao(empresa, cnpj, competencia_txt, data_base, contas_bal, composicoes, pendencias=(), evidencias=(), baixas=()) -> bytes:
    """Book no estilo 'uma aba por conta': ÍNDICE, BALANCETE (assinado), composições com rótulos 'Conta:', 'Data Base:', 'Método:',
    cabeçalho na linha 8, saldo ACUMULADO por fórmula, TOTAL/SALDO CONFORME BALANCETE/DIFERENÇA, situação e assinaturas.
    composicoes: [(nome_aba, classificacao, descricao, metodo, [(data, nf, descricao, debito, credito, obs)])]."""
    wb = _wb()
    ws = wb.create_sheet("ÍNDICE")
    ws["B3"], ws["F3"] = empresa, f"COMPETÊNCIA {competencia_txt} · CNPJ {cnpj}"
    ws["B4"] = "CONCILIAÇÃO CONTÁBIL (FICTÍCIA)"
    for i, (aba, *_r) in enumerate(composicoes, 6):
        ws.cell(i, 2, aba)
    b = wb.create_sheet("BALANCETE")
    b.append(["Conta", "Descrição", "Saldo anterior", "Débito", "Crédito", "Movimento", "Saldo atual", "Nível"])
    for cod, k, desc, ant, deb, cre, atu in contas_bal:
        b.append([k, desc, float(ant), float(deb), float(cre), float(deb - cre), float(atu), k.count(".") + 1])
    for aba, k, desc, metodo, itens in composicoes:
        w = wb.create_sheet(aba)
        w["B1"], w["C1"] = "‹ ÍNDICE", "BALANCETE"
        w["B3"], w["F3"] = empresa, f"COMPETÊNCIA {competencia_txt}"
        w["B6"], w["C6"], w["D6"], w["F6"], w["G6"] = "Conta:", k, f"{desc}   ·   {k}", "Natureza:", "não classificada"
        w["B7"], w["C7"], w["E7"], w["F7"], w["G7"] = "Data Base: ", data_base, "Moeda:", "Real - R$", f"Método: {metodo}"
        for j, t in enumerate(["Data Lançto", "NF", "Descrição", "Débito", "Crédito", "Saldo", "Observação"], 2):
            w.cell(8, j, t)
        r = 9
        for data, nf, d_, deb, cre, obs in itens:
            w.cell(r, 2, data)
            w.cell(r, 3, nf)
            w.cell(r, 4, d_)
            w.cell(r, 5, deb if not isinstance(deb, (int, float, Decimal)) else float(deb))
            w.cell(r, 6, float(cre) if isinstance(cre, (int, float, Decimal)) else cre)
            w.cell(r, 7, f"=E{r}-F{r}" if r == 9 else f"=G{r - 1}+E{r}-F{r}")
            w.cell(r, 8, obs)
            r += 1
        fim = r - 1
        t = r + 1
        w.cell(t, 2, "TOTAL")
        w.cell(t, 5, f"=SUM(E9:E{max(fim, 9)})")
        w.cell(t, 6, f"=SUM(F9:F{max(fim, 9)})")
        w.cell(t, 7, f"=E{t}-F{t}")
        w.cell(t, 8, f"{len(itens)} linha(s) na composição")
        w.cell(t + 2, 2, "SALDO CONFORME BALANCETE")
        w.cell(t + 2, 7, f"=VLOOKUP($C$6,BALANCETE!$A:$G,7,0)")
        w.cell(t + 3, 2, "DIFERENÇA")
        w.cell(t + 3, 7, f"=G{t}-G{t + 2}")
        w.cell(t + 5, 2, "SALDO · fecha")
        w.cell(t + 5, 4, "IDENTIFICAÇÃO · completa")
        w.cell(t + 5, 5, "EVIDÊNCIA · pendente")
        w.cell(t + 5, 7, "PENDÊNCIAS · nenhuma")
        w.cell(t + 7, 2, "OBSERVAÇÃO:")
        w.cell(t + 7, 3, "Composição fictícia para teste.")
        w.cell(t + 10, 6, "Preparado por:")
        w.cell(t + 10, 7, "Aprovado por:")
        w.cell(t + 11, 5, "Nome")
        w.cell(t + 11, 6, "Fulano Ficticio")
        w.cell(t + 11, 7, "Beltrano Ficticio")
    p = wb.create_sheet("PENDÊNCIAS")
    p.append(["Conta", "Tipo", "Severidade", "Título", "Detalhe", "Texto original", "Origem", "Situação"])
    for x in pendencias:
        p.append(list(x))
    h = wb.create_sheet("HISTÓRICO DE BAIXAS")
    h.append(["Conta", "Título", "Terceiro", "Documento", "Valor baixado", "Regra", "Cardinalidade", "Confiança", "Linha do razão",
              "Histórico do movimento", "Justificativa"])
    for x in baixas:
        h.append(list(x))
    e = wb.create_sheet("EVIDÊNCIAS")
    e.append(["Conta", "Conta analítica", "Arquivo", "Tipo reconhecido", "Extrator", "Escopo declarado", "Valor confrontado",
              "Data do saldo", "Saldo no documento", "Diferença", "Veredito", "Validada", "Explicação"])
    for x in evidencias:
        e.append(list(x))
    return _bytes(wb)


def book_variado(empresa_cnpj, data_base_txt, composicoes, extra_vazias=2, com_vinculo_externo=False) -> bytes:
    """Outra estrutura: abas com nomes arbitrários, cabeçalho deslocado (linha/coluna variáveis), conta pelo CÓDIGO REDUZIDO,
    colunas 'Fornecedor | Documento | Emissão | Vencimento | Valor em aberto' (sem débito/crédito), método por extenso, títulos
    antigos, fórmula aritmética e linhas de assinatura. composicoes: [(aba, linha_cab, col_ini, rotulo_conta, metodo, itens)]
    com itens [(terceiro, documento, emissao, vencimento, valor)] — valor pode ser fórmula '=...'."""
    wb = _wb()
    capa = wb.create_sheet("Capa")
    capa["A1"] = f"Pasta de composições — {empresa_cnpj}"
    for i in range(extra_vazias):
        wb.create_sheet(f"Plan{i + 1}")["C5"] = "rascunho sem tabela"
    for aba, lin, col, rotulo, metodo, itens in composicoes:
        w = wb.create_sheet(aba)
        w.cell(lin - 4, col, "Conta contábil:")
        w.cell(lin - 4, col + 1, rotulo)
        w.cell(lin - 3, col, "Posição em:")
        w.cell(lin - 3, col + 1, data_base_txt)
        w.cell(lin - 2, col, f"Método: {metodo}")
        for j, t in enumerate(["Fornecedor", "Documento", "Emissão", "Vencimento", "Valor em aberto"]):
            w.cell(lin, col + j, t)
        r = lin + 1
        for terc, doc, em, venc, val in itens:
            for j, v in enumerate([terc, doc, em, venc, val]):
                w.cell(r, col + j, float(v) if isinstance(v, Decimal) else v)
            r += 1
            if r == lin + 3:                           # cabeçalho repetido no meio (quebra de impressão)
                for j, t in enumerate(["Fornecedor", "Documento", "Emissão", "Vencimento", "Valor em aberto"]):
                    w.cell(r, col + j, t)
                r += 1
        w.cell(r + 1, col, "Total geral")
        w.cell(r + 1, col + 4, f"=SUM({chr(64 + col + 4)}{lin + 1}:{chr(64 + col + 4)}{r - 1})")
        w.cell(r + 4, col, "Responsável: Ciclano Ficticio")
    dados = _bytes(wb)
    if com_vinculo_externo:
        import zipfile
        entrada, saida = io.BytesIO(dados), io.BytesIO()
        with zipfile.ZipFile(entrada) as zi, zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zo:
            for it in zi.infolist():
                zo.writestr(it, zi.read(it.filename))
            zo.writestr("xl/externalLinks/externalLink1.xml", '<?xml version="1.0"?><externalLink xmlns="http://schemas.openxmlformats.org/'
                        'spreadsheetml/2006/main"><externalBook r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
                        '2006/relationships"/></externalLink>')
        dados = saida.getvalue()
    return dados
