"""Testes da Conciliação (CONCILIACAO_V1) — somente dados fictícios, em diretório temporário.

Empresa fictícia criada em RAIZ temporária (patch de RAIZ); nada é criado em CLIENTES, nenhuma API é acessada.
Execução: .venv/Scripts/python.exe -I TESTES/CONCILIACAO/testar_conciliacao.py
"""
import copy
import hashlib
import io
import json
import random
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'AGENTES' / 'CONCILIACAO' / 'ferramentas'))
import conciliacao as conc  # noqa: E402

cf = conc.cf
EMP, SOL, COMP = 'AMOSTRA-COMPLETA-FICTICIA', 'SOL-2026-900001', '2026-10'
CNPJ_EMP = '90.010.010/0001-09'
ALFA, BETA, GAMA = '90030030000133', '90040040000150', '90050050000176'
PASTA = 'RECEBIDOS/' + SOL
CONTA_BANCO = '001-1234-555555'

CADASTRO = f"""# CADASTRO - {EMP}
## Identificação
- Razão social: EMPRESA AMOSTRA COMPLETA FICTICIA LTDA
- CNPJ (matriz): {CNPJ_EMP}

## Contas bancárias
| Banco | Agência | Conta | Titular (CNPJ) | Conta contábil | Situação |
|---|---|---|---|---|---|
| 001 | 1234 | 55555-5 | {CNPJ_EMP} | 1101 | ATIVA |
"""
CONTAS = [('1101', 'BANCO FICTICIO C/C', 'ATIVO'), ('1121', 'CLIENTES', 'ATIVO'), ('2101', 'FORNECEDORES', 'PASSIVO'),
          ('2111', 'SALARIOS A PAGAR', 'PASSIVO'), ('2112', 'INSS A RECOLHER', 'PASSIVO'), ('2113', 'FGTS A RECOLHER', 'PASSIVO'),
          ('2114', 'IRRF A RECOLHER', 'PASSIVO'), ('2121', 'PROVISAO DE FERIAS', 'PASSIVO'), ('2122', 'PROVISAO DE 13 SALARIO', 'PASSIVO'),
          ('2131', 'ISS A RECOLHER', 'PASSIVO'), ('2132', 'PIS A RECOLHER', 'PASSIVO'), ('2133', 'COFINS A RECOLHER', 'PASSIVO'),
          ('3101', 'RECEITA DE SERVICOS', 'RECEITA'), ('3191', '(-) ISS SOBRE SERVICOS', 'RECEITA'), ('3192', '(-) PIS', 'RECEITA'),
          ('3193', '(-) COFINS', 'RECEITA'), ('4101', 'SALARIOS', 'DESPESA'), ('4102', 'INSS PATRONAL', 'DESPESA'),
          ('4103', 'FGTS', 'DESPESA'), ('4104', 'FERIAS', 'DESPESA'), ('4105', '13 SALARIO', 'DESPESA'),
          ('4201', 'SERVICOS DE TERCEIROS', 'DESPESA'), ('4202', 'TARIFAS BANCARIAS', 'DESPESA')]
PLANO = ('# PLANO DE CONTAS\n\n## Contas utilizadas\n| Código reduzido | Classificação | Descrição | Grupo | Tipo |\n|---|---|---|---|---|\n'
         + ''.join(f'| {c} | 1.{c} | {d} | {g} | ANALITICA |\n' for c, d, g in CONTAS)
         + '| 1000 | 1 | ATIVO | ATIVO | SINTETICA |\n')

ABERTURA = ('CONTA;DESCRICAO;SALDO;NATUREZA;DATA_BASE;FONTE\n'
            '1101;BANCO FICTICIO C/C;40.000,00;D;30/09/2026;BALANCETE 09/2026\n'
            '1121;CLIENTES;10.000,00;D;30/09/2026;BALANCETE 09/2026\n'
            '2101;FORNECEDORES;3.000,00;C;30/09/2026;BALANCETE 09/2026\n'
            '2131;ISS A RECOLHER;500,00;C;30/09/2026;BALANCETE 09/2026\n'
            + ''.join(f'{c};X;0,00;C;30/09/2026;BALANCETE 09/2026\n' for c in ('2111', '2112', '2113', '2114', '2121', '2122', '2132', '2133')))
POSICAO = ('TIPO;POSICAO;DATA_BASE;CONTRAPARTE;CNPJ;TITULO;VENCIMENTO;VALOR\n'
           'RECEBER;INICIAL;30/09/2026;ALFA;90.030.030/0001-33;NF 101;10/10/2026;10.000,00\n'
           'PAGAR;INICIAL;30/09/2026;BETA;90.040.040/0001-50;NF 555;05/10/2026;3.000,00\n'
           'RECEBER;FINAL;31/10/2026;ALFA;90.030.030/0001-33;NF 103;28/11/2026;4.000,00\n'
           'PAGAR;FINAL;31/10/2026;;;SEM TITULOS EM ABERTO;;0,00\n')


def confirmacao(emitente, cnpj, saldo, data='31/10/2026', cliente=CNPJ_EMP):
    return (f'CONFIRMACAO DE SALDO\nEMITENTE: {emitente}\nCNPJ DO EMITENTE: {cnpj}\n'
            f'CLIENTE: EMPRESA AMOSTRA COMPLETA FICTICIA LTDA\nCNPJ DO CLIENTE: {cliente}\nDATA BASE: {data}\nSALDO EM ABERTO: {saldo}\n')


EXTRATO = ('CONTA;DATA;TIPO;HISTORICO;VALOR;SALDO;IDENTIFICADOR\n001-1234-55555-5;30/09/2026;SALDO_INICIAL;;;40.000,00;\n'
           '001-1234-55555-5;31/10/2026;SALDO_FINAL;;;45.455,00;\n')


def mov(mid, data, valor, direcao, descricao, documentos=()):
    return {'id': mid, 'empresa': EMP, 'competencia': COMP, 'conta': CONTA_BANCO, 'data': data, 'valor': valor, 'direcao': direcao,
            'descricao': descricao, 'identificadores': {}, 'tipo_banco': None, 'origens': ['extrato.csv'],
            'documentos': list(documentos), 'situacao': 'COM_SUPORTE'}


def conta(c):
    return {'codigo': c, 'descricao': dict((x, d) for x, d, _ in CONTAS)[c]}


def lan_banco(n, movimento, data, valor, tipo, deb, cre, documentos=()):
    return {'id': f'LAN-{n:03d}', 'status': 'PROPOSTO', 'data': data, 'valor': valor, 'debito': conta(deb) if deb else None,
            'credito': conta(cre) if cre else None, 'historico': 'FICTICIO', 'tipo': tipo, 'origem': 'regra RB-00X',
            'movimentos': [movimento], 'conta_bancaria': CONTA_BANCO, 'documentos': list(documentos), 'pendencias': [],
            'natureza_registro': 'PROPOSTA_SIMULACAO', 'revisao_de': []}


def resultados():
    """Resultados sintéticos dos agentes no formato real, cenário A (seção 4 + adendo)."""
    movimentos = [
        mov('MOV-ALFA101', '2026-10-03', '10000.00', 'CREDITO', 'TED RECEBIDA ALFA'),
        mov('MOV-BETA555', '2026-10-05', '3000.00', 'DEBITO', 'PIX BETA NF 555',
            [{'id': 'DOC-C1', 'arquivo': 'comprovante_beta.txt', 'tipo': 'COMPROVANTE', 'papel': 'LIQUIDACAO', 'numero': None, 'valor': '3000.00'}]),
        mov('MOV-ISS0926', '2026-10-15', '500.00', 'DEBITO', 'PAGTO ISS 09/2026'),
        mov('MOV-GAMA102', '2026-10-25', '6000.00', 'CREDITO', 'TED RECEBIDA GAMA NF 102'),
        mov('MOV-SALARIO', '2026-10-30', '7000.00', 'DEBITO', 'PAGTO SALARIOS FP-2026-10',
            [{'id': 'DOC-F1', 'arquivo': 'folha.txt', 'tipo': 'FOLHA', 'papel': 'NATUREZA', 'numero': 'FP-2026-10', 'valor': '7000.00'}]),
        mov('MOV-TARIFA', '2026-10-31', '45.00', 'DEBITO', 'TARIFA BANCARIA'),
    ]
    fin = {'agente': 'FINANCEIRO', 'versao': '1.1', 'sol': SOL, 'empresa': EMP, 'competencia': COMP, 'modo': 'SIMULACAO',
           'bloqueio_lote': [], 'movimentos': movimentos, 'documentos': [], 'relacao': [],
           'verificacao_extratos': [{'conta': CONTA_BANCO, 'cobertura_competencia': 'COMPLETA', 'situacao': 'CONCLUIDA',
                                     'extratos': [{'arquivo': 'extrato.csv', 'conta': CONTA_BANCO, 'inicio': '2026-09-30', 'fim': '2026-10-31',
                                                   'saldo_inicial': '40000.00', 'saldo_final': '45455.00', 'soma_movimentos': '5455.00',
                                                   'aritmetica': 'CONSISTENTE'}]}],
           'posicoes_titulos': [
               {'tipo': 'RECEBER', 'titulo': 'NF 101', 'contraparte': 'ALFA', 'cnpj': ALFA, 'valor_inicial': '10000.00', 'valor_final': None,
                'liquidacao': {'movimento': 'MOV-ALFA101', 'valor': '10000.00', 'data': '2026-10-03'}, 'situacao': 'LIQUIDADO_CONFERIDO', 'observacao': ''},
               {'tipo': 'PAGAR', 'titulo': 'NF 555', 'contraparte': 'BETA', 'cnpj': BETA, 'valor_inicial': '3000.00', 'valor_final': None,
                'liquidacao': {'movimento': 'MOV-BETA555', 'valor': '3000.00', 'data': '2026-10-05'}, 'situacao': 'LIQUIDADO_CONFERIDO', 'observacao': ''},
               {'tipo': 'RECEBER', 'titulo': 'NF 103', 'contraparte': 'ALFA', 'cnpj': ALFA, 'valor_inicial': None, 'valor_final': '4000.00',
                'liquidacao': None, 'situacao': 'EM_ABERTO', 'observacao': ''}],
           'pendencias': [], 'resumo': {}}
    bancos = {'agente': 'CONTABILIDADE/BANCOS', 'versao': '1.1', 'sol': SOL, 'empresa': EMP, 'competencia': COMP, 'modo': 'SIMULACAO',
              'lancamentos': [
                  lan_banco(1, 'MOV-ALFA101', '2026-10-03', '10000.00', 'RECEBIMENTO', '1101', '1121'),
                  lan_banco(2, 'MOV-BETA555', '2026-10-05', '3000.00', 'LIQUIDACAO_OBRIGACAO', '2101', '1101',
                            [{'arquivo': 'comprovante_beta.txt', 'tipo': 'COMPROVANTE', 'papel': 'LIQUIDACAO', 'numero': None}]),
                  lan_banco(3, 'MOV-ISS0926', '2026-10-15', '500.00', 'LIQUIDACAO_OBRIGACAO', '2131', '1101'),
                  lan_banco(4, 'MOV-GAMA102', '2026-10-25', '6000.00', 'RECEBIMENTO', '1101', '1121'),
                  lan_banco(5, 'MOV-SALARIO', '2026-10-30', '7000.00', 'LIQUIDACAO_OBRIGACAO', '2111', '1101',
                            [{'arquivo': 'folha.txt', 'tipo': 'FOLHA', 'papel': 'NATUREZA', 'numero': 'FP-2026-10'}]),
                  lan_banco(6, 'MOV-TARIFA', '2026-10-31', '45.00', 'DESPESA', '4202', '1101')],
              'nao_escriturados': [], 'pendencias': [], 'resumo': {}}

    def fdoc(i, tipo, valor, **k):
        return dict({'id': f'FIS-{i}', 'arquivo': f'{PASTA}/fiscal_{i}.txt', 'sha256': hashlib.sha256(i.encode()).hexdigest(), 'tipo': tipo,
                     'pendencias': [], 'competencia': COMP, 'valor': valor, 'elegivel_contabilidade': True, 'papel_empresa': 'PRESTADOR_EMITENTE'}, **k)
    fis_docs = [fdoc('NF102', 'NFSE', '6000.00', numero='102', emitente_cnpj='90010010000109', destinatario_cnpj=GAMA),
                fdoc('NF103', 'NFSE', '4000.00', numero='103', emitente_cnpj='90010010000109', destinatario_cnpj=ALFA),
                fdoc('ISS', 'APURACAO_TRIBUTO', '200.00', tributo='ISS', titular_cnpj='90010010000109', papel_empresa='CONTRIBUINTE'),
                fdoc('PIS', 'APURACAO_TRIBUTO', '65.00', tributo='PIS', titular_cnpj='90010010000109', papel_empresa='CONTRIBUINTE'),
                fdoc('COFINS', 'APURACAO_TRIBUTO', '300.00', tributo='COFINS', titular_cnpj='90010010000109', papel_empresa='CONTRIBUINTE')]
    fiscal = {'contrato': 'FISCAL_LOCAL_V1', 'agente': 'FISCAL', 'empresa': EMP, 'competencia': COMP, 'sol': SOL, 'modo': 'SIMULACAO',
              'documentos': fis_docs, 'pendencias': [], 'resumo': {}}

    def flan(d, evento, deb, cre):
        return {'id': 'PF-' + d['id'], 'documento': d['id'], 'arquivo': d['arquivo'], 'sha256': d['sha256'], 'status': 'PROPOSTO_PARA_CONFERENCIA',
                'evento': evento, 'competencia': COMP, 'data': '2026-10-31', 'valor': d['valor'], 'debito': conta(deb), 'credito': conta(cre), 'historico': 'X',
                'origem_regra': 'REGRAS-FISCAIS.json', 'pendencias': [], 'aprovado': False, 'escriturado': False}
    cfis = {'contrato': 'CONTABILIDADE_FISCAL_V1', 'agente': 'CONTABILIDADE/FISCAL', 'empresa': EMP, 'competencia': COMP, 'sol': SOL,
            'modo': 'SIMULACAO', 'lancamentos': [flan(fis_docs[0], 'RECEITA_SERVICOS', '1121', '3101'), flan(fis_docs[1], 'RECEITA_SERVICOS', '1121', '3101'),
                                                 flan(fis_docs[2], 'ISS', '3191', '2131'), flan(fis_docs[3], 'PIS', '3192', '2132'),
                                                 flan(fis_docs[4], 'COFINS', '3193', '2133')], 'resumo': {}}

    def ddoc(i, tipo, numero):
        return {'id': f'DPD-{i}', 'arquivo': f'{PASTA}/{i.lower()}.txt', 'sha256': hashlib.sha256(i.encode()).hexdigest(), 'tipo': tipo,
                'competencia': COMP, 'cnpj': '90010010000109', 'numero': numero, 'rubricas': [], 'totais': {}, 'pendencias': [],
                'elegivel_contabilidade': True}
    dp_docs = [ddoc('FOLHA', 'RESUMO_FOLHA', 'FP-2026-10'), ddoc('ENC', 'ENCARGOS_FOLHA', 'EN-2026-10'), ddoc('PROV', 'PROVISOES', 'PR-2026-10')]
    eventos = [(0, 'FOLHA_PROVENTOS', '8000.00', '4101', '2111'), (0, 'RETENCAO_INSS', '700.00', '2111', '2112'),
               (0, 'RETENCAO_IRRF', '300.00', '2111', '2114'), (0, 'LIQUIDO_A_PAGAR', '7000.00', None, None),
               (1, 'ENCARGO_INSS_EMPRESA', '2100.00', '4102', '2112'), (1, 'ENCARGO_FGTS', '640.00', '4103', '2113'),
               (2, 'PROVISAO_FERIAS', '1000.00', '4104', '2121'), (2, 'PROVISAO_13', '666.67', '4105', '2122')]
    fatos, dlans = [], []
    for i, ev, v, deb, cre in eventos:
        d = dp_docs[i]
        f = {'id': d['id'] + '-' + ev, 'evento': ev, 'natureza': 'X', 'valor': v, 'competencia': COMP, 'documento': d['id'],
             'arquivo': d['arquivo'], 'sha256': d['sha256'], 'origem': {'rotulo': ev, 'tipo_documento': d['tipo'], 'numero': d['numero']}}
        fatos.append(f)
        if deb:
            dlans.append({'id': f"DP-{d['id']}-{ev}", 'evento': ev, 'natureza': 'X', 'status': 'PROPOSTO_PARA_CONFERENCIA', 'competencia': COMP,
                          'data': '2026-10-31',
                          'valor': v, 'debito': conta(deb), 'credito': conta(cre), 'documento': d['id'], 'arquivo': d['arquivo'],
                          'sha256': d['sha256'], 'origem': {'fato': f['id']}, 'regra': {'fonte': 'REGRAS-DP.json'}, 'pendencias': [],
                          'aprovado': False, 'escriturado': False})
    dp = {'contrato': 'DP_LOCAL_V1', 'agente': 'DP', 'empresa': EMP, 'competencia': COMP, 'sol': SOL, 'modo': 'SIMULACAO',
          'documentos': dp_docs, 'fatos': fatos, 'pendencias': [], 'resumo': {}}
    cdp = {'contrato': 'CONTABILIDADE_DP_V1', 'agente': 'CONTABILIDADE/DP', 'empresa': EMP, 'competencia': COMP, 'sol': SOL,
           'modo': 'SIMULACAO', 'lancamentos': dlans, 'resumo': {}}
    return {'FINANCEIRO': fin, 'BANCOS': bancos, 'DP': dp, 'CONTABILIDADE_DP': cdp, 'FISCAL': fiscal, 'CONTABILIDADE_FISCAL': cfis}


def documentos_conciliacao():
    return {'saldos_abertura.csv': ABERTURA, 'posicao_titulos.csv': POSICAO, 'extrato.csv': EXTRATO,
            'confirmacao_alfa.txt': confirmacao('ALFA CLIENTE FICTICIO LTDA', '90.030.030/0001-33', '4.000,00'),
            'confirmacao_beta.txt': confirmacao('BETA SERVICOS FICTICIOS LTDA', '90.040.040/0001-50', '0,00')}


def exigencias(**sobre):
    """Exigências da Conciliação APROVADAS pelo Supervisor (confirmação com a frase exata) para a empresa fictícia de teste."""
    def regra(chave, exigencia, **k):
        return dict({'exigencia': exigencia, 'situacao': 'APROVADA', 'origem': 'teste unitário', 'versao': 1,
                     'confirmacao': {'frase': f'VALIDADO REGRA CONCILIACAO {EMP} {chave}', 'em': '2026-11-05T10:00:00-03:00',
                                     'por': 'Supervisor Contábil'}}, **k)
    ex = {c: regra(c, 'EXIGIDA') for c in ('POSICAO_TITULOS_PAGAR', 'POSICAO_TITULOS_RECEBER', 'CONFIRMACAO_TERCEIROS')}
    for c, v in sobre.items():
        if v is None:
            ex.pop(c, None)
        else:
            ex[c] = regra(c, **v) if isinstance(v, dict) and 'exigencia' in v and 'situacao' not in v else v
    return {'contrato': 'EXIGENCIAS_CONCILIACAO_V1', 'empresa': EMP, 'exigencias': ex}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='prime-conciliacao-'))
        self.raiz = self.tmp / 'raiz'
        base = self.raiz / 'CLIENTES' / EMP
        (base / 'PLANO-DE-CONTAS').mkdir(parents=True)
        (base / 'CADASTRO.md').write_text(CADASTRO, encoding='utf-8')
        (base / 'PLANO-DE-CONTAS' / 'PLANO-DE-CONTAS.md').write_text(PLANO, encoding='utf-8')
        self.regras(exigencias())
        self.patches = [patch.object(cf, 'RAIZ', self.raiz), patch.object(conc, 'RAIZ', self.raiz)]
        for p in self.patches:
            p.start()
        self.n = 0

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def regras(self, dados):
        arq = self.raiz / 'CLIENTES' / EMP / 'REGRAS-CONCILIACAO.json'
        if dados is None:
            arq.unlink(missing_ok=True)
        else:
            arq.write_text(json.dumps(dados, ensure_ascii=False), encoding='utf-8')

    def montar(self, res=None, docs=None, etapas=None, area_conciliacao=True, pendencias=(), adulterar=None):
        """Grava resultados/pacote em pasta nova e devolve entradas.json (dict)."""
        self.n += 1
        dir_exec = self.tmp / f'exec{self.n}'
        dir_exec.mkdir()
        res = resultados() if res is None else res
        docs = documentos_conciliacao() if docs is None else docs
        pasta = self.raiz / 'CLIENTES' / EMP / PASTA
        if pasta.exists():
            shutil.rmtree(pasta)
        pasta.mkdir(parents=True)
        itens, arquivos = [], []
        for nome, texto in sorted(docs.items()):
            dados = texto.encode('utf-8')
            (pasta / nome).write_bytes(dados)
            sha = hashlib.sha256(dados).hexdigest()
            itens.append({'arquivo': f'{PASTA}/{nome}', 'sha256': sha})
            arquivos.append({'arquivo': f'{PASTA}/{nome}', 'sha256': sha, 'extensao': Path(nome).suffix, 'leitura': 'EXTRAIDO_TEXTO',
                             'marcacoes': [], 'conteudo': {'codificacao': 'utf-8', 'truncado': False, 'texto': texto}})
        extracao = json.dumps({'arquivos': arquivos}, ensure_ascii=False, indent=2).encode('utf-8')
        (dir_exec / 'extracao-local.json').write_bytes(extracao)
        tarefas = {'FINANCEIRO': {'area': 'FINANCEIRO', 'documentos': []}}
        if area_conciliacao:
            tarefas['CONCILIACAO'] = {'area': 'CONCILIACAO', 'documentos': [
                {'id': f"TD-{i['sha256'][:12].upper()}-CONCILIACAO", 'arquivo': i['arquivo'], 'sha256': i['sha256'],
                 'papel': 'PRINCIPAL', 'situacao': 'DISPONIVEL', 'leitura': 'EXTRAIDO_TEXTO'} for i in itens]}
        manifesto = {'contrato': 'DOCUMENTOS_LOCAL_V1', 'empresa': EMP, 'sol': SOL, 'competencia': COMP, 'pasta': PASTA,
                     'itens': itens, 'tarefas_areas': tarefas, 'extracao_sha256': hashlib.sha256(extracao).hexdigest()}
        (dir_exec / 'documentos-local.json').write_text(json.dumps(manifesto, ensure_ascii=False), encoding='utf-8')
        etapas_e = {}
        for et, r in res.items():
            caminho = dir_exec / et / 'resultado.json'
            caminho.parent.mkdir()
            caminho.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
            etapas_e[et] = {'situacao': 'CONCLUIDA', 'resultado': str(caminho), 'sha256_registrado': hashlib.sha256(caminho.read_bytes()).hexdigest()}
        for et, info in (etapas or {}).items():
            etapas_e[et] = info
        if adulterar:
            adulterar(etapas_e)
        return {'contrato': 'ENTRADAS_CONCILIACAO_V1', 'empresa': EMP, 'sol': SOL, 'competencia': COMP, 'etapas': etapas_e,
                'pacote': {'pasta': PASTA, 'documentos_local': str(dir_exec / 'documentos-local.json'),
                           'extracao_local': str(dir_exec / 'extracao-local.json')},
                'cadastro': str(self.raiz / 'CLIENTES' / EMP / 'CADASTRO.md'),
                'plano': str(self.raiz / 'CLIENTES' / EMP / 'PLANO-DE-CONTAS' / 'PLANO-DE-CONTAS.md'),
                'regras_conciliacao': str(self.raiz / 'CLIENTES' / EMP / 'REGRAS-CONCILIACAO.json'),
                'pendencias_anteriores': list(pendencias)}

    def rodar(self, **k):
        return conc.conciliar(self.montar(**k))

    @staticmethod
    def ver(r, vid):
        achados = [v for v in r['verificacoes'] if v['id'] == vid]
        assert len(achados) == 1, (vid, [v['id'] for v in r['verificacoes']])
        return achados[0]

    @staticmethod
    def saldos(r):
        return {s['conta']: (s['saldo_final'], s['situacao']) for s in r['saldos_contas']}


class TestCenarioA(Base):
    def test_cenario_a_integral(self):
        r = self.rodar()
        problemas = [(v['id'], v['resultado'], v['justificativa']) for v in r['verificacoes'] if v['resultado'] not in ('CONFERIDO', 'NAO_APLICAVEL')]
        self.assertEqual(problemas, [])
        for v in r['verificacoes']:
            if v['resultado'] == 'NAO_APLICAVEL':
                self.assertTrue(v['justificativa'])
            for campo in ('id', 'grupo', 'titulo', 'item', 'contas', 'lancamentos', 'fontes', 'valores', 'resultado',
                          'justificativa', 'area_responsavel', 'acao'):
                self.assertIn(campo, v)
            self.assertEqual(set(v['valores']), {'esperado', 'encontrado', 'diferenca'})
        self.assertFalse(r['alcance']['parcial'], r['alcance'])
        self.assertEqual(set(r['alcance']['executadas']), set('ABCDE'))
        self.assertEqual((r['contrato'], r['agente'], r['modo']), ('CONCILIACAO_V1', 'CONCILIACAO', 'SIMULACAO'))
        self.assertEqual(r['resumo']['total'], len(r['verificacoes']))
        self.assertEqual(r['resumo']['conferido'] + r['resumo']['nao_aplicavel'], r['resumo']['total'])
        esperados = {'1101': '45455.00', '1121': '4000.00', '2101': '0.00', '2111': '0.00', '2112': '-2800.00', '2113': '-640.00',
                     '2114': '-300.00', '2121': '-1000.00', '2122': '-666.67', '2131': '-200.00', '2132': '-65.00', '2133': '-300.00'}
        s = self.saldos(r)
        for c, v in esperados.items():
            self.assertEqual(s[c], (v, 'CALCULADO'), c)
        # verificações essenciais presentes e conferidas
        for vid in ('CONC-C-EXTRATO-001-1234-555555', 'CONC-C-SALDO-1101', 'CONC-C-ABERTURA-1101', 'CONC-C-POSICAO-RECEBER',
                    'CONC-C-POSICAO-PAGAR', 'CONC-D-PAGTO-SALARIOS', 'CONC-D-SALDO-2112', 'CONC-D-SALDO-2131',
                    'CONC-D-TRIB-PROVISAO-ISS', 'CONC-D-LIQ-MOV-ISS0926', 'CONC-E-CONF-90030030000133', 'CONC-E-CONF-90040040000150',
                    'CONC-A-HASH-BANCOS', 'CONC-A-PACOTE', 'CONC-B-LAN-BANCOS-MOV-TARIFA-DESPESA'):
            self.assertEqual(self.ver(r, vid)['resultado'], 'CONFERIDO', vid)
        self.assertEqual(self.ver(r, 'CONC-C-SALDO-1101')['valores']['encontrado'], '45455.00')
        self.assertEqual(len([v for v in r['verificacoes'] if v['grupo'] == 'B']), 6 + 5 + 7)
        self.assertEqual(set(r['versoes_entradas']), set(conc.ETAPAS) | {'PACOTE', 'EXTRACAO'})
        self.assertEqual(sum(r['resumo']['conferidas_por_evidencia'].values()), r['resumo']['conferido'])
        self.assertEqual((r['resumo']['nao_determinado'], r['perguntas_supervisor']), (0, []))

    def test_cli_grava_resultado(self):
        entradas = self.montar()
        arq = self.tmp / 'entradas.json'
        arq.write_text(json.dumps(entradas), encoding='utf-8')
        saida = self.tmp / 'saida'
        with redirect_stdout(io.StringIO()):
            codigo = conc.main(['--empresa', EMP, '--sol', SOL, '--competencia', COMP, '--entradas', str(arq), '--saida', str(saida)])
        self.assertEqual(codigo, 0)
        r = json.loads((saida / 'resultado.json').read_text(encoding='utf-8'))
        self.assertEqual(r['contrato'], 'CONCILIACAO_V1')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(conc.main(['--empresa', EMP, '--sol', 'SOL-2026-000000', '--competencia', COMP, '--entradas', str(arq),
                                        '--saida', str(saida)]), 2)


class TestDivergenciasEPendencias(Base):
    def test_pagamento_salarios_divergente(self):
        res = resultados()
        m = next(x for x in res['FINANCEIRO']['movimentos'] if x['id'] == 'MOV-SALARIO')
        m['valor'] = '7100.00'
        ex = res['FINANCEIRO']['verificacao_extratos'][0]['extratos'][0]
        ex['saldo_final'], ex['soma_movimentos'] = '45355.00', '5355.00'
        next(l for l in res['BANCOS']['lancamentos'] if l['movimentos'] == ['MOV-SALARIO'])['valor'] = '7100.00'
        r = self.rodar(res=res)
        v = self.ver(r, 'CONC-D-PAGTO-SALARIOS')
        self.assertEqual(v['resultado'], 'DIVERGENTE')
        self.assertEqual((v['valores']['esperado'], v['valores']['encontrado'], v['valores']['diferenca']), ('7000.00', '7100.00', '100.00'))
        self.assertEqual(self.ver(r, 'CONC-D-SALDO-2111')['resultado'], 'DIVERGENTE')   # passivo com saldo devedor

    def test_lancamento_incompleto(self):
        res = resultados()
        l = next(l for l in res['BANCOS']['lancamentos'] if l['movimentos'] == ['MOV-TARIFA'])
        l.update(status='INCOMPLETO', debito=None, tipo=None, pendencias=['Sem regra aprovada'])
        r = self.rodar(res=res)
        self.assertEqual(self.ver(r, 'CONC-B-LAN-BANCOS-MOV-TARIFA-SEM-TIPO')['resultado'], 'PENDENTE')
        self.assertEqual(self.ver(r, 'CONC-C-SALDO-1101')['resultado'], 'PENDENTE')
        self.assertEqual(self.ver(r, 'CONC-C-MOV-MOV-TARIFA')['resultado'], 'PENDENTE')
        self.assertEqual(self.saldos(r)['1101'][1], 'PENDENTE')

    def test_sem_saldo_de_abertura(self):
        docs = documentos_conciliacao()
        del docs['saldos_abertura.csv']
        r = self.rodar(docs=docs)
        for vid in ('CONC-C-SALDO-1101', 'CONC-C-ABERTURA-1101', 'CONC-C-POSICAO-RECEBER', 'CONC-D-SALDO-2112'):
            self.assertEqual(self.ver(r, vid)['resultado'], 'PENDENTE', vid)
        self.assertIsNone(dict((s['conta'], s) for s in r['saldos_contas'])['1101']['saldo_final'])
        self.assertTrue(r['alcance']['parcial'])
        self.assertIn('SALDOS_DE_ABERTURA', [x['item'] for x in r['alcance']['nao_executadas']])

    def test_area_conciliacao_sem_documentos(self):
        r = self.rodar(area_conciliacao=False)
        self.assertEqual(self.ver(r, 'CONC-A-PACOTE')['resultado'], 'CONFERIDO')
        self.assertEqual(self.ver(r, 'CONC-C-SALDO-1101')['resultado'], 'PENDENTE')
        self.assertTrue(r['alcance']['parcial'])

    def test_confirmacao_ausente(self):
        docs = documentos_conciliacao()
        del docs['confirmacao_alfa.txt']
        r = self.rodar(docs=docs)
        v = self.ver(r, 'CONC-E-CONF-90030030000133')
        self.assertEqual(v['resultado'], 'PENDENTE')
        self.assertEqual(v['valores']['esperado'], '4000.00')
        # a concordância interna continua conferida, mas marcada INTERNA
        self.assertEqual(self.ver(r, 'CONC-C-POSICAO-RECEBER')['resultado'], 'CONFERIDO')

    def test_confirmacao_divergente(self):
        docs = documentos_conciliacao()
        docs['confirmacao_beta.txt'] = confirmacao('BETA SERVICOS FICTICIOS LTDA', '90.040.040/0001-50', '3.000,00')
        r = self.rodar(docs=docs)
        v = self.ver(r, 'CONC-E-CONF-90040040000150')
        self.assertEqual((v['resultado'], v['valores']['diferenca']), ('DIVERGENTE', '3000.00'))

    def test_posicao_final_nao_declarada(self):
        docs = documentos_conciliacao()
        docs['posicao_titulos.csv'] = '\n'.join(l for l in POSICAO.splitlines() if 'SEM TITULOS' not in l) + '\n'
        r = self.rodar(docs=docs)
        self.assertEqual(self.ver(r, 'CONC-C-POSICAO-PAGAR')['resultado'], 'PENDENTE')
        self.assertEqual(self.ver(r, 'CONC-E-CONF-90040040000150')['resultado'], 'PENDENTE')

    def test_concordancia_interna_nao_e_externa(self):
        r = self.rodar()
        v = self.ver(r, 'CONC-C-POSICAO-RECEBER')
        self.assertEqual(v['resultado'], 'CONFERIDO')
        self.assertEqual(v['evidencia'], 'CONTROLE_INTERNO')
        self.assertNotIn('DOCUMENTO_EXTERNO', v['evidencias'])
        self.assertFalse(any(f['natureza'] == 'EXTERNA' for f in v['fontes']))
        self.assertIn('não é confirmação independente', v['justificativa'])
        self.assertEqual(self.ver(r, 'CONC-E-CONF-90030030000133')['evidencia'], 'DOCUMENTO_EXTERNO')
        self.assertEqual(self.ver(r, 'CONC-C-SALDO-1101')['evidencia'], 'DOCUMENTO_EXTERNO')
        # verificação mista: categorias presentes ficam explícitas (sem pontuação)
        self.assertIn('CONTROLE_INTERNO', self.ver(r, 'CONC-E-CONF-90030030000133')['evidencias'])
        # integridade de resultado é consistência entre resultados do próprio sistema
        self.assertEqual(self.ver(r, 'CONC-A-HASH-BANCOS')['evidencia'], 'CONSISTENCIA_SISTEMA')

    def test_confirmacao_ausente_sem_regra_nao_determinada(self):
        """Sem regra da empresa: a exigência da confirmação não é presumida (nem PENDENTE nem NÃO APLICÁVEL) — pergunta ao Supervisor."""
        self.regras(exigencias(CONFIRMACAO_TERCEIROS=None))
        docs = documentos_conciliacao()
        del docs['confirmacao_alfa.txt']
        r = self.rodar(docs=docs)
        v = self.ver(r, 'CONC-E-CONF-90030030000133')
        self.assertEqual(v['resultado'], 'NAO_DETERMINADO')
        self.assertTrue(r['alcance']['parcial'])
        self.assertIn('CONC-E-CONF-90030030000133', r['alcance']['indeterminadas'])
        self.assertTrue(any('confirmação' in p['pergunta'] for p in r['perguntas_supervisor']))

    def test_confirmacao_dispensada_com_justificativa(self):
        self.regras(exigencias(CONFIRMACAO_TERCEIROS={'exigencia': 'DISPENSADA', 'justificativa': 'Clientes pessoa física (teste).'}))
        docs = documentos_conciliacao()
        del docs['confirmacao_alfa.txt']
        r = self.rodar(docs=docs)
        v = self.ver(r, 'CONC-E-CONF-90030030000133')
        self.assertEqual(v['resultado'], 'NAO_APLICAVEL')
        self.assertIn('Clientes pessoa física', v['justificativa'])
        self.assertTrue(any(f['tipo'] == 'REGRA_EMPRESA' for f in v['fontes']))

    def test_dispensa_sem_justificativa_nao_aceita(self):
        self.regras(exigencias(CONFIRMACAO_TERCEIROS={'exigencia': 'DISPENSADA'}))
        docs = documentos_conciliacao()
        del docs['confirmacao_alfa.txt']
        self.assertEqual(self.ver(self.rodar(docs=docs), 'CONC-E-CONF-90030030000133')['resultado'], 'NAO_DETERMINADO')

    def test_sem_posicoes_nunca_vira_nao_aplicavel_por_falta_de_documento(self):
        docs = documentos_conciliacao()
        del docs['posicao_titulos.csv'], docs['confirmacao_alfa.txt'], docs['confirmacao_beta.txt']
        res = resultados()
        res['FINANCEIRO']['posicoes_titulos'] = []
        # 1) exigidas pela regra → PENDENTE
        r = self.rodar(docs=docs, res=res)
        self.assertEqual(self.ver(r, 'CONC-C-POSICAO-PAGAR')['resultado'], 'PENDENTE')
        self.assertEqual(self.ver(r, 'CONC-C-POSICAO-RECEBER')['resultado'], 'PENDENTE')
        self.assertEqual(self.ver(r, 'CONC-E-CONFIRMACOES')['resultado'], 'PENDENTE')
        # 2) sem regra → NÃO DETERMINADO com pergunta, sem fechamento integral
        self.regras(None)
        r = self.rodar(docs=docs, res=res)
        for vid in ('CONC-C-POSICAO-PAGAR', 'CONC-C-POSICAO-RECEBER', 'CONC-E-CONFIRMACOES'):
            self.assertEqual(self.ver(r, vid)['resultado'], 'NAO_DETERMINADO', vid)
        self.assertTrue(r['alcance']['parcial'])
        self.assertEqual(len(r['perguntas_supervisor']), 3)
        self.assertFalse([v['id'] for v in r['verificacoes'] if v['resultado'] == 'NAO_APLICAVEL' and v['grupo'] in 'CE'
                          and 'POSI' in v['id'] + v['titulo'].upper()])
        # 3) dispensadas com justificativa documentada → NÃO APLICÁVEL citando a regra
        self.regras(exigencias(POSICAO_TITULOS_PAGAR={'exigencia': 'DISPENSADA', 'justificativa': 'Sem fornecedores a prazo (teste).'},
                               POSICAO_TITULOS_RECEBER={'exigencia': 'DISPENSADA', 'justificativa': 'Vendas à vista (teste).'},
                               CONFIRMACAO_TERCEIROS={'exigencia': 'DISPENSADA', 'justificativa': 'Sem saldos com terceiros (teste).'}))
        r = self.rodar(docs=docs, res=res)
        v = self.ver(r, 'CONC-C-POSICAO-RECEBER')
        self.assertEqual((v['resultado'], 'Vendas à vista' in v['justificativa']), ('NAO_APLICAVEL', True))

    def test_regra_sem_situacao_ou_teste_em_empresa_real_nao_aplicada(self):
        docs = documentos_conciliacao()
        del docs['confirmacao_alfa.txt']
        legado = exigencias()
        legado['exigencias']['CONFIRMACAO_TERCEIROS'] = {'exigencia': 'DISPENSADA', 'justificativa': 'x', 'origem': 'histórico'}
        self.regras(legado)
        self.assertEqual(self.ver(self.rodar(docs=docs), 'CONC-E-CONF-90030030000133')['resultado'], 'NAO_DETERMINADO')
        teste = exigencias()
        teste['exigencias']['CONFIRMACAO_TERCEIROS'] = {'exigencia': 'DISPENSADA', 'justificativa': 'x', 'origem': 'amostra',
                                                        'situacao': 'TESTE_FICTICIO'}
        self.regras(teste)     # empresa de teste SEM o marcador AMOSTRA-FICTICIA.json = tratada como real
        self.assertEqual(self.ver(self.rodar(docs=docs), 'CONC-E-CONF-90030030000133')['resultado'], 'NAO_DETERMINADO')

    def test_data_do_lancamento_dp_fiscal(self):
        res = resultados()
        res['CONTABILIDADE_DP']['lancamentos'][0]['data'] = None
        res['CONTABILIDADE_FISCAL']['lancamentos'][0]['data'] = '2026-11-01'
        r = self.rodar(res=res)
        dp = [v for v in r['verificacoes'] if v['grupo'] == 'B' and 'FOLHA-PROVENTOS' in v['id']][0]
        self.assertEqual(dp['resultado'], 'DIVERGENTE')
        self.assertIn('data do lançamento ausente', dp['justificativa'])
        fis = [v for v in r['verificacoes'] if v['grupo'] == 'B' and 'NF102' in v['id']][0]
        self.assertIn('fora da competência', fis['justificativa'])

    def test_etapa_falhou_alcance_parcial(self):
        res = resultados()
        del res['DP'], res['CONTABILIDADE_DP']
        r = self.rodar(res=res, etapas={'DP': {'situacao': 'FALHOU', 'resultado': None, 'sha256_registrado': None},
                                        'CONTABILIDADE_DP': {'situacao': 'BLOQUEADA_POR_DEPENDENCIA', 'resultado': None, 'sha256_registrado': None}})
        self.assertTrue(r['alcance']['parcial'])
        areas = [v for v in r['verificacoes'] if v['area_responsavel'] in ('DP', 'CONTABILIDADE_DP')]
        self.assertTrue(areas)
        self.assertFalse([v['id'] for v in areas if v['resultado'] == 'CONFERIDO'])
        self.assertFalse([v['id'] for v in r['verificacoes'] if v['id'].startswith(('CONC-D-DP', 'CONC-D-SALDO-211', 'CONC-D-PAGTO'))
                          and v['resultado'] == 'CONFERIDO'])
        self.assertEqual(self.ver(r, 'CONC-A-SITUACAO-DP')['resultado'], 'PENDENTE')
        self.assertEqual(self.ver(r, 'CONC-C-SALDO-1101')['resultado'], 'CONFERIDO')     # banco não depende do DP
        self.assertEqual(self.saldos(r)['2111'][1], 'PENDENTE')
        self.assertIn('DP', [x['item'] for x in r['alcance']['nao_executadas']])

    def test_resultado_adulterado(self):
        def adulterar(etapas):
            p = Path(etapas['BANCOS']['resultado'])
            d = json.loads(p.read_text(encoding='utf-8'))
            d['lancamentos'][0]['valor'] = '1.00'
            p.write_text(json.dumps(d), encoding='utf-8')
        r = self.rodar(adulterar=adulterar)
        self.assertEqual(self.ver(r, 'CONC-A-HASH-BANCOS')['resultado'], 'DIVERGENTE')
        self.assertNotEqual(self.ver(r, 'CONC-A-ORIGEM-BANCOS')['resultado'], 'CONFERIDO')
        self.assertFalse([v['id'] for v in r['verificacoes'] if v['id'].startswith('CONC-B-LAN-BANCOS') ])
        self.assertEqual(self.ver(r, 'CONC-B-ETAPA-BANCOS')['resultado'], 'PENDENTE')
        self.assertEqual(self.ver(r, 'CONC-C-SALDO-1101')['resultado'], 'PENDENTE')
        self.assertTrue(r['alcance']['parcial'])

    def test_resultado_de_outra_sol_ou_empresa(self):
        res = resultados()
        res['FISCAL']['sol'] = 'SOL-2026-900099'
        res['CONTABILIDADE_DP']['empresa'] = 'OUTRA-EMPRESA-FICTICIA'
        r = self.rodar(res=res)
        self.assertEqual(self.ver(r, 'CONC-A-ORIGEM-FISCAL')['resultado'], 'DIVERGENTE')
        self.assertEqual(self.ver(r, 'CONC-A-ORIGEM-CONTABILIDADE_DP')['resultado'], 'DIVERGENTE')
        self.assertEqual(self.ver(r, 'CONC-A-HASH-FISCAL')['resultado'], 'CONFERIDO')
        # fora do grupo A (integridade do próprio arquivo), nada que dependa de FISCAL/CONTABILIDADE_DP fica CONFERIDO
        self.assertFalse([v['id'] for v in r['verificacoes'] if v['grupo'] != 'A'
                          and v['area_responsavel'] in ('CONTABILIDADE_FISCAL', 'CONTABILIDADE_DP', 'FISCAL', 'DP')
                          and v['resultado'] == 'CONFERIDO'])
        self.assertEqual(self.saldos(r)['2131'][1], 'PENDENTE')

    def test_pacote_alterado(self):
        entradas = self.montar()
        alvo = self.raiz / 'CLIENTES' / EMP / PASTA / 'saldos_abertura.csv'
        alvo.write_text(ABERTURA.replace('40.000,00', '45.455,00'), encoding='utf-8')
        r = conc.conciliar(entradas)
        self.assertEqual(self.ver(r, 'CONC-A-PACOTE')['resultado'], 'DIVERGENTE')
        self.assertEqual(self.ver(r, 'CONC-C-SALDO-1101')['resultado'], 'PENDENTE')

    def test_duplicidade_de_lancamento(self):
        res = resultados()
        dup = copy.deepcopy(res['BANCOS']['lancamentos'][0])
        dup['id'] = 'LAN-007'
        res['BANCOS']['lancamentos'].append(dup)
        r = self.rodar(res=res)
        ids = [v for v in r['verificacoes'] if v['id'].startswith('CONC-B-LAN-BANCOS-MOV-ALFA101-RECEBIMENTO')]
        self.assertEqual(len(ids), 2)
        self.assertTrue(all(v['resultado'] == 'DIVERGENTE' and 'duplicidade' in v['justificativa'] for v in ids))
        self.assertEqual(self.ver(r, 'CONC-C-MOV-MOV-ALFA101')['resultado'], 'DIVERGENTE')
        self.assertEqual(self.ver(r, 'CONC-C-SALDO-1101')['resultado'], 'DIVERGENTE')

    def test_despesa_duas_vezes(self):
        res = resultados()
        l = next(l for l in res['BANCOS']['lancamentos'] if l['movimentos'] == ['MOV-SALARIO'])
        l.update(tipo='DESPESA', debito=conta('4101'))
        r = self.rodar(res=res)
        v = self.ver(r, 'CONC-B-LAN-BANCOS-MOV-SALARIO-DESPESA')
        self.assertEqual(v['resultado'], 'DIVERGENTE')
        self.assertIn('reconhecida duas vezes', v['justificativa'])

    def test_guia_nao_gera_provisao(self):
        res = resultados()
        guia = {'id': 'FIS-GUIA', 'arquivo': f'{PASTA}/guia_iss.txt', 'sha256': 'ab' * 32, 'tipo': 'GUIA', 'pendencias': ['Guia é cobrança'],
                'competencia': COMP, 'valor': '200.00', 'numero': 'G-1', 'elegivel_contabilidade': False}
        res['FISCAL']['documentos'].append(guia)
        r = self.rodar(res=copy.deepcopy(res))
        self.assertEqual(self.ver(r, 'CONC-D-GUIA-FIS-GUIA')['resultado'], 'CONFERIDO')
        res['CONTABILIDADE_FISCAL']['lancamentos'].append(
            {'id': 'PF-FIS-GUIA', 'documento': 'FIS-GUIA', 'arquivo': guia['arquivo'], 'sha256': guia['sha256'],
             'status': 'PROPOSTO_PARA_CONFERENCIA', 'evento': 'ISS', 'competencia': COMP, 'valor': '200.00',
             'debito': conta('3191'), 'credito': conta('2131'), 'pendencias': [], 'aprovado': False, 'escriturado': False})
        r = self.rodar(res=res)
        self.assertEqual(self.ver(r, 'CONC-D-GUIA-FIS-GUIA')['resultado'], 'DIVERGENTE')
        self.assertEqual(self.ver(r, 'CONC-B-LAN-FISCAL-FIS-GUIA-ISS')['resultado'], 'DIVERGENTE')
        self.assertEqual(self.ver(r, 'CONC-D-TRIB-PROVISAO-ISS')['resultado'], 'DIVERGENTE')

    def test_pendencias_anteriores_preservadas(self):
        r = self.rodar(pendencias=['PF-01: documento ilegível', {'id': 'PB-02', 'descricao': 'sem regra'}])
        v = self.ver(r, 'CONC-A-PENDENCIAS-ANTERIORES')
        self.assertEqual(v['resultado'], 'PENDENTE')
        self.assertIn('PF-01', v['item'])
        self.assertEqual(len(r['pendencias_anteriores']), 2)


class TestEstabilidade(Base):
    def test_ids_estaveis_e_reordenacao(self):
        r1 = self.rodar()
        r2 = self.rodar()
        # encontrado de CONC-A-HASH-* é o sha256 do próprio arquivo (muda com a reordenação); demais valores devem ser idênticos
        chave = lambda r: [(v['id'], v['resultado'], None if v['id'].startswith('CONC-A-HASH') else v['valores']['encontrado'])
                           for v in r['verificacoes']]
        self.assertEqual(chave(r1), chave(r2))
        self.assertEqual(len({v['id'] for v in r1['verificacoes']}), len(r1['verificacoes']))
        res = resultados()
        for et in ('BANCOS', 'CONTABILIDADE_FISCAL', 'CONTABILIDADE_DP'):
            random.Random(7).shuffle(res[et]['lancamentos'])
        for n, l in enumerate(res['BANCOS']['lancamentos'], 1):
            l['id'] = f'LAN-{n:03d}'
        random.Random(3).shuffle(res['FINANCEIRO']['movimentos'])
        r3 = self.rodar(res=res)
        self.assertEqual([(i, s, e) for i, s, e in chave(r1)], [(i, s, e) for i, s, e in chave(r3)])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    unittest.main(verbosity=2)
