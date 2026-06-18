"""Phase 4.6 — transactional result evidence persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultCommand
from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
    manifest_composition_projection,
)
from src.domain.traceability import TraceabilityStatus
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)
from tests.support.worker_phase1.doubles import FailOnNthSavePositionRepository
from tests.support.worker_phase1.executor_harness import ExecutorHarness, make_entity_hybrid_report
from tests.support.worker_phase2.persist_builders import build_persist_aisle_result_use_case


def _manifest_composition() -> dict:
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
    return manifest_composition_projection(manifest)


def test_persist_writes_structural_evidence_rows(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-re")
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
    uc = build_persist_aisle_result_use_case(
        position_repo=harness.position_repo,
        product_record_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        result_evidence_repo=re_repo,
        aisle_repo=harness.aisle_repo,
        raw_label_repo=harness.raw_repo,
        normalized_label_repo=harness.norm_repo,
        final_count_repo=harness.final_repo,
        clock=__import__(
            "tests.support.worker_phase1.executor_harness", fromlist=["FixedClock"]
        ).FixedClock(harness.now),
    )
    uc.execute(
        PersistAisleResultCommand(
            aisle_id=harness.aisle_id,
            job_id=harness.job_id,
            report=report,
            run_dir=tmp_path / harness.job_id,
            provider="gemini",
            model_name="gemini-2.0",
            prompt_composition=_manifest_composition(),
        )
    )
    rows = list(re_repo.list_by_job_id(harness.job_id))
    assert len(rows) == 1
    assert rows[0].has_valid_evidence is True
    assert rows[0].source_asset_id == "asset-1"


def test_retry_replaces_evidence_rows(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-retry")
    re_repo = MemoryResultEvidenceRepository()
    uc = build_persist_aisle_result_use_case(
        position_repo=harness.position_repo,
        product_record_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        result_evidence_repo=re_repo,
        aisle_repo=harness.aisle_repo,
        raw_label_repo=harness.raw_repo,
        normalized_label_repo=harness.norm_repo,
        final_count_repo=harness.final_repo,
        clock=__import__(
            "tests.support.worker_phase1.executor_harness", fromlist=["FixedClock"]
        ).FixedClock(harness.now),
    )
    cmd = PersistAisleResultCommand(
        aisle_id=harness.aisle_id,
        job_id=harness.job_id,
        report=make_entity_hybrid_report(
            [
                {
                    "entity_uid": "e1",
                    "entity_type": "PALLET",
                    "internal_code": "SKU-A",
                    "final_quantity": 1,
                    "confidence": 0.9,
                    "count_status": "COUNTED",
                    "evidence_path": "evidence/crop.jpg",
                    "traceability_status": TraceabilityStatus.MISSING.value,
                }
            ]
        ),
        run_dir=tmp_path / harness.job_id,
    )
    uc.execute(cmd)
    first_ids = {r.id for r in re_repo.list_by_job_id(harness.job_id)}
    assert len(first_ids) == 1
    uc.execute(cmd)
    second = list(re_repo.list_by_job_id(harness.job_id))
    assert len(second) == 1
    assert second[0].id not in first_ids


def test_position_failure_rolls_back_evidence(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-fail")
    re_repo = MemoryResultEvidenceRepository()
    failing_positions = FailOnNthSavePositionRepository(harness.position_repo, fail_on_call=1)
    uc = build_persist_aisle_result_use_case(
        position_repo=failing_positions,
        product_record_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        result_evidence_repo=re_repo,
        aisle_repo=harness.aisle_repo,
        raw_label_repo=harness.raw_repo,
        normalized_label_repo=harness.norm_repo,
        final_count_repo=harness.final_repo,
        clock=__import__(
            "tests.support.worker_phase1.executor_harness", fromlist=["FixedClock"]
        ).FixedClock(harness.now),
    )
    with pytest.raises(RuntimeError):
        uc.execute(
            PersistAisleResultCommand(
                aisle_id=harness.aisle_id,
                job_id=harness.job_id,
                report=make_entity_hybrid_report(
                    [
                        {
                            "entity_uid": "e1",
                            "entity_type": "PALLET",
                            "internal_code": "SKU-A",
                            "final_quantity": 1,
                            "confidence": 0.9,
                            "count_status": "COUNTED",
                            "evidence_path": "evidence/crop.jpg",
                        }
                    ]
                ),
                run_dir=tmp_path / harness.job_id,
            )
        )
    assert re_repo.list_by_job_id(harness.job_id) == []
