"""
Phase 3 / 8 — explicit pipeline provider resolution boundary.

Centralizes how a worker run chooses the logical LLM vendor (Gemini, OpenAI, Claude, DeepSeek)
and the corresponding :class:`~src.pipeline.ports.llm_execution.LlmGlobalAnalysisExecutor`.

**Phase 5 contract:** explicit ``job.provider_name`` is never silently remapped. Visual inventory
jobs are validated for vision + image-binding capabilities before executor selection.

**Runtime failover is not implemented** unless ``pipeline_analysis_execution_strategy`` enables
multi-provider fallback via settings — that is separate from per-job provider resolution here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.application.errors import ProcessingProviderIncompatibleWithJobError
from src.application.services.provider_contract_validation import (
    validate_provider_model_for_visual_inventory_job,
)
from src.llm.errors import LLMProviderError
from src.llm.provider_error_taxonomy import PROVIDER_INCOMPATIBLE_WITH_JOB
from src.pipeline.ports.llm_execution import LlmGlobalAnalysisExecutor
from src.pipeline.provider_keys import (
    InactivePipelineProviderKeyError,
    ResolvedPipelineProviderKey,
    UnknownPipelineProviderKeyError,
    resolve_pipeline_provider_key,
)
from src.pipeline.providers.capabilities import PROVIDER_CONTRACT_VERSION
from src.pipeline.providers.definitions import deprecated_processing_provider_message
from src.pipeline.providers.registry import resolve_llm_executor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedPipelineExecution:
    """Bundle returned after resolving which ``LlmGlobalAnalysisExecutor`` runs this hybrid call."""

    executor: LlmGlobalAnalysisExecutor
    normalized_provider_key: str
    requested_provider_key: str | None = None
    resolution_source: str = "settings_default"
    provider_contract_version: str = PROVIDER_CONTRACT_VERSION


def _contract_error_from_resolution(exc: BaseException, *, requested: str | None) -> LLMProviderError:
    key = (requested or "").strip().lower() or None
    if isinstance(exc, InactivePipelineProviderKeyError) and key:
        message = deprecated_processing_provider_message(key)
    else:
        message = str(exc)
    return LLMProviderError(
        code=PROVIDER_INCOMPATIBLE_WITH_JOB,
        message=message,
        details={
            "provider": key,
            "requested_provider_key": key,
            "phase": "provider_resolution",
        },
    )


def resolve_pipeline_provider_for_execution(
    pipeline_provider_name: str | None,
    settings: Any,
    *,
    validate_visual_inventory: bool = True,
    model_name: str | None = None,
) -> ResolvedPipelineProviderKey:
    """
    Resolve provider key for worker execution (fail-closed on explicit inactive/unknown).

    When ``validate_visual_inventory`` is true (default), incompatible providers raise
    :class:`~src.llm.errors.LLMProviderError` with canonical ``PROVIDER_INCOMPATIBLE_WITH_JOB``.
    """
    try:
        resolved = resolve_pipeline_provider_key(pipeline_provider_name, settings)
    except (UnknownPipelineProviderKeyError, InactivePipelineProviderKeyError) as exc:
        raise _contract_error_from_resolution(exc, requested=pipeline_provider_name) from exc

    if resolved.remapped:
        raise LLMProviderError(
            code=PROVIDER_INCOMPATIBLE_WITH_JOB,
            message=(
                f"Explicit provider {resolved.requested_key!r} cannot be remapped to "
                f"{resolved.resolved_key!r} for job execution."
            ),
            details={
                "requested_provider_key": resolved.requested_key,
                "resolved_provider_key": resolved.resolved_key,
                "phase": "provider_resolution",
            },
        )

    if validate_visual_inventory:
        try:
            validate_provider_model_for_visual_inventory_job(
                resolved.resolved_key,
                model_name,
            )
        except ProcessingProviderIncompatibleWithJobError as exc:
            raise LLMProviderError(
                code=PROVIDER_INCOMPATIBLE_WITH_JOB,
                message=str(exc),
                details={
                    "provider": resolved.resolved_key,
                    "requested_provider_key": resolved.requested_key,
                    "model_name": (model_name or "").strip() or None,
                    "phase": "provider_capability_validation",
                },
            ) from exc

    if resolved.requested_key and resolved.requested_key != resolved.resolved_key:
        logger.warning(
            "provider_key_mismatch requested=%s resolved=%s",
            resolved.requested_key,
            resolved.resolved_key,
        )

    return resolved


def resolve_llm_executor_for_context(
    pipeline_provider_name: str | None,
    settings: Any,
    *,
    model_name: str | None = None,
) -> tuple[LlmGlobalAnalysisExecutor, str]:
    """
    Resolve executor and normalized provider key for this run.

    Prefer explicit ``pipeline_provider_name`` (job / RunContext). Otherwise ``settings.llm_provider``.
    """
    resolved = resolve_pipeline_provider_for_execution(
        pipeline_provider_name,
        settings,
        model_name=model_name,
    )
    return resolve_llm_executor(resolved.resolved_key, settings), resolved.resolved_key


class PipelineProviderResolver:
    """Thin façade: typed entrypoints over provider resolution + registry."""

    @staticmethod
    def resolve_for_run(
        *,
        pipeline_provider_name: str | None,
        settings: Any,
        job_model_name: str | None = None,
    ) -> ResolvedPipelineExecution:
        executor, key = resolve_llm_executor_for_context(
            pipeline_provider_name,
            settings,
            model_name=job_model_name,
        )
        meta = resolve_pipeline_provider_for_execution(
            pipeline_provider_name,
            settings,
            model_name=job_model_name,
            validate_visual_inventory=False,
        )
        requested = (pipeline_provider_name or "").strip().lower() or None
        return ResolvedPipelineExecution(
            executor=executor,
            normalized_provider_key=key,
            requested_provider_key=requested,
            resolution_source=meta.resolution_source,
        )

    @staticmethod
    def effective_provider_key(
        pipeline_provider_name: str | None,
        settings: Any,
    ) -> str:
        """Return normalized key without visual-capability preflight (multi-provider ordering only)."""
        return resolve_pipeline_provider_for_execution(
            pipeline_provider_name,
            settings,
            validate_visual_inventory=False,
        ).resolved_key
