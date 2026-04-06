"""Legacy LLM provider protocol (Stage 2.2.D).

Still implemented by ``FakeProvider`` / ``OpenAIProvider`` / ``GeminiProvider`` for CLI and tests.
The pipeline registry prefers ``LlmGlobalAnalysisExecutor``; ``fake`` uses
``TransitionalLlmProviderBridgeExecutor``. ``openai`` is native via ``OpenAiSdkAdapter``.
"""

from typing import Protocol

from src.llm.types import LLMRequest, LLMResponse


class LLMProvider(Protocol):
    """Historical interface: one global analysis call (v2.1 entity detection)."""

    @property
    def name(self) -> str:
        """Logical provider key (e.g. ``gemini``, ``fake``)."""
        ...

    def analyze_global(self, request: LLMRequest) -> LLMResponse:
        """Run one global analysis; return parsed v2.1 JSON."""
        ...
