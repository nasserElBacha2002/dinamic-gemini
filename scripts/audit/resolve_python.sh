#!/usr/bin/env sh
# Resolve AUDIT_PYTHON for audit shell runners. Source this file:
#   . "$(dirname "$0")/resolve_python.sh"
# Sets: AUDIT_PYTHON, AUDIT_PYTHON_REASON, AUDIT_VENV_ROOT

_audit_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"

_audit_pick_python() {
  if [ -n "${AUDIT_PYTHON:-}" ] && [ -x "${AUDIT_PYTHON}" ]; then
    AUDIT_PYTHON_REASON="AUDIT_PYTHON"
    return 0
  fi
  if [ -n "${DINAMIC_AUDIT_PYTHON:-}" ] && [ -x "${DINAMIC_AUDIT_PYTHON}" ]; then
    AUDIT_PYTHON="${DINAMIC_AUDIT_PYTHON}"
    AUDIT_PYTHON_REASON="DINAMIC_AUDIT_PYTHON"
    return 0
  fi
  for candidate in \
    "${_audit_root}/backend/.venv/bin/python" \
    "${_audit_root}/backend/.venv/bin/python3" \
    "${_audit_root}/.venv/bin/python" \
    "${_audit_root}/.venv/bin/python3" \
    "${_audit_root}/venv/bin/python" \
    "${_audit_root}/venv/bin/python3" \
    "${_audit_root}/backend/venv/bin/python" \
    "${_audit_root}/backend/venv/bin/python3"
  do
    if [ -x "$candidate" ]; then
      AUDIT_PYTHON="$candidate"
      AUDIT_PYTHON_REASON="project venv: $candidate"
      return 0
    fi
  done
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
    AUDIT_PYTHON="${VIRTUAL_ENV}/bin/python"
    AUDIT_PYTHON_REASON="VIRTUAL_ENV"
    return 0
  fi
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/Scripts/python.exe" ]; then
    AUDIT_PYTHON="${VIRTUAL_ENV}/Scripts/python.exe"
    AUDIT_PYTHON_REASON="VIRTUAL_ENV (Windows)"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    AUDIT_PYTHON="$(command -v python3)"
    AUDIT_PYTHON_REASON="PATH python3 (fallback)"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    AUDIT_PYTHON="$(command -v python)"
    AUDIT_PYTHON_REASON="PATH python (fallback)"
    return 0
  fi
  AUDIT_PYTHON=""
  AUDIT_PYTHON_REASON="NOT_AVAILABLE"
  return 1
}

_audit_pick_python || true
export AUDIT_PYTHON AUDIT_PYTHON_REASON
if [ -n "${AUDIT_PYTHON:-}" ]; then
  AUDIT_VENV_ROOT="$(CDPATH= cd -- "$(dirname -- "$AUDIT_PYTHON")/.." && pwd)"
  export AUDIT_VENV_ROOT
  # Prefer same-env binaries on PATH for this process.
  export PATH="$(dirname -- "$AUDIT_PYTHON"):$PATH"
fi

audit_run_module() {
  # usage: audit_run_module <module> [args...]  → runs "$AUDIT_PYTHON" -m module
  module="$1"
  shift
  if [ -z "${AUDIT_PYTHON:-}" ]; then
    return 127
  fi
  "$AUDIT_PYTHON" -m "$module" "$@"
}

audit_write_exitcode() {
  report_path="$1"
  code="$2"
  printf '%s\n' "$code" >"${report_path}.exitcode"
}
