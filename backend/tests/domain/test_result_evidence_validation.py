"""Phase 4.6 — structural result evidence validation invariants."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.result_evidence.validation import (
    ResultEvidenceValidationError,
    validate_result_evidence_record,
)
from src.domain.traceability import TraceabilityStatus


def _valid_record(**overrides: object) -> ResultEvidenceRecord:
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    base = dict(
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
    base.update(overrides)
    return ResultEvidenceRecord(**base)  # type: ignore[arg-type]


def test_valid_record_passes() -> None:
    validate_result_evidence_record(_valid_record())


def test_has_valid_evidence_true_requires_valid_status() -> None:
    with pytest.raises(ResultEvidenceValidationError, match="traceability_status=valid"):
        validate_result_evidence_record(
            _valid_record(
                traceability_status=TraceabilityStatus.INVALID.value,
                has_valid_evidence=True,
            )
        )


def test_has_valid_evidence_true_requires_source_image_id() -> None:
    with pytest.raises(ResultEvidenceValidationError, match="source_image_id"):
        validate_result_evidence_record(
            _valid_record(source_image_id=None, has_valid_evidence=True)
        )


def test_has_valid_evidence_true_requires_primary_role() -> None:
    with pytest.raises(ResultEvidenceValidationError, match="primary_evidence"):
        validate_result_evidence_record(
            _valid_record(
                role=ResultEvidenceRole.REFERENCE_IMAGE,
                has_valid_evidence=True,
            )
        )


@pytest.mark.parametrize("field", ["job_id", "inventory_id", "aisle_id"])
def test_required_scope_fields(field: str) -> None:
    with pytest.raises(ResultEvidenceValidationError, match=field):
        validate_result_evidence_record(_valid_record(**{field: ""}))


def test_evidence_kind_must_be_entity_traceability() -> None:
    with pytest.raises(ResultEvidenceValidationError, match="evidence_kind"):
        validate_result_evidence_record(_valid_record(evidence_kind="crop"))
