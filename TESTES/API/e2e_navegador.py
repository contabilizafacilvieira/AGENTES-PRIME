"""Teste de ponta a ponta PELO NAVEGADOR (Chrome sem interface), com o Agente de Documentos REAL.

Escritório Virtual → API local → Coordenador (abrir) → executor → agente-documentos → Coordenador (encerrar) → tela.
Usa somente documentos FICTÍCIOS (lote misto da EMPRESA-TESTE). Executa o Claude Code de verdade (tem custo).

Uso (a partir da raiz AGENTES-PRIME, com a API já em execução em 127.0.0.1:8765):
    .venv/Scripts/python.exe -I -u TESTES/API/e2e_navegador.py <pasta para capturas de tela> [EMPRESA] [pasta do lote fictício]
Com EMPRESA=VGROW o teste percorre a rota PILOTO_REAL_SUPERVISIONADO usando os MESMOS documentos fictícios.
"""

import base64
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
def descobrir_navegador() -> Path | None:
    candidatos = []
    if os.environ.get("AGENTES_PRIME_NAVEGADOR"):
        candidatos.append(Path(os.environ["AGENTES_PRIME_NAVEGADOR"]))
    for nome in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        achado = shutil.which(nome)
        if achado:
            candidatos.append(Path(achado))
    if sys.platform == "darwin":
        candidatos.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
        candidatos.append(Path("/Applications/Chromium.app/Contents/MacOS/Chromium"))
    elif os.name == "nt":
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
            if base:
                candidatos.append(Path(base) / "Google/Chrome/Application/chrome.exe")
                candidatos.append(Path(base) / "Chromium/Application/chrome.exe")
    return next((p for p in candidatos if p.is_file()), None)

CHROME = descobrir_navegador()
URL = "http://127.0.0.1:8765/"
PORTA_CDP = 9333
LOTE = RAIZ / "CLIENTES/EMPRESA-TESTE/T004-MISTO"
SEGREDO_SCAN = [r"(?<![0-9A-Fa-f.,])9\.876,54(?![0-9])", r"(?<![0-9A-Fa-f.,])9876(?![0-9A-Fa-f])", r"TOTAL R\$ 9"]


class CDP:
    """Cliente mínimo do Chrome DevTools Protocol (WebSocket sem bibliotecas externas)."""

    def __init__(self, ws_url):
        hostporta, caminho = ws_url[len("ws://"):].split("/", 1)
        host, porta = hostporta.split(":")
        self.s = socket.create_connection((host, int(porta)))
        chave = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{caminho} HTTP/1.1\r\nHost: {hostporta}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {chave}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        resposta = b""
        while b"\r\n\r\n" not in resposta:
            resposta += self.s.recv(1)
        assert b" 101 " in resposta.split(b"\r\n")[0], resposta
        self.n = 0

    def _ler(self, n):
        dados = b""
        while len(dados) < n:
            dados += self.s.recv(n - len(dados))
        return dados

    def _enviar(self, texto):
        p = texto.encode()
        cab = bytes([0x81])
        cab += bytes([0x80 | len(p)]) if len(p) < 126 else (bytes([0x80 | 126]) + len(p).to_bytes(2, "big") if len(p) < 65536 else bytes([0x80 | 127]) + len(p).to_bytes(8, "big"))
        mascara = os.urandom(4)
        self.s.sendall(cab + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(p)))

    def _receber(self):
        partes = b""
        while True:
            b1, b2 = self._ler(2)
            n = b2 & 0x7F
            if n == 126:
                n = int.from_bytes(self._ler(2), "big")
            elif n == 127:
                n = int.from_bytes(self._ler(8), "big")
            partes += self._ler(n)
            if b1 & 0x80:
                return json.loads(partes.decode("utf-8"))

    def chamar(self, metodo, **params):
        self.n += 1
        self._enviar(json.dumps({"id": self.n, "method": metodo, "params": params}))
        while True:
            m = self._receber()
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})

    def js(self, expressao):
        r = self.chamar("Runtime.evaluate", expression=expressao, awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")

    def foto(self, destino):
        Path(destino).write_bytes(base64.b64decode(self.chamar("Page.captureScreenshot", format="png")["data"]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    saida = Path(sys.argv[1])
    empresa = sys.argv[2] if len(sys.argv) > 2 else "EMPRESA-TESTE"
    lote = Path(sys.argv[3]) if len(sys.argv) > 3 else LOTE   # pasta com documentos FICTÍCIOS
    saida.mkdir(parents=True, exist_ok=True)
    perfil = tempfile.mkdtemp(prefix="chrome-e2e-")
    chrome = subprocess.Popen([str(CHROME), "--headless=new", f"--remote-debugging-port={PORTA_CDP}", f"--user-data-dir={perfil}",
                               "--window-size=1500,1050", "--no-first-run", "--disable-extensions", URL])
    try:
        for _ in range(50):
            try:
                alvos = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORTA_CDP}/json/list"))
                pagina = next(a for a in alvos if a["type"] == "page" and a["url"].startswith(URL))
                break
            except Exception:
                time.sleep(0.3)
        cdp = CDP(pagina["webSocketDebuggerUrl"])
        cdp.chamar("Page.enable")
        cdp.chamar("DOM.enable")
        time.sleep(1.5)
        print("modo operação ativo:", cdp.js("!!document.querySelector('.op-botao') && document.querySelector('#botao-sim').closest('.menu').hidden"))
        cdp.js("document.querySelector('.op-botao').click()")
        time.sleep(1.5)
        print("empresas na lista:", cdp.js("Array.from(document.querySelectorAll('.op-campo select option')).map(o=>o.value).join(',')"))
        selecionada = cdp.js("""(() => { const s=document.querySelector('.op-campo select'); s.value='__EMPRESA__'; if (s.value !== '__EMPRESA__') return false;
                  const c=document.querySelector('.op-campo input[type=month]'); c.value='2026-09';
                  const t=document.querySelector('.op-campo textarea'); t.value='Coordenador, chegaram documentos da competência 09/2026. Inicie o processamento.';
                  document.querySelector('.op-confirma input').checked=true; return true; })()""".replace("__EMPRESA__", empresa))
        print("empresa selecionada:", empresa, selecionada)
        if not selecionada:
            raise SystemExit(f"{empresa} não está na lista de empresas autorizadas")
        no = cdp.chamar("DOM.querySelector", nodeId=cdp.chamar("DOM.getDocument")["root"]["nodeId"], selector=".op-campo input[type=file]")["nodeId"]
        arquivos = sorted(str(p) for p in lote.iterdir() if p.is_file())
        cdp.chamar("DOM.setFileInputFiles", nodeId=no, files=arquivos)
        cdp.js("document.querySelector('.op-campo input[type=file]').dispatchEvent(new Event('change'))")
        cdp.foto(saida / "1-formulario.png")
        cdp.js("document.querySelector('.op-iniciar').click()")
        inicio = time.time()
        sol, foto_meio = None, False
        while time.time() - inicio < 1500:
            time.sleep(3)
            texto = cdp.js("(document.querySelector('.op-sol-id')||{}).textContent || document.querySelector('.op-msg').textContent") or ""
            m = re.search(r"SOL-\d{4}-\d{6}", texto)
            if m and not sol:
                sol = m.group(0)
                print("SOL gerada:", sol, "·", texto)
            if sol and not foto_meio and "Em processamento" in (cdp.js("document.querySelector('.op-sol').textContent") or ""):
                cdp.js("document.querySelector('.op-painel').hidden = true")
                time.sleep(1)
                cdp.foto(saida / "2-processando-escritorio.png")
                cdp.js("document.querySelector('.op-painel').hidden = false")
                foto_meio = True
            if sol and "Em processamento" not in (cdp.js("document.querySelector('.op-sol').textContent") or ""):
                break
            if not sol and texto and "Encaminhando" not in texto and "recebid" not in texto:
                print("ERRO NA TELA:", texto)
                cdp.foto(saida / "erro.png")
                break
        time.sleep(2)
        cdp.js("document.querySelector('.op-relatorio') && (document.querySelector('.op-relatorio').open = false)")
        cdp.foto(saida / "3-resultado.png")
        cdp.js("document.querySelector('.op-painel').hidden = true; document.querySelector('[data-agente=\"coordenador\"], .rotulo') && 0")
        time.sleep(1)
        cdp.foto(saida / "4-escritorio-final.png")
        print("duração (s):", round(time.time() - inicio))
        print("resumo da tela:", cdp.js("document.getElementById('resumo').textContent"))
        print("tela da SOL contém CONFERENCIA_MANUAL_PILOTO:", "CONFERENCIA_MANUAL_PILOTO" in (cdp.js("document.querySelector('.op-sol').textContent") or ""))
        print("modo exibido:", cdp.js("Array.from(document.querySelectorAll('.op-sol dd')).map(x=>x.textContent)[2]"))
        print(json.dumps({"sol": sol}))
    finally:
        chrome.terminate()


if __name__ == "__main__":
    main()
