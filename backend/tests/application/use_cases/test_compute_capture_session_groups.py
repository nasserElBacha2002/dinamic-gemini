"""Unit tests for G3 temporal grouping (time-gap segmentation)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.application.errors import (
    CaptureSessionGroupingNotAllowedError,
    CaptureSessionNoItemsForGroupingError,
)
from src.application.use_cases.compute_capture_session_groups import ComputeCaptureSessionGroupsUseCase
from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)
from src.infrastructure.repositories.memory_capture_session_group_repository import (
    MemoryCaptureSessionGroupRepository,
)
from src.infrastructure.repositories.memory_capture_session_item_repository import MemoryCaptureSessionItemRepository
from src.infrastructure.repositories.memory_capture_session_repository import MemoryCaptureSessionRepository

UTC = timezone.utc


class _FixedClock:
    def __init__(self, t: datetime) -> None:
        self._t = t

    def now(self) -> datetime:
        return self._t


def _session(
    *,
    session_id: str,
    inventory_id: str,
    closed: bool = True,
    status: CaptureSessionStatus = CaptureSessionStatus.READY_FOR_REVIEW,
) -> CaptureSession:
    now = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
    return CaptureSession(
        id=session_id,
        inventory_id=inventory_id,
        aisle_id=None,
        status=status,
        created_at=now,
        updated_at=now,
        opened_at=now,
        closed_at=now if closed else None,
        clock_offset_seconds=0,
    )


def _imported_item(
    *,
    item_id: str,
    session_id: str,
    effective: datetime,
    adjusted: datetime | None = None,
    updated_at: datetime | None = None,
) -> CaptureSessionItem:
    u = updated_at or datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    return CaptureSessionItem(
        id=item_id,
        session_id=session_id,
        staging_storage_key=f"capture/staging/{item_id}",
        import_status=CaptureSessionItemImportStatus.IMPORTED,
        assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
        updated_at=u,
        effective_capture_time=effective,
        adjusted_capture_time=adjusted,
        original_filename=f"{item_id}.jpg",
    )


@pytest.fixture
def grouping_ctx() -> tuple[
    MemoryCaptureSessionRepository,
    MemoryCaptureSessionItemRepository,
    MemoryCaptureSessionGroupRepository,
    ComputeCaptureSessionGroupsUseCase,
]:
    sr = MemoryCaptureSessionRepository()
    ir = MemoryCaptureSessionItemRepository()
    gr = MemoryCaptureSessionGroupRepository(ir)
    clock = _FixedClock(datetime(2025, 1, 2, 15, 0, 0, tzinfo=UTC))
    uc = ComputeCaptureSessionGroupsUseCase(
        session_repo=sr,
        item_repo=ir,
        group_repo=gr,
        clock=clock,
        max_time_gap_seconds=60,
    )
    return sr, ir, gr, uc


def test_single_group_when_gap_within_threshold(grouping_ctx) -> None:
    sr, ir, _gr, uc = grouping_ctx
    inv, sid = "inv-1", "sess-1"
    sr.save(_session(session_id=sid, inventory_id=inv))
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    ir.save(_imported_item(item_id="a", session_id=sid, effective=t0))
    ir.save(_imported_item(item_id="b", session_id=sid, effective=t0 + timedelta(seconds=30)))

    summaries = uc.execute(inventory_id=inv, session_id=sid)
    assert len(summaries) == 1
    assert summaries[0].item_count == 2
    assert summaries[0].group_index == 1
    grouped = [i for i in ir.list_by_session(sid) if i.group_id is not None]
    assert len(grouped) == 2
    assert grouped[0].group_id == grouped[1].group_id


def test_multiple_groups_when_gap_exceeds_threshold(grouping_ctx) -> None:
    sr, ir, _gr, uc = grouping_ctx
    inv, sid = "inv-1", "sess-1"
    sr.save(_session(session_id=sid, inventory_id=inv))
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    ir.save(_imported_item(item_id="a", session_id=sid, effective=t0))
    ir.save(_imported_item(item_id="b", session_id=sid, effective=t0 + timedelta(seconds=120)))

    summaries = uc.execute(inventory_id=inv, session_id=sid)
    assert len(summaries) == 2
    assert [s.item_count for s in summaries] == [1, 1]
    assert summaries[0].group_index == 1
    assert summaries[1].group_index == 2


def test_gap_equal_to_threshold_stays_one_group(grouping_ctx) -> None:
    sr, ir, _gr, uc = grouping_ctx
    inv, sid = "inv-1", "sess-1"
    sr.save(_session(session_id=sid, inventory_id=inv))
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    ir.save(_imported_item(item_id="a", session_id=sid, effective=t0))
    ir.save(_imported_item(item_id="b", session_id=sid, effective=t0 + timedelta(seconds=60)))

    summaries = uc.execute(inventory_id=inv, session_id=sid)
    assert len(summaries) == 1
    assert summaries[0].item_count == 2


def test_sort_uses_adjusted_capture_time_when_present(grouping_ctx) -> None:
    sr, ir, _gr, uc = grouping_ctx
    inv, sid = "inv-1", "sess-1"
    sr.save(_session(session_id=sid, inventory_id=inv))
    t_base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    # Effective times would suggest b before a; adjusted flips order to a then b within 30s.
    ir.save(
        _imported_item(
            item_id="a",
            session_id=sid,
            effective=t_base + timedelta(minutes=10),
            adjusted=t_base,
        )
    )
    ir.save(
        _imported_item(
            item_id="b",
            session_id=sid,
            effective=t_base + timedelta(minutes=5),
            adjusted=t_base + timedelta(seconds=30),
        )
    )

    summaries = uc.execute(inventory_id=inv, session_id=sid)
    assert len(summaries) == 1
    assert summaries[0].item_count == 2


def test_items_without_effective_time_stay_ungrouped(grouping_ctx) -> None:
    sr, ir, _gr, uc = grouping_ctx
    inv, sid = "inv-1", "sess-1"
    sr.save(_session(session_id=sid, inventory_id=inv))
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    ir.save(_imported_item(item_id="a", session_id=sid, effective=t0))
    u = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    ir.save(
        CaptureSessionItem(
            id="no-time",
            session_id=sid,
            staging_storage_key="capture/staging/no-time",
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=u,
            effective_capture_time=None,
            original_filename="no-time.jpg",
        )
    )

    summaries = uc.execute(inventory_id=inv, session_id=sid)
    assert len(summaries) == 1
    assert summaries[0].item_count == 1
    no_time = ir.get_by_id("no-time")
    assert no_time is not None
    assert no_time.group_id is None


def test_non_imported_items_excluded_from_clusters(grouping_ctx) -> None:
    sr, ir, _gr, uc = grouping_ctx
    inv, sid = "inv-1", "sess-1"
    sr.save(_session(session_id=sid, inventory_id=inv))
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    ir.save(_imported_item(item_id="a", session_id=sid, effective=t0))
    u = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    ir.save(
        CaptureSessionItem(
            id="pending",
            session_id=sid,
            staging_storage_key="capture/staging/pending",
            import_status=CaptureSessionItemImportStatus.PENDING_IMPORT,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=u,
            effective_capture_time=t0,
            original_filename="pending.jpg",
        )
    )

    summaries = uc.execute(inventory_id=inv, session_id=sid)
    assert len(summaries) == 1
    assert summaries[0].item_count == 1
    assert ir.get_by_id("pending") is not None
    assert ir.get_by_id("pending").group_id is None


def test_idempotent_recompute(grouping_ctx) -> None:
    sr, ir, _gr, uc = grouping_ctx
    inv, sid = "inv-1", "sess-1"
    sr.save(_session(session_id=sid, inventory_id=inv))
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    ir.save(_imported_item(item_id="a", session_id=sid, effective=t0))
    ir.save(_imported_item(item_id="b", session_id=sid, effective=t0 + timedelta(seconds=120)))

    first = uc.execute(inventory_id=inv, session_id=sid)
    second = uc.execute(inventory_id=inv, session_id=sid)
    assert len(first) == len(second) == 2
    assert [s.item_count for s in first] == [s.item_count for s in second]
    gids_run2 = {i.group_id for i in ir.list_by_session(sid) if i.group_id}
    assert len(gids_run2) == 2


def test_open_session_raises_not_allowed(grouping_ctx) -> None:
    sr, ir, _gr, uc = grouping_ctx
    inv, sid = "inv-1", "sess-1"
    s = _session(session_id=sid, inventory_id=inv, closed=False, status=CaptureSessionStatus.DRAFT)
    sr.save(s)
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    ir.save(_imported_item(item_id="a", session_id=sid, effective=t0))

    with pytest.raises(CaptureSessionGroupingNotAllowedError):
        uc.execute(inventory_id=inv, session_id=sid)


def test_no_qualifying_items_raises(grouping_ctx) -> None:
    sr, ir, _gr, uc = grouping_ctx
    inv, sid = "inv-1", "sess-1"
    sr.save(_session(session_id=sid, inventory_id=inv))
    u = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    ir.save(
        CaptureSessionItem(
            id="pending",
            session_id=sid,
            staging_storage_key="capture/staging/pending",
            import_status=CaptureSessionItemImportStatus.PENDING_IMPORT,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=u,
            original_filename="pending.jpg",
        )
    )

    with pytest.raises(CaptureSessionNoItemsForGroupingError):
        uc.execute(inventory_id=inv, session_id=sid)
