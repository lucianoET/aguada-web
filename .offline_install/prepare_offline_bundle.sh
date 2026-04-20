#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OFFLINE_DIR="$ROOT_DIR/.offline_install"
IMAGES_DIR="$OFFLINE_DIR/images"
BACKUPS_DIR="$OFFLINE_DIR/backups"
STAMP="$(date +%F-%H%M%S)"

mkdir -p "$IMAGES_DIR" "$BACKUPS_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[erro] docker não encontrado"
  exit 1
fi

echo "[1/5] Build da imagem offline do app"
docker build -t aguada-web-app:offline "$ROOT_DIR"

echo "[2/5] Pull das imagens auxiliares"
docker pull nginx:alpine
docker pull eclipse-mosquitto:2

echo "[3/5] Export das imagens"
docker save -o "$IMAGES_DIR/aguada-web-app-offline.tar" aguada-web-app:offline
docker save -o "$IMAGES_DIR/nginx-alpine.tar" nginx:alpine
docker save -o "$IMAGES_DIR/eclipse-mosquitto-2.tar" eclipse-mosquitto:2

echo "[4/5] Backup do diretório data"
tar czf "$BACKUPS_DIR/data-$STAMP.tar.gz" -C "$ROOT_DIR" data

echo "[5/5] Manifesto"
cat > "$OFFLINE_DIR/manifest.txt" <<EOF
Gerado em: $STAMP
Workspace: $ROOT_DIR
Imagens:
- aguada-web-app:offline -> .offline_install/images/aguada-web-app-offline.tar
- nginx:alpine -> .offline_install/images/nginx-alpine.tar
- eclipse-mosquitto:2 -> .offline_install/images/eclipse-mosquitto-2.tar
Backup:
- .offline_install/backups/data-$STAMP.tar.gz
EOF

echo
echo "[ok] Bundle offline preparado em $OFFLINE_DIR"
echo "Copie o workspace inteiro para o pendrive."