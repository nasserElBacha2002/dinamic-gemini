"""
Phase 3 / 8 — explicit pipeline provider resolution boundary.

Centralizes how a worker run chooses the logical LLM vendor (Gemini, OpenAI, Claude, DeepSeek)
and the corresponding :class:`~src.pipeline.ports.llm_execution.LlmGlobalAnalysisExecutor`.

**Execution contract:** vendor calls are made only through ``LlmGlobalAnalysisExecutor.execute``;
this module does not add a parallel giant protocol — see ``LlmGlobalAnalysisExecutor`` in
``src.pipeline.ports.llm_execution``.

:func:`resolve_llm_executor_for_context` is the **only** implementation of job-level provider choice
+ executor resolution (tests patch this symbol on this module to inject offline executors).

Adapter registration (which class implements ``gemini`` / ``openai`` / …) remains in
:mod:`src.pipeline.providers.registry` — this module delegates to ``registry.resolve_llm_executor``
after normalizing the logical key.

**Typing note:** :func:`resolve_llm_executor_for_context` keeps ``settings: Any`` so tests and the
LLM harness can pass duck-typed objects. ``normalize_pipeline_provider_key`` reads only
``llm_provider``; each adapter’s ``execute`` may read a wider slice of real ``AppSettings`` fields
(pricing, API keys), so a narrow Protocol on this boundary would be misleading rather than helpful.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.pipeline.ports.llm_execution import LlmGlobalAnalysisExecutor
from src.pipeline.providers.registry import resolve_llm_executor


@dataclass(frozen=True)
class ResolvedPipelineExecution:
    """Bundle returned after resolving which ``LlmGlobalAnalysisExecutor`` runs this hybrid call."""

    executor: LlmGlobalAnalysisExecutor
    normalized_provider_key: str


def resolve_llm_executor_for_context(
    pipeline_provider_name: Optional[str],
    settings: Any,
) -> tuple[LlmGlobalAnalysisExecutor, str]:
    """
    Resolve executor and normalized provider key for this run.

    Prefer explicit ``pipeline_provider_name`` (job / RunContext). Otherwise ``settings.llm_provider``.

    ``settings`` is typically :class:`~src.config.Settings` (``AppSettings``); typed as ``Any`` because
    unit tests and the LLM harness pass duck-typed objects (e.g. ``MagicMock``) with the few fields read here.
    """
    key = normalize_pipeline_provider_key(pipeline_provider_name, settings)
    return resolve_llm_executor(key, settings), key


class PipelineProviderResolver:
    """Thin façade: typed entrypoints over :func:`resolve_llm_executor_for_context`.

    Not a second registry — no new provider keys or adapter wiring here. Callers that only need
    the logical key can use :meth:`effective_provider_key`; full runs use :meth:`resolve_for_run`.
    """

    @staticmethod
    def resolve_for_run(
        *,
        pipeline_provider_name: Optional[str],
        settings: Any,
    ) -> ResolvedPipelineExecution:
        """Resolve executor + key (see :func:`resolve_llm_executor_for_context` for ``settings`` typing note)."""
        executor, key = resolve_llm_executor_for_context(pipeline_provider_name, settings)
        return ResolvedPipelineExecution(executor=executor, normalized_provider_key=key)

    @staticmethod
    def effective_provider_key(
        pipeline_provider_name: Optional[str],
        settings: Any,
    ) -> str:
        """Return the normalized logical provider key without instantiating an executor."""
        return normalize_pipeline_provider_key(pipeline_provider_name, settings)
