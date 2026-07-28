"""Cancel request vs fenced acknowledgement."""

from __future__ import annotations

from datetime import timedelta

from src.domain.jobs.entities import JobStatus
from src.domain.jobs.lease import LeaseWriteOutcome
from tests.support.worker_phase1.executor_harness import ExecutorHarness


def test_external_cancel_request_does_not_need_lease(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    harness.lease()
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.status = JobStatus.CANCEL_REQUESTED
    harness.job_repo.save(job)
    refreshed = harness.job_repo.get_by_id(harness.job_id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.CANCEL_REQUESTED


def test_acknowledge_cancel_requires_current_lease(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    lease = harness.lease()
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.status = JobStatus.CANCEL_REQUESTED
    harness.job_repo.save(job)

    ok = harness.job_repo.acknowledge_cancel_if_leased(
        lease, now=harness.now, reason="user cancel"
    )
    assert ok.outcome == LeaseWriteOutcome.APPLIED
    done = harness.job_repo.get_by_id(harness.job_id)
    assert done is not None
    assert done.status == JobStatus.CANCELED


def test_stale_acknowledge_cancel_rejected(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    lease = harness.lease()
    # Expire + steal while still RUNNING.
    stolen = harness.job_repo.reacquire_expired_lease(
        harness.job_id,
        now=harness.now + timedelta(hours=2),
        new_owner_id="owner-b",
        extension_seconds=60,
    )
    assert stolen.lease is not None
    assert stolen.lease.owner_id == "owner-b"

    job_b = harness.job_repo.get_by_id(harness.job_id)
    assert job_b is not None
    job_b.status = JobStatus.CANCEL_REQUESTED
    harness.job_repo.save(job_b)

    result = harness.job_repo.acknowledge_cancel_if_leased(
        lease, now=harness.now + timedelta(hours=2), reason="stale ack"
    )
    assert result.outcome == LeaseWriteOutcome.LEASE_LOST
    still = harness.job_repo.get_by_id(harness.job_id)
    assert still is not None
    assert still.status == JobStatus.CANCEL_REQUESTED
    assert still.claim_owner_id == "owner-b"
