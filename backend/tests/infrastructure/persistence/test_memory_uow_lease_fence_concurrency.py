"""Concurrent Memory UoW fence hold closes TOCTOU between assert and commit."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.lease import JobLease, LeaseRenewalOutcome
from src.infrastructure.persistence.memory_job_result_unit_of_work import (
    MemoryJobResultUnitOfWork,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository


def _now() -> datetime:
    return datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)


def test_memory_uow_fence_blocks_concurrent_lease_renewal_until_exit() -> None:
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository(aisle_repo=aisle_repo)
    now = _now()
    aisle_id = "aisle-1"
    job_id = "job-1"
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id="inv-1",
            code="A1",
            status=AisleStatus.PROCESSING,
            created_at=now,
            updated_at=now,
        )
    )
    job = Job(
        id=job_id,
        job_type="process_aisle",
        target_type="aisle",
        target_id=aisle_id,
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
        claim_owner_id="owner-a",
        lease_fencing_token=1,
        lease_acquired_at=now,
        lease_expires_at=now + timedelta(minutes=5),
    )
    job_repo.save(job)
    lease = JobLease(
        job_id=job_id,
        owner_id="owner-a",
        fencing_token=1,
        acquired_at=now,
        expires_at=now + timedelta(minutes=5),
    )

    fence_started = threading.Event()
    renew_finished = threading.Event()
    renew_outcome: list = []

    def uow_worker() -> None:
        uow = MemoryJobResultUnitOfWork(repositories=__import__("unittest.mock").mock.MagicMock(), job_repo=job_repo)
        with uow:
            assert uow.fence_job_lease(lease, now=now) is True
            fence_started.set()
            time.sleep(0.15)
            uow.commit()

    def renew_worker() -> None:
        fence_started.wait(timeout=2.0)
        result = job_repo.renew_lease(lease, now=now, extension_seconds=120)
        renew_outcome.append(result.outcome)
        renew_finished.set()

    t_uow = threading.Thread(target=uow_worker)
    t_renew = threading.Thread(target=renew_worker)
    t_uow.start()
    t_renew.start()
    t_uow.join(timeout=3.0)
    t_renew.join(timeout=3.0)

    assert renew_finished.is_set()
    assert renew_outcome
    assert renew_outcome[0] == LeaseRenewalOutcome.RENEWED
    renewed = job_repo.get_by_id(job_id)
    assert renewed is not None
    assert renewed.lease_expires_at == now + timedelta(seconds=120)
