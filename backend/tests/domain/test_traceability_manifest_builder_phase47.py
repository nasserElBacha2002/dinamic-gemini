"""Phase 4.7 — traceability_manifest.json domain builder tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

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
from src.domain.traceability_artifact.builder import (
    TRACEABILITY_MANIFEST_SCHEMA_VERSION,
    TraceabilityManifestBuildInput,
    build_traceability_manifest,
    traceability_manifest_is_json_safe,
)
from src.domain.traceability_artifact.canonical_json import sha256_canonical_json
from src.pipeline.services.provider_execution_request import PROVIDER_IMAGE_MANIFEST_ORDER_KEY


def _manifest() -> ExecutionImageManifest:
    return ExecutionImageManifest(
        job_id="job-1",
        entries=(
            ExecutionImageEntry(
                manifest_entry_id="IMG_001",
                source_asset_id="asset-1",
                source_image_id="asset-1",
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=1,
                storage_reference="photos/asset-1.jpg",
            ),
            ExecutionImageEntry(
                manifest_entry_id="REF_001",
                source_asset_id="ref-1",
                source_image_id="ref-1",
                role=ExecutionImageRole.REFERENCE_IMAGE,
                payload_ordinal=2,
                storage_reference="photos/ref-1.jpg",
            ),
        ),
        excluded_entries=(),
    )


def _row(
    *,
    status: str,
    role: ResultEvidenceRole | None,
    source_image_id: str | None = None,
    warning: str | None = None,
    mid: str | None = None,
) -> ResultEvidenceRecord:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    return ResultEvidenceRecord(
        id="re-1",
        job_id="job-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        position_id="pos-1",
        entity_uid="job_E1",
        model_entity_id="E1",
        raw_manifest_entry_id=mid,
        manifest_entry_id=mid,
        raw_source_image_id=None,
        resolved_manifest_entry_id=mid,
        source_image_id=source_image_id,
        source_asset_id=source_image_id,
        traceability_status=status,
        traceability_warning=warning,
        role=role,
        provider="gemini",
        model_name="gemini-2.0",
        schema_version="2.1",
        manifest_version=1,
        has_valid_evidence=status == TraceabilityStatus.VALID.value
        and role == ResultEvidenceRole.PRIMARY_EVIDENCE
        and source_image_id is not None,
        evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
        created_at=now,
        updated_at=now,
    )


def _input(*rows: ResultEvidenceRecord) -> TraceabilityManifestBuildInput:
    manifest = _manifest()
    return TraceabilityManifestBuildInput(
        job_id="job-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        run_id="run",
        provider="gemini",
        model_name="gemini-2.0",
        created_at=datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc),
        prompt_composition=manifest_composition_projection(manifest),
        run_metadata={
            PROVIDER_IMAGE_MANIFEST_ORDER_KEY: [
                {
                    "provider_position": 0,
                    "manifest_entry_id": "IMG_001",
                    "source_image_id": "asset-1",
                    "role": "primary_evidence",
                }
            ]
        },
        result_evidence_rows=rows,
    )


def test_valid_primary_row_is_displayable() -> None:
    body = build_traceability_manifest(
        _input(
            _row(
                status=TraceabilityStatus.VALID.value,
                role=ResultEvidenceRole.PRIMARY_EVIDENCE,
                source_image_id="asset-1",
                mid="IMG_001",
            )
        )
    )
    row = body["result_evidence"][0]
    assert row["displayable"] is True
    assert body["summary"]["displayable"] == 1


def test_invalid_reference_not_displayable() -> None:
    body = build_traceability_manifest(
        _input(
            _row(
                status=TraceabilityStatus.INVALID.value,
                role=ResultEvidenceRole.REFERENCE_IMAGE,
                warning="Provider returned a reference image as evidence.",
                mid="REF_001",
            )
        )
    )
    assert body["result_evidence"][0]["displayable"] is False
    assert body["summary"]["reference_rejected"] == 1


def test_missing_and_unvalidated_not_displayable() -> None:
    body = build_traceability_manifest(
        _input(
            _row(status=TraceabilityStatus.MISSING.value, role=None),
            _row(status=TraceabilityStatus.UNVALIDATED.value, role=ResultEvidenceRole.UNKNOWN),
        )
    )
    assert all(not row["displayable"] for row in body["result_evidence"])
    assert body["summary"]["missing"] == 1
    assert body["summary"]["unvalidated"] == 1


def test_conflict_invalid_warning_counted() -> None:
    body = build_traceability_manifest(
        _input(
            _row(
                status=TraceabilityStatus.INVALID.value,
                role=ResultEvidenceRole.UNKNOWN,
                warning="Provider returned conflicting manifest_entry_id and source_image_id.",
                mid="IMG_001",
            )
        )
    )
    assert body["summary"]["conflicting_identifier"] == 1


def test_hashes_are_deterministic() -> None:
    payload = _input(
        _row(
            status=TraceabilityStatus.VALID.value,
            role=ResultEvidenceRole.PRIMARY_EVIDENCE,
            source_image_id="asset-1",
            mid="IMG_001",
        )
    )
    first = build_traceability_manifest(payload)
    second = build_traceability_manifest(payload)
    assert first["integrity"]["result_evidence_hash"] == second["integrity"]["result_evidence_hash"]
    assert (
        first["integrity"]["traceability_manifest_hash"]
        == second["integrity"]["traceability_manifest_hash"]
    )


def test_json_safe_and_schema_version() -> None:
    body = build_traceability_manifest(
        _input(
            _row(
                status=TraceabilityStatus.VALID.value,
                role=ResultEvidenceRole.PRIMARY_EVIDENCE,
                source_image_id="asset-1",
                mid="IMG_001",
            )
        )
    )
    assert body["schema_version"] == TRACEABILITY_MANIFEST_SCHEMA_VERSION
    assert traceability_manifest_is_json_safe(body)
    json.dumps(body)


def test_provider_order_unavailable_warning() -> None:
    payload = _input(
        _row(
            status=TraceabilityStatus.VALID.value,
            role=ResultEvidenceRole.PRIMARY_EVIDENCE,
            source_image_id="asset-1",
            mid="IMG_001",
        )
    )
    payload = TraceabilityManifestBuildInput(
        **{**payload.__dict__, "run_metadata": {}}
    )
    body = build_traceability_manifest(payload)
    order = body["provider_image_manifest_order"]
    assert order["status"] == "unavailable"
    assert "unavailable" in order["warning"].lower()


def test_execution_manifest_section_present() -> None:
    body = build_traceability_manifest(
        _input(
            _row(
                status=TraceabilityStatus.VALID.value,
                role=ResultEvidenceRole.PRIMARY_EVIDENCE,
                source_image_id="asset-1",
                mid="IMG_001",
            )
        )
    )
    assert body["execution_image_manifest"]["entries"][0]["manifest_entry_id"] == "IMG_001"
    assert body["integrity"]["execution_image_manifest_hash"] == sha256_canonical_json(
        body["execution_image_manifest"]
    )
