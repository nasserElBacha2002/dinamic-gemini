"""
Phase 3 / 5 / 7 — normalize ``LLMResponse`` into :class:`~src.pipeline.ports.analysis_provider.AnalysisResult`.

Provider-specific parsing stays inside LLM adapters; this helper only maps the neutral
``LLMResponse`` contract into the pipeline ``AnalysisResult`` shape and attaches pricing snapshot.

**Ownership:** ``provider_metadata`` and ``prompt_composition`` are built entirely by callers;
this function does not merge or default them (keeps a single place of truth for visual-reference
metadata and prompt traceability).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.llm.costing import build_llm_cost_snapshot
from src.llm.types import LLMResponse
from src.pipeline.ports.analysis_provider import AnalysisResult


def _mutable_dict_from_mapping(m: Mapping[str, Any]) -> dict[str, Any]:
    return m if isinstance(m, dict) else dict(m)


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
    the helper does not mutate them. When the caller passes a plain ``dict``, that same object is
    stored on ``AnalysisResult`` (identity preserved for Phase 6 traceability). Other ``Mapping``
    types are copied to a new ``dict``.

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
        provider_metadata=_mutable_dict_from_mapping(provider_metadata),
        prompt_composition=_mutable_dict_from_mapping(prompt_composition),
        llm_cost_snapshot=llm_cost_snapshot,
    )
