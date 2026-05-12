"""Parse ``visual_reference_context`` from persisted job ``result_json`` (operator-facing summary)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Persisted ``job.result_json`` key for visual reference summary blocks.
# Must stay aligned with ``src.pipeline.run_metadata.RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT``.
VISUAL_REFERENCE_CONTEXT_RESULT_JSON_KEY = "visual_reference_context"


def _coerce_non_negative_int(value: Any) -> int:
    """Best-effort int parsing for persisted metadata; invalid values fall back to 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        if value != value:
            return 0
        return max(0, int(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0
        try:
            return max(0, int(stripped))
        except ValueError:
            return 0
    return 0


@dataclass(frozen=True)
class ReferenceUsageFields:
    """Neutral DTO before mapping to API :class:`ReferenceUsageSummary`."""

    resolved: bool
    resolved_count: int
    provider_consumed: bool
    provider_consumed_count: int
    reference_ids: list[str]
    resolution_error: str | None


def parse_reference_usage_from_result_json(result_json: Any) -> ReferenceUsageFields | None:
    """Map persisted ``result_json`` into compact reference-usage fields, or ``None`` if absent."""
    if not isinstance(result_json, dict):
        return None
    raw = result_json.get(VISUAL_REFERENCE_CONTEXT_RESULT_JSON_KEY)
    if not isinstance(raw, dict):
        return None

    reference_ids: list[str] = []
    reference_ids_raw = raw.get("reference_ids")
    if isinstance(reference_ids_raw, list):
        seen: set[str] = set()
        for item in reference_ids_raw:
            if not isinstance(item, str):
                continue
            ref_id = item.strip()
            if not ref_id or ref_id in seen:
                continue
            seen.add(ref_id)
            reference_ids.append(ref_id)

    resolved_count = _coerce_non_negative_int(raw.get("resolved_count"))
    provider_consumed_count = _coerce_non_negative_int(raw.get("provider_consumed_count"))
    resolution_error = raw.get("resolution_error")
    return ReferenceUsageFields(
        resolved=bool(raw.get("resolved")),
        resolved_count=max(0, resolved_count),
        provider_consumed=bool(raw.get("provider_consumed")),
        provider_consumed_count=max(0, provider_consumed_count),
        reference_ids=reference_ids,
        resolution_error=resolution_error[:2048] if isinstance(resolution_error, str) else None,
    )
