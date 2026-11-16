"""CONCILIAÇÃO CAIXINHA — etapa CAIXINHA_CONCILIACAO → CONCILIACAO_CAIXINHA_V1. SIMULAÇÃO, código local, determinístico.

Especialistas (um módulo, quatro responsabilidades separadas no resultado):
1. CONCILIADOR TRIBUTÁRIO — cruza pagamentos do e-CAC (evidência EXTERNA) com o razão e o balancete das contas de tributos:
   classifica cada obrigação (PAGA_E_CONTABILIZADA, PAGA_NAO_CONTABILIZADA, EM_ABERTO, DIVERGENTE, SEM_PROVISAO_IDENTIFICADA,
   PAGAMENTO_DUPLICADO, NECESSITA_REVISAO) e prepara D Tributo a Recolher × C Caixa Geral só para pagamento comprovado e ainda não
   contabilizado. Associação por critérios verificáveis (conta, valor exato + data do pagamento na janela OU referência do período /
   documento no histórico); valor igual sozinho NUNCA associa; mais de uma possibilidade → revisão. DARF com vários tributos: um
   débito por tributo, soma = crédito no Caixa; sem composição → revisão (divisão nunca presumida). Provisão nunca é criada.
2. CONCILIADOR DE FOLHA — política operacional APROVADA: manter em aberto só o líquido da última competência da folha; a diferença
   do saldo do Pró-labore a Pagar é REGULARIZAÇÃO CONFORME POLÍTICA CAIXINHA (não é pagamento individualmente comprovado). Interpreta
   o razão: retenções (INSS/IRRF) já lançadas e pagamentos já contabilizados são identificados e NÃO descontados de novo.
3. CONCILIADOR GERAL — integridade das etapas, saldos razão × balancete, vigência das regras, duplicidade (no resultado, com baixas
   aprovadas/exportadas em outras solicitações e com baixas já presentes no razão), saldo projetado de cada conta (nunca forçado a zero).
4. CONTROLE DO CAIXA — saldo do Caixa Geral (balancete) − baixas tributárias − baixas de folha = saldo CONTÁBIL projetado (não é
   conferência de dinheiro físico); saldo credor projetado gera alerta.
Nada é aprovado, escriturado ou exportado aqui. Competências encerradas nunca são alteradas: data fora da competência → revisão.

Uso: .venv/bin/python -I AGENTES/CONCILIACAO/CAIXINHA/ferramentas/conciliacao_caixinha.py --empresa <EMP> --sol <SOL>
     --competencia AAAA-MM --entradas <entradas.json> --saida <dir>
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import caixinha_comum as cc  # noqa: E402
import exportacao_dominio  # noqa: E402
import regras_caixinha  # noqa: E402

CONTRATO = "CONCILIACAO_CAIXINHA_V1"
ETAPAS = {"CAIXINHA_CONTABIL": "CAIXINHA_CONTABIL_V1", "CAIXINHA_FISCAL": "CAIXINHA_FISCAL_V1", "CAIXINHA_DP": "CAIXINHA_DP_V1"}
CLASSES = {"PAGA_E_CONTABILIZADA": "Paga e contabilizada", "PAGA_NAO_CONTABILIZADA": "Paga e não contabilizada", "EM_ABERTO": "Em aberto",
           "DIVERGENTE": "Divergente", "SEM_PROVISAO_IDENTIFICADA": "Sem provisão identificada", "PAGAMENTO_DUPLICADO": "Pagamento duplicado",
           "NECESSITA_REVISAO": "Necessita revisão"}
EVID = {"EXTERNA": "DOCUMENTO_EXTERNO", "INTERNA": "CONTROLE_INTERNO", "POLITICA": "POLITICA_OPERACIONAL", "SISTEMA": "CONSISTENCIA_SISTEMA"}
Z = Decimal("0")
D = lambda v: Z if v in (None, "") else Decimal(str(v))  # noqa: E731
f2 = lambda v: None if v is None else f"{Decimal(v):.2f}"  # noqa: E731
br = lambda v: f"{Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
mmaaaa = lambda comp: f"{comp[5:7]}/{comp[:4]}" if comp else "?"  # noqa: E731
dmy = lambda iso: f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else "?"  # noqa: E731


class Conciliacao:
    def __init__(self, ent: dict):
        self.ent, self.empresa, self.sol, self.comp = ent, ent["empresa"], ent["sol"], ent["competencia"]
        self.inicio = dt.date.fromisoformat(self.comp + "-01").isoformat()
        self.fim = cc.fim_competencia(self.comp).isoformat()
        self.verificacoes, self.obrigacoes, self.lancamentos, self.revisao = [], [], [], []
        self.versoes, self.parcial, self.consumidos = {}, [], set()
        self.res = {}
        self.em_aberto, self.folha_res, self.caixa, self.projecao = {}, None, None, {}

    # ---------------------------------------------------------------- utilitários
    def verif(self, grupo, titulo, resultado, evidencia, bloqueia=True, conta=None, esperado=None, encontrado=None, detalhe=None,
              fontes=(), acao=None, responsavel="SUPERVISOR"):
        vid = "VCX-" + cc.chave_hash(self.empresa, self.sol, grupo, titulo, conta)[:12]
        dif = None
        if esperado is not None and encontrado is not None:
            dif = f2(D(encontrado) - D(esperado))
        v = {"id": vid, "grupo": grupo, "titulo": titulo, "resultado": resultado, "evidencia": EVID[evidencia], "bloqueia": bool(bloqueia),
             "conta": conta, "esperado": f2(esperado) if esperado is not None else None,
             "encontrado": f2(encontrado) if encontrado is not None else None, "diferenca": dif, "detalhe": detalhe,
             "fontes": list(fontes), "acao": acao, "responsavel": responsavel}
        self.verificacoes.append(v)
        return v

    def rev(self, tipo, problema, impacto, acao, responsavel="SUPERVISOR", origem=None, obrigacao=None):
        self.revisao.append({"id": "RCX-" + cc.chave_hash(self.sol, tipo, problema)[:12], "tipo": tipo, "problema": problema,
                             "impacto": impacto, "o_que_fazer": acao, "responsavel": responsavel, "origem": origem, "obrigacao": obrigacao})

    def conta_info(self, cod):
        c = self.plano.get(str(cod)) or {}
        return {"codigo": str(cod), "descricao": c.get("descricao"), "classificacao": c.get("classificacao")}

    # ---------------------------------------------------------------- entradas
    def carregar(self):
        e = self.ent
        for etapa, contrato in ETAPAS.items():
            x = (e.get("etapas") or {}).get(etapa) or {}
            caminho = x.get("resultado")
            ok, motivo = False, None
            if x.get("situacao") != "CONCLUIDA" or not caminho:
                motivo = f"etapa {etapa} não concluída ({x.get('situacao') or 'NAO_ACIONADA'})"
            else:
                bruto = Path(caminho).read_bytes()
                sha = hashlib.sha256(bruto).hexdigest()
                if sha != x.get("sha256_registrado"):
                    motivo = f"resultado de {etapa} diferente do registrado pelo Coordenador (sha256)"
                else:
                    r = json.loads(bruto.decode("utf-8"))
                    if (r.get("contrato"), r.get("empresa"), r.get("sol"), r.get("competencia"), r.get("modo")) != (
                            contrato, self.empresa, self.sol, self.comp, "SIMULACAO"):
                        motivo = f"resultado de {etapa} de outro contrato/empresa/SOL/competência"
                    else:
                        ok = True
                        self.res[etapa] = r
                        self.versoes[etapa] = sha
            self.verif("A_INTEGRIDADE", f"Resultado da etapa {etapa} íntegro e da mesma solicitação", "CONFERIDO" if ok else "PENDENTE",
                       "SISTEMA", detalhe=motivo, acao=None if ok else "Rever a etapa indicada (ação do Supervisor).", responsavel="COORDENADOR")
            if not ok:
                self.parcial.append(motivo)
        p = e.get("pacote") or {}
        if p.get("manifesto_sha256"):
            self.versoes["PACOTE"] = p["manifesto_sha256"]
        if p.get("extracao_sha256"):
            self.versoes["EXTRACAO"] = p["extracao_sha256"]
        self.plano = exportacao_dominio.plano_empresa(self.empresa)
        self.class_para_cod = {str(v.get("classificacao")): k for k, v in self.plano.items() if v.get("classificacao")}
        base = exportacao_dominio.clientes() / self.empresa
        cnpjs = [re.sub(r"\D", "", c) for c in re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", (base / "CADASTRO.md").read_text(encoding="utf-8"))]
        self.regras = regras_caixinha.avaliar(base, self.empresa, cnpjs, self.comp)
        try:
            bruto_regras = regras_caixinha.ler(base) or {}
        except (OSError, ValueError):
            bruto_regras = {}
        cfg = bruto_regras.get("configuracao") or {}
        self.cfg_aplicavel = bool((self.regras.get("configuracao") or {}).get("aplicavel"))
        self.folha_aplicavel = bool((self.regras.get("politica_folha") or {}).get("aplicavel"))
        # Análise usa o conteúdo registrado (mesmo em PROPOSTA) para mostrar o resultado; lançamento só é COMPLETO com regra aplicável.
        self.contas = {k: str(v) for k, v in (cfg.get("contas") or {}).items() if v not in (None, "")}
        self.tributos = cfg.get("tributos") or []
        self.pol_datas = (cfg.get("politica_datas") or {}).get("tributos")
        self.criterios = dict(regras_caixinha.CRITERIOS_PADRAO, **(cfg.get("criterios_baixa") or {}))
        self.folha_pol = bruto_regras.get("politica_folha") or {}
        g = self.regras.get("configuracao") or {}
        self.verif("B_REGRAS", "Configuração da rotina Caixinha aprovada e vigente", "CONFERIDO" if self.cfg_aplicavel else "PENDENTE",
                   "SISTEMA", detalhe=None if self.cfg_aplicavel else (g.get("motivo") or "Configuração ausente."),
                   acao=None if self.cfg_aplicavel else f"Confirme a configuração (frase \"{g.get('frase') or 'VALIDADO REGRA CAIXINHA ...'}\")."
                   " Sem regra aprovada as propostas ficam INCOMPLETAS.")
        if not self.contas.get("CAIXA_GERAL"):
            self.parcial.append("conta Caixa Geral não definida")

    # ---------------------------------------------------------------- contábil (balancete e razão)
    def preparar_contabil(self):
        c = self.res.get("CAIXINHA_CONTABIL") or {}
        self.balancete = c.get("balancete")
        self.razao = c.get("razao")
        self.saldos = {}
        for x in (self.balancete or {}).get("contas", []):
            cod = str(x.get("codigo") or self.class_para_cod.get(str(x.get("conta"))) or "")
            if cod:
                self.saldos[cod] = x
        self.linhas = {}
        for i, l in enumerate((self.razao or {}).get("lancamentos", [])):
            cod = str(l.get("codigo") or self.class_para_cod.get(str(l.get("conta"))) or l.get("conta") or "")
            if not cod:
                continue
            x = {"idx": i, "data": l.get("data"), "historico": cc.norm(l.get("historico")), "historico_original": l.get("historico"),
                 "debito": D(l.get("debito")), "credito": D(l.get("credito")), "contrapartida": str(l.get("contrapartida") or "") or None,
                 "pagina": l.get("pagina"), "lote": l.get("lote")}
            if x["contrapartida"] and x["contrapartida"] not in self.plano and x["contrapartida"] in self.class_para_cod:
                x["contrapartida"] = self.class_para_cod[x["contrapartida"]]
            self.linhas.setdefault(cod, []).append(x)
        self.razao_contas = {}
        for x in (self.razao or {}).get("contas", []):
            cod = str(x.get("codigo") or self.class_para_cod.get(str(x.get("classificacao"))) or "")
            if cod:
                self.razao_contas[cod] = x
        self.razao_periodo = (self.razao or {}).get("periodo")
        if not self.balancete:
            self.verif("C_SALDOS", "Balancete do período recebido e lido", "PENDENTE", "INTERNA",
                       detalhe="Balancete ausente ou não lido: saldos das contas não conhecidos (nada é presumido).",
                       acao="Envie o balancete do período (PDF do Domínio).", responsavel="CONTABIL")
            self.parcial.append("balancete ausente")
        if not self.razao:
            self.verif("C_SALDOS", "Razão do período recebido e lido", "PENDENTE", "INTERNA",
                       detalhe="Razão ausente ou não lido: não é possível verificar baixas já contabilizadas.",
                       acao="Envie o razão das contas da rotina (PDF do Domínio).", responsavel="CONTABIL")
            self.parcial.append("razão ausente")
        elif not self.razao_periodo:
            self.verif("C_SALDOS", "Período do razão identificado", "PENDENTE", "INTERNA",
                       detalhe="Período do razão não identificado: cobertura das datas não verificável.", acao="Envie o razão com o período no cabeçalho.",
                       responsavel="CONTABIL")
        for chave, cod in sorted(self.contas.items()):
            if chave in ("MULTAS_FISCAIS", "JUROS_FISCAIS"):
                continue
            b = self.saldos.get(cod)
            r = self.razao_contas.get(cod)
            if not self.balancete:
                continue
            if b is None:
                self.verif("C_SALDOS", f"Conta {cod} ({chave}) no balancete", "PENDENTE", "INTERNA", conta=cod,
                           detalhe="Conta não consta no balancete (filtro de emissão?): saldo desconhecido; nada presumido.",
                           acao="Emita o balancete com todas as contas da rotina.", responsavel="CONTABIL")
                continue
            if not self.razao:
                continue
            if r is None:
                movimento = D(b.get("debitos")) or D(b.get("creditos"))
                self.verif("C_SALDOS", f"Conta {cod} ({chave}) no razão", "PENDENTE" if movimento else "CONFERIDO", "INTERNA", conta=cod,
                           bloqueia=bool(movimento), detalhe=("Conta com movimento no balancete e sem seção no razão." if movimento else
                                                            "Conta sem movimento no período e sem seção no razão."),
                           acao="Emita o razão incluindo a conta." if movimento else None, responsavel="CONTABIL")
                continue
            iguais = r.get("saldo_final") is not None and D(r["saldo_final"]) == D(b.get("saldo_final"))
            self.verif("C_SALDOS", f"Saldo final da conta {cod} ({chave}): razão × balancete", "CONFERIDO" if iguais else "DIVERGENTE",
                       "INTERNA", conta=cod, esperado=b.get("saldo_final"), encontrado=r.get("saldo_final"),
                       detalhe=None if iguais else "Razão e balancete não concordam: nenhuma baixa desta conta é tratada como completa.",
                       acao=None if iguais else "Emita razão e balancete do mesmo período/versão da escrituração.", responsavel="CONTABIL",
                       fontes=[(self.balancete or {}).get("arquivo"), (self.razao or {}).get("arquivo")])
            if not iguais:
                self.contas_divergentes.add(cod)

    def razao_cobre(self, data):
        p = self.razao_periodo or {}
        return bool(p.get("inicio") and p.get("fim") and p["inicio"] <= data <= p["fim"])

    # ---------------------------------------------------------------- tributário
    def tributo_de(self, comp, pag):
        cod = str(comp.get("codigo") or "")
        por_codigo = [t for t in self.tributos if cod and cod in [str(x) for x in t.get("codigos_receita") or []]]
        if len(por_codigo) == 1:
            return por_codigo[0], f"código de receita {cod} vinculado a {por_codigo[0]['chave']} na configuração da empresa"
        por_tipo = [t for t in self.tributos if pag.get("tipo_documento") in (t.get("tipos_documento") or [])]
        if not por_codigo and len(por_tipo) == 1:
            return por_tipo[0], f"tipo de documento {pag.get('tipo_documento')} vinculado a {por_tipo[0]['chave']}"
        den = cc.norm(comp.get("denominacao"))
        por_desc = [t for t in self.tributos if den and any(cc.norm(d) in den for d in t.get("descricoes") or [])]
        if not por_codigo and len(por_desc) == 1:
            return por_desc[0], f"denominação '{comp.get('denominacao')}' vinculada a {por_desc[0]['chave']}"
        return None, None

    def data_lancamento(self, data_pag):
        pol = self.pol_datas
        dentro = self.inicio <= data_pag <= self.fim
        if pol == "DATA_PAGAMENTO":
            return (data_pag, False, None) if dentro else (None, False, "pagamento fora da competência em análise (competência encerrada não "
                                                                         "é alterada automaticamente)")
        if pol == "ULTIMO_DIA_COMPETENCIA":
            return self.fim, not dentro, None
        if pol == "DATA_PAGAMENTO_OU_ULTIMO_DIA":
            return (data_pag, False, None) if dentro else (self.fim, True, None)
        return None, False, "política de data das baixas tributárias não definida"

    def candidatos(self, cod, valor, lado, criterio):
        return [x for x in self.linhas.get(cod, []) if x[lado] == valor and (cod, x["idx"]) not in self.consumidos and criterio(x)]

    def refs(self, pag):
        pa = (pag.get("periodo_apuracao") or {}).get("competencia")
        saida = []
        if pa:
            saida += [mmaaaa(pa), f"{pa[5:7]}/{pa[2:4]}", f"{pa[5:7]}.{pa[:4]}"]
        n = cc.digitos(pag.get("numero_documento"))
        if len(n) >= 8:
            saida.append(n)
        return saida

    @staticmethod
    def periodo_ref(historico):
        m = re.search(r"(?<!\d)(0[1-9]|1[0-2])/(20\d{2})(?!\d)", historico or "")
        return f"{m.group(1)}/{m.group(2)}" if m else None

    @staticmethod
    def tem_ref(x, refs):
        return any(r in x["historico"] or (r.isdigit() and r in cc.digitos(x["historico"])) for r in refs)

    @staticmethod
    def outro_periodo(x, refs):
        """Histórico cita um período MM/AAAA diferente do pagamento (lançamento atribuível a outra competência)."""
        citados = re.findall(r"(?<!\d)(?:0[1-9]|1[0-2])/20\d{2}(?!\d)", x["historico"])
        return bool(citados) and not any(c in refs for c in citados)

    def baixa_ja_contabilizada(self, cod, valor, pag):
        """(situação, linha, critério): JA (associação única com critério) | AMBIGUO | SO_VALOR (valor igual sem critério) | NAO."""
        janela = int(self.criterios.get("janela_dias_baixa_razao") or 0)
        data = dt.date.fromisoformat(pag["data_pagamento"])
        refs = self.refs(pag)

        def criterio(x):
            if not x.get("data"):
                return False
            perto = abs((dt.date.fromisoformat(x["data"]) - data).days) <= janela
            ref = any(r in x["historico"] or (r.isdigit() and r in cc.digitos(x["historico"])) for r in refs)
            return perto or ref
        fortes = self.candidatos(cod, valor, "debito", criterio)
        if len(fortes) > 1:                       # valores mensais repetidos: prevalece quem atende data E referência
            ambos = [x for x in fortes if self.tem_ref(x, refs) and abs((dt.date.fromisoformat(x["data"]) - data).days) <= janela]
            fortes = ambos if len(ambos) == 1 else fortes
        if len(fortes) == 1:
            x = fortes[0]
            motivo = []
            if abs((dt.date.fromisoformat(x["data"]) - data).days) <= janela:
                motivo.append(f"data {dmy(x['data'])} a até {janela} dia(s) do pagamento")
            if any(r in x["historico"] for r in refs):
                motivo.append("referência do período/documento no histórico")
            return "JA", x, f"débito de {br(valor)} na conta {cod} (p.{x['pagina']}), " + " e ".join(motivo)
        if len(fortes) > 1:
            return "AMBIGUO", fortes, f"{len(fortes)} débitos de {br(valor)} na conta {cod} atendem aos critérios"
        pa = (pag.get("periodo_apuracao") or {}).get("competencia") or ""
        so_valor = self.candidatos(cod, valor, "debito", lambda x: (x.get("data") or "")[:7] >= pa and not self.outro_periodo(x, refs))
        if so_valor:
            return "SO_VALOR", so_valor, f"débito de mesmo valor na conta {cod} sem data/referência compatível"
        return "NAO", None, None

    def provisao(self, cod, valor, pag):
        pa = (pag.get("periodo_apuracao") or {}).get("competencia")
        refs = self.refs(pag)
        if not pa:
            return "NAO_DETERMINADA", None, "período de apuração não identificado"
        a, m = map(int, pa.split("-"))
        seguinte = f"{a + (m == 12):04d}-{m % 12 + 1:02d}"

        # critérios em NÍVEIS (o primeiro nível com candidato decide; mais de um candidato no nível = ambíguo):
        # 1) referência do período no histórico; 2) data no mês do período de apuração (integração do Domínio no fim do mês);
        # 3) data no mês seguinte. Valor igual sozinho nunca associa; histórico que cita OUTRO período é excluído.
        niveis = ((lambda x: self.tem_ref(x, refs), "referência do período no histórico"),
                  (lambda x: (x.get("data") or "")[:7] == pa and not self.outro_periodo(x, refs), f"data no mês do período de apuração {mmaaaa(pa)}"),
                  (lambda x: (x.get("data") or "")[:7] == seguinte and not self.outro_periodo(x, refs), f"data no mês seguinte ao período {mmaaaa(pa)}"))
        for criterio, texto in niveis:
            c = self.candidatos(cod, valor, "credito", criterio)
            if len(c) == 1:
                x = c[0]
                return "IDENTIFICADA", x, f"crédito (provisão) de {br(valor)} na conta {cod} em {dmy(x['data'])} (p.{x['pagina']}), {texto}"
            if len(c) > 1:
                return "AMBIGUA", c, f"{len(c)} provisões de {br(valor)} na conta {cod} atendem ao mesmo critério ({texto})"
        inicio = (self.razao_periodo or {}).get("inicio") or ""
        if inicio and pa < inicio[:7]:
            anterior = (self.razao_contas.get(cod) or {}).get("saldo_anterior")
            credor = -D(anterior) if anterior is not None else None
            total_ant = self.pagos_antes_do_razao.get(cod, Z)
            if credor is not None and credor > 0 and credor == total_ant:
                return "IDENTIFICADA", None, (f"período {mmaaaa(pa)} anterior ao razão: saldo anterior credor da conta {cod} ({br(credor)}) "
                                              f"integralmente composto pelos pagamentos de períodos anteriores ao razão ({br(total_ant)})")
            return "ANTERIOR_AO_RAZAO", None, (f"período {mmaaaa(pa)} anterior ao início do razão: saldo anterior "
                                               f"({br(credor) if credor is not None else 'não identificado'}) ≠ pagamentos de períodos anteriores "
                                               f"({br(total_ant)}); provisão não individualizada")
        return "NAO_IDENTIFICADA", None, f"nenhuma provisão de {br(valor)} compatível com o período {mmaaaa(pa)} na conta {cod}"

    def tributos_conciliar(self):
        f = self.res.get("CAIXINHA_FISCAL") or {}
        pagamentos = f.get("pagamentos") or []
        caixa = self.contas.get("CAIXA_GERAL")
        anteriores = {x["identidade"]: x for x in self.ent.get("fatos_outras_sols") or []}
        duplicados = {i for d in f.get("possiveis_duplicidades") or [] for i in d["pagamentos"]}
        contas_trib = {t["chave"]: self.contas.get(t.get("conta")) for t in self.tributos}
        # pagamentos comprovados de períodos ANTERIORES ao início do razão, por conta (para conferir com o saldo anterior do razão)
        self.pagos_antes_do_razao = {}
        inicio = ((self.razao_periodo or {}).get("inicio") or "")[:7]
        for p in pagamentos:
            pa = (p.get("periodo_apuracao") or {}).get("competencia") or ""
            if inicio and pa and pa < inicio and p.get("utilizavel") and p["id"] not in duplicados:
                for c in p["componentes"]:
                    t_, _ = self.tributo_de(c, p)
                    cod = contas_trib.get(t_["chave"]) if t_ else None
                    if cod:
                        self.pagos_antes_do_razao[cod] = self.pagos_antes_do_razao.get(cod, Z) + D(c["principal"])
        for p in pagamentos:
            ob = {"id": "OCX-" + p["id"][4:], "pagamento": p["id"], "tipo_documento": p.get("tipo_documento"),
                  "numero_documento": p.get("numero_documento"), "periodo_apuracao": (p.get("periodo_apuracao") or {}).get("texto"),
                  "competencia_apuracao": (p.get("periodo_apuracao") or {}).get("competencia"), "data_pagamento": p.get("data_pagamento"),
                  "valor_total": p.get("valor_total"), "componentes": [], "classificacao": None, "motivos": [], "criterios": [],
                  "lancamentos": [], "origem": p.get("origem"), "evidencia": EVID["EXTERNA"] if p.get("evidencia") == "PAGAMENTO_REGISTRADO_ECAC" else None,
                  "competencia_lancamento": None}
            self.obrigacoes.append(ob)

            def classificar(classe, motivo, acao="Revise o pagamento e decida (nenhuma baixa foi preparada).", impacto=None):
                ob["classificacao"] = classe
                ob["motivos"].append(motivo)
                if classe in ("NECESSITA_REVISAO", "DIVERGENTE", "SEM_PROVISAO_IDENTIFICADA", "PAGAMENTO_DUPLICADO"):
                    self.rev(classe, f"{p.get('tipo_documento')} {p.get('numero_documento') or ''} PA {ob['periodo_apuracao']} pago em "
                                     f"{dmy(p.get('data_pagamento'))} ({br(D(p.get('valor_total')))}): {motivo}",
                             impacto or "Pagamento sem baixa proposta; saldo da conta permanece.", acao, origem=p.get("origem"), obrigacao=ob["id"])
            if p.get("evidencia") != "PAGAMENTO_REGISTRADO_ECAC":
                classificar("NECESSITA_REVISAO", "guia sem comprovação de pagamento (sem data de arrecadação): não gera baixa")
                continue
            if p["id"] in duplicados:
                classificar("PAGAMENTO_DUPLICADO", "mesmo período, código e valor de outro pagamento com número de documento diferente",
                            "Confirme no e-CAC se houve pagamento em duplicidade (restituição/compensação); nenhuma baixa em dobro.")
                continue
            if not p.get("utilizavel"):
                classificar("NECESSITA_REVISAO", "; ".join(p.get("pendencias") or ["leitura do pagamento incompleta"]))
                continue
            if p["data_pagamento"] > self.fim:
                ob["classificacao"] = "EM_ABERTO"
                ob["motivos"].append(f"pago em {dmy(p['data_pagamento'])}, depois do fim da competência {mmaaaa(self.comp)}: a baixa pertence à "
                                     "competência do pagamento")
                continue
            # tributo e conta de cada componente
            por_conta, falta = {}, None
            for c in p["componentes"]:
                t, crit = self.tributo_de(c, p)
                cod = contas_trib.get(t["chave"]) if t else None
                comp = {"codigo": c["codigo"], "denominacao": c.get("denominacao"), "principal": c["principal"], "multa": c["multa"],
                        "juros": c["juros"], "total": c["total"], "tributo": t["chave"] if t else None, "conta": cod, "criterio": crit,
                        "pagina": c.get("pagina")}
                ob["componentes"].append(comp)
                if not t:
                    falta = f"código de receita {c['codigo']} sem tributo vinculado na configuração da empresa"
                elif not cod:
                    falta = f"tributo {t['chave']} sem conta definida na configuração"
                else:
                    g = por_conta.setdefault(cod, {"tributo": t["chave"], "principal": Z, "componentes": []})
                    g["principal"] += D(c["principal"])
                    g["componentes"].append(c["codigo"])
            if falta:
                classificar("NECESSITA_REVISAO", falta, "Vincule o código de receita ao tributo/conta na configuração (nova versão, aprovação).")
                continue
            multa = sum((D(c["multa"]) for c in p["componentes"]), Z)
            juros = sum((D(c["juros"]) for c in p["componentes"]), Z)
            if (multa and not self.contas.get("MULTAS_FISCAIS")) or (juros and not self.contas.get("JUROS_FISCAIS")):
                classificar("NECESSITA_REVISAO", "pagamento com multa/juros e conta de despesa correspondente não definida na configuração")
                continue
            if not self.razao or not self.razao_cobre(p["data_pagamento"]):
                classificar("NECESSITA_REVISAO", "o razão recebido não cobre a data do pagamento: não é possível verificar se a baixa já foi "
                                                 "contabilizada", "Envie o razão que inclua a data do pagamento.")
                continue
            # já contabilizado?
            estados, linhas_ja = {}, []
            for cod, g in por_conta.items():
                s, x, crit = self.baixa_ja_contabilizada(cod, g["principal"], p)
                estados[cod] = s
                if s == "JA":
                    linhas_ja.append((cod, x))
                    ob["criterios"].append(crit)
                elif s in ("AMBIGUO", "SO_VALOR"):
                    ob["motivos"].append(crit)
            if all(s == "JA" for s in estados.values()):
                for cod, x in linhas_ja:
                    self.consumidos.add((cod, x["idx"]))
                ob["classificacao"] = "PAGA_E_CONTABILIZADA"
                ob["valores_contabilizados"] = {cod: f2(g["principal"]) for cod, g in por_conta.items()}
                continue
            if any(s in ("AMBIGUO", "SO_VALOR") for s in estados.values()):
                classificar("NECESSITA_REVISAO", "possível baixa já contabilizada sem associação única por critério verificável",
                            "Confira no razão se o débito indicado corresponde a este pagamento.")
                continue
            if any(s == "JA" for s in estados.values()):
                classificar("DIVERGENTE", "parte do pagamento já contabilizada e parte não: composição divergente no razão",
                            "Confira os lançamentos do pagamento no razão (nenhuma baixa parcial automática).")
                continue
            # provisão (já integrada pelo Domínio; nunca criada aqui)
            prov_ok, sem_prov = [], None
            for cod, g in por_conta.items():
                s, x, crit = self.provisao(cod, g["principal"], p)
                if s == "IDENTIFICADA":
                    prov_ok.append((cod, x))
                    ob["criterios"].append(crit)
                elif s == "AMBIGUA":
                    sem_prov = ("NECESSITA_REVISAO", crit)
                elif s in ("ANTERIOR_AO_RAZAO", "NAO_IDENTIFICADA", "NAO_DETERMINADA"):
                    if self.criterios.get("exigir_provisao_identificada", True) or s == "NAO_DETERMINADA":
                        sem_prov = ("SEM_PROVISAO_IDENTIFICADA", crit)
                    else:
                        ob["criterios"].append(f"{crit}; critério da empresa dispensa provisão individualizada")
            if sem_prov:
                classificar(sem_prov[0], sem_prov[1], "Confirme a provisão da obrigação no razão (o sistema não cria provisão).")
                continue
            identidade_base = f"CXN-TRIB|{self.empresa}|{p['id']}"
            ja = [i for i in anteriores if i.startswith(identidade_base + "|")]
            if ja:
                x = anteriores[ja[0]]
                classificar("NECESSITA_REVISAO", f"baixa deste pagamento já {x.get('situacao', 'proposta').lower()} na {x.get('sol')} e ainda não "
                                                 "consta no razão recebido", "Importe/confira no Domínio a baixa já aprovada e reenvie o razão; "
                                                                             "nenhuma baixa em dobro.")
                continue
            data, regularizacao, motivo_data = self.data_lancamento(p["data_pagamento"])
            if motivo_data and "fora da competência" in motivo_data:
                classificar("NECESSITA_REVISAO", motivo_data, "Decida a competência da baixa (política de datas da empresa).")
                continue
            for cod, x in prov_ok:
                if x is not None:
                    self.consumidos.add((cod, x["idx"]))
            ob["classificacao"] = "PAGA_NAO_CONTABILIZADA"
            ob["competencia_lancamento"] = data[:7] if data else None
            grupo = "GCX-" + cc.chave_hash(identidade_base)[:12]
            partes = [(cod, g["principal"], g["tributo"], ",".join(g["componentes"])) for cod, g in sorted(por_conta.items())]
            if multa:
                partes.append((self.contas["MULTAS_FISCAIS"], multa, "MULTA", "multa"))
            if juros:
                partes.append((self.contas["JUROS_FISCAIS"], juros, "JUROS", "juros"))
            for cod, valor, tributo, rot in partes:
                hist = (f"BAIXA {tributo.replace('_', ' ')} PA {ob['periodo_apuracao']} PAGO EM {dmy(p['data_pagamento'])} "
                        f"{p.get('tipo_documento') or ''} {cc.digitos(p.get('numero_documento'))}").strip()
                if regularizacao:
                    hist = "REGULARIZACAO " + hist
                l = self.lancamento("CAIXINHA_TRIBUTOS", f"{identidade_base}|{cod}|{rot}", data, cod, caixa, valor, hist,
                                    evidencia="EXTERNA", classificacao="BAIXA_TRIBUTARIA_COMPROVADA_ECAC", grupo=grupo,
                                    origem=p.get("origem"), motivo_incompleto=motivo_data,
                                    extra={"pagamento": p["id"], "tributo": tributo, "componentes": rot, "data_pagamento": p["data_pagamento"],
                                           "periodo_apuracao": ob["periodo_apuracao"], "regularizacao": regularizacao})
                ob["lancamentos"].append(l["id"])
            soma = sum((D(self.por_id[i]["valor"]) for i in ob["lancamentos"]), Z)
            self.verif("D_TRIBUTOS", f"DARF/DAS {p.get('numero_documento') or p['id']}: soma dos débitos = crédito no Caixa = valor pago",
                       "CONFERIDO" if soma == D(p["valor_total"]) else "DIVERGENTE", "EXTERNA", esperado=p["valor_total"], encontrado=soma,
                       fontes=[(p.get("origem") or {}).get("arquivo")])
        # provisões do razão sem pagamento no e-CAC (EM ABERTO) — informativo por conta
        self.em_aberto = {}
        for t in self.tributos:
            cod = contas_trib.get(t["chave"])
            if not cod:
                continue
            # provisão (crédito) sem baixa no razão: cada débito quita no máximo UMA provisão, de mesmo valor, data posterior e
            # sem referência a OUTRO período (débito que cita o período da provisão tem preferência)
            creditos = [x for x in self.linhas.get(cod, []) if x["credito"] > 0 and (cod, x["idx"]) not in self.consumidos]
            debitos = [x for x in self.linhas.get(cod, []) if x["debito"] > 0]
            usados, abertas = set(), []
            for x in creditos:
                pr = self.periodo_ref(x["historico"])
                cands = [y for y in debitos if y["idx"] not in usados and y["debito"] == x["credito"] and (y.get("data") or "") >= (x.get("data") or "")]
                com_ref = [y for y in cands if pr and pr in y["historico"]]
                sem_conflito = [y for y in cands if not (pr and self.periodo_ref(y["historico"]) and pr not in y["historico"])]
                escolhido = (com_ref or sem_conflito or [None])[0]
                if escolhido:
                    usados.add(escolhido["idx"])
                else:
                    abertas.append(x)
            self.em_aberto[cod] = [{"data": x["data"], "valor": f2(x["credito"]), "historico": x["historico_original"], "pagina": x["pagina"]}
                                   for x in abertas]
            for x in self.em_aberto[cod]:
                self.obrigacoes.append({"id": "OCX-" + cc.chave_hash(self.sol, cod, x["data"], x["valor"], x["historico"])[:16], "pagamento": None,
                                        "tributo": t["chave"], "conta": cod, "classificacao": "EM_ABERTO", "valor_total": x["valor"],
                                        "data_provisao": x["data"], "motivos": ["provisão no razão sem pagamento correspondente no e-CAC"],
                                        "origem": {"arquivo": (self.razao or {}).get("arquivo"), "pagina": x["pagina"]},
                                        "evidencia": EVID["INTERNA"], "componentes": [], "lancamentos": [], "criterios": []})

    def situacao_fiscal(self):
        sf = (self.res.get("CAIXINHA_FISCAL") or {}).get("situacao_fiscal")
        if not sf:
            self.verif("E_SITUACAO_FISCAL", "Relatório de Situação Fiscal conferido", "NAO_DETERMINADO", "EXTERNA", bloqueia=False,
                       detalhe="Relatório não recebido: conferência adicional não realizada (não impede as baixas comprovadas no e-CAC).",
                       acao="Envie o Relatório de Situação Fiscal do período.", responsavel="FISCAL")
            return
        pags = [o for o in self.obrigacoes if o.get("pagamento")]
        for it in sf.get("itens") or []:
            if it["categoria"] != "DEBITO_PENDENTE" or it["estado_vencimento"] == "A_VENCER":
                continue
            pa = (it.get("periodo_apuracao") or {}).get("competencia")
            relacionados = [o for o in pags if o.get("competencia_apuracao") == pa and
                            any(c["codigo"] == it.get("codigo_receita") for c in o.get("componentes") or [])]
            texto = (f"{it.get('codigo_receita') or ''} {it.get('denominacao') or ''} PA {mmaaaa(pa)} venc. {dmy(it.get('vencimento'))} "
                     f"saldo devedor {it.get('saldo_devedor')}")
            if relacionados:
                self.verif("E_SITUACAO_FISCAL", f"Débito pendente na RFB com pagamento no e-CAC ({texto})", "DIVERGENTE", "EXTERNA",
                           bloqueia=False, detalhe="A situação fiscal indica pendência para período com pagamento comprovado: possível pagamento "
                                                   "não alocado ou diferença. A baixa comprovada não é alterada.",
                           acao="Confira a alocação do pagamento no e-CAC.", responsavel="FISCAL", fontes=[sf.get("arquivo")])
                self.rev("DIVERGENTE", f"Situação fiscal: {texto} — há pagamento no e-CAC para o mesmo período.", "Pode haver diferença a pagar.",
                         "Conferir no e-CAC.", "FISCAL", origem=it.get("origem"))
            else:
                self.obrigacoes.append({"id": "OCX-" + it["id"][3:], "pagamento": None, "tributo": it.get("denominacao"),
                                        "classificacao": "EM_ABERTO", "valor_total": it.get("saldo_devedor"), "periodo_apuracao": mmaaaa(pa),
                                        "motivos": ["débito pendente vencido no Relatório de Situação Fiscal, sem pagamento no e-CAC"],
                                        "origem": it.get("origem"), "evidencia": EVID["EXTERNA"], "componentes": [], "lancamentos": [],
                                        "criterios": []})
        self.verif("E_SITUACAO_FISCAL", "Relatório de Situação Fiscal conferido (conferência adicional)", "CONFERIDO", "EXTERNA", bloqueia=False,
                   detalhe=f"Emitido em {dmy(sf.get('emissao'))}; itens a vencer não são pendência; 'sem pendências' não significa baixa contábil.",
                   fontes=[sf.get("arquivo")])

    # ---------------------------------------------------------------- folha (pró-labore)
    def competencia_linha(self, x):
        m = re.search(r"(?<!\d)(0[1-9]|1[0-2])/(20\d{2})(?!\d)", x["historico"])
        return f"{m.group(2)}-{m.group(1)}" if m else (x.get("data") or "")[:7] or None

    def folha(self):
        self.folha_res = None
        cod = self.contas.get("PRO_LABORE")
        dp = self.res.get("CAIXINHA_DP") or {}
        ultimo = dp.get("ultimo")
        if not cod:
            self.verif("F_FOLHA", "Conta Pró-labore a Pagar definida", "NAO_APLICAVEL", "SISTEMA", bloqueia=False,
                       detalhe="Configuração sem conta de pró-labore: conciliação da folha não executada.")
            return
        b = self.saldos.get(cod)
        if not b:
            self.verif("F_FOLHA", "Saldo do Pró-labore a Pagar no balancete", "PENDENTE", "INTERNA", conta=cod,
                       detalhe="Saldo da conta não conhecido; nada presumido.", acao="Envie o balancete com a conta.", responsavel="CONTABIL")
            return
        saldo = D(b.get("saldo_final"))
        credor = -saldo
        linhas = self.linhas.get(cod, [])
        inss, irrf, caixa = self.contas.get("INSS"), self.contas.get("IRRF"), self.contas.get("CAIXA_GERAL")
        por_comp, outros = {}, []
        for x in linhas:
            comp = self.competencia_linha(x)
            g = por_comp.setdefault(comp, {"competencia": comp, "bruto": Z, "retencoes": Z, "pagamentos": Z, "outros_debitos": Z,
                                          "linhas_retencao": [], "linhas_pagamento": []})
            if x["credito"]:
                g["bruto"] += x["credito"]
            if x["debito"]:
                ret = x["contrapartida"] in (inss, irrf) if x["contrapartida"] else any(k in x["historico"] for k in ("INSS", "IRRF", "I.R.R.F", "RETENCAO"))
                pag = x["contrapartida"] == caixa if x["contrapartida"] else any(k in x["historico"] for k in ("PAGTO", "PAGAMENTO", "PAGO"))
                if ret:
                    g["retencoes"] += x["debito"]
                    g["linhas_retencao"].append({"data": x["data"], "valor": f2(x["debito"]), "historico": x["historico_original"], "pagina": x["pagina"]})
                elif pag:
                    g["pagamentos"] += x["debito"]
                    g["linhas_pagamento"].append({"data": x["data"], "valor": f2(x["debito"]), "historico": x["historico_original"], "pagina": x["pagina"]})
                else:
                    g["outros_debitos"] += x["debito"]
                    outros.append({"data": x["data"], "valor": f2(x["debito"]), "historico": x["historico_original"], "pagina": x["pagina"]})
        comps = []
        for k in sorted(c for c in por_comp if c):
            g = por_comp[k]
            g["liquido_em_aberto"] = g["bruto"] - g["retencoes"] - g["pagamentos"] - g["outros_debitos"]
            comps.append({kk: (f2(v) if isinstance(v, Decimal) else v) for kk, v in g.items()})
        anterior = -D((self.razao_contas.get(cod) or {}).get("saldo_anterior")) if (self.razao_contas.get(cod) or {}).get("saldo_anterior") else None
        res = {"conta": self.conta_info(cod), "saldo_contabil": f2(credor), "ultimo": ultimo, "competencias": comps,
               "saldo_anterior_ao_razao": f2(anterior), "outros_debitos": outros, "baixa": None, "saldo_esperado": None, "lancamento": None,
               "situacao": None, "motivos": []}
        self.folha_res = res
        if saldo > 0:
            res.update(situacao="DIVERGENTE", motivos=["Pró-labore a Pagar com saldo DEVEDOR: não há líquido a regularizar."])
            self.verif("F_FOLHA", "Saldo do Pró-labore a Pagar credor", "DIVERGENTE", "INTERNA", conta=cod, encontrado=saldo,
                       acao="Confira a escrituração da conta.", responsavel="CONTABIL")
            return
        if not ultimo or ultimo.get("liquido") is None:
            res.update(situacao="NECESSITA_REVISAO", motivos=["Último líquido da folha não identificado (resumo mensal do Domínio)."])
            self.verif("F_FOLHA", "Último líquido do pró-labore identificado (resumo da folha)", "PENDENTE", "INTERNA", conta=cod,
                       acao="Envie o resumo mensal da folha do Domínio da última competência.", responsavel="DP")
            self.rev("NECESSITA_REVISAO", "Folha: último líquido do pró-labore não identificado.", "Regularização da folha não preparada.",
                     "Enviar o resumo mensal da folha.", "DP")
            return
        L = D(ultimo["liquido"])
        ultima = ultimo["competencia"]
        g = por_comp.get(ultima)
        checks = []
        if not g or not g["bruto"]:
            checks.append(f"provisão do pró-labore de {mmaaaa(ultima)} não localizada no razão da conta {cod}")
        else:
            if D(ultimo.get("bruto")) != g["bruto"]:
                checks.append(f"bruto no razão ({br(g['bruto'])}) ≠ bruto do resumo ({br(D(ultimo.get('bruto')))})")
            ret_resumo = D(ultimo.get("inss")) + D(ultimo.get("irrf"))
            if ret_resumo != g["retencoes"]:
                checks.append(f"retenções no razão ({br(g['retencoes'])}) ≠ INSS + IRRF do resumo ({br(ret_resumo)})")
            if g["bruto"] - g["retencoes"] - g["pagamentos"] - g["outros_debitos"] != L:
                checks.append(f"líquido em aberto de {mmaaaa(ultima)} no razão ({br(g['bruto'] - g['retencoes'] - g['pagamentos'] - g['outros_debitos'])}) "
                              f"≠ líquido do resumo ({br(L)})")
        self.verif("F_FOLHA", f"Último pró-labore ({mmaaaa(ultima)}): bruto, retenções e líquido do razão = resumo da folha",
                   "CONFERIDO" if not checks else "DIVERGENTE", "INTERNA", conta=cod, esperado=L,
                   encontrado=(g["bruto"] - g["retencoes"] - g["pagamentos"] - g["outros_debitos"]) if g else None,
                   detalhe="; ".join(checks) or "Retenções já lançadas foram identificadas e não são descontadas de novo.",
                   acao="Confira a integração do pró-labore no Domínio." if checks else None, responsavel="DP",
                   fontes=[(self.razao or {}).get("arquivo"), (ultimo.get("arquivo"))])
        if credor < L:
            res.update(situacao="DIVERGENTE", motivos=[f"saldo credor ({br(credor)}) menor que o último líquido ({br(L)})"])
            self.verif("F_FOLHA", "Saldo do Pró-labore ≥ último líquido", "DIVERGENTE", "INTERNA", conta=cod, esperado=L, encontrado=credor,
                       acao="Confira os pagamentos/integrações do pró-labore.", responsavel="CONTABIL")
            return
        baixa = credor - L
        res.update(baixa=f2(baixa), saldo_esperado=f2(L))
        if checks:
            res.update(situacao="NECESSITA_REVISAO", motivos=checks)
            self.rev("NECESSITA_REVISAO", "Folha: " + "; ".join(checks), "Regularização da folha não preparada (risco de descontar retenções "
                     "de novo ou de baixar líquido ainda não integrado).", "Confira o razão do pró-labore e reenvie.", "DP")
            return
        if baixa == 0:
            res.update(situacao="PAGA_E_CONTABILIZADA", motivos=["Saldo da conta = último líquido: nada a regularizar."])
            return
        identidade = f"CXN-FOLHA|{self.empresa}|{cod}|{self.comp}"
        anteriores = [x for x in self.ent.get("fatos_outras_sols") or [] if x["identidade"].startswith(f"CXN-FOLHA|{self.empresa}|{cod}|")]
        pend_ant = [x for x in anteriores if x["identidade"] == identidade or not any(
            l["debito"] == D(x.get("valor")) and l["contrapartida"] == caixa for l in linhas)]
        if pend_ant:
            x = pend_ant[0]
            res.update(situacao="NECESSITA_REVISAO", motivos=[f"regularização da folha já {x.get('situacao', 'proposta').lower()} na {x['sol']} "
                                                             "e não localizada no razão recebido"])
            self.rev("NECESSITA_REVISAO", f"Folha: regularização anterior ({x['sol']}, {br(D(x.get('valor')))}) não consta no razão.",
                     "Nova regularização não preparada (sem duplicidade).", "Importe/confira no Domínio e reenvie o razão.")
            return
        pol = self.folha_pol.get("data_lancamento") or {}
        motivo = None
        if pol.get("politica") == "ULTIMO_DIA_COMPETENCIA":
            data = self.fim
        elif pol.get("politica") == "DATA_FIXA" and self.inicio <= str(pol.get("data")) <= self.fim:
            data = str(pol.get("data"))
        else:
            data, motivo = None, "data da regularização não definida pela política aprovada (ou fora da competência)"
        if not self.folha_aplicavel:
            motivo = ((self.regras.get("politica_folha") or {}).get("motivo") or "política da folha não aprovada") + \
                " — a regularização exige aprovação PRÉVIA do Supervisor."
        a_, m_ = map(int, ultima.split("-"))
        anterior_comp = f"{a_ - (m_ == 1):04d}-{(m_ - 2) % 12 + 1:02d}"
        # o histórico cita a ÚLTIMA competência regularizada (a anterior à mantida em aberto), nunca a competência mantida em aberto
        hist = f"REGULARIZACAO CONFORME POLITICA CAIXINHA - PRO-LABORE LIQUIDO COMPETENCIAS ATE {mmaaaa(anterior_comp)}"
        l = self.lancamento("CAIXINHA_FOLHA", identidade, data, cod, caixa, baixa, hist, evidencia="POLITICA",
                            classificacao="REGULARIZACAO_CONFORME_POLITICA_CAIXINHA", grupo="GCX-" + cc.chave_hash(identidade)[:12],
                            origem={"arquivo": (self.razao or {}).get("arquivo"), "documento": (self.razao or {}).get("documento")},
                            motivo_incompleto=motivo, extra={"politica_folha_versao": self.folha_pol.get("versao"), "ultima_competencia": ultima,
                                                             "ultimo_liquido": f2(L)}, regras_cfg=self.cfg_aplicavel)
        res.update(situacao="REGULARIZACAO_PROPOSTA" if l["status"] == "PROPOSTO" else "REGULARIZACAO_INCOMPLETA", lancamento=l["id"])
        self.verif("F_FOLHA", "Regularização do pró-labore conforme política Caixinha", "CONFERIDO" if l["status"] == "PROPOSTO" else "PENDENTE",
                   "POLITICA", conta=cod, esperado=baixa, encontrado=baixa if l["status"] == "PROPOSTO" else None,
                   detalhe="Baixa por POLÍTICA OPERACIONAL aprovada (não é pagamento individualmente comprovado)." if l["status"] == "PROPOSTO"
                   else motivo, acao=None if l["status"] == "PROPOSTO" else
                   f"Aprove a política da folha (frase \"{(self.regras.get('politica_folha') or {}).get('frase')}\").")

    # ---------------------------------------------------------------- lançamentos
    def lancamento(self, fonte, identidade, data, debito, credito, valor, historico, evidencia, classificacao, grupo, origem=None,
                   motivo_incompleto=None, extra=None, regras_cfg=None):
        origem_doc = origem
        motivos = []
        if not (self.cfg_aplicavel if regras_cfg is None else regras_cfg):
            motivos.append("configuração da rotina Caixinha não aprovada/vigente")
        if motivo_incompleto:
            motivos.append(motivo_incompleto)
        if not credito:
            motivos.append("conta Caixa Geral não definida")
        if not data:
            motivos.append("data do lançamento não definida")
        for cod in (debito, credito):
            if cod and cod not in self.plano:
                motivos.append(f"conta {cod} inexistente no plano")
        lid = "LCX-" + cc.chave_hash(self.empresa, identidade)[:12]
        l = {"id": lid, "identidade": identidade, "origem": fonte, "status": "INCOMPLETO" if motivos else "PROPOSTO", "data": data,
             "competencia": self.comp, "debito": self.conta_info(debito) if debito else None, "credito": self.conta_info(credito) if credito else None,
             "valor": f2(valor), "historico": historico, "evidencia": EVID[evidencia], "classificacao": classificacao, "grupo": grupo,
             "documento": (origem_doc or {}).get("documento"), "arquivo": (origem_doc or {}).get("arquivo"), "sha256": (origem_doc or {}).get("sha256"),
             "pagina": (origem_doc or {}).get("pagina"), "motivos_incompleto": motivos, "aprovado": False, "escriturado": False,
             "data_origem": "política de datas da empresa (REGRAS-CAIXINHA)", **(extra or {})}
        self.lancamentos.append(l)
        self.por_id[lid] = l
        return l

    def saldos_projetados(self):
        self.projecao = {}
        mov = {}
        for l in self.lancamentos:
            v = D(l["valor"])
            if l.get("debito"):
                mov.setdefault(l["debito"]["codigo"], [Z, Z])[0] += v
            if l.get("credito"):
                mov.setdefault(l["credito"]["codigo"], [Z, Z])[1] += v
        for chave, cod in self.contas.items():
            b = self.saldos.get(cod)
            if b is None:
                continue
            d, c = mov.get(cod, [Z, Z])
            atual = D(b.get("saldo_final"))
            proj = atual + d - c
            self.projecao[cod] = {"chave": chave, "conta": self.conta_info(cod), "saldo_atual": f2(atual), "debitos_propostos": f2(d),
                                  "creditos_propostos": f2(c), "saldo_projetado": f2(proj)}
            grupo = str((self.plano.get(cod) or {}).get("grupo") or "").upper()
            if grupo == "PASSIVO" and proj > 0:
                self.verif("G_GERAL", f"Saldo projetado da conta {cod} ({chave}) não fica devedor", "DIVERGENTE", "INTERNA", conta=cod,
                           encontrado=proj, detalhe="Baixas propostas excedem o saldo credor da obrigação; propostas da conta tornadas INCOMPLETAS.",
                           acao="Confira provisões e baixas da conta (o saldo nunca é forçado).", responsavel="CONTABIL")
                for l in self.lancamentos:
                    if (l.get("debito") or {}).get("codigo") == cod and l["status"] == "PROPOSTO":
                        l["status"] = "INCOMPLETO"
                        l["motivos_incompleto"].append("baixas excedem o saldo credor da conta")
            if cod in self.contas_divergentes:
                for l in self.lancamentos:
                    if (l.get("debito") or {}).get("codigo") == cod and l["status"] == "PROPOSTO":
                        l["status"] = "INCOMPLETO"
                        l["motivos_incompleto"].append("razão × balancete divergentes nesta conta")

    def controle_caixa(self):
        cod = self.contas.get("CAIXA_GERAL")
        b = self.saldos.get(cod) if cod else None
        trib = sum((D(l["valor"]) for l in self.lancamentos if l["origem"] == "CAIXINHA_TRIBUTOS"), Z)
        folha = sum((D(l["valor"]) for l in self.lancamentos if l["origem"] == "CAIXINHA_FOLHA"), Z)
        r = self.razao_contas.get(cod) if cod else None
        self.caixa = {"conta": self.conta_info(cod) if cod else None, "saldo_inicial": f2(D(b.get("saldo_final"))) if b else None,
                      "baixas_tributarias": f2(trib), "baixas_folha": f2(folha),
                      "outras_movimentacoes": {"debitos": (r or {}).get("debitos"), "creditos": (r or {}).get("creditos"),
                                               "fonte": "razão do período (já contabilizadas)"} if r else None,
                      "saldo_projetado": f2(D(b.get("saldo_final")) - trib - folha) if b else None,
                      "aviso": "Saldo CONTÁBIL projetado (balancete − baixas propostas). Não representa conferência de dinheiro físico."}
        if not b:
            self.verif("H_CAIXA", "Saldo do Caixa Geral no balancete", "PENDENTE", "INTERNA", conta=cod,
                       detalhe="Saldo do Caixa não conhecido: projeção não calculada.", responsavel="CONTABIL")
            return
        saldo = D(b.get("saldo_final"))
        proj = saldo - trib - folha
        if saldo < 0:
            self.verif("H_CAIXA", "Caixa Geral com saldo devedor antes das baixas", "DIVERGENTE", "INTERNA", bloqueia=False, conta=cod,
                       encontrado=saldo, detalhe="Caixa com saldo CREDOR no balancete (inconsistência contábil).", responsavel="CONTABIL",
                       acao="Confira a escrituração do Caixa.")
        self.verif("H_CAIXA", "Saldo contábil projetado do Caixa Geral não fica credor", "CONFERIDO" if proj >= 0 else "DIVERGENTE", "INTERNA",
                   bloqueia=False, conta=cod, esperado=saldo, encontrado=proj,
                   detalhe=("Saldo projetado credor: as baixas excedem o saldo do Caixa (alerta; exige ciência do Supervisor)." if proj < 0 else
                            "Projeção contábil; não é conferência de dinheiro físico."), responsavel="SUPERVISOR",
                   acao="Avalie as baixas antes de aprovar." if proj < 0 else None)
        if proj < 0:
            self.rev("ALERTA_CAIXA", f"Caixa Geral ficaria com saldo credor de {br(-proj)} após as baixas.", "Saldo contábil inconsistente.",
                     "Avalie antes de aprovar (nenhum saldo é forçado).")

    # ---------------------------------------------------------------- execução
    def executar(self):
        self.por_id, self.contas_divergentes = {}, set()
        self.carregar()
        self.preparar_contabil()
        self.tributos_conciliar()
        self.situacao_fiscal()
        self.folha()
        self.saldos_projetados()
        self.controle_caixa()
        for l in self.lancamentos:
            if l["status"] == "INCOMPLETO":
                l["motivos_incompleto"] = list(dict.fromkeys(l["motivos_incompleto"]))
        return self.montar()

    def montar(self):
        ids = [l["identidade"] for l in self.lancamentos]
        repetidas = sorted({i for i in ids if ids.count(i) > 1})
        self.verif("G_GERAL", "Cada fato gera no máximo uma baixa (idempotência)", "DIVERGENTE" if repetidas else "CONFERIDO", "SISTEMA",
                   detalhe=("Identidades repetidas: " + ", ".join(repetidas)) if repetidas else "Identidade = empresa + pagamento (e-CAC) + conta.")
        trib = {}
        contas_trib = {t["chave"]: self.contas.get(t.get("conta")) for t in self.tributos}
        for chave, cod in contas_trib.items():
            if not cod or cod in trib:
                continue
            obs = [o for o in self.obrigacoes if o.get("pagamento") and any(c.get("conta") == cod for c in o.get("componentes") or [])]
            pago = sum((D(c["principal"]) for o in obs if o["classificacao"] in ("PAGA_E_CONTABILIZADA", "PAGA_NAO_CONTABILIZADA")
                        for c in o["componentes"] if c.get("conta") == cod), Z)
            ja = sum((D(c["principal"]) for o in obs if o["classificacao"] == "PAGA_E_CONTABILIZADA" for c in o["componentes"] if c.get("conta") == cod), Z)
            prop = sum((D(l["valor"]) for l in self.lancamentos if l["origem"] == "CAIXINHA_TRIBUTOS" and (l.get("debito") or {}).get("codigo") == cod), Z)
            b = self.saldos.get(cod)
            saldo = -D(b.get("saldo_final")) if b else None
            trib[cod] = {"tributo": chave, "conta": self.conta_info(cod), "saldo_contabil": f2(saldo), "pagamentos_identificados": f2(pago),
                         "ja_contabilizado": f2(ja), "baixas_propostas": f2(prop), "saldo_restante": f2(saldo - prop) if saldo is not None else None,
                         "divergencias": sum(1 for o in obs if o["classificacao"] in ("DIVERGENTE", "NECESSITA_REVISAO", "SEM_PROVISAO_IDENTIFICADA",
                                                                                     "PAGAMENTO_DUPLICADO")),
                         "em_aberto_no_razao": (self.em_aberto or {}).get(cod, []),
                         "obrigacoes": [o["id"] for o in obs]}
        tot = lambda k: f2(sum((D(x[k]) for x in trib.values() if x[k] is not None), Z))  # noqa: E731
        contagem = {k: sum(1 for v in self.verificacoes if v["resultado"] == k) for k in ("CONFERIDO", "DIVERGENTE", "PENDENTE", "NAO_APLICAVEL",
                                                                                           "NAO_DETERMINADO")}
        bloqueantes = [v for v in self.verificacoes if v["bloqueia"] and v["resultado"] in ("DIVERGENTE", "PENDENTE", "NAO_DETERMINADO")]
        por_evid = {}
        for v in self.verificacoes:
            if v["resultado"] == "CONFERIDO":
                por_evid[v["evidencia"]] = por_evid.get(v["evidencia"], 0) + 1
        classes = {k: sum(1 for o in self.obrigacoes if o.get("classificacao") == k) for k in CLASSES}
        propostos = [l for l in self.lancamentos if l["status"] == "PROPOSTO"]
        incompletos = [l for l in self.lancamentos if l["status"] == "INCOMPLETO"]
        caixa = self.contas.get("CAIXA_GERAL")
        saldos_contas = [{"conta": cod, "abertura": f2(D(self.saldos[cod].get("saldo_final"))),
                          "fonte": "saldo do balancete do período (antes das baixas propostas)"}
                         for cod in sorted({c for l in self.lancamentos for c in ((l.get("debito") or {}).get("codigo"), (l.get("credito") or {}).get("codigo")) if c})
                         if cod in self.saldos]
        return {
            "contrato": CONTRATO, "agente": "CONCILIACAO_CAIXINHA", "empresa": self.empresa, "sol": self.sol, "competencia": self.comp,
            "modo": "SIMULACAO", "fluxo": "CONCILIACAO_CAIXINHA", "executado_em": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "regras": {"configuracao": self.regras.get("configuracao"), "politica_folha": self.regras.get("politica_folha"),
                       "versao_arquivo": self.regras.get("versao"), "sha256": self.regras.get("sha256"), "contas": self.contas,
                       "politica_datas": self.pol_datas, "criterios": self.criterios},
            "verificacoes": self.verificacoes, "obrigacoes": self.obrigacoes, "lancamentos": self.lancamentos, "revisao": self.revisao,
            "tributos": {"por_conta": list(trib.values()), "total_provisionado": tot("saldo_contabil"), "total_pago": tot("pagamentos_identificados"),
                         "total_ja_contabilizado": tot("ja_contabilizado"), "baixas_propostas": tot("baixas_propostas"),
                         "saldo_restante": tot("saldo_restante"), "divergencias": sum(x["divergencias"] for x in trib.values())},
            "folha": self.folha_res, "caixa": self.caixa, "saldos_projetados": list(self.projecao.values()),
            "saldos_contas": saldos_contas,
            "versoes_entradas": self.versoes,
            "alcance": {"parcial": bool(self.parcial), "motivos": list(dict.fromkeys(self.parcial)),
                        "texto": "Conciliação contábil das obrigações da rotina Caixinha (sem extrato bancário): evidência externa = e-CAC; "
                                 "consistência interna = balancete × razão × resumo da folha; folha por política operacional aprovada."},
            "resumo": {**contagem, "bloqueantes": len(bloqueantes), "propostos": len(propostos), "incompletos": len(incompletos),
                       "revisao": len(self.revisao), "obrigacoes": classes, "conferidas_por_evidencia": por_evid,
                       "caixa_conta": caixa},
            "classes": CLASSES,
            "aviso": "SIMULAÇÃO: propostas para conferência do Supervisor. Nada aprovado, escriturado ou exportado. Saldos nunca são forçados.",
        }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Conciliação Caixinha (SIMULACAO).")
    for a in ("empresa", "sol", "competencia", "entradas", "saida"):
        p.add_argument("--" + a, required=True)
    a = p.parse_args(argv)
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", a.empresa) or not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", a.competencia):
        print("ERRO: parâmetros inválidos.", file=sys.stderr)
        return 2
    try:
        ent = json.loads(Path(a.entradas).read_text(encoding="utf-8"))
        if (ent.get("contrato"), ent.get("empresa"), ent.get("sol"), ent.get("competencia")) != (
                "ENTRADAS_CONCILIACAO_CAIXINHA_V1", a.empresa, a.sol, a.competencia):
            raise ValueError("entradas de outra empresa/SOL/competência")
        r = Conciliacao(ent).executar()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"ERRO: Conciliação Caixinha recusada: {e}", file=sys.stderr)
        return 1
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "resultado.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
