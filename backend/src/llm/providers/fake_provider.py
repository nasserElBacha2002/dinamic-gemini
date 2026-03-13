"""Stage 2.2.D — Fake LLM provider for tests/CI (no network)."""

import json
import logging
from pathlib import Path
from typing import Any

from src.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

# Default minimal v2.1-shaped JSON when no fixture path is set
DEFAULT_FAKE_RESPONSE: dict = {
    "total_entities_detected": 0,
    "entities": [],
}


class FakeProvider:
    """LLM provider that returns a fixed or fixture-based v2.1 JSON (no network)."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._fixture_path: str | None = getattr(
            settings, "fake_llm_fixture_path", None
        ) or None

    @property
    def name(self) -> str:
        return "fake"

    def analyze_global(self, request: LLMRequest) -> LLMResponse:
        if self._fixture_path and Path(self._fixture_path).is_file():
            with open(self._fixture_path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = DEFAULT_FAKE_RESPONSE.copy()
        return LLMResponse(
            provider="fake",
            model=None,
            latency_ms=0,
            parsed_json=data,
            raw_text=json.dumps(data),
            usage=None,
        )
