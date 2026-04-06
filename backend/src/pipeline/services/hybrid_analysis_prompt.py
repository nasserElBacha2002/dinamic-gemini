"""
Hybrid global-analysis prompt assembly (provider-neutral).

Builds the v2.1 text passed on ``LLMRequest.prompt`` — same semantics as pre–Phase 4 pipeline.
"""

from __future__ import annotations

from typing import Optional

from src.jobs.image_identity import load_job_images_from_manifest
from src.llm.prompts import enrich_prompt_with_image_ids, get_hybrid_prompt
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_from_dict
from src.pipeline.context.run_context import RunContext


def build_hybrid_analysis_prompt_text(context: RunContext) -> str:
    """
    Base hybrid prompt, optionally enriched for photos jobs (image IDs in prompt text).

    Does not append product/label association blocks (regression guard vs main).
    """
    settings = context.settings
    prompt_text = get_hybrid_prompt(getattr(settings, "hybrid_prompt", "global_v21"))
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
