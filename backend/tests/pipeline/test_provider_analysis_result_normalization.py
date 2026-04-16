"""Phase 3 — ``LLMResponse`` → ``AnalysisResult`` normalization."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.llm.types import LLMResponse
from src.pipeline.services.provider_analysis_result_normalization import (
    build_analysis_result_from_llm_response,
)


def test_build_analysis_result_from_llm_response_maps_fields() -> None:
    response = LLMResponse(
        provider="openai",
        model="gpt-4o-mini",
        latency_ms=10,
        parsed_json={"total_entities_detected": 0, "entities": []},
        usage={"prompt_tokens": 1},
    )
    settings = MagicMock()
    pm = {"visual_references_consumed": False}
    pc = {"profile_name": "hybrid", "pipeline_provider_key": "openai"}
    out = build_analysis_result_from_llm_response(
        response=response,
        prompt_composition=pc,
        visual_references_available=False,
        visual_references_consumed=False,
        visual_reference_count=0,
        visual_reference_ids=[],
        provider_metadata=pm,
        settings=settings,
    )
    assert out.provider_name == "openai"
    assert out.parsed_json["total_entities_detected"] == 0
    assert out.prompt_composition == pc
    assert out.provider_metadata == pm
    assert out.llm_cost_snapshot is not None
