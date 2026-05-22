"""Parse persisted ``llm_cost_snapshot`` from job ``result_json`` for analytics aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from src.application.services.llm_cost_snapshot_public import llm_cost_snapshot_public_dict

CaptureStatus = Literal["exact", "estimated", "partial", "unavailable", "missing"]

_VALID_CAPTURE_STATUSES: frozenset[str] = frozenset(
    {"exact", "estimated", "partial", "unavailable", "missing"}
)


@dataclass(frozen=True)
class ParsedCostSnapshot:
    capture_status: CaptureStatus
    cost_amount: Decimal | None
    provider_name: str | None
    model_name: str | None
    has_snapshot: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _strip(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _parse_non_negative_cost(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value < 0:
        return None
    return value


def _normalize_capture_status(raw: str | None, *, has_snapshot: bool) -> CaptureStatus:
    if not has_snapshot:
        return "missing"
    status = (raw or "").strip().lower()
    if status in _VALID_CAPTURE_STATUSES and status != "missing":
        return status  # type: ignore[return-value]
    if status:
        return "unavailable"
    return "unavailable"


def parse_llm_cost_snapshot(result_json: dict[str, Any] | None) -> ParsedCostSnapshot:
    """Parse one job's persisted cost snapshot without raising on malformed payloads."""
    warnings: list[str] = []
    if not isinstance(result_json, dict):
        return ParsedCostSnapshot(
            capture_status="missing",
            cost_amount=None,
            provider_name=None,
            model_name=None,
            has_snapshot=False,
        )

    public = llm_cost_snapshot_public_dict(result_json)
    if public is None:
        return ParsedCostSnapshot(
            capture_status="missing",
            cost_amount=None,
            provider_name=None,
            model_name=None,
            has_snapshot=False,
        )

    capture_status = _normalize_capture_status(_strip(public.get("capture_status")), has_snapshot=True)
    computed = public.get("computed_cost")
    total_raw = computed.get("total_cost") if isinstance(computed, dict) else None
    cost_amount = _parse_non_negative_cost(total_raw)
    if total_raw is not None and cost_amount is None:
        warnings.append("invalid_computed_cost")

    provider_name = _strip(public.get("provider"))
    model_name = _strip(public.get("model"))

    return ParsedCostSnapshot(
        capture_status=capture_status,
        cost_amount=cost_amount,
        provider_name=provider_name,
        model_name=model_name,
        has_snapshot=True,
        warnings=tuple(warnings),
    )
