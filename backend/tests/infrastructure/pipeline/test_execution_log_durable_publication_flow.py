"""Durable execution_log publication flow — source → staging → outbox → artifact store."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.application.services.artifact_publication_dispatcher import (
    ArtifactPublicationDispatcher,
    ArtifactSourceStagingFailedError,
)
from src.domain.jobs.artifact_manifest import ArtifactManifestStatus
from src.domain.jobs.artifact_policy import ARTIFACT_KIND_EXECUTION_LOG, ARTIFACT_KIND_HYBRID_REPORT_JSON
from src.domain.jobs.artifact_publication_outbox import (
    ArtifactPublicationOutboxEntry,
    ArtifactPublicationOutboxStatus,
    ArtifactSourceType,
)
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)
from src.pipeline.execution_log import ExecutionLogWriter
from tests.infrastructure.pipeline.test_worker_phase3_part5_artifact_outbox import (
    RUN_ID,
    _build_dispatcher,
)
from tests.support.worker_phase1.doubles import SizeOnlyArtifactStore
from tests.support.worker_phase1.executor_harness import ExecutorHarness


def _write_valid_execution_log(run_dir) -> None:
    writer = ExecutionLogWriter(run_dir)
    writer.append("Analysis", "info", "completed", payload={"frames": 5, "provider": "gemini"})


def test_execution_log_source_missing_raises_artifact_source_missing(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=SizeOnlyArtifactStore())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    (run_dir / "execution_log.jsonl").unlink()

    with pytest.raises(ArtifactSourceStagingFailedError) as exc_info:
        dispatcher.register_publication_work(
            job_id=harness.job_id,
            run_segment=RUN_ID,
            run_dir=run_dir,
        )
    assert exc_info.value.error_code == "ARTIFACT_SOURCE_MISSING"


def test_execution_log_invalid_jsonl_raises_artifact_source_invalid_jsonl(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=SizeOnlyArtifactStore())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    (run_dir / "execution_log.jsonl").write_text("not-json\n", encoding="utf-8")

    with pytest.raises(ArtifactSourceStagingFailedError) as exc_info:
        dispatcher.register_publication_work(
            job_id=harness.job_id,
            run_segment=RUN_ID,
            run_dir=run_dir,
        )
    assert exc_info.value.error_code == "ARTIFACT_SOURCE_INVALID_JSONL"


def test_valid_execution_log_staged_with_sha_and_size(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=SizeOnlyArtifactStore())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    _write_valid_execution_log(run_dir)

    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert entry is not None
    assert entry.source_type == ArtifactSourceType.EXACT_DURABLE_SOURCE
    assert entry.source_reference
    assert entry.source_sha256
    assert entry.size_bytes and entry.size_bytes > 0
    assert entry.destination_key.endswith("execution_log.jsonl")
    assert harness.staging_store.source_exists(entry.source_reference)


def test_size_only_artifact_store_publishes_execution_log_durably(tmp_path) -> None:
    """Regression: S3/GCS-like stores without SHA metadata must still publish staged bytes."""
    store = SizeOnlyArtifactStore()
    harness = ExecutorHarness.build(tmp_path, artifact_store=store)
    dispatcher, tracker, _, _ = _build_dispatcher(harness, artifact_store=store)
    run_dir = harness.seed_run_dir()
    _write_valid_execution_log(run_dir)
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)

    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(
        job_id=harness.job_id,
        run_segment=RUN_ID,
        run_dir=run_dir,
        tracker=tracker,
        continuation_aisle=aisle,
        report_path=run_dir / "hybrid_report.json",
    )

    assert ARTIFACT_KIND_EXECUTION_LOG in result.published_kinds
    assert ARTIFACT_KIND_EXECUTION_LOG not in result.permanently_failed_kinds
    assert result.required_complete
    manifest = harness.manifest_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert manifest is not None and manifest.status == ArtifactManifestStatus.PUBLISHED
    outbox = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert outbox is not None and outbox.status == ArtifactPublicationOutboxStatus.PUBLISHED


def test_stale_permanently_failed_outbox_entry_resets_on_fresh_register(tmp_path) -> None:
    store = SizeOnlyArtifactStore()
    harness = ExecutorHarness.build(tmp_path, artifact_store=store)
    dispatcher, tracker, _, _ = _build_dispatcher(harness, artifact_store=store)
    run_dir = harness.seed_run_dir()
    _write_valid_execution_log(run_dir)
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    now = datetime.now(timezone.utc)

    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    stale = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert stale is not None
    harness.outbox_store.mark_permanently_failed(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        error_code="checksum_mismatch",
        error_message="uploaded object not SHA-256 confirmed",
        now=now,
        expected_version=stale.version,
    )

    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    reset = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert reset is not None
    assert reset.status == ArtifactPublicationOutboxStatus.PENDING
    assert reset.attempt_count == 0
    assert reset.last_error_code is None

    result = dispatcher.dispatch_job(
        job_id=harness.job_id,
        run_segment=RUN_ID,
        run_dir=run_dir,
        tracker=tracker,
        continuation_aisle=aisle,
        report_path=run_dir / "hybrid_report.json",
    )
    assert ARTIFACT_KIND_EXECUTION_LOG in result.published_kinds
    assert result.required_complete


def test_publish_failure_records_failed_entries_with_last_error(tmp_path) -> None:
    from unittest.mock import MagicMock

    harness = ExecutorHarness.build(tmp_path, artifact_store=MagicMock())
    harness.artifact_store.put_object.side_effect = RuntimeError("storage write denied")
    harness.artifact_store.object_exists.return_value = False
    dispatcher, _, _, _ = _build_dispatcher(harness, max_attempts=1)
    run_dir = harness.seed_run_dir()
    _write_valid_execution_log(run_dir)

    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)

    assert ARTIFACT_KIND_EXECUTION_LOG in result.permanently_failed_kinds
    assert result.failed_entries
    failed = result.failed_entries[0]
    assert failed["artifact_kind"] == ARTIFACT_KIND_EXECUTION_LOG
    assert failed["last_error_code"]
    assert failed["last_error_message"]
    assert failed["source_reference"]
    assert failed["destination_key"]


def test_execution_log_failure_blocks_later_required_kind(tmp_path) -> None:
    from unittest.mock import MagicMock

    harness = ExecutorHarness.build(tmp_path, artifact_store=MagicMock())
    harness.artifact_store.put_object.side_effect = RuntimeError("storage write denied")
    harness.artifact_store.object_exists.return_value = False
    dispatcher, _, _, _ = _build_dispatcher(harness, max_attempts=1)
    run_dir = harness.seed_run_dir()
    _write_valid_execution_log(run_dir)

    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)

    assert ARTIFACT_KIND_EXECUTION_LOG in result.permanently_failed_kinds
    assert ARTIFACT_KIND_HYBRID_REPORT_JSON not in result.published_kinds
    json_entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_HYBRID_REPORT_JSON)
    assert json_entry is not None
    assert json_entry.status != ArtifactPublicationOutboxStatus.PUBLISHED


def test_five_frame_gemini_shape_execution_log_end_to_end(tmp_path) -> None:
    """Reported job shape: valid JSONL, staged source, size-only durable store, no API calls."""
    store = SizeOnlyArtifactStore()
    harness = ExecutorHarness.build(tmp_path, artifact_store=store)
    dispatcher, tracker, _, _ = _build_dispatcher(harness, artifact_store=store)
    run_dir = harness.seed_run_dir()
    writer = ExecutionLogWriter(run_dir)
    for index in range(5):
        writer.append(
            "FrameAcquisition",
            "info",
            f"frame_{index}",
            payload={"frame_id": f"f{index}", "provider": "gemini"},
        )
    writer.append("Analysis", "info", "completed", payload={"provider": "gemini", "frame_count": 5})
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)

    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(
        job_id=harness.job_id,
        run_segment=DEFAULT_V3_WORKER_RUN_SEGMENT,
        run_dir=run_dir,
        tracker=tracker,
        continuation_aisle=aisle,
        report_path=run_dir / "hybrid_report.json",
    )

    assert ARTIFACT_KIND_EXECUTION_LOG not in result.permanently_failed_kinds
    assert result.failed_entries == []
    outbox = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert outbox is not None and outbox.status == ArtifactPublicationOutboxStatus.PUBLISHED
    staged_key = outbox.source_reference
    assert staged_key and harness.staging_store.source_exists(staged_key)
    dest = outbox.destination_key
    assert dest and store.object_exists(dest)
    with harness.staging_store.open_source(staged_key) as staged_fh:
        staged_bytes = staged_fh.read()
    assert json.loads(staged_bytes.decode("utf-8").splitlines()[0])
