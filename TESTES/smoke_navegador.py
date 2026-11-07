"""SMOKE TEST de release pelo navegador (Chrome sem janela), em pt-BR, com dados FICTÍCIOS.

Dois modos:
  isolado     (padrão) — sobe o servidor REAL pelo comando oficial (.venv\\Scripts\\python.exe -I API-LOCAL\\servidor.py) numa
                porta própria e com estado TEMPORÁRIO (CLIENTES, registro, ordem ativa, runtime e LIBERADOS próprios); prepara a
                amostra fictícia e percorre o fluxo completo: Empresas, empresa, base inicial (resumo, 4 fases, pendências),
                configurações, menu, exclusão lógica (só a prévia), Nova solicitação com upload de documentos fictícios,
                Coordenador → áreas → resultado na tela e Solicitações recentes.
  operacional — SOMENTE LEITURA no servidor operacional já no ar (http://127.0.0.1:8765/): abre telas, painéis e menus;
                não envia documentos, não cria nem altera nada (nenhuma rota de alteração é chamada).

Ambos verificam 1920×1080 e 1366×768, erros de JavaScript e rolagem horizontal.

Uso: .venv\\Scripts\\python.exe -I TESTES\\smoke_navegador.py [isolado|operacional] [pasta para capturas]
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
from e2e_navegador import CDP, CHROME  # noqa: E402

MODO = sys.argv[1] if len(sys.argv) > 1 else "isolado"
FOTOS = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(tempfile.mkdtemp(prefix=f"smoke-{MODO}-"))
FOTOS.mkdir(parents=True, exist_ok=True)
resultados = []
COLETOR = """window.__erros=[];addEventListener('error',e=>__erros.push('erro: '+(e.message||e.type)));
addEventListener('unhandledrejection',e=>__erros.push('promessa: '+String(e.reason&&e.reason.message||e.reason)));
const _ce=console.error;console.error=(...a)=>{__erros.push('console: '+a.join(' '));_ce(...a)};"""


def livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ok(caso, cond, detalhe=""):
    resultados.append((caso, bool(cond), str(detalhe)[:300]))


class Tela:
    def __init__(self, cdp):
        self.cdp = cdp

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
            time.sleep(0.25)
        return False

    def clicar(self, expr):
        self.esperar(f"({expr})")
        self.js(f"(()=>{{const e=({expr});e.scrollIntoView({{block:'center'}});e.click()}})()")
        time.sleep(0.4)

    def estavel(self, s=20):
        fim, ant = time.time() + s, None
        while time.time() < fim:
            atual = self.js("document.body.innerHTML.length")
            if atual == ant:
                return
            ant = atual
            time.sleep(0.8)

    def sem_rolagem(self):
        return self.js("document.documentElement.scrollWidth<=innerWidth+1")


def q(sel):
    return f"document.querySelector({json.dumps(sel)})"


def abrir_chrome(url, w, h):
    porta = livre()
    perfil = tempfile.mkdtemp(prefix="chrome-smoke-")
    p = subprocess.Popen([str(CHROME), "--headless=new", f"--remote-debugging-port={porta}", f"--user-data-dir={perfil}",
                          f"--window-size={w},{h}", "--no-first-run", "--disable-extensions", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdp = None
    for _ in range(80):
        try:
            alvos = json.load(urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/list", timeout=2))
            cdp = CDP(next(a for a in alvos if a.get("type") == "page")["webSocketDebuggerUrl"])
            break
        except Exception:
            time.sleep(0.25)
    assert cdp, "Chrome não respondeu"
    cdp.chamar("Page.enable")
    cdp.chamar("Page.addScriptToEvaluateOnNewDocument", source=COLETOR)
    cdp.chamar("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
    cdp.chamar("Page.navigate", url=url)
    return p, perfil, cdp


def roteiro_empresa(t, w, h, emp, sufixo):
    """Telas de Empresas e da empresa (somente leitura): resumo, 4 fases, pendências, configurações, menu e prévia de exclusão."""
    t.clicar(q('[data-pagina="empresas"]'))
    ok(f"[{sufixo}] Empresas carrega", t.esperar("document.querySelectorAll('[data-empresa]').length>=1"))
    t.estavel()
    t.cdp.foto(FOTOS / f"{sufixo}-01-empresas.png")
    ok(f"[{sufixo}] Empresas sem 'Importar plano de contas do Domínio' nem 'Contas de adiantamento'",
       not t.js("/Importar plano de contas do Domínio|Contas de adiantamento/.test(document.querySelector('.gestao-conteudo').textContent)"))
    t.clicar(f"{q(f'[data-empresa=\"{emp}\"]')}.querySelector('.gestao-menu-botao')")
    itens = t.js(f"Array.from({q(f'[data-empresa=\"{emp}\"]')}.querySelectorAll('.gestao-menu-lista button')).map(b=>b.textContent)")
    ok(f"[{sufixo}] menu secundário da empresa", "Excluir cadastro" in (itens or []) and "Configurações" in (itens or []), itens)
    t.js("document.body.click()")
    t.clicar(f"{q(f'[data-empresa=\"{emp}\"]')}.querySelector('[data-acao=abrir-empresa]')")
    ok(f"[{sufixo}] empresa abre com o resumo compacto da base inicial", t.esperar("document.querySelector('[data-base-resumo]')")
       and t.js("document.querySelector('[data-fluxo-base]').hidden"))
    t.estavel()
    t.cdp.foto(FOTOS / f"{sufixo}-02-empresa.png")
    t.clicar(q("[data-acao=ver-detalhes-base]"))
    fases = t.js("Array.from(document.querySelectorAll('.gestao-fases li')).map(l=>l.textContent.replace(/^[^ ]+ \\d\\. /,''))") \
        if t.esperar("document.querySelectorAll('.gestao-fases li').length===4") else []
    ok(f"[{sufixo}] detalhe em 4 fases", fases == ["Balancete anterior", "Book / composições", "Conferência", "Confirmação"], fases)
    t.clicar(f"{q('[data-fase=conferencia]')}.querySelector('button')")
    t.esperar("document.querySelector('[data-fase-ativa=conferencia]')")
    ok(f"[{sufixo}] fase Conferência (pendências) abre", t.esperar("document.querySelector('[data-fase-ativa=conferencia]')"))
    if t.js("!!document.querySelector('.gestao-pendencia .gestao-tecnico')"):
        t.js("document.querySelector('.gestao-pendencia .gestao-tecnico').open=true")
        ok(f"[{sufixo}] detalhes de uma pendência abrem", t.js("document.querySelector('.gestao-pendencia .gestao-tecnico').open"))
    t.cdp.foto(FOTOS / f"{sufixo}-03-conferencia.png")
    for k, rot in (("bancos", "Contas bancárias"), ("cadastro", "Cadastro e piloto"), ("plano", "Plano contábil atual")):
        t.clicar(q(f"[data-config={k}]"))
        ok(f"[{sufixo}] área '{rot}' abre", t.esperar(f"document.querySelector('.gestao-config-painel h3') && "
                                                   f"document.querySelector('.gestao-config-painel h3').textContent==={json.dumps(rot)}"))
    t.clicar(q("[data-config-empresa] .gestao-menu-botao"))
    t.clicar(q("[data-config-empresa] [data-acao=excluir-cadastro]"))
    ok(f"[{sufixo}] fluxo de exclusão lógica presente (prévia com aviso; nada é confirmado)",
       t.esperar("document.querySelector('[data-exclusao-empresa]')") and
       "não serão apagados" in t.js("document.querySelector('[data-exclusao-empresa]').textContent"))
    t.cdp.foto(FOTOS / f"{sufixo}-04-exclusao-previa.png")
    ok(f"[{sufixo}] sem rolagem horizontal ({w}×{h})", t.sem_rolagem())


def isolado():
    tmp = Path(tempfile.mkdtemp(prefix="prime-smoke-"))
    porta = livre()
    env = dict(os.environ, AGENTES_PRIME_PORTA=str(porta), AGENTES_PRIME_CLIENTES=str(tmp / "CLIENTES"),
               AGENTES_PRIME_RUNTIME=str(tmp / "runtime"), AGENTES_PRIME_REGISTRO_SOL=str(tmp / "controle" / "solicitacoes.json"),
               AGENTES_PRIME_ORDEM_ATIVA=str(tmp / "ordem-ativa.json"), AGENTES_PRIME_LIBERADOS=str(tmp / "LIBERADOS"),
               AGENTES_PRIME_CLAUDE=str(tmp / "claude-inexistente.exe"), LOCALAPPDATA=str(tmp / "localappdata"))
    (tmp / "CLIENTES").mkdir()
    (tmp / "controle").mkdir()
    py = RAIZ / ".venv" / "Scripts" / "python.exe"
    srv = subprocess.Popen([str(py), "-I", "API-LOCAL/servidor.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{porta}/"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(url, timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        import amostra_ficticia as am
        docs = tmp / "docs"
        docs.mkdir()
        for nome, conteudo in am.documentos("A").items():
            (docs / nome).write_bytes(conteudo)
        for (w, h) in ((1920, 1080), (1366, 768)):
            chrome, perfil, cdp = abrir_chrome(url, w, h)
            t = Tela(cdp)
            try:
                ok(f"[{w}x{h}] Escritório Virtual carrega", t.esperar("window.EV && EV.app && document.querySelector('.gestao-nav')", 40))
                t.estavel()
                t.cdp.foto(FOTOS / f"{w}x{h}-00-escritorio.png")
                if w == 1920:          # prepara a amostra fictícia pela própria tela (Administração)
                    t.js("window.confirm=()=>true")
                    t.clicar(q('[data-pagina="empresas"]'))
                    t.esperar("document.querySelector('[data-mais-opcoes]')")
                    t.js("document.querySelector('[data-mais-opcoes]').open=true")
                    t.clicar(q("[data-acao=preparar-amostra]"))
                    ok("amostra fictícia preparada pela tela", t.esperar("document.querySelector('[data-amostra]').innerText.includes('PREPARADA')", 60))
                    t.clicar(q('[data-pagina="escritorio"]'))     # recolhe o painel; a lista de empresas é recarregada a seguir
                    t.esperar("document.querySelector('.gestao').hidden")
                roteiro_empresa(t, w, h, am.EMPRESAS["A"]["id"], f"{w}x{h}")
                if w == 1920:          # Nova solicitação com upload fictício → Coordenador → áreas → resultado
                    t.clicar(q(".op-botao"))
                    t.esperar("!document.querySelector('.op-painel').hidden")
                    t.esperar(f"Array.from(document.querySelectorAll('.op-form select')[0].options).some(o=>o.value==='{am.EMPRESAS['A']['id']}')")
                    t.js(f"(()=>{{const s=document.querySelectorAll('.op-form select')[0];s.value='{am.EMPRESAS['A']['id']}';s.dispatchEvent(new Event('change'))}})()")
                    t.js("(()=>{const i=document.querySelector('.op-form input[type=month]');i.value='2026-10';i.dispatchEvent(new Event('input'));i.dispatchEvent(new Event('change'))})()")
                    raiz = cdp.chamar("DOM.getDocument")["root"]["nodeId"]
                    no = cdp.chamar("DOM.querySelector", nodeId=raiz, selector=".op-form input[type=file]")["nodeId"]
                    cdp.chamar("DOM.setFileInputFiles", nodeId=no, files=[str(p) for p in sorted(docs.iterdir())])
                    ok("Nova solicitação: documentos fictícios selecionados e resumo 'Você está iniciando'",
                       t.esperar(f"document.querySelectorAll('.op-arquivos li').length==={len(list(docs.iterdir()))}")
                       and "Outubro/2026" in t.js("document.querySelector('[data-resumo-envio]').innerText"))
                    t.js("(()=>{const x=document.querySelector('.op-form textarea');x.value='Smoke test com documentos fictícios.';x.dispatchEvent(new Event('input'))})()")
                    t.js("(()=>{const c=document.querySelector('.op-form .op-confirma input');if(!c.checked)c.click()})()")
                    t.cdp.foto(FOTOS / "1920-05-nova-solicitacao.png")
                    t.clicar(q(".op-iniciar"))
                    ok("Coordenador recebe a solicitação (acompanhamento aberto)", t.esperar("document.querySelector('.ac-sol') && /SOL-\\d{4}-\\d{6}/.test(document.querySelector('.ac-sol').textContent)", 120))
                    sol = t.js("document.querySelector('.ac-sol').textContent")
                    fim = time.time() + 600
                    estado = None
                    while time.time() < fim:
                        estado = json.loads(urllib.request.urlopen(urllib.request.Request(
                            url + f"api/solicitacoes/{sol}", headers={"X-Prime-Sessao": t.js("document.querySelector('meta[name=prime-sessao]').content")})).read())
                        if not str(estado.get("estado", "")).endswith("_EM_ANDAMENTO") and estado.get("execucao", {}).get("status") != "EM_EXECUCAO":
                            break
                        time.sleep(2)
                    areas = sorted((estado.get("tarefas_areas") or {}).keys())
                    ok("fluxo de agentes esperado (Documentos → áreas → Contabilidade → Conciliação) e SOL aguarda o Supervisor",
                       estado.get("estado") == "AGUARDANDO_SUPERVISOR" and {"FINANCEIRO", "FISCAL", "DP", "CONCILIACAO"} <= set(areas), f"{sol} {estado.get('estado')} {areas}")
                    t.estavel()
                    ok("resultado volta para a tela (acompanhamento com estado final)", t.esperar("document.querySelector('.op-sol') && /Aguardando/.test(document.querySelector('.op-sol').innerText)", 60))
                    t.cdp.foto(FOTOS / "1920-06-resultado.png")
                    t.clicar(q(".op-painel .fechar"))
                    t.clicar(q(".op-botao"))
                    ok("Solicitações recentes lista a solicitação", t.esperar(f"Array.from(document.querySelectorAll('.op-recente')).some(b=>b.textContent.includes('{sol}'))", 30))
                    t.clicar(q(".op-painel .fechar"))
                erros = t.js("window.__erros||[]")
                ok(f"[{w}x{h}] nenhum erro crítico de JavaScript", not erros, erros[:3])
            finally:
                chrome.terminate()
                shutil.rmtree(perfil, ignore_errors=True)
    finally:
        srv.terminate()
        try:
            srv.wait(15)
        except subprocess.TimeoutExpired:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def operacional():
    url = "http://127.0.0.1:8765/"
    empresas = None
    for (w, h) in ((1920, 1080), (1366, 768)):
        chrome, perfil, cdp = abrir_chrome(url, w, h)
        t = Tela(cdp)
        try:
            ok(f"[op {w}x{h}] Escritório Virtual operacional carrega", t.esperar("window.EV && EV.app && document.querySelector('.gestao-nav')", 40))
            t.js("window.confirm=()=>false")           # qualquer confirmação acidental é recusada (somente leitura)
            t.estavel()
            t.cdp.foto(FOTOS / f"op-{w}x{h}-00-escritorio.png")
            t.clicar(q('[data-pagina="empresas"]'))
            t.esperar("document.querySelectorAll('[data-empresa]').length>=1")
            empresas = t.js("Array.from(document.querySelectorAll('[data-empresa]')).map(e=>e.dataset.empresa)")
            alvo = next((e for e in empresas if "FICTICIA" in e), None)
            if alvo:
                roteiro_empresa(t, w, h, alvo, f"op-{w}x{h}")
            t.clicar(q('[data-pagina="solicitacoes"]'))
            ok(f"[op {w}x{h}] Solicitações carrega", t.esperar("document.querySelector('.gestao-filtros input[type=search]')"))
            t.clicar(q(".op-botao"))
            ok(f"[op {w}x{h}] Nova solicitação abre (sem enviar nada)", t.esperar("!document.querySelector('.op-painel').hidden && document.querySelector('[data-resumo-envio]')"))
            t.cdp.foto(FOTOS / f"op-{w}x{h}-05-nova-solicitacao.png")
            t.clicar(q(".op-painel .fechar"))
            ok(f"[op {w}x{h}] sem rolagem horizontal", t.sem_rolagem())
            erros = t.js("window.__erros||[]")
            ok(f"[op {w}x{h}] nenhum erro crítico de JavaScript", not erros, erros[:3])
        finally:
            chrome.terminate()
            shutil.rmtree(perfil, ignore_errors=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        isolado() if MODO == "isolado" else operacional()
    except Exception as exc:
        import traceback
        ok("smoke interrompido", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-300:]}")
    falhas = 0
    for c, passou, d in resultados:
        falhas += not passou
        print(f"{'PASS' if passou else 'FAIL'}  {c}" + (f"  — {d}" if d and not passou else ""))
    print(f"\nSMOKE {MODO.upper()}: {len(resultados)} verificações · {len(resultados) - falhas} PASS · {falhas} FAIL · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
