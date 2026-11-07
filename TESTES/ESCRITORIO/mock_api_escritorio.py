"""Servidor MOCK do Escritório Virtual para testes de interface (somente em memória; dados 100% fictícios).

Serve os arquivos de ESCRITORIO-VIRTUAL e responde a um subconjunto da API local com o MESMO contrato do servidor real
(GET /api/estado, /api/solicitacoes, /api/solicitacoes/<sol>, /api/solicitacoes/<sol>/financeiro, /api/empresas,
/api/empresas/<id>, /api/empresas/<id>/base-inicial, /api/amostra; POST /api/empresas/<id>/contas-adiantamento, /api/solicitacoes/<sol>/areas/<ETAPA>/retomar,
/api/solicitacoes/<sol>/aprovacao, /api/amostra/preparar, /api/amostra/corrigir-dp-b). Não lê nem grava CLIENTES, runtime ou registros.
Aprovação do fechamento (SIMULAÇÃO): mesmo contrato do servidor (aprovacao, aprovacoes_anteriores, aprovacao_impedimentos,
frase_aprovacao "APROVO FECHAMENTO <SOL>", estado FECHAMENTO_APROVADO); só conc_ok não tem impedimentos.
Cenários do percurso completo (valores da amostra A fictícia): conc_ok, conc_div, conc_desat, falha_cdp, sem_ancora.
Rotas de controle do teste: /__cenario?n=<nome> e /__posts (POSTs recebidos).

Uso: python -I mock_api_escritorio.py <pasta ESCRITORIO-VIRTUAL> <porta>
"""
import copy
import http.server
import json
import sys
import urllib.parse
from pathlib import Path

EV = Path(sys.argv[1])
PORTA = int(sys.argv[2])
EMPRESA = 'FICTICIA-AUD'
C = {'n': 'enc', 'atraso_amostra': 0.0}   # atraso_amostra: reproduz resposta lenta de /api/amostra (PN-16)
POSTS = []
T = lambda m: f"2026-10-01T10:{m:02d}:00-03:00"  # noqa: E731
NA = {'status': 'NAO_APLICAVEL'}
# Cadastro fictício: plano com grupos e tipos; 1150 é a conta contábil do banco; 1103 é sintética.
PLANO = [
    {'codigo': '1101', 'classificacao': '1.1.2.01', 'descricao': 'ADIANTAMENTO A FORNECEDORES', 'grupo': 'ATIVO', 'tipo': 'ANALITICA'},
    {'codigo': '1102', 'classificacao': '1.1.2.02', 'descricao': 'OUTROS CREDITOS', 'grupo': 'ATIVO', 'tipo': 'ANALITICA'},
    {'codigo': '1103', 'classificacao': '1.1.2', 'descricao': 'CREDITOS (GRUPO)', 'grupo': 'ATIVO', 'tipo': 'SINTETICA'},
    {'codigo': '1150', 'classificacao': '1.1.1.01', 'descricao': 'BANCO FICTICIO', 'grupo': 'ATIVO', 'tipo': 'ANALITICA'},
    {'codigo': '2101', 'classificacao': '2.1.1.01', 'descricao': 'FORNECEDORES', 'grupo': 'PASSIVO', 'tipo': 'ANALITICA'},
    {'codigo': '2102', 'classificacao': '2.1.1.02', 'descricao': 'ADIANTAMENTO DE CLIENTES', 'grupo': 'PASSIVO', 'tipo': 'ANALITICA'},
    {'codigo': '4103', 'classificacao': '4.1.1.03', 'descricao': 'DESPESAS GERAIS', 'grupo': 'DESPESA', 'tipo': 'ANALITICA'},
]
CONTAS_BANCO = [{'banco': '999 · Banco Ficticio', 'agencia': '0001', 'conta': '12345-6', 'titular': '00000000000191', 'contabil': '1150'}]
ADIANTAMENTO = {}   # natureza -> {conta, descricao, justificativa, indicada_em}
APROVACOES = {}     # sol -> {'aprovacao': {...} | None, 'anteriores': [...]} (em memória; zera a cada /__cenario)
COMPAT = {'LIQUIDACAO_OBRIGACAO': ('DEBITO', ['PASSIVO']), 'DESPESA': ('DEBITO', ['CUSTO', 'DESPESA']), 'RECEBIMENTO': ('CREDITO', ['ATIVO']),
          'RECEITA': ('CREDITO', ['RECEITA']), 'ADIANTAMENTO_FORNECEDOR': ('DEBITO', ['ATIVO']), 'ADIANTAMENTO_CLIENTE': ('CREDITO', ['PASSIVO'])}


def etapas_fb(bancos='CONCLUIDA', fiscal=False, incompletos=3):
    e = {'documentos': {'status': 'CONCLUIDA', 'inicio': T(1), 'fim': T(2)}, 'reconhecimento': NA, 'importacao': NA,
         'financeiro': {'status': 'CONCLUIDA', 'n': 1, 'inicio': T(2), 'fim': T(3), 'resumo': {'movimentos': 4, 'sem_suporte': 0}},
         'bancos': {'status': bancos, 'n': 1, 'inicio': T(3), 'fim': T(4) if bancos == 'CONCLUIDA' else None,
                    'resumo': {'propostos': 4 - incompletos, 'incompletos': incompletos} if bancos == 'CONCLUIDA' else None},
         'fiscal': NA, 'contabilfiscal': NA}
    if fiscal:
        e['fiscal'] = {'status': 'CONCLUIDA', 'n': 1, 'inicio': T(2), 'fim': T(3), 'resumo': {'documentos': 1, 'pendencias': 0}}
        e['contabilfiscal'] = {'status': 'CONCLUIDA', 'n': 1, 'inicio': T(5), 'fim': T(6), 'resumo': {'propostos': 1, 'incompletos': 0}}
    return e


def lanc(i, st, faltas=(), direcao='DEBITO'):
    return {'id': f'L{i}', 'status': st, 'data': '2026-09-0%d' % i, 'valor': 100 + i, 'movimentos': [f'M{i}'],
            'debito': {'codigo': '4103', 'descricao': 'DESPESAS GERAIS'} if st == 'PROPOSTO' else None,
            'credito': {'codigo': '1150', 'descricao': 'BANCO FICTICIO'}, 'historico': 'pagto ficticio', 'fato': 'ficticio', 'documentos': [],
            'origem': 'RB-001' if st == 'PROPOSTO' else None, 'acompanhamentos': [],
            'pendencias': [] if st == 'PROPOSTO' else [f'Pendência fictícia {f}' for f in faltas], 'faltas_codigos': list(faltas)}


# cenário -> (sol, estado, etapas, extras do detalhe, lançamentos, pendências do Financeiro)
def cenario():
    n = C['n']
    if n in PERCURSOS:
        return percurso()
    if n in ('enc', 'can'):
        sol = 'SOL-2026-000102' if n == 'enc' else 'SOL-2026-000103'
        ls = [lanc(1, 'PROPOSTO')] + [lanc(i, 'INCOMPLETO', ['SUPORTE']) for i in (2, 3, 4)]
        extra = {'revisao_parcial_encerrada': n == 'enc',
                 'revisoes_piloto': [{'acao': 'encerrar', 'em': T(9), 'justificativa': 'fictícia'}] if n == 'enc' else [],
                 'tarefas_areas': {'FINANCEIRO': {'area': 'FINANCEIRO', 'estado': 'ENTREGUE_COM_PENDENCIAS', 'documentos': ['D01']},
                                   'CONTABILIDADE': {'area': 'CONTABILIDADE', 'estado': 'PROPOSTAS_PARCIAIS_AGUARDANDO_SUPERVISOR', 'documentos': ['D01']}}}
        return sol, 'ENCERRADA' if n == 'enc' else 'CANCELADA', etapas_fb(), extra, ls, [
            {'id': 'PF-1', 'tipo': 'EXTRATO_INCOMPLETO', 'descricao': 'Extrato cobre somente até 10/09.', 'referencia': 'Conta 1150'}]
    if n == 'pend':
        ls = [lanc(i, 'PROPOSTO') for i in (1, 2, 3, 4)]
        extra = {'tarefas_areas': {'FINANCEIRO': {'area': 'FINANCEIRO', 'estado': 'ENTREGUE_COM_PENDENCIAS', 'documentos': ['D01']},
                                   'CONTABILIDADE': {'area': 'CONTABILIDADE', 'estado': 'PROPOSTAS_PARCIAIS_AGUARDANDO_SUPERVISOR', 'documentos': ['D01']}}}
        return 'SOL-2026-000104', 'AGUARDANDO_SUPERVISOR', etapas_fb(incompletos=0), extra, ls, [
            {'id': 'PF-1', 'tipo': 'EXTRATO_INCOMPLETO', 'descricao': 'Extrato cobre somente até 10/09; restante do mês sem extrato.', 'referencia': 'Conta 1150'},
            {'id': 'PF-2', 'tipo': 'DOCUMENTO_ILEGIVEL', 'descricao': 'Comprovante ilegível.', 'referencia': 'D02'}]
    if n == 'misto':
        extra = {'motivos': ['Relatório: análise fictícia', 'FALHA_BANCOS: erro fictício na preparação das propostas'],
                 'falhas_areas': {'BANCOS': 'FALHA_BANCOS: erro fictício na preparação das propostas'},
                 'tarefas_areas': {'FINANCEIRO': {'area': 'FINANCEIRO', 'estado': 'ENTREGUE', 'documentos': ['D01']},
                                   'CONTABILIDADE': {'area': 'CONTABILIDADE', 'estado': 'FALHOU', 'documentos': ['D01']},
                                   'FISCAL': {'area': 'FISCAL', 'estado': 'ENTREGUE', 'documentos': ['D02']},
                                   'CONTABILIDADE_FISCAL': {'area': 'CONTABILIDADE_FISCAL', 'estado': 'PROPOSTAS_PARCIAIS_AGUARDANDO_SUPERVISOR', 'documentos': ['D02']}},
                 'fiscal': {'resumo': {'documentos': 1, 'pendencias': 0}, 'documentos': [
                     {'tipo': 'NFSE', 'numero': '10', 'valor': 500, 'competencia': '2026-09', 'papel_empresa': 'TOMADOR_DESTINATARIO',
                      'arquivo': 'D02.xml', 'retencoes': {}, 'pendencias': []}], 'limitacoes': ['fictícia']},
                 'contabilfiscal': {'resumo': {'propostos': 1, 'incompletos': 0}, 'lancamentos': [
                     {'status': 'PROPOSTO', 'valor': 500, 'debito': {'codigo': '4103', 'descricao': 'DESPESAS GERAIS'},
                      'credito': {'codigo': '2101', 'descricao': 'FORNECEDORES'}, 'historico': 'NFS-e 10 fictícia', 'arquivo': 'D02.xml',
                      'origem_regra': 'ficticia', 'pendencias': []}]}}
        return 'SOL-2026-000105', 'AGUARDANDO_SUPERVISOR', etapas_fb(bancos='FALHOU', fiscal=True), extra, None, []
    # 'adi': decisões com adiantamento, dependência de área e cadastro
    ls = [lanc(1, 'INCOMPLETO', ['SEM_REGRA']), lanc(2, 'INCOMPLETO', ['ADIANTAMENTO_NAO_INDICADO', 'SUPORTE']),
          lanc(3, 'INCOMPLETO', ['DEPENDE_AREA']), lanc(4, 'PROPOSTO')]
    return 'SOL-2026-000106', 'AGUARDANDO_SUPERVISOR', etapas_fb(), {}, ls, []


# ---------------------------------------------------------------- percurso completo (amostra A, valores 100% fictícios)
PERCURSOS = ('conc_ok', 'conc_div', 'conc_desat', 'falha_cdp', 'sem_ancora')
AMOSTRA = {'A': {'empresa': 'AMOSTRA-COMPLETA-FICTICIA', 'preparada': False, 'documentos': 'TESTES/AMOSTRA-COMPLETA/CENARIO-A'},
           'B': {'empresa': 'AMOSTRA-PENDENCIAS-FICTICIA', 'preparada': False, 'documentos': 'TESTES/AMOSTRA-COMPLETA/CENARIO-B'}}
CT = {'1101': 'BANCO FICTICIO C/C', '1121': 'CLIENTES', '2101': 'FORNECEDORES', '2111': 'SALARIOS A PAGAR', '2112': 'INSS A RECOLHER',
      '2113': 'FGTS A RECOLHER', '2114': 'IRRF A RECOLHER', '2121': 'PROVISAO DE FERIAS', '2122': 'PROVISAO DE 13 SALARIO', '2131': 'ISS A RECOLHER',
      '2132': 'PIS A RECOLHER', '2133': 'COFINS A RECOLHER', '3101': 'RECEITA DE SERVICOS', '3191': '(-) ISS SOBRE SERVICOS', '3192': '(-) PIS',
      '3193': '(-) COFINS', '4101': 'SALARIOS', '4102': 'INSS PATRONAL', '4103': 'FGTS', '4104': 'FERIAS', '4105': '13 SALARIO', '4202': 'TARIFAS BANCARIAS'}
cta = lambda c: {'codigo': c, 'descricao': CT[c]} if c else None  # noqa: E731
BANCOS_A = [('2026-10-03', 10000, '1101', '1121', 'TED RECEBIDA ALFA NF 101'), ('2026-10-05', 3000, '2101', '1101', 'PIX BETA NF 555'),
            ('2026-10-15', 500, '2131', '1101', 'PAGTO ISS 09/2026'), ('2026-10-25', 6000, '1101', '1121', 'TED RECEBIDA GAMA NF 102'),
            ('2026-10-30', 7000, '2111', '1101', 'PAGTO SALARIOS FP-2026-10'), ('2026-10-31', 45, '4202', '1101', 'TARIFA BANCARIA')]
DP_A = [('FOLHA_PROVENTOS', 'RECONHECIMENTO', '4101', '2111', '8000.00', 'FP-2026-10'), ('RETENCAO_INSS', 'RETENCAO', '2111', '2112', '700.00', 'FP-2026-10'),
        ('RETENCAO_IRRF', 'RETENCAO', '2111', '2114', '300.00', 'FP-2026-10'), ('ENCARGO_INSS_EMPRESA', 'ENCARGO', '4102', '2112', '2100.00', 'EN-2026-10'),
        ('ENCARGO_FGTS', 'ENCARGO', '4103', '2113', '640.00', 'EN-2026-10'), ('PROVISAO_FERIAS', 'PROVISAO', '4104', '2121', '1000.00', 'PR-2026-10'),
        ('PROVISAO_13', 'PROVISAO', '4105', '2122', '666.67', 'PR-2026-10')]
FISCAL_A = [('6000.00', '1121', '3101', 'NFS-e 102 GAMA — receita de serviços'), ('120.00', '3191', '2131', 'ISS 10/2026'),
            ('39.00', '3192', '2132', 'PIS 10/2026'), ('180.00', '3193', '2133', 'COFINS 10/2026')]


def verif(vid, g, titulo, res, fontes, esperado=None, encontrado=None, area='CONTABILIDADE', contas=(), item=None):
    dif = None if esperado is None or encontrado is None else f'{float(esperado) - float(encontrado):.2f}'
    return {'id': vid, 'grupo': g, 'titulo': titulo, 'item': item, 'contas': list(contas), 'lancamentos': [],
            'fontes': [{'referencia': r, 'tipo': t, 'natureza': n} for r, t, n in fontes],
            'valores': {'esperado': esperado, 'encontrado': encontrado, 'diferenca': dif}, 'resultado': res,
            'justificativa': {'CONFERIDO': 'Valores iguais (igualdade exata).', 'DIVERGENTE': 'Valores diferentes; nada foi corrigido.',
                              'PENDENTE': 'Evidência ausente; nada foi presumido.', 'NAO_APLICAVEL': 'Sem item desta natureza na SOL.'}[res],
            'area_responsavel': area, 'acao': {'CONFERIDO': 'Nenhuma ação de correção; conferência do Supervisor.',
                                               'DIVERGENTE': f'Comunicar ao Coordenador Geral e devolver à área {area} para correção.',
                                               'PENDENTE': f'Providenciar o que falta (área {area}) e reexecutar a Conciliação.',
                                               'NAO_APLICAVEL': '—'}[res]}


def conciliacao(n):
    ok = n in ('conc_ok', 'conc_desat')
    vs = [verif('CONC-A-SHA-BANCOS', 'A', 'Resultado de Bancos íntegro (sha256 = registrado)', 'CONFERIDO', [('bancos-1/resultado.json', 'RESULTADO', 'RESULTADO')], area='COORDENADOR'),
          verif('CONC-B-LAN-M1-RECEBIMENTO', 'B', 'Lançamento D1101/C1121 10.000,00 com suporte', 'CONFERIDO', [('extrato out/2026', 'EXTRATO', 'EXTERNA'), ('NF 101', 'NFSE', 'INTERNA')], '10000.00', '10000.00', contas=('1101', '1121')),
          verif('CONC-C-SALDO-1101', 'C', 'Saldo contábil 1101 × saldo final do extrato', 'CONFERIDO' if ok else 'DIVERGENTE',
                [('SALDOS DE ABERTURA 30/09', 'SALDOS_ABERTURA', 'INTERNA'), ('extrato out/2026 (saldo final)', 'EXTRATO', 'EXTERNA')], '45455.00', '45455.00' if ok else '45410.00', contas=('1101',)),
          verif('CONC-C-POSICAO-2101', 'C', 'Fornecedores × posição FINAL a pagar', 'CONFERIDO', [('posição de títulos FINAL', 'POSICAO_TITULOS', 'INTERNA')], '0.00', '0.00', area='FINANCEIRO', contas=('2101',)),
          verif('CONC-D-INSS-2112', 'D', 'INSS a recolher × resumo de encargos', 'CONFERIDO' if ok else 'DIVERGENTE', [('EN-2026-10', 'DEMONSTRATIVO_DP', 'INTERNA')], '2800.00', '2800.00' if ok else '2100.00', area='DP', contas=('2112',)),
          verif('CONC-D-LIQUIDO-FP', 'D', 'Pagamento de salários no extrato × LÍQUIDO A PAGAR', 'CONFERIDO', [('extrato 30/10', 'EXTRATO', 'EXTERNA'), ('FP-2026-10', 'DEMONSTRATIVO_DP', 'INTERNA')], '7000.00', '7000.00', area='DP', contas=('2111',)),
          verif('CONC-E-CONF-BETA', 'E', 'Confirmação de saldo BETA × posição a pagar', 'CONFERIDO' if ok else 'PENDENTE',
                [('CONFIRMACAO DE SALDO BETA', 'CONFIRMACAO_TERCEIRO', 'EXTERNA')] if ok else [], '0.00', '0.00' if ok else None, area='FINANCEIRO', contas=('2101',)),
          verif('CONC-E-CONF-GAMA', 'E', 'Confirmação de terceiro para clientes', 'NAO_APLICAVEL', [], area='FINANCEIRO')]
    resumo = {k.lower(): sum(v['resultado'] == k for v in vs) for k in ('CONFERIDO', 'DIVERGENTE', 'PENDENTE', 'NAO_APLICAVEL')}
    resumo['total'] = len(vs)
    nao = [] if ok else [{'grupo': 'E', 'item': 'CONFIRMACAO_GAMA', 'motivo': 'confirmação de saldo do cliente GAMA não recebida'},
                         {'grupo': 'D', 'item': 'CONTABILIDADE_DP', 'motivo': 'etapa CONTABILIDADE_DP FALHOU'}]
    alcance = {'executadas': ['A', 'B', 'C', 'D', 'E'], 'nao_executadas': nao, 'parcial': bool(nao),
               'texto': 'Todas as verificações previstas foram executadas sobre as entradas recebidas.' if ok else
               'Conciliação PARCIAL: ' + '; '.join(f"{x['grupo']}/{x['item']}: {x['motivo']}" for x in nao) + '.'}
    res = {'contrato': 'CONCILIACAO_V1', 'agente': 'CONCILIACAO', 'empresa': AMOSTRA['A']['empresa'], 'sol': 'SOL-2026-000201', 'competencia': '2026-10',
           'modo': 'SIMULACAO', 'verificacoes': vs, 'resumo': resumo, 'alcance': alcance, 'n': 2 if n == 'conc_desat' else 1,
           'aviso': 'SIMULAÇÃO. A Conciliação verifica e aponta; não corrige, não aprova, não escritura e não libera.'}
    hist = [{'em': T(40), 'tentativa': 1, 'resumo': resumo, 'alcance': alcance, 'versoes_entradas': {'BANCOS': 'a' * 64}, 'resultado_sha256': 'c' * 64,
             'vigente': n != 'conc_desat'}]
    if n == 'conc_desat':
        hist.insert(0, {'em': T(20), 'tentativa': 0, 'resumo': {'conferido': 3, 'divergente': 1, 'pendente': 0, 'nao_aplicavel': 0, 'total': 4},
                        'alcance': {'executadas': ['A', 'B'], 'nao_executadas': [], 'parcial': False, 'texto': 'anterior'}, 'versoes_entradas': {},
                        'resultado_sha256': 'b' * 64, 'vigente': False})
    return {'historico': hist, 'vigente': n != 'conc_desat', 'resultado': res}


def percurso():
    n = C['n']
    falha = n in ('falha_cdp', 'sem_ancora')
    ordem = ['FINANCEIRO', 'DP', 'FISCAL', 'BANCOS', 'CONTABILIDADE_DP', 'CONTABILIDADE_FISCAL', 'CONCILIACAO']
    dep = {'BANCOS': ['FINANCEIRO'], 'CONTABILIDADE_DP': ['DP'], 'CONTABILIDADE_FISCAL': ['FISCAL']}
    plano = [{'etapa': e, 'situacao': 'FALHOU' if falha and e == 'CONTABILIDADE_DP' else 'CONCLUIDA', 'depende': dep.get(e, []),
              'tentativas': 1} for e in ordem]
    chave = {'FINANCEIRO': 'financeiro', 'DP': 'dp', 'FISCAL': 'fiscal', 'BANCOS': 'bancos', 'CONTABILIDADE_DP': 'contabdp',
             'CONTABILIDADE_FISCAL': 'contabilfiscal', 'CONCILIACAO': 'conciliacao'}
    conc = conciliacao('conc_div' if falha else n)
    cr = conc['resultado']['resumo']
    resumos = {'financeiro': {'movimentos': 6, 'sem_suporte': 0}, 'dp': {'documentos': 3, 'aptos': 3, 'fatos': 8, 'pendencias': 0},
               'fiscal': {'documentos': 2, 'pendencias': 0}, 'bancos': {'propostos': 6, 'incompletos': 0}, 'contabdp': {'propostos': 7, 'incompletos': 0},
               'contabilfiscal': {'propostos': 4, 'incompletos': 0}, 'conciliacao': cr}
    et = {'documentos': {'status': 'CONCLUIDA', 'inicio': T(1), 'fim': T(2)}, 'reconhecimento': NA, 'importacao': NA}
    for i, e in enumerate(ordem):
        k = chave[e]
        et[k] = {'status': 'FALHOU', 'n': 1, 'inicio': T(3 + i), 'fim': None} if falha and e == 'CONTABILIDADE_DP' else \
            {'status': 'CONCLUIDA', 'n': 1, 'inicio': T(3 + i), 'fim': T(4 + i), 'resumo': resumos[k]}
    escopo = 'SIMULACAO_CONCILIADA_NO_ALCANCE' if n in ('conc_ok', 'conc_desat') else 'SIMULACAO_CONCILIACAO_PARCIAL'
    tarefas = {a: {'area': a, 'estado': 'ENTREGUE', 'documentos': [{'id': 'D01', 'arquivo': 'D01.csv', 'papel': 'PRINCIPAL'}]}
               for a in ('FINANCEIRO', 'DP', 'FISCAL', 'CONTABILIDADE', 'CONTABILIDADE_DP', 'CONTABILIDADE_FISCAL', 'CONCILIACAO')}
    if falha:
        tarefas['CONTABILIDADE_DP'].update(estado='FALHOU', motivo='REGRAS-DP.json inválido (JSON truncado) — falha real de configuração')
    if escopo != 'SIMULACAO_CONCILIADA_NO_ALCANCE':
        tarefas['CONCILIACAO']['estado'] = 'ENTREGUE_COM_PENDENCIAS'
    contabdp = None if falha else {'n': 1, 'resumo': {'propostos': 7, 'incompletos': 0, 'valor_propostos': '13406.67'}, 'pendencias': [], 'limites': ['fictício'],
                                   'lancamentos': [{'id': f'DP-{doc}-{ev}', 'evento': ev, 'natureza': nat, 'status': 'PROPOSTO_PARA_CONFERENCIA', 'competencia': '2026-10',
                                                    'valor': v, 'debito': cta(d), 'credito': cta(c), 'documento': doc, 'arquivo': f'{doc}.txt',
                                                    'origem': {'fato': f'{doc}-{ev}', 'numero': doc}, 'regra': {'fonte': 'REGRAS-DP.json'}, 'pendencias': [],
                                                    'aprovado': False, 'escriturado': False} for ev, nat, d, c, v, doc in DP_A]}
    extra = {'fluxo_origem': 'DOCUMENTOS', 'plano_etapas': plano, 'tarefas_areas': tarefas,
             'falhas_areas': {'CONTABILIDADE_DP': 'FALHA_CONTABILIDADE_DP: REGRAS-DP.json inválido'} if falha else {},
             'dp': {'n': 1, 'resumo': resumos['dp'], 'documentos': [{'id': x, 'arquivo': f'{x}.txt', 'tipo': t, 'numero': x, 'competencia': '2026-10', 'pendencias': [],
                                                                     'elegivel_contabilidade': True} for x, t in (('FP-2026-10', 'RESUMO_FOLHA'), ('EN-2026-10', 'RESUMO_ENCARGOS'), ('PR-2026-10', 'PROVISOES'))],
                    'fatos': [], 'pendencias': [], 'limites': ['fictício']},
             'contabdp': contabdp,
             'fiscal': {'n': 1, 'resumo': {'documentos': 2, 'pendencias': 0}, 'limitacoes': ['fictícia'], 'documentos': [
                 {'tipo': 'NFSE', 'numero': '102', 'valor': 6000, 'competencia': '2026-10', 'papel_empresa': 'PRESTADOR_EMITENTE', 'arquivo': 'NF102.xml', 'retencoes': {}, 'pendencias': []},
                 {'tipo': 'APURACAO_TRIBUTO', 'numero': 'AP-10', 'valor': 339, 'competencia': '2026-10', 'papel_empresa': 'CONTRIBUINTE', 'arquivo': 'AP10.txt', 'retencoes': {}, 'pendencias': []}]},
             'contabilfiscal': {'n': 1, 'resumo': {'propostos': 4, 'incompletos': 0}, 'lancamentos': [
                 {'status': 'PROPOSTO', 'valor': v, 'debito': cta(d), 'credito': cta(c), 'historico': h, 'arquivo': 'NF102.xml', 'origem_regra': 'REGRAS-FISCAIS.json', 'pendencias': []}
                 for v, d, c, h in FISCAL_A]},
             'conciliacao': conc, 'escopo_resultado': escopo,
             'retomadas': [{'em': T(30), 'etapa': 'CONTABILIDADE_DP', 'justificativa': 'Referências corrigidas (fictício)', 'reexecuta': ['CONTABILIDADE_DP', 'CONCILIACAO']}] if n == 'conc_desat' else [],
             'retomada_disponivel': n != 'sem_ancora'}
    return 'SOL-2026-000201', 'AGUARDANDO_SUPERVISOR', et, extra, BANCOS_A, []


def impedimentos(estado):
    """Mesma regra do Coordenador (impedimentos_aprovacao), aplicada aos cenários fictícios do mock."""
    n = C['n']
    faltas = [] if estado == 'AGUARDANDO_SUPERVISOR' else ['A solicitação não está aguardando o Supervisor.']
    if n not in PERCURSOS or n == 'sem_ancora':
        return faltas + ['Solicitação sem pacote local com âncora de integridade (anterior a esta versão).']
    if n == 'falha_cdp':
        faltas += ['Etapa CONTABILIDADE_DP não concluída (FALHOU).', 'Conciliação com 2 verificação(ões) divergente(s).',
                   'Conciliação com 1 verificação(ões) pendente(s).', 'Conciliação com alcance parcial.']
    if n == 'conc_div':
        faltas += ['Conciliação com 2 verificação(ões) divergente(s).', 'Conciliação com 1 verificação(ões) pendente(s).', 'Conciliação com alcance parcial.']
    if n == 'conc_desat':
        faltas.append('Conciliação desatualizada: resultados alterados depois dela.')
    return faltas


def estado_atual(sol, estado):
    return 'FECHAMENTO_APROVADO' if (APROVACOES.get(sol) or {}).get('aprovacao') else estado


def aprovar(sol, corpo):
    """POST /api/solicitacoes/<sol>/aprovacao (mesmas validações do servidor e do Coordenador)."""
    if set(corpo) - {'acao', 'frase', 'justificativa', 'confirmado'} or corpo.get('confirmado') is not True or corpo.get('acao') not in ('aprovar', 'revogar'):
        return 400, {'erro': 'Confirme a ação (aprovar ou revogar) e informe a justificativa.'}
    j = str(corpo.get('justificativa') or '').strip()
    if not 5 <= len(j) <= 500 or '|' in j:
        return 409, {'erro': 'Informe justificativa de 5 a 500 caracteres.'}
    _, estado, *_ = cenario()
    reg = APROVACOES.setdefault(sol, {'aprovacao': None, 'anteriores': []})
    if corpo['acao'] == 'revogar':
        if not reg['aprovacao']:
            return 409, {'erro': 'Não há aprovação vigente para revogar.'}
        reg['anteriores'].append(dict(reg['aprovacao'], revogada_em=T(59), motivo_revogacao=j))
        reg['aprovacao'] = None
        return 200, {'resultado': 'APROVACAO_REVOGADA', 'sol': sol, 'estado': 'AGUARDANDO_SUPERVISOR'}
    esperado = f'APROVO FECHAMENTO {sol}'
    if str(corpo.get('frase') or '').strip() != esperado:
        return 409, {'erro': f'Aprovação exige a frase exata: "{esperado}".'}
    faltas = impedimentos(estado_atual(sol, estado))
    if faltas:
        return 409, {'erro': 'Não é possível aprovar: ' + ' '.join(faltas)}
    reg['aprovacao'] = {'em': T(50), 'por': 'Supervisor Contábil', 'frase': esperado, 'justificativa': j, 'escopo': 'SIMULACAO',
                        'conciliacao_tentativa': 1, 'escrituracao': 'NAO_REALIZADA', 'liberacao_dominio': 'BLOQUEADA_NESTA_VERSAO'}
    return 200, {'resultado': 'FECHAMENTO_APROVADO', 'sol': sol, 'estado': 'FECHAMENTO_APROVADO'}


def detalhe():
    sol, estado, et, extra, _, _ = cenario()
    estado = estado_atual(sol, estado)
    d = {'sol': sol, 'empresa': EMPRESA, 'competencia': '2026-09', 'modo': 'SIMULACAO', 'fluxo': 'FINANCEIRO_BANCOS', 'piloto': None,
         'estado': estado, 'etapa': None, 'motivos': ['Relatório: fictício'], 'eventos': [{'em': T(1), 'evento': 'criada (fictícia)'}],
         'instrucao': 'teste fictício', 'execucao': {'status': 'CONCLUIDA', 'inicio': T(1), 'fim': T(2), 'auditoria': {}},
         'etapas': et, 'mensagem': None,
         'arquivos': [{'nome_original': 'extrato.ofx', 'nome_interno': 'D01.ofx', 'tamanho': 1, 'sha256': '0' * 64, 'duplicado_de': None}],
         'inventario': [{'nome': 'D01.ofx', 'leitura': 'EXTRAIDO_TEXTO'}], 'documentos_local': None, 'tarefas_areas': {},
         'fiscal': None, 'contabilfiscal': None, 'escopo_resultado': 'PARCIAL_PILOTO_SEM_CONCILIACAO', 'revisao_parcial_encerrada': False,
         'pendencias': [], 'relatorio': 'fictício', 'dp': None, 'contabdp': None, 'conciliacao': None, 'plano_etapas': [], 'retomadas': [],
         'retomada_disponivel': False, 'falhas_areas': {}}
    d.update(copy.deepcopy(extra))
    reg = APROVACOES.get(sol) or {}
    eventos = [{'em': x['em'], 'evento': 'Supervisor APROVOU o fechamento conferido (SIMULAÇÃO). Nada foi escriturado nem liberado.'} for x in reg.get('anteriores', [])]
    eventos += [{'em': x['revogada_em'], 'evento': f"Supervisor revogou a aprovação do fechamento: {x['motivo_revogacao']}"} for x in reg.get('anteriores', [])]
    if reg.get('aprovacao'):
        eventos.append({'em': reg['aprovacao']['em'], 'evento': 'Supervisor APROVOU o fechamento conferido (SIMULAÇÃO). Nada foi escriturado nem liberado.'})
    d['eventos'] = d['eventos'] + sorted(eventos, key=lambda x: x['em'])
    d.update({'aprovacao': copy.deepcopy(reg.get('aprovacao')), 'aprovacoes_anteriores': copy.deepcopy(reg.get('anteriores', [])),
              'aprovacao_impedimentos': [] if estado == 'FECHAMENTO_APROVADO' else impedimentos(estado), 'frase_aprovacao': f'APROVO FECHAMENTO {sol}'})
    return d


def financeiro():
    sol, estado, _, _, ls, pend = cenario()
    if C['n'] in PERCURSOS:
        ls = [{'id': f'L{i}', 'status': 'PROPOSTO', 'data': dt, 'valor': v, 'movimentos': [f'M{i}'], 'debito': cta(d), 'credito': cta(c),
               'historico': h, 'fato': 'movimento do extrato', 'documentos': [{'arquivo': 'extrato-out-2026.csv', 'papel': 'EXTRATO'}],
               'origem': 'REGRAS-BANCOS.md', 'acompanhamentos': [], 'pendencias': [], 'faltas_codigos': []}
              for i, (dt, v, d, c, h) in enumerate(BANCOS_A, 1)]
    movs = [{'id': f'M{i}', 'data': '2026-09-0%d' % i, 'valor': 100 + i, 'direcao': 'DEBITO', 'conta': '1150', 'descricao': 'PAGTO FICTICIO',
             'situacao': 'SEM_SUPORTE' if ls and ls[i - 1]['status'] != 'PROPOSTO' else 'COM_SUPORTE', 'documentos': [], 'origens': ['D01']} for i in (1, 2, 3, 4)]
    bancos = None if ls is None else {'n': 1, 'resumo': {'propostos': sum(x['status'] == 'PROPOSTO' for x in ls),
                                                         'incompletos': sum(x['status'] != 'PROPOSTO' for x in ls), 'valor_propostos': 1, 'valor_incompletos': 1},
                                      'lancamentos': ls, 'pendencias': []}
    return {'disponivel': True, 'estado': estado, 'empresa': EMPRESA, 'competencia': '2026-09', 'em_execucao': False,
            'financeiro': {'resumo': {'movimentos': 4, 'com_suporte': 4, 'sem_suporte': 0, 'comprovante_sem_natureza': 0, 'ambiguos': 0,
                                      'transferencias_proprias': 0},
                           'movimentos': movs, 'sugestoes': [], 'ambiguas': [], 'documentos': [],
                           'verificacao_extratos': [{'conta': '1150', 'cobertura_competencia': 'INCOMPLETA' if pend else 'COMPLETA',
                                                     'situacao': 'SEM_VERIFICACAO_ARITMETICA'}],
                           'pendencias': pend, 'relacionados_sem_movimento': [], 'duplicidades': [], 'ressalvas_documentos': [],
                           'limitacoes': ['fictícia'], 'bloqueio_lote': []},
            'bancos': bancos, 'regras': [], 'decisoes': {}, 'motivos': detalhe()['motivos'],
            'plano_contas': [{k: c[k] for k in ('codigo', 'descricao', 'grupo')} for c in PLANO if c['tipo'] == 'ANALITICA'],
            'contas_banco': ['1150'], 'contas_adiantamento': {k: [v['conta']] for k, v in ADIANTAMENTO.items()},
            'compatibilidade': {k: {'direcao': v[0], 'grupos': v[1]} for k, v in COMPAT.items()}, 'frase_aprovacao': 'VALIDADO REGRA FICTICIA <RB-NNN>',
            'tentativas': {'financeiro': [{'n': 1, 'concluida': True}], 'bancos': [{'n': 1, 'concluida': ls is not None}]}}


def empresa():
    return {'id': EMPRESA, 'nome': 'Empresa Fictícia Auditoria', 'cnpj': '00000000000191', 'regime': 'Simples (fictício)', 'plano': PLANO,
            'contas': CONTAS_BANCO, 'cadastro_confirmado': True, 'piloto': True, 'producao_liberada': False,
            'contas_adiantamento': copy.deepcopy(ADIANTAMENTO)}


def indicar(d):
    exigido = {'ADIANTAMENTO_FORNECEDOR': 'ATIVO', 'ADIANTAMENTO_CLIENTE': 'PASSIVO'}
    nat = d.get('natureza')
    if nat not in exigido or d.get('confirmado') is not True:
        raise ValueError('Natureza inválida ou sem confirmação.')
    if d.get('remover') is True:
        ADIANTAMENTO.pop(nat, None)
        return empresa()
    j = str(d.get('justificativa') or '').strip()
    if not 5 <= len(j) <= 300:
        raise ValueError('Justificativa de 5 a 300 caracteres.')
    c = next((x for x in PLANO if x['codigo'] == d.get('conta')), None)
    if not c or c['tipo'] != 'ANALITICA' or c['grupo'] != exigido[nat] or c['codigo'] == '1150':
        raise ValueError('Conta não permitida para esta natureza.')
    ADIANTAMENTO[nat] = {'conta': c['codigo'], 'descricao': c['descricao'], 'justificativa': j, 'indicada_em': T(30)}
    return empresa()


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def j(self, o, c=200):
        b = json.dumps(o, ensure_ascii=False).encode()
        self.send_response(c)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        tam = int(self.headers.get('Content-Length') or 0)
        corpo = json.loads(self.rfile.read(tam) or b'{}')
        POSTS.append({'rota': self.path, 'corpo': corpo})
        partes = self.path.split('/')
        if len(partes) == 5 and partes[2] == 'solicitacoes' and partes[4] == 'aprovacao':
            codigo, r = aprovar(partes[3], corpo)
            return self.j(r, codigo)
        if len(partes) == 7 and partes[2] == 'solicitacoes' and partes[4] == 'areas' and partes[6] == 'retomar':
            if set(corpo) != {'justificativa', 'confirmado'} or corpo['confirmado'] is not True or not 5 <= len(str(corpo['justificativa']).strip()) <= 500:
                return self.j({'erro': 'Confirme a nova tentativa e informe a justificativa.'}, 400)
            if C['n'] == 'sem_ancora':
                return self.j({'erro': 'Solicitação sem âncora íntegra; abra nova solicitação.'}, 409)
            return self.j({'resultado': 'RETOMADA_INICIADA', 'reexecuta': [partes[5], 'CONCILIACAO'],
                           'mensagem': f'Nova tentativa de {partes[5]} iniciada (reexecuta {partes[5]}, CONCILIACAO); tentativas anteriores preservadas.'}, 202)
        if self.path in ('/api/amostra/preparar', '/api/amostra/corrigir-dp-b'):
            if corpo.get('confirmado') is not True:
                return self.j({'erro': 'Confirme a ação sobre as empresas fictícias da amostra.'}, 400)
            if self.path.endswith('preparar'):
                feitas = []
                for k, a in AMOSTRA.items():
                    feitas.append({'empresa': a['empresa'], 'situacao': 'PREPARADA' if corpo.get('recriar') is True or not a['preparada'] else 'JA_PREPARADA'})
                    a['preparada'] = True
                return self.j({'resultado': 'AMOSTRA_PREPARADA', 'empresas': feitas, 'competencia': '2026-10',
                               'documentos': {k: a['documentos'] for k, a in AMOSTRA.items()}})
            if not AMOSTRA['B']['preparada']:
                return self.j({'erro': 'Empresa fictícia do cenário B não preparada.'}, 400)
            return self.j({'resultado': 'REFERENCIAS_DP_CORRIGIDAS', 'empresa': AMOSTRA['B']['empresa'],
                           'proximo_passo': "Na solicitação do cenário B, use 'Retomar Contabilidade/DP'."})
        if self.path == f'/api/empresas/{EMPRESA}/contas-adiantamento':
            try:
                return self.j(indicar(corpo))
            except ValueError as e:
                return self.j({'erro': str(e)}, 400)
        self.j({'erro': 'mock: ação não suportada'}, 409)

    def do_DELETE(self):
        self.j({'erro': 'mock somente leitura'}, 409)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        if p == '/__cenario':
            q = urllib.parse.parse_qs(u.query, keep_blank_values=True)
            C['n'] = q['n'][0]
            APROVACOES.clear()
            C['atraso_amostra'] = float(q.get('atraso_amostra', ['0'])[0]) / 1000
            if 'amostra' in q:
                for a in AMOSTRA.values():
                    a['preparada'] = q['amostra'][0] == '1'
            if 'adiantamento' in q:
                ADIANTAMENTO.clear()
                if q['adiantamento'][0]:
                    indicar({'natureza': 'ADIANTAMENTO_FORNECEDOR', 'conta': q['adiantamento'][0], 'justificativa': 'indicação fictícia', 'confirmado': True})
            return self.j({'ok': C['n']})
        if p == '/__posts':
            return self.j(POSTS)
        if p.startswith('/api/'):
            r = p[5:].split('/')
            sol, estado, et, _, _, _ = cenario()
            estado = estado_atual(sol, estado)
            if r == ['estado']:
                return self.j({'modo': 'OPERACAO_LOCAL', 'empresas': [{'id': EMPRESA, 'nome': 'Empresa Fictícia Auditoria', 'piloto': None, 'modo': 'SIMULACAO'}],
                               'empresas_pendentes': [], 'em_execucao': None,
                               'recentes': [{'sol': sol, 'empresa': EMPRESA, 'competencia': '2026-09', 'estado': estado, 'execucao': 'CONCLUIDA', 'etapas': et}],
                               'limites': {'arquivo': 1048576, 'lote': 1048576, 'arquivos': 5, 'formatos': ['.pdf', '.ofx']}})
            if r == ['solicitacoes']:
                cat = 'historico' if estado in ('ENCERRADA', 'CANCELADA', 'FECHAMENTO_APROVADO') else 'decisoes'
                lst = [{'sol': sol, 'empresa': EMPRESA, 'competencia': '2026-09', 'fluxo': 'FINANCEIRO_BANCOS', 'estado': estado, 'etapas': et,
                        'proxima_acao': 'Consultar', 'atualizado_em': T(4), 'categoria': cat}]
                return self.j({'solicitacoes': lst, 'contagem': {k: sum(x['categoria'] == k for x in lst) for k in
                                                                ['processando', 'decisoes', 'documentos', 'prontos', 'falhas', 'historico']},
                               'criterio': 'fictício', 'na_lixeira': 0})
            if r == ['amostra']:
                if C['atraso_amostra']:
                    import time as _t
                    _t.sleep(C['atraso_amostra'])
                return self.j(AMOSTRA)
            if r == ['empresas']:
                return self.j([{'id': EMPRESA, 'nome': 'Empresa Fictícia Auditoria'}])
            if r == ['empresas', EMPRESA]:
                return self.j(empresa())
            if r == ['empresas', EMPRESA, 'base-inicial']:      # mesmo contrato do servidor: base ainda não iniciada
                etapas = [{'etapa': n, 'titulo': x, 'feito': n == 1, 'falta': [] if n == 1 else ['pendente']} for n, x in enumerate(
                    ['Identificação', 'Importação e conferência do balancete anterior', 'Conferência das contas e saldos',
                     'Importação e conferência do book', 'Resolução das definições pendentes', 'Confirmação da base inicial'], 1)]
                return self.j({'competencias': [], 'competencia': None, 'etapas': etapas,
                               'proxima_acao': 'Envie o balancete de encerramento do mês anterior (etapa 2).'})
            if r == ['solicitacoes', sol]:
                return self.j(detalhe())
            if r == ['solicitacoes', sol, 'financeiro']:
                return self.j(financeiro())
            return self.j({'erro': 'mock: rota inexistente'}, 404)
        f = (EV / (p.lstrip('/') or 'index.html')).resolve()
        if EV.resolve() not in f.parents or not f.is_file():
            self.send_response(404)
            self.end_headers()
            return
        b = f.read_bytes()
        if f.name == 'index.html':
            b = b.decode().replace("connect-src 'none'", "connect-src 'self'").replace('<head>', '<head>\n<meta name="prime-sessao" content="mock">', 1).encode()
        self.send_response(200)
        self.send_header('Content-Type', {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css'}.get(f.suffix, 'application/octet-stream'))
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)


http.server.ThreadingHTTPServer(('127.0.0.1', PORTA), H).serve_forever()
