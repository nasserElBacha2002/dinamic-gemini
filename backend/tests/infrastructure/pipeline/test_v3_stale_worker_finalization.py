"""Stale worker finalization: tracker + domain marker fencing."""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.domain.jobs.finalization import CurrentFinalizationStep
from src.domain.jobs.lease import JobLeaseLostError
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from tests.support.worker_phase1.executor_harness import ExecutorHarness, FixedClock


def test_stale_begin_rejected(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    lease = harness.lease()
    # Steal lease for another owner.
    reacquired = harness.job_repo.reacquire_expired_lease(
        harness.job_id,
        now=harness.now + timedelta(hours=2),
        new_owner_id="owner-b",
        extension_seconds=60,
    )
    assert reacquired.lease is not None
    tracker = JobFinalizationTracker(
        job_repo=harness.job_repo,
        clock=FixedClock(harness.now + timedelta(hours=2)),
        job_id=harness.job_id,
        lease=lease,
    )
    with pytest.raises(JobLeaseLostError):
        tracker.begin()


def test_stale_advance_rejected(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    lease = harness.lease()
    tracker = JobFinalizationTracker(
        job_repo=harness.job_repo,
        clock=FixedClock(harness.now),
        job_id=harness.job_id,
        lease=lease,
    )
    tracker.begin()
    harness.job_repo.reacquire_expired_lease(
        harness.job_id,
        now=harness.now + timedelta(hours=2),
        new_owner_id="owner-b",
        extension_seconds=60,
    )
    with pytest.raises(JobLeaseLostError):
        tracker.set_current_step(CurrentFinalizationStep.PUBLISH_ARTIFACTS)


def test_stale_failure_marker_rejected(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    lease = harness.lease()
    tracker = JobFinalizationTracker(
        job_repo=harness.job_repo,
        clock=FixedClock(harness.now),
        job_id=harness.job_id,
        lease=lease,
    )
    tracker.begin()
    harness.job_repo.reacquire_expired_lease(
        harness.job_id,
        now=harness.now + timedelta(hours=2),
        new_owner_id="owner-b",
        extension_seconds=60,
    )
    from src.domain.jobs.finalization import FinalizationErrorCode

    with pytest.raises(JobLeaseLostError):
        tracker.fail(
            error_code=FinalizationErrorCode.DOMAIN_PERSISTENCE_FAILED,
            current_step=CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS,
            message="should not persist",
        )
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    # Stale failure must not overwrite the stolen job's terminal metadata as FAILED by A.
    assert job.claim_owner_id == "owner-b"
