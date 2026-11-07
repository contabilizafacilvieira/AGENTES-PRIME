"""Contabilidade/DP: propostas de competência a partir dos fatos do DP. SIMULAÇÃO, sem aprovação nem escrituração.

Uso:
    .venv/Scripts/python.exe -I AGENTES/CONTABILIDADE/DP/ferramentas/propostas_dp.py --empresa <EMP> --competencia AAAA-MM
        --sol <SOL> --dp <resultado.json do DP> --saida <dir>
Saída: <saida>/resultado.json (contrato CONTABILIDADE_DP_V1).
Códigos: 0 = resultado gravado (pode conter propostas INCOMPLETAS); 1 = falha real (resultado DP de outra empresa/SOL/
competência, REGRAS-DP.json inválido, cadastro ausente); 2 = parâmetros inválidos.
"""
import argparse
import calendar
import hashlib
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]


def clientes():
    """Pasta CLIENTES (avaliada a cada uso: AGENTES_PRIME_CLIENTES em testes isolados; RAIZ/CLIENTES em produção)."""
    return Path(os.environ.get("AGENTES_PRIME_CLIENTES") or RAIZ / "CLIENTES")


sys.path.insert(0, str(RAIZ/'AGENTES/CONTABILIDADE/BANCOS/ferramentas'))
from lancamentos_bancarios import tabela_md, norm  # noqa: E402
sys.path.insert(0, str(RAIZ/'AGENTES/CONTABILIDADE'))
import governanca_regras as gov  # noqa: E402

CONTRATO = 'CONTABILIDADE_DP_V1'
COMPETENCIA = re.compile(r'20\d{2}-(0[1-9]|1[0-2])')
DESPESA, PASSIVO = {'DESPESA', 'CUSTO'}, {'PASSIVO'}
# evento → (natureza do lançamento, grupos do débito, grupos do crédito)
EVENTOS = {'FOLHA_PROVENTOS': ('RECONHECIMENTO', DESPESA, PASSIVO), 'RETENCAO_INSS': ('RETENCAO', PASSIVO, PASSIVO),
           'RETENCAO_IRRF': ('RETENCAO', PASSIVO, PASSIVO), 'ENCARGO_INSS_EMPRESA': ('ENCARGO', DESPESA, PASSIVO),
           'ENCARGO_FGTS': ('ENCARGO', DESPESA, PASSIVO), 'PROVISAO_FERIAS': ('PROVISAO', DESPESA, PASSIVO),
           'PROVISAO_13': ('PROVISAO', DESPESA, PASSIVO)}
INFORMATIVOS = {'LIQUIDO_A_PAGAR'}
DESCRICAO_EVENTO = {'FOLHA_PROVENTOS': 'FOLHA DE PAGAMENTO - PROVENTOS', 'RETENCAO_INSS': 'RETENCAO INSS SEGURADOS',
                    'RETENCAO_IRRF': 'RETENCAO IRRF SOBRE SALARIOS', 'ENCARGO_INSS_EMPRESA': 'INSS PATRONAL E TERCEIROS',
                    'ENCARGO_FGTS': 'FGTS SOBRE FOLHA', 'PROVISAO_FERIAS': 'PROVISAO DE FERIAS COM 1/3',
                    'PROVISAO_13': 'PROVISAO DE 13 SALARIO'}


def historico_dp(evento, competencia, numero):
    """Fato contábil e referência útil (número do documento); caminhos e IDs técnicos ficam na auditoria."""
    mes = f'{competencia[5:7]}/{competencia[:4]}' if competencia and COMPETENCIA.fullmatch(competencia) else 'A CONFERIR'
    return (f"{DESCRICAO_EVENTO.get(evento, str(evento or 'EVENTO DP').replace('_', ' '))} COMPETENCIA {mes}"
            + (f' REF. {numero}' if numero else ''))
SEM_REGRAS = 'Referências contábeis de DP não definidas pelo Supervisor (CLIENTES/<empresa>/REGRAS-DP.json ausente).'


def digitos(t): return re.sub(r'\D', '', str(t or ''))


def ler_cadastro(base):
    arq = base/'CADASTRO.md'
    if not arq.is_file(): raise ValueError(f'Cadastro da empresa ausente ({arq.name}); não é possível validar CNPJ e contas bancárias.')
    t = arq.read_text(encoding='utf-8')
    cnpjs = {digitos(c) for c in re.findall(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', t)}
    bancos = {digitos(l.get('CONTA CONTABIL')) for l in tabela_md(t, 'Contas bancarias') if digitos(l.get('CONTA CONTABIL'))}
    return cnpjs, bancos


def ler_regras(base, empresa, cnpjs, competencia):
    """(referencias, aviso_global, limites, dados). Arquivo inválido → ValueError (falha de configuração)."""
    arq = base/'REGRAS-DP.json'
    if not arq.exists(): return {}, SEM_REGRAS, [], {}
    try: r = json.loads(arq.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e: raise ValueError(f'REGRAS-DP.json inválido: JSON ilegível ({e}).')
    if not isinstance(r, dict) or r.get('contrato') != 'REFERENCIAS_DP_V1':
        raise ValueError('REGRAS-DP.json inválido: contrato diferente de REFERENCIAS_DP_V1.')
    if r.get('empresa') != empresa: raise ValueError('REGRAS-DP.json inválido: empresa não corresponde à solicitação.')
    if not digitos(r.get('cnpj')) or digitos(r.get('cnpj')) not in cnpjs:
        raise ValueError('REGRAS-DP.json inválido: CNPJ ausente ou não pertence ao cadastro da empresa.')
    if not isinstance(r.get('referencias'), dict): raise ValueError('REGRAS-DP.json inválido: "referencias" ausente ou não é objeto.')
    for nome in ('competencia_desde', 'competencia_ate'):
        if r.get(nome) is not None and not COMPETENCIA.fullmatch(str(r[nome])):
            raise ValueError(f'REGRAS-DP.json inválido: {nome} fora do formato AAAA-MM.')
    limites = []
    desconhecidos = sorted(set(r['referencias']) - set(EVENTOS))
    if desconhecidos: limites.append('Referências de DP para eventos desconhecidos ignoradas: ' + ', '.join(desconhecidos) + '.')
    if r.get('competencia_desde') is None:
        return {}, 'Referências de DP sem início de vigência (competencia_desde) declarado.', limites, r
    if competencia < r['competencia_desde']: return {}, 'Referências de DP ainda não vigentes nesta competência.', limites, r
    if r.get('competencia_ate') is not None and competencia > r['competencia_ate']:
        return {}, 'Referências de DP encerradas antes desta competência (fim de vigência).', limites, r
    if r.get('competencia_ate') is None:
        limites.append('Referências de DP sem fim de vigência declarado: válidas até revisão do Supervisor; nenhuma data presumida.')
    return r['referencias'], None, limites, r


def ler_plano(base):
    arq = base/'PLANO-DE-CONTAS/PLANO-DE-CONTAS.md'
    if not arq.is_file(): return None
    return {l['CODIGO REDUZIDO']: l for l in tabela_md(arq.read_text(encoding='utf-8'), 'Contas utilizadas') if l.get('CODIGO REDUZIDO')}


def conta(plano, bancos, codigo, lado, grupos, faltas):
    codigo = str(codigo or '').strip()
    if not codigo: faltas.append(f'Conta de {lado} não informada na referência.'); return None
    if plano is None: faltas.append('Plano de contas da empresa ausente.'); return None
    c = plano.get(codigo)
    if not c: faltas.append(f'Conta de {lado} {codigo} inexistente no plano desta empresa.'); return None
    if norm(c.get('TIPO')) != 'ANALITICA': faltas.append(f'Conta de {lado} {codigo} não é analítica (sintética ou tipo não definido).'); return None
    if norm(c.get('GRUPO')) not in grupos:
        faltas.append(f'Conta de {lado} {codigo} do grupo "{c.get("GRUPO") or "não definido"}" incompatível '
                      f'(exigido: {"/".join(sorted(grupos))}).'); return None
    if digitos(codigo) in bancos: faltas.append(f'Conta de {lado} {codigo} é conta bancária; fatos de DP não movimentam banco.'); return None
    return {'codigo': c['CODIGO REDUZIDO'], 'descricao': c.get('DESCRICAO')}


def gerar(empresa, competencia, sol, dp):
    if not isinstance(dp, dict) or (dp.get('contrato'), dp.get('agente'), dp.get('empresa'), dp.get('competencia'), dp.get('sol')) != (
            'DP_LOCAL_V1', 'DP', empresa, competencia, sol):
        raise ValueError('Resultado do DP de outra empresa, competência ou SOL (ou contrato diferente de DP_LOCAL_V1).')
    if dp.get('modo') != 'SIMULACAO': raise ValueError('Resultado do DP fora do modo SIMULACAO.')
    base = clientes()/empresa
    cnpjs, bancos = ler_cadastro(base)
    referencias, aviso, limites_extra, dados_regras = ler_regras(base, empresa, cnpjs, competencia)
    plano = ler_plano(base)
    # data do LANÇAMENTO (≠ competência do fato): só por política expressa da empresa; nunca presumida
    pol = gov.politica_data(dados_regras, 'DP', empresa, competencia, base)
    data_lanc = None
    if pol['aplicavel'] and pol['politica'] == 'ULTIMO_DIA_COMPETENCIA':
        ano, mes = map(int, competencia.split('-'))
        data_lanc = f'{competencia}-{calendar.monthrange(ano, mes)[1]:02d}'
    elif pol['aplicavel']:
        pol = dict(pol, aplicavel=False, politica=None,
                   motivo=f"DP/DATA_LANCAMENTO: política {pol['politica']} não se aplica a fatos de DP (sem data documentada).")
    docs = {d.get('id'): d for d in dp.get('documentos', [])}
    lancamentos = []
    for f in dp.get('fatos', []):
        ev = f.get('evento')
        if ev in INFORMATIVOS: continue
        faltas = []; debito = credito = None
        natureza = EVENTOS.get(ev, (None,))[0]
        if natureza is None: faltas.append(f'Evento de DP "{ev}" sem tratamento contábil definido.')
        d = docs.get(f.get('documento'))
        if not d or not d.get('elegivel_contabilidade') or d.get('sha256') != f.get('sha256'):
            faltas.append('Fato sem documento elegível correspondente no resultado do DP (suporte não confirmado).')
        if f.get('competencia') != competencia: faltas.append('Fato de competência diferente da SOL.')
        try: v = Decimal(str(f.get('valor')))
        except (InvalidOperation, ValueError): v = None
        if v is None or not v.is_finite() or v <= 0 or v != v.quantize(Decimal('0.01')):
            faltas.append('Valor do fato ausente, não positivo ou fora do formato.'); v = None
        regra = referencias.get(ev) if natureza else None
        governanca = None
        if aviso: faltas.append(aviso)
        elif natureza and not isinstance(regra, dict):
            faltas.append(f'Referência contábil de {ev} não definida (ou malformada) em REGRAS-DP.json.'); regra = None
        if natureza and isinstance(regra, dict):
            av = gov.avaliar(regra, 'DP', empresa, ev, competencia, base)
            governanca = av['governanca']
            if not av['aplicavel']: faltas.append(av['motivo'])
            if not str(regra.get('fonte') or regra.get('origem') or '').strip(): faltas.append('Referência contábil sem fonte documentada.')
            _, gd, gc = EVENTOS[ev]
            debito = conta(plano, bancos, regra.get('debito'), 'débito', gd, faltas)
            credito = conta(plano, bancos, regra.get('credito'), 'crédito', gc, faltas)
            if debito and credito and debito['codigo'] == credito['codigo']:
                faltas.append('Débito e crédito na mesma conta.'); debito = credito = None
        regra = regra if isinstance(regra, dict) else {}
        if natureza and not pol['aplicavel']: faltas.append(pol['motivo'])
        numero = (d or {}).get('numero') or (f.get('origem') or {}).get('numero')
        lancamentos.append({'id': f"DP-{f.get('documento')}-{ev}", 'evento': ev, 'natureza': natureza,
                            'status': 'INCOMPLETO' if faltas else 'PROPOSTO_PARA_CONFERENCIA',
                            'competencia': f.get('competencia'), 'data': data_lanc if pol['aplicavel'] else None,
                            'data_origem': (f"política da empresa: {gov.POLITICAS_DATA[pol['politica']]} "
                                            f"({pol['governanca']['situacao']})") if pol['aplicavel'] else None,
                            'valor': None if v is None else f'{v:.2f}',
                            'historico': historico_dp(ev, f.get('competencia'), numero),
                            # identidade do fato (evento + competência + documento): evita repetir o mesmo fato em outra SOL
                            'identidade': f"DP:{ev}:{f.get('competencia')}:{f.get('sha256')}",
                            'debito': debito, 'credito': credito, 'documento': f.get('documento'), 'arquivo': f.get('arquivo'),
                            'sha256': f.get('sha256'), 'origem': {'fato': f.get('id'), **(f.get('origem') or {})},
                            'regra': {'fonte': regra.get('fonte') or regra.get('origem'), 'governanca': governanca},
                            'pendencias': list(dict.fromkeys(faltas)), 'aprovado': False, 'escriturado': False})
    # Defesa: mesmo documento+evento proposto mais de uma vez não segue para conferência.
    ids = {}
    for l in lancamentos: ids.setdefault(l['id'], []).append(l)
    for g in ids.values():
        if len(g) > 1:
            for l in g:
                l['status'] = 'INCOMPLETO'; l['pendencias'].append('Fato de DP repetido (mesmo documento e evento); nenhum escolhido.')
    nao_aproveitados = [{'documento': d.get('id'), 'arquivo': d.get('arquivo'), 'pendencias': d.get('pendencias', [])}
                        for d in dp.get('documentos', []) if not d.get('elegivel_contabilidade')]
    pendencias = [{'lancamento': l['id'], 'descricao': p} for l in lancamentos for p in l['pendencias']]
    if aviso == SEM_REGRAS: pendencias.insert(0, {'lancamento': None, 'descricao': SEM_REGRAS})
    propostos = [l for l in lancamentos if l['status'] == 'PROPOSTO_PARA_CONFERENCIA']
    return {'contrato': CONTRATO, 'agente': 'CONTABILIDADE/DP', 'empresa': empresa, 'competencia': competencia, 'sol': sol,
            'modo': 'SIMULACAO', 'origem_dp_sha256': hashlib.sha256(json.dumps(dp, sort_keys=True).encode()).hexdigest(),
            'lancamentos': lancamentos, 'documentos_nao_aproveitados': nao_aproveitados, 'pendencias': pendencias,
            'politica_data': {k: pol.get(k) for k in ('aplicavel', 'politica', 'motivo', 'governanca')},
            'resumo': {'propostos': len(propostos), 'incompletos': len(lancamentos) - len(propostos),
                       'sem_data': sum(1 for l in lancamentos if l['natureza'] and not l['data']),
                       'valor_propostos': f"{sum((Decimal(l['valor']) for l in propostos), Decimal('0')):.2f}"},
            'limites': ['Propostas de competência (reconhecimento, retenção, encargo, provisão) para conferência do Supervisor; '
                        'não significa aprovação, escrituração ou liberação para o Domínio.',
                        'Pagamentos de salários e encargos são tratados por Bancos a partir do extrato; LIQUIDO_A_PAGAR não gera lançamento.',
                        'Encargos sobre provisões não são calculados nem presumidos.'] + limites_extra}


def main(argv=None):
    p = argparse.ArgumentParser(description='Contabilidade/DP (SIMULACAO).')
    for n in ('empresa', 'competencia', 'sol', 'dp', 'saida'): p.add_argument('--' + n, required=True)
    a = p.parse_args(argv)
    if not re.fullmatch('[A-Z0-9][A-Z0-9-]*', a.empresa) or not COMPETENCIA.fullmatch(a.competencia):
        print('ERRO: empresa ou competência (AAAA-MM) inválida.', file=sys.stderr); return 2
    try:
        bruto = Path(a.dp).read_bytes()
        r = gerar(a.empresa, a.competencia, a.sol, json.loads(bruto.decode('utf-8')))
    except (ValueError, OSError) as e:   # JSONDecodeError é ValueError
        print(f'ERRO: {e}', file=sys.stderr); return 1
    r['origem_dp_sha256'] = hashlib.sha256(bruto).hexdigest()
    s = Path(a.saida); s.mkdir(parents=True, exist_ok=True)
    (s/'resultado.json').write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__': sys.exit(main())
