import unittest
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from BASE_CONHECIMENTO_CONTABIL.consulta import (
    autoriza_decisao_critica,
    carregar,
    consultar,
    consultar_cobertura,
    detectar_conflitos,
    validar_registro,
    vigente_na_competencia,
)


class BaseConhecimentoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registros = carregar()

    def test_categorias_e_ids_unicos_com_campos_obrigatorios(self):
        self.assertGreaterEqual(len(self.registros), 25)
        self.assertEqual(len({r["ID"] for r in self.registros}), len(self.registros))
        for registro in self.registros:
            validar_registro(registro)
            self.assertIn(registro["STATUS_VERIFICACAO"], {"VERIFICADO", "PARCIAL", "PENDENTE", "NAO_VERIFICADO"})

    def test_fontes_oficiais_citam_portal_e_url(self):
        fontes = [f for r in self.registros for f in r["FONTE_OFICIAL"]]
        self.assertTrue(fontes)
        self.assertTrue(all(f["URL"].startswith("https://") for f in fontes))

    def test_consulta_por_departamento_assunto_e_referencial(self):
        achados = consultar(departamento="fiscal", assunto="LALUR", registros=self.registros)
        self.assertIn("ECF-ELALUR-ELACS", {r["ID"] for r in achados})
        contabeis = consultar(departamento="contabilidade", referencial_contabil="NBC TG 1001", registros=self.registros)
        self.assertTrue(contabeis)
        self.assertIn("NBC-TG-1001", {r["ID"] for r in contabeis})

    def test_consulta_por_regime_operacao_e_competencia(self):
        achados = consultar(regime_tributario="lucro real", tipo_operacao="CSLL", competencia="2026-11", registros=self.registros)
        self.assertIn("IRPJ-CSLL-BASE-FISCAL", {r["ID"] for r in achados})

    def test_janela_de_vigencia_e_competencia_invalida(self):
        registro = next(r for r in self.registros if r["ID"] == "ITG-2000-R1")
        self.assertTrue(vigente_na_competencia(registro, "2026-11"))
        self.assertFalse(vigente_na_competencia(registro, "2010-01"))
        with self.assertRaises(ValueError):
            vigente_na_competencia(registro, "2026/11")

    def test_nao_verificados_e_pendentes_nao_sao_fundamento_confirmado(self):
        pendentes = consultar(status="PENDENTE", registros=self.registros)
        self.assertTrue(pendentes)
        self.assertTrue(all(not autoriza_decisao_critica(r) for r in self.registros))
        self.assertTrue(all(not r["AUTORIZA_DECISAO_AUTOMATICA"] for r in self.registros))

    def test_regra_especifica_fica_isolada_da_regra_geral_e_de_outra_empresa(self):
        exemplo = dict(self.registros[0])
        exemplo.update(ID="TESTE-REGRA-EMPRESA", ESCOPO={"TIPO": "EMPRESA", "EMPRESA_ID": "FICTICIA-A"})
        self.assertNotIn("TESTE-REGRA-EMPRESA", {r["ID"] for r in consultar(registros=[exemplo])})
        self.assertIn("TESTE-REGRA-EMPRESA", {r["ID"] for r in consultar(empresa_id="FICTICIA-A", registros=[exemplo])})
        self.assertNotIn("TESTE-REGRA-EMPRESA", {r["ID"] for r in consultar(empresa_id="FICTICIA-B", registros=[exemplo])})

    def test_conflito_normativo_gera_pendencia_sem_precedencia(self):
        encontrados = detectar_conflitos([
            {"ID": "NORMA-A", "CONFLITO_CHAVE": "CASO-FICTICIO", "CONFLITO_POSICAO": "POSICAO-A"},
            {"ID": "NORMA-B", "CONFLITO_CHAVE": "CASO-FICTICIO", "CONFLITO_POSICAO": "POSICAO-B"},
        ])
        self.assertEqual(len(encontrados), 1)
        self.assertEqual(encontrados[0]["RESULTADO"], "PENDENTE_REVISAO")
        self.assertEqual(encontrados[0]["POSICOES"], ["POSICAO-A", "POSICAO-B"])

    def test_simples_nacional_nao_seleciona_nbc_tg_1002(self):
        achados = consultar(assunto="NBC TG 1002", regime_tributario="Simples Nacional", registros=self.registros)
        self.assertNotIn("NBC-TG-1002", {r["ID"] for r in achados})

    def test_consulta_de_cobertura_exibe_tema_pendente(self):
        achados = consultar_cobertura(departamento="CONTABILIDADE", assunto="depreciação")
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0]["STATUS"], "PENDENTE")


if __name__ == "__main__":
    unittest.main(verbosity=2)

class ComplementacaoEtapa03BTest(unittest.TestCase):
    def test_fichas_p0_estruturadas_sem_decisao_automatica(self):
        from BASE_CONHECIMENTO_CONTABIL.consulta import carregar_fundamentos, consultar_fundamentos
        fichas = carregar_fundamentos()
        self.assertGreaterEqual(len(fichas), 17)
        self.assertTrue(all(f['FONTE_OFICIAL'] and f['DISPOSITIVO'] for f in fichas))
        self.assertTrue(all(f['AUTORIZA_DECISAO_AUTOMATICA'] is False for f in fichas))
        self.assertIn('P0-ESTOQUES-CMV', {f['ID'] for f in consultar_fundamentos(assunto='estoques')})

    def test_dez_consultas_demonstrativas_com_limites(self):
        from BASE_CONHECIMENTO_CONTABIL.consulta import consultar_respostas
        respostas = consultar_respostas()
        self.assertEqual(len(respostas), 10)
        for resposta in respostas:
            self.assertTrue(resposta['FONTES'])
            self.assertTrue(resposta['DISPOSITIVOS'])
            self.assertTrue(resposta['LIMITACOES'])
            self.assertTrue(resposta['NECESSIDADE_REVISAO'])
            self.assertFalse(resposta['AUTORIZA_DECISAO_AUTOMATICA'])

    def test_prioridades_preservam_158_topicos_e_expoem_lacunas(self):
        from BASE_CONHECIMENTO_CONTABIL.consulta import resumo_prioridades, consultar_cobertura
        resumo = resumo_prioridades()
        self.assertEqual(sum(resumo[p]['TOTAL'] for p in resumo), 158)
        self.assertEqual(resumo['P0']['TOTAL'], 130)
        self.assertEqual(resumo['P0']['PENDENTE'], 94)
        self.assertEqual(len(consultar_cobertura(prioridade='P0')), 130)

class Etapa03CTest(unittest.TestCase):
    def test_vinte_fundamentos_contabeis_estao_mapeados(self):
        from BASE_CONHECIMENTO_CONTABIL.consulta import carregar_fundamentos, consultar_fundamento_id
        fichas = carregar_fundamentos()
        cont = [f for f in fichas if f['ID'].startswith('CONT-')]
        self.assertEqual({f['ID'] for f in cont}, {f'CONT-{i:02d}' for i in range(1, 21)})
        self.assertEqual(len(cont), 20)
        for ficha in cont:
            self.assertIn(ficha['STATUS_VERIFICACAO'], {'VERIFICADO','PARCIAL','PENDENTE','NAO_VERIFICADO'})
            for campo in ('CONCEITO','OBJETIVO','NORMA','DISPOSITIVO','FONTE_OFICIAL','VIGENCIA','REFERENCIAL_APLICAVEL','CONDICOES_RECONHECIMENTO','CRITERIOS_MENSURACAO','EVIDENCIAS_NECESSARIAS','TRATAMENTO_CONTABIL_CONCEITUAL','EXEMPLO_FICTICIO','EXCECOES','ERROS_COMUNS','RISCOS','LIMITACOES','STATUS_VERIFICACAO'):
                self.assertTrue(ficha.get(campo), f"{ficha['ID']}: {campo}")
            self.assertTrue(ficha['FONTE_OFICIAL'])
            self.assertFalse(ficha['AUTORIZA_DECISAO_AUTOMATICA'])
        self.assertEqual(consultar_fundamento_id('CONT-01')['ID'], 'CONT-01')

    def test_referencial_e_vigencia_explicitados(self):
        from BASE_CONHECIMENTO_CONTABIL.consulta import carregar_fundamentos, consultar_fundamento_id
        fichas=[f for f in carregar_fundamentos() if f['ID'].startswith('CONT-')]
        self.assertTrue(all(f['REFERENCIAL_APLICAVEL'] for f in fichas))
        self.assertTrue(all(f['VIGENCIA'].get('OBSERVACAO') for f in fichas))
        self.assertTrue(all(f['STATUS_VERIFICACAO'] == 'VERIFICADO' for f in fichas))
        self.assertIn('NBC TG 1002', consultar_fundamento_id('CONT-10')['REFERENCIAL_APLICAVEL'])

    def test_doze_casos_ficticios_sao_consultaveis_sem_lancamento(self):
        from BASE_CONHECIMENTO_CONTABIL.consulta import consultar_casos_contabeis
        casos=consultar_casos_contabeis()
        self.assertEqual(len(casos),12)
        self.assertEqual({c['ID'] for c in casos},{f'CASO-{i:02d}' for i in range(1,13)})
        for caso in casos:
            self.assertIn('fictício',caso['EXEMPLO_FICTICIO'])
            self.assertTrue(caso['FUNDAMENTO_ID'].startswith('CONT-'))
            self.assertTrue(caso['FONTES'] and caso['DISPOSITIVOS'] and caso['LIMITACOES'])
            self.assertTrue(caso['EVIDENCIA_NECESSARIA'] and caso['NECESSIDADE_APROVACAO'])
            self.assertFalse(caso['AUTORIZA_DECISAO_AUTOMATICA'])
        self.assertEqual(consultar_casos_contabeis(caso_id='CASO-08')[0]['FUNDAMENTO_ID'],'CONT-11')

    def test_03c_preserva_inventario_de_158_topicos(self):
        from BASE_CONHECIMENTO_CONTABIL.consulta import consultar_cobertura
        self.assertEqual(len(consultar_cobertura()),158)

    def test_fundamento_parcial_bloqueia_uso_como_suficiente(self):
        from BASE_CONHECIMENTO_CONTABIL.consulta import consultar_fundamento_verificado
        self.assertEqual(consultar_fundamento_verificado('CONT-01')['STATUS_VERIFICACAO'],'VERIFICADO')
        with self.assertRaises(PermissionError):
            consultar_fundamento_verificado('P0-MENSURACAO')
