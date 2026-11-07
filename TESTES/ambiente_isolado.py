"""Ambiente ISOLADO para testes: nenhum teste toca o CLIENTES/, o registro, a ordem ativa, o runtime ou o LIBERADOS reais.

Uso (ANTES de importar módulos do aplicativo, que leem as variáveis de ambiente na importação):

    sys.path.insert(0, str(RAIZ / "TESTES"))
    import ambiente_isolado
    AMB = ambiente_isolado.criar("prime-extrator-", fixtures=("EMPRESA-TESTE", "EMPRESA-ISOLAMENTO"), com_guarda=True)
    AMB.clientes   # CLIENTES temporário (cópia das fixtures FICTÍCIAS de TESTES/FIXTURES-FICTICIAS)
    AMB.raiz       # raiz temporária do "projeto" (onde fica a cópia do guarda, se pedida)

- As fixtures são empresas FICTÍCIAS (TESTES/FIXTURES-FICTICIAS); dados reais nunca são usados.
- O guarda (AGENTES/DOCUMENTOS/ferramentas/guarda_agente.py) localiza CLIENTES e a ordem ativa pela própria posição no
  disco; para testá-lo sem tocar o estado operacional, uma CÓPIA dele é colocada na raiz temporária (o código do guarda
  não é alterado) e AGENTES_PRIME_ORDEM_ATIVA aponta para a ordem ativa dessa raiz, que o guarda copiado lê.
- Tudo é apagado ao final do processo (atexit).
"""
import atexit
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = RAIZ / "TESTES" / "FIXTURES-FICTICIAS"
GUARDA = RAIZ / "AGENTES" / "DOCUMENTOS" / "ferramentas" / "guarda_agente.py"
REGISTRO_OPERACIONAL = RAIZ / "COORDENADOR-GERAL" / "controle" / "solicitacoes.json"
TENTATIVAS_LEITURA, ESPERA_LEITURA = 40, 0.05          # mesmo limite da leitura de produção (coordenador.com_nova_tentativa, ~2 s)


def ler_json_substituido(caminho, tentativas: int = TENTATIVAS_LEITURA, espera: float = ESPERA_LEITURA):
    """Lê um JSON que outro processo grava por SUBSTITUIÇÃO ATÔMICA (temporário completo + os.replace, como
    coordenador.gravar_json). No Windows, abrir o arquivo no instante exato da troca gera PermissionError (violação de
    compartilhamento): só esse erro é repetido, no máximo `tentativas` vezes; persistindo, é propagado (nunca escondido).
    JSON inválido NÃO é repetido: com gravação atômica, conteúdo parcial seria defeito real e deve aparecer como erro."""
    caminho = Path(caminho)
    for i in range(tentativas):
        try:
            texto = caminho.read_text(encoding="utf-8")
        except PermissionError:
            if i == tentativas - 1:
                raise
            time.sleep(espera)
            continue
        return json.loads(texto)


def registro_isolado(padrao=None):
    """Registro de solicitações do AMBIENTE ISOLADO (AGENTES_PRIME_REGISTRO_SOL). Recusa o registro operacional; sem a variável,
    falha (nunca cai no caminho padrão do projeto). Arquivo ainda inexistente → `padrao` ({"solicitacoes": {}})."""
    arq = Path(os.environ["AGENTES_PRIME_REGISTRO_SOL"])
    if arq.resolve() == REGISTRO_OPERACIONAL.resolve():
        raise RuntimeError("Teste tentou ler o registro OPERACIONAL de solicitações; use um ambiente isolado.")
    if not arq.is_file():
        return {"solicitacoes": {}} if padrao is None else padrao
    return ler_json_substituido(arq)


class Ambiente:
    def __init__(self, raiz: Path):
        self.raiz = raiz
        self.clientes = raiz / "CLIENTES"
        self.ordem = raiz / "AGENTES" / "DOCUMENTOS" / "controle" / "ordem-ativa.json"
        self.guarda = raiz / "AGENTES" / "DOCUMENTOS" / "ferramentas" / "guarda_agente.py"
        self.registro = raiz / "controle" / "solicitacoes.json"
        self.runtime = raiz / "runtime"
        self.liberados = raiz / "LIBERADOS"


def criar(prefixo: str = "prime-teste-", fixtures=(), com_guarda: bool = False) -> Ambiente:
    raiz = Path(tempfile.mkdtemp(prefix=prefixo))
    amb = Ambiente(raiz)
    amb.clientes.mkdir()
    amb.ordem.parent.mkdir(parents=True)
    amb.registro.parent.mkdir(parents=True)
    for nome in fixtures:
        shutil.copytree(FIXTURES / nome, amb.clientes / nome)
    if com_guarda:
        amb.guarda.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(GUARDA, amb.guarda)
    os.environ.update({
        "AGENTES_PRIME_CLIENTES": str(amb.clientes),
        "AGENTES_PRIME_ORDEM_ATIVA": str(amb.ordem),
        "AGENTES_PRIME_REGISTRO_SOL": str(amb.registro),
        "AGENTES_PRIME_RUNTIME": str(amb.runtime),
        "AGENTES_PRIME_LIBERADOS": str(amb.liberados),
        "AGENTES_PRIME_CLAUDE": str(raiz / "claude-inexistente.exe"),
        "LOCALAPPDATA": str(raiz / "localappdata"),
    })
    atexit.register(shutil.rmtree, raiz, ignore_errors=True)
    return amb
