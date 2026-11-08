"""Casos fictícios do reprocessamento auditado (sem CLIENTES/ operacional)."""
import json
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "API-LOCAL"))
import reprocessamento


def preparar():
    base = Path(tempfile.mkdtemp(prefix="prime-reproc-"))
    (base / "execucoes" / "SOL-2099-000001").mkdir(parents=True)
    (base / "lotes" / "L-20990101-010101-abcdef").mkdir(parents=True)
    arquivo = base / "documento.txt"
    arquivo.write_text("DADO FICTÍCIO\n", encoding="utf-8")
    h = reprocessamento.sha256(arquivo)
    (base / "lotes" / "L-20990101-010101-abcdef" / "lote.json").write_text(json.dumps({"arquivos": [{"nome_interno": "documento.txt", "caminho": str(arquivo), "sha256": h}]}), encoding="utf-8")
    execucao = {"lote": "L-20990101-010101-abcdef", "status": "CONCLUIDA"}
    registro = {"empresa": "EMPRESA-FICTICIA", "competencia": "2099-01"}
    return base, registro, execucao, arquivo, h


def main():
    ok = 0
    base, registro, execucao, arquivo, h = preparar()
    e = reprocessamento.elegibilidade(base, "SOL-2099-000001", registro, execucao)
    assert e["elegivel"]  # REPROC-01
    t1 = reprocessamento.criar(base, "SOL-2099-000001", origem={"numero": 1}, motivo="Atualização do leitor", solicitante="Supervisor", documentos=e["documentos"])
    assert t1["numero"] == 1; ok += 1
    assert reprocessamento.listar(base, "SOL-2099-000001")[0]["motivo"] == "Atualização do leitor"  # 02
    assert t1["documentos"][0]["sha256"] == h  # 03
    arquivo.write_text("ALTERADO\n", encoding="utf-8")
    e2 = reprocessamento.elegibilidade(base, "SOL-2099-000001", registro, execucao)
    assert not e2["elegivel"] and any("SHA" in x for x in e2["motivos"]); ok += 1  # 04
    arquivo.write_text("DADO FICTÍCIO\n", encoding="utf-8")
    t1["resultado"] = {"leitura": "EXTRAIDO_PLANILHA", "leitor": "CALAMINE_FALLBACK"}
    reprocessamento.gravar(base / "execucoes" / "SOL-2099-000001" / "tentativas" / "0001" / "tentativa.json", t1)
    assert reprocessamento.listar(base, "SOL-2099-000001")[0]["resultado"]["leitura"] == "EXTRAIDO_PLANILHA"; ok += 1
    t2 = reprocessamento.criar(base, "SOL-2099-000001", origem=t1, motivo="Correção do leitor XLSX", solicitante="Supervisor", documentos=e["documentos"])
    assert t2["numero"] == 2; ok += 1  # 05
    assert reprocessamento.listar(base, "SOL-2099-000001")[-1]["numero"] == 2; ok += 1  # 06
    assert len(reprocessamento.comparar(reprocessamento.listar(base, "SOL-2099-000001"))) == 2; ok += 1  # 07
    t1["pendencias"] = ["P-01"]
    reprocessamento.gravar(base / "execucoes" / "SOL-2099-000001" / "tentativas" / "0001" / "tentativa.json", t1)
    t2["pendencias"] = []
    assert reprocessamento.listar(base, "SOL-2099-000001")[0]["pendencias"] == ["P-01"]; ok += 1  # 08
    assert t2["sol"] == "SOL-2099-000001"; ok += 1  # 09
    assert t2["motivo"] == "Correção do leitor XLSX"; ok += 1  # 10
    assert t2["versao_codigo"]; ok += 1  # 11
    assert arquivo.read_text(encoding="utf-8") == "DADO FICTÍCIO\n"; ok += 1  # 12
    assert reprocessamento.comparar(reprocessamento.listar(base, "SOL-2099-000001"))[1]["numero"] == 2; ok += 1
    print(f"{ok}/12 PASS")


if __name__ == "__main__":
    main()
