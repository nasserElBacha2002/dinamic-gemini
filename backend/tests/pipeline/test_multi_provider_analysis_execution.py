"""Phase 4 / 6 — multi-provider dispatch (parallel + sequential fallback) and trace helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.llm.errors import LLMProviderError
from src.llm.types import LLMRequest
from src.pipeline.context.run_context import RunContext
from src.pipeline.ports.analysis_provider import (
    PROVIDER_METADATA_KEY_MULTI_PROVIDER_EXECUTION,
    AnalysisResult,
)
from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.pipeline.services.multi_provider_analysis_execution import dispatch_multi_provider_analysis
from src.pipeline.services.provider_analysis_execution_config import (
    STRATEGY_MULTI_PARALLEL,
    STRATEGY_MULTI_SEQUENTIAL,
)
from tests.support.llm_executor_harness import TestLLMExecutor, llm_response_success


def _ctx(*, settings: MagicMock, pipeline_provider_name: str | None = "openai") -> RunContext:
    job_input = MagicMock()
    job_input.metadata = {}
    return RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
        pipeline_provider_name=pipeline_provider_name,
    )


def _settings_base() -> MagicMock:
    s = MagicMock()
    s.llm_provider = "openai"
    s.hybrid_prompt = "global_v21"
    s.output_dir = "/tmp/out"
    s.debug_log_full_analysis_prompt = False
    return s


def test_parallel_runs_each_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str | None] = []

    def handler(request: LLMRequest, s: object) -> object:
        comp = (request.metadata or {}).get("prompt_composition") or {}
        rk = str(comp.get("resolved_llm_provider_key") or "").strip().lower()
        seen.append(rk)
        return llm_response_success(parsed_json={"k": rk}, provider=rk, model=f"model-{rk}")

    executor = TestLLMExecutor(handler=handler)

    def fake_resolve(pipeline_provider_name: str | None, settings: object) -> tuple[object, str]:
        key = normalize_pipeline_provider_key(pipeline_provider_name, settings)
        return executor, key

    monkeypatch.setattr(
        "src.pipeline.services.pipeline_provider_resolver.resolve_llm_executor_for_context",
        fake_resolve,
    )

    settings = _settings_base()
    settings.pipeline_analysis_execution_strategy = "not_read_here"
    settings.pipeline_analysis_extra_provider_keys = "not_read_here"
    base = _ctx(settings=settings, pipeline_provider_name="openai")

    def analyze_once(rc: RunContext) -> AnalysisResult:
        from src.pipeline.adapters.hybrid_global_analysis_strategy import (
            HybridGlobalAnalysisStrategy,
        )

        return HybridGlobalAnalysisStrategy()._analyze_once(
            rc,
            [],
            [],
            [],
            {},
        )

    out = dispatch_multi_provider_analysis(
        strategy_name=STRATEGY_MULTI_PARALLEL,
        base_context=base,
        ordered_provider_keys=["openai", "claude"],
        analyze_once=analyze_once,
        run_logger=base.logger,
    )
    assert set(seen) == {"openai", "claude"}
    assert out.provider_name == "openai"
    meta = out.provider_metadata or {}
    trace = meta.get(PROVIDER_METADATA_KEY_MULTI_PROVIDER_EXECUTION) or {}
    assert trace.get("primary_provider_key") == "openai"
    assert trace.get("ordered_provider_keys") == ["openai", "claude"]


def test_parallel_all_must_succeed_propagates_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """``multi_parallel``: if any branch raises, the dispatch fails (no partial primary result)."""

    def handler(request: LLMRequest, s: object) -> object:
        comp = (request.metadata or {}).get("prompt_composition") or {}
        rk = str(comp.get("resolved_llm_provider_key") or "").strip().lower()
        if rk == "claude":
            raise LLMProviderError(code="RATE_LIMIT", message="claude down", details={})
        return llm_response_success(parsed_json={"k": rk}, provider=rk, model="m")

    executor = TestLLMExecutor(handler=handler)

    def fake_resolve(pipeline_provider_name: str | None, settings: object) -> tuple[object, str]:
        key = normalize_pipeline_provider_key(pipeline_provider_name, settings)
        return executor, key

    monkeypatch.setattr(
        "src.pipeline.services.pipeline_provider_resolver.resolve_llm_executor_for_context",
        fake_resolve,
    )

    settings = _settings_base()
    base = _ctx(settings=settings, pipeline_provider_name="openai")

    def analyze_once(rc: RunContext) -> AnalysisResult:
        from src.pipeline.adapters.hybrid_global_analysis_strategy import (
            HybridGlobalAnalysisStrategy,
        )

        return HybridGlobalAnalysisStrategy()._analyze_once(
            rc,
            [],
            [],
            [],
            {},
        )

    with pytest.raises(LLMProviderError, match="claude down"):
        dispatch_multi_provider_analysis(
            strategy_name=STRATEGY_MULTI_PARALLEL,
            base_context=base,
            ordered_provider_keys=["openai", "claude"],
            analyze_once=analyze_once,
            run_logger=base.logger,
        )


def test_sequential_fallback_stops_after_first_success_without_calling_later_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sequential mode is fallback: later keys are skipped once an earlier provider succeeds."""
    calls: list[str | None] = []

    def handler(request: LLMRequest, s: object) -> object:
        comp = (request.metadata or {}).get("prompt_composition") or {}
        rk = str(comp.get("resolved_llm_provider_key") or "").strip().lower()
        calls.append(rk)
        return llm_response_success(parsed_json={"ok": True}, provider=rk, model="m")

    executor = TestLLMExecutor(handler=handler)

    def fake_resolve(pipeline_provider_name: str | None, settings: object) -> tuple[object, str]:
        key = normalize_pipeline_provider_key(pipeline_provider_name, settings)
        return executor, key

    monkeypatch.setattr(
        "src.pipeline.services.pipeline_provider_resolver.resolve_llm_executor_for_context",
        fake_resolve,
    )

    settings = _settings_base()
    base = _ctx(settings=settings, pipeline_provider_name="openai")

    def analyze_once(rc: RunContext) -> AnalysisResult:
        from src.pipeline.adapters.hybrid_global_analysis_strategy import (
            HybridGlobalAnalysisStrategy,
        )

        return HybridGlobalAnalysisStrategy()._analyze_once(
            rc,
            [],
            [],
            [],
            {},
        )

    out = dispatch_multi_provider_analysis(
        strategy_name=STRATEGY_MULTI_SEQUENTIAL,
        base_context=base,
        ordered_provider_keys=["openai", "claude", "gemini"],
        analyze_once=analyze_once,
        run_logger=base.logger,
    )
    assert calls == ["openai"]
    assert out.provider_name == "openai"
    trace = (out.provider_metadata or {}).get(PROVIDER_METADATA_KEY_MULTI_PROVIDER_EXECUTION) or {}
    assert trace.get("primary_provider_key") == "openai"
    runs = trace.get("runs") or []
    assert any(r.get("status") == "skipped" and r.get("provider_key") == "claude" for r in runs)


def test_sequential_uses_second_provider_after_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str | None] = []

    def handler(request: LLMRequest, s: object) -> object:
        comp = (request.metadata or {}).get("prompt_composition") or {}
        rk = str(comp.get("resolved_llm_provider_key") or "").strip().lower()
        calls.append(rk)
        if rk == "openai":
            raise LLMProviderError(code="RATE_LIMIT", message="slow", details={})
        return llm_response_success(parsed_json={"ok": True}, provider=rk, model="m")

    executor = TestLLMExecutor(handler=handler)

    def fake_resolve(pipeline_provider_name: str | None, settings: object) -> tuple[object, str]:
        key = normalize_pipeline_provider_key(pipeline_provider_name, settings)
        return executor, key

    monkeypatch.setattr(
        "src.pipeline.services.pipeline_provider_resolver.resolve_llm_executor_for_context",
        fake_resolve,
    )

    settings = _settings_base()
    base = _ctx(settings=settings, pipeline_provider_name="openai")

    def analyze_once(rc: RunContext) -> AnalysisResult:
        from src.pipeline.adapters.hybrid_global_analysis_strategy import (
            HybridGlobalAnalysisStrategy,
        )

        return HybridGlobalAnalysisStrategy()._analyze_once(
            rc,
            [],
            [],
            [],
            {},
        )

    out = dispatch_multi_provider_analysis(
        strategy_name=STRATEGY_MULTI_SEQUENTIAL,
        base_context=base,
        ordered_provider_keys=["openai", "claude"],
        analyze_once=analyze_once,
        run_logger=base.logger,
    )
    assert calls == ["openai", "claude"]
    assert out.provider_name == "claude"
    trace = (out.provider_metadata or {}).get(PROVIDER_METADATA_KEY_MULTI_PROVIDER_EXECUTION) or {}
    assert trace.get("primary_provider_key") == "claude"


def test_hybrid_single_strategy_ignores_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default single path: one provider resolution even if extras are configured on settings."""
    resolve_calls: list[str | None] = []

    def counting_resolve(
        pipeline_provider_name: str | None, settings: object
    ) -> tuple[object, str]:
        resolve_calls.append(pipeline_provider_name)
        key = normalize_pipeline_provider_key(pipeline_provider_name, settings)
        return TestLLMExecutor(), key

    monkeypatch.setattr(
        "src.pipeline.services.pipeline_provider_resolver.resolve_llm_executor_for_context",
        counting_resolve,
    )

    settings = _settings_base()
    settings.pipeline_analysis_execution_strategy = "single"
    settings.pipeline_analysis_extra_provider_keys = "claude,gemini"
    ctx = _ctx(settings=settings, pipeline_provider_name=None)

    from src.pipeline.adapters.hybrid_global_analysis_strategy import HybridGlobalAnalysisStrategy

    HybridGlobalAnalysisStrategy().analyze(
        ctx,
        [np.zeros((8, 8, 3), dtype=np.uint8)],
        [Path("/tmp/f0.jpg")],
        ["f0"],
        {"frame_count": 1},
    )
    assert len(resolve_calls) == 1


def test_sequential_skipped_trace_entries_matches_fallback_contract() -> None:
    """Phase 6 — skipped rows after success stay stable for execution-log consumers."""
    from src.pipeline.services.multi_provider_analysis_execution import (
        _sequential_skipped_trace_entries,
    )

    rows = _sequential_skipped_trace_entries(["openai", "claude", "gemini"], successful_index=0)
    assert rows == [
        {"provider_key": "claude", "status": "skipped", "reason": "prior_provider_succeeded"},
        {"provider_key": "gemini", "status": "skipped", "reason": "prior_provider_succeeded"},
    ]
    assert _sequential_skipped_trace_entries(["a", "b"], successful_index=1) == []


def test_parallel_trace_payload_includes_ordered_runs() -> None:
    """Phase 6 — parallel trace shape stays keyed to ``ordered_provider_keys`` order."""
    from src.pipeline.services.multi_provider_analysis_execution import _parallel_trace_payload

    r_openai = AnalysisResult(parsed_json={"x": 1}, provider_name="openai")
    r_claude = AnalysisResult(parsed_json={"x": 2}, provider_name="claude")
    by_key = {"openai": r_openai, "claude": r_claude}
    trace = _parallel_trace_payload(keys=["openai", "claude"], results_by_key=by_key)
    assert trace["strategy_effective"] == "multi_parallel"
    assert trace["primary_provider_key"] == "openai"
    assert [row["provider_key"] for row in trace["runs"]] == ["openai", "claude"]


def test_parallel_trace_satisfies_multi_provider_execution_trace_contract() -> None:
    """Phase 7 — trace dict matches ``MultiProviderExecutionTrace`` (required keys + row statuses)."""
    from src.pipeline.contracts.multi_provider_trace_types import MultiProviderExecutionTrace
    from src.pipeline.services.multi_provider_analysis_execution import _parallel_trace_payload

    r_openai = AnalysisResult(parsed_json={}, provider_name="openai")
    trace: MultiProviderExecutionTrace = _parallel_trace_payload(
        keys=["openai"],
        results_by_key={"openai": r_openai},
    )
    assert set(trace) >= {
        "strategy_effective",
        "ordered_provider_keys",
        "primary_provider_key",
        "runs",
    }
    assert trace["runs"][0]["status"] == "ok"
