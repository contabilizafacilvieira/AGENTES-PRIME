"""Amostra fictícia do percurso completo (Documentos → Financeiro/DP/Fiscal → Contabilidade → Conciliação → Supervisor).

Somente dados FICTÍCIOS. Nada é criado ao iniciar o aplicativo: a preparação é explícita (Empresas → "Preparar amostra fictícia"
na interface, ou `python -I API-LOCAL/amostra_ficticia.py preparar`). Atua SOMENTE sobre as duas empresas abaixo; uma versão
anterior delas é movida para o runtime (preservada), nunca apagada. Os documentos de cada cenário ficam em
TESTES/AMOSTRA-COMPLETA/CENARIO-A e CENARIO-B (gerados por `gerar_documentos`). Passo a passo: TESTES/AMOSTRA-COMPLETA/LEIA-ME.md.
"""
import base64
import datetime as dt
import io
import json
import os
import shutil
import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
def clientes():
    """Pasta CLIENTES (avaliada a cada uso: AGENTES_PRIME_CLIENTES em testes isolados; RAIZ/CLIENTES em produção)."""
    return Path(os.environ.get("AGENTES_PRIME_CLIENTES") or RAIZ / "CLIENTES")
PASTA_AMOSTRA = RAIZ / "TESTES" / "AMOSTRA-COMPLETA"
MARCA = "AMOSTRA-FICTICIA.json"           # identifica pasta criada por esta preparação (nada mais é movido)
COMPETENCIA = "2026-10"

EMPRESAS = {
    "A": {"id": "AMOSTRA-COMPLETA-FICTICIA", "nome": "EMPRESA AMOSTRA COMPLETA FICTICIA LTDA", "cnpj": "90.010.010/0001-09",
          "conta": "55555-5"},
    "B": {"id": "AMOSTRA-PENDENCIAS-FICTICIA", "nome": "EMPRESA AMOSTRA PENDENCIAS FICTICIA LTDA", "cnpj": "90.020.020/0001-17",
          "conta": "66666-6"},
}
ALFA = ("ALFA SERVICOS FICTICIOS LTDA", "90.030.030/0001-33")
BETA = ("BETA SERVICOS FICTICIOS LTDA", "90.040.040/0001-50")
GAMA = ("GAMA COMERCIO FICTICIO LTDA", "90.050.050/0001-76")
PREFEITURA = ("PREFEITURA MUNICIPAL FICTICIA", "90.060.060/0001-92")
OUTRA = ("OUTRA EMPRESA FICTICIA LTDA", "90.070.070/0001-09")

PLANO = [  # código, classificação, descrição, grupo
    ("1101", "1.1.1.01", "BANCO FICTICIO C/C", "ATIVO"), ("1121", "1.1.2.01", "CLIENTES", "ATIVO"),
    ("2101", "2.1.1.01", "FORNECEDORES", "PASSIVO"), ("2111", "2.1.2.01", "SALARIOS A PAGAR", "PASSIVO"),
    ("2112", "2.1.2.02", "INSS A RECOLHER", "PASSIVO"), ("2113", "2.1.2.03", "FGTS A RECOLHER", "PASSIVO"),
    ("2114", "2.1.2.04", "IRRF A RECOLHER", "PASSIVO"), ("2121", "2.1.3.01", "PROVISAO DE FERIAS", "PASSIVO"),
    ("2122", "2.1.3.02", "PROVISAO DE 13 SALARIO", "PASSIVO"), ("2131", "2.1.4.01", "ISS A RECOLHER", "PASSIVO"),
    ("2132", "2.1.4.02", "PIS A RECOLHER", "PASSIVO"), ("2133", "2.1.4.03", "COFINS A RECOLHER", "PASSIVO"),
    ("3101", "3.1.1.01", "RECEITA DE SERVICOS", "RECEITA"), ("3191", "3.1.9.01", "(-) ISS SOBRE SERVICOS", "RECEITA"),
    ("3192", "3.1.9.02", "(-) PIS SOBRE FATURAMENTO", "RECEITA"), ("3193", "3.1.9.03", "(-) COFINS SOBRE FATURAMENTO", "RECEITA"),
    ("4101", "4.1.1.01", "SALARIOS", "DESPESA"), ("4102", "4.1.1.02", "INSS PATRONAL", "DESPESA"),
    ("4103", "4.1.1.03", "FGTS", "DESPESA"), ("4104", "4.1.1.04", "FERIAS", "DESPESA"),
    ("4105", "4.1.1.05", "13 SALARIO", "DESPESA"), ("4201", "4.2.1.01", "SERVICOS DE TERCEIROS", "DESPESA"),
    ("4202", "4.2.1.02", "TARIFAS BANCARIAS", "DESPESA"),
]
ABERTURA = {"1101": ("40000.00", "D"), "1121": ("10000.00", "D"), "2101": ("3000.00", "C"), "2131": ("500.00", "C")}


def br(v) -> str:
    v = Decimal(str(v)).quantize(Decimal("0.01"))
    inteiro, dec = f"{abs(v):.2f}".split(".")
    grupos = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return ("-" if v < 0 else "") + ".".join(grupos) + "," + dec


# ---------------------------------------------------------------- regras documentadas da amostra (por empresa)

FONTE = "Amostra fictícia documentada (TESTES/AMOSTRA-COMPLETA/LEIA-ME.md)"
ESCOPO = "SOMENTE a empresa fictícia da amostra; não é regra aprovada de nenhum cliente"


def teste(**dados) -> dict:
    """Regra de TESTE identificada (governança): vale só em empresa com o marcador AMOSTRA-FICTICIA.json; não é aprovação."""
    return dict(dados, situacao="TESTE_FICTICIO", origem=FONTE, versao=1, competencia_desde=COMPETENCIA, escopo=ESCOPO)


def regras_bancos(e: dict, cenario: str) -> str:
    fonte = FONTE
    aprov = "Regra de TESTE da amostra fictícia (não é aprovação do Supervisor)"
    # Cenário B: a regra da liquidação do ISS aponta, DE PROPÓSITO, uma conta incompatível (DESPESA para LIQUIDACAO_OBRIGACAO,
    # que exige PASSIVO) — caso "conta incompatível"; o pagamento tem guia como suporte, então a decisão do caso pode corrigi-lo.
    iss = "4202" if cenario == "B" else "2131"
    linhas = [
        ("RB-001", f"direcao=CREDITO; favorecido_cnpj={ALFA[1]}; obrigacao_contabilizada=SIM", "RECEBIMENTO", "1121", "NAO", "RECEBIMENTO TITULO {favorecido}"),
        ("RB-002", f"direcao=DEBITO; favorecido_cnpj={BETA[1]}; obrigacao_contabilizada=SIM", "LIQUIDACAO_OBRIGACAO", "2101", "NAO", "PAGTO TITULO {favorecido}"),
        ("RB-003", "direcao=DEBITO; suporte=GUIA; historico_contem=ISS", "LIQUIDACAO_OBRIGACAO", iss, "SIM", "PAGTO ISS {documento}"),
        ("RB-004", "direcao=CREDITO; suporte=NOTA_FISCAL", "RECEBIMENTO", "1121", "SIM", "RECEBIMENTO {documento} {favorecido}"),
        ("RB-005", "direcao=DEBITO; suporte=FOLHA; historico_contem=SALARIOS", "LIQUIDACAO_OBRIGACAO", "2111", "SIM", "PAGTO SALARIOS {documento}"),
        ("RB-006", "direcao=DEBITO; historico_contem=TARIFA", "DESPESA", "4202", "NAO", "TARIFA BANCARIA {data}"),
    ]
    corpo = "\n".join(f"| {r} | 1 | {c} | {t} | {conta} | {s} | {h} | {fonte} | TESTE_FICTICIO | {aprov} |" for r, c, t, conta, s, h in linhas)
    return (f"# Regras bancárias — {e['id']} (AMOSTRA FICTÍCIA)\n\nRegras documentadas somente para esta amostra fictícia; não valem "
            "para nenhuma outra empresa.\n\n## Regras\n| Regra | Versão | Condições | Tipo | Contrapartida | Exige suporte | Histórico | "
            "Origem | Situação | Aprovação |\n|---|---|---|---|---|---|---|---|---|---|\n" + corpo + "\n")


def politica_data_teste() -> dict:
    """Configuração FICTÍCIA explícita da amostra: data do lançamento = último dia da competência. Não é decisão do Supervisor
    para nenhum cliente (nem para a State); empresas reais precisam definir e confirmar a própria política."""
    return teste(politica="ULTIMO_DIA_COMPETENCIA")


def regras_fiscais(e: dict) -> dict:
    return {"contrato": "REFERENCIAS_FISCAIS_V1", "empresa": e["id"], "cnpj": e["cnpj"].replace(".", "").replace("/", "").replace("-", ""),
            "competencia_desde": COMPETENCIA, "data_lancamento": politica_data_teste(),
            "referencias": {"RECEITA_SERVICOS": teste(debito="1121", credito="3101", fonte=FONTE),
                            "ISS": teste(debito="3191", credito="2131", fonte=FONTE),
                            "PIS": teste(debito="3192", credito="2132", fonte=FONTE),
                            "COFINS": teste(debito="3193", credito="2133", fonte=FONTE)}}


def regras_conciliacao(e: dict) -> dict:
    """Exigências de TESTE da Conciliação da amostra (posições e confirmações exigidas). Não valem para empresa real."""
    return {"contrato": "EXIGENCIAS_CONCILIACAO_V1", "empresa": e["id"],
            "exigencias": {"POSICAO_TITULOS_PAGAR": teste(exigencia="EXIGIDA"), "POSICAO_TITULOS_RECEBER": teste(exigencia="EXIGIDA"),
                           "CONFIRMACAO_TERCEIROS": teste(exigencia="EXIGIDA")}}


def regras_dp(e: dict, valido: bool = True) -> str:
    ref = {"FOLHA_PROVENTOS": ("4101", "2111"), "RETENCAO_INSS": ("2111", "2112"), "RETENCAO_IRRF": ("2111", "2114"),
           "ENCARGO_INSS_EMPRESA": ("4102", "2112"), "ENCARGO_FGTS": ("4103", "2113"), "PROVISAO_FERIAS": ("4104", "2121"),
           "PROVISAO_13": ("4105", "2122")}
    dados = {"contrato": "REFERENCIAS_DP_V1", "empresa": e["id"], "cnpj": e["cnpj"], "competencia_desde": COMPETENCIA,
             "data_lancamento": politica_data_teste(),
             "referencias": {k: teste(debito=d, credito=c, fonte=FONTE) for k, (d, c) in ref.items()}}
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    # Cenário B: referências do DP com formato inválido (JSON truncado) — falha REAL de configuração da Contabilidade/DP,
    # corrigida pela ação "Aplicar correção das referências do DP da amostra B" e retomada da etapa pela interface.
    return texto if valido else texto[: len(texto) // 2]


# ---------------------------------------------------------------- preparação explícita das empresas

def preparar(runtime: Path, recriar: bool = False, cenarios=None) -> dict:
    sys.path.insert(0, str(RAIZ / "API-LOCAL"))
    from empresas_local import Empresas
    gestor = Empresas(RAIZ, runtime)
    feitas = []
    for cenario, e in EMPRESAS.items():
        if cenarios and cenario not in cenarios:
            continue                                  # ex.: demonstração só com o cenário A
        base = clientes() / e["id"]
        if base.exists():
            if not (base / MARCA).is_file():
                raise ValueError(f"CLIENTES/{e['id']} existe e não foi criada pela preparação da amostra; nada foi alterado.")
            if not recriar:
                feitas.append({"empresa": e["id"], "situacao": "JA_PREPARADA"})
                continue
            destino = Path(runtime) / "amostra-anterior" / f"{e['id']}-{dt.datetime.now():%Y%m%d-%H%M%S}"
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(base), str(destino))          # preservada fora de CLIENTES; nunca apagada
        gestor.cadastrar({"id": e["id"], "nome": e["nome"], "cnpj": e["cnpj"], "regime": "LUCRO PRESUMIDO (FICTICIO)"})
        csv = "codigo;classificacao;descricao;grupo;tipo\n" + "\n".join(f"{c};{k};{d};{g};A" for c, k, d, g in PLANO) + "\n"
        previa = gestor.previa(e["id"], {"nome": "plano-amostra.csv", "conteudo": base64.b64encode(csv.encode()).decode()})
        gestor.plano(e["id"], {"token": previa["token"], "salvar": True, "confirmado": True})
        gestor.bancos(e["id"], {"contas": [{"banco": "001", "agencia": "1234", "conta": e["conta"], "titular": e["cnpj"], "contabil": "1101"}]})
        gestor.habilitar(e["id"], {"frase": f"CONFIRMO PILOTO {e['id']}"})
        (base / "REGRAS-BANCOS.md").write_text(regras_bancos(e, cenario), encoding="utf-8")
        (base / "REGRAS-FISCAIS.json").write_text(json.dumps(regras_fiscais(e), ensure_ascii=False, indent=2), encoding="utf-8")
        (base / "REGRAS-DP.json").write_text(regras_dp(e, valido=cenario == "A"), encoding="utf-8")
        (base / "REGRAS-CONCILIACAO.json").write_text(json.dumps(regras_conciliacao(e), ensure_ascii=False, indent=2), encoding="utf-8")
        (base / MARCA).write_text(json.dumps({"amostra": "PERCURSO_COMPLETO", "cenario": cenario, "ficticia": True,
                                              "preparada_em": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                                              "documentos": f"TESTES/AMOSTRA-COMPLETA/CENARIO-{cenario}"}, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        feitas.append({"empresa": e["id"], "situacao": "PREPARADA"})
    return {"resultado": "AMOSTRA_PREPARADA", "empresas": feitas, "competencia": COMPETENCIA,
            "documentos": {k: f"TESTES/AMOSTRA-COMPLETA/CENARIO-{k}" for k in EMPRESAS}}


def corrigir_referencias_dp_b() -> dict:
    """Correção do caso "falha de etapa" do cenário B: grava REGRAS-DP.json válido SOMENTE na empresa fictícia B."""
    e = EMPRESAS["B"]
    base = clientes() / e["id"]
    if not (base / MARCA).is_file():
        raise ValueError("Empresa fictícia do cenário B não preparada.")
    (base / "REGRAS-DP.json").write_text(regras_dp(e, valido=True), encoding="utf-8")
    return {"resultado": "REFERENCIAS_DP_CORRIGIDAS", "empresa": e["id"],
            "proximo_passo": "Na solicitação do cenário B, use 'Retomar Contabilidade/DP'."}


def situacao() -> dict:
    return {k: {"empresa": e["id"], "preparada": (clientes() / e["id"] / MARCA).is_file(),
                "documentos": f"TESTES/AMOSTRA-COMPLETA/CENARIO-{k}"} for k, e in EMPRESAS.items()}


# ---------------------------------------------------------------- documentos fictícios dos cenários

def documentos(cenario: str) -> dict:
    """Nome → conteúdo (bytes) dos arquivos do cenário. Mesmos valores do LEIA-ME."""
    e = EMPRESAS[cenario]
    b = cenario == "B"
    conta = f"001-1234-{e['conta']}"
    movs = [("03/10/2026", "TED RECEBIDA ALFA SERVICOS FICTICIOS", "10000.00", "TED001"),
            ("05/10/2026", "PIX ENVIADO BETA SERVICOS NF 555", "-3000.00", "PIX555"),
            ("15/10/2026", "PAGTO ISS 09/2026 ISS-2026-09", "-500.00", "ISS0909"),
            ("25/10/2026", "TED RECEBIDA GAMA COMERCIO NF 102", "6000.00", "TED102"),
            ("30/10/2026", "PAGTO SALARIOS FP-2026-10", "-7100.00" if b else "-7000.00", "FOLHA10"),
            ("31/10/2026", "TARIFA BANCARIA PACOTE", "-45.00", "TAR10")]
    if b:  # pagamento sem suporte e recebimento sem origem comprovada
        movs += [("12/10/2026", "PIX ENVIADO DIVERSOS", "-250.00", "PIXDIV"),
                 ("20/10/2026", "PIX RECEBIDO NAO IDENTIFICADO", "1500.00", "PIXNID")]
    movs.sort(key=lambda m: dt.datetime.strptime(m[0], "%d/%m/%Y"))
    saldo = Decimal("40000.00")
    linhas = ["CONTA;DATA;TIPO;HISTORICO;VALOR;SALDO;IDENTIFICADOR", f"{conta};30/09/2026;SALDO_INICIAL;SALDO ANTERIOR;;{br(saldo)};"]
    for data, hist, valor, ident in movs:
        saldo += Decimal(valor)
        linhas.append(f"{conta};{data};{'CREDITO' if Decimal(valor) > 0 else 'DEBITO'};{hist};{br(valor)};{br(saldo)};{ident}")
    linhas.append(f"{conta};31/10/2026;SALDO_FINAL;SALDO FINAL;;{br(saldo)};")
    arquivos = {f"01_extrato_001_{e['conta']}_2026-10.csv": "\n".join(linhas) + "\n"}

    rel = ["TIPO;DATA;FAVORECIDO;CNPJ;VALOR;DOCUMENTOS;TITULO;CONTA;OBRIGACAO_CONTABILIZADA",
           f"RECEBIMENTO;03/10/2026;{ALFA[0]};{ALFA[1]};10.000,00;;NF 101;{conta};SIM",
           f"PAGAMENTO;05/10/2026;{BETA[0]};{BETA[1]};3.000,00;;NF 555;{conta};SIM",
           f"PAGAMENTO;15/10/2026;{PREFEITURA[0]};{PREFEITURA[1]};500,00;ISS-2026-09;;{conta};SIM",
           f"RECEBIMENTO;25/10/2026;{GAMA[0]};{GAMA[1]};6.000,00;NF 102;;{conta};NAO",
           f"PAGAMENTO;30/10/2026;FOLHA DE PAGAMENTO 10/2026;;{'7.100,00' if b else '7.000,00'};FP-2026-10;;{conta};SIM"]
    arquivos["02_relacao_pagamentos_recebimentos_2026-10.csv"] = "\n".join(rel) + "\n"

    pos = ["TIPO;POSICAO;DATA_BASE;CONTRAPARTE;CNPJ;TITULO;VENCIMENTO;VALOR",
           f"RECEBER;INICIAL;30/09/2026;{ALFA[0]};{ALFA[1]};NF 101;03/10/2026;10.000,00",
           f"PAGAR;INICIAL;30/09/2026;{BETA[0]};{BETA[1]};NF 555;05/10/2026;3.000,00",
           f"RECEBER;FINAL;31/10/2026;{ALFA[0]};{ALFA[1]};NF 103;10/11/2026;4.000,00",
           "PAGAR;FINAL;31/10/2026;;;SEM TITULOS EM ABERTO;;0,00"]
    arquivos["03_posicao_titulos_2026-10.csv"] = "\n".join(pos) + "\n"

    abertura = ["CONTA;DESCRICAO;SALDO;NATUREZA;DATA_BASE;FONTE"]
    for codigo, _, descricao, grupo in PLANO:
        valor, natureza = ABERTURA.get(codigo, ("0.00", "D" if grupo in ("ATIVO", "DESPESA") else "C"))
        abertura.append(f"{codigo};{descricao};{br(valor)};{natureza};30/09/2026;BALANCETE DE 30/09/2026 (FICTICIO, CONTROLE INTERNO)")
    arquivos["04_saldos_abertura_2026-09-30.csv"] = "\n".join(abertura) + "\n"

    cab = f"EMPRESA: {e['nome']}\nCNPJ: {e['cnpj']}\n"
    arquivos["05_resumo_folha_2026-10.txt"] = (
        f"RESUMO DA FOLHA DE PAGAMENTO\n{cab}COMPETENCIA: 10/2026\nNUMERO DO DOCUMENTO: FP-2026-10\nRUBRICA;TIPO;VALOR\n"
        "SALARIO BASE;PROVENTO;8.000,00\nINSS SEGURADOS;DESCONTO;700,00\nIRRF;DESCONTO;300,00\nTOTAL DE PROVENTOS: 8.000,00\n"
        "TOTAL DE DESCONTOS: 1.000,00\nLIQUIDO A PAGAR: 7.000,00\n")
    arquivos["06_resumo_encargos_2026-10.txt"] = (
        f"RESUMO DE ENCARGOS DA FOLHA\nCNPJ: {e['cnpj']}\nCOMPETENCIA: 10/2026\nNUMERO DO DOCUMENTO: EN-2026-10\nENCARGO;BASE;VALOR\n"
        "INSS EMPRESA;8.000,00;1.600,00\nINSS RAT E TERCEIROS;8.000,00;500,00\nFGTS;8.000,00;640,00\n"
        "TOTAL INSS A RECOLHER: 2.800,00\nTOTAL FGTS A RECOLHER: 640,00\n")
    comp_prov = "09/2026" if b else "10/2026"     # cenário B: competência diferente
    arquivos["07_provisoes_ferias_13_2026-10.txt"] = (
        f"DEMONSTRATIVO DE PROVISOES DE FERIAS E 13 SALARIO\nCNPJ: {e['cnpj']}\nCOMPETENCIA: {comp_prov}\nNUMERO DO DOCUMENTO: PR-{comp_prov[3:]}-{comp_prov[:2]}\n"
        "PROVISAO;VALOR DO MES\nFERIAS COM 1/3;1.000,00\n13 SALARIO;666,67\nTOTAL DAS PROVISOES: 1.666,67\n"
        "ENCARGOS SOBRE PROVISOES: NAO INFORMADOS\n")
    for numero, cliente, data, valor in (("102", GAMA, "25/10/2026", "6.000,00"), ("103", ALFA, "28/10/2026", "4.000,00")):
        arquivos[f"{'08' if numero == '102' else '09'}_nfse_{numero}_{cliente[0].split()[0].lower()}.txt"] = (
            f"NFS-E - NOTA FISCAL DE SERVICOS ELETRONICA (FICTICIA)\nPRESTADOR: {e['nome']}\nCNPJ DO PRESTADOR: {e['cnpj']}\n"
            f"TOMADOR: {cliente[0]}\nCNPJ DO TOMADOR: {cliente[1]}\nNUMERO DA NOTA: {numero}\nDATA DE EMISSAO: {data}\n"
            f"COMPETENCIA: 10/2026\nVALOR DOS SERVICOS: R$ {valor}\nVALOR TOTAL DA NOTA: R$ {valor}\n")
    apuracoes = [("10", "ISS", "200,00"), ("11", "PIS", "65,00"), ("12", "COFINS", "300,00")]
    for prefixo, tributo, valor in apuracoes:
        arquivos[f"{prefixo}_apuracao_{tributo.lower()}_2026-10.txt"] = (
            f"DEMONSTRATIVO DE APURACAO\nCNPJ: {e['cnpj']}\nPERIODO DE APURACAO: 10/2026\nTRIBUTO: {tributo}\n"
            f"NUMERO DO DOCUMENTO: AP-{tributo}-2026-10\nVALOR APURADO: R$ {valor}\n")
    if b:  # cenário B: apuração de ISS duplicada com valor diferente (qual prevalece não é determinável)
        arquivos["10b_apuracao_iss_2026-10_segunda_via.txt"] = (
            f"DEMONSTRATIVO DE APURACAO\nCNPJ: {e['cnpj']}\nPERIODO DE APURACAO: 10/2026\nTRIBUTO: ISS\n"
            "NUMERO DO DOCUMENTO: AP-ISS-2026-10-B\nVALOR APURADO: R$ 210,00\n")
    arquivos["13_guia_iss_2026-09.txt"] = (
        f"DOCUMENTO DE ARRECADACAO MUNICIPAL - ISS (FICTICIO)\nCONTRIBUINTE: {e['nome']}\nCNPJ: {e['cnpj']}\n"
        "NUMERO DO DOCUMENTO: ISS-2026-09\nPERIODO DE APURACAO: 09/2026\nCODIGO DA RECEITA: 1406\nVENCIMENTO: 15/10/2026\n"
        "VALOR TOTAL: R$ 500,00\n")
    arquivos["14_comprovante_pix_beta.txt"] = (
        f"COMPROVANTE DE PAGAMENTO PIX (FICTICIO)\nPAGADOR: {e['nome']}\nCNPJ DO PAGADOR: {e['cnpj']}\nFAVORECIDO: {BETA[0]}\n"
        f"CNPJ DO FAVORECIDO: {BETA[1]}\nDATA DO PAGAMENTO: 05/10/2026\nVALOR PAGO: R$ 3.000,00\nID DA TRANSACAO: PIX555\n"
        "REFERENTE A: NF 555\n")
    # cenário B: confirmação do cliente ALFA (saldo em aberto de 4.000,00 — posição necessária) NÃO recebida
    confirmacoes = [("15_confirmacao_saldo_beta.txt", BETA, "0,00")] + ([] if b else [("16_confirmacao_saldo_alfa.txt", ALFA, "4.000,00")])
    for nome, terceiro, saldo_terceiro in confirmacoes:
        arquivos[nome] = (f"CONFIRMACAO DE SALDO\nEMITENTE: {terceiro[0]}\nCNPJ DO EMITENTE: {terceiro[1]}\nCLIENTE: {e['nome']}\n"
                          f"CNPJ DO CLIENTE: {e['cnpj']}\nDATA BASE: 31/10/2026\nSALDO EM ABERTO: {saldo_terceiro}\n")
    if b:
        arquivos["17_comprovante_outra_empresa.txt"] = (   # documento de outra empresa
            f"COMPROVANTE DE PAGAMENTO PIX (FICTICIO)\nPAGADOR: {OUTRA[0]}\nCNPJ DO PAGADOR: {OUTRA[1]}\nFAVORECIDO: {BETA[0]}\n"
            f"CNPJ DO FAVORECIDO: {BETA[1]}\nDATA DO PAGAMENTO: 12/10/2026\nVALOR PAGO: R$ 250,00\nID DA TRANSACAO: PIXOUT\n")
    saida = {n: c.encode("utf-8") for n, c in arquivos.items()}
    if b:
        saida["18_documento_protegido.pdf"] = pdf_protegido()   # protegido (somente senha de proprietário)
    return saida


def pdf_protegido() -> bytes:
    """PDF fictício com proteção apenas de proprietário: deve ficar PDF_PROTEGIDO (nenhuma senha é tentada)."""
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.encrypt(user_password="", owner_password="proprietario-ficticio", algorithm="RC4-128")
    buffer = io.BytesIO()
    w.write(buffer)
    return buffer.getvalue()


def gerar_documentos(destino: Path = PASTA_AMOSTRA) -> list:
    escritos = []
    for cenario in EMPRESAS:
        pasta = Path(destino) / f"CENARIO-{cenario}"
        pasta.mkdir(parents=True, exist_ok=True)
        for nome, conteudo in documentos(cenario).items():
            if nome.endswith(".pdf") and (pasta / nome).is_file():
                continue            # PDF criptografado muda a cada geração; o existente é mantido (conteúdo equivalente)
            (pasta / nome).write_bytes(conteudo)
            escritos.append(str((pasta / nome).relative_to(RAIZ)))
    return escritos


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    acao = sys.argv[1] if len(sys.argv) > 1 else ""
    if acao == "gerar-documentos":
        print(json.dumps({"escritos": gerar_documentos()}, ensure_ascii=False, indent=2))
        return 0
    if acao == "preparar":
        import os
        runtime = Path(os.environ.get("AGENTES_PRIME_RUNTIME") or Path(os.environ.get("LOCALAPPDATA", "")) / "AgentesPrime" / "runtime")
        somente = sys.argv[sys.argv.index("--somente") + 1].split(",") if "--somente" in sys.argv else None
        print(json.dumps(preparar(runtime, recriar="--recriar" in sys.argv, cenarios=somente), ensure_ascii=False, indent=2))
        return 0
    if acao == "corrigir-dp-b":
        print(json.dumps(corrigir_referencias_dp_b(), ensure_ascii=False, indent=2))
        return 0
    print("Uso: amostra_ficticia.py gerar-documentos | preparar [--recriar] [--somente A|B|A,B] | corrigir-dp-b")
    return 2


if __name__ == "__main__":
    sys.exit(main())
