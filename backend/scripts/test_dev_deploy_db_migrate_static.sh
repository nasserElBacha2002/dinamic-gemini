#!/usr/bin/env bash
# Static checks for dev_deploy_db_migrate.sh (no Docker required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${ROOT}/dev_deploy_db_migrate.sh"

bash -n "${TARGET}"

for needle in \
  "set -euo pipefail" \
  "config-check" \
  "RUN_MIGRATION_DOCTOR_ON_DEPLOY" \
  "Skipping migration doctor during deploy" \
  "wait_for_api_exec" \
  "run_migration_status_json" \
  "Running migration status" \
  ">&2" \
  "sys.stdin.read" \
  "pending_migration_count" \
  "empty output" \
  "status" \
  "apply" \
  "validate" \
  "AUTO_APPLY_DEV_MIGRATIONS" \
  "DEV_DEPLOY_DB_MIGRATE_CHECK_ONLY" \
  "main_check_only" \
  "CHECK_ONLY OK" \
  "require_docker_compose" \
  "require_api_service" \
  "exec -T" \
  "pending_versions" \
  "compatible"; do
  if ! grep -q "${needle}" "${TARGET}"; then
    echo "missing expected content: ${needle}" >&2
    exit 1
  fi
done

if grep -q 'run_migrate doctor' "${TARGET}" && ! grep -q 'maybe_run_doctor' "${TARGET}"; then
  echo "doctor must only run via maybe_run_doctor (optional flag)" >&2
  exit 1
fi

if ! grep -q 'run_migrate apply' "${TARGET}"; then
  echo "missing run_migrate apply for deploy path" >&2
  exit 1
fi

# CHECK_ONLY path must not invoke apply
if awk '/^main_check_only\(\)/,/^}/' "${TARGET}" | grep -q 'run_migrate apply'; then
  echo "main_check_only must not call run_migrate apply" >&2
  exit 1
fi

echo "dev_deploy_db_migrate.sh static checks OK"
