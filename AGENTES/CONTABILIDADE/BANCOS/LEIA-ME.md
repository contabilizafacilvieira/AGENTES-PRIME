# CONTABILIDADE · ESPECIALISTA BANCOS

Status: **IMPLEMENTADO EM SIMULAÇÃO** (31/10/2026): empresa fictícia e piloto real autorizado em SIMULAÇÃO. Conferência humana obrigatória.

- Área: Contabilidade (lançamentos). Especialistas internos: Importação VGROW (pausada) e Bancos; Impostos, Folha e
  Notas de entrada/saída ainda não existem.
- Papel: preparar os lançamentos bancários a partir da conferência do Financeiro, com o plano de contas e as regras
  aprovadas da empresa (`PROCEDIMENTO.md`).
- Execução: código local determinístico (`ferramentas/lancamentos_bancarios.py`), **sem chamar o Claude**.
- Acionado SOMENTE pelo Coordenador, depois do Financeiro. Resultado volta ao Coordenador → Supervisor.
- Bancos não libera nada: o TXT do Domínio é gerado depois, pela API, só após a aprovação do fechamento integral e só para empresa
  fictícia (`API-LOCAL/exportacao_dominio.py`). Nada é importado no Domínio pelo sistema.
- Cada lançamento leva a identidade do fato (`BANCO:<movimento(s)>`), usada para impedir repetição entre solicitações.
- Regras: só VALIDADA com confirmação estruturada na coluna Aprovação
  (`CONFIRMADA; frase=VALIDADO REGRA <EMPRESA> <RB-NNN>; versao=<n>; por=Supervisor Contábil; em=<data-hora>`), igual à versão da
  linha, ou TESTE_FICTICIO em empresa fictícia (marcador AMOSTRA-FICTICIA.json). Texto livre ou o formato antigo (sem versão e
  responsável) não é aplicado e aparece para reconfirmação em Empresas → Definições necessárias.

## Limitações conhecidas
- TXT do Domínio em partida simples (decisão de 04/11/2026), ainda não validado no Domínio; a proposta também sai em CSV.
- Regras por condições exatas (sem tolerância); classificação de créditos (recebimentos) depende de regra aprovada.
- Duplicidade dentro da SOL: o mesmo movimento em dois lançamentos é divergência. Entre SOLs: propostas em SIMULAÇÃO aparecem
  como revisões; fato já APROVADO em outra SOL bloqueia a aprovação (Coordenador). Escrituração efetiva não existe nesta versão.
