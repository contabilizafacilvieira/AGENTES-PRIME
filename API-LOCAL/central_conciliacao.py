"""Central de Revisão do Supervisor — conciliação financeira banco × relatório (leitura para a tela + decisões).

Duas fontes, mesma lógica:
- SOL real: última tentativa CONCLUÍDA do Financeiro (financeiro-N/resultado.json, campo conciliacao_financeira). Decisões em
  <runtime>/execucoes/<SOL>/supervisor-conciliacao/decisoes.json (camada separada; o resultado do Financeiro não é tocado).
- DEMONSTRAÇÃO: cenário 100% FICTÍCIO montado aqui e conciliado pelo MOTOR REAL (política V1). Fica numa pasta PRÓPRIA, fora do
  runtime operacional (sem SOL, sem empresa cadastrada, sem registro do Coordenador). "Reiniciar" apaga só essa pasta.

A tela recebe textos prontos em pt-BR; identificadores técnicos só servem para as ações (não são exibidos na visão principal).
O estado operacional vem SEMPRE de decisoes_conciliacao (lógica central).
"""
import datetime as dt
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
    "RELATORIO_SEM_BANCO": ("Só no relatório", "info", "i"),
    "RELATORIO_ASSOCIADO_MANUAL": ("Usado em associação manual", "ok", "✓")}
PENDENCIAS = {
    "REVISAR": ("O sistema encontrou uma associação provável, mas não possui evidência suficiente para confirmá-la sozinho.",
                "A movimentação ainda não pode seguir automaticamente para o tratamento contábil.",
                "Confira os dois registros e confirme ou rejeite a associação."),
    "AMBIGUO": ("Mais de um registro do relatório combina com esta movimentação; o sistema não escolhe sozinho.",
                "A movimentação ainda não pode seguir automaticamente para o tratamento contábil.",
                "Compare os candidatos, selecione UM e confirme — ou rejeite se nenhum for o correto."),
    "NAO_CONCILIADO": ("Não encontramos associação segura automaticamente.",
                       "Este movimento continua bloqueando o avanço.",
                       "Busque registros no relatório e confirme uma associação manual somente se conseguir comprová-la, ou registre uma observação."),
    "REJEITADO": ("A associação sugerida foi rejeitada pelo Supervisor.",
                  "A movimentação continua impedindo o avanço até receber outro suporte.",
                  "Forneça documentação de suporte ou registro correto no relatório. Se a rejeição foi engano, desfaça a decisão."),
    "AMBIGUO_PARCIAL": ("Parte desta ambiguidade já foi resolvida, mas há movimento bancário do grupo ainda sem associação confirmada.",
                        "O movimento continua bloqueando o avanço.",
                        "Revise os registros ainda disponíveis e escolha a associação correta, ou registre uma observação. Nada é confirmado sozinho."),
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


# ---------------------------------------------------------------- 2ª demonstração: ASSOCIAÇÃO MANUAL ASSISTIDA (100% fictícia)
DEMO_MANUAL_ID = "DEMONSTRACAO-MANUAL"
DEMO_MANUAL_ROTULO = "DEMONSTRAÇÃO — Associação manual"
PASTAS_DEMO = ("demonstracao-conciliacao", "demonstracao-associacao-manual", "demonstracao-ambiguo-parcial")
DEMO_AMBIGUO_ID = "DEMONSTRACAO-AMBIGUO"
DEMO_AMBIGUO_ROTULO = "DEMONSTRAÇÃO — Ambiguidade parcial"


def _montar_demo(banco, relatorio, rotulo):
    sha_b = hashlib.sha256(f"{rotulo}-BANCO-FICTICIO".encode()).hexdigest()
    sha_a = hashlib.sha256(f"{rotulo}-RELATORIO-FICTICIO".encode()).hexdigest()
    bm = [{"id": i, "data": d, "valor": Decimal(v), "natureza": n, "descricao": t, "documento": doc, "sha256_origem": sha_b}
          for i, d, v, n, t, doc in banco]
    am = [{"id": i, "data": d, "data_quitacao": d, "data_competencia": None, "valor": Decimal(v), "natureza": n, "documento": doc,
           "contraparte": {"nome": cp}, "descricao": t, "plano_contas": "Despesas bancárias", "banco": "BANCO FICTICIO", "sha": sha_a}
          for i, d, v, n, cp, t, doc in relatorio]
    conc = cf.para_json(cf.conciliar(
        [{"contrato": cf.CONTRATO_BANCARIO, "situacao": "NORMALIZADO", "adaptador": "DEMONSTRACAO_FICTICIA", "origem": {"sha256": sha_b}, "movimentos": bm}],
        [{"contrato": cf.CONTRATO_AUXILIAR, "situacao": "NORMALIZADO", "adaptador": "DEMONSTRACAO_FICTICIA", "origem": {"sha256": sha_a}, "movimentos": am}]))
    bancarios = {m["id"]: {"data": m["data"], "valor": f"{m['valor']:.2f}", "natureza": "ENTRADA" if m["natureza"] == "CREDITO" else "SAIDA",
                           "descricao": m["descricao"], "documento": m["documento"], "suporte": False} for m in bm}
    return conc, bancarios, {m["id"]: dict(m, valor=f"{m['valor']:.2f}") for m in am}


def montar_demo_ambiguo():
    """2 movimentos bancários × 2 registros do relatório de MESMO valor, datas próximas → AMBIGUO 2x2 (4 candidatos)."""
    banco = [("DAMB-B1", "2026-09-15", "10.00", "DEBITO", "TARIFA AVULSA FICTICIA", None),
             ("DAMB-B2", "2026-09-16", "10.00", "DEBITO", "TARIFA AVULSA FICTICIA", None),
             ("DAMB-B3", "2026-09-05", "250.00", "DEBITO", "PAGTO BOLETO 556677", "556677")]
    relatorio = [("DAMB-R1", "2026-09-15", "10.00", "SAIDA", "BANCO FICTICIO S A", "Tarifa bancária", None),
                 ("DAMB-R2", "2026-09-16", "10.00", "SAIDA", "BANCO FICTICIO S A", "Tarifa bancária", None),
                 ("DAMB-R3", "2026-09-05", "250.00", "SAIDA", "FORNECEDOR OMEGA FICTICIO", "Material", "556677")]
    return _montar_demo(banco, relatorio, "DEMONSTRACAO-AMBIGUO")


def fonte_demo_ambiguo(pasta: Path) -> Fonte:
    conc, bancarios, auxiliares = montar_demo_ambiguo()
    contexto = {"sol": DEMO_AMBIGUO_ID, "empresa": "DEMONSTRACAO-FICTICIA", "competencia": DEMO_COMPETENCIA, "tentativa": "demonstracao-ambiguo"}
    return Fonte(contexto, conc, bancarios, auxiliares, [], Path(pasta) / "decisoes.json",
                 f"{DEMO_EMPRESA} · {fmt_comp(DEMO_COMPETENCIA)}", demonstracao=True)


def _demo_manual_movimentos():
    D = lambda d: f"2026-09-{d:02d}"
    banco = [  # (id, dia, valor, natureza, descrição, documento)
        ("M01", 2, "800.00", "DEBITO", "PAGTO BOLETO 445566", "445566"),
        ("M02", 3, "12000.00", "DEBITO", "PIX ENVIADO EMPRESA FICTICIA", None),       # 1×4: além do limite automático (3)
        ("M03", 8, "350.00", "DEBITO", "PIX ENVIADO", None),
        ("M04", 20, "900.00", "CREDITO", "PIX RECEBIDO", None),                       # duas combinações exatas (fora da janela)
        ("M05", 26, "777.77", "DEBITO", "TARIFA DIVERSA", None)]                       # nenhuma combinação
    relatorio = [  # (id, dia quitação, valor, natureza, contraparte, descrição, documento, plano de contas)
        ("R01", 2, "800.00", "SAIDA", "FORNECEDOR ALFA FICTICIO", "Material de consumo", "445566", "Despesas gerais"),
        ("R02", 2, "2000.00", "SAIDA", "EMPRESA FICTICIA COMERCIO", "Parcela 1/4", "NF 9001", "Fornecedores"),
        ("R03", 3, "3000.00", "SAIDA", "EMPRESA FICTICIA COMERCIO", "Parcela 2/4", "NF 9002", "Fornecedores"),
        ("R04", 4, "1500.00", "SAIDA", "EMPRESA FICTICIA COMERCIO", "Parcela 3/4", "NF 9003", "Fornecedores"),
        ("R05", 5, "5500.00", "SAIDA", "EMPRESA FICTICIA COMERCIO", "Parcela 4/4", "NF 9004", "Fornecedores"),
        ("R06", 8, "350.00", "SAIDA", "SERVICOS GAMA FICTICIOS", "Manutenção", None, "Serviços"),
        ("R07", 24, "400.00", "ENTRADA", "CLIENTE DELTA FICTICIO", "Venda à vista", None, "Receitas"),
        ("R08", 24, "500.00", "ENTRADA", "CLIENTE EPSILON FICTICIO", "Venda à vista", None, "Receitas"),
        ("R09", 25, "300.00", "ENTRADA", "CLIENTE ZETA FICTICIO", "Venda à vista", None, "Receitas"),
        ("R10", 1, "600.00", "ENTRADA", "CLIENTE ETA FICTICIO", "Venda antiga", None, "Receitas"),
        ("R11", 26, "100.00", "SAIDA", "DESPESA AVULSA FICTICIA", "Despesa avulsa", None, "Despesas gerais")]
    sha_b = hashlib.sha256(b"DEMONSTRACAO-MANUAL-BANCO-FICTICIO").hexdigest()
    sha_a = hashlib.sha256(b"DEMONSTRACAO-MANUAL-RELATORIO-FICTICIO").hexdigest()
    bm = [{"id": f"DMAN-{i}", "data": D(d), "valor": Decimal(v), "natureza": n, "descricao": t, "documento": doc, "sha256_origem": sha_b}
          for i, d, v, n, t, doc in banco]
    am = [{"id": f"DMAN-{i}", "data": D(d), "data_quitacao": D(d), "data_competencia": None, "valor": Decimal(v), "natureza": n,
           "documento": doc, "contraparte": {"nome": cp}, "descricao": t, "plano_contas": pc, "banco": "BANCO FICTICIO", "sha": sha_a}
          for i, d, v, n, cp, t, doc, pc in relatorio]
    return bm, am, sha_b, sha_a


def montar_demo_manual():
    bm, am, sha_b, sha_a = _demo_manual_movimentos()
    conc = cf.para_json(cf.conciliar(
        [{"contrato": cf.CONTRATO_BANCARIO, "situacao": "NORMALIZADO", "adaptador": "DEMONSTRACAO_FICTICIA", "origem": {"sha256": sha_b}, "movimentos": bm}],
        [{"contrato": cf.CONTRATO_AUXILIAR, "situacao": "NORMALIZADO", "adaptador": "DEMONSTRACAO_FICTICIA", "origem": {"sha256": sha_a}, "movimentos": am}]))
    bancarios = {m["id"]: {"data": m["data"], "valor": f"{m['valor']:.2f}", "natureza": "ENTRADA" if m["natureza"] == "CREDITO" else "SAIDA",
                           "descricao": m["descricao"], "documento": m["documento"], "suporte": False} for m in bm}
    auxiliares = {m["id"]: dict(m, valor=f"{m['valor']:.2f}") for m in am}
    return conc, bancarios, auxiliares


def fonte_demo_manual(pasta: Path) -> Fonte:
    conc, bancarios, auxiliares = montar_demo_manual()
    contexto = {"sol": DEMO_MANUAL_ID, "empresa": "DEMONSTRACAO-FICTICIA", "competencia": DEMO_COMPETENCIA, "tentativa": "demonstracao-manual"}
    return Fonte(contexto, conc, bancarios, auxiliares, [], Path(pasta) / "decisoes.json",
                 f"{DEMO_EMPRESA} · {fmt_comp(DEMO_COMPETENCIA)}", demonstracao=True)


def reiniciar_demo(pasta: Path) -> None:
    """Apaga SOMENTE a pasta de uma demonstração (decisões fictícias). Recusa qualquer pasta que não seja de demonstração."""
    pasta = Path(pasta)
    if pasta.name not in PASTAS_DEMO or not pasta.parent.exists():
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


def _status(x: dict, ev, consumidos=frozenset()) -> str:
    estado = dcs.estado_operacional(x, ev)
    if estado == dcs.SEM_ASSOCIACAO and not x["bancarios"] and set(x["auxiliares"]) & set(consumidos):
        return "RELATORIO_ASSOCIADO_MANUAL"
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


def _item(f: Fonte, x: dict, ev, consumidos=frozenset()) -> dict:
    st = _status(x, ev, consumidos)
    manual = bool(ev and ev.get("origem") == dcs.ORIGEM_MANUAL)
    aux_ids = (ev["candidato_escolhido"]["auxiliares"] if manual else x["auxiliares"])
    bloq = set(dcs.bloqueios({"associacoes": [x]}, {x["id"]: ev} if ev else {}, f.suporte))
    natureza = (f.bancarios.get(x["bancarios"][0]) or {}).get("natureza") if x["bancarios"] else (f.auxiliares.get(x["auxiliares"][0]) or {}).get("natureza")
    rotulo, tom, icone = STATUS[st]
    eh_parcial = dcs.parcial(x, ev)
    if eh_parcial:
        rotulo = "Ambíguo — parcialmente resolvido"
    cobertos = set(dcs.ids_confirmados(x, ev)[0])
    return {"id": x["id"], "status": st, "status_rotulo": rotulo, "tom": tom, "icone": icone, "parcial": eh_parcial,
            "movimentos_total": len(x["bancarios"]), "movimentos_resolvidos": len(cobertos & set(x["bancarios"])),
            "classificacao_motor": x["classificacao"], "decisao_supervisor": ev["decisao"] if ev else dcs.SEM_DECISAO,
            "estado_operacional": dcs.estado_operacional(x, ev), "cardinalidade": x.get("cardinalidade"),
            "natureza": "ENTRADA" if natureza in ("ENTRADA", "CREDITO") else "SAIDA",
            "banco": [_banco_linha(f, i) for i in x["bancarios"]], "relatorio": [_aux_linha(f, i) for i in aux_ids],
            "valor_banco": x.get("valor_bancario"),
            "valor_relatorio": (ev["associacao_manual"]["soma_relatorio"] if manual else x.get("valor_auxiliar")),
            "associacao_manual": manual,
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
    consumidos = dcs.auxiliares_confirmados(f.conciliacao, efetivas)
    itens = [_item(f, x, efetivas.get(x["id"]), consumidos) for x in f.conciliacao["associacoes"]]
    ordem = {"REVISAR": 0, "AMBIGUO": 1, "NAO_CONCILIADO": 2, "REJEITADO": 3, "APROVADO": 4, "CONCILIADO": 5, "RELATORIO_SEM_BANCO": 6,
             "RELATORIO_ASSOCIADO_MANUAL": 7}
    itens.sort(key=lambda i: (ordem[i["status"]], (i["banco"] or i["relatorio"])[0]["data"] or "", i["id"]))
    res = dcs.resumo(f.conciliacao, efetivas, f.suporte)
    if corrompido:
        res["bloqueios_restantes"] = res["movimentos_bancarios"]
    lista_bloqueios = bloqueios_detalhados(f, efetivas, corrompido)
    return {"disponivel": True, "demonstracao": f.demonstracao, "titulo": f.titulo,
            "rotulo": ({DEMO_MANUAL_ID: DEMO_MANUAL_ROTULO, DEMO_AMBIGUO_ID: DEMO_AMBIGUO_ROTULO}.get(f.contexto["sol"], DEMO_ROTULO)
                       if f.demonstracao else "Conciliação financeira"),
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
            "bloqueios_lista": lista_bloqueios,
            "invariante": invariante(f, efetivas, lista_bloqueios, itens, corrompido),
            "aviso_efeito": dcs.EFEITO}


def invariante(f: Fonte, efetivas: dict, lista_bloqueios: list, itens: list, corrompido=None) -> dict:
    """TOTAL de movimentos bancários = liberados (associação confirmada ou suporte independente) + bloqueadores, sem sobreposição,
    e todo bloqueador aparece num item da Central (caminho operacional visível)."""
    todos = {i for x in f.conciliacao["associacoes"] for i in x["bancarios"]}
    liberados = (dcs.bancarios_liberados(f.conciliacao, efetivas) | set(f.suporte)) & todos
    bloq = set(dcs.bloqueios(f.conciliacao, efetivas, f.suporte))
    visiveis = {i["id"] for i in itens}
    return {"movimentos_bancarios": len(todos), "liberados": len(liberados), "bloqueios": len(bloq),
            "ok": bool(corrompido) or (len(todos) == len(liberados) + len(bloq) and not liberados & bloq),
            "todos_visiveis": all(b["associacao"] in visiveis for b in lista_bloqueios) and len(lista_bloqueios) == (len(todos) if corrompido else len(bloq))}


ACAO_BLOQUEIO = {
    "REVISAR": "Abrir e confirmar ou rejeitar a associação sugerida.",
    "AMBIGUO": "Abrir e escolher explicitamente o candidato correto.",
    "AMBIGUO_PARCIAL": "Abrir e escolher entre os candidatos ainda disponíveis.",
    "NAO_CONCILIADO": "Abrir e buscar registros no relatório (associação manual) ou registrar observação — observação não remove o bloqueio.",
    "REJEITADO": "Fornecer suporte ou desfazer a rejeição, se foi engano.",
    "APROVADO": "Abrir e revisar a decisão vigente.",
}


def bloqueios_detalhados(f: Fonte, efetivas: dict, corrompido=None) -> list:
    """REDE DE SEGURANÇA: todo movimento bancário que impede o avanço, um por linha (por MOVIMENTO, não por grupo), com a
    associação em que pode ser tratado, a classificação do motor, o estado operacional do movimento e o que fazer."""
    por_b = {i: x for x in f.conciliacao["associacoes"] for i in x["bancarios"]}
    consumidos = dcs.auxiliares_confirmados(f.conciliacao, efetivas)
    ids = sorted(por_b) if corrompido else dcs.bloqueios(f.conciliacao, efetivas, f.suporte)
    out = []
    for b in ids:
        x = por_b[b]
        ev = efetivas.get(x["id"])
        st = _status(x, ev, consumidos)
        chave = "AMBIGUO_PARCIAL" if dcs.parcial(x, ev) else st
        p = PENDENCIAS.get(chave) or PENDENCIAS.get("NAO_CONCILIADO")
        linha = _banco_linha(f, b)
        out.append({"associacao": x["id"], "data": linha["data"], "valor": linha["valor"], "natureza": linha["natureza"],
                    "descricao": linha["descricao"], "classificacao_motor": x["classificacao"],
                    "estado_operacional": dcs.AGUARDANDO if chave == "AMBIGUO_PARCIAL" else dcs.estado_operacional(x, ev),
                    "situacao": "Ambíguo — parcialmente resolvido" if chave == "AMBIGUO_PARCIAL" else STATUS[st][0],
                    "problema": p[0], "impacto": p[1], "o_que_fazer": p[2], "acao": ACAO_BLOQUEIO.get(chave, ACAO_BLOQUEIO["APROVADO"])})
    out.sort(key=lambda r: (r["data"] or "", r["associacao"]))
    return out


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
    consumidos = dcs.auxiliares_confirmados(f.conciliacao, efetivas)
    item = _item(f, x, ev, consumidos)
    eh_parcial = dcs.parcial(x, ev)
    problema = PENDENCIAS.get("AMBIGUO_PARCIAL" if eh_parcial else item["status"])
    proprios = set((ev or {}).get("candidato_escolhido", {}).get("auxiliares", []) if ev and dcs.escolhas(ev) else [])
    disponiveis = dcs.candidatos_disponiveis(x, ev, consumidos - proprios) if x["classificacao"] == "AMBIGUO" else []
    por_escolha = {dcs.canonico({"b": sorted(e["candidato_escolhido"]["bancarios"]), "a": sorted(e["candidato_escolhido"]["auxiliares"])}): e
                   for e in dcs.escolhas(ev)}
    candidatos = []
    for n, c in enumerate(x.get("candidatos") or [], 1):
        crit = c.get("criterios") or []
        escolha = por_escolha.get(dcs.canonico({"b": sorted(c["bancarios"]), "a": sorted(c["auxiliares"])}))
        escolhido = bool(escolha)
        candidatos.append({"numero": n, "bancarios": c["bancarios"], "auxiliares": c["auxiliares"],
                           "banco": [_banco_linha(f, i) for i in c["bancarios"]], "relatorio": [_aux_linha(f, i) for i in c["auxiliares"]],
                           "explicacao": _explicar(crit, [k for k in cf.TODAS if k not in crit]),
                           "pontuacao": (c.get("score") or {}).get("total"), "escolhido": escolhido,
                           "escolha_evento": escolha["id"] if escolha else None,
                           "disponivel": (not escolhido) and any(dcs._candidato_igual(c, d) for d in disponiveis) and (ev is None or eh_parcial)})
    pode = not corrompido
    n_disp = sum(1 for c in candidatos if c["disponivel"])
    acoes = {"confirmar": pode and x["classificacao"] == "PROVAVEL" and ev is None,
             "rejeitar": pode and x["classificacao"] in ("PROVAVEL", "AMBIGUO") and ev is None,
             "escolher_candidato": pode and x["classificacao"] == "AMBIGUO" and (ev is None or eh_parcial) and n_disp > 0,
             "desfazer": pode and ev is not None and not dcs.escolhas(ev),      # AMBIGUO: desfazer por escolha (no candidato)
             "desfazer_escolha": pode and bool(dcs.escolhas(ev)),
             "observacao": pode and ((x["classificacao"] == "NAO_CONCILIADO" and ev is None) or eh_parcial),
             "buscar_manual": pode and x["classificacao"] == "NAO_CONCILIADO" and len(x["bancarios"]) == 1 and not x["auxiliares"] and ev is None}
    historico = [_evento_tela(e) for e in dados["eventos"] if e["associacao"] == x["id"]]
    return dict(item, motivo=x.get("motivo"),
                explicacao=_explicar(x.get("criterios_atendidos") or [], x.get("criterios_ausentes") or []) if x["classificacao"] in ("CONCILIADO", "PROVAVEL") else [],
                pontuacao=(x.get("score") or {}).get("total") if x["classificacao"] in ("CONCILIADO", "PROVAVEL") else None,
                candidatos=candidatos, acoes=acoes, historico=historico,
                pendencia={"problema": problema[0], "impacto": problema[1], "o_que_fazer": problema[2]} if problema else None,
                aviso_candidatos=(None if not eh_parcial else
                                  "Após a decisão anterior, resta 1 associação possível. A confirmação continua sendo sua." if n_disp == 1 else
                                  f"Após a decisão anterior, restam {n_disp} associações possíveis." if n_disp > 1 else
                                  "Nenhum candidato original continua disponível para o movimento restante. Ele continua bloqueando; "
                                  "registre uma observação ou desfaça uma escolha se ela estiver errada."),
                decisao=_evento_tela(ev) if ev else None,
                revisao_conciliacao=dcs.revisao_conciliacao(f.conciliacao), revisao_decisoes=dcs.revisao_decisoes(dados),
                aviso_efeito=dcs.EFEITO)


ACOES_TEXTO = {dcs.APROVADO: "Confirmou associação", dcs.REJEITADO: "Rejeitou associação", dcs.REVOGADO: "Desfez decisão",
               dcs.OBSERVACAO: "Registrou observação"}


def _evento_tela(e: dict) -> dict:
    manual = e.get("associacao_manual")
    return {"manual": {"quantidade": manual["quantidade"], "soma": manual["soma_relatorio"], "valor_bancario": manual["valor_bancario"],
                       "diferenca": manual["diferenca"]} if manual else None, **_evento_base(e)}


ACOES_MANUAL = {dcs.APROVADO: "Confirmou associação manual"}


def _evento_base(e: dict) -> dict:
    return {"em": e["em"], "responsavel": e["responsavel"],
            "acao": ACOES_MANUAL[e["decisao"]] if e.get("origem") == dcs.ORIGEM_MANUAL else ACOES_TEXTO[e["decisao"]], "decisao": e["decisao"],
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
                       "acao": _evento_base(e)["acao"] + (" em lote" if e["lote"] else ""), "quantidade": 1,
                       "justificativa": e["justificativa"], "itens": [_evento_tela(e)]})
    for g in grupos:
        g.pop("chave")
    return {"disponivel": True, "total_eventos": len(dados["eventos"]), "grupos": list(reversed(grupos))}


def decidir(f: Fonte, pedidos: list, corpo: dict, origem: str) -> list:
    return dcs.decidir_e_gravar(f.caminho, f.contexto, f.conciliacao, pedidos, revisao_conciliacao_cliente=corpo.get("revisao_conciliacao"),
                                revisao_decisoes_cliente=corpo.get("revisao_decisoes"), justificativa=corpo.get("justificativa"),
                                origem=origem, registros=f.auxiliares)


# ---------------------------------------------------------------- busca assistida para associação manual (NAO_CONCILIADO)
LIMITE_CANDIDATOS_BUSCA = 40      # combinações só entre os 40 registros elegíveis mais próximos na data (proteção)
LIMITE_COMBINACOES = 20           # no máximo 20 sugestões exibidas
LIMITE_PASSOS = 300_000           # orçamento de busca; esgotado → busca marcada como incompleta (nunca silenciosa)
DIAS_ALERTA = 15                  # acima disso: "Atenção: data distante do movimento bancário."


def _data(t):
    try:
        return dt.date.fromisoformat(str(t)[:10]) if t else None
    except ValueError:
        return None


def _centavos(v) -> int:
    d = Decimal(str(v))
    if d != d.quantize(Decimal("0.01")):
        raise ValueError("valor com mais de duas casas")
    return int(d * 100)


def combinacoes_exatas(alvo: int, valores: list, maximo: int = dcs.LIMITE_MANUAL, limite: int = LIMITE_COMBINACOES,
                       passos: int = LIMITE_PASSOS) -> tuple:
    """Subconjuntos de até `maximo` índices cuja soma em CENTAVOS é exatamente `alvo`. Busca em profundidade com poda (só valores
    positivos e soma parcial ≤ alvo), na ordem dada (determinística). Devolve (combinações, completa)."""
    achadas, cont = [], [0]
    ordem = [i for i, v in enumerate(valores) if 0 < v <= alvo]

    def dfs(inicio, soma, escolhidos):
        for pos in range(inicio, len(ordem)):
            cont[0] += 1
            if cont[0] > passos or len(achadas) >= limite:
                return
            i = ordem[pos]
            s = soma + valores[i]
            if s == alvo:
                achadas.append(escolhidos + [i])
            elif s < alvo and len(escolhidos) + 1 < maximo:
                dfs(pos + 1, s, escolhidos + [i])
    dfs(0, 0, [])
    return achadas, cont[0] <= passos


def busca_manual(f: Fonte, assoc_id: str):
    """Registros do relatório (MESMA conciliação/tentativa) que podem compor uma associação manual para um movimento bancário
    NAO_CONCILIADO, e as combinações de soma EXATA (até 5). Somente leitura: não decide nem grava nada."""
    x = next((a for a in f.conciliacao["associacoes"] if a["id"] == assoc_id), None)
    if not x:
        return None
    try:
        dados = dcs.carregar(f.caminho, f.contexto)
    except dcs.EstadoCorrompido:
        return {"disponivel": False, "motivo": "Registro de decisões inconsistente; busca indisponível. Avise o responsável técnico."}
    efetivas, _ = dcs.decisoes_efetivas(dados, f.conciliacao)
    if x["classificacao"] != "NAO_CONCILIADO" or len(x["bancarios"]) != 1 or x["auxiliares"] or efetivas.get(x["id"]):
        return {"disponivel": False, "motivo": "A busca de registros é só para movimento do banco sem associação e sem decisão vigente."}
    banco = _banco_linha(f, x["bancarios"][0])
    natureza = dcs.NATUREZA_COMPATIVEL.get(x.get("natureza_bancaria"))
    alvo = _centavos(x["valor_bancario"])
    data_b = _data(banco.get("data"))
    consumidos = dcs.auxiliares_confirmados(f.conciliacao, efetivas)
    pendentes = {i for a in f.conciliacao["associacoes"] if a["classificacao"] in ("PROVAVEL", "AMBIGUO") and not efetivas.get(a["id"])
                 for i in a["auxiliares"]}
    candidatos, ignorados = [], {"natureza": 0, "indisponivel": 0, "sem_rastreio": 0}
    for i in sorted(dcs.universo_auxiliar(f.conciliacao)):
        a = f.auxiliares.get(i) or {}
        if a.get("natureza") != natureza:
            ignorados["natureza"] += 1
            continue
        if i in consumidos:
            ignorados["indisponivel"] += 1
            continue
        if not (a.get("sha") or a.get("sha256")):
            ignorados["sem_rastreio"] += 1
            continue
        d = _data(a.get("data_quitacao") or a.get("data"))
        dias = abs((d - data_b).days) if d and data_b else None
        linha = _aux_linha(f, i)
        candidatos.append(dict(linha, id=i, centavos=_centavos(a.get("valor")), dias=dias,
                               data_origem="data de quitação" if a.get("data_quitacao") else "data do lançamento (sem quitação)",
                               plano_contas=a.get("plano_contas"), banco_relatorio=a.get("banco"),
                               alerta_data=dias is None or dias > DIAS_ALERTA, sugerido_em_outra=i in pendentes,
                               valor_exato=_centavos(a.get("valor")) == alvo))
    candidatos.sort(key=lambda c: (c["dias"] if c["dias"] is not None else 10 ** 6, c["id"]))
    base = candidatos[:LIMITE_CANDIDATOS_BUSCA]
    achadas, completa = combinacoes_exatas(alvo, [c["centavos"] for c in base])
    combos = []
    for idx in achadas:
        regs = [base[k] for k in idx]
        combos.append({"quantidade": len(regs), "registros": [r["id"] for r in regs], "total": f"{sum(r['centavos'] for r in regs) / 100:.2f}",
                       "diferenca": "0.00", "dias_maximo": max((r["dias"] or 0) for r in regs),
                       "com_alerta_data": any(r["alerta_data"] for r in regs), "com_sugestao_pendente": any(r["sugerido_em_outra"] for r in regs)})
    combos.sort(key=lambda c: (c["quantidade"], c["dias_maximo"], c["registros"]))
    for c in candidatos:
        c.pop("centavos")
    return {"disponivel": True, "associacao": x["id"], "banco": banco, "valor_banco": x["valor_bancario"], "natureza_relatorio": natureza,
            "candidatos": candidatos, "combinacoes": combos, "limite_manual": dcs.LIMITE_MANUAL,
            "busca_completa": completa and len(candidatos) <= LIMITE_CANDIDATOS_BUSCA and len(achadas) < LIMITE_COMBINACOES,
            "explicacao": [f"Aparecem só registros do relatório desta mesma conferência com natureza compatível ({'recebimentos' if natureza == 'ENTRADA' else 'pagamentos'}), "
                           "ainda não usados em outra associação confirmada e com origem rastreável.",
                           "A lista está ordenada pela proximidade de data; registros fora da janela automática também aparecem para investigação.",
                           f"As combinações somam exatamente o valor do banco, com até {dcs.LIMITE_MANUAL} registros, e consideram os "
                           f"{LIMITE_CANDIDATOS_BUSCA} registros mais próximos na data. São sugestões para revisão: nenhuma é escolhida pelo sistema.",
                           f"Registros com mais de {DIAS_ALERTA} dias de diferença aparecem com alerta de data distante."],
            "ignorados": ignorados, "revisao_conciliacao": dcs.revisao_conciliacao(f.conciliacao), "revisao_decisoes": dcs.revisao_decisoes(dados),
            "aviso_efeito": dcs.EFEITO}
