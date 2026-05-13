"""Serialize persisted ``llm_cost_snapshot`` for read-only API surfaces (auditability, job summaries).

Pricing data is **already persisted** on successful aisle jobs under ``job.result_json["llm_cost_snapshot"]``
(see ``V3JobExecutionStateService.mark_success`` and pipeline run metadata). Legacy or failed jobs may
omit it; callers should treat a ``None`` return as "no cost row for this execution".
"""

from __future__ import annotations

from typing import Any

from src.api.schemas.benchmark_schemas import LlmCostSnapshotResponse
from src.application.use_cases.benchmark_compare_support import (
    sanitize_llm_cost_snapshot_for_compare,
)


def llm_cost_snapshot_public_dict(result_json: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a JSON-serializable, redacted cost snapshot dict, or ``None`` if absent/invalid."""
    if not isinstance(result_json, dict):
        return None
    raw = result_json.get("llm_cost_snapshot")
    if not isinstance(raw, dict):
        return None
    sanitized: dict[str, object] = sanitize_llm_cost_snapshot_for_compare(raw)
    try:
        validated = LlmCostSnapshotResponse.model_validate(sanitized)
    except Exception:
        return None
    return validated.model_dump(mode="json")
