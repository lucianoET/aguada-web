# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandos

### Backend

```bash
# Iniciar backend (recomendado)
./tools/start_backend.sh

# Ou diretamente
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8001

# Instalar dependências
pip install -r requirements.txt
```

### Frontend (CSS)

```bash
# Compilar Tailwind CSS
npm run build:css
```

### Docker

```bash
# Subir nginx (serve o frontend estático)
docker compose up -d nginx

# Subir stack completa (app + nginx)
docker compose up -d

# Testes dentro da imagem (Python 3.13, mesmas deps de produção)
docker run --rm -v "$PWD":/app -w /app -e DATA_DIR=/tmp/d aguada-web-app python -m pytest -q
```

- Frontend em `http://localhost:${HTTP_PORT}` (8090 neste host). nginx manda `Cache-Control: no-cache` no frontend.
- **Origem dos dados:** `.env.gateway` (gitignored, `chmod 600`) define `GW_MQTT_HOST/PORT/USER/PASS` do broker do HA (192.168.0.8), onde o `aguada-bridge.service` republica `aguada/gateway/rx` e os `.../config`. Gerado a partir de `~/.config/aguada/bridge.env`. Sem ele, o app lê o mosquitto local do compose (sem dados).
- **Docker Desktop (virtiofs):** arquivo do host trocado por substituição (`sed -i`, save atômico de editor, `os.replace`) fica invisível no container até `docker compose restart <serviço>`. Escrita in-place (`cp`, `>`) aparece na hora.

### Testes

```bash
# Todos os testes
pytest

# Um arquivo específico
pytest tests/test_api.py

# Um teste específico
pytest tests/test_calc.py::nome_do_teste
```

## Arquitetura

### Fluxo de dados

```
Gateway ESP32 (WiFi) → MQTT (Mosquitto) → bridge.py (thread MQTT) → SQLite + WebSocket broadcast → frontend HTML
```

O backend é um **FastAPI** com lifespan que inicializa:
1. `bridge.Bridge` — thread daemon que recebe pacotes do gateway via MQTT, parseia e persiste no SQLite
2. `WSManager` — gerencia conexões WebSocket; a bridge chama `ws_manager.broadcast()` via `call_soon_threadsafe` para cruzar a barreira thread→asyncio
3. `APScheduler` — job diário às 6h que gera relatório PDF do dia anterior

### Módulos do backend

- `bridge.py` — recepção MQTT do gateway WiFi, parse de pacotes, dedup por `(node, sensor, seq)`, modo simulação. Carrega `reservoirs.yaml` em `RESERVOIR_INDEX` (chave: `(node_id, sensor_id)`) e `NODE_ALIASES`
- `db.py` — schema SQLite e todas as queries (sem lógica de negócio). Tabelas: `readings`, `reservoir_state`, mais tabelas manuais (hidrometros, bombas, válvulas, reservatórios) e `nodes`
- `calc.py` — cálculo de `level_cm`/`volume_l`/`pct` a partir de `distance_cm`, e agregação de eventos de consumo/abastecimento (medianas por hora + deadband de ruído: variação só conta ao acumular >= max(1,5 cm, ruído medido do sensor))
- `report.py` — geração de PDF diário via WeasyPrint
- `alarms.py` — alarmes de nível com histerese e falhas de sensor (offline, fora da faixa, salto); cada transição vira evento na tabela `events` (insert-only por trigger; reconhecimento em `event_acks`). Normas em `docs/sistemas-hidricos/Normas_Tecnicas.md`
- `main.py` — rotas FastAPI + servir SPA estática do `frontend/`

### Configuração de reservatórios

Fonte de verdade: `luctronics_firmware/platformio/tools/reservoirs.yaml` (repo aguada-firmware), o mesmo arquivo que o bridge do Home Assistant lê e edita em runtime (offsets via entidades `number`). Novo reservatório físico entra **lá**.

- `backend/reservoirs.yaml` é só uma cópia, sobrescrita por `tools/sync_reservoirs.sh` no firmware — não editar à mão.
- `RESERVOIRS_FILE` aponta direto para o arquivo do firmware (o `docker-compose.yml` monta `../platformio/tools`, ou `RESERVOIRS_DIR`). Se não existir, cai na cópia com warning.
- O backend recarrega o arquivo quando o mtime muda; YAML inválido loga erro e mantém a config anterior. Entrada sem `alias`/`name`/`sensor_offset_cm`/`volume_max_L` falha no load.
- Offsets editados no HA também chegam por MQTT: o bridge HA publica retido `aguada/<node>/<sid>/config` e o backend aplica em memória (`apply_remote_config`). Necessário no Docker Desktop, que não propaga o `os.replace` do bridge para o container. Só funciona se o backend assinar o mesmo broker do bridge HA.
- `also: ["0XEE02"]` = node alternativo do mesmo reservatório (node cabeado do CAV); é traduzido para o node principal, como `NODE_ALIASES` no bridge HA.

### Frontend

Páginas HTML puras em `frontend/` servidas como SPA pelo FastAPI (fallback para `index.html`). Usa Tailwind CSS compilado em `frontend/assets/tailwind.css`. Em produção, o nginx serve o frontend estático e faz proxy reverso para o backend.

- Mapa (Painel, `planta.html` e `rede.html?r=agua|incendio`): `assets/mapa.js` + `mapa.css` — base OSM/satélite, camadas e marcadores. Elementos fixos (reservatórios, bombas, válvulas, hidrômetros, saneamento) em `assets/infra.json`.
- Redes, prédios e Áreas A/B/C vêm do PDF "PROJETO REDE INCÊNDIO E AGUADA" via `tools/georef_plantas.py` → `assets/plantas/redes.geojson` (camada pela espessura do traço; encaixe por pontos de controle no script). Hidrantes, registros e hidrômetros dos prédios saem dos símbolos; os nomes (HID-0xx, prédio, vazão) foram lidos à mão em `tools/plantas_rotulos.json`.

### Dados

`data/aguada.db` — SQLite com todas as leituras. `data/reports/` — PDFs gerados. `DATA_DIR` configurável via `.env`.

### Variáveis de ambiente (`.env`)

- `GATEWAY_TRANSPORT` — transporte do gateway (padrão: `wifi`)
- `DATA_DIR` — diretório dos dados e relatórios
- `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS` — broker MQTT opcional
- `TZ` — fuso horário para o scheduler (padrão: `America/Sao_Paulo`)
- `HTTP_PORT` — porta do nginx (padrão: 80)
- `RESERVOIRS_FILE` — caminho do `reservoirs.yaml` (padrão: `backend/reservoirs.yaml`)

### Testes

Os testes usam `pytest-asyncio` no modo `auto`. O `conftest.py` provê fixture `db` com SQLite em memória temporária. `test_api.py` testa as rotas FastAPI diretamente sem bridge MQTT. `test_bridge.py` cobre o load/reload do `reservoirs.yaml`, alias `also` e dedup por seq.
