"""Classificação e roteamento fictícios: Documentos classifica, Coordenador roteia."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "API-LOCAL"))
import documentos_local
import servidor


def main():
    # Extrato reconhecido pela ESTRUTURA do conteúdo (nome genérico); o nome do arquivo sozinho não classifica (v1.4.1).
    pdf = {"arquivo": "RECEBIDOS/2026-09/documento.pdf", "extensao": ".pdf", "leitura": "EXTRAIDO_PDF", "conteudo": {"paginas": [{"texto":
           "Santander Empresas\nEMPRESA FICTICIA Agência: 1234 Conta: 11111-1\nPeríodos: 01/09/2026 a 30/09/2026\n"
           "20/09/2026 PIX RECEBIDO FICTICIO 50,00 950,00\n10/09/2026 PAGAMENTO FICTICIO -20,00 900,00"}]}}
    so_nome = {"arquivo": "RECEBIDOS/2026-09/extrato-SANTANDER.pdf", "extensao": ".pdf", "leitura": "EXTRAIDO_PDF", "conteudo": {"paginas": [{"texto": "Movimentação bancária"}]}}
    assert not documentos_local.classificar(so_nome).startswith('Extrato')
    xlsx = {"arquivo": "relatorio.xlsx", "extensao": ".xlsx", "leitura": "EXTRAIDO_PLANILHA", "conteudo": {"abas": [{"oculta": False, "linhas": [{"valores": ["Data de Vencimento", "Valor Pago", "Plano de Contas", "Banco", "Empresa CNPJ"]}]}]}}
    folha = {"arquivo": "folha.pdf", "extensao": ".pdf", "conteudo": {"paginas": [{"texto": "HOLERITE SALARIO"}]}}
    nota = {"arquivo": "nf.xml", "extensao": ".xml", "leitura": "EXTRAIDO_NFE", "conteudo": {}}
    amb = {"arquivo": "arquivo.pdf", "extensao": ".pdf", "conteudo": {"paginas": [{"texto": "documento sem natureza definida"}]}}
    assert documentos_local.classificar(pdf) == 'Extrato PDF Santander Empresas (leitura pelo Financeiro)'
    assert documentos_local.encaminhamento(pdf)['area'] == 'FINANCEIRO'
    assert documentos_local.classificar(xlsx) == 'Relatório financeiro de lançamentos'
    assert documentos_local.encaminhamento(xlsx)['copias_suporte'] == ['CONCILIACAO']
    assert documentos_local.encaminhamento(folha)['area'] == 'DP'
    assert documentos_local.encaminhamento(nota)['area'] == 'FISCAL'
    assert documentos_local.encaminhamento(amb)['area'] is None
    assert documentos_local.encaminhamento(pdf)['area'] != 'CONCILIACAO'
    # a classificação não executa agentes; apenas devolve metadados para o Coordenador
    assert documentos_local.encaminhamento(pdf)['situacao'] == 'DISPONIVEL_PARA_ENCAMINHAMENTO'
    with patch.dict(os.environ, {'AGENTES_PRIME_RUNTIME': '/tmp/prime-runtime-ficticio', 'AGENTES_PRIME_MODO_TESTE': '1'}, clear=False):
        assert servidor.pasta_runtime().name == 'prime-runtime-ficticio'
    with patch.dict(os.environ, {'AGENTES_PRIME_RUNTIME': '/tmp/prime-runtime-operacional', 'AGENTES_PRIME_MODO_TESTE': '0', 'AGENTES_PRIME_REGISTRO_SOL': ''}, clear=False):
        try:
            servidor.pasta_runtime()
        except SystemExit as e:
            assert 'temporário recusado' in str(e)
        else:
            raise AssertionError('runtime temporário aceito fora do modo de teste')
    print('10/10 PASS')


if __name__ == '__main__':
    main()
