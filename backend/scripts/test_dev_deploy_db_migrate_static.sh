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
  "capture_status_json" \
  "Running migration status" \
  ">&2" \
  "sys.stdin.read" \
  "pending_migration_count" \
  "empty output" \
  "status" \
  "apply" \
  "validate" \
  "AUTO_APPLY_DEV_MIGRATIONS" \
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

echo "dev_deploy_db_migrate.sh static checks OK"
