"""
Run metadata for job-level traceability — v3.2.4 Phase 5.

Builds the visual_reference_context block from the shared AnalysisContext (Phase 3)
and provider metadata (Phase 4). Sanitizes counts and reference_ids for consistency.
Provider-agnostic; used by pipeline to produce run_metadata in memory and by
executor to persist into job.result_json.
"""

from __future__ import annotations

from typing import Any

from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    analysis_context_from_dict,
)
from src.pipeline.execution_log_sanitizer import (
    find_non_json_serializable_path,
    make_json_safe_for_execution_log,
)
from src.pipeline.ports.analysis_provider import (
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED,
)

# Job-level block key (Phase 5)
RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT = "visual_reference_context"
# Phase 6 — optional prompt traceability block (backward compatible when absent)
RUN_METADATA_KEY_PROMPT_COMPOSITION = "prompt_composition"
# Phase 10 — provider-agnostic one-call usage/pricing/cost snapshot
RUN_METADATA_KEY_LLM_COST_SNAPSHOT = "llm_cost_snapshot"
# Phase H4 — compact persisted audit snapshot (safe metadata only; no prompt bodies)
RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT = "run_audit_snapshot"


def default_empty_block() -> dict[str, Any]:
    """Canonical empty visual_reference_context for no-reference jobs (consistent shape)."""
    return {
        "resolved": False,
        "reference_ids": [],
        "resolved_count": 0,
        "provider_consumed": False,
        "provider_consumed_count": 0,
    }


def _sanitize_reference_ids(refs: list[Any]) -> list[str]:
    """Extract non-empty reference_id strings and deduplicate preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for r in refs:
        if not isinstance(r, dict) or not r.get("reference_id"):
            continue
        rid = str(r["reference_id"]).strip()
        if rid and rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def _reference_ids_from_context(ctx: AnalysisContext | None) -> list[str]:
    """Extract sanitized reference_ids from formal AnalysisContext."""
    if not ctx or not ctx.visual_references:
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for ref in ctx.visual_references:
        rid = (ref.reference_id or "").strip()
        if rid and rid not in seen:
            seen.add(rid)
            ids.append(rid)
    return ids


def _reference_ids_from_provider_metadata(meta: dict[str, Any]) -> list[str]:
    raw_ids = meta.get(PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS)
    if not isinstance(raw_ids, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_ids:
        rid = str(item).strip() if item is not None else ""
        if rid and rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def build_visual_reference_context(
    analysis_context: AnalysisContext | dict[str, Any] | None,
    provider_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build the job-level visual_reference_context block from resolved context and provider result.

    Prefers formal AnalysisContext; if a dict is passed, deserializes via analysis_context_from_dict.
    Enforces consistency: resolved_count = len(reference_ids), provider_consumed_count in [0, resolved_count],
    and provider_consumed false => provider_consumed_count = 0.
    """
    ctx: AnalysisContext | None = None
    if isinstance(analysis_context, dict):
        ctx = analysis_context_from_dict(analysis_context)
        context_reference_ids = (
            _reference_ids_from_context(ctx)
            if ctx
            else _sanitize_reference_ids((analysis_context or {}).get("visual_references", []))
        )
    else:
        ctx = analysis_context
        # Formal AnalysisContext (or None): must mirror dict branch — otherwise
        # context_reference_ids is undefined on the non-dict path (runtime UnboundLocalError).
        context_reference_ids = _reference_ids_from_context(ctx)

    meta = provider_metadata or {}
    provider_reference_ids = _reference_ids_from_provider_metadata(meta)
    reference_ids = provider_reference_ids or context_reference_ids
    provider_consumed = bool(meta.get(PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED))
    raw_count_from_meta = int(meta.get(PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT, 0))
    raw_count = raw_count_from_meta
    if not provider_consumed:
        raw_count = 0
    provider_consumed_count = max(0, min(raw_count, len(reference_ids)))
    resolved_count = len(reference_ids)
    count_key_present = PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT in meta
    if provider_reference_ids or (count_key_present and provider_consumed):
        resolved_count = provider_consumed_count
        reference_ids = (
            provider_reference_ids[:provider_consumed_count]
            if provider_reference_ids
            else reference_ids[:provider_consumed_count]
        )
    elif count_key_present and not provider_consumed and raw_count_from_meta == 0:
        # Provider reported no consumption and count 0 — job output has no resolved reference slice.
        resolved_count = provider_consumed_count
        reference_ids = reference_ids[:provider_consumed_count]
    resolved = resolved_count > 0

    block: dict[str, Any] = {
        "resolved": resolved,
        "reference_ids": reference_ids,
        "resolved_count": resolved_count,
        "provider_consumed": provider_consumed,
        "provider_consumed_count": provider_consumed_count,
    }
    # Optional traceability for C7+ jobs; omitted for legacy inventory_reference-only contexts.
    if ctx and ctx.visual_references and any(
        getattr(ref, "role", "") == "supplier_reference" for ref in ctx.visual_references
    ):
        block["reference_source"] = "supplier_reference_images"
    return block


def build_run_metadata(
    analysis_context: AnalysisContext | dict[str, Any] | None,
    provider_metadata: dict[str, Any] | None,
    prompt_composition: dict[str, Any] | None = None,
    llm_cost_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the full run metadata dict (for in-memory propagation to executor).
    Contains visual_reference_context for job-level traceability.
    Phase 6: optional ``prompt_composition`` — when provided, the same dict object SHOULD be the
    one from ``AnalysisResult`` / ``LLMRequest.metadata`` (no re-serialization) so job
    ``result_json`` matches the analysis call exactly.
    Omitted when ``None`` for backward compatibility.
    """
    out: dict[str, Any] = {
        RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT: build_visual_reference_context(
            analysis_context, provider_metadata
        ),
    }
    if prompt_composition is not None:
        if find_non_json_serializable_path(prompt_composition) is None:
            out[RUN_METADATA_KEY_PROMPT_COMPOSITION] = prompt_composition
        else:
            safe_pc = make_json_safe_for_execution_log(prompt_composition)
            if isinstance(safe_pc, dict):
                out[RUN_METADATA_KEY_PROMPT_COMPOSITION] = safe_pc
    if llm_cost_snapshot is not None:
        out[RUN_METADATA_KEY_LLM_COST_SNAPSHOT] = llm_cost_snapshot
    return out
