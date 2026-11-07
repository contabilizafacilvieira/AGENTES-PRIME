"""Percurso completo na interface (Chrome sem interface) contra o MOCK em memória (dados 100% fictícios da amostra A).

Confere: DP e Conciliação trabalhando no escritório; acompanhamento com etapa atual, situação de todas as áreas, propostas
contábeis (Bancos, Fiscal, DP), seção Conciliação (resumo, alcance, vigência, verificações A–E com fontes EXTERNA × INTERNA,
valores, diferença, área responsável e ação, histórico); resumo que nunca diz "sem pendências" havendo divergência/pendência/
alcance parcial/falha; retomada de etapa com justificativa e confirmação; SOL sem âncora sem botão; bloco da amostra fictícia
em Empresas; legibilidade em 1000×720 e 1280×800 sem rolagem horizontal.

Não acessa a API principal (127.0.0.1:8765), CLIENTES, runtime nem registros.

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_percurso_navegador.py <pasta para capturas>
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

PORTA_MOCK, PORTA_CDP = 18794, 9364
MOCK = f"http://127.0.0.1:{PORTA_MOCK}"
SOL = "SOL-2026-000201"
resultados = []
PROIBIDOS = ("Não há pendências", "sem pendências", "Sem pendências", "fechamento concluído", "Fechamento concluído")


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), detalhe))


def posts():
    return json.loads(urllib.request.urlopen(MOCK + "/__posts").read())


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

    def carregar(n, w=1280, h=800, amostra=None, atraso_amostra=0):
        urllib.request.urlopen(f"{MOCK}/__cenario?n={n}" + ("" if amostra is None else f"&amostra={amostra}")
                               + f"&atraso_amostra={atraso_amostra}").read()
        cdp.chamar("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        cdp.chamar("Page.navigate", url=MOCK + "/")
        time.sleep(0.5)
        esperar("window.EV && EV.app && document.querySelector('.gestao-nav') && EV.app.estadoDe('coordenador').solicitacao", 15)
        time.sleep(0.8)

    def acompanhar():
        cdp.js(f"EV.operacao.acompanhar('{SOL}')")
        esperar("document.querySelector('.ac-resumo')")
        time.sleep(0.8)

    texto = lambda sel: cdp.js(f"(document.querySelector({json.dumps(sel)})||{{}}).innerText||''")  # noqa: E731
    # acompanhamento em abas (Resumo · Lançamentos · Conciliação · Decisões · Histórico): o teste navega como o Supervisor
    aba = lambda nome: (cdp.js(f"(document.querySelector('.ac-aba[data-aba={nome}]')||{{click(){{}}}}).click()"), time.sleep(0.3))  # noqa: E731
    passos = lambda: json.loads(cdp.js("JSON.stringify(Array.from(document.querySelectorAll('.ac-passo')).map(l=>[l.className.replace('ac-passo','').trim(),l.textContent]))"))  # noqa: E731
    rolar = lambda sel: cdp.js(f"(()=>{{const e=document.querySelector({json.dumps(sel)});if(e){{e.scrollIntoView({{block:'start'}});}}return !!e}})()")  # noqa: E731
    layout = """(()=>{const p=document.querySelector('.op-painel:not([hidden])')||document.querySelector('.gestao:not([hidden])');
      const fora=p?Array.from(p.querySelectorAll('*')).filter(e=>{const b=e.getBoundingClientRect();const q=p.getBoundingClientRect();
        return b.width&&b.right>q.right+1&&getComputedStyle(e).position!=='fixed'&&!e.closest('.ac-rolagem')}).map(e=>e.tagName+'.'+e.className).slice(0,5):['sem painel'];
      return JSON.stringify({scroll:document.documentElement.scrollWidth>innerWidth,painel:p?p.scrollWidth>p.clientWidth+1:true,fora})})()"""

    # ---------------- escritório: DP e Conciliação acionados trabalham/ficam na mesa; não acionados na copa
    carregar("conc_ok")
    pos = cdp.js("EV.app.cena._posicoes()")
    st = json.loads(cdp.js("JSON.stringify(Object.fromEntries(['dp','conciliacao','importacao'].map(id=>[id,EV.app.estadoDe(id).status])))"))
    cdp.foto(fotos / "1-escritorio-dp-conciliacao-na-mesa-copa-nao-acionados.png")
    registrar("PN-01 escritório: DP e Conciliação implementados (não \"Em breve\"), na própria mesa com a SOL aberta; Importação (não acionada) na copa",
              st.get("dp") not in (None, "NAO_IMPLEMENTADO") and st.get("conciliacao") not in (None, "NAO_IMPLEMENTADO")
              and (pos.get("dp") or {}).get("pose") == "mesa" and (pos.get("conciliacao") or {}).get("pose") == "mesa"
              and (pos.get("importacao") or {}).get("pose") in ("sentado", "pe"), json.dumps({"st": st, "pos": {k: (pos.get(k) or {}).get("pose") for k in ("dp", "conciliacao", "importacao")}}))

    # ---------------- acompanhamento: Conciliação toda conferida no alcance
    acompanhar()
    resumo = texto(".ac-resumo")
    aba("conciliacao")
    conc = texto("[data-conciliacao]")
    grupos = json.loads(cdp.js("JSON.stringify(Array.from(document.querySelectorAll('[data-conciliacao] [data-grupo]')).map(g=>g.dataset.grupo))"))
    fontes = json.loads(cdp.js("JSON.stringify(Array.from(document.querySelectorAll('[data-conciliacao] [data-natureza-fonte]')).map(f=>f.dataset.naturezaFonte))"))
    registrar("PN-02 resumo com tudo CONFERIDO: SIMULAÇÃO conciliada no alcance, sem aprovação nem escrituração; nunca \"sem pendências\"/\"fechamento concluído\"",
              "conciliada no alcance" in resumo and ("não foi aprovado" in resumo or "sem aprovação" in resumo) and "escritur" in resumo
              and not any(x in resumo for x in PROIBIDOS), resumo.replace("\n", " ")[:500])
    registrar("PN-03 seção Conciliação: resumo, alcance, verificações agrupadas A–E com fontes marcadas documento externo × controle interno × sistema",
              bool(conc) and "Alcance" in conc and sorted(set(grupos)) == ["A", "B", "C", "D", "E"] and "EXTERNA" in fontes and "INTERNA" in fontes
              and "documento externo" in conc and "controle interno" in conc and "consistência do sistema" in conc, f"grupos {grupos} · fontes {sorted(set(fontes))} · {conc[:200]!r}")
    aba("resumo")
    cdp.js("document.querySelector('[data-situacao-areas]').open=true")
    areas = texto("[data-situacao-areas]")
    registrar("PN-04 situação de cada área (Financeiro, DP, Fiscal, Contabilidade com especialistas, Conciliação) com responsável",
              all(x in areas for x in ("Financeiro", "DP", "Fiscal", "Contabilidade", "Bancos", "Conciliação", "Responsável")),
              areas.replace("\n", " | ")[:400])
    aba("lancamentos")
    linhas = json.loads(cdp.js("""JSON.stringify(Array.from(document.querySelectorAll('[data-propostas] tr[data-area-proposta]')).map(r=>[r.dataset.areaProposta,r.innerText]))"""))
    cab = texto("[data-propostas] tr")
    por_area = {a: sum(1 for x, _ in linhas if x == a) for a in ("BANCOS", "FISCAL", "DP")}
    registrar("PN-05 propostas contábeis de Bancos (6), Fiscal (4) e DP (7) com débito, crédito, valor, origem e status",
              por_area == {"BANCOS": 6, "FISCAL": 4, "DP": 7} and all(k in cab for k in ("Débito", "Crédito", "Valor", "Origem", "Status"))
              and any("4101" in t and "2111" in t and "8.000,00" in t for a, t in linhas if a == "DP"), f"{por_area} · cab {cab!r}")
    aba("resumo")
    etapa = texto(".ac-etapa")
    registrar("PN-06 etapa atual e próxima ação do Supervisor presentes; ⑤ Supervisor sem ✓ antes da aprovação (nunca \"fechamento concluído\")",
              etapa.startswith("Etapa atual") and "Próxima ação" in resumo
              and not any(c == "feito" and ("Coordenador" in t or "Supervisor" in t) for c, t in passos()) and any("⑤ Supervisor" in t for _, t in passos()),
              f"{etapa} · {passos()}")
    aba("conciliacao")
    rolar("[data-conciliacao]")
    time.sleep(0.3)
    cdp.foto(fotos / "2-acompanhamento-conciliacao-conferida.png")

    # ---------------- divergências, pendências e alcance parcial (com Contabilidade/DP que falhou)
    carregar("falha_cdp")
    acompanhar()
    resumo, p = texto(".ac-resumo"), passos()
    cdp.foto(fotos / "3-acompanhamento-divergencias-alcance-parcial.png")
    aba("conciliacao")
    conc = texto("[data-conciliacao]")
    registrar("PN-07 divergências/pendências/alcance parcial/etapa falha: resumo cita tudo e nunca diz \"sem pendências\"",
              not any(x in resumo for x in PROIBIDOS) and "divergente" in resumo.lower() and "parcial" in resumo.lower()
              and "Contabilidade/DP" in resumo and "conciliada no alcance" not in resumo, resumo.replace("\n", " ")[:500])
    registrar("PN-08 Conciliação parcial: texto do alcance e o que NÃO foi executado (com motivo); passo ④ Conciliação sem ✓",
              "não executad" in conc.lower() and "confirmação de saldo do cliente GAMA não recebida" in conc
              and any("Conciliação" in t and c in ("pendente", "bloqueado") for c, t in p), f"{p} · {conc[:300]!r}")
    div = cdp.js("(()=>{const v=document.querySelector('[data-verificacao=\"CONC-C-SALDO-1101\"]');if(!v)return '';const b=v.querySelector('.ac-expandir');if(b&&b.getAttribute('aria-expanded')!=='true')b.click();return v.innerText})()")
    registrar("PN-09 verificação DIVERGENTE mostra valores confrontados, diferença, área responsável e ação (linha expandida: fontes, justificativa e ação)",
              all(x in div for x in ("Divergente", "45.455,00", "45.410,00", "45,00", "CONTABILIDADE", "Ação", "EXTERNA", "INTERNA")), div.replace("\n", " | ")[:400])
    rolar("[data-verificacao=\"CONC-C-SALDO-1101\"]")
    time.sleep(0.3)
    cdp.foto(fotos / "4-verificacao-divergente.png")

    # ---------------- retomada pela interface (aba Decisões)
    aba("decisoes")
    bt = json.loads(cdp.js("""JSON.stringify(Array.from(document.querySelectorAll('[data-retomar]')).map(b=>({etapa:b.dataset.retomar,texto:b.textContent,disabled:b.disabled})))"""))
    caixa = texto("[data-retomada]")
    registrar("PN-10 etapa FALHOU com âncora: botão \"Retomar Contabilidade/DP\" desabilitado até justificativa + confirmação; mostra o que será reexecutado",
              bt == [{"etapa": "CONTABILIDADE_DP", "texto": "Retomar Contabilidade/DP", "disabled": True}] and "reexecut" in caixa.lower()
              and "Conciliação" in caixa and "Contabilidade/DP" in caixa, f"{bt} · {caixa[:300]!r}")
    antes = len(posts())
    cdp.js("""(()=>{const c=document.querySelector('[data-retomada]');const d=c.closest('details');if(d)d.open=true;
      const j=c.querySelector('textarea');j.value='Referências do DP corrigidas (fictício)';j.dispatchEvent(new Event('input'));
      const k=c.querySelector('input[type=checkbox]');k.checked=true;k.dispatchEvent(new Event('change'));c.scrollIntoView();})()""")
    time.sleep(0.3)
    habilitado = cdp.js("!document.querySelector('[data-retomar]').disabled")
    cdp.foto(fotos / "5-botao-retomada.png")
    cdp.js("document.querySelector('[data-retomar]').click()")
    esperar("(document.querySelector('[data-retomada]')||{innerText:''}).innerText.includes('Nova tentativa')", 6)
    novos = posts()[antes:]
    registrar("PN-11 retomada envia POST .../areas/CONTABILIDADE_DP/retomar com {justificativa, confirmado:true} e mostra a resposta",
              habilitado and len(novos) == 1 and novos[0]["rota"] == f"/api/solicitacoes/{SOL}/areas/CONTABILIDADE_DP/retomar"
              and novos[0]["corpo"] == {"justificativa": "Referências do DP corrigidas (fictício)", "confirmado": True}, json.dumps(novos, ensure_ascii=False))
    carregar("sem_ancora")
    acompanhar()
    aba("decisoes")
    caixa = texto("[data-retomada]")
    registrar("PN-12 SOL sem âncora: sem botão de retomada; explica que não está disponível e orienta nova solicitação",
              not cdp.js("!!document.querySelector('[data-retomar]')") and "não está disponível" in caixa and "nova solicitação" in caixa, caixa[:300])

    # ---------------- conciliação desatualizada + histórico + retomadas anteriores
    carregar("conc_desat")
    acompanhar()
    resumo = texto(".ac-resumo")
    aba("conciliacao")
    conc = texto("[data-conciliacao]")
    rolar("[data-conciliacao]")
    time.sleep(0.3)
    cdp.foto(fotos / "6-conciliacao-desatualizada.png")
    hist = cdp.js("document.querySelectorAll('[data-conciliacao] [data-historico-conciliacao] li').length")
    registrar("PN-13 Conciliação desatualizada: aviso no resumo e na seção; histórico com as execuções; passo ④ sem ✓; personagem em PENDÊNCIA (nunca ✓)",
              "Conciliação DESATUALIZADA — algo que ela conferiu mudou depois" in conc and "desatualizada" in resumo
              and hist == 2 and not any(c == "feito" and "Conciliação" in t for c, t in passos())
              and cdp.js("EV.app.estadoDe('conciliacao').status") == "PENDENCIA", f"hist {hist} · {resumo[:300]!r}")
    registrar("PN-14 retomadas anteriores listadas (etapa, justificativa, o que reexecutou)",
              "Referências corrigidas (fictício)" in texto("[data-retomada]") or "Referências corrigidas (fictício)" in texto(".op-sol"), texto("[data-retomada]")[:300])

    # ---------------- legibilidade em 1000×720 e 1280×800
    for w, h in ((1000, 720), (1280, 800)):
        carregar("falha_cdp", w=w, h=h)
        acompanhar()
        ruins = {}
        for ampliado in (False, True):
            cdp.js(f"EV.operacao.ampliar({'true' if ampliado else 'false'})")
            time.sleep(0.4)
            for nome in ("resumo", "lancamentos", "conciliacao", "decisoes", "historico"):
                aba(nome)
                cdp.js("document.querySelectorAll('.op-sol details').forEach(d=>d.open=true);document.querySelectorAll('[data-filtro-conc=todas]').forEach(b=>b.click());"
                       "document.querySelectorAll('.ac-expandir[aria-expanded=false]').forEach(b=>b.click())")
                time.sleep(0.3)
                a = json.loads(cdp.js(layout))
                if a["scroll"] or a["painel"] or a["fora"]:
                    ruins[f"{'ampliado' if ampliado else 'normal'}/{nome}"] = a
            if w == 1000 and not ampliado:
                aba("conciliacao")
                rolar("[data-conciliacao]")
                cdp.foto(fotos / "7-acompanhamento-1000x720.png")
        cdp.js("EV.operacao.ampliar(false)")
        registrar(f"PN-15 {w}×{h}: todas as abas (painel normal e ampliado) sem rolagem horizontal da página nem conteúdo além do painel (tabelas rolam no próprio contêiner)",
                  not ruins, json.dumps(ruins)[:400])

    # ---------------- Empresas: amostra fictícia do percurso completo
    carregar("conc_ok", amostra="0", atraso_amostra=1500)        # resposta lenta de /api/amostra: reproduz a corrida do PN-16
    cdp.js("document.querySelector('[data-pagina=empresas]').click()")
    esperar("document.querySelector('[data-mais-opcoes]')", 8)
    cdp.js("document.querySelector('[data-mais-opcoes]').open=true")      # amostra fica em Administração · Mais opções
    # sincronização pela condição REAL da tela (não por tempo): situação das duas empresas já carregada de /api/amostra
    pronto_amostra = ("(()=>{const d=document.querySelector('[data-amostra]');const b=d&&d.querySelector('[data-acao=preparar-amostra]');"
                      "return !!d&&d.querySelectorAll('ul li').length>=2&&d.innerText.includes('Cenário B')&&!!b&&!b.disabled})()")
    achou = esperar(pronto_amostra, 15)
    bloco = texto("[data-amostra]")
    registrar("PN-16 Empresas: bloco da amostra fictícia com situação das duas empresas, pastas dos documentos e passo a passo",
              achou and all(x in bloco for x in ("AMOSTRA-COMPLETA-FICTICIA", "AMOSTRA-PENDENCIAS-FICTICIA", "inteiramente fictícios",
                                                 "TESTES/AMOSTRA-COMPLETA/CENARIO-A", "TESTES/AMOSTRA-COMPLETA/CENARIO-B", "TESTES/AMOSTRA-COMPLETA/LEIA-ME.md")),
              bloco.replace("\n", " | ")[:500])
    def esperar_posts(n, s=15):
        fim = time.time() + s
        while time.time() < fim and len(posts()) < n:
            time.sleep(0.1)
        return len(posts()) >= n
    antes = len(posts())
    cdp.js("window.__recusas=0;window.confirm=()=>{window.__recusas++;return false};(document.querySelector('[data-acao=preparar-amostra]')||{click(){}}).click()")
    esperar("window.__recusas===1", 5)                       # o pedido de confirmação foi mostrado e recusado
    recusado = posts()[antes:]
    cdp.js("window.confirm=()=>true;document.querySelector('[data-acao=preparar-amostra]').click()") if achou else None
    esperar_posts(antes + 1)
    esperar("(document.querySelector('[data-amostra]')||{innerText:''}).innerText.includes('PREPARADA')", 15)
    esperar(pronto_amostra, 15)
    prep = posts()[antes:]
    cdp.js("""(()=>{const r=document.querySelector('[data-amostra] input[data-recriar]');if(r){r.checked=true;r.dispatchEvent(new Event('change'));}})()""")
    esperar("(document.querySelector('[data-amostra]')||{innerText:''}).innerText.includes('preservada')", 5)
    aviso_recriar = texto("[data-amostra]")
    cdp.js("window.confirm=()=>true;(document.querySelector('[data-acao=preparar-amostra]')||{click(){}}).click()")
    esperar_posts(antes + 2)
    esperar(pronto_amostra, 15)
    recriar = posts()[antes + 1:]
    esperar("(()=>{const b=document.querySelector('[data-acao=corrigir-dp-b]');return !!b&&!b.disabled})()", 15)
    cdp.js("window.confirm=()=>true;(document.querySelector('[data-acao=corrigir-dp-b]')||{click(){}}).click()")
    esperar_posts(antes + 3)
    esperar("(document.querySelector('[data-amostra]')||{innerText:''}).innerText.includes('Retomar Contabilidade/DP')", 15)
    corr = posts()[antes + 2:]
    rolar("[data-amostra]")
    time.sleep(0.3)
    cdp.foto(fotos / "8-empresas-amostra-ficticia.png")
    registrar("PN-17 Preparar amostra: confirmação explícita (recusa não envia nada); POST {confirmado:true}; recriar avisa que a versão anterior é preservada",
              achou and not recusado and len(prep) >= 1 and prep[0]["rota"] == "/api/amostra/preparar" and prep[0]["corpo"] == {"confirmado": True}
              and "preservada" in aviso_recriar and len(recriar) >= 1 and recriar[0]["corpo"] == {"confirmado": True, "recriar": True},
              json.dumps({"recusado": recusado, "prep": prep[:1], "recriar": recriar[:1]}, ensure_ascii=False))
    registrar("PN-18 Correção das referências do DP da amostra B: POST /api/amostra/corrigir-dp-b {confirmado:true} e próximo passo exibido",
              len(corr) == 1 and corr[0]["rota"] == "/api/amostra/corrigir-dp-b" and corr[0]["corpo"] == {"confirmado": True},
              json.dumps(corr, ensure_ascii=False))
    for w, h in ((1000, 720), (1280, 800)):
        carregar("conc_ok", w=w, h=h, amostra="1")
        cdp.js("document.querySelector('[data-pagina=empresas]').click()")
        esperar("document.querySelector('[data-amostra]')", 8)
        cdp.js("document.querySelector('[data-mais-opcoes]').open=true")
        a = json.loads(cdp.js(layout))
        registrar(f"PN-19 {w}×{h}: Empresas com o bloco da amostra sem rolagem horizontal", not a["scroll"] and not a["fora"], json.dumps(a))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fotos = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="percurso-ev-"))
    fotos.mkdir(parents=True, exist_ok=True)
    mock = subprocess.Popen([sys.executable, "-I", str(Path(__file__).with_name("mock_api_escritorio.py")), str(RAIZ / "ESCRITORIO-VIRTUAL"), str(PORTA_MOCK)])
    perfil = tempfile.mkdtemp(prefix="chrome-perc-ev-")
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
        try:
            bateria(cdp, fotos)
        except Exception as e:  # interface ausente: registra como falha em vez de abortar
            registrar("PN-XX bateria interrompida", False, repr(e)[:300])
    finally:
        if chrome:
            chrome.terminate()
        mock.terminate()
    falhas = 0
    for caso, ok, det in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {caso}" + (f"  — {det}" if det and not ok else ""))
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL · capturas em {fotos}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
