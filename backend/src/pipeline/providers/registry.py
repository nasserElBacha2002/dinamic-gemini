"""
Analysis provider registry — resolves ``LlmGlobalAnalysisExecutor`` by logical provider name.

**Canonical job-level resolution** (job provider + settings → executor + key) lives in
:mod:`src.pipeline.services.pipeline_provider_resolver` — import
:func:`~src.pipeline.services.pipeline_provider_resolver.resolve_llm_executor_for_context` or
:class:`~src.pipeline.services.pipeline_provider_resolver.PipelineProviderResolver` from there.

This module owns **adapter registration** only: ``resolve_llm_executor(provider_key, settings)``
returns the vendor adapter implementing :class:`~src.pipeline.ports.llm_execution.LlmGlobalAnalysisExecutor`.

Resolution rules (for ``resolve_llm_executor``)
-----------------------------------------------
* Unknown keys raise ``UnknownPipelineProviderError`` (no silent vendor fallback).

Registered providers
--------------------
* ``gemini`` → ``GeminiSdkAdapter`` (native executor; vendor SDK inside adapter).
* ``openai`` → ``OpenAiSdkAdapter`` (native executor).
* ``claude`` → ``AnthropicSdkAdapter`` (Anthropic Messages API + vision).
* ``deepseek`` → ``DeepSeekSdkAdapter`` (OpenAI-compatible Chat Completions; multimodal image jobs blocked; Phase 9).

Generic pipeline code must depend only on ``LlmGlobalAnalysisExecutor``, not on legacy ``LLMProvider``.

Default analysis strategy
-------------------------
``default_analysis_provider()`` returns ``HybridGlobalAnalysisStrategy`` when the orchestrator is
constructed without injection. The LLM vendor is chosen at execute time via the resolver + registry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from src.pipeline.ports.analysis_provider import AnalysisProvider
from src.pipeline.ports.llm_execution import LlmGlobalAnalysisExecutor
from src.pipeline.providers.definitions import registered_pipeline_provider_keys_from_definitions


class UnknownPipelineProviderError(LookupError):
    """Raised when ``provider_name`` does not map to a registered pipeline provider."""


_KNOWN_KEYS: Final[frozenset[str]] = registered_pipeline_provider_keys_from_definitions()


def _build_gemini_executor() -> LlmGlobalAnalysisExecutor:
    from src.llm.gemini_sdk_adapter import GeminiSdkAdapter

    return GeminiSdkAdapter()


def _build_openai_executor() -> LlmGlobalAnalysisExecutor:
    from src.llm.openai_sdk_adapter import OpenAiSdkAdapter

    return OpenAiSdkAdapter()


def _build_claude_executor() -> LlmGlobalAnalysisExecutor:
    from src.llm.anthropic_sdk_adapter import AnthropicSdkAdapter

    return AnthropicSdkAdapter()


def _build_deepseek_executor() -> LlmGlobalAnalysisExecutor:
    from src.llm.deepseek_sdk_adapter import DeepSeekSdkAdapter

    return DeepSeekSdkAdapter()


_EXECUTOR_BUILDERS: Final[
    dict[str, Callable[[], LlmGlobalAnalysisExecutor]]
] = {
    "gemini": _build_gemini_executor,
    "openai": _build_openai_executor,
    "claude": _build_claude_executor,
    "deepseek": _build_deepseek_executor,
}


def registered_pipeline_provider_keys() -> frozenset[str]:
    """Keys accepted for explicit processing provider selection (API / UI)."""
    return _KNOWN_KEYS


def resolve_llm_executor(provider_key: str, settings: Any) -> LlmGlobalAnalysisExecutor:
    """
    Return the executor for ``provider_key``.

    ``settings`` is unused here; native adapters read credentials in ``execute(request, settings)``.

    Raises:
        UnknownPipelineProviderError: if ``provider_key`` is not registered.
    """
    _ = settings
    key = (provider_key or "").strip().lower()
    builder = _EXECUTOR_BUILDERS.get(key)
    if builder is None:
        raise UnknownPipelineProviderError(
            f"Unknown pipeline provider {provider_key!r}. Known: {sorted(_KNOWN_KEYS)}"
        )
    return builder()


def default_analysis_provider() -> AnalysisProvider:
    """
    Runtime default when ``HybridInventoryPipeline`` is built without an injected ``AnalysisProvider``.

    Returns ``HybridGlobalAnalysisStrategy``, which resolves the **executor** from
    ``RunContext.pipeline_provider_name`` + settings via
    :mod:`src.pipeline.services.pipeline_provider_resolver` (Gemini, OpenAI, Claude, DeepSeek).
    """
    from src.pipeline.adapters.hybrid_global_analysis_strategy import HybridGlobalAnalysisStrategy

    return HybridGlobalAnalysisStrategy()
