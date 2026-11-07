"""Testes locais com empresas e documentos inteiramente fictícios e diretório temporário."""
import base64
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'API-LOCAL'))
sys.path.insert(0, str(RAIZ / 'AGENTES/FINANCEIRO/ferramentas'))
sys.path.insert(0, str(RAIZ / 'AGENTES/CONTABILIDADE/BANCOS/ferramentas'))
import empresas_local as mod
import documentos_local as docs
import conferencia_financeira as fin
import lancamentos_bancarios as ban


class Local(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='prime-local-')
        self.raiz = Path(self.tmp.name)
        (self.raiz / 'CLIENTES').mkdir()
        self.g = mod.Empresas(self.raiz, self.raiz / 'runtime')
        self.id = 'CLIENTE-TESTE'
        self.g.cadastrar({'id': self.id, 'nome': 'CLIENTE DE TESTE SEM DADOS REAIS', 'cnpj': '11.222.333/0001-81', 'regime': 'TESTE'})

    def tearDown(self):
        self.tmp.cleanup()

    def previa(self, texto, ident=None):
        return self.g.previa(ident or self.id, {'nome':'teste.csv', 'conteudo':base64.b64encode(texto.encode()).decode()})

    def plano(self):
        texto = 'codigo;classificacao;descricao;grupo;tipo\n5;1.1.1;BANCO;ATIVO;ANALITICA\n2101;2.1.1;FORNECEDOR;PASSIVO;ANALITICA\n4103;4.1.1;DESPESAS;DESPESA;ANALITICA\n'
        p = self.previa(texto)
        d = {'token':p['token'], 'mapa':dict(zip(('codigo','classificacao','descricao','grupo','tipo'),range(5)))}
        return self.g.plano(self.id, dict(d,salvar=True,confirmado=True))

    def bancos(self):
        self.plano()
        self.g.bancos(self.id, {'contas':[{'banco':'001','agencia':'1234','conta':'11111-1','titular':'11.222.333/0001-81','contabil':'5'}]})

    def test_cnpj_invalido(self):
        with self.assertRaises(ValueError): mod.cnpj('11111111111111')

    def test_cnpj_duplicado(self):
        with self.assertRaises(ValueError): self.g.cadastrar({'id':'OUTRA-EMPRESA','nome':'OUTRA','cnpj':'11.222.333/0001-81','regime':'TESTE'})

    def test_caminho_fora(self):
        for v in ('../FORA','_MODELO','A/B','C:\\teste'):
            with self.assertRaises(ValueError): self.g.base(v)

    def test_plano_previa_nao_salva(self):
        p=self.previa('codigo;classificacao;descricao;grupo;tipo\n5;1.1;BANCO;ATIVO;ANALITICA')
        r=self.g.plano(self.id,{'token':p['token'],'mapa':dict(zip(('codigo','classificacao','descricao','grupo','tipo'),range(5)))})
        self.assertFalse(r['erros']); self.assertEqual(self.g.obter(self.id)['plano'],[])

    def test_plano_duplicado(self):
        p=self.previa('c;cl;d;g;t\n5;1.1;A;ATIVO;ANALITICA\n5;1.2;B;ATIVO;ANALITICA')
        with self.assertRaises(ValueError): self.g.plano(self.id,{'token':p['token'],'mapa':dict(zip(('codigo','classificacao','descricao','grupo','tipo'),range(5))),'salvar':True,'confirmado':True})

    def test_plano_sem_grupo(self):
        p=self.previa('c;cl;d;g;t\n5;1.1;A;;ANALITICA')
        r=self.g.plano(self.id,{'token':p['token'],'mapa':dict(zip(('codigo','classificacao','descricao','grupo','tipo'),range(5)))})
        self.assertTrue(r['avisos']);self.assertFalse(r['erros'])

    def test_previa_isolada(self):
        self.g.cadastrar({'id':'OUTRO-CLIENTE','nome':'OUTRO TESTE','cnpj':'04.252.011/0001-10','regime':'TESTE'})
        p=self.previa('a;b\n1;2')
        with self.assertRaises(ValueError): self.g.tabela('OUTRO-CLIENTE',{'token':p['token'],'mapa':{'codigo':0}},('codigo',))

    def test_plano_parcial_e_definicao_explicita(self):
        p=self.previa('c;cl;d\n5;1.1;BANCO')
        r=self.g.plano(self.id,{'token':p['token'],'mapa':{'codigo':0,'classificacao':1,'descricao':2},'salvar':True,'confirmado':True})
        self.assertEqual(r['plano'][0]['grupo'],'')
        r=self.g.definir_conta(self.id,{'codigo':'5','grupo':'ATIVO','tipo':'ANALITICA','confirmado':True})
        self.assertEqual(r['plano'][0]['tipo'],'ANALITICA')

    def test_piloto_sem_cadastro(self):
        with self.assertRaises(ValueError): self.g.habilitar(self.id, {'frase':'CONFIRMO PILOTO '+self.id})

    def test_banco_outro_titular(self):
        self.plano()
        with self.assertRaises(ValueError):self.g.bancos(self.id,{'contas':[{'banco':'001','agencia':'1','conta':'2','titular':'04.252.011/0001-10','contabil':'5'}]})

    def conta_teste(self, **mudancas):
        return dict({'banco':'SANTANDER','agencia':'0451','conta':'987654321','titular':'11.222.333/0001-81','contabil':'5'},**mudancas)

    def test_nome_santander_reconhecido(self):
        self.plano();e=self.g.bancos(self.id,{'contas':[self.conta_teste()]})
        self.assertEqual(e['contas'][0]['banco'],'033')
        self.assertEqual(e['contas'][0]['agencia'],'0451')
        self.assertEqual(e['contas'][0]['conta'],'987654321')
        self.assertEqual(e['contas'][0]['banco_informado'],'SANTANDER')

    def test_banco_numerico_e_agencia_zero(self):
        self.plano();e=self.g.bancos(self.id,{'contas':[self.conta_teste(banco='33',agencia='0000')]})
        self.assertEqual(e['contas'][0]['banco'],'033');self.assertEqual(e['contas'][0]['agencia'],'0000')

    def test_duplicada_nome_e_codigo_mesmo_banco(self):
        self.plano()
        with self.assertRaisesRegex(ValueError,'duplicada nas linhas 1 e 2'):
            self.g.bancos(self.id,{'contas':[self.conta_teste(),self.conta_teste(banco='033',agencia='451')]})
        self.assertEqual(self.g.obter(self.id)['contas'],[])

    def test_erros_bancarios_especificos(self):
        self.plano()
        for conta,erro in ((self.conta_teste(banco='BANCO DESCONHECIDO'),'Banco'),(self.conta_teste(agencia='abc'),'Agência'),(self.conta_teste(conta='000000'),'número da conta')):
            with self.assertRaisesRegex(ValueError,erro):self.g.bancos(self.id,{'contas':[conta]})
        self.assertEqual(self.g.obter(self.id)['contas'],[])

    def test_habilitacao_aponta_apenas_o_que_falta(self):
        self.plano()
        with self.assertRaisesRegex(ValueError,'vínculo bancário na etapa 2') as erro:
            self.g.habilitar(self.id,{'frase':'CONFIRMO PILOTO '+self.id})
        self.assertNotIn('Importe',str(erro.exception));self.assertNotIn('Digite',str(erro.exception))

    def test_piloto_nao_libera_producao(self):
        self.bancos();e=self.g.habilitar(self.id,{'frase':'CONFIRMO PILOTO '+self.id})
        self.assertTrue(e['piloto']);self.assertFalse(e['producao_liberada']);self.assertNotIn('meses_restantes',e)

    def test_atualizacao_suspende_piloto_e_preserva_versao(self):
        self.bancos();self.g.habilitar(self.id,{'frase':'CONFIRMO PILOTO '+self.id});e=self.plano()
        self.assertFalse(e['piloto']);self.assertTrue(list((self.g.base(self.id)/'VERSOES').glob('*.json')))

    def test_arquivo_nao_suportado(self):
        with self.assertRaises(ValueError): self.g.previa(self.id,{'nome':'razao.pdf','conteudo':base64.b64encode(b'%PDF').decode()})

    def test_razao_desativado(self):
        with self.assertRaisesRegex(ValueError, 'razão foi removido'):
            self.g.previa(self.id, {'nome':'r.csv','finalidade':'razao'})

    def test_executor_local_sem_modelo(self):
        a={'arquivo':'RECEBIDOS/a.txt','sha256':'abc','leitura':'EXTRAIDO_TEXTO','conteudo':{'texto':'COMPROVANTE'},'extensao':'.txt'}
        ordem='- SOL: SOL-2026-999999\n- Empresa: CLIENTE-TESTE\n- Competência: 2026-09\n- Pasta dos documentos (relativa à pasta da empresa): RECEBIDOS\n'
        with patch.object(docs,'extrair',return_value={'arquivos':[a]}):
            r=docs.executar(ordem,self.raiz/'saida')
        self.assertEqual(r['executor'],'LOCAL_SEM_MODELO')
        self.assertEqual(json.loads((self.raiz/'saida/documentos-local.json').read_text(encoding='utf-8'))['contrato'],'DOCUMENTOS_LOCAL_V1')


if __name__=='__main__':
    unittest.main(verbosity=2)
