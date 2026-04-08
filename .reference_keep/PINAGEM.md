# Aguada — Pinagem (Node + Relay)

Este documento consolida a pinagem **atual do firmware** para facilitar montagem e bancada.

> Fonte da verdade de pinagem nesta versão:
> - `firmware/node/include/node_config.h`
> - `firmware/node/src/main.cpp`
> - `firmware/node/platformio.ini`

---

## 1) Node ESP32-C3 SuperMini (modo sensor)

### Padrões de fábrica (default)

| Função | Pino | Origem |
|---|---:|---|
| HC-SR04 Sensor 1 TRIG | GPIO1 | `DEFAULT_TRIG1` |
| HC-SR04 Sensor 1 ECHO | GPIO0 | `DEFAULT_ECHO1` |
| HC-SR04 Sensor 2 TRIG | GPIO3 | `DEFAULT_TRIG2` |
| HC-SR04 Sensor 2 ECHO | GPIO2 | `DEFAULT_ECHO2` |
| LED onboard | GPIO8 (ativo em nível baixo) | `DEFAULT_LED_PIN` |

### Observações

- O firmware é único: `num_sensors=0` vira relay, `1/2` vira sensor.
- Pinagem de sensores pode ser alterada por configuração/NVS.
- VBAT é opcional e depende de `vbat_enabled`, `vbat_pin` e `vbat_div`.

---

## 2) Relay ESP32-C3 SuperMini (quando `num_sensors=0`)

No modo relay, além do encaminhamento ESP-NOW, há periféricos auxiliares.

| Função | Pino default (C3) | Macro |
|---|---:|---|
| Botão capacitivo (módulo com saída digital OUT, ativo em LOW) | GPIO9 | `RELAY_BTN_PIN` |
| I2C SDA (HD21D/HTU21D) | GPIO6 | `RELAY_I2C_SDA_PIN` |
| I2C SCL (HD21D/HTU21D) | GPIO7 | `RELAY_I2C_SCL_PIN` |
| Endereço I2C principal | `0x40` | `RELAY_I2C_ADDR_HD21D` |
| Endereço I2C fallback | `0x44` | `RELAY_I2C_ADDR_SHT3X` |
| LED status | GPIO8 (ativo em LOW) | `DEFAULT_LED_PIN` |

### Comportamento do botão

- Clique curto: envia `HELLO`
- Pressão longa (>= 5s): reinicia o nó

---

## 3) Relay ESP32 DevKit (env `esp32-devkit-relay`)

No profile dedicado de relay (`firmware/node/platformio.ini`), a build aplica overrides:

- `DEFAULT_LED_PIN=2`
- `DEFAULT_NUM_SENSORS=0`

Pinagem efetiva do relay auxiliar em ESP32 clássico:

| Função | Pino default (ESP32 DevKit) | Origem |
|---|---:|---|
| LED | GPIO2 | build flag do env `esp32-devkit-relay` |
| Botão capacitivo (módulo OUT, ativo em LOW) | GPIO0 | `RELAY_BTN_PIN` (não-C3) |
| I2C SDA (HD21D/HTU21D) | GPIO21 | `RELAY_I2C_SDA_PIN` (não-C3) |
| I2C SCL (HD21D/HTU21D) | GPIO22 | `RELAY_I2C_SCL_PIN` (não-C3) |
| Endereço I2C principal | `0x40` | `RELAY_I2C_ADDR_HD21D` |
| Endereço I2C fallback | `0x44` | `RELAY_I2C_ADDR_SHT3X` |

---

## 4) Gateway ESP32-S3

A comunicação principal do gateway é:

- ESP-NOW (rádio)
- USB CDC Serial 115200 para o `bridge.py`

Nesta versão, não há pinagem de sensores físicos no gateway no fluxo principal.

---

## 5) Dicas de bancada

- Em relay, use alimentação estável (preferencialmente contínua).
- Para I2C, confirme pull-up em SDA/SCL (HD21D/HTU21D normalmente requerem pull-up).
- Para botão capacitivo, prefira módulo com pino `OUT` digital ligado ao `RELAY_BTN_PIN`.
- O firmware espera botão **ativo em LOW** (toque = nível baixo no pino).
- Se mudar pinos por macro/build flag, documente junto com o ambiente (`platformio.ini`).
