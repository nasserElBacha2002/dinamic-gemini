"""Stage 2.2.D — Gemini LLM provider (delegates to pipeline GeminiSdkAdapter)."""

from typing import Any

from src.llm.gemini_sdk_adapter import GeminiSdkAdapter
from src.llm.types import LLMRequest, LLMResponse


class GeminiProvider:
    """LLM provider that uses Gemini (same prompt/schema/retry as before).

    SDK calls are centralized in ``GeminiSdkAdapter`` (Phase 4) so the pipeline and ``llm``
    package share one implementation path.
    """

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._adapter = GeminiSdkAdapter()

    @property
    def name(self) -> str:
        return "gemini"

    def analyze_global(self, request: LLMRequest) -> LLMResponse:
        return self._adapter.execute(request, self._settings)
