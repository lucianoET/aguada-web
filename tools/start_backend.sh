#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"
PYTHON_BIN="${PYTHON_BIN:-}"
HOST="${AGUADA_WEB_HOST:-127.0.0.1}"
PORT="${AGUADA_WEB_PORT:-8001}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$VENV_PY" ]]; then
    PYTHON_BIN="$VENV_PY"
  else
    PYTHON_BIN="$(command -v python3)"
  fi
fi

cd "$PROJECT_ROOT"
export PYTHONUNBUFFERED=1

exec "$PYTHON_BIN" -m uvicorn backend.main:app --host "$HOST" --port "$PORT"
