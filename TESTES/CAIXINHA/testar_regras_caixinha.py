"""CONCILIAÇÃO CAIXINHA — leitores e regras de segurança (CXR-01..CXR-24). Dados 100% FICTÍCIOS; API real em ambiente ISOLADO.

Leitores (unitários): reconhecimento pelo conteúdo, guia × pagamento, lista sem composição, CNPJ de outra empresa, situação fiscal
(a vencer × vencido), resumo da folha (totais conferidos; folha mista), layout documentado do DP preservado.
Conciliação (API): sem composição, guia sem comprovação, mesmo pagamento em dois arquivos, possível pagamento duplicado, multa/juros,
situação fiscal divergente, pagamento após a competência, razão × balancete, folha sem provisão da última competência, Caixa credor,
política de data DATA_PAGAMENTO, razão ausente (alcance parcial), regras de outra empresa.

Uso (raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/CAIXINHA/testar_regras_caixinha.py
"""
import hashlib
import json
import shutil
import sys
import threading
from decimal import Decimal as D
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(RAIZ / "TESTES"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
sys.path.insert(0, str(RAIZ / "TESTES" / "CAIXINHA"))
import ambiente_isolado as ai  # noqa: E402
AMB = ai.criar("prime-caixinha-regras-")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import cenario_complementar as cc  # noqa: E402
import cenario_caixinha as cx  # noqa: E402
import ficticios_caixinha as fc  # noqa: E402
import documentos_local as dl  # noqa: E402
import leitura_pdf_local as lp  # noqa: E402
import pagamentos_ecac  # noqa: E402
import situacao_fiscal  # noqa: E402
import resumo_folha_dominio as rfd  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:500]))


def extraido(nome, dados):
    p = AMB.raiz / "leitura" / nome
    p.parent.mkdir(exist_ok=True)
    p.write_bytes(dados)
    a = lp.ler(p) if nome.endswith(".pdf") else {"leitura": "EXTRAIDO_TEXTO", "conteudo": {"texto": dados.decode("utf-8")}}
    a.update(arquivo=nome, sha256=hashlib.sha256(dados).hexdigest(), extensao=Path(nome).suffix)
    return a


def leitores():
    e = fc.EMPRESAS["A"]
    cnpjs = [e["cnpj"]]
    guia = ("DOCUMENTO DE ARRECADACAO DE RECEITAS FEDERAIS - DARF\nCNPJ: " + e["cnpj"] + "\nCodigo da Receita: 0561\nPeriodo de Apuracao: "
            "31/10/2026\nData de Vencimento: 20/11/2026\nValor Total: 402,35\nPagavel ate 20/11/2026\n").encode("utf-8")
    a = extraido("guia.txt", guia)
    registrar("CXR-01 guia (DARF emitido, sem data de arrecadação) NÃO é reconhecida como pagamento do e-CAC (segue como guia ao Fiscal)",
              dl.classificar(a) == "Possível guia" and not pagamentos_ecac.reconhece(dl.texto_de_documento(a)), dl.classificar(a))
    bloco_sem_pg = dict(fc.ecac_blocos("A")[0], pago=None, numero="07.20.2610.0000010-0")
    r = pagamentos_ecac.ler(extraido("ecac_guia.pdf", fc.ecac_pdf("A", blocos=[fc.ecac_blocos("A")[0], bloco_sem_pg])), e["id"], cnpjs)
    ev = sorted(p["evidencia"] for p in r["pagamentos"])
    registrar("CXR-02 bloco sem data de arrecadação dentro do relatório = GUIA_SEM_COMPROVACAO (não utilizável)",
              ev == ["GUIA_SEM_COMPROVACAO", "PAGAMENTO_REGISTRADO_ECAC"] and not [p for p in r["pagamentos"] if p["evidencia"] != "PAGAMENTO_REGISTRADO_ECAC"][0]["utilizavel"], ev)
    lista = ("RECEITA FEDERAL - e-CAC\nCONSULTA DE PAGAMENTOS\nCNPJ: " + e["cnpj"] + "\nTipo Numero do Documento Periodo de Apuracao Data de "
             "Arrecadacao Data de Vencimento Codigo de Receita Valor Total\n"
             "DARF 07.01.26.00000001-1 31/08/2026 18/09/2026 20/09/2026 0561 402,35\n"
             "DARF 07.01.26.00000002-2 31/08/2026 25/09/2026 20/09/2026 0561 410,00\n"
             "DARF 07.01.26.00000003-3 31/08/2026 18/09/2026 20/09/2026 - 952,35\n").encode("utf-8")
    r = pagamentos_ecac.ler(extraido("lista.txt", lista), e["id"], cnpjs)
    comp = {p["numero_documento"]: (p["composicao"], p["utilizavel"]) for p in r["pagamentos"]}
    registrar("CXR-03 lista sem composição: código único pago no prazo = principal; pago após o vencimento ou sem código → pendente "
              "(divisão nunca presumida)",
              comp == {"07.01.26.00000001-1": ("CODIGO_UNICO_PAGO_NO_PRAZO", True), "07.01.26.00000002-2": ("NAO_INFORMADA", False),
                       "07.01.26.00000003-3": ("NAO_INFORMADA", False)}, comp)
    r = pagamentos_ecac.ler(extraido("outro.pdf", fc.ecac_pdf("B")), e["id"], cnpjs)
    registrar("CXR-04 relatório do e-CAC de OUTRO CNPJ: nenhum pagamento aproveitado (isolamento)", not r["pagamentos"]
              and any("outra" in x or "não é da empresa" in x for x in r["pendencias"]), r["pendencias"])
    itens = [("1082", "CP SEGURADOS", "08/2026", "20/09/2026", D("550.00"), "DEVEDOR"), ("", "SIMPLES NACIONAL", "10/2026", "20/11/2026", D("3500.00"), "A VENCER")]
    r = situacao_fiscal.ler(extraido("sf.pdf", fc.situacao_fiscal_pdf("A", itens=itens)), e["id"], cnpjs)
    est = sorted((i["codigo_receita"] or "", i["estado_vencimento"]) for i in r["itens"])
    r2 = situacao_fiscal.ler(extraido("sf2.pdf", fc.situacao_fiscal_pdf("A", sem_pendencias=True)), e["id"], cnpjs)
    registrar("CXR-05 situação fiscal: emissão respeitada (vencido × a vencer); 'sem pendências' registrado como declaração, sem itens",
              est == [("", "A_VENCER"), ("1082", "VENCIDO")] and r2["sem_pendencias_declaradas"] and not r2["itens"], (est, r2["dados"]))
    r = rfd.ler(extraido("folha_mista.pdf", fc.folha_pdf("A", extra_provento=("SALARIO", D("2000.00")))), e["id"], cnpjs)
    r_ok = rfd.ler(extraido("folha.pdf", fc.folha_pdf("A")), e["id"], cnpjs)
    registrar("CXR-06 resumo da folha: proventos − descontos = líquido conferido; folha com salário além do pró-labore → líquido do pró-labore "
              "NÃO separado (pendência)", r_ok["pro_labore"]["liquido"] == "4047.65" and (r["pro_labore"] or {}).get("liquido") is None
              and any("além de pró-labore" in x for x in r["pendencias"]), r["pendencias"][-1:])
    doc = ("RESUMO DA FOLHA DE PAGAMENTO\nCNPJ: " + e["cnpj"] + "\nCOMPETENCIA: 10/2026\nNUMERO DO DOCUMENTO: FP-1\nRUBRICA;TIPO;VALOR\n"
           "SALARIO;PROVENTO;1.000,00\nTOTAL DE PROVENTOS: 1.000,00\nTOTAL DE DESCONTOS: 0,00\nLIQUIDO A PAGAR: 1.000,00\n").encode("utf-8")
    registrar("CXR-07 layout documentado do DP (RUBRICA;TIPO;VALOR) continua no leitor existente (não vira resumo do Domínio)",
              dl.classificar(extraido("fp.txt", doc)) == "Resumo da folha de pagamento", dl.classificar(extraido("fp.txt", doc)))


def preparar(c, cenario="A", politica="DATA_PAGAMENTO_OU_ULTIMO_DIA"):
    emp = cx.cadastrar(c, cenario, ficticia=True, clientes=AMB.clientes)
    cx.salvar_regras(c, emp, cfg=cx.configuracao(politica=politica))
    cx.habilitar(c, emp)
    for k in ("CONFIGURACAO", "POLITICA_FOLHA"):
        cx.aprovar(c, emp, k)
    return emp


def rodar(c, emp, docs):
    lote = cx.criar_lote(c, emp, docs)
    st, r = cx.iniciar(c, lote)
    assert st == 202, (st, r)
    cc.ocioso(servidor, ai.registro_isolado)
    return r["sol"], c.j("GET", f"/api/solicitacoes/{r['sol']}/caixinha")[1]


def obrig(conc, pa):
    return [o for o in conc["obrigacoes"] if o.get("periodo_apuracao") == pa and o.get("pagamento")]


def conciliacao(c):
    A = preparar(c, "A")
    base = fc.documentos("A")
    troca = lambda nome, dados: [(n, dados if n == nome else b) for n, b in base]  # noqa: E731
    blocos = fc.ecac_blocos("A")
    # DARF de setembro sem composição + guia sem arrecadação + mesmo DAS em dois arquivos + DAS de agosto duplicado com outro número
    sem_comp = dict(blocos[5], comp=None)
    guia = dict(blocos[2], pago=None, numero="07.20.2609.7777777-7")
    dup = dict(blocos[1], numero="07.20.2608.8888888-8")
    docs = troca("03_pagamentos_ecac.pdf", fc.ecac_pdf("A", blocos=[blocos[0], blocos[1], blocos[3], blocos[4], sem_comp, guia, dup]))
    docs.append(("07_segunda_via_ecac.pdf", fc.ecac_pdf("A", blocos=[blocos[0]])))
    sol, p = rodar(c, A, docs)
    conc = p["conciliacao"]
    set_ = obrig(conc, "30/09/2026")
    registrar("CXR-08 DARF com dois tributos SEM composição: NECESSITA REVISÃO, nenhuma baixa (divisão não inventada)",
              any(o["tipo_documento"] == "DARF" and o["classificacao"] == "NECESSITA_REVISAO" and not o["lancamentos"] for o in set_),
              [(o["tipo_documento"], o["classificacao"], o["motivos"]) for o in set_])
    registrar("CXR-09 guia sem data de arrecadação: NECESSITA REVISÃO e nunca gera baixa",
              any(o["tipo_documento"] == "DAS" and o["classificacao"] == "NECESSITA_REVISAO" and "guia" in o["motivos"][0] and not o["lancamentos"]
                  for o in obrig(conc, "09/2026")), [(o["tipo_documento"], o["motivos"]) for o in obrig(conc, "09/2026")])
    fis = json.loads(sorted((servidor.RUNTIME / "execucoes" / sol).glob("caixinha_fiscal-*"))[-1].joinpath("resultado.json").read_text(encoding="utf-8"))
    jul_das = [o for o in obrig(conc, "07/2026")]
    registrar("CXR-10 o MESMO pagamento em dois documentos é UM pagamento (duplicidade documental registrada; uma única baixa)",
              len(jul_das) == 1 and len(jul_das[0]["lancamentos"]) == 1 and fis["repetidos_entre_documentos"], len(jul_das))
    ago = obrig(conc, "08/2026")
    registrar("CXR-11 mesmo período/código/valor com números diferentes: PAGAMENTO DUPLICADO (ambos), nenhuma baixa em dobro",
              len(ago) == 2 and all(o["classificacao"] == "PAGAMENTO_DUPLICADO" and not o["lancamentos"] for o in ago), [o["classificacao"] for o in ago])
    registrar("CXR-12 itens em revisão não geram lançamento e exigem ciência na aprovação",
              p["aprovacao_exige_ciencia_revisao"] and any("ciência" in x for x in p["aprovacao_impedimentos"]) is False
              and conc["resumo"]["revisao"] >= 4, conc["resumo"])
    # multa e juros
    atraso = dict(blocos[4], pago="25/09/2026", comp=[("1082", "CP SEGURADOS", D("550.00"), D("0"), D("11.00"), D("561.00")),
                                                     ("0561", "IRRF", D("402.35"), D("8.05"), D("0"), D("410.40"))], total=D("971.40"))
    sol2, p2 = rodar(c, A, troca("03_pagamentos_ecac.pdf", fc.ecac_pdf("A", blocos=[atraso])))
    l2 = [l for l in p2["conciliacao"]["lancamentos"] if l["origem"] == "CAIXINHA_TRIBUTOS"]
    registrar("CXR-13 pagamento com multa e juros: principal na conta do tributo e acréscimos nas contas de despesa configuradas; soma = pago",
              sorted((l["debito"]["codigo"], l["valor"]) for l in l2) == [("402", "550.00"), ("403", "402.35"), ("503", "8.05"), ("504", "11.00")]
              and sum(D(l["valor"]) for l in l2) == D("971.40"), [(l["debito"]["codigo"], l["valor"]) for l in l2])
    # situação fiscal com débito vencido para período pago; pagamento depois da competência
    itens = [("1082", "CP SEGURADOS", "08/2026", "20/09/2026", D("550.00"), "DEVEDOR")]
    nov = dict(blocos[2], pago="20/11/2026", numero="07.20.2609.0000099-9")
    docs3 = troca("04_situacao_fiscal.pdf", fc.situacao_fiscal_pdf("A", itens=itens))
    docs3 = [(n, fc.ecac_pdf("A", blocos=blocos[:2] + blocos[3:] + [nov]) if n == "03_pagamentos_ecac.pdf" else b) for n, b in docs3]
    sol3, p3 = rodar(c, A, docs3)
    c3 = p3["conciliacao"]
    sf = [v for v in c3["verificacoes"] if v["grupo"] == "E_SITUACAO_FISCAL" and v["resultado"] == "DIVERGENTE"]
    registrar("CXR-14 situação fiscal com débito vencido de período PAGO no e-CAC: divergência informada (não bloqueia a baixa comprovada)",
              sf and not sf[0]["bloqueia"] and any(o["classificacao"] == "PAGA_NAO_CONTABILIZADA" for o in obrig(c3, "31/08/2026")), sf[:1])
    registrar("CXR-15 pagamento depois do fim da competência: EM ABERTO na competência (a baixa pertence ao mês do pagamento)",
              any(o["classificacao"] == "EM_ABERTO" and o["data_pagamento"] == "2026-11-20" for o in c3["obrigacoes"]),
              [(o["classificacao"], o.get("data_pagamento")) for o in obrig(c3, "09/2026")])
    # razão × balancete divergentes (razão com lançamento a mais na conta INSS)
    fc.PARTIDAS_EXTRAS[:] = [("15/10/2026", "502", "402", D("10.00"), "AJUSTE FICTICIO INSS")]
    razao_div = fc.razao_pdf("A")
    fc.PARTIDAS_EXTRAS[:] = []
    sol4, p4 = rodar(c, A, troca("02_razao_2026.pdf", razao_div))
    c4 = p4["conciliacao"]
    inss = [l for l in c4["lancamentos"] if l["debito"]["codigo"] == "402"]
    registrar("CXR-16 razão × balancete divergentes na conta: verificação DIVERGENTE bloqueante e baixas da conta INCOMPLETAS (nada forçado)",
              any(v["conta"] == "402" and v["resultado"] == "DIVERGENTE" and v["bloqueia"] for v in c4["verificacoes"])
              and inss and all(l["status"] == "INCOMPLETO" for l in inss), [l["status"] for l in inss])
    # folha: resumo de competência sem provisão no razão
    sol5, p5 = rodar(c, A, troca("05_resumo_folha_2026-10.pdf", fc.folha_pdf("A", competencia="11/2026")))
    f5 = p5["conciliacao"]["folha"]
    registrar("CXR-17 folha: última competência do resumo sem provisão no razão → NECESSITA REVISÃO, nenhuma regularização",
              f5["situacao"] == "NECESSITA_REVISAO" and not [l for l in p5["conciliacao"]["lancamentos"] if l["origem"] == "CAIXINHA_FOLHA"],
              f5["motivos"])
    # Caixa credor projetado
    fc.PARTIDAS_EXTRAS[:] = [("30/10/2026", "291", "11", D("110000.00"), "DEVOLUCAO FICTICIA DE CAPITAL")]
    docs6 = [(n, b) for n, b in fc.documentos("A")]
    fc.PARTIDAS_EXTRAS[:] = []
    sol6, p6 = rodar(c, A, docs6)
    c6 = p6["conciliacao"]
    registrar("CXR-18 Caixa com saldo contábil projetado CREDOR: alerta e item para revisão (não bloqueia, exige ciência; nada forçado)",
              D(c6["caixa"]["saldo_projetado"]) < 0 and any(r["tipo"] == "ALERTA_CAIXA" for r in c6["revisao"])
              and any(v["grupo"] == "H_CAIXA" and v["resultado"] == "DIVERGENTE" and not v["bloqueia"] for v in c6["verificacoes"]),
              c6["caixa"]["saldo_projetado"])
    # razão ausente
    sol7, p7 = rodar(c, A, [(n, b) for n, b in base if "razao" not in n])
    c7 = p7["conciliacao"]
    registrar("CXR-19 razão ausente: alcance PARCIAL, pagamentos vão à revisão (não é possível saber se já foram baixados) e aprovação impedida",
              c7["alcance"]["parcial"] and c7["resumo"]["propostos"] == 0 and any("alcance parcial" in x for x in p7["aprovacao_impedimentos"]),
              c7["alcance"])
    # layouts conferidos com os arquivos reais (dados fictícios): comprovante e-CAC por página, balancete sem classificação,
    # razão do Domínio em planilha, resumo da folha por seções
    sol9, p9 = rodar(c, A, fc.documentos_layout_real("A"))
    c9 = p9["conciliacao"]
    esp = fc.esperado("A")
    leit = {d["tipo"]: (d["reconhecimento"], d["leitor"], d["pendencias"]) for d in p9["documentos"]}
    registrar("CXR-25 layouts reais reconhecidos pelo conteúdo e lidos sem pendência: comprovante e-CAC por página, balancete SEM "
              "classificação (hierarquia pelo recuo), razão do Domínio em planilha, resumo da folha por seções",
              len(leit) == 5 and all(v[0] == "RECONHECIDO" and not v[2] for v in leit.values())
              and leit["RAZAO"][1] == "RAZAO_SECOES_CONTA_V1" and leit["RESUMO_FOLHA_DOMINIO"][1].endswith("+SECOES"), leit)
    t9 = {x["conta"]["codigo"]: x for x in c9["tributos"]["por_conta"]}
    registrar("CXR-26 percurso com os layouts reais reproduz os valores esperados (tributos, folha e Caixa) sem itens em revisão",
              all(D(t9[k]["baixas_propostas"]) == esp["baixas_tributarias"][k] and D(t9[k]["saldo_restante"]) == esp["restantes"][k]
                  for k in ("401", "402", "403")) and D(c9["folha"]["baixa"]) == esp["baixa_folha"]
              and D(c9["caixa"]["saldo_projetado"]) == esp["caixa_projetado"] and c9["resumo"]["revisao"] == 0
              and c9["resumo"]["bloqueantes"] == 0, (c9["resumo"], {k: v["baixas_propostas"] for k, v in t9.items()}))
    # política DATA_PAGAMENTO (estrita): pagamentos de competência encerrada vão à revisão
    B = preparar(c, "B", politica="DATA_PAGAMENTO")
    sol8, p8 = rodar(c, B, fc.documentos("B"))
    c8 = p8["conciliacao"]
    fora = [o for o in c8["obrigacoes"] if o.get("pagamento") and o["data_pagamento"] < "2026-10-01" and o["classificacao"] != "PAGA_E_CONTABILIZADA"]
    dentro = [l for l in c8["lancamentos"] if l["origem"] == "CAIXINHA_TRIBUTOS"]
    registrar("CXR-20 política DATA_PAGAMENTO: competência encerrada nunca é alterada (revisão); pagamentos de outubro lançados na própria data",
              fora and all(o["classificacao"] == "NECESSITA_REVISAO" and "encerrada" in o["motivos"][-1] for o in fora)
              and dentro and all(l["data"] == "2026-10-20" for l in dentro), [(l["data"], l["valor"]) for l in dentro])
    # regras de outra empresa copiadas não valem
    shutil.copy2(AMB.clientes / A / "REGRAS-CAIXINHA.json", AMB.clientes / B / "REGRAS-CAIXINHA.json")
    st, cfg = c.j("GET", f"/api/empresas/{B}/caixinha?competencia=2026-10")
    registrar("CXR-21 REGRAS-CAIXINHA copiadas de outra empresa NÃO são aplicadas (empresa/CNPJ conferidos)",
              not cfg["avaliacao"]["contas"] and any("outra empresa" in x or "não corresponde" in x for x in cfg["avaliacao"]["problemas"]),
              cfg["avaliacao"]["problemas"][:1])
    # adulteração do conteúdo aprovado
    arq = AMB.clientes / A / "REGRAS-CAIXINHA.json"
    d = json.loads(arq.read_text(encoding="utf-8"))
    d["configuracao"]["contas"]["CAIXA_GERAL"] = "12"
    arq.write_text(json.dumps(d), encoding="utf-8")
    st, cfg = c.j("GET", f"/api/empresas/{A}/caixinha?competencia=2026-10")
    registrar("CXR-22 regra APROVADA alterada fora do aplicativo (sha256 do conteúdo diferente): NÃO aplicada",
              not cfg["avaliacao"]["configuracao"]["aplicavel"] and "sha256" in cfg["avaliacao"]["configuracao"]["motivo"],
              cfg["avaliacao"]["configuracao"]["motivo"])
    st_v, r_v = c.j("GET", "/api/caixinha/lote?competencia=2026-1")
    registrar("CXR-23 painel de lote valida a competência (AAAA-MM)", st_v == 400, st_v)
    st_d, r_d = c.j("GET", f"/api/solicitacoes/{sol}/caixinha/documento/../../CADASTRO")
    registrar("CXR-24 documento de origem só por identificador da ficha (nenhum caminho aceito)", st_d == 404, st_d)


def main():
    foto = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c = cc.Cliente(srv.server_address[1])
    try:
        leitores()
        conciliacao(c)
    finally:
        srv.shutdown()
        registrar("CXR-99 estado operacional intocado", foto_operacional() == foto)
    falhas = [r for r in resultados if not r[1]]
    for caso, ok, det in resultados:
        print(("PASSOU " if ok else "FALHOU ") + caso + ("" if ok else f" — {det}"))
    print(f"RESUMO: {len(resultados) - len(falhas)}/{len(resultados)} casos aprovados")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
