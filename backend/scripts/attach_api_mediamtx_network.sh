#!/usr/bin/env bash
# Attach the running API container to MediaMTX (DIN-508) for internal HLS + status API DNS.
# Idempotent — safe to run after every compose up / deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NET="${MEDIAMTX_DOCKER_NETWORK:-dinamic-mediamtx-poc-net}"
MEDIAMTX_HOST="${MEDIAMTX_DOCKER_HOSTNAME:-dinamic-mediamtx-poc}"

cd "${ROOT}"

resolve_api_cid() {
  local cid=""
  if command -v docker-compose >/dev/null 2>&1; then
    cid="$(docker-compose ps -q api 2>/dev/null || true)"
  else
    cid="$(docker compose ps -q api 2>/dev/null || true)"
  fi
  if [ -n "${cid}" ]; then
    echo "${cid}"
    return 0
  fi
  cid="$(docker ps -q \
    --filter "label=com.docker.compose.service=api" \
    --filter "name=backend" 2>/dev/null | head -1 || true)"
  if [ -n "${cid}" ]; then
    echo "${cid}"
    return 0
  fi
  return 1
}

if ! docker network inspect "${NET}" >/dev/null 2>&1; then
  echo "attach_mediamtx_network: network ${NET} not found; skip"
  exit 0
fi

CID=""
for attempt in $(seq 1 15); do
  if CID="$(resolve_api_cid)"; then
    break
  fi
  echo "attach_mediamtx_network: waiting for api container (${attempt}/15)..."
  sleep 2
done

if [ -z "${CID}" ]; then
  echo "attach_mediamtx_network: ERROR — api container not running (MediaMTX network ${NET} exists)" >&2
  exit 1
fi

if docker network connect "${NET}" "${CID}" 2>/dev/null; then
  echo "attach_mediamtx_network: connected ${CID} to ${NET}"
else
  echo "attach_mediamtx_network: already on ${NET} (or connect declined)"
fi

if ! docker exec "${CID}" getent hosts "${MEDIAMTX_HOST}" >/dev/null 2>&1; then
  echo "attach_mediamtx_network: ERROR — ${MEDIAMTX_HOST} not resolvable inside api container" >&2
  exit 1
fi

echo "attach_mediamtx_network: OK (${MEDIAMTX_HOST} resolvable)"