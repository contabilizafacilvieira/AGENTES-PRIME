"""BASE INICIAL da empresa para a competência M: balancete de encerramento de M−1 (contas e saldos) + book contábil do mesmo
período (composições, títulos em aberto, evidências, pendências). Código local; nada é aprovado, escriturado ou importado.

Armazenamento (por empresa, nunca misturado):
  CLIENTES/<EMP>/BASE-INICIAL/<AAAA-MM>/fontes/      originais recebidos (preservados; nunca sobrescritos)
  CLIENTES/<EMP>/BASE-INICIAL/<AAAA-MM>/base.json    versão vigente (RASCUNHO ou CONFIRMADA)
  CLIENTES/<EMP>/BASE-INICIAL/<AAAA-MM>/VERSOES/     versões anteriores
  CLIENTES/<EMP>/BASE-INICIAL/INDICE.json            resumo das bases (fonte de VIGÊNCIA: qualquer mudança torna desatualizadas as
                                                    conferências e aprovações que usaram a versão anterior)
Regras: saldos D/C preservados como informados (inclusive contrários à natureza); zero sem D/C fica sem natureza; saldos de abertura
e composições NÃO são lançamentos; conta nova não tem saldo presumido (exige definição, inclusive zero explícito); divergências são
mostradas com valores, diferença e fontes, sem ajuste automático; base incompleta pode ser salva, marcada como NÃO confirmada.
"""
import base64
import calendar
import datetime as dt
import hashlib
import json
import re
import secrets
from decimal import Decimal
from pathlib import Path

import balancete_anterior
import book_contabil
import empresas_local as el
import plano_hierarquia

LIMITE_ARQUIVO = 40 * 1024 * 1024
FRASE = "CONFIRMO BASE INICIAL {emp} {comp}"
CIENCIAS = {
    "identificacao_balancete": "Empresa/CNPJ ou período não constam no arquivo do balancete: o Supervisor declara que é o balancete de "
                               "encerramento da data-base desta empresa.",
    "estabelecimento": "CNPJ do balancete é de outro estabelecimento da mesma empresa (mesma raiz).",
    "consolidado": "Balancete CONSOLIDADO: os saldos somam os estabelecimentos listados.",
    "problemas_balancete": "Linhas do balancete com problemas de leitura ou que não conferem (anterior + D − C ≠ atual).",
    "conflitos_contas": "Contas do balancete NÃO adotadas no plano (código/classificação/descrição diferentes do plano atual).",
    "sem_book": "Base sem book contábil (composições não recebidas).",
    "book_identificacao": "Book sem CNPJ/competência identificáveis, ou CNPJ/competência diferentes do esperado.",
    "divergencias_book": "Composições divergentes do balancete (sem ajuste automático).",
    "composicoes_sem_conta": "Composições sem conta correspondente no balancete.",
    "metodos_desconhecidos": "Composições com método não reconhecido (nenhum método presumido).",
    "pendencias_book": "Pendências registradas no book (permanecem abertas; o aplicativo não as resolve).",
    "seguranca_book": "Book com macros ou vínculos externos (não executados; valores dependentes não verificados).",
}


# Orientação das pendências da base inicial, em linguagem de negócio: (título curto, problema, impacto, o que fazer).
# Nível: BLOQUEIO (impede confirmar a base), ATENCAO (recomenda revisão; não impede a base) e INFORMATIVO (não impede nada).
GUIA = {
    "balancete": ("Balancete do mês anterior não enviado", "A base ainda não tem o balancete de encerramento do mês anterior.",
                  "Sem ele não há contas nem saldos iniciais para conferir.", "Envie o balancete na fase Balancete anterior."),
    "identificacao_balancete": ("Empresa ou período não identificados no balancete",
                                "O arquivo não informa o CNPJ e/ou o período do balancete.",
                                "Não é possível garantir que o balancete é desta empresa e do mês certo.",
                                "Confira o arquivo e marque como conferido, informando a justificativa."),
    "estabelecimento": ("Balancete de outro estabelecimento", "O CNPJ do balancete é de outro estabelecimento da mesma empresa.",
                        "Os saldos podem não corresponder ao cadastro desta empresa.",
                        "Confirme que este é o balancete correto e marque como conferido."),
    "consolidado": ("Balancete consolidado", "O balancete soma mais de um estabelecimento.",
                    "Os saldos iniciais serão os consolidados dos estabelecimentos listados.",
                    "Confira os estabelecimentos e marque como conferido."),
    "classificacao_repetida": ("Contas com a mesma classificação contábil", "Duas contas possuem a mesma classificação contábil.",
                               "A hierarquia não pode determinar com segurança a posição dessas contas.",
                               "Conferir no plano contábil qual classificação está correta."),
    "problemas_balancete": ("Saldos que não conferem no balancete",
                            "Em algumas contas, saldo anterior + débitos − créditos não chega ao saldo informado, ou a leitura ficou incompleta.",
                            "Esses saldos podem estar errados ou mal lidos; nada foi corrigido automaticamente.",
                            "Confira cada conta no relatório original e marque como conferido."),
    "contas": ("Contas do balancete ainda não aplicadas", "As contas extraídas do balancete ainda não foram aplicadas ao plano da empresa.",
               "Sem isso, os saldos não podem ser usados.", "Na fase Balancete anterior, use Aplicar contas ao plano."),
    "conflitos_contas": ("Contas diferentes do plano atual", "Algumas contas do balancete têm código, classificação ou descrição diferentes do plano atual.",
                         "O plano atual foi mantido para essas contas.", "Confira as contas e marque como conferido."),
    "tipos": ("Contas com classificação que não pôde ser lida",
              "A classificação destas contas não pôde ser lida com segurança, então não foi possível saber se são sintéticas ou analíticas.",
              "Contas sem tipo não podem receber saldo nem lançamentos.",
              "Confira a classificação no relatório original e defina o tipo em Configuração da empresa › Plano contábil atual."),
    "grupos": ("Contas sem grupo contábil identificado",
               "Não foi possível identificar com segurança o grupo contábil destas contas.",
               "A conta não pode ser usada automaticamente nas análises patrimoniais.",
               "Confirme se a conta pertence a Ativo, Passivo, Patrimônio Líquido, Contas de Resultado ou Outros."),
    "saldos": ("Contas sem saldo inicial", "Estas contas não constam no balancete ou foram criadas no aplicativo.",
               "O saldo inicial nunca é presumido (nem zero); sem ele, o saldo final não é calculado.",
               "Informe o saldo inicial de cada conta (zero também precisa ser informado)."),
    "sem_book": ("Book do mês anterior não enviado", "A base ainda não tem o book com as composições dos saldos.",
                 "Os saldos não poderão ser comparados com as composições.",
                 "Envie o book na fase Book / composições ou marque como conferido para seguir sem ele."),
    "book_identificacao": ("Empresa ou data do book não confirmadas", "O book não informa o CNPJ ou a data-base esperada.",
                           "Não é possível garantir que o book é desta empresa e do mês certo.", "Confira o arquivo e marque como conferido."),
    "divergencias_book": ("Composições diferentes do balancete", "O total de algumas composições não bate com o saldo do balancete.",
                          "A diferença precisa ser entendida; nada foi ajustado automaticamente.",
                          "Confira cada composição e marque como conferido."),
    "composicoes_sem_conta": ("Composições sem conta no balancete", "Algumas abas do book não correspondem a nenhuma conta do balancete.",
                              "Essas composições não foram usadas.", "Confira as abas e marque como conferido."),
    "metodos_desconhecidos": ("Método de composição não reconhecido", "Algumas composições informam um método que o aplicativo não conhece.",
                              "Nenhum método foi presumido para elas.", "Confira o método com o responsável e marque como conferido."),
    "pendencias_book": ("Pendências anotadas no book", "O book traz pendências registradas no mês anterior.",
                        "Elas continuam abertas; o aplicativo não as resolve.", "Leia as pendências e marque como conferido."),
    "seguranca_book": ("Book com macros ou vínculos externos", "O arquivo contém macros ou vínculos com outras planilhas.",
                       "Nada disso foi executado; valores que dependem deles não foram verificados.",
                       "Confira os valores no arquivo original e marque como conferido."),
    "dominio": ("Contas criadas aqui e ainda não confirmadas no Domínio",
                "Estas contas foram criadas no aplicativo e ninguém confirmou que existem no Domínio com o mesmo código.",
                "Não impedem a base, mas lançamentos nelas não entram no arquivo TXT.",
                "Crie a conta no Domínio (manualmente) e confirme a correspondência aqui."),
    "sem_composicao": ("Contas com saldo sem composição no Book",
                       "A conta possui saldo no fechamento, mas não foi encontrada uma composição correspondente no Book.",
                       "O saldo existe contabilmente, porém sua composição ainda não foi confirmada.",
                       "Confira o saldo e informe/valide a composição ou registre a justificativa da conferência."),
}


def agora():
    return dt.datetime.now().astimezone().isoformat()


def competencia(v) -> str:
    v = str(v or "").strip()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", v):
        raise ValueError("Competência inválida; use AAAA-MM (mês dos documentos que serão processados).")
    return v


def data_base(comp: str) -> str:
    """Competência M usa o balancete de ENCERRAMENTO de M−1: data-base = último dia de M−1."""
    a, m = map(int, comp.split("-"))
    a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return dt.date(a, m, calendar.monthrange(a, m)[1]).isoformat()


def sha_obj(o) -> str:
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _dec(v):
    return None if v is None else Decimal(str(v))


class BaseInicial:
    def __init__(self, gestor: "el.Empresas"):
        self.g = gestor

    # ------------------------------------------------------------ armazenamento
    def raiz(self, ident) -> Path:
        return self.g.base(ident) / "BASE-INICIAL"

    def pasta(self, ident, comp) -> Path:
        return self.raiz(ident) / competencia(comp)

    def ler(self, ident, comp):
        return el.ler(self.pasta(ident, comp) / "base.json")

    def nova(self, ident, comp):
        e = self.g.obter(ident)
        return {"contrato": "BASE_INICIAL_V1", "empresa": ident, "cnpj": e.get("cnpj"), "competencia": comp, "data_base": data_base(comp),
                "versao": 0, "situacao": "RASCUNHO", "balancete": None, "book": None, "saldos_definidos": {}, "ciencias": {},
                "contas_aplicadas": None, "historico": []}

    def gravar(self, ident, comp, base, motivo):
        p = self.pasta(ident, comp)
        anterior = el.ler(p / "base.json")
        if anterior:
            el.gravar(p / "VERSOES" / f"base-{anterior['versao']:04d}-{secrets.token_hex(3)}.json", anterior)
            if anterior.get("situacao") == "CONFIRMADA":
                base["confirmacao_anterior"] = anterior.get("confirmacao")
                motivo += " (a confirmação anterior deixou de valer; conferências que usaram a versão anterior ficam desatualizadas)"
        base["versao"] = (anterior or {}).get("versao", 0) + 1
        base["situacao"] = "RASCUNHO"
        base.pop("confirmacao", None)
        base.setdefault("historico", []).append({"versao": base["versao"], "em": agora(), "motivo": motivo})
        el.gravar(p / "base.json", base)
        self._indice(ident)
        return base

    def _indice(self, ident):
        r = self.raiz(ident)
        itens = {}
        for p in sorted(r.glob("*/base.json")):
            b = el.ler(p)
            itens[b["competencia"]] = {"versao": b["versao"], "situacao": b["situacao"], "data_base": b["data_base"],
                                       "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        el.gravar(r / "INDICE.json", {"empresa": ident, "bases": itens})

    def _receber(self, ident, d, tipo):
        comp = competencia(d.get("competencia"))
        nome = Path(el.limpo(d.get("nome"))).name
        if not nome:
            raise ValueError("Informe o arquivo.")
        try:
            dados = base64.b64decode(d.get("conteudo", ""), validate=True)
        except Exception:
            raise ValueError("Arquivo inválido.")
        if not dados or len(dados) > LIMITE_ARQUIVO:
            raise ValueError("Envie um arquivo de até 40 MB.")
        return comp, nome, dados

    def _guardar_original(self, ident, comp, tipo, nome, dados) -> str:
        sha = hashlib.sha256(dados).hexdigest()
        alvo = self.pasta(ident, comp) / "fontes" / f"{tipo}-{sha[:12]}{Path(nome).suffix.lower()}"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        if alvo.exists():
            if hashlib.sha256(alvo.read_bytes()).hexdigest() != sha:
                raise ValueError("Arquivo de origem divergente já existe com o mesmo nome; nada foi sobrescrito.")
        else:
            alvo.write_bytes(dados)
        return str(alvo.relative_to(self.g.base(ident))).replace("\\", "/")

    def _previa(self, ident, comp, tipo, nome, dados, resultado):
        token = secrets.token_hex(16)
        p = self.g.runtime / "previas"
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{token}.bin").write_bytes(dados)
        el.gravar(p / f"{token}.json", {"empresa": ident, "competencia": comp, "tipo": tipo, "nome": nome,
                                        "sha256": hashlib.sha256(dados).hexdigest(), "resultado": resultado})
        return token

    def _token(self, ident, d, tipo):
        token = str(d.get("token") or "")
        if not re.fullmatch("[a-f0-9]{32}", token):
            raise ValueError("Prévia inválida; envie o arquivo novamente.")
        p = self.g.runtime / "previas"
        info = el.ler(p / f"{token}.json")
        if not info or info.get("empresa") != ident or info.get("tipo") != tipo:
            raise ValueError("Prévia de outra empresa, de outro tipo ou não encontrada.")
        dados = (p / f"{token}.bin").read_bytes()
        if hashlib.sha256(dados).hexdigest() != info["sha256"]:
            raise ValueError("Prévia alterada; envie o arquivo novamente.")
        return info, dados

    # ------------------------------------------------------------ etapa 2: balancete anterior
    def _linhas_tabela(self, nome, dados):
        ext = Path(nome).suffix.lower()
        if ext == ".pdf":
            return None
        fake = {"nome": nome, "conteudo": base64.b64encode(dados).decode()}
        if ext not in (".csv", ".txt", ".xls", ".xlsx"):
            raise ValueError("Balancete: envie PDF do Domínio, XLSX, XLS ou CSV.")
        return _ler_tabular(fake)

    def conferir_balancete(self, ident, comp, lido):
        e = self.g.obter(ident)
        meta = lido.get("meta") or {}
        db = data_base(comp)
        bloqueios, ciencias, info = [], [], []
        cnpj_rel = re.sub(r"\D", "", meta.get("cnpj") or "")
        cnpj_cad = re.sub(r"\D", "", e.get("cnpj") or "")
        if not cnpj_rel:
            ciencias.append("identificacao_balancete")
            info.append("CNPJ não identificado no arquivo do balancete.")
        elif cnpj_rel == cnpj_cad:
            info.append(f"CNPJ do balancete {meta['cnpj']} = cadastro.")
        elif cnpj_rel[:8] == cnpj_cad[:8]:
            ciencias.append("estabelecimento")
            info.append(f"CNPJ do balancete {meta['cnpj']} é de outro estabelecimento da mesma raiz do cadastro ({e.get('cnpj')}).")
        else:
            bloqueios.append(f"CNPJ do balancete {meta['cnpj']} é de OUTRA empresa (cadastro {e.get('cnpj')}). Nada foi salvo.")
        per = meta.get("periodo") or {}
        if not per.get("fim"):
            if "identificacao_balancete" not in ciencias:
                ciencias.append("identificacao_balancete")
            info.append(f"Período não identificado no arquivo; a base exige o balancete encerrado em {db}.")
        elif per["fim"] != db:
            bloqueios.append(f"Balancete encerrado em {per['fim']}, mas a competência {comp} exige o encerramento de {db} (mês anterior). "
                             "Nada foi salvo.")
        else:
            info.append(f"Período {per.get('inicio') or '?'} a {per['fim']}: encerramento do mês anterior à competência {comp}.")
        ab = meta.get("abrangencia") or {"tipo": "NAO_INFORMADA", "estabelecimentos": []}
        if ab.get("tipo") == "CONSOLIDADO":
            ciencias.append("consolidado")
            info.append("Balancete CONSOLIDADO dos estabelecimentos: " + ", ".join(ab.get("estabelecimentos") or ["(não listados)"]) + ".")
        if meta.get("empresa") and e.get("nome") and balancete_anterior.chave(meta["empresa"]) != balancete_anterior.chave(e["nome"]):
            info.append(f"Nome no relatório ({meta['empresa']}) difere da razão social cadastrada ({e['nome']}); conferir.")
        com_problema = [c for c in lido["contas"] if c.get("problemas")]
        if com_problema or lido["totais"].get("linhas_que_nao_conferem") or lido.get("limites"):
            ciencias.append("problemas_balancete")
        if not lido["contas"]:
            bloqueios.append("Nenhuma conta extraída do balancete. Nada foi salvo.")
        return {"data_base_exigida": db, "bloqueios": bloqueios, "ciencias_exigidas": ciencias, "informacoes": info,
                "abrangencia": ab, "contas_com_problema": len(com_problema)}

    def balancete(self, ident, d):
        if d.get("salvar"):
            info, dados = self._token(ident, d, "balancete")
            comp, nome, lido = info["competencia"], info["nome"], info["resultado"]
            if competencia(d.get("competencia")) != comp:
                raise ValueError("A prévia é de outra competência.")
            conf = self.conferir_balancete(ident, comp, lido)
            if conf["bloqueios"]:
                raise ValueError(" ".join(conf["bloqueios"]))
            if d.get("confirmado") is not True:
                raise ValueError("Confira as contas extraídas e confirme o recebimento do balancete.")
            base = self.ler(ident, comp) or self.nova(ident, comp)
            dif = _diferencas_balancete((base.get("balancete") or {}).get("contas") or [], lido["contas"]) if base.get("balancete") else None
            original = self._guardar_original(ident, comp, "balancete", nome, dados)
            base["balancete"] = dict(lido, arquivo=nome, original=original, sha256=info["sha256"], recebido_em=agora(), conferencia=conf)
            base["contas_aplicadas"] = None
            motivo = f"balancete {nome} recebido" + (" (reimportação: " + _resumo_dif(dif) + ")" if dif else "")
            if base.get("grupos_confirmados"):
                self._reanalisar_balancete(base)
            self.gravar(ident, comp, base, motivo)
            el.gravar(self.pasta(ident, comp) / "analise.json", {"em": agora(), "versao_algoritmo": plano_hierarquia.VERSAO_ANALISE,
                                                                  "origem": "análise no recebimento do balancete"})
            return self.situacao(ident, comp)
        comp, nome, dados = self._receber(ident, d, "balancete")
        try:
            lido = balancete_anterior.ler(nome, dados, self._linhas_tabela(nome, dados))
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Não foi possível ler o balancete ({type(exc).__name__}). Envie o PDF do Domínio ou uma planilha.") from exc
        conf = self.conferir_balancete(ident, comp, lido)
        atual = self.ler(ident, comp)
        dif = _diferencas_balancete((atual.get("balancete") or {}).get("contas") or [], lido["contas"]) if atual and atual.get("balancete") else None
        token = self._previa(ident, comp, "balancete", nome, dados, lido)
        return {"token": token, "competencia": comp, "arquivo": nome, "formato": lido["formato"], "meta": lido["meta"], "conferencia": conf,
                "totais": lido["totais"], "duvidas": lido["duvidas"], "limites": lido.get("limites", []),
                "linhas_ignoradas": lido.get("linhas_ignoradas"), "aviso": lido["aviso"], "contas": lido["contas"],
                "reimportacao": dif, "pode_salvar": not conf["bloqueios"]}

    # ------------------------------------------------------------ etapa 3: contas e saldos
    def comparar_contas(self, ident, base):
        e = self.g.obter(ident)
        plano = {c["codigo"]: c for c in e.get("plano", [])}
        por_class = {}
        for c in e.get("plano", []):
            por_class.setdefault(c.get("classificacao"), []).append(c["codigo"])
        novas, iguais, alteradas, conflitos = [], [], [], []
        for c in (base.get("balancete") or {}).get("contas", []):
            cod = c.get("codigo")
            if not cod:
                conflitos.append({"conta": c, "motivo": "conta sem código reduzido no balancete; não incluída automaticamente"})
                continue
            p = plano.get(cod)
            if p is None:
                outros = [x for x in por_class.get(c["classificacao"], []) if x != cod]
                if outros:
                    conflitos.append({"conta": c, "motivo": f"classificação {c['classificacao']} já existe no plano com o código "
                                                            f"{', '.join(outros)}; códigos nunca são substituídos"})
                else:
                    novas.append(c)
                continue
            mud = [k for k in ("classificacao", "descricao") if el.limpo(p.get(k)) != el.limpo(c.get(k))]
            (alteradas if mud else iguais).append({"conta": c, "plano": {k: p.get(k) for k in ("codigo", "classificacao", "descricao", "grupo", "tipo")},
                                                    "campos": mud} if mud else c)
        presentes = {c.get("codigo") for c in (base.get("balancete") or {}).get("contas", [])}
        ausentes = [{k: c.get(k) for k in ("codigo", "classificacao", "descricao", "grupo", "tipo", "origem")}
                    for c in e.get("plano", []) if c["codigo"] not in presentes]
        return {"novas": novas, "iguais": iguais, "alteradas": alteradas, "conflitos": conflitos, "ausentes_no_balancete": ausentes}

    def contas(self, ident, d):
        comp = competencia(d.get("competencia"))
        base = self.ler(ident, comp)
        if not base or not base.get("balancete"):
            raise ValueError("Importe e confira o balancete do mês anterior (etapa 2) antes de aplicar as contas.")
        cmp_ = self.comparar_contas(ident, base)
        ancoras = (base["balancete"].get("ancoras_grupo") or [])            # só ramos SEM grupo identificável
        if not d.get("salvar"):
            return {"competencia": comp, "resumo": {k: len(v) for k, v in cmp_.items()}, **cmp_, "ancoras_grupo": ancoras,
                    "analise_plano": base["balancete"].get("analise_plano"),
                    "aviso": "Contas novas são incluídas no plano; contas alteradas/conflitantes só com adoção expressa; contas ausentes do "
                             "balancete são MANTIDAS (nunca excluídas). Tipo e grupo são identificados automaticamente pela hierarquia; "
                             "confirme apenas os ramos que a estrutura não permite identificar."}
        if d.get("confirmado") is not True:
            raise ValueError("Confira as contas e confirme a aplicação.")
        grupos = {}
        for k, g in (d.get("grupos") or {}).items():
            if not g:
                continue
            g = {"RECEITA": "RESULTADO", "DESPESA": "RESULTADO", "CUSTO": "RESULTADO"}.get(g, g)   # nomes antigos aceitos
            if g not in plano_hierarquia.GRUPOS_CONTABEIS:
                raise ValueError(f"Grupo inválido para {k}: use Ativo, Passivo, Patrimônio Líquido, Contas de Resultado ou Outros.")
            grupos[k] = g
        if grupos:                    # confirmação do Supervisor para ramos ambíguos: reanalisa a árvore com ela (auditável)
            base["grupos_confirmados"] = dict(base.get("grupos_confirmados") or {}, **grupos)
            self._reanalisar_balancete(base)
            cmp_ = self.comparar_contas(ident, base)
        e = self.g.obter(ident)
        texto_regras = (self.g.base(ident) / "REGRAS-BANCOS.md").read_text(encoding="utf-8") if (self.g.base(ident) / "REGRAS-BANCOS.md").is_file() else ""
        plano = [dict(c) for c in e.get("plano", [])]
        por_cod = {c["codigo"]: c for c in plano}
        adotar = {str(x) for x in (d.get("adotar") or [])}
        origem = f"BALANCETE {base['data_base']} ({base['balancete']['arquivo']})"
        incluidas, adotadas = [], []
        for c in cmp_["novas"]:
            n = {"linha": c.get("origem"), "codigo": c["codigo"], "classificacao": c["classificacao"], "descricao": c["descricao"],
                 "grupo": "", "tipo": "", "observacao": "", "origem": origem, "dominio": "CONSTA_NO_BALANCETE", "superior": c.get("superior")}
            plano.append(n)
            por_cod[n["codigo"]] = n
            incluidas.append(n["codigo"])
        for x in cmp_["alteradas"]:
            cod = x["conta"]["codigo"]
            if cod in adotar:
                if re.search(r"\|\s*" + re.escape(cod) + r"\s*\|", texto_regras):
                    raise ValueError(f"Conta {cod} usada em regra bancária: revise a regra antes de adotar a alteração do balancete.")
                p = por_cod[cod]
                p.setdefault("versoes_anteriores", []).append({k: p.get(k) for k in ("classificacao", "descricao")} | {"ate": agora()})
                p.update(classificacao=x["conta"]["classificacao"], descricao=x["conta"]["descricao"], origem=origem)
                adotadas.append(cod)
        for x in cmp_["conflitos"]:
            cod = x["conta"].get("codigo")
            if cod and cod in adotar:
                c = x["conta"]
                plano.append({"linha": c.get("origem"), "codigo": cod, "classificacao": c["classificacao"], "descricao": c["descricao"],
                              "grupo": "", "tipo": "", "observacao": "classificação compartilhada com outro código; confira",
                              "origem": origem, "dominio": "CONSTA_NO_BALANCETE"})
                adotadas.append(cod)
        preenchidas = _aplicar_derivados(plano, base["balancete"]["contas"])
        for banco in e.get("contas", []):
            p = por_cod.get(banco["contabil"])
            if not p or p.get("grupo") != "ATIVO":
                raise ValueError("A aplicação removeria ou alteraria a conta bancária " + banco["contabil"] + "; nada foi salvo.")
        self.g.atualizar(ident, {"plano": plano, "plano_origem": {"nome": base["balancete"]["arquivo"], "sha256": base["balancete"]["sha256"],
                                                                 "origem": {"formato": "BALANCETE_ANTERIOR", "competencia_base": comp}},
                                 "cadastro_confirmado": False, "piloto": False})
        base["contas_aplicadas"] = {"em": agora(), "balancete_sha256": base["balancete"]["sha256"], "incluidas": len(incluidas),
                                    "adotadas": adotadas, "grupos_confirmados": grupos, "nao_adotadas": [x["conta"].get("codigo") for x in
                                    cmp_["alteradas"] + cmp_["conflitos"] if x["conta"].get("codigo") not in adotar],
                                    "grupos_preenchidos": preenchidas["grupos"], "tipos_preenchidos": preenchidas["tipos"]}
        self.gravar(ident, comp, base, f"contas do balancete aplicadas ao plano ({len(incluidas)} incluída(s), {len(adotadas)} adotada(s))")
        return self.situacao(ident, comp)

    # ------------------------------------------------------------ reanálise (algoritmo novo sobre a base já gravada)
    def _reanalisar_balancete(self, base):
        """Reaplica a árvore do plano sobre as contas já extraídas (sem reler arquivos) e refaz o confronto do book."""
        bal = base["balancete"]
        contas = bal["contas"]
        if base.get("grupos_confirmados"):
            plano_hierarquia.anotar(contas, grupos_confirmados=base["grupos_confirmados"])
        novo = balancete_anterior.analisar({k: v for k, v in bal.items() if k in ("formato", "meta", "contas", "linhas_ignoradas", "limites")})
        if base.get("grupos_confirmados"):           # analisar() reconstrói a árvore: reaplica as confirmações do Supervisor
            arv = plano_hierarquia.anotar(novo["contas"], grupos_confirmados=base["grupos_confirmados"])
            novo["analise_plano"] = arv["resumo"]
            novo["ancoras_grupo"] = [{"classificacao": r_["classificacao"], "descricao": r_["descricao"], "grupo_sugerido": ""}
                                     for r_ in arv["resumo"]["ramos_para_confirmar"]]
        for k in ("contas", "duvidas", "ancoras_grupo", "analise_plano", "analise_versao", "totais"):
            bal[k] = novo[k]
        if base.get("book"):
            base["book"]["confronto"] = book_contabil.confrontar(base["book"], bal["contas"], base["data_base"])

    def reanalisar(self, ident, d):
        """Recalcula tipos, grupos, elegibilidade para composição no book e pendências usando os arquivos já enviados (os
        originais não são lidos de novo nem alterados). Metadados derivados ficam marcados como AUTOMÁTICOS; o histórico registra
        a reanálise. O plano só recebe tipo/grupo onde estavam vazios (definições do Supervisor nunca são substituídas)."""
        comp = competencia(d.get("competencia"))
        if d.get("confirmado") is not True:
            raise ValueError("Confirme a reanálise da base.")
        base = self.ler(ident, comp)
        if not base or not base.get("balancete"):
            raise ValueError("Não há balancete nesta base para reanalisar.")
        antes = [x for x in self.definicoes(ident, comp, base) if not x.get("resolvida")]
        hash_antes = sha_obj({k: base.get(k) for k in ("balancete", "book")})
        self._reanalisar_balancete(base)
        e = self.g.obter(ident)
        plano = [dict(c) for c in e.get("plano", [])]
        preenchidas = {"tipos": 0, "grupos": 0}
        aplicadas = (base.get("contas_aplicadas") or {}).get("balancete_sha256") == base["balancete"]["sha256"]
        if aplicadas:
            preenchidas = _aplicar_derivados(plano, base["balancete"]["contas"])
            if preenchidas["tipos"] or preenchidas["grupos"]:
                self.g.atualizar(ident, {"plano": plano, "cadastro_confirmado": False, "piloto": False})
        depois = [x for x in self.definicoes(ident, comp, base) if not x.get("resolvida")]
        resumo = {"em": agora(), "versao_algoritmo": plano_hierarquia.VERSAO_ANALISE, "tipos_preenchidos": preenchidas["tipos"],
                  "grupos_preenchidos": preenchidas["grupos"],
                  "pendencias_antes": {x["chave"]: x.get("quantidade", 1) for x in antes},
                  "pendencias_depois": {x["chave"]: x.get("quantidade", 1) for x in depois},
                  "origem": "REANALISE_AUTOMATICA (metadados derivados; nada foi informado pelo Supervisor)"}
        mudou = sha_obj({k: base.get(k) for k in ("balancete", "book")}) != hash_antes or preenchidas["tipos"] or preenchidas["grupos"]
        if mudou:
            base.setdefault("reanalises", []).append(resumo)
            self.gravar(ident, comp, base, f"reanálise automática da estrutura do plano (algoritmo v{plano_hierarquia.VERSAO_ANALISE}): "
                                           f"{preenchidas['tipos']} tipo(s) e {preenchidas['grupos']} grupo(s) preenchidos no plano; "
                                           "pendências recalculadas; arquivos originais não alterados")
        el.gravar(self.pasta(ident, comp) / "analise.json", dict(resumo, mudou=bool(mudou)))
        r_ = self.situacao(ident, comp)
        r_["reanalise"] = dict(resumo, mudou=bool(mudou))
        return r_

    # ------------------------------------------------------------ etapa 4: book
    def book(self, ident, d):
        if d.get("salvar"):
            info, dados = self._token(ident, d, "book")
            comp = info["competencia"]
            if competencia(d.get("competencia")) != comp:
                raise ValueError("A prévia é de outra competência.")
            if d.get("confirmado") is not True:
                raise ValueError("Confira a leitura do book e confirme o recebimento.")
            base = self.ler(ident, comp)
            if not base or not base.get("balancete"):
                raise ValueError("Importe o balancete (etapa 2) antes do book.")
            lido = info["resultado"]
            original = self._guardar_original(ident, comp, "book", info["nome"], dados)
            base["book"] = dict(lido, arquivo=info["nome"], original=original, sha256=info["sha256"], recebido_em=agora(),
                                confronto=book_contabil.confrontar(lido, base["balancete"]["contas"], base["data_base"]),
                                conferencia=self._conferir_book(ident, comp, lido))
            self.gravar(ident, comp, base, f"book {info['nome']} recebido")
            return self.situacao(ident, comp)
        comp, nome, dados = self._receber(ident, d, "book")
        base = self.ler(ident, comp)
        if not base or not base.get("balancete"):
            raise ValueError("Importe o balancete do mês anterior (etapa 2) antes do book: as composições são confrontadas com ele.")
        try:
            lido = book_contabil.ler(nome, dados)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Não foi possível ler o book ({type(exc).__name__}).") from exc
        confronto = book_contabil.confrontar(lido, base["balancete"]["contas"], base["data_base"])
        token = self._previa(ident, comp, "book", nome, dados, lido)
        return {"token": token, "competencia": comp, "arquivo": nome, "resumo": lido["resumo"], "abas": lido["abas"], "alertas": lido["alertas"],
                "seguranca": lido["seguranca"], "conferencia": self._conferir_book(ident, comp, lido), "confronto": confronto,
                "pendencias": lido["pendencias"][:300], "evidencias": lido["evidencias"][:300], "historico_baixas": len(lido["historico_baixas"]),
                "aviso": lido["aviso"]}

    def _conferir_book(self, ident, comp, lido):
        e = self.g.obter(ident)
        meta = lido.get("meta") or {}
        info, ciencias = [], []
        raiz = re.sub(r"\D", "", e.get("cnpj") or "")[:8]
        cnpjs = [re.sub(r"\D", "", c) for c in meta.get("cnpjs") or []]
        outros = [c for c in cnpjs if c[:8] != raiz]
        if outros:
            return {"bloqueios": [f"Book menciona CNPJ de outra empresa ({', '.join(meta['cnpjs'])}); cadastro {e.get('cnpj')}. Nada foi salvo."],
                    "ciencias_exigidas": [], "informacoes": []}
        db = data_base(comp)
        comps = meta.get("competencias_mencionadas") or []
        datas = sorted({c["data_base"] for c in lido.get("composicoes", []) if c.get("data_base")})
        if not cnpjs:
            ciencias.append("book_identificacao")
            info.append("CNPJ não identificado no book.")
        else:
            info.append("CNPJ(s) no book da mesma raiz do cadastro: " + ", ".join(meta["cnpjs"]) + ".")
        if datas and datas != [db]:
            ciencias.append("book_identificacao")
            info.append(f"Data(s)-base das composições {', '.join(datas)}; esperada {db}.")
        elif not datas and db[:7] not in comps:
            ciencias.append("book_identificacao")
            info.append(f"Data-base do book não identificada; esperada {db}.")
        if meta.get("mencoes_consolidado"):
            info.append("Book menciona consolidação: " + " | ".join(meta["mencoes_consolidado"][:2]))
        return {"bloqueios": [], "ciencias_exigidas": sorted(set(ciencias)), "informacoes": info}

    # ------------------------------------------------------------ etapa 5: definições pendentes
    def saldos(self, ident, base):
        """Saldo de abertura por código reduzido: balancete (saldo atual, D/C como informado) ou definição EXPRESSA do Supervisor."""
        saida = {}
        for c in (base.get("balancete") or {}).get("contas", []):
            if c.get("codigo") and c.get("saldo_atual") is not None:
                saida[c["codigo"]] = {"saldo": c["saldo_atual"], "natureza": c.get("natureza_atual"), "origem": "BALANCETE",
                                      "classificacao": c["classificacao"], "tipo": c.get("tipo")}
        for cod, s in (base.get("saldos_definidos") or {}).items():
            if cod not in saida:
                saida[cod] = dict(s, origem="DEFINIDO_PELO_SUPERVISOR")
        return saida

    def definicoes(self, ident, comp, base=None):
        base = base or self.ler(ident, comp)
        e = self.g.obter(ident)
        itens = []

        def item(chave_, titulo, detalhe, acao, bloqueia=True, ref=None, lista=None):
            x = {"chave": chave_, "titulo": titulo, "detalhe": detalhe, "acao": acao, "bloqueia_confirmacao": bloqueia}
            if ref is not None:
                x["referencia"] = ref
                c = (base or {}).get("ciencias", {}).get(chave_)
                x["resolvida"] = bool(c and c.get("referencia") == ref)
                x["ciencia"] = c if x["resolvida"] else None
            if lista is not None:
                x["itens"] = lista[:300]
                x["quantidade"] = len(lista)
            g = GUIA.get(chave_)
            if g:
                x.update(titulo_simples=g[0], problema=g[1], impacto=g[2], o_que_fazer=g[3])
            x["nivel"] = "BLOQUEIO" if bloqueia else "ATENCAO"
            itens.append(x)
            return x
        if not base or not base.get("balancete"):
            item("balancete", "Balancete do mês anterior não recebido", f"Envie o balancete de encerramento de {data_base(comp)}.", "ETAPA_2")
            return itens
        bal = base["balancete"]
        conf = bal.get("conferencia") or {}
        # classificação REPETIDA: item próprio (Bloqueio); nenhuma posição na hierarquia é presumida, nada é renumerado ou fundido
        repetidas = {}
        for c in bal["contas"]:
            repetidas.setdefault(c.get("classificacao_normalizada") or c["classificacao"], []).append(c)
        repetidas = {k: v for k, v in repetidas.items() if len(v) > 1}
        if repetidas:
            lista_rep = [f"{c.get('codigo') or ''} {c['classificacao']} {c['descricao']}" for v in repetidas.values() for c in v]
            item("classificacao_repetida", "Contas com a mesma classificação contábil",
                 f"{len(repetidas)} classificação(ões) usada(s) por mais de uma conta; nenhuma posição foi presumida.", "CIENCIA",
                 ref=sha_obj(["repetida", bal["sha256"], lista_rep]), lista=lista_rep)

        def eh_repetida(msg):
            return msg.startswith("classificação ") and "repetida" in msg
        for k in conf.get("ciencias_exigidas", []):
            lista = None
            if k == "problemas_balancete":
                lista = [f"{c.get('codigo') or ''} {c['classificacao']} {c['descricao']}: {'; '.join(m for m in c['problemas'] if not eh_repetida(m))}"
                         for c in bal["contas"] if any(not eh_repetida(m) for m in c.get("problemas", []))]
                lista += bal.get("limites") or []
                if not lista:
                    continue                       # só havia classificação repetida: já é o item próprio acima
            if k == "consolidado":
                lista = (conf.get("abrangencia") or {}).get("estabelecimentos") or []
            x = item(k, CIENCIAS[k], " ".join(conf.get("informacoes", [])) if k != "problemas_balancete" else "Nada foi corrigido automaticamente.",
                     "CIENCIA", ref=sha_obj([k, bal["sha256"], lista]), lista=lista)
            if k == "problemas_balancete":
                x["saldos_nao_conferem"] = _saldos_nao_conferem(bal["contas"])
        aplicadas = base.get("contas_aplicadas") or {}
        if aplicadas.get("balancete_sha256") != bal["sha256"]:
            item("contas", "Contas do balancete ainda não aplicadas ao plano", "Confira as contas extraídas e aplique (etapa 3).", "ETAPA_3")
        else:
            nao = aplicadas.get("nao_adotadas") or []
            if nao:
                item("conflitos_contas", CIENCIAS["conflitos_contas"], "O plano atual foi mantido para estas contas.", "CIENCIA",
                     ref=sha_obj(["conflitos", bal["sha256"], nao]), lista=nao)
        plano = {c["codigo"]: c for c in e.get("plano", [])}
        presentes = {c.get("codigo") for c in bal["contas"]}
        sem_tipo = [f"{c['codigo']} {c.get('classificacao')} {c.get('descricao')}" for c in plano.values()
                    if c["codigo"] in presentes and not c.get("tipo")]
        if sem_tipo:
            item("tipos", "Contas sem tipo (analítica/sintética) definido", "A classificação não permitiu montar a hierarquia com "
                 "segurança; nenhum tipo foi presumido.", "DEFINIR_CONTA", lista=sem_tipo)
        sem_grupo = [f"{c['codigo']} {c.get('classificacao')} {c.get('descricao')}" for c in plano.values()
                     if c["codigo"] in presentes and not c.get("grupo")]
        if sem_grupo:
            item("grupos", "Contas sem grupo contábil", "A estrutura principal do plano não permitiu identificar o grupo com "
                 "segurança; nenhum grupo foi presumido.", "DEFINIR_CONTA", lista=sem_grupo)
        saldos = self.saldos(ident, base)
        sem_saldo = [c for c in plano.values() if c.get("tipo") in ("ANALITICA", "ANALÍTICA") and c["codigo"] not in saldos]
        if sem_saldo:
            item("saldos", "Contas analíticas sem saldo inicial definido",
                 f"Ausentes do balancete ou criadas no aplicativo: o saldo em {base['data_base']} não é presumido (nem zero). Defina cada um "
                 "(inclusive zero explícito).", "SALDO_INICIAL",
                 lista=[f"{c['codigo']} {c.get('classificacao')} {c.get('descricao')}" + (" · criada no aplicativo" if c.get("origem") == "CRIADA_NO_APLICATIVO" else "")
                        for c in sem_saldo])
        bk = base.get("book")
        if not bk:
            item("sem_book", CIENCIAS["sem_book"], "Envie o book do mesmo período (etapa 4) ou declare ciência de que a base fica sem composições.",
                 "ETAPA_4_OU_CIENCIA", ref=sha_obj(["sem_book", bal["sha256"]]))
        else:
            cf = bk.get("conferencia") or {}
            for k in cf.get("ciencias_exigidas", []):
                item(k, CIENCIAS[k], " ".join(cf.get("informacoes", [])), "CIENCIA", ref=sha_obj([k, bk["sha256"]]))
            conf_b = bk.get("confronto") or {}
            comps = conf_b.get("composicoes", [])
            div = [f"{x['aba']}: composição {x.get('saldo_composicao')} × balancete {x.get('saldo_balancete')} (diferença {x.get('diferenca')})"
                   for x in comps if x["conferencia_numerica"] in ("DIVERGENTE", "SINAL_A_CONFIRMAR")]
            if div:
                item("divergencias_book", CIENCIAS["divergencias_book"], "Valores, diferença e fontes abaixo; nada foi ajustado.", "CIENCIA",
                     ref=sha_obj(["div", bk["sha256"], bal["sha256"], div]), lista=div)
            sem = [f"{x['aba']}: {x['identificador'].get('classificacao') or x['identificador'].get('codigo') or 'sem identificador'}"
                   for x in comps if x["conferencia_numerica"] == "SEM_CONTA_CORRESPONDENTE"]
            if sem:
                item("composicoes_sem_conta", CIENCIAS["composicoes_sem_conta"], "Nada foi presumido.", "CIENCIA",
                     ref=sha_obj(["sem", bk["sha256"], bal["sha256"], sem]), lista=sem)
            met = [f"{x['aba']}: '{x.get('metodo_informado')}'" for x in comps if x["metodo"] == "DESCONHECIDO"]
            if met:
                item("metodos_desconhecidos", CIENCIAS["metodos_desconhecidos"], "Informe o método ao Supervisor; nenhum foi escolhido.",
                     "CIENCIA", ref=sha_obj(["met", bk["sha256"], met]), lista=met)
            pend = [f"{p.get('conta') or ''} · {p.get('titulo') or p.get('detalhe') or ''} · {p.get('situacao') or 'situação não informada'}"
                    for p in bk.get("pendencias", [])]
            if pend:
                item("pendencias_book", CIENCIAS["pendencias_book"], "Permanecem abertas na base; o aplicativo não as resolve.", "CIENCIA",
                     ref=sha_obj(["pend", bk["sha256"]]), lista=pend)
            sem_c = conf_b.get("contas_com_saldo_sem_composicao") or []
            if sem_c:
                # só contas ANALÍTICAS patrimoniais com saldo ≠ 0 chegam aqui (book_contabil.confrontar): ATENÇÃO, não bloqueia a base;
                # a conferência do Supervisor (com justificativa) vale para esta lista e estes saldos — mudou, volta a ficar aberta.
                # Nenhuma composição é presumida e nenhum ajuste é gerado.
                lista_sc = [f"{c.get('codigo') or ''} {c['classificacao']} {c.get('descricao') or ''}" for c in sem_c]
                item("sem_composicao", "Contas com saldo sem composição no Book",
                     "Contas patrimoniais analíticas com saldo, sem composição identificada no Book.", "CIENCIA", bloqueia=False,
                     ref=sha_obj(["sem_composicao", bk.get("sha256"), bal["sha256"],
                                  sorted([c.get("codigo"), c["classificacao"], str(c.get("saldo"))] for c in sem_c)]),
                     lista=lista_sc)
            seg = bk.get("seguranca") or {}
            if seg.get("macros") or seg.get("vinculos_externos"):
                item("seguranca_book", CIENCIAS["seguranca_book"], " ".join(bk.get("alertas", [])), "CIENCIA", ref=sha_obj(["seg", bk["sha256"]]))
        pend_dom = [f"{c['codigo']} {c.get('classificacao')} {c.get('descricao')}" for c in plano.values()
                    if c.get("dominio") == "PENDENTE_CONFERENCIA"]
        if pend_dom:
            item("dominio", "Contas criadas no aplicativo sem correspondência confirmada no Domínio",
                 "Não bloqueia a base, mas BLOQUEIA a exportação TXT de lançamentos nessas contas. Crie a conta no Domínio (manualmente) e "
                 "confirme a correspondência aqui.", "CONTA_DOMINIO", bloqueia=False, lista=pend_dom)
        return itens

    def ciencia(self, ident, d):
        comp = competencia(d.get("competencia"))
        base = self.ler(ident, comp)
        if not base:
            raise ValueError("Base inicial não encontrada para a competência.")
        chave_ = d.get("chave")
        alvo = next((x for x in self.definicoes(ident, comp, base) if x["chave"] == chave_ and "referencia" in x), None)
        just = el.limpo(d.get("justificativa"))
        if not alvo:
            raise ValueError("Não há ciência pendente com esta chave.")
        if d.get("confirmado") is not True or not 5 <= len(just) <= 500:
            raise ValueError("Confirme a ciência e informe uma justificativa (5 a 500 caracteres).")
        base.setdefault("ciencias", {})[chave_] = {"referencia": alvo["referencia"], "em": agora(), "justificativa": just,
                                                   "texto": alvo["titulo"], "por": "Supervisor Contábil (tela Empresas)"}
        self.gravar(ident, comp, base, f"ciência registrada: {chave_}")
        return self.situacao(ident, comp)

    def saldo_inicial(self, ident, d):
        """Definição EXPRESSA do saldo inicial de conta ausente do balancete ou criada no aplicativo (inclusive zero explícito)."""
        comp = competencia(d.get("competencia"))
        base = self.ler(ident, comp)
        if not base or not base.get("balancete"):
            raise ValueError("Importe o balancete do mês anterior antes de definir saldos iniciais.")
        e = self.g.obter(ident)
        plano = {c["codigo"]: c for c in e.get("plano", [])}
        codigos = [str(x) for x in (d.get("codigos") or ([d.get("codigo")] if d.get("codigo") else []))]
        if not codigos:
            raise ValueError("Informe a conta.")
        presentes = {c.get("codigo") for c in base["balancete"]["contas"]}
        just = el.limpo(d.get("justificativa"))
        if d.get("confirmado") is not True or not 5 <= len(just) <= 300:
            raise ValueError("Confirme a definição e informe uma justificativa (5 a 300 caracteres).")
        try:
            valor = Decimal(str(d.get("saldo", "")).replace(".", "").replace(",", ".") if "," in str(d.get("saldo", "")) else str(d.get("saldo", "")))
        except Exception:
            raise ValueError("Saldo inválido; informe o valor (zero explícito: 0,00).")
        if valor < 0 or valor != valor.quantize(Decimal("0.01")):
            raise ValueError("Informe o saldo em valor absoluto, com até 2 casas, e a natureza D/C.")
        nat = d.get("natureza")
        if valor == 0:
            nat = None
        elif nat not in ("D", "C"):
            raise ValueError("Saldo diferente de zero exige a natureza D (devedor) ou C (credor).")
        for cod in codigos:
            if cod not in plano:
                raise ValueError(f"Conta {cod} inexistente no plano desta empresa.")
            if cod in presentes:
                raise ValueError(f"Conta {cod} consta no balancete: o saldo do balancete não é substituído por definição manual.")
            if plano[cod].get("tipo") not in ("ANALITICA", "ANALÍTICA"):
                raise ValueError(f"Conta {cod} não é analítica: saldo de conta sintética é a soma das analíticas.")
        for cod in codigos:
            base.setdefault("saldos_definidos", {})[cod] = {"saldo": f"{(valor if nat != 'C' else -valor):.2f}", "natureza": nat,
                                                            "justificativa": just, "em": agora(), "por": "Supervisor Contábil (tela Empresas)",
                                                            "classificacao": plano[cod].get("classificacao"), "tipo": plano[cod].get("tipo")}
        self.gravar(ident, comp, base, f"saldo inicial definido pelo Supervisor para {len(codigos)} conta(s)")
        return self.situacao(ident, comp)

    # ------------------------------------------------------------ etapa 6: confirmação
    def confirmar(self, ident, d):
        comp = competencia(d.get("competencia"))
        base = self.ler(ident, comp)
        if not base:
            raise ValueError("Base inicial não encontrada.")
        frase = FRASE.format(emp=ident, comp=comp)
        faltas = [x["titulo"] for x in self.definicoes(ident, comp, base) if x["bloqueia_confirmacao"] and not x.get("resolvida")]
        if faltas:
            raise ValueError("Base não confirmada; resolva antes: " + "; ".join(faltas) + ".")
        if d.get("frase") != frase:
            raise ValueError(f"Digite exatamente: {frase}")
        e = self.g.obter(ident)
        base["situacao"] = "CONFIRMADA"
        base["confirmacao"] = {"em": agora(), "frase": frase, "versao": base["versao"], "por": "Supervisor Contábil (tela Empresas)",
                               "plano_sha256": sha_obj(e.get("plano", [])), "saldos_sha256": sha_obj(self.saldos(ident, base))}
        base["historico"].append({"versao": base["versao"], "em": agora(), "motivo": "base inicial CONFIRMADA pelo Supervisor"})
        el.gravar(self.pasta(ident, comp) / "base.json", base)
        self._indice(ident)
        return self.situacao(ident, comp)

    def reabrir_por_mudanca(self, ident, motivo):
        """Mudança no plano que afeta saldos (ex.: conta nova): bases CONFIRMADAS voltam a RASCUNHO (nova versão, com o motivo)."""
        if not self.raiz(ident).is_dir():
            return
        for p in sorted(self.raiz(ident).glob("*/base.json")):
            b = el.ler(p)
            if b.get("situacao") == "CONFIRMADA":
                self.gravar(ident, b["competencia"], b, motivo)

    # ------------------------------------------------------------ resumo para a interface
    def situacao(self, ident, comp=None):
        comps = sorted(p.parent.name for p in self.raiz(ident).glob("*/base.json")) if self.raiz(ident).is_dir() else []
        comp = comp or (comps[-1] if comps else None)
        e = self.g.obter(ident)
        if not comp:
            return {"competencias": [], "competencia": None, "etapas": _etapas(e, None, []), "proxima_acao": "Informe a competência dos "
                    "documentos que serão processados e envie o balancete de encerramento do mês anterior.", "fases": _fases(None, []),
                    "pendencias_resumo": {"BLOQUEIO": 0, "ATENCAO": 0, "INFORMATIVO": 0}, "resumo_analise": None}
        competencia(comp)
        base = self.ler(ident, comp)
        defs = self.definicoes(ident, comp, base)
        r = {"competencias": comps, "competencia": comp, "data_base": data_base(comp), "situacao": (base or {}).get("situacao", "NAO_INICIADA"),
             "versao": (base or {}).get("versao"), "definicoes": defs, "etapas": _etapas(e, base, defs),
             "historico": (base or {}).get("historico", [])[-15:]}
        if base:
            bal = base.get("balancete") or {}
            r["balancete"] = {k: bal.get(k) for k in ("arquivo", "sha256", "recebido_em", "formato", "meta", "totais", "duvidas", "limites",
                                                      "conferencia", "aviso", "linhas_ignoradas")} if bal else None
            if bal:
                r["contas_extraidas"] = bal.get("contas")
                r["comparacao_plano"] = {k: len(v) for k, v in self.comparar_contas(ident, base).items()}
                r["ancoras_grupo"] = bal.get("ancoras_grupo")
            bk = base.get("book") or {}
            r["book"] = {"arquivo": bk.get("arquivo"), "sha256": bk.get("sha256"), "recebido_em": bk.get("recebido_em"), "resumo": bk.get("resumo"),
                         "alertas": bk.get("alertas"), "conferencia": bk.get("conferencia"), "confronto": bk.get("confronto"),
                         "abas": bk.get("abas"), "aviso": bk.get("aviso")} if bk else None
            r["saldos"] = self.saldos(ident, base)
            r["contas_aplicadas"] = base.get("contas_aplicadas")
            r["confirmacao"] = base.get("confirmacao")
            r["frase_confirmacao"] = FRASE.format(emp=ident, comp=comp)
        pend = [x for x in defs if x["bloqueia_confirmacao"] and not x.get("resolvida")]
        if not base:
            prox = f"Envie o balancete de encerramento de {data_base(comp)} (fase Balancete anterior)."
        elif base.get("situacao") == "CONFIRMADA":
            prox = "Base confirmada. Abra uma Nova solicitação para processar os documentos do mês."
        elif pend:
            prox = "Resolva: " + (pend[0].get("titulo_simples") or pend[0]["titulo"]).rstrip(".") + "."
        else:
            prox = f"Confirme a base inicial na fase Confirmação digitando {FRASE.format(emp=ident, comp=comp)}."
        r["proxima_acao"] = prox
        if base and base.get("balancete"):
            marca = el.ler(self.pasta(ident, comp) / "analise.json") or {}
            r["analise_plano"] = base["balancete"].get("analise_plano")
            r["reanalise_disponivel"] = int(marca.get("versao_algoritmo") or 0) < plano_hierarquia.VERSAO_ANALISE
            r["ultima_reanalise"] = (base.get("reanalises") or [None])[-1]
        r["fases"] = _fases(base, defs)
        r["pendencias_resumo"] = {n: sum(1 for x in defs if x.get("nivel") == n and not x.get("resolvida")) for n in ("BLOQUEIO", "ATENCAO", "INFORMATIVO")}
        r["resumo_analise"] = _resumo_analise(base, defs)
        r["aviso"] = ("Saldos de abertura e composições não são lançamentos. Diferença zero não significa conciliação concluída. "
                      "Situação, nomes e assinaturas do book são informação da fonte, não aprovações do aplicativo.")
        return r


def _aplicar_derivados(plano, contas_balancete):
    """Preenche no plano, SÓ ONDE ESTÁ VAZIO, o tipo e o grupo derivados da árvore (origem AUTOMÁTICA registrada). Definições do
    Supervisor ou do plano importado nunca são substituídas."""
    bal = {c["codigo"]: c for c in contas_balancete if c.get("codigo")}
    n = {"tipos": 0, "grupos": 0}
    for p in plano:
        b = bal.get(p["codigo"])
        if not b:
            continue
        if not p.get("tipo") and b.get("tipo"):
            p["tipo"], p["tipo_origem"] = b["tipo"], "AUTOMATICO: hierarquia da classificação"
            n["tipos"] += 1
        if not p.get("grupo") and b.get("grupo_sugerido"):
            p["grupo"], p["grupo_origem"] = b["grupo_sugerido"], b.get("grupo_origem") or "AUTOMATICO"
            n["grupos"] += 1
        if b.get("grupo_contabil") and not p.get("grupo_contabil"):
            p["grupo_contabil"] = b["grupo_contabil"]
    return n


def _saldos_nao_conferem(contas):
    """Contas em que saldo anterior + débitos − créditos ≠ saldo informado, com os valores para a explicação na tela."""
    saida = []
    for c in contas:
        try:
            ant, deb, cre, atu = (Decimal(c[x]) for x in ("saldo_anterior", "debitos", "creditos", "saldo_atual"))
        except (TypeError, ValueError, ArithmeticError, KeyError):
            if c.get("problemas"):
                saida.append({"codigo": c.get("codigo"), "classificacao": c["classificacao"], "descricao": c.get("descricao"),
                              "problemas": c["problemas"], "calculavel": False})
            continue
        if ant + deb - cre != atu:
            saida.append({"codigo": c.get("codigo"), "classificacao": c["classificacao"], "descricao": c.get("descricao"),
                          "saldo_anterior": f"{ant:.2f}", "debitos": f"{deb:.2f}", "creditos": f"{cre:.2f}",
                          "saldo_esperado": f"{ant + deb - cre:.2f}", "saldo_informado": f"{atu:.2f}",
                          "diferenca": f"{atu - (ant + deb - cre):.2f}", "calculavel": True})
    return saida[:300]


def _fases(base, defs):
    """As 4 fases mostradas na tela (o backend mantém as etapas detalhadas): Balancete anterior, Book / composições, Conferência,
    Confirmação. Situação: CONCLUIDA, ATUAL ou PENDENTE (só uma ATUAL: a primeira não concluída)."""
    bal = (base or {}).get("balancete")
    aplicadas = ((base or {}).get("contas_aplicadas") or {}).get("balancete_sha256") == (bal or {}).get("sha256") and bool(bal)
    book_ok = bool((base or {}).get("book")) or any(x["chave"] == "sem_book" and x.get("resolvida") for x in defs)
    pend = [x for x in defs if x["bloqueia_confirmacao"] and not x.get("resolvida") and x["chave"] not in ("balancete", "contas", "sem_book")]
    feitas = [bool(bal) and aplicadas, book_ok, bool(bal) and aplicadas and book_ok and not pend,
              (base or {}).get("situacao") == "CONFIRMADA"]
    nomes = [("balancete", "Balancete anterior"), ("book", "Book / composições"), ("conferencia", "Conferência"), ("confirmacao", "Confirmação")]
    atual = next((i for i, f in enumerate(feitas) if not f), None)
    return [{"fase": k, "titulo": t, "situacao": "CONCLUIDA" if feitas[i] else ("ATUAL" if i == atual else "PENDENTE")}
            for i, (k, t) in enumerate(nomes)]


def _resumo_analise(base, defs):
    """Contas analisadas e quantas têm apontamentos (bloqueio/atenção), pelo código das contas citadas nas pendências abertas."""
    contas = ((base or {}).get("balancete") or {}).get("contas") or []
    if not contas:
        return None
    def codigos(x):
        return {str(i).split(" ")[0] for i in x.get("itens") or [] if str(i).split(" ")[0].isdigit()}
    bloq, aten = set(), set()
    do_balancete = {c.get("codigo") for c in contas}
    comps = (((base or {}).get("book") or {}).get("confronto") or {}).get("composicoes") or []
    for x in defs:
        if x.get("resolvida"):
            continue
        if x["chave"] == "problemas_balancete":
            alvo = {c.get("codigo") for c in contas if c.get("problemas")}
        elif x["chave"] == "divergencias_book":
            alvo = {(c.get("conta") or {}).get("codigo") for c in comps if c.get("conferencia_numerica") in ("DIVERGENTE", "SINAL_A_CONFIRMAR")}
        elif x["chave"] in ("tipos", "grupos", "saldos", "conflitos_contas", "dominio", "sem_composicao"):
            alvo = codigos(x)            # listas "código classificação descrição" (estabelecimentos e abas nunca contam como contas)
        else:
            continue
        alvo &= do_balancete
        (bloq if x.get("nivel") == "BLOQUEIO" else aten if x.get("nivel") == "ATENCAO" else set()).update(c for c in alvo if c)
    aten -= bloq
    total = len(contas)
    return {"contas_analisadas": total, "sem_apontamentos": total - len(bloq) - len(aten), "precisam_atencao": len(aten),
            "bloqueiam": len(bloq), "pendencias_abertas": sum(1 for x in defs if not x.get("resolvida") and x.get("nivel") != "INFORMATIVO")}


def _etapas(e, base, defs):
    pend = [x for x in defs if x["bloqueia_confirmacao"] and not x.get("resolvida")]
    bal = (base or {}).get("balancete")
    aplicadas = (base or {}).get("contas_aplicadas") or {}
    contas_ok = bool(bal) and aplicadas.get("balancete_sha256") == bal.get("sha256")
    def_contas = [x for x in pend if x["chave"] in ("tipos", "grupos", "saldos", "conflitos_contas")]
    book_ok = bool((base or {}).get("book")) or any(x["chave"] == "sem_book" and x.get("resolvida") for x in defs)
    return [
        {"etapa": 1, "titulo": "Identificação", "feito": bool(e.get("cnpj")), "falta": [] if e.get("cnpj") else ["CNPJ e razão social"]},
        {"etapa": 2, "titulo": "Importação e conferência do balancete anterior", "feito": bool(bal),
         "falta": [] if bal else ["balancete de encerramento do mês anterior"]},
        {"etapa": 3, "titulo": "Conferência das contas e saldos", "feito": contas_ok and not def_contas,
         "falta": ([] if contas_ok else ["aplicar as contas extraídas ao plano"]) + [x["titulo"].rstrip(".") for x in def_contas]},
        {"etapa": 4, "titulo": "Importação e conferência do book", "feito": book_ok,
         "falta": [] if book_ok else ["book do mesmo período (ou ciência sem book)"]},
        {"etapa": 5, "titulo": "Resolução das definições pendentes", "feito": bool(base) and not pend, "falta": [x["titulo"].rstrip(".") for x in pend]},
        {"etapa": 6, "titulo": "Confirmação da base inicial", "feito": (base or {}).get("situacao") == "CONFIRMADA",
         "falta": [] if (base or {}).get("situacao") == "CONFIRMADA" else ["confirmação com a frase exata"]},
    ]


def _diferencas_balancete(antigas, novas):
    a = {c["classificacao"]: c for c in antigas}
    n = {c["classificacao"]: c for c in novas}
    alteradas = []
    for k in sorted(set(a) & set(n)):
        mud = {f: [a[k].get(f), n[k].get(f)] for f in ("codigo", "descricao", "saldo_anterior", "debitos", "creditos", "saldo_atual",
                                                         "natureza_atual") if a[k].get(f) != n[k].get(f)}
        if mud:
            alteradas.append({"classificacao": k, "mudancas": mud})
    return {"novas": sorted(set(n) - set(a)), "ausentes_no_novo": sorted(set(a) - set(n)), "alteradas": alteradas,
            "aviso": "Reimportação: contas ausentes no novo arquivo NÃO são excluídas do plano; códigos, saldos e classificações só mudam "
                     "na base com a sua confirmação, e a confirmação anterior da base deixa de valer."}


def _resumo_dif(d):
    return f"{len(d['novas'])} nova(s), {len(d['alteradas'])} alterada(s), {len(d['ausentes_no_novo'])} ausente(s)"


def _ler_tabular(d):
    """Reaproveita a leitura tabular do cadastro (CSV/XLS/XLSX) sem gravar prévia de plano."""
    import csv
    import io
    nome = d["nome"]
    dados = base64.b64decode(d["conteudo"])
    ext = Path(nome).suffix.lower()
    if ext in (".csv", ".txt"):
        try:
            t = dados.decode("utf-8-sig")
        except UnicodeDecodeError:
            t = dados.decode("cp1252")
        try:
            dialect = csv.Sniffer().sniff(t[:8000], delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
        return list(csv.reader(io.StringIO(t), dialect))
    if ext == ".xls":
        from python_calamine import CalamineWorkbook
        with CalamineWorkbook.from_filelike(io.BytesIO(dados)) as wb:
            return [list(r) for r in wb.get_sheet_by_index(0).to_python()[:20000]]
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
    try:
        return [list(r) for r in wb.worksheets[0].iter_rows(max_row=20000, max_col=60, values_only=True)]
    finally:
        wb.close()
