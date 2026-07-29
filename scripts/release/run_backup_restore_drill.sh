#!/usr/bin/env bash
# Phase 7 — backup/restore drill on ephemeral test databases (never production).
#
# This environment's SQL Server Docker rejects BACKUP DATABASE ... TO DISK
# (Error 3041 / OpenMedia). The drill therefore performs a verified *logical*
# backup/restore: CREATE empty DB + copy schema_migrations + business tables
# from a seeded source, then validate schema/counts/API against the restored DB.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/release/_common.sh
source "${ROOT}/scripts/release/_common.sh"

START_TS="$(date +%s)"

release_require_cmd git
release_require_python
release_require_sha
release_ensure_sql_available

release_drop_database "${PHASE7_SQL_BACKUP_DATABASE}"
release_drop_database "${PHASE7_SQL_RESTORE_DATABASE}"

# Real (non-clone) source DB with full schema: restore schema via clone then
# convert by re-creating as non-clone using SELECT INTO into a fresh CREATE DB.
release_log_stage "1) create real seeded backup_src (non-clone)"
release_create_database "${PHASE7_SQL_BACKUP_DATABASE}"
# Copy schema objects from dinamic-gemini into backup_src via SELECT INTO for core tables
# plus schema_migrations; also create minimal supporting tables used by FKs when needed.
PYTHONPATH="${ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
SQLSERVER_DATABASE=master \
SQLSERVER_SERVER="${SQLSERVER_SERVER}" SQLSERVER_UID="${SQLSERVER_UID}" \
SQLSERVER_PWD="${SQLSERVER_PWD}" SQLSERVER_ENABLED=true \
SQLSERVER_TRUST_SERVER_CERTIFICATE=yes APP_ENV=development \
"${RELEASE_PY}" - <<PY
import pyodbc
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config

src = """${PHASE7_CLONE_SOURCE_FULL:-dinamic-gemini}"""
dst = """${PHASE7_SQL_BACKUP_DATABASE}"""
conn = pyodbc.connect(resolve_sqlserver_connection_config().connection_string, autocommit=True)
cur = conn.cursor()
# Copy migration history + core operational tables (logical backup payload).
tables = [
    "schema_migrations",
    "inventories",
    "aisles",
    "inventory_jobs",
]
for table in tables:
    cur.execute(
        f"""
        IF OBJECT_ID(N'[{dst}].dbo.[{table}]', 'U') IS NOT NULL
            DROP TABLE [{dst}].dbo.[{table}];
        SELECT * INTO [{dst}].dbo.[{table}] FROM [{src}].dbo.[{table}];
        """
    )
    cur.execute(f"SELECT COUNT(*) FROM [{dst}].dbo.[{table}]")
    print(f"copied {table} rows={cur.fetchone()[0]}")
# Recreate 0073 unique index on inventory_jobs if column exists
cur.execute(
    f"""
    IF COL_LENGTH(N'[{dst}].dbo.inventory_jobs', 'retry_of_job_id') IS NOT NULL
       AND NOT EXISTS (
         SELECT 1 FROM [{dst}].sys.indexes WHERE name = N'UX_inventory_jobs_retry_of_job_id'
       )
    BEGIN
      EXEC(N'USE [{dst}];
        CREATE UNIQUE NONCLUSTERED INDEX UX_inventory_jobs_retry_of_job_id
          ON dbo.inventory_jobs(retry_of_job_id) WHERE retry_of_job_id IS NOT NULL;');
    END
    """
)
print("logical_backup_src_ready")
cur.close(); conn.close()
PY

release_export_ephemeral_sql_env "${PHASE7_SQL_BACKUP_DATABASE}"

release_log_stage "2) seed synthetic historical job on backup_src"
PYTHONPATH="${ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
SQLSERVER_ENABLED=true SQLSERVER_SERVER="${SQLSERVER_SERVER}" \
SQLSERVER_DATABASE="${SQLSERVER_DATABASE}" SQLSERVER_UID="${SQLSERVER_UID}" \
SQLSERVER_PWD="${SQLSERVER_PWD}" SQLSERVER_TRUST_SERVER_CERTIFICATE=yes \
APP_ENV=development \
"${RELEASE_PY}" - <<'PY'
import uuid
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
inv_id, aisle_id, job_id = f"inv-bak-{suffix}", f"aisle-bak-{suffix}", f"job-bak-{suffix}"
SqlInventoryRepository(client).save(Inventory(id=inv_id, name="backup-seed", status=InventoryStatus.PROCESSING, created_at=now, updated_at=now, processing_mode=InventoryProcessingMode.TEST))
SqlAisleRepository(client).save(Aisle(id=aisle_id, inventory_id=inv_id, code=f"B{suffix[:4]}", status=AisleStatus.QUEUED, created_at=now, updated_at=now))
SqlJobRepository(client).save(Job(id=job_id, job_type="process_aisle", target_type="aisle", target_id=aisle_id, status=JobStatus.SUCCEEDED, payload_json={"seed": True}, created_at=now, updated_at=now, attempt_count=1))
print(f"seed_job_id={job_id}")
open("/tmp/phase7_backup_job_id.txt", "w", encoding="utf-8").write(job_id)
PY
SEED_JOB="$(cat /tmp/phase7_backup_job_id.txt)"

release_log_stage "3) logical restore → restore_test (SELECT INTO copy)"
release_create_database "${PHASE7_SQL_RESTORE_DATABASE}"
PYTHONPATH="${ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
SQLSERVER_DATABASE=master \
SQLSERVER_SERVER="${SQLSERVER_SERVER}" SQLSERVER_UID="${SQLSERVER_UID}" \
SQLSERVER_PWD="${SQLSERVER_PWD}" SQLSERVER_ENABLED=true \
SQLSERVER_TRUST_SERVER_CERTIFICATE=yes APP_ENV=development \
"${RELEASE_PY}" - <<PY
import pyodbc
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config

src = """${PHASE7_SQL_BACKUP_DATABASE}"""
dst = """${PHASE7_SQL_RESTORE_DATABASE}"""
conn = pyodbc.connect(resolve_sqlserver_connection_config().connection_string, autocommit=True)
cur = conn.cursor()
tables = ["schema_migrations", "inventories", "aisles", "inventory_jobs"]
for table in tables:
    cur.execute(
        f"""
        IF OBJECT_ID(N'[{dst}].dbo.[{table}]', 'U') IS NOT NULL
            DROP TABLE [{dst}].dbo.[{table}];
        SELECT * INTO [{dst}].dbo.[{table}] FROM [{src}].dbo.[{table}];
        """
    )
    cur.execute(f"SELECT COUNT(*) FROM [{dst}].dbo.[{table}]")
    print(f"restored {table} rows={cur.fetchone()[0]}")
cur.execute(
    f"""
    IF COL_LENGTH(N'[{dst}].dbo.inventory_jobs', 'retry_of_job_id') IS NOT NULL
       AND NOT EXISTS (
         SELECT 1 FROM [{dst}].sys.indexes WHERE name = N'UX_inventory_jobs_retry_of_job_id'
       )
    BEGIN
      EXEC(N'USE [{dst}];
        CREATE UNIQUE NONCLUSTERED INDEX UX_inventory_jobs_retry_of_job_id
          ON dbo.inventory_jobs(retry_of_job_id) WHERE retry_of_job_id IS NOT NULL;');
    END
    """
)
print("logical_restore_ok")
cur.close(); conn.close()
PY

release_log_stage "4) verify schema version + counts + historical job"
release_export_ephemeral_sql_env "${PHASE7_SQL_RESTORE_DATABASE}"
set +e
st_out="$(release_db_migrate status 2>&1)"
st_ec=$?
set -e
echo "${st_out}"
[[ "${st_ec}" -eq 0 ]] || release_die "restored status failed"
echo "${st_out}" | grep -q '"current_version": "0073"' || release_die "restored schema not 0073"
release_index_0073_exists "${PHASE7_SQL_RESTORE_DATABASE}" || release_die "restored missing 0073 index"

PYTHONPATH="${ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
SQLSERVER_ENABLED=true SQLSERVER_SERVER="${SQLSERVER_SERVER}" \
SQLSERVER_DATABASE="${SQLSERVER_DATABASE}" SQLSERVER_UID="${SQLSERVER_UID}" \
SQLSERVER_PWD="${SQLSERVER_PWD}" SQLSERVER_TRUST_SERVER_CERTIFICATE=yes \
APP_ENV=development SEED_JOB="${SEED_JOB}" \
"${RELEASE_PY}" - <<'PY'
import os
from src.database.sqlserver import SqlServerClient
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
job_id = os.environ["SEED_JOB"]
client = SqlServerClient(resolve_sqlserver_connection_config().connection_string)
with client.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM dbo.inventory_jobs")
    jobs = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM dbo.inventories")
    invs = int(cur.fetchone()[0])
job = SqlJobRepository(client).get_by_id(job_id)
assert job is not None, job_id
assert job.status.value == "succeeded"
print(f"counts jobs={jobs} inventories={invs} historical_job={job_id}")
PY

release_log_stage "5) API against restored DB"
SMOKE_PORT="${PHASE7_RESTORE_PORT:-18083}"
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
  export OUTPUT_DIR="${ROOT}/.tmp/phase7-restore-output"
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
[[ "${ready}" -eq 1 ]] || release_die "API on restored DB /ready != 200"
cleanup
trap - EXIT

END_TS="$(date +%s)"
echo "BACKUP_RESTORE_DRILL_OK"
echo "mode=logical_select_into"
echo "physical_backup=unavailable_error_3041_docker_sql"
echo "duration_sec=$((END_TS - START_TS))"
echo "seed_job=${SEED_JOB}"
echo "HEAD=${GIT_SHA}"
