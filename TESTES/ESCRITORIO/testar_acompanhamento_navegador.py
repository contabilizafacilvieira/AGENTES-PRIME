"""Acompanhamento em abas e APROVAÇÃO do fechamento (SIMULAÇÃO) no navegador, contra o MOCK em memória (dados 100% fictícios).

Confere: abas Resumo · Lançamentos · Conciliação · Decisões · Histórico (teclado e estado preservado na atualização); faixa de
status por cor (pronto para aprovar, impedimentos, aprovado, encerrada/cancelada); indicadores com os números do detalhe;
tabela de lançamentos com filtros e totais; Conciliação filtrada (divergentes e pendentes) com linha expansível; aprovação com
frase exata + justificativa + ciência da SIMULAÇÃO (POST com o contrato do servidor) e revogação; escritório e Solicitações
com "Fechamento aprovado (SIMULAÇÃO)" e participantes liberados; "Ampliar painel" sem esconder o escritório nem criar rolagem
horizontal (1000×720 e 1280×800). Capturas para a conferência visual.

Não acessa a API principal (127.0.0.1:8765), CLIENTES, runtime nem registros.

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_acompanhamento_navegador.py <pasta para capturas>
"""
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
from e2e_navegador import CDP, CHROME  # noqa: E402

PORTA_MOCK, PORTA_CDP = 18795, 9365
MOCK = f"http://127.0.0.1:{PORTA_MOCK}"
SOL = "SOL-2026-000201"
FRASE = f"APROVO FECHAMENTO {SOL}"
resultados = []
PROIBIDOS = ("Não há pendências", "sem pendências", "Sem pendências", "fechamento concluído", "Fechamento concluído")
# toda menção a escrituração/liberação precisa ser negada ("nada … escriturado nem liberado")
NEGADAS = re.compile(r"(nada|não|nem)( foi| é)? (escriturad[oa]s?|liberad[oa]s?)( nem (escriturad[oa]s?|liberad[oa]s?))?", re.I)


def afirma_escrituracao(texto):
    return bool(re.search(r"escriturad|liberad", NEGADAS.sub("", texto), re.I))


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

    def carregar(n, w=1280, h=800):
        urllib.request.urlopen(f"{MOCK}/__cenario?n={n}").read()
        cdp.chamar("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        cdp.chamar("Page.navigate", url=MOCK + "/")
        time.sleep(0.5)
        esperar("window.EV && EV.app && document.querySelector('.gestao-nav') && EV.app.estadoDe('coordenador').solicitacao", 15)
        time.sleep(0.8)

    def acompanhar(sol=SOL):
        cdp.js(f"EV.operacao.acompanhar('{sol}')")
        esperar("document.querySelector('.ac-resumo')")
        time.sleep(0.8)

    texto = lambda sel: cdp.js(f"(document.querySelector({json.dumps(sel)})||{{}}).innerText||''")  # noqa: E731
    aba = lambda nome: (cdp.js(f"document.querySelector('.ac-aba[data-aba={nome}]').click()"), time.sleep(0.3))  # noqa: E731
    topo = lambda: cdp.js("document.querySelector('.op-painel').scrollTop=0")  # noqa: E731
    jsj = lambda js: json.loads(cdp.js(f"JSON.stringify({js})"))  # noqa: E731
    layout = """(()=>{const p=document.querySelector('.op-painel');const q=p.getBoundingClientRect();
      const fora=Array.from(p.querySelectorAll('*')).filter(e=>{const b=e.getBoundingClientRect();return b.width&&b.right>q.right+1&&!e.closest('.ac-rolagem')}).length;
      const palco=document.querySelector('.palco').getBoundingClientRect();
      return {scroll:document.documentElement.scrollWidth>innerWidth,fora,painel:Math.round(q.width),palcoEsq:Math.round(palco.left),painelDir:Math.round(q.right),
              palco:Math.round(palco.width),visivel:getComputedStyle(document.querySelector('.palco')).visibility}})()"""

    # ---------------- abas e Resumo pronto para aprovar (tudo conferido)
    carregar("conc_ok")
    acompanhar()
    abas = jsj("Array.from(document.querySelectorAll('.ac-aba')).map(b=>[b.dataset.aba,b.getAttribute('aria-selected'),b.getAttribute('role')])")
    paineis = jsj("Array.from(document.querySelectorAll('.op-sol [role=tabpanel]')).filter(p=>!p.hidden).map(p=>p.id)")
    registrar("AB-01 cinco abas na ordem (Resumo, Lançamentos, Conciliação, Decisões, Histórico) com papéis ARIA; Resumo aberto por padrão",
              [a[0] for a in abas] == ["resumo", "lancamentos", "conciliacao", "decisoes", "historico"] and abas[0][1] == "true"
              and all(a[2] == "tab" for a in abas) and paineis == ["ac-painel-resumo"], json.dumps({"abas": abas, "paineis": paineis}))
    cdp.js("document.querySelector('.ac-aba[data-aba=resumo]').focus();document.querySelector('.ac-abas').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))")
    time.sleep(0.2)
    teclado = jsj("[document.activeElement.dataset.aba, !document.getElementById('ac-painel-lancamentos').hidden]")
    aba("resumo")
    registrar("AB-02 teclado: seta para a direita leva à próxima aba (foco e painel)", teclado == ["lancamentos", True], json.dumps(teclado))
    faixa = texto(".ac-faixa")
    ind = jsj("Object.fromEntries(Array.from(document.querySelectorAll('.ac-ind')).map(c=>[c.dataset.indicador,c.querySelector('.ac-ind-valor').innerText.replace(/\\s+/g,'')]))")
    btn = jsj("(()=>{const b=document.querySelector('[data-acao-aprovacao=abrir-aprovar]');return b?{d:b.disabled,v:b.offsetParent!==null}:null})()")
    resumo = texto(".ac-resumo")
    registrar("AB-03 faixa VERDE \"Tudo conferido — pronto para a sua aprovação\" e botão \"Aprovar fechamento\" habilitado e visível no Resumo",
              cdp.js("document.querySelector('.ac-faixa').dataset.faixa") == "verde" and "Tudo conferido — pronto para a sua aprovação" in faixa
              and btn == {"d": False, "v": True} and not any(x in resumo for x in PROIBIDOS), f"{faixa!r} · {btn}")
    registrar("AB-04 indicadores com os números reais do detalhe: 4 movimentos · 17/0 lançamentos · Conciliação 7/0/0 · 0 pendências abertas",
              ind == {"movimentos": "4", "lancamentos": "17/0", "conciliacao": "7/0/0", "pendencias": "0"}, json.dumps(ind, ensure_ascii=False))
    topo()
    cdp.foto(fotos / "depois-1-resumo-pronto-para-aprovar.png")

    # ---------------- Lançamentos: tabela, filtros e totais por origem
    aba("lancamentos")
    lanc = jsj("""(()=>{const rows=()=>Array.from(document.querySelectorAll('[data-propostas] tr[data-area-proposta]')).filter(r=>!r.hidden);
      const sel=document.querySelectorAll('[data-propostas] .ac-filtro select');const r={todas:rows().length,
        cab:Array.from(document.querySelectorAll('[data-propostas] thead th')).map(t=>t.textContent),
        totais:Array.from(document.querySelectorAll('[data-total-origem]')).map(t=>t.innerText.replace(/\\n/g,' '))};
      sel[0].value='DP';sel[0].dispatchEvent(new Event('change'));r.dp=rows().length;r.dpTexto=rows().map(x=>x.innerText).join(' ');
      sel[1].value='INCOMPLETO';sel[1].dispatchEvent(new Event('change'));r.dpInc=rows().length;
      r.vazio=!document.querySelector('[data-propostas] > p.nd').hidden;r.contagem=document.querySelector('.ac-barra-n').textContent;
      sel[0].value='';sel[0].dispatchEvent(new Event('change'));sel[1].value='';sel[1].dispatchEvent(new Event('change'));r.depois=rows().length;return r})()""")
    registrar("AB-05 Lançamentos em TABELA (origem, data/comp., débito, crédito, valor, status, origem/regra) com totais por origem e filtros por origem e status",
              lanc["todas"] == 17 and lanc["cab"] == ["Origem", "Data / comp.", "Débito", "Crédito", "Valor", "Status", "Origem / regra"]
              and len(lanc["totais"]) == 3 and "26.545,00" in lanc["totais"][0] and lanc["dp"] == 7 and "4101" in lanc["dpTexto"] and "8.000,00" in lanc["dpTexto"]
              and lanc["dpInc"] == 0 and lanc["vazio"] and lanc["depois"] == 17, json.dumps(lanc, ensure_ascii=False)[:400])
    topo()
    cdp.foto(fotos / "depois-4-aba-lancamentos.png")

    # ---------------- aprovação: frase exata + justificativa + ciência; POST com o contrato do servidor
    aba("resumo")
    cdp.js("document.querySelector('[data-acao-aprovacao=abrir-aprovar]').click()")
    time.sleep(0.3)
    estados_btn = []
    passos = [("frase errada", "APROVO FECHAMENTO", "Conferi tudo (fictício).", True), ("sem ciência", FRASE, "Conferi tudo (fictício).", False),
              ("justificativa curta", FRASE, "ok", True), ("tudo válido", FRASE, "Conferi lançamentos e conciliação (fictício).", True)]
    for nome, frase, just, ciente in passos:
        estados_btn.append((nome, cdp.js(f"""(()=>{{const c=document.querySelector('.ac-aprovacao');const f=c.querySelector('input[type=text]');f.value={json.dumps(frase)};
          f.dispatchEvent(new Event('input'));const j=c.querySelector('textarea');j.value={json.dumps(just)};j.dispatchEvent(new Event('input'));
          const k=c.querySelector('input[type=checkbox]');if(k.checked!=={json.dumps(ciente)})k.click();
          return document.querySelector('[data-acao-aprovacao=aprovar]').disabled}})()""")))
    guia = texto(".ac-aprovacao")
    cdp.js("document.querySelector('.ac-aprovacao').scrollIntoView({block:'center'})")
    time.sleep(0.2)
    cdp.foto(fotos / "depois-1b-confirmacao-da-aprovacao.png")
    registrar("AB-06 confirmação mostra a frase a digitar e só habilita \"Confirmar aprovação\" com frase exata, justificativa (5–500) e ciência da SIMULAÇÃO",
              FRASE in guia and "Entendo que é SIMULAÇÃO: nada é escriturado; o TXT (empresa fictícia) só serve para importação MANUAL no Domínio, ainda não validada" in guia
              and [d for _, d in estados_btn] == [True, True, True, False], json.dumps(estados_btn, ensure_ascii=False))
    antes = len(posts())
    cdp.js("document.querySelector('[data-acao-aprovacao=aprovar]').click()")
    esperar("document.querySelector('.ac-faixa') && document.querySelector('.ac-faixa').dataset.faixa==='aprovado'", 8)
    time.sleep(0.6)
    novos = posts()[antes:]
    registrar("AB-07 aprovação envia POST /api/solicitacoes/<SOL>/aprovacao {acao:'aprovar', frase, justificativa, confirmado:true}",
              len(novos) == 1 and novos[0]["rota"] == f"/api/solicitacoes/{SOL}/aprovacao"
              and novos[0]["corpo"] == {"acao": "aprovar", "frase": FRASE, "justificativa": "Conferi lançamentos e conciliação (fictício).", "confirmado": True},
              json.dumps(novos, ensure_ascii=False))
    faixa = texto(".ac-faixa")
    selo = texto(".ac-cab .ac-selo")
    passos5 = jsj("Array.from(document.querySelectorAll('.ac-passo')).map(l=>[l.className.replace('ac-passo','').trim(),l.textContent])")
    resumo = texto(".ac-resumo")
    registrar("AB-08 aprovado: faixa VERDE ESCURA \"Fechamento aprovado em <data> (SIMULAÇÃO — <situação efetiva do TXT>; nada escriturado)\" "
              "(sem situação de TXT informada = nenhum arquivo TXT entregue), selo e ⑤ Supervisor ✓; botão Revogar",
              re.search(r"Fechamento aprovado em \d\d/\d\d/\d{4}.*\(SIMULAÇÃO — nenhum arquivo TXT entregue; nada escriturado\)", faixa) is not None
              and selo == "Fechamento aprovado (SIMULAÇÃO)" and passos5[-1][0] == "feito" and "⑤ Supervisor" in passos5[-1][1]
              and cdp.js("!!document.querySelector('[data-acao-aprovacao=abrir-revogar]')") and not afirma_escrituracao(resumo),
              f"{faixa!r} · {selo!r} · {passos5[-1]}")
    est = jsj("Object.fromEntries(['coordenador','documentos','financeiro','dp','fiscal','bancos','conciliacao'].map(id=>{const e=EV.app.estadoDe(id);return [id,[e.status,e.local||'',e.tarefa||'']]}))")
    registrar("AB-09 escritório: Coordenador \"Fechamento aprovado (SIMULAÇÃO)\"; participantes liberados (copa), ninguém preso ao posto; sem afirmar escrituração",
              "Fechamento aprovado (SIMULAÇÃO)" in est["coordenador"][2] and all(est[k][1] == "copa" for k in ("documentos", "financeiro", "dp", "fiscal", "bancos", "conciliacao"))
              and not any(afirma_escrituracao(v[2]) for v in est.values()), json.dumps(est, ensure_ascii=False)[:500])
    topo()
    cdp.foto(fotos / "depois-3-aprovado.png")
    aba("historico")
    hist = texto("[data-historico-aprovacoes]") + " " + texto(".ac-linha-tempo")
    registrar("AB-10 Histórico registra a aprovação (data, justificativa) e o evento da SOL", "APROVADO (SIMULAÇÃO)" in hist and "Conferi lançamentos" in hist
              and "APROVOU o fechamento" in hist, hist[:300])
    cdp.foto(fotos / "depois-6-aba-historico-aprovacao.png")
    # Solicitações: rótulo do estado fechado
    cdp.js("document.querySelector('[data-pagina=solicitacoes]').click()")
    esperar("document.querySelector('.gestao-lista .gestao-item')", 8)
    item = texto(".gestao-lista .gestao-item")
    registrar("AB-11 Solicitações: \"Fechamento aprovado (SIMULAÇÃO)\" (estado fechado) e nunca \"escriturado\"/\"liberado\" como afirmação",
              "Fechamento aprovado (SIMULAÇÃO)" in item and not afirma_escrituracao(item)
              and cdp.js("document.querySelector('.gestao-lista .gestao-item').classList.contains('fechada')"), item.replace("\n", " | ")[:300])
    # revogação: justificativa + confirmação; volta a aguardar o Supervisor; histórico preserva a aprovação revogada
    acompanhar()
    aba("resumo")
    cdp.js("document.querySelector('[data-acao-aprovacao=abrir-revogar]').click()")
    time.sleep(0.2)
    desab = cdp.js("""(()=>{const c=document.querySelector('.ac-aprovacao');const j=c.querySelector('textarea');j.value='Reabrir para conferir de novo (fictício).';
      j.dispatchEvent(new Event('input'));const r=document.querySelector('[data-acao-aprovacao=revogar]').disabled;c.querySelector('input[type=checkbox]').click();
      return [r, document.querySelector('[data-acao-aprovacao=revogar]').disabled]})()""")
    antes = len(posts())
    cdp.js("document.querySelector('[data-acao-aprovacao=revogar]').click()")
    esperar("document.querySelector('.ac-faixa') && document.querySelector('.ac-faixa').dataset.faixa==='verde'", 8)
    time.sleep(0.6)
    novos = posts()[antes:]
    aba("historico")
    hist = texto("[data-historico-aprovacoes]")
    registrar("AB-12 revogação: exige justificativa + confirmação; POST {acao:'revogar', justificativa, confirmado:true}; volta a aguardar; histórico mostra REVOGADO",
              desab == [True, False] and len(novos) == 1 and novos[0]["corpo"] == {"acao": "revogar", "justificativa": "Reabrir para conferir de novo (fictício).", "confirmado": True}
              and cdp.js("document.querySelector('.ac-cab .ac-selo').textContent") == "Aguardando Supervisor" and "REVOGADO" in hist
              and cdp.js("EV.app.estadoDe('dp').local") == "mesa", f"{desab} · {json.dumps(novos, ensure_ascii=False)} · {hist[:200]!r}")

    # ---------------- com impedimentos: faixa âmbar, botão desabilitado, Conciliação filtrada
    carregar("falha_cdp")
    acompanhar()
    faixa = texto(".ac-faixa")
    imp = texto(".ac-impedimentos")
    btn = cdp.js("document.querySelector('[data-acao-aprovacao=abrir-aprovar]').disabled")
    resumo = texto(".ac-resumo")
    registrar("AB-13 com impedimentos: faixa ÂMBAR \"4 itens impedem a aprovação\" com a lista curta; botão desabilitado e impedimentos explicados",
              cdp.js("document.querySelector('.ac-faixa').dataset.faixa") == "ambar" and "4 itens impedem a aprovação" in faixa
              and "CONTABILIDADE_DP" in faixa and btn is True and "divergente" in imp and "alcance parcial" in imp
              and not any(x in resumo for x in PROIBIDOS), f"{faixa!r} · {imp!r}")
    topo()
    cdp.foto(fotos / "depois-2-com-impedimentos.png")
    antes = len(posts())
    cdp.js("document.querySelector('[data-acao-aprovacao=abrir-aprovar]').click()")
    time.sleep(0.4)
    registrar("AB-14 botão desabilitado não abre confirmação nem envia nada", not cdp.js("!!document.querySelector('[data-acao-aprovacao=aprovar]')")
              and len(posts()) == antes)
    aba("conciliacao")
    conc = jsj("""(()=>{const vis=()=>Array.from(document.querySelectorAll('[data-conciliacao] tbody[data-verificacao]')).filter(t=>!t.hidden).map(t=>t.dataset.resultado);
      const r={padrao:vis(),pressionado:document.querySelector('[data-filtro-conc][aria-pressed=true]').dataset.filtroConc,
        cab:Array.from(document.querySelectorAll('.ac-grade-conc thead th')).map(t=>t.textContent),grupos:Array.from(document.querySelectorAll('[data-conciliacao] tr[data-grupo]')).map(g=>g.dataset.grupo)};
      const v=document.querySelector('[data-verificacao="CONC-C-SALDO-1101"]');const det=v.querySelector('.ac-v-detalhe');r.detAntes=det.hidden;v.querySelector('.ac-expandir').click();
      r.detDepois=det.hidden;r.detTexto=det.innerText;return r})()""")
    registrar("AB-15 Conciliação: filtro padrão \"Divergentes e pendentes\" (3 linhas), resumo por grupo A–E, colunas pedidas e linha expansível com fontes, justificativa e ação",
              conc["padrao"] and set(conc["padrao"]) <= {"DIVERGENTE", "PENDENTE"} and len(conc["padrao"]) == 3 and conc["pressionado"] == "abertas"
              and conc["cab"] == ["Grupo", "Verificação", "Conta / item", "Esperado", "Encontrado", "Diferença", "Resultado", "Área"]
              and conc["grupos"] == ["A", "B", "C", "D", "E"] and conc["detAntes"] and not conc["detDepois"]
              and all(x in conc["detTexto"] for x in ("EXTERNA", "INTERNA", "Justificativa", "Ação")), json.dumps(conc, ensure_ascii=False)[:400])
    topo()
    cdp.foto(fotos / "depois-5-aba-conciliacao-filtrada.png")
    cdp.js("document.querySelector('[data-filtro-conc=todas]').click()")
    todas = cdp.js("Array.from(document.querySelectorAll('[data-conciliacao] tbody[data-verificacao]')).filter(t=>!t.hidden).length")
    # atualização da tela preserva aba, filtro e linha aberta
    acompanhar()
    preservado = jsj("[document.querySelector('.ac-aba[aria-selected=true]').dataset.aba, document.querySelector('[data-filtro-conc][aria-pressed=true]').dataset.filtroConc,"
                     "!document.querySelector('[data-verificacao=\"CONC-C-SALDO-1101\"] .ac-v-detalhe').hidden]")
    registrar("AB-16 \"Todas\" mostra as 8 verificações; atualizar a tela preserva aba, filtro e linha aberta", todas == 8 and preservado == ["conciliacao", "todas", True],
              f"{todas} · {preservado}")
    aba("decisoes")
    dec = texto(".ac-painel-decisoes")
    registrar("AB-17 Decisões: retomada de etapa com justificativa e confirmação continua disponível (fila de decisões preservada)",
              cdp.js("!!document.querySelector('.ac-painel-decisoes [data-retomar=CONTABILIDADE_DP]')") and "Decisões que exigem a sua ação" in dec, dec[:200])

    # ---------------- Ampliar painel: o escritório encolhe mas continua visível; sem rolagem horizontal
    medidas = {}
    for w, h in ((1280, 800), (1000, 720)):
        carregar("falha_cdp", w=w, h=h)
        acompanhar()
        aba("conciliacao")
        cdp.js("document.querySelector('[data-filtro-conc=todas]').click()")
        normal = jsj(layout)
        cdp.js("document.querySelector('.ac-ampliar').click()")
        time.sleep(0.6)
        amp = jsj(layout)
        rotulo = cdp.js("document.querySelector('.ac-ampliar').textContent")
        if w == 1280:
            topo()
            cdp.foto(fotos / "depois-7-painel-ampliado-1280.png")
        else:
            topo()
            cdp.foto(fotos / "depois-9-ampliado-1000x720.png")
        cdp.js("document.querySelector('.ac-ampliar').click()")
        time.sleep(0.6)
        volta = jsj(layout)
        if w == 1000:
            aba("resumo")
            topo()
            cdp.foto(fotos / "depois-8-resumo-1000x720.png")
        medidas[f"{w}x{h}"] = {"normal": normal, "ampliado": amp, "recolhido": volta, "rotulo": rotulo}
        ok = (amp["painel"] > normal["painel"] + 100 and volta["painel"] == normal["painel"] and rotulo == "Recolher painel"
              and all(not m["scroll"] and m["fora"] == 0 and m["palco"] > 200 and m["palcoEsq"] >= m["painelDir"] - 1 and m["visivel"] == "visible"
                      for m in (normal, amp, volta)))
        registrar(f"AB-18 {w}×{h}: \"Ampliar painel\" alarga o acompanhamento, o escritório continua visível ao lado; \"Recolher\" volta; sem rolagem horizontal",
                  ok, json.dumps(medidas[f"{w}x{h}"]))

    # ---------------- encerrada e cancelada: faixa cinza, sem aprovação
    for n, sol, titulo in (("enc", "SOL-2026-000102", "Revisão parcial encerrada"), ("can", "SOL-2026-000103", "Solicitação cancelada")):
        carregar(n)
        acompanhar(sol)
        faixa = texto(".ac-faixa")
        registrar(f"AB-19 {n.upper()}: faixa CINZA \"{titulo}\"; sem botão de aprovação; nada aprovado nem escriturado",
                  cdp.js("document.querySelector('.ac-faixa').dataset.faixa") == "cinza" and titulo in faixa
                  and not cdp.js("!!document.querySelector('[data-acao-aprovacao]')") and not afirma_escrituracao(texto(".ac-resumo")), faixa[:200])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fotos = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="acomp-ev-"))
    fotos.mkdir(parents=True, exist_ok=True)
    mock = subprocess.Popen([sys.executable, "-I", str(Path(__file__).with_name("mock_api_escritorio.py")), str(RAIZ / "ESCRITORIO-VIRTUAL"), str(PORTA_MOCK)])
    perfil = tempfile.mkdtemp(prefix="chrome-acomp-ev-")
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
            registrar("AB-XX bateria interrompida", False, repr(e)[:300])
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
