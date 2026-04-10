"""
Phase 1 — Test-only ``LlmGlobalAnalysisExecutor`` harness (multi-provider migration).

This module lives under ``tests/`` only. It is **not** a registered pipeline provider and must
never be imported from ``src/``.

**Injection:** Patch ``resolve_llm_executor_for_context`` where the hybrid analysis strategy
imports it (see ``patch_hybrid_resolve_llm_executor``), or patch
``src.pipeline.providers.registry.resolve_llm_executor`` for tests that call the registry
directly. After patching the registry, call ``registry.resolve_llm_executor`` on the **module**
(``from src.pipeline.providers import registry as reg``) — do not ``from registry import
resolve_llm_executor`` at import time or you will keep a stale function reference.

**Phase 2:** Migrate tests that use ``provider_name="fake"`` / ``LLM_PROVIDER=fake`` to this
boundary instead of the transitional ``FakeProvider``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

import pytest

from src.llm.errors import LLMProviderError
from src.llm.types import LLMRequest, LLMResponse

# Minimal v2.1-shaped dict for deterministic success defaults (aligned with FakeProvider default).
MINIMAL_V21_PARSED: dict[str, Any] = {
    "total_entities_detected": 0,
    "entities": [],
}

ExecutorHandler = Callable[[LLMRequest, Any], LLMResponse]


class TestLLMExecutor:
    """
    Test double implementing ``LlmGlobalAnalysisExecutor.execute``.

    Configure **exactly one** of ``response``, ``handler``, or ``error``. If all are omitted,
    ``execute`` returns a minimal successful ``LLMResponse`` (provider ``test_llm``).
    """

    __test__ = False  # tell pytest not to collect this class as a test

    def __init__(
        self,
        *,
        response: LLMResponse | None = None,
        handler: ExecutorHandler | None = None,
        error: BaseException | None = None,
    ) -> None:
        configured = sum(1 for x in (response, handler, error) if x is not None)
        if configured > 1:
            raise ValueError("Specify at most one of response=, handler=, error=")
        self._response = response
        self._handler = handler
        self._error = error

    def execute(self, request: LLMRequest, settings: Any) -> LLMResponse:
        if self._error is not None:
            raise self._error
        if self._handler is not None:
            return self._handler(request, settings)
        if self._response is not None:
            return self._response
        return LLMResponse(
            provider="test_llm",
            model="fixture",
            latency_ms=0,
            parsed_json=dict(MINIMAL_V21_PARSED),
            raw_text=None,
            usage={},
        )


def llm_response_success(
    *,
    parsed_json: dict[str, Any] | None = None,
    provider: str = "test_llm",
    model: str | None = "test-model",
    raw_text: str | None = None,
    latency_ms: int = 0,
    usage: dict[str, Any] | None = None,
) -> LLMResponse:
    """Build a successful ``LLMResponse`` for use with ``TestLLMExecutor(response=...)``."""
    body = dict(MINIMAL_V21_PARSED) if parsed_json is None else parsed_json
    return LLMResponse(
        provider=provider,
        model=model,
        latency_ms=latency_ms,
        parsed_json=body,
        raw_text=raw_text,
        usage=dict(usage) if usage else {},
    )


def patch_hybrid_resolve_llm_executor(
    monkeypatch: pytest.MonkeyPatch,
    executor: Any,
    *,
    resolved_provider_key: str = "gemini",
) -> None:
    """
    Patch ``resolve_llm_executor_for_context`` as bound in ``HybridGlobalAnalysisStrategy``.

    ``resolved_provider_key`` is the second tuple element (e.g. ``gemini`` / ``openai``) and
    affects model metadata injection in the strategy.
    """

    def _fake_resolve(
        pipeline_provider_name: str | None,
        settings: Any,
    ) -> tuple[Any, str]:
        del pipeline_provider_name, settings
        return executor, resolved_provider_key

    monkeypatch.setattr(
        "src.pipeline.adapters.hybrid_global_analysis_strategy.resolve_llm_executor_for_context",
        _fake_resolve,
    )


def patch_registry_resolve_llm_executor(
    monkeypatch: pytest.MonkeyPatch,
    executor: Any,
) -> None:
    """Patch ``src.pipeline.providers.registry.resolve_llm_executor`` to return ``executor``."""

    def _fake_resolve(provider_key: str, settings: Any) -> Any:
        del provider_key, settings
        return executor

    monkeypatch.setattr(
        "src.pipeline.providers.registry.resolve_llm_executor",
        _fake_resolve,
    )


def test_executor_from_json_path(
    path: str | Path,
    *,
    provider: str = "gemini",
    model: str = "gemini-2.0-flash-exp",
) -> TestLLMExecutor:
    """
    Build a ``TestLLMExecutor`` that returns the JSON file contents as ``parsed_json``.

    Replaces E2E usage of ``fake_llm_fixture_path`` + ``FakeProvider`` at the executor boundary.
    """
    raw = Path(path).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(raw)
    return TestLLMExecutor(
        response=llm_response_success(parsed_json=data, provider=provider, model=model),
    )
