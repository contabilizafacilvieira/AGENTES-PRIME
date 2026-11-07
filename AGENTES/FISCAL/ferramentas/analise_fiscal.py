"""Fiscal documental local. Sem consulta externa, apuração por alíquota presumida ou escrituração."""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ/'AGENTES/FINANCEIRO/ferramentas'))
from conferencia_financeira import cadastro, receber_pacote_local


def norm(t):
    return unicodedata.normalize('NFKD', str(t or '')).encode('ascii','ignore').decode().upper()


def digitos(t): return re.sub(r'\D','',str(t or ''))


def valor(t, xml=False):
    try:
        t=str(t or '').strip().replace('R$','').strip()
        if not xml: t=t.replace('.','').replace(',','.')
        d=Decimal(t)
        if not d.is_finite() or d<0 or d != d.quantize(Decimal('.01')): return None
        return str(d.quantize(Decimal('.01')))
    except (InvalidOperation, ValueError): return None


def periodo(t):
    t=str(t or '').strip()
    for fmt in ('%Y-%m','%m/%Y','%d/%m/%Y','%Y-%m-%d'):
        try: return dt.datetime.strptime(t,fmt).strftime('%Y-%m')
        except ValueError: pass
    return None


def linhas_rotuladas(t, rotulos, padrao):
    """Somente rótulo explícito, mesma linha/próxima linha; candidatos divergentes não são escolhidos."""
    linhas=norm(t).splitlines(); achados=[]
    for n,l in enumerate(linhas):
        for rotulo in rotulos:
            m=re.match(r'^\s*'+rotulo+r'\s*(?:[:=]|\s)\s*(.*)$',l)
            if m:
                candidato=m.group(1).strip() or (linhas[n+1].strip() if n+1<len(linhas) else '')
                a=re.fullmatch(padrao,candidato)
                if a: achados.append(a.group(0))
    unicos=set(achados)
    return next(iter(unicos)) if len(unicos)==1 else None


def campo(t, rotulos, tipo):
    padroes={'dinheiro':r'(?:R\$\s*)?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}',
             'cnpj':r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}',
             'periodo':r'(?:20\d{2}-\d{2}(?:-\d{2})?|\d{2}/(?:\d{2}/)?20\d{2})',
             'numero':r'[A-Z0-9][A-Z0-9./-]{0,59}'}
    v=linhas_rotuladas(t,rotulos,padroes[tipo])
    return valor(v) if v and tipo=='dinheiro' else digitos(v) if v and tipo=='cnpj' else periodo(v) if v and tipo=='periodo' else v


def texto(a):
    c=a.get('conteudo') or {}
    return c.get('texto') or '\n'.join(p.get('texto','') for p in c.get('paginas',[]))


def nfse_municipal(t):
    """Cabeçalhos/blocos da NFS-e paulistana observados nas fontes; não usa RPS como número da nota."""
    n=norm(t); saida={}
    if not ('PRESTADOR DE SERVICOS' in n and 'TOMADOR DE SERVICOS' in n): return saida
    prestador=n.split('PRESTADOR DE SERVICOS',1)[1].split('TOMADOR DE SERVICOS',1)[0]
    tomador=n.split('TOMADOR DE SERVICOS',1)[1]
    tomador=re.split(r'INTERMEDIARIO DE SERVICOS|DISCRIMINACAO DE SERVICOS',tomador,maxsplit=1)[0]
    for chave,bloco in (('emitente_cnpj',prestador),('destinatario_cnpj',tomador)):
        vs={digitos(v) for v in re.findall(r'(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)',bloco)}
        if len(vs)==1: saida[chave]=vs.pop()
    cab=n.split('PRESTADOR DE SERVICOS',1)[0]
    numeros=set(re.findall(r'(?m)^\s*(\d{1,15})\s*\n\s*\d{2}/\d{2}/20\d{2}\s+\d{2}:\d{2}:\d{2}\s*$',cab))
    if len(numeros)==1:saida['numero']=numeros.pop()
    return saida


DINHEIRO=r'(?:R\$\s*)?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}'
# Rótulo de cada tributo retido. Combinações (PIS/COFINS/CSLL, CSRF, PCC) não são distribuídas entre tributos.
TRIBUTOS_RETIDOS={'ISS':r'ISS(?:QN)?','IRRF':r'IRRF|IR|IMPOSTO DE RENDA','PIS':r'PIS(?:/PASEP)?','COFINS':r'COFINS',
                  'CSLL':r'CSLL','INSS':r'INSS'}
_ALT='|'.join(f'(?P<{k}>{v})' for k,v in TRIBUTOS_RETIDOS.items())
_ROTULO_RETENCAO=re.compile(
    r'^(?:VALOR (?:DO |DA |DE )?)?(?:'
    r'(?:RETENCAO (?:DE |DO |DA )?(?:'+_ALT.replace('?P<','?P<r_')+r'))'
    r'|(?:(?:'+_ALT+r') RETID[OA])'
    r'|(?P<irrf_puro>IRRF)'
    r')(?: NA FONTE)?(?: \(R\$\))?\s*(?:[:=]\s*)?(?P<resto>.*)$')
_INDICIO_RETENCAO=re.compile(r'RETID|RETENC|NA FONTE|\bIRRF\b|\bCSRF\b|\b(?:INSS|IRRF|CSLL|COFINS|PIS(?:/PASEP)?)\s*\(R\$\)')
_COLUNA_TABELA=re.compile(r'(INSS|IRRF|CSLL|COFINS|PIS(?:/PASEP)?)\s*\(R\$\)')


def retencoes_nfse(t):
    """Retenções somente por rótulo unívoco; todo indício não reconhecido vira ressalva (nunca vale zero).

    Retorna (valores, ausencias_declaradas, ressalvas). Valores divergentes para o mesmo tributo não são escolhidos.
    Tabela federal (cabeçalho "INSS (R$) IRRF (R$) ..." e linha seguinte com um valor ou "-" por coluna) é lida por coluna;
    "-" registra ausência de valor declarada na tabela, sem gravar zero.
    """
    linhas=[re.sub(r'\s+',' ',l).strip() for l in norm(t).splitlines()]
    usadas=set(); candidatos={}; sim=set(); nao=set(); ressalvas=[]
    for i,l in enumerate(linhas):
        colunas=_COLUNA_TABELA.findall(l)
        if len(colunas)>=2:
            resto=_COLUNA_TABELA.sub('',l).strip()
            prox=linhas[i+1] if i+1<len(linhas) else ''
            vals=re.findall(r'-|'+DINHEIRO,prox)
            if not resto and vals and re.fullmatch(r'(?:\s*(?:-|'+DINHEIRO+r'))+\s*',prox) and len(vals)==len(colunas):
                usadas.update((i,i+1))
                for col,v in zip(colunas,vals):
                    trib='PIS' if col.startswith('PIS') else col
                    if v=='-': nao.add(trib)
                    else: candidatos.setdefault(trib,set()).add(valor(v))
            else: ressalvas.append('Tabela de retenções sem valores alinhados por coluna: "'+l[:80]+'".')
            usadas.add(i)
            continue
        m=_ROTULO_RETENCAO.match(l)
        if not m: continue
        trib='IRRF' if m.group('irrf_puro') else next((k for k in TRIBUTOS_RETIDOS if m.group(k) or m.group('r_'+k)),None)
        resto=m.group('resto').strip(); j=None
        if not resto and i+1<len(linhas) and re.fullmatch(DINHEIRO+r'|SIM|NAO',linhas[i+1]): resto=linhas[i+1]; j=i+1
        if re.fullmatch(DINHEIRO,resto) and valor(resto) is not None: candidatos.setdefault(trib,set()).add(valor(resto))
        elif resto=='NAO': nao.add(trib)
        elif resto=='SIM': sim.add(trib)
        else: continue  # rótulo sem valor unívoco: permanece como indício não reconhecido
        usadas.add(i)
        if j is not None: usadas.add(j)
    valores={}
    for trib,vs in candidatos.items():
        if len(vs)!=1: ressalvas.append(f'Retenção de {trib} com valores divergentes; nenhum valor escolhido.')
        elif trib in nao and next(iter(vs))!='0.00':
            ressalvas.append(f'Retenção de {trib} declarada ausente e com valor positivo; conferir o documento.')
        else: valores[trib]=next(iter(vs))
    for trib in sim-set(candidatos): ressalvas.append(f'Retenção de {trib} declarada sem valor identificado.')
    for i,l in enumerate(linhas):
        if i not in usadas and _INDICIO_RETENCAO.search(l):
            ressalvas.append('Indício de retenção sem tributo/valor unívoco reconhecido: "'+l[:80]+'".')
    return valores, sorted(nao-set(valores)), ressalvas


def tipo_documento(n):
    """NFS-e x guia por estrutura, não por menção. Ambos estruturados ou nenhum: ambíguo (pendência)."""
    guia=('DARF' in n or 'DOCUMENTO DE ARRECADACAO' in n)
    nota=any(x in n for x in ('NOTA FISCAL','NFS-E','NFSE'))
    if guia and not nota: return 'GUIA'
    if nota and not guia: return 'NFSE'
    if not (guia and nota): return None
    est_nota=bool(re.search(r'PRESTADOR|TOMADOR|NUMERO DA NOTA|NUMERO DA NFS-E|VALOR (?:TOTAL )?DOS? SERVICOS?',n))
    est_guia=bool(re.search(r'CODIGO D[AE] RECEITA|PERIODO DE APURACAO|NUMERO DO DOCUMENTO|DOCUMENTO DE ARRECADACAO',n))
    if est_nota and not est_guia: return 'NFSE'
    if est_guia and not est_nota: return 'GUIA'
    return 'AMBIGUO'


def substituicoes(n):
    """Referências de substituição declaradas. Retorna (substitui, substituida_por, marca_sem_numero)."""
    n=re.sub(r'SUBSTITU\w* TRIBUTARI\w*','',n)  # substituição tributária não é substituição de nota
    num=r'(?:A |O )?(?:NOTA(?: FISCAL)?(?: DE SERVICOS?)?(?: ELETRONICA)?|NFS-?E)(?: (?:N[O.º]?|NUMERO))?[ .:]*(\d{1,15})\b'
    substitui=set(re.findall(r'\bSUBSTITU(?:I|INDO|TA D[AO])\s+'+num,n))
    por=set(re.findall(r'\bSUBSTITUIDA\s+(?:PELA|POR)\s+'+num,n))
    marca=bool(re.search(r'\bNOTA SUBSTITUTA\b|\bSUBSTITUTA\b|\bSUBSTITUI\b|\bSUBSTITUICAO\b',n)) and not substitui
    return substitui, por, marca


def _num(x): return str(x or '').lstrip('0')


def verificar_substituicoes(documentos,pend):
    """Substituída nunca é aproveitada. Substituta só prevalece quando a relação é unívoca e a substituída está no lote."""
    notas=[d for d in documentos if d['tipo']=='NFSE' and not d.get('duplicado_de')]
    por_numero={}; substitutas={}
    for d in notas:
        por_numero.setdefault((d.get('emitente_cnpj'),_num(d.get('numero'))),[]).append(d)
        for numero in d.get('substitui') or []: substitutas.setdefault((d.get('emitente_cnpj'),_num(numero)),[]).append(d)
    def achar(d,numero): return por_numero.get((d.get('emitente_cnpj'),_num(numero)),[])
    def bloquear(docs,motivo):
        for o in docs: o['elegivel_contabilidade']=False; pend(o,motivo)
    for d in notas:
        if d.get('substituicao_sem_referencia'):
            bloquear([o for o in notas if o.get('emitente_cnpj')==d.get('emitente_cnpj')],
                     'Há nota substituta sem referência identificável no lote; não é possível determinar qual nota prevalece.')
        if d.get('substituida_por'): bloquear([d],'Nota declarada substituída; não aproveitar como receita. A substituta deve ser conferida.')
        elif (d.get('emitente_cnpj'),_num(d.get('numero'))) in substitutas:
            bloquear([d],'Outra nota do lote declara substituir esta; não aproveitar como receita.')
    for d in notas:
        subs=d.get('substitui') or []
        if subs:
            originais=achar(d,subs[0]); motivo=None
            if len(subs)>1: motivo='Nota substitui mais de uma nota; definir qual receita prevalece.'
            elif len(substitutas.get((d.get('emitente_cnpj'),_num(subs[0])),[]))>1:
                motivo='Mais de uma nota declara substituir a mesma nota; nenhuma versão foi escolhida.'
            elif len(originais)!=1:
                motivo='Nota substituída ausente do lote ou não única; conferir se já foi contabilizada para não duplicar a receita.'
            else:
                ref=[_num(x) for x in originais[0].get('substituida_por') or []]
                if ref and ref!=[_num(d.get('numero'))]: motivo='Referências de substituição incoerentes entre as notas.'
                elif originais[0].get('competencia')!=d.get('competencia'):
                    motivo='Nota substituída de outra competência; conferir o tratamento contábil da original.'
            if motivo: bloquear([d]+originais,motivo)
        for numero in d.get('substituida_por') or []:
            alvo=achar(d,numero)
            if alvo and [_num(x) for x in alvo[0].get('substitui') or []]!=[_num(d.get('numero'))]:
                bloquear(alvo+[d],'Referências de substituição incoerentes entre as notas.')


def verificar_apuracoes_repetidas(documentos,pend):
    """Mesmo contribuinte/competência/tributo: só uma retificadora única com a original no lote prevalece."""
    grupos={}
    for d in documentos:
        if d['tipo']=='APURACAO_TRIBUTO' and not d.get('duplicado_de') and d.get('tributo') and d.get('competencia'):
            grupos.setdefault((d.get('titular_cnpj'),d['competencia'],d['tributo']),[]).append(d)
    for grupo in grupos.values():
        retif=[d for d in grupo if d.get('retificadora')]
        if len(grupo)==1:
            if retif:
                grupo[0]['elegivel_contabilidade']=False
                pend(grupo[0],'Apuração retificadora sem a original no lote; conferir se a provisão original já foi registrada para não duplicar.')
            continue
        prevalece=retif[0] if len(retif)==1 and len(grupo)-1==sum(not d.get('retificadora') for d in grupo) else None
        for d in grupo:
            if d is prevalece:
                d['prevalece_sobre']=[o['id'] for o in grupo if o is not d]; continue
            d['elegivel_contabilidade']=False
            pend(d,'Retificada por outra apuração do lote; não provisionar.' if prevalece else
                   'Mais de uma apuração do mesmo tributo/competência; nenhuma versão foi escolhida para não duplicar a provisão.')


def analisar(empresa, competencia, sol, arquivos, cnpjs):
    cnpjs={digitos(c) for c in cnpjs}; documentos=[]; pendencias=[]
    def pend(d,t):
        if t not in d['pendencias']: d['pendencias'].append(t)
    for a in arquivos:
        c=a.get('conteudo') or {}; t=texto(a); n=norm(t)
        d={'id':'FIS-'+a['sha256'][:16].upper(),'arquivo':a['arquivo'],'sha256':a['sha256'],
           'tipo':'NAO_RECONHECIDO','pendencias':[],'emitente_cnpj':None,'destinatario_cnpj':None,
           'competencia':None,'valor':None,'numero':None,'retencoes':{},'tributos_destacados':{},
           'origem':{'leitura':a.get('leitura'),'paginas':[{'pagina':p.get('pagina'), 'origem':p.get('origem'),
                       'confianca':p.get('confianca')} for p in c.get('paginas',[])],
                     'validacao_externa':False},'papel_empresa':'NAO_IDENTIFICADO','elegivel_contabilidade':False}
        if not str(a.get('leitura','')).startswith('EXTRAIDO_') or c.get('requer_conferencia_ocr') or c.get('leitura_incompleta'):
            pend(d,'Leitura protegida, parcial ou OCR duvidoso; conferir o original. Nenhum valor aproveitado.')
        elif c.get('tipo')=='CANCELAMENTO':
            d.update(tipo='EVENTO_CANCELAMENTO',chave=c.get('chave_nfe'),situacao_declarada=c.get('situacao_declarada'))
            pend(d,'Evento de cancelamento recebido; conferir situação e documentos relacionados. Não estornar automaticamente.')
        elif a.get('leitura')=='EXTRAIDO_NFE':
            ide=c.get('ide') or {}; emit=c.get('emitente') or {}; dest=c.get('destinatario') or {}; totais=c.get('totais') or {}
            d.update(tipo='NFE',chave=c.get('chave'),numero=ide.get('nNF'),serie=ide.get('serie'),modelo=ide.get('mod'),
                     emissao=ide.get('dhEmi'),emitente_cnpj=digitos(emit.get('CNPJ')) or None,
                     destinatario_cnpj=digitos(dest.get('CNPJ')) or None,valor=valor(totais.get('vNF'),True),
                     tpNF=ide.get('tpNF'),ambiente=ide.get('tpAmb'),competencia_documental=periodo((ide.get('dhEmi') or '')[:10]))
            d['tributos_destacados']={k:valor(totais[k],True) for k in ('vICMS','vIPI','vPIS','vCOFINS') if totais.get(k) is not None}
            if not c.get('chave_valida'): pend(d,'Chave da NF-e inválida ou ausente.')
            if ide.get('tpAmb')!='1': pend(d,'NF-e fora do ambiente de produção ou ambiente ausente; não aproveitada como nota regular.')
            prot=c.get('protocolo') or {}
            if prot.get('cStat') not in ('100','150'): pend(d,'Protocolo de autorização declarada ausente ou não autorizado.')
            for m in a.get('marcacoes',[]): pend(d,'Ressalva do extrator: '+m)
            for m in c.get('divergencias',[]): pend(d,m)
            # Emissão e tpNF não decidem por si sós competência da receita, natureza ou crédito fiscal.
            pend(d,'NF-e entregue para classificação contábil; não presumir competência de receita, natureza da compra ou direito a crédito tributário.')
        elif tipo_documento(n)=='AMBIGUO':
            pend(d,'Classificação ambígua: o arquivo tem estrutura de nota e de guia/DARF; separar ou conferir antes de aproveitar.')
        elif tipo_documento(n)=='GUIA':
            d.update(tipo='GUIA',titular_cnpj=campo(t,[r'CNPJ',r'CPF/CNPJ',r'CNPJ DO CONTRIBUINTE'],'cnpj'),
                     numero=campo(t,[r'NUMERO DO DOCUMENTO',r'N[ºO.]? DO DOCUMENTO'],'numero'),
                     competencia=campo(t,[r'PERIODO DE APURACAO',r'COMPETENCIA'],'periodo'),
                     valor=campo(t,[r'VALOR TOTAL',r'TOTAL A PAGAR',r'VALOR DO DOCUMENTO'],'dinheiro'),
                     codigo_receita=campo(t,[r'CODIGO DA RECEITA',r'CODIGO DE RECEITA'],'numero'))
            # Natureza da guia é informação (não pendência): cobrança de obrigação; o pagamento é fato do Financeiro (extrato).
            d.setdefault('observacoes',[]).append('Guia é cobrança: não comprova pagamento nem gera nova provisão; a liquidação é conferida '
                                                  'pelo Financeiro e proposta por Contabilidade/Bancos contra a obrigação já reconhecida.')
            if not d['codigo_receita']: pend(d,'Código/composição da receita não identificado de forma unívoca.')
        elif tipo_documento(n)=='NFSE':
            d.update(tipo='NFSE',emitente_cnpj=campo(t,[r'CNPJ DO PRESTADOR',r'PRESTADOR CNPJ',r'CNPJ PRESTADOR'],'cnpj'),
                     destinatario_cnpj=campo(t,[r'CNPJ DO TOMADOR',r'TOMADOR CNPJ',r'CNPJ TOMADOR'],'cnpj'),
                     numero=campo(t,[r'NUMERO DA NOTA',r'NUMERO DA NFS-E',r'NOTA FISCAL NUMERO'],'numero'),
                     competencia=campo(t,[r'COMPETENCIA',r'COMPETENCIA DO SERVICO'],'periodo'),
                     valor=campo(t,[r'VALOR DOS SERVICOS',r'VALOR TOTAL DOS SERVICOS',r'VALOR TOTAL DO SERVICO'],'dinheiro'))
            municipal=nfse_municipal(t)
            for k,v in municipal.items():
                if d.get(k) and d[k]!=v: pend(d,'Conflito entre campos rotulados e bloco municipal: '+k)
                elif not d.get(k): d[k]=v
            if n.count('PRESTADOR DE SERVICOS')>1: pend(d,'Mais de um bloco de prestador no arquivo; separar/conferir as notas antes de propor totais.')
            # Retenção não reconhecida nunca vale zero: indício sem tributo/valor unívoco bloqueia a proposta.
            d['retencoes'],d['retencoes_ausencia_declarada'],ressalvas=retencoes_nfse(t)
            for r in ressalvas: pend(d,r)
            if not d['numero']: pend(d,'Número da nota não identificado.')
            d['pais_tomador']=linhas_rotuladas(t,[r'PAIS DO TOMADOR'],r'[A-Z][A-Z ]{1,59}')
            d['tomador_id_exterior']=linhas_rotuladas(t,[r'NIF DO TOMADOR',r'TAX ID DO TOMADOR',r'TAX ID',
                r'IDENTIFICACAO FISCAL ESTRANGEIRA DO TOMADOR',r'DOCUMENTO ESTRANGEIRO DO TOMADOR'],r'[A-Z0-9][A-Z0-9 ./-]{1,39}')
            subs,por,marca=substituicoes(n); d['substitui']=sorted(subs); d['substituida_por']=sorted(por)
            d['substituicao_sem_referencia']=marca
            if marca: pend(d,'Nota declara substituição sem número da nota substituída identificável; conferir qual documento prevalece.')
            if any(x in n for x in ('HOMOLOGACAO','SEM VALOR FISCAL','PROFORMA','PRO FORMA','VALOR ESTIMADO')):
                pend(d,'Documento declara homologação, estimativa ou ausência de valor fiscal; não apropriar como receita definitiva.')
            if re.search(r'\b(USD|DOLAR|DOLARES|EUR|EURO)\b',n): pend(d,'Moeda estrangeira no documento; exigir valor em reais e base de conversão conferidos, sem estimar câmbio.')
            if re.search(r'\b(CANCELADA|SUBSTITUIDA)\b',n): pend(d,'Nota declara cancelamento/substituição; conferir documento vigente.')
            if any(Decimal(v)>0 for v in d['retencoes'].values()): pend(d,'Retenções destacadas: composição e contas precisam de conferência antes da proposta contábil.')
        elif 'DEMONSTRATIVO DE APURACAO' in n:
            d.update(tipo='APURACAO_TRIBUTO',titular_cnpj=campo(t,[r'CNPJ',r'CNPJ DO CONTRIBUINTE'],'cnpj'),
                     competencia=campo(t,[r'PERIODO DE APURACAO',r'COMPETENCIA'],'periodo'),
                     tributo=campo(t,[r'TRIBUTO'],'numero'),valor=campo(t,[r'VALOR APURADO'],'dinheiro'),
                     retificadora=bool(re.search(r'\bRETIFICADORA\b|\bRETIFICACAO\b',n)))
            if d['tributo'] not in ('ISS','IRPJ','CSLL','PIS','COFINS'): pend(d,'Tributo sem método de provisão definido.')
        else:
            pend(d,'Layout fiscal não reconhecido; análise manual necessária. Não inferir valores pelo nome do arquivo.')
        if d.get('emitente_cnpj') in cnpjs: d['papel_empresa']='PRESTADOR_EMITENTE'
        elif d.get('destinatario_cnpj') in cnpjs: d['papel_empresa']='TOMADOR_DESTINATARIO'
        elif d.get('titular_cnpj') in cnpjs: d['papel_empresa']='CONTRIBUINTE'
        else: pend(d,'Titularidade fiscal da empresa não comprovada; documento isolado da proposta contábil.')
        if d.get('emitente_cnpj') in cnpjs and d.get('destinatario_cnpj') in cnpjs:
            pend(d,'Emitente e destinatário pertencem ao cadastro; operação interna exige classificação específica.')
        # filial não cadastrada: mesmo radical (8 dígitos) de um CNPJ da empresa não é cliente/fornecedor externo presumido
        radicais={c[:8] for c in cnpjs if c}
        for papel in ('emitente_cnpj','destinatario_cnpj','titular_cnpj'):
            c=d.get(papel)
            if c and c not in cnpjs and c[:8] in radicais:
                pend(d,f'CNPJ {c} tem o mesmo radical da empresa e não está no cadastro (possível filial): operação possivelmente '
                       'interna; confirme o cadastro da filial antes de qualquer proposta.')
        if d['valor'] is None or Decimal(d['valor'])<=0: pend(d,'Valor fiscal positivo não identificado de forma unívoca.')
        if not d['competencia']: pend(d,'Competência fiscal explícita ausente; emissão/pagamento não substituem competência.')
        elif d['tipo']=='GUIA' and d['competencia']<competencia:
            # guia de competência anterior paga neste mês: liquidação de obrigação já reconhecida (saldo de abertura), não pendência
            d.setdefault('observacoes',[]).append(f"Guia de competência anterior ({d['competencia']}): liquidação de obrigação já reconhecida; "
                                                  'conferir com o saldo de abertura. Sem provisão neste mês.')
        elif d['competencia']!=competencia: pend(d,'Competência distinta da SOL; documento mantido para suporte, sem apropriação automática neste mês.')
        if d['tipo']=='NFSE' and d['papel_empresa']!='PRESTADOR_EMITENTE':
            pend(d,'Serviço tomado: definir natureza e se a obrigação já foi contabilizada; não duplicar a despesa no pagamento.')
        d['elegivel_contabilidade']=not d['pendencias'] and d['tipo'] in ('NFSE','APURACAO_TRIBUTO')
        documentos.append(d)
    identidades={}
    for d in documentos:
        chave=d.get('chave') or ((d['tipo'],d.get('emitente_cnpj'),d.get('serie'),d['numero']) if d['numero'] and d.get('emitente_cnpj') else ('SHA',d['sha256']))
        identidades.setdefault(str(chave),[]).append(d)
    for grupo in identidades.values():
        if len(grupo)>1:
            iguais=len({d['sha256'] for d in grupo})==1
            for i,d in enumerate(grupo):
                if iguais and i==0: continue
                d['duplicado_de']=grupo[0]['id']; d['elegivel_contabilidade']=False
                pend(d,'Cópia duplicada; não somar novamente.' if iguais else 'Documentos diferentes com a mesma identidade fiscal; nenhuma versão foi escolhida.')
    verificar_substituicoes(documentos,pend)
    verificar_apuracoes_repetidas(documentos,pend)
    canceladas={d.get('chave') for d in documentos if d['tipo']=='EVENTO_CANCELAMENTO'}-{None}
    for d in documentos:
        if d.get('chave') in canceladas and d['tipo']!='EVENTO_CANCELAMENTO':
            d['elegivel_contabilidade']=False; pend(d,'Evento de cancelamento relacionado recebido; não aproveitar antes de conferir.')
        pendencias.extend({'documento':d['id'],'arquivo':d['arquivo'],'descricao':p} for p in d['pendencias'])
    return {'contrato':'FISCAL_LOCAL_V1','agente':'FISCAL','empresa':empresa,'competencia':competencia,'sol':sol,'modo':'SIMULACAO',
            'documentos':documentos,'pendencias':pendencias,'resumo':{'documentos':len(documentos),
                'aptos_proposta':sum(d['elegivel_contabilidade'] for d in documentos),'pendencias':len(pendencias)},
            'limitacoes':['Conferência documental local; sem consulta municipal/SEFAZ, assinatura ou autenticidade verificadas.',
                          'Sem apuração por alíquota presumida, compensações, créditos fiscais ou escrituração.',
                          'Guias não provam liquidação; a conferência do pagamento pertence ao Financeiro.']}


def main():
    p=argparse.ArgumentParser()
    for a in ('empresa','competencia','sol','pasta','documentos-local','extracao-local','saida'): p.add_argument('--'+a,required=True)
    a=p.parse_args()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]*',a.empresa) or not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])',a.competencia): return 2
    arquivos,_=receber_pacote_local(a.empresa,a.competencia,a.sol,a.pasta,a.documentos_local,a.extracao_local,area='FISCAL',exigir_hash=True)
    r=analisar(a.empresa,a.competencia,a.sol,arquivos,cadastro(a.empresa)['cnpjs'])
    saida=Path(a.saida); saida.mkdir(parents=True,exist_ok=True)
    (saida/'resultado.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0


if __name__=='__main__': sys.exit(main())
