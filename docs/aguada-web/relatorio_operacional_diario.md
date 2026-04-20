# Relatório Operacional Diário

## Objetivo

Consolidar por data a operação hídrica do dia, com dados persistidos no banco e exportação em PDF pelo backend.

## Escopo atual

O relatório ativo da release é a página `relatorio_tabelas.html` e seu PDF correspondente em `/api/report/daily.pdf`.

Ele reúne:

- volumes dos reservatórios por checkpoints do dia
- resumo de hidrômetros manuais
- matriz operacional de válvulas
- matriz operacional de bombas
- observações persistidas por data
- campos de assinatura para `Eletricista` e `OSE`

## Persistência

- Os dados editados do relatório são salvos em `report_daily_data`
- As observações são salvas separadamente e vinculadas à data
- O PDF é sempre regenerado a partir do estado persistido mais recente

## Regras operacionais

- a data selecionada define todo o contexto do relatório
- checkpoints futuros no dia corrente permanecem em branco
- o botão `Gerar PDF` salva antes de abrir o arquivo final
- o backend desabilita cache HTTP para evitar abertura de PDF antigo

## Saída PDF

O PDF gerado contém:

- título `Relatorio Aguada`
- subtítulo `CMASM, dd/mm/aaaa`
- tabela de reservatórios
- tabela de hidrômetros
- válvulas e bombas lado a lado
- observações
- bloco final de assinaturas de `Eletricista` e `OSE`