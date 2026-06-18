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
from src.domain.traceability_artifact.errors import (
    TraceabilityEvidenceMissingError,
    TraceabilityManifestInvalidError,
    TraceabilityManifestMissingError,
)
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


def _corrupt_composition() -> dict:
    return {"execution_image_manifest": {"version": 1, "entries": "not-a-list"}}


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


def test_is_required_for_photo_v3_canonical_job() -> None:
    assert TraceabilityArtifactService.is_required_for_run(
        input_type="photos",
        canonical_traceability_expected=True,
        prompt_composition=None,
    )


def test_is_not_required_for_non_photo_job() -> None:
    assert not TraceabilityArtifactService.is_required_for_run(
        input_type="video",
        canonical_traceability_expected=True,
        prompt_composition=None,
    )


def test_is_not_required_when_canonical_traceability_not_expected() -> None:
    assert not TraceabilityArtifactService.is_required_for_run(
        input_type="photos",
        canonical_traceability_expected=False,
        prompt_composition=_composition(),
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
        input_type="photos",
        canonical_traceability_expected=True,
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
            input_type="photos",
            canonical_traceability_expected=True,
        )


def test_missing_manifest_raises_for_required_photo_job(tmp_path: Path) -> None:
    repo = MemoryResultEvidenceRepository()
    repo.save_many([_record()])
    svc = TraceabilityArtifactService(
        result_evidence_repo=repo,
        clock=FixedClock(datetime(2026, 6, 18, tzinfo=timezone.utc)),
    )
    with pytest.raises(TraceabilityManifestMissingError) as exc_info:
        svc.generate_and_write(
            job_id="job-1",
            inventory_id="inv-1",
            aisle_id="aisle-1",
            run_id="run",
            run_dir=tmp_path / "run",
            provider="gemini",
            model_name="gemini-2.0",
            prompt_composition=None,
            run_metadata={},
            input_type="photos",
            canonical_traceability_expected=True,
        )
    assert exc_info.value.error_code == "TRACEABILITY_MANIFEST_MISSING"


def test_corrupt_manifest_raises_for_required_photo_job(tmp_path: Path) -> None:
    repo = MemoryResultEvidenceRepository()
    repo.save_many([_record()])
    svc = TraceabilityArtifactService(
        result_evidence_repo=repo,
        clock=FixedClock(datetime(2026, 6, 18, tzinfo=timezone.utc)),
    )
    with pytest.raises(TraceabilityManifestInvalidError) as exc_info:
        svc.generate_and_write(
            job_id="job-1",
            inventory_id="inv-1",
            aisle_id="aisle-1",
            run_id="run",
            run_dir=tmp_path / "run",
            provider="gemini",
            model_name="gemini-2.0",
            prompt_composition=_corrupt_composition(),
            run_metadata={},
            input_type="photos",
            canonical_traceability_expected=True,
        )
    assert exc_info.value.error_code == "TRACEABILITY_MANIFEST_INVALID"


def test_optional_non_photo_job_without_rows_does_not_require_manifest(tmp_path: Path) -> None:
    svc = TraceabilityArtifactService(
        result_evidence_repo=MemoryResultEvidenceRepository(),
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
        prompt_composition=None,
        run_metadata={},
        input_type="video",
        canonical_traceability_expected=False,
    )
    import json

    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["execution_image_manifest"] is None
    assert body["result_evidence"] == []


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
        input_type="photos",
        canonical_traceability_expected=True,
    )
    import json

    body = json.loads(path.read_text(encoding="utf-8"))
    assert len(body["result_evidence"]) == 1
