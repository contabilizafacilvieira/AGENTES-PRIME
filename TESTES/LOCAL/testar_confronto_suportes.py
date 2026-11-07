"""Leitura por rótulos e confronto direto: dados fictícios, sem arquivos de clientes."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'AGENTES/FINANCEIRO/ferramentas'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import conferencia_financeira as f
from testar_extrato_santander import arquivo

CAD = {'cnpjs': ['11222333000181'], 'contas': {'033-1234-111111': {'conta': '11111-1'}}, 'cnpjs_outras_empresas': {}}


def nota(texto=None):
    return {'arquivo': 'nota-ficticia.pdf', 'extensao': '.pdf', 'leitura': 'EXTRAIDO_PDF', 'sha256': 'a' * 64,
            'conteudo': {'paginas_total': 1, 'paginas': [{'pagina': 1, 'texto': texto or
                'NOTA FISCAL ELETRONICA DE SERVICOS\nData Emissão Hora Emissão\n01/10/2026 10:20\n'
                'Número da Nota\n0000017\nPrestador de Serviços FORNECEDOR FICTICIO LTDA\n'
                'CNPJ/CPF 04.252.011/0001-10\nTomador: EMPRESA FICTICIA 11.222.333/0001-81\n'
                'VALOR TOTAL DA NOTA\n80,00\nCódigo de barras: 123456789012345678901234567890\n'}]}}


class Confronto(unittest.TestCase):
    def test_rotulos_em_linhas_separadas(self):
        d = f.ler_documento_texto(nota(), CAD)
        self.assertEqual((d['valor'], d['data'], d['numero']), ('80.00', '2026-10-01', '0000017'))
        self.assertEqual(d['papel_data'], 'EMISSAO_DOCUMENTO')
        self.assertEqual(d['favorecido'], 'FORNECEDOR FICTICIO LTDA')
        self.assertEqual(d['favorecido_cnpj'], '04252011000110')

    def test_rotulo_nao_pula_campo_para_capturar_numero(self):
        self.assertEqual(f.rotulado(['VALOR TOTAL', 'OUTRO CAMPO', '100,00'], ['VALOR TOTAL'], f.RE_VALOR_BR), (None, None))

    def test_rotulos_repetidos_conflitantes(self):
        v, origem = f.rotulado(['VALOR TOTAL', '80,00', 'VALOR TOTAL', '90,00'], ['VALOR TOTAL'], f.RE_VALOR_BR)
        self.assertIsNone(v); self.assertIn('conflitantes', origem)

    def test_valor_nao_vem_do_nome_do_arquivo(self):
        a = nota('NOTA FISCAL\nDocumento sem valor'); a['arquivo'] = 'NF_80.00.pdf'
        self.assertIsNone(f.ler_documento_texto(a, CAD)['valor'])

    def test_valor_sem_separador_de_milhar_nao_perde_digito(self):
        d = f.ler_documento_texto(nota('NOTA FISCAL\nValor total: 1234,56'), CAD)
        self.assertEqual(d['valor'], '1234.56')

    def test_tabela_boleto_agrupada(self):
        a = nota('BOLETO\nBeneficiário FORNECEDOR FICTICIO LTDA - 04.252.011/0001-10\n'
                 'Número do documento CPF/CNPJ Vencimento Valor documento\n'
                 '90001 04.252.011/0001-10 05/10/2026 80,00\nPagador: EMPRESA FICTICIA 11.222.333/0001-81')
        d = f.ler_documento_texto(a, CAD)
        self.assertEqual((d['valor'], d['data'], d['numero']), ('80.00', '2026-10-05', '90001'))
        self.assertEqual(d['tipo'], 'BOLETO'); self.assertEqual(d['papel_data'], 'VENCIMENTO')

    def test_codigo_barras_nao_virou_cnpj(self):
        d = f.ler_documento_texto(nota('NOTA FISCAL\nValor total: 80,00\nCódigo de barras: 16290000010857'), CAD)
        self.assertEqual(d['cnpjs_terceiros'], []); self.assertIsNone(d['favorecido_cnpj'])

    def conferir(self, a=None, decisoes=None):
        with patch.object(f, 'cadastro', return_value=CAD): c = f.Conferencia('FICTICIA', '2026-10', 'SOL-2099-999999')
        c.carregar([arquivo(), a or nota()]); c.preparar_movimentos(); c.corresponder(decisoes or {})
        return c

    def test_nota_e_confrontada_sem_relacao_ou_comprovante(self):
        c = self.conferir()
        self.assertEqual(len(c.sugestoes), 1)
        self.assertEqual(c.sugestoes[0]['documento'], c.documentos[0]['id'])
        m = next(m for m in c.movimentos if m['valor'] == '80.00')
        self.assertEqual(m['suportes'], []); self.assertEqual(m['situacao'], 'SEM_SUPORTE')
        self.assertIn('EMISSAO_DOCUMENTO', c.sugestoes[0]['descricao'])
        self.assertIn('exige conferência', c.sugestoes[0]['descricao'])

    def test_confirmacao_individual_vincula_documento(self):
        c = self.conferir(); s = c.sugestoes[0]
        d = {s['movimento']: [{'tipo': 'VINCULAR', 'vinculos': [s['documento']], 'em': '2026-11-02', 'justificativa': 'Conferência fictícia'}]}
        novo = self.conferir(decisoes=d)
        m = next(m for m in novo.movimentos if m['id'] == s['movimento'])
        self.assertEqual(m['suportes'], [s['documento']]); self.assertEqual(m['situacao'], 'COM_SUPORTE')
        self.assertEqual(novo.sugestoes, [])

    def test_valor_diferente_nao_sugere(self):
        c = self.conferir(nota('NOTA FISCAL\nValor total: 81,00'))
        self.assertEqual(c.sugestoes, [])

    def test_entrada_sem_nome_ou_numero_no_extrato_tem_candidato(self):
        c = self.conferir(nota('NOTA FISCAL\nValor total: 50,00'))
        self.assertEqual(len(c.sugestoes), 1)
        s = c.sugestoes[0]; m = next(m for m in c.movimentos if m['id'] == s['movimento'])
        self.assertEqual(m['direcao'], 'CREDITO'); self.assertEqual(m['suportes'], [])
        self.assertIn('sem identificador comum', s['descricao']); self.assertIn('crédito', s['descricao'])

    def test_nf_emitida_pela_empresa_nao_vincula_saida_bancaria(self):
        a = nota(); a['leitura'] = 'EXTRAIDO_NFE'
        a['conteudo'] = {'emitente': {'CNPJ': '11222333000181'}, 'destinatario': {'CNPJ': '04252011000110'},
                         'totais': {'vNF': '80.00'}, 'ide': {'nNF': '17', 'dhEmi': '2026-10-01'}}
        self.assertEqual(self.conferir(a).sugestoes, [])

    def test_varios_movimentos_mesmo_valor_mantem_alternativas(self):
        with patch.object(f, 'cadastro', return_value=CAD): c = f.Conferencia('FICTICIA', '2026-10', 'SOL-2099-999999')
        c.carregar([arquivo(), nota()]); c.preparar_movimentos()
        import copy
        outro = copy.deepcopy(next(m for m in c.movimentos if m['valor'] == '80.00')); outro['id'] = 'MOV-FICTICIO-REPETIDO'
        c.movimentos.append(outro); c.corresponder({})
        self.assertEqual(len(c.sugestoes), 2)
        self.assertTrue(any(a['tipo'] == 'DOCUMENTO_MESMO_VALOR' for a in c.ambiguas))
        self.assertTrue(all(not m['suportes'] for m in c.movimentos))

    def test_documento_outra_empresa_isolado_nao_sugere(self):
        a = nota(); a['leitura'] = 'EXTRAIDO_NFE'
        a['conteudo'] = {'emitente': {'CNPJ': '04252011000110'}, 'destinatario': {'CNPJ': '99999999000191'},
                         'totais': {'vNF': '80.00'}, 'ide': {'nNF': '17', 'dhEmi': '2026-10-01'}}
        c = self.conferir(a)
        self.assertEqual(c.sugestoes, []); self.assertTrue(c.documentos[0].get('bloqueado'))


if __name__ == '__main__': unittest.main()
