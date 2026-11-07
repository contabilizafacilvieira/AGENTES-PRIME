"""Testes unitários da exportação TXT para o Domínio (API-LOCAL/exportacao_dominio.py). Somente dados fictícios, pasta temporária.

Reproduz os defeitos apontados no relatório de 05/11/2026 (valor inválido, contas, histórico com caminho técnico, '?' silencioso,
data presumida, fatos não aprovados) e confere que cada um RECUSA a exportação inteira, com todos os problemas listados.

Uso: .venv/Scripts/python.exe -I TESTES/EXPORTACAO/testar_exportacao_dominio.py
"""
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import exportacao_dominio as ex  # noqa: E402

EMP, SOL, COMP = "EMPRESA-EXPORT-TESTE", "SOL-2026-990001", "2026-10"
PLANO = {"1101": {"tipo": "ANALITICA"}, "1121": {"tipo": "ANALITICA"}, "2122": {"tipo": "ANALITICA"}, "4105": {"tipo": "ANALITICA"},
         "3101": {"tipo": "ANALITICA"}, "11": {"tipo": "SINTETICA"}}


def lan(i, data, deb, cre, valor, hist, ident, status="PROPOSTO"):
    return {"id": f"L{i}", "status": status, "data": data, "valor": valor, "debito": {"codigo": deb}, "credito": {"codigo": cre},
            "historico": hist, "identidade": ident, "arquivo": f"RECEBIDOS/2026-10/L-20261105-101010-abcdef/doc{i}.txt"}


def resultados_base():
    return {"BANCOS": [lan(1, "2026-10-25", "1101", "1121", "6000.00", "RECEBIMENTO GAMA COMERCIO REF. NOTA FISCAL 102", "BANCO:MOV-1")],
            "CONTABILIDADE_DP": [lan(2, "2026-10-31", "4105", "2122", "666.67", "PROVISAO DE 13 SALARIO COMPETENCIA 10/2026 REF. PR-2026-10",
                                     "DP:PROVISAO_13:2026-10:abc", "PROPOSTO_PARA_CONFERENCIA")],
            "CONTABILIDADE_FISCAL": [lan(3, "2026-10-31", "1121", "3101", "4000.00", "RECEITA_SERVICOS REF. 103 COMPETENCIA 2026-10",
                                         "FISCAL:RECEITA_SERVICOS:NOTA:90010010000109:103", "PROPOSTO_PARA_CONFERENCIA")]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="prime-export-"))
        self.res = resultados_base()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def montar(self, aprovar_fatos=True, mudar_depois=None):
        """Grava os resultados, aprova (sha256 + fatos aprovados) e, opcionalmente, altera algo DEPOIS da aprovação."""
        caminhos, versoes, fatos = {}, {}, {}
        for etapa, lancs in self.res.items():
            r = {"empresa": EMP, "sol": SOL, "competencia": COMP, "lancamentos": lancs}
            p = self.tmp / f"{etapa}.json"
            p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
            caminhos[etapa], versoes[etapa] = str(p), hashlib.sha256(p.read_bytes()).hexdigest()
            for l in lancs:
                if l.get("identidade") and l["status"] in ex.PROPOSTO:
                    fatos[l["identidade"]] = {"valor": l["valor"], "debito": (l["debito"] or {}).get("codigo"),
                                              "credito": (l["credito"] or {}).get("codigo")}
        registro = {"empresa": EMP, "competencia": COMP, "estado": "FECHAMENTO_APROVADO",
                    "aprovacao": {"versoes_aprovadas": versoes, **({"fatos_aprovados": fatos} if aprovar_fatos else {})}}
        if mudar_depois:
            mudar_depois(registro, caminhos)
        return registro, caminhos

    def gerar(self, **k):
        registro, caminhos = self.montar(**k)
        return ex.gerar(SOL, registro, caminhos, PLANO)

    def recusa(self, trecho, **k):
        with self.assertRaises(ex.ErroExportacao) as ctx:
            self.gerar(**k)
        self.assertTrue(any(trecho in p for p in ctx.exception.problemas), ctx.exception.problemas)
        return ctx.exception.problemas


class Layout(Base):
    def test_partida_simples_uma_linha_por_lancamento(self):
        g = self.gerar()
        linhas = g["conteudo"].decode("cp1252").split("\r\n")
        self.assertEqual(linhas[-1], "")                       # termina em CRLF
        self.assertEqual(linhas[:-1], [
            "25/10/2026;1101;1121;6000;;RECEBIMENTO GAMA COMERCIO REF. NOTA FISCAL 102;1;;;",
            "31/10/2026;4105;2122;666,67;;PROVISAO DE 13 SALARIO COMPETENCIA 10/2026 REF. PR-2026-10;1;;;",
            "31/10/2026;1121;3101;4000;;RECEITA_SERVICOS REF. 103 COMPETENCIA 2026-10;1;;;"])
        self.assertNotIn(b"\n\n", g["conteudo"])
        self.assertEqual((g["linhas"], g["total"], g["por_origem"]), (3, "10666.67", {"Bancos": 1, "DP": 1, "Fiscal": 1}))
        a = g["auditoria"]
        self.assertIn("NÃO validada no Domínio", a["variante"])
        self.assertEqual((a["limite_complemento"], a["importado_no_dominio"], a["escriturado"]), ("NAO_COMPROVADO", False, False))
        # caminho técnico fica SÓ na auditoria
        self.assertEqual(a["linhas"][0]["arquivo"], "RECEBIDOS/2026-10/L-20261105-101010-abcdef/doc1.txt")
        self.assertNotIn(b"RECEBIDOS", g["conteudo"])

    def test_formato_de_valor_igual_ao_gerador_vgrow(self):
        for v, esperado in (("6000.00", "6000"), ("666.67", "666,67"), ("0.50", "0,5"), ("1234567.8", "1234567,8")):
            self.assertEqual(ex.fmt_valor(Decimal(v)), esperado)


class Valores(Base):
    def test_valor_ausente_invalido_nao_finito_ou_incompativel(self):
        for v in (None, "", "abc", "NaN", "Infinity", "1.234", "1e3", "-5.00", "0.00", "1.234,56", 6000.0, 6000):
            with self.subTest(v=v):
                self.res = resultados_base()
                self.res["BANCOS"][0]["valor"] = v
                self.recusa("valor")

    def test_valor_diferente_do_aprovado(self):
        def mudar(registro, caminhos):            # sha recalculado (resultado "aprovado"), mas o fato aprovado tinha outro valor
            registro["aprovacao"]["fatos_aprovados"]["BANCO:MOV-1"]["valor"] = "5999.99"
        self.recusa("diferentes dos aprovados", mudar_depois=mudar)


class Contas(Base):
    def test_conta_inexistente_sintetica_igual_ou_ausente(self):
        casos = (("debito", "9999", "inexistente"), ("debito", "11", "não é analítica"), ("credito", "1101", "mesma conta"),
                 ("debito", None, "ausente"))
        for lado, cod, trecho in casos:
            with self.subTest(lado=lado, cod=cod):
                self.res = resultados_base()
                self.res["BANCOS"][0][lado] = {"codigo": cod} if cod else None
                self.recusa(trecho)

    def test_plano_do_cadastro_local_e_do_markdown(self):
        base = self.tmp / "CLIENTES" / EMP
        (base / "PLANO-DE-CONTAS").mkdir(parents=True)
        (base / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md").write_text(
            "## Contas utilizadas\n| Código reduzido | Descrição | Grupo | Tipo |\n|---|---|---|---|\n| 1101 | BANCO | ATIVO | ANALITICA |\n"
            "| 11 | ATIVO CIRC | ATIVO | SINTÉTICA |\n", encoding="utf-8")
        with patch.dict(os.environ, {"AGENTES_PRIME_CLIENTES": str(self.tmp / "CLIENTES")}):
            p = ex.plano_empresa(EMP)
            self.assertEqual((p["1101"]["tipo"], p["11"]["tipo"]), ("ANALITICA", "SINTETICA"))
            (base / "empresa-local.json").write_text(json.dumps({"plano": [{"codigo": "4105", "tipo": "ANALITICA"}]}), encoding="utf-8")
            self.assertEqual(set(ex.plano_empresa(EMP)), {"4105"})          # cadastro local prevalece


class Historico(Base):
    def test_caminho_tecnico_nome_de_arquivo_ou_id_interno_recusados(self):
        for h in ("EVENTO RECEBIDOS/2026-10/L-20261104-171000-1788d8/05_resumo_folha_2026-10.txt",   # defeito do relatório (DP)
                  "PROVISAO 05_resumo_folha_2026-10.txt", "PAGTO C:\\pasta\\x", "PAGTO MOV-3F2A9C1B7D", "REF SOL-2026-000001",
                  "LOTE L-20261105-101010-abcdef"):
            with self.subTest(h=h):
                self.res = resultados_base()
                self.res["CONTABILIDADE_DP"][0]["historico"] = h
                self.recusa("histórico com caminho técnico")

    def test_historico_ausente_recusado(self):
        self.res["CONTABILIDADE_DP"][0]["historico"] = None
        self.recusa("histórico ausente")

    def test_barra_de_fato_contabil_aceita(self):
        self.res["CONTABILIDADE_DP"][0]["historico"] = "PROVISAO DE FERIAS COM 1/3 COMPETENCIA 10/2026 BANCO C/C"
        self.assertIn(b"FERIAS COM 1/3", self.gerar()["conteudo"])

    def test_caractere_fora_do_cp1252_recusado_sem_interrogacao(self):
        self.res["BANCOS"][0]["historico"] = "RECEBIMENTO → GAMA ✓"
        problemas = self.recusa("fora do cp1252")
        self.assertTrue(any("U+2192" in p for p in problemas))

    def test_transformacoes_explicitas_e_registradas(self):
        self.res["BANCOS"][0]["historico"] = "RECEBIMENTO;GAMA\r\nCOMERCIO  E\u0301 AÇÃO €"
        g = self.gerar()
        linha = g["conteudo"].decode("cp1252").split("\r\n")[0]
        self.assertEqual(linha.split(";")[5], "RECEBIMENTO,GAMA COMERCIO É AÇÃO €")
        self.assertEqual(len(linha.split(";")), 10)
        t = g["auditoria"]["linhas"][0]["transformacoes"]
        self.assertEqual(set(t), {"normalização Unicode NFC", "quebra de linha/tabulação → espaço", "';' (separador do layout) → ','",
                                  "espaços repetidos/nas pontas removidos"})
        self.assertEqual(g["auditoria"]["linhas"][0]["historico_original"], "RECEBIMENTO;GAMA\r\nCOMERCIO  E\u0301 AÇÃO €")
        self.assertNotIn(b"?", g["conteudo"])

    def test_sem_truncar_complemento(self):
        longo = "RECEBIMENTO " + "GAMA " * 80
        self.res["BANCOS"][0]["historico"] = longo
        g = self.gerar()
        self.assertEqual(g["auditoria"]["maior_complemento"], len(longo.strip()))
        self.assertIn(longo.strip().encode("cp1252"), g["conteudo"])


class DatasEFatos(Base):
    def test_data_ausente_nao_presumida(self):
        self.res["CONTABILIDADE_DP"][0]["data"] = None
        self.recusa("data do lançamento ausente")

    def test_data_fora_da_competencia(self):
        self.res["CONTABILIDADE_FISCAL"][0]["data"] = "2026-11-01"
        self.recusa("fora da competência")

    def test_identidade_ausente_repetida_ou_nao_aprovada(self):
        self.res["BANCOS"][0]["identidade"] = None
        self.recusa("sem identidade")
        self.res = resultados_base()
        self.res["CONTABILIDADE_FISCAL"][0]["identidade"] = "BANCO:MOV-1"
        self.recusa("repetida no mesmo TXT")

        def remover(registro, caminhos):
            del registro["aprovacao"]["fatos_aprovados"]["BANCO:MOV-1"]
        self.res = resultados_base()
        self.recusa("não consta entre os fatos aprovados", mudar_depois=remover)

        def sobrar(registro, caminhos):
            registro["aprovacao"]["fatos_aprovados"]["BANCO:MOV-EXTRA"] = {"valor": "1.00", "debito": "1101", "credito": "1121"}
        self.res = resultados_base()
        self.recusa("ausente(s) dos resultados", mudar_depois=sobrar)


class Integridade(Base):
    def test_resultado_alterado_depois_da_aprovacao(self):
        def alterar(registro, caminhos):
            p = Path(caminhos["BANCOS"])
            p.write_text(p.read_text(encoding="utf-8").replace("6000.00", "6000.01"), encoding="utf-8")
        self.recusa("diferente do aprovado (sha256)", mudar_depois=alterar)

    def test_outra_empresa_nao_aprovado_ou_nao_proposto(self):
        def outra(registro, caminhos):
            registro["empresa"] = "OUTRA"
        self.recusa("outra empresa", mudar_depois=outra)
        registro, caminhos = self.montar()
        registro["estado"] = "AGUARDANDO_SUPERVISOR"
        with self.assertRaises(ex.ErroExportacao):
            ex.gerar(SOL, registro, caminhos, PLANO)
        self.res["BANCOS"][0]["status"] = "INCOMPLETO"
        self.recusa("não proposto")

    def test_todos_os_problemas_listados_e_nada_gerado(self):
        self.res["BANCOS"][0]["valor"] = "abc"
        self.res["CONTABILIDADE_DP"][0]["historico"] = "x.pdf"
        self.res["CONTABILIDADE_FISCAL"][0]["debito"] = {"codigo": "9999"}
        problemas = self.recusa("valor")
        self.assertGreaterEqual(len(problemas), 3)


class Liberacao(Base):
    def test_empresa_real_bloqueada_e_destino_configuravel(self):
        clientes = self.tmp / "CLIENTES"
        (clientes / EMP).mkdir(parents=True)
        with patch.dict(os.environ, {"AGENTES_PRIME_CLIENTES": str(clientes), "AGENTES_PRIME_LIBERADOS": str(self.tmp / "LIB")}):
            self.assertFalse(ex.liberacao_permitida(EMP))                    # piloto real em SIMULAÇÃO: exportação bloqueada
            (clientes / EMP / "AMOSTRA-FICTICIA.json").write_text("{}", encoding="utf-8")
            self.assertTrue(ex.liberacao_permitida(EMP))
            self.assertEqual(ex.destino(EMP, COMP, SOL), self.tmp / "LIB" / EMP / COMP / f"lanctos_{EMP}_{COMP}_{SOL}.txt")


class SaidasDoFechamento(Base):
    """Excel dos lançamentos e balancete: mesma versão do TXT; abertura documentada; nunca total como saldo; sem sintéticas."""
    SALDOS = [{"conta": "1101", "abertura": "40000.00"}, {"conta": "1121", "abertura": "10000.00"}, {"conta": "2122", "abertura": "0.00"},
              {"conta": "3101", "abertura": "-500.00"}]

    def setUp(self):
        super().setUp()
        self.registro, caminhos = self.montar()
        self.registro["aprovacao"].update(em="2026-11-05T10:00:00-03:00", conciliacao_tentativa=1, conciliacao_sha256="c" * 64)
        self.g = ex.gerar(SOL, self.registro, caminhos, PLANO)
        self.sha = hashlib.sha256(self.g["conteudo"]).hexdigest()

    def test_excel_igual_ao_txt_linha_a_linha(self):
        import io
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(ex.gerar_excel(SOL, self.registro, self.g, PLANO, "arq.txt", self.sha)))
        linhas_txt = self.g["conteudo"].decode("cp1252").split(chr(13) + chr(10))[:-1]
        rows = [r for r in wb["Lançamentos"].iter_rows(min_row=2, values_only=True) if isinstance(r[0], int)]
        self.assertEqual(len(rows), len(linhas_txt))
        for r, l in zip(rows, linhas_txt):
            c = l.split(";")
            self.assertEqual((r[1].strftime("%d/%m/%Y"), r[2], r[4], ex.fmt_valor(Decimal(str(r[6]))), r[7]), (c[0], c[1], c[2], c[3], c[5]))
        ident = {r[0]: r[1] for r in wb["Identificação"].iter_rows(values_only=True)}
        self.assertEqual((ident["sha256 do TXT correspondente"], ident["Lançamentos"]), (self.sha, 3))
        self.assertIn("Não comprova importação nem escrituração no Domínio", ident["Aviso"])

    def test_balancete_integral_abertura_movimento_saldo(self):
        b = ex.calcular_balancete(self.g, self.SALDOS, dict(PLANO, **{"4105": {"tipo": "ANALITICA"}}), {"tipo": "INTEGRAL", "texto": "x"})
        c = {x["conta"]: x for x in b["contas"]}
        self.assertEqual((c["1101"]["abertura"], c["1101"]["debitos"], c["1101"]["creditos"], c["1101"]["saldo_final"]),
                         (Decimal("40000.00"), Decimal("6000.00"), Decimal("0"), Decimal("46000.00")))
        self.assertEqual(c["1121"]["saldo_final"], Decimal("10000.00") - Decimal("6000.00") + Decimal("4000.00"))
        self.assertEqual(c["3101"]["saldo_final"], Decimal("-4500.00"))                     # credora (abertura C + crédito)
        self.assertEqual((c["4105"]["abertura"], c["4105"]["saldo_final"], c["4105"]["situacao"]),
                         (None, None, "NAO_CALCULADO_ABERTURA_NAO_DOCUMENTADA"))         # nunca presume abertura zero
        self.assertEqual(b["total_debitos"], b["total_creditos"])
        self.assertEqual(b["total_debitos"], Decimal(self.g["total"]))                       # movimento ≠ saldo
        self.assertNotIn("11", c)                                                            # conta sintética não entra

    def test_balancete_complementar_sem_saldo_final(self):
        b = ex.calcular_balancete(self.g, self.SALDOS, PLANO, {"tipo": "COMPLEMENTAR", "texto": "há outra entrega"})
        self.assertTrue(all(x["saldo_final"] is None and x["situacao"] == "NAO_CALCULADO_ENTREGA_COMPLEMENTAR" for x in b["contas"]))
        self.assertIsNone(b["soma_saldos_finais"])

    def test_sintetica_com_movimento_ou_abertura_nao_duplica_total(self):
        saldos = self.SALDOS + [{"conta": "11", "abertura": "50000.00"}]                     # sintética = soma de 1101+1121
        b = ex.calcular_balancete(self.g, saldos, PLANO, {"tipo": "INTEGRAL", "texto": "x"})
        self.assertNotIn("11", [x["conta"] for x in b["contas"]])
        self.assertEqual(b["soma_aberturas"], Decimal("49500.00"))

    def test_planilha_do_balancete_identifica_abrangencia_e_simulacao(self):
        import io
        from openpyxl import load_workbook
        conteudo, _ = ex.gerar_balancete(SOL, self.registro, self.g, self.SALDOS, PLANO, {"tipo": "INTEGRAL", "texto": "única entrega"},
                                         "arq.txt", self.sha)
        wb = load_workbook(io.BytesIO(conteudo))
        ident = {r[0]: r[1] for r in wb["Identificação"].iter_rows(values_only=True)}
        self.assertTrue(ident["Abrangência"].startswith("INTEGRAL"))
        self.assertIn("SIMULAÇÃO", ident["Aviso"])
        self.assertIn("nunca presumido zero", ident["Saldos de abertura"])
        cab = next(wb["Balancete"].iter_rows(values_only=True))
        self.assertEqual(list(cab), ex.COLUNAS_BALANCETE)
        self.assertIn("não utilizada", ident["Base inicial"])


if __name__ == "__main__":
    unittest.main()
