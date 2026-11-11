"""Integração Documentos → Normalizador Financeiro → Financeiro (fonte AUXILIAR). Somente dados FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/FINANCEIRO/testar_integracao_normalizador.py
Não lê CLIENTES/, runtime nem SOL: o cadastro é simulado, a pasta CLIENTES aponta para um diretório temporário vazio e os
arquivos são dicionários no formato devolvido pelo extrator. Não executa Conciliação nem Contabilidade.
"""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "AGENTES/FINANCEIRO/ferramentas"))
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import conferencia_financeira as f
import documentos_local
import normalizador_financeiro as nf

SHA = "a" * 64
EMPRESA, SOL = "EMPRESA-FICTICIA", "SOL-2099-999999"
CAB = ["Código", "Data de Vencimento", "Data de Quitação", "É Despesa", "Valor Entrada", "Valor Saída", "Valor Pago",
       "Situação", "Cliente.CPF/CNPJ", "Cliente.Razão Social", "Nº Documento", "Plano de Contas", "Banco", "Breve Descrição",
       "Empresa.CNPJ", "Data de Competência"]


def lin(cod, despesa, entrada, saida, situacao="Foi Pago", quit="2026-10-12"):
    pago = entrada or saida
    return [cod, "2026-10-10", quit, despesa, entrada, saida, pago, situacao, "00.000.000/0001-00", "FORNECEDOR TESTE LTDA",
            f"DOC {cod}", "Despesas Gerais", "Banco Fictício 999", "Lançamento fictício", "00.000.000/0001-91", "10/2026"]


def relatorio(linhas=None, sha=SHA, **extra):
    linhas = linhas if linhas is not None else [CAB, lin(1, "Não", "100,00", None), lin(2, "Sim", None, "40,00"),
                                                lin(3, "Sim", None, "15,00", situacao="Em aberto", quit=None)]
    a = {"arquivo": "RECEBIDOS/2026-10/planilha-ficticia.xlsx", "extensao": ".xlsx", "sha256": sha, "leitura": "EXTRAIDO_PLANILHA",
         "marcacoes": ["ESTILO_XLSX_INVALIDO", "LEITOR_CALAMINE_FALLBACK"],
         "conteudo": {"abas": [{"aba": "Relatorio", "oculta": False, "protegida": False, "truncado": False, "celulas_mescladas": [],
                                "formulas_sem_valor": [], "linhas": [{"linha": i + 1, "valores": v} for i, v in enumerate(linhas)]}],
                      "links_externos": 0, "contem_macros": False}}
    a.update(extra)
    return a


def extrato():
    """Extrato PDF Santander FICTÍCIO (mesmo texto da bateria LOCAL/testar_extrato_santander.py)."""
    return {"arquivo": "extrato-ficticio.pdf", "extensao": ".pdf", "sha256": "b" * 64, "leitura": "EXTRAIDO_PDF",
            "conteudo": {"paginas_total": 2, "paginas": [
                {"pagina": 1, "texto": "Santander Empresas\nEMPRESA FICTICIA Agência: 1234 Conta: 11111-1\n"
                 "Períodos: 01/10/2026 a 31/10/2026 Data/Hora: 01/11/2026 as 10h00\n"
                 "Saldo disponível para uso: R$ 9.999,99\nData Histórico Documento Valor (R$) Saldo (R$)\n"
                 "20/10/2026 PIX RECEBIDO FICTICIO 12345678 50,00 950,00\n"
                 "10/10/2026 PAGAMENTO FICTICIO 0000000000 -20,00 900,00\n1/2"},
                {"pagina": 2, "texto": "10/10/2026 PAGAMENTO FICTICIO 87654321 -80,00 920,00\n"
                 "Saldo de ContaMax 9.999,99\nSaldo\nPosição em: 01/11/2026\n2/2"}]}}


CAD = {"cnpjs": ["00000000000191"], "contas": {f.chave_conta("033", "1234", "11111-1"): {
    "banco": "033", "agencia": "1234", "conta": "11111-1", "titular": "00000000000191", "situacao": "ATIVA"}},
       "cnpjs_outras_empresas": {}}

# Formato ANTERIOR do resultado (consumidores existentes: Coordenador, API, interface).
CHAVES_BLOQUEADO_V12 = {"agente", "versao", "procedimento", "sol", "empresa", "competencia", "modo", "executado_em", "aviso",
                        "bloqueio_lote", "ressalvas_documentos", "verificacao_extratos", "movimentos", "resumo",
                        "relacionados_sem_movimento", "ambiguas", "sugestoes", "duplicidades", "pendencias", "documentos",
                        "relacao", "ignorados", "limitacoes", "posicoes_titulos", "posicoes_titulos_resumo"}
RESUMO_BLOQUEADO_V12 = {"movimentos", "com_suporte", "comprovante_sem_natureza", "sem_suporte", "ambiguos", "transferencias_proprias",
                        "ja_escriturados", "com_proposta_anterior_simulacao", "relacionados_sem_movimento", "duplicidades",
                        "pendencias", "movimentos_encontrados"}
CHAVES_NOVAS = {"fonte_bancaria", "fonte_auxiliar_financeira", "movimentos_financeiros_auxiliares", "conciliacao_financeira"}


def conferir(arquivos, competencia="2026-10"):
    """Executa o caminho da conferência (carregar → preparar → triagem → montar) sem extrator, CLIENTES nem gravação."""
    with tempfile.TemporaryDirectory() as vazio, patch.dict(os.environ, {"AGENTES_PRIME_CLIENTES": vazio}), \
            patch.object(f, "cadastro", return_value=copy.deepcopy(CAD)):
        c = f.Conferencia(EMPRESA, competencia, SOL)
        c.carregar(arquivos)
        c.preparar_movimentos()
        bloqueios = c.triagem()
        if bloqueios:
            return c, c.montar_bloqueado(bloqueios, [])
        c.corresponder({})
        return c, c.montar({})


class IntegracaoNormalizador(unittest.TestCase):
    def test_00_fixture_classificada_por_documentos(self):
        self.assertEqual(documentos_local.encaminhamento(relatorio())["tipo"], f.TIPO_RELATORIO_FINANCEIRO)

    def test_fin_norm_01_relatorio_planilha_chama_normalizador(self):
        with patch.object(f.nf, "normalizar", wraps=nf.normalizar) as chamada:
            conferir([relatorio()])
        self.assertEqual(chamada.call_count, 1)
        # outra natureza documental (ex.: extrato) não passa pelo normalizador
        with patch.object(f.nf, "normalizar", wraps=nf.normalizar) as chamada:
            conferir([extrato()])
        self.assertEqual(chamada.call_count, 0)

    def test_fin_norm_02_movimentos_entram_como_fonte_auxiliar(self):
        _, r = conferir([relatorio()])
        aux = r["movimentos_financeiros_auxiliares"]
        self.assertEqual([(m["natureza"], m["valor"], m["fonte"]) for m in aux],
                         [("ENTRADA", "100.00", "FONTE_AUXILIAR_FINANCEIRA"), ("SAIDA", "40.00", "FONTE_AUXILIAR_FINANCEIRA")])
        res = r["fonte_auxiliar_financeira"]["resumo"]
        self.assertEqual((res["relatorios"], res["movimentos"], res["entradas"], res["saidas"], res["nao_realizadas"]), (1, 2, 1, 1, 1))
        self.assertEqual((res["total_entradas"], res["total_saidas"]), ("100.00", "40.00"))
        self.assertEqual(r["fonte_auxiliar_financeira"]["tipo"], "FONTE_AUXILIAR_FINANCEIRA")

    def test_fin_norm_03_fonte_auxiliar_nao_vira_extrato(self):
        c, r = conferir([relatorio()])
        self.assertEqual((c.extratos, c.movimentos, r["verificacao_extratos"], r["movimentos"]), ([], [], [], []))
        self.assertEqual({k: r["fonte_bancaria"][k] for k in ("tipo", "extratos_recebidos", "extratos_utilizaveis", "movimentos_bancarios")},
                         {"tipo": "EXTRATO_BANCARIO", "extratos_recebidos": 0, "extratos_utilizaveis": 0, "movimentos_bancarios": 0})
        self.assertEqual(r["fonte_bancaria"]["fontes_normalizadas"], [])
        self.assertIn("não substitui extrato", r["fonte_auxiliar_financeira"]["aviso"])

    def test_fin_norm_04_sem_extrato_continua_bloqueado(self):
        _, r = conferir([relatorio()])
        self.assertTrue(r["bloqueio_lote"])
        self.assertTrue(r["bloqueio_lote"][0].startswith("Nenhum extrato utilizável"))          # mensagem anterior preservada
        self.assertIn("nenhum extrato bancário utilizável foi localizado", r["bloqueio_lote"][1])
        self.assertTrue(r["aviso"].startswith("LOTE BLOQUEADO"))
        # 100% das linhas normalizadas não muda isso
        _, r = conferir([relatorio([CAB, lin(1, "Não", "100,00", None)])])
        self.assertEqual(r["fonte_auxiliar_financeira"]["relatorios"][0]["situacao"], "NORMALIZADO")
        self.assertTrue(r["bloqueio_lote"])

    def test_fin_norm_05_bancarios_e_auxiliares_separados(self):
        c, r = conferir([extrato(), relatorio()])
        self.assertEqual(r["bloqueio_lote"], [])
        self.assertEqual(len(r["movimentos"]), 3)                                               # só os do extrato
        self.assertTrue(all(m["id"].startswith("MOV-") for m in r["movimentos"]))
        self.assertEqual(len(r["movimentos_financeiros_auxiliares"]), 2)
        self.assertTrue(all(m["id"].startswith("RF-") for m in r["movimentos_financeiros_auxiliares"]))
        self.assertFalse({m["id"] for m in r["movimentos"]} & {m["id"] for m in r["movimentos_financeiros_auxiliares"]})
        self.assertEqual((r["fonte_bancaria"]["extratos_utilizaveis"], r["fonte_bancaria"]["movimentos_bancarios"]), (1, 3))
        self.assertEqual(r["resumo"]["movimentos"], 3)

    def test_fin_norm_06_rastreabilidade(self):
        _, r = conferir([relatorio()])
        for m in r["movimentos_financeiros_auxiliares"]:
            self.assertEqual((m["sha"], m["origem"]["arquivo"], m["origem"]["aba"]), (SHA, "RECEBIDOS/2026-10/planilha-ficticia.xlsx", "Relatorio"))
            self.assertEqual(m["origem"]["linha"], m["indice_linha"])
            self.assertRegex(m["id"], r"^RF-[0-9A-F]{12}$")
        self.assertEqual([m["indice_linha"] for m in r["movimentos_financeiros_auxiliares"]], [2, 3])
        rel = r["fonte_auxiliar_financeira"]["relatorios"][0]
        self.assertEqual((rel["origem"]["sha256"], rel["contrato"]), (SHA, "MOVIMENTOS_FINANCEIROS_NORMALIZADOS_V1"))

    def test_fin_norm_07_em_aberto_nao_entra(self):
        _, r = conferir([relatorio()])
        self.assertNotIn(4, [m["indice_linha"] for m in r["movimentos_financeiros_auxiliares"]])
        nr = r["fonte_auxiliar_financeira"]["relatorios"][0]["linhas_nao_realizadas"]
        self.assertEqual([(x["indice_linha"], x["situacao"], x["valor"]) for x in nr], [(4, "EM_ABERTO", "15.00")])

    def test_fin_norm_11_situacao_ausente_nao_entra(self):
        _, r = conferir([relatorio([CAB, lin(1, "Não", "100,00", None), lin(2, "Sim", None, "40,00", situacao=None)])])
        self.assertEqual([m["indice_linha"] for m in r["movimentos_financeiros_auxiliares"]], [2])
        nr = r["fonte_auxiliar_financeira"]["relatorios"][0]["linhas_nao_realizadas"]
        self.assertEqual([(x["indice_linha"], x["situacao"]) for x in nr], [(3, "AUSENTE")])
        self.assertIn("RELATORIO_FINANCEIRO_SITUACAO_AUSENTE", [p["tipo"] for p in r["pendencias"]])

    def test_fin_norm_08_falha_do_normalizador_vira_pendencia(self):
        casos = {"sem_sha": relatorio(sha=None), "cabecalho_ambiguo": relatorio([["Data de Vencimento", "Valor Pago", "Plano de Contas",
                                                                                    "Banco", "Empresa.CNPJ", "Valor Quitado"]]),
                 "truncado": relatorio(marcacoes=["LIMITE_EXCEDIDO"])}
        for nome, a in casos.items():
            _, r = conferir([a])
            tipos = [p["tipo"] for p in r["pendencias"]]
            self.assertTrue(any(t in ("RELATORIO_FINANCEIRO_NAO_NORMALIZADO", "DOCUMENTO_INCOMPLETO") for t in tipos), (nome, tipos))
            self.assertEqual(r["movimentos_financeiros_auxiliares"], [], nome)
            self.assertEqual(r["bloqueio_lote"][1:], [], nome)                 # não finge que processou
        with patch.object(f.nf, "normalizar", side_effect=RuntimeError("falha simulada")):
            c, r = conferir([relatorio()])
        self.assertIn("RELATORIO_FINANCEIRO_NAO_NORMALIZADO", [p["tipo"] for p in r["pendencias"]])
        self.assertEqual((c.extratos, r["fonte_auxiliar_financeira"]["relatorios"][0]["falha"]), ([], "RuntimeError"))
        # pendências de linha do normalizador chegam agrupadas ao Financeiro
        _, r = conferir([relatorio([CAB, lin(1, "Sim", "100,00", None), lin(2, "Sim", "5,00", None)])])
        self.assertEqual([p["tipo"] for p in r["pendencias"] if p["tipo"].startswith("RELATORIO_")], ["RELATORIO_FINANCEIRO_DIVERGENCIA_NATUREZA"])

    def test_fin_norm_09_formato_anterior_compativel(self):
        _, r = conferir([relatorio()])
        self.assertEqual((r["versao"], r["procedimento"]), ("1.5", "AGENTES/FINANCEIRO/PROCEDIMENTO.md v1.5"))
        self.assertEqual(set(r) - CHAVES_NOVAS, CHAVES_BLOQUEADO_V12)
        self.assertEqual(set(r["resumo"]), RESUMO_BLOQUEADO_V12)
        _, sem_relatorio = conferir([extrato()])
        _, com_relatorio = conferir([extrato(), relatorio()])
        self.assertEqual(set(sem_relatorio), set(com_relatorio))
        self.assertEqual(set(sem_relatorio["resumo"]), set(com_relatorio["resumo"]))
        self.assertEqual(sem_relatorio["movimentos"], com_relatorio["movimentos"])             # extrato idêntico com ou sem relatório
        self.assertEqual(json.loads(json.dumps(com_relatorio, ensure_ascii=False))["fonte_auxiliar_financeira"]["resumo"]["movimentos"], 2)

    def test_fin_norm_10_nenhum_lancamento_criado(self):
        with tempfile.TemporaryDirectory() as tmp:
            antes = sorted(Path(tmp).rglob("*"))
            with patch.object(f, "RAIZ", Path(tmp)):
                _, r = conferir([relatorio()])
            self.assertEqual(sorted(Path(tmp).rglob("*")), antes)                            # nada gravado
        texto = json.dumps(r, ensure_ascii=False)
        for chave in ("lancamentos", "propostas", "partidas", "debito_conta", "credito_conta"):
            self.assertNotIn(f'"{chave}"', texto)
        self.assertEqual(r["movimentos"], [])
        self.assertIn("não gera lançamento contábil", r["fonte_auxiliar_financeira"]["aviso"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
