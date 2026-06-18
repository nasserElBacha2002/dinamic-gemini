"""Phase 4.7 — traceability artifact finalization integration tests."""

from __future__ import annotations

import json
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
from tests.support.worker_phase1.executor_harness import (
    ExecutorHarness,
    FixedClock,
    make_entity_hybrid_report,
)


def _manifest_composition(job_id: str) -> dict:
    manifest = ExecutionImageManifest(
        job_id=job_id,
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


def test_persist_then_generate_traceability_manifest(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-finalize")
    re_repo = MemoryResultEvidenceRepository()
    report = make_entity_hybrid_report(
        [
            {
                "entity_uid": "e1",
                "entity_type": "PALLET",
                "internal_code": "SKU-A",
                "final_quantity": 1,
                "confidence": 0.9,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop.jpg",
                "manifest_entry_id": "IMG_001",
                "resolved_manifest_entry_id": "IMG_001",
                "source_image_id": "asset-1",
                "traceability_status": TraceabilityStatus.VALID.value,
            }
        ]
    )
    uc = harness.make_persist_use_case(result_evidence_repo=re_repo)
    run_dir = harness.seed_run_dir(report)
    from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultCommand

    uc.execute(
        PersistAisleResultCommand(
            aisle_id=harness.aisle_id,
            job_id=harness.job_id,
            report=report,
            run_dir=run_dir,
            provider="gemini",
            model_name="gemini-2.0",
            prompt_composition=_manifest_composition(harness.job_id),
        )
    )
    svc = TraceabilityArtifactService(
        result_evidence_repo=re_repo,
        clock=FixedClock(datetime(2026, 6, 18, tzinfo=timezone.utc)),
    )
    path = svc.generate_and_write(
        job_id=harness.job_id,
        inventory_id=harness.inventory_id,
        aisle_id=harness.aisle_id,
        run_id="run",
        run_dir=run_dir,
        provider="gemini",
        model_name="gemini-2.0",
        prompt_composition=_manifest_composition(harness.job_id),
        run_metadata={},
        input_type="photos",
        canonical_traceability_expected=True,
    )
    body = json.loads(path.read_text(encoding="utf-8"))
    assert len(body["result_evidence"]) == 1
    assert body["result_evidence"][0]["displayable"] is True


def test_generation_failure_after_persist_does_not_publish_traceability(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-gen-fail")
    re_repo = MemoryResultEvidenceRepository()
    report = make_entity_hybrid_report(
        [
            {
                "entity_uid": "e1",
                "entity_type": "PALLET",
                "internal_code": "SKU-A",
                "final_quantity": 1,
                "confidence": 0.9,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop.jpg",
                "manifest_entry_id": "IMG_001",
                "resolved_manifest_entry_id": "IMG_001",
                "source_image_id": "asset-1",
                "traceability_status": TraceabilityStatus.VALID.value,
            }
        ]
    )
    run_dir = harness.seed_run_dir(report)

    svc = TraceabilityArtifactService(
        result_evidence_repo=re_repo,
        clock=FixedClock(datetime(2026, 6, 18, tzinfo=timezone.utc)),
    )
    with pytest.raises(TraceabilityEvidenceMissingError):
        svc.generate_and_write(
            job_id=harness.job_id,
            inventory_id=harness.inventory_id,
            aisle_id=harness.aisle_id,
            run_id="run",
            run_dir=run_dir,
            provider="gemini",
            model_name="gemini-2.0",
            prompt_composition=_manifest_composition(harness.job_id),
            run_metadata={},
            input_type="photos",
            canonical_traceability_expected=True,
        )
    assert not (run_dir / "traceability_manifest.json").exists()


def test_same_evidence_rows_produce_stable_hash(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-hash")
    re_repo = MemoryResultEvidenceRepository()
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    row = ResultEvidenceRecord(
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
    re_repo.save_many([row])
    run_dir = tmp_path / harness.job_id / "run"
    run_dir.mkdir(parents=True)
    comp = _manifest_composition(harness.job_id)
    early_clock = FixedClock(datetime(2026, 6, 18, 10, 0, 0, tzinfo=timezone.utc))
    late_clock = FixedClock(datetime(2026, 6, 18, 14, 0, 0, tzinfo=timezone.utc))
    svc_early = TraceabilityArtifactService(result_evidence_repo=re_repo, clock=early_clock)
    svc_late = TraceabilityArtifactService(result_evidence_repo=re_repo, clock=late_clock)
    first = svc_early.generate_and_write(
        job_id=harness.job_id,
        inventory_id=harness.inventory_id,
        aisle_id=harness.aisle_id,
        run_id="run",
        run_dir=run_dir,
        provider="gemini",
        model_name="gemini-2.0",
        prompt_composition=comp,
        run_metadata={},
        input_type="photos",
        canonical_traceability_expected=True,
    )
    hash_one = json.loads(first.read_text(encoding="utf-8"))["integrity"]["traceability_manifest_hash"]
    second = svc_late.generate_and_write(
        job_id=harness.job_id,
        inventory_id=harness.inventory_id,
        aisle_id=harness.aisle_id,
        run_id="run",
        run_dir=run_dir,
        provider="gemini",
        model_name="gemini-2.0",
        prompt_composition=comp,
        run_metadata={},
        input_type="photos",
        canonical_traceability_expected=True,
    )
    hash_two = json.loads(second.read_text(encoding="utf-8"))["integrity"]["traceability_manifest_hash"]
    assert hash_one == hash_two


def test_photo_v3_missing_manifest_fails_closed(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-missing-manifest")
    re_repo = MemoryResultEvidenceRepository()
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    re_repo.save_many(
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
    svc = TraceabilityArtifactService(
        result_evidence_repo=re_repo,
        clock=FixedClock(now),
    )
    with pytest.raises(TraceabilityManifestMissingError) as exc_info:
        svc.generate_and_write(
            job_id=harness.job_id,
            inventory_id=harness.inventory_id,
            aisle_id=harness.aisle_id,
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


def test_photo_v3_corrupt_manifest_fails_closed(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-corrupt-manifest")
    re_repo = MemoryResultEvidenceRepository()
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    re_repo.save_many(
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
    svc = TraceabilityArtifactService(
        result_evidence_repo=re_repo,
        clock=FixedClock(now),
    )
    with pytest.raises(TraceabilityManifestInvalidError) as exc_info:
        svc.generate_and_write(
            job_id=harness.job_id,
            inventory_id=harness.inventory_id,
            aisle_id=harness.aisle_id,
            run_id="run",
            run_dir=tmp_path / "run",
            provider="gemini",
            model_name="gemini-2.0",
            prompt_composition={"execution_image_manifest": {"version": 1, "entries": "bad"}},
            run_metadata={},
            input_type="photos",
            canonical_traceability_expected=True,
        )
    assert exc_info.value.error_code == "TRACEABILITY_MANIFEST_INVALID"
