# AGUADA - Regras e Padrões do Sistema

## 1. Visão Geral do Sistema

AGUADA é um sistema supervisório IoT para monitoramento e gestão de redes hídricas, composto por:
- **5 reservatórios** monitorados (RCON, RCAV, RB03, IE01, IE02)
- **Casa de Bombas N03** com reservatório intermediário
- **2 bombas de recalque** (B03E elétrica, B03D diesel)
- **Válvulas de controle** (entrada, saída, manobra)
- **Sensores ultrassônicos** AJ-SR04M para medição de nível
- **Nodes ESP32-C3 SuperMini** para telemetria
- **Comunicação ESP-NOW** sensor → gateway (até 250m)
- **Gateway ESP32-C3** converte ESP-NOW → MQTT
- **Backend PostgreSQL/TimescaleDB** para persistência
- **Dashboard Grafana/Web** para visualização

---

## 2. Topologia Hidráulica

### 2.1 Reservatórios Principais

#### RCON - Castelo de Consumo (CON)
- **ID**: RCON
- **Capacidade**: 80 m³ (81.7 m³ calculado)
- **Altura útil**: 400 cm
- **Diâmetro**: 510 cm
- **Sensor offset**: 40 cm (hsensor)
- **Tipo**: Cilíndrico vertical
- **Variação diária significativa** (foco principal de monitoramento)
- **Válvulas**: entrada (IE), saída AZ (Área Azul), saída AV (Área Vermelha)
- **Node**: ESP32-C3 single sensor
- **Local**: Cobertura Bloco A

#### RCAV - Castelo de Incêndio (CAV)
- **ID**: RCAV
- **Capacidade**: 80 m³ (81.7 m³ calculado)
- **Altura útil**: 400 cm
- **Diâmetro**: 510 cm
- **Sensor offset**: 20 cm (hsensor)
- **Tipo**: Cilíndrico vertical
- **Nível mínimo crítico: 70%**
- **Rede independente** com tomadas em Y
- **Uso esporádico**, esvaziamento rápido em eventos
- **Node**: ESP32-C3 single sensor
- **Local**: Cobertura Bloco B

#### RB03 - Reservatório Casa de Bombas N03
- **ID**: RB03
- **Capacidade**: 80 m³
- **Tipo**: Cilíndrico vertical (confirmar dimensões)
- **Local**: CB03 - Casa de Bombas N03
- **Função**: Armazenamento intermediário para recalque
- **Bombas associadas**:
  - **B03E**: Bomba elétrica de recalque
  - **B03D**: Bomba diesel (backup/emergência)
- **Válvulas**: entrada IE, saída CON, saída CAV, válvulas de manobra
- **Node**: ESP32-C3 single sensor
- **Abastece**: RCON (consumo) ou RCAV (incêndio)

#### IE01 e IE02 - Cisternas Ilha do Engenho
- **ID**: IE01, IE02
- **Capacidade**: 254 m³ cada (254.124 m³ calculado)
- **Altura útil**: 600 cm (útil: 240cm)
- **Comprimento**: 1040 cm
- **Largura**: 407 cm
- **Sensor offset**: 20 cm (hsensor)
- **Tipo**: Retangular (paralelepípedo)
- **Válvulas**: saída para RB03, entrada IF (Ilha da Fazenda)
- **Node**: **1 único ESP32-C3 com 2 sensores ultrassônicos** (TYPE_DUAL_ULTRA)
- **Firmware**: node_sensor_20 (monitora IE01 e IE02 simultaneamente)
- **Local**: Subsolo
- **Sensores**: 2 ultrassônicos, 4 válvulas (2 por cisterna), 2 detectores de som

---

## 3. Modelo de Dados

### 3.1 Estrutura de Elementos

Cada elemento hidráulico (reservatório, bomba, válvula) possui:

```json
{
  "id": "elemento_id",
  "tipo": "reservatorio|bomba|valvula|rede|consumidor",
  "nome": "string",
  "coordenadas": {"x": float, "y": float, "z": float},
  "estado": "ativo|inativo|alerta",
  "conexoes": {
    "entradas": ["porta_id"],
    "saidas": ["porta_id"]
  }
}
```

### 3.2 Portas e Conexões

Modelo de grafo hidráulico:

```
Elemento.porta_saida -> Conexão -> Elemento.porta_entrada
```

Exemplo:
```
res_cons.in01 = valv_conAV.out
```

Água só flui se:
- Válvulas intermediárias estão ABERTAS
- Bombas intermediárias estão ON
- Pressão é suficiente

### 3.3 Coordenadas Espaciais

Cada elemento tem coordenadas para visualização em:
- **Planta 2D** (x, y em metros ou pixels)
- **Mapa geográfico** (latitude, longitude) - opcional
- **Altitude** (z em metros)

---

## 4. Telemetria e Compressão de Dados

### 4.1 Estrutura Padronizada (JSON via ESP-NOW)

**Payload Simplificado - Envio Individual por Variável:**

```json
{
  "mac": "dc:06:75:67:6a:cc",
  "type": "nivel_cm",
  "value": 24480,
  "battery": 5000,
  "uptime": 3600,
  "rssi": -50
}
```

**Regras de Transmissão:**
- Cada variável é enviada **individualmente** quando muda
- `value` sempre como **inteiro** (ex: 244.8cm → 24480, multiplicado por 100)
- `datetime` é adicionado pelo **servidor** ao receber
- `battery` em mV (fonte DC 5V → 5000mV)
- `uptime` em segundos desde boot
- `rssi` em dBm (força do sinal ESP-NOW)

**Tipos de Dados Enviados:**

#### TYPE_SINGLE_ULTRA (node_sensor_10: RCON, RCAV, RB03)

| type | value | unit | quando enviar |
|------|-------|------|---------------|
| `distance_cm` | int (cm*100) | cm | variação > ±2cm |
| `sound_in` | 0 ou 1 | boolean | mudança de estado |
| `valve_in` | 0 ou 1 | boolean | mudança de estado |
| `valve_out` | 0 ou 1 | boolean | mudança de estado |

#### TYPE_DUAL_ULTRA (node_sensor_20: IE01 + IE02)

| type | value | unit | quando enviar |
|------|-------|------|---------------|
| `IE01_distance_cm` | int (cm*100) | cm | variação > ±2cm |
| `IE02_distance_cm` | int (cm*100) | cm | variação > ±2cm |
| `IE01_sound_in` | 0 ou 1 | boolean | mudança de estado |
| `IE02_sound_in` | 0 ou 1 | boolean | mudança de estado |
| `IE01_valve_in` | 0 ou 1 | boolean | mudança de estado |
| `IE01_valve_out` | 0 ou 1 | boolean | mudança de estado |
| `IE02_valve_in` | 0 ou 1 | boolean | mudança de estado |
| `IE02_valve_out` | 0 ou 1 | boolean | mudança de estado |

**Exemplo de Sequência de Envios:**

```json
// Distância mudou de 244.8 para 247.2 cm
{"mac":"dc:06:75:67:6a:cc","type":"distance_cm","value":24720,"battery":5000,"uptime":3600,"rssi":-50}

// Som detectado (água entrando)
{"mac":"dc:06:75:67:6a:cc","type":"sound_in","value":1,"battery":5000,"uptime":3602,"rssi":-50}

// Válvula entrada abriu
{"mac":"dc:06:75:67:6a:cc","type":"valve_in","value":1,"battery":5000,"uptime":3605,"rssi":-50}
```

**Recursos em Todos os Nodes:**

#### node_sensor_10 (TYPE_SINGLE_ULTRA)

**Firmware**: RCON, RCAV, RB03

- **1 sensor ultrassônico** (distance_cm)
- **2 válvulas** (valve_in, valve_out) - controle digital
- **1 detector de som** (sound_in) - detecta água entrando
- **RSSI** - força do sinal ESP-NOW
- **Battery** - fonte DC 5V (5000mV)
- **Uptime** - segundos desde boot

**GPIOs**: TRIG=1, ECHO=0, VALVE_IN=2, VALVE_OUT=3, SOUND=5, LED=8

#### node_sensor_20 (TYPE_DUAL_ULTRA)

**Firmware**: IE01 + IE02 (um único ESP32-C3 monitora 2 cisternas)

- **2 sensores ultrassônicos** (IE01_distance_cm, IE02_distance_cm)
- **4 válvulas** (IE01_valve_in/out, IE02_valve_in/out)
- **2 detectores de som** (IE01_sound_in, IE02_sound_in)
- **RSSI, Battery, Uptime** - compartilhados

**GPIOs**:
- IE01: TRIG=0, ECHO=1, VALVE_IN=7, VALVE_OUT=8, SOUND=5
- IE02: TRIG=2, ECHO=3, VALVE_IN=9, VALVE_OUT=10, SOUND=6
- LED=8 (compartilhado)

**Total de ESP32-C3 no sistema**: 4 microcontroladores (3 single + 1 dual)

**Mapeamento no Backend:**
- MAC address único identifica o node
- Backend mapeia MAC → reservatório(s) via tabela `node_mapping`
- Datetime timestamp adicionado pelo servidor ao receber
- Conversão: `value` int → float (divide por 100 para distance_cm)

**Nota:** Bombas B03E/B03D são **elementos independentes** não controlados por ESP32

### 4.2 Regras de Transmissão

**Protocolo de Comunicação:**
- **Sensor → Gateway**: ESP-NOW (alcance até 250m, sem necessidade de WiFi nos sensores)
- **Gateway → Backend**: MQTT over WiFi (QoS 1)
- **Fallback**: HTTP POST se MQTT falhar

**Envio Individual por Variável:**
- Cada mudança significativa gera **1 payload** individual
- Não há agregação de múltiplas variáveis no node
- Backend agrupa por MAC + timestamp para análise

**Quando Enviar:**
- **distance_cm**: variação > ±2 cm (deadband)
- **sound_in**: mudança de 0→1 ou 1→0 (água entrando)
- **valve_in / valve_out**: mudança de estado (0↔1)
- **Heartbeat**: a cada 30 segundos (envia último distance_cm mesmo sem mudança)

**Conversão de Valores:**
- `distance_cm`: float → int (multiplica por 100)
  - 244.8 cm → 24480
  - 180.5 cm → 18050
- Estados digitais: 0 (FECHADA/OFF) ou 1 (ABERTA/ON)
- `battery`: mV (fonte DC 5V = 5000mV)
- `rssi`: dBm (negativo, ex: -50)

### 4.3 Filtragem de Ruído

```cpp
// Aplicar mediana de N amostras
const int MEDIAN_SAMPLES = 11;

// Deadband para ignorar ruído
const float DEADBAND_CM = 2.0;

// Desvio padrão aceitável para "estável"
const float STABLE_STDDEV = 0.5;
```

### 4.4 Compressão no Banco

#### Tabela leituras_raw
- Armazena TODAS as leituras recebidas
- Índices: (sensor_id, datetime), (processed)
- Retention: 180 dias

#### Tabela leituras_processadas
- Armazena APENAS mudanças significativas
- Atualiza `data_fim` enquanto valor permanece estável
- Cria novo registro quando valor muda além do deadband

**Algoritmo:**
```python
if abs(valor_atual - valor_anterior) <= DEADBAND:
    UPDATE leituras_processadas SET data_fim = now()
else:
    INSERT INTO leituras_processadas (...)
```

---

## 5. Cálculos Físicos

### 5.1 Volume a partir do Nível

#### Reservatório Cilíndrico
```python
raio_m = diametro_cm / 200.0
volume_m3 = π * raio_m² * (nivel_cm / 100.0)
percentual = (volume_m3 / volume_max_m3) * 100
```

#### Reservatório Retangular
```python
volume_m3 = (comprimento_m * largura_m * nivel_cm) / 100.0
percentual = (volume_m3 / volume_max_m3) * 100
```

### 5.2 Pressão Estática

```python
# No fundo do reservatório
P_Pa = ρ * g * h
P_bar = P_Pa / 100000

# ρ água = 1000 kg/m³
# g = 9.81 m/s²
```

### 5.3 Vazão Estimada

```python
# Simplificado (orifício)
Q_m3s = C * sqrt(ΔP)

# Perda de carga
ΔP_loss = K_loss * Q
```

---

## 6. Detecção de Eventos

### 6.1 Abastecimento

**Condições:**
- ΔVolume > +50 L
- Bomba = ON
- Válvula entrada = ABERTA
- Duração > 5 minutos

**Ação:**
```sql
INSERT INTO eventos (tipo, reservatorio_id, volume_estimado_l, ...)
VALUES ('ABASTECIMENTO', 'res_cons', 520, ...)
```

### 6.2 Consumo

**Condições:**
- ΔVolume < 0 (queda gradual)
- Válvula saída = ABERTA
- Bomba consumo = ON (se aplicável)

**Métricas:**
```python
consumo_diario_L = sum(volumes_negativos) over 24h
consumo_por_periodo = consumo[00-06h, 06-12h, 12-18h, 18-24h]
```

### 6.3 Vazamento

**Condições:**
- Queda lenta e contínua > 1 hora
- Taxa: -15 L/h ou mais
- Todas válvulas saída = FECHADAS
- Bombas = OFF

**Ação:**
```sql
INSERT INTO anomalias (tipo, nivel_alerta, descricao, ...)
VALUES ('VAZAMENTO_SUSPEITO', 'MODERADO', 'queda 18L/h', ...)
```

### 6.4 Rede de Incêndio Crítica

**Condições:**
- Nível CAV < 70%
- Duração > 10 minutos

**Ação:**
- Alerta sonoro
- Notificação imediata
- Registro em eventos críticos

### 6.5 Falha de Sensor

**Condições:**
- Leitura travada (mesmo valor por > 1h)
- Valor fora de faixa física (< 0 ou > altura_max)
- Jitter > 3x desvio padrão normal
- Timeout de comunicação > 5 minutos

---

## 7. Auditoria e Rastreabilidade

### 7.1 Campos Obrigatórios

Toda leitura/modificação deve registrar:

```json
{
  "fonte": "sensor|usuario|sistema",
  "autor": "node_id | usuario_nome | processo",
  "datetime": "ISO8601 timestamp",
  "modo": "automatica|manual"
}
```

### 7.2 Leituras Manuais

Hidrômetros e conferências:

```sql
INSERT INTO leituras_raw (
  sensor_id, ativo_id, variavel, valor,
  fonte, autor, modo, observacao, datetime
) VALUES (
  'manual_001', 'res_cons', 'nivel_cm', 347,
  'usuario', 'luciano', 'manual', 
  'Conferência com régua', '2025-11-16T09:30:00'
)
```

### 7.3 Calibração

```sql
INSERT INTO calibracoes (
  sensor_id, valor_referencia, valor_sensor,
  ajuste_aplicado, responsavel_usuario_id
) VALUES (
  'SEN001', 347, 345, '+2cm', 1
)
```

---

## 8. Relatório Diário 06:00

### 8.1 Geração Automática

Cron job executa às 06:00 todos os dias:

```sql
INSERT INTO relatorio_diario (
  data, 
  volume_consumido_total_l,
  volume_abastecido_total_l,
  eventos_registrados,
  anomalias_detectadas,
  resumo
) SELECT ...
```

### 8.2 Conteúdo do Relatório

1. **Resumo de Volumes**
   - Volume inicial e final de cada reservatório
   - Consumo total do dia
   - Abastecimentos realizados

2. **Eventos Significativos**
   - Abastecimentos (horário, duração, volume)
   - Consumos anormais
   - Vazamentos detectados

3. **Status de Equipamentos**
   - Horas de operação de bombas
   - Ciclos de válvulas
   - Falhas ou alertas

4. **Métricas por Período**
   - Consumo 00-06h (residual)
   - Consumo 06-12h (pico matutino)
   - Consumo 12-18h (operacional)
   - Consumo 18-24h (redução)

5. **Alertas e Ações**
   - Anomalias em investigação
   - Recomendações de manutenção

---

## 9. Padrões de Código

### 9.1 Firmware (ESP32)

```cpp
// Configuração em JSON (SPIFFS/LittleFS)
// Cálculo de volume no node
// Transmissão lean (mudança > threshold)
// Buffer local para resiliência
// MQTT QoS 1 como padrão
```

### 9.2 Backend (Node.js/Python)

```javascript
// Validação rigorosa de payloads
// Pipeline: ingestão -> validação -> processamento -> eventos
// Funções puras para cálculos
// Logging estruturado (JSON)
// Testes unitários para regras de detecção
```

### 9.3 Database (PostgreSQL/TimescaleDB)

```sql
-- Hypertables para séries temporais
-- Índices em (elemento_id, datetime)
-- Triggers para compressão automática
-- Functions PL/pgSQL para eventos
-- Particionamento por tempo (se necessário)
```

---

## 10. Segurança e Confiabilidade

### 10.1 Comunicação

- MQTT com autenticação
- TLS/SSL em produção
- MAC address como identificador único
- Validação de checksum (opcional)

### 10.2 Persistência

- Backup diário automático
- Retenção configurable (raw: 180d, processadas: 2 anos)
- Reprocessamento possível (leituras_raw preservadas)

### 10.3 Resiliência

- Buffer local nos nodes (até 100 leituras)
- Fallback HTTP se MQTT falhar
- Reconexão automática com backoff exponencial
- Watchdog timer nos firmwares

---

## 11. Visualização e Interface

### 11.1 Dashboard Principal

- 6 cards de reservatórios (%, m³, tendência)
- Status de bombas e válvulas em tempo real
- Timeline de eventos do dia
- Alertas destacados (vermelho/amarelo/verde)

### 11.2 Planta Hidráulica

- Visualização com coordenadas x,y
- Cores por status (verde=OK, amarelo=alerta, vermelho=crítico)
- Linhas de conexão mostrando fluxo
- Click nos elementos para detalhes

### 11.3 Histórico

- Gráficos de 24h, 7d, 30d
- Comparação entre reservatórios
- Curvas de consumo por período
- Exportação de relatórios (PDF/CSV)

---

## 12. Próximas Evoluções

1. **Simulador hidráulico** (previsão de comportamento)
2. **IA para detecção preditiva** (vazamentos antes de se tornarem críticos)
3. **Controle automático** (ligar bombas conforme nível)
4. **Integração com sistema elétrico** (eficiência energética)
5. **App mobile** para operadores

---

## 13. Referências

- ESP32-C3 Datasheet
- AJ-SR04M Ultrasonic Sensor Spec
- PostgreSQL TimescaleDB Documentation
- MQTT 3.1.1 Protocol Specification
- Hidráulica básica (Bernoulli, perda de carga)

---

**Versão:** 1.0  
**Data:** 2025-11-16  
**Autor:** Luciano / Sistema AGUADA  
**Licença:** Uso interno
