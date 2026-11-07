"""Pacotes e integridade na passagem entre áreas; todos os arquivos são fictícios."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'API-LOCAL'))
sys.path.insert(0, str(RAIZ / 'AGENTES/FINANCEIRO/ferramentas'))
import documentos_local as docs
import conferencia_financeira as fin


class Pacotes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='prime-pacotes-'); self.root = Path(self.tmp.name)
        self.base = self.root / 'CLIENTES/FICTICIA'; self.pasta = self.base / 'RECEBIDOS/TESTE'; self.pasta.mkdir(parents=True)
        itens, arquivos = [], []
        for nome, tipo, area, copias in [('extrato.txt', 'Extrato', 'FINANCEIRO', []), ('nota.txt', 'Nota fiscal', 'FISCAL', ['FINANCEIRO']),
                                        ('folha.txt', 'Folha', 'DP', []), ('indefinido.txt', 'Não identificado', None, [])]:
            p = self.pasta / nome; p.write_text('Documento fictício ' + nome, encoding='utf-8'); sha = hashlib.sha256(p.read_bytes()).hexdigest()
            arquivo = 'RECEBIDOS/TESTE/' + nome
            itens.append({'arquivo': arquivo, 'sha256': sha, 'leitura': 'EXTRAIDO_TEXTO', 'tipo': tipo,
                          'conteudo_utilizavel': True, 'leitura_pendente': False,
                          'encaminhamento': {'area': area, 'copias_suporte': copias}})
            arquivos.append({'arquivo': arquivo, 'sha256': sha, 'leitura': 'EXTRAIDO_TEXTO', 'extensao': '.txt', 'conteudo': {'texto': nome}})
        self.d = {'contrato': 'DOCUMENTOS_LOCAL_V1', 'empresa': 'FICTICIA', 'sol': 'SOL-2099-999999',
                  'competencia': '2026-10', 'pasta': 'RECEBIDOS/TESTE', 'itens': itens, 'tarefas_areas': docs.montar_tarefas(itens)}
        self.x = {'arquivos': arquivos}

    def tearDown(self): self.tmp.cleanup()

    def receber(self):
        m, x = self.root / 'manifesto.json', self.root / 'extracao.json'
        m.write_text(json.dumps(self.d), encoding='utf-8'); x.write_text(json.dumps(self.x), encoding='utf-8')
        with patch.object(fin, 'RAIZ', self.root):
            return fin.receber_pacote_local('FICTICIA', '2026-10', 'SOL-2099-999999', 'RECEBIDOS/TESTE', m, x)

    def test_financeiro_recebe_apenas_seu_pacote_e_copias_suporte(self):
        arquivos, triagem = self.receber()
        self.assertEqual({a['arquivo'].split('/')[-1] for a in arquivos}, {'extrato.txt', 'nota.txt'})
        self.assertEqual(triagem, ['indefinido.txt'])

    def test_dp_pendente_fiscal_com_pacote_ainda_nao_executado(self):
        self.assertEqual(self.d['tarefas_areas']['DP']['estado'], 'PRONTO_PARA_ENCAMINHAMENTO')  # DP executa (rodada 03/11)
        self.assertEqual(self.d['tarefas_areas']['FISCAL']['estado'], 'PRONTO_PARA_ENCAMINHAMENTO')
        self.assertEqual(self.d['tarefas_areas']['FINANCEIRO']['documentos'][1]['papel'], 'COPIA_SUPORTE')

    def test_original_alterado_recusa_pacote(self):
        (self.pasta / 'nota.txt').write_text('Alteração fictícia', encoding='utf-8')
        with self.assertRaises(ValueError): self.receber()

    def test_cache_com_hash_trocado_recusa_pacote(self):
        self.x['arquivos'][0]['sha256'] = 'invalido'
        with self.assertRaises(ValueError): self.receber()

    def test_identidade_empresa_divergente_recusa(self):
        self.d['empresa'] = 'OUTRA'
        with self.assertRaises(ValueError): self.receber()

    def test_texto_da_extracao_alterado_recusa(self):
        self.d['extracao_sha256'] = hashlib.sha256(json.dumps(self.x).encode('utf-8')).hexdigest()
        self.x['arquivos'][0]['conteudo']['texto'] = 'Valor alterado fictício'
        with self.assertRaises(ValueError): self.receber()

    def test_tarefa_com_arquivo_fora_inventario_recusa(self):
        self.d['tarefas_areas']['FINANCEIRO']['documentos'].append({'arquivo': 'OUTRO'})
        with self.assertRaises(ValueError): self.receber()

    def test_ocr_duvidoso_nao_e_suporte_confirmado(self):
        with patch.object(fin, 'cadastro', return_value={'cnpjs': [], 'contas': {}, 'cnpjs_outras_empresas': {}}):
            c = fin.Conferencia('FICTICIA', '2026-10', 'SOL-2099-999999')
        c.carregar([{'arquivo': 'recibo.pdf', 'extensao': '.pdf', 'leitura': 'EXTRAIDO_PDF',
                     'conteudo': {'requer_conferencia_ocr': True, 'paginas': [{'texto': 'RECIBO VALOR 100,00'}]}}])
        self.assertEqual(c.documentos, []); self.assertEqual(c.documentos_pendentes_leitura, ['recibo.pdf'])


if __name__ == '__main__': unittest.main()
