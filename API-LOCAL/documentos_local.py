"""Inventário e extração locais. Não interpreta documentos nem chama modelos externos."""
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import time
import unicodedata
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
def clientes():
    """Pasta CLIENTES (avaliada a cada uso: AGENTES_PRIME_CLIENTES em testes isolados; RAIZ/CLIENTES em produção)."""
    return Path(os.environ.get("AGENTES_PRIME_CLIENTES") or RAIZ / "CLIENTES")
EXTRATOR = RAIZ / 'AGENTES/DOCUMENTOS/ferramentas/extrair_documentos.py'
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from leitura_pdf_local import VERSAO as VERSAO_PDF   # leitor usa importação tardia: sem custo aqui


def pasta_cache(nome):
    """Mesma regra para os caches de PDF e de OCR: AGENTES_PRIME_RUNTIME tem precedência sobre LOCALAPPDATA."""
    base = os.environ.get('AGENTES_PRIME_RUNTIME')
    raiz = Path(base) if base else Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AgentesPrime'
    pasta = raiz / nome
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def ler_cache(arquivo, valido):
    """Cache ilegível ou com estrutura inválida é ignorado (e refeito pelo chamador)."""
    try:
        o = json.loads(arquivo.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return o if valido(o) else None


def gravar_cache(pasta, arquivo, o):
    temp = pasta / (arquivo.stem + '-' + str(os.getpid()) + '.tmp')
    temp.write_text(json.dumps(o, ensure_ascii=False), encoding='utf-8'); temp.replace(arquivo)


def resultado_pdf_valido(o):
    if not isinstance(o, dict) or not isinstance(o.get('leitura'), str) or not o['leitura']: return False
    c = o.get('conteudo')
    if not isinstance(c, dict): return False
    if o['leitura'] in ('EXTRAIDO_PDF', 'DOCUMENTO_REQUER_OCR') or c:
        return (c.get('versao_leitor') == VERSAO_PDF and isinstance(c.get('paginas'), list)
                and all(isinstance(p, dict) and isinstance(p.get('texto', ''), str) for p in c['paginas']))
    return True


def resultado_ocr_valido(o):
    if not isinstance(o, dict) or not isinstance(o.get('utilizavel'), bool): return False
    if not o['utilizavel']: return True
    conf = o.get('confianca')
    return (isinstance(o.get('texto'), str) and bool(o['texto'].strip()) and isinstance(conf, (int, float))
            and not isinstance(conf, bool) and 0 <= conf <= 1)


def detalhe_erro(p):
    return ((p.stderr or '') or (p.stdout or '')).strip()[-300:]


def extrair(empresa, pasta):
    p = subprocess.run([sys.executable, '-I', str(EXTRATOR), '--empresa', empresa, '--pasta', pasta, '--completo'],
                       cwd=RAIZ, capture_output=True, encoding='utf-8', errors='replace', timeout=1800)
    if p.returncode:
        raise ValueError('Extrator local indisponível: ' + detalhe_erro(p))
    dados = json.loads(p.stdout)
    base = clientes() / empresa
    for a in dados['arquivos']:
        leitura = a.get('leitura','')
        if a.get('extensao') == '.pdf' and leitura != 'PDF_PROTEGIDO':
            caminho = (base / a['arquivo']).resolve(); caminho.relative_to(base.resolve())
            try:
                cache = pasta_cache('leitura-pdf-cache')
                arq_cache = cache / (a['sha256'] + '-' + VERSAO_PDF + '.json')
                o = ler_cache(arq_cache, resultado_pdf_valido)
                if o is None:
                    filho = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--pdf', str(caminho)],
                                           capture_output=True, encoding='utf-8', errors='replace', timeout=300)
                    if filho.returncode: raise ValueError('Leitor PDF local falhou: ' + detalhe_erro(filho))
                    o = json.loads(filho.stdout)
                    if not resultado_pdf_valido(o): raise ValueError('Retorno PDF inválido.')
                    gravar_cache(cache, arq_cache, o)   # somente resultado válido vai para o cache
                a.update(o)
                if o['leitura'] == 'PDF_PROTEGIDO':
                    a['marcacoes'] = [m for m in a.get('marcacoes', []) if m != 'PDF_CRIPTOGRAFADO_SEM_SENHA']
                if not o['conteudo'].get('leitura_incompleta') and o['leitura'] == 'EXTRAIDO_PDF':
                    a['marcacoes'] = [m for m in a.get('marcacoes', []) if m not in ('LIMITE_EXCEDIDO', 'PAGINAS_REQUEREM_OCR')]
            except (OSError, ValueError, subprocess.TimeoutExpired):
                a['observacao'] = 'Leitura PDF complementar falhou ou excedeu 300 segundos; o conteúdo disponível é parcial.'
                a.setdefault('conteudo', {})['leitura_incompleta'] = True
            continue
        if leitura == 'DOCUMENTO_REQUER_OCR' and a.get('extensao') in ('.png','.jpg','.jpeg'):
            caminho = (base / a['arquivo']).resolve()
            caminho.relative_to(base.resolve())
            try:
                cache = pasta_cache('ocr-local')
                arq_cache = cache / (a['sha256'] + '-v1.json')
                o = ler_cache(arq_cache, resultado_ocr_valido)
                if o is None:
                    filho = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--ocr', str(caminho)],
                                           capture_output=True, encoding='utf-8', errors='replace', timeout=90)
                    if filho.returncode: raise ValueError('Processo de OCR falhou: ' + detalhe_erro(filho))
                    o = json.loads(filho.stdout)
                    if not resultado_ocr_valido(o): raise ValueError('Retorno de OCR inválido.')
                    gravar_cache(cache, arq_cache, o)   # falha e timeout nunca são gravados
                if o['utilizavel']:
                    a.update(leitura='EXTRAIDO_TEXTO', conteudo={'texto': o['texto'], 'origem': 'OCR_LOCAL',
                                                              'confianca_minima': o['confianca']},
                             observacao='OCR local conservador; conferir valores e documento original.')
                else:
                    a['observacao'] = 'OCR local sem confiança suficiente; exige conferência/documento estruturado.'
            except (OSError, ValueError, subprocess.TimeoutExpired):
                a['observacao'] = 'OCR local indisponível, falhou ou excedeu 90 segundos; documento pendente (nada gravado em cache).'
    return dados


def ocr_arquivo(caminho):
    import sys
    sys.path.insert(0, str(RAIZ / 'AGENTES/IMPORTACAO/ferramentas'))
    from reconhecer_documentos_vgrow import ocr, paginas
    linhas, confiancas = [], []
    if caminho.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        if len(PdfReader(str(caminho)).pages) > 30:
            return {'utilizavel': False}
        for _, caixas, _ in paginas(caminho):
            for _, _, _, texto, conf in caixas:
                linhas.append(texto); confiancas.append(conf)
    else:
        from PIL import Image
        import numpy as np
        with Image.open(caminho) as im:
            if im.width*im.height > 20_000_000:
                return {'utilizavel': False}
            resultados, _ = ocr()(np.array(im.convert('RGB')))
            for _, texto, conf in resultados or []:
                linhas.append(texto); confiancas.append(float(conf))
    minimo = min(confiancas, default=0)
    return {'utilizavel': bool(linhas) and minimo >= 0.90, 'texto': '\n'.join(linhas), 'confianca': minimo}


FOLHA_FORTE = ('DEMONSTRATIVO DE PAGAMENTO DE SALARIO', 'RECIBO DE PAGAMENTO DE SALARIO', 'HOLERITE')
# Demonstrativos de pessoal com layout documentado (CONTRATO 3.1–3.3): rótulos fortes de DP.
RESUMOS_DP = (('RESUMO DA FOLHA DE PAGAMENTO', 'Resumo da folha de pagamento'),
              ('RESUMO DE ENCARGOS DA FOLHA', 'Resumo de encargos da folha'),
              ('DEMONSTRATIVO DE PROVISOES', 'Demonstrativo de provisões'))
NOTA = ('DANFE', 'NOTA FISCAL', 'NFS-E', 'NFSE')
GUIA = ('DOCUMENTO DE ARRECADACAO', 'DARF')
AMBIGUO = 'Classificação ambígua: '
# Cabeçalhos tabulares documentados (CSV ';' ou planilha), normalizados com '_' no lugar de espaços.
CAB_EXTRATO = {'CONTA', 'DATA', 'TIPO', 'HISTORICO', 'VALOR', 'SALDO'}
CAB_POSICAO = {'TIPO', 'POSICAO', 'DATA_BASE', 'CONTRAPARTE', 'TITULO', 'VALOR'}
CAB_SALDOS_ABERTURA = {'CONTA', 'DESCRICAO', 'SALDO', 'NATUREZA', 'DATA_BASE'}
CAB_RELACAO = {'FAVORECIDO', 'VALOR'}
# Layouts tabulares em que os CNPJs são de contrapartes (não identificam a titularidade do arquivo).
SEM_VERIFICACAO_CNPJ = ('Posição de títulos', 'Saldos de abertura', 'Possível relação de pagamentos',
                        'Posição de investimentos', 'Contrato de câmbio')
RE_CNPJ = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")


def sem_acento(texto):
    return unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().upper()


def cabecalhos(a, texto):
    """Primeiras linhas tabulares (CSV ';' ou abas visíveis da planilha) como conjuntos de nomes normalizados."""
    linhas = [l.split(';') for l in texto.splitlines()[:10]]
    if a.get('leitura') == 'EXTRAIDO_PLANILHA':
        for aba in (a.get('conteudo') or {}).get('abas', []):
            if not aba.get('oculta'):
                linhas += [l.get('valores') or [] for l in aba.get('linhas', [])[:10]]
    return [{re.sub(r'\s+', '_', sem_acento(c).strip()) for c in l if c is not None} for l in linhas]


def cnpjs_identificados(texto):
    """CNPJs com barra ou precedidos do rótulo CNPJ (sequências de código de barras não contam)."""
    t = sem_acento(texto)
    return sorted({re.sub(r'\D', '', m.group(0)) for m in RE_CNPJ.finditer(t)
                   if '/' in m.group(0) or 'CNPJ' in t[max(0, m.start() - 35):m.start()]})


def formatar_cnpj(c):
    return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}' if len(c) == 14 else c


def cnpjs_cadastro(empresa):
    """CNPJs do CADASTRO.md da empresa (mesma leitura de conferencia_financeira.cadastro). None = cadastro ausente."""
    arquivo = clientes() / empresa / 'CADASTRO.md'
    if not arquivo.is_file():
        return None
    return sorted({re.sub(r'\D', '', c) for c in re.findall(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', arquivo.read_text(encoding='utf-8'))})


def classificar(a):
    if (a.get('conteudo') or {}).get('tipo') == 'CANCELAMENTO': return 'Evento fiscal'
    if a.get('leitura') == 'EXTRAIDO_NFE':
        return 'Nota fiscal XML'
    if a.get('extensao') == '.ofx':
        return 'Extrato OFX (classificação por formato)'
    c = a.get('conteudo') or {}
    texto = c.get('texto', '') + '\n'.join(x.get('texto', '') for x in c.get('paginas', []))
    t = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().upper()
    if ('EXTRATO DE MOVIMENTACAO MENSAL' in t and any(x in t for x in ('CDB', 'ITAUVEST'))) or 'MONTHLY CONSOLIDATED POSITION' in t:
        return 'Posição de investimentos'
    if 'CONTRATO DE CAMBIO' in t or ('NOTA DE NEGOCIACAO' in t and 'TAXA CAMBIAL' in t):
        return 'Contrato de câmbio'
    # O histórico bancário pode mencionar folha ou notas: o cabeçalho do extrato tem precedência.
    if 'SANTANDER EMPRESAS' in t and re.search(r'AGENCIA:\s*\d+\s+CONTA:', t):
        return 'Extrato PDF Santander Empresas (leitura pelo Financeiro)'
    cabs = cabecalhos(a, texto)
    if any(CAB_EXTRATO <= c for c in cabs):
        return 'Extrato CSV (classificação por cabeçalho)'
    # Layouts tabulares documentados: o cabeçalho define o tipo (o conteúdo das colunas não troca o destino).
    if any(CAB_POSICAO <= c for c in cabs):
        return 'Posição de títulos'
    if any(CAB_SALDOS_ABERTURA <= c for c in cabs):
        return 'Saldos de abertura'
    if any(CAB_RELACAO <= c for c in cabs):
        return 'Possível relação de pagamentos'
    primeira = next((l.strip() for l in t.splitlines() if l.strip()), '')
    if primeira.startswith('CONFIRMACAO DE SALDO'):
        return 'Confirmação de saldo'
    # Precedência (o rótulo do próprio documento vence menções no corpo):
    # nota fiscal > guia de arrecadação > folha; boleto/recibo/comprovante só valem sem guia ou nota.
    # Indícios fortes e conflitantes não são resolvidos aqui: vão à triagem, sem área presumida.
    resumos = [(x, tipo) for x, tipo in RESUMOS_DP if x in t]
    folha_forte = [x for x in FOLHA_FORTE if x in t] + [x for x, _ in resumos]
    folha = folha_forte + (['FOLHA DE PAGAMENTO'] if 'FOLHA DE PAGAMENTO' in t else [])
    nota = [x for x in NOTA if x in t]
    guia = [x for x in GUIA if re.search(r'\b' + x + r'\b', t)]
    if nota and folha_forte:
        return AMBIGUO + 'nota fiscal e documento de pessoal (' + ', '.join(nota + folha_forte) + ')'
    if guia and folha:
        return AMBIGUO + 'guia de arrecadação e folha/documento de pessoal (' + ', '.join(guia + folha) + ')'
    if folha and not nota:
        # Mais de um demonstrativo no mesmo arquivo não é desmembrado aqui: segue como documento de pessoal genérico.
        return resumos[0][1] if len(resumos) == 1 else 'Folha / documento de pessoal'
    if 'DEMONSTRATIVO DE APURACAO' in t: return 'Demonstrativo de apuração'
    if nota:
        return 'Possível nota fiscal'
    if guia:
        return 'Possível guia'
    for termo, tipo in [('FAVORECIDO;', 'Possível relação de pagamentos'), ('<OFX>', 'Extrato OFX'),
                        ('COMPROVANTE', 'Possível comprovante'), ('BOLETO', 'Possível boleto'),
                        ('FICHA DE COMPENSACAO', 'Possível boleto'), ('RECIBO DO PAGADOR', 'Possível boleto'),
                        ('LINHA DIGITAVEL', 'Possível boleto'), ('DOCUMENTO DE ARRECADACAO', 'Possível guia'),
                        ('RECIBO', 'Possível recibo'),
                        ('RAZAO', 'Possível razão'), ('DARF', 'Possível guia')]:
        if termo in t:
            return tipo
    return 'Tipo a conferir; sem interpretação automática'


def nao_identifica_empresa(a, tipo, cnpjs_empresa):
    """CNPJs identificados no texto sem nenhum CNPJ da empresa da SOL. None = verificação não se aplica ou empresa presente."""
    if cnpjs_empresa is None or tipo.startswith('Extrato ') or tipo in SEM_VERIFICACAO_CNPJ:
        return None
    achados = cnpjs_identificados(texto_de_documento(a))
    if not achados or set(achados) & set(cnpjs_empresa):
        return None
    return achados


def encaminhamento(a, cnpjs_empresa=None):
    """Triagem técnica; não valida natureza, competência contábil ou regularidade fiscal.

    cnpjs_empresa (CNPJs do CADASTRO.md da empresa da SOL): quando informado, documento cujo texto identifica CNPJs e
    nenhum deles é da empresa não é distribuído (vai à TRIAGEM). Sem cadastro, a verificação não é feita."""
    tipo = classificar(a)
    outros = nao_identifica_empresa(a, tipo, cnpjs_empresa)
    if outros:
        texto = 'documento não identifica esta empresa (CNPJs: ' + ', '.join(formatar_cnpj(c) for c in outros) + ')'
        return {'area': None, 'situacao': 'DOCUMENTO_NAO_IDENTIFICA_EMPRESA', 'copias_suporte': [], 'tipo': tipo,
                'cnpjs_identificados': outros, 'observacao': texto + '; não distribuído (isolamento entre empresas).',
                'acao_necessaria': 'Confirmar a titularidade: se o documento for de outra empresa, retirá-lo deste lote e '
                                   'enviá-lo na solicitação da empresa correta; se for desta empresa, enviar versão que a identifique.'}
    if tipo == 'Confirmação de saldo':
        return {'area': 'CONCILIACAO', 'situacao': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'copias_suporte': [], 'tipo': tipo,
                'observacao': 'Evidência de terceiro destinada à Conciliação; Documentos não confere o saldo.'}
    if tipo == 'Saldos de abertura':
        return {'area': 'CONCILIACAO', 'situacao': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'copias_suporte': [], 'tipo': tipo,
                'observacao': 'Controle interno de saldos de abertura destinado à Conciliação; Documentos não confere saldos.'}
    if tipo == 'Posição de títulos':
        return {'area': 'FINANCEIRO', 'situacao': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'copias_suporte': ['CONCILIACAO'], 'tipo': tipo,
                'observacao': 'Posição de títulos (controle interno): Financeiro confere liquidações; cópia à Conciliação.'}
    if tipo == 'Demonstrativo de apuração':
        # Somente Fiscal: não é suporte de pagamento (cópia ao Financeiro geraria pendência falsa).
        return {'area': 'FISCAL', 'situacao': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'copias_suporte': [], 'tipo': tipo,
                'observacao': 'Demonstrativo de apuração destinado somente ao Fiscal. Não constitui apuração tributária completa.'}
    if tipo in ('Nota fiscal XML', 'Possível nota fiscal', 'Possível guia', 'Evento fiscal'):
        return {'area': 'FISCAL', 'situacao': 'DISPONIVEL_PARA_ENCAMINHAMENTO',
                'copias_suporte': ['FINANCEIRO'], 'tipo': tipo,
                'observacao': 'Fiscal documental local; cópia ao Financeiro para conferir pagamento. Não constitui apuração tributária completa.'}
    if tipo.startswith(AMBIGUO):
        return {'area': None, 'situacao': 'AGUARDANDO_IDENTIFICACAO', 'copias_suporte': [], 'tipo': tipo,
                'indicios': tipo[len(AMBIGUO):],
                'observacao': 'Indícios conflitantes de áreas diferentes; destino não presumido. Conferir na triagem '
                              '(Documentos não decide natureza contábil).'}
    if tipo == 'Resumo da folha de pagamento':
        return {'area': 'DP', 'situacao': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'copias_suporte': ['FINANCEIRO'], 'tipo': tipo,
                'observacao': 'Análise da folha pelo DP; cópia ao Financeiro como suporte do pagamento de salários '
                              '(sem análise de folha pelo Financeiro).'}
    if tipo in ('Folha / documento de pessoal', 'Resumo de encargos da folha', 'Demonstrativo de provisões'):
        return {'area': 'DP', 'situacao': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'copias_suporte': [],
                'tipo': tipo, 'observacao': 'Documento de pessoal destinado ao DP; o Coordenador decide a execução da área.'}
    if tipo.startswith('Extrato '):
        return {'area': 'FINANCEIRO', 'situacao': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'copias_suporte': ['CONCILIACAO'],
                'tipo': tipo, 'observacao': 'Conferência dos movimentos é responsabilidade do Financeiro; '
                                            'cópia à Conciliação (saldos do extrato, evidência de terceiro).'}
    if tipo in ('Posição de investimentos', 'Contrato de câmbio', 'Possível relação de pagamentos', 'Possível comprovante', 'Possível boleto', 'Possível recibo'):
        return {'area': 'FINANCEIRO', 'situacao': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'copias_suporte': [],
                'tipo': tipo, 'observacao': 'Conferência dos movimentos e suportes é responsabilidade do Financeiro.'}
    return {'area': None, 'situacao': 'AGUARDANDO_IDENTIFICACAO', 'copias_suporte': [], 'tipo': tipo,
            'observacao': 'Área não reconhecida por formato ou rótulo; não foi presumida.'}


def texto_de_documento(a):
    c = a.get('conteudo') or {}
    return c.get('texto', '') or '\n'.join(p.get('texto', '') for p in c.get('paginas', []))


def montar_tarefas(itens):
    areas = {}
    repetidos = {s for s in (i['sha256'] for i in itens) if sum(1 for j in itens if j['sha256'] == s) > 1}
    for i in itens:
        # Cópias idênticas (mesmo hash) recebem sufixo determinístico pelo caminho; demais mantêm o ID anterior.
        sufixo = ('-' + hashlib.sha256(i['arquivo'].encode('utf-8')).hexdigest()[:8].upper()) if i['sha256'] in repetidos else ''
        e = i['encaminhamento']; principal = e['area'] or 'TRIAGEM'
        for area in [principal] + e.get('copias_suporte', []):
            tarefa = areas.setdefault(area, {'area': area, 'estado': 'PRONTO_PARA_ENCAMINHAMENTO', 'documentos': []})
            # DP está disponível como as demais áreas: o Coordenador decide se executa a etapa.
            situacao = (('DOCUMENTO_NAO_IDENTIFICA_EMPRESA' if e.get('situacao') == 'DOCUMENTO_NAO_IDENTIFICA_EMPRESA'
                         else 'AGUARDANDO_IDENTIFICACAO') if area == 'TRIAGEM' else
                        'AGUARDANDO_LEITURA' if i.get('leitura_pendente') else 'DISPONIVEL')
            doc = {'id': f"TD-{i['sha256'][:12].upper()}{sufixo}-{area}", 'arquivo': i['arquivo'],
                   'sha256': i['sha256'], 'papel': 'PRINCIPAL' if area == principal else 'COPIA_SUPORTE',
                   'situacao': situacao, 'leitura': i['leitura']}
            if area == 'TRIAGEM' and e.get('acao_necessaria'):
                doc.update(observacao=e.get('observacao'), acao_necessaria=e['acao_necessaria'])
            tarefa['documentos'].append(doc)
            if area == 'TRIAGEM': tarefa['estado'] = 'AGUARDANDO_IDENTIFICACAO'
    return areas


def executar(ordem, saida):
    inicio = time.monotonic()
    empresa = re.search(r'^- Empresa: ([A-Z0-9-]+)', ordem, re.M).group(1)
    sol = re.search(r'^- SOL: (SOL-\d{4}-\d{6})', ordem, re.M).group(1)
    comp = re.search(r'^- Competência: (\d{4}-\d{2})', ordem, re.M).group(1)
    pasta = re.search(r'^- Pasta dos documentos \(relativa à pasta da empresa\): (.+)$', ordem, re.M).group(1)
    dados = extrair(empresa, pasta)
    itens, pendencias = [], []
    cnpjs_empresa = cnpjs_cadastro(empresa)
    for a in dados['arquivos']:
        destino = encaminhamento(a, cnpjs_empresa)
        if destino['situacao'] == 'DOCUMENTO_NAO_IDENTIFICA_EMPRESA':
            pendencias.append(f"{a['arquivo']}: {destino['observacao']} Ação necessária: {destino['acao_necessaria']}")
        utilizavel = a.get('leitura', '').startswith('EXTRAIDO_')
        if a.get('leitura') == 'EXTRAIDO_PDF':
            texto = '\n'.join(p.get('texto', '') for p in a.get('conteudo', {}).get('paginas', []))
            # Camada textual não garante conteúdo interpretável; classificação conservadora.
            utilizavel = len(re.findall(r'[A-Za-zÀ-ÿ]{3,}', texto)) >= 3
        c = a.get('conteudo') or {}
        leitura_conferir = bool(c.get('leitura_incompleta') or c.get('requer_conferencia_ocr'))
        if leitura_conferir: utilizavel = False
        if not utilizavel:
            destino['situacao'] = 'AGUARDANDO_LEITURA'
            pendencias.append(f"{a['arquivo']}: {a.get('leitura')} — conteúdo ausente ou não utilizável; conferir documento.")
        if a.get('marcacoes'):
            pendencias.append(f"{a['arquivo']}: marcações {', '.join(a['marcacoes'])}.")
        itens.append({'arquivo': a['arquivo'], 'sha256': a['sha256'], 'leitura': a.get('leitura'),
                      'conteudo_utilizavel': utilizavel, 'leitura_pendente': not utilizavel,
                      'motivo_leitura': a.get('observacao'), 'tipo': destino['tipo'], 'encaminhamento': destino,
                      'paginas_leitura': [{k: p.get(k) for k in ('pagina', 'situacao', 'origem', 'confianca_minima', 'rotacao_ocr')}
                                         for p in c.get('paginas', [])],
                      'texto_para_conferencia': texto_de_documento(a)[:100_000] if leitura_conferir else None,
                      'origem': (a.get('conteudo') or {}).get('origem', 'EXTRATOR_DIGITAL'),
                      'confianca_ocr': (a.get('conteudo') or {}).get('confianca_minima')})
    for d in dados.get('duplicados_exatos', []):
        pendencias.append('Duplicidade exata: ' + ', '.join(d['arquivos']))
    resultado = {'contrato': 'DOCUMENTOS_LOCAL_V1', 'executor': 'LOCAL_SEM_MODELO', 'empresa': empresa, 'sol': sol,
                 'competencia': comp, 'pasta': pasta, 'itens': itens, 'pendencias': pendencias,
                 'limitacoes': ['Documentos recebe, identifica e separa por área; não realiza análise contábil, fiscal ou de folha.',
                               'Classificação por formato e rótulos; não substitui conferência da área responsável.',
                               'Valores e competências não identificados não são inferidos.',
                               'OCR local só aproveitado com confiança mínima 0,90; demais casos ficam pendentes.']
                               + (['CADASTRO.md da empresa ausente: identificação da empresa pelos CNPJs dos documentos não verificada.']
                                  if cnpjs_empresa is None else []),
                 'executado_em': dt.datetime.now().astimezone().isoformat()}
    resultado['tarefas_areas'] = montar_tarefas(itens)
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    extracao_serializada = json.dumps(dados, ensure_ascii=False, indent=2)
    resultado['extracao_sha256'] = hashlib.sha256(extracao_serializada.encode('utf-8')).hexdigest()
    (saida / 'extracao-local.json').write_text(extracao_serializada, encoding='utf-8', newline='')
    (saida / 'documentos-local.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    relatorio = f"# Documentos — execução local\n\n{sol} · {empresa} · {comp}\n\n"
    relatorio += '\n'.join(f"- {i['arquivo']}: {i['tipo']} / {i['leitura']} → {i['encaminhamento']['area'] or 'área a identificar'} · {i['encaminhamento']['situacao']}" for i in itens)
    relatorio += '\n\n## Pendências\n' + '\n'.join('- ' + x for x in pendencias)
    relatorio += '\n\n## Limitações\n' + '\n'.join('- ' + x for x in resultado['limitacoes'])
    return {'relatorio': relatorio, 'problemas': [], 'ferramentas': {'extrator_local': 1}, 'bloqueios': 0,
            'duracao_s': round(time.monotonic() - inicio, 2), 'codigo_saida': 0, 'executor': 'LOCAL_SEM_MODELO'}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv)==3 and sys.argv[1]=='--pdf':
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from leitura_pdf_local import ler
        print(json.dumps(ler(Path(sys.argv[2])), ensure_ascii=False))
    elif len(sys.argv)==3 and sys.argv[1]=='--ocr':
        print(json.dumps(ocr_arquivo(Path(sys.argv[2])), ensure_ascii=False))
    elif len(sys.argv)==4 and sys.argv[1]=='--extrair':
        print(json.dumps(extrair(sys.argv[2], sys.argv[3]), ensure_ascii=False))
    else:
        raise SystemExit('Parâmetros inválidos.')
