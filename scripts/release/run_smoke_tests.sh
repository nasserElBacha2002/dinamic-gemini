#!/usr/bin/env bash
# Phase 7 — strict smoke: real API/worker startup against ephemeral migrated DB.
# Requires GET /health=200 and GET /ready=200 (503 fails).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/release/_common.sh
source "${ROOT}/scripts/release/_common.sh"

release_require_cmd git curl
release_require_python
release_require_sha
release_ensure_sql_available
release_ensure_phase7_db "${PHASE7_SQL_DATABASE}"

release_log_stage "schema already at 0073 via clone; validate"
set +e
status_out="$(release_db_migrate validate 2>&1)"
status_ec=$?
set -e
echo "${status_out}"
[[ "${status_ec}" -eq 0 ]] || release_die "schema not compatible for smoke"
echo "${status_out}" | grep -q '"compatible": true' || release_die "schema not compatible for smoke"

SMOKE_PORT="${PHASE7_SMOKE_PORT:-18080}"
SMOKE_HOST="127.0.0.1"
BASE_URL="http://${SMOKE_HOST}:${SMOKE_PORT}"
API_PID=""
WORKER_PID=""
OUTPUT_DIR="${ROOT}/.tmp/phase7-smoke-output"
mkdir -p "${OUTPUT_DIR}"

cleanup() {
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
    wait "${API_PID}" 2>/dev/null || true
  fi
  if [[ -n "${WORKER_PID}" ]] && kill -0 "${WORKER_PID}" 2>/dev/null; then
    kill "${WORKER_PID}" 2>/dev/null || true
    wait "${WORKER_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

release_log_stage "start API (uvicorn)"
(
  cd "${ROOT}/backend"
  export DINAMIC_PYTEST_DOTENV_LOCKED=1
  export SQLSERVER_ENABLED=true
  export SQLSERVER_SERVER="${SQLSERVER_SERVER}"
  export SQLSERVER_DATABASE="${SQLSERVER_DATABASE}"
  export SQLSERVER_UID="${SQLSERVER_UID}"
  export SQLSERVER_PWD="${SQLSERVER_PWD}"
  export SQLSERVER_TRUST_SERVER_CERTIFICATE=yes
  export APP_ENV=development
  export V3_ALLOW_IN_MEMORY_FALLBACK=false
  export DB_SCHEMA_REQUIRED_VERSION=0073
  export EMBEDDED_WORKER_ENABLED=false
  export OUTPUT_DIR="${OUTPUT_DIR}"
  export GIT_SHA="${GIT_SHA}"
  export PYTHONPATH="${ROOT}/backend"
  exec "${RELEASE_PY}" -m uvicorn src.api.server:app --host "${SMOKE_HOST}" --port "${SMOKE_PORT}" --log-level warning
) &
API_PID=$!

release_log_stage "wait for /health and strict /ready=200"
ready=0
for i in $(seq 1 60); do
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    release_die "API process exited during startup"
  fi
  if curl -fsS "${BASE_URL}/health" >/tmp/phase7_smoke_health.json 2>/dev/null; then
    code="$(curl -s -o /tmp/phase7_smoke_ready.json -w '%{http_code}' "${BASE_URL}/ready")"
    if [[ "${code}" == "200" ]]; then
      ready=1
      break
    fi
    echo "ready_attempt=${i} ready_http=${code}"
  fi
  sleep 1
done
[[ "${ready}" -eq 1 ]] || release_die "API did not become ready (need /ready=200)"

health_code="$(curl -s -o /tmp/phase7_smoke_health.json -w '%{http_code}' "${BASE_URL}/health")"
ready_code="$(curl -s -o /tmp/phase7_smoke_ready.json -w '%{http_code}' "${BASE_URL}/ready")"
[[ "${health_code}" == "200" ]] || release_die "GET /health expected 200 got ${health_code}"
[[ "${ready_code}" == "200" ]] || release_die "GET /ready expected 200 got ${ready_code} (503 must fail smoke)"

"${RELEASE_PY}" - <<'PY'
import json
from pathlib import Path
health = json.loads(Path("/tmp/phase7_smoke_health.json").read_text())
ready = json.loads(Path("/tmp/phase7_smoke_ready.json").read_text())
assert health.get("ok") is True
assert health.get("schema_compatible") is True, health
assert health.get("repository_backend_healthy") is True, health
# configuration surfaced via schema + repository fields
assert ready.get("ok") is True, ready
print("health_body_ok schema_compatible repository_backend_healthy")
print("ready_body_ok")
PY

release_log_stage "metrics access"
metrics_code="$(curl -s -o /tmp/phase7_smoke_metrics.txt -w '%{http_code}' "${BASE_URL}/metrics")"
[[ "${metrics_code}" == "200" ]] || release_die "GET /metrics expected 200 got ${metrics_code}"

release_log_stage "SQL connectivity (already proven by /ready)"
release_db_migrate status >/tmp/phase7_smoke_mig_status.json
echo "migration_status=$(cat /tmp/phase7_smoke_mig_status.json)"

release_log_stage "worker import + short startup"
(
  cd "${ROOT}/backend"
  export DINAMIC_PYTEST_DOTENV_LOCKED=1
  export SQLSERVER_ENABLED=true
  export SQLSERVER_SERVER="${SQLSERVER_SERVER}"
  export SQLSERVER_DATABASE="${SQLSERVER_DATABASE}"
  export SQLSERVER_UID="${SQLSERVER_UID}"
  export SQLSERVER_PWD="${SQLSERVER_PWD}"
  export SQLSERVER_TRUST_SERVER_CERTIFICATE=yes
  export APP_ENV=development
  export V3_ALLOW_IN_MEMORY_FALLBACK=false
  export OUTPUT_DIR="${OUTPUT_DIR}"
  export PYTHONPATH="${ROOT}/backend"
  # Import worker entrypoint and run a bounded poll loop.
  exec "${RELEASE_PY}" - <<'PY'
import time
from pathlib import Path
from src.jobs.worker import worker_loop
stop_at = time.time() + 3
worker_loop(Path("."), stop=lambda: time.time() >= stop_at)
print("worker_startup_ok")
PY
) &
WORKER_PID=$!
wait "${WORKER_PID}"
WORKER_PID=""

release_log_stage "ops CLI smoke"
PYTHONPATH="${ROOT}:${ROOT}/backend" \
DINAMIC_PYTEST_DOTENV_LOCKED=1 \
"${RELEASE_PY}" -m scripts.ops.recover_job --help >/dev/null
PYTHONPATH="${ROOT}:${ROOT}/backend" \
DINAMIC_PYTEST_DOTENV_LOCKED=1 \
"${RELEASE_PY}" -m scripts.ops.inspect_aisle --help >/dev/null

release_log_stage "clean shutdown"
cleanup
trap - EXIT
API_PID=""
WORKER_PID=""

echo "SMOKE_OK"
echo "health=${health_code} ready=${ready_code} metrics=${metrics_code}"
echo "HEAD=${GIT_SHA}"
