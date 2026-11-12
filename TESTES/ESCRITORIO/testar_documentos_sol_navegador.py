"""Tela da solicitação: "Adicionar documento complementar" e "Reconciliar tentativa legada" (UI-DOC-01..08; cobre DOC-COMP-29).
Chrome sem janela com cliques reais (CDP). Servidor REAL em ambiente ISOLADO; empresa e documentos 100% FICTÍCIOS.

Uso: .venv/bin/python -I TESTES/ESCRITORIO/testar_documentos_sol_navegador.py [pasta para capturas]
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
AMB = ai.criar("prime-docs-sol-ui-")
os.environ["AGENTES_PRIME_DEMO_CONCILIACAO"] = str(AMB.raiz / "demonstracao-conciliacao")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import reprocessamento as rp  # noqa: E402
import cenario_complementar as cc  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-docs-sol-"))
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
    sol, _ = cli.abrir_sol([("relatorio-financeiro.xlsx", cc.relatorio_xlsx()), ("pagamentos-lote.pdf", cc.pagfor_pdf())])
    assert cc.ocioso(servidor, ai.registro_isolado)
    E = R / "execucoes" / sol
    reg_antes = json.dumps(ai.registro_isolado()["solicitacoes"][sol], sort_keys=True)
    fin_antes = sorted(p.name for p in E.glob("financeiro-*"))
    t.js(f"window.EV.operacao.acompanhar('{sol}')")
    ok = t.esperar("document.querySelector('.sd-botao-complemento')", 40)
    registrar("UI-DOC-01 tela da SOL mostra 'Adicionar documento complementar'", ok)
    time.sleep(1.5)
    registrar("UX-REAL-06 abrir a tela não executa nada (sem nova execução, sem tentativa, registro igual)",
              sorted(p.name for p in E.glob("financeiro-*")) == fin_antes and rp.listar(R, sol) == []
              and json.dumps(ai.registro_isolado()["solicitacoes"][sol], sort_keys=True) == reg_antes)
    corpo = t.js("document.querySelector('.op-painel').innerText")
    registrar("UX-REAL-05 texto antigo atualizado (documento complementar + reprocessar; nova solicitação só secundária)",
              "Abrir nova solicitação com a competência e os documentos corretos" not in corpo
              and "adicione-o como documento complementar e depois reprocesse o fechamento" in corpo, corpo[:300])
    registrar("UX-REAL-01 botão 'Reprocessar fechamento' existe no fluxo Financeiro", t.js("!!document.querySelector('.sd-botao-reprocessar')"))
    t.cdp.foto(FOTOS / "01-sol.png")
    # fluxo completo pela tela
    extrato = AMB.raiz / "extrato-ficticio-0001.pdf"
    extrato.write_bytes(cc.extrato_pdf())
    t.clicar("document.querySelector('.sd-botao-complemento')")
    t.esperar("!document.querySelector('.sd-camada').hidden")
    t.clicar(por_texto(".sd-caixa button", "Revisar"))
    exigiu = t.esperar("document.querySelector('.sd-caixa .cr-msg').textContent.includes('Selecione um arquivo')", 5)
    t.arquivo(".sd-arquivo", extrato)
    t.digitar("document.querySelector('.sd-caixa textarea')", "Extrato recebido depois (teste fictício).")
    t.clicar(por_texto(".sd-caixa button", "Revisar"))
    revisou = t.esperar("document.querySelector('.sd-dup[data-categoria=NOVO]')", 30)
    t.cdp.foto(FOTOS / "02-revisao.png")
    registrar("UI-DOC-02 revisão antes de enviar (arquivo obrigatório, motivo, duplicidade explicada)", exigiu and revisou)
    t.clicar("document.querySelector('[data-acao=enviar-complemento]')")
    feito = t.esperar("document.querySelector('.sd-classificacao')", 120)
    texto = t.js("document.querySelector('.sd-caixa').innerText")
    t.cdp.foto(FOTOS / "03-resultado.png")
    registrar("UI-DOC-03 resultado da classificação na tela (extrato reconhecido)", feito and "Extrato bancário" in texto and "Financeiro" in texto, texto[-300:])
    registrar("UI-DOC-04 (DOC-COMP-29) tela informa que nada foi reprocessado e não executa o fechamento",
              "crie uma nova tentativa" in texto and "Nada foi reprocessado" in texto
              and json.dumps(ai.registro_isolado()["solicitacoes"][sol], sort_keys=True) == reg_antes
              and sorted(p.name for p in E.glob("financeiro-*")) == ["financeiro-1"] and rp.listar(R, sol) == [])
    registrar("UI-DOC-05 tela principal sem jargão técnico ('lote complementar', JSON, SHA)",
              not any(x in texto for x in ("lote complementar", "Lote complementar", '{"', "sha256", "L-20")), texto[:200])
    t.clicar(por_texto(".sd-caixa button", "Fechar"))
    t.esperar("document.querySelector('.sd-camada').hidden")
    t.js(f"window.EV.operacao.acompanhar('{sol}')")
    t.clicar("document.querySelector('.sd-botao-reprocessar')")
    t.esperar("document.querySelector('.sd-resumo-reprocessar')", 20)
    resumo = t.js("document.querySelector('.sd-caixa').innerText")
    t.cdp.foto(FOTOS / "04-reprocessar-resumo.png")
    registrar("UX-REAL-04 complemento aparece no resumo da futura tentativa (documentos serão congelados)",
              "Os documentos disponíveis serão congelados em uma nova tentativa de reprocessamento." in resumo and "extrato-ficticio-0001.pdf" in resumo, resumo[:300])
    t.clicar(por_texto(".sd-caixa button", "Fechar"))
    t.esperar("document.querySelector('.sd-camada').hidden")
    registrar("UX-REAL-03 nenhuma tentativa sem confirmação (abrir e fechar o resumo não cria nada)", rp.listar(R, sol) == [])
    # tentativa LEGADA fictícia: execução real (retomada sem tentativa) + registro antigo PREPARADA com o mesmo motivo
    motivo = "Retomada fictícia de teste da tentativa legada."
    s, r = cli.j("POST", f"/api/solicitacoes/{sol}/retomar-rota-financeira", {"justificativa": motivo, "confirmado": True})
    assert s == 202, r
    assert cc.ocioso(servidor, ai.registro_isolado)
    pasta_t = E / "tentativas" / "0001"
    pasta_t.mkdir(parents=True)
    (pasta_t / "tentativa.json").write_text(json.dumps({
        "numero": 1, "sol": sol, "tentativa_origem": 1, "criada_em": "2020-01-01T00:00:00-03:00", "motivo": motivo, "solicitante": "Supervisor",
        "versao_codigo": "0" * 40, "tag": None, "documentos": [], "status": "PREPARADA", "pendencias": [],
        "auditoria": {"origem": "REPROCESSAMENTO_AUDITADO"}}), encoding="utf-8")
    t.js("window.EV.operacao.atualizar()")
    t.js(f"window.EV.operacao.acompanhar('{sol}')")
    ok = t.esperar("document.querySelector('.sd-botao-legada')", 40)
    registrar("UI-DOC-06 ação 'Reconciliar tentativa legada' aparece só para a tentativa antiga pendente", ok)
    t.clicar("document.querySelector('.sd-botao-legada')")
    t.esperar("document.querySelector('.sd-caixa .cr-pio')", 30)
    texto = t.js("document.querySelector('.sd-caixa').innerText")
    t.cdp.foto(FOTOS / "06-legada.png")
    frase = rp.frase_reconciliacao(sol, 1)
    t.digitar("document.querySelector('.sd-caixa textarea')", "Execução comprovada pelos resultados registrados (fictício).")
    t.digitar("document.querySelector('.sd-frase')", frase.lower())
    t.clicar("document.querySelector('[data-acao=reconciliar-legada]')")
    recusou = t.esperar("document.querySelector('.sd-caixa .cr-msg').dataset.tipo==='erro'", 10)
    t.digitar("document.querySelector('.sd-frase')", frase)
    t.clicar("document.querySelector('[data-acao=reconciliar-legada]')")
    feito = t.esperar("document.querySelector('.sd-caixa .cr-msg').textContent.includes('reconciliada como BLOQUEADA')", 20)
    tj = json.loads((pasta_t / "tentativa.json").read_text(encoding="utf-8"))
    registrar("UI-DOC-07 reconciliação pela tela: Problema/Impacto/O que será feito, frase exata exigida, estado derivado BLOQUEADA",
              all(x in texto for x in ("Problema", "Impacto", "O que será feito", "BLOQUEADA")) and recusou and feito
              and tj["status"] == "BLOQUEADA" and (pasta_t / "reconciliacao-legada.json").is_file(), (recusou, feito, tj["status"]))
    t.clicar(por_texto(".sd-caixa button", "Cancelar"))
    t.js(f"window.EV.operacao.acompanhar('{sol}')")
    t.clicar("document.querySelector('.sd-botao-reprocessar')", 40)
    t.esperar("document.querySelector('.sd-resumo-reprocessar')", 20)
    t.digitar("document.querySelector('.sd-caixa textarea')", "Reprocessar com o extrato complementar (teste fictício).")
    t.clicar("document.querySelector('[data-acao=criar-tentativa]')")
    criada = t.esperar("document.querySelector('[data-acao=iniciar-execucao]')", 30)
    t2 = rp.listar(R, sol)[-1]
    registrar("UX-REAL-02 botão usa o backend oficial (tentativa V2 auditada com manifesto efetivo; nada executado antes de iniciar)",
              criada and t2["numero"] == 2 and t2["ciclo_vida"] == "V2" and t2["status"] == "PREPARADA"
              and t2["auditoria"]["origem"] == "REPROCESSAMENTO_AUDITADO"
              and any(x["origem"] == "COMPLEMENTAR" for x in t2["manifesto_efetivo"]["documentos"]), (criada, t2.get("status")))
    t.clicar("document.querySelector('[data-acao=iniciar-execucao]')")
    time.sleep(1)
    assert cc.ocioso(servidor, ai.registro_isolado)
    t2 = rp.listar(R, sol)[-1]
    s, vc = cli.j("GET", f"/api/solicitacoes/{sol}/conciliacao-financeira")
    registrar("UX-REAL-02b 'Iniciar execução' roda a tentativa pelo fluxo oficial até a Central (lote segue bloqueado)",
              t2["status"] == "BLOQUEADA" and vc.get("disponivel") and vc["resumo"]["bloqueios_restantes"] > 0, (t2["status"], vc.get("resumo")))
    t.js("document.querySelector('.sd-camada').hidden || Array.from(document.querySelectorAll('.sd-caixa button')).find(b=>b.textContent==='Fechar').click()")
    t.js(f"window.EV.operacao.acompanhar('{sol}')")
    t.esperar("document.querySelector('.sd-botao-complemento')", 40)
    time.sleep(1)
    corpo = t.js("document.querySelector('.op-painel').innerText")
    registrar("UI-DOC-08 tentativa V2 (e a já reconciliada) não mostram a ação legada; próxima ação aponta a Central",
              not t.js("!!document.querySelector('.sd-botao-legada')") and "Central de Revisão" in corpo)


def main():
    antes = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    perfil = tempfile.mkdtemp(prefix="chrome-docs-sol-")
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
        registrar("UI-DOC-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-400:]}")
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
    registrar("UI-DOC-99 ambiente operacional intocado", foto_operacional() == antes)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASSOU' if ok else 'FALHOU'}  {c}" + ("" if ok else f"  → {d}"))
    print(f"TOTAL: {len(resultados)} · PASSARAM: {len(resultados) - falhas} · FALHARAM: {falhas} · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
