"""G7 — derived operator-facing materialization state for a temporal capture group."""

from __future__ import annotations


def materialization_state_for_counts(
    *,
    assignment_status: str,
    imported_count: int,
    linked_imported_count: int,
) -> str:
    """Return ``unassigned`` | ``assigned`` | ``materialized`` | ``partially_materialized``.

    ``imported_count`` / ``linked_imported_count`` count only **imported** items in the group;
    ``linked_imported_count`` is how many of those have a non-empty ``linked_source_asset_id``.
    """
    st = (assignment_status or "").strip().lower()
    if st == "unassigned":
        return "unassigned"
    if imported_count <= 0:
        return "assigned"
    if linked_imported_count <= 0:
        return "assigned"
    if linked_imported_count >= imported_count:
        return "materialized"
    return "partially_materialized"
