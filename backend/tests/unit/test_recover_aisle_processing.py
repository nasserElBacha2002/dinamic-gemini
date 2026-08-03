"""Unit tests for RecoverAisleProcessingUseCase (memory fakes)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

from src.application.services.aisle_processing_state import AisleProcessingStateView
from src.application.use_cases.recovery.recover_aisle_processing import (
    RecoverAisleProcessingCommand,
    RecoverAisleProcessingOutcome,
    RecoverAisleProcessingUseCase,
)
from src.application.use_cases.recovery.recover_stale_job import (
    RecoverStaleJobOutcome,
    RecoverStaleJobResult,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@dataclass
class _StatusResult:
    aisle: Aisle
    latest_job: Job | None
    recent_jobs: tuple[Job, ...] = field(default_factory=tuple)


def _aisle(*, operational_job_id: str | None = None) -> Aisle:
    now = datetime.now(timezone.utc)
    return Aisle(
        id="a1",
        inventory_id="inv1",
        code="A1",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        operational_job_id=operational_job_id,
    )


def _job(*, job_id: str, status: JobStatus, age_s: int = 0, owner: str | None = None) -> Job:
    now = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return Job(
        id=job_id,
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=status,
        payload_json={"idempotency_key": "k1"},
        created_at=now,
        updated_at=now,
        started_at=now,
        claim_owner_id=owner,
        lease_expires_at=(now + timedelta(minutes=5)) if owner else None,
        last_heartbeat_at=now if owner else None,
    )


def test_alive_job_with_lease_is_not_canceled():
    now = datetime.now(timezone.utc)
    job = _job(job_id="j-live", status=JobStatus.RUNNING, owner="w1")
    job.lease_expires_at = now + timedelta(minutes=5)
    job.last_heartbeat_at = now
    aisle = _aisle(operational_job_id=job.id)

    status_uc = MagicMock()
    status_uc.execute.return_value = _StatusResult(aisle=aisle, latest_job=job, recent_jobs=(job,))

    recover_stale = MagicMock()
    cancel_job = MagicMock()
    job_repo = MagicMock()
    job_repo.get_by_id.return_value = job
    aisle_repo = MagicMock()
    aisle_repo.get_by_id.return_value = aisle

    uc = RecoverAisleProcessingUseCase(
        status_use_case=status_uc,
        recover_stale=recover_stale,
        cancel_job=cancel_job,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=_Clock(now),
    )
    result = uc.execute(
        RecoverAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", actor="tester", stale_after_seconds=60
        )
    )
    assert result.outcome is RecoverAisleProcessingOutcome.JOB_ALIVE
    recover_stale.execute.assert_not_called()
    cancel_job.execute.assert_not_called()


def test_queued_orphan_is_canceled():
    now = datetime.now(timezone.utc)
    job = _job(job_id="j-orphan", status=JobStatus.QUEUED, age_s=10_000)
    aisle = _aisle(operational_job_id=job.id)

    status_uc = MagicMock()
    # First call: recovery required; after cancel: idle/failed path with canceled job.
    canceled = _job(job_id="j-orphan", status=JobStatus.CANCELED, age_s=10_000)
    status_uc.execute.side_effect = [
        _StatusResult(aisle=aisle, latest_job=job, recent_jobs=(job,)),
        _StatusResult(aisle=_aisle(operational_job_id=None), latest_job=canceled, recent_jobs=(canceled,)),
    ]

    recover_stale = MagicMock()
    cancel_job = MagicMock()
    cancel_job.execute.return_value = canceled
    job_repo = MagicMock()
    job_repo.get_by_id.return_value = job
    aisle_repo = MagicMock()
    aisle_repo.get_by_id.return_value = aisle
    aisle_repo.save = MagicMock()

    uc = RecoverAisleProcessingUseCase(
        status_use_case=status_uc,
        recover_stale=recover_stale,
        cancel_job=cancel_job,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=_Clock(now),
    )
    result = uc.execute(
        RecoverAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", actor="tester", stale_after_seconds=60
        )
    )
    assert result.outcome is RecoverAisleProcessingOutcome.ORPHAN_CANCELED
    cancel_job.execute.assert_called_once()
    recover_stale.execute.assert_not_called()


def test_recover_stale_relaunch_outcome():
    now = datetime.now(timezone.utc)
    job = _job(job_id="j-stale", status=JobStatus.STARTING, age_s=10_000)
    job.failure_code = "WORKER_LAUNCH_FAILED"
    aisle = _aisle(operational_job_id=job.id)
    child = _job(job_id="j-child", status=JobStatus.QUEUED)

    status_uc = MagicMock()
    status_uc.execute.side_effect = [
        _StatusResult(aisle=aisle, latest_job=job, recent_jobs=(job,)),
        _StatusResult(aisle=_aisle(operational_job_id=child.id), latest_job=child, recent_jobs=(child,)),
    ]
    recover_stale = MagicMock()
    recover_stale.execute.return_value = RecoverStaleJobResult(
        RecoverStaleJobOutcome.RELAUNCHED, job.id, new_job_id=child.id
    )
    cancel_job = MagicMock()
    job_repo = MagicMock()
    job_repo.get_by_id.return_value = job
    aisle_repo = MagicMock()
    aisle_repo.get_by_id.return_value = aisle
    aisle_repo.save = MagicMock()

    uc = RecoverAisleProcessingUseCase(
        status_use_case=status_uc,
        recover_stale=recover_stale,
        cancel_job=cancel_job,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=_Clock(now),
    )
    result = uc.execute(
        RecoverAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", actor="tester", stale_after_seconds=60
        )
    )
    assert result.outcome is RecoverAisleProcessingOutcome.RELAUNCHED
    assert result.new_job_id == child.id
