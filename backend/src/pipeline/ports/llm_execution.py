"""
Pipeline-level port for one global analysis call — vendor-neutral (Phase 4).

Analysis strategies build ``LLMRequest`` and invoke an executor chosen from ``provider_name`` +
settings via ``providers.registry``. Vendor SDKs stay inside executor implementations only.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.llm.types import LLMRequest, LLMResponse


class LlmGlobalAnalysisExecutor(Protocol):
    """Runs one global analysis; implementations map failures to ``LLMProviderError`` where applicable."""

    def execute(self, request: LLMRequest, settings: Any) -> LLMResponse:
        """Execute analysis for ``request``; ``settings`` is the run configuration snapshot."""
        ...
