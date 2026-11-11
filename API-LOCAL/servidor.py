"""API LOCAL CONTROLADA - Escritório Virtual ↔ Coordenador Geral (AGENTES PRIME).

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I API-LOCAL/servidor.py
e abrir no navegador o endereço impresso (http://127.0.0.1:8765/).

Segurança (ver API-LOCAL/LEIA-ME.md):
- Escuta SOMENTE em 127.0.0.1 (constante; não há opção de outro endereço). Host diferente de 127.0.0.1/localhost na
  porta configurada é recusado (barra DNS rebinding).
- Toda rota /api exige o token de sessão (gerado a cada início, entregue só dentro da página servida) no cabeçalho
  X-Prime-Sessao; Origin/Sec-Fetch-Site de outra origem são recusados.
- O navegador nunca envia caminhos: só empresa (identificador cadastrado), competência, instrução e o conteúdo dos
  arquivos. Nomes são saneados; o servidor escolhe todos os caminhos.
- Upload: lista fechada de formatos, conferência de assinatura do conteúdo, limites por arquivo e por lote, SHA-256
  conferido com o calculado pelo navegador (upload incompleto falha), sem sobrescrita, duplicidade tratada.
- O processamento segue: lote → validação → coordenador.py abrir (SOL + ordem ativa) → executor (agente-documentos)
  → coordenador.py encerrar (decisão) → estado exibido. Uma execução por vez.
- Runtime (lotes, transcrições, resultados) fica FORA do projeto e de pastas sincronizadas (%LOCALAPPDATA%).
  Os documentos recebidos ficam em CLIENTES/<EMPRESA>/RECEBIDOS/<AAAA-MM>/<LOTE>/ (fora do Git), somente leitura.
"""

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import unicodedata
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "COORDENADOR-GERAL" / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(RAIZ / "AGENTES" / "IMPORTACAO" / "ferramentas"))
sys.path.insert(0, str(RAIZ / "AGENTES" / "CONTABILIDADE"))
import coordenador  # noqa: E402  (somente leitura de cadastro/registro e identificação de empresa/competência)
import documentos_local  # noqa: E402
import empresas_local  # noqa: E402
import base_inicial  # noqa: E402  (base inicial: balancete anterior + book; somente dados da empresa)
import amostra_ficticia  # noqa: E402
import exportacao_dominio  # noqa: E402
import metodo_empresa  # noqa: E402
import importacao_vgrow  # noqa: E402  (somente agrupamento de processos para a tela; o fechamento roda em processo separado)
import governanca_regras  # noqa: E402  (definições necessárias por empresa; somente leitura)
import regras_areas  # noqa: E402  (sugestões e confirmação guiada das referências por área)
import reprocessamento  # noqa: E402  (tentativas auditadas; somente metadados no runtime)

HOST = "127.0.0.1"
PORTA = int(os.environ.get("AGENTES_PRIME_PORTA", "8765"))
PY = sys.executable
FERRAMENTA_COORDENADOR = RAIZ / "COORDENADOR-GERAL" / "ferramentas" / "coordenador.py"
FERRAMENTA_IMPORTACAO = RAIZ / "AGENTES" / "IMPORTACAO" / "ferramentas" / "importacao_vgrow.py"
FERRAMENTA_RECONHECIMENTO = RAIZ / "AGENTES" / "IMPORTACAO" / "ferramentas" / "reconhecer_documentos_vgrow.py"
FERRAMENTA_FINANCEIRO = RAIZ / "AGENTES" / "FINANCEIRO" / "ferramentas" / "conferencia_financeira.py"
FERRAMENTA_BANCOS = RAIZ / "AGENTES" / "CONTABILIDADE" / "BANCOS" / "ferramentas" / "lancamentos_bancarios.py"
FERRAMENTA_FISCAL = RAIZ / 'AGENTES/FISCAL/ferramentas/analise_fiscal.py'
FERRAMENTA_CONTABIL_FISCAL = RAIZ / 'AGENTES/CONTABILIDADE/FISCAL/ferramentas/propostas_fiscais.py'
FERRAMENTA_DP = RAIZ / 'AGENTES/DP/ferramentas/analise_dp.py'
FERRAMENTA_CONTABIL_DP = RAIZ / 'AGENTES/CONTABILIDADE/DP/ferramentas/propostas_dp.py'
FERRAMENTA_CONCILIACAO = RAIZ / 'AGENTES/CONCILIACAO/ferramentas/conciliacao.py'
EXTRATOR = RAIZ / "AGENTES" / "DOCUMENTOS" / "ferramentas" / "extrair_documentos.py"
ESTATICO = RAIZ / "ESCRITORIO-VIRTUAL"
EXECUTAR_AGENTE = documentos_local.executar   # execução local; sem fallback para Claude

LIMITE_ARQUIVO = 20 * 1024 * 1024             # igual ao limite por arquivo do extrator
LIMITE_LOTE = 100 * 1024 * 1024
LIMITE_ARQUIVOS = 30
LIMITE_JSON = 16 * 1024
LIMITE_INSTRUCAO = 2000
FORMATOS = {".pdf", ".xml", ".xlsx", ".xlsm", ".txt", ".csv", ".ofx", ".png", ".jpg", ".jpeg"}
NOMES_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
RE_LOTE = re.compile(r"L-\d{8}-\d{6}-[0-9a-f]{6}")
RE_SOL = re.compile(r"SOL-20\d{2}-\d{6}")
RE_COMPETENCIA = re.compile(r"(20\d{2})-(0[1-9]|1[0-2])")

# Especialista Importação VGROW DESATIVADO por decisão do Supervisor: rotas respondem 410 e o reconhecimento automático não roda.
# Código, regras e histórico ficam preservados. A exportação contábil TXT (exportacao_dominio) é outra funcionalidade e continua ativa.
IMPORTACAO_VGROW_ATIVA = False
AVISO_IMPORTACAO = ("Especialista Importação VGROW desativado por decisão do Supervisor (código, regras e histórico preservados). "
                    "A exportação contábil TXT para importação manual no Domínio continua disponível após a aprovação do fechamento.")

TRAVA = threading.Lock()
EM_EXECUCAO = {"sol": None}
EM_IMPORTACAO = {"sol": None}   # só para exibição no Escritório Virtual (a Importação roda dentro da requisição, com a TRAVA)
EM_FINANCEIRO = {"sol": None, "etapa": None}   # etapa do fluxo Financeiro → Bancos em execução (exibição)


def proxima_tentativa(pasta: Path, prefixo: str) -> int:
    """Número da próxima tentativa (<prefixo>-N): conta também as que falharam; nada é reaproveitado ou sobrescrito."""
    anteriores = [int(p.name.split("-")[1]) for p in pasta.glob(f"{prefixo}-*") if p.name.split("-")[1].isdigit()]
    return max(anteriores, default=0) + 1


# ---------------------------------------------------------------- runtime fora do projeto e de pastas sincronizadas

def pasta_runtime() -> Path:
    base = os.environ.get("AGENTES_PRIME_RUNTIME") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "AgentesPrime" / "runtime")
    p = Path(base).resolve()
    modo_teste = os.environ.get("AGENTES_PRIME_MODO_TESTE") == "1" or bool(os.environ.get("AGENTES_PRIME_REGISTRO_SOL"))
    temporario = str(p).startswith(("/tmp/", "/private/tmp/")) or "/T/" in str(p)
    if temporario and not modo_teste:
        raise SystemExit("Runtime operacional temporário recusado. Configure um diretório persistente fora do projeto.")
    if not p.is_absolute() or "onedrive" in str(p).lower() or str(p).lower().startswith(str(RAIZ).lower()):
        raise SystemExit(f"Runtime recusado (dentro do projeto ou de pasta sincronizada): {p}")
    for sub in ("lotes", "execucoes"):
        (p / sub).mkdir(parents=True, exist_ok=True)
    return p


RUNTIME = None


def agora() -> str:
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def gravar_json(caminho: Path, dados: dict) -> None:
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    coordenador.com_nova_tentativa(lambda: os.replace(temporario, caminho))


def ler_json(caminho: Path):
    return coordenador.com_nova_tentativa(lambda: json.loads(caminho.read_text(encoding="utf-8"))) if caminho.exists() else None


def lixeira_solicitacoes() -> dict:
    return ler_json(RUNTIME / 'lixeira-solicitacoes.json') or {'itens': {}, 'eventos': []}


def solicitacao_excluida(sol: str) -> bool:
    return bool(lixeira_solicitacoes()['itens'].get(sol, {}).get('excluida'))


# ---------------------------------------------------------------- empresas e validações

def empresas_autorizadas() -> dict:
    autorizadas = {}
    for ident, e in coordenador.empresas_cadastradas().items():
        modo, motivo = coordenador.autorizacao(e)
        if not motivo:
            autorizadas[ident] = {"id": ident, "nome": e["razao_social"], "modo": modo,
                                  "piloto": coordenador.PILOTO if coordenador.eh_piloto(e) else None}
    return autorizadas


def empresas_com_cadastro_pendente(autorizadas: dict) -> list:
    """Visibilidade do cadastro não concede autorização para criar ou processar lotes."""
    pendentes = []
    for ident, e in coordenador.empresas_cadastradas().items():
        if ident in autorizadas or not e.get('cadastro_local'):
            continue
        d = ler_json(coordenador.CLIENTES / ident / 'empresa-local.json') or {}
        if d.get('excluida'):
            continue                      # cadastro excluído: não aparece para novas solicitações
        motivos = []
        if not d.get('plano'):
            motivos.append('Preparar a base inicial (balancete do mês anterior) para cadastrar as contas.')
        if not d.get('contas'):
            motivos.append('Vincular as contas bancárias a contas contábeis analíticas do grupo ATIVO.')
        if not d.get('cadastro_confirmado') or not d.get('piloto'):
            motivos.append('Conferir o cadastro e habilitar o piloto em simulação.')
        pendentes.append({'id': ident, 'nome': d.get('nome') or e['razao_social'], 'modo': 'SIMULAÇÃO',
                          'piloto': None, 'cadastro_pendente': True, 'motivos': motivos or ['Revisar a autorização do piloto no cadastro.'],
                          'grupos_pendentes': sum(not c.get('grupo') for c in d.get('plano', []))})
    return pendentes


def impedimentos_exclusao_empresa(ident: str) -> list:
    """Operações em andamento que impedem excluir o cadastro (nada é interrompido automaticamente)."""
    motivos = []
    if coordenador.ler_ordem():
        motivos.append('Há uma ordem ativa no Coordenador.')
    if EM_EXECUCAO['sol'] or EM_FINANCEIRO['sol'] or EM_IMPORTACAO['sol']:
        motivos.append('Há um processamento em andamento no escritório.')
    for sol, s in coordenador.ler_registro()['solicitacoes'].items():
        if s.get('empresa') != ident:
            continue
        if str(s.get('estado', '')).endswith('_EM_ANDAMENTO'):
            motivos.append(f'A solicitação {sol} desta empresa está em processamento.')
        if (s.get('aprovacao') or {}).get('liberacao_dominio') == 'PREPARANDO':
            motivos.append(f'A exportação da solicitação {sol} desta empresa está em andamento.')
    return motivos


def resumo_base_empresa(ident: str) -> dict:
    """Competência mais recente com base inicial registrada (para a lista de empresas)."""
    indice = ler_json(coordenador.CLIENTES / ident / 'BASE-INICIAL' / 'INDICE.json') or {}
    bases = indice.get('bases') or {}
    if not bases:
        return {}
    comp = max(bases)
    return {'competencia_atual': comp, 'situacao_base': bases[comp].get('situacao')}


def saneado(nome_original: str):
    nome = re.split(r"[\\/]", nome_original)[-1]
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    nome = re.sub(r"[^A-Za-z0-9._-]+", "_", nome).strip("._ -")
    nome = re.sub(r"_+", "_", nome)[:100]
    base, ext = os.path.splitext(nome)
    ext = ext.lower()
    if not base or ext not in FORMATOS or base.upper().split(".")[0] in NOMES_RESERVADOS:
        return None, ext
    return f"{base}{ext}", ext


def conteudo_confere(ext: str, inicio: bytes) -> bool:
    corpo = inicio.lstrip(b"\xef\xbb\xbf \t\r\n")
    if ext == ".pdf":
        return b"%PDF-" in inicio[:1024]
    if ext in (".xlsx", ".xlsm"):
        return inicio.startswith(b"PK\x03\x04")
    if ext == ".png":
        return inicio.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in (".jpg", ".jpeg"):
        return inicio.startswith(b"\xff\xd8\xff")
    if ext == ".xml":
        return corpo.startswith(b"<") and b"\x00" not in inicio
    # texto (txt/csv/ofx): sem bytes nulos e sem assinatura de binário conhecida
    return b"\x00" not in inicio and not corpo.startswith((b"%PDF-", b"PK\x03\x04", b"\x89PNG", b"\xff\xd8\xff", b"\xd0\xcf\x11\xe0", b"MZ"))


def novo_lote_id() -> str:
    return f"L-{dt.datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"


def pasta_lote(lote: str) -> Path:
    if not RE_LOTE.fullmatch(lote):
        raise ValueError("lote inválido")
    return RUNTIME / "lotes" / lote


# ---------------------------------------------------------------- processamento (thread única)

def coordenador_cli(*args) -> tuple:
    p = subprocess.run([PY, "-I", str(FERRAMENTA_COORDENADOR), *args], cwd=RAIZ, capture_output=True, encoding="utf-8")
    try:
        return p.returncode, json.loads(p.stdout)
    except json.JSONDecodeError:
        return p.returncode, {"resultado": "ERRO_COORDENADOR", "motivo": (p.stderr or "")[-300:]}


def processar(lote_id: str, sol: str, ordem_de_servico: str) -> None:
    pasta = RUNTIME / "execucoes" / sol
    estado = {"sol": sol, "lote": lote_id, "status": "EM_EXECUCAO", "inicio": agora()}
    gravar_json(pasta / "execucao.json", estado)
    try:
        resultado = EXECUTAR_AGENTE(ordem_de_servico, pasta)
    except Exception as e:  # falha do executor nunca deixa a ordem ativa sem encerramento
        resultado = {"relatorio": None, "problemas": [f"Falha no executor: {type(e).__name__}: {e}"], "ferramentas": {}, "bloqueios": 0}
    relatorio = pasta / "relatorio.md"
    if resultado.get("relatorio"):
        relatorio.write_text(resultado["relatorio"], encoding="utf-8")
    local = resultado.get('executor') == 'LOCAL_SEM_MODELO'
    codigo, decisao = coordenador_cli("encerrar-local" if local else "encerrar", "--sol", sol,
                                    "--relatorio", str(pasta / 'documentos-local.json') if local else str(relatorio))
    lote = ler_json(pasta_lote(lote_id) / "lote.json")
    alteracoes = []
    destino = coordenador.CLIENTES / lote["empresa"] / lote["pasta"]
    for a in lote["arquivos"]:
        arquivo = destino / a["nome_interno"]
        if not arquivo.is_file() or hashlib.sha256(arquivo.read_bytes()).hexdigest() != a["sha256"]:
            alteracoes.append(a["nome_interno"])
    estado.update(status="CONCLUIDA" if resultado.get("relatorio") and not resultado.get("problemas") else "FALHOU",
                  fim=agora(), auditoria={k: resultado.get(k) for k in ("problemas", "ferramentas", "bloqueios", "duracao_s", "codigo_saida")},
                  decisao=decisao, documentos_alterados=alteracoes,
                  inventario=inventario_extrator(lote["empresa"], lote["pasta"]))
    if local:
        estado['documentos_local'] = ler_json(pasta / 'documentos-local.json')
    gravar_json(pasta / "execucao.json", estado)
    executar_pendentes(sol)        # plano do Coordenador: áreas → Contabilidade → Conciliação
    with TRAVA:
        EM_EXECUCAO["sol"] = None
    if IMPORTACAO_VGROW_ATIVA and lote["empresa"] == "VGROW" and (decisao or {}).get("piloto") == coordenador.PILOTO:
        reconhecer_campos(sol, lote["pasta"])


def reconhecer_campos(sol: str, pasta_lote_rel: str) -> None:
    """VGROW: reconhecimento automático dos campos da DUIMP/NFs (texto do PDF ou OCR local) para a conferência do
    Supervisor antes do encaminhamento manual à Importação. Não decide nada e não aciona a Importação."""
    pasta = RUNTIME / "execucoes" / sol
    gravar_json(pasta / "reconhecimento-status.json", {"status": "EM_ANDAMENTO", "inicio": agora()})
    try:
        p = subprocess.run([PY, "-I", str(FERRAMENTA_RECONHECIMENTO), "--pasta", pasta_lote_rel, "--saida", str(pasta / "reconhecimento.json")],
                           cwd=RAIZ, capture_output=True, encoding="utf-8", timeout=1800)
        ok = p.returncode == 0 and (pasta / "reconhecimento.json").exists()
    except subprocess.TimeoutExpired:
        ok = False
    gravar_json(pasta / "reconhecimento-status.json", {"status": "PRONTO" if ok else "FALHOU", "fim": agora()})


def problema_ancora(s: dict, pasta: Path):
    """None se o pacote de Documentos confere com a âncora registrada pelo Coordenador; senão, o motivo (nada é presumido)."""
    manifesto, extracao = pasta / 'documentos-local.json', pasta / 'extracao-local.json'
    if not manifesto.is_file() or not extracao.is_file():
        return None                                   # execução sem pacote local (fluxo legado): nada a conferir aqui
    ancora = s.get('ancora_documentos')
    if not ancora:
        return ('Pacote de Documentos sem âncora de integridade registrada pelo Coordenador (anterior a esta versão): '
                'não é tratado como verificado. Abra nova solicitação para nova triagem.')
    atuais = {'manifesto_sha256': hashlib.sha256(manifesto.read_bytes()).hexdigest(),
              'extracao_sha256': hashlib.sha256(extracao.read_bytes()).hexdigest()}
    if any(atuais[k] != ancora.get(k) for k in atuais):
        return 'Integridade: pacote de Documentos alterado depois do registro do Coordenador (âncora não confere); pacote recusado.'
    return None


def situacao_areas(s: dict) -> dict:
    """Situação das áreas que recebem documentos compartilhados com o Financeiro (para a Contabilidade/Bancos)."""
    t = s.get('tarefas_areas', {}).get('FISCAL')
    if not t:
        return {}
    return {'FISCAL': {'estado': t.get('estado') or 'NAO_INFORMADO',
                       'documentos': [d.get('arquivo') if isinstance(d, dict) else str(d) for d in t.get('documentos', [])]}}


# Etapas documentais executadas pelo plano: (ferramenta, prefixo das tentativas, comando de registro, resultado de origem)
ETAPAS_DOCUMENTAIS = {
    'FISCAL': ('FERRAMENTA_FISCAL', 'fiscal', 'registrar-fiscal', None),
    'CONTABILIDADE_FISCAL': ('FERRAMENTA_CONTABIL_FISCAL', 'contabilfiscal', 'registrar-contabilidade-fiscal', ('fiscal', '--fiscal')),
    'DP': ('FERRAMENTA_DP', 'dp', 'registrar-dp', None),
    'CONTABILIDADE_DP': ('FERRAMENTA_CONTABIL_DP', 'contabdp', 'registrar-contabilidade-dp', ('dp', '--dp')),
}


def nova_execucao(sol: str, prefixo: str) -> Path:
    """Cria a pasta da próxima execução da etapa (<prefixo>-N, nunca reaproveitada) e a VINCULA explicitamente à tentativa
    auditada em execução, quando houver (ciclo de vida do reprocessamento)."""
    pasta = RUNTIME / "execucoes" / sol
    saida = pasta / f"{prefixo}-{proxima_tentativa(pasta, prefixo)}"
    saida.mkdir(parents=True, exist_ok=False)
    try:
        reprocessamento.vincular_execucao(RUNTIME, sol, saida.name)
    except (OSError, ValueError, KeyError) as exc:          # o vínculo é auditoria: nunca impede a etapa
        print(f"Aviso: vínculo da execução {saida.name} à tentativa não registrado ({type(exc).__name__}).", file=sys.stderr)
    return saida


def finalizar_tentativa(sol: str, tentativa: dict, erro: BaseException | None = None) -> dict | None:
    """Fecha a tentativa auditada iniciada por iniciar_execucao: CONCLUIDA, BLOQUEADA (bloqueio funcional) ou FALHOU (erro
    técnico). Idempotente (segunda chamada não altera nada). Erro técnico fica registrado sem rastreamento interno."""
    try:
        atual = next((t for t in reprocessamento.listar(RUNTIME, sol) if t["numero"] == tentativa["numero"]), None)
        if not atual or atual.get("status") in reprocessamento.FINAIS:
            return atual and dict(atual, finalizacao_repetida=True)
        s = coordenador.ler_registro()["solicitacoes"].get(sol) or {}
        plano = coordenador.plano_de(s) if s else []
        execucoes = reprocessamento.resumir_execucoes(RUNTIME, sol, atual.get("execucoes", []))
        status = reprocessamento.status_final(execucoes, plano, erro=erro is not None)
        bloqueios = [b for e in execucoes for b in e.get("bloqueio_lote") or []]
        resultado = {"execucoes": execucoes, "bloqueio_lote": bloqueios,
                     "motivo_bloqueio": bloqueios[0] if bloqueios else None,
                     "plano": [{"etapa": e.get("etapa"), "situacao": e.get("situacao")} for e in plano]}
        falha = None
        if erro is not None:
            falha = {"tipo": type(erro).__name__, "mensagem": "Erro técnico durante a execução; detalhes no registro local do servidor."}
        elif status == "FALHOU":
            falha = {"tipo": "ETAPA", "mensagem": next((e["falha"] for e in execucoes if e.get("falha")), None)
                     or "Etapa sem resultado registrado ou nenhuma execução realizada."}
        return reprocessamento.finalizar(RUNTIME, sol, tentativa["numero"], status, resultado=resultado,
                                         estado_sol=s.get("estado"), erro=falha)
    except Exception as exc:                                   # nunca derrubar o servidor por causa da auditoria
        print(f"Aviso: finalização da tentativa de {sol} não registrada ({type(exc).__name__}).", file=sys.stderr)
        return None


def fotografar_fontes(pasta: Path, empresa: str, etapa: str) -> None:
    """sha256 das fontes da empresa ANTES da etapa: o Coordenador recusa o resultado se elas mudarem durante a execução."""
    gravar_json(pasta / 'fontes.json', {'etapa': etapa, 'em': agora(),
                                        'fontes': coordenador.fontes_atuais(empresa, coordenador.FONTES_ETAPA[etapa])})


def executar_etapa_documental(sol, etapa):
    """Fiscal, DP (pacote de Documentos com âncora) ou seus especialistas da Contabilidade (resultado registrado da área)."""
    s = coordenador.ler_registro()['solicitacoes'][sol]; pasta = RUNTIME / 'execucoes' / sol
    ferramenta, prefixo, comando, fonte = ETAPAS_DOCUMENTAIS[etapa]
    saida = nova_execucao(sol, prefixo)
    comuns = ['--empresa', s['empresa'], '--competencia', s['competencia'], '--sol', sol, '--saida', str(saida)]
    gravar_json(saida / 'origem.json', {'sol': sol, 'etapa': etapa, 'inicio': agora()})
    fotografar_fontes(saida, s['empresa'], etapa)
    try:
        EM_FINANCEIRO.update(sol=sol, etapa=etapa)
        if fonte:
            origem = ultimo_concluido_caminho(sol, fonte[0])
            registrado = (s.get(fonte[0]) or [{}])[-1].get('resultado_sha256')
            if not origem or hashlib.sha256(origem.read_bytes()).hexdigest() != registrado:
                raise ValueError(f'Resultado de {fonte[0]} ausente ou alterado após o registro; proposta recusada.')
            args = [str(globals()[ferramenta]), *comuns, fonte[1], str(origem)]
        else:
            if (motivo_ancora := problema_ancora(s, pasta)):
                raise ValueError(motivo_ancora)
            args = [str(globals()[ferramenta]), *comuns, '--pasta', s['pasta'], '--documentos-local', str(pasta / 'documentos-local.json'),
                    '--extracao-local', str(pasta / 'extracao-local.json')]
        p = subprocess.run([PY, '-I', *args], cwd=RAIZ, capture_output=True, encoding='utf-8', errors='replace', timeout=300)
        if p.returncode or not (saida / 'resultado.json').exists():
            raise ValueError((p.stderr or p.stdout or 'Resultado ausente')[-250:])
        codigo, r = coordenador_cli(comando, '--sol', sol, '--resultado', str(saida / 'resultado.json'))
        if codigo:
            raise ValueError(r.get('motivo', 'Registro recusado'))
    except (OSError, ValueError, IndexError, KeyError, subprocess.TimeoutExpired) as exc:
        gravar_json(saida / 'falha.json', {'em': agora(), 'motivo': str(exc)[-300:]})
        coordenador_cli('registrar-falha-etapa', '--sol', sol, '--etapa', etapa, '--motivo', f'{saida.name}: {str(exc)[-300:]}')
    finally:
        EM_FINANCEIRO.update(sol=None, etapa=None)


def executar_etapa_fiscal(sol, contabilidade=False):
    executar_etapa_documental(sol, 'CONTABILIDADE_FISCAL' if contabilidade else 'FISCAL')


def ultimo_concluido_caminho(sol: str, prefixo: str):
    for pasta_t in reversed(tentativas(sol, prefixo)):
        if (pasta_t / 'resultado.json').is_file():
            return pasta_t / 'resultado.json'
    return None


def executar_financeiro(sol: str) -> None:
    """Coordenador → Financeiro (conferência) → Coordenador. Código local (sem Claude). Cada tentativa fica em financeiro-N;
    falha é registrada, sem repetição automática. Contabilidade/Bancos é a etapa seguinte do plano (executar_bancos)."""
    registro = coordenador.ler_registro()
    s = registro["solicitacoes"][sol]
    pasta = RUNTIME / "execucoes" / sol
    fin = nova_execucao(sol, "financeiro")
    fotografar_fontes(fin, s["empresa"], "FINANCEIRO")
    gravar_json(fin / "ja-tratados.json", coordenador.movimentos_tratados(registro, sol))
    gravar_json(fin / "decisoes.json", s.get("decisoes_movimentos", {}))
    gravar_json(fin / "ressalvas.json", s.get("pendencias_documentos", []))       # ressalvas da etapa de Documentos
    comuns = ["--empresa", s["empresa"], "--sol", sol, "--competencia", s["competencia"]]
    try:
        EM_FINANCEIRO.update(sol=sol, etapa="FINANCEIRO")
        pacote = []
        if (pasta / 'documentos-local.json').is_file() and (pasta / 'extracao-local.json').is_file():
            motivo_ancora = problema_ancora(s, pasta)
            if motivo_ancora:
                gravar_json(fin / 'falha.json', {'em': agora(), 'motivo': motivo_ancora})
                coordenador_cli("registrar-falha-etapa", "--sol", sol, "--etapa", "FINANCEIRO", "--motivo", f"{fin.name}: {motivo_ancora}")
                return
            pacote = ['--documentos-local', str(pasta / 'documentos-local.json'), '--extracao-local', str(pasta / 'extracao-local.json'),
                      '--exigir-ancora']
        p = subprocess.run([PY, "-I", str(FERRAMENTA_FINANCEIRO), *comuns, "--pasta", s["pasta"], "--saida", str(fin),
                            "--ja-tratados", str(fin / "ja-tratados.json"), "--decisoes", str(fin / "decisoes.json"),
                            "--ressalvas", str(fin / "ressalvas.json"), *pacote],
                           cwd=RAIZ, capture_output=True, encoding="utf-8", timeout=900)
        if p.returncode != 0 or not (fin / "resultado.json").exists():
            coordenador_cli("registrar-falha-etapa", "--sol", sol, "--etapa", "FINANCEIRO", "--motivo",
                            f"{fin.name}: o Financeiro não devolveu resultado ({(p.stderr or p.stdout or '').strip()[-200:]})")
            return
        codigo, r = coordenador_cli("registrar-financeiro", "--sol", sol, "--resultado", str(fin / "resultado.json"))
        if codigo != 0:
            coordenador_cli("registrar-falha-etapa", "--sol", sol, "--etapa", "FINANCEIRO", "--motivo", f"{fin.name}: {r.get('motivo')}")
            return
    except subprocess.TimeoutExpired:
        coordenador_cli("registrar-falha-etapa", "--sol", sol, "--etapa", "FINANCEIRO", "--motivo", "tempo esgotado")
    finally:
        EM_FINANCEIRO.update(sol=None, etapa=None)


def executar_bancos(sol: str) -> None:
    """Contabilidade/Bancos sobre o último resultado REGISTRADO do Financeiro; situação atual das outras áreas (--areas)."""
    registro = coordenador.ler_registro()
    s = registro["solicitacoes"][sol]
    pasta = RUNTIME / "execucoes" / sol
    comuns = ["--empresa", s["empresa"], "--sol", sol, "--competencia", s["competencia"]]
    try:
        ban = nova_execucao(sol, "bancos")
        fotografar_fontes(ban, s["empresa"], "BANCOS")
        EM_FINANCEIRO.update(sol=sol, etapa="BANCOS")
        origem = ultimo_concluido_caminho(sol, "financeiro")
        fin = origem.parent if origem else None
        if not origem or hashlib.sha256(origem.read_bytes()).hexdigest() != (s.get("financeiro") or [{}])[-1].get("resultado_sha256"):
            coordenador_cli("registrar-falha-etapa", "--sol", sol, "--etapa", "BANCOS", "--motivo",
                            f"{ban.name}: resultado do Financeiro ausente ou alterado após o registro; nada foi proposto.")
            return
        gravar_json(ban / "origem.json", {"financeiro": fin.name})
        gravar_json(ban / "areas.json", situacao_areas(s))          # situação final das áreas que compartilham documentos
        p = subprocess.run([PY, "-I", str(FERRAMENTA_BANCOS), *comuns, "--financeiro", str(origem), "--saida", str(ban),
                            "--decisoes", str(fin / "decisoes.json"), "--areas", str(ban / "areas.json")],
                           cwd=RAIZ, capture_output=True, encoding="utf-8", errors="replace", timeout=900)
        if p.returncode != 0 or not (ban / "resultado.json").exists():
            coordenador_cli("registrar-falha-etapa", "--sol", sol, "--etapa", "BANCOS", "--motivo",
                            f"{ban.name}: Contabilidade/Bancos não devolveu resultado ({(p.stderr or p.stdout or '').strip()[-200:]})")
            return
        codigo, r = coordenador_cli("registrar-bancos", "--sol", sol, "--resultado", str(ban / "resultado.json"))
        if codigo != 0:
            coordenador_cli("registrar-falha-etapa", "--sol", sol, "--etapa", "BANCOS", "--motivo", f"{ban.name}: {r.get('motivo')}")
    except subprocess.TimeoutExpired:
        coordenador_cli("registrar-falha-etapa", "--sol", sol, "--etapa", EM_FINANCEIRO["etapa"] or "FINANCEIRO", "--motivo", "tempo esgotado")
    finally:
        EM_FINANCEIRO.update(sol=None, etapa=None)


def executar_conciliacao(sol: str) -> None:
    """Conciliação sobre os resultados REGISTRADOS (caminho + sha256 do registro) e o pacote de Documentos com âncora."""
    s = coordenador.ler_registro()['solicitacoes'][sol]
    pasta = RUNTIME / 'execucoes' / sol
    saida = nova_execucao(sol, "conciliacao")
    gravar_json(saida / 'origem.json', {'sol': sol, 'etapa': 'CONCILIACAO', 'inicio': agora()})
    fotografar_fontes(saida, s['empresa'], 'CONCILIACAO')
    try:
        EM_FINANCEIRO.update(sol=sol, etapa='CONCILIACAO')
        if (motivo_ancora := problema_ancora(s, pasta)):
            raise ValueError(motivo_ancora)
        situacoes = {e['etapa']: e['situacao'] for e in coordenador.plano_de(s)}
        etapas = {}
        for etapa, chave in coordenador.RESULTADOS_ETAPA.items():
            if etapa == 'CONCILIACAO':
                continue
            caminho = ultimo_concluido_caminho(sol, chave)
            etapas[etapa] = {'situacao': situacoes.get(etapa, 'NAO_ACIONADA'), 'resultado': str(caminho) if caminho and s.get(chave) else None,
                             'sha256_registrado': (s.get(chave) or [{}])[-1].get('resultado_sha256')}
        base = coordenador.CLIENTES / s['empresa']
        entradas = {'contrato': 'ENTRADAS_CONCILIACAO_V1', 'empresa': s['empresa'], 'sol': sol, 'competencia': s['competencia'],
                    'etapas': etapas, 'pacote': {'pasta': s['pasta'], 'documentos_local': str(pasta / 'documentos-local.json'),
                                                 'extracao_local': str(pasta / 'extracao-local.json')},
                    'cadastro': str(base / 'CADASTRO.md'), 'plano': str(base / 'PLANO-DE-CONTAS' / 'PLANO-DE-CONTAS.md'),
                    'regras_conciliacao': str(base / 'REGRAS-CONCILIACAO.json'),
                    'base_inicial': str(base / 'BASE-INICIAL' / s['competencia'] / 'base.json'),
                    'pendencias_anteriores': list(dict.fromkeys(list(s.get('falhas_areas', {}).values()) + s.get('pendencias_documentos', [])))}
        gravar_json(saida / 'entradas.json', entradas)
        p = subprocess.run([PY, '-I', str(FERRAMENTA_CONCILIACAO), '--empresa', s['empresa'], '--sol', sol, '--competencia', s['competencia'],
                            '--entradas', str(saida / 'entradas.json'), '--saida', str(saida)],
                           cwd=RAIZ, capture_output=True, encoding='utf-8', errors='replace', timeout=300)
        if p.returncode or not (saida / 'resultado.json').exists():
            raise ValueError((p.stderr or p.stdout or 'Resultado ausente')[-250:])
        codigo, r = coordenador_cli('registrar-conciliacao', '--sol', sol, '--resultado', str(saida / 'resultado.json'))
        if codigo:
            raise ValueError(r.get('motivo', 'Registro recusado'))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        gravar_json(saida / 'falha.json', {'em': agora(), 'motivo': str(exc)[-300:]})
        coordenador_cli('registrar-falha-etapa', '--sol', sol, '--etapa', 'CONCILIACAO', '--motivo', f'{saida.name}: {str(exc)[-300:]}')
    finally:
        EM_FINANCEIRO.update(sol=None, etapa=None)


EXECUTORES_ETAPA = {
    'FINANCEIRO_EM_ANDAMENTO': lambda sol: executar_financeiro(sol),
    'DP_EM_ANDAMENTO': lambda sol: executar_etapa_documental(sol, 'DP'),
    'FISCAL_EM_ANDAMENTO': lambda sol: executar_etapa_documental(sol, 'FISCAL'),
    'BANCOS_EM_ANDAMENTO': lambda sol: executar_bancos(sol),
    'CONTABILIDADE_DP_EM_ANDAMENTO': lambda sol: executar_etapa_documental(sol, 'CONTABILIDADE_DP'),
    'CONTABILIDADE_FISCAL_EM_ANDAMENTO': lambda sol: executar_etapa_documental(sol, 'CONTABILIDADE_FISCAL'),
    'CONCILIACAO_EM_ANDAMENTO': lambda sol: executar_conciliacao(sol),
}


def executar_pendentes(sol: str) -> None:
    """Executa as etapas pendentes do plano do Coordenador, uma vez cada, na ordem decidida por ele. Uma etapa que não registra
    resultado nem falha (estado inalterado) é registrada como falha: nunca fica "em andamento" sem executor."""
    for _ in range(3 * len(EXECUTORES_ETAPA)):
        estado = coordenador.ler_registro()['solicitacoes'][sol].get('estado')
        executor = EXECUTORES_ETAPA.get(estado)
        if not executor:
            return
        executor(sol)
        if coordenador.ler_registro()['solicitacoes'][sol].get('estado') == estado:
            coordenador_cli('registrar-falha-etapa', '--sol', sol, '--etapa', estado[:-len('_EM_ANDAMENTO')], '--motivo',
                            'A etapa terminou sem registrar resultado nem falha; registrada como falha (sem repetição automática).')


def iniciar_execucao(sol: str) -> bool:
    """Nova tentativa por ação do Supervisor (decisão, regra aprovada ou retomada de etapa). Uma execução por vez."""
    with TRAVA:
        if EM_EXECUCAO["sol"]:
            return False
        EM_EXECUCAO["sol"] = sol
    try:
        tentativa = reprocessamento.iniciar(RUNTIME, sol)       # PREPARADA → EM_EXECUCAO (somente ciclo V2)
    except (OSError, ValueError, KeyError) as exc:
        tentativa = None
        print(f"Aviso: início da tentativa de {sol} não registrado ({type(exc).__name__}).", file=sys.stderr)

    def rodar():
        erro = None
        try:
            executar_pendentes(sol)
        except Exception as exc:                               # erro técnico inesperado: auditado como FALHOU
            erro = exc
            print(f"Erro técnico na execução de {sol}: {type(exc).__name__}: {exc}", file=sys.stderr)
        finally:
            if tentativa:
                finalizar_tentativa(sol, tentativa, erro)
            with TRAVA:
                EM_EXECUCAO["sol"] = None
    threading.Thread(target=rodar, daemon=True).start()
    return True


iniciar_cadeia_financeira = iniciar_execucao


def tentativas(sol: str, prefixo: str) -> list:
    pasta = RUNTIME / "execucoes" / sol
    return sorted((p for p in pasta.glob(f"{prefixo}-*") if p.name.split("-")[1].isdigit()), key=lambda p: int(p.name.split("-")[1]))


def plano_com_descricao(empresa: str) -> list:
    """Contas do plano da empresa (código e descrição), somente leitura, para a tela mostrar nomes completos."""
    arquivo = coordenador.CLIENTES / empresa / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md"
    contas, dentro, cab = [], False, None
    for l in (arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []):
        if l.startswith("## "):
            dentro = coordenador.normalizar(l).startswith("## CONTAS UTILIZADAS")
            continue
        if dentro and l.strip().startswith("|"):
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if cab is None:
                cab = c
            elif not all(re.fullmatch(r":?-{2,}:?", x) for x in c if x) and re.sub(r"\D", "", c[0]):
                grupo = coordenador.grupos_do_plano(empresa).get(re.sub(r"\D", "", c[0]), "")
                contas.append({"codigo": re.sub(r"\D", "", c[0]), "classificacao": c[1] if len(c) > 1 else "", "descricao": c[2] if len(c) > 2 else "",
                               "grupo": grupo})
    return contas


def ultimo_concluido(sol: str, prefixo: str):
    """Resultado da última tentativa CONCLUÍDA (uma tentativa que falhou não apaga nem substitui a anterior válida)."""
    for p in reversed(tentativas(sol, prefixo)):
        r = ler_json(p / "resultado.json")
        if r:
            return dict(r, n=int(p.name.split("-")[1]))
    return None


def etapa_financeira(sol: str, prefixo: str, etapa: str) -> dict:
    lista = tentativas(sol, prefixo)
    if not lista:
        return {"status": "EM_ANDAMENTO" if EM_FINANCEIRO["sol"] == sol and EM_FINANCEIRO["etapa"] == etapa else "NAO_EXECUTADA"}
    ultima = lista[-1]
    r = ler_json(ultima / "resultado.json")
    info = {"n": int(ultima.name.split("-")[1]), "inicio": horario_arquivo(ultima / ("ja-tratados.json" if prefixo == "financeiro" else "origem.json")),
            "fim": horario_arquivo(ultima / "resultado.json")}
    if r:
        return dict(info, status="CONCLUIDA", resumo=r.get("resumo"), bloqueado=bool(r.get("bloqueio_lote")))
    return dict(info, status="EM_ANDAMENTO" if EM_FINANCEIRO["sol"] == sol and EM_FINANCEIRO["etapa"] == etapa else "FALHOU")


# ---------------------------------------------------------------- leitura para a tela

def tabela(relatorio: str, numero: int) -> list:
    linhas, dentro = [], False
    for l in relatorio.splitlines():
        if l.startswith("## "):
            dentro = l.startswith(f"## {numero}.")
            continue
        if dentro and l.strip().startswith("|"):
            linhas.append([c.strip() for c in l.strip().strip("|").split("|")])
    linhas = [c for c in linhas if not all(re.fullmatch(r":?-{2,}:?", x) for x in c if x)]
    return linhas


def inventario_extrator(empresa: str, pasta: str) -> list:
    itens, parte, total = [], 1, 1
    while parte <= total:
        p = subprocess.run([PY, "-I", str(EXTRATOR), "--empresa", empresa, "--pasta", pasta, "--resumo", "--parte", str(parte)],
                           cwd=RAIZ, capture_output=True, encoding="utf-8")
        if p.returncode != 0:
            return []
        dados = json.loads(p.stdout)
        itens += [{k: i.get(k) for k in ("nome", "leitura", "marcacoes", "partes_total", "conteudo_disponivel")} for i in dados["itens"]]
        total = dados["partes_total"]
        parte += 1
    return itens


def horario_arquivo(caminho: Path):
    return dt.datetime.fromtimestamp(caminho.stat().st_mtime).astimezone().replace(microsecond=0).isoformat() if caminho.exists() else None


def etapas_de(sol: str, registro: dict, execucao: dict) -> dict:
    """Resumo SOMENTE LEITURA das etapas da SOL para o Escritório Virtual (estado e horários reais de cada etapa).
    Não decide nada: o estado da SOL continua sendo o do registro do Coordenador."""
    pasta = RUNTIME / "execucoes" / sol
    docs = {"status": {"EM_EXECUCAO": "EM_ANDAMENTO", "CONCLUIDA": "CONCLUIDA"}.get(execucao.get("status"), "FALHOU"),
            "inicio": execucao.get("inicio"), "fim": execucao.get("fim")}
    no_plano = {e['etapa'] for e in registro.get('plano_etapas', [])}
    fiscal = {}
    for chave, etapa in (('fiscal', 'FISCAL'), ('contabilfiscal', 'CONTABILIDADE_FISCAL'), ('dp', 'DP'), ('contabdp', 'CONTABILIDADE_DP'),
                         ('conciliacao', 'CONCILIACAO')):
        fiscal[chave] = (etapa_financeira(sol, chave, etapa) if etapa in no_plano or registro.get(chave)
                         else {'status': 'NAO_APLICAVEL'})
    if registro.get("fluxo") == "FINANCEIRO_BANCOS":
        return {**fiscal, "documentos": docs, "reconhecimento": {"status": "NAO_APLICAVEL"}, "importacao": {"status": "NAO_APLICAVEL"},
                "financeiro": etapa_financeira(sol, "financeiro", "FINANCEIRO"), "bancos": etapa_financeira(sol, "bancos", "BANCOS")}
    if registro.get("empresa") != "VGROW" or registro.get("piloto") != coordenador.PILOTO:
        return {**fiscal, "documentos": docs, "reconhecimento": {"status": "NAO_APLICAVEL"}, "importacao": {"status": "NAO_APLICAVEL"}}
    rec = ler_json(pasta / "reconhecimento-status.json") or {"status": "NAO_EXECUTADO"}
    imp = {"status": "NAO_SOLICITADA"}
    execs = sorted((p for p in pasta.glob("importacao-*") if p.name.split("-")[1].isdigit()), key=lambda p: int(p.name.split("-")[1]))
    if execs:
        ultima = execs[-1]
        resultado = ler_json(ultima / "resultado.json")
        imp = {"n": int(ultima.name.split("-")[1]), "inicio": horario_arquivo(ultima / "informados.json"), "fim": horario_arquivo(ultima / "resultado.json")}
        if resultado:
            imp.update(status="CONCLUIDA", resumo={"fechados": len(resultado.get("processos_fechados", [])),
                                                   "bloqueios": len(resultado.get("processos_pendentes", [])),
                                                   "aguardando_aceite": len(resultado.get("processos_aguardando_aceite", []))})
        else:
            imp["status"] = "EM_ANDAMENTO" if EM_IMPORTACAO["sol"] == sol else "FALHOU"
    return {"documentos": docs, "reconhecimento": {k: rec.get(k) for k in ("status", "inicio", "fim")}, "importacao": imp}


def conciliacao_vigente(sol: str, registro: dict):
    """Última Conciliação com o histórico. Uma execução só é VIGENTE se conferiu exatamente os resultados, o pacote, a extração e as
    fontes da empresa (cadastro, plano, regras) vigentes agora (coordenador.vigencia). Execuções anteriores ficam no histórico."""
    execucoes = registro.get('conciliacao', [])
    if not execucoes:
        return None
    historico = []
    for x in execucoes:
        v = coordenador.vigencia(registro, x)
        historico.append(dict(x, vigente=v['vigente'], motivos_desatualizada=v['motivos']))
    atual = coordenador.vigencia(registro)
    return {'historico': historico, 'vigente': atual['vigente'], 'motivos': atual['motivos'], 'rever': atual['rever'],
            'resultado': ultimo_concluido(sol, 'conciliacao')}


def relativo_raiz(p: Path) -> str:
    return p.relative_to(RAIZ).as_posix() if p.is_relative_to(RAIZ) else p.as_posix()


def caminho_registrado(texto: str) -> Path:
    p = Path(texto)
    return p if p.is_absolute() else RAIZ / p


def gravar_exclusivo(arquivo: Path, conteudo: bytes) -> None:
    """Grava SEM sobrescrever: cria '<nome>.parcial' (exclusivo), confere o conteúdo e só então dá o nome final (rename falha se
    o destino existir). O '.parcial' não tem extensão .txt: um resto de falha nunca parece um TXT liberado."""
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    parcial = arquivo.with_name(arquivo.name + '.parcial')
    with open(parcial, 'xb') as f:
        f.write(conteudo)
        f.flush()
        os.fsync(f.fileno())
    if parcial.read_bytes() != conteudo:
        raise OSError('conteúdo gravado difere do gerado (arquivo .parcial preservado para análise)')
    if arquivo.exists():
        raise OSError(f'{arquivo.name} passou a existir durante a gravação; não é sobrescrito (.parcial preservado)')
    os.rename(parcial, arquivo)


def retirar_de_uso(arquivo: Path, rotulo: str):
    """Renomeia um TXT sem registro válido para nome sem extensão .txt (preservado, nunca apagado). Devolve o novo caminho ou None."""
    destino = arquivo.with_name(f"{arquivo.stem}.{rotulo}-{dt.datetime.now():%Y%m%d-%H%M%S}.bloqueado")
    try:
        os.rename(arquivo, destino)
        return destino
    except OSError:
        return None


NOMES_ANEXOS = {"excel": "lancamentos", "balancete": "balancete"}


def destinos_anexos(txt: Path, empresa: str, competencia: str, sol: str) -> dict:
    return {tipo: txt.with_name(f"{prefixo}_{empresa}_{competencia}_{sol}.xlsx") for tipo, prefixo in NOMES_ANEXOS.items()}


def abrangencia_entrega(todos: dict, sol: str) -> dict:
    """INTEGRAL quando é a única entrega aprovada/exportada da empresa+competência; COMPLEMENTAR quando já há outra (o balancete
    traz só o movimento desta SOL e não calcula saldo final, que dependeria das outras entregas)."""
    s = todos["solicitacoes"][sol]
    outras = [o for o, x in todos["solicitacoes"].items() if o != sol and (x.get("empresa"), x.get("competencia")) == (s["empresa"], s["competencia"])
              and x.get("estado") == "FECHAMENTO_APROVADO"]
    outras += [o for o, m in (todos.get("registros_minimos") or {}).items()
               if (m.get("empresa"), m.get("competencia")) == (s["empresa"], s["competencia"]) and m.get("fatos_exportados")]
    if outras:
        return {"tipo": "COMPLEMENTAR", "outras": sorted(outras),
                "texto": "a competência já tem outra(s) entrega(s) aprovada(s)/exportada(s) (" + ", ".join(sorted(outras)) + "); este "
                         "balancete traz SÓ o movimento desta solicitação e não calcula saldo final."}
    return {"tipo": "INTEGRAL", "outras": [], "texto": "única entrega aprovada da competência: abertura documentada + movimento desta solicitação."}


def problemas_txt(registro: dict) -> list:
    """Por que o TXT registrado NÃO pode ser entregue agora (vazio = pode): arquivo íntegro, fontes e pacote como aprovados."""
    ap = registro.get('aprovacao') or {}
    problemas = []
    arquivo = caminho_registrado(ap['arquivo_txt']) if ap.get('arquivo_txt') else None
    if not arquivo or not arquivo.is_file():
        problemas.append('Arquivo liberado não encontrado no local registrado.')
    elif hashlib.sha256(arquivo.read_bytes()).hexdigest() != ap.get('txt_sha256'):
        problemas.append('Arquivo liberado alterado depois do registro (sha256 diferente).')
    for tipo, a in (ap.get('anexos') or {}).items():
        p = caminho_registrado(a['arquivo'])
        if not p.is_file():
            problemas.append(f'{tipo.capitalize()} liberado não encontrado no local registrado.')
        elif hashlib.sha256(p.read_bytes()).hexdigest() != a['sha256']:
            problemas.append(f'{tipo.capitalize()} alterado depois do registro (sha256 diferente).')
    problemas += coordenador.vigencia_aprovacao(registro)
    if (motivo := problema_ancora(registro, RUNTIME / 'execucoes' / registro['sol'])):
        problemas.append(motivo)
    return problemas


def situacao_txt(registro: dict) -> dict:
    """Situação EFETIVA do TXT para a tela: só há arquivo entregue quando há registro de liberação e arquivo íntegro e vigente."""
    if registro.get('estado') != 'FECHAMENTO_APROVADO' or not registro.get('aprovacao'):
        ultima = (registro.get('aprovacoes_anteriores') or [{}])[-1]
        if ultima.get('liberacao_dominio') == 'REVOGADO_ARQUIVO_NAO_MOVIDO':
            return {'situacao': 'REVOGADO_ARQUIVO_NAO_MOVIDO', 'download': False, 'arquivo': ultima.get('arquivo_txt'),
                    'texto': 'Aprovação revogada, mas o arquivo continua em LIBERADOS com o nome original: NÃO importe. Feche-o e use '
                             '"Mover arquivo revogado".'}
        return {'situacao': 'SEM_APROVACAO_VIGENTE', 'download': False}
    ap = registro['aprovacao']
    lib = ap.get('liberacao_dominio')
    textos = {'BLOQUEADA_NESTA_VERSAO': 'Aprovada antes da exportação TXT existir: nenhum arquivo foi gerado para esta aprovação.',
              'BLOQUEADA_PRODUCAO': 'Empresa real: produção bloqueada nesta versão; nenhum TXT gerado (aprovação registrada).',
              'AGUARDANDO_GERACAO_TXT': 'TXT ainda não gerado.', 'PREPARANDO': 'Geração do TXT iniciada e não concluída; nada liberado.',
              'FALHOU': f"Geração do TXT falhou: {ap.get('liberacao_motivo') or 'motivo não informado'}. Nada liberado; gere de novo só "
                        'depois de corrigir (ação explícita).'}
    if lib != 'LIBERADO_PARA_IMPORTACAO_MANUAL':
        return {'situacao': lib, 'download': False, 'texto': textos.get(lib, lib),
                'pode_gerar': lib in ('FALHOU', 'AGUARDANDO_GERACAO_TXT', 'PREPARANDO') and exportacao_dominio.liberacao_permitida(registro['empresa'])}
    problemas = problemas_txt(registro)
    return {'situacao': lib, 'download': not problemas, 'problemas': problemas, 'arquivo': ap.get('arquivo_txt'),
            'linhas': ap.get('txt_linhas'), 'total': ap.get('txt_total'),
            'texto': ('TXT liberado para importação MANUAL no Domínio (exportado ≠ importado ≠ escriturado).' if not problemas else
                      'TXT registrado, mas o download está BLOQUEADO: ' + ' '.join(problemas))}


def liberar_txt(sol: str) -> dict:
    """Depois da aprovação: TXT do Domínio com os resultados APROVADOS (empresa fictícia nesta versão). Duas fases no registro
    (PREPARANDO → LIBERADO) com o mesmo sha256; nunca sobrescreve; falha fica visível e nada é repetido automaticamente.
    Nunca importa no Domínio. Cópia e auditoria (linha → lançamento, transformações) ficam em execucoes/<SOL>/exportacao-N."""
    s = coordenador.ler_registro()['solicitacoes'][sol]
    if not exportacao_dominio.liberacao_permitida(s['empresa']):
        codigo, r = coordenador_cli('registrar-liberacao', '--sol', sol, '--situacao', 'BLOQUEADA_PRODUCAO',
                                    '--motivo', 'Empresa real: produção bloqueada nesta versão.')
        return {'situacao': 'BLOQUEADA_PRODUCAO' if codigo == 0 else 'ERRO_DE_REGISTRO',
                'mensagem': 'Empresa real: produção bloqueada nesta versão; TXT não gerado (aprovação registrada).'
                            + ('' if codigo == 0 else f" ATENÇÃO: registro recusado: {r.get('motivo')}")}
    pasta = RUNTIME / 'execucoes' / sol
    exp = pasta / f"exportacao-{proxima_tentativa(pasta, 'exportacao')}"
    exp.mkdir(parents=True, exist_ok=False)

    def falhou(motivo, arquivo=''):
        gravar_json(exp / 'falha.json', {'em': agora(), 'motivo': motivo, 'arquivo': arquivo})
        codigo, r = coordenador_cli('registrar-liberacao', '--sol', sol, '--situacao', 'FALHOU', '--motivo', motivo[-300:], '--arquivo', arquivo)
        return {'situacao': 'FALHOU', 'mensagem': motivo[-400:] + ('' if codigo == 0 else f" ATENÇÃO: o registro da falha também foi recusado "
                                                                                          f"({r.get('motivo')}).")}
    try:
        problemas = coordenador.vigencia_aprovacao(s)
        if (motivo := problema_ancora(s, pasta)):
            problemas.append(motivo)
        if problemas:
            raise ValueError(' '.join(problemas))
        resultados = {etapa: str(c) for etapa, chave, _ in exportacao_dominio.ORIGENS if (c := ultimo_concluido_caminho(sol, chave))}
        plano = exportacao_dominio.plano_empresa(s['empresa'])
        gerado = exportacao_dominio.gerar(sol, s, resultados, plano)
        conc = ultimo_concluido_caminho(sol, 'conciliacao')
        if not conc or hashlib.sha256(conc.read_bytes()).hexdigest() != (s.get('aprovacao') or {}).get('conciliacao_sha256'):
            raise ValueError('Resultado da Conciliação aprovada ausente ou alterado (sha256): balancete não calculado; nada liberado.')
        arquivo = exportacao_dominio.destino(s['empresa'], s['competencia'], sol)
        sha = hashlib.sha256(gerado['conteudo']).hexdigest()
        abrangencia = abrangencia_entrega(coordenador.ler_registro(), sol)
        conteudos = {'excel': exportacao_dominio.gerar_excel(sol, s, gerado, plano, arquivo.name, sha)}
        dados_conc = json.loads(conc.read_text(encoding='utf-8')) or {}
        conteudos['balancete'], balancete = exportacao_dominio.gerar_balancete(
            sol, s, gerado, dados_conc.get('saldos_contas'), plano, abrangencia, arquivo.name, sha, dados_conc.get('base_inicial'))
    except (OSError, ValueError, KeyError) as exc:
        return falhou(f'TXT não gerado: {exc}')
    (exp / 'lanctos.txt').write_bytes(gerado['conteudo'])
    gravar_json(exp / 'auditoria.json', dict(gerado['auditoria'], abrangencia=abrangencia))
    destinos = destinos_anexos(arquivo, s['empresa'], s['competencia'], sol)
    for tipo, c in conteudos.items():
        (exp / destinos[tipo].name).write_bytes(c)
    rel = relativo_raiz(arquivo)
    anexos = {t: {'arquivo': relativo_raiz(destinos[t]), 'sha256': hashlib.sha256(c).hexdigest()} for t, c in conteudos.items()}
    for p in [arquivo, *destinos.values()]:
        if p.exists() or p.with_name(p.name + '.parcial').exists():
            return falhou(f'{p.name} (ou o .parcial) já existe em LIBERADOS; nada é sobrescrito. Confira e retire o arquivo anterior.')
    codigo, r = coordenador_cli('registrar-liberacao', '--sol', sol, '--situacao', 'PREPARANDO', '--arquivo', rel, '--sha256', sha,
                                '--auditoria', exp.name, '--anexos', json.dumps(anexos, ensure_ascii=False))
    if codigo != 0:
        return falhou(f"Registro da preparação recusado ({r.get('motivo')}); nenhum arquivo foi gravado em LIBERADOS.")
    gravados = []
    try:
        gravar_exclusivo(arquivo, gerado['conteudo'])
        gravados.append(arquivo)
        for tipo, c in conteudos.items():
            gravar_exclusivo(destinos[tipo], c)
            gravados.append(destinos[tipo])
    except OSError as exc:
        retirados = [retirar_de_uso(p, 'NAO_REGISTRADO') for p in gravados]
        return falhou(f'Falha ao gravar as saídas em LIBERADOS ({exc}); nada liberado'
                      + ('; arquivos já gravados retirados de uso (sem extensão original)' if gravados and all(retirados) else '') + '.',
                      ', '.join(relativo_raiz(p) for p in retirados if p))
    codigo, r = coordenador_cli('registrar-liberacao', '--sol', sol, '--situacao', 'LIBERADO_PARA_IMPORTACAO_MANUAL', '--arquivo', rel,
                                '--sha256', sha, '--linhas', str(gerado['linhas']), '--total', gerado['total'],
                                '--anexos', json.dumps(anexos, ensure_ascii=False))
    if codigo != 0:
        retirados = [retirar_de_uso(p, 'NAO_REGISTRADO') for p in gravados]
        if all(retirados):
            return falhou(f"Registro da liberação recusado ({r.get('motivo')}); os arquivos foram retirados de uso (sem extensão original) "
                          'e preservados. Nada liberado.', ', '.join(relativo_raiz(p) for p in retirados))
        return falhou(f"Registro da liberação recusado ({r.get('motivo')}) e arquivo(s) NÃO puderam ser retirados de uso em LIBERADOS: "
                      'NÃO importe esses arquivos.', rel)
    return {'situacao': 'LIBERADO_PARA_IMPORTACAO_MANUAL', 'arquivo': rel, 'linhas': gerado['linhas'], 'total': gerado['total'],
            'por_origem': gerado['por_origem'], 'transformacoes': gerado['auditoria']['transformacoes_total'],
            'anexos': anexos, 'abrangencia': abrangencia['tipo'],
            'mensagem': 'TXT, Excel dos lançamentos e balancete liberados (mesma versão aprovada). TXT para importação MANUAL no Domínio; '
                        'exportado não significa importado nem escriturado.'}


def preparacao_interrompida(sol: str) -> None:
    """Geração que ficou em PREPARANDO (ex.: queda da API): registra FALHOU e retira de uso o arquivo sem liberação registrada."""
    s = coordenador.ler_registro()['solicitacoes'][sol]
    t = ((s.get('aprovacao') or {}).get('tentativas_exportacao') or [{}])[-1]
    arquivo = caminho_registrado(t['arquivo']) if t.get('arquivo') else None
    residual = retirar_de_uso(arquivo, 'NAO_REGISTRADO') if arquivo and arquivo.is_file() else None
    coordenador_cli('registrar-liberacao', '--sol', sol, '--situacao', 'FALHOU', '--motivo',
                    'Geração interrompida antes da liberação registrada' + ('; arquivo retirado de uso' if residual else ''),
                    '--arquivo', relativo_raiz(residual) if residual else '')


def revogar_txt(sol: str) -> dict:
    """Depois da revogação no registro (download já bloqueado): renomeia o TXT liberado como REVOGADO (preservado). Se o arquivo
    estiver travado, registra que a aprovação foi revogada mas o arquivo NÃO foi movido (visível; nova tentativa explícita)."""
    s = coordenador.ler_registro()['solicitacoes'][sol]
    anterior = (s.get('aprovacoes_anteriores') or [{}])[-1]
    aviso = 'Revogar no aplicativo não estorna importação eventualmente já feita no Domínio (estorno manual).'
    if anterior.get('liberacao_dominio') not in ('LIBERADO_PARA_IMPORTACAO_MANUAL', 'REVOGADO_ARQUIVO_NAO_MOVIDO') or not anterior.get('arquivo_txt'):
        codigo, r = coordenador_cli('registrar-liberacao', '--sol', sol, '--situacao', 'REVOGADO', '--movimentacao', 'SEM_ARQUIVO')
        return {'situacao': 'SEM_TXT', 'mensagem': 'Aprovação revogada; não havia TXT liberado.'
                + ('' if codigo == 0 else f" ATENÇÃO: registro recusado ({r.get('motivo')}).")}
    arquivo = caminho_registrado(anterior['arquivo_txt'])
    anexos = [caminho_registrado(a['arquivo']) for a in (anterior.get('anexos') or {}).values()]
    retentativa = bool(anterior.get('movimentacoes_revogacao'))
    if not arquivo.is_file() and not retentativa:
        coordenador_cli('registrar-liberacao', '--sol', sol, '--situacao', 'REVOGADO', '--movimentacao', 'FALHOU',
                        '--arquivo', anterior['arquivo_txt'], '--motivo', 'arquivo não encontrado no local registrado')
        return {'situacao': 'REVOGADO_ARQUIVO_NAO_MOVIDO', 'arquivo': anterior['arquivo_txt'],
                'mensagem': f"Aprovação revogada e download bloqueado, mas o arquivo não foi encontrado em {anterior['arquivo_txt']}: "
                            f'localize-o e não o importe. {aviso}'}
    marca = f"_REVOGADO-{dt.datetime.now():%Y%m%d-%H%M%S}"
    novo = arquivo.with_name(f"{arquivo.stem}{marca}{arquivo.suffix}")
    try:
        for p in anexos:                     # anexos primeiro; o TXT por último (é ele que indica "ainda não movido")
            if p.is_file():
                os.rename(p, p.with_name(f"{p.stem}{marca}{p.suffix}"))
        if arquivo.is_file():
            os.rename(arquivo, novo)
        elif retentativa:
            novo = next(iter(sorted(arquivo.parent.glob(f"{arquivo.stem}_REVOGADO-*{arquivo.suffix}"))), novo)
    except OSError as exc:
        codigo, r = coordenador_cli('registrar-liberacao', '--sol', sol, '--situacao', 'REVOGADO', '--movimentacao', 'FALHOU',
                                    '--arquivo', anterior['arquivo_txt'], '--motivo', f'{type(exc).__name__}: {exc}'[:300])
        return {'situacao': 'REVOGADO_ARQUIVO_NAO_MOVIDO', 'arquivo': anterior['arquivo_txt'],
                'mensagem': f"Aprovação REVOGADA e download bloqueado, mas o arquivo NÃO pôde ser renomeado ({type(exc).__name__}): "
                            f"{anterior['arquivo_txt']} continua em LIBERADOS com o nome original. NÃO importe esse arquivo; feche-o "
                            f'(Excel/OneDrive) e use "Mover arquivo revogado". {aviso}'
                            + ('' if codigo == 0 else f" ATENÇÃO: registro recusado ({r.get('motivo')}).")}
    rel = relativo_raiz(novo)
    codigo, r = coordenador_cli('registrar-liberacao', '--sol', sol, '--situacao', 'REVOGADO', '--movimentacao', 'RENOMEADO', '--arquivo', rel)
    return {'situacao': 'REVOGADO', 'arquivo': rel,
            'mensagem': f'TXT, Excel e balancete renomeados como REVOGADO ({novo.name}) e download bloqueado. {aviso}'
                        + ('' if codigo == 0 else f" ATENÇÃO: renomeado, mas o registro foi recusado ({r.get('motivo')}).")}


def resumo_conciliacao(sol: str, registro: dict) -> dict:
    """Vigência e alcance da última Conciliação (para o escritório mostrar desatualizada/parcial em qualquer SOL aberta)."""
    c = conciliacao_vigente(sol, registro) if registro.get('conciliacao') else None
    if not c:
        return {}
    return {'conciliacao_vigente': c['vigente'], 'conciliacao_parcial': bool((registro['conciliacao'][-1].get('alcance') or {}).get('parcial'))}


def dentro(p: Path, *bases) -> bool:
    try:
        r = p.resolve()
        return any(r.is_relative_to(Path(b).resolve()) for b in bases)
    except OSError:
        return False


def remover_fisicamente(resultado: dict, empresa: str, sol: str, lote: str) -> list:
    """Apaga SÓ o que pertence à SOL, dentro das pastas permitidas (RECEBIDOS da empresa, runtime da SOL e do lote, LIBERADOS).
    Devolve o que não pôde ser apagado (fica visível no registro mínimo)."""
    liberados = Path(os.environ.get('AGENTES_PRIME_LIBERADOS') or RAIZ / 'LIBERADOS')
    pendentes, alvos = [], []
    if resultado.get('pasta_documentos'):
        alvos.append(coordenador.CLIENTES / empresa / resultado['pasta_documentos'])
    alvos += [RUNTIME / 'execucoes' / sol] + ([pasta_lote(lote)] if lote else [])
    alvos += [caminho_registrado(a) for a in resultado.get('arquivos_a_remover', [])]
    # todas as saídas desta SOL na pasta da competência (TXT/Excel/balancete, inclusive REVOGADOS e retirados de uso): o número
    # da SOL está no nome de cada arquivo e é único
    if resultado.get('competencia'):
        alvos += sorted((liberados / empresa / resultado['competencia']).glob(f'*{sol}*'))
    for p in alvos:
        if not dentro(p, coordenador.CLIENTES / empresa / 'RECEBIDOS', RUNTIME, liberados):
            pendentes.append(f'{p} (fora das pastas permitidas; não apagado)')
            continue
        if not p.exists():
            continue
        try:
            if p.is_dir():
                def permissao(fn, caminho, _exc):
                    os.chmod(caminho, stat.S_IWRITE)
                    fn(caminho)
                shutil.rmtree(p, onexc=permissao)
            else:
                os.chmod(p, stat.S_IWRITE)
                p.unlink()
        except OSError as exc:
            pendentes.append(f'{p} ({type(exc).__name__})')
    return pendentes


def detalhe_solicitacao(sol: str) -> dict:
    todos = coordenador.ler_registro()
    registro = todos["solicitacoes"].get(sol)
    execucao = ler_json(RUNTIME / "execucoes" / sol / "execucao.json")
    if not registro:
        return None
    execucao = execucao or {'status': 'INDISPONIVEL'}
    lote = (ler_json(pasta_lote(execucao['lote']) / 'lote.json') if execucao.get('lote') else None) or {'arquivos': [], 'instrucao': registro.get('pedido')}
    relatorio_arq = RUNTIME / "execucoes" / sol / "relatorio.md"
    relatorio = relatorio_arq.read_text(encoding="utf-8") if relatorio_arq.exists() else None
    return {
        "sol": sol, "empresa": registro["empresa"], "competencia": registro["competencia"], "modo": registro["modo"],
        "fluxo": registro.get("fluxo", "DOCUMENTOS"),
        "piloto": registro.get("piloto"),
        "estado": registro["estado"], "etapa": registro.get("etapa"), "motivos": registro.get("motivos", []),
        "eventos": registro.get("eventos", []), "instrucao": lote.get("instrucao"),
        "execucao": {k: execucao.get(k) for k in ("status", "inicio", "fim", "auditoria", "documentos_alterados")},
        "etapas": etapas_de(sol, registro, execucao),
        "mensagem": (execucao.get("decisao") or {}).get("mensagem_supervisor"),
        "arquivos": [{k: a.get(k) for k in ("nome_original", "nome_interno", "tamanho", "sha256", "duplicado_de")} for a in lote["arquivos"]],
        "inventario": execucao.get("inventario") or [],
        "documentos_local": execucao.get('documentos_local'),
        "tarefas_areas": registro.get('tarefas_areas', {}),
        "falhas_areas": registro.get('falhas_areas', {}),
        'fiscal': ultimo_concluido(sol,'fiscal'), 'contabilfiscal': ultimo_concluido(sol,'contabilfiscal'),
        'dp': ultimo_concluido(sol, 'dp'), 'contabdp': ultimo_concluido(sol, 'contabdp'),
        'conciliacao': conciliacao_vigente(sol, registro),
        'plano_etapas': registro.get('plano_etapas', []), 'retomadas': registro.get('retomadas', []),
        'retomada_disponivel': bool(registro.get('ancora_documentos') and registro.get('plano_etapas')),
        'aprovacao': registro.get('aprovacao'), 'aprovacoes_anteriores': registro.get('aprovacoes_anteriores', []),
        # bloqueios definitivos; fatos já exportados em TXT revogado não bloqueiam, mas exigem ciência explícita (aprovacao_exige_ciencia)
        'aprovacao_impedimentos': coordenador.impedimentos_aprovacao(registro, todos, True) if registro.get('estado') != 'FECHAMENTO_APROVADO' else [],
        'aprovacao_exige_ciencia': [r['texto'] for r in coordenador.relacao_outras_sols(todos, sol) if r['classificacao'] == 'FATOS_JA_EXPORTADOS']
                                   if registro.get('estado') != 'FECHAMENTO_APROVADO' else [],
        'relacao_outras_sols': coordenador.relacao_outras_sols(todos, sol),
        'vigencia_aprovacao': coordenador.vigencia_aprovacao(registro) if registro.get('estado') == 'FECHAMENTO_APROVADO' else [],
        'situacao_txt': situacao_txt(registro),
        'definicoes_necessarias': governanca_regras.definicoes_necessarias(registro['empresa']),
        'perguntas_supervisor': ((registro.get('conciliacao') or [{}])[-1]).get('perguntas_supervisor', []),
        'frase_aprovacao': f'APROVO FECHAMENTO {sol}',
        "escopo_resultado": registro.get('escopo_resultado', 'PARCIAL_PILOTO_SEM_CONCILIACAO'),
        "revisao_parcial_encerrada": registro.get('revisao_parcial_encerrada', False),
        "pendencias": tabela(relatorio, 5)[1:] if relatorio else [],
        "relatorio": relatorio,
        "tentativas": reprocessamento.comparar(reprocessamento.listar(RUNTIME, sol)),
    }


# ---------------------------------------------------------------- Importação (ESPECÍFICA DA VGROW)

RE_VALOR = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?|\d+(?:\.\d{1,2})?")


def contexto_importacao(sol: str):
    registro = coordenador.ler_registro()["solicitacoes"].get(sol)
    execucao = ler_json(RUNTIME / "execucoes" / sol / "execucao.json")
    if not registro or not execucao:
        return None, (404, "Solicitação não encontrada.")
    if registro["empresa"] != "VGROW" or registro.get("piloto") != coordenador.PILOTO:
        return None, (409, "A área de Importação atende somente SOL piloto da VGROW.")
    if execucao["status"] == "EM_EXECUCAO" or registro["estado"] != "AGUARDANDO_SUPERVISOR":
        return None, (409, "A etapa de Documentos desta SOL ainda não terminou.")
    return (registro, execucao, ler_json(pasta_lote(execucao["lote"]) / "lote.json")), None


def processos_do_lote(lote: dict) -> tuple:
    grupos, sem = {}, []
    for a in lote["arquivos"]:
        proc = importacao_vgrow.processo_de(a["nome_interno"])
        if proc:
            grupos.setdefault(proc, []).append({"nome": a["nome_interno"], "tipo": importacao_vgrow.tipo_de(a["nome_interno"], a["extensao"])})
        else:
            sem.append(a["nome_interno"])
    return grupos, sem


def execucoes_importacao(sol: str) -> list:
    saida = []
    for pasta in sorted((RUNTIME / "execucoes" / sol).glob("importacao-*"), key=lambda p: int(p.name.split("-")[1])):
        r = ler_json(pasta / "resultado.json")
        if r:
            saida.append({"n": int(pasta.name.split("-")[1]), "resultado": r})
    return saida


def valor_decimal(texto) -> str:
    texto = str(texto).strip()
    if not RE_VALOR.fullmatch(texto):
        raise ValueError(f"Valor inválido: {texto[:20]!r} (use 1234,56).")
    return texto.replace(".", "").replace(",", ".") if "," in texto or re.fullmatch(r"\d{1,3}(\.\d{3})+", texto) else texto


def reconhecimento_de(sol: str) -> dict:
    status = ler_json(RUNTIME / "execucoes" / sol / "reconhecimento-status.json") or {"status": "NAO_EXECUTADO"}
    dados = ler_json(RUNTIME / "execucoes" / sol / "reconhecimento.json") if status["status"] == "PRONTO" else None
    return {"status": status["status"], "processos": {p: r["campos"] for p, r in (dados or {}).get("processos", {}).items()},
            "pendencias": {p: r["pendencias"] for p, r in (dados or {}).get("processos", {}).items() if r.get("pendencias")}}


def _reconhecimento_compativel(r: dict) -> dict:
    """Reconhecimentos gravados antes da versão com listas de páginas (ex.: SOL-2026-000015) são lidos sem reprocessar:
    páginas com campos vêm da origem registrada ("OCR p.N") e das DANFEs; submetidas ao OCR só quando o registro diz que
    todas as páginas foram por OCR; sem nº da DUIMP registrado, nenhuma atualização por DUIMP."""
    if "paginas_com_campos" in r:
        return r
    por_campo = {}
    for campo, v in r.get("campos", {}).items():
        m = re.search(r"p\.(\d+)", v.get("origem") or "")
        por_campo[campo] = [int(m.group(1))] if m else []
    por_campo["nfs"] = por_campo["icms_nf"] = sorted({n["pagina"] for n in r.get("notas", []) if "chave" in n})
    todas = list(range(1, r.get("paginas", 0) + 1))
    return dict(r, paginas_com_campos=por_campo, duimp=r.get("duimp", []),
                paginas_submetidas_ocr=todas if r.get("paginas_ocr") == r.get("paginas") else [],
                paginas_sem_campos=sorted(set(todas) - {p for v in por_campo.values() for p in v}))


def evidencias_e_pendencias(sol: str, registro: dict, lote: dict) -> dict:
    """Evidências complementares (o relatório original de Documentos é preservado como histórico) e quadro de pendências:
    texto original de cada P-xx + atualizações SOMENTE por identificador exato (nº da NF, nº da DUIMP, nome do arquivo).
    Nenhum item é encerrado automaticamente: RESOLVIDA só por decisão registrada do Supervisor."""
    pasta = RUNTIME / "execucoes" / sol
    relatorio = (pasta / "relatorio.md").read_text(encoding="utf-8") if (pasta / "relatorio.md").exists() else ""
    rec = {p: _reconhecimento_compativel(r) for p, r in ((ler_json(pasta / "reconhecimento.json") or {}).get("processos", {})).items()}
    execucoes = execucoes_importacao(sol)
    ultimo = execucoes[-1]["resultado"] if execucoes else None
    inventario = (ler_json(pasta / "execucao.json") or {}).get("inventario", [])

    def estado_campo(proc, campo):
        if ultimo:
            for lista in (ultimo["processos_fechados"], ultimo.get("processos_aguardando_aceite", []), ultimo["processos_pendentes"]):
                p = next((x for x in lista if x["processo"] == proc), None)
                origem = ((p or {}).get("valores") or {}).get(campo)
                origem = origem.get("origem") if isinstance(origem, dict) else None
                if origem and "_PELO_SUPERVISOR" in origem:
                    return "CONFIRMADO_PELO_SUPERVISOR", origem
        r = (rec.get(proc) or {}).get("campos", {}).get(campo)
        if r and r.get("valor") is not None:
            return "RECONHECIDO_AGUARDANDO_CONFERENCIA", f"{r['status']} · {r.get('origem', '')}"
        return "NAO_IDENTIFICADO", ""

    evidencias = []
    for a in lote["arquivos"]:
        inv = next((i for i in inventario if i["nome"] == a["nome_interno"]), {})
        e = {"arquivo": a["nome_interno"], "leitura_extrator": inv.get("leitura"),
             "estado": "LIDO_PELO_EXTRATOR" if str(inv.get("leitura", "")).startswith("EXTRAIDO_") else "RECEBIDO_NAO_LIDO"}
        r = next((x for x in rec.values() if x["arquivo"] == a["nome_interno"]), None)
        if r:
            com = sorted({p for v in r["paginas_com_campos"].values() for p in v})
            e["leitura_especifica"] = {"paginas": r["paginas"], "submetidas_ocr": r["paginas_submetidas_ocr"], "com_campos_identificados": com,
                                       "por_campo": r["paginas_com_campos"], "sem_campos_identificados": r["paginas_sem_campos"],
                                       "observacao": "Leitura específica de campos: o documento NÃO foi analisado por inteiro."}
        evidencias.append(e)
    for p in (ultimo or {}).get("processos_pendentes", []):
        for tipo in p.get("documentos_ausentes", []):
            evidencias.append({"arquivo": f"{tipo} do {p['processo']}", "estado": "NAO_RECEBIDO"})

    quadro, decisoes = [], registro.get("decisoes_pendencias", {})
    for linha in tabela(relatorio, 5)[1:]:
        pid, texto = linha[0], " | ".join(linha[1:])
        if not re.fullmatch(r"P-\d{2,3}", pid):
            continue
        atualizacoes = []
        for proc, r in rec.items():
            for nf in (r["campos"].get("nfs") or {}).get("valor") or []:
                if re.search(rf"(?<!\d){nf}(?!\d)", texto):
                    estado, detalhe = estado_campo(proc, "nfs")
                    atualizacoes.append({"item": f"NF {nf}", "estado": estado, "evidencia": f"número (chave de acesso) e ICMS da DANFE, "
                                         f"pág(s) {r['paginas_com_campos']['nfs']}; {detalhe}",
                                         "nao_verificado": "documento completo e valor total da NF não verificados pelo reconhecimento"})
            for duimp in r.get("duimp", []):
                if duimp in texto.replace(" ", ""):
                    estado, detalhe = estado_campo(proc, "fob")
                    atualizacoes.append({"item": f"DUIMP {duimp}", "estado": estado, "evidencia": f"extrato reconhecido na(s) pág(s) "
                                         f"{r['paginas_com_campos']['fob']} (FOB, frete, chegada, fatura); {detalhe}",
                                         "nao_verificado": "demais páginas da DUIMP não analisadas"})
            if r["arquivo"] in texto:
                com = sorted({p for v in r["paginas_com_campos"].values() for p in v})
                atualizacoes.append({"item": r["arquivo"], "estado": "RECEBIDO_NAO_LIDO",
                                     "evidencia": f"não lido pelo extrator; leitura específica: OCR em {len(r['paginas_submetidas_ocr'])} pág(s), "
                                                  f"campos identificados na(s) pág(s) {com}",
                                     "nao_verificado": f"pág(s) {r['paginas_sem_campos']} sem campos identificados (não analisadas)"})
        historico = decisoes.get(pid, [])
        estado = "RESOLVIDA" if historico and historico[-1]["decisao"] == "RESOLVIDA" else ("PARCIALMENTE_ATUALIZADA" if atualizacoes else "ABERTA")
        quadro.append({"pendencia": pid, "texto_original": linha, "atualizacoes": atualizacoes, "estado": estado, "decisoes": historico})

    cadastro = coordenador.empresas_cadastradas().get("VGROW", {}).get("texto", "")
    trava = None
    if "a confirmar" in cadastro.lower() or "Cadastro validado: NÃO" in cadastro:
        trava = {"estado": "TRAVA_OPERACIONAL_PILOTO", "descricao": "Cadastro da VGROW não validado (CNPJ com tipo 'a confirmar'). Trava operacional "
                 "do piloto: impede liberação real; não é regra contábil do material VGROW; não é resolvida pelo reconhecimento automático."}
    return {"evidencias_complementares": evidencias, "quadro_pendencias": quadro, "trava_cadastral": trava}


def mesma(campo: str, a, b) -> bool:
    if a is None or b is None:
        return False
    if campo == "nfs":
        return sorted(map(str, a), key=int) == sorted(map(str, b), key=int)
    if campo in ("fob", "frete", "icms_nf"):
        return Decimal(str(a)) == Decimal(str(b))
    return str(a).strip().upper() == str(b).strip().upper()


def consolidar_conferencia(informados: dict, reconhecidos: dict, confirmados: dict) -> dict:
    """Valor final e origem de cada campo. Campo reconhecido OK pode ser só conferido; ILEGIVEL/AUSENTE/CONFLITO exige
    que o Supervisor confirme a sugestão explicitamente ou corrija o valor (somente nesse campo)."""
    final = {}
    for proc in set(informados) | set(reconhecidos):
        enviados, rec, conf = informados.get(proc, {}), reconhecidos.get(proc, {}), set(confirmados.get(proc, []))
        valores, origens = {}, {}
        for campo in importacao_vgrow.CAMPOS_INFORMADOS:
            r = rec.get(campo) or {"status": "AUSENTE", "valor": None}
            sugestao, status = r.get("valor"), r.get("status")
            enviado = enviados.get(campo)
            if enviado is None:
                if status == "OK":
                    valores[campo], origens[campo] = sugestao, f"RECONHECIDO ({r.get('origem')}) · CONFERIDO_PELO_SUPERVISOR"
                continue
            if mesma(campo, enviado, sugestao):
                if status != "OK" and campo not in conf:
                    raise ValueError(f"{proc}: o campo {campo} está {status}. Confirme a sugestão ou corrija o valor.")
                origem = "CONFERIDO_PELO_SUPERVISOR" if status == "OK" else f"CONFIRMADO_PELO_SUPERVISOR (estava {status})"
                valores[campo], origens[campo] = enviado, f"RECONHECIDO ({r.get('origem')}) · {origem}"
            elif sugestao is not None:
                valores[campo], origens[campo] = enviado, f"CORRIGIDO_PELO_SUPERVISOR (reconhecido: {sugestao if not isinstance(sugestao, list) else '/'.join(sugestao)})"
            else:
                valores[campo], origens[campo] = enviado, f"INFORMADO_PELO_SUPERVISOR (reconhecimento: {status})"
        final[proc] = dict(valores, _origem=origens)
    return final


def validar_informados(corpo: dict, processos: set) -> dict:
    if not isinstance(corpo.get("processos"), dict) or not corpo["processos"]:
        raise ValueError("Envie {processos: {...}}.")
    limpos = {}
    for proc, campos in corpo["processos"].items():
        if proc not in processos:
            raise ValueError(f"Processo {proc[:20]!r} não pertence a este lote.")
        if not isinstance(campos, dict) or set(campos) - set(importacao_vgrow.CAMPOS_INFORMADOS):
            raise ValueError(f"{proc}: campos não permitidos.")
        c = {}
        for k, v in campos.items():
            if v in (None, "", []):
                continue
            if k in ("fob", "frete", "icms_nf"):
                c[k] = valor_decimal(v)
            elif k == "chegada":
                if not isinstance(v, str) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", v):
                    raise ValueError(f"{proc}: data de chegada inválida.")
                dt.date.fromisoformat(v)
                c[k] = v
            elif k == "fatura":
                if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9/._ -]{1,60}", v.strip()):
                    raise ValueError(f"{proc}: fatura inválida.")
                c[k] = v.strip()
            elif k == "nfs":
                lista = v if isinstance(v, list) else re.split(r"[/,; ]+", str(v).strip())
                lista = [str(n).strip() for n in lista if str(n).strip()]
                if not lista or len(lista) > 50 or not all(re.fullmatch(r"\d{1,9}", n) for n in lista):
                    raise ValueError(f"{proc}: números de NF inválidos.")
                c[k] = lista
        limpos[proc] = c
    return limpos


# ---------------------------------------------------------------- HTTP

class Manipulador(BaseHTTPRequestHandler):
    server_version = "AgentesPrimeLocal"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, formato, *args):  # sem log de conteúdo; só método, rota e código
        sys.stderr.write(f"{self.log_date_time_string()} {self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ''}\n")

    # ---- respostas
    def responder(self, codigo: int, corpo: bytes, tipo: str = "application/json; charset=utf-8") -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                         "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(corpo)

    def json(self, codigo: int, dados) -> None:
        self.responder(codigo, json.dumps(dados, ensure_ascii=False).encode("utf-8"))

    def erro(self, codigo: int, mensagem: str) -> None:
        self.json(codigo, {"erro": mensagem})

    # ---- verificações comuns
    def origem_local(self) -> bool:
        permitidos = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.client_address[0] != "127.0.0.1" or self.headers.get("Host") not in permitidos:
            return False
        origem = self.headers.get("Origin")
        if origem and origem not in {f"http://{h}" for h in permitidos}:
            return False
        return self.headers.get("Sec-Fetch-Site") in (None, "same-origin", "none")

    def autenticado(self) -> bool:
        return hmac.compare_digest(self.headers.get("X-Prime-Sessao", ""), self.server.token)

    def corpo_json(self):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Transfer-Encoding não aceito")
        tamanho = int(self.headers.get("Content-Length") or 0)
        limite = 60 * 1024 * 1024 if urlsplit(self.path).path.startswith('/api/empresas') else LIMITE_JSON
        if tamanho > limite:
            raise ValueError("corpo grande demais")
        dados = json.loads(self.rfile.read(tamanho).decode("utf-8") or "{}")
        if not isinstance(dados, dict):
            raise ValueError("JSON inválido")
        return dados

    def despachar(self, metodo: str) -> None:
        if not self.origem_local():
            self.close_connection = True
            return self.erro(403, "Acesso permitido somente pela página local.")
        rota = urlsplit(self.path).path
        if not rota.startswith("/api/"):
            return self.estatico(rota) if metodo == "GET" else self.erro(405, "Método não permitido.")
        if not self.autenticado():
            self.close_connection = True
            return self.erro(401, "Sessão inválida. Recarregue a página.")
        partes = rota.strip("/").split("/")[1:]
        try:
            if partes and partes[0] == 'empresas':
                return self.api_empresas(metodo, partes[1:])
            if partes and partes[0] == 'amostra':
                return self.api_amostra(metodo, partes[1:])
            if metodo == 'GET' and partes == ['solicitacoes']:
                return self.api_solicitacoes()
            if metodo == 'GET' and partes == ['solicitacoes', 'lixeira']:
                return self.api_solicitacoes(lixeira=True)
            if metodo == 'POST' and partes == ['solicitacoes', 'limpar']:
                return self.api_lixeira('limpar')
            if len(partes) == 3 and partes[0] == 'solicitacoes' and RE_SOL.fullmatch(partes[1]) and partes[2] == 'exclusao-definitiva':
                return self.api_exclusao_definitiva(metodo, partes[1])
            if len(partes) >= 2 and partes[0] == 'solicitacoes' and RE_SOL.fullmatch(partes[1]):
                if metodo == 'DELETE' and len(partes) == 2:
                    return self.api_lixeira('excluir', partes[1])
                if metodo == 'POST' and partes[2:] == ['restaurar']:
                    return self.api_lixeira('restaurar', partes[1])
                if metodo != 'GET' and solicitacao_excluida(partes[1]):
                    return self.erro(409, 'Solicitação na lixeira. Restaure antes de registrar decisões ou executar etapas.')
            if metodo == "GET" and partes == ["estado"]:
                return self.api_estado()
            if metodo == "POST" and partes == ["lotes"]:
                return self.api_criar_lote()
            if len(partes) >= 2 and partes[0] == "lotes" and RE_LOTE.fullmatch(partes[1]):
                if metodo == "PUT" and partes[2:] == ["arquivos"]:
                    return self.api_receber_arquivo(partes[1])
                if metodo == "DELETE" and len(partes) == 2:
                    return self.api_descartar(partes[1])
                if metodo == "POST" and partes[2:] == ["iniciar"]:
                    return self.api_iniciar(partes[1])
            if metodo == "GET" and len(partes) == 2 and partes[0] == "solicitacoes" and RE_SOL.fullmatch(partes[1]):
                d = detalhe_solicitacao(partes[1])
                return self.json(200, d) if d else self.erro(404, "Solicitação não encontrada.")
            if metodo == "POST" and len(partes) == 3 and partes[0] == "solicitacoes" and RE_SOL.fullmatch(partes[1]) and partes[2] == "reprocessar":
                return self.api_reprocessar(partes[1])
            if metodo == "POST" and len(partes) == 3 and partes[0] == "solicitacoes" and RE_SOL.fullmatch(partes[1]) and partes[2] == "pendencias":
                return self.api_pendencia_decisao(partes[1])
            if metodo == 'POST' and len(partes) == 3 and partes[0] == 'solicitacoes' and RE_SOL.fullmatch(partes[1]) and partes[2] == 'revisao-piloto':
                return self.api_revisao_piloto(partes[1])
            if metodo == 'POST' and len(partes) == 3 and partes[0] == 'solicitacoes' and RE_SOL.fullmatch(partes[1]) and partes[2] == 'retomar-rota-financeira':
                return self.api_retomar_rota_financeira(partes[1])
            if metodo == 'POST' and len(partes) == 3 and partes[0] == 'solicitacoes' and RE_SOL.fullmatch(partes[1]) and partes[2] == 'aprovacao':
                return self.api_aprovacao(partes[1])
            if metodo == 'GET' and len(partes) == 3 and partes[0] == 'solicitacoes' and RE_SOL.fullmatch(partes[1]) and partes[2] == 'txt-dominio':
                return self.api_txt_dominio(partes[1])
            if (metodo == 'GET' and len(partes) == 4 and partes[0] == 'solicitacoes' and RE_SOL.fullmatch(partes[1]) and partes[2] == 'saidas'
                    and partes[3] in NOMES_ANEXOS):
                return self.api_txt_dominio(partes[1], partes[3])
            if (metodo == 'POST' and len(partes) == 4 and partes[0] == 'solicitacoes' and RE_SOL.fullmatch(partes[1]) and partes[2] == 'txt-dominio'
                    and partes[3] in ('gerar', 'mover-revogado')):
                return self.api_txt_acao(partes[1], partes[3])
            if (metodo == 'POST' and len(partes) == 5 and partes[0] == 'solicitacoes' and RE_SOL.fullmatch(partes[1]) and partes[2] == 'areas'
                    and partes[3] in coordenador.ETAPAS and partes[4] == 'retomar'):
                return self.api_retomar_area(partes[1], partes[3])
            if len(partes) >= 3 and partes[0] == "solicitacoes" and RE_SOL.fullmatch(partes[1]) and partes[2] == "financeiro":
                if metodo == "GET" and len(partes) == 3:
                    return self.api_financeiro_estado(partes[1])
                if metodo == "POST" and partes[3:] == ["decisoes"]:
                    return self.api_financeiro_decisao(partes[1])
                if metodo == "POST" and partes[3:] == ["regras"]:
                    return self.api_financeiro_regra(partes[1])
                if metodo == "POST" and partes[3:] == ["regras", "aprovar"]:
                    return self.api_financeiro_aprovar(partes[1])
                if metodo == "GET" and len(partes) == 5 and re.fullmatch(r"\d{1,3}", partes[3]) and partes[4] == "csv":
                    return self.api_bancos_csv(partes[1], int(partes[3]))
            if len(partes) >= 3 and partes[0] == "solicitacoes" and RE_SOL.fullmatch(partes[1]) and partes[2] == "importacao":
                if not IMPORTACAO_VGROW_ATIVA:
                    return self.erro(410, AVISO_IMPORTACAO)
                if metodo == "GET" and len(partes) == 3:
                    return self.api_importacao_estado(partes[1])
                if metodo == "POST" and len(partes) == 3:
                    return self.api_importacao_executar(partes[1])
                if metodo == "POST" and partes[3:] == ["aceites"]:
                    return self.api_importacao_aceite(partes[1])
                if metodo == "GET" and len(partes) == 5 and re.fullmatch(r"\d{1,3}", partes[3]) and partes[4] in ("txt", "conferencia"):
                    return self.api_importacao_arquivo(partes[1], int(partes[3]), partes[4])
            return self.erro(404, "Rota inexistente.")
        except ValueError as e:
            self.close_connection = True
            return self.erro(400, str(e))
        except Exception:  # noqa: BLE001 — nunca devolver rastreamento técnico à tela
            import traceback
            traceback.print_exc()
            self.close_connection = True
            return self.erro(500, 'Não foi possível concluir a operação por um erro inesperado do aplicativo. Tente novamente; se '
                                  'persistir, avise o responsável técnico (o detalhe ficou registrado no console do servidor).')

    def api_amostra(self, metodo, partes):
        """Amostra FICTÍCIA do percurso completo: preparação explícita (nunca na inicialização) e correção do caso B."""
        if metodo == 'GET' and not partes:
            return self.json(200, amostra_ficticia.situacao())
        if metodo != 'POST' or len(partes) != 1 or partes[0] not in ('preparar', 'corrigir-dp-b'):
            return self.erro(404, 'Rota inexistente.')
        d = self.corpo_json()
        if d.get('confirmado') is not True:
            raise ValueError('Confirme a ação sobre as empresas fictícias da amostra.')
        with TRAVA:
            if EM_EXECUCAO['sol'] or EM_IMPORTACAO['sol'] or coordenador.ler_ordem():
                return self.erro(409, 'Aguarde o processamento atual antes de preparar a amostra.')
            if partes[0] == 'preparar':
                return self.json(200, amostra_ficticia.preparar(RUNTIME, recriar=d.get('recriar') is True))
            return self.json(200, amostra_ficticia.corrigir_referencias_dp_b())

    def api_empresas(self, metodo, partes):
        gestor = empresas_local.Empresas(RAIZ, RUNTIME)
        if metodo == 'GET':
            if len(partes) == 2 and partes[1] == 'regras-area':
                e = gestor.obter(partes[0])
                if e.get('legado'):
                    return self.erro(409, 'Cadastro legado não pode receber referências por esta tela.')
                comp = (parse_qs(urlsplit(self.path).query).get('competencia') or [dt.datetime.now().strftime('%Y-%m')])[0]
                sugestao = regras_areas.sugerir(partes[0], e.get('plano') or [], comp)
                sugestao['plano'] = e.get('plano') or []
                sugestao['arquivos'] = {a: arquivo for a, (_, arquivo) in regras_areas.AREAS.items()}
                return self.json(200, sugestao)
            if len(partes) == 2 and partes[1] == 'exclusao':
                e = gestor.obter(partes[0])
                imp = impedimentos_exclusao_empresa(partes[0])
                return self.json(200, {
                    'empresa': partes[0], 'nome': e.get('nome') or partes[0], 'frase': f'EXCLUIR {partes[0]}',
                    'ja_excluida': bool(e.get('excluida')), 'impedimentos': imp, 'permitida': not imp and not e.get('excluida') and not e.get('legado'),
                    'mensagem': f"Você está excluindo o cadastro operacional da empresa {e.get('nome') or partes[0]}. Os documentos e "
                                "históricos não serão apagados. A empresa deixará de ficar disponível para novas solicitações.",
                    'permanece': ['Documentos recebidos e originais', 'Solicitações e históricos de auditoria',
                                  'Arquivos TXT, Excel e balancetes já gerados', 'Base inicial, balancetes e books enviados'],
                    'bloqueio': 'Não é possível excluir o cadastro enquanto existe uma operação em andamento.' if imp else None})
            if len(partes) == 2 and partes[1] == 'base-inicial':
                comp = (parse_qs(urlsplit(self.path).query).get('competencia') or [None])[0]
                return self.json(200, base_inicial.BaseInicial(gestor).situacao(partes[0], comp))
            if len(partes)>1:
                return self.erro(404, 'Rota inexistente.')
            if len(partes) == 1:
                d = gestor.obter(partes[0])
                d['metodo_fechamento'] = metodo_empresa.carregar(coordenador.CLIENTES / partes[0], partes[0], [d.get('cnpj')])
                d['definicoes_necessarias'] = governanca_regras.definicoes_necessarias(partes[0])
                plano = d.get('plano') or []
                sugestoes = regras_areas.sugerir(partes[0], plano, dt.datetime.now().strftime('%Y-%m'))
                d['referencias_sugeridas'] = sum(1 for area in sugestoes['areas'].values() for item in area['itens'] if item.get('conta'))
                return self.json(200, d)
            excluidas = (parse_qs(urlsplit(self.path).query).get('excluidas') or ['0'])[0] == '1'
            lista = gestor.listar(incluir_excluidas=excluidas)
            for d in lista:
                d.update(resumo_base_empresa(d['id']))
            return self.json(200, lista)
        if metodo != 'POST':
            return self.erro(405, 'Método não permitido.')
        # Modificações de cadastro não concorrem com processamento de SOL.
        with TRAVA:
            if len(partes) == 2 and partes[1] == 'excluir':
                d = self.corpo_json()
                imp = impedimentos_exclusao_empresa(partes[0])
                if imp:
                    return self.erro(409, 'Não é possível excluir o cadastro enquanto existe uma operação em andamento. ' + ' '.join(imp))
                return self.json(200, gestor.excluir(partes[0], d))
            if EM_EXECUCAO['sol'] or EM_IMPORTACAO['sol'] or coordenador.ler_ordem():
                return self.erro(409, 'Aguarde o processamento atual antes de alterar o cadastro.')
            d = self.corpo_json()
            if not partes:
                return self.json(201, gestor.cadastrar(d))
            if len(partes) != 2:
                return self.erro(404, 'Ação inexistente.')
            ident, acao = partes
            if gestor.obter(ident).get('excluida'):
                return self.erro(409, 'O cadastro desta empresa foi excluído; nenhuma alteração é feita. Os históricos continuam disponíveis.')
            if acao in ('estudar', 'decidir-estudo', 'simular-estudo'):
                return self.erro(410, 'O estudo por razão foi removido. Use extratos e documentos do mês no fluxo Financeiro/Bancos.')
            if acao == 'parametros-bancos':
                return self.erro(410, 'A classificação automática em adiantamentos foi removida. Movimentos sem suporte ficam pendentes de classificação.')
            if acao == 'regras-area':
                if 'decisoes' in d:
                    e = gestor.obter(ident)
                    if e.get('legado') or not isinstance(d.get('area'), str):
                        raise ValueError('Empresa ou área inválida.')
                    comp = str(d.get('competencia') or dt.datetime.now().strftime('%Y-%m'))
                    sugestao = regras_areas.sugerir(ident, e.get('plano') or [], comp)
                    sugestao['plano'] = e.get('plano') or []
                    regras_areas.confirmar(gestor.base(ident), sugestao, d['area'], d['decisoes'], comp)
                    return self.json(200, {'resultado': 'REGRAS_AREA_CONFIRMADAS', 'empresa': ident, 'area': d['area'], 'competencia': comp})
                if set(d) != {'area', 'chave', 'frase', 'confirmado'} or d['confirmado'] is not True:
                    raise ValueError('Informe área, chave, frase e confirme.')
                codigo, r = coordenador_cli('aprovar-regra-area', '--empresa', ident, '--area', str(d['area']), '--chave', str(d['chave']),
                                            '--frase', str(d['frase']))
                return self.json(200, r) if codigo == 0 else self.erro(409, r.get('motivo') or 'Confirmação recusada.')
            bi = base_inicial.BaseInicial(gestor)
            funcoes = {'previa': gestor.previa, 'plano': gestor.plano, 'definir-conta': gestor.definir_conta, 'bancos': gestor.bancos,
                       'piloto': gestor.habilitar, 'contas-adiantamento': gestor.contas_adiantamento,
                       'criar-conta': gestor.criar_conta, 'conta-dominio': gestor.conta_dominio,
                       'base-balancete': bi.balancete, 'base-contas': bi.contas, 'base-book': bi.book, 'base-ciencia': bi.ciencia,
                       'base-saldo-inicial': bi.saldo_inicial, 'base-confirmar': bi.confirmar, 'base-reanalisar': bi.reanalisar}
            if acao not in funcoes:
                return self.erro(404, 'Ação inexistente.')
            return self.json(200, funcoes[acao](ident, d))

    def api_exclusao_definitiva(self, metodo, sol):
        """GET = prévia (impedimentos, consequências, o que é apagado e o que permanece). POST = exclusão DEFINITIVA com a frase
        exata; só de SOL que está na lixeira. Não é estorno nem revogação de importação no Domínio."""
        registro = coordenador.ler_registro()
        if sol not in registro['solicitacoes']:
            m = (registro.get('registros_minimos') or {}).get(sol)
            return self.json(200, {'sol': sol, 'ja_excluida': True, 'registro_minimo': m}) if m and metodo == 'GET' else self.erro(404, 'Solicitação não encontrada.')
        prev = coordenador.dependencias_exclusao(registro, sol)
        if not solicitacao_excluida(sol):
            prev['impedimentos'] = ['Mova a solicitação para a lixeira antes da exclusão definitiva.'] + prev['impedimentos']
            prev['permitida'] = False
        prev.pop('exportados', None)
        prev.update(sol=sol, frase=f'EXCLUIR DEFINITIVAMENTE {sol}',
                    aviso='A exclusão definitiva apaga os arquivos da solicitação e não pode ser desfeita. Não estorna nem revoga nada no Domínio.')
        if metodo == 'GET':
            return self.json(200, prev)
        if metodo != 'POST':
            return self.erro(405, 'Método não permitido.')
        d = self.corpo_json()
        if set(d) != {'frase', 'justificativa', 'confirmado'} or d['confirmado'] is not True:
            raise ValueError('Informe a frase, a justificativa e confirme.')
        with TRAVA:
            if EM_EXECUCAO['sol'] or EM_IMPORTACAO['sol'] or EM_FINANCEIRO['sol'] or coordenador.ler_ordem():
                return self.erro(409, 'Aguarde o processamento atual antes de excluir.')
            if not prev['permitida']:
                return self.erro(409, 'Exclusão definitiva recusada: ' + ' '.join(prev['impedimentos']))
            s = registro['solicitacoes'][sol]
            lote = (ler_json(RUNTIME / 'execucoes' / sol / 'execucao.json') or {}).get('lote')
            codigo, r = coordenador_cli('excluir-definitivamente', '--sol', sol, '--frase', str(d['frase']), '--justificativa', str(d['justificativa']))
            if codigo != 0:
                return self.erro(409, r.get('motivo') or 'Exclusão recusada.')
            pendentes = remover_fisicamente(r, s['empresa'], sol, lote)
            coordenador_cli('registrar-remocao', '--sol', sol, '--pendentes', json.dumps(pendentes, ensure_ascii=False))
            lixo = lixeira_solicitacoes()
            lixo['itens'].pop(sol, None)
            lixo['eventos'].append({'sol': sol, 'acao': 'excluir_definitivamente', 'em': agora()})
            gravar_json(RUNTIME / 'lixeira-solicitacoes.json', lixo)
        return self.json(200, {'resultado': 'SOL_EXCLUIDA_DEFINITIVAMENTE', 'sol': sol, 'permanece': r.get('permanece'),
                               'remocao_pendente': pendentes,
                               'mensagem': (f'{sol} excluída definitivamente. Permanece apenas o registro mínimo. ' if not pendentes else
                                            f'{sol} excluída do registro, mas {len(pendentes)} item(ns) não puderam ser apagados (listados). ')
                                           + 'Nada foi estornado no Domínio.'})

    def api_lixeira(self, acao, sol=None):
        d = self.corpo_json()
        if d.get('confirmado') is not True:
            return self.erro(400, 'Confirme a ação antes de continuar.')
        with TRAVA:
            if EM_EXECUCAO['sol'] or EM_IMPORTACAO['sol'] or EM_FINANCEIRO['sol'] or coordenador.ler_ordem():
                return self.erro(409, 'Aguarde o processamento atual antes de alterar a lixeira.')
            registro = coordenador.ler_registro()['solicitacoes']
            if sol and sol not in registro:
                return self.erro(404, 'Solicitação não encontrada.')
            lixo = lixeira_solicitacoes()
            alvos = [sol] if sol else list(registro)
            if acao != 'restaurar':
                aprovadas = [x for x in alvos if registro[x].get('estado') == 'FECHAMENTO_APROVADO' and not lixo['itens'].get(x, {}).get('excluida')]
                if aprovadas:
                    return self.erro(409, 'Solicitação com aprovação VIGENTE não vai para a lixeira: revogue a aprovação antes ('
                                          + ', '.join(aprovadas) + ').')
            # Resultados incompletos após interrupção também exigem conferência antes da limpeza.
            if acao != 'restaurar':
                for item in alvos:
                    if lixo['itens'].get(item, {}).get('excluida'):
                        continue
                    x = ler_json(RUNTIME / 'execucoes' / item / 'execucao.json') or {}
                    etapas = etapas_de(item, registro[item], x)
                    if x.get('status') == 'EM_EXECUCAO' or any(e.get('status') == 'EM_ANDAMENTO' for e in etapas.values()):
                        return self.erro(409, 'Há solicitação em processamento ou com execução interrompida. Confira antes de excluir.')
            alterados = []
            for item in alvos:
                excluida = acao != 'restaurar'
                if bool(lixo['itens'].get(item, {}).get('excluida')) == excluida:
                    continue
                evento = {'sol': item, 'acao': 'excluir' if excluida else 'restaurar', 'em': agora()}
                lixo['itens'][item] = dict(evento, excluida=excluida)
                lixo['eventos'].append(evento)
                alterados.append(item)
            gravar_json(RUNTIME / 'lixeira-solicitacoes.json', lixo)
            return self.json(200, {'alteradas': alterados, 'total': len(alterados),
                                   'mensagem': 'Lista atualizada. Documentos, registros e regras preservados.'})

    def api_solicitacoes(self, lixeira=False):
        lista = []
        lixo = lixeira_solicitacoes()['itens']
        for sol, r in sorted(coordenador.ler_registro()['solicitacoes'].items(), reverse=True):
            if bool(lixo.get(sol, {}).get('excluida')) != lixeira:
                continue
            x = ler_json(RUNTIME / 'execucoes' / sol / 'execucao.json') or {}
            etapas = etapas_de(sol, r, x)
            falha = x.get('status') == 'FALHOU' or any(e.get('status')=='FALHOU' for e in etapas.values())
            bancos = tentativas(sol, 'bancos')
            resultado = ler_json(bancos[-1] / 'resultado.json') if bancos else None
            cf=ultimo_concluido(sol,'contabilfiscal')
            pendencias_fiscais=bool(cf and cf.get('resumo',{}).get('incompletos'))
            pendentes = [l for l in (resultado or {}).get('lancamentos', []) if l['status']=='INCOMPLETO']
            faltas = {f for l in pendentes for f in l.get('faltas_codigos', [])}
            categoria = ('historico' if r['estado'] in ('ENCERRADA','CANCELADA','CONCLUIDA','FECHAMENTO_APROVADO') else 'processando' if r['estado'].endswith('ANDAMENTO') else 'falhas' if falha else
                         'documentos' if resultado and pendentes and faltas and faltas <= {'SUPORTE','DIVERGENCIA','TRANSFERENCIA_SEM_PAR'} else
                         'prontos' if (resultado or cf) and not pendentes and not pendencias_fiscais else
                         'decisoes' if r['estado']=='AGUARDANDO_SUPERVISOR' else 'historico')
            lista.append({'sol': sol, 'empresa': r['empresa'], 'competencia': r['competencia'], 'estado': r['estado'],
                          'fluxo': r.get('fluxo','DOCUMENTOS'), 'etapas': etapas, 'categoria': categoria,
                          'excluida': lixeira, 'excluida_em': lixo.get(sol, {}).get('em') if lixeira else None,
                          'atualizado_em': (r.get('eventos') or [{}])[-1].get('em'),
                          'resumo': (resultado or {}).get('resumo'),
                          'proxima_acao': {'processando':'Aguardar processamento', 'decisoes':'Conferir decisões e pendências',
                                           'documentos':'Providenciar documentos ou esclarecimentos', 'prontos':'Conferir propostas prontas; nada foi escriturado',
                                           'falhas':'Consultar a causa da falha', 'historico':'Consultar histórico'}[categoria]})
        minimos = coordenador.ler_registro().get('registros_minimos') or {}
        excluidas_def = [{k: m.get(k) for k in ('sol', 'empresa', 'competencia', 'situacao', 'situacao_texto', 'excluida_em', 'justificativa',
                                                'permanece', 'remocao_pendente')} | {'fatos_exportados': len(m.get('fatos_exportados') or {})}
                         for _, m in sorted(minimos.items(), reverse=True)] if lixeira else []
        return self.json(200, {'solicitacoes': lista, 'excluidas_definitivamente': excluidas_def, 'na_lixeira': sum(bool(v.get('excluida')) for k,v in lixo.items() if k in coordenador.ler_registro()['solicitacoes']), 'contagem': {k: sum(s['categoria']==k for s in lista) for k in ('processando','decisoes','documentos','prontos','falhas','historico')},
                               'criterio': 'Uma categoria por solicitação: processamento, falha, documento pendente, propostas prontas, decisão ou histórico. Os detalhes podem conter outras pendências.'})

    def api_reprocessar(self, sol: str) -> None:
        """Cria somente o registro de uma nova tentativa; a execução é iniciada por ordem explícita posterior."""
        dados = self.corpo_json()
        if not dados.get("confirmado"):
            return self.erro(400, "Confirme a criação da nova tentativa.")
        motivo = str(dados.get("motivo") or "").strip()
        registro = coordenador.ler_registro()["solicitacoes"].get(sol)
        execucao = ler_json(RUNTIME / "execucoes" / sol / "execucao.json") or {}
        if registro and (ler_json(coordenador.CLIENTES / registro["empresa"] / "empresa-local.json") or {}).get("excluida"):
            registro = dict(registro, empresa_excluida=True)
        lote = ler_json(pasta_lote(execucao.get("lote", "")) / "lote.json") if execucao.get("lote") else None
        if lote and registro:
            destino = coordenador.CLIENTES / registro["empresa"] / lote.get("pasta", "")
            arquivos = [dict(a, caminho=str(destino / a.get("nome_interno", ""))) for a in lote.get("arquivos", [])]
            eleg = reprocessamento.elegibilidade(RUNTIME, sol, registro, execucao,
                                                 ordem_ativa=coordenador.ler_ordem() is not None,
                                                 em_execucao=bool(EM_EXECUCAO["sol"]), raiz=RAIZ,
                                                 documentos_override=arquivos)
        else:
            eleg = {"elegivel": False, "motivos": ["Execução original ou documentos não encontrados."], "documentos": []}
        if not eleg["elegivel"]:
            return self.json(409, {"mensagem": "Reprocessamento bloqueado.", "motivos": eleg["motivos"]})
        atual = reprocessamento.listar(RUNTIME, sol)
        if reprocessamento.ativa(RUNTIME, sol):                 # só PREPARADA/EM_EXECUCAO impedem; finais não
            return self.erro(409, "Já existe uma tentativa de reprocessamento em andamento.")
        nova = reprocessamento.criar(RUNTIME, sol, origem=(atual[-1] if atual else {"numero": 1}),
                                     motivo=motivo, solicitante=str(dados.get("solicitante") or "Supervisor"),
                                     documentos=eleg["documentos"], raiz=RAIZ)
        return self.json(201, {"mensagem": "Nova tentativa criada e registrada para execução auditada.", "tentativa": nova})

    def do_GET(self):
        self.despachar("GET")

    def do_POST(self):
        self.despachar("POST")

    def do_PUT(self):
        self.despachar("PUT")

    def do_DELETE(self):
        self.despachar("DELETE")

    # ---- página (lista fixa de arquivos; nada fora dela é servido)
    def estatico(self, rota: str) -> None:
        arquivo = self.server.paginas.get("/index.html" if rota == "/" else rota)
        if arquivo is None:
            return self.erro(404, "Não encontrado.")
        tipo = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}[arquivo.suffix] + "; charset=utf-8"
        conteudo = arquivo.read_bytes()
        if arquivo.name == "index.html":
            conteudo = conteudo.decode("utf-8").replace("connect-src 'none'", "connect-src 'self'").replace(
                "<head>", f'<head>\n  <meta name="prime-sessao" content="{self.server.token}">', 1).encode("utf-8")
        self.responder(200, conteudo, tipo)

    # ---- API
    def api_estado(self) -> None:
        lixo = lixeira_solicitacoes()['itens']
        registro = coordenador.ler_registro()["solicitacoes"]
        ativas = [p for p in sorted((RUNTIME / "execucoes").glob("SOL-*/execucao.json"), key=lambda p: p.parent.name, reverse=True)
                  if not lixo.get(p.parent.name, {}).get('excluida')]
        # As 10 mais recentes e TODA SOL ainda aberta (mais antiga também): a disponibilidade dos personagens no escritório
        # considera todas as tarefas pendentes; SOL aberta fora da janela não pode soltar ninguém para a copa.
        fechadas = ('ENCERRADA', 'CANCELADA', 'CONCLUIDA', 'FINALIZADA', 'FECHAMENTO_APROVADO')
        execucoes = ativas[:10] + [p for p in ativas[10:] if registro.get(p.parent.name, {}).get('estado') not in fechadas
                                   and registro.get(p.parent.name)]
        recentes = []
        for e in execucoes:
            x = ler_json(e)
            r = registro.get(x["sol"], {})
            recentes.append({"sol": x["sol"], "empresa": r.get("empresa"), "competencia": r.get("competencia"),
                             "estado": r.get("estado"), "execucao": x.get("status"), "etapas": etapas_de(x["sol"], r, x),
                             **resumo_conciliacao(x["sol"], r)})
        autorizadas = empresas_autorizadas()
        self.json(200, {"modo": "OPERACAO_LOCAL", "empresas": list(autorizadas.values()),
                        "empresas_pendentes": empresas_com_cadastro_pendente(autorizadas),
                        "em_execucao": EM_EXECUCAO["sol"], "recentes": recentes,
                        "limites": {"arquivo": LIMITE_ARQUIVO, "lote": LIMITE_LOTE, "arquivos": LIMITE_ARQUIVOS,
                                    "formatos": sorted(FORMATOS)}})

    def api_criar_lote(self) -> None:
        d = self.corpo_json()
        empresa, competencia, instrucao = d.get("empresa"), d.get("competencia"), d.get("instrucao")
        fluxo = d.get("fluxo", "DOCUMENTOS")
        if set(d) - {"empresa", "competencia", "instrucao", "fluxo"}:
            raise ValueError("Campos não permitidos.")
        if fluxo not in coordenador.FLUXOS:
            raise ValueError("Tipo de solicitação inválido.")
        if not isinstance(empresa, str) or empresa not in empresas_autorizadas():
            return self.erro(403, "Empresa não cadastrada ou não autorizada para o Agente de Documentos.")
        if fluxo == "FINANCEIRO_BANCOS" and not coordenador.financeiro_permitido(coordenador.empresas_cadastradas()[empresa]):
            # recusa ANTES de receber arquivos: nada é copiado para a pasta de empresa real
            return self.erro(403, "O fluxo Financeiro → Contabilidade/Bancos exige empresa fictícia ou piloto real AUTORIZADO em SIMULAÇÃO "
                                  "(cadastro, plano, vínculos bancários e autorização específica do Supervisor). Produção continua bloqueada.")
        if not isinstance(competencia, str) or not RE_COMPETENCIA.fullmatch(competencia):
            raise ValueError("Competência deve estar no formato AAAA-MM.")
        if not isinstance(instrucao, str) or not instrucao.strip() or len(instrucao) > LIMITE_INSTRUCAO:
            raise ValueError(f"Instrução obrigatória (até {LIMITE_INSTRUCAO} caracteres).")
        lote = novo_lote_id()
        pasta = pasta_lote(lote)
        (pasta / "arquivos").mkdir(parents=True)
        gravar_json(pasta / "lote.json", {"lote": lote, "empresa": empresa, "competencia": competencia,
                                          "instrucao": instrucao.strip(), "fluxo": fluxo, "criado_em": agora(), "estado": "RECEBENDO", "arquivos": []})
        self.json(201, {"lote": lote})

    def api_receber_arquivo(self, lote_id: str) -> None:
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            return self.erro(411, "Envie o arquivo com Content-Length.")
        try:
            tamanho = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.close_connection = True
            return self.erro(411, "Content-Length obrigatório.")
        nome_original = unquote(self.headers.get("X-Nome-Arquivo", ""))[:300]
        sha_informado = (self.headers.get("X-Sha256") or "").lower()
        pasta = pasta_lote(lote_id)
        with TRAVA:
            lote = ler_json(pasta / "lote.json")
            if not lote or lote["estado"] != "RECEBENDO":
                self.close_connection = True
                return self.erro(409, "Lote inexistente ou já iniciado.")
            nome, ext = saneado(nome_original)
            problema = None
            if nome is None:
                problema = (415, f"Formato não aceito ({ext or 'sem extensão'}). Aceitos: {', '.join(sorted(FORMATOS))}.")
            elif not re.fullmatch(r"[0-9a-f]{64}", sha_informado):
                problema = (400, "SHA-256 do arquivo ausente ou inválido.")
            elif tamanho <= 0 or tamanho > LIMITE_ARQUIVO:
                problema = (413, f"Arquivo vazio ou acima de {LIMITE_ARQUIVO // (1024 * 1024)} MB.")
            elif len(lote["arquivos"]) >= LIMITE_ARQUIVOS:
                problema = (413, f"Lote limitado a {LIMITE_ARQUIVOS} arquivos.")
            elif sum(a["tamanho"] for a in lote["arquivos"]) + tamanho > LIMITE_LOTE:
                problema = (413, f"Lote limitado a {LIMITE_LOTE // (1024 * 1024)} MB.")
            if problema:
                self.close_connection = True
                return self.erro(*problema)
            numero = len(lote["arquivos"]) + 1
            temporario = pasta / "arquivos" / f".parcial-{secrets.token_hex(8)}"
            h, recebido = hashlib.sha256(), 0
            try:
                with open(temporario, "xb") as f:
                    while recebido < tamanho:
                        bloco = self.rfile.read(min(1024 * 1024, tamanho - recebido))
                        if not bloco:
                            break
                        f.write(bloco)
                        h.update(bloco)
                        recebido += len(bloco)
                if recebido != tamanho:
                    raise ValueError("Upload incompleto: o arquivo não foi recebido inteiro.")
                if h.hexdigest() != sha_informado:
                    raise ValueError("Upload corrompido: SHA-256 diferente do calculado pelo navegador.")
                with open(temporario, "rb") as f:
                    if not conteudo_confere(ext, f.read(65536)):
                        raise ValueError(f"O conteúdo do arquivo não corresponde à extensão {ext}.")
                if any(a["sha256"] == sha_informado for a in lote["arquivos"]):
                    temporario.unlink()
                    return self.erro(409, "Arquivo idêntico já enviado neste lote.")
                nome_interno = f"{numero:02d}_{nome}"
                destino = pasta / "arquivos" / nome_interno
                os.rename(temporario, destino)          # falha se já existir: nunca sobrescreve
            except ValueError:
                temporario.unlink(missing_ok=True)
                self.close_connection = True
                raise
            except OSError:
                temporario.unlink(missing_ok=True)
                self.close_connection = True
                return self.erro(500, "Falha ao gravar o arquivo no staging.")
            anterior = None
            for outro in (RUNTIME / "lotes").glob("L-*/lote.json"):
                o = ler_json(outro)
                if o and o["lote"] != lote_id and o["empresa"] == lote["empresa"] and o.get("sol"):
                    if any(a["sha256"] == sha_informado for a in o["arquivos"]):
                        anterior = {"lote": o["lote"], "sol": o["sol"]}
                        break
            registro = {"numero": numero, "nome_original": nome_original, "nome_interno": nome_interno, "extensao": ext,
                        "tamanho": tamanho, "sha256": sha_informado, "duplicado_de": anterior, "recebido_em": agora()}
            lote["arquivos"].append(registro)
            gravar_json(pasta / "lote.json", lote)
        self.json(201, registro)

    def api_descartar(self, lote_id: str) -> None:
        pasta = pasta_lote(lote_id)
        with TRAVA:
            lote = ler_json(pasta / "lote.json")
            if not lote or lote["estado"] != "RECEBENDO":
                return self.erro(409, "Somente lote ainda não iniciado pode ser descartado.")
            # rascunho sem SOL: nada a rastrear — o lote inteiro (documentos e metadados) é apagado
            def permissao(fn, caminho, _exc):
                os.chmod(caminho, stat.S_IWRITE)
                fn(caminho)
            try:
                shutil.rmtree(pasta, onexc=permissao)
            except OSError as exc:
                return self.erro(500, f"Rascunho não pôde ser apagado por completo ({type(exc).__name__}); confira {pasta.name}.")
        self.json(200, {"lote": lote_id, "estado": "EXCLUIDO", "mensagem": "Rascunho excluído: documentos enviados e dados do lote apagados."})

    def api_iniciar(self, lote_id: str) -> None:
        d = self.corpo_json()
        if d != {"conferencia_humana": True}:
            raise ValueError("Confirme a conferência humana do resultado para iniciar.")
        pasta = pasta_lote(lote_id)
        with TRAVA:
            lote = ler_json(pasta / "lote.json")
            if not lote or lote["estado"] != "RECEBENDO":
                return self.erro(409, "Lote inexistente ou já iniciado.")
            if not lote["arquivos"]:
                return self.erro(409, "Envie ao menos um documento.")
            if EM_EXECUCAO["sol"] or coordenador.ler_ordem() is not None:
                return self.erro(409, "Já existe uma solicitação em processamento. Aguarde a conclusão.")
            if lote["empresa"] not in empresas_autorizadas():
                return self.erro(403, "Empresa não autorizada.")
            ano, mes = lote["competencia"].split("-")
            pedido = f"{lote['instrucao']}\n\n[Escritório Virtual] Empresa: {lote['empresa']}. Competência: {mes}/{ano}."
            empresa, problema = coordenador.identificar_empresa(pedido, coordenador.empresas_cadastradas())
            if problema or empresa != lote["empresa"]:
                return self.erro(422, "A instrução cita outra empresa ou não confere com a empresa selecionada. Ajuste a instrução.")
            competencia, problema = coordenador.identificar_competencia(pedido)
            if problema or competencia != lote["competencia"]:
                return self.erro(422, "A instrução cita outra competência. Ajuste a instrução ou a competência selecionada.")
            relativa = f"RECEBIDOS/{lote['competencia']}/{lote_id}"
            destino = coordenador.CLIENTES / lote["empresa"] / relativa
            if destino.exists():
                return self.erro(409, "Destino do lote já existe; nada foi sobrescrito.")
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(pasta / "arquivos", destino)
            for a in lote["arquivos"]:
                arquivo = destino / a["nome_interno"]
                if hashlib.sha256(arquivo.read_bytes()).hexdigest() != a["sha256"]:
                    shutil.rmtree(destino, ignore_errors=True)
                    return self.erro(500, "Falha de integridade ao transferir o lote; nada foi processado.")
                os.chmod(arquivo, stat.S_IREAD)
            codigo, aberto = coordenador_cli("abrir", "--pedido", pedido, "--pasta", relativa, "--fluxo", lote.get("fluxo", "DOCUMENTOS"))
            lote.update(pasta=relativa, iniciado_em=agora())
            if codigo != 0 or aberto.get("resultado") != "SOL_ABERTA":
                lote.update(estado="RECUSADO", recusa=aberto)
                gravar_json(pasta / "lote.json", lote)
                return self.json(422, {"erro": aberto.get("motivo") or "O Coordenador recusou a solicitação.", "coordenador": aberto})
            lote.update(estado="INICIADO", sol=aberto["sol"])
            gravar_json(pasta / "lote.json", lote)
            shutil.rmtree(pasta / "arquivos", ignore_errors=True)
            EM_EXECUCAO["sol"] = aberto["sol"]
            (RUNTIME / "execucoes" / aberto["sol"]).mkdir(parents=True, exist_ok=True)
            gravar_json(RUNTIME / "execucoes" / aberto["sol"] / "execucao.json",
                        {"sol": aberto["sol"], "lote": lote_id, "status": "EM_EXECUCAO", "inicio": agora()})
        threading.Thread(target=processar, args=(lote_id, aberto["sol"], aberto["ordem_de_servico"]), daemon=True).start()
        self.json(202, {"sol": aberto["sol"], "empresa": aberto["empresa"], "competencia": aberto["competencia"], "modo": aberto["modo"],
                        "piloto": aberto.get("piloto")})


    def api_importacao_estado(self, sol: str) -> None:
        ctx, problema = contexto_importacao(sol)
        if problema:
            return self.json(200, {"disponivel": False, "motivo": problema[1]})
        registro, _, lote = ctx
        grupos, sem = processos_do_lote(lote)
        self.json(200, dict({"disponivel": True, "processos": [{"processo": p, "documentos": d} for p, d in sorted(grupos.items())],
                             "sem_processo": sem, "campos": list(importacao_vgrow.CAMPOS_INFORMADOS), "execucoes": execucoes_importacao(sol),
                             "reconhecimento": reconhecimento_de(sol), "aceites": registro.get("aceites", {})},
                            **evidencias_e_pendencias(sol, registro, lote)))

    def executar_importacao(self, sol: str, registro: dict, informados: dict) -> None:
        """Coordenador encaminha à Importação (chamado com a TRAVA). Responde ao navegador."""
        # Cada tentativa tem número próprio: conta também as que falharam (sem resultado), que ficam preservadas.
        # Nenhuma pasta existente é reaproveitada, sobrescrita ou apagada (mkdir com exist_ok=False).
        n = proxima_tentativa(RUNTIME / "execucoes" / sol, "importacao")
        pasta = RUNTIME / "execucoes" / sol / f"importacao-{n}"
        pasta.mkdir(parents=True, exist_ok=False)
        gravar_json(pasta / "informados.json", informados)
        # Processos já fechados em OUTRAS SOLs da VGROW (registro do Coordenador): não lançar de novo; competência
        # já processada → TXT complementar (regra da VGROW). Aceites do Supervisor desta SOL (amarrados por chave).
        ja = [{"occt": occt, "sol": outra, "competencia": s["competencia"]}
              for outra, s in coordenador.ler_registro()["solicitacoes"].items() if outra != sol and s.get("empresa") == "VGROW"
              for x in s.get("importacao", []) for occt in x.get("processos_fechados", [])]
        gravar_json(pasta / "ja-lancados.json", ja)
        gravar_json(pasta / "aceites.json", registro.get("aceites", {}))
        EM_IMPORTACAO["sol"] = sol
        try:
            p = subprocess.run([PY, "-I", str(FERRAMENTA_IMPORTACAO), "--sol", sol, "--competencia", registro["competencia"],
                                "--pasta", registro["pasta"], "--informados", str(pasta / "informados.json"), "--saida", str(pasta),
                                "--ja-lancados", str(pasta / "ja-lancados.json"), "--aceites", str(pasta / "aceites.json")],
                               cwd=RAIZ, capture_output=True, encoding="utf-8")
        finally:
            EM_IMPORTACAO["sol"] = None
        if p.returncode != 0 or not (pasta / "resultado.json").exists():
            return self.erro(500, "A Importação não devolveu resultado ao Coordenador.")
        codigo, registrado = coordenador_cli("registrar-importacao", "--sol", sol, "--resultado", str(pasta / "resultado.json"))
        if codigo != 0:
            return self.erro(409, registrado.get("motivo") or "O Coordenador recusou o resultado da Importação.")
        self.json(200, {"n": n, "resultado": ler_json(pasta / "resultado.json"), "coordenador": registrado})

    def api_importacao_executar(self, sol: str) -> None:
        corpo = self.corpo_json()
        if set(corpo) - {"processos", "confirmados", "conferencia_supervisor"} or corpo.get("conferencia_supervisor") is not True:
            raise ValueError("Confirme que conferiu os campos reconhecidos (conferencia_supervisor) e envie só processos/confirmados.")
        confirmados = corpo.get("confirmados") or {}
        if not isinstance(confirmados, dict) or not all(isinstance(v, list) and set(v) <= set(importacao_vgrow.CAMPOS_INFORMADOS)
                                                        for v in confirmados.values()):
            raise ValueError("Lista de campos confirmados inválida.")
        with TRAVA:
            if EM_EXECUCAO["sol"]:
                return self.erro(409, "Há uma solicitação em processamento. Aguarde.")
            ctx, problema = contexto_importacao(sol)
            if problema:
                return self.erro(*problema)
            registro, _, lote = ctx
            grupos, _ = processos_do_lote(lote)
            reconhecimento = reconhecimento_de(sol)
            if reconhecimento["status"] == "EM_ANDAMENTO":
                return self.erro(409, "O reconhecimento automático dos documentos ainda está em andamento. Aguarde.")
            informados = consolidar_conferencia(validar_informados({"processos": corpo["processos"]}, set(grupos)),
                                                {p: c for p, c in reconhecimento["processos"].items() if p in grupos}, confirmados)
            return self.executar_importacao(sol, registro, informados)

    def api_importacao_aceite(self, sol: str) -> None:
        """Aceite da diferença numerário − saldo − total REAL de um processo, exatamente como exibida no último retorno.
        Registrado pelo Coordenador e a Importação é refeita com os mesmos campos conferidos."""
        corpo = self.corpo_json()
        if set(corpo) != {"processo", "chave"}:
            raise ValueError("Envie {processo, chave}.")
        with TRAVA:
            if EM_EXECUCAO["sol"]:
                return self.erro(409, "Há uma solicitação em processamento. Aguarde.")
            ctx, problema = contexto_importacao(sol)
            if problema:
                return self.erro(*problema)
            execucoes = execucoes_importacao(sol)
            if not execucoes:
                return self.erro(409, "Não há retorno da Importação para aceitar.")
            pedido = next((x["aceite_necessario"] for x in execucoes[-1]["resultado"].get("processos_aguardando_aceite", [])
                           if x["processo"] == corpo["processo"]), None)
            ultimo = execucoes[-1]["n"]
            registrado = (ctx[0].get("aceites") or {}).get(corpo["processo"])
            if registrado and registrado.get("chave") == corpo["chave"]:
                return self.erro(409, f"O aceite desta diferença ({registrado.get('diferenca')}) já foi registrado em {registrado.get('em')} e o "
                                      f"retorno nº {ultimo} já o considera. Nenhum novo aceite foi registrado.")
            if not pedido:
                return self.erro(409, f"O processo {corpo['processo']} não aguarda aceite no último retorno (nº {ultimo}). "
                                      "Nenhum aceite foi registrado.")
            if pedido["chave"] != corpo["chave"]:
                return self.erro(409, "O aceite não corresponde à diferença exibida no último retorno (valores ou documentos mudaram).")
            codigo, r = coordenador_cli("registrar-aceite", "--sol", sol, "--processo", corpo["processo"], "--chave", corpo["chave"],
                                        "--diferenca", pedido["diferenca"])
            if codigo != 0:
                return self.erro(409, r.get("motivo") or "O Coordenador recusou o aceite.")
            registro = coordenador.ler_registro()["solicitacoes"][sol]
            informados = ler_json(RUNTIME / "execucoes" / sol / f"importacao-{execucoes[-1]['n']}" / "informados.json")
            return self.executar_importacao(sol, registro, informados)

    def api_pendencia_decisao(self, sol: str) -> None:
        corpo = self.corpo_json()
        if set(corpo) != {"pendencia", "decisao", "justificativa"} or not all(isinstance(v, str) for v in corpo.values()):
            raise ValueError("Envie {pendencia, decisao, justificativa}.")
        ctx, problema = contexto_importacao(sol)
        if problema:
            return self.erro(*problema)
        registro, _, lote = ctx
        if corpo["pendencia"] not in {q["pendencia"] for q in evidencias_e_pendencias(sol, registro, lote)["quadro_pendencias"]}:
            return self.erro(404, "Pendência não consta no relatório desta SOL.")
        codigo, r = coordenador_cli("registrar-decisao-pendencia", "--sol", sol, "--pendencia", corpo["pendencia"],
                                    "--decisao", corpo["decisao"], "--justificativa", corpo["justificativa"])
        return self.json(200, r) if codigo == 0 else self.erro(400, r.get("motivo") or "Decisão recusada.")

    def api_importacao_arquivo(self, sol: str, n: int, tipo: str) -> None:
        ctx, problema = contexto_importacao(sol)
        if problema:
            return self.erro(*problema)
        pasta = RUNTIME / "execucoes" / sol / f"importacao-{n}"
        nome = ((ler_json(pasta / "resultado.json") or {}).get("arquivos") or {}).get(tipo)
        arquivo = pasta / nome if nome and re.fullmatch(r"[A-Za-z0-9_.-]+", nome) else None
        if not arquivo or not arquivo.is_file():
            return self.erro(404, "Arquivo não gerado nesta execução.")
        conteudo = arquivo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=windows-1252" if tipo == "txt"
                         else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", f'attachment; filename="{nome}"')
        self.send_header("Content-Length", str(len(conteudo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(conteudo)


    # ---- Financeiro → Contabilidade/Bancos (SIMULAÇÃO): leitura, decisões do Supervisor e regras (sempre pelo Coordenador)
    def api_revisao_piloto(self, sol):
        corpo = self.corpo_json()
        if set(corpo) != {'acao', 'justificativa', 'confirmado'} or corpo['confirmado'] is not True:
            raise ValueError('Confirme a revisão parcial e informe ação e justificativa.')
        with TRAVA:
            if EM_EXECUCAO['sol'] or coordenador.ORDEM_ATIVA.exists():
                return self.erro(409, 'Há processamento ativo; aguarde o término.')
            codigo, r = coordenador_cli('revisar-piloto', '--sol', sol, '--acao', str(corpo['acao']), '--justificativa', str(corpo['justificativa']))
        return self.json(200, r) if codigo == 0 else self.erro(409, r.get('motivo') or 'Ação recusada.')

    def api_retomar_rota_financeira(self, sol):
        corpo = self.corpo_json()
        if set(corpo) != {'justificativa', 'confirmado'} or corpo['confirmado'] is not True:
            raise ValueError('Confirme a retomada e informe a justificativa.')
        with TRAVA:
            if EM_EXECUCAO['sol'] or coordenador.ORDEM_ATIVA.exists():
                return self.erro(409, 'Há processamento ativo; aguarde o término.')
            tipos = {}
            extracao = ler_json(RUNTIME / 'execucoes' / sol / 'extracao-local.json') or {}
            manifesto_path = RUNTIME / 'execucoes' / sol / 'documentos-local.json'
            manifesto = ler_json(manifesto_path) or {}
            por_arquivo = {x.get('arquivo'): x for x in extracao.get('arquivos', [])}
            alterados = []
            financeiros = []
            conciliacoes = []
            for item in manifesto.get('itens', []):
                origem = por_arquivo.get(item.get('arquivo'))
                if not origem:
                    continue
                tipo = documentos_local.classificar(origem)
                novo = documentos_local.encaminhamento(origem)
                item['roteamento_anterior'] = {'tipo': item.get('tipo'), 'encaminhamento': item.get('encaminhamento')}
                item['tipo'] = tipo
                item['encaminhamento'] = novo
                alterados.append(item.get('arquivo'))
                tipos[item.get('arquivo')] = tipo
                registro_doc = {'id': 'TD-' + str(item.get('sha256', ''))[:12].upper() + '-FINANCEIRO',
                                'arquivo': item.get('arquivo'), 'sha256': item.get('sha256'), 'papel': 'PRINCIPAL',
                                'situacao': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'leitura': item.get('leitura')}
                financeiros.append(registro_doc)
                if 'CONCILIACAO' in (novo.get('copias_suporte') or []):
                    conciliacoes.append(dict(registro_doc, id=registro_doc['id'].replace('-FINANCEIRO', '-CONCILIACAO'), papel='SUPORTE'))
            if alterados:
                manifesto['reavaliacao_rota'] = {'em': agora(), 'motivo': str(corpo['justificativa']), 'arquivos': alterados}
                manifesto['tarefas_areas'] = {'TRIAGEM': {'area': 'TRIAGEM', 'estado': 'ENCAMINHADO', 'documentos': financeiros},
                                              'FINANCEIRO': {'area': 'FINANCEIRO', 'estado': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'documentos': financeiros},
                                              'CONCILIACAO': {'area': 'CONCILIACAO', 'estado': 'DISPONIVEL_PARA_ENCAMINHAMENTO', 'documentos': conciliacoes}}
                manifesto['pendencias'] = [p for p in manifesto.get('pendencias', []) if 'marcação' in p or 'marcação' in p]
                gravar_json(manifesto_path, manifesto)
            manifesto_sha = hashlib.sha256(manifesto_path.read_bytes()).hexdigest() if manifesto_path.is_file() else ''
            codigo, r = coordenador_cli('retomar-rota-financeira', '--sol', sol, '--justificativa', str(corpo['justificativa']),
                                        '--tipos', json.dumps(tipos, ensure_ascii=False), '--manifesto-sha256', manifesto_sha)
        if codigo != 0:
            return self.erro(409, r.get('motivo') or 'Retomada recusada.')
        iniciar_execucao(sol)
        self.json(202, dict(r, mensagem='Rota determinada automaticamente. Financeiro e Conciliação interna iniciados.'))

    def api_aprovacao(self, sol):
        corpo = self.corpo_json()
        if (set(corpo) - {'acao', 'frase', 'justificativa', 'confirmado', 'ciente_exportados'} or corpo.get('confirmado') is not True
                or corpo.get('acao') not in ('aprovar', 'revogar')):
            raise ValueError('Confirme a ação (aprovar ou revogar) e informe a justificativa.')
        with TRAVA:
            if EM_EXECUCAO['sol'] or coordenador.ORDEM_ATIVA.exists():
                return self.erro(409, 'Há processamento ativo; aguarde o término.')
            codigo, r = coordenador_cli('aprovar-fechamento', '--sol', sol, '--acao', corpo['acao'], '--frase', str(corpo.get('frase') or ''),
                                        '--justificativa', str(corpo.get('justificativa') or ''),
                                        *(['--ciente-exportados'] if corpo.get('ciente_exportados') is True else []))
            if codigo != 0:
                return self.erro(409, r.get('motivo') or 'Ação recusada.')
            r['liberacao'] = liberar_txt(sol) if corpo['acao'] == 'aprovar' else revogar_txt(sol)
        return self.json(200, r)

    def api_txt_acao(self, sol, acao):
        """Ações EXPLÍCITAS do Supervisor (nada é repetido automaticamente): gerar o TXT de novo depois de uma falha corrigida, ou
        tentar de novo mover o arquivo de uma aprovação revogada que estava travado."""
        corpo = self.corpo_json()
        if set(corpo) != {'confirmado', 'justificativa'} or corpo['confirmado'] is not True or not 5 <= len(str(corpo['justificativa']).strip()) <= 300:
            raise ValueError('Confirme a ação e informe a justificativa (5 a 300 caracteres).')
        with TRAVA:
            if EM_EXECUCAO['sol'] or coordenador.ORDEM_ATIVA.exists():
                return self.erro(409, 'Há processamento ativo; aguarde o término.')
            s = coordenador.ler_registro()['solicitacoes'].get(sol)
            if not s:
                return self.erro(404, 'Solicitação não encontrada.')
            if acao == 'gerar':
                lib = (s.get('aprovacao') or {}).get('liberacao_dominio')
                if s.get('estado') != 'FECHAMENTO_APROVADO' or lib not in ('FALHOU', 'AGUARDANDO_GERACAO_TXT', 'PREPARANDO'):
                    return self.erro(409, f'Geração do TXT não disponível (situação {lib or s.get("estado")}).')
                if lib == 'PREPARANDO':
                    preparacao_interrompida(sol)
                return self.json(200, {'liberacao': liberar_txt(sol)})
            ultima = (s.get('aprovacoes_anteriores') or [{}])[-1]
            if s.get('estado') == 'FECHAMENTO_APROVADO' or ultima.get('liberacao_dominio') != 'REVOGADO_ARQUIVO_NAO_MOVIDO':
                return self.erro(409, 'Não há arquivo de aprovação revogada pendente de mover.')
            return self.json(200, {'liberacao': revogar_txt(sol)})

    def api_txt_dominio(self, sol, tipo='txt'):
        registro = coordenador.ler_registro()['solicitacoes'].get(sol) or {}
        aprovacao = registro.get('aprovacao') or {}
        if registro.get('estado') != 'FECHAMENTO_APROVADO' or aprovacao.get('liberacao_dominio') != 'LIBERADO_PARA_IMPORTACAO_MANUAL':
            return self.erro(404, 'Saídas não liberadas para esta solicitação (exige fechamento aprovado e liberação registrada).')
        if tipo != 'txt' and tipo not in (aprovacao.get('anexos') or {}):
            return self.erro(404, f'{tipo.capitalize()} não foi gerado para esta liberação.')
        problemas = problemas_txt(registro)
        if problemas:
            return self.erro(409, 'Download bloqueado: ' + ' '.join(problemas))
        arquivo = caminho_registrado(aprovacao['arquivo_txt'] if tipo == 'txt' else aprovacao['anexos'][tipo]['arquivo'])
        conteudo = arquivo.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=windows-1252' if tipo == 'txt'
                         else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.send_header('Content-Disposition', f'attachment; filename="{arquivo.name}"')
        self.send_header('Content-Length', str(len(conteudo)))
        self.end_headers()
        self.wfile.write(conteudo)

    def api_retomar_area(self, sol, etapa):
        corpo = self.corpo_json()
        if set(corpo) != {'justificativa', 'confirmado'} or corpo['confirmado'] is not True:
            raise ValueError('Confirme a nova tentativa e informe a justificativa.')
        with TRAVA:
            if EM_EXECUCAO['sol'] or coordenador.ORDEM_ATIVA.exists():
                return self.erro(409, 'Há processamento ativo; aguarde o término.')
        registro = coordenador.ler_registro()['solicitacoes'].get(sol)
        if registro and (motivo := problema_ancora(registro, RUNTIME / 'execucoes' / sol)):
            return self.erro(409, motivo)
        codigo, r = coordenador_cli('retomar-area', '--sol', sol, '--etapa', etapa, '--justificativa', str(corpo['justificativa']))
        if codigo != 0:
            return self.erro(409, r.get('motivo') or 'Retomada recusada.')
        iniciar_execucao(sol)
        self.json(202, dict(r, mensagem=f"Nova tentativa de {etapa} iniciada (reexecuta {', '.join(r.get('reexecuta', []))}); "
                                        "tentativas anteriores preservadas."))

    def contexto_financeiro(self, sol: str):
        registro = coordenador.ler_registro()["solicitacoes"].get(sol)
        if not registro:
            return None, (404, "Solicitação não encontrada.")
        if registro.get("fluxo") != "FINANCEIRO_BANCOS":
            return None, (409, "Esta solicitação não é do fluxo Financeiro → Contabilidade/Bancos.")
        return registro, None

    def api_financeiro_estado(self, sol: str) -> None:
        registro, problema = self.contexto_financeiro(sol)
        if problema:
            return self.json(200, {"disponivel": False, "motivo": problema[1]})
        fins, bans = tentativas(sol, "financeiro"), tentativas(sol, "bancos")
        arquivo_regras = coordenador._arquivo_regras(registro["empresa"])
        regras = [dict(zip(["regra", "versao", "condicoes", "tipo", "contrapartida", "exige_suporte", "historico", "origem", "situacao",
                            "aprovacao"], c))
                  for _, c in coordenador._linhas_regras(arquivo_regras.read_text(encoding="utf-8") if arquivo_regras.exists() else "")]
        ultimo_bancos = ultimo_concluido(sol, "bancos")
        self.json(200, {
            "disponivel": True, "estado": registro["estado"], "empresa": registro["empresa"], "competencia": registro["competencia"],
            "em_execucao": EM_EXECUCAO["sol"] == sol, "etapa_em_execucao": EM_FINANCEIRO["etapa"] if EM_FINANCEIRO["sol"] == sol else None,
            "tentativas": {"financeiro": [{"n": int(p.name.split("-")[1]), "concluida": (p / "resultado.json").exists()} for p in fins],
                           "bancos": [{"n": int(p.name.split("-")[1]), "concluida": (p / "resultado.json").exists(),
                                       "financeiro": (ler_json(p / "origem.json") or {}).get("financeiro")} for p in bans]},
            "financeiro": ultimo_concluido(sol, "financeiro"), "bancos": ultimo_bancos,
            "ultima_tentativa_falhou": registro["estado"] == "AGUARDANDO_SUPERVISOR" and any(
                str(m).startswith("FALHA_") for m in registro.get("motivos", [])[:1]),
            "motivos": registro.get("motivos", []),
            "decisoes": registro.get("decisoes_movimentos", {}), "pendencias_documentos": registro.get("pendencias_documentos", []),
            "plano": sorted(coordenador.contas_do_plano(registro["empresa"]), key=lambda c: (len(c), c)), "regras": regras,
            "plano_contas": plano_com_descricao(registro["empresa"]),
            "contas_banco": sorted(coordenador.contas_bancarias_contabeis(registro["empresa"])),
            "contas_adiantamento": coordenador.contas_adiantamento(registro["empresa"]),
            "compatibilidade": {k: {"direcao": v[0], "grupos": sorted(v[1])} for k, v in coordenador.COMPATIBILIDADE.items()},
            "sem_suporte": {"habilitado": False, "automatico_removido": True},
            "metodo_empresa": metodo_empresa.carregar(coordenador.CLIENTES/registro['empresa'], registro['empresa'],
                                                       coordenador.empresas_cadastradas().get(registro['empresa'], {}).get('cnpjs', [])),
            "frase_aprovacao": f"VALIDADO REGRA {registro['empresa']} <RB-NNN>"})

    def api_financeiro_decisao(self, sol: str) -> None:
        corpo = self.corpo_json()
        if set(corpo) != {"movimento", "tipo", "dados", "justificativa"} or not isinstance(corpo["dados"], dict):
            raise ValueError("Envie {movimento, tipo, dados, justificativa}.")
        registro, problema = self.contexto_financeiro(sol)
        if problema:
            return self.erro(*problema)
        ultimo = ultimo_concluido(sol, "financeiro")
        if not ultimo or corpo["movimento"] not in {m["id"] for m in ultimo["movimentos"]}:
            return self.erro(409, "Movimento inexistente na última conferência desta SOL.")
        if corpo["tipo"] == "CONTRAPARTIDA":
            mov = next(m for m in ultimo["movimentos"] if m["id"] == corpo["movimento"])
            direcao = coordenador.COMPATIBILIDADE.get(corpo["dados"].get("natureza_tipo"), (None,))[0]
            if direcao and direcao != mov["direcao"]:
                return self.erro(409, f"Natureza {corpo['dados']['natureza_tipo']} não se aplica a movimento de {mov['direcao']} "
                                      f"({'saída' if mov['direcao'] == 'DEBITO' else 'entrada'} no extrato).")
        if corpo["tipo"] == "VINCULAR":
            validos = {d["id"] for d in ultimo["documentos"]} | {r["id"] for r in ultimo["relacao"]}
            if not set(corpo["dados"].get("vinculos") or []) <= validos:
                return self.erro(409, "Documento ou item da relação inexistente nesta conferência.")
        with TRAVA:
            if EM_EXECUCAO["sol"]:
                return self.erro(409, "Há uma solicitação em processamento. Aguarde.")
        codigo, r = coordenador_cli("registrar-decisao-movimento", "--sol", sol, "--movimento", corpo["movimento"], "--tipo", str(corpo["tipo"]),
                                    "--dados", json.dumps(corpo["dados"], ensure_ascii=False), "--justificativa", str(corpo["justificativa"]))
        if codigo != 0:
            return self.erro(409, r.get("motivo") or "O Coordenador recusou a decisão.")
        iniciar_cadeia_financeira(sol)
        self.json(202, {"resultado": r["resultado"], "mensagem": "Decisão registrada (somente este movimento). Nova tentativa Financeiro → Bancos iniciada."})

    def api_financeiro_regra(self, sol: str) -> None:
        corpo = self.corpo_json()
        registro, problema = self.contexto_financeiro(sol)
        if problema:
            return self.erro(*problema)
        codigo, r = coordenador_cli("propor-regra-bancos", "--sol", sol, "--dados", json.dumps(corpo, ensure_ascii=False))
        if codigo != 0:
            return self.erro(409, r.get("motivo") or "O Coordenador recusou a proposta.")
        self.json(201, r)

    def api_financeiro_aprovar(self, sol: str) -> None:
        corpo = self.corpo_json()
        if set(corpo) != {"regra", "frase"}:
            raise ValueError("Envie {regra, frase}.")
        registro, problema = self.contexto_financeiro(sol)
        if problema:
            return self.erro(*problema)
        with TRAVA:
            if EM_EXECUCAO["sol"]:
                return self.erro(409, "Há uma solicitação em processamento. Aguarde.")
        codigo, r = coordenador_cli("aprovar-regra-bancos", "--sol", sol, "--regra", str(corpo["regra"]), "--frase", str(corpo["frase"]))
        if codigo != 0:
            return self.erro(409, r.get("motivo") or "Aprovação recusada.")
        iniciar_cadeia_financeira(sol)
        self.json(202, dict(r, mensagem=f"{r['regra']} aprovada. Nova tentativa Financeiro → Bancos iniciada para aplicá-la."))

    def api_bancos_csv(self, sol: str, n: int) -> None:
        registro, problema = self.contexto_financeiro(sol)
        if problema:
            return self.erro(*problema)
        arquivo = RUNTIME / "execucoes" / sol / f"bancos-{n}" / f"lancamentos_SIMULACAO_{sol}.csv"
        if not arquivo.is_file():
            return self.erro(404, "Proposta não gerada nesta tentativa.")
        conteudo = arquivo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=windows-1252")
        self.send_header("Content-Disposition", f'attachment; filename="lancamentos_SIMULACAO_{sol}_tentativa{n}.csv"')
        self.send_header("Content-Length", str(len(conteudo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(conteudo)


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, porta: int):
        super().__init__((HOST, porta), Manipulador)
        self.token = secrets.token_urlsafe(32)
        self.paginas = {}
        for arquivo in ESTATICO.rglob("*"):
            if arquivo.is_file() and arquivo.suffix in (".html", ".css", ".js") and "contrato" not in arquivo.parts:
                self.paginas["/" + arquivo.relative_to(ESTATICO).as_posix()] = arquivo


ETAPA_EM_ANDAMENTO = {e + '_EM_ANDAMENTO': e for e in coordenador.ETAPAS}


def reconciliar_interrompidas() -> list:
    """Na partida não há executor ativo: etapa de área que ficou "em andamento" foi interrompida. Registra a falha (tentativa
    preservada) sem repetir nada automaticamente; a SOL volta ao Supervisor com o motivo explícito."""
    tratadas = []
    for sol, s in coordenador.ler_registro()['solicitacoes'].items():
        for _ in range(len(ETAPA_EM_ANDAMENTO)):
            etapa = ETAPA_EM_ANDAMENTO.get(s.get('estado'))
            if not etapa:
                break
            coordenador_cli('registrar-falha-etapa', '--sol', sol, '--etapa', etapa, '--motivo',
                            'Execução interrompida ou não iniciada (servidor reiniciado durante o processamento); não repetida automaticamente.')
            tratadas.append((sol, etapa))
            s = coordenador.ler_registro()['solicitacoes'][sol]
    return tratadas


def iniciar(porta: int = PORTA) -> Servidor:
    global RUNTIME
    RUNTIME = pasta_runtime()
    reconciliar_interrompidas()
    return Servidor(porta)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    servidor = iniciar()
    print(f"Escritório Virtual (operação local): http://127.0.0.1:{servidor.server_port}/")
    print(f"Runtime: {RUNTIME}")
    print("Somente este computador acessa. Ctrl+C encerra.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
