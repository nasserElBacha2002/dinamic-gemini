"""Apply published Phase 4 assignment views onto position summaries (Phase 5)."""

from __future__ import annotations

from typing import Any

from src.application.services.position_reconciliation.published_assignment_read_model import (
    PositionReadAvailability,
    PublishedPositionAssignmentView,
)


def view_to_position_payload(view: PublishedPositionAssignmentView) -> dict[str, Any] | None:
    """Nested ``position`` object for API/export. Null when unassigned / unavailable."""
    if view.availability is PositionReadAvailability.FEATURE_DISABLED:
        return None
    if view.position is None or not (view.position.name or view.position.id):
        return None
    return {
        "id": view.position.id,
        "name": view.position.name,
    }


def view_to_position_assignment_payload(
    view: PublishedPositionAssignmentView,
) -> dict[str, Any] | None:
    """Nested ``position_assignment`` object. Null when feature disabled."""
    if view.availability is PositionReadAvailability.FEATURE_DISABLED:
        return None
    return {
        "status": view.assignment_status,
        "source": view.assignment_source,
        "reason": view.assignment_reason,
        "reconciliation_id": view.reconciliation_id,
        "reconciliation_version": view.reconciliation_version,
        "reconciliation_status": view.reconciliation_status,
        "availability": view.availability.value,
        "sequence_number": view.sequence_number,
        "source_asset_id": view.source_asset_id,
    }


def apply_published_assignment_to_summary(
    summary: Any,
    *,
    primary_product_id: str | None,
    views_by_result_id: dict[str, PublishedPositionAssignmentView],
) -> Any:
    """Enrich a PositionSummary-like object from the Phase 5 read model.

    Also mirrors aisle name onto ``position_code`` / ``aisle_position_assigned`` for
    backward-compatible clients (does not invent position from detections).
    """
    view: PublishedPositionAssignmentView | None = None
    if primary_product_id:
        view = views_by_result_id.get(primary_product_id)

    position_payload = view_to_position_payload(view) if view else None
    assignment_payload = view_to_position_assignment_payload(view) if view else None

    assigned = bool(position_payload and position_payload.get("name"))
    code = getattr(summary, "position_code", None)
    if assigned and position_payload and position_payload.get("name"):
        code = position_payload["name"]

    updates = {
        "position_code": code if code is not None else getattr(summary, "position_code", ""),
        "aisle_position_assigned": assigned,
        "position": position_payload,
        "position_assignment": assignment_payload,
    }
    if hasattr(summary, "model_copy"):
        return summary.model_copy(update=updates)
    for key, value in updates.items():
        setattr(summary, key, value)
    return summary


def matches_position_filters(
    view: PublishedPositionAssignmentView | None,
    *,
    with_position: bool | None = None,
    position_label_id: str | None = None,
    position_assignment_status: str | None = None,
    position_name: str | None = None,
    unassigned_reason: str | None = None,
) -> bool:
    """Return True when the view satisfies optional Phase 5 list filters."""
    if with_position is True:
        if view is None or view.position is None or not view.position.name:
            return False
    if with_position is False:
        if view is not None and view.position is not None and view.position.name:
            return False

    if position_label_id:
        label = (view.position.id if view and view.position else None) or ""
        if label != position_label_id.strip():
            return False

    if position_name:
        name = (view.position.name if view and view.position else None) or ""
        if name.strip().lower() != position_name.strip().lower():
            return False

    if position_assignment_status:
        status = (view.assignment_status if view else None) or ""
        if status != position_assignment_status.strip():
            return False

    if unassigned_reason:
        reason = (view.assignment_reason if view else None) or ""
        status = (view.assignment_status if view else None) or ""
        needle = unassigned_reason.strip()
        if needle not in (reason, status):
            return False

    return True


def export_fields_from_view(
    view: PublishedPositionAssignmentView | None,
) -> dict[str, Any]:
    """Flat export columns from the same read model used by the API."""
    if view is None or view.availability is PositionReadAvailability.FEATURE_DISABLED:
        return {
            "position_label_id": None,
            "position_name": None,
            "position_assignment_status": None,
            "position_assignment_reason": None,
            "position_assignment_source": None,
            "reconciliation_id": None,
            "reconciliation_version": None,
            "sequence_number": None,
            "source_asset_id": None,
        }
    return {
        "position_label_id": view.position.id if view.position else None,
        "position_name": view.position.name if view.position else None,
        "position_assignment_status": view.assignment_status,
        "position_assignment_reason": view.assignment_reason,
        "position_assignment_source": view.assignment_source,
        "reconciliation_id": view.reconciliation_id,
        "reconciliation_version": view.reconciliation_version,
        "sequence_number": view.sequence_number,
        "source_asset_id": view.source_asset_id,
    }
