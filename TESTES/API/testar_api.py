"""Bateria da API LOCAL CONTROLADA (A-01..A-27). Não executa o Claude: o agente é substituído por um executor
simulado que devolve um RELATÓRIO FICTÍCIO (identificado como tal). O Coordenador, o extrator, o guarda e o upload são
os reais.

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/API/testar_api.py

Usa runtime e registro de SOL temporários (fora do projeto) e documentos fictícios da EMPRESA-TESTE. Remove ao final
CLIENTES/EMPRESA-TESTE/RECEBIDOS/. Aborta sem fazer nada se existir ordem ativa ou RECEBIDOS da EMPRESA-TESTE.
"""

import hashlib
import http.client
import json
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote

RAIZ = Path(__file__).resolve().parents[2]
# Ambiente ISOLADO (TESTES/ambiente_isolado.py): EMPRESA-TESTE FICTÍCIA num CLIENTES temporário; runtime, registro, ordem
# ativa e LIBERADOS temporários. Nada operacional é lido ou alterado.
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado  # noqa: E402
AMB = ambiente_isolado.criar("prime-api-", fixtures=("EMPRESA-TESTE", "EMPRESA-ISOLAMENTO"))
# cadastros FICTÍCIOS de "empresa real": um com a autorização exata do piloto e outro sem autorização (deve ficar fora da lista)
for _ident, _linha in (("CLIENTE-PILOTO-TESTE", "- Agente de Documentos: PILOTO SUPERVISIONADO AUTORIZADO"),
                       ("CLIENTE-SEM-AUTORIZACAO-TESTE", None)):
    (AMB.clientes / _ident).mkdir()
    _texto = [f"# CADASTRO - {_ident}", "", f"- Identificador: {_ident}", f"- Razão social: {_ident} LTDA", "",
              "## Situação", "- Status: EM CADASTRO"] + ([_linha] if _linha else [])
    (AMB.clientes / _ident / "CADASTRO.md").write_text("\n".join(_texto) + "\n", encoding="utf-8")
TMP = AMB.raiz
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import servidor  # noqa: E402

ORDEM = AMB.ordem
RECEBIDOS = AMB.clientes / "EMPRESA-TESTE" / "RECEBIDOS"
DOCS = AMB.clientes / "EMPRESA-TESTE" / "TREINAMENTO" / "2026-09" / "DOCUMENTOS"
D1 = (DOCS / "D1_NF_COMPRA_FORNECEDOR.txt").read_bytes()
D2 = (DOCS / "D2_COMPROVANTE_TARIFA_BANCARIA.txt").read_bytes()
PDF = (AMB.clientes / "EMPRESA-TESTE/T004/PDF/PDF-01_nf_servico.pdf").read_bytes()
PNG = (AMB.clientes / "EMPRESA-TESTE/T004/SCAN/SCAN-03_recibo.png").read_bytes()
resultados = []
CONTROLE = {"modo": "ok", "liberar": threading.Event()}

RELATORIO = """<!-- RELATÓRIO FICTÍCIO DO EXECUTOR SIMULADO (teste da API; não produzido pelo Agente de Documentos) -->
▶ EMPRESA: EMPRESA-TESTE | CNPJ: 11.111.111/1111-11 | COMPETÊNCIA: 2026-09 | MODO: SIMULAÇÃO
RELATÓRIO DO AGENTE DE DOCUMENTOS - {sol}

## 1. Inventário
| # | Arquivo | Tamanho (bytes) | SHA-256 (12 primeiros) | Leitura (código do extrator) | Marcações | Partes recebidas/total | Analisado? |
|---|---|---|---|---|---|---|---|
| 1 | 01_D1.txt | 1 | x | EXTRAIDO_TEXTO | nenhuma | 1/1 | SIM |

## 5. Pendências propostas (para PENDENCIAS.md - gravação pelo Coordenador)
| Nº provisório | Competência | Tipo | Descrição | Documento | Responsável sugerido | Status sugerido |
|---|---|---|---|---|---|---|
| P-01 | 2026-09 | Esclarecimento | Pendência fictícia de teste | 01_D1.txt | Cliente | Aguardando informação |

## 6. Documentos não analisados
| Arquivo | Código do extrator | Motivo (observação do extrator) | Pendência proposta |
|---|---|---|---|
| Nenhum | — | — | — |

## 7. Tarefas da ordem de serviço
| Tarefa | Situação | Observação |
|---|---|---|
| (1) Inventário | EXECUTADA | — |
"""


def executor_simulado(ordem_de_servico, pasta):
    sol = next(l.split("SOL:")[1].strip() for l in ordem_de_servico.splitlines() if "SOL:" in l)
    if CONTROLE["modo"] == "lento":
        CONTROLE["liberar"].wait(30)
    if CONTROLE["modo"] == "sem_relatorio":
        return {"relatorio": None, "problemas": ["O Agente de Documentos não entregou relatório ao Coordenador."], "ferramentas": {}, "bloqueios": 0}
    return {"relatorio": RELATORIO.format(sol=sol), "problemas": [], "ferramentas": {"Read": 2, "Bash": 3, "SubagentHandback": 1}, "bloqueios": 0}


servidor.EXECUTAR_AGENTE = executor_simulado


def remover(pasta):
    """rmtree que tolera o atributo somente leitura aplicado pelo OneDrive a pastas recém-criadas."""
    def forcar(funcao, caminho, _erro):
        os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD)
        funcao(caminho)
    shutil.rmtree(pasta, onexc=forcar)


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), detalhe))


def pedido(metodo, rota, corpo=None, cabecalhos=None, host=None, token=True):
    c = http.client.HTTPConnection("127.0.0.1", PORTA, timeout=30)
    c.putrequest(metodo, rota, skip_host=True, skip_accept_encoding=True)
    c.putheader("Host", host or f"127.0.0.1:{PORTA}")
    h = dict(cabecalhos or {})
    if token:
        h.setdefault("X-Prime-Sessao", SRV.token)
    if isinstance(corpo, (dict, list)):
        corpo = json.dumps(corpo).encode()
        h.setdefault("Content-Type", "application/json")
    if corpo is not None:
        h.setdefault("Content-Length", str(len(corpo)))
    for k, v in h.items():
        c.putheader(k, v)
    c.endheaders()
    if corpo is not None:
        c.send(corpo)
    r = c.getresponse()
    dados = r.read()
    c.close()
    try:
        return r.status, json.loads(dados), r
    except json.JSONDecodeError:
        return r.status, dados.decode("utf-8", "replace"), r


def enviar(lote, nome, conteudo, sha=None):
    return pedido("PUT", f"/api/lotes/{lote}/arquivos", conteudo,
                  {"X-Nome-Arquivo": quote(nome), "X-Sha256": sha or hashlib.sha256(conteudo).hexdigest()})


def novo_lote(instrucao="Chegaram documentos. Inicie o processamento.", empresa="EMPRESA-TESTE", competencia="2026-09"):
    c, d, _ = pedido("POST", "/api/lotes", {"empresa": empresa, "competencia": competencia, "instrucao": instrucao})
    return c, d


def esperar(sol, limite=120):
    fim = time.time() + limite
    while time.time() < fim:
        c, d, _ = pedido("GET", f"/api/solicitacoes/{sol}")
        if c == 200 and d["execucao"]["status"] != "EM_EXECUCAO":
            return d
        time.sleep(0.5)
    return None


def staging(lote):
    return Path(os.environ["AGENTES_PRIME_RUNTIME"]) / "lotes" / lote / "arquivos"


def bateria():
    # A-01..A-07 fronteira de rede e sessão
    registrar("A-01 escuta somente em 127.0.0.1", SRV.server_address[0] == "127.0.0.1" and servidor.HOST == "127.0.0.1")
    c, pagina, r = pedido("GET", "/", token=False)
    registrar("A-02 página com token de sessão e CSP local", c == 200 and SRV.token in pagina and "connect-src 'self'" in pagina
              and "frame-ancestors 'none'" in r.getheader("Content-Security-Policy", ""))
    c1 = pedido("GET", "/api/estado", host="evil.example:80")[0]
    c2 = pedido("GET", "/", host=f"127.0.0.1:{PORTA + 1}", token=False)[0]
    c3 = pedido("GET", "/api/estado", host=f"192.168.0.10:{PORTA}")[0]
    registrar("A-03 Host diferente (DNS rebinding) recusado", c1 == c2 == c3 == 403)
    c1 = pedido("GET", "/api/estado", token=False)[0]
    c2 = pedido("GET", "/api/estado", cabecalhos={"X-Prime-Sessao": "x" * 43})[0]
    registrar("A-04 API sem token ou com token errado", c1 == c2 == 401)
    c1 = pedido("GET", "/api/estado", cabecalhos={"Origin": "https://evil.example"})[0]
    c2 = pedido("POST", "/api/lotes", {"empresa": "EMPRESA-TESTE"}, cabecalhos={"Sec-Fetch-Site": "cross-site"})[0]
    registrar("A-05 outra origem recusada", c1 == c2 == 403)
    rotas = ["/../CLAUDE.md", "/%2e%2e/CLAUDE.md", "/contrato/SEGURANCA.md", "/dados/../../CLAUDE.md",
             "/../CLIENTES/EMPRESA-TESTE/CADASTRO.md", "/LEIA-ME.md", "/js/../../API-LOCAL/servidor.py"]
    obtidos = [pedido("GET", r, token=False) for r in rotas]
    registrar("A-06 nenhum arquivo fora da lista fixa da página", all(c in (403, 404) and "AGENTES PRIME" not in str(d)[:400] or c == 404 for c, d, _ in obtidos),
              " ".join(str(c) for c, _, _ in obtidos))
    c, e, _ = pedido("GET", "/api/estado")
    ids = sorted(x["id"] for x in e["empresas"])
    piloto = [x["id"] for x in e["empresas"] if x.get("piloto") == "PILOTO_REAL_SUPERVISIONADO"]
    registrar("A-07 só empresas autorizadas (fictícias + piloto explícito)", c == 200 and ids == ["CLIENTE-PILOTO-TESTE", "EMPRESA-ISOLAMENTO", "EMPRESA-TESTE"]
              and piloto == ["CLIENTE-PILOTO-TESTE"], ", ".join(ids) + f" · piloto: {piloto}")

    # A-08 validação do lote
    casos = [({"empresa": "EMPRESA-REAL-NAO-AUTORIZADA", "competencia": "2026-09", "instrucao": "x"}, 403),
             ({"empresa": "../EMPRESA-TESTE", "competencia": "2026-09", "instrucao": "x"}, 403),
             ({"empresa": "_MODELO", "competencia": "2026-09", "instrucao": "x"}, 403),
             ({"empresa": "EMPRESA-TESTE", "competencia": "2026-13", "instrucao": "x"}, 400),
             ({"empresa": "EMPRESA-TESTE", "competencia": "09/2026", "instrucao": "x"}, 400),
             ({"empresa": "EMPRESA-TESTE", "competencia": "2026-09", "instrucao": "  "}, 400),
             ({"empresa": "EMPRESA-TESTE", "competencia": "2026-09", "instrucao": "x", "pasta": "C:/"}, 400)]
    obtidos = [pedido("POST", "/api/lotes", d)[0] for d, _ in casos]
    registrar("A-08 empresa/competência/instrução/campos extras validados", obtidos == [e for _, e in casos], " ".join(map(str, obtidos)))

    # A-09..A-17, A-27 upload
    _, d = novo_lote()
    lote = d["lote"]
    c, r, _ = enviar(lote, "..\\..\\..\\CLIENTES\\EMPRESA-ISOLAMENTO\\nota fiscal(1).TXT", D1)
    dentro = c == 201 and (staging(lote) / r["nome_interno"]).is_file() and r["nome_interno"] == "01_nota_fiscal_1_.txt"
    registrar("A-09 nome com caminho é saneado e fica no staging", dentro, r.get("nome_interno") if isinstance(r, dict) else r)
    obtidos = [enviar(lote, n, b"conteudo")[0] for n in ("virus.exe", "pacote.zip", "carta.docx", "pagina.html", "sem_extensao", "CON.pdf", ".pdf")]
    registrar("A-10 extensões fora da lista fechada e nomes reservados", all(x == 415 for x in obtidos), " ".join(map(str, obtidos)))
    c1 = enviar(lote, "imagem_disfarcada.pdf", PNG)[0]
    c2 = enviar(lote, "binario.txt", b"abc\x00def")[0]
    c3 = enviar(lote, "pdf_como_xml.xml", PDF)[0]
    registrar("A-11/A-27 conteúdo diferente da extensão recusado", c1 == c2 == c3 == 400)
    c = enviar(lote, "d2.txt", D2, sha="0" * 64)[0]
    sobras = [p.name for p in staging(lote).iterdir() if p.name.startswith(".parcial")]
    registrar("A-12 SHA-256 divergente recusado sem resíduo", c == 400 and not sobras)
    s = socket.create_connection(("127.0.0.1", PORTA))
    s.sendall((f"PUT /api/lotes/{lote}/arquivos HTTP/1.1\r\nHost: 127.0.0.1:{PORTA}\r\nX-Prime-Sessao: {SRV.token}\r\n"
               f"X-Nome-Arquivo: parcial.txt\r\nX-Sha256: {hashlib.sha256(D2).hexdigest()}\r\nContent-Length: {len(D2)}\r\n\r\n").encode() + D2[:50])
    s.shutdown(socket.SHUT_WR)
    resposta = s.recv(4096).decode("utf-8", "replace")
    s.close()
    time.sleep(0.3)
    sobras = [p.name for p in staging(lote).iterdir() if p.name.startswith(".parcial")]
    lote_json = json.loads((staging(lote).parent / "lote.json").read_text(encoding="utf-8"))
    registrar("A-13 upload incompleto falha sem resíduo", " 400 " in resposta.split("\r\n")[0] + " " and not sobras and len(lote_json["arquivos"]) == 1,
              resposta.split("\r\n")[0])
    c = pedido("PUT", f"/api/lotes/{lote}/arquivos", None, {"X-Nome-Arquivo": "grande.pdf", "X-Sha256": "a" * 64,
                                                            "Content-Length": str(servidor.LIMITE_ARQUIVO + 1)})[0]
    registrar("A-14 arquivo acima do limite recusado antes de receber", c == 413)
    c1, _, _ = enviar(lote, "d2.txt", D2)
    c2, r2, _ = enviar(lote, "copia_d2.txt", D2)
    registrar("A-15 arquivo idêntico no mesmo lote recusado", c1 == 201 and c2 == 409)
    antigo = servidor.LIMITE_ARQUIVOS
    servidor.LIMITE_ARQUIVOS = 2
    c = enviar(lote, "terceiro.pdf", PDF)[0]
    servidor.LIMITE_ARQUIVOS = antigo
    registrar("A-16 limite de arquivos por lote", c == 413)
    c = pedido("PUT", f"/api/lotes/{lote}/arquivos", None, {"X-Nome-Arquivo": "x.txt", "X-Sha256": "a" * 64, "Transfer-Encoding": "chunked"})[0]
    registrar("A-17 envio sem Content-Length (chunked) recusado", c == 411)

    # A-18 início
    c1 = pedido("POST", f"/api/lotes/{lote}/iniciar", {})[0]
    _, d = novo_lote("Processe os documentos da EMPRESA-ISOLAMENTO.")
    enviar(d["lote"], "d1.txt", D1)
    c2 = pedido("POST", f"/api/lotes/{d['lote']}/iniciar", {"conferencia_humana": True})[0]
    _, d = novo_lote("Documentos referentes a 08/2026.")
    enviar(d["lote"], "d1.txt", D1)
    c3 = pedido("POST", f"/api/lotes/{d['lote']}/iniciar", {"conferencia_humana": True})[0]
    registrar("A-18 sem confirmação / outra empresa / outra competência recusados", c1 == 400 and c2 == c3 == 422 and not RECEBIDOS.exists(),
              f"{c1} {c2} {c3}; nada movido para CLIENTES")

    # A-19 fluxo completo (executor simulado; Coordenador, extrator e decisão reais)
    c, r, _ = pedido("POST", f"/api/lotes/{lote}/iniciar", {"conferencia_humana": True})
    sol = r.get("sol") if isinstance(r, dict) else None
    d = esperar(sol) if sol else None
    destino = RECEBIDOS / "2026-09" / lote
    arquivos = sorted(p.name for p in destino.iterdir()) if destino.exists() else []
    somente_leitura = all(not (p.stat().st_mode & stat.S_IWRITE) for p in destino.iterdir()) if destino.exists() else False
    registrar("A-19 fluxo completo até a decisão do Coordenador", c == 202 and d and d["estado"] == "PRONTO_PARA_FINANCEIRO"
              and d["execucao"]["status"] == "CONCLUIDA" and arquivos == ["01_nota_fiscal_1_.txt", "02_d2.txt"] and somente_leitura
              and not ORDEM.exists() and not staging(lote).exists() and len(d["inventario"]) == 2 and len(d["pendencias"]) == 1
              and d["relatorio"].startswith("<!-- RELATÓRIO FICTÍCIO"),
              f"{sol} → {d and d['estado']}; documentos somente leitura em RECEBIDOS; ordem removida")
    c = pedido("DELETE", f"/api/lotes/{lote}")[0]
    registrar("A-26 lote iniciado não pode ser descartado", c == 409)

    # A-20 uma execução por vez
    CONTROLE["modo"] = "lento"
    CONTROLE["liberar"].clear()
    _, d1 = novo_lote()
    enviar(d1["lote"], "pdf.pdf", PDF)
    c1, r1, _ = pedido("POST", f"/api/lotes/{d1['lote']}/iniciar", {"conferencia_humana": True})
    _, d2 = novo_lote()
    enviar(d2["lote"], "png.png", PNG)
    c2 = pedido("POST", f"/api/lotes/{d2['lote']}/iniciar", {"conferencia_humana": True})[0]
    CONTROLE["liberar"].set()
    fim = esperar(r1["sol"])
    CONTROLE["modo"] = "ok"
    registrar("A-20 segunda solicitação recusada durante o processamento", c1 == 202 and c2 == 409 and fim is not None)

    # A-21 sem relatório → AGUARDANDO_SUPERVISOR
    CONTROLE["modo"] = "sem_relatorio"
    c, r, _ = pedido("POST", f"/api/lotes/{d2['lote']}/iniciar", {"conferencia_humana": True})
    d = esperar(r["sol"])
    CONTROLE["modo"] = "ok"
    registrar("A-21 sem relatório entregue → AGUARDANDO_SUPERVISOR", d and d["estado"] == "AGUARDANDO_SUPERVISOR" and d["execucao"]["status"] == "FALHOU"
              and any("não pôde ser lido" in m for m in d["motivos"]) and not ORDEM.exists())

    # A-22 duplicidade entre lotes
    _, d = novo_lote()
    c, r, _ = enviar(d["lote"], "d1_de_novo.txt", D1)
    registrar("A-22 arquivo já processado em outra SOL é sinalizado", c == 201 and r["duplicado_de"] and r["duplicado_de"]["sol"] == sol)
    pedido("DELETE", f"/api/lotes/{d['lote']}")

    # A-23 runtime em pasta sincronizada / dentro do projeto recusado
    recusas = 0
    for proibido in (str(RAIZ / "runtime"), str(Path.home() / "OneDrive" / "runtime")):
        os.environ["AGENTES_PRIME_RUNTIME"] = proibido
        try:
            servidor.pasta_runtime()
        except SystemExit:
            recusas += 1
    os.environ["AGENTES_PRIME_RUNTIME"] = str(TMP / "runtime")
    registrar("A-23 runtime no projeto ou no OneDrive recusado", recusas == 2)

    # A-24/A-25 rotas inexistentes e identificadores inválidos
    obtidos = [pedido("POST", "/api/executar", {"cmd": "dir"})[0], pedido("POST", "/api/agentes/agente-financeiro", {})[0],
               pedido("GET", "/api/arquivo?caminho=C:/Windows/win.ini")[0], pedido("PUT", "/api/lotes/../../x/arquivos", b"x")[0],
               pedido("GET", "/api/solicitacoes/SOL-2026-99")[0], pedido("POST", "/api/lotes/L-1/iniciar", {"conferencia_humana": True})[0]]
    registrar("A-24/A-25 sem rota de shell, caminho ou agente; ids validados", all(c == 404 for c in obtidos), " ".join(map(str, obtidos)))


def limpar_recebidos():
    if RECEBIDOS.exists():
        for p in RECEBIDOS.rglob("*"):
            if p.is_file():
                os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
        remover(RECEBIDOS)


def main():
    global SRV, PORTA
    sys.stdout.reconfigure(encoding="utf-8")
    if ORDEM.exists() or RECEBIDOS.exists():
        print("ABORTADO: existe ordem ativa ou CLIENTES/EMPRESA-TESTE/RECEBIDOS; nada foi feito.")
        return 1
    SRV = servidor.iniciar(0)
    PORTA = SRV.server_port
    threading.Thread(target=SRV.serve_forever, daemon=True).start()
    try:
        bateria()
    except Exception as exc:  # falha inesperada vira FAIL explícito (nunca some do relatório)
        import traceback
        registrar("A-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-300:]}")
    finally:
        SRV.shutdown()
        ORDEM.unlink(missing_ok=True)
        limpar_recebidos()
        shutil.rmtree(TMP, ignore_errors=True)
    largura = max(len(c) for c, _, _ in resultados)
    for c, ok, det in resultados:
        print(f"{'PASS' if ok else 'FAIL'}  {c.ljust(largura)}  {det}")
    falhas = [c for c, ok, _ in resultados if not ok]
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - len(falhas)} PASS · {len(falhas)} FAIL")
    print(f"ordem ativa residual: {'SIM' if ORDEM.exists() else 'não'} · RECEBIDOS residual: {'SIM' if RECEBIDOS.exists() else 'não'}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
