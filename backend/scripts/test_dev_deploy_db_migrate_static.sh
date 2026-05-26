#!/usr/bin/env bash
# Static checks for dev_deploy_db_migrate.sh (no Docker required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${ROOT}/dev_deploy_db_migrate.sh"

bash -n "${TARGET}"

for needle in \
  "set -euo pipefail" \
  "config-check" \
  "RUN_MIGRATION_DOCTOR_ON_DEPLOY" \
  "Skipping migration doctor during deploy" \
  "wait_for_api_exec" \
  "run_migration_status_json" \
  "Running migration status" \
  ">&2" \
  "sys.stdin.read" \
  "pending_migration_count" \
  "empty output" \
  "status" \
  "apply" \
  "validate" \
  "AUTO_APPLY_DEV_MIGRATIONS" \
  "DEV_DEPLOY_DB_MIGRATE_CHECK_ONLY" \
  "main_check_only" \
  "CHECK_ONLY OK" \
  "require_docker_compose" \
  "require_api_service" \
  "exec -T" \
  "pending_versions" \
  "compatible"; do
  if ! grep -q "${needle}" "${TARGET}"; then
    echo "missing expected content: ${needle}" >&2
    exit 1
  fi
done

if grep -q 'run_migrate doctor' "${TARGET}" && ! grep -q 'maybe_run_doctor' "${TARGET}"; then
  echo "doctor must only run via maybe_run_doctor (optional flag)" >&2
  exit 1
fi

if ! grep -q 'run_migrate apply' "${TARGET}"; then
  echo "missing run_migrate apply for deploy path" >&2
  exit 1
fi

# CHECK_ONLY path must not invoke apply
if awk '/^main_check_only\(\)/,/^}/' "${TARGET}" | grep -q 'run_migrate apply'; then
  echo "main_check_only must not call run_migrate apply" >&2
  exit 1
fi

# Embedded Python must compile (catches f-string backslash-in-expression errors).
_python_snippet() {
  local fn="$1"
  awk -v fn="${fn}" '
    $0 ~ "^" fn "\\(\\) \\{" { found=1; next }
    found && /^[[:space:]]*cat <<.?PY/ { heredoc=1; next }
    heredoc && /^PY$/ { exit }
    heredoc { print }
  ' "${TARGET}"
}

_tmpdir="$(mktemp -d)"
trap 'rm -rf "${_tmpdir}"' EXIT
_read_file="${_tmpdir}/read_status.py"
_assert_file="${_tmpdir}/assert_status_clean.py"
_python_snippet _python_read_status_json >"${_read_file}"
_python_snippet _python_assert_status_clean >"${_assert_file}"
python3 -c 'import ast, sys; [ast.parse(open(p).read(), p) for p in sys.argv[1:]]' \
  "${_read_file}" "${_assert_file}"

# Smoke: status JSON parse + assert_status_clean (no Docker).
sample='{"pending_versions":[],"compatible":true,"required_version":"0036","current_version":"0036"}'
parsed="$(printf '%s' "${sample}" | python3 "${_read_file}")"
if ! printf '%s' "${parsed}" | STATUS_LABEL=smoke python3 "${_assert_file}" | grep -q 'OK: smoke'; then
  echo "assert_status_clean smoke test failed" >&2
  exit 1
fi

if grep -E 'data\.get\\(\\"' "${TARGET}" >/dev/null 2>&1; then
  echo "found escaped quotes inside f-string expression (invalid in Python 3.11+)" >&2
  grep -n -E 'data\.get\\(\\"' "${TARGET}" >&2 || true
  exit 1
fi

echo "dev_deploy_db_migrate.sh static checks OK"
