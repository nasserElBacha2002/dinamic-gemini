"""
Provider-neutral hybrid global-analysis strategy implementing ``AnalysisProvider`` (Stage 2.3.B, Phase 4–5).

Builds the shared ``LLMRequest`` (prompt, context images, primary frames) and delegates the vendor
call to ``LlmGlobalAnalysisExecutor`` resolved by :mod:`src.pipeline.services.pipeline_provider_resolver`
(Gemini, OpenAI, Claude, DeepSeek).
"""

from __future__ import annotations

import logging
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
from src.pipeline.services.pipeline_provider_resolver import PipelineProviderResolver
from src.pipeline.services.provider_analysis_result_normalization import (
    build_analysis_result_from_llm_response,
)
from src.pipeline.services.provider_llm_request_metadata import (
    apply_job_model_name_to_llm_request_metadata,
)
from src.pipeline.services.analysis_visual_reference_prep import (
    build_primary_evidence_attachments,
    prepare_visual_reference_inputs,
)
from src.llm.prompt_composer.prompt_traceability import (
    LLM_IDENTITY_METADATA_KEY,
    LLM_METADATA_KEY_PROMPT_COMPOSITION,
    LLM_METADATA_KEY_PROMPT_PARITY_MODE,
    apply_execution_layer_to_composition,
    prompt_composition_summary_for_execution_log,
    sha256_utf8,
)
from src.pipeline.services.hybrid_analysis_prompt import (
    build_hybrid_analysis_prompt_with_traceability,
    resolve_analysis_context_for_run,
)

logger = logging.getLogger(__name__)


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


class HybridGlobalAnalysisStrategy:
    """
    Default pipeline analysis strategy: assembles hybrid context and runs the resolved LLM executor.

    Executor choice comes from ``RunContext.pipeline_provider_name`` and settings (see registry);
    this class is not tied to a single vendor.
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
        resolved_exec = PipelineProviderResolver.resolve_for_run(
            pipeline_provider_name=pipeline_provider_name,
            settings=settings,
        )
        executor = resolved_exec.executor
        resolved_key = resolved_exec.normalized_provider_key

        prompt_text, composition_base = build_hybrid_analysis_prompt_with_traceability(context)

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

        req_meta: Dict[str, Any] = {**metadata, "run_dir": str(context.run_dir)}
        jm = getattr(context, "job_model_name", None)
        rk = (resolved_key or "").strip().lower()
        model_for_meta = apply_job_model_name_to_llm_request_metadata(
            resolved_provider_key=rk,
            job_model_name=jm,
            metadata=req_meta,
        )

        # Phase 6: linear propagation — one dict after execution-layer merge is the source of truth
        # for LLMRequest, AnalysisResult, run_metadata, and (redacted) execution_log summary.
        prompt_composition = apply_execution_layer_to_composition(
            composition_base,
            resolved_llm_provider_key=rk,
            model_name=model_for_meta,
        )
        if prompt_composition.get("final_prompt_text") != prompt_text:
            logger.warning(
                "prompt_composition final_prompt_text mismatch vs assembled prompt (job_id=%s)",
                job_id,
            )
        req_meta[LLM_METADATA_KEY_PROMPT_COMPOSITION] = prompt_composition
        req_meta[LLM_METADATA_KEY_PROMPT_PARITY_MODE] = bool(prompt_composition.get("prompt_parity_mode"))
        _lid = prompt_composition.get("llm_identity")
        if isinstance(_lid, dict):
            req_meta[LLM_IDENTITY_METADATA_KEY] = dict(_lid)

        request = LLMRequest(
            job_id=job_id,
            frames=frame_paths,
            frame_refs=frame_refs,
            prompt=prompt_text,
            schema_version="v2.1",
            metadata=req_meta,
            frames_nd=frames_nd,
            context_instruction=context_instruction,
            context_images=context_images,
        )
        run_logger = getattr(context, "logger", None)
        if run_logger is not None:
            pv_raw = prompt_composition.get("prompt_version")
            pv_opt = pv_raw.strip() if isinstance(pv_raw, str) and pv_raw.strip() else None
            log_parts = [
                prompt_composition.get("profile_name"),
                prompt_composition.get("pipeline_provider_key"),
                prompt_composition.get("resolved_llm_provider_key"),
                prompt_composition.get("model_name"),
                prompt_composition.get("prompt_hash"),
                prompt_composition.get("enrichments_applied"),
            ]
            fmt = (
                "Prompt composition: profile=%s pipeline_provider=%s llm_provider=%s "
                "model=%s prompt_hash=%s enrichments=%s"
            )
            if pv_opt:
                fmt += " prompt_version=%s"
                log_parts.append(pv_opt)
            run_logger.info(fmt, *log_parts)
        exec_log = getattr(context, "execution_log", None)
        # Full prompt strings live on ``prompt_composition`` in request/job metadata (audit).
        # Execution log uses a redacted summary plus hash/len unless debug enables full ``prompt_text``.
        debug_full_prompt = getattr(settings, "debug_log_full_analysis_prompt", None) is True
        if exec_log:
            primary_attachments = build_primary_evidence_attachments(frame_paths, frame_refs)
            log_payload: Dict[str, Any] = {
                "event_type": "analysis_request",
                "pipeline_provider": resolved_key,
                "context_instruction": context_instruction,
                "attachment_summary": {
                    "primary_evidence_count": len(primary_attachments),
                    "visual_reference_count": consumed_count,
                    "total_count": len(primary_attachments) + consumed_count,
                },
                "primary_evidence_attachments": primary_attachments,
                "visual_reference_attachments": visual_reference_attachments,
                "prompt_composition": prompt_composition_summary_for_execution_log(
                    prompt_composition,
                    final_prompt_char_len=len(prompt_text),
                ),
            }
            if debug_full_prompt:
                log_payload["prompt_text"] = prompt_text
            else:
                log_payload["prompt_text_sha256"] = sha256_utf8(prompt_text)
                log_payload["prompt_text_len"] = len(prompt_text)
            exec_log.info(
                "AnalysisStage",
                "Analysis request prepared",
                payload=log_payload,
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
            return build_analysis_result_from_llm_response(
                response=response,
                prompt_composition=prompt_composition,
                visual_references_available=visual_references_available,
                visual_references_consumed=consumed,
                visual_reference_count=consumed_count,
                visual_reference_ids=resolved_reference_ids,
                provider_metadata=_provider_metadata(
                    visual_references_available=visual_references_available,
                    visual_references_consumed=consumed,
                    visual_reference_count=consumed_count,
                    visual_reference_ids=resolved_reference_ids,
                ),
                settings=settings,
            )
        except Exception as e:
            if exec_log:
                exec_log.error(
                    "AnalysisStage",
                    f"Analysis request failed: {e}",
                    payload={"error": str(e)[:500]},
                )
            raise
