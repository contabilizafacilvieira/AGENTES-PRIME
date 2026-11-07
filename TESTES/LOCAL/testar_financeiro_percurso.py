"""Percurso Documentos → Financeiro com a amostra fictícia da rodada (competência 10/2026).

Tudo é gerado em diretório temporário: a empresa fictícia fica em uma RAIZ temporária (patch de RAIZ), nada é criado
em CLIENTES. CNPJs: empresa 90.010.010/0001-09; terceiros ALFA, BETA, GAMA e OUTRA EMPRESA (seção 4 do contrato).
"""
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

EMPRESA, SOL, COMP, PASTA = 'AMOSTRA-COMPLETA-FICTICIA', 'SOL-2099-000001', '2026-10', 'RECEBIDOS/2026-10/LOTE'
CONTA = '001-1234-55555-5'

CADASTRO = """# Cadastro fictício
Razão social: EMPRESA AMOSTRA COMPLETA FICTICIA LTDA
CNPJ: 90.010.010/0001-09

## Contas bancarias
| Banco | Agencia | Conta | Titular (CNPJ) | Situacao |
|---|---|---|---|---|
| 001 | 1234 | 55555-5 | 90.010.010/0001-09 | ATIVA |
"""

EXTRATO = f"""CONTA;DATA;TIPO;HISTORICO;VALOR;SALDO;IDENTIFICADOR
{CONTA};01/10/2026;SALDO_INICIAL;SALDO ANTERIOR;;40.000,00;
{CONTA};03/10/2026;MOVIMENTO;TED RECEBIDA ALFA;10.000,00;50.000,00;
{CONTA};05/10/2026;MOVIMENTO;PIX BETA NF 555;-3.000,00;47.000,00;
{CONTA};15/10/2026;MOVIMENTO;PAGTO ISS 09/2026;-500,00;46.500,00;
{CONTA};25/10/2026;MOVIMENTO;TED RECEBIDA GAMA NF 102;6.000,00;52.500,00;
{CONTA};30/10/2026;MOVIMENTO;PAGTO SALARIOS FP-2026-10;-7.000,00;45.500,00;
{CONTA};31/10/2026;MOVIMENTO;TARIFA BANCARIA;-45,00;45.455,00;
{CONTA};31/10/2026;SALDO_FINAL;SALDO FINAL;;45.455,00;
"""

CAB_RELACAO = 'TIPO;DATA;FAVORECIDO;CNPJ;VALOR;DOCUMENTOS;TITULO;CONTA;OBRIGACAO_CONTABILIZADA'
REL_ALFA = f'RECEBIMENTO;03/10/2026;ALFA CLIENTE FICTICIO LTDA;90.030.030/0001-33;10.000,00;;NF 101;{CONTA};SIM'
REL_BETA = f'PAGAMENTO;05/10/2026;BETA SERVICOS FICTICIOS LTDA;90.040.040/0001-50;3.000,00;NF 555;NF 555;{CONTA};SIM'
REL_GAMA = f'RECEBIMENTO;25/10/2026;GAMA CLIENTE FICTICIO LTDA;90.050.050/0001-76;6.000,00;NF 102;;{CONTA};'
REL_FOLHA = f'PAGAMENTO;30/10/2026;EMPREGADOS FOLHA 10/2026;;7.000,00;FP-2026-10;;{CONTA};'

CAB_POSICAO = 'TIPO;POSICAO;DATA_BASE;CONTRAPARTE;CNPJ;TITULO;VENCIMENTO;VALOR'
POS_ALFA_INI = 'RECEBER;INICIAL;30/09/2026;ALFA CLIENTE FICTICIO LTDA;90.030.030/0001-33;NF 101;15/10/2026;10.000,00'
POS_BETA_INI = 'PAGAR;INICIAL;30/09/2026;BETA SERVICOS FICTICIOS LTDA;90.040.040/0001-50;NF 555;05/10/2026;3.000,00'
POS_RECEBER_FINAL_VAZIA = 'RECEBER;FINAL;31/10/2026;;;SEM TITULOS EM ABERTO;;0,00'
POS_PAGAR_FINAL_VAZIA = 'PAGAR;FINAL;31/10/2026;;;SEM TITULOS EM ABERTO;;0,00'

FOLHA = """RESUMO DA FOLHA DE PAGAMENTO
EMPRESA: EMPRESA AMOSTRA COMPLETA FICTICIA LTDA
CNPJ: 90.010.010/0001-09
COMPETENCIA: 10/2026
NUMERO DO DOCUMENTO: FP-2026-10
RUBRICA;TIPO;VALOR
SALARIO BASE;PROVENTO;8.000,00
INSS SEGURADOS;DESCONTO;700,00
IRRF;DESCONTO;300,00
TOTAL DE PROVENTOS: 8.000,00
TOTAL DE DESCONTOS: 1.000,00
LIQUIDO A PAGAR: 7.000,00
"""
ENCARGOS = """RESUMO DE ENCARGOS DA FOLHA
CNPJ: 90.010.010/0001-09
COMPETENCIA: 10/2026
NUMERO DO DOCUMENTO: EN-2026-10
ENCARGO;BASE;VALOR
INSS EMPRESA;8.000,00;1.600,00
INSS RAT E TERCEIROS;8.000,00;500,00
FGTS;8.000,00;640,00
TOTAL INSS A RECOLHER: 2.800,00
TOTAL FGTS A RECOLHER: 640,00
"""
PROVISOES = """DEMONSTRATIVO DE PROVISOES DE FERIAS E 13 SALARIO
CNPJ: 90.010.010/0001-09
COMPETENCIA: 10/2026
NUMERO DO DOCUMENTO: PR-2026-10
PROVISAO;VALOR DO MES
FERIAS COM 1/3;1.000,00
13 SALARIO;666,67
TOTAL DAS PROVISOES: 1.666,67
ENCARGOS SOBRE PROVISOES: NAO INFORMADOS
"""
SALDOS = """CONTA;DESCRICAO;SALDO;NATUREZA;DATA_BASE;FONTE
1101;BANCO FICTICIO C/C;40.000,00;D;30/09/2026;BALANCETE FICTICIO
1121;CLIENTES;10.000,00;D;30/09/2026;BALANCETE FICTICIO
"""
CONFIRMACAO = """CONFIRMACAO DE SALDO
EMITENTE: BETA SERVICOS FICTICIOS LTDA
CNPJ DO EMITENTE: 90.040.040/0001-50
CLIENTE: EMPRESA AMOSTRA COMPLETA FICTICIA LTDA
CNPJ DO CLIENTE: 90.010.010/0001-09
DATA BASE: 31/10/2026
SALDO EM ABERTO: 0,00
"""
OUTRA_EMPRESA = """RECIBO
EMITENTE: PRESTADOR FICTICIO
TOMADOR: OUTRA EMPRESA FICTICIA LTDA
CNPJ: 90.070.070/0001-09
VALOR: 45,00
DATA: 31/10/2026
"""


def csv(*linhas):
    return '\n'.join(linhas) + '\n'


class Percurso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='prime-percurso-')
        self.root = Path(self.tmp.name)
        (self.root / 'CLIENTES' / EMPRESA).mkdir(parents=True)
        (self.root / 'CLIENTES' / EMPRESA / 'CADASTRO.md').write_text(CADASTRO, encoding='utf-8')
        self.arquivos = {
            'extrato.csv': EXTRATO,
            'relacao.csv': csv(CAB_RELACAO, REL_ALFA, REL_BETA, REL_GAMA, REL_FOLHA),
            'posicao.csv': csv(CAB_POSICAO, POS_ALFA_INI, POS_BETA_INI, POS_RECEBER_FINAL_VAZIA, POS_PAGAR_FINAL_VAZIA),
            'folha.txt': FOLHA, 'encargos.txt': ENCARGOS, 'provisoes.txt': PROVISOES,
            'saldos-abertura.csv': SALDOS, 'confirmacao-beta.txt': CONFIRMACAO,
        }

    def tearDown(self):
        self.tmp.cleanup()

    # ---- montagem do lote em diretório temporário e execução do percurso
    def extracao(self):
        pasta = self.root / 'CLIENTES' / EMPRESA / PASTA
        pasta.mkdir(parents=True, exist_ok=True)
        lista = []
        for nome, texto in self.arquivos.items():
            p = pasta / nome
            p.write_text(texto, encoding='utf-8')
            lista.append({'arquivo': f'{PASTA}/{nome}', 'extensao': p.suffix, 'leitura': 'EXTRAIDO_TEXTO',
                          'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'conteudo': {'texto': texto}})
        return {'arquivos': lista}

    def documentos(self):
        ordem = (f'- Empresa: {EMPRESA}\n- SOL: {SOL}\n- Competência: 2026-10\n'
                 f'- Pasta dos documentos (relativa à pasta da empresa): {PASTA}\n')
        saida = self.root / 'saida-documentos'
        with patch.object(docs, 'RAIZ', self.root), patch.object(docs, 'extrair', return_value=self.extracao()):
            docs.executar(ordem, saida)
        return saida, json.loads((saida / 'documentos-local.json').read_text(encoding='utf-8'))

    def financeiro(self):
        saida, _ = self.documentos()
        with patch.object(fin, 'RAIZ', self.root):
            arquivos, triagem = fin.receber_pacote_local(EMPRESA, COMP, SOL, PASTA, saida / 'documentos-local.json',
                                                         saida / 'extracao-local.json', area='FINANCEIRO', exigir_hash=True)
            c = fin.Conferencia(EMPRESA, COMP, SOL)
            c.carregar(arquivos)
            c.preparar_movimentos()
            self.assertEqual(c.triagem(), [])
            c.corresponder({})
            return c.montar({})

    @staticmethod
    def movimento(r, historico):
        return next(m for m in r['movimentos'] if m['descricao'] == historico)

    @staticmethod
    def titulo(r, tipo, titulo):
        return next(t for t in r['posicoes_titulos'] if t['tipo'] == tipo and t['titulo'] == titulo)

    # ---- Documentos: roteamento de cada tipo novo
    def test_roteamento_dos_tipos_novos(self):
        _, d = self.documentos()
        destino = {i['arquivo'].rsplit('/', 1)[-1]: i['encaminhamento'] for i in d['itens']}
        esperado = {'extrato.csv': ('FINANCEIRO', ['CONCILIACAO']), 'relacao.csv': ('FINANCEIRO', []),
                    'posicao.csv': ('FINANCEIRO', ['CONCILIACAO']), 'folha.txt': ('DP', ['FINANCEIRO']),
                    'encargos.txt': ('DP', []), 'provisoes.txt': ('DP', []),
                    'saldos-abertura.csv': ('CONCILIACAO', []), 'confirmacao-beta.txt': ('CONCILIACAO', [])}
        for nome, (area, copias) in esperado.items():
            self.assertEqual((destino[nome]['area'], destino[nome]['copias_suporte']), (area, copias), nome)
        t = d['tarefas_areas']
        nomes = lambda area: sorted(x['arquivo'].rsplit('/', 1)[-1] for x in t[area]['documentos'])
        self.assertEqual(nomes('FINANCEIRO'), ['extrato.csv', 'folha.txt', 'posicao.csv', 'relacao.csv'])
        self.assertEqual(nomes('DP'), ['encargos.txt', 'folha.txt', 'provisoes.txt'])
        self.assertEqual(nomes('CONCILIACAO'), ['confirmacao-beta.txt', 'extrato.csv', 'posicao.csv', 'saldos-abertura.csv'])
        self.assertNotIn('TRIAGEM', t)
        self.assertEqual(t['DP']['estado'], 'PRONTO_PARA_ENCAMINHAMENTO')
        self.assertEqual({x['situacao'] for x in t['DP']['documentos']}, {'DISPONIVEL'})
        self.assertEqual(d['pendencias'], [])

    def test_documento_de_outra_empresa_nao_e_distribuido(self):
        self.arquivos['recibo-outra.txt'] = OUTRA_EMPRESA
        _, d = self.documentos()
        item = next(i for i in d['itens'] if i['arquivo'].endswith('recibo-outra.txt'))
        e = item['encaminhamento']
        self.assertIsNone(e['area']); self.assertEqual(e['copias_suporte'], [])
        self.assertEqual(e['situacao'], 'DOCUMENTO_NAO_IDENTIFICA_EMPRESA')
        self.assertIn('documento não identifica esta empresa (CNPJs: 90.070.070/0001-09)', e['observacao'])
        self.assertTrue(e['acao_necessaria'])
        triagem = d['tarefas_areas']['TRIAGEM']['documentos']
        self.assertEqual([x['situacao'] for x in triagem], ['DOCUMENTO_NAO_IDENTIFICA_EMPRESA'])
        self.assertTrue(triagem[0]['acao_necessaria'])
        self.assertTrue(any('não identifica esta empresa' in p for p in d['pendencias']))
        for area in ('FINANCEIRO', 'DP', 'FISCAL', 'CONCILIACAO'):
            self.assertFalse(any(x['arquivo'].endswith('recibo-outra.txt') for x in d['tarefas_areas'].get(area, {}).get('documentos', [])))

    def test_financeiro_isola_documento_de_outra_empresa_nao_cadastrada(self):
        with patch.object(fin, 'RAIZ', self.root):
            c = fin.Conferencia(EMPRESA, COMP, SOL)
        c.carregar([{'arquivo': 'recibo-outra.txt', 'extensao': '.txt', 'leitura': 'EXTRAIDO_TEXTO', 'sha256': '1' * 64,
                     'conteudo': {'texto': OUTRA_EMPRESA}}])
        self.assertIn('não identifica esta empresa', c.documentos[0]['bloqueado'])
        self.assertEqual([p['tipo'] for p in c.pendencias if p['tipo'] == 'ISOLAMENTO'], ['ISOLAMENTO'])

    # ---- Financeiro: recebimentos, posição de títulos, folha
    def test_recebimentos_casados_com_a_relacao(self):
        r = self.financeiro()
        rels = {x['id']: x for x in r['relacao']}
        alfa, gama = self.movimento(r, 'TED RECEBIDA ALFA'), self.movimento(r, 'TED RECEBIDA GAMA NF 102')
        for m, cnpj in ((alfa, '90030030000133'), (gama, '90050050000176')):
            self.assertEqual(m['direcao'], 'CREDITO')
            self.assertEqual(len(m['relacao']), 1, m)
            rel = rels[m['relacao'][0]]
            self.assertEqual((rel['tipo'], rel['favorecido_cnpj'], rel['conta']), ('RECEBIMENTO', cnpj, CONTA))
            self.assertIn('conta recebedora = conta do extrato', ' '.join(m['fundamentos']))
        self.assertEqual(rels[alfa['relacao'][0]]['titulo'], 'NF 101')
        self.assertEqual(rels[alfa['relacao'][0]]['obrigacao_contabilizada'], 'SIM')
        self.assertEqual(r['relacionados_sem_movimento'], [])

    def test_recebimento_nao_casa_com_debito(self):
        self.arquivos['relacao.csv'] = csv(CAB_RELACAO, f'RECEBIMENTO;05/10/2026;BETA SERVICOS FICTICIOS LTDA;;3.000,00;NF 555;;{CONTA};')
        r = self.financeiro()
        self.assertEqual(self.movimento(r, 'PIX BETA NF 555')['relacao'], [])
        self.assertEqual([x['tipo'] for x in r['relacionados_sem_movimento'] if x['tipo'] == 'RELACAO'], ['RELACAO'])

    def test_relacao_com_colunas_antigas_continua_aceita(self):
        self.arquivos['relacao.csv'] = csv('DATA_PAGAMENTO;FAVORECIDO;CNPJ_CPF;VALOR;DOCUMENTOS;CONTA_PAGADORA',
                                           f'05/10/2026;BETA SERVICOS FICTICIOS LTDA;90.040.040/0001-50;3.000,00;NF 555;{CONTA}')
        r = self.financeiro()
        beta = self.movimento(r, 'PIX BETA NF 555')
        self.assertEqual(len(beta['relacao']), 1)
        self.assertEqual(r['relacao'][0]['tipo'], 'PAGAMENTO')

    def test_posicao_com_liquidacoes_conferidas(self):
        r = self.financeiro()
        alfa, beta = self.titulo(r, 'RECEBER', 'NF 101'), self.titulo(r, 'PAGAR', 'NF 555')
        for t, mov, v in ((alfa, 'TED RECEBIDA ALFA', '10000.00'), (beta, 'PIX BETA NF 555', '3000.00')):
            self.assertEqual(t['situacao'], 'LIQUIDADO_CONFERIDO', t)
            self.assertEqual(t['liquidacao']['movimento'], self.movimento(r, mov)['id'])
            self.assertEqual((t['valor_inicial'], t['valor_final'], t['liquidacao']['valor']), (v, None, v))
        res = r['posicoes_titulos_resumo']
        self.assertEqual(res['controle'], 'INTERNO'); self.assertIn('INTERNO', res['aviso'])
        self.assertEqual((res['titulos'], res['liquidado_conferido'], res['divergente'], res['sem_liquidacao']), (2, 2, 0, 0))
        self.assertEqual(res['totais'], {'PAGAR_INICIAL': '3000.00', 'PAGAR_FINAL': '0.00',
                                         'RECEBER_INICIAL': '10000.00', 'RECEBER_FINAL': '0.00'})
        self.assertFalse([p for p in r['pendencias'] if 'TITULO' in p['tipo'] or 'POSICAO' in p['tipo']])

    def test_titulo_liquidado_que_permanece_na_final_e_divergente(self):
        self.arquivos['posicao.csv'] = csv(CAB_POSICAO, POS_ALFA_INI, POS_BETA_INI, POS_PAGAR_FINAL_VAZIA,
                                           'RECEBER;FINAL;31/10/2026;ALFA CLIENTE FICTICIO LTDA;90.030.030/0001-33;NF 101;15/10/2026;10.000,00')
        r = self.financeiro()
        alfa = self.titulo(r, 'RECEBER', 'NF 101')
        self.assertEqual(alfa['situacao'], 'DIVERGENTE'); self.assertIn('mantido na posição final', alfa['observacao'])
        self.assertTrue(any(p['tipo'] == 'DIVERGENCIA_TITULO' for p in r['pendencias']))
        self.assertEqual(self.titulo(r, 'PAGAR', 'NF 555')['situacao'], 'LIQUIDADO_CONFERIDO')

    def test_titulo_com_valor_diferente_do_movimento_e_divergente(self):
        self.arquivos['posicao.csv'] = csv(CAB_POSICAO, POS_ALFA_INI.replace('10.000,00', '10.500,00'), POS_BETA_INI,
                                           POS_RECEBER_FINAL_VAZIA, POS_PAGAR_FINAL_VAZIA)
        r = self.financeiro()
        alfa = self.titulo(r, 'RECEBER', 'NF 101')
        self.assertEqual(alfa['situacao'], 'DIVERGENTE'); self.assertIn('10500.00', alfa['observacao'])

    def test_titulo_baixado_sem_movimento_fica_sem_liquidacao(self):
        self.arquivos['posicao.csv'] = csv(CAB_POSICAO, POS_ALFA_INI, POS_BETA_INI,
                                           'PAGAR;INICIAL;30/09/2026;BETA SERVICOS FICTICIOS LTDA;90.040.040/0001-50;NF 556;10/10/2026;1.200,00',
                                           POS_RECEBER_FINAL_VAZIA, POS_PAGAR_FINAL_VAZIA)
        r = self.financeiro()
        t = self.titulo(r, 'PAGAR', 'NF 556')
        self.assertEqual((t['situacao'], t['liquidacao']), ('SEM_LIQUIDACAO', None))
        self.assertTrue(any(p['tipo'] == 'TITULO_SEM_LIQUIDACAO' and 'NF 556' in p['descricao'] for p in r['pendencias']))

    def test_titulo_emitido_no_mes_permanece_em_aberto_sem_pendencia(self):
        self.arquivos['posicao.csv'] = csv(CAB_POSICAO, POS_ALFA_INI, POS_BETA_INI, POS_PAGAR_FINAL_VAZIA,
                                           'RECEBER;FINAL;31/10/2026;ALFA CLIENTE FICTICIO LTDA;90.030.030/0001-33;NF 103;10/11/2026;4.000,00')
        r = self.financeiro()
        t = self.titulo(r, 'RECEBER', 'NF 103')
        self.assertEqual((t['situacao'], t['valor_inicial'], t['valor_final'], t['liquidacao']), ('EM_ABERTO', None, '4000.00', None))
        self.assertFalse([p for p in r['pendencias'] if 'NF 103' in p['descricao']])
        self.assertEqual(r['posicoes_titulos_resumo']['totais']['RECEBER_FINAL'], '4000.00')

    def test_liquidacao_de_titulo_inicial_contabilizado_nao_aponta_nota_ausente(self):
        r = self.financeiro()
        beta = self.movimento(r, 'PIX BETA NF 555')
        self.assertEqual(beta['liquidacao_titulo']['titulo'], 'NF 555')
        self.assertFalse([a for a in beta['ausentes'] if 'NF 555' in a])
        self.assertFalse([p for p in r['pendencias'] if 'NF 555' in p['descricao']])
        self.assertEqual(self.movimento(r, 'TED RECEBIDA ALFA')['liquidacao_titulo']['titulo'], 'NF 101')

    def test_linha_sem_titulo_nao_declara_posicao_vazia(self):
        self.arquivos['posicao.csv'] = csv(CAB_POSICAO, POS_ALFA_INI, POS_BETA_INI, 'RECEBER;FINAL;31/10/2026;;;;;0,00', POS_PAGAR_FINAL_VAZIA)
        r = self.financeiro()
        self.assertTrue(any(p['tipo'] == 'POSICAO_TITULOS_INVALIDA' for p in r['pendencias']))
        self.assertTrue(any(p['tipo'] == 'POSICAO_TITULOS_INCOMPLETA' and 'receber' in p['descricao'] for p in r['pendencias']))
        self.assertEqual(self.titulo(r, 'RECEBER', 'NF 101')['situacao'], 'EM_ABERTO')

    def test_posicao_final_nao_enviada_nao_e_presumida(self):
        self.arquivos['posicao.csv'] = csv(CAB_POSICAO, POS_ALFA_INI, POS_BETA_INI)
        r = self.financeiro()
        self.assertEqual({t['situacao'] for t in r['posicoes_titulos']}, {'EM_ABERTO'})
        self.assertEqual(sum(1 for p in r['pendencias'] if p['tipo'] == 'POSICAO_TITULOS_INCOMPLETA'), 2)

    def test_folha_sustenta_a_natureza_do_pagamento_de_salarios(self):
        r = self.financeiro()
        folha = next(d for d in r['documentos'] if d['tipo'] == 'FOLHA')
        self.assertEqual((folha['valor'], folha['numero'], folha['competencia']), ('7000.00', 'FP-2026-10', '2026-10'))
        m = self.movimento(r, 'PAGTO SALARIOS FP-2026-10')
        self.assertEqual(m['situacao'], 'COM_SUPORTE')
        self.assertEqual([(d['tipo'], d['papel']) for d in m['documentos']], [('FOLHA', 'NATUREZA')])
        self.assertEqual(m['conferencia']['natureza'], 'SIM')
        self.assertNotIn('encargos.txt', [i['arquivo'] for i in r['ignorados']])   # o pacote do Financeiro já não o inclui

    def test_folha_sem_referencia_explicita_e_apenas_candidata(self):
        self.arquivos['relacao.csv'] = csv(CAB_RELACAO, REL_ALFA, REL_BETA, REL_GAMA,
                                           f'PAGAMENTO;30/10/2026;EMPREGADOS FOLHA 10/2026;;7.000,00;;;{CONTA};')
        r = self.financeiro()
        m = self.movimento(r, 'PAGTO SALARIOS FP-2026-10')
        self.assertEqual(m['situacao'], 'SEM_SUPORTE')
        folha = next(d for d in r['documentos'] if d['tipo'] == 'FOLHA')
        self.assertTrue(any(s['movimento'] == m['id'] and s.get('documento') == folha['id'] for s in r['sugestoes']))

    def test_pagamento_sem_suporte_continua_sem_suporte(self):
        r = self.financeiro()
        for historico in ('TARIFA BANCARIA', 'PAGTO ISS 09/2026'):
            m = self.movimento(r, historico)
            self.assertEqual(m['situacao'], 'SEM_SUPORTE', historico)
            self.assertIn('não consta na relação de pagamentos', m['ausentes'])


if __name__ == '__main__':
    unittest.main()
