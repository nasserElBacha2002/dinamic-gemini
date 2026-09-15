#!/usr/bin/env bash
# Lab status: compose, SQL connectivity, optional API attestation.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

lab_load_env

echo "==> Docker compose ps"
lab_compose ps || true

echo "==> SQL connectivity"
if lab_sqlcmd_in_container "SELECT DB_NAME()" >/dev/null 2>&1; then
  echo "SQL: OK (container sqlcmd)"
else
  echo "SQL: FAIL (container not ready or sqlcmd missing)"
fi

API_HOST="${LAB_API_HOST:-127.0.0.1}"
API_PORT="${LAB_API_PORT:-18080}"
ATT_URL="http://${API_HOST}:${API_PORT}/lab/health"
RUN_ID="${LAB_RUN_ID:-status-check}"

echo "==> Attestation probe ${ATT_URL}?audit_run_id=${RUN_ID}"
if command -v curl >/dev/null 2>&1; then
  if curl -fsS --max-time 3 "${ATT_URL}?audit_run_id=${RUN_ID}" 2>/dev/null; then
    echo
    echo "Attestation: OK"
  else
    echo "Attestation: API not up or gate failed (expected if uvicorn not running)"
  fi
else
  echo "curl not found; skip attestation HTTP probe"
fi
