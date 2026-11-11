"""Recepção e distribuição por área; dados inteiramente fictícios e saídas temporárias."""
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


def texto(t, nome='ficticio.txt'):
    return {'arquivo': nome, 'extensao': '.txt', 'leitura': 'EXTRAIDO_TEXTO',
            'sha256': '0' * 64, 'conteudo': {'texto': t}}


class Triagem(unittest.TestCase):
    def test_extrato_financeiro(self):
        for a in (dict(texto(''), extensao='.ofx'), texto('conta;data;tipo;historico;valor;saldo')):
            self.assertEqual(docs.encaminhamento(a)['area'], 'FINANCEIRO')

    def test_nota_fiscal_com_copia_suporte(self):
        for a in (dict(texto(''), leitura='EXTRAIDO_NFE'), texto('DANFE - documento fictício')):
            e = docs.encaminhamento(a)
            self.assertEqual(e['area'], 'FISCAL'); self.assertEqual(e['copias_suporte'], ['FINANCEIRO'])
            self.assertEqual(e['situacao'], 'DISPONIVEL_PARA_ENCAMINHAMENTO')

    def test_historico_do_extrato_nao_troca_destino_para_dp(self):
        a = texto('Santander Empresas\nAgência: 1234 Conta: 111111\nPeríodo: 01/10/2026 a 31/10/2026\n05/10/2026 PIX RECEBIDO FICTICIO 50,00 950,00\n06/10/2026 TARIFA FICTICIA -5,00 945,00\nPAGAMENTO FOLHA DE PAGAMENTO NOTA FISCAL DE SERVICOS')
        self.assertEqual(docs.encaminhamento(a)['area'], 'FINANCEIRO')

    def test_folha_dp_nao_confunde_com_comprovante(self):
        e = docs.encaminhamento(texto('FOLHA DE PAGAMENTO\nComprovante de salário fictício'))
        self.assertEqual(e['area'], 'DP'); self.assertEqual(e['copias_suporte'], [])

    def test_desconhecido_nao_inventa_area(self):
        e = docs.encaminhamento(texto('Documento sem rótulo identificador'))
        self.assertIsNone(e['area']); self.assertEqual(e['situacao'], 'AGUARDANDO_IDENTIFICACAO')

    def test_comprovante_financeiro(self):
        self.assertEqual(docs.encaminhamento(texto('COMPROVANTE de transferência fictícia'))['area'], 'FINANCEIRO')

    def test_nfse_que_menciona_folha_vai_ao_fiscal(self):
        for t in ('NFS-E - Nota Fiscal de Serviços Eletrônica fictícia\nDiscriminação: processamento da folha de pagamento',
                  'NOTA FISCAL fictícia\nServiço: assessoria em FOLHA DE PAGAMENTO de outubro'):
            e = docs.encaminhamento(texto(t))
            self.assertEqual(e['area'], 'FISCAL', t); self.assertEqual(e['copias_suporte'], ['FINANCEIRO'])

    def test_guia_com_boleto_recibo_ou_comprovante_vai_ao_fiscal_com_copia(self):
        for t in ('DAS - DOCUMENTO DE ARRECADAÇÃO DO SIMPLES NACIONAL fictício\nPagável em boleto bancário',
                  'DARF fictício\nRECIBO do sacado', 'Documento de Arrecadação de Receitas Federais\nCOMPROVANTE de pagamento fictício',
                  'BOLETO\nDOCUMENTO DE ARRECADACAO fictício'):
            e = docs.encaminhamento(texto(t))
            self.assertEqual(e['area'], 'FISCAL', t); self.assertEqual(e['copias_suporte'], ['FINANCEIRO'], t)
            self.assertEqual(e['tipo'], 'Possível guia', t)

    def test_boleto_comum_continua_no_financeiro(self):
        e = docs.encaminhamento(texto('BOLETO fictício de fornecedor\nLinha digitável 0000'))
        self.assertEqual(e['area'], 'FINANCEIRO'); self.assertEqual(e['copias_suporte'], [])

    def test_ambiguidade_real_vai_para_triagem_com_apontamento(self):
        for t in ('HOLERITE fictício\nNOTA FISCAL nº 1', 'DARF fictício\nFOLHA DE PAGAMENTO de outubro'):
            e = docs.encaminhamento(texto(t))
            self.assertIsNone(e['area'], t); self.assertEqual(e['situacao'], 'AGUARDANDO_IDENTIFICACAO')
            self.assertEqual(e['copias_suporte'], []); self.assertTrue(e.get('indicios'), t)
            self.assertIn('não presumid', e['observacao'])
        tarefas = docs.montar_tarefas([{'arquivo': 'x.txt', 'sha256': '1' * 64, 'leitura': 'EXTRAIDO_TEXTO',
                                        'encaminhamento': docs.encaminhamento(texto('HOLERITE\nNOTA FISCAL'))}])
        self.assertEqual(list(tarefas), ['TRIAGEM'])

    def test_financeiro_nao_analisa_folha(self):
        with patch.object(fin, 'cadastro', return_value={'cnpjs': [], 'contas': {}, 'cnpjs_outras_empresas': {}}):
            c = fin.Conferencia('FICTICIA', '2026-10', 'SOL-2099-999999')
        c.carregar([texto('FOLHA DE PAGAMENTO\nRecibo\nValor: 100,00')])
        self.assertEqual(c.documentos, [])
        self.assertEqual(c.ignorados[0]['motivo'], 'DOCUMENTO_DESTINADO_AO_DP')

    def test_inventario_relatorio_e_pendencias_por_area(self):
        ordem = '- Empresa: FICTICIA\n- SOL: SOL-2099-999999\n- Competência: 2026-10\n- Pasta dos documentos (relativa à pasta da empresa): RECEBIDOS/2026-10/TESTE\n'
        arquivos = [texto('FOLHA DE PAGAMENTO', 'folha.txt'), texto('DANFE fictícia', 'nota.txt'),
                    dict(texto('', 'extrato.ofx'), extensao='.ofx')]
        with tempfile.TemporaryDirectory(prefix='prime-triagem-') as tmp, patch.object(docs, 'extrair', return_value={'arquivos': arquivos}):
            r = docs.executar(ordem, tmp)
            d = json.loads((Path(tmp) / 'documentos-local.json').read_text(encoding='utf-8'))
        self.assertEqual([i['encaminhamento']['area'] for i in d['itens']], ['DP', 'FISCAL', 'FINANCEIRO'])
        # DP deixou de ser "área não implementada": documento disponível; o Coordenador decide a execução.
        self.assertEqual(d['pendencias'], [])
        self.assertEqual(d['tarefas_areas']['DP']['estado'], 'PRONTO_PARA_ENCAMINHAMENTO')
        self.assertEqual(d['tarefas_areas']['DP']['documentos'][0]['situacao'], 'DISPONIVEL')
        self.assertEqual(d['tarefas_areas']['CONCILIACAO']['documentos'][0]['papel'], 'COPIA_SUPORTE')   # extrato
        self.assertTrue(any('identificação da empresa' in x for x in d['limitacoes']))   # sem CADASTRO.md
        self.assertIn('→ FINANCEIRO', r['relatorio'])

    # ---- rotas novas (CONTRATO seção 2)
    def test_resumo_da_folha_vai_ao_dp_com_copia_ao_financeiro(self):
        e = docs.encaminhamento(texto('RESUMO DA FOLHA DE PAGAMENTO\nCNPJ: 90.010.010/0001-09\nLIQUIDO A PAGAR: 7.000,00'))
        self.assertEqual((e['area'], e['copias_suporte'], e['situacao']), ('DP', ['FINANCEIRO'], 'DISPONIVEL_PARA_ENCAMINHAMENTO'))

    def test_encargos_e_provisoes_vao_ao_dp(self):
        for t in ('RESUMO DE ENCARGOS DA FOLHA\nFGTS;8.000,00;640,00', 'DEMONSTRATIVO DE PROVISOES DE FERIAS E 13 SALARIO\nTOTAL DAS PROVISOES: 1.666,67'):
            e = docs.encaminhamento(texto(t))
            self.assertEqual((e['area'], e['copias_suporte'], e['situacao']), ('DP', [], 'DISPONIVEL_PARA_ENCAMINHAMENTO'), t)

    def test_precedencia_preservada_para_resumos_de_pessoal(self):
        for t in ('RESUMO DA FOLHA DE PAGAMENTO\nNOTA FISCAL nº 1', 'DARF fictício\nRESUMO DE ENCARGOS DA FOLHA'):
            e = docs.encaminhamento(texto(t))
            self.assertIsNone(e['area'], t); self.assertTrue(e.get('indicios'), t)

    def test_posicao_de_titulos_financeiro_com_copia_conciliacao(self):
        for cab in ('TIPO;POSICAO;DATA_BASE;CONTRAPARTE;CNPJ;TITULO;VENCIMENTO;VALOR', 'tipo;posicao;data_base;contraparte;titulo;valor'):
            e = docs.encaminhamento(texto(cab + '\nPAGAR;INICIAL;30/09/2026;BETA;90.040.040/0001-50;NF 555;05/10/2026;3.000,00', 'p.csv'))
            self.assertEqual((e['area'], e['copias_suporte'], e['tipo']), ('FINANCEIRO', ['CONCILIACAO'], 'Posição de títulos'), cab)

    def test_demonstrativo_de_apuracao_somente_ao_fiscal(self):
        e = docs.encaminhamento(texto('DEMONSTRATIVO DE APURACAO\nISS 10/2026 fictício'))
        self.assertEqual((e['area'], e['copias_suporte']), ('FISCAL', []))

    def test_saldos_de_abertura_e_confirmacao_vao_a_conciliacao(self):
        for t in ('CONTA;DESCRICAO;SALDO;NATUREZA;DATA_BASE;FONTE\n1101;BANCO;40.000,00;D;30/09/2026;BALANCETE',
                  'CONFIRMACAO DE SALDO\nCNPJ DO EMITENTE: 90.040.040/0001-50\nCNPJ DO CLIENTE: 90.010.010/0001-09\nSALDO EM ABERTO: 0,00'):
            e = docs.encaminhamento(texto(t), ['90010010000109'])
            self.assertEqual((e['area'], e['copias_suporte']), ('CONCILIACAO', []), t)

    def test_extratos_ganham_copia_a_conciliacao(self):
        for a in (dict(texto(''), extensao='.ofx'), texto('CONTA;DATA;TIPO;HISTORICO;VALOR;SALDO;IDENTIFICADOR'),
                  texto('Santander Empresas\nAgência: 1234 Conta: 111111\nPeríodo: 01/10/2026 a 31/10/2026\n05/10/2026 PIX RECEBIDO FICTICIO 50,00 950,00\n06/10/2026 TARIFA FICTICIA -5,00 945,00')):  # extrato pela estrutura do conteúdo
            e = docs.encaminhamento(a)
            self.assertEqual((e['area'], e['copias_suporte']), ('FINANCEIRO', ['CONCILIACAO']))

    def test_relacao_com_cabecalho_novo_vai_ao_financeiro(self):
        t = ('TIPO;DATA;FAVORECIDO;CNPJ;VALOR;DOCUMENTOS;TITULO;CONTA;OBRIGACAO_CONTABILIZADA\n'
             'PAGAMENTO;15/10/2026;PREFEITURA FICTICIA;90.060.060/0001-92;500,00;DARF ISS 09/2026;;001-1234-55555-5;SIM')
        e = docs.encaminhamento(texto(t, 'relacao.csv'), ['90010010000109'])
        self.assertEqual((e['area'], e['copias_suporte']), ('FINANCEIRO', []))

    # ---- identificação da empresa pelos CNPJs do documento
    def test_documento_que_nao_identifica_a_empresa_vai_a_triagem(self):
        e = docs.encaminhamento(texto('NOTA FISCAL\nTOMADOR CNPJ: 90.070.070/0001-09\nVALOR: 10,00'), ['90010010000109'])
        self.assertIsNone(e['area']); self.assertEqual(e['situacao'], 'DOCUMENTO_NAO_IDENTIFICA_EMPRESA')
        self.assertIn('documento não identifica esta empresa (CNPJs: 90.070.070/0001-09)', e['observacao'])
        self.assertTrue(e['acao_necessaria'])
        t = docs.montar_tarefas([{'arquivo': 'x.txt', 'sha256': '2' * 64, 'leitura': 'EXTRAIDO_TEXTO', 'encaminhamento': e}])
        self.assertEqual(list(t), ['TRIAGEM'])
        self.assertEqual(t['TRIAGEM']['documentos'][0]['situacao'], 'DOCUMENTO_NAO_IDENTIFICA_EMPRESA')

    def test_documento_com_cnpj_da_empresa_e_distribuido(self):
        e = docs.encaminhamento(texto('NOTA FISCAL\nPRESTADOR CNPJ: 90.040.040/0001-50\nTOMADOR CNPJ: 90.010.010/0001-09'), ['90010010000109'])
        self.assertEqual(e['area'], 'FISCAL')

    def test_sem_cnpj_ou_sem_cadastro_nao_bloqueia(self):
        self.assertEqual(docs.encaminhamento(texto('COMPROVANTE de PIX fictício\nVALOR: 10,00'), ['90010010000109'])['area'], 'FINANCEIRO')
        self.assertEqual(docs.encaminhamento(texto('COMPROVANTE\nCNPJ: 90.070.070/0001-09'))['area'], 'FINANCEIRO')
        # código de barras de 14 dígitos sem rótulo não é CNPJ identificado
        self.assertEqual(docs.encaminhamento(texto('BOLETO\nLinha digitável 90070070000109'), ['90010010000109'])['area'], 'FINANCEIRO')

    def test_extrato_e_planilha_com_cnpj_de_terceiro_nao_sao_afetados(self):
        for a in (texto('CONTA;DATA;TIPO;HISTORICO;VALOR;SALDO\n001-1;01/10/2026;MOVIMENTO;PIX 90.070.070/0001-09;-1,00;1,00'),
                  texto('TIPO;POSICAO;DATA_BASE;CONTRAPARTE;CNPJ;TITULO;VENCIMENTO;VALOR\nPAGAR;FINAL;31/10/2026;OUTRA;90.070.070/0001-09;X;;1,00')):
            self.assertEqual(docs.encaminhamento(a, ['90010010000109'])['area'], 'FINANCEIRO')

    def test_financeiro_usa_copia_do_resumo_da_folha(self):
        with patch.object(fin, 'cadastro', return_value={'cnpjs': ['90010010000109'], 'contas': {}, 'cnpjs_outras_empresas': {}}):
            c = fin.Conferencia('FICTICIA', '2026-10', 'SOL-2099-999999')
        c.carregar([texto('RESUMO DA FOLHA DE PAGAMENTO\nCNPJ: 90.010.010/0001-09\nCOMPETENCIA: 10/2026\n'
                          'NUMERO DO DOCUMENTO: FP-2026-10\nLIQUIDO A PAGAR: 7.000,00'),
                    texto('RESUMO DE ENCARGOS DA FOLHA\nCNPJ: 90.010.010/0001-09', 'encargos.txt')])
        self.assertEqual([(d['tipo'], d['valor'], d['numero']) for d in c.documentos], [('FOLHA', '7000.00', 'FP-2026-10')])
        self.assertEqual(c.ignorados, [{'arquivo': 'encargos.txt', 'motivo': 'DOCUMENTO_DESTINADO_AO_DP'}])


if __name__ == '__main__': unittest.main()
