"""CONCILIAÇÃO CAIXINHA pela TELA do Escritório Virtual (UI-CX-01..10). Chrome sem janela, cliques reais. Servidor REAL em ambiente
ISOLADO; empresa e documentos 100% FICTÍCIOS.

Navegação "Caixinha" → lista da competência → Configurar (sugestões do plano, regras aprovadas) → Enviar documentos pela tela →
painel RESUMO (TRIBUTOS · FOLHA · CAIXA · PENDÊNCIAS) → STATUS → conta aberta com pagamentos e origem (página) → simulação do TXT →
aprovação pela frase → TXT liberado (empresa fictícia).

Uso: .venv/bin/python -I TESTES/ESCRITORIO/testar_caixinha_navegador.py [pasta para capturas]
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
sys.path.insert(0, str(RAIZ / "TESTES" / "ESCRITORIO"))
sys.path.insert(0, str(RAIZ / "TESTES" / "CAIXINHA"))
import ambiente_isolado as ai  # noqa: E402
AMB = ai.criar("prime-caixinha-ui-")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import cenario_complementar as cc  # noqa: E402
import cenario_caixinha as cx  # noqa: E402
import ficticios_caixinha as fc  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402
FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-caixinha-"))
FOTOS.mkdir(parents=True, exist_ok=True)
resultados = []


def porta_livre():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Tela:
    """Mesmo protocolo das baterias de navegador existentes (cliques reais via CDP)."""
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


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:300]))


def texto(t, sel):
    return t.js(f"(document.querySelector({json.dumps(sel)})||{{}}).innerText||''")


def bateria(t, cli):
    A = cx.cadastrar(cli, "A", ficticia=True, clientes=AMB.clientes)
    t.js("location.reload()")
    time.sleep(1.5)
    t.esperar("window.EV && window.EV.caixinha", 30)
    registrar("UI-CX-01 navegação principal ganha 'Caixinha' (mesma aplicação, sem segunda tela)",
              t.js("!!document.querySelector('.gestao-nav [data-pagina=caixinha]')"))
    t.clicar("document.querySelector('.gestao-nav [data-pagina=caixinha]')")
    t.esperar("document.querySelector('.cxn [data-empresa]')", 30)
    item = texto(t, f".cxn [data-empresa='{A}']")
    registrar("UI-CX-02 lista da competência com a empresa Caixinha, a categoria e o aviso de piloto ainda não habilitado",
              "Sem solicitação" in item and "Piloto Caixinha ainda não habilitado" in item, item[:200])
    t.clicar(f"Array.from(document.querySelectorAll('.cxn [data-empresa=\"{A}\"] button')).find(b=>b.textContent==='Configurar')")
    t.esperar("document.querySelector('.cxn select')", 30)
    sel = t.js("Array.from(document.querySelectorAll('.cxn .gestao-card select')).slice(0,5).map(s=>s.value)")
    registrar("UI-CX-03 configuração: contas sugeridas pela descrição do plano DA EMPRESA já pré-selecionadas (sem gravar)",
              sel == ["11", "401", "402", "403", "301"], sel)
    t.js("""(()=>{const ss=Array.from(document.querySelectorAll('.cxn select'));const p=ss.find(s=>Array.from(s.options).some(o=>o.value==='DATA_PAGAMENTO_OU_ULTIMO_DIA'));
      p.value='DATA_PAGAMENTO_OU_ULTIMO_DIA';const f=ss.find(s=>Array.from(s.options).some(o=>o.value==='DATA_FIXA'));f.value='ULTIMO_DIA_COMPETENCIA';})()""")
    t.clicar("Array.from(document.querySelectorAll('.cxn button')).find(b=>b.textContent==='Gravar proposta')")
    t.esperar("Array.from(document.querySelectorAll('.cxn input')).some(i=>i.closest('label')&&i.closest('label').innerText.includes('VALIDADO REGRA CAIXINHA'))", 20)
    for chave in ("CONFIGURACAO", "POLITICA_FOLHA"):
        frase = f"VALIDADO REGRA CAIXINHA {A} {chave}"
        t.digitar(f"Array.from(document.querySelectorAll('.cxn label')).find(l=>l.innerText.includes({json.dumps(frase)})).querySelector('input')", frase)
        t.clicar(f"Array.from(document.querySelectorAll('.cxn label')).find(l=>l.innerText.includes({json.dumps(frase)})).nextElementSibling")
        time.sleep(1.2)
    t.digitar("Array.from(document.querySelectorAll('.cxn label')).find(l=>l.innerText.includes('CONFIRMO PILOTO')).querySelector('input')", f"CONFIRMO PILOTO {A}")
    t.clicar("Array.from(document.querySelectorAll('.cxn button')).find(b=>b.textContent.startsWith('Habilitar piloto'))")
    ok = t.esperar("document.querySelector('.cxn').innerText.includes('Conciliação Caixinha habilitada')", 20)
    regras = json.loads((AMB.clientes / A / "REGRAS-CAIXINHA.json").read_text(encoding="utf-8"))
    registrar("UI-CX-04 pela tela: proposta gravada, configuração e política da folha confirmadas com a frase exata, piloto habilitado",
              ok and regras["configuracao"]["situacao"] == "APROVADA" and regras["politica_folha"]["situacao"] == "APROVADA",
              (ok, regras["configuracao"]["situacao"], regras["politica_folha"]["situacao"]))
    t.cdp.foto(FOTOS / "01-configuracao.png")
    # envio pela tela
    pasta = AMB.raiz / "upload"
    pasta.mkdir()
    caminhos = []
    for n, b in fc.documentos("A"):
        (pasta / n).write_bytes(b)
        caminhos.append(pasta / n)
    t.clicar("Array.from(document.querySelectorAll('.cxn button')).find(b=>b.textContent==='Voltar')")
    t.clicar(f"Array.from(document.querySelectorAll('.cxn [data-empresa=\"{A}\"] button')).find(b=>b.textContent==='Enviar documentos')")
    t.esperar("document.querySelector('.cxn input[type=file]')", 20)
    t.js("(()=>{const m=document.querySelector('.cxn input[type=month]');m.value='2026-10';})()")
    t.arquivos(".cxn input[type=file]", caminhos)
    t.js("document.querySelector('.cxn .cxn-sel input').click()")
    t.clicar("Array.from(document.querySelectorAll('.cxn button')).find(b=>b.textContent==='Enviar e iniciar a conciliação')")
    ok = t.esperar("document.querySelector('.cxn-resumo')", 120)
    resumo = texto(t, ".cxn-resumo")
    registrar("UI-CX-05 envio e execução pela tela; painel com RESUMO em quatro blocos: TRIBUTOS, FOLHA, CAIXA, PENDÊNCIAS",
              ok and all(x in resumo for x in ("TRIBUTOS", "FOLHA", "CAIXA", "PENDÊNCIAS")), resumo[:300])
    registrar("UI-CX-06 valores do painel vêm do processamento (baixas tributárias, último líquido, Caixa projetado)",
              all(x in resumo for x in ("11.655,65", "4.047,65", "24.285,90", "87.849,05")), resumo[:500])
    t.cdp.foto(FOTOS / "02-painel.png")
    st = texto(t, ".cxn .gestao-card")
    registrar("UI-CX-07 STATUS das etapas (Contábil, Fiscal, DP, Conciliação Caixinha) concluídas", st.count("CONCLUIDA") >= 4, st[:300])
    t.clicar("Array.from(document.querySelectorAll('.cxn details > summary')).find(s=>s.textContent.startsWith('402'))")
    conta = t.js("Array.from(document.querySelectorAll('.cxn details')).find(d=>d.querySelector('summary').textContent.startsWith('402')).innerText")
    origem = t.js("Array.from(document.querySelectorAll('.cxn details')).find(d=>d.querySelector('summary').textContent.startsWith('402')).querySelector('button.gestao-link')?.textContent||''")
    registrar("UI-CX-08 conta aberta: pagamentos associados, classificação, critérios e ORIGEM com documento e página (botão)",
              "Paga e não contabilizada" in conta and "Paga e contabilizada" in conta and "p. " in origem, (conta[:200], origem))
    t.cdp.foto(FOTOS / "03-conta.png")
    t.clicar("Array.from(document.querySelectorAll('.cxn button')).find(b=>b.textContent.startsWith('Simular o TXT'))")
    ok = t.esperar("document.querySelector('.cxn-marca')", 20)
    registrar("UI-CX-09 simulação do TXT visível com o aviso NÃO IMPORTAR (nenhum arquivo gravado)",
              ok and "NÃO IMPORTAR" in texto(t, ".cxn-acao") and texto(t, ".cxn-marca").count("\n") == 8 and not (AMB.liberados / A).exists(),
              texto(t, ".cxn-acao")[:200])
    sol = sorted(ai.registro_isolado()["solicitacoes"])[-1]
    t.digitar(f"Array.from(document.querySelectorAll('.cxn-acao label')).find(l=>l.innerText.includes('APROVO')).querySelector('input')", f"APROVO FECHAMENTO {sol}")
    t.digitar("Array.from(document.querySelectorAll('.cxn-acao label')).find(l=>l.innerText.startsWith('Justificativa')).querySelector('input')", "Baixas conferidas (fictício).")
    t.clicar("Array.from(document.querySelectorAll('.cxn-acao button')).find(b=>b.textContent==='Aprovar as baixas propostas')")
    ok = t.esperar("document.querySelector('.cxn-acao') && document.querySelector('.cxn-acao').innerText.includes('Baixar TXT liberado')", 40)
    registrar("UI-CX-10 aprovação pela frase exata → TXT liberado (empresa fictícia) com botão de download; nada importado",
              ok and (AMB.liberados / A / "2026-10" / f"lanctos_{A}_2026-10_{sol}.txt").is_file(), texto(t, ".cxn-acao")[:200])
    t.cdp.foto(FOTOS / "04-aprovado.png")


def main():
    antes = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    perfil = tempfile.mkdtemp(prefix="chrome-caixinha-")
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
        assert t.esperar("window.EV && window.EV.operacao && window.EV.caixinha", 30), "página não carregou"
        bateria(t, cli)
    except Exception as exc:  # noqa: BLE001
        import traceback
        registrar("UI-CX-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-400:]}")
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
    registrar("UI-CX-99 ambiente operacional intocado", foto_operacional() == antes)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {c}" + ("" if ok else f"  → {d}"))
    print(f"TOTAL: {len(resultados)} · PASSARAM: {len(resultados) - falhas} · FALHARAM: {falhas} · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
