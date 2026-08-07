#!/usr/bin/env bash
# Full audit commands for dinamic-gemini (after reviewing inventory/config).
# Run from dinamic-gemini with security-agents on PYTHONPATH.
set -euo pipefail
GEMINI_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SA_ROOT="${SA_ROOT:-$HOME/Documents/Dinamic sistems/dinamic-security-agents}"
export PYTHONPATH="${SA_ROOT}/security-agents:${PYTHONPATH:-}"
CFG="$GEMINI_ROOT/security-audit.yaml"
cd "$GEMINI_ROOT"

python -m security_agents config validate --project-root . --config "$CFG"
INIT=$(python -m security_agents init --project-root . --config "$CFG" --json)
RUN_ID=$(python -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' <<<"$INIT")
export RUN_ID
export DAST_BASE_URL="${DAST_BASE_URL:-http://127.0.0.1:8000}"
export DAST_ACTIVE_CONFIRMATION="CONFIRM_ACTIVE_DAST_${RUN_ID}"
export DAST_INJECTION_CONFIRMATION="CONFIRM_INJECTION_DAST_${RUN_ID}"
# Synthetic JWTs (never commit real tokens):
# export DAST_TOKEN_PLATFORM_ADMIN=...
# export DAST_TOKEN_COMPANY_ADMIN_A=...
# export DAST_TOKEN_COMPANY_ADMIN_B=...
# export DAST_TOKEN_OPERATOR_A=...
# export DAST_TOKEN_OPERATOR_B=...
# export DAST_TOKEN_INVALID=not-a-jwt

python -m security_agents discover --project-root . --config "$CFG" --run-id "$RUN_ID"
python -m security_agents sast plan --project-root . --config "$CFG" --run-id "$RUN_ID"
python -m security_agents sast run --project-root . --config "$CFG" --run-id "$RUN_ID"
python -m security_agents dast plan --project-root . --config "$CFG" --run-id "$RUN_ID"
python -m security_agents dast suites list --project-root . --config "$CFG" --run-id "$RUN_ID" || true
python -m security_agents dast passive --project-root . --config "$CFG" --run-id "$RUN_ID"
python -m security_agents dast active --project-root . --config "$CFG" --run-id "$RUN_ID"
python -m security_agents dast authz --project-root . --config "$CFG" --run-id "$RUN_ID" || true
python -m security_agents report --project-root . --config "$CFG" --run-id "$RUN_ID"
python -m security_agents validate --project-root . --config "$CFG" --run-id "$RUN_ID"
echo "RUN_ID=$RUN_ID"
