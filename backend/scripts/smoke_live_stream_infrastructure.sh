#!/usr/bin/env bash
# Post-deploy smoke for DIN-508 live stream infrastructure (no active publisher required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/../.env"
NET="${MEDIAMTX_DOCKER_NETWORK:-dinamic-mediamtx-poc-net}"
MEDIAMTX_HOST="${MEDIAMTX_DOCKER_HOSTNAME:-dinamic-mediamtx-poc}"
API_ALIAS="${MEDIAMTX_API_DOCKER_ALIAS:-dinamic-backend-api}"

live_enabled() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    return 1
  fi
  local v
  v="$(grep -E '^[[:space:]]*LIVE_STREAM_ENABLED=' "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
  [[ "${v}" == "true" || "${v}" == "1" || "${v}" == "yes" ]]
}

resolve_api_cid() {
  local cid=""
  if command -v docker-compose >/dev/null 2>&1; then
    cid="$(docker-compose -f "${ROOT}/docker-compose.yml" ps -q api 2>/dev/null || true)"
  fi
  if [ -z "${cid}" ] && command -v docker >/dev/null 2>&1; then
    cid="$(docker ps -q --filter "label=com.docker.compose.service=api" --filter "name=backend" 2>/dev/null | head -1 || true)"
  fi
  echo "${cid}"
}

if ! live_enabled; then
  echo "smoke_live_stream: LIVE_STREAM_ENABLED not true — skip"
  exit 0
fi

echo "smoke_live_stream: LIVE_STREAM_ENABLED — running infrastructure checks"

if ! docker network inspect "${NET}" >/dev/null 2>&1; then
  echo "smoke_live_stream: ERROR — Docker network ${NET} missing" >&2
  exit 1
fi
echo "smoke_live_stream: OK network ${NET} exists"

CID="$(resolve_api_cid)"
if [ -z "${CID}" ]; then
  echo "smoke_live_stream: ERROR — api container not running" >&2
  exit 1
fi

if ! docker inspect "${CID}" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' | grep -q "${NET}"; then
  echo "smoke_live_stream: ERROR — api container not on ${NET}" >&2
  exit 1
fi
echo "smoke_live_stream: OK api joined ${NET}"

if ! docker exec "${CID}" getent hosts "${MEDIAMTX_HOST}" >/dev/null 2>&1; then
  echo "smoke_live_stream: ERROR — ${MEDIAMTX_HOST} not resolvable in api" >&2
  exit 1
fi
echo "smoke_live_stream: OK DNS ${MEDIAMTX_HOST} from api"

# Any HTTP response from HLS listener ⇒ TCP + listener up (empty path may 401/404).
hls_code="$(docker exec -e MEDIAMTX_HOST="${MEDIAMTX_HOST}" "${CID}" python3 - <<'PY' 2>/dev/null || echo "000"
import os
import urllib.error
import urllib.request

host = os.environ.get("MEDIAMTX_HOST", "dinamic-mediamtx-poc")
url = f"http://{host}:8888/"
try:
    with urllib.request.urlopen(url, timeout=5) as r:
        print(r.status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception:
    print("000")
PY
)"
if [[ "${hls_code}" == "000" ]]; then
  echo "smoke_live_stream: ERROR — no HTTP response from ${MEDIAMTX_HOST}:8888" >&2
  exit 1
fi
echo "smoke_live_stream: OK HLS HTTP response code=${hls_code}"

mtx_cid="$(docker ps -q --filter "name=${MEDIAMTX_HOST}" 2>/dev/null | head -1 || true)"
if [ -n "${mtx_cid}" ]; then
  if ! docker inspect "${mtx_cid}" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' | grep -q "${NET}"; then
    echo "smoke_live_stream: ERROR — MediaMTX not on ${NET}" >&2
    exit 1
  fi
  echo "smoke_live_stream: OK MediaMTX on ${NET}"
  if docker exec "${mtx_cid}" getent hosts "${API_ALIAS}" >/dev/null 2>&1; then
    echo "smoke_live_stream: OK DNS ${API_ALIAS} from MediaMTX"
  else
    echo "smoke_live_stream: WARN — ${API_ALIAS} not resolvable from MediaMTX (authHTTP may use host.docker.internal)"
  fi
  # Control API on loopback inside MediaMTX (admin excluded from authHTTP for 127.0.0.1).
  if docker exec "${mtx_cid}" /bin/wget -q --spider "http://127.0.0.1:9997/v3/config/global/get" 2>/dev/null; then
    echo "smoke_live_stream: OK MediaMTX control API (localhost)"
  else
    echo "smoke_live_stream: ERROR — MediaMTX control API not healthy on 127.0.0.1:9997" >&2
    exit 1
  fi
else
  echo "smoke_live_stream: WARN — container ${MEDIAMTX_HOST} not running (inventory unaffected)"
fi

# authHTTP callback reachability from MediaMTX when container exists.
if [ -n "${mtx_cid}" ]; then
  health_ok=false
  for target in "http://${API_ALIAS}:8000/health" "http://host.docker.internal:8000/health"; do
    if docker exec "${mtx_cid}" /bin/wget -q -O /dev/null --timeout=5 "${target}" 2>/dev/null; then
      echo "smoke_live_stream: OK authHTTP path probe ${target}"
      health_ok=true
      break
    fi
  done
  if [[ "${health_ok}" != true ]]; then
    echo "smoke_live_stream: ERROR — MediaMTX cannot reach API for authHTTP" >&2
    exit 1
  fi
fi

echo "smoke_live_stream: all required checks passed"