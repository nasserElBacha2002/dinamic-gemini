"""
Run metadata for job-level traceability — v3.2.4 Phase 5.

Builds the visual_reference_context block from the shared AnalysisContext (Phase 3)
and provider metadata (Phase 4). Sanitizes counts and reference_ids for consistency.
Provider-agnostic; used by pipeline to produce run_metadata in memory and by
executor to persist into job.result_json.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    analysis_context_from_dict,
)
from src.pipeline.ports.analysis_provider import (
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED,
)

# Job-level block key (Phase 5)
RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT = "visual_reference_context"


def default_empty_block() -> Dict[str, Any]:
    """Canonical empty visual_reference_context for no-reference jobs (consistent shape)."""
    return {
        "resolved": False,
        "reference_ids": [],
        "resolved_count": 0,
        "provider_consumed": False,
        "provider_consumed_count": 0,
    }


def _sanitize_reference_ids(refs: List[Any]) -> List[str]:
    """Extract non-empty reference_id strings and deduplicate preserving order."""
    seen: set[str] = set()
    out: List[str] = []
    for r in refs:
        if not isinstance(r, dict) or not r.get("reference_id"):
            continue
        rid = str(r["reference_id"]).strip()
        if rid and rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def _reference_ids_from_context(ctx: Optional[AnalysisContext]) -> List[str]:
    """Extract sanitized reference_ids from formal AnalysisContext."""
    if not ctx or not ctx.visual_references:
        return []
    ids: List[str] = []
    seen: set[str] = set()
    for ref in ctx.visual_references:
        rid = (ref.reference_id or "").strip()
        if rid and rid not in seen:
            seen.add(rid)
            ids.append(rid)
    return ids


def build_visual_reference_context(
    analysis_context: Optional[Union[AnalysisContext, Dict[str, Any]]],
    provider_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build the job-level visual_reference_context block from resolved context and provider result.

    Prefers formal AnalysisContext; if a dict is passed, deserializes via analysis_context_from_dict.
    Enforces consistency: resolved_count = len(reference_ids), provider_consumed_count in [0, resolved_count],
    and provider_consumed false => provider_consumed_count = 0.
    """
    ctx: Optional[AnalysisContext] = None
    if isinstance(analysis_context, dict):
        ctx = analysis_context_from_dict(analysis_context)
        reference_ids = _reference_ids_from_context(ctx) if ctx else _sanitize_reference_ids(
            (analysis_context or {}).get("visual_references", [])
        )
    else:
        ctx = analysis_context
        reference_ids = _reference_ids_from_context(ctx) if ctx else []

    resolved_count = len(reference_ids)
    resolved = resolved_count > 0

    meta = provider_metadata or {}
    provider_consumed = bool(meta.get(PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED))
    raw_count = int(meta.get(PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT, 0))
    if not provider_consumed:
        raw_count = 0
    provider_consumed_count = max(0, min(raw_count, resolved_count))

    return {
        "resolved": resolved,
        "reference_ids": reference_ids,
        "resolved_count": resolved_count,
        "provider_consumed": provider_consumed,
        "provider_consumed_count": provider_consumed_count,
    }


def build_run_metadata(
    analysis_context: Optional[Union[AnalysisContext, Dict[str, Any]]],
    provider_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build the full run metadata dict (for in-memory propagation to executor).
    Contains visual_reference_context for job-level traceability.
    """
    return {
        RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT: build_visual_reference_context(
            analysis_context, provider_metadata
        ),
    }
