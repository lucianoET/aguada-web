#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OFFLINE_DIR="$ROOT_DIR/.offline_install"
IMAGES_DIR="$OFFLINE_DIR/images"

if ! command -v docker >/dev/null 2>&1; then
  echo "[erro] docker não encontrado no host"
  exit 1
fi

for image_tar in \
  "$IMAGES_DIR/aguada-web-app-offline.tar" \
  "$IMAGES_DIR/nginx-alpine.tar" \
  "$IMAGES_DIR/eclipse-mosquitto-2.tar"; do
  if [[ ! -f "$image_tar" ]]; then
    echo "[erro] arquivo ausente: $image_tar"
    exit 1
  fi
done

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "[warn] .env não encontrado; copiando modelo CMASM"
  cp "$OFFLINE_DIR/cmasm.env.example" "$ROOT_DIR/.env"
fi

echo "[1/3] Carregando imagens"
docker load -i "$IMAGES_DIR/aguada-web-app-offline.tar"
docker load -i "$IMAGES_DIR/nginx-alpine.tar"
docker load -i "$IMAGES_DIR/eclipse-mosquitto-2.tar"

echo "[2/3] Subindo stack offline"
docker compose -f "$OFFLINE_DIR/docker-compose.offline.yml" up -d

echo "[3/3] Status"
docker compose -f "$OFFLINE_DIR/docker-compose.offline.yml" ps

echo
echo "[ok] Instalação offline iniciada"
echo "Acesse: http://192.168.10.141/"