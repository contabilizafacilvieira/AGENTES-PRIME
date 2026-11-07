"""Bateria da interface paginada do extrator (--resumo / --arquivo / --parte). Não executa agentes.

Uso (a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I TESTES/T004/testar_interface.py

Ambiente isolado (TESTES/ambiente_isolado.py): fixtures fictícias num CLIENTES temporário, removido ao final.
"""

import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
# Ambiente ISOLADO: fixtures FICTÍCIAS copiadas para um CLIENTES temporário; o guarda testado é uma CÓPIA dentro da raiz
# temporária (código inalterado), sem tocar o CLIENTES/ nem a ordem ativa operacionais.
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado  # noqa: E402
AMB = ambiente_isolado.criar("prime-interface-t004-", fixtures=("EMPRESA-TESTE", "EMPRESA-ISOLAMENTO"), com_guarda=True)
CLIENTES = AMB.clientes
PY = sys.executable
EXTRATOR = RAIZ / "AGENTES" / "DOCUMENTOS" / "ferramentas" / "extrair_documentos.py"
GUARDA = AMB.guarda
TMP17 = CLIENTES / "EMPRESA-TESTE/T004-TMP-I17"
TMP19 = CLIENTES / "EMPRESA-TESTE/T004-TMP-I19"
ORCAMENTO = 12_000
resultados = []
maior_saida = [0, ""]


def remover(pasta):
    """rmtree que tolera o atributo somente leitura aplicado pelo OneDrive a pastas recém-criadas."""
    def forcar(funcao, caminho, _erro):
        os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD)
        funcao(caminho)
    shutil.rmtree(pasta, onexc=forcar)


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), detalhe))


def rodar(*args):
    p = subprocess.run([PY, "-I", str(EXTRATOR), *args], cwd=RAIZ, capture_output=True, encoding="utf-8")
    if p.returncode == 0 and len(p.stdout) > maior_saida[0]:
        maior_saida[:] = [len(p.stdout), " ".join(args)]
    dados = json.loads(p.stdout) if p.returncode == 0 else (json.loads(p.stderr.strip().splitlines()[-1]) if p.stderr.strip().startswith("{") else {"erro": p.stderr.strip()[:120]})
    return p.returncode, dados, len(p.stdout)


def resumo(empresa, pasta):
    """Resumo completo (todas as partes)."""
    itens, n, total = [], 1, 1
    while n <= total:
        codigo, d, tam = rodar("--empresa", empresa, "--pasta", pasta, "--resumo", "--parte", str(n))
        assert codigo == 0, d
        itens += d["itens"]
        total = d["partes_total"]
        n += 1
    return itens


def todas_as_partes(empresa, ident):
    partes, n, total = [], 1, 1
    while n <= total:
        codigo, d, tam = rodar("--empresa", empresa, "--arquivo", ident, "--parte", str(n))
        assert codigo == 0, d
        partes.append((d, tam))
        total = d["partes_total"]
        n += 1
    return partes


def por_nome(itens, trecho):
    return next(i for i in itens if trecho in i["nome"])


def reconstruir(partes):
    """Reúne as unidades de todas as partes, juntando trechos de texto/colunas divididos."""
    unidades = []
    for d, _ in partes:
        for u in d["conteudo"]:
            chave = (u.get("aba"), u.get("linha"), u.get("pagina"), u.get("nItem"))
            if ("trecho" in u or "colunas" in u) and unidades and unidades[-1][0] == chave:
                anterior = unidades[-1][1]
                if "texto" in u:
                    anterior["texto"] += u["texto"]
                else:
                    anterior["valores"] += u["valores"]
                continue
            unidades.append((chave, {k: v for k, v in u.items() if k not in ("trecho", "colunas")}))
    return [u for _, u in unidades]


def completo(empresa, pasta):
    p = subprocess.run([PY, "-I", str(EXTRATOR), "--empresa", empresa, "--pasta", pasta, "--completo"], cwd=RAIZ, capture_output=True, encoding="utf-8")
    return {a["arquivo"]: a for a in json.loads(p.stdout)["arquivos"]}


def unidades_completas(a):
    c = a.get("conteudo") or {}
    l = a.get("leitura")
    if l == "EXTRAIDO_TEXTO":
        return [{"linha": i, "texto": t} for i, t in enumerate(c.get("texto", "").splitlines(), 1)]
    if l == "EXTRAIDO_PDF":
        return c.get("paginas", [])
    if l == "EXTRAIDO_PLANILHA":
        return [{"aba": ab["aba"], "linha": x["linha"], "valores": x["valores"]} for ab in c["abas"] for x in ab["linhas"]]
    if l == "EXTRAIDO_NFE":
        return c.get("itens", [])
    return []


def bateria():
    # I-01 resumo pequeno
    codigo, d, tam = rodar("--empresa", "EMPRESA-TESTE", "--pasta", "T004/PDF", "--resumo")
    registrar("I-01 resumo pequeno (PDF)", codigo == 0 and d["itens_total"] == 8 and d["partes_total"] == 1 and tam <= ORCAMENTO
              and all("conteudo" not in i for i in d["itens"]), f"{tam} caracteres, {d.get('itens_total')} itens")
    # I-02 resumo de pasta XLSX grande
    codigo, d, tam = rodar("--empresa", "EMPRESA-TESTE", "--pasta", "T004/XLSX", "--resumo")
    x05 = por_nome(d["itens"], "XLSX-05")
    registrar("I-02 resumo pasta XLSX (antes 341 KB)", codigo == 0 and tam <= ORCAMENTO and d["itens_total"] == 11 and x05["partes_total"] > 1
              and "LIMITE_EXCEDIDO" in x05["marcacoes"], f"{tam} caracteres; XLSX-05 em {x05['partes_total']} partes")
    itens_xlsx = d["itens"]
    # I-03 resumo de pasta XML
    codigo, d, tam = rodar("--empresa", "EMPRESA-TESTE", "--pasta", "T004/XML", "--resumo")
    x01, x08 = por_nome(d["itens"], "XML-01_"), por_nome(d["itens"], "XML-08")
    registrar("I-03 resumo pasta XML (antes 52 KB)", codigo == 0 and tam <= ORCAMENTO and d["itens_total"] == 10
              and "NOTA_CANCELADA" in x01["marcacoes"] and x01["relacionado_a"] == x08["id"] and x08["relacionado_a"] == x01["id"],
              f"{tam} caracteres; XML-01↔XML-08 relacionados por id")
    itens_xml = d["itens"]
    # I-04 arquivo pequeno
    itens_pdf = resumo("EMPRESA-TESTE", "T004/PDF")
    codigo, d, tam = rodar("--empresa", "EMPRESA-TESTE", "--arquivo", por_nome(itens_pdf, "PDF-01")["id"])
    registrar("I-04 arquivo pequeno (PDF-01)", codigo == 0 and d["partes_total"] == 1 and not d["tem_mais"] and "000777" in json.dumps(d["conteudo"])
              and d["sha256"].startswith(por_nome(itens_pdf, "PDF-01")["sha256"][:16]), f"{tam} caracteres")
    # I-05..I-08 arquivo grande com várias partes (XLSX-05)
    partes = todas_as_partes("EMPRESA-TESTE", x05["id"])
    total = len(partes)
    registrar("I-05 arquivo grande em várias partes", total == x05["partes_total"] and total > 2, f"{total} partes")
    p1 = partes[0][0]
    registrar("I-06 primeira parte", p1["parte"] == 1 and p1["tem_mais"] and p1["conteudo"][0]["linha"] == 1 and p1["intervalo"].startswith("aba Lancamentos: linhas 1-"), p1["intervalo"])
    meio = partes[total // 2][0]
    anterior = partes[total // 2 - 1][0]
    registrar("I-07 parte intermediária (continuidade)", meio["tem_mais"] and meio["conteudo"][0]["linha"] == anterior["conteudo"][-1]["linha"] + 1, meio["intervalo"])
    ultima = partes[-1][0]
    linhas = [u["linha"] for d, _ in partes for u in d["conteudo"]]
    registrar("I-08 última parte e cobertura sem perda", not ultima["tem_mais"] and linhas == list(range(1, 2001)) and "LIMITE_EXCEDIDO" in ultima["marcacoes"],
              f"{len(linhas)} linhas de 1 a {linhas[-1]}, sem lacuna nem repetição; LIMITE_EXCEDIDO preservado")
    # I-09 parte inexistente
    codigo, d, _ = rodar("--empresa", "EMPRESA-TESTE", "--arquivo", x05["id"], "--parte", str(total + 1))
    registrar("I-09 parte inexistente", codigo == 2 and d.get("erro") == "PARTE_INEXISTENTE" and d.get("partes_total") == total)
    codigo, d, _ = rodar("--empresa", "EMPRESA-TESTE", "--pasta", "T004/PDF", "--resumo", "--parte", "2")
    registrar("I-09b parte inexistente do resumo", codigo == 2 and d.get("erro") == "PARTE_INEXISTENTE")
    # I-10 id fora do inventário
    codigo, d, _ = rodar("--empresa", "EMPRESA-TESTE", "--arquivo", "%032x" % random.Random(4).getrandbits(128))
    registrar("I-10 id fora do inventário", codigo == 2 and d.get("erro") == "ID_DESCONHECIDO")
    # I-11 nome inventado
    codigo, d, _ = rodar("--empresa", "EMPRESA-TESTE", "--arquivo", "XLSX-02_notas.xlsx")
    registrar("I-11 nome de arquivo inventado", codigo == 2 and d.get("erro") == "PARAMETROS_INVALIDOS")
    # I-12 caminho absoluto
    codigo, d, _ = rodar("--empresa", "EMPRESA-TESTE", "--arquivo", str(CLIENTES / "EMPRESA-TESTE/CADASTRO.md"))
    c2, d2, _ = rodar("--empresa", "EMPRESA-TESTE", "--pasta", "C:/Windows", "--resumo")
    registrar("I-12 caminho absoluto", codigo == 2 and d.get("erro") == "PARAMETROS_INVALIDOS" and c2 == 2 and d2.get("erro") == "VIOLACAO_CAMINHO")
    # I-13 ..
    codigo, d, _ = rodar("--empresa", "EMPRESA-TESTE", "--pasta", "../EMPRESA-ISOLAMENTO/T004", "--resumo")
    registrar("I-13 '..' na pasta", codigo == 2 and d.get("erro") == "VIOLACAO_CAMINHO")
    # I-14 outra empresa (id válido da EMPRESA-ISOLAMENTO usado com EMPRESA-TESTE)
    iso = resumo("EMPRESA-ISOLAMENTO", "T004")
    codigo, d, _ = rodar("--empresa", "EMPRESA-TESTE", "--arquivo", iso[0]["id"])
    c2, d2, _ = rodar("--empresa", "EMPRESA-ISOLAMENTO", "--arquivo", iso[0]["id"])
    registrar("I-14 id de outra empresa não resolve", codigo == 2 and d.get("erro") == "ID_DESCONHECIDO" and c2 == 0, "na própria empresa o mesmo id resolve")
    # I-15 argumentos extras / combinações ambíguas
    casos = [["--pasta", "T004/PDF", "--resumo", "--arquivo", x05["id"]], ["--pasta", "T004/PDF", "--arquivo", x05["id"]],
             ["--pasta", "T004/PDF", "--completo", "--parte", "2"], ["--pasta", "T004/PDF"], ["--arquivo", x05["id"], "--parte", "0"]]
    ok = all(rodar("--empresa", "EMPRESA-TESTE", *c)[0] == 2 for c in casos)
    p = subprocess.run([PY, "-I", str(EXTRATOR), "--empresa", "EMPRESA-TESTE", "--pasta", "T004/PDF", "--resumo", "--extra"], cwd=RAIZ, capture_output=True)
    registrar("I-15 argumentos extras e combinações ambíguas", ok and p.returncode == 2, f"{len(casos) + 1} combinações recusadas")
    # I-16 shell chaining (barrado no guarda)
    comando = f".venv/Scripts/python.exe -I AGENTES/DOCUMENTOS/ferramentas/extrair_documentos.py --empresa EMPRESA-TESTE --arquivo {x05['id']} && echo x"
    p = subprocess.run([PY, "-I", str(GUARDA)], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": comando}, "agent_type": "agente-documentos"}).encode(), capture_output=True)
    registrar("I-16 encadeamento de shell", p.returncode == 2, "bloqueado pelo guarda antes de qualquer ordem")
    # I-17 resumo com muitos arquivos (paginação do inventário e limite de arquivos)
    TMP17.mkdir()
    for i in range(1, 121):
        (TMP17 / f"documento_ficticio_com_nome_longo_para_teste_de_paginacao_{i:03d}.txt").write_text(f"DOCUMENTO FICTICIO {i}\n", encoding="utf-8")
    itens = resumo("EMPRESA-TESTE", "T004-TMP-I17")
    codigo, d, tam = rodar("--empresa", "EMPRESA-TESTE", "--pasta", "T004-TMP-I17", "--resumo")
    registrar("I-17a inventário paginado", d["partes_total"] > 1 and len(itens) == 120 and len({i["id"] for i in itens}) == 120,
              f"120 arquivos em {d['partes_total']} partes de resumo")
    for i in range(121, 202):
        (TMP17 / f"documento_ficticio_com_nome_longo_para_teste_de_paginacao_{i:03d}.txt").write_text(f"DOCUMENTO FICTICIO {i}\n", encoding="utf-8")
    codigo, d, _ = rodar("--empresa", "EMPRESA-TESTE", "--pasta", "T004-TMP-I17", "--resumo")
    registrar("I-17b pasta acima do limite de arquivos", codigo == 2 and d.get("erro") == "LIMITE_EXCEDIDO", d.get("mensagem", ""))
    # I-18 determinismo
    a = rodar("--empresa", "EMPRESA-TESTE", "--arquivo", x05["id"], "--parte", "3")[1]
    b = rodar("--empresa", "EMPRESA-TESTE", "--arquivo", x05["id"], "--parte", "3")[1]
    r2 = resumo("EMPRESA-TESTE", "T004/XLSX")
    registrar("I-18 determinismo de partes e ids", a["conteudo"] == b["conteudo"] and a["intervalo"] == b["intervalo"] == partes[2][0]["intervalo"]
              and [i["id"] for i in r2] == [i["id"] for i in itens_xlsx])
    # I-19 arquivo alterado entre resumo e leitura
    TMP19.mkdir()
    alvo = TMP19 / "documento_ficticio.txt"
    alvo.write_text("VERSAO 1 FICTICIA\n", encoding="utf-8")
    ident = resumo("EMPRESA-TESTE", "T004-TMP-I19")[0]["id"]
    alvo.write_text("VERSAO 2 FICTICIA ALTERADA\n", encoding="utf-8")
    codigo, d, _ = rodar("--empresa", "EMPRESA-TESTE", "--arquivo", ident)
    registrar("I-19 arquivo alterado após o resumo", codigo == 2 and d.get("erro") == "ARQUIVO_ALTERADO" and "VERSAO 2" not in json.dumps(d))
    # I-21 linha de texto maior que o orçamento: dividida em trechos, sem perda
    longa = TMP19 / "linha_unica_longa.txt"
    texto = "".join(f"[{i:05d}-dado-ficticio]" for i in range(3000))
    longa.write_text(texto + "\nSEGUNDA LINHA\n", encoding="utf-8")
    ident = next(i for i in resumo("EMPRESA-TESTE", "T004-TMP-I19") if i["nome"] == longa.name)["id"]
    ps = todas_as_partes("EMPRESA-TESTE", ident)
    rec = reconstruir(ps)
    registrar("I-21 linha gigante dividida em trechos sem perda", len(ps) > 1 and rec[0]["texto"] == texto and rec[1]["texto"] == "SEGUNDA LINHA"
              and all(t <= ORCAMENTO for _, t in ps), f"{len(ps)} partes")

    # I-22 NF-e com 80 itens: cabeçalho e totais em todas as partes, itens completos
    x02 = por_nome(itens_xml, "XML-02")
    ps = todas_as_partes("EMPRESA-TESTE", x02["id"])
    nitens = [u["nItem"] for d, _ in ps for u in d["conteudo"]]
    registrar("I-22 NF-e paginada por itens", nitens == [str(i) for i in range(1, 81)]
              and all(d["cabecalho"]["chave"] == "35260922222222222222550010000001241123456785" and d["cabecalho"]["totais"]["vNF"] == "800.00" for d, _ in ps),
              f"{len(ps)} parte(s); cabeçalho e totais repetidos em todas")

    # I-24 executado_em: presente, ISO 8601 com fuso, sem efeito em hash, id e partes
    hash_real = hashlib.sha256((CLIENTES / "EMPRESA-TESTE" / x05["arquivo"]).read_bytes()).hexdigest()
    r1 = rodar("--empresa", "EMPRESA-TESTE", "--pasta", "T004/XLSX", "--resumo")[1]
    a1 = [rodar("--empresa", "EMPRESA-TESTE", "--arquivo", x05["id"], "--parte", str(n))[1] for n in (1, 2)]
    time.sleep(1.2)
    r2 = rodar("--empresa", "EMPRESA-TESTE", "--pasta", "T004/XLSX", "--resumo")[1]
    a2 = [rodar("--empresa", "EMPRESA-TESTE", "--arquivo", x05["id"], "--parte", str(n))[1] for n in (1, 2)]

    def valido(v):
        if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", v):
            return False
        return dt.datetime.fromisoformat(v).tzinfo is not None

    sem = lambda d: {k: v for k, v in d.items() if k != "executado_em"}
    todas = [r1, r2, *a1, *a2]
    registrar("I-24a executado_em presente em --resumo e --arquivo/--parte", all("executado_em" in d for d in todas))
    registrar("I-24b ISO 8601 válido com fuso explícito", all(valido(d.get("executado_em")) for d in todas), r1.get("executado_em", ""))
    registrar("I-24c executado_em não altera hash nem id", all(d["sha256"] == hash_real and d["id"] == x05["id"] for d in [*a1, *a2])
              and por_nome(r2["itens"], "XLSX-05")["sha256"] == hash_real and por_nome(r2["itens"], "XLSX-05")["id"] == x05["id"])
    registrar("I-24d executado_em não altera identidade/divisão das partes",
              r1["executado_em"] != r2["executado_em"] and sem(r1) == sem(r2) and all(sem(x) == sem(y) for x, y in zip(a1, a2)),
              f"{r1['executado_em']} → {r2['executado_em']}; demais campos idênticos")

    # I-20 + I-23 orçamento e reconstrução sem perda em TODAS as fixtures
    pastas = [("EMPRESA-TESTE", p) for p in ("T004/PDF", "T004/SCAN", "T004/XLSX", "T004/XML", "T004-MISTO", "T004-INJ", "TREINAMENTO/2026-09/DOCUMENTOS")] + [("EMPRESA-ISOLAMENTO", "T004")]
    falhas_rec, n_arquivos, n_partes = [], 0, 0
    for empresa, pasta in pastas:
        ref = completo(empresa, pasta)
        for item in resumo(empresa, pasta):
            ps = todas_as_partes(empresa, item["id"])
            n_arquivos += 1
            n_partes += len(ps)
            esperado = unidades_completas(ref[item["arquivo"]])
            if reconstruir(ps) != esperado or ps[0][0]["leitura"] != ref[item["arquivo"]]["leitura"]:
                falhas_rec.append(item["arquivo"])
    registrar("I-23 reconstrução sem perda (todas as fixtures)", not falhas_rec, f"{n_arquivos} arquivos, {n_partes} partes" + (f"; falhas: {falhas_rec}" if falhas_rec else ""))
    registrar("I-20 nenhuma resposta acima do orçamento", maior_saida[0] <= ORCAMENTO, f"maior resposta: {maior_saida[0]} caracteres ({maior_saida[1][:70]})")


def main():
    for t in (TMP17, TMP19):
        if t.exists():
            remover(t)
    try:
        bateria()
    finally:
        for t in (TMP17, TMP19):
            if t.exists():
                remover(t)
    largura = max(len(c) for c, _, _ in resultados)
    for c, ok, det in resultados:
        print(f"{'PASS' if ok else 'FAIL'}  {c.ljust(largura)}  {det}")
    falhas = [c for c, ok, _ in resultados if not ok]
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - len(falhas)} PASS · {len(falhas)} FAIL")
    print(f"pastas temporárias residuais: {'SIM' if TMP17.exists() or TMP19.exists() else 'não'}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
