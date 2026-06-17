"""Phase 4.3 — prompt composition from canonical execution manifest."""

from __future__ import annotations

from src.domain.execution_image_manifest import ExecutionImageEntry, ExecutionImageManifest, ExecutionImageRole
from src.domain.prompt_image_projection import COMPOSITION_KEY_PROMPT_IMAGE_PROJECTION
from src.llm.prompt_composer.enrichments import enrich_prompt_with_execution_manifest
from src.pipeline.services.hybrid_analysis_prompt import build_hybrid_analysis_prompt_with_traceability
from src.pipeline.context.run_context import RunContext
from unittest.mock import MagicMock


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


def test_enrich_prompt_separates_primary_and_reference_sections() -> None:
    text, projection = enrich_prompt_with_execution_manifest("BASE", _manifest())
    assert "PRIMARY EVIDENCE IMAGES" in text
    assert "REFERENCE IMAGES" in text
    assert "IMG_001" in text
    assert "REF_001" in text
    assert "source_image_id='asset-1'" in text
    assert "manifest_entry_id" in text.lower() or "IMG_001" in text
    assert projection.ordered_manifest_entry_ids == ("REF_001", "IMG_001")


def test_build_hybrid_prompt_uses_manifest_projection(monkeypatch) -> None:
    context = MagicMock(spec=RunContext)
    context.settings = MagicMock()
    context.settings.hybrid_prompt = "global_v22"
    context.settings.prompt_version = None
    context.job_prompt_version = None
    context.job_prompt_key = None
    context.pipeline_provider_name = None
    context.job_prompt_parity_mode = False
    context.supplier_prompt_resolution = None
    context.job_model_name = None
    context.run_dir = MagicMock()
    context.job_input = MagicMock()
    context.job_input.input_type = "photos"

    prompt, composition = build_hybrid_analysis_prompt_with_traceability(
        context,
        execution_manifest=_manifest(),
    )
    assert "IMG_001" in prompt
    assert composition["frames_sent_ids"] == ["asset-1"]
    assert "IMG_001" in composition["prompt_listed_image_ids"]
    assert composition.get("execution_image_manifest") is not None
    assert COMPOSITION_KEY_PROMPT_IMAGE_PROJECTION in composition
