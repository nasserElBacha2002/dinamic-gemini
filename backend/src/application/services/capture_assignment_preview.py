"""Deterministic capture → position preview (Sprint 3; no SourceAsset)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Sequence

from src.domain.capture.entities import (
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
)
from src.domain.positions.entities import Position, PositionStatus


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


def adjusted_effective_time(
    effective: datetime | None,
    clock_offset_seconds: int,
) -> datetime | None:
    if effective is None:
        return None
    return _utc(effective) + timedelta(seconds=int(clock_offset_seconds))


@dataclass(frozen=True)
class ItemPreviewOutcome:
    assignment_status: CaptureSessionItemAssignmentStatus
    assignment_reason: str
    adjusted_capture_time: datetime | None
    preview_target_position_id: str | None


def compute_item_preview_outcomes(
    *,
    items: Sequence[CaptureSessionItem],
    positions: Sequence[Position],
    clock_offset_seconds: int,
) -> Dict[str, ItemPreviewOutcome]:
    """Map item id → preview row for **imported** items only (others left to caller)."""
    out: Dict[str, ItemPreviewOutcome] = {}
    eligible = [i for i in items if i.import_status == CaptureSessionItemImportStatus.IMPORTED]
    slots = sorted(
        (p for p in positions if p.status != PositionStatus.DELETED),
        key=lambda p: ((p.corrected_position_code or "").lower(), p.id),
    )
    key_items: List[CaptureSessionItem] = []
    for i in eligible:
        adj = adjusted_effective_time(i.effective_capture_time, clock_offset_seconds)
        if adj is None:
            out[i.id] = ItemPreviewOutcome(
                assignment_status=CaptureSessionItemAssignmentStatus.UNASSIGNED,
                assignment_reason="preview:missing_effective_capture_time",
                adjusted_capture_time=None,
                preview_target_position_id=None,
            )
        else:
            key_items.append(i)

    by_adj: dict[datetime, List[CaptureSessionItem]] = defaultdict(list)
    for i in key_items:
        adj = adjusted_effective_time(i.effective_capture_time, clock_offset_seconds)
        assert adj is not None
        by_adj[adj].append(i)

    conflict_ids: set[str] = set()
    for adj, group in by_adj.items():
        if len(group) > 1:
            for i in group:
                conflict_ids.add(i.id)
                out[i.id] = ItemPreviewOutcome(
                    assignment_status=CaptureSessionItemAssignmentStatus.CONFLICT,
                    assignment_reason="preview:duplicate_adjusted_capture_time",
                    adjusted_capture_time=adj,
                    preview_target_position_id=None,
                )

    unique = [i for i in key_items if i.id not in conflict_ids]
    unique.sort(
        key=lambda i: (
            adjusted_effective_time(i.effective_capture_time, clock_offset_seconds),
            i.id,
        )
    )
    for idx, i in enumerate(unique):
        adj = adjusted_effective_time(i.effective_capture_time, clock_offset_seconds)
        assert adj is not None
        if idx < len(slots):
            pos = slots[idx]
            out[i.id] = ItemPreviewOutcome(
                assignment_status=CaptureSessionItemAssignmentStatus.PROPOSED,
                assignment_reason=f"preview:ordered_position_slot:index={idx};position_id={pos.id}",
                adjusted_capture_time=adj,
                preview_target_position_id=pos.id,
            )
        else:
            out[i.id] = ItemPreviewOutcome(
                assignment_status=CaptureSessionItemAssignmentStatus.UNASSIGNED,
                assignment_reason="preview:no_position_slot",
                adjusted_capture_time=adj,
                preview_target_position_id=None,
            )
    return out

