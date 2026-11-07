"""Conciliação (Agente Conciliador) - código local, determinístico, SEM modelo de linguagem. SIMULAÇÃO.

Uso (chamado pelo Coordenador/servidor depois de todas as demais etapas do plano; a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I AGENTES/CONCILIACAO/ferramentas/conciliacao.py --empresa <EMP> --sol <SOL>
        --competencia AAAA-MM --entradas <entradas.json> --saida <pasta>

Procedimento: AGENTES/CONCILIACAO/PROCEDIMENTO.md. Executa as verificações A–E sobre os resultados recebidos:
  A integridade/origem dos resultados e do pacote; B cada lançamento proposto; C bancos e posições;
  D folha, provisões e tributos; E confirmações de terceiros.
Não corrige, não cria tolerância (igualdade exata com Decimal), não aprova, não escritura, não libera.
Verificação não executada nunca aparece como CONFERIDO. Cada verificação informa contra o que foi feita: DOCUMENTO_EXTERNO
(extrato, confirmação de terceiro), CONTROLE_INTERNO (demonstrativos, posições, cadastro, plano) ou CONSISTENCIA_SISTEMA
(resultados produzidos pelo próprio sistema). NAO_APLICAVEL só com justificativa pela natureza do item ou por regra documentada
da empresa; quando nem documentos nem regras permitem saber se o item é exigido, o resultado é NAO_DETERMINADO, com a pergunta
ao Supervisor, e o fechamento não é integral.
Saída: <saida>/resultado.json (CONCILIACAO_V1). Códigos: 0 = ok | 2 = parâmetros/entradas inválidos.
"""

import argparse
import calendar
import datetime as dt
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / 'AGENTES' / 'FINANCEIRO' / 'ferramentas'))
sys.path.insert(0, str(RAIZ / 'AGENTES' / 'CONTABILIDADE' / 'BANCOS' / 'ferramentas'))
import conferencia_financeira as cf  # noqa: E402
from lancamentos_bancarios import tabela_md, chave_conta, norm, digitos  # noqa: E402
sys.path.insert(0, str(RAIZ / 'AGENTES' / 'CONTABILIDADE'))
import governanca_regras as gov  # noqa: E402

CONTRATO = 'CONCILIACAO_V1'
VERSAO = '1.0'
PROCEDIMENTO = 'AGENTES/CONCILIACAO/PROCEDIMENTO.md v1.0'
ZERO = Decimal('0.00')
ETAPAS = ('FINANCEIRO', 'BANCOS', 'DP', 'CONTABILIDADE_DP', 'FISCAL', 'CONTABILIDADE_FISCAL')
# identidade esperada de cada resultado (contrato e/ou agente)
IDENTIDADE = {'FINANCEIRO': (None, 'FINANCEIRO'), 'BANCOS': (None, 'CONTABILIDADE/BANCOS'),
              'DP': ('DP_LOCAL_V1', 'DP'), 'CONTABILIDADE_DP': ('CONTABILIDADE_DP_V1', 'CONTABILIDADE/DP'),
              'FISCAL': ('FISCAL_LOCAL_V1', 'FISCAL'), 'CONTABILIDADE_FISCAL': ('CONTABILIDADE_FISCAL_V1', 'CONTABILIDADE/FISCAL')}
PROPOSTOS = {'PROPOSTO', 'PROPOSTO_PARA_CONFERENCIA'}
# grupos exigidos por natureza (Bancos: contrapartida; Fiscal/DP: débito, crédito)
GRUPOS_BANCOS = {'LIQUIDACAO_OBRIGACAO': {'PASSIVO'}, 'DESPESA': {'DESPESA', 'CUSTO'}, 'RECEBIMENTO': {'ATIVO'},
                 'RECEITA': {'RECEITA'}, 'ADIANTAMENTO_FORNECEDOR': {'ATIVO'}, 'ADIANTAMENTO_CLIENTE': {'PASSIVO'}}
GRUPOS_FISCAL = {'RECEITA_SERVICOS': ({'ATIVO'}, {'RECEITA'}), 'ISS': ({'DESPESA', 'RECEITA'}, {'PASSIVO'}),
                 'IRPJ': ({'DESPESA'}, {'PASSIVO'}), 'CSLL': ({'DESPESA'}, {'PASSIVO'}),
                 'PIS': ({'DESPESA', 'RECEITA'}, {'PASSIVO'}), 'COFINS': ({'DESPESA', 'RECEITA'}, {'PASSIVO'})}
_DC = ({'DESPESA', 'CUSTO'}, {'PASSIVO'})
GRUPOS_DP = {'FOLHA_PROVENTOS': _DC, 'ENCARGO_INSS_EMPRESA': _DC, 'ENCARGO_FGTS': _DC, 'PROVISAO_FERIAS': _DC,
             'PROVISAO_13': _DC, 'RETENCAO_INSS': ({'PASSIVO'}, {'PASSIVO'}), 'RETENCAO_IRRF': ({'PASSIVO'}, {'PASSIVO'})}
EVENTOS_DP = ('FOLHA_PROVENTOS', 'RETENCAO_INSS', 'RETENCAO_IRRF', 'ENCARGO_INSS_EMPRESA', 'ENCARGO_FGTS',
              'PROVISAO_FERIAS', 'PROVISAO_13')
RESULTADOS = ('CONFERIDO', 'DIVERGENTE', 'PENDENTE', 'NAO_APLICAVEL', 'NAO_DETERMINADO')
# categoria da evidência de cada fonte (sem pontuação: só identifica contra o que a verificação foi feita)
CATEGORIA_NATUREZA = {'EXTERNA': 'DOCUMENTO_EXTERNO', 'INTERNA': 'CONTROLE_INTERNO', 'RESULTADO': 'CONSISTENCIA_SISTEMA'}
TIPOS_SISTEMA = {'REGISTRO_COORDENADOR', 'PACOTE_DOCUMENTOS', 'RESULTADO_AGENTE', 'LANCAMENTO_PROPOSTO'}
ACAO_PADRAO = {
    'CONFERIDO': 'Nenhuma correção apontada; segue para a conferência do Supervisor (não é aprovação).',
    'NAO_APLICAVEL': 'Nenhuma.',
}


def dec(v):
    """Decimal exato com 2 casas a partir de '1234.56' (resultados) ou '1.234,56' (documentos). None se inválido."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, Decimal):
        return v.quantize(Decimal('0.01'))
    return cf.valor(v)


def f2(v):
    return None if v is None else f'{v:.2f}'


def saldo_txt(v):
    """Saldo assinado (devedor positivo) em texto com natureza."""
    if v is None:
        return None
    return '0.00' if v == 0 else f"{abs(v):.2f} {'D' if v > 0 else 'C'}"


def chave_id(*partes):
    return '-'.join(re.sub(r'[^A-Z0-9]+', '-', norm(p)).strip('-') or 'X' for p in partes)


def sha_arquivo(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def ultimo_dia(competencia):
    a, m = map(int, competencia.split('-'))
    return dt.date(a, m, calendar.monthrange(a, m)[1])


def dia_anterior(competencia):
    a, m = map(int, competencia.split('-'))
    return dt.date(a, m, 1) - dt.timedelta(days=1)


def resolver(caminho):
    if not caminho:
        return None
    p = Path(caminho)
    return p if p.is_absolute() else RAIZ / p


def texto_arquivo(a):
    c = a.get('conteudo') or {}
    return c.get('texto') or '\n'.join(p.get('texto', '') for p in c.get('paginas', []))


class Conciliacao:
    def __init__(self, entradas: dict):
        self.e = entradas
        self.empresa, self.sol, self.competencia = entradas.get('empresa'), entradas.get('sol'), entradas.get('competencia')
        self.verificacoes, self.nao_executadas, self.observacoes = [], [], []
        self.res, self.estado, self.versoes = {}, {}, {}
        self.ids = {}
        self.perguntas, self.exig_dados, self.exig_usadas, self.base_regras = [], {}, {}, None

    # ------------------------------------------------------------------ registro de verificações
    def v(self, vid, grupo, titulo, resultado, justificativa, area, item=None, contas=(), lancamentos=(), fontes=(),
          esperado=None, encontrado=None, diferenca=None, acao=None):
        assert resultado in RESULTADOS
        fontes = [dict(f) for f in fontes if f]
        for f in fontes:
            f['categoria'] = 'CONSISTENCIA_SISTEMA' if f.get('tipo') in TIPOS_SISTEMA else CATEGORIA_NATUREZA.get(f.get('natureza'), 'CONTROLE_INTERNO')
        if resultado == 'CONFERIDO' and not fontes:
            raise AssertionError(f'{vid}: CONFERIDO sem fonte')
        n = self.ids.get(vid, 0) + 1
        self.ids[vid] = n
        if n > 1:
            vid = f'{vid}-{n}'
        if acao is None:
            acao = ACAO_PADRAO.get(resultado) or (
                f'Comunicar ao Coordenador Geral e devolver à área {area} para correção, com rastreabilidade.' if resultado == 'DIVERGENTE'
                else f'Providenciar o que falta (área {area}) e reexecutar a Conciliação; nada foi presumido.')
        cats = {f['categoria'] for f in fontes}
        tipo = next((c for c in ('DOCUMENTO_EXTERNO', 'CONTROLE_INTERNO', 'CONSISTENCIA_SISTEMA') if c in cats), 'NENHUMA')
        self.verificacoes.append({
            'id': vid, 'grupo': grupo, 'titulo': titulo, 'item': item, 'contas': sorted(set(c for c in contas if c)),
            'lancamentos': list(dict.fromkeys(l for l in lancamentos if l)), 'fontes': fontes,
            'valores': {'esperado': esperado, 'encontrado': encontrado, 'diferenca': diferenca},
            'resultado': resultado, 'evidencia': tipo, 'evidencias': sorted(cats),
            'justificativa': justificativa, 'area_responsavel': area, 'acao': acao})

    def indeterminado(self, vid, grupo, titulo, pergunta, area, item=None, fontes=()):
        """Exigência do item não determinável pelos documentos nem pelas regras da empresa: limitação + pergunta ao Supervisor."""
        self.perguntas.append({'verificacao': vid, 'pergunta': pergunta})
        self.v(vid, grupo, titulo, 'NAO_DETERMINADO', 'Exigência não determinada: ' + pergunta, area, item=item, fontes=fontes,
               acao='Supervisor: definir a exigência na regra da empresa (REGRAS-CONCILIACAO.json, com confirmação) e reexecutar a Conciliação.')

    def exigencia(self, chave):
        """('EXIGIDA'|'DISPENSADA'|None, justificativa ou motivo da indeterminação). Só regra aplicável (governança) vale."""
        regra = (self.exig_dados.get('exigencias') or {}).get(chave)
        if regra is None:
            return None, f'a regra {chave} não está definida para esta empresa'
        av = gov.avaliar(regra, 'CONCILIACAO', self.empresa, chave, self.competencia, self.base_regras)
        if not av['aplicavel']:
            return None, av['motivo']
        ex = str(regra.get('exigencia') or '').upper()
        if ex not in ('EXIGIDA', 'DISPENSADA'):
            return None, f'{chave}: exigência "{ex}" inválida (use EXIGIDA ou DISPENSADA)'
        if ex == 'DISPENSADA' and not str(regra.get('justificativa') or '').strip():
            return None, f'{chave}: dispensa sem justificativa documentada não é aceita'
        self.exig_usadas[chave] = {'exigencia': ex, 'justificativa': regra.get('justificativa'), 'governanca': av['governanca']}
        return ex, str(regra.get('justificativa') or '')

    def fonte_regra(self, chave):
        return {'referencia': f'REGRAS-CONCILIACAO.json ({chave})', 'tipo': 'REGRA_EMPRESA', 'natureza': 'INTERNA'}

    def nao_exec(self, grupo, item, motivo):
        if not any(x['grupo'] == grupo and x['item'] == item for x in self.nao_executadas):
            self.nao_executadas.append({'grupo': grupo, 'item': item, 'motivo': motivo})

    # ------------------------------------------------------------------ disponibilidade das etapas
    def disponivel(self, *etapas):
        """None se todas as etapas planejadas estão íntegras e concluídas; senão o motivo. Fora do plano não bloqueia."""
        motivos = [f"{et}: {self.estado[et]['motivo']}" for et in etapas
                   if self.estado.get(et, {}).get('estado') == 'INDISPONIVEL']
        return '; '.join(motivos) or None

    def planejada(self, etapa):
        return self.estado.get(etapa, {}).get('estado') != 'FORA_DO_PLANO'

    # ------------------------------------------------------------------ A: integridade e origem
    def grupo_a(self):
        etapas = self.e.get('etapas') or {}
        for et in ETAPAS:
            info = etapas.get(et)
            area = et
            if info is None or str(info.get('situacao') or '').upper() in ('NAO_PLANEJADA', 'FORA_DO_PLANO'):
                self.estado[et] = {'estado': 'FORA_DO_PLANO', 'motivo': 'etapa não integra o plano desta SOL'}
                self.v(f'CONC-A-SITUACAO-{et}', 'A', f'Situação da etapa {et}', 'NAO_APLICAVEL',
                       'Etapa não integra o plano desta SOL (não há documentos/resultado dessa área); verificações dela não se aplicam.',
                       area, item=et)
                continue
            situacao = str(info.get('situacao') or '').upper()
            caminho = resolver(info.get('resultado'))
            registrado = str(info.get('sha256_registrado') or '').lower() or None
            fonte_reg = {'referencia': f'registro da SOL (plano_etapas/{et})', 'tipo': 'REGISTRO_COORDENADOR', 'natureza': 'INTERNA'}
            if situacao != 'CONCLUIDA':
                motivo = f'etapa {situacao or "SEM_SITUACAO"}'
                self.estado[et] = {'estado': 'INDISPONIVEL', 'motivo': motivo}
                self.v(f'CONC-A-SITUACAO-{et}', 'A', f'Situação da etapa {et}', 'PENDENTE',
                       f'Etapa {et} não concluída ({situacao or "sem situação"}); seus resultados não foram usados e as verificações '
                       'que dependem dela ficam PENDENTES (alcance parcial).', area, item=et, fontes=[fonte_reg],
                       acao=f'Retomar a etapa {et} pelo Coordenador (com justificativa) e reexecutar a Conciliação.')
                self.nao_exec('A', et, motivo)
                continue
            self.v(f'CONC-A-SITUACAO-{et}', 'A', f'Situação da etapa {et}', 'CONFERIDO',
                   f'Etapa {et} registrada como CONCLUIDA no plano da SOL.', area, item=et, fontes=[fonte_reg])
            # hash do arquivo de resultado × registrado
            if not caminho or not caminho.is_file():
                self.estado[et] = {'estado': 'INDISPONIVEL', 'motivo': 'arquivo de resultado ausente'}
                self.v(f'CONC-A-HASH-{et}', 'A', f'Integridade do resultado {et}', 'PENDENTE',
                       'Arquivo de resultado não localizado; integridade não verificável e dados não usados.', area, item=et,
                       fontes=[fonte_reg])
                self.v(f'CONC-A-ORIGEM-{et}', 'A', f'Origem do resultado {et}', 'PENDENTE',
                       'Arquivo de resultado não localizado; empresa/SOL/competência não verificáveis.', area, item=et)
                continue
            atual = sha_arquivo(caminho)
            self.versoes[et] = atual
            fonte_res = {'referencia': f'{et}: {caminho.name} (sha256 {atual[:16]}…)', 'tipo': 'RESULTADO_AGENTE', 'natureza': 'RESULTADO'}
            if not registrado:
                self.estado[et] = {'estado': 'INDISPONIVEL', 'motivo': 'sha256 não registrado pelo Coordenador'}
                self.v(f'CONC-A-HASH-{et}', 'A', f'Integridade do resultado {et}', 'PENDENTE',
                       'Hash do resultado não registrado pelo Coordenador: não é possível afirmar que o arquivo é o entregue pela etapa.',
                       area, item=et, fontes=[fonte_res], encontrado=atual)
            elif atual != registrado:
                self.estado[et] = {'estado': 'INDISPONIVEL', 'motivo': 'resultado alterado após o registro (sha256 divergente)'}
                self.v(f'CONC-A-HASH-{et}', 'A', f'Integridade do resultado {et}', 'DIVERGENTE',
                       'sha256 do arquivo de resultado difere do registrado pelo Coordenador: resultado alterado depois da entrega. '
                       'Os dados desse resultado NÃO foram usados.', area, item=et, fontes=[fonte_reg, fonte_res],
                       esperado=registrado, encontrado=atual)
            else:
                self.v(f'CONC-A-HASH-{et}', 'A', f'Integridade do resultado {et}', 'CONFERIDO',
                       'sha256 do arquivo de resultado igual ao registrado pelo Coordenador.', area, item=et,
                       fontes=[fonte_reg, fonte_res], esperado=registrado, encontrado=atual)
            if self.estado.get(et, {}).get('estado') == 'INDISPONIVEL':
                self.v(f'CONC-A-ORIGEM-{et}', 'A', f'Origem do resultado {et}', 'PENDENTE',
                       'Resultado sem integridade confirmada: empresa/SOL/competência não atestadas e dados não usados.', area, item=et)
                continue
            try:
                dados = json.loads(caminho.read_text(encoding='utf-8'))
            except (OSError, ValueError) as exc:
                self.estado[et] = {'estado': 'INDISPONIVEL', 'motivo': 'resultado ilegível'}
                self.v(f'CONC-A-ORIGEM-{et}', 'A', f'Origem do resultado {et}', 'DIVERGENTE',
                       f'Resultado não é JSON legível ({exc.__class__.__name__}).', area, item=et, fontes=[fonte_res])
                continue
            contrato, agente = IDENTIDADE[et]
            achado = (dados.get('empresa'), dados.get('sol'), dados.get('competencia'))
            problemas = []
            if achado != (self.empresa, self.sol, self.competencia):
                problemas.append(f'empresa/SOL/competência do resultado = {"/".join(str(x) for x in achado)}')
            if contrato and dados.get('contrato') != contrato:
                problemas.append(f'contrato {dados.get("contrato")} ≠ {contrato}')
            if agente and dados.get('agente') != agente:
                problemas.append(f'agente {dados.get("agente")} ≠ {agente}')
            if dados.get('modo') != 'SIMULACAO':
                problemas.append(f'modo {dados.get("modo")} ≠ SIMULACAO')
            esperado_id = f'{self.empresa}/{self.sol}/{self.competencia}'
            if problemas:
                self.estado[et] = {'estado': 'INDISPONIVEL', 'motivo': 'resultado de outra origem (' + '; '.join(problemas) + ')'}
                self.v(f'CONC-A-ORIGEM-{et}', 'A', f'Origem do resultado {et}', 'DIVERGENTE',
                       'Resultado não corresponde a esta solicitação: ' + '; '.join(problemas) + '. Dados NÃO usados.',
                       area, item=et, fontes=[fonte_res], esperado=esperado_id, encontrado='/'.join(str(x) for x in achado))
                continue
            self.v(f'CONC-A-ORIGEM-{et}', 'A', f'Origem do resultado {et}', 'CONFERIDO',
                   'Empresa, SOL, competência, contrato/agente e modo SIMULACAO do resultado correspondem à solicitação.',
                   area, item=et, fontes=[fonte_res], esperado=esperado_id, encontrado=esperado_id)
            if et == 'FINANCEIRO' and dados.get('bloqueio_lote'):
                self.estado[et] = {'estado': 'INDISPONIVEL', 'motivo': 'lote bloqueado na conferência financeira'}
                self.v('CONC-A-BLOQUEIO-FINANCEIRO', 'A', 'Lote financeiro bloqueado', 'PENDENTE',
                       'O Financeiro bloqueou o lote: ' + ' | '.join(dados['bloqueio_lote']), 'FINANCEIRO', item='FINANCEIRO',
                       fontes=[fonte_res])
                self.nao_exec('A', 'FINANCEIRO', 'lote bloqueado no Financeiro')
                continue
            if self.estado.get(et, {}).get('estado') != 'INDISPONIVEL':
                self.estado[et] = {'estado': 'USAVEL', 'motivo': None}
                self.res[et] = dados
        for et in ETAPAS:
            if self.estado[et]['estado'] == 'INDISPONIVEL':
                self.nao_exec('A', et, self.estado[et]['motivo'])
        self.pacote()
        self.fontes_empresa()
        anteriores = self.e.get('pendencias_anteriores') or []
        if anteriores:
            lista = [p if isinstance(p, str) else json.dumps(p, ensure_ascii=False, sort_keys=True) for p in anteriores]
            self.v('CONC-A-PENDENCIAS-ANTERIORES', 'A', 'Pendências anteriores da SOL', 'PENDENTE',
                   f'{len(lista)} pendência(s) registrada(s) antes desta Conciliação permanecem abertas; preservadas e listadas. '
                   'A Conciliação não as resolve.', 'COORDENADOR', item=' | '.join(lista),
                   fontes=[{'referencia': 'pendencias_anteriores (entradas)', 'tipo': 'REGISTRO_COORDENADOR', 'natureza': 'INTERNA'}],
                   acao='Tratar as pendências anteriores com o Coordenador/Supervisor.')
        else:
            self.v('CONC-A-PENDENCIAS-ANTERIORES', 'A', 'Pendências anteriores da SOL', 'NAO_APLICAVEL',
                   'Nenhuma pendência anterior registrada nas entradas.', 'COORDENADOR')

    def pacote(self):
        self.docs_conc, self.pacote_ok = [], False
        p = self.e.get('pacote') or {}
        if not (p.get('pasta') and p.get('documentos_local') and p.get('extracao_local')):
            self.v('CONC-A-PACOTE', 'A', 'Pacote de Documentos da Conciliação', 'PENDENTE',
                   'Pacote de Documentos não informado; documentos da Conciliação (saldos de abertura, posições, confirmações) não lidos.',
                   'DOCUMENTOS')
            self.nao_exec('A', 'PACOTE', 'pacote de Documentos não informado')
            return
        man, ext = resolver(p['documentos_local']), resolver(p['extracao_local'])
        try:
            arquivos, _ = cf.receber_pacote_local(self.empresa, self.competencia, self.sol, p['pasta'], man, ext,
                                                  area='CONCILIACAO', exigir_hash=True)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.v('CONC-A-PACOTE', 'A', 'Pacote de Documentos da Conciliação', 'DIVERGENTE',
                   f'Pacote recusado na validação de integridade: {exc} Nenhum documento do pacote foi usado.', 'DOCUMENTOS',
                   fontes=[{'referencia': Path(man).name, 'tipo': 'PACOTE_DOCUMENTOS', 'natureza': 'INTERNA'}])
            self.nao_exec('A', 'PACOTE', 'pacote de Documentos recusado')
            return
        self.versoes['PACOTE'] = sha_arquivo(man)
        self.versoes['EXTRACAO'] = sha_arquivo(ext)
        self.pacote_ok = True
        self.docs_conc = arquivos
        self.v('CONC-A-PACOTE', 'A', 'Pacote de Documentos da Conciliação', 'CONFERIDO',
               f'Manifesto, extração (sha256) e originais conferidos por receber_pacote_local; {len(arquivos)} documento(s) '
               'destinado(s) à CONCILIACAO.', 'DOCUMENTOS', item=', '.join(a['arquivo'] for a in arquivos) or None,
               fontes=[{'referencia': Path(man).name, 'tipo': 'PACOTE_DOCUMENTOS', 'natureza': 'INTERNA'}])

    def fontes_empresa(self):
        self.plano, self.contas_banco, self.cnpjs = {}, {}, set()
        cad, plano = resolver(self.e.get('cadastro')), resolver(self.e.get('plano'))
        faltas = [n for n, c in (('CADASTRO.md', cad), ('PLANO-DE-CONTAS.md', plano)) if not c or not c.is_file()]
        if faltas:
            self.fontes_ok = False
            self.v('CONC-A-FONTES-EMPRESA', 'A', 'Cadastro e plano de contas da empresa', 'PENDENTE',
                   f'Fonte(s) da empresa não localizada(s): {", ".join(faltas)}. Contas e grupos não verificáveis.', 'COORDENADOR')
            self.nao_exec('A', 'FONTES_EMPRESA', 'cadastro ou plano ausente')
            return
        texto_cad = cad.read_text(encoding='utf-8')
        self.cnpjs = {digitos(c) for c in re.findall(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto_cad)}
        exig = resolver(self.e.get('regras_conciliacao'))
        if exig:
            self.base_regras = exig.parent
        if exig and exig.is_file():
            try:
                dados = json.loads(exig.read_text(encoding='utf-8'))
                if dados.get('contrato') != 'EXIGENCIAS_CONCILIACAO_V1' or dados.get('empresa') != self.empresa:
                    raise ValueError('contrato ou empresa diferente')
                self.exig_dados = dados
            except (OSError, ValueError) as exc:
                self.observacoes.append(f'REGRAS-CONCILIACAO.json inválido ({exc}); exigências tratadas como não determinadas.')
        for l in tabela_md(texto_cad, 'Contas bancarias'):
            if digitos(l.get('BANCO')) and digitos(l.get('CONTA')):
                self.contas_banco[chave_conta(l['BANCO'], l.get('AGENCIA'), l['CONTA'])] = digitos(l.get('CONTA CONTABIL')) or None
        for l in tabela_md(plano.read_text(encoding='utf-8'), 'Contas utilizadas'):
            cod = digitos(l.get('CODIGO REDUZIDO'))
            if cod:
                self.plano[cod] = {'descricao': l.get('DESCRICAO', ''), 'grupo': norm(l.get('GRUPO')).replace(' ', '_'),
                                   'tipo': norm(l.get('TIPO'))}
        self.contas_contabeis_banco = {c for c in self.contas_banco.values() if c}
        problemas = [f'conta bancária {k} sem conta contábil' for k, c in self.contas_banco.items() if not c]
        problemas += [f'conta contábil {c} (banco) fora do plano' for c in self.contas_contabeis_banco if c not in self.plano]
        self.fontes_ok = True
        fontes = [{'referencia': 'CADASTRO.md', 'tipo': 'CADASTRO_EMPRESA', 'natureza': 'INTERNA'},
                  {'referencia': 'PLANO-DE-CONTAS.md', 'tipo': 'PLANO_DE_CONTAS', 'natureza': 'INTERNA'}]
        if problemas:
            self.v('CONC-A-FONTES-EMPRESA', 'A', 'Cadastro e plano de contas da empresa', 'DIVERGENTE',
                   'Cadastro/plano incoerentes: ' + '; '.join(problemas) + '.', 'COORDENADOR', fontes=fontes)
        elif not self.cnpjs:
            self.v('CONC-A-FONTES-EMPRESA', 'A', 'Cadastro e plano de contas da empresa', 'PENDENTE',
                   'CNPJ da empresa não identificado no CADASTRO.md.', 'COORDENADOR', fontes=fontes)
        else:
            self.v('CONC-A-FONTES-EMPRESA', 'A', 'Cadastro e plano de contas da empresa', 'CONFERIDO',
                   f'{len(self.plano)} conta(s) no plano; {len(self.contas_banco)} conta(s) bancária(s) com conta contábil no plano.',
                   'COORDENADOR', fontes=fontes)

    # ------------------------------------------------------------------ documentos próprios da Conciliação
    def ler_documentos(self):
        self.abertura, self.abertura_invalida, self.posicoes, self.confirmacoes = {}, {}, [], []
        self.docs_lidos = {'ABERTURA': [], 'POSICAO': [], 'CONFIRMACAO': []}
        for a in self.docs_conc:
            nome = a['arquivo'].rsplit('/', 1)[-1]
            c = a.get('conteudo') or {}
            if not str(a.get('leitura', '')).startswith('EXTRAIDO_') or c.get('leitura_incompleta') or c.get('requer_conferencia_ocr') or c.get('truncado'):
                self.observacoes.append(f'{nome}: leitura pendente/parcial; não usado pela Conciliação.')
                continue
            texto = texto_arquivo(a)
            linhas = [[x.strip() for x in l.split(';')] for l in texto.splitlines() if l.strip()]
            i_ab, cab_ab = cf.cabecalho(linhas, {'CONTA', 'DESCRICAO', 'SALDO', 'NATUREZA', 'DATA_BASE'})
            i_po, cab_po = cf.cabecalho(linhas, {'TIPO', 'POSICAO', 'DATA_BASE', 'CNPJ', 'TITULO', 'VALOR'})
            if i_ab is not None:
                self.docs_lidos['ABERTURA'].append(nome)
                self.ler_abertura(nome, linhas[i_ab + 1:], cab_ab)
            elif i_po is not None:
                self.docs_lidos['POSICAO'].append(nome)
                self.ler_posicao(nome, linhas[i_po + 1:], cab_po)
            elif norm(texto.strip().splitlines()[0] if texto.strip() else '').startswith('CONFIRMACAO DE SALDO'):
                self.docs_lidos['CONFIRMACAO'].append(nome)
                self.confirmacoes.append(self.ler_confirmacao(nome, a.get('sha256', ''), texto))
            else:
                self.observacoes.append(f'{nome}: cópia recebida pela Conciliação (ex.: extrato); as verificações usam o '
                                        'resultado do Financeiro para esse documento.')

    def ler_abertura(self, nome, linhas, cab):
        for n, l in enumerate(linhas, 1):
            r = dict(zip(cab, l))
            conta = digitos(r.get('CONTA'))
            if not conta:
                continue
            s, nat, data = dec(r.get('SALDO')), norm(r.get('NATUREZA')), cf.data_iso(r.get('DATA_BASE'))
            item = {'arquivo': nome, 'linha': n, 'saldo': s, 'natureza': nat, 'data_base': data, 'fonte': r.get('FONTE'),
                    'descricao': r.get('DESCRICAO')}
            motivo = None
            if s is None or s < 0:
                motivo = 'saldo ausente, inválido ou negativo'
            elif nat not in ('D', 'C'):
                motivo = 'natureza diferente de D/C'
            elif data != dia_anterior(self.competencia).isoformat():
                motivo = f'data-base {data} ≠ {dia_anterior(self.competencia).isoformat()} (véspera da competência)'
            if motivo:
                self.abertura_invalida.setdefault(conta, []).append(f'{nome} linha {n}: {motivo}')
                continue
            assinado = s if nat == 'D' else -s
            if conta in self.abertura and self.abertura[conta]['valor'] != assinado:
                self.abertura_invalida.setdefault(conta, []).append(f'{nome}: saldos de abertura conflitantes para a conta')
            self.abertura.setdefault(conta, dict(item, valor=assinado))
        for conta in self.abertura_invalida:
            self.abertura.pop(conta, None)

    def ler_base_inicial(self):
        """Saldos de abertura da BASE INICIAL CONFIRMADA pelo Supervisor (balancete de encerramento de M-1 + definições expressas).
        Só contas analíticas; D/C como informado. Documento SALDOS DE ABERTURA divergente torna a abertura da conta inválida (nenhum
        dos dois prevalece). Base em RASCUNHO não é usada. Composições do book: resumo informado (não são lançamentos)."""
        self.base_ok, self.base_info = False, None
        p = resolver(self.e.get('base_inicial'))
        vid, titulo = 'CONC-A-BASE-INICIAL', 'Base inicial (balancete anterior e book)'
        if not p or not p.is_file():
            self.v(vid, 'A', titulo, 'NAO_APLICAVEL', 'Nenhuma base inicial registrada para a competência; saldos de abertura somente por '
                   'documento SALDOS DE ABERTURA.', 'COORDENADOR')
            return
        try:
            b = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            self.v(vid, 'A', titulo, 'DIVERGENTE', f'Base inicial ilegível ({type(exc).__name__}); não usada.', 'COORDENADOR')
            return
        db = dia_anterior(self.competencia).isoformat()
        fonte = [{'referencia': f"base inicial {self.competencia} v{b.get('versao')} (sha256 {sha_arquivo(p)[:12]})", 'tipo': 'BASE_INICIAL',
                  'natureza': 'INTERNA'}]
        if (b.get('empresa'), b.get('competencia'), b.get('data_base')) != (self.empresa, self.competencia, db):
            self.v(vid, 'A', titulo, 'DIVERGENTE', f'Base inicial de outra empresa/competência/data-base (esperado {self.empresa} '
                   f'{self.competencia} {db}); não usada.', 'COORDENADOR', fontes=fonte)
            return
        if b.get('situacao') != 'CONFIRMADA':
            self.v(vid, 'A', titulo, 'PENDENTE', f"Base inicial v{b.get('versao')} em RASCUNHO (não confirmada pelo Supervisor); saldos não "
                   'usados.', 'COORDENADOR', fontes=fonte, acao='Concluir e confirmar a base inicial na tela Empresas.')
            return
        bal = b.get('balancete') or {}
        saldos = {}
        for c in bal.get('contas', []):
            if c.get('codigo') and c.get('saldo_atual') is not None:
                saldos[c['codigo']] = (Decimal(c['saldo_atual']), c.get('natureza_atual'), c.get('tipo'), c.get('descricao'),
                                       f"balancete {bal.get('arquivo')}")
        for cod, s in (b.get('saldos_definidos') or {}).items():
            saldos.setdefault(cod, (Decimal(s['saldo']), s.get('natureza'), s.get('tipo'), None, 'definição expressa do Supervisor'))
        usados, conflitos = 0, []
        for cod, (valor, nat, tipo, desc, origem) in saldos.items():
            tipo_plano = (self.plano.get(cod) or {}).get('tipo') or norm(tipo)
            if tipo_plano not in ('ANALITICA', 'A'):
                continue
            item = {'arquivo': f"BASE INICIAL v{b['versao']} ({origem})", 'linha': None, 'saldo': abs(valor), 'natureza': nat,
                    'data_base': db, 'fonte': 'BASE_INICIAL', 'descricao': desc, 'valor': valor, 'tipo_fonte': 'BASE_INICIAL'}
            if cod in self.abertura and self.abertura[cod]['valor'] != valor:
                self.abertura_invalida.setdefault(cod, []).append(
                    f"documento {self.abertura[cod]['arquivo']} ({f2(self.abertura[cod]['valor'])}) difere da base inicial confirmada ({f2(valor)})")
                conflitos.append(cod)
                continue
            self.abertura.setdefault(cod, item)
            usados += 1
        for conta in self.abertura_invalida:
            self.abertura.pop(conta, None)
        conf = ((b.get('book') or {}).get('confronto') or {}).get('resumo') or {}
        ciencias = sorted((b.get('ciencias') or {}))
        self.base_ok = True
        self.base_info = {'competencia': b['competencia'], 'versao': b['versao'], 'data_base': db, 'sha256': sha_arquivo(p),
                          'confirmada_em': (b.get('confirmacao') or {}).get('em'), 'balancete': bal.get('arquivo'),
                          'balancete_sha256': bal.get('sha256'), 'book': (b.get('book') or {}).get('arquivo'),
                          'book_sha256': (b.get('book') or {}).get('sha256'), 'saldos_usados': usados, 'ciencias': ciencias}
        texto = (f"Base inicial v{b['versao']} CONFIRMADA (data-base {db}): {usados} saldo(s) de abertura de contas analíticas"
                 f" (balancete {bal.get('arquivo')}" + (f"; book {(b.get('book') or {}).get('arquivo')}: {conf.get('iguais_ao_balancete', 0)} "
                 f"composição(ões) iguais ao balancete, {conf.get('divergentes', 0)} divergente(s), {conf.get('sem_conta', 0)} sem conta"
                                                        if b.get('book') else '; sem book')
                 + "). Ciências do Supervisor: " + (', '.join(ciencias) or 'nenhuma') + '. Composições e saldos de abertura não são lançamentos.')
        if conflitos:
            self.v(vid, 'A', titulo, 'DIVERGENTE', texto + f" Documento SALDOS DE ABERTURA diverge da base nas contas {', '.join(conflitos)}: "
                   'abertura dessas contas inválida (nenhum valor prevalece).', 'CONCILIACAO', fontes=fonte, contas=conflitos)
        else:
            self.v(vid, 'A', titulo, 'CONFERIDO', texto, 'COORDENADOR', fontes=fonte)

    def ler_posicao(self, nome, linhas, cab):
        for n, l in enumerate(linhas, 1):
            r = dict(zip(cab, l))
            tipo, pos = norm(r.get('TIPO')), norm(r.get('POSICAO'))
            if not tipo and not pos:
                continue
            self.posicoes.append({'arquivo': nome, 'linha': n, 'tipo': tipo, 'posicao': pos, 'data_base': cf.data_iso(r.get('DATA_BASE')),
                                  'contraparte': r.get('CONTRAPARTE'), 'cnpj': digitos(r.get('CNPJ')) or None,
                                  'titulo': (r.get('TITULO') or '').strip() or None, 'valor': dec(r.get('VALOR'))})

    def ler_confirmacao(self, nome, sha, texto):
        linhas = [norm(l) for l in texto.splitlines() if l.strip()]

        def rot(r):
            achados = {m.group(1).strip() for l in linhas for m in [re.match(rf'^{re.escape(r)}\s*:\s*(.*)$', l)] if m}
            return achados.pop() if len(achados) == 1 else None
        saldo = rot('SALDO EM ABERTO')
        return {'arquivo': nome, 'sha256': sha, 'emitente': rot('EMITENTE'), 'cnpj_emitente': digitos(rot('CNPJ DO EMITENTE')) or None,
                'cnpj_cliente': digitos(rot('CNPJ DO CLIENTE')) or None, 'data_base': cf.data_iso(rot('DATA BASE')),
                'saldo': dec(saldo) if saldo and re.fullmatch(r'(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}', saldo) else None}

    # ------------------------------------------------------------------ lançamentos (normalizados)
    def coletar_lancamentos(self):
        self.lans = []
        fontes = (('BANCOS', 'CONTABILIDADE/BANCOS'), ('CONTABILIDADE_FISCAL', 'CONTABILIDADE/FISCAL'), ('CONTABILIDADE_DP', 'CONTABILIDADE/DP'))
        for et, rotulo in fontes:
            for l in (self.res.get(et) or {}).get('lancamentos', []):
                deb, cre = (l.get('debito') or {}), (l.get('credito') or {})
                if et == 'BANCOS':
                    movs = sorted(l.get('movimentos') or [])
                    chave = ('BANCOS', '+'.join(movs) or 'SEM-MOVIMENTO', l.get('tipo') or 'SEM-TIPO')
                    evento = l.get('tipo')
                else:
                    movs = []
                    evento = l.get('evento')
                    chave = ('FISCAL' if et == 'CONTABILIDADE_FISCAL' else 'DP', l.get('documento') or 'SEM-DOCUMENTO', evento or 'SEM-EVENTO')
                self.lans.append({'etapa': et, 'rotulo': rotulo, 'ref': f"{rotulo}:{l.get('id')}", 'bruto': l, 'chave': chave,
                                  'status': l.get('status'), 'proposto': l.get('status') in PROPOSTOS, 'evento': evento,
                                  'debito': digitos(deb.get('codigo')) or None, 'credito': digitos(cre.get('codigo')) or None,
                                  'valor': dec(l.get('valor')), 'movimentos': movs, 'documento': l.get('documento'),
                                  'data': l.get('data'), 'competencia': l.get('competencia')})
        # ordem estável por chave de negócio (não pela posição na lista nem pelo LAN-00N)
        self.lans.sort(key=lambda x: (x['chave'], json.dumps({k: v for k, v in x['bruto'].items() if k != 'id'},
                                                              sort_keys=True, ensure_ascii=False, default=str), x['ref']))

    # ------------------------------------------------------------------ B: cada lançamento
    def grupo_b(self):
        fin = self.res.get('FINANCEIRO') or {}
        movs = {m['id']: m for m in fin.get('movimentos', [])}
        fis_docs = {d['id']: d for d in (self.res.get('FISCAL') or {}).get('documentos', [])}
        dp_docs = {d['id']: d for d in (self.res.get('DP') or {}).get('documentos', [])}
        dp_fatos = {(f.get('documento'), f.get('evento')): f for f in (self.res.get('DP') or {}).get('fatos', [])}
        comp_ini, comp_fim = f'{self.competencia}-01', ultimo_dia(self.competencia).isoformat()
        # duplicidade: mesmo movimento (Bancos) ou mesmo documento+evento (Fiscal/DP) mais de uma vez
        uso_mov, uso_doc = {}, {}
        for x in self.lans:
            for m in x['movimentos']:
                uso_mov.setdefault(m, []).append(x['ref'])
            if x['etapa'] != 'BANCOS':
                uso_doc.setdefault(x['chave'], []).append(x['ref'])
        # reconhecimentos por documento (Fiscal/DP) para a separação reconhecimento × liquidação
        reconhecidos = {}
        for x in self.lans:
            if x['etapa'] == 'BANCOS' or not x['proposto']:
                continue
            arq = str(x['bruto'].get('arquivo') or '').rsplit('/', 1)[-1]
            numero = (dp_docs.get(x['documento']) or fis_docs.get(x['documento']) or {}).get('numero')
            for k in (('ARQ', norm(arq)) if arq else None, ('NUM', norm(numero)) if numero else None):
                if k:
                    reconhecidos.setdefault(k, set()).add(x['ref'])
        for et in ('BANCOS', 'CONTABILIDADE_FISCAL', 'CONTABILIDADE_DP'):
            motivo = self.disponivel(et) or self.disponivel('FINANCEIRO' if et == 'BANCOS' else 'FISCAL' if et == 'CONTABILIDADE_FISCAL' else 'DP')
            if motivo and self.planejada(et):
                self.v(f'CONC-B-ETAPA-{et}', 'B', f'Lançamentos de {et}', 'PENDENTE',
                       f'Lançamentos de {et} não verificados: {motivo}.', et)
                self.nao_exec('B', et, motivo)
        for x in self.lans:
            et, l = x['etapa'], x['bruto']
            if self.disponivel(et) or self.disponivel('FINANCEIRO' if et == 'BANCOS' else 'FISCAL' if et == 'CONTABILIDADE_FISCAL' else 'DP'):
                continue
            vid = 'CONC-B-LAN-' + chave_id(*x['chave'])
            contas = [x['debito'], x['credito']]
            fonte_lan = {'referencia': x['ref'], 'tipo': 'LANCAMENTO_PROPOSTO', 'natureza': 'RESULTADO'}
            titulo = f"Lançamento {x['rotulo']} {x['evento'] or ''}".strip()
            if not x['proposto']:
                self.v(vid, 'B', titulo, 'PENDENTE',
                       f"Lançamento {x['status']}: não é conferido. Pendências da área: " + ' | '.join(l.get('pendencias') or ['não informadas']),
                       et, item=x['ref'], contas=contas, lancamentos=[x['ref']], fontes=[fonte_lan], encontrado=f2(x['valor']),
                       acao=f'Completar a proposta na área {et} (decisão/regra/documento) e reexecutar.')
                continue
            erros, pend, fontes = [], [], [fonte_lan]
            esperado = None
            # contas e grupos
            for lado, cod in (('débito', x['debito']), ('crédito', x['credito'])):
                if not cod:
                    erros.append(f'conta de {lado} não definida')
                elif cod not in self.plano:
                    erros.append(f'conta de {lado} {cod} inexistente no plano')
                elif self.plano[cod]['tipo'] == 'SINTETICA':
                    erros.append(f'conta de {lado} {cod} é sintética')
                elif self.plano[cod]['tipo'] != 'ANALITICA':
                    pend.append(f'tipo (analítica/sintética) da conta {cod} não definido no plano')
            if x['debito'] and x['debito'] == x['credito']:
                erros.append('débito e crédito na mesma conta')
            grupo = lambda c: (self.plano.get(c) or {}).get('grupo') or ''
            if et == 'BANCOS':
                tipo = l.get('tipo')
                movs_l = [movs.get(m) for m in x['movimentos']]
                if not x['movimentos'] or None in movs_l:
                    erros.append('movimento(s) do lançamento ausente(s) do resultado do Financeiro: ' +
                                 ', '.join(m for m in x['movimentos'] if m not in movs) if x['movimentos'] else 'lançamento sem movimento')
                else:
                    m0 = movs_l[0]
                    esperado = dec(m0['valor'])
                    fontes.append({'referencia': f"extrato {m0['conta']} · {m0['id']} ({m0['data']})", 'tipo': 'EXTRATO_BANCARIO', 'natureza': 'EXTERNA'})
                    banco = self.contas_banco.get(m0['conta'])
                    if tipo == 'TRANSFERENCIA_PROPRIA':
                        if not (x['debito'] in self.contas_contabeis_banco and x['credito'] == banco):
                            erros.append('transferência própria deve debitar a conta contábil de destino e creditar a de origem (bancos)')
                    else:
                        lado_banco, contra = (x['credito'], x['debito']) if m0['direcao'] == 'DEBITO' else (x['debito'], x['credito'])
                        if lado_banco != banco:
                            erros.append(f'lado bancário {lado_banco} ≠ conta contábil {banco} da conta {m0["conta"]}')
                        exig = GRUPOS_BANCOS.get(tipo)
                        if exig is None:
                            pend.append(f'natureza {tipo} sem grupo de contrapartida definido')
                        elif contra in self.contas_contabeis_banco:
                            erros.append(f'contrapartida {contra} é conta de banco da empresa')
                        elif contra and grupo(contra) not in exig:
                            erros.append(f'contrapartida {contra} (grupo {grupo(contra) or "indefinido"}) incompatível com {tipo} '
                                         f'(exige {" ou ".join(sorted(exig))})')
                    if x['data'] != m0['data']:
                        erros.append(f'data do lançamento {x["data"]} ≠ data do movimento {m0["data"]}')
                    for m in movs_l[1:]:
                        if dec(m['valor']) != esperado:
                            erros.append(f'pontas da transferência com valores diferentes ({m["valor"]})')
                if not (x['data'] and comp_ini <= x['data'] <= comp_fim):
                    erros.append(f'data {x["data"]} fora da competência {self.competencia}')
                dups = sorted({r for m in x['movimentos'] for r in uso_mov.get(m, []) if r != x['ref']})
                if dups:
                    erros.append('duplicidade: o mesmo movimento está em outro(s) lançamento(s): ' + ', '.join(dups))
                # separação reconhecimento × liquidação: despesa/receita no banco para documento já reconhecido em Fiscal/DP
                if tipo in ('DESPESA', 'RECEITA'):
                    docs_l = l.get('documentos') or []
                    chaves = {('ARQ', norm(str(d.get('arquivo') or '').rsplit('/', 1)[-1])) for d in docs_l if d.get('arquivo')}
                    chaves |= {('NUM', norm(d.get('numero'))) for d in docs_l if d.get('numero')}
                    outros = sorted({r for k in chaves for r in reconhecidos.get(k, ())})
                    if outros:
                        erros.append(f'{tipo} no pagamento/recebimento de documento já reconhecido em ' + ', '.join(outros) +
                                     ' (mesma obrigação reconhecida duas vezes)')
            else:
                fonte_docs = fis_docs if et == 'CONTABILIDADE_FISCAL' else dp_docs
                tabela = GRUPOS_FISCAL if et == 'CONTABILIDADE_FISCAL' else GRUPOS_DP
                d = fonte_docs.get(x['documento'])
                if not d:
                    erros.append(f'documento {x["documento"]} não consta no resultado de {"FISCAL" if et == "CONTABILIDADE_FISCAL" else "DP"}')
                else:
                    if l.get('sha256') and d.get('sha256') and l['sha256'] != d['sha256']:
                        erros.append('sha256 do documento no lançamento ≠ do documento analisado')
                    if not d.get('elegivel_contabilidade'):
                        erros.append('documento de suporte não elegível na análise da área')
                    if d.get('tipo') == 'GUIA':
                        erros.append('suporte é guia (cobrança): guia não gera provisão nem despesa')
                    if et == 'CONTABILIDADE_FISCAL':
                        esperado = dec(d.get('valor'))
                        fontes.append({'referencia': f"{d.get('tipo')} {d.get('numero') or ''} ({str(d.get('arquivo')).rsplit('/', 1)[-1]})".strip(),
                                       'tipo': 'DOCUMENTO_FISCAL', 'natureza': 'INTERNA'})
                    else:
                        f = dp_fatos.get((x['documento'], x['evento']))
                        if not f:
                            erros.append(f'fato {x["evento"]} do documento não consta no resultado do DP')
                        else:
                            esperado = dec(f.get('valor'))
                        fontes.append({'referencia': f"{d.get('tipo')} {d.get('numero') or ''} ({str(d.get('arquivo')).rsplit('/', 1)[-1]})".strip(),
                                       'tipo': 'DEMONSTRATIVO_DP', 'natureza': 'INTERNA'})
                exig = tabela.get(x['evento'])
                if exig is None:
                    pend.append(f'evento {x["evento"]} sem grupos definidos')
                else:
                    for lado, cod, gs in (('débito', x['debito'], exig[0]), ('crédito', x['credito'], exig[1])):
                        if cod and cod in self.plano and grupo(cod) not in gs:
                            erros.append(f'{lado} {cod} (grupo {grupo(cod) or "indefinido"}) incompatível com {x["evento"]}')
                        if cod in self.contas_contabeis_banco:
                            erros.append(f'{lado} {cod} é conta de banco (pagamento é fato do Financeiro/Bancos)')
                if x['competencia'] != self.competencia:
                    erros.append(f'competência {x["competencia"]} ≠ {self.competencia}')
                if not x['data']:
                    erros.append('data do lançamento ausente (sem política de data aplicável); não presumida')
                elif not comp_ini <= x['data'] <= comp_fim:
                    erros.append(f'data do lançamento {x["data"]} fora da competência {self.competencia}')
                dups = [r for r in uso_doc.get(x['chave'], []) if r != x['ref']]
                if dups:
                    erros.append('duplicidade: mesmo documento e evento em ' + ', '.join(dups))
            if x['valor'] is None or x['valor'] <= 0:
                erros.append('valor ausente ou não positivo')
            elif esperado is not None and x['valor'] != esperado:
                erros.append(f'valor {f2(x["valor"])} ≠ {f2(esperado)} da fonte')
            if esperado is None and not erros:
                pend.append('valor de referência da fonte não localizado')
            dif = f2(x['valor'] - esperado) if x['valor'] is not None and esperado is not None else None
            if erros:
                self.v(vid, 'B', titulo, 'DIVERGENTE', 'Lançamento proposto com problema: ' + '; '.join(erros + pend) + '.', et,
                       item=x['ref'], contas=contas, lancamentos=[x['ref']], fontes=fontes, esperado=f2(esperado),
                       encontrado=f2(x['valor']), diferenca=dif)
            elif pend:
                self.v(vid, 'B', titulo, 'PENDENTE', 'Não verificável integralmente: ' + '; '.join(pend) + '.', et,
                       item=x['ref'], contas=contas, lancamentos=[x['ref']], fontes=fontes, esperado=f2(esperado),
                       encontrado=f2(x['valor']), diferenca=dif)
            else:
                self.v(vid, 'B', titulo, 'CONFERIDO',
                       'Débito e crédito definidos em contas analíticas do plano com grupos compatíveis; valor positivo igual ao da '
                       'fonte; data/competência na SOL; suporte localizado; sem duplicidade nem segundo reconhecimento.', et,
                       item=x['ref'], contas=contas, lancamentos=[x['ref']], fontes=fontes, esperado=f2(esperado),
                       encontrado=f2(x['valor']), diferenca=dif)
        if not self.lans and not any(self.planejada(et) and self.disponivel(et) for et in ('BANCOS', 'CONTABILIDADE_FISCAL', 'CONTABILIDADE_DP')):
            self.v('CONC-B-SEM-LANCAMENTOS', 'B', 'Lançamentos propostos', 'NAO_APLICAVEL',
                   'Nenhum lançamento recebido das etapas de Contabilidade desta SOL.', 'COORDENADOR')

    # ------------------------------------------------------------------ saldos contábeis
    def calcular_saldos(self):
        """Saldo por conta = abertura + débitos − créditos dos lançamentos PROPOSTOS (devedor positivo)."""
        self.saldos = {}
        contas = set(self.abertura) | set(self.abertura_invalida)
        for x in self.lans:
            contas |= {c for c in (x['debito'], x['credito']) if c}
        incompletos_indeterminados = [x['ref'] for x in self.lans if not x['proposto'] and not (x['debito'] and x['credito'])]
        for c in sorted(contas):
            deb = sum((x['valor'] for x in self.lans if x['proposto'] and x['debito'] == c and x['valor']), ZERO)
            cre = sum((x['valor'] for x in self.lans if x['proposto'] and x['credito'] == c and x['valor']), ZERO)
            inc = sorted({x['ref'] for x in self.lans if not x['proposto'] and c in (x['debito'], x['credito'])})
            if c in self.contas_contabeis_banco:
                inc += sorted({x['ref'] for x in self.lans if not x['proposto'] and x['etapa'] == 'BANCOS'
                               and self.contas_banco.get((self.mov_por_id().get((x['movimentos'] or [''])[0]) or {}).get('conta')) == c
                               and x['ref'] not in inc})
                indet = []
            else:
                indet = incompletos_indeterminados
            ab = self.abertura.get(c)
            motivos = []
            produtores = ('FINANCEIRO', 'BANCOS') if c in self.contas_contabeis_banco else (
                'FINANCEIRO', 'BANCOS', 'CONTABILIDADE_FISCAL', 'CONTABILIDADE_DP')
            if self.disponivel(*produtores):
                motivos.append('etapa(s) indisponível(is) podem afetar a conta: ' + self.disponivel(*produtores))
            if ab is None:
                motivos.append('saldo de abertura não documentado' + (f' ({"; ".join(self.abertura_invalida[c])})' if c in self.abertura_invalida else '')
                               + ' — não presumido zero')
            if inc:
                motivos.append('lançamento(s) INCOMPLETO(s) afetando a conta: ' + ', '.join(inc))
            if indet:
                motivos.append('lançamento(s) INCOMPLETO(s) com contrapartida indefinida (podem afetar a conta): ' + ', '.join(indet))
            final = None if ab is None else ab['valor'] + deb - cre
            self.saldos[c] = {'conta': c, 'descricao': (self.plano.get(c) or {}).get('descricao'), 'grupo': (self.plano.get(c) or {}).get('grupo'),
                              'abertura': None if ab is None else f2(ab['valor']), 'debitos': f2(deb), 'creditos': f2(cre),
                              'saldo_final': None if final is None else f2(final), 'natureza': None if final is None else ('D' if final > 0 else 'C' if final < 0 else '-'),
                              'situacao': 'PENDENTE' if motivos else 'CALCULADO', 'motivos': motivos,
                              '_final': final, '_ab': ab}

    def mov_por_id(self):
        return {m['id']: m for m in (self.res.get('FINANCEIRO') or {}).get('movimentos', [])}

    def fonte_abertura(self, c):
        ab = self.abertura.get(c)
        return {'referencia': f"saldos de abertura {ab['arquivo']} · conta {c} ({ab['data_base']})", 'tipo': ab.get('tipo_fonte') or 'SALDOS_DE_ABERTURA',
                'natureza': 'INTERNA'} if ab else None

    # ------------------------------------------------------------------ C: bancos e posições
    def grupo_c(self):
        fin = self.res.get('FINANCEIRO') or {}
        movs = self.mov_por_id()
        motivo_fin = self.disponivel('FINANCEIRO')
        motivo_bancos = self.disponivel('FINANCEIRO', 'BANCOS')
        if motivo_fin:
            self.nao_exec('C', 'EXTRATOS', motivo_fin)
        if motivo_bancos:
            self.nao_exec('C', 'SALDOS_BANCARIOS', motivo_bancos)
        verif = {v['conta']: v for v in fin.get('verificacao_extratos', [])}
        for chave in sorted(self.contas_banco):
            conta = self.contas_banco[chave]
            # C1: aritmética do extrato (terceiro)
            vid = f'CONC-C-EXTRATO-{chave_id(chave)}'
            if motivo_fin:
                self.v(vid, 'C', f'Aritmética do extrato {chave}', 'PENDENTE', f'Não verificado: {motivo_fin}.', 'FINANCEIRO',
                       item=chave, contas=[conta])
                extrato_si = extrato_sf = None
            else:
                extrato_si, extrato_sf = self.c_extrato(vid, chave, conta, verif.get(chave), movs)
            # C2: abertura (interna) × saldo inicial do extrato (externa)
            vid = f'CONC-C-ABERTURA-{conta}'
            if motivo_fin:
                self.v(vid, 'C', f'Abertura × saldo inicial do extrato ({conta})', 'PENDENTE', f'Não verificado: {motivo_fin}.',
                       'FINANCEIRO', item=chave, contas=[conta])
            elif self.abertura.get(conta) is None:
                self.v(vid, 'C', f'Abertura × saldo inicial do extrato ({conta})', 'PENDENTE',
                       'Saldo de abertura da conta não documentado (SALDOS DE ABERTURA); não presumido zero.', 'CONCILIACAO',
                       item=chave, contas=[conta], acao='Enviar o documento SALDOS DE ABERTURA com a conta e reexecutar.')
            elif extrato_si is None:
                self.v(vid, 'C', f'Abertura × saldo inicial do extrato ({conta})', 'PENDENTE',
                       'Saldo inicial do extrato não informado; não presumido.', 'FINANCEIRO', item=chave, contas=[conta])
            else:
                ab = self.abertura[conta]['valor']
                res = 'CONFERIDO' if ab == extrato_si else 'DIVERGENTE'
                self.v(vid, 'C', f'Abertura × saldo inicial do extrato ({conta})', res,
                       'Saldo de abertura documentado igual ao saldo inicial do extrato.' if res == 'CONFERIDO' else
                       'Saldo de abertura documentado difere do saldo inicial do extrato.', 'CONCILIACAO', item=chave, contas=[conta],
                       fontes=[self.fonte_abertura(conta), {'referencia': f'extrato {chave} (saldo inicial)', 'tipo': 'EXTRATO_BANCARIO', 'natureza': 'EXTERNA'}],
                       esperado=f2(extrato_si), encontrado=f2(ab), diferenca=f2(ab - extrato_si))
            # C3: saldo contábil × saldo final do extrato
            vid = f'CONC-C-SALDO-{conta}'
            s = self.saldos.get(conta)
            titulo = f'Saldo contábil {conta} × saldo final do extrato'
            if motivo_bancos:
                self.v(vid, 'C', titulo, 'PENDENTE', f'Não verificado: {motivo_bancos}.', 'BANCOS', item=chave, contas=[conta])
                continue
            sem_lanc = sorted(m['id'] for m in movs.values() if m['conta'] == chave and not any(m['id'] in x['movimentos'] for x in self.lans)
                              and not ((m.get('transferencia_propria') or {}).get('par')))
            motivos = list((s or {}).get('motivos') or (['saldo de abertura não documentado — não presumido zero'] if not s or s['_ab'] is None else []))
            if sem_lanc:
                motivos.append('movimento(s) do extrato sem lançamento: ' + ', '.join(sem_lanc))
            if extrato_sf is None:
                motivos.append('saldo final do extrato não disponível')
            if motivos:
                self.v(vid, 'C', titulo, 'PENDENTE', 'Não verificável: ' + '; '.join(motivos) + '.', 'BANCOS', item=chave, contas=[conta],
                       encontrado=None if not s or s['_final'] is None else f2(s['_final']),
                       esperado=f2(extrato_sf))
                continue
            final = s['_final'] if s else self.abertura[conta]['valor']
            res = 'CONFERIDO' if final == extrato_sf else 'DIVERGENTE'
            self.v(vid, 'C', titulo, res,
                   ('Abertura + débitos − créditos dos lançamentos propostos = saldo final do extrato.' if res == 'CONFERIDO' else
                    'Saldo contábil calculado (abertura + débitos − créditos dos propostos) difere do saldo final do extrato.')
                   + ' Convenção: positivo = devedor.', 'BANCOS', item=chave, contas=[conta],
                   lancamentos=[x['ref'] for x in self.lans if x['proposto'] and conta in (x['debito'], x['credito'])],
                   fontes=[self.fonte_abertura(conta), {'referencia': 'lançamentos propostos (Bancos/Fiscal/DP)', 'tipo': 'LANCAMENTO_PROPOSTO', 'natureza': 'RESULTADO'},
                           {'referencia': f'extrato {chave} (saldo final)', 'tipo': 'EXTRATO_BANCARIO', 'natureza': 'EXTERNA'}],
                   esperado=f2(extrato_sf), encontrado=f2(final), diferenca=f2(final - extrato_sf))
        if not motivo_bancos:
            self.c_movimentos(movs)
            self.c_transferencias(movs)
        self.c_posicoes(movs)

    def c_extrato(self, vid, chave, conta, v, movs):
        titulo = f'Aritmética do extrato {chave}'
        if not v:
            self.v(vid, 'C', titulo, 'PENDENTE', 'Extrato da conta cadastrada não recebido/conferido pelo Financeiro.', 'FINANCEIRO',
                   item=chave, contas=[conta], acao='Enviar o extrato completo da competência.')
            return None, None
        extratos = sorted(v.get('extratos') or [], key=lambda e: (e.get('inicio') or '', e.get('fim') or ''))
        si = dec(extratos[0].get('saldo_inicial')) if extratos else None
        sf = dec(extratos[-1].get('saldo_final')) if extratos else None
        soma = sum(((dec(m['valor']) if m['direcao'] == 'CREDITO' else -dec(m['valor'])) for m in movs.values() if m['conta'] == chave), ZERO)
        motivos = []
        if v.get('cobertura_competencia') != 'COMPLETA':
            motivos.append('extratos não cobrem toda a competência')
        if si is None or sf is None:
            motivos.append('saldo inicial ou final do extrato ausente (não presumido)')
        fonte = {'referencia': ', '.join(e.get('arquivo') or '' for e in extratos) or chave, 'tipo': 'EXTRATO_BANCARIO', 'natureza': 'EXTERNA'}
        if motivos:
            self.v(vid, 'C', titulo, 'PENDENTE', 'Não verificável: ' + '; '.join(motivos) + '.', 'FINANCEIRO', item=chave, contas=[conta],
                   fontes=[fonte])
            return si, None
        esperado = si + soma
        res = 'CONFERIDO' if esperado == sf else 'DIVERGENTE'
        self.v(vid, 'C', titulo, res,
               f'Saldo inicial {f2(si)} + movimentos {f2(soma)} ' + ('= saldo final do extrato.' if res == 'CONFERIDO' else '≠ saldo final do extrato.'),
               'FINANCEIRO', item=chave, contas=[conta], fontes=[fonte], esperado=f2(esperado), encontrado=f2(sf), diferenca=f2(sf - esperado))
        return si, (sf if res == 'CONFERIDO' else None)

    def c_movimentos(self, movs):
        """Cada movimento do extrato × exatamente um lançamento proposto de mesmo valor."""
        for mid in sorted(movs):
            m = movs[mid]
            tp = m.get('transferencia_propria') or {}
            ligados = [x for x in self.lans if mid in x['movimentos']]
            vid = f'CONC-C-MOV-{chave_id(mid)}'
            titulo = f"Movimento {m['data']} {m['direcao']} {m['valor']}"
            fonte = {'referencia': f"extrato {m['conta']} · {mid}", 'tipo': 'EXTRATO_BANCARIO', 'natureza': 'EXTERNA'}
            propostos = [x for x in ligados if x['proposto']]
            if not ligados:
                self.v(vid, 'C', titulo, 'PENDENTE', 'Movimento do extrato sem lançamento (' +
                       (f"já escriturado na {m['ja_escriturado_em'].get('sol')}" if m.get('ja_escriturado_em') else 'não proposto') + ').',
                       'BANCOS', item=mid, fontes=[fonte], esperado=m['valor'])
            elif len(propostos) > 1:
                self.v(vid, 'C', titulo, 'DIVERGENTE', 'Movimento contabilizado mais de uma vez: ' + ', '.join(x['ref'] for x in propostos) + '.',
                       'BANCOS', item=mid, lancamentos=[x['ref'] for x in propostos], fontes=[fonte], esperado=m['valor'],
                       encontrado=f2(sum((x['valor'] or ZERO for x in propostos), ZERO)))
            elif not propostos:
                self.v(vid, 'C', titulo, 'PENDENTE', 'Lançamento do movimento INCOMPLETO: ' + ', '.join(x['ref'] for x in ligados) + '.',
                       'BANCOS', item=mid, lancamentos=[x['ref'] for x in ligados], fontes=[fonte], esperado=m['valor'])
            else:
                x = propostos[0]
                res = 'CONFERIDO' if x['valor'] == dec(m['valor']) else 'DIVERGENTE'
                self.v(vid, 'C', titulo, res, ('Um único lançamento proposto com o valor do movimento' +
                                               (' (transferência própria: lançamento único para as duas pontas).' if tp.get('par') else '.'))
                       if res == 'CONFERIDO' else 'Valor do lançamento difere do movimento.', 'BANCOS', item=mid,
                       contas=[x['debito'], x['credito']], lancamentos=[x['ref']],
                       fontes=[fonte, {'referencia': x['ref'], 'tipo': 'LANCAMENTO_PROPOSTO', 'natureza': 'RESULTADO'}],
                       esperado=m['valor'], encontrado=f2(x['valor']), diferenca=f2((x['valor'] or ZERO) - dec(m['valor'])))

    def c_transferencias(self, movs):
        transf = [m for m in movs.values() if m['direcao'] == 'DEBITO' and m.get('transferencia_propria')]
        if not transf:
            self.v('CONC-C-TRANSFERENCIAS', 'C', 'Transferências entre contas próprias', 'NAO_APLICAVEL',
                   'Nenhuma transferência entre contas próprias identificada pelo Financeiro nesta competência.', 'FINANCEIRO')
            return
        for m in sorted(transf, key=lambda m: m['id']):
            par = m['transferencia_propria'].get('par')
            vid = f"CONC-C-TRANSF-{chave_id(m['id'])}"
            fonte = {'referencia': f"extrato {m['conta']} · {m['id']}", 'tipo': 'EXTRATO_BANCARIO', 'natureza': 'EXTERNA'}
            if not par:
                self.v(vid, 'C', 'Transferência própria', 'PENDENTE', 'Outra ponta da transferência não localizada.', 'FINANCEIRO',
                       item=m['id'], fontes=[fonte])
                continue
            com_par = [x for x in self.lans if x['proposto'] and (m['id'] in x['movimentos'] or par in x['movimentos'])]
            ok = len(com_par) == 1 and set(com_par[0]['movimentos']) == {m['id'], par}
            self.v(vid, 'C', 'Transferência própria', 'CONFERIDO' if ok else ('PENDENTE' if not com_par else 'DIVERGENTE'),
                   'Um único lançamento liga as duas pontas (sem duplicação).' if ok else
                   ('Sem lançamento proposto para a transferência.' if not com_par else
                    'Transferência contabilizada em mais de um lançamento ou sem as duas pontas: ' + ', '.join(x['ref'] for x in com_par) + '.'),
                   'BANCOS', item=f"{m['id']} + {par}", lancamentos=[x['ref'] for x in com_par], fontes=[fonte])

    def finais_por_tipo(self):
        """Total da posição FINAL por tipo e por CNPJ. Posição FINAL só é considerada documentada quando há ao menos
        uma linha FINAL do tipo (posição sem títulos: linha com VALOR 0,00). Ausência nunca vira zero."""
        fim = ultimo_dia(self.competencia).isoformat()
        out = {}
        for tipo in ('PAGAR', 'RECEBER'):
            linhas = [p for p in self.posicoes if p['tipo'] == tipo and p['posicao'] == 'FINAL']
            invalidas = [p for p in linhas if p['valor'] is None or p['valor'] < 0 or p['data_base'] != fim]
            out[tipo] = {'documentada': bool(linhas), 'invalidas': invalidas,
                         'total': sum((p['valor'] for p in linhas if p['valor'] is not None), ZERO),
                         'por_cnpj': {}, 'arquivos': sorted({p['arquivo'] for p in linhas})}
            for p in linhas:
                if p['cnpj'] and p['valor'] is not None:
                    out[tipo]['por_cnpj'][p['cnpj']] = out[tipo]['por_cnpj'].get(p['cnpj'], ZERO) + p['valor']
        return out

    def c_posicoes(self, movs):
        fin = self.res.get('FINANCEIRO') or {}
        motivo = self.disponivel('FINANCEIRO', 'BANCOS', 'CONTABILIDADE_FISCAL', 'CONTABILIDADE_DP')
        titulos = fin.get('posicoes_titulos')
        self.finais = self.finais_por_tipo()
        self.conta_posicao = {}
        tipos_presentes = {p['tipo'] for p in self.posicoes} | {t.get('tipo') for t in titulos or []}
        for tipo in ('PAGAR', 'RECEBER'):
            if tipo in tipos_presentes:
                continue
            vid, titulo, chave = f'CONC-C-POSICAO-{tipo}', f'Posição de títulos a {tipo.lower()}', f'POSICAO_TITULOS_{tipo}'
            if not self.pacote_ok or motivo:
                self.v(vid, 'C', titulo, 'PENDENTE', f'Não verificável: {motivo or "pacote da Conciliação indisponível"}.', 'FINANCEIRO', item=tipo)
                self.nao_exec('C', f'POSICAO_{tipo}', motivo or 'pacote indisponível')
                continue
            ex, info = self.exigencia(chave)
            if ex == 'EXIGIDA':
                self.v(vid, 'C', titulo, 'PENDENTE', f'Posição de títulos a {tipo.lower()} exigida pela regra da empresa e não recebida nesta SOL; '
                       'a ausência não é presumida zero.', 'FINANCEIRO', item=tipo, fontes=[self.fonte_regra(chave)],
                       acao='Obter a posição de títulos e reexecutar a Conciliação.')
            elif ex == 'DISPENSADA':
                self.v(vid, 'C', titulo, 'NAO_APLICAVEL', f'Dispensada pela regra documentada da empresa ({chave}): {info}', 'FINANCEIRO',
                       item=tipo, fontes=[self.fonte_regra(chave)])
            else:
                self.indeterminado(vid, 'C', titulo, f'A empresa {self.empresa} exige posição de títulos a {tipo.lower()} na conciliação '
                                   f'mensal? Nenhuma posição foi recebida e {info}.', 'FINANCEIRO', item=tipo)
        if not tipos_presentes:
            return
        # títulos (Financeiro): liquidação × extrato
        if self.disponivel('FINANCEIRO'):
            self.nao_exec('C', 'TITULOS', self.disponivel('FINANCEIRO'))
        elif titulos is None:
            self.v('CONC-C-TITULOS', 'C', 'Títulos da posição × liquidações', 'PENDENTE',
                   'Resultado do Financeiro sem "posicoes_titulos": liquidações dos títulos não conferidas.', 'FINANCEIRO')
        else:
            for t in titulos:
                vid = 'CONC-C-TITULO-' + chave_id(t.get('tipo'), t.get('cnpj') or 'SEM-CNPJ', t.get('titulo') or 'SEM-TITULO')
                sit = t.get('situacao')
                res = {'LIQUIDADO_CONFERIDO': 'CONFERIDO', 'EM_ABERTO': 'CONFERIDO', 'DIVERGENTE': 'DIVERGENTE'}.get(sit, 'PENDENTE')
                fontes = [{'referencia': f"posição de títulos ({t.get('tipo')}) {t.get('titulo')}", 'tipo': 'POSICAO_TITULOS', 'natureza': 'INTERNA'}]
                liq = t.get('liquidacao') or {}
                if liq.get('movimento'):
                    fontes.append({'referencia': f"extrato · {liq['movimento']}", 'tipo': 'EXTRATO_BANCARIO', 'natureza': 'EXTERNA'})
                if res == 'CONFERIDO' and sit == 'LIQUIDADO_CONFERIDO' and (liq.get('movimento') not in movs or dec(liq.get('valor')) != dec(t.get('valor_inicial'))):
                    res = 'DIVERGENTE'
                self.v(vid, 'C', f"Título {t.get('tipo')} {t.get('titulo')} ({t.get('contraparte')})", res,
                       {'LIQUIDADO_CONFERIDO': 'Título da posição inicial liquidado no extrato pelo mesmo valor.',
                        'EM_ABERTO': 'Título permanece em aberto na posição final (sem liquidação no mês).'}.get(sit, '')
                       if res == 'CONFERIDO' else f"Situação no Financeiro: {sit}. {t.get('observacao') or ''}".strip(),
                       'FINANCEIRO', item=t.get('titulo'), fontes=fontes, esperado=t.get('valor_inicial'),
                       encontrado=liq.get('valor') if liq else t.get('valor_final'))
        # saldo contábil × total da posição FINAL (controle INTERNO)
        for tipo in ('PAGAR', 'RECEBER'):
            if tipo not in tipos_presentes:
                continue
            vid = f'CONC-C-POSICAO-{tipo}'
            titulo = f'Saldo contábil × posição FINAL a {tipo.lower()} (controle interno)'
            if motivo:
                self.v(vid, 'C', titulo, 'PENDENTE', f'Não verificado: {motivo}.', 'FINANCEIRO', item=tipo)
                self.nao_exec('C', f'POSICAO_{tipo}', motivo)
                continue
            fin_tipo = self.finais[tipo]
            contas = self.contas_da_posicao(tipo, titulos or [])
            self.conta_posicao[tipo] = next(iter(contas)) if len(contas) == 1 else None
            motivos = []
            if not fin_tipo['documentada']:
                motivos.append(f'posição FINAL a {tipo.lower()} não recebida (ausência não é presumida zero)')
            if fin_tipo['invalidas']:
                motivos.append('linha(s) da posição FINAL com valor inválido ou data-base ≠ fim da competência')
            if len(contas) != 1:
                motivos.append('conta contábil da posição não identificada de forma única pelos lançamentos de liquidação/reconhecimento'
                               + (f' ({", ".join(sorted(contas))})' if contas else ''))
            conta = next(iter(contas)) if len(contas) == 1 else None
            s = self.saldos.get(conta) if conta else None
            if conta and (not s or s['situacao'] != 'CALCULADO'):
                motivos.append(f'saldo contábil da conta {conta} pendente: ' + '; '.join((s or {}).get('motivos') or ['sem abertura documentada']))
            if motivos:
                self.v(vid, 'C', titulo, 'PENDENTE', 'Não verificável: ' + '; '.join(motivos) + '.', 'FINANCEIRO', item=tipo,
                       contas=[conta], esperado=f2(fin_tipo['total']) if fin_tipo['documentada'] else None)
                continue
            contabil = s['_final'] if tipo == 'RECEBER' else -s['_final']
            res = 'CONFERIDO' if contabil == fin_tipo['total'] else 'DIVERGENTE'
            self.v(vid, 'C', titulo, res,
                   ('Saldo contábil igual ao total da posição FINAL. Concordância entre controles INTERNOS da empresa: '
                    'não é confirmação independente.' if res == 'CONFERIDO' else
                    'Saldo contábil difere do total da posição FINAL (controle interno).'),
                   'FINANCEIRO', item=tipo, contas=[conta],
                   fontes=[{'referencia': f"posição FINAL a {tipo.lower()} ({', '.join(fin_tipo['arquivos'])})", 'tipo': 'POSICAO_TITULOS', 'natureza': 'INTERNA'},
                           self.fonte_abertura(conta), {'referencia': 'lançamentos propostos', 'tipo': 'LANCAMENTO_PROPOSTO', 'natureza': 'RESULTADO'}],
                   esperado=f2(fin_tipo['total']), encontrado=f2(contabil), diferenca=f2(contabil - fin_tipo['total']))
            # abertura × posição INICIAL (ambas internas)
            iniciais = [p for p in self.posicoes if p['tipo'] == tipo and p['posicao'] == 'INICIAL' and p['valor'] is not None]
            if iniciais:
                total_ini = sum((p['valor'] for p in iniciais), ZERO)
                ab = s['_ab']['valor'] if tipo == 'RECEBER' else -s['_ab']['valor']
                self.v(f'CONC-C-POSICAO-INICIAL-{tipo}', 'C', f'Abertura × posição INICIAL a {tipo.lower()} (controle interno)',
                       'CONFERIDO' if ab == total_ini else 'DIVERGENTE',
                       'Saldo de abertura igual ao total da posição INICIAL (concordância interna, não independente).' if ab == total_ini
                       else 'Saldo de abertura difere do total da posição INICIAL.', 'FINANCEIRO', item=tipo, contas=[conta],
                       fontes=[self.fonte_abertura(conta), {'referencia': f'posição INICIAL a {tipo.lower()}', 'tipo': 'POSICAO_TITULOS', 'natureza': 'INTERNA'}],
                       esperado=f2(total_ini), encontrado=f2(ab), diferenca=f2(ab - total_ini))

    def contas_da_posicao(self, tipo, titulos):
        contas = set()
        for t in titulos:
            mid = (t.get('liquidacao') or {}).get('movimento')
            if t.get('tipo') != tipo or not mid:
                continue
            for x in self.lans:
                if mid in x['movimentos'] and x['proposto']:
                    contas.add(x['debito'] if tipo == 'PAGAR' else x['credito'])
        if tipo == 'RECEBER':
            contas |= {x['debito'] for x in self.lans if x['proposto'] and x['etapa'] == 'CONTABILIDADE_FISCAL' and x['evento'] == 'RECEITA_SERVICOS'}
        return {c for c in contas if c}

    # ------------------------------------------------------------------ D: folha, provisões e tributos
    def grupo_d(self):
        self.d_dp()
        self.d_tributos()
        fis = self.res.get('FISCAL') or {}
        self.d_liquidacoes([d for d in fis.get('documentos', []) if d.get('tipo') == 'GUIA'])

    def eventos_dp(self):
        dp = self.res.get('DP') or {}
        docs = {d['id']: d for d in dp.get('documentos', [])}
        tot = {}
        for f in dp.get('fatos', []):
            d = docs.get(f.get('documento'))
            if not d or not d.get('elegivel_contabilidade') or f.get('competencia') != self.competencia:
                continue
            v = dec(f.get('valor'))
            if v is not None:
                tot.setdefault(f['evento'], []).append((v, f))
        return tot, docs

    def d_dp(self):
        motivo = self.disponivel('DP', 'CONTABILIDADE_DP')
        if not self.planejada('DP'):
            self.v('CONC-D-DP', 'D', 'Folha, encargos e provisões', 'NAO_APLICAVEL', 'Etapa DP não integra o plano desta SOL.', 'DP')
            return
        if motivo:
            self.v('CONC-D-DP', 'D', 'Folha, encargos e provisões', 'PENDENTE',
                   f'Lançamentos de DP × demonstrativos não verificados: {motivo}.', 'DP')
            self.v('CONC-D-PAGTO-SALARIOS', 'D', 'Pagamento de salários × líquido a pagar', 'PENDENTE',
                   f'Líquido a pagar não disponível: {motivo}.', 'DP')
            self.v('CONC-D-OBRIGACOES-DP', 'D', 'Saldos das obrigações de DP', 'PENDENTE', f'Não verificado: {motivo}.', 'CONTABILIDADE_DP')
            self.nao_exec('D', 'DP', motivo)
            return
        eventos, docs = self.eventos_dp()
        dp_lans = [x for x in self.lans if x['etapa'] == 'CONTABILIDADE_DP']
        fonte_dp = lambda ev: {'referencia': 'demonstrativos de DP (' + ', '.join(sorted({f.get('origem', {}).get('numero') or f.get('documento') for _, f in eventos.get(ev, [])})) + ')',
                               'tipo': 'DEMONSTRATIVO_DP', 'natureza': 'INTERNA'}
        nao_eleg = [d for d in docs.values() if not d.get('elegivel_contabilidade')]
        for ev in EVENTOS_DP:
            vid = f'CONC-D-DP-{ev}'
            ls = [x for x in dp_lans if x['evento'] == ev]
            total_ev = sum((v for v, _ in eventos.get(ev, [])), ZERO)
            if not eventos.get(ev) and not ls:
                self.v(vid, 'D', f'{ev}: lançamentos × demonstrativo', 'PENDENTE' if nao_eleg else 'NAO_APLICAVEL',
                       ('Evento ausente dos fatos aproveitados e há documento de DP não elegível: ' + ', '.join(d['arquivo'] for d in nao_eleg))
                       if nao_eleg else 'Demonstrativos aproveitados não trazem este evento nesta competência; nenhum lançamento proposto.',
                       'DP', item=ev)
                continue
            inc = [x['ref'] for x in ls if not x['proposto']]
            prop = sum((x['valor'] or ZERO for x in ls if x['proposto']), ZERO)
            if inc:
                self.v(vid, 'D', f'{ev}: lançamentos × demonstrativo', 'PENDENTE', 'Lançamento(s) INCOMPLETO(s): ' + ', '.join(inc) + '.',
                       'CONTABILIDADE_DP', item=ev, lancamentos=inc, esperado=f2(total_ev), encontrado=f2(prop))
                continue
            res = 'CONFERIDO' if prop == total_ev else 'DIVERGENTE'
            self.v(vid, 'D', f'{ev}: lançamentos × demonstrativo', res,
                   'Soma dos lançamentos propostos igual ao valor do demonstrativo.' if res == 'CONFERIDO' else
                   'Soma dos lançamentos propostos difere do demonstrativo.', 'CONTABILIDADE_DP', item=ev,
                   contas=[c for x in ls for c in (x['debito'], x['credito'])], lancamentos=[x['ref'] for x in ls],
                   fontes=[fonte_dp(ev), {'referencia': 'lançamentos Contabilidade/DP', 'tipo': 'LANCAMENTO_PROPOSTO', 'natureza': 'RESULTADO'}],
                   esperado=f2(total_ev), encontrado=f2(prop), diferenca=f2(prop - total_ev))
        self.d_pagamento_salarios(eventos, docs, dp_lans)
        self.d_saldos_obrigacoes('DP', dp_lans, eventos)

    def d_pagamento_salarios(self, eventos, docs, dp_lans):
        vid = 'CONC-D-PAGTO-SALARIOS'
        titulo = 'Pagamento de salários no extrato × líquido a pagar'
        motivo = self.disponivel('FINANCEIRO', 'BANCOS')
        liq = eventos.get('LIQUIDO_A_PAGAR', [])
        if not liq:
            self.v(vid, 'D', titulo, 'PENDENTE' if self.eventos_folha_esperados(docs) else 'NAO_APLICAVEL',
                   'LIQUIDO A PAGAR não disponível nos fatos aproveitados do DP.' if self.eventos_folha_esperados(docs) else
                   'Nenhum resumo da folha nesta SOL.', 'DP')
            return
        if motivo:
            self.v(vid, 'D', titulo, 'PENDENTE', f'Não verificado: {motivo}.', 'FINANCEIRO')
            return
        liquido = sum((v for v, _ in liq), ZERO)
        numeros = {norm(f.get('origem', {}).get('numero')) for _, f in liq if f.get('origem', {}).get('numero')}
        arquivos = {norm(str(f.get('arquivo') or '').rsplit('/', 1)[-1]) for _, f in liq}
        conta_sal = {x['credito'] for x in dp_lans if x['evento'] == 'FOLHA_PROVENTOS' and x['credito']}
        pagos = {}
        for m in self.mov_por_id().values():
            if m['direcao'] != 'DEBITO':
                continue
            docs_m = m.get('documentos') or []
            texto = norm(m.get('descricao')) + ' ' + ' '.join(norm(v) for v in (m.get('identificadores') or {}).values())
            if (any(d.get('tipo') == 'FOLHA' or norm(d.get('numero')) in numeros or norm(d.get('arquivo')) in arquivos for d in docs_m)
                    or any(n and n in texto for n in numeros)
                    or any(m['id'] in x['movimentos'] and x['debito'] in conta_sal for x in self.lans if x['etapa'] == 'BANCOS')):
                pagos[m['id']] = m
        fontes = [{'referencia': 'resumo da folha (LIQUIDO A PAGAR ' + ', '.join(sorted(numeros)) + ')', 'tipo': 'DEMONSTRATIVO_DP', 'natureza': 'INTERNA'}]
        if not pagos:
            self.v(vid, 'D', titulo, 'PENDENTE', 'Pagamento de salários não localizado no extrato da competência (pode ocorrer no mês '
                   'seguinte; nesse caso o saldo de salários a pagar deve igualar o líquido).', 'FINANCEIRO', fontes=fontes,
                   esperado=f2(liquido))
            return
        total = sum((dec(m['valor']) for m in pagos.values()), ZERO)
        fontes += [{'referencia': f"extrato {m['conta']} · {m['id']} ({m['data']})", 'tipo': 'EXTRATO_BANCARIO', 'natureza': 'EXTERNA'} for m in pagos.values()]
        res = 'CONFERIDO' if total == liquido else 'DIVERGENTE'
        self.v(vid, 'D', titulo, res, 'Pagamento no extrato igual ao líquido a pagar da folha.' if res == 'CONFERIDO' else
               f'Pagamento no extrato ({f2(total)}) difere do líquido a pagar ({f2(liquido)}).', 'FINANCEIRO',
               item=', '.join(sorted(pagos)), lancamentos=[x['ref'] for x in self.lans if set(x['movimentos']) & set(pagos)],
               fontes=fontes, esperado=f2(liquido), encontrado=f2(total), diferenca=f2(total - liquido))

    def eventos_folha_esperados(self, docs):
        return any(d.get('tipo') == 'RESUMO_FOLHA' for d in docs.values())

    def d_saldos_obrigacoes(self, origem, lans_area, eventos=None):
        """Obrigações (PASSIVO) da área: saldo esperado = abertura + valores das fontes (demonstrativo/apuração) com o lado
        de cada lançamento + liquidações do extrato; encontrado = saldo contábil dos propostos. Débito em passivo = DIVERGENTE."""
        etapa = 'CONTABILIDADE_DP' if origem == 'DP' else 'CONTABILIDADE_FISCAL'
        contas = sorted({c for x in lans_area for c in (x['debito'], x['credito'])
                         if c and (self.plano.get(c) or {}).get('grupo') == 'PASSIVO'})
        if origem == 'FISCAL':
            contas = sorted({x['credito'] for x in lans_area if x['evento'] in GRUPOS_FISCAL and x['evento'] != 'RECEITA_SERVICOS'
                             and x['credito'] and (self.plano.get(x['credito']) or {}).get('grupo') == 'PASSIVO'})
        motivo = self.disponivel('FINANCEIRO', 'BANCOS', 'CONTABILIDADE_FISCAL', 'CONTABILIDADE_DP')
        movs = self.mov_por_id()
        fis_docs = {d['id']: d for d in (self.res.get('FISCAL') or {}).get('documentos', [])}
        for c in contas:
            vid = f'CONC-D-SALDO-{c}'
            titulo = f'Saldo da obrigação {c} × {"demonstrativos" if origem == "DP" else "apuração"} e liquidações'
            s = self.saldos.get(c)
            if motivo or not s or s['situacao'] != 'CALCULADO':
                self.v(vid, 'D', titulo, 'PENDENTE', 'Não verificável: ' + (motivo or '; '.join((s or {}).get('motivos') or ['saldo não calculado'])) + '.',
                       etapa, item=c, contas=[c])
                continue
            esperado, problemas, liquidacoes = s['_ab']['valor'], [], []
            for x in self.lans:
                if c not in (x['debito'], x['credito']):
                    continue
                if not x['proposto']:
                    problemas.append(f'{x["ref"]} incompleto')
                    continue
                sinal = 1 if x['debito'] == c else -1
                if x['etapa'] == 'BANCOS':
                    vals = [dec(movs[m]['valor']) for m in x['movimentos'][:1] if m in movs]
                    if not vals:
                        problemas.append(f'{x["ref"]} sem movimento no extrato')
                        continue
                    esperado += sinal * vals[0]
                    liquidacoes.append(x['movimentos'][0])
                elif x['etapa'] == 'CONTABILIDADE_DP':
                    vs = [v for v, f in (eventos or {}).get(x['evento'], []) if f.get('documento') == x['documento']]
                    if len(vs) != 1:
                        problemas.append(f'{x["ref"]} sem valor único no demonstrativo')
                        continue
                    esperado += sinal * vs[0]
                else:
                    d = fis_docs.get(x['documento'])
                    v = dec((d or {}).get('valor'))
                    if v is None:
                        problemas.append(f'{x["ref"]} sem valor no documento fiscal')
                        continue
                    esperado += sinal * v
            fontes = [self.fonte_abertura(c),
                      {'referencia': 'demonstrativos de DP' if origem == 'DP' else 'apurações fiscais', 'tipo': 'DEMONSTRATIVO_DP' if origem == 'DP' else 'APURACAO_TRIBUTO', 'natureza': 'INTERNA'},
                      {'referencia': 'lançamentos propostos', 'tipo': 'LANCAMENTO_PROPOSTO', 'natureza': 'RESULTADO'}]
            if liquidacoes:
                fontes.append({'referencia': 'extrato: ' + ', '.join(sorted(liquidacoes)), 'tipo': 'EXTRATO_BANCARIO', 'natureza': 'EXTERNA'})
            if problemas:
                self.v(vid, 'D', titulo, 'PENDENTE', 'Não verificável: ' + '; '.join(problemas) + '.', etapa, item=c, contas=[c])
                continue
            final = s['_final']
            if final != esperado:
                res, just = 'DIVERGENTE', 'Saldo contábil difere do esperado pelos documentos de origem e liquidações do extrato.'
            elif final > 0:
                res, just = 'DIVERGENTE', 'Obrigação (PASSIVO) com saldo devedor: liquidação acima da obrigação reconhecida.'
            else:
                res, just = 'CONFERIDO', 'Abertura + valores dos documentos de origem − liquidações do extrato = saldo contábil (convenção: negativo = credor).'
            self.v(vid, 'D', titulo, res, just, etapa, item=c, contas=[c],
                   lancamentos=[x['ref'] for x in self.lans if c in (x['debito'], x['credito'])], fontes=fontes,
                   esperado=f2(esperado), encontrado=f2(final), diferenca=f2(final - esperado))

    def d_tributos(self):
        if not self.planejada('FISCAL'):
            self.v('CONC-D-TRIBUTOS', 'D', 'Tributos', 'NAO_APLICAVEL', 'Etapa Fiscal não integra o plano desta SOL.', 'FISCAL')
            return
        motivo = self.disponivel('FISCAL', 'CONTABILIDADE_FISCAL')
        if motivo:
            self.v('CONC-D-TRIBUTOS', 'D', 'Tributos: provisão × apuração, liquidação × guia × extrato', 'PENDENTE',
                   f'Não verificado: {motivo}.', 'FISCAL')
            self.nao_exec('D', 'TRIBUTOS', motivo)
            return
        fis = self.res['FISCAL']
        docs = fis.get('documentos', [])
        fis_lans = [x for x in self.lans if x['etapa'] == 'CONTABILIDADE_FISCAL']
        apur = [d for d in docs if d.get('tipo') == 'APURACAO_TRIBUTO' and not d.get('duplicado_de')]
        tributos = sorted({d.get('tributo') for d in apur if d.get('tributo')} | {x['evento'] for x in fis_lans if x['evento'] not in (None, 'RECEITA_SERVICOS')})
        for trib in tributos:
            vid = f'CONC-D-TRIB-PROVISAO-{chave_id(trib)}'
            titulo = f'Provisão de {trib} × apuração declarada'
            ds = [d for d in apur if d.get('tributo') == trib]
            ls = [x for x in fis_lans if x['evento'] == trib]
            nao_eleg = [d for d in ds if not d.get('elegivel_contabilidade') or d.get('competencia') != self.competencia]
            inc = [x['ref'] for x in ls if not x['proposto']]
            if nao_eleg or inc or not ds:
                self.v(vid, 'D', titulo, 'PENDENTE', 'Não verificável: ' + '; '.join(
                    ([f'apuração não elegível ({", ".join(d["arquivo"] for d in nao_eleg)})'] if nao_eleg else []) +
                    ([f'lançamento(s) INCOMPLETO(s): {", ".join(inc)}'] if inc else []) +
                    (['apuração declarada não recebida'] if not ds else [])) + '.', 'CONTABILIDADE_FISCAL', item=trib, lancamentos=inc)
                continue
            apurado = sum((dec(d.get('valor')) or ZERO for d in ds), ZERO)
            prov = sum((x['valor'] or ZERO for x in ls if x['proposto']), ZERO)
            res = 'CONFERIDO' if prov == apurado else 'DIVERGENTE'
            self.v(vid, 'D', titulo, res, 'Provisão proposta igual à apuração declarada.' if res == 'CONFERIDO' else
                   'Provisão proposta difere da apuração declarada.', 'CONTABILIDADE_FISCAL', item=trib,
                   contas=[c for x in ls for c in (x['debito'], x['credito'])], lancamentos=[x['ref'] for x in ls],
                   fontes=[{'referencia': f'apuração {trib} (' + ', '.join(str(d['arquivo']).rsplit('/', 1)[-1] for d in ds) + ')', 'tipo': 'APURACAO_TRIBUTO', 'natureza': 'INTERNA'},
                           {'referencia': 'lançamentos Contabilidade/Fiscal', 'tipo': 'LANCAMENTO_PROPOSTO', 'natureza': 'RESULTADO'}],
                   esperado=f2(apurado), encontrado=f2(prov), diferenca=f2(prov - apurado))
        self.d_saldos_obrigacoes('FISCAL', fis_lans)
        # guia não gera provisão
        guias = [d for d in docs if d.get('tipo') == 'GUIA']
        if not guias:
            self.v('CONC-D-GUIAS', 'D', 'Guia não gera provisão', 'NAO_APLICAVEL', 'Nenhuma guia recebida pelo Fiscal nesta SOL.', 'FISCAL')
        for g in guias:
            nome = str(g.get('arquivo')).rsplit('/', 1)[-1]
            usos = [x['ref'] for x in self.lans if x['etapa'] != 'BANCOS' and x['proposto'] and
                    (x['documento'] == g['id'] or norm(str(x['bruto'].get('arquivo') or '').rsplit('/', 1)[-1]) == norm(nome))]
            self.v(f"CONC-D-GUIA-{chave_id(g['id'])}", 'D', f'Guia {g.get("numero") or nome} não gera provisão',
                   'DIVERGENTE' if usos else 'CONFERIDO',
                   ('Guia usada como base de provisão/reconhecimento em ' + ', '.join(usos) + ': guia é cobrança, não apuração.') if usos else
                   'Nenhum lançamento de provisão/reconhecimento tem a guia como suporte.', 'CONTABILIDADE_FISCAL', item=nome,
                   lancamentos=usos, fontes=[{'referencia': f'guia {nome}', 'tipo': 'GUIA', 'natureza': 'INTERNA'},
                                             {'referencia': 'lançamentos Contabilidade/Fiscal e DP', 'tipo': 'LANCAMENTO_PROPOSTO', 'natureza': 'RESULTADO'}])

    def d_liquidacoes(self, guias):
        """Liquidação de tributo/encargo no extrato × guia (ou × obrigação de abertura quitada integralmente)."""
        if self.disponivel('FINANCEIRO', 'BANCOS'):
            return
        obrig = {x['credito'] for x in self.lans if x['etapa'] in ('CONTABILIDADE_FISCAL', 'CONTABILIDADE_DP') and x['credito']
                 and (self.plano.get(x['credito']) or {}).get('grupo') == 'PASSIVO' and x['evento'] != 'FOLHA_PROVENTOS'}
        obrig -= {x['credito'] for x in self.lans if x['evento'] == 'FOLHA_PROVENTOS'}
        guias_por_arq = {norm(str(g.get('arquivo')).rsplit('/', 1)[-1]): g for g in guias}
        movs = self.mov_por_id()
        for x in self.lans:
            if x['etapa'] != 'BANCOS' or x['debito'] not in obrig or not x['movimentos']:
                continue
            m = movs.get(x['movimentos'][0])
            if not m:
                continue
            vid = f"CONC-D-LIQ-{chave_id(m['id'])}"
            titulo = f"Liquidação da obrigação {x['debito']} × guia × extrato"
            fonte_m = {'referencia': f"extrato {m['conta']} · {m['id']} ({m['data']})", 'tipo': 'EXTRATO_BANCARIO', 'natureza': 'EXTERNA'}
            if not x['proposto']:
                self.v(vid, 'D', titulo, 'PENDENTE', 'Lançamento da liquidação INCOMPLETO.', 'BANCOS', item=m['id'], lancamentos=[x['ref']], fontes=[fonte_m])
                continue
            gs = [guias_por_arq[norm(str(d.get('arquivo')).rsplit('/', 1)[-1])] for d in (x['bruto'].get('documentos') or [])
                  if norm(str(d.get('arquivo')).rsplit('/', 1)[-1]) in guias_por_arq]
            gs += [g for g in guias if any(d.get('arquivo') and norm(d['arquivo']) == norm(str(g.get('arquivo')).rsplit('/', 1)[-1]) for d in m.get('documentos') or []) and g not in gs]
            valor_mov = dec(m['valor'])
            if len(gs) == 1:
                vg = dec(gs[0].get('valor'))
                res = 'CONFERIDO' if vg == valor_mov else 'DIVERGENTE'
                self.v(vid, 'D', titulo, res, 'Valor pago no extrato igual ao da guia vinculada (a guia não prova o pagamento; o extrato prova).'
                       if res == 'CONFERIDO' else 'Valor pago difere do valor da guia vinculada.', 'FINANCEIRO', item=m['id'],
                       contas=[x['debito']], lancamentos=[x['ref']],
                       fontes=[fonte_m, {'referencia': f"guia {gs[0].get('arquivo')}", 'tipo': 'GUIA', 'natureza': 'INTERNA'}],
                       esperado=f2(vg), encontrado=f2(valor_mov), diferenca=f2(valor_mov - vg) if vg is not None else None)
                continue
            ab = self.abertura.get(x['debito'])
            if ab is not None and -ab['valor'] == valor_mov:
                self.v(vid, 'D', titulo, 'CONFERIDO', 'Sem guia vinculada; valor pago no extrato igual à obrigação documentada no saldo de abertura '
                       '(quitação integral da competência anterior).', 'FINANCEIRO', item=m['id'], contas=[x['debito']], lancamentos=[x['ref']],
                       fontes=[fonte_m, self.fonte_abertura(x['debito'])], esperado=f2(-ab['valor']), encontrado=f2(valor_mov), diferenca='0.00')
            else:
                self.v(vid, 'D', titulo, 'PENDENTE', 'Sem guia vinculada (ou mais de uma) e valor pago diferente da obrigação de abertura: '
                       'composição da liquidação não confirmada.', 'FINANCEIRO', item=m['id'], contas=[x['debito']], lancamentos=[x['ref']],
                       fontes=[fonte_m], encontrado=f2(valor_mov), esperado=None if ab is None else f2(-ab['valor']))

    # ------------------------------------------------------------------ E: confirmações de terceiros
    def grupo_e(self):
        if not self.pacote_ok:
            self.v('CONC-E-CONFIRMACOES', 'E', 'Confirmações de terceiros', 'PENDENTE',
                   'Pacote da Conciliação indisponível: confirmações não lidas.', 'DOCUMENTOS')
            self.nao_exec('E', 'CONFIRMACOES', 'pacote indisponível')
            return
        finais = self.finais
        por_cnpj = {}
        for c in self.confirmacoes:
            por_cnpj.setdefault(c['cnpj_emitente'] or f"SEM-CNPJ-{c['sha256'][:8]}", []).append(c)
        necessarias = {}
        for tipo in ('PAGAR', 'RECEBER'):
            for cnpj, v in finais[tipo]['por_cnpj'].items():
                if v > 0:
                    necessarias.setdefault(cnpj, set()).add(tipo)
        sem_posicao = [t for t in ('PAGAR', 'RECEBER') if not finais.get(t, {}).get('documentada')]
        if not por_cnpj and not necessarias:
            if not sem_posicao:
                self.v('CONC-E-CONFIRMACOES', 'E', 'Confirmações de terceiros', 'NAO_APLICAVEL',
                       'Posições FINAIS a pagar e a receber recebidas sem saldo em aberto com terceiros: pela natureza, não há saldo a '
                       'confirmar, e nenhuma confirmação foi recebida.', 'FINANCEIRO',
                       fontes=[{'referencia': 'posições FINAIS de títulos (sem saldo em aberto)', 'tipo': 'POSICAO_TITULOS', 'natureza': 'INTERNA'}])
                return
            ex, info = self.exigencia('CONFIRMACAO_TERCEIROS')
            falta = 'posição FINAL a ' + ' e a '.join(t.lower() for t in sem_posicao) + ' não recebida'
            if ex == 'EXIGIDA':
                self.v('CONC-E-CONFIRMACOES', 'E', 'Confirmações de terceiros', 'PENDENTE',
                       f'Confirmações exigidas pela regra da empresa, mas {falta}: saldos com terceiros não determináveis e nenhuma '
                       'confirmação recebida.', 'FINANCEIRO', fontes=[self.fonte_regra('CONFIRMACAO_TERCEIROS')])
            elif ex == 'DISPENSADA':
                self.v('CONC-E-CONFIRMACOES', 'E', 'Confirmações de terceiros', 'NAO_APLICAVEL',
                       f'Dispensadas pela regra documentada da empresa (CONFIRMACAO_TERCEIROS): {info}', 'FINANCEIRO',
                       fontes=[self.fonte_regra('CONFIRMACAO_TERCEIROS')])
            else:
                self.indeterminado('CONC-E-CONFIRMACOES', 'E', 'Confirmações de terceiros',
                                   f'A empresa {self.empresa} exige confirmação de saldo de terceiros? {falta[0].upper() + falta[1:]}, '
                                   f'nenhuma confirmação foi recebida e {info}.', 'FINANCEIRO')
            return
        fim = ultimo_dia(self.competencia).isoformat()
        for cnpj in sorted(set(por_cnpj) | set(necessarias)):
            vid = f'CONC-E-CONF-{chave_id(cnpj)}'
            confs = por_cnpj.get(cnpj, [])
            tipos = (necessarias.get(cnpj) or {p['tipo'] for p in self.posicoes if p['cnpj'] == cnpj and p['posicao'] == 'FINAL'}
                     or {p['tipo'] for p in self.posicoes if p['cnpj'] == cnpj})
            titulo = f'Confirmação de saldo do terceiro {cnpj}'
            fonte_pos = {'referencia': 'posição FINAL de títulos (' + '/'.join(sorted(tipos)) + ')', 'tipo': 'POSICAO_TITULOS', 'natureza': 'INTERNA'}
            if not confs:
                tipo = next(iter(sorted(tipos)))
                saldo = f2(finais[tipo]["por_cnpj"][cnpj])
                ex, info = self.exigencia('CONFIRMACAO_TERCEIROS')
                if ex == 'DISPENSADA':
                    self.v(vid, 'E', titulo, 'NAO_APLICAVEL', f'Saldo em aberto ({saldo}) sem confirmação; confirmação dispensada pela regra '
                           f'documentada da empresa (CONFIRMACAO_TERCEIROS): {info}', 'FINANCEIRO', item=cnpj,
                           fontes=[fonte_pos, self.fonte_regra('CONFIRMACAO_TERCEIROS')], esperado=saldo)
                elif ex is None:
                    self.indeterminado(vid, 'E', titulo, f'A empresa {self.empresa} exige confirmação do saldo em aberto ({saldo}) com o terceiro '
                                       f'{cnpj}? Nenhuma confirmação recebida e {info}.', 'FINANCEIRO', item=cnpj, fontes=[fonte_pos])
                else:
                    self.v(vid, 'E', titulo, 'PENDENTE', f'Saldo final em aberto com o terceiro ({saldo}) sem confirmação de terceiro recebida '
                           '(exigida pela regra da empresa). A concordância interna (posição × contabilidade) não substitui a confirmação '
                           'independente.', 'FINANCEIRO', item=cnpj, fontes=[fonte_pos, self.fonte_regra('CONFIRMACAO_TERCEIROS')],
                           esperado=saldo, acao='Obter a CONFIRMACAO DE SALDO do terceiro (ou decisão do Supervisor) e reexecutar.')
                continue
            if len(confs) > 1:
                self.v(vid, 'E', titulo, 'PENDENTE', 'Mais de uma confirmação do mesmo terceiro; nenhuma escolhida: ' +
                       ', '.join(c['arquivo'] for c in confs) + '.', 'FINANCEIRO', item=cnpj)
                continue
            c = confs[0]
            fonte_c = {'referencia': f"confirmação de saldo {c['arquivo']} ({c['emitente']})", 'tipo': 'CONFIRMACAO_TERCEIRO', 'natureza': 'EXTERNA'}
            faltas = [k for k in ('cnpj_emitente', 'cnpj_cliente', 'data_base', 'saldo') if c.get(k) is None]
            if faltas:
                self.v(vid, 'E', titulo, 'PENDENTE', 'Confirmação sem campo(s) legível(is): ' + ', '.join(faltas) + '.', 'FINANCEIRO', item=c['arquivo'],
                       fontes=[fonte_c])
                continue
            if c['cnpj_cliente'] not in self.cnpjs:
                self.v(vid, 'E', titulo, 'DIVERGENTE', f"Confirmação dirigida a outro cliente (CNPJ {c['cnpj_cliente']}); não usada.", 'DOCUMENTOS',
                       item=c['arquivo'], fontes=[fonte_c])
                continue
            if c['data_base'] != fim:
                self.v(vid, 'E', titulo, 'PENDENTE', f"Data-base da confirmação {c['data_base']} ≠ fim da competência {fim}.", 'FINANCEIRO',
                       item=c['arquivo'], fontes=[fonte_c], encontrado=f2(c['saldo']))
                continue
            if len(tipos) != 1:
                self.v(vid, 'E', titulo, 'PENDENTE', 'Terceiro ' + ('não consta' if not tipos else 'consta em mais de um tipo') +
                       ' nas posições de títulos; posição de comparação não identificada.', 'FINANCEIRO', item=c['arquivo'], fontes=[fonte_c],
                       encontrado=f2(c['saldo']))
                continue
            tipo = next(iter(tipos))
            if not finais[tipo]['documentada'] or finais[tipo]['invalidas']:
                self.v(vid, 'E', titulo, 'PENDENTE', f'Posição FINAL a {tipo.lower()} não recebida ou inválida; confirmação sem base de comparação '
                       '(ausência não é presumida zero).', 'FINANCEIRO', item=c['arquivo'], fontes=[fonte_c], encontrado=f2(c['saldo']))
                continue
            posicao = finais[tipo]['por_cnpj'].get(cnpj, ZERO)
            res = 'CONFERIDO' if posicao == c['saldo'] else 'DIVERGENTE'
            conta = getattr(self, 'conta_posicao', {}).get(tipo)
            s = self.saldos.get(conta) if conta else None
            info = (f" Informação: conta {conta} ({tipo.lower()}) com saldo contábil {saldo_txt(s['_final'])} (agrega todos os terceiros; "
                    'não altera o resultado).' if s and s.get('_final') is not None else
                    ' Informação: saldo contábil da conta correspondente não disponível.')
            self.v(vid, 'E', titulo, res, ('Saldo confirmado pelo terceiro (evidência EXTERNA) igual à posição FINAL do mesmo CNPJ.'
                   if res == 'CONFERIDO' else 'Saldo confirmado pelo terceiro difere da posição FINAL do mesmo CNPJ.') + info, 'FINANCEIRO',
                   item=c['arquivo'], contas=[conta], fontes=[fonte_c, fonte_pos], esperado=f2(posicao), encontrado=f2(c['saldo']),
                   diferenca=f2(c['saldo'] - posicao))

    # ------------------------------------------------------------------ execução
    def executar(self) -> dict:
        self.grupo_a()
        if self.fontes_ok:
            self.ler_documentos()
            self.ler_base_inicial()
        else:
            self.base_ok, self.base_info = False, None
            self.abertura, self.abertura_invalida, self.posicoes, self.confirmacoes = {}, {}, [], []
            self.docs_lidos = {'ABERTURA': [], 'POSICAO': [], 'CONFIRMACAO': []}
        if self.pacote_ok and not self.docs_conc:
            self.nao_exec('C', 'DOCUMENTOS_CONCILIACAO', 'pacote sem documentos destinados à CONCILIACAO (saldos de abertura, '
                                                          'posições e confirmações não recebidos)')
        if not self.docs_lidos['ABERTURA'] and not self.base_ok:
            self.nao_exec('C', 'SALDOS_DE_ABERTURA', 'documento SALDOS DE ABERTURA não recebido: saldos contábeis não calculados')
        self.coletar_lancamentos()
        if self.fontes_ok:
            self.grupo_b()
            self.calcular_saldos()
            self.grupo_c()
            self.grupo_d()
            self.grupo_e()
        else:
            self.saldos, self.finais = {}, {}
            for g in 'BCDE':
                self.v(f'CONC-{g}-FONTES-EMPRESA', g, 'Verificações do grupo', 'PENDENTE',
                       'Cadastro/plano da empresa indisponível.', 'COORDENADOR')
                self.nao_exec(g, 'TODOS', 'cadastro/plano indisponível')
        self.verificacoes.sort(key=lambda v: (v['grupo'], v['id']))
        resumo = {k.lower(): sum(v['resultado'] == k for v in self.verificacoes) for k in RESULTADOS}
        resumo['total'] = len(self.verificacoes)
        resumo['conferidas_por_evidencia'] = {c: sum(v['resultado'] == 'CONFERIDO' and v['evidencia'] == c for v in self.verificacoes)
                                              for c in ('DOCUMENTO_EXTERNO', 'CONTROLE_INTERNO', 'CONSISTENCIA_SISTEMA')}
        indeterminadas = [v['id'] for v in self.verificacoes if v['resultado'] == 'NAO_DETERMINADO']
        parcial = bool(self.nao_executadas or indeterminadas)
        executadas = sorted({v['grupo'] for v in self.verificacoes if v['resultado'] in ('CONFERIDO', 'DIVERGENTE')})
        texto = ('Conciliação PARCIAL: ' + '; '.join([f"{x['grupo']}/{x['item']}: {x['motivo']}" for x in self.nao_executadas]
                                                     + [f'{len(indeterminadas)} verificação(ões) com exigência NÃO DETERMINADA '
                                                        '(pergunta ao Supervisor)'] * bool(indeterminadas)) + '.'
                 if parcial else 'Todas as verificações previstas foram executadas sobre as entradas recebidas.')
        return {
            'contrato': CONTRATO, 'agente': 'CONCILIACAO', 'versao': VERSAO, 'procedimento': PROCEDIMENTO,
            'empresa': self.empresa, 'sol': self.sol, 'competencia': self.competencia, 'modo': 'SIMULACAO',
            'executado_em': dt.datetime.now().astimezone().replace(microsecond=0).isoformat(),
            'versoes_entradas': dict(sorted(self.versoes.items())),
            'verificacoes': self.verificacoes, 'resumo': resumo,
            'alcance': {'executadas': executadas, 'nao_executadas': self.nao_executadas, 'indeterminadas': indeterminadas,
                        'parcial': parcial, 'texto': texto},
            'perguntas_supervisor': self.perguntas, 'exigencias_utilizadas': self.exig_usadas,
            'saldos_contas': [{k: v for k, v in s.items() if not k.startswith('_')} for _, s in sorted(self.saldos.items())],
            'convencao_saldos': 'Valores de saldo assinados: positivo = devedor, negativo = credor. Igualdade exata (Decimal), sem tolerância.',
            'documentos_conciliacao': self.docs_lidos, 'observacoes': self.observacoes, 'base_inicial': self.base_info,
            'pendencias_anteriores': list(self.e.get('pendencias_anteriores') or []),
            'aviso': 'SIMULAÇÃO. A Conciliação verifica e aponta; não corrige, não cria tolerância, não aprova, não escritura e não libera. '
                     'Verificação não executada nunca aparece como CONFERIDO; concordância entre controles internos não é confirmação '
                     'independente (cada verificação informa: documento externo, controle interno ou consistência do sistema). '
                     'A decisão é do Supervisor Contábil.',
        }


def conciliar(entradas: dict) -> dict:
    if not isinstance(entradas, dict) or entradas.get('contrato') != 'ENTRADAS_CONCILIACAO_V1':
        raise ValueError('Entradas fora do contrato ENTRADAS_CONCILIACAO_V1.')
    for k in ('empresa', 'sol', 'competencia'):
        if not entradas.get(k):
            raise ValueError(f'Entradas sem {k}.')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', entradas['competencia']):
        raise ValueError('Competência inválida.')
    return Conciliacao(entradas).executar()


def main(argv=None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='Conciliação local (SIMULACAO).')
    for a in ('--empresa', '--sol', '--competencia', '--entradas', '--saida'):
        p.add_argument(a, required=True)
    a = p.parse_args(argv)
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]*', a.empresa) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', a.competencia):
        print(json.dumps({'erro': 'PARAMETROS'}))
        return 2
    try:
        entradas = json.loads(Path(a.entradas).read_text(encoding='utf-8'))
        if (entradas.get('empresa'), entradas.get('sol'), entradas.get('competencia')) != (a.empresa, a.sol, a.competencia):
            raise ValueError('Entradas de outra empresa, SOL ou competência.')
        resultado = conciliar(entradas)
    except (OSError, ValueError) as exc:
        print(json.dumps({'erro': 'ENTRADAS_INVALIDAS', 'mensagem': str(exc)}, ensure_ascii=False))
        return 2
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / 'resultado.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'resultado': 'CONCILIACAO_CONCLUIDA', 'resumo': resultado['resumo'], 'alcance': resultado['alcance']['parcial']},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
