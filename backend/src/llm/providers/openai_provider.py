"""Stage 2.2.D — OpenAI LLM provider (stub: NOT_CONFIGURED until integrated)."""

from typing import Any

from src.llm.errors import LLMProviderError
from src.llm.types import LLMRequest, LLMResponse


class OpenAIProvider:
    """LLM provider for OpenAI (stub: raises NOT_CONFIGURED if no key)."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "openai"

    def analyze_global(self, request: LLMRequest) -> LLMResponse:
        api_key = getattr(self._settings, "openai_api_key", "") or ""
        if not api_key.strip():
            raise LLMProviderError(
                code="NOT_CONFIGURED",
                message="OPENAI_API_KEY not set; required when llm_provider=openai",
                details={"provider": "openai"},
            )
        # TODO: integrate OpenAI vision API for global analysis (v2.1 schema)
        raise LLMProviderError(
            code="NOT_IMPLEMENTED",
            message="OpenAI provider not yet implemented",
            details={"provider": "openai"},
        )
