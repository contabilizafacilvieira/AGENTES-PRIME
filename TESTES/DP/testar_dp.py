"""DP e Contabilidade/DP: somente fontes fictícias geradas em diretório temporário (nada em CLIENTES)."""
import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ/'AGENTES/DP/ferramentas'))
sys.path.insert(0, str(RAIZ/'AGENTES/CONTABILIDADE/DP/ferramentas'))
import analise_dp as dp  # noqa: E402
import propostas_dp as cdp  # noqa: E402
import conferencia_financeira as cf  # noqa: E402

EMP = 'AMOSTRA-DP-FICTICIA'; COMP = '2026-10'; SOL = 'SOL-2026-999901'
CNPJ = '90.010.010/0001-09'; OUTRO = '90.070.070/0001-09'

FOLHA = ('RESUMO DA FOLHA DE PAGAMENTO\nEMPRESA: EMPRESA AMOSTRA COMPLETA FICTICIA LTDA\nCNPJ: 90.010.010/0001-09\n'
         'COMPETENCIA: 10/2026\nNUMERO DO DOCUMENTO: FP-2026-10\nRUBRICA;TIPO;VALOR\nSALARIO BASE;PROVENTO;8.000,00\n'
         'INSS SEGURADOS;DESCONTO;700,00\nIRRF;DESCONTO;300,00\nTOTAL DE PROVENTOS: 8.000,00\nTOTAL DE DESCONTOS: 1.000,00\n'
         'LIQUIDO A PAGAR: 7.000,00\n')
ENCARGOS = ('RESUMO DE ENCARGOS DA FOLHA\nCNPJ: 90.010.010/0001-09\nCOMPETENCIA: 10/2026\nNUMERO DO DOCUMENTO: EN-2026-10\n'
            'ENCARGO;BASE;VALOR\nINSS EMPRESA;8.000,00;1.600,00\nINSS RAT E TERCEIROS;8.000,00;500,00\nFGTS;8.000,00;640,00\n'
            'TOTAL INSS A RECOLHER: 2.800,00\nTOTAL FGTS A RECOLHER: 640,00\n')
PROVISOES = ('DEMONSTRATIVO DE PROVISOES DE FERIAS E 13 SALARIO\nCNPJ: 90.010.010/0001-09\nCOMPETENCIA: 10/2026\n'
             'NUMERO DO DOCUMENTO: PR-2026-10\nPROVISAO;VALOR DO MES\nFERIAS COM 1/3;1.000,00\n13 SALARIO;666,67\n'
             'TOTAL DAS PROVISOES: 1.666,67\nENCARGOS SOBRE PROVISOES: NAO INFORMADOS\n')

CADASTRO = ('# CADASTRO - EMPRESA AMOSTRA COMPLETA FICTICIA LTDA\n\n## CNPJs do cliente\n| CNPJ | Tipo (matriz/filial) | Razão social | Observação |\n'
            '|---|---|---|---|\n| 90.010.010/0001-09 | matriz | EMPRESA AMOSTRA COMPLETA FICTICIA LTDA | fictícia |\n\n'
            '## Contas bancárias\n| Banco | Agência | Conta | Titular (CNPJ) | Conta contábil | Situação |\n|---|---|---|---|---|---|\n'
            '| 001 | 1234 | 55555-5 | 90.010.010/0001-09 | 1101 | ATIVA |\n')
PLANO = ('# PLANO DE CONTAS - FICTICIO\n\n## Contas utilizadas\n| Código reduzido | Descrição | Grupo | Tipo |\n|---|---|---|---|\n'
         '| 1 | ATIVO | ATIVO | SINTETICA |\n| 1101 | BANCO FICTICIO C/C | ATIVO | ANALITICA |\n'
         '| 2111 | SALARIOS A PAGAR | PASSIVO | ANALITICA |\n| 2112 | INSS A RECOLHER | PASSIVO | ANALITICA |\n'
         '| 2113 | FGTS A RECOLHER | PASSIVO | ANALITICA |\n| 2114 | IRRF A RECOLHER | PASSIVO | ANALITICA |\n'
         '| 2121 | PROVISAO DE FERIAS | PASSIVO | ANALITICA |\n| 2122 | PROVISAO DE 13 SALARIO | PASSIVO | ANALITICA |\n'
         '| 41 | DESPESAS COM PESSOAL | DESPESA | SINTETICA |\n| 4101 | SALARIOS | DESPESA | ANALITICA |\n'
         '| 4102 | INSS PATRONAL | DESPESA | ANALITICA |\n| 4103 | FGTS | DESPESA | ANALITICA |\n'
         '| 4104 | FERIAS | DESPESA | ANALITICA |\n| 4105 | 13 SALARIO | DESPESA | ANALITICA |\n'
         '| 3101 | RECEITA DE SERVICOS | RECEITA | ANALITICA |\n')
FONTE = 'Definição fictícia do Supervisor para teste'
REFS = {'FOLHA_PROVENTOS': ('4101', '2111'), 'RETENCAO_INSS': ('2111', '2112'), 'RETENCAO_IRRF': ('2111', '2114'),
        'ENCARGO_INSS_EMPRESA': ('4102', '2112'), 'ENCARGO_FGTS': ('4103', '2113'), 'PROVISAO_FERIAS': ('4104', '2121'),
        'PROVISAO_13': ('4105', '2122')}
ESPERADO = {'FOLHA_PROVENTOS': ('4101', '2111', '8000.00'), 'RETENCAO_INSS': ('2111', '2112', '700.00'),
            'RETENCAO_IRRF': ('2111', '2114', '300.00'), 'ENCARGO_INSS_EMPRESA': ('4102', '2112', '2100.00'),
            'ENCARGO_FGTS': ('4103', '2113', '640.00'), 'PROVISAO_FERIAS': ('4104', '2121', '1000.00'),
            'PROVISAO_13': ('4105', '2122', '666.67')}


def arquivo(t, nome, **extra):
    a = {'arquivo': 'RECEBIDOS/LOTE-DP/' + nome, 'sha256': hashlib.sha256(t.encode()).hexdigest(), 'leitura': 'EXTRAIDO_TEXTO',
         'extensao': '.' + nome.rsplit('.', 1)[-1], 'conteudo': {'texto': t}}
    a.update(extra); return a


def completo():
    return [arquivo(FOLHA, 'folha.txt'), arquivo(ENCARGOS, 'encargos.txt'), arquivo(PROVISOES, 'provisoes.csv')]


def analisar(arquivos=None):
    return dp.analisar(EMP, COMP, SOL, completo() if arquivos is None else arquivos, [CNPJ])


def doc(r, nome): return next(d for d in r['documentos'] if d['arquivo'].endswith(nome))


class AnaliseDP(unittest.TestCase):
    def test_cenario_completo(self):
        r = analisar()
        self.assertEqual((r['contrato'], r['agente'], r['modo'], r['empresa'], r['sol'], r['competencia']),
                         ('DP_LOCAL_V1', 'DP', 'SIMULACAO', EMP, SOL, COMP))
        self.assertEqual(r['resumo'], {'documentos': 3, 'aptos': 3, 'fatos': 8, 'pendencias': 0})
        fatos = {f['evento']: f for f in r['fatos']}
        self.assertEqual({k: f['valor'] for k, f in fatos.items()},
                         {'FOLHA_PROVENTOS': '8000.00', 'RETENCAO_INSS': '700.00', 'RETENCAO_IRRF': '300.00',
                          'LIQUIDO_A_PAGAR': '7000.00', 'ENCARGO_INSS_EMPRESA': '2100.00', 'ENCARGO_FGTS': '640.00',
                          'PROVISAO_FERIAS': '1000.00', 'PROVISAO_13': '666.67'})
        self.assertEqual(fatos['LIQUIDO_A_PAGAR']['natureza'], 'OBRIGACAO_A_PAGAR')
        self.assertEqual(fatos['FOLHA_PROVENTOS']['natureza'], 'RECONHECIMENTO')
        f = doc(r, 'folha.txt')
        self.assertEqual((f['tipo'], f['cnpj'], f['numero'], f['competencia']), ('RESUMO_FOLHA', '90010010000109', 'FP-2026-10', COMP))
        self.assertEqual(f['totais'], {'TOTAL DE PROVENTOS': '8000.00', 'TOTAL DE DESCONTOS': '1000.00', 'LIQUIDO A PAGAR': '7000.00'})
        self.assertEqual(doc(r, 'provisoes.csv')['tipo'], 'PROVISOES')
        self.assertTrue(any('Encargos sobre provisões não informados' in l for l in r['limites']))
        # ids estáveis entre execuções
        self.assertEqual([x['id'] for x in r['fatos']], [x['id'] for x in analisar()['fatos']])

    def inapto(self, r, nome, trecho):
        d = doc(r, nome); self.assertFalse(d['elegivel_contabilidade'])
        self.assertTrue(any(trecho in p for p in d['pendencias']), d['pendencias'])
        self.assertFalse([f for f in r['fatos'] if f['documento'] == d['id']])

    def test_totais_incoerentes(self):
        for alterado, trecho in ((FOLHA.replace('TOTAL DE PROVENTOS: 8.000,00', 'TOTAL DE PROVENTOS: 8.000,01'), 'Soma dos proventos'),
                                 (FOLHA.replace('TOTAL DE DESCONTOS: 1.000,00', 'TOTAL DE DESCONTOS: 999,99'), 'Soma dos descontos'),
                                 (FOLHA.replace('LIQUIDO A PAGAR: 7.000,00', 'LIQUIDO A PAGAR: 7.000,10'), 'LIQUIDO A PAGAR')):
            self.inapto(analisar([arquivo(alterado, 'folha.txt')]), 'folha.txt', trecho)
        r = analisar([arquivo(FOLHA, 'folha.txt'), arquivo(ENCARGOS.replace('TOTAL INSS A RECOLHER: 2.800,00', 'TOTAL INSS A RECOLHER: 2.100,00'), 'encargos.txt')])
        self.inapto(r, 'encargos.txt', 'TOTAL INSS A RECOLHER')
        self.assertTrue(doc(r, 'folha.txt')['elegivel_contabilidade'])
        r = analisar([arquivo(FOLHA, 'folha.txt'), arquivo(ENCARGOS.replace('TOTAL FGTS A RECOLHER: 640,00', 'TOTAL FGTS A RECOLHER: 640,01'), 'encargos.txt')])
        self.inapto(r, 'encargos.txt', 'TOTAL FGTS')
        self.inapto(analisar([arquivo(PROVISOES.replace('1.666,67', '1.666,66'), 'prov.txt')]), 'prov.txt', 'Soma das provisões')

    def test_rubrica_de_desconto_desconhecida(self):
        t = FOLHA.replace('IRRF;DESCONTO;300,00', 'IRRF;DESCONTO;300,00\nVALE TRANSPORTE;DESCONTO;100,00').replace(
            'TOTAL DE DESCONTOS: 1.000,00', 'TOTAL DE DESCONTOS: 1.100,00').replace('LIQUIDO A PAGAR: 7.000,00', 'LIQUIDO A PAGAR: 6.900,00')
        r = analisar([arquivo(t, 'folha.txt'), arquivo(ENCARGOS, 'encargos.txt')])
        self.inapto(r, 'folha.txt', 'VALE TRANSPORTE')
        self.inapto(r, 'encargos.txt', 'folha da mesma competência com pendência')

    def test_competencia_diferente(self):
        self.inapto(analisar([arquivo(FOLHA.replace('10/2026', '09/2026'), 'folha.txt')]), 'folha.txt', 'Competência do documento distinta')

    def test_cnpj_de_outra_empresa(self):
        self.inapto(analisar([arquivo(PROVISOES.replace(CNPJ, OUTRO), 'prov.txt')]), 'prov.txt', 'não pertence ao cadastro')

    def test_duplicado_identico_nenhum_aproveitado(self):
        r = analisar([arquivo(FOLHA, 'folha.txt'), arquivo(FOLHA, 'folha-copia.txt')])
        self.inapto(r, 'folha.txt', 'Cópia idêntica'); self.inapto(r, 'folha-copia.txt', 'Cópia idêntica')
        self.assertNotEqual(r['documentos'][0]['id'], r['documentos'][1]['id'])

    def test_mesmo_numero_conteudo_diferente(self):
        r = analisar([arquivo(PROVISOES, 'a.txt'), arquivo(PROVISOES.replace('ENCARGOS SOBRE PROVISOES: NAO INFORMADOS', 'ENCARGOS SOBRE PROVISOES: NAO INFORMADO'), 'b.txt')])
        self.inapto(r, 'a.txt', 'Mesmo NUMERO DO DOCUMENTO'); self.inapto(r, 'b.txt', 'Mesmo NUMERO DO DOCUMENTO')

    def test_encargos_sem_folha(self):
        self.inapto(analisar([arquivo(ENCARGOS, 'encargos.txt')]), 'encargos.txt', 'Resumo da folha da mesma competência não recebido')

    def test_leitura_pendente_ou_protegido(self):
        for a in (arquivo(FOLHA, 'f.pdf', leitura='PDF_PROTEGIDO'), arquivo(FOLHA, 'f.pdf', leitura='DOCUMENTO_REQUER_OCR'),
                  arquivo(FOLHA, 'f.pdf', conteudo={'texto': FOLHA, 'requer_conferencia_ocr': True}),
                  arquivo(FOLHA, 'f.pdf', leitura='EXTRAIDO_PDF', conteudo={'paginas': [{'texto': FOLHA}], 'leitura_incompleta': True})):
            r = analisar([a]); self.inapto(r, 'f.pdf', 'Leitura pendente')
            self.assertEqual(doc(r, 'f.pdf')['tipo'], 'NAO_RECONHECIDO')
        r = analisar([arquivo(FOLHA, 'f.pdf', leitura='EXTRAIDO_PDF', conteudo={'paginas': [{'texto': FOLHA}]})])
        self.assertTrue(doc(r, 'f.pdf')['elegivel_contabilidade'])

    def test_layout_nao_reconhecido(self):
        for t in ('HOLERITE\nFUNCIONARIO: FULANO\nLIQUIDO: 1.000,00\n', FOLHA.replace('RUBRICA;TIPO;VALOR', 'RUBRICA;VALOR'),
                  FOLHA + 'OBSERVACAO LIVRE QUALQUER\n', FOLHA + ENCARGOS):
            r = analisar([arquivo(t, 'x.txt')]); self.assertFalse(doc(r, 'x.txt')['elegivel_contabilidade']); self.assertFalse(r['fatos'])
        self.assertEqual(doc(analisar([arquivo('HOLERITE\n', 'x.txt')]), 'x.txt')['tipo'], 'NAO_RECONHECIDO')

    def test_pacote_vazio_gera_pendencia(self):
        r = analisar([]); self.assertEqual(r['resumo']['documentos'], 0); self.assertEqual(len(r['pendencias']), 1)


def aprovada(chave, **dados):
    return dict(dados, situacao='APROVADA', origem=dados.get('fonte') or 'teste unitário', versao=1,
                confirmacao={'frase': f'VALIDADO REGRA DP {EMP} {chave}', 'em': '2026-11-05T10:00:00-03:00', 'por': 'Supervisor Contábil'})


class BaseEmpresa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='prime-dp-'); self.root = Path(self.tmp.name)
        self.base = self.root/'CLIENTES'/EMP; (self.base/'PLANO-DE-CONTAS').mkdir(parents=True)
        (self.base/'CADASTRO.md').write_text(CADASTRO, encoding='utf-8')
        (self.base/'PLANO-DE-CONTAS/PLANO-DE-CONTAS.md').write_text(PLANO, encoding='utf-8')
        # referências APROVADAS pelo Supervisor (frase exata) e política de data aprovada: o que torna a proposta aplicável
        self.regras = {'contrato': 'REFERENCIAS_DP_V1', 'empresa': EMP, 'cnpj': CNPJ, 'competencia_desde': '2026-10',
                       'data_lancamento': aprovada('DATA_LANCAMENTO', politica='ULTIMO_DIA_COMPETENCIA'),
                       'referencias': {k: aprovada(k, debito=d, credito=c, fonte=FONTE) for k, (d, c) in REFS.items()}}

    def tearDown(self): self.tmp.cleanup()

    def salvar(self, regras=None):
        (self.base/'REGRAS-DP.json').write_text(regras if isinstance(regras, str) else json.dumps(regras or self.regras), encoding='utf-8')

    def gerar(self, r=None, salvar=True):
        if salvar: self.salvar()
        with patch.object(cdp, 'RAIZ', self.root): return cdp.gerar(EMP, COMP, SOL, r or analisar())

    def lanc(self, res, ev): return next(l for l in res['lancamentos'] if l['evento'] == ev)


class ContabilidadeDP(BaseEmpresa):
    def test_cenario_completo_sete_lancamentos(self):
        res = self.gerar()
        self.assertEqual(res['contrato'], 'CONTABILIDADE_DP_V1'); self.assertEqual(len(res['lancamentos']), 7)
        for l in res['lancamentos']:
            d, c, v = ESPERADO[l['evento']]
            self.assertEqual((l['debito']['codigo'], l['credito']['codigo'], l['valor'], l['status']), (d, c, v, 'PROPOSTO_PARA_CONFERENCIA'))
            self.assertEqual(l['id'], f"DP-{l['documento']}-{l['evento']}")
            self.assertEqual(l['regra']['fonte'], FONTE); self.assertEqual(l['regra']['governanca']['situacao'], 'APROVADA')
            self.assertEqual(l['pendencias'], [])
            self.assertEqual((l['competencia'], l['data']), ('2026-10', '2026-10-31'))      # competência ≠ data do lançamento
            self.assertTrue(l['identidade'].startswith(f"DP:{l['evento']}:2026-10:"))
            self.assertNotIn('/', l['historico'].replace('1/3', '').replace('10/2026', ''))   # sem caminho de arquivo
            self.assertIs(l['aprovado'], False); self.assertIs(l['escriturado'], False)
        self.assertEqual(res['resumo'], {'propostos': 7, 'incompletos': 0, 'sem_data': 0, 'valor_propostos': '13406.67'})
        self.assertEqual(self.lanc(res, 'PROVISAO_13')['historico'], 'PROVISAO DE 13 SALARIO COMPETENCIA 10/2026 REF. PR-2026-10')
        self.assertNotIn('LIQUIDO_A_PAGAR', [l['evento'] for l in res['lancamentos']])
        self.assertEqual(self.lanc(res, 'RETENCAO_INSS')['natureza'], 'RETENCAO')

    def incompleto(self, evento, trecho, **ref):
        self.regras['referencias'][evento].update(ref)
        l = self.lanc(self.gerar(), evento)
        self.assertEqual(l['status'], 'INCOMPLETO'); self.assertTrue(any(trecho in p for p in l['pendencias']), l['pendencias'])
        self.assertIs(l['aprovado'], False)

    def test_conta_inexistente(self): self.incompleto('FOLHA_PROVENTOS', 'inexistente', debito='4999')
    def test_conta_sintetica(self): self.incompleto('ENCARGO_FGTS', 'não é analítica', debito='41')
    def test_grupo_incompativel(self):
        self.incompleto('PROVISAO_13', 'incompatível', debito='3101')
        self.tearDown(); self.setUp(); self.incompleto('RETENCAO_IRRF', 'incompatível', debito='4101')

    def test_conta_bancaria_como_contrapartida(self):
        # 1101 é ATIVO (já incompatível); marca também conta PASSIVO como bancária no cadastro para isolar a regra.
        (self.base/'CADASTRO.md').write_text(CADASTRO.replace('| 1101 | ATIVA |', '| 2114 | ATIVA |'), encoding='utf-8')
        l = self.lanc(self.gerar(), 'RETENCAO_IRRF'); self.assertEqual(l['status'], 'INCOMPLETO')
        self.assertTrue(any('conta bancária' in p for p in l['pendencias']))
        self.tearDown(); self.setUp(); self.incompleto('RETENCAO_INSS', 'incompatível', credito='1101')

    def test_referencia_sem_fonte(self): self.incompleto('PROVISAO_FERIAS', 'sem fonte', fonte='  ')

    def test_regra_sem_situacao_ou_proposta_nao_aplicada(self):
        """Referência histórica sem situação (ou PROPOSTA) não vira regra aprovada em silêncio."""
        self.regras['referencias']['FOLHA_PROVENTOS'] = {'debito': '4101', 'credito': '2111', 'fonte': FONTE}
        self.regras['referencias']['ENCARGO_FGTS']['situacao'] = 'PROPOSTA'
        res = self.gerar()
        for ev in ('FOLHA_PROVENTOS', 'ENCARGO_FGTS'):
            l = self.lanc(res, ev)
            self.assertEqual(l['status'], 'INCOMPLETO', ev)
            self.assertTrue(any('VALIDADO REGRA DP' in p for p in l['pendencias']), l['pendencias'])
        self.assertEqual(self.lanc(res, 'RETENCAO_INSS')['status'], 'PROPOSTO_PARA_CONFERENCIA')

    def test_aprovada_sem_confirmacao_valida(self):
        self.regras['referencias']['PROVISAO_13']['confirmacao']['frase'] = 'aprovo'
        self.assertEqual(self.lanc(self.gerar(), 'PROVISAO_13')['status'], 'INCOMPLETO')

    def test_regra_de_teste_so_vale_em_empresa_ficticia(self):
        for k in self.regras['referencias']:
            self.regras['referencias'][k].update(situacao='TESTE_FICTICIO'); self.regras['referencias'][k].pop('confirmacao')
        self.regras['data_lancamento'].update(situacao='TESTE_FICTICIO')
        self.assertEqual(self.gerar()['resumo']['propostos'], 0)            # sem marcador = empresa real
        (self.base/'AMOSTRA-FICTICIA.json').write_text('{"ficticia": true}', encoding='utf-8')
        self.assertEqual(self.gerar()['resumo']['propostos'], 7)

    def test_sem_politica_de_data_pede_definicao(self):
        """Data do lançamento não é presumida: sem política expressa, a proposta fica incompleta com a pergunta ao Supervisor."""
        del self.regras['data_lancamento']
        res = self.gerar()
        self.assertEqual((res['resumo']['propostos'], res['resumo']['sem_data']), (0, 7))
        l = self.lanc(res, 'FOLHA_PROVENTOS')
        self.assertIsNone(l['data']); self.assertEqual(l['competencia'], '2026-10')
        self.assertTrue(any('Data do lançamento (DP) não definida' in p for p in l['pendencias']), l['pendencias'])
        self.regras['data_lancamento'] = aprovada('DATA_LANCAMENTO', politica='DATA_EMISSAO_DOCUMENTO')
        self.assertEqual(self.gerar()['resumo']['propostos'], 0)          # DP não tem data documentada: não se aplica

    def test_regras_ausente_todas_incompletas(self):
        res = self.gerar(salvar=False)
        self.assertEqual(res['resumo']['propostos'], 0); self.assertEqual(res['resumo']['incompletos'], 7)
        self.assertTrue(all(any('não definidas pelo Supervisor' in p for p in l['pendencias']) for l in res['lancamentos']))

    def test_regras_invalidas_erro(self):
        for invalida in ('{ nao e json', {**self.regras, 'contrato': 'OUTRO'}, {**self.regras, 'empresa': 'OUTRA'},
                         {**self.regras, 'cnpj': OUTRO}, {**self.regras, 'referencias': []}):
            self.salvar(invalida)
            with patch.object(cdp, 'RAIZ', self.root), self.assertRaises(ValueError):
                cdp.gerar(EMP, COMP, SOL, analisar())

    def test_regras_invalidas_cli_codigo_nao_zero(self):
        self.salvar('{ nao e json'); entrada = self.root/'dp.json'; entrada.write_text(json.dumps(analisar()), encoding='utf-8')
        err = io.StringIO()
        with patch.object(cdp, 'RAIZ', self.root), contextlib.redirect_stderr(err):
            codigo = cdp.main(['--empresa', EMP, '--competencia', COMP, '--sol', SOL, '--dp', str(entrada), '--saida', str(self.root/'out')])
        self.assertNotEqual(codigo, 0); self.assertIn('REGRAS-DP.json inválido', err.getvalue())
        self.assertFalse((self.root/'out/resultado.json').exists())

    def test_resultado_de_outra_sol(self):
        outro = analisar(); outro['sol'] = 'SOL-2026-000000'
        with self.assertRaises(ValueError): self.gerar(outro)
        for k, v in (('empresa', 'OUTRA'), ('competencia', '2026-09')):
            r = copy.deepcopy(analisar()); r[k] = v
            with self.assertRaises(ValueError): self.gerar(r)

    def test_documentos_pendentes_nao_geram_lancamento(self):
        r = analisar([arquivo(ENCARGOS, 'encargos.txt'), arquivo(PROVISOES, 'prov.txt')])
        res = self.gerar(r)
        self.assertEqual(sorted(l['evento'] for l in res['lancamentos']), ['PROVISAO_13', 'PROVISAO_FERIAS'])
        self.assertEqual(len(res['documentos_nao_aproveitados']), 1)

    def test_fato_forjado_sem_documento_elegivel(self):
        r = analisar(); r['fatos'][0]['sha256'] = '0' * 64
        l = next(l for l in self.gerar(r)['lancamentos'] if l['origem']['fato'] == r['fatos'][0]['id'])
        self.assertEqual(l['status'], 'INCOMPLETO')

    def test_cli_completo_grava_resultado(self):
        self.salvar(); entrada = self.root/'dp.json'; entrada.write_text(json.dumps(analisar()), encoding='utf-8')
        with patch.object(cdp, 'RAIZ', self.root):
            codigo = cdp.main(['--empresa', EMP, '--competencia', COMP, '--sol', SOL, '--dp', str(entrada), '--saida', str(self.root/'out')])
        self.assertEqual(codigo, 0)
        res = json.loads((self.root/'out/resultado.json').read_text(encoding='utf-8'))
        self.assertEqual(res['resumo']['propostos'], 7)
        self.assertEqual(res['origem_dp_sha256'], hashlib.sha256(entrada.read_bytes()).hexdigest())


class CLIAnaliseDP(BaseEmpresa):
    """Pacote completo de Documentos (manifesto + extração com hash) recebido pela área DP."""

    def montar(self, tarefas=True):
        pasta = 'RECEBIDOS/LOTE-DP'; (self.base/pasta).mkdir(parents=True)
        arquivos = completo()
        for a, t in zip(arquivos, (FOLHA, ENCARGOS, PROVISOES)): (self.base/a['arquivo']).write_bytes(t.encode())
        ext = json.dumps({'arquivos': arquivos}).encode(); (self.root/'extracao-local.json').write_bytes(ext)
        man = {'contrato': 'DOCUMENTOS_LOCAL_V1', 'empresa': EMP, 'competencia': COMP, 'sol': SOL, 'pasta': pasta,
               'extracao_sha256': hashlib.sha256(ext).hexdigest(), 'itens': [{'arquivo': a['arquivo'], 'sha256': a['sha256']} for a in arquivos]}
        if tarefas: man['tarefas_areas'] = {'DP': {'documentos': [{'arquivo': a['arquivo'], 'papel': 'PRINCIPAL'} for a in arquivos]}}
        (self.root/'documentos-local.json').write_text(json.dumps(man), encoding='utf-8')
        return ['--empresa', EMP, '--competencia', COMP, '--sol', SOL, '--pasta', pasta,
                '--documentos-local', str(self.root/'documentos-local.json'), '--extracao-local', str(self.root/'extracao-local.json'),
                '--saida', str(self.root/'dp')]

    def rodar(self, args):
        err = io.StringIO()
        with patch.object(cf, 'RAIZ', self.root), contextlib.redirect_stderr(err): return dp.main(args), err.getvalue()

    def test_pacote_completo(self):
        codigo, _ = self.rodar(self.montar()); self.assertEqual(codigo, 0)
        r = json.loads((self.root/'dp/resultado.json').read_text(encoding='utf-8'))
        self.assertEqual(r['resumo'], {'documentos': 3, 'aptos': 3, 'fatos': 8, 'pendencias': 0})
        self.salvar(); self.assertEqual(self.gerar(r)['resumo']['propostos'], 7)

    def test_pacote_sem_registro_da_area_recusado(self):
        codigo, err = self.rodar(self.montar(tarefas=False)); self.assertEqual(codigo, 1); self.assertIn('Pacote da área', err)

    def test_original_alterado_recusado(self):
        args = self.montar(); (self.base/'RECEBIDOS/LOTE-DP/folha.txt').write_text(FOLHA + ' ', encoding='utf-8')
        codigo, err = self.rodar(args); self.assertEqual(codigo, 1); self.assertFalse((self.root/'dp/resultado.json').exists())


if __name__ == '__main__': unittest.main(verbosity=2)
