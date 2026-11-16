"""ESPECIALISTA FISCAL · RELATÓRIO DE SITUAÇÃO FISCAL (RFB/PGFN) → SITUACAO_FISCAL_NORMALIZADA_V1.

Fonte de CONFERÊNCIA ADICIONAL da Conciliação Caixinha. Nunca comprova pagamento (só o e-CAC comprova) e "sem pendências" NÃO
significa que os tributos estejam baixados na contabilidade.

Leitura por rótulos e seções do relatório "Informações de Apoio para Emissão de Certidão" / "Relatório de Situação Fiscal":
- data de emissão ("Data:", "Emitido em", "Data da consulta") — respeitada: vencimento posterior à emissão = A VENCER, não pendente;
- seções: "Pendência - Débito", "Débito com Exigibilidade Suspensa", "Parcelamento", "Pendência - Omissão", "Pendência - Processo
  Fiscal", "Inscrição em Dívida Ativa" e similares; frase "Não foram detectadas pendências" registrada como SEM_PENDENCIAS_DECLARADAS;
- linhas de débito: [código de receita] [denominação] PA vencimento valor original saldo devedor [multa juros saldo consolidado] situação.
Layout a homologar com o arquivo real da empresa piloto (leitor marcado LAYOUT_A_HOMOLOGAR).
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ / "API-LOCAL") not in sys.path:
    sys.path.insert(0, str(RAIZ / "API-LOCAL"))
import caixinha_comum as cc  # noqa: E402

CONTRATO = "SITUACAO_FISCAL_NORMALIZADA_V1"
LEITOR = "SITUACAO_FISCAL_ROTULOS_V1"
SITUACAO_LEITOR = "CONFERIDO_COM_ARQUIVO_REAL_PILOTO"
SECOES = (("EXIGIBILIDADE SUSPENSA", "EXIGIBILIDADE_SUSPENSA"), ("PARCELAMENTO", "PARCELAMENTO"), ("OMISSAO", "OMISSAO_DECLARACAO"),
          ("DIVIDA ATIVA", "DIVIDA_ATIVA"), ("PROCESSO FISCAL", "PROCESSO_FISCAL"), ("PENDENCIA - DEBITO", "DEBITO_PENDENTE"),
          ("PENDENCIA DEBITO", "DEBITO_PENDENTE"), ("DEBITO", "DEBITO_PENDENTE"), ("PENDENCIA", "OUTRA_PENDENCIA"))
RE_DEBITO = re.compile(r"^(?:(\d{4})(?:-\d{2})?\s*-?\s*)?(.*?)\s*(\d{2}/\d{4}|\d{2}/\d{2}/\d{4}|\d{2}/\d{2}/\d{4}|\d{4})\s+(\d{2}/\d{2}/\d{4})\s+"
                       r"((?:" + cc.DINHEIRO + r"\s*)+)\s*([A-Z][A-Z ./-]*)?$")
SEM_PENDENCIAS = ("NAO FORAM DETECTADAS PENDENCIAS", "NAO CONSTAM PENDENCIAS", "SEM PENDENCIAS")


def reconhece(texto: str) -> bool:
    t = cc.norm(texto)
    return ("INFORMACOES DE APOIO PARA EMISSAO DE CERTIDAO" in t or "RELATORIO DE SITUACAO FISCAL" in t
            or ("SITUACAO FISCAL" in t and ("RECEITA FEDERAL" in t or "PROCURADORIA" in t)))


def _secao(linha: str):
    if RE_DEBITO.match(linha):
        return None
    for marcador, tipo in SECOES:
        if marcador in linha and len(linha) < 120 and not cc.RE_DINHEIRO.search(linha):
            return tipo
    return None


def ler(a: dict, empresa: str, cnpjs_empresa) -> dict:
    f = cc.ficha(a, "SITUACAO_FISCAL", empresa)
    f["leitor"], f["situacao_leitor"] = LEITOR, SITUACAO_LEITOR
    motivo = cc.leitura_utilizavel(a)
    if motivo:
        f["pendencias"].append(f"Pendência de leitura: {motivo}. Relatório não aproveitado.")
        return dict(f, itens=[], sem_pendencias_declaradas=None)
    texto = cc.texto_total(a)
    if not reconhece(texto):
        f["pendencias"].append("Estrutura do Relatório de Situação Fiscal não reconhecida pelo conteúdo.")
        return dict(f, itens=[], sem_pendencias_declaradas=None)
    f["reconhecimento"] = "RECONHECIDO"
    t = cc.norm(texto)
    completos = cc.cnpjs_no_texto(texto)
    raizes = ["".join(m.groups()) for m in cc.RE_CNPJ_RAIZ.finditer(texto)]
    encontrados = completos + raizes
    if not encontrados:
        f["pendencias"].append("CNPJ do contribuinte não identificado.")
    elif not cc.cnpj_confere(encontrados, cnpjs_empresa):
        f["pendencias"].append("CNPJ do relatório não é da empresa selecionada: relatório não aproveitado (isolamento entre empresas).")
        return dict(f, itens=[], sem_pendencias_declaradas=None)
    f["cnpj"] = next((c for c in encontrados if cc.cnpj_confere([c], cnpjs_empresa)), None)
    m = re.search(r"(?:^|\s)(?:DATA|EMITIDO EM|DATA DA CONSULTA|DATA DE EMISSAO)\s*:?\s*(\d{2}/\d{2}/\d{4})", t, re.M)
    if not m:                                 # cabeçalho do relatório da RFB: "dd/mm/aaaa hh:mm:ss" (sem rótulo) nas primeiras linhas
        m = re.search(r"(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}:\d{2}", "\n".join(t.splitlines()[:8]))
    f["emissao"] = cc.data_iso(m.group(1)) if m else None
    if not f["emissao"]:
        f["pendencias"].append("Data de emissão do relatório não identificada: vencidos × a vencer não podem ser separados.")
    itens, secao = [], None
    for pagina, conteudo in cc.paginas(a):
        for n, bruta in enumerate(conteudo.splitlines(), 1):
            linha = cc.norm(bruta)
            if not linha:
                continue
            s = _secao(linha)
            if s:
                secao = s
                continue
            md = RE_DEBITO.match(linha)
            if not md or secao is None:
                continue
            valores = cc.RE_DINHEIRO.findall(md.group(5))
            try:
                vals = [cc.valor(v) for v in valores]
            except ValueError:
                f["pendencias"].append(f"Página {pagina}, linha {n}: valor ilegível; item não aproveitado.")
                continue
            venc = cc.data_iso(md.group(4))
            situacao_doc = (md.group(6) or "").strip() or None
            pa = cc.periodo_apuracao(md.group(3))
            estado = ("A_VENCER" if venc and f["emissao"] and venc > f["emissao"] else "VENCIDO" if venc and f["emissao"] else "NAO_DETERMINADO")
            item = {"id": "SF-" + cc.chave_hash(empresa, f["sha256"], pagina, n), "categoria": secao, "codigo_receita": md.group(1),
                    "denominacao": md.group(2).strip(" -") or None, "periodo_apuracao": pa, "vencimento": venc,
                    "valor_original": cc.txt(vals[0]) if vals else None, "saldo_devedor": cc.txt(vals[1]) if len(vals) > 1 else None,
                    "saldo_consolidado": cc.txt(vals[-1]) if len(vals) > 3 else None, "situacao_documento": situacao_doc,
                    "estado_vencimento": estado, "origem": {"documento": f["id"], "arquivo": f["arquivo"], "sha256": f["sha256"],
                                                            "pagina": pagina, "linha": n, "leitor": LEITOR}}
            if secao == "DEBITO_PENDENTE" and estado == "A_VENCER":
                item["observacao"] = "Vencimento posterior à emissão do relatório: tributo a vencer, não débito pendente."
            itens.append(item)
    sem = any(x in t for x in SEM_PENDENCIAS)
    f["dados"] = {"itens": len(itens), "debitos_pendentes": sum(i["categoria"] == "DEBITO_PENDENTE" and i["estado_vencimento"] != "A_VENCER"
                                                                for i in itens),
                  "a_vencer": sum(i["estado_vencimento"] == "A_VENCER" for i in itens),
                  "exigibilidade_suspensa": sum(i["categoria"] == "EXIGIBILIDADE_SUSPENSA" for i in itens),
                  "parcelamentos": sum(i["categoria"] == "PARCELAMENTO" for i in itens), "sem_pendencias_declaradas": sem}
    if sem and itens:
        f["pendencias"].append("Relatório declara ausência de pendências e também lista itens: conferir o original.")
    return dict(f, itens=itens, sem_pendencias_declaradas=sem,
                aviso="Situação fiscal é conferência ADICIONAL: não comprova pagamento nem baixa contábil.")
