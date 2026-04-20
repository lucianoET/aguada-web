# Aguada Web

Sistema web de operação e monitoramento hídrico com backend FastAPI, persistência em SQLite, ingestão via MQTT e frontend estático servido pelo próprio backend ou por nginx.

## Fluxo de dados

```text
Gateway ESP32 (WiFi) -> MQTT (Mosquitto) -> backend FastAPI -> SQLite + WebSocket -> frontend web
```

## Estrutura atual

- `backend/` — API FastAPI, bridge MQTT, persistência SQLite e geração de PDF
- `frontend/` — páginas operacionais ativas: Painel, SCADA, Dados, Relatório, Alertas, Manutenção, Qualidade, Esgoto e Documentação
- `docs/` — documentação vigente da aplicação e formulários operacionais
- `tools/` — scripts de operação, broker MQTT local e units systemd

## Release atual

- Relatório diário persistido por data no banco
- PDF diário gerado pelo backend a partir dos dados salvos
- Navegação reduzida às telas operacionais ativas
- arquivos obsoletos e backups removidos da versão final

## Início rápido

Produção com Docker:

```bash
git clone https://github.com/luctronics-ET/aguada-web.git
cd aguada-web
docker compose up -d
```

Compatibilidade com stack explícita WiFi:

```bash
docker compose -f docker-compose.wifi.yml up -d
```

Veja [instalacao.md](instalacao.md) para instalação detalhada.

## Configuração

As variáveis padrão atendem a maior parte dos cenários. Ajustes opcionais:

| Variável | Padrão | Descrição |
|----------|--------|----------|
| `HTTP_PORT` | `80` | Porta pública do nginx |
| `TZ` | `America/Sao_Paulo` | Fuso horário do scheduler |
| `MQTT_PORT` | `1883` | Porta do broker |
| `MQTT_USER` / `MQTT_PASS` | — | Autenticação MQTT, se habilitada |
| `DATA_DIR` | `./data` | Diretório local de banco e relatórios fora do Docker |

## Desenvolvimento local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./tools/start_backend.sh
```

O backend sobe em `http://127.0.0.1:8001`.

Para expor o frontend por nginx em ambiente local:

```bash
docker compose up -d nginx
```

## Testes

```bash
source .venv/bin/activate
pytest
```

## Autostart sem Docker

```bash
./tools/install_autostart_user_service.sh
```

Instala `aguada-web-backend.service` como serviço de usuário systemd.
