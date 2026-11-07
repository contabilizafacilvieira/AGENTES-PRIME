"""Extração SOMENTE LEITURA de documentos de uma empresa - Agente de Documentos (AGENTES PRIME).

Uso (a partir da raiz AGENTES-PRIME) - interface paginada (versão 2.1):
    1) Inventário compacto, sem conteúdo (pode ter várias partes):
       .venv/Scripts/python.exe -I AGENTES/DOCUMENTOS/ferramentas/extrair_documentos.py --empresa EMPRESA-TESTE --pasta "T004/PDF" --resumo [--parte N]
    2) Conteúdo de UM arquivo, pelo id devolvido no inventário (pode ter várias partes):
       .venv/Scripts/python.exe -I AGENTES/DOCUMENTOS/ferramentas/extrair_documentos.py --empresa EMPRESA-TESTE --arquivo <id> [--parte N]
    3) Somente testes/uso controlado (bloqueado para o agente pelo guarda): --pasta "<pasta>" --completo
    Toda resposta de --resumo/--arquivo é JSON compacto com no máximo LIMITES["orcamento_saida_caracteres"].
    A divisão em partes é determinística: mesmo arquivo (mesmo hash) = mesmas partes.
    Toda resposta traz "executado_em" (ISO 8601 com fuso): momento técnico da execução do extrator. Não é conteúdo
    do documento, não entra em hash nem id e não altera a divisão das partes (é medido com tamanho fixo).

O que faz (versão 2, T-004):
- Lista os arquivos da pasta (recursivo), com tamanho, data de modificação e hash SHA-256.
- Agrupa arquivos com conteúdo idêntico (mesmo hash) como duplicados exatos.
- TXT/CSV/JSON/OFX: texto. PDF digital: texto por página (pypdf). XLSX/XLSM: valores das células e marcações.
  XML NF-e (modelo 55) e NFC-e (65) e evento de cancelamento: dados estruturados e validação da chave.
- PDF escaneado e imagens (PNG/JPG/JPEG): DOCUMENTO_REQUER_OCR. Sem OCR e sem interpretação visual.
- Fora do escopo (XLS antigo, ZIP, NFS-e, CT-e etc.): código controlado, sem interpretação.
- Nunca inventa conteúdo: o que não puder ser extraído de forma determinística recebe um código.

Segurança:
- Isolamento de caminhos inalterado (empresa em CLIENTES/ com CADASTRO.md; pasta dentro da empresa; links ignorados).
- Nenhum arquivo é criado, alterado ou apagado. A saída é JSON no stdout.
- Sem rede: não segue links externos de planilhas, não resolve entidades XML (DOCTYPE/ENTITY são recusados),
  não consulta a SEFAZ, não valida assinatura digital, não executa JavaScript de PDF nem macros.
- PDF, planilhas e XML são processados em processo separado com tempo máximo (LIMITES).

Códigos de saída: 0 = ok | 2 = violação de caminho/parâmetro | 1 = erro inesperado.
"""

import argparse
import datetime as dt
import hashlib
import json
import multiprocessing
import os
import queue
import re
import sys
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree

RAIZ_PROJETO = Path(__file__).resolve().parents[3]
PASTA_CLIENTES = Path(os.environ.get("AGENTES_PRIME_CLIENTES") or RAIZ_PROJETO / "CLIENTES").resolve()  # testes isolados
VERSAO_EXTRATOR = "2.1"

EXT_TEXTO = {".txt", ".csv", ".json", ".ofx"}
EXT_PDF = {".pdf"}
EXT_PLANILHA = {".xlsx", ".xlsm"}
EXT_XML = {".xml"}
EXT_IMAGEM = {".png", ".jpg", ".jpeg"}
FORA_DO_ESCOPO = {
    ".xls": "Planilha .xls (Excel antigo) fora do escopo da V1.",
    ".zip": "Arquivo compactado fora do escopo da V1.",
    ".rar": "Arquivo compactado fora do escopo da V1.",
    ".7z": "Arquivo compactado fora do escopo da V1.",
}

# Limites conservadores (justificativa em TESTES/T004/LEIA-ME.md). Prefere-se falhar de forma explícita
# (LIMITE_EXCEDIDO) a truncar sem aviso.
LIMITES = {
    "bytes_arquivo": 20 * 1024 * 1024,        # 20 MB por arquivo
    "caracteres_texto": 100_000,              # TXT/CSV/JSON/OFX (além disso: texto parcial + LIMITE_EXCEDIDO)
    "pdf_paginas": 50,                        # acima: LIMITE_EXCEDIDO sem conteúdo
    "pdf_caracteres": 150_000,                # texto total do PDF; acima: LIMITE_EXCEDIDO sem conteúdo
    "pdf_min_caracteres_pagina": 10,          # menos que isso (sem espaços) = página sem texto aproveitável
    "planilha_abas": 20,
    "planilha_linhas": 2_000,                 # por aba; acima: linhas parciais + LIMITE_EXCEDIDO
    "planilha_colunas": 60,
    "zip_bytes_descompactados": 100 * 1024 * 1024,
    "zip_taxa_compressao": 100,               # por membro com mais de 1 MB descompactado
    "zip_membros": 2_000,
    "xml_bytes": 5 * 1024 * 1024,
    "xml_itens": 990,                         # máximo do leiaute da NF-e
    "tempo_segundos": 60,                     # por arquivo PDF/planilha/XML
    "orcamento_saida_caracteres": 12_000,     # por resposta de --resumo/--arquivo (margem ampla antes do desvio para tool-results)
    "arquivos_por_pasta": 200,                # acima: --resumo recusa com LIMITE_EXCEDIDO (dividir a pasta)
}

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_PLANILHA = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL_PACOTE = "http://schemas.openxmlformats.org/package/2006/relationships"
AVISO_NFE = "Assinatura digital e situação na SEFAZ NÃO verificadas; protocolo e status são apenas os declarados no arquivo."


class ViolacaoCaminho(Exception):
    pass


class Resultado(Exception):
    """Interrompe a leitura de um arquivo com um código controlado."""

    def __init__(self, leitura, observacao="", marcacoes=None):
        super().__init__(observacao)
        self.leitura = leitura
        self.observacao = observacao
        self.marcacoes = marcacoes or []


def dentro_de(caminho: Path, base: Path) -> bool:
    try:
        caminho.relative_to(base)
        return True
    except ValueError:
        return False


def eh_link(caminho: Path) -> bool:
    if caminho.is_symlink():
        return True
    eh_juncao = getattr(caminho, "is_junction", None)
    return bool(eh_juncao and eh_juncao())


def validar_empresa(empresa: str) -> Path:
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", empresa):
        raise ViolacaoCaminho(f"Identificador de empresa inválido: {empresa!r} (use maiúsculas, números e hífen; _MODELO não é permitido).")
    pasta = PASTA_CLIENTES / empresa
    if eh_link(pasta):
        raise ViolacaoCaminho(f"A pasta da empresa é um link/atalho e foi recusada: {empresa}")
    pasta = pasta.resolve()
    if pasta.parent != PASTA_CLIENTES or not pasta.is_dir():
        raise ViolacaoCaminho(f"Empresa não encontrada em CLIENTES/: {empresa}")
    if not (pasta / "CADASTRO.md").is_file():
        raise ViolacaoCaminho(f"Empresa sem CADASTRO.md: {empresa}")
    return pasta


def validar_pasta(pasta_empresa: Path, relativa: str) -> Path:
    bruto = Path(relativa)
    if bruto.is_absolute() or bruto.drive or relativa.startswith(("\\", "/")):
        raise ViolacaoCaminho("A pasta deve ser relativa à pasta da empresa (caminho absoluto recusado).")
    if ".." in bruto.parts:
        raise ViolacaoCaminho("A pasta não pode conter '..'.")
    alvo = (pasta_empresa / bruto).resolve()
    if not dentro_de(alvo, pasta_empresa):
        raise ViolacaoCaminho("A pasta resolvida fica fora da pasta da empresa.")
    if not alvo.is_dir():
        raise ViolacaoCaminho(f"Pasta não encontrada: {relativa}")
    return alvo


def sha256(arquivo: Path) -> str:
    h = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def cabecalho(arquivo: Path, n: int = 1024) -> bytes:
    with open(arquivo, "rb") as f:
        return f.read(n)


# ============================================================ texto
def ler_texto(arquivo: Path) -> dict:
    dados = arquivo.read_bytes()
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = dados.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    truncado = len(texto) > LIMITES["caracteres_texto"]
    return {
        "leitura": "EXTRAIDO_TEXTO",
        "marcacoes": ["LIMITE_EXCEDIDO"] if truncado else [],
        "conteudo": {"codificacao": codificacao, "truncado": truncado, "texto": texto[:LIMITES["caracteres_texto"]]},
    }


# ============================================================ PDF (pypdf)
def _pagina_tem_imagem(objeto, profundidade=0) -> bool:
    if profundidade > 3:
        return False
    recursos = objeto.get("/Resources")
    recursos = recursos.get_object() if recursos is not None else None
    if not recursos or "/XObject" not in recursos:
        return False
    for ref in recursos["/XObject"].get_object().values():
        xobj = ref.get_object()
        tipo = xobj.get("/Subtype")
        if tipo == "/Image":
            return True
        if tipo == "/Form" and _pagina_tem_imagem(xobj, profundidade + 1):
            return True
    return False


def _pagina_tem_desenho(pagina) -> bool:
    """Página sem texto mas com algum desenho (ex.: imagem embutida BI/ID/EI) não pode ser tratada como vazia."""
    try:
        conteudo = pagina.get_contents()
        return bool(conteudo is not None and conteudo.get_data().strip())
    except Exception:
        return True


def _contem_javascript(leitor) -> bool:
    raiz = leitor.trailer["/Root"].get_object()
    acao = raiz.get("/OpenAction")
    acao = acao.get_object() if acao is not None else None
    if isinstance(acao, dict) and acao.get("/S") == "/JavaScript":
        return True
    nomes = raiz.get("/Names")
    nomes = nomes.get_object() if nomes is not None else None
    return bool(nomes and "/JavaScript" in nomes) or "/AA" in raiz


MSG_PDF_PROTEGIDO = ("PDF criptografado/protegido (inclusive proteção somente de proprietário). Nenhuma senha foi "
                     "tentada (nem vazia), o arquivo não foi desbloqueado nem alterado e o conteúdo não foi extraído. "
                     "Envie cópia sem proteção.")
_ENCRYPT_PDF = re.compile(rb"/Encrypt\s*(?:\d+\s+\d+\s+R|<<)")


def _pdf_criptografado(arquivo: Path) -> bool:
    """Procura o dicionário /Encrypt nos bytes (arquivo já limitado a LIMITES['bytes_arquivo'])."""
    return _ENCRYPT_PDF.search(arquivo.read_bytes()) is not None


def ler_pdf(arquivo: Path) -> dict:
    import logging

    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)   # avisos da biblioteca não poluem a saída

    if b"%PDF-" not in cabecalho(arquivo):
        raise Resultado("EXTENSAO_INCOMPATIVEL", "O conteúdo não corresponde a um PDF.")
    marcacoes = []
    # Tratamento conservador (decisão do Supervisor): qualquer PDF criptografado, inclusive com proteção
    # somente de proprietário, fica PDF_PROTEGIDO. Nenhuma senha é tentada (nem vazia): a verificação dos
    # bytes vem antes do PdfReader, que testaria a senha vazia ao abrir o arquivo.
    if _pdf_criptografado(arquivo):
        raise Resultado("PDF_PROTEGIDO", MSG_PDF_PROTEGIDO)
    try:
        leitor = PdfReader(str(arquivo), strict=False)
        if leitor.is_encrypted:
            raise Resultado("PDF_PROTEGIDO", MSG_PDF_PROTEGIDO)
        total_paginas = len(leitor.pages)
    except Resultado:
        raise
    except Exception as e:
        raise Resultado("ARQUIVO_CORROMPIDO", f"PDF ilegível ({type(e).__name__}).")

    if total_paginas == 0:
        raise Resultado("DOCUMENTO_VAZIO", "PDF sem páginas.")
    if total_paginas > LIMITES["pdf_paginas"]:
        raise Resultado("LIMITE_EXCEDIDO", f"PDF com {total_paginas} páginas (limite {LIMITES['pdf_paginas']}); conteúdo não extraído.")
    try:
        if _contem_javascript(leitor):
            marcacoes.append("CONTEM_JAVASCRIPT")
    except Exception:
        pass

    paginas, total_caracteres = [], 0
    for numero, pagina in enumerate(leitor.pages, 1):
        try:
            texto = pagina.extract_text() or ""
            tem_imagem = _pagina_tem_imagem(pagina) or _pagina_tem_desenho(pagina)
        except Exception as e:
            raise Resultado("ARQUIVO_CORROMPIDO", f"Falha ao ler a página {numero} ({type(e).__name__}).")
        uteis = len(re.sub(r"\s", "", texto))
        if uteis >= LIMITES["pdf_min_caracteres_pagina"]:
            situacao = "TEXTO"
        elif tem_imagem:
            situacao, texto = "REQUER_OCR", ""     # sem camada de texto: nada é interpretado
        else:
            situacao = "VAZIA"
        total_caracteres += len(texto)
        if total_caracteres > LIMITES["pdf_caracteres"]:
            raise Resultado("LIMITE_EXCEDIDO", f"Texto do PDF acima de {LIMITES['pdf_caracteres']} caracteres; conteúdo não extraído.")
        paginas.append({"pagina": numero, "situacao": situacao, "texto": texto})

    requer_ocr = [p["pagina"] for p in paginas if p["situacao"] == "REQUER_OCR"]
    vazias = [p["pagina"] for p in paginas if p["situacao"] == "VAZIA"]
    conteudo = {"paginas_total": total_paginas, "paginas_requer_ocr": requer_ocr, "paginas_vazias": vazias}
    if not any(p["situacao"] == "TEXTO" for p in paginas):
        if requer_ocr:
            return {"leitura": "DOCUMENTO_REQUER_OCR", "marcacoes": marcacoes, "conteudo": conteudo,
                    "observacao": "PDF sem camada de texto (escaneado). Nenhum conteúdo foi interpretado; requer tratamento manual."}
        raise Resultado("DOCUMENTO_VAZIO", "PDF sem texto e sem imagens.", marcacoes)
    if requer_ocr:
        marcacoes.append("PAGINAS_REQUEREM_OCR")
    if vazias:
        marcacoes.append("PAGINAS_VAZIAS")
    conteudo["paginas"] = paginas
    return {"leitura": "EXTRAIDO_PDF", "marcacoes": marcacoes, "conteudo": conteudo}


# ============================================================ planilhas (openpyxl, somente leitura)
def _xml_seguro(dados: bytes):
    if re.search(rb"<!DOCTYPE|<!ENTITY", dados[:4096], re.I):
        raise Resultado("ARQUIVO_CORROMPIDO", "Parte interna da planilha com DTD/entidade; recusada.")
    return ElementTree.fromstring(dados)


def _inspecionar_pacote(arquivo: Path) -> dict:
    """Verifica o ZIP antes de abrir com o openpyxl e coleta metadados sem recalcular nada."""
    try:
        z = zipfile.ZipFile(arquivo)
    except zipfile.BadZipFile:
        raise Resultado("ARQUIVO_CORROMPIDO", "Planilha ilegível (pacote ZIP inválido).")
    with z:
        membros = z.infolist()
        if len(membros) > LIMITES["zip_membros"]:
            raise Resultado("LIMITE_EXCEDIDO", f"Pacote com {len(membros)} partes (limite {LIMITES['zip_membros']}).")
        total = sum(m.file_size for m in membros)
        if total > LIMITES["zip_bytes_descompactados"]:
            raise Resultado("LIMITE_EXCEDIDO", "Conteúdo descompactado acima do limite; planilha não aberta.")
        for m in membros:
            if m.file_size > 1024 * 1024 and m.file_size / max(m.compress_size, 1) > LIMITES["zip_taxa_compressao"]:
                raise Resultado("LIMITE_EXCEDIDO", "Taxa de compressão desproporcional (possível bomba de descompactação); planilha não aberta.")
        nomes = z.namelist()
        meta = {
            "macros": any(n.lower().endswith("vbaproject.bin") for n in nomes),
            "links_externos": len([n for n in nomes if n.lower().startswith("xl/externallinks/") and n.lower().endswith(".xml")]),
            "pasta_protegida": False,
            "abas": {},
        }
        if "xl/workbook.xml" not in nomes:
            raise Resultado("ARQUIVO_CORROMPIDO", "Planilha sem a parte principal (xl/workbook.xml).")
        livro = _xml_seguro(z.read("xl/workbook.xml"))
        # Pela especificação OOXML, o elemento sem atributos de bloqueio NÃO significa proteção.
        protecao = livro.find(f"{{{NS_PLANILHA}}}workbookProtection")
        meta["pasta_protegida"] = protecao is not None and any(
            protecao.get(a) in ("1", "true") for a in ("lockStructure", "lockWindows", "lockRevision"))
        alvos = {}
        if "xl/_rels/workbook.xml.rels" in nomes:
            for rel in _xml_seguro(z.read("xl/_rels/workbook.xml.rels")).findall(f"{{{NS_REL_PACOTE}}}Relationship"):
                alvos[rel.get("Id")] = rel.get("Target", "").lstrip("/")
        for aba in livro.iter(f"{{{NS_PLANILHA}}}sheet"):
            alvo = alvos.get(aba.get(f"{{{NS_REL}}}id"), "")
            caminho = alvo if alvo.startswith("xl/") else f"xl/{alvo}"
            info = {"oculta": aba.get("state", "visible") != "visible", "protegida": False, "mescladas": [], "formulas_sem_valor": []}
            if caminho in nomes:
                with z.open(caminho) as fluxo:
                    for _evento, el in ElementTree.iterparse(fluxo):
                        tag = el.tag.rsplit("}", 1)[-1]
                        if tag == "sheetProtection":
                            info["protegida"] = el.get("sheet") in ("1", "true")   # padrão da especificação: falso
                        elif tag == "mergeCell" and len(info["mescladas"]) < 200:
                            info["mescladas"].append(el.get("ref"))
                        elif tag == "c":
                            f = el.find(f"{{{NS_PLANILHA}}}f")
                            v = el.find(f"{{{NS_PLANILHA}}}v")
                            if f is not None and (v is None or not (v.text or "").strip()) and len(info["formulas_sem_valor"]) < 200:
                                info["formulas_sem_valor"].append(el.get("r"))
                            el.clear()
            meta["abas"][aba.get("name")] = info
        return meta


def _valor_celula(v):
    if v is None:
        return None
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, (int, float, bool, str)):
        return v
    return str(v)


def ler_planilha(arquivo: Path) -> dict:
    import openpyxl

    inicio = cabecalho(arquivo, 8)
    if inicio.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise Resultado("PROTEGIDO", "Arquivo em formato OLE: planilha com senha de abertura (ou formato antigo); conteúdo não extraído.")
    if not inicio.startswith(b"PK\x03\x04"):
        raise Resultado("EXTENSAO_INCOMPATIVEL", "O conteúdo não corresponde a uma planilha XLSX/XLSM.")
    meta = _inspecionar_pacote(arquivo)
    try:
        wb = openpyxl.load_workbook(arquivo, read_only=True, data_only=True, keep_links=False, keep_vba=False)
    except Exception as e:
        raise Resultado("ARQUIVO_CORROMPIDO", f"Planilha ilegível ({type(e).__name__}).")
    marcacoes = set()
    if meta["macros"]:
        marcacoes.add("CONTEM_MACROS")
    if meta["links_externos"]:
        marcacoes.add("LINKS_EXTERNOS")
    if meta["pasta_protegida"]:
        marcacoes.add("PROTEGIDO")
    try:
        planilhas = wb.worksheets
        if len(planilhas) > LIMITES["planilha_abas"]:
            marcacoes.add("LIMITE_EXCEDIDO")
        abas = []
        for ws in planilhas[: LIMITES["planilha_abas"]]:
            info = meta["abas"].get(ws.title, {"oculta": False, "protegida": False, "mescladas": [], "formulas_sem_valor": []})
            linhas, truncado = [], False
            for i, linha in enumerate(ws.iter_rows(values_only=True)):
                if i >= LIMITES["planilha_linhas"]:
                    truncado = True
                    break
                if len(linha) > LIMITES["planilha_colunas"] and any(v is not None for v in linha[LIMITES["planilha_colunas"]:]):
                    truncado = True
                valores = [_valor_celula(v) for v in linha[: LIMITES["planilha_colunas"]]]
                if any(v is not None for v in valores):
                    linhas.append({"linha": i + 1, "valores": valores})
            if truncado:
                marcacoes.add("LIMITE_EXCEDIDO")
            if info["oculta"]:
                marcacoes.add("ABA_OCULTA")
            if info["protegida"]:
                marcacoes.add("PROTEGIDO")
            if info["mescladas"]:
                marcacoes.add("CELULAS_MESCLADAS")
            if info["formulas_sem_valor"]:
                marcacoes.add("FORMULA_SEM_VALOR")
            abas.append({"aba": ws.title, "oculta": info["oculta"], "protegida": info["protegida"], "truncado": truncado,
                         "celulas_mescladas": info["mescladas"], "formulas_sem_valor": info["formulas_sem_valor"], "linhas": linhas})
    except Resultado:
        raise
    except Exception as e:
        raise Resultado("ARQUIVO_CORROMPIDO", f"Falha ao ler a planilha ({type(e).__name__}).")
    finally:
        wb.close()
    return {"leitura": "EXTRAIDO_PLANILHA", "marcacoes": sorted(marcacoes),
            "conteudo": {"abas": abas, "links_externos": meta["links_externos"], "contem_macros": meta["macros"]}}


# ============================================================ XML NF-e / NFC-e / evento
def _t(el, caminho):
    if el is None:
        return None
    alvo = el.find("/".join(f"{{{NS_NFE}}}{p}" for p in caminho.split("/")))
    return alvo.text.strip() if alvo is not None and alvo.text is not None else None


def _dv_chave(chave43: str) -> str:
    soma, peso = 0, 2
    for d in reversed(chave43):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    dv = 11 - soma % 11
    return "0" if dv >= 10 else str(dv)


def _decimal(valor):
    try:
        return Decimal(valor) if valor is not None else None
    except InvalidOperation:
        return None


def _ler_nfe(raiz) -> dict:
    nfe = raiz if raiz.tag == f"{{{NS_NFE}}}NFe" else raiz.find(f"{{{NS_NFE}}}NFe")
    inf = nfe.find(f"{{{NS_NFE}}}infNFe") if nfe is not None else None
    if inf is None:
        raise Resultado("XML_TIPO_NAO_SUPORTADO", "XML no namespace da NF-e sem o grupo infNFe.")
    marcacoes, ausentes, divergencias = [], [], []
    ide = inf.find(f"{{{NS_NFE}}}ide")
    emit = inf.find(f"{{{NS_NFE}}}emit")
    dest = inf.find(f"{{{NS_NFE}}}dest")
    tot = inf.find(f"{{{NS_NFE}}}total/{{{NS_NFE}}}ICMSTot")
    mod = _t(ide, "mod")
    if mod not in ("55", "65"):
        raise Resultado("XML_TIPO_NAO_SUPORTADO", f"Modelo de documento {mod!r} fora do escopo (somente 55 e 65).")

    dados_ide = {k: _t(ide, k) for k in ("cUF", "cNF", "natOp", "mod", "serie", "nNF", "dhEmi", "tpNF", "tpEmis", "cDV", "tpAmb")}
    for k in ("mod", "serie", "nNF", "dhEmi"):
        if not dados_ide.get(k):
            ausentes.append(f"ide.{k}")
    emitente = {k: _t(emit, k) for k in ("CNPJ", "CPF", "xNome", "IE")} if emit is not None else None
    if emitente is None or not (emitente.get("CNPJ") or emitente.get("CPF")) or not emitente.get("xNome"):
        ausentes.append("emit")
    destinatario = {k: _t(dest, k) for k in ("CNPJ", "CPF", "idEstrangeiro", "xNome")} if dest is not None else None
    if dest is None and mod == "55":
        ausentes.append("dest")

    dets = inf.findall(f"{{{NS_NFE}}}det")
    if len(dets) > LIMITES["xml_itens"]:
        raise Resultado("LIMITE_EXCEDIDO", f"NF-e com {len(dets)} itens (limite {LIMITES['xml_itens']}); conteúdo não extraído.")
    if not dets:
        ausentes.append("det")
    itens = []
    for det in dets:
        prod = det.find(f"{{{NS_NFE}}}prod")
        imposto = det.find(f"{{{NS_NFE}}}imposto")
        item = {"nItem": det.get("nItem")}
        item.update({k: _t(prod, k) for k in ("cProd", "xProd", "NCM", "CFOP", "uCom", "qCom", "vUnCom", "vProd")})
        for grupo, campo in (("ICMS", "vICMS"), ("IPI", "vIPI"), ("PIS", "vPIS"), ("COFINS", "vCOFINS")):
            alvo = imposto.find(f"{{{NS_NFE}}}{grupo}") if imposto is not None else None
            achado = alvo.find(f".//{{{NS_NFE}}}{campo}") if alvo is not None else None
            item[campo] = achado.text.strip() if achado is not None and achado.text else None
        itens.append(item)

    totais = None
    if tot is None:
        ausentes.append("total")
    else:
        totais = {k: _t(tot, k) for k in ("vBC", "vICMS", "vST", "vProd", "vFrete", "vSeg", "vDesc", "vII", "vIPI", "vPIS", "vCOFINS", "vOutro", "vNF")}
        soma = sum((_decimal(i["vProd"]) or Decimal(0)) for i in itens)
        if _decimal(totais.get("vProd")) is not None and soma != _decimal(totais["vProd"]):
            divergencias.append(f"Soma dos itens ({soma}) diferente de vProd ({totais['vProd']}).")
            marcacoes.append("TOTAL_DIVERGENTE")

    id_inf = inf.get("Id") or ""
    chave = id_inf[3:] if id_inf.startswith("NFe") else None
    chave_valida = bool(chave and re.fullmatch(r"\d{44}", chave) and _dv_chave(chave[:43]) == chave[43])
    if not chave:
        ausentes.append("chave")
    elif not chave_valida:
        marcacoes.append("CHAVE_INVALIDA")
    if chave and re.fullmatch(r"\d{44}", chave):
        dh = dados_ide.get("dhEmi") or ""
        esperado = {
            "cUF": (chave[0:2], dados_ide.get("cUF")),
            "AAMM": (chave[2:6], dh[2:4] + dh[5:7] if len(dh) >= 7 else None),
            "CNPJ/CPF emitente": (chave[6:20], (emitente or {}).get("CNPJ") or ((emitente or {}).get("CPF") or "").zfill(14)),
            "mod": (chave[20:22], dados_ide.get("mod")),
            "serie": (chave[22:25], (dados_ide.get("serie") or "").zfill(3)),
            "nNF": (chave[25:34], (dados_ide.get("nNF") or "").zfill(9)),
            "tpEmis": (chave[34:35], dados_ide.get("tpEmis")),
            "cNF": (chave[35:43], (dados_ide.get("cNF") or "").zfill(8)),
            "cDV": (chave[43:44], dados_ide.get("cDV")),
        }
        difs = [f"{nome}: chave={na_chave} documento={no_doc}" for nome, (na_chave, no_doc) in esperado.items() if no_doc is not None and na_chave != no_doc]
        if difs:
            divergencias.extend(difs)
            marcacoes.append("CHAVE_DIVERGENTE")

    prot = raiz.find(f"{{{NS_NFE}}}protNFe/{{{NS_NFE}}}infProt")
    protocolo = {k: _t(prot, k) for k in ("chNFe", "nProt", "cStat", "xMotivo", "dhRecbto")} if prot is not None else None
    if protocolo and chave and protocolo.get("chNFe") and protocolo["chNFe"] != chave:
        divergencias.append("Chave do protocolo diferente da chave da nota.")
        marcacoes.append("CHAVE_DIVERGENTE")
    if ausentes:
        marcacoes.append("CAMPO_AUSENTE")
    return {
        "leitura": "EXTRAIDO_NFE",
        "marcacoes": sorted(set(marcacoes)),
        "conteudo": {
            "tipo": "NFE" if mod == "55" else "NFCE",
            "chave": chave, "chave_valida": chave_valida, "ide": dados_ide, "emitente": emitente, "destinatario": destinatario,
            "itens_quantidade": len(itens), "itens": itens, "totais": totais, "protocolo": protocolo,
            "campos_ausentes": ausentes, "divergencias": divergencias, "limitacoes": AVISO_NFE,
        },
    }


def _ler_evento(raiz) -> dict:
    inf = raiz.find(f"{{{NS_NFE}}}evento/{{{NS_NFE}}}infEvento")
    if inf is None:
        raise Resultado("XML_TIPO_NAO_SUPORTADO", "Evento sem o grupo infEvento.")
    tipo = _t(inf, "tpEvento")
    if tipo != "110111":
        raise Resultado("XML_TIPO_NAO_SUPORTADO", f"Evento {tipo!r} fora do escopo (somente cancelamento 110111).")
    ret = raiz.find(f"{{{NS_NFE}}}retEvento/{{{NS_NFE}}}infEvento")
    return {
        "leitura": "EXTRAIDO_EVENTO_NFE",
        "marcacoes": [],
        "conteudo": {
            "tipo": "CANCELAMENTO", "tp_evento": tipo, "chave_nfe": _t(inf, "chNFe"), "dh_evento": _t(inf, "dhEvento"),
            "protocolo_nota": _t(inf, "detEvento/nProt"), "justificativa": _t(inf, "detEvento/xJust"),
            "situacao_declarada": _t(ret, "cStat"), "protocolo_evento": _t(ret, "nProtEvento"),
            "nota_relacionada": None, "limitacoes": AVISO_NFE,
        },
    }


def ler_xml(arquivo: Path) -> dict:
    dados = arquivo.read_bytes()
    if len(dados) > LIMITES["xml_bytes"]:
        raise Resultado("LIMITE_EXCEDIDO", f"XML acima de {LIMITES['xml_bytes']} bytes; conteúdo não extraído.")
    if re.search(rb"<!DOCTYPE|<!ENTITY", dados, re.I):
        raise Resultado("XML_DTD_PROIBIDO", "XML com DOCTYPE/ENTITY recusado antes da leitura (proteção contra entidades externas e expansão).")
    try:
        raiz = ElementTree.fromstring(dados)
    except ElementTree.ParseError as e:
        raise Resultado("ARQUIVO_CORROMPIDO", f"XML malformado ({e}).")
    tag = raiz.tag
    if tag in (f"{{{NS_NFE}}}nfeProc", f"{{{NS_NFE}}}NFe"):
        return _ler_nfe(raiz)
    if tag == f"{{{NS_NFE}}}procEventoNFe":
        return _ler_evento(raiz)
    raise Resultado("XML_TIPO_NAO_SUPORTADO", "XML fora do escopo da V1 (somente NF-e/NFC-e e evento de cancelamento).")


# ============================================================ imagens
def classificar_imagem(arquivo: Path) -> dict:
    inicio = cabecalho(arquivo, 8)
    if not (inicio.startswith(b"\x89PNG\r\n\x1a\n") or inicio.startswith(b"\xff\xd8\xff")):
        raise Resultado("EXTENSAO_INCOMPATIVEL", "O conteúdo não corresponde a uma imagem PNG/JPEG.")
    return {"leitura": "DOCUMENTO_REQUER_OCR", "marcacoes": [],
            "observacao": "Imagem não é interpretada (sem OCR na V1). Requer tratamento manual."}


# ============================================================ execução isolada com tempo máximo
FUNCOES_ISOLADAS = {"pdf": ler_pdf, "planilha": ler_planilha, "xml": ler_xml}


def _trabalhador(fila, nome, caminho):
    try:
        fila.put(("ok", FUNCOES_ISOLADAS[nome](Path(caminho))))
    except Resultado as r:
        fila.put(("resultado", (r.leitura, r.observacao, r.marcacoes)))
    except Exception as e:
        fila.put(("erro", f"{type(e).__name__}: {e}"))


def executar_isolado(nome: str, arquivo: Path) -> dict:
    ctx = multiprocessing.get_context("spawn")
    fila = ctx.Queue()
    processo = ctx.Process(target=_trabalhador, args=(fila, nome, str(arquivo)), daemon=True)
    processo.start()
    try:
        tipo, valor = fila.get(timeout=LIMITES["tempo_segundos"])
    except queue.Empty:
        processo.terminate()
        processo.join(5)
        raise Resultado("LIMITE_EXCEDIDO", f"Tempo máximo de processamento ({LIMITES['tempo_segundos']} s) excedido.")
    processo.join(5)
    if tipo == "ok":
        return valor
    if tipo == "resultado":
        raise Resultado(*valor)
    raise Resultado("ERRO_LEITURA", valor)


# ============================================================ análise de cada arquivo
def analisar_arquivo(arquivo: Path, pasta_empresa: Path) -> dict:
    ext = arquivo.suffix.lower()
    estado = arquivo.stat()
    info = {
        "arquivo": arquivo.relative_to(pasta_empresa).as_posix(),
        "extensao": ext,
        "tamanho_bytes": estado.st_size,
        "modificado_em": dt.datetime.fromtimestamp(estado.st_mtime).isoformat(timespec="seconds"),
        "sha256": sha256(arquivo),
        "marcacoes": [],
    }
    try:
        if estado.st_size == 0:
            raise Resultado("DOCUMENTO_VAZIO", "Arquivo vazio.")
        if estado.st_size > LIMITES["bytes_arquivo"]:
            raise Resultado("LIMITE_EXCEDIDO", f"Arquivo acima de {LIMITES['bytes_arquivo']} bytes; conteúdo não extraído.")
        if ext in EXT_TEXTO:
            resultado = ler_texto(arquivo)
        elif ext in EXT_PDF:
            resultado = executar_isolado("pdf", arquivo)
        elif ext in EXT_PLANILHA:
            resultado = executar_isolado("planilha", arquivo)
        elif ext in EXT_XML:
            resultado = executar_isolado("xml", arquivo)
        elif ext in EXT_IMAGEM:
            resultado = classificar_imagem(arquivo)
        else:
            raise Resultado("NAO_SUPORTADO", FORA_DO_ESCOPO.get(ext, f"Formato {ext or '(sem extensão)'} não suportado."))
        info.update(resultado)
    except Resultado as r:
        info["leitura"] = r.leitura
        info["marcacoes"] = r.marcacoes
        if r.observacao:
            info["observacao"] = r.observacao
    except Exception as e:  # o erro de um arquivo não interrompe a análise dos demais
        info["leitura"] = "ERRO_LEITURA"
        info["observacao"] = f"{type(e).__name__}: {e}"
    return info


def relacionar_cancelamentos(arquivos: list) -> None:
    """Marca como cancelada a nota cuja chave aparece em um evento de cancelamento da mesma pasta."""
    notas = {a["conteudo"]["chave"]: a for a in arquivos if a.get("leitura") == "EXTRAIDO_NFE" and a["conteudo"].get("chave")}
    for ev in (a for a in arquivos if a.get("leitura") == "EXTRAIDO_EVENTO_NFE"):
        nota = notas.get(ev["conteudo"].get("chave_nfe"))
        if nota is None:
            ev["marcacoes"] = sorted(set(ev["marcacoes"]) | {"NOTA_NAO_ENCONTRADA_NA_PASTA"})
            continue
        ev["conteudo"]["nota_relacionada"] = nota["arquivo"]
        nota["marcacoes"] = sorted(set(nota["marcacoes"]) | {"NOTA_CANCELADA"})
        nota["conteudo"]["cancelamento"] = {"arquivo_evento": ev["arquivo"], "situacao_declarada": ev["conteudo"].get("situacao_declarada")}


def listar_arquivos(alvo: Path, pasta_empresa: Path):
    arquivos, ignorados = [], []
    for raiz, dirs, nomes in os.walk(alvo, followlinks=False):
        raiz_p = Path(raiz)
        for d in list(dirs):
            if eh_link(raiz_p / d):
                dirs.remove(d)
                ignorados.append({"arquivo": (raiz_p / d).relative_to(pasta_empresa).as_posix(), "motivo": "pasta link/atalho ignorada"})
        for nome in sorted(nomes):
            caminho = raiz_p / nome
            rel = caminho.relative_to(pasta_empresa).as_posix()
            if eh_link(caminho):
                ignorados.append({"arquivo": rel, "motivo": "link/atalho ignorado"})
                continue
            if not dentro_de(caminho.resolve(), pasta_empresa):
                ignorados.append({"arquivo": rel, "motivo": "resolve para fora da pasta da empresa"})
                continue
            arquivos.append(caminho)
    return arquivos, ignorados


# ============================================================ interface paginada (T-004.6): --resumo / --arquivo / --parte
def compacto(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def id_arquivo(rel: str, sha: str) -> str:
    """Identificador do item do inventário: 16 hex do caminho relativo + 16 hex do conteúdo.
    Só pode ser obtido pelo --resumo (o agente não lê arquivos brutos) e muda se o arquivo mudar."""
    return hashlib.sha256(rel.encode("utf-8")).hexdigest()[:16] + sha[:16]


def estrutura(info: dict):
    """Separa o resultado em cabeçalho (repetido em todas as partes) e unidades atômicas paginaveis."""
    leitura, c = info.get("leitura"), info.get("conteudo") or {}
    if leitura == "EXTRAIDO_TEXTO":
        return "linhas", {k: c.get(k) for k in ("codificacao", "truncado")}, \
            [{"linha": i, "texto": t} for i, t in enumerate(c.get("texto", "").splitlines(), 1)]
    if leitura == "EXTRAIDO_PDF":
        return "paginas", {k: c.get(k) for k in ("paginas_total", "paginas_requer_ocr", "paginas_vazias")}, list(c.get("paginas", []))
    if leitura == "EXTRAIDO_PLANILHA":
        abas = c.get("abas", [])
        cab = {"links_externos": c.get("links_externos"), "contem_macros": c.get("contem_macros"),
               "abas": [dict({k: a[k] for k in ("aba", "oculta", "protegida", "truncado", "celulas_mescladas", "formulas_sem_valor")},
                             linhas_com_dados=len(a["linhas"])) for a in abas]}
        return "linhas_planilha", cab, [{"aba": a["aba"], "linha": l["linha"], "valores": l["valores"]} for a in abas for l in a["linhas"]]
    if leitura == "EXTRAIDO_NFE":
        return "itens", {k: v for k, v in c.items() if k != "itens"}, list(c.get("itens", []))
    if leitura == "EXTRAIDO_EVENTO_NFE":
        return "nenhuma", c, []
    return "nenhuma", None, []


def _fatiar(unidade: dict, limite: int) -> list:
    """Divide uma unidade maior que o orçamento em trechos explícitos (nada é descartado)."""
    if len(compacto(unidade)) <= limite:
        return [unidade]
    if isinstance(unidade.get("texto"), str):
        texto, tamanho = unidade["texto"], max(200, limite // 2)
        while True:
            pedacos = [texto[i:i + tamanho] for i in range(0, len(texto), tamanho)]
            trechos = [dict(unidade, texto=p, trecho=f"{k}/{len(pedacos)}") for k, p in enumerate(pedacos, 1)]
            if all(len(compacto(t)) <= limite for t in trechos) or tamanho <= 200:
                break
            tamanho //= 2
        if any(len(compacto(t)) > limite for t in trechos):
            raise Resultado("LIMITE_EXCEDIDO", "Trecho de texto não cabe no orçamento de saída.")
        return trechos
    if isinstance(unidade.get("valores"), list):
        valores, tamanho = unidade["valores"], max(1, len(unidade["valores"]) // 2)
        while True:
            grupos = [(i, valores[i:i + tamanho]) for i in range(0, len(valores), tamanho)]
            trechos = [dict(unidade, valores=g, colunas=f"{i + 1}-{i + len(g)}") for i, g in grupos]
            if all(len(compacto(t)) <= limite for t in trechos) or tamanho == 1:
                break
            tamanho = max(1, tamanho // 2)
        if any(len(compacto(t)) > limite for t in trechos):
            raise Resultado("LIMITE_EXCEDIDO", "Célula de planilha não cabe no orçamento de saída.")
        return trechos
    raise Resultado("LIMITE_EXCEDIDO", "Registro estruturado não cabe no orçamento de saída.")


def _intervalo(tipo: str, unidades: list) -> str:
    if not unidades:
        return "sem conteúdo"
    a, b = unidades[0], unidades[-1]

    def ponta(u, chave):
        # Unidade dividida: informa qual trecho (texto) ou quais colunas (planilha) a ponta representa.
        if "trecho" in u:
            return f"{u[chave]} [trecho {u['trecho']}]"
        if "colunas" in u:
            return f"{u[chave]} [colunas {u['colunas']}]"
        return str(u[chave])

    if tipo == "linhas":
        return f"linhas {ponta(a, 'linha')}-{ponta(b, 'linha')}"
    if tipo == "paginas":
        return f"páginas {ponta(a, 'pagina')}-{ponta(b, 'pagina')}"
    if tipo == "itens":
        return f"itens {a.get('nItem')}-{b.get('nItem')}"
    faixas = {}
    for u in unidades:
        faixas.setdefault(u["aba"], [u, u])[1] = u
    return "; ".join(f"aba {aba}: linhas {ponta(i, 'linha')}-{ponta(f, 'linha')}" for aba, (i, f) in faixas.items())


EXECUTADO_EM_MODELO = "0000-00-00T00:00:00+00:00"  # tamanho fixo usado no cálculo das partes


def executado_em() -> str:
    """Momento técnico da execução, ISO 8601 com fuso explícito (sempre 25 caracteres)."""
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def envelope_arquivo(empresa, info, tipo, cab, conteudo, parte, total, intervalo, quando=EXECUTADO_EM_MODELO) -> dict:
    return {
        "modo": "arquivo", "versao": VERSAO_EXTRATOR, "executado_em": quando, "empresa": empresa,
        "id": id_arquivo(info["arquivo"], info["sha256"]), "arquivo": info["arquivo"], "sha256": info["sha256"],
        "tamanho_bytes": info["tamanho_bytes"], "leitura": info.get("leitura"), "marcacoes": info.get("marcacoes", []),
        "observacao": info.get("observacao"), "parte": parte, "partes_total": total, "tem_mais": parte < total,
        "intervalo": intervalo, "tipo_unidade": tipo, "cabecalho": cab, "conteudo": conteudo,
        "aviso": "Documento só está completo após receber TODAS as partes. Marcações de pasta (NOTA_CANCELADA, duplicidade) estão no --resumo.",
    }


def paginar(empresa: str, info: dict):
    """Divide o conteúdo em partes determinísticas que cabem no orçamento (mesmo hash = mesmas partes)."""
    tipo, cab, unidades = estrutura(info)
    orcamento = LIMITES["orcamento_saida_caracteres"]
    base = len(compacto(envelope_arquivo(empresa, info, tipo, cab, [], 9999, 9999, "x" * 800)))  # 800: margem para o intervalo
    disponivel = orcamento - base - 200
    if disponivel < 1500:
        raise Resultado("LIMITE_EXCEDIDO", "Metadados do arquivo excedem o orçamento de saída; tratamento manual.")
    partes, atual, tamanho = [], [], 0
    for u in (t for un in unidades for t in _fatiar(un, disponivel)):
        t = len(compacto(u)) + 1
        if atual and tamanho + t > disponivel:
            partes.append(atual)
            atual, tamanho = [], 0
        atual.append(u)
        tamanho += t
    partes.append(atual)
    return tipo, cab, partes


def info_paginada(empresa: str, info: dict):
    """Aplica a paginação; se a paginação falhar, o arquivo vira LIMITE_EXCEDIDO sem conteúdo."""
    try:
        return info, paginar(empresa, info)
    except Resultado as r:
        info = {k: v for k, v in info.items() if k != "conteudo"}
        info.update(leitura=r.leitura, observacao=r.observacao, marcacoes=sorted(set(info.get("marcacoes", [])) | set(r.marcacoes)))
        return info, paginar(empresa, info)


def erro(codigo: str, mensagem: str, **extra) -> int:
    print(compacto(dict({"erro": codigo, "mensagem": mensagem}, **extra)), file=sys.stderr)
    return 2


def modo_resumo(empresa: str, pasta_empresa: Path, alvo: Path, parte: int) -> int:
    caminhos, ignorados = listar_arquivos(alvo, pasta_empresa)
    if len(caminhos) > LIMITES["arquivos_por_pasta"]:
        return erro("LIMITE_EXCEDIDO", f"Pasta com {len(caminhos)} arquivos (limite {LIMITES['arquivos_por_pasta']}); divida a pasta.")
    infos = [analisar_arquivo(c, pasta_empresa) for c in caminhos]
    relacionar_cancelamentos(infos)
    ids = {i["arquivo"]: id_arquivo(i["arquivo"], i["sha256"]) for i in infos}
    primeiro_por_hash, itens = {}, []
    for info in infos:
        info, (_tipo, _cab, partes) = info_paginada(empresa, info)
        c = info.get("conteudo") or {}
        relacionado = (c.get("cancelamento") or {}).get("arquivo_evento") or c.get("nota_relacionada")
        itens.append({
            "id": ids[info["arquivo"]], "arquivo": info["arquivo"], "nome": Path(info["arquivo"]).name, "extensao": info["extensao"],
            "tamanho_bytes": info["tamanho_bytes"], "sha256": info["sha256"], "leitura": info.get("leitura"),
            "marcacoes": info.get("marcacoes", []), "conteudo_disponivel": str(info.get("leitura", "")).startswith("EXTRAIDO_"),
            "partes_total": len(partes), "duplicado_de": primeiro_por_hash.get(info["sha256"]),
            "relacionado_a": ids.get(relacionado) if relacionado else None,
        })
        primeiro_por_hash.setdefault(info["sha256"], ids[info["arquivo"]])

    def envelope(lista, n, total, quando=EXECUTADO_EM_MODELO):
        return {"modo": "resumo", "versao": VERSAO_EXTRATOR, "executado_em": quando, "empresa": empresa,
                "pasta": alvo.relative_to(pasta_empresa).as_posix(),
                "parte": n, "partes_total": total, "tem_mais": n < total, "itens_total": len(itens), "itens": lista,
                "ignorados": ignorados[:20] if n == 1 else [], "ignorados_total": len(ignorados),
                "aviso": "Inventário sem conteúdo. Peça o conteúdo com --arquivo <id> (um arquivo por vez) e todas as --parte indicadas."}

    disponivel = LIMITES["orcamento_saida_caracteres"] - len(compacto(envelope([], 9999, 9999))) - 300
    paginas, atual, tamanho = [], [], 0
    for item in itens:
        t = len(compacto(item)) + 1
        if atual and tamanho + t > disponivel:
            paginas.append(atual)
            atual, tamanho = [], 0
        atual.append(item)
        tamanho += t
    paginas.append(atual)
    if parte > len(paginas):
        return erro("PARTE_INEXISTENTE", f"O resumo tem {len(paginas)} parte(s).", partes_total=len(paginas))
    saida = compacto(envelope(paginas[parte - 1], parte, len(paginas), executado_em()))
    if len(saida) > LIMITES["orcamento_saida_caracteres"]:
        return erro("LIMITE_EXCEDIDO", "Parte do resumo acima do orçamento de saída (não deveria ocorrer); nada foi devolvido.")
    print(saida)
    return 0


def modo_arquivo(empresa: str, pasta_empresa: Path, ident: str, parte: int) -> int:
    caminhos, _ = listar_arquivos(pasta_empresa, pasta_empresa)
    por_caminho = {hashlib.sha256(c.relative_to(pasta_empresa).as_posix().encode("utf-8")).hexdigest()[:16]: c for c in caminhos}
    caminho = por_caminho.get(ident[:16])
    if caminho is None:
        return erro("ID_DESCONHECIDO", "Identificador não corresponde a nenhum arquivo da empresa. Use somente ids devolvidos pelo --resumo.")
    if sha256(caminho)[:16] != ident[16:]:
        return erro("ARQUIVO_ALTERADO", "O arquivo mudou desde o --resumo. Rode o --resumo novamente.")
    info, (tipo, cab, partes) = info_paginada(empresa, analisar_arquivo(caminho, pasta_empresa))
    if parte > len(partes):
        return erro("PARTE_INEXISTENTE", f"O arquivo tem {len(partes)} parte(s).", partes_total=len(partes))
    saida = compacto(envelope_arquivo(empresa, info, tipo, cab, partes[parte - 1], parte, len(partes), _intervalo(tipo, partes[parte - 1]),
                                    executado_em()))
    if len(saida) > LIMITES["orcamento_saida_caracteres"]:
        return erro("LIMITE_EXCEDIDO", "Parte acima do orçamento de saída (não deveria ocorrer); nada foi devolvido.")
    print(saida)
    return 0


def modo_completo(empresa: str, pasta_empresa: Path, alvo: Path) -> int:
    """Saída integral da pasta. SOMENTE para testes/uso controlado; o guarda não permite ao agente."""
    caminhos, ignorados = listar_arquivos(alvo, pasta_empresa)
    arquivos = [analisar_arquivo(c, pasta_empresa) for c in caminhos]
    relacionar_cancelamentos(arquivos)
    por_hash = {}
    for a in arquivos:
        por_hash.setdefault(a["sha256"], []).append(a["arquivo"])
    print(json.dumps({
        "ferramenta": "extrair_documentos.py", "versao": VERSAO_EXTRATOR, "modo": "completo",
        "executado_em": dt.datetime.now().isoformat(timespec="seconds"), "empresa": empresa,
        "pasta_analisada": alvo.relative_to(pasta_empresa).as_posix(), "total_arquivos": len(arquivos), "arquivos": arquivos,
        "duplicados_exatos": [{"sha256": h, "arquivos": l} for h, l in por_hash.items() if len(l) > 1],
        "ignorados": ignorados, "limites": LIMITES,
    }, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description="Extração somente leitura de documentos de uma empresa.")
    p.add_argument("--empresa", required=True, help="Identificador da empresa (pasta em CLIENTES/).")
    p.add_argument("--pasta", help="Pasta relativa à pasta da empresa (somente com --resumo ou --completo).")
    p.add_argument("--resumo", action="store_true", help="Inventário compacto, sem conteúdo.")
    p.add_argument("--arquivo", help="Identificador devolvido pelo --resumo (32 caracteres hexadecimais).")
    p.add_argument("--parte", type=int, default=1, help="Parte do resumo ou do arquivo (inteiro >= 1).")
    p.add_argument("--completo", action="store_true", help="Saída integral da pasta (somente testes; bloqueado para o agente).")
    args = p.parse_args()

    modos = [bool(args.resumo), args.arquivo is not None, bool(args.completo)]
    if sum(modos) != 1:
        return erro("PARAMETROS_INVALIDOS", "Use exatamente um modo: --resumo, --arquivo ou --completo.")
    if not 1 <= args.parte <= 9999:
        return erro("PARAMETROS_INVALIDOS", "--parte deve ser um inteiro entre 1 e 9999.")
    if args.arquivo is not None and (args.pasta is not None or not re.fullmatch(r"[0-9a-f]{32}", args.arquivo)):
        return erro("PARAMETROS_INVALIDOS", "--arquivo exige somente o id de 32 caracteres hexadecimais devolvido pelo --resumo (sem --pasta).")
    if (args.resumo or args.completo) and args.pasta is None:
        return erro("PARAMETROS_INVALIDOS", "--resumo e --completo exigem --pasta.")
    if args.completo and args.parte != 1:
        return erro("PARAMETROS_INVALIDOS", "--completo não aceita --parte.")

    try:
        pasta_empresa = validar_empresa(args.empresa)
        alvo = validar_pasta(pasta_empresa, args.pasta) if args.pasta is not None else None
    except ViolacaoCaminho as e:
        return erro("VIOLACAO_CAMINHO", str(e))

    if args.resumo:
        return modo_resumo(args.empresa, pasta_empresa, alvo, args.parte)
    if args.arquivo is not None:
        return modo_arquivo(args.empresa, pasta_empresa, args.arquivo, args.parte)
    return modo_completo(args.empresa, pasta_empresa, alvo)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({"erro": "ERRO_INESPERADO", "mensagem": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
