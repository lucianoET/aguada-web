#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DST_DIR="$HOME/.config/systemd/user"
mkdir -p "$DST_DIR"

# --- Backend ---
BACKEND_TEMPLATE="$SCRIPT_DIR/systemd/aguada-web-backend.service"
BACKEND_SERVICE="aguada-web-backend.service"
sed "s#__PROJECT_ROOT__#$PROJECT_ROOT#g" "$BACKEND_TEMPLATE" > "$DST_DIR/$BACKEND_SERVICE"

# --- Browser ---
BROWSER_TEMPLATE="$SCRIPT_DIR/systemd/aguada-web-browser.service"
BROWSER_SERVICE="aguada-web-browser.service"
sed "s#__PROJECT_ROOT__#$PROJECT_ROOT#g" "$BROWSER_TEMPLATE" > "$DST_DIR/$BROWSER_SERVICE"

systemctl --user daemon-reload
systemctl --user enable --now "$BACKEND_SERVICE"
systemctl --user enable "$BROWSER_SERVICE"

if loginctl enable-linger "$USER" >/dev/null 2>&1; then
  echo "[ok] Linger ativado para $USER"
else
  echo "[warn] Para autostart sem login: sudo loginctl enable-linger $USER"
fi

echo
echo "[ok] Serviços instalados:"
echo "  $BACKEND_SERVICE (backend + serial bridge)"
echo "  $BROWSER_SERVICE (abre navegador após backend pronto)"
echo
echo "Comandos úteis:"
echo "  systemctl --user status $BACKEND_SERVICE"
echo "  systemctl --user restart $BACKEND_SERVICE"
echo "  systemctl --user start $BROWSER_SERVICE   # abre browser manualmente"
echo "  journalctl --user -u $BACKEND_SERVICE -f  # logs ao vivo"
