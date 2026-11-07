"""Contabilidade: propostas a partir dos fatos do Fiscal, sem lançamentos bancários nem escrituração."""
import argparse
import hashlib
import json
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

RAIZ=Path(__file__).resolve().parents[4]


def clientes():
    """Pasta CLIENTES (avaliada a cada uso: AGENTES_PRIME_CLIENTES em testes isolados; RAIZ/CLIENTES em produção)."""
    return Path(os.environ.get("AGENTES_PRIME_CLIENTES") or RAIZ / "CLIENTES")


sys.path.insert(0,str(RAIZ/'AGENTES/CONTABILIDADE/BANCOS/ferramentas'))
from lancamentos_bancarios import tabela_md, norm
sys.path.insert(0,str(RAIZ/'AGENTES/CONTABILIDADE'))
import governanca_regras as gov
import calendar


# Lista explícita (nomes PT/EN e códigos ISO alfa-3). Igualdade exata após normalização; nada é presumido por semelhança.
PAISES_ESTRANGEIROS={
    'ESTADOS UNIDOS':('ESTADOS UNIDOS','ESTADOS UNIDOS DA AMERICA','EUA','UNITED STATES','UNITED STATES OF AMERICA','USA'),
    'INDIA':('INDIA','IND'),'PORTUGAL':('PORTUGAL','PRT'),'ARGENTINA':('ARGENTINA','ARG'),'CHILE':('CHILE','CHL'),
    'URUGUAI':('URUGUAI','URUGUAY','URY'),'PARAGUAI':('PARAGUAI','PARAGUAY','PRY'),'COLOMBIA':('COLOMBIA','COL'),
    'PERU':('PERU','PER'),'MEXICO':('MEXICO','MEX'),'CANADA':('CANADA','CAN'),
    'REINO UNIDO':('REINO UNIDO','UNITED KINGDOM','GBR'),'ALEMANHA':('ALEMANHA','GERMANY','DEU'),
    'FRANCA':('FRANCA','FRANCE','FRA'),'ESPANHA':('ESPANHA','SPAIN','ESP'),'ITALIA':('ITALIA','ITALY','ITA'),
    'PAISES BAIXOS':('PAISES BAIXOS','HOLANDA','NETHERLANDS','NLD'),'BELGICA':('BELGICA','BELGIUM','BEL'),
    'SUICA':('SUICA','SWITZERLAND','CHE'),'IRLANDA':('IRLANDA','IRELAND','IRL'),'LUXEMBURGO':('LUXEMBURGO','LUXEMBOURG','LUX'),
    'AUSTRIA':('AUSTRIA','AUT'),'SUECIA':('SUECIA','SWEDEN','SWE'),'NORUEGA':('NORUEGA','NORWAY','NOR'),
    'DINAMARCA':('DINAMARCA','DENMARK','DNK'),'FINLANDIA':('FINLANDIA','FINLAND','FIN'),'POLONIA':('POLONIA','POLAND','POL'),
    'ESTONIA':('ESTONIA','EST'),'ISRAEL':('ISRAEL','ISR'),'EMIRADOS ARABES UNIDOS':('EMIRADOS ARABES UNIDOS','UNITED ARAB EMIRATES','ARE'),
    'JAPAO':('JAPAO','JAPAN','JPN'),'CHINA':('CHINA','CHN'),'HONG KONG':('HONG KONG','HKG'),
    'COREIA DO SUL':('COREIA DO SUL','SOUTH KOREA','KOR'),'SINGAPURA':('SINGAPURA','SINGAPORE','SGP'),
    'AUSTRALIA':('AUSTRALIA','AUS'),'NOVA ZELANDIA':('NOVA ZELANDIA','NEW ZEALAND','NZL'),
    'AFRICA DO SUL':('AFRICA DO SUL','SOUTH AFRICA','ZAF')}
_ALIAS_PAIS={a:k for k,v in PAISES_ESTRANGEIROS.items() for a in v}
BRASIL=('BR','BRA','BRASIL','BRAZIL','REPUBLICA FEDERATIVA DO BRASIL')
TRIBUTOS_SOBRE_RECEITA=('ISS','PIS','COFINS')
COMPETENCIA=re.compile(r'20\d{2}-(0[1-9]|1[0-2])')


def classificar_pais(pais):
    """('ESTRANGEIRO', nome) | ('BRASIL', None) | ('NAO_RECONHECIDO', texto) | ('AUSENTE', None)."""
    p=norm(pais)
    if not p: return 'AUSENTE',None
    if p in BRASIL: return 'BRASIL',None
    if p in _ALIAS_PAIS: return 'ESTRANGEIRO',_ALIAS_PAIS[p]
    return 'NAO_RECONHECIDO',p


def redutora(conta):
    """Conta redutora identificada no plano pela marca "(-)" na descrição (padrão do Domínio)."""
    return bool(re.match(r'^\(\s*-\s*\)',norm(conta.get('DESCRICAO'))))


def vigente(competencia, desde, ate):
    """None = vigente; texto = motivo. Fim ausente não é inventado (apenas registrado nos limites)."""
    for nome,v in (('início',desde),('fim',ate)):
        if v is not None and not COMPETENCIA.fullmatch(str(v)): return f'Vigência ({nome}) inválida nas referências fiscais.'
    if desde is not None and competencia<desde: return 'Referência fiscal ainda não vigente nesta competência.'
    if ate is not None and competencia>ate: return 'Referência fiscal encerrada antes desta competência (fim de vigência).'
    return None


def verificar_tomador(d, regra, faltas):
    situacao,nome=classificar_pais(d.get('pais_tomador'))
    cnpj_br=len(re.sub(r'\D','',str(d.get('destinatario_cnpj') or '')))==14
    id_ext=bool(str(d.get('tomador_id_exterior') or '').strip())
    if situacao=='ESTRANGEIRO' and cnpj_br:
        faltas.append(f'Conflito: país do tomador {nome} e CNPJ brasileiro do tomador no mesmo documento; conferir antes da conta de clientes.')
    if situacao=='BRASIL' and id_ext:
        faltas.append('Conflito: país do tomador Brasil e identificador fiscal estrangeiro do tomador; conferir antes da conta de clientes.')
    if regra.get('tomador_exterior'):
        if situacao=='AUSENTE': faltas.append('País do tomador ausente; a referência é de clientes no exterior.')
        elif situacao=='BRASIL': faltas.append('País do tomador é Brasil; a referência é de clientes no exterior.')
        elif situacao=='NAO_RECONHECIDO':
            faltas.append(f'País do tomador "{nome}" não reconhecido na lista explícita de países estrangeiros; não presumir exterior.')
    elif situacao=='ESTRANGEIRO' or (id_ext and situacao!='BRASIL'):
        faltas.append('Tomador indicado no exterior, mas a referência desta empresa não é de clientes no exterior; conferir natureza e conta.')


def cnpjs_empresa(base):
    """CNPJ(s) da empresa: cadastro local (empresa-local.json) ou, na falta dele, o CADASTRO.md (cadastro anterior)."""
    local=base/'empresa-local.json'
    if local.is_file():
        return {re.sub(r'\D','',json.loads(local.read_text(encoding='utf-8')).get('cnpj',''))}
    cad=base/'CADASTRO.md'
    if not cad.is_file(): raise ValueError('Cadastro da empresa ausente (empresa-local.json e CADASTRO.md).')
    achados={re.sub(r'\D','',c) for c in re.findall(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}',cad.read_text(encoding='utf-8'))}
    if not achados: raise ValueError('CNPJ da empresa não identificado no CADASTRO.md.')
    return achados


def data_lancamento(pol, competencia, d):
    """(data ISO | None, motivo). Data do LANÇAMENTO separada da competência do fato; nunca presumida."""
    if not pol['aplicavel']: return None, pol['motivo']
    if pol['politica']=='ULTIMO_DIA_COMPETENCIA':
        a,m=map(int,competencia.split('-')); return f'{competencia}-{calendar.monthrange(a,m)[1]:02d}', None
    emissao=str(d.get('data_emissao') or '')
    if pol['politica']=='DATA_EMISSAO_DOCUMENTO' and re.fullmatch(r'\d{4}-\d{2}-\d{2}',emissao): return emissao, None
    return None, 'Política DATA_EMISSAO_DOCUMENTO sem data de emissão documentada neste documento; data não presumida.'


def gerar(empresa, competencia, sol, fiscal):
    if (fiscal.get('contrato'),fiscal.get('empresa'),fiscal.get('competencia'),fiscal.get('sol')) != ('FISCAL_LOCAL_V1',empresa,competencia,sol):
        raise ValueError('Retorno Fiscal de outra empresa, competência ou SOL.')
    if fiscal.get('modo')!='SIMULACAO': raise ValueError('Fiscal restrito à SIMULACAO.')
    base=clientes()/empresa; fonte=base/'REGRAS-FISCAIS.json'
    cnpjs=cnpjs_empresa(base)
    regras={}; aviso=None; limites_extra=[]; dados_regras={}
    if fonte.exists():
        r=json.loads(fonte.read_text(encoding='utf-8')); dados_regras=r
        if (r.get('contrato'),r.get('empresa')) != ('REFERENCIAS_FISCAIS_V1',empresa) or re.sub(r'\D','',str(r.get('cnpj',''))) not in cnpjs:
            raise ValueError('Referências fiscais não correspondem à empresa/CNPJ.')
        aviso=('Referências fiscais sem início de vigência (competencia_desde) declarado.' if r.get('competencia_desde') is None
               else vigente(competencia,r.get('competencia_desde'),r.get('competencia_ate')))
        if not aviso: regras=r.get('referencias',{})
        if r.get('competencia_ate') is None and not aviso:
            limites_extra.append('Referências fiscais sem fim de vigência declarado: válidas até revisão do Supervisor; nenhuma data foi presumida.')
    else: aviso='Referências contábeis fiscais desta empresa ainda não definidas pelo Supervisor.'
    plano={c['CODIGO REDUZIDO']:c for c in tabela_md((base/'PLANO-DE-CONTAS/PLANO-DE-CONTAS.md').read_text(encoding='utf-8'),'Contas utilizadas')}
    pol=gov.politica_data(dados_regras,'FISCAL',empresa,competencia,base)
    lancamentos=[]; sem_proposta=[]
    for d in fiscal['documentos']:
        if d.get('duplicado_de'): continue
        if d['tipo']=='GUIA':
            # guia não gera provisão nem despesa: é suporte da liquidação, proposta por Contabilidade/Bancos
            sem_proposta.append({'documento':d['id'],'arquivo':d['arquivo'],'tipo':'GUIA','pendencias':d['pendencias'],
                                 'motivo':'Guia é cobrança de obrigação; liquidação proposta por Contabilidade/Bancos; não gera provisão.'})
            continue
        evento='RECEITA_SERVICOS' if d['tipo']=='NFSE' and d['papel_empresa']=='PRESTADOR_EMITENTE' else d.get('tributo') if d['tipo']=='APURACAO_TRIBUTO' else None
        regra=regras.get(evento,{}) if evento else {}
        faltas=list(d['pendencias']); debito=credito=None; governanca=None
        if aviso: faltas.append(aviso)
        if regra:
            motivo=vigente(competencia,regra.get('competencia_desde'),regra.get('competencia_ate'))
            if motivo: faltas.append(motivo); regra={}
        if regra:
            av=gov.avaliar(regra,'FISCAL',empresa,evento,competencia,base); governanca=av['governanca']
            if not av['aplicavel']: faltas.append(av['motivo']); regra={}
        if not regra: faltas.append('Natureza e contas do fato fiscal não definidas para esta empresa; não usar o total da guia como nova despesa.')
        else:
            if evento=='RECEITA_SERVICOS': verificar_tomador(d,regra,faltas)
            # Tributos sobre faturamento podem debitar dedução da receita (ex.: 60201 "(-) ISS" da State), nunca a receita bruta.
            grupos={'RECEITA_SERVICOS':({'ATIVO'},{'RECEITA'}),'ISS':({'DESPESA','RECEITA'},{'PASSIVO'}),
                    'IRPJ':({'DESPESA'},{'PASSIVO'}),'CSLL':({'DESPESA'},{'PASSIVO'}),
                    'PIS':({'DESPESA','RECEITA'},{'PASSIVO'}),'COFINS':({'DESPESA','RECEITA'},{'PASSIVO'})}
            for lado,grupo in zip(('debito','credito'),grupos.get(evento,(set(),set()))):
                c=plano.get(str(regra.get(lado,'')))
                if not c or norm(c.get('TIPO'))!='ANALITICA' or norm(c.get('GRUPO')) not in grupo:
                    faltas.append('Conta de '+lado+' ausente, sintética ou de grupo incompatível no plano desta empresa.'); continue
                if (lado=='debito' and evento in TRIBUTOS_SOBRE_RECEITA and norm(c.get('GRUPO'))=='RECEITA'
                        and not (redutora(c) or str(regra.get('conta_redutora_receita',''))==c['CODIGO REDUZIDO'])):
                    faltas.append('Débito do tributo em conta de RECEITA que não é redutora identificada: exigir descrição "(-)" no plano '
                                  'ou "conta_redutora_receita" documentada na referência da empresa.'); continue
                if lado=='credito' and evento=='RECEITA_SERVICOS' and redutora(c):
                    faltas.append('Receita de serviços não pode ser creditada em conta redutora "(-)".'); continue
                if lado=='debito': debito={'codigo':c['CODIGO REDUZIDO'],'descricao':c['DESCRICAO']}
                else: credito={'codigo':c['CODIGO REDUZIDO'],'descricao':c['DESCRICAO']}
        if not d['elegivel_contabilidade'] and not faltas: faltas.append('Fato fiscal não elegível para proposta automática.')
        if not (regra.get('fonte') or regra.get('origem')) and regra: faltas.append('Referência contábil sem origem documentada.')
        data,motivo_data=data_lancamento(pol,competencia,d)
        if motivo_data: faltas.append(motivo_data)
        identidade=(f"FISCAL:{evento}:APURACAO:{d.get('competencia')}:{d.get('titular_cnpj')}" if d['tipo']=='APURACAO_TRIBUTO'
                    else f"FISCAL:{evento or d['tipo']}:NOTA:{d.get('emitente_cnpj')}:{str(d.get('numero') or '').lstrip('0') or 'SEM-NUMERO'}")
        lancamentos.append({'id':'PF-'+d['id'],'documento':d['id'],'arquivo':d['arquivo'],'sha256':d['sha256'],
                            'status':'INCOMPLETO' if faltas else 'PROPOSTO_PARA_CONFERENCIA', 'evento':evento,
                            'competencia':d['competencia'],'data':data,
                            'data_origem':(f"política da empresa: {gov.POLITICAS_DATA[pol['politica']]} ({pol['governanca']['situacao']})"
                                           if data else None),
                            'identidade':identidade,'regra_governanca':governanca,
                            'valor':d['valor'],'debito':debito,'credito':credito,
                            'historico':f"{evento or d['tipo']} REF. {d.get('numero') or 'SEM NUMERO'} COMPETENCIA {d.get('competencia') or 'A CONFERIR'}",
                            'origem_regra':regra.get('fonte'), 'pendencias':list(dict.fromkeys(faltas)),
                            'aprovado':False,'escriturado':False})
    # Defesa em profundidade: mesma provisão ou mesma nota proposta mais de uma vez não segue para conferência.
    grupos_prop={}
    for l,d in zip(lancamentos,[d for d in fiscal['documentos'] if not d.get('duplicado_de') and d['tipo']!='GUIA']):
        if l['status']!='PROPOSTO_PARA_CONFERENCIA': continue
        chave=(l['evento'],l['competencia'],d.get('titular_cnpj')) if d['tipo']=='APURACAO_TRIBUTO' else (l['evento'],d.get('emitente_cnpj'),str(d.get('numero') or '').lstrip('0'))
        grupos_prop.setdefault(chave,[]).append(l)
    for grupo in grupos_prop.values():
        if len(grupo)>1:
            for l in grupo:
                l['status']='INCOMPLETO'; l['pendencias'].append('Mais de uma proposta para o mesmo fato fiscal (tributo/competência ou nota); nenhuma foi escolhida.')
    return {'contrato':'CONTABILIDADE_FISCAL_V1','agente':'CONTABILIDADE/FISCAL','empresa':empresa,'competencia':competencia,'sol':sol,
            'modo':'SIMULACAO','lancamentos':lancamentos,'documentos_sem_proposta':sem_proposta,'origem_fiscal_sha256':hashlib.sha256(json.dumps(fiscal,sort_keys=True).encode()).hexdigest(),
            'politica_data':{k:pol.get(k) for k in ('aplicavel','politica','motivo','governanca')},
            'resumo':{'propostos':sum(l['status']=='PROPOSTO_PARA_CONFERENCIA' for l in lancamentos),
                      'sem_data':sum(1 for l in lancamentos if not l['data']),
                      'incompletos':sum(l['status']=='INCOMPLETO' for l in lancamentos),'pendencias':sum(len(l['pendencias']) for l in lancamentos)},
            'limites':['Propostas de competência, sem lançamentos de banco. Pagamentos são tratados por Bancos, evitando nova despesa.',
                       'Não significa aprovação, escrituração, apuração tributária completa ou Conciliação independente.']+limites_extra}


def main():
    p=argparse.ArgumentParser()
    for n in ('empresa','competencia','sol','fiscal','saida'): p.add_argument('--'+n,required=True)
    a=p.parse_args()
    if not re.fullmatch('[A-Z0-9][A-Z0-9-]*',a.empresa): return 2
    r=gerar(a.empresa,a.competencia,a.sol,json.loads(Path(a.fiscal).read_text(encoding='utf-8')))
    r['origem_fiscal_sha256']=hashlib.sha256(Path(a.fiscal).read_bytes()).hexdigest()
    s=Path(a.saida); s.mkdir(parents=True,exist_ok=True)
    (s/'resultado.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0


if __name__=='__main__':sys.exit(main())
