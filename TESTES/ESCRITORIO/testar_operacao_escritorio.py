"""Escritório Virtual no MODO OPERAÇÃO (página servida pela API local), com executor SIMULADO e dados FICTÍCIOS.

Sobe um servidor de teste próprio (porta livre, runtime e registro temporários — mesma montagem da bateria da API),
abre a página no Chrome sem interface e confere que o escritório acompanha o estado real lido por GET:
Documentos sai da copa quando a etapa começa e permanece na mesa enquanto a SOL aguarda o Supervisor.
Não usa o Claude, documentos reais, o registro real nem a API que estiver em execução.

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_operacao_escritorio.py <pasta para capturas>
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
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import testar_api as ta  # noqa: E402  (runtime e registro temporários + executor simulado)
from e2e_navegador import CDP, CHROME  # noqa: E402

PORTA_CDP = 9336
resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), detalhe))


def esperar_ate(cdp, expressao, segundos):
    fim = time.time() + segundos
    while time.time() < fim:
        v = cdp.js(expressao)
        if v:
            return v
        time.sleep(0.25)
    return None


def bateria(cdp, fotos):
    estado = "(() => { const e = id => EV.app.estadoDe(id); const p = EV.app.cena._posicoes(); return JSON.stringify({ coord: e('coordenador'), docs: e('documentos'), imp: e('importacao'), p }); })()"
    ini = json.loads(cdp.js(estado))
    registrar("O-01 modo operação: sem solicitação, Coordenador livre e Documentos/Importação na copa",
              ini["coord"]["status"] == "LIVRE" and ini["p"]["documentos"]["pose"] == "sentado" and ini["p"]["importacao"]["pose"] == "sentado")

    ta.CONTROLE["modo"] = "lento"
    ta.CONTROLE["liberar"].clear()
    _, d = ta.novo_lote()
    ta.enviar(d["lote"], "d1.txt", ta.D1)
    c, r, _ = ta.pedido("POST", f"/api/lotes/{d['lote']}/iniciar", {"conferencia_humana": True})
    sol = r["sol"]
    cdp.js("document.querySelector('.op-botao').click()")   # o Supervisor abre o painel e passa a acompanhar a SOL em execução
    andando = esperar_ate(cdp, "EV.app.cena._posicoes().documentos.alvo === 'visita' || EV.app.cena._posicoes().documentos.pose === 'mesa'", 15)
    meio = json.loads(cdp.js(estado))
    registrar("O-02 etapa de Documentos em andamento: Coordenador Trabalhando e Documentos sai da copa rumo ao Coordenador",
              c == 202 and andando and meio["coord"]["status"] == "TRABALHANDO" and meio["docs"]["status"] == "TRABALHANDO"
              and meio["docs"]["local"] == "mesa", f"{sol} · {meio['p']['documentos']['alvo']}")
    esperar_ate(cdp, "EV.app.cena._posicoes().documentos.pose === 'mesa'", 15)
    cdp.js("document.querySelector('.op-painel').hidden = true")
    time.sleep(0.4)
    cdp.foto(fotos / "op-1-documentos-trabalhando.png")

    ta.CONTROLE["liberar"].set()
    ta.esperar(sol)
    ta.CONTROLE["modo"] = "ok"
    voltou = esperar_ate(cdp, "EV.app.estadoDe('documentos').status === 'CONCLUIDO' && EV.app.cena._posicoes().documentos.pose === 'mesa' && !EV.app.cena._posicoes().documentos.andando", 30)
    cdp.js("EV.app.selecionar('documentos')")
    time.sleep(0.5)
    fim = json.loads(cdp.js(estado))
    ficha = cdp.js("document.getElementById('ficha').textContent")
    registrar("O-03 etapa concluída: Documentos entrega e permanece na mesa até a conclusão da SOL",
              voltou and fim["docs"]["status"] == "CONCLUIDO" and "Concluído — relatório entregue" in ficha and "solicitação ainda não concluída" in ficha)
    registrar("O-04 Coordenador mostra o estado real da SOL (Pronto para o Financeiro → Concluído, sem Aguardando Supervisor)",
              fim["coord"]["status"] == "CONCLUIDO" and "Pronto para o Financeiro" in fim["coord"]["tarefa"], fim["coord"]["tarefa"])
    cdp.foto(fotos / "op-2-documentos-de-volta-resultado-preservado.png")

    # recarga: nada se repete
    cdp.chamar("Page.reload")
    time.sleep(2.5)
    amostras = [json.loads(cdp.js(estado))["p"] for _ in range(10) if not time.sleep(0.2)]
    registrar("O-05 recarregar não repete entregas; personagem permanece na mesa da SOL pendente",
              all(not a["documentos"]["andando"] and a["documentos"]["pose"] == "mesa" for a in amostras))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fotos = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="escritorio-op-"))
    fotos.mkdir(parents=True, exist_ok=True)
    if ta.ORDEM.exists() or ta.RECEBIDOS.exists():
        print("ABORTADO: existe ordem ativa ou CLIENTES/EMPRESA-TESTE/RECEBIDOS; nada foi feito.")
        return 1
    srv = servidor = ta.servidor.iniciar(0)
    ta.SRV, ta.PORTA = srv, srv.server_port
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    perfil = tempfile.mkdtemp(prefix="chrome-op-")
    url = f"http://127.0.0.1:{ta.PORTA}/"
    chrome = subprocess.Popen([str(CHROME), "--headless=new", f"--remote-debugging-port={PORTA_CDP}", f"--user-data-dir={perfil}",
                               "--window-size=1500,1000", "--no-first-run", "--disable-extensions", url])
    try:
        for _ in range(50):
            try:
                alvos = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORTA_CDP}/json/list"))
                pagina = next(a for a in alvos if a["type"] == "page" and a["url"].startswith(url))
                break
            except Exception:
                time.sleep(0.3)
        cdp = CDP(pagina["webSocketDebuggerUrl"])
        cdp.chamar("Page.enable")
        esperar_ate(cdp, "!!(window.EV && EV.app && EV.app.cena && document.querySelector('.op-botao'))", 10)
        time.sleep(1)
        bateria(cdp, fotos)
    finally:
        chrome.terminate()
        srv.shutdown()
        ta.ORDEM.unlink(missing_ok=True)
        ta.limpar_recebidos()          # só a pasta fictícia criada por este teste (verificado no início que não existia)
        shutil.rmtree(ta.TMP, ignore_errors=True)
    falhas = 0
    for caso, ok, det in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {caso}" + (f"  — {det}" if det else ""))
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    print(f"ordem ativa residual: {'SIM' if ta.ORDEM.exists() else 'não'} · RECEBIDOS residual: {'SIM' if ta.RECEBIDOS.exists() else 'não'}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
