"""Cadastro, plano e parâmetros de conferência bancária locais, isolados por cliente."""
import base64
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import secrets
import plano_dominio
import colunas_automaticas
from pathlib import Path

# Valores do campo `grupo` do plano (consumido pelos agentes): ATIVO, PASSIVO, PATRIMONIO_LIQUIDO; nas Contas de Resultado a natureza
# (RECEITA, DESPESA, CUSTO) quando identificada, ou RESULTADO quando não; OUTROS para Contas de Apuração/compensação.
GRUPOS = {'ATIVO', 'PASSIVO', 'PATRIMONIO_LIQUIDO', 'RECEITA', 'DESPESA', 'CUSTO', 'RESULTADO', 'OUTROS'}


def agora():
    return dt.datetime.now().astimezone().isoformat()


def ler(p, padrao=None):
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else padrao


def gravar(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_name(p.name + '.' + secrets.token_hex(4) + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(p)


def limpo(v):
    return str(v or '').replace('|', ' ').replace('\r', ' ').replace('\n', ' ').strip()


def codigo_banco(v):
    nome = re.sub(r'[^A-Z0-9]', '', plano_dominio.chave(limpo(v)))
    # Identificação explícita, sem consulta de dados de clientes nem adivinhação por descrição do extrato.
    # Fonte: https://cms.santander.com.br/sites/WPS/documentos/arq-layout-de-arquivos-download-cob240esp/26-02-25_174335_h7815_layout_cobranc%CC%A7a_cnab_240_posicoes_padrao_santander_multibanco_feb_2026_v.8.5_%28espanhol%29.pdf
    if nome in ('SANTANDER','BANCOSANTANDER','BANCOSANTANDERBRASIL','BANCOSANTANDERBRASILSA','BCOSANTANDERBRASILSA'):
        return '033'
    if re.fullmatch(r'\d{1,3}', limpo(v)) and int(v) > 0:
        return limpo(v).zfill(3)
    raise ValueError(f"Banco '{limpo(v)}' não reconhecido. Informe o código numérico do banco (ex.: 033) ou Santander.")


def cnpj(v):
    n = re.sub(r'\D', '', str(v))
    if len(n) != 14 or len(set(n)) == 1:
        raise ValueError('Informe um CNPJ numérico com 14 dígitos válidos.')
    for tamanho, pesos in [(12, [5,4,3,2,9,8,7,6,5,4,3,2]), (13, [6,5,4,3,2,9,8,7,6,5,4,3,2])]:
        resto = sum(int(a)*b for a,b in zip(n[:tamanho], pesos)) % 11
        if int(n[tamanho]) != (0 if resto < 2 else 11-resto):
            raise ValueError('Dígitos verificadores do CNPJ inválidos.')
    return f'{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}'


def rotina(d) -> str:
    """Rotina operacional da empresa: CAIXINHA só por definição expressa; ausência = TRADICIONAL (nada muda para as existentes)."""
    r = (d or {}).get('rotina')
    tipo = (r or {}).get('tipo') if isinstance(r, dict) else r
    return 'CAIXINHA' if tipo == 'CAIXINHA' else 'TRADICIONAL'


class Empresas:
    def __init__(self, raiz, runtime):
        self.raiz, self.clientes, self.runtime = Path(raiz), Path(os.environ.get('AGENTES_PRIME_CLIENTES') or Path(raiz) / 'CLIENTES'), Path(runtime)

    def base(self, ident):
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{1,59}', ident) or ident.startswith('_'):
            raise ValueError('Identificador inválido; use letras maiúsculas, números e hífen.')
        p = self.clientes / ident
        if p.is_symlink() or p.resolve().parent != self.clientes.resolve():
            raise ValueError('Pasta de empresa inválida.')
        return p

    def obter(self, ident):
        p = self.base(ident)
        d = ler(p / 'empresa-local.json')
        if d is None:
            if (p / 'CADASTRO.md').exists():
                return {'id': ident, 'legado': True, 'aviso': 'Cadastro legado preservado; piloto financeiro não habilitado por esta tela.'}
            raise ValueError('Empresa não encontrada.')
        d = dict(d)
        d.update(producao_liberada=False)
        d['situacao'] = 'EXCLUIDA' if d.get('excluida') else ('ATIVA' if d.get('piloto') and d.get('cadastro_confirmado') else 'CADASTRO_PENDENTE')
        d['tipo_rotina'] = rotina(d)
        return d

    def listar(self, incluir_excluidas=False):
        """Empresas cadastradas. Cadastro EXCLUÍDO (exclusão lógica) só aparece quando pedido explicitamente (histórico)."""
        saida = [self.obter(p.name) for p in sorted(self.clientes.iterdir())
                 if re.fullmatch(r'[A-Z0-9][A-Z0-9-]{1,59}', p.name) and (p / 'CADASTRO.md').exists()]
        return saida if incluir_excluidas else [d for d in saida if not d.get('excluida')]

    def excluir(self, ident, d):
        """EXCLUSÃO LÓGICA do cadastro operacional: a empresa deixa de aceitar novas solicitações e sai da lista ativa. NADA é
        apagado (documentos, base inicial, solicitações, saídas, histórico e versões ficam preservados) e o identificador nunca é
        reutilizado. Piloto e confirmação do cadastro são revogados; um novo cadastro não herda autorizações."""
        atual = self.obter(ident)
        if atual.get('legado'):
            raise ValueError('Cadastro legado: a exclusão por esta tela não está disponível.')
        if atual.get('excluida'):
            raise ValueError('O cadastro desta empresa já foi excluído.')
        if d.get('confirmado') is not True or d.get('frase') != f'EXCLUIR {ident}':
            raise ValueError(f'Para excluir, digite exatamente: EXCLUIR {ident}')
        return self.atualizar(ident, {'excluida': {'em': agora(), 'por': 'Supervisor Contábil (tela Empresas)', 'frase': d['frase'],
                                                   'piloto_anterior': bool(atual.get('piloto'))},
                                      'piloto': False, 'cadastro_confirmado': False}, permitir_excluida=True)

    def cadastrar(self, d):
        ident = d.get('id', '')
        p = self.base(ident)
        if p.exists():
            raise ValueError('Identificador já existe; o cadastro existente foi preservado.')
        nome, regime = limpo(d.get('nome')), limpo(d.get('regime'))
        if not nome or not regime:
            raise ValueError('Razão social e regime tributário são obrigatórios.')
        numero = cnpj(d.get('cnpj'))
        for outro in self.listar():
            if outro.get('cnpj') == numero or numero in (self.base(outro['id']) / 'CADASTRO.md').read_text(encoding='utf-8'):
                raise ValueError('CNPJ já cadastrado.')
        d = {'id': ident, 'nome': nome, 'cnpj': numero, 'regime': regime, 'contas': [], 'plano': [],
             'cadastro_confirmado': False, 'piloto': False, 'criado_em': agora(), 'versao': 1}
        p.mkdir(parents=True)
        gravar(p / 'empresa-local.json', d)
        (p / 'REGRAS-BANCOS.md').write_text('# Regras bancárias\n\n## Regras\n| Regra | Versão | Condições | Tipo | Contrapartida | Exige suporte | Histórico | Origem | Situação | Aprovação |\n|---|---|---|---|---|---|---|---|---|---|\n', encoding='utf-8')
        self.sincronizar(d)
        return self.obter(ident)

    def sincronizar(self, d):
        p = self.base(d['id'])
        plano = p / 'PLANO-DE-CONTAS/PLANO-DE-CONTAS.md'
        plano.parent.mkdir(exist_ok=True)
        plano.write_text('# Plano de contas\n\n## Contas utilizadas\n| Código reduzido | Classificação | Descrição | Grupo | Tipo | Observação |\n|---|---|---|---|---|---|\n' + '\n'.join('| ' + ' | '.join(limpo(c.get(k)) for k in ('codigo','classificacao','descricao','grupo','tipo','observacao')) + ' |' for c in d['plano']), encoding='utf-8')
        contas = '\n'.join('| ' + ' | '.join(limpo(c[k]) for k in ('banco','agencia','conta','titular','contabil')) + ' | ATIVA |' for c in d['contas'])
        cadastro = f"# Cadastro — {d['id']}\n\n## Identificação\n- Razão social: {d['nome']}\n- CNPJ (matriz): {d['cnpj']}\n- Regime tributário: {d['regime']}\n\n## CNPJs do cliente\n| CNPJ | Tipo | Razão social | Observação |\n|---|---|---|---|\n| {d['cnpj']} | matriz | {d['nome']} | Cadastro informado pelo Supervisor |\n\n## Contas bancárias\n| Banco | Agência | Conta | Titular (CNPJ) | Conta contábil | Situação |\n|---|---|---|---|---|---|\n{contas}\n\n## Situação\n- Status: {'EXCLUIDO' if d.get('excluida') else 'CONFIGURAÇÃO / SIMULAÇÃO'}\n- Cadastro validado: {'SIM' if d['cadastro_confirmado'] else 'NÃO'}\n- Liberação de lançamentos reais: BLOQUEADA\n"
        if rotina(d) == 'CAIXINHA':
            # Rotina CAIXINHA (sem extrato bancário): o fluxo Financeiro/Bancos só é habilitado se houver vínculo bancário.
            cadastro += '- Rotina: CAIXINHA (Conciliação Caixinha; sem extrato bancário)\n'
            if d['piloto']:
                cadastro += '\n- Agente de Documentos: PILOTO SUPERVISIONADO AUTORIZADO\n- Conciliação Caixinha: PILOTO SIMULACAO AUTORIZADO\n'
                if d['contas']:
                    cadastro += '- Financeiro/Bancos local: PILOTO SIMULACAO AUTORIZADO\n'
        elif d['piloto']:
            cadastro += '\n- Agente de Documentos: PILOTO SUPERVISIONADO AUTORIZADO\n- Financeiro/Bancos local: PILOTO SIMULACAO AUTORIZADO\n'
        # Indicação expressa do Supervisor (lida pelo Coordenador e por Contabilidade/Bancos); sem linha, nenhuma conta é aceita.
        adiantamentos = d.get('contas_adiantamento') or {}
        if adiantamentos:
            cadastro += ('\n## Contas de adiantamento indicadas pelo Supervisor\n'
                         '| Natureza | Conta contábil | Descrição | Indicada em | Justificativa |\n|---|---|---|---|---|\n'
                         + '\n'.join(f"| {n} | {limpo(c['conta'])} | {limpo(c.get('descricao'))} | {limpo(c.get('indicada_em'))} | "
                                     f"{limpo(c.get('justificativa'))} |" for n, c in sorted(adiantamentos.items())) + '\n')
        (p / 'CADASTRO.md').write_text(cadastro, encoding='utf-8')

    def atualizar(self, ident, mudancas, permitir_excluida=False):
        d = self.obter(ident)
        if d.get('legado'):
            raise ValueError('Edição do cadastro legado não está disponível; arquivos preservados.')
        if d.get('excluida') and not permitir_excluida:
            raise ValueError('O cadastro desta empresa foi excluído; nenhuma alteração é feita. Os históricos continuam disponíveis.')
        p = self.base(ident)
        anterior = ler(p / 'empresa-local.json')
        gravar(p / 'VERSOES' / f"cadastro-{anterior['versao']:04d}-{secrets.token_hex(3)}.json", anterior)
        anterior.update(mudancas, versao=anterior['versao']+1, atualizado_em=agora())
        gravar(p / 'empresa-local.json', anterior)
        self.sincronizar(anterior)
        return self.obter(ident)

    def previa(self, ident, d):
        if d.get('finalidade') not in (None, 'plano'):
            raise ValueError('O estudo por razão foi removido. Esta importação é somente para o plano de contas.')
        empresa = self.obter(ident)
        nome = Path(limpo(d.get('nome'))).name
        try:
            dados = base64.b64decode(d.get('conteudo', ''), validate=True)
        except Exception:
            raise ValueError('Arquivo inválido.')
        if not dados or len(dados) > 10*1024*1024:
            raise ValueError('Envie um arquivo de até 10 MB.')
        ext = Path(nome).suffix.lower()
        if ext in ('.csv', '.txt'):
            try:
                texto = dados.decode('utf-8-sig')
            except UnicodeDecodeError:
                texto = dados.decode('cp1252')
            try:
                dialect = csv.Sniffer().sniff(texto[:8000], delimiters=';,\t')
            except csv.Error:
                dialect = csv.excel
            linhas = list(csv.reader(io.StringIO(texto), dialect))
        elif ext == '.xls':
            from python_calamine import CalamineWorkbook
            try:
                with CalamineWorkbook.from_filelike(io.BytesIO(dados)) as wb:
                    aba = wb.get_sheet_by_index(0)
                    if aba.height > 10020 or aba.width > 60:
                        raise ValueError('Planilha acima de 10.000 registros / 60 colunas.')
                    linhas = [[plano_dominio.texto(v) for v in r] for r in aba.to_python()]
            except ValueError:
                raise
            except Exception as e:
                raise ValueError('Não foi possível ler o XLS. Confira o arquivo exportado pelo sistema.') from e
        elif ext == '.xlsx':
            from openpyxl import load_workbook
            import zipfile
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                if sum(i.file_size for i in z.infolist()) > 60*1024*1024:
                    raise ValueError('Planilha excede o limite descompactado.')
            wb = load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
            try:
                aba = wb.worksheets[0]
                if (aba.max_row or 0) > 10020 or (aba.max_column or 0) > 60:
                    raise ValueError('Planilha acima de 10.000 registros / 60 colunas.')
                linhas = [[plano_dominio.texto(v) for v in row] for row in aba.iter_rows(max_row=10020, max_col=60, values_only=True)]
            finally:
                wb.close()
        else:
            raise ValueError('Importação tabular: CSV, TXT delimitado, XLS ou XLSX. PDF requer preparação prévia.')
        origem = None
        finalidade = 'plano'
        reconhecido = plano_dominio.reconhecer(linhas, empresa)
        if reconhecido:
            linhas, origem = reconhecido
        linhas = [l for l in linhas if any(str(v).strip() for v in l)]
        if not linhas or len(linhas) > 10001 or max(map(len, linhas)) > 60:
            raise ValueError('Tabela vazia ou acima de 10.000 registros / 60 colunas.')
        automatico = colunas_automaticas.reconhecer(linhas, finalidade)
        if automatico:
            automatico['finalidade'] = finalidade
        token = secrets.token_hex(16)
        gravar(self.runtime / 'previas' / f'{token}.json', {'empresa': ident, 'nome': nome, 'sha256': hashlib.sha256(dados).hexdigest(), 'linhas': linhas, 'origem': origem, 'automatico': automatico})
        return {'token': token, 'linhas': linhas[:12], 'total': len(linhas)-1, 'origem': origem,
                'automatico': bool(automatico), 'mapa_sugerido': automatico['mapa'] if automatico else None}

    def tabela(self, ident, d, obrigatorios):
        token = d.get('token', '')
        if not re.fullmatch('[a-f0-9]{32}', token):
            raise ValueError('Prévia inválida.')
        arq = ler(self.runtime / 'previas' / f'{token}.json')
        if not arq or arq['empresa'] != ident:
            raise ValueError('Prévia de outra empresa ou não encontrada.')
        if (arq.get('automatico') or {}).get('finalidade') == 'razao' or (arq.get('origem') or {}).get('formato') == 'DOMINIO_RAZAO':
            raise ValueError('Prévia de razão desativada; envie o plano de contas.')
        automatico = arq.get('automatico') or {}
        cab = int(d.get('cabecalho', automatico.get('cabecalho', 1)))-1
        if not 0 <= cab < min(len(arq['linhas']), 20):
            raise ValueError('Linha de cabeçalho inválida.')
        mapa = d.get('mapa', automatico.get('mapa', {}))
        if (arq.get('origem') or {}).get('formato') == 'DOMINIO_RELACAO_CONTAS':
            fixo = {'codigo': 0, 'classificacao': 1, 'descricao': 2, 'tipo': 4}
            if cab != 0 or any(str(mapa.get(k)) != str(v) for k,v in fixo.items()) or mapa.get('grupo') not in (None, '', 3, '3'):
                raise ValueError('Use o cabeçalho e as colunas reconhecidas do Domínio para preservar todas as contas.')
        if any(mapa.get(k) in ('', None) for k in obrigatorios):
            raise ValueError('Mapeie os campos obrigatórios: ' + ', '.join(obrigatorios))
        if len(set(int(v) for v in mapa.values() if v not in ('', None))) != len([v for v in mapa.values() if v not in ('', None)]):
            raise ValueError('A mesma coluna não pode representar dois campos.')
        linhas = []
        for n, linha in enumerate(arq['linhas'][cab+1:], cab+2):
            r = {'linha': n}
            for k, v in mapa.items():
                if v in ('', None):
                    r[k] = ''
                else:
                    i = int(v)
                    if i < 0 or i >= 60:
                        raise ValueError('Coluna inválida.')
                    r[k] = limpo(linha[i] if i < len(linha) else '')
            if (arq.get('origem') or {}).get('linhas_origem'):
                r['linha_origem'] = arq['origem']['linhas_origem'][n-2]
            linhas.append(r)
        return arq, linhas

    def plano(self, ident, d):
        arq, linhas = self.tabela(ident, d, ('codigo','classificacao','descricao'))
        erros, avisos, usados, classes = [], [], set(), set()
        for c in linhas:
            c['grupo'] = plano_dominio.chave(c.get('grupo', '')).replace(' ', '_')
            tipo = plano_dominio.chave(c.get('tipo', ''))
            c['tipo'] = {'A': 'ANALITICA', 'S': 'SINTETICA'}.get(tipo, tipo)
            if not re.fullmatch(r'\d+', c.get('codigo','')) or c['codigo'] in usados:
                erros.append(f"Linha {c['linha']}: código reduzido inválido ou duplicado.")
            if not c.get('classificacao') or not c.get('descricao'):
                erros.append(f"Linha {c['linha']}: classificação ou descrição ausente.")
            if c.get('classificacao') in classes:
                avisos.append(f"Conta {c.get('codigo')}: classificação {c['classificacao']} repetida em outro código reduzido. Ambas preservadas; confira no sistema de origem.")
            if c['grupo'] and c['grupo'] not in GRUPOS:
                erros.append(f"Linha {c['linha']}: Grupo '{c['grupo']}' não reconhecido. Use ATIVO, PASSIVO, PATRIMONIO_LIQUIDO, RECEITA, DESPESA, CUSTO, RESULTADO ou OUTROS.")
            if c['tipo'] and c['tipo'] not in ('ANALITICA','SINTETICA'):
                erros.append(f"Linha {c['linha']}: Tipo '{c['tipo']}' não reconhecido. Use A/Analítica ou S/Sintética.")
            if not c['grupo'] or not c['tipo']:
                avisos.append(f"Conta {c.get('codigo')}: Grupo/Tipo ainda não definido; não utilizar em decisões até conferência.")
            usados.add(c.get('codigo')); classes.add(c.get('classificacao'))
        atual = self.obter(ident)
        novas = {c['codigo']: c for c in linhas}
        for banco in atual.get('contas', []):
            if banco['contabil'] not in novas or novas[banco['contabil']]['grupo'] != 'ATIVO':
                erros.append('Plano remove ou altera a conta bancária ' + banco['contabil'])
        impactos = []
        regras = (self.base(ident) / 'REGRAS-BANCOS.md').read_text(encoding='utf-8')
        for anterior in atual.get('plano', []):
            novo = novas.get(anterior['codigo'])
            if novo != anterior:
                impactos.append('Conta alterada/removida: ' + anterior['codigo'])
                if re.search(r'\|\s*'+re.escape(anterior['codigo'])+r'\s*\|', regras):
                    erros.append('Conta usada em regra existente foi alterada/removida: ' + anterior['codigo'] + '. Revise a regra antes de atualizar o plano.')
        if not d.get('salvar'):
            return {'contas': linhas[:50], 'total': len(linhas), 'erros': erros[:100], 'avisos': avisos[:100], 'impactos': impactos[:100],
                    'contas_removidas': [{'codigo': c['codigo'], 'descricao': c.get('descricao', '')} for c in atual.get('plano', []) if c['codigo'] not in novas],
                    'aviso': 'Confira também as regras existentes antes de confirmar uma nova versão do plano.'}
        if erros or not d.get('confirmado'):
            raise ValueError('Plano não salvo: corrija os erros e confirme a conferência da nova versão.')
        # Alterar plano invalida a confirmação do cadastro e a habilitação do piloto.
        return self.atualizar(ident, {'plano': linhas, 'plano_origem': {k: arq.get(k) for k in ('nome','sha256','origem')},
                                     'cadastro_confirmado': False, 'piloto': False})

    def definir_conta(self, ident, d):
        atual = self.obter(ident)
        contas = atual.get('plano', [])
        c = next((c for c in contas if c['codigo']==d.get('codigo')), None)
        if not c or d.get('grupo') not in GRUPOS or d.get('tipo') not in ('ANALITICA','SINTETICA') or not d.get('confirmado'):
            raise ValueError('Selecione uma conta, defina Grupo e Tipo e confirme sua conferência.')
        if any(b['contabil']==c['codigo'] for b in atual.get('contas', [])) and (d['grupo']!='ATIVO' or d['tipo']!='ANALITICA'):
            raise ValueError('Conta vinculada a banco deve permanecer analítica do grupo ATIVO.')
        texto = (self.base(ident) / 'REGRAS-BANCOS.md').read_text(encoding='utf-8')
        if re.search(r'\|\s*'+re.escape(c['codigo'])+r'\s*\|',texto) and (c.get('grupo')!=d['grupo'] or c.get('tipo')!=d['tipo']):
            raise ValueError('Conta usada por regra existente; revise a regra antes de alterar Grupo/Tipo.')
        c.update(grupo=d['grupo'],tipo=d['tipo'],definido_em=agora())
        return self.atualizar(ident, {'plano':contas, 'cadastro_confirmado':False,'piloto':False})

    def criar_conta(self, ident, d):
        """Criação EXPRESSA de conta/subconta pelo Supervisor (nunca automática). A conta fica 'cadastrada no aplicativo' com
        correspondência no Domínio PENDENTE (a exportação TXT recusa lançamentos nela até a confirmação) e SEM saldo inicial presumido."""
        atual = self.obter(ident)
        if atual.get('legado'):
            raise ValueError('Cadastro legado: criação de contas não disponível por esta tela.')
        if d.get('confirmado') is not True:
            raise ValueError('Confira os dados e confirme a criação da conta.')
        codigo, classificacao, descricao = limpo(d.get('codigo')), limpo(d.get('classificacao')), limpo(d.get('descricao'))
        superior, tipo, grupo = limpo(d.get('superior')), limpo(d.get('tipo')).upper(), limpo(d.get('grupo')).upper()
        faltas = [n for n, v in (('código reduzido', codigo), ('classificação', classificacao), ('descrição', descricao), ('tipo', tipo),
                                 ('grupo', grupo)) if not v]
        if faltas:
            raise ValueError('Campos obrigatórios: ' + ', '.join(faltas) + '.')
        if not re.fullmatch(r'\d{1,10}', codigo):
            raise ValueError('Código reduzido: somente números (até 10 dígitos).')
        if not re.fullmatch(r'\d+(?:\.\d+)*', classificacao):
            raise ValueError('Classificação inválida: use números separados por ponto (ex.: 1.1.2.01.000010).')
        if not 2 <= len(descricao) <= 120:
            raise ValueError('Descrição: de 2 a 120 caracteres.')
        if tipo not in ('ANALITICA', 'SINTETICA'):
            raise ValueError('Tipo: ANALITICA ou SINTETICA.')
        if grupo not in GRUPOS:
            raise ValueError('Grupo: ' + ', '.join(sorted(GRUPOS)) + '.')
        plano = [dict(c) for c in atual.get('plano', [])]
        if any(c['codigo'] == codigo for c in plano):
            raise ValueError(f'Código reduzido {codigo} já existe no plano desta empresa; códigos nunca são reutilizados nem substituídos.')
        if any(c.get('classificacao') == classificacao for c in plano):
            raise ValueError(f'Classificação {classificacao} já existe no plano desta empresa.')
        if superior:
            sup = next((c for c in plano if c.get('classificacao') == superior), None)
            if not sup:
                raise ValueError(f'Conta superior {superior} inexistente no plano desta empresa.')
            if sup.get('tipo') not in ('SINTETICA', 'SINTÉTICA'):
                raise ValueError(f'Conta superior {superior} não é sintética: conta analítica não recebe subcontas.')
            if not classificacao.startswith(superior + '.') or classificacao.count('.') != superior.count('.') + 1:
                raise ValueError(f'A classificação deve ser um nível abaixo da conta superior ({superior}.xxx).')
            if sup.get('grupo') and sup['grupo'] != grupo:
                raise ValueError(f"Grupo {grupo} diferente do grupo da conta superior ({sup['grupo']}).")
        elif '.' in classificacao:
            raise ValueError('Informe a conta superior (sintética) da nova conta.')
        nova = {'linha': 'criada no aplicativo', 'codigo': codigo, 'classificacao': classificacao, 'descricao': descricao, 'grupo': grupo,
                'tipo': tipo, 'observacao': 'criada no aplicativo; correspondência no Domínio pendente', 'superior': superior or None,
                'origem': 'CRIADA_NO_APLICATIVO', 'dominio': 'PENDENTE_CONFERENCIA', 'criada_em': agora(),
                'criada_por': 'Supervisor Contábil (tela Empresas)'}
        plano.append(nova)
        r = self.atualizar(ident, {'plano': plano, 'cadastro_confirmado': False, 'piloto': False})
        import base_inicial
        base_inicial.BaseInicial(self).reabrir_por_mudanca(ident, f'conta {codigo} criada no aplicativo (saldo inicial exige definição)')
        return r

    def conta_dominio(self, ident, d):
        """Confirma, por declaração do Supervisor, que a conta criada no aplicativo existe no Domínio com o MESMO código reduzido.
        O aplicativo não cria nem consulta contas no Domínio."""
        atual = self.obter(ident)
        plano = [dict(c) for c in atual.get('plano', [])]
        c = next((c for c in plano if c['codigo'] == limpo(d.get('codigo'))), None)
        if not c or c.get('dominio') != 'PENDENTE_CONFERENCIA':
            raise ValueError('Selecione uma conta criada no aplicativo com correspondência pendente.')
        just = limpo(d.get('justificativa'))
        if d.get('confirmado') is not True or not 5 <= len(just) <= 300:
            raise ValueError('Confirme que a conta existe no Domínio com o mesmo código e informe uma justificativa (5 a 300 caracteres).')
        c.update(dominio='CONFIRMADA_NO_DOMINIO', dominio_confirmacao={'em': agora(), 'justificativa': just,
                                                                     'por': 'Supervisor Contábil (tela Empresas)'},
                 observacao='criada no aplicativo; existência no Domínio declarada pelo Supervisor')
        return self.atualizar(ident, {'plano': plano})

    def bancos(self, ident, d):
        atual = self.obter(ident)
        plano = {c['codigo']: c for c in atual.get('plano', [])}
        contas, chaves = [], {}
        for linha, c in enumerate(d.get('contas', []), 1):
            c = {k: limpo(c.get(k)) for k in ('banco','agencia','conta','titular','contabil')}
            if not all(c.values()) or cnpj(c['titular']) != atual['cnpj']:
                raise ValueError('Preencha todos os campos e use a titularidade do próprio cliente.')
            c['titular'] = atual['cnpj']
            informado = c['banco']
            c['banco'] = codigo_banco(informado)
            c['banco_informado'] = informado
            for campo, rotulo in (('agencia','Agência'),('conta','Conta')):
                if not re.fullmatch(r'[0-9. /-]+[Xx]?',c[campo]) or not re.search(r'\d',c[campo]):
                    raise ValueError(f'Linha {linha}: {rotulo} inválida. Confira os dígitos e o eventual dígito verificador.')
            p = plano.get(c['contabil'], {})
            if p.get('grupo') != 'ATIVO' or p.get('tipo') not in ('ANALITICA','ANALÍTICA'):
                raise ValueError('Banco exige conta analítica do grupo ATIVO no plano.')
            chave = (c['banco'],re.sub(r'\D','',c['agencia']).lstrip('0') or '0',re.sub(r'\D','',c['conta']).lstrip('0'))
            if not chave[2]:
                raise ValueError(f'Linha {linha}: número da conta inválido; não pode conter somente zeros.')
            if chave in chaves:
                raise ValueError(f'Conta bancária duplicada nas linhas {chaves[chave]} e {linha}. Mantenha apenas uma linha para o mesmo banco, agência e conta.')
            chaves[chave]=linha; contas.append(c)
        return self.atualizar(ident, {'contas': contas, 'cadastro_confirmado': False, 'piloto': False})

    def habilitar(self, ident, d):
        atual = self.obter(ident)
        faltas = []
        if not atual.get('plano'): faltas.append('Importe e confira o plano de contas.')
        if rotina(atual) == 'CAIXINHA':
            # Rotina CAIXINHA: não há extrato; no lugar do vínculo bancário, a conta Caixa Geral da configuração da rotina.
            import regras_caixinha
            try:
                cfg = (regras_caixinha.ler(self.base(ident)) or {}).get('configuracao') or {}
            except (OSError, ValueError):
                cfg = {}
            if not (cfg.get('contas') or {}).get('CAIXA_GERAL'):
                faltas.append('Rotina Caixinha: salve a configuração com a conta Caixa Geral (Conciliação Caixinha → Configuração).')
        elif not atual.get('contas'): faltas.append('Salve ao menos um vínculo bancário na etapa 2.')
        if d.get('frase') != f'CONFIRMO PILOTO {ident}': faltas.append(f'Digite exatamente: CONFIRMO PILOTO {ident}.')
        if faltas:
            raise ValueError(' '.join(faltas))
        return self.atualizar(ident, {'cadastro_confirmado': True, 'piloto': True,
                                    'autorizacao_piloto': {'em': agora(), 'frase': d['frase'], 'modo': 'SIMULACAO'}})

    def definir_rotina(self, ident, d):
        """Tipo de rotina da empresa: TRADICIONAL (padrão; processos financeiros/bancários existentes) ou CAIXINHA (Conciliação
        Caixinha, sem extrato). Mudança expressa do Supervisor, versionada no cadastro; altera a vigência das conferências."""
        atual = self.obter(ident)
        if atual.get('legado'):
            raise ValueError('Cadastro legado: a rotina não pode ser definida por esta tela.')
        tipo = limpo(d.get('rotina')).upper()
        just = limpo(d.get('justificativa'))
        if tipo not in ('TRADICIONAL', 'CAIXINHA'):
            raise ValueError('Rotina deve ser TRADICIONAL ou CAIXINHA.')
        if d.get('confirmado') is not True or not 5 <= len(just) <= 300:
            raise ValueError('Confirme a rotina e informe uma justificativa (5 a 300 caracteres).')
        if rotina(atual) == tipo:
            return atual
        # trocar de rotina revoga a habilitação do piloto: a nova rotina tem exigências próprias (vínculo bancário ou Caixa Geral)
        return self.atualizar(ident, {'rotina': {'tipo': tipo, 'definida_em': agora(), 'por': 'Supervisor Contábil', 'justificativa': just},
                                      'cadastro_confirmado': False, 'piloto': False})

    def contas_adiantamento(self, ident, d):
        """Indicação EXPRESSA, pelo Supervisor, da conta de adiantamento da empresa (uma por natureza). Não classifica nada
        automaticamente: só habilita essa conta em decisões específicas por movimento, que continuam sem suprir documento."""
        exigido = {'ADIANTAMENTO_FORNECEDOR': 'ATIVO', 'ADIANTAMENTO_CLIENTE': 'PASSIVO'}
        natureza = d.get('natureza')
        if natureza not in exigido:
            raise ValueError('Natureza deve ser ADIANTAMENTO_FORNECEDOR ou ADIANTAMENTO_CLIENTE.')
        atual = self.obter(ident)
        if atual.get('legado'):
            raise ValueError('Cadastro legado: a indicação de conta de adiantamento não está disponível por esta tela.')
        indicadas = dict(atual.get('contas_adiantamento') or {})
        if d.get('remover') is True:
            if d.get('confirmado') is not True:
                raise ValueError('Confirme a remoção da indicação.')
            indicadas.pop(natureza, None)
            return self.atualizar(ident, {'contas_adiantamento': indicadas})
        justificativa = limpo(d.get('justificativa'))
        if d.get('confirmado') is not True or not 5 <= len(justificativa) <= 300 or '|' in justificativa:
            raise ValueError('Confirme a indicação e informe uma justificativa (5 a 300 caracteres, sem "|").')
        conta = next((c for c in atual.get('plano', []) if c['codigo'] == limpo(d.get('conta'))), None)
        if not conta:
            raise ValueError('Conta inexistente no plano de contas desta empresa.')
        if conta.get('tipo') not in ('ANALITICA', 'ANALÍTICA') or conta.get('grupo') != exigido[natureza]:
            raise ValueError(f'{natureza} exige conta analítica do grupo {exigido[natureza]} no plano desta empresa.')
        if any(b['contabil'] == conta['codigo'] for b in atual.get('contas', [])):
            raise ValueError('Conta contábil de banco da própria empresa não pode ser conta de adiantamento.')
        indicadas[natureza] = {'conta': conta['codigo'], 'descricao': conta.get('descricao', ''), 'justificativa': justificativa,
                               'indicada_em': agora(), 'indicada_por': 'Supervisor Contábil (tela Empresas)'}
        return self.atualizar(ident, {'contas_adiantamento': indicadas})

    def parametros_bancarios(self, ident, d):
        raise ValueError('Classificação automática em adiantamentos removida pelo Supervisor; use decisão específica por movimento.')

