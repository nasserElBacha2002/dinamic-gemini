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

cd "${ROOT}"
exec "$@"
