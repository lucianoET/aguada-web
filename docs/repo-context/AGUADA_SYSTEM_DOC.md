# AGUADA — Sistema de Telemetria de Reservatórios v3.2

ESP32 + ESP-NOW. Sem WiFi nos nodes. Sem infraestrutura em campo.

---

## 1. Visão Geral

```
[Nodes ESP32-C3]  ←── firmware único ──►  [comportamento por NVS]
  mede distance_cm, filtra, transmite     (ou num_sensors=0 → relay)

  ESP-NOW canal 1, sem WiFi
       │
       ▼
[Gateway ESP32-S3]  ──USB Serial──►  [Servidor Linux]
                                          bridge.py
                                          │ MQTT
                                     Home Assistant
                                     InfluxDB / Grafana
```

**Princípios de design:**
| Decisão | Escolha | Motivo |
|---------|---------|--------|
| Firmware | Único para todos os nodes | `num_sensors=0` → relay automático |
| Node ID | 2 últimos bytes do MAC | Único por hardware, sem cadastro |
| Node transmite | Apenas `distance_cm` | Simples, robusto, parâmetros mudam sem reflash |
| Cálculos | No servidor (bridge.py) | Fácil corrigir offset/volume sem tocar node |
| Unidade sensor | cm (precisão real do HC-SR04) | Não fingir precisão que não existe |
| Filtro | Outlier reject + média móvel 5 + threshold 2cm | Filtra oscilação sem suprimir mudanças reais |

---

## 2. Modelo: Sensor = Reservatório

Cada par `(node_id, sensor_id)` = um reservatório único com seu próprio alias e parâmetros.

```
NODE-03  node_id=0x2EC4
  ├── sensor_id=1  alias="CB31"  →  Casa de Bombas Nº3 - Tanque 1
  └── sensor_id=2  alias="CB32"  →  Casa de Bombas Nº3 - Tanque 2

NODE-01  node_id=0x7758
  └── sensor_id=1  alias="CON"   →  Castelo de Consumo
```

---

## 3. Inventário — CMASM (Ilha do Engenho)

| node_id | MAC (fim) | alias(es) | Reservatório | level_max_cm | volume_max_L | sensor_offset_cm | n_sensors |
|---------|-----------|-----------|-------------|-------------|-------------|-----------------|----------|
| 0x7758 | `6B:77:58` | CON | Castelo de Consumo | 450 | 80000 | 20 | 1 |
| 0xEE02 | `DD:EE:02` | CAV | Castelo de Incêndio | 450 | 80000 | 20 | 1 |
| 0x2EC4 | `50:2E:C4` | CB31 / CB32 | Casa de Bombas Nº3 | 200 / 200 | 40000 / 40000 | 10 / 10 | 2 |
| 0x9EAC | `8B:9E:AC` | CIE1 / CIE2 | Cisterna IE | 200 / 200 | 245000 / 245000 | 10 / 10 | 2 |
| 0x3456 | `12:34:56` | CBIF1 / CBIF2 | Casa de Bombas IF | 200 / 200 | 40000 / 40000 | 10 / 10 | 2 |

**Gateway:** ESP32-S3 — MAC `24:D7:EB:5B:2E:74`

> Parâmetros (`level_max_cm`, `volume_max_L`, `sensor_offset_cm`) vivem no servidor (bridge.py / HA).
> Nodes **não precisam** dessas informações.

---

## 4. Hardware

### Node — ESP32-C3 SuperMini

Pinos configuráveis via NVS. Defaults:

```
sensor_id=1:  GPIO1→TRIG   GPIO0→ECHO
sensor_id=2:  GPIO3→TRIG   GPIO2→ECHO
GPIO8 → LED builtin (active-low)
```

### Gateway — ESP32-S3
```
USB Serial 115200bps → servidor
Canal ESP-NOW: 1 (fixo)
```

---

## 5. Configuração NVS do Node

O node **não armazena parâmetros de reservatório** — apenas identidade, pinos e temporização.

```c
// config/node_config.h

typedef struct {
    uint8_t  trig_pin;
    uint8_t  echo_pin;
    bool     enabled;
} sensor_hw_t;

typedef struct {
    uint16_t   node_id;              // 2 bytes do MAC
    uint8_t    num_sensors;          // 0=relay, 1 ou 2
    sensor_hw_t sensor[2];           // [0]=sensor_id1, [1]=sensor_id2

    // Temporização
    uint16_t interval_measure_s;     // default: 30
    uint16_t interval_send_s;        // default: 120
    uint16_t heartbeat_s;            // default: 60

    // Filtros
    uint8_t  filter_window;          // média móvel, default: 5
    uint8_t  filter_outlier_cm;      // rejeita se delta > N cm, default: 10
    uint8_t  filter_threshold_cm;    // threshold de envio, default: 2

    // Features opcionais
    bool     vbat_enabled;
    uint8_t  vbat_pin;
    bool     deep_sleep_enabled;     // incompatível com relay
    bool     led_enabled;

    // Rede
    uint8_t  espnow_channel;         // default: 1
    uint8_t  ttl_max;                // default: 8

    // Manutenção
    uint8_t  restart_daily_h;        // 0=desabilitado
    char     fw_version[8];
} node_config_t;
```

### Boot

```
boot → ler NVS
  num_sensors == 0  →  modo RELAY  (só mesh, sem sensores)
  num_sensors >= 1  →  modo SENSOR (inicializa drivers nos pinos configurados)
```

---

## 6. Filtro de Leitura (no Node)

HC-SR04 tem precisão real de **±1cm**. Superfície de água oscila. Filtro em 3 camadas:

```
a cada interval_measure_s:

  raw = hcsr04_read_cm(trig, echo)      // leitura bruta

  [1] REJEIÇÃO DE OUTLIER
      se raw == 0 ou raw > MAX_RANGE:
          raw = INVALID  → não entra no buffer
      se |raw - moving_avg_current| > filter_outlier_cm (10cm):
          raw = INVALID  → eco falso, descarta

  [2] MÉDIA MÓVEL (janela = filter_window = 5)
      buffer[i % 5] = raw
      avg_cm = mean(buffer)              // inteiro, arredondado

  [3] THRESHOLD DE ENVIO
      se |avg_cm - last_sent_cm| >= filter_threshold_cm (2cm):
          enviar SENSOR agora
          last_sent_cm = avg_cm
      senão se elapsed >= interval_send_s:
          enviar SENSOR  (envio forçado periódico)
      senão se elapsed >= heartbeat_s:
          enviar HEARTBEAT
```

**Por que threshold=2cm e não 1cm:**  
Com precisão de ±1cm, um threshold de 1cm geraria envio contínuo por ruído.  
2cm garante que só mudanças reais (>2 amostras consecutivas de desvio) disparam envio.

---

## 7. Protocolo ESP-NOW — Pacote Binário v3

**Canal: 1 | Tamanho: 16 bytes**

```c
typedef struct __attribute__((packed)) {
    uint8_t  version;       // 0x03
    uint8_t  type;          // PacketType
    uint16_t node_id;       // 2 últimos bytes do MAC
    uint8_t  sensor_id;     // 1 ou 2  |  0 = controle/heartbeat
    uint8_t  ttl;           // decrementado por relay (max 8)
    uint16_t seq;           // contador por node (wrap around ok)
    uint16_t distance_cm;   // leitura filtrada  |  0xFFFF = erro
    int8_t   rssi;          // preenchido pelo receptor
    int8_t   vbat;          // décimos de V (33=3.3V)  | -1=n/a
    uint8_t  flags;         // bitmask
    uint8_t  reserved;      // alinhamento, futuro uso
    uint16_t crc;           // CRC-16/CCITT bytes 0..13
} espnow_packet_t;          // 16 bytes
```

**Flags:**
```
bit 0: is_relay        retransmitido por relay
bit 1: ota_pending     node aguarda OTA
bit 2: sensor_error    leitura inválida (distance_cm = 0xFFFF)
bit 3: low_battery     vbat abaixo do limiar
bit 4: config_pending  NVS desatualizado
bit 5: cfg_num_sensors compat legacy: num_sensors em distance_cm high byte
```

### Configuração estendida (mantendo 16 bytes)

Para evoluir `CMD_CONFIG` sem alterar `espnow_packet_t`, o transporte de configuração completa passa a reutilizar campos do pacote atual:

```c
// Somente quando type == PKT_CMD_CONFIG
sensor_id   -> alvo (0=global, 1/2=sensor específico)
seq         -> id da transação de configuração
distance_cm -> config_value_u16
vbat        -> config_group
reserved    -> config_item
flags       -> CFG_FLAG_* (first/last/ack/applied/error)
```

Grupos previstos:

- `GENERAL`
- `TIMING`
- `FILTER`
- `SENSOR_HW`
- `VBAT`
- `COMMIT`

Cada pacote carrega **um item de configuração**. O commit é explícito no final da transação.

### Tipos de pacote

| type | Nome | Direção | Descrição |
|------|------|---------|-----------|
| 0x01 | SENSOR | Node→GW | Telemetria: distance_cm filtrado |
| 0x02 | HEARTBEAT | Node→GW | Sinal de vida, sem leitura nova |
| 0x03 | HELLO | Node→GW | Anúncio no boot |
| 0x10 | CMD_CONFIG | GW→Node | Atualiza NVS do node |
| 0x11 | CMD_RESTART | GW→Node | Reinicia o node |
| 0x12 | CMD_OTA_START | GW→Node | Inicia sessão OTA |
| 0x13 | OTA_BLOCK | GW→Node | Bloco de firmware (~200 bytes) |
| 0x14 | OTA_END | GW→Node | Finaliza OTA + SHA-256 |
| 0x20 | ACK | Bidirecional | Confirmação |

---

## 8. Gateway

Recebe ESP-NOW → serializa JSON → USB.  
Recebe JSON de comando da USB → ESP-NOW.

### Saída USB — JSON por linha

**SENSOR:**
```json
{"v":3,"type":"SENSOR","node_id":"0x7758","sensor_id":1,
 "distance_cm":118,"rssi":-63,"vbat":33,"flags":0,"seq":1234,"ts":1741780800}
```

**HEARTBEAT:**
```json
{"v":3,"type":"HEARTBEAT","node_id":"0x2EC4","sensor_id":0,"rssi":-71,"seq":88,"ts":1741780860}
```

**HELLO:**
```json
{"v":3,"type":"HELLO","node_id":"0x9EAC","fw_version":"3.2.0","num_sensors":2,"ts":1741780500}
```

**GATEWAY_STATUS:**
```json
{"v":3,"type":"GATEWAY_STATUS","fw":"4.0.0","mac":"80:F3:DA:62:A7:84",
 "transport":"usb","proto":3,"channel":1,"uptime_s":120,"free_heap":237120,
 "rx_packets":52,"queue_drops":0,"json_tx":68,"cmd_rx":1,"cmd_ok":1,
 "cmd_fail":0,"bad_json":0,"crc_failures":0,"radio_tx_ok":0,"radio_tx_fail":0,
 "queue_depth":0,"unhandled_pkt":0,"ts":1741780860}
```

**CMD_ACK:**
```json
{"v":3,"type":"CMD_ACK","cmd":"SETTIME","ok":true,"ts":1741780861}
```

### Entrada USB — Comandos do servidor

```json
{"cmd":"CONFIG","node_id":"0x2EC4",
 "num_sensors":2,
 "sensor":[
   {"id":1,"trig_pin":1,"echo_pin":0,"enabled":true},
   {"id":2,"trig_pin":3,"echo_pin":2,"enabled":true}
 ],
 "interval_measure_s":30,"interval_send_s":120,"heartbeat_s":60,
 "filter_window":5,"filter_outlier_cm":10,"filter_threshold_cm":2
}
```

```json
{"cmd":"RESTART","node_id":"0x7758"}
{"cmd":"OTA_START","node_id":"broadcast","fw_size":819200,"fw_sha256":"a3f1c2..."}
```

> Estado atual: a implementação em produção ainda aceita apenas um subconjunto compacto de `CONFIG` (`num_sensors` e parâmetros VBAT). O JSON rico acima continua sendo a interface-alvo, a ser quebrada em itens `config_group/config_item/value` no bridge.

---

## 9. Bridge Python (`bridge.py`) — Cálculos e MQTT

Os parâmetros de reservatório vivem aqui, em arquivo de config (YAML/JSON).

### Configuração de reservatórios (`reservoirs.yaml`)

```yaml
reservoirs:
  "0x7758":
    - sensor_id: 1
      alias: CON
      name: Castelo de Consumo
      level_max_cm: 450
      volume_max_L: 80000
      sensor_offset_cm: 20

  "0x2EC4":
    - sensor_id: 1
      alias: CB31
      name: Casa de Bombas Nº3 - Tanque 1
      level_max_cm: 200
      volume_max_L: 40000
      sensor_offset_cm: 10
    - sensor_id: 2
      alias: CB32
      name: Casa de Bombas Nº3 - Tanque 2
      level_max_cm: 200
      volume_max_L: 40000
      sensor_offset_cm: 10
```

### Cálculos (bridge.py)

```python
def calculate(distance_cm: int, cfg: dict) -> dict:
    level_max_cm      = cfg["level_max_cm"]
    volume_max_L      = cfg["volume_max_L"]
    sensor_offset_cm  = cfg["sensor_offset_cm"]

    level_cm  = level_max_cm - (distance_cm - sensor_offset_cm)
    level_cm  = max(0, min(level_cm, level_max_cm))   # clamp

    pct       = round((level_cm / level_max_cm) * 100, 1)
    volume_L  = round((level_cm / level_max_cm) * volume_max_L)

    return {"level_cm": level_cm, "pct": pct, "volume_L": volume_L}
```

### Tópicos MQTT publicados

```
aguada/{node_id}/{sensor_id}/state    → payload JSON completo
aguada/{node_id}/status               → "online" / "offline"
aguada/gateway/status                 → "online" / "offline"
aguada/gateway/health                 → payload JSON retained do gateway
aguada/gateway/ack                    → ACKs de comando do gateway
```

**Payload state:**
```json
{
  "alias": "CON",
  "distance_cm": 118,
  "level_cm": 352,
  "pct": 78.2,
  "volume_L": 62560,
  "rssi": -63,
  "vbat": 3.3,
  "seq": 1234,
  "ts": 1741780800
}
```

### MQTT Discovery (publicado no HELLO)

```
homeassistant/sensor/aguada_{node_id}_{sensor_id}_level/config →
{
  "name": "CON - Nível",
  "state_topic": "aguada/0x7758/1/state",
  "value_template": "{{ value_json.level_cm }}",
  "unit_of_measurement": "cm",
  "device_class": "distance",
  "unique_id": "aguada_0x7758_1_level",
  "device": {"name": "CON", "identifiers": ["aguada_0x7758"]}
}
```

Bridge publica entidades para: `level_cm`, `pct`, `volume_L`, `distance_cm`, `rssi`.

Além disso, o bridge publica MQTT Discovery do gateway USB para:

- online (`binary_sensor`)
- uptime
- free_heap
- queue_drops
- crc_failures
- cmd_fail
- radio_tx_fail
- last_seen

### Tópicos MQTT subscritos (comandos)

```
aguada/cmd/config    → serializa para USB
aguada/cmd/restart   → serializa para USB
aguada/cmd/ota       → lê .bin, inicia fluxo OTA via USB/gateway
```

---

## 10. Mesh — Tabela de Vizinhos

```c
typedef struct {
    uint16_t node_id;
    uint8_t  mac[6];
    int8_t   rssi;
    uint8_t  hops_to_gw;
    uint32_t last_seen;
} neighbor_t;

// Melhor rota = maior score
int score = rssi - (hops_to_gw * 10);
```

Atualizada ao receber qualquer pacote. Vizinhos sem atividade por `3 × heartbeat_s` são removidos.

**Topologia CMASM (estimada):**
```
GW (ESP32-S3)
  └── N01 CON
  └── N03 CB31/32
        └── N04 CIE1/2
              └── N05 CBIF1/2
```

---

## 11. OTA via ESP-NOW

```
servidor → bridge.py → USB
  gateway recebe CMD_OTA_START
  gateway fragmenta .bin em blocos de 200 bytes
  envia OTA_BLOCK[0..N] com ACK por bloco
  envia OTA_END + SHA-256

node:
  grava blocos na partição app_ota
  OTA_END:
    SHA-256 OK   → reinicia no novo firmware
    SHA-256 FAIL → rollback automático
```

**Partições:**
```
nvs      20KB
otadata   8KB
app0    1.5MB  ← ativo
app1    1.5MB  ← OTA
spiffs  512KB
```

**Tempo estimado:** ~10–20s para 800KB link direto. +~50% por hop de relay.

---

## 12. Resiliência

| Mecanismo | Onde | O que faz |
|-----------|------|-----------|
| CRC-16 | Todo pacote | Detecta corrupção; descarta pacote inválido |
| SHA-256 | OTA | Verifica integridade do firmware |
| Seq number | Todo pacote | Detecta duplicatas e perda |
| Outlier reject | Node | Descarta eco falso do HC-SR04 |
| Média móvel | Node | Suaviza oscilação da superfície |
| Threshold 2cm | Node | Evita flood por ruído de ±1cm |
| TTL | Mesh | Evita loops; max 8 hops |
| Rollback OTA | Node | Firmware anterior preservado se falhar |
| Watchdog | Node/GW | Reinicia em travamento |
| Restart diário | Node | Hora configurável por NVS |
| SENSOR_ERROR | Node | Leitura inválida nunca silenciada |
| low_battery flag | Node | Alerta antes de falha de energia |

---

## 13. Balanço Hídrico (bridge.py / HA)

```python
# Calculado no servidor, não nos nodes
balance = volume_L(18h) - volume_L(06h)
# > 0  → abastecimento
# < 0  → consumo
# delta > limiar configurado → alerta de vazamento
```

Publicado em: `aguada/{node_id}/{sensor_id}/balance`

---

## 14. Defaults

```c
// config/defaults.h
#define ESPNOW_CHANNEL           1
#define DEFAULT_MEASURE_S        30
#define DEFAULT_SEND_S           120
#define DEFAULT_HEARTBEAT_S      60
#define DEFAULT_FILTER_WINDOW    5      // amostras
#define DEFAULT_OUTLIER_CM       10     // rejeita delta > 10cm
#define DEFAULT_THRESHOLD_CM     2      // envia se mudou >= 2cm
#define DEFAULT_TTL              8
#define OTA_BLOCK_SIZE           200    // bytes
#define VBAT_LOW_THRESHOLD       32     // 3.2V em décimos de V
#define FW_VERSION               "3.2.0"
```

---

## 15. Estrutura do Firmware

```
firmware/
  src/
    main.cpp
    radio/
      espnow.cpp / .h       init, send, recv, channel
    mesh/
      neighbor.cpp / .h     tabela de vizinhos, score, relay
    sensors/
      driver_api.h          interface comum
      ultrasonic.cpp / .h   HC-SR04, TRIG/ECHO, timeout
      filter.cpp / .h       outlier reject, moving avg, threshold
    config/
      nvs_config.cpp / .h   leitura/gravação NVS
      defaults.h            constantes padrão
    ota/
      ota_receiver.cpp / .h recebe blocos, grava partição, rollback
    gateway/
      gateway.cpp / .h      serializa JSON, parseia comandos USB
  platformio.ini
  partitions.csv
```

---

## 16. Roadmap

| Fase | Entregável | Prioridade |
|------|-----------|-----------|
| 1 | Firmware único: sensor + relay + NVS boot | 🔴 crítico |
| 2 | Protocolo binário v3 + CRC-16 | 🔴 crítico |
| 3 | Filtros: outlier + média móvel + threshold | 🔴 crítico |
| 4 | Gateway USB + JSON serial | 🔴 crítico |
| 5 | bridge.py + cálculos + MQTT + HA Discovery | 🔴 crítico |
| 6 | CMD_CONFIG via ESP-NOW | 🟠 importante |
| 7 | Mesh relay + tabela de vizinhos | 🟠 importante |
| 8 | OTA via ESP-NOW | 🟡 desejável |
| 9 | Deep sleep (bateria) | 🟡 desejável |
| 10 | Balanço hídrico automatizado | 🟡 desejável |
| 11 | Dashboard HA + alertas | 🟡 desejável |
