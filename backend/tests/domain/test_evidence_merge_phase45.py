"""Phase 4.5 — evidence merge policy."""

from __future__ import annotations

from src.domain.entity import Entity
from src.domain.manifest_evidence_resolution import (
    EvidenceResolutionOutcome,
    EvidenceResolutionResult,
    WARNING_MERGE_MULTIPLE_VALID_SOURCES,
    merge_entity_evidence_fields,
    merge_evidence_resolution_results,
)
from src.domain.traceability import TraceabilityStatus


def _entity(**kwargs) -> Entity:
    defaults = dict(
        entity_uid="job_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        has_boxes=True,
        confidence=0.9,
    )
    defaults.update(kwargs)
    return Entity(**defaults)


def test_valid_plus_missing_keeps_valid() -> None:
    left = EvidenceResolutionResult(
        outcome=EvidenceResolutionOutcome.RESOLVED,
        traceability_status=TraceabilityStatus.VALID.value,
        resolved_source_image_id="asset-1",
    )
    right = EvidenceResolutionResult(
        outcome=EvidenceResolutionOutcome.MISSING,
        traceability_status=TraceabilityStatus.MISSING.value,
    )
    merged = merge_evidence_resolution_results(left, right)
    assert merged.outcome == EvidenceResolutionOutcome.RESOLVED
    assert merged.resolved_source_image_id == "asset-1"


def test_valid_plus_invalid_keeps_valid() -> None:
    left = EvidenceResolutionResult(
        outcome=EvidenceResolutionOutcome.RESOLVED,
        traceability_status=TraceabilityStatus.VALID.value,
        resolved_source_image_id="asset-1",
    )
    right = EvidenceResolutionResult(
        outcome=EvidenceResolutionOutcome.INVALID_UNKNOWN,
        traceability_status=TraceabilityStatus.INVALID.value,
    )
    merged = merge_evidence_resolution_results(left, right)
    assert merged.resolved_source_image_id == "asset-1"


def test_entity_merge_keeps_valid_over_missing() -> None:
    target = _entity(
        source_image_id="asset-1",
        traceability_status=TraceabilityStatus.VALID.value,
    )
    candidate = _entity(traceability_status=TraceabilityStatus.MISSING.value)
    merge_entity_evidence_fields(target, candidate)
    assert target.source_image_id == "asset-1"
    assert target.traceability_status == TraceabilityStatus.VALID.value


def test_entity_merge_warns_on_two_valid_sources() -> None:
    target = _entity(
        source_image_id="asset-1",
        traceability_status=TraceabilityStatus.VALID.value,
    )
    candidate = _entity(
        source_image_id="asset-2",
        traceability_status=TraceabilityStatus.VALID.value,
    )
    merge_entity_evidence_fields(target, candidate)
    assert target.traceability_warning == WARNING_MERGE_MULTIPLE_VALID_SOURCES
