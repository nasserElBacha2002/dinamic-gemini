"""Characterization: Memory UoW fence returns False when unbound; Persist falls back."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.application.errors import FencingConfigurationError
from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.domain.jobs.lease import JobLease, JobLeaseLostError, LeaseWriteOutcome, LeaseWriteResult
from src.infrastructure.persistence.memory_job_result_unit_of_work import (
    MemoryJobResultUnitOfWork,
)


def _lease() -> JobLease:
    now = datetime.now(timezone.utc)
    return JobLease(
        job_id="j1",
        owner_id="o1",
        fencing_token=1,
        acquired_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def test_memory_uow_fence_unbound_returns_false() -> None:
    uow = MemoryJobResultUnitOfWork(
        repositories=MagicMock(),
        job_repo=None,
    )
    assert uow.fence_job_lease(_lease(), now=datetime.now(timezone.utc)) is False


def test_memory_uow_fence_bound_asserts_lease() -> None:
    job_repo = MagicMock()
    job_repo.assert_lease = MagicMock(
        return_value=LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
    )
    uow = MemoryJobResultUnitOfWork(repositories=MagicMock(), job_repo=job_repo)
    lease = _lease()
    now = datetime.now(timezone.utc)
    assert uow.fence_job_lease(lease, now=now) is True
    job_repo.assert_lease.assert_called_once_with(lease, now=now)


def test_persist_fence_raises_when_uow_false_and_no_job_repo() -> None:
    class _UnboundFenceUow:
        def fence_job_lease(self, lease, *, now):
            return False

    uc = PersistAisleResultUseCase.__new__(PersistAisleResultUseCase)
    uc._job_repo = None

    command = PersistAisleResultCommand(
        aisle_id="a1",
        job_id="j1",
        report={},
        run_dir=MagicMock(),
        lease=_lease(),
    )
    with pytest.raises(FencingConfigurationError):
        uc._fence_domain_persist(_UnboundFenceUow(), command, now=datetime.now(timezone.utc))


def test_persist_fence_falls_back_when_uow_returns_false() -> None:
    job_repo = MagicMock()
    job_repo.assert_lease = MagicMock(
        return_value=LeaseWriteResult(
            outcome=LeaseWriteOutcome.LEASE_LOST,
            reason="lease_expired",
        )
    )

    class _UnboundFenceUow:
        def fence_job_lease(self, lease, *, now):
            return False

    uc = PersistAisleResultUseCase.__new__(PersistAisleResultUseCase)
    uc._job_repo = job_repo

    command = PersistAisleResultCommand(
        aisle_id="a1",
        job_id="j1",
        report={},
        run_dir=MagicMock(),
        lease=_lease(),
    )
    with pytest.raises(JobLeaseLostError):
        uc._fence_domain_persist(_UnboundFenceUow(), command, now=datetime.now(timezone.utc))
    job_repo.assert_lease.assert_called_once()


def test_persist_fence_skips_job_repo_when_uow_fenced() -> None:
    job_repo = MagicMock()
    job_repo.assert_lease = MagicMock()

    class _FencedUow:
        def fence_job_lease(self, lease, *, now):
            return True

    uc = PersistAisleResultUseCase.__new__(PersistAisleResultUseCase)
    uc._job_repo = job_repo

    command = PersistAisleResultCommand(
        aisle_id="a1",
        job_id="j1",
        report={},
        run_dir=MagicMock(),
        lease=_lease(),
    )
    uc._fence_domain_persist(_FencedUow(), command, now=datetime.now(timezone.utc))
    job_repo.assert_lease.assert_not_called()
