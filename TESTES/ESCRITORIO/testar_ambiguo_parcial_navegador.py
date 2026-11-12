"""Ambiguidade PARCIAL pela TELA da Central (UI-AMB-01..10). Chrome sem janela, cliques reais (CDP). Servidor REAL em ambiente
ISOLADO; usa a "DEMONSTRAÇÃO — Ambiguidade parcial" (2 movimentos × 2 registros = 4 candidatos; dados 100% fictícios).

Uso: .venv/bin/python -I TESTES/ESCRITORIO/testar_ambiguo_parcial_navegador.py [pasta para capturas]
"""
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

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado  # noqa: E402
AMB = ambiente_isolado.criar("prime-ambiguo-ui-")
os.environ["AGENTES_PRIME_DEMO_CONCILIACAO"] = str(AMB.raiz / "demonstracao-conciliacao")
DEMO = AMB.raiz / "demonstracao-ambiguo-parcial"
os.environ["AGENTES_PRIME_DEMO_AMBIGUO"] = str(DEMO)
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import servidor  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-ambiguo-"))
FOTOS.mkdir(parents=True, exist_ok=True)
resultados = []
JUST = "Conferi os registros selecionados; soma e contraparte conferem (teste fictício)."


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

    def esperar(self, cond, s=20):
        fim = time.time() + s
        while time.time() < fim:
            try:
                if self.js("!!(" + cond + ")"):
                    return True
            except Exception:
                pass
            time.sleep(0.15)
        return False

    def clicar(self, expr, s=20):
        self.n += 1
        marca = f"c{self.n}"
        if not self.esperar(f"(()=>{{const e=({expr});if(e&&!e.disabled){{e.dataset.alvoTeste='{marca}';return true}}return false}})()", s):
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

    def card(self, chave):
        return self.js(f"(()=>{{const c=document.querySelector('.cr-card[data-card={chave}] .cr-card-n');return c?Number(c.textContent):null}})()")

    def cards(self):
        return tuple(self.card(k) for k in ("conciliados", "revisar", "ambiguos", "nao", "bloqueios"))


def item_com(valor):
    return f"Array.from(document.querySelectorAll('.cr-item')).find(e=>e.textContent.replace(/\\u00a0/g,' ').includes({json.dumps(valor)}))"


def abrir_item(t, valor):
    t.clicar(f"({item_com(valor)}).querySelector('.cr-abrir')")
    assert t.esperar("!document.querySelector('.cr-camada').hidden && document.querySelector('.cr-detalhe .cr-acoes')"), valor


def fechar_detalhe(t):
    t.js("document.querySelector('.cr-camada').hidden || document.querySelector('.cr-fechar').click()")
    t.esperar("document.querySelector('.cr-camada').hidden", 5)


def confirmar_modal(t, justificativa):
    t.esperar("!document.querySelector('.cr-camada-confirmar').hidden")
    t.digitar("document.querySelector('.cr-confirmar textarea')", justificativa)
    t.clicar("document.querySelector('.cr-camada-confirmar:not([hidden]) [data-acao=confirmar-envio]')")


def decisoes():
    p = DEMO / "decisoes.json"
    return json.loads(p.read_text(encoding="utf-8"))["eventos"] if p.exists() else []


def candidato(dia_banco, dia_relatorio):
    return (f"Array.from(document.querySelectorAll('.cr-candidato')).find(c=>{{const t=c.innerText;"
            f"return t.includes('Banco: {dia_banco}/09/2026') && t.split('\\n').some(l=>l.startsWith('{dia_relatorio}/09/2026'))}})")


def bateria(t):
    t.js("window.__semRecarga = 'sim'")
    t.clicar("document.querySelector('.cr-entrada-demo-ambiguo')")
    t.esperar("!document.querySelector('.cr').hidden && document.querySelector('.cr-card')")
    registrar("UI-AMB-01 demonstração abre com o ambíguo 2×2 (2 bloqueios)", t.js("document.querySelector('.cr-h1').textContent") ==
              "DEMONSTRAÇÃO — Ambiguidade parcial" and t.cards() == (1, 0, 1, 0, 2), t.cards())
    abrir_item(t, "R$ 20,00")
    n_cand = t.js("document.querySelectorAll('.cr-candidato').length")
    t.clicar(f"({candidato(16, 16)}).querySelector('input[type=radio]')")
    t.digitar("document.querySelector('.cr-detalhe textarea')", JUST)
    t.clicar("Array.from(document.querySelectorAll('.cr-detalhe button')).find(b=>b.textContent==='Confirmar candidato selecionado')")
    nada_antes = decisoes() == []
    t.clicar("document.querySelector('.cr-camada-confirmar:not([hidden]) [data-acao=confirmar-envio]')")
    t.esperar("document.querySelector('.cr-card[data-card=bloqueios] .cr-card-n').textContent==='1'")
    t.cdp.foto(FOTOS / "01-apos-primeira-escolha.png")
    registrar("UI-AMB-02 escolher um par resolve SÓ aquele movimento (bloqueios 2→1; nada gravado antes de confirmar)",
              n_cand == 4 and nada_antes and t.cards() == (1, 0, 1, 0, 1) and t.js("window.__semRecarga") == "sim", t.cards())
    rot = t.js(f"({item_com('R$ 20,00')}).querySelector('.cr-status').textContent")
    registrar("UI-AMB-03 o grupo continua visível como 'Ambíguo — parcialmente resolvido'", "parcialmente resolvido" in rot, rot)
    t.clicar("document.querySelector('.cr-ver-bloqueios summary')")
    linhas = t.js("[...document.querySelectorAll('.cr-bloqueio-item')].map(e=>e.innerText)")
    t.cdp.foto(FOTOS / "02-ver-bloqueios.png")
    registrar("UI-AMB-04 'Ver bloqueios' lista o remanescente (15/09) com Problema/Impacto/O que fazer",
              len(linhas) == 1 and "15/09/2026" in linhas[0] and all(x in linhas[0] for x in ("Problema", "Impacto", "O que fazer", "Ambíguo")), linhas)
    t.clicar("document.querySelector('.cr-abrir-bloqueio')")
    t.esperar("!document.querySelector('.cr-camada').hidden && document.querySelector('.cr-detalhe .cr-candidatos')")
    det = t.js("document.querySelector('.cr-detalhe').innerText")
    radios = t.js("document.querySelectorAll('.cr-candidato input[type=radio]').length")
    t.cdp.foto(FOTOS / "03-remanescente.png")
    registrar("UI-AMB-05 remanescente abre pela Central: resta 1 associação, R2 não aparece como livre, nada automático",
              radios == 1 and "resta 1 associação possível" in det and "Indisponível" in det and "Parte desta ambiguidade já foi resolvida" in det,
              (radios, det[:200]))
    t.clicar(f"({candidato(15, 15)}).querySelector('input[type=radio]')")
    t.digitar("document.querySelector('.cr-detalhe textarea')", JUST)
    t.clicar("Array.from(document.querySelectorAll('.cr-detalhe button')).find(b=>b.textContent==='Confirmar candidato selecionado')")
    t.clicar("document.querySelector('.cr-camada-confirmar:not([hidden]) [data-acao=confirmar-envio]')")
    t.esperar("document.querySelector('.cr-card[data-card=bloqueios] .cr-card-n').textContent==='0'")
    registrar("UI-AMB-06 segunda escolha explícita: 2/2 confirmados, nenhum bloqueio, 0 ambíguos", t.cards() == (1, 0, 0, 0, 0)
              and t.js("!!document.querySelector('.cr-impede-nao')") and len(decisoes()) == 2, t.cards())
    t.clicar("document.querySelector('.cr-filtro[data-filtro=aprovados]')")
    abrir_item(t, "R$ 20,00")
    n_desf = t.js("document.querySelectorAll('[data-acao=desfazer-escolha]').length")
    t.clicar(f"({candidato(16, 16)}).querySelector('[data-acao=desfazer-escolha]')")
    t.esperar("!document.querySelector('.cr-camada-confirmar').hidden")
    t.digitar("document.querySelector('.cr-confirmar textarea')", "Desfazendo para conferir de novo (teste fictício).")
    t.clicar("document.querySelector('.cr-camada-confirmar:not([hidden]) [data-acao=confirmar-envio]')")
    t.esperar("document.querySelector('.cr-card[data-card=bloqueios] .cr-card-n').textContent==='1'")
    ev = decisoes()
    registrar("UI-AMB-07 desfazer UMA escolha: o bloqueio daquele movimento volta, histórico preservado",
              n_desf == 2 and t.cards() == (1, 0, 1, 0, 1) and [e["decisao"] for e in ev] == ["APROVADO", "APROVADO", "REVOGADO"]
              and ev[2]["decisao_anterior"] == ev[0]["id"], (n_desf, t.cards()))
    t.clicar("document.querySelector('.cr-filtro[data-filtro=todos]')")
    t.clicar("document.querySelector('.cr-historico summary')")
    t.esperar("document.querySelector('.cr-tabela-hist')")
    hist = t.js("document.querySelector('.cr-historico').innerText")
    registrar("UI-AMB-08 histórico mostra as duas confirmações e o desfazer", hist.count("Confirmou associação") >= 2 and "Desfez decisão" in hist, hist[:200])
    texto = t.js("document.querySelector('.cr').innerText")
    registrar("UI-AMB-09 sem JSON nem IDs técnicos na tela", not any(x in texto for x in ('{"', "DAMB-", "CF-", "DS-")))
    registrar("UI-AMB-10 classificação do sistema continua Ambíguo em todas as decisões", all(e["classificacao_motor"] == "AMBIGUO" for e in ev))

def main():
    antes = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    perfil = tempfile.mkdtemp(prefix="chrome-ambiguo-")
    porta_cdp = porta_livre()
    chrome = None
    try:
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
        cdp.chamar("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
        t = Tela(cdp)
        assert t.esperar("document.querySelector('.cr-entrada-demo-ambiguo')", 30), "página não carregou"
        bateria(t)
    except Exception as exc:  # noqa: BLE001
        import traceback
        registrar("UI-AMB-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-400:]}")
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
    registrar("UI-AMB-99 ambiente operacional intocado", foto_operacional() == antes)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {c}" + ("" if ok else f"  → {d}"))
    print(f"TOTAL: {len(resultados)} · PASSARAM: {len(resultados) - falhas} · FALHARAM: {falhas} · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
