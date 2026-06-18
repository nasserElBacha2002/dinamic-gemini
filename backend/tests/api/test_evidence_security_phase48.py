"""Phase 4.8 — evidence API security filtering tests."""

from __future__ import annotations

import json
import re

from src.api.mappers.result_evidence_mapper import result_evidence_view_to_response
from src.application.services.result_evidence_query_service import ResultEvidenceViewModel


def test_api_response_excludes_local_absolute_paths() -> None:
    view = ResultEvidenceViewModel(
        displayable=False,
        traceability_status="valid",
        traceability_warning="safe warning",
        role="primary_evidence",
        source_image_id="asset-1",
        source_asset_id="asset-1",
        resolved_manifest_entry_id="IMG_001",
        raw_manifest_entry_id="IMG_001",
        raw_source_image_id=None,
        image_url=None,
        thumbnail_url=None,
        image_access_status="not_allowed",
        source_kind="structural_result_evidence",
        provider="gemini",
        model_name="gemini-2.0",
    )
    payload = result_evidence_view_to_response(view).model_dump(mode="json")
    text = json.dumps(payload)
    assert "/Users/" not in text
    assert "prompt_composition" not in text
    assert "provider_raw" not in text


def test_non_displayable_evidence_has_no_signed_url() -> None:
    view = ResultEvidenceViewModel(
        displayable=False,
        traceability_status="invalid",
        traceability_warning="reference rejected",
        role="reference_image",
        source_image_id="ref-1",
        source_asset_id="ref-1",
        resolved_manifest_entry_id="REF_001",
        raw_manifest_entry_id="REF_001",
        raw_source_image_id=None,
        image_url=None,
        thumbnail_url=None,
        image_access_status="not_allowed",
        source_kind="structural_result_evidence",
        provider="gemini",
        model_name="gemini-2.0",
    )
    payload = result_evidence_view_to_response(view).model_dump(mode="json")
    assert payload["image_url"] is None
    assert payload["displayable"] is False


def test_artifact_metadata_has_no_credentials_fields() -> None:
    from src.api.mappers.result_evidence_mapper import artifact_read_model_to_response
    from src.application.services.result_evidence_query_service import TraceabilityArtifactReadModel
    from datetime import datetime, timezone

    model = TraceabilityArtifactReadModel(
        kind="traceability_manifest",
        published=True,
        required=True,
        status="published",
        storage_key="jobs/job-1/run/traceability_manifest.json",
        content_hash="abc123",
        size_bytes=10,
        published_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
    )
    payload = artifact_read_model_to_response(model).model_dump(mode="json")
    forbidden = re.compile(r"(secret|password|credential|aws_secret)", re.I)
    assert not forbidden.search(json.dumps(payload))
