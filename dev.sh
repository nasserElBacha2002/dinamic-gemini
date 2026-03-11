#!/usr/bin/env bash
# Levanta backend (Python) y frontend (Vite) para desarrollo local.
# Uso: ./dev.sh   (desde la raíz del repo)

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "[dev] No hay .venv en la raíz. Crea uno: python -m venv .venv && .venv/bin/pip install -e ."
  PYTHON=python
fi

# Backend en segundo plano
echo "[dev] Arrancando backend en http://127.0.0.1:${PORT} ..."
"$PYTHON" -m uvicorn src.api.server:app --reload --port "$PORT" &
BE_PID=$!

cleanup() {
  echo "[dev] Cerrando backend (PID $BE_PID)..."
  kill "$BE_PID" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM EXIT

# Frontend en primer plano (Ctrl+C cierra ambos)
echo "[dev] Arrancando frontend..."
cd frontend && npm run dev
