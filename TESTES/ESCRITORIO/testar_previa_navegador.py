"""PRÉVIA DO FECHAMENTO e identificação do AMBIENTE pela TELA (UI-PF-01..12). Chrome sem janela, cliques reais. Servidor REAL em
ambiente ISOLADO; empresas e documentos 100% FICTÍCIOS (mini fechamento completo da amostra).

Fluxo: faixa AMBIENTE REAL → SOL do fechamento recebida e classificada → aba "Prévia do fechamento" (5 departamentos) → "Preparar
fechamento" (parar após o Financeiro) → checkpoint na prévia → continuação autorizada → prévia pronta (0 lançamentos) → pendências
filtradas por departamento → proveniência visível → "Adicionar documentos ao fechamento" com vários arquivos → faixa DEMONSTRAÇÃO.

Uso: .venv/bin/python -I TESTES/ESCRITORIO/testar_previa_navegador.py [pasta para capturas]
"""
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(RAIZ / "TESTES"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import ambiente_isolado as ai  # noqa: E402
AMB = ai.criar("prime-previa-ui-")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import amostra_ficticia  # noqa: E402
import reprocessamento as rp  # noqa: E402
import cenario_complementar as cc  # noqa: E402
import cenario_fechamento as cf  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-previa-"))
FOTOS.mkdir(parents=True, exist_ok=True)
resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:300]))


def porta_livre():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Tela:
    def __init__(self, cdp):
        self.cdp, self.n = cdp, 0

    def js(self, e):
        return self.cdp.js(e)

    def esperar(self, cond, s=30):
        fim = time.time() + s
        while time.time() < fim:
            try:
                if self.js("!!(" + cond + ")"):
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        return False

    def clicar(self, expr, s=30):
        self.n += 1
        marca = f"c{self.n}"
        if not self.esperar(f"(()=>{{const e=({expr});if(e&&!e.disabled&&!e.hidden){{e.dataset.alvoTeste='{marca}';return true}}return false}})()", s):
            self.cdp.foto(FOTOS / f"falha-{marca}.png")
            raise AssertionError(f"elemento não encontrado/habilitado: {expr}")
        xy = self.js(f"(()=>{{const e=document.querySelector(\"[data-alvo-teste='{marca}']\");e.scrollIntoView({{block:'center'}});"
                     "const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
        for tipo in ("mousePressed", "mouseReleased"):
            self.cdp.chamar("Input.dispatchMouseEvent", type=tipo, button="left", clickCount=1, **xy)
        time.sleep(0.2)

    def digitar(self, expr, texto):
        self.js(f"(()=>{{const e=({expr});e.focus();e.select&&e.select()}})()")
        self.cdp.chamar("Input.insertText", text=texto)
        time.sleep(0.1)

    def arquivos(self, seletor, caminhos):
        raiz = self.cdp.chamar("DOM.getDocument", depth=-1, pierce=True)["root"]["nodeId"]
        no = self.cdp.chamar("DOM.querySelector", nodeId=raiz, selector=seletor)["nodeId"]
        self.cdp.chamar("DOM.setFileInputFiles", files=[str(c) for c in caminhos], nodeId=no)


def abrir_previa(t, sol):
    t.js(f"window.EV.operacao.acompanhar('{sol}')")
    t.clicar("document.querySelector('.ac-aba[data-aba=fechamento]')", 40)
    return t.esperar("document.querySelector('.pf-cabecalho')", 60)


def texto(t, sel):
    return t.js(f"(document.querySelector({json.dumps(sel)})||{{}}).innerText||''")


def bateria(t, cli, url):
    R = servidor.RUNTIME
    faixa = t.js("(()=>{const f=document.querySelector('.amb-faixa');return f?[f.dataset.ambiente,f.innerText,document.title]:null})()")
    registrar("UI-PF-01 faixa de identificação 'AMBIENTE REAL' visível no topo e no título da aba (servidor padrão)",
              faixa and faixa[0] == "REAL" and "AMBIENTE REAL" in faixa[1] and faixa[2].startswith("[REAL]"), faixa)
    opcoes = t.js("Array.from(document.querySelectorAll('select option')).map(o=>o.value)")
    registrar("UI-PF-02 nova solicitação oferece o fluxo 'Fechamento do mês' (recebe e classifica tudo; nada executa)", "FECHAMENTO" in opcoes, opcoes[:12])

    amostra_ficticia.preparar(R)
    sol = cf.abrir_fechamento(cli, cf.A, cf.documentos("A"))
    assert cc.ocioso(servidor, ai.registro_isolado)
    ok = abrir_previa(t, sol)
    cards = t.js("Array.from(document.querySelectorAll('.pf-dep')).map(c=>[c.dataset.departamento,c.dataset.status])")
    cab = texto(t, ".pf-cabecalho")
    registrar("UI-PF-03 aba 'Prévia do fechamento': cabeçalho (empresa, competência, SOL) e os CINCO departamentos na ordem Fiscal, "
              "Financeiro, Contábil, DP, Conciliação",
              ok and [c[0] for c in cards] == ["FISCAL", "FINANCEIRO", "CONTABIL", "DP", "CONCILIACAO"] and cf.A in cab and "2026-10" in cab and sol in cab,
              (cards, cab[:160]))
    registrar("UI-PF-04 antes de preparar: status 'Não iniciado' (Fiscal, Financeiro, Contábil, DP) e nenhum lançamento efetivado",
              all(c[1] == "NAO_INICIADO" for c in cards[:4]) and "Lançamentos efetivados: 0" in cab, cards)
    docs = texto(t, ".pf-docs-resumo")
    registrar("UI-PF-05 documentos recebidos agrupados por departamento (Fiscal 7, Financeiro 4, Contábil 2, DP 3, Conciliação 4)",
              all(x in docs for x in ("Fiscal: 7", "Financeiro: 4", "Contábil: 2", "DP: 3", "Conciliação: 4", "Balancete: 1", "Razão: 1")), docs[:300])
    cdp_foto = t.cdp.foto
    cdp_foto(FOTOS / "01-previa-nao-iniciada.png")

    t.clicar("document.querySelector('.ac-aba[data-aba=resumo]')")
    rotulo = t.js("(document.querySelector('.sd-botao-reprocessar')||{}).textContent")
    t.clicar("document.querySelector('.sd-botao-reprocessar')", 40)
    t.esperar("document.querySelector('.sd-parar-check')", 20)
    titulo = texto(t, ".sd-caixa h2")
    registrar("UI-PF-06 SOL do fechamento oferece 'Preparar fechamento' (janela própria) com 'parar após o Financeiro' já marcado",
              rotulo == "Preparar fechamento" and titulo == "Preparar fechamento" and t.js("document.querySelector('.sd-parar-check').checked"), (rotulo, titulo))
    t.digitar("document.querySelector('.sd-caixa textarea')", "Preparar o fechamento fictício de outubro.")
    t.clicar("document.querySelector('[data-acao=criar-tentativa]')")
    t.clicar("document.querySelector('[data-acao=iniciar-execucao]')", 30)
    t.esperar("document.querySelector('.sd-caixa .cr-msg').dataset.tipo==='ok'", 30)
    time.sleep(1)
    assert cc.ocioso(servidor, ai.registro_isolado)
    t.js("document.querySelector('.sd-camada') && (document.querySelector('.sd-camada').hidden=true)")
    abrir_previa(t, sol)
    t.esperar("document.querySelector('.pf-dep[data-departamento=FINANCEIRO]')", 30)
    cards = dict(t.js("Array.from(document.querySelectorAll('.pf-dep')).map(c=>[c.dataset.departamento,c.dataset.status])"))
    dec = texto(t, ".pf-decisoes")
    registrar("UI-PF-07 checkpoint na prévia: Financeiro e Contábil 'Aguardando Supervisor'; decisão 'Autorizar a continuação' visível",
              cards.get("FINANCEIRO") == "AGUARDANDO_SUPERVISOR" and cards.get("CONTABIL") == "AGUARDANDO_SUPERVISOR"
              and "Autorizar a continuação após o Financeiro" in dec, (cards, dec[:200]))
    t.cdp.foto(FOTOS / "02-previa-checkpoint.png")

    t.clicar("document.querySelector('.ac-aba[data-aba=resumo]')")
    t.clicar("document.querySelector('.sd-botao-continuar')", 40)
    t.digitar("document.querySelector('.sd-caixa textarea')", "Revisei o Financeiro e as consultas às outras áreas (fictício).")
    t.clicar("document.querySelector('[data-acao=autorizar-continuacao]')")
    t.esperar("document.querySelector('.sd-caixa .cr-msg').dataset.tipo==='ok'", 30)
    time.sleep(1)
    assert cc.ocioso(servidor, ai.registro_isolado)
    t.js("document.querySelector('.sd-camada') && (document.querySelector('.sd-camada').hidden=true)")
    abrir_previa(t, sol)
    t.esperar("document.querySelector('.pf-cabecalho[data-status-geral=PREVIA_PRONTA]')", 60)
    cab = texto(t, ".pf-cabecalho")
    contabil = texto(t, ".pf-dep[data-departamento=CONTABIL]")
    registrar("UI-PF-08 prévia final: 'Prévia pronta para a revisão do Supervisor'; Contábil com propostas e 'Lançamentos efetivados 0'",
              "Prévia pronta" in cab and "Lançamentos efetivados\n0" in contabil.replace("\t", "\n") and not ai.registro_isolado()["solicitacoes"][sol].get("aprovacao"),
              contabil[:200])
    cab_pend = t.js("Array.from(document.querySelectorAll('.pf-tab-pend th')).map(x=>x.textContent)")
    registrar("UI-PF-09 pendências com Classificação, Departamento responsável, Problema, Impacto, O que fazer e Origem",
              cab_pend == ["Classificação", "Departamento responsável", "Problema", "Impacto", "O que fazer", "Origem"], cab_pend)
    t.clicar("document.querySelector('.pf-dep[data-departamento=DP] .pf-ver')")
    deps = t.js("Array.from(document.querySelectorAll('.pf-tab-pend tbody tr td:nth-child(2)')).map(x=>x.textContent)")
    registrar("UI-PF-10 'Ver pendências' de um departamento filtra a lista por departamento (DP)",
              deps and set(deps) == {"DP"} and t.js("document.querySelector('.pf-filtro').value") == "DP", deps)
    t.js("document.querySelectorAll('.pf-det').forEach(d=>d.open=true)")
    prop = texto(t, ".pf-tab-propostas")
    registrar("UI-PF-11 proveniência visível ('de onde veio'): departamento, registro e sha256 do resultado em cada proposta; contas legíveis",
              "Origem: Contábil" in prop and "registro bancos-1" in prop and "sha256" in prop and "[object Object]" not in prop, prop[:250])
    t.cdp.foto(FOTOS / "03-previa-pronta.png")

    sol2 = cf.abrir_fechamento(cli, cf.A, [d for d in cf.documentos("A") if d[0].startswith("01_")])
    assert cc.ocioso(servidor, ai.registro_isolado)
    pasta = Path(tempfile.mkdtemp(prefix="ui-previa-docs-"))
    caminhos = []
    for nome, conteudo in [d for d in cf.documentos("A") if d[0][:2] in ("20", "21")]:
        (pasta / nome).write_bytes(conteudo)
        caminhos.append(pasta / nome)
    t.js(f"window.EV.operacao.acompanhar('{sol2}')")
    t.clicar("document.querySelector('.ac-aba[data-aba=resumo]')", 40)
    t.clicar("document.querySelector('.sd-botao-complemento')", 40)
    multiplo = t.js("document.querySelector('.sd-arquivo').multiple")
    t.arquivos(".sd-arquivo", caminhos)
    t.digitar("document.querySelector('.sd-caixa textarea')", "Balancete e razão recebidos depois (fictício).")
    t.clicar(f"Array.from(document.querySelectorAll('.sd-caixa button')).find(b=>b.textContent==='Revisar')")
    t.clicar("document.querySelector('[data-acao=enviar-complemento]')", 30)
    t.esperar("document.querySelector('.sd-classificacao-dep')", 60)
    res = texto(t, ".sd-revisao")
    registrar("UI-PF-12 'Adicionar documentos ao fechamento' aceita VÁRIOS arquivos e mostra a classificação por departamento; nada executa",
              multiplo and "Contábil: 2" in res and not ai.registro_isolado()["solicitacoes"][sol2].get("plano_etapas"), res[:200])
    shutil.rmtree(pasta, ignore_errors=True)

    servidor.AMBIENTE = "DEMONSTRACAO"
    try:
        t.cdp.chamar("Page.navigate", url=url)
        t.esperar("document.querySelector('.amb-faixa')", 30)
        demo = t.js("(()=>{const f=document.querySelector('.amb-faixa');return [f.dataset.ambiente,f.innerText,document.title]})()")
        registrar("UI-PF-13 servidor de demonstração mostra a faixa 'DEMONSTRAÇÃO · dados fictícios' (nunca confundida com o REAL)",
                  demo[0] == "DEMONSTRACAO" and "DEMONSTRAÇÃO" in demo[1] and demo[2].startswith("[DEMONSTRAÇÃO]"), demo)
        t.cdp.foto(FOTOS / "04-faixa-demonstracao.png")
    finally:
        servidor.AMBIENTE = "REAL"


def main():
    antes = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    perfil = tempfile.mkdtemp(prefix="chrome-previa-")
    porta_cdp = porta_livre()
    chrome = None
    try:
        cli = cc.Cliente(srv.server_port)
        chrome = subprocess.Popen([str(CHROME), "--headless=new", f"--remote-debugging-port={porta_cdp}", f"--user-data-dir={perfil}",
                                   "--window-size=1440,1000", "--no-first-run", "--disable-extensions", url],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cdp = None
        for _ in range(80):
            try:
                alvos = json.load(urllib.request.urlopen(f"http://127.0.0.1:{porta_cdp}/json/list", timeout=2))
                cdp = CDP(next(a for a in alvos if a.get("type") == "page" and a["url"].startswith(url))["webSocketDebuggerUrl"])
                break
            except Exception:
                time.sleep(0.25)
        assert cdp, "Chrome não respondeu na porta de depuração"
        cdp.chamar("Page.enable")
        cdp.chamar("DOM.enable")
        cdp.chamar("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
        t = Tela(cdp)
        assert t.esperar("window.EV && window.EV.operacao && window.EV.previa && window.EV.solDocumentos", 30), "página não carregou"
        bateria(t, cli, url)
    except Exception as exc:  # noqa: BLE001
        import traceback
        registrar("UI-PF-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-400:]}")
    finally:
        if chrome:
            chrome.terminate()
            try:
                chrome.wait(15)
            except subprocess.TimeoutExpired:
                chrome.kill()
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(perfil, ignore_errors=True)
    registrar("UI-PF-99 ambiente operacional intocado", foto_operacional() == antes)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {c}" + ("" if ok else f"  → {d}"))
    print(f"TOTAL: {len(resultados)} · PASSARAM: {len(resultados) - falhas} · FALHARAM: {falhas} · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
