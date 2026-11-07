"""Rodada de SIMPLIFICAÇÃO de Empresas / Base inicial / experiência operacional — Chrome sem janela contra a API REAL, ambiente
ISOLADO (cadastros, registro, runtime, ordem ativa e LIBERADOS temporários) e dados 100% fictícios (amostra A e B).

Casos: UI-01…UI-12 (interface), EMP-DEL-01…EMP-DEL-12 (excluir cadastro = exclusão LÓGICA) e UX-01…UX-10 (uso por um funcionário
novo). A tela é verificada pelo que o usuário VÊ (innerText); detalhes técnicos só existem sob "Ver detalhes técnicos".

Uso: .venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_simplificacao_empresas.py [pasta para capturas]
"""
import base64
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
TMP = Path(tempfile.mkdtemp(prefix="prime-simplificacao-"))
for k, v in {"AGENTES_PRIME_RUNTIME": TMP / "runtime", "AGENTES_PRIME_REGISTRO_SOL": TMP / "controle" / "solicitacoes.json",
             "AGENTES_PRIME_ORDEM_ATIVA": TMP / "ordem-ativa.json", "AGENTES_PRIME_CLAUDE": TMP / "claude-inexistente.exe",
             "LOCALAPPDATA": TMP / "localappdata", "AGENTES_PRIME_LIBERADOS": TMP / "LIBERADOS", "AGENTES_PRIME_CLIENTES": TMP / "CLIENTES"}.items():
    os.environ[k] = str(v)
(TMP / "CLIENTES").mkdir()
(TMP / "controle").mkdir()
for p in ("API-LOCAL", "TESTES/API", "TESTES/BASE-INICIAL"):
    sys.path.insert(0, str(RAIZ / p))
import amostra_ficticia as am  # noqa: E402
import ficticios as f  # noqa: E402
import servidor  # noqa: E402
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado as _ai  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402

FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-simplificacao-"))
FOTOS.mkdir(parents=True, exist_ok=True)
D = Decimal
A, B = am.EMPRESAS["A"], am.EMPRESAS["B"]
resultados, srv = [], None
CODIGOS_TECNICOS = re.compile(r"\b(SEM_CONTA_CORRESPONDENTE|IGUAL_AO_BALANCETE|SINAL_A_CONFIRMAR|FORMULA_\w+|ITENS_EM_ABERTO|HISTORICO_ACUMULADO|"
                              r"POSICAO_DE_RELATORIO|CONC-[A-Z]-\w+|SALDO_INICIAL|CONTA_DOMINIO|CIENCIA|ETAPA_\d|PENDENTE_CONFERENCIA|"
                              r"CRIADA_NO_APLICATIVO|empresa-local\.json|\.json\b|runtime|agent_type)\b")


def porta_livre():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORTA_CDP = porta_livre()


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:400]))


def req(metodo, rota, dados=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=300)
    h = {"X-Prime-Sessao": srv.token, "Content-Type": "application/json"}
    h.update(cab or {})
    c.request(metodo, "/api" + rota, dados if isinstance(dados, bytes) else json.dumps(dados).encode() if dados is not None else None, h)
    r = c.getresponse()
    bruto = r.read()
    c.close()
    try:
        return r.status, json.loads(bruto)
    except ValueError:
        return r.status, bruto


def registro():
    return _ai.registro_isolado()["solicitacoes"]


def ocioso(limite=600):
    fim = time.time() + limite
    while time.time() < fim:
        if not servidor.EM_EXECUCAO["sol"] and not servidor.EM_FINANCEIRO["sol"] and not any(
                str(s.get("estado", "")).endswith("_EM_ANDAMENTO") for s in registro().values()):
            return True
        time.sleep(0.3)
    return False


def hashes(pasta: Path, ignorar=("empresa-local.json", "CADASTRO.md")):
    return {str(p.relative_to(pasta)): hashlib.sha256(p.read_bytes()).hexdigest() for p in pasta.rglob("*")
            if p.is_file() and p.name not in ignorar and "VERSOES" not in p.parts}


class Tela:
    def __init__(self, cdp):
        self.cdp, self.n = cdp, 0

    def js(self, e):
        return self.cdp.js(e)

    def esperar(self, cond, s=30):
        fim = time.time() + s
        while time.time() < fim:
            try:
                if self.js("!!(" + cond + ")"):
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        return False

    def alvo(self, expr, s=30):
        self.n += 1
        marca = f"t{self.n}"
        if not self.esperar(f"(()=>{{const e=({expr});if(e){{e.dataset.alvoTeste='{marca}';return true}}return false}})()", s):
            self.cdp.foto(FOTOS / f"falha-{marca}.png")
            raise AssertionError(f"elemento não encontrado: {expr}")
        return f"[data-alvo-teste='{marca}']"

    def clicar(self, expr, s=30):
        for _ in range(6):
            sel = self.alvo(expr, s)
            self.esperar(f"document.querySelector(\"{sel}\") && !document.querySelector(\"{sel}\").disabled", 15)
            xy = self.js(f"(()=>{{const e=document.querySelector(\"{sel}\");if(!e)return null;e.scrollIntoView({{block:'center'}});"
                         "const r=e.getBoundingClientRect();return r.width&&r.height?{x:r.x+r.width/2,y:r.y+r.height/2}:null})()")
            if xy:
                for tipo in ("mousePressed", "mouseReleased"):
                    self.cdp.chamar("Input.dispatchMouseEvent", type=tipo, button="left", clickCount=1, **xy)
                time.sleep(0.15)
                return
            time.sleep(0.5)
        self.cdp.foto(FOTOS / f"falha-clique-{self.n}.png")
        raise AssertionError(f"elemento não clicável: {expr}")

    def digitar(self, expr, texto):
        sel = self.alvo(expr)
        self.js(f"(()=>{{const e=document.querySelector(\"{sel}\");e.scrollIntoView({{block:'center'}});e.focus();e.select&&e.select()}})()")
        self.cdp.chamar("Input.insertText", text=texto)
        time.sleep(0.1)

    def texto(self, expr):
        return self.js(f"(()=>{{const e=({expr});return e?e.innerText:''}})()") or ""

    def estavel(self, s=30):
        fim, anterior = time.time() + s, None
        while time.time() < fim:
            atual = self.js("(document.querySelector('.op-painel:not([hidden])')||document.querySelector('.gestao:not([hidden])')||document.body).innerHTML.length")
            if atual == anterior:
                return True
            anterior = atual
            time.sleep(0.8)
        return False

    def arquivos(self, seletor, caminhos):
        raiz = self.cdp.chamar("DOM.getDocument")["root"]["nodeId"]
        no = self.cdp.chamar("DOM.querySelector", nodeId=raiz, selector=seletor)["nodeId"]
        self.cdp.chamar("DOM.setFileInputFiles", nodeId=no, files=[str(c) for c in caminhos])


def q(sel):
    return f"document.querySelector({json.dumps(sel)})"


def por_texto(seletor, trecho, dentro="document"):
    return f"Array.from(({dentro}).querySelectorAll({json.dumps(seletor)})).find(e=>e.textContent.includes({json.dumps(trecho)}))"


VISIVEL = ("(()=>{const c=document.querySelector('.gestao-conteudo').cloneNode(true);c.querySelectorAll('.gestao-tecnico,[hidden]').forEach(x=>x.remove());"
           "return document.querySelector('.gestao-conteudo').innerText})()")
VISIVEL_SEM_TECNICO = ("(()=>{const o=document.querySelector('.gestao-conteudo');const tec=Array.from(o.querySelectorAll('.gestao-tecnico')).map(x=>x.innerText).join(' ');"
                       "let t=o.innerText;tec.split(/\\n/).filter(Boolean).forEach(s=>{t=t.split(s).join('')});return t})()")
PRIMARIOS_VISIVEIS = "Array.from(document.querySelectorAll('.gestao .gestao-primario')).filter(b=>b.checkVisibility({contentVisibilityAuto:true,visibilityProperty:true})).length"


def balancete_amostra(inicio, fim):
    """Balancete FICTÍCIO coerente com a amostra A (analíticas do plano + sintéticas 9xxx)."""
    analiticas = {k: (cod, desc) for cod, k, desc, _ in am.PLANO}
    saldo = {k: (D(am.ABERTURA[cod][0]) * (1 if am.ABERTURA[cod][1] == "D" else -1) if cod in am.ABERTURA else D("0")) for k, (cod, _) in analiticas.items()}
    nomes = {"1": "ATIVO", "1.1": "ATIVO CIRCULANTE", "1.1.1": "DISPONIBILIDADES", "1.1.2": "CREDITOS", "2": "PASSIVO", "2.1": "PASSIVO CIRCULANTE",
             "2.1.1": "FORNECEDORES", "2.1.2": "OBRIGACOES TRABALHISTAS", "2.1.3": "PROVISOES", "2.1.4": "OBRIGACOES TRIBUTARIAS", "3": "RECEITAS",
             "3.1": "RECEITA BRUTA", "3.1.1": "SERVICOS", "3.1.9": "DEDUCOES", "4": "DESPESAS", "4.1": "DESPESAS OPERACIONAIS", "4.1.1": "PESSOAL",
             "4.2": "OUTRAS DESPESAS", "4.2.1": "GERAIS"}
    cods = {k: str(9000 + i) for i, k in enumerate(sorted(nomes, key=lambda k: [int(x) for x in k.split(".")]), 1)}
    linhas = []
    for k in sorted(list(nomes) + list(analiticas), key=lambda k: [int(x) for x in k.split(".")]):
        if k in nomes:
            s = sum((v for a, v in saldo.items() if a.startswith(k + ".")), D("0"))
            linhas.append((cods[k], k, nomes[k], s, D("0"), D("0"), s))
        else:
            linhas.append((analiticas[k][0], k, analiticas[k][1], saldo[k], D("0"), D("0"), saldo[k]))
    return f.pdf_balancete(A["nome"], A["cnpj"], inicio, fim, linhas, consolidado=["1", "2"], por_pagina=18), linhas


def preparar_base_com_pendencias():
    """Base de 2026-11 (balancete de 31/10) da empresa A, EM PREPARAÇÃO e com pendências de todos os níveis."""
    emp = A["id"]
    pdf, linhas = balancete_amostra("01/10/2026", "31/10/2026")
    c, prev = req("POST", f"/empresas/{emp}/base-balancete", {"competencia": "2026-11", "nome": "balancete-outubro.pdf", "conteudo": base64.b64encode(pdf).decode()})
    assert c == 200, prev
    req("POST", f"/empresas/{emp}/base-balancete", {"competencia": "2026-11", "token": prev["token"], "salvar": True, "confirmado": True})
    c, cmp_ = req("POST", f"/empresas/{emp}/base-contas", {"competencia": "2026-11"})
    req("POST", f"/empresas/{emp}/base-contas", {"competencia": "2026-11", "salvar": True, "confirmado": True,
                                                 "grupos": {a["classificacao"]: a["grupo_sugerido"] for a in cmp_["ancoras_grupo"]}})
    comp = [("1121-CLIENTES", "1.1.2.01", "CLIENTES", "Itens em aberto", [("2026-10-20", "NF 90", "Cliente Ficticio", 9000.0, 0, "")])]   # diverge
    book = f.book_padrao(A["nome"], A["cnpj"], "10/2026", "2026-10-31", linhas, comp)
    c, pb = req("POST", f"/empresas/{emp}/base-book", {"competencia": "2026-11", "nome": "book-outubro.xlsx", "conteudo": base64.b64encode(book).decode()})
    req("POST", f"/empresas/{emp}/base-book", {"competencia": "2026-11", "token": pb["token"], "salvar": True, "confirmado": True})
    c, r = req("POST", f"/empresas/{emp}/criar-conta", {"codigo": "1199", "classificacao": "1.1.2.99", "descricao": "OUTROS CREDITOS FICTICIOS",
                                                       "superior": "1.1.2", "tipo": "ANALITICA", "grupo": "ATIVO", "confirmado": True})
    assert c == 200, r
    req("POST", f"/empresas/{emp}/piloto", {"frase": f"CONFIRMO PILOTO {emp}"})


def bateria(t):
    emp = A["id"]
    t.esperar("window.EV && EV.app && document.querySelector('.gestao-nav')", 30)
    t.js("window.confirm=()=>true")
    # ---------------- lista de empresas
    t.clicar(q('[data-pagina="empresas"]'))
    t.esperar("document.querySelectorAll('[data-empresa]').length>=2")
    t.estavel()
    t.cdp.foto(FOTOS / "01-empresas.png")
    visivel = t.js(VISIVEL)
    cartao = q(f"[data-empresa='{emp}']")
    menu_fechado = t.js(f"{cartao}.querySelector('.gestao-menu-lista').hidden")
    t.clicar(f"{cartao}.querySelector('.gestao-menu-botao')")
    itens_menu = t.js(f"Array.from({cartao}.querySelectorAll('.gestao-menu-lista button')).map(b=>b.textContent)")
    t.js("document.body.click()")
    registrar("UI-11 lista de empresas: cada cartão mostra nome, status, modo e competência atual; ações em [Abrir] + menu '⋯' "
              "(Configurações, Editar cadastro, Histórico, Excluir cadastro) fechado por padrão",
              menu_fechado and itens_menu == ["Configurações", "Editar cadastro", "Histórico de solicitações", "Excluir cadastro"]
              and all(x in t.texto(cartao) for x in ("Modo: Simulação", "Competência atual")), (itens_menu, t.texto(cartao)[:200]))
    registrar("UI-12 tela principal sem excesso de texto: só cartões, 'Como funciona' recolhido e Administração recolhida",
              len(visivel) < 900 and not t.js("document.querySelector('[data-como-funciona]').open") and not t.js("document.querySelector('[data-mais-opcoes]').open"),
              f"{len(visivel)} caracteres visíveis")
    registrar("UX-01 primeira ação identificável: 'Como funciona' com os 6 passos (escolher empresa → abrir competência → base → enviar "
              "documentos → Coordenador → conferir) e [Abrir] em cada empresa",
              "Prepare a base inicial." in t.js("document.querySelector('[data-como-funciona]').textContent")
              and t.js("document.querySelectorAll('[data-acao=abrir-empresa]').length") >= 2)
    registrar("UX-08 ações administrativas separadas da operação: cadastro, cadastros excluídos e amostra ficam em 'Administração · Mais "
              "opções'; excluir só dentro de menus",
              t.js("!!document.querySelector('[data-mais-opcoes].gestao-admin [data-cadastrar-empresa]') && !!document.querySelector('[data-mais-opcoes] [data-amostra]')")
              and not t.js("Array.from(document.querySelectorAll('.gestao button')).some(b=>b.offsetParent!==null&&b.textContent.includes('Excluir cadastro'))"))
    registrar("UI-09 lista de empresas: no máximo uma ação principal visível", t.js(PRIMARIOS_VISIVEIS) <= 1, t.js(PRIMARIOS_VISIVEIS))
    # ---------------- empresa: resumo executivo
    t.clicar(f"{cartao}.querySelector('[data-acao=abrir-empresa]')")
    t.esperar("document.querySelector('[data-base-resumo]')")
    t.estavel()
    t.cdp.foto(FOTOS / "02-empresa-resumo.png")
    resumo = t.texto(q("[data-base-resumo]"))
    abas = t.js("Array.from(document.querySelectorAll('[data-config-empresa] [data-config]')).map(b=>b.textContent)")
    registrar("UI-04 base inicial em resumo compacto (status, balancete, book, pendências); o fluxo detalhado fica fechado",
              all(x in resumo for x in ("Base inicial — Novembro/2026", "Status: Em preparação", "Balancete anterior: concluído", "Book anterior: concluído", "Pendências:"))
              and t.js("document.querySelector('[data-fluxo-base]').hidden") and len(resumo) < 450, resumo)
    registrar("UX-02 situação da base compreensível: 'Status: Em preparação' e o que está concluído/pendente", "Em preparação" in resumo)
    n_comp = t.js("(document.querySelector('[data-base-resumo] [data-contas-conferencia]')||{dataset:{}}).dataset.contasConferencia||''")
    registrar("BOOK-SEV-02 (tela) resumo da base conta as contas sem composição no Book: '⚠ N contas precisam de conferência', explicação "
              "e [Revisar N contas]; nunca 'Pendências: nenhuma' enquanto houver contas a conferir",
              n_comp.isdigit() and int(n_comp) > 0 and f"{n_comp} conta" in resumo and "precisa" in resumo and "de conferência" in resumo
              and "São contas patrimoniais analíticas com saldo, mas sem composição identificada no Book." in resumo
              and f"Revisar {n_comp} conta" in t.texto(q("[data-base-resumo] [data-acao=revisar-contas-book]"))
              and "Pendências: nenhuma" not in resumo, resumo)
    registrar("UI-06 pendências resumidas: 'N pendências precisam da sua atenção' + [Revisar pendências], sem blocos de texto",
              re.search(r"\d+ pendências precisam da sua atenção", resumo) and t.js("!!document.querySelector('[data-base-resumo] [data-acao=revisar-pendencias]')"), resumo)
    registrar("UI-03 configuração da empresa só com Contas bancárias, Cadastro e piloto, Plano contábil atual (+ menu Mais opções)",
              abas == ["Contas bancárias", "Cadastro e piloto", "Plano contábil atual"] and t.js("!!document.querySelector('[data-config-empresa] .gestao-menu-botao')"), abas)
    registrar("UI-09 empresa: UMA ação principal visível ('Continuar preparação')", t.js(PRIMARIOS_VISIVEIS) == 1
              and t.texto(q("[data-acao=continuar-base]")) == "Continuar preparação", t.js(PRIMARIOS_VISIVEIS))
    # UI-01/UI-02: percorre todas as áreas de configuração e procura os itens removidos
    textos = [t.js("document.querySelector('.gestao-conteudo').textContent")]
    for k in ("bancos", "cadastro", "plano"):
        t.clicar(q(f"[data-config={k}]"))
        t.esperar(f"document.querySelector('.gestao-config-painel h3')")
        textos.append(t.js("document.querySelector('.gestao-conteudo').textContent"))
        if k == "bancos":
            t.cdp.foto(FOTOS / "03-contas-bancarias.png")
            banco = t.texto(q("[data-banco]"))
    t.clicar(q("[data-config-empresa] .gestao-menu-botao"))
    textos.append(t.js("document.querySelector('.gestao-conteudo').textContent"))
    t.js("document.body.click()")
    tudo = " ".join(textos)
    registrar("UI-01 'Importar plano de contas do Domínio' não aparece em nenhuma área", "Importar plano" not in tudo and "plano de contas do Domínio" not in tudo
              and not t.js("!!document.querySelector('[data-importador]')"))
    registrar("UI-02 'Contas de adiantamento' não aparece (nem formulário de adiantamento automático)", "adiantamento" not in tudo.lower().replace("adiantamento de viagem", "")
              and not t.js("!!document.querySelector('[data-contas-adiantamento]')"))
    registrar("Contas bancárias em visão simples: banco, agência/conta mascaradas, conta contábil e status 'Vinculada' (edição sob [Editar])",
              "Vinculada" in banco and "•••" in banco and "1101" in banco and not t.js("document.querySelector('[data-editar-bancos]').open"), banco)
    # ---------------- pendências (fase Conferência)
    t.clicar(q("[data-base-resumo] [data-acao=revisar-pendencias]"))
    t.esperar("document.querySelector('[data-fase-ativa=conferencia] [data-definicao-base]')")
    t.estavel()
    t.cdp.foto(FOTOS / "04-pendencias.png")
    cards = t.js("Array.from(document.querySelectorAll('[data-fase-ativa=conferencia] .gestao-pendencia[data-resolvida=nao]')).map(c=>({chave:c.dataset.definicaoBase,nivel:c.dataset.nivel,"
                 "texto:c.innerText,borda:getComputedStyle(c).borderLeftColor}))")
    niveis = {c["nivel"] for c in cards}
    bordas = {c["nivel"]: c["borda"] for c in cards}
    guiados = [c for c in cards if c["nivel"] != "INFORMATIVO"]
    registrar("UI-07 / UX-03 / UX-04 cada pendência explica Problema, Impacto e O que fazer (sem abrir detalhes técnicos)",
              guiados and all(all(x in c["texto"] for x in ("Problema", "Impacto", "O que fazer")) for c in guiados), [c["chave"] for c in cards])
    # Informativo continua existindo como nível visual, mas nenhuma pendência desta amostra é informativa (composição ausente no Book
    # passou a Atenção): a cor do nível é conferida num cartão-sonda, criado e removido no mesmo container.
    bordas["INFORMATIVO"] = t.js("(()=>{const c=document.querySelector('[data-fase-ativa=conferencia]');const a=document.createElement('article');"
                                 "a.className='gestao-pendencia informativo';c.append(a);const b=getComputedStyle(a).borderLeftColor;a.remove();return b})()")
    registrar("BOOK-SEV-01 (tela) contas com saldo sem composição no Book aparecem como Atenção (não Informativo, não Bloqueio)",
              any(c["chave"] == "sem_composicao" and c["nivel"] == "ATENCAO" and "⚠ Atenção" in c["texto"] for c in cards),
              [(c["chave"], c["nivel"]) for c in cards])
    registrar("UI-08 / UX-05 Bloqueio, Atenção e Informativo visualmente distintos (selo e cor diferentes) e legenda explicando se impede seguir",
              {"BLOQUEIO", "ATENCAO"} <= niveis and len(set(bordas.values())) == 3
              and all(x in t.texto(q(".gestao-legenda")) for x in ("Bloqueio: Precisa ser resolvido", "Atenção: Recomenda revisão", "Informativo: Não impede")),
              bordas)
    sem_tecnico = t.js(VISIVEL_SEM_TECNICO)
    achados = sorted(set(CODIGOS_TECNICOS.findall(sem_tecnico)))
    tem_tecnico = t.js("document.querySelectorAll('.gestao-tecnico').length")
    registrar("UI-10 / UX-06 termos técnicos só em 'Ver detalhes técnicos' (nenhum código interno visível no texto da tela)",
              not achados and tem_tecnico > 0, achados)
    analise = t.texto(q("[data-analise-base]"))
    registrar("Resumo executivo da análise: contas analisadas, sem apontamentos, precisam de atenção, bloqueiam a confirmação",
              all(x in analise for x in ("contas analisadas", "sem apontamentos", "precisam de atenção", "bloqueiam a confirmação")), analise.replace("\n", " "))
    registrar("UI-09 fase Conferência: no máximo uma ação principal visível", t.js(PRIMARIOS_VISIVEIS) <= 1, t.js(PRIMARIOS_VISIVEIS))
    # UI-05: detalhes continuam acessíveis (composições com filtros)
    t.clicar(f"{q('[data-fase=book]')}.querySelector('button')")
    t.esperar("document.querySelector('[data-fase-ativa=book] details.gestao-sob-demanda')")
    t.clicar(f"{por_texto('[data-fase-ativa=book] summary', 'Ver todas as composições')}")
    t.esperar("document.querySelector('[data-fase-ativa=book] .gestao-tabela tr td')")
    filtros = t.js("Array.from(document.querySelectorAll('[data-fase-ativa=book] .gestao-filtro-botao')).map(b=>b.textContent)")
    registrar("UI-05 informações detalhadas acessíveis sob demanda (tabela de composições com filtros Todas/Pendentes/Divergentes/Conferidas)",
              [x.split(" (")[0] for x in filtros] == ["Todas", "Pendentes", "Divergentes", "Conferidas"], filtros)
    # UX-07: a tela da empresa não exige entender SOL/arquivos internos
    registrar("UX-07 tela da empresa sem jargão de SOL, pastas ou arquivos internos", not re.search(r"SOL-\d|CLIENTES/|\\\\|\.py\b", t.js(VISIVEL_SEM_TECNICO)))
    # ---------------- Nova solicitação: resumo antes de iniciar e acompanhamento (empresa A, competência 10/2026)
    pasta = TMP / "docs-A"
    pasta.mkdir()
    for nome, conteudo in am.documentos("A").items():
        (pasta / nome).write_bytes(conteudo)
    docs = sorted(pasta.iterdir())
    t.clicar(q(".op-botao"))
    t.esperar("!document.querySelector('.op-painel').hidden")
    t.alvo(f"Array.from(document.querySelectorAll('.op-form select')[0].options).find(o=>o.value==='{emp}')")
    t.js(f"(()=>{{const s=document.querySelectorAll('.op-form select')[0];s.value='{emp}';s.dispatchEvent(new Event('change'))}})()")
    t.js("(()=>{const i=document.querySelector('.op-form input[type=month]');i.value='2026-10';i.dispatchEvent(new Event('input'));i.dispatchEvent(new Event('change'))})()")
    t.arquivos(".op-form input[type=file]", docs)
    t.esperar(f"document.querySelectorAll('.op-arquivos li').length==={len(docs)}")
    res_envio = t.texto(q("[data-resumo-envio]"))
    t.cdp.foto(FOTOS / "05-nova-solicitacao.png")
    registrar("UX-09 antes de iniciar: 'Você está iniciando' com empresa, competência e quantidade de documentos; botão 'Iniciar processamento'",
              all(x in res_envio for x in (A["nome"], "Outubro/2026", str(len(docs)))) and t.texto(q(".op-iniciar")) == "Iniciar processamento",
              res_envio.replace("\n", " "))
    t.digitar(q(".op-form textarea"), "Documentos fictícios de outubro/2026 para processar (SIMULAÇÃO).")
    if not t.js("document.querySelector('.op-form .op-confirma input').checked"):
        t.clicar("document.querySelector('.op-form .op-confirma input')")
    antes = set(registro())
    t.clicar(q(".op-iniciar"))
    fim = time.time() + 120
    while time.time() < fim and not (set(registro()) - antes):
        time.sleep(0.2)
    sol = sorted(set(registro()) - antes)[0]
    c, imp = req("GET", f"/empresas/{emp}/exclusao")
    c2, tentativa = req("POST", f"/empresas/{emp}/excluir", {"frase": f"EXCLUIR {emp}", "confirmado": True})
    em_processo = servidor.EM_EXECUCAO["sol"] or any(str(s.get("estado", "")).endswith("_EM_ANDAMENTO") for s in registro().values())
    t.esperar("document.querySelector('.op-sol') && !document.querySelector('.op-sol').hidden && document.querySelector('.op-sol').innerText.length>40", 30)
    acomp = t.texto(q(".op-sol"))
    t.cdp.foto(FOTOS / "06-acompanhamento.png")
    registrar("EMP-DEL-03 empresa com SOL em processamento não pode ser excluída (mensagem clara; processamento não é interrompido)",
              (not em_processo) or (c2 == 409 and "operação em andamento" in str(tentativa.get("erro")) and imp["bloqueio"]), (c2, tentativa))
    registrar("UX-10 acompanhamento mostra etapas em andamento sem inventar porcentagem",
              any(x in acomp for x in ("Documentos", "Coordenador", "Financeiro", "Conciliação")) and "%" not in acomp, acomp[:200].replace("\n", " "))
    ocioso()
    c, r = req("POST", f"/solicitacoes/{sol}/aprovacao", {"acao": "aprovar", "frase": f"APROVO FECHAMENTO {sol}", "justificativa": "Teste fictício.", "confirmado": True})
    liberados_antes = hashes(TMP / "LIBERADOS") if (TMP / "LIBERADOS").is_dir() else {}
    docs_antes = hashes(TMP / "CLIENTES" / emp)
    outra_antes = hashlib.sha256((TMP / "CLIENTES" / B["id"] / "empresa-local.json").read_bytes()).hexdigest()
    # ---------------- excluir cadastro
    Path(os.environ["AGENTES_PRIME_ORDEM_ATIVA"]).write_text(json.dumps({"sol": "SOL-2026-999999", "empresa": B["id"]}), encoding="utf-8")
    c, r2 = req("POST", f"/empresas/{emp}/excluir", {"frase": f"EXCLUIR {emp}", "confirmado": True})
    Path(os.environ["AGENTES_PRIME_ORDEM_ATIVA"]).unlink()
    registrar("EMP-DEL-02 ordem ativa impede a exclusão: 'Não é possível excluir o cadastro enquanto existe uma operação em andamento.'",
              c == 409 and "Não é possível excluir o cadastro enquanto existe uma operação em andamento." in r2.get("erro", ""), r2)
    c, r3 = req("POST", f"/empresas/{emp}/excluir", {"frase": f"EXCLUIR {emp} ", "confirmado": True})
    c4, r4 = req("POST", f"/empresas/{emp}/excluir", {"frase": "EXCLUIR OUTRA", "confirmado": True})
    t.clicar(q('[data-pagina="empresas"]'))
    t.esperar("document.querySelectorAll('[data-empresa]').length>=2")
    t.estavel()
    cartao = q(f"[data-empresa='{emp}']")
    t.clicar(f"{cartao}.querySelector('.gestao-menu-botao')")
    t.clicar(f"{cartao}.querySelector('[data-acao=menu-excluir]')")
    t.esperar("document.querySelector('[data-exclusao-empresa] [data-campo=frase-exclusao]')")
    caixa = t.texto(q("[data-exclusao-empresa]"))
    t.digitar(q("[data-campo=frase-exclusao]"), "EXCLUIR ERRADO")
    desabilitado = t.js("document.querySelector('[data-acao=confirmar-exclusao-empresa]').disabled")
    t.cdp.foto(FOTOS / "07-excluir-cadastro.png")
    registrar("EMP-DEL-04 frase errada não exclui (API recusa; na tela o botão fica desabilitado); aviso explica que documentos e históricos "
              "não serão apagados",
              c == 400 and c4 == 400 and desabilitado and "Os documentos e históricos não serão apagados." in caixa
              and "deixará de ficar disponível para novas solicitações" in caixa and registro_empresa(emp).get("excluida") is None, (r3, caixa[:200]))
    t.digitar(q("[data-campo=frase-exclusao]"), f"EXCLUIR {emp}")
    t.clicar(q("[data-acao=confirmar-exclusao-empresa]"))
    t.esperar(f"document.querySelector('.gestao h1').textContent==='Empresas' && !document.querySelector(\"[data-empresa='{emp}']\")", 30)
    t.estavel()
    t.cdp.foto(FOTOS / "08-apos-exclusao.png")
    dados = registro_empresa(emp)
    registrar("EMP-DEL-01 empresa sem operação ativa é excluída (exclusão LÓGICA: situação EXCLUIDA, piloto revogado, nada apagado)",
              dados.get("excluida") and not dados.get("piloto") and (TMP / "CLIENTES" / emp).is_dir()
              and "Status: EXCLUIDO" in (TMP / "CLIENTES" / emp / "CADASTRO.md").read_text(encoding="utf-8"), dados.get("excluida"))
    c, estado = req("GET", "/estado")
    ids = [x["id"] for x in estado["empresas"] + (estado.get("empresas_pendentes") or [])]
    t.clicar(q(".op-botao"))
    t.esperar("!document.querySelector('.op-painel').hidden")
    t.estavel()
    opcoes = t.js("Array.from(document.querySelectorAll('.op-form select')[0].options).map(o=>o.value)")
    t.clicar(q(".op-painel .fechar"))
    registrar("EMP-DEL-05 empresa excluída some das escolhas de Nova solicitação (API e tela)", emp not in ids and emp not in opcoes, (ids, opcoes))
    c, lote = req("POST", "/lotes", {"empresa": emp, "competencia": "2026-11", "fluxo": "DOCUMENTOS", "instrucao": "Teste após exclusão."})
    registrar("EMP-DEL-06 nova solicitação para a empresa excluída é recusada", c >= 400, (c, lote))
    c, lista = req("GET", "/solicitacoes")
    c2, det = req("GET", f"/solicitacoes/{sol}")
    registrar("EMP-DEL-07 históricos continuam disponíveis e identificam a empresa", any(s["sol"] == sol and s["empresa"] == emp for s in lista["solicitacoes"])
              and c2 == 200 and det.get("empresa") == emp, (c2, det.get("empresa")))
    depois = hashes(TMP / "CLIENTES" / emp)
    registrar("EMP-DEL-08 documentos da empresa preservados (todos os arquivos anteriores continuam idênticos)",
              docs_antes and all(depois.get(k) == v for k, v in docs_antes.items()), f"{len(docs_antes)} arquivos")
    liberados = hashes(TMP / "LIBERADOS") if (TMP / "LIBERADOS").is_dir() else {}
    registrar("EMP-DEL-09 saídas anteriores (TXT, Excel, balancete) preservadas", liberados_antes and liberados == liberados_antes,
              f"{len(liberados_antes)} arquivo(s)")
    c, r = req("POST", "/empresas", {"id": emp, "nome": "OUTRA EMPRESA FICTICIA LTDA", "cnpj": "90.090.090/0001-90", "regime": "SIMPLES"})
    registrar("EMP-DEL-10 código da empresa excluída não é reutilizado", c == 400 and "já existe" in r.get("erro", ""), r)
    c, lista_e = req("GET", "/empresas")
    registrar("EMP-DEL-11 excluir uma empresa não afeta outra (cadastro da empresa B intacto e ativo)",
              hashlib.sha256((TMP / "CLIENTES" / B["id"] / "empresa-local.json").read_bytes()).hexdigest() == outra_antes
              and any(x["id"] == B["id"] for x in lista_e) and not any(x["id"] == emp for x in lista_e))
    c, nova = req("POST", "/empresas", {"id": emp + "-NOVO", "nome": A["nome"], "cnpj": A["cnpj"], "regime": "LUCRO PRESUMIDO (FICTICIO)"})
    registrar("EMP-DEL-12 novo cadastro (mesmo CNPJ, novo código) não herda piloto, vínculos, plano nem regras",
              c == 201 and not nova.get("piloto") and not nova.get("contas") and not nova.get("plano") and not nova.get("contas_adiantamento")
              and not (TMP / "CLIENTES" / (emp + "-NOVO") / "REGRAS-DP.json").exists(), {k: nova.get(k) for k in ("id", "piloto", "contas")})
    t.clicar(q('[data-pagina="empresas"]'))
    t.esperar("document.querySelector('[data-mais-opcoes]')")
    t.clicar(f"{q('[data-mais-opcoes]')}.querySelector('summary')")
    t.clicar(f"{q('[data-cadastros-excluidos]')}.querySelector('summary')")
    t.esperar(f"document.querySelector('[data-cadastros-excluidos]').innerText.includes('{emp}')", 15)
    registrar("Cadastros excluídos consultáveis em Administração (com acesso ao histórico)", "Ver histórico" in t.texto(q("[data-cadastros-excluidos]")))


def registro_empresa(ident):
    return json.loads((TMP / "CLIENTES" / ident / "empresa-local.json").read_text(encoding="utf-8"))


def revisao_visual(t):
    """Revisão nas resoluções pedidas (1920×1080 e 1366×768): sem rolagem horizontal; resumo cabe sem rolar a tela."""
    for w, h in ((1920, 1080), (1366, 768)):
        t.cdp.chamar("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        t.cdp.chamar("Page.reload")
        t.esperar("window.EV && EV.app && document.querySelector('.gestao-nav')", 30)
        t.clicar(q('[data-pagina="empresas"]'))
        t.esperar("document.querySelectorAll('[data-empresa]').length>=1")
        t.estavel()
        lista = t.js("document.documentElement.scrollWidth<=innerWidth+1")
        t.cdp.foto(FOTOS / f"09-empresas-{w}x{h}.png")
        t.clicar(f"{q('[data-empresa]')}.querySelector('[data-acao=abrir-empresa]')")
        t.esperar("document.querySelector('[data-base-resumo]')")
        t.estavel()
        t.cdp.foto(FOTOS / f"10-empresa-{w}x{h}.png")
        empresa = t.js("document.documentElement.scrollWidth<=innerWidth+1")
        dentro = t.js("Array.from(document.querySelectorAll('.gestao-conteudo *')).filter(e=>e.offsetParent!==null&&e.getBoundingClientRect().right>document.querySelector('.gestao').getBoundingClientRect().right+1).length")
        registrar(f"Revisão visual {w}×{h}: Empresas e empresa sem rolagem horizontal nem conteúdo fora do painel", lista and empresa and dentro == 0, dentro)


def foto_operacional():
    arqs = sorted((str(p.relative_to(RAIZ)), p.stat().st_size, p.stat().st_mtime_ns) for p in (RAIZ / "CLIENTES").rglob("*") if p.is_file())
    reg = RAIZ / "COORDENADOR-GERAL" / "controle" / "solicitacoes.json"
    return arqs, hashlib.sha256(reg.read_bytes()).hexdigest() if reg.is_file() else None, (RAIZ / "LIBERADOS").exists()


def main():
    global srv
    antes = foto_operacional()
    chrome = None
    perfil = tempfile.mkdtemp(prefix="chrome-simplificacao-")
    try:
        am.preparar(servidor.pasta_runtime(), cenarios=["A", "B"])
        srv = servidor.iniciar(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        preparar_base_com_pendencias()
        url = f"http://127.0.0.1:{srv.server_port}/"
        chrome = subprocess.Popen([str(CHROME), "--headless=new", f"--remote-debugging-port={PORTA_CDP}", f"--user-data-dir={perfil}",
                                   "--window-size=1440,1000", "--no-first-run", "--disable-extensions", url],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cdp = None
        for _ in range(80):
            try:
                alvos = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORTA_CDP}/json/list", timeout=2))
                cdp = CDP(next(a for a in alvos if a.get("type") == "page" and a["url"].startswith(url))["webSocketDebuggerUrl"])
                break
            except Exception:
                time.sleep(0.25)
        assert cdp, "Chrome não respondeu na porta de depuração"
        cdp.chamar("Page.enable")
        cdp.chamar("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
        t = Tela(cdp)
        bateria(t)
        revisao_visual(t)
    except Exception as exc:
        import traceback
        registrar("XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-600:]}")
    finally:
        if chrome:
            chrome.terminate()
            try:
                chrome.wait(15)
            except subprocess.TimeoutExpired:
                chrome.kill()
        if srv:
            srv.shutdown()
            srv.server_close()
        registrar("Ambiente operacional intocado (CLIENTES/, registro e LIBERADOS/ reais)", foto_operacional() == antes)
        shutil.rmtree(perfil, ignore_errors=True)
        shutil.rmtree(TMP, ignore_errors=True)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {c}  — {d}")
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
