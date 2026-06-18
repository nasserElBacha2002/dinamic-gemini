"""Phase 4.7 — traceability_manifest durable publication tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.application.services.artifact_publication_dispatcher import (
    ArtifactSourceStagingFailedError,
)
from src.application.services.traceability_artifact_service import TraceabilityArtifactService
from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
    manifest_composition_projection,
)
from src.domain.jobs.artifact_manifest import ArtifactManifestStatus
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_TRACEABILITY_MANIFEST,
)
from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.traceability import TraceabilityStatus
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)
from src.pipeline.execution_log import ExecutionLogWriter
from tests.infrastructure.pipeline.test_worker_phase3_part5_artifact_outbox import (
    RUN_ID,
    _build_dispatcher,
)
from tests.support.worker_phase1.doubles import SizeOnlyArtifactStore
from tests.support.worker_phase1.executor_harness import ExecutorHarness, FixedClock


def _write_run_artifacts(harness: ExecutorHarness, run_dir) -> None:
    writer = ExecutionLogWriter(run_dir)
    writer.append("Analysis", "info", "completed", payload={"frames": 1})
    report = {"entities": []}
    (run_dir / "hybrid_report.json").write_text(json.dumps(report), encoding="utf-8")


def _write_traceability_manifest(harness: ExecutorHarness, run_dir) -> None:
    repo = MemoryResultEvidenceRepository()
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    repo.save_many(
        [
            ResultEvidenceRecord(
                id="re-1",
                job_id=harness.job_id,
                inventory_id=harness.inventory_id,
                aisle_id=harness.aisle_id,
                position_id="pos-1",
                entity_uid="job_E1",
                model_entity_id="E1",
                raw_manifest_entry_id="IMG_001",
                manifest_entry_id="IMG_001",
                raw_source_image_id=None,
                resolved_manifest_entry_id="IMG_001",
                source_image_id="asset-1",
                source_asset_id="asset-1",
                traceability_status=TraceabilityStatus.VALID.value,
                traceability_warning=None,
                role=ResultEvidenceRole.PRIMARY_EVIDENCE,
                provider="gemini",
                model_name="gemini-2.0",
                schema_version="2.1",
                manifest_version=1,
                has_valid_evidence=True,
                evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
                created_at=now,
                updated_at=now,
            )
        ]
    )
    manifest = ExecutionImageManifest(
        job_id=harness.job_id,
        entries=(
            ExecutionImageEntry(
                manifest_entry_id="IMG_001",
                source_asset_id="asset-1",
                source_image_id="asset-1",
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=1,
                storage_reference="photos/a.jpg",
            ),
        ),
        excluded_entries=(),
    )
    svc = TraceabilityArtifactService(
        result_evidence_repo=repo,
        clock=FixedClock(now),
    )
    svc.generate_and_write(
        job_id=harness.job_id,
        inventory_id=harness.inventory_id,
        aisle_id=harness.aisle_id,
        run_id=RUN_ID,
        run_dir=run_dir,
        provider="gemini",
        model_name="gemini-2.0",
        prompt_composition=manifest_composition_projection(manifest),
        run_metadata={},
    )


def test_traceability_manifest_registered_staged_and_published(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=SizeOnlyArtifactStore())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    _write_run_artifacts(harness, run_dir)
    _write_traceability_manifest(harness, run_dir)

    dispatcher.register_publication_work(
        job_id=harness.job_id,
        run_segment=RUN_ID,
        run_dir=run_dir,
        required_kind_overrides={ARTIFACT_KIND_TRACEABILITY_MANIFEST: True},
    )
    trace_entry = harness.outbox_store.get_entry(
        harness.job_id, ARTIFACT_KIND_TRACEABILITY_MANIFEST
    )
    assert trace_entry is not None
    assert trace_entry.required is True

    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    assert ARTIFACT_KIND_TRACEABILITY_MANIFEST in result.published_kinds
    manifest_entry = harness.manifest_store.get_entry(
        harness.job_id, ARTIFACT_KIND_TRACEABILITY_MANIFEST
    )
    assert manifest_entry is not None
    assert manifest_entry.status == ArtifactManifestStatus.PUBLISHED


def test_traceability_manifest_staging_failure_when_required_file_missing(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=SizeOnlyArtifactStore())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    _write_run_artifacts(harness, run_dir)

    with pytest.raises(ArtifactSourceStagingFailedError) as exc_info:
        dispatcher.register_publication_work(
            job_id=harness.job_id,
            run_segment=RUN_ID,
            run_dir=run_dir,
            required_kind_overrides={ARTIFACT_KIND_TRACEABILITY_MANIFEST: True},
        )
    assert exc_info.value.error_code == "ARTIFACT_SOURCE_MISSING"


def test_retry_replaces_single_traceability_outbox_entry(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=SizeOnlyArtifactStore())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    _write_run_artifacts(harness, run_dir)
    _write_traceability_manifest(harness, run_dir)

    overrides = {ARTIFACT_KIND_TRACEABILITY_MANIFEST: True}
    dispatcher.register_publication_work(
        job_id=harness.job_id,
        run_segment=RUN_ID,
        run_dir=run_dir,
        required_kind_overrides=overrides,
    )
    first = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_TRACEABILITY_MANIFEST)
    dispatcher.register_publication_work(
        job_id=harness.job_id,
        run_segment=RUN_ID,
        run_dir=run_dir,
        required_kind_overrides=overrides,
    )
    second = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_TRACEABILITY_MANIFEST)
    assert first is not None and second is not None
    assert first.id == second.id
    assert ARTIFACT_KIND_EXECUTION_LOG in {
        e.artifact_kind for e in harness.outbox_store.list_entries(harness.job_id)
    }
