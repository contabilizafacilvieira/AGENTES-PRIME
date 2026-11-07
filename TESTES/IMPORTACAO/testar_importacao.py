"""Bateria da área de Importação ESPECÍFICA DA VGROW (motor, Coordenador e API). SOMENTE FIXTURES FICTÍCIAS.

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/IMPORTACAO/testar_importacao.py

Cria temporariamente CLIENTES/VGROW/T-IMP-TMP/ (comparativos, numerários e "Documentos.pdf" fictícios, gerados aqui) e
remove ao final, junto com os lotes que o teste da API criar em CLIENTES/VGROW/RECEBIDOS. Registro de SOL e runtime
temporários. Não executa o Claude (executor simulado com relatório FICTÍCIO identificado).
"""

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
import urllib.request
from decimal import Decimal as D
from pathlib import Path
from urllib.parse import quote

RAIZ = Path(__file__).resolve().parents[2]
# LEGADO (fora do gate de release v1.0.0-interno): a Importação VGROW está DESATIVADA desde 05/11/2026 (rotas 410; Coordenador
# recusa os comandos). Esta bateria cobria o módulo ativo e dependia do cadastro real da empresa em CLIENTES/; não é executada
# pelo gate (TESTES/GATE-RELEASE.md). Código, regras e histórico do módulo continuam preservados.
raise SystemExit("LEGADO: Importação VGROW desativada (05/11/2026); bateria fora do gate de release. Nada foi feito.")


TMP = Path(tempfile.mkdtemp(prefix="imp-prime-"))
os.environ["AGENTES_PRIME_RUNTIME"] = str(TMP / "runtime")
os.environ["AGENTES_PRIME_REGISTRO_SOL"] = str(TMP / "solicitacoes.json")
sys.path.insert(0, str(RAIZ / "TESTES" / "T004"))
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import gerar_fixtures as gf  # noqa: E402
sys.path.insert(0, str(RAIZ / "TESTES" / "IMPORTACAO"))
import fixtures_reconhecimento as fx  # noqa: E402
import servidor  # noqa: E402
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado as _ai  # noqa: E402

PY = sys.executable
MOTOR = RAIZ / "AGENTES" / "IMPORTACAO" / "ferramentas" / "importacao_vgrow.py"
COORD = RAIZ / "COORDENADOR-GERAL" / "ferramentas" / "coordenador.py"
ORDEM = RAIZ / "AGENTES" / "DOCUMENTOS" / "controle" / "ordem-ativa.json"
VGROW = RAIZ / "CLIENTES" / "VGROW"
FIX = VGROW / "T-IMP-TMP"
FIX_REC = VGROW / "T-REC-TMP"
RECONHECEDOR = RAIZ / "AGENTES" / "IMPORTACAO" / "ferramentas" / "reconhecer_documentos_vgrow.py"
resultados = []
lotes_criados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), detalhe))


def remover(pasta):
    def forcar(f, c, _e):
        os.chmod(c, stat.S_IWRITE | stat.S_IREAD)
        f(c)
    if pasta.exists():
        for p in pasta.rglob("*"):
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
        shutil.rmtree(pasta, onexc=forcar)


# ---------------------------------------------------------------- fixtures fictícias
def comparativo(saldo="950", pago="5000", leiaute="out"):
    def preparar(wb):
        ws = wb.active
        ws.title = "Plan1"
        ws.append(["COMPARATIVO - FICTICIO"])
        ws.append(["DESPESA", "DESCRIÇÃO", "NUMERÁRIO", "REAL", "DIFERENÇA"])
        linhas = [("IMPOSTOS DE IMPORTAÇÃO", 1000, 1000), ("IMPOSTO SOBRE PRODUTOS", 500, 500), ("PIS ", 200, 200),
                  ("COFINS ", 900, 900), ("Marinha Mercante (AFRMM)", 50, 50), ("Capatazia", 100, 100), ("Armazenagem", 850, 0)]
        linhas += ([("Honorários", 800, 900), ("Serviços Capital Trade", 200, 0)] if leiaute == "out"
                   else [("Serviço de Desembaraço Aduaneiro", 1000, 900)])
        linhas += [("ICMS ", 300, 300), ("Diferença de IPI", None, None), ("Diferença I.P.I ", 100, 100)]
        for rot, n, r in linhas:
            ws.append([rot, "fictício", n, r, None if n is None else (r or 0) - n])
        ws.append([None, "TOTAL", 5000, 4050, 950])
        ws.append(["VALOR PASSADO EM NUMERÁRIO", 5000])
        ws.append(["VALOR PAGO EM NUMERÁRIO", float(pago)])
        ws.append(["DIFERENÇA", 0])
        ws.append(["SALDO RELATÓRIO DE PROCESSO", float(saldo)])
    return gf.montar_xlsx(preparar)


def prestacao(processo, entradas=("5000",), total1="4050", nfs=(("1001", "1000", "400"), ("1002", "500", "200"))):
    def preparar(wb):
        ws = wb.active
        ws.title = "RP_FICTICIO"
        ws.append(["PRESTACAO DE CONTAS FICTICIA"])
        ws.append(["Registro:", processo, "Cliente Ref:", "GG900000001", "N° DI/DUIMP:", "26BR0000000000-0"])
        ws.append(["TOTAL(1):", float(total1)])
        ws.append(["SOLICITAÇÃO DE NUMERÁRIO", 5000.0])
        ws.append(["SALDO A FAVOR DO VGROW FICTICIO", 950.0])
        ws.append(["Evento", "Valor", "Data", "Observação"])
        ws.append(["SOLICITAÇÃO DE NUMERÁRIO", 5000.0, "2026-09-10", "FICTICIO"])
        for e in entradas:
            ws.append(["ENTRADA DE NUMERÁRIO", float(e), "2026-09-11", "BANCO FICTICIO"])
        ws.append(["LISTAGEM DE NOTAS FISCAIS"])
        ws.append(["NF. Número", "Valor", "ICMS", "Desconto ICMS"])
        for nf, valor, icms in nfs:
            ws.append([int(nf), float(valor), float(icms), 1.0])
        ws.append(["RODAPE FICTICIO"])
    return gf.montar_xlsx(preparar)


def numerario(processo, total="5.000,00"):
    return gf.montar_pdf([{"linhas": [f"NUMERARIO FICTICIO {processo}", "DOCUMENTO FICTICIO PARA TESTE",
                                      f"Total a pagar para CAPITAL TRADE: R$ {total}"]}])


def documentos_pdf():
    return gf.montar_pdf([{"imagem": gf.desenhar("TOTAL 4567")}])     # só imagem, sem camada de texto (como a DUIMP real)


PROCESSOS = {  # número OCCT fictício → (comparativo kwargs, numerário total, tem documentos)
    "90001": ({}, "5.000,00", True),               # completo
    "90002": (None, "5.000,00", False),            # só numerário
    "90003": ({}, "5.000,00", True),               # chegada em mês anterior
    "90004": ({}, "5.005,00", True),               # numerário PDF ≠ depositado (comparativo 5000)
    "90005": ({"saldo": "900"}, "5.000,00", True),  # divergência numerário − saldo − total REAL
    "90006": ({}, "5.000,00", True),               # ICMS informado incoerente com o cobrado (alerta)
    "90007": ({"leiaute": "set"}, "5.000,00", True),  # leiaute de setembro (serviço numa linha)
    "90008": ({}, "5.000,00", True),               # campos do Supervisor ausentes
    "90011": ({}, "5.000,00", True),               # Prestação: ENTRADA = PDF; NFs conferem
    "90012": ({}, "5.000,00", True),               # Prestação: ENTRADA 4990 ≠ PDF → depositado
    "90013": ({}, "5.000,00", True),               # Prestação: duas ENTRADAS → ambíguo
    "90014": ({}, "5.000,00", True),               # Prestação de outro processo
    "90015": ({}, "5.000,00", True),               # Prestação: lista de NFs com ICMS diferente
    "90016": ({}, "5.000,00", True),               # Prestação: TOTAL(1) ≠ total REAL do comparativo
    "90017": ({}, "5.000,00", True),               # ICMS destacado 600,01 → desconto 300,01 (arredondamento do gerador)
}
PRESTACOES = {"90011": {}, "90012": {"entradas": ("4990",)}, "90013": {"entradas": ("2500", "2500")},
              "90014": {"processo": "OCCT99999/26"}, "90015": {"nfs": (("1001", "1000", "400"), ("1002", "500", "250"))},
              "90016": {"total1": "4051"}}
BASE = {"fob": "20000.00", "frete": "3000.00", "chegada": "2026-09-15", "fatura": "TEST/INV/000001", "nfs": ["1002", "1001"], "icms_nf": "600.00"}
INFORMADOS = {f"OCCT{n}/26": dict(BASE) for n in PROCESSOS if n != "90008"}
INFORMADOS["OCCT90003/26"]["chegada"] = "2026-08-20"
INFORMADOS["OCCT90006/26"]["icms_nf"] = "700.00"
INFORMADOS["OCCT90017/26"]["icms_nf"] = "600.01"


def preparar():
    FIX.mkdir()
    for n, (comp, total, docs) in PROCESSOS.items():
        if comp is not None:
            (FIX / f"OCCT{n}-26 - COMPARATIVO.xlsx").write_bytes(comparativo(**comp))
        (FIX / f"NUMERARIO_OCCT{n}_26_FICTICIO.pdf").write_bytes(numerario(f"OCCT{n}/26", total))
        if docs:
            (FIX / f"OCCT{n}-26 - DOCUMENTOS.pdf").write_bytes(documentos_pdf())
    for n, k in PRESTACOES.items():
        (FIX / f"OCCT{n}-26.xlsx").write_bytes(prestacao(k.pop("processo", f"OCCT{n}/26"), **k))
    (FIX / "recibo_sem_processo.txt").write_text("RECIBO FICTICIO SEM PROCESSO\n", encoding="utf-8")


def motor(saida, informados=INFORMADOS, empresa="VGROW", pasta="T-IMP-TMP", sol="SOL-2026-000001", competencia="2026-09", ja_lancados=None, aceites=None):
    arq = TMP / f"informados-{time.time_ns()}.json"
    arq.write_text(json.dumps(informados), encoding="utf-8")
    p = subprocess.run([PY, "-I", str(MOTOR), "--sol", sol, "--competencia", competencia, "--pasta", pasta, "--informados", str(arq),
                        "--saida", str(saida), "--empresa", empresa] + (["--ja-lancados", str(ja_lancados)] if ja_lancados else []) + (["--aceites", str(aceites)] if aceites else []), cwd=RAIZ, capture_output=True, encoding="utf-8")
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"stderr": p.stderr[-300:]})


# ---------------------------------------------------------------- motor
def bateria_motor():
    saida = TMP / "saida-motor"
    c, r = motor(saida, sol="SOL-2026-999999")
    fech = {p["processo"]: p for p in r.get("processos_fechados", [])}
    pend = {p["processo"]: p for p in r.get("processos_pendentes", [])}
    p1 = fech.get("OCCT90001/26")
    esperado = [(10084, "D", "950.00"), (10084, "C", "5000.00"), (29, "D", "600.00"), (30, "D", "600.00"), (36, "D", "900.00"),
                (37, "D", "200.00"), (55, "D", "20000.00"), (55, "D", "3000.00"), (55, "D", "1111.50"), (10010, "C", "20000.00"),
                (10010, "C", "3000.00"), (178, "C", "15.00"), (182, "C", "46.50"), (434, "C", "300.00"), (470, "D", "1000.00")]
    obtido = [(l["conta"], l["dc"], l["valor"]) for l in p1["lancamentos"]] if p1 else []
    registrar("M-01 processo completo fechado com as 15 linhas da regra", c == 0 and obtido == esperado and p1["confere"]
              and p1["debito"] == p1["credito"] == "28361.50" and p1["historico"] == "TEST/INV/000001 - NF'S 1001/1002",
              "custo de fechamento 1111.50; D = C = 28361.50")
    registrar("M-02 origem dos valores registrada", p1 and p1["valores"]["fob"]["origem"] == "INFORMADO_PELO_SUPERVISOR"
              and p1["valores"]["saldo"]["origem"].startswith("EXTRAIDO: OCCT90001-26 - COMPARATIVO") and p1["valores"]["num"]["origem"].startswith("EXTRAIDO: numerário PDF (NUMERARIO_OCCT90001"))
    p2 = pend.get("OCCT90002/26", {})
    registrar("M-03 documentos obrigatórios ausentes → pendente", sorted(p2.get("documentos_ausentes", [])) == ["comparativo", "documentos"])
    registrar("M-04 chegada em mês anterior → pendente ao Supervisor", "OCCT90003/26" in pend and "OCCT90003/26" not in fech
              and any(m.startswith("Chegada 20/08/2026") for m in pend["OCCT90003/26"]["motivos"]))
    agu = {p["processo"]: p for p in r.get("processos_aguardando_aceite", [])}
    p4 = agu.get("OCCT90004/26")
    registrar("M-05 VALOR PAGO do comparativo ≠ numerário → só alerta; PDF continua o padrão", p4 and p4["valores"]["num"]["valor"] == "5005.00"
              and p4["numerario"]["usado"] == "5005.00" and any("OCCT90004/26" in a and "VALOR PAGO" in a and "Diferença 5.00" in a for a in r["alertas"]))
    p5 = agu.get("OCCT90005/26")
    registrar("M-06 checagem ≠ 0 → aguardando aceite com diferença exata e fontes (sem tolerância, sem ajuste)", p5 and "OCCT90005/26" not in pend
              and p5["aceite_necessario"]["diferenca"] == "50.00" and p5["aceite_necessario"]["fontes"]["saldo"].startswith("EXTRAIDO: OCCT90005-26")
              and p5["valores"]["saldo"]["valor"] == "900.00" and "OCCT90005/26" not in fech)
    p6 = fech.get("OCCT90006/26")
    registrar("M-07 ICMS cobrado e destacado são campos distintos (sem alerta de igualdade)", p6 and not any("OCCT90006/26" in a and "ICMS" in a for a in r["alertas"])
              and p6["calculos"]["icms_cobrado_comparativo"] == "300.00" and p6["calculos"]["icms_destacado_nfs"] == "700.00"
              and p6["calculos"]["desconto_icms_50_sobre_destacado"] == "350.00" and next(l for l in p6["lancamentos"] if l["conta"] == 30)["valor"] == "700.00")
    p7 = fech.get("OCCT90007/26")
    registrar("M-08 leiaute de setembro (serviço numa linha)", p7 and p7["valores"]["serv"]["valor"] == "1000.00")
    registrar("M-09 campos do Supervisor ausentes → pendente", any("não informados pelo Supervisor" in m for m in pend.get("OCCT90008/26", {}).get("motivos", [])))
    registrar("M-10 documento sem número de processo é listado", r.get("documentos_sem_processo") == ["recibo_sem_processo.txt"])
    txt = saida / r["arquivos"]["txt"]
    bruto = txt.read_bytes()
    linhas = bruto.decode("cp1252").split("\r\n")
    registrar("M-11 TXT no leiaute do Domínio (cp1252, CRLF, 10 campos, lote inicia com 1)", r["arquivos"]["txt"] == "lanctos_Vgrow_2026-09_SIMULACAO_SOL-2026-999999.txt"
              and linhas[0] == "15/09/2026;10084;;950;;TEST/INV/000001 - NF'S 1001/1002 - SALDO A RECEBER;1;;;" and all(l.count(";") == 9 for l in linhas if l)
              and b"\r\n" in bruto and sum(1 for l in linhas if l.split(";")[6:7] == ["1"]) == len(fech), f"{len([l for l in linhas if l])} linhas")
    import openpyxl
    wb = openpyxl.load_workbook(saida / r["arquivos"]["conferencia"])
    wl = wb["Lançamentos"]
    custo = next(r for r in range(4, wl.max_row + 1) if str(wl.cell(r, 9).value or "").endswith('" - CUSTO"'))
    registrar("M-12b conferência no formato validado (fórmulas a partir de Entradas, checagem, parâmetros)",
              str(wl.cell(4, 4).value).startswith("=IF(Entradas!H5>=0,10084,10001)") and str(wl.cell(custo, 7).value).startswith("=SUM(H")
              and wb["Entradas"].cell(5, 17).value == "=ROUND(G5-H5-P5,2)" and wb["Entradas"]["A3"].value == "Processo")
    registrar("M-15 alerta de set/26 (já lançado manualmente: TXT só de teste)", r["alertas"][0].startswith("Setembro/2026 já foi lançado manualmente"))
    registrar("M-16 processo identificado como na referência (GG do numerário ou OCCT)", p1 and p1["identificacao"] == "OCCT90001/26")
    ja = TMP / "ja.json"
    ja.write_text(json.dumps([{"occt": "OCCT90001/26", "sol": "SOL-2026-000777", "competencia": "2026-09"}]), encoding="utf-8")
    _, r3 = motor(TMP / "x3", sol="SOL-2026-999997", ja_lancados=ja)
    p3 = {p["processo"]: p for p in r3.get("processos_pendentes", [])}.get("OCCT90001/26", {})
    registrar("M-17 processo já lançado em outra SOL não é lançado de novo", any("já lançado na SOL-2026-000777" in m for m in p3.get("motivos", []))
              and "OCCT90001/26" not in [x["processo"] for x in r3["processos_fechados"]])
    registrar("M-18 competência já processada → TXT complementar", r3["complementar"] and r3["arquivos"].get("txt", "").startswith("lanctos_Vgrow_2026-09_complementar_SIMULACAO_"))
    registrar("M-12 planilha de conferência e validação D = C", wb.sheetnames == ["Resumo", "Entradas", "Lançamentos", "Contas", "Origem"]
              and r["validacao_debito_igual_credito"] is True and r["modo"] == "SIMULAÇÃO")
    registrar("M-13 nada em LIBERADOS", not (RAIZ / "LIBERADOS").exists())
    _, r2 = motor(TMP / "x0", informados={"OCCT90001/26": dict(BASE, chegada="2026-09-29")}, sol="SOL-2026-999998", competencia="2026-10")
    p2 = {p["processo"]: p for p in r2.get("processos_pendentes", [])}.get("OCCT90001/26", {})
    registrar("M-04b chegada em mês anterior à competência → pendente (não lança no dia 01 sozinho)",
              any("mês anterior" in m for m in p2.get("motivos", [])) and not r2.get("processos_fechados"))
    p11 = fech.get("OCCT90011/26")
    registrar("P-01 Prestação com ENTRADA = PDF: PDF mantido; depósito registrado; NFs/ICMS verificados", p11 and p11["numerario"]["usado"] == "5000.00"
              and p11["numerario"]["deposito_prestacao"] == "5000.00" and p11["valores"]["num"]["origem"].startswith("EXTRAIDO: numerário PDF")
              and p11["verificacao_nfs"]["confere"] and p11["valores"]["icms_nf"]["origem"].endswith("VERIFICADO na Prestação de contas"))
    p12 = agu.get("OCCT90012/26") or fech.get("OCCT90012/26")
    registrar("P-02 ENTRADA ≠ PDF → depositado, com os dois valores, as fontes e o motivo", p12 and p12["numerario"]["pdf"] == "5000.00"
              and p12["numerario"]["deposito_prestacao"] == "4990.00" and p12["numerario"]["usado"] == "4990.00" and "regra §4" in p12["numerario"]["motivo"]
              and p12["valores"]["num"]["origem"].endswith("ENTRADA DE NUMERÁRIO") and any("OCCT90012/26" in a and "substituído" in a for a in r["alertas"]))
    registrar("P-03 duas ENTRADAS de numerário → ambíguo, bloqueio para o Supervisor", any("ambíguo" in m for m in pend.get("OCCT90013/26", {}).get("motivos", [])))
    registrar("P-04 Prestação de outro processo → bloqueio para o Supervisor", any("OCCT99999/26" in m for m in pend.get("OCCT90014/26", {}).get("motivos", [])))
    registrar("P-05 lista de NFs/ICMS da Prestação diverge → bloqueio para o Supervisor", any("divergem da Prestação" in m for m in pend.get("OCCT90015/26", {}).get("motivos", [])))
    p16 = fech.get("OCCT90016/26")
    registrar("P-06 TOTAL(1) da Prestação ≠ total REAL → alerta com as fontes; comparativo usado", p16 and p16["valores"]["total_real"]["valor"] == "4050.00"
              and any("OCCT90016/26" in a and "TOTAL(1)" in a and "4051.00" in a for a in r["alertas"]))
    p17 = fech.get("OCCT90017/26")
    registrar("P-07 desconto 50% sobre o destacado com o arredondamento do gerador (600,01 → 300,01)", p17
              and next(l for l in p17["lancamentos"] if l["conta"] == 434)["valor"] == "300.01")
    registrar("P-08 acompanhamentos (reembolso opcional, saldo a receber) não bloqueiam", p1 and any("reembolso" in a for a in p1["acompanhamentos"])
              and any("Saldo a receber" in a for a in p1["acompanhamentos"]))
    registrar("P-09 processo aguardando aceite fica fora do TXT", "OCCT90004/26" not in txt.read_text(encoding="cp1252")
              and not any("90004" in l for l in linhas))
    chave = p4["aceite_necessario"]["chave"]
    ac = TMP / "aceites.json"
    ac.write_text(json.dumps({"OCCT90004/26": {"chave": chave, "em": "2026-10-31T15:00:00-03:00"}, "OCCT90013/26": {"chave": "0" * 64, "em": "x"}}), encoding="utf-8")
    _, ra = motor(TMP / "xa", sol="SOL-2026-999996", aceites=ac)
    fa = {p["processo"]: p for p in ra.get("processos_fechados", [])}
    registrar("P-10 aceite registrado para aqueles valores → processo entra no TXT; D = C continua exigido", "OCCT90004/26" in fa and fa["OCCT90004/26"]["confere"]
              and "aceite_supervisor" in fa["OCCT90004/26"]["calculos"] and "OCCT90013/26" not in fa)
    (FIX / "NUMERARIO_OCCT90004_26_FICTICIO.pdf").write_bytes(numerario("OCCT90004/26", "5.006,00"))
    _, rb = motor(TMP / "xb", sol="SOL-2026-999995", aceites=ac)
    agb = {p["processo"]: p for p in rb.get("processos_aguardando_aceite", [])}
    registrar("P-11 documento/valor mudou → aceite anterior não vale (novo aceite exigido)", "OCCT90004/26" in agb
              and agb["OCCT90004/26"]["aceite_necessario"]["diferenca"] == "6.00" and "não vale" in agb["OCCT90004/26"]["aceite_necessario"]["motivo"])
    c1, _ = motor(TMP / "x1", empresa="EMPRESA-TESTE")
    c2, _ = motor(TMP / "x2", pasta="../EMPRESA-TESTE")
    c3, _ = motor(RAIZ / "LIBERADOS" / "VGROW")
    registrar("M-14 recusa outra empresa, '..' e saída no projeto/LIBERADOS", c1 == c2 == c3 == 2 and not (RAIZ / "LIBERADOS").exists())
    return r


# ---------------------------------------------------------------- Coordenador
def coord(*args):
    p = subprocess.run([PY, "-I", str(COORD), *args], cwd=RAIZ, capture_output=True, encoding="utf-8")
    return p.returncode, json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}


RELATORIO = """<!-- RELATÓRIO FICTÍCIO SIMULADO (teste da Importação) -->
▶ EMPRESA: VGROW | CNPJ: a confirmar | COMPETÊNCIA: 2026-09 | MODO: SIMULAÇÃO
RELATÓRIO DO AGENTE DE DOCUMENTOS - {sol}

## 1. Inventário
| # | Arquivo | Tamanho | SHA | Leitura | Marcações | Partes | Analisado? |
|---|---|---|---|---|---|---|---|
| 1 | x | 1 | x | EXTRAIDO_PDF | nenhuma | 1/1 | SIM |

## 5. Pendências propostas
| Nº | Competência | Tipo | Descrição | Documento | Responsável | Status |
|---|---|---|---|---|---|---|
| Nenhum | — | — | — | — | — | — |

## 6. Documentos não analisados
| Arquivo | Código | Motivo | Pendência |
|---|---|---|---|
| Nenhum | — | — | — |

## 7. Tarefas da ordem de serviço
| Tarefa | Situação | Observação |
|---|---|---|
| (1) Inventário | EXECUTADA | — |
"""


def bateria_coordenador():
    c, d = coord("abrir", "--pedido", "Documentos da VGROW, competência 09/2026.", "--pasta", "T-IMP-TMP")
    sol = d["sol"]
    c_antes, d_antes = coord("registrar-importacao", "--sol", sol, "--resultado", str(TMP / "saida-motor" / "resultado.json"))
    rel = TMP / "rel.md"
    rel.write_text(RELATORIO.format(sol=sol), encoding="utf-8")
    coord("encerrar", "--sol", sol, "--relatorio", str(rel))
    saida = TMP / "saida-coord"
    _, r = motor(saida, sol=sol)
    c1, d1 = coord("registrar-importacao", "--sol", sol, "--resultado", str(saida / "resultado.json"))
    reg = _ai.registro_isolado()["solicitacoes"][sol]
    registrar("C-01 Importação devolvida ao Coordenador e consolidada; SOL continua AGUARDANDO_SUPERVISOR", c_antes == 3 and c1 == 0
              and d1["estado"] == "AGUARDANDO_SUPERVISOR" and reg["estado"] == "AGUARDANDO_SUPERVISOR" and reg["importacao"][0]["fechados"] == len(r["processos_fechados"])
              and ordem_ausente(), d1.get("mensagem_supervisor", "")[:110])
    c2, d2 = coord("registrar-importacao", "--sol", sol, "--resultado", str(TMP / "saida-motor" / "resultado.json"))
    registrar("C-05 registro guarda os processos fechados (histórico contra duplicidade)",
              reg["importacao"][0]["processos_fechados"] == [p["processo"] for p in r["processos_fechados"]])
    registrar("C-02 resultado de outra SOL recusado", c2 == 3 and d2.get("resultado") == "RESULTADO_INVALIDO")
    c, d = coord("abrir", "--pedido", "Documentos da EMPRESA-TESTE, 09/2026.", "--pasta", "T004-MISTO")
    sol_t = d["sol"]
    rel.write_text(RELATORIO.format(sol=sol_t).replace("VGROW", "EMPRESA-TESTE"), encoding="utf-8")
    coord("encerrar", "--sol", sol_t, "--relatorio", str(rel))
    c3, d3 = coord("registrar-importacao", "--sol", sol_t, "--resultado", str(saida / "resultado.json"))
    registrar("C-03 Importação recusada para empresa que não é VGROW piloto", c3 == 3 and d3.get("resultado") == "IMPORTACAO_NAO_PERMITIDA")
    registrar("C-04 Importação recusada antes do fim da etapa de Documentos", c_antes == 3 and d_antes.get("resultado") == "IMPORTACAO_NAO_PERMITIDA")


def ordem_ausente():
    return not ORDEM.exists()


# ---------------------------------------------------------------- API
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


PENDENCIAS_REC = ("| P-01 | 2026-09 | Informação ausente | Arquivo não lido pelo extrator: 03_OCCT91001-26_-_DOCUMENTOS.pdf | 03 | Supervisor | Aguardando documento |\n"
                  "| P-07 | 2026-09 | Informação ausente | Não vieram legíveis: NF 1001 (R$ 1.000,00), DUIMP 26BR0000000000-0 e o comprovante de depósito | Doc 5 | Supervisor | Aguardando documento |")
RELATORIO_ATUAL = {"pendencias": None}


def executor_simulado(ordem_de_servico, pasta):
    sol = next(l.split("SOL:")[1].strip() for l in ordem_de_servico.splitlines() if "SOL:" in l)
    empresa = "VGROW" if "VGROW" in ordem_de_servico else "EMPRESA-TESTE"
    rel = RELATORIO.format(sol=sol).replace("VGROW", empresa)
    if RELATORIO_ATUAL["pendencias"]:
        rel = rel.replace("| Nenhum | — | — | — | — | — | — |", RELATORIO_ATUAL["pendencias"])
    return {"relatorio": rel, "problemas": [], "ferramentas": {"Bash": 1}, "bloqueios": 0}


def esperar_reconhecimento(sol):
    for _ in range(600):
        c, e = pedido("GET", f"/api/solicitacoes/{sol}/importacao")
        if c == 200 and (not e.get("disponivel") or e.get("reconhecimento", {}).get("status") not in ("EM_ANDAMENTO", "NAO_EXECUTADO")):
            return e
        time.sleep(0.5)
    return None


def esperar(sol):
    for _ in range(240):
        c, d = pedido("GET", f"/api/solicitacoes/{sol}")
        if c == 200 and d["execucao"]["status"] != "EM_EXECUCAO":
            return d
        time.sleep(0.5)
    return None


def enviar_lote(empresa, arquivos):
    c, d = pedido("POST", "/api/lotes", {"empresa": empresa, "competencia": "2026-09", "instrucao": "Chegaram documentos. Inicie o processamento."})
    lote = d["lote"]
    lotes_criados.append((empresa, lote))
    for nome, conteudo in arquivos:
        pedido("PUT", f"/api/lotes/{lote}/arquivos", conteudo, {"X-Nome-Arquivo": quote(nome), "X-Sha256": hashlib.sha256(conteudo).hexdigest()})
    c, d = pedido("POST", f"/api/lotes/{lote}/iniciar", {"conferencia_humana": True})
    final = esperar(d["sol"])
    if empresa == "VGROW":
        esperar_reconhecimento(d["sol"])
    return final


def bateria_api():
    # registro próprio: o histórico da etapa do Coordenador (OCCT90001/26 já fechado) não deve contaminar esta etapa
    novo = TMP / "solicitacoes-api.json"
    os.environ["AGENTES_PRIME_REGISTRO_SOL"] = str(novo)
    servidor.coordenador.REGISTRO = novo
    arquivos = [(p.name, p.read_bytes()) for p in sorted(FIX.iterdir()) if "90001" in p.name or "90002" in p.name]
    d = enviar_lote("VGROW", arquivos)
    sol = d["sol"]
    c, e = pedido("GET", f"/api/solicitacoes/{sol}/importacao")
    procs = [p["processo"] for p in e.get("processos", [])]
    registrar("A-01 processos do lote VGROW listados para o Supervisor", c == 200 and e["disponivel"] and procs == ["OCCT90001/26", "OCCT90002/26"]
              and d["estado"] == "AGUARDANDO_SUPERVISOR" and d["piloto"] == "PILOTO_REAL_SUPERVISIONADO")
    invalidos = [{"processos": {"OCCT99999/26": {"fob": "1"}}}, {"processos": {"OCCT90001/26": {"fob": "-5"}}},
                 {"processos": {"OCCT90001/26": {"chegada": "15/09/2026"}}}, {"processos": {"OCCT90001/26": {"conta": "55"}}},
                 {"processos": {"OCCT90001/26": {"nfs": "abc"}}}, {"processos": {"OCCT90001/26": {"fatura": "<script>"}}},
                 {"processos": {}, "pasta": "C:/"}, {"processos": {"OCCT90001/26": {"fob": "1"}}}]
    obtidos = [pedido("POST", f"/api/solicitacoes/{sol}/importacao", dict(b, conferencia_supervisor=True) if b is not invalidos[-1] else b)[0] for b in invalidos]
    registrar("A-02 campos informados validados (processo, valor, data, campo extra, NFs, fatura)", all(x == 400 for x in obtidos), " ".join(map(str, obtidos)))
    corpo = {"processos": {"OCCT90001/26": {"fob": "20.000,00", "frete": "3000,00", "chegada": "2026-09-15", "fatura": "TEST/INV/000001",
                                            "nfs": "1001/1002", "icms_nf": "600,00"}, "OCCT90002/26": {}}, "conferencia_supervisor": True}
    c, r = pedido("POST", f"/api/solicitacoes/{sol}/importacao", corpo)
    res = r.get("resultado", {}) if isinstance(r, dict) else {}
    registrar("A-03 Importação executada pelo Coordenador e devolvida", c == 200 and [p["processo"] for p in res.get("processos_fechados", [])] == ["OCCT90001/26"]
              and [p["processo"] for p in res.get("processos_pendentes", [])] == ["OCCT90002/26"] and r["coordenador"]["estado"] == "AGUARDANDO_SUPERVISOR")
    c1, txt = pedido("GET", f"/api/solicitacoes/{sol}/importacao/1/txt")
    c2, _ = pedido("GET", f"/api/solicitacoes/{sol}/importacao/1/conferencia")
    c3, _ = pedido("GET", f"/api/solicitacoes/{sol}/importacao/1/..%2Fresultado.json")
    c4, _ = pedido("GET", f"/api/solicitacoes/{sol}/importacao/9/txt")
    registrar("A-04 download só do TXT e da planilha gerados", c1 == 200 and isinstance(txt, bytes) and txt.startswith(b"15/09/2026;10084;;950;")
              and c2 == 200 and c3 == 404 and c4 == 404)
    d3 = enviar_lote("VGROW", arquivos)
    c, r3 = pedido("POST", f"/api/solicitacoes/{d3['sol']}/importacao", corpo)
    res3 = r3.get("resultado", {}) if isinstance(r3, dict) else {}
    pend3 = {p["processo"]: p for p in res3.get("processos_pendentes", [])}
    registrar("A-07 mesmo processo em nova SOL: Coordenador informa o histórico e não há relançamento", c == 200 and not res3.get("processos_fechados")
              and any(f"já lançado na {sol}" in m for m in pend3.get("OCCT90001/26", {}).get("motivos", [])) and res3.get("complementar") is True)
    d2 = enviar_lote("EMPRESA-TESTE", [("d1.txt", (RAIZ / "CLIENTES/EMPRESA-TESTE/TREINAMENTO/2026-09/DOCUMENTOS/D1_NF_COMPRA_FORNECEDOR.txt").read_bytes())])
    c, e = pedido("GET", f"/api/solicitacoes/{d2['sol']}/importacao")
    c5, _ = pedido("POST", f"/api/solicitacoes/{d2['sol']}/importacao", corpo)
    registrar("A-05 Importação indisponível para empresa que não é VGROW", c == 200 and e["disponivel"] is False and c5 == 409)
    # A-08 resumo das etapas para o Escritório Virtual (somente leitura: não muda o estado da SOL)
    c, est = pedido("GET", "/api/estado")
    por_sol = {x["sol"]: x.get("etapas", {}) for x in est.get("recentes", [])}
    e1, e2 = por_sol.get(sol, {}), por_sol.get(d2["sol"], {})
    _, det = pedido("GET", f"/api/solicitacoes/{sol}")
    registrar("A-08 etapas da SOL (Documentos, reconhecimento, Importação) com horários, sem alterar o estado", c == 200
              and e1.get("documentos", {}).get("status") == "CONCLUIDA" and bool(e1["documentos"].get("fim"))
              and e1.get("importacao", {}).get("status") == "CONCLUIDA" and e1["importacao"].get("n") == 1
              and bool(e1["importacao"].get("inicio")) and bool(e1["importacao"].get("fim"))
              and e1["importacao"].get("resumo") == {"fechados": 1, "bloqueios": 1, "aguardando_aceite": 0}
              and e1.get("reconhecimento", {}).get("status") in ("PRONTO", "FALHOU", "EM_ANDAMENTO")
              and e2.get("importacao", {}).get("status") == "NAO_APLICAVEL" and det.get("etapas") == e1
              and det["estado"] == "AGUARDANDO_SUPERVISOR" and servidor.EM_IMPORTACAO["sol"] is None, json.dumps(e1, ensure_ascii=False)[:160])
    # A-09 Importação em andamento × sem resultado (pasta fictícia no runtime temporário do teste)
    extra = servidor.RUNTIME / "execucoes" / sol / "importacao-2"
    extra.mkdir()
    (extra / "informados.json").write_text("{}", encoding="utf-8")
    registro_sol = servidor.coordenador.ler_registro()["solicitacoes"][sol]
    execucao_sol = servidor.ler_json(servidor.RUNTIME / "execucoes" / sol / "execucao.json")
    servidor.EM_IMPORTACAO["sol"] = sol
    andamento = servidor.etapas_de(sol, registro_sol, execucao_sol)["importacao"]
    servidor.EM_IMPORTACAO["sol"] = None
    falhou = servidor.etapas_de(sol, registro_sol, execucao_sol)["importacao"]
    remover(extra)
    registrar("A-09 Importação em andamento só enquanto o Coordenador aguarda o retorno; sem resultado depois → FALHOU",
              andamento["status"] == "EM_ANDAMENTO" and andamento["n"] == 2 and andamento["fim"] is None and falhou["status"] == "FALHOU")
    # A-10 falha seguida de nova tentativa: número próprio, tentativas anteriores preservadas, sem repetição automática
    pasta_sol = servidor.RUNTIME / "execucoes" / sol
    resultado_1 = (pasta_sol / "importacao-1" / "resultado.json").read_bytes()
    falha = TMP / "importacao_que_falha.py"
    falha.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")   # motor fictício que falha sem devolver resultado
    original = servidor.FERRAMENTA_IMPORTACAO
    servidor.FERRAMENTA_IMPORTACAO = falha
    try:
        c_falha, _ = pedido("POST", f"/api/solicitacoes/{sol}/importacao", corpo)
    finally:
        servidor.FERRAMENTA_IMPORTACAO = original
    informados_2 = (pasta_sol / "importacao-2" / "informados.json").read_bytes() if (pasta_sol / "importacao-2").exists() else None
    etapa_falha = pedido("GET", f"/api/solicitacoes/{sol}")[1]["etapas"]["importacao"]
    registros_antes = len(servidor.coordenador.ler_registro()["solicitacoes"][sol].get("importacao", []))
    c_nova, r_nova = pedido("POST", f"/api/solicitacoes/{sol}/importacao", corpo)
    etapa_nova = pedido("GET", f"/api/solicitacoes/{sol}")[1]["etapas"]["importacao"]
    registros_depois = len(servidor.coordenador.ler_registro()["solicitacoes"][sol].get("importacao", []))
    c_txt2 = pedido("GET", f"/api/solicitacoes/{sol}/importacao/2/txt")[0]
    c_txt1, txt1 = pedido("GET", f"/api/solicitacoes/{sol}/importacao/1/txt")
    lista = [x["n"] for x in pedido("GET", f"/api/solicitacoes/{sol}/importacao")[1].get("execucoes", [])]
    registrar("A-10 falha seguida de nova tentativa: identificador próprio, tentativas anteriores preservadas, nada sobrescrito",
              c_falha == 500 and informados_2 is not None and not (pasta_sol / "importacao-2" / "resultado.json").exists()
              and etapa_falha["status"] == "FALHOU" and etapa_falha["n"] == 2
              and c_nova == 200 and r_nova.get("n") == 3 and etapa_nova["status"] == "CONCLUIDA" and etapa_nova["n"] == 3
              and (pasta_sol / "importacao-1" / "resultado.json").read_bytes() == resultado_1
              and (pasta_sol / "importacao-2" / "informados.json").read_bytes() == informados_2
              and c_txt2 == 404 and c_txt1 == 200 and txt == txt1 and lista == [1, 3]
              and registros_depois == registros_antes + 1,
              f"falha {c_falha} (n=2) · nova {c_nova} (n={r_nova.get('n') if isinstance(r_nova, dict) else '?'}) · execuções válidas {lista} · "
              f"registros do Coordenador {registros_antes}→{registros_depois}")
    fonte = MOTOR.read_text(encoding="utf-8")
    chamadas = re.findall(r"subprocess\.run\(\[([^\]]+)\]", fonte)
    registrar("A-06 Importação não aciona Claude nem outro agente; só o extrator", ordem_ausente() and not re.search(r"claude\.exe|claude\b.*-p|subagent_type|\"Agent\"|\"Task\"", fonte)
              and len(chamadas) == 1 and "EXTRATOR" in chamadas[0], "única chamada externa: extrator (canal homologado)")


def bateria_reconhecimento():
    fx.gravar(FIX_REC)
    saida = TMP / "rec.json"
    p = subprocess.run([PY, "-I", str(RECONHECEDOR), "--pasta", FIX_REC.name, "--saida", str(saida)], cwd=RAIZ, capture_output=True, encoding="utf-8")
    r = json.loads(saida.read_text(encoding="utf-8"))["processos"] if p.returncode == 0 else {}
    c1 = r.get("OCCT91001/26", {}).get("campos", {})
    registrar("R-01 DUIMP em imagem reconhecida por OCR (frete, chegada, fatura)", c1.get("frete", {}).get("valor") == "3000.00"
              and c1.get("chegada", {}).get("valor") == "2026-09-15" and c1.get("fatura", {}).get("valor") == "TEST/INV/000001"
              and c1.get("frete", {}).get("origem", "").startswith("OCR"), f"{r.get('OCCT91001/26', {}).get('paginas_ocr')} página(s) por OCR")
    registrar("R-02 FOB reconhecido (separador duvidoso → não aceita sozinho)", c1.get("fob", {}).get("valor") == "20000.00"
              and c1.get("fob", {}).get("status") in ("OK", "ILEGIVEL"), c1.get("fob", {}).get("status", ""))
    registrar("R-03 NFs pela chave de acesso (DV) e DANFE de outro destinatário ignorada", c1.get("nfs", {}).get("valor") == ["1001", "1002"]
              and c1.get("nfs", {}).get("status") == "OK")
    registrar("R-04 ICMS destacado = soma das DANFEs da VGROW", c1.get("icms_nf", {}).get("valor") == "600.00", c1.get("icms_nf", {}).get("evidencia", ""))
    c2 = r.get("OCCT91002/26", {}).get("campos", {})
    registrar("R-05 DUIMP com camada de texto lida sem OCR", all(c2.get(k, {}).get("status") == "OK" and c2[k].get("origem", "").startswith("TEXTO_PDF")
              for k in ("fob", "frete", "chegada", "fatura")) and c2["fob"]["valor"] == "1234.56" and r["OCCT91002/26"]["paginas_ocr"] == 0)
    registrar("R-06 sem DANFE → NFs e ICMS AUSENTES (intervenção só nesses campos)", c2.get("nfs", {}).get("status") == "AUSENTE"
              and c2.get("icms_nf", {}).get("status") == "AUSENTE")
    c3 = r.get("OCCT91003/26", {}).get("campos", {})
    registrar("R-07 DUIMP de outro processo → CONFLITO", all(c3.get(k, {}).get("status") == "CONFLITO" for k in ("fob", "frete", "chegada", "fatura")))
    c4 = r.get("OCCT91004/26", {}).get("campos", {})
    registrar("R-08 dois FOB diferentes → CONFLITO com candidatos", c4.get("fob", {}).get("status") == "CONFLITO"
              and c4["fob"].get("candidatos") == ["20000.00", "21000.00"] and c4.get("frete", {}).get("status") == "OK")
    r5 = r.get("OCCT91005/26", {})
    registrar("R-09 PDF corrompido → pendência e campos AUSENTES", r5.get("pendencias") and all(v["status"] == "AUSENTE" for v in r5.get("campos", {}).values()))
    q1 = subprocess.run([PY, "-I", str(RECONHECEDOR), "--pasta", FIX_REC.name, "--saida", str(RAIZ / "x.json")], cwd=RAIZ, capture_output=True)
    q2 = subprocess.run([PY, "-I", str(RECONHECEDOR), "--pasta", "../EMPRESA-TESTE", "--saida", str(TMP / "y.json")], cwd=RAIZ, capture_output=True)
    r1 = r.get("OCCT91001/26", {})
    registrar("R-11 nº da DUIMP capturado; páginas submetidas ao OCR ≠ páginas com campos identificados",
              r1.get("duimp") == ["26BR0000000000-0"] and r1.get("paginas_submetidas_ocr") == [1, 2, 3, 4]
              and r1.get("paginas_com_campos", {}).get("frete") == [1] and r1.get("paginas_com_campos", {}).get("nfs") == [2, 4]
              and r1.get("paginas_sem_campos") == [3], f"sem campos: {r1.get('paginas_sem_campos')}")
    registrar("R-10 recusa saída no projeto e pasta fora da VGROW", q1.returncode == q2.returncode == 2 and not (RAIZ / "x.json").exists())


def bateria_api_reconhecimento():
    RELATORIO_ATUAL["pendencias"] = PENDENCIAS_REC
    lote = [("OCCT91001-26 - COMPARATIVO.xlsx", comparativo()), ("NUMERARIO_OCCT91001_26_FICTICIO.pdf", numerario("OCCT91001/26")),
            ("OCCT91001-26 - DOCUMENTOS.pdf", (FIX_REC / "OCCT91001-26 - DOCUMENTOS.pdf").read_bytes())]
    d = enviar_lote("VGROW", lote)
    sol = d["sol"]
    e = esperar_reconhecimento(sol)
    campos = e["reconhecimento"]["processos"]["OCCT91001/26"]
    registrar("R-A1 reconhecimento automático disparado pelo Coordenador após Documentos", e["reconhecimento"]["status"] == "PRONTO"
              and campos["nfs"]["valor"] == ["1001", "1002"])
    valores = {c: ("/".join(v["valor"]) if isinstance(v["valor"], list) else v["valor"]) for c, v in campos.items() if v.get("valor") is not None}
    nao_ok = [c for c, v in campos.items() if v["status"] != "OK" and v.get("valor") is not None]
    c0, _ = pedido("POST", f"/api/solicitacoes/{sol}/importacao", {"processos": {"OCCT91001/26": valores}})
    c1, e1 = pedido("POST", f"/api/solicitacoes/{sol}/importacao", {"processos": {"OCCT91001/26": valores}, "conferencia_supervisor": True})
    registrar("R-A2 sem conferência geral ou sem confirmar campo duvidoso → recusado", c0 == 400 and (c1 == 400 if nao_ok else c1 == 200),
              f"campos a confirmar: {nao_ok or 'nenhum'}")
    c2, r2 = pedido("POST", f"/api/solicitacoes/{sol}/importacao", {"processos": {"OCCT91001/26": valores}, "confirmados": {"OCCT91001/26": nao_ok},
                                                                      "conferencia_supervisor": True})
    fech = (r2.get("resultado") or {}).get("processos_fechados", []) if isinstance(r2, dict) else []
    origem = fech[0]["valores"] if fech else {}
    registrar("R-A3 conferido/confirmado → fechado, sem digitar os seis campos", c2 == 200 and fech and fech[0]["confere"]
              and origem["nfs"]["origem"].startswith("RECONHECIDO") and origem["frete"]["origem"].endswith("CONFERIDO_PELO_SUPERVISOR")
              and all("CONFIRMADO_PELO_SUPERVISOR" in origem[c]["origem"] for c in nao_ok), f"D = C = {fech[0]['debito'] if fech else '?'}")
    corrigido = dict(valores, frete="3.100,00")
    c3, r3 = pedido("POST", f"/api/solicitacoes/{sol}/importacao", {"processos": {"OCCT91001/26": corrigido}, "confirmados": {"OCCT91001/26": nao_ok},
                                                                      "conferencia_supervisor": True})
    f3 = (r3.get("resultado") or {}).get("processos_fechados", []) if isinstance(r3, dict) else []
    registrar("R-A4 correção do Supervisor registrada (valor reconhecido preservado na origem)", c3 == 200 and f3
              and f3[0]["valores"]["frete"]["valor"] == "3100.00" and f3[0]["valores"]["frete"]["origem"] == "CORRIGIDO_PELO_SUPERVISOR (reconhecido: 3000.00)")
    reg = _ai.registro_isolado()["solicitacoes"][sol]
    registrar("R-A5 SOL continua AGUARDANDO_SUPERVISOR; nada encaminhado sem ação do Supervisor", reg["estado"] == "AGUARDANDO_SUPERVISOR"
              and len(reg.get("importacao", [])) == 2 and ordem_ausente())
    # evidências complementares e quadro de pendências (relatório original preservado)
    c, e2 = pedido("GET", f"/api/solicitacoes/{sol}/importacao")
    ev = next(x for x in e2["evidencias_complementares"] if x["arquivo"].endswith("DOCUMENTOS.pdf"))
    registrar("Q-01 Documentos.pdf: recebido, não lido pelo extrator; leitura específica com páginas (não 'analisado')", ev["estado"] == "RECEBIDO_NAO_LIDO"
              and ev["leitura_especifica"]["submetidas_ocr"] == [1, 2, 3, 4] and ev["leitura_especifica"]["sem_campos_identificados"] == [3]
              and "NÃO foi analisado por inteiro" in ev["leitura_especifica"]["observacao"])
    q = {x["pendencia"]: x for x in e2["quadro_pendencias"]}
    p07 = q.get("P-07", {})
    itens = {a["item"]: a for a in p07.get("atualizacoes", [])}
    registrar("Q-02 P-07 atualizada só por identificador (NF 1001, DUIMP); texto original preservado; não encerrada", p07.get("estado") == "PARCIALMENTE_ATUALIZADA"
              and itens.get("NF 1001", {}).get("estado") == "CONFIRMADO_PELO_SUPERVISOR" and "DUIMP 26BR0000000000-0" in itens
              and "não verificados" in itens["NF 1001"]["nao_verificado"] and "comprovante de depósito" in " ".join(p07["texto_original"]))
    registrar("Q-03 P-01: documento recebido e não lido, com páginas sem campos", q.get("P-01", {}).get("atualizacoes", [{}])[0].get("estado") == "RECEBIDO_NAO_LIDO")
    registrar("Q-04 trava cadastral do piloto visível e separada (não é regra contábil; não resolvida pelo OCR)",
              (e2.get("trava_cadastral") or {}).get("estado") == "TRAVA_OPERACIONAL_PILOTO")
    c1, _ = pedido("POST", f"/api/solicitacoes/{sol}/pendencias", {"pendencia": "P-99", "decisao": "RESOLVIDA", "justificativa": "teste ficticio"})
    c2, _ = pedido("POST", f"/api/solicitacoes/{sol}/pendencias", {"pendencia": "P-07", "decisao": "RESOLVIDA", "justificativa": "x"})
    c3, _ = pedido("POST", f"/api/solicitacoes/{sol}/pendencias", {"pendencia": "P-07", "decisao": "RESOLVIDA", "justificativa": "Conferido no documento físico (teste fictício)."})
    q3 = {x["pendencia"]: x for x in pedido("GET", f"/api/solicitacoes/{sol}/importacao")[1]["quadro_pendencias"]}
    registrar("Q-05 resolução só por decisão do Supervisor, com justificativa", c1 == 404 and c2 == 400 and c3 == 200
              and q3["P-07"]["estado"] == "RESOLVIDA" and q3["P-01"]["estado"] == "PARCIALMENTE_ATUALIZADA")
    RELATORIO_ATUAL["pendencias"] = None
    # aceite pela API: numerário 5.000,01 → diferença 0,01
    novo = TMP / "solicitacoes-aceite.json"          # registro próprio: OCCT91001/26 já foi fechado acima (evita "já lançado")
    os.environ["AGENTES_PRIME_REGISTRO_SOL"] = str(novo)
    servidor.coordenador.REGISTRO = novo
    lote2 = [("OCCT91001-26 - COMPARATIVO.xlsx", comparativo()), ("NUMERARIO_OCCT91001_26_FICTICIO.pdf", numerario("OCCT91001/26", "5.000,01")),
             ("OCCT91001-26 - DOCUMENTOS.pdf", (FIX_REC / "OCCT91001-26 - DOCUMENTOS.pdf").read_bytes())]
    d2 = enviar_lote("VGROW", lote2)
    sol2 = d2["sol"]
    camp2 = esperar_reconhecimento(sol2)["reconhecimento"]["processos"]["OCCT91001/26"]
    val2 = {c: ("/".join(v["valor"]) if isinstance(v["valor"], list) else v["valor"]) for c, v in camp2.items() if v.get("valor") is not None}
    conf2 = [c for c, v in camp2.items() if v["status"] != "OK" and v.get("valor") is not None]
    c, r4 = pedido("POST", f"/api/solicitacoes/{sol2}/importacao", {"processos": {"OCCT91001/26": val2}, "confirmados": {"OCCT91001/26": conf2},
                                                                       "conferencia_supervisor": True})
    pedido_aceite = (r4["resultado"].get("processos_aguardando_aceite") or [{}])[0].get("aceite_necessario", {})
    c5, _ = pedido("POST", f"/api/solicitacoes/{sol2}/importacao/aceites", {"processo": "OCCT91001/26", "chave": "f" * 64})
    c6, r6 = pedido("POST", f"/api/solicitacoes/{sol2}/importacao/aceites", {"processo": "OCCT91001/26", "chave": pedido_aceite.get("chave", "")})
    reg2 = _ai.registro_isolado()["solicitacoes"][sol2]
    registrar("Q-06 aceite pela tela: chave errada recusada; aceite registrado; processo entra no TXT",
              pedido_aceite.get("diferenca") == "0.01" and c5 == 409 and c6 == 200 and [p["processo"] for p in r6["resultado"]["processos_fechados"]] == ["OCCT91001/26"]
              and reg2["aceites"]["OCCT91001/26"]["diferenca"] == "0.01" and reg2["estado"] == "AGUARDANDO_SUPERVISOR")
    # Q-07 clique repetido no aceite já registrado (botão de um retorno antigo): recusado com a situação real, sem novo aceite
    pasta2 = servidor.RUNTIME / "execucoes" / sol2
    antes = sorted(p.name for p in pasta2.glob("importacao-*"))
    eventos_antes = len(reg2["eventos"])
    c7, r7 = pedido("POST", f"/api/solicitacoes/{sol2}/importacao/aceites", {"processo": "OCCT91001/26", "chave": pedido_aceite.get("chave", "")})
    reg3 = _ai.registro_isolado()["solicitacoes"][sol2]
    msg7 = (r7 or {}).get("erro", "") if isinstance(r7, dict) else str(r7)
    registrar("Q-07 aceite repetido: informa que já foi registrado (não \"valores mudaram\"); nada registrado nem reexecutado",
              c7 == 409 and "já foi registrado" in msg7 and "mudaram" not in msg7 and len(reg3["eventos"]) == eventos_antes
              and reg3["aceites"] == reg2["aceites"] and sorted(p.name for p in pasta2.glob("importacao-*")) == antes, msg7)
    # Q-08 tela: retorno antigo mostra o aceite registrado, sem botão de aceite
    registrar("Q-08 tela da SOL: nenhum botão de aceite para diferença já aceita; retorno antigo mostra o aceite registrado",
              *tela_aceite(sol2))


def tela_aceite(sol):
    """Abre a página servida por este servidor de teste no Chrome sem interface e lê a seção da Importação da SOL."""
    sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
    from e2e_navegador import CDP, CHROME
    perfil = tempfile.mkdtemp(prefix="chrome-aceite-")
    url = f"http://127.0.0.1:{PORTA}/"
    chrome = subprocess.Popen([str(CHROME), "--headless=new", "--remote-debugging-port=9337", f"--user-data-dir={perfil}",
                               "--window-size=1400,1000", "--no-first-run", "--disable-extensions", url])
    try:
        for _ in range(50):
            try:
                alvos = json.load(urllib.request.urlopen("http://127.0.0.1:9337/json/list"))
                pagina = next(a for a in alvos if a["type"] == "page" and a["url"].startswith(url))
                break
            except Exception:
                time.sleep(0.3)
        cdp = CDP(pagina["webSocketDebuggerUrl"])
        time.sleep(2)
        cdp.js("document.querySelector('.op-botao').click()")
        time.sleep(1.5)
        cdp.js(f"Array.from(document.querySelectorAll('.op-recente')).find(b => b.textContent.startsWith('{sol}')).click()")
        texto = ""
        for _ in range(40):
            time.sleep(0.5)
            texto = cdp.js("(document.querySelector('.op-importacao') || {}).textContent || ''") or ""
            if "Retorno da Importação nº" in texto:
                break
        time.sleep(0.5)
        texto = cdp.js("document.querySelector('.op-importacao').textContent")
        botoes = cdp.js("Array.from(document.querySelectorAll('.op-importacao button')).filter(b => b.textContent.startsWith('Aceitar a diferença')).length")
    finally:
        chrome.terminate()
    return (botoes == 0 and "Aceite registrado pelo Supervisor" in texto and "não corresponde" not in texto,
            f"botões de aceite: {botoes}")


def main():
    global SRV, PORTA
    sys.stdout.reconfigure(encoding="utf-8")
    if ORDEM.exists() or FIX.exists() or FIX_REC.exists() or not (VGROW / "CADASTRO.md").is_file():
        print("ABORTADO: ordem ativa, pasta temporária existente ou cadastro da VGROW ausente; nada foi feito.")
        return 1
    servidor.EXECUTAR_AGENTE = executor_simulado
    SRV = servidor.iniciar(0)
    PORTA = SRV.server_port
    threading.Thread(target=SRV.serve_forever, daemon=True).start()
    try:
        preparar()
        bateria_motor()
        bateria_coordenador()
        bateria_reconhecimento()
        bateria_api()
        bateria_api_reconhecimento()
    finally:
        SRV.shutdown()
        ORDEM.unlink(missing_ok=True)
        remover(FIX)
        remover(FIX_REC)
        for empresa, lote in lotes_criados:
            remover(RAIZ / "CLIENTES" / empresa / "RECEBIDOS" / "2026-09" / lote)
        for empresa in ("VGROW", "EMPRESA-TESTE"):
            r = RAIZ / "CLIENTES" / empresa / "RECEBIDOS"
            for sub in (r / "2026-09", r):
                if sub.exists() and not any(sub.iterdir()):
                    os.chmod(sub, stat.S_IWRITE | stat.S_IREAD)
                    sub.rmdir()
        shutil.rmtree(TMP, ignore_errors=True)
    largura = max(len(c) for c, _, _ in resultados)
    for c, ok, det in resultados:
        print(f"{'PASS' if ok else 'FAIL'}  {c.ljust(largura)}  {det}")
    falhas = [c for c, ok, _ in resultados if not ok]
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - len(falhas)} PASS · {len(falhas)} FAIL")
    print(f"ordem ativa residual: {'SIM' if ORDEM.exists() else 'não'} · fixtures residuais: {'SIM' if FIX.exists() else 'não'} · "
          f"LIBERADOS: {'SIM' if (RAIZ / 'LIBERADOS').exists() else 'não'}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
