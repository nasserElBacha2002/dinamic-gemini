"""
Provider-neutral hybrid global-analysis strategy implementing ``AnalysisProvider`` (Stage 2.3.B, Phase 4–6).

**Phase E1 / E4:** ``LLMRequest.prompt`` carries the **ProtectedSystemContractBlock** (hybrid base +
image enrichments + optional supplier-editable block from ``build_hybrid_analysis_prompt_with_traceability``
when v3 passes ``RunContext.supplier_prompt_resolution``). ``context_instruction`` remains
non-protected context (e.g. reference copy). OpenAI JSON suffix is still appended only in the adapter.

Builds the shared ``LLMRequest`` (prompt, context images, primary frames) and delegates the vendor
call to ``LlmGlobalAnalysisExecutor`` resolved by :mod:`src.pipeline.services.pipeline_provider_resolver`
(Gemini, OpenAI, Claude, DeepSeek).

Phase 4 adds optional multi-provider execution (parallel or sequential fallback) behind explicit
strategy settings or per-run ``RunContext`` fields; default ``single`` preserves the historical
one-call behavior.

Phase 6: visual-reference / instruction assembly for the LLM request is isolated in
:func:`_prepare_hybrid_llm_visual_bundle` so ``_analyze_once`` coordinates resolver + prompt + request
without owning the full visual-reference branching policy inline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

from src.llm.prompt_composer.prompt_traceability import (
    LLM_IDENTITY_METADATA_KEY,
    LLM_METADATA_KEY_PROMPT_COMPOSITION,
    LLM_METADATA_KEY_PROMPT_PARITY_MODE,
    apply_execution_layer_to_composition,
    prompt_composition_summary_for_execution_log,
    sha256_utf8,
)
from src.llm.types import ContextImageSequence, LLMRequest
from src.pipeline.context.run_context import RunContext
from src.pipeline.contracts.analysis_context import AnalysisContext
from src.pipeline.ports.analysis_provider import (
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED,
    AnalysisResult,
    ProviderCapabilities,
)
from src.pipeline.services.analysis_visual_reference_prep import (
    build_primary_evidence_attachments,
    prepare_visual_reference_inputs,
)
from src.pipeline.services.hybrid_analysis_prompt import (
    build_hybrid_analysis_prompt_with_traceability,
    resolve_analysis_context_for_run,
)
from src.pipeline.services.multi_provider_analysis_execution import (
    dispatch_multi_provider_analysis,
)
from src.pipeline.services.pipeline_provider_resolver import PipelineProviderResolver
from src.pipeline.services.provider_analysis_execution_config import (
    STRATEGY_SINGLE,
    build_ordered_provider_keys,
    effective_analysis_execution_strategy,
)
from src.pipeline.services.provider_analysis_result_normalization import (
    build_analysis_result_from_llm_response,
)
from src.pipeline.services.provider_llm_request_metadata import (
    apply_job_model_name_to_llm_request_metadata,
)

logger = logging.getLogger(__name__)


class _HybridLlmVisualBundle(NamedTuple):
    """Visual-reference inputs and instruction text assembled before ``LLMRequest`` construction."""

    context_instruction: str | None
    context_images: ContextImageSequence | None
    visual_reference_attachments: list[dict[str, Any]]
    resolved_reference_ids: list[str]
    consumed_count: int


def _prepare_hybrid_llm_visual_bundle(
    *,
    supports_visual_reference_context: bool,
    analysis_context: AnalysisContext | None,
    job_id: str,
) -> _HybridLlmVisualBundle:
    """
    Resolve optional context instruction and visual-reference attachments for one analysis call.

    Keeps the supports-visual-reference vs attachment-only-for-logging split in one place so
    :meth:`HybridGlobalAnalysisStrategy._analyze_once` stays a coordinator.
    """
    context_instruction: str | None = None
    context_images: ContextImageSequence | None = None
    visual_reference_attachments: list[dict[str, Any]] = []
    resolved_reference_ids: list[str] = []
    consumed_count = 0
    if analysis_context and analysis_context.instructions:
        context_instruction = "\n".join(analysis_context.instructions).strip() or None
    if (
        supports_visual_reference_context
        and analysis_context
        and analysis_context.visual_references
    ):
        loaded, visual_reference_attachments, resolved_reference_ids = (
            prepare_visual_reference_inputs(
                analysis_context,
                job_id=job_id,
            )
        )
        if loaded:
            context_images = loaded
            consumed_count = len(loaded)
    elif analysis_context and analysis_context.visual_references:
        _, visual_reference_attachments, _ = prepare_visual_reference_inputs(
            analysis_context,
            job_id=job_id,
        )
    return _HybridLlmVisualBundle(
        context_instruction=context_instruction,
        context_images=context_images,
        visual_reference_attachments=visual_reference_attachments,
        resolved_reference_ids=resolved_reference_ids,
        consumed_count=consumed_count,
    )


def _provider_metadata(
    visual_references_available: bool,
    visual_references_consumed: bool,
    visual_reference_count: int = 0,
    visual_reference_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE: visual_references_available,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: visual_references_consumed,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: visual_reference_count,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS: list(visual_reference_ids or []),
    }


class HybridGlobalAnalysisStrategy:
    """
    Default pipeline analysis strategy: assembles hybrid context and runs the resolved LLM executor.

    **Coordinator (Phase 6):** ``analyze`` chooses single vs multi-provider dispatch; ``_analyze_once``
    resolves the executor, composes prompt + ``LLMRequest``, emits structured logs, and maps the
    response to :class:`~src.pipeline.ports.analysis_provider.AnalysisResult`. Visual-reference
    branching lives in :func:`_prepare_hybrid_llm_visual_bundle`; multi-provider fan-out lives in
    :mod:`src.pipeline.services.multi_provider_analysis_execution`.

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
        frames_nd: list[np.ndarray],
        frame_paths: list[Path],
        frame_refs: list[str],
        metadata: dict[str, Any],
    ) -> AnalysisResult:
        """
        Run global analysis. Default ``single`` strategy uses one ``_analyze_once`` on ``context``.

        Multi-provider modes (non-single with 2+ keys) delegate to
        :func:`~src.pipeline.services.multi_provider_analysis_execution.dispatch_multi_provider_analysis`:
        parallel requires all branches to succeed; sequential is fallback (first success only).
        Primary selection for parallel is order-based (first key), not quality-ranked.
        """
        settings = context.settings
        strategy = effective_analysis_execution_strategy(context, settings)
        ordered_keys = build_ordered_provider_keys(context, settings)

        if strategy == STRATEGY_SINGLE or len(ordered_keys) <= 1:
            return self._analyze_once(context, frames_nd, frame_paths, frame_refs, metadata)

        run_logger = getattr(context, "logger", None)

        def analyze_once(rc: RunContext) -> AnalysisResult:
            return self._analyze_once(rc, frames_nd, frame_paths, frame_refs, metadata)

        return dispatch_multi_provider_analysis(
            strategy_name=strategy,
            base_context=context,
            ordered_provider_keys=ordered_keys,
            analyze_once=analyze_once,
            run_logger=run_logger,
        )

    def _analyze_once(
        self,
        run_ctx: RunContext,
        frames_nd: list[np.ndarray],
        frame_paths: list[Path],
        frame_refs: list[str],
        metadata: dict[str, Any],
    ) -> AnalysisResult:
        settings = run_ctx.settings
        job_id = run_ctx.job_id
        pipeline_provider_name: str | None = getattr(run_ctx, "pipeline_provider_name", None)
        resolved_exec = PipelineProviderResolver.resolve_for_run(
            pipeline_provider_name=pipeline_provider_name,
            settings=settings,
        )
        executor = resolved_exec.executor
        resolved_key = resolved_exec.normalized_provider_key

        prompt_text, composition_base = build_hybrid_analysis_prompt_with_traceability(run_ctx)

        analysis_context: AnalysisContext | None = resolve_analysis_context_for_run(run_ctx)
        visual_references_available = bool(analysis_context and analysis_context.visual_references)
        vb = _prepare_hybrid_llm_visual_bundle(
            supports_visual_reference_context=self.get_capabilities().supports_visual_reference_context,
            analysis_context=analysis_context,
            job_id=job_id,
        )
        context_instruction = vb.context_instruction
        context_images = vb.context_images
        visual_reference_attachments = vb.visual_reference_attachments
        resolved_reference_ids = vb.resolved_reference_ids
        consumed_count = vb.consumed_count

        req_meta: dict[str, Any] = {**metadata, "run_dir": str(run_ctx.run_dir)}
        jm = getattr(run_ctx, "job_model_name", None)
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
        req_meta[LLM_METADATA_KEY_PROMPT_PARITY_MODE] = bool(
            prompt_composition.get("prompt_parity_mode")
        )
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
        run_logger = getattr(run_ctx, "logger", None)
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
        exec_log = getattr(run_ctx, "execution_log", None)
        # Full prompt strings live on ``prompt_composition`` in request/job metadata (audit).
        # Execution log uses a redacted summary plus hash/len unless debug enables full ``prompt_text``.
        debug_full_prompt = getattr(settings, "debug_log_full_analysis_prompt", None) is True
        if exec_log:
            primary_attachments = build_primary_evidence_attachments(frame_paths, frame_refs)
            log_payload: dict[str, Any] = {
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
            consumed = (
                self.get_capabilities().supports_visual_reference_context and consumed_count > 0
            )
            return build_analysis_result_from_llm_response(
                response=response,
                prompt_composition=prompt_composition,
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
