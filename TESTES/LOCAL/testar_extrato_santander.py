"""Leitor de extrato PDF: somente texto fictício; não acessa documentos de clientes."""
import copy
import io
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'AGENTES/FINANCEIRO/ferramentas'))
import conferencia_financeira as f


def arquivo():
    return {'arquivo': 'extrato-ficticio.pdf', 'extensao': '.pdf', 'leitura': 'EXTRAIDO_PDF',
            'conteudo': {'paginas_total': 2, 'paginas': [
                {'pagina': 1, 'texto': 'Santander Empresas\nEMPRESA FICTICIA Agência: 1234 Conta: 11111-1\n'
                 'Períodos: 01/10/2026 a 31/10/2026 Data/Hora: 01/11/2026 as 10h00\n'
                 'Saldo disponível para uso: R$ 9.999,99\nData Histórico Documento Valor (R$) Saldo (R$)\n'
                 '20/10/2026 PIX RECEBIDO FICTICIO 12345678 50,00 950,00\n'
                 '10/10/2026 PAGAMENTO FICTICIO 0000000000 -20,00 900,00\n1/2'},
                {'pagina': 2, 'texto': '10/10/2026 PAGAMENTO FICTICIO 87654321 -80,00 920,00\n'
                 'Saldo de ContaMax 9.999,99\nSaldo\nPosição em: 01/11/2026\n2/2'}]}}


def pdf_ficticio():
    """PDF gerado somente para teste de upload/extrator, sem material real."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica'), NameObject('/Encoding'): NameObject('/WinAnsiEncoding')})
    for p in arquivo()['conteudo']['paginas']:
        page = writer.add_blank_page(width=900, height=700)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        linhas = p['texto'].replace('/10/2026', '/09/2026').replace('31/09/2026', '30/09/2026').splitlines()
        comandos = [b'BT /F1 10 Tf 30 660 Td 18 TL']
        for l in linhas:
            literal = l.encode('cp1252').replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')
            comandos.append(b'(' + literal + b') Tj T*')
        comandos.append(b'ET')
        stream = DecodedStreamObject(); stream.set_data(b'\n'.join(comandos))
        page[NameObject('/Contents')] = writer._add_object(stream)
    out = io.BytesIO(); writer.write(out)
    return out.getvalue()


class SantanderPDF(unittest.TestCase):
    def test_valores_datas_e_ordem_mesmo_dia(self):
        e = f.ler_santander_pdf(arquivo())[0]
        self.assertEqual((e['banco'], e['agencia'], e['conta']), ('033', '1234', '11111-1'))
        self.assertEqual([m['valor_assinado'] for m in e['movimentos']], list(map(Decimal, ['-80', '-20', '50'])))
        self.assertEqual(e['movimentos'][0]['identificadores'], {'DOCUMENTO': '87654321'})
        self.assertEqual(e['movimentos'][1]['identificadores'], {})
        self.assertIn('página 2', e['movimentos'][0]['origem'])

    def test_saldo_disponivel_nao_e_saldo_do_periodo(self):
        e = f.ler_santander_pdf(arquivo())[0]
        self.assertEqual(e['saldo_final'], Decimal('950'))
        self.assertIsNone(e['saldo_inicial']); self.assertIsNone(e['titular'])
        self.assertEqual(e['saldos_sucessivos'], 'CONSISTENTES')

    def test_outro_pdf_nao_e_extrato(self):
        a = arquivo(); a['conteudo']['paginas'][0]['texto'] = 'Recibo fictício'
        self.assertIsNone(f.ler_santander_pdf(a))

    def test_pagina_ausente_ocr_e_ordem(self):
        for mudar in (lambda a: a['conteudo']['paginas'].pop(),
                      lambda a: a['conteudo'].update(paginas_requer_ocr=[2]),
                      lambda a: a['conteudo']['paginas'].reverse()):
            a = arquivo(); mudar(a)
            with self.assertRaises(ValueError): f.ler_santander_pdf(a)

    def test_footer_invalido(self):
        a = arquivo(); a['conteudo']['paginas'][1]['texto'] = a['conteudo']['paginas'][1]['texto'].replace('2/2', '2/3')
        with self.assertRaises(ValueError): f.ler_santander_pdf(a)

    def test_linha_movimento_malformada_nao_e_descartada(self):
        a = arquivo(); a['conteudo']['paginas'][0]['texto'] = a['conteudo']['paginas'][0]['texto'].replace('50,00 950,00', '50.00 950,00')
        with self.assertRaises(ValueError): f.ler_santander_pdf(a)

    def test_divergencia_um_centavo_sem_tolerancia(self):
        a = arquivo(); a['conteudo']['paginas'][0]['texto'] = a['conteudo']['paginas'][0]['texto'].replace('950,00', '950,01')
        with self.assertRaisesRegex(ValueError, 'Saldos sucessivos'): f.ler_santander_pdf(a)

    def test_data_invalida(self):
        a = arquivo(); a['conteudo']['paginas'][0]['texto'] = a['conteudo']['paginas'][0]['texto'].replace('20/10/2026', '32/10/2026')
        with self.assertRaises(ValueError): f.ler_santander_pdf(a)

    def test_data_fora_periodo(self):
        a = arquivo(); a['conteudo']['paginas'][0]['texto'] = a['conteudo']['paginas'][0]['texto'].replace('20/10/2026', '20/11/2026')
        with self.assertRaises(ValueError): f.ler_santander_pdf(a)

    def conferencia(self, a=None, conta='033-1234-111111', competencia='2026-10'):
        cad = {'cnpjs': ['11222333000181'], 'contas': {conta: {'situacao': 'ATIVA'}}, 'cnpjs_outras_empresas': {}}
        with patch.object(f, 'cadastro', return_value=cad):
            c = f.Conferencia('EMPRESA-FICTICIA', competencia, 'SOL-2099-999999')
        c.carregar([copy.deepcopy(a or arquivo())]); c.preparar_movimentos()
        return c

    def test_chega_financeiro_sem_inventar_natureza(self):
        c = self.conferencia()
        self.assertEqual(c.triagem(), [])
        self.assertEqual(len(c.movimentos), 3); self.assertEqual(c.documentos, [])
        self.assertEqual(c.verificacoes[0]['situacao'], 'SEM_VERIFICACAO_ARITMETICA')
        self.assertTrue(any(p['tipo'] == 'SALDO_INICIAL_AUSENTE' for p in c.pendencias))

    def test_conta_ou_competencia_divergente_bloqueia(self):
        self.assertTrue(self.conferencia(conta='001-1234-111111').triagem())
        self.assertTrue(self.conferencia(competencia='2026-11').triagem())

    def test_extrato_ruim_nao_tem_aproveitamento_parcial(self):
        a = arquivo(); a['conteudo']['paginas'][1]['texto'] += '\n12/10/2026 ILEGIVEL'
        c = self.conferencia(a)
        self.assertEqual(c.movimentos, []); self.assertTrue(c.triagem())
        self.assertTrue(any(p['tipo'] == 'EXTRATO_PDF_NAO_UTILIZADO' for p in c.pendencias))


if __name__ == '__main__': unittest.main()
