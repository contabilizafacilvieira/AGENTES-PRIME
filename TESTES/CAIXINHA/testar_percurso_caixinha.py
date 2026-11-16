"""CONCILIAÇÃO CAIXINHA — percurso pela API REAL em ambiente ISOLADO (CX-01..CX-24). Dados 100% FICTÍCIOS.

Cadastro (rotina CAIXINHA, regras versionadas e aprovadas, piloto sem vínculo bancário) → upload dos cinco documentos → Documentos
classifica pelo CONTEÚDO → Contábil (leitores) → Fiscal (e-CAC, situação fiscal) → DP (resumo da folha) → Conciliação Caixinha →
painel → simulação do TXT → aprovação → TXT (empresa fictícia) / bloqueado (empresa sem marcador fictício) → idempotência,
razão atualizado após a importação, mudança de regras (vigência), isolamento entre empresas, fluxo tradicional preservado e lote.

Uso (raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/CAIXINHA/testar_percurso_caixinha.py
"""
import hashlib
import json
import sys
import threading
import time
from decimal import Decimal as D
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(RAIZ / "TESTES"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
sys.path.insert(0, str(RAIZ / "TESTES" / "CAIXINHA"))
import ambiente_isolado as ai  # noqa: E402
AMB = ai.criar("prime-caixinha-")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import cenario_complementar as cc  # noqa: E402
import cenario_caixinha as cx  # noqa: E402
import ficticios_caixinha as fc  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:500]))


def reg(sol=None):
    r = ai.registro_isolado()["solicitacoes"]
    return r[sol] if sol else r


def ultima_sol(emp):
    return sorted(s for s, x in reg().items() if x["empresa"] == emp)[-1]


def main():
    foto = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c = cc.Cliente(srv.server_address[1])
    espera = lambda: cc.ocioso(servidor, ai.registro_isolado)  # noqa: E731
    painel = lambda sol: c.j("GET", f"/api/solicitacoes/{sol}/caixinha")[1]  # noqa: E731
    esp = fc.esperado("A")
    try:
        # ---------------------------------------------------------------- configuração por empresa
        A = cx.cadastrar(c, "A", ficticia=True, clientes=AMB.clientes)
        st, cfg0 = c.j("GET", f"/api/empresas/{A}/caixinha?competencia=2026-10")
        sug = cfg0["proposta_inicial"]["sugestoes"]
        registrar("CX-01 sugestão de contas pela descrição do plano DA EMPRESA (Caixa 11, Simples 401, INSS 402, IRRF 403, Pró-labore 301), "
                  "nada gravado nem aprovado",
                  st == 200 and {k: sug[k]["sugerida"] for k in ("CAIXA_GERAL", "SIMPLES_NACIONAL", "INSS", "IRRF", "PRO_LABORE")}
                  == {"CAIXA_GERAL": "11", "SIMPLES_NACIONAL": "401", "INSS": "402", "IRRF": "403", "PRO_LABORE": "301"}
                  and cfg0["regras"] is None and cfg0["tipo_rotina"] == "CAIXINHA", json.dumps({k: v["sugerida"] for k, v in sug.items()}))
        st_r, r_r = c.j("POST", f"/api/empresas/{A}/caixinha-regras", {"confirmado": True, "configuracao": cx.configuracao(
            contas=dict(fc.ROTINA, INSS="999"))})
        st_s, r_s = cx.salvar_regras(c, A)
        regras_arq = AMB.clientes / A / "REGRAS-CAIXINHA.json"
        dados = json.loads(regras_arq.read_text(encoding="utf-8"))
        registrar("CX-02 regras gravadas como PROPOSTA versionada (conta fora do plano recusada); nada aplicado antes da aprovação",
                  st_r == 400 and "999" in r_r.get("erro", "") and st_s == 200 and dados["configuracao"]["situacao"] == "PROPOSTA"
                  and dados["politica_folha"]["situacao"] == "PROPOSTA", (st_r, r_r.get("erro"), dados["configuracao"]["situacao"]))
        st_e, r_e = c.j("POST", f"/api/empresas/{A}/caixinha-aprovar", {"chave": "CONFIGURACAO", "frase": "VALIDADO REGRA CAIXINHA OUTRA CONFIGURACAO",
                                                                         "confirmado": True})
        st_p, _ = cx.habilitar(c, A)
        aprov = [cx.aprovar(c, A, k)[0] for k in ("CONFIGURACAO", "POLITICA_FOLHA")]
        dados = json.loads(regras_arq.read_text(encoding="utf-8"))
        registrar("CX-03 aprovação só com a frase exata pelo Coordenador (versão + sha256 do conteúdo vinculados); piloto Caixinha sem "
                  "vínculo bancário; versões anteriores preservadas",
                  st_e == 409 and st_p == 200 and aprov == [200, 200] and dados["configuracao"]["confirmacao"]["conteudo_sha256"]
                  == dados["configuracao"]["conteudo_sha256"] and len(list((AMB.clientes / A / "VERSOES").glob("REGRAS-CAIXINHA-*"))) >= 2
                  and "Conciliação Caixinha: PILOTO SIMULACAO AUTORIZADO" in (AMB.clientes / A / "CADASTRO.md").read_text(encoding="utf-8"),
                  (st_e, st_p, aprov))
        st_f, r_f = c.j("POST", "/api/lotes", {"empresa": A, "competencia": "2026-10", "fluxo": "FINANCEIRO_BANCOS", "instrucao": "Teste 10/2026."})
        registrar("CX-04 empresa Caixinha sem vínculo bancário NÃO ganha o fluxo Financeiro/Bancos (exigência bancária preservada)",
                  st_f == 403, (st_f, r_f))

        # ---------------------------------------------------------------- execução individual
        docs = fc.documentos("A")
        # nomes trocados de propósito: a identificação é pelo CONTEÚDO
        trocados = [("arquivo_" + n.split("_", 1)[0] + ".pdf", b) for n, b in docs]
        lote = cx.criar_lote(c, A, trocados)
        st_i, r_i = cx.iniciar(c, lote)
        espera()
        sol1 = r_i["sol"]
        s1 = reg(sol1)
        man = json.loads((servidor.RUNTIME / "execucoes" / sol1 / "documentos-local.json").read_text(encoding="utf-8"))
        tipos = sorted(i["tipo"] for i in man["itens"])
        registrar("CX-05 Documentos identifica os cinco documentos pelo CONTEÚDO (nomes genéricos) e distribui: balancete/razão → Contábil, "
                  "e-CAC/situação fiscal → Fiscal, resumo da folha → DP",
                  tipos == sorted(["Balancete contábil do período", "Razão contábil", "Pagamentos efetuados (e-CAC)", "Relatório de situação fiscal",
                                   "Resumo mensal da folha (Domínio)"]) and {i["encaminhamento"]["area"] for i in man["itens"]} == {"CONTABIL", "FISCAL", "DP"},
                  tipos)
        plano = {e["etapa"]: e["situacao"] for e in s1["plano_etapas"]}
        execs = sorted(p.name for p in (servidor.RUNTIME / "execucoes" / sol1).iterdir() if p.is_dir())
        registrar("CX-06 plano do Coordenador: somente as etapas Caixinha (Contábil → Fiscal → DP → Conciliação), todas registradas; "
                  "nenhum Financeiro/Bancos executado; nenhum extrato exigido",
                  st_i == 202 and plano == {"CAIXINHA_CONTABIL": "CONCLUIDA", "CAIXINHA_FISCAL": "CONCLUIDA", "CAIXINHA_DP": "CONCLUIDA",
                                            "CAIXINHA_CONCILIACAO": "CONCLUIDA"} and s1["estado"] == "AGUARDANDO_SUPERVISOR"
                  and not any(x.startswith(("financeiro", "bancos", "conciliacao-")) for x in execs)
                  and all(s1[k][-1].get("resultado_sha256") and s1[k][-1].get("fontes_sha256") for k in
                          ("caixinha_contabil", "caixinha_fiscal", "caixinha_dp", "caixinha_conciliacao")), (plano, execs))
        p1 = painel(sol1)
        conc = p1["conciliacao"]
        trib = {x["conta"]["codigo"]: x for x in conc["tributos"]["por_conta"]}
        registrar("CX-07 tributos reproduzidos pelo processamento (saldo − baixas propostas = saldo restante) para Simples, INSS e IRRF",
                  all(D(trib[k]["baixas_propostas"]) == esp["baixas_tributarias"][k] and D(trib[k]["saldo_restante"]) == esp["restantes"][k]
                      and D(trib[k]["saldo_contabil"]) == esp["saldos"][k] for k in ("401", "402", "403"))
                  and D(conc["tributos"]["baixas_propostas"]) == esp["total_tributarias"],
                  json.dumps({k: (v["saldo_contabil"], v["baixas_propostas"], v["saldo_restante"]) for k, v in trib.items()}))
        f = conc["folha"]
        registrar("CX-08 pró-labore: saldo contábil, último líquido (resumo do Domínio), baixa de competências anteriores e saldo esperado",
                  D(f["saldo_contabil"]) == esp["saldos"]["301"] and D(f["ultimo"]["liquido"]) == esp["ultimo_liquido"]
                  and D(f["baixa"]) == esp["baixa_folha"] and D(f["saldo_esperado"]) == esp["ultimo_liquido"]
                  and f["situacao"] == "REGULARIZACAO_PROPOSTA", {k: f[k] for k in ("saldo_contabil", "baixa", "saldo_esperado", "situacao")})
        cxa = conc["caixa"]
        registrar("CX-09 Caixa: saldo inicial − baixas tributárias − baixas de folha = saldo CONTÁBIL projetado (aviso: não é dinheiro físico)",
                  D(cxa["saldo_inicial"]) == esp["caixa"] and D(cxa["saldo_projetado"]) == esp["caixa_projetado"]
                  and "dinheiro físico" in cxa["aviso"], cxa)
        lancs = conc["lancamentos"]
        darf_ago = [l for l in lancs if l.get("periodo_apuracao") == "31/08/2026"]
        registrar("CX-10 DARF com INSS + IRRF: um débito por tributo (contas 402 e 403), mesmo grupo, soma = valor pago = crédito no Caixa",
                  sorted((l["debito"]["codigo"], l["valor"]) for l in darf_ago) == [("402", "550.00"), ("403", "402.35")]
                  and {l["credito"]["codigo"] for l in darf_ago} == {"11"} and len({l["grupo"] for l in darf_ago}) == 1,
                  [(l["debito"]["codigo"], l["valor"], l["grupo"]) for l in darf_ago])
        ob = {(o.get("tipo_documento"), o.get("periodo_apuracao")): o for o in conc["obrigacoes"] if o.get("pagamento")}
        jul = ob[("DARF", "31/07/2026")]
        registrar("CX-11 DARF de julho já baixado no razão: PAGA E CONTABILIZADA por critério verificável (valor + data/referência), sem baixa nova",
                  jul["classificacao"] == "PAGA_E_CONTABILIZADA" and not jul["lancamentos"] and "referência" in " ".join(jul["criterios"]), jul["criterios"])
        das_jul = [l for l in lancs if l.get("periodo_apuracao") == "07/2026"][0]
        folha_l = [l for l in lancs if l["origem"] == "CAIXINHA_FOLHA"][0]
        registrar("CX-12 datas: pagamento de competência encerrada lançado no último dia da competência como REGULARIZAÇÃO (política da empresa); "
                  "folha classificada REGULARIZAÇÃO CONFORME POLÍTICA CAIXINHA (evidência = política operacional, não pagamento comprovado)",
                  das_jul["data"] == "2026-10-31" and das_jul["regularizacao"] and das_jul["historico"].startswith("REGULARIZACAO")
                  and folha_l["classificacao"] == "REGULARIZACAO_CONFORME_POLITICA_CAIXINHA" and folha_l["evidencia"] == "POLITICA_OPERACIONAL",
                  (das_jul["data"], folha_l["evidencia"]))
        doc_ecac = next(d for d in p1["documentos"] if d["tipo"] == "PAGAMENTOS_ECAC")
        st_d, cab_d, bruto = c.http("GET", f"/api/solicitacoes/{sol1}/caixinha/documento/{doc_ecac['id']}")
        st_x, _ = c.j("GET", f"/api/solicitacoes/{sol1}/caixinha/documento/CXD-000000000000")
        pagina_ok = all(isinstance((o.get("origem") or {}).get("pagina"), int) for o in conc["obrigacoes"] if o.get("pagamento"))
        registrar("CX-13 evidência: o documento de origem abre pelo id da ficha (sha256 conferido) e cada pagamento indica a PÁGINA; id de "
                  "outro documento recusado",
                  st_d == 200 and hashlib.sha256(bruto).hexdigest() == doc_ecac["sha256"] and bruto.startswith(b"%PDF") and st_x == 404 and pagina_ok,
                  (st_d, st_x))
        st_t, sim = c.j("GET", f"/api/solicitacoes/{sol1}/caixinha/simulacao-txt")
        registrar("CX-14 simulação do TXT (layout do Domínio): linhas balanceadas por pagamento, datas válidas, contas analíticas; nenhum "
                  "arquivo gravado; aviso NÃO IMPORTAR",
                  st_t == 200 and sim["balanceado"] and len(sim["linhas"]) == len(lancs) == 8 and not sim["problemas"]
                  and "NÃO IMPORTAR" in sim["aviso"] and not (AMB.liberados / A).exists(), (len(sim["linhas"]), sim["problemas"]))

        # ---------------------------------------------------------------- aprovação e exportação
        st_a0, r_a0 = c.j("POST", f"/api/solicitacoes/{sol1}/aprovacao", {"acao": "aprovar", "frase": "APROVO FECHAMENTO",
                                                                          "justificativa": "Baixas conferidas (fictício).", "confirmado": True})
        st_a, r_a = c.j("POST", f"/api/solicitacoes/{sol1}/aprovacao", {"acao": "aprovar", "frase": f"APROVO FECHAMENTO {sol1}",
                                                                        "justificativa": "Baixas conferidas (fictício).", "confirmado": True,
                                                                        "ciente_pendencias": True})
        lib = (r_a or {}).get("liberacao") or {}
        txt = AMB.liberados / A / "2026-10" / f"lanctos_{A}_2026-10_{sol1}.txt"
        linhas_txt = txt.read_bytes().decode("cp1252").splitlines() if txt.is_file() else []
        registrar("CX-15 aprovação explícita (frase) → TXT do Domínio gerado pelo exportador EXISTENTE só para empresa fictícia: 8 linhas, "
                  "partida simples, cp1252, mesmos valores; Excel e balancete juntos",
                  st_a0 == 409 and st_a == 200 and lib.get("situacao") == "LIBERADO_PARA_IMPORTACAO_MANUAL" and len(linhas_txt) == 8
                  and sum(D(l.split(";")[3].replace(",", ".")) for l in linhas_txt) == esp["total_tributarias"] + esp["baixa_folha"]
                  and all(l.split(";")[2] == "11" for l in linhas_txt) and len(lib.get("anexos") or {}) == 2, (st_a, lib.get("situacao"), len(linhas_txt)))

        # ---------------------------------------------------------------- idempotência / reprocessamento
        lote2 = cx.criar_lote(c, A, docs)
        _, r2 = cx.iniciar(c, lote2)
        espera()
        c2 = painel(r2["sol"])["conciliacao"]
        registrar("CX-16 reprocessar os MESMOS documentos (nova solicitação) não cria nenhuma baixa: pagamentos já aprovados e ainda não vistos "
                  "no razão vão à revisão (sem duplicidade)",
                  c2["resumo"]["propostos"] == 0 and c2["resumo"]["revisao"] >= 6 and not c2["lancamentos"]
                  and all("já aprovada" in " ".join(o["motivos"]) for o in c2["obrigacoes"] if o.get("classificacao") == "NECESSITA_REVISAO"),
                  c2["resumo"])
        # Supervisor importa o TXT no Domínio (manual) e reenvia razão e balancete
        fc.PARTIDAS_EXTRAS[:] = [(f"{l.split(';')[0]}", l.split(";")[1], l.split(";")[2], D(l.split(";")[3].replace(",", ".")), l.split(";")[5])
                                 for l in linhas_txt]
        docs_pos = [(n, b) for n, b in fc.documentos("A")]
        fc.PARTIDAS_EXTRAS[:] = []
        lote3 = cx.criar_lote(c, A, docs_pos)
        _, r3 = cx.iniciar(c, lote3)
        espera()
        c3 = painel(r3["sol"])["conciliacao"]
        t3 = {x["conta"]["codigo"]: x for x in c3["tributos"]["por_conta"]}
        registrar("CX-17 razão e balancete reenviados após a importação: todas as baixas reconhecidas como PAGAS E CONTABILIZADAS, folha com "
                  "saldo = último líquido, Caixa conferido; nenhuma nova proposta",
                  c3["resumo"]["propostos"] == 0 and c3["resumo"]["revisao"] == 0
                  and c3["resumo"]["obrigacoes"]["PAGA_E_CONTABILIZADA"] == 6 and c3["folha"]["situacao"] == "PAGA_E_CONTABILIZADA"
                  and all(D(t3[k]["saldo_contabil"]) == esp["restantes"][k] for k in ("401", "402", "403"))
                  and D(c3["caixa"]["saldo_inicial"]) == esp["caixa_projetado"], c3["resumo"])

        # ---------------------------------------------------------------- segunda empresa (sem marcador fictício): regras, isolamento, TXT
        B = cx.cadastrar(c, "B", ficticia=False)
        cx.salvar_regras(c, B)
        cx.habilitar(c, B)
        docs_b = fc.documentos("B") + [("06_ecac_de_outra_empresa.pdf", fc.ecac_pdf("A", blocos=[dict(fc.ecac_blocos("A")[0], numero="99.99.9999.9999999-9")]))]
        lote_b = cx.criar_lote(c, B, docs_b)
        _, rb = cx.iniciar(c, lote_b)
        espera()
        solb = rb["sol"]
        pb = painel(solb)
        cb = pb["conciliacao"]
        registrar("CX-18 regras ainda em PROPOSTA: análise feita, mas TODAS as propostas INCOMPLETAS e a aprovação impedida",
                  cb["resumo"]["incompletos"] == 8 and cb["resumo"]["propostos"] == 0
                  and any("incompleto" in x for x in pb["aprovacao_impedimentos"]), (cb["resumo"], pb["aprovacao_impedimentos"][:2]))
        man_b = json.loads((servidor.RUNTIME / "execucoes" / solb / "documentos-local.json").read_text(encoding="utf-8"))
        outro = next(i for i in man_b["itens"] if "outra_empresa" in i["arquivo"])
        registrar("CX-19 isolamento: documento e-CAC de OUTRA empresa no lote não é distribuído nem lido; nenhum pagamento dele na conciliação",
                  outro["encaminhamento"]["situacao"] == "DOCUMENTO_NAO_IDENTIFICA_EMPRESA"
                  and not any("99.99.9999" in str(o.get("numero_documento")) for o in cb["obrigacoes"]), outro["encaminhamento"]["situacao"])
        for k in ("CONFIGURACAO", "POLITICA_FOLHA"):
            cx.aprovar(c, B, k)
        pb2 = painel(solb)
        st_rt, r_rt = c.j("POST", f"/api/solicitacoes/{solb}/areas/CAIXINHA_CONCILIACAO/retomar", {"justificativa": "Regras aprovadas.", "confirmado": True})
        espera()
        pb3 = painel(solb)
        registrar("CX-20 mudança de regras torna a conciliação DESATUALIZADA (vigência pelas fontes); retomada pelo Supervisor reexecuta só a "
                  "Conciliação Caixinha, agora com propostas completas",
                  not pb2["vigencia"]["vigente"] and "CAIXINHA_CONCILIACAO" in pb2["vigencia"]["rever"] and st_rt == 202
                  and pb3["vigencia"]["vigente"] and pb3["conciliacao"]["resumo"]["propostos"] == 8
                  and len(reg(solb)["caixinha_conciliacao"]) == 2 and len(reg(solb)["caixinha_fiscal"]) == 1,
                  (pb2["vigencia"]["rever"], st_rt, pb3["conciliacao"]["resumo"]["propostos"]))
        st_b, r_b = c.j("POST", f"/api/solicitacoes/{solb}/aprovacao", {"acao": "aprovar", "frase": f"APROVO FECHAMENTO {solb}",
                                                                        "justificativa": "Conferido (fictício).", "confirmado": True, "ciente_pendencias": True})
        registrar("CX-21 empresa sem marcador fictício (equivale a real): aprovação registrada, TXT BLOQUEADO (produção bloqueada; nenhum arquivo)",
                  st_b == 200 and (r_b.get("liberacao") or {}).get("situacao") == "BLOQUEADA_PRODUCAO" and not (AMB.liberados / B).exists(),
                  (st_b, (r_b.get("liberacao") or {}).get("situacao")))
        # alteração de regra depois da aprovação: aprovação deixa de valer para exportar
        cfg_nova = cx.configuracao()
        cfg_nova["criterios_baixa"]["janela_dias_baixa_razao"] = 2
        cx.salvar_regras(c, B, cfg=cfg_nova, folha=False)
        det = c.j("GET", f"/api/solicitacoes/{solb}")[1]
        registrar("CX-22 regra alterada depois da aprovação: nova versão em PROPOSTA e aprovação marcada como sem vigência (rever)",
                  any("regras da rotina Caixinha" in m for m in det["vigencia_aprovacao"]), det["vigencia_aprovacao"])

        # ---------------------------------------------------------------- fluxo tradicional preservado
        st_tr, r_tr = c.j("POST", "/api/empresas", {"id": "TRADICIONAL-FICTICIA", "nome": "TRADICIONAL FICTICIA LTDA",
                                                    "cnpj": fc.cnpj("939393930001"), "regime": "LUCRO PRESUMIDO (FICTICIO)"})
        st_l, r_l = c.j("POST", "/api/lotes", {"empresa": "TRADICIONAL-FICTICIA", "competencia": "2026-10", "fluxo": "CONCILIACAO_CAIXINHA",
                                               "instrucao": "Teste 10/2026."})
        cad_tr = (AMB.clientes / "TRADICIONAL-FICTICIA" / "CADASTRO.md").read_text(encoding="utf-8")
        st_h, r_h = c.j("POST", "/api/empresas/TRADICIONAL-FICTICIA/piloto", {"frase": "CONFIRMO PILOTO TRADICIONAL-FICTICIA"})
        registrar("CX-23 empresa TRADICIONAL: sem rotina Caixinha no cadastro, não abre Conciliação Caixinha e o piloto continua exigindo "
                  "vínculo bancário (lógica tradicional intocada)",
                  st_tr == 201 and st_l == 403 and "Rotina: CAIXINHA" not in cad_tr and st_h == 400 and "vínculo bancário" in r_h.get("erro", ""),
                  (st_l, st_h, r_h.get("erro")))

        # ---------------------------------------------------------------- execução em lote
        la = cx.criar_lote(c, A, fc.documentos("A"), competencia="2026-10")
        lb = cx.criar_lote(c, B, fc.documentos("B"), competencia="2026-10")
        st_q, r_q = c.j("POST", "/api/caixinha/lote/executar", {"lotes": [la, lb], "confirmado": True})
        fim = time.time() + 300
        while time.time() < fim:
            pl = c.j("GET", "/api/caixinha/lote?competencia=2026-10")[1]
            if pl["fila"]["fim"]:
                break
            time.sleep(0.5)
        espera()
        pl = c.j("GET", "/api/caixinha/lote?competencia=2026-10")[1]
        cats = {x["empresa"]: x["categoria"] for x in pl["empresas"]}
        sols_fila = [x["sol"] for x in pl["fila"]["resultados"]]
        registrar("CX-24 execução em LOTE: duas empresas processadas uma de cada vez, cada uma na própria solicitação; painel por categoria "
                  "(divergências/revisão, aprovação, documentos, exportação)",
                  st_q == 202 and len(sols_fila) == 2 and all(sols_fila) and len(set(sols_fila)) == 2
                  and {reg(s)["empresa"] for s in sols_fila} == {A, B} and set(cats) == {A, B}
                  and all(v in pl["categorias"] for v in cats.values()) and sum(pl["totais"].values()) == 2, (cats, pl["fila"]["resultados"]))
    finally:
        srv.shutdown()
        registrar("CX-99 estado operacional (CLIENTES, registro, ordem ativa, LIBERADOS reais) intocado", foto_operacional() == foto)
    falhas = [r for r in resultados if not r[1]]
    for caso, ok, det in resultados:
        print(("PASSOU " if ok else "FALHOU ") + caso + ("" if ok else f" — {det}"))
    print(f"RESUMO: {len(resultados) - len(falhas)}/{len(resultados)} casos aprovados")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
