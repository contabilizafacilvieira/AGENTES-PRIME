import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(RAIZ))
from BASE_CONHECIMENTO_CONTABIL.consulta import (
 carregar_fundamentos_fiscais, consultar_casos_fiscais,
 consultar_fundamento_fiscal_id, consultar_fundamentos_fiscais)

class Etapa03EFiscalTest(unittest.TestCase):
 def test_vinte_e_cinco_fichas_e_campos_fontes_e_bloqueio(self):
  fichas=carregar_fundamentos_fiscais()
  self.assertEqual(len(fichas),25)
  self.assertEqual({f['ID'] for f in fichas},{f'FISC-{i:02d}' for i in range(1,26)})
  for f in fichas:
   for campo in ('CONCEITO','OBJETIVO','FUNDAMENTO','FONTES','DISPOSITIVO','VIGENCIA','APLICABILIDADE','EVIDENCIAS_NECESSARIAS','TRATAMENTO_CONCEITUAL','EXCECOES','RISCOS','LIMITACOES','EXEMPLO_FICTICIO','STATUS_VERIFICACAO','EVIDENCIA_CONSULTA'):
    self.assertTrue(f.get(campo),f['ID']+' '+campo)
   self.assertFalse(f['AUTORIZA_DECISAO_AUTOMATICA'])
   self.assertTrue(all(x['URL'].startswith('https://') for x in f['FONTES']))
   self.assertEqual(f['STATUS_APLICABILIDADE'],'DEPENDENTE_DE_CONTEXTO')
  self.assertEqual(sum(f['STATUS_VERIFICACAO']=='VERIFICADO' for f in fichas),5)
  self.assertEqual(sum(f['STATUS_VERIFICACAO']=='PARCIAL' for f in fichas),20)

 def test_busca_assunto_regime_jurisdicao_e_contexto_explicito(self):
  x=consultar_fundamentos_fiscais(assunto='ICMS',regime='Lucro Real',competencia='2026-11',uf='SP',municipio='São Paulo',tipo_operacao='entrada')
  self.assertIn('FISC-12',{f['ID'] for f in x})
  self.assertEqual(x[0]['CONTEXTO_SOLICITADO']['UF'],'SP')
  self.assertIn('não determina',x[0]['ALERTA_CONTEXTO_CONSULTA'])
  self.assertIn('FISC-10',{f['ID'] for f in consultar_fundamentos_fiscais(assunto='recuperáveis')})
  with self.assertRaises(ValueError): consultar_fundamentos_fiscais(competencia='2026/11')

 def test_ids_status_nao_verificados_bloqueiam_e_filtro(self):
  self.assertEqual(consultar_fundamento_fiscal_id('FISC-01')['ID'],'FISC-01')
  self.assertEqual(len(consultar_fundamentos_fiscais(status='PARCIAL')),20)
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)
   data=json.loads((RAIZ/'BASE_CONHECIMENTO_CONTABIL/fundamentos_fiscais.json').read_text())
   data['REGISTROS'][0]['STATUS_VERIFICACAO']='NAO_VERIFICADO'
   (p/'fundamentos_fiscais.json').write_text(json.dumps(data))
   with self.assertRaises(PermissionError): consultar_fundamento_fiscal_id('FISC-01',exigir_verificado=True,base=p)

 def test_vinte_casos_ficticios_contextuais_e_sem_lancamento(self):
  casos=consultar_casos_fiscais()
  self.assertEqual(len(casos),20)
  for c in casos:
   self.assertTrue(c['EXEMPLO_FICTICIO'].startswith('Exemplo fictício:'))
   self.assertTrue(c['FUNDAMENTO_IDS'] and c['FONTES'] and c['DISPOSITIVOS'] and c['EVIDENCIA_NECESSARIA'])
   self.assertTrue(c['LIMITACOES'] and c['NECESSIDADE_APROVACAO'])
   self.assertFalse(c['AUTORIZA_DECISAO_AUTOMATICA'])

 def test_distincoes_credito_emissao_pagamento_e_base_fiscal(self):
  fs={f['ID']:f for f in carregar_fundamentos_fiscais()}
  self.assertIn('destaque',fs['FISC-10']['ERROS_COMUNS'])
  self.assertIn('emissão',fs['FISC-07']['TRATAMENTO_CONCEITUAL'])
  self.assertIn('pagamento',fs['FISC-18']['TRATAMENTO_CONCEITUAL'])
  self.assertIn('resultado contábil',fs['FISC-21']['FUNDAMENTO'])
  self.assertIn('município',fs['FISC-14']['DISPOSITIVO']) if 'município' in fs['FISC-14']['DISPOSITIVO'] else self.assertIn('municipal',fs['FISC-14']['FUNDAMENTO'])

 def test_consulta_de_casos_por_id_e_termo(self):
  self.assertEqual(consultar_casos_fiscais(caso_id='FISC-CASO-16')[0]['TITULO'],'IRPJ e CSLL sobre base fiscal')
  self.assertEqual(len(consultar_casos_fiscais(termo='DUIMP')),1)

if __name__=='__main__': unittest.main(verbosity=2)
