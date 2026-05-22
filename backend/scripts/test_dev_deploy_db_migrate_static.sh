#!/usr/bin/env bash
# Static checks for dev_deploy_db_migrate.sh (no Docker required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${ROOT}/dev_deploy_db_migrate.sh"

bash -n "${TARGET}"

for needle in \
  "set -euo pipefail" \
  "config-check" \
  "doctor" \
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

echo "dev_deploy_db_migrate.sh static checks OK"
