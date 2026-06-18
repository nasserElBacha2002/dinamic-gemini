"""Phase 4.4 corrections — evidence identifier resolution."""

from __future__ import annotations

import pytest

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
)
from src.domain.manifest_evidence_resolution import (
    EvidenceResolutionOutcome,
    RawEvidenceIdentifier,
    WARNING_CONFLICTING_EVIDENCE_IDS,
    WARNING_MANIFEST_UNAVAILABLE,
    WARNING_MALFORMED_MANIFEST_ENTRY_ID,
    WARNING_MISSING_EVIDENCE_ID,
    WARNING_REFERENCE_AS_EVIDENCE,
    resolve_raw_evidence_identifier,
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


def test_manifest_entry_id_only_valid() -> None:
    result = resolve_raw_evidence_identifier(
        RawEvidenceIdentifier("IMG_001", None), _manifest()
    )
    assert result.outcome == EvidenceResolutionOutcome.RESOLVED
    assert result.resolved_source_image_id == "asset-1"


def test_legacy_source_image_id_only_valid() -> None:
    result = resolve_raw_evidence_identifier(
        RawEvidenceIdentifier(None, "asset-1"), _manifest()
    )
    assert result.outcome == EvidenceResolutionOutcome.RESOLVED
    assert result.resolved_source_image_id == "asset-1"


def test_both_fields_agree() -> None:
    result = resolve_raw_evidence_identifier(
        RawEvidenceIdentifier("IMG_001", "asset-1"), _manifest()
    )
    assert result.outcome == EvidenceResolutionOutcome.RESOLVED


def test_both_fields_conflict() -> None:
    result = resolve_raw_evidence_identifier(
        RawEvidenceIdentifier("IMG_001", "ref-1"), _manifest()
    )
    assert result.outcome == EvidenceResolutionOutcome.CONFLICT
    assert result.warning == WARNING_CONFLICTING_EVIDENCE_IDS


def test_ref_manifest_entry_invalid() -> None:
    result = resolve_raw_evidence_identifier(
        RawEvidenceIdentifier("REF_001", None), _manifest()
    )
    assert result.outcome == EvidenceResolutionOutcome.INVALID_REFERENCE


def test_unknown_img_invalid() -> None:
    result = resolve_raw_evidence_identifier(
        RawEvidenceIdentifier("IMG_999", None), _manifest()
    )
    assert result.outcome == EvidenceResolutionOutcome.INVALID_UNKNOWN


def test_neither_field_missing() -> None:
    result = resolve_raw_evidence_identifier(RawEvidenceIdentifier(None, None), _manifest())
    assert result.outcome == EvidenceResolutionOutcome.MISSING


def test_unknown_legacy_source_id_invalid() -> None:
    result = resolve_raw_evidence_identifier(
        RawEvidenceIdentifier(None, "unknown-legacy-id"), _manifest()
    )
    assert result.outcome == EvidenceResolutionOutcome.INVALID_UNKNOWN


def test_malformed_manifest_entry_id_invalid() -> None:
    result = resolve_raw_evidence_identifier(
        RawEvidenceIdentifier("filename.jpg", None), _manifest()
    )
    assert result.outcome == EvidenceResolutionOutcome.INVALID_MALFORMED
    assert result.warning == WARNING_MALFORMED_MANIFEST_ENTRY_ID


def test_manifest_missing_unvalidated() -> None:
    result = resolve_raw_evidence_identifier(
        RawEvidenceIdentifier("IMG_001", None),
        None,
        manifest_required=True,
    )
    assert result.outcome == EvidenceResolutionOutcome.MANIFEST_UNAVAILABLE
    assert result.traceability_status == TraceabilityStatus.UNVALIDATED.value
    assert result.warning == WARNING_MANIFEST_UNAVAILABLE


def test_missing_sets_warning() -> None:
    result = resolve_raw_evidence_identifier(RawEvidenceIdentifier(None, None), _manifest())
    assert result.traceability_warning == WARNING_MISSING_EVIDENCE_ID


def test_ref_warning_text() -> None:
    result = resolve_raw_evidence_identifier(
        RawEvidenceIdentifier("REF_001", None), _manifest()
    )
    assert result.warning == WARNING_REFERENCE_AS_EVIDENCE
