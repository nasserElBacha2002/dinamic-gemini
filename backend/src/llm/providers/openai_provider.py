"""Stage 2.2.D — OpenAI LLM provider (delegates to ``OpenAiSdkAdapter`` for global analysis)."""

from typing import Any

from src.llm.errors import LLMProviderError
from src.llm.openai_sdk_adapter import OpenAiSdkAdapter
from src.llm.types import LLMRequest, LLMResponse


class OpenAIProvider:
    """Thin wrapper for legacy ``analyze_global`` call sites; execution is native OpenAI vision."""

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
        return OpenAiSdkAdapter().execute(request, self._settings)
