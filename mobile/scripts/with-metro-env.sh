#!/usr/bin/env bash
# Ensure Watchman + file-descriptor headroom before Metro/Expo.
# Root cause of EMFILE on this machine: ~/.local/state is root-owned, so Watchman
# cannot create its state dir and Metro falls back to Node FSEvents (soft limit ~256).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export XDG_STATE_HOME="${XDG_STATE_HOME:-${HOME}/.watchman-state}"
mkdir -p "${XDG_STATE_HOME}"

# Soft limit: raise as high as the hard limit allows (ignore failures).
ulimit -n 65536 2>/dev/null || ulimit -n 10240 2>/dev/null || true

if command -v watchman >/dev/null 2>&1; then
  # Prefer a project-scoped watch; ignore failures (Metro will still try Watchman).
  watchman watch-project "${ROOT}" >/dev/null 2>&1 || true
fi

# Physical device + DINAMIC_API_BASE_URL=http://127.0.0.1:<port> needs a USB tunnel.
# Without it, local CODE_SCAN still works but uploads fail → «Procesar» stays disabled.
ensure_adb_reverse_for_loopback_api() {
  local url="${DINAMIC_API_BASE_URL:-${EXPO_PUBLIC_API_BASE_URL:-}}"
  if [[ -z "${url}" && -f "${ROOT}/.env" ]]; then
    url="$(
      grep -E '^(DINAMIC_API_BASE_URL|EXPO_PUBLIC_API_BASE_URL)=' "${ROOT}/.env" \
        | head -n 1 \
        | cut -d= -f2- \
        | tr -d '\"' \
        | tr -d "'" \
        | tr -d '\r'
    )"
  fi
  [[ -n "${url}" ]] || return 0

  local host="" port="8000"
  if [[ "${url}" =~ ^https?://([^/:]+)(:([0-9]+))? ]]; then
    host="${BASH_REMATCH[1]}"
    port="${BASH_REMATCH[3]:-8000}"
  else
    return 0
  fi
  if [[ "${host}" != "127.0.0.1" && "${host}" != "localhost" ]]; then
    return 0
  fi
  if ! command -v adb >/dev/null 2>&1; then
    return 0
  fi
  if ! adb devices 2>/dev/null | grep -qE $'\tdevice$'; then
    echo "[dinamic] loopback API (${host}:${port}) but no USB device — uploads need adb reverse or a LAN IP" >&2
    return 0
  fi
  if adb reverse "tcp:${port}" "tcp:${port}" >/dev/null 2>&1; then
    echo "[dinamic] adb reverse tcp:${port} → host (loopback API for physical device)" >&2
  else
    echo "[dinamic] warning: adb reverse tcp:${port} failed" >&2
  fi
}

ensure_adb_reverse_for_loopback_api

cd "${ROOT}"
exec "$@"
