"""Método documentado por empresa: contexto de conferência, nunca código executável."""
import json
import re
from pathlib import Path


def carregar(base, empresa, cnpjs):
    p = Path(base) / 'PERFIL-FECHAMENTO.json'
    if not p.is_file(): return None
    try:
        if p.is_symlink() or p.stat().st_size > 300_000: raise ValueError('Arquivo de método inválido.')
        d = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(d, dict): raise ValueError('Formato de método inválido.')
        digitos = lambda x: re.sub(r'\D', '', str(x))
        if d.get('contrato') != 'METODO_EMPRESA_V1' or d.get('empresa') != empresa or len(digitos(d.get('cnpj'))) != 14 or digitos(d.get('cnpj')) not in {digitos(c) for c in cnpjs}:
            raise ValueError('Método não corresponde à empresa/CNPJ selecionados.')
        # A presença do perfil não aprova regras nem instrui o executor a rodar agentes futuros.
        return {**d, 'executa_regras': False, 'arquivo_metodo': 'MANUAL-FECHAMENTO.md'}
    except (OSError, ValueError, TypeError) as exc:
        return {'disponivel': False, 'motivo': str(exc), 'executa_regras': False}
