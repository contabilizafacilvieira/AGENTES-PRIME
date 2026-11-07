"""Fiscal pela API e navegador: empresa fictícia, registro/runtime isolados, sem documentos reais."""
import base64
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

RAIZ=Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding='utf-8')
EMP='CLIENTE-CODEX-FISCAL-TMP'
tmp=tempfile.TemporaryDirectory(prefix='prime-e2e-fiscal-')
# ambiente ISOLADO: CLIENTES, ordem ativa, runtime, registro e LIBERADOS temporários (nada operacional é tocado)
CLIENTES=Path(tmp.name)/'CLIENTES';CLIENTES.mkdir();BASE=CLIENTES/EMP
ORDEM=Path(tmp.name)/'ordem-ativa.json'
os.environ['AGENTES_PRIME_ORDEM_ATIVA']=str(ORDEM)
os.environ['AGENTES_PRIME_CLIENTES']=str(CLIENTES)
os.environ['AGENTES_PRIME_LIBERADOS']=str(Path(tmp.name)/'LIBERADOS')
os.environ['LOCALAPPDATA']=str(Path(tmp.name)/'localappdata')
os.environ['AGENTES_PRIME_RUNTIME']=str(Path(tmp.name)/'runtime')
os.environ['AGENTES_PRIME_REGISTRO_SOL']=str(Path(tmp.name)/'registro.json')
os.environ['AGENTES_PRIME_CLAUDE']=str(Path(tmp.name)/'inexistente.exe')
sys.path.insert(0,str(RAIZ/'API-LOCAL'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from testar_fiscal import NOTA,CNPJ
import servidor
srv=servidor.iniciar(0);threading.Thread(target=srv.serve_forever,daemon=True).start()


def req(m,p,d=None,headers=None):
    c=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=90)
    h={'X-Prime-Sessao':srv.token,'Content-Type':'application/json'};h.update(headers or {})
    c.request(m,'/api'+p,d if isinstance(d,bytes) else json.dumps(d).encode() if d is not None else None,h)
    r=c.getresponse();raw=r.read();c.close();j=json.loads(raw)
    assert r.status<400,(r.status,j)
    return j


def iniciar(numero,misto=False,mes='10/2026'):
    l=req('POST','/lotes',{'empresa':EMP,'competencia':'2026-10','fluxo':'DOCUMENTOS','instrucao':'Distribua por área e prepare propostas fictícias.'})['lote']
    fontes=[('nota.txt',NOTA.replace('123\n',str(numero)+'\n').replace('10/2026',mes).encode())]
    if misto:
        fontes.append(('extrato.ofx',b'<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><BANKID>033<BRANCHID>1234<ACCTID>11111-1</BANKACCTFROM><BANKTRANLIST><DTSTART>20261001<DTEND>20261031<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261005<TRNAMT>-100.00<FITID>FISCAL-TESTE<MEMO>PAGAMENTO FICTICIO</STMTTRN></BANKTRANLIST><LEDGERBAL><BALAMT>900.00<DTASOF>20261031</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>'))
    for nome,d in fontes:
        req('PUT',f'/lotes/{l}/arquivos',d,{'X-Nome-Arquivo':nome,'X-Sha256':hashlib.sha256(d).hexdigest(),'Content-Type':'application/octet-stream'})
    sol=req('POST',f'/lotes/{l}/iniciar',{'conferencia_humana':True})['sol']
    for _ in range(180):
        d=req('GET',f'/solicitacoes/{sol}')
        if d['estado']=='AGUARDANDO_SUPERVISOR' and not servidor.EM_EXECUCAO['sol']: return sol,d
        time.sleep(.25)
    raise AssertionError('Fluxo Fiscal não terminou.')


def navegador(sol):
    sys.path.insert(0,str(RAIZ/'TESTES/API'))
    from e2e_navegador import CDP,CHROME
    perfil=tempfile.TemporaryDirectory(prefix='chrome-fiscal-'); cdp=None
    url=f'http://127.0.0.1:{srv.server_port}/'
    chrome=subprocess.Popen([str(CHROME),'--headless=new','--remote-debugging-port=9357',f'--user-data-dir={perfil.name}',
                             '--window-size=1440,1000','--no-first-run','--disable-extensions',url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(70):
            try:
                ts=json.load(urllib.request.urlopen('http://127.0.0.1:9357/json/list',timeout=2))
                t=next(x for x in ts if x.get('type')=='page' and x['url'].startswith(url));cdp=CDP(t['webSocketDebuggerUrl']);break
            except Exception:time.sleep(.15)
        assert cdp
        def esperar(js):
            for _ in range(90):
                if cdp.js('!!('+js+')'):return
                time.sleep(.15)
            raise AssertionError('Tela não atingiu estado: '+js)
        esperar('window.EV && document.querySelector("[data-pagina=solicitacoes]")')
        cdp.js('document.querySelector("[data-pagina=solicitacoes]").click()')
        esperar('document.querySelector(".gestao-filtros input[type=search]")')
        cdp.js(f'(()=>{{const i=document.querySelector(".gestao-filtros input[type=search]");i.value={json.dumps(sol)};i.dispatchEvent(new Event("input"));}})()')
        esperar('document.querySelector(".gestao-lista .gestao-item button")')
        cdp.js('document.querySelector(".gestao-lista .gestao-item button").click()')
        esperar('document.querySelector("[data-area-fiscal]")')
        assert cdp.js('document.querySelector("[data-area-fiscal]").textContent.includes("1.234,56")')
        assert cdp.js('document.querySelector("[data-area-fiscal]").textContent.includes("Proposto para conferência")')
        assert cdp.js('Array.from(document.querySelectorAll(".ac-passos li")).some(x=>x.textContent.includes("Fiscal"))')
        assert cdp.js('!!document.querySelector("canvas") && !document.querySelector("canvas").hidden')
        assert cdp.js('document.querySelector(".op-sol").scrollWidth <= document.querySelector(".op-sol").clientWidth+1')
        fotos=Path(os.environ.get('CAPTURAS_FISCAL') or Path(tmp.name)/'capturas-fiscal');fotos.mkdir(parents=True,exist_ok=True)
        cdp.foto(fotos/'fiscal-resultado.png')
        print('PASS: Fiscal na interface; valor, proposta, fluxo e escritório visível.',flush=True)
    finally:
        if cdp: cdp.s.close()
        chrome.terminate();chrome.wait(timeout=10)
        try: perfil.cleanup()
        except PermissionError: pass


try:
    req('POST','/empresas',{'id':EMP,'nome':'CLIENTE FICTICIO FISCAL','cnpj':CNPJ,'regime':'TESTE'})
    csv='codigo;classificacao;descricao;grupo;tipo\n5;1.1;BANCO;ATIVO;A\n11;1.2;CLIENTES;ATIVO;A\n60;3.1;RECEITA;RECEITA;A\n'
    p=req('POST',f'/empresas/{EMP}/previa',{'nome':'p.csv','conteudo':base64.b64encode(csv.encode()).decode()})
    req('POST',f'/empresas/{EMP}/plano',{'token':p['token'],'salvar':True,'confirmado':True})
    req('POST',f'/empresas/{EMP}/bancos',{'contas':[{'banco':'033','agencia':'1234','conta':'11111-1','titular':CNPJ,'contabil':'5'}]})
    req('POST',f'/empresas/{EMP}/piloto',{'frase':'CONFIRMO PILOTO '+EMP})
    cad=req('GET',f'/empresas/{EMP}')
    # contrato vigente: referência e política de DATA do lançamento com situação PROPOSTA, confirmadas pelo Supervisor com a frase
    # exata (mesmo caminho da tela Empresas). Sem política de data a proposta ficaria incompleta (regra de negócio mantida).
    proposta=lambda **d: dict(d,situacao='PROPOSTA',versao=1,origem='Método fictício para teste',competencia_desde='2026-10')
    regras={'contrato':'REFERENCIAS_FISCAIS_V1','empresa':EMP,'cnpj':cad['cnpj'],'competencia_desde':'2026-10',
            'data_lancamento':proposta(politica='ULTIMO_DIA_COMPETENCIA'),
            'referencias':{'RECEITA_SERVICOS':proposta(debito='11',credito='60',fonte='Método fictício para teste')}}
    (BASE/'REGRAS-FISCAIS.json').write_text(json.dumps(regras),encoding='utf-8')
    for chave in ('RECEITA_SERVICOS','DATA_LANCAMENTO'):
        req('POST',f'/empresas/{EMP}/regras-area',{'area':'FISCAL','chave':chave,'frase':f'VALIDADO REGRA FISCAL {EMP} {chave}','confirmado':True})
    sol,d=iniciar(123)
    assert d['fiscal']['resumo']['aptos_proposta']==1,d
    assert d['contabilfiscal']['resumo']['propostos']==1,d
    assert d['etapas']['fiscal']['status']=='CONCLUIDA' and d['etapas']['contabilfiscal']['status']=='CONCLUIDA'
    assert d['tarefas_areas']['FISCAL']['estado']=='ENTREGUE'
    # Conciliação executa depois da Contabilidade (rodada 03/11/2026): entregue com resultado; escopo continua SIMULAÇÃO
    assert d['tarefas_areas']['CONCILIACAO']['estado'] in ('ENTREGUE','ENTREGUE_COM_PENDENCIAS') and d['conciliacao']['resultado'],d['tarefas_areas']['CONCILIACAO']
    assert d['escopo_resultado'] in ('SIMULACAO_CONCILIADA_NO_ALCANCE','SIMULACAO_CONCILIACAO_PARCIAL'),d['escopo_resultado']
    assert not servidor.tentativas(sol,'financeiro')
    navegador(sol)
    req('POST',f'/solicitacoes/{sol}/revisao-piloto',{'acao':'encerrar','justificativa':'Conferência fictícia parcial','confirmado':True})
    assert req('GET',f'/solicitacoes/{sol}')['estado']=='ENCERRADA'
    print('PASS: Fiscal sem extrato → Contabilidade/Fiscal → Supervisor; revisão parcial sem escrituração.',flush=True)
    sol,d=iniciar(124,misto=True)
    assert d['fluxo']=='FINANCEIRO_BANCOS' and d['contabilfiscal']['resumo']['propostos']==1,d
    fin=req('GET',f'/solicitacoes/{sol}/financeiro')
    assert fin['financeiro']['resumo']['movimentos']==1 and len(fin['bancos']['lancamentos'])==1
    assert d['etapas']['fiscal']['fim']<=d['etapas']['contabilfiscal']['inicio']
    print('PASS: lote misto passa por Fiscal, Financeiro e Contabilidade sem criar liquidação fiscal em dobro.',flush=True)
    sol,d=iniciar(125,mes='09/2026')
    assert d['contabilfiscal']['resumo']['propostos']==0 and d['contabilfiscal']['resumo']['incompletos']==1
    print('PASS: nota de competência anterior não vira receita de outubro.',flush=True)
finally:
    srv.shutdown();srv.server_close()
    if ORDEM.exists():
        d=json.loads(ORDEM.read_text(encoding='utf-8'))
        if d.get('empresa')==EMP:ORDEM.unlink()
    def permissao(fn,p,exc):
        os.chmod(p,0o700);fn(p)
    shutil.rmtree(tmp.name,onexc=permissao)
