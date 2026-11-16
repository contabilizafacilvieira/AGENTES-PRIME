import unittest
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from BASE_CONHECIMENTO_CONTABIL.consulta import (
    carregar_fundamentos_financeiros,
    consultar_casos_financeiros,
    consultar_fundamento_financeiro_id,
    consultar_fundamentos_financeiros,
)


class Etapa03DFinanceiroTest(unittest.TestCase):
    def test_vinte_fichas_estruturadas_sem_decisao_automatica(self):
        fichas = carregar_fundamentos_financeiros()
        self.assertEqual(len(fichas), 20)
        self.assertEqual({f["ID"] for f in fichas}, {f"FIN-{i:02d}" for i in range(1, 21)})
        obrigatorios = ("CONCEITO", "OBJETIVO", "FUNDAMENTO", "FONTES", "DISPOSITIVO", "VIGENCIA",
                        "APLICABILIDADE", "REFERENCIAL", "EVIDENCIAS_NECESSARIAS", "TRATAMENTO_CONCEITUAL",
                        "EXCECOES", "RISCOS", "ERROS_COMUNS", "PROCEDIMENTO_INTERNO_RELACIONADO",
                        "EXEMPLO_FICTICIO", "LIMITACOES", "STATUS_VERIFICACAO", "EVIDENCIA_CONSULTA")
        for f in fichas:
            for campo in obrigatorios:
                self.assertTrue(f.get(campo), f"{f['ID']}: {campo}")
            self.assertFalse(f["AUTORIZA_DECISAO_AUTOMATICA"])
            self.assertIn(f["STATUS_VERIFICACAO"], {"VERIFICADO", "PARCIAL", "PENDENTE", "NAO_VERIFICADO"})
            self.assertTrue(all(x["URL"].startswith("https://") for x in f["FONTES"]))
            self.assertIn("Exemplo fictício:", f["EXEMPLO_FICTICIO"])

    def test_consulta_por_assunto_referencial_e_competencia(self):
        self.assertIn("FIN-17", {f["ID"] for f in consultar_fundamentos_financeiros(assunto="Pix")})
        self.assertIn("FIN-14", {f["ID"] for f in consultar_fundamentos_financeiros(referencial="NBC TG 1001", competencia="2026-11")})
        with self.assertRaises(ValueError):
            consultar_fundamentos_financeiros(competencia="2026/11")

    def test_fundamento_verificado_e_sem_automatico(self):
        self.assertEqual(consultar_fundamento_financeiro_id("FIN-02")["ID"], "FIN-02")
        self.assertFalse(consultar_fundamento_financeiro_id("FIN-02")["AUTORIZA_DECISAO_AUTOMATICA"])

    def test_quinze_casos_ficticios_com_evidencia_responsavel_e_decisao_humana(self):
        casos = consultar_casos_financeiros()
        self.assertEqual(len(casos), 15)
        self.assertEqual({c["ID"] for c in casos}, {f"FIN-CASO-{i:02d}" for i in range(1, 16)})
        for c in casos:
            self.assertIn("Exemplo fictício:", c["EXEMPLO_FICTICIO"])
            self.assertTrue(c["FUNDAMENTO_IDS"] and c["EVIDENCIA_NECESSARIA"] and c["DEPARTAMENTO_RESPONSAVEL"])
            self.assertTrue(c["LIMITACOES"] and c["NECESSIDADE_DECISAO_HUMANA"] and c["FONTES"])
            self.assertFalse(c["AUTORIZA_DECISAO_AUTOMATICA"])

    def test_casos_chave_distinguem_liquidacao_e_natureza(self):
        pagamento = consultar_casos_financeiros(caso_id="FIN-CASO-01")[0]
        sem_doc = consultar_casos_financeiros(caso_id="FIN-CASO-02")[0]
        pix = consultar_casos_financeiros(caso_id="FIN-CASO-12")[0]
        duplicidade = consultar_casos_financeiros(caso_id="FIN-CASO-15")[0]
        self.assertIn("não se registra despesa", pagamento["TRATAMENTO_CONCEITUAL"])
        self.assertIn("natureza desconhecida", sem_doc["NATUREZA_PROVAVEL"])
        self.assertIn("não determina", pix["FUNDAMENTO"])
        self.assertIn("valor", duplicidade["LIMITACOES"])

    def test_criterios_motor_permancem_rotulados_procedimento_interno(self):
        fichas = carregar_fundamentos_financeiros()
        conc = next(f for f in fichas if f["ID"] == "FIN-02")
        rastreio = next(f for f in fichas if f["ID"] == "FIN-20")
        self.assertEqual(conc["TIPO_CONHECIMENTO"], "PROCEDIMENTO_INTERNO")
        self.assertIn("interno", conc["PROCEDIMENTO_INTERNO_RELACIONADO"].casefold())
        self.assertIn("interno", rastreio["PROCEDIMENTO_INTERNO_RELACIONADO"].casefold())
        self.assertIn("sem determinar", conc["CRITERIO_ASSOCIACAO_MOTOR"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
