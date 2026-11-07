"""Bateria do Escritório Virtual no navegador (Chrome sem interface): hierarquia, caminhos, caminhada e capturas.

Abre a página DIRETO DO DISCO (modo simulação, sem rede) e injeta estados FICTÍCIOS calculados pela mesma função de
mapeamento usada no modo operação (EV.mapa.operacao). Não usa a API, documentos reais, registros nem o runtime.

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_escritorio.py <pasta para capturas>
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

PAGINA = (RAIZ / "ESCRITORIO-VIRTUAL" / "index.html").as_uri()
PORTA = 9334
resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), detalhe))


# Estados fictícios: uma SOL VGROW de teste percorrendo as etapas. "{t}" = horário (ms) gerado no navegador.
ETAPAS = {
    "docs_andamento": ("DOCUMENTOS_EM_ANDAMENTO", {"documentos": {"status": "EM_ANDAMENTO", "inicio": "{t0}"},
                                                  "reconhecimento": {"status": "NAO_EXECUTADO"}, "importacao": {"status": "NAO_SOLICITADA"}}),
    "docs_concluido": ("AGUARDANDO_SUPERVISOR", {"documentos": {"status": "CONCLUIDA", "inicio": "{t0}", "fim": "{t1}"},
                                                 "reconhecimento": {"status": "EM_ANDAMENTO", "inicio": "{t1}"}, "importacao": {"status": "NAO_SOLICITADA"}}),
    "imp_andamento": ("AGUARDANDO_SUPERVISOR", {"documentos": {"status": "CONCLUIDA", "inicio": "{t0}", "fim": "{t1}"},
                                                "reconhecimento": {"status": "PRONTO", "fim": "{t1}"},
                                                "importacao": {"status": "EM_ANDAMENTO", "n": 1, "inicio": "{t2}", "fim": None}}),
    "imp_concluida": ("AGUARDANDO_SUPERVISOR", {"documentos": {"status": "CONCLUIDA", "inicio": "{t0}", "fim": "{t1}"},
                                                "reconhecimento": {"status": "PRONTO", "fim": "{t1}"},
                                                "importacao": {"status": "CONCLUIDA", "n": 1, "inicio": "{t2}", "fim": "{t3}",
                                                               "resumo": {"fechados": 1, "bloqueios": 1, "aguardando_aceite": 0}}}),
    # fluxo Financeiro → Contabilidade/Bancos (passagem da pasta entre mesas)
    "fb_docs": ("DOCUMENTOS_EM_ANDAMENTO", {"documentos": {"status": "EM_ANDAMENTO", "inicio": "{t0}"}, "reconhecimento": {"status": "NAO_APLICAVEL"},
                                           "importacao": {"status": "NAO_APLICAVEL"}, "financeiro": {"status": "NAO_EXECUTADA"}, "bancos": {"status": "NAO_EXECUTADA"}}),
    "fb_fin": ("FINANCEIRO_EM_ANDAMENTO", {"documentos": {"status": "CONCLUIDA", "inicio": "{t0}", "fim": "{t1}"}, "reconhecimento": {"status": "NAO_APLICAVEL"},
                                          "importacao": {"status": "NAO_APLICAVEL"}, "financeiro": {"status": "EM_ANDAMENTO", "n": 1, "inicio": "{t1}"},
                                          "bancos": {"status": "NAO_EXECUTADA"}}),
    "fb_ban": ("BANCOS_EM_ANDAMENTO", {"documentos": {"status": "CONCLUIDA", "inicio": "{t0}", "fim": "{t1}"}, "reconhecimento": {"status": "NAO_APLICAVEL"},
                                      "importacao": {"status": "NAO_APLICAVEL"}, "financeiro": {"status": "CONCLUIDA", "n": 1, "inicio": "{t1}", "fim": "{t2}", "resumo": {}},
                                      "bancos": {"status": "EM_ANDAMENTO", "n": 1, "inicio": "{t2}"}}),
    "fb_fim": ("AGUARDANDO_SUPERVISOR", {"documentos": {"status": "CONCLUIDA", "inicio": "{t0}", "fim": "{t1}"}, "reconhecimento": {"status": "NAO_APLICAVEL"},
                                        "importacao": {"status": "NAO_APLICAVEL"}, "financeiro": {"status": "CONCLUIDA", "n": 1, "inicio": "{t1}", "fim": "{t2}", "resumo": {}},
                                        "bancos": {"status": "CONCLUIDA", "n": 1, "inicio": "{t2}", "fim": "{t3}", "resumo": {"propostos": 6, "incompletos": 6}}}),
    "fb_bloq": ("AGUARDANDO_SUPERVISOR", {"documentos": {"status": "CONCLUIDA", "inicio": "{t0}", "fim": "{t1}"}, "reconhecimento": {"status": "NAO_APLICAVEL"},
                                         "importacao": {"status": "NAO_APLICAVEL"},
                                         "financeiro": {"status": "CONCLUIDA", "n": 1, "inicio": "{t1}", "fim": "{t2}", "bloqueado": True, "resumo": {}},
                                         "bancos": {"status": "NAO_EXECUTADA"}}),
}

APLICAR = """((estado, etapas, horarios) => {
  const t = (k) => new Date(horarios[k]).toISOString();
  const preencher = (o) => JSON.parse(JSON.stringify(o), (k, v) => (typeof v === "string" && /^\\{t\\d\\}$/.test(v) ? t(v.slice(1, 3)) : v));
  const s = { sol: "SOL-2026-900010", empresa: "EMPRESA-FICTICIA (VGROW de teste)", competencia: "2026-09", estado, etapas: preencher(etapas) };
  const est = EV.mapa.operacao({ recentes: [s], foco: { sol: s.sol, pendencias: ["P-01 · Documento · fictício"] } });
  // mesma formatação de horários do modo operação (js/operacao.js)
  const hora = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" }) : "");
  Object.values(est).forEach((e) => { e.atualizacao = hora(e.fim || e.inicio); e.inicio = hora(e.inicio); e.fim = hora(e.fim); });
  EV.app.aplicarOperacao(est, "teste");
  return true;
})(%s, %s, window.__horarios)"""


def aplicar(cdp, chave):
    estado, etapas = ETAPAS[chave]
    return cdp.js(APLICAR % (json.dumps(estado), json.dumps(etapas)))


def posicoes(cdp):
    return cdp.js("EV.app.cena._posicoes()")


def acompanhar(cdp, segundos, passo=0.1):
    """Amostra as posições até todos pararem (ou o tempo acabar). Devolve a lista de amostras."""
    amostras, fim = [], time.time() + segundos
    while time.time() < fim:
        p = posicoes(cdp)
        amostras.append(p)
        if len(amostras) > 3 and not any(v["andando"] for v in p.values()):
            break
        time.sleep(passo)
    return amostras


def carregar(cdp, consulta="", reduzido=False):
    cdp.chamar("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce" if reduzido else "no-preference"}])
    cdp.chamar("Page.navigate", url=PAGINA + consulta)
    for _ in range(50):
        time.sleep(0.2)
        if cdp.js("!!(window.EV && EV.app && EV.app.cena && EV.mapa)"):
            break
    # horários "depois do carregamento": t0..t3 a partir de 2 s após a carga
    cdp.js("window.__horarios = (() => { const b = Math.ceil(Date.now() / 1000) * 1000 + 2000; return { t0: b, t1: b + 1000, t2: b + 2000, t3: b + 3000 }; })()")


def trilha(amostras, agente):
    """Sequência de destinos de um personagem (sem repetições consecutivas): mesa, assento, visita:<destino>."""
    seq = []
    for a in amostras:
        v = a[agente]
        x = f"visita:{v['destino']}" if v["alvo"] == "visita" else v["alvo"]
        if not seq or seq[-1] != x:
            seq.append(x)
    return seq


def acompanhar_foto(cdp, segundos, condicao_js, destino):
    """Como acompanhar(), mas captura a tela na primeira amostra em que a condição (JS) for verdadeira."""
    amostras, fim, tirada = [], time.time() + segundos, False
    while time.time() < fim:
        amostras.append(posicoes(cdp))
        if not tirada and cdp.js(condicao_js):
            cdp.foto(destino)
            tirada = True
        if len(amostras) > 3 and not any(v["andando"] for v in amostras[-1].values()):
            break
        time.sleep(0.1)
    return amostras, tirada


SOBREPOSICAO = """((g) => {
  // retângulo × polígono convexo (SAT) e retângulo × retângulo, com 1 px de folga
  const hull = (pts) => { pts = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lo = [], hi = [];
    for (const p of pts) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
    for (const p of pts.slice().reverse()) { while (hi.length >= 2 && cross(hi[hi.length - 2], hi[hi.length - 1], p) <= 0) hi.pop(); hi.push(p); }
    return lo.slice(0, -1).concat(hi.slice(0, -1)); };
  const rpts = (r) => [[r.x + 1, r.y + 1], [r.x + r.w - 1, r.y + 1], [r.x + r.w - 1, r.y + r.h - 1], [r.x + 1, r.y + r.h - 1]];
  const sat = (a, b) => { for (const poly of [a, b]) for (let i = 0; i < poly.length; i++) {
      const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % poly.length], n = [y1 - y2, x2 - x1];
      const pa = a.map((p) => p[0] * n[0] + p[1] * n[1]), pb = b.map((p) => p[0] * n[0] + p[1] * n[1]);
      if (Math.max(...pa) < Math.min(...pb) || Math.max(...pb) < Math.min(...pa)) return false; }
    return true; };
  const conflitos = [];
  const placas = Object.entries(g.placas);
  placas.forEach(([a, ra], i) => {
    placas.slice(i + 1).forEach(([b, rb]) => { if (sat(rpts(ra), rpts(rb))) conflitos.push(`placa ${a} × placa ${b}`); });
    Object.entries(g.alvos).forEach(([b, rb]) => { if (sat(rpts(ra), rpts(rb))) conflitos.push(`placa ${a} × personagem ${b}`); });
    g.moveis.forEach((m, k) => { if (sat(rpts(ra), hull(m))) conflitos.push(`placa ${a} × móvel ${k}`); });
  });
  return conflitos;
})(EV.app.cena._geometria())"""


def bateria(cdp, fotos):
    carregar(cdp, "?cenario=repouso")
    i = cdp.js("EV.cena._interno")  # noqa: F841 (garante que a cena carregou)
    # E-01 hierarquia
    h = cdp.js("""(() => ({
      agentes: EV.app.agentes.map(a => a.id + ':' + (a.implementado ? 1 : 0) + ':' + (a.area || '') + ':' + (a.relacao || '')),
      quadro: document.querySelector('.quadro-area') && document.querySelector('.quadro-area').textContent,
      placas: Array.from(document.querySelectorAll('.placa-posto')).map(p => p.textContent) }))()""")
    registrar("E-01 hierarquia: Importação e Bancos são especialistas da Contabilidade; Financeiro confere; Fiscal e DP fornecem; Conciliação implementada após a Contabilidade",
              "importacao:1:contabilidade:" in h["agentes"] and "bancos:1:contabilidade:" in h["agentes"]
              and any(a.startswith("financeiro:1::Recebe de Documentos") for a in h["agentes"])
              and 'fiscal:1::Fornece informações à Contabilidade' in h['agentes'] and 'dp:1::Fornece informações à Contabilidade' in h['agentes']
              and any(a.startswith("conciliacao:1::Após Contabilidade") for a in h["agentes"])
              and all(n in h["quadro"] for n in ("Contabilidade", "Importação", "Bancos"))
              and h["placas"] == ["5 · Coordenador", "1 · Documentos", "2 · Financeiro", "2 · Fiscal", "2 · DP", "4 · Conciliação", "Copa"]
              and not any("breve" in x for x in h["placas"])
              and not any(a.startswith("contabil") for a in h["agentes"]), " | ".join(h["placas"]) + " · " + h["quadro"])
    p = posicoes(cdp)
    registrar("E-02 só módulos funcionais caminham (Documentos, Financeiro, Fiscal, DP, Importação, Bancos e Conciliação; Coordenador fica no posto)",
              sorted(p) == ["bancos", "conciliacao", "documentos", "dp", "financeiro", "fiscal", "importacao"], str(sorted(p)))
    registrar("E-03 repouso: os 7 personagens na copa (3 lugares do sofá + poltrona; os demais em pé), posições distintas, sem caminhada ao carregar",
              sum(v['pose']=='sentado' for v in p.values())==4 and all(v['alvo'] in ('assento', 'copa-em-pe') for v in p.values())
              and all(not v['andando'] for v in p.values()) and len({(v["x"], v["y"]) for v in p.values()}) == 7, json.dumps(p)[:160])
    cdp.foto(fotos / "1-repouso-copa.png")

    # E-04/E-05 caminhos na grade
    r = cdp.js("""(() => {
      const I = EV.cena._interno, g = I.grade();
      const pontos = { docMesa: I.POSTOS.documentos.pessoa, impMesa: I.POSTOS.importacao.pessoa, finMesa: I.POSTOS.financeiro.pessoa,
                       banMesa: I.POSTOS.bancos.pessoa, fiscalMesa:I.POSTOS.fiscal.pessoa, entregaFiscal:I.ENTREGA.fiscal, visita: I.VISITA_COORDENADOR, entregaFin: I.ENTREGA.financeiro, entregaBan: I.ENTREGA.bancos,
                       dpMesa: I.POSTOS.dp.pessoa, entregaDp: I.ENTREGA.dp, concMesa: I.POSTOS.conciliacao.pessoa, entregaConc: I.ENTREGA.conciliacao };
      I.COPA.assentos.forEach((a, k) => pontos['assento' + k] = a);
      I.COPA.emPe.forEach((a, k) => pontos['emPe' + k] = a);
      const livre = (q) => I.ehLivre(g, ...I.celulaDe(q));
      const dentroDivisoria = (q) => (q.x > 5.95 && q.x < 6.15 && q.y < 6.0) || (q.y > 5.95 && q.y < 6.15 && q.x < 4.3);
      const problemas = []; let pares = 0, porta = false;
      const nomes = Object.keys(pontos);
      nomes.forEach(a => nomes.forEach(b => {
        if (a === b) return;
        pares++;
        const c = I.planejarCaminho(g, pontos[a], pontos[b]);
        if (!c) { problemas.push(a + '→' + b + ': sem caminho'); return; }
        for (let k = 0; k + 1 < c.length; k++) {
          const p = c[k], q = c[k + 1], n = Math.ceil(Math.hypot(q.x - p.x, q.y - p.y) / 0.05);
          const extremo = k === 0 || k === c.length - 2;   // saída/chegada no assento ou cadeira
          if (extremo && Math.hypot(q.x - p.x, q.y - p.y) > 1.0) problemas.push(a + '→' + b + ': trecho de saída/chegada longo');
          for (let s = 0; s <= n; s++) {
            const z = { x: p.x + (q.x - p.x) * s / n, y: p.y + (q.y - p.y) * s / n };
            if (dentroDivisoria(z)) problemas.push(a + '→' + b + ': atravessa divisória de vidro');
            if (!extremo && !livre(z)) problemas.push(a + '→' + b + ': passa sobre móvel/parede em ' + z.x.toFixed(2) + ',' + z.y.toFixed(2));
            if (a === 'docMesa' && b === 'visita' && z.y > 5.9 && z.y < 6.2 && z.x > 4.3 && z.x < 6.0) porta = true;
          }
        }
      }));
      return { pares, problemas: [...new Set(problemas)].slice(0, 8), porta };
    })()""")
    registrar("E-04 caminhos entre mesas, Coordenador e copa: existem e não passam sobre móveis, paredes ou divisórias",
              r["pares"] >= 72 and not r["problemas"], f"{r['pares']} pares · " + "; ".join(r["problemas"]))
    registrar("E-05 Documentos entra na sala do Coordenador pela porta (vão da divisória de vidro)", r["porta"])

    # E-06 evento real depois do carregamento: busca no Coordenador (com envelope) e vai à mesa
    aplicar(cdp, "docs_andamento")
    amostras, foto_envelope, t_fim = [], False, time.time() + 25
    while time.time() < t_fim:
        q = posicoes(cdp)
        amostras.append(q)
        if q["documentos"]["carregando"] and not foto_envelope and q["documentos"]["alvo"] == "mesa":
            cdp.foto(fotos / "2-documentos-levando-envelope.png")
            foto_envelope = True
        if len(amostras) > 5 and not q["documentos"]["andando"]:
            break
        time.sleep(0.1)
    alvos = [a["documentos"]["alvo"] for a in amostras]
    seq = [x for k, x in enumerate(alvos) if not k or x != alvos[k - 1]]
    registrar("E-06 tarefa autorizada: levanta da copa, vai ao Coordenador, leva o envelope e senta na mesa",
              seq[:2] == ["visita", "mesa"] and amostras[-1]["documentos"]["pose"] == "mesa" and foto_envelope
              and not amostras[-1]["documentos"]["carregando"], " → ".join(seq))
    cdp.foto(fotos / "3-documentos-trabalhando.png")

    # E-07 o mesmo estado reaplicado não repete a ida ao Coordenador
    aplicar(cdp, "docs_andamento")
    time.sleep(0.6)
    registrar("E-07 estado repetido não repete a caminhada nem a entrega", not posicoes(cdp)["documentos"]["andando"])

    # E-08 entrega: leva o relatório ao Coordenador e volta à copa; painel preserva o resultado
    aplicar(cdp, "docs_concluido")
    amostras = acompanhar(cdp, 25)
    alvos = [a["documentos"]["alvo"] for a in amostras]
    seq = [x for k, x in enumerate(alvos) if not k or x != alvos[k - 1]]
    cdp.js("EV.app.selecionar('documentos')")
    time.sleep(0.4)
    ficha = cdp.js("document.getElementById('ficha').textContent")
    coord = cdp.js("EV.app.estadoDe('coordenador')")
    registrar("E-08 entrega no Coordenador e volta à mesa enquanto a SOL ainda está pendente",
              seq[:2] == ["visita", "mesa"] and amostras[-1]["documentos"]["pose"] == "mesa"
              and "Concluído — relatório entregue" in ficha and "solicitação ainda não concluída" in ficha, " → ".join(seq))
    registrar("E-09 Coordenador mostra o estado real (reconhecimento em andamento → Trabalhando, não Aguardando Supervisor)",
              coord["status"] == "TRABALHANDO" and "Reconhecimento" in coord["tarefa"], coord["tarefa"])
    cdp.foto(fotos / "4-documentos-na-copa-resultado-preservado.png")
    cdp.js("EV.app.fecharPainel()")

    # E-10 Importação: busca, calcula na mesa; etapa termina ANTES de chegar → segue o estado mais recente
    aplicar(cdp, "imp_andamento")
    time.sleep(1.2)
    cdp.foto(fotos / "5-importacao-a-caminho.png")
    durante = posicoes(cdp)["importacao"]
    aplicar(cdp, "imp_concluida")
    amostras = acompanhar(cdp, 25)
    alvos = [durante["alvo"]] + [a["importacao"]["alvo"] for a in amostras]
    seq = [x for k, x in enumerate(alvos) if not k or x != alvos[k - 1]]
    registrar("E-10 etapa rápida preserva buscar, passagem pela mesa, entrega e retorno ao posto",
              durante["andando"] and "mesa" in seq and seq[-1] == "mesa" and seq.count("visita") == 2
              and amostras[-1]["importacao"]["pose"] == "mesa", " → ".join(seq))
    imp = cdp.js("EV.app.estadoDe('importacao')")
    coord = cdp.js("EV.app.estadoDe('coordenador')")
    registrar("E-11 Importação \"Concluído — aguardando conferência\" com a SOL em Aguardando Supervisor",
              imp["status"] == "CONCLUIDO" and imp["tarefa"] == "Concluído — aguardando conferência" and coord["status"] == "AGUARDANDO_SUPERVISOR")
    cdp.js("EV.app.selecionar('importacao')")
    time.sleep(0.4)
    cdp.foto(fotos / "6-importacao-concluida-aguardando-conferencia.png")

    # E-12 Importação trabalhando (estado direto, sem animação antiga)
    carregar(cdp, "?cenario=importacao&agente=contabilidade")
    time.sleep(0.6)
    q = posicoes(cdp)
    ficha = cdp.js("document.getElementById('ficha').textContent")
    registrar("E-12 painel da Contabilidade lista os especialistas (Importação funcional; demais em breve)",
              q["importacao"]["pose"] == "mesa" and "Especialistas internos (6)" in ficha and "Importação VGROW" in ficha and "Em breve" in ficha)
    cdp.foto(fotos / "7-contabilidade-especialistas-importacao-trabalhando.png")

    # E-13 recarregar não repete entregas: eventos anteriores ao carregamento são ignorados
    carregar(cdp, "?cenario=repouso")
    cdp.js("window.__horarios = { t0: Date.now() - 60000, t1: Date.now() - 50000, t2: Date.now() - 40000, t3: Date.now() - 30000 }")
    aplicar(cdp, "imp_concluida")
    amostras = acompanhar(cdp, 2.5, 0.1)
    registrar("E-13 recarga: entregas anteriores ao carregamento não são repetidas (personagens já no lugar atual)",
              not any(a[k]["andando"] for a in amostras for k in a)
              and all(amostras[-1][k]["pose"] == "mesa" for k in ("documentos", "importacao"))
              and all(amostras[-1][k]["pose"] in ('sentado','pe') and amostras[-1][k]['alvo'] in ('assento','copa-em-pe') for k in ("financeiro", "bancos")))

    # E-14 movimento reduzido: sem caminhada, sem envelope; personagem aparece direto no lugar do estado atual
    carregar(cdp, "?cenario=repouso", reduzido=True)
    aplicar(cdp, "docs_andamento")
    amostras = acompanhar(cdp, 2.5, 0.1)
    q = amostras[-1]["documentos"]
    img1 = cdp.chamar("Page.captureScreenshot", format="png")["data"]
    time.sleep(0.7)
    img2 = cdp.chamar("Page.captureScreenshot", format="png")["data"]
    registrar("E-14 movimento reduzido: sem caminhada nem transições; Documentos aparece direto na mesa e a cena fica estática",
              not any(a["documentos"]["andando"] for a in amostras) and q["pose"] == "mesa" and not q["carregando"] and img1 == img2)
    cdp.foto(fotos / "8-movimento-reduzido-documentos-trabalhando.png")

    # ---------------- passagem da pasta entre mesas (fluxo Financeiro → Contabilidade/Bancos)
    carregar(cdp, "?cenario=repouso")
    cdp.js("window.__horarios.t4 = window.__horarios.t3 + 1000")
    aplicar(cdp, "fb_docs")
    a1 = acompanhar(cdp, 25)
    aplicar(cdp, "fb_fin")
    a2, foto2 = acompanhar_foto(cdp, 25, "EV.app.cena._posicoes().documentos.carregando && EV.app.cena._posicoes().documentos.destino === 'financeiro'",
                                fotos / "2-documentos-entrega-pasta-ao-financeiro.png")
    pasta_fin = cdp.js("JSON.stringify(EV.app.cena._pastas())")
    aplicar(cdp, "fb_ban")
    a3, foto3 = acompanhar_foto(cdp, 25, "EV.app.cena._posicoes().financeiro.carregando && EV.app.cena._posicoes().financeiro.destino === 'bancos'",
                                fotos / "3-financeiro-entrega-pasta-a-bancos.png")
    pasta_ban = cdp.js("JSON.stringify(EV.app.cena._pastas())")
    aplicar(cdp, "fb_fim")
    a4, foto4 = acompanhar_foto(cdp, 25, "EV.app.cena._posicoes().bancos.carregando && EV.app.cena._posicoes().bancos.destino === 'coordenador'",
                                fotos / "4-bancos-devolve-ao-coordenador.png")
    pasta_fim = cdp.js("JSON.stringify(EV.app.cena._pastas())")
    cdp.foto(fotos / "5-fluxo-concluido-pasta-no-coordenador.png")
    registrar("E-16 pasta passa de mesa em mesa: Coordenador → Documentos → Financeiro → Bancos → Coordenador, uma entrega por etapa registrada",
              trilha(a1, "documentos")[-2:] == ["visita:coordenador", "mesa"]
              and trilha(a2, "documentos")[-2:] == ["visita:financeiro", "mesa"] and "visita:coordenador" not in trilha(a2, "financeiro")
              and trilha(a2, "financeiro")[-1] == "mesa" and pasta_fin == '[{"agente":"financeiro","bloqueada":false}]'
              and trilha(a3, "financeiro")[-2:] == ["visita:bancos", "mesa"] and trilha(a3, "bancos")[-1] == "mesa"
              and pasta_ban == '[{"agente":"bancos","bloqueada":false}]'
              and trilha(a4, "bancos")[-2:] == ["visita:coordenador", "mesa"] and pasta_fim == '[{"agente":"coordenador","bloqueada":false}]'
              and foto2 and foto3 and foto4,
              f"docs {trilha(a2, 'documentos')} · fin {trilha(a3, 'financeiro')} · bancos {trilha(a4, 'bancos')}")
    # bloqueio no Financeiro: nenhuma entrega ao Bancos; a pasta fica no Financeiro
    carregar(cdp, "?cenario=repouso")
    aplicar(cdp, "fb_fin")
    acompanhar(cdp, 25)
    aplicar(cdp, "fb_bloq")
    a5 = acompanhar(cdp, 25)
    pasta_bloq = cdp.js("JSON.stringify(EV.app.cena._pastas())")
    cdp.foto(fotos / "6-lote-bloqueado-pasta-no-financeiro.png")
    registrar("E-17 bloqueio antes de Bancos: nenhuma entrega inventada; pasta parada no Financeiro (bloqueada); Bancos não sai da copa",
              not any(x.startswith("visita") for x in trilha(a5, "financeiro")) and trilha(a5, "bancos") == ["assento"]
              and pasta_bloq == '[{"agente":"financeiro","bloqueada":true}]' and cdp.js("EV.app.estadoDe('financeiro').status") == "PENDENCIA",
              f"fin {trilha(a5, 'financeiro')} · pasta {pasta_bloq}")
    # atualização rápida: todas as etapas terminam enquanto Documentos ainda caminha
    carregar(cdp, "?cenario=repouso")
    aplicar(cdp, "fb_docs")
    time.sleep(0.4)
    aplicar(cdp, "fb_fim")
    a6 = acompanhar(cdp, 90)
    t_doc, t_fin, t_ban = trilha(a6, "documentos"), trilha(a6, "financeiro"), trilha(a6, "bancos")
    registrar("E-18 atualização rápida preserva todas as mesas e entregas sem repetição",
              "mesa" in t_doc and t_doc[-2:] == ["visita:financeiro", "mesa"] and t_doc.count("visita:financeiro") == 1
              and t_fin[-2:] == ["visita:bancos", "mesa"] and t_fin.count("visita:bancos") == 1 and "mesa" in t_fin
              and t_ban[-2:] == ["visita:coordenador", "mesa"] and t_ban.count("visita:coordenador") == 1 and "mesa" in t_ban
              and cdp.js("JSON.stringify(EV.app.cena._pastas())") == '[{"agente":"coordenador","bloqueada":false}]',
              f"docs {t_doc} · fin {t_fin} · bancos {t_ban}")
    # recarga: entregas anteriores ao carregamento não se repetem; pasta já no lugar atual
    carregar(cdp, "?cenario=repouso")
    cdp.js("window.__horarios = { t0: Date.now() - 60000, t1: Date.now() - 50000, t2: Date.now() - 40000, t3: Date.now() - 30000 }")
    aplicar(cdp, "fb_fim")
    a7 = acompanhar(cdp, 2.5)
    registrar("E-19 recarga no fluxo financeiro: nenhuma caminhada antiga repetida; pasta direto no Coordenador",
              not any(a[k]["andando"] for a in a7 for k in a) and cdp.js("JSON.stringify(EV.app.cena._pastas())") == '[{"agente":"coordenador","bloqueada":false}]')
    # movimento reduzido: sem caminhada; pasta e personagens direto no lugar atual
    carregar(cdp, "?cenario=repouso", reduzido=True)
    aplicar(cdp, "fb_ban")
    a8 = acompanhar(cdp, 2.5)
    q8 = a8[-1]
    registrar("E-20 movimento reduzido: participantes na mesa, sem caminhada nem envelope; pasta em Bancos",
              not any(a[k]["andando"] for a in a8 for k in a) and q8["bancos"]["pose"] == "mesa" and q8["financeiro"]["pose"] == "mesa"
              and not any(v["carregando"] for v in q8.values()) and cdp.js("JSON.stringify(EV.app.cena._pastas())") == '[{"agente":"bancos","bloqueada":false}]')
    cdp.foto(fotos / "7-movimento-reduzido-bancos.png")
    # placas sem sobreposição (personagens, móveis e entre si), na janela padrão e em janela menor
    carregar(cdp, "?cenario=financeiro")
    time.sleep(0.6)
    c_padrao = cdp.js(SOBREPOSICAO)
    cdp.chamar("Emulation.setDeviceMetricsOverride", width=1100, height=760, deviceScaleFactor=1, mobile=False)
    carregar(cdp, "?cenario=financeiro")
    time.sleep(0.6)
    c_menor = cdp.js(SOBREPOSICAO)
    cdp.foto(fotos / "8-janela-menor.png")
    cdp.chamar("Emulation.clearDeviceMetricsOverride")
    registrar("E-21 placas e quadro da Contabilidade não se sobrepõem a personagens, móveis nem entre si (1500×1000 e 1100×760)",
              not c_padrao and not c_menor, "; ".join((c_padrao or []) + (c_menor or []))[:200])

    # Fiscal usa os mesmos corredores e permanece no posto até terminar a SOL.
    carregar(cdp,'?cenario=repouso')
    etapas_f={'documentos':{'status':'CONCLUIDA','inicio':'{t0}','fim':'{t1}'},
              'fiscal':{'status':'EM_ANDAMENTO','n':1,'inicio':'{t1}'},'contabilfiscal':{'status':'NAO_EXECUTADA'}}
    cdp.js(APLICAR % (json.dumps('FISCAL_EM_ANDAMENTO'),json.dumps(etapas_f)))
    amostras=acompanhar(cdp,35)
    registrar('E-22 Fiscal recebe de Documentos, caminha até a mesa e trabalha',
              amostras[-1]['fiscal']['pose']=='mesa' and 'visita:fiscal' in trilha(amostras,'documentos'))
    cdp.foto(fotos/'9-fiscal-trabalhando.png')
    etapas_f['fiscal'].update(status='CONCLUIDA',fim='{t2}',resumo={'documentos':1,'pendencias':0})
    etapas_f['contabilfiscal']={'status':'EM_ANDAMENTO','n':1,'inicio':'{t2}'}
    cdp.js(APLICAR % (json.dumps('CONTABILIDADE_FISCAL_EM_ANDAMENTO'),json.dumps(etapas_f)))
    amostras=acompanhar(cdp,30)
    registrar('E-23 Fiscal entrega à Contabilidade e volta à mesa, sem ir à copa na SOL aberta',
              'visita:bancos' in trilha(amostras,'fiscal') and amostras[-1]['fiscal']['pose']=='mesa' and amostras[-1]['bancos']['pose']=='mesa')
    cdp.foto(fotos/'10-fiscal-entregue-contabilidade.png')

    # Percurso completo: DP recebe de Documentos e trabalha; Contabilidade entrega à Conciliação; não acionados na copa.
    carregar(cdp, '?cenario=repouso')
    cdp.js("window.__horarios.t4 = window.__horarios.t3 + 1000; window.__horarios.t5 = window.__horarios.t3 + 2000")
    na = {'status': 'NAO_APLICAVEL'}
    etapas_p = {'documentos': {'status': 'CONCLUIDA', 'inicio': '{t0}', 'fim': '{t1}'}, 'reconhecimento': na, 'importacao': na,
                'financeiro': na, 'bancos': na, 'fiscal': na, 'contabilfiscal': na,
                'dp': {'status': 'EM_ANDAMENTO', 'n': 1, 'inicio': '{t1}'}, 'contabdp': {'status': 'NAO_EXECUTADA'}, 'conciliacao': {'status': 'NAO_EXECUTADA'}}
    cdp.js(APLICAR % (json.dumps('DP_EM_ANDAMENTO'), json.dumps(etapas_p)))
    amostras = acompanhar(cdp, 35)
    st = cdp.js("EV.app.estadoDe('dp').status")
    q = amostras[-1]
    registrar('E-24 DP recebe a pasta de Documentos, caminha até a própria mesa e trabalha; não acionados (Fiscal, Conciliação, Importação) na copa',
              q['dp']['pose'] == 'mesa' and st == 'TRABALHANDO' and 'visita:dp' in trilha(amostras, 'documentos')
              and all(q[k]['alvo'] in ('assento', 'copa-em-pe') for k in ('fiscal', 'conciliacao', 'importacao', 'financeiro', 'bancos')),
              f"dp {st} {q['dp']['pose']} · docs {trilha(amostras, 'documentos')}")
    cdp.foto(fotos / '11-dp-trabalhando-copa-nao-acionados.png')
    etapas_p['dp'].update(status='CONCLUIDA', fim='{t2}', resumo={'documentos': 3, 'fatos': 7, 'pendencias': 0})
    etapas_p['contabdp'] = {'status': 'CONCLUIDA', 'n': 1, 'inicio': '{t2}', 'fim': '{t3}', 'resumo': {'propostos': 7, 'incompletos': 0}}
    etapas_p['conciliacao'] = {'status': 'EM_ANDAMENTO', 'n': 1, 'inicio': '{t4}'}
    cdp.js(APLICAR % (json.dumps('CONCILIACAO_EM_ANDAMENTO'), json.dumps(etapas_p)))
    amostras = acompanhar(cdp, 60)
    q = amostras[-1]
    registrar('E-25 DP entrega à Contabilidade; a Contabilidade entrega à Conciliação, que trabalha na própria mesa (pasta na Conciliação)',
              'visita:bancos' in trilha(amostras, 'dp') and 'visita:conciliacao' in trilha(amostras, 'bancos') and q['conciliacao']['pose'] == 'mesa'
              and q['dp']['pose'] == 'mesa' and cdp.js("JSON.stringify(EV.app.cena._pastas())") == '[{"agente":"conciliacao","bloqueada":false}]'
              and cdp.js("EV.app.estadoDe('conciliacao').status") == 'TRABALHANDO',
              f"dp {trilha(amostras, 'dp')} · bancos {trilha(amostras, 'bancos')} · conc {trilha(amostras, 'conciliacao')}")
    cdp.foto(fotos / '12-conciliacao-trabalhando.png')
    etapas_p['conciliacao'].update(status='CONCLUIDA', fim='{t5}', resumo={'conferido': 20, 'divergente': 0, 'pendente': 0, 'nao_aplicavel': 1, 'total': 21})
    cdp.js(APLICAR % (json.dumps('AGUARDANDO_SUPERVISOR'), json.dumps(etapas_p)))
    amostras = acompanhar(cdp, 40)
    q = amostras[-1]
    registrar('E-26 Conciliação entrega ao Coordenador e permanece na mesa (SOL aberta aguardando o Supervisor); Coordenador não aprova nada',
              trilha(amostras, 'conciliacao')[-2:] == ['visita:coordenador', 'mesa'] and q['conciliacao']['pose'] == 'mesa'
              and cdp.js("EV.app.estadoDe('coordenador').status") == 'AGUARDANDO_SUPERVISOR',
              f"conc {trilha(amostras, 'conciliacao')}")
    cdp.foto(fotos / '13-conciliacao-entregue-coordenador.png')
    carregar(cdp, '?cenario=percurso')
    time.sleep(0.6)
    q = posicoes(cdp)
    registrar('E-27 cenário de demonstração "Percurso completo": Conciliação trabalhando e DP na mesa (dados fictícios)',
              q['conciliacao']['pose'] == 'mesa' and q['dp']['pose'] == 'mesa' and cdp.js("EV.app.estadoDe('conciliacao').status") == 'TRABALHANDO'
              and q['importacao']['alvo'] in ('assento', 'copa-em-pe'))
    cdp.foto(fotos / '14-cenario-percurso-dp-conciliacao.png')

    # E-15 a cena e o mapeamento não chamam a API nem disparam operações
    fonte = "".join((RAIZ / "ESCRITORIO-VIRTUAL" / "js" / n).read_text(encoding="utf-8") for n in ("cena.js", "mapa.js"))
    registrar("E-15 animações só leem o estado (cena.js e mapa.js sem fetch, XHR ou chamadas à API)",
              not any(x in fonte for x in ("fetch(", "XMLHttpRequest", "api(", "/api/", "WebSocket")))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fotos = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="escritorio-"))
    fotos.mkdir(parents=True, exist_ok=True)
    perfil = tempfile.mkdtemp(prefix="chrome-ev-")
    chrome = subprocess.Popen([str(CHROME), "--headless=new", f"--remote-debugging-port={PORTA}", f"--user-data-dir={perfil}",
                               "--window-size=1500,1000", "--no-first-run", "--disable-extensions", "about:blank"])
    try:
        for _ in range(50):
            try:
                alvos = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/json/list"))
                pagina = next(a for a in alvos if a["type"] == "page")
                break
            except Exception:
                time.sleep(0.3)
        cdp = CDP(pagina["webSocketDebuggerUrl"])
        cdp.chamar("Page.enable")
        bateria(cdp, fotos)
    finally:
        chrome.terminate()
    falhas = 0
    for caso, ok, det in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {caso}" + (f"  — {det}" if det else ""))
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL · capturas em {fotos}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
