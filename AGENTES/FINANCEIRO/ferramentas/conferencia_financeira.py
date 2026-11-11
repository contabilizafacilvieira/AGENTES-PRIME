"""Conferência financeira (Agente Financeiro) - código local, determinístico, SEM modelo de linguagem.

Uso (chamado pelo Coordenador/API depois da etapa de Documentos; a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I AGENTES/FINANCEIRO/ferramentas/conferencia_financeira.py --empresa <EMP> --sol <SOL>
        --competencia AAAA-MM --pasta <pasta relativa à empresa> --saida <pasta> [--ja-tratados <json>] [--decisoes <json>]

O que faz (procedimento geral: AGENTES/FINANCEIRO/PROCEDIMENTO.md):
- Lê os documentos SOMENTE pelo extrator (canal homologado), sem alterar nada.
- Extrato (OFX ou CSV no leiaute do projeto) é a fonte das movimentações efetivas; a relação de pagamentos é auxiliar.
- Conta bancária identificada pelo extrato e conferida com as contas do CADASTRO.md da empresa (sem mistura de contas).
- Para cada movimento: relação, comprovante de liquidação, documento que sustenta a natureza, valores, datas,
  favorecido e identificadores; divergências, duplicidades e ausências.
- Correspondência só com igualdade EXATA (sem tolerância de valor ou data). Mais de um candidato = AMBÍGUA (Supervisor
  decide). Igualdade parcial = SUGESTÃO, apresentada à parte e nunca contada como confirmada.
- Não é conciliação contábil completa (a Conciliação independente é etapa futura).
Saída: <saida>/resultado.json. Códigos de saída: 0 = ok | 2 = parâmetros | 3 = extrator indisponível.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
def clientes():
    """Pasta CLIENTES (avaliada a cada uso: AGENTES_PRIME_CLIENTES em testes isolados; RAIZ/CLIENTES em produção)."""
    return Path(os.environ.get("AGENTES_PRIME_CLIENTES") or RAIZ / "CLIENTES")
sys.path.insert(0, str(RAIZ / 'API-LOCAL'))
from documentos_local import encaminhamento
from metodo_empresa import carregar as carregar_metodo_empresa
sys.path.insert(0, str(Path(__file__).resolve().parent))
import normalizador_financeiro as nf
import normalizador_bancario as nb
import conciliador_financeiro as cf
import decisoes_conciliacao as dcs
EXTRATOR = RAIZ / "AGENTES" / "DOCUMENTOS" / "ferramentas" / "extrair_documentos.py"
VERSAO = "1.5"
PROCEDIMENTO = "AGENTES/FINANCEIRO/PROCEDIMENTO.md v1.5"
RE_CNPJ = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")
RE_DATA = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
RE_VALOR_BR = re.compile(r"(?<!\d)(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?!\d)")


def norm(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip()


def digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def valor(texto):
    """Valor monetário exato (Decimal). Aceita 1.234,56 / 1234,56 / -1234.56 / 1234.5."""
    if texto is None or isinstance(texto, bool):
        return None
    if isinstance(texto, (int, float)):
        texto = repr(texto)
    t = str(texto).strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t).quantize(Decimal("0.01")) if re.fullmatch(r"[-+]?\d+(\.\d+)?", t) else None
    except InvalidOperation:
        return None


def data_iso(texto):
    if texto is None:
        return None
    t = str(texto).strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", t)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(?:\d{6})?(?:\.\d+)?(?:\[.*\])?", t)     # OFX
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def fmt(v) -> str:
    return None if v is None else f"{v:.2f}"


def hash_curto(*partes) -> str:
    return hashlib.sha256("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:12].upper()


# ---------------------------------------------------------------- cadastro da empresa (somente leitura)

def tabela_md(texto: str, titulo: str) -> list:
    """Linhas (dict) da primeira tabela após o título '## <titulo>'."""
    linhas, dentro, cab = [], False, None
    for l in texto.splitlines():
        if l.startswith("## "):
            dentro = norm(l[3:]).startswith(norm(titulo))
            continue
        if not dentro or not l.strip().startswith("|"):
            continue
        celulas = [c.strip() for c in l.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in celulas if c):
            continue
        if cab is None:
            cab = [norm(c) for c in celulas]
            continue
        if any(celulas):
            linhas.append(dict(zip(cab, celulas)))
    return linhas


def chave_conta(banco, agencia, conta) -> str:
    return f"{digitos(banco).zfill(3)}-{digitos(agencia).lstrip('0') or '0'}-{digitos(conta).lstrip('0') or '0'}"


def cadastro(empresa: str) -> dict:
    texto = (clientes() / empresa / "CADASTRO.md").read_text(encoding="utf-8")
    cnpjs = sorted({digitos(c) for c in re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)})
    contas = {}
    for l in tabela_md(texto, "Contas bancarias"):
        banco, agencia, conta = l.get("BANCO", ""), l.get("AGENCIA", ""), l.get("CONTA", "")
        if digitos(banco) and digitos(conta):
            contas[chave_conta(banco, agencia, conta)] = {"banco": banco, "agencia": agencia, "conta": conta,
                                                           "titular": digitos(l.get("TITULAR (CNPJ)", "")),
                                                           "situacao": norm(l.get("SITUACAO", "ATIVA")) or "ATIVA"}
    outras = {}
    for pasta in (clientes()).iterdir():
        if pasta.is_dir() and pasta.name != empresa and (pasta / "CADASTRO.md").is_file():
            for c in re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", (pasta / "CADASTRO.md").read_text(encoding="utf-8")):
                outras[digitos(c)] = pasta.name
    return {"cnpjs": cnpjs, "contas": contas, "cnpjs_outras_empresas": {c: e for c, e in outras.items() if c not in cnpjs}}


# ---------------------------------------------------------------- leitura (somente pelo extrator)

def extrair(empresa: str, pasta: str) -> list:
    p = subprocess.run([sys.executable, "-I", str(RAIZ / 'API-LOCAL/documentos_local.py'), '--extrair', empresa, pasta],
                       cwd=RAIZ, capture_output=True, encoding="utf-8", timeout=1800)
    if p.returncode != 0:
        print(json.dumps({"erro": "EXTRATOR", "mensagem": (p.stderr or "")[-300:]}, ensure_ascii=False))
        raise SystemExit(3)
    return json.loads(p.stdout)["arquivos"]


def nome_arquivo(a: dict) -> str:
    return a["arquivo"].rsplit("/", 1)[-1]


def texto_de(a: dict) -> str:
    c = a.get("conteudo") or {}
    if a.get("leitura") == "EXTRAIDO_TEXTO":
        return c.get("texto", "")
    if a.get("leitura") == "EXTRAIDO_PDF":
        return "\n".join(p.get("texto", "") for p in c.get("paginas", []))
    return ""


def linhas_tabulares(a: dict) -> list:
    """Linhas de CSV (separador ';') ou de planilha, como listas de células."""
    if a.get("leitura") == "EXTRAIDO_PLANILHA":
        return [l["valores"] for aba in a["conteudo"]["abas"] if not aba.get("oculta") for l in aba["linhas"]]
    if a.get("leitura") == "EXTRAIDO_TEXTO" and a["extensao"] == ".csv":
        return [[c.strip() for c in l.split(";")] for l in texto_de(a).splitlines() if l.strip()]
    return []


def cabecalho(linhas: list, exigidas: set):
    for i, l in enumerate(linhas[:10]):
        nomes = [norm(c).replace(" ", "_") if c is not None else "" for c in l]
        if exigidas <= set(nomes):
            return i, nomes
    return None, None


# ---------------------------------------------------------------- extratos

def ofx_campo(bloco: str, tag: str):
    m = re.search(rf"<{tag}>([^<\r\n]*)", bloco, re.I)
    return m.group(1).strip() if m else None


def ler_ofx(a: dict, empresa: str) -> list:
    texto = texto_de(a)
    extratos = []
    for bloco in re.split(r"<STMTRS>", texto, flags=re.I)[1:]:
        conta = re.search(r"<BANKACCTFROM>(.*?)(?:</BANKACCTFROM>|<BANKTRANLIST>)", bloco, re.S | re.I)
        conta = conta.group(1) if conta else ""
        banco, agencia, numero = ofx_campo(conta, "BANKID"), ofx_campo(conta, "BRANCHID"), ofx_campo(conta, "ACCTID")
        lista = re.search(r"<BANKTRANLIST>(.*?)(?:</BANKTRANLIST>|$)", bloco, re.S | re.I)
        lista = lista.group(1) if lista else ""
        movs = []
        for i, t in enumerate(re.split(r"<STMTTRN>", lista, flags=re.I)[1:], 1):
            t = re.split(r"</STMTTRN>", t, flags=re.I)[0]
            v = valor(ofx_campo(t, "TRNAMT"))
            movs.append({"data": data_iso(ofx_campo(t, "DTPOSTED")), "valor_assinado": v,
                         "descricao": " ".join(x for x in (ofx_campo(t, "NAME"), ofx_campo(t, "MEMO")) if x),
                         "identificadores": {k: ofx_campo(t, k) for k in ("FITID", "CHECKNUM", "REFNUM") if ofx_campo(t, k)},
                         "tipo_banco": ofx_campo(t, "TRNTYPE"), "origem": f"{nome_arquivo(a)} · STMTTRN {i}"})
        saldo_final = re.search(r"<LEDGERBAL>(.*?)(?:</LEDGERBAL>|<AVAILBAL>|</STMTRS>|$)", bloco, re.S | re.I)
        extratos.append({
            "arquivo": nome_arquivo(a), "formato": "OFX", "banco": banco, "agencia": agencia, "conta": numero, "titular": None,
            "inicio": data_iso(ofx_campo(lista, "DTSTART")), "fim": data_iso(ofx_campo(lista, "DTEND")),
            "saldo_inicial": None, "data_saldo_inicial": None,
            "saldo_final": valor(ofx_campo(saldo_final.group(1), "BALAMT")) if saldo_final else None,
            "data_saldo_final": data_iso(ofx_campo(saldo_final.group(1), "DTASOF")) if saldo_final else None,
            "movimentos": movs})
    return extratos


CSV_EXTRATO = {"CONTA", "DATA", "TIPO", "HISTORICO", "VALOR", "SALDO"}


def ler_santander_pdf(a: dict):
    """Layout Santander Empresas, texto digital completo, linhas em ordem decrescente.

    None = outro layout. Erro = layout reconhecido mas não utilizável; nunca aproveita
    parcialmente um extrato nem transforma saldo disponível em saldo contábil.
    """
    texto = texto_de(a)
    if a.get("leitura") != "EXTRAIDO_PDF" or "SANTANDER EMPRESAS" not in norm(texto):
        return None
    c = a.get("conteudo") or {}
    paginas = c.get("paginas", [])
    total = c.get("paginas_total")
    if not total or len(paginas) != total or c.get("paginas_requer_ocr") or c.get("truncado"):
        raise ValueError("PDF Santander incompleto ou com páginas sem texto; envie o OFX ou PDF digital completo.")
    if [p.get("pagina") for p in paginas] != list(range(1, total + 1)):
        raise ValueError("Páginas do PDF Santander ausentes ou fora de ordem.")
    contas = set(re.findall(r"Ag[eê]ncia:\s*(\d+)\s+Conta:\s*([\d.-]+)", texto, re.I))
    periodos = set(re.findall(r"Per[ií]odos?:\s*(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})", texto, re.I))
    if len(contas) != 1 or len(periodos) != 1:
        raise ValueError("Agência, conta ou período do PDF Santander ausente ou ambíguo.")
    agencia, numero = next(iter(contas))
    ini, fim = next(iter(periodos))
    try:
        inicio, final = (dt.datetime.strptime(d, "%d/%m/%Y").date().isoformat() for d in (ini, fim))
    except ValueError as exc:
        raise ValueError("Período inválido no PDF Santander.") from exc
    if inicio > final:
        raise ValueError("Período invertido no PDF Santander.")
    dinheiro = r"[-+]?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}"
    linha_mov = re.compile(rf"^(\d{{2}}/\d{{2}}/\d{{4}})\s+(.+?)\s+({dinheiro})\s+({dinheiro})$")
    movimentos, vistos = [], set()
    for p in paginas:
        pg, txt = p.get("pagina"), p.get("texto", "")
        if pg in vistos or not isinstance(pg, int) or not 1 <= pg <= total:
            raise ValueError("Paginação inválida no PDF Santander.")
        vistos.add(pg)
        if not re.search(rf"(?m)^\s*{pg}/{total}\s*$", txt):
            raise ValueError(f"Página {pg}: numeração do PDF Santander não confirmada.")
        for n, l in enumerate(txt.splitlines(), 1):
            l = l.strip()
            if not re.match(r"^\d{2}/\d{2}/\d{4}(?:\s|$)", l):
                continue
            m = linha_mov.fullmatch(l)
            if not m:
                raise ValueError(f"Página {pg}, linha {n}: movimento Santander não reconhecido; nenhum movimento deste arquivo foi utilizado.")
            dia, descricao, quantia, saldo = m.groups()
            try:
                dia = dt.datetime.strptime(dia, "%d/%m/%Y").date().isoformat()
            except ValueError as exc:
                raise ValueError(f"Página {pg}: data de movimento inválida.") from exc
            if not inicio <= dia <= final:
                raise ValueError(f"Página {pg}: movimento fora do período declarado.")
            documento = re.search(r"\s(\d{6,})$", descricao)
            ids = {"DOCUMENTO": documento.group(1)} if documento and int(documento.group(1)) else {}
            movimentos.append({"data": dia, "valor_assinado": valor(quantia), "saldo_apos": valor(saldo),
                               "descricao": descricao, "identificadores": ids, "tipo_banco": None,
                               "origem": f"{nome_arquivo(a)} · página {pg}, linha {n}"})
    if not movimentos:
        raise ValueError("Nenhuma linha de movimentação reconhecida no PDF Santander; envie o OFX.")
    for atual, anterior in zip(movimentos, movimentos[1:]):
        if atual["data"] < anterior["data"]:
            raise ValueError("Ordem de movimentos diferente do layout Santander reconhecido.")
        if anterior["saldo_apos"] + atual["valor_assinado"] != atual["saldo_apos"]:
            raise ValueError(f"Saldos sucessivos divergentes em {atual['origem']}; confira o extrato completo ou envie OFX.")
    # Não há saldo inicial independente nesse layout. Não deduzir um saldo para
    # depois declarar a própria dedução como prova de conciliação completa.
    return [{"arquivo": nome_arquivo(a), "formato": "PDF_SANTANDER", "banco": "033", "agencia": agencia,
             "conta": numero, "titular": None, "inicio": inicio, "fim": final,
             "saldo_inicial": None, "data_saldo_inicial": None,
             "saldo_final": movimentos[0]["saldo_apos"], "data_saldo_final": movimentos[0]["data"],
             "saldos_sucessivos": "CONSISTENTES", "paginas_lidas": sorted(vistos),
             "movimentos": list(reversed(movimentos))}]


def ler_csv_extrato(a: dict, linhas: list) -> list:
    i, cab = cabecalho(linhas, CSV_EXTRATO)
    por_conta = {}
    for n, l in enumerate(linhas[i + 1:], i + 2):
        r = dict(zip(cab, l))
        partes = [x for x in re.split(r"[-/ ]", str(r.get("CONTA") or "")) if x]
        if len(partes) < 3:
            continue
        chave = tuple(partes[:2] + ["".join(partes[2:])])
        e = por_conta.setdefault(chave, {"arquivo": nome_arquivo(a), "formato": "CSV", "banco": partes[0], "agencia": partes[1],
                                          "conta": "".join(partes[2:]), "titular": digitos(r.get("TITULAR_CNPJ")) or None,
                                          "inicio": None, "fim": None, "saldo_inicial": None, "data_saldo_inicial": None,
                                          "saldo_final": None, "data_saldo_final": None, "movimentos": []})
        tipo = norm(r.get("TIPO"))
        if tipo == "SALDO_INICIAL":
            e.update(saldo_inicial=valor(r.get("SALDO")), data_saldo_inicial=data_iso(r.get("DATA")), inicio=data_iso(r.get("DATA")))
        elif tipo == "SALDO_FINAL":
            e.update(saldo_final=valor(r.get("SALDO")), data_saldo_final=data_iso(r.get("DATA")), fim=data_iso(r.get("DATA")))
        else:
            e["movimentos"].append({"data": data_iso(r.get("DATA")), "valor_assinado": valor(r.get("VALOR")),
                                    "descricao": str(r.get("HISTORICO") or ""),
                                    "identificadores": {"DOCUMENTO": str(r["IDENTIFICADOR"])} if r.get("IDENTIFICADOR") else {},
                                    "tipo_banco": None, "origem": f"{nome_arquivo(a)} · linha {n}"})
    return list(por_conta.values())


# ---------------------------------------------------------------- relação de pagamentos

def ler_relacao(a: dict, linhas: list) -> list:
    i, cab = cabecalho(linhas, {"FAVORECIDO", "VALOR"})
    itens = []
    for n, l in enumerate(linhas[i + 1:], i + 2):
        r = dict(zip(cab, l))
        if not any(v not in (None, "") for v in r.values()):
            continue
        ref = str(r.get("DOCUMENTOS") or r.get("DOCUMENTO") or "")
        # TIPO: PAGAMENTO (débito; padrão quando a coluna não existe ou está vazia) | RECEBIMENTO (crédito; FAVORECIDO = pagador).
        tipo = norm(r.get("TIPO")) or "PAGAMENTO"
        itens.append({"id": f"REL-{hash_curto(nome_arquivo(a), n)}", "origem": f"{nome_arquivo(a)} · linha {n}",
                      "tipo": tipo, "direcao": {"PAGAMENTO": "DEBITO", "RECEBIMENTO": "CREDITO"}.get(tipo),
                      "data": data_iso(r.get("DATA_PAGAMENTO") or r.get("DATA")), "favorecido": str(r.get("FAVORECIDO") or ""),
                      "favorecido_cnpj": digitos(r.get("CNPJ_CPF") or r.get("CNPJ")) or None, "valor": fmt(valor(r.get("VALOR"))),
                      "referencias": [x.strip() for x in re.split(r"[;,]", ref) if x.strip()],
                      "titulo": str(r.get("TITULO") or "").strip() or None,
                      "conta": str(r.get("CONTA_PAGADORA") or r.get("CONTA") or "") or None,
                      "pagamento_id": str(r.get("PAGAMENTO_ID") or "") or None,
                      "obrigacao_contabilizada": norm(r.get("OBRIGACAO_CONTABILIZADA")) or None,
                      "natureza_informada": str(r.get("NATUREZA") or "") or None})
    return itens


CSV_POSICAO = {"TIPO", "POSICAO", "DATA_BASE", "CONTRAPARTE", "TITULO", "VALOR"}
SEM_TITULOS = "SEM TITULOS EM ABERTO"     # declaração expressa de posição sem títulos (sem ela, nunca presumir vazia)


def ler_posicao(a: dict, linhas: list) -> list:
    """Posição de títulos a pagar/receber (controle INTERNO da empresa): uma linha por título e posição."""
    i, cab = cabecalho(linhas, CSV_POSICAO)
    itens = []
    for n, l in enumerate(linhas[i + 1:], i + 2):
        r = dict(zip(cab, l))
        if not any(v not in (None, "") for v in r.values()):
            continue
        itens.append({"origem": f"{nome_arquivo(a)} · linha {n}", "arquivo": nome_arquivo(a), "tipo": norm(r.get("TIPO")),
                      "posicao": norm(r.get("POSICAO")), "data_base": data_iso(r.get("DATA_BASE")),
                      "contraparte": str(r.get("CONTRAPARTE") or "").strip(), "cnpj": digitos(r.get("CNPJ")) or None,
                      "titulo": str(r.get("TITULO") or "").strip(), "vencimento": data_iso(r.get("VENCIMENTO")),
                      "valor": valor(r.get("VALOR"))})
    return itens


# ---------------------------------------------------------------- comprovantes e documentos de suporte

TIPOS_TEXTO = [
    # Cópia de suporte do DP (layout CONTRATO 3.1): sustenta a natureza do pagamento de salários; sem análise de folha aqui.
    ("FOLHA", lambda t: "RESUMO DA FOLHA DE PAGAMENTO" in t),
    ("COMPROVANTE", lambda t: "COMPROVANTE" in t and any(k in t for k in ("PAGAMENTO", "TRANSFERENCIA", "PIX", "TED"))),
    ("GUIA", lambda t: any(k in t for k in ("DARF", "DOCUMENTO DE ARRECADACAO", "GUIA DE RECOLHIMENTO", "GPS ", "FGTS"))),
    ("BOLETO", lambda t: any(k in t for k in ("LINHA DIGITAVEL", "FICHA DE COMPENSACAO", "BOLETO"))),
    ("RECIBO", lambda t: "RECIBO" in t),
    ("NOTA_FISCAL", lambda t: any(k in t for k in ("NOTA FISCAL", "NFS-E", "NFSE"))),
]
ROTULOS_VALOR = {
    "FOLHA": ["LIQUIDO A PAGAR"],
    "COMPROVANTE": ["VALOR PAGO", "VALOR DA TRANSFERENCIA", "VALOR"],
    "GUIA": ["VALOR TOTAL", "VALOR A PAGAR", "VALOR DO DOCUMENTO", "VALOR"],
    "BOLETO": ["VALOR DO DOCUMENTO", "VALOR DOCUMENTO", "VALOR COBRADO", "VALOR"],
    "RECIBO": ["VALOR", "QUANTIA"],
    "NOTA_FISCAL": ["VALOR TOTAL DA NOTA", "VALOR LIQUIDO", "VALOR TOTAL", "VALOR"],
}
ROTULOS_DATA = {
    "FOLHA": ["DATA DO PAGAMENTO", "DATA DE PAGAMENTO"],
    "COMPROVANTE": ["DATA DO PAGAMENTO", "DATA DE PAGAMENTO", "DATA DA TRANSFERENCIA", "PAGO EM", "DATA"],
    "GUIA": ["VENCIMENTO", "DATA DE VENCIMENTO"], "BOLETO": ["VENCIMENTO"],
    "RECIBO": ["DATA", "EMISSAO"], "NOTA_FISCAL": ["DATA DE EMISSAO", "DATA EMISSAO", "EMISSAO", "DATA"],
}
ROTULOS_ID = ["AUTENTICACAO", "ID DA TRANSACAO", "ID TRANSACAO", "CODIGO DA TRANSACAO", "E2E", "NOSSO NUMERO",
              "NUMERO DO DOCUMENTO", "NUMERO DA NOTA", "NUMERO", "LINHA DIGITAVEL", "CODIGO DE BARRAS"]


def rotulado(linhas: list, rotulos: list, padrao):
    """Valor após o rótulo no início da linha: 'ROTULO: valor' (ou 'ROTULO valor' quando o valor tem padrão próprio).
    O rótulo mais específico vem primeiro na lista; 'VALOR' não captura 'VALOR PAGO: ...'."""
    for r in rotulos:
        achados = set()
        for n, l in enumerate(linhas):
            m = re.match(rf"^{re.escape(r)}\s*:\s*(.+)$", l) or (re.match(rf"^{re.escape(r)}\s+(?![A-Z]{{2}})(.+)$", l) if padrao else None)
            trecho = m.group(1) if m else None
            if (re.fullmatch(rf"{re.escape(r)}\s*:?", l) or
                (padrao is RE_DATA and l == r + ' HORA EMISSAO')) and n + 1 < len(linhas):
                proxima = linhas[n + 1]
                # Somente o valor imediatamente seguinte; nunca procurar adiante até
                # encontrar um número que possa pertencer a outro campo.
                if padrao and padrao.match(proxima):
                    trecho = proxima
            if trecho:
                achado = padrao.search(trecho) if padrao else None
                if achado:
                    achados.add(achado.group(0))
                elif padrao is None and trecho.strip():
                    achados.add(trecho.strip())
        if len(achados) == 1:
            return achados.pop(), r
        if len(achados) > 1:
            return None, f'{r} (valores conflitantes)'
    return None, None


def ler_documento_texto(a: dict, cad: dict) -> dict:
    texto = norm(texto_de(a))
    linhas = [norm(l) for l in texto_de(a).splitlines() if l.strip()]
    tipo = next((t for t, teste in TIPOS_TEXTO if teste(texto)), "NAO_IDENTIFICADO")
    doc = {"id": f"DOC-{hash_curto(a['sha256'])}", "arquivo": nome_arquivo(a), "tipo": tipo, "origem_dados": "texto do documento (extrator)",
           "campos": {}, "ausentes": []}
    if tipo == "NAO_IDENTIFICADO":
        return doc
    v, r = rotulado(linhas, ROTULOS_VALOR[tipo], RE_VALOR_BR)
    doc["valor"] = fmt(valor(v)) if v else None
    doc["campos"]["valor"] = f"rótulo {r}" if r else None
    d, r = rotulado(linhas, ROTULOS_DATA[tipo], RE_DATA)
    doc["data"] = data_iso(d) if d else None
    doc["campos"]["data"] = f"rótulo {r}" if r else None
    doc['papel_data'] = ('PAGAMENTO' if tipo == 'COMPROVANTE' else
                         'VENCIMENTO' if tipo in ('BOLETO', 'GUIA') else 'EMISSAO_DOCUMENTO')
    # Tabela de boleto com cabeçalhos agrupados: ler somente este esquema explícito.
    if tipo == 'BOLETO':
        valores_tabela, datas_tabela, numeros_tabela = set(), set(), set()
        for n, l in enumerate(linhas[:-1]):
            if l == 'NUMERO DO DOCUMENTO CPF/CNPJ VENCIMENTO VALOR DOCUMENTO':
                m = re.fullmatch(r'(\S+)\s+(' + RE_CNPJ.pattern + r')\s+(\d{2}/\d{2}/\d{4})\s+(\d[\d.]*,\d{2})', linhas[n + 1])
                if m:
                    numeros_tabela.add(m.group(1)); datas_tabela.add(data_iso(m.group(3))); valores_tabela.add(fmt(valor(m.group(4))))
        for campo, valores in (('valor', valores_tabela), ('data', datas_tabela)):
            if valores:
                atual = doc.get(campo)
                if atual: valores.add(atual)
                doc[campo] = next(iter(valores)) if len(valores) == 1 else None
                doc['campos'][campo] = 'tabela explícita do boleto' if len(valores) == 1 else 'tabela e rótulo conflitantes'
    fav, r = rotulado(linhas, ["FAVORECIDO", "BENEFICIARIO", "RECEBEDOR", "DESTINATARIO", "PRESTADOR", "EMITENTE"], None)
    if not fav:
        candidatos_fav = set()
        for l in linhas:
            m = re.match(r'^(?:BENEFICIARIO|PRESTADOR DE SERVICOS)\s+(.+)', l)
            if m and not m.group(1).startswith(('AGENCIA', 'ESPECIE', 'CPF', 'CNPJ', 'NOME')):
                candidatos_fav.add(re.split(r'\s+-?\s*CNPJ|\s+AGENCIA/CODIGO|\s+\d{2}\.\d{3}\.\d{3}/', m.group(1))[0].rstrip(' -'))
        if len(candidatos_fav) == 1: fav = candidatos_fav.pop()
    doc["favorecido"] = RE_CNPJ.sub("", fav).strip(" -:") if fav else None
    # Sequências de 14 dígitos de códigos de barras não são CNPJs identificados.
    cnpjs = [digitos(m.group(0)) for m in RE_CNPJ.finditer(texto)
             if '/' in m.group(0) or 'CNPJ' in texto[max(0, m.start()-35):m.start()]]
    doc["cnpjs_empresa"] = sorted({c for c in cnpjs if c in cad["cnpjs"]})
    doc["cnpjs_terceiros"] = sorted({c for c in cnpjs if c not in cad["cnpjs"]})
    fav_cnpj, _ = rotulado(linhas, ["CNPJ DO FAVORECIDO", "CNPJ DO BENEFICIARIO", "CNPJ DO PRESTADOR", "CNPJ DO EMITENTE", "CNPJ/CPF DO FAVORECIDO"], RE_CNPJ)
    doc["favorecido_cnpj"] = digitos(fav_cnpj) if fav_cnpj else (doc["cnpjs_terceiros"][0] if len(doc["cnpjs_terceiros"]) == 1 else None)
    if tipo == "NOTA_FISCAL":
        # Nota em texto: a contraparte é quem NÃO é esta empresa. Prestador = esta empresa → nota emitida (contraparte = tomador;
        # sustenta entrada no banco); tomador = esta empresa → nota recebida (contraparte = prestador; sustenta saída).
        tomador, _ = rotulado(linhas, ["CNPJ DO TOMADOR", "CNPJ TOMADOR"], RE_CNPJ)
        if doc["favorecido_cnpj"] in cad["cnpjs"] and tomador and digitos(tomador) not in cad["cnpjs"]:
            nome_tomador, _ = rotulado(linhas, ["TOMADOR"], None)
            doc.update(papel="SAIDA", favorecido_cnpj=digitos(tomador),
                       favorecido=RE_CNPJ.sub("", nome_tomador).strip(" -:") if nome_tomador else None)
        elif tomador and digitos(tomador) in cad["cnpjs"]:
            doc["papel"] = "ENTRADA"
    ids = {}
    if tipo == 'BOLETO' and len(numeros_tabela) == 1:
        ids['NUMERO DO DOCUMENTO'] = numeros_tabela.pop()
    for r in ROTULOS_ID:
        achado, _ = rotulado(linhas, [r], None)
        if achado:
            ids[r] = digitos(achado) if r in ("LINHA DIGITAVEL", "CODIGO DE BARRAS") else achado.split(" ")[0]
    if tipo == 'NOTA_FISCAL':
        numeros = {m.group(1) for n, l in enumerate(linhas) if l in ('NUMERO DA NOTA', 'NUMERO DA NFS-E')
                   and n + 1 < len(linhas) for m in [re.fullmatch(r'(\d{1,15})', linhas[n + 1])] if m}
        if len(numeros) == 1:
            ids['NUMERO DA NOTA'] = numeros.pop()
    doc["identificadores"] = ids
    ref = [m.group(1) for l in linhas for m in [re.match(r"^(?:REFERENTE A|REF\.|REF:|DOCUMENTO PAGO)\s*:?\s*(.+)$", l)] if m]
    doc["referencias"] = [x.strip() for r in ref for x in re.split(r"[;,]", r) if x.strip()]
    if tipo == "NOTA_FISCAL" and not ids.get("NUMERO") and not ids.get("NUMERO DA NOTA"):
        m = re.search(r"(?:NOTA FISCAL|NFS-?E)\s*(?:N[O\.]?|NUMERO)?\s*:?\s*(\d+)", texto)
        if m:
            ids["NUMERO"] = m.group(1)
    doc["numero"] = ids.get("NUMERO DA NOTA") or ids.get("NUMERO") or ids.get("NUMERO DO DOCUMENTO")
    doc["ausentes"] = [k for k in ("valor", "data") if not doc.get(k)]
    if tipo == "FOLHA":
        # Resumo da folha: valor = LIQUIDO A PAGAR; número = NUMERO DO DOCUMENTO; competência no lugar da data
        # (o layout não traz data de pagamento, que vem do extrato). Vínculo somente por referência explícita.
        doc["numero"] = ids.get("NUMERO DO DOCUMENTO")
        comp, _ = rotulado(linhas, ["COMPETENCIA"], re.compile(r"\d{2}/\d{4}"))
        doc["competencia"] = f"{comp[3:]}-{comp[:2]}" if comp else None
        doc["papel_data"] = "COMPETENCIA"
        doc["ausentes"] = [k for k, v in (("valor", doc.get("valor")), ("numero do documento", doc["numero"]),
                                          ("competencia", doc["competencia"])) if not v]
    return doc


def ler_nfe(a: dict, cad: dict) -> dict:
    c = a["conteudo"]
    emit = digitos((c.get("emitente") or {}).get("CNPJ"))
    dest = digitos((c.get("destinatario") or {}).get("CNPJ"))
    papel = "ENTRADA" if dest in cad["cnpjs"] else "SAIDA" if emit in cad["cnpjs"] else "TERCEIROS"
    return {"id": f"DOC-{hash_curto(a['sha256'])}", "arquivo": nome_arquivo(a), "tipo": "NOTA_FISCAL", "origem_dados": "XML NF-e (extrator)",
            "papel": papel, "numero": (c.get("ide") or {}).get("nNF"), "chave": c.get("chave"),
            "valor": fmt(valor((c.get("totais") or {}).get("vNF"))), "data": data_iso(((c.get("ide") or {}).get("dhEmi") or "")[:10]),
            "favorecido": (c.get("emitente") or {}).get("xNome") if papel == "ENTRADA" else (c.get("destinatario") or {}).get("xNome"),
            "favorecido_cnpj": emit if papel == "ENTRADA" else dest,
            "cnpjs_empresa": sorted({x for x in (emit, dest) if x in cad["cnpjs"]}),
            "cnpjs_terceiros": sorted({x for x in (emit, dest) if x and x not in cad["cnpjs"]}),
            "identificadores": {"CHAVE": c.get("chave"), "NUMERO": (c.get("ide") or {}).get("nNF")}, "referencias": [],
            "cancelada": "NOTA_CANCELADA" in a.get("marcacoes", []), "campos": {"valor": "vNF", "data": "dhEmi"}, "ausentes": []}


# ---------------------------------------------------------------- conferência

TIPO_RELATORIO_FINANCEIRO = "Relatório financeiro de lançamentos"     # natureza documental definida por Documentos
FONTE_AUXILIAR = "FONTE_AUXILIAR_FINANCEIRA"
NATUREZA = {"NOTA_FISCAL", "GUIA", "RECIBO", "FOLHA"}   # boleto identifica a cobrança, não a natureza (ver PROCEDIMENTO)
# FOLHA = resumo da folha (cópia de suporte do DP): natureza do pagamento de salários, vinculada por referência explícita.


class Conferencia:
    def __init__(self, empresa, competencia, sol):
        self.empresa, self.competencia, self.sol = empresa, competencia, sol
        self.cad = cadastro(empresa)
        self.metodo_empresa = carregar_metodo_empresa(clientes() / empresa, empresa, self.cad['cnpjs'])
        self.pendencias, self.limitacoes, self.duplicidades, self.sugestoes, self.ambiguas = [], [], [], [], []
        self.extratos, self.movimentos, self.relacao, self.documentos, self.ignorados = [], [], [], [], []
        self.ressalvas = []
        self.documentos_pendentes_leitura = []
        self.posicoes, self.posicoes_titulos, self.posicoes_resumo = [], [], None
        # Fonte AUXILIAR (relatório financeiro normalizado): nunca se mistura com extratos/movimentos bancários.
        self.relatorios_financeiros, self.movimentos_auxiliares = [], []
        # Fontes bancárias lidas pelo Normalizador Bancário (contrato comum), utilizáveis ou recusadas.
        self.fontes_bancarias_normalizadas = []
        # Contratos completos (Decimal) usados pelo motor de conciliação banco × relatório.
        self.contratos_bancarios, self.contratos_auxiliares, self.conciliacao = [], [], None

    def pendencia(self, tipo, descricao, referencia=None):
        self.pendencias.append({"id": f"PF-{len(self.pendencias) + 1:02d}", "tipo": tipo, "descricao": descricao, "referencia": referencia})

    # ---- classificação dos arquivos
    def carregar(self, arquivos: list):
        for a in arquivos:
            nome = nome_arquivo(a)
            leitura = a.get("leitura", "")
            destino = encaminhamento(a)
            # Documento de outra área só é usado quando a cópia é destinada ao Financeiro (ex.: resumo da folha → suporte
            # do pagamento de salários). O pacote da área já filtra; aqui vale também para a leitura direta pelo extrator.
            if destino['area'] in ('DP', 'CONCILIACAO') and 'FINANCEIRO' not in destino.get('copias_suporte', []):
                self.ignorados.append({'arquivo': nome, 'motivo': f"DOCUMENTO_DESTINADO_{'AO_DP' if destino['area'] == 'DP' else 'A_CONCILIACAO'}"})
                self.limitacoes.append(f"{nome}: destinado {'ao DP' if destino['area'] == 'DP' else 'à Conciliação'}; "
                                       "não analisado pelo Financeiro.")
                continue
            if destino['area'] == 'DP':
                self.limitacoes.append(f"{nome}: cópia de suporte do DP; usada somente como natureza do pagamento de salários, "
                                       "sem análise de folha pelo Financeiro.")
            if destino['area'] == 'FISCAL':
                self.limitacoes.append(f"{nome}: destinado ao Fiscal; usado aqui somente como possível suporte ao pagamento, sem análise fiscal.")
            c = a.get('conteudo') or {}
            if c.get('leitura_incompleta') or c.get('requer_conferencia_ocr'):
                self.documentos_pendentes_leitura.append(nome)
                self.pendencia('DOCUMENTO_RECEBIDO_LEITURA_PENDENTE', f'{nome}: recebido com leitura parcial ou OCR duvidoso; não utilizado como suporte confirmado.', nome)
                self.ignorados.append({'arquivo': nome, 'motivo': 'LEITURA_PENDENTE'})
                continue
            if not leitura.startswith("EXTRAIDO_"):
                self.documentos_pendentes_leitura.append(nome)
                self.pendencia("DOCUMENTO_ILEGIVEL", f"{nome}: não utilizado ({leitura}: {a.get('observacao', 'conteúdo não extraído')}). "
                               "Envie versão legível (OFX/CSV/PDF digital) ou confira manualmente.", nome)
                self.ignorados.append({"arquivo": nome, "motivo": leitura})
                continue
            if "LIMITE_EXCEDIDO" in a.get("marcacoes", []) or (a.get("conteudo") or {}).get("truncado"):
                self.pendencia("DOCUMENTO_INCOMPLETO", f"{nome}: conteúdo truncado pelo extrator; não utilizado.", nome)
                self.ignorados.append({"arquivo": nome, "motivo": "LIMITE_EXCEDIDO"})
                continue
            if a["extensao"] == ".ofx" or (leitura == "EXTRAIDO_TEXTO" and "<OFX>" in texto_de(a).upper()):
                self.extratos += ler_ofx(a, self.empresa)
                continue
            if leitura == "EXTRAIDO_PDF" and self.carregar_extrato_normalizado(a, nome):
                continue                                   # contrato bancário comum: nenhum leitor específico é usado
            try:
                santander = ler_santander_pdf(a)           # LEGADO: só para PDF sem adaptador no normalizador bancário
            except ValueError as exc:
                self.pendencia("EXTRATO_PDF_NAO_UTILIZADO", f"{nome}: {exc}", nome)
                self.ignorados.append({"arquivo": nome, "motivo": str(exc)})
                continue
            if santander is not None:
                self.extratos += santander
                self.limitacoes.append(f"{nome}: PDF Santander; identificação pela conta cadastrada, sem CNPJ no cabeçalho. "
                                       "Saldos sucessivos conferidos; saldo inicial não informado. Saldo disponível não usado como saldo final do período.")
                self.pendencia("SALDO_INICIAL_AUSENTE", f"{nome}: saldo inicial não informado no layout. "
                               "Os movimentos podem ser conferidos, mas a verificação aritmética integral do mês continua pendente.", nome)
                continue
            if destino.get("tipo") == TIPO_RELATORIO_FINANCEIRO and leitura == "EXTRAIDO_PLANILHA":
                self.carregar_relatorio_financeiro(a, nome)
                continue
            linhas = linhas_tabulares(a)
            if linhas and cabecalho(linhas, CSV_EXTRATO)[0] is not None:
                self.extratos += ler_csv_extrato(a, linhas)
            elif linhas and cabecalho(linhas, CSV_POSICAO)[0] is not None:
                self.posicoes += ler_posicao(a, linhas)
            elif linhas and cabecalho(linhas, {"FAVORECIDO", "VALOR"})[0] is not None:
                self.relacao += ler_relacao(a, linhas)
            elif leitura == "EXTRAIDO_NFE":
                self.documentos.append(ler_nfe(a, self.cad))
            elif leitura in ("EXTRAIDO_TEXTO", "EXTRAIDO_PDF"):
                doc = ler_documento_texto(a, self.cad)
                if doc["tipo"] == "NAO_IDENTIFICADO":
                    self.pendencia("DOCUMENTO_NAO_IDENTIFICADO", f"{nome}: tipo de documento não identificado (não é extrato, relação, "
                                   "comprovante, nota, guia, boleto ou recibo reconhecível).", nome)
                self.documentos.append(doc)
                if doc['tipo'] == 'NAO_IDENTIFICADO' or not doc.get('valor'):
                    self.documentos_pendentes_leitura.append(nome)
            else:
                self.pendencia("FORMATO_NAO_SUPORTADO", f"{nome}: {leitura} não é um formato aceito pela conferência financeira "
                               "(extrato OFX/CSV, relação CSV/XLSX, NF-e XML, documento de texto/PDF).", nome)
                self.ignorados.append({"arquivo": nome, "motivo": leitura})
        for d in self.documentos:
            if d.get("ausentes") and d["tipo"] != "NAO_IDENTIFICADO":
                self.pendencia("DADO_AUSENTE", f"{d['arquivo']} ({d['tipo']}): {', '.join(d['ausentes'])} não localizado(s) no texto.", d["arquivo"])
            outras = sorted({self.cad["cnpjs_outras_empresas"][c] for c in d.get("cnpjs_terceiros", []) if c in self.cad["cnpjs_outras_empresas"]})
            if outras and not d.get("cnpjs_empresa"):
                d["bloqueado"] = f"documento identifica outra empresa cadastrada ({', '.join(outras)}) e não esta empresa"
                self.pendencia("ISOLAMENTO", f"{d['arquivo']}: {d['bloqueado']}; não utilizado.", d["arquivo"])
            elif d.get("cnpjs_terceiros") and not d.get("cnpjs_empresa") and d["tipo"] != "NAO_IDENTIFICADO" and not d.get("papel"):
                # Outra empresa não cadastrada: CNPJs identificados no texto, nenhum desta empresa (mesma regra de Documentos).
                d["bloqueado"] = ("documento não identifica esta empresa (CNPJs: " + ", ".join(d["cnpjs_terceiros"]) + ")")
                self.pendencia("ISOLAMENTO", f"{d['arquivo']}: {d['bloqueado']}; não utilizado. Confirmar a titularidade "
                               "ou enviar o documento na solicitação da empresa correta.", d["arquivo"])
            if d.get("papel") == "TERCEIROS" and not d.get("bloqueado"):
                d["bloqueado"] = "NF-e sem esta empresa como emitente ou destinatária (titularidade)"
                self.pendencia("ISOLAMENTO", f"{d['arquivo']}: {d['bloqueado']}; não utilizada.", d["arquivo"])
            if d.get("cancelada"):
                d["bloqueado"] = "nota fiscal cancelada"
                self.pendencia("DOCUMENTO_CANCELADO", f"{d['arquivo']}: NF-e cancelada; não sustenta pagamento.", d["arquivo"])

    # ---- fonte auxiliar: relatório financeiro → Normalizador Financeiro (NÃO é extrato bancário)
    def carregar_relatorio_financeiro(self, a: dict, nome: str):
        try:
            r = nf.normalizar(a)
        except Exception as exc:                       # falha do normalizador vira pendência; nunca derruba a conferência
            self.pendencia("RELATORIO_FINANCEIRO_NAO_NORMALIZADO", f"{nome}: falha ao normalizar o relatório financeiro "
                           f"({type(exc).__name__}); nenhum movimento auxiliar foi usado.", nome)
            self.ignorados.append({"arquivo": nome, "motivo": "FALHA_NORMALIZADOR"})
            self.relatorios_financeiros.append({"arquivo": nome, "sha256": a.get("sha256"), "situacao": "NAO_NORMALIZADO",
                                                "falha": type(exc).__name__})
            return
        if r["situacao"] == "NAO_NORMALIZADO":
            motivo = "; ".join(p["problema"] for p in r["pendencias"] if p["nivel"] == nf.BLOQUEIO) or "relatório não normalizado"
            self.pendencia("RELATORIO_FINANCEIRO_NAO_NORMALIZADO", f"{motivo} Nenhum movimento auxiliar foi usado.", nome)
            self.ignorados.append({"arquivo": nome, "motivo": "RELATORIO_FINANCEIRO_NAO_NORMALIZADO"})
        else:
            grupos = {}
            for p in r["pendencias"]:
                if p["nivel"] != nf.INFORMATIVO:
                    grupos.setdefault(p["codigo"], []).append(p)
            for codigo, lista in grupos.items():
                p = lista[0]
                texto_p = p["problema"] if len(lista) == 1 else f"{nome}: {len(lista)} linha(s) com {codigo}."
                self.pendencia(f"RELATORIO_FINANCEIRO_{codigo}", f"{texto_p} Impacto: {p['impacto']} O que fazer: {p['o_que_fazer']}", nome)
            self.limitacoes.append(f"{nome}: relatório financeiro usado como FONTE AUXILIAR ({r['resumo']['movimentos']} movimento(s) "
                                   "normalizado(s)); não é extrato bancário e não comprova movimentação na conta.")
        if r["situacao"] != "NAO_NORMALIZADO":
            self.contratos_auxiliares.append(r)
        self.movimentos_auxiliares += [dict(nf.para_json(m), fonte=FONTE_AUXILIAR) for m in r["movimentos"]]
        self.relatorios_financeiros.append(nf.para_json({k: r[k] for k in (
            "contrato", "versao", "tipo_fonte", "adaptador", "origem", "situacao", "abas", "campos_ausentes",
            "campos_complementares_ausentes", "resumo", "pendencias", "linhas_nao_realizadas", "linhas_ignoradas") if k in r}))

    # ---- fonte bancária: documento → Normalizador Bancário → contrato comum (MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1)
    def carregar_extrato_normalizado(self, a: dict, nome: str) -> bool:
        """True = o normalizador bancário tratou o documento (fonte utilizável ou recusada); False = nenhum adaptador
        reconheceu a estrutura (o documento segue para os demais leitores, inclusive o legado)."""
        try:
            r = nb.normalizar(a)
        except Exception as exc:                       # falha técnica: recusa explícita, nunca leitura parcial
            self.pendencia("EXTRATO_BANCARIO_RECUSADO", f"{nome}: falha técnica na leitura bancária ({type(exc).__name__}). "
                           "Impacto: o documento não foi usado como extrato. O que fazer: enviar novamente ou conferir manualmente.", nome)
            self.ignorados.append({"arquivo": nome, "motivo": "EXTRATO_BANCARIO_FALHA_TECNICA"})
            return True
        codigos = [p["codigo"] for p in r["pendencias"]]
        if r["adaptador"] is None and codigos == ["FONTE_SEM_ADAPTADOR"]:
            return False
        resumo = nb.para_json({k: v for k, v in r.items() if k not in ("movimentos", "movimentos_nao_confirmados")})
        utilizavel = r["situacao"] in ("NORMALIZADO", "NORMALIZADO_COM_PENDENCIAS")
        self.fontes_bancarias_normalizadas.append(dict(resumo, arquivo=nome, utilizavel=utilizavel))
        if not utilizavel:
            for p in r["pendencias"]:
                if p["nivel"] == nb.BLOQUEIO:
                    self.pendencia("EXTRATO_BANCARIO_RECUSADO", f"{nome}: {p['problema']} Impacto: {p['impacto']} "
                                   f"O que fazer: {p['o_que_fazer']} ({p['codigo']})", nome)
            self.ignorados.append({"arquivo": nome, "motivo": "EXTRATO_BANCARIO_RECUSADO: " + ", ".join(codigos)})
            return True
        for p in r["pendencias"]:
            if p["nivel"] != nb.INFORMATIVO:
                self.pendencia(f"EXTRATO_BANCARIO_{p['codigo']}", f"{nome}: {p['problema']} Impacto: {p['impacto']} "
                               f"O que fazer: {p['o_que_fazer']}", nome)
        self.contratos_bancarios.append({"arquivo": nome, "contrato": r})
        self.extratos.append({
            "arquivo": nome, "formato": f"NORMALIZADO:{r['adaptador']}", "banco": r["banco"]["codigo"], "agencia": r["agencia"],
            "conta": r["conta"], "titular": None, "inicio": r["periodo_inicio"], "fim": r["periodo_fim"],
            "saldo_inicial": r["saldo_inicial"]["valor"], "data_saldo_inicial": r["saldo_inicial"]["data"],
            "saldo_final": r["saldo_final"]["valor"], "data_saldo_final": r["saldo_final"]["data"],
            "movimentos": [{"data": m["data"], "valor_assinado": m["valor"] if m["natureza"] == "CREDITO" else -m["valor"],
                            "descricao": m["descricao"], "identificadores": {"DOCUMENTO": m["documento"]} if m["documento"] else {},
                            "tipo_banco": None, "origem": f"{nome} · página {m['pagina']}, linha {m['linhas']['linha_inicial']}",
                            "rastreio": {"contrato": nb.CONTRATO, "id": m["id"], "sha256": m["sha256_origem"], "pagina": m["pagina"],
                                         "linhas": m["linhas"], "natureza": m["natureza"]}} for m in r["movimentos"]]})
        self.limitacoes.append(f"{nome}: extrato lido pelo Normalizador Bancário ({r['adaptador']}); aritmética e saldos diários "
                               "conferidos sem tolerância. Titular informado pelo banco por nome (CNPJ não consta no leiaute); a "
                               "titularidade é verificada pela conta cadastrada.")
        return True

    def saida_fontes(self) -> dict:
        """Campos NOVOS do resultado (retrocompatíveis): fonte bancária e fonte auxiliar, sempre separadas."""
        movs = self.movimentos_auxiliares
        conta = lambda n: sum(1 for m in movs if m["natureza"] == n)
        soma = lambda n: fmt(sum((Decimal(m["valor"]) for m in movs if m["natureza"] == n), Decimal("0.00")))
        return {
            "fonte_bancaria": {"tipo": "EXTRATO_BANCARIO", "extratos_recebidos": len(self.extratos),
                               "extratos_utilizaveis": sum(1 for e in self.extratos if e.get("aceito")),
                               "movimentos_bancarios": len(self.movimentos), "contrato": nb.CONTRATO,
                               "fontes_normalizadas": self.fontes_bancarias_normalizadas},
            "fonte_auxiliar_financeira": {
                "tipo": FONTE_AUXILIAR, "contrato": nf.CONTRATO,
                "aviso": "Relatório financeiro é fonte AUXILIAR: não substitui extrato bancário, não conclui a conferência "
                         "bancária e não gera lançamento contábil.",
                "relatorios": self.relatorios_financeiros,
                "resumo": {"relatorios": len(self.relatorios_financeiros), "movimentos": len(movs),
                           "entradas": conta("ENTRADA"), "saidas": conta("SAIDA"), "indeterminadas": conta("INDETERMINADA"),
                           "total_entradas": soma("ENTRADA"), "total_saidas": soma("SAIDA"),
                           "nao_realizadas": sum(len(r.get("linhas_nao_realizadas") or []) for r in self.relatorios_financeiros),
                           "pendencias": sum(1 for r in self.relatorios_financeiros for p in r.get("pendencias") or []
                                             if p.get("nivel") != nf.INFORMATIVO) +
                                         sum(1 for r in self.relatorios_financeiros if r.get("falha"))}},
            "movimentos_financeiros_auxiliares": movs,
            "conciliacao_financeira": cf.para_json(self.conciliacao) if self.conciliacao else None}

    # ---- conciliação financeira banco × relatório + regra fail-closed (somente movimentos do contrato bancário comum)
    def conciliar_fontes(self) -> list:
        """Executa o motor quando há extrato normalizado ACEITO (conta cadastrada). Anota cada movimento bancário com a
        classificação da associação, sem alterar suportes, situação ou documentos. Devolve o bloqueio do lote (ou [])."""
        aceitos = {e["arquivo"] for e in self.extratos if e.get("aceito")}
        fontes = [c["contrato"] for c in self.contratos_bancarios if c["arquivo"] in aceitos]
        if not fontes:
            return []
        self.conciliacao = cf.conciliar(fontes, self.contratos_auxiliares)
        por_id = {i: x for x in self.conciliacao["associacoes"] for i in x["bancarios"]}
        efetivas = self.decisoes_supervisor_efetivas()
        liberados_supervisor = {i for x in self.conciliacao["associacoes"] if x["id"] in efetivas
                                for i in dcs.ids_confirmados(x, efetivas[x["id"]])[0]}      # só aprovação vigente e válida
        pendentes = Counter()
        for m in self.movimentos:
            rid = (m.get("rastreio_bancario") or {}).get("id")
            if not rid:
                continue                                  # leiautes antigos (CSV/OFX/PDF legado): regra anterior, inalterada
            x = por_id.get(rid)
            m["conciliacao_financeira"] = {"classificacao": x["classificacao"] if x else "NAO_CONCILIADO",
                                           "associacao": x["id"] if x else None, "auxiliares": x["auxiliares"] if x else [],
                                           "libera_associacao_financeira": bool(x and x["libera_associacao_financeira"]),
                                           "suporte_documental": False}
            if x and x["id"] in efetivas:                 # camada separada: a classificação do motor fica como veio
                ev = efetivas[x["id"]]
                m["conciliacao_financeira"]["decisao_supervisor"] = {"decisao": ev["decisao"], "evento": ev["id"], "em": ev["em"],
                                                                     "estado_operacional": dcs.estado_operacional(x, ev)}
            suporte_independente = m.get("situacao") in ("COM_SUPORTE", "TRANSFERENCIA_PROPRIA")
            confirmada_supervisor = rid in liberados_supervisor
            if m["conciliacao_financeira"]["classificacao"] != "CONCILIADO" and not suporte_independente and not confirmada_supervisor:
                pendentes[m["conciliacao_financeira"]["classificacao"]] += 1
        if not pendentes:
            return []
        total = sum(pendentes.values())
        detalhe = ", ".join(f"{n} {r}" for r, n in (("prováveis", pendentes["PROVAVEL"]), ("ambíguas", pendentes["AMBIGUO"]),
                                                    ("não conciliadas", pendentes["NAO_CONCILIADO"])) if n)
        self.pendencia("ASSOCIACAO_FINANCEIRA_NAO_CONFIRMADA",
                       f"Problema: existem movimentações bancárias que ainda não possuem associação financeira confirmada "
                       f"({total} de {len([m for m in self.movimentos if m.get('rastreio_bancario')])}: {detalhe}). "
                       "Impacto: essas movimentações não podem seguir automaticamente para tratamento contábil. "
                       "O que fazer: revisar as associações sugeridas ou fornecer documentação/suporte adicional.")
        return [f"Existem {total} movimentação(ões) bancária(s) sem associação financeira confirmada nem suporte independente "
                f"({detalhe}); o lote não segue automaticamente para a proposta contábil. Revisar as associações sugeridas "
                "ou fornecer documentação/suporte adicional."]

    def decisoes_supervisor_efetivas(self) -> dict:
        """Decisões do Supervisor (DECISOES_SUPERVISOR_CONCILIACAO_V1) que ainda valem para esta conciliação. Registro ausente
        → nenhuma; registro inválido/de outro contexto → nenhuma + pendência (fail-closed: nada é liberado)."""
        dados = getattr(self, "decisoes_conciliacao", None)
        if dados is None:
            return {}
        try:
            dcs.validar(dados, {"sol": self.sol, "empresa": self.empresa, "competencia": self.competencia})
        except dcs.EstadoCorrompido as exc:
            self.pendencia("DECISOES_SUPERVISOR_INVALIDAS", f"Problema: o registro de decisões do Supervisor sobre a conciliação "
                           f"financeira não pôde ser usado ({exc}). Impacto: nenhuma decisão foi aplicada; as associações seguem "
                           "pendentes. O que fazer: avisar o responsável técnico; as decisões não foram presumidas.")
            return {}
        return dcs.decisoes_efetivas(dados, self.conciliacao)[0]

    # ---- extratos: conta, titular, período, saldos, duplicidades
    def preparar_movimentos(self):
        ano, mes = map(int, self.competencia.split("-"))
        primeiro = dt.date(ano, mes, 1)
        ultimo = (dt.date(ano + mes // 12, mes % 12 + 1, 1) - dt.timedelta(days=1))
        por_id, contas = {}, {}
        for e in self.extratos:
            chave = chave_conta(e["banco"], e["agencia"], e["conta"])
            e["conta_chave"] = chave
            cadastrada = self.cad["contas"].get(chave)
            if not cadastrada:
                e["aceito"] = False
                self.pendencia("CONTA_NAO_CADASTRADA", f"{e['arquivo']}: conta {chave} não consta no CADASTRO.md de {self.empresa}; "
                               "extrato não utilizado (sem mistura de empresas ou contas).", e["arquivo"])
                continue
            if e.get("titular") and e["titular"] not in self.cad["cnpjs"]:
                e["aceito"] = False
                self.pendencia("ISOLAMENTO", f"{e['arquivo']}: titular {e['titular']} diferente da empresa; extrato não utilizado.", e["arquivo"])
                continue
            e["aceito"] = True
            e["ids"] = []
            soma = Decimal("0.00")
            ordinais = {}
            for m in e["movimentos"]:
                if m["data"] is None or m["valor_assinado"] is None:
                    self.pendencia("MOVIMENTO_ILEGIVEL", f"{m['origem']}: data ou valor ausente; movimento não utilizado.", m["origem"])
                    continue
                soma += m["valor_assinado"]
                fitid = m["identificadores"].get("FITID")
                if fitid:
                    ident = hash_curto(self.empresa, chave, "FITID", fitid)
                else:
                    base = (self.empresa, chave, m["data"], fmt(m["valor_assinado"]), m["identificadores"].get("DOCUMENTO", ""), norm(m["descricao"]))
                    ordinais[base] = ordinais.get(base, 0) + 1
                    ident = hash_curto(*base, ordinais[base])
                mov = {"id": f"MOV-{ident}", "empresa": self.empresa, "competencia": self.competencia, "conta": chave,
                       "data": m["data"], "valor": fmt(abs(m["valor_assinado"])), "direcao": "DEBITO" if m["valor_assinado"] < 0 else "CREDITO",
                       "descricao": m["descricao"], "identificadores": m["identificadores"], "tipo_banco": m["tipo_banco"],
                       "origens": [m["origem"]]}
                if m.get("rastreio"):                          # origem no contrato bancário comum (id, SHA, página, linhas)
                    mov["rastreio_bancario"] = m["rastreio"]
                e["ids"].append(mov["id"])
                if mov["id"] in por_id:
                    por_id[mov["id"]]["origens"].append(m["origem"])
                    self.duplicidades.append({"tipo": "SOBREPOSICAO_DE_EXTRATOS", "movimento": mov["id"],
                                              "descricao": f"mesmo movimento ({'FITID ' + fitid if fitid else 'mesmos dados e posição'}) em "
                                                           f"{por_id[mov['id']]['origens'][0]} e {m['origem']}; considerado UMA vez."})
                    continue
                por_id[mov["id"]] = mov
            # consistência aritmética e cobertura do período
            verif = {"arquivo": e["arquivo"], "conta": chave, "formato": e["formato"], "inicio": e["inicio"], "fim": e["fim"],
                     "saldo_inicial": fmt(e["saldo_inicial"]), "saldo_final": fmt(e["saldo_final"]), "soma_movimentos": fmt(soma)}
            if e["saldo_inicial"] is not None and e["saldo_final"] is not None:
                esperado = e["saldo_inicial"] + soma
                verif["aritmetica"] = "CONSISTENTE" if esperado == e["saldo_final"] else "DIVERGENTE"
                if esperado != e["saldo_final"]:
                    verif["diferenca"] = fmt(e["saldo_final"] - esperado)
                    self.pendencia("EXTRATO_INCONSISTENTE", f"{e['arquivo']}: saldo inicial {fmt(e['saldo_inicial'])} + movimentos {fmt(soma)} = "
                                   f"{fmt(esperado)} ≠ saldo final {fmt(e['saldo_final'])} (diferença {verif['diferenca']}); "
                                   "faltam movimentos ou páginas.", e["arquivo"])
            else:
                verif["aritmetica"] = "NAO_VERIFICAVEL"
                verif["motivo"] = "saldo inicial ou final ausente; não foi presumido para fechar a verificação"
            if e.get("saldos_sucessivos"):
                verif["saldos_sucessivos"] = e["saldos_sucessivos"]
                verif["paginas_lidas"] = e["paginas_lidas"]
            contas.setdefault(chave, []).append(verif)
        self.verificacoes = []
        for chave, lista in contas.items():
            periodos = sorted((v["inicio"], v["fim"]) for v in lista if v["inicio"] and v["fim"])
            coberto, cursor = False, primeiro
            for ini, fim in periodos:
                if dt.date.fromisoformat(ini) <= cursor:
                    cursor = max(cursor, dt.date.fromisoformat(fim) + dt.timedelta(days=1))
            coberto = cursor > ultimo
            aritmeticas = {v["aritmetica"] for v in lista}
            situacao = ("CONCLUIDA" if coberto and aritmeticas == {"CONSISTENTE"} else
                        "INCOMPLETA" if not coberto or "DIVERGENTE" in aritmeticas else "SEM_VERIFICACAO_ARITMETICA")
            self.verificacoes.append({"conta": chave, "cobertura_competencia": "COMPLETA" if coberto else "INCOMPLETA",
                                      "periodos": [f"{a} a {b}" for a, b in periodos], "situacao": situacao, "extratos": lista})
            if not coberto:
                self.pendencia("EXTRATO_INCOMPLETO", f"Conta {chave}: os extratos enviados ({', '.join(f'{a} a {b}' for a, b in periodos) or 'sem período'}) "
                               f"não cobrem toda a competência {self.competencia}; a verificação não está concluída.", chave)
        for chave in self.cad["contas"]:
            if chave not in contas:
                self.limitacoes.append(f"Conta {chave} cadastrada sem extrato neste lote: movimentos dessa conta não foram conferidos.")
        self.movimentos = sorted(por_id.values(), key=lambda m: (m["conta"], m["data"], m["id"]))
        # mesmos dados no mesmo dia (identificadores diferentes): possível duplicidade a confirmar
        grupos = {}
        for m in self.movimentos:
            grupos.setdefault((m["conta"], m["data"], m["direcao"], m["valor"]), []).append(m["id"])
        for (conta, data, direcao, v), ids in grupos.items():
            if len(ids) > 1:
                self.duplicidades.append({"tipo": "MESMO_VALOR_E_DATA", "movimentos": ids,
                                          "descricao": f"{len(ids)} movimentos de {direcao} {v} em {data} na conta {conta} com "
                                                       "identificadores diferentes: possível duplicidade a confirmar (mantidos separados)."})
        for m in self.movimentos:
            if not (str(primeiro) <= m["data"] <= str(ultimo)):
                m.setdefault("divergencias", []).append(f"data {m['data']} fora da competência {self.competencia}")
        # divergência entre extratos sobrepostos da mesma conta: movimento do período comum presente em um e ausente no outro
        porid = {m["id"]: m for m in self.movimentos}
        aceitos = [e for e in self.extratos if e.get("aceito") and e["inicio"] and e["fim"]]
        for a in aceitos:
            for b in aceitos:
                if a is b or a["conta_chave"] != b["conta_chave"]:
                    continue
                ini, fim = max(a["inicio"], b["inicio"]), min(a["fim"], b["fim"])
                if ini > fim:
                    continue
                faltam = [i for i in dict.fromkeys(a["ids"]) if ini <= porid[i]["data"] <= fim and i not in b["ids"]]
                for i in faltam:
                    texto = (f"movimento de {porid[i]['data']} ({porid[i]['valor']}) consta em {a['arquivo']} e falta em {b['arquivo']}, "
                             f"que declara cobrir {b['inicio']} a {b['fim']}")
                    porid[i].setdefault("divergencias", []).append(f"divergência entre extratos: {texto}")
                    self.pendencia("DIVERGENCIA_ENTRE_EXTRATOS", f"Conta {a['conta_chave']}: {texto}.", i)

    def triagem(self) -> list:
        """Bloqueio do LOTE INTEIRO (o Financeiro não confere e Bancos não roda). Pendência de documento/movimento não entra aqui."""
        bloqueios = []
        ano, mes = map(int, self.competencia.split("-"))
        primeiro = str(dt.date(ano, mes, 1))
        ultimo = str(dt.date(ano + mes // 12, mes % 12 + 1, 1) - dt.timedelta(days=1))
        aceitos = [e for e in self.extratos if e.get("aceito")]
        if not aceitos:
            bloqueios.append("Nenhum extrato utilizável de conta cadastrada desta empresa (extrato ausente, ilegível ou de outro titular): "
                             "titularidade do lote indeterminada e arquivo essencial indisponível.")
            if any(r.get("situacao") != "NAO_NORMALIZADO" for r in self.relatorios_financeiros):
                bloqueios.append("Relatório financeiro processado como fonte auxiliar, porém nenhum extrato bancário utilizável foi "
                                 "localizado para a conta; o relatório não substitui o extrato.")
            return bloqueios
        periodos = [(e["inicio"], e["fim"]) for e in aceitos if e["inicio"] and e["fim"]]
        datas = [m["data"] for m in self.movimentos]
        sobrepoe = any(ini <= ultimo and fim >= primeiro for ini, fim in periodos)
        if not sobrepoe and not any(primeiro <= d <= ultimo for d in datas):
            achado = ", ".join(f"{a} a {b}" for a, b in sorted(set(periodos))) or (f"movimentos de {min(datas)} a {max(datas)}" if datas else "sem datas")
            bloqueios.append(f"Competência da solicitação ({self.competencia}) não corresponde aos extratos enviados ({achado}). "
                             "Confirme a competência e abra nova solicitação; nada foi conferido nem escriturado.")
        return bloqueios

    def montar_bloqueado(self, bloqueios: list, ressalvas: list) -> dict:
        return {
            "agente": "FINANCEIRO", "versao": VERSAO, "procedimento": PROCEDIMENTO, "sol": self.sol, "empresa": self.empresa,
            "competencia": self.competencia, "modo": "SIMULACAO", "executado_em": dt.datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "aviso": "LOTE BLOQUEADO: a conferência não foi feita e nada segue para Contabilidade/Bancos.",
            "bloqueio_lote": bloqueios, "ressalvas_documentos": ressalvas, "verificacao_extratos": getattr(self, "verificacoes", []),
            "movimentos": [], "resumo": {"movimentos": 0, "com_suporte": 0, "comprovante_sem_natureza": 0, "sem_suporte": 0, "ambiguos": 0,
                                         "transferencias_proprias": 0, "ja_escriturados": 0, "com_proposta_anterior_simulacao": 0,
                                         "relacionados_sem_movimento": 0, "duplicidades": 0, "pendencias": len(self.pendencias),
                                         "movimentos_encontrados": len(self.movimentos)},
            "relacionados_sem_movimento": [], "ambiguas": [], "sugestoes": [], "duplicidades": self.duplicidades, "pendencias": self.pendencias,
            "documentos": self.documentos, "relacao": self.relacao, "ignorados": self.ignorados, "limitacoes": self.limitacoes,
            "posicoes_titulos": [], "posicoes_titulos_resumo": None, **self.saida_fontes()}

    # ---- correspondências
    PALAVRAS_COMUNS = {"LTDA", "EIRELI", "FICTICIA", "FICTICIO", "COMERCIO", "SERVICOS", "INDUSTRIA", "EMPRESA", "BRASIL", "PRESTADOR",
                       "PAGAMENTO", "PAGTO", "DOCUMENTO", "ENVIADO", "RECEBIDO", "TRANSF"}

    def evidencia(self, m, identificadores, favorecidos, cnpjs):
        """Identificador comum entre o documento e o movimento do extrato (texto exato, sem tolerância). None se não houver."""
        alvo = norm(" ".join(m["identificadores"].values()) + " " + m["descricao"])
        palavras = set(re.findall(r"[A-Z0-9]+", alvo))
        for v in identificadores:
            v = norm(v)
            if v and len(re.sub(r"\W", "", v)) >= 4 and v in alvo:
                return f"identificador '{v}' presente no extrato"
        for c in cnpjs:
            if c and c in digitos(alvo):
                return f"CNPJ do favorecido {c} presente no histórico"
        for f in favorecidos:
            for t in re.findall(r"[A-Z0-9]+", norm(f)):
                if len(t) >= 4 and t not in self.PALAVRAS_COMUNS and t in palavras:
                    return f"favorecido '{t}' presente no histórico do extrato"
        return None

    def candidatos(self, valor_alvo, data_alvo, direcao="DEBITO", conta=None):
        alvo = None
        partes = [x for x in re.split(r"[-/ ]", conta or "") if x]
        if len(partes) >= 3:
            alvo = chave_conta(partes[0], partes[1], "".join(partes[2:]))
        return [m for m in self.movimentos if m["direcao"] == direcao and m["valor"] == valor_alvo and m["data"] == data_alvo
                and (alvo is None or m["conta"] == alvo)]

    def corresponder(self, decisoes: dict):
        for m in self.movimentos:
            m.update(relacao=[], comprovantes=[], suportes=[], fundamentos=[], divergencias=m.get("divergencias", []), ausentes=[],
                     sugestoes=[], ambiguidades=[], decisoes=[])
        mov = {m["id"]: m for m in self.movimentos}
        docs = {d["id"]: d for d in self.documentos}
        rels = {r["id"]: r for r in self.relacao}
        usaveis = [d for d in self.documentos if not d.get("bloqueado") and d.get("valor")]
        comprovantes = [d for d in usaveis if d["tipo"] == "COMPROVANTE"]
        suportes = [d for d in usaveis if d["tipo"] in NATUREZA | {"BOLETO"}]

        # decisões registradas do Supervisor (somente para este caso): vínculos escolhidos
        decididos = set()
        for mid, lista in decisoes.items():
            for d in lista:
                if d.get("tipo") != "VINCULAR" or mid not in mov:
                    continue
                for ref in d.get("vinculos", []):
                    alvo = docs.get(ref) or rels.get(ref)
                    if not alvo:
                        continue
                    destino = "relacao" if ref in rels else "comprovantes" if alvo["tipo"] == "COMPROVANTE" else "suportes"
                    if ref not in mov[mid][destino]:
                        mov[mid][destino].append(ref)
                    decididos.add(ref)
                mov[mid]["decisoes"].append(d)
                mov[mid]["fundamentos"].append(f"vínculo definido pelo Supervisor em {d.get('em')}: {d.get('justificativa')}")

        # Valor e data iguais só SELECIONAM candidatos. O vínculo é CONFIRMADO apenas com titularidade (o documento identifica
        # esta empresa como pagadora, ou a relação informa a conta pagadora igual à do extrato) E um identificador comum
        # (autenticação/ID/documento, CNPJ ou nome do favorecido no histórico do extrato). Faltando um deles: SUGESTÃO.
        def sugerir(m, chave, valor_ref, descricao):
            self.sugestoes.append({"movimento": m["id"], chave: valor_ref, "descricao": descricao})
            m["sugestoes"].append(descricao)

        # A) comprovante → movimento
        reivindicados = {}
        for c in comprovantes:
            if c["id"] in decididos:
                continue
            cands = self.candidatos(c["valor"], c["data"])
            titular = bool(c.get("cnpjs_empresa"))
            fortes = [(m, e) for m in cands for e in [self.evidencia(m, c["identificadores"].values(), [c.get("favorecido")], [c.get("favorecido_cnpj")])] if e]
            if titular and len(fortes) == 1:
                m, e = fortes[0]
                reivindicados.setdefault(m["id"], []).append((c, f"valor e data idênticos; pagador = esta empresa; {e}"))
            elif len(cands) > 1:
                self.ambiguas.append({"origem": c["id"], "arquivo": c["arquivo"], "tipo": "COMPROVANTE", "candidatos": [m["id"] for m in cands],
                                      "descricao": f"comprovante {c['arquivo']} ({c['valor']} em {c['data']}) corresponde a {len(cands)} movimentos "
                                                   f"({len(fortes)} com identificador comum); escolha exige conferência do Supervisor."})
                for m in cands:
                    m["ambiguidades"].append(f"comprovante {c['arquivo']} também corresponde a outro movimento")
            elif len(cands) == 1:
                falta = ", ".join(x for x, ok in (("titularidade (pagador = esta empresa)", titular), ("identificador comum", bool(fortes))) if not ok)
                sugerir(cands[0], "documento", c["id"], f"comprovante {c['arquivo']}: valor e data iguais, mas sem {falta}; não confirmado (requer conferência).")
                c["sem_movimento"] = True
            else:
                for m in (x for x in self.movimentos if x["direcao"] == "DEBITO" and x["valor"] == c["valor"]):
                    sugerir(m, "documento", c["id"], f"comprovante {c['arquivo']} com mesmo valor {c['valor']} mas data {c['data']} ≠ {m['data']} "
                                                     "do extrato (sem tolerância aprovada: não confirmado).")
                c["sem_movimento"] = True
        for mid, lista in reivindicados.items():
            if len(lista) > 1:
                self.ambiguas.append({"origem": mid, "tipo": "MOVIMENTO", "candidatos": [c["id"] for c, _ in lista],
                                      "descricao": f"{len(lista)} comprovantes correspondem ao movimento {mid}; possível comprovante duplicado."})
                mov[mid]["ambiguidades"].append("mais de um comprovante para o mesmo movimento")
            else:
                c, base = lista[0]
                mov[mid]["comprovantes"].append(c["id"])
                mov[mid]["fundamentos"].append(f"comprovante {c['arquivo']}: {base}")

        # B) relação de pagamentos (item isolado ou agrupado por pagamento_id) → movimento
        # PAGAMENTO casa com DÉBITO; RECEBIMENTO casa com CRÉDITO, pelas mesmas regras (CONTA da relação = conta do
        # extrato + identificador comum). Agrupamento por pagamento_id nunca mistura os dois tipos.
        grupos = {}
        for r in self.relacao:
            if r["id"] in decididos:
                continue
            direcao = r.get("direcao") if r.get("tipo") else "DEBITO"
            if not direcao:
                self.pendencia("DADO_INVALIDO", f"Relação: {r['origem']} com TIPO '{r.get('tipo')}' (aceitos: PAGAMENTO ou "
                               "RECEBIMENTO); item não utilizado.", r["id"])
                continue
            grupos.setdefault((r.get("pagamento_id") or r["id"], direcao), []).append(r)
        alvo_por_grupo = {}
        for (gid, direcao), itens in grupos.items():
            if any(i["valor"] is None or i["data"] is None for i in itens):
                self.pendencia("DADO_AUSENTE", f"Relação: {', '.join(i['origem'] for i in itens)} sem valor ou data.", gid)
                continue
            total = fmt(sum(valor(i["valor"]) for i in itens))
            datas = {i["data"] for i in itens}
            if len(datas) > 1:
                self.pendencia("DIVERGENCIA", f"Relação: pagamento agrupado {gid} com datas diferentes ({', '.join(sorted(datas))}).", gid)
                continue
            data_grupo = datas.pop()
            contas = {i["conta"] for i in itens}
            titular = len(contas) == 1 and None not in contas      # conta pagadora informada (o filtro exige que seja a do extrato)
            cands = self.candidatos(total, data_grupo, direcao=direcao, conta=itens[0]["conta"])
            fortes = [(m, e) for m in cands for e in [self.evidencia(m, [x for i in itens for x in i["referencias"] + ([i["titulo"]] if i.get("titulo") else [])], [i["favorecido"] for i in itens],
                                                                     [i["favorecido_cnpj"] for i in itens])] if e]
            if titular and len(fortes) == 1:
                m, e = fortes[0]
                alvo_por_grupo.setdefault(m["id"], []).append((gid, itens, e, direcao))
            elif len(cands) > 1:
                self.ambiguas.append({"origem": gid, "tipo": "RELACAO", "candidatos": [m["id"] for m in cands],
                                      "descricao": f"item(ns) da relação {', '.join(i['origem'] for i in itens)} ({total}) corresponde(m) a "
                                                   f"{len(cands)} movimentos; escolha exige conferência do Supervisor."})
                for m in cands:
                    m["ambiguidades"].append(f"relação {gid} corresponde também a outro movimento")
            elif len(cands) == 1:
                falta = ", ".join(x for x, ok in (("conta pagadora" if direcao == "DEBITO" else "conta recebedora", titular), ("identificador comum", bool(fortes))) if not ok)
                sugerir(cands[0], "relacao", [i["id"] for i in itens], f"relação {gid}: valor e data iguais, mas sem {falta}; não confirmado (requer conferência).")
                for i in itens:
                    i["sem_movimento"] = True
            else:
                for m in (x for x in self.movimentos if x["direcao"] == direcao and x["valor"] == total):
                    sugerir(m, "relacao", [i["id"] for i in itens], f"relação {gid} com mesmo valor {total} mas data {data_grupo} ≠ {m['data']} "
                                                                    "do extrato (não confirmado).")
                for i in itens:
                    i["sem_movimento"] = True
        for mid, lista in alvo_por_grupo.items():
            if len(lista) > 1:
                self.ambiguas.append({"origem": mid, "tipo": "MOVIMENTO", "candidatos": [g for g, _, _, _ in lista],
                                      "descricao": f"{len(lista)} itens/grupos da relação correspondem ao movimento {mid}."})
                mov[mid]["ambiguidades"].append("mais de um item da relação para o mesmo movimento")
                continue
            gid, itens, e, direcao = lista[0]
            mov[mid]["relacao"] += [i["id"] for i in itens]
            mov[mid]["fundamentos"].append(f"relação {', '.join(i['origem'] for i in itens)}: valor"
                                           f"{' somado do pagamento agrupado ' + gid if len(itens) > 1 else ''} e data idênticos; "
                                           f"conta {'pagadora' if direcao == 'DEBITO' else 'recebedora'} = conta do extrato; {e}")

        # C) natureza: referências explícitas (relação / comprovante) → documento de suporte
        def achar(ref: str, cnpj=None):
            dig = digitos(ref)
            if not dig:
                return []
            achados = [s for s in suportes if dig in {digitos(s.get("numero")), digitos(s.get("chave")), digitos((s.get("identificadores") or {}).get("LINHA DIGITAVEL"))} - {""}]
            if cnpj:
                achados = [s for s in achados if not s.get("favorecido_cnpj") or s["favorecido_cnpj"] == cnpj] or achados
            return achados

        for m in self.movimentos:
            refs = [(ref, rels[r]["favorecido_cnpj"], f"relação {rels[r]['origem']}") for r in m["relacao"] for ref in rels[r]["referencias"]]
            refs += [(ref, docs[c].get("favorecido_cnpj"), f"comprovante {docs[c]['arquivo']}") for c in m["comprovantes"] for ref in docs[c]["referencias"]]
            refs += [(docs[c]["identificadores"]["LINHA DIGITAVEL"], None, f"comprovante {docs[c]['arquivo']}") for c in m["comprovantes"]
                     if docs[c]["identificadores"].get("LINHA DIGITAVEL")]
            for ref, cnpj, fonte in refs:
                achados = achar(ref, cnpj)
                if len(achados) == 1:
                    s = achados[0]
                    if s["id"] not in m["suportes"]:
                        m["suportes"].append(s["id"])
                        m["fundamentos"].append(f"{s['tipo'].lower()} {s['arquivo']}: referência '{ref}' citada em {fonte}")
                    if cnpj and s.get("favorecido_cnpj") and cnpj != s["favorecido_cnpj"]:
                        m["divergencias"].append(f"CNPJ do favorecido na {fonte} ({cnpj}) ≠ {s['arquivo']} ({s['favorecido_cnpj']})")
                elif len(achados) > 1:
                    m["ambiguidades"].append(f"referência '{ref}' ({fonte}) corresponde a {len(achados)} documentos")
                    self.ambiguas.append({"origem": m["id"], "tipo": "REFERENCIA", "candidatos": [s["id"] for s in achados],
                                          "descricao": f"referência '{ref}' em {fonte} corresponde a {len(achados)} documentos."})
                else:
                    m["ausentes"].append(f"documento '{ref}' citado em {fonte} não foi enviado")
            # sem referência: CNPJ do favorecido + valor idênticos e documento único
            if not m["suportes"] and m["direcao"] == "DEBITO":
                cnpjs = {rels[r]["favorecido_cnpj"] for r in m["relacao"]} | {docs[c].get("favorecido_cnpj") for c in m["comprovantes"]}
                cnpjs.discard(None)
                if len(cnpjs) == 1:
                    cnpj = cnpjs.pop()
                    achados = [s for s in suportes if s.get("favorecido_cnpj") == cnpj and s["valor"] == m["valor"]]
                    if len(achados) == 1:
                        m["suportes"].append(achados[0]["id"])
                        m["fundamentos"].append(f"{achados[0]['tipo'].lower()} {achados[0]['arquivo']}: CNPJ do favorecido e valor idênticos; documento único")
                    elif len(achados) > 1:
                        m["ambiguidades"].append(f"{len(achados)} documentos do favorecido com o mesmo valor")
                        self.ambiguas.append({"origem": m["id"], "tipo": "SUPORTE", "candidatos": [s["id"] for s in achados],
                                              "descricao": f"{len(achados)} documentos do mesmo favorecido e valor para {m['id']}."})

        # Confronto direto extrato × suporte: emissão/vencimento não comprovam a
        # data do pagamento. Propor vínculo para conferência, sem confirmar por valor.
        vinculados = {i for m in self.movimentos for i in m['suportes'] + m['comprovantes']}
        for s in suportes + comprovantes:
            if s['id'] in vinculados or s['id'] in decididos:
                continue
            # Entrada/saída da NOTA é a perspectiva fiscal: compra sustenta saída
            # bancária; venda sustenta entrada. Documento sem papel identificado
            # pode ser candidato a ambas, com direção ainda sujeita à conferência.
            direcoes = {'ENTRADA': {'DEBITO'}, 'SAIDA': {'CREDITO'}}.get(s.get('papel'), {'DEBITO', 'CREDITO'})
            candidatos_valor = [m for m in self.movimentos if m['direcao'] in direcoes and m['valor'] == s['valor']]
            if len(candidatos_valor) > 1:
                self.ambiguas.append({'origem': s['id'], 'tipo': 'DOCUMENTO_MESMO_VALOR',
                                      'candidatos': [m['id'] for m in candidatos_valor],
                                      'descricao': f"{s['arquivo']}: valor igual a {len(candidatos_valor)} movimentos; escolher qual corresponde ao documento."})
            for m in candidatos_valor:
                if any(x.get('movimento') == m['id'] and x.get('documento') == s['id'] for x in self.sugestoes):
                    continue
                evidencia = self.evidencia(m, (s.get('identificadores') or {}).values(),
                                          [s.get('favorecido')], [s.get('favorecido_cnpj')])
                titular = bool(s.get('cnpjs_empresa'))
                descricao = (f"{s['tipo'].lower()} {s['arquivo']}: valor {s['valor']} igual ao {'débito' if m['direcao'] == 'DEBITO' else 'crédito'} do extrato; "
                             + (evidencia or 'sem identificador comum confirmado') + '; '
                             + ('empresa identificada no documento' if titular else 'titularidade não confirmada')
                             + f". Data do documento {s.get('data') or 'não identificada'} ({s.get('papel_data', 'DOCUMENTO')}); "
                             f"{'pagamento' if m['direcao'] == 'DEBITO' else 'recebimento'} em {m['data']}. "
                             + ('Direção do documento não identificada; conferir se corresponde à saída ou entrada. ' if not s.get('papel') else '')
                             + "Vínculo sugerido, exige conferência; não comprova liquidação por si só.")
                sugerir(m, 'documento', s['id'], descricao)

        # D) transferências entre contas próprias (as duas pontas, quando disponíveis)
        proprias = {k: digitos(v["conta"]).lstrip("0") for k, v in self.cad["contas"].items()}
        for m in self.movimentos:
            if m["direcao"] != "DEBITO":
                continue
            outra = [k for k, dig in proprias.items() if k != m["conta"] and dig and dig in digitos(m["descricao"])]
            if len(outra) != 1:
                continue
            m["transferencia_propria"] = {"conta_destino": outra[0]}
            pares = [x for x in self.movimentos if x["conta"] == outra[0] and x["direcao"] == "CREDITO" and x["valor"] == m["valor"] and x["data"] == m["data"]]
            if len(pares) == 1:
                m["transferencia_propria"]["par"] = pares[0]["id"]
                pares[0]["transferencia_propria"] = {"conta_origem": m["conta"], "par": m["id"]}
                m["fundamentos"].append(f"transferência entre contas próprias: histórico cita a conta {outra[0]}; crédito {pares[0]['id']} "
                                        "de mesmo valor e data na outra conta")
                pares[0]["fundamentos"].append(f"transferência entre contas próprias: ponta de débito {m['id']} na conta {m['conta']}")
            elif len(pares) > 1:
                self.ambiguas.append({"origem": m["id"], "tipo": "TRANSFERENCIA", "candidatos": [p["id"] for p in pares],
                                      "descricao": f"transferência {m['id']}: {len(pares)} créditos possíveis na conta {outra[0]}."})
            else:
                m["ausentes"].append(f"ponta de crédito na conta {outra[0]} não localizada (extrato dessa conta ausente ou sem o movimento)")

        # E) situação de cada movimento
        for m in self.movimentos:
            tipos = {docs[s]["tipo"] for s in m["suportes"]}
            natureza = bool(tipos & NATUREZA)
            if m["direcao"] == "DEBITO" and not m["relacao"] and not m.get("transferencia_propria"):
                m["ausentes"].append("não consta na relação de pagamentos")
            if tipos == {"BOLETO"}:
                m["ausentes"].append("boleto identifica a cobrança; falta o documento da natureza (nota, guia, recibo ou contrato)")
            if m.get("transferencia_propria"):
                situacao = "TRANSFERENCIA_PROPRIA" if m["transferencia_propria"].get("par") else "TRANSFERENCIA_PROPRIA_SEM_PAR"
            elif m["ambiguidades"] and not m["decisoes"]:
                situacao = "AMBIGUO"
            elif natureza:
                situacao = "COM_SUPORTE"
            elif m["comprovantes"]:
                situacao = "COMPROVANTE_SEM_NATUREZA"
            else:
                situacao = "SEM_SUPORTE"
            m["situacao"] = situacao
            if situacao in ('SEM_SUPORTE', 'COMPROVANTE_SEM_NATUREZA') and self.documentos_pendentes_leitura:
                m['documentacao_inconclusiva'] = sorted(set(self.documentos_pendentes_leitura))
            m["conferencia"] = {
                "relacao": "SIM" if m["relacao"] else ("NAO_APLICAVEL" if m["direcao"] == "CREDITO" or m.get("transferencia_propria") else "NAO"),
                "comprovante": "SIM" if m["comprovantes"] else "NAO",
                "natureza": "SIM" if natureza else ("SOMENTE_BOLETO" if tipos == {"BOLETO"} else "NAO"),
            }
            # valores dos documentos vinculados (pagamento parcial ou agrupado: informado, sem ajuste)
            soma_sup = sum((valor(docs[s]["valor"]) for s in m["suportes"] if docs[s]["tipo"] in NATUREZA), Decimal("0.00"))
            if natureza and soma_sup != valor(m["valor"]):
                pagos = [x for x in self.movimentos if set(x["suportes"]) & set(m["suportes"])]
                total_pago = sum((valor(x["valor"]) for x in pagos), Decimal("0.00"))
                m["parcial_ou_agrupado"] = (f"documentos vinculados somam {fmt(soma_sup)}; este movimento {m['valor']}; "
                                            f"total pago nesta conferência para esses documentos: {fmt(total_pago)} em {len(pagos)} movimento(s)")
                if total_pago > soma_sup:
                    m["divergencias"].append(f"pagamentos ({fmt(total_pago)}) acima do valor dos documentos ({fmt(soma_sup)})")

        self.conferir_posicoes()

    # ---- posição de títulos a pagar/receber: controle INTERNO da empresa (não é confirmação de terceiros)
    def conferir_posicoes(self):
        """Título da posição inicial ausente da final exige liquidação vinculada (relação com TITULO + movimento confirmado);
        título liquidado que permanece na final ou com valor diferente do movimento = divergência. Igualdade exata."""
        self.posicoes_titulos, self.posicoes_resumo = [], None
        if not self.posicoes:
            return
        ano, mes = map(int, self.competencia.split("-"))
        primeiro = dt.date(ano, mes, 1)
        ultimo = dt.date(ano + mes // 12, mes % 12 + 1, 1) - dt.timedelta(days=1)
        base_esperada = {"INICIAL": str(primeiro - dt.timedelta(days=1)), "FINAL": str(ultimo)}
        validas, vazias = [], set()
        for p in self.posicoes:
            if norm(p["titulo"]) == SEM_TITULOS:
                # Linha TITULO = "SEM TITULOS EM ABERTO" e VALOR 0,00: declara expressamente a posição sem títulos (não é título).
                if p["valor"] != 0 or p["tipo"] not in ("PAGAR", "RECEBER") or p["posicao"] not in ("INICIAL", "FINAL"):
                    self.pendencia("POSICAO_TITULOS_INVALIDA", f"Posição de títulos {p['origem']}: declaração '{SEM_TITULOS}' exige "
                                   "TIPO PAGAR/RECEBER, POSICAO INICIAL/FINAL e VALOR 0,00; linha não utilizada.", p["origem"])
                    continue
                if p["data_base"] == base_esperada[p["posicao"]]:
                    vazias.add((p["tipo"], p["posicao"]))
                else:
                    self.pendencia("POSICAO_TITULOS_DATA_BASE", f"Posição de títulos {p['origem']}: data-base {p['data_base'] or 'ausente'} "
                                   f"da posição {p['posicao']} ≠ {base_esperada[p['posicao']]}; linha não utilizada.", p["origem"])
                continue
            erros = [x for x, ok in ((f"TIPO '{p['tipo']}' (aceitos: PAGAR, RECEBER)", p["tipo"] in ("PAGAR", "RECEBER")),
                                     (f"POSICAO '{p['posicao']}' (aceitas: INICIAL, FINAL)", p["posicao"] in ("INICIAL", "FINAL")),
                                     ("TITULO ausente", bool(p["titulo"])),
                                     ("VALOR ausente ou negativo", p["valor"] is not None and p["valor"] >= 0)) if not ok]
            if erros:
                self.pendencia("POSICAO_TITULOS_INVALIDA", f"Posição de títulos {p['origem']}: {'; '.join(erros)}; linha não utilizada.", p["origem"])
                continue
            if p["data_base"] != base_esperada[p["posicao"]]:
                self.pendencia("POSICAO_TITULOS_DATA_BASE", f"Posição de títulos {p['origem']}: data-base {p['data_base'] or 'ausente'} da posição "
                               f"{p['posicao']} ≠ {base_esperada[p['posicao']]} esperada para a competência {self.competencia}; linha não utilizada.",
                               p["origem"])
                continue
            validas.append(p)
        chave = lambda tipo, titulo: (tipo, norm(titulo))
        pos = {}
        for p in validas:
            pos.setdefault(chave(p["tipo"], p["titulo"]), {"INICIAL": [], "FINAL": []})[p["posicao"]].append(p)
        presentes = {(p["tipo"], p["posicao"]) for p in validas} | vazias
        for tipo, posicao in sorted(vazias & {(p["tipo"], p["posicao"]) for p in validas}):
            self.pendencia("POSICAO_TITULOS_INVALIDA", f"Posição {posicao} a {tipo.lower()} declarada sem títulos e, ao mesmo tempo, "
                           "com títulos informados; conferir a posição enviada.", tipo)
        for tipo in sorted({t for t, _ in presentes}):
            for posicao in ("INICIAL", "FINAL"):
                if (tipo, posicao) not in presentes:
                    self.pendencia("POSICAO_TITULOS_INCOMPLETA", f"Posição {posicao} de títulos a {tipo.lower()} não enviada: a conferência "
                                   f"das liquidações a {tipo.lower()} não está concluída (nada presumido).", tipo)
        movimento_da_relacao = {r: m for m in self.movimentos for r in m.get("relacao", [])}
        liquidacoes = {}
        for r in self.relacao:
            if r.get("titulo"):
                tipo_pos = {"DEBITO": "PAGAR", "CREDITO": "RECEBER"}.get(r.get("direcao") if r.get("tipo") else "DEBITO")
                if tipo_pos:
                    liquidacoes.setdefault(chave(tipo_pos, r["titulo"]), []).append(r)
        for k, rs in sorted(liquidacoes.items()):
            if k not in pos and any((k[0], x) in presentes for x in ("INICIAL", "FINAL")):
                self.pendencia("TITULO_FORA_DA_POSICAO", f"Relação {', '.join(r['origem'] for r in rs)}: título '{rs[0]['titulo']}' "
                               f"não consta na posição de títulos a {k[0].lower()} enviada.", rs[0]["id"])
        for k in sorted(pos):
            tipo, linhas = k[0], pos[k]
            ini, fin = (linhas["INICIAL"] or [None])[0], (linhas["FINAL"] or [None])[0]
            ref = ini or fin
            rels = liquidacoes.get(k, [])
            confirmadas = [r for r in rels if r["id"] in movimento_da_relacao]
            nao_confirmadas = [r for r in rels if r["id"] not in movimento_da_relacao]
            liquidacao = None
            if confirmadas:
                movs = list(dict.fromkeys(movimento_da_relacao[r["id"]]["id"] for r in confirmadas))
                liquidacao = {"movimento": movs[0] if len(movs) == 1 else movs,
                              "valor": fmt(sum((valor(r["valor"]) for r in confirmadas), Decimal("0.00"))),
                              "data": max(movimento_da_relacao[r["id"]]["data"] for r in confirmadas),
                              "relacao": [r["id"] for r in confirmadas]}
            obs = []
            if len(linhas["INICIAL"]) > 1 or len(linhas["FINAL"]) > 1:
                obs.append("título repetido na mesma posição")
            for r in confirmadas:
                if ref["cnpj"] and r.get("favorecido_cnpj") and r["favorecido_cnpj"] != ref["cnpj"]:
                    obs.append(f"CNPJ da relação ({r['favorecido_cnpj']}) ≠ CNPJ da posição ({ref['cnpj']})")
            completa = (tipo, "INICIAL") in presentes and (tipo, "FINAL") in presentes
            base_valor = ref["valor"]
            if not completa:
                situacao = "EM_ABERTO"
                obs.append("posição inicial ou final não enviada: conferência incompleta")
            elif liquidacao and fin:
                situacao = "DIVERGENTE"
                obs.append(f"título liquidado no mês (movimento {liquidacao['movimento']}) e mantido na posição final")
            elif liquidacao and valor(liquidacao["valor"]) != base_valor:
                situacao = "DIVERGENTE"
                obs.append(f"valor do título {fmt(base_valor)} ≠ valor liquidado {liquidacao['valor']}")
            elif liquidacao:
                situacao = "DIVERGENTE" if obs else "LIQUIDADO_CONFERIDO"
                if not obs:
                    obs.append("título baixado da posição final com liquidação confirmada no extrato pelo mesmo valor")
            elif ini and not fin:
                situacao = "SEM_LIQUIDACAO"
                obs.append("título da posição inicial ausente da final sem liquidação vinculada no extrato"
                           + (f" (item da relação {', '.join(r['origem'] for r in nao_confirmadas)} sem movimento confirmado)"
                              if nao_confirmadas else ""))
            elif ini and fin and ini["valor"] != fin["valor"]:
                situacao = "DIVERGENTE"
                obs.append(f"valor alterado de {fmt(ini['valor'])} para {fmt(fin['valor'])} sem liquidação vinculada")
            else:
                situacao = "DIVERGENTE" if obs else "EM_ABERTO"
                if not obs:
                    obs.append("título em aberto na posição final" + ("" if ini else " (incluído no mês; reconhecimento é da área responsável)"))
            item = {"tipo": tipo, "titulo": ref["titulo"], "contraparte": ref["contraparte"], "cnpj": ref["cnpj"],
                    "vencimento": ref["vencimento"], "valor_inicial": fmt(ini["valor"]) if ini else None,
                    "valor_final": fmt(fin["valor"]) if fin else None, "liquidacao": liquidacao, "situacao": situacao,
                    "observacao": "; ".join(obs), "origens": [p["origem"] for p in linhas["INICIAL"] + linhas["FINAL"]],
                    "controle": "INTERNO"}
            self.posicoes_titulos.append(item)
            if situacao == "LIQUIDADO_CONFERIDO" and ini:
                # Liquidação de título que já constava da posição INICIAL: com OBRIGACAO_CONTABILIZADA=SIM, a falta da nota
                # no lote não é ausência do Financeiro (a obrigação foi reconhecida antes). O fato é registrado no movimento;
                # a situação do movimento não muda e a regra bancária decide.
                for r in confirmadas:
                    if r.get("obrigacao_contabilizada") != "SIM":
                        continue
                    m = movimento_da_relacao[r["id"]]
                    m["liquidacao_titulo"] = {"tipo": tipo, "titulo": ref["titulo"], "contraparte": ref["contraparte"],
                                              "posicao_inicial": fmt(ini["valor"]), "situacao_titulo": situacao,
                                              "obrigacao_contabilizada": "SIM", "relacao": r["id"]}
                    citados = [x for x in r["referencias"] + [r["titulo"]] if norm(x) == norm(ref["titulo"])]
                    m["ausentes"] = [x for x in m["ausentes"] if not any(x.startswith(f"documento '{c}' citado em relação") for c in citados)]
                    m["fundamentos"].append(f"liquidação do título {ref['titulo']} da posição inicial a {tipo.lower()} "
                                            f"({fmt(ini['valor'])}); relação marca obrigação já contabilizada; nota anterior não exigida neste lote")
            if situacao == "SEM_LIQUIDACAO":
                self.pendencia("TITULO_SEM_LIQUIDACAO", f"Título {ref['titulo']} ({ref['contraparte']}, a {tipo.lower()}): {item['observacao']}.", ref["titulo"])
            elif situacao == "DIVERGENTE":
                self.pendencia("DIVERGENCIA_TITULO", f"Título {ref['titulo']} ({ref['contraparte']}, a {tipo.lower()}): {item['observacao']}.", ref["titulo"])
        total = lambda tipo, posicao: fmt(sum((p["valor"] for p in validas if p["tipo"] == tipo and p["posicao"] == posicao), Decimal("0.00")))
        contar = lambda s: sum(1 for t in self.posicoes_titulos if t["situacao"] == s)
        self.posicoes_resumo = {
            "controle": "INTERNO", "titulos": len(self.posicoes_titulos), "liquidado_conferido": contar("LIQUIDADO_CONFERIDO"),
            "em_aberto": contar("EM_ABERTO"), "divergente": contar("DIVERGENTE"), "sem_liquidacao": contar("SEM_LIQUIDACAO"),
            "totais": {f"{t}_{p}": total(t, p) for t in ("PAGAR", "RECEBER") for p in ("INICIAL", "FINAL")
                       if (t, p) in presentes},
            "aviso": "Posição de títulos é controle INTERNO da empresa: confere liquidações com o extrato, mas não é "
                     "confirmação independente de terceiros (atribuição da Conciliação)."}

    def montar(self, historico: dict) -> dict:
        """historico (do Coordenador): escriturados (lançamento efetivo → bloqueia) e propostas_simulacao (só rastreio)."""
        docs = {d["id"]: d for d in self.documentos}
        bloqueio_conciliacao = self.conciliar_fontes()    # antes do resumo: a pendência agrupada entra na contagem
        escriturados, propostas = historico.get("escriturados", {}), historico.get("propostas_simulacao", {})
        for m in self.movimentos:
            if m["id"] in escriturados:
                e = escriturados[m["id"]]
                m["ja_escriturado_em"] = e
                m["divergencias"].append(f"movimento já ESCRITURADO (lançamento efetivo {e.get('lancamento') or ''}) na {e['sol']}: "
                                         "não gera novo lançamento (reenvio/sobreposição/reprocessamento)")
            if m["id"] in propostas:
                m["propostas_anteriores"] = propostas[m["id"]]       # simulação: não bloqueia; a nova proposta é revisão
            m["documentos"] = [{"id": i, "arquivo": docs[i]["arquivo"], "tipo": docs[i]["tipo"], "papel": "LIQUIDACAO" if docs[i]["tipo"] == "COMPROVANTE"
                                else "COBRANCA" if docs[i]["tipo"] == "BOLETO" else "NATUREZA", "numero": docs[i].get("numero"),
                                "valor": docs[i].get("valor"), "favorecido": docs[i].get("favorecido"), "favorecido_cnpj": docs[i].get("favorecido_cnpj")}
                               for i in m["comprovantes"] + m["suportes"]]
        ambiguos = {a["origem"] for a in self.ambiguas}            # aparecem em "ambíguas", não como "sem movimento"
        usados = {i for m in self.movimentos for i in m["comprovantes"] + m["suportes"]} | ambiguos
        relac_usados = {i for m in self.movimentos for i in m["relacao"]} | ambiguos
        sem_mov = ([{"tipo": "RELACAO", "id": r["id"], "origem": r["origem"], "data": r["data"], "valor": fmt(valor(r["valor"])),
                     "favorecido": r["favorecido"], "referencias": r["referencias"],
                     "descricao": "item da relação sem liquidação localizada no extrato (a relação não comprova pagamento)"}
                    for r in self.relacao if r["id"] not in relac_usados]
                   + [{"tipo": d["tipo"], "id": d["id"], "arquivo": d["arquivo"], "data": d.get("data"), "valor": d.get("valor"),
                       "favorecido": d.get("favorecido"), "descricao": d.get("bloqueado") or "documento sem movimento localizado"}
                      for d in self.documentos if d["id"] not in usados and d["tipo"] in ("COMPROVANTE", "NOTA_FISCAL", "GUIA", "BOLETO", "RECIBO", "FOLHA")])
        separar = lambda *s: [m for m in self.movimentos if m["situacao"] in s]
        return {
            "agente": "FINANCEIRO", "versao": VERSAO, "procedimento": PROCEDIMENTO, "sol": self.sol, "empresa": self.empresa,
            "competencia": self.competencia, "modo": "SIMULACAO", "executado_em": dt.datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "aviso": ("LOTE BLOQUEADO: movimentações bancárias sem associação financeira confirmada; nada segue automaticamente "
                      "para Contabilidade/Bancos." if bloqueio_conciliacao else
                      "Conferência financeira (extrato × relação × comprovantes × suportes). NÃO é conciliação contábil completa: "
                      "a Conciliação independente é etapa futura."),
            "verificacao_extratos": self.verificacoes, "movimentos": self.movimentos, "bloqueio_lote": bloqueio_conciliacao,
            "ressalvas_documentos": self.ressalvas,
            "resumo": {
                "movimentos": len(self.movimentos),
                "com_suporte": len(separar("COM_SUPORTE")), "comprovante_sem_natureza": len(separar("COMPROVANTE_SEM_NATUREZA")),
                "sem_suporte": len(separar("SEM_SUPORTE")), "ambiguos": len(separar("AMBIGUO")),
                "transferencias_proprias": len(separar("TRANSFERENCIA_PROPRIA", "TRANSFERENCIA_PROPRIA_SEM_PAR")),
                "ja_escriturados": sum(1 for m in self.movimentos if m.get("ja_escriturado_em")),
                "com_proposta_anterior_simulacao": sum(1 for m in self.movimentos if m.get("propostas_anteriores")),
                "relacionados_sem_movimento": len(sem_mov), "duplicidades": len(self.duplicidades), "pendencias": len(self.pendencias)},
            "relacionados_sem_movimento": sem_mov, "ambiguas": self.ambiguas, "sugestoes": self.sugestoes,
            "duplicidades": self.duplicidades, "pendencias": self.pendencias, "documentos": self.documentos, "relacao": self.relacao,
            "ignorados": self.ignorados,
            "posicoes_titulos": self.posicoes_titulos, "posicoes_titulos_resumo": self.posicoes_resumo,
            "documentos_pendentes_leitura": sorted(set(self.documentos_pendentes_leitura)),
            "metodo_empresa": self.metodo_empresa,
            "limitacoes": self.limitacoes + [
                "Correspondência somente por igualdade exata de valor e data (nenhuma tolerância aprovada).",
                "Comprovante prova a liquidação; a natureza depende de nota, guia, recibo, resumo da folha ou contrato vinculado.",
                "Posição de títulos a pagar/receber é controle INTERNO da empresa; não substitui confirmação de terceiros.",
                "PDFs digitais, mistos e escaneados têm leitura local por página; OCR duvidoso ou leitura incompleta exige conferência.",
                "CSV de extrato e relação somente no leiaute do projeto (ver PROCEDIMENTO.md).",
                "Enquanto não houver mecanismo aprovado de associação entre movimentos bancários e fontes auxiliares, a existência de um extrato bancário normalizado não constitui suporte documental/contábil para os movimentos."],
            **self.saida_fontes(),
        }


def receber_pacote_local(empresa, competencia, sol, pasta, manifesto, extracao, area='FINANCEIRO', exigir_hash=False):
    """Entrega de Documentos ao Financeiro: reutilizar extração e validar os originais."""
    d = json.loads(Path(manifesto).read_text(encoding='utf-8'))
    bytes_extracao = Path(extracao).read_bytes()
    if exigir_hash and not d.get('extracao_sha256'): raise ValueError('Entrega sem hash da extração; nova triagem necessária.')
    if d.get('extracao_sha256') and hashlib.sha256(bytes_extracao).hexdigest() != d['extracao_sha256']:
        raise ValueError('Conteúdo da extração alterado após a triagem; pacote recusado.')
    x = json.loads(bytes_extracao.decode('utf-8'))
    if (d.get('contrato'), d.get('empresa'), d.get('competencia'), d.get('sol'), d.get('pasta')) != (
            'DOCUMENTOS_LOCAL_V1', empresa, competencia, sol, pasta):
        raise ValueError('Pacote de Documentos não corresponde à solicitação.')
    base = (clientes() / empresa).resolve(); alvo = (base / pasta).resolve(); alvo.relative_to(base)
    atuais = {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in alvo.rglob('*') if p.is_file() and not p.is_symlink()}
    esperados = {i['arquivo']: i['sha256'] for i in d['itens']}
    extraidos = {a['arquivo']: a['sha256'] for a in x['arquivos']}
    if atuais != esperados or extraidos != esperados:
        raise ValueError('Documentos alterados ou inventário divergente; pacote recusado.')
    # Execuções locais antigas sem tarefas preservam a compatibilidade; não inventam manifesto retroativo.
    tarefas = d.get('tarefas_areas')
    if tarefas is None:
        if area != 'FINANCEIRO': raise ValueError('Pacote da área não registrado.')
        return x['arquivos'], []
    permitidos = {i['arquivo'] for i in tarefas.get(area, {}).get('documentos', [])}
    if not permitidos <= set(esperados): raise ValueError('Pacote financeiro contém arquivo fora do inventário.')
    triagem = [i['arquivo'].rsplit('/', 1)[-1] for i in tarefas.get('TRIAGEM', {}).get('documentos', [])]
    return [a for a in x['arquivos'] if a['arquivo'] in permitidos], triagem


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    for a in ("--empresa", "--sol", "--competencia", "--pasta", "--saida"):
        p.add_argument(a, required=True)
    p.add_argument("--ja-tratados")
    p.add_argument("--decisoes")
    p.add_argument("--ressalvas")
    p.add_argument("--decisoes-conciliacao", help="registro DECISOES_SUPERVISOR_CONCILIACAO_V1 (camada separada; opcional)")
    p.add_argument('--documentos-local')
    p.add_argument('--extracao-local')
    p.add_argument('--exigir-ancora', action='store_true', help='pacote novo: hash da extração obrigatório')
    args = p.parse_args()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", args.empresa) or not re.fullmatch(r"\d{4}-\d{2}", args.competencia):
        print(json.dumps({"erro": "PARAMETROS"}))
        return 2
    ja = json.loads(Path(args.ja_tratados).read_text(encoding="utf-8")) if args.ja_tratados else {}
    decisoes = json.loads(Path(args.decisoes).read_text(encoding="utf-8")) if args.decisoes else {}
    # ressalvas da etapa de Documentos (repassadas pelo Coordenador): documentos citados NÃO são tratados como validados
    ressalvas = json.loads(Path(args.ressalvas).read_text(encoding="utf-8")) if args.ressalvas else []
    c = Conferencia(args.empresa, args.competencia, args.sol)
    c.ressalvas = [str(r) for r in ressalvas]
    if args.decisoes_conciliacao:
        try:
            c.decisoes_conciliacao = json.loads(Path(args.decisoes_conciliacao).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            c.decisoes_conciliacao = {"contrato": "ILEGIVEL"}      # fail-closed: vira pendência, nada é liberado
    if bool(args.documentos_local) != bool(args.extracao_local):
        print(json.dumps({'erro': 'PACOTE_INCOMPLETO'})); return 2
    if args.documentos_local:
        try:
            arquivos, pendentes_triagem = receber_pacote_local(args.empresa, args.competencia, args.sol, args.pasta,
                                                              args.documentos_local, args.extracao_local, exigir_hash=args.exigir_ancora)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(json.dumps({'erro': 'PACOTE_INVALIDO', 'mensagem': str(exc)})); return 2
        c.documentos_pendentes_leitura += pendentes_triagem
        for nome in pendentes_triagem:
            c.pendencia('DOCUMENTO_AGUARDANDO_TRIAGEM', f'{nome}: recebido; área ou leitura ainda não identificada. Não tratado como documento ausente.', nome)
    else:
        arquivos = extrair(args.empresa, args.pasta)
    c.carregar(arquivos)
    for d in c.documentos:
        citado = [r for r in c.ressalvas if d["arquivo"] in r]
        if citado:
            d["ressalva_documentos"] = citado
    c.preparar_movimentos()
    bloqueios = c.triagem()
    if bloqueios:
        resultado = c.montar_bloqueado(bloqueios, c.ressalvas)
    else:
        c.corresponder(decisoes)
        resultado = c.montar(ja)
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"resultado": "CONFERENCIA_CONCLUIDA", "resumo": resultado["resumo"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
