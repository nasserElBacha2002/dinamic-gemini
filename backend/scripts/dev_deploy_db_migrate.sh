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
  echo "==> db_migrate.py $*" >&2
  ${COMPOSE} exec -T "${SERVICE}" python3 scripts/db_migrate.py "$@"
}

# stdout: JSON only (for capture). Log lines go to stderr.
capture_status_json() {
  echo "==> Running migration status..." >&2
  ${COMPOSE} exec -T "${SERVICE}" python3 scripts/db_migrate.py status
}

log_migration_status() {
  local label="$1"
  local json="$2"
  echo "==> ${label} migration status" >&2
  printf '%s\n' "${json}"
}

# Prints pending_versions length to stdout. Exits non-zero on empty/invalid JSON.
pending_migration_count() {
  local json="$1"
  local label="${2:-initial}"
  printf '%s' "${json}" | STATUS_LABEL="${label}" python3 - <<'PY'
import json
import os
import sys

label = os.environ.get("STATUS_LABEL", "initial")
raw = sys.stdin.read().strip()
if not raw:
    print(f"ERROR: db_migrate.py status returned empty output ({label}).", file=sys.stderr)
    sys.exit(1)

try:
    data = json.loads(raw)
except json.JSONDecodeError as exc:
    print(f"ERROR: invalid JSON from db_migrate.py status ({label}): {exc}", file=sys.stderr)
    print("--- raw captured output ---", file=sys.stderr)
    print(raw, file=sys.stderr)
    print("--- end raw output ---", file=sys.stderr)
    sys.exit(1)

print(len(data.get("pending_versions") or []))
PY
}

assert_status_clean() {
  local json="$1"
  local label="${2:-final}"
  printf '%s' "${json}" | STATUS_LABEL="${label}" python3 - <<'PY'
import json
import os
import sys

label = os.environ.get("STATUS_LABEL", "final")
raw = sys.stdin.read().strip()
if not raw:
    print(f"ERROR: db_migrate.py status returned empty output ({label}).", file=sys.stderr)
    sys.exit(1)

try:
    data = json.loads(raw)
except json.JSONDecodeError as exc:
    print(f"ERROR: invalid JSON from db_migrate.py status ({label}): {exc}", file=sys.stderr)
    print("--- raw captured output ---", file=sys.stderr)
    print(raw, file=sys.stderr)
    print("--- end raw output ---", file=sys.stderr)
    sys.exit(1)

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
      echo "==> Running migration doctor..." >&2
      run_migrate doctor
      ;;
    *)
      echo "==> Skipping migration doctor during deploy. Run it manually for deep diagnostics:" >&2
      echo "    ${COMPOSE} exec ${SERVICE} python3 scripts/db_migrate.py doctor" >&2
      ;;
  esac
}

main() {
  wait_for_api_exec

  echo "==> Validating GCP credentials mount inside container (before migrations)..." >&2
  bash "${SCRIPT_DIR}/check_deploy_secrets.sh" container

  echo "==> Running migration config-check..." >&2
  run_migrate config-check

  maybe_run_doctor

  local initial_status
  initial_status="$(capture_status_json)"
  log_migration_status "Initial" "${initial_status}"

  local pending_count
  pending_count="$(pending_migration_count "${initial_status}" "initial")"

  if [[ "${pending_count}" -gt 0 ]]; then
    echo "==> Pending migrations detected" >&2
    case "${AUTO_APPLY}" in
      true | 1 | yes | YES | True)
        echo "==> Applying pending DEV migrations..." >&2
        run_migrate apply
        ;;
      *)
        echo "ERROR: AUTO_APPLY_DEV_MIGRATIONS=${AUTO_APPLY} — pending migrations were NOT applied." >&2
        printf '%s\n' "${initial_status}" >&2
        exit 1
        ;;
    esac
  else
    echo "==> No pending migrations; skipping apply (apply would no-op)" >&2
  fi

  echo "==> Running migration validate..." >&2
  run_migrate validate

  local final_status
  final_status="$(capture_status_json)"
  log_migration_status "Final" "${final_status}"
  assert_status_clean "${final_status}" "post-deploy"

  echo "==> DEV database migrations completed successfully" >&2
}

main "$@"
