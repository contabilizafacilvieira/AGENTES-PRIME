"""Concorrência no registro de solicitações (COORDENADOR-GERAL/ferramentas/coordenador.py) — registro TEMPORÁRIO, dados fictícios.

C-01 REPRODUZ o risco: duas leituras-modificações-gravações simultâneas SEM trava perdem uma atualização.
C-02..C-06 comprovam a proteção: mesma operação com trava_registro; comandos reais do Coordenador em paralelo; prazo esgotado com
recusa explícita e registro intacto; geração de TXT concorrente incompatível (só uma aceita); JSON sempre íntegro, sem temporários.
REG-ATOMIC-01..06: gravação por substituição atômica x leitores simultâneos em OUTRO processo (causa da falha intermitente do gate:
leitura direta, sem tratar a violação de compartilhamento do Windows durante os.replace); repetição limitada e determinística só
para PermissionError; falha persistente e JSON inválido aparecem como erro; nenhuma entrada perdida; registro operacional intocado.
Não usa nem altera o registro operacional.

Uso: .venv/Scripts/python.exe -I TESTES/REGISTRO/testar_concorrencia_registro.py
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="prime-concorrencia-"))
REG = TMP / "registro.json"
ENV = dict(os.environ, AGENTES_PRIME_REGISTRO_SOL=str(REG), AGENTES_PRIME_ORDEM_ATIVA=str(TMP / "ordem-ativa.json"),
           AGENTES_PRIME_CLIENTES=str(TMP / "CLIENTES"))
COORD = RAIZ / "COORDENADOR-GERAL" / "ferramentas" / "coordenador.py"
os.environ.update({k: ENV[k] for k in ("AGENTES_PRIME_REGISTRO_SOL", "AGENTES_PRIME_ORDEM_ATIVA", "AGENTES_PRIME_CLIENTES")})
(TMP / "CLIENTES").mkdir()
sys.path.insert(0, str(RAIZ / "COORDENADOR-GERAL" / "ferramentas"))
import coordenador  # noqa: E402
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado  # noqa: E402

resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:300]))


def sol(n, estado="DOCUMENTOS_EM_ANDAMENTO", **extra):
    return f"SOL-2026-9{n:05d}", dict({"sol": f"SOL-2026-9{n:05d}", "empresa": "EMPRESA-CONC-TMP", "competencia": "2026-10",
                                       "estado": estado, "eventos": [], "motivos": []}, **extra)


def base(n=2, **extra):
    coordenador.gravar_json(REG, {"solicitacoes": dict(sol(i, **extra) for i in range(1, n + 1))})


SCRIPT = r'''
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
import coordenador as c
def operar():
    r = c.ler_registro()
    time.sleep(float(sys.argv[3]))           # janela entre leitura e gravação (simula operação lenta)
    r["solicitacoes"][sys.argv[2]]["eventos"].append({"evento": "alteracao de " + sys.argv[2]})
    c.gravar_json(c.REGISTRO, r)
if sys.argv[4] == "com_trava":
    with c.trava_registro():
        operar()
else:
    operar()
'''


ESCRITOR = r'''
import sys
sys.path.insert(0, sys.argv[1])
import coordenador as c
# grava N versões COMPLETAS e crescentes do registro (versão k tem as entradas 0..k, cada uma com carga para alongar a gravação)
for k in range(int(sys.argv[2])):
    c.gravar_json(c.REGISTRO, {"versao": k, "solicitacoes": {f"SOL-2026-8{i:05d}": {"sol": f"SOL-2026-8{i:05d}", "carga": "x" * 2000}
                                                           for i in range(k + 1)}})
'''

ADICIONADOR = r'''
import sys
sys.path.insert(0, sys.argv[1])
import coordenador as c
# leitura-modificação-gravação SOB a trava oficial: cada processo acrescenta suas próprias entradas
for i in range(int(sys.argv[3])):
    with c.trava_registro():
        r = c.ler_registro()
        r["solicitacoes"][f"SOL-{sys.argv[2]}-{i:04d}"] = {"sol": f"SOL-{sys.argv[2]}-{i:04d}"}
        c.gravar_json(c.REGISTRO, r)
'''


def leitor_concorrente(versoes):
    """Escritor em OUTRO processo + leitores neste processo (helper dos testes e leitura de produção) até o escritor terminar."""
    s = TMP / "escritor.py"
    s.write_text(ESCRITOR, encoding="utf-8")
    coordenador.gravar_json(REG, {"versao": -1, "solicitacoes": {}})
    proc = subprocess.Popen([sys.executable, "-I", str(s), str(COORD.parent), str(versoes)], env=ENV)
    leituras, invalidas, inconsistentes, ultima = 0, [], [], -1
    while proc.poll() is None or leituras == 0:
        for ler in (lambda: ambiente_isolado.ler_json_substituido(REG), coordenador.ler_registro):
            try:
                d = ler()
            except ValueError as exc:                  # JSON parcial/inválido
                invalidas.append(str(exc)[:80])
                continue
            leituras += 1
            k = d["versao"]
            if set(d["solicitacoes"]) != {f"SOL-2026-8{i:05d}" for i in range(k + 1)} or k < ultima:
                inconsistentes.append(k)
            ultima = max(ultima, k)
    proc.wait(120)
    return {"codigo": proc.returncode, "leituras": leituras, "invalidas": invalidas, "inconsistentes": inconsistentes,
            "final": coordenador.ler_registro()["versao"]}


def paralelo(com_trava):
    s = TMP / "rmw.py"
    s.write_text(SCRIPT, encoding="utf-8")
    ps = [subprocess.Popen([sys.executable, "-I", str(s), str(COORD.parent), f"SOL-2026-9{i:05d}", "0.8", com_trava], env=ENV)
          for i in (1, 2)]
    for p in ps:
        p.wait(60)
    r = coordenador.ler_registro()["solicitacoes"]
    return [len(r[f"SOL-2026-9{i:05d}"]["eventos"]) for i in (1, 2)]


def cli(*args, env=None):
    p = subprocess.run([sys.executable, "-I", str(COORD), *args], env=env or ENV, capture_output=True, encoding="utf-8")
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        return p.returncode, {"saida": p.stdout[-200:], "erro": p.stderr[-300:]}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        base()
        eventos = paralelo("sem_trava")
        registrar("C-01 REPRODUZIDO: sem trava, duas leituras-modificações-gravações simultâneas perdem uma atualização",
                  sorted(eventos) == [0, 1], f"eventos por SOL = {eventos}")
        base()
        eventos = paralelo("com_trava")
        registrar("C-02 com trava_registro: as duas atualizações são preservadas (a segunda espera a primeira)", eventos == [1, 1], eventos)

        base(8)
        saidas = [None] * 8
        def cancelar(i):
            saidas[i - 1] = cli("cancelar", "--sol", f"SOL-2026-9{i:05d}", "--motivo", f"cancelamento ficticio {i}")
        ts = [threading.Thread(target=cancelar, args=(i,)) for i in range(1, 9)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        r = coordenador.ler_registro()["solicitacoes"]
        registrar("C-03 oito comandos reais do Coordenador em paralelo (cancelar SOLs diferentes): todos registrados, nenhum evento perdido",
                  all(c == 0 for c, _ in saidas) and all(x["estado"] == "CANCELADA" and len(x["eventos"]) == 1 for x in r.values()),
                  [c for c, _ in saidas])

        base(1)
        antes = hashlib.sha256(REG.read_bytes()).hexdigest()
        with coordenador.trava_registro():
            inicio = time.monotonic()
            codigo, resp = cli("cancelar", "--sol", "SOL-2026-900001", "--motivo", "deve esperar",
                               env=dict(ENV, AGENTES_PRIME_TRAVA_REGISTRO_TIMEOUT="1.5"))
            duracao = time.monotonic() - inicio
        registrar("C-04 trava ocupada além do prazo: recusa EXPLÍCITA (TRAVA_REGISTRO_INDISPONIVEL), nada alterado, sem repetição automática",
                  codigo != 0 and resp.get("resultado") == "TRAVA_REGISTRO_INDISPONIVEL" and 1.4 <= duracao < 10
                  and hashlib.sha256(REG.read_bytes()).hexdigest() == antes, f"{codigo} {resp} {duracao:.1f}s")

        aprov = {"em": "2026-11-05T10:00:00-03:00", "versoes_aprovadas": {"BANCOS": "x"}, "fatos_aprovados": {},
                 "liberacao_dominio": "AGUARDANDO_GERACAO_TXT", "tentativas_exportacao": []}
        coordenador.gravar_json(REG, {"solicitacoes": dict([sol(1, estado="FECHAMENTO_APROVADO", aprovacao=aprov)])})
        saidas = [None, None]
        def preparar(i):
            saidas[i] = cli("registrar-liberacao", "--sol", "SOL-2026-900001", "--situacao", "PREPARANDO",
                            "--arquivo", f"LIBERADOS/X/2026-10/arquivo-{i}.txt", "--sha256", f"{i}" * 64)
        ts = [threading.Thread(target=preparar, args=(i,)) for i in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        ap = coordenador.ler_registro()["solicitacoes"]["SOL-2026-900001"]["aprovacao"]
        registrar("C-05 duas gerações de TXT concorrentes para a mesma aprovação: exatamente UMA aceita, a outra recusada pelo estado",
                  sorted(c == 0 for c, _ in saidas) == [False, True] and any(r.get("resultado") == "ESTADO_INVALIDO" for _, r in saidas)
                  and len(ap["tentativas_exportacao"]) == 1 and ap["liberacao_dominio"] == "PREPARANDO",
                  [(c, r.get("resultado")) for c, r in saidas])

        json.loads(REG.read_text(encoding="utf-8"))
        temporarios = list(TMP.glob("*.tmp"))
        registrar("C-06 registro sempre JSON íntegro e sem arquivos temporários residuais", not temporarios, temporarios)

        # ---------------- REG-ATOMIC: gravação por substituição atômica x leitura simultânea (Windows)
        op = ambiente_isolado.REGISTRO_OPERACIONAL
        op_antes = (hashlib.sha256(op.read_bytes()).hexdigest(), op.stat().st_mtime_ns) if op.exists() else None
        conc = leitor_concorrente(400)
        registrar("REG-ATOMIC-01 leitor (outro processo gravando 400 versões) nunca recebe JSON parcial: toda leitura é uma versão completa",
                  conc["codigo"] == 0 and conc["leituras"] > 0 and not conc["invalidas"] and not conc["inconsistentes"]
                  and conc["final"] == 399, {k: (v if k != "invalidas" else v[:3]) for k, v in conc.items()})

        erros = []
        for k in range(300):
            dados = {"versao": k, "solicitacoes": dict(sol(i) for i in range(1, k % 7 + 2))}
            coordenador.gravar_json(REG, dados)
            if ambiente_isolado.ler_json_substituido(REG) != dados or coordenador.ler_registro() != dados:
                erros.append(k)
        registrar("REG-ATOMIC-02 300 gravações e leituras repetidas: JSON sempre válido e igual ao gravado; sem temporários residuais",
                  not erros and not list(TMP.glob("*.tmp")), erros[:5])

        import pathlib
        original = pathlib.Path.read_text
        estado = {"n": 0}

        def violacao_3x(self, *a, **k):            # simula a janela de os.replace: 3 violações de compartilhamento, depois lê
            if self == REG and estado["n"] < 3:
                estado["n"] += 1
                raise PermissionError(13, "violação de compartilhamento simulada", str(self))
            return original(self, *a, **k)
        coordenador.gravar_json(REG, {"versao": "ok", "solicitacoes": {}})
        pathlib.Path.read_text = violacao_3x
        try:
            lido = ambiente_isolado.ler_json_substituido(REG)
            estado_helper = estado["n"]
            estado["n"] = 0
            lido_prod = coordenador.ler_registro()
        finally:
            pathlib.Path.read_text = original
        registrar("REG-ATOMIC-03 violação de compartilhamento momentânea (Windows) tratada de forma determinística: repetição limitada "
                  "e leitura correta (helper dos testes e leitura de produção)",
                  lido == lido_prod == {"versao": "ok", "solicitacoes": {}} and estado_helper == 3 and estado["n"] == 3,
                  (estado_helper, estado["n"]))

        contagem = {"n": 0}

        def sempre_bloqueado(self, *a, **k):
            if self == REG:
                contagem["n"] += 1
                raise PermissionError(13, "arquivo bloqueado (simulado)", str(self))
            return original(self, *a, **k)
        pathlib.Path.read_text = sempre_bloqueado
        inicio = time.monotonic()
        try:
            ambiente_isolado.ler_json_substituido(REG, tentativas=5, espera=0.01)
            persistente = "não propagou"
        except PermissionError:
            persistente = "PermissionError"
        finally:
            pathlib.Path.read_text = original
        duracao = time.monotonic() - inicio
        REG.write_text('{"solicitacoes": {"SOL-', encoding="utf-8")            # JSON truncado (defeito) → erro imediato, sem repetir
        contagem_json = {"n": 0}

        def contar(self, *a, **k):
            if self == REG:
                contagem_json["n"] += 1
            return original(self, *a, **k)
        pathlib.Path.read_text = contar
        try:
            ambiente_isolado.ler_json_substituido(REG)
            invalido = "não propagou"
        except ValueError:
            invalido = "ValueError"
        finally:
            pathlib.Path.read_text = original
        registrar("REG-ATOMIC-04 falha persistente de acesso continua aparecendo como erro (5 tentativas, sem laço infinito); JSON "
                  "inválido propaga na 1ª leitura (não é mascarado por repetição)",
                  persistente == "PermissionError" and contagem["n"] == 5 and duracao < 2 and invalido == "ValueError"
                  and contagem_json["n"] == 1, (persistente, contagem["n"], f"{duracao:.2f}s", invalido, contagem_json["n"]))

        coordenador.gravar_json(REG, {"solicitacoes": {}})
        s = TMP / "adicionador.py"
        s.write_text(ADICIONADOR, encoding="utf-8")
        ps = [subprocess.Popen([sys.executable, "-I", str(s), str(COORD.parent), nome, "40"], env=ENV) for nome in ("A", "B", "C")]
        leituras_ok = 0
        while any(x.poll() is None for x in ps):
            d = ambiente_isolado.ler_json_substituido(REG)
            leituras_ok += isinstance(d.get("solicitacoes"), dict)
        codigos = [x.wait(120) for x in ps]
        final = coordenador.ler_registro()["solicitacoes"]
        esperado = {f"SOL-{n}-{i:04d}" for n in "ABC" for i in range(40)}
        registrar("REG-ATOMIC-05 três processos acrescentando 40 entradas cada (trava oficial + substituição atômica), com leituras "
                  "simultâneas: nenhuma entrada perdida (120 de 120)",
                  codigos == [0, 0, 0] and set(final) == esperado, (codigos, len(final), leituras_ok))

        recusou = False
        anterior = os.environ["AGENTES_PRIME_REGISTRO_SOL"]
        os.environ["AGENTES_PRIME_REGISTRO_SOL"] = str(op)
        try:
            ambiente_isolado.registro_isolado()
        except RuntimeError:
            recusou = True
        finally:
            os.environ["AGENTES_PRIME_REGISTRO_SOL"] = anterior
        op_depois = (hashlib.sha256(op.read_bytes()).hexdigest(), op.stat().st_mtime_ns) if op.exists() else None
        registrar("REG-ATOMIC-06 ambiente isolado nunca toca o registro operacional: caminhos de teste diferentes do operacional, "
                  "leitura do operacional recusada pelo helper e registro operacional idêntico (conteúdo e data) antes/depois",
                  coordenador.REGISTRO.resolve() != op.resolve() and REG.resolve() != op.resolve() and recusou and op_antes == op_depois,
                  (str(coordenador.REGISTRO), recusou, op_antes == op_depois))
    finally:
        import shutil
        shutil.rmtree(TMP, ignore_errors=True)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {c}  — {d}")
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
