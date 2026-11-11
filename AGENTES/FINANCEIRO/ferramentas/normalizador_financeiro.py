"""Normalizador Financeiro - transforma documentos JÁ EXTRAÍDOS em um contrato financeiro comum.

Desenho:  Documento extraído → Normalizador Financeiro → Contrato Financeiro Comum → Financeiro → Conciliação → Contabilidade

- Código local, determinístico, SEM modelo de linguagem, sem acesso a arquivos, rede ou sistemas externos: recebe o
  dicionário de um arquivo como devolvido pelo extrator do Agente de Documentos e devolve um dicionário novo. A entrada
  nunca é alterada.
- Cada fonte (planilha financeira, extrato de um banco, relatório de um sistema) tem um ADAPTADOR registrado em
  ADAPTADORES. Todos devolvem o mesmo contrato; o Financeiro não precisa conhecer o leiaute de origem.
- Nesta versão existe um adaptador: PLANILHA_FINANCEIRA_GENERICA (RELATORIO_FINANCEIRO + EXTRAIDO_PLANILHA).
  Extrato bancário ainda NÃO tem adaptador aqui (aguarda o extrato correto); CAMPOS_MOVIMENTO_BANCARIO só reserva o contrato.
- Reconhecimento pelo CONTEÚDO (cabeçalhos, tipos das células, estrutura). O nome do arquivo nunca decide.
- Moeda sempre em Decimal (nunca float nas contas). Campo ausente na origem fica None e é listado em campos_ausentes:
  nada é inventado. Linha duvidosa vira pendência (Problema / Impacto / O que fazer), nunca movimento.
- O contrato representa movimentos financeiros REALIZADOS. Linha com situação explícita de não realizada (em aberto,
  cancelada) ou situação não reconhecida fica preservada em linhas_nao_realizadas, nunca em movimentos.
- Relatório financeiro é fonte AUXILIAR: não é extrato bancário e não comprova movimentação na conta.

v1.2: célula de situação VAZIA (coluna existente) = AUSENTE / SITUACAO_AUSENTE, distinta de texto não reconhecido
      (INDETERMINADO / SITUACAO_NAO_RECONHECIDA); nenhuma das duas entra como REALIZADO.
v1.1: data_competencia, situacao e contraparte (estruturada) no contrato; "É Despesa" e "Valor Pago" como validação
      cruzada (divergência = pendência, nada é corrigido em silêncio); linhas_nao_realizadas.

Uso:
    from normalizador_financeiro import normalizar, para_json
    resultado = normalizar(arquivo_extraido)          # valores em Decimal
    json.dumps(para_json(resultado))                  # valores como texto "1234.56"
"""

import datetime as dt
import hashlib
import re
import unicodedata
from decimal import Decimal, InvalidOperation

VERSAO = "1.2"
CONTRATO = "MOVIMENTOS_FINANCEIROS_NORMALIZADOS_V1"
CENTAVO = Decimal("0.01")

# Contrato comum do movimento de RELATÓRIO FINANCEIRO (um dicionário por linha útil da planilha).
# v1.1 acrescenta campos NO FINAL (data_competencia, situacao, contraparte): consumidores da v1.0 continuam válidos.
CAMPOS_MOVIMENTO_RELATORIO = ("id", "data", "data_vencimento", "data_quitacao", "descricao", "valor", "natureza",
                              "plano_contas", "banco", "empresa", "documento", "codigo", "indice_linha", "origem",
                              "sha", "evidencias", "data_competencia", "situacao", "contraparte")
NATUREZAS_RELATORIO = ("ENTRADA", "SAIDA", "INDETERMINADA")
SITUACOES = ("REALIZADO", "EM_ABERTO", "CANCELADO", "INDETERMINADO", "AUSENTE")
# Contrato reservado para o movimento BANCÁRIO (adaptadores de extrato virão depois; nenhum é implementado aqui).
CAMPOS_MOVIMENTO_BANCARIO = ("data", "descricao", "documento", "valor", "natureza", "banco", "agencia", "conta",
                             "origem_documento", "sha256_origem", "indice_origem", "evidencias")
NATUREZAS_BANCARIAS = ("CREDITO", "DEBITO")

INFORMATIVO, ATENCAO, BLOQUEIO = "INFORMATIVO", "ATENCAO", "BLOQUEIO"

# Cabeçalhos aceitos por campo (já normalizados: sem acento, maiúsculas, só letras/números separados por espaço).
# Comparação EXATA com a lista; nunca por trecho do texto.
SINONIMOS = {
    "codigo": ("CODIGO", "COD", "ID", "CODIGO DO LANCAMENTO", "CODIGO LANCAMENTO"),
    "data": ("DATA", "DATA LANCAMENTO", "DATA DO LANCAMENTO", "DATA MOVIMENTO", "DATA DO MOVIMENTO"),
    "data_vencimento": ("DATA DE VENCIMENTO", "DATA VENCIMENTO", "DATA DO VENCIMENTO", "VENCIMENTO", "DT VENCIMENTO", "VENCTO"),
    "data_quitacao": ("DATA DE QUITACAO", "DATA QUITACAO", "DATA DA QUITACAO", "QUITACAO", "DATA DE PAGAMENTO",
                      "DATA PAGAMENTO", "DATA DO PAGAMENTO", "DATA DA BAIXA", "DATA DE BAIXA", "DATA BAIXA",
                      "DATA DE LIQUIDACAO", "DATA LIQUIDACAO", "DATA DA LIQUIDACAO", "PAGO EM"),
    "data_competencia": ("DATA DE COMPETENCIA", "DATA COMPETENCIA", "DATA DA COMPETENCIA", "COMPETENCIA", "MES DE COMPETENCIA"),
    "descricao": ("DESCRICAO", "BREVE DESCRICAO", "HISTORICO", "DESCRICAO DO LANCAMENTO"),
    "valor_entrada": ("VALOR ENTRADA", "VALOR DE ENTRADA", "VALOR DA ENTRADA", "ENTRADA", "ENTRADAS", "VALOR RECEBIDO",
                      "RECEBIMENTO", "RECEBIMENTOS", "VALOR CREDITO", "CREDITO"),
    "valor_saida": ("VALOR SAIDA", "VALOR DE SAIDA", "VALOR DA SAIDA", "SAIDA", "SAIDAS", "PAGAMENTO", "PAGAMENTOS",
                    "VALOR DEBITO", "DEBITO"),
    # Coluna única de valor: sozinha não diz se é entrada ou saída.
    "valor": ("VALOR", "VALOR LIQUIDO", "VALOR TOTAL", "VALOR DO LANCAMENTO", "VALOR R"),
    # Valor efetivamente pago/recebido: valor principal só sem as colunas acima; com elas, é validação cruzada.
    "valor_pago": ("VALOR PAGO", "VALOR QUITADO", "VALOR LIQUIDADO", "VALOR BAIXADO"),
    "tipo": ("TIPO", "NATUREZA", "TIPO DE LANCAMENTO", "TIPO LANCAMENTO", "TIPO DO LANCAMENTO", "OPERACAO", "ENTRADA SAIDA"),
    "e_despesa": ("E DESPESA", "EH DESPESA", "E UMA DESPESA"),
    "situacao": ("SITUACAO", "STATUS", "SITUACAO DO LANCAMENTO", "STATUS DO LANCAMENTO", "SITUACAO DO PAGAMENTO", "STATUS DO PAGAMENTO"),
    "plano_contas": ("PLANO DE CONTAS", "PLANO CONTAS", "CATEGORIA", "CLASSIFICACAO"),
    "banco": ("BANCO", "CONTA BANCARIA", "CONTA CORRENTE", "BANCO CONTA"),
    "empresa": ("EMPRESA", "EMPRESA CNPJ", "CNPJ EMPRESA", "CNPJ DA EMPRESA", "FILIAL"),
    "documento": ("DOCUMENTO", "N DOCUMENTO", "NO DOCUMENTO", "NUMERO DOCUMENTO", "NUMERO DO DOCUMENTO", "NUM DOCUMENTO",
                  "NRO DOCUMENTO", "DOC", "NOTA FISCAL", "NF"),
    # Contraparte (cliente/fornecedor/favorecido). Nunca obrigatória; nunca a empresa da própria planilha ("Empresa.*").
    "contraparte_nome": ("CLIENTE RAZAO SOCIAL", "FORNECEDOR RAZAO SOCIAL", "CLIENTE FORNECEDOR RAZAO SOCIAL", "RAZAO SOCIAL",
                         "CONTRAPARTE", "FAVORECIDO", "CLIENTE", "FORNECEDOR", "CLIENTE FORNECEDOR", "CLIENTE NOME",
                         "FORNECEDOR NOME", "NOME DO CLIENTE", "NOME DO FORNECEDOR", "NOME DO FAVORECIDO"),
    "contraparte_nome_fantasia": ("CLIENTE NOME FANTASIA", "FORNECEDOR NOME FANTASIA", "CLIENTE FORNECEDOR NOME FANTASIA", "NOME FANTASIA"),
    "contraparte_documento": ("CLIENTE CPF CNPJ", "FORNECEDOR CPF CNPJ", "CLIENTE FORNECEDOR CPF CNPJ", "CLIENTE CNPJ", "CLIENTE CPF",
                              "FORNECEDOR CNPJ", "FORNECEDOR CPF", "CPF CNPJ", "CNPJ CPF", "CPF CNPJ DO CLIENTE",
                              "CPF CNPJ DO FORNECEDOR", "CNPJ DO FAVORECIDO", "CPF CNPJ DO FAVORECIDO"),
}
CAMPO_POR_CABECALHO = {s: campo for campo, lista in SINONIMOS.items() for s in lista}
CAMPOS_DATA = ("data", "data_vencimento", "data_quitacao")
CAMPOS_DATA_TODOS = CAMPOS_DATA + ("data_competencia",)
CAMPOS_VALOR = ("valor_entrada", "valor_saida", "valor", "valor_pago")
CAMPOS_TEXTO = ("descricao", "plano_contas", "banco", "empresa", "documento", "codigo")
CONTRAPARTE = {"contraparte_nome": "nome", "contraparte_nome_fantasia": "nome_fantasia", "contraparte_documento": "documento"}
# Campos do contrato v1.0 que dependem de uma coluna da planilha (para informar o que NÃO existe na origem).
CAMPOS_DA_ORIGEM = CAMPOS_DATA + CAMPOS_TEXTO
# Campos complementares da v1.1 (opcionais; listados à parte para não mudar o significado de campos_ausentes).
CAMPOS_COMPLEMENTARES = ("data_competencia", "situacao", "contraparte", "e_despesa", "valor_pago")

TIPOS_ENTRADA = {"ENTRADA", "ENTRADAS", "RECEBIMENTO", "RECEITA", "CREDITO", "RECEBER", "A RECEBER", "E"}
TIPOS_SAIDA = {"SAIDA", "SAIDAS", "PAGAMENTO", "DESPESA", "DEBITO", "PAGAR", "A PAGAR", "S"}
# Situação: somente valores EXATOS (normalizados) cobertos por teste. Qualquer outro = INDETERMINADO (conservador).
SITUACAO_POR_TEXTO = {
    **{t: "REALIZADO" for t in ("FOI PAGO", "FOI RECEBIDO", "PAGO", "PAGA", "RECEBIDO", "RECEBIDA", "QUITADO", "QUITADA",
                                "LIQUIDADO", "LIQUIDADA", "BAIXADO", "BAIXADA", "REALIZADO", "REALIZADA")},
    **{t: "EM_ABERTO" for t in ("EM ABERTO", "ABERTO", "ABERTA", "PENDENTE", "NAO PAGO", "NAO PAGA", "NAO RECEBIDO",
                                "NAO RECEBIDA", "A PAGAR", "A RECEBER", "A VENCER", "VENCIDO", "VENCIDA", "EM ATRASO", "ATRASADO")},
    **{t: "CANCELADO" for t in ("CANCELADO", "CANCELADA", "CANCELAMENTO")},
}
SIM_NAO = {"SIM": True, "S": True, "VERDADEIRO": True, "TRUE": True, "NAO": False, "N": False, "FALSO": False, "FALSE": False}
RE_TOTALIZADOR = re.compile(r"^(SUB ?TOTAL|TOTAL|TOTAIS|SALDO|SOMA|RESUMO)\b")
LINHAS_BUSCA_CABECALHO = 15
# Datas gravadas como número de série do Excel (comum na leitura alternativa): só inteiros entre 2000 e 2099.
SERIAL_MIN, SERIAL_MAX = 36526, 73050
EPOCA_EXCEL_1900 = dt.date(1899, 12, 30)


# ---------------------------------------------------------------- conversões seguras

def chave(texto) -> str:
    """Cabeçalho normalizado: 'Nº Documento' → 'NO DOCUMENTO'; 'Empresa.CNPJ' → 'EMPRESA CNPJ'."""
    t = unicodedata.normalize("NFKD", str(texto if texto is not None else "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", t).strip()


def chave_estrita(texto) -> str:
    """Valor de célula para comparação exata: sem acento, maiúsculas, espaços simples; pontuação PRESERVADA ('Pago?' ≠ 'PAGO')."""
    t = unicodedata.normalize("NFKD", str(texto if texto is not None else "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip()


def vazio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def texto(v):
    """Texto da célula sem inventar formato: 123.0 → '123'; vazio → None."""
    if vazio(v) or isinstance(v, bool):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def decimal_seguro(v):
    """(Decimal em centavos | None, erro | None). Nunca faz conta em float e nunca arredonda em silêncio.

    Aceita: int; float (convertido pelo texto exato do número); '1.234,56'; '1234,56'; '1234.56'; 'R$ 1.234,56'; sinal.
    Recusa: texto não numérico; '1.234' (milhar ou decimal? ambíguo); mais de duas casas decimais significativas.
    """
    if vazio(v):
        return None, None
    if isinstance(v, bool):
        return None, "valor lógico (verdadeiro/falso) no lugar de um número"
    if isinstance(v, Decimal):
        d = v
    elif isinstance(v, int):
        d = Decimal(v)
    elif isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return None, "número inválido"
        d = Decimal(repr(v))
    else:
        t = str(v).strip().replace("R$", "").replace(" ", "").replace(" ", "")
        negativo = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
        t = t.strip("()").lstrip("+-")
        if re.fullmatch(r"(\d{1,3}(\.\d{3})+|\d+),\d{1,2}", t):
            t = t.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            return None, f"'{v}' pode ser milhar ou decimal; formato ambíguo"
        elif not re.fullmatch(r"\d+(\.\d+)?", t):
            return None, f"'{v}' não é um valor monetário reconhecido"
        try:
            d = Decimal(t)
        except InvalidOperation:
            return None, f"'{v}' não é um valor monetário reconhecido"
        if negativo:
            d = -d
    q = d.quantize(CENTAVO)
    if abs(d - q) > Decimal("0.000001"):
        return None, f"'{v}' tem mais de duas casas decimais; não foi arredondado"
    return q, None


def data_segura(v):
    """(AAAA-MM-DD | None, erro | None, evidência | None). Só datas reais do calendário."""
    if vazio(v):
        return None, None, None
    if isinstance(v, bool):
        return None, "valor lógico no lugar de uma data", None
    if isinstance(v, (int, float)):
        if float(v).is_integer() and SERIAL_MIN <= int(v) <= SERIAL_MAX:
            return (EPOCA_EXCEL_1900 + dt.timedelta(days=int(v))).isoformat(), None, "DATA_SERIAL_EXCEL"
        return None, f"número {v} não é uma data reconhecida", None
    t = str(v).strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?", t)
    partes = (m.group(1), m.group(2), m.group(3)) if m else None
    if not partes:
        m = re.fullmatch(r"(\d{2})[/.-](\d{2})[/.-](\d{4})", t)
        partes = (m.group(3), m.group(2), m.group(1)) if m else None
    if not partes:
        return None, f"'{v}' não é uma data reconhecida", None
    try:
        return dt.date(*map(int, partes)).isoformat(), None, None
    except ValueError:
        return None, f"'{v}' não existe no calendário", None


def competencia_segura(v):
    """Data de competência: data completa (AAAA-MM-DD) ou mês explícito (MM/AAAA, AAAA-MM → 'AAAA-MM')."""
    if isinstance(v, str):
        t = v.strip()
        m = re.fullmatch(r"(\d{2})[/-](\d{4})", t) or re.fullmatch(r"(\d{4})-(\d{2})", t)
        if m:
            ano, mes = (m.group(2), m.group(1)) if len(m.group(1)) == 2 else (m.group(1), m.group(2))
            if 1 <= int(mes) <= 12:
                return f"{ano}-{mes}", None, "COMPETENCIA_MENSAL"
            return None, f"'{v}' não é um mês válido", None
    return data_segura(v)


def pendencia(nivel, codigo, problema, impacto, o_que_fazer, **extra) -> dict:
    return {"nivel": nivel, "codigo": codigo, "problema": problema, "impacto": impacto, "o_que_fazer": o_que_fazer, **extra}


def mascarar_documento(doc):
    """CPF/CNPJ para exibição: só os 2 primeiros e os 2 últimos dígitos ('12.***.***/****-34'). None se vazio."""
    d = re.sub(r"\D", "", str(doc or ""))
    if not d:
        return None
    return f"{d[:2]}{'*' * max(len(d) - 4, 0)}{d[-2:]}" if len(d) > 4 else "*" * len(d)


# ---------------------------------------------------------------- adaptador: planilha financeira genérica

def mapear_cabecalho(valores: list):
    """Mapeia as células de uma linha para campos do contrato. Devolve (mapa, repetidos, nao_mapeadas) ou None."""
    mapa, repetidos, sobras = {}, {}, []
    for i, celula in enumerate(valores):
        if not isinstance(celula, str) or not celula.strip():
            continue
        campo = CAMPO_POR_CABECALHO.get(chave(celula))
        if campo is None:
            sobras.append(celula.strip())
        elif campo in mapa:
            repetidos.setdefault(campo, [mapa[campo]["cabecalho"]]).append(celula.strip())
        else:
            mapa[campo] = {"coluna": i, "cabecalho": celula.strip()}
    tem_valor = any(c in mapa for c in CAMPOS_VALOR)
    tem_data = any(c in mapa for c in CAMPOS_DATA_TODOS)
    if not (tem_valor and tem_data and len(mapa) >= 3):
        return None
    return mapa, repetidos, sobras


def localizar_cabecalho(linhas: list):
    for posicao, linha in enumerate(linhas[:LINHAS_BUSCA_CABECALHO]):
        achado = mapear_cabecalho(linha.get("valores") or [])
        if achado:
            return posicao, achado
    return None, None


def reconhece_planilha_financeira(arquivo: dict) -> bool:
    """Reconhecimento pelo conteúdo: planilha extraída com uma aba visível que tenha cabeçalho financeiro."""
    if arquivo.get("leitura") != "EXTRAIDO_PLANILHA":
        return False
    abas = (arquivo.get("conteudo") or {}).get("abas") or []
    return any(not aba.get("oculta") and localizar_cabecalho(aba.get("linhas") or [])[0] is not None for aba in abas)


def _natureza_por_tipo(celula):
    t = chave(celula)
    return "ENTRADA" if t in TIPOS_ENTRADA else "SAIDA" if t in TIPOS_SAIDA else None


def _normalizar_aba(aba: dict, posicao: int, mapa: dict, nome: str, sha, pendencias: list, ignoradas: list,
                    nao_realizadas: list) -> list:
    linhas = aba.get("linhas") or []
    nome_aba = aba.get("aba")
    movimentos = []

    def celula(valores, campo):
        info = mapa.get(campo)
        return valores[info["coluna"]] if info and info["coluna"] < len(valores) else None

    def cab(campo):
        return mapa[campo]["cabecalho"]

    for linha in linhas[posicao + 1:]:
        valores, n = linha.get("valores") or [], linha.get("linha")
        onde = f"{nome_aba} · linha {n}"
        ref = {"aba": nome_aba, "indice_linha": n}
        if all(vazio(celula(valores, c)) for c in mapa):
            ignoradas.append({**ref, "motivo": "LINHA_VAZIA"})
            continue
        # ---- datas e valores: tudo é lido antes de decidir; uma célula inválida impede o uso da linha inteira
        datas, erros, evidencias = {}, [], ["CABECALHO_ESTRUTURADO"]
        for campo in CAMPOS_DATA_TODOS:
            if campo in mapa:
                ler = competencia_segura if campo == "data_competencia" else data_segura
                datas[campo], erro, evid = ler(celula(valores, campo))
                if erro:
                    erros.append(("DATA_INVALIDA", f"{cab(campo)}: {erro}"))
                if evid and evid not in evidencias:
                    evidencias.append(evid)
        quantias = {}
        for campo in CAMPOS_VALOR:
            if campo in mapa:
                quantias[campo], erro = decimal_seguro(celula(valores, campo))
                if erro:
                    erros.append(("VALOR_INVALIDO", f"{cab(campo)}: {erro}"))
        tem_data = any(datas.values())
        descricao = texto(celula(valores, "descricao"))
        primeiro_texto = next((str(v) for v in valores if isinstance(v, str) and v.strip()), "")
        if not tem_data and not any(c == "DATA_INVALIDA" for c, _ in erros):
            # Sem nenhuma data: título, observação, subtotal ou total. Fica registrada, nunca vira movimento.
            motivo = "LINHA_TOTALIZADORA" if RE_TOTALIZADOR.match(chave(descricao or primeiro_texto)) else "LINHA_INFORMATIVA"
            ignoradas.append({**ref, "motivo": motivo, "texto": descricao or primeiro_texto or None})
            continue
        contraparte = {destino: texto(celula(valores, campo)) for campo, destino in CONTRAPARTE.items()
                       if campo in mapa and texto(celula(valores, campo))} or None
        # ---- situação: o contrato só recebe movimentos REALIZADOS
        situacao = None
        if "situacao" in mapa:
            bruto = texto(celula(valores, "situacao"))
            situacao = SITUACAO_POR_TEXTO.get(chave_estrita(bruto), "INDETERMINADO") if bruto else "AUSENTE"
            if situacao != "REALIZADO":
                entrada, saida = quantias.get("valor_entrada") or None, quantias.get("valor_saida") or None
                nao_realizadas.append({
                    **ref, "situacao": situacao, "situacao_origem": bruto,
                    "motivo": {"EM_ABERTO": "Lançamento em aberto: ainda não pago/recebido.",
                               "CANCELADO": "Lançamento cancelado na origem.",
                               "INDETERMINADO": "Situação não reconhecida; não presumida como realizada.",
                               "AUSENTE": "Situação financeira não informada; não presumida como realizada."}[situacao],
                    "evidencia": f"coluna '{cab('situacao')}' = '{bruto or ''}'",
                    "valor": (entrada if entrada is not None and saida is None else saida if saida is not None and entrada is None
                              else quantias.get("valor") or quantias.get("valor_pago")),
                    "natureza": "ENTRADA" if entrada is not None and saida is None else "SAIDA" if saida is not None and entrada is None else None,
                    "data_vencimento": datas.get("data_vencimento"), "data_quitacao": datas.get("data_quitacao"),
                    "data_competencia": datas.get("data_competencia"), "descricao": descricao, "documento": texto(celula(valores, "documento")),
                    "codigo": texto(celula(valores, "codigo")), "contraparte": contraparte,
                    "origem": {"arquivo": nome, "aba": nome_aba, "linha": n}, "sha": sha})
                if situacao == "INDETERMINADO":
                    pendencias.append(pendencia(
                        ATENCAO, "SITUACAO_NAO_RECONHECIDA",
                        f"{onde}: situação '{bruto or 'vazia'}' não é reconhecida como paga/recebida, em aberto ou cancelada.",
                        "A linha não entrou nos movimentos realizados; ficou preservada em 'não realizadas'.",
                        "Confirmar na origem se o lançamento foi pago/recebido e reenviar, ou tratar a linha manualmente.", **ref))
                elif situacao == "AUSENTE":
                    pendencias.append(pendencia(
                        ATENCAO, "SITUACAO_AUSENTE", f"{onde}: situação financeira não informada.",
                        "Não é possível confirmar apenas por esse campo que o lançamento foi realizado; a linha ficou "
                        "preservada em 'não realizadas'.",
                        "Validar a situação ou utilizar outra evidência estruturada aprovada pelo processo.", **ref))
                continue
            evidencias.append("SITUACAO_REALIZADO")
        if erros:
            for codigo, detalhe in erros:
                pendencias.append(pendencia(
                    ATENCAO, codigo, f"{onde}: {detalhe}.",
                    "A linha não entrou nos movimentos normalizados; nada foi corrigido ou presumido.",
                    "Conferir a célula na planilha de origem e reenviar o arquivo corrigido, ou tratar a linha manualmente.", **ref))
            continue
        entrada, saida = quantias.get("valor_entrada"), quantias.get("valor_saida")
        entrada = entrada if entrada else None            # 0,00 numa coluna de entrada/saída = coluna sem valor
        saida = saida if saida else None
        if entrada is not None and saida is not None:
            pendencias.append(pendencia(
                ATENCAO, "ENTRADA_E_SAIDA_SIMULTANEAS", f"{onde}: a linha tem valor de entrada ({entrada}) e de saída ({saida}) ao mesmo tempo.",
                "A linha não entrou nos movimentos; o sistema não escolhe um dos lados nem calcula a diferença.",
                "Confirmar na origem se é entrada ou saída (ou dois lançamentos) e reenviar a planilha ajustada.", **ref))
            continue
        lado = entrada if entrada is not None else saida
        if lado is not None and lado < 0:
            pendencias.append(pendencia(
                ATENCAO, "VALOR_NEGATIVO", f"{onde}: valor negativo ({lado}) em coluna de {'entrada' if entrada is not None else 'saída'}.",
                "A linha não entrou nos movimentos; pode ser estorno, mas isso não foi presumido.",
                "Confirmar na origem o significado do valor negativo.", **ref))
            continue
        # ---- valor principal: entrada/saída > coluna única de valor > valor pago
        unico_campo = next((c for c in ("valor", "valor_pago") if quantias.get(c)), None)
        if lado is not None:
            valor, natureza, principal = lado, "ENTRADA" if entrada is not None else "SAIDA", "lado"
            evidencias.append("COLUNA_VALOR_ENTRADA" if entrada is not None else "COLUNA_VALOR_SAIDA")
        elif unico_campo:
            unico = quantias[unico_campo]
            valor, natureza, principal = abs(unico), _natureza_por_tipo(celula(valores, "tipo")) if "tipo" in mapa else None, unico_campo
            evidencias.append("COLUNA_VALOR_UNICA" if unico_campo == "valor" else "COLUNA_VALOR_PAGO")
            if natureza:
                evidencias.append("NATUREZA_PELA_COLUNA_TIPO")
            else:
                natureza = "INDETERMINADA"
            if unico < 0:
                evidencias.append("SINAL_NEGATIVO_NA_ORIGEM")
        else:
            pendencias.append(pendencia(
                ATENCAO, "LINHA_SEM_VALOR", f"{onde}: a linha tem data, mas nenhum valor preenchido.",
                "A linha não entrou nos movimentos; nenhum valor foi presumido.",
                "Conferir na origem se o lançamento tem valor e reenviar, ou desconsiderar a linha.", **ref))
            continue
        # ---- validação cruzada: Valor Pago (nunca substitui o valor principal)
        if "valor_pago" in mapa and principal != "valor_pago" and quantias.get("valor_pago") is not None:
            pago = abs(quantias["valor_pago"])
            if pago != valor:
                pendencias.append(pendencia(
                    ATENCAO, "DIVERGENCIA_VALOR_PAGO",
                    f"{onde}: o valor do lançamento ({valor}) é diferente de '{cab('valor_pago')}' ({pago}).",
                    "A linha não entrou nos movimentos; nenhum dos dois valores foi escolhido ou corrigido.",
                    "Conferir na origem qual valor está correto (juros, desconto, pagamento parcial?) e reenviar.",
                    valor_movimento=valor, valor_pago=pago, **ref))
                continue
            evidencias.append("VALOR_PAGO_CONSISTENTE")
        # ---- validação cruzada: "É Despesa" (só define a natureza quando nenhuma outra coluna a define)
        if "e_despesa" in mapa and not vazio(celula(valores, "e_despesa")):
            bruto = texto(celula(valores, "e_despesa"))
            despesa = SIM_NAO.get(chave_estrita(bruto))
            if despesa is None:
                evidencias.append("E_DESPESA_NAO_INTERPRETADO")
            elif natureza == "INDETERMINADA":
                natureza = "SAIDA" if despesa else "ENTRADA"
                evidencias.append("NATUREZA_PELA_COLUNA_E_DESPESA")
            elif (natureza == "SAIDA") != despesa:
                pendencias.append(pendencia(
                    ATENCAO, "DIVERGENCIA_NATUREZA",
                    f"{onde}: o lançamento é {'saída' if natureza == 'SAIDA' else 'entrada'} pelas colunas de valor, "
                    f"mas '{cab('e_despesa')}' = '{bruto}'.",
                    "A linha não entrou nos movimentos; a natureza não foi alterada para fazer as colunas concordarem.",
                    "Conferir na origem se o lançamento é entrada ou saída e reenviar a planilha ajustada.",
                    natureza_movimento=natureza, e_despesa=bruto, **ref))
                continue
            else:
                evidencias.append("E_DESPESA_CONSISTENTE")
        if contraparte:
            evidencias.append("CONTRAPARTE_INFORMADA")
        movimentos.append({
            "id": "RF-" + hashlib.sha256(f"{sha}|{nome_aba}|{n}".encode("utf-8")).hexdigest()[:12].upper(),
            "data": datas.get("data"), "data_vencimento": datas.get("data_vencimento"), "data_quitacao": datas.get("data_quitacao"),
            "descricao": descricao, "valor": valor, "natureza": natureza,
            "plano_contas": texto(celula(valores, "plano_contas")), "banco": texto(celula(valores, "banco")),
            "empresa": texto(celula(valores, "empresa")), "documento": texto(celula(valores, "documento")),
            "codigo": texto(celula(valores, "codigo")), "indice_linha": n,
            "origem": {"arquivo": nome, "aba": nome_aba, "linha": n}, "sha": sha, "evidencias": evidencias,
            "data_competencia": datas.get("data_competencia"), "situacao": situacao, "contraparte": contraparte})
    return movimentos


def normalizar_planilha_financeira(arquivo: dict) -> dict:
    """RELATORIO_FINANCEIRO + EXTRAIDO_PLANILHA → MOVIMENTOS_FINANCEIROS_NORMALIZADOS."""
    nome, sha = arquivo.get("arquivo"), arquivo.get("sha256")
    marcacoes = list(arquivo.get("marcacoes") or [])
    conteudo = arquivo.get("conteudo") or {}
    pendencias, ignoradas, nao_realizadas, movimentos, abas_usadas, mapeamentos = [], [], [], [], [], {}
    base = {"contrato": CONTRATO, "versao": VERSAO, "tipo_fonte": "RELATORIO_FINANCEIRO", "adaptador": "PLANILHA_FINANCEIRA_GENERICA",
            "origem": {"arquivo": nome, "sha256": sha, "leitura": arquivo.get("leitura"), "marcacoes": marcacoes}}

    def recusar(codigo, problema, o_que_fazer):
        pendencias.append(pendencia(BLOQUEIO, codigo, problema, "Nenhum movimento deste arquivo foi normalizado.", o_que_fazer))
        return _fechar(base, [], ignoradas, pendencias, {}, [], [])

    if arquivo.get("leitura") != "EXTRAIDO_PLANILHA":
        return recusar("LEITURA_NAO_SUPORTADA", f"{nome}: a leitura do arquivo ({arquivo.get('leitura')}) não é de planilha extraída.",
                       "Enviar a planilha em formato XLSX legível.")
    if not sha:
        return recusar("ORIGEM_SEM_SHA", f"{nome}: o arquivo chegou sem a impressão digital (SHA-256) do original.",
                       "Refazer a etapa de Documentos para que a origem possa ser rastreada.")
    if "LIMITE_EXCEDIDO" in marcacoes or conteudo.get("truncado") or any(a.get("truncado") for a in conteudo.get("abas") or []):
        return recusar("PLANILHA_INCOMPLETA", f"{nome}: a planilha foi lida só em parte (limite do leitor).",
                       "Dividir a planilha em arquivos menores e reenviar; leitura parcial não é aproveitada.")
    # Estilo inválido + leitor alternativo NÃO bloqueiam: os dados foram recuperados íntegros. Fica só o registro.
    if "LEITOR_CALAMINE_FALLBACK" in marcacoes or "ESTILO_XLSX_INVALIDO" in marcacoes:
        pendencias.append(pendencia(
            INFORMATIVO, "LEITURA_ALTERNATIVA", f"{nome}: a planilha tem um problema de formatação e foi lida por método alternativo.",
            "Nenhum: os dados foram recuperados. Datas podem ter vindo como número de série do Excel e foram convertidas.",
            "Nada a fazer. Se alguma data parecer estranha, conferir na planilha original."))
    for aba in conteudo.get("abas") or []:
        if aba.get("oculta"):
            pendencias.append(pendencia(INFORMATIVO, "ABA_OCULTA_NAO_USADA", f"{nome}: a aba oculta '{aba.get('aba')}' não foi usada.",
                                        "Lançamentos que estejam só nessa aba não entraram.", "Se a aba tiver lançamentos, reexibi-la e reenviar.",
                                        aba=aba.get("aba")))
            continue
        posicao, achado = localizar_cabecalho(aba.get("linhas") or [])
        if achado is None:
            continue
        mapa, repetidos, sobras = achado
        linha_cab = aba["linhas"][posicao].get("linha")
        if repetidos:
            lista = "; ".join(f"{campo}: {', '.join(nomes)}" for campo, nomes in repetidos.items())
            pendencias.append(pendencia(
                BLOQUEIO, "CABECALHO_AMBIGUO", f"{nome} · {aba.get('aba')}: mais de uma coluna para o mesmo campo ({lista}).",
                "A aba não foi normalizada; o sistema não escolhe uma das colunas.",
                "Manter uma só coluna por informação (ou renomear as demais) e reenviar.", aba=aba.get("aba")))
            continue
        if aba.get("formulas_sem_valor"):
            pendencias.append(pendencia(
                ATENCAO, "FORMULA_SEM_VALOR", f"{nome} · {aba.get('aba')}: há fórmulas sem valor gravado; essas células chegaram vazias.",
                "Linhas que dependem dessas células podem aparecer como sem valor.",
                "Abrir a planilha, recalcular, salvar e reenviar.", aba=aba.get("aba")))
        ignoradas += [{"aba": aba.get("aba"), "indice_linha": l.get("linha"), "motivo": "ANTES_DO_CABECALHO"} for l in aba["linhas"][:posicao]]
        movimentos += _normalizar_aba(aba, posicao, mapa, nome, sha, pendencias, ignoradas, nao_realizadas)
        abas_usadas.append({"aba": aba.get("aba"), "linha_cabecalho": linha_cab, "linhas_lidas": len(aba["linhas"]) - posicao - 1,
                            "colunas_nao_mapeadas": sobras})
        mapeamentos[aba.get("aba")] = mapa
    if not abas_usadas and not any(p["nivel"] == BLOQUEIO for p in pendencias):
        return recusar("CABECALHO_NAO_RECONHECIDO", f"{nome}: nenhuma aba visível tem cabeçalho de relatório financeiro "
                       "(ao menos uma coluna de data, uma de valor e mais uma informação).",
                       "Conferir se o arquivo é o relatório financeiro e se a linha de títulos das colunas está nas primeiras linhas.")
    indeterminados = [m for m in movimentos if m["natureza"] == "INDETERMINADA"]
    if indeterminados:
        pendencias.append(pendencia(
            ATENCAO, "NATUREZA_INDETERMINADA", f"{nome}: {len(indeterminados)} lançamento(s) sem indicação de entrada ou saída na planilha.",
            "Esses lançamentos seguem como INDETERMINADA e não poderão ser conciliados por natureza.",
            "Enviar o relatório com colunas separadas de entrada e saída, ou com uma coluna de tipo.",
            linhas=[m["indice_linha"] for m in indeterminados]))
    fechadas = [l for l in nao_realizadas if l["situacao"] in ("EM_ABERTO", "CANCELADO")]
    if fechadas:
        pendencias.append(pendencia(
            INFORMATIVO, "LINHAS_NAO_REALIZADAS",
            f"{nome}: {len(fechadas)} lançamento(s) em aberto ou cancelado(s) na própria planilha.",
            "Não entram como movimentos realizados; ficam preservados à parte para consulta.",
            "Nada a fazer, salvo se algum deles já tiver sido pago/recebido (então atualizar a planilha e reenviar).",
            linhas=[l["indice_linha"] for l in fechadas]))
    return _fechar(base, movimentos, ignoradas, pendencias, mapeamentos, abas_usadas, nao_realizadas)


def _fechar(base, movimentos, ignoradas, pendencias, mapeamentos, abas_usadas, nao_realizadas) -> dict:
    bloqueio = any(p["nivel"] == BLOQUEIO for p in pendencias)
    usados = {campo for mapa in mapeamentos.values() for campo in mapa}
    usados |= {"contraparte"} if usados & set(CONTRAPARTE) else set()
    total = lambda natureza: sum((m["valor"] for m in movimentos if m["natureza"] == natureza), Decimal("0.00"))
    contar = lambda natureza: sum(1 for m in movimentos if m["natureza"] == natureza)
    return {**base,
            "situacao": ("NAO_NORMALIZADO" if not movimentos and (bloqueio or not abas_usadas) else
                         "NORMALIZADO_COM_PENDENCIAS" if any(p["nivel"] != INFORMATIVO for p in pendencias) else "NORMALIZADO"),
            "abas": abas_usadas, "mapeamento": mapeamentos,
            "campos_ausentes": [c for c in CAMPOS_DA_ORIGEM if c not in usados] if mapeamentos else [],
            "campos_complementares_ausentes": [c for c in CAMPOS_COMPLEMENTARES if c not in usados] if mapeamentos else [],
            "movimentos": movimentos, "linhas_nao_realizadas": nao_realizadas, "linhas_ignoradas": ignoradas, "pendencias": pendencias,
            "resumo": {"linhas_lidas": sum(a["linhas_lidas"] for a in abas_usadas), "movimentos": len(movimentos),
                       "entradas": contar("ENTRADA"), "saidas": contar("SAIDA"), "indeterminadas": contar("INDETERMINADA"),
                       "total_entradas": total("ENTRADA"), "total_saidas": total("SAIDA"), "total_indeterminado": total("INDETERMINADA"),
                       "nao_realizadas": len(nao_realizadas), "linhas_ignoradas": len(ignoradas), "pendencias": len(pendencias),
                       "bloqueios": sum(1 for p in pendencias if p["nivel"] == BLOQUEIO)}}


# ---------------------------------------------------------------- registro de adaptadores (ponto de extensão)

# (nome, reconhece(arquivo) -> bool, normaliza(arquivo) -> contrato). Novas fontes (Santander, Bradesco, Itaú, Banco do
# Brasil, Omie...) entram AQUI, cada uma devolvendo o mesmo contrato; o Financeiro não muda.
ADAPTADORES = [
    ("PLANILHA_FINANCEIRA_GENERICA", reconhece_planilha_financeira, normalizar_planilha_financeira),
]


def normalizar(arquivo: dict) -> dict:
    """Escolhe o adaptador pelo conteúdo. Nenhum ou mais de um candidato = não normaliza (nunca escolhe em silêncio)."""
    candidatos = [(nome, fn) for nome, reconhece, fn in ADAPTADORES if reconhece(arquivo)]
    if len(candidatos) == 1:
        return candidatos[0][1](arquivo)
    if arquivo.get("leitura") == "EXTRAIDO_PLANILHA" and not candidatos:
        return normalizar_planilha_financeira(arquivo)          # devolve o motivo exato (cabeçalho, truncado, sha...)
    nome = arquivo.get("arquivo")
    base = {"contrato": CONTRATO, "versao": VERSAO, "tipo_fonte": None, "adaptador": None,
            "origem": {"arquivo": nome, "sha256": arquivo.get("sha256"), "leitura": arquivo.get("leitura"),
                       "marcacoes": list(arquivo.get("marcacoes") or [])}}
    p = (pendencia(BLOQUEIO, "FONTE_AMBIGUA", f"{nome}: mais de um leitor reconhece este arquivo ({', '.join(n for n, _ in candidatos)}).",
                   "Nenhum movimento foi normalizado; o sistema não escolhe um leitor em silêncio.", "Encaminhar ao Supervisor para definir a fonte.")
         if candidatos else
         pendencia(BLOQUEIO, "FONTE_SEM_ADAPTADOR", f"{nome}: ainda não há leitor financeiro para este tipo de documento.",
                   "Nenhum movimento foi normalizado; nada foi inferido do conteúdo.",
                   "Enviar o relatório financeiro em planilha, ou aguardar o leitor específico desta fonte."))
    return _fechar(base, [], [], [p], {}, [], [])


def para_json(obj):
    """Cópia serializável: Decimal vira texto com duas casas ('1234.56'). Nunca converte para float."""
    if isinstance(obj, Decimal):
        return f"{obj:.2f}"
    if isinstance(obj, dict):
        return {k: para_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [para_json(v) for v in obj]
    return obj
