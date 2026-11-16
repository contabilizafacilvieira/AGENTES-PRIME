"""HOMOLOGAÇÃO LOCAL da Conciliação Caixinha com documentos REAIS de uma empresa piloto — sem tocar CLIENTES/, runtime, registro
ou LIBERADOS reais e sem gravar nada no Git.

O que faz (tudo numa pasta TEMPORÁRIA apagada ao final):
1. lê os documentos da pasta informada e localiza o balancete pelo CONTEÚDO; monta o plano (código reduzido, classificação,
   descrição, tipo e grupo pela árvore do plano) a partir dele;
2. sobe a API real em ambiente isolado, cadastra a empresa, define a rotina CAIXINHA, grava e confirma as regras (contas informadas,
   vínculos tributários sugeridos, política de datas e da folha) — confirmação válida SÓ dentro deste ambiente temporário;
3. envia os documentos, executa o fluxo completo (Documentos → Contábil → Fiscal → DP → Conciliação Caixinha) e imprime o painel:
   reconhecimento de cada documento (com pendências de leitura), tributos por conta, folha, Caixa, itens para revisão e lançamentos;
4. com --referencia, compara cada valor de referência com o processado (igualdade exata) e informa CONFERE / DIVERGE.
Os valores de referência são CONFERÊNCIA, nunca entrada: nada é fixado no sistema.

Uso (raiz AGENTES-PRIME):
  .venv/bin/python -I TESTES/CAIXINHA/homologar_caixinha_local.py --pasta <pasta com os 5 documentos> --empresa <CODIGO> \
      --nome "RAZÃO SOCIAL" --cnpj 00.000.000/0000-00 --competencia 2026-10 \
      --contas '{"CAIXA_GERAL":"<cod>","SIMPLES_NACIONAL":"<cod>","INSS":"<cod>","IRRF":"<cod>","PRO_LABORE":"<cod>"}' \
      [--politica-datas DATA_PAGAMENTO_OU_ULTIMO_DIA] [--referencia <ref.json>] [--relatorio <saida.json fora do Git>]
Formato de --referencia (exemplo; valores em texto decimal):
  {"tributos": {"<cod>": {"saldo": "0.00", "pagamentos": "0.00", "saldo_esperado": "0.00"}, ...},
   "total_baixas_tributarias": "0.00",
   "folha": {"saldo": "0.00", "ultimo_liquido": "0.00", "baixas": "0.00", "saldo_esperado": "0.00"},
   "caixa": {"saldo_inicial": "0.00", "baixas_tributarias": "0.00", "baixas_folha": "0.00", "saldo_projetado": "0.00"}}
"""
import argparse
import base64
import hashlib
import json
import sys
import threading
from decimal import Decimal as D
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")


def principal() -> int:
    p = argparse.ArgumentParser(description="Homologação local da Conciliação Caixinha (ambiente temporário isolado).")
    for a in ("pasta", "empresa", "nome", "cnpj", "competencia", "contas"):
        p.add_argument("--" + a, required=True)
    p.add_argument("--politica-datas", default="DATA_PAGAMENTO_OU_ULTIMO_DIA")
    p.add_argument("--politica-folha", default="ULTIMO_DIA_COMPETENCIA")
    p.add_argument("--janela-dias", type=int, default=3)
    p.add_argument("--dispensar-provisao-individualizada", action="store_true",
                   help="critério da empresa: provisão anterior ao razão não precisa ser individualizada (padrão: exigir)")
    p.add_argument("--referencia")
    p.add_argument("--relatorio")
    a = p.parse_args()
    pasta = Path(a.pasta).expanduser().resolve()
    arquivos = sorted(x for x in pasta.iterdir() if x.is_file() and x.suffix.lower() in (".pdf", ".txt", ".csv", ".xlsx", ".xlsm", ".xls"))
    if not arquivos:
        print("ERRO: nenhum documento na pasta.")
        return 2
    sys.path.insert(0, str(RAIZ / "TESTES"))
    sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
    import ambiente_isolado as ai
    amb = ai.criar("prime-homologacao-caixinha-")
    sys.path.insert(0, str(RAIZ / "API-LOCAL"))
    import servidor
    import cenario_complementar as cc
    import documentos_local as dl
    import leitura_pdf_local as lp
    import balancete_anterior as ba
    import regras_caixinha

    # 1. balancete pelo conteúdo → plano
    balancete = None
    for x in arquivos:
        if x.suffix.lower() != ".pdf":
            continue
        e = lp.ler(x)
        e.update(arquivo=x.name, sha256=hashlib.sha256(x.read_bytes()).hexdigest(), extensao=".pdf")
        if dl.classificar(e) == dl.TIPO_BALANCETE:
            balancete = x
            break
    if not balancete:
        print("ERRO: balancete (PDF do Domínio) não identificado pelo conteúdo na pasta.")
        return 2
    lido = ba.ler(balancete.name, balancete.read_bytes())
    linhas = ["codigo;classificacao;descricao;grupo;tipo"]
    for c in lido["contas"]:
        if c.get("codigo"):
            linhas.append(";".join([c["codigo"], c["classificacao"], c["descricao"].replace(";", ","), c.get("grupo_sugerido") or c.get("grupo") or "",
                                    "A" if c.get("tipo") == "ANALITICA" else "S"]))
    print(f"Balancete: {balancete.name} · {len(lido['contas'])} conta(s) extraída(s); limites: {lido.get('limites') or '—'}")
    srv = servidor.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c = cc.Cliente(srv.server_address[1])
    relatorio = {"empresa": a.empresa, "competencia": a.competencia, "documentos": [], "conferencia": []}
    try:
        def ok(resp, etapa):
            st, r = resp
            if st not in (200, 201, 202):
                raise SystemExit(f"ERRO em {etapa}: {st} {r}")
            return r
        ok(c.j("POST", "/api/empresas", {"id": a.empresa, "nome": a.nome, "cnpj": a.cnpj, "regime": "SIMPLES NACIONAL"}), "cadastro")
        prev = ok(c.j("POST", f"/api/empresas/{a.empresa}/previa", {"nome": "plano.csv", "conteudo": base64.b64encode("\n".join(linhas).encode()).decode()}), "plano")
        ok(c.j("POST", f"/api/empresas/{a.empresa}/plano", {"token": prev["token"], "salvar": True, "confirmado": True}), "plano")
        ok(c.j("POST", f"/api/empresas/{a.empresa}/caixinha-rotina", {"rotina": "CAIXINHA", "justificativa": "Homologação local.", "confirmado": True}), "rotina")
        contas = json.loads(a.contas)
        cfg = {"contas": contas, "tributos": regras_caixinha.TRIBUTOS_SUGERIDOS, "politica_datas": {"tributos": a.politica_datas},
               "criterios_baixa": {"janela_dias_baixa_razao": a.janela_dias, "exigir_provisao_identificada": not a.dispensar_provisao_individualizada},
               "competencia_desde": a.competencia, "competencia_ate": None}
        folha = {"regra": "MANTER_ULTIMO_LIQUIDO", "conta": "PRO_LABORE", "data_lancamento": {"politica": a.politica_folha},
                 "competencia_desde": a.competencia, "competencia_ate": None}
        ok(c.j("POST", f"/api/empresas/{a.empresa}/caixinha-regras", {"configuracao": cfg, "politica_folha": folha, "confirmado": True}), "regras")
        ok(c.j("POST", f"/api/empresas/{a.empresa}/piloto", {"frase": f"CONFIRMO PILOTO {a.empresa}"}), "piloto")
        for k in ("CONFIGURACAO", "POLITICA_FOLHA"):
            ok(c.j("POST", f"/api/empresas/{a.empresa}/caixinha-aprovar", {"chave": k, "frase": f"VALIDADO REGRA CAIXINHA {a.empresa} {k}",
                                                                             "confirmado": True}), "aprovação (ambiente temporário)")
        an, me = a.competencia.split("-")
        lote = ok(c.j("POST", "/api/lotes", {"empresa": a.empresa, "competencia": a.competencia, "fluxo": "CONCILIACAO_CAIXINHA",
                                             "instrucao": f"Homologação Caixinha {me}/{an}."}), "lote")["lote"]
        for x in arquivos:
            ok(c.enviar(lote, x.name, x.read_bytes()), f"envio de {x.name}")
        sol = ok(c.j("POST", f"/api/lotes/{lote}/iniciar", {"conferencia_humana": True}), "início")["sol"]
        cc.ocioso(servidor, ai.registro_isolado, limite=1800)
        painel = ok(c.j("GET", f"/api/solicitacoes/{sol}/caixinha"), "painel")
    finally:
        srv.shutdown()
    print(f"\n== {sol} · estado {painel['estado']}")
    for e, x in painel["plano"].items():
        print(f"  etapa {e}: {x['situacao']}" + (f" — {x['falha']}" if x.get("falha") else ""))
    print("\n== DOCUMENTOS (identificados pelo conteúdo)")
    for d in painel["documentos"]:
        print(f"  {d['nome']}: {d['tipo']} · {d['reconhecimento']} · leitor {d.get('leitor')} · CNPJ {d.get('cnpj')} · período "
              f"{d.get('periodo') or d.get('competencia')} · emissão {d.get('emissao')}")
        for x in d.get("pendencias") or []:
            print(f"     ! {x}")
        relatorio["documentos"].append({k: d.get(k) for k in ("nome", "tipo", "reconhecimento", "leitor", "pendencias", "dados")})
    conc = painel.get("conciliacao")
    if not conc:
        print("\nConciliação não registrada: veja as falhas das etapas acima.")
        return 1
    print("\n== TRIBUTOS")
    for t in conc["tributos"]["por_conta"]:
        print(f"  {t['conta']['codigo']} {t['conta']['descricao']}: saldo {t['saldo_contabil']} · pagos {t['pagamentos_identificados']} · já contab. "
              f"{t['ja_contabilizado']} · baixas {t['baixas_propostas']} · restante {t['saldo_restante']} · divergências {t['divergencias']}")
    print(f"  TOTAL baixas tributárias: {conc['tributos']['baixas_propostas']}")
    f = conc.get("folha") or {}
    print(f"\n== FOLHA: saldo {f.get('saldo_contabil')} · último líquido {(f.get('ultimo') or {}).get('liquido')} "
          f"({(f.get('ultimo') or {}).get('competencia')}) · baixas {f.get('baixa')} · esperado {f.get('saldo_esperado')} · {f.get('situacao')} "
          f"{'; '.join(f.get('motivos') or [])}")
    x = conc.get("caixa") or {}
    print(f"\n== CAIXA: inicial {x.get('saldo_inicial')} · tributárias {x.get('baixas_tributarias')} · folha {x.get('baixas_folha')} · "
          f"projetado {x.get('saldo_projetado')}")
    print(f"\n== REVISÃO HUMANA ({len(conc['revisao'])})")
    for r in conc["revisao"]:
        print(f"  [{r['tipo']}] {r['problema']}")
    print("\n== VERIFICAÇÕES NÃO CONFERIDAS")
    for v in conc["verificacoes"]:
        if v["resultado"] not in ("CONFERIDO", "NAO_APLICAVEL"):
            print(f"  {v['resultado']} · {v['titulo']} · {v.get('detalhe') or ''}")
    print(f"\n== LANÇAMENTOS ({conc['resumo']['propostos']} proposto(s), {conc['resumo']['incompletos']} incompleto(s))")
    for l in conc["lancamentos"]:
        print(f"  {l['status']} {l['data']} D {l['debito']['codigo']} C {(l['credito'] or {}).get('codigo')} {l['valor']} · {l['historico']}")
    falhas = 0
    if a.referencia:
        ref = json.loads(Path(a.referencia).expanduser().read_text(encoding="utf-8"))
        por = {t["conta"]["codigo"]: t for t in conc["tributos"]["por_conta"]}
        pares = []
        for cod, v in (ref.get("tributos") or {}).items():
            t = por.get(cod) or {}
            pares += [(f"tributo {cod} saldo", v.get("saldo"), t.get("saldo_contabil")),
                      (f"tributo {cod} pagamentos (baixas)", v.get("pagamentos"), t.get("baixas_propostas")),
                      (f"tributo {cod} saldo esperado", v.get("saldo_esperado"), t.get("saldo_restante"))]
        pares.append(("total das baixas tributárias", ref.get("total_baixas_tributarias"), conc["tributos"]["baixas_propostas"]))
        rf = ref.get("folha") or {}
        pares += [("folha saldo", rf.get("saldo"), f.get("saldo_contabil")), ("folha último líquido", rf.get("ultimo_liquido"), (f.get("ultimo") or {}).get("liquido")),
                  ("folha baixas", rf.get("baixas"), f.get("baixa")), ("folha saldo esperado", rf.get("saldo_esperado"), f.get("saldo_esperado"))]
        rc = ref.get("caixa") or {}
        pares += [("caixa saldo inicial", rc.get("saldo_inicial"), x.get("saldo_inicial")), ("caixa baixas tributárias", rc.get("baixas_tributarias"), x.get("baixas_tributarias")),
                  ("caixa baixas folha", rc.get("baixas_folha"), x.get("baixas_folha")), ("caixa saldo projetado", rc.get("saldo_projetado"), x.get("saldo_projetado"))]
        print("\n== CONFERÊNCIA COM A REFERÊNCIA (igualdade exata)")
        for nome, esperado, obtido in pares:
            if esperado is None:
                continue
            confere = obtido is not None and D(str(esperado)) == D(str(obtido))
            falhas += not confere
            print(f"  {'CONFERE' if confere else 'DIVERGE'} · {nome}: referência {esperado} · processado {obtido}")
            relatorio["conferencia"].append({"item": nome, "referencia": esperado, "processado": obtido, "confere": confere})
    if a.relatorio:
        destino = Path(a.relatorio).expanduser().resolve()
        if destino.is_relative_to(RAIZ):
            print("AVISO: relatório NÃO gravado dentro do repositório (dados reais fora do Git). Informe outro caminho.")
        else:
            relatorio.update(painel=painel)
            destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nRelatório: {destino}")
    print("\nAmbiente temporário descartado ao final. Nada foi gravado em CLIENTES/, runtime, LIBERADOS ou no Git.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(principal())
