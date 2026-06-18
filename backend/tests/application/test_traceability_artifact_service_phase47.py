"""Phase 4.7 — traceability artifact application service tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.application.services.traceability_artifact_service import TraceabilityArtifactService
from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
    manifest_composition_projection,
)
from src.domain.jobs.artifact_policy import ARTIFACT_KIND_TRACEABILITY_MANIFEST
from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.traceability import TraceabilityStatus
from src.domain.traceability_artifact.errors import TraceabilityEvidenceMissingError
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)
from tests.support.worker_phase1.executor_harness import FixedClock


def _composition() -> dict:
    manifest = ExecutionImageManifest(
        job_id="job-1",
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
    return manifest_composition_projection(manifest)


def _record() -> ResultEvidenceRecord:
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    return ResultEvidenceRecord(
        id="re-1",
        job_id="job-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
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


def test_service_writes_traceability_manifest_from_structural_rows(tmp_path: Path) -> None:
    repo = MemoryResultEvidenceRepository()
    repo.save_many([_record()])
    svc = TraceabilityArtifactService(
        result_evidence_repo=repo,
        clock=FixedClock(datetime(2026, 6, 18, tzinfo=timezone.utc)),
    )
    run_dir = tmp_path / "job-1" / "run"
    path = svc.generate_and_write(
        job_id="job-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        run_id="run",
        run_dir=run_dir,
        provider="gemini",
        model_name="gemini-2.0",
        prompt_composition=_composition(),
        run_metadata={},
    )
    assert path.name == "traceability_manifest.json"
    assert path.is_file()
    assert svc.artifact_kind() == ARTIFACT_KIND_TRACEABILITY_MANIFEST


def test_missing_structural_rows_raises_for_required_photo_job(tmp_path: Path) -> None:
    svc = TraceabilityArtifactService(
        result_evidence_repo=MemoryResultEvidenceRepository(),
        clock=FixedClock(datetime(2026, 6, 18, tzinfo=timezone.utc)),
    )
    with pytest.raises(TraceabilityEvidenceMissingError):
        svc.generate_and_write(
            job_id="job-1",
            inventory_id="inv-1",
            aisle_id="aisle-1",
            run_id="run",
            run_dir=tmp_path / "run",
            provider="gemini",
            model_name="gemini-2.0",
            prompt_composition=_composition(),
            run_metadata={},
            hybrid_report={"entities": [{"entity_uid": "e1"}]},
        )


def test_service_reads_scope_aligned_rows_only(tmp_path: Path) -> None:
    repo = MemoryResultEvidenceRepository()
    repo.save_many(
        [
            _record(),
            ResultEvidenceRecord(
                **{
                    **_record().__dict__,
                    "id": "re-other",
                    "inventory_id": "inv-other",
                }
            ),
        ]
    )
    svc = TraceabilityArtifactService(
        result_evidence_repo=repo,
        clock=FixedClock(datetime(2026, 6, 18, tzinfo=timezone.utc)),
    )
    path = svc.generate_and_write(
        job_id="job-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        run_id="run",
        run_dir=tmp_path / "run",
        provider="gemini",
        model_name="gemini-2.0",
        prompt_composition=_composition(),
        run_metadata={},
    )
    import json

    body = json.loads(path.read_text(encoding="utf-8"))
    assert len(body["result_evidence"]) == 1
