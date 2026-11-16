"""Relação de Contas do Domínio: somente fixture fictícia e cadastros temporários."""
import base64
import copy
import io
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'API-LOCAL'))
from empresas_local import Empresas
from plano_dominio import reconhecer
from python_calamine import CalamineWorkbook

FIXTURE = Path(__file__).parent / 'fixtures/plano-dominio-ficticio.xlsx'


class Dominio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='prime-plano-dominio-')
        self.raiz = Path(self.tmp.name)
        (self.raiz / 'CLIENTES').mkdir()
        self.g = Empresas(self.raiz, self.raiz / 'runtime')
        self.id = 'EMPRESA-FICTICIA'
        self.empresa = self.g.cadastrar({'id': self.id, 'nome': 'EMPRESA FICTICIA PARA TESTE',
                                        'cnpj': '99.999.999/0001-91', 'regime': 'TESTE'})
        with CalamineWorkbook.from_path(str(FIXTURE)) as w:
            self.rows = w.get_sheet_by_index(0).to_python()

    def tearDown(self):
        self.tmp.cleanup()

    def previa(self, dados=None, nome='plano.xls'):
        return self.g.previa(self.id, {'nome': nome, 'conteudo': base64.b64encode(dados or FIXTURE.read_bytes()).decode(), 'finalidade': 'plano'})

    def test_xls_previa_automatica_sem_cadastro(self):
        p = self.previa()
        self.assertEqual(p['total'], 3)
        self.assertEqual(p['linhas'][1], ['1', '1', 'GRUPO FICTICIO', '', 'SINTETICA'])
        self.assertEqual(p['linhas'][2][4], 'ANALITICA')
        self.assertEqual(len(p['origem']['linhas_origem']), 3)
        self.assertEqual(self.g.obter(self.id)['plano'], [])

    def test_xlsx_mesmo_layout(self):
        from openpyxl import Workbook
        w = Workbook()
        for r in self.rows:
            w.active.append(r)
        b = io.BytesIO();w.save(b);w.close()
        self.assertEqual(self.previa(b.getvalue(), 'plano.xlsx')['total'], 3)

    def test_cnpj_diferente_sem_gravacao(self):
        dados = copy.deepcopy(self.rows)
        linha_cnpj = next(r for r in dados if r[0] == 'CNPJ:')
        linha_cnpj[3] = '88.888.888/0001-91'
        with self.assertRaisesRegex(ValueError, 'CNPJ'):
            reconhecer(dados, self.empresa)
        self.assertFalse((self.g.runtime / 'previas').exists())

    def test_cnpj_repetido_diferente(self):
        dados = copy.deepcopy(self.rows)
        dados.insert(9, ['C.N.P.J.:', '', '', '88.888.888/0001-91'])
        with self.assertRaisesRegex(ValueError, 'CNPJ'):
            reconhecer(dados, self.empresa)

    def test_tipo_desconhecido_nao_descarta(self):
        dados = copy.deepcopy(self.rows)
        linha_conta = next(r for r in dados if r[0] == '1')
        linha_conta[4] = 'X'
        with self.assertRaisesRegex(ValueError, 'linha'):
            reconhecer(dados, self.empresa)

    def test_total_divergente(self):
        dados = copy.deepcopy(self.rows)
        linha_total = next(r for r in dados if r[0] == 'TOTAL DE ITENS LISTADOS:')
        linha_total[5] = 4
        with self.assertRaisesRegex(ValueError, 'total de itens'):
            reconhecer(dados, self.empresa)

    def test_cabecalhos_repetidos(self):
        dados = copy.deepcopy(self.rows)
        dados.insert(9, self.rows[3])
        linha_total = next(r for r in dados if r[0] == 'TOTAL DE ITENS LISTADOS:')
        linha_total[5] = 3
        self.assertEqual(len(reconhecer(dados, self.empresa)[0]), 4)

    def test_sem_titulo_nao_e_dominio(self):
        self.assertIsNone(reconhecer([['codigo', 'classificacao', 'descricao'], ['1', '1', 'X']], self.empresa))

    def test_classificacao_repetida_preserva_codigos_sem_inferir_grupo(self):
        p = self.previa()
        d = {'token': p['token'], 'mapa': p['mapa_sugerido']}
        r = self.g.plano(self.id, d)
        self.assertFalse(r['erros'])
        self.assertTrue(any('repetida' in a for a in r['avisos']))
        r = self.g.plano(self.id, dict(d, salvar=True, confirmado=True))
        self.assertEqual([c['codigo'] for c in r['plano']], ['1', '10', '11'])
        self.assertTrue(all(c['grupo'] == '' for c in r['plano']))
        self.assertEqual(r['plano'][2]['linha_origem'], p['origem']['linhas_origem'][2])
        self.assertFalse(r['piloto'])
        self.assertEqual(r['plano_origem']['origem']['formato'], 'DOMINIO_RELACAO_CONTAS')

    def test_nao_pode_omitir_primeira_conta(self):
        p = self.previa()
        with self.assertRaisesRegex(ValueError, 'preservar todas as contas'):
            self.g.plano(self.id, {'token': p['token'], 'mapa': p['mapa_sugerido'], 'cabecalho': 2})

    def test_codigo_duplicado_bloqueia(self):
        p = self.g.previa(self.id, {'nome': 't.csv', 'conteudo': base64.b64encode(b'codigo;classificacao;descricao\n1;1;A\n1;2;B').decode()})
        with self.assertRaisesRegex(ValueError, 'Plano não salvo'):
            self.g.plano(self.id, {'token': p['token'], 'mapa': {'codigo': 0, 'classificacao': 1, 'descricao': 2}, 'salvar': True, 'confirmado': True})

    def test_xls_invalido_recusado(self):
        with self.assertRaisesRegex(ValueError, 'XLS'):
            self.previa(b'nao e planilha')

    def test_csv_aceita_a_s_sem_alterar_grupos(self):
        csv='codigo;classificacao;descricao;grupo;tipo\n1;1;GRUPO FICTICIO;ATIVO;S\n10;1.1;CONTA FICTICIA;ATIVO;A\n'
        p=self.previa(csv.encode(),'plano.csv')
        r=self.g.plano(self.id,{'token':p['token']})
        self.assertFalse(r['erros']);self.assertFalse(r['avisos'])
        self.assertEqual([c['tipo'] for c in r['contas']],['SINTETICA','ANALITICA'])
        self.assertTrue(all(c['grupo']=='ATIVO' for c in r['contas']))
        self.assertEqual(self.g.obter(self.id)['plano'],[])
        salvo=self.g.plano(self.id,{'token':p['token'],'salvar':True,'confirmado':True})
        self.assertEqual([c['tipo'] for c in salvo['plano']],['SINTETICA','ANALITICA'])

    def test_csv_acentos_e_mensagem_especifica(self):
        csv='codigo;classificacao;descricao;grupo;tipo\n1;1;GRUPO FICTICIO;Patrimônio Líquido;Sintética\n10;1.1;CONTA FICTICIA;Patrimônio Líquido;Analítica\n'
        p=self.previa(csv.encode(),'plano.csv')
        r=self.g.plano(self.id,{'token':p['token']})
        self.assertFalse(r['erros']);self.assertEqual(r['contas'][0]['grupo'],'PATRIMONIO_LIQUIDO')
        p=self.previa(csv.replace('Analítica','X').encode(),'plano.csv')
        r=self.g.plano(self.id,{'token':p['token']})
        self.assertEqual(len(r['erros']),1);self.assertIn("Tipo 'X'",r['erros'][0])
        p=self.previa(csv.replace('Patrimônio Líquido','GRUPO_DESCONHECIDO').encode(),'plano.csv')
        r=self.g.plano(self.id,{'token':p['token']})
        self.assertTrue(all('Grupo' in e and 'Tipo' not in e for e in r['erros']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
