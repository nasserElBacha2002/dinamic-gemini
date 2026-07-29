"""SQL Server integration tests for Phase 3 job lease fencing.

Skipped automatically when SQL Server / ODBC is unavailable. These must run against
a real SQL Server (not mocks) before merge.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.claim import JobClaimOutcome
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.lease import LeaseRenewalOutcome, LeaseWriteOutcome
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


@pytest.fixture(scope="module")
def _require_lease_columns(sql_client):
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT name FROM sys.columns
            WHERE object_id = OBJECT_ID('inventory_jobs')
              AND name IN ('lease_fencing_token', 'lease_expires_at', 'lease_acquired_at', 'claim_owner_id')
            """
        )
        names = {str(getattr(r, "name", r[0])) for r in cur.fetchall()}
    required = {
        "lease_fencing_token",
        "lease_expires_at",
        "lease_acquired_at",
        "claim_owner_id",
    }
    missing = required - names
    if missing:
        pytest.skip(f"lease columns missing ({sorted(missing)}); apply migration 0072")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed(sql_client, *, job_status: JobStatus = JobStatus.STARTING):
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    job_repo = SqlJobRepository(sql_client)
    now = _now()
    suffix = uuid.uuid4().hex[:10]
    inv_id = f"inv-lease-{suffix}"
    aisle_id = f"aisle-lease-{suffix}"
    job_id = f"job-lease-{suffix}"
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Lease IT",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"L{suffix[:4]}",
            status=AisleStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
    )
    job_repo.save(
        Job(
            id=job_id,
            job_type="process_aisle",
            target_type="aisle",
            target_id=aisle_id,
            status=job_status,
            payload_json={"aisle_id": aisle_id},
            created_at=now,
            updated_at=now,
            attempt_count=1,
            execution_id=f"ex-{suffix}",
            started_at=now if job_status != JobStatus.QUEUED else None,
            last_heartbeat_at=now,
        )
    )
    return job_repo, aisle_repo, job_id, aisle_id


def test_sql_monotonic_fencing_token(sql_client, _require_lease_columns) -> None:
    job_repo, _aisle_repo, job_id, aisle_id = _seed(sql_client)
    now = _now()
    a = job_repo.try_claim_starting_to_running(
        job_id, now=now, claim_owner_id="owner-a", aisle_id=aisle_id, lease_duration_seconds=30
    )
    assert a.outcome == JobClaimOutcome.ACQUIRED
    assert a.lease is not None
    assert a.lease.fencing_token == 1

    after = now + timedelta(seconds=31)
    b = job_repo.reacquire_expired_lease(
        job_id, now=after, new_owner_id="owner-b", extension_seconds=30
    )
    assert b.outcome == JobClaimOutcome.ACQUIRED
    assert b.lease is not None
    assert b.lease.fencing_token == 2
    assert b.lease.fencing_token > a.lease.fencing_token


def test_sql_stale_heartbeat_rejected(sql_client, _require_lease_columns) -> None:
    job_repo, _aisle_repo, job_id, aisle_id = _seed(sql_client)
    now = _now()
    a = job_repo.try_claim_starting_to_running(
        job_id, now=now, claim_owner_id="owner-a", aisle_id=aisle_id, lease_duration_seconds=30
    )
    assert a.lease is not None
    after = now + timedelta(seconds=31)
    b = job_repo.reacquire_expired_lease(
        job_id, now=after, new_owner_id="owner-b", extension_seconds=60
    )
    assert b.lease is not None

    renew = job_repo.renew_lease(a.lease, now=after, extension_seconds=60)
    assert renew.outcome == LeaseRenewalOutcome.LEASE_LOST


def test_sql_stale_result_write_rejected(sql_client, _require_lease_columns) -> None:
    job_repo, _aisle_repo, job_id, aisle_id = _seed(sql_client)
    now = _now()
    a = job_repo.try_claim_starting_to_running(
        job_id, now=now, claim_owner_id="owner-a", aisle_id=aisle_id, lease_duration_seconds=30
    )
    assert a.lease is not None
    after = now + timedelta(seconds=31)
    b = job_repo.reacquire_expired_lease(
        job_id, now=after, new_owner_id="owner-b", extension_seconds=60
    )
    assert b.lease is not None

    stale, _ = job_repo.merge_result_json_if_leased(a.lease, {"stale": True}, now=after)
    assert stale.outcome == LeaseWriteOutcome.LEASE_LOST
    current, job = job_repo.merge_result_json_if_leased(b.lease, {"ok": True}, now=after)
    assert current.applied is True
    assert job is not None
    assert job.result_json.get("ok") is True
    assert "stale" not in (job.result_json or {})


def test_sql_stale_finalization_rejected(sql_client, _require_lease_columns) -> None:
    job_repo, _aisle_repo, job_id, aisle_id = _seed(sql_client)
    now = _now()
    a = job_repo.try_claim_starting_to_running(
        job_id, now=now, claim_owner_id="owner-a", aisle_id=aisle_id, lease_duration_seconds=30
    )
    assert a.lease is not None
    after = now + timedelta(seconds=31)
    b = job_repo.reacquire_expired_lease(
        job_id, now=after, new_owner_id="owner-b", extension_seconds=60
    )
    assert b.lease is not None

    job = job_repo.get_by_id(job_id)
    assert job is not None
    job.status = JobStatus.SUCCEEDED
    job.result_json = {"report_path": "/tmp/x"}
    stale = job_repo.complete_if_leased(a.lease, job, now=after)
    assert stale.outcome == LeaseWriteOutcome.LEASE_LOST
    persisted = job_repo.get_by_id(job_id)
    assert persisted is not None
    assert persisted.status == JobStatus.RUNNING

    current_job = job_repo.get_by_id(job_id)
    assert current_job is not None
    current_job.status = JobStatus.SUCCEEDED
    current_job.result_json = {"report_path": "/tmp/ok"}
    ok = job_repo.complete_if_leased(b.lease, current_job, now=after)
    assert ok.applied is True
    persisted = job_repo.get_by_id(job_id)
    assert persisted is not None
    assert persisted.status == JobStatus.SUCCEEDED


def test_sql_dual_connection_lease_steal(sql_client, _require_lease_columns) -> None:
    """Two independent repository instances / connections compete after expiry."""
    job_repo, _aisle_repo, job_id, aisle_id = _seed(sql_client)
    now = _now()
    a = job_repo.try_claim_starting_to_running(
        job_id, now=now, claim_owner_id="owner-a", aisle_id=aisle_id, lease_duration_seconds=30
    )
    assert a.lease is not None
    after = now + timedelta(seconds=31)
    barrier = threading.Barrier(2)
    outcomes: list[JobClaimOutcome] = []
    tokens: list[int] = []
    lock = threading.Lock()

    def worker(owner: str) -> None:
        local = SqlJobRepository(sql_client)
        barrier.wait()
        result = local.reacquire_expired_lease(
            job_id, now=after, new_owner_id=owner, extension_seconds=60
        )
        with lock:
            outcomes.append(result.outcome)
            if result.lease is not None:
                tokens.append(result.lease.fencing_token)

    threads = [
        threading.Thread(target=worker, args=("owner-b",)),
        threading.Thread(target=worker, args=("owner-c",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert outcomes.count(JobClaimOutcome.ACQUIRED) == 1
    assert outcomes.count(JobClaimOutcome.CONFLICT) == 1
    assert tokens == [2]
