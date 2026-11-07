"""Ferramenta do Coordenador Geral - abertura e encerramento da etapa documental de uma solicitação (SOL).

Uso exclusivo do Coordenador Geral (o guarda bloqueia qualquer Bash do Agente de Documentos que não seja o extrator).
Comandos (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I COORDENADOR-GERAL/ferramentas/coordenador.py abrir --pedido "<texto do Supervisor>" [--pasta "<pasta>"]
    .venv/Scripts/python.exe -I COORDENADOR-GERAL/ferramentas/coordenador.py encerrar --sol SOL-AAAA-NNNNNN --relatorio <arquivo.md>
    .venv/Scripts/python.exe -I COORDENADOR-GERAL/ferramentas/coordenador.py cancelar --sol SOL-AAAA-NNNNNN --motivo "<texto>"
    .venv/Scripts/python.exe -I COORDENADOR-GERAL/ferramentas/coordenador.py consultar --sol SOL-AAAA-NNNNNN

abrir:
- Identifica empresa (identificador, razão social ou CNPJ cadastrados) e competência no texto do Supervisor.
  Nada é deduzido: empresa/competência ausente ou ambígua = ESCLARECIMENTO_NECESSARIO, nada é criado.
- Empresa precisa existir em CLIENTES/ com CADASTRO.md, não estar SUSPENSA e ser FICTÍCIA enquanto o Agente de
  Documentos não estiver liberado para produção.
- Pasta padrão: TREINAMENTO/AAAA-MM/DOCUMENTOS (ou --pasta relativa à empresa). Pasta sem arquivos = nada é criado.
- Gera SOL única (SOL-AAAA-NNNNNN, sequencial no registro, nunca reutilizada), vincula a SOL a UMA empresa e grava a
  ordem ativa (AGENTES/DOCUMENTOS/controle/ordem-ativa.json, validade 2h) usada pelo guarda.
encerrar:
- Remove a ordem ativa da SOL e decide a transição:
  DOCUMENTOS_CONCLUIDO -> PRONTO_PARA_FINANCEIRO     (nenhum motivo bloqueante)
  DOCUMENTOS_PENDENTE  -> AGUARDANDO_SUPERVISOR      (qualquer motivo bloqueante, listado na saída)
- A decisão é do Coordenador: confere o relatório (cabeçalho, seções 1/5/6/7) e refaz o inventário pelo --resumo do
  extrator. Sugestões do agente sobre a próxima etapa são ignoradas.
- Fluxo FINANCEIRO_BANCOS (abrir --fluxo; empresa fictícia ou piloto real autorizado, sempre SIMULAÇÃO): sem problema estrutural, a SOL segue
  para FINANCEIRO_EM_ANDAMENTO (pendências de documento seguem junto). Depois: registrar-financeiro → BANCOS_EM_ANDAMENTO
  → registrar-bancos → AGUARDANDO_SUPERVISOR. Decisões por movimento, proposta e aprovação de regra: ver comandos abaixo.

Registro: COORDENADOR-GERAL/controle/solicitacoes.json (não versionado). Saída: JSON no stdout.
Códigos de saída: 0 = executado | 3 = recusado (nada foi criado; o motivo está na saída) | 2 = parâmetros inválidos.
"""

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CLIENTES = Path(os.environ.get("AGENTES_PRIME_CLIENTES") or RAIZ / "CLIENTES")  # testes isolados podem apontar outra pasta
# Testes usam AGENTES_PRIME_ORDEM_ATIVA (arquivo temporário) para não disputar a ordem ativa real.
ORDEM_ATIVA = Path(os.environ.get("AGENTES_PRIME_ORDEM_ATIVA") or RAIZ / "AGENTES" / "DOCUMENTOS" / "controle" / "ordem-ativa.json")
EXTRATOR = RAIZ / "AGENTES" / "DOCUMENTOS" / "ferramentas" / "extrair_documentos.py"
REGISTRO = Path(os.environ.get("AGENTES_PRIME_REGISTRO_SOL") or RAIZ / "COORDENADOR-GERAL" / "controle" / "solicitacoes.json")
VALIDADE_ORDEM = dt.timedelta(hours=2)

MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
         "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
ABREVIADOS = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10,
              "NOV": 11, "DEZ": 12}
# Marcações do extrator que NÃO impedem a transição (apenas pontos de atenção). Qualquer outra bloqueia (falha fechada).
MARCACOES_NAO_BLOQUEANTES = {"NOTA_CANCELADA", "CELULAS_MESCLADAS"}


def agora() -> dt.datetime:
    return dt.datetime.now().astimezone().replace(microsecond=0)


def normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()


def saida(dados: dict, codigo: int = 0) -> int:
    print(json.dumps(dados, ensure_ascii=False, indent=2))
    return codigo


def recusar(resultado: str, motivo: str, **extra) -> int:
    return saida(dict({"resultado": resultado, "motivo": motivo, "criado": "nada"}, **extra), 3)


def com_nova_tentativa(funcao, tentativas: int = 40):
    """No Windows, ler um arquivo no instante em que outro processo o substitui (os.replace) gera PermissionError
    momentâneo. Repete por até ~2 s; o conteúdo lido/gravado é sempre o arquivo inteiro (nunca parcial)."""
    for i in range(tentativas):
        try:
            return funcao()
        except PermissionError:
            if i == tentativas - 1:
                raise
            time.sleep(0.05)


class TravaRegistroIndisponivel(RuntimeError):
    """A trava do registro não foi obtida dentro do prazo: a operação NÃO foi executada (nada é repetido automaticamente)."""


@contextlib.contextmanager
def trava_registro(timeout: float = None):
    """Trava EXCLUSIVA entre processos para toda leitura-modificação-gravação do registro de solicitações.
    Usa trava de arquivo do sistema operacional (msvcrt no Windows, fcntl nos demais): liberada pelo sistema se o processo
    terminar, sem trava "esquecida". Prazo: AGENTES_PRIME_TRAVA_REGISTRO_TIMEOUT (s, padrão 60); esgotado → exceção explícita."""
    prazo = float(timeout if timeout is not None else os.environ.get("AGENTES_PRIME_TRAVA_REGISTRO_TIMEOUT", "60"))
    arquivo = REGISTRO.with_name(REGISTRO.name + ".trava")
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(arquivo), os.O_RDWR | os.O_CREAT, 0o600)
    obtida = False
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
        limite = time.monotonic() + prazo
        while True:
            try:
                os.lseek(fd, 0, 0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                obtida = True
                break
            except OSError:
                if time.monotonic() >= limite:
                    raise TravaRegistroIndisponivel(f"Registro de solicitações ocupado por outra operação há mais de {prazo:g} s; "
                                                    "nada foi alterado. Tente de novo quando a outra operação terminar.")
                time.sleep(0.05)
        yield
    finally:
        if obtida:
            os.lseek(fd, 0, 0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def ler_registro() -> dict:
    if not REGISTRO.exists():
        return {"solicitacoes": {}}
    return com_nova_tentativa(lambda: json.loads(REGISTRO.read_text(encoding="utf-8")))


def gravar_json(caminho: Path, dados: dict) -> None:
    """Gravação atômica: arquivo temporário EXCLUSIVO deste processo, gravado por inteiro e com fsync, e substituição única
    (os.replace). Leitores nunca veem gravação parcial."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(f"{caminho.name}.{os.getpid()}.tmp")
    with open(temporario, "w", encoding="utf-8") as f:
        f.write(json.dumps(dados, ensure_ascii=False, indent=2))
        f.flush()
        os.fsync(f.fileno())
    com_nova_tentativa(lambda: os.replace(temporario, caminho))


def ler_ordem():
    if not ORDEM_ATIVA.exists():
        return None
    try:
        return json.loads(ORDEM_ATIVA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sol": None, "empresa": None, "corrompida": True}


# ---------------------------------------------------------------- empresa e competência

def empresas_cadastradas() -> dict:
    empresas = {}
    for pasta in sorted(CLIENTES.iterdir()):
        cadastro = pasta / "CADASTRO.md"
        if pasta.is_dir() and not pasta.is_symlink() and re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", pasta.name) and cadastro.is_file():
            texto = cadastro.read_text(encoding="utf-8")
            razao = re.search(r"Raz[ãa]o social:\s*(.+)", texto)
            empresas[pasta.name] = {
                "texto": texto,
                "cadastro_local": (pasta / 'empresa-local.json').is_file(),
                "razao_social": razao.group(1).strip() if razao else "",
                "cnpjs": sorted({re.sub(r"\D", "", c) for c in re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)}),
                "cnpjs_formatados": sorted(set(re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto))),
            }
    return empresas


def identificar_empresa(pedido: str, empresas: dict):
    t = normalizar(pedido)
    digitos = set(re.findall(r"(?<!\d)\d{14}(?!\d)", re.sub(r"[./-]", "", pedido)))
    achadas = set()
    for ident, e in empresas.items():
        if re.search(rf"(?<![A-Z0-9-]){re.escape(ident)}(?![A-Z0-9-])", t):
            achadas.add(ident)
        if e["razao_social"] and normalizar(e["razao_social"]) in t:
            achadas.add(ident)
        if digitos & set(e["cnpjs"]):
            achadas.add(ident)
    if len(achadas) == 1:
        return achadas.pop(), None
    if len(achadas) > 1:
        return None, ("EMPRESA_AMBIGUA", f"O pedido cita mais de uma empresa ({', '.join(sorted(achadas))}). Uma SOL atende uma única empresa: qual delas?")
    citadas = sorted(set(re.findall(r"(?<![A-Z0-9-])EMPRESA-[A-Z0-9-]+", t)) | set(re.findall(r"(?<![A-Z0-9-])_[A-Z0-9-]+", t)))
    if citadas:
        return None, ("EMPRESA_NAO_ENCONTRADA", f"Empresa {', '.join(citadas)} não tem cadastro válido em CLIENTES/. Nenhum processamento foi criado.")
    return None, ("EMPRESA_NAO_IDENTIFICADA", "O pedido não identifica a empresa (identificador, razão social ou CNPJ). Qual empresa?")


def identificar_competencia(pedido: str):
    t = normalizar(pedido)
    achadas, meses_sem_ano = set(), set()
    for m, a in re.findall(r"(?<![\d/])(\d{1,2})\s*/\s*(20\d{2})(?![\d/])", t):
        if 1 <= int(m) <= 12:
            achadas.add((int(a), int(m)))
    for a, m in re.findall(r"(?<![\d/.-])(20\d{2})-(\d{2})(?![\d-])", t):
        if 1 <= int(m) <= 12:
            achadas.add((int(a), int(m)))
    for nome, a in re.findall(r"\b(" + "|".join(MESES) + r")\b(?:\s*(?:/|-|DE)?\s*(20\d{2}))?", t):
        (achadas.add((int(a), MESES[nome])) if a else meses_sem_ano.add(MESES[nome]))
    for nome, a in re.findall(r"\b(" + "|".join(ABREVIADOS) + r")\s*/\s*(20\d{2})\b", t):
        achadas.add((int(a), ABREVIADOS[nome]))
    meses_sem_ano -= {m for _, m in achadas}
    if len(achadas) == 1 and not meses_sem_ano:
        a, m = achadas.pop()
        return f"{a:04d}-{m:02d}", None
    if not achadas and not meses_sem_ano:
        return None, ("COMPETENCIA_AUSENTE", "O pedido não informa a competência (ex.: 09/2026). Qual competência devo processar?")
    return None, ("COMPETENCIA_AMBIGUA", "A competência está ambígua (mais de um período ou mês sem ano). Qual competência devo processar?")


# Autorização EXATA do Supervisor no CADASTRO.md para o piloto real supervisionado (autorização de 31/10/2026).
# Nome digitado, pedido, pasta, documentos ou CNPJ nunca autorizam: só esta linha no cadastro da própria empresa.
RE_PILOTO = re.compile(r"^- Agente de Documentos: PILOTO SUPERVISIONADO AUTORIZADO(?: \([^\n]*\))?[ \t]*$", re.M)
PILOTO = "PILOTO_REAL_SUPERVISIONADO"
CONFERENCIA_PILOTO = "CONFERENCIA_MANUAL_PILOTO"


def eh_piloto(empresa: dict) -> bool:
    return (empresa.get('cadastro_local') or "EMPRESA FICTICIA" not in normalizar(empresa["texto"])) and bool(RE_PILOTO.search(empresa["texto"]))


def piloto_financeiro(empresa: dict) -> bool:
    return bool(re.search(r'^- Financeiro/Bancos local: PILOTO SIMULACAO AUTORIZADO[ \t]*$', empresa['texto'], re.M))


def financeiro_permitido(empresa: dict) -> bool:
    if empresa.get('cadastro_local'):
        return eh_piloto(empresa) and piloto_financeiro(empresa)
    return 'EMPRESA FICTICIA' in normalizar(empresa['texto']) or (eh_piloto(empresa) and piloto_financeiro(empresa))


def autorizacao(empresa: dict):
    t = normalizar(empresa["texto"])
    status = re.search(r"STATUS:\s*([A-Z ]+?)\s*(?:\(|$)", t, re.M)
    status = status.group(1).strip() if status else "NAO CONSTA"
    if status == "SUSPENSO":
        return None, "Empresa com Status SUSPENSO no CADASTRO.md."
    if status == "EXCLUIDO":
        return None, "Cadastro da empresa excluído: não aceita novas solicitações (históricos preservados)."
    if (empresa.get('cadastro_local') or "EMPRESA FICTICIA" not in t) and not eh_piloto(empresa):
        return None, ("O Agente de Documentos está homologado somente em ambiente fictício; empresa real exige, no "
                      "CADASTRO.md, a autorização exata \"- Agente de Documentos: PILOTO SUPERVISIONADO AUTORIZADO\".")
    real = status == "VALIDADO" and "CADASTRO VALIDADO: SIM" in t and "TREINAMENTO VALIDADO: SIM" in t
    return ("SIMULAÇÃO" if eh_piloto(empresa) else "REAL" if real else "SIMULAÇÃO"), None


def validar_pasta(empresa: str, pasta: str):
    if not pasta or Path(pasta).is_absolute() or re.match(r"^[A-Za-z]:|^[\\/]", pasta) or ".." in re.split(r"[\\/]", pasta) or ":" in pasta:
        return None, "Pasta deve ser relativa à empresa, sem '..', unidade ou ':'."
    base = (CLIENTES / empresa).resolve()
    alvo = (base / pasta).resolve()
    try:
        alvo.relative_to(base)
    except ValueError:
        return None, "Pasta fora da empresa."
    if not alvo.is_dir():
        return None, f"Pasta {pasta} não existe em CLIENTES/{empresa}/."
    if not any(p.is_file() for p in alvo.rglob("*")):
        return None, f"Pasta {pasta} não contém documentos."
    return alvo.relative_to(base).as_posix(), None


def proxima_sol(registro: dict, ano: int) -> str:
    """Próximo número: maior entre as SOLs ativas, os registros mínimos (excluídas/arquivadas) e a sequência registrada.
    Nenhum número é reutilizado depois de exclusão definitiva ou arquivamento."""
    usados = [int(s.rsplit("-", 1)[1]) for s in list(registro["solicitacoes"]) + list(registro.get("registros_minimos", {}))
              if s.startswith(f"SOL-{ano}-")]
    usados.append(int((registro.get("sequencia_sol") or {}).get(str(ano), 0)))
    return f"SOL-{ano}-{max(usados) + 1:06d}"


# ---------------------------------------------------------------- comandos

FLUXOS = ("DOCUMENTOS", "FINANCEIRO_BANCOS")


def abrir(pedido: str, pasta_informada, fluxo: str = "DOCUMENTOS") -> int:
    empresas = empresas_cadastradas()
    empresa, problema = identificar_empresa(pedido, empresas)
    if problema:
        return recusar(*problema) if problema[0] == "EMPRESA_NAO_ENCONTRADA" else recusar("ESCLARECIMENTO_NECESSARIO", problema[1], codigo=problema[0])
    modo, motivo = autorizacao(empresas[empresa])
    if motivo:
        return recusar("EMPRESA_NAO_AUTORIZADA", motivo, empresa=empresa)
    if fluxo not in FLUXOS:
        return recusar("PARAMETROS_INVALIDOS", f"Fluxo deve ser um de {', '.join(FLUXOS)}.")
    if fluxo == "FINANCEIRO_BANCOS" and not financeiro_permitido(empresas[empresa]):
        return recusar("FLUXO_NAO_AUTORIZADO", "O fluxo Financeiro → Contabilidade/Bancos exige empresa fictícia ou piloto real AUTORIZADO "
                       "em SIMULAÇÃO (autorização específica do Supervisor). Produção continua bloqueada.", empresa=empresa)
    competencia, problema = identificar_competencia(pedido)
    if problema:
        return recusar("ESCLARECIMENTO_NECESSARIO", problema[1], codigo=problema[0], empresa=empresa)
    pasta, motivo = validar_pasta(empresa, pasta_informada or f"TREINAMENTO/{competencia}/DOCUMENTOS")
    if motivo:
        return recusar("AGUARDANDO_DOCUMENTO", motivo, empresa=empresa, competencia=competencia)
    ordem = ler_ordem()
    if ordem is not None:
        return recusar("ORDEM_ATIVA_EXISTENTE", f"Já existe ordem ativa ({ordem.get('sol')}, {ordem.get('empresa')}). "
                       "Encerre ou cancele essa SOL antes de abrir outra (uma empresa por vez).")

    registro = ler_registro()
    momento = agora()
    sol = proxima_sol(registro, momento.year)
    registro.setdefault("sequencia_sol", {})[str(momento.year)] = int(sol.rsplit("-", 1)[1])
    e = empresas[empresa]
    piloto = PILOTO if eh_piloto(empresas[empresa]) else None
    registro["solicitacoes"][sol] = {
        "sol": sol, "empresa": empresa, "competencia": competencia, "pasta": pasta, "modo": modo, "piloto": piloto,
        "etapa": "DOCUMENTOS", "estado": "DOCUMENTOS_EM_ANDAMENTO", "pedido": pedido, "fluxo": fluxo,
        "eventos": [{"em": momento.isoformat(), "evento": "SOL aberta; ordem ativa emitida para o Agente de Documentos"}],
    }
    gravar_json(REGISTRO, registro)
    gravar_json(ORDEM_ATIVA, {"sol": sol, "empresa": empresa, "competencia": competencia, "emitida_por": "Coordenador Geral",
                              "emitida_em": momento.replace(tzinfo=None).isoformat(),
                              "valida_ate": (momento + VALIDADE_ORDEM).replace(tzinfo=None).isoformat()})
    ordem_de_servico = (
        "ORDEM DE SERVIÇO — Coordenador Geral → Agente de Documentos\n"
        f"- SOL: {sol}\n"
        f"- Empresa: {empresa} — razão social {e['razao_social']} — CNPJs do cliente: {', '.join(e['cnpjs_formatados']) or 'NÃO CONSTA'}"
        + (" (cadastro: a confirmar; NÃO validados)" if piloto and "A CONFIRMAR" in normalizar(e["texto"]) else "") + "\n"
        f"- Competência: {competencia} — Modo: {modo}" + (f" — {PILOTO} (conferência manual de 100% pelo Supervisor)" if piloto else "") + "\n"
        f"- Pasta dos documentos (relativa à pasta da empresa): {pasta}\n"
        "- Tarefas: (1) inventário completo da pasta; (2) leitura de todos os documentos pelo extrator; (3) ficha de cada "
        "documento extraído; (4) classificação por tipo e competência; (5) duplicidades; (6) pendências propostas; "
        "(7) documentos não analisados com o código do extrator.\n"
        + ("- Fluxo: FINANCEIRO → CONTABILIDADE/BANCOS. Organize extratos bancários, relação de pagamentos, comprovantes e "
           "documentos de suporte (nota, boleto, guia, recibo); indique conta bancária, titular e período de cada extrato quando "
           "constarem no documento. Não faça a conferência financeira (é do Agente Financeiro).\n" if fluxo == "FINANCEIRO_BANCOS" else "")
        + "Devolva o relatório completo no formato do MODELO-RELATORIO.md.")
    return saida({"resultado": "SOL_ABERTA", "sol": sol, "empresa": empresa, "razao_social": e["razao_social"],
                  "cnpjs": e["cnpjs_formatados"], "competencia": competencia, "modo": modo, "piloto": piloto, "pasta": pasta,
                  "estado": "DOCUMENTOS_EM_ANDAMENTO", "fluxo": fluxo, "ordem_ativa_valida_ate": (momento + VALIDADE_ORDEM).isoformat(),
                  "delegar_para": "agente-documentos", "ordem_de_servico": ordem_de_servico})


def secao(relatorio: str, numero: int):
    linhas, dentro = [], False
    for l in relatorio.splitlines():
        if l.startswith("## "):
            dentro = l.startswith(f"## {numero}.")
            continue
        if dentro:
            linhas.append(l)
    return linhas if any(relatorio_l.startswith(f"## {numero}.") for relatorio_l in relatorio.splitlines()) else None


def linhas_tabela(linhas) -> list:
    tabela = [[c.strip() for c in l.strip().strip("|").split("|")] for l in linhas if l.strip().startswith("|")]
    tabela = [c for c in tabela if not all(re.fullmatch(r":?-{2,}:?", x) for x in c if x)][1:]   # sem separador e cabeçalho
    return [c for c in tabela if not all(normalizar(x) in ("", "-", "—", "NENHUM", "NENHUMA") for x in c)]


def motivos_do_relatorio(relatorio: str, sol: str, empresa: str, outras: list) -> list:
    motivos = []
    cabecalho = next((l for l in relatorio.splitlines() if "EMPRESA:" in l), "")
    empresa_rel = re.search(r"EMPRESA:\s*([^\s|]+)", cabecalho)
    if not empresa_rel or empresa_rel.group(1) != empresa:
        motivos.append(f"Relatório com empresa diferente da SOL ({empresa_rel.group(1) if empresa_rel else 'ausente'} ≠ {empresa}).")
    if sol not in relatorio:
        motivos.append(f"Relatório não identifica a {sol}.")
    citadas = [o for o in outras if re.search(rf"(?<![A-Za-z0-9-]){re.escape(o)}(?![A-Za-z0-9-])", relatorio)]
    if citadas:
        motivos.append(f"Relatório cita outra empresa ({', '.join(citadas)}); possível mistura de dados.")
    secoes = {n: secao(relatorio, n) for n in (1, 5, 6, 7)}
    faltando = [str(n) for n, s in secoes.items() if s is None]
    if faltando:
        motivos.append(f"Relatório fora do modelo (seções ausentes: {', '.join(faltando)}).")
        return motivos
    for c in linhas_tabela(secoes[1]):
        if any("PARCIAL" in normalizar(x) for x in c):
            motivos.append(f"Relatório: documento parcial no inventário ({c[1] if len(c) > 1 else c[0]}).")
    nao_analisados = linhas_tabela(secoes[6])
    if nao_analisados:
        motivos.append("Relatório: documento(s) não analisado(s): " + "; ".join(f"{c[0]} ({c[1]})" if len(c) > 1 else c[0] for c in nao_analisados) + ".")
    for c in linhas_tabela(secoes[5]):
        tipo = normalizar(c[2]) if len(c) > 2 else ""
        if "DIVERGENCIA" in tipo or "IDENTIFICACAO" in tipo or "TITULARIDADE" in tipo:
            motivos.append(f"Relatório: pendência bloqueante {c[0]} ({c[2]}): {c[3] if len(c) > 3 else ''}"[:240])
    for c in linhas_tabela(secoes[7]):
        situacao = normalizar(" ".join(c[1:2]))
        if "PARCIAL" in situacao or "NAO EXECUTADA" in situacao:
            motivos.append(f"Relatório: tarefa {c[0]} {c[1]}.")
    return motivos


def motivos_do_extrator(empresa: str, pasta: str) -> list:
    """Inventário refeito pelo Coordenador: o agente não consegue esconder documento não extraído ou marcado."""
    motivos, itens, parte, total = [], [], 1, 1
    while parte <= total:
        p = subprocess.run([sys.executable, "-I", str(EXTRATOR), "--empresa", empresa, "--pasta", pasta, "--resumo", "--parte", str(parte)],
                           cwd=RAIZ, capture_output=True, encoding="utf-8")
        if p.returncode != 0:
            return [f"Extrator: não foi possível refazer o inventário ({(p.stderr or '').strip()[:160]})."]
        dados = json.loads(p.stdout)
        itens += dados["itens"]
        total = dados["partes_total"]
        parte += 1
    for i in itens:
        if not str(i.get("leitura", "")).startswith("EXTRAIDO_"):
            motivos.append(f"Extrator: {i['nome']} = {i.get('leitura')} (não extraído).")
        bloqueantes = sorted(set(i.get("marcacoes", [])) - MARCACOES_NAO_BLOQUEANTES)
        if bloqueantes:
            motivos.append(f"Extrator: {i['nome']} com marcação {', '.join(bloqueantes)}.")
        if i.get("duplicado_de"):
            motivos.append(f"Extrator: {i['nome']} é duplicado exato de outro arquivo.")
    return motivos


def encerrar(sol: str, caminho_relatorio: str) -> int:
    registro = ler_registro()
    s = registro["solicitacoes"].get(sol)
    if s is None:
        return recusar("SOL_DESCONHECIDA", f"{sol} não foi aberta por este Coordenador.")
    if s["estado"] != "DOCUMENTOS_EM_ANDAMENTO":
        return recusar("SOL_JA_ENCERRADA", f"{sol} já está em {s['estado']}; SOL não é reutilizada. Abra uma nova SOL.")
    motivos = []
    ordem = ler_ordem()
    if ordem is None:
        motivos.append("Ordem ativa da SOL não encontrada no encerramento (vencida ou removida por fora do Coordenador).")
    elif ordem.get("sol") != sol:
        return recusar("ORDEM_DE_OUTRA_SOL", f"A ordem ativa pertence a {ordem.get('sol')}; nada foi alterado.")
    else:
        if ordem.get("empresa") != s["empresa"]:
            motivos.append(f"Ordem ativa com empresa trocada durante a SOL ({ordem.get('empresa')} ≠ {s['empresa']}).")
        ORDEM_ATIVA.unlink()

    try:
        relatorio = Path(caminho_relatorio).read_text(encoding="utf-8")
    except OSError as e:
        relatorio = None
        motivos.append(f"Relatório do Agente de Documentos não pôde ser lido ({type(e).__name__}).")
    if relatorio is not None:
        outras = [x for x in empresas_cadastradas() if x != s["empresa"]]
        motivos += motivos_do_relatorio(relatorio, sol, s["empresa"], outras)
    motivos += motivos_do_extrator(s["empresa"], s["pasta"])

    momento = agora().isoformat()
    if motivos:
        etapa, estado = "DOCUMENTOS_PENDENTE", "AGUARDANDO_SUPERVISOR"
        mensagem = f"{sol}: etapa documental com pendência bloqueante. Decisão do Supervisor necessária antes do Financeiro."
    else:
        etapa, estado = "DOCUMENTOS_CONCLUIDO", "PRONTO_PARA_FINANCEIRO"
        mensagem = (f"{sol}: etapa documental concluída. Próximo estágio: FINANCEIRO, que ainda não está implementado/"
                    "homologado. Nenhum outro agente foi executado.")
    proximo = "FINANCEIRO" if estado == "PRONTO_PARA_FINANCEIRO" else None
    if s.get("fluxo") == "FINANCEIRO_BANCOS":
        # Pendência de documento (ilegível, não analisado, marcado) não impede a conferência dos demais: segue como
        # pendência para o Financeiro. Problema estrutural (empresa, SOL, modelo, ordem ativa) para no Supervisor.
        documentais = ("Extrator:", "Relatório: documento", "Relatório: pendência", "Relatório: tarefa")
        estruturais = [m for m in motivos if not m.startswith(documentais)]
        if estruturais:
            estado, proximo = "AGUARDANDO_SUPERVISOR", None
            mensagem = f"{sol}: etapa documental com problema estrutural; o Financeiro não foi acionado. Decisão do Supervisor necessária."
        else:
            estado, proximo = "FINANCEIRO_EM_ANDAMENTO", "FINANCEIRO"
            s["plano_etapas"] = novo_plano(["FINANCEIRO", "BANCOS"])      # sem pacote local: a Conciliação não é acionada
            s["pendencias_documentos"] = motivos
            mensagem = (f"{sol}: etapa documental encerrada; o Coordenador encaminhou à conferência do Agente Financeiro"
                        + (f" com {len(motivos)} pendência(s) de documento." if motivos else "."))
    if s.get("piloto") == PILOTO:
        # Piloto real supervisionado: sempre para para a conferência humana, mesmo sem pendência documental.
        estado = "AGUARDANDO_SUPERVISOR"
        motivos = [f"{CONFERENCIA_PILOTO}: piloto real supervisionado; o Supervisor confere 100% do resultado antes de "
                   "qualquer próximo estágio (Financeiro e Importação não são executados)."] + motivos
        mensagem = (f"{sol}: {PILOTO}. Etapa documental {'concluída' if etapa == 'DOCUMENTOS_CONCLUIDO' else 'com pendências'}; "
                    f"aguardando a conferência manual do Supervisor ({CONFERENCIA_PILOTO}).")
    s.update(etapa=etapa, estado=estado, motivos=motivos,
             relatorio_sha256=hashlib.sha256(relatorio.encode("utf-8")).hexdigest() if relatorio is not None else None)
    s["eventos"].append({"em": momento, "evento": f"{etapa} -> {estado}; ordem ativa encerrada"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "SOL_ENCERRADA", "sol": sol, "empresa": s["empresa"], "competencia": s["competencia"],
                  "etapa_documentos": etapa, "estado": estado, "motivos": motivos, "piloto": s.get("piloto"),
                  "proximo_estagio": proximo if s.get("piloto") != PILOTO else None, "fluxo": s.get("fluxo", "DOCUMENTOS"),
                  "agente_executado_apos_documentos": ("Agente Financeiro (código local), depois Contabilidade/Bancos"
                                                       if estado == "FINANCEIRO_EM_ANDAMENTO" else "nenhum"),
                  "ordem_ativa_residual": ORDEM_ATIVA.exists(), "mensagem_supervisor": mensagem})


def encerrar_local(sol, caminho):
    """Contrato estruturado local; não exige nem imita relatório de um modelo."""
    registro = ler_registro()
    s = registro['solicitacoes'].get(sol)
    if not s or s['estado'] != 'DOCUMENTOS_EM_ANDAMENTO':
        return recusar('SOL_INVALIDA', 'Solicitação ausente ou etapa documental já encerrada.')
    ordem = ler_ordem()
    if not ordem or ordem.get('sol') != sol or ordem.get('empresa') != s['empresa']:
        return recusar('ORDEM_INVALIDA', 'Ordem ativa não corresponde à solicitação.')
    motivos, estruturais = [], []
    try:
        d = json.loads(Path(caminho).read_text(encoding='utf-8'))
        if (d.get('contrato'), d.get('empresa'), d.get('sol'), d.get('competencia'), d.get('pasta')) != (
                'DOCUMENTOS_LOCAL_V1', s['empresa'], sol, s['competencia'], s['pasta']):
            raise ValueError('Contrato ou identificação inválidos.')
        base = (CLIENTES / s['empresa']).resolve()
        alvo = (base / s['pasta']).resolve()
        atuais = {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in alvo.rglob('*') if p.is_file() and not p.is_symlink()}
        recebidos = {i['arquivo']: i['sha256'] for i in d['itens']}
        if atuais != recebidos:
            raise ValueError('Inventário ou hashes não conferem com os documentos recebidos.')
        motivos = [str(x) for x in d['pendencias']]
        s['limitacoes_documentos'] = [str(x) for x in d['limitacoes']]
        s['triagem_documentos'] = [{'arquivo': i['arquivo'], **i['encaminhamento']} for i in d['itens'] if i.get('encaminhamento')]
        s['tarefas_areas'] = d.get('tarefas_areas', {})
        s['escopo_resultado'] = 'PARCIAL_PILOTO_SEM_CONCILIACAO'
        # âncora de integridade: hashes do manifesto e da extração no registro (conferidos antes de cada área)
        extracao = Path(caminho).with_name('extracao-local.json')
        s['ancora_documentos'] = {'manifesto_sha256': hashlib.sha256(Path(caminho).read_bytes()).hexdigest(),
                                  'extracao_sha256': hashlib.sha256(extracao.read_bytes()).hexdigest() if extracao.is_file() else None,
                                  'registrada_em': agora().isoformat()}
    except (OSError, ValueError, KeyError, TypeError) as e:
        estruturais.append('Falha no resultado local: ' + str(e))
    ORDEM_ATIVA.unlink()
    tarefas = s.get('tarefas_areas', {}) if not estruturais else {}
    destinos_financeiros = any(i.get('conteudo_utilizavel') and
                              (i.get('encaminhamento') or {}).get('area') == 'FINANCEIRO'
                              for i in d.get('itens', [])) if not estruturais else False
    solicitado_financeiro = s.get('fluxo') == 'FINANCEIRO_BANCOS'
    empresa_atual = empresas_cadastradas().get(s['empresa'])
    permitido = bool(empresa_atual and financeiro_permitido(empresa_atual))
    financeiro = (solicitado_financeiro or destinos_financeiros) and not estruturais
    if financeiro and not permitido:
        financeiro = False
        motivos.append('Documentos destinados ao Financeiro; encaminhamento pendente porque o piloto Financeiro/Bancos da empresa não está autorizado.')
    elif financeiro and not solicitado_financeiro:
        s['fluxo_origem'] = s.get('fluxo', 'DOCUMENTOS')
        s['fluxo'] = 'FINANCEIRO_BANCOS'
        s['eventos'].append({'em': agora().isoformat(), 'evento': 'Triagem de Documentos identificou destino Financeiro; encaminhamento automático autorizado pelo cadastro da empresa.'})
    acionadas = {'FINANCEIRO': financeiro}
    for area, texto in (('DP', 'Documentos de pessoal recebidos'), ('FISCAL', 'Documentos fiscais recebidos')):
        recebidos = not estruturais and bool(tarefas.get(area, {}).get('documentos'))
        if recebidos and not permitido:
            motivos.append(f'{texto}; piloto da empresa não autorizado para execução local. Confira o cadastro com o Supervisor.')
            tarefas[area]['estado'] = 'BLOQUEADO'
        acionadas[area] = recebidos and permitido
    etapas = [e for area, ativo in acionadas.items() if ativo for e in (area, *DEPENDENTES[area])]
    if etapas:
        etapas.append('CONCILIACAO')
    s['plano_etapas'] = novo_plano(etapas)
    s.update(etapa='DOCUMENTOS_PENDENTE' if motivos or estruturais else 'DOCUMENTOS_CONCLUIDO',
             motivos=estruturais + motivos, pendencias_documentos=motivos, executor_documentos='LOCAL_SEM_MODELO')
    s['estado'] = avancar(s)
    nomes = [n for n, a in (('Financeiro', acionadas['FINANCEIRO']), ('DP', acionadas['DP']), ('Fiscal', acionadas['FISCAL'])) if a]
    s['eventos'].append({'em': agora().isoformat(), 'evento': 'Documentos local encerrado → ' + s['estado']
                         + (f"; áreas acionadas: {', '.join(nomes)}; depois Contabilidade e Conciliação" if nomes else '')})
    gravar_json(REGISTRO, registro)
    return saida({'resultado': 'SOL_ENCERRADA', 'estado': s['estado'], 'sol': sol, 'piloto': s.get('piloto'),
                  'areas_acionadas': nomes,
                  'mensagem_supervisor': (f"Documentos distribuídos a {', '.join(nomes)}; depois a Contabilidade prepara as propostas e a "
                                          "Conciliação confere (SIMULAÇÃO)." if nomes else
                                          'Triagem local concluída; confira os destinos, limitações e pendências das áreas.'),
                  'motivos': s['motivos']})


IMPORTACAO_VGROW_ATIVA = False   # especialista desativado por decisão do Supervisor; código e histórico preservados


def registrar_importacao(sol: str, caminho_resultado: str) -> int:
    """Etapa de Importação ESPECÍFICA DA VGROW: só depois da etapa de Documentos de uma SOL piloto e por ação do
    Supervisor. O resultado é consolidado na SOL, que continua em AGUARDANDO_SUPERVISOR (conferência e aprovação manual)."""
    registro = ler_registro()
    s = registro["solicitacoes"].get(sol)
    if s is None:
        return recusar("SOL_DESCONHECIDA", f"{sol} não foi aberta por este Coordenador.")
    if s["empresa"] != "VGROW" or s.get("piloto") != PILOTO:
        return recusar("IMPORTACAO_NAO_PERMITIDA", "A área de Importação atende somente SOL piloto da VGROW.")
    if s["estado"] != "AGUARDANDO_SUPERVISOR" or s.get("etapa") not in ("DOCUMENTOS_CONCLUIDO", "DOCUMENTOS_PENDENTE"):
        return recusar("IMPORTACAO_NAO_PERMITIDA", "A etapa de Documentos desta SOL ainda não terminou.")
    try:
        r = json.loads(Path(caminho_resultado).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return recusar("RESULTADO_INVALIDO", "Resultado da Importação ilegível.")
    if r.get("sol") != sol or r.get("empresa") != "VGROW" or r.get("competencia") != s["competencia"]:
        return recusar("RESULTADO_INVALIDO", "Resultado da Importação não corresponde a esta SOL/empresa/competência.")
    fechados, pendentes = len(r.get("processos_fechados", [])), len(r.get("processos_pendentes", []))
    execucao = {"em": agora().isoformat(), "fechados": fechados, "pendentes": pendentes,
                "processos_fechados": [p["processo"] for p in r.get("processos_fechados", [])],   # histórico contra duplicidade
                "validacao_debito_igual_credito": r.get("validacao_debito_igual_credito"),
                "alertas": len(r.get("alertas", [])), "divergencias": len(r.get("divergencias", [])),
                "resultado_sha256": hashlib.sha256(Path(caminho_resultado).read_bytes()).hexdigest()}
    s.setdefault("importacao", []).append(execucao)
    s["eventos"].append({"em": execucao["em"], "evento": f"IMPORTACAO (SIMULAÇÃO) devolvida ao Coordenador: {fechados} "
                         f"fechado(s), {pendentes} pendente(s); aguardando conferência do Supervisor"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "IMPORTACAO_REGISTRADA", "sol": sol, "estado": s["estado"], "execucao": execucao,
                  "mensagem_supervisor": f"{sol}: Importação VGROW devolvida ao Coordenador ({fechados} processo(s) fechado(s), "
                                         f"{pendentes} pendente(s)). Nada foi liberado nem importado: conferência e aprovação manual."})


def _sol_piloto_vgrow(registro: dict, sol: str):
    s = registro["solicitacoes"].get(sol)
    if s is None:
        return None, recusar("SOL_DESCONHECIDA", f"{sol} não foi aberta por este Coordenador.")
    if s["empresa"] != "VGROW" or s.get("piloto") != PILOTO or s["estado"] != "AGUARDANDO_SUPERVISOR":
        return None, recusar("NAO_PERMITIDO", "Somente SOL piloto da VGROW em AGUARDANDO_SUPERVISOR.")
    return s, None


def registrar_aceite(sol: str, processo: str, chave: str, diferenca: str) -> int:
    """Aceite explícito do Supervisor para a diferença numerário − saldo − total REAL de UM processo, amarrado à chave
    (valores, fontes e documentos). Valores/documentos mudaram → a chave muda e o aceite precisa ser dado de novo."""
    registro = ler_registro()
    s, erro = _sol_piloto_vgrow(registro, sol)
    if erro is not None:
        return erro
    if not re.fullmatch(r"OCCT\d{4,6}/\d{2}", processo) or not re.fullmatch(r"[0-9a-f]{64}", chave) or not re.fullmatch(r"-?\d+\.\d{2}", diferenca):
        return recusar("PARAMETROS_INVALIDOS", "Processo, chave ou diferença inválidos.")
    momento = agora().isoformat()
    s.setdefault("aceites", {})[processo] = {"chave": chave, "diferenca": diferenca, "em": momento}
    s["eventos"].append({"em": momento, "evento": f"ACEITE do Supervisor: {processo}, diferença {diferenca} (chave {chave[:12]})"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "ACEITE_REGISTRADO", "sol": sol, "processo": processo, "diferenca": diferenca, "em": momento})


def registrar_decisao_pendencia(sol: str, pendencia: str, decisao: str, justificativa: str) -> int:
    """Decisão do Supervisor sobre uma pendência do relatório (o texto original é preservado). Só assim um item é RESOLVIDA."""
    registro = ler_registro()
    s, erro = _sol_piloto_vgrow(registro, sol)
    if erro is not None:
        return erro
    if not re.fullmatch(r"P-\d{2,3}", pendencia) or decisao not in ("RESOLVIDA", "REABERTA") or not 5 <= len(justificativa.strip()) <= 500:
        return recusar("PARAMETROS_INVALIDOS", "Pendência, decisão (RESOLVIDA/REABERTA) ou justificativa (5 a 500 caracteres) inválida.")
    momento = agora().isoformat()
    s.setdefault("decisoes_pendencias", {}).setdefault(pendencia, []).append({"decisao": decisao, "justificativa": justificativa.strip(), "em": momento})
    s["eventos"].append({"em": momento, "evento": f"Supervisor: {pendencia} {decisao}"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "DECISAO_REGISTRADA", "sol": sol, "pendencia": pendencia, "decisao": decisao, "em": momento})


# ---------------------------------------------------------------- fluxo FINANCEIRO → CONTABILIDADE/BANCOS (SIMULAÇÃO)
# Documentos → Coordenador → Financeiro (conferência, código local) → Coordenador → Contabilidade/Bancos (lançamentos,
# código local) → Coordenador → Supervisor. O Coordenador registra cada retorno, guarda as tentativas e decide a próxima
# etapa; decisões do Supervisor valem só para o movimento decidido; regra nova só vale depois de aprovada.

TIPOS_LANCAMENTO = ("LIQUIDACAO_OBRIGACAO", "DESPESA", "RECEBIMENTO", "RECEITA", "ADIANTAMENTO_FORNECEDOR", "ADIANTAMENTO_CLIENTE")
CHAVES_CONDICAO = ("direcao", "tipo_banco", "historico_contem", "favorecido_cnpj", "suporte", "conta", "obrigacao_contabilizada", "competencia_desde")
CABECALHO_REGRAS = "| Regra | Versão | Condições | Tipo | Contrapartida | Exige suporte | Histórico | Origem | Situação | Aprovação |"


def _sol_financeira(registro: dict, sol: str, estados: tuple):
    s = registro["solicitacoes"].get(sol)
    if s is None:
        return None, recusar("SOL_DESCONHECIDA", f"{sol} não foi aberta por este Coordenador.")
    if s.get("fluxo") != "FINANCEIRO_BANCOS":
        return None, recusar("NAO_PERMITIDO", f"{sol} não é do fluxo Financeiro → Contabilidade/Bancos.")
    if s["estado"] not in estados:
        return None, recusar("NAO_PERMITIDO", f"{sol} está em {s['estado']} (esperado: {' ou '.join(estados)}).")
    return s, None


def _resultado_da_sol(caminho: str, s: dict, sol: str, agente: str):
    try:
        r = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if r.get("sol") != sol or r.get("empresa") != s["empresa"] or r.get("competencia") != s["competencia"] or r.get("agente") != agente:
        return None
    return r


def contas_do_plano(empresa: str) -> set:
    arquivo = CLIENTES / empresa / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md"
    codigos, dentro, cab = set(), False, None
    for l in (arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []):
        if l.startswith("## "):
            dentro = normalizar(l).startswith("## CONTAS UTILIZADAS")
            continue
        if dentro and l.strip().startswith("|"):
            celulas = [c.strip() for c in l.strip().strip("|").split("|")]
            if cab is None:
                cab = celulas
            elif not all(re.fullmatch(r":?-{2,}:?", c) for c in celulas if c) and re.sub(r"\D", "", celulas[0]):
                codigos.add(re.sub(r"\D", "", celulas[0]))
    return codigos


# Compatibilidade natureza × grupo da conta (procedimento de Contabilidade/Bancos). A conta de contrapartida nunca é a conta
# contábil de uma conta bancária da própria empresa (transferência própria tem tratamento próprio).
COMPATIBILIDADE = {"LIQUIDACAO_OBRIGACAO": ("DEBITO", {"PASSIVO"}), "DESPESA": ("DEBITO", {"DESPESA", "CUSTO"}),
                   "RECEBIMENTO": ("CREDITO", {"ATIVO"}), "RECEITA": ("CREDITO", {"RECEITA"})}
COMPATIBILIDADE.update(ADIANTAMENTO_FORNECEDOR=('DEBITO', {'ATIVO'}), ADIANTAMENTO_CLIENTE=('CREDITO', {'PASSIVO'}))


def grupos_do_plano(empresa: str) -> dict:
    """Código reduzido → grupo (coluna "Grupo" do plano; vazio = não definido pelo Supervisor)."""
    arquivo = CLIENTES / empresa / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md"
    grupos, dentro, cab = {}, False, None
    for l in (arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []):
        if l.startswith("## "):
            dentro = normalizar(l).startswith("## CONTAS UTILIZADAS")
            continue
        if dentro and l.strip().startswith("|"):
            celulas = [c.strip() for c in l.strip().strip("|").split("|")]
            if cab is None:
                cab = [normalizar(c) for c in celulas]
            elif not all(re.fullmatch(r":?-{2,}:?", c) for c in celulas if c) and re.sub(r"\D", "", celulas[0]):
                linha = dict(zip(cab, celulas))
                grupos[re.sub(r"\D", "", celulas[0])] = ('' if normalizar(linha.get('TIPO','')) == 'SINTETICA' or
                                                        ((CLIENTES / empresa / 'empresa-local.json').exists() and normalizar(linha.get('TIPO','')) != 'ANALITICA')
                                                        else normalizar(linha.get("GRUPO", "")).replace(" ", "_"))
    return grupos


def contas_bancarias_contabeis(empresa: str) -> set:
    texto = (CLIENTES / empresa / "CADASTRO.md").read_text(encoding="utf-8")
    contas, dentro, cab = set(), False, None
    for l in texto.splitlines():
        if l.startswith("## "):
            dentro = normalizar(l).startswith("## CONTAS BANCARIAS")
            continue
        if dentro and l.strip().startswith("|"):
            celulas = [c.strip() for c in l.strip().strip("|").split("|")]
            if cab is None:
                cab = [normalizar(c) for c in celulas]
            elif not all(re.fullmatch(r":?-{2,}:?", c) for c in celulas if c):
                codigo = re.sub(r"\D", "", dict(zip(cab, celulas)).get("CONTA CONTABIL", ""))
                if codigo:
                    contas.add(codigo)
    return contas


def contas_adiantamento(empresa: str) -> dict:
    """Natureza → contas indicadas expressamente pelo Supervisor (CADASTRO.md, seção "Contas de adiantamento")."""
    arquivo = CLIENTES / empresa / "CADASTRO.md"
    contas, dentro, cab = {}, False, None
    for l in (arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []):
        if l.startswith("## "):
            dentro, cab = normalizar(l).startswith("## CONTAS DE ADIANTAMENTO"), None
            continue
        if dentro and l.strip().startswith("|"):
            celulas = [c.strip() for c in l.strip().strip("|").split("|")]
            if cab is None:
                cab = [normalizar(c) for c in celulas]
            elif not all(re.fullmatch(r":?-{2,}:?", c) for c in celulas if c):
                linha = dict(zip(cab, celulas))
                natureza, conta = normalizar(linha.get("NATUREZA", "")).replace(" ", "_"), re.sub(r"\D", "", linha.get("CONTA CONTABIL", ""))
                if natureza.startswith("ADIANTAMENTO_") and conta:
                    contas.setdefault(natureza, []).append(conta)
    return contas


def compatibilidade(empresa: str, conta: str, natureza: str):
    """None se a conta pode ser contrapartida desta natureza; senão (código, motivo) — nada é presumido."""
    if natureza not in COMPATIBILIDADE:
        return "PARAMETROS_INVALIDOS", f"Natureza deve ser uma de {', '.join(COMPATIBILIDADE)}."
    if natureza.startswith("ADIANTAMENTO_") and conta not in contas_adiantamento(empresa).get(natureza, []):
        return ("ADIANTAMENTO_NAO_INDICADO", f"Conta {conta or '(vazia)'} não é a conta de adiantamento indicada pelo Supervisor para "
                                             f"{natureza} nesta empresa. Indique a conta em Empresas (contas de adiantamento); "
                                             "sem indicação, a classificação fica pendente.")
    grupos = grupos_do_plano(empresa)
    if conta not in grupos:
        return "CONTA_INEXISTENTE", f"Conta {conta or '(vazia)'} não existe no plano de contas de {empresa}."
    if conta in contas_bancarias_contabeis(empresa):
        return "COMBINACAO_INCOMPATIVEL", f"Conta {conta} é a conta contábil de uma conta bancária da empresa; não pode ser contrapartida."
    exigidos = COMPATIBILIDADE[natureza][1]
    if not grupos[conta]:
        return ("GRUPO_NAO_DEFINIDO", f"Conta {conta} sem grupo no plano de contas: defina o grupo (ATIVO, PASSIVO, RECEITA, DESPESA...) "
                                      f"para validar a natureza {natureza} (exige {' ou '.join(sorted(exigidos))}).")
    if grupos[conta] not in exigidos:
        return ("COMBINACAO_INCOMPATIVEL", f"Conta {conta} é do grupo {grupos[conta]}; a natureza {natureza} exige conta do grupo "
                                           f"{' ou '.join(sorted(exigidos))}.")
    return None


def movimentos_tratados(registro: dict, sol: str) -> dict:
    """Histórico de duplicidade da empresa, com as duas situações SEPARADAS:
    - escriturados: lançamento EFETIVAMENTE escriturado (registro "escriturados" da SOL, gravado só por etapa futura de
      aprovação/liberação; nesta fase não há escrituração efetiva) → o movimento não gera lançamento de novo;
    - propostas_simulacao: propostas geradas em SIMULAÇÃO (cada tentativa de Bancos, desta e de outras SOLs) → não
      bloqueiam; a nova proposta sai como REVISÃO rastreável (SOL e tentativa anteriores)."""
    s = registro["solicitacoes"][sol]
    escriturados, propostas = {}, {}
    for outra, o in sorted(registro["solicitacoes"].items()):
        if o.get("empresa") != s["empresa"] or o.get("fluxo") != "FINANCEIRO_BANCOS":
            continue
        for e in o.get("escriturados", []):
            escriturados.setdefault(e["movimento"], {"sol": outra, "lancamento": e.get("lancamento"), "em": e.get("em")})
        for n, b in enumerate(o.get("bancos", []), 1):
            for mid in b.get("movimentos_propostos_simulacao", b.get("movimentos_escriturados", [])):
                propostas.setdefault(mid, []).append({"sol": outra, "tentativa": n, "em": b.get("em")})
    return {"escriturados": escriturados, "propostas_simulacao": propostas}


# ---------------------------------------------------------------- fontes da empresa (vigência de conferências e aprovações)
# Cada etapa registra o sha256 das fontes da empresa que usou (fotografia tirada ANTES de executar e conferida no registro).
# Conciliação e aprovação só valem enquanto essas fontes, os resultados das áreas e o pacote de Documentos não mudarem.
ARQUIVOS_FONTE = {"CADASTRO": "CADASTRO.md", "EMPRESA_LOCAL": "empresa-local.json", "PLANO": "PLANO-DE-CONTAS/PLANO-DE-CONTAS.md",
                  "REGRAS_BANCOS": "REGRAS-BANCOS.md", "REGRAS_DP": "REGRAS-DP.json", "REGRAS_FISCAIS": "REGRAS-FISCAIS.json",
                  "REGRAS_CONCILIACAO": "REGRAS-CONCILIACAO.json", "PERFIL_FECHAMENTO": "PERFIL-FECHAMENTO.json",
                  "MARCA_FICTICIA": "AMOSTRA-FICTICIA.json", "BASE_INICIAL": "BASE-INICIAL/INDICE.json"}
ROTULO_FONTE = {"CADASTRO": "cadastro (CADASTRO.md)", "EMPRESA_LOCAL": "cadastro local e vínculos bancários (empresa-local.json)",
                "PLANO": "plano de contas", "REGRAS_BANCOS": "regras bancárias", "REGRAS_DP": "referências de DP",
                "REGRAS_FISCAIS": "referências fiscais", "REGRAS_CONCILIACAO": "exigências da Conciliação",
                "PERFIL_FECHAMENTO": "perfil de fechamento (referência)", "MARCA_FICTICIA": "marcador de empresa fictícia",
                "PACOTE": "pacote de Documentos (manifesto)", "EXTRACAO": "extração dos documentos",
                "BASE_INICIAL": "base inicial (balancete anterior, book, saldos e confirmação)"}
_FONTES_BASE = ("CADASTRO", "EMPRESA_LOCAL", "MARCA_FICTICIA")
FONTES_ETAPA = {"FINANCEIRO": _FONTES_BASE + ("PERFIL_FECHAMENTO",), "DP": _FONTES_BASE, "FISCAL": _FONTES_BASE,
                "BANCOS": _FONTES_BASE + ("PLANO", "REGRAS_BANCOS"), "CONTABILIDADE_DP": _FONTES_BASE + ("PLANO", "REGRAS_DP"),
                "CONTABILIDADE_FISCAL": _FONTES_BASE + ("PLANO", "REGRAS_FISCAIS"),
                "CONCILIACAO": _FONTES_BASE + ("PLANO", "REGRAS_CONCILIACAO", "BASE_INICIAL")}


def fontes_atuais(empresa: str, nomes=None) -> dict:
    base = CLIENTES / empresa
    saida = {}
    for nome in (nomes or ARQUIVOS_FONTE):
        arq = base / ARQUIVOS_FONTE[nome]
        saida[nome] = hashlib.sha256(arq.read_bytes()).hexdigest() if arq.is_file() else "AUSENTE"
    return saida


def conferir_fontes(caminho_resultado: str, empresa: str, etapa: str):
    """(fontes, motivo). Compara a fotografia tirada antes da execução (fontes.json ao lado do resultado) com as fontes agora:
    fonte alterada DURANTE a execução invalida o resultado (nada é aproveitado). Sem fotografia: registra as atuais."""
    atuais = fontes_atuais(empresa, FONTES_ETAPA[etapa])
    foto = Path(caminho_resultado).parent / "fontes.json"
    if foto.is_file():
        try:
            antes = json.loads(foto.read_text(encoding="utf-8")).get("fontes")
        except (OSError, ValueError):
            return None, "Fotografia das fontes (fontes.json) ilegível; resultado não registrado."
        if antes != atuais:
            mudaram = sorted(k for k in set(antes or {}) | set(atuais) if (antes or {}).get(k) != atuais.get(k))
            return None, ("Fontes da empresa alteradas durante a execução (" + ", ".join(ROTULO_FONTE.get(k, k) for k in mudaram)
                          + "); resultado não registrado. Execute novamente a etapa.")
    return atuais, None


def _ultima(s: dict, etapa: str):
    return (s.get(RESULTADOS_ETAPA[etapa]) or [None])[-1]


def vigencia(s: dict, conc=None) -> dict:
    """Vigência de uma Conciliação (padrão: a última): resultados, pacote, extração e fontes da empresa precisam ser exatamente os
    conferidos. Devolve {'vigente', 'motivos', 'rever'} — 'rever' = etapas que precisam ser revistas (nada é reexecutado sozinho)."""
    conc = conc if conc is not None else (s.get("conciliacao") or [None])[-1]
    if not conc:
        return {"vigente": False, "motivos": ["Nenhuma Conciliação registrada."], "rever": ["CONCILIACAO"]}
    motivos, rever = [], []
    atuais = {e: (_ultima(s, e) or {}).get("resultado_sha256") for e in RESULTADOS_ETAPA if e != "CONCILIACAO"}
    atuais = {e: v for e, v in atuais.items() if v}
    ancora = s.get("ancora_documentos") or {}
    if ancora.get("manifesto_sha256"):
        atuais["PACOTE"] = ancora["manifesto_sha256"]
    if ancora.get("extracao_sha256"):
        atuais["EXTRACAO"] = ancora["extracao_sha256"]
    conferidas = {k: v for k, v in (conc.get("versoes_entradas") or {}).items() if v}
    for k in sorted(set(atuais) | set(conferidas)):
        if atuais.get(k) != conferidas.get(k):
            nome = ROTULO_FONTE.get(k, f"resultado de {k}")
            motivos.append(f"{nome}: {'não conferido pela Conciliação' if k not in conferidas else 'alterado depois da Conciliação'}.")
            rever.append("CONCILIACAO")
    agora_f = fontes_atuais(s["empresa"])
    execucoes = [(e, _ultima(s, e)) for e in ETAPAS if e != "CONCILIACAO" and _ultima(s, e)] + [("CONCILIACAO", conc)]
    for etapa, ex in execucoes:
        usadas = ex.get("fontes_sha256")
        if usadas is None:
            motivos.append(f"{etapa}: execução anterior ao controle de fontes (cadastro, plano e regras não registrados); vigência não comprovada.")
            rever.append(etapa)
            continue
        for nome, sha in usadas.items():
            if agora_f.get(nome) != sha:
                motivos.append(f"{ROTULO_FONTE.get(nome, nome)} alterado depois da etapa {etapa}.")
                rever.append(etapa)
    if rever and "CONCILIACAO" not in rever:
        rever.append("CONCILIACAO")
    return {"vigente": not motivos, "motivos": list(dict.fromkeys(motivos)), "rever": [e for e in ETAPAS if e in rever]}


def vigencia_aprovacao(s: dict) -> list:
    """Motivos pelos quais a aprovação vigente NÃO vale mais para exportar/baixar (vazio = vale): fontes da empresa alteradas
    depois da aprovação, ou aprovação anterior ao controle de fontes. Resultados aprovados são conferidos por sha256 no TXT."""
    ap = s.get("aprovacao") or {}
    if "fontes_aprovadas" not in ap:
        return ["Aprovação anterior ao controle de fontes (cadastro, plano e regras não registrados na aprovação)."]
    atuais = fontes_atuais(s["empresa"])
    mudaram = sorted(k for k in set(ap["fontes_aprovadas"]) | set(atuais)
                     if ap["fontes_aprovadas"].get(k, "AUSENTE") != atuais.get(k, "AUSENTE"))
    return ["Fontes alteradas depois da aprovação: " + ", ".join(ROTULO_FONTE.get(k, k) for k in mudaram)
            + ". Revogue a aprovação e reveja as etapas afetadas."] if mudaram else []


# ---------------------------------------------------------------- identidade dos fatos (duplicação entre solicitações)
CHAVES_CONTABILIDADE = (("BANCOS", "bancos"), ("CONTABILIDADE_DP", "contabdp"), ("CONTABILIDADE_FISCAL", "contabilfiscal"))


def fatos_do_resultado(r: dict) -> dict:
    """Identidade → (valor, débito, crédito) dos lançamentos PROPOSTOS. Identidade vem da área (movimento do extrato; documento +
    evento + competência; nota/apuração), nunca só de valor ou nome de arquivo."""
    fatos = {}
    for l in r.get("lancamentos", []):
        if l.get("status") in ("PROPOSTO", "PROPOSTO_PARA_CONFERENCIA") and l.get("identidade"):
            fatos[l["identidade"]] = {"valor": l.get("valor"), "debito": (l.get("debito") or {}).get("codigo"),
                                      "credito": (l.get("credito") or {}).get("codigo"), "lancamento": l.get("id")}
    return fatos


def fatos_da_sol(s: dict):
    """Fatos propostos nas últimas execuções da Contabilidade. None = execução sem identidades (anterior a esta versão)."""
    fatos = {}
    for etapa, chave in CHAVES_CONTABILIDADE:
        ex = (s.get(chave) or [None])[-1]
        if ex is None:
            continue
        if "fatos" not in ex:
            return None
        fatos.update(ex["fatos"])
    return fatos


def _mesmo(a: dict, b: dict) -> bool:
    return (str(a.get("valor")), a.get("debito"), a.get("credito")) == (str(b.get("valor")), b.get("debito"), b.get("credito"))


def relacao_outras_sols(registro: dict, sol: str) -> list:
    """Relação desta SOL com as outras da MESMA empresa e competência: REVISAO_DE_PROPOSTA (outra ainda não aprovada),
    COMPLEMENTO (só fatos novos), REPETICAO_DE_APROVADA / SUBSTITUICAO_DE_APROVADA (mesmos fatos de SOL aprovada: bloqueia),
    FATOS_JA_EXPORTADOS (fatos que saíram em TXT depois revogado: exige ciência do Supervisor) e SEM_IDENTIDADES (anterior)."""
    s = registro["solicitacoes"][sol]
    meus = fatos_da_sol(s)
    saida = []
    # TXT revogado da PRÓPRIA SOL: os fatos podem ter sido importados no Domínio antes da revogação
    proprios = {}
    for ap in s.get("aprovacoes_anteriores", []):
        proprios.update(ap.get("fatos_exportados") or {})
    if meus and proprios:
        comuns = sorted(i for i in meus if i in proprios)
        if comuns:
            saida.append({"sol": sol, "estado": s.get("estado"), "classificacao": "FATOS_JA_EXPORTADOS", "fatos_exportados": comuns,
                          "texto": f"{len(comuns)} fato(s) desta SOL já saíram em TXT depois REVOGADO; se aquele TXT foi importado no "
                                   "Domínio, o estorno lá é manual antes de importar o novo."})
    for outra, m in (registro.get("registros_minimos") or {}).items():
        if (m.get("empresa"), m.get("competencia")) != (s.get("empresa"), s.get("competencia")) or not meus:
            continue
        comuns = sorted(i for i in meus if i in (m.get("fatos_exportados") or {}))
        if comuns:
            saida.append({"sol": outra, "estado": m.get("situacao"), "classificacao": "FATOS_JA_EXPORTADOS", "fatos_exportados": comuns,
                          "texto": f"{len(comuns)} fato(s) já saíram em TXT da {outra} ({m.get('situacao_texto')}); só o registro "
                                   "mínimo foi mantido. Se aquele TXT foi importado no Domínio, o estorno lá é manual."})
    for outra, o in registro["solicitacoes"].items():
        if outra == sol or (o.get("empresa"), o.get("competencia")) != (s.get("empresa"), s.get("competencia")) or o.get("estado") == "CANCELADA":
            continue
        aprovada = o.get("estado") == "FECHAMENTO_APROVADO"
        item = {"sol": outra, "estado": o.get("estado")}
        if meus is None:
            saida.append(dict(item, classificacao="SEM_IDENTIDADES", texto="Esta SOL é anterior às identidades de fatos: repetição não pode ser descartada."))
            continue
        aprovados = (o.get("aprovacao") or {}).get("fatos_aprovados") if aprovada else None
        if aprovada and aprovados is None:
            saida.append(dict(item, classificacao="SEM_IDENTIDADES",
                              texto=f"{outra} foi aprovada antes das identidades de fatos: repetição não pode ser descartada."))
            continue
        exportados = {}
        for ap in [o.get("aprovacao")] + o.get("aprovacoes_anteriores", []):
            exportados.update((ap or {}).get("fatos_exportados") or {})
        pendentes = (fatos_da_sol(o) or {}) if not aprovada else {}
        aprovados = aprovados or {}
        repetidos = sorted(i for i in meus if i in aprovados and _mesmo(meus[i], aprovados[i]))
        alterados = sorted(i for i in meus if i in aprovados and not _mesmo(meus[i], aprovados[i]))
        ja_exportados = sorted(i for i in meus if i in exportados and i not in aprovados)
        em_revisao = sorted(i for i in meus if i in pendentes)
        novos = sorted(i for i in meus if i not in aprovados and i not in exportados and i not in pendentes)
        if repetidos or alterados:
            classe = "SUBSTITUICAO_DE_APROVADA" if alterados else "REPETICAO_DE_APROVADA"
            texto = (f"{len(repetidos)} fato(s) iguais e {len(alterados)} alterado(s) em relação à {outra}, APROVADA: revogue a aprovação "
                     f"da {outra} (substituição) antes de aprovar esta, ou retire os fatos repetidos.")
        elif ja_exportados:
            classe, texto = "FATOS_JA_EXPORTADOS", (f"{len(ja_exportados)} fato(s) já saíram em TXT da {outra} (depois revogado); se aquele "
                                                   "TXT foi importado no Domínio, o estorno lá é manual.")
        elif em_revisao:
            classe, texto = "REVISAO_DE_PROPOSTA", f"{len(em_revisao)} fato(s) também propostos na {outra} (não aprovada): revisão de proposta."
        else:
            classe, texto = "COMPLEMENTO", f"Nenhum fato desta SOL consta na {outra} ({len(novos)} fato(s) desta SOL são novos em relação a ela)."
        saida.append(dict(item, classificacao=classe, texto=texto, repetidos=repetidos, alterados=alterados,
                          fatos_exportados=ja_exportados, em_revisao=em_revisao, novos=len(novos)))
    return saida


# ---------------------------------------------------------------- plano de etapas da SOL
# Áreas independentes (Financeiro, DP, Fiscal) analisam primeiro; a Contabilidade prepara depois (cada especialista depende só
# da própria área); a Conciliação roda quando as demais terminaram (com sucesso ou não) e informa o alcance.
ETAPAS = ("FINANCEIRO", "DP", "FISCAL", "BANCOS", "CONTABILIDADE_DP", "CONTABILIDADE_FISCAL", "CONCILIACAO")
DEPENDE = {"BANCOS": ("FINANCEIRO",), "CONTABILIDADE_DP": ("DP",), "CONTABILIDADE_FISCAL": ("FISCAL",)}
DEPENDENTES = {"FINANCEIRO": ("BANCOS",), "DP": ("CONTABILIDADE_DP",), "FISCAL": ("CONTABILIDADE_FISCAL",)}
TAREFA_ETAPA = {"FINANCEIRO": "FINANCEIRO", "DP": "DP", "FISCAL": "FISCAL", "BANCOS": "CONTABILIDADE", "CONTABILIDADE_DP": "CONTABILIDADE_DP",
                "CONTABILIDADE_FISCAL": "CONTABILIDADE_FISCAL", "CONCILIACAO": "CONCILIACAO"}
RESULTADOS_ETAPA = {"FINANCEIRO": "financeiro", "BANCOS": "bancos", "DP": "dp", "CONTABILIDADE_DP": "contabdp", "FISCAL": "fiscal",
                    "CONTABILIDADE_FISCAL": "contabilfiscal", "CONCILIACAO": "conciliacao"}
ORDEM_RESUMOS = ("CONCILIACAO", "FINANCEIRO", "BANCOS", "CONTABILIDADE_DP", "CONTABILIDADE_FISCAL")


def novo_plano(etapas) -> list:
    return [{"etapa": e, "situacao": "PENDENTE", "depende": list(DEPENDE.get(e, ())), "tentativas": 0} for e in ETAPAS if e in etapas]


def plano_de(s: dict) -> list:
    """Plano da SOL. SOL anterior a esta versão: reconstruído só do que já foi registrado (sem Conciliação, sem fabricar etapas)."""
    if "plano_etapas" not in s:
        etapas = (["FINANCEIRO", "BANCOS"] if s.get("fluxo") == "FINANCEIRO_BANCOS" else []) + \
                 (["FISCAL", "CONTABILIDADE_FISCAL"] if s.get("fiscal") or s.get("contabilfiscal") else [])
        plano = novo_plano(etapas)
        for e in plano:
            if s.get(RESULTADOS_ETAPA[e["etapa"]]):
                e.update(situacao="CONCLUIDA", tentativas=len(s[RESULTADOS_ETAPA[e["etapa"]]]))
            elif e["etapa"] in s.get("falhas_areas", {}):
                e["situacao"] = "FALHOU"
        s["plano_etapas"] = plano
    return s["plano_etapas"]


def etapa_do_plano(s: dict, nome: str):
    return next((e for e in plano_de(s) if e["etapa"] == nome), None)


def marcar(s: dict, nome: str, situacao: str) -> None:
    e = etapa_do_plano(s, nome)
    if e:
        e["situacao"] = situacao
        if situacao in ("CONCLUIDA", "FALHOU", "BLOQUEADA"):
            e["tentativas"] = e.get("tentativas", 0) + 1


def reabrir(s: dict, nomes) -> list:
    reabertas = []
    for nome in nomes:
        e = etapa_do_plano(s, nome)
        if e:
            e["situacao"] = "PENDENTE"
            reabertas.append(nome)
    return reabertas


def avancar(s: dict) -> str:
    """Estado seguinte: primeira etapa PENDENTE com dependência concluída. Dependência que falhou ou foi bloqueada bloqueia a
    dependente (explícito). A Conciliação espera todas as demais. Sem etapa pendente: AGUARDANDO_SUPERVISOR."""
    plano = plano_de(s)
    tarefas = s.setdefault("tarefas_areas", {})
    for e in plano:
        if e["situacao"] != "PENDENTE":
            continue
        if e["etapa"] == "CONCILIACAO":
            if any(x["situacao"] == "PENDENTE" for x in plano if x["etapa"] != "CONCILIACAO"):
                continue
        else:
            deps = [d for d in (etapa_do_plano(s, n) for n in e["depende"]) if d]
            ruim = next((d for d in deps if d["situacao"] in ("FALHOU", "BLOQUEADA", "BLOQUEADA_POR_DEPENDENCIA")), None)
            if ruim:
                e["situacao"] = "BLOQUEADA_POR_DEPENDENCIA"
                area = TAREFA_ETAPA[e["etapa"]]
                tarefas[area] = dict(tarefas.get(area, {}), area=area, estado="BLOQUEADO_POR_DEPENDENCIA", dependencia=ruim["etapa"],
                                     motivo=f"Depende de {ruim['etapa']}, que ficou {ruim['situacao']}; nada foi preparado nesta etapa.")
                continue
            if any(d["situacao"] == "PENDENTE" for d in deps):
                continue
        area = TAREFA_ETAPA[e["etapa"]]
        tarefas.setdefault(area, {"area": area, "documentos": []})["estado"] = "EM_ANDAMENTO"
        if e["etapa"] == "BANCOS":
            tarefas[area]["especialista"] = "BANCOS"
        return e["etapa"] + "_EM_ANDAMENTO"
    return "AGUARDANDO_SUPERVISOR"


def motivos_atuais(s: dict, *primeiros) -> list:
    """Resumo consolidado de todas as áreas: Conciliação, resultados da Contabilidade, falhas e pendências de Documentos."""
    resumos = s.get("resumos_etapas", {})
    itens = [m for m in primeiros if m]
    for e in ORDEM_RESUMOS:
        valor = resumos.get(e)
        itens += valor if isinstance(valor, list) else ([valor] if valor else [])
    itens += list(s.get("falhas_areas", {}).values()) + s.get("pendencias_documentos", [])
    return list(dict.fromkeys(itens))



def registrar_financeiro(sol: str, caminho_resultado: str) -> int:
    registro = ler_registro()
    s, erro = _sol_financeira(registro, sol, ("FINANCEIRO_EM_ANDAMENTO",))
    if erro is not None:
        return erro
    r = _resultado_da_sol(caminho_resultado, s, sol, "FINANCEIRO")
    if r is None:
        return recusar("RESULTADO_INVALIDO", "Resultado do Financeiro ilegível ou de outra SOL/empresa/competência.")
    fontes, motivo_fontes = conferir_fontes(caminho_resultado, s["empresa"], "FINANCEIRO")
    if motivo_fontes:
        return recusar("FONTES_ALTERADAS", motivo_fontes)
    execucao = {"em": agora().isoformat(), "resumo": r["resumo"], "fontes_sha256": fontes,
                "verificacao_extratos": [{"conta": v["conta"], "situacao": v["situacao"]} for v in r["verificacao_extratos"]],
                "resultado_sha256": hashlib.sha256(Path(caminho_resultado).read_bytes()).hexdigest()}
    s.setdefault("financeiro", []).append(execucao)
    tarefa_financeiro = s.setdefault('tarefas_areas', {}).setdefault('FINANCEIRO', {'area': 'FINANCEIRO', 'documentos': []})
    tarefa_financeiro.update(estado='BLOQUEADO' if r.get('bloqueio_lote') else 'ENTREGUE_COM_PENDENCIAS' if r['resumo']['pendencias'] else 'ENTREGUE',
                            retorno_em=execucao['em'], pendencias=r.get('pendencias', []))
    s.setdefault("falhas_areas", {}).pop("FINANCEIRO", None)
    resumos = s.setdefault("resumos_etapas", {})
    if r.get("bloqueio_lote"):
        # bloqueio do LOTE INTEIRO (competência, titularidade do lote, extrato essencial): Bancos não é acionado
        execucao["bloqueio_lote"] = r["bloqueio_lote"]
        marcar(s, "FINANCEIRO", "BLOQUEADA")
        resumos["FINANCEIRO"] = [f"BLOQUEIO_LOTE: {b}" for b in r["bloqueio_lote"]]
        s.update(etapa="FINANCEIRO_LOTE_BLOQUEADO", estado=avancar(s), motivos=motivos_atuais(s))
        s["eventos"].append({"em": execucao["em"], "evento": f"FINANCEIRO: lote bloqueado ({'; '.join(r['bloqueio_lote'])[:200]}); Bancos não acionado"})
        gravar_json(REGISTRO, registro)
        return saida({"resultado": "LOTE_BLOQUEADO", "sol": sol, "estado": s["estado"], "proximo_estagio": None,
                      "mensagem_supervisor": f"{sol}: lote bloqueado pelo Financeiro — {' '.join(r['bloqueio_lote'])}"})
    resumos.pop("FINANCEIRO", None)
    marcar(s, "FINANCEIRO", "CONCLUIDA")
    contab = s['tarefas_areas'].setdefault('CONTABILIDADE', {'area': 'CONTABILIDADE', 'documentos': []})
    contab.update(especialista='BANCOS', origem='FINANCEIRO', documentos=tarefa_financeiro['documentos'])
    if contab.get('estado') in (None, 'EM_ANDAMENTO'):
        contab['estado'] = 'PRONTO_PARA_ENCAMINHAMENTO'
    s.update(etapa="FINANCEIRO_CONCLUIDO", estado=avancar(s))
    s["eventos"].append({"em": execucao["em"], "evento": f"FINANCEIRO devolveu a conferência ao Coordenador ({r['resumo']['movimentos']} movimento(s), "
                         f"{r['resumo']['pendencias']} pendência(s)); encaminhada à Contabilidade/Bancos"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "FINANCEIRO_REGISTRADO", "sol": sol, "estado": s["estado"], "proximo_estagio": "CONTABILIDADE/BANCOS"})


AREAS_DOCUMENTAIS = {"FISCAL": ("FISCAL", "FISCAL_LOCAL_V1", "fiscal", None),
                     "CONTABILIDADE_FISCAL": ("CONTABILIDADE/FISCAL", "CONTABILIDADE_FISCAL_V1", "contabilfiscal", "FISCAL_SIMULACAO"),
                     "DP": ("DP", "DP_LOCAL_V1", "dp", None),
                     "CONTABILIDADE_DP": ("CONTABILIDADE/DP", "CONTABILIDADE_DP_V1", "contabdp", "DP_SIMULACAO")}


def registrar_area(sol, etapa, caminho_resultado):
    """Resultado do Fiscal, do DP ou dos especialistas Contabilidade/Fiscal e Contabilidade/DP (SIMULAÇÃO, nada escriturado)."""
    registro = ler_registro(); s = registro['solicitacoes'].get(sol)
    agente, contrato, chave, rotulo = AREAS_DOCUMENTAIS[etapa]
    if not s or s.get('estado') != etapa + '_EM_ANDAMENTO':
        return recusar('ESTADO_INVALIDO', f'Etapa {etapa} não está em andamento.')
    r = _resultado_da_sol(caminho_resultado, s, sol, agente)
    if not r or r.get('contrato') != contrato or r.get('modo') != 'SIMULACAO' or not isinstance(r.get('resumo'), dict):
        return recusar('RESULTADO_INVALIDO', f'Retorno de {agente} inválido ou de outra SOL/empresa/competência.')
    if rotulo and any(l.get('aprovado') or l.get('escriturado') for l in r.get('lancamentos', [])):
        return recusar('RESULTADO_INVALIDO', 'Resultado da Contabilidade não pode declarar lançamento aprovado ou escriturado.')
    fontes, motivo_fontes = conferir_fontes(caminho_resultado, s['empresa'], etapa)
    if motivo_fontes:
        return recusar('FONTES_ALTERADAS', motivo_fontes)
    momento = agora().isoformat()
    execucao = {'em': momento, 'resumo': r['resumo'], 'fontes_sha256': fontes,
                'resultado_sha256': hashlib.sha256(Path(caminho_resultado).read_bytes()).hexdigest()}
    if rotulo:
        execucao['fatos'] = fatos_do_resultado(r)
    s.setdefault(chave, []).append(execucao)
    s.setdefault('falhas_areas', {}).pop(etapa, None)
    marcar(s, etapa, 'CONCLUIDA')
    area = TAREFA_ETAPA[etapa]
    tarefa = s.setdefault('tarefas_areas', {}).setdefault(area, {'area': area, 'documentos': []})
    if rotulo:
        tarefa.update(estado='PROPOSTAS_PARCIAIS_AGUARDANDO_SUPERVISOR', retorno_em=momento, resumo=r['resumo'])
        s.setdefault('resumos_etapas', {})[etapa] = (f"{rotulo}: {r['resumo'].get('propostos', 0)} proposta(s) e "
                                                    f"{r['resumo'].get('incompletos', 0)} incompleta(s). Conferência humana; nada escriturado.")
        s['etapa'] = etapa + '_CONCLUIDO'
    else:
        tarefa.update(estado='ENTREGUE_COM_PENDENCIAS' if r.get('pendencias') else 'ENTREGUE', retorno_em=momento,
                      resumo=r['resumo'], pendencias=r.get('pendencias', []))
    s['estado'] = avancar(s)
    s['motivos'] = motivos_atuais(s)
    s['eventos'].append({'em': momento, 'evento': agente + ' entregou resultado em SIMULAÇÃO; sem escrituração ou liberação.'})
    gravar_json(REGISTRO, registro)
    return saida({'resultado': chave.upper() + '_REGISTRADO', 'sol': sol, 'estado': s['estado']})


def registrar_fiscal(sol, caminho_resultado, contabilidade=False):
    return registrar_area(sol, 'CONTABILIDADE_FISCAL' if contabilidade else 'FISCAL', caminho_resultado)


def registrar_conciliacao(sol, caminho_resultado):
    """Resultado da Conciliação: verificações e alcance; não corrige, não aprova, não libera."""
    registro = ler_registro(); s = registro['solicitacoes'].get(sol)
    if not s or s.get('estado') != 'CONCILIACAO_EM_ANDAMENTO':
        return recusar('ESTADO_INVALIDO', 'Etapa de Conciliação não está em andamento.')
    r = _resultado_da_sol(caminho_resultado, s, sol, 'CONCILIACAO')
    validos = {'CONFERIDO', 'DIVERGENTE', 'PENDENTE', 'NAO_APLICAVEL', 'NAO_DETERMINADO'}
    if (not r or r.get('contrato') != 'CONCILIACAO_V1' or r.get('modo') != 'SIMULACAO' or not isinstance(r.get('verificacoes'), list)
            or not isinstance(r.get('alcance'), dict) or any(v.get('resultado') not in validos for v in r['verificacoes'])):
        return recusar('RESULTADO_INVALIDO', 'Retorno da Conciliação inválido ou de outra SOL/empresa/competência.')
    fontes, motivo_fontes = conferir_fontes(caminho_resultado, s['empresa'], 'CONCILIACAO')
    if motivo_fontes:
        return recusar('FONTES_ALTERADAS', motivo_fontes)
    momento = agora().isoformat()
    contagem = {k: sum(1 for v in r['verificacoes'] if v['resultado'] == k) for k in validos}
    execucao = {'em': momento, 'tentativa': len(s.get('conciliacao', [])) + 1, 'resumo': r.get('resumo') or contagem,
                'alcance': r['alcance'], 'versoes_entradas': r.get('versoes_entradas', {}), 'fontes_sha256': fontes,
                'perguntas_supervisor': r.get('perguntas_supervisor', []),
                'resultado_sha256': hashlib.sha256(Path(caminho_resultado).read_bytes()).hexdigest()}
    s.setdefault('conciliacao', []).append(execucao)
    s.setdefault('falhas_areas', {}).pop('CONCILIACAO', None)
    marcar(s, 'CONCILIACAO', 'CONCLUIDA')
    com_pendencia = contagem['DIVERGENTE'] or contagem['PENDENTE'] or contagem['NAO_DETERMINADO'] or r['alcance'].get('parcial')
    s.setdefault('tarefas_areas', {})['CONCILIACAO'] = dict(s['tarefas_areas'].get('CONCILIACAO', {}), area='CONCILIACAO',
        estado='ENTREGUE_COM_PENDENCIAS' if com_pendencia else 'ENTREGUE', retorno_em=momento, resumo=contagem,
        alcance=r['alcance'])
    s.setdefault('resumos_etapas', {})['CONCILIACAO'] = (
        f"CONCILIACAO_SIMULACAO: {contagem['CONFERIDO']} conferida(s), {contagem['DIVERGENTE']} divergente(s), "
        f"{contagem['PENDENTE']} pendente(s), {contagem['NAO_APLICAVEL']} não aplicável(is)"
        + (f", {contagem['NAO_DETERMINADO']} com exigência não determinada" if contagem['NAO_DETERMINADO'] else '')
        + ('; alcance PARCIAL' if r['alcance'].get('parcial') else '') + '. Não aprova nem escritura.')
    s['escopo_resultado'] = 'SIMULACAO_CONCILIACAO_PARCIAL' if com_pendencia else 'SIMULACAO_CONCILIADA_NO_ALCANCE'
    s['estado'] = avancar(s)
    s['motivos'] = motivos_atuais(s)
    s['eventos'].append({'em': momento, 'evento': f"CONCILIAÇÃO entregou ao Coordenador: {s['resumos_etapas']['CONCILIACAO']}"})
    gravar_json(REGISTRO, registro)
    return saida({'resultado': 'CONCILIACAO_REGISTRADA', 'sol': sol, 'estado': s['estado'], 'resumo': contagem})


def registrar_bancos(sol: str, caminho_resultado: str) -> int:
    registro = ler_registro()
    s, erro = _sol_financeira(registro, sol, ("BANCOS_EM_ANDAMENTO",))
    if erro is not None:
        return erro
    r = _resultado_da_sol(caminho_resultado, s, sol, "CONTABILIDADE/BANCOS")
    if r is None:
        return recusar("RESULTADO_INVALIDO", "Resultado de Contabilidade/Bancos ilegível ou de outra SOL/empresa/competência.")
    fontes, motivo_fontes = conferir_fontes(caminho_resultado, s["empresa"], "BANCOS")
    if motivo_fontes:
        return recusar("FONTES_ALTERADAS", motivo_fontes)
    execucao = {"em": agora().isoformat(), "resumo": r["resumo"], "fontes_sha256": fontes, "fatos": fatos_do_resultado(r),
                # PROPOSTA em SIMULAÇÃO (não é escrituração efetiva): usada para rastrear revisões, nunca para bloquear
                "movimentos_propostos_simulacao": sorted({m for l in r["lancamentos"] for m in l["movimentos"]}),
                "resultado_sha256": hashlib.sha256(Path(caminho_resultado).read_bytes()).hexdigest()}
    s.setdefault("bancos", []).append(execucao)
    motivo = (f"CONFERENCIA_HUMANA_SIMULACAO: {r['resumo']['propostos']} lançamento(s) proposto(s), {r['resumo']['incompletos']} "
              f"incompleto(s) e {r['resumo']['pendencias']} pendência(s). Nada é liberado nem importado sem aprovação do Supervisor.")
    s.setdefault("falhas_areas", {}).pop("BANCOS", None)
    s.setdefault("resumos_etapas", {})["BANCOS"] = motivo
    marcar(s, "BANCOS", "CONCLUIDA")
    s.setdefault('tarefas_areas', {}).setdefault('CONTABILIDADE', {'area': 'CONTABILIDADE', 'documentos': []}).update(
        estado='PROPOSTAS_PARCIAIS_AGUARDANDO_SUPERVISOR', especialista='BANCOS', retorno_em=execucao['em'])
    if not etapa_do_plano(s, "CONCILIACAO"):
        s['tarefas_areas']['CONCILIACAO'] = {**s['tarefas_areas'].get('CONCILIACAO', {'documentos': []}), 'area': 'CONCILIACAO', 'estado': 'NAO_EXECUTADA',
                                             'motivo': 'Solicitação sem pacote local de Documentos: a Conciliação não foi acionada.'}
    s.update(etapa="BANCOS_CONCLUIDO", estado=avancar(s), motivos=motivos_atuais(s))
    s["eventos"].append({"em": execucao["em"], "evento": f"CONTABILIDADE/BANCOS devolveu a escrituração (SIMULAÇÃO) ao Coordenador: {motivo}"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "BANCOS_REGISTRADO", "sol": sol, "estado": s["estado"], "execucao": execucao,
                  "mensagem_supervisor": f"{sol}: escrituração bancária em SIMULAÇÃO pronta para a sua conferência. {motivo}"})


def impedimentos_aprovacao(s: dict, registro: dict = None, ciente_exportados: bool = False) -> list:
    """Motivos que impedem aprovar o fechamento (vazio = pode aprovar). Só se aprova o que foi conferido por inteiro, com as
    fontes vigentes e sem repetir fatos já aprovados em outra SOL. Aprovação parcial não existe nesta versão."""
    faltas = []
    if s.get('estado') != 'AGUARDANDO_SUPERVISOR':
        faltas.append('A solicitação não está aguardando o Supervisor.')
    if not s.get('ancora_documentos') or 'plano_etapas' not in s:
        faltas.append('Solicitação sem pacote local com âncora de integridade (anterior a esta versão).')
        return faltas
    for e in plano_de(s):
        if e['situacao'] != 'CONCLUIDA':
            faltas.append(f"Etapa {e['etapa']} não concluída ({e['situacao']}).")
    if not etapa_do_plano(s, 'CONCILIACAO'):
        faltas.append('Conciliação não faz parte desta solicitação.')
    for chave, nome in (('bancos', 'Bancos'), ('contabdp', 'Contabilidade/DP'), ('contabilfiscal', 'Contabilidade/Fiscal')):
        if s.get(chave) and (s[chave][-1].get('resumo') or {}).get('incompletos'):
            faltas.append(f"{nome}: há lançamento(s) incompleto(s).")
    conc = (s.get('conciliacao') or [None])[-1]
    if conc:
        resumo = {k.upper(): v for k, v in (conc.get('resumo') or {}).items()}
        if resumo.get('DIVERGENTE'):
            faltas.append(f"Conciliação com {resumo['DIVERGENTE']} verificação(ões) divergente(s).")
        if resumo.get('PENDENTE'):
            faltas.append(f"Conciliação com {resumo['PENDENTE']} verificação(ões) pendente(s).")
        if resumo.get('NAO_DETERMINADO'):
            faltas.append(f"Conciliação com {resumo['NAO_DETERMINADO']} verificação(ões) de exigência NÃO DETERMINADA: responda às "
                          "perguntas ao Supervisor (regras da empresa) e reexecute a Conciliação; não há fechamento integral.")
        if (conc.get('alcance') or {}).get('parcial'):
            faltas.append('Conciliação com alcance parcial.')
        v = vigencia(s, conc)
        if not v['vigente']:
            faltas.append('Conciliação desatualizada: ' + ' '.join(v['motivos']) + ' Rever: ' + ', '.join(v['rever']) + '.')
    if registro is not None and s.get('sol') in registro.get('solicitacoes', {}):
        for rel in relacao_outras_sols(registro, s['sol']):
            if rel['classificacao'] in ('REPETICAO_DE_APROVADA', 'SUBSTITUICAO_DE_APROVADA', 'SEM_IDENTIDADES'):
                faltas.append(f"Duplicação: {rel['texto']}")
            elif rel['classificacao'] == 'FATOS_JA_EXPORTADOS' and not ciente_exportados:
                faltas.append(f"Fatos já exportados: {rel['texto']} Confirme a ciência na aprovação.")
    return list(dict.fromkeys(faltas))


def aprovar_fechamento(sol, acao, frase, justificativa, ciente_exportados=False):
    """Aprovação EXPLÍCITA do Supervisor (SIMULAÇÃO) do fechamento conferido por inteiro. Não escritura. O TXT do Domínio é gerado
    depois, pela API, só para empresa fictícia (produção bloqueada). Revogar não estorna importação já feita no Domínio."""
    registro = ler_registro(); s = registro['solicitacoes'].get(sol)
    if not s:
        return recusar('SOL_DESCONHECIDA', f'{sol} não foi aberta por este Coordenador.')
    if not isinstance(justificativa, str) or not 5 <= len(justificativa.strip()) <= 500 or '|' in justificativa:
        return recusar('PARAMETROS_INVALIDOS', 'Informe justificativa de 5 a 500 caracteres.')
    momento = agora().isoformat()
    if acao == 'revogar':
        if s.get('estado') != 'FECHAMENTO_APROVADO':
            return recusar('ESTADO_INVALIDO', 'Não há aprovação vigente para revogar.')
        anterior = dict(s.pop('aprovacao'), revogada_em=momento, motivo_revogacao=justificativa.strip())
        s.setdefault('aprovacoes_anteriores', []).append(anterior)
        s['estado'] = 'AGUARDANDO_SUPERVISOR'
        s['eventos'].append({'em': momento, 'evento': f'Supervisor revogou a aprovação do fechamento: {justificativa.strip()[:120]}. '
                                                      'Download do TXT bloqueado; revogar no aplicativo não estorna importação já feita no Domínio.'})
        gravar_json(REGISTRO, registro)
        return saida({'resultado': 'APROVACAO_REVOGADA', 'sol': sol, 'estado': s['estado'],
                      'liberacao_anterior': anterior.get('liberacao_dominio'), 'arquivo_txt': anterior.get('arquivo_txt')})
    esperado = f'APROVO FECHAMENTO {sol}'
    if (frase or '').strip() != esperado:
        return recusar('APROVACAO_INVALIDA', f'Aprovação exige a frase exata: "{esperado}".')
    s.setdefault('sol', sol)
    faltas = impedimentos_aprovacao(s, registro, ciente_exportados)
    if faltas:
        return recusar('APROVACAO_IMPEDIDA', 'Não é possível aprovar: ' + ' '.join(faltas))
    conc = s['conciliacao'][-1]
    relacao = relacao_outras_sols(registro, sol)
    s['aprovacao'] = {'em': momento, 'por': 'Supervisor Contábil', 'frase': esperado, 'justificativa': justificativa.strip(),
                      'escopo': 'SIMULACAO', 'tipo': 'FECHAMENTO_INTEGRAL_CONCILIADO', 'conciliacao_tentativa': conc.get('tentativa'),
                      'conciliacao_sha256': conc.get('resultado_sha256'), 'versoes_aprovadas': conc.get('versoes_entradas'),
                      'fontes_aprovadas': fontes_atuais(s['empresa']), 'fatos_aprovados': fatos_da_sol(s) or {},
                      'conferidas_por_evidencia': (conc.get('resumo') or {}).get('conferidas_por_evidencia'),
                      'relacao_outras_sols': [{k: r.get(k) for k in ('sol', 'estado', 'classificacao', 'texto')} for r in relacao],
                      'ciente_fatos_ja_exportados': bool(ciente_exportados and any(r['classificacao'] == 'FATOS_JA_EXPORTADOS' for r in relacao)),
                      'escrituracao': 'NAO_REALIZADA', 'importacao_dominio': 'NAO_REGISTRADA_PELO_APLICATIVO',
                      'liberacao_dominio': 'AGUARDANDO_GERACAO_TXT', 'tentativas_exportacao': []}
    s['estado'] = 'FECHAMENTO_APROVADO'
    s['eventos'].append({'em': momento, 'evento': 'Supervisor APROVOU o fechamento conferido por inteiro (SIMULAÇÃO). Nada foi escriturado; '
                                                  'a importação no Domínio é sempre manual.'})
    gravar_json(REGISTRO, registro)
    return saida({'resultado': 'FECHAMENTO_APROVADO', 'sol': sol, 'estado': s['estado']})


SITUACOES_LIBERACAO = ('PREPARANDO', 'LIBERADO_PARA_IMPORTACAO_MANUAL', 'BLOQUEADA_PRODUCAO', 'FALHOU', 'REVOGADO')
PODE_GERAR = ('AGUARDANDO_GERACAO_TXT', 'FALHOU')


def registrar_liberacao(sol, situacao, arquivo='', sha256='', linhas='0', total='0', motivo='', movimentacao='', auditoria='', anexos=''):
    """Situação do TXT do Domínio depois da aprovação (nunca é importação nem escrituração):
    PREPARANDO (fase 1: arquivo e sha anunciados ANTES de gravar) → LIBERADO_PARA_IMPORTACAO_MANUAL (fase 2: mesmo arquivo e sha);
    FALHOU (nada liberado; nova geração só por ação explícita do Supervisor); BLOQUEADA_PRODUCAO (empresa real nesta versão);
    REVOGADO (aprovação revogada; movimentacao RENOMEADO | FALHOU | SEM_ARQUIVO informa o que aconteceu com o arquivo)."""
    registro = ler_registro(); s = registro['solicitacoes'].get(sol)
    if not s:
        return recusar('SOL_DESCONHECIDA', f'{sol} não foi aberta por este Coordenador.')
    momento = agora().isoformat()
    if situacao == 'REVOGADO':
        alvo = (s.get('aprovacoes_anteriores') or [None])[-1]
        if not alvo or s.get('estado') == 'FECHAMENTO_APROVADO':
            return recusar('ESTADO_INVALIDO', 'Nenhuma aprovação revogada para registrar a situação do arquivo.')
        if movimentacao not in ('RENOMEADO', 'FALHOU', 'SEM_ARQUIVO'):
            return recusar('PARAMETROS_INVALIDOS', 'Informe a movimentação do arquivo (RENOMEADO, FALHOU ou SEM_ARQUIVO).')
        alvo['liberacao_dominio'] = 'REVOGADO' if movimentacao != 'FALHOU' else 'REVOGADO_ARQUIVO_NAO_MOVIDO'
        alvo.setdefault('movimentacoes_revogacao', []).append({'em': momento, 'movimentacao': movimentacao, 'arquivo': arquivo,
                                                               'motivo': motivo[:300]})
        if movimentacao == 'RENOMEADO':
            alvo['arquivo_revogado'] = arquivo
        texto = {'RENOMEADO': f'TXT da aprovação revogada renomeado como REVOGADO ({arquivo}); download bloqueado.',
                 'SEM_ARQUIVO': 'Aprovação revogada sem TXT liberado a mover.',
                 'FALHOU': f'ATENÇÃO: aprovação revogada, mas o arquivo NÃO pôde ser renomeado ({arquivo}): {motivo[:160]}. Download '
                           'bloqueado; não importe esse arquivo; renomeie manualmente ou tente de novo.'}[movimentacao]
    else:
        if s.get('estado') != 'FECHAMENTO_APROVADO' or not s.get('aprovacao'):
            return recusar('ESTADO_INVALIDO', 'Liberação só depois da aprovação explícita do fechamento.')
        ap = s['aprovacao']
        atual = ap.get('liberacao_dominio')
        if situacao == 'PREPARANDO':
            if atual not in PODE_GERAR or not arquivo or not re.fullmatch(r'[0-9a-f]{64}', sha256 or ''):
                return recusar('ESTADO_INVALIDO', f'Geração do TXT não permitida na situação {atual} (sem repetição automática).')
            try:
                anexos_d = json.loads(anexos) if anexos else {}
            except ValueError:
                return recusar('PARAMETROS_INVALIDOS', 'Anexos da liberação ilegíveis.')
            if any(not isinstance(v, dict) or not v.get('arquivo') or not re.fullmatch(r'[0-9a-f]{64}', str(v.get('sha256')))
                   for v in anexos_d.values()):
                return recusar('PARAMETROS_INVALIDOS', 'Cada anexo exige arquivo e sha256.')
            ap.setdefault('tentativas_exportacao', []).append({'n': len(ap.get('tentativas_exportacao', [])) + 1, 'em': momento,
                                                               'arquivo': arquivo, 'sha256': sha256, 'auditoria': auditoria,
                                                               'anexos': anexos_d, 'situacao': 'PREPARANDO'})
            ap.update(liberacao_dominio='PREPARANDO', liberacao_em=momento)
            texto = f'Geração do TXT iniciada (arquivo {arquivo}); ainda não liberado.'
        elif situacao == 'LIBERADO_PARA_IMPORTACAO_MANUAL':
            t = (ap.get('tentativas_exportacao') or [None])[-1]
            try:
                anexos_d = json.loads(anexos) if anexos else {}
            except ValueError:
                anexos_d = None
            if atual != 'PREPARANDO' or not t or (t['arquivo'], t['sha256'], t.get('anexos') or {}) != (arquivo, sha256, anexos_d):
                return recusar('ESTADO_INVALIDO', 'Liberação recusada: arquivos/sha256 diferentes dos anunciados na preparação.')
            t['situacao'] = 'LIBERADO'
            ap.update(liberacao_dominio=situacao, liberacao_em=momento, arquivo_txt=arquivo, txt_sha256=sha256, txt_linhas=int(linhas),
                      txt_total=total, txt_auditoria=t.get('auditoria'), anexos=anexos_d,
                      fatos_exportados=dict(ap.get('fatos_aprovados') or {}))
            ap.pop('liberacao_motivo', None)
            texto = (f'TXT para o Domínio liberado em {arquivo} ({linhas} linha(s), total {total}); importação MANUAL pelo Supervisor. '
                     'Exportado não significa importado nem escriturado.')
        elif situacao == 'FALHOU':
            if atual not in ('AGUARDANDO_GERACAO_TXT', 'PREPARANDO', 'FALHOU'):
                return recusar('ESTADO_INVALIDO', f'Falha de geração não se aplica à situação {atual}.')
            t = (ap.get('tentativas_exportacao') or [None])[-1]
            if t and t.get('situacao') == 'PREPARANDO':
                t.update(situacao='FALHOU', motivo=motivo[:300], arquivo_residual=arquivo or None)
            ap.update(liberacao_dominio='FALHOU', liberacao_em=momento, liberacao_motivo=motivo[:300])
            texto = f'TXT não liberado: {motivo[:200]}' + (f' (arquivo preservado fora de uso: {arquivo})' if arquivo else '')
        elif situacao == 'BLOQUEADA_PRODUCAO':
            if atual not in PODE_GERAR:
                return recusar('ESTADO_INVALIDO', f'Bloqueio não se aplica à situação {atual}.')
            ap.update(liberacao_dominio=situacao, liberacao_em=momento, liberacao_motivo=motivo[:300] or None)
            texto = 'TXT não liberado: produção bloqueada nesta versão para empresa real (aprovação registrada).'
        else:
            return recusar('PARAMETROS_INVALIDOS', f'Situação {situacao} desconhecida.')
    s['eventos'].append({'em': momento, 'evento': texto})
    gravar_json(REGISTRO, registro)
    return saida({'resultado': 'LIBERACAO_REGISTRADA', 'sol': sol, 'situacao': situacao})


def revisar_piloto(sol, acao, justificativa):
    """Encerra/reabre revisão parcial sem aprovar ou resolver pendências."""
    registro = ler_registro(); s = registro['solicitacoes'].get(sol)
    if not s or (s.get('fluxo') != 'FINANCEIRO_BANCOS' and not s.get('contabilfiscal') and not s.get('plano_etapas')):
        return recusar('SOL_INVALIDA', 'Revisão parcial disponível somente para o piloto Financeiro/Bancos.')
    if ORDEM_ATIVA.exists(): return recusar('ORDEM_ATIVA', 'Há uma ordem ativa; aguarde o término.')
    if acao not in ('encerrar', 'reabrir') or not isinstance(justificativa, str) or not 5 <= len(justificativa.strip()) <= 500:
        return recusar('PARAMETROS_INVALIDOS', 'Informe ação e justificativa de 5 a 500 caracteres.')
    esperado = 'AGUARDANDO_SUPERVISOR' if acao == 'encerrar' else 'ENCERRADA'
    if s.get('estado') != esperado or (acao == 'reabrir' and not s.get('revisao_parcial_encerrada')):
        return recusar('ESTADO_INVALIDO', 'A solicitação não está disponível para esta ação.')
    s.update(estado='ENCERRADA' if acao == 'encerrar' else 'AGUARDANDO_SUPERVISOR', revisao_parcial_encerrada=acao == 'encerrar')
    # o escopo informado pela Conciliação (quando houve) é preservado; revisão parcial nunca vira fechamento aprovado
    if not s.get('conciliacao'):
        s['escopo_resultado'] = 'PARCIAL_PILOTO_SEM_CONCILIACAO'
    evento = {'em': agora().isoformat(), 'acao': acao, 'justificativa': justificativa.strip(),
              'escopo': 'REVISAO_PARCIAL_PILOTO', 'escrituracao_aprovada': False}
    s.setdefault('revisoes_piloto', []).append(evento)
    s['eventos'].append({'em': evento['em'], 'evento': f"Revisão parcial do piloto: {acao}. Pendências preservadas; sem aprovação de escrituração ou fechamento integral."})
    gravar_json(REGISTRO, registro)
    return saida({'resultado': 'REVISAO_PILOTO_REGISTRADA', 'estado': s['estado'], 'sol': sol, 'escopo': evento['escopo']})


def registrar_falha_etapa(sol: str, etapa: str, motivo: str) -> int:
    """Falha de uma etapa: registrada e preservada, sem repetição automática; as áreas independentes seguem."""
    registro = ler_registro()
    s = registro['solicitacoes'].get(sol)
    if not s or s.get('estado') != etapa + '_EM_ANDAMENTO':
        return recusar('ESTADO_INVALIDO', f'A etapa {etapa} não está em andamento nesta SOL.')
    momento = agora().isoformat()
    falha = f"FALHA_{etapa}: {motivo[:300]}"
    s.setdefault("falhas_areas", {})[etapa] = falha
    marcar(s, etapa, "FALHOU")
    area = TAREFA_ETAPA[etapa]
    s.setdefault("tarefas_areas", {}).setdefault(area, {"area": area, "documentos": []}).update(estado="FALHOU", falha_em=momento)
    s["estado"] = avancar(s)
    s["motivos"] = [falha] + [m for m in motivos_atuais(s) if m != falha]
    s["eventos"].append({"em": momento, "evento": f"Falha na etapa {etapa}: {motivo[:300]} (tentativa preservada; sem repetição automática; "
                                                   "áreas independentes seguem)"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "FALHA_REGISTRADA", "sol": sol, "estado": s["estado"]})


def retomar_area(sol: str, etapa: str, justificativa: str) -> int:
    """Nova tentativa AUTORIZADA da etapa que falhou, sobre o MESMO pacote íntegro: reexecuta a etapa, os dependentes e a
    Conciliação; resultados válidos das demais áreas e todas as tentativas anteriores são preservados."""
    registro = ler_registro()
    s = registro['solicitacoes'].get(sol)
    if s is None:
        return recusar("SOL_DESCONHECIDA", f"{sol} não foi aberta por este Coordenador.")
    if s.get('estado') != 'AGUARDANDO_SUPERVISOR':
        return recusar('ESTADO_INVALIDO', 'Retomada só com a SOL aguardando o Supervisor (sem processamento e sem revisão encerrada).')
    if ORDEM_ATIVA.exists():
        return recusar('ORDEM_ATIVA', 'Há uma ordem ativa; aguarde o término.')
    if not isinstance(justificativa, str) or not 5 <= len(justificativa.strip()) <= 500 or '|' in justificativa:
        return recusar('PARAMETROS_INVALIDOS', 'Informe justificativa de 5 a 500 caracteres.')
    if 'plano_etapas' not in s or not s.get('ancora_documentos'):
        return recusar('SEM_ANCORA', 'SOL anterior a esta versão ou sem âncora de integridade: a etapa não é retomada sobre este pacote '
                                     '(nenhuma integridade retroativa é fabricada). Abra nova solicitação.')
    e = etapa_do_plano(s, etapa)
    desatualizada = bool(e and e['situacao'] == 'CONCLUIDA' and s.get('conciliacao') and etapa in vigencia(s)['rever'])
    if not e or (e['situacao'] != 'FALHOU' and not desatualizada):
        return recusar('NAO_PERMITIDO', 'Somente etapa que FALHOU, ou etapa DESATUALIZADA por alteração de fonte (cadastro, plano, regras), '
                                        'pode ser retomada. Bloqueio de lote ou dependência se resolve na etapa de origem ou com nova '
                                        'solicitação (mudança de empresa, competência ou documentos).')
    reabertas = reabrir(s, list(dict.fromkeys([etapa, *DEPENDENTES.get(etapa, ()), 'CONCILIACAO'])))
    momento = agora().isoformat()
    s.setdefault('retomadas', []).append({'em': momento, 'etapa': etapa, 'justificativa': justificativa.strip(), 'reexecuta': reabertas})
    s['estado'] = avancar(s)
    s['eventos'].append({'em': momento, 'evento': f"Supervisor autorizou nova tentativa de {etapa} ({justificativa.strip()[:120]}); "
                                                  f"reexecuta {', '.join(reabertas)}; tentativas anteriores preservadas"})
    gravar_json(REGISTRO, registro)
    return saida({'resultado': 'RETOMADA_REGISTRADA', 'sol': sol, 'estado': s['estado'], 'reexecuta': reabertas})


def registrar_decisao_movimento(sol: str, movimento: str, tipo: str, dados: str, justificativa: str) -> int:
    """Decisão do Supervisor para UM movimento (vale só para ele; nunca vira regra sozinha). A SOL volta ao Financeiro
    para nova tentativa; as anteriores ficam preservadas."""
    registro = ler_registro()
    s, erro = _sol_financeira(registro, sol, ("AGUARDANDO_SUPERVISOR",))
    if erro is not None:
        return erro
    try:
        d = json.loads(dados)
    except json.JSONDecodeError:
        d = None
    if not re.fullmatch(r"MOV-[0-9A-F]{12}", movimento) or tipo not in ("VINCULAR", "CONTRAPARTIDA") or not isinstance(d, dict) \
            or not 5 <= len(justificativa.strip()) <= 500 or "|" in justificativa:
        return recusar("PARAMETROS_INVALIDOS", "Movimento, tipo (VINCULAR/CONTRAPARTIDA), dados ou justificativa (5 a 500 caracteres) inválidos.")
    if tipo == "VINCULAR":
        vinculos = d.get("vinculos")
        if set(d) != {"vinculos"} or not isinstance(vinculos, list) or not vinculos or not all(isinstance(v, str) and re.fullmatch(r"(DOC|REL)-[0-9A-F]{12}", v) for v in vinculos):
            return recusar("PARAMETROS_INVALIDOS", "VINCULAR exige a lista de documentos/itens da relação (DOC-…/REL-…).")
        decisao = {"tipo": tipo, "vinculos": vinculos}
    else:
        conta = re.sub(r"\D", "", str(d.get("conta", "")))
        if set(d) - {"conta", "natureza_tipo", "historico"} or d.get("natureza_tipo") not in TIPOS_LANCAMENTO:
            return recusar("PARAMETROS_INVALIDOS", f"CONTRAPARTIDA exige conta e natureza_tipo ({', '.join(TIPOS_LANCAMENTO)}).")
        problema = compatibilidade(s["empresa"], conta, d["natureza_tipo"])
        if problema:
            return recusar(*problema)
        historico = str(d.get("historico") or "")[:120]
        if "|" in historico:
            return recusar("PARAMETROS_INVALIDOS", "Histórico não pode conter '|'.")
        decisao = {"tipo": tipo, "conta": conta, "natureza_tipo": d["natureza_tipo"], "historico": historico}
    momento = agora().isoformat()
    decisao.update(justificativa=justificativa.strip(), em=momento, escopo="somente este movimento")
    s.setdefault("decisoes_movimentos", {}).setdefault(movimento, []).append(decisao)
    reabrir(s, ["FINANCEIRO", "BANCOS", "CONCILIACAO"])
    s["estado"] = avancar(s)
    s["eventos"].append({"em": momento, "evento": f"Supervisor: decisão {tipo} para {movimento} (somente este caso); nova tentativa Financeiro → Bancos"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "DECISAO_REGISTRADA", "sol": sol, "movimento": movimento, "estado": s["estado"]})


def _arquivo_regras(empresa: str) -> Path:
    return CLIENTES / empresa / "REGRAS-BANCOS.md"


def _linhas_regras(texto: str) -> list:
    """(índice da linha, células) das regras da tabela '## Regras'."""
    saida_, dentro = [], False
    for i, l in enumerate(texto.splitlines()):
        if l.startswith("## "):
            dentro = normalizar(l).startswith("## REGRAS")
            continue
        if dentro and l.strip().startswith("|"):
            celulas = [c.strip() for c in l.strip().strip("|").split("|")]
            if re.fullmatch(r"RB-\d{3}", celulas[0]):
                saida_.append((i, celulas))
    return saida_


def propor_regra_bancos(sol: str, dados: str) -> int:
    """Proposta de regra a partir de um caso decidido. Fica PROPOSTA (não é usada) até a aprovação explícita."""
    registro = ler_registro()
    s, erro = _sol_financeira(registro, sol, ("AGUARDANDO_SUPERVISOR",))
    if erro is not None:
        return erro
    try:
        d = json.loads(dados)
    except json.JSONDecodeError:
        return recusar("PARAMETROS_INVALIDOS", "Dados da regra inválidos.")
    campos = {"condicoes", "tipo", "contrapartida", "exige_suporte", "historico", "movimento"}
    if not isinstance(d, dict) or set(d) != campos or any("|" in str(v) or "\n" in str(v) for v in d.values()):
        return recusar("PARAMETROS_INVALIDOS", f"Envie exatamente {', '.join(sorted(campos))} (sem '|' ou quebra de linha).")
    pares = [p.strip() for p in str(d["condicoes"]).split(";") if p.strip()]
    if not pares or any("=" not in p or p.split("=", 1)[0].strip() not in CHAVES_CONDICAO or not p.split("=", 1)[1].strip() for p in pares):
        return recusar("PARAMETROS_INVALIDOS", f"Condições no formato 'chave=valor; …' com chaves {', '.join(CHAVES_CONDICAO)}.")
    conta = re.sub(r"\D", "", str(d["contrapartida"]))
    for par in pares:
        k, v = (x.strip() for x in par.split('=', 1))
        if k == 'competencia_desde' and not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', v):
            return recusar('PARAMETROS_INVALIDOS', 'competencia_desde deve ser AAAA-MM válido.')
    if d["tipo"] not in TIPOS_LANCAMENTO or d["exige_suporte"] not in ("SIM", "NAO"):
        return recusar("PARAMETROS_INVALIDOS", f"Tipo ({', '.join(TIPOS_LANCAMENTO)}) ou exige_suporte (SIM/NAO) inválido.")
    if d['tipo'].startswith('ADIANTAMENTO_'):
        return recusar('AUTOMATISMO_REMOVIDO', 'Regras automáticas de adiantamento foram removidas. Use decisão específica do movimento.')
    problema = compatibilidade(s["empresa"], conta, d["tipo"])
    if problema:
        return recusar(*problema)
    arquivo = _arquivo_regras(s["empresa"])
    texto = arquivo.read_text(encoding="utf-8") if arquivo.exists() else (
        f"# REGRAS DE LANÇAMENTOS BANCÁRIOS - {s['empresa']}\nSomente regras VALIDADAS são usadas pela Contabilidade/Bancos.\n\n"
        f"## Regras\n{CABECALHO_REGRAS}\n|---|---|---|---|---|---|---|---|---|---|\n")
    existentes = _linhas_regras(texto)
    numero = max([int(c[0][3:]) for _, c in existentes] + [0]) + 1
    regra = f"RB-{numero:03d}"
    momento = agora()
    linha = (f"| {regra} | 1 | {'; '.join(pares)} | {d['tipo']} | {conta} | {d['exige_suporte']} | {d['historico'][:120]} | "
             f"Proposta do Supervisor a partir da {sol}, movimento {d['movimento']} ({momento.date().isoformat()}) | PROPOSTA | — |")
    linhas = texto.splitlines()
    fim_tabela = (existentes[-1][0] if existentes else next(i for i, l in enumerate(linhas) if l.startswith("|---"))) + 1
    linhas.insert(fim_tabela, linha)
    gravar_texto(arquivo, "\n".join(linhas) + "\n")
    s["eventos"].append({"em": momento.isoformat(), "evento": f"Supervisor propôs a regra {regra} (PROPOSTA; não é usada até ser aprovada)"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "REGRA_PROPOSTA", "sol": sol, "regra": regra, "situacao": "PROPOSTA",
                  "frase_de_aprovacao": f"VALIDADO REGRA {s['empresa']} {regra}"})


def aprovar_regra_bancos(sol: str, regra: str, frase: str) -> int:
    registro = ler_registro()
    s, erro = _sol_financeira(registro, sol, ("AGUARDANDO_SUPERVISOR",))
    if erro is not None:
        return erro
    esperado = f"VALIDADO REGRA {s['empresa']} {regra}"
    if frase.strip() != esperado:
        return recusar("APROVACAO_INVALIDA", f"Aprovação exige a frase exata: \"{esperado}\".")
    arquivo = _arquivo_regras(s["empresa"])
    texto = arquivo.read_text(encoding="utf-8") if arquivo.exists() else ""
    alvo = next(((i, c) for i, c in _linhas_regras(texto) if c[0] == regra), None)
    if alvo is None or normalizar(alvo[1][8]) != "PROPOSTA":
        return recusar("NAO_PERMITIDO", f"{regra} não existe ou não está PROPOSTA.")
    i, c = alvo
    if c[3].startswith('ADIANTAMENTO_'):
        return recusar('AUTOMATISMO_REMOVIDO', 'Esta regra automática de adiantamento não pode ser reativada; use decisão específica do movimento.')
    momento = agora()
    sys.path.insert(0, str(RAIZ / "AGENTES" / "CONTABILIDADE"))
    import governanca_regras as gov
    c[8], c[9] = "VALIDADA", gov.texto_confirmacao_bancos(s["empresa"], regra, c[1], momento.isoformat())
    linhas = texto.splitlines()
    linhas[i] = "| " + " | ".join(c) + " |"
    gravar_texto(arquivo, "\n".join(linhas) + "\n")
    reabrir(s, ["FINANCEIRO", "BANCOS", "CONCILIACAO"])
    s["estado"] = avancar(s)
    s["eventos"].append({"em": momento.isoformat(), "evento": f"Supervisor aprovou a regra {regra} ({esperado}); nova tentativa Financeiro → Bancos"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "REGRA_APROVADA", "sol": sol, "regra": regra, "estado": s["estado"]})


def aprovar_regra_area(empresa: str, area: str, chave: str, frase: str) -> int:
    """Confirmação EXPLÍCITA do Supervisor de UMA referência (DP, FISCAL ou CONCILIACAO) em situação REFERENCIA ou PROPOSTA.
    Grava APROVADA com {frase, em, por}; versão anterior do arquivo preservada em VERSOES/. Nunca aprova regra de teste fictício."""
    sys.path.insert(0, str(RAIZ / "AGENTES" / "CONTABILIDADE"))
    import governanca_regras as gov
    if area not in (*gov.AREAS, "BANCOS") or not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]*", chave or "") or empresa not in empresas_cadastradas():
        return recusar("PARAMETROS_INVALIDOS", "Empresa, área (BANCOS, DP, FISCAL, CONCILIACAO) ou chave inválida.")
    esperado = gov.frase(area, empresa, chave)
    if (frase or "").strip() != esperado:
        return recusar("APROVACAO_INVALIDA", f'Confirmação exige a frase exata: "{esperado}".')
    if area == "BANCOS":
        return _confirmar_regra_bancos(empresa, chave, esperado, gov)
    arquivo = CLIENTES / empresa / gov.AREAS[area]
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return recusar("NAO_PERMITIDO", f"{arquivo.name} ausente ou ilegível: nada a confirmar.")
    grupo = dados.get("exigencias" if area == "CONCILIACAO" else "referencias") or {}
    regra = dados.get("data_lancamento") if chave == "DATA_LANCAMENTO" and area != "CONCILIACAO" else grupo.get(chave)
    situacao = str((regra or {}).get("situacao") or "REFERENCIA").upper()
    if not isinstance(regra, dict) or situacao not in ("REFERENCIA", "PROPOSTA"):
        return recusar("NAO_PERMITIDO", f"{chave} não existe ou não está em REFERENCIA/PROPOSTA (situação {situacao}).")
    if not str(regra.get("origem") or regra.get("fonte") or "").strip():
        return recusar("NAO_PERMITIDO", f"{chave} sem origem documentada: registre a origem antes de confirmar.")
    if chave == "DATA_LANCAMENTO" and str(regra.get("politica") or "").upper() in gov.POLITICAS_NAO_SUPORTADAS:
        return recusar("NAO_PERMITIDO", "Política de data indisponível nesta versão: "
                       + gov.POLITICAS_NAO_SUPORTADAS[str(regra.get("politica")).upper()] + ". Nada foi confirmado.")
    momento = agora()
    _preservar_versao(arquivo, empresa, momento)
    regra.setdefault("historico_situacoes", []).append({"de": situacao, "para": "APROVADA", "em": momento.isoformat()})
    regra.update(situacao="APROVADA", versao=int(regra.get("versao") or 0) + 1,
                 confirmacao={"frase": esperado, "em": momento.isoformat(), "por": "Supervisor Contábil"})
    gravar_texto(arquivo, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")
    return saida({"resultado": "REGRA_CONFIRMADA", "empresa": empresa, "area": area, "chave": chave, "versao": regra["versao"],
                  "aviso": "Conciliações e aprovações que usaram a versão anterior ficam desatualizadas (rever as etapas indicadas)."})


def _preservar_versao(arquivo: Path, empresa: str, momento) -> None:
    (CLIENTES / empresa / "VERSOES").mkdir(parents=True, exist_ok=True)
    n = 1
    while True:                                                   # versão anterior preservada; nome exclusivo, nunca sobrescreve
        copia = CLIENTES / empresa / "VERSOES" / f"{arquivo.stem}-{momento:%Y%m%d-%H%M%S}-{n:03d}{arquivo.suffix}"
        try:
            with open(copia, "xb") as f:
                f.write(arquivo.read_bytes())
            return
        except FileExistsError:
            n += 1


def _confirmar_regra_bancos(empresa, regra, esperado, gov) -> int:
    """Confirmação do Supervisor de UMA regra bancária PROPOSTA, ou VALIDADA sem confirmação suficiente (texto livre ou formato
    anterior sem versão/responsável). Grava a confirmação estruturada da versão atual; versão anterior do arquivo em VERSOES/."""
    arquivo = _arquivo_regras(empresa)
    texto = arquivo.read_text(encoding="utf-8") if arquivo.exists() else ""
    alvo = next(((i, c) for i, c in _linhas_regras(texto) if c[0] == regra), None)
    if alvo is None:
        return recusar("NAO_PERMITIDO", f"{regra} não existe em REGRAS-BANCOS.md.")
    i, c = alvo
    situacao = normalizar(c[8])
    if c[3].startswith("ADIANTAMENTO_"):
        return recusar("AUTOMATISMO_REMOVIDO", "Regra automática de adiantamento não pode ser reativada.")
    if situacao == "TESTE_FICTICIO":
        return recusar("NAO_PERMITIDO", f"{regra} é regra de TESTE fictício: não é confirmável como aprovação do Supervisor.")
    if situacao == "VALIDADA" and gov.confirmacao_bancos(c[9], empresa, regra, c[1])["valida"]:
        return recusar("NAO_PERMITIDO", f"{regra} já tem confirmação válida da versão {c[1]}.")
    if situacao not in ("VALIDADA", "PROPOSTA"):
        return recusar("NAO_PERMITIDO", f"{regra} está em situação {c[8]}; só PROPOSTA ou VALIDADA sem confirmação suficiente.")
    if not c[7].strip():
        return recusar("NAO_PERMITIDO", f"{regra} sem origem documentada: registre a origem antes de confirmar.")
    momento = agora()
    _preservar_versao(arquivo, empresa, momento)
    c[8], c[9] = "VALIDADA", gov.texto_confirmacao_bancos(empresa, regra, c[1], momento.isoformat())
    linhas = texto.splitlines()
    linhas[i] = "| " + " | ".join(c) + " |"
    gravar_texto(arquivo, "\n".join(linhas) + "\n")
    return saida({"resultado": "REGRA_CONFIRMADA", "empresa": empresa, "area": "BANCOS", "chave": regra, "versao": c[1],
                  "aviso": "Etapas de Bancos que usaram a versão anterior das regras ficam desatualizadas (rever as etapas indicadas)."})


def dependencias_exclusao(registro: dict, sol: str) -> dict:
    """Prévia da exclusão DEFINITIVA: impedimentos (dependência sem solução segura), consequências, o que é apagado e o que permanece.
    A exclusão nunca é estorno nem revogação de importação feita no Domínio."""
    s = registro["solicitacoes"].get(sol)
    if not s:
        return {"permitida": False, "impedimentos": [f"{sol} não está no registro ativo."], "consequencias": [], "permanece": [], "sera_removido": []}
    imp, cons = [], []
    if s.get("estado") == "FECHAMENTO_APROVADO":
        imp.append("Aprovação VIGENTE do fechamento: revogue a aprovação antes (a exclusão não substitui a revogação).")
    if str(s.get("estado", "")).endswith("_EM_ANDAMENTO") or (ORDEM_ATIVA.exists() and (ler_ordem() or {}).get("sol") == sol):
        imp.append("Solicitação em processamento ou com ordem ativa.")
    ultima = (s.get("aprovacoes_anteriores") or [{}])[-1]
    if ultima.get("liberacao_dominio") == "REVOGADO_ARQUIVO_NAO_MOVIDO":
        imp.append("TXT de aprovação revogada ainda está em LIBERADOS com o nome original: use 'Mover arquivo revogado' antes.")
    exportados, exportacoes = {}, []
    for ap in s.get("aprovacoes_anteriores", []):
        if ap.get("fatos_exportados"):
            exportados.update(ap["fatos_exportados"])
            exportacoes.append({"em": ap.get("liberacao_em"), "revogada_em": ap.get("revogada_em"), "txt_sha256": ap.get("txt_sha256"),
                                "linhas": ap.get("txt_linhas"), "total": ap.get("txt_total"),
                                "anexos_sha256": {k: v.get("sha256") for k, v in (ap.get("anexos") or {}).items()}})
    if exportados:
        cons.append(f"{len(exportados)} fato(s) desta SOL já saíram em TXT ({len(exportacoes)} exportação(ões), depois revogada(s)). Os "
                    "identificadores e valores desses fatos permanecem como registro mínimo: SOLs futuras com os mesmos fatos continuarão "
                    "marcadas como 'fatos já exportados' (exigem ciência). Excluir NÃO estorna nada no Domínio.")
    for outra, o in registro["solicitacoes"].items():
        if outra != sol and (o.get("empresa"), o.get("competencia")) == (s.get("empresa"), s.get("competencia")):
            cons.append(f"Relacionada à {outra} ({o.get('estado')}), mesma empresa e competência: a {outra} não é alterada; a relação "
                        "deixa de aparecer, exceto fatos já exportados (registro mínimo).")
    return {"permitida": not imp, "impedimentos": imp, "consequencias": cons, "exportados": exportados, "exportacoes": exportacoes,
            "permanece": ["número da SOL (nunca reutilizado), empresa, competência, estado final, datas de abertura e exclusão, "
                          "justificativa da exclusão", *(["identificadores, valores e contas dos fatos exportados; sha256, linhas e total dos TXT "
                                                          "exportados (sem o conteúdo dos arquivos)"] if exportados else [])],
            "sera_removido": ["registro completo da SOL (eventos, decisões, aprovações anteriores, resultados registrados)",
                              "documentos recebidos (pasta RECEBIDOS do lote)", "resultados das etapas no runtime e o lote de envio",
                              "arquivos TXT/Excel/balancete desta SOL em LIBERADOS (inclusive os REVOGADOS)"]}


def excluir_definitivamente(sol: str, frase: str, justificativa: str) -> int:
    """Remove a SOL do registro ativo e grava o REGISTRO MÍNIMO. O servidor apaga em seguida os arquivos listados; o que não puder
    ser apagado fica listado no registro mínimo (remocao_pendente), visível. Nada é repetido automaticamente."""
    esperado = f"EXCLUIR DEFINITIVAMENTE {sol}"
    if (frase or "").strip() != esperado:
        return recusar("CONFIRMACAO_INVALIDA", f'Exclusão definitiva exige a frase exata: "{esperado}".')
    if not isinstance(justificativa, str) or not 5 <= len(justificativa.strip()) <= 500:
        return recusar("PARAMETROS_INVALIDOS", "Informe justificativa de 5 a 500 caracteres.")
    registro = ler_registro()
    dep = dependencias_exclusao(registro, sol)
    if not dep["permitida"]:
        return recusar("EXCLUSAO_IMPEDIDA", "Exclusão definitiva recusada: " + " ".join(dep["impedimentos"]))
    s = registro["solicitacoes"].pop(sol)
    momento = agora().isoformat()
    arquivos = []
    for ap in s.get("aprovacoes_anteriores", []) + ([s["aprovacao"]] if s.get("aprovacao") else []):
        for t in ap.get("tentativas_exportacao", []):
            arquivos += [t.get("arquivo"), t.get("arquivo_residual")] + [v.get("arquivo") for v in (t.get("anexos") or {}).values()]
        arquivos += [ap.get("arquivo_txt"), ap.get("arquivo_revogado")] + [m.get("arquivo") for m in ap.get("movimentacoes_revogacao", [])]
    numero = int(sol.rsplit("-", 1)[1])
    seq = registro.setdefault("sequencia_sol", {})
    seq[sol.split("-")[1]] = max(int(seq.get(sol.split("-")[1], 0)), numero)
    registro.setdefault("registros_minimos", {})[sol] = {
        "sol": sol, "empresa": s.get("empresa"), "competencia": s.get("competencia"), "situacao": "EXCLUIDA_DEFINITIVAMENTE",
        "situacao_texto": f"excluída definitivamente em {momento[:10]}", "estado_final": s.get("estado"),
        "aberta_em": (s.get("eventos") or [{}])[0].get("em"), "excluida_em": momento, "justificativa": justificativa.strip(),
        "fatos_exportados": dep["exportados"], "exportacoes": dep["exportacoes"], "permanece": dep["permanece"],
        "arquivos_a_remover": sorted({a for a in arquivos if a}), "pasta_documentos": s.get("pasta"), "remocao_pendente": None}
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "SOL_EXCLUIDA_DEFINITIVAMENTE", "sol": sol, "empresa": s.get("empresa"), "competencia": s.get("competencia"),
                  "pasta_documentos": s.get("pasta"),
                  "arquivos_a_remover": registro["registros_minimos"][sol]["arquivos_a_remover"], "permanece": dep["permanece"]})


def registrar_remocao(sol: str, pendentes: str) -> int:
    """Resultado da remoção física feita pelo servidor (lista do que NÃO pôde ser apagado; vazia = tudo removido)."""
    registro = ler_registro()
    m = (registro.get("registros_minimos") or {}).get(sol)
    if not m:
        return recusar("SOL_DESCONHECIDA", f"{sol} não tem registro mínimo.")
    lista = json.loads(pendentes or "[]")
    m["remocao_pendente"] = lista or []
    m["remocao_conferida_em"] = agora().isoformat()
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "REMOCAO_REGISTRADA", "sol": sol, "pendentes": lista})


def gravar_texto(caminho: Path, texto: str) -> None:
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(texto, encoding="utf-8")
    com_nova_tentativa(lambda: os.replace(temporario, caminho))


def cancelar(sol: str, motivo: str) -> int:
    registro = ler_registro()
    s = registro["solicitacoes"].get(sol)
    if s is None:
        return recusar("SOL_DESCONHECIDA", f"{sol} não foi aberta por este Coordenador.")
    if s["estado"] != "DOCUMENTOS_EM_ANDAMENTO":
        return recusar("SOL_JA_ENCERRADA", f"{sol} já está em {s['estado']}.")
    ordem = ler_ordem()
    if ordem is not None and ordem.get("sol") == sol:
        ORDEM_ATIVA.unlink()
    s.update(estado="CANCELADA", motivos=[motivo])
    s["eventos"].append({"em": agora().isoformat(), "evento": f"SOL cancelada: {motivo}"})
    gravar_json(REGISTRO, registro)
    return saida({"resultado": "SOL_CANCELADA", "sol": sol, "ordem_ativa_residual": ORDEM_ATIVA.exists()})


def consultar(sol: str) -> int:
    s = ler_registro()["solicitacoes"].get(sol)
    return saida(s) if s else recusar("SOL_DESCONHECIDA", f"{sol} não consta no registro.")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Ferramenta do Coordenador Geral (etapa documental).")
    sub = p.add_subparsers(dest="comando", required=True)
    a = sub.add_parser("abrir")
    a.add_argument("--pedido", required=True)
    a.add_argument("--pasta")
    a.add_argument("--fluxo", default="DOCUMENTOS")
    for nome in ("encerrar-local", "encerrar", "cancelar", "consultar", "registrar-importacao", "registrar-aceite", "registrar-decisao-pendencia",
                 "registrar-financeiro", "registrar-bancos", "registrar-falha-etapa", "registrar-decisao-movimento",
                 "propor-regra-bancos", "aprovar-regra-bancos", "revisar-piloto", "aprovar-fechamento", "registrar-liberacao", "registrar-fiscal", "registrar-contabilidade-fiscal",
                 "registrar-dp", "registrar-contabilidade-dp", "registrar-conciliacao", "retomar-area"):
        s = sub.add_parser(nome)
        s.add_argument("--sol", required=True)
        if nome == 'registrar-liberacao':
            s.add_argument('--situacao', required=True, choices=list(SITUACOES_LIBERACAO))
            for opc in ('--arquivo', '--sha256', '--linhas', '--total', '--motivo', '--movimentacao', '--auditoria', '--anexos'):
                s.add_argument(opc, default='')
        if nome == 'aprovar-fechamento':
            s.add_argument('--acao', choices=['aprovar', 'revogar'], required=True)
            s.add_argument('--frase', default='')
            s.add_argument('--justificativa', required=True)
            s.add_argument('--ciente-exportados', action='store_true')
        if nome == 'revisar-piloto':
            s.add_argument('--acao', choices=['encerrar', 'reabrir'], required=True)
            s.add_argument('--justificativa', required=True)
        if nome in ("registrar-financeiro", "registrar-bancos", "registrar-fiscal", "registrar-contabilidade-fiscal", "registrar-dp",
                    "registrar-contabilidade-dp", "registrar-conciliacao"):
            s.add_argument("--resultado", required=True)
        if nome == "registrar-falha-etapa":
            s.add_argument("--etapa", required=True, choices=list(ETAPAS))
            s.add_argument("--motivo", required=True)
        if nome == "retomar-area":
            s.add_argument("--etapa", required=True, choices=list(ETAPAS))
            s.add_argument("--justificativa", required=True)
        if nome == "registrar-decisao-movimento":
            s.add_argument("--movimento", required=True)
            s.add_argument("--tipo", required=True)
            s.add_argument("--dados", required=True)
            s.add_argument("--justificativa", required=True)
        if nome == "propor-regra-bancos":
            s.add_argument("--dados", required=True)
        if nome == "aprovar-regra-bancos":
            s.add_argument("--regra", required=True)
            s.add_argument("--frase", required=True)
        if nome == "registrar-aceite":
            s.add_argument("--processo", required=True)
            s.add_argument("--chave", required=True)
            s.add_argument("--diferenca", required=True)
        if nome == "registrar-decisao-pendencia":
            s.add_argument("--pendencia", required=True)
            s.add_argument("--decisao", required=True)
            s.add_argument("--justificativa", required=True)
        if nome in ("encerrar", "encerrar-local"):
            s.add_argument("--relatorio", required=True)
        if nome == "registrar-importacao":
            s.add_argument("--resultado", required=True)
        if nome == "cancelar":
            s.add_argument("--motivo", required=True)
    x = sub.add_parser("excluir-definitivamente")
    for opc in ("--sol", "--frase", "--justificativa"):
        x.add_argument(opc, required=True)
    x = sub.add_parser("registrar-remocao")
    x.add_argument("--sol", required=True)
    x.add_argument("--pendentes", default="[]")
    r = sub.add_parser("aprovar-regra-area")
    for opc in ("--empresa", "--area", "--chave", "--frase"):
        r.add_argument(opc, required=True)
    args = p.parse_args()
    if args.comando == "consultar":
        return consultar(args.sol)
    try:
        with trava_registro():
            return executar_comando(args)
    except TravaRegistroIndisponivel as e:
        return recusar("TRAVA_REGISTRO_INDISPONIVEL", str(e))


def executar_comando(args) -> int:
    """Comandos que alteram o registro (executados sob trava_registro)."""
    if args.comando in ("registrar-importacao", "registrar-aceite") and not IMPORTACAO_VGROW_ATIVA:
        return recusar("ESPECIALISTA_DESATIVADO", "Importação VGROW desativada por decisão do Supervisor (código, regras e histórico "
                                                  "preservados). A exportação TXT contábil continua disponível após a aprovação.")
    if args.comando in ("excluir-definitivamente", "registrar-remocao") and not re.fullmatch(r"SOL-20\d{2}-\d{6}", args.sol or ""):
        return recusar("PARAMETROS_INVALIDOS", "SOL deve estar no formato SOL-AAAA-NNNNNN.")
    if args.comando == "excluir-definitivamente":
        return excluir_definitivamente(args.sol, args.frase, args.justificativa)
    if args.comando == "registrar-remocao":
        return registrar_remocao(args.sol, args.pendentes)
    if args.comando == "aprovar-regra-area":
        return aprovar_regra_area(args.empresa, args.area, args.chave, args.frase)
    if getattr(args, "sol", None) and not re.fullmatch(r"SOL-20\d{2}-\d{6}", args.sol):
        return recusar("PARAMETROS_INVALIDOS", "SOL deve estar no formato SOL-AAAA-NNNNNN.")
    if args.comando == "abrir":
        return abrir(args.pedido, args.pasta, args.fluxo)
    if args.comando == "registrar-financeiro":
        return registrar_financeiro(args.sol, args.resultado)
    if args.comando == "registrar-bancos":
        return registrar_bancos(args.sol, args.resultado)
    if args.comando in ('registrar-fiscal','registrar-contabilidade-fiscal'):
        return registrar_fiscal(args.sol,args.resultado,args.comando=='registrar-contabilidade-fiscal')
    if args.comando in ('registrar-dp', 'registrar-contabilidade-dp'):
        return registrar_area(args.sol, 'CONTABILIDADE_DP' if args.comando == 'registrar-contabilidade-dp' else 'DP', args.resultado)
    if args.comando == 'registrar-conciliacao':
        return registrar_conciliacao(args.sol, args.resultado)
    if args.comando == 'retomar-area':
        return retomar_area(args.sol, args.etapa, args.justificativa)
    if args.comando == 'registrar-liberacao':
        return registrar_liberacao(args.sol, args.situacao, args.arquivo, args.sha256, args.linhas or '0', args.total or '0', args.motivo,
                                   args.movimentacao, args.auditoria, args.anexos)
    if args.comando == 'aprovar-fechamento':
        return aprovar_fechamento(args.sol, args.acao, args.frase, args.justificativa, args.ciente_exportados)
    if args.comando == 'revisar-piloto':
        return revisar_piloto(args.sol, args.acao, args.justificativa)
    if args.comando == "registrar-falha-etapa":
        return registrar_falha_etapa(args.sol, args.etapa, args.motivo)
    if args.comando == "registrar-decisao-movimento":
        return registrar_decisao_movimento(args.sol, args.movimento, args.tipo, args.dados, args.justificativa)
    if args.comando == "propor-regra-bancos":
        return propor_regra_bancos(args.sol, args.dados)
    if args.comando == "aprovar-regra-bancos":
        return aprovar_regra_bancos(args.sol, args.regra, args.frase)
    if args.comando == "encerrar":
        return encerrar(args.sol, args.relatorio)
    if args.comando == "encerrar-local":
        return encerrar_local(args.sol, args.relatorio)
    if args.comando == "cancelar":
        return cancelar(args.sol, args.motivo)
    if args.comando == "registrar-importacao":
        return registrar_importacao(args.sol, args.resultado)
    if args.comando == "registrar-aceite":
        return registrar_aceite(args.sol, args.processo, args.chave, args.diferenca)
    if args.comando == "registrar-decisao-pendencia":
        return registrar_decisao_pendencia(args.sol, args.pendencia, args.decisao, args.justificativa)
    return consultar(args.sol)


if __name__ == "__main__":
    sys.exit(main())
