"""Sprint 3 — deterministic assignment preview outcomes."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import src.application.services.capture_assignment_preview as capture_assignment_preview
from src.application.services.capture_assignment_preview import (
    adjusted_effective_time,
    compute_item_preview_outcomes,
)
from src.domain.capture.entities import (
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
)
from src.domain.positions.entities import Position, PositionStatus


def test_preview_module_documents_position_slots_as_mvp_heuristic() -> None:
    """Lock Sprint 3 intent: preview uses persisted ``Position`` rows as ordinal slots, not optical truth."""
    doc = capture_assignment_preview.__doc__ or ""
    assert "Position" in doc
    assert "MVP heuristic" in doc
    assert "review seed" in doc


def _item(
    iid: str,
    sid: str,
    *,
    eff: datetime | None,
    offset: int = 0,
) -> CaptureSessionItem:
    return CaptureSessionItem(
        id=iid,
        session_id=sid,
        staging_storage_key="k",
        import_status=CaptureSessionItemImportStatus.IMPORTED,
        assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
        updated_at=datetime.now(timezone.utc),
        effective_capture_time=eff,
        content_hash="h" + iid[:6],
    )


def test_adjusted_time_applies_offset_seconds() -> None:
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    adj = adjusted_effective_time(base, 120)
    assert adj == datetime(2026, 1, 1, 12, 2, 0, tzinfo=timezone.utc)


def test_duplicate_adjusted_time_marks_conflict() -> None:
    sid = "sess-1"
    t = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    items = (
        _item("a", sid, eff=t),
        _item("b", sid, eff=t),
    )
    positions = (
        Position(
            id="p1",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=t,
            updated_at=t,
            corrected_position_code="Z1",
        ),
    )
    out = compute_item_preview_outcomes(items=items, positions=positions, clock_offset_seconds=0)
    assert out["a"].assignment_status == CaptureSessionItemAssignmentStatus.CONFLICT
    assert out["b"].assignment_status == CaptureSessionItemAssignmentStatus.CONFLICT


def test_ordered_slots_deterministic() -> None:
    sid = "sess-2"
    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    items = (
        _item("i2", sid, eff=t1),
        _item("i1", sid, eff=t0),
    )
    positions = (
        Position(
            id=str(uuid4()),
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=t0,
            updated_at=t0,
            corrected_position_code="B",
        ),
        Position(
            id=str(uuid4()),
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=t0,
            updated_at=t0,
            corrected_position_code="A",
        ),
    )
    out = compute_item_preview_outcomes(items=items, positions=positions, clock_offset_seconds=0)
    # Sorted items: i1 (t0) then i2 (t1); sorted positions: A then B
    assert out["i1"].assignment_status == CaptureSessionItemAssignmentStatus.PROPOSED
    assert out["i2"].assignment_status == CaptureSessionItemAssignmentStatus.PROPOSED
    assert "position_id=" in (out["i1"].assignment_reason or "")


def test_excess_items_unassigned() -> None:
    sid = "sess-3"
    t = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    items = tuple(
        CaptureSessionItem(
            id=f"x{i}",
            session_id=sid,
            staging_storage_key="k",
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=datetime.now(timezone.utc),
            effective_capture_time=datetime(2026, 1, i, 10, 0, 0, tzinfo=timezone.utc),
            content_hash=f"hash-{i}-{uuid4().hex[:8]}",
        )
        for i in range(1, 4)
    )
    positions = (
        Position(
            id="only",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=t,
            updated_at=t,
            corrected_position_code="1",
        ),
    )
    out = compute_item_preview_outcomes(items=items, positions=positions, clock_offset_seconds=0)
    proposed = [
        k
        for k, v in out.items()
        if v.assignment_status == CaptureSessionItemAssignmentStatus.PROPOSED
    ]
    unassigned = [
        k
        for k, v in out.items()
        if v.assignment_status == CaptureSessionItemAssignmentStatus.UNASSIGNED
    ]
    assert len(proposed) == 1
    assert len(unassigned) == 2
