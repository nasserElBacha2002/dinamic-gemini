"""E4 integration tests: supplier resolution + effective prompt in ``build_hybrid_analysis_prompt_with_traceability``."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from PIL import Image

from src.application.services.aisle_analysis_context_builder import SUPPLIER_REFERENCES_INSTRUCTION
from src.application.services.supplier_prompt_resolver import (
    SupplierPromptFallbackReason,
    SupplierPromptResolution,
    SupplierPromptResolutionErrorCode,
)
from src.jobs.models import JobInput
from src.llm.prompt_composer.enrichments import (
    IMAGE_ID_TRACEABILITY_ENRICHMENT_ID,
    SUPPLIER_EDITABLE_INSTRUCTIONS_ENRICHMENT_ID,
)
from src.llm.prompt_composer.prompt_traceability import (
    COMPOSITION_STEP_EFFECTIVE_SUPPLIER_PROMPT,
    LLM_METADATA_KEY_PROMPT_COMPOSITION,
    apply_execution_layer_to_composition,
    validate_prompt_composition_dict,
)
from src.llm.prompt_composer.protected_prompt_contract import HYBRID_V21_SHARED_CONTRACT_MARKERS
from src.llm.types import LLMRequest
from src.pipeline.context.run_context import RunContext
from src.pipeline.contracts.analysis_context import AnalysisContext, VisualReferenceContext
from src.pipeline.services.hybrid_analysis_prompt import (
    build_hybrid_analysis_prompt_with_traceability,
)


def _minimal_run_context(
    *,
    supplier_prompt_resolution: SupplierPromptResolution | None = None,
    analysis_context: AnalysisContext | None = None,
) -> RunContext:
    log = MagicMock()
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    settings.llm_provider = "gemini"
    settings.artifact_storage_legacy_local_read_enabled = False
    job_input = JobInput(
        video_path="/tmp/x.mp4",
        mode="hybrid",
        input_type="video",
        metadata={"inventory_id": "inv-1", "aisle_id": "aisle-1"},
    )
    return RunContext(
        job_id="job-1",
        run_id="run-1",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/job-1/run-1"),
        job_input=job_input,
        settings=settings,
        logger=log,
        pipeline_provider_name="gemini",
        job_model_name="gemini-2.0-flash",
        supplier_prompt_resolution=supplier_prompt_resolution,
        analysis_context=analysis_context,
    )


def _resolution(**kwargs: Any) -> SupplierPromptResolution:
    d: dict[str, Any] = {
        "inventory_id": "inv-1",
        "aisle_id": "aisle-1",
        "client_id": "c1",
        "client_supplier_id": "s1",
        "provider_name": "gemini",
        "model_name": None,
        "supplier_prompt_config_id": None,
        "supplier_prompt_config_version": None,
        "editable_instructions": None,
        "fallback_used": False,
        "fallback_reason": None,
        "resolution_status": "resolved",
        "warnings": (),
        "error_code": None,
    }
    d.update(kwargs)
    return SupplierPromptResolution(**d)


def test_e4_resolved_supplier_appends_section_and_metadata() -> None:
    res = _resolution(
        resolution_status="resolved",
        editable_instructions="Prefer SKU from left label.",
        supplier_prompt_config_id="cfg-1",
        supplier_prompt_config_version=2,
    )
    ctx = _minimal_run_context(supplier_prompt_resolution=res)
    text, comp = build_hybrid_analysis_prompt_with_traceability(ctx)
    assert "SUPPLIER-SPECIFIC EDITABLE INSTRUCTIONS" in text
    assert "Prefer SKU from left label." in text
    eff = comp.get("effective_prompt") or {}
    assert eff.get("supplier_instructions_applied") is True
    assert eff.get("supplier_prompt_config_id") == "cfg-1"
    assert eff.get("supplier_prompt_config_version") == 2
    assert eff.get("effective_prompt_hash") == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert comp.get("final_prompt_text") == text
    assert comp.get("prompt_hash") == hashlib.sha256(text.encode("utf-8")).hexdigest()
    for m in HYBRID_V21_SHARED_CONTRACT_MARKERS:
        assert m in text
    assert validate_prompt_composition_dict(comp) == []


def test_e4_fallback_no_supplier_delimiter_same_as_legacy_text() -> None:
    res = _resolution(
        resolution_status="fallback",
        fallback_used=True,
        fallback_reason=SupplierPromptFallbackReason.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG,
    )
    ctx_fb = _minimal_run_context(supplier_prompt_resolution=res)
    text_fb, comp_fb = build_hybrid_analysis_prompt_with_traceability(ctx_fb)
    ctx_none = _minimal_run_context(supplier_prompt_resolution=None)
    text_none, comp_none = build_hybrid_analysis_prompt_with_traceability(ctx_none)
    assert "SUPPLIER-SPECIFIC EDITABLE INSTRUCTIONS" not in text_fb
    assert text_fb == text_none
    assert comp_fb.get("prompt_hash") == comp_none.get("prompt_hash")
    eff = comp_fb.get("effective_prompt") or {}
    assert eff.get("fallback_used") is True
    assert eff.get("fallback_reason") == SupplierPromptFallbackReason.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG


def test_e4_inventory_without_client_fallback_matches_baseline() -> None:
    res = _resolution(
        resolution_status="fallback",
        fallback_used=True,
        fallback_reason=SupplierPromptFallbackReason.INVENTORY_WITHOUT_CLIENT,
    )
    ctx = _minimal_run_context(supplier_prompt_resolution=res)
    text, comp = build_hybrid_analysis_prompt_with_traceability(ctx)
    ctx_base = _minimal_run_context(supplier_prompt_resolution=None)
    base_text, _ = build_hybrid_analysis_prompt_with_traceability(ctx_base)
    assert text == base_text
    assert (comp.get("effective_prompt") or {}).get("fallback_reason") == (
        SupplierPromptFallbackReason.INVENTORY_WITHOUT_CLIENT
    )


def test_e4_openai_pipeline_prompt_excludes_adapter_json_suffix() -> None:
    res = _resolution(
        resolution_status="resolved",
        editable_instructions="Operational note.",
        supplier_prompt_config_id="c1",
        supplier_prompt_config_version=1,
    )
    ctx = _minimal_run_context(supplier_prompt_resolution=res)
    ctx.pipeline_provider_name = "openai"
    text, _ = build_hybrid_analysis_prompt_with_traceability(ctx)
    assert "Output requirement: respond with a single JSON object only" not in text
    assert "SUPPLIER-SPECIFIC EDITABLE INSTRUCTIONS" in text


def test_e4_reference_metadata_propagates_to_effective_prompt_block() -> None:
    res = _resolution(
        resolution_status="resolved",
        editable_instructions="x",
        supplier_prompt_config_id="c1",
        supplier_prompt_config_version=1,
    )
    ac = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="ref-a",
                source_path="s",
                mime_type="image/jpeg",
                role="supplier_reference",
            )
        ],
        instructions=[],
        metadata={"reference_source": "supplier_inventory"},
    )
    ctx = _minimal_run_context(supplier_prompt_resolution=res, analysis_context=ac)
    _, comp = build_hybrid_analysis_prompt_with_traceability(ctx)
    eff = comp.get("effective_prompt") or {}
    assert eff.get("reference_source") == "supplier_inventory"
    assert eff.get("reference_image_ids") == ["ref-a"]


def test_e4_composition_step_records_effective_supplier() -> None:
    res = _resolution(
        resolution_status="resolved",
        editable_instructions="note",
        supplier_prompt_config_id="c1",
        supplier_prompt_config_version=1,
    )
    ctx = _minimal_run_context(supplier_prompt_resolution=res)
    _, comp = build_hybrid_analysis_prompt_with_traceability(ctx)
    steps = comp.get("composition_steps") or []
    assert any(s.get("step") == COMPOSITION_STEP_EFFECTIVE_SUPPLIER_PROMPT for s in steps)


def test_e4_empty_resolved_instructions_warning_not_delimiter() -> None:
    res = _resolution(
        resolution_status="resolved",
        editable_instructions="   ",
        supplier_prompt_config_id="c-empty",
        supplier_prompt_config_version=3,
    )
    ctx = _minimal_run_context(supplier_prompt_resolution=res)
    text, comp = build_hybrid_analysis_prompt_with_traceability(ctx)
    ctx_none = _minimal_run_context(supplier_prompt_resolution=None)
    base, _ = build_hybrid_analysis_prompt_with_traceability(ctx_none)
    assert text == base
    assert "EMPTY_SUPPLIER_INSTRUCTIONS" in (comp.get("effective_prompt") or {}).get("warnings", [])


def test_e4_error_resolution_should_not_reach_prompt_builder_in_production() -> None:
    """Composer still keeps protected-only text if an error resolution were ever passed."""
    res = _resolution(
        resolution_status="error",
        error_code=SupplierPromptResolutionErrorCode.INVALID_SCOPE_INPUT,
        editable_instructions="NEVER",
    )
    ctx = _minimal_run_context(supplier_prompt_resolution=res)
    text, comp = build_hybrid_analysis_prompt_with_traceability(ctx)
    assert "NEVER" not in text
    eff = comp.get("effective_prompt") or {}
    assert eff.get("resolution_status") == "error"
    assert "RESOLUTION_STATUS_ERROR" in eff.get("warnings", [])


def test_e41_llm_request_metadata_includes_effective_prompt_resolved() -> None:
    """Same merge + ``LLMRequest`` attachment as ``HybridGlobalAnalysisStrategy._analyze_once`` (L249–277).

    Importing ``HybridGlobalAnalysisStrategy`` can hit ``src.pipeline.providers`` package init cycles
    under some pytest collection orders; this test pins the observable ``metadata`` shape instead.
    """
    res = _resolution(
        resolution_status="resolved",
        editable_instructions="Prefer SKU from left label.",
        supplier_prompt_config_id="cfg-1",
        supplier_prompt_config_version=2,
    )
    ctx = _minimal_run_context(supplier_prompt_resolution=res)
    prompt_text, comp = build_hybrid_analysis_prompt_with_traceability(ctx)
    merged = apply_execution_layer_to_composition(
        comp,
        resolved_llm_provider_key="gemini",
        model_name="gemini-2.0-flash",
    )
    req = LLMRequest(
        job_id=ctx.job_id,
        frames=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        prompt=prompt_text,
        schema_version="v2.1",
        metadata={LLM_METADATA_KEY_PROMPT_COMPOSITION: merged},
    )
    pc = req.metadata[LLM_METADATA_KEY_PROMPT_COMPOSITION]
    ep = pc["effective_prompt"]
    assert ep["supplier_instructions_applied"] is True
    assert ep["supplier_prompt_config_id"] == "cfg-1"
    assert ep["supplier_prompt_config_version"] == 2
    assert ep["resolution_status"] == "resolved"
    assert ep["fallback_used"] is False
    assert ep["effective_prompt_hash"] == pc["prompt_hash"]
    assert "Prefer SKU from left label." in req.prompt
    assert "Prefer SKU from left label." not in str(ep)


def test_e41_llm_request_metadata_includes_effective_prompt_fallback() -> None:
    res = _resolution(
        resolution_status="fallback",
        fallback_used=True,
        fallback_reason=SupplierPromptFallbackReason.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG,
    )
    ctx = _minimal_run_context(supplier_prompt_resolution=res)
    prompt_text, comp = build_hybrid_analysis_prompt_with_traceability(ctx)
    merged = apply_execution_layer_to_composition(
        comp,
        resolved_llm_provider_key="gemini",
        model_name="gemini-2.0-flash",
    )
    req = LLMRequest(
        job_id=ctx.job_id,
        frames=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        prompt=prompt_text,
        schema_version="v2.1",
        metadata={LLM_METADATA_KEY_PROMPT_COMPOSITION: merged},
    )
    ctx_base = _minimal_run_context(supplier_prompt_resolution=None)
    baseline_prompt, _ = build_hybrid_analysis_prompt_with_traceability(ctx_base)
    assert req.prompt == baseline_prompt
    ep = req.metadata[LLM_METADATA_KEY_PROMPT_COMPOSITION]["effective_prompt"]
    assert ep["supplier_instructions_applied"] is False
    assert ep["fallback_used"] is True
    assert ep["fallback_reason"] == SupplierPromptFallbackReason.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG
    assert ep["resolution_status"] == "fallback"


def test_e5_e4_combined_image_ids_supplier_prompt_and_visual_reference_bundle(tmp_path: Path) -> None:
    """E5 + E4: photos manifest enrichment, supplier editable block, and supplier visual references."""
    job_root = tmp_path / "job-1"
    run_dir = job_root / "run-1"
    run_dir.mkdir(parents=True)
    photos_dir = job_root / "input_photos"
    photos_dir.mkdir()
    Image.new("RGB", (8, 8)).save(photos_dir / "0000_a.jpg")
    manifest = {
        "input_type": "photos",
        "photos": [
            {
                "index": 1,
                "image_id": "asset-1",
                "original_filename": "a.jpg",
                "stored_filename": "0000_a.jpg",
            }
        ],
    }
    (job_root / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    ref_path = tmp_path / "supplier_ref.png"
    Image.new("RGB", (8, 8), color=(2, 3, 4)).save(ref_path)

    res = _resolution(
        resolution_status="resolved",
        editable_instructions="Prefer SKU from left label.",
        supplier_prompt_config_id="cfg-1",
        supplier_prompt_config_version=2,
    )
    ac = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="sr-1",
                source_path=str(ref_path),
                mime_type="image/png",
                role="supplier_reference",
                resolved_path=str(ref_path),
            )
        ],
        instructions=[SUPPLIER_REFERENCES_INSTRUCTION],
        metadata={"reference_source": "supplier_reference_images"},
    )
    log = MagicMock()
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    settings.llm_provider = "gemini"
    settings.artifact_storage_legacy_local_read_enabled = False
    job_input = JobInput(
        video_path="",
        mode="hybrid",
        input_type="photos",
        input_manifest_path="input_manifest.json",
        photos_dir="input_photos",
        metadata={"inventory_id": "inv-1", "aisle_id": "aisle-1"},
    )
    ctx = RunContext(
        job_id="job-1",
        run_id="run-1",
        workspace_path=job_root,
        run_dir=run_dir,
        job_input=job_input,
        settings=settings,
        logger=log,
        pipeline_provider_name="gemini",
        job_model_name="gemini-2.0-flash",
        supplier_prompt_resolution=res,
        analysis_context=ac,
    )
    text, comp = build_hybrid_analysis_prompt_with_traceability(ctx)
    enrich = list(comp.get("enrichments_applied") or [])
    assert IMAGE_ID_TRACEABILITY_ENRICHMENT_ID in enrich
    assert SUPPLIER_EDITABLE_INSTRUCTIONS_ENRICHMENT_ID in enrich
    assert "Prefer SKU from left label." in text

    from src.pipeline.adapters.hybrid_global_analysis_strategy import (
        _prepare_hybrid_llm_visual_bundle,
    )

    vb = _prepare_hybrid_llm_visual_bundle(
        supports_visual_reference_context=True,
        analysis_context=ac,
        job_id="job-1",
    )
    assert vb.consumed_count == 1
    assert vb.visual_reference_attachments[0]["resolved"] is True
    assert vb.visual_reference_attachments[0]["role"] == "visual_reference"
    assert SUPPLIER_REFERENCES_INSTRUCTION in (vb.context_instruction or "")
