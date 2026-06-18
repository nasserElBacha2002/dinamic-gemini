"""Phase 4.6 — structural evidence mapping from hybrid report entities."""

from __future__ import annotations

from datetime import datetime, timezone

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
    manifest_composition_projection,
)
from src.domain.result_evidence.entities import ResultEvidenceRole
from src.domain.result_evidence.mapper import (
    ResultEvidenceMapContext,
    map_entity_to_result_evidence,
)
from src.domain.traceability import TraceabilityStatus


def _manifest() -> ExecutionImageManifest:
    return ExecutionImageManifest(
        job_id="job-1",
        entries=(
            ExecutionImageEntry(
                manifest_entry_id="REF_001",
                source_asset_id="ref-1",
                source_image_id="ref-1",
                role=ExecutionImageRole.REFERENCE_IMAGE,
                payload_ordinal=1,
                storage_reference="ref.jpg",
            ),
            ExecutionImageEntry(
                manifest_entry_id="IMG_001",
                source_asset_id="asset-1",
                source_image_id="asset-1",
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=2,
                storage_reference="a.jpg",
            ),
        ),
        excluded_entries=(),
    )


def _ctx() -> ResultEvidenceMapContext:
    return ResultEvidenceMapContext(
        job_id="job-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        now=datetime(2026, 6, 18, tzinfo=timezone.utc),
        position_id="pos-1",
        provider="gemini",
        model_name="gemini-2.0",
        prompt_composition=manifest_composition_projection(_manifest()),
        schema_version="2.1",
    )


def test_valid_img_maps_primary_with_source_asset() -> None:
    record = map_entity_to_result_evidence(
        {
            "entity_uid": "job_E1",
            "model_entity_id": "E1",
            "manifest_entry_id": "IMG_001",
            "resolved_manifest_entry_id": "IMG_001",
            "source_image_id": "asset-1",
            "traceability_status": TraceabilityStatus.VALID.value,
        },
        _ctx(),
    )
    assert record.has_valid_evidence is True
    assert record.source_image_id == "asset-1"
    assert record.source_asset_id == "asset-1"
    assert record.role == ResultEvidenceRole.PRIMARY_EVIDENCE


def test_ref_invalid_not_displayable() -> None:
    record = map_entity_to_result_evidence(
        {
            "entity_uid": "job_E1",
            "manifest_entry_id": "REF_001",
            "resolved_manifest_entry_id": "REF_001",
            "traceability_status": TraceabilityStatus.INVALID.value,
            "traceability_warning": "Provider returned a reference image as evidence.",
        },
        _ctx(),
    )
    assert record.has_valid_evidence is False
    assert record.source_image_id is None
    assert record.role == ResultEvidenceRole.REFERENCE_IMAGE


def test_unknown_img_invalid() -> None:
    record = map_entity_to_result_evidence(
        {
            "entity_uid": "job_E1",
            "manifest_entry_id": "IMG_999",
            "traceability_status": TraceabilityStatus.INVALID.value,
        },
        _ctx(),
    )
    assert record.has_valid_evidence is False
    assert record.source_image_id is None


def test_missing_evidence_row() -> None:
    record = map_entity_to_result_evidence(
        {
            "entity_uid": "job_E1",
            "traceability_status": TraceabilityStatus.MISSING.value,
        },
        _ctx(),
    )
    assert record.has_valid_evidence is False
    assert record.traceability_status == TraceabilityStatus.MISSING.value


def test_unvalidated_manifest_unavailable() -> None:
    record = map_entity_to_result_evidence(
        {
            "entity_uid": "job_E1",
            "manifest_entry_id": "IMG_001",
            "traceability_status": TraceabilityStatus.UNVALIDATED.value,
        },
        ResultEvidenceMapContext(
            job_id="job-1",
            inventory_id="inv-1",
            aisle_id="aisle-1",
            now=datetime(2026, 6, 18, tzinfo=timezone.utc),
        ),
    )
    assert record.has_valid_evidence is False
    assert record.traceability_status == TraceabilityStatus.UNVALIDATED.value


def test_conflict_invalid_preserves_warning() -> None:
    record = map_entity_to_result_evidence(
        {
            "entity_uid": "job_E1",
            "manifest_entry_id": "IMG_001",
            "raw_source_image_id": "ref-1",
            "traceability_status": TraceabilityStatus.INVALID.value,
            "traceability_warning": "Provider returned conflicting manifest_entry_id and source_image_id.",
        },
        _ctx(),
    )
    assert record.has_valid_evidence is False
    assert "conflicting" in (record.traceability_warning or "").lower()
