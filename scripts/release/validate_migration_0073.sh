#!/usr/bin/env bash
# Phase 7 — migration 0073 validation (fail-closed).
# Modes: preflight | apply | verify | rollback | reapply | full (default)
# Uses an ephemeral *test* database on the configured local SQL Server — never production.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/release/_common.sh
source "${ROOT}/scripts/release/_common.sh"

MODE="${1:-full}"
case "${MODE}" in
  preflight|apply|verify|rollback|reapply|full) ;;
  *)
    echo "Usage: $0 [preflight|apply|verify|rollback|reapply|full]" >&2
    exit 2
    ;;
esac

release_require_cmd git
release_require_python
release_require_sha
release_ensure_sql_available
release_ensure_phase7_db "${PHASE7_SQL_DATABASE}"

EXIT_PREFLIGHT=0
EXIT_APPLY=0
EXIT_VERIFY=0
EXIT_ROLLBACK=0
EXIT_REAPPLY=0
EXIT_VERIFY2=0
SCHEMA_VERSION=""
INDEX_STATE=""

_json_field() {
  local field="$1"
  "${RELEASE_PY}" -c 'import sys,json
lines=[l for l in sys.stdin.read().splitlines() if l.strip().startswith("{")]
print(json.loads(lines[-1]).get(sys.argv[1],"") if lines else "")' "${field}"
}

run_preflight() {
  release_log_stage "0073 preflight"
  set +e
  release_preflight_0073
  EXIT_PREFLIGHT=$?
  set -e
  echo "preflight_exit=${EXIT_PREFLIGHT}"
  [[ "${EXIT_PREFLIGHT}" -eq 0 ]] || release_die "preflight failed (duplicates or SQL unavailable)"
}

run_apply() {
  release_log_stage "0073 apply (pending migrations including 0073)"
  set +e
  out="$(release_db_migrate apply 2>&1)"
  EXIT_APPLY=$?
  set -e
  echo "${out}"
  echo "apply_exit=${EXIT_APPLY}"
  [[ "${EXIT_APPLY}" -eq 0 ]] || release_die "migration apply failed"
  SCHEMA_VERSION="$(printf '%s\n' "${out}" | _json_field current_version)"
  echo "schema_version=${SCHEMA_VERSION}"
}

run_verify() {
  release_log_stage "0073 verify"
  set +e
  status_out="$(release_db_migrate status 2>&1)"
  EXIT_VERIFY=$?
  set -e
  echo "${status_out}"
  echo "status_exit=${EXIT_VERIFY}"
  [[ "${EXIT_VERIFY}" -eq 0 ]] || release_die "migration status failed"
  SCHEMA_VERSION="$(printf '%s\n' "${status_out}" | _json_field current_version)"
  echo "schema_version=${SCHEMA_VERSION}"
  [[ "${SCHEMA_VERSION}" == "0073" ]] || release_die "expected schema version 0073, got ${SCHEMA_VERSION}"
  if release_index_0073_exists "${PHASE7_SQL_DATABASE}"; then
    INDEX_STATE=present
  else
    INDEX_STATE=absent
    release_die "UX_inventory_jobs_retry_of_job_id missing after apply"
  fi
  echo "index_state=${INDEX_STATE}"
  set +e
  validate_out="$(release_db_migrate validate 2>&1)"
  local_validate=$?
  set -e
  echo "${validate_out}"
  [[ "${local_validate}" -eq 0 ]] || release_die "schema validate failed"
}

run_rollback() {
  release_log_stage "0073 rollback"
  set +e
  release_rollback_0073 "${PHASE7_SQL_DATABASE}"
  EXIT_ROLLBACK=$?
  set -e
  echo "rollback_exit=${EXIT_ROLLBACK}"
  [[ "${EXIT_ROLLBACK}" -eq 0 ]] || release_die "rollback failed"
  INDEX_STATE=absent
}

run_reapply() {
  release_log_stage "0073 reapply"
  set +e
  release_preflight_0073
  local pf=$?
  set -e
  [[ "${pf}" -eq 0 ]] || release_die "preflight before reapply failed"
  set +e
  release_reapply_0073 "${PHASE7_SQL_DATABASE}"
  EXIT_REAPPLY=$?
  set -e
  echo "reapply_exit=${EXIT_REAPPLY}"
  [[ "${EXIT_REAPPLY}" -eq 0 ]] || release_die "reapply failed"
}

run_verify2() {
  release_log_stage "0073 verify after reapply"
  if release_index_0073_exists "${PHASE7_SQL_DATABASE}"; then
    INDEX_STATE=present
    EXIT_VERIFY2=0
  else
    INDEX_STATE=absent
    EXIT_VERIFY2=1
    release_die "index missing after reapply"
  fi
  echo "index_state=${INDEX_STATE}"
  echo "verify2_exit=${EXIT_VERIFY2}"
}

case "${MODE}" in
  preflight) run_preflight ;;
  apply) run_apply ;;
  verify) run_verify ;;
  rollback) run_rollback ;;
  reapply) run_reapply ;;
  full)
    # Clone provides schema; then verify → preflight → rollback → reapply → verify.
    run_verify
    run_preflight
    run_rollback
    run_reapply
    run_verify2
    ;;
esac

echo ""
echo "MIG_0073_VALIDATION_OK"
echo "mode=${MODE}"
echo "schema_version=${SCHEMA_VERSION}"
echo "index_state=${INDEX_STATE}"
echo "exits preflight=${EXIT_PREFLIGHT} apply=${EXIT_APPLY} verify=${EXIT_VERIFY} rollback=${EXIT_ROLLBACK} reapply=${EXIT_REAPPLY} verify2=${EXIT_VERIFY2}"
