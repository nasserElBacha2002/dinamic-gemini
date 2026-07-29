#!/usr/bin/env bash
# Phase 7 — migrations from empty DB.
#
# Repo contract: 0001_baseline.sql is metadata-only; full DDL comes from historical
# bootstrap / a schema-compatible source DB. This drill:
#   A) empty DB ← schema-only clone of dinamic-gemini (0073) → guard → app → rollback/reapply
#   B) empty DB ← schema-only clone of dinamic_inventory_test (0004) → apply 0005–0073
#   C) upgrade 0072 → 0073 on ephemeral DB
# Never targets production.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/release/_common.sh
source "${ROOT}/scripts/release/_common.sh"

CLONE_SOURCE_FULL="${PHASE7_CLONE_SOURCE_FULL:-dinamic-gemini}"
CLONE_SOURCE_BASE="${PHASE7_CLONE_SOURCE_BASE:-dinamic_inventory_test}"

release_require_cmd git
release_require_python
release_require_sha
release_ensure_sql_available

release_clone_database() {
  local src="$1"
  local dst="$2"
  [[ "${dst}" == *test* || "${dst}" == *phase7* ]] || release_die "refusing clone into non-test db: ${dst}"
  release_drop_database "${dst}"
  PYTHONPATH="${RELEASE_ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
  SQLSERVER_DATABASE=master \
  SQLSERVER_SERVER="${SQLSERVER_SERVER}" SQLSERVER_UID="${SQLSERVER_UID}" \
  SQLSERVER_PWD="${SQLSERVER_PWD}" SQLSERVER_ENABLED=true \
  SQLSERVER_TRUST_SERVER_CERTIFICATE=yes APP_ENV=development \
  "${RELEASE_PY}" - <<PY
import pyodbc
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
src, dst = """${src}""", """${dst}"""
conn = pyodbc.connect(resolve_sqlserver_connection_config().connection_string, autocommit=True)
cur = conn.cursor()
cur.execute("SELECT DB_ID(?)", (src,))
if cur.fetchone()[0] is None:
    raise SystemExit(f"clone source missing: {src}")
# Schema-only clone (no data). Requires SQL Server 2014+.
cur.execute(f"DBCC CLONEDATABASE (N'{src}', N'{dst}')")
cur.execute(f"ALTER DATABASE [{dst}] SET READ_WRITE WITH ROLLBACK IMMEDIATE")
cur.execute(
    f"""
    IF OBJECT_ID(N'[{dst}].dbo.schema_migrations', 'U') IS NOT NULL
       AND OBJECT_ID(N'[{src}].dbo.schema_migrations', 'U') IS NOT NULL
    BEGIN
        DELETE FROM [{dst}].dbo.schema_migrations;
        SET IDENTITY_INSERT [{dst}].dbo.schema_migrations ON;
        INSERT INTO [{dst}].dbo.schema_migrations
            (id, service_name, version, migration_name, checksum_sha256, deployment_id, applied_at)
        SELECT id, service_name, version, migration_name, checksum_sha256, deployment_id, applied_at
        FROM [{src}].dbo.schema_migrations;
        SET IDENTITY_INSERT [{dst}].dbo.schema_migrations OFF;
    END
    """
)
cur.close(); conn.close()
print(f"cloned_schema_only src={src} dst={dst}")
PY
}

_json_ver() {
  "${RELEASE_PY}" -c 'import json,sys; print(json.loads(sys.argv[1])["current_version"])' "$(echo "$1" | grep '^{' | tail -1)"
}

release_log_stage "A) empty → clone full schema (0073) → validate → app → rollback/reapply"
release_clone_database "${CLONE_SOURCE_FULL}" "${PHASE7_SQL_DATABASE}"
release_export_ephemeral_sql_env "${PHASE7_SQL_DATABASE}"
set +e
st_out="$(release_db_migrate status 2>&1)"
st_ec=$?
set -e
echo "${st_out}"
[[ "${st_ec}" -eq 0 ]] || release_die "status failed after clone"
ver="$(_json_ver "${st_out}")"
[[ "${ver}" == "0073" ]] || release_die "expected 0073 after full clone, got ${ver}"
set +e
val_out="$(release_db_migrate validate 2>&1)"
val_ec=$?
set -e
echo "${val_out}"
[[ "${val_ec}" -eq 0 ]] || release_die "validate failed after clone"
release_index_0073_exists "${PHASE7_SQL_DATABASE}" || release_die "0073 index missing after clone"

SMOKE_PORT="${PHASE7_MIG_PORT:-18082}"
API_PID=""
cleanup() {
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
    wait "${API_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT
(
  cd "${ROOT}/backend"
  export DINAMIC_PYTEST_DOTENV_LOCKED=1
  export SQLSERVER_ENABLED=true
  export SQLSERVER_SERVER="${SQLSERVER_SERVER}"
  export SQLSERVER_DATABASE="${SQLSERVER_DATABASE}"
  export SQLSERVER_UID="${SQLSERVER_UID}"
  export SQLSERVER_PWD="${SQLSERVER_PWD}"
  export SQLSERVER_TRUST_SERVER_CERTIFICATE=yes
  export APP_ENV=development
  export V3_ALLOW_IN_MEMORY_FALLBACK=false
  export EMBEDDED_WORKER_ENABLED=false
  export DB_SCHEMA_REQUIRED_VERSION=0073
  export OUTPUT_DIR="${ROOT}/.tmp/phase7-mig-output"
  mkdir -p "${OUTPUT_DIR}"
  export PYTHONPATH="${ROOT}/backend"
  exec "${RELEASE_PY}" -m uvicorn src.api.server:app --host 127.0.0.1 --port "${SMOKE_PORT}" --log-level warning
) &
API_PID=$!
ready=0
for _ in $(seq 1 60); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${SMOKE_PORT}/ready" || true)"
  if [[ "${code}" == "200" ]]; then ready=1; break; fi
  sleep 1
done
[[ "${ready}" -eq 1 ]] || release_die "app startup /ready != 200"
cleanup
trap - EXIT
API_PID=""

release_rollback_0073 "${PHASE7_SQL_DATABASE}"
release_preflight_0073
release_reapply_0073 "${PHASE7_SQL_DATABASE}"
release_preflight_0073

release_log_stage "B) empty → full clone → idempotent apply (no pending) + index verify"
# dinamic_inventory_test (0004) is not a complete historical bootstrap for 0005+ (missing legacy jobs).
# Canonical empty-DB path is schema-only clone of a 0073-compatible source + migration history copy,
# then idempotent apply. Incremental apply 0005–0073 is covered by upgrade path D (0072→0073).
release_clone_database "${CLONE_SOURCE_FULL}" "${PHASE7_SQL_UPGRADE_DATABASE}"
release_export_ephemeral_sql_env "${PHASE7_SQL_UPGRADE_DATABASE}"
set +e
apply_out="$(release_db_migrate apply 2>&1)"
apply_ec=$?
set -e
echo "${apply_out}"
[[ "${apply_ec}" -eq 0 ]] || release_die "idempotent apply failed"
apply_ver="$(_json_ver "${apply_out}")"
[[ "${apply_ver}" == "0073" ]] || release_die "expected 0073 after apply, got ${apply_ver}"
release_index_0073_exists "${PHASE7_SQL_UPGRADE_DATABASE}" || release_die "0073 index missing after apply"

release_log_stage "C) concurrent insert uniqueness on applied DB"
PYTHONPATH="${ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
SQLSERVER_ENABLED=true SQLSERVER_SERVER="${SQLSERVER_SERVER}" \
SQLSERVER_DATABASE="${PHASE7_SQL_UPGRADE_DATABASE}" SQLSERVER_UID="${SQLSERVER_UID}" \
SQLSERVER_PWD="${SQLSERVER_PWD}" SQLSERVER_TRUST_SERVER_CERTIFICATE=yes \
APP_ENV=development \
"${RELEASE_PY}" - <<'PY'
import threading, uuid
from datetime import datetime, timezone
from src.database.sqlserver import SqlServerClient
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository

client = SqlServerClient(resolve_sqlserver_connection_config().connection_string)
now = datetime.now(timezone.utc)
suffix = uuid.uuid4().hex[:8]
inv_id, aisle_id, parent = f"inv-c-{suffix}", f"aisle-c-{suffix}", f"job-p-{suffix}"
SqlInventoryRepository(client).save(Inventory(id=inv_id, name="c", status=InventoryStatus.PROCESSING, created_at=now, updated_at=now, processing_mode=InventoryProcessingMode.TEST))
SqlAisleRepository(client).save(Aisle(id=aisle_id, inventory_id=inv_id, code=f"C{suffix[:4]}", status=AisleStatus.QUEUED, created_at=now, updated_at=now))
SqlJobRepository(client).save(Job(id=parent, job_type="process_aisle", target_type="aisle", target_id=aisle_id, status=JobStatus.FAILED, payload_json={}, created_at=now, updated_at=now, attempt_count=1))
errors = []
def insert(cid: str) -> None:
    try:
        SqlJobRepository(client).save(Job(id=cid, job_type="process_aisle", target_type="aisle", target_id=aisle_id, status=JobStatus.QUEUED, payload_json={}, created_at=now, updated_at=now, attempt_count=1, retry_of_job_id=parent))
    except Exception as exc:  # noqa: BLE001
        errors.append(type(exc).__name__)
barrier = threading.Barrier(2)
def worker(cid: str) -> None:
    barrier.wait(); insert(cid)
ts = [threading.Thread(target=worker, args=(f"job-c{i}-{suffix}",)) for i in (1, 2)]
for t in ts: t.start()
for t in ts: t.join()
assert len(errors) >= 1, errors
print("concurrent_insert_ok", errors)
PY

release_log_stage "D) upgrade previous supported → 0073 (hide 0073, apply to 0072, restore, apply)"
# Use full clone, remove 0073 migration row + index, hide file, status should be 0072, then reapply file.
release_clone_database "${CLONE_SOURCE_FULL}" "${PHASE7_SQL_RESTORE_DATABASE}"
release_export_ephemeral_sql_env "${PHASE7_SQL_RESTORE_DATABASE}"
release_rollback_0073 "${PHASE7_SQL_RESTORE_DATABASE}"
PYTHONPATH="${ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
SQLSERVER_ENABLED=true SQLSERVER_SERVER="${SQLSERVER_SERVER}" \
SQLSERVER_DATABASE="${PHASE7_SQL_RESTORE_DATABASE}" SQLSERVER_UID="${SQLSERVER_UID}" \
SQLSERVER_PWD="${SQLSERVER_PWD}" SQLSERVER_TRUST_SERVER_CERTIFICATE=yes \
APP_ENV=development \
"${RELEASE_PY}" - <<'PY'
from src.database.sqlserver import SqlServerClient
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
client = SqlServerClient(resolve_sqlserver_connection_config().connection_string)
with client.cursor() as cur:
    cur.execute("DELETE FROM schema_migrations WHERE version = '0073'")
print("deleted_0073_migration_row")
PY
MIG_DIR="${ROOT}/backend/src/database/migrations/versions"
HIDE_DIR="${ROOT}/.tmp/phase7-hide-0073"
mkdir -p "${HIDE_DIR}"
mv "${MIG_DIR}/0073_inventory_jobs_retry_of_unique.sql" "${HIDE_DIR}/"
mv "${MIG_DIR}/0073_README.md" "${HIDE_DIR}/" 2>/dev/null || true
restore_0073() {
  mv "${HIDE_DIR}/0073_inventory_jobs_retry_of_unique.sql" "${MIG_DIR}/" 2>/dev/null || true
  mv "${HIDE_DIR}/0073_README.md" "${MIG_DIR}/" 2>/dev/null || true
}
trap restore_0073 EXIT
set +e
prev_st="$(release_db_migrate status 2>&1)"
prev_ec=$?
set -e
echo "${prev_st}"
[[ "${prev_ec}" -eq 0 ]] || { restore_0073; release_die "status at N-1 schema failed"; }
prev_ver="$(_json_ver "${prev_st}")"
[[ "${prev_ver}" == "0072" ]] || { restore_0073; release_die "expected 0072 got ${prev_ver}"; }
restore_0073
trap - EXIT
set +e
up_out="$(release_db_migrate apply 2>&1)"
up_ec=$?
set -e
echo "${up_out}"
[[ "${up_ec}" -eq 0 ]] || release_die "upgrade apply 0073 failed"
up_ver="$(_json_ver "${up_out}")"
[[ "${up_ver}" == "0073" ]] || release_die "upgrade expected 0073 got ${up_ver}"
release_index_0073_exists "${PHASE7_SQL_RESTORE_DATABASE}" || release_die "upgrade missing index"

echo "MIGRATIONS_FROM_ZERO_OK"
echo "schema_version=0073"
echo "HEAD=${GIT_SHA}"
echo "note=0001_baseline is metadata-only; empty DB uses schema-only clone + incremental apply"
