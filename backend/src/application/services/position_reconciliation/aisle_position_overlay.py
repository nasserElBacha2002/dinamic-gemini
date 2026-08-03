"""Overlay Phase 4 aisle-position assignments onto operational position summaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.domain.position_reconciliation.entities import (
    AssignmentStatus,
    ProductPositionAssignment,
)


def aisle_position_names_by_result_id(
    assignments: Sequence[ProductPositionAssignment],
) -> dict[str, str]:
    """Map product result_id → human aisle position name for automatic assignments."""
    out: dict[str, str] = {}
    for row in assignments:
        if row.assignment_status is not AssignmentStatus.ASSIGNED_AUTOMATIC:
            continue
        name = (row.position_name_snapshot or "").strip()
        if not name:
            continue
        out[row.result_id] = name
    return out


def apply_aisle_position_to_summary(
    summary: Any,
    *,
    primary_product_id: str | None,
    names_by_result_id: Mapping[str, str],
) -> Any:
    """Replace synthetic CODE_SCAN position_code with the reconciled aisle label when present."""
    assigned = False
    code = getattr(summary, "position_code", None)
    if primary_product_id:
        name = names_by_result_id.get(primary_product_id)
        if name:
            code = name
            assigned = True
    updates = {
        "position_code": code if code is not None else getattr(summary, "position_code", ""),
        "aisle_position_assigned": assigned,
    }
    if hasattr(summary, "model_copy"):
        return summary.model_copy(update=updates)
    for key, value in updates.items():
        setattr(summary, key, value)
    return summary
