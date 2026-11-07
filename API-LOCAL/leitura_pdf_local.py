"""Leitura técnica por página, offline; nunca modifica o PDF, nunca tenta senha e nunca desbloqueia PDF protegido."""
import mmap
import re
from pathlib import Path

# v3: PDF criptografado (inclusive só de proprietário) deixou de ser lido; caches v2 não são reaproveitados.
VERSAO = 'pdf-local-v3'
MAX_PAGINAS = 500
MAX_CARACTERES = 2_000_000
_OCR = None


def legivel(texto):
    if not texto or re.search(r'\(cid:\d+\)', texto) or '\ufffd' in texto:
        return False
    letras = re.findall(r'[A-Za-zÀ-ÿ]', texto)
    return len(letras) >= 8 and len(re.findall(r'[A-Za-zÀ-ÿ]{2,}', texto)) >= 2


def motor_ocr():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    return _OCR


def reconhecer(imagem):
    """Conserva texto e confiança; confiança baixa pede conferência, não desaparece."""
    import numpy as np
    from PIL import ImageOps
    melhor, nota = None, -1
    for angulo in (0, 90, 180, 270):
        im = imagem.rotate(angulo, expand=True) if angulo else imagem
        im = ImageOps.autocontrast(im.convert('L')).convert('RGB')
        resultado, _ = motor_ocr()(np.array(im))
        trechos = [{'texto': t, 'confianca': float(c), 'caixa': [[float(v) for v in ponto] for ponto in caixa]}
                   for caixa, t, c in (resultado or []) if t.strip()]
        score = sum(len(t['texto']) * t['confianca'] for t in trechos if t['confianca'] >= .80)
        if score > nota:
            cs = [t['confianca'] for t in trechos]
            melhor = {'texto': '\n'.join(t['texto'] for t in trechos), 'trechos': trechos,
                      'confianca_minima': min(cs, default=0), 'confianca_media': sum(cs) / len(cs) if cs else 0,
                      'rotacao_ocr': angulo}
            nota = score
        if trechos and min(t['confianca'] for t in trechos) >= .90:
            break
    return melhor


def imagem_principal(pagina):
    try:
        recursos = pagina.get('/Resources') or {}
        if hasattr(recursos, 'get_object'): recursos = recursos.get_object()
        xs = recursos.get('/XObject') or {}
        return any(o.get_object().get('/Subtype') == '/Image' and
                   o.get_object().get('/Width', 0) >= 400 and o.get_object().get('/Height', 0) >= 400
                   for o in xs.get_object().values()) if hasattr(xs, 'get_object') else False
    except Exception:
        return False


PROTEGIDO = {'leitura': 'PDF_PROTEGIDO', 'conteudo': {},
             'observacao': 'PDF criptografado/protegido (inclusive proteção somente de proprietário). Por tratamento '
                           'conservador, nenhuma senha foi tentada (nem vazia), o arquivo não foi desbloqueado nem '
                           'alterado e não houve extração de texto nem OCR. Envie cópia sem proteção.'}
_ENCRYPT = re.compile(rb'/Encrypt\s*(?:\d+\s+\d+\s+R|<<)')


def marcador_criptografia(caminho):
    """Detecta o dicionário /Encrypt nos bytes do arquivo, sem abrir o PDF nem verificar senha alguma."""
    with open(caminho, 'rb') as f:
        if f.seek(0, 2) == 0: return False
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
            return _ENCRYPT.search(m) is not None


def protegido_pdfium(pdf):
    import pypdfium2.raw as pdfium_c
    return pdfium_c.FPDF_GetSecurityHandlerRevision(pdf.raw) != -1


def resultado_protegido():
    return {'leitura': PROTEGIDO['leitura'], 'conteudo': {}, 'observacao': PROTEGIDO['observacao']}


def ler(caminho):
    from pypdf import PdfReader
    import pypdfium2 as pdfium
    caminho = Path(caminho)
    leitor, pdf, erro_pypdf = None, None, None
    # Verificação antes de qualquer leitor: o PdfReader testa a senha vazia ao abrir um PDF criptografado.
    try:
        if marcador_criptografia(caminho): return resultado_protegido()
    except (OSError, ValueError):
        pass
    try:
        leitor = PdfReader(str(caminho), strict=False)
        if leitor.is_encrypted:
            return resultado_protegido()
        total = len(leitor.pages)
    except Exception as exc:
        erro_pypdf = type(exc).__name__
        try:
            pdf = pdfium.PdfDocument(str(caminho))
            if protegido_pdfium(pdf):
                pdf.close(); return resultado_protegido()
            total = len(pdf)
        except Exception:
            return {'leitura': 'ARQUIVO_CORROMPIDO', 'conteudo': {},
                    'observacao': 'PDF não pôde ser aberto pelos leitores locais; pode estar danificado ou protegido.'}
    if not total:
        if pdf: pdf.close()
        return {'leitura': 'DOCUMENTO_VAZIO', 'conteudo': {}, 'observacao': 'PDF sem páginas.'}
    paginas, caracteres = [], 0
    try:
        for indice in range(min(total, MAX_PAGINAS)):
            pagina_pdfium = None
            p = {'pagina': indice + 1, 'texto': '', 'situacao': 'PENDENTE', 'origem': None}
            try:
                pagina = leitor.pages[indice] if leitor else None
                try: texto = (pagina.extract_text() or '') if pagina is not None else ''
                except Exception: texto = ''
                precisa_imagem = pagina is not None and imagem_principal(pagina) and len(texto.split()) < 30
                if legivel(texto) and not precisa_imagem:
                    p.update(texto=texto, situacao='TEXTO', origem='PYPDF')
                else:
                    if pdf is None:
                        pdf = pdfium.PdfDocument(str(caminho))
                        if protegido_pdfium(pdf):
                            pdf.close(); return resultado_protegido()
                    pagina_pdfium = pdf[indice]
                    tp = pagina_pdfium.get_textpage()
                    try: alternativo = tp.get_text_range()
                    finally: tp.close()
                    if legivel(alternativo) and not precisa_imagem:
                        p.update(texto=alternativo, situacao='TEXTO', origem='PDFIUM')
                    else:
                        w, h = pagina_pdfium.get_size()
                        escala = min(2.5, (16_000_000 / max(w * h, 1)) ** .5)
                        bitmap = pagina_pdfium.render(scale=escala)
                        try: imagem = bitmap.to_pil().convert('RGB').copy()
                        finally: bitmap.close()
                        extremos = imagem.convert('L').getextrema()
                        if extremos[1] - extremos[0] < 8:
                            p.update(situacao='VAZIA', origem='RENDER_LOCAL')
                        else:
                            o = reconhecer(imagem)
                            p.update(o, origem='OCR_LOCAL')
                            p['requer_conferencia'] = o['confianca_minima'] < .90
                            p['situacao'] = ('OCR_CONFERIR' if p['requer_conferencia'] else 'OCR') if o['texto'] else 'ILEGIVEL'
                caracteres += len(p['texto'])
                if caracteres > MAX_CARACTERES:
                    p.update(texto='', situacao='LIMITE_TEXTO', requer_conferencia=True)
                    paginas.append(p); break
            except Exception as exc:
                p.update(situacao='ERRO_LEITURA', erro=type(exc).__name__, requer_conferencia=True)
            finally:
                if pagina_pdfium is not None: pagina_pdfium.close()
            paginas.append(p)
    finally:
        if pdf is not None: pdf.close()
    pendentes = [p['pagina'] for p in paginas if p['situacao'] in ('ILEGIVEL', 'ERRO_LEITURA', 'LIMITE_TEXTO')]
    conferir = [p['pagina'] for p in paginas if p.get('requer_conferencia')]
    incompleta = bool(pendentes) or len(paginas) != total
    houve_ocr = any(p.get('origem') == 'OCR_LOCAL' for p in paginas)
    if any(p['texto'] for p in paginas): leitura = 'EXTRAIDO_PDF'
    elif paginas and len(paginas) == total and all(p['situacao'] == 'VAZIA' for p in paginas): leitura = 'DOCUMENTO_VAZIO'
    else: leitura = 'DOCUMENTO_REQUER_OCR'
    if leitura == 'DOCUMENTO_VAZIO':
        observacao = 'PDF sem texto e com páginas renderizadas em branco; nenhum conteúdo foi interpretado.'
    elif houve_ocr:
        observacao = 'Leitura local por página com OCR local; texto OCR duvidoso é apresentado para conferência, sem validação automática de valores.'
    else:
        observacao = 'Leitura local por página da camada de texto digital (sem reconhecimento de imagem); sem validação automática de valores.'
    return {'leitura': leitura,
            'conteudo': {'paginas_total': total, 'paginas': paginas, 'paginas_requer_ocr': pendentes,
                         'paginas_vazias': [p['pagina'] for p in paginas if p['situacao'] == 'VAZIA'],
                         'paginas_conferir_ocr': conferir, 'leitura_incompleta': incompleta,
                         'requer_conferencia_ocr': bool(conferir), 'versao_leitor': VERSAO,
                         'alternativa_apos_erro_pypdf': erro_pypdf},
            'observacao': observacao}
