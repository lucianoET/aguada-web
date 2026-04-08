# Proposta Técnica - AGUADA2 (Offline, Leve, Simples)

## 1) Diretriz principal

Refazer o sistema em nova pasta `aguada2` mantendo os nomes e funcionalidades essenciais do Aguada atual, com foco em:

- operação local sem internet;
- desempenho e simplicidade de uso;
- conformidade normativa;
- auditabilidade operacional.

## 2) Arquitetura recomendada

### Camadas

1. **Ingestão**: endpoints compatíveis com gateway/nodes (`api_gateway_v3`/`ingest_nano` equivalentes)
2. **Domínio**: cálculos de nível/volume, regras NBR 5626, alarmes, detecções
3. **Persistência**: MySQL com tabelas normalizadas + visões de leitura
4. **Apresentação**: páginas web responsivas Tailwind local

### Offline obrigatório

- Sem `cdn.tailwindcss.com`, `unpkg`, `jsdelivr` em runtime.
- Bibliotecas entregues localmente (`public/assets/vendor`).
- Mapa com tiles locais/cache local ou fallback em imagem georreferenciada.

## 3) Módulos do sistema (MVP)

1. **Dashboard Geral**
   - volumes, percentuais, status de reservatórios
   - status de bombas, válvulas, hidrômetros
   - alarmes ativos e últimos eventos

2. **Mapa Operacional (MAP 4)**
   - elementos no mapa: reservatórios, bombas, válvulas, hidrômetros, ETE
   - popups com estado e última atualização
   - sobreposição de rede hidráulica operacional

3. **Consumo e Abastecimento**
   - relatórios diários
   - séries históricas
   - médias históricas e comparação por período

4. **Detecção de Anomalias**
   - vazamento provável (balanço reservatório vs hidrômetros)
   - consumo elevado (desvio da média e thresholds)
   - falha de sensor/sem leitura

5. **Qualidade da Água e ETE**
   - registro de laudos e conformidade
   - histórico de não conformidades
   - status operacional da ETE

6. **Manutenções**
   - preventiva/corretiva por elemento
   - calendário e pendências
   - histórico auditável

## 4) Regras normativas incorporadas

Baseado em `docs/Normas_Tecnicas.md`:

- Nível calculado com offset e saturação em faixa física
- Bloqueio automático de recalque abaixo do mínimo operacional (NBR 5626)
- Histerese de alarmes para evitar oscilação
- trilha de auditoria para comando manual/override (usuário, motivo, timestamp)
- armazenamento UTC e exibição local

## 5) UX alvo (simples e leve)

- Layout único com sidebar + topbar
- páginas com densidade baixa de informação por tela
- padrões visuais consistentes para estados (normal, atenção, crítico, offline)
- filtros mínimos: período, local, tipo de elemento

## 6) Estratégia de migração

Fase 1 (fundação):
- schema novo + importadores + APIs de leitura

Fase 2 (operação):
- dashboard, mapa, estados operacionais, alarmes

Fase 3 (gestão):
- relatórios, consumo/abastecimento, qualidade, manutenção

Fase 4 (hardening):
- performance, backup/restore, testes e homologação

## 7) Tecnologias opcionais (se desejar evoluir)

- **Vue 3** para frontend SPA (mais interatividade)
- **Python/FastAPI** para motor analítico (anomalias e previsões)
- **Docker Compose** para padronizar ambiente local

Para MVP leve e rápido, manter PHP + MySQL + JS local é o caminho de menor risco.
