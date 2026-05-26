#!/usr/bin/env bash
# Static checks for check_deploy_secrets.sh (no Docker required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${ROOT}/check_deploy_secrets.sh"

bash -n "${TARGET}"

for needle in \
  "ensure-override" \
  "check_host" \
  "check_container" \
  "GOOGLE_APPLICATION_CREDENTIALS" \
  "docker-compose.override.example.yml" \
  "backend/secrets" \
  "test -f"; do
  if ! grep -q "${needle}" "${TARGET}"; then
    echo "missing expected content: ${needle}" >&2
    exit 1
  fi
done

echo "check_deploy_secrets.sh static checks OK"
