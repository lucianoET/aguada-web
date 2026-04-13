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
```

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

- `bridge.py` — recepção MQTT do gateway WiFi, parse de pacotes, modo simulação. Carrega `reservoirs.yaml` para montar `RESERVOIR_INDEX` (chave: `(node_id, sensor_id)`)
- `db.py` — schema SQLite e todas as queries (sem lógica de negócio). Tabelas: `readings`, `reservoir_state`, mais tabelas manuais (hidrometros, bombas, válvulas, reservatórios) e `nodes`
- `calc.py` — cálculo de `level_cm`/`volume_l`/`pct` a partir de `distance_cm`, e agregação de eventos de consumo/abastecimento
- `report.py` — geração de PDF diário via WeasyPrint
- `main.py` — rotas FastAPI + servir SPA estática do `frontend/`

### Configuração de reservatórios

`backend/reservoirs.yaml` é a fonte de verdade para o mapeamento `node_id → sensor_id → alias/nome/capacidade`. Qualquer novo reservatório físico deve ser adicionado aqui.

### Frontend

Páginas HTML puras em `frontend/` servidas como SPA pelo FastAPI (fallback para `index.html`). Usa Tailwind CSS compilado em `frontend/assets/tailwind.css`. Em produção, o nginx serve o frontend estático e faz proxy reverso para o backend.

### Dados

`data/aguada.db` — SQLite com todas as leituras. `data/reports/` — PDFs gerados. `DATA_DIR` configurável via `.env`.

### Variáveis de ambiente (`.env`)

- `GATEWAY_TRANSPORT` — transporte do gateway (padrão: `wifi`)
- `DATA_DIR` — diretório dos dados e relatórios
- `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS` — broker MQTT opcional
- `TZ` — fuso horário para o scheduler (padrão: `America/Sao_Paulo`)
- `HTTP_PORT` — porta do nginx (padrão: 80)

### Testes

Os testes usam `pytest-asyncio` no modo `auto`. O `conftest.py` provê fixture `db` com SQLite em memória temporária. `test_api.py` testa as rotas FastAPI diretamente sem bridge MQTT.
