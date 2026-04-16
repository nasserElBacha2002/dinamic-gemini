"""
Phase 3 — normalize ``LLMResponse`` into :class:`~src.pipeline.ports.analysis_provider.AnalysisResult`.

Keeps provider-specific parsing inside adapters; the hybrid strategy only maps the neutral
``LLMResponse`` contract into the pipeline's ``AnalysisResult`` shape.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.llm.costing import build_llm_cost_snapshot
from src.llm.types import LLMResponse
from src.pipeline.ports.analysis_provider import AnalysisResult


def build_analysis_result_from_llm_response(
    *,
    response: LLMResponse,
    prompt_composition: Dict[str, Any],
    visual_references_available: bool,
    visual_references_consumed: bool,
    visual_reference_count: int,
    visual_reference_ids: List[str],
    provider_metadata: Dict[str, Any],
    settings: Any,
) -> AnalysisResult:
    """Build ``AnalysisResult`` from a successful ``LLMResponse`` (post-adapter normalization)."""
    llm_cost_snapshot = build_llm_cost_snapshot(
        provider=response.provider,
        model=response.model,
        raw_usage=response.usage,
        settings=settings,
    )
    return AnalysisResult(
        parsed_json=response.parsed_json,
        provider_name=response.provider,
        provider_metadata=provider_metadata,
        prompt_composition=prompt_composition,
        llm_cost_snapshot=llm_cost_snapshot,
    )
