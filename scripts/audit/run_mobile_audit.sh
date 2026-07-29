#!/usr/bin/env sh
set -u

echo "== Quality Gate - Mobile audit (Phase 0) =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
RAW_DIR="$ROOT_DIR/audit/raw"
MOBILE_DIR="$ROOT_DIR/mobile"

mkdir -p "$RAW_DIR"

TYPECHECK_REPORT="$RAW_DIR/mobile-typecheck.txt"
LINT_REPORT="$RAW_DIR/mobile-lint.txt"
TEST_REPORT="$RAW_DIR/mobile-jest.txt"
NPM_AUDIT_REPORT="$RAW_DIR/mobile-npm-audit.json"

TYPECHECK_STATUS="SKIPPED"
LINT_STATUS="SKIPPED"
TEST_STATUS="SKIPPED"
NPM_AUDIT_STATUS="SKIPPED"

write_note() {
  report_path="$1"
  message="$2"
  {
    echo "$message"
    echo "timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
  } >"$report_path"
}

write_exitcode() {
  printf '%s\n' "$2" >"${1}.exitcode"
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

has_script() {
  script_name="$1"
  node -e "const fs=require('fs');const p=process.argv[1];const n=process.argv[2];const j=JSON.parse(fs.readFileSync(p,'utf8'));process.exit(j.scripts&&Object.prototype.hasOwnProperty.call(j.scripts,n)?0:1);" \
    "$MOBILE_DIR/package.json" "$script_name" >/dev/null 2>&1
}

echo "Repositorio detectado: $ROOT_DIR"
echo "Directorio mobile: ${MOBILE_DIR}"
echo "Directorio de evidencia: $RAW_DIR"
echo

if [ ! -f "$MOBILE_DIR/package.json" ]; then
  write_note "$TYPECHECK_REPORT" "Mobile no ejecutado: no se detecto mobile/package.json."
  write_note "$LINT_REPORT" "Mobile no ejecutado: no se detecto mobile/package.json."
  write_note "$TEST_REPORT" "Mobile no ejecutado: no se detecto mobile/package.json."
  write_note "$NPM_AUDIT_REPORT" "Mobile no ejecutado: no se detecto mobile/package.json."
  write_exitcode "$TYPECHECK_REPORT" 0
  write_exitcode "$LINT_REPORT" 0
  write_exitcode "$TEST_REPORT" 0
  write_exitcode "$NPM_AUDIT_REPORT" 0
  echo "Mobile ausente — SKIPPED"
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  write_note "$TYPECHECK_REPORT" "npm no instalado en el entorno actual."
  write_note "$LINT_REPORT" "npm no instalado en el entorno actual."
  write_note "$TEST_REPORT" "npm no instalado en el entorno actual."
  write_note "$NPM_AUDIT_REPORT" "npm no instalado en el entorno actual."
  write_exitcode "$TYPECHECK_REPORT" 127
  write_exitcode "$LINT_REPORT" 127
  write_exitcode "$TEST_REPORT" 127
  write_exitcode "$NPM_AUDIT_REPORT" 127
  TYPECHECK_STATUS="NOT_AVAILABLE"
  LINT_STATUS="NOT_AVAILABLE"
  TEST_STATUS="NOT_AVAILABLE"
  NPM_AUDIT_STATUS="NOT_AVAILABLE"
else
  if has_script "typecheck"; then
    (cd "$MOBILE_DIR" && npm run typecheck) >"$TYPECHECK_REPORT" 2>&1
    rc=$?
    write_exitcode "$TYPECHECK_REPORT" "$rc"
    TYPECHECK_STATUS="$(mark_from_exit_code "$rc")"
  else
    TYPECHECK_STATUS="SKIPPED"
    write_note "$TYPECHECK_REPORT" "no se encontro script 'typecheck'"
    write_exitcode "$TYPECHECK_REPORT" 0
  fi

  if has_script "lint"; then
    (cd "$MOBILE_DIR" && npm run lint) >"$LINT_REPORT" 2>&1
    rc=$?
    write_exitcode "$LINT_REPORT" "$rc"
    LINT_STATUS="$(mark_from_exit_code "$rc")"
  else
    LINT_STATUS="SKIPPED"
    write_note "$LINT_REPORT" "no se encontro script 'lint'"
    write_exitcode "$LINT_REPORT" 0
  fi

  # Jest without Watchman — use project scripts (already include --watchman=false).
  if has_script "test"; then
    (cd "$MOBILE_DIR" && npm test -- --watchman=false) >"$TEST_REPORT" 2>&1
    rc=$?
    write_exitcode "$TEST_REPORT" "$rc"
    TEST_STATUS="$(mark_from_exit_code "$rc")"
  else
    TEST_STATUS="SKIPPED"
    write_note "$TEST_REPORT" "no se encontro script 'test'"
    write_exitcode "$TEST_REPORT" 0
  fi

  (cd "$MOBILE_DIR" && npm audit --json) >"$NPM_AUDIT_REPORT" 2>&1
  rc=$?
  write_exitcode "$NPM_AUDIT_REPORT" "$rc"
  # npm audit exits non-zero when vulns exist → FINDINGS
  NPM_AUDIT_STATUS="$(mark_from_exit_code "$rc")"
fi

echo "Resumen mobile audit:"
printf "%-12s | %-16s | %s\n" "Herramienta" "Estado" "Reporte"
printf "%-12s | %-16s | %s\n" "Typecheck" "$TYPECHECK_STATUS" "audit/raw/mobile-typecheck.txt"
printf "%-12s | %-16s | %s\n" "Lint" "$LINT_STATUS" "audit/raw/mobile-lint.txt"
printf "%-12s | %-16s | %s\n" "Jest" "$TEST_STATUS" "audit/raw/mobile-jest.txt"
printf "%-12s | %-16s | %s\n" "npm audit" "$NPM_AUDIT_STATUS" "audit/raw/mobile-npm-audit.json"

exit 0
