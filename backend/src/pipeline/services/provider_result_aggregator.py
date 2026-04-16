"""
Phase 4 / 6 — minimal deterministic aggregation of multiple ``AnalysisResult`` values.

Selects a primary result for the rest of the pipeline and optionally attaches a trace blob
to the primary's ``provider_metadata`` (see ``PROVIDER_METADATA_KEY_MULTI_PROVIDER_EXECUTION``).

**Primary selection:** order-based only (first entry in the caller-supplied sequence). This phase
does not rank providers by confidence, cost, or agreement — that would be future evaluation work.

**Scope:** trace attachment and primary pick only — not multi-provider dispatch (see
:mod:`src.pipeline.services.multi_provider_analysis_execution`).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional, Sequence

from src.pipeline.ports.analysis_provider import (
    PROVIDER_METADATA_KEY_MULTI_PROVIDER_EXECUTION,
    AnalysisResult,
)


def model_label_from_analysis_result(result: AnalysisResult) -> Optional[str]:
    """Best-effort model id for trace rows (prompt composition preferred, then cost snapshot)."""
    comp = result.prompt_composition or {}
    mn = comp.get("model_name")
    if isinstance(mn, str) and mn.strip():
        return mn.strip()
    snap = result.llm_cost_snapshot or {}
    m = snap.get("model")
    if isinstance(m, str) and m.strip():
        return m.strip()
    return None


def select_primary_first_in_order(results: Sequence[AnalysisResult]) -> AnalysisResult:
    """
    Return the first ``AnalysisResult`` in ``results`` (index 0).

    Used after parallel execution where ``results`` is ordered like ``ordered_provider_keys``; the
    pipeline primary is always the **first key’s** outcome, not a “best” pick across providers.
    """
    if not results:
        raise ValueError("select_primary_first_in_order requires at least one AnalysisResult")
    return results[0]


def attach_multi_provider_trace(
    primary: AnalysisResult,
    *,
    trace: Dict[str, Any],
) -> AnalysisResult:
    """Shallow-merge trace into ``primary.provider_metadata`` (copy-on-write)."""
    meta: Dict[str, Any] = dict(primary.provider_metadata or {})
    meta[PROVIDER_METADATA_KEY_MULTI_PROVIDER_EXECUTION] = trace
    return replace(primary, provider_metadata=meta)
