"""Transição após triagem local; somente pastas e documentos fictícios temporários."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('coord_triagem_teste', RAIZ / 'COORDENADOR-GERAL/ferramentas/coordenador.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class Encaminhamento(unittest.TestCase):
    def encerrar(self, area='FINANCEIRO', autorizado=True, hash_correto=True, utilizavel=True, fluxo='DOCUMENTOS'):
        with tempfile.TemporaryDirectory(prefix='prime-auto-') as tmp:
            root = Path(tmp); base = root / 'CLIENTES/FICTICIA'; alvo = base / 'RECEBIDOS/TESTE'; alvo.mkdir(parents=True)
            (alvo / 'arquivo.txt').write_text('Documento ficticio', encoding='utf-8')
            sha = hashlib.sha256((alvo / 'arquivo.txt').read_bytes()).hexdigest()
            ordem = root / 'ordem.json'; ordem.write_text('{}')
            registro = {'solicitacoes': {'SOL-2099-999999': {'empresa': 'FICTICIA', 'competencia': '2026-10',
                        'pasta': 'RECEBIDOS/TESTE', 'estado': 'DOCUMENTOS_EM_ANDAMENTO', 'fluxo': fluxo, 'eventos': []}}}
            d = {'contrato': 'DOCUMENTOS_LOCAL_V1', 'empresa': 'FICTICIA', 'sol': 'SOL-2099-999999',
                 'competencia': '2026-10', 'pasta': 'RECEBIDOS/TESTE', 'pendencias': [], 'limitacoes': [],
                 'itens': [{'arquivo': 'RECEBIDOS/TESTE/arquivo.txt', 'sha256': sha if hash_correto else 'invalido',
                            'conteudo_utilizavel': utilizavel, 'encaminhamento': {'area': area}}]}
            resultado = root / 'docs.json'; resultado.write_text(json.dumps(d), encoding='utf-8')
            with patch.object(c, 'CLIENTES', root / 'CLIENTES'), patch.object(c, 'ORDEM_ATIVA', ordem), \
                 patch.object(c, 'REGISTRO', root / 'registro.json'), patch.object(c, 'ler_registro', return_value=registro), \
                 patch.object(c, 'ler_ordem', return_value={'sol': 'SOL-2099-999999', 'empresa': 'FICTICIA'}), \
                 patch.object(c, 'empresas_cadastradas', return_value={'FICTICIA': {'texto': 'EMPRESA FICTICIA'}}), \
                 patch.object(c, 'financeiro_permitido', return_value=autorizado), patch.object(c, 'saida', side_effect=lambda d: d):
                r = c.encerrar_local('SOL-2099-999999', str(resultado))
            return r, registro['solicitacoes']['SOL-2099-999999']

    def test_documentos_transita_financeiro_preservando_origem(self):
        r, s = self.encerrar()
        self.assertEqual(r['estado'], 'FINANCEIRO_EM_ANDAMENTO')
        self.assertEqual(s['fluxo_origem'], 'DOCUMENTOS'); self.assertEqual(s['fluxo'], 'FINANCEIRO_BANCOS')

    def test_sem_autorizacao_nao_executa(self):
        r, s = self.encerrar(autorizado=False)
        self.assertEqual(r['estado'], 'AGUARDANDO_SUPERVISOR'); self.assertEqual(s['fluxo'], 'DOCUMENTOS')
        self.assertIn('não está autorizado', ' '.join(s['motivos']))

    def test_hash_divergente_nao_executa(self):
        r, s = self.encerrar(hash_correto=False)
        self.assertEqual(r['estado'], 'AGUARDANDO_SUPERVISOR'); self.assertEqual(s['fluxo'], 'DOCUMENTOS')

    def test_dp_nao_inventa_financeiro(self):
        r, s = self.encerrar(area='DP')
        self.assertEqual(r['estado'], 'AGUARDANDO_SUPERVISOR'); self.assertEqual(s['fluxo'], 'DOCUMENTOS')

    def test_arquivo_nao_lido_nao_aciona(self):
        r, _ = self.encerrar(utilizavel=False)
        self.assertEqual(r['estado'], 'AGUARDANDO_SUPERVISOR')

    def test_fluxo_explicito_preservado(self):
        r, s = self.encerrar(fluxo='FINANCEIRO_BANCOS')
        self.assertEqual(r['estado'], 'FINANCEIRO_EM_ANDAMENTO'); self.assertNotIn('fluxo_origem', s)


if __name__ == '__main__': unittest.main()
