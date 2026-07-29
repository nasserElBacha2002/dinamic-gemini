#!/usr/bin/env bash
# Phase 7 — real E2E release validation against ephemeral migrated SQL + deterministic LLM.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/release/_common.sh
source "${ROOT}/scripts/release/_common.sh"

release_require_cmd git
release_require_python
release_require_sha
release_ensure_sql_available
release_ensure_phase7_db "${PHASE7_SQL_DATABASE}"

release_log_stage "schema ready for E2E"
release_index_0073_exists "${PHASE7_SQL_DATABASE}" || release_die "0073 index required for E2E"
set +e
val_out="$(release_db_migrate validate 2>&1)"
val_ec=$?
set -e
echo "${val_out}"
[[ "${val_ec}" -eq 0 ]] || release_die "schema validate failed for E2E"

OUTPUT_DIR="${ROOT}/.tmp/phase7-e2e-output"
mkdir -p "${OUTPUT_DIR}"
export OUTPUT_DIR
export PYTHONPATH="${ROOT}:${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"

release_log_stage "E2E pytest suite (SQL + fake provider scenarios)"
set +e
"${RELEASE_PY}" -m pytest \
  backend/tests/release/test_phase7_e2e_release.py \
  -q --no-cov -m release_e2e
E2E_EC=$?
set -e
echo "e2e_pytest_exit=${E2E_EC}"
[[ "${E2E_EC}" -eq 0 ]] || release_die "E2E pytest failed"

release_log_stage "API ready check on migrated DB"
SMOKE_PORT="${PHASE7_E2E_PORT:-18081}"
API_PID=""
cleanup() {
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
    wait "${API_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT
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
  export EMBEDDED_WORKER_ENABLED=false
  export DB_SCHEMA_REQUIRED_VERSION=0073
  export OUTPUT_DIR
  export GIT_SHA
  export PYTHONPATH="${ROOT}/backend"
  exec "${RELEASE_PY}" -m uvicorn src.api.server:app --host 127.0.0.1 --port "${SMOKE_PORT}" --log-level warning
) &
API_PID=$!
ready=0
for i in $(seq 1 60); do
  code="$(curl -s -o /tmp/phase7_e2e_ready.json -w '%{http_code}' "http://127.0.0.1:${SMOKE_PORT}/ready" || true)"
  if [[ "${code}" == "200" ]]; then
    ready=1
    break
  fi
  sleep 1
done
[[ "${ready}" -eq 1 ]] || release_die "E2E API /ready != 200"
cleanup
trap - EXIT
API_PID=""

echo "E2E_RELEASE_VALIDATION_OK"
echo "HEAD=${GIT_SHA}"
echo "database=${PHASE7_SQL_DATABASE}"
