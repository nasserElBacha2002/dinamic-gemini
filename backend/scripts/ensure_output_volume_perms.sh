#!/usr/bin/env bash
# Ensure host bind-mount data/output is writable by the API container user (appuser uid/gid 10001).
#
# docker-compose mounts ../data/output → /app/output. If that host dir is root-owned
# (common after first docker create), on-demand workers fail with:
#   WORKER_LAUNCH_FAILED: [Errno 13] Permission denied: 'output/<job_id>'
#
# Usage (from backend/):
#   bash scripts/ensure_output_volume_perms.sh
# Or with explicit repo root:
#   bash scripts/ensure_output_volume_perms.sh /opt/dinamic/dinamic-gemini

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="${1:-$(cd "${BACKEND_DIR}/.." && pwd)}"
OUT_DIR="${REPO_ROOT}/data/output"
APPUSER_UID="${APPUSER_UID:-10001}"
APPUSER_GID="${APPUSER_GID:-10001}"

echo "==> Ensuring output volume exists and is owned by ${APPUSER_UID}:${APPUSER_GID}"
echo "    host path: ${OUT_DIR}"

mkdir -p "${OUT_DIR}"

# Prefer docker (no host sudo) when available — works if the operator is in the docker group.
if command -v docker >/dev/null 2>&1; then
  docker run --rm \
    -v "${OUT_DIR}:/out" \
    alpine:3.20 \
    chown -R "${APPUSER_UID}:${APPUSER_GID}" /out
elif chown -R "${APPUSER_UID}:${APPUSER_GID}" "${OUT_DIR}" 2>/dev/null; then
  :
else
  echo "ERROR: could not chown ${OUT_DIR} to ${APPUSER_UID}:${APPUSER_GID}." >&2
  echo "Run as a user that can use docker, or: sudo chown -R ${APPUSER_UID}:${APPUSER_GID} ${OUT_DIR}" >&2
  exit 1
fi

# Best-effort write probe without needing a running api container.
if touch "${OUT_DIR}/.dinamic_write_probe" 2>/dev/null; then
  rm -f "${OUT_DIR}/.dinamic_write_probe"
  echo "OK: host path is writable after ownership fix"
else
  echo "WARN: host path still not writable by current user (container appuser should still be able to write)." >&2
fi
