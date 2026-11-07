"""Interface (Chrome sem janela) contra a API REAL — cadastro de empresa e BASE INICIAL (resumo executivo e 4 fases), tudo pela TELA (cliques,
digitação e seleção de arquivos via CDP). Dados 100% fictícios gerados (TESTES/BASE-INICIAL/ficticios.py); cadastros, registro,
runtime e LIBERADOS temporários; o ambiente operacional não é tocado (conferido no final).

Uso: .venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_interface_base_inicial.py [pasta para capturas]
"""
import hashlib
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
TMP = Path(tempfile.mkdtemp(prefix="prime-ui-base-"))
for k, v in {"AGENTES_PRIME_RUNTIME": TMP / "runtime", "AGENTES_PRIME_REGISTRO_SOL": TMP / "registro.json",
             "AGENTES_PRIME_ORDEM_ATIVA": TMP / "ordem-ativa.json", "AGENTES_PRIME_CLAUDE": TMP / "claude-inexistente.exe",
             "LOCALAPPDATA": TMP / "localappdata", "AGENTES_PRIME_LIBERADOS": TMP / "LIBERADOS", "AGENTES_PRIME_CLIENTES": TMP / "CLIENTES"}.items():
    os.environ[k] = str(v)
(TMP / "CLIENTES").mkdir()
for p in ("API-LOCAL", "TESTES/API", "TESTES/BASE-INICIAL"):
    sys.path.insert(0, str(RAIZ / p))
import ficticios as f  # noqa: E402
import servidor  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402

FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-base-capturas-"))
FOTOS.mkdir(parents=True, exist_ok=True)
EMP = {"id": "BASE-UI-TMP", "nome": "EMPRESA BASE UI FICTICIA LTDA", "cnpj": "90.080.080/0001-25", "regime": "LUCRO PRESUMIDO (FICTICIO)"}
resultados = []


def porta_livre():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORTA_CDP = porta_livre()


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:400]))


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

    def alvo(self, expr, s=30):
        self.n += 1
        marca = f"t{self.n}"
        if not self.esperar(f"(()=>{{const e=({expr});if(e){{e.dataset.alvoTeste='{marca}';return true}}return false}})()", s):
            self.cdp.foto(FOTOS / f"falha-{marca}.png")
            raise AssertionError(f"elemento não encontrado: {expr}")
        return f"[data-alvo-teste='{marca}']"

    def clicar(self, expr, s=30):
        for _ in range(6):
            sel = self.alvo(expr, s)
            self.esperar(f"document.querySelector(\"{sel}\") && !document.querySelector(\"{sel}\").disabled", 15)
            xy = self.js(f"(()=>{{const e=document.querySelector(\"{sel}\");if(!e)return null;e.scrollIntoView({{block:'center'}});"
                         "const r=e.getBoundingClientRect();return r.width&&r.height?{x:r.x+r.width/2,y:r.y+r.height/2}:null})()")
            if xy:
                for tipo in ("mousePressed", "mouseReleased"):
                    self.cdp.chamar("Input.dispatchMouseEvent", type=tipo, button="left", clickCount=1, **xy)
                time.sleep(0.15)
                return
            time.sleep(0.5)
        self.cdp.foto(FOTOS / f"falha-clique-{self.n}.png")
        raise AssertionError(f"elemento não clicável: {expr}")

    def digitar(self, expr, texto):
        sel = self.alvo(expr)
        self.js(f"(()=>{{const e=document.querySelector(\"{sel}\");e.scrollIntoView({{block:'center'}});e.focus();e.select&&e.select()}})()")
        self.cdp.chamar("Input.insertText", text=texto)
        time.sleep(0.1)

    def texto(self, expr):
        return self.js(f"(()=>{{const e=({expr});return e?e.textContent:''}})()") or ""

    def estavel(self, s=30):
        fim, anterior = time.time() + s, None
        while time.time() < fim:
            atual = self.js("(document.querySelector('.gestao:not([hidden])')||document.body).innerHTML.length")
            if atual == anterior:
                return True
            anterior = atual
            time.sleep(0.8)
        return False

    def arquivo(self, seletor, caminho):
        raiz = self.cdp.chamar("DOM.getDocument")["root"]["nodeId"]
        no = self.cdp.chamar("DOM.querySelector", nodeId=raiz, selector=seletor)["nodeId"]
        self.cdp.chamar("DOM.setFileInputFiles", nodeId=no, files=[str(caminho)])

    def abrir_etapa(self, n):
        self.esperar(f"document.querySelector('[data-etapa-base=\"{n}\"]')")
        if not self.js(f"document.querySelector('[data-etapa-base=\"{n}\"]').open"):
            self.clicar(f"document.querySelector('[data-etapa-base=\"{n}\"] > summary')")


def q(sel):
    return f"document.querySelector({json.dumps(sel)})"


def por_texto(seletor, trecho, dentro="document"):
    return f"Array.from(({dentro}).querySelectorAll({json.dumps(seletor)})).find(e=>e.textContent.includes({json.dumps(trecho)}))"


def situacao():
    return json.loads((TMP / "CLIENTES" / EMP["id"] / "BASE-INICIAL" / "2026-10" / "base.json").read_text(encoding="utf-8"))


def fase_ativa(t):
    return t.js("(document.querySelector('[data-fase-ativa]')||{dataset:{}}).dataset.faseAtiva||''")


def bateria(t):
    contas = f.contas_ficticias(f.SALDOS_PADRAO, f.MOV_PADRAO)
    pdf = TMP / "entrada" / "balancete-setembro.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(f.pdf_balancete(EMP["nome"], EMP["cnpj"], "01/09/2026", "30/09/2026", contas, consolidado=["1", "2"], por_pagina=14,
                                    quebrar={"22"}))
    comp = [("21-CLIENTES", "1.1.2.01.000001", "CLIENTES NACIONAIS", "Itens em aberto", [("2026-09-15", "NF 88", "Cliente Ficticio", 8000.0, 0, "")]),
            ("42-ISS", "2.1.1.02.000001", "ISS A RECOLHER", "Híbrido", [("2026-09-30", "GUIA", "ISS do mês", 0, 600.0, "")])]
    book = TMP / "entrada" / "book-setembro.xlsx"
    book.write_bytes(f.book_padrao(EMP["nome"], EMP["cnpj"], "09/2026", "2026-09-30", contas, comp))
    t.esperar("window.EV && EV.app && document.querySelector('.gestao-nav')", 30)
    t.js("window.confirm=()=>true")
    # cadastro pela tela (sem empresas: Administração e o formulário já vêm abertos)
    t.clicar(q('[data-pagina="empresas"]'))
    t.esperar("document.querySelector('.gestao h1') && document.querySelector('.gestao h1').textContent==='Empresas'")
    t.estavel()
    for rotulo, valor in (("Código da empresa", EMP["id"]), ("Razão social", EMP["nome"]), ("CNPJ", EMP["cnpj"]), ("Regime tributário", EMP["regime"])):
        t.digitar(f"({por_texto('[data-cadastrar-empresa] label', rotulo)}).querySelector('input')", valor)
    t.clicar(q("[data-acao=criar-cadastro]"))
    if not t.esperar(f"document.querySelector('.gestao h1') && document.querySelector('.gestao h1').textContent==={json.dumps(EMP['nome'])}"):
        t.cdp.foto(FOTOS / "falha-cadastro.png")
        raise AssertionError("cadastro não abriu: " + t.texto(q(".gestao-mensagem")))
    t.estavel()
    resumo = t.texto(q("[data-base-resumo]"))
    registrar("V-01 empresa criada pela tela; resumo executivo da base (status, balancete, book, pendências) e UMA ação principal",
              "Não iniciada" in resumo and "Balancete anterior: pendente" in resumo and t.js("document.querySelectorAll('[data-base-resumo] .gestao-primario').length===1")
              and t.texto(q("[data-acao=continuar-base]")) == "Iniciar preparação", resumo[:200])
    t.js("(()=>{const i=document.querySelector('[data-campo=competencia-base]');i.value='2026-10';i.dispatchEvent(new Event('input'))})()")
    t.clicar(q("[data-acao=abrir-competencia]"))
    t.esperar("document.querySelector('[data-base-resumo=\"2026-10\"]')")
    t.estavel()
    # fase 1: balancete anterior
    t.clicar(q("[data-acao=continuar-base]"))
    t.esperar("document.querySelector('[data-fase-ativa=balancete]')")
    t.arquivo("[data-arquivo=balancete]", pdf)
    t.esperar("document.querySelector('[data-previa=balancete]') && document.querySelector('[data-campo=confirmar-balancete]')", 60)
    previa = t.texto(q("[data-previa=balancete]"))
    t.cdp.foto(FOTOS / "01-balancete-previa.png")
    registrar("V-02 balancete enviado pela tela: resumo primeiro ('Contas extraídas', números) e a tabela só sob demanda; período, CNPJ e "
              "abrangência consolidada em linguagem simples",
              f"Contas extraídas do balancete: {len(contas)}" in previa and "Consolidado (1, 2)" in previa and "01/09/2026 a 30/09/2026" in previa
              and not t.js("document.querySelector('[data-previa=balancete] details.gestao-sob-demanda').open"), previa[:300])
    t.clicar(q("[data-campo=confirmar-balancete]"))
    t.clicar(q("[data-acao=salvar-balancete]"))
    t.esperar("document.querySelector('[data-previa=contas] [data-campo=confirmar-contas]')", 30)
    t.estavel()
    ancoras = t.js("Array.from(document.querySelectorAll('[data-ancora]')).map(s=>s.dataset.ancora+'='+s.value)")
    resumo_plano = t.texto(q("[data-previa=contas] [data-resumo-plano]"))
    t.clicar(q("[data-campo=confirmar-contas]"))
    t.clicar(q("[data-acao=aplicar-contas]"))
    t.esperar("document.querySelector('[data-fase-ativa=book]')", 30)
    t.estavel()
    plano = json.loads((TMP / "CLIENTES" / EMP["id"] / "empresa-local.json").read_text(encoding="utf-8"))["plano"]
    registrar("V-03 tipo e grupo identificados AUTOMATICAMENTE pela hierarquia (resumo 'Plano contábil': todas classificadas, nenhuma "
              "conta para confirmar); nenhum grupo pedido ao usuário; a tela segue sozinha para a fase Book",
              len(plano) == len(contas) and not ancoras and all(c["grupo"] and c["tipo"] for c in plano)
              and f"{len(contas)}contas analisadas{len(contas)}classificadas automaticamente0precisam de confirmação" in "".join(resumo_plano.split())
              .replace("contasanalisadas", "contas analisadas").replace("classificadasautomaticamente", "classificadas automaticamente")
              .replace("precisamdeconfirmação", "precisam de confirmação")
              and fase_ativa(t) == "book", " ".join(resumo_plano.split()))
    # fase 2: book
    t.arquivo("[data-arquivo=book]", book)
    t.esperar("document.querySelector('[data-previa=book] [data-campo=confirmar-book]')", 60)
    prev_book = t.texto(q("[data-previa=book] [data-resumo-book]"))
    t.cdp.foto(FOTOS / "02-book-previa.png")
    registrar("V-04 book: resumo (composições, iguais, diferentes) e aviso de que diferença zero não conclui a conciliação",
              "composições analisadas" in prev_book and "diferentes do balancete" in prev_book and "Diferença zero não significa" in prev_book,
              prev_book[:300])
    t.clicar(q("[data-campo=confirmar-book]"))
    t.clicar(q("[data-acao=salvar-book]"))
    t.esperar("document.querySelector('[data-fase-ativa=conferencia]')", 30)
    t.estavel()
    # criar conta (Configuração › Plano contábil atual)
    t.clicar(q("[data-config=plano]"))
    t.clicar(f"{q('[data-criar-conta]')}.querySelector('summary')")
    t.js("(()=>{const s=document.querySelector('[data-campo=nova-conta-superior]');s.value='1.1.2.02';s.dispatchEvent(new Event('change'))})()")
    t.digitar(q("[data-campo=nova-conta-codigo]"), "24")
    t.digitar(q("[data-campo=nova-conta-classificacao]"), "1.1.2.02.000003")
    t.digitar(q("[data-campo=nova-conta-descricao]"), "ADIANTAMENTO DE VIAGEM")
    t.clicar(q("[data-campo=nova-conta-confirmar]"))
    t.clicar(q("[data-acao=criar-conta]"))
    t.esperar("(document.querySelector('[data-base-resumo] [data-pendencias]')||{dataset:{}}).dataset.pendencias!=='0'", 30)
    t.estavel()
    t.clicar(f"{q('[data-criar-conta]')}.querySelector('summary')")
    t.js("(()=>{const s=document.querySelector('[data-campo=nova-conta-superior]');s.value='1.1.2.02';s.dispatchEvent(new Event('change'))})()")
    t.digitar(q("[data-campo=nova-conta-codigo]"), "24")
    t.digitar(q("[data-campo=nova-conta-classificacao]"), "1.1.2.02.000009")
    t.digitar(q("[data-campo=nova-conta-descricao]"), "DUPLICADA")
    t.clicar(q("[data-campo=nova-conta-confirmar]"))
    t.clicar(q("[data-acao=criar-conta]"))
    t.esperar("document.querySelector('.gestao-mensagem').textContent.includes('já existe')", 15)
    msg = t.texto(q(".gestao-mensagem"))
    registrar("V-05 conta criada pela tela entra como pendência (saldo inicial e Domínio); código duplicado recusado com mensagem clara",
              "já existe" in msg, msg)
    # fase 3: conferência — pendências guiadas
    t.clicar(q("[data-acao=revisar-pendencias]"))
    t.esperar("document.querySelector('[data-fase-ativa=conferencia] [data-definicao-base=saldos]')", 30)
    card = t.texto(q("[data-definicao-base=saldos]"))
    registrar("V-06 cada pendência explica Problema, Impacto e O que fazer, com o nível (Bloqueio/Atenção/Informativo) e o código só em "
              "'Ver detalhes técnicos'",
              all(x in card for x in ("Problema", "Impacto", "O que fazer", "Bloqueio")) and "SALDO_INICIAL" not in t.js(
                  "(()=>{const c=document.querySelector('[data-definicao-base=saldos]').cloneNode(true);c.querySelectorAll('.gestao-tecnico').forEach(x=>x.remove());return c.textContent})()"),
              card[:250])
    sel_saldo = "[data-definicao-base=saldos]"
    t.digitar(f"{q(sel_saldo)}.querySelector('[data-campo=saldo-valor]')", "0,00")
    t.digitar(f"{q(sel_saldo)}.querySelector('[data-campo=saldo-justificativa]')", "Conta nova sem saldo em 30/09/2026.")
    t.clicar(f"{q(sel_saldo)}.querySelector('[data-campo=saldo-confirmar]')")
    t.clicar(f"{q(sel_saldo)}.querySelector('[data-acao=definir-saldo]')")
    t.esperar("document.querySelector('[data-fase-ativa]') && !document.querySelector('[data-definicao-base=saldos]')", 30)
    t.estavel()
    for _ in range(8):
        chave = t.js("(()=>{const a=Array.from(document.querySelectorAll('[data-definicao-base][data-resolvida=nao]')).find(a=>a.querySelector('[data-acao^=ciencia-]'));return a?a.dataset.definicaoBase:null})()")
        if not chave:
            break
        alvo = f"document.querySelector('[data-definicao-base={chave}][data-resolvida=nao]')"
        t.digitar(f"({alvo}).querySelector('[data-campo=justificativa]')", "Conferido no teste fictício.")
        t.clicar(f"({alvo}).querySelector('input[type=checkbox]')")
        t.clicar(f"({alvo}).querySelector('[data-acao^=ciencia-]')")
        t.esperar(f"!document.querySelector('[data-definicao-base={chave}][data-resolvida=nao]')", 30)
        t.estavel()
    t.cdp.foto(FOTOS / "03-conferencia.png")
    ciencias = sorted(situacao().get("ciencias", {}))
    registrar("V-07 pendências resolvidas pela tela: saldo zero informado e 'Marcar como conferido' com justificativa (consolidado, "
              "divergência do book)", {"consolidado", "divergencias_book"} <= set(ciencias) and situacao()["saldos_definidos"]["24"]["saldo"] == "0.00",
              ciencias)
    # fase 4: confirmação (botão só habilita com a frase exata)
    t.clicar(f"{q('[data-fase=confirmacao]')}.querySelector('button')")
    t.esperar("document.querySelector('[data-campo=frase-base]')")
    desabilitado = t.js("document.querySelector('[data-acao=confirmar-base]').disabled")
    t.digitar(q("[data-campo=frase-base]"), f"CONFIRMO BASE INICIAL {EMP['id']} 2026-10")
    t.clicar(q("[data-acao=confirmar-base]"))
    t.esperar("(document.querySelector('[data-situacao-base]')||{dataset:{}}).dataset.situacaoBase==='CONFIRMADA'", 30)
    t.estavel()
    t.cdp.foto(FOTOS / "04-base-confirmada.png")
    registrar("V-08 base CONFIRMADA na fase Confirmação (resumo do que se confirma; botão só habilita com a frase); ação principal passa a "
              "ser 'Enviar documentos do mês'",
              desabilitado and situacao()["situacao"] == "CONFIRMADA" and t.texto(q("[data-acao=enviar-documentos]")) == "Enviar documentos do mês",
              t.texto(q("[data-base-resumo]"))[:200])
    # correspondência no Domínio (Atenção; não bloqueia a base)
    if t.js("document.querySelector('[data-fluxo-base]').hidden"):
        t.clicar(q("[data-acao=ver-detalhes-base]"))
    t.clicar(f"{q('[data-fase=conferencia]')}.querySelector('button')")
    t.esperar("document.querySelector('[data-definicao-base=dominio][data-nivel=ATENCAO]')", 30)
    alvo = "document.querySelector('[data-definicao-base=dominio]')"
    t.digitar(f"({alvo}).querySelector('input:not([type=checkbox])')", "Conta criada no Domínio pelo Supervisor (teste).")
    t.clicar(f"({alvo}).querySelector('input[type=checkbox]')")
    t.clicar(f"({alvo}).querySelector('[data-acao=conta-dominio]')")
    t.esperar("document.querySelector('[data-base-resumo]') && !document.querySelector('[data-definicao-base=dominio]')", 30)
    plano = {c["codigo"]: c for c in json.loads((TMP / "CLIENTES" / EMP["id"] / "empresa-local.json").read_text(encoding="utf-8"))["plano"]}
    registrar("V-09 correspondência no Domínio confirmada pela tela (declaração do Supervisor; nada é criado no Domínio)",
              plano["24"]["dominio"] == "CONFIRMADA_NO_DOMINIO", plano["24"].get("dominio"))
    layout = t.js("(()=>{const nav=document.querySelector('.gestao-nav').getBoundingClientRect();const g=document.querySelector('.gestao').getBoundingClientRect();"
                  "return g.left>=nav.right-1&&document.documentElement.scrollWidth<=innerWidth+1})()")
    registrar("V-10 escritório virtual preservado: botões à esquerda, painel ao lado, sem rolagem horizontal", layout)


def foto_operacional():
    arqs = sorted((str(p.relative_to(RAIZ)), p.stat().st_size, p.stat().st_mtime_ns) for p in (RAIZ / "CLIENTES").rglob("*") if p.is_file())
    reg = RAIZ / "COORDENADOR-GERAL" / "controle" / "solicitacoes.json"
    return arqs, hashlib.sha256(reg.read_bytes()).hexdigest() if reg.is_file() else None, (RAIZ / "LIBERADOS").exists()


def main():
    antes = foto_operacional()
    chrome, srv = None, None
    perfil = tempfile.mkdtemp(prefix="chrome-ui-base-")
    try:
        srv = servidor.iniciar(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_port}/"
        chrome = subprocess.Popen([str(CHROME), "--headless=new", f"--remote-debugging-port={PORTA_CDP}", f"--user-data-dir={perfil}",
                                   "--window-size=1440,1000", "--no-first-run", "--disable-extensions", url],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cdp = None
        for _ in range(80):
            try:
                alvos = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORTA_CDP}/json/list", timeout=2))
                cdp = CDP(next(a for a in alvos if a.get("type") == "page" and a["url"].startswith(url))["webSocketDebuggerUrl"])
                break
            except Exception:
                time.sleep(0.25)
        assert cdp, "Chrome não respondeu na porta de depuração"
        cdp.chamar("Page.enable")
        cdp.chamar("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
        bateria(Tela(cdp))
    except Exception as exc:
        import traceback
        registrar("V-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-500:]}")
    finally:
        if chrome:
            chrome.terminate()
            try:
                chrome.wait(15)
            except subprocess.TimeoutExpired:
                chrome.kill()
        if srv:
            srv.shutdown()
            srv.server_close()
        registrar("V-11 ambiente operacional intocado (CLIENTES/, registro e LIBERADOS/ reais)", foto_operacional() == antes)
        shutil.rmtree(perfil, ignore_errors=True)
        shutil.rmtree(TMP, ignore_errors=True)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {c}  — {d}")
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
