"""Consulta somente leitura da base normativa/técnica; nunca produz lançamentos ou aprova regras."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Iterable

RAIZ = Path(__file__).resolve().parent
CATEGORIAS = (
    "NORMAS_CONTABEIS", "LEGISLACAO_TRIBUTARIA", "LEGISLACAO_TRABALHISTA",
    "PROCEDIMENTOS_CONTABEIS", "POLITICAS_CONTABEIS", "CONTROLES_INTERNOS",
    "REFERENCIAS_NORMATIVAS",
)
STATUS = {"VERIFICADO", "PARCIAL", "PENDENTE", "NAO_VERIFICADO"}


def normalizar(valor) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).replace("_", " ")
    return " ".join(texto.casefold().split())


def carregar(base: Path = RAIZ) -> list[dict]:
    """Carrega registros das sete categorias, valida campos mínimos e IDs únicos."""
    registros = []
    for categoria in CATEGORIAS:
        arquivo = base / categoria / "registros.json"
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        if not isinstance(dados, list):
            raise ValueError(f"{arquivo}: esperado array JSON")
        for registro in dados:
            validar_registro(registro)
            registro = dict(registro)
            registro["_CATEGORIA"] = categoria
            registros.append(registro)
    ids = [r["ID"] for r in registros]
    if len(ids) != len(set(ids)):
        raise ValueError("IDs de conhecimento duplicados")
    return registros


def validar_registro(r: dict) -> None:
    obrigatorios = {
        "ID", "TITULO", "ASSUNTO", "DEPARTAMENTO", "NORMA", "DISPOSITIVO",
        "FONTE_OFICIAL", "DATA_CONSULTA", "VIGENCIA", "APLICABILIDADE",
        "RESUMO_TECNICO", "LIMITACOES", "STATUS_VERIFICACAO", "VERSAO",
        "TIPO_CONHECIMENTO", "ESCOPO", "AUTORIZA_DECISAO_AUTOMATICA",
    }
    faltantes = obrigatorios - r.keys()
    if faltantes:
        raise ValueError(f"{r.get('ID', '<sem ID>')}: campos ausentes {sorted(faltantes)}")
    if r["STATUS_VERIFICACAO"] not in STATUS:
        raise ValueError(f"{r['ID']}: STATUS_VERIFICACAO inválido")
    if r["AUTORIZA_DECISAO_AUTOMATICA"] is not False:
        raise ValueError(f"{r['ID']}: conhecimento não pode autorizar decisão automática")
    if r["ESCOPO"]["TIPO"] == "EMPRESA" and not r["ESCOPO"].get("EMPRESA_ID"):
        raise ValueError(f"{r['ID']}: regra de empresa exige EMPRESA_ID")


def _lista(valor) -> list[str]:
    if isinstance(valor, list):
        return valor
    return [parte.strip() for parte in str(valor or "").split(";") if parte.strip()]


def _contido(filtro: str, valores: Iterable[str]) -> bool:
    alvo = normalizar(filtro)
    return any(alvo in normalizar(v) for v in valores)


def vigente_na_competencia(r: dict, competencia: str | None) -> bool:
    if not competencia:
        return True
    if not re.fullmatch(r"\d{4}-\d{2}", competencia):
        raise ValueError("competencia deve usar AAAA-MM")
    inicio = r["VIGENCIA"].get("INICIO")
    fim = r["VIGENCIA"].get("FIM")
    return not ((inicio and competencia < inicio[:7]) or (fim and competencia > fim[:7]))


def consultar(*, departamento: str | None = None, assunto: str | None = None,
              referencial_contabil: str | None = None, competencia: str | None = None,
              tipo_operacao: str | None = None, regime_tributario: str | None = None,
              uf: str | None = None, municipio: str | None = None,
              empresa_id: str | None = None, status: str | None = None,
              incluir_pendentes: bool = True, registros: list[dict] | None = None) -> list[dict]:
    """Pesquisa interseção dos filtros; regras específicas só aparecem para a mesma empresa."""
    dados = carregar() if registros is None else registros
    if status and status not in STATUS:
        raise ValueError(f"status deve ser um de {sorted(STATUS)}")
    resultado = []
    for r in dados:
        ap, escopo = r["APLICABILIDADE"], r["ESCOPO"]
        if escopo["TIPO"] == "EMPRESA" and escopo.get("EMPRESA_ID") != empresa_id:
            continue
        if not incluir_pendentes and r["STATUS_VERIFICACAO"] != "VERIFICADO":
            continue
        if status and r["STATUS_VERIFICACAO"] != status:
            continue
        if departamento and not _contido(departamento, _lista(r["DEPARTAMENTO"])):
            continue
        if assunto and not _contido(assunto, _lista(r["ASSUNTO"]) + [r["TITULO"]]):
            continue
        if referencial_contabil and not _contido(referencial_contabil, ap["REFERENCIAL_CONTABIL"]):
            continue
        if competencia and not vigente_na_competencia(r, competencia):
            continue
        if tipo_operacao and not _contido(tipo_operacao, ap["TIPO_OPERACAO"]):
            continue
        if regime_tributario and not _contido(regime_tributario, ap["REGIME_TRIBUTARIO"]):
            continue
        if uf and not _contido(uf, ap["UF"]):
            continue
        if municipio and not _contido(municipio, ap["MUNICIPIO"]):
            continue
        resultado.append(r)
    return sorted(resultado, key=lambda r: (r["STATUS_VERIFICACAO"] != "VERIFICADO", r["ID"]))


def detectar_conflitos(registros: list[dict]) -> list[dict]:
    """Marca posições incompatíveis na mesma chave para revisão; não escolhe precedência."""
    grupos: dict[str, list[dict]] = {}
    for r in registros:
        chave, posicao = r.get("CONFLITO_CHAVE"), r.get("CONFLITO_POSICAO")
        if chave and posicao:
            grupos.setdefault(chave, []).append(r)
    return [
        {"CONFLITO_CHAVE": chave, "REGISTROS": [r["ID"] for r in itens],
         "POSICOES": sorted({r["CONFLITO_POSICAO"] for r in itens}),
         "RESULTADO": "PENDENTE_REVISAO"}
        for chave, itens in sorted(grupos.items())
        if len({r["CONFLITO_POSICAO"] for r in itens}) > 1
    ]


def autoriza_decisao_critica(_registro: dict) -> bool:
    """A consulta nunca substitui aprovação humana, política validada ou evidência."""
    return False


def consultar_cobertura(*, departamento: str | None = None, assunto: str | None = None,
                        status: str | None = None, prioridade: str | None = None,
                        base: Path = RAIZ) -> list[dict]:
    """Consulta o inventário de temas, inclusive os que ainda não têm orientação normativa."""
    dados = json.loads((base / "cobertura.json").read_text(encoding="utf-8"))["ITENS"]
    if status and status not in STATUS:
        raise ValueError(f"status deve ser um de {sorted(STATUS)}")
    if prioridade and prioridade not in {"P0", "P1", "P2"}:
        raise ValueError("prioridade deve ser P0, P1 ou P2")
    saida = []
    for item in dados:
        if departamento and not _contido(departamento, _lista(item["DEPARTAMENTO"])):
            continue
        if assunto and not _contido(assunto, [item["ASSUNTO"]]):
            continue
        if status and item["STATUS"] != status:
            continue
        if prioridade and item.get("PRIORIDADE") != prioridade:
            continue
        saida.append(item)
    return sorted(saida, key=lambda x: (x["STATUS"] != "VERIFICADO", x["DEPARTAMENTO"], x["ASSUNTO"]))


def carregar_fundamentos(base: Path = RAIZ) -> list[dict]:
    """Carrega fichas contábeis 03C; são orientação consultiva, não regras de lançamento."""
    dados = json.loads((base / "fundamentos_p0.json").read_text(encoding="utf-8"))["REGISTROS"]
    ids = [r["ID"] for r in dados]
    if len(ids) != len(set(ids)):
        raise ValueError("IDs de fundamentos P0 duplicados")
    for r in dados:
        campos_legado = {"ID", "CONCEITO", "CONDICOES_RECONHECIMENTO", "EVIDENCIA_NECESSARIA",
                         "TRATAMENTO_GERAL", "EXCECOES", "RISCOS", "REFERENCIAL",
                         "VIGENCIA", "DISPOSITIVO", "FONTE_OFICIAL", "STATUS_VERIFICACAO",
                         "LIMITACAO_REFERENCIAL", "AUTORIZA_DECISAO_AUTOMATICA"}
        campos_03c = {"ID", "CONCEITO", "OBJETIVO", "NORMA", "DISPOSITIVO", "FONTE_OFICIAL",
                      "VIGENCIA", "REFERENCIAL_APLICAVEL", "CONDICOES_RECONHECIMENTO",
                      "CRITERIOS_MENSURACAO", "EVIDENCIAS_NECESSARIAS", "TRATAMENTO_CONTABIL_CONCEITUAL",
                      "EXEMPLO_FICTICIO", "EXCECOES", "ERROS_COMUNS", "RISCOS", "LIMITACOES",
                      "STATUS_VERIFICACAO", "AUTORIZA_DECISAO_AUTOMATICA"}
        campos = campos_03c if r.get("ID", "").startswith("CONT-") else campos_legado
        faltantes = campos - r.keys()
        if faltantes:
            raise ValueError(f"{r.get('ID', '<sem ID>')}: fundamentos sem campos {sorted(faltantes)}")
        if r["STATUS_VERIFICACAO"] not in STATUS or r["AUTORIZA_DECISAO_AUTOMATICA"] is not False:
            raise ValueError(f"{r['ID']}: estado ou autorização inválidos")
        if not r["FONTE_OFICIAL"] or not r["DISPOSITIVO"]:
            raise ValueError(f"{r['ID']}: fundamento sem dispositivo ou fonte")
    return dados


def consultar_fundamento_id(fundamento_id: str, *, base: Path = RAIZ) -> dict:
    """Busca um fundamento identificado; estados abaixo de VERIFICADO continuam bloqueados."""
    registro = next((r for r in carregar_fundamentos(base) if r["ID"] == fundamento_id), None)
    if registro is None:
        raise KeyError(f"fundamento contábil inexistente: {fundamento_id}")
    return registro


def consultar_fundamento_verificado(fundamento_id: str, *, base: Path = RAIZ) -> dict:
    """Retorna apenas fundamento verificado; parcial/pendente bloqueia uso como base suficiente."""
    registro = consultar_fundamento_id(fundamento_id, base=base)
    if registro["STATUS_VERIFICACAO"] != "VERIFICADO":
        raise PermissionError(f"{fundamento_id} está {registro['STATUS_VERIFICACAO']}; requer revisão e evidência adicional")
    return registro


def consultar_fundamentos(*, assunto: str | None = None, referencial: str | None = None,
                          status: str | None = None, base: Path = RAIZ) -> list[dict]:
    """Busca fichas técnicas dos fundamentos; não infere aplicabilidade a empresa."""
    if status and status not in STATUS:
        raise ValueError(f"status deve ser um de {sorted(STATUS)}")
    resultado = []
    for r in carregar_fundamentos(base):
        if assunto and not _contido(assunto, [r.get("CONCEITO", ""), r.get("TITULO", ""), r.get("ASSUNTO", "")]):
            continue
        if referencial and not _contido(referencial, r.get("REFERENCIAL", r.get("REFERENCIAL_APLICAVEL", []))):
            continue
        if status and r["STATUS_VERIFICACAO"] != status:
            continue
        resultado.append(r)
    return sorted(resultado, key=lambda r: (r["STATUS_VERIFICACAO"] != "VERIFICADO", r["ID"]))


def carregar_fundamentos_financeiros(base: Path = RAIZ) -> list[dict]:
    """Carrega fichas 03D, validando estrutura e bloqueio de decisão automática."""
    dados = json.loads((base / "fundamentos_financeiros.json").read_text(encoding="utf-8"))["REGISTROS"]
    ids = [r["ID"] for r in dados]
    if len(ids) != len(set(ids)) or set(ids) != {f"FIN-{i:02d}" for i in range(1, 21)}:
        raise ValueError("fundamentos financeiros: esperado o conjunto único FIN-01..FIN-20")
    obrigatorios = {"ID", "CONCEITO", "OBJETIVO", "FUNDAMENTO", "FONTES", "DISPOSITIVO", "VIGENCIA",
                    "APLICABILIDADE", "EVIDENCIAS_NECESSARIAS", "TRATAMENTO_CONCEITUAL", "EXCECOES",
                    "RISCOS", "ERROS_COMUNS", "PROCEDIMENTO_INTERNO_RELACIONADO", "EXEMPLO_FICTICIO",
                    "STATUS_VERIFICACAO", "TIPO_CONHECIMENTO", "REFERENCIAL", "LIMITACOES",
                    "AUTORIZA_DECISAO_AUTOMATICA"}
    for r in dados:
        if obrigatorios - r.keys():
            raise ValueError(f"{r.get('ID')}: ficha financeira incompleta: {sorted(obrigatorios-r.keys())}")
        if r["STATUS_VERIFICACAO"] not in STATUS or r["AUTORIZA_DECISAO_AUTOMATICA"] is not False:
            raise ValueError(f"{r['ID']}: status/autorização inválidos")
        if not r["FONTES"] or not r["DISPOSITIVO"] or not r["EVIDENCIA_CONSULTA"]:
            raise ValueError(f"{r['ID']}: fonte, dispositivo ou evidência de consulta ausente")
        if r["TIPO_CONHECIMENTO"] == "PROCEDIMENTO_INTERNO" and not r["PROCEDIMENTO_INTERNO_RELACIONADO"]:
            raise ValueError(f"{r['ID']}: procedimento interno sem vínculo identificado")
    return dados


def consultar_fundamentos_financeiros(*, assunto: str | None = None, referencial: str | None = None,
                                       status: str | None = None, competencia: str | None = None,
                                       base: Path = RAIZ) -> list[dict]:
    """Pesquisa fichas financeiras; sempre consultivas, sem selecionar tratamento da empresa."""
    if status and status not in STATUS:
        raise ValueError(f"status deve ser um de {sorted(STATUS)}")
    achados = []
    for r in carregar_fundamentos_financeiros(base):
        if assunto and not _contido(assunto, [r["ID"], r["CONCEITO"], r["OBJETIVO"], r["FUNDAMENTO"]]):
            continue
        if referencial and not _contido(referencial, r["REFERENCIAL"]):
            continue
        if status and r["STATUS_VERIFICACAO"] != status:
            continue
        vig = r["VIGENCIA"]
        if competencia and (not re.fullmatch(r"\d{4}-\d{2}", competencia)):
            raise ValueError("competencia deve usar AAAA-MM")
        if competencia and vig.get("INICIO") and competencia < vig["INICIO"][:7]:
            continue
        if competencia and vig.get("FIM") and competencia > vig["FIM"][:7]:
            continue
        achados.append(r)
    return sorted(achados, key=lambda r: (r["STATUS_VERIFICACAO"] != "VERIFICADO", r["ID"]))


def consultar_fundamento_financeiro_id(fundamento_id: str, *, exigir_verificado: bool = False,
                                        base: Path = RAIZ) -> dict:
    registro = next((r for r in carregar_fundamentos_financeiros(base) if r["ID"] == fundamento_id), None)
    if registro is None:
        raise KeyError(f"fundamento financeiro inexistente: {fundamento_id}")
    if exigir_verificado and registro["STATUS_VERIFICACAO"] != "VERIFICADO":
        raise PermissionError(f"{fundamento_id} está {registro['STATUS_VERIFICACAO']}; requer revisão e evidência adicional")
    return registro


def consultar_casos_financeiros(*, caso_id: str | None = None, termo: str | None = None,
                                 base: Path = RAIZ) -> list[dict]:
    dados = json.loads((base / "casos_financeiros.json").read_text(encoding="utf-8"))["CASOS"]
    saida = []
    for caso in dados:
        if caso_id and normalizar(caso_id) != normalizar(caso["ID"]):
            continue
        texto = " ".join(str(caso.get(k, "")) for k in ("TITULO", "NATUREZA_PROVAVEL", "TRATAMENTO_CONCEITUAL", "EXEMPLO_FICTICIO"))
        if termo and normalizar(termo) not in normalizar(texto):
            continue
        required = ("FUNDAMENTO_IDS", "EVIDENCIA_NECESSARIA", "DEPARTAMENTO_RESPONSAVEL", "REFERENCIAL",
                    "LIMITACOES", "NECESSIDADE_DECISAO_HUMANA", "FONTES", "DISPOSITIVOS")
        if caso.get("TIPO_CONHECIMENTO") != "EXEMPLO_ILUSTRATIVO" or caso.get("AUTORIZA_DECISAO_AUTOMATICA") is not False:
            raise ValueError(f"{caso.get('ID')}: caso deve ser ilustrativo e não automático")
        if any(not caso.get(k) for k in required) or "fictício" not in caso["EXEMPLO_FICTICIO"].casefold():
            raise ValueError(f"{caso.get('ID')}: caso incompleto ou sem exemplo fictício")
        saida.append(caso)
    return saida


def carregar_fundamentos_dp(base: Path = RAIZ) -> list[dict]:
    """Carrega conhecimento DP consultivo, sem cálculos ou lançamentos."""
    dados = json.loads((base / "fundamentos_dp.json").read_text(encoding="utf-8"))["REGISTROS"]
    ids = [r.get("ID") for r in dados]
    if len(ids) != len(set(ids)) or set(ids) != {f"DP-{i:02d}" for i in range(1, 21)}:
        raise ValueError("fundamentos DP: esperado o conjunto único DP-01..DP-20")
    obrigatorios = {"CONCEITO", "OBJETIVO", "FUNDAMENTO", "FONTES", "DISPOSITIVO", "VIGENCIA",
                    "APLICABILIDADE", "REFERENCIAL", "EVIDENCIAS_NECESSARIAS", "TRATAMENTO_CONCEITUAL",
                    "EXCECOES", "RISCOS", "ERROS_COMUNS", "LIMITACOES", "EXEMPLO_FICTICIO",
                    "STATUS_VERIFICACAO", "STATUS_APLICABILIDADE", "TIPO_CONHECIMENTO",
                    "FUNDAMENTOS_CONTABEIS_RELACIONADOS", "FUNDAMENTOS_FINANCEIROS_RELACIONADOS",
                    "PROCEDIMENTO_INTERNO_RELACIONADO", "EVIDENCIA_CONSULTA", "AUTORIZA_DECISAO_AUTOMATICA"}
    for r in dados:
        faltantes = obrigatorios - r.keys()
        if faltantes:
            raise ValueError(f"{r.get('ID')}: ficha DP incompleta: {sorted(faltantes)}")
        if r["STATUS_VERIFICACAO"] not in STATUS or r["AUTORIZA_DECISAO_AUTOMATICA"] is not False:
            raise ValueError(f"{r['ID']}: status/autorização inválidos")
        if r["STATUS_APLICABILIDADE"] not in {"GERAL_LIMITADA", "DEPENDENTE_DE_CONTEXTO", "NAO_DETERMINADA"}:
            raise ValueError(f"{r['ID']}: aplicabilidade inválida")
        if not r["FONTES"] or not r["DISPOSITIVO"] or not r["EVIDENCIA_CONSULTA"]:
            raise ValueError(f"{r['ID']}: fonte, dispositivo ou evidência ausente")
        if any(not f.get("URL", "").startswith("https://") for f in r["FONTES"]):
            raise ValueError(f"{r['ID']}: fonte inválida")
    return sorted(dados, key=lambda r: r["ID"])


def consultar_fundamentos_dp(*, assunto: str | None = None, referencial: str | None = None,
                              competencia: str | None = None, status: str | None = None,
                              base: Path = RAIZ) -> list[dict]:
    if status and status not in STATUS:
        raise ValueError(f"status deve ser um de {sorted(STATUS)}")
    if competencia and not re.fullmatch(r"\d{4}-\d{2}", competencia):
        raise ValueError("competencia deve usar AAAA-MM")
    achados = []
    for r in carregar_fundamentos_dp(base):
        if assunto and not _contido(assunto, [r["ID"], r["CONCEITO"], r["OBJETIVO"], r["FUNDAMENTO"]]):
            continue
        if referencial and not _contido(referencial, r["REFERENCIAL"]):
            continue
        if status and r["STATUS_VERIFICACAO"] != status:
            continue
        achados.append(r)
    return sorted(achados, key=lambda r: (r["STATUS_VERIFICACAO"] != "VERIFICADO", r["ID"]))


def consultar_fundamento_dp_id(fundamento_id: str, *, exigir_verificado: bool = False,
                                base: Path = RAIZ) -> dict:
    registro = next((r for r in carregar_fundamentos_dp(base) if r["ID"] == fundamento_id), None)
    if registro is None:
        raise KeyError(f"fundamento DP inexistente: {fundamento_id}")
    if exigir_verificado and registro["STATUS_VERIFICACAO"] != "VERIFICADO":
        raise PermissionError(f"{fundamento_id} está {registro['STATUS_VERIFICACAO']}; requer revisão e evidência adicional")
    return registro


def consultar_casos_dp(*, caso_id: str | None = None, termo: str | None = None,
                        base: Path = RAIZ) -> list[dict]:
    dados = json.loads((base / "casos_dp.json").read_text(encoding="utf-8"))["CASOS"]
    ids = [c.get("ID") for c in dados]
    if len(ids) != len(set(ids)) or set(ids) != {f"DP-CASO-{i:02d}" for i in range(1, 16)}:
        raise ValueError("casos DP: esperado o conjunto único DP-CASO-01..15")
    saida = []
    for c in dados:
        if caso_id and normalizar(caso_id) != normalizar(c["ID"]):
            continue
        texto = " ".join(str(c.get(k, "")) for k in ("TITULO", "FATO", "TRATAMENTO_CONCEITUAL", "EXEMPLO_FICTICIO"))
        if termo and normalizar(termo) not in normalizar(texto):
            continue
        campos = ("FUNDAMENTO_IDS", "DOCUMENTACAO", "FONTES", "DISPOSITIVOS", "VIGENCIA",
                  "APLICABILIDADE", "TRATAMENTO_CONCEITUAL", "RISCOS", "LIMITACOES", "NECESSIDADE_REVISAO")
        if c.get("TIPO_CONHECIMENTO") != "EXEMPLO_ILUSTRATIVO" or c.get("AUTORIZA_DECISAO_AUTOMATICA") is not False:
            raise ValueError(f"{c.get('ID')}: caso DP não é ilustrativo/bloqueado")
        if any(not c.get(k) for k in campos) or not c["EXEMPLO_FICTICIO"].startswith("Exemplo fictício:"):
            raise ValueError(f"{c.get('ID')}: caso DP incompleto ou sem marcação fictícia")
        saida.append(c)
    return saida


def carregar_fundamentos_fiscais(base: Path = RAIZ) -> list[dict]:
    """Carrega as fichas fiscais 03E, mantendo regra geral separada da aplicação contextual."""
    dados = json.loads((base / "fundamentos_fiscais.json").read_text(encoding="utf-8"))["REGISTROS"]
    ids = [r.get("ID") for r in dados]
    if len(ids) != len(set(ids)) or set(ids) != {f"FISC-{i:02d}" for i in range(1, 26)}:
        raise ValueError("fundamentos fiscais: esperado o conjunto único FISC-01..FISC-25")
    obrigatorios = {"ID", "CONCEITO", "OBJETIVO", "FUNDAMENTO", "FONTES", "DISPOSITIVO", "VIGENCIA",
                    "APLICABILIDADE", "EVIDENCIAS_NECESSARIAS", "TRATAMENTO_CONCEITUAL", "EXCECOES",
                    "RISCOS", "ERROS_COMUNS", "LIMITACOES", "EXEMPLO_FICTICIO", "STATUS_VERIFICACAO",
                    "STATUS_APLICABILIDADE", "TIPO_CONHECIMENTO", "FUNDAMENTOS_CONTABEIS_RELACIONADOS",
                    "FUNDAMENTOS_FINANCEIROS_RELACIONADOS", "AUTORIZA_DECISAO_AUTOMATICA", "EVIDENCIA_CONSULTA"}
    for r in dados:
        faltantes = obrigatorios - r.keys()
        if faltantes:
            raise ValueError(f"{r.get('ID')}: ficha fiscal incompleta: {sorted(faltantes)}")
        if r["STATUS_VERIFICACAO"] not in STATUS or r["AUTORIZA_DECISAO_AUTOMATICA"] is not False:
            raise ValueError(f"{r['ID']}: status/autorização inválidos")
        if r["STATUS_APLICABILIDADE"] not in {"GERAL_LIMITADA", "DEPENDENTE_DE_CONTEXTO", "NAO_DETERMINADA"}:
            raise ValueError(f"{r['ID']}: status de aplicabilidade inválido")
        if not r["FONTES"] or not r["DISPOSITIVO"] or not r["EVIDENCIA_CONSULTA"]:
            raise ValueError(f"{r['ID']}: fonte, dispositivo ou evidência de consulta ausente")
        if any(not f.get("URL", "").startswith("https://") for f in r["FONTES"]):
            raise ValueError(f"{r['ID']}: fonte oficial inválida")
        if not r["EXEMPLO_FICTICIO"].lower().startswith("exemplo fictício:"):
            raise ValueError(f"{r['ID']}: exemplo não identificado como fictício")
        if r["TIPO_CONHECIMENTO"] == "PROCEDIMENTO_INTERNO" and not r.get("PROCEDIMENTO_INTERNO_RELACIONADO"):
            raise ValueError(f"{r['ID']}: procedimento interno sem vínculo identificado")
    return sorted(dados, key=lambda r: r["ID"])


def consultar_fundamentos_fiscais(*, assunto: str | None = None, regime: str | None = None,
                                   competencia: str | None = None, uf: str | None = None,
                                   municipio: str | None = None, atividade: str | None = None,
                                   tipo_operacao: str | None = None, status: str | None = None,
                                   base: Path = RAIZ) -> list[dict]:
    """Pesquisa fichas fiscais. Filtros contextualizam a busca, não determinam o tratamento."""
    if status and status not in STATUS:
        raise ValueError(f"status deve ser um de {sorted(STATUS)}")
    if competencia and not re.fullmatch(r"\d{4}-\d{2}", competencia):
        raise ValueError("competencia deve usar AAAA-MM")
    resultado = []
    for r in carregar_fundamentos_fiscais(base):
        if assunto and not _contido(assunto, [r["ID"], r["CONCEITO"], r["OBJETIVO"], r["FUNDAMENTO"]]):
            continue
        if regime and not _contido(regime, r["CONTEXTO_CONSULTA"]["REGIME_TRIBUTARIO"]):
            continue
        if competencia:
            vig = r["VIGENCIA"]
            if vig.get("INICIO") and competencia < vig["INICIO"][:7]:
                continue
            if vig.get("FIM") and competencia > vig["FIM"][:7]:
                continue
        # Jurisdição/operação localiza a ficha consultiva; sem regra contextual
        # cadastrada, não exclui o fundamento geral nem simula aplicabilidade.
        if status and r["STATUS_VERIFICACAO"] != status:
            continue
        copia = dict(r)
        copia["CONTEXTO_SOLICITADO"] = {"REGIME":regime,"COMPETENCIA":competencia,"UF":uf,"MUNICIPIO":municipio,"ATIVIDADE":atividade,"TIPO_OPERACAO":tipo_operacao}
        faltantes = []
        if competencia is None: faltantes.append("competência")
        if regime is None: faltantes.append("regime tributário")
        if uf is None: faltantes.append("UF")
        if municipio is None: faltantes.append("município")
        if atividade is None: faltantes.append("atividade")
        if tipo_operacao is None: faltantes.append("natureza da operação")
        copia["ALERTA_CONTEXTO_CONSULTA"] = ("Contexto não informado: " + ", ".join(faltantes) + ". A consulta não determina incidência, crédito, retenção, obrigação ou tratamento.") if faltantes else "Filtros de contexto informados não substituem validação documental, legal e supervisora."
        resultado.append(copia)
    return resultado


def consultar_fundamento_fiscal_id(fundamento_id: str, *, exigir_verificado: bool = False,
                                    base: Path = RAIZ) -> dict:
    registro = next((r for r in carregar_fundamentos_fiscais(base) if r["ID"] == fundamento_id), None)
    if registro is None:
        raise KeyError(f"fundamento fiscal inexistente: {fundamento_id}")
    if exigir_verificado and registro["STATUS_VERIFICACAO"] != "VERIFICADO":
        raise PermissionError(f"{fundamento_id} está {registro['STATUS_VERIFICACAO']}; requer revisão e evidência adicional")
    return registro


def consultar_casos_fiscais(*, caso_id: str | None = None, termo: str | None = None,
                             base: Path = RAIZ) -> list[dict]:
    dados = json.loads((base / "casos_fiscais.json").read_text(encoding="utf-8"))["CASOS"]
    ids = [c.get("ID") for c in dados]
    if len(ids) != len(set(ids)) or set(ids) != {f"FISC-CASO-{i:02d}" for i in range(1, 21)}:
        raise ValueError("casos fiscais: esperado o conjunto único FISC-CASO-01..20")
    saida = []
    for caso in dados:
        if caso_id and normalizar(caso_id) != normalizar(caso["ID"]):
            continue
        texto = " ".join(str(caso.get(k, "")) for k in ("TITULO", "FATO", "TRATAMENTO_CONCEITUAL", "EXEMPLO_FICTICIO"))
        if termo and normalizar(termo) not in normalizar(texto):
            continue
        obrigatorios = ("FUNDAMENTO_IDS", "EVIDENCIA_NECESSARIA", "DEPARTAMENTO_RESPONSAVEL", "LIMITACOES",
                        "NECESSIDADE_APROVACAO", "FONTES", "DISPOSITIVOS", "VIGENCIA", "APLICABILIDADE")
        if caso.get("TIPO_CONHECIMENTO") != "EXEMPLO_ILUSTRATIVO" or caso.get("AUTORIZA_DECISAO_AUTOMATICA") is not False:
            raise ValueError(f"{caso.get('ID')}: caso deve ser ilustrativo e não automático")
        if any(not caso.get(k) for k in obrigatorios) or not caso["EXEMPLO_FICTICIO"].lower().startswith("exemplo fictício:"):
            raise ValueError(f"{caso.get('ID')}: caso incompleto ou sem exemplo fictício")
        saida.append(caso)
    return saida


def consultar_respostas(*, pergunta_id: str | None = None, termo: str | None = None,
                        base: Path = RAIZ) -> list[dict]:
    """Consulta respostas fundamentadas às dez questões de demonstração, sem decidir operações."""
    dados = json.loads((base / "respostas_demonstrativas.json").read_text(encoding="utf-8"))["RESPOSTAS"]
    saida = []
    for r in dados:
        if pergunta_id and normalizar(pergunta_id) != normalizar(r["ID"]):
            continue
        alvo = " ".join(str(r.get(c, "")) for c in ("PERGUNTA", "FUNDAMENTO", "DISPOSITIVOS"))
        if termo and normalizar(termo) not in normalizar(alvo):
            continue
        if r.get("AUTORIZA_DECISAO_AUTOMATICA") is not False or not r.get("FONTES") or not r.get("DISPOSITIVOS"):
            raise ValueError(f"{r.get('ID', '<sem ID>')}: resposta sem fonte/dispositivo ou com autorização automática")
        saida.append(r)
    return saida


def consultar_casos_contabeis(*, caso_id: str | None = None, termo: str | None = None,
                               base: Path = RAIZ) -> list[dict]:
    """Pesquisa casos fictícios explicativos; a resposta é sempre conceitual e não lança."""
    dados = json.loads((base / "casos_contabeis.json").read_text(encoding="utf-8"))["CASOS"]
    saida = []
    for caso in dados:
        if caso_id and normalizar(caso_id) != normalizar(caso["ID"]):
            continue
        texto = " ".join(str(caso.get(k, "")) for k in ("TITULO", "FUNDAMENTO", "TRATAMENTO_CONCEITUAL", "EXEMPLO_FICTICIO"))
        if termo and normalizar(termo) not in normalizar(texto):
            continue
        if caso.get("TIPO_CONHECIMENTO") != "EXEMPLO_ILUSTRATIVO" or caso.get("AUTORIZA_DECISAO_AUTOMATICA") is not False:
            raise ValueError(f"{caso.get('ID')}: caso deve ser fictício e não automático")
        if not all(caso.get(k) for k in ("FONTES", "DISPOSITIVOS", "EVIDENCIA_NECESSARIA", "REFERENCIAL", "LIMITACOES", "NECESSIDADE_APROVACAO")):
            raise ValueError(f"{caso.get('ID')}: caso sem metadados de consulta/revisão")
        saida.append(caso)
    return saida


def resumo_prioridades(base: Path = RAIZ) -> dict[str, dict[str, int]]:
    """Resume cobertura sem ocultar pendências nem inferir aprovação da etapa."""
    from collections import Counter
    dados = json.loads((base / "cobertura.json").read_text(encoding="utf-8"))["ITENS"]
    resumo = {}
    for prioridade in ("P0", "P1", "P2"):
        contagem = Counter(i["STATUS"] for i in dados if i.get("PRIORIDADE") == prioridade)
        resumo[prioridade] = {s: contagem[s] for s in sorted(STATUS)}
        resumo[prioridade]["TOTAL"] = sum(contagem.values())
    return resumo


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--departamento")
    parser.add_argument("--atividade", help="filtra contexto da ficha fiscal por atividade")
    parser.add_argument("--assunto")
    parser.add_argument("--referencial")
    parser.add_argument("--competencia")
    parser.add_argument("--operacao")
    parser.add_argument("--regime")
    parser.add_argument("--uf")
    parser.add_argument("--municipio")
    parser.add_argument("--empresa")
    parser.add_argument("--status")
    parser.add_argument("--somente-verificados", action="store_true")
    parser.add_argument("--cobertura", action="store_true", help="pesquisa o inventário de assuntos e lacunas")
    parser.add_argument("--resumo-prioridades", action="store_true", help="resume estados por P0/P1/P2")
    parser.add_argument("--prioridade", choices=("P0", "P1", "P2"), help="filtra o inventário por prioridade")
    parser.add_argument("--fundamento", help="consulta fichas técnicas P0 pelo conceito")
    parser.add_argument("--resposta", help="consulta uma resposta demonstrativa pelo ID, Q01–Q10")
    parser.add_argument("--fundamento-id", help="consulta um fundamento contábil 03C, CONT-01–CONT-20")
    parser.add_argument("--fundamento-verificado", help="consulta fundamento bloqueando status abaixo de VERIFICADO")
    parser.add_argument("--caso", help="consulta um caso fictício, CASO-01–CASO-12")
    parser.add_argument("--fundamento-financeiro", help="consulta FIN-01–FIN-20 por assunto")
    parser.add_argument("--fundamento-financeiro-id", help="consulta ficha financeira por ID")
    parser.add_argument("--caso-financeiro", help="consulta caso financeiro fictício, FIN-CASO-01–15")
    parser.add_argument("--fundamento-fiscal", help="consulta FISC-01–FISC-25 por assunto")
    parser.add_argument("--fundamento-fiscal-id", help="consulta ficha fiscal por ID")
    parser.add_argument("--caso-fiscal", help="consulta caso fiscal fictício, FISC-CASO-01–20")
    parser.add_argument("--fundamento-dp", help="consulta DP-01–DP-20 por assunto")
    parser.add_argument("--fundamento-dp-id", help="consulta fundamento DP por ID")
    parser.add_argument("--caso-dp", help="consulta caso DP fictício, DP-CASO-01–15")
    args = parser.parse_args()
    if args.resumo_prioridades:
        print(json.dumps(resumo_prioridades(), ensure_ascii=False, indent=2))
        raise SystemExit(0)
    if args.cobertura:
        achados = consultar_cobertura(departamento=args.departamento, assunto=args.assunto,
                                     status=args.status, prioridade=args.prioridade)
    elif args.fundamento:
        achados = consultar_fundamentos(assunto=args.fundamento, referencial=args.referencial, status=args.status)
    elif args.resposta:
        achados = consultar_respostas(pergunta_id=args.resposta)
    elif args.fundamento_id:
        achados = [consultar_fundamento_id(args.fundamento_id)]
    elif args.fundamento_verificado:
        achados = [consultar_fundamento_verificado(args.fundamento_verificado)]
    elif args.caso:
        achados = consultar_casos_contabeis(caso_id=args.caso)
    elif args.fundamento_financeiro:
        achados = consultar_fundamentos_financeiros(assunto=args.fundamento_financeiro,
                                                    referencial=args.referencial, status=args.status,
                                                    competencia=args.competencia)
    elif args.fundamento_financeiro_id:
        achados = [consultar_fundamento_financeiro_id(args.fundamento_financeiro_id)]
    elif args.caso_financeiro:
        achados = consultar_casos_financeiros(caso_id=args.caso_financeiro)
    elif args.fundamento_fiscal:
        achados = consultar_fundamentos_fiscais(assunto=args.fundamento_fiscal, regime=args.regime,
                                                competencia=args.competencia, uf=args.uf, municipio=args.municipio,
                                                atividade=args.atividade, tipo_operacao=args.operacao, status=args.status)
    elif args.fundamento_fiscal_id:
        achados = [consultar_fundamento_fiscal_id(args.fundamento_fiscal_id)]
    elif args.caso_fiscal:
        achados = consultar_casos_fiscais(caso_id=args.caso_fiscal)
    elif args.fundamento_dp:
        achados = consultar_fundamentos_dp(assunto=args.fundamento_dp, referencial=args.referencial,
                                           competencia=args.competencia, status=args.status)
    elif args.fundamento_dp_id:
        achados = [consultar_fundamento_dp_id(args.fundamento_dp_id)]
    elif args.caso_dp:
        achados = consultar_casos_dp(caso_id=args.caso_dp)
    else:
        achados = consultar(departamento=args.departamento, assunto=args.assunto,
                            referencial_contabil=args.referencial, competencia=args.competencia,
                            tipo_operacao=args.operacao, regime_tributario=args.regime,
                            uf=args.uf, municipio=args.municipio, empresa_id=args.empresa,
                            status=args.status, incluir_pendentes=not args.somente_verificados)
    print(json.dumps(achados, ensure_ascii=False, indent=2))
