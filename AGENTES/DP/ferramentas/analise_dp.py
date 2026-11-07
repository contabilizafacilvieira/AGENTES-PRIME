"""DP documental local (folha, encargos e provisões). SIMULAÇÃO, sem modelos externos.

Não calcula folha, alíquotas, bases, encargos ou provisões: somente lê os layouts documentados
(AGENTES/DP/PROCEDIMENTO.md) e confere, por igualdade exata (Decimal), as somas declaradas no próprio documento.

Uso:
    .venv/Scripts/python.exe -I AGENTES/DP/ferramentas/analise_dp.py --empresa <EMP> --competencia AAAA-MM --sol <SOL>
        --pasta <pasta do lote> --documentos-local <documentos-local.json> --extracao-local <extracao-local.json> --saida <dir>
Saída: <saida>/resultado.json (contrato DP_LOCAL_V1). Códigos: 0 = resultado gravado (pode conter pendências);
1 = pacote recusado/erro de leitura; 2 = parâmetros inválidos.
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ/'AGENTES/FINANCEIRO/ferramentas'))
from conferencia_financeira import cadastro, receber_pacote_local  # noqa: E402

CONTRATO = 'DP_LOCAL_V1'
DINHEIRO = re.compile(r'(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}')
CNPJ_FMT = re.compile(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}')
NUMERO = re.compile(r'[A-Z0-9][A-Z0-9./-]{0,59}')

# Layouts documentados: título (início da 1ª linha), cabeçalho da tabela, rótulos obrigatórios e opcionais.
LAYOUTS = {
    'RESUMO_FOLHA': {'titulo': 'RESUMO DA FOLHA DE PAGAMENTO', 'cabecalho': 'RUBRICA;TIPO;VALOR',
                     'totais': ('TOTAL DE PROVENTOS', 'TOTAL DE DESCONTOS', 'LIQUIDO A PAGAR'), 'opcionais': ('EMPRESA',)},
    'ENCARGOS_FOLHA': {'titulo': 'RESUMO DE ENCARGOS DA FOLHA', 'cabecalho': 'ENCARGO;BASE;VALOR',
                       'totais': ('TOTAL INSS A RECOLHER', 'TOTAL FGTS A RECOLHER'), 'opcionais': ('EMPRESA',)},
    'PROVISOES': {'titulo': 'DEMONSTRATIVO DE PROVISOES', 'cabecalho': 'PROVISAO;VALOR DO MES',
                  'totais': ('TOTAL DAS PROVISOES',), 'opcionais': ('EMPRESA', 'ENCARGOS SOBRE PROVISOES')},
}
IDENTIFICACAO = ('CNPJ', 'COMPETENCIA', 'NUMERO DO DOCUMENTO')
ENCARGOS_CONHECIDOS = {'INSS EMPRESA': 'ENCARGO_INSS_EMPRESA', 'INSS RAT E TERCEIROS': 'ENCARGO_INSS_EMPRESA',
                       'FGTS': 'ENCARGO_FGTS'}
NATUREZA = {'FOLHA_PROVENTOS': 'RECONHECIMENTO', 'RETENCAO_INSS': 'RETENCAO', 'RETENCAO_IRRF': 'RETENCAO',
            'ENCARGO_INSS_EMPRESA': 'ENCARGO', 'ENCARGO_FGTS': 'ENCARGO', 'PROVISAO_FERIAS': 'PROVISAO',
            'PROVISAO_13': 'PROVISAO', 'LIQUIDO_A_PAGAR': 'OBRIGACAO_A_PAGAR'}
LIMITES = [
    'Conferência documental local somente dos layouts documentados (RESUMO DA FOLHA DE PAGAMENTO, RESUMO DE ENCARGOS DA '
    'FOLHA, DEMONSTRATIVO DE PROVISOES); qualquer outro layout ou linha fora do layout fica pendente.',
    'Não calcula folha, alíquotas, bases, encargos ou provisões: confere apenas as somas declaradas no próprio documento, '
    'por igualdade exata, sem tolerância. Base de encargos é informativa.',
    'Pagamento de salários e encargos é fato do Financeiro (extrato); o DP não registra liquidação. LIQUIDO_A_PAGAR é '
    'informativo para Financeiro/Conciliação e não gera lançamento próprio.',
    'Sem consulta a eSocial, DCTFWeb, FGTS Digital ou outros sistemas; assinatura e autenticidade não verificadas.',
    'Documento com qualquer pendência não é aproveitado (nenhum fato parcial é extraído dele).',
]


def norm(t):
    t = unicodedata.normalize('NFKD', str(t or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', t).strip()


def digitos(t): return re.sub(r'\D', '', str(t or ''))


def dinheiro(t):
    """Valor BR exato (1.234,56) → Decimal; qualquer outro formato → None."""
    t = str(t or '').strip()
    if not DINHEIRO.fullmatch(t): return None
    return Decimal(t.replace('.', '').replace(',', '.'))


def s(v): return None if v is None else f'{v:.2f}'


def periodo(t):
    t = str(t or '').strip()
    m = re.fullmatch(r'(0[1-9]|1[0-2])/(20\d{2})', t)
    if m: return f'{m.group(2)}-{m.group(1)}'
    return t if re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', t) else None


def texto(a):
    c = a.get('conteudo') or {}
    if a.get('leitura') == 'EXTRAIDO_PLANILHA':
        return '\n'.join(';'.join('' if v is None else str(v) for v in l.get('valores', []))
                         for aba in c.get('abas', []) if not aba.get('oculta') for l in aba.get('linhas', []))
    return c.get('texto') or '\n'.join(p.get('texto', '') for p in c.get('paginas', []))


def id_documento(a):
    return 'DPD-' + hashlib.sha256(f"{a['arquivo']}|{a['sha256']}".encode()).hexdigest()[:12].upper()


def ler_layout(t):
    """(tipo, rotulos{rotulo:[valores]}, linhas_tabela[[celulas]], problemas[]). tipo None = não reconhecido."""
    linhas = [re.sub(r'\s*;\s*', ';', norm(l)) for l in t.splitlines()]
    linhas = [l.strip(';') if set(l) <= {';'} else l for l in linhas]
    linhas = [l for l in linhas if l]
    if not linhas: return None, {}, [], ['Documento sem texto legível.']
    candidatos = [k for k, v in LAYOUTS.items() if linhas[0].startswith(v['titulo'])]
    if len(candidatos) != 1: return None, {}, [], []
    tipo = candidatos[0]; lay = LAYOUTS[tipo]
    titulos = [l for l in linhas[1:] if any(l.startswith(v['titulo']) for v in LAYOUTS.values())]
    problemas = ['Mais de um demonstrativo no mesmo arquivo; separar antes da análise.'] if titulos else []
    permitidos = set(IDENTIFICACAO) | set(lay['totais']) | set(lay['opcionais'])
    rotulos, tabela, dentro = {}, [], False
    for l in linhas[1:]:
        if l == lay['cabecalho']:
            if dentro or tabela: problemas.append('Cabeçalho da tabela repetido; layout não reconhecido.')
            dentro = True; continue
        m = re.fullmatch(r'([A-Z0-9 /]+?)\s*:\s*(.*)', l)
        if m and m.group(1) in permitidos:
            rotulos.setdefault(m.group(1), []).append(m.group(2).strip()); continue
        if dentro and ';' in l and ':' not in l:
            tabela.append(l.split(';')); continue
        problemas.append(f'Linha fora do layout documentado: "{l[:80]}".')
    if not dentro: problemas.append(f'Cabeçalho da tabela "{lay["cabecalho"]}" ausente.')
    return tipo, rotulos, tabela, problemas


def rotulo_unico(rotulos, nome, pend):
    vals = set(rotulos.get(nome, []))
    if not vals: return None
    if len(vals) > 1: pend(f'Rótulo "{nome}" repetido com valores divergentes; nenhum valor escolhido.'); return None
    return vals.pop()


def analisar_folha(d, tabela, totais, pend):
    proventos, descontos, retencoes = Decimal('0'), Decimal('0'), {}
    for linha in tabela:
        if len(linha) != 3 or not linha[0] or dinheiro(linha[2]) is None or linha[1] not in ('PROVENTO', 'DESCONTO'):
            pend(f'Linha da tabela de rubricas fora do layout: "{";".join(linha)[:80]}".'); continue
        rubrica, tipo, v = linha[0], linha[1], dinheiro(linha[2])
        d['rubricas'].append({'rubrica': rubrica, 'tipo': tipo, 'valor': s(v)})
        if tipo == 'PROVENTO': proventos += v; continue
        descontos += v
        inss, irrf = 'INSS' in rubrica, 'IRRF' in rubrica
        if inss and irrf: pend(f'Rubrica de desconto "{rubrica}" ambígua (INSS e IRRF); nenhum evento atribuído.')
        elif inss or irrf:
            ev = 'RETENCAO_INSS' if inss else 'RETENCAO_IRRF'
            r = retencoes.setdefault(ev, {'valor': Decimal('0'), 'rubricas': []}); r['valor'] += v; r['rubricas'].append(rubrica)
        else: pend(f'Rubrica de desconto "{rubrica}" não reconhecida (somente INSS/IRRF); sem evento, documento não aproveitado.')
    tp, td, liq = (totais.get(k) for k in ('TOTAL DE PROVENTOS', 'TOTAL DE DESCONTOS', 'LIQUIDO A PAGAR'))
    if tp is not None and proventos != tp: pend(f'Soma dos proventos ({s(proventos)}) difere do TOTAL DE PROVENTOS ({s(tp)}).')
    if td is not None and descontos != td: pend(f'Soma dos descontos ({s(descontos)}) difere do TOTAL DE DESCONTOS ({s(td)}).')
    if None not in (tp, td, liq) and tp - td != liq:
        pend(f'TOTAL DE PROVENTOS − TOTAL DE DESCONTOS ({s(tp - td)}) difere do LIQUIDO A PAGAR ({s(liq)}).')
    if tp is not None and tp <= 0: pend('Total de proventos não positivo.')
    if liq is not None and liq < 0: pend('Líquido a pagar negativo.')
    fatos = [('FOLHA_PROVENTOS', tp, {'rotulo': 'TOTAL DE PROVENTOS',
                                      'rubricas': [r['rubrica'] for r in d['rubricas'] if r['tipo'] == 'PROVENTO']})]
    fatos += [(ev, r['valor'], {'rubricas': r['rubricas']}) for ev, r in sorted(retencoes.items())]
    fatos.append(('LIQUIDO_A_PAGAR', liq, {'rotulo': 'LIQUIDO A PAGAR', 'gera_lancamento': False}))
    return fatos, retencoes


def analisar_encargos(d, tabela, totais, pend):
    vistos = {}
    for linha in tabela:
        base = dinheiro(linha[1]) if len(linha) == 3 and linha[1] else None
        if (len(linha) != 3 or dinheiro(linha[2]) is None or (linha[1] and base is None)):
            pend(f'Linha da tabela de encargos fora do layout: "{";".join(linha)[:80]}".'); continue
        nome, v = linha[0], dinheiro(linha[2])
        d['rubricas'].append({'rubrica': nome, 'base_informada': s(base), 'valor': s(v)})
        if nome not in ENCARGOS_CONHECIDOS: pend(f'Encargo "{nome}" não reconhecido; sem evento, documento não aproveitado.'); continue
        if nome in vistos: pend(f'Encargo "{nome}" repetido no demonstrativo; nenhum valor escolhido.'); continue
        vistos[nome] = v
    inss_empresa = [n for n in ('INSS EMPRESA', 'INSS RAT E TERCEIROS') if n in vistos]
    fgts = vistos.get('FGTS', Decimal('0'))
    tf = totais.get('TOTAL FGTS A RECOLHER')
    if tf is not None and tf != fgts:
        pend(f'TOTAL FGTS A RECOLHER ({s(tf)}) difere da linha FGTS ({s(fgts) if "FGTS" in vistos else "ausente"}).')
    d['_inss_empresa'] = sum((vistos[n] for n in inss_empresa), Decimal('0'))
    return [('ENCARGO_INSS_EMPRESA', d['_inss_empresa'], {'rubricas': inss_empresa}),
            ('ENCARGO_FGTS', vistos.get('FGTS'), {'rubricas': ['FGTS'] if 'FGTS' in vistos else []})]


def analisar_provisoes(d, tabela, totais, rotulos, pend, limites):
    vistos, soma = {}, Decimal('0')
    for linha in tabela:
        if len(linha) != 2 or not linha[0] or dinheiro(linha[1]) is None:
            pend(f'Linha da tabela de provisões fora do layout: "{";".join(linha)[:80]}".'); continue
        nome, v = linha[0], dinheiro(linha[1]); soma += v
        d['rubricas'].append({'rubrica': nome, 'valor': s(v)})
        ev = 'PROVISAO_FERIAS' if nome.startswith('FERIAS') else 'PROVISAO_13' if re.match(r'13(?:O|º)?\s*SALARIO', nome) else None
        if not ev: pend(f'Provisão "{nome}" não reconhecida (férias/13º salário); documento não aproveitado.'); continue
        if ev in vistos: pend(f'Provisão {ev} repetida no demonstrativo; nenhum valor escolhido.'); continue
        vistos[ev] = (v, nome)
    tt = totais.get('TOTAL DAS PROVISOES')
    if tt is not None and tt != soma: pend(f'Soma das provisões ({s(soma)}) difere do TOTAL DAS PROVISOES ({s(tt)}).')
    enc = rotulo_unico(rotulos, 'ENCARGOS SOBRE PROVISOES', pend)
    if enc is None or enc in ('NAO INFORMADO', 'NAO INFORMADOS'):
        limites.append(f'Encargos sobre provisões não informados em {d["arquivo"]}; não foram calculados nem presumidos.')
    else:
        pend('Encargos sobre provisões informados sem evento/regra definidos; documento não aproveitado até definição do Supervisor.')
    return [(ev, v, {'rubricas': [nome]}) for ev, (v, nome) in sorted(vistos.items())]


def analisar(empresa, competencia, sol, arquivos, cnpjs):
    cnpjs = {digitos(c) for c in cnpjs}; documentos = []; limites = list(LIMITES); brutos = {}

    def pend_de(d):
        def pend(t):
            if t not in d['pendencias']: d['pendencias'].append(t)
        return pend

    for a in arquivos:
        c = a.get('conteudo') or {}
        d = {'id': id_documento(a), 'arquivo': a['arquivo'], 'sha256': a['sha256'], 'tipo': 'NAO_RECONHECIDO',
             'competencia': None, 'cnpj': None, 'numero': None, 'rubricas': [], 'totais': {}, 'pendencias': [],
             'elegivel_contabilidade': False}
        pend = pend_de(d); documentos.append(d)
        if (not str(a.get('leitura', '')).startswith('EXTRAIDO_') or c.get('requer_conferencia_ocr')
                or c.get('leitura_incompleta')):
            pend('Leitura pendente, protegida, parcial ou OCR duvidoso; conferir o original. Nenhum valor aproveitado.'); continue
        if a.get('leitura') == 'EXTRAIDO_NFE':
            pend('Documento fiscal estruturado (NF-e) não é layout de DP; análise manual necessária.'); continue
        tipo, rotulos, tabela, problemas = ler_layout(texto(a))
        if tipo is None:
            for p in problemas: pend(p)
            pend('Layout de DP não reconhecido; análise manual necessária. Não inferir valores pelo nome do arquivo.'); continue
        d['tipo'] = tipo
        for p in problemas: pend(p)
        cnpj = rotulo_unico(rotulos, 'CNPJ', pend); comp = rotulo_unico(rotulos, 'COMPETENCIA', pend)
        numero = rotulo_unico(rotulos, 'NUMERO DO DOCUMENTO', pend)
        if cnpj is None: pend('CNPJ não identificado de forma unívoca.')
        elif not CNPJ_FMT.fullmatch(cnpj): pend(f'CNPJ "{cnpj}" fora do formato.')
        else: d['cnpj'] = digitos(cnpj)
        d['competencia'] = periodo(comp)
        if d['competencia'] is None: pend('Competência explícita (MM/AAAA) ausente ou inválida.')
        elif d['competencia'] != competencia: pend('Competência do documento distinta da SOL; documento não aproveitado neste mês.')
        if numero and NUMERO.fullmatch(numero): d['numero'] = numero
        else: pend('NUMERO DO DOCUMENTO ausente ou inválido.')
        if d['cnpj'] and d['cnpj'] not in cnpjs: pend(f'CNPJ {d["cnpj"]} não pertence ao cadastro desta empresa; documento isolado.')
        totais = {}
        for k in LAYOUTS[tipo]['totais']:
            v = rotulo_unico(rotulos, k, pend)
            if v is None: pend(f'Total "{k}" ausente.'); continue
            if dinheiro(v) is None: pend(f'Total "{k}" com valor fora do formato ("{v[:30]}").'); continue
            totais[k] = dinheiro(v)
        d['totais'] = {k: s(v) for k, v in totais.items()}
        if not tabela: pend('Tabela do demonstrativo sem linhas.')
        if tipo == 'RESUMO_FOLHA': fatos, ret = analisar_folha(d, tabela, totais, pend); d['_retencao_inss'] = ret.get('RETENCAO_INSS', {}).get('valor', Decimal('0'))
        elif tipo == 'ENCARGOS_FOLHA': fatos = analisar_encargos(d, tabela, totais, pend)
        else: fatos = analisar_provisoes(d, tabela, totais, rotulos, pend, limites)
        d['_totais'] = totais; brutos[d['id']] = fatos

    # Duplicidades: cópia idêntica ou mesmo número com conteúdo diferente → nenhum aproveitado.
    por_sha, por_numero, por_periodo = {}, {}, {}
    for d in documentos:
        por_sha.setdefault(d['sha256'], []).append(d)
        if d['tipo'] != 'NAO_RECONHECIDO' and d['numero']: por_numero.setdefault((d['tipo'], d['numero']), []).append(d)
        if d['tipo'] != 'NAO_RECONHECIDO' and d['cnpj'] and d['competencia']:
            por_periodo.setdefault((d['tipo'], d['cnpj'], d['competencia']), []).append(d)
    for g in por_sha.values():
        if len(g) > 1:
            for d in g: pend_de(d)('Cópia idêntica de outro arquivo do lote (' + ', '.join(o['arquivo'] for o in g if o is not d)
                                   + '); nenhuma cópia aproveitada.')
    for g in por_numero.values():
        if len({d['sha256'] for d in g}) > 1:
            for d in g: pend_de(d)('Mesmo NUMERO DO DOCUMENTO com conteúdo diferente em outro arquivo; nenhuma versão escolhida.')
    for g in por_periodo.values():
        if len({d['numero'] for d in g}) > 1:
            for d in g: pend_de(d)('Mais de um demonstrativo do mesmo tipo, CNPJ e competência; nenhuma versão escolhida.')

    # Encargos: INSS a recolher = INSS EMPRESA + RAT E TERCEIROS + RETENCAO_INSS da folha da mesma competência.
    for d in documentos:
        if d['tipo'] != 'ENCARGOS_FOLHA' or d['pendencias']: continue
        folhas = [f for f in documentos if f['tipo'] == 'RESUMO_FOLHA' and f['cnpj'] == d['cnpj'] and f['competencia'] == d['competencia']]
        ti = d['_totais'].get('TOTAL INSS A RECOLHER')
        if not folhas: pend_de(d)('Resumo da folha da mesma competência não recebido; TOTAL INSS A RECOLHER não conferível.')
        elif len(folhas) > 1 or folhas[0]['pendencias']:
            pend_de(d)('Resumo da folha da mesma competência com pendência ou não único; TOTAL INSS A RECOLHER não conferível.')
        elif ti != d['_inss_empresa'] + folhas[0]['_retencao_inss']:
            pend_de(d)(f'TOTAL INSS A RECOLHER ({s(ti)}) difere de INSS EMPRESA + RAT E TERCEIROS ({s(d["_inss_empresa"])}) '
                       f'+ INSS retido na folha ({s(folhas[0]["_retencao_inss"])}).')

    fatos, pendencias = [], []
    for d in documentos:
        d['elegivel_contabilidade'] = d['tipo'] != 'NAO_RECONHECIDO' and not d['pendencias']
        if d['elegivel_contabilidade']:
            for ev, v, origem in brutos.get(d['id'], []):
                if v is None or v <= 0: continue
                fatos.append({'id': d['id'] + '-' + ev, 'evento': ev, 'natureza': NATUREZA[ev], 'valor': s(v),
                              'competencia': d['competencia'], 'documento': d['id'], 'arquivo': d['arquivo'],
                              'sha256': d['sha256'], 'origem': dict(origem, tipo_documento=d['tipo'], numero=d['numero'])})
        for k in [k for k in d if k.startswith('_')]: del d[k]
        pendencias.extend({'documento': d['id'], 'arquivo': d['arquivo'], 'descricao': p} for p in d['pendencias'])
    if not documentos:
        pendencias.append({'documento': None, 'arquivo': None, 'descricao': 'Nenhum documento de DP recebido no pacote desta SOL.'})
    return {'contrato': CONTRATO, 'agente': 'DP', 'empresa': empresa, 'competencia': competencia, 'sol': sol, 'modo': 'SIMULACAO',
            'documentos': documentos, 'fatos': fatos, 'pendencias': pendencias, 'limites': list(dict.fromkeys(limites)),
            'resumo': {'documentos': len(documentos), 'aptos': sum(d['elegivel_contabilidade'] for d in documentos),
                       'fatos': len(fatos), 'pendencias': len(pendencias)}}


def main(argv=None):
    p = argparse.ArgumentParser(description='DP documental local (SIMULACAO).')
    for a in ('empresa', 'competencia', 'sol', 'pasta', 'documentos-local', 'extracao-local', 'saida'): p.add_argument('--' + a, required=True)
    a = p.parse_args(argv)
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]*', a.empresa) or not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', a.competencia):
        print('ERRO: empresa ou competência (AAAA-MM) inválida.', file=sys.stderr); return 2
    try:
        arquivos, _ = receber_pacote_local(a.empresa, a.competencia, a.sol, a.pasta, a.documentos_local, a.extracao_local,
                                           area='DP', exigir_hash=True)
        r = analisar(a.empresa, a.competencia, a.sol, arquivos, cadastro(a.empresa)['cnpjs'])
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print(f'ERRO: pacote de DP recusado: {e}', file=sys.stderr); return 1
    saida = Path(a.saida); saida.mkdir(parents=True, exist_ok=True)
    (saida/'resultado.json').write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__': sys.exit(main())
