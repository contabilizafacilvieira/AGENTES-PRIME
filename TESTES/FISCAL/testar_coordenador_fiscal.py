"""Transições fiscais, recusa e preservação; registro inteiramente fictício e temporário."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ/'COORDENADOR-GERAL/ferramentas'))
import coordenador as c


class RegistroFiscal(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='prime-coord-fiscal-');self.base=Path(self.tmp.name)
        self.reg=self.base/'solicitacoes.json';self.ret=self.base/'resultado.json';self.sol='SOL-2026-999999'
        # plano de etapas do Coordenador (áreas → Contabilidade → Conciliação)
        self.s={'estado':'FISCAL_EM_ANDAMENTO','empresa':'FICTICIA','competencia':'2026-10','eventos':[],
                'plano_etapas':c.novo_plano(['FISCAL','CONTABILIDADE_FISCAL']),'tarefas_areas':{'FISCAL':{'area':'FISCAL','documentos':[]}}}
        self.r={'contrato':'FISCAL_LOCAL_V1','agente':'FISCAL','modo':'SIMULACAO','empresa':'FICTICIA','competencia':'2026-10',
                'sol':self.sol,'resumo':{'documentos':1,'pendencias':0},'pendencias':[]}

    def tearDown(self):self.tmp.cleanup()
    def escrever(self):
        self.reg.write_text(json.dumps({'solicitacoes':{self.sol:self.s}}),encoding='utf-8')
        self.ret.write_text(json.dumps(self.r),encoding='utf-8')
    def registrar(self,contabilidade=False):
        self.escrever()
        with patch.object(c,'REGISTRO',self.reg),contextlib.redirect_stdout(io.StringIO()):
            codigo=c.registrar_fiscal(self.sol,str(self.ret),contabilidade)
        return codigo,json.loads(self.reg.read_text(encoding='utf-8'))['solicitacoes'][self.sol]

    def test_entrega_fiscal_sem_extrato_segue_contabilidade(self):
        codigo,s=self.registrar()
        self.assertEqual(codigo,0);self.assertEqual(s['estado'],'CONTABILIDADE_FISCAL_EM_ANDAMENTO')
        self.assertEqual(s['tarefas_areas']['FISCAL']['estado'],'ENTREGUE')

    def test_contabilidade_vem_depois_de_todas_as_areas(self):
        # Financeiro e DP já analisaram; depois do Fiscal, a Contabilidade/Bancos é a próxima etapa do plano
        self.s['plano_etapas']=c.novo_plano(['FINANCEIRO','DP','FISCAL','BANCOS','CONTABILIDADE_DP','CONTABILIDADE_FISCAL','CONCILIACAO'])
        for e in self.s['plano_etapas']:
            if e['etapa'] in ('FINANCEIRO','DP'): e['situacao']='CONCLUIDA'
        codigo,s=self.registrar()
        self.assertEqual(s['estado'],'BANCOS_EM_ANDAMENTO')
        self.assertEqual({e['etapa']:e['situacao'] for e in s['plano_etapas']}['FISCAL'],'CONCLUIDA')

    def test_outra_sol_ou_empresa_nao_grava(self):
        for campo,valor in [('sol','SOL-2026-999998'),('empresa','OUTRA'),('competencia','2026-09'),('modo','PRODUCAO')]:
            old=dict(self.r);self.r[campo]=valor
            codigo,s=self.registrar();self.assertNotEqual(codigo,0);self.assertNotIn('fiscal',s)
            self.r=old

    def test_contabilidade_entrega_sem_aprovar_escrituracao(self):
        self.s['estado']='CONTABILIDADE_FISCAL_EM_ANDAMENTO'
        self.r.update(contrato='CONTABILIDADE_FISCAL_V1',agente='CONTABILIDADE/FISCAL',resumo={'propostos':1,'incompletos':0},
                      lancamentos=[{'aprovado':False,'escriturado':False}])
        self.s['plano_etapas'][0]['situacao']='CONCLUIDA'
        codigo,s=self.registrar(True)
        self.assertEqual(codigo,0);self.assertEqual(s['estado'],'AGUARDANDO_SUPERVISOR')
        self.assertEqual([e['situacao'] for e in s['plano_etapas']],['CONCLUIDA','CONCLUIDA'])
        # com Conciliação no plano, a entrega da Contabilidade segue para ela (nada aprovado nem escriturado)
        self.s['plano_etapas']=c.novo_plano(['FISCAL','CONTABILIDADE_FISCAL','CONCILIACAO']);self.s['plano_etapas'][0]['situacao']='CONCLUIDA'
        codigo,s=self.registrar(True)
        self.assertEqual(s['estado'],'CONCILIACAO_EM_ANDAMENTO');self.assertEqual(s['tarefas_areas']['CONCILIACAO']['estado'],'EM_ANDAMENTO')

    def test_falsa_escrituracao_recusada(self):
        self.s['estado']='CONTABILIDADE_FISCAL_EM_ANDAMENTO'
        self.r.update(contrato='CONTABILIDADE_FISCAL_V1',agente='CONTABILIDADE/FISCAL',lancamentos=[{'escriturado':True}])
        codigo,s=self.registrar(True)
        self.assertNotEqual(codigo,0);self.assertNotIn('contabilfiscal',s)

    def test_falha_preservada_sem_repeticao(self):
        self.escrever()
        with patch.object(c,'REGISTRO',self.reg),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.registrar_falha_etapa(self.sol,'FISCAL','Falha fictícia'),0)
            self.assertNotEqual(c.registrar_fiscal(self.sol,str(self.ret)),0)
        s=json.loads(self.reg.read_text(encoding='utf-8'))['solicitacoes'][self.sol]
        self.assertEqual(s['estado'],'AGUARDANDO_SUPERVISOR');self.assertEqual(s['tarefas_areas']['FISCAL']['estado'],'FALHOU')
        self.assertEqual(s['tarefas_areas']['CONTABILIDADE_FISCAL']['estado'],'BLOQUEADO_POR_DEPENDENCIA')


if __name__=='__main__':unittest.main()
