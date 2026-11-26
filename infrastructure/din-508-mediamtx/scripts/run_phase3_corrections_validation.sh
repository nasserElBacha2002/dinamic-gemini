#!/usr/bin/env bash
# DIN-508 Phase 3 corrections — optional RTMP/HLS smoke (sanitized output).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EVIDENCE_DIR="${ROOT}/../../DIN-508/phase-3/corrections"
mkdir -p "$EVIDENCE_DIR"
OUT="${EVIDENCE_DIR}/implementation-corrections-tests.txt"

{
  echo "=== phase3 corrections validation ==="
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "--- backend unit (live_stream) ---"
  (cd "${ROOT}/../../backend" && .venv/bin/pytest tests/unit/live_stream -q --tb=line --no-cov)
  echo ""
  echo "--- MediaMTX authHTTP probe ---"
  API="${API_BASE:-http://127.0.0.1:8000}"
  SECRET="${MEDIAMTX_HTTP_AUTH_SECRET:-}"
  if [[ -z "$SECRET" ]]; then
    echo "SKIP: MEDIAMTX_HTTP_AUTH_SECRET unset"
  else
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    "${API}/api/internal/mediamtx/auth?mtx_key=${SECRET}" \
    -H "Content-Type: application/json" \
    -d '{"user":"bad","password":"bad","path":"live/x/y","action":"read"}' || true)
    echo "invalid_credentials_http_status=${CODE}"
  fi
  echo ""
  echo "--- optional FFmpeg publish (set RUN_FFMPEG_SMOKE=1) ---"
  if [[ "${RUN_FFMPEG_SMOKE:-0}" != "1" ]]; then
    echo "SKIP: RUN_FFMPEG_SMOKE not set"
  elif ! command -v ffmpeg >/dev/null; then
    echo "SKIP: ffmpeg not found"
  else
    echo "FFmpeg smoke configured but path/credentials must be supplied by operator — not auto-run."
  fi
} | tee "$OUT"
echo "wrote ${OUT}"