"""Phase 4.5 regression — normalization metadata must not break artifact hotfixes."""

from __future__ import annotations

import json
from pathlib import Path

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
    manifest_composition_projection,
)
from src.domain.manifest_evidence_resolution import apply_evidence_resolution_to_entities
from src.domain.traceability import TraceabilityStatus, apply_traceability_validation
from src.parsing.global_analysis_parser import parse_entities
from src.pipeline.execution_log_sanitizer import make_json_safe_for_execution_log
from src.pipeline.llm_metadata_json_safety import assert_metadata_json_serializable
from tests.infrastructure.pipeline.test_execution_log_durable_publication_flow import (
    _write_valid_execution_log,
)
from tests.infrastructure.pipeline.test_worker_phase3_part5_artifact_outbox import (
    RUN_ID,
    _build_dispatcher,
)
from tests.support.worker_phase1.doubles import SizeOnlyArtifactStore
from tests.support.worker_phase1.executor_harness import ExecutorHarness


def test_phase45_entity_fields_json_safe_in_run_metadata() -> None:
    payload = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "manifest_entry_id": "IMG_001",
                "source_image_id": "asset-1",
            }
        ],
    }
    entities = parse_entities(payload, job_id="job-1")
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(
            ExecutionImageEntry(
                manifest_entry_id="IMG_001",
                source_asset_id="asset-1",
                source_image_id="asset-1",
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=1,
                storage_reference="a.jpg",
            ),
        ),
        excluded_entries=(),
    )
    composition = manifest_composition_projection(manifest)
    apply_evidence_resolution_to_entities(entities, composition=composition)
    apply_traceability_validation(
        entities,
        frozenset({"asset-1"}),
        sent_metadata_available=True,
    )
    run_metadata = {
        "entities": [
            {
                "manifest_entry_id": e.manifest_entry_id,
                "raw_source_image_id": e.raw_source_image_id,
                "resolved_manifest_entry_id": e.resolved_manifest_entry_id,
                "source_image_id": e.source_image_id,
                "traceability_status": e.traceability_status,
                "traceability_warning": e.traceability_warning,
            }
            for e in entities
        ]
    }
    safe = make_json_safe_for_execution_log(run_metadata)
    json.dumps(safe)
    assert_metadata_json_serializable(safe, context="phase45_run_metadata")
    assert entities[0].traceability_status == TraceabilityStatus.VALID.value


def test_phase45_durable_execution_log_publication_still_succeeds(tmp_path: Path) -> None:
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
    assert "execution_log" not in result.permanently_failed_kinds
