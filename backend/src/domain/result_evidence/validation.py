"""Pre-persistence invariants for structural result evidence rows (Phase 4.6)."""

from __future__ import annotations

from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.traceability import TraceabilityStatus, normalize_traceability_status

_ALLOWED_STATUSES = frozenset(
    {
        TraceabilityStatus.VALID.value,
        TraceabilityStatus.INVALID.value,
        TraceabilityStatus.MISSING.value,
        TraceabilityStatus.UNVALIDATED.value,
    }
)

_ALLOWED_ROLES = frozenset(
    {
        ResultEvidenceRole.PRIMARY_EVIDENCE,
        ResultEvidenceRole.REFERENCE_IMAGE,
        ResultEvidenceRole.UNKNOWN,
    }
)


class ResultEvidenceValidationError(ValueError):
    """Raised when a structural evidence row violates persistence invariants."""


def validate_result_evidence_record(record: ResultEvidenceRecord) -> None:
    """Fail closed before repository persistence."""
    if not (record.job_id or "").strip():
        raise ResultEvidenceValidationError("result_evidence.job_id is required")
    if not (record.inventory_id or "").strip():
        raise ResultEvidenceValidationError("result_evidence.inventory_id is required")
    if not (record.aisle_id or "").strip():
        raise ResultEvidenceValidationError("result_evidence.aisle_id is required")
    if record.evidence_kind != RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY:
        raise ResultEvidenceValidationError(
            f"result_evidence.evidence_kind must be {RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY!r}"
        )

    status = normalize_traceability_status(record.traceability_status)
    if status is not None and status not in _ALLOWED_STATUSES:
        raise ResultEvidenceValidationError(
            f"result_evidence.traceability_status not allowed: {record.traceability_status!r}"
        )
    if record.role is not None and record.role not in _ALLOWED_ROLES:
        raise ResultEvidenceValidationError(f"result_evidence.role not allowed: {record.role!r}")

    if record.has_valid_evidence:
        if status != TraceabilityStatus.VALID.value:
            raise ResultEvidenceValidationError(
                "has_valid_evidence=true requires traceability_status=valid"
            )
        if not (record.source_image_id or "").strip():
            raise ResultEvidenceValidationError(
                "has_valid_evidence=true requires source_image_id"
            )
        if record.role != ResultEvidenceRole.PRIMARY_EVIDENCE:
            raise ResultEvidenceValidationError(
                "has_valid_evidence=true requires role=primary_evidence"
            )
