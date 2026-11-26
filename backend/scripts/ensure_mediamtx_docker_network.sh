#!/usr/bin/env bash
# Idempotently create the shared MediaMTX ↔ API Docker bridge (DIN-508).
set -euo pipefail

NET="${MEDIAMTX_DOCKER_NETWORK:-dinamic-mediamtx-poc-net}"

if docker network inspect "${NET}" >/dev/null 2>&1; then
  echo "ensure_mediamtx_network: ${NET} already exists"
  exit 0
fi

docker network create --driver bridge "${NET}"
echo "ensure_mediamtx_network: created ${NET}"