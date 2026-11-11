"""GATE DE RELEASE — executa TODAS as baterias ATIVAS do AGENTES PRIME e confere que o estado operacional não foi tocado.

Uso (a partir da raiz AGENTES-PRIME; pode rodar com a API operacional no ar — os testes usam ambientes isolados):
    .venv\\Scripts\\python.exe -I TESTES\\executar_gate.py              # tudo
    .venv\\Scripts\\python.exe -I TESTES\\executar_gate.py FISCAL LOCAL # só as áreas indicadas

Saída: uma linha por bateria (PASSOU/FALHOU, tempo, último resumo) e o veredito final. Código 0 só se TODAS passarem e o estado
operacional (CLIENTES/, registro do Coordenador, ordem ativa e LIBERADOS/) estiver idêntico antes e depois. Saídas completas
de cada bateria ficam numa pasta temporária (indicada no final), fora do repositório.
Lista oficial e justificativas (inclusive das baterias LEGADAS, fora do gate): TESTES/GATE-RELEASE.md.
"""
import hashlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PY = str(RAIZ / ".venv" / "Scripts" / "python.exe") if (RAIZ / ".venv" / "Scripts" / "python.exe").exists() else sys.executable

# (área, arquivo) — ordem: unitários rápidos primeiro, navegador e percursos depois
GATE = [
    ("GOVERNANÇA", "TESTES/GOVERNANCA/testar_governanca_regras.py"),
    ("REGISTRO", "TESTES/REGISTRO/testar_concorrencia_registro.py"),
    ("EXTRATOR", "TESTES/T004/testar_extrator.py"),
    ("EXTRATOR (interface)", "TESTES/T004/testar_interface.py"),
    ("GUARDA", "TESTES/T004/testar_guarda.py"),
    ("COORDENADOR", "TESTES/COORD/testar_coordenador.py"),
    ("API LOCAL / SEGURANÇA", "TESTES/API/testar_api.py"),
    ("REPROCESSAMENTO", "TESTES/API/testar_ciclo_reprocessamento.py"),
    ("DOCUMENTOS", "TESTES/LOCAL/testar_pdf_local.py"),
    ("DOCUMENTOS", "TESTES/LOCAL/testar_triagem_documentos.py"),
    ("DOCUMENTOS", "TESTES/LOCAL/testar_salvaguardas_documentos.py"),
    ("DOCUMENTOS", "TESTES/LOCAL/testar_pacotes_areas.py"),
    ("DOCUMENTOS", "TESTES/LOCAL/testar_encaminhamento_automatico.py"),
    ("DOCUMENTOS", "TESTES/LOCAL/testar_classificacao_extrato.py"),
    ("CADASTRO", "TESTES/LOCAL/testar_local.py"),
    ("CADASTRO", "TESTES/LOCAL/testar_plano_dominio.py"),
    ("CADASTRO", "TESTES/LOCAL/testar_metodo_empresa.py"),
    ("CADASTRO", "TESTES/LOCAL/testar_lixeira.py"),
    ("CADASTRO", "TESTES/LOCAL/testar_revisao_piloto.py"),
    ("FINANCEIRO", "TESTES/LOCAL/testar_extrato_santander.py"),
    ("FINANCEIRO", "TESTES/LOCAL/testar_confronto_suportes.py"),
    ("FINANCEIRO", "TESTES/LOCAL/testar_adiantamentos.py"),
    ("FINANCEIRO", "TESTES/LOCAL/testar_financeiro_percurso.py"),
    ("FINANCEIRO", "TESTES/FINANCEIRO/testar_correcoes_fluxo.py"),
    ("FINANCEIRO", "TESTES/FINANCEIRO/testar_financeiro.py"),
    ("FINANCEIRO", "TESTES/FINANCEIRO/testar_normalizador_financeiro.py"),
    ("FINANCEIRO", "TESTES/FINANCEIRO/testar_integracao_normalizador.py"),
    ("FINANCEIRO", "TESTES/FINANCEIRO/testar_normalizador_bancario.py"),
    ("FINANCEIRO", "TESTES/FINANCEIRO/testar_integracao_bancaria.py"),
    ("FISCAL", "TESTES/FISCAL/testar_fiscal.py"),
    ("FISCAL", "TESTES/FISCAL/testar_salvaguardas_fiscais.py"),
    ("FISCAL", "TESTES/FISCAL/testar_coordenador_fiscal.py"),
    ("FISCAL", "TESTES/FISCAL/testar_fluxo_fiscal.py"),
    ("DP", "TESTES/DP/testar_dp.py"),
    ("CONCILIAÇÃO", "TESTES/CONCILIACAO/testar_conciliacao.py"),
    ("EXPORTAÇÃO", "TESTES/EXPORTACAO/testar_exportacao_dominio.py"),
    ("BASE INICIAL", "TESTES/BASE-INICIAL/testar_base_inicial.py"),
    ("PLANO / HIERARQUIA", "TESTES/BASE-INICIAL/testar_plano_hierarquia.py"),
    ("BASE INICIAL", "TESTES/BASE-INICIAL/testar_percurso_base_inicial.py"),
    ("SAÍDAS", "TESTES/AMOSTRA-COMPLETA/testar_saidas_exclusao.py"),
    ("PERCURSO COMPLETO", "TESTES/AMOSTRA-COMPLETA/testar_percurso_completo.py"),
    ("PERCURSO LOCAL", "TESTES/LOCAL/testar_fluxo_local.py"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_mapa.js"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_percurso_mapa.js"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_aprovacao_mapa.js"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_auditoria_mapa.js"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_ciclo_solicitacao.js"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_estado_recentes.py"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_escritorio.py"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_operacao_escritorio.py"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_acompanhamento_navegador.py"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_auditoria_navegador.py"),
    ("ESCRITÓRIO", "TESTES/ESCRITORIO/testar_percurso_navegador.py"),
    ("ESCRITÓRIO / API REAL", "TESTES/ESCRITORIO/testar_interface_api_real.py"),
    ("EMPRESAS / BASE INICIAL (tela)", "TESTES/ESCRITORIO/testar_interface_base_inicial.py"),
    ("EMPRESAS (simplificação e exclusão)", "TESTES/ESCRITORIO/testar_simplificacao_empresas.py"),
]


def foto_operacional() -> str:
    """Impressão digital do estado operacional: arquivos de CLIENTES/, registro e ordem ativa do Coordenador, LIBERADOS/."""
    h = hashlib.sha256()
    alvos = [RAIZ / "CLIENTES", RAIZ / "LIBERADOS", RAIZ / "COORDENADOR-GERAL" / "controle", RAIZ / "AGENTES" / "DOCUMENTOS" / "controle"]
    for base in alvos:
        if not base.exists():
            h.update(f"{base}:AUSENTE".encode())
            continue
        for p in sorted(x for x in base.rglob("*") if x.is_file()):
            if p.name.endswith(".trava"):
                continue
            h.update(str(p.relative_to(RAIZ)).encode())
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    filtro = {a.upper() for a in sys.argv[1:]}
    alvo = [(a, t) for a, t in GATE if not filtro or any(f in a.upper() for f in filtro)]
    saida = Path(tempfile.mkdtemp(prefix="prime-gate-"))
    antes = foto_operacional()
    linhas, falhas = [], 0
    for area, teste in alvo:
        cmd = ["node", teste] if teste.endswith(".js") else [PY, "-I", teste, str(saida / ("capturas-" + Path(teste).stem))]
        if teste.endswith(".py") and "ESCRITORIO" not in teste:
            cmd = cmd[:3]                              # só as baterias de tela aceitam pasta de capturas
        ini = time.time()
        try:
            p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
            codigo, texto = p.returncode, (p.stdout or "") + "\n--- stderr ---\n" + (p.stderr or "")
        except subprocess.TimeoutExpired as e:
            codigo, texto = "TEMPO_ESGOTADO", str(e.stdout or "")
        (saida / (Path(teste).stem + ".txt")).write_text(texto, encoding="utf-8")
        ok = codigo == 0
        falhas += not ok
        resumo = next((l.strip() for l in reversed(texto.splitlines()) if l.strip().startswith(("TOTAL", "OK", "Ran ", "FAILED"))), "")
        linha = f"{'PASSOU' if ok else 'FALHOU'}  {round(time.time() - ini):>4}s  {area:<34} {teste}  {resumo[:90]}"
        linhas.append(linha)
        print(linha, flush=True)
    depois = foto_operacional()
    intocado = antes == depois
    print(f"\nEstado operacional (CLIENTES/, registro, ordem ativa, LIBERADOS/) intocado: {'SIM' if intocado else 'NÃO — VERIFICAR'}")
    print(f"BATERIAS: {len(alvo)} · PASSARAM: {len(alvo) - falhas} · FALHARAM: {falhas} · saídas completas em {saida}")
    veredito = falhas == 0 and intocado
    print("GATE DE RELEASE: " + ("APROVADO" if veredito else "REPROVADO"))
    return 0 if veredito else 1


if __name__ == "__main__":
    sys.exit(main())
