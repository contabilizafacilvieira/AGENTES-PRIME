"""DEMONSTRAÇÃO ISOLADA do checkpoint após o Financeiro — Escritório Virtual em 127.0.0.1:8766, dados 100% FICTÍCIOS.

Tudo fica numa pasta PRÓPRIA (fora do runtime, de CLIENTES/ e do registro reais):
    ~/Library/Application Support/AgentesPrime-Demonstracao-Checkpoint/
A preparação cria uma empresa fictícia e uma SOL com o relatório financeiro fictício; o extrato fictício chega como documento
complementar (mesma situação da SOL real antes da nova tentativa). O Supervisor então:
    Reprocessar fechamento (parar após o Financeiro) → Iniciar execução → revisa → Continuar para Contabilidade/Bancos.

Uso (a partir da raiz AGENTES-PRIME):
    .venv/bin/python -I TESTES/DEMONSTRACOES/servidor_demo_checkpoint.py            # usa a demonstração existente (ou prepara)
    .venv/bin/python -I TESTES/DEMONSTRACOES/servidor_demo_checkpoint.py --recriar  # apaga SÓ a pasta da demonstração e recria
"""
import os
import shutil
import sys
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BASE = Path.home() / "Library" / "Application Support" / "AgentesPrime-Demonstracao-Checkpoint"
MARCA = BASE / "DEMONSTRACAO-FICTICIA.txt"
PORTA = 8766


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
    MARCA.write_text("Demonstração FICTÍCIA do checkpoint após o Financeiro. Pode ser apagada a qualquer momento.\n", encoding="utf-8")
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
    import cenario_complementar as cc  # noqa: E402
    import ambiente_isolado as ai  # noqa: E402
    srv = servidor.iniciar(PORTA)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if nova:
        cc.preparar_empresa(servidor, servidor.RUNTIME)
        c = cc.Cliente(PORTA)
        sol, _ = c.abrir_sol([("relatorio-financeiro-ficticio.xlsx", cc.relatorio_xlsx())],
                             instrucao="Demonstração fictícia: conferência financeira de outubro/2026.")
        cc.ocioso(servidor, ai.registro_isolado)
        lote = c.complementar(sol, "extrato-ficticio.pdf", cc.extrato_identificado_pdf(), motivo="Extrato fictício recebido depois (demonstração).")
        c.j("POST", f"/api/solicitacoes/{sol}/complementos/{lote}/concluir", {"confirmado": True})
        print(f"Demonstração preparada: {sol} (empresa fictícia {cc.EMPRESA}).")
    print(f"DEMONSTRAÇÃO (dados fictícios): http://127.0.0.1:{PORTA}/  · pasta {BASE}")
    print("Somente este computador acessa. Ctrl+C encerra.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
