"""Testes ISOLADOS do extrator (T-004.4). Não executa o Agente de Documentos e não cria ordem ativa.

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/T004/testar_extrator.py

0. Ambiente isolado: fixtures FICTÍCIAS copiadas para um CLIENTES temporário (TESTES/ambiente_isolado.py).
1. Roda o extrator pela linha de comando (como o agente faria) sobre as fixtures e compara arquivo a
   arquivo com TESTES/T004/gabaritos.json.
2. Testes negativos em pasta temporária FORA do repositório (inexistente, extensão enganosa, vazio,
   acima do limite, nomes estranhos, link/junção, fora do escopo, tempo máximo).
3. Confere que o extrator não criou, alterou nem apagou nada nas fixtures.
Saída: tabela PASS/FAIL; código 0 só se tudo passar.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
# Ambiente ISOLADO: as empresas FICTÍCIAS (TESTES/FIXTURES-FICTICIAS) são copiadas para um CLIENTES temporário; o CLIENTES/
# operacional nunca é lido nem alterado (AGENTES_PRIME_CLIENTES, respeitado pelo extrator).
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado  # noqa: E402
AMB = ambiente_isolado.criar("prime-extrator-", fixtures=("EMPRESA-TESTE", "EMPRESA-ISOLAMENTO"))
CLIENTES = AMB.clientes

PY = sys.executable
EXTRATOR = RAIZ / "AGENTES" / "DOCUMENTOS" / "ferramentas" / "extrair_documentos.py"
GABARITO = Path(__file__).with_name("gabaritos.json")
IGNORAR_NA_BUSCA = {"sha256", "tamanho_bytes", "modificado_em"}

resultados = []


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, ok, detalhe))


def extrair(empresa, pasta):
    p = subprocess.run([PY, "-I", str(EXTRATOR), "--empresa", empresa, "--pasta", pasta, "--completo"],
                       cwd=RAIZ, capture_output=True, encoding="utf-8")
    return p.returncode, (json.loads(p.stdout) if p.returncode == 0 else None), p.stderr


def resolver(obj, caminho):
    for parte in caminho.split("."):
        if obj is None:
            return "<ausente>"
        if isinstance(obj, list):
            idx = int(parte)
            obj = obj[idx] if idx < len(obj) else "<ausente>"
        else:
            obj = obj.get(parte, "<ausente>")
    return obj


def conferir(caso, entrada):
    falhas = []
    if entrada is None:
        return ["arquivo ausente na saída do extrator"]
    if entrada.get("leitura") != caso["leitura"]:
        falhas.append(f"leitura={entrada.get('leitura')} (esperado {caso['leitura']})")
    marc = set(entrada.get("marcacoes", []))
    for m in caso.get("marcacoes_incluem", []):
        if m not in marc:
            falhas.append(f"falta marcação {m}")
    for m in caso.get("marcacoes_excluem", []):
        if m in marc:
            falhas.append(f"marcação indevida {m}")
    conteudo = entrada.get("conteudo")
    texto_conteudo = json.dumps(conteudo, ensure_ascii=False)
    for s in caso.get("deve_conter", []):
        if s not in texto_conteudo:
            falhas.append(f"não contém {s!r}")
    busca = json.dumps({k: v for k, v in entrada.items() if k not in IGNORAR_NA_BUSCA}, ensure_ascii=False)
    for s in caso.get("nao_pode_conter", []):
        if s in busca:
            falhas.append(f"CONTÉM VALOR PROIBIDO {s!r}")
    for caminho, esperado in caso.get("campos", {}).items():
        obtido = resolver(conteudo, caminho)
        if obtido != esperado:
            falhas.append(f"{caminho}={obtido!r} (esperado {esperado!r})")
    for caminho, itens in caso.get("lista_contem", {}).items():
        lista = resolver(conteudo, caminho)
        for item in itens:
            if not isinstance(lista, list) or item not in lista:
                falhas.append(f"{caminho} não contém {item!r}")
    if caso.get("sem_conteudo") and conteudo:
        falhas.append("há conteúdo extraído quando não deveria haver")
    if caso.get("sha256_prefixo") and not entrada.get("sha256", "").startswith(caso["sha256_prefixo"]):
        falhas.append("hash diferente do homologado")
    return falhas


def hashes(pastas):
    h = {}
    for pasta in pastas:
        for f in sorted(pasta.rglob("*")):
            if f.is_file():
                h[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    return h


def testes_fixtures():
    casos = json.loads(GABARITO.read_text(encoding="utf-8"))["casos"]
    pastas = {("EMPRESA-TESTE", "T004/PDF"), ("EMPRESA-TESTE", "T004/SCAN"), ("EMPRESA-TESTE", "T004/XLSX"),
              ("EMPRESA-TESTE", "T004/XML"), ("EMPRESA-ISOLAMENTO", "T004"), ("EMPRESA-TESTE", "TREINAMENTO/2026-09/DOCUMENTOS")}
    saidas = {}
    for empresa, pasta in sorted(pastas):
        codigo, saida, erro = extrair(empresa, pasta)
        if codigo != 0:
            registrar(f"EXEC {empresa}/{pasta}", False, erro.strip()[:200])
            continue
        for a in saida["arquivos"]:
            saidas[(empresa, a["arquivo"])] = a
    for caso in casos:
        falhas = conferir(caso, saidas.get((caso["empresa"], caso["arquivo"])))
        registrar(caso["id"], not falhas, "; ".join(falhas))
    # nenhum valor proibido do SCAN-01 em NENHUM resultado do lote
    proibidos = next(c for c in casos if c["id"] == "SCAN-01")["nao_pode_conter"]
    vazou = [(k[1], s) for k, a in saidas.items() for s in proibidos
             if s in json.dumps({x: y for x, y in a.items() if x not in IGNORAR_NA_BUSCA}, ensure_ascii=False)]
    registrar("SCAN-GLOBAL", not vazou, f"valor da imagem apareceu em: {vazou}" if vazou else "valor só da imagem não aparece em nenhum arquivo")


def testes_negativos():
    sys.path.insert(0, str(EXTRATOR.parent))
    import extrair_documentos as ex

    # NEG-01 pasta inexistente e caminho com '..' pela linha de comando
    codigo, _, erro = extrair("EMPRESA-TESTE", "T004/NAO-EXISTE")
    registrar("NEG-01a pasta inexistente", codigo == 2 and "VIOLACAO_CAMINHO" in erro)
    # (o modo --completo é usado aqui só para comparar com o gabarito; o agente usa --resumo/--arquivo)
    codigo, _, erro = extrair("EMPRESA-TESTE", "../EMPRESA-ISOLAMENTO/T004")
    registrar("NEG-01b pasta com '..'", codigo == 2 and "VIOLACAO_CAMINHO" in erro)

    with tempfile.TemporaryDirectory(prefix="t004-neg-") as tmp:
        base = Path(tmp)

        def caso(nome, dados, esperado, rotulo, marcacao=None):
            arq = base / nome
            arq.write_bytes(dados)
            r = ex.analisar_arquivo(arq, base)
            ok = r["leitura"] == esperado and (marcacao is None or marcacao in r.get("marcacoes", []))
            registrar(rotulo, ok, f"leitura={r['leitura']}")

        caso("fatura.pdf", b"isto e texto, nao um PDF", "EXTENSAO_INCOMPATIVEL", "NEG-02a extensão enganosa (.pdf com texto)")
        caso("foto.jpg", b"%PDF-1.4 conteudo", "EXTENSAO_INCOMPATIVEL", "NEG-02b extensão enganosa (.jpg com PDF)")
        caso("planilha.xlsx", b"texto qualquer", "EXTENSAO_INCOMPATIVEL", "NEG-02c extensão enganosa (.xlsx com texto)")
        caso("nota.xml", b"\x00\x01\x02 binario", "ARQUIVO_CORROMPIDO", "NEG-02d .xml binário")
        caso("vazio.pdf", b"", "DOCUMENTO_VAZIO", "NEG-04 arquivo vazio")
        caso("antigo.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100, "NAO_SUPORTADO", "NEG-07a .xls fora do escopo")
        caso("pacote.zip", b"PK\x05\x06" + b"\x00" * 18, "NAO_SUPORTADO", "NEG-07b .zip fora do escopo")
        caso("nfse.xml", b'<?xml version="1.0"?><CompNfse xmlns="http://www.abrasf.org.br/nfse.xsd"/>', "XML_TIPO_NAO_SUPORTADO", "NEG-07c NFS-e")
        caso("cte.xml", b'<?xml version="1.0"?><cteProc xmlns="http://www.portalfiscal.inf.br/cte"/>', "XML_TIPO_NAO_SUPORTADO", "NEG-07d CT-e")
        caso("grande.txt", b"a" * (ex.LIMITES["caracteres_texto"] + 10), "EXTRAIDO_TEXTO", "NEG-05a texto acima do limite", "LIMITE_EXCEDIDO")

        enorme = base / "enorme.pdf"
        with open(enorme, "wb") as f:
            f.write(b"%PDF-1.4\n")
            f.truncate(ex.LIMITES["bytes_arquivo"] + 1)
        r = ex.analisar_arquivo(enorme, base)
        registrar("NEG-05b arquivo acima de 20 MB", r["leitura"] == "LIMITE_EXCEDIDO", f"leitura={r['leitura']}")

        estranho = base / "nota fiscal (cópia) çãõ #1 [x]..pdf"
        estranho.write_bytes((CLIENTES / "EMPRESA-TESTE/T004/PDF/PDF-01_nf_servico.pdf").read_bytes())
        r = ex.analisar_arquivo(estranho, base)
        registrar("NEG-06 nome estranho", r["leitura"] == "EXTRAIDO_PDF" and r["arquivo"] == estranho.name, f"leitura={r['leitura']}")

        # NEG-11 PDF escaneado com imagem embutida no fluxo (BI/ID/EI), sem XObject: deve exigir OCR, não "vazio"
        sys.path.insert(0, str(Path(__file__).parent))
        import gerar_fixtures as gf
        embutida = base / "escaneado_imagem_embutida.pdf"
        embutida.write_bytes(gf.montar_pdf([{"bruto": b"q 200 0 0 50 56 600 cm BI /W 2 /H 2 /CS /G /BPC 8 ID \x00\xff\xff\x00 EI Q"}]))
        r = ex.analisar_arquivo(embutida, base)
        registrar("NEG-11 PDF com imagem embutida (BI/ID/EI)", r["leitura"] == "DOCUMENTO_REQUER_OCR", f"leitura={r['leitura']}")

        # NEG-08 link/junção apontando para fora da pasta analisada
        fora = Path(tempfile.mkdtemp(prefix="t004-fora-"))
        (fora / "segredo.txt").write_text("CONTEUDO FORA DA PASTA", encoding="utf-8")
        juncao = base / "atalho"
        criado = subprocess.run(["cmd", "/c", "mklink", "/J", str(juncao), str(fora)], capture_output=True).returncode == 0
        if criado:
            arquivos, ignorados = ex.listar_arquivos(base, base)
            ok = all("segredo" not in str(a) for a in arquivos) and any(i["motivo"].startswith("pasta link") for i in ignorados)
            registrar("NEG-08a junção de pasta ignorada", ok)
            os.rmdir(juncao)
        else:
            registrar("NEG-08a junção de pasta ignorada", False, "não foi possível criar a junção")
        try:
            os.symlink(fora / "segredo.txt", base / "link.txt")
            arquivos, ignorados = ex.listar_arquivos(base, base)
            registrar("NEG-08b link simbólico de arquivo ignorado", all(a.name != "link.txt" for a in arquivos))
        except OSError:
            registrar("NEG-08b link simbólico de arquivo ignorado", None, "NÃO TESTADO: o Windows exige privilégio/modo desenvolvedor para criar symlink")
        (fora / "segredo.txt").unlink()
        fora.rmdir()

        # NEG-09 tempo máximo: força 0,01 s e espera LIMITE_EXCEDIDO sem travar
        original = ex.LIMITES["tempo_segundos"]
        ex.LIMITES["tempo_segundos"] = 0.01
        r = ex.analisar_arquivo(estranho, base)
        ex.LIMITES["tempo_segundos"] = original
        registrar("NEG-09 tempo máximo de processamento", r["leitura"] == "LIMITE_EXCEDIDO", f"leitura={r['leitura']}")

    # NEG-10 o código do extrator não importa bibliotecas de rede
    fonte = EXTRATOR.read_text(encoding="utf-8")
    proibidos = [m for m in ("import socket", "urllib", "requests", "http.client", "ftplib") if m in fonte]
    registrar("NEG-10 sem bibliotecas de rede no extrator", not proibidos, str(proibidos) if proibidos else "")


def main():
    pastas = [CLIENTES / "EMPRESA-TESTE/T004", CLIENTES / "EMPRESA-ISOLAMENTO/T004",
              CLIENTES / "EMPRESA-TESTE/TREINAMENTO"]
    antes = hashes(pastas)
    testes_fixtures()
    testes_negativos()
    registrar("INTEGRIDADE fixtures intocadas pelo extrator", hashes(pastas) == antes)

    largura = max(len(c) for c, _, _ in resultados)
    for caso, ok, detalhe in resultados:
        status = "PASS" if ok else ("N/T " if ok is None else "FAIL")
        print(f"{status}  {caso.ljust(largura)}  {detalhe}")
    falhas = [c for c, ok, _ in resultados if ok is False]
    nt = [c for c, ok, _ in resultados if ok is None]
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - len(falhas) - len(nt)} PASS · {len(falhas)} FAIL · {len(nt)} não testado(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
