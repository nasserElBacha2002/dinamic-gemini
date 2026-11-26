#!/usr/bin/env bash
# DIN-508 Phase 2 — strict RTMP/HLS POC validation (fails on assertion breach).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
EVIDENCE_DIR="${REPO}/DIN-508/phase-2"
FINAL_DIR="${REPO}/DIN-508/phase-2/corrections"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_LOG="${EVIDENCE_DIR}/run-${STAMP}.log"
SANITIZE_LOG="${EVIDENCE_DIR}/phase-2-tests.txt"
SANITIZE_FINAL="${FINAL_DIR}/final-corrections-tests-streaming.txt"

FAILURES=0

log() { echo "$@" | tee -a "$RUN_LOG"; }

fail() {
  log "ASSERT_FAIL: $*"
  FAILURES=$((FAILURES + 1))
}

assert_http() {
  local label="$1"
  local expected="$2"
  local actual="$3"
  if [[ "$actual" != "$expected" ]]; then
    fail "${label}: expected http ${expected}, got ${actual}"
  else
    log "ASSERT_OK: ${label} http=${actual}"
  fi
}

wait_container_healthy() {
  local label="$1"
  local max_attempts="$2"
  local ok=false
  for _ in $(seq 1 "$max_attempts"); do
    local status
    status="$(docker inspect -f '{{.State.Health.Status}}' dinamic-mediamtx-poc 2>/dev/null || echo missing)"
    log "${label} health=${status}"
    if [[ "$status" == "healthy" ]]; then
      ok=true
      break
    fi
    sleep 2
  done
  if [[ "$ok" != true ]]; then
    fail "${label}: readiness/recovery timeout (${max_attempts} attempts)"
  fi
}

mtx_log_recent() {
  docker logs --since 15s dinamic-mediamtx-poc 2>&1 || true
}

publish_ffmpeg_sync() {
  local path="$1"
  local user="$2"
  local pass="$3"
  local duration="$4"
  urlencode "$user" "$pass"
  ffmpeg -hide_banner -loglevel warning \
    -re -f lavfi -i "testsrc=size=640x360:rate=15,format=yuv420p" \
    -f lavfi -i "sine=frequency=440:sample_rate=44100" \
    -t "$duration" \
    -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p -g 30 \
    -c:a aac -b:a 64k \
    -f flv "rtmp://127.0.0.1:${RTMP_PORT}/${path}?user=${EU}&pass=${EP}" \
    >>"$RUN_LOG" 2>&1
}

publish_ffmpeg_bg() {
  local path="$1"
  local user="$2"
  local pass="$3"
  local duration="$4"
  urlencode "$user" "$pass"
  ffmpeg -hide_banner -loglevel warning \
    -re -f lavfi -i "testsrc=size=640x360:rate=15,format=yuv420p" \
    -f lavfi -i "sine=frequency=440:sample_rate=44100" \
    -t "$duration" \
    -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p -g 30 \
    -c:a aac -b:a 64k \
    -f flv "rtmp://127.0.0.1:${RTMP_PORT}/${path}?user=${EU}&pass=${EP}" \
    >>"$RUN_LOG" 2>&1 &
  echo $!
}

urlencode() {
  EU="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$1")"
  EP="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$2")"
}

wait_pid() {
  local pid="${1//[[:space:]]/}"
  local label="$2"
  if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
    fail "wait_pid ${label}: invalid pid '${pid}'"
    return
  fi
  if kill -0 "$pid" 2>/dev/null; then
    wait "$pid" || log "pid_${label}=${pid} exit=$?"
  else
    log "pid_${label}=${pid} already exited"
  fi
}

assert_hls_playlist_200() {
  local url="$1"
  local user="$2"
  local pass="$3"
  local label="$4"
  local code="" i
  for i in $(seq 1 15); do
    code="$(hls_playlist_http "$url" "$user" "$pass")"
    log "${label} attempt=$i http=$code"
    [[ "$code" == "200" ]] && break
    sleep 1
  done
  assert_http "$label" 200 "$code"
}

try_publish_expect_reject() {
  local path="$1"
  local user="$2"
  local pass="$3"
  local reason_label="$4"
  set +e
  publish_ffmpeg_sync "$path" "$user" "$pass" 3
  local rc=$?
  set -e
  sleep 1
  local tail_log
  tail_log="$(mtx_log_recent | tail -40)"
  log "--- mediamtx tail (${reason_label}) ---"
  log "$tail_log"
  if [[ "$rc" -eq 0 ]]; then
    fail "${reason_label}: publish unexpectedly succeeded (ffmpeg rc=0)"
    return
  fi
  if echo "$tail_log" | grep -qiE 'authentication failed|already publishing|path is already|not allowed|is being published|path already'; then
    log "ASSERT_OK: ${reason_label} rejected (log confirmed)"
  else
    fail "${reason_label}: ffmpeg failed (rc=${rc}) but mediamtx log lacks expected reject reason"
  fi
}

hls_playlist_http() {
  local url="$1"
  local user="$2"
  local pass="$3"
  curl -s -o /dev/null -w '%{http_code}' -u "${user}:${pass}" "$url"
}

resolve_hls_segment_url() {
  local path="$1"
  local user="$2"
  local pass="$3"
  local playlist_url="http://127.0.0.1:${HLS_PORT}/${path}/index.m3u8"
  local playlist
  playlist="$(curl -sf -u "${user}:${pass}" "$playlist_url")" || return 1
  local rel seg_rel="" media_lines
  media_lines="$(echo "$playlist" | grep -E '^[^#].+' | tr -d '\r' || true)"
  for rel in $media_lines; do
    if [[ "$rel" == *.ts ]]; then
      seg_rel="$rel"
      break
    fi
    if [[ "$rel" == *.m3u8 ]]; then
      local sub sub_pl
      sub="http://127.0.0.1:${HLS_PORT}/${path}/${rel}"
      sub_pl="$(curl -sf -u "${user}:${pass}" "$sub")" || return 1
      seg_rel="$(echo "$sub_pl" | grep -E '^[^#].+\.ts' | head -1 | tr -d '\r' || true)"
      [[ -n "$seg_rel" ]] && break
    fi
  done
  [[ -z "$seg_rel" ]] && return 1
  echo "http://127.0.0.1:${HLS_PORT}/${path}/${seg_rel}"
}

assert_hls_segment_pair() {
  local path="$1"
  local user="$2"
  local pass="$3"
  local label="$4"
  local seg_url
  if ! seg_url="$(resolve_hls_segment_url "$path" "$user" "$pass")"; then
    fail "${label}: mandatory HLS segment missing in playlist"
    return
  fi
  local auth_code noauth_code
  auth_code="$(curl -s -o /dev/null -w '%{http_code}' -u "${user}:${pass}" "$seg_url")"
  noauth_code="$(curl -s -o /dev/null -w '%{http_code}' "$seg_url")"
  assert_http "${label}_segment_auth" 200 "$auth_code"
  assert_http "${label}_segment_noauth" 401 "$noauth_code"
}

mkdir -p "$EVIDENCE_DIR" "$FINAL_DIR" "$ROOT/generated"

# Built-in proof that failed assertions exit non-zero (no docker).
if [[ "${POC_VALIDATION_SELF_TEST_ASSERT:-}" == "1" ]]; then
  log "=== self-test assert failure ==="
  fail "deliberate self-test failure"
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Missing $ROOT/.env — copy .env.example and set secrets." >&2
  exit 2
fi

set -a
# shellcheck source=/dev/null
source "$ROOT/.env"
set +a

python3 "$ROOT/scripts/render_mediamtx_config.py" | tee -a "$RUN_LOG"

PATH_A="$(grep path_a= "$ROOT/generated/channel-paths.txt" | cut -d= -f2)"
PATH_B="$(grep path_b= "$ROOT/generated/channel-paths.txt" | cut -d= -f2)"

RTMP_PORT="${MTX_RTMP_HOST_PORT:-19350}"
HLS_PORT="${MTX_HLS_HOST_PORT:-8888}"
HLS_A="http://127.0.0.1:${HLS_PORT}/${PATH_A}/index.m3u8"
HLS_B="http://127.0.0.1:${HLS_PORT}/${PATH_B}/index.m3u8"

cd "$ROOT"

log "=== docker compose up ==="
docker compose down --remove-orphans 2>/dev/null | tee -a "$RUN_LOG" || true
docker compose up -d | tee -a "$RUN_LOG"

wait_container_healthy "initial" 30

log "=== unauthorized publish ==="
try_publish_expect_reject "$PATH_A" "${POC_BAD_PUB_USER:-bad}" "${POC_BAD_PUB_PASS:-bad}" "unauthorized_publish"

log "=== authorized publish A (12s) ==="
FF_A="$(publish_ffmpeg_bg "$PATH_A" "$POC_PUB_A_USER" "$POC_PUB_A_PASS" 12)"
sleep 5
assert_hls_playlist_200 "$HLS_A" "$POC_VIEW_A_USER" "$POC_VIEW_A_PASS" "hls_playlist_authorized"
noauth_playlist="$(curl -s -o /dev/null -w '%{http_code}' "$HLS_A")"
assert_http "hls_playlist_unauthorized" 401 "$noauth_playlist"
assert_hls_segment_pair "$PATH_A" "$POC_VIEW_A_USER" "$POC_VIEW_A_PASS" "live_A"

view_b_on_a="$(hls_playlist_http "$HLS_B" "$POC_VIEW_A_USER" "$POC_VIEW_A_PASS")"
assert_http "hls_cross_channel_viewer" 401 "$view_b_on_a"

log "=== dual channel publish A+B ==="
FF_B="$(publish_ffmpeg_bg "$PATH_B" "$POC_PUB_B_USER" "$POC_PUB_B_PASS" 10)"
sleep 3
hls_b="$(hls_playlist_http "$HLS_B" "$POC_VIEW_B_USER" "$POC_VIEW_B_PASS")"
assert_http "hls_channel_b" 200 "$hls_b"
try_publish_expect_reject "$PATH_B" "$POC_PUB_A_USER" "$POC_PUB_A_PASS" "cross_channel_publish"

log "=== concurrent publisher same channel (overridePublisher=no) ==="
wait_pid "$FF_A" "pub_a_initial"

FF_A1="$(publish_ffmpeg_bg "$PATH_A" "$POC_PUB_A_USER" "$POC_PUB_A_PASS" 18)"
sleep 4
hls_mid="$(hls_playlist_http "$HLS_A" "$POC_VIEW_A_USER" "$POC_VIEW_A_PASS")"
assert_http "hls_during_first_publisher" 200 "$hls_mid"
try_publish_expect_reject "$PATH_A" "$POC_PUB_A_USER" "$POC_PUB_A_PASS" "concurrent_second_publisher"
wait_pid "$FF_A1" "pub_a_primary"

sleep 2
publish_ffmpeg_sync "$PATH_A" "$POC_PUB_A_USER" "$POC_PUB_A_PASS" 8 &
FF_REPUB=$!
sleep 4
assert_hls_playlist_200 "$HLS_A" "$POC_VIEW_A_USER" "$POC_VIEW_A_PASS" "hls_after_republish"
wait_pid "$FF_REPUB" "repub_a"

wait_pid "$FF_B" "pub_b"

log "=== abrupt publisher stop + republish ==="
FF_KILL="$(publish_ffmpeg_bg "$PATH_A" "$POC_PUB_A_USER" "$POC_PUB_A_PASS" 60)"
sleep 3
kill -9 "$FF_KILL" 2>/dev/null || true
wait_pid "$FF_KILL" "killed_pub" || true
sleep 5
FF_AFTER_KILL="$(publish_ffmpeg_bg "$PATH_A" "$POC_PUB_A_USER" "$POC_PUB_A_PASS" 12)"
sleep 4
assert_hls_playlist_200 "$HLS_A" "$POC_VIEW_A_USER" "$POC_VIEW_A_PASS" "hls_after_abrupt_stop"
wait_pid "$FF_AFTER_KILL" "after_kill"

log "=== healthcheck stop/start ==="
docker compose stop mediamtx | tee -a "$RUN_LOG"
docker compose start mediamtx | tee -a "$RUN_LOG"
wait_container_healthy "after_start" 25

log "=== mediamtx restart + HLS smoke ==="
docker compose restart mediamtx | tee -a "$RUN_LOG"
wait_container_healthy "after_restart" 25
publish_ffmpeg_sync "$PATH_A" "$POC_PUB_A_USER" "$POC_PUB_A_PASS" 10 &
FF_POST_RESTART=$!
sleep 4
assert_hls_playlist_200 "$HLS_A" "$POC_VIEW_A_USER" "$POC_VIEW_A_PASS" "hls_after_container_restart"
assert_hls_segment_pair "$PATH_A" "$POC_VIEW_A_USER" "$POC_VIEW_A_PASS" "post_restart"
wait_pid "$FF_POST_RESTART" "post_restart"

backend_code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000/health" || echo 000)"
log "backend_health_http=${backend_code}"

python3 - <<'PY' "$RUN_LOG" "$SANITIZE_LOG" "$SANITIZE_FINAL"
import re, sys
for dst in sys.argv[2:]:
    text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    text = re.sub(r"user=[^&\s]+", "user=***", text)
    text = re.sub(r"pass=[^&\s]+", "pass=***", text)
    open(dst, "w", encoding="utf-8").write(text)
print(sys.argv[2])
PY

if [[ "$FAILURES" -gt 0 ]]; then
  log "VALIDATION_FAILED failures=${FAILURES}"
  exit 1
fi

log "VALIDATION_PASSED"
exit 0