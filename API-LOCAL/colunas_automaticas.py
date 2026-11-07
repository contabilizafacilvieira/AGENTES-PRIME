"""Correspondência de cabeçalhos explícitos; não deduz colunas pelos valores."""
import re
from plano_dominio import chave

ALIASES = {
    'codigo': ['codigo', 'codigo reduzido', 'cod', 'conta reduzida'],
    'classificacao': ['classificacao', 'classificacao contabil'],
    'descricao': ['descricao', 'descricao da conta', 'nome da conta'],
    'grupo': ['grupo', 'grupo contabil'], 'tipo': ['tipo', 'tipo da conta'],
}


def normal(v):
    return re.sub(r'[^A-Z0-9]', '', chave(v))


def reconhecer(linhas, finalidade):
    if finalidade != 'plano':
        return None
    obrigatorios = ['codigo','classificacao','descricao']
    permitidos = obrigatorios + ['grupo','tipo']
    candidatos = []
    for n,r in enumerate(linhas[:20],1):
        mapa = {}
        for k in permitidos:
            cols = [c for c,v in enumerate(r) if normal(v) in {normal(a) for a in ALIASES[k]}]
            if len(cols)>1:
                mapa = {};break
            if cols:
                mapa[k] = cols[0]
        if all(k in mapa for k in obrigatorios):
            candidatos.append({'cabecalho': n, 'mapa': mapa})
    return candidatos[0] if len(candidatos)==1 else None
