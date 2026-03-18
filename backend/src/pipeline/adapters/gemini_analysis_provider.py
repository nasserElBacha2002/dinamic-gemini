"""
GeminiAnalysisProvider — adapter implementing AnalysisProvider (Stage 2.3.B).

In Stage B this adapter wraps the current global entity analysis flow only. It preserves the
existing prompt (GLOBAL_ENTITY_ANALYSIS_PROMPT_V21), schema (v2.1), and parse contract. It is
not yet a general-purpose Gemini abstraction; future stages may introduce a broader provider
or multiple analysis flows.
v3.2.4 Phase 4: consumes shared AnalysisContext; uses resolved_path only (no storage layout in provider).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from src.jobs.image_identity import load_job_images_from_manifest
from src.llm.prompts import enrich_prompt_with_image_ids, get_hybrid_prompt
from src.llm.providers.factory import get_llm_provider
from src.llm.types import ContextImageSequence
from src.llm.types import LLMRequest
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_from_dict
from src.pipeline.context.run_context import RunContext
from src.pipeline.ports.analysis_provider import (
    AnalysisResult,
    ProviderCapabilities,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED,
)

logger = logging.getLogger(__name__)


def _load_pil_from_path(path: Path) -> Any:  # PIL.Image.Image | None
    """Load image from path as PIL RGB; return None if missing or unreadable."""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow required for visual reference loading. Install with: pip install pillow")
    img = cv2.imread(str(path))
    if img is None:
        return None
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _provider_metadata(
    visual_references_available: bool,
    visual_references_consumed: bool,
    visual_reference_count: int = 0,
) -> Dict[str, Any]:
    return {
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE: visual_references_available,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: visual_references_consumed,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: visual_reference_count,
    }


class GeminiAnalysisProvider:
    """
    Implements AnalysisProvider by delegating to the current LLM provider (Gemini/Fake/OpenAI).

    Wraps the existing global entity analysis flow: same prompt, schema, and parse contract.
    Not a general-purpose Gemini adapter; scope is intentionally aligned with v2.1/v2.3 hybrid analysis.
    v3.2.4 Phase 4: supports_visual_reference_context=True by default; can be set False for tests.
    """

    def __init__(self, supports_visual_reference_context: bool = True) -> None:
        self._supports_visual_reference_context = supports_visual_reference_context

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_visual_reference_context=self._supports_visual_reference_context,
        )

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

        job_input = getattr(context, "job_input", None)
        # Epic 3.1.A: for photos jobs, enrich prompt with image IDs so provider can reference them
        if job_input and getattr(job_input, "input_type", "") == "photos":
            manifest_rel = (getattr(job_input, "input_manifest_path", None) or "").strip()
            photos_dir_rel = (getattr(job_input, "photos_dir", None) or "").strip()
            if manifest_rel and photos_dir_rel:
                job_dir = context.run_dir.parent
                manifest_path = job_dir / manifest_rel
                images = load_job_images_from_manifest(manifest_path, photos_dir_rel)
                if images:
                    prompt_text = enrich_prompt_with_image_ids(prompt_text, images)

        # v3.2.4 Phase 4: consume shared analysis context (no raw dict or storage layout here)
        analysis_context: Optional[AnalysisContext] = getattr(context, "analysis_context", None)
        if analysis_context is None and job_input and getattr(job_input, "metadata", None):
            # Compatibility fallback only: legacy callers may pass analysis_context via JobInput.metadata.
            analysis_context = analysis_context_from_dict((job_input.metadata or {}).get("analysis_context"))
        visual_references_available = bool(analysis_context and analysis_context.visual_references)
        context_instruction = None
        context_images: Optional[ContextImageSequence] = None
        consumed_count = 0
        if analysis_context and analysis_context.instructions:
            context_instruction = "\n".join(analysis_context.instructions).strip() or None
        if self.get_capabilities().supports_visual_reference_context and analysis_context and analysis_context.visual_references:
            loaded: List[Any] = []
            for ref in analysis_context.visual_references:
                if not ref.resolved_path or not ref.resolved_path.strip():
                    continue
                path = Path(ref.resolved_path)
                if not path.is_file():
                    logger.warning(
                        "Visual reference file not found, skipping: %s",
                        path,
                        extra={"job_id": job_id},
                    )
                    continue
                pil_img = _load_pil_from_path(path)
                if pil_img is not None:
                    loaded.append(pil_img)
            if loaded:
                context_images = loaded
                consumed_count = len(loaded)

        request = LLMRequest(
            job_id=job_id,
            frames=frame_paths,
            frame_refs=frame_refs,
            prompt=prompt_text,
            schema_version="v2.1",
            metadata={**metadata, "run_dir": str(context.run_dir)},
            frames_nd=frames_nd,
            context_instruction=context_instruction,
            context_images=context_images,
        )
        exec_log = getattr(context, "execution_log", None)
        if exec_log:
            exec_log.info("AnalysisStage", "Gemini analysis request started", payload={"frames_count": len(frames_nd)})
        try:
            response = provider.analyze_global(request)
            if exec_log:
                exec_log.info("AnalysisStage", "Gemini analysis request finished", payload={"provider": response.provider})
            consumed = self.get_capabilities().supports_visual_reference_context and consumed_count > 0
            return AnalysisResult(
                parsed_json=response.parsed_json,
                provider_name=response.provider,
                provider_metadata=_provider_metadata(
                    visual_references_available=visual_references_available,
                    visual_references_consumed=consumed,
                    visual_reference_count=consumed_count,
                ),
            )
        except Exception as e:
            if exec_log:
                exec_log.error("AnalysisStage", f"Gemini analysis request failed: {e}", payload={"error": str(e)[:500]})
            raise
