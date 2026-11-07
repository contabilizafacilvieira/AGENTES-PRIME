"""AGENTE DE IMPORTAÇÃO · SOMENTE VGROW · fechamento das importações por conta e ordem (Capital Trade).

ESPECÍFICO DA VGROW. Contas, percentuais, documentos e decisões abaixo NÃO valem para outras empresas, áreas ou tipos
de importação. Fonte: REGRAS_Vgrow_Importacoes.md (pasta externa "Agente VGrow", validadas em 30/10/2026),
transcritas sem recriar nem generalizar o processo.

Quem executa: SOMENTE o Coordenador (API local), depois da etapa de Documentos de uma SOL PILOTO da VGROW e por ação
do Supervisor. Nunca é acionado pelo Agente de Documentos nem pelo navegador.

Entradas:
- documentos do lote, lidos pelo extrator (canal homologado): Comparativo (.xlsx, colunas NUMERÁRIO/REAL) e
  Numerário (.pdf com texto);
- campos INFORMADOS PELO SUPERVISOR por processo (decisão de 31/10/2026: o "Documentos.pdf" — extrato da DUIMP e NFs
  da Capital Trade — não tem texto legível e a leitura visual é proibida): fob, frete, chegada (AAAA-MM-DD), fatura,
  nfs (números das NFs da Capital Trade) e icms_nf (ICMS destacado nas NFs).

Saída (JSON no stdout + arquivos na pasta de saída do runtime): processos fechados, pendentes, documentos ausentes,
valores (com origem), cálculos, lançamentos, alertas, divergências, TXT do Domínio, planilha de conferência e a
validação débito = crédito. Tudo em SIMULAÇÃO: nada é colocado em LIBERADOS nem importado no Domínio.

Uso:
  .venv/Scripts/python.exe -I AGENTES/IMPORTACAO/ferramentas/importacao_vgrow.py --sol SOL-AAAA-NNNNNN
      --competencia AAAA-MM --pasta "<pasta do lote, relativa a CLIENTES/VGROW>" --informados <json> --saida <pasta>
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from decimal import Decimal as D, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
EXTRATOR = RAIZ / "AGENTES" / "DOCUMENTOS" / "ferramentas" / "extrair_documentos.py"
EMPRESA = "VGROW"
VERSAO = "1.0"

# ---- REGRAS_Vgrow_Importacoes.md §4 (percentuais fixos) e §7 (layout)
IRRF, CRF, DESCONTO_ICMS = D("0.015"), D("0.0465"), D("0.5")
INICIO_REGRAS = "2026-09"            # §5: chegada antes de set/26 → perguntar ao usuário
CONTAS = {10084: ("1.1.3.05.000003", "ADIANTAMENTO ADUANEIRO"), 10001: ("2.1.3.01.000001", "FORNECEDORES"),
          29: ("1.1.3.08.000001", "IPI A RECUPERAR"), 30: ("1.1.3.08.000002", "ICMS A RECUPERAR"),
          36: ("1.1.3.08.000008", "COFINS RETIDO A COMPENSAR"), 37: ("1.1.3.08.000009", "PIS RETIDO A COMPENSAR"),
          55: ("1.1.5.01.000001", "MERCADORIAS PARA REVENDA"), 10010: ("2.1.3.01.000002", "FORNECEDORES ESTRANGEIROS"),
          178: ("2.1.4.01.000008", "IRRF A RECOLHER"), 182: ("2.1.4.01.000012", "CRF A RECOLHER"),
          434: ("3.1.3.01.000003", "DESCONTOS FINANCEIROS OBTIDOS"), 470: ("4.1.7.01.000001", "CUSTOS DAS MERCADORIAS VENDIDAS")}
CAMPOS_INFORMADOS = ("fob", "frete", "chegada", "fatura", "nfs", "icms_nf")


def r2(x) -> D:
    return D(str(x)).quantize(D("0.01"), ROUND_HALF_UP)


def norm(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper().strip()


def fmt_txt(v: D) -> str:
    """§7: vírgula decimal, sem separador de milhar (mesma formatação do gerador validado)."""
    s = format(v.normalize(), "f") if v != v.to_integral() else str(int(v))
    return s.replace(".", ",")


def processo_de(nome: str):
    m = re.search(r"OCCT\s*0*(\d{4,6})\D{0,3}(\d{2})(?!\d)", nome, re.I)
    return f"OCCT{m.group(1)}/{m.group(2)}" if m else None


def tipo_de(nome: str, extensao: str) -> str:
    n = norm(nome)
    if extensao in (".xlsx", ".xlsm"):
        return "comparativo" if "COMPARATIVO" in n else "prestacao_de_contas"
    if extensao == ".pdf":
        for chave, tipo in (("NUMERARIO", "numerario"), ("DOCUMENTOS", "documentos"), ("REEMBOLSO", "reembolso")):
            if chave in n:
                return tipo
    return "outro"


# ---------------------------------------------------------------- leitura (somente pelo extrator)

def extrair(pasta: str) -> list:
    p = subprocess.run([sys.executable, "-I", str(EXTRATOR), "--empresa", EMPRESA, "--pasta", pasta, "--completo"],
                       cwd=RAIZ, capture_output=True, encoding="utf-8")
    if p.returncode != 0:
        raise SystemExit(json.dumps({"erro": "EXTRATOR", "mensagem": (p.stderr or "")[-300:]}, ensure_ascii=False))
    return json.loads(p.stdout)["arquivos"]


def ler_comparativo(arquivo: dict):
    """Comparativo: colunas NUMERÁRIO / REAL pelo cabeçalho; linhas pelo rótulo (primeira célula de texto da linha)."""
    if arquivo.get("leitura") != "EXTRAIDO_PLANILHA":
        return None, [f"Comparativo não extraído ({arquivo.get('leitura')})."]
    linhas = [l["valores"] for aba in arquivo["conteudo"]["abas"] if not aba.get("oculta") for l in aba["linhas"]]
    cab = next((v for v in linhas if any(norm(x) == "NUMERARIO" for x in v if x is not None)
                and any(norm(x) == "REAL" for x in v if x is not None)), None)
    if not cab:
        return None, ["Comparativo sem cabeçalho NUMERÁRIO/REAL."]
    i_num = next(i for i, x in enumerate(cab) if x is not None and norm(x) == "NUMERARIO")
    i_real = next(i for i, x in enumerate(cab) if x is not None and norm(x) == "REAL")

    def numero(x):
        if x is None or isinstance(x, bool) or (isinstance(x, str) and not x.strip()):
            return None
        try:
            return D(str(x))
        except InvalidOperation:
            return None

    def rotulo(v):
        return next((norm(x) for x in v if isinstance(x, str) and x.strip()), "")

    def valores_de(prefixos, indice, exato=False):
        achados = []
        for v in linhas:
            r = rotulo(v)
            if (r in prefixos) if exato else any(r.startswith(p) for p in prefixos):
                n = numero(v[indice]) if len(v) > indice else None
                if n is not None:
                    achados.append(n)
        return achados

    def depois_do_rotulo(prefixo):
        for v in linhas:
            if rotulo(v).startswith(prefixo):
                n = [numero(x) for x in v if numero(x) is not None]
                return n[0] if n else None
        return None

    problemas, valores = [], {}
    campos = {"ipi": (["IMPOSTO SOBRE PRODUTOS", "IMPOSTOS SOBRE PRODUTOS", "IMPOSTO SOBRE PRODTOS", "IMPOSTOS SOBRE PRODTOS"], False),
              "difipi": (["DIFERENCA I.P.I", "DIFERENCA DE IPI", "DIFERENCA IPI"], False),
              "pis": (["PIS"], True), "cof": (["COFINS"], True), "icms_cobrado": (["ICMS"], True)}
    for campo, (prefixos, exato) in campos.items():
        achados = valores_de(prefixos, i_real, exato)
        if len([a for a in achados if a != 0]) > 1:
            problemas.append(f"Comparativo com mais de uma linha não zerada para {campo}.")
        valores[campo] = r2(sum(achados)) if achados else (D("0.00") if campo == "difipi" else None)
    # §4: serviço BRUTO = coluna NUMERÁRIO. Dois leiautes de comparativo: "Honorários" + "Serviços Capital Trade" ou uma
    # única linha "Serviço de Desembaraço Aduaneiro". Os dois juntos = ambíguo → pendência.
    honorarios = valores_de(["HONORARIOS"], i_num)
    servicos = valores_de(["SERVICOS CAPITAL TRADE"], i_num)
    desembaraco = valores_de(["SERVICO DE DESEMBARACO"], i_num)
    if honorarios and desembaraco:
        problemas.append("Comparativo com 'Honorários' e 'Serviço de Desembaraço' ao mesmo tempo: serviço bruto ambíguo.")
        valores["serv"] = None
    elif honorarios:
        valores["serv"] = r2(sum(honorarios) + sum(servicos))
    else:
        valores["serv"] = r2(sum(desembaraco)) if len(desembaraco) == 1 else None
    total = valores_de(["TOTAL"], i_real, exato=True)
    valores["total_real"] = r2(total[0]) if len(total) == 1 else None
    saldo = depois_do_rotulo("SALDO RELATORIO DE PRO")
    valores["saldo"] = r2(saldo) if saldo is not None else None
    pago = depois_do_rotulo("VALOR PAGO EM NUMER")
    valores["numerario_pago"] = r2(pago) if pago is not None else None
    faltando = [k for k in ("ipi", "pis", "cof", "icms_cobrado", "serv", "total_real", "saldo") if valores.get(k) is None]
    if faltando:
        problemas.append(f"Comparativo sem os campos: {', '.join(faltando)}.")
    return valores, problemas


def ler_prestacao(arquivo: dict):
    """Prestação de contas (relatório da Capital Trade, .xlsx): processo ("Registro:"), linhas "ENTRADA DE NUMERÁRIO"
    (depósito efetivo), "TOTAL(1):" e "LISTAGEM DE NOTAS FISCAIS" (nº, valor, ICMS). Nada além disso é usado."""
    if arquivo.get("leitura") != "EXTRAIDO_PLANILHA":
        return None
    linhas = [[x for x in l["valores"]] for aba in arquivo["conteudo"]["abas"] if not aba.get("oculta") for l in aba["linhas"]]

    def numero(x):
        try:
            return r2(x) if x not in (None, "") and not isinstance(x, bool) else None
        except InvalidOperation:
            return None

    occt, entradas, total1, nfs, na_lista = None, [], None, [], False
    for v in linhas:
        textos = [norm(x) for x in v if isinstance(x, str) and x.strip()]
        nums = [numero(x) for x in v if numero(x) is not None and not isinstance(x, str)]
        if textos and textos[0].startswith("REGISTRO"):
            m = next((re.search(r"OCCT\s*0*(\d{4,6})\D{0,3}(\d{2})", str(x), re.I) for x in v if isinstance(x, str) and "OCCT" in x.upper()), None)
            occt = f"OCCT{m.group(1)}/{m.group(2)}" if m else occt
        elif textos and textos[0] == "ENTRADA DE NUMERARIO" and nums:
            entradas.append(nums[0])
        elif textos and textos[0].startswith("TOTAL(1)") and nums:
            total1 = nums[0]
        elif textos and textos[0].startswith("NF. NUMERO"):
            na_lista = True
            continue
        if na_lista:
            primeiro = v[0] if v else None
            if primeiro is not None and re.fullmatch(r"\d{1,9}", str(primeiro).split(".")[0]) and len(nums) >= 3:
                nfs.append((str(int(float(primeiro))), nums[1], nums[2]))
            elif any(x not in (None, "") for x in v):
                na_lista = False
    return {"occt": occt, "entradas": entradas, "total1": total1, "nfs": nfs}


def ler_numerario(arquivo: dict):
    if arquivo.get("leitura") != "EXTRAIDO_PDF":
        return None
    texto = "\n".join(p.get("texto", "") for p in arquivo["conteudo"]["paginas"])
    m = re.search(r"Total a pagar para CAPITAL TRADE:\s*R\$\s*([\d.]+,\d{2})", texto.replace("\xa0", " "), re.I)
    return r2(m.group(1).replace(".", "").replace(",", ".")) if m else None


# ---------------------------------------------------------------- regras de lançamento (§4) e data (§5)

def lancamentos(v: dict) -> list:
    s, serv, icms = v["saldo"], v["serv"], v["icms_nf"]
    irrf, crf, desc = r2(serv * IRRF), r2(serv * CRF), r2(icms * DESCONTO_ICMS)
    linhas = [(10084, "D", s, " - SALDO A RECEBER")] if s >= 0 else [(10001, "C", -s, " - SALDO A PAGAR")]
    linhas += [(10084, "C", v["num"], ""), (29, "D", v["ipi"] + v["difipi"], ""), (30, "D", icms, ""),
               (36, "D", v["cof"], ""), (37, "D", v["pis"], ""), (55, "D", v["fob"], ""), (55, "D", v["frete"], " - FRETE"),
               (55, "D", None, " - CUSTO"), (10010, "C", v["fob"], ""), (10010, "C", v["frete"], " - FRETE"),
               (178, "C", irrf, " - capital trade"), (182, "C", crf, " - capital trade"), (434, "C", desc, " - DESCONTO ICMS"),
               (470, "D", serv, " - capital trade")]
    credito = sum(x for _, dc, x, _ in linhas if dc == "C")
    debito = sum(x for _, dc, x, _ in linhas if dc == "D" and x is not None)
    return [(conta, dc, credito - debito if x is None else x, sufixo) for conta, dc, x, sufixo in linhas]


def identificacao(docs: list, proc: str) -> str:
    """Processo como na referência ("GG 260005007"): número GG do nome dos arquivos; sem ele, a Ref. Capital Trade."""
    for d in docs:
        m = re.search(r"GG\s*_?(\d{9})", d["nome"], re.I)
        if m:
            return f"GG {m.group(1)}"
    return proc


def processar(sol: str, competencia: str, arquivos: list, informados: dict, ja_lancados: list = (), aceites: dict = None) -> dict:
    grupos, sem_processo = {}, []
    for a in arquivos:
        nome = Path(a["arquivo"]).name
        proc = processo_de(nome)
        if not proc:
            sem_processo.append(nome)
            continue
        grupos.setdefault(proc, []).append(dict(a, nome=nome, tipo=tipo_de(nome, a["extensao"])))

    fechados, pendentes, alertas, divergencias, aguardando_aceite = [], [], [], [], []
    for proc in sorted(grupos):
        docs = grupos[proc]
        por_tipo = {}
        for d in docs:
            por_tipo.setdefault(d["tipo"], []).append(d)
        motivos, alertas_p = [], []
        anterior = next((x for x in ja_lancados if x.get("occt") == proc), None)
        if anterior:     # CLAUDE.md / §6: não gerar de novo processo já lançado (risco de duplicidade)
            motivos.append(f"Processo já lançado na {anterior['sol']} (competência {anterior.get('competencia')}): não gerar de novo.")
        ausentes = [t for t in ("comparativo", "numerario", "documentos") if t not in por_tipo]   # §3 obrigatórios
        if ausentes:
            motivos.append("Documento obrigatório ausente: " + ", ".join(ausentes) + ".")
        for t in ("comparativo", "numerario", "documentos"):
            if len(por_tipo.get(t, [])) > 1:
                motivos.append(f"Mais de um arquivo do tipo {t} no processo.")
        inf = informados.get(proc) or {}
        faltam_inf = [c for c in CAMPOS_INFORMADOS if inf.get(c) in (None, "", [])]
        if faltam_inf:
            motivos.append("Campos da DUIMP/NFs não informados pelo Supervisor: " + ", ".join(faltam_inf) + ".")
        valores, origem = {}, {}
        if "comparativo" in por_tipo and len(por_tipo["comparativo"]) == 1:
            comp, problemas = ler_comparativo(por_tipo["comparativo"][0])
            motivos += problemas
            if comp:
                valores.update({k: x for k, x in comp.items() if x is not None})
                origem.update({k: f"EXTRAIDO: {por_tipo['comparativo'][0]['nome']}" for k in comp if comp[k] is not None})
        num_pdf = ler_numerario(por_tipo["numerario"][0]) if len(por_tipo.get("numerario", [])) == 1 else None
        if "numerario" in por_tipo and num_pdf is None:
            motivos.append("Numerário sem 'Total a pagar para CAPITAL TRADE' legível.")
        if not faltam_inf:
            try:
                for c in ("fob", "frete", "icms_nf"):
                    valores[c] = r2(inf[c])
                    if valores[c] < 0:
                        raise ValueError
                chegada = dt.date.fromisoformat(inf["chegada"])
                valores["fatura"] = str(inf["fatura"]).strip()
                valores["nfs"] = sorted({str(n).strip() for n in inf["nfs"]}, key=int)
            except (ValueError, InvalidOperation, TypeError, KeyError):
                motivos.append("Campos informados pelo Supervisor inválidos.")
                chegada = None
            for c in CAMPOS_INFORMADOS:    # origem consolidada pelo Coordenador (reconhecido/conferido/corrigido/informado)
                origem[c] = (inf.get("_origem") or {}).get(c, "INFORMADO_PELO_SUPERVISOR")
        else:
            chegada = None
        # §4 numerário: padrão = numerário do PDF. Substituído SOMENTE quando a Prestação de contas do MESMO processo
        # registra explicitamente "ENTRADA DE NUMERÁRIO" (depósito efetivo) diferente. Solicitação, total e saldo não são
        # depósito. Ambíguo/conflitante → decisão do Supervisor (decisão de 31/10/2026).
        acompanhamentos = []
        prestacoes = por_tipo.get("prestacao_de_contas", [])
        prest = ler_prestacao(prestacoes[0]) if len(prestacoes) == 1 else None
        if len(prestacoes) > 1:
            motivos.append("Mais de uma Prestação de contas no processo: depósito efetivo e NFs ambíguos — decisão do Supervisor.")
        if prest and prest.get("occt") and prest["occt"] != proc:
            motivos.append(f"Prestação de contas é do processo {prest['occt']}, não de {proc} — decisão do Supervisor.")
            prest = None
        numerario = {"pdf": str(num_pdf) if num_pdf is not None else None, "deposito_prestacao": None, "pago_comparativo":
                     str(valores["numerario_pago"]) if valores.get("numerario_pago") is not None else None, "usado": None, "motivo": None}
        if num_pdf is not None:
            valores["num"], origem["num"] = num_pdf, f"EXTRAIDO: numerário PDF ({por_tipo['numerario'][0]['nome']})"
            numerario.update(usado=str(num_pdf), motivo="Padrão da regra: numerário do PDF.")
            if prest is not None:
                entradas = prest["entradas"]
                if len(entradas) > 1:
                    motivos.append(f"Prestação de contas com {len(entradas)} linhas 'ENTRADA DE NUMERÁRIO': depósito efetivo ambíguo — decisão do Supervisor.")
                elif len(entradas) == 1:
                    deposito = entradas[0]
                    numerario["deposito_prestacao"] = str(deposito)
                    if deposito != num_pdf:
                        valores["num"] = deposito
                        origem["num"] = f"EXTRAIDO: Prestação de contas ({prestacoes[0]['nome']}), ENTRADA DE NUMERÁRIO"
                        numerario.update(usado=str(deposito), motivo=f"Prestação de contas registra ENTRADA DE NUMERÁRIO {deposito}, diferente do "
                                                                       f"numerário do PDF {num_pdf} (regra §4: usar o depositado e alertar).")
                        alertas_p.append(f"{proc}: numerário PDF {num_pdf} substituído pelo depósito efetivo {deposito} "
                                         f"(Prestação de contas, ENTRADA DE NUMERÁRIO).")
                else:
                    acompanhamentos.append("Prestação de contas sem 'ENTRADA DE NUMERÁRIO': depósito efetivo não declarado; usado o numerário do PDF (padrão).")
            elif not prestacoes:
                acompanhamentos.append("Prestação de contas não recebida (documento opcional): depósito efetivo não confirmado; usado o numerário do PDF (padrão da regra).")
            pago = valores.get("numerario_pago")
            if pago is not None and pago != valores["num"]:      # visível como alerta, sem tolerância
                alertas_p.append(f"{proc}: 'VALOR PAGO EM NUMERÁRIO' do comparativo = {pago}; numerário usado = {valores['num']} "
                                 f"({origem['num']}). Diferença {valores['num'] - pago}.")
        # Total realizado: a regra usa o total REAL do comparativo; TOTAL(1) da Prestação diferente → alerta com as fontes
        if prest and prest.get("total1") is not None and valores.get("total_real") is not None and prest["total1"] != valores["total_real"]:
            alertas_p.append(f"{proc}: total REAL do comparativo = {valores['total_real']} (usado, regra §4); TOTAL(1) da Prestação de contas = "
                             f"{prest['total1']}. Diferença {prest['total1'] - valores['total_real']}.")
        # NFs e ICMS: verificação textual pela LISTAGEM DE NOTAS FISCAIS da Prestação (quando houver)
        verificacao_nfs = None
        if prest and prest["nfs"] and not faltam_inf and "nfs" in valores:
            lista = {n for n, _, _ in prest["nfs"]}
            icms_lista = sum((i for _, _, i in prest["nfs"]), D("0"))
            iguais = lista == set(valores["nfs"]) and icms_lista == valores["icms_nf"]
            verificacao_nfs = {"prestacao_nfs": sorted(lista, key=int), "prestacao_icms": str(icms_lista), "confere": iguais}
            if iguais:
                origem["nfs"] += " · VERIFICADO na Prestação de contas"
                origem["icms_nf"] += " · VERIFICADO na Prestação de contas"
            else:
                motivos.append(f"NFs/ICMS divergem da Prestação de contas (lista {sorted(lista, key=int)}, ICMS {icms_lista}; usados "
                               f"{valores['nfs']}, ICMS {valores['icms_nf']}) — decisão do Supervisor.")
        # Data (§5): chegada em mês anterior → PENDÊNCIA ao Supervisor (decisão de 31/10/2026); posterior → pendência
        if chegada:
            mes = chegada.strftime("%Y-%m")
            if mes < INICIO_REGRAS:
                motivos.append(f"Chegada {chegada:%d/%m/%Y} antes de set/26: regra manda perguntar ao Supervisor.")
            elif mes < competencia:
                motivos.append(f"Chegada {chegada:%d/%m/%Y} em mês anterior à competência {competencia}: o Supervisor confirma se "
                               "já foi lançado (regra: se não foi, lançar no dia 01 da competência).")
            elif mes > competencia:
                motivos.append(f"Chegada {chegada:%d/%m/%Y} posterior à competência {competencia}.")
        if "reembolso" not in por_tipo:
            acompanhamentos.append("Comprovante de reembolso não recebido (documento opcional na regra; não bloqueia).")
        obrig = ("num", "saldo", "total_real", "ipi", "difipi", "pis", "cof", "serv", "fob", "frete", "icms_nf")
        calculos, aceite_pedido = {}, None
        documentos = [{"arquivo": d["nome"], "tipo": d["tipo"], "leitura": d.get("leitura"), "sha256": d.get("sha256")} for d in docs]
        if not motivos and all(k in valores for k in obrig):
            # ICMS: dois campos DIFERENTES, apresentados lado a lado, sem julgamento de igualdade e sem tolerância
            calculos["icms_cobrado_comparativo"] = valores["icms_cobrado"]
            calculos["icms_destacado_nfs"] = valores["icms_nf"]
            calculos["desconto_icms_50_sobre_destacado"] = r2(valores["icms_nf"] * DESCONTO_ICMS)
            # Checagem exata; diferente de zero → aceite explícito do Supervisor para ESTES valores e documentos
            checagem = valores["num"] - valores["saldo"] - valores["total_real"]
            calculos["checagem_numerario_saldo_total_real"] = checagem
            if checagem != 0:
                base = {"processo": proc, "num": str(valores["num"]), "saldo": str(valores["saldo"]), "total_real": str(valores["total_real"]),
                        "diferenca": str(checagem), "fontes": {k: origem.get(k) for k in ("num", "saldo", "total_real")},
                        "documentos": sorted((d["arquivo"], d.get("sha256")) for d in documentos)}
                chave = hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
                aceite = (aceites or {}).get(proc)
                if aceite and aceite.get("chave") == chave:
                    alertas_p.append(f"{proc}: diferença numerário − saldo − total REAL = {checagem} ACEITA pelo Supervisor em {aceite.get('em')}.")
                    calculos["aceite_supervisor"] = f"{aceite.get('em')} · chave {chave[:12]}"
                else:
                    aceite_pedido = dict(base, chave=chave, motivo=("Aceite anterior não vale para os valores/documentos atuais."
                                                                     if aceite else "Diferença diferente de zero: requer aceite explícito do Supervisor."))
        elif not motivos:
            motivos.append("Valores obrigatórios não obtidos: " + ", ".join(k for k in obrig if k not in valores) + ".")
        if valores.get("saldo") is not None and valores["saldo"] > 0:
            acompanhamentos.append(f"Saldo a receber {valores['saldo']} lançado em 10084 (SALDO A RECEBER, regra §4): acompanhar a liquidação "
                                   "(devolução/compensação); comprovante de reembolso é opcional.")
        elif valores.get("saldo") is not None and valores["saldo"] < 0:
            acompanhamentos.append(f"Saldo a pagar {-valores['saldo']} lançado em 10001 (SALDO A PAGAR, regra §4): acompanhar o pagamento.")
        alertas += alertas_p
        comum = {"processo": proc, "identificacao": identificacao(docs, proc), "documentos": documentos, "numerario": numerario,
                 "verificacao_nfs": verificacao_nfs, "alertas": alertas_p, "acompanhamentos": acompanhamentos,
                 "chegada": chegada.strftime("%d/%m/%Y") if chegada else None}
        if motivos:
            pendentes.append(dict(comum, motivos=motivos, documentos_ausentes=ausentes, classe="BLOQUEIO",
                                  valores={k: str(x) if isinstance(x, D) else x for k, x in valores.items()}))
            continue
        ls = lancamentos(valores)
        debito = sum(x for _, dc, x, _ in ls if dc == "D")
        credito = sum(x for _, dc, x, _ in ls if dc == "C")
        custo = next(x for _, _, x, sx in ls if sx == " - CUSTO")
        if custo <= 0 or debito != credito:      # D = C é validação separada e obrigatória (aceite não a substitui)
            divergencias.append(f"{proc}: custo de fechamento {custo} / D {debito} × C {credito}: valores incoerentes.")
            pendentes.append(dict(comum, motivos=[f"Custo de fechamento {custo} ≤ 0 ou débito ≠ crédito: valores incoerentes."],
                                  documentos_ausentes=[], classe="BLOQUEIO"))
            continue
        historico = f"{valores['fatura']} - NF'S {'/'.join(valores['nfs'])}"          # §6
        calculos.update({"irrf_1_5": r2(valores["serv"] * IRRF), "crf_4_65": r2(valores["serv"] * CRF),
                         "ipi_mais_diferenca": valores["ipi"] + valores["difipi"], "custo_fechamento": custo})
        registro = dict(comum, data=chegada.isoformat(), historico=historico,
                        valores={k: {"valor": str(valores[k]) if isinstance(valores[k], D) else valores[k], "origem": origem.get(k, "")}
                                 for k in (*obrig, "icms_cobrado", "fatura", "nfs") if k in valores},
                        calculos={k: str(x) for k, x in calculos.items()},
                        lancamentos=[{"seq": i + 1, "conta": c, "classificacao": CONTAS[c][0], "descricao": CONTAS[c][1], "dc": dc,
                                      "valor": str(x), "historico": historico + sx} for i, (c, dc, x, sx) in enumerate(ls)],
                        debito=str(debito), credito=str(credito), confere=debito == credito)
        if aceite_pedido:                 # calculado e exibido, mas fora do TXT até o aceite
            aguardando_aceite.append(dict(registro, aceite_necessario=aceite_pedido, classe="AGUARDANDO_ACEITE"))
        else:
            fechados.append(registro)
    if competencia == "2026-09":     # CLAUDE.md / §2: setembro/26 já lançado manualmente
        alertas.insert(0, "Setembro/2026 já foi lançado manualmente: este TXT é apenas TESTE e NÃO deve ser importado no Domínio.")
    complementar = any(x.get("competencia") == competencia for x in ja_lancados)
    return {"agente": "agente-importacao (VGROW)", "versao": VERSAO, "complementar": complementar, "empresa": EMPRESA, "sol": sol, "competencia": competencia,
            "modo": "SIMULAÇÃO", "processos_fechados": fechados, "processos_pendentes": pendentes, "processos_aguardando_aceite": aguardando_aceite,
            "documentos_sem_processo": sem_processo, "alertas": alertas, "divergencias": divergencias,
            "validacao_debito_igual_credito": bool(fechados) and all(f["confere"] for f in fechados)}


# ---------------------------------------------------------------- saídas (§7 TXT + conferência)

def gravar_saidas(resultado: dict, saida: Path) -> dict:
    arquivos = {}
    comp = resultado["competencia"]
    if resultado["processos_fechados"]:
        txt = []
        for p in resultado["processos_fechados"]:
            data = dt.date.fromisoformat(p["data"]).strftime("%d/%m/%Y")
            for i, l in enumerate(p["lancamentos"]):
                conta = str(l["conta"])
                txt.append(";".join([data, conta if l["dc"] == "D" else "", conta if l["dc"] == "C" else "", fmt_txt(D(l["valor"])),
                                     "", l["historico"], "1" if i == 0 else "", "", "", ""]))
        # §6: competência já processada → TXT complementar só com os processos novos
        nome_txt = f"lanctos_Vgrow_{comp}{'_complementar' if resultado.get('complementar') else ''}_SIMULACAO_{resultado['sol']}.txt"
        (saida / nome_txt).write_text("\n".join(txt) + "\n", encoding="cp1252", newline="\r\n")
        arquivos["txt"] = nome_txt
    nome_xlsx = f"conferencia_Vgrow_{comp}_SIMULACAO_{resultado['sol']}.xlsx"
    planilha(resultado, saida / nome_xlsx)
    arquivos["conferencia"] = nome_xlsx
    return arquivos


def planilha(resultado: dict, destino: Path) -> None:
    """Planilha de conferência no MESMO formato do gerador validado da VGROW (vgrow_gerar.py): Resumo, Entradas
    (azul = valor dos documentos; parâmetros; checagem), Lançamentos (fórmulas a partir de Entradas) e Contas.
    Acrescenta só a aba "Origem" (EXTRAÍDO x INFORMADO_PELO_SUPERVISOR), exigida pela arquitetura do projeto."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter as L

    comp = resultado["competencia"]
    P = [{k: (v["valor"] if isinstance(v, dict) else v) for k, v in p["valores"].items()} | {"proc": p["identificacao"], "occt": p["processo"],
          "data": p["data"], "hist": p["historico"]} for p in resultado["processos_fechados"]]
    F = lambda **k: Font(name="Arial", **({"size": 10} | k))
    H = PatternFill("solid", fgColor="1F3864")
    HF = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    Y = PatternFill("solid", fgColor="FFF2CC")
    G = PatternFill("solid", fgColor="E2EFDA")
    R = PatternFill("solid", fgColor="FCE4D6")
    NUM = "#,##0.00;(#,##0.00);-"

    def header(ws, r, cols, w):
        for i, c in enumerate(cols, 1):
            x = ws.cell(r, i, c)
            x.fill, x.font, x.alignment = H, HF, Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[r].height = 32
        for i, v in enumerate(w, 1):
            ws.column_dimensions[L(i)].width = v

    wb = openpyxl.Workbook()
    # Resumo
    ws = wb.active
    ws.title = "Resumo"
    ws["A1"] = f"VGROW – Importações {comp[5:]}/{comp[:4]} – resumo (SIMULAÇÃO · {resultado['sol']} · conferência do Supervisor)"
    ws["A1"].font = F(bold=True, size=12)
    r = 3
    ws.cell(r, 1, "LANÇADOS NO TXT").font = F(bold=True)
    r += 1
    header(ws, r, ["Processo", "Ref. Capital Trade", "Data", "Total do lote", "Situação"], [30, 18, 12, 16, 90])
    r += 1
    for p in resultado["processos_fechados"]:
        for i, v in enumerate([p["identificacao"], p["processo"], dt.date.fromisoformat(p["data"]), float(p["debito"]), "Lançado"], 1):
            ws.cell(r, i, v).font = F()
        ws.cell(r, 3).number_format = "DD/MM/YYYY"
        ws.cell(r, 4).number_format = NUM
        r += 1
    r += 1
    ws.cell(r, 1, "PENDENTES (não lançados)").font = F(bold=True, color="C00000")
    r += 1
    header(ws, r, ["Processo", "Ref. Capital Trade", "Chegada", "", "Motivo"], [30, 18, 12, 16, 90])
    r += 1
    aguardando = [dict(x, motivos=[f"AGUARDANDO ACEITE do Supervisor: numerário − saldo − total REAL = {x['aceite_necessario']['diferenca']} "
                                    f"(fora do TXT até o aceite)"]) for x in resultado.get("processos_aguardando_aceite", [])]
    for p in resultado["processos_pendentes"] + aguardando:
        for i, v in enumerate([p.get("identificacao", p["processo"]), p["processo"], p.get("chegada") or "", "", " | ".join(p["motivos"])], 1):
            c = ws.cell(r, i, v)
            c.font, c.fill, c.alignment = F(), R, Alignment(wrap_text=True, vertical="top")
        r += 1
    r += 1
    ws.cell(r, 1, "ALERTAS (lançados, conferir)").font = F(bold=True, color="C55A11")
    r += 1
    for a in resultado["alertas"] + [f"DIVERGÊNCIA: {d}" for d in resultado["divergencias"]]:
        c = ws.cell(r, 1, a)
        c.font = F()
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        c.alignment = Alignment(wrap_text=True)
        ws.row_dimensions[r].height = 30
        r += 1
    # Entradas
    we = wb.create_sheet("Entradas")
    we["A1"] = "Entradas por processo (azul = valor extraído dos documentos)"
    we["A1"].font = F(bold=True, size=12)
    cols = ["Processo", "Ref. Capital Trade", "Data chegada", "Histórico base", "FOB R$", "Frete R$", "Numerário", "Saldo (+ receber / − pagar)", "IPI",
            "Diferença IPI", "PIS", "COFINS", "ICMS cobrado", "ICMS destacado NFs", "Serviço bruto", "Total REAL comparativo"]
    orig = ["Pasta", "Comparativo", "DUIMP – chegada", "Fatura + NFs", "DUIMP", "DUIMP", "Numerário / depósito efetivo", "Comparativo – saldo relatório",
            "Comparativo REAL", "Comparativo REAL", "Comparativo REAL", "Comparativo REAL", "Comparativo REAL", "NFs Capital Trade",
            "Comparativo – col. NUMERÁRIO (honorários + serviços)", "Comparativo"]
    header(we, 3, cols, [24, 15, 12, 44, 13, 13, 13, 14, 12, 12, 11, 12, 12, 12, 12, 14])
    for i, o in enumerate(orig, 1):
        c = we.cell(4, i, o)
        c.font, c.alignment = F(italic=True, size=8, color="595959"), Alignment(wrap_text=True)
    we.row_dimensions[4].height = 30
    K = ["proc", "occt", "data", "hist", "fob", "frete", "num", "saldo", "ipi", "difipi", "pis", "cof", "icms_cobrado", "icms_nf", "serv", "total_real"]
    for j, p in enumerate(P):
        for i, k in enumerate(K, 1):
            v = dt.date.fromisoformat(p[k]) if k == "data" else (float(p[k]) if i >= 5 else p[k])
            c = we.cell(5 + j, i, v)
            c.font = F(color="0000FF")
            c.number_format = "DD/MM/YYYY" if k == "data" else (NUM if i >= 5 else "General")
    last = 4 + len(P)
    pr = last + 2
    we.cell(pr, 1, "Parâmetros").font = F(bold=True)
    for j, (n, v) in enumerate([("% IRRF", 0.015), ("% CSRF", 0.0465), ("% desconto ICMS", 0.5)]):
        we.cell(pr + 1 + j, 1, n).font = F()
        c = we.cell(pr + 1 + j, 2, v)
        c.font, c.fill, c.number_format = F(color="0000FF"), Y, "0.00%"
    PI, PC, PD = [f"Entradas!$B${pr + 1 + j}" for j in range(3)]
    we.cell(pr + 5, 1, "Checagem: Numerário − Saldo − Total REAL (deve ser ~0)").font = F(bold=True)
    for j in range(len(P)):
        rr = 5 + j
        c = we.cell(rr, 17, f"=ROUND(G{rr}-H{rr}-P{rr},2)")
        c.number_format, c.font = NUM, F()
    we.cell(3, 17, "Checagem").fill = H
    we.cell(3, 17).font = HF
    we.column_dimensions["Q"].width = 11
    # Lançamentos
    wl = wb.create_sheet("Lançamentos")
    wl["A1"] = "Lançamentos (fórmulas a partir de Entradas) – mesmo conteúdo do TXT"
    wl["A1"].font = F(bold=True, size=12)
    header(wl, 3, ["Data", "Processo", "Seq", "Reduzida", "Conta", "Descrição", "Débito", "Crédito", "Histórico"], [11, 24, 5, 9, 16, 32, 15, 15, 62])
    r = 4
    for j, p in enumerate(P):
        e = 5 + j
        first = r
        E = lambda col, e=e: f"Entradas!{col}{e}"
        spec = [(f'=IF({E("H")}>=0,10084,10001)', f'=IF({E("H")}>=0,{E("H")},"")', f'=IF({E("H")}<0,-{E("H")},"")', f'=IF({E("H")}>=0," - SALDO A RECEBER"," - SALDO A PAGAR")'),
                (10084, "", f'={E("G")}', ""), (29, f'={E("I")}+{E("J")}', "", ""), (30, f'={E("N")}', "", ""), (36, f'={E("L")}', "", ""), (37, f'={E("K")}', "", ""),
                (55, f'={E("E")}', "", ""), (55, f'={E("F")}', "", '" - FRETE"'), (55, "CUSTO", "", '" - CUSTO"'), (10010, "", f'={E("E")}', ""),
                (10010, "", f'={E("F")}', '" - FRETE"'), (178, "", f'=ROUND({E("O")}*{PI},2)', '" - capital trade"'),
                (182, "", f'=ROUND({E("O")}*{PC},2)', '" - capital trade"'), (434, "", f'=ROUND({E("N")}*{PD},2)', '" - DESCONTO ICMS"'),
                (470, f'={E("O")}', "", '" - capital trade"')]
        custo = None
        for seq, (red, d, c, sx) in enumerate(spec, 1):
            wl.cell(r, 1, f'={E("C")}').number_format = "DD/MM/YYYY"
            wl.cell(r, 2, f'={E("A")}')
            wl.cell(r, 3, seq)
            wl.cell(r, 4, red)
            rc = f"D{r}"
            wl.cell(r, 5, f'=IFERROR(VLOOKUP({rc},Contas!$A:$C,2,0),"")')
            wl.cell(r, 6, f'=IFERROR(VLOOKUP({rc},Contas!$A:$C,3,0),"")')
            if d == "CUSTO":
                custo = r
            else:
                if d:
                    wl.cell(r, 7, d)
                if c:
                    wl.cell(r, 8, c)
            suf = sx if sx.startswith("=") else (sx if sx else '""')
            wl.cell(r, 9, f'={E("D")}&' + (suf[1:] if suf.startswith("=") else suf))
            r += 1
        lastl = r - 1
        wl.cell(custo, 7, f"=SUM(H{first}:H{lastl})-SUM(G{first}:G{custo - 1})-SUM(G{custo + 1}:G{lastl})")
        wl.cell(custo, 7).fill = Y
        wl.cell(r, 6, "Total / D−C")
        wl.cell(r, 7, f"=SUM(G{first}:G{lastl})")
        wl.cell(r, 8, f"=SUM(H{first}:H{lastl})")
        wl.cell(r, 9, f"=ROUND(G{r}-H{r},2)")
        for cc in range(1, 10):
            wl.cell(r, cc).fill = G
            wl.cell(r, cc).font = F(bold=True)
        r += 2
    for row in wl.iter_rows(min_row=4, max_row=r):
        for c in row:
            if not c.font.bold:
                c.font = F()
            if c.column in (7, 8):
                c.number_format = NUM
    wl.freeze_panes = "A4"
    # Contas
    wc = wb.create_sheet("Contas")
    header(wc, 1, ["Reduzida", "Classificação", "Descrição"], [10, 18, 34])
    for i, (k, (a, b)) in enumerate(CONTAS.items(), 2):
        wc.cell(i, 1, k)
        wc.cell(i, 2, a)
        wc.cell(i, 3, b)
    # Origem (projeto): de onde veio cada valor
    wo = wb.create_sheet("Origem")
    header(wo, 1, ["Ref. Capital Trade", "Campo", "Valor", "Origem"], [18, 16, 18, 70])
    r = 1
    for p in resultado["processos_fechados"]:
        for campo, v in p["valores"].items():
            r += 1
            for i, x in enumerate([p["processo"], campo, "/".join(v["valor"]) if isinstance(v["valor"], list) else v["valor"], v["origem"]], 1):
                wo.cell(r, i, x)
    wb.save(destino)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--sol", required=True)
    ap.add_argument("--competencia", required=True)
    ap.add_argument("--pasta", required=True)
    ap.add_argument("--informados", required=True)
    ap.add_argument("--saida", required=True)
    ap.add_argument("--empresa", default=EMPRESA)
    ap.add_argument("--aceites", help="JSON {processo: {chave, em}} com os aceites do Supervisor para diferenças de checagem")
    ap.add_argument("--ja-lancados", help="JSON com [{occt, sol, competencia}] já fechados em SOLs anteriores (registro do Coordenador)")
    a = ap.parse_args()
    erro = None
    saida = Path(a.saida).resolve()
    if a.empresa != EMPRESA:
        erro = "Este agente é exclusivo da VGROW."
    elif not re.fullmatch(r"SOL-20\d{2}-\d{6}", a.sol) or not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", a.competencia):
        erro = "SOL ou competência inválida."
    elif Path(a.pasta).is_absolute() or ".." in re.split(r"[\\/]", a.pasta) or ":" in a.pasta:
        erro = "Pasta do lote deve ser relativa à VGROW, sem '..'."
    elif str(saida).lower().startswith(str(RAIZ).lower()) or "onedrive" in str(saida).lower():
        erro = "Saída deve ficar no runtime (fora do projeto e de pastas sincronizadas); nunca em LIBERADOS."
    if erro:
        print(json.dumps({"erro": "PARAMETROS_INVALIDOS", "mensagem": erro}, ensure_ascii=False))
        return 2
    informados = json.loads(Path(a.informados).read_text(encoding="utf-8"))
    ja_lancados = json.loads(Path(a.ja_lancados).read_text(encoding="utf-8")) if a.ja_lancados else []
    aceites = json.loads(Path(a.aceites).read_text(encoding="utf-8")) if a.aceites else {}
    resultado = processar(a.sol, a.competencia, extrair(a.pasta), informados, ja_lancados, aceites)
    saida.mkdir(parents=True, exist_ok=True)
    resultado["arquivos"] = gravar_saidas(resultado, saida)
    (saida / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
