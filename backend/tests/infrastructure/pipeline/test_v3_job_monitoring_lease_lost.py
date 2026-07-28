"""Phase 3 — monitoring heartbeat stops on lease loss without failing the job."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.lease import JobLease, LeaseRenewalOutcome, LeaseRenewalResult
from src.infrastructure.pipeline.v3_job_monitoring_service import (
    V3JobMonitoringRequest,
    V3JobMonitoringService,
)


def test_heartbeat_lease_lost_sets_abort_without_failing_job(tmp_path: Path) -> None:
    now = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
    lease = JobLease(
        job_id="job-1",
        owner_id="owner-a",
        fencing_token=1,
        acquired_at=now,
        expires_at=now + timedelta(seconds=60),
    )
    job = Job(
        id="job-1",
        job_type="process_aisle",
        target_type="aisle",
        target_id="aisle-1",
        status=JobStatus.RUNNING,
        payload_json={},
        created_at=now,
        updated_at=now,
        attempt_count=1,
        execution_id="ex-1",
        current_substep="processing",
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )

    state = MagicMock()
    state.heartbeat_with_lease.return_value = (
        None,
        LeaseRenewalResult(outcome=LeaseRenewalOutcome.LEASE_LOST, reason="stolen"),
    )
    state.fail_job_and_aisle = MagicMock()

    monitoring = V3JobMonitoringService(
        state_service=state,
        heartbeat_interval_sec=0.05,
        startup_progress_timeout_sec=3600.0,
    )
    req = V3JobMonitoringRequest(
        base_path=tmp_path,
        job_id="job-1",
        job_dir=tmp_path / "job-1",
        job=job,
        aisle=aisle,
        aisle_id="aisle-1",
        lease=lease,
        lease_extension_seconds=60,
    )
    (tmp_path / "job-1").mkdir(parents=True, exist_ok=True)

    with monitoring.session(req) as rt:
        deadline = time.monotonic() + 2.0
        while not rt.runtime_abort_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert rt.runtime_abort_event.is_set()
        # Allow heartbeat thread to observe stop.
        time.sleep(0.05)

    state.fail_job_and_aisle.assert_not_called()
    assert state.heartbeat_with_lease.called
