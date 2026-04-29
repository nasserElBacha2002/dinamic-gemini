"""
Phase 3 / 5 / 7 — normalize ``LLMResponse`` into :class:`~src.pipeline.ports.analysis_provider.AnalysisResult`.

Provider-specific parsing stays inside LLM adapters; this helper only maps the neutral
``LLMResponse`` contract into the pipeline ``AnalysisResult`` shape and attaches pricing snapshot.

**Ownership:** ``provider_metadata`` and ``prompt_composition`` are built entirely by callers;
this function does not merge or default them (keeps a single place of truth for visual-reference
metadata and prompt traceability).
"""

from __future__ import annotations

from typing import Any, Mapping

from src.llm.costing import build_llm_cost_snapshot
from src.llm.types import LLMResponse
from src.pipeline.ports.analysis_provider import AnalysisResult


def build_analysis_result_from_llm_response(
    *,
    response: LLMResponse,
    prompt_composition: Mapping[str, Any],
    provider_metadata: Mapping[str, Any],
    settings: Any,
) -> AnalysisResult:
    """
    Build ``AnalysisResult`` from a successful ``LLMResponse`` (post-adapter normalization).

    ``prompt_composition`` and ``provider_metadata`` are typed as :class:`~typing.Mapping` to signal
    the helper does not mutate them; call sites pass ``dict`` instances, which are stored on
    ``AnalysisResult`` by reference (unchanged from pre–Phase 5 behavior).

    ``settings`` remains ``Any`` (same contract as :func:`resolve_llm_executor_for_context` and
    :func:`~src.llm.costing.build_llm_cost_snapshot`): pricing/catalog code reads many optional
    fields; narrowing would duplicate costing internals without improving safety here.
    """
    llm_cost_snapshot = build_llm_cost_snapshot(
        provider=response.provider,
        model=response.model,
        raw_usage=response.usage,
        settings=settings,
    )
    return AnalysisResult(
        parsed_json=response.parsed_json,
        provider_name=response.provider,
        provider_metadata=dict(provider_metadata),
        prompt_composition=dict(prompt_composition),
        llm_cost_snapshot=llm_cost_snapshot,
    )
