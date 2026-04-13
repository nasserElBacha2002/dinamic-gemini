"""Legacy LLM provider protocol (Stage 2.2.D).

Implemented by ``OpenAIProvider`` / ``GeminiProvider`` for non-pipeline callers.
The hybrid pipeline resolves ``LlmGlobalAnalysisExecutor`` from the provider registry (Gemini/OpenAI).
"""

from typing import Protocol

from src.llm.types import LLMRequest, LLMResponse


class LLMProvider(Protocol):
    """Historical interface: one global analysis call (v2.1 entity detection)."""

    @property
    def name(self) -> str:
        """Logical provider key (e.g. ``gemini``, ``openai``)."""
        ...

    def analyze_global(self, request: LLMRequest) -> LLMResponse:
        """Run one global analysis; return parsed v2.1 JSON."""
        ...
