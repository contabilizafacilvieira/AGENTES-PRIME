"""Defeitos da auditoria da interface, no navegador (Chrome sem interface) contra um MOCK em memória (dados fictícios).

Não acessa a API principal (127.0.0.1:8765), CLIENTES, runtime nem registros. O mock (mock_api_escritorio.py) roda em porta
própria e devolve o mesmo contrato do servidor local. Itens: ENCERRADA/CANCELADA (1), resumo e etapas com pendências de
todas as áreas (2), falha de Bancos com etapa fiscal concluída (3), zoom sem sobrepor painéis (4) e adiantamento (6).

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_auditoria_navegador.py <pasta para capturas>
"""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
from e2e_navegador import CDP, CHROME  # noqa: E402

PORTA_MOCK, PORTA_CDP = 18793, 9363
MOCK = f"http://127.0.0.1:{PORTA_MOCK}"
resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), detalhe))


def cenario(n, adiantamento=None):
    q = f"n={n}" + ("" if adiantamento is None else f"&adiantamento={adiantamento}")
    urllib.request.urlopen(f"{MOCK}/__cenario?{q}").read()


def bateria(cdp, fotos):
    def esperar(js, s=12):
        fim = time.time() + s
        while time.time() < fim:
            try:
                if cdp.js("!!(" + js + ")"):
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        return False

    def carregar(n, adiantamento=None, w=1280, h=800):
        cenario(n, adiantamento)
        cdp.chamar("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        cdp.chamar("Page.navigate", url=MOCK + "/")
        time.sleep(0.5)
        esperar("window.EV && EV.app && document.querySelector('.gestao-nav') && EV.app.estadoDe('coordenador').solicitacao", 15)
        time.sleep(0.8)

    def acompanhar(sol):
        cdp.js(f"EV.operacao.acompanhar('{sol}')")
        esperar("document.querySelector('.ac-resumo')")
        time.sleep(0.8)

    texto = lambda sel: cdp.js(f"(document.querySelector({json.dumps(sel)})||{{}}).innerText||''")  # noqa: E731
    passos = lambda: cdp.js("JSON.stringify(Array.from(document.querySelectorAll('.ac-passo')).map(l=>[l.className.replace('ac-passo','').trim(),l.textContent]))")  # noqa: E731
    estados = lambda: json.loads(cdp.js("JSON.stringify(Object.fromEntries(['coordenador','documentos','financeiro','fiscal','bancos'].map(id=>[id,EV.app.estadoDe(id).status])))"))  # noqa: E731

    # ---------------- Item 1: ENCERRADA e CANCELADA
    carregar("enc")
    topo, st = texto("#resumo"), estados()
    cdp.js("EV.app.selecionar('coordenador')")
    time.sleep(0.5)
    ficha, quadro = texto("#ficha"), texto(".quadro-area")
    cdp.foto(fotos / "1-encerrada-coordenador.png")
    registrar("NV-01 ENCERRADA: topo, Coordenador e placa da Contabilidade sem ✓ Concluído; \"Revisão parcial encerrada\" com pendências históricas",
              "Concluído" not in topo and "CONCLUIDO" not in st.values() and "Revisão parcial encerrada" in ficha and "Pendências (0)" not in ficha
              and "✓" not in quadro, f"topo [{topo.replace(chr(10), ' ')}] · {st} · quadro [{quadro.replace(chr(10), ' ')}]")
    cdp.js("EV.app.fecharPainel()")
    acompanhar("SOL-2026-000102")
    p = json.loads(passos())
    cdp.foto(fotos / "1b-encerrada-acompanhamento.png")
    registrar("NV-02 ENCERRADA (acompanhamento): etapa com pendência (Financeiro com extrato incompleto, Bancos com incompletos) não recebe ✓",
              not any(c == "feito" and ("Financeiro" in t or "Contabilidade" in t) for c, t in p), json.dumps(p, ensure_ascii=False))
    carregar("can")
    topo, st = texto("#resumo"), estados()
    cdp.js("EV.app.selecionar('coordenador')")
    time.sleep(0.5)
    ficha = texto("#ficha")
    cdp.foto(fotos / "2-cancelada-coordenador.png")
    registrar("NV-03 CANCELADA: Coordenador \"Cancelada\"; nenhum ✓ Concluído no topo ou nos personagens",
              "Concluído" not in topo and "CONCLUIDO" not in st.values() and "Cancelada" in ficha, f"topo [{topo.replace(chr(10), ' ')}] · {st}")

    # ---------------- Item 2: resumo considera as pendências de todas as áreas
    carregar("pend")
    acompanhar("SOL-2026-000104")
    resumo, p = texto(".ac-resumo"), json.loads(passos())
    cdp.foto(fotos / "3-resumo-pendencias-financeiro.png")
    registrar("NV-04 resumo: com pendências do Financeiro (extrato incompleto, documento ilegível) não diz \"Não há pendências\" e as cita",
              "Não há pendências" not in resumo and "extrato" in resumo.lower(), resumo.replace("\n", " ")[:400])
    registrar("NV-05 etapas: Financeiro entregue com pendências não recebe ✓", not any(c == "feito" and "Financeiro" in t for c, t in p),
              json.dumps(p, ensure_ascii=False))

    # ---------------- Item 3: Bancos falhou + Contabilidade/Fiscal concluída
    carregar("misto")
    st = estados()
    cdp.js("EV.app.selecionar('bancos')")
    time.sleep(0.5)
    ficha_b = texto("#ficha")
    cdp.foto(fotos / "4a-bancos-falhou-fiscal-ok-cena.png")
    cdp.js("EV.app.fecharPainel()")
    acompanhar("SOL-2026-000105")
    resumo, p = texto(".ac-resumo"), json.loads(passos())
    cdp.foto(fotos / "4b-bancos-falhou-fiscal-ok-acompanhamento.png")
    registrar("NV-06 cena: Bancos FALHOU aparece como erro mesmo com a Contabilidade/Fiscal concluída; as duas aparecem no painel",
              st["bancos"] == "ERRO" and "Fiscal" in ficha_b and "Bancos" in ficha_b, f"{st} · {ficha_b[:300]!r}")
    registrar("NV-07 acompanhamento: falha de Bancos visível no resumo e na etapa ③ (sem ✓), mesmo com o Fiscal entregue",
              "Bancos" in resumo and "falh" in resumo.lower() and not any(c == "feito" and "Contabilidade" in t for c, t in p),
              f"{json.dumps(p, ensure_ascii=False)} · {resumo.replace(chr(10), ' ')[:300]}")

    # ---------------- Item 4: zoom não sobrepõe painéis
    sobre = """(()=>{const r=s=>{const e=document.querySelector(s);if(!e||e.hidden)return null;const b=e.getBoundingClientRect();return b.width&&b.height?b:null};
      const z=r('.zoom-escritorio');const x=(a,b)=>a&&b&&a.left<b.right-1&&b.left<a.right-1&&a.top<b.bottom-1&&b.top<a.bottom-1;
      const g=document.body.querySelector('.area.com-painel')?r('.gaveta'):null;
      return JSON.stringify({zoom:z&&[z.left,z.top,z.right,z.bottom].map(Math.round),gaveta:x(z,g),gestao:x(z,r('.gestao')),op:x(z,r('.op-painel')),
        nav:x(z,r('.gestao-nav')),visivel:!!z&&z.right<=innerWidth&&z.bottom<=innerHeight,scroll:document.documentElement.scrollWidth>innerWidth})})()"""
    for w, h in ((1000, 720), (1280, 800)):
        carregar("enc", w=w, h=h)
        cdp.js("EV.app.selecionar('bancos')")
        time.sleep(0.7)
        a = json.loads(cdp.js(sobre))
        if w == 1000:
            cdp.foto(fotos / "5-zoom-1000x720-gaveta.png")
        cdp.js("EV.app.fecharPainel()")
        cdp.js("document.querySelector('[data-pagina=solicitacoes]').click()")
        esperar("document.querySelector('.gestao-lista .gestao-item')")
        time.sleep(0.5)
        b = json.loads(cdp.js(sobre))
        if w == 1000:
            cdp.foto(fotos / "5b-zoom-1000x720-solicitacoes.png")
        registrar(f"NV-08 zoom {w}×{h}: controles visíveis, sem sobrepor o painel do Supervisor nem os painéis da esquerda; sem rolagem horizontal",
                  a["visivel"] and b["visivel"] and not any(a[k] or b[k] for k in ("gaveta", "gestao", "op", "nav", "scroll")), f"{a} · {b}")

    # ---------------- Item 6: adiantamento na tela de decisão
    carregar("adi", adiantamento="")
    acompanhar("SOL-2026-000106")
    cartoes = """JSON.stringify(Object.fromEntries(Array.from(document.querySelectorAll('.ac-decisao[data-movimento]')).map(a=>[a.dataset.movimento,{
      classe:a.className,chip:(a.querySelector('.ac-chip')||{}).textContent,texto:a.innerText,
      naturezas:Array.from((a.querySelector('.ac-acoes select')||{options:[]}).options).map(o=>o.value).filter(Boolean)}])))"""
    c = json.loads(cdp.js(cartoes))
    m1, m2, m3 = c.get("M1", {}), c.get("M2", {}), c.get("M3", {})
    cdp.js("const d=document.querySelector('.ac-decisao[data-movimento=M1] details');if(d)d.open=true;document.querySelector('.ac-decisao[data-movimento=M1]').scrollIntoView()")
    time.sleep(0.4)
    cdp.foto(fotos / "6a-decisao-sem-conta-adiantamento.png")
    registrar("NV-09 sem conta indicada: ADIANTAMENTO_* não é oferecido e o cartão explica que o Supervisor indica a conta em Empresas",
              m1.get("naturezas") and not any(n.startswith("ADIANTAMENTO_") for n in m1["naturezas"]) and "Empresas" in m1.get("texto", "")
              and "adiantamento" in m1.get("texto", "").lower(), json.dumps({k: m1.get(k) for k in ("naturezas", "chip")}, ensure_ascii=False))
    registrar("NV-10 ADIANTAMENTO_NAO_INDICADO depende de definição no cadastro; DEPENDE_AREA depende de outra área (não é decisão possível agora)",
              "cadastro" in (m2.get("chip") or "") and "agora" not in m2.get("classe", "").split() and "outra área" in (m3.get("chip") or "")
              and "agora" not in m3.get("classe", "").split() and "Decisão parcial possível agora" not in (m3.get("chip") or ""),
              json.dumps({"M2": m2.get("chip"), "M3": m3.get("chip")}, ensure_ascii=False))
    carregar("adi", adiantamento="1101")
    acompanhar("SOL-2026-000106")
    c = json.loads(cdp.js(cartoes))
    cdp.js("""(()=>{const a=document.querySelector('.ac-decisao[data-movimento=M1]');const d=a.querySelector('.ac-acoes details');d.open=true;
      const s=d.querySelector('select');s.value='ADIANTAMENTO_FORNECEDOR';s.dispatchEvent(new Event('change'));a.scrollIntoView();})()""")
    time.sleep(0.4)
    contas = json.loads(cdp.js("JSON.stringify(Array.from(document.querySelectorAll('.ac-decisao[data-movimento=M1] .ac-acoes details select')[1].options).map(o=>o.value).filter(Boolean))"))
    cdp.foto(fotos / "6b-decisao-com-conta-adiantamento.png")
    registrar("NV-11 com conta indicada: ADIANTAMENTO_FORNECEDOR oferecido e lista SOMENTE a conta indicada pelo Supervisor",
              "ADIANTAMENTO_FORNECEDOR" in c.get("M1", {}).get("naturezas", []) and contas == ["1101"], f"{c.get('M1', {}).get('naturezas')} · contas {contas}")

    # ---------------- Item 6: Empresas — o formulário de contas de adiantamento foi REMOVIDO da tela (rodada de simplificação)
    carregar("adi", adiantamento="")
    cdp.js("document.querySelector('[data-pagina=empresas]').click()")
    esperar("document.querySelector('[data-empresa=FICTICIA-AUD] [data-acao=abrir-empresa]')")
    cdp.js("document.querySelector('[data-empresa=FICTICIA-AUD] [data-acao=abrir-empresa]').click()")
    achou = esperar("document.querySelector('[data-base-resumo]') && document.querySelector('[data-config-empresa]')", 8)
    textos = []
    for k in ("bancos", "cadastro", "plano"):
        cdp.js(f"(document.querySelector('[data-config={k}]')||{{click(){{}}}}).click()")
        time.sleep(0.4)
        textos.append(cdp.js("(document.querySelector('.gestao-conteudo')||{textContent:''}).textContent"))
    cdp.foto(fotos / "7-empresas-sem-adiantamento.png")
    tudo = " ".join(textos)
    abas = cdp.js("Array.from(document.querySelectorAll('[data-config-empresa] [data-config]')).map(b=>b.textContent)")
    registrar("NV-12 Empresas: formulário de contas de adiantamento removido da tela (nenhuma área mostra a indicação de adiantamento)",
              achou and not cdp.js("!!document.querySelector('[data-contas-adiantamento]')") and "Contas de adiantamento" not in tudo, tudo[:200])
    registrar("NV-13 Empresas: configuração simplificada (Contas bancárias, Cadastro e piloto, Plano contábil atual)",
              abas == ["Contas bancárias", "Cadastro e piloto", "Plano contábil atual"], abas)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fotos = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="auditoria-ev-"))
    fotos.mkdir(parents=True, exist_ok=True)
    mock = subprocess.Popen([sys.executable, "-I", str(Path(__file__).with_name("mock_api_escritorio.py")), str(RAIZ / "ESCRITORIO-VIRTUAL"), str(PORTA_MOCK)])
    perfil = tempfile.mkdtemp(prefix="chrome-aud-ev-")
    chrome = None
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(MOCK + "/__posts", timeout=1).read()
                break
            except Exception:
                time.sleep(0.2)
        chrome = subprocess.Popen([str(CHROME), "--headless=new", f"--remote-debugging-port={PORTA_CDP}", f"--user-data-dir={perfil}",
                                   "--window-size=1280,800", "--no-first-run", "--disable-extensions", "about:blank"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                alvos = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORTA_CDP}/json/list"))
                pagina = next(a for a in alvos if a["type"] == "page")
                break
            except Exception:
                time.sleep(0.3)
        cdp = CDP(pagina["webSocketDebuggerUrl"])
        cdp.chamar("Page.enable")
        bateria(cdp, fotos)
    finally:
        if chrome:
            chrome.terminate()
        mock.terminate()
    falhas = 0
    for caso, ok, det in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {caso}" + (f"  — {det}" if det else ""))
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL · capturas em {fotos}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
