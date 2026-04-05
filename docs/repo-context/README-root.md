
# Aguada — Telemetria de Reservatórios (ESP-NOW + Home Assistant)

Sistema de telemetria de nível/volume de reservatórios com:

- nodes ESP32-C3 (HC-SR04)
- gateway ESP32-S3 **ou ESP32 clássico** (ESP-NOW → USB serial)
- `tools/bridge.py` (cálculo + MQTT + MQTT Discovery)
- Home Assistant (dashboard, templates, automações)

## Arquitetura

`Node(s) ESP32-C3` → `Gateway ESP32-S3/ESP32` → `bridge.py` → `MQTT` → `Home Assistant`

## Build rápido

- Node:
	- `cd firmware/node && pio run`
- Gateway:
	- `cd firmware/gateway && pio run -e gateway-c3` (ESP32-C3)
	- `cd firmware/gateway && pio run -e gateway-s3` (ESP32-S3)
	- `cd firmware/gateway && pio run -e gateway-esp32-usb` (ESP32 clássico)
	- `cd firmware/gateway-ethernet && pio run -e gateway-esp32-enc28j60` (ESP32 + ENC28J60, ESP-NOW→Ethernet MQTT)

Upload (exemplo):
	- `cd firmware/gateway && pio run -e gateway-esp32-usb -t upload --upload-port /dev/ttyACM1`
	- `cd firmware/gateway-ethernet && pio run -e gateway-esp32-enc28j60 -t upload --upload-port /dev/ttyACM0`

### Gateway Ethernet (ESP32 + ENC28J60)

- Projeto: `firmware/gateway-ethernet`
- Fluxo: ESP-NOW (canal 1) → JSON v3 → MQTT via Ethernet
- Tópicos publicados:
	- `aguada/gateway/status` (`online`/`offline`, retained)
	- `aguada/gateway/raw`
	- `aguada/{node_id}/{sensor_id}/raw`
- Pinagem ENC28J60 (ESP32 DevKit):
	- SCK=`GPIO18`, MISO=`GPIO19`, MOSI=`GPIO23`, CS=`GPIO5`

## Bridge

Dependências:

- `pip install -r tools/requirements.txt`

Execução:

- `python tools/bridge.py --port /dev/ttyACM0 --mqtt localhost`

Autostart recomendado no Linux desktop/headless:

- `./tools/install_autostart_user_service.sh`
- o serviço `aguada-bridge-autoswitch.service` sobe o bridge automaticamente quando um `/dev/ttyACM*`/`ttyUSB*` aparece

### Observabilidade do gateway USB

O gateway USB publica eventos JSON adicionais na serial, consumidos por `tools/bridge.py`:

- `GATEWAY_READY`
- `GATEWAY_STATUS`
- `CMD_ACK`

O bridge republica esses eventos em MQTT:

- `aguada/gateway/status` → `online` / `offline` (retained)
- `aguada/gateway/health` → payload JSON retained com uptime, heap, drops, CRC, etc.
- `aguada/gateway/ack` → ACKs de comandos do gateway (não retained)

## Home Assistant — migração limpa (recomendado)

Para evitar entidades duplicadas ou sem dados:

1. **Use MQTT Discovery para reservatórios** (CON/CAV/CB*/CIE*), publicado pelo `bridge.py`.
2. **Gateway USB também já possui MQTT Discovery** para entidades diagnósticas (online, uptime, heap, queue drops, CRC failures, cmd fail, radio tx fail, last seen).
3. No `configuration.yaml` do HA, use:
	 - `mqtt:` (com discovery habilitado no HA)
	 - `sensor: !include aguada/statistics_sensors.yaml`
	 - `template: !include aguada/template_sensors.yaml`
	 - `automation: !include automations.yaml`

Arquivos de referência neste repositório:

- `homeassistant/configuration_snippet.yaml`
- `homeassistant/configuration_full.yaml`

## Importante

- Os arquivos `homeassistant/mqtt_sensors.yaml` e `homeassistant/mqtt_gateway_sensors.yaml` são **legados** e não devem ser usados junto com discovery.
- Especificação oficial: `AGUADA_SYSTEM_DOC.md`.
- Pinagem atual de Node/Relay: `PINAGEM.md`.
