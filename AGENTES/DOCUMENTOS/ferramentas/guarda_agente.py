"""Guarda (hook PreToolUse) do Agente de Documentos - AGENTES PRIME.

Declarado em .claude/settings.json (hook do projeto). O Claude Code o executa ANTES de TODA ferramenta,
de qualquer sessão do projeto, e envia o JSON da chamada no stdin. Hooks no cabeçalho do agente não são
executados neste ambiente (diagnóstico F-001 / D-2), por isso o guarda fica no settings.json.

Escopo: as regras só valem quando agent_type == "agente-documentos" (campo preenchido pelo Claude Code
nas chamadas do subagente). Demais chamadas (ex.: Coordenador Geral) são liberadas sem análise.

Vínculo com a empresa: o Coordenador Geral registra a ordem de serviço ativa em
AGENTES/DOCUMENTOS/controle/ordem-ativa.json (empresa, SOL, validade) antes de delegar. O agente não
consegue alterá-la (não tem ferramenta de gravação). Sem ordem válida e dentro do prazo, tudo é bloqueado.

Regras (somente para o agente-documentos):
- Ferramentas permitidas: Read, Glob, Bash e SubagentHandback. Qualquer outra é bloqueada (inclusive Grep, que
  leria o conteúdo bruto dos documentos por fora do extrator, e Agent/Task, que chamariam outro agente).
- SubagentHandback (mecanismo do Claude Code para devolver o relatório ao Coordenador): somente o campo 'message'
  com texto; não dá acesso a arquivos nem altera a ordem ativa. Também exige ordem de serviço válida.
- Read/Glob: somente dentro de CLIENTES/<EMPRESA DA ORDEM ATIVA>/ ou AGENTES/DOCUMENTOS/.
  Glob exige o parâmetro 'path'.
- Canal único de conteúdo (T-004.5): Read de documentos (lista fechada EXTENSOES_SO_PELO_EXTRATOR, ou
  arquivo cujo conteúdo é de documento/imagem/pacote mesmo com outra extensão, ou fluxo alternativo NTFS)
  é bloqueado; o conteúdo de documentos entra somente pelo extrator. Arquivos de controle (.md) seguem legíveis.
- Bash: somente a ferramenta extrair_documentos.py na interface paginada (--resumo ou --arquivo <id>, com
  --parte opcional), na ordem exata, sem operadores de shell, com --empresa igual à empresa da ordem ativa.
  A extração integral (--completo) e qualquer argumento extra são bloqueados.

Executor sem interface do Coordenador (processo `claude -p` iniciado pela API local, com a variável de ambiente
AGENTES_PRIME_EXECUTOR=1): na linha principal (sem agent_type) só é permitido delegar ao agente-documentos pela
ferramenta Agent/Task. Qualquer outra ferramenta ou subagente é bloqueado. As chamadas do próprio agente-documentos
seguem as regras acima.

Falha fechada: qualquer erro de leitura ou de validação bloqueia a chamada (exit 2 + motivo no stderr).
"""

import datetime as dt
import json
import os
import re
import shlex
import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parents[3]
PASTA_CLIENTES = (RAIZ_PROJETO / "CLIENTES").resolve()
PASTA_AGENTE = (RAIZ_PROJETO / "AGENTES" / "DOCUMENTOS").resolve()
ORDEM_ATIVA = PASTA_AGENTE / "controle" / "ordem-ativa.json"

AGENTE_PROTEGIDO = "agente-documentos"
FERRAMENTAS_PERMITIDAS = {"Read", "Glob", "Bash", "SubagentHandback"}

# Lista FECHADA: formatos que o extrator processa (ou classifica como fora do escopo), imagens e pacotes.
# O agente nunca lê esses arquivos diretamente.
EXTENSOES_SO_PELO_EXTRATOR = frozenset({
    ".pdf", ".xml", ".xlsx", ".xlsm", ".xls",                       # documentos estruturados
    ".txt", ".csv", ".json", ".ofx",                                # texto processado pelo extrator
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic",  # imagens (sem leitura visual)
    ".zip", ".rar", ".7z",                                          # pacotes
    ".doc", ".docx", ".odt", ".ods", ".rtf",                        # outros documentos de escritório
})
# Assinaturas de conteúdo de documento/imagem/pacote (pegam extensão disfarçada, ex.: PDF salvo como .md).
ASSINATURAS_DOCUMENTO = (b"%PDF-", b"\x89PNG", b"\xff\xd8\xff", b"PK\x03\x04", b"\xd0\xcf\x11\xe0",
                         b"GIF8", b"II*\x00", b"MM\x00*", b"RIFF", b"Rar!", b"7z\xbc\xaf", b"{\\rtf", b"<?xml")
COMANDO_PERMITIDO = [".venv/Scripts/python.exe", "-I", "AGENTES/DOCUMENTOS/ferramentas/extrair_documentos.py"]
CARACTERES_PROIBIDOS = set(";&|<>`$(){}\n\r")


def bloquear(motivo: str) -> None:
    print(f"BLOQUEADO pelo guarda do Agente de Documentos: {motivo}", file=sys.stderr)
    sys.exit(2)


def dentro_de(caminho: Path, base: Path) -> bool:
    try:
        caminho.relative_to(base)
        return True
    except ValueError:
        return False


def empresa_da_ordem() -> str:
    if not ORDEM_ATIVA.is_file():
        bloquear("nenhuma ordem de serviço ativa registrada pelo Coordenador Geral.")
    ordem = json.loads(ORDEM_ATIVA.read_text(encoding="utf-8"))
    empresa = ordem.get("empresa", "")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", empresa) or not (PASTA_CLIENTES / empresa / "CADASTRO.md").is_file():
        bloquear(f"ordem de serviço ativa com empresa inválida: {empresa!r}.")
    if dt.datetime.now() > dt.datetime.fromisoformat(ordem["valida_ate"]):
        bloquear(f"ordem de serviço ativa vencida ({ordem.get('sol')}, válida até {ordem['valida_ate']}).")
    return empresa


def caminho_autorizado(bruto: str, empresa: str) -> bool:
    # Caminho no formato do Git Bash (/c/Users/...) -> C:/Users/...
    unidade = re.match(r"^/([A-Za-z])/(.*)$", bruto)
    if unidade:
        bruto = f"{unidade.group(1)}:/{unidade.group(2)}"
    caminho = Path(bruto)
    if not caminho.is_absolute():
        caminho = RAIZ_PROJETO / caminho
    caminho = caminho.resolve()
    return dentro_de(caminho, PASTA_AGENTE) or dentro_de(caminho, (PASTA_CLIENTES / empresa).resolve())


def motivo_documento(bruto: str):
    """Retorna o motivo se o Read for de um documento (que só pode entrar pelo extrator); senão None."""
    if ":" in re.sub(r"^(/[A-Za-z]/|[A-Za-z]:)", "", bruto):
        return "fluxo alternativo de arquivo (':' no nome) não é permitido"
    caminho = Path(bruto) if Path(bruto).is_absolute() else RAIZ_PROJETO / bruto
    caminho = caminho.resolve()
    nome = caminho.name.rstrip(". ").lower()
    extensao = Path(nome).suffix
    if extensao in EXTENSOES_SO_PELO_EXTRATOR:
        return f"arquivo {extensao} só pode ser lido pelo extrator (extrair_documentos.py)"
    if caminho.is_file():
        with open(caminho, "rb") as f:
            inicio = f.read(16).lstrip(b"\xef\xbb\xbf \t\r\n")
        if inicio.startswith(ASSINATURAS_DOCUMENTO):
            return "o conteúdo do arquivo é de documento/imagem/pacote; só pode ser lido pelo extrator"
    return None


FORMAS_EXTRATOR = (
    "--empresa <ID> --pasta \"<pasta>\" --resumo [--parte N]",
    "--empresa <ID> --arquivo <id de 32 hex do resumo> [--parte N]",
)


def validar_bash(comando: str, empresa: str) -> None:
    """Somente a interface paginada do extrator (T-004.6); a extração integral (--completo) é proibida ao agente."""
    if any(c in CARACTERES_PROIBIDOS for c in comando):
        bloquear("comando com operadores de shell não permitidos.")
    partes = shlex.split(comando)
    if partes[:3] != COMANDO_PERMITIDO:
        bloquear("o único comando permitido é: " + " ".join(COMANDO_PERMITIDO) + " " + " | ".join(FORMAS_EXTRATOR))
    resto = partes[3:]
    if len(resto) >= 2 and resto[0] == "--empresa" and resto[1] != empresa:
        bloquear(f"--empresa {resto[1]} diferente da empresa da ordem de serviço ativa.")
    if len(resto) in (7, 6) and resto[-2] == "--parte":     # 7 = resumo + parte; 6 = arquivo + parte
        if not re.fullmatch(r"[1-9][0-9]{0,3}", resto[-1]):
            bloquear("--parte deve ser um inteiro entre 1 e 9999.")
        resto = resto[:-2]
    if len(resto) == 5 and resto[0] == "--empresa" and resto[2] == "--pasta" and resto[4] == "--resumo":
        pasta = resto[3]
        if Path(pasta).is_absolute() or re.match(r"^[A-Za-z]:|^[\\/]", pasta) or ".." in re.split(r"[\\/]", pasta) or ":" in pasta:
            bloquear("--pasta deve ser relativa à empresa, sem '..', unidade ou ':'.")
        return
    if len(resto) == 4 and resto[0] == "--empresa" and resto[2] == "--arquivo":
        if not re.fullmatch(r"[0-9a-f]{32}", resto[3]):
            bloquear("--arquivo aceita somente o id de 32 caracteres hexadecimais devolvido pelo --resumo.")
        return
    bloquear("parâmetros fora da interface permitida: " + " | ".join(FORMAS_EXTRATOR))


def main() -> None:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        dados = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if os.environ.get("AGENTES_PRIME_EXECUTOR") == "1" and not dados.get("agent_type"):
            entrada = dados.get("tool_input", {}) or {}
            if dados.get("tool_name") in ("Agent", "Task") and entrada.get("subagent_type") == AGENTE_PROTEGIDO:
                sys.exit(0)
            bloquear(f"executor do Coordenador só pode delegar ao {AGENTE_PROTEGIDO} "
                     f"(ferramenta '{dados.get('tool_name')}' recusada).")
        if dados.get("agent_type") != AGENTE_PROTEGIDO:
            sys.exit(0)
        ferramenta = dados.get("tool_name", "")
        entrada = dados.get("tool_input", {}) or {}

        if ferramenta not in FERRAMENTAS_PERMITIDAS:
            bloquear(f"ferramenta '{ferramenta}' não permitida (o agente é somente leitura).")
        empresa = empresa_da_ordem()

        if ferramenta == "Read":
            if not caminho_autorizado(entrada.get("file_path", ""), empresa):
                bloquear(f"leitura fora das pastas autorizadas para {empresa}: {entrada.get('file_path')}")
            motivo = motivo_documento(entrada.get("file_path", ""))
            if motivo:
                bloquear(f"{motivo}. Use o extrator; não leia documentos diretamente.")
        elif ferramenta == "Glob":
            caminho = entrada.get("path")
            if not caminho:
                bloquear(f"{ferramenta} exige o parâmetro 'path' apontando para a pasta da empresa.")
            if not caminho_autorizado(caminho, empresa):
                bloquear(f"busca fora das pastas autorizadas para {empresa}: {caminho}")
            for chave in ("pattern", "glob"):
                padrao = entrada.get(chave) or ""
                if ferramenta == "Glob" or chave == "glob":
                    if ".." in padrao or Path(padrao).is_absolute() or re.match(r"^[A-Za-z]:", padrao):
                        bloquear(f"padrão de busca não permitido: {padrao}")
        elif ferramenta == "Bash":
            validar_bash(entrada.get("command", ""), empresa)
        elif ferramenta == "SubagentHandback":
            if set(entrada) != {"message"} or not isinstance(entrada["message"], str):
                bloquear("SubagentHandback aceita somente o campo 'message' (texto do relatório ao Coordenador).")
    except SystemExit:
        raise
    except Exception as e:
        bloquear(f"erro ao validar a chamada ({type(e).__name__}: {e}).")
    sys.exit(0)


if __name__ == "__main__":
    main()
