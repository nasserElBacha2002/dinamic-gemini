"""
Pipeline-level LLM execution port — vendor-neutral boundary for global analysis (Phase 4).

Strategies (e.g. GeminiAnalysisProvider) build ``LLMRequest`` and call an executor resolved from
``provider_name`` + settings. SDK/API details stay inside executor implementations (adapters).
"""

from __future__ import annotations

from typing import Any, Protocol

from src.llm.types import LLMRequest, LLMResponse


class LlmGlobalAnalysisExecutor(Protocol):
    """Executes one global analysis call; hides vendor SDKs from pipeline strategies."""

    def execute(self, request: LLMRequest, settings: Any) -> LLMResponse:
        """Run analysis; map vendor failures to ``LLMProviderError`` inside the adapter."""
        ...
