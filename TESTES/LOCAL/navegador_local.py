"""Conferência visual e navegação por cliques do Chrome; sem Claude."""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def verificar(raiz, porta, empresa, sol, fotos, empresa_pendente=None, esperar_candidato=False):
    sys.path.insert(0, str(raiz/'TESTES/API'))
    from e2e_navegador import CDP, CHROME
    fotos=Path(fotos);fotos.mkdir(parents=True,exist_ok=True)
    perfil=tempfile.TemporaryDirectory(prefix='chrome-prime-local-')
    url=f'http://127.0.0.1:{porta}/'
    chrome=subprocess.Popen([str(CHROME),'--headless=new','--remote-debugging-port=9347',f'--user-data-dir={perfil.name}',
                             '--window-size=1440,1000','--no-first-run','--disable-extensions',url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    cdp=None
    try:
        for _ in range(60):
            try:
                alvos=json.load(urllib.request.urlopen('http://127.0.0.1:9347/json/list',timeout=2))
                alvo=next(a for a in alvos if a.get('type')=='page' and a['url'].startswith(url))
                cdp=CDP(alvo['webSocketDebuggerUrl']);break
            except Exception:time.sleep(.2)
        assert cdp,'Chrome não iniciou'
        def esperar(js):
            for _ in range(80):
                if cdp.js('!!('+js+')'):return
                time.sleep(.15)
            cdp.foto(fotos/'falha.png')
            raise AssertionError('Condição não encontrada: '+js+'; tela: '+str(cdp.js("document.querySelector('.gestao')?.innerText")))
        def clicar(selector):
            esperar(f'document.querySelector({json.dumps(selector)})')
            xy=cdp.js(f"(() => {{const e=document.querySelector({json.dumps(selector)});if(!e)return null;e.scrollIntoView({{block:'center'}});const r=e.getBoundingClientRect();return {{x:r.x+r.width/2,y:r.y+r.height/2}};}})()")
            assert xy,selector
            cdp.chamar('Input.dispatchMouseEvent',type='mousePressed',button='left',clickCount=1,**xy)
            cdp.chamar('Input.dispatchMouseEvent',type='mouseReleased',button='left',clickCount=1,**xy)
        esperar("document.querySelector('.gestao')?.hidden && document.querySelector('.gestao-nav')")
        def escritorio_livre():
            time.sleep(.25)
            r=cdp.js("(()=>{const palco=document.querySelector('.palco').getBoundingClientRect();const painel=[document.querySelector('.gestao'),document.querySelector('.op-painel')].find(p=>!p.hidden);const limite=painel?painel.getBoundingClientRect().right:document.querySelector('.gestao-nav').getBoundingClientRect().right;return {esquerda:palco.left,limite,largura:palco.width,visivel:getComputedStyle(document.querySelector('.palco')).visibility};})()")
            assert r['esquerda']>=r['limite']-1 and r['largura']>200 and r['visivel']=='visible',r
        escritorio_livre();cdp.foto(fotos/'01-escritorio-inicial.png')
        largura_ajustada=cdp.js("document.querySelector('#tela').getBoundingClientRect().width")
        clicar('[aria-label="Aumentar escritório"]')
        esperar(f"document.querySelector('#tela').getBoundingClientRect().width>{largura_ajustada}*1.1")
        cdp.foto(fotos/'01-zoom-ampliado.png')
        clicar('[aria-label="Mostrar escritório inteiro"]')
        esperar(f"Math.abs(document.querySelector('#tela').getBoundingClientRect().width-{largura_ajustada})<2")
        if empresa_pendente:
            clicar('.op-botao')
            esperar(f"Array.from(document.querySelectorAll('.op-form select')[0].options).some(o=>o.value==={json.dumps(empresa_pendente)})")
            cdp.js(f"(()=>{{const s=document.querySelector('.op-form select');s.value={json.dumps(empresa_pendente)};s.dispatchEvent(new Event('change'));}})()")
            esperar("!document.querySelector('.op-cadastro-pendente').hidden")
            assert cdp.js("document.querySelector('.op-iniciar').disabled && document.querySelector('.op-form input[type=file]').disabled")
            assert cdp.js("document.querySelector('.op-cadastro-pendente').textContent.includes('Vincular as contas bancárias')")
            escritorio_livre();cdp.foto(fotos/'00-empresa-pendente-na-solicitacao.png')
            clicar('.op-cadastro-pendente button')
            esperar("document.querySelector('.gestao h1')?.textContent==='CLIENTE FICTICIO COM CADASTRO PENDENTE'")
            escritorio_livre()
            clicar('.op-botao')
            esperar("!document.querySelector('.op-painel').hidden")
            cdp.js(f"(()=>{{const s=document.querySelector('.op-form select');s.value={json.dumps(empresa)};s.dispatchEvent(new Event('change'));}})()")
            esperar("document.querySelector('.op-cadastro-pendente').hidden && !document.querySelector('.op-iniciar').disabled")
            clicar('.op-cabeca .fechar')
            print('PASS: empresa cadastrada pendente aparece na solicitação, explica faltas e abre cadastro; upload/início bloqueados; empresa autorizada continua utilizável.')
        clicar('[data-pagina="inicio"]');esperar("document.querySelector('.gestao-lista .gestao-item')")
        escritorio_livre();cdp.foto(fotos/'01-resumo-lateral.png')
        clicar('[data-pagina="solicitacoes"]')
        esperar("document.querySelector('.gestao h1')?.textContent === 'Consultar solicitações'")
        esperar("document.querySelector('.gestao-lista .gestao-item')")
        clicar('.gestao-lista .gestao-item button')
        esperar("document.querySelector('.ac-resumo') && !document.querySelector('.op-painel').hidden")
        escritorio_livre()
        assert sol in cdp.js("document.querySelector('.op-sol').textContent")
        if esperar_candidato:
            esperar("document.querySelector('.op-sol').textContent.includes('nota-ficticia.txt')")
            assert cdp.js("document.querySelector('.op-sol').textContent.includes('valor 80.00 igual ao débito')")
            assert cdp.js("Array.from(document.querySelectorAll('.op-sol button')).some(b=>b.textContent.includes('Confirmar vínculo'))")
        cdp.foto(fotos/'02-acompanhamento.png')
        cdp.js("Array.from(document.querySelectorAll('.op-sol details')).find(d=>d.querySelector('summary')?.textContent==='Revisão parcial do piloto').open=true")
        cdp.js("(()=>{const t=document.querySelector('[aria-label=\"Justificativa da revisão parcial\"]');t.value='Revisão fictícia pela interface';t.dispatchEvent(new Event('input'));})()")
        clicar('[data-revisao-piloto="encerrar"]')
        esperar("document.querySelector('[data-revisao-piloto=reabrir]')")
        assert cdp.js("document.querySelector('.ac-resultado').textContent.includes('nenhum lançamento foi aprovado')")
        cdp.js("Array.from(document.querySelectorAll('.op-sol details')).find(d=>d.querySelector('summary')?.textContent==='Revisão parcial do piloto').open=true")
        cdp.js("(()=>{const t=document.querySelector('[aria-label=\"Justificativa da revisão parcial\"]');t.value='Reabrir revisão fictícia pela interface';t.dispatchEvent(new Event('input'));})()")
        clicar('[data-revisao-piloto="reabrir"]')
        esperar("document.querySelector('[data-revisao-piloto=encerrar]')")
        print('PASS: encerrar e reabrir revisão parcial pela tela; sem aprovação de lançamento ou fechamento integral.')
        clicar('.op-sol > button')
        esperar("document.querySelector('.op-painel').hidden && document.querySelector('.gestao h1').textContent==='Consultar solicitações'")
        clicar('[data-pagina="empresas"]')
        esperar(f"document.querySelector('[data-empresa={empresa}] [data-acao=abrir-empresa]')")
        clicar(f'[data-empresa="{empresa}"] [data-acao=abrir-empresa]')
        esperar("document.querySelector('[data-base-resumo]')")
        escritorio_livre()
        cdp.foto(fotos/'03-empresa.png')
        assert not cdp.js("document.querySelector('[data-parametros=bancos]')"),'Configuracao automatica de adiantamentos deve estar removida.'
        clicar('[data-config="plano"]')
        esperar("document.querySelector('.gestao-config-painel h3')")
        cdp.foto(fotos/'04-plano.png')
        # rodada de simplificação: a importação do plano pela tela foi REMOVIDA (as contas vêm do balancete da base inicial)
        assert not cdp.js("document.querySelector('[data-importador]')"),'Importacao do plano deve estar fora da tela.'
        assert 'Importar plano' not in cdp.js("document.querySelector('.gestao-conteudo').textContent")
        print('PASS: plano contábil atual em resumo; sem importação de plano pela tela.')
        assert not cdp.js("document.querySelector('[data-importador=razao]')")
        assert not cdp.js("document.querySelector('[data-parametros=bancos]')")
        clicar('[data-config="cadastro"]')
        esperar("document.querySelector('.gestao-config-painel h3')")
        assert cdp.js("document.querySelector('[data-metodo-empresa]')?.textContent.includes('Método fictício para testar isolamento.')")
        print('PASS: sem estudo por razão e sem formulário de adiantamentos automáticos.')
        clicar('[data-pagina="solicitacoes"]')
        esperar("document.querySelector('.gestao-filtros input[type=search]')")
        clicar('.gestao-filtros input[type=search]')
        cdp.chamar('Input.insertText',text='SEM-RESULTADO')
        esperar("document.querySelector('.gestao-lista').textContent.includes('Nenhuma solicitação')")
        clicar('[data-pagina="inicio"]');esperar("document.querySelector('.gestao-filas')")
        cdp.chamar('Emulation.setDeviceMetricsOverride',width=1000,height=720,deviceScaleFactor=1,mobile=False)
        time.sleep(.4)
        overflow=cdp.js("document.documentElement.scrollWidth>innerWidth || document.querySelector('.gestao').scrollWidth>document.querySelector('.gestao').clientWidth")
        cdp.foto(fotos/'05-janela-menor.png')
        assert not overflow,'Rolagem horizontal: '+str(cdp.js("Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>innerWidth+1 && getComputedStyle(e).position!=='absolute').map(e=>[e.className,e.getBoundingClientRect().right]).slice(0,20)"))
        clicar('.op-botao');esperar("!document.querySelector('.op-painel').hidden && !document.querySelector('.op-form').hidden")
        assert cdp.js("document.querySelectorAll('.op-campo select')[1].value === 'DOCUMENTOS'"),'Recepção com distribuição por área deve ser o padrão.'
        # texto do percurso completo (rodada 03/11/2026): distribuição por área, Contabilidade e Conciliação
        assert cdp.js("(()=>{const t=document.querySelector('.op-form').textContent;return t.includes('distribui por área')&&t.includes('extratos ao Financeiro')&&t.includes('Conciliação');})()")
        assert cdp.js("(()=>{const p=document.querySelector('.op-painel').getBoundingClientRect();return Array.from(document.querySelectorAll('.op-form input,.op-form select,.op-form textarea,.op-ajuda')).every(e=>e.getBoundingClientRect().right<=p.right);})()"),'Campo do formulário cortado pelo painel.'
        escritorio_livre()
        cdp.foto(fotos/'06-nova-solicitacao.png')
        clicar('.op-cabeca .fechar')
        clicar('[data-pagina="escritorio"]');esperar("document.querySelector('.gestao').hidden")
        cdp.foto(fotos/'07-escritorio.png')
        cdp.chamar('Page.reload');esperar("document.querySelector('.gestao')?.hidden && document.querySelector('.gestao-nav')")
        escritorio_livre()
        clicar('[data-pagina="solicitacoes"]');esperar("document.querySelector('[data-acao=excluir]')")
        cdp.js('window.confirm=()=>false')
        clicar('[data-acao="excluir"]')
        assert cdp.js("document.querySelectorAll('.gestao-lista .gestao-item').length") == 1
        cdp.js('window.confirm=()=>true')
        clicar('[data-acao="excluir"]');esperar("!document.querySelector('.gestao-lista .gestao-item')")
        clicar('[data-acao="lixeira"]');esperar("document.querySelector('[data-acao=restaurar]')")
        escritorio_livre();cdp.foto(fotos/'08-lixeira.png')
        clicar('[data-acao="restaurar"]');esperar("!document.querySelector('.gestao-lista .gestao-item')")
        clicar('[data-acao="ativas"]');esperar("document.querySelector('[data-acao=excluir]')")
        clicar('[data-acao="limpar-solicitacoes"]');esperar("!document.querySelector('.gestao-lista .gestao-item')")
        escritorio_livre();cdp.foto(fotos/'09-lista-limpa.png')
        print('PASS: cancelar exclusão, excluir, consultar lixeira, restaurar e limpar lista pela interface.')
        print('PASS: escritório inicial e sempre visível; painéis laterais sem sobreposição; navegação, consulta, cadastro, janela 1000x720 e recarga.')
    finally:
        if cdp:cdp.s.close()
        chrome.terminate()
        try:chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:chrome.kill();chrome.wait()
        try:perfil.cleanup()
        except PermissionError:pass
