#!/usr/bin/env bash
# OpenCloud DEV — recreate backend API with DIN-508 MediaMTX network overlay when live stream is enabled.
# Invoked after git reset to origin/develop (GHA or manual). Single source of truth for server deploy steps.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/dinamic/dinamic-gemini}"
BACKEND_HOST_PORT="${BACKEND_HOST_PORT:-8001}"
NET="${MEDIAMTX_DOCKER_NETWORK:-dinamic-mediamtx-poc-net}"

live_stream_enabled() {
  grep -qE '^[[:space:]]*LIVE_STREAM_ENABLED=(true|1|yes)' "${REPO_ROOT}/.env" 2>/dev/null
}

compose_files_array() {
  local -a files=(-f docker-compose.yml)
  if [ -f "${REPO_ROOT}/backend/docker-compose.override.yml" ]; then
    files+=(-f docker-compose.override.yml)
  fi
  if live_stream_enabled; then
    if [ ! -f "${REPO_ROOT}/backend/docker-compose.mediamtx-network.yml" ]; then
      echo "opencloud_deploy_api: ERROR — LIVE_STREAM_ENABLED but missing docker-compose.mediamtx-network.yml" >&2
      exit 1
    fi
    files+=(-f docker-compose.mediamtx-network.yml)
  fi
  printf '%s\n' "${files[@]}"
}

if [ ! -d "${REPO_ROOT}" ]; then
  echo "opencloud_deploy_api: missing repo ${REPO_ROOT}" >&2
  exit 1
fi
if [ ! -f "${REPO_ROOT}/.env" ]; then
  echo "opencloud_deploy_api: missing ${REPO_ROOT}/.env" >&2
  exit 1
fi
if ! command -v docker-compose >/dev/null 2>&1; then
  echo "opencloud_deploy_api: docker-compose not on PATH" >&2
  exit 1
fi

export BACKEND_HOST_PORT
export COMPOSE_INTERACTIVE_NO=1

cd "${REPO_ROOT}/backend"

chmod +x scripts/check_deploy_secrets.sh scripts/dev_deploy_db_migrate.sh scripts/ensure_output_volume_perms.sh \
  scripts/ensure_mediamtx_docker_network.sh scripts/smoke_live_stream_infrastructure.sh 2>/dev/null || true

python3 scripts/patch_compose_host_port.py \
  --compose "${REPO_ROOT}/backend/docker-compose.yml" \
  --host-port "${BACKEND_HOST_PORT}"

echo "==> GCP secrets preflight..."
bash scripts/check_deploy_secrets.sh ensure-override
bash scripts/check_deploy_secrets.sh host
bash scripts/ensure_output_volume_perms.sh "${REPO_ROOT}"

mapfile -t COMPOSE_FILES < <(compose_files_array)
if live_stream_enabled; then
  echo "opencloud_deploy_api: LIVE_STREAM_ENABLED — compose files: ${COMPOSE_FILES[*]}"
  bash scripts/ensure_mediamtx_docker_network.sh
else
  echo "opencloud_deploy_api: LIVE_STREAM_ENABLED not set — default compose only"
fi

echo "==> Building API image..."
docker-compose "${COMPOSE_FILES[@]}" build api

if docker-compose "${COMPOSE_FILES[@]}" ps -q api 2>/dev/null | grep -q .; then
  echo "==> Recreating API (same compose project, MediaMTX stack untouched)..."
  docker-compose "${COMPOSE_FILES[@]}" rm -sf api 2>/dev/null || true
  docker-compose "${COMPOSE_FILES[@]}" up -d --no-deps --build api
else
  echo "==> First API start..."
  docker-compose "${COMPOSE_FILES[@]}" up -d --build api
fi

docker-compose "${COMPOSE_FILES[@]}" ps
bash scripts/check_deploy_secrets.sh container

export AUTO_APPLY_DEV_MIGRATIONS="${AUTO_APPLY_DEV_MIGRATIONS:-true}"
export RUN_MIGRATION_DOCTOR_ON_DEPLOY="${RUN_MIGRATION_DOCTOR_ON_DEPLOY:-false}"
bash "${REPO_ROOT}/backend/scripts/dev_deploy_db_migrate.sh"

ok=0
for i in $(seq 1 45); do
  if curl -sfS --connect-timeout 5 --max-time 15 "http://127.0.0.1:${BACKEND_HOST_PORT}/health" >/dev/null; then
    ok=1
    break
  fi
  echo "opencloud_deploy_api: /health attempt ${i}/45..."
  sleep 3
done
if [ "${ok}" -ne 1 ]; then
  echo "opencloud_deploy_api: ERROR — /health failed" >&2
  exit 1
fi
echo "opencloud_deploy_api: /health OK"

bash scripts/smoke_live_stream_infrastructure.sh

if live_stream_enabled; then
  nets="$(docker inspect backend_api_1 --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null || true)"
  if ! grep -q "${NET}" <<< "${nets}"; then
    echo "opencloud_deploy_api: ERROR — api not on ${NET} (networks=${nets})" >&2
    exit 1
  fi
  if ! docker exec backend_api_1 getent hosts dinamic-mediamtx-poc >/dev/null 2>&1; then
    echo "opencloud_deploy_api: ERROR — dinamic-mediamtx-poc not resolvable in api" >&2
    exit 1
  fi
  echo "opencloud_deploy_api: OK api on ${NET}, DNS dinamic-mediamtx-poc"
fi

echo "opencloud_deploy_api: deploy complete (sha=$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown))"