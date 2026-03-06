"""Stage 2.2.D — LLM provider protocol."""

from typing import Protocol

from src.llm.types import LLMRequest, LLMResponse


class LLMProvider(Protocol):
    """Protocol for global-analysis LLM calls (v2.1 entity detection)."""

    @property
    def name(self) -> str:
        """Provider identifier (e.g. 'gemini', 'fake')."""
        ...

    def analyze_global(self, request: LLMRequest) -> LLMResponse:
        """Run one global analysis; return parsed v2.1 JSON in LLMResponse."""
        ...
