#!/usr/bin/env bash
# Local sanity check for CI-1.3.3 — copies compose to /tmp and runs patch script (does not modify repo file).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT
cp "${ROOT}/docker-compose.yml" "${TMP}"
HOST_PORT="${HOST_PORT:-8001}"
echo "Patching temp file ${TMP} -> host port ${HOST_PORT}"
python3 "${ROOT}/scripts/patch_compose_host_port.py" --compose "${TMP}" --host-port "${HOST_PORT}"
echo "--- relevant lines ---"
grep -nE "8000|${HOST_PORT}" "${TMP}" || true
