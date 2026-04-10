"""Stage 2.2.D — LLM providers (gemini, openai)."""

from src.llm.providers.base import LLMProvider

__all__ = ["LLMProvider", "get_llm_provider"]  # get_llm_provider — lazy (see __getattr__)


def __getattr__(name: str):
    if name == "get_llm_provider":
        from src.llm.providers.factory import get_llm_provider

        return get_llm_provider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
