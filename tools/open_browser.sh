#!/usr/bin/env bash
# Aguarda o backend responder e abre o navegador.
BACKEND_URL="${AGUADA_WEB_BACKEND_URL:-http://127.0.0.1:8001}"
APP_URL="${AGUADA_WEB_APP_URL:-http://localhost}"
MAX_WAIT="${AGUADA_WEB_BROWSER_MAX_WAIT:-60}"

echo "[browser] Aguardando backend em $BACKEND_URL ..."
elapsed=0
while ! curl -sf "$BACKEND_URL/api/reservoirs" >/dev/null 2>&1; do
    if [[ $elapsed -ge $MAX_WAIT ]]; then
        echo "[browser] Timeout após ${MAX_WAIT}s. Abrindo mesmo assim."
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

echo "[browser] Backend pronto após ${elapsed}s. Abrindo $APP_URL ..."
xdg-open "$APP_URL"
