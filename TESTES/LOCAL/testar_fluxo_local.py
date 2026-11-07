"""Ponta a ponta sem Claude; empresa fictícia temporária, registro/runtime isolados."""
import base64
import hashlib
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ=Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding='utf-8')
EMP='CLIENTE-CODEX-LOCAL-TMP'
EMP_PEND='CLIENTE-CODEX-PENDENTE-TMP'
tmp=tempfile.TemporaryDirectory(prefix='prime-e2e-local-')
# ambiente ISOLADO: CLIENTES, ordem ativa e LIBERADOS temporários (o CLIENTES/ operacional nunca é tocado)
CLIENTES=Path(tmp.name)/'CLIENTES';CLIENTES.mkdir()
BASE=CLIENTES/EMP
BASE_PEND=CLIENTES/EMP_PEND
ORDEM=Path(tmp.name)/'ordem-ativa.json'
os.environ['AGENTES_PRIME_ORDEM_ATIVA']=str(ORDEM)
os.environ['AGENTES_PRIME_CLIENTES']=str(CLIENTES)
os.environ['AGENTES_PRIME_LIBERADOS']=str(Path(tmp.name)/'LIBERADOS')
os.environ['LOCALAPPDATA']=str(Path(tmp.name)/'localappdata')
os.environ['AGENTES_PRIME_RUNTIME']=str(Path(tmp.name)/'runtime')
os.environ['AGENTES_PRIME_REGISTRO_SOL']=str(Path(tmp.name)/'registro.json')
# Um CLI ausente comprova que o fluxo local não tenta acioná-lo.
os.environ['AGENTES_PRIME_CLAUDE']=str(Path(tmp.name)/'claude-inexistente.exe')
sys.path.insert(0,str(RAIZ/'API-LOCAL'))
import servidor

srv=servidor.iniciar(0)
threading.Thread(target=srv.serve_forever,daemon=True).start()
def req(m,r,d=None,headers=None):
    conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=120)
    corpo=d if isinstance(d,bytes) else json.dumps(d).encode() if d is not None else None
    h={'X-Prime-Sessao':srv.token,'Content-Type':'application/json'};h.update(headers or {})
    conn.request(m,'/api'+r,corpo,h);resp=conn.getresponse();raw=resp.read();conn.close()
    result=json.loads(raw)
    if resp.status>=400:raise AssertionError((resp.status,result))
    return result

try:
    req('POST','/empresas',{'id':EMP,'nome':'CLIENTE TEMPORARIO DE TESTE LOCAL','cnpj':'11.222.333/0001-81','regime':'TESTE'})
    req('POST','/empresas',{'id':EMP_PEND,'nome':'CLIENTE FICTICIO COM CADASTRO PENDENTE','cnpj':'04.252.011/0001-10','regime':'TESTE'})
    perfil={'contrato':'METODO_EMPRESA_V1','empresa':EMP,'cnpj':'11.222.333/0001-81',
            'resumo':'Método fictício para testar isolamento.','confirmacoes_supervisor':['Confirmação fictícia'],
            'agentes_necessarios':[{'area':'Fiscal','situacao':'a implementar'}],'executa_regras':False}
    (BASE/'PERFIL-FECHAMENTO.json').write_text(json.dumps(perfil,ensure_ascii=False),encoding='utf-8')
    assert req('GET',f'/empresas/{EMP}')['metodo_fechamento']['empresa']==EMP
    assert req('GET',f'/empresas/{EMP_PEND}')['metodo_fechamento'] is None
    e=req('GET','/estado')
    assert EMP_PEND in [c['id'] for c in e['empresas_pendentes']]
    assert EMP_PEND not in [c['id'] for c in e['empresas']]
    try:
        req('POST','/lotes',{'empresa':EMP_PEND,'competencia':'2026-09','fluxo':'FINANCEIRO_BANCOS','instrucao':'Teste ficticio'})
        raise AssertionError('Cadastro pendente recebeu um lote.')
    except AssertionError as exc:
        assert exc.args[0][0]==403,exc
    assert not (BASE_PEND/'RECEBIDOS').exists()
    plano=b'codigo;classificacao;descricao;grupo;tipo\n5;1.1.1;BANCO;ATIVO;ANALITICA\n4103;4.1.1;DESPESA;DESPESA;ANALITICA\n11550;1.2;ADIANTAMENTO DIVERSO;ATIVO;A\n2200;2.1;ADIANTAMENTO CLIENTE;PASSIVO;A\n'
    previa=req('POST',f'/empresas/{EMP}/previa',{'nome':'plano.csv','conteudo':base64.b64encode(plano).decode()})
    req('POST',f'/empresas/{EMP}/plano',{'token':previa['token'],'mapa':dict(zip(('codigo','classificacao','descricao','grupo','tipo'),range(5))),'salvar':True,'confirmado':True})
    bancario=req('POST',f'/empresas/{EMP}/bancos',{'contas':[{'banco':'SANTANDER','agencia':'1234','conta':'11111-1','titular':'11.222.333/0001-81','contabil':'5'}]})
    assert bancario['contas'][0]['banco']=='033'
    try:
        req('POST',f'/empresas/{EMP}/parametros-bancos',{'habilitado':True,'confirmado':True})
        raise AssertionError('Regra automatica removida aceitou configuracao.')
    except AssertionError as exc:
        assert exc.args[0][0]==410,exc
    req('POST',f'/empresas/{EMP}/piloto',{'frase':'CONFIRMO PILOTO '+EMP})
    fluxo_origem = 'DOCUMENTOS' if os.environ.get('TRIAGEM_AUTOMATICA_LOCAL') == '1' else 'FINANCEIRO_BANCOS'
    lote=req('POST','/lotes',{'empresa':EMP,'competencia':'2026-09','fluxo':fluxo_origem,'instrucao':'Confira localmente os documentos deste mês.'})['lote']
    ofx=b'<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><BANKID>033<BRANCHID>1234<ACCTID>11111-1</BANKACCTFROM><BANKTRANLIST><DTSTART>20260901<DTEND>20260930<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260905<TRNAMT>-100.00<FITID>LOCAL-001<MEMO>PAGAMENTO SERVICO ALFA</STMTTRN></BANKTRANLIST><LEDGERBAL><BALAMT>900.00<DTASOF>20260930</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>'
    pdf = os.environ.get('EXTRATO_PDF_LOCAL') == '1'
    if pdf:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from testar_extrato_santander import pdf_ficticio
        ofx = pdf_ficticio()
    req('PUT',f'/lotes/{lote}/arquivos',ofx,{'X-Nome-Arquivo':'extrato.pdf' if pdf else 'extrato.ofx','X-Sha256':hashlib.sha256(ofx).hexdigest(),'Content-Type':'application/octet-stream'})
    suporte = pdf and os.environ.get('SUPORTE_FICTICIO_LOCAL') == '1'
    if suporte:
        from testar_confronto_suportes import nota
        conteudo = nota()['conteudo']['paginas'][0]['texto'].replace('/10/2026', '/09/2026').encode('utf-8')
        req('PUT',f'/lotes/{lote}/arquivos',conteudo,{'X-Nome-Arquivo':'nota-ficticia.txt','X-Sha256':hashlib.sha256(conteudo).hexdigest(),'Content-Type':'application/octet-stream'})
    sol=req('POST',f'/lotes/{lote}/iniciar',{'conferencia_humana':True})['sol']
    for _ in range(180):
        d=req('GET',f'/solicitacoes/{sol}')
        if d['execucao']['status']!='EM_EXECUCAO' and d['estado']=='AGUARDANDO_SUPERVISOR' and not servidor.EM_EXECUCAO['sol']:break
        time.sleep(.5)
    else:raise AssertionError('Processamento local não terminou.')
    fin=req('GET',f'/solicitacoes/{sol}/financeiro')
    assert fin['metodo_empresa']['empresa']==EMP and not fin['metodo_empresa']['executa_regras']
    assert fin['financeiro']['metodo_empresa']['empresa']==EMP
    assert fin['financeiro']['resumo']['movimentos']==(3 if pdf else 1),fin
    assert fin['bancos']['resumo']['propostos']==0,fin
    if suporte:
        assert fin['bancos']['resumo']['incompletos']==3
        assert len(fin['financeiro']['sugestoes'])==1
        assert fin['financeiro']['sugestoes'][0]['documento'] in {d['id'] for d in fin['financeiro']['documentos']}
    if pdf:
        assert any(p['tipo']=='SALDO_INICIAL_AUSENTE' for p in fin['financeiro']['pendencias'])
        assert fin['financeiro']['verificacao_extratos'][0]['situacao']=='SEM_VERIFICACAO_ARITMETICA'
    assert all(l['status']=='INCOMPLETO' and l['tipo'] not in ('ADIANTAMENTO_FORNECEDOR','ADIANTAMENTO_CLIENTE') for l in fin['bancos']['lancamentos'])
    registro=servidor.coordenador.ler_registro()['solicitacoes'][sol]
    assert registro['modo']=='SIMULAÇÃO' and registro['executor_documentos']=='LOCAL_SEM_MODELO'
    assert registro['triagem_documentos'][0]['area']=='FINANCEIRO'
    assert registro['fluxo']=='FINANCEIRO_BANCOS'
    if fluxo_origem=='DOCUMENTOS': assert registro['fluxo_origem']=='DOCUMENTOS'
    assert registro['tarefas_areas']['FINANCEIRO']['estado'] in ('ENTREGUE','ENTREGUE_COM_PENDENCIAS')
    # Conciliação executa depois da Contabilidade (rodada 03/11/2026); escopo continua SIMULAÇÃO (aqui, com pendências)
    assert registro['tarefas_areas']['CONCILIACAO']['estado'] in ('ENTREGUE','ENTREGUE_COM_PENDENCIAS') and registro.get('conciliacao')
    assert registro['escopo_resultado']=='SIMULACAO_CONCILIACAO_PARCIAL'
    assert not ORDEM.exists()
    assert req('GET','/solicitacoes')['contagem']['decisoes']==1
    original=(servidor.RUNTIME/'execucoes'/sol/'documentos-local.json').read_bytes()
    req('POST',f'/solicitacoes/{sol}/revisao-piloto',{'acao':'encerrar','justificativa':'Encerramento ficticio da revisao parcial','confirmado':True})
    encerrada=req('GET',f'/solicitacoes/{sol}')
    assert encerrada['estado']=='ENCERRADA' and encerrada['revisao_parcial_encerrada']
    assert original==(servidor.RUNTIME/'execucoes'/sol/'documentos-local.json').read_bytes()
    req('POST',f'/solicitacoes/{sol}/revisao-piloto',{'acao':'reabrir','justificativa':'Reabertura ficticia sem reprocessar','confirmado':True})
    assert req('GET',f'/solicitacoes/{sol}')['estado']=='AGUARDANDO_SUPERVISOR'
    for acao in ('estudar','decidir-estudo','simular-estudo'):
        try:
            req('POST',f'/empresas/{EMP}/{acao}',{})
            raise AssertionError('Recurso de estudo deveria estar desativado.')
        except AssertionError as exc:
            assert exc.args[0][0]==410,exc
    if os.environ.get('CAPTURAS_LOCAL'):
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from navegador_local import verificar
        verificar(RAIZ,srv.server_port,EMP,sol,os.environ['CAPTURAS_LOCAL'],empresa_pendente=EMP_PEND,esperar_candidato=suporte)
    print('PASS: cadastro → plano → bancos → piloto → Documentos LOCAL → Financeiro → Bancos → Supervisor; CLI Claude inexistente.')
    print('PASS: sem suporte permanece incompleto, sem adiantamentos automáticos; modo SIMULAÇÃO e nenhuma ordem residual.')
    print('PASS: aprendizado por razão removido; rotas antigas recusadas sem alterar arquivos.')
finally:
    srv.shutdown();srv.server_close()
    # Apenas a empresa temporária criada por este teste; nunca RECEBIDOS de outra empresa.
    for criada,nome in ((BASE,EMP),(BASE_PEND,EMP_PEND)):
        if criada.exists() and criada.resolve().parent==CLIENTES.resolve() and criada.name==nome and not criada.is_symlink():
            def permissao(fn,p,exc):
                os.chmod(p,0o700);fn(p)
            shutil.rmtree(criada,onerror=permissao)
    if ORDEM.exists():
        ordem=json.loads(ORDEM.read_text(encoding='utf-8'))
        if ordem.get('empresa')==EMP:ORDEM.unlink()
    tmp.cleanup()
