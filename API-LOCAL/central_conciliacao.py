"""Central de Revisão do Supervisor — conciliação financeira banco × relatório (leitura para a tela + decisões).

Duas fontes, mesma lógica:
- SOL real: última tentativa CONCLUÍDA do Financeiro (financeiro-N/resultado.json, campo conciliacao_financeira). Decisões em
  <runtime>/execucoes/<SOL>/supervisor-conciliacao/decisoes.json (camada separada; o resultado do Financeiro não é tocado).
- DEMONSTRAÇÃO: cenário 100% FICTÍCIO montado aqui e conciliado pelo MOTOR REAL (política V1). Fica numa pasta PRÓPRIA, fora do
  runtime operacional (sem SOL, sem empresa cadastrada, sem registro do Coordenador). "Reiniciar" apaga só essa pasta.

A tela recebe textos prontos em pt-BR; identificadores técnicos só servem para as ações (não são exibidos na visão principal).
O estado operacional vem SEMPRE de decisoes_conciliacao (lógica central).
"""
import hashlib
import shutil
import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "AGENTES" / "FINANCEIRO" / "ferramentas"))
import conciliador_financeiro as cf  # noqa: E402
import decisoes_conciliacao as dcs  # noqa: E402

DEMO_ID = "DEMONSTRACAO"
DEMO_ROTULO = "DEMONSTRAÇÃO — Conciliação Financeira"
DEMO_EMPRESA = "EMPRESA DEMONSTRAÇÃO (fictícia)"
DEMO_COMPETENCIA = "2026-09"
MESES = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")

CRITERIOS_OK = {
    "VALOR_EXATO": "Mesmo valor", "SOMA_EXATA": "A soma dos valores fecha exatamente",
    "NATUREZA_COMPATIVEL": "Mesma natureza (entrada com recebimento, saída com pagamento)",
    "DATA_EXATA": "Mesma data", "DATA_1_DIA": "Datas com 1 dia de diferença", "DATA_2_DIAS": "Datas com 2 dias de diferença",
    "DOCUMENTO_EXATO": "Mesmo número de documento", "CONTRAPARTE_DOCUMENTO": "CPF/CNPJ da contraparte aparece no banco",
    "CONTRAPARTE_NOME_FORTE": "Nome da contraparte aparece no banco",
    "CONTRAPARTE_NOME_PARCIAL": "Só parte do nome da contraparte aparece no banco",
    "DESCRICAO_COMPATIVEL": "Descrições parecidas"}
STATUS = {  # chave → (rótulo, tom, ícone)
    "CONCILIADO": ("Conciliado automaticamente", "ok", "✓"), "REVISAR": ("Revisar", "atencao", "!"),
    "AMBIGUO": ("Ambíguo", "atencao", "?"), "NAO_CONCILIADO": ("Não conciliado", "bloqueio", "✕"),
    "APROVADO": ("Aprovado pelo Supervisor", "ok", "✓"), "REJEITADO": ("Rejeitado", "bloqueio", "✕"),
    "RELATORIO_SEM_BANCO": ("Só no relatório", "info", "i")}
PENDENCIAS = {
    "REVISAR": ("O sistema encontrou uma associação provável, mas não possui evidência suficiente para confirmá-la sozinho.",
                "A movimentação ainda não pode seguir automaticamente para o tratamento contábil.",
                "Confira os dois registros e confirme ou rejeite a associação."),
    "AMBIGUO": ("Mais de um registro do relatório combina com esta movimentação; o sistema não escolhe sozinho.",
                "A movimentação ainda não pode seguir automaticamente para o tratamento contábil.",
                "Compare os candidatos, selecione UM e confirme — ou rejeite se nenhum for o correto."),
    "NAO_CONCILIADO": ("Não encontramos associação segura no relatório para esta movimentação.",
                       "A movimentação continua impedindo o avanço até receber suporte.",
                       "Verifique se falta algum registro no relatório ou forneça documentação de suporte. O sistema não cria associação."),
    "REJEITADO": ("A associação sugerida foi rejeitada pelo Supervisor.",
                  "A movimentação continua impedindo o avanço até receber outro suporte.",
                  "Forneça documentação de suporte ou registro correto no relatório. Se a rejeição foi engano, desfaça a decisão."),
    "RELATORIO_SEM_BANCO": ("Registro do relatório sem movimento correspondente no banco.",
                            "Não bloqueia o banco, mas pode indicar pagamento não realizado ou realizado em outra conta.",
                            "Confira com o financeiro da empresa, se necessário.")}


def fmt_comp(c: str) -> str:
    try:
        a, m = c.split("-")
        return f"{MESES[int(m) - 1]}/{a}"
    except (ValueError, IndexError, AttributeError):
        return str(c or "")


# ---------------------------------------------------------------- fontes
class Fonte:
    """Tudo o que a Central precisa de uma conciliação: contexto, conciliação, movimentos para exibir e onde gravar."""

    def __init__(self, contexto, conciliacao, bancarios, auxiliares, suporte, caminho, titulo, demonstracao=False):
        self.contexto, self.conciliacao = contexto, conciliacao
        self.bancarios, self.auxiliares, self.suporte = bancarios, auxiliares, set(suporte)
        self.caminho, self.titulo, self.demonstracao = Path(caminho), titulo, demonstracao


def pasta_decisoes_sol(runtime: Path, sol: str) -> Path:
    return Path(runtime) / "execucoes" / sol / "supervisor-conciliacao" / "decisoes.json"


def fonte_sol(runtime: Path, sol: str, registro: dict, resultado: dict):
    """None quando a SOL ainda não tem conciliação financeira (sem extrato normalizado/relatório ou sem resultado concluído)."""
    conc = (resultado or {}).get("conciliacao_financeira")
    if not conc or conc.get("situacao") != "EXECUTADA":
        return None
    bancarios = {}
    for m in resultado.get("movimentos") or []:
        rid = (m.get("rastreio_bancario") or {}).get("id")
        if rid:
            bancarios[rid] = {"data": m.get("data"), "valor": m.get("valor"), "natureza": "ENTRADA" if m.get("direcao") == "CREDITO" else "SAIDA",
                              "descricao": m.get("descricao") or "", "documento": (m.get("identificadores") or {}).get("DOCUMENTO"),
                              "suporte": m.get("situacao") in ("COM_SUPORTE", "TRANSFERENCIA_PROPRIA")}
    auxiliares = {a["id"]: a for a in resultado.get("movimentos_financeiros_auxiliares") or [] if a.get("id")}
    contexto = {"sol": sol, "empresa": registro["empresa"], "competencia": registro["competencia"], "tentativa": f"financeiro-{resultado.get('n')}"}
    return Fonte(contexto, conc, bancarios, auxiliares, [i for i, b in bancarios.items() if b["suporte"]],
                 pasta_decisoes_sol(runtime, sol), f"{registro['empresa']} · {fmt_comp(registro['competencia'])} · {sol}")


# ---------------------------------------------------------------- demonstração (dados 100% fictícios, motor real)
def _demo_movimentos():
    D = lambda d: f"2026-09-{d:02d}"
    banco = [  # (id, dia, valor, natureza, descrição, documento)
        ("B01", 3, "1500.00", "DEBITO", "PAGTO BOLETO 778899", "778899"),
        ("B02", 4, "3200.00", "CREDITO", "PIX RECEBIDO BETA SERVICOS FICTICIOS", None),
        ("B03", 5, "890.00", "DEBITO", "TED ENVIADA GAMA TRANSPORTES DEMO", None),
        ("B04", 8, "245.90", "DEBITO", "PAGAMENTO DIVERSOS", None),
        ("B05", 9, "1320.00", "DEBITO", "PIX ENVIADO EPSILON", None),
        ("B06", 10, "1180.00", "CREDITO", "DEPOSITO", None),
        ("B07", 11, "75.50", "DEBITO", "TARIFA PACOTE SERVICOS", None),
        ("B08", 12, "412.30", "DEBITO", "PIX ENVIADO", None),
        ("B09", 14, "960.00", "CREDITO", "TED RECEBIDA", None),
        ("B10", 15, "300.00", "DEBITO", "PIX ENVIADO", None),
        ("B11", 16, "500.00", "CREDITO", "PIX RECEBIDO", None),
        ("B12", 18, "1000.00", "DEBITO", "PAGAMENTO FORNECEDORES", None),
        ("B13", 21, "700.00", "CREDITO", "PIX RECEBIDO OMEGA ATACADO FICTICIO", None),
        ("B14", 21, "300.00", "CREDITO", "PIX RECEBIDO OMEGA ATACADO FICTICIO", None),
        ("B15", 25, "2345.67", "DEBITO", "TRANSFERENCIA ENTRE CONTAS", None)]
    relatorio = [  # (id, dia quitação, valor, natureza, contraparte, descrição, documento)
        ("R01", 3, "1500.00", "SAIDA", "PAPELARIA AURORA FICTICIA LTDA", "Material de escritório", "778899"),
        ("R02", 4, "3200.00", "ENTRADA", "BETA SERVICOS FICTICIOS LTDA", "Consultoria mensal", None),
        ("R03", 6, "890.00", "SAIDA", "GAMA TRANSPORTES DEMO LTDA", "Frete de mercadorias", None),
        ("R04", 8, "245.90", "SAIDA", "DELTA MANUTENCAO FICTICIA", "Manutenção do ar-condicionado", None),
        ("R05", 9, "1320.00", "SAIDA", "EPSILON CONSULTORIA FICTICIA", "Assessoria jurídica", None),
        ("R06", 12, "1180.00", "ENTRADA", "CLIENTE ZETA FICTICIO", "Venda de serviços", None),
        ("R07", 11, "75.50", "SAIDA", None, "Tarifa bancária", None),
        ("R08", 12, "412.30", "SAIDA", "ETA LIMPEZA FICTICIA", "Serviço de limpeza", None),
        ("R09", 15, "960.00", "ENTRADA", "TETA DISTRIBUIDORA FICTICIA", "Recebimento de duplicata", None),
        ("R10", 15, "300.00", "SAIDA", "IOTA SOFTWARE FICTICIO", "Licença de sistema", None),
        ("R11", 15, "300.00", "SAIDA", "KAPPA INTERNET FICTICIA", "Internet do escritório", None),
        ("R12", 16, "500.00", "ENTRADA", "LAMBDA COMERCIO FICTICIO", "Venda à vista", None),
        ("R13", 16, "500.00", "ENTRADA", "MI REPRESENTACOES FICTICIAS", "Comissão recebida", None),
        ("R14", 18, "600.00", "SAIDA", "NI EMBALAGENS FICTICIAS", "Compra de embalagens", None),
        ("R15", 19, "400.00", "SAIDA", "XI ETIQUETAS FICTICIAS", "Compra de etiquetas", None),
        ("R16", 21, "1000.00", "ENTRADA", "OMEGA ATACADO FICTICIO", "Venda parcelada recebida", None),
        ("R17", 28, "88.00", "SAIDA", "SIGMA CORREIOS FICTICIOS", "Postagem", None)]
    sha_b, sha_a = hashlib.sha256(b"DEMONSTRACAO-BANCO-FICTICIO").hexdigest(), hashlib.sha256(b"DEMONSTRACAO-RELATORIO-FICTICIO").hexdigest()
    bm = [{"id": f"DEMO-{i}", "data": D(d), "valor": Decimal(v), "natureza": n, "descricao": t, "documento": doc, "sha256_origem": sha_b}
          for i, d, v, n, t, doc in banco]
    am = [{"id": f"DEMO-{i}", "data": D(d), "data_quitacao": D(d), "data_competencia": None, "valor": Decimal(v), "natureza": n,
           "documento": doc, "contraparte": {"nome": cp} if cp else {}, "descricao": t, "sha": sha_a}
          for i, d, v, n, cp, t, doc in relatorio]
    return bm, am, sha_b, sha_a


def montar_demo():
    bm, am, sha_b, sha_a = _demo_movimentos()
    conc = cf.para_json(cf.conciliar(
        [{"contrato": cf.CONTRATO_BANCARIO, "situacao": "NORMALIZADO", "adaptador": "DEMONSTRACAO_FICTICIA", "origem": {"sha256": sha_b}, "movimentos": bm}],
        [{"contrato": cf.CONTRATO_AUXILIAR, "situacao": "NORMALIZADO", "adaptador": "DEMONSTRACAO_FICTICIA", "origem": {"sha256": sha_a}, "movimentos": am}]))
    bancarios = {m["id"]: {"data": m["data"], "valor": f"{m['valor']:.2f}", "natureza": "ENTRADA" if m["natureza"] == "CREDITO" else "SAIDA",
                           "descricao": m["descricao"], "documento": m["documento"], "suporte": False} for m in bm}
    auxiliares = {m["id"]: dict(m, valor=f"{m['valor']:.2f}") for m in am}
    return conc, bancarios, auxiliares


def fonte_demo(pasta: Path) -> Fonte:
    conc, bancarios, auxiliares = montar_demo()
    contexto = {"sol": DEMO_ID, "empresa": "DEMONSTRACAO-FICTICIA", "competencia": DEMO_COMPETENCIA, "tentativa": "demonstracao"}
    return Fonte(contexto, conc, bancarios, auxiliares, [], Path(pasta) / "decisoes.json",
                 f"{DEMO_EMPRESA} · {fmt_comp(DEMO_COMPETENCIA)}", demonstracao=True)


def reiniciar_demo(pasta: Path) -> None:
    """Apaga SOMENTE a pasta da demonstração (decisões fictícias). Recusa qualquer pasta que não seja a da demonstração."""
    pasta = Path(pasta)
    if pasta.name != "demonstracao-conciliacao" or not pasta.parent.exists():
        raise ValueError("Pasta da demonstração inválida.")
    if pasta.exists():
        shutil.rmtree(pasta)


# ---------------------------------------------------------------- visão para a tela
def _banco_linha(f: Fonte, i: str) -> dict:
    b = f.bancarios.get(i) or {}
    return {"data": b.get("data"), "valor": b.get("valor"), "natureza": b.get("natureza"), "descricao": b.get("descricao") or "",
            "documento": b.get("documento")}


def _aux_linha(f: Fonte, i: str) -> dict:
    a = f.auxiliares.get(i) or {}
    cp = a.get("contraparte") or {}
    return {"data": a.get("data_quitacao") or a.get("data"), "valor": a.get("valor"), "natureza": a.get("natureza"),
            "contraparte": cp.get("nome") or cp.get("nome_fantasia") or "", "documento_contraparte": cf.mascarar(cp.get("documento")) if cp.get("documento") else None,
            "descricao": a.get("descricao") or "", "documento": a.get("documento")}


def _status(x: dict, ev) -> str:
    estado = dcs.estado_operacional(x, ev)
    if estado == dcs.CONFIRMADA_AUTO:
        return "CONCILIADO"
    if estado == dcs.CONFIRMADA_SUPERVISOR:
        return "APROVADO"
    if estado == dcs.REJEITADA:
        return "REJEITADO"
    if estado == dcs.SEM_ASSOCIACAO:
        return "NAO_CONCILIADO" if x["bancarios"] else "RELATORIO_SEM_BANCO"
    return "AMBIGUO" if x["classificacao"] == "AMBIGUO" else "REVISAR"


def _explicar(criterios: list, ausentes: list) -> list:
    itens = [{"ok": True, "texto": CRITERIOS_OK[c]} for c in criterios if c in CRITERIOS_OK
             and not (c == "VALOR_EXATO" and "SOMA_EXATA" in criterios)]
    if not any(c.startswith("CONTRAPARTE_") for c in criterios):
        itens.append({"ok": False, "texto": "Contraparte não identificada no banco"})
    if "DOCUMENTO_EXATO" in ausentes:
        itens.append({"ok": False, "texto": "Documento diferente ou não informado"})
    if "DESCRICAO_COMPATIVEL" in ausentes:
        itens.append({"ok": False, "texto": "Descrições diferentes"})
    if "DATA_NA_JANELA" in ausentes:
        itens.append({"ok": False, "texto": "Datas fora da janela de 2 dias"})
    return itens


def _item(f: Fonte, x: dict, ev) -> dict:
    st = _status(x, ev)
    bloq = set(dcs.bloqueios({"associacoes": [x]}, {x["id"]: ev} if ev else {}, f.suporte))
    natureza = (f.bancarios.get(x["bancarios"][0]) or {}).get("natureza") if x["bancarios"] else (f.auxiliares.get(x["auxiliares"][0]) or {}).get("natureza")
    rotulo, tom, icone = STATUS[st]
    return {"id": x["id"], "status": st, "status_rotulo": rotulo, "tom": tom, "icone": icone,
            "classificacao_motor": x["classificacao"], "decisao_supervisor": ev["decisao"] if ev else dcs.SEM_DECISAO,
            "estado_operacional": dcs.estado_operacional(x, ev), "cardinalidade": x.get("cardinalidade"),
            "natureza": "ENTRADA" if natureza in ("ENTRADA", "CREDITO") else "SAIDA",
            "banco": [_banco_linha(f, i) for i in x["bancarios"]], "relatorio": [_aux_linha(f, i) for i in x["auxiliares"]],
            "valor_banco": x.get("valor_bancario"), "valor_relatorio": x.get("valor_auxiliar"),
            "candidatos_quantidade": len(x.get("candidatos") or []),
            "selecionavel_lote": x["classificacao"] == "PROVAVEL" and ev is None,
            "bloqueios": len(bloq), "aprovado_por": ev["responsavel"] if ev and ev["decisao"] == dcs.APROVADO else None}


def visao(f: Fonte) -> dict:
    """Tela principal. Registro de decisões corrompido → visão SEM ações (fail-closed) e aviso claro."""
    try:
        dados = dcs.carregar(f.caminho, f.contexto)
        corrompido = None
    except dcs.EstadoCorrompido as exc:
        dados, corrompido = dcs.vazio(f.contexto), str(exc)
    efetivas, desatualizadas = dcs.decisoes_efetivas(dados, f.conciliacao) if not corrompido else ({}, [])
    itens = [_item(f, x, efetivas.get(x["id"])) for x in f.conciliacao["associacoes"]]
    ordem = {"REVISAR": 0, "AMBIGUO": 1, "NAO_CONCILIADO": 2, "REJEITADO": 3, "APROVADO": 4, "CONCILIADO": 5, "RELATORIO_SEM_BANCO": 6}
    itens.sort(key=lambda i: (ordem[i["status"]], (i["banco"] or i["relatorio"])[0]["data"] or "", i["id"]))
    res = dcs.resumo(f.conciliacao, efetivas, f.suporte)
    if corrompido:
        res["bloqueios_restantes"] = res["movimentos_bancarios"]
    return {"disponivel": True, "demonstracao": f.demonstracao, "titulo": f.titulo,
            "rotulo": DEMO_ROTULO if f.demonstracao else "Conciliação financeira",
            "competencia": f.contexto["competencia"], "competencia_texto": fmt_comp(f.contexto["competencia"]),
            "revisao_conciliacao": dcs.revisao_conciliacao(f.conciliacao), "revisao_decisoes": dcs.revisao_decisoes(dados),
            "resumo": res, "itens": itens, "decisoes_desatualizadas": len(desatualizadas),
            "acoes_bloqueadas": bool(corrompido),
            "aviso_corrompido": ("O registro de decisões desta conciliação está inconsistente. Nenhuma decisão foi aplicada e nenhuma "
                                 "nova decisão será aceita. Avise o responsável técnico.") if corrompido else None,
            "pendencia_bloqueio": {"problema": f"{res['bloqueios_restantes']} movimentação(ões) do banco ainda não têm associação confirmada nem suporte.",
                                   "impacto": "Essas movimentações impedem o avanço automático para o tratamento contábil.",
                                   "o_que_fazer": "Revise as associações sugeridas (Para revisar e Ambíguos) ou forneça suporte para as não conciliadas."}
            if res["bloqueios_restantes"] else None,
            "aviso_efeito": dcs.EFEITO}


def detalhe(f: Fonte, assoc_id: str):
    x = next((a for a in f.conciliacao["associacoes"] if a["id"] == assoc_id), None)
    if not x:
        return None
    try:
        dados = dcs.carregar(f.caminho, f.contexto)
        corrompido = False
    except dcs.EstadoCorrompido:
        dados, corrompido = dcs.vazio(f.contexto), True
    efetivas, _ = dcs.decisoes_efetivas(dados, f.conciliacao) if not corrompido else ({}, [])
    ev = efetivas.get(x["id"])
    item = _item(f, x, ev)
    problema = PENDENCIAS.get(item["status"])
    candidatos = []
    for n, c in enumerate(x.get("candidatos") or [], 1):
        crit = c.get("criterios") or []
        escolhido = bool(ev and ev.get("candidato_escolhido") and dcs._candidato_igual(c, ev["candidato_escolhido"]))
        candidatos.append({"numero": n, "bancarios": c["bancarios"], "auxiliares": c["auxiliares"],
                           "banco": [_banco_linha(f, i) for i in c["bancarios"]], "relatorio": [_aux_linha(f, i) for i in c["auxiliares"]],
                           "explicacao": _explicar(crit, [k for k in cf.TODAS if k not in crit]),
                           "pontuacao": (c.get("score") or {}).get("total"), "escolhido": escolhido})
    pode = not corrompido
    acoes = {"confirmar": pode and x["classificacao"] == "PROVAVEL" and ev is None,
             "rejeitar": pode and x["classificacao"] in ("PROVAVEL", "AMBIGUO") and ev is None,
             "escolher_candidato": pode and x["classificacao"] == "AMBIGUO" and ev is None,
             "desfazer": pode and ev is not None, "observacao": pode and x["classificacao"] == "NAO_CONCILIADO"}
    historico = [_evento_tela(e) for e in dados["eventos"] if e["associacao"] == x["id"]]
    return dict(item, motivo=x.get("motivo"),
                explicacao=_explicar(x.get("criterios_atendidos") or [], x.get("criterios_ausentes") or []) if x["classificacao"] in ("CONCILIADO", "PROVAVEL") else [],
                pontuacao=(x.get("score") or {}).get("total") if x["classificacao"] in ("CONCILIADO", "PROVAVEL") else None,
                candidatos=candidatos, acoes=acoes, historico=historico,
                pendencia={"problema": problema[0], "impacto": problema[1], "o_que_fazer": problema[2]} if problema else None,
                decisao=_evento_tela(ev) if ev else None,
                revisao_conciliacao=dcs.revisao_conciliacao(f.conciliacao), revisao_decisoes=dcs.revisao_decisoes(dados),
                aviso_efeito=dcs.EFEITO)


ACOES_TEXTO = {dcs.APROVADO: "Confirmou associação", dcs.REJEITADO: "Rejeitou associação", dcs.REVOGADO: "Desfez decisão",
               dcs.OBSERVACAO: "Registrou observação"}


def _evento_tela(e: dict) -> dict:
    return {"em": e["em"], "responsavel": e["responsavel"], "acao": ACOES_TEXTO[e["decisao"]], "decisao": e["decisao"],
            "classificacao_motor": e["classificacao_motor"], "justificativa": e["justificativa"], "origem": e["origem"],
            "lote": e["lote"], "estado_anterior": e["estado_anterior"], "estado_posterior": e["estado_posterior"],
            "candidato_escolhido": bool(e["candidato_escolhido"]), "politica": e["politica"], "evento": e["id"],
            "associacao": e["associacao"]}


def historico(f: Fonte) -> dict:
    """Agrupado por ação (um lote = uma linha com a quantidade); detalhes por decisão sob demanda."""
    try:
        dados = dcs.carregar(f.caminho, f.contexto)
    except dcs.EstadoCorrompido:
        return {"disponivel": False, "motivo": "Registro de decisões inconsistente; histórico indisponível. Avise o responsável técnico."}
    grupos = []
    for e in dados["eventos"]:
        chave = e["lote"] or e["id"]
        if grupos and grupos[-1]["chave"] == chave:
            grupos[-1]["quantidade"] += 1
            grupos[-1]["itens"].append(_evento_tela(e))
            continue
        grupos.append({"chave": chave, "em": e["em"], "responsavel": e["responsavel"],
                       "acao": ACOES_TEXTO[e["decisao"]] + (" em lote" if e["lote"] else ""), "quantidade": 1,
                       "justificativa": e["justificativa"], "itens": [_evento_tela(e)]})
    for g in grupos:
        g.pop("chave")
    return {"disponivel": True, "total_eventos": len(dados["eventos"]), "grupos": list(reversed(grupos))}


def decidir(f: Fonte, pedidos: list, corpo: dict, origem: str) -> list:
    return dcs.decidir_e_gravar(f.caminho, f.contexto, f.conciliacao, pedidos, revisao_conciliacao_cliente=corpo.get("revisao_conciliacao"),
                                revisao_decisoes_cliente=corpo.get("revisao_decisoes"), justificativa=corpo.get("justificativa"),
                                origem=origem)
