#!/usr/bin/env bash
# Levanta backend (Python) y frontend (Vite) para desarrollo local.
# Uso: ./dev.sh   (desde la raíz del repo)

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
# Prefer backend's venv (has backend deps); fallback to root .venv or system python
if [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/backend/.venv/bin/python"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
else
  echo "[dev] No .venv encontrado. Crea uno en backend: cd backend && python3 -m venv .venv && .venv/bin/pip install -e \".[dev]\""
  PYTHON=python
fi

# Ensure backend package is installed (from backend/)
"$PYTHON" -m pip install -e "$ROOT/backend" -q 2>/dev/null || true

# Backend en segundo plano (PYTHONPATH=backend para que el import src.api.server funcione)
echo "[dev] Arrancando backend en http://127.0.0.1:${PORT} ..."
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"
(cd "$ROOT/backend" && "$PYTHON" -m uvicorn src.api.server:app --reload --port "$PORT") &
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
