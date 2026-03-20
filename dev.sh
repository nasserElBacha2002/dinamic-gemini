#!/usr/bin/env bash
# Levanta backend (Python), worker y frontend (Vite) para desarrollo local.
# Uso: ./dev.sh   (desde la raíz del repo)

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"

# Load shared env once so backend + worker inherit identical runtime config.
# Parse .env safely (supports optional spaces around "=" without shell-eval).
if [[ -f "${ROOT}/.env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="$(echo "$key" | xargs)"
    value="${value#"${value%%[![:space:]]*}"}"
    [[ -z "$key" ]] && continue
    export "${key}=${value}"
  done < "${ROOT}/.env"
fi

# Prefer backend's venv (has backend deps); fallback to root .venv or system python
if [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/backend/.venv/bin/python"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
else
  echo "[dev] No .venv encontrado. Crea uno en backend: cd backend && python3 -m venv .venv && .venv/bin/pip install -e \".[dev]\""
  PYTHON=python
fi

# Ensure backend package is installed
"$PYTHON" -m pip install -e "$ROOT/backend" -q 2>/dev/null || true

# Shared env for backend + worker
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"
# dev.sh always starts a dedicated worker process, so keep API embedded worker disabled
# to avoid duplicate worker loops and reduce local/runtime ambiguity.
export EMBEDDED_WORKER_ENABLED=false
echo "[dev] Runtime: OUTPUT_DIR=${OUTPUT_DIR:-output} SQLSERVER_ENABLED=${SQLSERVER_ENABLED:-unset} EMBEDDED_WORKER_ENABLED=${EMBEDDED_WORKER_ENABLED:-unset}"

# Prevent stale mixed runtimes: kill previously running local backend/worker
# processes before starting fresh ones.
echo "[dev] Limpiando procesos previos de backend/worker..."
if command -v pgrep >/dev/null 2>&1; then
  WORKER_PIDS="$(pgrep -f "python -m src.jobs.run_worker" || true)"
  if [[ -n "${WORKER_PIDS}" ]]; then
    echo "${WORKER_PIDS}" | xargs kill 2>/dev/null || true
  fi
  API_PIDS="$(pgrep -f "uvicorn src.api.server:app --reload --port ${PORT}" || true)"
  if [[ -n "${API_PIDS}" ]]; then
    echo "${API_PIDS}" | xargs kill 2>/dev/null || true
  fi
fi

echo "[dev] Arrancando backend en http://127.0.0.1:${PORT} ..."
(cd "$ROOT/backend" && "$PYTHON" -m uvicorn src.api.server:app --reload --port "$PORT") &
BE_PID=$!

echo "[dev] Arrancando worker..."
(cd "$ROOT/backend" && "$PYTHON" -m src.jobs.run_worker) &
WORKER_PID=$!

cleanup() {
  echo "[dev] Cerrando procesos..."
  kill "$BE_PID" 2>/dev/null || true
  kill "$WORKER_PID" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM EXIT

# Frontend en primer plano (Ctrl+C cierra backend + worker)
echo "[dev] Arrancando frontend..."
cd "$ROOT/frontend" && npm run dev