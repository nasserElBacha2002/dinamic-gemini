"""When GLOBAL_BATCH may call the external provider (after internal aisle pass)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.application.services.image_processing.global_fallback_merge_policy import (
    InternalAssetEvidence,
)

# Internal statuses that justify an aisle-level GLOBAL_BATCH call.
FALLBACK_ELIGIBLE_INTERNAL_STATUSES = frozenset(
    {
        "UNRECOGNIZED",
        "PENDING_MANUAL_REVIEW",
        "FAILED_TECHNICAL",
        "PENDING",
        "PROCESSING",
        None,
        "",
    }
)


@dataclass(frozen=True)
class GlobalFallbackEligibilityDecision:
    needs_fallback: bool
    reason: str
    total_assets: int
    resolved_internal: int
    eligible_count: int
    partial_or_unresolved: int


def evaluate_global_fallback_eligibility(
    evidence_by_asset: Mapping[str, InternalAssetEvidence],
) -> GlobalFallbackEligibilityDecision:
    """Decide whether to invoke GLOBAL_BATCH.

    Rule: if every asset is fully resolved internally, skip the provider.
    If at least one is eligible (unrecognized / partial / failed / pending),
    run GLOBAL_BATCH with **all** images for cross-image context.
    """
    total = len(evidence_by_asset)
    if total == 0:
        return GlobalFallbackEligibilityDecision(
            needs_fallback=False,
            reason="no_assets",
            total_assets=0,
            resolved_internal=0,
            eligible_count=0,
            partial_or_unresolved=0,
        )

    resolved = 0
    eligible = 0
    for ev in evidence_by_asset.values():
        if ev.resolved_internal and ev.internal_code and _qty_ok(ev.quantity):
            resolved += 1
            continue
        status = (ev.status or "").strip().upper() or None
        # Code present but missing quantity → partial, still eligible.
        if ev.internal_code and not _qty_ok(ev.quantity):
            eligible += 1
            continue
        if status in FALLBACK_ELIGIBLE_INTERNAL_STATUSES or status is None:
            eligible += 1
            continue
        if status == "RESOLVED" and not (
            ev.resolved_internal and ev.internal_code and _qty_ok(ev.quantity)
        ):
            eligible += 1
            continue
        # CANCELLED / other terminal non-eligible
        if status == "CANCELLED":
            continue
        eligible += 1

    if eligible == 0 and resolved == total:
        return GlobalFallbackEligibilityDecision(
            needs_fallback=False,
            reason="all_resolved_internal",
            total_assets=total,
            resolved_internal=resolved,
            eligible_count=0,
            partial_or_unresolved=0,
        )
    if eligible == 0:
        return GlobalFallbackEligibilityDecision(
            needs_fallback=False,
            reason="no_eligible_internal_states",
            total_assets=total,
            resolved_internal=resolved,
            eligible_count=0,
            partial_or_unresolved=total - resolved,
        )
    return GlobalFallbackEligibilityDecision(
        needs_fallback=True,
        reason="eligible_assets_present",
        total_assets=total,
        resolved_internal=resolved,
        eligible_count=eligible,
        partial_or_unresolved=total - resolved,
    )


def _qty_ok(quantity: float | None) -> bool:
    if quantity is None:
        return False
    try:
        return float(quantity) > 0
    except (TypeError, ValueError):
        return False
