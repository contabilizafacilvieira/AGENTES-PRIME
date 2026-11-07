"""TXT de lançamentos para importação MANUAL no Domínio — gerado somente depois da aprovação explícita do Supervisor.

Cabeçalho e formato dos campos iguais aos da referência da VGROW (REGRAS_Vgrow_Importacoes.md §7; macro "Lançamentos Contábeis
Partidas Simples.Múltiplas3.1"):
    Data;Débito;Crédito;Valor;CódHist;Complemento;IniciaLote;Matriz/Filial;CCDébito;CCCrédito
- data dd/mm/aaaa; valor com vírgula decimal e sem separador de milhar (mesma formatação do gerador da VGROW); códigos reduzidos;
- arquivo cp1252, quebra de linha CRLF.
ATENÇÃO — variante AINDA NÃO VALIDADA no Domínio: a referência da VGROW valida PARTIDA MÚLTIPLA (cada linha só com débito OU
crédito; IniciaLote = 1 só na 1ª linha de cada processo). Por decisão do Supervisor (04/11/2026) este exportador usa PARTIDA
SIMPLES: UMA linha por lançamento, débito e crédito na mesma linha, IniciaLote = 1 em todas as linhas. Essa variante exige teste
de importação numa empresa de teste do Domínio antes de qualquer uso real (roteiro: TESTES/EXPORTACAO/ROTEIRO-TESTE-DOMINIO.md).

Regras desta exportação (nada é presumido nem perdido em silêncio):
- só lançamentos dos resultados APROVADOS (sha256 iguais aos da aprovação), todos "propostos", com identidade de fato aprovada;
- valor em texto decimal com até 2 casas, finito e > 0; contas existentes, ANALÍTICAS no plano da empresa e diferentes entre si;
- data do lançamento obrigatória no resultado e dentro da competência (DP/Fiscal: política de data da empresa; nunca presumida);
- Complemento = histórico do fato contábil; caminho técnico, nome de arquivo ou ID interno é recusado (fica na auditoria);
- transformações de caracteres são explícitas e registradas por linha (NFC, ';' do separador → ',', quebras/tabulação → espaço,
  espaços repetidos); caractere fora do cp1252 RECUSA a exportação (nenhum '?' silencioso);
- tamanho máximo do Complemento no Domínio NÃO comprovado: nada é truncado; o maior tamanho fica registrado para validação.
"""
import datetime as dt
import hashlib
import json
import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
def clientes():
    """Pasta CLIENTES (avaliada a cada uso: AGENTES_PRIME_CLIENTES em testes isolados; RAIZ/CLIENTES em produção)."""
    return Path(os.environ.get("AGENTES_PRIME_CLIENTES") or RAIZ / "CLIENTES")
PROPOSTO = ("PROPOSTO", "PROPOSTO_PARA_CONFERENCIA")
ORIGENS = (("BANCOS", "bancos", "Bancos"), ("CONTABILIDADE_DP", "contabdp", "DP"), ("CONTABILIDADE_FISCAL", "contabilfiscal", "Fiscal"))
CABECALHO = "Data;Débito;Crédito;Valor;CódHist;Complemento;IniciaLote;Matriz/Filial;CCDébito;CCCrédito"
VALOR = re.compile(r"\d{1,13}(?:\.\d{1,2})?")
EXTENSOES = r"(?:pdf|txt|csv|xml|xlsx|xlsm|xls|ofx|json|png|jpe?g|zip)"
TECNICO = re.compile(r"\\|RECEBIDOS/|\b[\w.-]+\." + EXTENSOES + r"\b|\bL-\d{8}-\d{6}-[0-9a-f]{6}\b|\bSOL-\d{4}-\d{6}\b"
                     r"|\b(?:MOV|DPD|DOC|LAN|REL|PF|DP)-[0-9A-F]{8,}\b", re.I)
LIMITE_COMPLEMENTO = "NAO_COMPROVADO"        # nenhuma referência comprovada do tamanho máximo no Domínio


class ErroExportacao(ValueError):
    def __init__(self, problemas):
        self.problemas = list(problemas)
        super().__init__("; ".join(self.problemas[:12]) + (f" (+{len(self.problemas) - 12})" if len(self.problemas) > 12 else ""))


def fmt_valor(v: Decimal) -> str:
    """Igual a fmt_txt do gerador da VGROW: vírgula decimal, sem milhar, sem zeros à direita desnecessários."""
    s = format(v.normalize(), "f") if v != v.to_integral() else str(int(v))
    return s.replace(".", ",")


def _cp1252(c: str) -> bool:
    try:
        c.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def complemento(texto) -> tuple:
    """(texto final, transformações registradas). Levanta ValueError para caminho técnico ou caractere fora do cp1252."""
    original = str(texto or "")
    t, transf = unicodedata.normalize("NFC", original), []
    if t != original:
        transf.append("normalização Unicode NFC")
    if re.search(r"[\r\n\t]", t):
        t = re.sub(r"[\r\n\t]+", " ", t)
        transf.append("quebra de linha/tabulação → espaço")
    if ";" in t:
        t = t.replace(";", ",")
        transf.append("';' (separador do layout) → ','")
    novo = re.sub(r" {2,}", " ", t).strip()
    if novo != t:
        transf.append("espaços repetidos/nas pontas removidos")
    t = novo
    if not t:
        raise ValueError("histórico ausente")
    if any(unicodedata.category(c) == "Cc" for c in t):
        raise ValueError("histórico com caractere de controle")
    achado = TECNICO.search(t)
    if achado:
        raise ValueError(f"histórico com caminho técnico, nome de arquivo ou ID interno ({achado.group(0)!r}); esses dados ficam na auditoria")
    fora = sorted({c for c in t if not _cp1252(c)})
    if fora:
        raise ValueError("histórico com caractere(s) fora do cp1252 (sem substituição silenciosa): "
                         + ", ".join(f"{c!r} U+{ord(c):04X}" for c in fora))
    return t, transf


def valor_exato(v):
    """Decimal > 0 com até 2 casas a partir do TEXTO do resultado ('1234.56'); qualquer outro formato é recusado."""
    if not isinstance(v, str) or not VALOR.fullmatch(v.strip()):
        raise ValueError(f"valor ausente ou fora do formato decimal com até 2 casas ({v!r})")
    try:
        d = Decimal(v.strip())
    except InvalidOperation:
        raise ValueError(f"valor inválido ({v!r})")
    if not d.is_finite() or d <= 0:
        raise ValueError(f"valor não positivo ou não finito ({v!r})")
    return d


def _ascii(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()


def plano_empresa(empresa: str) -> dict:
    """Código reduzido → {tipo, grupo, descricao}: cadastro local (empresa-local.json) ou, na falta, PLANO-DE-CONTAS.md."""
    base = clientes() / empresa
    local = base / "empresa-local.json"
    if local.is_file():
        dados = json.loads(local.read_text(encoding="utf-8"))
        return {str(c.get("codigo")): {"tipo": _ascii(str(c.get("tipo") or "")), "grupo": c.get("grupo"), "descricao": c.get("descricao"),
                                       "classificacao": c.get("classificacao"), "dominio": c.get("dominio"), "origem": c.get("origem")}
                for c in dados.get("plano", []) if c.get("codigo")}
    arquivo = base / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md"
    if not arquivo.is_file():
        return {}
    contas, dentro, cab = {}, False, None
    for l in arquivo.read_text(encoding="utf-8").splitlines():
        if l.startswith("## "):
            dentro, cab = "CONTAS UTILIZADAS" in _ascii(l), None
            continue
        if dentro and l.strip().startswith("|"):
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if cab is None:
                cab = [_ascii(x) for x in c]
            elif not all(re.fullmatch(r":?-{2,}:?", x) for x in c if x):
                linha = dict(zip(cab, c))
                cod = re.sub(r"\D", "", linha.get("CODIGO REDUZIDO", ""))
                if cod:
                    contas[cod] = {"tipo": _ascii(linha.get("TIPO", "")), "grupo": linha.get("GRUPO"), "descricao": linha.get("DESCRICAO")}
    return contas


def _fim(competencia: str) -> dt.date:
    a, m = map(int, competencia.split("-"))
    return dt.date(a + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)


def gerar(sol: str, registro: dict, resultados: dict, plano: dict) -> dict:
    """resultados: ETAPA → caminho do resultado aprovado. Devolve {conteudo, linhas, total, por_origem, auditoria} ou levanta
    ErroExportacao com TODOS os problemas encontrados (nada é gerado parcialmente)."""
    aprovacao = registro.get("aprovacao") or {}
    aprovadas = aprovacao.get("versoes_aprovadas") or {}
    if registro.get("estado") != "FECHAMENTO_APROVADO" or not aprovadas:
        raise ErroExportacao(["Fechamento não aprovado: nenhum TXT é gerado sem a aprovação explícita do Supervisor."])
    fatos_aprovados = aprovacao.get("fatos_aprovados")
    problemas, linhas, vistos, ocorrencias = [], [], set(), {}
    competencia = registro["competencia"]
    inicio, fim = dt.date.fromisoformat(competencia + "-01"), _fim(competencia)
    for etapa, _, nome in ORIGENS:
        caminho = resultados.get(etapa)
        if not caminho:
            if etapa in aprovadas:
                problemas.append(f"Resultado aprovado de {nome} não encontrado.")
            continue
        bruto = Path(caminho).read_bytes()
        if hashlib.sha256(bruto).hexdigest() != aprovadas.get(etapa):
            problemas.append(f"Resultado de {nome} diferente do aprovado (sha256).")
            continue
        r = json.loads(bruto.decode("utf-8"))
        if (r.get("empresa"), r.get("sol"), r.get("competencia")) != (registro["empresa"], sol, competencia):
            problemas.append(f"Resultado de {nome} de outra empresa/SOL/competência.")
            continue
        for l in r.get("lancamentos", []):
            ref = f"{nome}/{l.get('id')}"
            if l.get("status") not in PROPOSTO:
                problemas.append(f"{ref}: lançamento não proposto ({l.get('status')}); nada é liberado.")
                continue
            erros = []
            try:
                valor = valor_exato(l.get("valor"))
            except ValueError as e:
                erros.append(str(e))
                valor = None
            contas = {}
            for lado in ("debito", "credito"):
                cod = str((l.get(lado) or {}).get("codigo") or "")
                conta = plano.get(cod)
                if not cod:
                    erros.append(f"conta de {lado} ausente")
                elif conta is None:
                    erros.append(f"conta de {lado} {cod} inexistente no plano da empresa")
                elif conta["tipo"] not in ("ANALITICA", "A"):
                    erros.append(f"conta de {lado} {cod} não é analítica (tipo {conta['tipo'] or 'não definido'})")
                elif conta.get("dominio") == "PENDENTE_CONFERENCIA":
                    erros.append(f"conta de {lado} {cod} criada no aplicativo sem correspondência confirmada no Domínio (crie-a no Domínio "
                                 "manualmente e confirme a correspondência na tela Empresas)")
                contas[lado] = cod
            if contas.get("debito") and contas.get("debito") == contas.get("credito"):
                erros.append("débito e crédito na mesma conta")
            data = None
            try:
                data = dt.date.fromisoformat(str(l.get("data")))
                if not inicio <= data <= fim:
                    erros.append(f"data {data.isoformat()} fora da competência {competencia}")
            except ValueError:
                erros.append("data do lançamento ausente ou inválida (não presumida; defina a política de data da empresa)")
            ident = l.get("identidade")
            if ident:
                ocorrencias.setdefault(ident, []).append(ref)
            if not ident:
                erros.append("lançamento sem identidade de fato (rastreabilidade)")
            elif len(ocorrencias[ident]) > 1:
                erros.append(f"identidade de fato repetida no mesmo TXT ({ident}; também em {ocorrencias[ident][0]})")
            elif fatos_aprovados is not None:
                fa = fatos_aprovados.get(ident)
                if fa is None:
                    erros.append(f"fato {ident} não consta entre os fatos aprovados")
                elif (str(fa.get("valor")), fa.get("debito"), fa.get("credito")) != (str(l.get("valor")), contas.get("debito"), contas.get("credito")):
                    erros.append(f"valor/contas do fato {ident} diferentes dos aprovados")
            try:
                texto, transf = complemento(l.get("historico"))
            except ValueError as e:
                erros.append(str(e))
                texto, transf = None, []
            if erros:
                problemas += [f"{ref}: {e}" for e in erros]
                continue
            vistos.add(ident)
            campos = [data.strftime("%d/%m/%Y"), contas["debito"], contas["credito"], fmt_valor(valor), "", texto, "1", "", "", ""]
            linhas.append({"data": data, "origem": nome, "identidade": ident, "texto": ";".join(campos), "valor": valor,
                           "debito": contas["debito"], "credito": contas["credito"], "complemento": texto,
                           "audit": {"origem": nome, "etapa": etapa, "lancamento": l.get("id"), "identidade": ident,
                                     "documento": l.get("documento"), "arquivo": l.get("arquivo"), "sha256_documento": l.get("sha256"),
                                     "movimentos": l.get("movimentos"), "data_origem": l.get("data_origem") or "data do movimento no extrato",
                                     "historico_original": l.get("historico"), "complemento": texto, "transformacoes": transf,
                                     "tamanho_complemento": len(texto)}})
    if fatos_aprovados is not None and not problemas:
        faltando = sorted(set(fatos_aprovados) - vistos)
        if faltando:
            problemas.append(f"{len(faltando)} fato(s) aprovado(s) ausente(s) dos resultados: " + ", ".join(faltando[:5]))
    if problemas:
        raise ErroExportacao(problemas)
    if not linhas:
        raise ErroExportacao(["Nenhum lançamento aprovado para exportar."])
    ordem = [o[2] for o in ORIGENS]
    linhas.sort(key=lambda x: (x["data"], ordem.index(x["origem"]), x["identidade"]))
    texto = "\r\n".join(x["texto"] for x in linhas) + "\r\n"
    total = sum((x["valor"] for x in linhas), Decimal("0"))
    auditoria, por_origem = [], {}
    for n, x in enumerate(linhas, 1):
        auditoria.append(dict(x["audit"], linha=n))
        por_origem[x["origem"]] = por_origem.get(x["origem"], 0) + 1
    lancamentos = [{"linha": n, "data": x["data"].isoformat(), "debito": x["debito"], "credito": x["credito"], "valor": f"{x['valor']:.2f}",
                    "complemento": x["complemento"], "origem": x["origem"], "identidade": x["identidade"],
                    "lancamento": x["audit"]["lancamento"]} for n, x in enumerate(linhas, 1)]
    return {"conteudo": texto.encode("cp1252"), "linhas": len(linhas), "total": f"{total:.2f}", "por_origem": por_origem,
            "lancamentos": lancamentos,
            "auditoria": {"sol": sol, "empresa": registro["empresa"], "competencia": competencia, "layout": CABECALHO,
                          "variante": "PARTIDA_SIMPLES_INICIALOTE_1_TODAS (decisão do Supervisor 04/11/2026; NÃO validada no Domínio)",
                          "cabecalho_no_arquivo": False, "codificacao": "cp1252", "quebra": "CRLF",
                          "limite_complemento": LIMITE_COMPLEMENTO, "maior_complemento": max(a["tamanho_complemento"] for a in auditoria),
                          "transformacoes_total": sum(len(a["transformacoes"]) for a in auditoria), "linhas": auditoria,
                          "total": f"{total:.2f}", "importado_no_dominio": False, "escriturado": False}}


# ---------------------------------------------------------------- Excel dos lançamentos e balancete (mesma versão do TXT)
AVISO_SIMULACAO = ("SIMULAÇÃO — calculado pelo aplicativo sobre os lançamentos APROVADOS desta solicitação. Não comprova importação nem "
                   "escrituração no Domínio; a importação do TXT é manual, pelo Supervisor.")


def _identificacao(ws, registro: dict, sol: str, txt_nome: str, txt_sha: str, gerado: dict, extra=()):
    from openpyxl.styles import Font
    ap = registro.get("aprovacao") or {}
    linhas = [("Solicitação", sol), ("Empresa", registro.get("empresa")), ("Competência", registro.get("competencia")),
              ("Aprovação do Supervisor", ap.get("em")), ("Conciliação aprovada (tentativa)", ap.get("conciliacao_tentativa")),
              ("Conciliação aprovada (sha256)", ap.get("conciliacao_sha256")), ("Arquivo TXT correspondente", txt_nome),
              ("sha256 do TXT correspondente", txt_sha), ("Lançamentos", gerado["linhas"]), ("Total dos lançamentos", Decimal(gerado["total"])),
              *extra, ("Aviso", AVISO_SIMULACAO)]
    for i, (k, v) in enumerate(linhas, 1):
        ws.cell(i, 1, k).font = Font(bold=True)
        c = ws.cell(i, 2, v)
        if isinstance(v, Decimal):
            c.number_format = "#,##0.00"
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 34, 90


def _bytes(wb) -> bytes:
    import io
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def gerar_excel(sol: str, registro: dict, gerado: dict, plano: dict, txt_nome: str, txt_sha: str) -> bytes:
    """Planilha dos lançamentos EXATAMENTE como no TXT (mesma ordem, linha a linha), com descrições do plano e rastreabilidade."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Lançamentos"
    cab = ["Linha do TXT", "Data", "Débito", "Descrição do débito", "Crédito", "Descrição do crédito", "Valor", "Complemento (histórico)",
           "Origem", "Identidade do fato", "Lançamento proposto"]
    ws.append(cab)
    for c in ws[1]:
        c.font = Font(bold=True)
    for l in gerado["lancamentos"]:
        ws.append([l["linha"], dt.date.fromisoformat(l["data"]), l["debito"], (plano.get(l["debito"]) or {}).get("descricao"), l["credito"],
                   (plano.get(l["credito"]) or {}).get("descricao"), Decimal(l["valor"]), l["complemento"], l["origem"], l["identidade"],
                   l["lancamento"]])
        ws.cell(ws.max_row, 2).number_format = "dd/mm/yyyy"
        ws.cell(ws.max_row, 7).number_format = "#,##0.00"
    n = ws.max_row
    ws.append(["Total", None, None, None, None, None, sum((Decimal(l["valor"]) for l in gerado["lancamentos"]), Decimal("0"))])
    ws.cell(n + 1, 1).font = Font(bold=True)
    ws.cell(n + 1, 7).number_format = "#,##0.00"
    for col, w in zip("ABCDEFGHIJK", (12, 12, 10, 34, 10, 34, 14, 60, 10, 48, 34)):
        ws.column_dimensions[col].width = w
    _identificacao(wb.create_sheet("Identificação"), registro, sol, txt_nome, txt_sha, gerado)
    return _bytes(wb)


def _ordem(classificacao, codigo):
    partes = str(classificacao or "").split(".")
    return (0, [int(x) for x in partes if x.isdigit()], str(codigo)) if classificacao else (1, [], str(codigo).zfill(12))


def calcular_balancete(gerado: dict, saldos_conciliacao: list, plano: dict, abrangencia: dict) -> dict:
    """Balancete de verificação: contas ANALÍTICAS = abertura DOCUMENTADA (Conciliação aprovada, que usa a base inicial confirmada;
    ausente nunca vira zero) + movimento dos lançamentos aprovados = saldo final. Contas SINTÉTICAS (pela classificação do plano) são
    linhas de consolidação = soma das analíticas subordinadas; nunca entram nos totais (sem duplicar).
    Entrega COMPLEMENTAR: movimento só desta SOL; saldo final não é calculado (dependeria das outras entregas da competência)."""
    abertura = {}
    for s in saldos_conciliacao or []:
        if s.get("abertura") is not None:
            abertura[str(s["conta"])] = Decimal(str(s["abertura"]))
    mov = {}
    for l in gerado["lancamentos"]:
        v = Decimal(l["valor"])
        mov.setdefault(l["debito"], [Decimal("0"), Decimal("0")])[0] += v
        mov.setdefault(l["credito"], [Decimal("0"), Decimal("0")])[1] += v
    integral = abrangencia.get("tipo") == "INTEGRAL"
    contas = []
    for c in sorted(set(abertura) | set(mov), key=lambda x: (len(x), x)):
        info = plano.get(c) or {}
        if info.get("tipo") and info["tipo"] not in ("ANALITICA", "A"):
            continue                                    # nunca soma conta sintética junto com as analíticas
        d, cr = mov.get(c, [Decimal("0"), Decimal("0")])
        ab = abertura.get(c)
        if not integral:
            final, situacao = None, "NAO_CALCULADO_ENTREGA_COMPLEMENTAR"
        elif ab is None:
            final, situacao = None, "NAO_CALCULADO_ABERTURA_NAO_DOCUMENTADA"
        else:
            final, situacao = ab + d - cr, "CALCULADO"
        contas.append({"conta": c, "classificacao": info.get("classificacao"), "descricao": info.get("descricao"), "grupo": info.get("grupo"),
                       "tipo": "ANALITICA", "nivel": None, "abertura": ab, "debitos": d, "creditos": cr, "saldo_final": final,
                       "situacao": situacao})
    # consolidação hierárquica: sintética = soma das analíticas subordinadas (pela classificação); incompleta se alguma faltar
    sinteticas = []
    for cod, info in plano.items():
        k = info.get("classificacao")
        if not k or info.get("tipo") in ("ANALITICA", "A"):
            continue
        filhas = [x for x in contas if x["classificacao"] and x["classificacao"].startswith(k + ".")]
        if not filhas:
            continue
        soma = lambda campo: (None if any(x[campo] is None for x in filhas)  # noqa: E731
                              else sum((x[campo] for x in filhas), Decimal("0")))
        sinteticas.append({"conta": cod, "classificacao": k, "descricao": info.get("descricao"), "grupo": info.get("grupo"), "tipo": "SINTETICA",
                           "abertura": soma("abertura"), "debitos": soma("debitos"), "creditos": soma("creditos"),
                           "saldo_final": soma("saldo_final"), "subordinadas": len(filhas),
                           "situacao": "CONSOLIDADA" if all(x["situacao"] == "CALCULADO" for x in filhas) else "CONSOLIDACAO_INCOMPLETA"})
    for x in contas + sinteticas:
        x["nivel"] = x["classificacao"].count(".") + 1 if x.get("classificacao") else None
    linhas = sorted(contas + sinteticas, key=lambda x: _ordem(x["classificacao"], x["conta"]))
    tot = lambda k: sum((x[k] for x in contas if x[k] is not None), Decimal("0"))  # noqa: E731
    return {"contas": contas, "sinteticas": sinteticas, "linhas": linhas, "total_debitos": tot("debitos"), "total_creditos": tot("creditos"),
            "soma_aberturas": tot("abertura") if integral else None, "soma_saldos_finais": tot("saldo_final") if integral else None,
            "contas_sem_abertura": [x["conta"] for x in contas if x["abertura"] is None], "abrangencia": abrangencia}


COLUNAS_BALANCETE = ["Código", "Classificação", "Descrição", "Tipo", "Grupo", "Saldo inicial", "D/C inicial", "Débitos", "Créditos",
                     "Saldo final", "D/C final", "Situação"]


def gerar_balancete(sol: str, registro: dict, gerado: dict, saldos_conciliacao: list, plano: dict, abrangencia: dict,
                    txt_nome: str, txt_sha: str, base_inicial: dict = None) -> tuple:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    b = calcular_balancete(gerado, saldos_conciliacao, plano, abrangencia)
    wb = Workbook()
    ws = wb.active
    ws.title = "Balancete"
    nat = lambda v: None if v is None else ("D" if v > 0 else "C" if v < 0 else "")  # noqa: E731
    ws.append(COLUNAS_BALANCETE)
    for c in ws[1]:
        c.font = Font(bold=True)
    for x in b["linhas"]:
        ws.append([x["conta"], x["classificacao"], x["descricao"], "S" if x["tipo"] == "SINTETICA" else "A", x["grupo"],
                   abs(x["abertura"]) if x["abertura"] is not None else "não documentado", nat(x["abertura"]), x["debitos"],
                   x["creditos"], abs(x["saldo_final"]) if x["saldo_final"] is not None else "não calculado", nat(x["saldo_final"]),
                   x["situacao"]])
        for col in (6, 8, 9, 10):
            ws.cell(ws.max_row, col).number_format = "#,##0.00"
        if x["tipo"] == "SINTETICA":
            for col in range(1, 13):
                ws.cell(ws.max_row, col).font = Font(bold=True)
    ws.append(["Total do movimento (só contas analíticas)", None, None, None, None, None, None, b["total_debitos"], b["total_creditos"]])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    for col in (8, 9):
        ws.cell(ws.max_row, col).number_format = "#,##0.00"
    for col, w in zip("ABCDEFGHIJKL", (10, 18, 34, 6, 14, 18, 6, 18, 18, 18, 6, 34)):
        ws.column_dimensions[col].width = w
    ab = b["abrangencia"]
    bi = base_inicial or {}
    _identificacao(wb.create_sheet("Identificação"), registro, sol, txt_nome, txt_sha, gerado, extra=(
        ("Abrangência", f"{ab['tipo']}: {ab['texto']}"),
        ("Saldos de abertura", ("Base inicial CONFIRMADA (balancete de encerramento do mês anterior) e/ou documento SALDOS DE ABERTURA, "
                                "conferidos pela Conciliação aprovada" if bi else "Documento SALDOS DE ABERTURA conferido pela Conciliação "
                                "aprovada") + "; conta sem abertura = 'não documentado' (nunca presumido zero)."),
        ("Base inicial", (f"versão {bi.get('versao')} · data-base {bi.get('data_base')} · confirmada em {bi.get('confirmada_em')} · balancete "
                          f"{bi.get('balancete')} · book {bi.get('book') or 'não recebido'} · sha256 {bi.get('sha256')}") if bi else
         "não utilizada nesta Conciliação"),
        ("Contas", "Analíticas (A) somadas nos totais; sintéticas (S) são consolidação das analíticas subordinadas pela classificação, "
                   "em negrito, e NÃO entram nos totais (sem duplicar)."),
        ("Convenção", "Valores exatos; D = devedor, C = credor. O total do movimento não é saldo: saldo final = saldo inicial + débitos − "
                      "créditos.")))
    return _bytes(wb), b



def liberacao_permitida(empresa: str) -> bool:
    """Produção bloqueada nesta versão (CLAUDE.md): o TXT só é gerado para empresa FICTÍCIA da amostra (pasta com o marcador
    AMOSTRA-FICTICIA.json criado pela preparação). Empresa real (inclusive em piloto SIMULAÇÃO): aprovação registrada, TXT bloqueado."""
    return (clientes() / empresa / "AMOSTRA-FICTICIA.json").is_file()


def destino(empresa: str, competencia: str, sol: str) -> Path:
    base = Path(os.environ.get("AGENTES_PRIME_LIBERADOS") or RAIZ / "LIBERADOS")
    return base / empresa / competencia / f"lanctos_{empresa}_{competencia}_{sol}.txt"
