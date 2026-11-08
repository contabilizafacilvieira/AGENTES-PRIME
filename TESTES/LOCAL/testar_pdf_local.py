"""PDFs gerados para testes: digitais, mistos, escaneados, girados e protegidos."""
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'API-LOCAL'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leitura_pdf_local as pdf
from testar_extrato_santander import pdf_ficticio
from pypdf import PdfReader, PdfWriter


def scan(girado=False):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new('RGB', (1800, 900), 'white'); d = ImageDraw.Draw(im)
    f = ImageFont.load_default(size=48)
    for n, linha in enumerate(('DOCUMENTO FICTICIO PARA TESTE', 'RECIBO DE PAGAMENTO', 'VALOR TOTAL: 123,45',
                               'DATA: 10/10/2026', 'EMPRESA FICTICIA DE TESTE')):
        d.text((90, 80 + n * 120), linha, fill='black', font=f)
    if girado: im = im.rotate(90, expand=True)
    out = io.BytesIO(); im.save(out, format='PDF', resolution=150)
    return out.getvalue()


class PDFs(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.TemporaryDirectory(prefix='prime-pdf-v2-'); self.base = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()

    def ler(self, dados):
        arq = self.base / 'ficticio.pdf'; arq.write_bytes(dados)
        return pdf.ler(arq)

    def test_digital_preserva_paginas_e_nao_chama_ocr(self):
        with patch.object(pdf, 'motor_ocr', side_effect=AssertionError('OCR desnecessário')):
            r = self.ler(pdf_ficticio())
        self.assertEqual(r['leitura'], 'EXTRAIDO_PDF')
        self.assertEqual(len(r['conteudo']['paginas']), 2)
        self.assertTrue(all(p['origem'] == 'PYPDF' for p in r['conteudo']['paginas']))

    def test_pdfium_recupera_falha_do_primeiro_leitor(self):
        with patch('pypdf.PdfReader', side_effect=ValueError('falha fictícia')):
            r = self.ler(pdf_ficticio())
        self.assertEqual(r['leitura'], 'EXTRAIDO_PDF')
        self.assertEqual(r['conteudo']['paginas'][0]['origem'], 'PDFIUM')

    def test_protegido_nao_tenta_ocr(self):
        w = PdfWriter(); w.add_blank_page(width=300, height=300); w.encrypt('senha-ficticia'); b = io.BytesIO(); w.write(b)
        with patch.object(pdf, 'motor_ocr', side_effect=AssertionError('Não abrir protegido')):
            self.assertEqual(self.ler(b.getvalue())['leitura'], 'PDF_PROTEGIDO')

    def protegido(self, senha_usuario):
        w = PdfWriter(); w.append(PdfReader(io.BytesIO(pdf_ficticio())))
        w.encrypt(user_password=senha_usuario, owner_password='dono-ficticio', algorithm='RC4-128')
        b = io.BytesIO(); w.write(b); return b.getvalue()

    def ler_sem_senha(self, dados):
        """Nenhuma senha pode ser tentada (nem vazia), nem OCR; o original não pode mudar."""
        from pypdf import _encryption
        arq = self.base / 'protegido.pdf'; arq.write_bytes(dados)
        with patch.object(PdfReader, 'decrypt', side_effect=AssertionError('decrypt chamado')), \
             patch.object(_encryption.Encryption, 'verify', side_effect=AssertionError('senha verificada')), \
             patch.object(pdf, 'motor_ocr', side_effect=AssertionError('OCR em protegido')):
            r = pdf.ler(arq)
        self.assertEqual(arq.read_bytes(), dados)
        return r

    def test_protegido_somente_proprietario_fica_pendente(self):
        r = self.ler_sem_senha(self.protegido(''))
        self.assertEqual(r['leitura'], 'PDF_PROTEGIDO'); self.assertEqual(r['conteudo'], {})
        self.assertNotIn('nem tentada', r['observacao'])
        self.assertIn('nenhuma senha', r['observacao'].lower())

    def test_protegido_com_senha_de_usuario_fica_pendente(self):
        r = self.ler_sem_senha(self.protegido('usuario-ficticio'))
        self.assertEqual(r['leitura'], 'PDF_PROTEGIDO'); self.assertEqual(r['conteudo'], {})

    def test_pdfium_nao_abre_protegido_apos_falha_do_pypdf(self):
        arq = self.base / 'protegido.pdf'; arq.write_bytes(self.protegido(''))
        with patch('pypdf.PdfReader', side_effect=ValueError('falha fictícia')), \
             patch.object(pdf, 'marcador_criptografia', return_value=False), \
             patch.object(pdf, 'motor_ocr', side_effect=AssertionError('OCR em protegido')):
            r = pdf.ler(arq)
        self.assertEqual(r['leitura'], 'PDF_PROTEGIDO'); self.assertEqual(r['conteudo'], {})

    def test_digital_sem_observacao_de_ocr(self):
        r = self.ler(pdf_ficticio())
        self.assertNotIn('OCR', r['observacao'])

    def test_ocr_mantem_observacao_de_conferencia(self):
        dados = {'texto': 'RECIBO VALOR 123,45', 'trechos': [], 'confianca_minima': .95,
                 'confianca_media': .95, 'rotacao_ocr': 0}
        with patch.object(pdf, 'reconhecer', return_value=dados): r = self.ler(scan())
        self.assertIn('OCR', r['observacao'])

    def test_pdf_em_branco_fica_documento_vazio(self):
        w = PdfWriter(); w.add_blank_page(width=300, height=300); b = io.BytesIO(); w.write(b)
        with patch.object(pdf, 'motor_ocr', side_effect=AssertionError('OCR em página branca')):
            r = self.ler(b.getvalue())
        self.assertEqual(r['leitura'], 'DOCUMENTO_VAZIO')
        self.assertNotIn('OCR', r['observacao'])

    def test_corrompido_tem_motivo(self):self.assertEqual(self.ler(b'%PDF-invalido')['leitura'], 'ARQUIVO_CORROMPIDO')

    def test_pagina_branca_nao_inventa_texto(self):
        w = PdfWriter(); w.add_blank_page(width=300, height=300); b = io.BytesIO(); w.write(b)
        r = self.ler(b.getvalue()); self.assertEqual(r['conteudo']['paginas'][0]['situacao'], 'VAZIA')

    def test_misto_le_por_pagina(self):
        w = PdfWriter(); w.append(PdfReader(io.BytesIO(pdf_ficticio()))); w.append(PdfReader(io.BytesIO(scan())))
        b = io.BytesIO(); w.write(b); r = self.ler(b.getvalue())
        self.assertEqual(r['conteudo']['paginas_total'], 3)
        self.assertEqual(r['conteudo']['paginas'][0]['origem'], 'PYPDF')
        p = r['conteudo']['paginas'][2]
        self.assertEqual(p['origem'], 'OCR_LOCAL'); self.assertIn('123,45', p['texto'])

    def test_scan_girado_recupera_valor_com_ocr_local(self):
        r = self.ler(scan(True)); p = r['conteudo']['paginas'][0]
        self.assertEqual(p['origem'], 'OCR_LOCAL'); self.assertIn('123,45', p['texto'])

    def test_confianca_baixa_preserva_texto_e_exige_conferencia(self):
        dados = {'texto': 'RECIBO VALOR 123,45', 'trechos': [], 'confianca_minima': .55,
                 'confianca_media': .80, 'rotacao_ocr': 0}
        with patch.object(pdf, 'reconhecer', return_value=dados): r = self.ler(scan())
        self.assertTrue(r['conteudo']['requer_conferencia_ocr'])
        self.assertEqual(r['conteudo']['paginas'][0]['situacao'], 'OCR_CONFERIR')
        self.assertIn('123,45', r['conteudo']['paginas'][0]['texto'])

    def test_limite_nao_declara_documento_completo(self):
        with patch.object(pdf, 'MAX_PAGINAS', 1): r = self.ler(pdf_ficticio())
        self.assertTrue(r['conteudo']['leitura_incompleta']); self.assertEqual(r['conteudo']['paginas_total'], 2)


if __name__ == '__main__': unittest.main(verbosity=2)
