"""
Phase 1 — Test-only ``LlmGlobalAnalysisExecutor`` harness (multi-provider migration).

This module lives under ``tests/`` only. It is **not** a registered pipeline provider and must
never be imported from ``src/``.

**Injection:** Patch ``resolve_llm_executor_for_context`` on
``src.pipeline.services.pipeline_provider_resolver`` (see ``patch_hybrid_resolve_llm_executor``), or patch
``src.pipeline.providers.registry.resolve_llm_executor`` on the **registry module object** for tests
that bypass job-level resolution (``from src.pipeline.providers import registry as reg`` — do not
``from registry import resolve_llm_executor`` at import time or you will keep a stale reference).

**Phase 2:** Migrate tests that use ``provider_name="fake"`` / ``LLM_PROVIDER=fake`` to this
boundary instead of the transitional ``FakeProvider``.

**Standard offline pipeline pattern:** ``patch_hybrid_resolve_llm_executor`` +
``executor_from_json_fixture`` (or a ``TestLLMExecutor``). This patches
``src.pipeline.services.pipeline_provider_resolver.resolve_llm_executor_for_context``, so the
resolved logical key matches ``HARNESS_LOGICAL_PROVIDER_KEY`` instead of following
``settings.llm_provider`` (avoids coupling tests to Gemini).

**Registry-only patch:** ``patch_registry_resolve_llm_executor`` is for tests that call
``registry.resolve_llm_executor`` directly; full hybrid runs should prefer the hybrid patch above.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from src.llm.types import LLMRequest, LLMResponse
from src.pipeline.services.pipeline_provider_resolver import (
    PipelineProviderResolver,
    ResolvedPipelineExecution,
)

# Logical provider key returned as the second element of ``resolve_llm_executor_for_context`` when
# using ``patch_hybrid_resolve_llm_executor`` with defaults — not a registered production key.
HARNESS_LOGICAL_PROVIDER_KEY = "test_llm"

# Attribution strings on ``LLMResponse`` for harness-built successes (not registry keys).
HARNESS_RESPONSE_PROVIDER = "test_llm"
HARNESS_DEFAULT_MODEL = "test-model"

# Minimal v2.1-shaped dict for deterministic success defaults.
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
            provider=HARNESS_RESPONSE_PROVIDER,
            model=HARNESS_DEFAULT_MODEL,
            latency_ms=0,
            parsed_json=dict(MINIMAL_V21_PARSED),
            raw_text=None,
            usage={},
        )


def llm_response_success(
    *,
    parsed_json: dict[str, Any] | None = None,
    provider: str = HARNESS_RESPONSE_PROVIDER,
    model: str | None = HARNESS_DEFAULT_MODEL,
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
    resolved_provider_key: str = HARNESS_LOGICAL_PROVIDER_KEY,
) -> None:
    """
    Patch :func:`src.pipeline.services.pipeline_provider_resolver.resolve_llm_executor_for_context`
    (canonical Phase 3 hook used by ``HybridGlobalAnalysisStrategy``).

    ``resolved_provider_key`` is the second tuple element (logging / metadata). Default
    ``HARNESS_LOGICAL_PROVIDER_KEY`` keeps tests vendor-agnostic; pass ``\"gemini\"`` or
    ``\"openai\"`` when exercising provider-specific request metadata branches.
    """

    def _fake_resolve_llm_executor_for_context(
        pipeline_provider_name: str | None,
        settings: Any,
        *,
        model_name: str | None = None,
        **kwargs: Any,
    ) -> tuple[Any, str]:
        del pipeline_provider_name, settings, model_name, kwargs
        return executor, resolved_provider_key

    def _fake_resolve_for_run(
        *,
        pipeline_provider_name: str | None,
        settings: Any,
        job_model_name: str | None = None,
    ) -> ResolvedPipelineExecution:
        del settings, job_model_name
        requested = (pipeline_provider_name or "").strip().lower() or None
        return ResolvedPipelineExecution(
            executor=executor,
            normalized_provider_key=resolved_provider_key,
            requested_provider_key=requested,
            resolution_source="explicit_job_provider" if requested else "settings_default",
        )

    def _noop_validate_ordered_providers_for_visual_inventory_job(
        *_args: Any,
        **_kwargs: Any,
    ) -> None:
        """Offline harness runs must not fail Phase 5 contract preflight on MagicMock settings."""

    monkeypatch.setattr(
        "src.pipeline.services.pipeline_provider_resolver.resolve_llm_executor_for_context",
        _fake_resolve_llm_executor_for_context,
    )
    monkeypatch.setattr(
        PipelineProviderResolver,
        "resolve_for_run",
        staticmethod(_fake_resolve_for_run),
    )
    monkeypatch.setattr(
        "src.pipeline.services.provider_analysis_execution_config.validate_ordered_providers_for_visual_inventory_job",
        _noop_validate_ordered_providers_for_visual_inventory_job,
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


def executor_from_json_fixture(
    path: str | Path,
    *,
    provider: str = HARNESS_RESPONSE_PROVIDER,
    model: str | None = HARNESS_DEFAULT_MODEL,
) -> TestLLMExecutor:
    """
    Build a ``TestLLMExecutor`` that returns the JSON file contents as ``parsed_json``.

    Replaces legacy E2E wiring that loaded JSON via a production fake provider; tests patch the executor boundary instead.
    """
    raw = Path(path).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(raw)
    return TestLLMExecutor(
        response=llm_response_success(parsed_json=data, provider=provider, model=model),
    )


def patch_offline_hybrid_json_fixture(monkeypatch: pytest.MonkeyPatch, path: str | Path) -> None:
    """Apply ``patch_hybrid_resolve_llm_executor`` with an executor built from fixture JSON."""
    patch_hybrid_resolve_llm_executor(monkeypatch, executor_from_json_fixture(path))


# Back-compat alias (older Phase 2 migrations).
test_executor_from_json_path = executor_from_json_fixture
