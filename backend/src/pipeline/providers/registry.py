"""
Analysis provider registry — resolves ``LlmGlobalAnalysisExecutor`` by logical provider name (Phase 4).

Resolution rules
----------------
* ``provider_name`` on the job (``RunContext.pipeline_provider_name``) wins when set.
* Otherwise ``settings.llm_provider`` is used (CLI / dev / legacy config).
* Unknown keys raise ``UnknownPipelineProviderError`` (no silent vendor fallback).

Transitional bridge (explicit)
------------------------------
``gemini`` maps to a **native** executor: ``GeminiSdkAdapter`` implements
``LlmGlobalAnalysisExecutor.execute`` directly (vendor SDK only inside ``src/llm/gemini_sdk_adapter.py``).

``fake`` and ``openai`` still wrap the historical ``LLMProvider.analyze_global`` protocol via
``TransitionalLlmProviderBridgeExecutor``. That keeps behavior identical with minimal code until
Phase 5+ adds dedicated ``FakeGlobalAnalysisExecutor`` / OpenAI executors. Generic pipeline code
must depend only on ``LlmGlobalAnalysisExecutor``, not on ``LLMProvider``.

Default analysis strategy
-------------------------
``default_analysis_provider()`` returns the historical hybrid analysis **strategy** class
(``GeminiAnalysisProvider``) when the orchestrator is constructed without injection. That is a
**runtime wiring default** for current production, not a claim that Gemini is the domain model.
"""

from __future__ import annotations

from typing import Any, Final, Optional

from src.llm.providers.base import LLMProvider
from src.llm.providers.fake_provider import FakeProvider
from src.llm.providers.openai_provider import OpenAIProvider
from src.llm.types import LLMRequest, LLMResponse
from src.llm.gemini_sdk_adapter import GeminiSdkAdapter
from src.pipeline.ports.analysis_provider import AnalysisProvider
from src.pipeline.ports.llm_execution import LlmGlobalAnalysisExecutor


class UnknownPipelineProviderError(LookupError):
    """Raised when ``provider_name`` does not map to a registered pipeline provider."""


class TransitionalLlmProviderBridgeExecutor:
    """
    Wraps a legacy ``LLMProvider`` as ``LlmGlobalAnalysisExecutor``.

    **Transitional:** ``fake`` and ``openai`` registry keys use this until each has a native
    executor. Do not add new providers here long-term — implement ``LlmGlobalAnalysisExecutor``
    directly instead.
    """

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner

    def execute(self, request: LLMRequest, settings: Any) -> LLMResponse:
        del settings  # legacy API ignores settings on call (configured at construction)
        return self._inner.analyze_global(request)


# Registry keys that use ``TransitionalLlmProviderBridgeExecutor`` (documented for Phase 4 closure).
TRANSITIONAL_LLM_PROVIDER_BRIDGE_KEYS: Final[frozenset[str]] = frozenset({"fake", "openai"})

_KNOWN_KEYS: Final[frozenset[str]] = frozenset({"gemini", "fake", "openai"})


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
    Return the executor for ``provider_key``.

    Raises:
        UnknownPipelineProviderError: if ``provider_key`` is not registered.
    """
    key = (provider_key or "").strip().lower()
    if key == "gemini":
        return GeminiSdkAdapter()
    if key == "fake":
        return TransitionalLlmProviderBridgeExecutor(FakeProvider(settings))
    if key == "openai":
        return TransitionalLlmProviderBridgeExecutor(OpenAIProvider(settings))
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

    Returns the existing hybrid global-analysis strategy (class name is historical). The strategy
    itself resolves the **executor** from ``RunContext.pipeline_provider_name`` + settings via the
    registry — it is not hard-wired to a single vendor at the executor layer.
    """
    from src.pipeline.adapters.gemini_analysis_provider import GeminiAnalysisProvider

    return GeminiAnalysisProvider()
