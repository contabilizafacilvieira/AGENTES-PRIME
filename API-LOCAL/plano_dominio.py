"""Leitura estrutural da Relação de Contas do Domínio; sem inferir grupos contábeis."""
import re
import unicodedata


def texto(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return '' if v is None else str(v).strip()


def chave(v):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto(v).upper()) if not unicodedata.combining(c))


def reconhecer(linhas, empresa):
    if not any(chave(v) == 'RELACAO DE CONTAS' for r in linhas[:20] for v in r):
        return None
    mapa = None
    cabecalho = None
    identificacoes = []
    for n, r in enumerate(linhas):
        for c, v in enumerate(r):
            if chave(v) in ('C.N.P.J.:', 'CNPJ:', 'C.N.P.J.', 'CNPJ'):
                proximos = [texto(x) for x in r[c+1:] if texto(x)]
                if not proximos:
                    raise ValueError('Relação de Contas: CNPJ do cabeçalho ausente.')
                identificacoes.append(re.sub(r'\D', '', proximos[0]))
        cols = {chave(v): c for c, v in enumerate(r) if texto(v)}
        if all(k in cols for k in ('CODIGO', 'CLASSIFICACAO', 'TIPO', 'DESCRICAO')):
            if mapa is None:
                mapa = [cols[k] for k in ('CODIGO', 'CLASSIFICACAO', 'DESCRICAO', 'TIPO')]
                cabecalho = n
    esperado = re.sub(r'\D', '', empresa.get('cnpj', ''))
    if not identificacoes or any(v != esperado or len(v) != 14 for v in identificacoes):
        raise ValueError('CNPJ da Relação de Contas ausente ou diferente da empresa selecionada. Cadastro preservado.')
    if mapa is None:
        raise ValueError('Relação de Contas sem as colunas Código, Classificação, Tipo e Descrição.')
    resultado = [['codigo', 'classificacao', 'descricao', 'grupo', 'tipo']]
    origens, totais = [], []
    for n, r in enumerate(linhas[cabecalho+1:], cabecalho+2):
        preenchidas = [texto(v) for v in r if texto(v)]
        if not preenchidas:
            continue
        normalizadas = [chave(v) for v in preenchidas]
        if 'TOTAL DE ITENS LISTADOS:' in normalizadas:
            pos = next(c for c,v in enumerate(r) if chave(v) == 'TOTAL DE ITENS LISTADOS:')
            valores = [texto(v) for v in r[pos+1:] if texto(v)]
            if len(valores) != 1 or not re.fullmatch(r'\d+', valores[0]):
                raise ValueError(f'Total de itens inválido na linha {n}.')
            totais.append(int(valores[0]))
            continue
        # Cabeçalhos de página e rodapé são reconhecidos explicitamente; linhas desconhecidas não somem.
        if normalizadas[0] in ('EMPRESA:', 'C.N.P.J.:', 'CNPJ:', 'PERIODO:', 'RELACAO DE CONTAS', 'PAGINA:', 'EMISSAO:', 'HORA:') or normalizadas[0].startswith('SISTEMA LICENCIADO PARA '):
            continue
        if all(k in normalizadas for k in ('CODIGO', 'CLASSIFICACAO', 'TIPO', 'DESCRICAO')):
            continue
        codigo, classificacao, descricao, tipo = [texto(r[c]) if c < len(r) else '' for c in mapa]
        if not re.fullmatch(r'\d+', codigo) or not classificacao or not descricao or tipo.upper() not in ('A', 'S'):
            raise ValueError(f'Relação de Contas, linha {n}: conta ou tipo A/S não reconhecido. Nenhuma linha foi descartada automaticamente.')
        resultado.append([codigo, classificacao, descricao, '', {'A': 'ANALITICA', 'S': 'SINTETICA'}[tipo.upper()]])
        origens.append(n)
    if len(resultado) == 1 or len(resultado) > 10001:
        raise ValueError('Relação de Contas vazia ou acima de 10.000 contas.')
    if totais and any(t != len(origens) for t in totais):
        raise ValueError('O total de itens do relatório não confere com as contas lidas; confira se a exportação está completa.')
    classes = {}
    for c in resultado[1:]:
        classes.setdefault(c[1], []).append(c[0])
    repetidas = [{'classificacao': k, 'codigos': v} for k,v in classes.items() if len(v)>1]
    return resultado, {'formato': 'DOMINIO_RELACAO_CONTAS', 'cnpj': identificacoes[0], 'linhas_origem': origens,
                       'classificacoes_repetidas': repetidas,
                       'total_informado': totais[-1] if totais else None,
                       'aviso': 'Tipos A/S reconhecidos. Grupo contábil não informado pelo relatório; defina e confira antes de usar a conta.'}
