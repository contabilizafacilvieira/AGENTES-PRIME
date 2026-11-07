"""Fixtures FICTÍCIAS do reconhecimento automático da VGROW ("Documentos.pdf": extrato da DUIMP e DANFEs).

Imitam o layout real (conhecido por leitura única autorizada em 31/10/2026) sem nenhum dado real: valores, números,
chaves e nomes são fictícios. Duas formas: páginas só com IMAGEM (texto desenhado; força o OCR, como a DUIMP real com
fontes Type3) e páginas com camada de TEXTO (caminho sem OCR).
"""

import io
import sys
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "T004"))
import gerar_fixtures as gf  # noqa: E402

LARGURA, ALTURA = 1240, 1754      # A4 a 150 dpi


def fonte(tamanho=22):
    for nome in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default(size=tamanho)


def pagina_imagem(itens):
    """itens: [(x, y, texto)] → bytes de imagem cinza (sem camada de texto)."""
    img = Image.new("L", (LARGURA, ALTURA), 255)
    d = ImageDraw.Draw(img)
    f = fonte()
    for x, y, texto in itens:
        d.text((x, y), texto, fill=0, font=f)
    return img.tobytes()


def pdf_de_imagens(paginas) -> bytes:
    """PDF com uma imagem ocupando a página inteira em cada página (sem texto)."""
    objs = []

    def add(b):
        objs.append(b)
        return len(objs)

    catalogo, raiz = add(None), add(None)
    filhos = []
    for px in paginas:
        dados = zlib.compress(px, 9)
        img = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray /BitsPerComponent 8 "
                  b"/Filter /FlateDecode /Length %d >>\nstream\n" % (LARGURA, ALTURA, len(dados)) + dados + b"\nendstream")
        conteudo = b"q 595 0 0 842 0 0 cm /Im1 Do Q"
        cont = add(b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream")
        filhos.append(add(f"<< /Type /Page /Parent {raiz} 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im1 {img} 0 R >> >> "
                          f"/Contents {cont} 0 R >>".encode()))
    objs[catalogo - 1] = f"<< /Type /Catalog /Pages {raiz} 0 R >>".encode()
    objs[raiz - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in filhos)}] /Count {len(filhos)} >>".encode()
    saida = io.BytesIO()
    saida.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posicoes = []
    for i, o in enumerate(objs, 1):
        posicoes.append(saida.tell())
        saida.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = saida.tell()
    saida.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for p in posicoes:
        saida.write(f"{p:010d} 00000 n \n".encode())
    saida.write(f"trailer\n<< /Size {len(objs) + 1} /Root {catalogo} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return saida.getvalue()


def linhas_duimp(ref="OCCT91001/26", fob="20.000,00", frete="3.000,00", fatura="TEST/INV/000001", chegada="15/09/2026", fob_extra=None):
    linhas = ["Extrato da DUIMP 26BR0000000000-0 / Versao 0001 (FICTICIO)", "RESUMO DE VALORES TOTAIS DO PROCESSO",
              "REAIS (R$)        DOLARES AMERICANOS (US$)", f"VALOR FOB.......... {fob} ..... 4.000,00 ..... 4.000,00",
              f"VALOR FRETE........ {frete} ..... 600,00 ..... 600,00", "VALOR SEGURO....... 50,00 ..... 10,00",
              "ADQUIRENTE...: VGROW COMERCIO E REPRESENTACAO LTDA (FICTICIO)", f"REF.CAPITALTRADE...:{ref}",
              "REF. CLIENTE......:GG900000001", f"FATURA.............:{fatura}", f"DATA DA CHEGADA....:{chegada}", "INCOTERM...........: CFR"]
    if fob_extra:
        linhas.insert(5, f"VALOR FOB.......... {fob_extra}")
    return linhas


def duimp_imagem(**k):
    return pagina_imagem([(60, 60 + 46 * i, t) for i, t in enumerate(linhas_duimp(**k))])


def danfe_imagem(nf: int, icms: str, destinatario="VGROW COMERCIO E REPRESENTACAO LTDA (FICTICIO)"):
    chave = gf.chave_nfe("55", nf, "22222222000191")
    return pagina_imagem([
        (980, 40, "DANFE"), (60, 40, "CAPITAL TRADE IMPORTACAO FICTICIA LTDA"), (60, 90, f"NOTA FISCAL No {nf} SERIE 4"),
        (700, 140, "CHAVE DE ACESSO"), (700, 180, chave), (60, 260, "NATUREZA DA OPERACAO"), (60, 300, "VENDA FICTICIA"),
        (60, 360, "DESTINATARIO"), (60, 400, destinatario),
        (60, 500, "BASE DE CALCULO DO ICMS"), (420, 500, "VALOR DO ICMS"), (700, 500, "BASE DE CALC. ICMS S.T."),
        (300, 545, "0,00"), (590, 545, icms), (900, 545, "0,00"),
        (60, 620, "VALOR TOTAL DA NOTA"), (300, 665, "9.999,00")])


def duimp_texto(**k) -> bytes:
    return gf.montar_pdf([{"linhas": linhas_duimp(**k)}])


def gravar(pasta: Path) -> dict:
    """Cria os 'Documentos.pdf' fictícios e devolve o gabarito por processo."""
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "OCCT91001-26 - DOCUMENTOS.pdf").write_bytes(pdf_de_imagens([
        duimp_imagem(), danfe_imagem(1001, "400,00"), danfe_imagem(999, "0,00", destinatario="EXPORTADOR ESTRANGEIRO FICTICIO CO LTD"),
        danfe_imagem(1002, "200,00")]))
    (pasta / "OCCT91002-26 - DOCUMENTOS.pdf").write_bytes(duimp_texto(ref="OCCT91002/26", fob="1.234,56", frete="100,00", fatura="TEST/INV/000002"))
    (pasta / "OCCT91003-26 - DOCUMENTOS.pdf").write_bytes(pdf_de_imagens([duimp_imagem(ref="OCCT99999/26")]))
    (pasta / "OCCT91004-26 - DOCUMENTOS.pdf").write_bytes(pdf_de_imagens([duimp_imagem(ref="OCCT91004/26", fob_extra="21.000,00")]))
    (pasta / "OCCT91005-26 - DOCUMENTOS.pdf").write_bytes(b"%PDF-1.4\n%corrompido\n")
    return {"OCCT91001/26": {"fob": "20000.00", "frete": "3000.00", "chegada": "2026-09-15", "fatura": "TEST/INV/000001",
                             "nfs": ["1001", "1002"], "icms_nf": "600.00"}}
