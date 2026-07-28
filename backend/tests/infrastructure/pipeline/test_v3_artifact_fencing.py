"""Artifact publication fencing: stale workers cannot mark published."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from src.application.services.artifact_publication_dispatcher import (
    ArtifactPublicationDispatcher,
)
from src.application.services.finalization_projection_service import (
    FinalizationProjectionService,
)
from src.domain.jobs.lease import JobLeaseLostError
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
    worker_durable_artifact_key_prefix,
)
from tests.support.worker_phase1.doubles import ArtifactUploadSpy
from tests.support.worker_phase1.executor_harness import ExecutorHarness, FixedClock


def test_token_scoped_artifact_prefix() -> None:
    plain = worker_durable_artifact_key_prefix("job-1", "run")
    scoped = worker_durable_artifact_key_prefix("job-1", "run", fencing_token=3)
    assert plain == "jobs/job-1/run"
    assert scoped == "jobs/job-1/ft3/run"


def test_stale_mark_published_rejected(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    lease = harness.lease()
    run_dir = harness.seed_run_dir()
    projection = FinalizationProjectionService(
        job_repo=harness.job_repo,
        stage_store=harness.stage_store,
        clock=FixedClock(harness.now),
    )
    recorder = FinalizationStageRecorder(
        stage_store=harness.stage_store,
        projection=projection,
        manifest_store=harness.manifest_store,
        clock=FixedClock(harness.now),
    )
    dispatcher = ArtifactPublicationDispatcher(
        outbox_store=harness.outbox_store,
        manifest_store=harness.manifest_store,
        stage_store=harness.stage_store,
        artifact_store=ArtifactUploadSpy(),
        stage_recorder=recorder,
        continuation=None,
        automatic_continuation=None,
        staging_store=harness.staging_store,
        reconciler=None,
        clock=FixedClock(harness.now),
    )
    tracker = JobFinalizationTracker(
        job_id=harness.job_id,
        job_repo=harness.job_repo,
        clock=FixedClock(harness.now),
        lease=lease,
        stage_recorder=recorder,
    )
    dispatcher.register_publication_work(
        job_id=harness.job_id,
        run_segment=DEFAULT_V3_WORKER_RUN_SEGMENT,
        run_dir=run_dir,
        fencing_token=lease.fencing_token,
    )
    # Steal lease after register / before promote.
    stolen = harness.job_repo.reacquire_expired_lease(
        harness.job_id,
        now=harness.now + timedelta(hours=2),
        new_owner_id="owner-b",
        extension_seconds=60,
    )
    assert stolen.lease is not None
    with pytest.raises(JobLeaseLostError):
        dispatcher.dispatch_job(
            job_id=harness.job_id,
            run_segment=DEFAULT_V3_WORKER_RUN_SEGMENT,
            run_dir=run_dir,
            tracker=tracker,
        )
