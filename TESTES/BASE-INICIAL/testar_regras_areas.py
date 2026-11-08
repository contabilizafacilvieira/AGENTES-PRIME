"""Cobertura isolada das referências de DP, Fiscal e Conciliação (dados fictícios)."""
import json, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "API-LOCAL"))
import regras_areas

def conta(codigo, classificacao, descricao, grupo, tipo="ANALITICA"):
    return {"codigo": codigo, "classificacao": classificacao, "descricao": descricao, "grupo": grupo, "tipo": tipo}

class RegrasAreas(unittest.TestCase):
    def setUp(self):
        self.plano = [conta("2000","2","OBRIGACOES","PASSIVO","SINTETICA"), conta("2101","2.1","INSS A RECOLHER","PASSIVO"), conta("2102","2.2","FGTS A RECOLHER","PASSIVO"), conta("2103","2.3","SALARIOS E ORDENADOS","PASSIVO"), conta("1201","1.2","ICMS A RECUPERAR","ATIVO"), conta("2201","2.4","ICMS A RECOLHER","PASSIVO"), conta("2202","2.5","PIS A RECOLHER","PASSIVO"), conta("2203","2.6","COFINS A RECOLHER","PASSIVO"), conta("1101","1.1","BANCO FICTICIO","ATIVO"), conta("1102","1.1.1","APLICACAO FINANCEIRA FICTICIA","ATIVO"), conta("1300","1.3","CLIENTES","ATIVO","SINTETICA"), conta("1301","1.3.1","CLIENTE FICTICIO ALFA","ATIVO"), conta("2104","2.7","FORNECEDORES","PASSIVO","SINTETICA"), conta("2105","2.7.1","FORNECEDOR FICTICIO BETA","PASSIVO"), conta("3101","3.1","PIS SOBRE RECEITA","DESPESA")]
    def sugestoes(self):
        s=regras_areas.sugerir("EMPRESA-FICTICIA",self.plano,"2026-10"); s["plano"]=self.plano; return s
    def test_dp_ref_01_02_03(self):
        d={x["chave"]:x for x in self.sugestoes()["areas"]["DP"]["itens"]}; self.assertEqual(d["FOLHA_PROVENTOS"]["conta"]["codigo"],"2103"); self.assertEqual(d["RETENCAO_INSS"]["conta"]["codigo"],"2101"); self.assertEqual(d["ENCARGO_FGTS"]["conta"]["codigo"],"2102")
    def test_dp_ref_04_sintetica_prefere_analitica(self):
        s=regras_areas.sugerir("E",[conta("2000","2","SALARIOS","PASSIVO","SINTETICA"),conta("2001","2.1","SALARIOS E ORDENADOS","PASSIVO")],"2026-10"); self.assertEqual(next(x for x in s["areas"]["DP"]["itens"] if x["chave"]=="FOLHA_PROVENTOS")["conta"]["codigo"],"2001")
    def test_dp_ref_05_inexistente_nao_inventa(self):
        s=regras_areas.sugerir("E",[conta("1000","1","CAIXA","ATIVO")],"2026-10"); self.assertIsNone(next(x for x in s["areas"]["DP"]["itens"] if x["chave"]=="ENCARGO_FGTS")["conta"])
    def test_dp_ref_06_07_08_troca_nao_aplica_audita(self):
        s=self.sugestoes()
        with tempfile.TemporaryDirectory() as td:
            b=Path(td); (b/"CADASTRO.md").write_text("CNPJ: 11.111.111/1111-11\n")
            regras_areas.confirmar(b,s,"DP",[{"chave":"RETENCAO_INSS","acao":"CONFIRMAR","codigo":"2102"}],"2026-10"); d=json.loads((b/"REGRAS-DP.json").read_text()); self.assertEqual(d["referencias"]["RETENCAO_INSS"]["debito"],"2102")
            with self.assertRaises(ValueError): regras_areas.confirmar(b,s,"DP",[{"chave":"ENCARGO_FGTS","acao":"NAO_APLICA","justificativa":"x"}],"2026-10")
            regras_areas.confirmar(b,s,"DP",[{"chave":"ENCARGO_FGTS","acao":"NAO_APLICA","justificativa":"sem folha nesta empresa fictícia"}],"2026-10"); d=json.loads((b/"REGRAS-DP.json").read_text()); self.assertTrue(d["referencias"]["ENCARGO_FGTS"]["nao_aplicavel"]); self.assertTrue(list((b/"VERSOES").glob("REGRAS-DP.json-*.json")))
    def test_fiscal_ref_01_02_03_06(self):
        f={x["chave"]:x for x in self.sugestoes()["areas"]["FISCAL"]["itens"]}; self.assertEqual(f["ICMS_RECOLHER"]["conta"]["codigo"],"2201"); self.assertEqual(f["ICMS_RECUPERAR"]["conta"]["codigo"],"1201"); self.assertEqual(f["PIS"]["conta"]["codigo"],"2202"); self.assertEqual(f["COFINS"]["conta"]["codigo"],"2203")
    def test_fiscal_ref_04_05_07_ambiguo_e_resultado(self):
        p=[conta("3101","3.1","IRPJ","DESPESA"),conta("3102","3.2","CSLL","DESPESA"),conta("1000","1","CAIXA","ATIVO")]; f={x["chave"]:x for x in regras_areas.sugerir("E",p,"2026-10")["areas"]["FISCAL"]["itens"]}; self.assertIsNone(f["IRPJ"]["conta"]); self.assertIsNone(f["CSLL"]["conta"]); self.assertIsNone(f["ISS"]["conta"])
    def test_conc_ref_01_02_03_04(self):
        c={x["chave"]:x for x in self.sugestoes()["areas"]["CONCILIACAO"]["itens"]}; self.assertEqual(c["BANCOS"]["conta"]["codigo"],"1101"); self.assertEqual(c["APLICACOES"]["conta"]["codigo"],"1102"); self.assertEqual(c["CLIENTES"]["conta"]["codigo"],"1301"); self.assertEqual(c["FORNECEDORES"]["conta"]["codigo"],"2105")
    def test_conc_ref_05_06_07_ambigua(self):
        p=[conta("3101","3.1","BANCO FICTICIO","RECEITA"),conta("3102","3.2","BANCO FICTICIO","DESPESA"),conta("1000","1","CAIXA","ATIVO")]; i=next(x for x in regras_areas.sugerir("E",p,"2026-10")["areas"]["CONCILIACAO"]["itens"] if x["chave"]=="BANCOS"); self.assertIsNone(i["conta"]); self.assertEqual(i["status"],"PRECISA_CONFIRMACAO")
    def test_regra_area_01_02_03_04_05_06_vigencia_historico(self):
        s=self.sugestoes()
        with tempfile.TemporaryDirectory() as td:
            b=Path(td); regras_areas.confirmar(b,s,"CONCILIACAO",[{"chave":"BANCOS","acao":"CONFIRMAR","codigo":"1101"}],"2026-10"); primeira=(b/"REGRAS-CONCILIACAO.json").read_text(); regras_areas.confirmar(b,s,"CONCILIACAO",[{"chave":"BANCOS","acao":"CONFIRMAR","codigo":"1102"}],"2026-11"); self.assertNotEqual(primeira,(b/"REGRAS-CONCILIACAO.json").read_text()); self.assertTrue(list((b/"VERSOES").glob("REGRAS-CONCILIACAO.json-*.json"))); self.assertFalse((b/"REGRAS-DP.json").exists())
    def test_api_01_04_05_06_get_somente_leitura_e_conta_invalida(self):
        s=self.sugestoes()
        with tempfile.TemporaryDirectory() as td:
            b=Path(td); self.assertIn("areas",s); self.assertFalse((b/"REGRAS-DP.json").exists());
            with self.assertRaises(ValueError): regras_areas.confirmar(b,s,"DP",[{"chave":"RETENCAO_INSS","acao":"CONFIRMAR","codigo":"9999"}],"2026-10")
            self.assertFalse((b/"REGRAS-DP.json").exists())

if __name__ == "__main__": unittest.main(verbosity=2)
