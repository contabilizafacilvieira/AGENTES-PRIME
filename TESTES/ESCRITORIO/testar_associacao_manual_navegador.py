"""Associação manual assistida pela TELA da Central (UI-MANUAL-01..12). Chrome sem janela, cliques reais (CDP).
Servidor REAL em ambiente ISOLADO; usa a "DEMONSTRAÇÃO — Associação manual" (dados 100% fictícios, pasta própria temporária).

Uso: .venv/bin/python -I TESTES/ESCRITORIO/testar_associacao_manual_navegador.py [pasta para capturas]
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
AMB = ambiente_isolado.criar("prime-manual-ui-")
os.environ["AGENTES_PRIME_DEMO_CONCILIACAO"] = str(AMB.raiz / "demonstracao-conciliacao")
DEMO = AMB.raiz / "demonstracao-associacao-manual"
os.environ["AGENTES_PRIME_DEMO_MANUAL"] = str(DEMO)
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import servidor  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-manual-"))
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


def bateria(t):
    t.js("window.__semRecarga = 'sim'")
    t.clicar("document.querySelector('.cr-entrada-demo-manual')")
    t.esperar("!document.querySelector('.cr').hidden && document.querySelector('.cr-card')")
    inicial = t.cards()
    assert t.js("document.querySelector('.cr-h1').textContent") == "DEMONSTRAÇÃO — Associação manual"
    assert inicial == (1, 1, 0, 3, 4), inicial
    # UI-MANUAL-02: onde NÃO deve aparecer
    sem = []
    for valor in ("R$ 800,00", "R$ 350,00"):                                  # conciliado e provável
        abrir_item(t, valor)
        sem.append(t.js("!!document.querySelector('[data-acao=buscar-manual]')"))
        fechar_detalhe(t)
    registrar("UI-MANUAL-02 botão não aparece em CONCILIADO nem em PROVÁVEL", sem == [False, False], sem)
    # UI-MANUAL-01 / 12 / 03 / 04 / 05: caso 1×4
    abrir_item(t, "R$ 12.000,00")
    det = t.js("document.querySelector('.cr-detalhe').innerText")
    registrar("UI-MANUAL-01 'Buscar registros no relatório' aparece no NÃO CONCILIADO (com Problema/Impacto/O que fazer)",
              t.js("!!document.querySelector('[data-acao=buscar-manual]')") and "Busque registros no relatório" in det
              and "Registrar observação" in det, det[:200])
    t.clicar("document.querySelector('[data-acao=buscar-manual]')")
    t.esperar("document.querySelector('.cr-manual-item')", 20)
    texto = t.js("document.querySelector('.cr-manual').innerText").replace(" ", " ")
    t.cdp.foto(FOTOS / "01-busca-1x4.png")
    registrar("UI-MANUAL-12 abrir e buscar não toma nenhuma decisão", decisoes() == [] and t.cards() == inicial)
    registrar("UI-MANUAL-03 busca mostra registros elegíveis (sem sair da Central)", t.js("document.querySelectorAll('.cr-manual-item').length") >= 4
              and not t.js("document.querySelector('.cr').hidden"))
    registrar("UI-MANUAL-04 combinação de 4 registros aparece como sugestão para revisão", "Sugestão para revisão 1 · 4 registros" in texto
              and "Total R$ 12.000,00" in texto, texto[:300])
    desabilitado = t.js("document.querySelector('[data-acao=confirmar-manual]').disabled")
    t.clicar("document.querySelector('[data-acao=selecionar-combinacao]')")
    resumo = t.js("document.querySelector('.cr-manual-resumo').textContent").replace(" ", " ")
    registrar("UI-MANUAL-05 total e diferença aparecem; confirmar só com diferença R$ 0,00", desabilitado and "Diferença R$ 0,00" in texto
              and "Soma R$ 12.000,00" in resumo and "Diferença R$ 0,00" in resumo
              and not t.js("document.querySelector('[data-acao=confirmar-manual]').disabled"), resumo)
    # UI-MANUAL-07 / 08 / 09
    t.clicar("document.querySelector('[data-acao=confirmar-manual]')")
    t.esperar("!document.querySelector('.cr-camada-confirmar').hidden")
    modal = t.js("document.querySelector('.cr-confirmar').innerText").replace(" ", " ")
    t.cdp.foto(FOTOS / "02-confirmar-manual.png")
    t.clicar("document.querySelector('[data-acao=confirmar-envio]')")
    exigiu = t.esperar("document.querySelector('.cr-confirmar .cr-msg').textContent.includes('justificativa')", 5)
    registrar("UI-MANUAL-07 justificativa obrigatória (campo vazio com exemplo, nada gravado sem ela)", exigiu and decisoes() == []
              and t.js("document.querySelector('.cr-confirmar textarea').value") == ""
              and "Conferi os registros selecionados" in t.js("document.querySelector('.cr-confirmar textarea').placeholder")
              and "continua \"não conciliado\"" in modal and "Diferença R$ 0,00" in modal, modal[:250])
    confirmar_modal(t, JUST)
    t.esperar("document.querySelector('.cr-card[data-card=nao] .cr-card-n').textContent==='2'")
    ev = decisoes()
    registrar("UI-MANUAL-08 confirmação atualiza os cards sem recarregar (não conciliados 3→2, bloqueios 4→3)",
              t.cards() == (1, 1, 0, 2, 3) and t.js("window.__semRecarga") == "sim" and len(ev) == 1
              and ev[0]["origem"] == "ASSOCIACAO_MANUAL_ASSISTIDA" and ev[0]["classificacao_motor"] == "NAO_CONCILIADO", (t.cards(), len(ev)))
    t.clicar("document.querySelector('.cr-historico summary')")
    t.esperar("document.querySelector('.cr-tabela-hist')")
    hist = t.js("document.querySelector('.cr-historico').innerText")
    registrar("UI-MANUAL-09 histórico mostra a associação manual", "Confirmou associação manual" in hist and "Supervisor Contábil" in hist, hist[:200])
    # UI-MANUAL-06: duas combinações exigem escolha explícita
    abrir_item(t, "R$ 900,00")
    t.clicar("document.querySelector('[data-acao=buscar-manual]')")
    t.esperar("document.querySelectorAll('.cr-manual-combo').length === 2", 20)
    texto = t.js("document.querySelector('.cr-manual').innerText")
    bloqueado = t.js("document.querySelector('[data-acao=confirmar-manual]').disabled")
    t.cdp.foto(FOTOS / "03-duas-combinacoes.png")
    registrar("UI-MANUAL-06 várias combinações: nenhuma escolhida, confirmação exige seleção; data distante sinalizada",
              "O sistema não escolhe" in texto and bloqueado and "Atenção: data distante do movimento bancário." in texto
              and not t.js("Array.from(document.querySelectorAll('.cr-manual-check')).some(c=>c.checked)"), texto[:200])
    # UI-MANUAL-11: estado obsoleto (outra aba decide antes da confirmação)
    t.clicar("document.querySelectorAll('[data-acao=selecionar-combinacao]')[0]")
    t.js("""(async()=>{const tk=document.querySelector('meta[name="prime-sessao"]').content;const h={'X-Prime-Sessao':tk,'Content-Type':'application/json'};
      const v=await (await fetch('/api/demonstracao/associacao-manual',{headers:h})).json();
      const alvo=v.itens.find(i=>i.status==='REVISAR').id;
      await fetch('/api/demonstracao/associacao-manual/'+alvo+'/decisao',{method:'POST',headers:h,body:JSON.stringify({decisao:'APROVADO',
        justificativa:'Decisão de outra aba (teste fictício).',revisao_conciliacao:v.revisao_conciliacao,revisao_decisoes:v.revisao_decisoes})});})()""")
    t.clicar("document.querySelector('[data-acao=confirmar-manual]')")
    confirmar_modal(t, JUST)
    obsoleto = t.esperar("document.querySelector('.cr-msg').textContent.includes('As informações mudaram')", 10)
    registrar("UI-MANUAL-11 estado obsoleto: mensagem amigável, nada gravado pela tela antiga", obsoleto and len(decisoes()) == 2
              and decisoes()[-1]["classificacao_motor"] == "PROVAVEL")
    fechar_detalhe(t)
    # UI-MANUAL-10: revogação da associação manual
    antes = t.cards()
    abrir_item(t, "R$ 12.000,00")
    t.digitar("document.querySelector('.cr-detalhe textarea')", "Desfazendo para conferir de novo (teste fictício).")
    t.clicar("Array.from(document.querySelectorAll('.cr-detalhe button')).find(b=>b.textContent==='Desfazer decisão')")
    t.esperar("!document.querySelector('.cr-camada-confirmar').hidden")
    t.clicar("document.querySelector('.cr-camada-confirmar:not([hidden]) [data-acao=confirmar-envio]')")
    t.esperar(f"document.querySelector('.cr-card[data-card=nao] .cr-card-n').textContent==='{antes[3] + 1}'")
    ev = decisoes()
    registrar("UI-MANUAL-10 revogação: volta a bloquear, histórico preservado", t.cards()[3] == antes[3] + 1 and t.cards()[4] == antes[4] + 1
              and [e["decisao"] for e in ev] == ["APROVADO", "APROVADO", "REVOGADO"] and ev[0]["origem"] == "ASSOCIACAO_MANUAL_ASSISTIDA", (antes, t.cards()))


def main():
    antes = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    perfil = tempfile.mkdtemp(prefix="chrome-manual-")
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
        assert t.esperar("document.querySelector('.cr-entrada-demo-manual')", 30), "página não carregou"
        bateria(t)
    except Exception as exc:  # noqa: BLE001
        import traceback
        registrar("UI-MANUAL-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-400:]}")
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
    registrar("UI-MANUAL-99 ambiente operacional intocado", foto_operacional() == antes)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {c}" + ("" if ok else f"  → {d}"))
    print(f"TOTAL: {len(resultados)} · PASSARAM: {len(resultados) - falhas} · FALHARAM: {falhas} · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
