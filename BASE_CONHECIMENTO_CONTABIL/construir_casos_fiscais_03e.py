"""Gera os vinte casos de consulta fiscal exclusivamente fictícios."""
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
F=json.loads((BASE/"fundamentos_fiscais.json").read_text(encoding="utf-8"))["REGISTROS"]
BY={x["ID"]:x for x in F}
SPECS=[
("Compra de mercadoria com tributo potencialmente recuperável","Compra fictícia com documento e valor de tributo destacado; elegibilidade do crédito ainda precisa de norma/operação.",["FISC-02","FISC-10"],"FISCAL + CONTÁBIL","Crédito somente se hipótese legal, regime, item, uso e evidência forem confirmados; nenhuma contabilização automática."),
("Compra com tributo potencialmente não recuperável","Documento fictício indica tributo, sem suporte para afirmar crédito.",["FISC-02","FISC-11"],"FISCAL + CONTÁBIL","Não reconhecer crédito pelo destaque; analisar custo do item segundo referencial e legislação confirmados."),
("Compra de serviço","Nota fictícia de serviço contratado com município/local e contrato ainda a validar.",["FISC-04","FISC-14"],"FISCAL + CONTÁBIL","Confirmar serviço, local, retenções e regras municipal/federal; reconhecimento contábil considera execução e referencial."),
("Venda de mercadoria","NF-e fictícia emitida e autorizada; comprovante de entrega ainda vinculado.",["FISC-03","FISC-07","FISC-08"],"FISCAL + CONTÁBIL","Emissão informa documento fiscal; receita e tributo devem ser avaliados conforme entrega, contrato e regras vigentes."),
("Prestação de serviço","NFS-e fictícia emitida para serviço mensal, com medição contratual.",["FISC-04","FISC-07","FISC-14"],"FISCAL + CONTÁBIL","Confirmar serviço realizado, competência, município e hipótese de ISS; emissão e recebimento não substituem reconhecimento."),
("NF de entrada cancelada","Evento fictício de cancelamento relacionado a uma NF-e de entrada.",["FISC-02","FISC-06"],"FISCAL","Validar evento/protocolo e se documento já gerou registro ou crédito; não estornar automaticamente."),
("NF de saída cancelada","Evento fictício de cancelamento relacionado a NF-e de saída.",["FISC-03","FISC-06","FISC-13"],"FISCAL + CONTÁBIL","Confirmar validade do evento, período e reflexos; ajuste contábil/fiscal depende de registro anterior e revisão."),
("Devolução de compra","Mercadoria fictícia devolvida parcialmente, com documento referenciando origem.",["FISC-02","FISC-06","FISC-10"],"FISCAL + CONTÁBIL","Vincular documento original, quantidade e evento; avaliar tributo/crédito e reversão sem presumir alíquotas."),
("Devolução de venda","Cliente fictício devolve mercadoria e apresenta documento relacionado à venda original.",["FISC-03","FISC-06","FISC-07"],"FISCAL + CONTÁBIL","Vincular venda e devolução; verificar tratamento fiscal e contábil, período e estoque antes de propor ajustes."),
("Serviço contratado com retenções","NFS-e fictícia apresenta rótulo de IRRF/CSRF/ISS, sem decisão sobre hipótese.",["FISC-04","FISC-09","FISC-16"],"FISCAL + CONTÁBIL","Identificar retenção separadamente do líquido após validar natureza, pagador, prestador, legislação e comprovantes."),
("Serviço prestado com retenções sofridas","NFS-e fictícia e demonstrativo do cliente indicam possível retenção sofrida.",["FISC-04","FISC-09","FISC-16"],"FISCAL + CONTÁBIL","Confirmar informe/comprovante, tributo, titularidade e possibilidade legal de compensar; não abater por mera indicação textual."),
("Tributo próprio apurado","Demonstrativo fictício declara tributo, competência e valor; guia relacionada.",["FISC-08","FISC-18"],"FISCAL + CONTÁBIL + FINANCEIRO","Separar declaração/apuração, passivo contábil e pagamento; não recalcular valor declarado nem presumir liquidação."),
("Pagamento de tributo provisionado","Comprovante fictício de pagamento relacionado a obrigação fiscal já reconhecida.",["FISC-18"],"FINANCEIRO + CONTÁBIL","Se identidade e baixa forem confirmadas, liquidação baixa o passivo; não duplicar despesa/tributo."),
("Compensação tributária","Recibo fictício de declaração de compensação e débitos/créditos relacionados.",["FISC-09","FISC-18","FISC-19"],"FISCAL + CONTÁBIL","Confirmar crédito, declaração, homologação/situação e vinculação legal; saldo pode permanecer sujeito à análise."),
("Importação de mercadoria","DUIMP fictícia relaciona NCM, valor aduaneiro, tributos e despesas aduaneiras.",["FISC-17","FISC-10","FISC-11"],"FISCAL + CONTÁBIL + FINANCEIRO","Confrontar documentos aduaneiros, tributos e pagamentos; separar custo do estoque de direitos a crédito."),
("IRPJ e CSLL sobre base fiscal","Balancete fictício e memória fiscal não conciliam resultado contábil com base de cálculo.",["FISC-20","FISC-21","FISC-22"],"FISCAL + CONTÁBIL","Exigir regime, apuração, adições/exclusões e memória; não usar resultado contábil como base sem ajustes."),
("Ajuste de adição no LALUR","Memória fictícia sugere adicionar despesa, sem dispositivo ou evidência completa.",["FISC-21","FISC-23"],"FISCAL + CONTÁBIL + SUPERVISOR","Bloquear ajuste até identificar fundamento legal, competência, valor, documento e controle futuro."),
("Divergência entre receita fiscal e contábil","Totais fictícios de NFs divergem do razão por cancelamentos, adiantamentos ou corte ainda não analisados.",["FISC-03","FISC-07","FISC-25"],"FISCAL + CONTÁBIL + FINANCEIRO","Abrir conciliação por documento e competência; divergência não autoriza ajuste de eliminação automática."),
("Pagamento de imposto sem provisão identificada","Extrato fictício contém pagamento tributário, mas não há saldo correspondente localizado.",["FISC-18","FISC-25"],"FINANCEIRO + FISCAL + CONTÁBIL","Localizar guia, tributo, período e obrigação; não criar provisão retroativa ou nova despesa sem fato e decisão."),
("Operação sujeita a regra dependente da competência","Operação fictícia cruza período de transição da reforma tributária, sem data de fato confirmada.",["FISC-24","FISC-05"],"FISCAL + SUPERVISOR","Bloquear conclusão até fixar competência e regra vigente; não aplicar parâmetro futuro a período anterior.")]

cases=[]
for i,(title,fact,ids,owner,treatment) in enumerate(SPECS,1):
 src=[]; devices=[]
 for fid in ids:
  record=BY[fid]
  for s in record["FONTES"]:
   if s not in src: src.append(s)
  devices.append(record["DISPOSITIVO"])
 cases.append({"ID":f"FISC-CASO-{i:02d}","TITULO":title,"TIPO_CONHECIMENTO":"EXEMPLO_ILUSTRATIVO","FATO":fact,
 "EXEMPLO_FICTICIO":f"Exemplo fictício: sociedade fictícia Ipê apresenta documentação sobre {title.lower()}, em competência hipotética; não representa cliente nem operação real.",
 "FUNDAMENTO_IDS":ids,"FUNDAMENTO":"Consulta às fichas FISC relacionadas; cada uma distingue fonte legal de procedimento interno.","DISPOSITIVOS":devices,"FONTES":src,
 "VIGENCIA":"Consulta base em 2026-11-16; competência do caso é hipotética e deve ser definida antes de concluir a regra.","APLICABILIDADE":"Exemplo didático. Depende de empresa, competência, regime, atividade, produto/serviço, natureza, UF, município, estabelecimento e evidências.",
 "EVIDENCIA_NECESSARIA":"Documentos fiscais originais e eventos; contrato/pedido/medição/entrega; cadastros pertinentes; apuração/declaração/guia e comprovante quando houver; prova de contexto e norma vigente.",
 "TRATAMENTO_CONCEITUAL":treatment,"DEPARTAMENTO_RESPONSAVEL":owner,"RISCOS":"Tratamento fiscal indevido, crédito/retenção incorretos, duplicidade ou distorção contábil por falta de identidade, competência ou fundamento.",
 "LIMITACOES":"Não calcula tributo, escolhe código, declara crédito, conclui obrigação ou gera contabilização. Fontes locais, exceções e fatos não apresentados ficam pendentes.",
 "NECESSIDADE_APROVACAO":"SIM — validação do Fiscal e revisão do Contábil/Supervisor conforme competência e responsabilidade; pendência deve permanecer se faltar fonte/evidência.","AUTORIZA_DECISAO_AUTOMATICA":False})
json.dump({"VERSAO":"1.0.0-03E","DATA_CONSULTA":"2026-11-16","CASOS":cases},(BASE/"casos_fiscais.json").open("w",encoding="utf-8"),ensure_ascii=False,indent=2)
print("created",len(cases))
