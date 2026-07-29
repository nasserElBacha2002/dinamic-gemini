"""SQL Server integration tests for atomic job claim / stale reclaim (Phase 1 corrections).

Skipped automatically when SQL Server / ODBC is unavailable. CI should provide SQL Server
(or a dockerized instance) so these tests execute before merge.
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
def _require_claim_owner_column(sql_client):
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'claim_owner_id'
            """
        )
        if cur.fetchone() is None:
            pytest.skip("claim_owner_id missing; apply migration 0071")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_job_aisle(sql_client, *, job_status: JobStatus = JobStatus.STARTING):
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    job_repo = SqlJobRepository(sql_client)
    now = _now()
    suffix = uuid.uuid4().hex[:10]
    inv_id = f"inv-claim-{suffix}"
    aisle_id = f"aisle-claim-{suffix}"
    job_id = f"job-claim-{suffix}"
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Claim IT",
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
            code=f"C{suffix[:4]}",
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


def test_sql_concurrent_claim_one_winner(
    sql_client, _require_claim_owner_column
) -> None:
    job_repo, aisle_repo, job_id, aisle_id = _seed_job_aisle(sql_client)
    barrier = threading.Barrier(2)
    outcomes: list[JobClaimOutcome] = []
    may_flags: list[bool] = []
    lock = threading.Lock()
    now = _now()

    def worker(owner: str) -> None:
        # Separate repository/client usage: each call opens its own connection/txn.
        local_repo = SqlJobRepository(sql_client)
        barrier.wait()
        result = local_repo.try_claim_starting_to_running(
            job_id, now=now, claim_owner_id=owner, aisle_id=aisle_id
        )
        with lock:
            outcomes.append(result.outcome)
            may_flags.append(result.may_execute)

    threads = [
        threading.Thread(target=worker, args=("owner-a",)),
        threading.Thread(target=worker, args=("owner-b",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count(JobClaimOutcome.ACQUIRED) == 1
    assert outcomes.count(JobClaimOutcome.CONFLICT) == 1
    assert may_flags.count(True) == 1
    job = job_repo.get_by_id(job_id)
    assert job is not None
    assert job.status == JobStatus.RUNNING
    assert job.claim_owner_id in {"owner-a", "owner-b"}
    aisle = aisle_repo.get_by_id(aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.PROCESSING


def test_sql_stale_reclaim_one_winner(sql_client, _require_claim_owner_column) -> None:
    job_repo, aisle_repo, job_id, aisle_id = _seed_job_aisle(
        sql_client, job_status=JobStatus.RUNNING
    )
    old = _now() - timedelta(hours=2)
    job = job_repo.get_by_id(job_id)
    assert job is not None
    job.last_heartbeat_at = old
    job.updated_at = old
    job.claim_owner_id = "owner-stale"
    job_repo.save(job)
    aisle = aisle_repo.get_by_id(aisle_id)
    assert aisle is not None
    aisle.status = AisleStatus.PROCESSING
    aisle.updated_at = old
    aisle_repo.save(aisle)

    barrier = threading.Barrier(2)
    wins: list[bool] = []
    lock = threading.Lock()
    now = _now()

    def recovery() -> None:
        local = SqlJobRepository(sql_client)
        barrier.wait()
        result = local.try_reclaim_stale_job_and_reconcile_aisle(
            job_id, now=now, stale_after_seconds=60
        )
        with lock:
            wins.append(result.won)

    threads = [threading.Thread(target=recovery) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert wins.count(True) == 1
    assert wins.count(False) == 1
    refreshed = job_repo.get_by_id(job_id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.FAILED
    aisle2 = aisle_repo.get_by_id(aisle_id)
    assert aisle2 is not None
    assert aisle2.status == AisleStatus.FAILED


def test_sql_claim_rollback_on_invalid_aisle(
    sql_client, _require_claim_owner_column
) -> None:
    job_repo, aisle_repo, job_id, aisle_id = _seed_job_aisle(sql_client)
    aisle = aisle_repo.get_by_id(aisle_id)
    assert aisle is not None
    aisle.status = AisleStatus.FAILED
    aisle.updated_at = _now()
    aisle_repo.save(aisle)

    result = job_repo.try_claim_starting_to_running(
        job_id, now=_now(), claim_owner_id="owner-x", aisle_id=aisle_id
    )
    assert result.outcome == JobClaimOutcome.TARGET_INVALID_STATUS
    job = job_repo.get_by_id(job_id)
    assert job is not None
    assert job.status == JobStatus.STARTING
    aisle2 = aisle_repo.get_by_id(aisle_id)
    assert aisle2 is not None
    assert aisle2.status == AisleStatus.FAILED
