"""
Hybrid global-analysis prompt assembly (provider-neutral).

**Phase E1 / E4:** The string returned here is the **ProtectedSystemContractBlock** (hybrid base from
``compose_hybrid_base``) plus optional **image-id enrichments**, then (Phase E4) an optional
**supplier-editable** block from ``EffectivePromptComposer`` when ``RunContext.supplier_prompt_resolution``
is set by the v3 executor. Fallback/error resolution never replaces the protected contract text.

Uses ``prompt_composer.hybrid_assembly`` for profile + base composition; applies photo enrichments
once here (step 4 of the Phase 5 flow).

**Profile vs Phase 7 version (see also ``prompt_traceability`` module doc):**

- **Profile:** ``resolve_hybrid_profile_name`` + ``compose_hybrid_base`` determine prompt **content**.
  Recorded in composition as ``profile_name``, ``job_prompt_key``, ``settings_hybrid_prompt_key``.
- **``prompt_version``:** Optional label from ``RunContext.job_prompt_version`` or ``settings.prompt_version``
  only; recorded in composition; **no effect** on resolution or text.
- **Hashes:** ``prompt_hash`` / ``base_prompt_hash`` fingerprint the strings only.
"""

from __future__ import annotations

from typing import Any

from src.jobs.image_identity import load_job_images_from_manifest
from src.llm.prompt_composer.enrichments import (
    IMAGE_ID_TRACEABILITY_ENRICHMENT_ID,
    SUPPLIER_EDITABLE_INSTRUCTIONS_ENRICHMENT_ID,
    enrich_prompt_with_image_ids,
)
from src.llm.prompt_composer.hybrid_assembly import (
    compose_hybrid_base,
    resolve_hybrid_profile_name,
)
from src.llm.prompt_composer.prompt_traceability import (
    COMPOSITION_STEP_COMPOSE_HYBRID_BASE,
    COMPOSITION_STEP_EFFECTIVE_SUPPLIER_PROMPT,
    COMPOSITION_STEP_ENRICH_IMAGE_IDS,
    COMPOSITION_STEP_NORMALIZE_PIPELINE_PROVIDER,
    COMPOSITION_STEP_PROMPT_PARITY_MODE,
    COMPOSITION_STEP_RESOLVE_PROFILE,
    build_prompt_composition_dict,
    sha256_utf8,
)
from src.pipeline.context.run_context import RunContext
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_from_dict
from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.pipeline.services.effective_prompt_composer import (
    EffectivePromptComposer,
    EffectivePromptComposerInput,
    EffectivePromptComposition,
)


def _job_metadata_inventory_aisle(context: RunContext) -> tuple[str | None, str | None]:
    md = (context.job_input.metadata or {}) if context.job_input else {}
    inv = md.get("inventory_id")
    aisle = md.get("aisle_id")
    inv_s = str(inv).strip() if inv is not None and str(inv).strip() else None
    aisle_s = str(aisle).strip() if aisle is not None and str(aisle).strip() else None
    return inv_s, aisle_s


def _reference_metadata_for_effective_prompt(context: RunContext) -> tuple[str | None, tuple[str, ...]]:
    ac = getattr(context, "analysis_context", None)
    if ac is None:
        return None, ()
    meta = ac.metadata or {}
    ref_src_raw = meta.get("reference_source") if isinstance(meta, dict) else None
    ref_src = (
        str(ref_src_raw).strip()
        if ref_src_raw is not None and str(ref_src_raw).strip()
        else None
    )
    ids = tuple(
        str(v.reference_id)
        for v in (ac.visual_references or [])
        if getattr(v, "reference_id", None) and str(v.reference_id).strip()
    )
    return ref_src, ids


def _effective_prompt_composition_subtree(
    eff: EffectivePromptComposition,
    *,
    resolution_status: str,
    resolution_error_code: str | None,
) -> dict[str, Any]:
    return {
        "protected_prompt_contract_key": eff.protected_prompt_contract_key,
        "protected_prompt_contract_version": eff.protected_prompt_contract_version,
        "effective_prompt_hash": eff.effective_prompt_hash,
        "supplier_prompt_config_id": eff.supplier_prompt_config_id,
        "supplier_prompt_config_version": eff.supplier_prompt_config_version,
        "supplier_instructions_applied": eff.supplier_instructions_applied,
        "fallback_used": eff.fallback_used,
        "fallback_reason": eff.fallback_reason,
        "resolution_status": resolution_status,
        "resolution_error_code": resolution_error_code,
        "reference_source": eff.reference_source,
        "reference_image_ids": list(eff.reference_image_ids),
        "warnings": list(eff.warnings),
        "sections": list(eff.sections),
    }


def build_hybrid_analysis_prompt_with_traceability(
    context: RunContext,
) -> tuple[str, dict[str, Any]]:
    """
    Same prompt text as legacy assembly, plus JSON-serializable composition metadata (Phase 6).

    Prompt construction order is unchanged: profile → provider → base → optional image-id enrichment.
    Returns ``(prompt_text, composition)`` where ``composition`` is the **construction-only** slice;
    the analysis strategy adds execution-layer fields (resolved provider, model) before attaching to
    ``LLMRequest.metadata`` (see ``apply_execution_layer_to_composition``).
    """
    settings = context.settings
    steps: list[dict[str, Any]] = []
    profile = resolve_hybrid_profile_name(
        job_prompt_key=getattr(context, "job_prompt_key", None),
        settings=settings,
    )
    steps.append({"step": COMPOSITION_STEP_RESOLVE_PROFILE, "profile_name": profile})
    effective_provider = normalize_pipeline_provider_key(
        getattr(context, "pipeline_provider_name", None),
        settings,
    )
    steps.append(
        {
            "step": COMPOSITION_STEP_NORMALIZE_PIPELINE_PROVIDER,
            "pipeline_provider_key": effective_provider,
        }
    )
    parity = bool(getattr(context, "job_prompt_parity_mode", False))
    if parity:
        steps.append({"step": COMPOSITION_STEP_PROMPT_PARITY_MODE, "prompt_parity_mode": True})
    base_prompt = compose_hybrid_base(profile, effective_provider, prompt_parity_mode=parity)
    steps.append({"step": COMPOSITION_STEP_COMPOSE_HYBRID_BASE})
    enrichments_applied: list[str] = []
    prompt_text = base_prompt
    job_input = getattr(context, "job_input", None)
    if job_input and getattr(job_input, "input_type", "") == "photos":
        manifest_rel = (getattr(job_input, "input_manifest_path", None) or "").strip()
        photos_dir_rel = (getattr(job_input, "photos_dir", None) or "").strip()
        if manifest_rel and photos_dir_rel:
            job_dir = context.run_dir.parent
            manifest_path = job_dir / manifest_rel
            images = load_job_images_from_manifest(manifest_path, photos_dir_rel)
            if images:
                prompt_text = enrich_prompt_with_image_ids(base_prompt, images)
                enrichments_applied.append(IMAGE_ID_TRACEABILITY_ENRICHMENT_ID)
                steps.append(
                    {
                        "step": COMPOSITION_STEP_ENRICH_IMAGE_IDS,
                        "enrichment_id": IMAGE_ID_TRACEABILITY_ENRICHMENT_ID,
                        "image_count": len(images),
                    }
                )
    jpk = getattr(context, "job_prompt_key", None)
    job_prompt_key_opt = jpk.strip() if isinstance(jpk, str) and jpk.strip() else None
    shp = getattr(settings, "hybrid_prompt", None)
    settings_prompt_opt = shp.strip() if isinstance(shp, str) and shp.strip() else None
    # Phase 7: optional traceability label only (not profile selection). job_prompt_version wins over settings.prompt_version.
    jpv = getattr(context, "job_prompt_version", None)
    prompt_version_opt = None
    if isinstance(jpv, str) and jpv.strip():
        prompt_version_opt = jpv.strip()
    else:
        spv = getattr(settings, "prompt_version", None)
        if isinstance(spv, str) and spv.strip():
            prompt_version_opt = spv.strip()
    composition = build_prompt_composition_dict(
        profile_name=profile,
        pipeline_provider_key=effective_provider,
        base_prompt_text=base_prompt,
        final_prompt_text=prompt_text,
        enrichments_applied=enrichments_applied,
        composition_steps=steps,
        job_prompt_key=job_prompt_key_opt,
        settings_hybrid_prompt_key=settings_prompt_opt,
        prompt_version=prompt_version_opt,
        prompt_parity_mode=parity,
    )

    supplier_resolution = getattr(context, "supplier_prompt_resolution", None)
    if supplier_resolution is not None:
        inv_id, aisle_id = _job_metadata_inventory_aisle(context)
        ref_src, ref_ids = _reference_metadata_for_effective_prompt(context)
        composer = EffectivePromptComposer()
        eff = composer.compose(
            EffectivePromptComposerInput(
                protected_prompt_text=prompt_text,
                provider_name=effective_provider,
                model_name=getattr(context, "job_model_name", None),
                supplier_resolution=supplier_resolution,
                inventory_id=inv_id,
                aisle_id=aisle_id,
                reference_source=ref_src,
                reference_image_ids=ref_ids,
            )
        )
        steps = list(composition.get("composition_steps") or [])
        steps.append(
            {
                "step": COMPOSITION_STEP_EFFECTIVE_SUPPLIER_PROMPT,
                "supplier_instructions_applied": eff.supplier_instructions_applied,
                "fallback_used": eff.fallback_used,
            }
        )
        composition["composition_steps"] = steps
        composition["effective_prompt"] = _effective_prompt_composition_subtree(
            eff,
            resolution_status=supplier_resolution.resolution_status,
            resolution_error_code=supplier_resolution.error_code,
        )
        if eff.effective_prompt_text != prompt_text:
            prompt_text = eff.effective_prompt_text
            composition["final_prompt_text"] = prompt_text
            composition["prompt_hash"] = sha256_utf8(prompt_text)
        if eff.supplier_instructions_applied:
            ea = list(composition.get("enrichments_applied") or [])
            if SUPPLIER_EDITABLE_INSTRUCTIONS_ENRICHMENT_ID not in ea:
                ea.append(SUPPLIER_EDITABLE_INSTRUCTIONS_ENRICHMENT_ID)
            composition["enrichments_applied"] = ea

    return prompt_text, composition


def build_hybrid_analysis_prompt_text(context: RunContext) -> str:
    """
    Base hybrid prompt, optionally enriched for photos jobs (image IDs in prompt text).

    Does not append product/label association blocks (regression guard vs main).
    """
    return build_hybrid_analysis_prompt_with_traceability(context)[0]


def resolve_analysis_context_for_run(context: RunContext) -> AnalysisContext | None:
    """Return typed AnalysisContext from RunContext or legacy JobInput.metadata."""
    analysis_context: AnalysisContext | None = getattr(context, "analysis_context", None)
    job_input = getattr(context, "job_input", None)
    if analysis_context is None and job_input and getattr(job_input, "metadata", None):
        analysis_context = analysis_context_from_dict(
            (job_input.metadata or {}).get("analysis_context")
        )
    return analysis_context
