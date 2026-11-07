"""Encerramento reversível da revisão parcial, sem aprovação contábil."""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('coord_revisao_teste', RAIZ / 'COORDENADOR-GERAL/ferramentas/coordenador.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class Revisao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='prime-revisao-'); self.root = Path(self.tmp.name)
        self.s = {'fluxo': 'FINANCEIRO_BANCOS', 'estado': 'AGUARDANDO_SUPERVISOR', 'eventos': [],
                  'motivos': ['Documento ainda pendente'], 'bancos': [{'resumo': {'propostos': 1}}]}
        self.r = {'solicitacoes': {'SOL-2099-999999': self.s}}

    def tearDown(self): self.tmp.cleanup()

    def agir(self, acao='encerrar'):
        with patch.object(c, 'ler_registro', return_value=self.r), patch.object(c, 'REGISTRO', self.root / 'registro.json'), \
             patch.object(c, 'ORDEM_ATIVA', self.root / 'ordem.json'), patch.object(c, 'saida', side_effect=lambda d, *a: d):
            return c.revisar_piloto('SOL-2099-999999', acao, 'Revisão fictícia do piloto')

    def test_encerrar_preserva_pendencias_e_nao_aprova(self):
        motivos, bancos = copy.deepcopy(self.s['motivos']), copy.deepcopy(self.s['bancos'])
        r = self.agir()
        self.assertEqual(r['estado'], 'ENCERRADA'); self.assertEqual(self.s['motivos'], motivos)
        self.assertEqual(self.s['bancos'], bancos); self.assertNotIn('escriturados', self.s)
        self.assertFalse(self.s['revisoes_piloto'][0]['escrituracao_aprovada'])

    def test_reabrir_nao_reprocessa(self):
        self.agir(); r = self.agir('reabrir')
        self.assertEqual(r['estado'], 'AGUARDANDO_SUPERVISOR'); self.assertFalse(self.s['revisao_parcial_encerrada'])
        self.assertEqual(len(self.s['bancos']), 1)

    def test_nao_encerra_execucao_ativa(self):
        self.s['estado'] = 'FINANCEIRO_EM_ANDAMENTO'
        self.assertNotEqual(self.agir().get('resultado'), 'REVISAO_PILOTO_REGISTRADA')
        self.assertEqual(self.s['estado'], 'FINANCEIRO_EM_ANDAMENTO')

    def test_ordem_ativa_impede_acao(self):
        (self.root / 'ordem.json').write_text('{}')
        self.assertNotEqual(self.agir().get('resultado'), 'REVISAO_PILOTO_REGISTRADA')


if __name__ == '__main__': unittest.main()
