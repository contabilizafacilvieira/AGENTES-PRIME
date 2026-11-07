"""Isolamento do método e vigência das regras; somente arquivos fictícios temporários."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ/'API-LOCAL'))
sys.path.insert(0, str(RAIZ/'AGENTES/CONTABILIDADE/BANCOS/ferramentas'))
import metodo_empresa as metodo
import lancamentos_bancarios as bancos
import documentos_local as docs
from empresas_local import Empresas


class Metodo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='prime-metodo-')
        self.root = Path(self.tmp.name)
        self.p = self.root/'PERFIL-FECHAMENTO.json'
        self.d = {'contrato':'METODO_EMPRESA_V1','empresa':'FICTICIA','cnpj':'11.222.333/0001-81','executa_regras':True}

    def tearDown(self): self.tmp.cleanup()
    def salvar(self, d=None): self.p.write_text(json.dumps(self.d if d is None else d),encoding='utf-8')

    def test_ausente_nao_treina_outro_cliente(self):
        self.assertIsNone(metodo.carregar(self.root,'FICTICIA', ['11222333000181']))

    def test_contexto_nao_executa_regras(self):
        self.salvar(); d=metodo.carregar(self.root,'FICTICIA',['11222333000181'])
        self.assertFalse(d['executa_regras']); self.assertEqual(d['arquivo_metodo'],'MANUAL-FECHAMENTO.md')

    def test_empresa_e_cnpj_segregados(self):
        self.salvar()
        for empresa,cnpjs in [('OUTRA',['11222333000181']),('FICTICIA',['04252011000110']),('FICTICIA',[])]:
            self.assertFalse(metodo.carregar(self.root,empresa,cnpjs)['disponivel'])

    def test_perfil_invalido_nao_derruba_cadastro(self):
        for d in ([],None,{}, {'contrato':'DESCONHECIDO'}):
            self.salvar(d) if d is not None else self.p.write_text('null')
            self.assertFalse(metodo.carregar(self.root,'FICTICIA',[])['disponivel'])
        self.p.write_text('{')
        self.assertFalse(metodo.carregar(self.root,'FICTICIA',[])['disponivel'])

    def test_limite_de_arquivo(self):
        self.p.write_text(' '*300001)
        self.assertFalse(metodo.carregar(self.root,'FICTICIA',[])['disponivel'])


class Vigencia(unittest.TestCase):
    def test_recusa_mes_invalido(self):
        for valor in ('2026-13','2026-00','2026-1','amanha'):
            self.assertIsNone(bancos.condicoes('competencia_desde='+valor))

    def test_aplica_somente_desde_inicio(self):
        regra={'condicoes':bancos.condicoes('competencia_desde=2026-10; direcao=CREDITO'),'tipo':'RECEITA'}
        e=bancos.Escrituracao.__new__(bancos.Escrituracao)
        for mes,esperado in [('2026-09',False),('2026-10',True),('2027-01',True)]:
            e.competencia=mes
            self.assertEqual(e.atende(regra,{'direcao':'CREDITO'},set(),set(),set()),esperado)

    def test_regra_realmente_orienta_proposta_sem_duplicar_ajuste_mensal(self):
        with tempfile.TemporaryDirectory(prefix='prime-vigencia-') as tmp:
            root=Path(tmp); (root/'CLIENTES').mkdir(); g=Empresas(root,root/'runtime')
            g.cadastrar({'id':'FICTICIA','nome':'CLIENTE FICTICIO','cnpj':'11.222.333/0001-81','regime':'TESTE'})
            plano=root/'CLIENTES/FICTICIA/PLANO-DE-CONTAS/PLANO-DE-CONTAS.md'
            plano.write_text('## Contas utilizadas\n| Código reduzido | Descrição | Grupo | Tipo |\n|---|---|---|---|\n| 5 | BANCO | ATIVO | ANALITICA |\n| 60 | RECEITA FINANCEIRA | RECEITA | ANALITICA |\n',encoding='utf-8')
            cadastro=root/'CLIENTES/FICTICIA/CADASTRO.md'
            cadastro.write_text('## Contas bancárias\n| Banco | Agência | Conta | Conta contábil |\n|---|---|---|---|\n| 001 | 1234 | 111111 | 5 |\n',encoding='utf-8')
            regras=root/'CLIENTES/FICTICIA/REGRAS-BANCOS.md'
            regras.write_text('## Regras\n| Regra | Versão | Condições | Tipo | Contrapartida | Exige suporte | Histórico | Origem | Situação | Aprovação |\n|---|---|---|---|---|---|---|---|---|---|\n| RB-001 | 1 | direcao=CREDITO; historico_contem=RENDIMENTO; competencia_desde=2026-10 | RECEITA | 60 | NAO | {descricao} EM {data} | TESTE | VALIDADA | CONFIRMADA; frase=VALIDADO REGRA FICTICIA RB-001; versao=1; por=Supervisor Contábil; em=2026-11-05T10:00:00-03:00 |\n',encoding='utf-8')
            m={'id':'MOV-TESTE','data':'2026-10-01','valor':'1.23','direcao':'CREDITO','conta':'001-1234-111111',
               'descricao':'RENDIMENTO FICTICIO','situacao':'SEM_SUPORTE','documentos':[],'relacao':[],'divergencias':[]}
            for mes,status in [('2026-09','INCOMPLETO'),('2026-10','PROPOSTO')]:
                with patch.object(bancos,'RAIZ',root):
                    e=bancos.Escrituracao('FICTICIA',mes,'SOL-2099-999999',{'documentos':[],'relacao':[],'movimentos':[dict(m,data=mes+'-01')]},{})
                    e.gerar()
                self.assertEqual(len(e.lancamentos),1)
                self.assertEqual(e.lancamentos[0]['status'],status)
                if status=='PROPOSTO': self.assertEqual(e.lancamentos[0]['credito']['codigo'],'60')


class TriagemFinanceira(unittest.TestCase):
    def test_novos_documentos_financeiros(self):
        for t in ('MONTHLY CONSOLIDATED POSITION\nCDB ITAUVEST','CONTRATO DE CAMBIO\nTaxa cambial'):
            a={'arquivo':'ficticio.txt','extensao':'.txt','leitura':'EXTRAIDO_TEXTO','conteudo':{'texto':t}}
            self.assertEqual(docs.encaminhamento(a)['area'],'FINANCEIRO')


if __name__ == '__main__': unittest.main()
