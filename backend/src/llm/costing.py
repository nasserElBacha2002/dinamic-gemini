"""
Provider-agnostic LLM usage/cost snapshot builder.

The snapshot is persisted with each run for auditability. To avoid overclaiming precision:
- ``total_tokens`` is kept only when reported by the provider payload.
- ambiguous accounting paths are explicitly marked with ``usage_dimension_ambiguous:*`` notes.
- ``pricing_snapshot.pricing_confidence`` distinguishes operator-approved catalog rows from embedded placeholders.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.llm.costing_helpers.capture_status import (
    total_cost_unavailable_reason as _total_cost_unavailable_reason,  # noqa: F401
)
from src.llm.costing_helpers.catalog import resolve_pricing_with_canonical
from src.llm.costing_helpers.coverage import (
    PricingCoverageIssue,
    validate_llm_pricing_coverage,
)
from src.llm.costing_helpers.snapshot_builder import (
    build_llm_cost_snapshot_impl as _build_llm_cost_snapshot_impl,
)
from src.llm.costing_helpers.usage_normalize import normalize_usage

__all__ = [
    "PricingCoverageIssue",
    "build_llm_cost_snapshot",
    "normalize_usage",
    "resolve_pricing_with_canonical",
    "validate_llm_pricing_coverage",
]


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_llm_cost_snapshot(
    *,
    provider: str,
    model: str | None,
    raw_usage: dict[str, Any] | None,
    settings: Any,
) -> dict[str, Any]:
    """
    Build the auditable usage + pricing + computed-cost snapshot for one LLM call.

    ``capture_status``:
    - ``unavailable``: no usage metadata, or no monetary subtotals can be derived.
    - ``partial``: at least one billable dimension was priced but another positive usage dimension
      lacks a catalog rate (``partial_total_cost`` sums priced lines only; ``total_cost`` is null).
    - ``estimated``: every positive billable dimension has a rate and ``total_cost`` is set, but
      ``usage_dimension_ambiguous:*`` or ``usage_assumption:*`` notes remain.
    - ``exact``: operator-approved catalog row matched, full pricing coverage for positive billable
      usage, no ambiguity or assumption notes, and ``total_cost`` is set.
    """
    return _build_llm_cost_snapshot_impl(
        provider=provider,
        model=model,
        raw_usage=raw_usage,
        settings=settings,
        captured_at_factory=_utc_iso_now,
    )
