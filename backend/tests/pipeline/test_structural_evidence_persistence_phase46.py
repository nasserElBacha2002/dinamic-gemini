"""Phase 4.6 — pipeline integration for structural evidence persistence."""

from __future__ import annotations

from pathlib import Path

from src.domain.traceability import TraceabilityStatus
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)
from tests.support.worker_phase1.executor_harness import ExecutorHarness, make_entity_hybrid_report


def test_pipeline_persist_structural_evidence_invalid_ref(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-ref")
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
                "manifest_entry_id": "REF_001",
                "resolved_manifest_entry_id": "REF_001",
                "traceability_status": TraceabilityStatus.INVALID.value,
                "traceability_warning": "Provider returned a reference image as evidence.",
            }
        ]
    )
    uc = harness.make_persist_use_case(result_evidence_repo=re_repo)
    harness.seed_run_dir(report)
    from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultCommand

    uc.execute(
        PersistAisleResultCommand(
            aisle_id=harness.aisle_id,
            job_id=harness.job_id,
            report=report,
            run_dir=tmp_path / harness.job_id / "run",
        )
    )
    rows = list(re_repo.list_by_job_id(harness.job_id))
    assert len(rows) == 1
    assert rows[0].has_valid_evidence is False
    assert rows[0].traceability_status == TraceabilityStatus.INVALID.value
