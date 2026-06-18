"""
Phase 1 — Demonstration tests for ``tests.support.llm_executor_harness``.

Proves the test-only executor boundary works for later migration off ``fake``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.llm.errors import LLMProviderError
from src.llm.types import LLMRequest, LLMResponse
from src.parsing.global_analysis_parser import parse_entities
from src.pipeline.adapters.hybrid_global_analysis_strategy import HybridGlobalAnalysisStrategy
from src.pipeline.context.run_context import RunContext
from src.pipeline.providers import registry as pipeline_registry
from tests.support.llm_executor_harness import (
    HARNESS_DEFAULT_MODEL,
    HARNESS_LOGICAL_PROVIDER_KEY,
    TestLLMExecutor,
    executor_from_json_fixture,
    llm_response_success,
    patch_hybrid_resolve_llm_executor,
    patch_offline_hybrid_json_fixture,
    patch_registry_resolve_llm_executor,
)


def test_test_llm_executor_default_success_minimal_v21() -> None:
    ex = TestLLMExecutor()
    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
    )
    resp = ex.execute(req, MagicMock())
    assert resp.provider == "test_llm"
    assert resp.model == HARNESS_DEFAULT_MODEL
    assert resp.parsed_json == {"total_entities_detected": 0, "entities": []}


def test_test_llm_executor_fixed_response_with_raw_text() -> None:
    raw = '{"total_entities_detected": 1, "entities": []}'
    ex = TestLLMExecutor(
        response=llm_response_success(
            parsed_json={"total_entities_detected": 1, "entities": []},
            provider="custom",
            model="m1",
            raw_text=raw,
        )
    )
    resp = ex.execute(
        LLMRequest(job_id="j", frames=[], frame_refs=[], prompt="p", schema_version="v2.1"),
        MagicMock(),
    )
    assert resp.provider == "custom"
    assert resp.model == "m1"
    assert resp.raw_text == raw


def test_test_llm_executor_raises_runtime_error() -> None:
    ex = TestLLMExecutor(error=RuntimeError("executor boom"))
    with pytest.raises(RuntimeError, match="executor boom"):
        ex.execute(
            LLMRequest(job_id="j", frames=[], frame_refs=[], prompt="p", schema_version="v2.1"),
            MagicMock(),
        )


def test_test_llm_executor_raises_llm_provider_error() -> None:
    ex = TestLLMExecutor(
        error=LLMProviderError(code="RATE_LIMIT", message="slow down", details={"provider": "x"})
    )
    with pytest.raises(LLMProviderError) as ei:
        ex.execute(
            LLMRequest(job_id="j", frames=[], frame_refs=[], prompt="p", schema_version="v2.1"),
            MagicMock(),
        )
    assert ei.value.code == "RATE_LIMIT"


def test_test_llm_executor_handler_receives_request_and_settings() -> None:
    seen: list[tuple[str, object]] = []

    def handler(request: LLMRequest, settings: object) -> LLMResponse:
        seen.append((request.job_id, settings))
        return llm_response_success(parsed_json={"total_entities_detected": 0, "entities": []})

    ex = TestLLMExecutor(handler=handler)
    settings = MagicMock()
    ex.execute(
        LLMRequest(job_id="job-xyz", frames=[], frame_refs=[], prompt="hi", schema_version="v2.1"),
        settings,
    )
    assert seen == [("job-xyz", settings)]


def test_test_llm_executor_rejects_multiple_modes() -> None:
    with pytest.raises(ValueError, match="at most one"):
        TestLLMExecutor(
            response=llm_response_success(),
            error=RuntimeError("x"),
        )


def test_patch_registry_resolve_llm_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = TestLLMExecutor(
        response=llm_response_success(
            provider="registry_stub", parsed_json={"total_entities_detected": 0, "entities": []}
        )
    )
    patch_registry_resolve_llm_executor(monkeypatch, stub)
    # Resolve via module so monkeypatch replaces the same object the test calls.
    out = pipeline_registry.resolve_llm_executor("openai", MagicMock())
    assert out is stub
    r = out.execute(
        LLMRequest(job_id="j", frames=[], frame_refs=[], prompt="p", schema_version="v2.1"),
        MagicMock(),
    )
    assert r.provider == "registry_stub"


def test_patch_hybrid_strategy_uses_executor_without_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HybridGlobalAnalysisStrategy runs with a patched executor; no FakeProvider / fake registry path."""
    parsed = {
        "total_entities_detected": 1,
        "entities": [
            {
                "model_entity_id": "E1",
                "entity_type": "PALLET",
                "confidence": 0.9,
                "has_boxes": True,
            }
        ],
    }
    executor = TestLLMExecutor(
        response=llm_response_success(parsed_json=parsed, provider="harness")
    )
    patch_hybrid_resolve_llm_executor(monkeypatch, executor)

    settings = MagicMock()
    settings.llm_provider = "openai"
    job_input = MagicMock()
    context = RunContext(
        job_id="j1",
        run_id="r1",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j1/r1"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    strategy = HybridGlobalAnalysisStrategy()
    result = strategy.analyze(
        context=context,
        frames_nd=[np.zeros((10, 10, 3), dtype=np.uint8)],
        frame_paths=[],
        frame_refs=["f0"],
        metadata={},
    )
    assert result.provider_name == "harness"
    entities = parse_entities(result.parsed_json, job_id="j1")
    assert len(entities) == 1


def test_malformed_parsed_json_passes_through_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Executor can return structurally invalid JSON for downstream tests (normalization targets)."""
    executor = TestLLMExecutor(
        response=llm_response_success(
            parsed_json={"not_v21": True},
            raw_text="not json",
        )
    )
    patch_hybrid_resolve_llm_executor(monkeypatch, executor)
    settings = MagicMock()
    settings.llm_provider = "openai"
    context = RunContext(
        job_id="j-bad",
        run_id="r1",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j-bad/r1"),
        job_input=MagicMock(),
        settings=settings,
        logger=MagicMock(),
    )
    strategy = HybridGlobalAnalysisStrategy()
    result = strategy.analyze(
        context=context,
        frames_nd=[np.zeros((4, 4, 3), dtype=np.uint8)],
        frame_paths=[],
        frame_refs=["x"],
        metadata={},
    )
    assert result.parsed_json == {"not_v21": True}


def test_executor_from_json_fixture_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        executor_from_json_fixture(bad)


def test_response_with_markdown_fenced_raw_text_preserved() -> None:
    inner = '{"total_entities_detected": 0, "entities": []}'
    raw = f"```json\n{inner}\n```"
    ex = TestLLMExecutor(
        response=llm_response_success(
            parsed_json={"total_entities_detected": 0, "entities": []},
            raw_text=raw,
        )
    )
    out = ex.execute(
        LLMRequest(job_id="j", frames=[], frame_refs=[], prompt="p", schema_version="v2.1"),
        MagicMock(),
    )
    assert out.raw_text == raw


def test_patch_hybrid_default_resolved_key_is_harness_logical_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default patch should surface ``HARNESS_LOGICAL_PROVIDER_KEY`` in execution metadata, not a vendor."""
    ex = TestLLMExecutor()
    patch_hybrid_resolve_llm_executor(monkeypatch, ex)
    context = RunContext(
        job_id="j1",
        run_id="r1",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j1/r1"),
        job_input=MagicMock(),
        settings=MagicMock(llm_provider="gemini"),
        logger=MagicMock(),
        execution_log=MagicMock(),
    )
    HybridGlobalAnalysisStrategy().analyze(
        context=context,
        frames_nd=[np.zeros((4, 4, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/a.jpg")],
        frame_refs=["a"],
        metadata={"frame_count": 1},
    )
    calls = context.execution_log.info.call_args_list
    prepared = next(
        (c for c in calls if len(c.args) > 1 and c.args[1] == "Analysis request prepared"), None
    )
    assert prepared is not None
    assert prepared.kwargs["payload"]["pipeline_provider"] == HARNESS_LOGICAL_PROVIDER_KEY


def test_patch_offline_hybrid_json_fixture_applies_executor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    p = tmp_path / "fx.json"
    p.write_text('{"total_entities_detected": 0, "entities": []}', encoding="utf-8")
    patch_offline_hybrid_json_fixture(monkeypatch, p)
    from src.pipeline.services import pipeline_provider_resolver as ppr

    ex, key = ppr.resolve_llm_executor_for_context(None, MagicMock())
    assert key == HARNESS_LOGICAL_PROVIDER_KEY
    r = ex.execute(
        LLMRequest(job_id="j", frames=[], frame_refs=[], prompt="p", schema_version="v2.1"),
        MagicMock(),
    )
    assert r.parsed_json["total_entities_detected"] == 0
