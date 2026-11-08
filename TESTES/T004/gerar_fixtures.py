"""Gerador das fixtures FICTÍCIAS do T-004 (Agente de Documentos).

Todos os arquivos são construídos byte a byte por este script (PDF, PNG, XML) ou pelo openpyxl (XLSX),
sem usar nenhum documento real como modelo. Todos os nomes, CNPJs (sem dígito verificador válido),
chaves e valores são sintéticos. Ambiente das NF-e: tpAmb=2 (homologação).

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/T004/gerar_fixtures.py

Saída (recriada a cada execução, somente nestas pastas):
    CLIENTES/EMPRESA-TESTE/T004/{PDF,SCAN,XLSX,XML}/
    CLIENTES/EMPRESA-ISOLAMENTO/T004/

Fixtures "maliciosas" são as menores possíveis para provar a proteção (nada é executável):
    PDF-07 tem uma ação JavaScript inerte ("void 0"); XML-06/07 têm DOCTYPE/ENTITY mínimos apontando
    para recurso inexistente; XLSX-09 tem taxa de compressão desproporcional (cerca de 20 MB de espaços).
"""

import datetime as dt
import io
import os
import re
import shutil
import struct
import sys
import zipfile
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PASTA_CLIENTES = Path(os.environ.get("AGENTES_PRIME_FIXTURES_DESTINO", str(RAIZ / "CLIENTES"))).resolve()
DESTINO_TESTE = PASTA_CLIENTES / "EMPRESA-TESTE" / "T004"
DESTINO_ISOLAMENTO = PASTA_CLIENTES / "EMPRESA-ISOLAMENTO" / "T004"
DATA_FIXA = (2026, 1, 1, 0, 0, 0)

CNPJ_EMITENTE = "22222222222222"      # FORNECEDOR FICTICIO (sem DV válido)
CNPJ_TESTE = "11111111111111"         # EMPRESA TESTE FICTICIA (sem DV válido)
CNPJ_ISOLAMENTO = "99999999999999"    # EMPRESA ISOLAMENTO FICTICIA (sem DV válido)


# ============================================================ utilidades
def gravar(pasta: Path, nome: str, dados: bytes) -> None:
    destino = (pasta / nome).resolve()
    if destino.parent != pasta.resolve() or not str(destino).startswith(str(PASTA_CLIENTES)):
        raise SystemExit(f"destino fora das pastas de fixtures: {destino}")
    destino.write_bytes(dados)


def dv_chave(chave43: str) -> str:
    soma, peso = 0, 2
    for d in reversed(chave43):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    dv = 11 - soma % 11
    return "0" if dv >= 10 else str(dv)


def chave_nfe(mod: str, numero: int, cnpj: str = CNPJ_EMITENTE) -> str:
    base = f"35" f"2609" f"{cnpj}" f"{mod}" f"001" f"{numero:09d}" f"1" f"12345678"
    return base + dv_chave(base)


# ============================================================ PDF construído byte a byte
def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def montar_pdf(paginas, extra_catalogo: str = "") -> bytes:
    """paginas: lista de dicts {"linhas": [str], "imagem": (largura, altura, pixels_cinza) | None,
    "bruto": bytes (operadores de conteúdo acrescentados como estão; usado só nos testes negativos)}."""
    objs = []

    def add(b):
        objs.append(b)
        return len(objs)

    catalogo = add(None)
    raiz_paginas = add(None)
    fonte = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    filhos = []
    for p in paginas:
        conteudo = b""
        recursos = f"/Font << /F1 {fonte} 0 R >>"
        if p.get("linhas"):
            partes = ["BT /F1 11 Tf 14 TL 56 780 Td"] + [f"({_esc(l)}) Tj T*" for l in p["linhas"]] + ["ET"]
            conteudo += "\n".join(partes).encode("cp1252")
        if p.get("imagem"):
            larg, alt, px = p["imagem"]
            dados = zlib.compress(px, 9)
            img = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray "
                      b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (larg, alt, len(dados))
                      + dados + b"\nendstream")
            recursos += f" /XObject << /Im1 {img} 0 R >>"
            conteudo += b"\nq %d 0 0 %d 56 600 cm /Im1 Do Q" % (larg, alt)
        if p.get("bruto"):
            conteudo += b"\n" + p["bruto"]
        cont = add(b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream")
        filhos.append(add(f"<< /Type /Page /Parent {raiz_paginas} 0 R /MediaBox [0 0 595 842] "
                          f"/Resources << {recursos} >> /Contents {cont} 0 R >>".encode()))
    objs[catalogo - 1] = f"<< /Type /Catalog /Pages {raiz_paginas} 0 R {extra_catalogo}>>".encode()
    objs[raiz_paginas - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in filhos)}] /Count {len(filhos)} >>".encode()

    saida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posicoes = []
    for i, o in enumerate(objs, 1):
        posicoes.append(len(saida))
        saida += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    inicio_xref = len(saida)
    saida += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for pos in posicoes:
        saida += f"{pos:010d} 00000 n \n".encode()
    saida += f"trailer\n<< /Size {len(objs) + 1} /Root {catalogo} 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n".encode()
    return bytes(saida)


# ============================================================ texto desenhado em pixels (sem camada de texto)
GLIFOS = {
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "$": ["..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    ",": [".....", ".....", ".....", ".....", ".##..", "..#..", ".#..."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
}


def desenhar(texto: str, escala: int = 4, margem: int = 8):
    larg = margem * 2 + len(texto) * 6 * escala
    alt = margem * 2 + 7 * escala
    px = bytearray(b"\xff" * (larg * alt))
    for i, ch in enumerate(texto):
        for r, linha in enumerate(GLIFOS[ch]):
            for c, v in enumerate(linha):
                if v != "#":
                    continue
                for dy in range(escala):
                    for dx in range(escala):
                        px[(margem + r * escala + dy) * larg + margem + (i * 6 + c) * escala + dx] = 0
    return larg, alt, bytes(px)


def montar_png(larg: int, alt: int, px: bytes) -> bytes:
    bruto = b"".join(b"\x00" + px[y * larg:(y + 1) * larg] for y in range(alt))

    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", larg, alt, 8, 0, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(bruto, 9)) + bloco(b"IEND", b""))


# JPG estruturalmente mínimo (marcadores SOI/APP0/EOI). Não decodificável: o extrator não decodifica imagens.
JPG_MINIMO = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


# ============================================================ XLSX (openpyxl) com ZIP normalizado
def zip_normalizado(dados: bytes, extras: dict = None) -> bytes:
    """Regrava o ZIP com data fixa (arquivos reproduzíveis) e acrescenta membros extras."""
    saida = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(dados)) as origem, zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for nome in origem.namelist():
            conteudo = origem.read(nome)
            if nome == "docProps/core.xml":  # o openpyxl grava a data/hora do salvamento
                conteudo = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)", rb"\g<1>2026-01-01T00:00:00Z\g<2>", conteudo)
            destino.writestr(zipfile.ZipInfo(nome, DATA_FIXA), conteudo, zipfile.ZIP_DEFLATED)
        for nome, conteudo in (extras or {}).items():
            destino.writestr(zipfile.ZipInfo(nome, DATA_FIXA), conteudo, zipfile.ZIP_DEFLATED)
    return saida.getvalue()


def montar_xlsx(preparar, extras: dict = None) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.properties.created = wb.properties.modified = dt.datetime(2026, 1, 1)
    wb.properties.creator = "gerador T-004 (ficticio)"
    preparar(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return zip_normalizado(buf.getvalue(), extras)


def xlsx_estilo_invalido(dados: bytes) -> bytes:
    """Fixture válida de ZIP/worksheet com `styles.xml` de fill estruturalmente inválido."""
    saida = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(dados)) as origem, zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for nome in origem.namelist():
            conteudo = origem.read(nome)
            if nome == "xl/styles.xml":
                conteudo = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                            b'<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                            b'<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
                            b'<fills count="1"><fill /></fills><borders count="1"><border/></borders>'
                            b'<cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="1"><xf/></cellXfs>'
                            b'</styleSheet>')
            destino.writestr(zipfile.ZipInfo(nome, DATA_FIXA), conteudo, zipfile.ZIP_DEFLATED)
    return saida.getvalue()


def xlsx_extrato(wb):
    ws = wb.active
    ws.title = "Extrato"
    ws.append(["Data", "Histórico", "Valor"])
    for linha in [
        (dt.date(2026, 9, 1), "SALDO ANTERIOR", 1000.00),
        (dt.date(2026, 9, 5), "TARIFA BANCARIA FICTICIA", -45.00),
        (dt.date(2026, 9, 10), "RECEBIMENTO CLIENTE FICTICIO", 2500.50),
        (dt.date(2026, 9, 15), "PAGAMENTO FORNECEDOR FICTICIO", -1500.25),
    ]:
        ws.append(list(linha))
    resumo = wb.create_sheet("Resumo")
    resumo.append(["Saldo final", 1955.25])


def xlsx_formula(wb):
    ws = wb.active
    ws.title = "Notas"
    ws.append(["Item", "Valor"])
    for v in (100, 200, 300):
        ws.append([f"ITEM {v}", v])
    ws.append(["Total", "=SUM(B2:B4)"])     # o openpyxl grava a fórmula SEM valor calculado


def xlsx_mescladas(wb):
    ws = wb.active
    ws.title = "Relatorio"
    ws["A1"] = "RELATORIO FICTICIO MESCLADO"
    ws.merge_cells("A1:C1")
    ws.append(["Conta", "Debito", "Credito"])
    ws.append(["CAIXA FICTICIO", 10, 0])


def xlsx_aba_oculta(wb):
    ws = wb.active
    ws.title = "Visivel"
    ws.append(["Dado visivel", 1])
    oculta = wb.create_sheet("Oculta")
    oculta.append(["DADO NA ABA OCULTA", 42])
    oculta.sheet_state = "hidden"


def xlsx_muitas_linhas(wb):
    ws = wb.active
    ws.title = "Lancamentos"
    ws.append(["Linha", "Valor"])
    for i in range(1, 2101):
        ws.append([i, i * 1.5])


def xlsx_protegida(wb):
    ws = wb.active
    ws.title = "Protegida"
    ws.append(["Dado em aba protegida", 7])
    ws.protection.sheet = True


def xlsx_simples(rotulo):
    def preparar(wb):
        ws = wb.active
        ws.title = "Dados"
        ws.append([rotulo, 1])
    return preparar


def xlsx_bomba() -> bytes:
    """ZIP com taxa de compressão desproporcional (cerca de 20 MB de espaços). Nada é executável."""
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("[Content_Types].xml", DATA_FIXA), "<Types/>")
        z.writestr(zipfile.ZipInfo("xl/worksheets/sheet1.xml", DATA_FIXA), b" " * (20 * 1024 * 1024), zipfile.ZIP_DEFLATED)
    return saida.getvalue()


# ============================================================ XML NF-e / NFC-e / eventos
NS = "http://www.portalfiscal.inf.br/nfe"


def item_xml(n: int, cod: str, desc: str, qtd: str, unit: str, total: str, vicms: str, pis_cofins=None) -> str:
    pc = ""
    if pis_cofins:
        vpis, vcof = pis_cofins
        pc = (f"<PIS><PISAliq><CST>01</CST><vBC>{total}</vBC><pPIS>1.65</pPIS><vPIS>{vpis}</vPIS></PISAliq></PIS>"
              f"<COFINS><COFINSAliq><CST>01</CST><vBC>{total}</vBC><pCOFINS>7.60</pCOFINS><vCOFINS>{vcof}</vCOFINS></COFINSAliq></COFINS>")
    return (f'<det nItem="{n}"><prod><cProd>{cod}</cProd><cEAN>SEM GTIN</cEAN><xProd>{desc}</xProd><NCM>00000000</NCM>'
            f"<CFOP>5102</CFOP><uCom>UN</uCom><qCom>{qtd}</qCom><vUnCom>{unit}</vUnCom><vProd>{total}</vProd></prod>"
            f"<imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST><modBC>3</modBC><vBC>{total}</vBC><pICMS>18.00</pICMS>"
            f"<vICMS>{vicms}</vICMS></ICMS00></ICMS>{pc}</imposto></det>")


def nfe_xml(chave: str, mod: str, numero: int, itens: str, totais: str, dest_cnpj=CNPJ_TESTE,
            dest_nome="EMPRESA TESTE FICTICIA LTDA", com_dest=True, com_total=True, cdv=None,
            emit_nome="FORNECEDOR FICTICIO LTDA") -> bytes:
    dest = f"<dest><CNPJ>{dest_cnpj}</CNPJ><xNome>{dest_nome}</xNome><indIEDest>9</indIEDest></dest>" if com_dest else ""
    total = f"<total><ICMSTot>{totais}</ICMSTot></total>" if com_total else ""
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<nfeProc xmlns="{NS}" versao="4.00"><NFe xmlns="{NS}">'
           f'<infNFe Id="NFe{chave}" versao="4.00"><ide><cUF>35</cUF><cNF>12345678</cNF><natOp>VENDA DE MERCADORIA FICTICIA</natOp>'
           f"<mod>{mod}</mod><serie>1</serie><nNF>{numero}</nNF><dhEmi>2026-09-10T10:00:00-03:00</dhEmi><tpNF>1</tpNF>"
           f"<tpEmis>1</tpEmis><cDV>{cdv if cdv is not None else chave[-1]}</cDV><tpAmb>2</tpAmb></ide>"
           f"<emit><CNPJ>{CNPJ_EMITENTE}</CNPJ><xNome>{emit_nome}</xNome><IE>ISENTO</IE><CRT>3</CRT></emit>"
           f"{dest}{itens}{total}<infAdic><infCpl>DOCUMENTO FICTICIO PARA TESTE</infCpl></infAdic></infNFe></NFe>"
           f'<protNFe versao="4.00"><infProt><tpAmb>2</tpAmb><chNFe>{chave}</chNFe><dhRecbto>2026-09-10T10:00:05-03:00</dhRecbto>'
           f"<nProt>135260000000001</nProt><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe></nfeProc>\n")
    return xml.encode("utf-8")


def totais_xml(vprod: str, vicms: str, vpis="0.00", vcofins="0.00") -> str:
    return (f"<vBC>{vprod}</vBC><vICMS>{vicms}</vICMS><vICMSDeson>0.00</vICMSDeson><vFCP>0.00</vFCP><vBCST>0.00</vBCST>"
            f"<vST>0.00</vST><vProd>{vprod}</vProd><vFrete>0.00</vFrete><vSeg>0.00</vSeg><vDesc>0.00</vDesc>"
            f"<vII>0.00</vII><vIPI>0.00</vIPI><vPIS>{vpis}</vPIS><vCOFINS>{vcofins}</vCOFINS><vOutro>0.00</vOutro><vNF>{vprod}</vNF>")


ITENS_3 = (item_xml(1, "A001", "PRODUTO FICTICIO A", "2.0000", "100.00", "200.00", "36.00", ("3.30", "15.20"))
           + item_xml(2, "B002", "PRODUTO FICTICIO B", "1.0000", "50.00", "50.00", "9.00")
           + item_xml(3, "C003", "PRODUTO FICTICIO C", "5.0000", "10.00", "50.00", "9.00"))
TOTAIS_3 = totais_xml("300.00", "54.00", "3.30", "15.20")


def evento_cancelamento(chave: str) -> bytes:
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<procEventoNFe xmlns="{NS}" versao="1.00"><evento versao="1.00">'
            f'<infEvento Id="ID110111{chave}01"><cOrgao>35</cOrgao><tpAmb>2</tpAmb><CNPJ>{CNPJ_EMITENTE}</CNPJ>'
            f"<chNFe>{chave}</chNFe><dhEvento>2026-09-11T09:00:00-03:00</dhEvento><tpEvento>110111</tpEvento>"
            f'<nSeqEvento>1</nSeqEvento><verEvento>1.00</verEvento><detEvento versao="1.00"><descEvento>Cancelamento</descEvento>'
            f"<nProt>135260000000001</nProt><xJust>CANCELAMENTO FICTICIO PARA TESTE</xJust></detEvento></infEvento></evento>"
            f'<retEvento versao="1.00"><infEvento><tpAmb>2</tpAmb><cStat>135</cStat><xMotivo>Evento registrado</xMotivo>'
            f"<chNFe>{chave}</chNFe><tpEvento>110111</tpEvento><nProtEvento>135260000000002</nProtEvento></infEvento></retEvento>"
            f"</procEventoNFe>\n").encode("utf-8")


# ============================================================ geração
def gerar() -> None:
    from pypdf import PdfReader, PdfWriter

    for pasta in (DESTINO_TESTE, DESTINO_ISOLAMENTO):
        if pasta.exists():
            shutil.rmtree(pasta)
    pdf_d, scan_d, xlsx_d, xml_d = (DESTINO_TESTE / n for n in ("PDF", "SCAN", "XLSX", "XML"))
    for p in (pdf_d, scan_d, xlsx_d, xml_d, DESTINO_ISOLAMENTO):
        p.mkdir(parents=True)

    # ---------------- PDF digital
    nf_servico = montar_pdf([{"linhas": [
        "DOCUMENTO FICTICIO PARA TESTE - NAO E DOCUMENTO REAL",
        "NOTA FISCAL DE SERVICO ELETRONICA FICTICIA N 000777",
        "Data de emissao: 12/09/2026",
        f"Prestador: PRESTADOR FICTICIO SERVICOS LTDA - CNPJ {CNPJ_EMITENTE}",
        f"Tomador: EMPRESA TESTE FICTICIA LTDA - CNPJ {CNPJ_TESTE}",
        "Descrição do serviço: Consultoria fictícia",
        "Valor total: R$ 1.250,00",
    ]}])
    gravar(pdf_d, "PDF-01_nf_servico.pdf", nf_servico)
    gravar(pdf_d, "PDF-02_extrato_12_paginas.pdf", montar_pdf([
        {"linhas": [f"EXTRATO FICTICIO - PAGINA {k} DE 12", f"Lancamento ficticio {k}: R$ {k * 10},00"]} for k in range(1, 13)]))
    gravar(pdf_d, "PDF-03a_pagina_em_branco.pdf", montar_pdf([{"linhas": []}]))
    gravar(pdf_d, "PDF-03b_sem_paginas.pdf", montar_pdf([]))
    escritor = PdfWriter(clone_from=PdfReader(io.BytesIO(nf_servico)))
    escritor.encrypt(user_password="fixture-t004", owner_password="fixture-t004-dono", algorithm="RC4-128")
    buf = io.BytesIO()
    escritor.write(buf)
    gravar(pdf_d, "PDF-04_protegido_senha.pdf", buf.getvalue())
    gravar(pdf_d, "PDF-05_corrompido.pdf", b"%PDF-1.4\n%fixture corrompida sem objetos nem xref\n" + bytes(range(256)) * 4)
    gravar(pdf_d, "PDF-06_excede_paginas.pdf", montar_pdf([{"linhas": [f"PAGINA FICTICIA {k}"]} for k in range(1, 52)]))
    gravar(pdf_d, "PDF-07_com_javascript.pdf", montar_pdf(
        [{"linhas": ["DOCUMENTO FICTICIO COM ACAO JAVASCRIPT INERTE", "Valor total: R$ 10,00"]}],
        extra_catalogo="/OpenAction << /S /JavaScript /JS (void 0) >> "))

    # ---------------- escaneados e imagens (valor visível SOMENTE na imagem)
    imagem = desenhar("TOTAL R$ 9.876,54")
    gravar(scan_d, "SCAN-01_somente_imagem.pdf", montar_pdf([{"imagem": imagem}]))
    gravar(scan_d, "SCAN-02_misto.pdf", montar_pdf([
        {"linhas": ["PAGINA 1 COM TEXTO FICTICIO", "Referencia ficticia: ABC-123"]},
        {"imagem": imagem}]))
    gravar(scan_d, "SCAN-03_recibo.png", montar_png(*imagem))
    gravar(scan_d, "SCAN-04_recibo.jpg", JPG_MINIMO)

    # ---------------- XLSX / XLSM
    extrato = montar_xlsx(xlsx_extrato)
    gravar(xlsx_d, "XLSX-01_extrato.xlsx", extrato)
    gravar(xlsx_d, "XLSX-02_formula_sem_valor.xlsx", montar_xlsx(xlsx_formula))
    gravar(xlsx_d, "XLSX-03_celulas_mescladas.xlsx", montar_xlsx(xlsx_mescladas))
    gravar(xlsx_d, "XLSX-04_aba_oculta.xlsx", montar_xlsx(xlsx_aba_oculta))
    gravar(xlsx_d, "XLSX-05_excede_linhas.xlsx", montar_xlsx(xlsx_muitas_linhas))
    gravar(xlsx_d, "XLSX-06a_corrompido.xlsx", extrato[: len(extrato) // 2])
    gravar(xlsx_d, "XLSX-06b_senha_abertura.xlsx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504)
    gravar(xlsx_d, "XLSX-07_com_macro.xlsm", montar_xlsx(xlsx_simples("Planilha com macro ficticia"),
                                                         {"xl/vbaProject.bin": b"FIXTURE T-004: SEM CODIGO EXECUTAVEL"}))
    gravar(xlsx_d, "XLSX-08_link_externo.xlsx", montar_xlsx(xlsx_simples("Planilha com vinculo externo ficticio"), {
        "xl/externalLinks/externalLink1.xml":
            b'<?xml version="1.0" encoding="UTF-8"?><externalLink xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'}))
    gravar(xlsx_d, "XLSX-09_zip_desproporcional.xlsx", xlsx_bomba())
    gravar(xlsx_d, "XLSX-10_aba_protegida.xlsx", montar_xlsx(xlsx_protegida))
    gravar(xlsx_d, "XLSX-11_estilo_invalido.xlsx", xlsx_estilo_invalido(montar_xlsx(xlsx_extrato)))

    # ---------------- XML NF-e / NFC-e
    ch01 = chave_nfe("55", 123)
    gravar(xml_d, "XML-01_nfe_3_itens.xml", nfe_xml(ch01, "55", 123, ITENS_3, TOTAIS_3))
    ch01b = chave_nfe("65", 10)
    gravar(xml_d, "XML-01b_nfce_sem_destinatario.xml", nfe_xml(
        ch01b, "65", 10, item_xml(1, "D004", "PRODUTO FICTICIO D", "1.0000", "25.00", "25.00", "4.50"),
        totais_xml("25.00", "4.50"), com_dest=False))
    ch02 = chave_nfe("55", 124)
    itens_80 = "".join(item_xml(i, f"P{i:03d}", f"PRODUTO FICTICIO {i:03d}", "1.0000", "10.00", "10.00", "1.80") for i in range(1, 81))
    gravar(xml_d, "XML-02_nfe_80_itens.xml", nfe_xml(ch02, "55", 124, itens_80, totais_xml("800.00", "144.00")))
    ch03 = ch01[:-1] + ("9" if ch01[-1] != "9" else "0")
    gravar(xml_d, "XML-03_chave_dv_invalido.xml", nfe_xml(ch03, "55", 123, ITENS_3, TOTAIS_3, cdv=ch01[-1]))
    ch04 = chave_nfe("55", 125)
    gravar(xml_d, "XML-04_sem_destinatario_e_totais.xml", nfe_xml(ch04, "55", 125, ITENS_3, TOTAIS_3, com_dest=False, com_total=False))
    gravar(xml_d, "XML-05_malformado.xml", nfe_xml(ch01, "55", 123, ITENS_3, TOTAIS_3)[:700])
    gravar(xml_d, "XML-06_doctype_entidade_externa.xml",
           f'<?xml version="1.0"?>\n<!DOCTYPE nfeProc [<!ENTITY ext SYSTEM "file:///recurso-inexistente-t004.txt">]>\n'
           f'<nfeProc xmlns="{NS}"><x>&ext;</x></nfeProc>\n'.encode())
    gravar(xml_d, "XML-07_expansao_entidades.xml",
           f'<?xml version="1.0"?>\n<!DOCTYPE nfeProc [<!ENTITY a "ficticio"><!ENTITY b "&a;&a;">]>\n'
           f'<nfeProc xmlns="{NS}"><x>&b;</x></nfeProc>\n'.encode())
    gravar(xml_d, "XML-08_evento_cancelamento.xml", evento_cancelamento(ch01))
    gravar(xml_d, "XML-09_nfse_outro_tipo.xml",
           b'<?xml version="1.0" encoding="UTF-8"?>\n<CompNfse xmlns="http://www.abrasf.org.br/nfse.xsd"><Nfse>'
           b"<InfNfse><Numero>1</Numero><Discriminacao>SERVICO FICTICIO</Discriminacao></InfNfse></Nfse></CompNfse>\n")

    # ---------------- EMPRESA-ISOLAMENTO (para os testes de isolamento futuros)
    gravar(DESTINO_ISOLAMENTO, "ISO-01_documento.pdf", montar_pdf([{"linhas": [
        "DOCUMENTO FICTICIO DA EMPRESA ISOLAMENTO", "Marcador: ISOLAMENTO-T004-PDF"]}]))
    gravar(DESTINO_ISOLAMENTO, "ISO-02_planilha.xlsx", montar_xlsx(xlsx_simples("ISOLAMENTO-T004-XLSX")))
    ch_iso = chave_nfe("55", 900)
    gravar(DESTINO_ISOLAMENTO, "ISO-03_nfe.xml", nfe_xml(
        ch_iso, "55", 900, item_xml(1, "I001", "PRODUTO ISOLAMENTO-T004-XML", "1.0000", "1.00", "1.00", "0.18"),
        totais_xml("1.00", "0.18"), dest_cnpj=CNPJ_ISOLAMENTO, dest_nome="EMPRESA ISOLAMENTO FICTICIA LTDA"))

    total = sum(1 for p in (DESTINO_TESTE, DESTINO_ISOLAMENTO) for f in p.rglob("*") if f.is_file())
    print(f"{total} fixtures geradas em CLIENTES/EMPRESA-TESTE/T004 e CLIENTES/EMPRESA-ISOLAMENTO/T004")


if __name__ == "__main__":
    if sys.flags.isolated == 0:
        print("aviso: execute com o Python do .venv e a opção -I", file=sys.stderr)
    gerar()
