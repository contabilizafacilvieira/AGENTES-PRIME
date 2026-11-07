"""Executor sem interface do Coordenador Geral (usado somente pela API local).

Roda `claude -p` na raiz do projeto com a ordem de serviço já emitida pela ferramenta do Coordenador. A linha
principal só pode delegar ao agente-documentos (o guarda impõe isso com AGENTES_PRIME_EXECUTOR=1); o subagente segue
as regras homologadas (canal único, extrator, isolamento por ordem ativa). Depois da execução, o executor audita a
transcrição estruturada (stream-json) e extrai o relatório entregue pelo SubagentHandback.

Nada aqui decide estado: a decisão continua com `coordenador.py encerrar`.
"""

import json
import os
import subprocess
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLAUDE_PADRAO = Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "claude.exe"
TEMPO_MAXIMO = 30 * 60
FERRAMENTAS_DO_AGENTE = {"Read", "Glob", "Bash", "SubagentHandback"}
PROMPT_SISTEMA = (
    "Você é o executor automático do Coordenador Geral do AGENTES PRIME. Sua única ação permitida: chamar UMA vez a "
    "ferramenta Agent com subagent_type 'agente-documentos', description 'Ordem de serviço', e prompt exatamente igual "
    "ao texto da ordem de serviço recebida na mensagem do usuário, sem alterar nada. Não use Read, Glob nem Bash. Não "
    "analise documentos e não escolha outro agente. Aguarde o relatório do agente e então responda apenas: ENTREGUE."
)


def caminho_claude() -> Path:
    caminho = Path(os.environ.get("AGENTES_PRIME_CLAUDE") or CLAUDE_PADRAO)
    if not caminho.is_file():
        raise FileNotFoundError(f"Claude Code CLI não encontrado em {caminho}")
    return caminho


def comando(claude: Path) -> list:
    return [str(claude), "-p", "--output-format", "stream-json", "--verbose", "--model", "opus",
            "--tools", "Agent,Read,Glob,Bash", "--system-prompt", PROMPT_SISTEMA, "--setting-sources", "project",
            "--strict-mcp-config", "--no-session-persistence"]


def executar(ordem_de_servico: str, pasta_saida: Path, tempo_maximo: int = TEMPO_MAXIMO) -> dict:
    """Executa a delegação e devolve o resultado auditado (relatorio = None se não houve entrega válida)."""
    pasta_saida.mkdir(parents=True, exist_ok=True)
    transcricao = pasta_saida / "execucao.jsonl"
    ambiente = dict(os.environ, AGENTES_PRIME_EXECUTOR="1")
    inicio = time.monotonic()
    try:
        with open(transcricao, "wb") as saida, open(pasta_saida / "execucao.stderr.txt", "wb") as erros:
            p = subprocess.run(comando(caminho_claude()), cwd=RAIZ, input=ordem_de_servico.encode("utf-8"),
                               stdout=saida, stderr=erros, env=ambiente, timeout=tempo_maximo)
        codigo = p.returncode
    except subprocess.TimeoutExpired:
        codigo = "TEMPO_ESGOTADO"
    except (OSError, FileNotFoundError) as e:
        return {"relatorio": None, "problemas": [f"Falha ao iniciar o executor: {e}"], "ferramentas": {},
                "bloqueios": 0, "duracao_s": 0, "codigo_saida": None}
    resultado = auditar(transcricao, ordem_de_servico)
    resultado["duracao_s"] = round(time.monotonic() - inicio)
    resultado["codigo_saida"] = codigo
    if codigo != 0:
        resultado["problemas"].append(f"Executor terminou com código {codigo}.")
        resultado["relatorio"] = None if codigo == "TEMPO_ESGOTADO" else resultado["relatorio"]
    return resultado


def _texto(conteudo) -> str:
    if isinstance(conteudo, str):
        return conteudo
    return "".join(b.get("text", "") for b in conteudo or [] if isinstance(b, dict))


def extrair_relatorio(texto: str):
    """Relatório entregue pelo SubagentHandback: linhas recuadas depois de 'The report follows:'."""
    marcador = "The report follows:"
    if marcador not in texto:
        return None
    corpo = texto.split(marcador, 1)[1].split("\n", 1)[-1]
    linhas = []
    for linha in corpo.split("\n"):
        if linha.startswith("agentId:") or linha.startswith("<usage>"):
            break
        linhas.append(linha[2:] if linha.startswith("  ") else linha)
    relatorio = "\n".join(linhas).strip()
    return relatorio or None


def auditar(transcricao: Path, ordem_de_servico: str) -> dict:
    principal, subagente, resultados = [], [], {}
    for linha in transcricao.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            o = json.loads(linha)
        except json.JSONDecodeError:
            continue
        m = o.get("message") if isinstance(o.get("message"), dict) else {}
        for b in m.get("content") or []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                (subagente if o.get("parent_tool_use_id") else principal).append(b)
            elif b.get("type") == "tool_result":
                resultados[b.get("tool_use_id")] = (bool(b.get("is_error")), _texto(b.get("content")))

    problemas, ferramentas, bloqueios = [], {}, 0
    for u in subagente:
        ferramentas[u["name"]] = ferramentas.get(u["name"], 0) + 1
        erro, saida = resultados.get(u.get("id"), (False, ""))
        if erro and "BLOQUEADO pelo guarda" in saida:
            bloqueios += 1
        if u["name"] not in FERRAMENTAS_DO_AGENTE:
            problemas.append(f"Agente usou ferramenta não permitida: {u['name']}.")
        if "tool-results" in json.dumps(u.get("input", {})).replace("\\\\", "/"):
            problemas.append("Agente tentou acessar tool-results.")

    relatorio = None
    delegacoes = [u for u in principal if u["name"] in ("Agent", "Task")]
    if len(principal) != 1 or len(delegacoes) != 1:
        problemas.append(f"Executor fez {len(principal)} chamada(s) na linha principal; esperado: 1 delegação.")
    for u in delegacoes[:1]:
        entrada = u.get("input", {})
        if entrada.get("subagent_type") != "agente-documentos":
            problemas.append(f"Delegação para agente não permitido: {entrada.get('subagent_type')}.")
        elif (entrada.get("prompt") or "").strip() != ordem_de_servico.strip():
            problemas.append("A ordem de serviço delegada difere da emitida pelo Coordenador.")
        else:
            erro, saida = resultados.get(u.get("id"), (True, ""))
            relatorio = None if erro else extrair_relatorio(saida)
            if relatorio is None:
                problemas.append("O Agente de Documentos não entregou relatório ao Coordenador.")
    if problemas and relatorio is not None and any("não permitid" in p or "difere" in p for p in problemas):
        relatorio = None
    return {"relatorio": relatorio, "problemas": problemas, "ferramentas": ferramentas, "bloqueios": bloqueios}
