"""Checkpoint após o Financeiro pela TELA da SOL (UI-CK-01..10). Chrome sem janela, cliques reais. Servidor REAL em ambiente
ISOLADO; empresa e documentos 100% FICTÍCIOS. Fluxo: Reprocessar fechamento (parar após o Financeiro marcado) → Financeiro concluído →
SOL aguardando autorização → Continuar para Contabilidade/Bancos (mesma tentativa, Financeiro não repetido, Bancos uma vez).

Uso: .venv/bin/python -I TESTES/ESCRITORIO/testar_checkpoint_navegador.py [pasta para capturas]
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
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import ambiente_isolado as ai  # noqa: E402
AMB = ai.criar("prime-checkpoint-ui-")
os.environ["AGENTES_PRIME_DEMO_CONCILIACAO"] = str(AMB.raiz / "demonstracao-conciliacao")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import reprocessamento as rp  # noqa: E402
import cenario_complementar as cc  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-checkpoint-"))
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

    def arquivo(self, seletor, caminho):
        raiz = self.cdp.chamar("DOM.getDocument", depth=-1, pierce=True)["root"]["nodeId"]
        no = self.cdp.chamar("DOM.querySelector", nodeId=raiz, selector=seletor)["nodeId"]
        self.cdp.chamar("DOM.setFileInputFiles", files=[str(caminho)], nodeId=no)


def por_texto(seletor, trecho):
    return f"Array.from(document.querySelectorAll({json.dumps(seletor)})).find(e=>e.textContent.includes({json.dumps(trecho)}))"


def bateria(t, cli):
    R = servidor.RUNTIME
    sol, _ = cli.abrir_sol([("relatorio.xlsx", cc.relatorio_xlsx())])
    assert cc.ocioso(servidor, ai.registro_isolado)
    lote = cli.complementar(sol, "extrato-ficticio.pdf", cc.extrato_identificado_pdf())
    assert cli.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote}/concluir", {"confirmado": True})[0] == 201
    E = R / "execucoes" / sol
    pastas = lambda p: sorted(x.name for x in E.glob(f"{p}-*"))
    t.js(f"window.EV.operacao.acompanhar('{sol}')")
    t.clicar("document.querySelector('.sd-botao-reprocessar')", 40)
    t.esperar("document.querySelector('.sd-parar-check')", 20)
    marcado = t.js("document.querySelector('.sd-parar-check').checked")
    texto = t.js("document.querySelector('.sd-caixa').innerText")
    registrar("UI-CK-01 'Reprocessar fechamento' oferece 'Executar o Financeiro e parar para revisão' já marcado",
              marcado and "parar para revisão" in texto, texto[:200])
    t.digitar("document.querySelector('.sd-caixa textarea')", "Reprocessar com o extrato fictício e parar após o Financeiro.")
    t.clicar("document.querySelector('[data-acao=criar-tentativa]')")
    t.esperar("document.querySelector('[data-acao=iniciar-execucao]')", 30)
    t.clicar("document.querySelector('[data-acao=iniciar-execucao]')")
    t.esperar("document.querySelector('.sd-caixa .cr-msg').textContent.includes('PARAR')", 20)
    msg = t.js("document.querySelector('.sd-caixa .cr-msg').textContent")
    time.sleep(1)
    assert cc.ocioso(servidor, ai.registro_isolado)
    tent = rp.listar(R, sol)[-1]
    registrar("UI-CK-02 execução iniciada com parada: mensagem clara e tentativa pausada após o Financeiro",
              "PARAR depois do Financeiro" in msg and tent["status"] == "PAUSADA" and pastas("financeiro") == ["financeiro-1", "financeiro-2"], (msg, tent["status"]))
    registrar("UI-CK-03 Bancos e Contabilidade NÃO rodaram", pastas("bancos") == [] and pastas("conciliacao") == ["conciliacao-1"]
              and not list(E.rglob("*.csv")))
    t.js("document.querySelector('.sd-camada').hidden || Array.from(document.querySelectorAll('.sd-caixa button')).find(b=>b.textContent==='Fechar').click()")
    t.js(f"window.EV.operacao.acompanhar('{sol}')")
    ok = t.esperar("document.querySelector('.sd-checkpoint')", 40)
    painel = t.js("document.querySelector('.sd-checkpoint').innerText") if ok else ""
    t.cdp.foto(FOTOS / "01-checkpoint.png")
    registrar("UI-CK-04 (CHECK-FIN-09) tela mostra 'FINANCEIRO — Concluído'", "FINANCEIRO — Concluído" in painel, painel[:200])
    registrar("UI-CK-05 (CHECK-FIN-10) tela mostra 'Contabilidade/Bancos aguardando sua autorização'",
              "PRÓXIMA ETAPA — Contabilidade/Bancos aguardando sua autorização" in painel)
    prox = t.js("(document.querySelector('.ac-proxima')||{}).textContent") or ""
    registrar("UI-CK-06 próxima ação e botões: revisar resultado / continuar; sem 'Reprocessar fechamento' durante a pausa",
              "Financeiro concluído" in prox and t.js("!!document.querySelector('.sd-botao-revisar-fin') && !!document.querySelector('.sd-botao-continuar')")
              and not t.js("!!document.querySelector('.sd-botao-reprocessar')"), prox)
    fin_antes = pastas("financeiro")
    t.clicar("document.querySelector('.sd-botao-continuar')")
    t.esperar("!document.querySelector('.sd-camada').hidden && document.querySelector('[data-acao=autorizar-continuacao]')", 10)
    t.clicar("document.querySelector('[data-acao=autorizar-continuacao]')")
    exigiu = t.esperar("document.querySelector('.sd-caixa .cr-msg').dataset.tipo==='erro'", 5)
    registrar("UI-CK-07 continuar exige justificativa (nada executado sem ela)", exigiu and pastas("bancos") == [])
    t.digitar("document.querySelector('.sd-caixa textarea')", "Revisei o Financeiro fictício; autorizo a Contabilidade/Bancos.")
    t.clicar("document.querySelector('[data-acao=autorizar-continuacao]')")
    t.esperar("document.querySelector('.sd-caixa .cr-msg').dataset.tipo==='ok'", 20)
    time.sleep(1)
    assert cc.ocioso(servidor, ai.registro_isolado)
    t2 = rp.listar(R, sol)[-1]
    registrar("UI-CK-08 continuação usa a MESMA tentativa", t2["numero"] == tent["numero"] and t2["status"] in ("CONCLUIDA", "BLOQUEADA"), t2["status"])
    registrar("UI-CK-09 Financeiro não roda de novo", pastas("financeiro") == fin_antes)
    registrar("UI-CK-10 Bancos roda uma única vez", pastas("bancos") == ["bancos-1"] and [x["execucao"] for x in t2["execucoes"]] == ["financeiro-2", "bancos-1", "conciliacao-2"],
              (pastas("bancos"), t2["execucoes"]))


def main():
    antes = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    perfil = tempfile.mkdtemp(prefix="chrome-checkpoint-")
    porta_cdp = porta_livre()
    chrome = None
    try:
        cc.preparar_empresa(servidor, servidor.RUNTIME)
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
        assert t.esperar("window.EV && window.EV.operacao && window.EV.solDocumentos", 30), "página não carregou"
        bateria(t, cli)
    except Exception as exc:  # noqa: BLE001
        import traceback
        registrar("UI-CK-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-400:]}")
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
    registrar("UI-CK-99 ambiente operacional intocado", foto_operacional() == antes)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {c}" + ("" if ok else f"  → {d}"))
    print(f"TOTAL: {len(resultados)} · PASSARAM: {len(resultados) - falhas} · FALHARAM: {falhas} · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
