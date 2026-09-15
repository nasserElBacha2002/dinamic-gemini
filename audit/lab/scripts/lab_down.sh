#!/usr/bin/env bash
# Stop lab compose. Pass --purge to remove the named SQL volume (destructive).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

PURGE=false
for arg in "$@"; do
  case "${arg}" in
    --purge) PURGE=true ;;
    -h | --help)
      echo "Usage: $0 [--purge]"
      exit 0
      ;;
    *) lab_die "Unknown argument: ${arg}" ;;
  esac
done

if [[ -f "${LAB_ENV_FILE}" ]]; then
  lab_load_env
else
  echo "WARN: ${LAB_ENV_FILE} missing; stopping compose without env file checks"
fi

echo "==> Stopping lab compose..."
if [[ -f "${LAB_ENV_FILE}" ]]; then
  lab_compose down
else
  docker compose -f "${LAB_COMPOSE_FILE}" --project-name "${COMPOSE_PROJECT_NAME}" down
fi

if [[ "${PURGE}" == true ]]; then
  echo "==> Purging volume dinamic-gemini-lab-sql-data (explicit --purge)"
  docker volume rm dinamic-gemini-lab-sql-data 2>/dev/null || echo "Volume already absent"
fi

echo "OK: lab down"
