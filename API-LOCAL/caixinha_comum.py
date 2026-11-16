"""Utilitários do MOTOR GERAL usados pelos leitores e especialistas da Conciliação Caixinha (sem dado nem regra de empresa).

- valores BR exatos (Decimal; nunca tolerância; inválido nunca vira zero);
- datas dd/mm/aaaa, períodos de apuração (MM/AAAA, dd/mm/aaaa, AAAA) e competências AAAA-MM;
- CNPJ (14 dígitos ou raiz de 8 dígitos, como no Relatório de Situação Fiscal);
- texto por PÁGINA do documento extraído (proveniência: arquivo, sha256, página e linha);
- identificador de documento (sha256 do original + caminho) e ficha documental comum aos cinco documentos da rotina.
"""
import datetime as dt
import hashlib
import re
import unicodedata
from decimal import Decimal, InvalidOperation

DINHEIRO = r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}"
RE_DINHEIRO = re.compile(DINHEIRO)
RE_DATA = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
RE_CNPJ = re.compile(r"(?<!\d)(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})(?!\d)")
RE_CNPJ_RAIZ = re.compile(r"(?<![\d/])(\d{2})\.(\d{3})\.(\d{3})(?![\d/])")
Z = Decimal("0")


def norm(t) -> str:
    """Maiúsculas sem acento e espaços simples (comparação de rótulos)."""
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[ \t]+", " ", t).strip()


def valor(t):
    """'1.234,56' → Decimal('1234.56'); '-' ou vazio → None; texto fora do formato → ValueError (nunca zero presumido)."""
    s = str(t or "").strip().replace("R$", "").strip()
    if s in ("", "-", "--"):
        return None
    if not re.fullmatch(DINHEIRO, s):
        raise ValueError(f"valor fora do formato: {s[:30]!r}")
    try:
        return Decimal(s.replace(".", "").replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"valor inválido: {s[:30]!r}")


def txt(v) -> str:
    return None if v is None else f"{Decimal(v):.2f}"


def data_iso(t):
    m = RE_DATA.search(str(t or ""))
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def periodo_apuracao(t):
    """PA do documento → {'texto', 'competencia' (AAAA-MM) | None, 'tipo'}. dd/mm/aaaa (último dia do mês) → mês; MM/AAAA → mês;
    AAAA (anual) → competência None. Nada é deduzido além do que está escrito."""
    s = str(t or "").strip()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m and data_iso(s):
        return {"texto": s, "competencia": f"{m.group(3)}-{m.group(2)}", "tipo": "DATA"}
    m = re.fullmatch(r"(\d{2})/(\d{4})", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return {"texto": s, "competencia": f"{m.group(2)}-{m.group(1)}", "tipo": "MES"}
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return {"texto": s, "competencia": None, "tipo": "ANO"}
    return None


def fim_competencia(comp: str) -> dt.date:
    a, m = map(int, comp.split("-"))
    return dt.date(a + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)


def competencia_de(data_txt: str):
    return data_txt[:7] if data_txt else None


def digitos(t) -> str:
    return re.sub(r"\D", "", str(t or ""))


def cnpjs_no_texto(t) -> list:
    return sorted({"".join(m.groups()) for m in RE_CNPJ.finditer(str(t or ""))})


def cnpj_confere(encontrados, cadastro) -> bool:
    """CNPJ completo do cadastro, ou raiz (8 dígitos) quando o documento só traz a raiz (situação fiscal)."""
    cad = {digitos(c) for c in cadastro or []}
    raizes = {c[:8] for c in cad}
    for e in encontrados or []:
        e = digitos(e)
        if (len(e) == 14 and e in cad) or (len(e) == 8 and e in raizes):
            return True
    return False


def paginas(extraido: dict) -> list:
    """[(número da página, texto)] do documento como lido pelo extrator de Documentos (PDF por página; TXT = página 1)."""
    c = (extraido or {}).get("conteudo") or {}
    if c.get("paginas"):
        return [(int(p.get("pagina") or i), p.get("texto") or "") for i, p in enumerate(c["paginas"], 1)]
    return [(1, c.get("texto") or "")]


def texto_total(extraido: dict) -> str:
    return "\n".join(t for _, t in paginas(extraido))


def leitura_utilizavel(extraido: dict):
    """None se o conteúdo pode ser lido; senão o motivo (pendência de leitura)."""
    c = (extraido or {}).get("conteudo") or {}
    if not str((extraido or {}).get("leitura", "")).startswith("EXTRAIDO_"):
        return f"leitura {extraido.get('leitura')}: conteúdo não disponível"
    if c.get("leitura_incompleta"):
        return "leitura incompleta (páginas não lidas)"
    if c.get("requer_conferencia_ocr") or c.get("paginas_conferir_ocr"):
        return "OCR com confiança insuficiente: conferir o original"
    return None


def id_documento(arquivo: str, sha256: str, prefixo: str = "CXD") -> str:
    return f"{prefixo}-" + hashlib.sha256(f"{arquivo}|{sha256}".encode("utf-8")).hexdigest()[:12].upper()


def ficha(a: dict, tipo: str, empresa: str) -> dict:
    """Ficha documental comum (empresa, CNPJ, competência, emissão, tipo, identificador, sha256, reconhecimento, dados, pendências,
    proveniência). Os leitores completam os campos; nada é preenchido por presunção."""
    return {"id": id_documento(a["arquivo"], a["sha256"]), "arquivo": a["arquivo"], "sha256": a["sha256"], "empresa": empresa,
            "tipo": tipo, "cnpj": None, "competencia": None, "periodo": None, "emissao": None, "reconhecimento": "NAO_RECONHECIDO",
            "leitor": None, "dados": {}, "pendencias": [], "proveniencia": {"arquivo": a["arquivo"], "sha256": a["sha256"],
                                                                          "leitura": a.get("leitura"),
                                                                          "paginas": len(paginas(a))}}


def chave_hash(*partes) -> str:
    return hashlib.sha256("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:16].upper()
