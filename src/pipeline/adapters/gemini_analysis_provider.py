"""
GeminiAnalysisProvider — adapter implementing AnalysisProvider (Stage 2.3.B).

In Stage B this adapter wraps the current global entity analysis flow only. It preserves the
existing prompt (GLOBAL_ENTITY_ANALYSIS_PROMPT_V21), schema (v2.1), and parse contract. It is
not yet a general-purpose Gemini abstraction; future stages may introduce a broader provider
or multiple analysis flows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from src.jobs.image_identity import load_job_images_from_manifest
from src.llm.prompts import enrich_prompt_with_image_ids, get_hybrid_prompt
from src.llm.providers.factory import get_llm_provider
from src.llm.types import LLMRequest
from src.pipeline.context.run_context import RunContext
from src.pipeline.ports.analysis_provider import AnalysisResult


class GeminiAnalysisProvider:
    """
    Implements AnalysisProvider by delegating to the current LLM provider (Gemini/Fake/OpenAI).

    Wraps the existing global entity analysis flow: same prompt, schema, and parse contract.
    Not a general-purpose Gemini adapter; scope is intentionally aligned with v2.1/v2.3 hybrid analysis.
    """

    def analyze(
        self,
        context: RunContext,
        frames_nd: List[np.ndarray],
        frame_paths: List[Path],
        frame_refs: List[str],
        metadata: Dict[str, Any],
    ) -> AnalysisResult:
        """Build LLMRequest, call get_llm_provider(settings).analyze_global, return AnalysisResult."""
        settings = context.settings
        job_id = context.job_id
        provider = get_llm_provider(settings)
        prompt_text = get_hybrid_prompt(getattr(settings, "hybrid_prompt", "global_v21"))
        # Do not append product/label association here: it caused Gemini to return null for
        # internal_code and product_label_quantity (regression vs main). Use base prompt only.

        # Epic 3.1.A: for photos jobs, enrich prompt with image IDs so provider can reference them
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

        request = LLMRequest(
            job_id=job_id,
            frames=frame_paths,
            frame_refs=frame_refs,
            prompt=prompt_text,
            schema_version="v2.1",
            metadata={**metadata, "run_dir": str(context.run_dir)},
            frames_nd=frames_nd,
        )
        exec_log = getattr(context, "execution_log", None)
        if exec_log:
            exec_log.info("AnalysisStage", "Gemini analysis request started", payload={"frames_count": len(frames_nd)})
        try:
            response = provider.analyze_global(request)
            if exec_log:
                exec_log.info("AnalysisStage", "Gemini analysis request finished", payload={"provider": response.provider})
            return AnalysisResult(
                parsed_json=response.parsed_json,
                provider_name=response.provider,
            )
        except Exception as e:
            if exec_log:
                exec_log.error("AnalysisStage", f"Gemini analysis request failed: {e}", payload={"error": str(e)[:500]})
            raise
