import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from BASE_CONHECIMENTO_CONTABIL.consulta import (
    carregar_fundamentos_dp, consultar_casos_dp, consultar_fundamento_dp_id,
    consultar_fundamentos_dp,
)

sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import estado_dp


class Etapa03FDPTest(unittest.TestCase):
    def test_vinte_fichas_com_fonte_dispositivo_e_limites(self):
        fichas = carregar_fundamentos_dp()
        self.assertEqual(len(fichas), 20)
        self.assertEqual({r["ID"] for r in fichas}, {f"DP-{i:02d}" for i in range(1, 21)})
        for r in fichas:
            for campo in ("CONCEITO", "OBJETIVO", "FUNDAMENTO", "FONTES", "DISPOSITIVO", "VIGENCIA",
                          "APLICABILIDADE", "REFERENCIAL", "EVIDENCIAS_NECESSARIAS", "TRATAMENTO_CONCEITUAL",
                          "EXCECOES", "RISCOS", "ERROS_COMUNS", "LIMITACOES", "EXEMPLO_FICTICIO",
                          "EVIDENCIA_CONSULTA"):
                self.assertTrue(r.get(campo), f"{r['ID']}: {campo}")
            self.assertFalse(r["AUTORIZA_DECISAO_AUTOMATICA"])
            self.assertIn(r["STATUS_VERIFICACAO"], {"VERIFICADO", "PARCIAL", "PENDENTE", "NAO_VERIFICADO"})
            self.assertTrue(all(f["URL"].startswith("https://") for f in r["FONTES"]))
            self.assertTrue(r["EXEMPLO_FICTICIO"].startswith("Exemplo fictício:"))
            self.assertIn("competência", r["LIMITACOES"].lower())

    def test_consulta_por_assunto_referencial_competencia_e_status(self):
        self.assertIn("DP-07", {r["ID"] for r in consultar_fundamentos_dp(assunto="FGTS")})
        self.assertIn("DP-01", {r["ID"] for r in consultar_fundamentos_dp(referencial="NBC TG 1001", competencia="2026-11")})
        self.assertEqual([r["ID"] for r in consultar_fundamentos_dp(status="VERIFICADO")], ["DP-16", "DP-17", "DP-18"])
        with self.assertRaises(ValueError):
            consultar_fundamentos_dp(competencia="2026/11")

    def test_bloqueio_de_fundamento_nao_verificado(self):
        self.assertFalse(consultar_fundamento_dp_id("DP-05")["AUTORIZA_DECISAO_AUTOMATICA"])
        with self.assertRaises(PermissionError):
            consultar_fundamento_dp_id("DP-05", exigir_verificado=True)

    def test_casos_ficticios_estruturados(self):
        casos = consultar_casos_dp()
        self.assertEqual(len(casos), 15)
        self.assertEqual({c["ID"] for c in casos}, {f"DP-CASO-{i:02d}" for i in range(1, 16)})
        for c in casos:
            self.assertTrue(c["FUNDAMENTO_IDS"] and c["DOCUMENTACAO"] and c["FONTES"])
            self.assertTrue(c["DISPOSITIVOS"] and c["VIGENCIA"] and c["APLICABILIDADE"])
            self.assertTrue(c["RISCOS"] and c["LIMITACOES"] and c["NECESSIDADE_REVISAO"])
            self.assertFalse(c["AUTORIZA_DECISAO_AUTOMATICA"])
            self.assertIn("fictício", c["EXEMPLO_FICTICIO"].lower())

    def test_bruto_liquido_retencoes_e_liquidacao(self):
        bruto = consultar_casos_dp(caso_id="DP-CASO-01")[0]
        self.assertIn("R$ 10.000,00", bruto["FATO"])
        self.assertIn("R$ 8.500,00", bruto["FATO"])
        self.assertIn("descontos", bruto["TRATAMENTO_CONCEITUAL"])
        self.assertIn("obrigação de salários já foi reconhecida", consultar_casos_dp(caso_id="DP-CASO-02")[0]["TRATAMENTO_CONCEITUAL"])
        self.assertIn("não duplica despesa", consultar_casos_dp(caso_id="DP-CASO-10")[0]["TRATAMENTO_CONCEITUAL"])

    def test_nao_aplicavel_evidencia_contraditoria_aguarda_supervisor(self):
        estado = estado_dp.nao_aplicavel("EMP-FICTICIA", "2026-10", justificativa="Caso de teste fictício")
        conflito = estado_dp.conflito(estado, [{"id": "doc-ficticio"}])
        self.assertEqual(estado["contrato"], "STATUS_DP_CONTEXTUAL_V1")
        self.assertEqual(conflito["codigo"], "DP_NAO_APLICAVEL_CONTRADITORIO")
        self.assertEqual(conflito["status"], "AGUARDANDO_SUPERVISOR")
        caso = consultar_casos_dp(caso_id="DP-CASO-15")[0]
        self.assertIn("evidência", caso["FATO"].lower())
        self.assertIn("Supervisor", caso["NECESSIDADE_REVISAO"])

    def test_fontes_esocial_e_dctfweb_nao_confundem_declaracao_e_pagamento(self):
        esocial = consultar_fundamento_dp_id("DP-17")
        self.assertIn("S-1200/S-1202/S-1207", esocial["DISPOSITIVO"])
        dctf = consultar_fundamento_dp_id("DP-18")
        self.assertIn("pagamento efetivo", dctf["TRATAMENTO_CONCEITUAL"])
        self.assertTrue(any("gov.br/receitafederal" in f["URL"] for f in dctf["FONTES"]))

    def test_intercambio_preserva_responsabilidades_departamentais(self):
        dp = consultar_fundamento_dp_id("DP-16")
        self.assertIn("Financeiro", dp["PROCEDIMENTO_INTERNO_RELACIONADO"])
        self.assertIn("CONT-19", dp["FUNDAMENTOS_CONTABEIS_RELACIONADOS"])
        self.assertIn("FIN-05", dp["FUNDAMENTOS_FINANCEIROS_RELACIONADOS"])
