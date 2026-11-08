"""Interface (Chrome sem janela) contra a API REAL do aplicativo e os executores locais reais — dados 100% fictícios.

Todo o fluxo é feito pela TELA (cliques do mouse, digitação e seleção de arquivos via CDP), sem chamar as rotas de ação
diretamente. Leituras do registro/arquivos servem só para conferir o resultado. Cadastros (AGENTES_PRIME_CLIENTES), registro,
runtime, ordem ativa e LIBERADOS são temporários; o ambiente operacional não é tocado (conferido no final).
Falha de gravação do TXT é simulada substituindo a função de gravação no servidor deste processo; arquivo travado é um handle real.

Empresa: variante da amostra A com DUAS definições pendentes de propósito — regra bancária RB-006 (tarifa) PROPOSTA e política de
data dos lançamentos de DP PROPOSTA — para exercitar perguntas, aprovação de regra, fonte alterada, retomada e nova Conciliação.

Uso: .venv/Scripts/python.exe -I TESTES/ESCRITORIO/testar_interface_api_real.py [pasta para capturas]
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
TMP = Path(tempfile.mkdtemp(prefix="prime-ui-real-"))
for k, v in {"AGENTES_PRIME_RUNTIME": TMP / "runtime", "AGENTES_PRIME_REGISTRO_SOL": TMP / "registro.json",
             "AGENTES_PRIME_ORDEM_ATIVA": TMP / "ordem-ativa.json", "AGENTES_PRIME_CLAUDE": TMP / "claude-inexistente.exe",
             "LOCALAPPDATA": TMP / "localappdata", "AGENTES_PRIME_LIBERADOS": TMP / "LIBERADOS", "AGENTES_PRIME_CLIENTES": TMP / "CLIENTES"}.items():
    os.environ[k] = str(v)
(TMP / "CLIENTES").mkdir()
sys.path.insert(0, str(RAIZ / "API-LOCAL"))
sys.path.insert(0, str(RAIZ / "TESTES" / "API"))
import amostra_ficticia as am  # noqa: E402
import servidor  # noqa: E402
sys.path.insert(0, str(RAIZ / "TESTES"))
import ambiente_isolado as _ai  # noqa: E402
from e2e_navegador import CDP, CHROME  # noqa: E402

FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ui-real-capturas-"))
FOTOS.mkdir(parents=True, exist_ok=True)
def porta_livre():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORTA_CDP = porta_livre()        # porta própria a cada execução (não disputa Chrome de execução anterior)
EMP = {"id": "AMOSTRA-UI-TESTE-TMP", "nome": "EMPRESA AMOSTRA UI TESTE FICTICIA LTDA", "cnpj": "90.080.080/0001-25", "conta": "55555-5"}
ORIGINAL_A = dict(am.EMPRESAS["A"])
resultados = []
srv = None


def registrar(caso, ok, detalhe=""):
    resultados.append((caso, bool(ok), str(detalhe)[:400]))


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


def preparar_empresa():
    """Amostra A em CLIENTES temporário + duas definições pendentes (RB-006 PROPOSTA; data de DP PROPOSTA)."""
    am.EMPRESAS["A"].update(EMP)
    am.preparar(servidor.pasta_runtime(), cenarios=["A"])
    base = TMP / "CLIENTES" / EMP["id"]
    regras = (base / "REGRAS-BANCOS.md").read_text(encoding="utf-8").splitlines()
    regras = [l.replace("| TESTE_FICTICIO | Regra de TESTE da amostra fictícia (não é aprovação do Supervisor) |", "| PROPOSTA | - |")
              if l.startswith("| RB-006 ") else l for l in regras]
    (base / "REGRAS-BANCOS.md").write_text("\n".join(regras) + "\n", encoding="utf-8")
    dp = json.loads((base / "REGRAS-DP.json").read_text(encoding="utf-8"))
    dp["data_lancamento"].update(situacao="PROPOSTA", origem="Política proposta para o teste de interface (fictícia)")
    (base / "REGRAS-DP.json").write_text(json.dumps(dp, ensure_ascii=False, indent=2), encoding="utf-8")
    pasta = TMP / "docs-A"
    pasta.mkdir()
    for nome, conteudo in am.documentos("A").items():
        (pasta / nome).write_bytes(conteudo)
    nota = (f"NFS-E - NOTA FISCAL DE SERVICOS ELETRONICA (FICTICIA)\nPRESTADOR: {EMP['nome']}\nCNPJ DO PRESTADOR: {EMP['cnpj']}\n"
            f"TOMADOR: {am.BETA[0]}\nCNPJ DO TOMADOR: {am.BETA[1]}\nNUMERO DA NOTA: 104\nDATA DE EMISSAO: 30/10/2026\n"
            "COMPETENCIA: 10/2026\nVALOR DOS SERVICOS: R$ 1.500,00\nVALOR TOTAL DA NOTA: R$ 1.500,00\n")
    (TMP / "docs-complemento").mkdir()
    (TMP / "docs-complemento" / "01_nfse_104_beta.txt").write_text(nota, encoding="utf-8")
    return sorted(str(p) for p in pasta.iterdir()), [str(TMP / "docs-complemento" / "01_nfse_104_beta.txt")]


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
        """Marca o elemento da expressão JS (que pode ainda não existir) e devolve o seletor dele."""
        self.n += 1
        marca = f"t{self.n}"
        ok = self.esperar(f"(()=>{{const e=({expr});if(e){{e.dataset.alvoTeste='{marca}';return true}}return false}})()", s)
        if not ok:
            self.cdp.foto(FOTOS / f"falha-{marca}.png")
            raise AssertionError(f"elemento não encontrado: {expr}")
        return f"[data-alvo-teste='{marca}']"

    def clicar(self, expr, s=30):
        """Clique de mouse real no elemento VISÍVEL; se a tela foi redesenhada entre a busca e o clique, busca de novo."""
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
        raise AssertionError(f"elemento não clicável (ausente ou invisível): {expr}")

    def digitar(self, expr, texto):
        sel = self.alvo(expr)
        self.js(f"(()=>{{const e=document.querySelector(\"{sel}\");e.scrollIntoView({{block:'center'}});e.focus();e.select&&e.select()}})()")
        self.cdp.chamar("Input.insertText", text=texto)
        time.sleep(0.1)

    def texto(self, expr):
        return self.js(f"(()=>{{const e=({expr});return e?e.textContent:''}})()") or ""

    def estavel(self, s=30):
        """Tela parada: o conteúdo do painel não muda por 1 s (nenhuma renderização pendente que apagaria o que for digitado)."""
        fim, anterior = time.time() + s, None
        while time.time() < fim:
            atual = self.js("(document.querySelector('.op-painel:not([hidden])')||document.querySelector('.gestao:not([hidden])')||document.body).innerHTML.length+':'+document.body.innerText.length")
            if atual == anterior:
                return True
            anterior = atual
            time.sleep(1.0)
        return False

    def aba(self, nome):
        self.clicar(f"document.querySelector('.ac-aba[data-aba={nome}]')")


def q(sel):
    return f"document.querySelector({json.dumps(sel)})"


def por_texto(seletor, trecho, dentro="document"):
    return f"Array.from(({dentro}).querySelectorAll({json.dumps(seletor)})).find(e=>e.textContent.includes({json.dumps(trecho)}))"


def bateria(t, docs_a, docs_comp):
    cdp = t.cdp
    painel_livre = ("(()=>{const palco=document.querySelector('.palco').getBoundingClientRect();const painel=[document.querySelector('.gestao'),"
                    "document.querySelector('.op-painel')].find(p=>p&&!p.hidden);const limite=painel?painel.getBoundingClientRect().right:"
                    "document.querySelector('.gestao-nav').getBoundingClientRect().right;return palco.left>=limite-1&&palco.width>200&&"
                    "getComputedStyle(document.querySelector('.palco')).visibility==='visible'})()")
    t.esperar("window.EV && EV.app && document.querySelector('.gestao-nav')", 30)
    registrar("U-01 escritório visível ao lado do menu lateral, sem sobreposição", t.js(painel_livre))

    def nova_solicitacao(arquivos, instrucao):
        antes = set(registro())
        t.clicar(q(".op-botao"))
        t.esperar("!document.querySelector('.op-painel').hidden")
        t.alvo(f"Array.from(document.querySelectorAll('.op-form select')[0].options).find(o=>o.value==='{EMP['id']}')")
        t.js(f"(()=>{{const s=document.querySelectorAll('.op-form select')[0];s.value='{EMP['id']}';s.dispatchEvent(new Event('change'))}})()")
        t.js("(()=>{const s=document.querySelectorAll('.op-form select')[1];s.value='DOCUMENTOS';s.dispatchEvent(new Event('change'))})()")
        t.js("(()=>{const i=document.querySelector('.op-form input[type=month]');i.value='2026-10';i.dispatchEvent(new Event('input'));"
             "i.dispatchEvent(new Event('change'))})()")
        no = cdp.chamar("DOM.querySelector", nodeId=cdp.chamar("DOM.getDocument")["root"]["nodeId"], selector=".op-form input[type=file]")["nodeId"]
        cdp.chamar("DOM.setFileInputFiles", nodeId=no, files=arquivos)
        t.esperar(f"document.querySelectorAll('.op-arquivos li').length==={len(arquivos)}")
        t.digitar(q(".op-form textarea"), instrucao)
        if not t.js("document.querySelector('.op-form .op-confirma input').checked"):
            t.clicar("document.querySelector('.op-form .op-confirma input')")
        t.clicar(q(".op-iniciar"))
        fim = time.time() + 120
        while time.time() < fim and not (set(registro()) - antes):
            time.sleep(0.3)
        novos = sorted(set(registro()) - antes)
        assert novos, "SOL não criada; mensagem da tela: " + t.texto(q(".op-msg"))
        sol = novos[0]
        ocioso()
        t.esperar(f"document.querySelector('.ac-sol') && document.querySelector('.ac-sol').textContent==='{sol}' && "
                  "document.querySelector('.ac-faixa') && document.querySelector('.ac-faixa').dataset.faixa!=='azul'", 120)
        t.estavel()
        return sol

    def abrir_sol(sol):
        t.clicar(q('[data-pagina="solicitacoes"]'))
        t.esperar("document.querySelector('.gestao h1') && document.querySelector('.gestao h1').textContent==='Consultar solicitações'")
        t.clicar(f"(Array.from(document.querySelectorAll('.gestao-lista .gestao-item')).find(a=>a.querySelector('h2').textContent==='{sol}')||{{}})"
                 ".querySelector && Array.from(document.querySelectorAll('.gestao-lista .gestao-item')).find(a=>a.querySelector('h2')"
                 f".textContent==='{sol}').querySelector('button')")
        # tela pronta = cabeçalho da SOL pedida (não basta o número aparecer em outra parte, ex.: relação entre SOLs)
        t.esperar(f"document.querySelector('.ac-sol') && document.querySelector('.ac-sol').textContent==='{sol}' && document.querySelector('.ac-resumo')")
        t.estavel()

    # ---------------- SOL 1: definições pendentes, política de data ausente
    sol1 = nova_solicitacao(docs_a, "Receber os documentos de outubro/2026, distribuir por área e preparar o fechamento (SIMULAÇÃO).")
    t.aba("resumo")
    defs = t.texto(q("[data-definicoes-necessarias]"))
    imp = t.texto(q(".ac-impedimentos"))
    t.aba("lancamentos")
    lanc = t.texto(q(".op-sol"))
    cdp.foto(FOTOS / "01-definicoes-pendentes.png")
    registrar("U-02 perguntas e definições pendentes na tela: regra bancária RB-006 proposta e política de data de DP; aprovação impedida",
              "BANCOS / RB-006" in defs and "DP / DATA_LANCAMENTO" in defs and "DATA_LANCAMENTO" in lanc and "não aplicada" in lanc
              and "incompleto" in imp, f"{defs[:300]} || {imp[:200]}")

    # ---------------- proposta e aprovação de regra bancária pela fila de decisões
    t.aba("decisoes")
    t.estavel()
    t.clicar(por_texto("summary", "Aprovar regra RB-006"))
    t.digitar(f"({por_texto('details', 'Aprovar regra RB-006')}).querySelector('input')", f"VALIDADO REGRA {EMP['id']} RB-006")
    t.clicar(por_texto("button", "Aprovar regra RB-006 para uso futuro"))
    arq_regras = TMP / "CLIENTES" / EMP["id"] / "REGRAS-BANCOS.md"
    fim = time.time() + 30
    sys.path.insert(0, str(RAIZ / "AGENTES" / "CONTABILIDADE"))
    import governanca_regras
    while time.time() < fim and "frase=VALIDADO REGRA " + EMP["id"] + " RB-006" not in governanca_regras.ler_texto(arq_regras):
        time.sleep(0.2)
    fim = time.time() + 30                                        # a nova tentativa começa (Financeiro → Bancos → Conciliação)
    while time.time() < fim and not (servidor.EM_EXECUCAO["sol"] or len(registro()[sol1].get("bancos", [])) >= 2):
        time.sleep(0.2)
    ocioso()
    regras_md = (TMP / "CLIENTES" / EMP["id"] / "REGRAS-BANCOS.md").read_text(encoding="utf-8")
    tarifa = [l for l in json.loads(urllib.request.urlopen(urllib.request.Request(
        f"http://127.0.0.1:{srv.server_port}/api/solicitacoes/{sol1}/financeiro", headers={"X-Prime-Sessao": srv.token})).read())["bancos"]["lancamentos"]
        if l["valor"] == "45.00"]
    registrar("U-03 regra proposta aprovada pela tela com a frase exata: confirmação vinculada a empresa/regra/versão, nova tentativa "
              "Financeiro → Bancos → Conciliação e tarifa proposta",
              f"CONFIRMADA; frase=VALIDADO REGRA {EMP['id']} RB-006; versao=1; por=Supervisor Contábil" in regras_md
              and tarifa and tarifa[0]["status"] == "PROPOSTO", tarifa[:1])

    # ---------------- política de data: confirmação em Empresas → fonte alterada → desatualizada → retomada pela tela
    abrir_sol(sol1)
    t.aba("resumo")
    t.clicar(q("[data-ir-definicoes]"))
    t.esperar("document.querySelector('[data-definicoes]')")
    t.digitar(f"{q('[data-definicao=\"DP/DATA_LANCAMENTO\"]')}.querySelector('input')", f"VALIDADO REGRA DP {EMP['id']} DATA_LANCAMENTO")
    t.clicar(f"{q('[data-definicao=\"DP/DATA_LANCAMENTO\"]')}.querySelector('button')")
    t.esperar("document.querySelector('[data-definicoes]') && !document.querySelector('[data-definicao=\"DP/DATA_LANCAMENTO\"]')")
    restantes = t.texto(q("[data-definicoes]"))
    t.esperar(painel_livre, 5)
    cdp.foto(FOTOS / "02-empresa-definicoes-confirmadas.png")
    registrar("U-04 Empresas: definição de data confirmada pela tela (frase exata); lista de definições sem pendências; painel lateral não cobre o escritório",
              "Nenhuma definição pendente" in restantes and t.js(painel_livre), restantes[:200])
    abrir_sol(sol1)
    t.aba("conciliacao")
    desat = t.texto(q("[data-desatualizada]"))
    t.aba("decisoes")
    ret = t.texto(q("[data-etapa-retomada=CONTABILIDADE_DP]"))
    registrar("U-05 resultado desatualizado por mudança de fonte: aviso com o motivo e as etapas a rever; retomada oferecida para a etapa",
              "referências de DP alterado depois da etapa CONTABILIDADE_DP" in desat and "desatualizada" in ret, f"{desat[:250]} || {ret[:150]}")
    t.digitar(f"{q('[data-etapa-retomada=CONTABILIDADE_DP]')}.querySelector('textarea')", "Política de data do DP confirmada pelo Supervisor.")
    t.clicar(f"{q('[data-etapa-retomada=CONTABILIDADE_DP]')}.querySelector('input[type=checkbox]')")
    t.clicar(q("[data-retomar=CONTABILIDADE_DP]"))
    fim = time.time() + 30
    while time.time() < fim and not registro()[sol1].get("retomadas"):
        time.sleep(0.2)
    ocioso()
    abrir_sol(sol1)
    t.aba("conciliacao")
    t.esperar("document.querySelector('[data-conciliacao]')")
    conc = t.texto(q("[data-conciliacao]"))
    t.aba("resumo")
    faixa = t.texto(q(".ac-faixa"))
    hist = registro()[sol1]["conciliacao"]
    registrar("U-06 retomada pela tela reexecuta Contabilidade/DP e uma NOVA Conciliação, vigente; histórico preservado; pronto para aprovar",
              "Vigente" in conc and len(hist) >= 3 and "Tudo conferido" in faixa and "documento externo" in conc, f"{faixa[:120]} || conciliações={len(hist)}")

    # ---------------- relação entre SOLs: revisão (mesmos fatos, original ainda não aprovada)
    sol2 = nova_solicitacao(docs_a, "Reenvio dos documentos de outubro/2026 para revisão da proposta (SIMULAÇÃO).")
    t.aba("resumo")
    rel2 = t.texto(q("[data-relacao-sols]"))
    registrar("U-07 segunda SOL com os mesmos fatos da original não aprovada: relação 'revisão de proposta' na tela",
              sol1 in rel2 and "revisão de proposta" in rel2, rel2[:300])

    # ---------------- aprovação do fechamento pela tela, TXT e download
    abrir_sol(sol1)
    t.aba("resumo")

    def aprovar(ciente=False):
        t.estavel()
        t.clicar(q("[data-acao-aprovacao=abrir-aprovar]"))
        t.esperar("document.querySelector('[data-acao-aprovacao=aprovar]') && !document.querySelector('[data-acao-aprovacao=aprovar]').closest('.ac-confirmacao').hidden", 10)
        t.digitar(q('[aria-label="Frase de aprovação"]'), f"APROVO FECHAMENTO {sol1}")
        t.digitar(q('[aria-label="Justificativa da aprovação"]'), "Conferi propostas e Conciliação da amostra fictícia.")
        form = "document.querySelector('[data-acao-aprovacao=aprovar]').closest('.ac-confirmacao')"
        t.clicar(f"{form}.querySelectorAll('.op-confirma input')[0]")
        if ciente:
            t.clicar(f"{form}.querySelectorAll('.op-confirma input')[1]")
        t.clicar(q("[data-acao-aprovacao=aprovar]"))
        t.esperar("document.querySelector('.ac-faixa') && document.querySelector('.ac-faixa').dataset.faixa==='aprovado'", 60)
        time.sleep(0.5)

    aprovar()
    ap = registro()[sol1]["aprovacao"]
    faixa = t.texto(q(".ac-faixa"))
    txt = servidor.caminho_registrado(ap["arquivo_txt"])
    destino = TMP / "downloads"
    destino.mkdir()
    cdp.chamar("Browser.setDownloadBehavior", behavior="allow", downloadPath=str(destino))
    t.clicar(q("[data-acao-aprovacao=baixar-txt]"))
    fim = time.time() + 20
    while time.time() < fim and not [p for p in destino.iterdir() if p.suffix == ".txt"]:
        time.sleep(0.2)
    baixados = [p for p in destino.iterdir() if p.suffix == ".txt"]
    linhas = txt.read_bytes().decode("cp1252").split("\r\n")[:-1]
    cdp.foto(FOTOS / "03-aprovado-txt.png")
    registrar("U-08 aprovação expressa pela tela; faixa com a situação EFETIVA (TXT liberado para importação MANUAL); download pela tela "
              "devolve exatamente o arquivo liberado",
              ap["liberacao_dominio"] == "LIBERADO_PARA_IMPORTACAO_MANUAL" and "TXT liberado para importação MANUAL" in faixa
              and "nenhum arquivo TXT entregue" not in faixa and baixados and baixados[0].read_bytes() == txt.read_bytes(),
              f"{faixa[:150]} · linhas={len(linhas)} · total={ap.get('txt_total')} · baixados={[p.name for p in baixados]}")
    INFO.append(f"TXT da SOL aprovada: {len(linhas)} linhas, total {ap.get('txt_total')}, sha256 {ap.get('txt_sha256')[:16]}…")
    iguais = {}
    for tipo in ("excel", "balancete"):
        t.clicar(q(f"[data-acao-aprovacao=baixar-{tipo}]"))
        nome = Path(ap["anexos"][tipo]["arquivo"]).name
        fim = time.time() + 20
        while time.time() < fim and not (destino / nome).is_file():
            time.sleep(0.2)
        time.sleep(0.3)
        iguais[tipo] = (destino / nome).is_file() and (destino / nome).read_bytes() == servidor.caminho_registrado(ap["anexos"][tipo]["arquivo"]).read_bytes()
    registrar("U-15 botões da tela baixam o Excel dos lançamentos e o balancete exatamente como registrados (mesma versão do TXT)",
              all(iguais.values()) and "não comprova importação" in t.texto(q(".ac-aprovacao")), iguais)

    # ---------------- revisão vira repetição; complemento legítimo
    abrir_sol(sol2)
    t.aba("resumo")
    rel2b = t.texto(q("[data-relacao-sols]"))
    imp2 = t.texto(q(".ac-impedimentos"))
    botao_bloqueado = t.js("document.querySelector('[data-acao-aprovacao=abrir-aprovar]').disabled")
    sol3 = nova_solicitacao(docs_comp, "Complemento de outubro/2026: nota emitida depois do fechamento (SIMULAÇÃO).")
    t.aba("resumo")
    rel3 = t.texto(q("[data-relacao-sols]"))
    registrar("U-09 relação entre original, revisão e complemento: a revisão passa a 'repetição de fatos aprovados' (aprovação bloqueada "
              "por duplicação); o complemento aparece como 'complemento'",
              "repetição de fatos aprovados" in rel2b and "Duplicação" in imp2 and botao_bloqueado and "complemento" in rel3
              and sol1 in rel3 and sol2 in rel3, f"{rel2b[:150]} || {rel3[:200]}")

    # ---------------- revogação, falha na geração e nova tentativa explícita
    def revogar():
        t.estavel()
        t.clicar(q("[data-acao-aprovacao=abrir-revogar]"))
        t.digitar(q('[aria-label="Justificativa da revogação"]'), "Revogação de teste fictício pela interface.")
        t.clicar("document.querySelector('[data-acao-aprovacao=revogar]').closest('.ac-confirmacao').querySelector('.op-confirma input')")
        t.clicar(q("[data-acao-aprovacao=revogar]"))
        t.esperar("document.querySelector('.ac-faixa') && document.querySelector('.ac-faixa').dataset.faixa!=='aprovado'", 60)
        time.sleep(0.5)

    abrir_sol(sol1)
    t.aba("resumo")
    revogar()
    sem_download = not t.js("!!document.querySelector('[data-acao-aprovacao=baixar-txt]')")
    revogado_ok = registro()[sol1]["aprovacoes_anteriores"][-1]["liberacao_dominio"] == "REVOGADO"
    original = servidor.gravar_exclusivo

    def falhar(arquivo, conteudo):
        raise OSError("disco cheio (simulado)")
    servidor.gravar_exclusivo = falhar
    try:
        ciencia = t.texto("(document.querySelector('[data-acao-aprovacao=aprovar]')||document.body).closest('.ac-confirmacao')?.querySelectorAll('.op-confirma')[1]")
        aprovar(ciente=True)
        msg_falha = t.texto(q(".ac-aprovacao"))
        lib_falha = registro()[sol1]["aprovacao"]["liberacao_dominio"]
        time.sleep(2)
        sem_repeticao = registro()[sol1]["aprovacao"]["liberacao_dominio"] == "FALHOU"
    finally:
        servidor.gravar_exclusivo = original
    t.digitar(f"{q('[data-acao-txt=gerar]')}.querySelector('textarea')", "Causa corrigida no teste; nova geração explícita.")
    t.clicar(f"{q('[data-acao-txt=gerar]')}.querySelector('button')")
    t.esperar("!!document.querySelector('[data-acao-aprovacao=baixar-txt]')", 30)
    cdp.foto(FOTOS / "04-nova-geracao.png")
    registrar("U-10 revogação pela tela bloqueia o download; reaprovação exige ciência dos fatos já exportados; falha na geração visível "
              "(sem repetição automática) e nova tentativa explícita pela tela libera o TXT",
              sem_download and revogado_ok and "já saíram em TXT" in ciencia and lib_falha == "FALHOU" and sem_repeticao
              and "disco cheio" in msg_falha and registro()[sol1]["aprovacao"]["liberacao_dominio"] == "LIBERADO_PARA_IMPORTACAO_MANUAL",
              f"{lib_falha} {msg_falha[:200]}")

    # ---------------- revogação com arquivo travado e "Mover arquivo revogado"
    txt = servidor.caminho_registrado(registro()[sol1]["aprovacao"]["arquivo_txt"])
    trava = open(txt, "rb")
    try:
        revogar()
        posix_rename = not bool(t.js("document.querySelector('[data-acao-txt=mover-revogado]')"))
        if not posix_rename:
            t.esperar("!!document.querySelector('[data-acao-txt=mover-revogado]')", 20)
        aviso = t.texto(q(".ac-aprovacao"))
        download = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}/api/solicitacoes/{sol1}/txt-dominio", headers={"X-Prime-Sessao": srv.token})
        try:
            urllib.request.urlopen(download)
            codigo = 200
        except urllib.error.HTTPError as e:
            codigo = e.code
        if not posix_rename:
            t.digitar(f"{q('[data-acao-txt=mover-revogado]')}.querySelector('textarea')", "Tentativa com o arquivo ainda aberto.")
            t.clicar(f"{q('[data-acao-txt=mover-revogado]')}.querySelector('button')")
        time.sleep(1.5)
        ainda = registro()[sol1]["aprovacoes_anteriores"][-1]["liberacao_dominio"]
        cdp.foto(FOTOS / "05-arquivo-travado.png")
    finally:
        trava.close()
    if not posix_rename:
        abrir_sol(sol1)
        t.aba("resumo")
        t.digitar(f"{q('[data-acao-txt=mover-revogado]')}.querySelector('textarea')", "Arquivo fechado; mover agora.")
        t.clicar(f"{q('[data-acao-txt=mover-revogado]')}.querySelector('button')")
        t.esperar("!document.querySelector('[data-acao-txt=mover-revogado]')", 20)
    ant = registro()[sol1]["aprovacoes_anteriores"][-1]
    registrar("U-11 revogação com arquivo travado: tela avisa que o arquivo NÃO foi movido, download bloqueado na hora; 'Mover arquivo "
              "revogado' falha com o arquivo aberto e renomeia depois de fechado",
              ((posix_rename and codigo == 404 and not txt.exists()) or
               (not posix_rename and "NÃO importe" in aviso and codigo == 404 and ainda == "REVOGADO_ARQUIVO_NAO_MOVIDO" and ant["liberacao_dominio"] == "REVOGADO"
                and not txt.exists() and [m["movimentacao"] for m in ant["movimentacoes_revogacao"]] == ["FALHOU", "FALHOU", "RENOMEADO"])),
              f"{codigo} {ainda} {aviso[:200]}")
    faixa = t.texto(q(".ac-faixa"))
    registrar("U-12 mensagens coerentes depois da revogação: sem botão de download, sem afirmar TXT liberado; aviso de que revogar não estorna o Domínio",
              not t.js("!!document.querySelector('[data-acao-aprovacao=baixar-txt]')") and "TXT liberado" not in faixa
              and "não estorna" in t.texto(q(".ac-aprovacao")), faixa[:150])

    # ---------------- exclusão definitiva pela lixeira (complemento, sem aprovação), toda pela tela
    t.js("window.confirm=()=>true")
    t.clicar(q('[data-pagina="solicitacoes"]'))
    t.esperar("document.querySelector('.gestao h1') && document.querySelector('.gestao h1').textContent==='Consultar solicitações'")
    t.estavel()
    t.clicar(f"Array.from(document.querySelectorAll('.gestao-lista .gestao-item')).find(a=>a.querySelector('h2').textContent==='{sol3}')"
             ".querySelector('[data-acao=excluir]')")
    t.esperar(f"!Array.from(document.querySelectorAll('.gestao-lista .gestao-item')).some(a=>a.querySelector('h2').textContent==='{sol3}')")
    t.clicar(q("[data-acao=lixeira]"))
    t.esperar(f"document.querySelector('[data-exclusao=\"{sol3}\"]')")
    t.estavel()
    t.clicar(f"{q(f'[data-exclusao="{sol3}"]')}.closest('.gestao-item').querySelector('[data-acao=previa-exclusao]')")
    t.esperar(f"{q(f'[data-exclusao="{sol3}"]')}.textContent.includes('Permanece')")
    previa = t.texto(q(f'[data-exclusao="{sol3}"]'))
    t.digitar(q(f'[aria-label="Frase de exclusão definitiva de {sol3}"]'), f"EXCLUIR DEFINITIVAMENTE {sol3}")
    t.digitar(q(f'[aria-label="Justificativa da exclusão de {sol3}"]'), "Complemento de teste fictício excluído pela tela.")
    t.clicar(f"{q(f'[data-exclusao="{sol3}"]')}.querySelector('[data-acao=confirmar-exclusao]')")
    t.esperar(f"!document.querySelector('[data-exclusao=\"{sol3}\"]') && document.querySelector('[data-registros-minimos]')", 30)
    minimos = t.texto(q("[data-registros-minimos]"))
    reg = _ai.registro_isolado()
    registrar("U-16 exclusão definitiva pela tela (lixeira): prévia mostra o que será apagado e o que permanece; frase exata; a SOL "
              "sai do registro e aparece só no registro mínimo",
              "Será apagado" in previa and "Permanece" in previa and sol3 not in reg["solicitacoes"] and sol3 in reg.get("registros_minimos", {})
              and sol3 in minimos, f"{previa[:200]} || {minimos[:150]}")

    # ---------------- movimento reduzido
    cdp.chamar("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
    cdp.chamar("Page.reload")
    t.esperar("window.EV && EV.app && document.querySelector('.gestao-nav')", 30)
    time.sleep(1.5)
    a = cdp.chamar("Page.captureScreenshot", format="png")["data"]
    time.sleep(0.8)
    b = cdp.chamar("Page.captureScreenshot", format="png")["data"]
    reduzido = t.js("matchMedia('(prefers-reduced-motion: reduce)').matches")
    registrar("U-13 movimento reduzido respeitado com dados reais: cena estática (sem caminhada) e escritório visível", reduzido and a == b and t.js(painel_livre))


INFO = []


def foto_operacional():
    clientes = sorted((str(p.relative_to(RAIZ)), p.stat().st_size, p.stat().st_mtime_ns) for p in (RAIZ / "CLIENTES").rglob("*") if p.is_file())
    reg = RAIZ / "COORDENADOR-GERAL" / "controle" / "solicitacoes.json"
    return clientes, hashlib.sha256(reg.read_bytes()).hexdigest() if reg.is_file() else None, (RAIZ / "LIBERADOS").exists()


def main():
    global srv
    antes = foto_operacional()
    chrome = None
    perfil = tempfile.mkdtemp(prefix="chrome-ui-real-")
    try:
        docs_a, docs_comp = preparar_empresa()
        srv = servidor.iniciar(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
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
        bateria(Tela(cdp), docs_a, docs_comp)
    except Exception as exc:
        import traceback
        registrar("U-XX bateria interrompida", False, f"{type(exc).__name__}: {exc} {traceback.format_exc()[-500:]}")
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
        am.EMPRESAS["A"].clear()
        am.EMPRESAS["A"].update(ORIGINAL_A)
        registrar("U-14 ambiente operacional intocado (CLIENTES/, registro e LIBERADOS/ reais)", foto_operacional() == antes)
        shutil.rmtree(perfil, ignore_errors=True)
        shutil.rmtree(TMP, ignore_errors=True)
    falhas = 0
    for c, ok, d in resultados:
        falhas += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {c}  — {d}")
    for i in INFO:
        print("INFO  " + i)
    print(f"\nTOTAL: {len(resultados)} casos · {len(resultados) - falhas} PASS · {falhas} FAIL · capturas em {FOTOS}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
