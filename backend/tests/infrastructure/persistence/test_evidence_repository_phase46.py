"""Phase 4.6 — result evidence repository (memory)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.traceability import TraceabilityStatus
from src.domain.result_evidence.validation import ResultEvidenceValidationError
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)


def _record(*, job_id: str = "job-1", valid: bool = False) -> ResultEvidenceRecord:
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    return ResultEvidenceRecord(
        id=f"re-{job_id}-{valid}",
        job_id=job_id,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        position_id="pos-1",
        entity_uid="job_E1",
        model_entity_id="E1",
        raw_manifest_entry_id="IMG_001" if valid else "REF_001",
        manifest_entry_id="IMG_001" if valid else "REF_001",
        raw_source_image_id=None,
        resolved_manifest_entry_id="IMG_001" if valid else "REF_001",
        source_image_id="asset-1" if valid else None,
        source_asset_id="asset-1" if valid else "ref-1",
        traceability_status=TraceabilityStatus.VALID.value
        if valid
        else TraceabilityStatus.INVALID.value,
        traceability_warning=None,
        role=ResultEvidenceRole.PRIMARY_EVIDENCE if valid else ResultEvidenceRole.REFERENCE_IMAGE,
        provider="gemini",
        model_name="gemini-2.0",
        schema_version="2.1",
        manifest_version=1,
        has_valid_evidence=valid,
        evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
        created_at=now,
        updated_at=now,
    )


def test_save_list_delete_replace_by_job() -> None:
    repo = MemoryResultEvidenceRepository()
    repo.save_many([_record(valid=True), _record(job_id="job-1", valid=False)])
    assert len(repo.list_by_job_id("job-1")) == 2
    assert len(repo.list_valid_by_job_id("job-1")) == 1
    removed = repo.delete_by_job_id("job-1")
    assert removed == 2
    assert repo.list_by_job_id("job-1") == []


def test_delete_for_scope_matches_inventory_aisle_job_only() -> None:
    repo = MemoryResultEvidenceRepository()
    repo.save_many(
        [
            _record(job_id="job-shared"),
            ResultEvidenceRecord(
                **_record(job_id="job-shared").__dict__
                | {
                    "id": "re-other-scope",
                    "inventory_id": "inv-other",
                    "aisle_id": "aisle-other",
                }
            ),
        ]
    )
    removed = repo.delete_for_scope(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        job_id="job-shared",
    )
    assert removed == 1
    remaining = list(repo.list_by_job_id("job-shared"))
    assert len(remaining) == 1
    assert remaining[0].inventory_id == "inv-other"


def test_save_many_validates_before_persist() -> None:
    repo = MemoryResultEvidenceRepository()
    invalid = _record(valid=True)
    invalid = ResultEvidenceRecord(
        **{**invalid.__dict__, "has_valid_evidence": True, "traceability_status": TraceabilityStatus.INVALID.value}
    )
    with pytest.raises(ResultEvidenceValidationError):
        repo.save_many([invalid])
