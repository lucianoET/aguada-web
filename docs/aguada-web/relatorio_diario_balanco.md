# Relatório Diário de Balanço Hídrico

## Objetivo

Consolidar, por data, o comportamento de consumo/abastecimento de cada reservatório para apoiar a detecção de anomalias operacionais e vazamentos.

## Conceito

\[\text{Balanço} = \text{Volume final} - \text{Volume inicial}\]

- Balanço > 0: entrada (abastecimento)
- Balanço < 0: saída (consumo)

## Critérios de alerta sugeridos

- **NORMAL**: consumo até 20% acima da média histórica
- **ALERTA**: consumo entre 20% e 50% acima da média
- **CRÍTICO**: consumo acima de 50% da média

## Fonte de dados

- Leituras históricas por reservatório
- Eventos de consumo e abastecimento derivados de delta de volume
- Resumo diário disponível em `/api/report/daily`

