"""Governança das regras por empresa (DP, Fiscal, Conciliação e política de data dos lançamentos).

Cada referência (ex.: evento de DP, tributo, exigência da Conciliação, política de data) declara:
- situacao: REFERENCIA (histórico/consulta, NÃO aplicada) | PROPOSTA (aguarda o Supervisor, NÃO aplicada) |
            APROVADA (aplicada; exige confirmação do Supervisor com a frase exata) |
            TESTE_FICTICIO (aplicada SOMENTE em empresa fictícia com o marcador AMOSTRA-FICTICIA.json);
- origem, versao, competencia_desde/competencia_ate (vigência), confirmacao {frase, em, por} e escopo.
Referência sem "situacao" (anterior a este controle) é tratada como REFERENCIA: nunca vira regra aprovada em silêncio.
Nenhuma aprovação é presumida ou criada retroativamente: só o comando do Coordenador (frase exata) grava APROVADA.
"""
import os
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SITUACOES = ("REFERENCIA", "PROPOSTA", "APROVADA", "TESTE_FICTICIO")
APLICAVEIS = ("APROVADA", "TESTE_FICTICIO")
MARCA_FICTICIA = "AMOSTRA-FICTICIA.json"
COMPETENCIA = re.compile(r"20\d{2}-(0[1-9]|1[0-2])")
AREAS = {"DP": "REGRAS-DP.json", "FISCAL": "REGRAS-FISCAIS.json", "CONCILIACAO": "REGRAS-CONCILIACAO.json"}
POLITICAS_DATA = {"ULTIMO_DIA_COMPETENCIA": "último dia da competência do fato",
                  "DATA_EMISSAO_DOCUMENTO": "data de emissão do documento (somente quando documentada)"}
# Políticas que os leitores atuais NÃO conseguem cumprir: nunca aplicadas nem confirmáveis (sem substituição por outra data).
POLITICAS_NAO_SUPORTADAS = {"DATA_EMISSAO_DOCUMENTO": "os leitores atuais de DP e Fiscal não extraem a data de emissão dos documentos; "
                                                      "a política não pode ser usada nesta versão (nenhuma outra data é usada no lugar)"}
RESPONSAVEL = "Supervisor Contábil"


def ler_texto(caminho) -> str:
    """Leitura tolerante ao instante da substituição atômica (Windows: PermissionError momentâneo durante os.replace)."""
    import time
    for i in range(40):
        try:
            return Path(caminho).read_text(encoding="utf-8")
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def clientes() -> Path:
    return Path(os.environ.get("AGENTES_PRIME_CLIENTES") or RAIZ / "CLIENTES")


def empresa_ficticia(empresa: str, base=None) -> bool:
    """base = pasta da empresa usada pelo chamador (mesma pasta de onde as regras foram lidas)."""
    return (Path(base) if base else clientes() / empresa).joinpath(MARCA_FICTICIA).is_file()


def frase(area: str, empresa: str, chave: str) -> str:
    # Bancos mantém a frase já usada na aprovação pela fila de decisões: "VALIDADO REGRA <EMPRESA> <RB-NNN>"
    return f"VALIDADO REGRA {empresa} {chave}" if area == "BANCOS" else f"VALIDADO REGRA {area} {empresa} {chave}"


def texto_confirmacao_bancos(empresa: str, regra: str, versao, em: str) -> str:
    """Confirmação estruturada gravada na coluna Aprovação de REGRAS-BANCOS.md (sem '|'): empresa+regra (frase), versão, responsável, data."""
    return f"CONFIRMADA; frase={frase('BANCOS', empresa, regra)}; versao={versao}; por={RESPONSAVEL}; em={em}"


def confirmacao_bancos(texto, empresa: str, regra: str, versao) -> dict:
    """{'valida', 'situacao', 'motivo'} da coluna Aprovação de uma regra bancária VALIDADA.
    CONFIRMADA = frase exata desta empresa/regra + versão igual à da linha + responsável + data → aplicada.
    LEGADA_SEM_VERSAO = frase exata e data, mas sem versão/responsável (formato anterior) → NÃO aplicada; reconfirmar.
    INSUFICIENTE = qualquer outro texto → NÃO aplicada; confirmação necessária. Nada é aprovado retroativamente."""
    t = str(texto or "").strip()
    esperado = frase("BANCOS", empresa, regra)
    if t.upper().startswith("CONFIRMADA;"):
        campos = {k.strip().lower(): v.strip() for k, _, v in (p.partition("=") for p in t.split(";")[1:]) if k.strip()}
        faltas = []
        if campos.get("frase") != esperado:
            faltas.append(f"frase diferente de \"{esperado}\"")
        if str(campos.get("versao")) != str(versao).strip():
            faltas.append(f"versão confirmada {campos.get('versao') or '-'} ≠ versão da regra {versao}")
        if not campos.get("por"):
            faltas.append("responsável ausente")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*", campos.get("em") or ""):
            faltas.append("data ausente ou inválida")
        if not faltas:
            return {"valida": True, "situacao": "CONFIRMADA", "motivo": None}
        return {"valida": False, "situacao": "INSUFICIENTE", "motivo": "confirmação incompleta: " + "; ".join(faltas)}
    if re.fullmatch(r'"' + re.escape(esperado) + r'" em \d{4}-\d{2}-\d{2}', t):
        return {"valida": False, "situacao": "LEGADA_SEM_VERSAO",
                "motivo": "confirmação anterior ao vínculo de versão e responsável (frase e data registradas); reconfirme a versão atual"}
    return {"valida": False, "situacao": "INSUFICIENTE",
            "motivo": "campo Aprovação não comprova a confirmação do Supervisor (frase, versão, responsável e data)"}


def pendencias_bancos(empresa: str, base=None) -> list:
    """Regras bancárias que precisam de decisão do Supervisor (VALIDADA sem confirmação suficiente, PROPOSTA, teste em empresa real)."""
    import sys
    sys.path.insert(0, str(RAIZ / "AGENTES" / "CONTABILIDADE" / "BANCOS" / "ferramentas"))
    from lancamentos_bancarios import tabela_md, norm
    arquivo = (Path(base) if base else clientes() / empresa) / "REGRAS-BANCOS.md"
    if not arquivo.is_file():
        return []
    itens = []
    for l in tabela_md(ler_texto(arquivo), "Regras"):
        regra, situacao = l.get("REGRA"), norm(l.get("SITUACAO"))
        tipo = norm(l.get("TIPO")).replace(" ", "_")
        if not regra or tipo.startswith("ADIANTAMENTO_"):
            continue
        item = {"area": "BANCOS", "chave": regra, "arquivo": "REGRAS-BANCOS.md", "frase": frase("BANCOS", empresa, regra)}
        if situacao == "VALIDADA":
            c = confirmacao_bancos(l.get("APROVACAO"), empresa, regra, l.get("VERSAO"))
            if not c["valida"]:
                itens.append(dict(item, situacao=c["situacao"], pergunta=f"Regra bancária {regra} (versão {l.get('VERSAO')}) não aplicada: {c['motivo']}."))
        elif situacao == "PROPOSTA":
            itens.append(dict(item, situacao="PROPOSTA", pergunta=f"Regra bancária {regra} proposta: aprovar a versão {l.get('VERSAO')}?"))
        elif situacao == "TESTE_FICTICIO" and not empresa_ficticia(empresa, arquivo.parent):
            itens.append(dict(item, situacao="TESTE_FICTICIO", frase=None,
                              pergunta=f"Regra bancária {regra} é de TESTE fictício e não vale para empresa real."))
    return itens


def avaliar(regra, area: str, empresa: str, chave: str, competencia: str = None, base=None) -> dict:
    """{'aplicavel': bool, 'motivo': texto|None, 'governanca': resumo rastreável}. Nunca aprova nada."""
    if not isinstance(regra, dict):
        return {"aplicavel": False, "motivo": f"{area}/{chave}: referência ausente ou malformada.", "governanca": None}
    situacao = str(regra.get("situacao") or "").upper() or None
    gov = {"chave": chave, "situacao": situacao or "REFERENCIA", "origem": regra.get("origem") or regra.get("fonte"),
           "versao": regra.get("versao"), "vigencia": {"desde": regra.get("competencia_desde"), "ate": regra.get("competencia_ate")},
           "confirmacao": regra.get("confirmacao"), "escopo": regra.get("escopo")}
    esperado = frase(area, empresa, chave)
    if situacao is None:
        return {"aplicavel": False, "governanca": gov,
                "motivo": f"{area}/{chave}: referência sem situação declarada (anterior ao controle de governança) é tratada como "
                          f"REFERÊNCIA e não é aplicada. Para aplicar, o Supervisor confirma com a frase \"{esperado}\"."}
    if situacao not in SITUACOES:
        return {"aplicavel": False, "governanca": gov, "motivo": f"{area}/{chave}: situação \"{situacao}\" desconhecida; não aplicada."}
    if situacao in ("REFERENCIA", "PROPOSTA"):
        return {"aplicavel": False, "governanca": gov,
                "motivo": f"{area}/{chave}: regra em situação {situacao}, não aplicada; aguarda confirmação do Supervisor "
                          f"(frase \"{esperado}\")."}
    if situacao == "TESTE_FICTICIO" and not empresa_ficticia(empresa, base):
        return {"aplicavel": False, "governanca": gov,
                "motivo": f"{area}/{chave}: regra de TESTE FICTÍCIO não vale para empresa real (sem o marcador {MARCA_FICTICIA})."}
    if situacao == "APROVADA":
        c = regra.get("confirmacao") or {}
        if c.get("frase") != esperado or not c.get("em") or not c.get("por"):
            return {"aplicavel": False, "governanca": gov,
                    "motivo": f"{area}/{chave}: marcada APROVADA sem confirmação válida do Supervisor (frase \"{esperado}\", data e "
                              "responsável); não aplicada."}
    if not str(regra.get("origem") or regra.get("fonte") or "").strip():
        return {"aplicavel": False, "governanca": gov, "motivo": f"{area}/{chave}: regra sem origem documentada; não aplicada."}
    if competencia:
        desde, ate = regra.get("competencia_desde"), regra.get("competencia_ate")
        for nome, v in (("início", desde), ("fim", ate)):
            if v is not None and not COMPETENCIA.fullmatch(str(v)):
                return {"aplicavel": False, "governanca": gov, "motivo": f"{area}/{chave}: vigência ({nome}) inválida."}
        if desde is not None and competencia < desde:
            return {"aplicavel": False, "governanca": gov, "motivo": f"{area}/{chave}: regra ainda não vigente em {competencia}."}
        if ate is not None and competencia > ate:
            return {"aplicavel": False, "governanca": gov, "motivo": f"{area}/{chave}: regra encerrada antes de {competencia}."}
    return {"aplicavel": True, "motivo": None, "governanca": gov}


def politica_data(dados: dict, area: str, empresa: str, competencia: str, base=None) -> dict:
    """Política de DATA DO LANÇAMENTO (separada da competência do fato). Sem política aplicável: data não é presumida."""
    regra = (dados or {}).get("data_lancamento")
    if regra is None:
        return {"aplicavel": False, "politica": None, "governanca": None,
                "motivo": f"Data do lançamento ({area}) não definida para a empresa: nenhuma política de data registrada. Defina a política "
                          f"(ex.: último dia da competência) e confirme com a frase \"{frase(area, empresa, 'DATA_LANCAMENTO')}\"."}
    politica = str((regra or {}).get("politica") or "").upper() if isinstance(regra, dict) else ""
    if politica in POLITICAS_NAO_SUPORTADAS:
        return {"aplicavel": False, "politica": None, "governanca": None,
                "motivo": f"{area}/DATA_LANCAMENTO: política {politica} indisponível — {POLITICAS_NAO_SUPORTADAS[politica]}. "
                          "Defina outra política para a empresa."}
    r = avaliar(regra, area, empresa, "DATA_LANCAMENTO", competencia, base)
    if r["aplicavel"] and politica not in POLITICAS_DATA:
        r = dict(r, aplicavel=False, motivo=f"{area}/DATA_LANCAMENTO: política \"{politica}\" desconhecida.")
    return dict(r, politica=politica if r["aplicavel"] else None)


def definicoes_necessarias(empresa: str, dados_por_area: dict = None) -> list:
    """Lista objetiva do que falta o Supervisor definir/confirmar (regras não aplicáveis por situação)."""
    itens = []
    for area, arquivo in AREAS.items():
        caminho = clientes() / empresa / arquivo
        dados = (dados_por_area or {}).get(area)
        if dados is None:
            if not caminho.is_file():
                itens.append({"area": area, "chave": None, "situacao": "AUSENTE", "arquivo": arquivo,
                              "pergunta": f"Quais as referências de {area} desta empresa? ({arquivo} inexistente)"})
                continue
            try:
                import json
                dados = json.loads(ler_texto(caminho))
            except (OSError, ValueError):
                itens.append({"area": area, "chave": None, "situacao": "INVALIDO", "arquivo": arquivo,
                              "pergunta": f"{arquivo} ilegível: corrigir o arquivo de referências de {area}."})
                continue
        grupo = dados.get("exigencias" if area == "CONCILIACAO" else "referencias") or {}
        chaves = dict(grupo)
        if area in ("DP", "FISCAL"):
            chaves["DATA_LANCAMENTO"] = dados.get("data_lancamento")
        for chave, regra in chaves.items():
            if regra is None:
                itens.append({"area": area, "chave": chave, "situacao": "AUSENTE", "arquivo": arquivo,
                              "pergunta": f"Qual a data dos lançamentos de {area} desta empresa (competência ≠ data do lançamento)?",
                              "frase": frase(area, empresa, chave)})
                continue
            politica = str(regra.get("politica") or "").upper() if chave == "DATA_LANCAMENTO" else ""
            if politica in POLITICAS_NAO_SUPORTADAS:
                itens.append({"area": area, "chave": chave, "situacao": "NAO_SUPORTADA", "arquivo": arquivo, "frase": None,
                              "pergunta": f"Política de data {politica} indisponível: {POLITICAS_NAO_SUPORTADAS[politica]}. Defina outra política."})
                continue
            r = avaliar(regra, area, empresa, chave)
            if not r["aplicavel"]:
                itens.append({"area": area, "chave": chave, "situacao": r["governanca"]["situacao"] if r["governanca"] else "INVALIDO",
                              "arquivo": arquivo, "pergunta": r["motivo"], "frase": frase(area, empresa, chave)})
    return pendencias_bancos(empresa) + itens
