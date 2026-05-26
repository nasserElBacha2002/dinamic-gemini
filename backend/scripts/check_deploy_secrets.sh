#!/usr/bin/env bash
# DEV deploy — validate GCP credentials file exists on host and inside the api container.
#
# Usage (from backend/):
#   ./scripts/check_deploy_secrets.sh ensure-override   # create override from example if needed
#   ./scripts/check_deploy_secrets.sh host              # before docker-compose up
#   ./scripts/check_deploy_secrets.sh container         # after api is up (before migrations)
#
# Does not print secret contents. Never commit gcp-service-account.json.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_ROOT}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
COMPOSE="${COMPOSE:-docker-compose}"
SERVICE="${DEV_MIGRATE_SERVICE:-api}"

HOST_REPO_SECRET="${REPO_ROOT}/secrets/gcp-service-account.json"
HOST_BACKEND_SECRET="${BACKEND_ROOT}/secrets/gcp-service-account.json"
CONTAINER_DEFAULT_PATH="/app/secrets/gcp-service-account.json"
OVERRIDE_FILE="${BACKEND_ROOT}/docker-compose.override.yml"
OVERRIDE_EXAMPLE="${BACKEND_ROOT}/docker-compose.override.example.yml"

read_env_var() {
  local key="$1"
  if [[ ! -f "${ENV_FILE}" ]]; then
    return 1
  fi
  local line
  line="$(grep -E "^[[:space:]]*${key}=" "${ENV_FILE}" | tail -n 1 || true)"
  [[ -n "${line}" ]] || return 1
  local value="${line#*=}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "${value}"
}

gcp_creds_required() {
  local creds provider
  creds="$(read_env_var GOOGLE_APPLICATION_CREDENTIALS 2>/dev/null || true)"
  provider="$(read_env_var ARTIFACT_STORAGE_PROVIDER 2>/dev/null || true)"
  provider="${provider,,}"
  if [[ -n "${creds}" && "${creds}" == /app/secrets/* ]]; then
    return 0
  fi
  if [[ "${provider}" == "gcs" && -n "${creds}" ]]; then
    return 0
  fi
  return 1
}

resolve_container_creds_path() {
  local creds
  creds="$(read_env_var GOOGLE_APPLICATION_CREDENTIALS 2>/dev/null || true)"
  if [[ -n "${creds}" ]]; then
    printf '%s' "${creds}"
    return 0
  fi
  printf '%s' "${CONTAINER_DEFAULT_PATH}"
}

print_mount_fix_message() {
  local creds_path="$1"
  cat >&2 <<EOF
ERROR: GOOGLE_APPLICATION_CREDENTIALS is set to ${creds_path} but the file is not available for the api service.

Expected on the host (at least one):
  ${HOST_BACKEND_SECRET}
  ${HOST_REPO_SECRET}

Expected inside the container:
  ${creds_path}

If the key lives under backend/secrets/, create a server-local override (not committed):
  cp docker-compose.override.example.yml docker-compose.override.yml

  services:
    api:
      volumes:
        - ./secrets:/app/secrets:ro

The main compose file already mounts repo-root secrets when the key is at:
  secrets/gcp-service-account.json  (→ ../secrets:/app/secrets in docker-compose.yml)

Place the JSON on the server, ensure the mount, then rerun deploy.

Manual checks:
  cd backend
  ls -la secrets/gcp-service-account.json
  ls -la ../secrets/gcp-service-account.json
  docker-compose exec api ls -la ${creds_path}
EOF
}

host_secret_exists() {
  [[ -f "${HOST_BACKEND_SECRET}" || -f "${HOST_REPO_SECRET}" ]]
}

ensure_override() {
  if [[ -f "${HOST_BACKEND_SECRET}" && ! -f "${OVERRIDE_FILE}" && -f "${OVERRIDE_EXAMPLE}" ]]; then
    cp "${OVERRIDE_EXAMPLE}" "${OVERRIDE_FILE}"
    echo "==> Created ${OVERRIDE_FILE} from example (mounts ./secrets → /app/secrets)"
  elif [[ -f "${OVERRIDE_FILE}" ]]; then
    echo "==> Using existing ${OVERRIDE_FILE}"
  else
    echo "==> No ${OVERRIDE_FILE} (optional; repo-root secrets/ mount may be enough)"
  fi
}

check_host() {
  if ! gcp_creds_required; then
    echo "==> GCP container secrets check skipped (GOOGLE_APPLICATION_CREDENTIALS not set to /app/secrets/ and ARTIFACT_STORAGE_PROVIDER is not gcs)"
    return 0
  fi

  local creds_path
  creds_path="$(resolve_container_creds_path)"
  echo "==> Checking host GCP secret files for container path ${creds_path}..."

  if host_secret_exists; then
    if [[ -f "${HOST_BACKEND_SECRET}" ]]; then
      echo "OK: found ${HOST_BACKEND_SECRET}"
    fi
    if [[ -f "${HOST_REPO_SECRET}" ]]; then
      echo "OK: found ${HOST_REPO_SECRET}"
    fi
    return 0
  fi

  print_mount_fix_message "${creds_path}"
  exit 1
}

check_container() {
  if ! gcp_creds_required; then
    echo "==> GCP container secrets check skipped"
    return 0
  fi

  local creds_path
  creds_path="$(resolve_container_creds_path)"
  echo "==> Checking GCP credentials inside ${SERVICE} container: ${creds_path}"

  if ${COMPOSE} exec -T "${SERVICE}" test -f "${creds_path}"; then
    echo "OK: ${creds_path} exists inside ${SERVICE}"
    return 0
  fi

  print_mount_fix_message "${creds_path}"
  exit 1
}

main() {
  cd "${BACKEND_ROOT}"
  local cmd="${1:-}"
  case "${cmd}" in
    ensure-override)
      ensure_override
      ;;
    host)
      ensure_override
      check_host
      ;;
    container)
      check_container
      ;;
    "")
      ensure_override
      check_host
      check_container
      ;;
    *)
      echo "Usage: $0 {ensure-override|host|container}" >&2
      exit 2
      ;;
  esac
}

main "$@"
