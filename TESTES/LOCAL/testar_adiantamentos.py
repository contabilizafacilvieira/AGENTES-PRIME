"""Pagamentos/recebimentos e configuração por empresa; somente dados fictícios temporários."""
import base64
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ/'API-LOCAL'))
sys.path.insert(0,str(RAIZ/'AGENTES/CONTABILIDADE/BANCOS/ferramentas'))
from empresas_local import Empresas
import lancamentos_bancarios as b


class Adiantamentos(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='prime-adiant-');self.root=Path(self.tmp.name)
        (self.root/'CLIENTES').mkdir();self.g=Empresas(self.root,self.root/'runtime');self.id='EMPRESA-FICTICIA'
        self.g.cadastrar({'id':self.id,'nome':'EMPRESA FICTICIA DE TESTE','cnpj':'11.222.333/0001-81','regime':'TESTE'})
        csv='codigo;classificacao;descricao;grupo;tipo\n5;1.1;BANCO;ATIVO;A\n4103;4.1;DESPESA;DESPESA;A\n11550;1.2;ADIANTAMENTO DIVERSO;ATIVO;A\n2200;2.1;ADIANTAMENTO CLIENTE;PASSIVO;A\n'
        p=self.g.previa(self.id,{'nome':'p.csv','conteudo':base64.b64encode(csv.encode()).decode()})
        self.g.plano(self.id,{'token':p['token'],'salvar':True,'confirmado':True})
        self.g.bancos(self.id,{'contas':[{'banco':'001','agencia':'1234','conta':'11111-1','titular':'11.222.333/0001-81','contabil':'5'}]})
        self.config={'habilitado':True,'fornecedores':'11550','clientes':'2200','confirmado':True}
        self.g.atualizar(self.id,{'sem_suporte':dict(self.config,confirmado_em='2026-11-01',versao=1)})
        self.mov={'id':'MOV-FICTICIO','data':'2026-10-05','valor':'100.00','direcao':'DEBITO','conta':'001-1234-111111',
                  'descricao':'PIX FAVORECIDO FICTICIO','situacao':'SEM_SUPORTE','documentos':[],'relacao':[],'divergencias':[]}

    def tearDown(self):self.tmp.cleanup()

    def gerar(self,m=None,decisoes=None):
        m=copy.deepcopy(m or self.mov)
        fin={'documentos':[],'relacao':[],'movimentos':[m]}
        with patch.object(b,'RAIZ',self.root):
            e=b.Escrituracao(self.id,'2026-10','SOL-2026-999999',fin,decisoes or {});e.gerar()
        return e

    def test_configuracao_antiga_nao_classifica_saida(self):
        l=self.gerar().lancamentos[0]
        self.assertEqual(l['status'],'INCOMPLETO');self.assertIsNone(l['debito'])
        self.assertNotEqual(l['tipo'],'ADIANTAMENTO_FORNECEDOR')

    def test_configuracao_antiga_nao_classifica_entrada(self):
        l=self.gerar(dict(self.mov,direcao='CREDITO')).lancamentos[0]
        self.assertEqual(l['status'],'INCOMPLETO');self.assertIsNone(l['credito'])
        self.assertNotEqual(l['tipo'],'ADIANTAMENTO_CLIENTE')

    def test_nao_permite_reativar_configuracao(self):
        with self.assertRaises(ValueError):self.g.parametros_bancarios(self.id,self.config)

    # Diretriz do Supervisor (03/11/2026): adiantamento manual só na conta indicada expressamente para a empresa (a configuração
    # antiga sem_suporte não vale como indicação) e a decisão não supre documento: o lançamento permanece INCOMPLETO.
    def test_adiantamento_sem_indicacao_expressa_fica_pendente(self):
        d={self.mov['id']:[{'tipo':'CONTRAPARTIDA','natureza_tipo':'ADIANTAMENTO_FORNECEDOR','conta':'11550','em':'2026-11-02','justificativa':'Decisao ficticia deste caso'}]}
        l=self.gerar(decisoes=d).lancamentos[0]
        self.assertEqual(l['status'],'INCOMPLETO');self.assertIsNone(l['debito'])
        self.assertIn('ADIANTAMENTO_NAO_INDICADO',l['faltas_codigos'])

    def test_decisao_especifica_na_conta_indicada_continua_incompleta(self):
        self.g.contas_adiantamento(self.id,{'natureza':'ADIANTAMENTO_FORNECEDOR','conta':'11550','confirmado':True,
                                            'justificativa':'Conta indicada pelo Supervisor (ficticio)'})
        d={self.mov['id']:[{'tipo':'CONTRAPARTIDA','natureza_tipo':'ADIANTAMENTO_FORNECEDOR','conta':'11550','em':'2026-11-02','justificativa':'Decisao ficticia deste caso'}]}
        l=self.gerar(decisoes=d).lancamentos[0]
        self.assertEqual(l['debito']['codigo'],'11550');self.assertEqual(l['status'],'INCOMPLETO')
        self.assertIn('SUPORTE',l['faltas_codigos']);self.assertFalse(l['acompanhamentos'])
        self.assertIn('somente este movimento',l['origem'])

    def test_indicacao_recusa_conta_de_grupo_errado_ou_banco(self):
        for natureza,conta in (('ADIANTAMENTO_FORNECEDOR','2200'),('ADIANTAMENTO_CLIENTE','11550'),('ADIANTAMENTO_FORNECEDOR','5')):
            with self.assertRaises(ValueError):
                self.g.contas_adiantamento(self.id,{'natureza':natureza,'conta':conta,'confirmado':True,'justificativa':'teste ficticio'})

    def test_regra_historica_de_adiantamento_nao_executa(self):
        with patch.object(b,'ler_regras',return_value=([{'tipo':'ADIANTAMENTO_FORNECEDOR','id':'RB-HISTORICA'}],[])):
            l=self.gerar().lancamentos[0]
        self.assertEqual(l['status'],'INCOMPLETO');self.assertIsNone(l['debito'])

    def test_documento_candidato_permanece_pendente(self):
        l=self.gerar(dict(self.mov,sugestoes=['Documento candidato ficticio'])).lancamentos[0]
        self.assertEqual(l['status'],'INCOMPLETO');self.assertIn('VINCULO_PENDENTE',l['faltas_codigos'])

    def test_documento_recebido_ilegivel_nao_e_ausencia_confirmada(self):
        l=self.gerar(dict(self.mov,documentacao_inconclusiva=['recebido-ilegivel.pdf'])).lancamentos[0]
        self.assertEqual(l['status'],'INCOMPLETO');self.assertIn('LEITURA_PENDENTE',l['faltas_codigos'])

    def test_decisao_de_despesa_nao_supre_documento(self):
        d={self.mov['id']:[{'tipo':'CONTRAPARTIDA','natureza_tipo':'DESPESA','conta':'4103','em':'2026-11-02','justificativa':'Decisao ficticia deste caso'}]}
        l=self.gerar(decisoes=d).lancamentos[0]
        self.assertEqual(l['status'],'INCOMPLETO');self.assertEqual(l['debito']['codigo'],'4103')
        self.assertTrue(any('documento' in p for p in l['pendencias']))


if __name__=='__main__':unittest.main(verbosity=2)
