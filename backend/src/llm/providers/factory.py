"""Stage 2.2.D — legacy ``LLMProvider`` factory (Gemini/OpenAI only).

Production hybrid analysis uses ``src.pipeline.providers.registry.resolve_llm_executor`` and
``LlmGlobalAnalysisExecutor`` — not this module. ``get_llm_provider`` remains for older call sites
and must **fail fast** for registry-only providers (``claude``, ``deepseek``) so they never
silently fall through to Gemini.
"""

from typing import Any

from src.llm.providers.base import LLMProvider


def get_llm_provider(settings: Any) -> LLMProvider:
    """Return ``GeminiProvider`` or ``OpenAIProvider`` only.

    Raises:
        ValueError: if ``settings.llm_provider`` is ``claude`` or ``deepseek`` — those vendors use
            ``resolve_llm_executor`` only, not ``LLMProvider``.
    """
    provider = getattr(settings, "llm_provider", "gemini")
    if isinstance(provider, str):
        provider = (provider or "gemini").strip().lower()
    if provider == "claude":
        raise ValueError(
            "llm_provider 'claude' is not supported by legacy get_llm_provider(); "
            "use the pipeline registry (resolve_llm_executor / AnthropicSdkAdapter)."
        )
    if provider == "deepseek":
        raise ValueError(
            "llm_provider 'deepseek' is not supported by legacy get_llm_provider(); "
            "use the pipeline registry (resolve_llm_executor / DeepSeekSdkAdapter)."
        )
    if provider == "openai":
        from src.llm.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(settings)
    from src.llm.providers.gemini_provider import GeminiProvider

    return GeminiProvider(settings)
