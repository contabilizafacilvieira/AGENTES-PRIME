"""Verifica o bloqueio de amostras no REAL e a primeira tela do perfil vazio."""
import json
import http.client
import os
import socket
import sys
import threading
import subprocess
import tempfile
import time
import urllib.request
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
TMP = tempfile.TemporaryDirectory(prefix="prime-separacao-ambientes-")
ROOT_TESTE = Path(TMP.name)
for pasta in ("CLIENTES", "runtime", "CONTROLE", "LIBERADOS"):
    (ROOT_TESTE / pasta).mkdir(parents=True, exist_ok=True)
(ROOT_TESTE / "CONTROLE" / "solicitacoes.json").write_text(
    json.dumps({"solicitacoes": {}, "sequencia_sol": {}}), encoding="utf-8"
)
os.environ.update({
    "AGENTES_PRIME_AMBIENTE": "REAL",
    "AGENTES_PRIME_MODO_TESTE": "0",
    "AGENTES_PRIME_CLIENTES": str(ROOT_TESTE / "CLIENTES"),
    "AGENTES_PRIME_RUNTIME": str(ROOT_TESTE / "runtime"),
    "AGENTES_PRIME_REGISTRO_SOL": str(ROOT_TESTE / "CONTROLE" / "solicitacoes.json"),
    "AGENTES_PRIME_ORDEM_ATIVA": str(ROOT_TESTE / "CONTROLE" / "ordem-ativa.json"),
    "AGENTES_PRIME_LIBERADOS": str(ROOT_TESTE / "LIBERADOS"),
})
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import servidor  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402


class SeparacaoAmbientes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = servidor.iniciar(0)
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(timeout=5)

    def requisicao(self, metodo, caminho, corpo=None, sessao=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=5)
        headers = {}
        if sessao:
            headers["X-Prime-Sessao"] = sessao
        if corpo is not None:
            import json
            corpo = json.dumps(corpo).encode()
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(corpo))
        conn.request(metodo, caminho, body=corpo, headers=headers)
        resposta = conn.getresponse()
        dados = resposta.read()
        status = resposta.status
        conn.close()
        return status, dados

    def test_real_bloqueia_preparacao_ficticia_por_politica(self):
        with patch.dict(os.environ, {"AGENTES_PRIME_AMBIENTE": "REAL", "AGENTES_PRIME_MODO_TESTE": "0"}):
            self.assertFalse(servidor.amostra_ficticia_permitida())
        with patch.dict(os.environ, {"AGENTES_PRIME_AMBIENTE": "DEMONSTRACAO", "AGENTES_PRIME_MODO_TESTE": "0"}):
            self.assertTrue(servidor.amostra_ficticia_permitida())
        with patch.dict(os.environ, {"AGENTES_PRIME_AMBIENTE": "TESTE", "AGENTES_PRIME_MODO_TESTE": "0"}):
            self.assertTrue(servidor.amostra_ficticia_permitida())

    def test_pagina_real_marca_amostra_bloqueada(self):
        status, pagina = self.requisicao("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'name="prime-ambiente" content="REAL"', pagina)
        self.assertIn(b'name="prime-amostra" content="BLOQUEADA"', pagina)

    def test_api_real_recusa_get_e_post_de_amostra(self):
        token = self.srv.token
        status_get, _ = self.requisicao("GET", "/api/amostra", sessao=token)
        status_post, dados = self.requisicao("POST", "/api/amostra/preparar", {"confirmado": True}, token)
        self.assertEqual(status_get, 403)
        self.assertEqual(status_post, 403)
        self.assertIn("bloqueada no ambiente REAL".encode(), dados)

    def test_tela_inicial_real_vazia_oferece_cadastro_e_esconde_amostra(self):
        if not CHROME:
            self.skipTest("Chrome/Chromium não disponível")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            porta = sock.getsockname()[1]
        perfil = ROOT_TESTE / "chrome"
        proc = subprocess.Popen([
            str(CHROME), "--headless=new", f"--remote-debugging-port={porta}", f"--user-data-dir={perfil}",
            "--window-size=1400,1000", "--no-first-run", "--disable-extensions", "--disable-background-networking",
            f"http://127.0.0.1:{self.srv.server_port}/",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cdp = None
        try:
            destino = None
            for _ in range(100):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/list", timeout=1) as resposta:
                        abas = json.loads(resposta.read())
                    destino = next((x.get("webSocketDebuggerUrl") for x in abas if x.get("type") == "page"), None)
                    if destino:
                        break
                except Exception:
                    pass
                time.sleep(0.1)
            self.assertTrue(destino, "Chrome não abriu a página local do perfil REAL vazio")
            cdp = CDP(destino)
            tela = None
            for _ in range(80):
                tela = cdp.js("""(()=>({
                  ambiente:document.querySelector('.amb-faixa')?.dataset.ambiente,
                  vazio:!!document.querySelector('[data-escritorio-vazio]'),
                  texto:document.querySelector('[data-escritorio-vazio]')?.innerText||'',
                  cta:document.querySelector('[data-acao=cadastrar-empresa-inicial]')?.textContent||'',
                  painel:!document.querySelector('.gestao')?.hidden
                }))()""")
                if tela and tela.get("ambiente") and tela.get("vazio") and tela.get("cta"):
                    break
                time.sleep(0.1)
            self.assertEqual(tela.get("ambiente"), "REAL")
            self.assertTrue(tela.get("vazio"))
            self.assertIn("Escritório aguardando demanda", tela.get("texto", ""))
            self.assertEqual(tela.get("cta"), "Cadastrar empresa")
            self.assertTrue(tela.get("painel"))
            cdp.js("document.querySelector('[data-acao=cadastrar-empresa-inicial]').click()")
            time.sleep(0.3)
            self.assertTrue(cdp.js("!!document.querySelector('[data-cadastrar-empresa] input')"))
            self.assertFalse(cdp.js("!!document.querySelector('[data-acao=preparar-amostra]')"))
        finally:
            if cdp:
                cdp.s.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
