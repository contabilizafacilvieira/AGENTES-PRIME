"""Governança das regras: confirmação bancária vinculada a empresa/regra/versão e política de data não suportada.
Empresa fictícia em pasta TEMPORÁRIA (AGENTES_PRIME_CLIENTES); registro temporário; nada em CLIENTES/ real.

Uso: .venv/Scripts/python.exe -I TESTES/GOVERNANCA/testar_governanca_regras.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="prime-governanca-"))
os.environ.update(AGENTES_PRIME_CLIENTES=str(TMP / "CLIENTES"), AGENTES_PRIME_REGISTRO_SOL=str(TMP / "registro.json"),
                  AGENTES_PRIME_ORDEM_ATIVA=str(TMP / "ordem.json"))
sys.path.insert(0, str(RAIZ / "AGENTES" / "CONTABILIDADE"))
sys.path.insert(0, str(RAIZ / "AGENTES" / "CONTABILIDADE" / "BANCOS" / "ferramentas"))
import governanca_regras as gov  # noqa: E402
import lancamentos_bancarios as lb  # noqa: E402

EMP = "EMPRESA-GOV-TMP"
CAB = ("| Regra | Versão | Condições | Tipo | Contrapartida | Exige suporte | Histórico | Origem | Situação | Aprovação |\n"
       "|---|---|---|---|---|---|---|---|---|---|\n")


def linha(rb, situacao, aprovacao, versao="2", origem="Fechamento fictício"):
    return f"| {rb} | {versao} | direcao=DEBITO; historico_contem=TARIFA | DESPESA | 4202 | NAO | TARIFA | {origem} | {situacao} | {aprovacao} |\n"


class Bancos(unittest.TestCase):
    def setUp(self):
        self.base = TMP / "CLIENTES" / EMP
        shutil.rmtree(self.base, ignore_errors=True)
        self.base.mkdir(parents=True)
        (self.base / "CADASTRO.md").write_text(f"# Cadastro\n- Razão social: GOV TMP LTDA\n- CNPJ: 90.010.010/0001-09\n", encoding="utf-8")

    def regras(self, *linhas):
        (self.base / "REGRAS-BANCOS.md").write_text("# Regras\n\n## Regras\n" + CAB + "".join(linhas), encoding="utf-8")

    def aplicadas(self):
        regras, avisos = lb.ler_regras(EMP)
        return [r["id"] for r in regras], avisos

    def test_confirmacao_vinculada_a_empresa_regra_versao(self):
        boa = gov.texto_confirmacao_bancos(EMP, "RB-001", "2", "2026-11-05T10:00:00-03:00")
        self.assertTrue(gov.confirmacao_bancos(boa, EMP, "RB-001", "2")["valida"])
        self.assertFalse(gov.confirmacao_bancos(boa, EMP, "RB-001", "3")["valida"])         # outra versão
        self.assertFalse(gov.confirmacao_bancos(boa, "OUTRA", "RB-001", "2")["valida"])     # outra empresa
        self.assertFalse(gov.confirmacao_bancos(boa, EMP, "RB-002", "2")["valida"])         # outra regra
        self.assertFalse(gov.confirmacao_bancos(boa.replace("por=Supervisor Contábil", "por="), EMP, "RB-001", "2")["valida"])

    def test_texto_livre_e_formato_antigo_nao_aplicados_e_pendentes(self):
        self.regras(linha("RB-001", "VALIDADA", "aprovado pelo chefe"),
                    linha("RB-002", "VALIDADA", f'"VALIDADO REGRA {EMP} RB-002" em 2026-10-31'),
                    linha("RB-003", "VALIDADA", gov.texto_confirmacao_bancos(EMP, "RB-003", "2", "2026-11-05T10:00:00-03:00")),
                    linha("RB-004", "PROPOSTA", "-"), linha("RB-005", "TESTE_FICTICIO", "teste"))
        ids, avisos = self.aplicadas()
        self.assertEqual(ids, ["RB-003"])                       # só a confirmação completa; teste sem marcador = empresa real
        pend = {p["chave"]: p["situacao"] for p in gov.pendencias_bancos(EMP)}
        self.assertEqual(pend, {"RB-001": "INSUFICIENTE", "RB-002": "LEGADA_SEM_VERSAO", "RB-004": "PROPOSTA", "RB-005": "TESTE_FICTICIO"})
        self.assertTrue(any("RB-002" in a and "reconfirme" in a for a in avisos), avisos)

    def test_teste_ficticio_so_com_marcador(self):
        self.regras(linha("RB-005", "TESTE_FICTICIO", "teste"))
        self.assertEqual(self.aplicadas()[0], [])
        (self.base / "AMOSTRA-FICTICIA.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.aplicadas()[0], ["RB-005"])

    def cli(self, *args):
        p = subprocess.run([sys.executable, "-I", str(RAIZ / "COORDENADOR-GERAL" / "ferramentas" / "coordenador.py"), *args],
                           capture_output=True, encoding="utf-8")
        return p.returncode, json.loads(p.stdout)

    def test_confirmacao_pelo_supervisor_preserva_versao_anterior(self):
        self.regras(linha("RB-002", "VALIDADA", f'"VALIDADO REGRA {EMP} RB-002" em 2026-10-31'),
                    linha("RB-005", "TESTE_FICTICIO", "teste"), linha("RB-006", "PROPOSTA", "-", origem=" "))
        antes = (self.base / "REGRAS-BANCOS.md").read_text(encoding="utf-8")
        c1, r1 = self.cli("aprovar-regra-area", "--empresa", EMP, "--area", "BANCOS", "--chave", "RB-002", "--frase", "aprovo")
        c2, r2 = self.cli("aprovar-regra-area", "--empresa", EMP, "--area", "BANCOS", "--chave", "RB-002", "--frase", f"VALIDADO REGRA {EMP} RB-002")
        c3, _ = self.cli("aprovar-regra-area", "--empresa", EMP, "--area", "BANCOS", "--chave", "RB-002", "--frase", f"VALIDADO REGRA {EMP} RB-002")
        c4, r4 = self.cli("aprovar-regra-area", "--empresa", EMP, "--area", "BANCOS", "--chave", "RB-005", "--frase", f"VALIDADO REGRA {EMP} RB-005")
        c5, r5 = self.cli("aprovar-regra-area", "--empresa", EMP, "--area", "BANCOS", "--chave", "RB-006", "--frase", f"VALIDADO REGRA {EMP} RB-006")
        self.assertEqual((c1 != 0, r1["resultado"]), (True, "APROVACAO_INVALIDA"))
        self.assertEqual((c2, r2["versao"]), (0, "2"))
        self.assertNotEqual(c3, 0)                              # já confirmada: não repete
        self.assertIn("TESTE", r4["motivo"])
        self.assertIn("origem", r5["motivo"])
        self.assertEqual(self.aplicadas()[0], ["RB-002"])
        copias = list((self.base / "VERSOES").glob("REGRAS-BANCOS-*.md"))
        self.assertEqual([p.read_text(encoding="utf-8") for p in copias], [antes])


class DataNaoSuportada(unittest.TestCase):
    def test_data_de_emissao_indisponivel_sem_substituicao(self):
        pol = {"politica": "DATA_EMISSAO_DOCUMENTO", "situacao": "APROVADA", "origem": "x",
               "confirmacao": {"frase": gov.frase("FISCAL", EMP, "DATA_LANCAMENTO"), "em": "2026-11-05T10:00:00", "por": "Supervisor Contábil"}}
        r = gov.politica_data({"data_lancamento": pol}, "FISCAL", EMP, "2026-10")
        self.assertEqual((r["aplicavel"], r["politica"]), (False, None))
        self.assertIn("não extraem a data de emissão", r["motivo"])
        base = TMP / "CLIENTES" / "EMPRESA-DATA-TMP"
        base.mkdir(parents=True, exist_ok=True)
        (base / "CADASTRO.md").write_text("# Cadastro\n- CNPJ: 90.010.010/0001-09\n", encoding="utf-8")
        (base / "REGRAS-FISCAIS.json").write_text(json.dumps({"contrato": "REFERENCIAS_FISCAIS_V1", "empresa": "EMPRESA-DATA-TMP",
                                                              "referencias": {}, "data_lancamento": dict(pol, situacao="PROPOSTA")}), encoding="utf-8")
        itens = [i for i in gov.definicoes_necessarias("EMPRESA-DATA-TMP") if i["chave"] == "DATA_LANCAMENTO" and i["area"] == "FISCAL"]
        self.assertEqual(itens[0]["situacao"], "NAO_SUPORTADA")
        p = subprocess.run([sys.executable, "-I", str(RAIZ / "COORDENADOR-GERAL" / "ferramentas" / "coordenador.py"), "aprovar-regra-area",
                            "--empresa", "EMPRESA-DATA-TMP", "--area", "FISCAL", "--chave", "DATA_LANCAMENTO",
                            "--frase", gov.frase("FISCAL", "EMPRESA-DATA-TMP", "DATA_LANCAMENTO")], capture_output=True, encoding="utf-8")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("indisponível", json.loads(p.stdout)["motivo"])


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
