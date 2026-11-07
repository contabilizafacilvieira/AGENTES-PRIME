"""Salvaguardas de Documentos: PDF protegido, caches de OCR/PDF, IDs de tarefa e mensagens de erro.

Somente dados fictícios gerados em diretórios temporários. AGENTES_PRIME_RUNTIME e LOCALAPPDATA são
temporários; RAIZ do módulo é redirecionada para uma pasta temporária; nenhum documento real é lido.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'API-LOCAL'))
sys.path.insert(0, str(RAIZ / 'AGENTES/DOCUMENTOS/ferramentas'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import documentos_local as docs
import extrair_documentos as extrator
import leitura_pdf_local as leitor_pdf
from testar_extrato_santander import pdf_ficticio
from pypdf import PdfReader, PdfWriter

SHA = 'ab' * 32


def pdf_protegido(senha_usuario=''):
    """Senha de usuário vazia = proteção somente de proprietário (abre sem senha em visualizadores)."""
    w = PdfWriter(); w.append(PdfReader(io.BytesIO(pdf_ficticio())))
    w.encrypt(user_password=senha_usuario, owner_password='dono-ficticio', algorithm='RC4-128')
    b = io.BytesIO(); w.write(b); return b.getvalue()


def proibir_senha():
    """Qualquer tentativa de senha (inclusive vazia) falha o teste."""
    from pypdf import _encryption
    return [patch.object(PdfReader, 'decrypt', side_effect=AssertionError('decrypt chamado')),
            patch.object(_encryption.Encryption, 'verify', side_effect=AssertionError('senha verificada'))]


class Ambiente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='prime-salvaguardas-'); self.base = Path(self.tmp.name)
        self.runtime = self.base / 'runtime'; self.local = self.base / 'localappdata'
        self.env = patch.dict(os.environ, {'AGENTES_PRIME_RUNTIME': str(self.runtime), 'LOCALAPPDATA': str(self.local)})
        self.env.start()
        self.raiz = patch.object(docs, 'RAIZ', self.base / 'raiz'); self.raiz.start()
        self.empresa = self.base / 'raiz/CLIENTES/FICTICIA'; (self.empresa / 'LOTE').mkdir(parents=True)

    def tearDown(self):
        self.raiz.stop(); self.env.stop(); self.tmp.cleanup()


class PdfProtegidoNoExtrator(Ambiente):
    def ler(self, dados):
        arq = self.base / 'ficticio.pdf'; arq.write_bytes(dados)
        antes = hashlib.sha256(arq.read_bytes()).hexdigest()
        try:
            r = extrator.ler_pdf(arq)
        except extrator.Resultado as e:
            r = {'leitura': e.leitura, 'observacao': e.observacao, 'marcacoes': e.marcacoes}
        self.assertEqual(hashlib.sha256(arq.read_bytes()).hexdigest(), antes, 'original alterado')
        return r

    def test_somente_proprietario_fica_protegido_sem_tentar_senha(self):
        dados = pdf_protegido(''); travas = proibir_senha()
        for t in travas: t.start()
        try: r = self.ler(dados)
        finally:
            for t in travas: t.stop()
        self.assertEqual(r['leitura'], 'PDF_PROTEGIDO')
        self.assertNotIn('conteudo', r)
        self.assertIn('nenhuma senha', r['observacao'].lower())

    def test_senha_de_usuario_fica_protegido(self):
        r = self.ler(pdf_protegido('usuario-ficticio'))
        self.assertEqual(r['leitura'], 'PDF_PROTEGIDO'); self.assertNotIn('conteudo', r)

    def test_pdf_sem_protecao_continua_lido(self):
        self.assertEqual(self.ler(pdf_ficticio())['leitura'], 'EXTRAIDO_PDF')


def concluido(args, rc=0, stdout='', stderr=''):
    return subprocess.CompletedProcess(args, rc, stdout, stderr)


class FalsoSubprocesso:
    """Substitui o extrator e os processos filhos; registra as chamadas."""
    def __init__(self, arquivos, filhos):
        self.arquivos, self.filhos, self.chamadas = arquivos, list(filhos), []

    def __call__(self, args, **kw):
        self.chamadas.append(args)
        if '--completo' in args:
            return concluido(args, stdout=json.dumps({'arquivos': json.loads(json.dumps(self.arquivos))}))
        r = self.filhos.pop(0)
        if isinstance(r, BaseException): raise r
        return concluido(args, *r)


class CacheOcrImagem(Ambiente):
    def arquivos(self):
        (self.empresa / 'LOTE/img.png').write_bytes(b'imagem ficticia')
        return [{'arquivo': 'LOTE/img.png', 'extensao': '.png', 'leitura': 'DOCUMENTO_REQUER_OCR', 'sha256': SHA}]

    def rodar(self, filhos):
        f = FalsoSubprocesso(self.arquivos(), filhos)
        with patch.object(docs.subprocess, 'run', f):
            return docs.extrair('FICTICIA', 'LOTE')['arquivos'][0], f

    def caches(self):
        return sorted(p.relative_to(self.base).as_posix() for p in self.base.rglob('*.json') if 'ocr' in p.as_posix())

    def test_falha_do_filho_nao_vai_para_cache(self):
        a, _ = self.rodar([(1, '', 'falha fictícia')])
        self.assertEqual(self.caches(), [], 'resultado de falha foi gravado em cache')
        self.assertEqual(a['leitura'], 'DOCUMENTO_REQUER_OCR')
        self.assertNotIn('sem confiança suficiente', a.get('observacao', ''))

    def test_timeout_nao_vai_para_cache(self):
        a, _ = self.rodar([subprocess.TimeoutExpired('ocr', 90)])
        self.assertEqual(self.caches(), []); self.assertEqual(a['leitura'], 'DOCUMENTO_REQUER_OCR')

    def test_resultado_valido_vai_para_cache_do_runtime(self):
        valido = json.dumps({'utilizavel': True, 'texto': 'RECIBO FICTICIO 10,00', 'confianca': 0.95})
        a, _ = self.rodar([(0, valido, '')])
        self.assertEqual(a['leitura'], 'EXTRAIDO_TEXTO')
        cache = list((self.runtime / 'ocr-local').glob(SHA + '*.json'))
        self.assertEqual(len(cache), 1, 'cache de OCR fora de AGENTES_PRIME_RUNTIME')
        self.assertFalse((self.local / 'AgentesPrime/ocr-local').exists(), 'LOCALAPPDATA usado com runtime definido')
        a2, f2 = self.rodar([])          # segunda leitura vem do cache, sem processo filho
        self.assertEqual(a2['leitura'], 'EXTRAIDO_TEXTO'); self.assertEqual(len(f2.chamadas), 1)

    def test_cache_invalido_e_ignorado_e_refeito(self):
        valido = json.dumps({'utilizavel': True, 'texto': 'RECIBO FICTICIO 10,00', 'confianca': 0.95})
        self.rodar([(0, valido, '')])
        cache = next((self.runtime / 'ocr-local').glob(SHA + '*.json'))
        for lixo in ('{}', 'nao-e-json', '[]', json.dumps({'utilizavel': True})):
            cache.write_text(lixo, encoding='utf-8')
            a, f = self.rodar([(0, valido, '')])
            self.assertEqual(len(f.chamadas), 2, f'cache inválido usado: {lixo}')
            self.assertEqual(a['leitura'], 'EXTRAIDO_TEXTO')
            self.assertEqual(json.loads(cache.read_text(encoding='utf-8'))['utilizavel'], True)


class CachePdf(Ambiente):
    def arquivos(self):
        (self.empresa / 'LOTE/doc.pdf').write_bytes(pdf_ficticio())
        return [{'arquivo': 'LOTE/doc.pdf', 'extensao': '.pdf', 'leitura': 'EXTRAIDO_PDF', 'sha256': SHA,
                 'conteudo': {'paginas': []}, 'marcacoes': []}]

    def rodar(self, filhos):
        f = FalsoSubprocesso(self.arquivos(), filhos)
        with patch.object(docs.subprocess, 'run', f):
            return docs.extrair('FICTICIA', 'LOTE')['arquivos'][0], f

    def valido(self):
        return json.dumps(leitor_pdf.ler(self.empresa / 'LOTE/doc.pdf'), ensure_ascii=False) if (self.empresa / 'LOTE/doc.pdf').exists() else None

    def test_cache_invalido_e_ignorado_e_refeito(self):
        self.arquivos(); valido = self.valido()
        a, _ = self.rodar([(0, valido, '')])
        self.assertEqual(a['leitura'], 'EXTRAIDO_PDF')
        caches = list((self.runtime / 'leitura-pdf-cache').glob(SHA + '*.json'))
        self.assertEqual(len(caches), 1)
        for lixo in ('{}', 'nao-e-json', json.dumps({'leitura': 'EXTRAIDO_PDF', 'conteudo': 'x'}),
                     json.dumps({'leitura': 'EXTRAIDO_PDF', 'conteudo': {'paginas': 'x'}})):
            caches[0].write_text(lixo, encoding='utf-8')
            a, f = self.rodar([(0, valido, '')])
            self.assertEqual(len(f.chamadas), 2, f'cache PDF inválido usado: {lixo}')
            self.assertEqual(a['leitura'], 'EXTRAIDO_PDF')

    def test_cache_de_versao_anterior_nao_e_usado(self):
        self.arquivos(); valido = self.valido()
        antigo = json.loads(valido); antigo['conteudo']['versao_leitor'] = 'pdf-local-v0'
        pasta = self.runtime / 'leitura-pdf-cache'; pasta.mkdir(parents=True)
        for nome in (SHA + '-pdf-local-v2.json', SHA + '-' + leitor_pdf.VERSAO + '.json'):
            (pasta / nome).write_text(json.dumps(antigo), encoding='utf-8')
        a, f = self.rodar([(0, valido, '')])
        self.assertEqual(len(f.chamadas), 2, 'cache de versão anterior reaproveitado')

    def test_falha_do_leitor_pdf_nao_vai_para_cache(self):
        a, _ = self.rodar([(1, '', 'falha fictícia')])
        self.assertTrue(a['conteudo']['leitura_incompleta'])
        self.assertEqual(list(self.base.rglob('*pdf-local*.json')), [])


class Mensagens(Ambiente):
    def test_stderr_cp1252_nao_perde_mensagem(self):
        script = self.base / 'falso_extrator.py'
        script.write_text("import sys\nsys.stderr.buffer.write('Falha fictícia na extração: ação'.encode('cp1252'))\nsys.exit(1)\n",
                          encoding='utf-8')
        with patch.object(docs, 'EXTRATOR', script):
            with self.assertRaises(ValueError) as ctx:
                docs.extrair('FICTICIA', 'LOTE')
        self.assertIn('Extrator local indisponível', str(ctx.exception))
        self.assertIn('Falha fict', str(ctx.exception))


class IdsDeTarefa(unittest.TestCase):
    def item(self, nome, sha):
        return {'arquivo': nome, 'sha256': sha, 'leitura': 'EXTRAIDO_TEXTO', 'leitura_pendente': False,
                'encaminhamento': {'area': 'FISCAL', 'copias_suporte': ['FINANCEIRO']}}

    def test_ids_unicos_para_duplicados_identicos_e_deterministicos(self):
        itens = [self.item('LOTE/a.txt', SHA), self.item('LOTE/copia/a.txt', SHA), self.item('LOTE/b.txt', 'cd' * 32)]
        t1, t2 = docs.montar_tarefas(itens), docs.montar_tarefas(json.loads(json.dumps(itens)))
        for area in ('FISCAL', 'FINANCEIRO'):
            ids = [d['id'] for d in t1[area]['documentos']]
            self.assertEqual(len(ids), len(set(ids)), f'IDs repetidos em {area}: {ids}')
            self.assertEqual(ids, [d['id'] for d in t2[area]['documentos']])
        # documento sem duplicata mantém o formato anterior
        self.assertEqual(t1['FISCAL']['documentos'][2]['id'], 'TD-' + ('CD' * 6) + '-FISCAL')


if __name__ == '__main__': unittest.main(verbosity=2)
