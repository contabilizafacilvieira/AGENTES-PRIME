"""RECONHECIMENTO AUTOMÁTICO · SOMENTE VGROW · campos da DUIMP e das NFs da Capital Trade ("Documentos.pdf").

ESPECÍFICO DA VGROW (área de Importação). Reconhece, por processo (OCCT), os seis campos de que o fechamento precisa:
FOB R$, frete R$, data da chegada, fatura, números das NFs e ICMS destacado. Decisão do Supervisor (31/10/2026):
1) usa a camada de texto do PDF quando ela é legível; 2) se não for (fontes Type3 sem tabela de caracteres, como no
extrato da DUIMP), renderiza a página e aplica OCR LOCAL (pypdfium2 + RapidOCR, offline). Leitura visual por modelo de
linguagem continua proibida. Nada é decidido aqui: cada campo sai com valor, origem, confiança, evidência e status
OK / ILEGIVEL / AUSENTE / CONFLITO, para conferência do Supervisor (que só intervém nos campos que não estão OK).

Executado somente pelo Coordenador (API local) depois da etapa de Documentos de uma SOL piloto da VGROW. Isolamento de
caminhos e limites reaproveitados do extrator homologado. Saída: JSON (arquivo no runtime, fora do projeto).

Layout (conhecido por uma leitura única autorizada em 31/10/2026):
- Extrato da DUIMP: "VALOR FOB." e "VALOR FRETE.." (1ª coluna = REAIS), "FATURA. :…", "DATA DA CHEGADA ….:dd/mm/aaaa",
  "REF.CAPITALTRADE…:OCCTnnnnn/aa" (conferência do processo).
- DANFE da Capital Trade destinada à VGROW: número da NF pela chave de acesso (44 dígitos, DV conferido) e
  "VALOR DO ICMS" (valor alinhado na célula do rótulo). DANFEs de outros destinatários são ignoradas.

Uso:
  .venv/Scripts/python.exe -I AGENTES/IMPORTACAO/ferramentas/reconhecer_documentos_vgrow.py --pasta "<lote>" --saida <arquivo.json>
"""

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "AGENTES" / "DOCUMENTOS" / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import extrair_documentos as extrator  # noqa: E402  (isolamento de caminhos e limites homologados)
import importacao_vgrow as importacao  # noqa: E402

EMPRESA = "VGROW"
LIMITE_PAGINAS = 60
ESCALA = 2.5
CONFIANCA_MINIMA = 0.80
# valor monetário com 2 decimais; o OCR às vezes troca a vírgula decimal por ponto ("20.000.00")
RE_DINHEIRO = re.compile(r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}(?!\d)")
CAMPOS = importacao.CAMPOS_INFORMADOS
_OCR = []


def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


def compacto(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", norm(s))


def ocr():
    if not _OCR:
        from rapidocr_onnxruntime import RapidOCR
        _OCR.append(RapidOCR())
    return _OCR[0]


def legivel(texto: str) -> bool:
    return len(re.findall(r"[A-Za-zÀ-ú]{3,}", texto)) >= 10


def paginas(caminho: Path):
    """(índice, caixas[(y, x_esq, x_dir, texto, confiança)], origem) por página: texto do PDF ou OCR local."""
    from pypdf import PdfReader
    leitor = PdfReader(str(caminho))
    if len(leitor.pages) > LIMITE_PAGINAS:
        raise ValueError(f"{len(leitor.pages)} páginas (limite {LIMITE_PAGINAS})")
    documento = None
    for i, pagina in enumerate(leitor.pages):
        texto = pagina.extract_text() or ""
        if legivel(texto):
            yield i, [(k * 30, 0, 0, linha, 1.0) for k, linha in enumerate(texto.splitlines())], "TEXTO_PDF"
            continue
        import numpy as np
        import pypdfium2 as pdfium
        documento = documento or pdfium.PdfDocument(str(caminho))
        imagem = np.array(documento[i].render(scale=ESCALA).to_pil().convert("RGB"))
        resultado, _ = ocr()(imagem)
        yield i, [(caixa[0][1], caixa[0][0], caixa[1][0], t, float(c)) for caixa, t, c in (resultado or [])], "OCR"


def linhas(caixas: list) -> list:
    """Junta caixas na mesma altura (rótulo e valor ficam em caixas separadas no OCR)."""
    grupos = []
    for y, xe, xd, t, c in sorted(caixas):
        if grupos and abs(grupos[-1]["y"] - y) <= 14:
            grupos[-1]["caixas"].append((xe, t, c))
        else:
            grupos.append({"y": y, "caixas": [(xe, t, c)]})
    return [(" ".join(t for _, t, _ in sorted(g["caixas"])), min(c for _, _, c in g["caixas"])) for g in grupos]


def dv_ok(chave: str) -> bool:
    soma, peso = 0, 2
    for d in reversed(chave[:43]):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return int(chave[43]) == (0 if resto < 2 else 11 - resto)


def dinheiro(texto: str):
    """(valor, separador decimal lido corretamente?). Últimos 2 dígitos = centavos; o resto são milhares."""
    m = RE_DINHEIRO.search(texto)
    if not m:
        return None, False
    bruto = m.group(0)
    return Decimal(re.sub(r"\D", "", bruto[:-3]) + "." + bruto[-2:]), bruto[-3] == ","


def duimp(linhas_pagina: list, origem: str, pagina: int) -> dict:
    achados = {}

    def anotar(campo, valor, conf, linha):
        achados.setdefault(campo, []).append({"valor": valor, "confianca": conf, "evidencia": linha.strip()[:140], "origem": f"{origem} p.{pagina}"})

    for texto, conf in linhas_pagina:
        c = compacto(texto)
        for numero in re.findall(r"(?<!\d)(\d{2}BR\d{10}-\d)(?!\d)", norm(texto).replace(" ", "")):
            anotar("duimp", numero, conf, texto)      # identificador (liga evidências às pendências); não é campo do lançamento
        if c.startswith("VALORFOB") or c.startswith("VALORFRETE"):
            v, separador_ok = dinheiro(texto)
            if v is not None:      # vírgula decimal lida como ponto → confiança rebaixada: o Supervisor confirma
                anotar("fob" if c.startswith("VALORFOB") else "frete", str(v), conf if separador_ok else min(conf, CONFIANCA_MINIMA - 0.01), texto)
        elif c.startswith("FATURA") and not c.startswith("FATURAM"):
            m = re.search(r"FATURA[\s.:]*([A-Z0-9][A-Z0-9/._-]{3,})", norm(texto))
            m and anotar("fatura", m.group(1).strip("."), conf, texto)
        elif c.startswith("DATADACHEGADA"):
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
            if m:
                try:
                    anotar("chegada", dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat(), conf, texto)
                except ValueError:
                    pass
        elif c.startswith("REFCAPITALTRADE"):
            m = re.search(r"OCCT\s*0*(\d{4,6})\s*/\s*(\d{2})", norm(texto))
            m and anotar("ref_occt", f"OCCT{m.group(1)}/{m.group(2)}", conf, texto)
    return achados


def danfe(caixas: list, origem: str, pagina: int):
    """NF da Capital Trade destinada à VGROW: (nº da NF, chave, ICMS, confiança, evidência) ou None."""
    texto = " ".join(t for _, _, _, t, _ in caixas)
    if "DANFE" not in compacto(texto) or "CAPITALTRADE" not in compacto(texto):
        return None
    if "VGROW" not in compacto(texto) and "21602012" not in re.sub(r"\D", "", texto):
        return None                                   # DANFE de outro destinatário (ex.: entrada por conta e ordem)
    chave = next((d for d in re.findall(r"\d{44}", re.sub(r"\s", "", texto)) if dv_ok(d)), None)
    if not chave:
        return {"pagina": pagina, "erro": "chave de acesso ilegível ou com DV inválido"}
    rotulo = next(((y, xe) for y, xe, xd, t, c in caixas if compacto(t) == "VALORDOICMS"), None)
    icms, conf_icms, evid = None, 0.0, ""
    if rotulo:
        y0, x0 = rotulo
        vizinhos = sorted(xe for y, xe, xd, t, c in caixas if abs(y - y0) <= 12 and xe > x0 + 10 and not RE_DINHEIRO.fullmatch(t.strip()))
        x1 = vizinhos[0] if vizinhos else x0 + 400
        candidatos = sorted((y - y0, xe, t, c) for y, xe, xd, t, c in caixas
                            if 4 < y - y0 < 70 and x0 - 80 <= xe < x1 and RE_DINHEIRO.fullmatch(t.strip().strip(".")))
        if candidatos:
            _, _, t, conf_icms = candidatos[0]
            icms, separador_ok = dinheiro(t)
            conf_icms = conf_icms if separador_ok else min(conf_icms, CONFIANCA_MINIMA - 0.01)
            evid = f"VALOR DO ICMS {t.strip()}"
    return {"pagina": pagina, "nf": str(int(chave[25:34])), "chave": chave, "icms": str(icms) if icms is not None else None,
            "confianca": min(conf_icms, 1.0) if icms is not None else 0.0, "origem": origem, "evidencia": evid}


def consolidar(achados: dict, notas: list, processo: str) -> dict:
    campos = {}
    for campo in ("fob", "frete", "chegada", "fatura"):
        lista = achados.get(campo, [])
        valores = {a["valor"] for a in lista}
        if not lista:
            campos[campo] = {"status": "AUSENTE", "valor": None}
        elif len(valores) > 1:
            campos[campo] = {"status": "CONFLITO", "valor": None, "candidatos": sorted(valores), "evidencia": " | ".join(a["evidencia"] for a in lista)}
        else:
            melhor = max(lista, key=lambda a: a["confianca"])
            campos[campo] = dict(melhor, status="OK" if melhor["confianca"] >= CONFIANCA_MINIMA else "ILEGIVEL")
    validas = {n["chave"]: n for n in notas if "chave" in n}
    if not validas:
        motivo = "; ".join(n["erro"] for n in notas if "erro" in n) or "nenhuma DANFE da Capital Trade destinada à VGROW"
        campos["nfs"] = {"status": "AUSENTE", "valor": None, "evidencia": motivo}
        campos["icms_nf"] = {"status": "AUSENTE", "valor": None, "evidencia": motivo}
    else:
        nfs = sorted({n["nf"] for n in validas.values()}, key=int)
        campos["nfs"] = {"status": "OK", "valor": nfs, "confianca": 1.0, "origem": "chave de acesso (DV conferido)",
                         "evidencia": ", ".join(f"NF {n['nf']} (p.{n['pagina']})" for n in validas.values())}
        if any(n["icms"] is None for n in validas.values()):
            campos["icms_nf"] = {"status": "AUSENTE", "valor": None, "evidencia": "VALOR DO ICMS não localizado em todas as DANFEs"}
        else:
            total = sum(Decimal(n["icms"]) for n in validas.values())
            conf = min(n["confianca"] for n in validas.values())
            campos["icms_nf"] = {"status": "OK" if conf >= CONFIANCA_MINIMA else "ILEGIVEL", "valor": str(total), "confianca": conf,
                                 "origem": "soma das DANFEs", "evidencia": " + ".join(f"NF {n['nf']}: {n['icms']}" for n in validas.values())}
    referencias = {a["valor"] for a in achados.get("ref_occt", [])}
    if referencias and referencias != {processo}:
        for campo in ("fob", "frete", "chegada", "fatura"):
            campos[campo] = dict(campos[campo], status="CONFLITO",
                                 evidencia=f"DUIMP indica {', '.join(sorted(referencias))}, mas o arquivo é do processo {processo}")
    return campos


def reconhecer(pasta: str) -> dict:
    pasta_empresa = extrator.validar_empresa(EMPRESA)
    alvo = extrator.validar_pasta(pasta_empresa, pasta)
    caminhos, _ = extrator.listar_arquivos(alvo, pasta_empresa)
    processos = {}
    for caminho in caminhos:
        proc = importacao.processo_de(caminho.name)
        if not proc or importacao.tipo_de(caminho.name, caminho.suffix.lower()) != "documentos":
            continue
        registro = {"arquivo": caminho.name, "paginas": 0, "paginas_ocr": 0, "paginas_submetidas_ocr": [], "pendencias": []}
        achados, notas = {}, []
        try:
            if caminho.stat().st_size > extrator.LIMITES["bytes_arquivo"]:
                raise ValueError("arquivo acima do limite de tamanho")
            for i, caixas, origem in paginas(caminho):
                registro["paginas"] += 1
                registro["paginas_ocr"] += origem == "OCR"
                if origem == "OCR":
                    registro["paginas_submetidas_ocr"].append(i + 1)
                for campo, lista in duimp(linhas(caixas), origem, i + 1).items():
                    achados.setdefault(campo, []).extend(lista)
                nota = danfe(caixas, origem, i + 1)
                nota and notas.append(nota)
        except Exception as e:      # documento ilegível/defeituoso: todos os campos ficam para o Supervisor
            registro["pendencias"].append(f"Leitura do {caminho.name} falhou ({type(e).__name__}: {str(e)[:120]}).")
        registro["campos"] = consolidar(achados, notas, proc)
        registro["notas"] = notas
        registro["duimp"] = sorted({a["valor"] for a in achados.get("duimp", [])})
        registro["ref_occt"] = sorted({a["valor"] for a in achados.get("ref_occt", [])})
        # páginas de onde cada campo foi efetivamente identificado (≠ páginas apenas submetidas ao OCR)
        paginas_campo = {}
        for campo in ("fob", "frete", "chegada", "fatura", "duimp", "ref_occt"):
            paginas_campo[campo] = sorted({int(re.search(r"p\.(\d+)", a["origem"]).group(1)) for a in achados.get(campo, [])})
        paginas_campo["nfs"] = paginas_campo["icms_nf"] = sorted({n["pagina"] for n in notas if "chave" in n})
        registro["paginas_com_campos"] = paginas_campo
        registro["paginas_sem_campos"] = sorted(set(range(1, registro["paginas"] + 1)) - {x for v in paginas_campo.values() for x in v})
        if proc in processos:
            registro["pendencias"].append("Mais de um 'Documentos.pdf' no processo: confira os campos.")
            registro["campos"] = {c: dict(v, status="CONFLITO") for c, v in registro["campos"].items()}
        processos[proc] = registro
    return {"empresa": EMPRESA, "pasta": pasta, "versao": "1.0", "confianca_minima": CONFIANCA_MINIMA, "processos": processos}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", required=True)
    ap.add_argument("--saida", required=True)
    a = ap.parse_args()
    saida = Path(a.saida).resolve()
    if str(saida).lower().startswith(str(RAIZ).lower()) or "onedrive" in str(saida).lower():
        print(json.dumps({"erro": "Saída deve ficar no runtime (fora do projeto e de pastas sincronizadas)."}, ensure_ascii=False))
        return 2
    try:
        resultado = reconhecer(a.pasta)
    except extrator.ViolacaoCaminho as e:
        print(json.dumps({"erro": str(e)}, ensure_ascii=False))
        return 2
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"processos": {p: {c: v["status"] for c, v in r["campos"].items()} for p, r in resultado["processos"].items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
