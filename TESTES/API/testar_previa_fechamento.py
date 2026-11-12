"""MINI FECHAMENTO FICTÍCIO COMPLETO + PRÉVIA DO FECHAMENTO (FECH-01..26). Dados 100% FICTÍCIOS, servidor REAL em ambiente ISOLADO.

Documentos → classificação/roteamento por departamento (upload NÃO inicia o fechamento) → "Preparar fechamento" (tentativa +
pacote) → Fiscal → DP → Financeiro → CHECKPOINT → (autorização) → Contábil → Conciliação → PRÉVIA PRONTA. Nenhum lançamento
efetivado. Cobre: adapters/contratos, intercâmbio (candidatos, nunca confirmação), conciliação do balanço, impostos, pendências
(problema/impacto/o que fazer/responsável), proveniência, fail-closed e identificação do ambiente.

Uso (a partir da raiz AGENTES-PRIME):  .venv/bin/python -I TESTES/API/testar_previa_fechamento.py
"""
import hashlib
import json
import os
import sys
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(RAIZ / "TESTES"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import ambiente_isolado as ai  # noqa: E402
AMB = ai.criar("prime-previa-fech-")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402
import amostra_ficticia  # noqa: E402
import adaptadores_fechamento as af  # noqa: E402
import documentos_local as dl  # noqa: E402
import intercambio as ic  # noqa: E402
import reprocessamento as rp  # noqa: E402
import cenario_complementar as cc  # noqa: E402
import cenario_fechamento as cf  # noqa: E402
from executar_gate import foto_operacional  # noqa: E402

resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:400]))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def arvore(p):
    p = Path(p)
    return {x.relative_to(p).as_posix(): sha(x) for x in p.rglob("*") if x.is_file() and not x.name.endswith(".trava")} if p.exists() else {}


def reg(sol):
    return ai.registro_isolado()["solicitacoes"][sol]


def pastas(sol, prefixo):
    return sorted(p.name for p in (servidor.RUNTIME / "execucoes" / sol).glob(f"{prefixo}-*"))


def main():
    foto = foto_operacional()
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c = cc.Cliente(srv.server_address[1])
    espera = lambda: cc.ocioso(servidor, ai.registro_isolado)  # noqa: E731
    previa = lambda sol: c.j("GET", f"/api/solicitacoes/{sol}/previa-fechamento")[1]  # noqa: E731
    try:
        amostra_ficticia.preparar(servidor.RUNTIME)
        E_ = lambda sol: servidor.RUNTIME / "execucoes" / sol  # noqa: E731

        # ---------------------------------------------------------------- upload único: recebe e classifica, NÃO executa
        sol = cf.abrir_fechamento(c, cf.A, cf.documentos("A"))
        espera()
        s = reg(sol)
        p0 = previa(sol)
        dep = {d["nome"].split("_", 2)[-1]: d["departamento"] for d in p0["documentos"]["itens"]}
        cl = p0["documentos"]["classificacao"]
        registrar("FECH-01 classificação por departamento: NF (entrada e saída) e impostos → Fiscal; extrato/relação → Financeiro; "
                  "balancete e razão → Contábil; folha → DP; book e confirmações → Conciliação",
                  dep.get("nfse_555_beta_entrada.txt") == "FISCAL" and dep.get("nfse_102_gama.txt") == "FISCAL" and dep.get("guia_iss_2026-09.txt") == "FISCAL"
                  and dep.get("extrato_001_55555-5_2026-10.csv") == "FINANCEIRO" and dep.get("balancete_2026-10.pdf") == "CONTABIL"
                  and dep.get("razao_2026-10.csv") == "CONTABIL" and dep.get("resumo_folha_2026-10.txt") == "DP"
                  and dep.get("book_conciliacao_2026-10.xlsx") == "CONCILIACAO" and cl["FISCAL"]["categorias"].get("Notas fiscais") == 3
                  and cl["CONTABIL"]["categorias"] == {"Balancete": 1, "Razão": 1} and "A_CONFERIR" not in cl, json.dumps(cl, ensure_ascii=False))
        registrar("FECH-02 upload do fechamento NÃO inicia nenhuma área (plano vazio, nenhuma execução, aguardando o Supervisor)",
                  s["estado"] == "AGUARDANDO_SUPERVISOR" and not s.get("plano_etapas") and not any(pastas(sol, x) for x in ("financeiro", "fiscal", "dp", "bancos", "conciliacao"))
                  and not rp.listar(servidor.RUNTIME, sol), s.get("estado"))
        registrar("FECH-03 prévia antes de preparar: status geral NÃO INICIADO, Fiscal/Financeiro/Contábil/DP 'Não iniciado', nenhum lançamento",
                  p0["status_geral"] == "NAO_INICIADO" and all(p0["departamentos"][k]["status"] == "NAO_INICIADO" for k in ("FISCAL", "FINANCEIRO", "CONTABIL", "DP"))
                  and p0["lancamentos_efetivados"] == 0 and "Preparar fechamento" in p0["departamentos"]["FISCAL"]["acao_necessaria"],
                  json.dumps({k: v["status"] for k, v in p0["departamentos"].items()}))
        rec = {d["tipo"]: d for d in p0["documentos"]["itens"] if d["tipo"] in dl.TIPOS_CONTABEIS}
        registrar("FECH-04 adapters: balancete (PDF colunas), razão (tabela) e book (planilha) reconhecidos com contrato normalizado",
                  rec[dl.TIPO_BALANCETE]["contrato"] == "BALANCETE_NORMALIZADO_V1" and rec[dl.TIPO_RAZAO]["contrato"] == "RAZAO_CONTABIL_NORMALIZADO_V1"
                  and rec[dl.TIPO_BOOK]["contrato"] == "BOOK_CONCILIACAO_CONTABIL_V1"
                  and all(d["situacao"] == af.ADAPTER_EXISTENTE for d in p0["documentos"]["itens"]),
                  json.dumps({k: (v["situacao"], v.get("adapter")) for k, v in rec.items()}, ensure_ascii=False))
        bal0 = {x["conta"]: (x["status"], x["departamento_responsavel"]) for x in p0["conciliacao_balanco"]["contas"]}
        esperado = {"1.1.1.01": ("CONCILIADA", "FINANCEIRO"), "1.1.2.01": ("DIVERGENTE", "FISCAL"), "2.1.1.01": ("SEM_COMPOSICAO", "FISCAL"),
                    "2.1.2.02": ("CONCILIADA", "DP"), "2.1.2.03": ("COMPOSICAO_INCOMPLETA", "DP"), "2.1.2.04": ("SEM_COMPOSICAO", "FISCAL"),
                    "2.1.4.01": ("CONCILIADA", "FISCAL"), "2.3.1.01": ("CONCILIADA", "CONTABIL"), "4.2.1.02": ("DIVERGENTE", "CONTABIL")}
        registrar("FECH-05 conciliação do balanço (book × balancete × razão): conciliada, divergente, sem composição, composição incompleta e "
                  "razão ≠ balancete, cada uma com o departamento RESPONSÁVEL (não a Conciliação só por ter detectado)",
                  bal0 == esperado, json.dumps(bal0, ensure_ascii=False))
        div = next(x for x in p0["conciliacao_balanco"]["contas"] if x["conta"] == "1.1.2.01")
        registrar("FECH-06 divergência explica PROBLEMA, IMPACTO e O QUE FAZER (sem ajuste automático)",
                  "500.00" in div["problema"] and div["impacto"] and "Nenhum ajuste automático" in div["o_que_fazer"], div)

        man = E_(sol) / "documentos-local.json"
        man_antes = sha(man)
        st, r = cf.preparar_fechamento(c, sol)
        espera()
        s = reg(sol)
        t = rp.ativa(servidor.RUNTIME, sol)
        registrar("FECH-07 'Preparar fechamento': plano Fiscal → DP → Financeiro → Contábil → Conciliação a partir do pacote ancorado; "
                  "manifesto original NÃO reescrito",
                  st == 202 and r.get("resultado") == "FECHAMENTO_PREPARADO"
                  and r.get("reexecuta") == ["FISCAL", "DP", "FINANCEIRO", "BANCOS", "CONTABILIDADE_FISCAL", "CONTABILIDADE_DP", "CONCILIACAO"]
                  and sha(man) == man_antes, r)
        sit = {e["etapa"]: e["situacao"] for e in s["plano_etapas"]}
        registrar("FECH-08 CHECKPOINT após o Financeiro: Fiscal, DP e Financeiro concluídos; Contábil e Conciliação PENDENTES e sem execução; "
                  "tentativa PAUSADA",
                  sit == {"FISCAL": "CONCLUIDA", "DP": "CONCLUIDA", "FINANCEIRO": "CONCLUIDA", "BANCOS": "PENDENTE", "CONTABILIDADE_FISCAL": "PENDENTE",
                          "CONTABILIDADE_DP": "PENDENTE", "CONCILIACAO": "PENDENTE"} and s["estado"] == "AGUARDANDO_SUPERVISOR"
                  and not pastas(sol, "bancos") and not pastas(sol, "contabilfiscal") and not pastas(sol, "contabdp") and not pastas(sol, "conciliacao")
                  and t and t["status"] == "PAUSADA" and s["checkpoint"]["situacao"] == "AGUARDANDO_AUTORIZACAO", json.dumps(sit))
        p1 = previa(sol)
        registrar("FECH-09 prévia no checkpoint: AGUARDANDO SUPERVISOR; Financeiro aguarda autorização; Contábil 'Aguardando Supervisor'; "
                  "decisão 'Autorizar a continuação' em primeiro lugar",
                  p1["status_geral"] == "AGUARDANDO_SUPERVISOR" and p1["departamentos"]["FINANCEIRO"]["status"] == "AGUARDANDO_SUPERVISOR"
                  and p1["departamentos"]["CONTABIL"]["status"] == "AGUARDANDO_SUPERVISOR"
                  and p1["supervisor"]["decisoes_necessarias"][0]["decisao"].startswith("Autorizar a continuação")
                  and p1["checkpoints"][-2]["proximas_etapas"] == ["Contábil (bancos)", "Contábil (fiscal)", "Contábil (DP)", "Conciliação"],
                  json.dumps(p1["checkpoints"], ensure_ascii=False)[:300])
        # ---------------------------------------------------------------- Financeiro consultando as outras áreas
        ctx = ic.contexto(servidor.RUNTIME, servidor.coordenador.CLIENTES, ai.registro_isolado()["solicitacoes"], sol)
        fx = ic.analisar_financeiro(ctx)
        por_desc = {m["descricao"]: m for m in fx["movimentos"]}
        sal = por_desc["PAGTO SALARIOS FP-2026-10"]["candidatos"]
        iss = por_desc["PAGTO ISS 09/2026 ISS-2026-09"]["candidatos"]
        gama = por_desc["TED RECEBIDA GAMA COMERCIO NF 102"]["candidatos"]
        registrar("FECH-10 Financeiro consulta DP, Fiscal e Fiscal-NF: salários ↔ folha (DP), ISS ↔ guia (Fiscal), TED ↔ NFS-e 102 de saída, "
                  "com critérios registrados (valor exato + número do documento)",
                  any(x["departamento"] == "DP" and "NUMERO_DOCUMENTO" in x["criterios"] for x in sal)
                  and any(x["departamento"] == "FISCAL" and x["tipo"] == "OBRIGACAO" and "NUMERO_DOCUMENTO" in x["criterios"] for x in iss)
                  and any(x["tipo"] == "DOCUMENTO_FISCAL" and "NUMERO_DOCUMENTO" in x["criterios"] for x in gama),
                  json.dumps([sal, iss], ensure_ascii=False)[:400])
        todos = [x for m in fx["movimentos"] for x in m["candidatos"]]
        fin_res = json.loads((E_(sol) / pastas(sol, "financeiro")[-1] / "resultado.json").read_text(encoding="utf-8"))
        registrar("FECH-11 consulta gera CANDIDATOS, nunca confirmação: situação sempre CANDIDATO e o resultado do Financeiro não é alterado",
                  todos and all(x["situacao"] == "CANDIDATO" for x in todos)
                  and sha(E_(sol) / pastas(sol, "financeiro")[-1] / "resultado.json") == reg(sol)["financeiro"][-1]["resultado_sha256"], len(todos))
        registrar("FECH-12 valor EXATO é obrigatório: tarifa (45,00) sem candidato; nenhum candidato com valor diferente do movimento",
                  not por_desc["TARIFA BANCARIA PACOTE"]["candidatos"]
                  and all(ic.dec(x["valor"]) == ic.dec(m["valor"]) for m in fx["movimentos"] for x in m["candidatos"]), "")
        mov_teste = {"id": "MOV-T", "valor": "999.99", "data": "2026-10-10", "direcao": "DEBITO", "descricao": "PAGTO SALARIOS FP-2026-10 GUIA ISS-2026-09"}
        registrar("FECH-13 texto parecido sozinho não gera candidato (mesmo histórico, valor diferente)", ic.candidatos(mov_teste, ctx["itens"]) == [], "")

        # ---------------------------------------------------------------- continuação autorizada → prévia pronta
        fin_antes = pastas(sol, "financeiro")
        st, r = c.j("POST", f"/api/solicitacoes/{sol}/continuar-apos-financeiro", {"justificativa": "Revisei o Financeiro (fictício).", "confirmado": True})
        espera()
        s = reg(sol)
        t2 = next((x for x in rp.listar(servidor.RUNTIME, sol) if x["numero"] == (t or {}).get("numero")), {"status": "SEM_TENTATIVA_PAUSADA"})
        registrar("FECH-14 continuação: MESMA tentativa, Financeiro não repetido, Contábil (bancos, fiscal, DP) e Conciliação uma vez cada; "
                  "tentativa CONCLUIDA",
                  st == 202 and pastas(sol, "financeiro") == fin_antes and pastas(sol, "bancos") == ["bancos-1"]
                  and pastas(sol, "contabilfiscal") == ["contabilfiscal-1"] and pastas(sol, "contabdp") == ["contabdp-1"]
                  and pastas(sol, "conciliacao") == ["conciliacao-1"] and t2["status"] == "CONCLUIDA" and len(rp.listar(servidor.RUNTIME, sol)) == 1,
                  (pastas(sol, "financeiro"), t2["status"]))
        liberados = arvore(Path(os.environ["AGENTES_PRIME_LIBERADOS"]))
        p2 = previa(sol)
        registrar("FECH-15 prévia final: PRÉVIA PRONTA (checkpoint final atingido), nenhum lançamento efetivado, nada aprovado nem liberado",
                  p2["status_geral"] == "PREVIA_PRONTA" and p2["checkpoints"][-1]["situacao"] == "ATINGIDO" and p2["lancamentos_efetivados"] == 0
                  and p2["departamentos"]["CONTABIL"]["lancamentos_efetivados"] == 0 and not s.get("aprovacao") and not liberados
                  and s["estado"] == "AGUARDANDO_SUPERVISOR", p2["status_geral"])
        props = p2["departamentos"]["CONTABIL"]["lista_propostas"]
        registrar("FECH-16 Contábil recebe propostas de bancos, fiscal e DP (débito/crédito/valor/histórico/status), todas aguardando o Supervisor",
                  {x["etapa"] for x in props} == {"BANCOS", "CONTABILIDADE_FISCAL", "CONTABILIDADE_DP"}
                  and all(x["status"] in ("PROPOSTO", "PROPOSTO_PARA_CONFERENCIA", "INCOMPLETO") for x in props)
                  and p2["departamentos"]["CONTABIL"]["aguardando_supervisor"] == p2["departamentos"]["CONTABIL"]["completas"] > 0,
                  {x["etapa"]: x["status"] for x in props})
        imp = {(o["tributo"] or o["codigo"]): o for o in p2["impostos"]["obrigacoes"]}
        registrar("FECH-17 impostos: apurações ISS/PIS/COFINS (Fiscal) com provisão proposta; guia ISS 09/2026 e salários com pagamento "
                  "identificado (candidato); tributo da guia NÃO inventado (somente código + pendência)",
                  all(imp[k]["provisao_proposta"] for k in ("ISS", "PIS", "COFINS")) and imp["1406"]["pagamento_identificado"]
                  and imp["1406"]["tributo"] is None and any("Tributo não identificado" in x for x in imp["1406"]["pendencias"])
                  and imp["Salários líquidos a pagar"]["departamento"] == "DP" and imp["Salários líquidos a pagar"]["pagamento_identificado"],
                  json.dumps({k: (v["provisao_proposta"], v["pagamento_identificado"]) for k, v in imp.items()}, ensure_ascii=False))
        campos = ("classificacao", "departamento", "responsavel_esperado", "problema", "impacto", "o_que_fazer", "origem", "empresa", "competencia")
        registrar("FECH-18 toda pendência tem PROBLEMA, IMPACTO, O QUE FAZER, classificação (INFORMATIVO/ATENÇÃO/BLOQUEIO), departamento "
                  "responsável, origem, empresa e competência",
                  p2["pendencias"] and all(all(x.get(k) for k in campos) and x["classificacao"] in ("INFORMATIVO", "ATENCAO", "BLOQUEIO")
                                           and x["empresa"] == cf.A and x["competencia"] == cf.COMPETENCIA for x in p2["pendencias"]),
                  len(p2["pendencias"]))
        regs = reg(sol)
        ctx2 = ic.contexto(servidor.RUNTIME, servidor.coordenador.CLIENTES, ai.registro_isolado()["solicitacoes"], sol)
        registrados = {x["resultado_sha256"] for k in ("fiscal", "dp", "bancos", "contabilfiscal", "contabdp") for x in regs.get(k, [])}
        verificados = [it for it in ctx2["itens"] if it["proveniencia"]["departamento"] != "CONCILIACAO"]
        prov_ok = all(it["proveniencia"]["empresa"] == cf.A and it["proveniencia"]["competencia"] == cf.COMPETENCIA and it["proveniencia"]["sol"] == sol
                      and it["proveniencia"]["resultado_sha256"] in registrados for it in verificados)
        tipos_v = {it["tipo"] for it in verificados}
        registrar("FECH-19 proveniência ('de onde veio esse valor?'): empresa, competência, SOL, departamento, documento, registro e sha256 "
                  "do resultado registrado pelo Coordenador (NF, obrigações e propostas contábeis)",
                  prov_ok and {"DOCUMENTO_FISCAL", "OBRIGACAO", "PROPOSTA_CONTABIL"} <= tipos_v
                  and all(x["proveniencia"].get("registro") for x in props), sorted(tipos_v))
        registrar("FECH-20 departamentos na prévia final: Fiscal/DP/Contábil com pendências ou aguardando; Conciliação com pendências "
                  "detectadas para outras áreas; ação necessária sempre preenchida",
                  all(p2["departamentos"][k]["status"] in ("COM_PENDENCIAS", "AGUARDANDO_SUPERVISOR", "CONCLUIDO") for k in af.DEPARTAMENTOS)
                  and p2["departamentos"]["CONCILIACAO"]["pendencias_detectadas_para_outros"] > 0
                  and all(p2["departamentos"][k]["acao_necessaria"] for k in af.DEPARTAMENTOS),
                  json.dumps({k: v["status"] for k, v in p2["departamentos"].items()}))

        # ---------------------------------------------------------------- fail-closed, somente leitura, ambiente
        antes = (arvore(servidor.RUNTIME), arvore(servidor.coordenador.CLIENTES), sha(os.environ["AGENTES_PRIME_REGISTRO_SOL"]))
        previa(sol)
        depois = (arvore(servidor.RUNTIME), arvore(servidor.coordenador.CLIENTES), sha(os.environ["AGENTES_PRIME_REGISTRO_SOL"]))
        registrar("FECH-21 a prévia é SOMENTE LEITURA (runtime, CLIENTES e registro idênticos antes e depois)", antes == depois, "")
        alvo = E_(sol) / "fiscal-1" / "resultado.json"
        original = alvo.read_bytes()
        try:
            alvo.write_bytes(original.replace(b'"SIMULACAO"', b'"SIMULACAO" ', 1))
            p3 = previa(sol)
            registrar("FECH-22 resultado alterado depois do registro é RECUSADO pelo intercâmbio (BLOQUEIO visível; nada parcial usado)",
                      not any(o["departamento"] == "FISCAL" for o in p3["impostos"]["obrigacoes"]) and p3["departamentos"]["FISCAL"]["notas_fiscais"] == []
                      and any("FISCAL: resultado registrado não encontrado ou alterado" in x["problema"] for x in p3["pendencias"]), "")
        finally:
            alvo.write_bytes(original)
        item = {"arquivo": "x/razao.txt", "sha256": "0" * 64, "tipo": dl.TIPO_RAZAO, "encaminhamento": {"area": "CONTABIL", "tipo": dl.TIPO_RAZAO}}
        extraido = {"leitura": "EXTRAIDO_PDF", "conteudo": {"paginas": [{"texto": "RAZAO ANALITICO\nDATA HISTORICO DEBITO CREDITO\n01/10 X 1,00"}]}}
        r_novo = af.reconhecer(item, extraido, servidor.coordenador.CLIENTES, cf.A)
        registrar("FECH-23 layout desconhecido de razão (PDF) → 'RECONHECIDO · LAYOUT NOVO — ADAPTER NECESSÁRIO' (nenhum valor lido)",
                  r_novo["situacao"] == af.LAYOUT_NOVO and "normalizado" not in r_novo, r_novo)
        r_nao = af.reconhecer({"arquivo": "x/y.pdf", "sha256": "1" * 64, "tipo": "Tipo a conferir; sem interpretação automática",
                               "encaminhamento": {"area": None}}, {}, servidor.coordenador.CLIENTES, cf.A)
        registrar("FECH-24 documento sem área → 'NÃO RECONHECIDO · AGUARDANDO SUPERVISOR' (destino não presumido)",
                  r_nao["situacao"] == af.NAO_RECONHECIDO and r_nao["departamento"] == "A_CONFERIR", r_nao)
        nf = {"arquivo": "nf.txt", "leitura": "EXTRAIDO_TEXTO", "conteudo": {"texto": "NOTA FISCAL\nRAZAO SOCIAL: X\nDEBITO CREDITO HISTORICO"}}
        registrar("FECH-25 'RAZÃO SOCIAL' numa nota não vira razão contábil (rótulo do documento vence menções)",
                  dl.classificar(nf) == "Possível nota fiscal", dl.classificar(nf))
        st_e, est = c.j("GET", "/api/estado")
        _, _, pagina = c.http("GET", "/", token=False)
        registrar("FECH-26 identificação do ambiente: servidor padrão declara AMBIENTE REAL (API e página)",
                  est.get("ambiente") == "REAL" and b'name="prime-ambiente" content="REAL"' in pagina, est.get("ambiente"))

        # ---------------------------------------------------------------- upload múltiplo de complemento ao fechamento
        sol2 = cf.abrir_fechamento(c, cf.A, [d for d in cf.documentos("A") if d[0].startswith("01_")])
        espera()
        st, r = c.j("POST", f"/api/solicitacoes/{sol2}/complementos", {"motivo": "Documentos contábeis recebidos depois (fictício)."})
        for nome, conteudo in [d for d in cf.documentos("A") if d[0][:2] in ("20", "21", "22")]:
            c.enviar(r["lote"], nome, conteudo)
        st2, r2 = c.j("POST", f"/api/solicitacoes/{sol2}/complementos/{r['lote']}/concluir", {"confirmado": True})
        areas = sorted(d["area"] for d in r2["complemento"]["documentos"])
        registrar("FECH-27 'Adicionar documentos ao fechamento' com VÁRIOS arquivos num envio: classificados (Contábil ×2, Conciliação) e "
                  "nenhuma etapa iniciada",
                  st2 == 201 and areas == ["CONCILIACAO", "CONTABIL", "CONTABIL"] and not reg(sol2).get("plano_etapas") and not pastas(sol2, "financeiro"),
                  areas)
        # ---------------------------------------------------------------- decisões VIGENTES da Central entram na prévia
        import previa_fechamento as pf  # noqa: E402
        cc.preparar_empresa(servidor, servidor.RUNTIME)
        sol3, _ = c.abrir_sol([("relatorio.xlsx", cc.relatorio_xlsx())])
        espera()
        lote = c.complementar(sol3, "extrato.pdf", cc.extrato_pdf())
        c.j("POST", f"/api/solicitacoes/{sol3}/complementos/{lote}/concluir", {"confirmado": True})
        c.j("POST", f"/api/solicitacoes/{sol3}/reprocessar", {"confirmado": True, "motivo": "Teste fictício da Central.", "solicitante": "Supervisor"})
        c.j("POST", f"/api/solicitacoes/{sol3}/retomar-rota-financeira", {"justificativa": "Teste fictício.", "confirmado": True})
        espera()
        p_bloq = previa(sol3)
        bloqueio = [x for x in p_bloq["pendencias"] if x["departamento"] == "FINANCEIRO" and x["classificacao"] == "BLOQUEIO"]
        registrar("FECH-29 lote bloqueado pelo Financeiro, sem decisões na Central: BLOQUEIO visível e decisão 'Revisar associações na Central'",
                  bloqueio and any(d["decisao"].startswith("Revisar associações") for d in p_bloq["supervisor"]["decisoes_necessarias"])
                  and p_bloq["departamentos"]["FINANCEIRO"]["central"]["bloqueios_restantes"] > 0, p_bloq["departamentos"]["FINANCEIRO"]["central"])
        registrar("FECH-31 execução anterior interrompida (Financeiro bloqueado) NÃO é 'prévia pronta': status 'execução interrompida', "
                  "checkpoint final não atingido e decisão 'Reprocessar o fechamento'",
                  p_bloq["status_geral"] == "EXECUCAO_INTERROMPIDA" and p_bloq["checkpoints"][-1]["situacao"] == "NAO_ATINGIDO"
                  and any(d["decisao"].startswith("Reprocessar") for d in p_bloq["supervisor"]["decisoes_necessarias"]), p_bloq["status_geral"])
        s3 = reg(sol3)
        fin3, _ = ic.resultado_registrado(servidor.RUNTIME, sol3, s3, "FINANCEIRO")
        ids = [m["rastreio_bancario"]["id"] for m in fin3["movimentos"] if m.get("rastreio_bancario")]
        man3, ext3 = servidor.pacote_vigente(E_(sol3), s3)
        central = {"liberados": ids, "resumo": {"movimentos_bancarios": len(ids), "movimentos_confirmados": len(ids), "bloqueios_restantes": 0}}
        p_ok = pf.montar(servidor.RUNTIME, servidor.coordenador.CLIENTES, sol3, s3, man3, ext3, registro=ai.registro_isolado()["solicitacoes"],
                         central=central)
        fin_p = [x for x in p_ok["pendencias"] if x["departamento"] == "FINANCEIRO"]
        registrar("FECH-30 com as decisões vigentes do Supervisor cobrindo todos os movimentos, o bloqueio da execução anterior vira INFORMATIVO "
                  "(resolvido na Central; a próxima tentativa reflete) e nenhum movimento aparece como pendente",
                  ids and not any(x["classificacao"] == "BLOQUEIO" for x in fin_p)
                  and [x["classificacao"] for x in fin_p if x["problema"].startswith("Bloqueio registrado")] == ["INFORMATIVO"]
                  and not any(x["problema"].startswith("Movimento sem suporte") for x in fin_p)
                  and p_ok["departamentos"]["FINANCEIRO"]["pendentes"] == 0
                  and not any(d["decisao"].startswith("Revisar associações") for d in p_ok["supervisor"]["decisoes_necessarias"]),
                  [(x["classificacao"], x["problema"][:90]) for x in fin_p])
    finally:
        srv.shutdown()
    registrar("FECH-28 estado operacional real (CLIENTES/, registro, ordem ativa, LIBERADOS/) intocado", foto == foto_operacional(), "")
    falhas = [r for r in resultados if not r[1]]
    for caso, ok, det in resultados:
        print(("PASSOU " if ok else "FALHOU ") + caso + ("" if ok else f" — {det}"))
    print(f"\nTOTAL: {len(resultados)} · PASSARAM: {len(resultados) - len(falhas)} · FALHARAM: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
