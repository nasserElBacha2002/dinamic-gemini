"""
Analysis provider registry — resolves pipeline LLM execution by logical provider name (Phase 4).

``provider_name`` on jobs selects the executor; when absent, ``settings.llm_provider`` is used
(development / CLI). Unknown names fail loudly — no silent fallback to another vendor.
"""

from __future__ import annotations

from typing import Any, Optional

from src.llm.providers.base import LLMProvider
from src.llm.providers.fake_provider import FakeProvider
from src.llm.providers.openai_provider import OpenAIProvider
from src.llm.types import LLMRequest, LLMResponse
from src.llm.gemini_sdk_adapter import GeminiSdkAdapter
from src.pipeline.ports.analysis_provider import AnalysisProvider
from src.pipeline.ports.llm_execution import LlmGlobalAnalysisExecutor


class UnknownPipelineProviderError(LookupError):
    """Raised when ``provider_name`` does not map to a registered pipeline provider."""


class _LlmProviderDelegateExecutor:
    """Adapts existing ``LLMProvider`` instances to ``LlmGlobalAnalysisExecutor``."""

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner

    def execute(self, request: LLMRequest, settings: Any) -> LLMResponse:
        return self._inner.analyze_global(request)


_KNOWN_KEYS = frozenset({"gemini", "fake", "openai"})


def normalize_pipeline_provider_key(
    provider_name: Optional[str],
    settings: Any,
) -> str:
    """
    Effective provider key for this run.

    Prefer explicit ``provider_name`` (e.g. from inventory job). Otherwise use ``settings.llm_provider``.
    """
    raw = (provider_name or "").strip().lower()
    if raw:
        return raw
    sp = getattr(settings, "llm_provider", "gemini") or "gemini"
    return str(sp).strip().lower()


def resolve_llm_executor(provider_key: str, settings: Any) -> LlmGlobalAnalysisExecutor:
    """
    Return the SDK-level executor for ``provider_key``.

    Raises:
        UnknownPipelineProviderError: if ``provider_key`` is not registered.
    """
    key = (provider_key or "").strip().lower()
    if key == "gemini":
        return GeminiSdkAdapter()
    if key == "fake":
        return _LlmProviderDelegateExecutor(FakeProvider(settings))
    if key == "openai":
        return _LlmProviderDelegateExecutor(OpenAIProvider(settings))
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
    """Default AnalysisProvider for HybridInventoryPipeline when none is injected (current production: Gemini strategy)."""
    from src.pipeline.adapters.gemini_analysis_provider import GeminiAnalysisProvider

    return GeminiAnalysisProvider()
