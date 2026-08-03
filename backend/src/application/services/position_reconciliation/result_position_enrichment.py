"""Apply published Phase 4 assignment views onto position summaries (Phase 5)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.application.ports.client_position_label_repository import (
    ClientPositionLabelRepository,
)
from src.application.ports.manual_position_override_repository import (
    ManualPositionOverrideRepository,
)
from src.application.ports.position_reconciliation_repository import (
    PositionReconciliationRepository,
)
from src.application.ports.repositories import ProductRecordRepository
from src.application.services.display_primary_product import select_display_primary_product
from src.application.services.position_overrides.effective_position_reader import (
    EffectivePositionReader,
)
from src.application.services.position_reconciliation.published_assignment_read_model import (
    PositionReadAvailability,
    PublishedPositionAssignmentView,
)
from src.application.services.position_reconciliation.published_assignment_reader import (
    PublishedPositionAssignmentReader,
)
from src.domain.position_overrides.entities import EffectiveProductPositionView
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord


def partition_key_from_assignment_view(
    view: PublishedPositionAssignmentView | EffectiveProductPositionView | None,
) -> str:
    """Stable SKU-consolidation partition from published Phase 4 assignment fields."""
    if view is None:
        return ""
    if isinstance(view, EffectiveProductPositionView):
        label_id = (
            view.effective_position.id if view.effective_position else None
        ) or ""
        reason = (
            view.manual_override.reason_code.value if view.manual_override else ""
        )
        return (
            f"{label_id}|{view.effective_source.value}|"
            f"{view.effective_status}|{reason}"
        )
    label_id = (view.position.id if view.position else None) or ""
    status = (view.assignment_status or "").strip()
    reason = (view.assignment_reason or "").strip()
    return f"{label_id}|{status}|{reason}"


def build_partition_key_by_position_id(
    positions: Sequence[Position],
    *,
    product_record_repo: ProductRecordRepository,
    reconciliation_repo: PositionReconciliationRepository | None,
    job_id: str | None,
    enrichment_enabled: bool,
    override_repo: ManualPositionOverrideRepository | None = None,
    label_repo: ClientPositionLabelRepository | None = None,
) -> dict[str, str]:
    """Map each position id to a partition key for SKU merge (Phase 5)."""
    if not enrichment_enabled or reconciliation_repo is None or not job_id or not positions:
        return {}
    batch = product_record_repo.list_by_position_ids([p.id for p in positions])
    by_position: dict[str, list] = {}
    for pr in batch:
        by_position.setdefault(pr.position_id, []).append(pr)
    primary_by_position: dict[str, ProductRecord | None] = {}
    result_ids: list[str] = []
    for p in positions:
        primary = select_display_primary_product(by_position.get(p.id, ()))
        primary_by_position[p.id] = primary
        if primary is not None:
            result_ids.append(primary.id)
    reader = PublishedPositionAssignmentReader(
        reconciliation_repo=reconciliation_repo,
        enrichment_enabled=True,
    )
    views = (
        EffectivePositionReader(
            automatic_reader=reader,
            override_repo=override_repo,
            label_repo=label_repo,
        ).load_for_job(job_id, result_ids=result_ids)
        if override_repo is not None
        else reader.load_for_job(job_id, result_ids=result_ids)
    )
    partition_keys: dict[str, str] = {}
    for position in positions:
        primary = primary_by_position[position.id]
        view = views.get(primary.id) if primary is not None else None
        partition_keys[position.id] = partition_key_from_assignment_view(view)
    return partition_keys


def view_to_position_payload(
    view: PublishedPositionAssignmentView | EffectiveProductPositionView,
) -> dict[str, Any] | None:
    """Nested ``position`` object for API/export. Null when unassigned / unavailable."""
    if isinstance(view, EffectiveProductPositionView):
        if view.effective_position is None:
            return None
        return {
            "id": view.effective_position.id,
            "name": view.effective_position.name,
        }
    if view.availability is PositionReadAvailability.FEATURE_DISABLED:
        return None
    if view.position is None or not (view.position.name or view.position.id):
        return None
    return {
        "id": view.position.id,
        "name": view.position.name,
    }


def view_to_position_assignment_payload(
    view: PublishedPositionAssignmentView | EffectiveProductPositionView,
) -> dict[str, Any] | None:
    """Nested ``position_assignment`` object. Null when feature disabled."""
    if isinstance(view, EffectiveProductPositionView):
        manual = view.manual_override
        return {
            "status": view.effective_status,
            "source": view.effective_source.value,
            "reason": manual.reason_code.value if manual else None,
            "reconciliation_status": view.reconciliation_status,
            "automatic_position": (
                {
                    "id": view.automatic_position.id,
                    "name": view.automatic_position.name,
                }
                if view.automatic_position
                else None
            ),
            "automatic_assignment_status": view.automatic_assignment_status,
            "manual_override": (
                {
                    "id": manual.id,
                    "action": manual.override_action.value,
                    "reason_code": manual.reason_code.value,
                    "reason_text": manual.reason_text,
                    "created_by_user_id": manual.created_by_user_id,
                    "created_at": manual.created_at,
                    "version": manual.version,
                }
                if manual
                else None
            ),
            "warnings": list(view.warnings),
            "version": view.version,
        }
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
    views_by_result_id: dict[
        str, PublishedPositionAssignmentView | EffectiveProductPositionView
    ],
) -> Any:
    """Enrich a PositionSummary-like object from the Phase 5 read model.

    Also mirrors aisle name onto ``position_code`` / ``aisle_position_assigned`` for
    backward-compatible clients (does not invent position from detections).
    """
    view: PublishedPositionAssignmentView | EffectiveProductPositionView | None = None
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
    view: PublishedPositionAssignmentView | EffectiveProductPositionView | None,
    *,
    with_position: bool | None = None,
    position_label_id: str | None = None,
    position_assignment_status: str | None = None,
    position_name: str | None = None,
    unassigned_reason: str | None = None,
    position_source: str | None = None,
    has_manual_override: bool | None = None,
    manual_reason_code: str | None = None,
    manual_position_invalidated: bool | None = None,
    automatic_changed_after_override: bool | None = None,
) -> bool:
    """Return True when the view satisfies optional Phase 5 list filters."""
    if isinstance(view, EffectiveProductPositionView):
        effective = view.effective_position
        if with_position is True and (effective is None or not effective.name):
            return False
        if with_position is False and effective is not None and effective.name:
            return False
        if position_label_id and (
            (effective.id if effective else "") != position_label_id.strip()
        ):
            return False
        if position_name and (
            ((effective.name or "") if effective else "").strip().lower()
            != position_name.strip().lower()
        ):
            return False
        if (
            position_assignment_status
            and view.effective_status != position_assignment_status.strip()
        ):
            return False
        if unassigned_reason and view.effective_status != unassigned_reason.strip():
            return False
        if position_source and view.effective_source.value != position_source.strip().upper():
            return False
        if (
            has_manual_override is not None
            and (view.manual_override is not None) is not has_manual_override
        ):
            return False
        if manual_reason_code and (
            view.manual_override is None
            or view.manual_override.reason_code.value != manual_reason_code.strip().upper()
        ):
            return False
        if (
            manual_position_invalidated is not None
            and ("MANUAL_POSITION_INVALIDATED" in view.warnings)
            is not manual_position_invalidated
        ):
            return False
        if (
            automatic_changed_after_override is not None
            and ("AUTOMATIC_CHANGED_AFTER_OVERRIDE" in view.warnings)
            is not automatic_changed_after_override
        ):
            return False
        return True
    if position_source:
        actual_source = (
            "AUTOMATIC"
            if view is not None and view.position is not None
            else "NONE"
        )
        if actual_source != position_source.strip().upper():
            return False
    if has_manual_override is True or manual_reason_code:
        return False
    if manual_position_invalidated is True or automatic_changed_after_override is True:
        return False
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
    view: PublishedPositionAssignmentView | EffectiveProductPositionView | None,
) -> dict[str, Any]:
    """Flat export columns from the same read model used by the API."""
    if isinstance(view, EffectiveProductPositionView):
        manual = view.manual_override
        return {
            "position_label_id": (
                view.effective_position.id if view.effective_position else None
            ),
            "position_name": (
                view.effective_position.name if view.effective_position else None
            ),
            "position_assignment_status": view.effective_status,
            "position_assignment_reason": (
                manual.reason_code.value if manual else None
            ),
            "position_assignment_source": view.effective_source.value,
            "reconciliation_id": (
                manual.automatic_reconciliation_id if manual else None
            ),
            "reconciliation_version": None,
            "sequence_number": None,
            "source_asset_id": manual.source_asset_id if manual else None,
            "effective_position_label_id": (
                view.effective_position.id if view.effective_position else None
            ),
            "effective_position_name": (
                view.effective_position.name if view.effective_position else None
            ),
            "effective_position_source": view.effective_source.value,
            "effective_position_status": view.effective_status,
            "automatic_position_label_id": (
                view.automatic_position.id if view.automatic_position else None
            ),
            "automatic_position_name": (
                view.automatic_position.name if view.automatic_position else None
            ),
            "manual_override_id": manual.id if manual else None,
            "manual_override_action": (
                manual.override_action.value if manual else None
            ),
            "manual_override_reason_code": (
                manual.reason_code.value if manual else None
            ),
            "manual_override_reason_text": manual.reason_text if manual else None,
            "manual_override_created_by": (
                manual.created_by_user_id if manual else None
            ),
            "manual_override_created_at": manual.created_at if manual else None,
            "manual_override_version": manual.version if manual else None,
        }
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
