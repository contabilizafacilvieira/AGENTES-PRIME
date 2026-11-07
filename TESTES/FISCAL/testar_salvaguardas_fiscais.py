"""Salvaguardas do Fiscal documental e da Contabilidade/Fiscal (auditoria de 03/11/2026).

Somente documentos fictícios em memória e diretórios temporários. As regras/plano da STATE-BANK são
apenas LIDOS e copiados para um diretório temporário (item 4); nenhum documento-fonte é lido e nada em
CLIENTES é alterado.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from testar_fiscal import NOTA, CNPJ, arquivo, analisar, f, c  # noqa: E402

APURACAO='DEMONSTRATIVO DE APURACAO\nCNPJ: 11.222.333/0001-81\nCOMPETENCIA: 10/2026\nTRIBUTO: {trib}\nVALOR APURADO: {valor}\n'


def nota(numero='123',extra=''):
    return NOTA.replace('NUMERO DA NOTA: 123','NUMERO DA NOTA: '+numero)+extra


def doc(r,nome):
    return next(d for d in r['documentos'] if d['arquivo'].endswith('/'+nome))


def texto_pend(d): return ' | '.join(d['pendencias'])



def governada(ref):
    """Referências do teste como APROVADAS pelo Supervisor (frase exata) + política de data aprovada, salvo as que o próprio
    teste declarou situação (casos de governança). Os testes de lógica fiscal pressupõem regras aplicáveis."""
    import copy
    r = copy.deepcopy(ref)
    def conf(chave):
        return {'frase': f"VALIDADO REGRA FISCAL {r.get('empresa')} {chave}", 'em': '2026-11-05T10:00:00-03:00', 'por': 'Supervisor Contábil'}
    for chave, x in (r.get('referencias') or {}).items():
        if isinstance(x, dict) and 'situacao' not in x:
            x.update(situacao='APROVADA', confirmacao=conf(chave), versao=1, **({'origem': x['fonte']} if x.get('fonte') else {}))
    r.setdefault('data_lancamento', {'politica': 'ULTIMO_DIA_COMPETENCIA', 'situacao': 'APROVADA', 'origem': 'teste unitário',
                                     'confirmacao': conf('DATA_LANCAMENTO')})
    return r

class Retencoes(unittest.TestCase):
    """Defeito 1: retenção não reconhecida nunca vale zero."""

    def d(self,extra): return analisar(arquivo(NOTA+extra))['documentos'][0]

    def test_rotulos_alternativos_univocos_reconhecidos(self):
        casos={'ISS RETIDO NA FONTE: 50,00\n':('ISS','50.00'),'IRRF (R$) 15,00\n':('IRRF','15.00'),
               'VALOR DO ISS RETIDO NA FONTE: 7,00\n':('ISS','7.00'),'RETENCAO DE ISS: 8,00\n':('ISS','8.00'),
               'IR RETIDO NA FONTE: 1,50\n':('IRRF','1.50'),'PIS/PASEP RETIDO: 6,50\n':('PIS','6.50'),
               'ISS RETIDO NA FONTE\n50,00\n':('ISS','50.00')}
        for extra,(trib,v) in casos.items():
            with self.subTest(extra=extra):
                d=self.d(extra)
                self.assertEqual(d['retencoes'].get(trib),v)
                self.assertFalse(d['elegivel_contabilidade'])

    def test_indicio_sem_valor_univoco_vira_pendencia(self):
        for extra in ('RETENCAO DE ISS\n','PIS/COFINS/CSLL RETIDO: 46,50\n','VALOR RETIDO: 30,00\n','ISS RETIDO: SIM\n',
                      'IMPOSTO RETIDO NA FONTE CONFORME LEGISLACAO\n','PIS (R$) 10,00\n','RETENCOES FEDERAIS: 12,00\n',
                      'ISS RETIDO: 10,00\nISS RETIDO NA FONTE: 20,00\n','CSRF RETIDA 4,65\n'):
            with self.subTest(extra=extra):
                d=self.d(extra)
                self.assertFalse(d['elegivel_contabilidade'],d['pendencias'])
                self.assertTrue(any('retenç' in p.lower() for p in d['pendencias']),d['pendencias'])
                self.assertNotIn('ISS',d['retencoes']) if 'ISS RETIDO: 10' in extra else None

    def test_combinado_nao_distribui_valor(self):
        d=self.d('PIS/COFINS/CSLL RETIDO: 46,50\n')
        self.assertEqual(d['retencoes'],{})

    def test_tabela_federal_com_valores_por_coluna(self):
        d=self.d('INSS (R$) IRRF (R$) CSLL (R$) COFINS (R$) PIS/PASEP (R$)\n- 15,00 - - -\n')
        self.assertEqual(d['retencoes'],{'IRRF':'15.00'}); self.assertFalse(d['elegivel_contabilidade'])

    def test_tabela_federal_sem_valores_e_ausencia_declarada_nao_bloqueiam(self):
        for extra in ('INSS (R$) IRRF (R$) CSLL (R$) COFINS (R$) PIS/PASEP (R$)\n- - - - -\n','ISS RETIDO: NAO\n',
                      'VALOR DO ISS RETIDO: 0,00\n'):
            with self.subTest(extra=extra):
                d=self.d(extra)
                self.assertTrue(d['elegivel_contabilidade'],d['pendencias'])

    def test_tabela_desalinhada_vira_pendencia(self):
        d=self.d('INSS (R$) IRRF (R$) CSLL (R$) COFINS (R$) PIS/PASEP (R$)\n15,00 -\n')
        self.assertFalse(d['elegivel_contabilidade']); self.assertEqual(d['retencoes'],{})

    def test_ausencia_declarada_conflitante_com_valor(self):
        d=self.d('ISS RETIDO: NAO\nVALOR DO ISS RETIDO: 10,00\n')
        self.assertFalse(d['elegivel_contabilidade']); self.assertNotIn('ISS',d['retencoes'])

    def test_valor_do_iss_devido_nao_e_retencao(self):
        d=self.d('VALOR DO ISS (R$) 61,73\n')
        self.assertTrue(d['elegivel_contabilidade'],d['pendencias']); self.assertEqual(d['retencoes'],{})


class Classificacao(unittest.TestCase):
    """Defeito 5: menção a DARF não transforma NFS-e em guia."""

    def test_nfse_com_mencao_a_darf_continua_nota(self):
        d=analisar(arquivo(NOTA+'OBSERVACAO: TRIBUTOS FEDERAIS RECOLHIDOS PELO PRESTADOR EM DARF PROPRIO\n'))['documentos'][0]
        self.assertEqual(d['tipo'],'NFSE'); self.assertTrue(d['elegivel_contabilidade'],d['pendencias'])

    def test_nota_com_campos_estruturais_de_guia_fica_ambigua(self):
        d=analisar(arquivo(NOTA+'DARF\nCODIGO DA RECEITA: 1708\nPERIODO DE APURACAO: 10/2026\n'))['documentos'][0]
        self.assertNotEqual(d['tipo'],'GUIA'); self.assertFalse(d['elegivel_contabilidade'])
        self.assertTrue(any('ambígu' in p for p in d['pendencias']),d['pendencias'])

    def test_guia_que_cita_nota_continua_guia(self):
        d=analisar(arquivo('DARF\nCNPJ: 11.222.333/0001-81\nPERIODO DE APURACAO: 30/09/2026\nVALOR TOTAL: 999,90\n'
                           'CODIGO DA RECEITA: 1708\nREFERENTE NOTA FISCAL 123\n'))['documentos'][0]
        self.assertEqual(d['tipo'],'GUIA'); self.assertFalse(d['elegivel_contabilidade'])


class Substituicoes(unittest.TestCase):
    """Defeito 3: substituída/substituta e apurações repetidas não duplicam receita nem provisão."""

    def test_substituta_com_substituida_no_lote_prevalece_sozinha(self):
        r=analisar(arquivo(nota('123'),'a.txt'),arquivo(nota('124','SUBSTITUI A NOTA 123\n'),'b.txt'))
        self.assertEqual(r['resumo']['aptos_proposta'],1)
        self.assertFalse(doc(r,'a.txt')['elegivel_contabilidade']); self.assertTrue(doc(r,'b.txt')['elegivel_contabilidade'])

    def test_substituta_sem_substituida_no_lote_pendente(self):
        r=analisar(arquivo(nota('124','SUBSTITUI A NOTA 123\n'),'b.txt'))
        self.assertEqual(r['resumo']['aptos_proposta'],0)

    def test_nota_substituta_sem_numero_pendente(self):
        r=analisar(arquivo(nota('123'),'a.txt'),arquivo(nota('124','NOTA SUBSTITUTA\n'),'b.txt'))
        self.assertEqual(r['resumo']['aptos_proposta'],0)

    def test_substituida_pela_nota_e_substituta_coerentes(self):
        r=analisar(arquivo(nota('123','SUBSTITUÍDA PELA NOTA 456\n'),'a.txt'),arquivo(nota('456','SUBSTITUI A NOTA 123\n'),'b.txt'))
        self.assertFalse(doc(r,'a.txt')['elegivel_contabilidade']); self.assertTrue(doc(r,'b.txt')['elegivel_contabilidade'])

    def test_substituida_sem_marca_explicita_mas_citada(self):
        r=analisar(arquivo(nota('123','SUBSTITUIDA PELA NOTA 456\n'),'a.txt'))
        self.assertEqual(r['resumo']['aptos_proposta'],0)

    def test_duas_substitutas_da_mesma_nota_bloqueiam_todas(self):
        r=analisar(arquivo(nota('123'),'a.txt'),arquivo(nota('124','SUBSTITUI A NOTA 123\n'),'b.txt'),
                   arquivo(nota('125','SUBSTITUI A NOTA 123\n'),'c.txt'))
        self.assertEqual(r['resumo']['aptos_proposta'],0)

    def test_referencias_incoerentes_bloqueiam(self):
        r=analisar(arquivo(nota('123','SUBSTITUIDA PELA NOTA 456\n'),'a.txt'),arquivo(nota('456','SUBSTITUI A NOTA 999\n'),'b.txt'))
        self.assertEqual(r['resumo']['aptos_proposta'],0)

    def test_apuracoes_repetidas_mesma_competencia_tributo_bloqueiam(self):
        for v2 in ('60,00','50,00'):
            with self.subTest(v2=v2):
                r=analisar(arquivo(APURACAO.format(trib='ISS',valor='50,00'),'a.txt'),
                           arquivo(APURACAO.format(trib='ISS',valor=v2)+'EMITIDO NOVAMENTE\n','b.txt'))
                self.assertEqual(r['resumo']['aptos_proposta'],0)

    def test_retificadora_unica_com_original_prevalece(self):
        r=analisar(arquivo(APURACAO.format(trib='ISS',valor='50,00'),'a.txt'),
                   arquivo(APURACAO.format(trib='ISS',valor='70,00')+'DECLARACAO RETIFICADORA\n','b.txt'))
        self.assertEqual(r['resumo']['aptos_proposta'],1); self.assertTrue(doc(r,'b.txt')['elegivel_contabilidade'])

    def test_retificadora_sem_original_ou_multiplas_bloqueiam(self):
        r=analisar(arquivo(APURACAO.format(trib='ISS',valor='70,00')+'RETIFICADORA\n','b.txt'))
        self.assertEqual(r['resumo']['aptos_proposta'],0)
        r=analisar(arquivo(APURACAO.format(trib='ISS',valor='50,00'),'a.txt'),
                   arquivo(APURACAO.format(trib='ISS',valor='70,00')+'RETIFICADORA\n','b.txt'),
                   arquivo(APURACAO.format(trib='ISS',valor='80,00')+'RETIFICADORA\n','c.txt'))
        self.assertEqual(r['resumo']['aptos_proposta'],0)

    def test_tributos_distintos_na_mesma_competencia_nao_conflitam(self):
        r=analisar(arquivo(APURACAO.format(trib='ISS',valor='50,00'),'a.txt'),arquivo(APURACAO.format(trib='PIS',valor='6,50'),'b.txt'))
        self.assertEqual(r['resumo']['aptos_proposta'],2)


class BaseContabil(unittest.TestCase):
    PLANO=('## Contas utilizadas\n| Código reduzido | Descrição | Grupo | Tipo |\n|---|---|---|---|\n'
           '| 11 | CLIENTES | ATIVO | ANALITICA |\n| 12 | CLIENTES NO EXTERIOR | ATIVO | ANALITICA |\n'
           '| 60 | SERVICOS | RECEITA | ANALITICA |\n| 61 | (-) ISS | RECEITA | ANALITICA |\n'
           '| 62 | DEDUCOES DA RECEITA ISS | RECEITA | ANALITICA |\n| 63 | (-) PIS | RECEITA | ANALITICA |\n'
           '| 26 | ISS A PAGAR | PASSIVO | ANALITICA |\n| 27 | PIS A RECOLHER | PASSIVO | ANALITICA |\n')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='prime-salv-fiscal-');self.root=Path(self.tmp.name)
        self.base=self.root/'CLIENTES/FICTICIA';(self.base/'PLANO-DE-CONTAS').mkdir(parents=True)
        (self.base/'empresa-local.json').write_text(json.dumps({'cnpj':CNPJ}))
        (self.base/'PLANO-DE-CONTAS/PLANO-DE-CONTAS.md').write_text(self.PLANO,encoding='utf-8')
        self.ref={'contrato':'REFERENCIAS_FISCAIS_V1','empresa':'FICTICIA','cnpj':CNPJ,'competencia_desde':'2026-10',
                  'referencias':{'RECEITA_SERVICOS':{'debito':'11','credito':'60','fonte':'Fechamento fictício confirmado'},
                                 'ISS':{'debito':'61','credito':'26','fonte':'Plano e fechamento fictícios'}}}

    def tearDown(self): self.tmp.cleanup()
    def salvar(self): (self.base/'REGRAS-FISCAIS.json').write_text(json.dumps(governada(self.ref) if getattr(self,'governanca',True) else self.ref),encoding='utf-8')

    def gerar(self,r=None,empresa='FICTICIA'):
        self.salvar() if empresa=='FICTICIA' else None
        with patch.object(c,'RAIZ',self.root): return c.gerar(empresa,'2026-10','SOL-2026-999999',r or analisar())

    def status(self,r=None): return self.gerar(r)['lancamentos'][0]['status']


class Exterior(BaseContabil):
    """Defeito 2: tomador no exterior exige país estrangeiro reconhecido e coerente."""

    def setUp(self):
        super().setUp(); self.ref['referencias']['RECEITA_SERVICOS'].update(debito='12',tomador_exterior=True)

    def exterior(self,pais,cnpj=False,extra=''):
        t=NOTA if cnpj else NOTA.replace('CNPJ DO TOMADOR: 04.252.011/0001-10\n','')
        return analisar(arquivo(t+'PAIS DO TOMADOR: '+pais+'\n'+extra))

    def test_pais_nao_reconhecido_ou_brasil_pendente(self):
        for pais in ('NAO INFORMADO','SAO PAULO','BRA','BR','BRASIL','XYZLANDIA','EXTERIOR','OUTROS'):
            with self.subTest(pais=pais):
                l=self.gerar(self.exterior(pais))['lancamentos'][0]
                self.assertEqual(l['status'],'INCOMPLETO'); self.assertTrue(any('país' in p.lower() or 'pais' in p.lower() for p in l['pendencias']))

    def test_pais_estrangeiro_reconhecido_proposto(self):
        for pais in ('INDIA','ESTADOS UNIDOS','UNITED STATES','PORTUGAL','USA'):
            with self.subTest(pais=pais):
                self.assertEqual(self.status(self.exterior(pais)),'PROPOSTO_PARA_CONFERENCIA')

    def test_pais_estrangeiro_com_cnpj_brasileiro_conflito(self):
        l=self.gerar(self.exterior('INDIA',cnpj=True))['lancamentos'][0]
        self.assertEqual(l['status'],'INCOMPLETO'); self.assertTrue(any('onflito' in p for p in l['pendencias']),l['pendencias'])

    def test_brasil_com_identificador_estrangeiro_conflito_mesmo_em_referencia_nacional(self):
        self.ref['referencias']['RECEITA_SERVICOS'].update(debito='11',tomador_exterior=False)
        r=analisar(arquivo(NOTA+'PAIS DO TOMADOR: BRASIL\nNIF DO TOMADOR: PT123456789\n'))
        l=self.gerar(r)['lancamentos'][0]
        self.assertEqual(l['status'],'INCOMPLETO'); self.assertTrue(any('onflito' in p for p in l['pendencias']),l['pendencias'])

    def test_referencia_nacional_com_tomador_estrangeiro_pendente(self):
        self.ref['referencias']['RECEITA_SERVICOS'].update(debito='11',tomador_exterior=False)
        self.assertEqual(self.status(self.exterior('INDIA')),'INCOMPLETO')

    def test_referencia_nacional_brasil_com_cnpj_segue(self):
        self.ref['referencias']['RECEITA_SERVICOS'].update(debito='11',tomador_exterior=False)
        self.assertEqual(self.status(analisar(arquivo(NOTA+'PAIS DO TOMADOR: BRASIL\n'))),'PROPOSTO_PARA_CONFERENCIA')


class Deducao(BaseContabil):
    """Defeito 4: tributo sobre receita só debita conta redutora documentada."""

    def apuracao(self,trib='ISS'): return analisar(arquivo(APURACAO.format(trib=trib,valor='50,00')))

    def test_redutora_identificada_no_plano_aceita(self):
        l=self.gerar(self.apuracao())['lancamentos'][0]
        self.assertEqual(l['status'],'PROPOSTO_PARA_CONFERENCIA'); self.assertEqual(l['debito']['codigo'],'61')

    def test_receita_bruta_no_debito_do_iss_recusada(self):
        self.ref['referencias']['ISS']['debito']='60'
        l=self.gerar(self.apuracao())['lancamentos'][0]
        self.assertEqual(l['status'],'INCOMPLETO'); self.assertIsNone(l['debito'])

    def test_redutora_sem_marca_exige_campo_explicito(self):
        self.ref['referencias']['ISS']['debito']='62'
        self.assertEqual(self.status(self.apuracao()),'INCOMPLETO')
        self.ref['referencias']['ISS']['conta_redutora_receita']='62'
        self.assertEqual(self.status(self.apuracao()),'PROPOSTO_PARA_CONFERENCIA')
        self.ref['referencias']['ISS']['conta_redutora_receita']='60'
        self.assertEqual(self.status(self.apuracao()),'INCOMPLETO')

    def test_pis_em_receita_bruta_recusado(self):
        self.ref['referencias']['PIS']={'debito':'60','credito':'27','fonte':'Fictícia'}
        self.assertEqual(self.status(self.apuracao('PIS')),'INCOMPLETO')
        self.ref['referencias']['PIS']['debito']='63'
        self.assertEqual(self.status(self.apuracao('PIS')),'PROPOSTO_PARA_CONFERENCIA')

    def test_receita_de_servicos_nao_credita_redutora(self):
        self.ref['referencias']['RECEITA_SERVICOS']['credito']='61'
        self.assertEqual(self.status(),'INCOMPLETO')

    def test_apuracoes_repetidas_nao_duplicam_provisao_na_contabilidade(self):
        r=self.apuracao(); d2=json.loads(json.dumps(r['documentos'][0]))
        d2.update(id='FIS-OUTRO',sha256='0'*64,arquivo='RECEBIDOS/TESTE/outra.txt',valor='60.00'); r['documentos'].append(d2)
        self.assertEqual([l['status'] for l in self.gerar(r)['lancamentos']],['INCOMPLETO','INCOMPLETO'])


class DeducaoState(unittest.TestCase):
    """Item 4: as referências reais da STATE-BANK são somente lidas e copiadas; não são alteradas."""

    def setUp(self):
        if os.environ.get('AGENTES_PRIME_TESTE_REFERENCIAS_REAIS')!='1':
            self.skipTest('Leitura de referências REAIS desativada por padrão (release interno: testes só com dados fictícios). '
                          'Para conferir, defina AGENTES_PRIME_TESTE_REFERENCIAS_REAIS=1.')
        self.real=RAIZ/'CLIENTES/STATE-BANK'
        self.arquivos=[self.real/'REGRAS-FISCAIS.json',self.real/'PLANO-DE-CONTAS/PLANO-DE-CONTAS.md']
        if not all(a.exists() for a in self.arquivos): self.skipTest('Referências da STATE-BANK ausentes.')
        self.hashes=[hashlib.sha256(a.read_bytes()).hexdigest() for a in self.arquivos]
        self.tmp=tempfile.TemporaryDirectory(prefix='prime-salv-state-');self.root=Path(self.tmp.name)
        self.base=self.root/'CLIENTES/STATE-BANK';(self.base/'PLANO-DE-CONTAS').mkdir(parents=True)
        shutil.copyfile(self.arquivos[0],self.base/'REGRAS-FISCAIS.json')
        shutil.copyfile(self.arquivos[1],self.base/'PLANO-DE-CONTAS/PLANO-DE-CONTAS.md')
        self.regras=json.loads((self.base/'REGRAS-FISCAIS.json').read_text(encoding='utf-8'))
        (self.base/'empresa-local.json').write_text(json.dumps({'cnpj':self.regras['cnpj']}),encoding='utf-8')
        self.cnpj=''.join(ch for ch in self.regras['cnpj'] if ch.isdigit())

    def tearDown(self):
        self.tmp.cleanup()
        self.assertEqual([hashlib.sha256(a.read_bytes()).hexdigest() for a in self.arquivos],self.hashes)

    def gerar(self):
        cnpj_fmt=f'{self.cnpj[:2]}.{self.cnpj[2:5]}.{self.cnpj[5:8]}/{self.cnpj[8:12]}-{self.cnpj[12:]}'
        t=APURACAO.format(trib='ISS',valor='12,34').replace('11.222.333/0001-81',cnpj_fmt)
        r=f.analisar('STATE-BANK','2026-10','SOL-2026-999999',[arquivo(t)],[self.cnpj])
        with patch.object(c,'RAIZ',self.root): return c.gerar('STATE-BANK','2026-10','SOL-2026-999999',r)['lancamentos'][0]

    def test_60201_continua_aceita(self):
        l=self.gerar(); self.assertEqual(l['status'],'PROPOSTO_PARA_CONFERENCIA',l['pendencias'])
        self.assertEqual(l['debito']['codigo'],'60201')

    def test_receita_bruta_60002_no_debito_do_iss_recusada(self):
        self.regras['referencias']['ISS']['debito']=self.regras['referencias']['RECEITA_SERVICOS']['credito']
        (self.base/'REGRAS-FISCAIS.json').write_text(json.dumps(self.regras),encoding='utf-8')
        self.assertEqual(self.gerar()['status'],'INCOMPLETO')


class Vigencia(BaseContabil):
    """Defeito 6: fim de vigência respeitado; ausência apenas registrada."""

    def test_fim_de_vigencia_do_arquivo_respeitado(self):
        self.ref['competencia_ate']='2026-09'
        self.assertEqual(self.status(),'INCOMPLETO')

    def test_fim_de_vigencia_da_referencia_respeitado(self):
        self.ref['referencias']['RECEITA_SERVICOS']['competencia_ate']='2026-09'
        self.assertEqual(self.status(),'INCOMPLETO')
        self.ref['referencias']['RECEITA_SERVICOS']['competencia_ate']='2026-10'
        self.assertEqual(self.status(),'PROPOSTO_PARA_CONFERENCIA')

    def test_sem_fim_apenas_registra_limitacao(self):
        r=self.gerar(); self.assertEqual(r['lancamentos'][0]['status'],'PROPOSTO_PARA_CONFERENCIA')
        self.assertTrue(any('fim de vigência' in x for x in r['limites']),r['limites'])

    def test_vigencia_invalida_recusada(self):
        self.ref['competencia_ate']='setembro'
        self.assertEqual(self.status(),'INCOMPLETO')


class Filial(unittest.TestCase):
    """Mesmo radical da empresa sem cadastro (possível filial) não é cliente externo presumido."""
    def nota(self, tomador):
        return NOTA.replace('04.252.011/0001-10', tomador)

    def test_tomador_filial_nao_cadastrada_fica_pendente(self):
        d=analisar(arquivo(self.nota('11.222.333/0002-62')))['documentos'][0]
        self.assertFalse(d['elegivel_contabilidade'])
        self.assertTrue(any('mesmo radical' in p for p in d['pendencias']), d['pendencias'])

    def test_tomador_externo_continua_elegivel(self):
        d=analisar(arquivo(self.nota('04.252.011/0001-10')))['documentos'][0]
        self.assertTrue(d['elegivel_contabilidade'], d['pendencias'])


if __name__=='__main__': unittest.main()
