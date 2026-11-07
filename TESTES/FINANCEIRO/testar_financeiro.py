"""Bateria do fluxo Financeiro → Contabilidade/Bancos (SIMULAÇÃO), somente com dados FICTÍCIOS.

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/FINANCEIRO/testar_financeiro.py

Cria a empresa fictícia temporária EMPRESA-FIN-TMP (cópia de EMPRESA-DEMO-FINANCEIRO) num CLIENTES TEMPORÁRIO, runtime e registro
temporários; o Agente de Documentos é substituído por um executor simulado (sem Claude). Ao final remove SOMENTE o que
criou (a empresa temporária, por nome). Não toca documentos reais, o registro real nem a API em execução.
"""

import base64
import hashlib
import http.client
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request as urllib_req
from pathlib import Path
from urllib.parse import quote

RAIZ = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="fin-prime-"))
os.environ["AGENTES_PRIME_RUNTIME"] = str(TMP / "runtime")
os.environ["AGENTES_PRIME_REGISTRO_SOL"] = str(TMP / "solicitacoes.json")
os.environ["AGENTES_PRIME_ORDEM_ATIVA"] = str(TMP / "ordem-ativa.json")
# CLIENTES, LIBERADOS e LOCALAPPDATA também temporários: o teste nunca grava no CLIENTES/ operacional
os.environ["AGENTES_PRIME_CLIENTES"] = str(TMP / "CLIENTES")
os.environ["AGENTES_PRIME_LIBERADOS"] = str(TMP / "LIBERADOS")
os.environ["LOCALAPPDATA"] = str(TMP / "localappdata")
(TMP / "CLIENTES").mkdir()
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(RAIZ / "TESTES" / "FINANCEIRO"))
import gerar_fixtures_financeiro as gf  # noqa: E402
import servidor  # noqa: E402
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado as _ai  # noqa: E402

PY = sys.executable
EMPRESA = "EMPRESA-FIN-TMP"
CLIENTES = TMP / "CLIENTES"
BASE = CLIENTES / EMPRESA
DEMO = RAIZ / "TESTES" / "FINANCEIRO" / "FIXTURE-EMPRESA-DEMO"
# empresas auxiliares temporárias (fictícias), criadas e removidas por este teste
ISOLAMENTO = CLIENTES / "EMPRESA-ISOLAMENTO-TMP"   # outra empresa cadastrada (CNPJ 99.999.999/9999-99)
REAL = CLIENTES / "EMPRESA-REAL-TMP"               # empresa "real" sem piloto Financeiro/Bancos
ORDEM = Path(os.environ["AGENTES_PRIME_ORDEM_ATIVA"])
FIN = RAIZ / "AGENTES" / "FINANCEIRO" / "ferramentas" / "conferencia_financeira.py"
BAN = RAIZ / "AGENTES" / "CONTABILIDADE" / "BANCOS" / "ferramentas" / "lancamentos_bancarios.py"
COORD = RAIZ / "COORDENADOR-GERAL" / "ferramentas" / "coordenador.py"
resultados = []

RELATORIO = """<!-- RELATÓRIO FICTÍCIO DO EXECUTOR SIMULADO (teste; não produzido pelo Agente de Documentos) -->
▶ EMPRESA: EMPRESA-FIN-TMP | CNPJ: 44.444.444/0001-44 | COMPETÊNCIA: 2026-09 | MODO: SIMULAÇÃO
RELATÓRIO DO AGENTE DE DOCUMENTOS - {sol}

## 1. Inventário
| # | Arquivo | Tamanho (bytes) | SHA-256 (12 primeiros) | Leitura (código do extrator) | Marcações | Partes recebidas/total | Analisado? |
|---|---|---|---|---|---|---|---|
| 1 | extratos, relação, comprovantes e suportes | 1 | x | EXTRAIDO_TEXTO | nenhuma | 1/1 | SIM |

## 5. Pendências propostas (para PENDENCIAS.md - gravação pelo Coordenador)
| Nº provisório | Competência | Tipo | Descrição | Documento | Responsável sugerido | Status sugerido |
|---|---|---|---|---|---|---|
| P-02 | 2026-09 | Divergência | Saldos dos dois extratos da conta 001/1234/11111-1 não fecham entre si | Docs 1 e 2 | Supervisor | Aguardando informação |
| P-03 | 2026-09 | Divergência | PIX BETA de 10/09 está no extrato completo e falta no extrato até 10/09 | Docs 1 e 2 | Supervisor | Aguardando informação |
| P-09 | 2026-09 | Identificação/Titularidade | Extrato da conta 341/9999/55555-5 fora das contas do CADASTRO | 13_13_extrato_341_55555-5_outra_empresa.ofx | Supervisor | Aguardando informação |
| P-10 | 2026-09 | Identificação/Titularidade | Comprovante com pagador de outro CNPJ | 14_14_comprovante_outra_empresa.txt | Supervisor | Aguardando informação |
| P-11 | 2026-09 | Divergência | Relação informa GAMA NF 4001 450,00 sem débito no extrato | Doc 4 | Supervisor | Aguardando informação |

## 6. Documentos não analisados
| Arquivo | Código do extrator | Motivo (observação do extrator) | Pendência proposta |
|---|---|---|---|
| 15_15_recibo_digitalizado.png | DOCUMENTO_REQUER_OCR | imagem sem camada de texto | P-12 |

## 7. Tarefas da ordem de serviço
| Tarefa | Situação | Observação |
|---|---|---|
| (1) Inventário | EXECUTADA | — |
"""


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), detalhe))


def remover(pasta: Path):
    def forcar(f, c, _e):
        os.chmod(c, stat.S_IWRITE | stat.S_IREAD)
        f(c)
    if pasta.exists():
        for p in pasta.rglob("*"):
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
        shutil.rmtree(pasta, onexc=forcar)


def confirmar_regras_validadas():
    """A fixture marca regras como VALIDADA com texto livre ("exemplo fictício"). O contrato atual (governanca_regras) só aplica
    VALIDADA com confirmação ESTRUTURADA vinculada a empresa, regra e versão; a cópia temporária recebe essa confirmação (a
    regra de negócio não é afrouxada; a fixture passa a representar o contrato vigente)."""
    sys.path.insert(0, str(RAIZ / "AGENTES" / "CONTABILIDADE"))
    import governanca_regras as gr
    import datetime as dt_
    arq = BASE / "REGRAS-BANCOS.md"
    linhas = []
    for l in arq.read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in l.strip().strip("|").split("|")] if l.startswith("| RB-") else None
        if c and len(c) >= 10 and c[8] == "VALIDADA":
            c[9] = gr.texto_confirmacao_bancos(EMPRESA, c[0], c[1], dt_.datetime(2026, 11, 7, 9, 0).astimezone().isoformat(timespec="seconds"))
            l = "| " + " | ".join(c) + " |"
        linhas.append(l)
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def preparar_empresa():
    """Empresa fictícia temporária: mesmos contas, plano e regras da demonstração, com identificador próprio."""
    shutil.copytree(DEMO, BASE, ignore=shutil.ignore_patterns("RECEBIDOS", "TESTE-*"))
    confirmar_regras_validadas()
    cad = BASE / "CADASTRO.md"
    cad.write_text(cad.read_text(encoding="utf-8").replace("EMPRESA-DEMO-FINANCEIRO", EMPRESA)
                   .replace("EMPRESA DEMONSTRACAO FINANCEIRO FICTICIA LTDA", "EMPRESA FIN TMP FICTICIA LTDA"), encoding="utf-8")
    ISOLAMENTO.mkdir()
    (ISOLAMENTO / "CADASTRO.md").write_text(
        "# CADASTRO - EMPRESA-ISOLAMENTO-TMP\n\n> EMPRESA FICTÍCIA temporária do teste de isolamento.\n\n## Identificação\n"
        "- Razão social: EMPRESA ISOLAMENTO FICTICIA LTDA\n- CNPJ (matriz): 99.999.999/9999-99\n\n## Situação\n"
        "- Status: SOMENTE TESTE\n- Liberação de lançamentos reais: BLOQUEADA\n", encoding="utf-8")
    REAL.mkdir()
    (REAL / "CADASTRO.md").write_text(
        "# CADASTRO - EMPRESA-REAL-TMP\n\n## Identificação\n- Razão social: CLIENTE REAL SIMULADO LTDA\n"
        "- CNPJ (matriz): 12.345.678/0001-95\n\n## Situação\n- Status: CONFIGURAÇÃO\n"
        "- Agente de Documentos: PILOTO SUPERVISIONADO AUTORIZADO\n- Liberação de lançamentos reais: BLOQUEADA\n", encoding="utf-8")


def rodar(lote: str, saida: Path, ja=None, decisoes=None, empresa=EMPRESA, sol="SOL-2026-900001"):
    saida.mkdir(parents=True, exist_ok=True)
    extra = []
    if ja is not None:
        (saida / "ja.json").write_text(json.dumps(ja), encoding="utf-8")
        extra += ["--ja-tratados", str(saida / "ja.json")]
    if decisoes is not None:
        (saida / "dec.json").write_text(json.dumps(decisoes), encoding="utf-8")
        extra += ["--decisoes", str(saida / "dec.json")]
    p = subprocess.run([PY, "-I", str(FIN), "--empresa", empresa, "--sol", sol, "--competencia", "2026-09", "--pasta", lote,
                        "--saida", str(saida / "fin"), *extra], cwd=RAIZ, capture_output=True, encoding="utf-8")
    if p.returncode != 0:
        return p.returncode, None, None
    b = subprocess.run([PY, "-I", str(BAN), "--empresa", empresa, "--sol", sol, "--competencia", "2026-09",
                        "--financeiro", str(saida / "fin" / "resultado.json"), "--saida", str(saida / "ban"),
                        *(["--decisoes", str(saida / "dec.json")] if decisoes is not None else [])],
                       cwd=RAIZ, capture_output=True, encoding="utf-8")
    fin = json.loads((saida / "fin" / "resultado.json").read_text(encoding="utf-8"))
    ban = json.loads((saida / "ban" / "resultado.json").read_text(encoding="utf-8")) if b.returncode == 0 else None
    return 0, fin, ban


def por_fitid(fin, fitid):
    return next(m for m in fin["movimentos"] if m["identificadores"].get("FITID") == fitid)


def lanc(ban, mov_id):
    return next((l for l in ban["lancamentos"] if mov_id in l["movimentos"]), None)


def codigo(conta):
    return (conta or {}).get("codigo")


# ---------------------------------------------------------------- motores (Financeiro e Bancos)

def bateria_motores():
    gf.gerar(BASE / "TESTE-LOTE")
    gf.gerar_incompleto(BASE / "TESTE-INCOMPLETO")
    sug = BASE / "TESTE-SUGESTAO"
    sug.mkdir()
    (sug / "01_extrato.ofx").write_bytes(gf.ofx("001", "1234", "11111-1", "20260901", "20260930",
                                                [("DEBIT", "20260903", "-999.00", "S001", "PAGTO SERVICO")], "1.00"))
    (sug / "02_comprovante.txt").write_bytes(gf.comprovante(gf.BETA, "04/09/2026", "999,00", "AUTENTICACAO", "AUTSUG"))
    c, fin, ban = rodar("TESTE-LOTE", TMP / "u1")
    m = {f: por_fitid(fin, f) for f in ("F001", "F002", "F003", "F004", "F005", "F006", "F007", "F008", "F009", "F010", "F011", "F012")}

    l1 = lanc(ban, m["F001"]["id"])
    registrar("F-01 pagamento com suporte completo (extrato × relação × comprovante × NF): confirmado e lançamento proposto",
              m["F001"]["situacao"] == "COM_SUPORTE" and m["F001"]["conferencia"] == {"relacao": "SIM", "comprovante": "SIM", "natureza": "SIM"}
              and l1["status"] == "PROPOSTO" and codigo(l1["debito"]) == "2101" and codigo(l1["credito"]) == "5"
              and {d["papel"] for d in l1["documentos"]} == {"LIQUIDACAO", "NATUREZA"} and l1["regra"]["id"] == "RB-001",
              "; ".join(m["F001"]["fundamentos"])[:150])
    l2 = lanc(ban, m["F002"]["id"])
    registrar("F-02 pagamento sem suporte: não desaparece; segue à Contabilidade como INCOMPLETO com pendência",
              m["F002"]["situacao"] == "SEM_SUPORTE" and l2 and l2["status"] == "INCOMPLETO" and l2["debito"] is None
              and any("sem documento de suporte" in p for p in l2["pendencias"]))
    registrar("F-03 comprovante sem documento da natureza: liquidação comprovada, natureza ausente (não é despesa comprovada)",
              m["F003"]["situacao"] == "COMPROVANTE_SEM_NATUREZA" and m["F003"]["conferencia"]["comprovante"] == "SIM"
              and m["F003"]["conferencia"]["natureza"] == "NAO")
    gama = [x for x in fin["relacionados_sem_movimento"] if x["tipo"] == "RELACAO" and "GAMA" in x["favorecido"]]
    registrar("F-04 item da relação sem liquidação no extrato: listado à parte (a relação não comprova pagamento)",
              len(gama) == 1 and gama[0]["valor"] == "450.00" and not any("GAMA" in " ".join(x["descricao"] for x in [mm]) for mm in fin["movimentos"]))
    registrar("F-05 pagamento agrupado (2 NFs, 1 débito) e parciais (1 NF, 2 débitos) vinculados por referência explícita",
              len(m["F004"]["relacao"]) == 2 and len(m["F004"]["suportes"]) == 2 and m["F004"]["situacao"] == "COM_SUPORTE"
              and m["F005"]["suportes"] == m["F006"]["suportes"] and len(m["F005"]["suportes"]) == 1
              and "parcial_ou_agrupado" in m["F005"] and not m["F005"]["divergencias"]
              and lanc(ban, m["F005"]["id"])["status"] == lanc(ban, m["F006"]["id"])["status"] == "PROPOSTO", m["F005"].get("parcial_ou_agrupado", ""))
    amb = [a for a in fin["ambiguas"] if a["tipo"] == "COMPROVANTE"]
    registrar("F-06 correspondência ambígua: sem escolha automática; exige conferência do Supervisor",
              m["F007"]["situacao"] == m["F008"]["situacao"] == "AMBIGUO" and not m["F007"]["comprovantes"] and not m["F008"]["comprovantes"]
              and len(amb) == 1 and set(amb[0]["candidatos"]) == {m["F007"]["id"], m["F008"]["id"]}
              and all(not x["id"] == amb[0]["origem"] for x in fin["relacionados_sem_movimento"]))
    sobre = [d for d in fin["duplicidades"] if d["tipo"] == "SOBREPOSICAO_DE_EXTRATOS"]
    contagem = [x["identificadores"].get("FITID") for x in fin["movimentos"]].count("F001")
    registrar("F-07 movimento repetido por sobreposição de extratos: contado UMA vez e reportado como duplicidade",
              len(sobre) == 2 and contagem == 1 and len(m["F001"]["origens"]) == 2)
    l9 = lanc(ban, m["F009"]["id"])
    credito_b = next(x for x in fin["movimentos"] if x["conta"].startswith("237") and x["direcao"] == "CREDITO")
    registrar("F-08 transferência entre contas próprias: duas pontas vinculadas, UM lançamento (sem dupla contabilização)",
              m["F009"]["situacao"] == credito_b["situacao"] == "TRANSFERENCIA_PROPRIA" and l9["movimentos"] == [m["F009"]["id"], credito_b["id"]]
              and codigo(l9["debito"]) == "6" and codigo(l9["credito"]) == "5" and lanc(ban, credito_b["id"]) is l9
              and sum(1 for l in ban["lancamentos"] if credito_b["id"] in l["movimentos"]) == 1)
    l10 = lanc(ban, m["F010"]["id"])
    registrar("F-09 pagamento de obrigação já contabilizada (DARF): só liquidação (2102), regra de despesa desconsiderada",
              l10["status"] == "PROPOSTO" and codigo(l10["debito"]) == "2102" and l10["tipo"] == "LIQUIDACAO_OBRIGACAO"
              and not any(codigo(l["debito"]) == "4104" for l in ban["lancamentos"])
              and any("RB-003" in p["descricao"] and "segunda despesa" in p["descricao"] for p in ban["pendencias"]))
    l3 = lanc(ban, m["F003"]["id"])
    codigos = {codigo(l["debito"]) for l in ban["lancamentos"]} | {codigo(l["credito"]) for l in ban["lancamentos"]}
    registrar("F-10 ausência de regra ou de conta: proposta incompleta com pendência; nenhuma conta inventada/transitória",
              l2["status"] == "INCOMPLETO" and any("Sem regra aprovada" in p for p in l2["pendencias"])
              and l3["status"] == "INCOMPLETO" and l3["debito"] is None and any("9999" in p for p in l3["pendencias"])
              and codigos - {None} <= {"5", "6", "2101", "2102", "4102", "4103", "4104"})
    c2, fin_i, _ = rodar("TESTE-INCOMPLETO", TMP / "u2")
    v = fin_i["verificacao_extratos"][0]
    tipos = {p["tipo"] for p in fin_i["pendencias"]}
    registrar("F-11 extrato incompleto: cobertura e saldos não fecham → verificação NÃO concluída, com pendências",
              v["situacao"] == "INCOMPLETA" and v["cobertura_competencia"] == "INCOMPLETA" and v["extratos"][0]["aritmetica"] == "DIVERGENTE"
              and {"EXTRATO_INCOMPLETO", "EXTRATO_INCONSISTENTE"} <= tipos, v["extratos"][0].get("diferenca"))
    contas = {x["conta"] for x in fin["movimentos"]}
    p = subprocess.run([PY, "-I", str(FIN), "--empresa", ISOLAMENTO.name, "--sol", "SOL-2026-900001", "--competencia", "2026-09",
                        "--pasta", "TESTE-LOTE", "--saida", str(TMP / "u3")], cwd=RAIZ, capture_output=True, encoding="utf-8")
    registrar("F-12 isolamento: conta de outro titular e comprovante de outra empresa não usados; outra empresa não lê esta pasta",
              not any(c.startswith("341") for c in contas) and any(x["tipo"] == "CONTA_NAO_CADASTRADA" for x in fin["pendencias"])
              and any(x["tipo"] == "ISOLAMENTO" and "EMPRESA-ISOLAMENTO" in x["descricao"] for x in fin["pendencias"])
              and p.returncode != 0 and not (TMP / "u3" / "resultado.json").exists())
    registrar("F-13 créditos, tarifas e demais movimentos aparecem; nada é classificado só pelo histórico",
              m["F012"]["direcao"] == "CREDITO" and m["F012"]["situacao"] == "SEM_SUPORTE" and m["F011"]["tipo_banco"] == "FEE"
              and lanc(ban, m["F011"]["id"])["status"] == "INCOMPLETO" and lanc(ban, m["F012"]["id"])["status"] == "INCOMPLETO")
    registrar("F-14 documento digitalizado/ilegível: pendência explícita, nada inventado",
              any(x["tipo"] == "DOCUMENTO_ILEGIVEL" and "15_recibo_digitalizado.png" in x["descricao"] for x in fin["pendencias"]))
    c4, fin_s, _ = rodar("TESTE-SUGESTAO", TMP / "u4")
    ms = fin_s["movimentos"][0]
    registrar("F-15 sem tolerância de data: mesmo valor com data diferente vira SUGESTÃO, separada do confirmado",
              ms["situacao"] == "SEM_SUPORTE" and not ms["comprovantes"] and len(fin_s["sugestoes"]) == 1 and "não confirmado" in fin_s["sugestoes"][0]["descricao"])
    c5, fin2, _ = rodar("TESTE-LOTE", TMP / "u5")
    registrar("F-16 identificador estável da movimentação (mesmos documentos → mesmos ids)",
              [x["id"] for x in fin2["movimentos"]] == [x["id"] for x in fin["movimentos"]])
    ja = {"escriturados": {m["F001"]["id"]: {"sol": "SOL-2026-000001", "lancamento": "LAN-001", "em": "2026-10-31"}},
          "propostas_simulacao": {m["F002"]["id"]: [{"sol": "SOL-2026-000001", "tentativa": 1, "em": "2026-10-31"}]}}
    c6, fin3, ban3 = rodar("TESTE-LOTE", TMP / "u6", ja=ja)
    l2r = lanc(ban3, m["F002"]["id"])
    registrar("F-17 escriturado ≠ proposta em simulação: só o ESCRITURADO bloqueia; proposta anterior gera REVISÃO rastreável",
              lanc(ban3, m["F001"]["id"]) is None and any(n["movimento"] == m["F001"]["id"] and "ESCRITURADO" in n["motivo"] for n in ban3["nao_escriturados"])
              and l2r is not None and l2r["revisao_de"] == [{"sol": "SOL-2026-000001", "tentativa": 1, "em": "2026-10-31"}]
              and all(l["natureza_registro"] == "PROPOSTA_SIMULACAO" for l in ban3["lancamentos"])
              and fin3["resumo"]["ja_escriturados"] == 1 and fin3["resumo"]["com_proposta_anterior_simulacao"] == 1)
    registrar("F-18 conferência não é apresentada como conciliação contábil completa; resultado com empresa, competência e conta",
              "NÃO é conciliação contábil completa" in fin["aviso"] and all(x["empresa"] == EMPRESA and x["competencia"] == "2026-09" and x["conta"]
                                                                              for x in fin["movimentos"]))
    div = [x for x in fin["pendencias"] if x["tipo"] == "DIVERGENCIA_ENTRE_EXTRATOS"]
    registrar("F-20 divergência entre extratos sobrepostos: movimento do período comum ausente em um deles vira pendência do movimento",
              len(div) == 1 and div[0]["referencia"] == m["F003"]["id"]
              and any("divergência entre extratos" in x for x in m["F003"]["divergencias"])
              and lanc(ban, m["F003"]["id"])["status"] == "INCOMPLETO" and not fin["bloqueio_lote"], div[0]["descricao"][:120] if div else "")
    dec = {m["F003"]["id"]: [{"tipo": "CONTRAPARTIDA", "conta": "4103", "natureza_tipo": "DESPESA", "justificativa": "teste", "em": "2026-10-31"}],
           m["F012"]["id"]: [{"tipo": "CONTRAPARTIDA", "conta": "4103", "natureza_tipo": "RECEITA", "justificativa": "teste", "em": "2026-10-31"}]}
    c8, fin8, ban8 = rodar("TESTE-LOTE", TMP / "u8", decisoes=dec)
    l800, l3000 = lanc(ban8, m["F003"]["id"]), lanc(ban8, m["F012"]["id"])
    registrar("F-21 contrapartida decidida não resolve documento: R$ 800 (DESPESA 4103) segue sem natureza e com divergência; "
              "R$ 3.000 com 4103 (despesa) como RECEITA é recusado pelo motor: sem contrapartida, segue sem origem",
              l800["status"] == l3000["status"] == "INCOMPLETO" and codigo(l800["debito"]) == "4103" and l3000["credito"] is None
              and set(l800["faltas_codigos"]) == {"SUPORTE", "DIVERGENCIA", "LEITURA_PENDENTE"} and set(l3000["faltas_codigos"]) == {"SUPORTE", "INCOMPATIVEL", "LEITURA_PENDENTE"}
              and any("sem documento da natureza" in x and "não supre o documento" in x for x in l800["pendencias"])
              and any("comprove a origem" in x for x in l3000["pendencias"])
              and any("4103" in x and "não é compatível" in x for x in l3000["pendencias"]),
              f"800 {l800['faltas_codigos']} · 3000 {l3000['faltas_codigos']}")
    # F-22: compatibilidade conta × natureza no motor (mesmo que a decisão chegue sem passar pelo Coordenador)
    dec_banco = {m["F003"]["id"]: [{"tipo": "CONTRAPARTIDA", "conta": "5", "natureza_tipo": "DESPESA", "justificativa": "teste", "em": "2026-10-31"}],
                 m["F012"]["id"]: [{"tipo": "CONTRAPARTIDA", "conta": "2101", "natureza_tipo": "RECEBIMENTO", "justificativa": "teste", "em": "2026-10-31"}]}
    _, _, ban9 = rodar("TESTE-LOTE", TMP / "u9", decisoes=dec_banco)
    plano = BASE / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md"
    plano_original = plano.read_text(encoding="utf-8")
    plano.write_text(plano_original.replace("| DESPESAS GERAIS | DESPESA |", "| DESPESAS GERAIS |  |"), encoding="utf-8")
    try:
        _, _, ban10 = rodar("TESTE-LOTE", TMP / "u10", decisoes={m["F003"]["id"]: dec[m["F003"]["id"]]})
    finally:
        plano.write_text(plano_original, encoding="utf-8")
    b800, b3000, g800 = lanc(ban9, m["F003"]["id"]), lanc(ban9, m["F012"]["id"]), lanc(ban10, m["F003"]["id"])
    registrar("F-22 motor recusa contrapartida incompatível (conta bancária; PASSIVO como RECEBIMENTO) e, sem grupo no plano, "
              "mantém pendente explicando o que o Supervisor precisa definir",
              b800["debito"] is None and "INCOMPATIVEL" in b800["faltas_codigos"] and any("conta bancária" in x or "não é compatível" in x for x in b800["pendencias"])
              and b3000["credito"] is None and "INCOMPATIVEL" in b3000["faltas_codigos"]
              and g800["debito"] is None and "GRUPO_INDEFINIDO" in g800["faltas_codigos"]
              and any("O Supervisor precisa definir o grupo" in x for x in g800["pendencias"])
              and plano.read_text(encoding="utf-8") == plano_original,
              f"{b800['faltas_codigos']} · {b3000['faltas_codigos']} · {g800['faltas_codigos']}")
    # F-19: valor e data iguais não bastam; titularidade e identificador comum são exigidos
    ev = BASE / "TESTE-EVIDENCIA"
    ev.mkdir()
    (ev / "01_extrato.ofx").write_bytes(gf.ofx("001", "1234", "11111-1", "20260901", "20260930", [
        ("DEBIT", "20260906", "-777.00", "E001", "PAGAMENTO DIVERSOS"),
        ("DEBIT", "20260907", "-555.00", "E002", "PIX ENVIADO BETA"),
        ("DEBIT", "20260908", "-333.00", "E003", "PIX ENVIADO DELTA")], "1.00"))
    (ev / "02_comprovante_sem_identificador.txt").write_bytes(gf.comprovante(("OMEGA PRESTADOR FICTICIO", None), "06/09/2026", "777,00", "AUTENTICACAO", "AUTX777"))
    sem_pagador = "\r\n".join(["COMPROVANTE DE PAGAMENTO - DOCUMENTO FICTICIO", f"FAVORECIDO: {gf.BETA[0]}", "DATA DO PAGAMENTO: 07/09/2026",
                               "VALOR PAGO: R$ 555,00", "AUTENTICACAO: AUTX555"]).encode("cp1252")
    (ev / "03_comprovante_sem_pagador.txt").write_bytes(sem_pagador)
    (ev / "04_relacao_sem_conta.csv").write_bytes(("data_pagamento;favorecido;cnpj_cpf;valor;documentos\r\n"
                                                   f"08/09/2026;{gf.DELTA[0]};{gf.DELTA[1]};333,00;NF 9001\r\n").encode("cp1252"))
    c7, fin_e, _ = rodar("TESTE-EVIDENCIA", TMP / "u7")
    me = {x["identificadores"]["FITID"]: x for x in fin_e["movimentos"]}
    registrar("F-19 vínculo exige titularidade e identificador: só valor e data iguais → SUGESTÃO (sem identificador, sem pagador, sem conta)",
              not any(x["comprovantes"] or x["relacao"] for x in me.values())
              and "identificador comum" in " ".join(me["E001"]["sugestoes"]) and "titularidade" in " ".join(me["E002"]["sugestoes"])
              and "conta pagadora" in " ".join(me["E003"]["sugestoes"]) and len(fin_e["sugestoes"]) == 3
              and all(x["situacao"] == "SEM_SUPORTE" for x in me.values()),
              " | ".join(s["descricao"][:70] for s in fin_e["sugestoes"]))
    return m


# ---------------------------------------------------------------- Coordenador e API (executor simulado no lugar do Claude)

def pedido(metodo, rota, corpo=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", PORTA, timeout=60)
    h = {"X-Prime-Sessao": SRV.token}
    h.update(cab or {})
    if isinstance(corpo, dict):
        corpo = json.dumps(corpo).encode()
        h["Content-Type"] = "application/json"
    c.request(metodo, rota, body=corpo, headers=h)
    r = c.getresponse()
    dados = r.read()
    c.close()
    try:
        return r.status, json.loads(dados)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return r.status, dados


CONTROLE = {"empresa_no_relatorio": EMPRESA}


def executor_simulado(ordem_de_servico, pasta):
    sol = next(l.split("SOL:")[1].strip() for l in ordem_de_servico.splitlines() if "SOL:" in l)
    return {"relatorio": RELATORIO.format(sol=sol).replace("EMPRESA: EMPRESA-FIN-TMP", f"EMPRESA: {CONTROLE['empresa_no_relatorio']}"),
            "problemas": [], "ferramentas": {"Bash": 1}, "bloqueios": 0}


def esperar_livre(sol, limite=180):
    fim = time.time() + limite
    while time.time() < fim:
        c, d = pedido("GET", f"/api/solicitacoes/{sol}")
        if c == 200 and d["execucao"]["status"] != "EM_EXECUCAO" and not servidor.EM_EXECUCAO["sol"]:
            return d
        time.sleep(0.3)
    return None


def enviar(arquivos, competencia="2026-09"):
    c, d = pedido("POST", "/api/lotes", {"empresa": EMPRESA, "competencia": competencia, "fluxo": "FINANCEIRO_BANCOS",
                                         "instrucao": "Chegaram os extratos, a relação de pagamentos e os comprovantes. Inicie."})
    lote = d["lote"]
    for nome, conteudo in arquivos:
        pedido("PUT", f"/api/lotes/{lote}/arquivos", conteudo, {"X-Nome-Arquivo": quote(nome), "X-Sha256": hashlib.sha256(conteudo).hexdigest()})
    c, d = pedido("POST", f"/api/lotes/{lote}/iniciar", {"conferencia_humana": True})
    return c, d, esperar_livre(d["sol"]) if c == 202 else None


def registro():
    return _ai.registro_isolado()["solicitacoes"]


def bateria_api(m_ref):
    origem = BASE / "TESTE-LOTE"
    arquivos = [(p.name, p.read_bytes()) for p in sorted(origem.iterdir())]
    c, d, final = enviar(arquivos)
    sol = d["sol"]
    s = registro()[sol]
    c, e = pedido("GET", f"/api/solicitacoes/{sol}/financeiro")
    _, est = pedido("GET", "/api/estado")
    etapas = next(x["etapas"] for x in est["recentes"] if x["sol"] == sol)
    registrar("A-01 fluxo completo: Documentos → Coordenador → Financeiro → Coordenador → Bancos → Supervisor (SIMULAÇÃO)",
              s["fluxo"] == "FINANCEIRO_BANCOS" and s["estado"] == "AGUARDANDO_SUPERVISOR" and s["etapa"] == "BANCOS_CONCLUIDO"
              and len(s["financeiro"]) == len(s["bancos"]) == 1 and s["motivos"][0].startswith("CONFERENCIA_HUMANA_SIMULACAO")
              and e["disponivel"] and e["financeiro"]["resumo"]["movimentos"] == 13 and e["bancos"]["resumo"]["propostos"] == 6
              and etapas["financeiro"]["status"] == etapas["bancos"]["status"] == "CONCLUIDA" and not ORDEM.exists(),
              f"{sol}: {s['motivos'][0][:110]}")
    registrar("A-02a ressalvas de Documentos (divergências, titularidade de documentos, imagem sem OCR) não bloqueiam o lote: "
              "seguem ao Financeiro como ressalvas, documentos citados não validados",
              len(s.get("pendencias_documentos", [])) >= 6 and len(e["financeiro"]["ressalvas_documentos"]) == len(s["pendencias_documentos"])
              and not e["financeiro"]["bloqueio_lote"]
              and all(d.get("bloqueado") for d in e["financeiro"]["documentos"] if "14_comprovante_outra_empresa" in d["arquivo"])
              and not any(x["conta"].startswith("341") for x in e["financeiro"]["movimentos"]),
              f"{len(s.get('pendencias_documentos', []))} ressalvas repassadas")
    registrar("A-02 pendência de documento (imagem ilegível) não bloqueia a conferência dos demais; segue como pendência",
              any("15_recibo_digitalizado.png" in x for x in s.get("pendencias_documentos", [])) and any("15_recibo" in x for x in s["motivos"]))
    p = subprocess.run([PY, "-I", str(COORD), "abrir", "--pedido", f"Supervisor: processar a {REAL.name} competência 09/2026.", "--fluxo", "FINANCEIRO_BANCOS"],
                       cwd=RAIZ, capture_output=True, encoding="utf-8")
    r = json.loads(p.stdout)
    lotes_antes = sorted((TMP / "runtime" / "lotes").glob("L-*"))
    c_real, r_real = pedido("POST", "/api/lotes", {"empresa": REAL.name, "competencia": "2026-09", "fluxo": "FINANCEIRO_BANCOS", "instrucao": "teste"})
    registrar("A-03 fluxo Financeiro/Bancos recusado para empresa real: na criação do lote (nada recebido nem copiado) e no Coordenador",
              p.returncode == 3 and r["resultado"] == "FLUXO_NAO_AUTORIZADO" and not ORDEM.exists()
              and c_real == 403 and sorted((TMP / "runtime" / "lotes").glob("L-*")) == lotes_antes)
    fin1 = TMP / "runtime" / "execucoes" / sol / "financeiro-1" / "resultado.json"
    hash1 = hashlib.sha256(fin1.read_bytes()).hexdigest()
    f7 = next(x for x in e["financeiro"]["movimentos"] if x["identificadores"].get("FITID") == "F007")
    comp = next(a for a in e["financeiro"]["ambiguas"] if a["tipo"] == "COMPROVANTE")["origem"]
    c1, _ = pedido("POST", f"/api/solicitacoes/{sol}/financeiro/decisoes", {"movimento": f7["id"], "tipo": "VINCULAR",
                                                                             "dados": {"vinculos": ["DOC-000000000000"]}, "justificativa": "teste"})
    c2, r2 = pedido("POST", f"/api/solicitacoes/{sol}/financeiro/decisoes", {"movimento": f7["id"], "tipo": "VINCULAR",
                                                                              "dados": {"vinculos": [comp]}, "justificativa": "Conferido no extrato físico (fictício)."})
    esperar_livre(sol)
    c, e2 = pedido("GET", f"/api/solicitacoes/{sol}/financeiro")
    f7b = next(x for x in e2["financeiro"]["movimentos"] if x["id"] == f7["id"])
    f8b = next(x for x in e2["financeiro"]["movimentos"] if x["identificadores"].get("FITID") == "F008")
    registrar("A-04 decisão do Supervisor resolve a ambiguidade só deste movimento; nova tentativa, anterior preservada",
              c1 == 409 and c2 == 202 and f7b["comprovantes"] == [comp] and f7b["decisoes"] and f8b["situacao"] == "SEM_SUPORTE"
              and len(e2["tentativas"]["financeiro"]) == 2 and hashlib.sha256(fin1.read_bytes()).hexdigest() == hash1
              and registro()[sol]["estado"] == "AGUARDANDO_SUPERVISOR"
              and all({"sol": sol, "tentativa": 1} == {k: x[k] for k in ("sol", "tentativa")} for l in e2["bancos"]["lancamentos"] for x in l["revisao_de"][:1])
              and all(l["revisao_de"] for l in e2["bancos"]["lancamentos"]), "revisão rastreável da tentativa nº 1")
    f2 = next(x for x in e2["financeiro"]["movimentos"] if x["identificadores"].get("FITID") == "F002")
    c3, _ = pedido("POST", f"/api/solicitacoes/{sol}/financeiro/decisoes", {"movimento": f2["id"], "tipo": "CONTRAPARTIDA",
                                                                             "dados": {"conta": "9999", "natureza_tipo": "DESPESA"}, "justificativa": "teste conta"})
    c4, _ = pedido("POST", f"/api/solicitacoes/{sol}/financeiro/decisoes", {"movimento": f2["id"], "tipo": "CONTRAPARTIDA",
                                                                             "dados": {"conta": "4103", "natureza_tipo": "DESPESA"},
                                                                             "justificativa": "Despesa geral confirmada com o cliente (fictício)."})
    esperar_livre(sol)
    c, e3 = pedido("GET", f"/api/solicitacoes/{sol}/financeiro")
    l2 = next(l for l in e3["bancos"]["lancamentos"] if f2["id"] in l["movimentos"])
    registrar("A-05 contrapartida decidida para o caso: conta do plano, origem registrada, suporte continua pendente",
              c3 == 409 and c4 == 202 and codigo(l2["debito"]) == "4103" and "somente este movimento" in l2["origem"]
              and l2["status"] == "INCOMPLETO" and any("sem documento de suporte" in p for p in l2["pendencias"]))
    # compatibilidade conta × direção × natureza validada no servidor/Coordenador antes de registrar qualquer decisão
    f12 = next(x for x in e3["financeiro"]["movimentos"] if x["identificadores"].get("FITID") == "F012")
    n_dec = len(registro()[sol].get("decisoes_movimentos", {}).get(f2["id"], []))

    def contra(mov, conta, natureza):
        return pedido("POST", f"/api/solicitacoes/{sol}/financeiro/decisoes", {"movimento": mov["id"], "tipo": "CONTRAPARTIDA",
                                                                                "dados": {"conta": conta, "natureza_tipo": natureza}, "justificativa": "teste"})
    recusas = {"pagamento LIQUIDACAO_OBRIGACAO + 4103 (despesa)": contra(f2, "4103", "LIQUIDACAO_OBRIGACAO"),
               "pagamento com natureza RECEITA (direção)": contra(f2, "4103", "RECEITA"),
               "pagamento DESPESA + 5 (conta bancária)": contra(f2, "5", "DESPESA"),
               "recebimento RECEBIMENTO + 4103 (despesa)": contra(f12, "4103", "RECEBIMENTO"),
               "recebimento RECEITA + 4103 (despesa)": contra(f12, "4103", "RECEITA"),
               "regra LIQUIDACAO_OBRIGACAO + 4103": pedido("POST", f"/api/solicitacoes/{sol}/financeiro/regras",
                                                           {"condicoes": "direcao=DEBITO; historico_contem=PIX ENVIADO", "tipo": "LIQUIDACAO_OBRIGACAO",
                                                            "contrapartida": "4103", "exige_suporte": "SIM", "historico": "PIX", "movimento": f2["id"]})}
    plano = BASE / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md"
    plano_original = plano.read_text(encoding="utf-8")
    plano.write_text(plano_original.replace("| IMPOSTOS E TAXAS | DESPESA |", "| IMPOSTOS E TAXAS |  |"), encoding="utf-8")
    try:
        recusas["grupo não definido (4104 sem grupo)"] = contra(f2, "4104", "DESPESA")
    finally:
        plano.write_text(plano_original, encoding="utf-8")
    _, est_tela = pedido("GET", f"/api/solicitacoes/{sol}/financeiro")
    erro = {k: (r.get("erro", "") if isinstance(r, dict) else "") for k, (_, r) in recusas.items()}
    registrar("A-05b servidor recusa combinação conta × direção × natureza incompatível (e conta sem grupo), sem registrar decisão nem regra",
              all(c == 409 for c, _ in recusas.values())
              and "não se aplica a movimento de DEBITO" in erro["pagamento com natureza RECEITA (direção)"]
              and "grupo PASSIVO" in erro["pagamento LIQUIDACAO_OBRIGACAO + 4103 (despesa)"]
              and "conta bancária" in erro["pagamento DESPESA + 5 (conta bancária)"]
              and "grupo ATIVO" in erro["recebimento RECEBIMENTO + 4103 (despesa)"]
              and "grupo RECEITA" in erro["recebimento RECEITA + 4103 (despesa)"]
              and "grupo PASSIVO" in erro["regra LIQUIDACAO_OBRIGACAO + 4103"]
              and "sem grupo" in erro["grupo não definido (4104 sem grupo)"]
              and len(registro()[sol].get("decisoes_movimentos", {}).get(f2["id"], [])) == n_dec
              and not registro()[sol].get("decisoes_movimentos", {}).get(f12["id"])
              and "LIQUIDACAO_OBRIGACAO | 4103" not in (BASE / "REGRAS-BANCOS.md").read_text(encoding="utf-8")
              and est_tela["compatibilidade"]["LIQUIDACAO_OBRIGACAO"] == {"direcao": "DEBITO", "grupos": ["PASSIVO"]}
              and "5" in est_tela["contas_banco"] and all(c.get("grupo") for c in est_tela["plano_contas"]),
              " · ".join(f"{k}: {c}" for k, (c, _) in recusas.items()))
    regras_antes = (BASE / "REGRAS-BANCOS.md").read_text(encoding="utf-8")
    proxima_regra = f"RB-{max(int(x) for x in re.findall(r'\| RB-(\d{3}) \|', regras_antes)) + 1:03d}"
    f8 = next(x for x in e3["financeiro"]["movimentos"] if x["identificadores"].get("FITID") == "F008")
    proposta = {"condicoes": "direcao=DEBITO; historico_contem=PIX ENVIADO", "tipo": "DESPESA", "contrapartida": "4103", "exige_suporte": "SIM",
                "historico": "PIX {favorecido}", "movimento": f8["id"]}
    c5, r5 = pedido("POST", f"/api/solicitacoes/{sol}/financeiro/regras", dict(proposta, contrapartida="9999"))
    c6, r6 = pedido("POST", f"/api/solicitacoes/{sol}/financeiro/regras", proposta)
    texto = (BASE / "REGRAS-BANCOS.md").read_text(encoding="utf-8")
    registrar("A-06 correção do Supervisor vira PROPOSTA de regra (com origem, versão e frase de aprovação), não regra silenciosa",
              c5 == 409 and c6 == 201 and r6["regra"] == proxima_regra and r6["situacao"] == "PROPOSTA"
              and re.search(rf"\| {proxima_regra} \| 1 \| .*Proposta do Supervisor a partir da {sol}, movimento {f8['id']}.*\| PROPOSTA \| — \|", texto)
              and texto.startswith(regras_antes.split("## Regras")[0]))
    c7, _ = pedido("POST", f"/api/solicitacoes/{sol}/financeiro/regras/aprovar", {"regra": "RB-004", "frase": "aprovado"})
    c8, r8 = pedido("POST", f"/api/solicitacoes/{sol}/financeiro/regras/aprovar", {"regra": "RB-004", "frase": f"VALIDADO REGRA {EMPRESA} RB-004"})
    esperar_livre(sol)
    c, e4 = pedido("GET", f"/api/solicitacoes/{sol}/financeiro")
    f11 = next(x for x in e4["financeiro"]["movimentos"] if x["identificadores"].get("FITID") == "F011")
    l11 = next(l for l in e4["bancos"]["lancamentos"] if f11["id"] in l["movimentos"])
    l8 = next(l for l in e4["bancos"]["lancamentos"] if f8["id"] in l["movimentos"])
    registrar("A-07 regra só vale após a frase exata; aprovada é aplicada em nova tentativa; proposta não aprovada não é usada",
              c7 == 409 and c8 == 202 and l11["status"] == "PROPOSTO" and codigo(l11["debito"]) == "4102" and l11["regra"]["id"] == "RB-004"
              and l8["regra"] is None and any("Sem regra aprovada" in p for p in l8["pendencias"])
              and "| RB-004 |" in (BASE / "REGRAS-BANCOS.md").read_text(encoding="utf-8")
              and f"VALIDADO REGRA {EMPRESA} RB-004" in (BASE / "REGRAS-BANCOS.md").read_text(encoding="utf-8"))
    # falha do Financeiro: registrada, preservada, sem repetição automática; nova tentativa com número próprio
    falha = TMP / "financeiro_que_falha.py"
    falha.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    original = servidor.FERRAMENTA_FINANCEIRO
    servidor.FERRAMENTA_FINANCEIRO = falha
    try:
        pedido("POST", f"/api/solicitacoes/{sol}/financeiro/decisoes", {"movimento": f2["id"], "tipo": "CONTRAPARTIDA",
                                                                       "dados": {"conta": "4103", "natureza_tipo": "DESPESA"}, "justificativa": "teste de falha"})
        esperar_livre(sol)
    finally:
        servidor.FERRAMENTA_FINANCEIRO = original
    s_falha = registro()[sol]
    pastas = sorted(p.name for p in (TMP / "runtime" / "execucoes" / sol).glob("financeiro-*"))
    c9, _ = pedido("POST", f"/api/solicitacoes/{sol}/financeiro/decisoes", {"movimento": f2["id"], "tipo": "CONTRAPARTIDA",
                                                                             "dados": {"conta": "4103", "natureza_tipo": "DESPESA"}, "justificativa": "nova tentativa"})
    esperar_livre(sol)
    pastas2 = sorted(p.name for p in (TMP / "runtime" / "execucoes" / sol).glob("financeiro-*"))
    registrar("A-08 falha do Financeiro: registrada pelo Coordenador, tentativa preservada; nova tentativa com número próprio",
              s_falha["estado"] == "AGUARDANDO_SUPERVISOR" and s_falha["motivos"][0].startswith("FALHA_FINANCEIRO")
              and pastas == ["financeiro-1", "financeiro-2", "financeiro-3", "financeiro-4", "financeiro-5"]
              and not (TMP / "runtime" / "execucoes" / sol / "financeiro-5" / "resultado.json").exists()
              and c9 == 202 and pastas2[-1] == "financeiro-6" and (TMP / "runtime" / "execucoes" / sol / "financeiro-6" / "resultado.json").exists()
              and registro()[sol]["estado"] == "AGUARDANDO_SUPERVISOR", " ".join(pastas2))
    c, csv_ = pedido("GET", f"/api/solicitacoes/{sol}/financeiro/{e4['bancos']['n']}/csv")
    registrar("A-09 proposta de lançamentos para conferência (CSV SIMULAÇÃO); nada liberado nem importado",
              c == 200 and isinstance(csv_, bytes) and csv_.startswith(b"lancamento;status;data;debito;credito")
              and not (TMP / "LIBERADOS").exists())
    # reenvio do mesmo extrato em outra SOL: proposta anterior (SIMULAÇÃO) não bloqueia, vira revisão; escriturado bloqueia
    c, d2, final2 = enviar(arquivos)
    sol2 = d2["sol"]
    c, e5 = pedido("GET", f"/api/solicitacoes/{sol2}/financeiro")
    reg = registro()
    registrar("A-10 reenvio em nova SOL: propostas anteriores em SIMULAÇÃO não bloqueiam; nova proposta é REVISÃO rastreável",
              e5["bancos"]["resumo"]["lancamentos"] == 12 and e5["financeiro"]["resumo"]["ja_escriturados"] == 0
              and e5["bancos"]["resumo"]["revisoes_de_propostas_anteriores"] == 12
              and all(any(x["sol"] == sol for x in l["revisao_de"]) for l in e5["bancos"]["lancamentos"])
              and "movimentos_propostos_simulacao" in reg[sol]["bancos"][-1] and not reg[sol].get("escriturados"))
    # lançamento EFETIVAMENTE escriturado (registro gravado por etapa futura de aprovação; aqui simulado no registro temporário)
    f1 = next(x for x in e5["financeiro"]["movimentos"] if x["identificadores"].get("FITID") == "F001")
    caminho = Path(os.environ["AGENTES_PRIME_REGISTRO_SOL"])
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["solicitacoes"][sol]["escriturados"] = [{"movimento": f1["id"], "lancamento": "LAN-001", "em": "2026-10-31T17:00:00-03:00"}]
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    f2b = next(x for x in e5["financeiro"]["movimentos"] if x["identificadores"].get("FITID") == "F002")
    pedido("POST", f"/api/solicitacoes/{sol2}/financeiro/decisoes", {"movimento": f2b["id"], "tipo": "CONTRAPARTIDA",
                                                                    "dados": {"conta": "4103", "natureza_tipo": "DESPESA"}, "justificativa": "nova tentativa da SOL 2"})
    esperar_livre(sol2)
    c, e6 = pedido("GET", f"/api/solicitacoes/{sol2}/financeiro")
    registrar("A-13 só lançamento ESCRITURADO bloqueia nova proposta (as demais seguem como revisão); tentativas da SOL preservadas",
              not any(f1["id"] in l["movimentos"] for l in e6["bancos"]["lancamentos"]) and e6["financeiro"]["resumo"]["ja_escriturados"] == 1
              and any(n["movimento"] == f1["id"] and "ESCRITURADO" in n["motivo"] and sol in n["motivo"] for n in e6["bancos"]["nao_escriturados"])
              and e6["bancos"]["resumo"]["lancamentos"] == 11 and len(e6["tentativas"]["bancos"]) == 2)
    # competência errada (amostra 09/2026 aberta como 10/2026): bloqueio do LOTE, sem conferência e sem Bancos
    c, d3, _ = enviar(arquivos, competencia="2026-10")
    s3 = registro()[d3["sol"]]
    c, e7 = pedido("GET", f"/api/solicitacoes/{d3['sol']}/financeiro")
    registrar("A-14 competência incorreta bloqueia o LOTE inteiro (determinístico, sem depender do relatório): nada conferido, Bancos não acionado",
              s3["estado"] == "AGUARDANDO_SUPERVISOR" and s3["etapa"] == "FINANCEIRO_LOTE_BLOQUEADO" and not s3.get("bancos")
              and any(m.startswith("BLOQUEIO_LOTE: Competência da solicitação (2026-10)") for m in s3["motivos"])
              and e7["financeiro"]["movimentos"] == [] and e7["bancos"] is None and e7["tentativas"]["bancos"] == [], s3["motivos"][0][:150])
    # somente extrato e comprovante de outra empresa: titularidade do lote indeterminada → bloqueio do lote
    so_outra = [(n, b) for n, b in arquivos if n.startswith(("13_", "14_"))]
    c, d4, _ = enviar(so_outra)
    s4 = registro()[d4["sol"]]
    registrar("A-15 lote sem extrato utilizável da empresa (só documentos de outra empresa): bloqueio do LOTE, nada misturado",
              s4["etapa"] == "FINANCEIRO_LOTE_BLOQUEADO" and any("Nenhum extrato utilizável" in m for m in s4["motivos"]) and not s4.get("bancos"))
    # problema estrutural do relatório (empresa diferente): para em Documentos, Financeiro não é acionado
    CONTROLE["empresa_no_relatorio"] = "EMPRESA-TESTE"
    try:
        c, d5, _ = enviar(arquivos)
    finally:
        CONTROLE["empresa_no_relatorio"] = EMPRESA
    s5 = registro()[d5["sol"]]
    registrar("A-16 relatório com empresa diferente (risco de mistura): bloqueio do LOTE na etapa de Documentos, Financeiro não acionado",
              s5["estado"] == "AGUARDANDO_SUPERVISOR" and s5["etapa"] == "DOCUMENTOS_PENDENTE" and not s5.get("financeiro")
              and any("empresa diferente" in m for m in s5["motivos"]))
    registrar("A-11 Financeiro e Bancos não acionam o Claude nem outro agente (somente extrator e código local)",
              not re.search(r"claude\.exe|subagent_type|\"Agent\"|EXECUTAR_AGENTE", FIN.read_text(encoding="utf-8") + BAN.read_text(encoding="utf-8")))
    registrar("A-12 tela: tipo de solicitação, conferência, ambíguas, lançamentos e regras; decisão enviada pela tela; Financeiro e Bancos no escritório",
              *tela(sol, d3["sol"], sol2))


def tela(sol, sol_bloqueada, sol_ambigua):
    """Abre a página servida por este servidor de teste (Chrome sem interface), confere a tela de acompanhamento e captura."""
    sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
    from e2e_navegador import CDP, CHROME
    fotos = Path(os.environ.get("CAPTURAS_FINANCEIRO") or TMP / "capturas")
    fotos.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{PORTA}/"
    chrome = subprocess.Popen([str(CHROME), "--headless=new", "--remote-debugging-port=9338", f"--user-data-dir={tempfile.mkdtemp(prefix='chrome-fin-')}",
                               "--window-size=1500,1000", "--no-first-run", "--disable-extensions", url])
    resultados_tela = []

    def abrir_sol(cdp, alvo):
        cdp.js("document.querySelector('.op-painel').hidden = false; document.querySelector('.op-botao').click()")
        time.sleep(1.2)
        cdp.js(f"Array.from(document.querySelectorAll('.op-recente')).find(b => b.textContent.startsWith('{alvo}')).click()")
        for _ in range(40):
            time.sleep(0.5)
            if cdp.js("!!document.querySelector('.ac-resumo') && !!document.querySelector('.ac-areas')"):
                break
        time.sleep(0.5)

    sem_rolagem = "(() => { const p = document.querySelector('.op-painel'); const els = [p, ...p.querySelectorAll('.ac-decisao, .ac-secao, .ac-resumo, .ac-area, .op-form')]; " \
                  "return els.filter((e) => e.offsetParent !== null && e.scrollWidth > e.clientWidth + 1).map((e) => e.className); })()"
    try:
        for _ in range(50):
            try:
                pagina = next(a for a in json.load(urllib_req.urlopen("http://127.0.0.1:9338/json/list")) if a["type"] == "page" and a["url"].startswith(url))
                break
            except Exception:
                time.sleep(0.3)
        cdp = CDP(pagina["webSocketDebuggerUrl"])
        time.sleep(2)
        cdp.js("document.querySelector('.op-botao').click()")
        time.sleep(1.2)
        opcoes = cdp.js("Array.from(document.querySelectorAll('.op-campo select')[1].options).map(o => o.value).filter(Boolean).join(',')")
        cdp.js("document.querySelectorAll('.op-campo select')[1].value = 'FINANCEIRO_BANCOS'")
        cdp.foto(fotos / "tela-1-formulario.png")
        abrir_sol(cdp, sol)
        c, e = pedido("GET", f"/api/solicitacoes/{sol}/financeiro")
        incompletos = {l["movimentos"][0] for l in e["bancos"]["lancamentos"] if l["status"] != "PROPOSTO"}
        # resumo do percurso (rodada 03/11/2026): números reais de cada área e da Contabilidade
        esperado = (f"Financeiro conferiu {e['financeiro']['resumo']['movimentos']} movimentos. Propostas contábeis: Bancos: "
                    f"{e['bancos']['resumo']['propostos']} propostas e {e['bancos']['resumo']['incompletos']} incompletas.")
        dados = json.loads(cdp.js("""JSON.stringify((() => {
          const sec = Array.from(document.querySelectorAll('.ac-secao'));
          const de = (t) => sec.find((x) => (x.querySelector('.ac-titulo') || {}).textContent?.startsWith(t));
          const movs = (x) => x ? Array.from(x.querySelectorAll('.ac-decisao[data-movimento]')).map((a) => a.dataset.movimento) : [];
          const resumos = (x) => x ? Array.from(x.querySelectorAll('details > summary')).map((s) => s.textContent) : [];
          return { resumo: document.querySelector('.ac-resultado').textContent, proxima: document.querySelector('.ac-proxima').textContent,
                   agora: movs(de('Decisões que exigem')), doc: movs(de('Dependem de documento')),
                   acoesAgora: resumos(de('Decisões que exigem')), regras: resumos(de('Regras propostas')),
                   ordem: sec.map((x) => (x.querySelector('.ac-titulo') || x.querySelector('summary') || {}).textContent || ''),
                   areas: Array.from(document.querySelectorAll('.ac-area h4')).map((h) => h.textContent) };
        })())"""))
        resultados_tela.append(("T-01 resumo no topo com números reais, etapa, próxima ação e 'Nada foi escriturado'",
                                esperado in dados["resumo"] and "Nada foi aprovado nem escriturado" in dados["resumo"] and dados["proxima"].startswith("Próxima ação:"),
                                dados["resumo"][:160]))
        todos = dados["agora"] + dados["doc"]
        resultados_tela.append(("T-02 um item por movimento (sem repetição): fila = lançamentos incompletos; decisões possíveis antes das que dependem de documento",
                                len(todos) == len(set(todos)) and set(todos) == incompletos and dados["ordem"][0].startswith("Decisões que exigem")
                                and len(dados["agora"]) > 0 and len(dados["doc"]) > 0,
                                f"agora {len(dados['agora'])} · documento {len(dados['doc'])} · incompletos {len(incompletos)}"))
        abrir_sol(cdp, sol_ambigua)
        acoes_amb = cdp.js("Array.from(document.querySelectorAll('.ac-decisao.agora details > summary')).map((s) => s.textContent).join(' | ')")
        abrir_sol(cdp, sol)
        acoes = " | ".join(dados["acoesAgora"]) + " | " + acoes_amb
        resultados_tela.append(("T-03 ações distintas: confirmar vínculo, contrapartida deste caso, regra para uso futuro e aprovação de regra",
                                "Confirmar vínculo — somente este caso" in acoes and "Informar contrapartida deste caso — vale só para este movimento" in acoes
                                and "Propor regra para uso futuro — não altera este movimento agora" in acoes
                                and any(x.startswith("Aprovar regra RB-") for x in dados["regras"]), acoes[:160]))
        resultados_tela.append(("T-04 trabalho por área: Documentos, Financeiro, Contabilidade/Bancos", dados["areas"] == ["① Documentos", "② Financeiro", "③ Contabilidade/Bancos"]))
        texto = cdp.js("document.querySelector('.op-sol').textContent").replace("\u00a0", " ")
        resultados_tela.append(("T-05 valores e datas em formato brasileiro; contas com nome; sem tabela larga de lançamentos",
                                "R$ 1.500,00" in texto and "05/09/2026" in texto and "2101 · FORNECEDORES" in texto
                                and not cdp.js("document.querySelector('.op-sol table')")))
        cdp.js("window.scrollTo(0,0); document.querySelector('.op-painel').scrollTop = 0")
        cdp.foto(fotos / "tela-2-resumo-e-decisoes.png")
        cdp.js("(() => { const d = document.querySelector('.ac-decisao.agora details'); if (d) d.open = true; })()")
        cdp.js("document.querySelector('.ac-decisao.agora').scrollIntoView()")
        time.sleep(0.3)
        cdp.foto(fotos / "tela-3-decisao-aberta.png")
        cdp.js("document.querySelector('.ac-areas').scrollIntoView()")
        time.sleep(0.3)
        cdp.foto(fotos / "tela-4-trabalho-por-area.png")
        # decisão enviada pela tela (contrapartida deste caso, com justificativa)
        antes = sum(len(v) for v in registro()[sol].get("decisoes_movimentos", {}).values())
        enviado = cdp.js("""(() => { const d = Array.from(document.querySelectorAll('.ac-decisao.agora details')).find(x => x.querySelector('summary').textContent.startsWith('Informar contrapartida'));
            if (!d) return false; d.open = true; d.querySelector('textarea').value = 'Decisão de teste enviada pela tela (fictício).';
            const sel = d.querySelectorAll('select'); sel[0].value = 'DESPESA'; sel[0].dispatchEvent(new Event('change')); sel[1].value = '4103';
            Array.from(d.querySelectorAll('button')).find(b => b.textContent.startsWith('Informar contrapartida')).click(); return true; })()""")
        depois = antes
        for _ in range(240):
            time.sleep(0.5)
            depois = sum(len(v) for v in registro()[sol].get("decisoes_movimentos", {}).values())
            if depois > antes and registro()[sol]["estado"] == "AGUARDANDO_SUPERVISOR" and not servidor.EM_EXECUCAO["sol"]:
                break
        resultados_tela.append(("T-06 decisão do caso enviada pela tela, registrada pelo Coordenador (nada aprovado nem escriturado)",
                                enviado and depois == antes + 1 and not (TMP / "LIBERADOS").exists()))
        # janela menor: sem rolagem horizontal no formulário nem no acompanhamento
        cdp.chamar("Emulation.setDeviceMetricsOverride", width=1000, height=720, deviceScaleFactor=1, mobile=False)
        time.sleep(0.8)
        abrir_sol(cdp, sol)
        rol_acomp = cdp.js(sem_rolagem)
        cdp.foto(fotos / "tela-5-janela-menor.png")
        cdp.js("document.querySelector('.op-botao').click()")
        time.sleep(1)
        rol_form = cdp.js(sem_rolagem)
        cdp.chamar("Emulation.clearDeviceMetricsOverride")
        resultados_tela.append(("T-07 janela menor (1000×720): sem rolagem horizontal no acompanhamento, nas decisões e no formulário",
                                rol_acomp == [] and rol_form == [], f"{rol_acomp} {rol_form}"))
        # lote bloqueado: resumo explica o motivo e a próxima ação; pasta parada no Financeiro
        abrir_sol(cdp, sol_bloqueada)
        bloq = cdp.js("document.querySelector('.ac-resumo').textContent")
        cdp.foto(fotos / "tela-6-lote-bloqueado.png")
        resultados_tela.append(("T-08 lote bloqueado: resumo explica o motivo (competência) e a próxima ação; nenhuma decisão oferecida",
                                "Lote bloqueado" in bloq and "Competência da solicitação (2026-10)" in bloq and "abrir nova solicitação" in bloq.lower()
                                and not cdp.js("document.querySelector('.ac-decisao')"), bloq[:140]))
        # decisão parcial: cartões de R$ 800,00 e R$ 3.000,00 antes e depois (SOL com os casos ainda abertos)
        cartao_js = """((valor) => { const a = Array.from(document.querySelectorAll('.ac-decisao[data-movimento]'))
            .find((x) => x.querySelector('.ac-valor').textContent.replace(/\\u00a0/g, ' ') === valor);
          if (!a) return null; const sec = a.closest('.ac-secao').querySelector('.ac-titulo').textContent;
          return { mov: a.dataset.movimento, secao: sec, chip: a.querySelector('.ac-chip').textContent,
                   restante: (a.querySelector('.ac-restante') || {}).textContent || '', pos: (a.querySelector('.ac-pos-decisao') || {}).textContent || '',
                   cadastro: (a.querySelector('.ac-cadastro') || {}).textContent || '',
                   form: !!Array.from(a.querySelectorAll('summary')).find((x) => x.textContent.startsWith('Informar contrapartida')),
                   naturezas: Array.from((Array.from(a.querySelectorAll('details')).find((x) => x.querySelector('summary').textContent.startsWith('Informar contrapartida')) || document.createElement('div'))
                     .querySelectorAll('select')).slice(0, 1).flatMap((x) => Array.from(x.options).map((o) => o.value)).filter(Boolean),
                   texto: a.textContent }; })"""

        def foto_cartao(valor, destino):
            cdp.js(f"(() => {{ const a = Array.from(document.querySelectorAll('.ac-decisao[data-movimento]')).find((x) => "
                   f"x.querySelector('.ac-valor').textContent.replace(/\\u00a0/g, ' ') === '{valor}'); a.scrollIntoView({{block: 'start'}}); }})()")
            time.sleep(0.4)
            r = json.loads(cdp.js(f"JSON.stringify((() => {{ const a = Array.from(document.querySelectorAll('.ac-decisao[data-movimento]')).find((x) => "
                                  f"x.querySelector('.ac-valor').textContent.replace(/\\u00a0/g, ' ') === '{valor}'); const r = a.getBoundingClientRect(); "
                                  f"return {{x: r.left, y: r.top, w: r.width, h: Math.min(r.height, 900)}}; }})())"))
            dados_png = cdp.chamar("Page.captureScreenshot", format="png", clip={"x": r["x"] - 4, "y": max(0, r["y"] - 4), "width": r["w"] + 8,
                                                                                "height": r["h"] + 8, "scale": 1})["data"]
            Path(destino).write_bytes(base64.b64decode(dados_png))

        def decidir_pela_tela(valor):
            ok = cdp.js(f"""(() => {{ const a = Array.from(document.querySelectorAll('.ac-decisao[data-movimento]')).find((x) =>
                x.querySelector('.ac-valor').textContent.replace(/\\u00a0/g, ' ') === '{valor}');
              const d = Array.from(a.querySelectorAll('details')).find((x) => x.querySelector('summary').textContent.startsWith('Informar contrapartida'));
              if (!d) return false; d.open = true; const sel = d.querySelectorAll('select'); sel[0].value = 'DESPESA'; sel[0].dispatchEvent(new Event('change')); sel[1].value = '4103';
              d.querySelector('textarea').value = 'Contrapartida deste caso (teste fictício).';
              Array.from(d.querySelectorAll('button')).find((b) => b.textContent.startsWith('Informar contrapartida')).click(); return true; }})()""")
            time.sleep(1)
            esperar_livre(sol_ambigua)
            time.sleep(1)
            abrir_sol(cdp, sol_ambigua)
            return ok

        abrir_sol(cdp, sol_ambigua)
        antes = {v: cdp.js(f"{cartao_js}('{v}')") for v in ("R$ 800,00", "R$ 3.000,00")}
        foto_cartao("R$ 800,00", fotos / "cartao-800-antes.png")
        foto_cartao("R$ 3.000,00", fotos / "cartao-3000-antes.png")
        # contas que a tela oferece por natureza (antes de decidir): 4103 só como DESPESA; nenhuma conta bancária
        oferta = json.loads(cdp.js("""JSON.stringify((() => { const a = Array.from(document.querySelectorAll('.ac-decisao[data-movimento]')).find((x) =>
            x.querySelector('.ac-valor').textContent.replace(/\\u00a0/g, ' ') === 'R$ 800,00');
          const d = Array.from(a.querySelectorAll('details')).find((x) => x.querySelector('summary').textContent.startsWith('Informar contrapartida'));
          const sel = d.querySelectorAll('select'); const r = { inicial: { desabilitada: sel[1].disabled, contas: Array.from(sel[1].options).map((o) => o.value).filter(Boolean) } };
          Array.from(sel[0].options).map((o) => o.value).filter(Boolean).forEach((n) => { sel[0].value = n; sel[0].dispatchEvent(new Event('change'));
            r[n] = Array.from(sel[1].options).map((o) => o.value).filter(Boolean); });
          sel[0].value = ''; sel[0].dispatchEvent(new Event('change')); return r; })())"""))
        enviado = decidir_pela_tela("R$ 800,00")
        for _ in range(40):            # a tela é redesenhada após a decisão: espera o cartão refletir o novo estado (sem tempo fixo)
            if cdp.js(f"{cartao_js}('R$ 800,00')") != antes["R$ 800,00"]:
                break
            time.sleep(0.5)
        time.sleep(0.5)
        depois = {v: cdp.js(f"{cartao_js}('{v}')") for v in ("R$ 800,00", "R$ 3.000,00")}
        foto_cartao("R$ 800,00", fotos / "cartao-800-depois.png")
        foto_cartao("R$ 3.000,00", fotos / "cartao-3000-depois.png")
        a800, a3000, d800, d3000 = antes["R$ 800,00"], antes["R$ 3.000,00"], depois["R$ 800,00"], depois["R$ 3.000,00"]
        resultados_tela.append(("T-09 R$ 800: decisão parcial com natureza primeiro e só contas compatíveis (4103 apenas como DESPESA, nunca LIQUIDAÇÃO; "
                                "nenhuma conta bancária). R$ 3.000: sem conta compatível no plano → pendente 'Depende de definição no cadastro', sem formulário",
                                a800["chip"] == "Decisão parcial possível agora" and "documento da natureza do pagamento" in a800["restante"]
                                and "divergência" in a800["restante"] and a800["form"] and a800["naturezas"] == ["LIQUIDACAO_OBRIGACAO", "DESPESA"]
                                and oferta["inicial"] == {"desabilitada": True, "contas": []}
                                and oferta["DESPESA"] == ["4102", "4103", "4104"] and oferta["LIQUIDACAO_OBRIGACAO"] == ["2101", "2102"]
                                and a3000["chip"] == "Depende de definição no cadastro" and not a3000["form"]
                                and "O Supervisor precisa definir" in a3000["cadastro"] and "nenhuma classificação foi presumida" in a3000["cadastro"]
                                and "grupo receita" in a3000["cadastro"] and "grupo ativo" in a3000["cadastro"]
                                and "origem do recebimento" in a3000["texto"] and "conta compatível no plano de contas" in a3000["texto"]
                                and "contrapartida informada para este caso" not in a3000["texto"] and "4103" not in a3000["texto"],
                                f"oferta {oferta} | {a3000['cadastro'][:120]}"))
        _, e2 = pedido("GET", f"/api/solicitacoes/{sol_ambigua}/financeiro")
        l800 = next(l for l in e2["bancos"]["lancamentos"] if l["movimentos"][0] == a800["mov"])
        l3000 = next(l for l in e2["bancos"]["lancamentos"] if l["movimentos"][0] == a3000["mov"])
        resultados_tela.append(("T-10 após a decisão: cartão mostra novo estado (Incompleto) e pendências restantes; documento não é dado como resolvido",
                                enviado and d800["secao"].startswith("Dependem de documento") and d3000["secao"].startswith("Dependem de documento")
                                and "Estado atual do movimento: Incompleto" in d800["pos"] and "documento da natureza do pagamento" in d800["pos"]
                                and "divergência" in d800["pos"] and "4103 · DESPESAS GERAIS" in d800["pos"]
                                and "Despesa reconhecida e paga no ato" in d800["pos"] and "obrigação já registrada" not in d800["pos"]
                                and d3000["chip"] == "Depende de definição no cadastro" and not d3000["pos"] and not d3000["form"]
                                and l800["status"] == l3000["status"] == "INCOMPLETO" and codigo(l800["debito"]) == "4103"
                                and l800["tipo"] == "DESPESA" and l3000["credito"] is None
                                and "SUPORTE" in l800["faltas_codigos"] and "SUPORTE" in l3000["faltas_codigos"]
                                and not any(codigo(l.get("debito")) == "4103" and l.get("tipo") == "LIQUIDACAO_OBRIGACAO" for l in e2["bancos"]["lancamentos"])
                                and not any(codigo(l.get("credito")) == "4103" for l in e2["bancos"]["lancamentos"]),
                                f"{d800['pos'][:110]}"))
        # escritório com a SOL concluída: personagens na copa, pasta no Coordenador
        abrir_sol(cdp, sol)
        cdp.js("document.querySelector('.op-painel').hidden = true")
        for _ in range(40):
            time.sleep(0.5)
            estados = cdp.js("JSON.stringify(['financeiro','bancos'].map(id => EV.app.estadoDe(id).status))")
            if estados == '["CONCLUIDO","CONCLUIDO"]' and not cdp.js("Object.values(EV.app.cena._posicoes()).some(p => p.andando)"):
                break
        cdp.foto(fotos / "tela-7-escritorio.png")
    finally:
        chrome.terminate()
    falhas = [r for r in resultados_tela if not r[1]]
    for r in resultados_tela:
        registrar(*r)
    return (opcoes == "DOCUMENTOS,FINANCEIRO_BANCOS" and not falhas and estados == '["CONCLUIDO","CONCLUIDO"]',
            f"opções {opcoes} · escritório {estados} · capturas em {fotos}")


def main():
    global SRV, PORTA
    sys.stdout.reconfigure(encoding="utf-8")
    if ORDEM.exists() or BASE.exists() or ISOLAMENTO.exists() or REAL.exists() or not DEMO.is_dir():
        print("ABORTADO: pasta temporária já existe ou fixture fictícia ausente; nada foi feito.")
        return 1
    servidor.EXECUTAR_AGENTE = executor_simulado
    SRV = servidor.iniciar(0)
    PORTA = SRV.server_port
    threading.Thread(target=SRV.serve_forever, daemon=True).start()
    demo_antes = {p: p.read_bytes() for p in DEMO.rglob("*") if p.is_file()}
    try:
        preparar_empresa()
        m = bateria_motores()
        bateria_api(m)
    finally:
        SRV.shutdown()
        ORDEM.unlink(missing_ok=True)
        for pasta in (BASE, ISOLAMENTO, REAL):
            remover(pasta)
        shutil.rmtree(TMP, ignore_errors=True)
    registrar("Z-01 fixture de demonstração intacta; empresas temporárias removidas",
              {p: p.read_bytes() for p in DEMO.rglob("*") if p.is_file()} == demo_antes
              and not BASE.exists() and not ISOLAMENTO.exists() and not REAL.exists())
    largura = max(len(c) for c, _, _ in resultados)
    for c, ok, det in resultados:
        print(f"{'PASS' if ok else 'FAIL'}  {c.ljust(largura)}  {det}")
    falhas = [c for c, ok, _ in resultados if not ok]
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - len(falhas)} PASS · {len(falhas)} FAIL")
    print(f"ordem ativa residual: {'SIM' if ORDEM.exists() else 'não'} · empresa temporária residual: {'SIM' if BASE.exists() else 'não'}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
