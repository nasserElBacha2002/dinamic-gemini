"""
Analysis provider registry — resolves ``LlmGlobalAnalysisExecutor`` by logical provider name (Phase 4).

Resolution rules
----------------
* ``provider_name`` on the job (``RunContext.pipeline_provider_name``) wins when set.
* Otherwise ``settings.llm_provider`` is used (CLI / dev / legacy config).
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
constructed without injection. The LLM vendor is chosen at execute time via the registry.
"""

from __future__ import annotations

from typing import Any, Final, Optional

from src.pipeline.ports.analysis_provider import AnalysisProvider
from src.pipeline.ports.llm_execution import LlmGlobalAnalysisExecutor
from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.pipeline.providers.definitions import registered_pipeline_provider_keys_from_definitions


class UnknownPipelineProviderError(LookupError):
    """Raised when ``provider_name`` does not map to a registered pipeline provider."""


_KNOWN_KEYS: Final[frozenset[str]] = registered_pipeline_provider_keys_from_definitions()


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
    if key == "gemini":
        from src.llm.gemini_sdk_adapter import GeminiSdkAdapter

        return GeminiSdkAdapter()
    if key == "openai":
        from src.llm.openai_sdk_adapter import OpenAiSdkAdapter

        return OpenAiSdkAdapter()
    if key == "claude":
        from src.llm.anthropic_sdk_adapter import AnthropicSdkAdapter

        return AnthropicSdkAdapter()
    if key == "deepseek":
        from src.llm.deepseek_sdk_adapter import DeepSeekSdkAdapter

        return DeepSeekSdkAdapter()
    raise UnknownPipelineProviderError(
        f"Unknown pipeline provider {provider_key!r}. Known: {sorted(_KNOWN_KEYS)}"
    )


def resolve_llm_executor_for_context(
    pipeline_provider_name: Optional[str],
    settings: Any,
) -> tuple[LlmGlobalAnalysisExecutor, str]:
    """Resolve executor and the normalized key (for logging)."""
    key = normalize_pipeline_provider_key(pipeline_provider_name, settings)
    return resolve_llm_executor(key, settings), key


def default_analysis_provider() -> AnalysisProvider:
    """
    Runtime default when ``HybridInventoryPipeline`` is built without an injected ``AnalysisProvider``.

    Returns ``HybridGlobalAnalysisStrategy``, which resolves the **executor** from
    ``RunContext.pipeline_provider_name`` + settings via the registry (Gemini, OpenAI, Claude, DeepSeek).
    """
    from src.pipeline.adapters.hybrid_global_analysis_strategy import HybridGlobalAnalysisStrategy

    return HybridGlobalAnalysisStrategy()
