"""Normalizador Bancário - documento bancário JÁ EXTRAÍDO → contrato bancário comum.

Desenho:  Documento bancário → extração segura (Agente de Documentos) → reconhecimento de formato → ADAPTADOR BANCÁRIO
          → MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1 → Financeiro → Conciliação

- Biblioteca pura, local e determinística: recebe o dicionário de um arquivo como devolvido pelo extrator (texto por
  página), sem abrir arquivos, sem rede e sem executar conteúdo ativo. A entrada nunca é alterada.
- Separação: o ADAPTADOR só reconhece e lê o leiaute (linhas → movimentos brutos). O NÚCLEO valida (completude, SHA,
  aritmética, saldos de fechamento e saldos diários), gera ids determinísticos e monta o contrato. Novos bancos e leiautes
  entram como novos adaptadores em ADAPTADORES, sem mudar o núcleo nem o Financeiro.
- Reconhecimento SOMENTE pelo conteúdo/estrutura; o nome do arquivo nunca é lido. Nenhum adaptador = FONTE_SEM_ADAPTADOR;
  mais de um = FONTE_AMBIGUA (nunca se escolhe o "mais parecido").
- Moeda em Decimal com 2 casas; nenhuma tolerância. Aritmética que não fecha, saldo diário divergente, linha não
  interpretável ou documento incompleto = BLOQUEIO: nenhum movimento é entregue como confirmado e nada é inventado.

Primeiro adaptador: SANTANDER_EXTRATO_CONSOLIDADO_PJ (Santander Empresas - Extrato Consolidado PJ, texto digital).
"""

import calendar
import datetime as dt
import hashlib
import re
import unicodedata
from decimal import Decimal

VERSAO = "1.0"
CONTRATO = "MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1"
CENTAVO = Decimal("0.01")
INFORMATIVO, ATENCAO, BLOQUEIO = "INFORMATIVO", "ATENCAO", "BLOQUEIO"
NATUREZAS = ("CREDITO", "DEBITO")
# Mesmo conjunto reservado em normalizador_financeiro.CAMPOS_MOVIMENTO_BANCARIO, mais id, saldo_apos e página/linhas.
CAMPOS_MOVIMENTO = ("id", "data", "descricao", "documento", "valor", "natureza", "saldo_apos", "banco", "agencia", "conta",
                    "origem_documento", "sha256_origem", "indice_origem", "pagina", "linhas", "evidencias")

DINHEIRO = r"\d{1,3}(?:\.\d{3})*,\d{2}"


class ErroLeiaute(Exception):
    """Leiaute reconhecido mas não utilizável com segurança (o núcleo transforma em BLOQUEIO)."""
    def __init__(self, codigo, problema, o_que_fazer="Conferir o documento original; nenhum movimento foi inventado.", **extra):
        super().__init__(problema)
        self.codigo, self.problema, self.o_que_fazer, self.extra = codigo, problema, o_que_fazer, extra


def sem_acento(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().upper()


def dinheiro(texto) -> Decimal:
    """'1.234,56' → Decimal('1234.56'). Somente o formato brasileiro com 2 casas (sem float)."""
    if not re.fullmatch(DINHEIRO, texto or ""):
        raise ValueError(f"valor monetário não reconhecido: {texto!r}")
    return Decimal(texto.replace(".", "").replace(",", ".")).quantize(CENTAVO)


def pendencia(nivel, codigo, problema, impacto, o_que_fazer, **extra) -> dict:
    return {"nivel": nivel, "codigo": codigo, "problema": problema, "impacto": impacto, "o_que_fazer": o_que_fazer, **extra}


def paginas_de(arquivo: dict) -> list:
    return list((arquivo.get("conteudo") or {}).get("paginas") or [])


# ================================================================ adaptador 1: Santander Empresas — Extrato Consolidado PJ

class SantanderExtratoConsolidadoPJ:
    nome = "SANTANDER_EXTRATO_CONSOLIDADO_PJ"
    banco = {"nome": "SANTANDER", "codigo": "033"}
    RE_CABECALHO = re.compile(r"^DATA\s+DESCRICAO\s+N\S?\s+DOCUMENTO\s+MOVIMENTOS\s+\(R\$\)\s+SALDO\s+\(R\$\)\s*$")
    RE_SUBCABECALHO = re.compile(r"^CREDITOS\s+DEBITOS\s*$")
    RE_SALDO_EM = re.compile(rf"^SALDO EM (\d{{2}})/(\d{{2}})\s+({DINHEIRO})\s*$")
    RE_PAGINA = re.compile(r"^PAGINA:\s*(\d+)/(\d+)\s*$")
    RE_RESUMO = re.compile(r"^RESUMO\s*-\s*([A-Z]+)/(\d{4})\s*$")
    RE_DATA = re.compile(r"^(\d{2})/(\d{2})\s+(.*)$")
    # final de movimento: <documento ("-" ou número)> <valor>[-] [<saldo>]
    RE_CAUDA = re.compile(rf"(?:^|\s)(-|\d+)\s+({DINHEIRO})(-?)(?:\s+({DINHEIRO}))?\s*$")
    RE_DIARIO = re.compile(rf"^(\d{{2}})((?:\s+{DINHEIRO}){{7}})\s*$")
    RE_LEGENDA = re.compile(r"^([A-Z])\s+-\s+(\S.*)$")
    MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
             "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
    RUIDO = re.compile(r"^(EXTRATO_PJ_|BALP_|PAGINA:|EXTRATO CONSOLIDADO\s*$|[A-Z]+/\d{4}\s*$)")
    TERMINADORES = re.compile(r"^(SALDOS POR PERIODO|[A-Z]\s+-\s+\S|\W?SE SUA EMPRESA)")

    # ---- reconhecimento: TODAS as evidências estruturais combinadas (marca sozinha não basta; nome nunca é lido)
    def reconhece(self, arquivo: dict):
        linhas = [sem_acento(l).strip() for p in paginas_de(arquivo) for l in (p.get("texto") or "").splitlines()]
        texto = "\n".join(linhas)
        evid = {
            "MARCA_SANTANDER": "SANTANDER" in texto,
            "EXTRATO_CONSOLIDADO": "EXTRATO CONSOLIDADO" in texto,
            "SECAO_CONTA_CORRENTE_MOVIMENTACAO": bool(re.search(r"^CONTA CORRENTE\s*\n\s*MOVIMENTACAO\s*$", texto, re.M)),
            "CABECALHO_COLUNAS": any(self.RE_CABECALHO.match(l) for l in linhas),
            "SUBCABECALHO_CREDITOS_DEBITOS": any(self.RE_SUBCABECALHO.match(l) for l in linhas),
            "AGENCIA_E_CONTA": bool(re.search(r"^AGENCIA\s*\n\s*\d{3,5}\s*\n\s*CONTA CORRENTE\s*\n\s*[\d.]+-\d", texto, re.M)),
            "SALDO_EM": sum(bool(self.RE_SALDO_EM.match(l)) for l in linhas) >= 2,
        }
        return sorted(evid) if all(evid.values()) else None

    # ---- leitura do leiaute (sem validação aritmética: isso é do núcleo)
    def ler(self, arquivo: dict) -> dict:
        paginas = paginas_de(arquivo)
        total = (arquivo.get("conteudo") or {}).get("paginas_total")
        for p in paginas:                                   # numeração impressa confere com a ordem recebida
            marcas = [self.RE_PAGINA.match(sem_acento(l).strip()) for l in (p.get("texto") or "").splitlines()]
            marcas = [m for m in marcas if m]
            if not marcas or (int(marcas[0].group(1)), int(marcas[0].group(2))) != (p.get("pagina"), total):
                raise ErroLeiaute("PAGINACAO_NAO_CONFIRMADA", f"Página {p.get('pagina')}: numeração impressa ausente ou diferente da ordem do documento.",
                                  "Enviar o extrato completo (todas as páginas, na ordem).")
        todas = [(p["pagina"], n, l) for p in paginas for n, l in enumerate((p.get("texto") or "").splitlines(), 1)]
        norm = [(pg, n, sem_acento(l).strip(), l.strip()) for pg, n, l in todas]
        cab = {}
        for i, (pg, n, l, _) in enumerate(norm):
            if l == "NOME" and i + 1 < len(norm) and "titular" not in cab:
                cab["titular"] = norm[i + 1][3]
            if l == "AGENCIA" and i + 1 < len(norm) and re.fullmatch(r"\d{3,5}", norm[i + 1][2]):
                cab.setdefault("agencias", set()).add(norm[i + 1][2])
            if l == "CONTA CORRENTE" and i + 1 < len(norm) and re.fullmatch(r"[\d.]+-\d", norm[i + 1][2]):
                cab.setdefault("contas", set()).add(norm[i + 1][2])
            m = self.RE_RESUMO.match(l)
            if m:
                cab.setdefault("periodos", set()).add((m.group(1), m.group(2)))
        if len(cab.get("agencias", ())) != 1 or len(cab.get("contas", ())) != 1:
            raise ErroLeiaute("CONTA_INDETERMINADA", "Agência ou conta ausente ou mais de uma no documento.")
        if len(cab.get("periodos", ())) != 1 or next(iter(cab["periodos"]))[0] not in self.MESES:
            raise ErroLeiaute("PERIODO_INDETERMINADO", "Mês/ano do resumo ausente, ilegível ou mais de um.")
        nome_mes, ano = next(iter(cab["periodos"]))
        mes, ano = self.MESES[nome_mes], int(ano)
        legendas = {m.group(1) for _, _, l, _ in norm if (m := self.RE_LEGENDA.match(l))}

        def data_mov(dd, mm):
            if int(mm) != mes:
                raise ErroLeiaute("DATA_FORA_DO_PERIODO", f"Movimento em {dd}/{mm} fora do período {mes:02d}/{ano}; o ano não é presumido.")
            try:
                return dt.date(ano, mes, int(dd)).isoformat()
            except ValueError:
                raise ErroLeiaute("DATA_INVALIDA", f"Data {dd}/{mm} inexistente.")

        # ---- seção de movimentação: depois do cabeçalho de colunas, em cada página, até um terminador
        movimentos, saldos_em, pendente, data_atual, grupo_aberto, dentro = [], [], None, None, False, False
        nao_interpretadas = []
        for pg, n, l, original in norm:
            if self.RE_CABECALHO.match(l):
                dentro = True
                continue
            if not dentro or not l or self.RE_SUBCABECALHO.match(l) or self.RUIDO.match(l):
                continue
            if self.TERMINADORES.match(l):
                dentro = False
                continue
            m = self.RE_SALDO_EM.match(l)
            if m:
                if pendente:
                    nao_interpretadas.append(pendente)
                    pendente = None
                saldos_em.append({"dia": m.group(1), "mes": m.group(2), "valor": dinheiro(m.group(3)), "pagina": pg, "linha": n})
                grupo_aberto = False
                continue
            if pendente is None:                                     # início de movimento
                md = self.RE_DATA.match(original)
                marcador = None
                if md:
                    data_atual = data_mov(md.group(1), md.group(2))
                    resto = md.group(3).strip()
                    if re.match(r"^[A-Z]\s+\S", resto) and resto[0] in legendas:       # marcador de legenda (ex.: "A")
                        marcador, resto = resto[0], resto[1:].strip()
                    evid = ["DATA_NA_LINHA"]
                else:
                    if data_atual is None or not grupo_aberto:
                        raise ErroLeiaute("DATA_NAO_COMPROVADA", f"Página {pg}, linha {n}: movimento sem data fora de um grupo do dia "
                                          "(o grupo anterior já foi fechado pelo saldo); a data não é herdada.")
                    resto, evid = original, ["DATA_HERDADA_DO_GRUPO"]
                pendente = {"data": data_atual, "partes": [], "pagina": pg, "linha_inicial": n, "evidencias": evid, "marcador": marcador}
                if marcador:
                    pendente["evidencias"].append(f"MARCADOR_LEGENDA_{marcador}")
                linha = resto
            else:
                linha = original                                     # continuação da descrição (inclusive em outra página)
                if pg != pendente["pagina"] and "CONTINUACAO_ENTRE_PAGINAS" not in pendente["evidencias"]:
                    pendente["evidencias"].append("CONTINUACAO_ENTRE_PAGINAS")
            c = self.RE_CAUDA.search(linha)
            if c:
                descricao = linha[:c.start()].strip()
                if descricao:
                    pendente["partes"].append(descricao)
                if not pendente["partes"]:
                    raise ErroLeiaute("DESCRICAO_AUSENTE", f"Página {pg}, linha {n}: valor sem descrição de movimento.")
                movimentos.append({**{k: pendente[k] for k in ("data", "pagina", "linha_inicial", "evidencias", "marcador")},
                                   "linha_final": n, "pagina_final": pg, "descricao": " ".join(pendente["partes"]),
                                   "documento": None if c.group(1) == "-" else c.group(1), "valor": dinheiro(c.group(2)),
                                   "natureza": "DEBITO" if c.group(3) == "-" else "CREDITO",
                                   "saldo_apos": dinheiro(c.group(4)) if c.group(4) else None})
                grupo_aberto = c.group(4) is None                    # saldo impresso fecha o grupo do dia
                pendente = None
            else:
                pendente["partes"].append(linha.strip())
        if pendente:
            nao_interpretadas.append(pendente)
        if nao_interpretadas:
            x = nao_interpretadas[0]
            raise ErroLeiaute("LINHA_NAO_INTERPRETADA", f"Página {x['pagina']}, linha {x['linha_inicial']}: trecho da movimentação sem valor "
                              "identificável; nenhum movimento foi inventado.", quantidade=len(nao_interpretadas))
        if len(saldos_em) < 2:
            raise ErroLeiaute("SALDO_INICIAL_OU_FINAL_AUSENTE", "Saldo inicial e/ou final ('SALDO EM') não localizado na movimentação.")
        ini, fim = saldos_em[0], saldos_em[-1]
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        ano_ini = ano - 1 if int(ini["mes"]) > mes else ano
        # ---- saldos por período (evidência independente)
        diarios, na_secao = [], False
        for pg, n, l, _ in norm:
            if l.startswith("SALDOS POR PERIODO"):
                na_secao = True
                continue
            if na_secao and (m := self.RE_DIARIO.match(l)):
                v = [dinheiro(x) for x in m.group(2).split()]
                diarios.append({"data": dt.date(ano, mes, int(m.group(1))).isoformat(), "saldo_conta_corrente": v[0],
                                "bloqueio_dia": v[1], "bloqueado": v[2], "bloqueio_judicial": v[3], "provisao_encargos": v[4],
                                "investimentos_resgate_automatico": v[5], "saldo_disponivel": v[6], "pagina": pg, "linha": n})
        return {"banco": self.banco, "titular": cab.get("titular"), "agencia": next(iter(cab["agencias"])),
                "conta": next(iter(cab["contas"])), "periodo_inicio": f"{ano}-{mes:02d}-01", "periodo_fim": f"{ano}-{mes:02d}-{ultimo_dia:02d}",
                "saldo_inicial": {"data": dt.date(ano_ini, int(ini["mes"]), int(ini["dia"])).isoformat(), "valor": ini["valor"],
                                  "pagina": ini["pagina"], "linha": ini["linha"]},
                "saldo_final": {"data": dt.date(ano, int(fim["mes"]), int(fim["dia"])).isoformat(), "valor": fim["valor"],
                                "pagina": fim["pagina"], "linha": fim["linha"]},
                "saldos_em_intermediarios": saldos_em[1:-1], "movimentos": movimentos, "saldos_diarios": diarios,
                # neste leiaute o saldo da movimentação inclui o bloqueio do dia: confere com a coluna "Saldo Disponível"
                "saldo_diario_comparavel": "saldo_disponivel"}


# ================================================================ registro de adaptadores (ponto de extensão)
ADAPTADORES = [SantanderExtratoConsolidadoPJ()]


# ================================================================ núcleo
def _base(arquivo, adaptador=None, evidencias=None):
    return {"contrato": CONTRATO, "versao": VERSAO, "adaptador": adaptador, "evidencias_reconhecimento": evidencias or [],
            "origem": {"arquivo": arquivo.get("arquivo"), "sha256": arquivo.get("sha256"), "leitura": arquivo.get("leitura"),
                       "paginas_total": (arquivo.get("conteudo") or {}).get("paginas_total")}}


def _bloqueado(base, *pendencias_, **extra):
    return {**base, "situacao": "BLOQUEADO", "movimentos": [], "pendencias": list(pendencias_), **extra,
            "resumo": {"movimentos": 0, "bloqueios": sum(p["nivel"] == BLOQUEIO for p in pendencias_)}}


def normalizar(arquivo: dict) -> dict:
    """Documento bancário extraído → MOVIMENTOS_BANCARIOS_NORMALIZADOS_V1 (ou BLOQUEADO com o motivo exato)."""
    candidatos = [(a, ev) for a in ADAPTADORES if (ev := a.reconhece(arquivo))]
    base = _base(arquivo)
    if not candidatos:
        return _bloqueado(base, pendencia(BLOQUEIO, "FONTE_SEM_ADAPTADOR", "Nenhum leitor bancário reconheceu a estrutura deste documento.",
                                          "Nenhum movimento bancário foi lido; nada foi inferido.",
                                          "Enviar o extrato em formato suportado ou aguardar o leitor deste banco/leiaute."))
    if len(candidatos) > 1:
        return _bloqueado(base, pendencia(BLOQUEIO, "FONTE_AMBIGUA", "Mais de um leitor bancário reconhece este documento: "
                                          + ", ".join(a.nome for a, _ in candidatos) + ".",
                                          "Nenhum movimento foi lido; o sistema não escolhe um leitor em silêncio.",
                                          "Encaminhar ao Supervisor para definir o leitor."))
    adaptador, evidencias = candidatos[0]
    base = _base(arquivo, adaptador.nome, evidencias)
    sha = arquivo.get("sha256")
    conteudo = arquivo.get("conteudo") or {}
    if not sha:
        return _bloqueado(base, pendencia(BLOQUEIO, "ORIGEM_SEM_SHA", "Documento sem impressão digital (SHA-256) do original.",
                                          "A origem não pode ser rastreada; nada foi lido.", "Refazer a etapa de Documentos."))
    paginas = paginas_de(arquivo)
    if (arquivo.get("leitura") != "EXTRAIDO_PDF" or not conteudo.get("paginas_total") or len(paginas) != conteudo["paginas_total"]
            or [p.get("pagina") for p in paginas] != list(range(1, conteudo["paginas_total"] + 1))
            or any(p.get("situacao", "TEXTO") != "TEXTO" for p in paginas) or conteudo.get("truncado")
            or conteudo.get("paginas_requer_ocr")):
        return _bloqueado(base, pendencia(BLOQUEIO, "DOCUMENTO_INCOMPLETO", "Documento incompleto, truncado, fora de ordem ou com páginas sem texto.",
                                          "Nenhum movimento foi lido; leitura parcial não é aproveitada.",
                                          "Enviar o extrato completo em PDF digital."))
    try:
        bruto = adaptador.ler(arquivo)
    except ErroLeiaute as e:
        return _bloqueado(base, pendencia(BLOQUEIO, e.codigo, e.problema, "Nenhum movimento bancário deste documento foi entregue.",
                                          e.o_que_fazer, **e.extra))
    return _montar(base, bruto, arquivo)


def _montar(base, bruto, arquivo):
    sha, nome = arquivo.get("sha256"), arquivo.get("arquivo")
    banco, agencia, conta = bruto["banco"], bruto["agencia"], bruto["conta"]
    pend = []
    movimentos = []
    for i, m in enumerate(bruto["movimentos"], 1):
        movimentos.append({
            "id": "BM-" + hashlib.sha256(f"{sha}|{m['pagina']}|{m['linha_inicial']}".encode()).hexdigest()[:12].upper(),
            "data": m["data"], "descricao": m["descricao"], "documento": m["documento"], "valor": m["valor"],
            "natureza": m["natureza"], "saldo_apos": m["saldo_apos"], "banco": banco, "agencia": agencia, "conta": conta,
            "origem_documento": nome, "sha256_origem": sha, "indice_origem": i, "pagina": m["pagina"],
            "linhas": {"pagina_inicial": m["pagina"], "linha_inicial": m["linha_inicial"],
                       "pagina_final": m["pagina_final"], "linha_final": m["linha_final"]},
            "evidencias": list(m["evidencias"])})
    creditos = sum((m["valor"] for m in movimentos if m["natureza"] == "CREDITO"), Decimal("0.00"))
    debitos = sum((m["valor"] for m in movimentos if m["natureza"] == "DEBITO"), Decimal("0.00"))
    ini, fim = bruto["saldo_inicial"]["valor"], bruto["saldo_final"]["valor"]
    calculado = ini + creditos - debitos
    aritmetica = {"saldo_inicial": ini, "total_creditos": creditos, "total_debitos": debitos, "saldo_calculado": calculado,
                  "saldo_final_informado": fim, "diferenca": calculado - fim,
                  "situacao": "CONSISTENTE" if calculado == fim else "DIVERGENTE", "tolerancia": Decimal("0.00")}
    if calculado != fim:
        pend.append(pendencia(BLOQUEIO, "ARITMETICA_DIVERGENTE",
                              f"Saldo inicial {ini} + créditos {creditos} − débitos {debitos} = {calculado} ≠ saldo final {fim} (diferença {calculado - fim}).",
                              "O extrato não fecha; os movimentos não são entregues como confirmados.",
                              "Conferir se faltam páginas ou linhas no documento original."))
    # saldos impressos ao longo da movimentação (fechamento de cada grupo/dia)
    corrente, fechamentos, div_fech = ini, 0, []
    saldo_fim_dia = {}
    for m in movimentos:
        corrente += m["valor"] if m["natureza"] == "CREDITO" else -m["valor"]
        m["saldo_reconstruido"] = corrente
        saldo_fim_dia[m["data"]] = corrente
        if m["saldo_apos"] is not None:
            fechamentos += 1
            if m["saldo_apos"] != corrente:
                div_fech.append({"movimento": m["id"], "data": m["data"], "informado": m["saldo_apos"], "reconstruido": corrente})
            else:
                m["evidencias"].append("SALDO_IMPRESSO_CONFERE")
    if div_fech:
        pend.append(pendencia(BLOQUEIO, "SALDO_IMPRESSO_DIVERGENTE", f"{len(div_fech)} saldo(s) impresso(s) na movimentação diferem do saldo reconstruído.",
                              "Leitura não confiável; os movimentos não são entregues como confirmados.",
                              "Conferir o documento original.", divergencias=div_fech))
    # saldos por período (evidência independente)
    campo = bruto.get("saldo_diario_comparavel", "saldo_disponivel")
    diarios = bruto.get("saldos_diarios") or []
    div_dia, conferidos, internos = [], 0, []
    for d in diarios:
        componentes = (d["saldo_conta_corrente"] + d["bloqueio_dia"] - d["bloqueado"] - d["bloqueio_judicial"]
                       - d["provisao_encargos"] + d["investimentos_resgate_automatico"])
        if componentes != d["saldo_disponivel"]:
            internos.append(d["data"])
        reconstruido = saldo_fim_dia.get(d["data"])
        if reconstruido is None or reconstruido != d[campo]:
            div_dia.append({"data": d["data"], "informado": d[campo], "reconstruido": reconstruido})
        else:
            conferidos += 1
    dias_sem_linha = sorted(set(saldo_fim_dia) - {d["data"] for d in diarios}) if diarios else []
    if div_dia or internos:
        pend.append(pendencia(BLOQUEIO, "SALDO_DIARIO_DIVERGENTE",
                              f"Saldos por período: {len(div_dia)} dia(s) divergente(s) do saldo reconstruído; {len(internos)} linha(s) com soma interna inconsistente.",
                              "Leitura não confiável; os movimentos não são entregues como confirmados.",
                              "Conferir o documento original.", datas=[x["data"] for x in div_dia], datas_soma_interna=internos))
    if not diarios:
        pend.append(pendencia(ATENCAO, "SALDOS_DIARIOS_AUSENTES", "Documento sem tabela de saldos diários.",
                              "A segunda validação independente não foi feita (a aritmética do período foi).", "Nenhuma, se o leiaute não tiver a tabela."))
    if dias_sem_linha:
        pend.append(pendencia(ATENCAO, "DIA_SEM_SALDO_DIARIO", f"{len(dias_sem_linha)} dia(s) com movimento sem linha em 'Saldos por Período'.",
                              "Esses dias não tiveram a segunda validação.", "Conferir no original, se necessário.", datas=dias_sem_linha))
    validacao_diaria = {"comparado_com": campo, "dias_informados": len(diarios), "dias_conferidos": conferidos,
                        "divergencias": div_dia, "linhas_soma_interna_inconsistente": internos, "dias_com_movimento_sem_linha": dias_sem_linha,
                        "situacao": "SEM_TABELA" if not diarios else "CONSISTENTE" if not (div_dia or internos) else "DIVERGENTE"}
    bloqueio = any(p["nivel"] == BLOQUEIO for p in pend)
    for m in movimentos:
        m.pop("saldo_reconstruido", None)
    resultado = {**base, "situacao": "BLOQUEADO" if bloqueio else ("NORMALIZADO_COM_PENDENCIAS" if pend else "NORMALIZADO"),
                 "banco": banco, "titular": bruto.get("titular"), "agencia": agencia, "conta": conta,
                 "periodo_inicio": bruto["periodo_inicio"], "periodo_fim": bruto["periodo_fim"],
                 "saldo_inicial": bruto["saldo_inicial"], "saldo_final": bruto["saldo_final"],
                 "validacao_aritmetica": aritmetica,
                 "validacao_saldos_impressos": {"conferidos": fechamentos - len(div_fech), "divergencias": div_fech},
                 "validacao_saldos_diarios": validacao_diaria,
                 "movimentos": [] if bloqueio else movimentos,
                 "movimentos_nao_confirmados": movimentos if bloqueio else [],
                 "pendencias": pend,
                 "resumo": {"movimentos": len(movimentos), "creditos": sum(m["natureza"] == "CREDITO" for m in movimentos),
                            "debitos": sum(m["natureza"] == "DEBITO" for m in movimentos), "total_creditos": creditos,
                            "total_debitos": debitos, "saldo_inicial": ini, "saldo_final": fim, "saldo_calculado": calculado,
                            "diferenca": calculado - fim, "saldos_diarios_conferidos": conferidos,
                            "bloqueios": sum(p["nivel"] == BLOQUEIO for p in pend)}}
    return resultado


def para_json(obj):
    """Cópia serializável: Decimal vira texto com duas casas ('1234.56'). Nunca converte para float."""
    if isinstance(obj, Decimal):
        return f"{obj:.2f}"
    if isinstance(obj, dict):
        return {k: para_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [para_json(v) for v in obj]
    return obj
