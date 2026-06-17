"""Phase 4.4 corrections — unified provider output evidence identifier contract."""

from __future__ import annotations

from src.llm.openai_sdk_adapter import _JSON_OBJECT_SUFFIX
from src.llm.prompt_composer.enrichments import enrich_prompt_with_execution_manifest
from src.llm.prompt_composer.hybrid_profiles import (
    CLAUDE_JSON_ENTITY_OUTPUT_KEYS,
    CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX,
)
from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
    EVIDENCE_RETURN_IDENTIFIER_FIELD,
    LEGACY_EVIDENCE_RETURN_FIELD,
)
from src.models.schemas import EntityV21


def test_gemini_schema_prefers_manifest_entry_id() -> None:
    fields = EntityV21.model_fields
    assert "manifest_entry_id" in fields
    assert "source_image_id" in fields
    assert fields["manifest_entry_id"].is_required() is False
    assert fields["source_image_id"].is_required() is False
    assert "Preferred" in (fields["manifest_entry_id"].description or "")
    assert "Legacy" in (fields["source_image_id"].description or "")


def test_openai_suffix_prefers_manifest_entry_id() -> None:
    assert "manifest_entry_id is the preferred evidence identifier" in _JSON_OBJECT_SUFFIX
    assert "source_image_id is optional legacy compatibility only" in _JSON_OBJECT_SUFFIX
    assert _JSON_OBJECT_SUFFIX.index("manifest_entry_id") < _JSON_OBJECT_SUFFIX.index(
        "source_image_id is optional"
    )


def test_claude_suffix_lists_manifest_entry_id_before_legacy() -> None:
    assert "manifest_entry_id" in CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX
    mid_idx = CLAUDE_JSON_ENTITY_OUTPUT_KEYS.index("manifest_entry_id")
    sid_idx = CLAUDE_JSON_ENTITY_OUTPUT_KEYS.index("source_image_id")
    assert mid_idx < sid_idx


def test_manifest_prompt_forbids_ref_as_evidence() -> None:
    manifest = ExecutionImageManifest(
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
    prompt, _ = enrich_prompt_with_execution_manifest("BASE", manifest)
    assert EVIDENCE_RETURN_IDENTIFIER_FIELD in prompt
    assert "REFERENCE images are classification context only" in prompt
    assert LEGACY_EVIDENCE_RETURN_FIELD in prompt
    assert "is preferred" in prompt
