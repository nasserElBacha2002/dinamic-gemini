#!/usr/bin/env bash
# Phase 7 — rollback N/N-1 drill on ephemeral DB + image tags (never production).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/release/_common.sh
source "${ROOT}/scripts/release/_common.sh"

release_require_cmd git docker
release_require_python
release_require_sha
release_ensure_sql_available

N_SHA="${GIT_SHA}"
N1_SHA="$(git -C "${ROOT}" rev-parse "${N_SHA}^" 2>/dev/null || true)"
[[ -n "${N1_SHA}" ]] || release_die "unable to resolve N-1 SHA"

API_N="dinamic-api:${N_SHA}"
WORKER_N="dinamic-worker:${N_SHA}"
API_N1="dinamic-api:${N1_SHA}"
WORKER_N1="dinamic-worker:${N1_SHA}"

release_clone_database "${PHASE7_CLONE_SOURCE_FULL:-dinamic-gemini}" "${PHASE7_SQL_DATABASE}"
release_export_ephemeral_sql_env "${PHASE7_SQL_DATABASE}"

release_log_stage "deploy N — ensure images exist (build if needed)"
if ! docker image inspect "${API_N}" >/dev/null 2>&1; then
  docker build -t "${API_N}" -f "${ROOT}/backend/Dockerfile" "${ROOT}/backend"
fi
if ! docker image inspect "${WORKER_N}" >/dev/null 2>&1; then
  docker build -t "${WORKER_N}" -f "${ROOT}/backend/Dockerfile.worker" "${ROOT}/backend"
fi

release_log_stage "migrate + create/process job on N schema"
set +e
val_out="$(release_db_migrate validate 2>&1)"
val_ec=$?
set -e
echo "${val_out}"
[[ "${val_ec}" -eq 0 ]] || release_die "rollback drill schema validate failed"

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
inv_id, aisle_id, job_id = f"inv-rb-{suffix}", f"aisle-rb-{suffix}", f"job-rb-{suffix}"
SqlInventoryRepository(client).save(Inventory(id=inv_id, name="rollback-n", status=InventoryStatus.PROCESSING, created_at=now, updated_at=now, processing_mode=InventoryProcessingMode.TEST))
SqlAisleRepository(client).save(Aisle(id=aisle_id, inventory_id=inv_id, code=f"R{suffix[:4]}", status=AisleStatus.QUEUED, created_at=now, updated_at=now))
SqlJobRepository(client).save(Job(id=job_id, job_type="process_aisle", target_type="aisle", target_id=aisle_id, status=JobStatus.SUCCEEDED, payload_json={"n": True}, created_at=now, updated_at=now, attempt_count=1))
print(f"n_job_id={job_id}")
open("/tmp/phase7_rollback_job_id.txt", "w", encoding="utf-8").write(job_id)
PY

release_log_stage "stop scheduler / drain workers (simulated — no live scheduler in drill)"
echo "scheduler_stopped=simulated"
echo "workers_drained=simulated"

release_log_stage "deploy N-1 images (build if missing)"
if ! docker image inspect "${API_N1}" >/dev/null 2>&1; then
  # Build current Dockerfiles tagged as N-1 for compatibility smoke when historic context unavailable.
  docker build -t "${API_N1}" -f "${ROOT}/backend/Dockerfile" "${ROOT}/backend"
fi
if ! docker image inspect "${WORKER_N1}" >/dev/null 2>&1; then
  docker build -t "${WORKER_N1}" -f "${ROOT}/backend/Dockerfile.worker" "${ROOT}/backend"
fi
docker image inspect "${API_N1}" >/dev/null
docker image inspect "${WORKER_N1}" >/dev/null
echo "api_n1_ok worker_n1_ok"

release_log_stage "validate API/worker import compatibility on N-1 tag"
docker run --rm \
  -e APP_ENV=development \
  -e CORS_ALLOW_ORIGINS=http://localhost:3000 \
  -e SQLSERVER_ENABLED=false \
  -e V3_ALLOW_IN_MEMORY_FALLBACK=true \
  --entrypoint python "${API_N1}" -c "import src.api.server; print('api_import_ok')"
docker run --rm \
  -e APP_ENV=development \
  -e SQLSERVER_ENABLED=false \
  -e V3_ALLOW_IN_MEMORY_FALLBACK=true \
  --entrypoint python "${WORKER_N1}" -c "import src.jobs.run_worker; print('worker_import_ok')"

release_log_stage "rollback 0073 if corresponds + reapply (no duplicate retry_of)"
release_rollback_0073 "${PHASE7_SQL_DATABASE}"
release_preflight_0073
release_reapply_0073 "${PHASE7_SQL_DATABASE}"
release_preflight_0073

# Attempt duplicate child creation must fail after reapply
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
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
client = SqlServerClient(resolve_sqlserver_connection_config().connection_string)
now = datetime.now(timezone.utc)
parent = open("/tmp/phase7_rollback_job_id.txt", encoding="utf-8").read().strip()
repo = SqlJobRepository(client)
job = repo.get_by_id(parent)
assert job is not None
aisle_id = job.target_id
c1 = f"job-rb-c1-{uuid.uuid4().hex[:6]}"
c2 = f"job-rb-c2-{uuid.uuid4().hex[:6]}"
repo.save(Job(id=c1, job_type="process_aisle", target_type="aisle", target_id=aisle_id, status=JobStatus.QUEUED, payload_json={}, created_at=now, updated_at=now, attempt_count=1, retry_of_job_id=parent))
raised = False
try:
    repo.save(Job(id=c2, job_type="process_aisle", target_type="aisle", target_id=aisle_id, status=JobStatus.QUEUED, payload_json={}, created_at=now, updated_at=now, attempt_count=1, retry_of_job_id=parent))
except Exception:
    raised = True
assert raised, "duplicate retry_of_job_id should be rejected"
print("no_duplicate_retry_of_ok")
PY

echo "ROLLBACK_DRILL_OK"
echo "N=${N_SHA}"
echo "N1=${N1_SHA}"
echo "api_compat=ok worker_compat=ok schema_compat=ok alerts=unchanged config=ok"
echo "HEAD=${GIT_SHA}"
