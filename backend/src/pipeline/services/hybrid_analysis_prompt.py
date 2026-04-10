"""
Hybrid global-analysis prompt assembly (provider-neutral).

Uses ``prompt_composer.hybrid_assembly`` for profile + base composition; applies photo enrichments
once here (step 4 of the Phase 5 flow).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from src.jobs.image_identity import load_job_images_from_manifest
from src.llm.prompt_composer.enrichments import (
    IMAGE_ID_TRACEABILITY_ENRICHMENT_ID,
    enrich_prompt_with_image_ids,
)
from src.llm.prompt_composer.hybrid_assembly import (
    compose_hybrid_base,
    resolve_hybrid_profile_name,
)
from src.llm.prompt_composer.prompt_traceability import build_prompt_composition_dict
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_from_dict
from src.pipeline.context.run_context import RunContext
from src.pipeline.provider_keys import normalize_pipeline_provider_key


def build_hybrid_analysis_prompt_with_traceability(context: RunContext) -> Tuple[str, Dict[str, Any]]:
    """
    Same prompt text as legacy assembly, plus JSON-serializable composition metadata (Phase 6).

    Prompt construction order is unchanged: profile → provider → base → optional image-id enrichment.
    """
    settings = context.settings
    steps: list[Dict[str, Any]] = []
    profile = resolve_hybrid_profile_name(
        job_prompt_key=getattr(context, "job_prompt_key", None),
        settings=settings,
    )
    steps.append({"step": "resolve_profile", "profile_name": profile})
    effective_provider = normalize_pipeline_provider_key(
        getattr(context, "pipeline_provider_name", None),
        settings,
    )
    steps.append({"step": "normalize_pipeline_provider", "pipeline_provider_key": effective_provider})
    base_prompt = compose_hybrid_base(profile, effective_provider)
    steps.append({"step": "compose_hybrid_base"})
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
                        "step": "enrich_image_ids",
                        "enrichment_id": IMAGE_ID_TRACEABILITY_ENRICHMENT_ID,
                        "image_count": len(images),
                    }
                )
    jpk = getattr(context, "job_prompt_key", None)
    job_prompt_key_opt = jpk.strip() if isinstance(jpk, str) and jpk.strip() else None
    shp = getattr(settings, "hybrid_prompt", None)
    settings_prompt_opt = shp.strip() if isinstance(shp, str) and shp.strip() else None
    composition = build_prompt_composition_dict(
        profile_name=profile,
        pipeline_provider_key=effective_provider,
        base_prompt_text=base_prompt,
        final_prompt_text=prompt_text,
        enrichments_applied=enrichments_applied,
        composition_steps=steps,
        job_prompt_key=job_prompt_key_opt,
        settings_hybrid_prompt_key=settings_prompt_opt,
    )
    return prompt_text, composition


def build_hybrid_analysis_prompt_text(context: RunContext) -> str:
    """
    Base hybrid prompt, optionally enriched for photos jobs (image IDs in prompt text).

    Does not append product/label association blocks (regression guard vs main).
    """
    return build_hybrid_analysis_prompt_with_traceability(context)[0]


def resolve_analysis_context_for_run(context: RunContext) -> Optional[AnalysisContext]:
    """Return typed AnalysisContext from RunContext or legacy JobInput.metadata."""
    analysis_context: Optional[AnalysisContext] = getattr(context, "analysis_context", None)
    job_input = getattr(context, "job_input", None)
    if analysis_context is None and job_input and getattr(job_input, "metadata", None):
        analysis_context = analysis_context_from_dict((job_input.metadata or {}).get("analysis_context"))
    return analysis_context
