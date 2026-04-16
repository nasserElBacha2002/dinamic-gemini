"""
Phase 3 — explicit pipeline provider resolution boundary.

Centralizes how a worker run chooses the logical LLM vendor (Gemini, OpenAI, Claude, DeepSeek)
and the corresponding :class:`~src.pipeline.ports.llm_execution.LlmGlobalAnalysisExecutor`.

**Execution contract:** vendor calls are made only through ``LlmGlobalAnalysisExecutor.execute``;
this module does not add a parallel giant protocol — see ``LlmGlobalAnalysisExecutor`` in
``src.pipeline.ports.llm_execution``.

``resolve_llm_executor_for_context`` is the canonical entrypoint (tests patch this symbol on this
module to inject offline executors).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.pipeline.ports.llm_execution import LlmGlobalAnalysisExecutor
from src.pipeline.providers.registry import resolve_llm_executor


@dataclass(frozen=True)
class ResolvedPipelineExecution:
    """Normalized outcome of provider + executor resolution for one hybrid run."""

    executor: LlmGlobalAnalysisExecutor
    normalized_provider_key: str


def resolve_llm_executor_for_context(
    pipeline_provider_name: Optional[str],
    settings: Any,
) -> tuple[LlmGlobalAnalysisExecutor, str]:
    """
    Resolve executor and normalized provider key for this run.

    Prefer explicit ``pipeline_provider_name`` (job / RunContext). Otherwise ``settings.llm_provider``.
    """
    key = normalize_pipeline_provider_key(pipeline_provider_name, settings)
    return resolve_llm_executor(key, settings), key


class PipelineProviderResolver:
    """Small façade over :func:`resolve_llm_executor_for_context` for typed call sites."""

    @staticmethod
    def resolve_for_run(
        *,
        pipeline_provider_name: Optional[str],
        settings: Any,
    ) -> ResolvedPipelineExecution:
        executor, key = resolve_llm_executor_for_context(pipeline_provider_name, settings)
        return ResolvedPipelineExecution(executor=executor, normalized_provider_key=key)

    @staticmethod
    def effective_provider_key(
        pipeline_provider_name: Optional[str],
        settings: Any,
    ) -> str:
        """Return the normalized logical provider key without constructing an executor."""
        return normalize_pipeline_provider_key(pipeline_provider_name, settings)
