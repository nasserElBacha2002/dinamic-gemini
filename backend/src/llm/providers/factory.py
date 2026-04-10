"""Stage 2.2.D — LLM provider factory (legacy ``LLMProvider`` protocol; pipeline uses registry executors)."""

from typing import Any

from src.llm.providers.base import LLMProvider
from src.llm.providers.gemini_provider import GeminiProvider
from src.llm.providers.openai_provider import OpenAIProvider


def get_llm_provider(settings: Any) -> LLMProvider:
    """Return the LLM provider for the current settings.llm_provider (gemini or openai)."""
    provider = getattr(settings, "llm_provider", "gemini")
    if isinstance(provider, str):
        provider = (provider or "gemini").strip().lower()
    if provider == "openai":
        return OpenAIProvider(settings)
    return GeminiProvider(settings)
