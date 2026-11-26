#!/usr/bin/env bash
# Attach the running API container to MediaMTX (DIN-508) for internal HLS + status API DNS.
# Idempotent — safe to run after every compose up / deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NET="${MEDIAMTX_DOCKER_NETWORK:-dinamic-mediamtx-poc-net}"

cd "${ROOT}"

if command -v docker-compose >/dev/null 2>&1; then
  CID="$(docker-compose ps -q api 2>/dev/null || true)"
else
  CID="$(docker compose ps -q api 2>/dev/null || true)"
fi

if [ -z "${CID}" ]; then
  echo "attach_mediamtx_network: api container not running; skip"
  exit 0
fi

if ! docker network inspect "${NET}" >/dev/null 2>&1; then
  echo "attach_mediamtx_network: network ${NET} not found; skip"
  exit 0
fi

if docker network connect "${NET}" "${CID}" 2>/dev/null; then
  echo "attach_mediamtx_network: connected ${CID} to ${NET}"
else
  echo "attach_mediamtx_network: already on ${NET} (or connect declined)"
fi