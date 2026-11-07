"""Suspeita 7a da auditoria: SOL ainda aberta fora das 10 mais recentes de GET /api/estado solta personagens para a copa.

Usa a função REAL do servidor (Manipulador.api_estado) com runtime, registro de SOL e ordem ativa TEMPORÁRIOS (variáveis
AGENTES_PRIME_RUNTIME, AGENTES_PRIME_REGISTRO_SOL e AGENTES_PRIME_ORDEM_ATIVA). Não abre porta, não acessa a API principal,
não cria nada em CLIENTES e não executa agentes. Dados 100% fictícios. O resultado é passado à função pura do escritório
(ESCRITORIO-VIRTUAL/js/mapa.js) via node.

Uso (a partir da raiz AGENTES-PRIME):  .venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_estado_recentes.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="estado-recentes-"))
os.environ["AGENTES_PRIME_RUNTIME"] = str(TMP / "runtime")
os.environ["AGENTES_PRIME_REGISTRO_SOL"] = str(TMP / "solicitacoes.json")
os.environ["AGENTES_PRIME_ORDEM_ATIVA"] = str(TMP / "ordem-ativa.json")
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402

resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), detalhe))


def montar(abertas, encerradas):
    """abertas/encerradas: números de SOL. Abertas: AGUARDANDO_SUPERVISOR; encerradas: ENCERRADA. Fluxo só de Documentos."""
    servidor.RUNTIME = servidor.pasta_runtime()
    shutil.rmtree(servidor.RUNTIME / "execucoes", ignore_errors=True)
    registro = {"solicitacoes": {}}
    for n in sorted(abertas + encerradas):
        sol = f"SOL-2026-{n:06d}"
        registro["solicitacoes"][sol] = {"empresa": "EMPRESA-FICTICIA-RECENTES", "competencia": "2026-09", "modo": "SIMULACAO",
                                         "fluxo": "DOCUMENTOS", "estado": "AGUARDANDO_SUPERVISOR" if n in abertas else "ENCERRADA",
                                         "eventos": [{"em": f"2026-10-01T10:{n % 60:02d}:00-03:00", "evento": "criada (fictícia)"}]}
        pasta = servidor.RUNTIME / "execucoes" / sol
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "execucao.json").write_text(json.dumps({"sol": sol, "status": "CONCLUIDA", "inicio": f"2026-10-01T10:{n % 60:02d}:00-03:00",
                                                          "fim": f"2026-10-01T10:{n % 60:02d}:30-03:00"}), encoding="utf-8")
    Path(os.environ["AGENTES_PRIME_REGISTRO_SOL"]).write_text(json.dumps(registro), encoding="utf-8")


def estado():
    saida = {}

    class Falso:
        def json(self, codigo, dados):
            saida.update(codigo=codigo, dados=dados)
    servidor.Manipulador.api_estado(Falso())
    return saida["dados"]


def mapear(recentes):
    js = ("const {operacao}=require(process.argv[1]);let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{"
          "const r=operacao({recentes:JSON.parse(d)});console.log(JSON.stringify({documentos:r.documentos.local,coord:r.coordenador.status,"
          "sol:r.coordenador.solicitacao}));});")
    p = subprocess.run(["node", "-e", js, str(RAIZ / "ESCRITORIO-VIRTUAL" / "js" / "mapa.js")], input=json.dumps(recentes),
                       capture_output=True, text=True, encoding="utf-8")
    return json.loads(p.stdout)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        # 1 SOL aberta (a mais antiga) + 10 encerradas mais novas
        montar([1], list(range(2, 12)))
        d = estado()
        sols = [r["sol"] for r in d["recentes"]]
        m = mapear(d["recentes"])
        registrar("ER-01 GET /api/estado inclui a SOL aberta mesmo fora das 10 mais recentes",
                  "SOL-2026-000001" in sols, f"{len(sols)} recentes: {sols[0]} … {sols[-1]}")
        registrar("ER-02 escritório: Documentos permanece na mesa e o Coordenador aguarda o Supervisor pela SOL aberta antiga",
                  m["documentos"] == "mesa" and m["coord"] == "AGUARDANDO_SUPERVISOR" and m["sol"] == "SOL-2026-000001", json.dumps(m))
        # a lista continua limitada: 15 encerradas → somente as 10 mais recentes (nenhuma aberta)
        montar([], list(range(1, 16)))
        d = estado()
        registrar("ER-03 sem SOL aberta, a lista continua limitada às 10 mais recentes",
                  [r["sol"] for r in d["recentes"]] == [f"SOL-2026-{n:06d}" for n in range(15, 5, -1)], str(len(d["recentes"])))
        # SOL aberta já entre as 10 não é repetida
        montar([9], list(range(1, 9)) + list(range(10, 13)))
        d = estado()
        sols = [r["sol"] for r in d["recentes"]]
        registrar("ER-04 SOL aberta já entre as recentes não é repetida", sols.count("SOL-2026-000009") == 1 and len(sols) == 10, str(sols))
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    falhas = 0
    for caso, ok, det in resultados:
        falhas += not ok
        print(f"{'OK   ' if ok else 'FALHA'} {caso}" + (f" — {det}" if det else ""))
    print(f"\nEstado recentes: {len(resultados) - falhas}/{len(resultados)}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
