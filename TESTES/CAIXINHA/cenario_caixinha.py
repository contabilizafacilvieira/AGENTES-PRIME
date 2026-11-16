"""Preparação FICTÍCIA da rotina Caixinha pela API real (ambiente isolado): cadastro, plano, rotina, regras, aprovação e piloto."""
import base64
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "TESTES" / "CAIXINHA"))
import ficticios_caixinha as fc  # noqa: E402

COMPETENCIA = fc.COMPETENCIA


def configuracao(contas=None, politica="DATA_PAGAMENTO_OU_ULTIMO_DIA", desde=COMPETENCIA):
    import regras_caixinha
    return {"contas": dict(contas or fc.ROTINA), "tributos": json.loads(json.dumps(regras_caixinha.TRIBUTOS_SUGERIDOS)),
            "politica_datas": {"tributos": politica}, "criterios_baixa": dict(regras_caixinha.CRITERIOS_PADRAO),
            "competencia_desde": desde, "competencia_ate": None}


def politica_folha(desde=COMPETENCIA):
    return {"regra": "MANTER_ULTIMO_LIQUIDO", "conta": "PRO_LABORE", "data_lancamento": {"politica": "ULTIMO_DIA_COMPETENCIA"},
            "competencia_desde": desde, "competencia_ate": None}


def cadastrar(c, cenario="A", ficticia=True, clientes=None):
    """Empresa fictícia com plano, rotina CAIXINHA e piloto (sem vínculo bancário). Regras NÃO aprovadas aqui."""
    e = fc.EMPRESAS[cenario]
    s, r = c.j("POST", "/api/empresas", {"id": e["id"], "nome": e["nome"], "cnpj": e["cnpj"], "regime": "SIMPLES NACIONAL (FICTICIO)"})
    assert s == 201, (s, r)
    csv = "codigo;classificacao;descricao;grupo;tipo\n" + "\n".join(f"{a};{b};{d};{g};{t}" for a, b, d, g, t in fc.PLANO) + "\n"
    s, r = c.j("POST", f"/api/empresas/{e['id']}/previa", {"nome": "plano.csv", "conteudo": base64.b64encode(csv.encode()).decode()})
    assert s == 200, (s, r)
    s, r = c.j("POST", f"/api/empresas/{e['id']}/plano", {"token": r["token"], "salvar": True, "confirmado": True})
    assert s == 200, (s, r)
    s, r = c.j("POST", f"/api/empresas/{e['id']}/caixinha-rotina", {"rotina": "CAIXINHA", "justificativa": "Cliente sem extrato (fictício).",
                                                                    "confirmado": True})
    assert s == 200 and r.get("tipo_rotina") == "CAIXINHA", (s, r)
    if ficticia and clientes is not None:
        (Path(clientes) / e["id"] / "AMOSTRA-FICTICIA.json").write_text(json.dumps({"ficticia": True, "amostra": "CAIXINHA"}), encoding="utf-8")
    return e["id"]


def salvar_regras(c, emp, cfg=None, folha=None):
    corpo = {"confirmado": True}
    if cfg is not False:
        corpo["configuracao"] = cfg or configuracao()
    if folha is not False:
        corpo["politica_folha"] = folha or politica_folha()
    return c.j("POST", f"/api/empresas/{emp}/caixinha-regras", corpo)


def aprovar(c, emp, chave):
    return c.j("POST", f"/api/empresas/{emp}/caixinha-aprovar", {"chave": chave, "frase": f"VALIDADO REGRA CAIXINHA {emp} {chave}", "confirmado": True})


def habilitar(c, emp):
    return c.j("POST", f"/api/empresas/{emp}/piloto", {"frase": f"CONFIRMO PILOTO {emp}"})


def criar_lote(c, emp, docs, competencia=COMPETENCIA):
    a, m = competencia.split("-")
    s, r = c.j("POST", "/api/lotes", {"empresa": emp, "competencia": competencia, "fluxo": "CONCILIACAO_CAIXINHA",
                                      "instrucao": f"Conciliação Caixinha fictícia de {m}/{a}."})
    assert s == 201, (s, r)
    for nome, conteudo in docs:
        s2, r2 = c.enviar(r["lote"], nome, conteudo)
        assert s2 == 201, (nome, s2, r2)
    return r["lote"]


def iniciar(c, lote):
    return c.j("POST", f"/api/lotes/{lote}/iniciar", {"conferencia_humana": True})
