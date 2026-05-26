#!/usr/bin/env bash
# DEV OpenCloud deploy — database migrations inside the running API Compose service.
#
# Prerequisites (caller responsibility):
#   - Current directory: backend/ (or set BACKEND_ROOT).
#   - `docker-compose up -d` has started the api service.
#   - Compose loads ../.env via env_file (same DB credentials as the API).
#
# Environment:
#   AUTO_APPLY_DEV_MIGRATIONS       default true — when false, pending migrations abort deploy (exit 1).
#   RUN_MIGRATION_DOCTOR_ON_DEPLOY  default false — when true, run doctor before apply (memory-heavy).
#   DEV_MIGRATE_SERVICE             default api
#   COMPOSE                         default docker-compose (v1 standalone on OpenCloud server)
#
# Sequence (default):
#   config-check → status → [apply if pending] → validate → status (must be clean)
#
# doctor is NOT run by default (same as config-check in CLI; skipped to avoid redundant work and
# extra memory use on small DEV hosts). Enable RUN_MIGRATION_DOCTOR_ON_DEPLOY=true for deep diagnostics.
#
# Do not run against production unless this script is explicitly wired into a prod deploy.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${BACKEND_ROOT}"

COMPOSE="${COMPOSE:-docker-compose}"
SERVICE="${DEV_MIGRATE_SERVICE:-api}"
AUTO_APPLY="${AUTO_APPLY_DEV_MIGRATIONS:-true}"
RUN_DOCTOR="${RUN_MIGRATION_DOCTOR_ON_DEPLOY:-false}"

run_migrate() {
  echo "==> db_migrate.py $*"
  ${COMPOSE} exec -T "${SERVICE}" python3 scripts/db_migrate.py "$@"
}

capture_status_json() {
  echo "==> Running migration status..."
  ${COMPOSE} exec -T "${SERVICE}" python3 scripts/db_migrate.py status
}

wait_for_api_exec() {
  echo "==> Waiting for ${SERVICE} container to accept exec..."
  local attempt
  for attempt in $(seq 1 45); do
    if ${COMPOSE} exec -T "${SERVICE}" python3 -c "pass" 2>/dev/null; then
      echo "==> ${SERVICE} ready for exec (attempt ${attempt})"
      return 0
    fi
    echo "==> ${SERVICE} not ready (attempt ${attempt}/45); sleeping 2s..."
    sleep 2
  done
  echo "ERROR: ${SERVICE} not ready for exec within ~90s" >&2
  ${COMPOSE} ps >&2 || true
  exit 1
}

json_has_pending() {
  local json="$1"
  STATUS_JSON="${json}" python3 - <<'PY'
import json
import os
import sys

data = json.loads(os.environ["STATUS_JSON"])
pending = data.get("pending_versions") or []
sys.exit(0 if pending else 1)
PY
}

assert_status_clean() {
  local json="$1"
  local label="${2:-final}"
  STATUS_JSON="${json}" STATUS_LABEL="${label}" python3 - <<'PY'
import json
import os
import sys

data = json.loads(os.environ["STATUS_JSON"])
label = os.environ.get("STATUS_LABEL", "final")
pending = data.get("pending_versions") or []
compatible = data.get("compatible")
if pending:
    print(f"ERROR: {label} status has pending_versions={pending}", file=sys.stderr)
    sys.exit(1)
if not compatible:
    print(
        f"ERROR: {label} status not compatible "
        f"(required={data.get('required_version')!r}, current={data.get('current_version')!r})",
        file=sys.stderr,
    )
    sys.exit(1)
print(f"OK: {label} — no pending migrations, schema compatible")
PY
}

maybe_run_doctor() {
  case "${RUN_DOCTOR}" in
    true | 1 | yes | YES | True)
      echo "WARNING: RUN_MIGRATION_DOCTOR_ON_DEPLOY=${RUN_DOCTOR} — running migration doctor (may be memory-intensive on small hosts)." >&2
      echo "==> Running migration doctor..."
      run_migrate doctor
      ;;
    *)
      echo "==> Skipping migration doctor during deploy. Run it manually for deep diagnostics:"
      echo "    ${COMPOSE} exec ${SERVICE} python3 scripts/db_migrate.py doctor"
      ;;
  esac
}

main() {
  wait_for_api_exec

  echo "==> Running migration config-check..."
  run_migrate config-check

  maybe_run_doctor

  echo "==> Initial migration status"
  initial_status="$(capture_status_json)"
  echo "${initial_status}"

  if json_has_pending "${initial_status}"; then
    echo "==> Pending migrations detected"
    case "${AUTO_APPLY}" in
      true | 1 | yes | YES | True)
        echo "==> Applying pending DEV migrations..."
        run_migrate apply
        ;;
      *)
        echo "ERROR: AUTO_APPLY_DEV_MIGRATIONS=${AUTO_APPLY} — pending migrations were NOT applied." >&2
        echo "${initial_status}" >&2
        exit 1
        ;;
    esac
  else
    echo "==> No pending migrations; skipping apply (apply would no-op)"
  fi

  echo "==> Running migration validate..."
  run_migrate validate

  echo "==> Final migration status"
  final_status="$(capture_status_json)"
  echo "${final_status}"
  assert_status_clean "${final_status}" "post-deploy"

  echo "==> DEV database migrations completed successfully"
}

main "$@"
