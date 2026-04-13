# Aguada Web

Sistema de monitoramento hídrico via web. O gateway de campo conecta via **WiFi/MQTT**; o backend processa os dados e serve o frontend.

## Fluxo de dados

```
Gateway ESP32 (WiFi) → MQTT (Mosquitto) → backend FastAPI → SQLite + WebSocket → frontend web
```

## Conteúdo

- `backend/` — FastAPI + bridge MQTT + SQLite + geração de PDF
- `frontend/` — SPA estática (HTML/JS), servida pelo nginx
- `docs/` — documentação do sistema
- `tools/` — scripts de inicialização e systemd units
- `docker-compose.wifi.yml` — stack de produção completa (recomendado)

## Início rápido (produção, Docker)

```bash
git clone https://github.com/luctronics-ET/aguada-web.git
cd aguada-web
docker compose -f docker-compose.wifi.yml up -d
```

Veja [instalacao.md](instalacao.md) para instruções detalhadas.

## Configuração

As variáveis com padrão razoável não precisam de `.env`. Para ajustes:

| Variável | Padrão | Descrição |
|----------|--------|----------|
| `HTTP_PORT` | `80` | Porta pública do nginx |
| `TZ` | `America/Sao_Paulo` | Fuso horário do scheduler |
| `MQTT_PORT` | `1883` | Porta do broker |
| `MQTT_USER` / `MQTT_PASS` | — | Autenticação MQTT (se configurada) |

## Desenvolvimento local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./tools/start_backend.sh          # backend em :8001
docker compose -f docker-compose.wifi.yml up -d nginx   # nginx em :80
```

## Autostart sem Docker

```bash
./tools/install_autostart_user_service.sh
```

Instala `aguada-web-backend.service` como serviço de usuário systemd.
