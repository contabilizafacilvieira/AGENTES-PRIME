"""Documentos FICTÍCIOS para o fluxo Financeiro → Contabilidade/Bancos (testes e primeiro teste pela interface).

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/FINANCEIRO/gerar_fixtures_financeiro.py <pasta de destino>
Gera, na pasta indicada, um lote da EMPRESA-DEMO-FINANCEIRO (competência 09/2026) com todos os cenários:
pagamento com suporte completo, sem suporte, comprovante sem natureza, item da relação sem liquidação, pagamento
agrupado e pagamentos parciais, correspondência ambígua, extratos sobrepostos, transferência entre contas próprias,
obrigação já contabilizada (DARF), tarifa e crédito sem documento, conta de outra empresa, comprovante de outra empresa
e documento digitalizado (ilegível sem OCR). Nenhum dado pertence a cliente real; CNPJs sem dígito verificador válido.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "TESTES" / "T004"))
from gerar_fixtures import dv_chave  # noqa: E402

EMPRESA = "EMPRESA DEMONSTRACAO FINANCEIRO FICTICIA LTDA"
CNPJ = "44.444.444/0001-44"
ALFA = ("ALFA SUPRIMENTOS FICTICIA LTDA", "22.222.222/0001-22")
BETA = ("BETA SERVICOS FICTICIA LTDA", "33.333.333/0001-33")
DELTA = ("DELTA COMERCIO FICTICIA LTDA", "55.555.555/0001-55")
EPSILON = ("EPSILON INDUSTRIA FICTICIA LTDA", "66.666.666/0001-66")
GAMA = ("GAMA LOGISTICA FICTICIA LTDA", "77.777.777/0001-77")
NS = "http://www.portalfiscal.inf.br/nfe"


def so_digitos(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def ofx(banco, agencia, conta, inicio, fim, transacoes, saldo_final) -> bytes:
    trn = "".join(f"<STMTTRN><TRNTYPE>{t}<DTPOSTED>{d}120000[-3:BRT]<TRNAMT>{v}<FITID>{f}<MEMO>{m}</STMTTRN>\n"
                  for t, d, v, f, m in transacoes)
    return ("OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\nENCODING:USASCII\n\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL\n"
            f"<BANKACCTFROM><BANKID>{banco}<BRANCHID>{agencia}<ACCTID>{conta}<ACCTTYPE>CHECKING</BANKACCTFROM>\n"
            f"<BANKTRANLIST><DTSTART>{inicio}<DTEND>{fim}\n{trn}</BANKTRANLIST>\n"
            f"<LEDGERBAL><BALAMT>{saldo_final}<DTASOF>{fim}</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>\n").encode("ascii")


def nfe(numero: int, emitente: tuple, valor: str, data: str) -> bytes:
    cnpj_emit = so_digitos(emitente[1])
    c43 = f"352609{cnpj_emit}55001{numero:09d}1{12345678:08d}"
    chave = c43 + dv_chave(c43)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<nfeProc xmlns="{NS}" versao="4.00"><NFe xmlns="{NS}">'
            f'<infNFe Id="NFe{chave}" versao="4.00"><ide><cUF>35</cUF><cNF>12345678</cNF><natOp>VENDA FICTICIA</natOp><mod>55</mod>'
            f"<serie>1</serie><nNF>{numero}</nNF><dhEmi>{data}T10:00:00-03:00</dhEmi><tpNF>1</tpNF><tpEmis>1</tpEmis>"
            f"<cDV>{chave[-1]}</cDV><tpAmb>2</tpAmb></ide><emit><CNPJ>{cnpj_emit}</CNPJ><xNome>{emitente[0]}</xNome><IE>ISENTO</IE>"
            f"<CRT>3</CRT></emit><dest><CNPJ>{so_digitos(CNPJ)}</CNPJ><xNome>{EMPRESA}</xNome><indIEDest>9</indIEDest></dest>"
            f'<det nItem="1"><prod><cProd>P1</cProd><cEAN>SEM GTIN</cEAN><xProd>PRODUTO FICTICIO</xProd><NCM>00000000</NCM>'
            f"<CFOP>5102</CFOP><uCom>UN</uCom><qCom>1.0000</qCom><vUnCom>{valor}</vUnCom><vProd>{valor}</vProd></prod><imposto>"
            f"<ICMS><ICMS00><orig>0</orig><CST>00</CST><modBC>3</modBC><vBC>{valor}</vBC><pICMS>0.00</pICMS><vICMS>0.00</vICMS>"
            f"</ICMS00></ICMS></imposto></det><total><ICMSTot><vBC>{valor}</vBC><vICMS>0.00</vICMS><vST>0.00</vST><vProd>{valor}</vProd>"
            f"<vFrete>0.00</vFrete><vSeg>0.00</vSeg><vDesc>0.00</vDesc><vII>0.00</vII><vIPI>0.00</vIPI><vPIS>0.00</vPIS>"
            f"<vCOFINS>0.00</vCOFINS><vOutro>0.00</vOutro><vNF>{valor}</vNF></ICMSTot></total>"
            f"<infAdic><infCpl>DOCUMENTO FICTICIO PARA TESTE</infCpl></infAdic></infNFe></NFe>"
            f'<protNFe versao="4.00"><infProt><tpAmb>2</tpAmb><chNFe>{chave}</chNFe><dhRecbto>{data}T10:00:05-03:00</dhRecbto>'
            f"<nProt>135260000000001</nProt><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe></nfeProc>\n").encode("utf-8")


def comprovante(favorecido, data, valor, ident_rotulo, ident, referente=None, pagador_cnpj=CNPJ, pagador=EMPRESA) -> bytes:
    linhas = ["COMPROVANTE DE PAGAMENTO - DOCUMENTO FICTICIO", f"PAGADOR: {pagador} CNPJ {pagador_cnpj}",
              f"FAVORECIDO: {favorecido[0]}"]
    if favorecido[1]:
        linhas.append(f"CNPJ DO FAVORECIDO: {favorecido[1]}")
    linhas += [f"DATA DO PAGAMENTO: {data}", f"VALOR PAGO: R$ {valor}", f"{ident_rotulo}: {ident}"]
    if referente:
        linhas.append(f"REFERENTE A: {referente}")
    return ("\r\n".join(linhas) + "\r\n").encode("cp1252")


def imagem_ilegivel() -> bytes:
    """PNG fictício de ruído (nenhum texto reconhecível): exige a biblioteca Pillow; falha claramente se ausente."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(f"Fixture obrigatória indisponível: Pillow ausente para gerar 15_recibo_digitalizado.png ({exc}).")
    import io
    import random
    gerador = random.Random(15)
    im = Image.new("L", (240, 120))
    im.putdata([gerador.randrange(256) for _ in range(240 * 120)])
    saida = io.BytesIO()
    im.save(saida, format="PNG")
    return saida.getvalue()


def gerar(destino: Path) -> list:
    destino.mkdir(parents=True, exist_ok=True)
    conta_a = [
        ("DEBIT", "20260905", "-1500.00", "F001", "PAGTO FORNECEDOR ALFA"),
        ("DEBIT", "20260908", "-320.00", "F002", "PAGAMENTO DIVERSOS"),
        ("DEBIT", "20260910", "-800.00", "F003", "PIX ENVIADO BETA"),
        ("DEBIT", "20260912", "-700.00", "F004", "PAGTO DELTA LOTE"),
        ("CREDIT", "20260914", "3000.00", "F012", "PIX RECEBIDO CLIENTE"),
        ("DEBIT", "20260915", "-1000.00", "F005", "PAGTO EPSILON PARC 1"),
        ("DEBIT", "20260918", "-250.00", "F007", "PIX ENVIADO"),
        ("DEBIT", "20260918", "-250.00", "F008", "PIX ENVIADO"),
        ("XFER", "20260922", "-5000.00", "F009", "TRANSF ENTRE CONTAS P/ 0001 98765-4"),
        ("DEBIT", "20260925", "-1000.00", "F006", "PAGTO EPSILON PARC 2"),
        ("DEBIT", "20260926", "-900.00", "F010", "PAGTO DARF"),
        ("FEE", "20260930", "-15.90", "F011", "TARIFA PACOTE SERVICOS"),
    ]
    arquivos = {
        "01_extrato_001_11111-1_2026-09.ofx": ofx("001", "1234", "11111-1", "20260901", "20260930", conta_a, "10000.00"),
        # segundo extrato da mesma conta, período sobreposto (01 a 10/09): F001 e F002 não podem ser contados duas vezes
        "02_extrato_001_11111-1_ate_10-09.ofx": ofx("001", "1234", "11111-1", "20260901", "20260910", conta_a[:2], "12180.00"),
        "03_extrato_237_98765-4_2026-09.csv": (
            "conta;titular_cnpj;data;tipo;historico;identificador;valor;saldo\r\n"
            f"237-0001-98765-4;{CNPJ};01/09/2026;SALDO_INICIAL;SALDO ANTERIOR;;;1.000,00\r\n"
            f"237-0001-98765-4;{CNPJ};22/09/2026;MOVIMENTO;TRANSF RECEBIDA DE 1234 11111-1;TR9;5.000,00;6.000,00\r\n"
            f"237-0001-98765-4;{CNPJ};30/09/2026;SALDO_FINAL;SALDO FINAL;;;6.000,00\r\n").encode("cp1252"),
        "04_relacao_pagamentos_2026-09.csv": (
            "data_pagamento;favorecido;cnpj_cpf;valor;documentos;conta_pagadora;pagamento_id;obrigacao_contabilizada;natureza\r\n"
            f"05/09/2026;{ALFA[0]};{ALFA[1]};1.500,00;NF 1001;001-1234-11111-1;;SIM;compra de mercadorias\r\n"
            f"12/09/2026;{DELTA[0]};{DELTA[1]};400,00;NF 2001;001-1234-11111-1;G1;SIM;compra\r\n"
            f"12/09/2026;{DELTA[0]};{DELTA[1]};300,00;NF 2002;001-1234-11111-1;G1;SIM;compra\r\n"
            f"15/09/2026;{EPSILON[0]};{EPSILON[1]};1.000,00;NF 3001;001-1234-11111-1;;SIM;parcela 1/2\r\n"
            f"25/09/2026;{EPSILON[0]};{EPSILON[1]};1.000,00;NF 3001;001-1234-11111-1;;SIM;parcela 2/2\r\n"
            f"20/09/2026;{GAMA[0]};{GAMA[1]};450,00;NF 4001;001-1234-11111-1;;SIM;frete\r\n"
            f"26/09/2026;RECEITA FEDERAL (DARF);;900,00;DARF 0909;001-1234-11111-1;;SIM;IRRF\r\n").encode("cp1252"),
        "05_comprovante_alfa_05-09.txt": comprovante(ALFA, "05/09/2026", "1.500,00", "AUTENTICACAO", "AUT0001ALFA", "NF 1001"),
        "06_nfe_1001_alfa.xml": nfe(1001, ALFA, "1500.00", "2026-09-01"),
        "07_comprovante_beta_10-09.txt": comprovante(BETA, "10/09/2026", "800,00", "E2E", "E2E0003BETA"),
        "08_comprovante_pix_250_18-09.txt": comprovante(("ZETA PRESTADOR FICTICIO", None), "18/09/2026", "250,00", "ID DA TRANSACAO", "PIX250"),
        "09_nfe_2001_delta.xml": nfe(2001, DELTA, "400.00", "2026-09-02"),
        "10_nfe_2002_delta.xml": nfe(2002, DELTA, "300.00", "2026-09-02"),
        "11_nfe_3001_epsilon.xml": nfe(3001, EPSILON, "2000.00", "2026-09-03"),
        "12_darf_0909.txt": ("DOCUMENTO DE ARRECADACAO DE RECEITAS FEDERAIS - DARF (FICTICIO)\r\n"
                             f"CONTRIBUINTE: {EMPRESA} CNPJ {CNPJ}\r\nNUMERO DO DOCUMENTO: 0909\r\nPERIODO DE APURACAO: 08/2026\r\n"
                             "VENCIMENTO: 26/09/2026\r\nVALOR TOTAL: R$ 900,00\r\n").encode("cp1252"),
        # isolamento: conta de outro titular e comprovante de outra empresa cadastrada (EMPRESA-ISOLAMENTO)
        "13_extrato_341_55555-5_outra_empresa.ofx": ofx("341", "9999", "55555-5", "20260901", "20260930",
                                                        [("DEBIT", "20260920", "-450.00", "X001", "PAGTO GAMA")], "100.00"),
        "14_comprovante_outra_empresa.txt": comprovante(GAMA, "20/09/2026", "450,00", "AUTENTICACAO", "AUTOUTRA",
                                                        "NF 4001", pagador_cnpj="99.999.999/9999-99", pagador="OUTRA EMPRESA FICTICIA"),
    }
    # imagem sem texto legível (gerada aqui; antes vinha de CLIENTES/EMPRESA-TESTE e era omitida em silêncio quando ausente)
    arquivos["15_recibo_digitalizado.png"] = imagem_ilegivel()
    for nome, dados in arquivos.items():
        (destino / nome).write_bytes(dados)
    return sorted(arquivos)


def gerar_incompleto(destino: Path) -> list:
    """Extrato da conta 237 que não cobre o mês (até 20/09) e cujo saldo final não fecha com os movimentos."""
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "01_extrato_237_incompleto.csv").write_bytes((
        "conta;titular_cnpj;data;tipo;historico;identificador;valor;saldo\r\n"
        f"237-0001-98765-4;{CNPJ};01/09/2026;SALDO_INICIAL;SALDO ANTERIOR;;;1.000,00\r\n"
        f"237-0001-98765-4;{CNPJ};05/09/2026;MOVIMENTO;DEPOSITO;D1;200,00;1.200,00\r\n"
        f"237-0001-98765-4;{CNPJ};20/09/2026;SALDO_FINAL;SALDO FINAL;;;1.350,00\r\n").encode("cp1252"))
    return ["01_extrato_237_incompleto.csv"]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    alvo = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not alvo:
        raise SystemExit("Informe a pasta de destino.")
    print("\n".join(gerar(alvo)))
