"""Central de Revisão do Supervisor pela TELA (Chrome sem janela, cliques reais via CDP) — UI-CR-01..18. Dados 100% FICTÍCIOS.

Servidor REAL em ambiente isolado (runtime, registro, CLIENTES, LIBERADOS e pasta da demonstração temporários). Exercita a
DEMONSTRAÇÃO (cards, filtros, detalhe, confirmar, rejeitar, lote, ambíguo, histórico, estado obsoleto, reinício) e o acesso pela
SOL fictícia. Ao final confere que o estado operacional não mudou.

Uso: .venv/bin/python -I TESTES/ESCRITORIO/testar_central_revisao_navegador.py [pasta para capturas]
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
AMB = ambiente_isolado.criar("prime-central-ui-")
os.environ["AGENTES_PRIME_DEMO_CONCILIACAO"] = str(AMB.raiz / "demonstracao-conciliacao")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
sys.path.insert(0, str(RAIZ / "TESTES" / "FINANCEIRO"))
import servidor  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402
import testar_decisoes_supervisor as sup  # noqa: E402  (resultado fictício do Financeiro)
from executar_gate import foto_operacional  # noqa: E402

FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-central-capturas-"))
FOTOS.mkdir(parents=True, exist_ok=True)
resultados = []
SOL_A = "SOL-2099-000201"


def preparar_sol():
    """SOL FICTÍCIA no registro/runtime temporários, com um resultado do Financeiro gerado pelo código real."""
    r = sup.conferir_com()
    AMB.registro.write_text(json.dumps({"solicitacoes": {SOL_A: {
        "sol": SOL_A, "empresa": sup.CTX_FIN["empresa"], "competencia": sup.CTX_FIN["competencia"], "estado": "AGUARDANDO_SUPERVISOR",
        "fluxo": "FINANCEIRO_BANCOS", "eventos": [], "motivos": []}}}, ensure_ascii=False), encoding="utf-8")
    pasta = AMB.runtime / "execucoes" / SOL_A / "financeiro-1"
    pasta.mkdir(parents=True)
    (pasta / "resultado.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")


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


def q(sel):
    return f"document.querySelector({json.dumps(sel)})"


def por_texto(seletor, trecho, dentro="document"):
    return f"Array.from(({dentro}).querySelectorAll({json.dumps(seletor)})).find(e=>e.textContent.includes({json.dumps(trecho)}))"


JUST = "Conferi data, valor e favorecido no comprovante fictício."


def abrir_primeiro(t, status):
    t.clicar(f"document.querySelector('.cr-item[data-status={status}] .cr-abrir')")
    assert t.esperar(f"!document.querySelector('.cr-camada').hidden && document.querySelector('.cr-detalhe').dataset.status==='{status}'"), status


def confirmar_modal(t):
    t.clicar("document.querySelector('.cr-camada-confirmar:not([hidden]) [data-acao=confirmar-envio]')")
    assert t.esperar("document.querySelector('.cr-camada-confirmar').hidden")


def bateria(t):
    t.js("window.__semRecarga = 'sim'")
    # UI-CR-01 abrir pela navegação
    t.clicar(q(".cr-entrada-demo"))
    ok = t.esperar("!document.querySelector('.cr').hidden && document.querySelector('.cr-card')")
    registrar("UI-CR-01 abre a Central (DEMONSTRAÇÃO identificada)", ok and t.js("document.querySelector('.cr-h1').textContent") ==
              "DEMONSTRAÇÃO — Conciliação Financeira" and t.js("!document.querySelector('.cr-selo-demo').hidden"))
    t.cdp.foto(FOTOS / "01-central.png")
    # UI-CR-02 cards
    registrar("UI-CR-02 cards iniciais (4 conciliados, 7 revisar, 2 ambíguos, 1 não conciliado, 10 bloqueios)", t.cards() == (4, 7, 2, 1, 10), t.cards())
    impede = t.js("document.querySelector('.cr-impede').textContent")
    registrar("UI-CR-03 bloqueios restantes com Problema / Impacto / O que fazer", "10 movimentações ainda impedem o avanço" in impede
              and all(x in impede for x in ("Problema", "Impacto", "O que fazer")), impede[:120])
    # UI-CR-04 filtros
    t.clicar(q(".cr-filtro[data-filtro=revisar]"))
    n_rev = t.js("[...document.querySelectorAll('.cr-item')].map(e=>e.dataset.status)")
    t.clicar(q(".cr-filtro[data-filtro=conciliados]"))
    n_conc = t.js("[...document.querySelectorAll('.cr-item')].map(e=>e.dataset.status)")
    t.clicar(q(".cr-filtro[data-filtro=todos]"))
    t.js("(()=>{const s=document.querySelector('.cr-natureza');s.value='ENTRADA';s.dispatchEvent(new Event('change'))})()")
    nat = t.js("[...new Set([...document.querySelectorAll('.cr-item')].map(e=>e.dataset.natureza))]")
    t.js("(()=>{const s=document.querySelector('.cr-natureza');s.value='';s.dispatchEvent(new Event('change'))})()")
    registrar("UI-CR-04 filtros (Para revisar, Conciliados, Entradas)", n_rev == ["REVISAR"] * 7 and n_conc == ["CONCILIADO"] * 4 and nat == ["ENTRADA"],
              (n_rev, n_conc, nat))
    # UI-CR-05 detalhe banco × relatório
    abrir_primeiro(t, "REVISAR")
    det = t.js("document.querySelector('.cr-detalhe').innerText")
    registrar("UI-CR-05 detalhe: banco × relatório, por que sugeriu, Problema/Impacto/O que fazer", all(x in det for x in (
        "MOVIMENTO NO BANCO", "REGISTRO NO RELATÓRIO", "POR QUE O SISTEMA SUGERIU?", "Mesmo valor", "Problema", "Impacto", "O que fazer",
        "Pontuação de referência"))
        and "Confirmar associação" in det and "Rejeitar" in det, det[:200])
    t.cdp.foto(FOTOS / "05-detalhe-provavel.png")
    # UI-CR-06 confirmar PROVAVEL (justificativa obrigatória na confirmação)
    t.clicar(por_texto(".cr-detalhe button", "Confirmar associação"))
    t.esperar("!document.querySelector('.cr-camada-confirmar').hidden")
    texto_conf = t.js("document.querySelector('.cr-confirmar').innerText")
    t.clicar("document.querySelector('[data-acao=confirmar-envio]')")
    exigiu = t.esperar("document.querySelector('.cr-confirmar .cr-msg').textContent.includes('justificativa')", 5)
    t.digitar("document.querySelector('.cr-confirmar textarea')", JUST)
    confirmar_modal(t)
    t.esperar("document.querySelector('.cr-card[data-card=revisar] .cr-card-n').textContent==='6'")
    registrar("UI-CR-06 confirmar PROVAVEL: resumo, justificativa exigida, cards 7→6 e bloqueios 10→9 sem recarregar",
              "não representa aprovação fiscal ou contábil" in texto_conf and exigiu and t.cards()[1] == 6 and t.cards()[4] == 9
              and t.js("window.__semRecarga") == "sim", (t.cards(), exigiu))
    # UI-CR-07 rejeitar PROVAVEL
    abrir_primeiro(t, "REVISAR")
    t.digitar("document.querySelector('.cr-detalhe textarea')", "Favorecido diferente do comprovante (teste fictício).")
    t.clicar(por_texto(".cr-detalhe button", "Rejeitar"))
    confirmar_modal(t)
    t.esperar("document.querySelector('.cr-card[data-card=revisar] .cr-card-n').textContent==='5'")
    t.clicar(q(".cr-filtro[data-filtro=rejeitados]"))
    rej = t.js("[...document.querySelectorAll('.cr-item')].map(e=>e.dataset.status)")
    t.clicar(q(".cr-filtro[data-filtro=todos]"))
    registrar("UI-CR-07 rejeitar PROVAVEL: sai de Para revisar, bloqueio mantido (9)", t.cards()[1] == 5 and t.cards()[4] == 9 and rej == ["REJEITADO"],
              (t.cards(), rej))
    # UI-CR-08 lote
    t.clicar(q(".cr-filtro[data-filtro=revisar]"))
    for i in range(3):
        t.clicar(f"document.querySelectorAll('.cr-item .cr-check')[{i}]")
    barra = t.js("document.querySelector('.cr-lote:not([hidden]) .cr-lote-n') && document.querySelector('.cr-lote-n').textContent")
    t.clicar(por_texto(".cr-lote button", "Confirmar selecionados"))
    t.esperar("!document.querySelector('.cr-camada-confirmar').hidden")
    resumo_lote = t.js("document.querySelector('.cr-confirmar').innerText")
    pre = t.js("document.querySelector('.cr-confirmar textarea').value")
    confirmar_modal(t)
    t.esperar("document.querySelector('.cr-card[data-card=revisar] .cr-card-n').textContent==='2'")
    registrar("UI-CR-08 lote: 3 selecionados → resumo → justificativa → confirmar (revisar 5→2, bloqueios 9→6)",
              barra == "3 selecionados" and "Você está confirmando 3 associações" in resumo_lote
              and pre == "Revisei os registros selecionados e confirmo as associações." and t.cards()[1] == 2 and t.cards()[4] == 6, (barra, t.cards()))
    t.clicar(q(".cr-filtro[data-filtro=todos]"))
    # UI-CR-09 ambíguo sem lote; escolha explícita de UM candidato
    sem_check = t.js("[...document.querySelectorAll('.cr-item[data-status=AMBIGUO], .cr-item[data-status=NAO_CONCILIADO], .cr-item[data-status=CONCILIADO]')].every(e=>!e.querySelector('.cr-check'))")
    abrir_primeiro(t, "AMBIGUO")
    desabilitado = t.js("(" + por_texto(".cr-detalhe button", "Confirmar candidato selecionado") + ").disabled")
    n_cand = t.js("document.querySelectorAll('.cr-candidato input[type=radio]').length")
    t.cdp.foto(FOTOS / "09-ambiguo.png")
    t.clicar("document.querySelectorAll('.cr-candidato input[type=radio]')[0]")
    t.digitar("document.querySelector('.cr-detalhe textarea')", "Nota fiscal do candidato 1 confere (teste fictício).")
    t.clicar(por_texto(".cr-detalhe button", "Confirmar candidato selecionado"))
    texto_amb = t.js("document.querySelector('.cr-confirmar').innerText")
    confirmar_modal(t)
    t.esperar("document.querySelector('.cr-card[data-card=ambiguos] .cr-card-n').textContent==='1'")
    registrar("UI-CR-09 ambíguo: sem lote, escolha explícita de um candidato (ambíguos 2→1, bloqueios 6→5)",
              sem_check and desabilitado and n_cand == 2 and "não escolhidos" in texto_amb and t.cards()[2] == 1 and t.cards()[4] == 5,
              (sem_check, desabilitado, n_cand, t.cards()))
    # UI-CR-10 conciliado sem botão de aprovação
    abrir_primeiro(t, "CONCILIADO")
    det = t.js("document.querySelector('.cr-detalhe').innerText")
    botoes = t.js("[...document.querySelectorAll('.cr-detalhe .cr-acoes button')].map(b=>b.textContent)")
    registrar("UI-CR-10 CONCILIADO: 'Conciliado automaticamente' e nenhum botão de aprovação", "Conciliado automaticamente" in det and botoes == [], botoes)
    t.js("document.querySelector('.cr-fechar').click()")
    # UI-CR-11 não conciliado
    abrir_primeiro(t, "NAO_CONCILIADO")
    det = t.js("document.querySelector('.cr-detalhe').innerText")
    botoes = t.js("[...document.querySelectorAll('.cr-detalhe .cr-acoes button')].map(b=>b.textContent)")
    registrar("UI-CR-11 NÃO CONCILIADO: 'Não encontramos associação segura', sem confirmar/rejeitar (só busca manual e observação)",
              "Não encontramos associação segura" in det and botoes == ["Buscar registros no relatório", "Registrar observação"], botoes)
    t.js("document.querySelector('.cr-fechar').click()")
    # UI-CR-12 estado obsoleto: outra aba decide enquanto este detalhe está aberto
    abrir_primeiro(t, "REVISAR")
    t.js("""(async()=>{const tk=document.querySelector('meta[name="prime-sessao"]').content;const h={'X-Prime-Sessao':tk,'Content-Type':'application/json'};
      const v=await (await fetch('/api/demonstracao/conciliacao-financeira',{headers:h})).json();
      const alvo=v.itens.filter(i=>i.status==='REVISAR').map(i=>i.id).find(id=>id!==document.querySelector('.cr-detalhe').dataset.id);
      await fetch('/api/demonstracao/conciliacao-financeira/'+alvo+'/decisao',{method:'POST',headers:h,body:JSON.stringify({decisao:'APROVADO',
        justificativa:'Decisão de outra aba (teste fictício).',revisao_conciliacao:v.revisao_conciliacao,revisao_decisoes:v.revisao_decisoes})});})()""")
    t.digitar("document.querySelector('.cr-detalhe textarea')", JUST)
    t.clicar(por_texto(".cr-detalhe button", "Confirmar associação"))
    confirmar_modal(t)
    obsoleto = t.esperar("document.querySelector('.cr-msg').textContent.includes('As informações mudaram')", 10)
    t.esperar("document.querySelector('.cr-card[data-card=revisar] .cr-card-n').textContent==='1'")
    registrar("UI-CR-12 estado obsoleto: recusa clara, nada gravado pela tela antiga, tela atualizada (revisar 1)", obsoleto and t.cards()[1] == 1, t.cards())
    t.cdp.foto(FOTOS / "12-obsoleto.png")
    t.js("document.querySelector('.cr-camada').hidden || document.querySelector('.cr-fechar').click()")
    # UI-CR-13 histórico
    t.clicar(q(".cr-historico summary"))
    t.esperar("document.querySelector('.cr-tabela-hist')")
    hist = t.js("document.querySelector('.cr-historico').innerText")
    linhas = t.js("document.querySelectorAll('.cr-hist-linha').length")
    registrar("UI-CR-13 histórico: data/hora, responsável, ação, quantidade, justificativa", linhas == 5 and all(x in hist for x in (
        "Confirmou associação em lote", "Rejeitou associação", "Supervisor Contábil", "Revisei os registros selecionados", "Quantidade")), (linhas, hist[:200]))
    # UI-CR-14 nenhum JSON nem identificador técnico na tela
    texto = t.js("document.querySelector('.cr').innerText")
    registrar("UI-CR-14 sem JSON técnico nem IDs na visão", not any(x in texto for x in ('{"', '":', "CF-", "DEMO-B", "DEMO-R", "DS-", "PROVAVEL", "NAO_CONCILIADO")),
              [x for x in ('{"', '":', "CF-", "DEMO-B", "PROVAVEL") if x in texto])
    # UI-CR-15 reiniciar só a demonstração
    t.clicar(por_texto(".cr-topo button", "Reiniciar demonstração"))
    t.clicar(por_texto(".cr-confirmar button", "Reiniciar"))
    t.esperar("document.querySelector('.cr-card[data-card=revisar] .cr-card-n').textContent==='7'")
    registrar("UI-CR-15 reiniciar demonstração volta ao cenário inicial", t.cards() == (4, 7, 2, 1, 10), t.cards())
    # UI-CR-16 tela menor sem rolagem horizontal
    t.cdp.chamar("Emulation.setDeviceMetricsOverride", width=700, height=900, deviceScaleFactor=1, mobile=False)
    time.sleep(0.6)
    larg = t.js("[document.querySelector('.cr').scrollWidth, document.querySelector('.cr').clientWidth]")
    t.cdp.foto(FOTOS / "16-tela-menor.png")
    t.cdp.chamar("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
    registrar("UI-CR-16 tela menor (700px) sem rolagem horizontal", larg[0] <= larg[1] + 1, larg)
    # UI-CR-17 Esc/Voltar fecham
    t.clicar(q(".cr-voltar"))
    fechou = t.esperar("document.querySelector('.cr').hidden")
    registrar("UI-CR-17 Voltar fecha a Central", fechou)
    # UI-CR-18 acesso por SOL (fictícia): não é demonstração
    t.js(f"window.EV.central.abrirSolicitacao('{SOL_A}')")
    t.esperar("!document.querySelector('.cr').hidden && document.querySelector('.cr-card')")
    sol = (t.js("document.querySelector('.cr-h1').textContent"), t.js("document.querySelector('.cr-selo-demo').hidden"),
           t.js("document.querySelector('.cr-sub').textContent"), t.cards())
    registrar("UI-CR-18 acesso pela SOL: título normal, sem selo de demonstração, dados da SOL", sol[0] == "Conciliação financeira" and sol[1]
              and SOL_A in sol[2] and sol[3][1] == 1, sol)


def main():
    antes = foto_operacional()
    preparar_sol()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    perfil = tempfile.mkdtemp(prefix="chrome-central-")
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
        assert t.esperar("document.querySelector('.cr-entrada-demo')", 30), "página não carregou"
        bateria(t)
    except Exception as exc:
        import traceback
        registrar("UI-CR-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-400:]}")
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
    registrar("UI-CR-99 ambiente operacional intocado", foto_operacional() == antes)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {c}" + ("" if ok else f"  → {d}"))
    print(f"TOTAL: {len(resultados)} · PASSARAM: {len(resultados) - falhas} · FALHARAM: {falhas} · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
