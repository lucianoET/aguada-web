# Aguada Web — workspace standalone

Este diretório foi preparado para funcionar fora do repositório `espnow-ha`, focado no host do `aguada-web`.

## O que já está contido aqui

- `backend/`, `frontend/`, `docs/`, `data/` — aplicação web e dados locais
- `docs/repo-context/AGUADA_SYSTEM_DOC.md` — especificação canônica do sistema
- `docs/repo-context/ROADMAP.md` — estado e prioridades do projeto
- `docs/repo-context/README-root.md` — contexto original do repositório raiz
- `tools/mqtt_broker.py` — broker MQTT local opcional
- `tools/start_backend.sh` — inicia o FastAPI/uvicorn do `aguada-web`
- `tools/install_autostart_user_service.sh` — instala autostart do backend via systemd user
- `tools/systemd/aguada-web-backend.service` — unit template do backend

## Fluxo recomendado neste workspace

O backend do `aguada-web` já contém a bridge serial em `backend/bridge.py`, com reconexão automática da porta serial.

Isso significa que, neste workspace separado, o fluxo principal recomendado é:

`Gateway USB` → `aguada-web/backend.main:app` → `SQLite/WebSocket` → frontend web

MQTT é opcional e controlado pelas variáveis do `.env`.

## Configuração

1. Copie `.env.example` para `.env`, se necessário.
2. Ajuste pelo menos:
   - `SERIAL_PORT`
   - `DATA_DIR`
   - `MQTT_HOST` apenas se quiser publicar MQTT

## Execução manual

### Backend

Use o script:

- `./tools/start_backend.sh`

Ou diretamente:

- `python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8001`

### Frontend via Docker/nginx

- `docker compose up -d nginx`

## Autostart do backend

Para manter a bridge serial sempre ativa quando o gateway estiver ligado, instale o serviço user do systemd:

- `./tools/install_autostart_user_service.sh`

Esse serviço mantém o backend web sempre rodando; a reconexão serial fica por conta do próprio `backend/bridge.py`.

## Observações

- Nenhum arquivo do `homeassistant/` foi copiado nem modificado aqui.
- O script legado da raiz (`tools/start_bridge_autoswitch.sh`) não é o fluxo recomendado neste workspace standalone.
- Se você quiser MQTT local para testes, pode iniciar `tools/mqtt_broker.py` separadamente.
