"""MINI FECHAMENTO FICTÍCIO COMPLETO (dados 100% FICTÍCIOS) — usado pelos testes da prévia/multiempresa e pela demonstração.

Empresas: as duas da amostra fictícia (API-LOCAL/amostra_ficticia.py: A = AMOSTRA-COMPLETA-FICTICIA, B = AMOSTRA-PENDENCIAS-FICTICIA).
Documentos do mês (competência 2026-10): os da amostra (extrato, relação, posição de títulos, saldos de abertura, folha,
encargos, provisões, NFS-e de saída, apurações, guia, comprovante, confirmações) + NF de ENTRADA (competência 09/2026, paga em
outubro), BALANCETE (PDF no layout de colunas), RAZÃO (CSV) e BOOK de conciliação (planilha) — todos gerados aqui.

O balancete/book/razão foram montados para mostrar TODOS os resultados da conciliação do balanço:
  banco, INSS, ISS, capital → CONCILIADA; clientes → DIVERGENTE (item sem NF no Fiscal); FGTS → COMPOSIÇÃO INCOMPLETA;
  fornecedores e IRRF → SEM COMPOSIÇÃO; tarifas → DIVERGENTE no razão × balancete (Contábil).
"""
import hashlib
import sys
from decimal import Decimal as D
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(RAIZ / "TESTES" / "BASE-INICIAL"))
import amostra_ficticia as af  # noqa: E402
import ficticios  # noqa: E402

COMPETENCIA = "2026-10"
A, B = af.EMPRESAS["A"]["id"], af.EMPRESAS["B"]["id"]

# (código, classificação, descrição, saldo anterior assinado D+, débitos, créditos) — analíticas; sintéticas somadas abaixo
ANALITICAS = [
    ("1101", "1.1.1.01", "BANCO FICTICIO C/C", "40000.00", "16000.00", "10545.00"),
    ("1121", "1.1.2.01", "CLIENTES", "10000.00", "10000.00", "16000.00"),
    ("2101", "2.1.1.01", "FORNECEDORES", "-3000.00", "3000.00", "1200.00"),
    ("2111", "2.1.2.01", "SALARIOS A PAGAR", "0", "8000.00", "8000.00"),
    ("2112", "2.1.2.02", "INSS A RECOLHER", "0", "0", "2800.00"),
    ("2113", "2.1.2.03", "FGTS A RECOLHER", "0", "0", "640.00"),
    ("2114", "2.1.2.04", "IRRF A RECOLHER", "0", "0", "300.00"),
    ("2131", "2.1.4.01", "ISS A RECOLHER", "-500.00", "500.00", "200.00"),
    ("2301", "2.3.1.01", "CAPITAL SOCIAL", "-46500.00", "0", "0"),
    ("3101", "3.1.1.01", "RECEITA DE SERVICOS", "0", "0", "10000.00"),
    ("3191", "3.1.9.01", "(-) ISS SOBRE SERVICOS", "0", "200.00", "0"),
    ("4101", "4.1.1.01", "SALARIOS", "0", "8000.00", "0"),
    ("4102", "4.1.1.02", "INSS PATRONAL", "0", "2100.00", "0"),
    ("4103", "4.1.1.03", "FGTS", "0", "640.00", "0"),
    ("4201", "4.2.1.01", "SERVICOS DE TERCEIROS", "0", "1200.00", "0"),
    ("4202", "4.2.1.02", "TARIFAS BANCARIAS", "0", "45.00", "0"),
]
SINTETICAS = [("1", "1", "ATIVO"), ("10", "1.1", "ATIVO CIRCULANTE"), ("11", "1.1.1", "DISPONIVEL"), ("12", "1.1.2", "CREDITOS"),
              ("2", "2", "PASSIVO"), ("20", "2.1", "PASSIVO CIRCULANTE"), ("21", "2.1.1", "FORNECEDORES E CONTAS A PAGAR"),
              ("22", "2.1.2", "OBRIGACOES TRABALHISTAS"), ("24", "2.1.4", "OBRIGACOES TRIBUTARIAS"), ("23", "2.3", "PATRIMONIO LIQUIDO"),
              ("230", "2.3.1", "CAPITAL"), ("3", "3", "RECEITAS"), ("30", "3.1", "RECEITA OPERACIONAL"), ("31", "3.1.1", "SERVICOS"),
              ("39", "3.1.9", "DEDUCOES"), ("4", "4", "DESPESAS"), ("40", "4.1", "DESPESAS COM PESSOAL"), ("41", "4.1.1", "FOLHA"),
              ("42", "4.2", "DESPESAS GERAIS"), ("421", "4.2.1", "SERVICOS E TARIFAS")]


def contas_balancete():
    """[(código, classificação, descrição, anterior, débitos, créditos, atual)] com sintéticas = soma das analíticas."""
    ana = [(c, k, d, D(a), D(db), D(cr), D(a) + D(db) - D(cr)) for c, k, d, a, db, cr in ANALITICAS]
    linhas = []
    for cod, k, desc in SINTETICAS:
        f = [x for x in ana if x[1].startswith(k + ".")]
        linhas.append((cod, k, desc, *(sum((x[i] for x in f), D("0")) for i in (3, 4, 5, 6))))
    todas = sorted(linhas + ana, key=lambda x: [int(p) for p in x[1].split(".")])
    return todas


def balancete_pdf(cenario="A") -> bytes:
    e = af.EMPRESAS[cenario]
    return ficticios.pdf_balancete(e["nome"], e["cnpj"], "01/10/2026", "31/10/2026", contas_balancete())


def razao_csv(cenario="A") -> bytes:
    """Razão contábil fictício (CSV ';'): partidas do mês; a tarifa foi digitada como 40,00 (divergência proposital com o balancete)."""
    partidas = [("03/10/2026", "1.1.1.01", "1.1.2.01", "TED RECEBIDA ALFA NF 101", "10000.00"),
                ("25/10/2026", "1.1.1.01", "1.1.2.01", "TED RECEBIDA GAMA NF 102", "6000.00"),
                ("25/10/2026", "1.1.2.01", "3.1.1.01", "NFS-E 102 GAMA", "6000.00"),
                ("28/10/2026", "1.1.2.01", "3.1.1.01", "NFS-E 103 ALFA", "4000.00"),
                ("31/10/2026", "3.1.9.01", "2.1.4.01", "ISS 10/2026 AP-ISS-2026-10", "200.00"),
                ("15/10/2026", "2.1.4.01", "1.1.1.01", "PAGTO ISS 09/2026", "500.00"),
                ("05/10/2026", "2.1.1.01", "1.1.1.01", "PIX BETA NF 555", "3000.00"),
                ("31/10/2026", "4.2.1.01", "2.1.1.01", "SERVICOS DE TERCEIROS OUTUBRO", "1200.00"),
                ("31/10/2026", "4.1.1.01", "2.1.2.01", "FOLHA 10/2026", "8000.00"),
                ("31/10/2026", "2.1.2.01", "2.1.2.02", "INSS SEGURADOS 10/2026", "700.00"),
                ("31/10/2026", "2.1.2.01", "2.1.2.04", "IRRF FOLHA 10/2026", "300.00"),
                ("30/10/2026", "2.1.2.01", "1.1.1.01", "PAGTO SALARIOS FP-2026-10", "7000.00"),
                ("31/10/2026", "4.1.1.02", "2.1.2.02", "INSS PATRONAL 10/2026", "2100.00"),
                ("31/10/2026", "4.1.1.03", "2.1.2.03", "FGTS 10/2026", "640.00"),
                ("31/10/2026", "4.2.1.02", "1.1.1.01", "TARIFA BANCARIA", "45.00")]
    linhas = ["DATA;CONTA;CONTRAPARTIDA;HISTORICO;DEBITO;CREDITO;DOCUMENTO;LOTE"]
    for n, (data, deb, cre, hist, v) in enumerate(partidas, 1):
        vd = "40,00" if deb == "4.2.1.02" else v.replace(".", ",")          # erro de digitação proposital (fictício)
        linhas.append(f"{data};{deb};{cre};{hist};{vd};;L{n:03d};{n}")
        linhas.append(f"{data};{cre};{deb};{hist};;{v.replace('.', ',')};L{n:03d};{n}")
    return ("\n".join(linhas) + "\n").encode("utf-8")


def book_xlsx(cenario="A") -> bytes:
    e = af.EMPRESAS[cenario]
    comps = [("BANCO", "1.1.1.01", "BANCO FICTICIO C/C", "ITENS EM ABERTO", [("31/10/2026", "EXTRATO", "Saldo conforme extrato 31/10/2026", 45455.0, 0, "")]),
             ("CLIENTES", "1.1.2.01", "CLIENTES", "ITENS EM ABERTO", [("28/10/2026", "NF 103", "ALFA SERVICOS FICTICIOS", 4000.0, 0, ""),
                                                                    ("30/10/2026", "NF 999", "OMEGA FICTICIA (sem NF no Fiscal)", 500.0, 0, "")]),
             ("INSS", "2.1.2.02", "INSS A RECOLHER", "ITENS EM ABERTO", [("31/10/2026", "GPS 10/2026", "INSS 10/2026", 0, 2800.0, "")]),
             ("FGTS", "2.1.2.03", "FGTS A RECOLHER", "ITENS EM ABERTO", [("31/10/2026", "", "", 0, 640.0, "")]),
             ("ISS", "2.1.4.01", "ISS A RECOLHER", "ITENS EM ABERTO", [("31/10/2026", "AP-ISS-2026-10", "ISS 10/2026", 0, 200.0, "")]),
             ("CAPITAL", "2.3.1.01", "CAPITAL SOCIAL", "ITENS EM ABERTO", [("01/01/2026", "CONTRATO", "Capital subscrito", 0, 46500.0, "")])]
    return ficticios.book_padrao(e["nome"], e["cnpj"], "OUTUBRO/2026", "31/10/2026", contas_balancete(), comps)


def nf_entrada_txt(cenario="A") -> bytes:
    e = af.EMPRESAS[cenario]
    return ("NFS-E - NOTA FISCAL DE SERVICOS ELETRONICA (FICTICIA)\n"
            f"PRESTADOR: {af.BETA[0]}\nCNPJ DO PRESTADOR: {af.BETA[1]}\n"
            f"TOMADOR: {e['nome']}\nCNPJ DO TOMADOR: {e['cnpj']}\n"
            "NUMERO DA NOTA: 555\nDATA DE EMISSAO: 20/09/2026\nCOMPETENCIA: 09/2026\n"
            "VALOR DOS SERVICOS: R$ 3.000,00\nVALOR TOTAL DA NOTA: R$ 3.000,00\n"
            "DISCRIMINACAO: SERVICOS DE MANUTENCAO (FICTICIO)\n").encode("utf-8")


def documentos(cenario="A") -> list:
    """[(nome, bytes)] do mini fechamento completo (amostra + documentos contábeis e NF de entrada)."""
    base = [(n, c.encode("utf-8") if isinstance(c, str) else c) for n, c in sorted(af.documentos(cenario).items())]
    base = [(n, c) for n, c in base if not n.endswith(".pdf") or "protegido" not in n]
    return base + [("19_nfse_555_beta_entrada.txt", nf_entrada_txt(cenario)), ("20_balancete_2026-10.pdf", balancete_pdf(cenario)),
                   ("21_razao_2026-10.csv", razao_csv(cenario)), ("22_book_conciliacao_2026-10.xlsx", book_xlsx(cenario))]


# ---------------------------------------------------------------- fluxo pela API (servidor em ambiente isolado)
def abrir_fechamento(cliente, empresa, docs, instrucao="Fechamento fictício de outubro/2026."):
    s, r = cliente.j("POST", "/api/lotes", {"empresa": empresa, "competencia": COMPETENCIA, "instrucao": instrucao, "fluxo": "FECHAMENTO"})
    assert s == 201, (s, r)
    for nome, conteudo in docs:
        s2, r2 = cliente.enviar(r["lote"], nome, conteudo)
        assert s2 == 201, (nome, s2, r2)
    s3, r3 = cliente.j("POST", f"/api/lotes/{r['lote']}/iniciar", {"conferencia_humana": True})
    assert s3 == 202, (s3, r3)
    return r3["sol"]


def preparar_fechamento(cliente, sol, parar=True, motivo="Preparar o fechamento fictício de outubro/2026."):
    s, r = cliente.j("POST", f"/api/solicitacoes/{sol}/reprocessar", {"confirmado": True, "motivo": motivo, "solicitante": "Supervisor"})
    assert s == 201, (s, r)
    return cliente.j("POST", f"/api/solicitacoes/{sol}/retomar-rota-financeira",
                     {"justificativa": "Preparar fechamento (fictício).", "confirmado": True, "parar_apos_financeiro": parar})


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
