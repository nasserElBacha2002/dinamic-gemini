"""ResolveAisleJobForInventoryReadUseCase — Phase 6 aisle job read context."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    AisleNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.use_cases.resolve_aisle_job_for_inventory_read import (
    ResolveAisleJobForInventoryReadUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository

UTC = timezone.utc


def test_resolve_returns_job_when_valid() -> None:
    now = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
    job_repo = MemoryJobRepository()
    aisle_repo = MemoryAisleRepository()
    uc = ResolveAisleJobForInventoryReadUseCase(job_repo, aisle_repo)
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A1", AisleStatus.PROCESSED, now, now))
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    got_job = uc.execute("inv-1", "aisle-1", "job-1")
    assert got_job.id == "job-1"


def test_resolve_raises_when_job_missing() -> None:
    now = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
    job_repo = MemoryJobRepository()
    aisle_repo = MemoryAisleRepository()
    uc = ResolveAisleJobForInventoryReadUseCase(job_repo, aisle_repo)
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A1", AisleStatus.PROCESSED, now, now))
    with pytest.raises(JobNotFoundError):
        uc.execute("inv-1", "aisle-1", "missing-job")


def test_resolve_raises_when_job_wrong_target() -> None:
    now = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
    job_repo = MemoryJobRepository()
    aisle_repo = MemoryAisleRepository()
    uc = ResolveAisleJobForInventoryReadUseCase(job_repo, aisle_repo)
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A1", AisleStatus.PROCESSED, now, now))
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="other-aisle",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)
    with pytest.raises(JobDoesNotBelongToAisleError):
        uc.execute("inv-1", "aisle-1", "job-1")


def test_resolve_raises_when_aisle_missing() -> None:
    now = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
    job_repo = MemoryJobRepository()
    aisle_repo = MemoryAisleRepository()
    uc = ResolveAisleJobForInventoryReadUseCase(job_repo, aisle_repo)
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)
    with pytest.raises(AisleNotFoundError):
        uc.execute("inv-1", "aisle-1", "job-1")


def test_resolve_raises_when_aisle_not_in_inventory() -> None:
    now = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
    job_repo = MemoryJobRepository()
    aisle_repo = MemoryAisleRepository()
    uc = ResolveAisleJobForInventoryReadUseCase(job_repo, aisle_repo)
    aisle_repo.save(Aisle("aisle-1", "other-inv", "A1", AisleStatus.PROCESSED, now, now))
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)
    with pytest.raises(AisleNotFoundError):
        uc.execute("inv-1", "aisle-1", "job-1")
