"""Phase 4 — provider result aggregation helpers."""

from __future__ import annotations

from src.pipeline.ports.analysis_provider import (
    PROVIDER_METADATA_KEY_MULTI_PROVIDER_EXECUTION,
    AnalysisResult,
)
from src.pipeline.services.provider_result_aggregator import (
    attach_multi_provider_trace,
    model_label_from_analysis_result,
    select_primary_first_in_order,
)


def test_select_primary_first_in_order() -> None:
    a = AnalysisResult(parsed_json={"a": 1}, provider_name="p1")
    b = AnalysisResult(parsed_json={"b": 2}, provider_name="p2")
    assert select_primary_first_in_order((a, b)).provider_name == "p1"


def test_model_label_prefers_prompt_composition() -> None:
    r = AnalysisResult(
        parsed_json={},
        provider_name="x",
        prompt_composition={"model_name": "  m1  "},
        llm_cost_snapshot={"model": "ignored"},
    )
    assert model_label_from_analysis_result(r) == "m1"


def test_attach_multi_provider_trace_merges_metadata() -> None:
    base = AnalysisResult(
        parsed_json={},
        provider_name="gemini",
        provider_metadata={"visual_reference_count": 0},
    )
    out = attach_multi_provider_trace(base, trace={"strategy_effective": "multi_parallel"})
    assert out.provider_metadata is not None
    assert out.provider_metadata["visual_reference_count"] == 0
    assert out.provider_metadata[PROVIDER_METADATA_KEY_MULTI_PROVIDER_EXECUTION]["strategy_effective"] == (
        "multi_parallel"
    )
