#!/usr/bin/env bash
# Ensure USB-connected Android devices can reach the host API via loopback.
# Required when DINAMIC_API_BASE_URL is http://127.0.0.1:<port> or http://localhost:<port>.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-}"

if [[ -z "${PORT}" ]]; then
  url="${DINAMIC_API_BASE_URL:-${EXPO_PUBLIC_API_BASE_URL:-}}"
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
  PORT="8000"
  if [[ -n "${url}" && "${url}" =~ ^https?://([^/:]+)(:([0-9]+))? ]]; then
    PORT="${BASH_REMATCH[3]:-8000}"
  fi
fi

if ! command -v adb >/dev/null 2>&1; then
  echo "[dinamic] adb no está en PATH — no se puede abrir el túnel USB" >&2
  exit 1
fi

devices="$(adb devices 2>/dev/null | awk '/\tdevice$/{print $1}')"
if [[ -z "${devices}" ]]; then
  echo "[dinamic] no hay dispositivo USB en estado 'device' — conectá el teléfono y reintentá" >&2
  exit 1
fi

ok=0
while IFS= read -r serial; do
  [[ -n "${serial}" ]] || continue
  if adb -s "${serial}" reverse "tcp:${PORT}" "tcp:${PORT}" >/dev/null 2>&1; then
    echo "[dinamic] adb reverse tcp:${PORT} → host (${serial})"
    ok=1
  else
    echo "[dinamic] warning: adb reverse falló en ${serial}" >&2
  fi
done <<< "${devices}"

if [[ "${ok}" -ne 1 ]]; then
  exit 1
fi

adb reverse --list 2>/dev/null || true
