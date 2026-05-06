#!/usr/bin/env sh
set -u

echo "== Quality Gate - Backend audit (Fase 2) =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
RAW_DIR="$ROOT_DIR/audit/raw"

mkdir -p "$RAW_DIR"

# Backend path detection
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

# Mypy target: prefer main backend package under src/, fallback to backend scope
MYPY_TARGET="$BACKEND_SCOPE"
if [ -n "${BACKEND_DIR}" ] && [ -d "$BACKEND_DIR/src" ]; then
  MYPY_TARGET="$BACKEND_DIR/src"
fi

RUFF_REPORT="$RAW_DIR/backend-ruff.txt"
MYPY_REPORT="$RAW_DIR/backend-mypy.txt"
BANDIT_REPORT="$RAW_DIR/backend-bandit.json"
PIP_AUDIT_REPORT="$RAW_DIR/backend-pip-audit.json"
PYTEST_REPORT="$RAW_DIR/backend-pytest.txt"

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
    echo "ERROR"
  fi
}

echo "Repositorio detectado: $ROOT_DIR"
echo "Directorio backend detectado: $BACKEND_SCOPE"
echo "Directorio de evidencia: $RAW_DIR"
echo

# Ruff
if [ -z "$BACKEND_DIR" ] || [ ! -d "$BACKEND_SCOPE" ]; then
  RUFF_STATUS="SKIPPED"
  write_note "$RUFF_REPORT" "Ruff no ejecutado: no se detecto directorio backend."
elif ! command -v ruff >/dev/null 2>&1; then
  RUFF_STATUS="NOT_INSTALLED"
  write_note "$RUFF_REPORT" "Ruff no instalado en el entorno actual."
else
  ruff check "$BACKEND_SCOPE" >"$RUFF_REPORT" 2>&1
  RUFF_STATUS="$(mark_from_exit_code "$?")"
fi

# Mypy
if [ -z "$BACKEND_DIR" ] || [ ! -d "$BACKEND_SCOPE" ]; then
  MYPY_STATUS="SKIPPED"
  write_note "$MYPY_REPORT" "Mypy no ejecutado: no se detecto directorio backend."
elif ! command -v mypy >/dev/null 2>&1; then
  MYPY_STATUS="NOT_INSTALLED"
  write_note "$MYPY_REPORT" "Mypy no instalado en el entorno actual."
else
  mypy "$MYPY_TARGET" >"$MYPY_REPORT" 2>&1
  MYPY_STATUS="$(mark_from_exit_code "$?")"
fi

# Bandit (JSON, recursive, with excludes)
if [ -z "$BACKEND_DIR" ] || [ ! -d "$BACKEND_SCOPE" ]; then
  BANDIT_STATUS="SKIPPED"
  write_note "$BANDIT_REPORT" "Bandit no ejecutado: no se detecto directorio backend."
elif ! command -v bandit >/dev/null 2>&1; then
  BANDIT_STATUS="NOT_INSTALLED"
  write_note "$BANDIT_REPORT" "Bandit no instalado en el entorno actual."
else
  BANDIT_TARGET="$SOURCE_DIR"
  if [ -z "$BANDIT_TARGET" ] || [ ! -d "$BANDIT_TARGET" ]; then
    BANDIT_TARGET="$BACKEND_SCOPE"
  fi
  bandit -r "$BANDIT_TARGET" -f json -o "$BANDIT_REPORT" \
    -x ".venv,venv,__pycache__,.mypy_cache,.pytest_cache" >/dev/null 2>&1
  BANDIT_STATUS="$(mark_from_exit_code "$?")"
  if [ ! -s "$BANDIT_REPORT" ]; then
    write_note "$BANDIT_REPORT" "Bandit no produjo salida JSON. Revisar salida local."
  fi
fi

# pip-audit (prefer pyproject.toml, fallback requirements.txt)
if ! command -v pip-audit >/dev/null 2>&1; then
  PIP_AUDIT_STATUS="NOT_INSTALLED"
  write_note "$PIP_AUDIT_REPORT" "pip-audit no instalado en el entorno actual."
else
  if [ -n "$BACKEND_DIR" ] && [ -f "$BACKEND_DIR/pyproject.toml" ]; then
    pip-audit --path "$BACKEND_DIR" --format json >"$PIP_AUDIT_REPORT" 2>&1
    PIP_AUDIT_STATUS="$(mark_from_exit_code "$?")"
  elif [ -n "$BACKEND_DIR" ] && [ -f "$BACKEND_DIR/requirements.txt" ]; then
    pip-audit -r "$BACKEND_DIR/requirements.txt" --format json >"$PIP_AUDIT_REPORT" 2>&1
    PIP_AUDIT_STATUS="$(mark_from_exit_code "$?")"
  else
    PIP_AUDIT_STATUS="SKIPPED"
    write_note "$PIP_AUDIT_REPORT" "pip-audit no ejecutado: no existe backend/pyproject.toml ni backend/requirements.txt."
  fi
fi

# Pytest
if [ -z "$BACKEND_DIR" ] || [ ! -d "$BACKEND_SCOPE" ]; then
  PYTEST_STATUS="SKIPPED"
  write_note "$PYTEST_REPORT" "Pytest no ejecutado: no se detecto directorio backend."
elif ! command -v pytest >/dev/null 2>&1; then
  PYTEST_STATUS="NOT_INSTALLED"
  write_note "$PYTEST_REPORT" "Pytest no instalado en el entorno actual."
else
  pytest "$BACKEND_SCOPE/tests" >"$PYTEST_REPORT" 2>&1
  PYTEST_STATUS="$(mark_from_exit_code "$?")"
fi

echo "Resumen backend audit:"
printf "%-12s | %-13s | %s\n" "Herramienta" "Estado" "Reporte"
printf "%-12s | %-13s | %s\n" "Ruff" "$RUFF_STATUS" "audit/raw/backend-ruff.txt"
printf "%-12s | %-13s | %s\n" "Mypy" "$MYPY_STATUS" "audit/raw/backend-mypy.txt"
printf "%-12s | %-13s | %s\n" "Bandit" "$BANDIT_STATUS" "audit/raw/backend-bandit.json"
printf "%-12s | %-13s | %s\n" "pip-audit" "$PIP_AUDIT_STATUS" "audit/raw/backend-pip-audit.json"
printf "%-12s | %-13s | %s\n" "Pytest" "$PYTEST_STATUS" "audit/raw/backend-pytest.txt"

exit 0
