# Normas Técnicas – Sistema Supervisório de Abastecimento de Água

**Data:** Fevereiro 2026  
**Escopo:** Sistema web supervisório para monitoramento e gerenciamento de sistema hidráulico com sensores ultrassom em reservatórios, entradas manuais de hidrômetros/bombas/válvulas e laudos de qualidade da água.

---

## 1. Normas Técnicas Aplicáveis

### 1.1 Normas ABNT – Projeto e Operação

| Norma | Título | Aplicação ao Sistema |
|-------|--------|----------------------|
| **NBR 12217** | Projeto de reservatório de distribuição de água para abastecimento público | Definição de volumes operacionais, níveis, segurança operacional |
| **NBR 12218** | Projeto de rede de distribuição de água | Pontos de coleta, pressões, ligação com controle de bombas |
| **NBR 12211** | Estudos de concepção de sistemas públicos de abastecimento | Visão sistêmica de projeto |
| **NBR 12214** | Projeto de estação elevatória de água | Automação de bombas, setpoints, desvios |
| **NBR 12215** | Projeto de adutora de água | Tubulações principais, válvulas de retenção |
| **NBR 5626** | Instalações prediais de água fria | **CRÍTICA:** Comandos de recalque, níveis mínimos, bloqueios de operação |

### 1.2 Normas de Gestão e Indicadores

| Norma | Título | Aplicação |
|-------|--------|-----------|
| **NBR ISO 24510** | Diretrizes para avaliação de serviços de água | Indicadores operacionais, KPIs, dashboards |
| **NBR ISO 24511** | Gestão de serviços de água e esgoto | Procedimentos operacionais |
| **NBR ISO 24512** | Estrutura de avaliação de desempenho | Métricas de conformidade |

### 1.3 Normas Sanitárias e Legais

| Norma | Título | Aplicação |
|-------|--------|-----------|
| **Portaria GM/MS nº 2.914/2011** | Padrões de potabilidade da água para consumo humano | Limites normalizados para parâmetros, laudos, conformidade |

> **Atenção:** Verificar atualizações/consolidações da Portaria conforme vigência legal na data do projeto.

---

## 2. NBR 12217 – Fundamentos para Supervisão (Resumo Executivo)

### 2.1 Objetivo e Escopo

Estabelecer critérios para dimensionamento e operação de reservatórios de distribuição que garantam:
- Continuidade do abastecimento
- Segurança hidráulica
- Confiabilidade operacional

Embora seja norma de **projeto**, seus conceitos impactam diretamente **operação**, **monitoramento** e **automação**.

### 2.2 Definições Críticas para o Sistema

| Termo | Definição | Impacto no Software |
|-------|-----------|---------------------|
| **Reservatório de distribuição** | Estrutura que armazena água e fornece à rede | Ponto central de monitoramento |
| **Volume útil/operacional** | Volume utilizável sem compromisso operacional | Define nível máximo operacional |
| **Reserva de emergência** | Volume extra para falhas/picos | Dispara alarmes de falta | 
| **Nível mínimo operacional** | Limite inferior para operação segura | **Bloqueia recalque automaticamente (NBR 5626)** |
| **Nível máximo operacional** | Limite superior antes de transbordo | Para bomba normalmente |
| **Sensor offset** | Distância sensor → nível máximo projeto | Parâmetro crítico de calibração |

---

## 3. Medição de Nível – Sensor Ultrassônico (NBR 12217 + Boas Práticas)

### 3.1 Princípio Físico

O sensor ultrassônico mede a distância entre o transdutor (no topo) e a superfície da água.

### 3.2 Fórmula de Cálculo

```
nivel_m = altura_total_m - (distancia_medida_m - sensor_offset_m)

Aplicar saturação: 0 ≤ nivel_m ≤ altura_total_m
```

### 3.3 Parâmetros Obrigatórios no Banco

- `altura_total_m` – altura total do reservatório
- `sensor_offset_m` – distância entre transdutor e nível máximo
- `distancia_medida_m` – leitura bruta do sensor (a cada leitura)
- `status_sensor` – ok | falha | eco_perdido | fora_faixa

### 3.4 Qualidade de Medição – Filtragem e Estabilidade

**Problema:** respingos, ondas, reflexos falsos  
**Solução:**

- Média móvel (5–15 amostras) OU mediana robusta
- Histerese de alarme (evita oscilação de estado)
- Detecção de leitura inválida (timeout, valor negativo, salto abrupto > 0,5 m em 5 min)

**Exemplo de histerese:**
```
Alarme "Nível Baixo":
  Dispara: nivel < 2,00 m
  Normaliza: nivel > 2,20 m (não volta imediatamente)
```

---

## 4. Conversão Nível → Volume (Exemplos Práticos)

### 4.1 Cilindro Vertical (Caso Mais Comum)

**Dados de exemplo:**
- Raio = 5,0 m
- Altura útil = 12,0 m
- Nível medido = 7,5 m

**Cálculo:**
```
Área base = π × r² = 3,1416 × 25,0 = 78,54 m²
Volume = 78,54 × 7,5 = 589,05 m³
```

### 4.2 Reservatório Prismático (Base Retangular)

```
Volume = área_base × nivel
```

### 4.3 Geometrias Complexas

Usar tabela nível vs. volume (calibrada em campo com medições reais).

### 4.4 Recomendação de Implementação

- Criar função por tipo geométrico no código
- Armazenar **tanto** nível quanto volume (para auditoria normativa)
- Nunca hardcode volume máximo sem vínculo com geometria real

---

## 5. Níveis Operacionais e Regras de Controle (NBR 5626)

### 5.1 Hierarquia de Níveis

| Nível | Ação | Justificativa |
|-------|------|---------------|
| **Nivel máximo** | Alarme de transbordo | Evita perdas/danos |
| **Nível máximo operacional** | Para bomba (modo automático) | Economia de energia |
| **Nível mínimo operacional** | **BLOQUEIA RECALQUE** (NBR 5626) | Evita cavitação / funcionamento a seco |
| **Nível mínimo absoluto** | Alarme crítico | Falha grave |

### 5.2 Regra Ouro de Segurança

> **Nunca permitir acionamento automático de bomba abaixo do nível mínimo operacional.**

Implementação:
- Lógica no PLC/RTU: bloqueio automático
- Sistema supervisório: indicar bloqueio visual + notificação
- Override manual: exigir usuário autenticado + justificativa + timestamp

---

## 6. Bombas e Automação (NBR 5626 + NBR 12214)

### 6.1 Estados Obrigatórios

```sql
estado_bomba: ligada | desligada | falha | manutencao
modo_operacao: automatico | manual
```

### 6.2 Lógica Mínima de Partida/Parada

```
SE modo = automatico ENTÃO:
  SE nivel < nivel_minimo_operacional ENTÃO
    bomba = desligada (bloqueio)
  SENÃO SE nivel < nivel_minimo_setpoint ENTÃO
    bomba = desligada
  SENÃO SE nivel > nivel_maximo_setpoint ENTÃO
    bomba = desligada
  SENÃO SE nivel >= nivel_minimo_setpoint E modo = manterAbaixoMaximo ENTÃO
    bomba = ligada
SENÃO
  operador controla manualmente (com registro)
```

### 6.3 Registro Obrigatório

Toda ação de bomba (automática ou manual) deve registrar:
- **timestamp** (ISO 8601 UTC)
- **estado_anterior** e **estado_novo**
- **usuario_id** (se manual)
- **motivo** (se manual)
- **nome_do_comando** (se automático)

---

## 7. Válvulas de Isolamento e Retenção

### 7.1 Estados Obrigatórios

```sql
estado_valvula: aberta | fechada | parcial | falha
```

### 7.2 Operação

- Espera-se que sejam comandadas manualmente ou por lógica automática (less common)
- Mudanças de estado devem ser auditadas igual às bombas
- Válvulas de retenção devem ter monitoramento de integridade (indicador visual de fluxo reverso)

---

## 8. Entradas Manuais – Hidrômetros (NBR 12218 + Boas Práticas)

### 8.1 Estrutura de Dados Mínima

```sql
hidrometro:
  - id (identificação única)
  - localizacao (ponto na rede)

leitura_hidrometro:
  - hidrometro_id
  - timestamp (ISO 8601)
  - leitura_m3 (valor acumulativo)
  - usuario_id (quem coletou)
  - origem (manual | importacao)
```

### 8.2 Validação

- Aceitar apenas leituras **incrementais** (maior ou igual à anterior)
- Indicar **discrepância** se volume calculado dos reservatórios ≠ volume medido em hidrômetros
- Permitir anotação de motivo de discrepância (vazamento, calibração, etc.)

### 8.3 Conciliação (KPI ISO 24510)

Implementar rotina diária que compara:
```
Volume distribuído (reservatórios) - Volume medido (hidrômetros) = Perdas aparentes
```

---

## 9. Laudos de Qualidade da Água (Portaria GM/MS nº 2.914/2011)

### 9.1 Estrutura Obrigatória

```sql
ponto_coleta:
  - id
  - nome (local específico da rede/reservatório)
  - reservatorio_id (referência)

laudo_agua:
  - ponto_coleta_id
  - data_coleta (ISO 8601)
  - parametro (pH, cloro, turbidez, etc.)
  - valor (número)
  - unidade (mg/L, etc.)
  - limite_normativo (conforme Portaria)
  - conforme (boolean: valor ≤ limite)
  - arquivo_pdf (pdf do laudo original)
  - criado_em (timestamp de importação)
```

### 9.2 Requisitos de Auditoria

- Cada laudo deve ser **rastreável** até: quem importou, quando, de qual laboratório
- Histórico completo de **não conformidades**
- Dashboard mostrar: "Últimas 5 coletas para ponto X: 4 OK, 1 NÃO CONFORME"

---

## 10. Alarmes e Eventos (Auditável)

### 10.1 Tipos de Evento

```sql
tipo_evento: alarme | comando | falha | informativo
```

### 10.2 Campos Obrigatórios

```sql
evento:
  - id
  - tipo (alarme, comando, falha, etc.)
  - entidade (reservatorio, bomba, valvula, sensor)
  - entidade_id (qual reservatório/bomba/etc.)
  - descricao (em linguagem clara)
  - usuario_id (quem originou, se aplicável)
  - ts_utc (timestamp ISO 8601)
  - reconhecido (boolean)
  - reconhecido_em (timestamp quando operador viu)
```

### 10.3 Alarmes Recomendados (Mínimo)

| Alarme | Condição | Ação |
|--------|----------|------|
| **Nível baixo crítico** | nivel < min_operacional | Bloqueia bomba + notificação |
| **Nível alto** | nivel > max_operacional | Para bomba + alerta |
| **Falha de sensor** | status ≠ ok por > 5 min | Alarme crítico |
| **Bomba não liga** | comando automático recusado (falha) | Alarme de manutenção |
| **Laudo não conforme** | parametro > limite_normativo | Alerta sanitário |
| **Hidrômetro inconsistente** | discrepância > X% | Alerta operacional |

---

## 11. Indicadores Operacionais (NBR ISO 24510)

Métricas recomendadas para dashboards e relatórios gerenciais:

| KPI | Fórmula/Método | Frequência |
|-----|---|---|
| **Disponibilidade** | (horas_acima_min / horas_totais) × 100% | Diário/mensal |
| **Acionamentos de bomba** | COUNT(eventos.tipo='comando' AND entidade='bomba') | Diário |
| **Consumo conciliado** | SUM(hidrometros) vs. Δ(reservatorios) | Diário |
| **Não conformidades de água** | COUNT(laudos.conforme=false) | Mensal |
| **Eventos de alarme** | COUNT(eventos.tipo='alarme') | Diário |
| **Intervenções manuais** | COUNT(eventos.usuario_id IS NOT NULL) | Diário |

---

## 12. Requisitos Não Funcionais Derivados das Normas

### 12.1 Rastreabilidade
- Logs imutáveis (insert-only, jamais update/delete de eventos históricos)
- Backup de eventos a cada 24h

### 12.2 Auditoria
- Quem? (`usuario_id`)
- Quando? (`timestamp` UTC)
- O quê? (`descricao`, `estado_anterior`, `estado_novo`)
- Por quê? (`motivo` para overrides)

### 12.3 Confiabilidade
- Detecção automática de falha de sensor (timeout, valor inválido)
- Fallback gracioso: manter último estado conhecido, notificar operador
- Sem continuação de comando automático com sensor falhando

### 12.4 Segurança
- Autenticação forte para comandos críticos (bomba, válvula)
- Autorização por role (operador, supervisor, admin)
- Criptografia de comunicação (HTTPS/TLS)

### 12.5 Temporalidade
- Todos os timestamps em **UTC** (armazenamento)
- Exibição em **timezone local** (America/Sao_Paulo no caso de Marinha/Rio)
- Nunca confiar em clock do cliente (validar no servidor)

---

## 13. Próximas Entregas Técnicas

Este documento estabelece base normativa para:

1. ✅ **Modelagem de dados** (schema SQL) → `database/schema_normas_aguada.sql`
2. ✅ **Regras de negócio** → Alarmes, níveis, bloqueios
3. ✅ **APIs** → Endpoints de leitura/comando com auditoria
4. ✅ **Dashboards** → KPIs ISO 24510, alertas visuais
5. ✅ **Comissionamento** → Calibração ultrassom, testes de campo

---

## Referências Normativas

1. ABNT NBR 12217:1994 – Projeto de reservatório de distribuição
2. ABNT NBR 5626:2020 – Instalações prediais de água fria
3. ABNT NBR 12214:1992 – Projeto de estação elevatória
4. ABNT NBR ISO 24510:2010 – Serviços de água e esgoto
5. Portaria GM/MS nº 2.914/2011 – Potabilidade da água

---

**Versão:** 1.0  
**Data:** Fevereiro 2026  
**Status:** Base normativa para desenvolvimento de sistema supervisório
