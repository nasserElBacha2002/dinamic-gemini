#!/usr/bin/env bash
# Levanta backend (Python) y frontend (Vite) para desarrollo local.
# Uso: ./dev.sh   (desde la raíz del repo)

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"

# Load shared env once so backend + spawned workers inherit identical runtime config.
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

# Shared env for backend + on-demand workers
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"
# Keep embedded worker loop disabled: backend should spawn workers on demand.
export EMBEDDED_WORKER_ENABLED=false
# Local sessions should not auto-reclaim stale RUNNING jobs from previous runs.
export WORKER_STALE_RUNNING_TIMEOUT_SEC=900
if [[ -z "${WORKER_ON_DEMAND_COMMAND:-}" ]]; then
  export WORKER_ON_DEMAND_COMMAND="$("$PYTHON" -c 'import json,sys; print(json.dumps([sys.argv[1], "-m", "src.jobs.run_worker"]))' "$PYTHON")"
fi
echo "[dev] Runtime: OUTPUT_DIR=${OUTPUT_DIR:-output} SQLSERVER_ENABLED=${SQLSERVER_ENABLED:-unset} EMBEDDED_WORKER_ENABLED=${EMBEDDED_WORKER_ENABLED:-unset}"
echo "[dev] On-demand worker command: ${WORKER_ON_DEMAND_COMMAND}"

# Prevent stale mixed runtimes: kill previously running local backend/legacy worker
# processes before starting fresh ones.
echo "[dev] Limpiando procesos previos de backend/legacy worker..."
if command -v pgrep >/dev/null 2>&1; then
  DEV_WORKER_PIDS="$(pgrep -f "src\\.jobs\\.run_worker_dev$" || true)"
  if [[ -n "${DEV_WORKER_PIDS}" ]]; then
    echo "${DEV_WORKER_PIDS}" | xargs kill 2>/dev/null || true
    sleep 0.3
    STILL_DEV_WORKER_PIDS="$(pgrep -f "src\\.jobs\\.run_worker_dev$" || true)"
    if [[ -n "${STILL_DEV_WORKER_PIDS}" ]]; then
      echo "${STILL_DEV_WORKER_PIDS}" | xargs kill -9 2>/dev/null || true
    fi
  fi
  API_PIDS="$(pgrep -f "uvicorn src.api.server:app --reload --port ${PORT}" || true)"
  if [[ -n "${API_PIDS}" ]]; then
    echo "${API_PIDS}" | xargs kill 2>/dev/null || true
    sleep 0.3
    STILL_API_PIDS="$(pgrep -f "uvicorn src.api.server:app --reload --port ${PORT}" || true)"
    if [[ -n "${STILL_API_PIDS}" ]]; then
      echo "${STILL_API_PIDS}" | xargs kill -9 2>/dev/null || true
    fi
  fi
fi

echo "[dev] Arrancando backend en http://127.0.0.1:${PORT} ..."
(cd "$ROOT/backend" && "$PYTHON" -m uvicorn src.api.server:app --reload --port "$PORT") &
BE_PID=$!

cleanup() {
  echo "[dev] Cerrando procesos..."
  kill "$BE_PID" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM EXIT

# Frontend en primer plano (Ctrl+C cierra backend)
echo "[dev] Arrancando frontend..."
cd "$ROOT/frontend" && npm run dev