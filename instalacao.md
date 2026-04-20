# Instalação — Aguada Web

Guia para instalar o Aguada Web em um novo computador Linux.

---

## Pré-requisitos

| Ferramenta | Versão mínima | Instalação |
|------------|---------------|------------|
| Python | 3.11+ | `sudo apt install python3 python3-venv python3-pip` |
| Git | qualquer | `sudo apt install git` |
| Docker + Compose | v2 | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| Node.js + npm | 18+ (só se for recompilar CSS) | `sudo apt install nodejs npm` |

**Dependências de sistema para WeasyPrint** (geração de PDF):

```bash
sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
  libcairo2 libgdk-pixbuf-2.0-0 libffi-dev libfontconfig1 fonts-liberation
```

---

## 1. Clonar o repositório

```bash
git clone https://github.com/luctronics-ET/aguada-web.git
cd aguada-web
```

---

## 2. Configurar o ambiente

```bash
cp .env.example .env
```

Edite o `.env` conforme necessário (apenas se quiser mudar os padrões):

```env
# Fuso horário para o scheduler de relatórios (padrão: America/Sao_Paulo)
TZ=America/Sao_Paulo

# Porta pública do nginx (padrão: 80)
HTTP_PORT=80

# Autenticação MQTT — deixar em branco para acesso anônimo
# MQTT_USER=
# MQTT_PASS=
```

> O `docker-compose.yml` já sobe a stack WiFi completa por padrão. O arquivo `docker-compose.wifi.yml` foi mantido para compatibilidade operacional.

---

## 3A. Modo produção WiFi — Docker completo (recomendado)

> Use este modo quando o gateway se conecta via WiFi/MQTT. Não é necessário porta serial nem Python instalado no host.

### Arquivos necessários

| Arquivo | Descrição |
|---------|-----------|
| `docker-compose.yml` | Stack padrão de release: app + mqtt + nginx |
| `docker-compose.wifi.yml` | Variante equivalente para compatibilidade operacional |
| `nginx.docker.conf` | nginx com proxy interno para `app:8000` |
| `tools/mosquitto.conf` | Configuração do broker Mosquitto |
| `frontend/` | Página estática servida pelo nginx |

### Passos

```bash
# 1. Clonar
git clone https://github.com/luctronics-ET/aguada-web.git
cd aguada-web

# 2. (Opcional) Criar .env só se quiser mudar porta HTTP ou fuso horário
#    Por padrão: HTTP_PORT=80, TZ=America/Sao_Paulo
echo "HTTP_PORT=80" > .env

# 3. Subir a stack
docker compose up -d

# 4. Verificar
docker compose ps
docker compose logs -f app
```

O broker MQTT ficará acessível na LAN na porta `1883`. Configure o firmware do gateway ESP32 com o IP do host e porta `1883`.

O frontend estará em `http://<ip-do-host>/`.

### Parar / atualizar

```bash
# Parar
docker compose down

# Atualizar após git pull
docker compose build --no-cache
docker compose up -d
```

### Dados persistentes

O banco SQLite e os PDFs ficam no volume Docker `aguada-data`. Para fazer backup:

```bash
docker run --rm -v aguada-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/aguada-backup.tar.gz /data
```

---

## 3B. Modo development — backend local + nginx Docker

> Para desenvolvimento e testes locais. O broker MQTT interno (`mqtt`) ainda é usado para receber o gateway.

### Backend (Python)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Subir só o broker MQTT
docker compose up -d mqtt

# Iniciar backend local apontando para o broker
GATEWAY_TRANSPORT=wifi GW_MQTT_HOST=localhost ./tools/start_backend.sh
```

O backend ficará em `http://127.0.0.1:8001`.

### Frontend via nginx (Docker)

```bash
docker compose up -d nginx
```

---

## 4. Autostart com systemd (sem Docker)

Para o backend iniciar automaticamente com o sistema:

```bash
./tools/install_autostart_user_service.sh
```

Ativa o serviço `aguada-web-backend.service` como serviço de usuário systemd.

Para iniciar sem precisar fazer login: `sudo loginctl enable-linger $USER`

Verificar status:

```bash
systemctl --user status aguada-web-backend
journalctl --user -u aguada-web-backend -f
```

---

## 5. (Opcional) Recompilar o CSS Tailwind

O CSS compilado já está em `frontend/assets/tailwind.css`. Só é necessário recompilar ao alterar classes Tailwind no HTML:

```bash
npm install
npm run build:css
```

---

## 6. Verificar instalação

| Endpoint | Esperado |
|----------|----------|
| `http://localhost/` | Dashboard HTML |
| `http://localhost/api/reservoirs` | JSON com reservatórios |
| `http://localhost/api/gateway` | Status do gateway |
| `http://127.0.0.1:8001/api/reservoirs` | (dev direto) |

---

## Estrutura de dados

O SQLite e os PDFs ficam em `DATA_DIR` (padrão: `./data/`):

```
data/
  aguada.db       # banco de leituras
  reports/        # PDFs diários gerados pelo scheduler (06h)
```

---

## Resumo rápido (produção, Docker + WiFi)

```bash
git clone https://github.com/luctronics-ET/aguada-web.git
cd aguada-web
docker compose up -d
```

Frontend: `http://<ip-do-host>/`
MQTT (para o firmware do gateway): `<ip-do-host>:1883`

## Observação de release

Esta versão final do repositório não inclui páginas antigas, documentação histórica de planejamento nem arquivos de backup que não participam do build atual.
