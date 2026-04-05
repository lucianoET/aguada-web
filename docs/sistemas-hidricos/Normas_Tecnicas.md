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

- Média móvel (5–15 amostras) OU mediana robusta
- Histerese de alarme (evita oscilação de estado)
- Detecção de leitura inválida (timeout, valor negativo, salto abrupto > 0,5 m em 5 min)

---

## 4. Conversão Nível → Volume (Resumo)

- Cilindro vertical: \(V = \pi r^2 h\)
- Prismático: \(V = A_{base} \cdot h\)
- Geometrias complexas: usar tabela de calibração nível × volume

Recomendação: armazenar nível e volume para auditoria normativa.

---

## 5. Níveis Operacionais e Regras de Controle (NBR 5626)

### Regra de Segurança

> **Nunca permitir acionamento automático de bomba abaixo do nível mínimo operacional.**

Aplicar bloqueio de recalque, alarme e trilha de auditoria.

---

## 6. Alarmes e Indicadores

Alarmes mínimos:
- Nível baixo crítico
- Nível alto
- Falha de sensor
- Bomba não liga
- Laudo não conforme
- Hidrômetro inconsistente

KPIs recomendados:
- Disponibilidade
- Acionamentos de bomba
- Consumo conciliado
- Não conformidades
- Eventos de alarme
- Intervenções manuais

---

## Referências

1. ABNT NBR 12217:1994
2. ABNT NBR 5626:2020
3. ABNT NBR 12214:1992
4. ABNT NBR ISO 24510:2010
5. Portaria GM/MS nº 2.914/2011

---

**Versão:** 1.0  
**Data:** Fevereiro 2026  
**Status:** Base normativa para desenvolvimento de sistema supervisório
