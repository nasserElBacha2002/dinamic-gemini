#!/usr/bin/env sh
set -u

echo "== Quality Gate - Backend audit (Phase 0 tooling) =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
RAW_DIR="$ROOT_DIR/audit/raw"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

# shellcheck disable=SC1091
. "$SCRIPT_DIR/resolve_python.sh"

mkdir -p "$RAW_DIR"

if [ -d "$ROOT_DIR/backend" ]; then
  BACKEND_DIR="$ROOT_DIR/backend"
  BACKEND_SCOPE="$ROOT_DIR/backend"
elif [ -f "$ROOT_DIR/pyproject.toml" ]; then
  BACKEND_DIR="$ROOT_DIR"
  BACKEND_SCOPE="$ROOT_DIR"
else
  BACKEND_DIR=""
  BACKEND_SCOPE="$ROOT_DIR/backend"
fi

if [ -n "$BACKEND_DIR" ] && [ -d "$BACKEND_DIR/src" ]; then
  SOURCE_DIR="$BACKEND_DIR/src"
else
  SOURCE_DIR="$BACKEND_DIR"
fi

MYPY_TARGET="$BACKEND_SCOPE"
if [ -n "${BACKEND_DIR}" ] && [ -d "$BACKEND_DIR/src" ]; then
  MYPY_TARGET="$BACKEND_DIR/src"
fi

RUFF_REPORT="$RAW_DIR/backend-ruff.txt"
MYPY_REPORT="$RAW_DIR/backend-mypy.txt"
BANDIT_REPORT="$RAW_DIR/backend-bandit.json"
PIP_AUDIT_REPORT="$RAW_DIR/backend-pip-audit.json"
PYTEST_REPORT="$RAW_DIR/backend-pytest.txt"
PYTHON_ENV_REPORT="$RAW_DIR/python-env.json"

RUFF_STATUS="SKIPPED"
MYPY_STATUS="SKIPPED"
BANDIT_STATUS="SKIPPED"
PIP_AUDIT_STATUS="SKIPPED"
PYTEST_STATUS="SKIPPED"

write_note() {
  report_path="$1"
  message="$2"
  {
    echo "$message"
    echo "timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
  } >"$report_path"
}

mark_from_exit_code() {
  exit_code="$1"
  if [ "$exit_code" -eq 0 ]; then
    echo "OK"
  elif [ "$exit_code" -eq 1 ]; then
    echo "FINDINGS"
  else
    echo "EXECUTION_ERROR"
  fi
}

module_available() {
  module="$1"
  if [ -z "${AUDIT_PYTHON:-}" ]; then
    return 1
  fi
  "$AUDIT_PYTHON" -c "import ${module}" >/dev/null 2>&1
}

echo "Repositorio detectado: $ROOT_DIR"
echo "Directorio backend detectado: $BACKEND_SCOPE"
echo "Directorio de evidencia: $RAW_DIR"
echo "Python resuelto: ${AUDIT_PYTHON:-NOT_AVAILABLE} (${AUDIT_PYTHON_REASON:-})"
echo

# Persist interpreter diagnosis for the aggregator / gate.
if [ -n "${AUDIT_PYTHON:-}" ]; then
  "$AUDIT_PYTHON" - "$PYTHON_ENV_REPORT" <<'PY' || true
import json, sys
from pathlib import Path
# Inline minimal env dump (avoid import path issues when lib not on PYTHONPATH)
out = Path(sys.argv[1])
payload = {
    "python_bin": sys.executable,
    "version": sys.version.split()[0],
    "selection_reason": __import__("os").environ.get("AUDIT_PYTHON_REASON", ""),
    "venv_root": __import__("os").environ.get("AUDIT_VENV_ROOT"),
    "tools": {},
}
for mod, label in [("pytest", "pytest"), ("ruff", "ruff"), ("mypy", "mypy"), ("bandit", "bandit")]:
    try:
        __import__(mod if mod != "pip_audit" else "pip_audit")
        payload["tools"][label] = f"{sys.executable} -m {mod}"
    except Exception:
        payload["tools"][label] = None
try:
    import pip_audit  # noqa: F401
    payload["tools"]["pip_audit"] = f"{sys.executable} -m pip_audit"
except Exception:
    payload["tools"]["pip_audit"] = None
out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
else
  write_note "$PYTHON_ENV_REPORT" '{"error":"AUDIT_PYTHON not available"}'
fi

# Ruff
if [ -z "$BACKEND_DIR" ] || [ ! -d "$BACKEND_SCOPE" ]; then
  RUFF_STATUS="SKIPPED"
  write_note "$RUFF_REPORT" "Ruff no ejecutado: no se detecto directorio backend."
  audit_write_exitcode "$RUFF_REPORT" 0
elif [ -z "${AUDIT_PYTHON:-}" ]; then
  RUFF_STATUS="NOT_AVAILABLE"
  write_note "$RUFF_REPORT" "Ruff no instalado: no hay intérprete Python resuelto."
  audit_write_exitcode "$RUFF_REPORT" 127
elif ! module_available ruff && ! command -v ruff >/dev/null 2>&1; then
  RUFF_STATUS="NOT_AVAILABLE"
  write_note "$RUFF_REPORT" "Ruff no instalado en el entorno actual."
  audit_write_exitcode "$RUFF_REPORT" 127
else
  if module_available ruff; then
    audit_run_module ruff check "$BACKEND_SCOPE" >"$RUFF_REPORT" 2>&1
  else
    ruff check "$BACKEND_SCOPE" >"$RUFF_REPORT" 2>&1
  fi
  rc=$?
  audit_write_exitcode "$RUFF_REPORT" "$rc"
  RUFF_STATUS="$(mark_from_exit_code "$rc")"
fi

# Mypy
if [ -z "$BACKEND_DIR" ] || [ ! -d "$BACKEND_SCOPE" ]; then
  MYPY_STATUS="SKIPPED"
  write_note "$MYPY_REPORT" "Mypy no ejecutado: no se detecto directorio backend."
  audit_write_exitcode "$MYPY_REPORT" 0
elif [ -z "${AUDIT_PYTHON:-}" ]; then
  MYPY_STATUS="NOT_AVAILABLE"
  write_note "$MYPY_REPORT" "Mypy no instalado: no hay intérprete Python resuelto."
  audit_write_exitcode "$MYPY_REPORT" 127
elif ! module_available mypy; then
  MYPY_STATUS="NOT_AVAILABLE"
  write_note "$MYPY_REPORT" "Mypy no instalado en el entorno actual."
  audit_write_exitcode "$MYPY_REPORT" 127
else
  (
    cd "$BACKEND_DIR" || exit 1
    audit_run_module mypy "$MYPY_TARGET"
  ) >"$MYPY_REPORT" 2>&1
  rc=$?
  audit_write_exitcode "$MYPY_REPORT" "$rc"
  MYPY_STATUS="$(mark_from_exit_code "$rc")"
fi

# Bandit
if [ -z "$BACKEND_DIR" ] || [ ! -d "$BACKEND_SCOPE" ]; then
  BANDIT_STATUS="SKIPPED"
  write_note "$BANDIT_REPORT" "Bandit no ejecutado: no se detecto directorio backend."
  audit_write_exitcode "$BANDIT_REPORT" 0
elif [ -z "${AUDIT_PYTHON:-}" ] || ! module_available bandit; then
  BANDIT_STATUS="NOT_AVAILABLE"
  write_note "$BANDIT_REPORT" "Bandit no instalado en el entorno actual."
  audit_write_exitcode "$BANDIT_REPORT" 127
else
  BANDIT_TARGET="$SOURCE_DIR"
  if [ -z "$BANDIT_TARGET" ] || [ ! -d "$BANDIT_TARGET" ]; then
    BANDIT_TARGET="$BACKEND_SCOPE"
  fi
  audit_run_module bandit -r "$BANDIT_TARGET" -f json -o "$BANDIT_REPORT" \
    -x ".venv,venv,__pycache__,.mypy_cache,.pytest_cache" >/dev/null 2>&1
  rc=$?
  audit_write_exitcode "$BANDIT_REPORT" "$rc"
  BANDIT_STATUS="$(mark_from_exit_code "$rc")"
  if [ ! -s "$BANDIT_REPORT" ]; then
    write_note "$BANDIT_REPORT" "Bandit no produjo salida JSON. Revisar salida local."
  fi
fi

# pip-audit
if [ -z "${AUDIT_PYTHON:-}" ] || ! "$AUDIT_PYTHON" -c "import pip_audit" >/dev/null 2>&1; then
  PIP_AUDIT_STATUS="NOT_AVAILABLE"
  write_note "$PIP_AUDIT_REPORT" "pip-audit no instalado en el entorno actual."
  audit_write_exitcode "$PIP_AUDIT_REPORT" 127
else
  if [ -n "$BACKEND_DIR" ] && [ -f "$BACKEND_DIR/pyproject.toml" ]; then
    (
      cd "$BACKEND_DIR" || exit 1
      audit_run_module pip_audit --path . --format json --skip-editable
    ) >"$PIP_AUDIT_REPORT" 2>&1
    rc=$?
    audit_write_exitcode "$PIP_AUDIT_REPORT" "$rc"
    PIP_AUDIT_STATUS="$(mark_from_exit_code "$rc")"
  elif [ -n "$BACKEND_DIR" ] && [ -f "$BACKEND_DIR/requirements.txt" ]; then
    audit_run_module pip_audit -r "$BACKEND_DIR/requirements.txt" --format json >"$PIP_AUDIT_REPORT" 2>&1
    rc=$?
    audit_write_exitcode "$PIP_AUDIT_REPORT" "$rc"
    PIP_AUDIT_STATUS="$(mark_from_exit_code "$rc")"
  else
    PIP_AUDIT_STATUS="SKIPPED"
    write_note "$PIP_AUDIT_REPORT" "pip-audit no ejecutado: no existe backend/pyproject.toml ni backend/requirements.txt."
    audit_write_exitcode "$PIP_AUDIT_REPORT" 0
  fi
fi

# Pytest — prefer repo-root invocation matching CI when possible
if [ -z "$BACKEND_DIR" ] || [ ! -d "$BACKEND_SCOPE" ]; then
  PYTEST_STATUS="SKIPPED"
  write_note "$PYTEST_REPORT" "Pytest no ejecutado: no se detecto directorio backend."
  audit_write_exitcode "$PYTEST_REPORT" 0
elif [ -z "${AUDIT_PYTHON:-}" ] || ! module_available pytest; then
  PYTEST_STATUS="NOT_AVAILABLE"
  write_note "$PYTEST_REPORT" "Pytest no instalado en el entorno actual."
  audit_write_exitcode "$PYTEST_REPORT" 127
else
  if [ -f "$ROOT_DIR/pytest.ini" ] || [ -f "$ROOT_DIR/pyproject.toml" ]; then
    (
      cd "$ROOT_DIR" || exit 1
      audit_run_module pytest backend/tests -q --tb=no
    ) >"$PYTEST_REPORT" 2>&1
  else
    (
      cd "$BACKEND_DIR" || exit 1
      audit_run_module pytest tests -q --tb=no
    ) >"$PYTEST_REPORT" 2>&1
  fi
  rc=$?
  audit_write_exitcode "$PYTEST_REPORT" "$rc"
  PYTEST_STATUS="$(mark_from_exit_code "$rc")"
fi

echo "Resumen backend audit:"
printf "%-12s | %-16s | %s\n" "Herramienta" "Estado" "Reporte"
printf "%-12s | %-16s | %s\n" "Ruff" "$RUFF_STATUS" "audit/raw/backend-ruff.txt"
printf "%-12s | %-16s | %s\n" "Mypy" "$MYPY_STATUS" "audit/raw/backend-mypy.txt"
printf "%-12s | %-16s | %s\n" "Bandit" "$BANDIT_STATUS" "audit/raw/backend-bandit.json"
printf "%-12s | %-16s | %s\n" "pip-audit" "$PIP_AUDIT_STATUS" "audit/raw/backend-pip-audit.json"
printf "%-12s | %-16s | %s\n" "Pytest" "$PYTEST_STATUS" "audit/raw/backend-pytest.txt"

exit 0
