"""SQL Server IT — finalization / cancel acknowledgement under lease fencing."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import FinalizationStatus
from src.domain.jobs.lease import LeaseWriteOutcome
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


def _seed_running(sql_client):
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    job_repo = SqlJobRepository(sql_client)
    now = _now()
    suffix = uuid.uuid4().hex[:10]
    inv_id = f"inv-fin-{suffix}"
    aisle_id = f"aisle-fin-{suffix}"
    job_id = f"job-fin-{suffix}"
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Finalization fence IT",
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
            code="F1",
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
            status=JobStatus.STARTING,
            payload_json={"aisle_id": aisle_id},
            created_at=now,
            updated_at=now,
        )
    )
    claim = job_repo.try_claim_starting_to_running(
        job_id,
        now=now,
        claim_owner_id=f"owner-a-{suffix}",
        aisle_id=aisle_id,
        lease_duration_seconds=60,
    )
    assert claim.lease is not None
    return job_repo, claim.lease, now


def test_sql_update_finalization_if_leased_rejects_stale(
    sql_client, _require_lease_columns
) -> None:
    job_repo, lease_a, now = _seed_running(sql_client)
    stolen = job_repo.reacquire_expired_lease(
        lease_a.job_id,
        now=now + timedelta(minutes=5),
        new_owner_id="owner-b",
        extension_seconds=60,
    )
    assert stolen.lease is not None

    result = job_repo.update_finalization_if_leased(
        lease_a,
        now=now + timedelta(minutes=5),
        mutator=lambda job: setattr(job, "finalization_status", FinalizationStatus.IN_PROGRESS),
    )
    assert result.outcome == LeaseWriteOutcome.LEASE_LOST


def test_sql_acknowledge_cancel_if_leased(sql_client, _require_lease_columns) -> None:
    job_repo, lease, now = _seed_running(sql_client)
    job = job_repo.get_by_id(lease.job_id)
    assert job is not None
    job.status = JobStatus.CANCEL_REQUESTED
    job_repo.save(job)

    applied = job_repo.acknowledge_cancel_if_leased(
        lease, now=now, reason="sql cancel ack"
    )
    assert applied.outcome == LeaseWriteOutcome.APPLIED
    done = job_repo.get_by_id(lease.job_id)
    assert done is not None
    assert done.status == JobStatus.CANCELED
