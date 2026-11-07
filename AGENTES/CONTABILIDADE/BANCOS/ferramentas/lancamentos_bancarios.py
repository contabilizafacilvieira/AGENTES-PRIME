"""Lançamentos bancários (Contabilidade/Bancos) - código local, determinístico, SEM modelo de linguagem. SIMULAÇÃO.

Uso (chamado pelo Coordenador/API depois do Financeiro; a partir da raiz AGENTES-PRIME):
    .venv/Scripts/python.exe -I AGENTES/CONTABILIDADE/BANCOS/ferramentas/lancamentos_bancarios.py --empresa <EMP> --sol <SOL>
        --competencia AAAA-MM --financeiro <resultado.json do Financeiro> --saida <pasta> [--decisoes <json>]

Usa EXCLUSIVAMENTE, da empresa selecionada (procedimento geral: AGENTES/CONTABILIDADE/BANCOS/PROCEDIMENTO.md):
- CADASTRO.md, seção "Contas bancárias": conta contábil de cada conta bancária;
- PLANO-DE-CONTAS/PLANO-DE-CONTAS.md: contas existentes (conta fora do plano nunca é usada);
- REGRAS-BANCOS.md: somente regras VALIDADAS (com origem, versão e aprovação);
- decisões do Supervisor registradas na própria SOL (valem só para o movimento decidido).
- CADASTRO.md, seção "Contas de adiantamento indicadas pelo Supervisor": única fonte de conta de adiantamento.
Não inventa conta ou enquadramento. Adiantamento só por decisão específica do movimento, na conta indicada pela empresa;
a falta de documento continua pendência (lançamento INCOMPLETO). Documento compartilhado com uma área cuja análise falhou ou
não foi concluída (--areas) torna a proposta dependente dessa área.
Conta ausente/incompatível, regra ausente ou divergência: proposta INCOMPLETA.
Pagamento de obrigação já contabilizada (relação: obrigacao_contabilizada=SIM): só regra de LIQUIDAÇÃO (nunca 2ª despesa).
Transferência entre contas próprias com as duas pontas: UM lançamento ligado aos dois movimentos.
Movimento efetivamente escriturado não é proposto novamente; proposta anterior em simulação vira revisão rastreável.
Saída: <saida>/resultado.json e <saida>/lancamentos_SIMULACAO_<SOL>.csv.
"""

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import unicodedata
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
def clientes():
    """Pasta CLIENTES (avaliada a cada uso: AGENTES_PRIME_CLIENTES em testes isolados; RAIZ/CLIENTES em produção)."""
    return Path(os.environ.get("AGENTES_PRIME_CLIENTES") or RAIZ / "CLIENTES")
VERSAO = "1.1"
PROCEDIMENTO = "AGENTES/CONTABILIDADE/BANCOS/PROCEDIMENTO.md v1.1"
TIPOS_REGRA = {"LIQUIDACAO_OBRIGACAO": "DEBITO", "DESPESA": "DEBITO", "RECEBIMENTO": "CREDITO", "RECEITA": "CREDITO",
               "ADIANTAMENTO_FORNECEDOR": "DEBITO", "ADIANTAMENTO_CLIENTE": "CREDITO"}
# grupo exigido da contrapartida para cada natureza (mesma tabela do Coordenador)
GRUPOS_POR_TIPO = {"LIQUIDACAO_OBRIGACAO": {"PASSIVO"}, "DESPESA": {"DESPESA", "CUSTO"}, "RECEBIMENTO": {"ATIVO"}, "RECEITA": {"RECEITA"}}
GRUPOS_POR_TIPO.update(ADIANTAMENTO_FORNECEDOR={'ATIVO'}, ADIANTAMENTO_CLIENTE={'PASSIVO'})
CHAVES_CONDICAO = {"direcao", "tipo_banco", "historico_contem", "favorecido_cnpj", "suporte", "conta", "obrigacao_contabilizada", "competencia_desde"}


def norm(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", t).strip()


def digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def tabela_md(texto: str, titulo: str) -> list:
    linhas, dentro, cab = [], False, None
    for l in texto.splitlines():
        if l.startswith("## "):
            dentro = norm(l[3:]).startswith(norm(titulo))
            cab = None if dentro else cab
            continue
        if not dentro or not l.strip().startswith("|"):
            continue
        celulas = [c.strip() for c in l.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in celulas if c):
            continue
        if cab is None:
            cab = [norm(c) for c in celulas]
            continue
        if any(celulas):
            linhas.append(dict(zip(cab, celulas)))
    return linhas


def chave_conta(banco, agencia, conta) -> str:
    return f"{digitos(banco).zfill(3)}-{digitos(agencia).lstrip('0') or '0'}-{digitos(conta).lstrip('0') or '0'}"


def sha(caminho: Path):
    return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16] if caminho.exists() else None


def condicoes(texto: str):
    """'chave=valor; chave=valor' → dict. Chave desconhecida = regra inválida (não aplicada)."""
    saida = {}
    for parte in [p.strip() for p in str(texto or "").split(";") if p.strip()]:
        if "=" not in parte:
            return None
        k, v = (x.strip() for x in parte.split("=", 1))
        if k not in CHAVES_CONDICAO or not v:
            return None
        if k == 'competencia_desde' and not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', v):
            return None
        saida[k] = v
    return saida or None


def ler_regras(empresa: str) -> tuple:
    arquivo = clientes() / empresa / "REGRAS-BANCOS.md"
    if not arquivo.exists():
        return [], ["REGRAS-BANCOS.md inexistente para a empresa: nenhuma regra de lançamento bancário aprovada."]
    regras, avisos = [], []
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # AGENTES/CONTABILIDADE (independe de RAIZ)
    import governanca_regras
    for l in tabela_md(governanca_regras.ler_texto(arquivo), "Regras"):
        situacao = norm(l.get("SITUACAO"))
        r = {"id": l.get("REGRA"), "versao": l.get("VERSAO"), "condicoes_texto": l.get("CONDICOES"), "condicoes": condicoes(l.get("CONDICOES")),
             "tipo": norm(l.get("TIPO")).replace(" ", "_"), "contrapartida": l.get("CONTRAPARTIDA"),
             "exige_suporte": norm(l.get("EXIGE SUPORTE") or "SIM") != "NAO", "historico": l.get("HISTORICO") or "",
             "origem": l.get("ORIGEM"), "situacao": situacao, "aprovacao": l.get("APROVACAO")}
        if situacao == "TESTE_FICTICIO":
            # regra de TESTE da amostra fictícia: só vale em empresa com o marcador; nunca é aprovação do Supervisor
            if not (clientes() / empresa / "AMOSTRA-FICTICIA.json").is_file():
                avisos.append(f"Regra {r['id']} de TESTE FICTÍCIO ignorada: empresa real (sem o marcador AMOSTRA-FICTICIA.json).")
                continue
        elif situacao != "VALIDADA":
            continue
        if situacao == "VALIDADA":
            # confirmação vinculada a empresa, regra e versão (frase, responsável, data); texto livre ou formato antigo não basta
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # AGENTES/CONTABILIDADE (independe de RAIZ)
            import governanca_regras
            conf = governanca_regras.confirmacao_bancos(r["aprovacao"], empresa, r["id"], r["versao"])
            r["confirmacao"] = conf["situacao"]
            if not conf["valida"]:
                avisos.append(f"Regra {r['id']} VALIDADA sem confirmação suficiente ({conf['motivo']}): não aplicada; "
                              "confirmação do Supervisor necessária (Empresas → Definições necessárias).")
                continue
        if not r["condicoes"] or r["tipo"] not in TIPOS_REGRA or not r["aprovacao"]:
            avisos.append(f"Regra {r['id']} VALIDADA mas inválida (condições, tipo ou aprovação ausentes): não aplicada.")
            continue
        regras.append(r)
    return regras, avisos


class Escrituracao:
    def __init__(self, empresa, competencia, sol, financeiro, decisoes):
        self.empresa, self.competencia, self.sol, self.fin, self.decisoes = empresa, competencia, sol, financeiro, decisoes
        base = clientes() / empresa
        self.plano = {digitos(l.get("CODIGO REDUZIDO")) or l.get("CODIGO REDUZIDO"): l.get("DESCRICAO", "")
                      for l in tabela_md((base / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md").read_text(encoding="utf-8"), "Contas utilizadas")
                      if l.get("CODIGO REDUZIDO") and norm(l.get('TIPO')) != 'SINTETICA'
                      and (not (base / 'empresa-local.json').exists() or norm(l.get('TIPO')) == 'ANALITICA')}
        # grupo de cada conta (coluna "Grupo" do plano, definida pelo Supervisor): valida natureza × conta; vazio = não definido
        self.grupos = {digitos(l.get("CODIGO REDUZIDO")): norm(l.get("GRUPO")).replace(" ", "_")
                       for l in tabela_md((base / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md").read_text(encoding="utf-8"), "Contas utilizadas")
                       if digitos(l.get("CODIGO REDUZIDO"))}
        self.contas_banco = {}
        for l in tabela_md((base / "CADASTRO.md").read_text(encoding="utf-8"), "Contas bancarias"):
            if digitos(l.get("BANCO")) and digitos(l.get("CONTA")):
                self.contas_banco[chave_conta(l["BANCO"], l.get("AGENCIA"), l["CONTA"])] = digitos(l.get("CONTA CONTABIL")) or None
        # contas de adiantamento indicadas expressamente pelo Supervisor (por natureza); sem indicação, nenhuma é aceita
        self.adiantamento = {}
        for l in tabela_md((base / "CADASTRO.md").read_text(encoding="utf-8"), "Contas de adiantamento"):
            natureza = norm(l.get("NATUREZA")).replace(" ", "_")
            if natureza.startswith("ADIANTAMENTO_") and digitos(l.get("CONTA CONTABIL")):
                self.adiantamento.setdefault(natureza, set()).add(digitos(l.get("CONTA CONTABIL")))
        self.areas = {}
        self.regras, self.avisos = ler_regras(empresa)
        local = base / 'empresa-local.json'
        self.fontes = {"cadastro": sha(base / "CADASTRO.md"), "plano": sha(base / "PLANO-DE-CONTAS" / "PLANO-DE-CONTAS.md"),
                       "regras": sha(base / "REGRAS-BANCOS.md")}
        self.fontes['cadastro_local'] = sha(local)
        self.docs = {d["id"]: d for d in financeiro["documentos"]}
        self.rels = {r["id"]: r for r in financeiro["relacao"]}
        self.lancamentos, self.nao_escriturados, self.pendencias = [], [], []

    def pendencia(self, mov, descricao):
        self.pendencias.append({"id": f"PB-{len(self.pendencias) + 1:02d}", "movimento": mov, "descricao": descricao})
        return descricao

    def conta(self, codigo):
        c = digitos(codigo)
        return {"codigo": c, "descricao": self.plano[c]} if c and c in self.plano else None

    def conta_banco(self, chave_banco, mov_id, faltas):
        codigo = self.contas_banco.get(chave_banco)
        conta = self.conta(codigo)
        if not codigo:
            faltas.append(self.pendencia(mov_id, f"Conta bancária {chave_banco} sem conta contábil no CADASTRO.md (seção Contas bancárias)."))
        elif not conta:
            faltas.append(self.pendencia(mov_id, f"Conta contábil {codigo} da conta bancária {chave_banco} não existe no plano de contas."))
        return conta

    def fatos(self, m):
        tipos = {d["tipo"] for d in m["documentos"]}
        cnpjs = {d["favorecido_cnpj"] for d in m["documentos"] if d.get("favorecido_cnpj")}
        cnpjs |= {self.rels[r]["favorecido_cnpj"] for r in m["relacao"] if self.rels[r].get("favorecido_cnpj")}
        obrig = {self.rels[r]["obrigacao_contabilizada"] for r in m["relacao"] if self.rels[r].get("obrigacao_contabilizada")}
        return tipos, cnpjs, obrig

    def atende(self, regra, m, tipos, cnpjs, obrig) -> bool:
        for k, v in regra["condicoes"].items():
            if k == 'competencia_desde' and self.competencia < v:
                return False
            if k == "direcao" and norm(v) != m["direcao"]:
                return False
            if k == "tipo_banco" and norm(v) != norm(m.get("tipo_banco")):
                return False
            if k == "historico_contem" and norm(v) not in norm(m["descricao"]):
                return False
            if k == "favorecido_cnpj" and digitos(v) not in cnpjs:
                return False
            if k == "suporte" and norm(v) not in tipos:
                return False
            if k == "conta" and chave_conta(*(re.split(r"[-/ ]", v, 2) + ["", ""])[:3]) != m["conta"]:
                return False
            if k == "obrigacao_contabilizada" and {norm(v)} != obrig:
                return False
        return TIPOS_REGRA[regra["tipo"]] == m["direcao"]

    def historico(self, modelo, m):
        nat = next((d for d in m["documentos"] if d["papel"] == "NATUREZA"), None) or (m["documentos"][0] if m["documentos"] else {})
        dados = {"favorecido": nat.get("favorecido") or "", "documento": f"{nat.get('tipo', '').replace('_', ' ')} {nat.get('numero') or ''}".strip(),
                 "data": m["data"], "descricao": m["descricao"]}
        return re.sub(r"\{(\w+)\}", lambda x: str(dados.get(x.group(1), x.group(0))), modelo or "").strip() or self.historico_movimento(m)

    def historico_movimento(self, m, adiantamento=False):
        partes = ['PAGAMENTO' if m['direcao']=='DEBITO' else 'RECEBIMENTO']
        nomes = list(dict.fromkeys(d.get('favorecido') for d in m.get('documentos', []) if d.get('favorecido')))
        refs = list(dict.fromkeys(f"{d['tipo'].replace('_', ' ')} {d['numero']}" for d in m.get('documentos', []) if d.get('numero')))
        if nomes: partes.append(' / '.join(nomes))
        if refs: partes.append('REF. ' + ' / '.join(refs))
        partes.append('EM ' + dt.date.fromisoformat(m['data']).strftime('%d/%m/%Y'))
        if adiantamento: partes.append('SEM SUPORTE DOCUMENTAL - ADIANTAMENTO A CONFERIR')
        partes.append(m['descricao'])
        return ' - '.join(partes)

    def gerar(self):
        movs = {m["id"]: m for m in self.fin["movimentos"]}
        for m in self.fin["movimentos"]:
            if m.get("ja_escriturado_em"):
                e = m["ja_escriturado_em"]
                self.nao_escriturados.append({"movimento": m["id"], "motivo": f"já ESCRITURADO (lançamento efetivo) na {e['sol']} (sem novo lançamento)"})
                continue
            tp = m.get("transferencia_propria") or {}
            if m["direcao"] == "CREDITO" and tp.get("par"):
                self.nao_escriturados.append({"movimento": m["id"], "motivo": f"ponta de crédito da transferência própria {tp['par']} (lançamento único na ponta de débito)"})
                continue
            faltas = []
            acompanhamentos = []
            banco = self.conta_banco(m["conta"], m["id"], faltas)
            decisao = next((d for d in reversed(self.decisoes.get(m["id"], [])) if d.get("tipo") == "CONTRAPARTIDA"), None)
            regra, contra, tipo, origem, historico = None, None, None, None, None
            if tp:
                tipo = "TRANSFERENCIA_PROPRIA"
                outra = tp.get("conta_destino")
                contra = self.conta_banco(outra, m["id"], faltas)
                origem = "transferência entre contas próprias (contas do CADASTRO.md)"
                historico = f"TRANSFERENCIA ENTRE CONTAS PROPRIAS {m['conta']} > {outra}"
                if not tp.get("par"):
                    faltas.append(self.pendencia(m["id"], f"Transferência para a conta própria {outra}: a outra ponta não foi localizada; "
                                                          "confirme antes de escriturar (evita dupla contabilização)."))
            elif decisao:
                tipo = decisao.get("natureza_tipo")
                contra = self.conta(decisao.get("conta"))
                origem = f"decisão do Supervisor em {decisao.get('em')} (somente este movimento): {decisao.get('justificativa')}"
                historico = decisao.get("historico") or self.historico_movimento(m)
                if not contra:
                    faltas.append(self.pendencia(m["id"], f"Conta {decisao.get('conta')} da decisão do Supervisor não existe no plano de contas."))
                if TIPOS_REGRA.get(tipo) != m["direcao"]:
                    faltas.append(self.pendencia(m["id"], f"Tipo {tipo} da decisão incompatível com movimento de {m['direcao']}."))
            else:
                tipos, cnpjs, obrig = self.fatos(m)
                aplicaveis = [r for r in self.regras if not r['tipo'].startswith('ADIANTAMENTO_') and self.atende(r, m, tipos, cnpjs, obrig)]
                if "SIM" in obrig:
                    despesa = [r for r in aplicaveis if r["tipo"] == "DESPESA"]
                    aplicaveis = [r for r in aplicaveis if r["tipo"] != "DESPESA"]
                    if despesa:
                        self.pendencia(m["id"], f"Obrigação já contabilizada (relação): regra(s) de DESPESA {', '.join(r['id'] for r in despesa)} "
                                                "desconsiderada(s) para não gerar segunda despesa.")
                contrapartidas = {digitos(r["contrapartida"]) for r in aplicaveis}
                if not aplicaveis:
                    faltas.append(self.pendencia(m["id"], "Sem regra aprovada (VALIDADA) para este movimento: contrapartida não definida. "
                                                          "Decida a contrapartida deste caso ou aprove uma regra."))
                elif len(contrapartidas) > 1:
                    faltas.append(self.pendencia(m["id"], f"Regras conflitantes ({', '.join(r['id'] for r in aplicaveis)}) com contrapartidas "
                                                          "diferentes; nenhuma foi escolhida."))
                else:
                    regra = aplicaveis[0]
                    tipo, origem = regra["tipo"], f"regra {regra['id']} v{regra['versao']} ({regra['origem']}; {regra['aprovacao']})"
                    contra = self.conta(regra["contrapartida"])
                    historico = self.historico(regra["historico"], m)
                    if not contra:
                        faltas.append(self.pendencia(m["id"], f"Conta {regra['contrapartida']} da regra {regra['id']} não existe no plano de contas."))
                    if regra["exige_suporte"] and m["situacao"] != "COM_SUPORTE":
                        faltas.append(self.pendencia(m["id"], f"Regra {regra['id']} exige documento da natureza; situação do movimento: "
                                                              f"{m['situacao']}."))
            # adiantamento: só a conta indicada pelo Supervisor para esta empresa (grupo compatível não basta)
            if contra and str(tipo).startswith("ADIANTAMENTO_") and contra["codigo"] not in self.adiantamento.get(tipo, set()):
                indicadas = ", ".join(sorted(self.adiantamento.get(tipo, set()))) or "nenhuma"
                faltas.append(self.pendencia(m["id"], f"Conta {contra['codigo']} não é a conta de adiantamento indicada pelo Supervisor para "
                                                      f"{tipo} nesta empresa (indicada: {indicadas}); a classificação fica pendente."))
                contra = None
            # natureza × grupo da conta (regra ou decisão): incompatível ou não verificável → a conta não é proposta
            if contra and tipo in GRUPOS_POR_TIPO:
                grupo = self.grupos.get(contra["codigo"], "")
                exigidos = " ou ".join(sorted(GRUPOS_POR_TIPO[tipo]))
                if contra["codigo"] in set(self.contas_banco.values()):
                    faltas.append(self.pendencia(m["id"], f"Conta {contra['codigo']} é a conta contábil de uma conta bancária da empresa e não é "
                                                          f"compatível como contrapartida de {tipo}."))
                    contra = None
                elif not grupo:
                    faltas.append(self.pendencia(m["id"], f"Grupo da conta {contra['codigo']} não definido no plano de contas: a compatibilidade com "
                                                          f"{tipo} (exige {exigidos}) não pode ser verificada. O Supervisor precisa definir o grupo."))
                    contra = None
                elif grupo not in GRUPOS_POR_TIPO[tipo]:
                    faltas.append(self.pendencia(m["id"], f"Conta {contra['codigo']} (grupo {grupo}) não é compatível com {tipo}, que exige conta "
                                                          f"do grupo {exigidos}; a combinação não é proposta."))
                    contra = None
            if m["situacao"] == "AMBIGUO":
                faltas.append(self.pendencia(m["id"], "Correspondência ambígua na conferência financeira: decisão do Supervisor necessária."))
            if m.get('sugestoes') and m['situacao'] in ('SEM_SUPORTE', 'COMPROVANTE_SEM_NATUREZA'):
                faltas.append(self.pendencia(m['id'], 'Documento candidato localizado para este movimento; conferir o vínculo sugerido antes de concluir a proposta por ausência de suporte.'))
            # leitura pendente só impede afirmar ausência de suporte quando a proposta depende de suporte
            # (sem regra, ou regra que exige documento); regra VALIDADA sem exigência de suporte (ex.: tarifa) não é afetada
            if (m.get('documentacao_inconclusiva') and m['situacao'] in ('SEM_SUPORTE', 'COMPROVANTE_SEM_NATUREZA')
                    and (regra is None or regra['exige_suporte'])):
                faltas.append(self.pendencia(m['id'], 'Documento recebido com leitura pendente no lote; não é possível afirmar ausência de suporte deste movimento. Confira os arquivos: '
                                             + ', '.join(m['documentacao_inconclusiva'])))
            for d in m.get("divergencias", []):
                faltas.append(self.pendencia(m["id"], f"Divergência na conferência financeira: {d}"))
            # documento também destinado a outra área (ex.: nota ao Fiscal) cuja análise não foi entregue: proposta depende dela
            for d in m.get("documentos", []):
                for area, info in self.areas.items():
                    if d["arquivo"] in info["arquivos"] and info["estado"] not in ("ENTREGUE", "ENTREGUE_COM_PENDENCIAS"):
                        faltas.append(self.pendencia(m["id"], f"Documento {d['arquivo']} depende da área {area.title()}, cuja análise está "
                                                              f"{info['estado']}; a proposta não pode ser concluída sem esse resultado."))
            # a decisão de contrapartida do caso NUNCA supre documento: natureza, origem do recebimento e divergências seguem abertas
            if not tp and regra is None and m["situacao"] in ("SEM_SUPORTE", "COMPROVANTE_SEM_NATUREZA"):
                if m["direcao"] == "CREDITO":
                    texto = "Recebimento sem documento que comprove a origem."
                elif m["situacao"] == "COMPROVANTE_SEM_NATUREZA":
                    texto = "Pagamento comprovado, mas sem documento da natureza (nota, guia, recibo ou contrato)."
                else:
                    texto = "Movimento sem documento de suporte identificado."
                # adiantamento decidido também não supre o documento: continua falta (lançamento INCOMPLETO, visível na fila)
                faltas.append(self.pendencia(m["id"], texto + (" A contrapartida decidida para o caso não supre o documento." if decisao else "")))
            debito, credito = (contra, banco) if m["direcao"] == "DEBITO" else (banco, contra)
            if tipo == "TRANSFERENCIA_PROPRIA":
                debito, credito = contra, banco
            self.lancamentos.append({
                "id": f"LAN-{len(self.lancamentos) + 1:03d}", "status": "PROPOSTO" if not faltas and debito and credito else "INCOMPLETO",
                "data": m["data"], "valor": m["valor"], "debito": debito, "credito": credito, "historico": historico or self.historico_movimento(m),
                "fato": {"LIQUIDACAO_OBRIGACAO": "liquidação de obrigação já reconhecida (sem nova despesa)",
                         "DESPESA": "reconhecimento da despesa e pagamento no mesmo ato", "RECEBIMENTO": "recebimento (liquidação de direito)",
                         "RECEITA": "reconhecimento da receita e recebimento", "TRANSFERENCIA_PROPRIA": "transferência entre contas próprias",
                         "ADIANTAMENTO_FORNECEDOR": "adiantamento a fornecedor; suporte documental pendente",
                         "ADIANTAMENTO_CLIENTE": "adiantamento de cliente; suporte documental pendente"}.get(tipo, "não definido"),
                "tipo": tipo, "origem": origem, "regra": regra and {"id": regra["id"], "versao": regra["versao"]},
                "movimentos": [m["id"]] + ([tp["par"]] if tp.get("par") else []), "conta_bancaria": m["conta"],
                # identidade do fato: movimento(s) do extrato (id estável derivado de empresa, conta, data, valor, documento e histórico)
                "identidade": "BANCO:" + "+".join(sorted([m["id"]] + ([tp["par"]] if tp.get("par") else []))),
                "regra_situacao": regra and regra["situacao"],
                "documentos": [{"arquivo": d["arquivo"], "tipo": d["tipo"], "papel": d["papel"], "numero": d.get("numero")} for d in m["documentos"]],
                "situacao_financeira": m["situacao"], "pendencias": faltas,
                "acompanhamentos": acompanhamentos,
                "faltas_codigos": sorted({codigo_falta(f) for f in faltas}),
                "natureza_registro": "PROPOSTA_SIMULACAO",          # não é lançamento escriturado
                # revisão rastreável: propostas anteriores (SIMULAÇÃO) para o mesmo movimento, nesta ou em outra SOL
                "revisao_de": [p for mid in [m["id"]] + ([tp["par"]] if tp.get("par") else [])
                               for p in (movs.get(mid) or {}).get("propostas_anteriores", [])]})

    def montar(self) -> dict:
        propostos = [l for l in self.lancamentos if l["status"] == "PROPOSTO"]
        soma = lambda lista: f"{sum((Decimal(l['valor']) for l in lista), Decimal('0.00')):.2f}"
        return {
            "agente": "CONTABILIDADE/BANCOS", "versao": VERSAO, "procedimento": PROCEDIMENTO, "sol": self.sol, "empresa": self.empresa,
            "competencia": self.competencia, "modo": "SIMULACAO",
            "executado_em": dt.datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "aviso": "SIMULAÇÃO para conferência humana. Nada foi liberado nem importado no Domínio.",
            "fontes_da_empresa": self.fontes, "regras_validadas_disponiveis": [r["id"] for r in self.regras], "avisos_regras": self.avisos,
            "lancamentos": self.lancamentos, "nao_escriturados": self.nao_escriturados, "pendencias": self.pendencias,
            "resumo": {"lancamentos": len(self.lancamentos), "propostos": len(propostos), "incompletos": len(self.lancamentos) - len(propostos),
                       "valor_propostos": soma(propostos), "valor_incompletos": soma([l for l in self.lancamentos if l["status"] != "PROPOSTO"]),
                       "nao_escriturados": len(self.nao_escriturados), "pendencias": len(self.pendencias),
                       "revisoes_de_propostas_anteriores": sum(1 for l in self.lancamentos if l["revisao_de"])},
            "registro": "Todos os lançamentos acima são PROPOSTAS geradas em SIMULAÇÃO, não lançamentos escriturados. "
                        "Somente lançamento efetivamente escriturado (etapa futura de aprovação/liberação) impede nova proposta.",
        }


def codigo_falta(texto: str) -> str:
    """Classificação estável do que falta (para a tela separar decisão possível agora × documento adicional)."""
    t = norm(texto)
    if 'DOCUMENTO CANDIDATO' in t:
        return 'VINCULO_PENDENTE'
    if 'DOCUMENTO RECEBIDO COM LEITURA PENDENTE' in t:
        return 'LEITURA_PENDENTE'
    if 'CONTA DE ADIANTAMENTO INDICADA' in t:
        return 'ADIANTAMENTO_NAO_INDICADO'
    if 'DEPENDE DA AREA' in t:
        return 'DEPENDE_AREA'
    for chave, codigo in (("NAO PODE SER VERIFICADA", "GRUPO_INDEFINIDO"), ("NAO E COMPATIVEL", "INCOMPATIVEL"), ("SEM REGRA APROVADA", "SEM_REGRA"), ("REGRAS CONFLITANTES", "REGRA_CONFLITANTE"), ("OUTRA PONTA", "TRANSFERENCIA_SEM_PAR"),
                          ("AMBIGUA", "AMBIGUO"), ("INCOMPATIVEL", "DECISAO_INCOMPATIVEL"), ("NAO EXISTE NO PLANO", "CONTA"),
                          ("SEM CONTA CONTABIL", "CONTA"), ("CONTA DE ADIANTAMENTO", "CONTA"), ("EXIGE DOCUMENTO DA NATUREZA", "SUPORTE"), ("SEM DOCUMENTO DE SUPORTE", "SUPORTE"),
                          ("SEM DOCUMENTO DA NATUREZA", "SUPORTE"), ("COMPROVE A ORIGEM", "SUPORTE"),
                          ("DIVERGENCIA", "DIVERGENCIA")):
        if chave in t:
            return codigo
    return "OUTRO"


def csv_lancamentos(lancamentos: list) -> str:
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    w.writerow(["lancamento", "status", "data", "debito", "credito", "valor", "historico", "movimentos", "documentos", "origem", "pendencias", "acompanhamento_documental"])
    for l in lancamentos:
        w.writerow([l["id"], l["status"], l["data"], (l["debito"] or {}).get("codigo", "PENDENTE"), (l["credito"] or {}).get("codigo", "PENDENTE"),
                    l["valor"].replace(".", ","), l["historico"], " ".join(l["movimentos"]), " ".join(d["arquivo"] for d in l["documentos"]),
                    l["origem"] or "", " | ".join(l["pendencias"]), " | ".join(l.get('acompanhamentos', []))])
    return saida.getvalue()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    for a in ("--empresa", "--sol", "--competencia", "--financeiro", "--saida"):
        p.add_argument(a, required=True)
    p.add_argument("--decisoes")
    p.add_argument("--areas", help="situação das outras áreas: {AREA: {estado, documentos: [caminhos]}}")
    args = p.parse_args()
    fin = json.loads(Path(args.financeiro).read_text(encoding="utf-8"))
    if fin.get("empresa") != args.empresa or fin.get("sol") != args.sol or fin.get("competencia") != args.competencia:
        print(json.dumps({"erro": "RESULTADO_FINANCEIRO_DE_OUTRA_SOL"}))
        return 2
    decisoes = json.loads(Path(args.decisoes).read_text(encoding="utf-8")) if args.decisoes else {}
    e = Escrituracao(args.empresa, args.competencia, args.sol, fin, decisoes)
    if args.areas:
        for area, info in json.loads(Path(args.areas).read_text(encoding="utf-8")).items():
            e.areas[area] = {"estado": info.get("estado") or "NAO_INFORMADO",
                             "arquivos": {str(x).rsplit("/", 1)[-1] for x in info.get("documentos", [])}}
    e.gerar()
    resultado = e.montar()
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    (saida / f"lancamentos_SIMULACAO_{args.sol}.csv").write_text(csv_lancamentos(resultado["lancamentos"]), encoding="cp1252", errors="replace")
    print(json.dumps({"resultado": "ESCRITURACAO_PREPARADA", "resumo": resultado["resumo"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
