"""Cenário 100% FICTÍCIO para documento complementar / pacote efetivo (usado pelas baterias de API e de tela).

Empresa inventada, CNPJ inventado (dígitos válidos), conta inventada; documentos gerados aqui:
- relatório financeiro XLSX (leiaute das baterias do Normalizador Financeiro);
- comprovante de pagamento em lote (PagFor) em PDF — NÃO é extrato;
- extrato no leiaute do Extrato Consolidado (textos das baterias do Normalizador Bancário) em PDF.
Nada real é lido. Requer ambiente isolado (TESTES/ambiente_isolado.py) criado ANTES de importar o servidor.
"""
import functools
import hashlib
import http.client
import io
import json
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "TESTES" / "FINANCEIRO"))
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import testar_normalizador_bancario as fx  # noqa: E402  (textos do extrato fictício)

EMPRESA = "EMPRESA-COMPLEMENTO-FICTICIA"
NOME = "EMPRESA COMPLEMENTO FICTICIA LTDA"
COMPETENCIA = "2026-10"
import amostra_ficticia  # noqa: E402  (mesmo plano de contas FICTÍCIO da amostra oficial)
PLANO = amostra_ficticia.PLANO


def cnpj(base12: str) -> str:
    def dv(n):
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(n):]
        r = sum(int(a) * b for a, b in zip(n, pesos)) % 11
        return "0" if r < 2 else str(11 - r)
    d = base12 + dv(base12)
    d += dv(d)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


CNPJ = cnpj("900900900001")


# ---------------------------------------------------------------- documentos fictícios
def _pdf(paginas) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    w = PdfWriter()
    fonte = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                              NameObject("/BaseFont"): NameObject("/Helvetica"), NameObject("/Encoding"): NameObject("/WinAnsiEncoding")})
    for texto in paginas:
        pg = w.add_blank_page(width=900, height=1200)
        pg[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(fonte)})})
        cmd = [b"BT /F1 9 Tf 20 1180 Td 14 TL"]
        for linha in texto.splitlines():
            lit = linha.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            cmd.append(b"(" + lit + b") Tj T*")
        cmd.append(b"ET")
        st = DecodedStreamObject()
        st.set_data(b"\n".join(cmd))
        pg[NameObject("/Contents")] = w._add_object(st)
    o = io.BytesIO()
    w.write(o)
    return o.getvalue()


def extrato_pdf() -> bytes:
    return _pdf([fx.P1, fx.P2, fx.P3, fx.P4])


def extrato_identificado_pdf() -> bytes:
    """Mesmo extrato fictício, com documento/contraparte identificáveis (como testar_integracao_bancaria.extrato_identificado):
    com o relatório fictício, todos os movimentos ficam CONCILIADOS → Financeiro conclui SEM bloqueio de lote."""
    p2 = (fx.P2.replace("TARIFA FICTICIA -  10,00-", "TARIFA FICTICIA 778899  10,00-")
          .replace("PIX RECEBIDO CLIENTE TESTE - 500,00", "PIX RECEBIDO OMEGA ALIMENTOS - 500,00")
          .replace("LANCAMENTO QUALQUER XYZ - 100,00", "LANCAMENTO QUALQUER XYZ 445566 100,00"))
    p3 = fx.P3.replace("PIX ENVIADO FORNECEDOR TESTE LTDA", "PIX ENVIADO SIGMA METALURGICA")
    return _pdf([fx.P1, p2, p3, fx.P4])


def pagfor_pdf(variante: str = "") -> bytes:
    return _pdf(["RELATORIO DE PAGAMENTOS FICTICIO\nCOMPROVANTE DE PAGAMENTO DE BOLETO\nPAGFOR - PAGAMENTO A FORNECEDORES\n"
                 f"BENEFICIARIO: FORNECEDOR TESTE LTDA\nPAGADOR: {NOME}\nAgência: 0001 Conta: 00.000001-0\nVALOR NOMINAL: 200,00\n"
                 f"DATA DO PAGAMENTO: 07/10/2026\nLINHA DIGITAVEL 00000.00000 00000.000000 00000.000000 0 00000000000000\n{variante}"])


def comprovante_pdf() -> bytes:
    return _pdf(["COMPROVANTE DE TRANSFERENCIA FICTICIO\nFAVORECIDO: SIGMA METALURGICA FICTICIA\nVALOR: 200,00\nDATA: 07/10/2026\n"
                 f"PAGADOR: {NOME}\n"])


@functools.lru_cache(maxsize=1)
def relatorio_xlsx() -> bytes:
    """Gerado UMA vez (o XLSX grava data/hora: duas gerações teriam SHA diferentes)."""
    from openpyxl import Workbook
    cab = ["Código", "Data de Vencimento", "Data de Quitação", "É Despesa", "Valor Entrada", "Valor Saída", "Valor Pago", "Situação",
           "Cliente.CPF/CNPJ", "Cliente.Razão Social", "Nº Documento", "Plano de Contas", "Banco", "Breve Descrição", "Empresa.CNPJ",
           "Data de Competência"]

    def linha(cod, quit, entrada, saida, doc=None, razao=None):
        return [cod, quit, quit, "Não" if entrada else "Sim", entrada, saida, entrada or saida, "Foi Pago", None, razao, doc,
                "Plano Teste", "Banco Teste", "Lançamento fictício", CNPJ, "10/2026"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatorio"
    for r in [cab, linha(1, "2026-10-01", None, "10,00", doc="778899"), linha(2, "2026-10-01", "500,00", None, razao="OMEGA ALIMENTOS LTDA"),
              linha(3, "2026-10-05", None, "90,00", doc="123456"), linha(4, "2026-10-07", "100,00", None, doc="445566"),
              linha(5, "2026-10-07", None, "200,00", razao="SIGMA METALURGICA LTDA")]:
        ws.append(r)
    o = io.BytesIO()
    wb.save(o)
    return o.getvalue()


# ---------------------------------------------------------------- empresa fictícia e cliente HTTP
def preparar_empresa(servidor, runtime):
    from empresas_local import Empresas
    import base64
    g = Empresas(RAIZ, runtime)
    g.cadastrar({"id": EMPRESA, "nome": NOME, "cnpj": CNPJ, "regime": "LUCRO PRESUMIDO (FICTICIO)"})
    csv = "codigo;classificacao;descricao;grupo;tipo\n" + "\n".join(f"{c};{k};{d};{gr};A" for c, k, d, gr in PLANO) + "\n"
    previa = g.previa(EMPRESA, {"nome": "plano-ficticio.csv", "conteudo": base64.b64encode(csv.encode()).decode()})
    g.plano(EMPRESA, {"token": previa["token"], "salvar": True, "confirmado": True})
    g.bancos(EMPRESA, {"contas": [{"banco": "033", "agencia": "0001", "conta": "00.000001-0", "titular": CNPJ, "contabil": "1101"}]})
    g.habilitar(EMPRESA, {"frase": f"CONFIRMO PILOTO {EMPRESA}"})


class Cliente:
    def __init__(self, porta):
        self.porta = porta
        _, _, corpo = self.http("GET", "/", token=False)
        self.token = re.search(r'name="prime-sessao" content="([^"]+)"', corpo.decode()).group(1)

    def http(self, metodo, rota, corpo=None, token=True, cab=None, bruto=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=600)
        h = {"Host": f"127.0.0.1:{self.porta}"}
        if token:
            h["X-Prime-Sessao"] = self.token
        if corpo is not None:
            h["Content-Type"] = "application/json"
        h.update(cab or {})
        c.request(metodo, rota, body=bruto if bruto is not None else (None if corpo is None else json.dumps(corpo)), headers=h)
        r = c.getresponse()
        dados = r.read()
        c.close()
        return r.status, dict(r.getheaders()), dados

    def j(self, metodo, rota, corpo=None, **kw):
        s, _, d = self.http(metodo, rota, corpo, **kw)
        try:
            return s, json.loads(d) if d else {}
        except ValueError:
            return s, {"bruto": d[:200]}

    def enviar(self, lote, nome, conteudo, sha=None):
        from urllib.parse import quote
        return self.j("PUT", f"/api/lotes/{lote}/arquivos", None, bruto=conteudo,
                      cab={"X-Nome-Arquivo": quote(nome), "X-Sha256": sha or hashlib.sha256(conteudo).hexdigest(),
                           "Content-Length": str(len(conteudo))})

    def abrir_sol(self, arquivos, instrucao="Conferência financeira fictícia de outubro/2026."):
        s, r = self.j("POST", "/api/lotes", {"empresa": EMPRESA, "competencia": COMPETENCIA, "instrucao": instrucao, "fluxo": "FINANCEIRO_BANCOS"})
        assert s == 201, (s, r)
        for nome, conteudo in arquivos:
            s2, r2 = self.enviar(r["lote"], nome, conteudo)
            assert s2 == 201, (s2, r2)
        s3, r3 = self.j("POST", f"/api/lotes/{r['lote']}/iniciar", {"conferencia_humana": True})
        assert s3 == 202, (s3, r3)
        return r3["sol"], r["lote"]

    def complementar(self, sol, nome, conteudo, motivo="Documento recebido depois (teste fictício)."):
        s, r = self.j("POST", f"/api/solicitacoes/{sol}/complementos", {"motivo": motivo})
        assert s == 201, (s, r)
        s2, r2 = self.enviar(r["lote"], nome, conteudo)
        assert s2 == 201, (s2, r2)
        return r["lote"]


def ocioso(servidor, registro_isolado, limite=600):
    fim = time.time() + limite
    while time.time() < fim:
        if not servidor.EM_EXECUCAO["sol"] and not servidor.EM_FINANCEIRO["sol"] and not any(
                str(s.get("estado", "")).endswith("_EM_ANDAMENTO") for s in registro_isolado()["solicitacoes"].values()):
            return True
        time.sleep(0.3)
    return False
