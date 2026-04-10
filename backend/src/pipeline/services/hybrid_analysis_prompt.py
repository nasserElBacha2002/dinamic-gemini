"""
Hybrid global-analysis prompt assembly (provider-neutral).

Uses ``HybridPromptComposer`` for base text and ``enrichments`` for photos traceability — Phase 4
single source of truth (parity with legacy ``get_hybrid_prompt`` + image-id appender).
"""

from __future__ import annotations

from typing import Optional

from src.jobs.image_identity import load_job_images_from_manifest
from src.llm.prompt_composer.composer import default_hybrid_composer
from src.llm.prompt_composer.enrichments import enrich_prompt_with_image_ids
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_from_dict
from src.pipeline.context.run_context import RunContext
from src.pipeline.provider_keys import normalize_pipeline_provider_key


def build_hybrid_analysis_prompt_text(context: RunContext) -> str:
    """
    Base hybrid prompt, optionally enriched for photos jobs (image IDs in prompt text).

    Does not append product/label association blocks (regression guard vs main).
    """
    settings = context.settings
    job_pk = getattr(context, "job_prompt_key", None)
    profile = (
        str(job_pk).strip()
        if job_pk and str(job_pk).strip()
        else str(getattr(settings, "hybrid_prompt", "global_v21") or "global_v21").strip()
    )
    effective_provider = normalize_pipeline_provider_key(
        getattr(context, "pipeline_provider_name", None),
        settings,
    )
    prompt_text = default_hybrid_composer.compose_base(profile, effective_provider)
    job_input = getattr(context, "job_input", None)
    if job_input and getattr(job_input, "input_type", "") == "photos":
        manifest_rel = (getattr(job_input, "input_manifest_path", None) or "").strip()
        photos_dir_rel = (getattr(job_input, "photos_dir", None) or "").strip()
        if manifest_rel and photos_dir_rel:
            job_dir = context.run_dir.parent
            manifest_path = job_dir / manifest_rel
            images = load_job_images_from_manifest(manifest_path, photos_dir_rel)
            if images:
                prompt_text = enrich_prompt_with_image_ids(prompt_text, images)
    return prompt_text


def resolve_analysis_context_for_run(context: RunContext) -> Optional[AnalysisContext]:
    """Return typed AnalysisContext from RunContext or legacy JobInput.metadata."""
    analysis_context: Optional[AnalysisContext] = getattr(context, "analysis_context", None)
    job_input = getattr(context, "job_input", None)
    if analysis_context is None and job_input and getattr(job_input, "metadata", None):
        analysis_context = analysis_context_from_dict((job_input.metadata or {}).get("analysis_context"))
    return analysis_context
