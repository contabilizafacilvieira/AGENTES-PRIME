"""DEMONSTRAÇÃO ISOLADA do FECHAMENTO COMPLETO — Escritório Virtual em 127.0.0.1:8767, dados 100% FICTÍCIOS, faixa "DEMONSTRAÇÃO".

Tudo fica numa pasta PRÓPRIA (fora do runtime, de CLIENTES/ e do registro reais):
    ~/Library/Application Support/AgentesPrime-Demonstracao-Fechamento/
Preparação (somente na primeira vez ou com --recriar):
  - duas empresas fictícias (multiempresa): AMOSTRA-COMPLETA-FICTICIA (A) e AMOSTRA-PENDENCIAS-FICTICIA (B);
  - SOL 1 (empresa A): fechamento de 10/2026 com TODOS os documentos (NF entrada/saída, extrato, relatório, impostos, folha,
    balancete, razão, book) RECEBIDOS E CLASSIFICADOS — pronta para o Supervisor clicar em "Preparar fechamento" ao vivo;
  - SOL 2 (empresa A): o MESMO fechamento já executado até a PRÉVIA PRONTA (checkpoint autorizado) — plano B da apresentação;
  - SOL 3 (empresa B): fechamento recebido e classificado (mostra o isolamento entre empresas).
Uso (a partir da raiz AGENTES-PRIME):
    .venv/bin/python -I TESTES/DEMONSTRACOES/servidor_demo_fechamento.py            # usa a demonstração existente (ou prepara)
    .venv/bin/python -I TESTES/DEMONSTRACOES/servidor_demo_fechamento.py --recriar  # apaga SÓ a pasta da demonstração e recria
"""
import os
import shutil
import sys
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BASE = Path.home() / "Library" / "Application Support" / "AgentesPrime-Demonstracao-Fechamento"
MARCA = BASE / "DEMONSTRACAO-FICTICIA.txt"
PORTA = 8767


def preparar_ambiente():
    real = (Path.home() / "Library" / "Application Support" / "AgentesPrime").resolve()
    if BASE.resolve() == real or real in BASE.resolve().parents or str(BASE).startswith(str(RAIZ)):
        raise SystemExit("Pasta da demonstração recusada (não pode ficar dentro do ambiente real nem do projeto).")
    if "--recriar" in sys.argv and BASE.exists():
        if not MARCA.is_file():
            raise SystemExit(f"{BASE} existe sem a marca da demonstração; nada foi apagado.")
        shutil.rmtree(BASE)
    nova = not BASE.exists()
    for sub in ("CLIENTES", "controle", "runtime", "LIBERADOS", "ordem", "localappdata"):
        (BASE / sub).mkdir(parents=True, exist_ok=True)
    MARCA.write_text("Demonstração FICTÍCIA do fechamento completo. Pode ser apagada a qualquer momento.\n", encoding="utf-8")
    os.environ.update({"AGENTES_PRIME_CLIENTES": str(BASE / "CLIENTES"), "AGENTES_PRIME_REGISTRO_SOL": str(BASE / "controle" / "solicitacoes.json"),
                       "AGENTES_PRIME_ORDEM_ATIVA": str(BASE / "ordem" / "ordem-ativa.json"), "AGENTES_PRIME_RUNTIME": str(BASE / "runtime"),
                       "AGENTES_PRIME_LIBERADOS": str(BASE / "LIBERADOS"), "AGENTES_PRIME_CLAUDE": str(BASE / "claude-inexistente.exe"),
                       "LOCALAPPDATA": str(BASE / "localappdata"), "AGENTES_PRIME_PORTA": str(PORTA), "AGENTES_PRIME_AMBIENTE": "DEMONSTRACAO",
                       "AGENTES_PRIME_DEMO_CONCILIACAO": str(BASE / "demonstracao-conciliacao"),
                       "AGENTES_PRIME_DEMO_MANUAL": str(BASE / "demonstracao-associacao-manual"),
                       "AGENTES_PRIME_DEMO_AMBIGUO": str(BASE / "demonstracao-ambiguo-parcial")})
    return nova


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    nova = preparar_ambiente()
    sys.path[:0] = [str(RAIZ / "API-LOCAL"), str(RAIZ / "TESTES" / "API"), str(RAIZ / "TESTES")]
    import servidor  # noqa: E402  (lê as variáveis de ambiente da demonstração)
    import amostra_ficticia  # noqa: E402
    import cenario_complementar as cc  # noqa: E402
    import cenario_fechamento as cf  # noqa: E402
    import ambiente_isolado as ai  # noqa: E402
    srv = servidor.iniciar(PORTA)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if nova:
        amostra_ficticia.preparar(servidor.RUNTIME)
        c = cc.Cliente(PORTA)
        espera = lambda: cc.ocioso(servidor, ai.registro_isolado)  # noqa: E731
        sol1 = cf.abrir_fechamento(c, cf.A, cf.documentos("A"), "Demonstração: fechamento fictício de outubro/2026 (ao vivo).")
        espera()
        sol2 = cf.abrir_fechamento(c, cf.A, cf.documentos("A"), "Demonstração: fechamento fictício de outubro/2026 (já executado).")
        espera()
        cf.preparar_fechamento(c, sol2)
        espera()
        c.j("POST", f"/api/solicitacoes/{sol2}/continuar-apos-financeiro",
            {"justificativa": "Revisei o Financeiro e as consultas às outras áreas (demonstração).", "confirmado": True})
        espera()
        sol3 = cf.abrir_fechamento(c, cf.B, cf.documentos("B"), "Demonstração: fechamento fictício da empresa B (isolamento).")
        espera()
        print(f"Demonstração preparada: {sol1} (A, pronta para 'Preparar fechamento'), {sol2} (A, prévia pronta), {sol3} (B).")
    print(f"DEMONSTRAÇÃO (dados fictícios): http://127.0.0.1:{PORTA}/  · pasta {BASE}")
    print("Somente este computador acessa. Ctrl+C encerra.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
