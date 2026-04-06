"""
Gemini-oriented analysis strategy implementing ``AnalysisProvider`` (Stage 2.3.B, Phase 4).

Orchestrates provider-neutral prompt/context assembly and delegates the external call to an
``LlmGlobalAnalysisExecutor`` resolved via ``providers.registry`` (not hard-coded Gemini types).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from src.llm.types import ContextImageSequence, LLMRequest
from src.pipeline.contracts.analysis_context import AnalysisContext
from src.pipeline.context.run_context import RunContext
from src.pipeline.ports.analysis_provider import (
    AnalysisResult,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED,
    ProviderCapabilities,
)
from src.pipeline.providers.registry import resolve_llm_executor_for_context
from src.pipeline.services.analysis_visual_reference_prep import (
    build_primary_evidence_attachments,
    prepare_visual_reference_inputs,
)
from src.pipeline.services.hybrid_analysis_prompt import (
    build_hybrid_analysis_prompt_text,
    resolve_analysis_context_for_run,
)


def _provider_metadata(
    visual_references_available: bool,
    visual_references_consumed: bool,
    visual_reference_count: int = 0,
    visual_reference_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE: visual_references_available,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: visual_references_consumed,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: visual_reference_count,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS: list(visual_reference_ids or []),
    }


class GeminiAnalysisProvider:
    """
    Pipeline analysis strategy: builds ``LLMRequest`` and runs the resolved executor.

    Name is historical (Gemini-first product); behavior is driven by ``provider_name`` on the
    run context and ``settings`` (see registry).
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
        settings = context.settings
        job_id = context.job_id
        pipeline_provider_name: Optional[str] = getattr(context, "pipeline_provider_name", None)
        executor, resolved_key = resolve_llm_executor_for_context(pipeline_provider_name, settings)

        prompt_text = build_hybrid_analysis_prompt_text(context)

        analysis_context: Optional[AnalysisContext] = resolve_analysis_context_for_run(context)
        visual_references_available = bool(analysis_context and analysis_context.visual_references)
        context_instruction = None
        context_images: Optional[ContextImageSequence] = None
        visual_reference_attachments: List[Dict[str, Any]] = []
        resolved_reference_ids: List[str] = []
        consumed_count = 0
        if analysis_context and analysis_context.instructions:
            context_instruction = "\n".join(analysis_context.instructions).strip() or None
        if self.get_capabilities().supports_visual_reference_context and analysis_context and analysis_context.visual_references:
            loaded, visual_reference_attachments, resolved_reference_ids = prepare_visual_reference_inputs(
                analysis_context,
                job_id=job_id,
            )
            if loaded:
                context_images = loaded
                consumed_count = len(loaded)
        elif analysis_context and analysis_context.visual_references:
            _, visual_reference_attachments, _ = prepare_visual_reference_inputs(
                analysis_context,
                job_id=job_id,
            )

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
            primary_attachments = build_primary_evidence_attachments(frame_paths, frame_refs)
            exec_log.info(
                "AnalysisStage",
                "Analysis request prepared",
                payload={
                    "event_type": "analysis_request",
                    "pipeline_provider": resolved_key,
                    "prompt_text": prompt_text,
                    "context_instruction": context_instruction,
                    "attachment_summary": {
                        "primary_evidence_count": len(primary_attachments),
                        "visual_reference_count": consumed_count,
                        "total_count": len(primary_attachments) + consumed_count,
                    },
                    "primary_evidence_attachments": primary_attachments,
                    "visual_reference_attachments": visual_reference_attachments,
                },
            )
            exec_log.info(
                "AnalysisStage",
                "Analysis request started",
                payload={"frames_count": len(frames_nd)},
            )
        try:
            response = executor.execute(request, settings)
            if exec_log:
                exec_log.info(
                    "AnalysisStage",
                    "Analysis request finished",
                    payload={"provider": response.provider},
                )
            consumed = self.get_capabilities().supports_visual_reference_context and consumed_count > 0
            return AnalysisResult(
                parsed_json=response.parsed_json,
                provider_name=response.provider,
                provider_metadata=_provider_metadata(
                    visual_references_available=visual_references_available,
                    visual_references_consumed=consumed,
                    visual_reference_count=consumed_count,
                    visual_reference_ids=resolved_reference_ids,
                ),
            )
        except Exception as e:
            if exec_log:
                exec_log.error(
                    "AnalysisStage",
                    f"Analysis request failed: {e}",
                    payload={"error": str(e)[:500]},
                )
            raise
