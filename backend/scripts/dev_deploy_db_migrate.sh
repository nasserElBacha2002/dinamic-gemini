#!/usr/bin/env bash
# DEV OpenCloud deploy — database migrations inside the running API Compose service.
#
# Prerequisites (caller responsibility):
#   - Current directory: backend/ (or set BACKEND_ROOT).
#   - `docker-compose up -d` has started the api service.
#   - Compose loads ../.env via env_file (same DB credentials as the API).
#
# Environment:
#   AUTO_APPLY_DEV_MIGRATIONS          default true — when false, pending migrations abort deploy (exit 1).
#   RUN_MIGRATION_DOCTOR_ON_DEPLOY     default false — when true, run doctor before apply (memory-heavy).
#   DEV_DEPLOY_DB_MIGRATE_CHECK_ONLY   default false — preflight only; never runs apply.
#   DEV_MIGRATE_SERVICE                default api
#   COMPOSE                            default docker-compose (v1 standalone on OpenCloud server)
#
# Normal sequence:
#   config-check → status → [apply if pending] → validate → status (must be clean)
#
# CHECK_ONLY sequence (manual/server preflight before full GHA deploy):
#   docker-compose + api checks → exec ready → GCP secrets → config-check → status (capture/parse)
#   → validate → success summary (no apply, no doctor by default)
#
# Manual preflight:
#   cd backend
#   bash -n scripts/dev_deploy_db_migrate.sh
#   DEV_DEPLOY_DB_MIGRATE_CHECK_ONLY=true bash scripts/dev_deploy_db_migrate.sh
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
CHECK_ONLY="${DEV_DEPLOY_DB_MIGRATE_CHECK_ONLY:-false}"

is_check_only() {
  case "${CHECK_ONLY}" in
    true | 1 | yes | YES | True) return 0 ;;
    *) return 1 ;;
  esac
}

run_migrate() {
  echo "==> db_migrate.py $*" >&2
  ${COMPOSE} exec -T "${SERVICE}" python3 scripts/db_migrate.py "$@"
}

# stdout: JSON only (for command substitution). Human logs go to stderr.
run_migration_status_json() {
  local label="${1:-status}"
  echo "==> Running migration status (${label})..." >&2

  local output
  if ! output="$(${COMPOSE} exec -T "${SERVICE}" python3 scripts/db_migrate.py status)"; then
    echo "ERROR: db_migrate.py status failed (${label})." >&2
    return 1
  fi

  if [[ -z "$(printf '%s' "${output}" | tr -d '[:space:]')" ]]; then
    echo "ERROR: db_migrate.py status returned empty output (${label})." >&2
    return 1
  fi

  printf '%s\n' "${output}"
}

require_docker_compose() {
  echo "==> Checking docker-compose is available..." >&2
  if ! command -v "${COMPOSE%% *}" >/dev/null 2>&1; then
    echo "ERROR: ${COMPOSE} not found on PATH (install docker-compose v1 standalone on the server)." >&2
    exit 1
  fi
  if ! ${COMPOSE} version >/dev/null 2>&1; then
    echo "ERROR: ${COMPOSE} version check failed." >&2
    exit 1
  fi
}

require_api_service() {
  echo "==> Checking compose defines service '${SERVICE}'..." >&2
  local services
  if ! services="$(${COMPOSE} config --services 2>/dev/null)"; then
    echo "ERROR: ${COMPOSE} config --services failed (is docker-compose.yml valid?)." >&2
    exit 1
  fi
  if ! printf '%s\n' "${services}" | grep -Fxq "${SERVICE}"; then
    echo "ERROR: service '${SERVICE}' is not defined in docker-compose.yml" >&2
    printf '%s\n' "${services}" >&2
    exit 1
  fi
  echo "==> Checking '${SERVICE}' container is running..." >&2
  if ! ${COMPOSE} ps -q "${SERVICE}" 2>/dev/null | grep -q .; then
    echo "ERROR: ${SERVICE} container is not running. Start it with: ${COMPOSE} up -d" >&2
    ${COMPOSE} ps >&2 || true
    exit 1
  fi
}

wait_for_api_exec() {
  echo "==> Waiting for ${SERVICE} container to accept exec..." >&2
  local attempt
  for attempt in $(seq 1 45); do
    if ${COMPOSE} exec -T "${SERVICE}" python3 -c "pass" >/dev/null 2>&1; then
      echo "==> ${SERVICE} ready for exec (attempt ${attempt})" >&2
      return 0
    fi
    echo "==> ${SERVICE} not ready (attempt ${attempt}/45); sleeping 2s..." >&2
    sleep 2
  done
  echo "ERROR: ${SERVICE} container did not become ready for docker-compose exec within ~90s" >&2
  ${COMPOSE} ps >&2 || true
  ${COMPOSE} logs --tail=100 "${SERVICE}" >&2 || true
  return 1
}

# stdin must be migration status JSON (do not combine pipe with python3 - <<'PY' — heredoc wins stdin).
_python_read_status_json() {
  cat <<'PY'
import json
import os
import sys

label = os.environ.get("STATUS_LABEL", "status")
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

sys.stdout.write(json.dumps(data))
PY
}

pending_migration_count() {
  local json="$1"
  local label="${2:-initial}"
  export STATUS_LABEL="${label}"
  printf '%s' "${json}" | python3 -c "$(_python_read_status_json)" | python3 -c '
import json
import sys

data = json.load(sys.stdin)
print(len(data.get("pending_versions") or []))
'
}

_python_assert_status_clean() {
  cat <<'PY'
import json
import os
import sys

label = os.environ.get("STATUS_LABEL", "final")
data = json.load(sys.stdin)
pending = data.get("pending_versions") or []
compatible = data.get("compatible")
if pending:
    print(f"ERROR: {label} status has pending_versions={pending}", file=sys.stderr)
    sys.exit(1)
if not compatible:
    required = data.get("required_version")
    current = data.get("current_version")
    print(
        f"ERROR: {label} status not compatible "
        f"(required={required!r}, current={current!r})",
        file=sys.stderr,
    )
    sys.exit(1)
print(f"OK: {label} — no pending migrations, schema compatible")
PY
}

assert_status_clean() {
  local json="$1"
  local label="${2:-final}"
  export STATUS_LABEL="${label}"
  printf '%s' "${json}" | python3 -c "$(_python_read_status_json)" | STATUS_LABEL="${label}" python3 -c "$(_python_assert_status_clean)"
}

maybe_run_doctor() {
  if is_check_only; then
    echo "==> Skipping migration doctor in CHECK_ONLY mode." >&2
    return 0
  fi
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

run_gcp_secrets_preflight() {
  echo "==> Validating GCP credentials on host (if configured)..." >&2
  bash "${SCRIPT_DIR}/check_deploy_secrets.sh" host
  echo "==> Validating GCP credentials inside container (if configured)..." >&2
  bash "${SCRIPT_DIR}/check_deploy_secrets.sh" container
}

main_check_only() {
  echo "==> DEV deploy DB migrate CHECK_ONLY (preflight only — apply is disabled)" >&2

  require_docker_compose
  require_api_service
  wait_for_api_exec
  run_gcp_secrets_preflight

  echo "==> Running migration config-check..." >&2
  run_migrate config-check

  maybe_run_doctor

  local status_json pending_count
  status_json="$(run_migration_status_json preflight)"
  echo "==> Preflight migration status" >&2
  printf '%s\n' "${status_json}"
  pending_count="$(pending_migration_count "${status_json}" preflight)"
  echo "==> Parsed pending migration count (preflight): ${pending_count}" >&2

  echo "==> Running migration validate..." >&2
  run_migrate validate

  if [[ "${pending_count}" -gt 0 ]]; then
    echo "CHECK_ONLY OK: migration preflight passed; ${pending_count} pending migration(s) detected (apply was not run)." >&2
  else
    echo "CHECK_ONLY OK: migration preflight passed; no pending migrations; apply was not run." >&2
  fi
}

main_deploy_migrations() {
  require_docker_compose
  require_api_service
  wait_for_api_exec
  run_gcp_secrets_preflight

  echo "==> Running migration config-check..." >&2
  run_migrate config-check

  maybe_run_doctor

  local initial_status_json pending_count
  initial_status_json="$(run_migration_status_json initial)"
  echo "==> Initial migration status" >&2
  printf '%s\n' "${initial_status_json}"
  pending_count="$(pending_migration_count "${initial_status_json}" initial)"

  if [[ "${pending_count}" -gt 0 ]]; then
    echo "==> Pending migrations detected" >&2
    case "${AUTO_APPLY}" in
      true | 1 | yes | YES | True)
        echo "==> Applying pending DEV migrations..." >&2
        run_migrate apply
        ;;
      *)
        echo "ERROR: AUTO_APPLY_DEV_MIGRATIONS=${AUTO_APPLY} — pending migrations were NOT applied." >&2
        printf '%s\n' "${initial_status_json}" >&2
        exit 1
        ;;
    esac
  else
    echo "==> No pending migrations; skipping apply (apply would no-op)" >&2
  fi

  echo "==> Running migration validate..." >&2
  run_migrate validate

  local final_status_json
  final_status_json="$(run_migration_status_json final)"
  echo "==> Final migration status" >&2
  printf '%s\n' "${final_status_json}"
  assert_status_clean "${final_status_json}" post-deploy

  echo "==> DEV database migrations completed successfully" >&2
}

main() {
  if is_check_only; then
    main_check_only
  else
    main_deploy_migrations
  fi
}

main "$@"
