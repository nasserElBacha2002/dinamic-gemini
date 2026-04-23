"""G3 — deterministic temporal grouping of capture session items (time-gap segmentation)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Sequence
from uuid import uuid4

from src.application.errors import (
    CaptureSessionGroupingNotAllowedError,
    CaptureSessionNoItemsForGroupingError,
    CaptureSessionNotFoundError,
)
from src.application.ports.capture_repositories import (
    CaptureSessionGroupRepository,
    CaptureSessionGroupSummary,
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.clock import Clock
from src.domain.capture.entities import (
    CaptureSessionGroup,
    CaptureSessionItem,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
    CaptureSession,
)

logger = logging.getLogger(__name__)

TIME_GAP_ALGORITHM_VERSION = "time_gap_v1"


def _sort_key_time(item: CaptureSessionItem):
    return item.adjusted_capture_time or item.effective_capture_time


class ComputeCaptureSessionGroupsUseCase:
    def __init__(
        self,
        *,
        session_repo: CaptureSessionRepository,
        item_repo: CaptureSessionItemRepository,
        group_repo: CaptureSessionGroupRepository,
        clock: Clock,
        max_time_gap_seconds: int,
    ) -> None:
        self._session_repo = session_repo
        self._item_repo = item_repo
        self._group_repo = group_repo
        self._clock = clock
        self._max_gap = max(1, int(max_time_gap_seconds))

    def execute(self, *, inventory_id: str, session_id: str) -> Sequence[CaptureSessionGroupSummary]:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError("Capture session not found for this inventory and aisle.")
        self._ensure_grouping_allowed(session)

        all_items = list(self._item_repo.list_by_session(session_id))
        if not all_items:
            raise CaptureSessionNoItemsForGroupingError("This capture session has no items to group.")

        qualifying = [
            i
            for i in all_items
            if i.import_status == CaptureSessionItemImportStatus.IMPORTED and i.effective_capture_time is not None
        ]
        if not qualifying:
            raise CaptureSessionNoItemsForGroupingError(
                "No imported items with effective_capture_time are available for temporal grouping."
            )

        qualifying.sort(key=lambda i: (_sort_key_time(i) or i.updated_at, i.id))

        clusters = self._cluster_by_gap(qualifying)
        now = self._clock.now()

        self._clear_previous_assignments(session_id, all_items, now)

        summaries: List[CaptureSessionGroupSummary] = []
        for idx, cluster in enumerate(clusters, start=1):
            gid = str(uuid4())
            group = CaptureSessionGroup(
                id=gid,
                session_id=session_id,
                group_index=idx,
                created_at=now,
                algorithm_version=TIME_GAP_ALGORITHM_VERSION,
            )
            self._group_repo.insert(group)
            times: list = []
            for item in cluster:
                item.group_id = gid
                item.updated_at = now
                self._item_repo.save(item)
                t = _sort_key_time(item)
                if t is not None:
                    times.append(t)
            if not times:
                continue
            summaries.append(
                CaptureSessionGroupSummary(
                    group_id=gid,
                    group_index=idx,
                    item_count=len(cluster),
                    start_time=min(times),
                    end_time=max(times),
                )
            )
        logger.info(
            "capture session groups computed session_id=%s groups=%s algorithm=%s",
            session_id,
            len(summaries),
            TIME_GAP_ALGORITHM_VERSION,
        )
        return tuple(summaries)

    def _ensure_grouping_allowed(self, session: CaptureSession) -> None:
        if session.closed_at is None:
            raise CaptureSessionGroupingNotAllowedError(
                "Temporal grouping is only allowed after the capture session is closed."
            )
        if session.status in (
            CaptureSessionStatus.CANCELLED,
            CaptureSessionStatus.FAILED,
            CaptureSessionStatus.CONFIRMED,
        ):
            raise CaptureSessionGroupingNotAllowedError(
                "Temporal grouping is not allowed for cancelled, failed, or confirmed capture sessions."
            )

    def _cluster_by_gap(self, sorted_items: Sequence[CaptureSessionItem]) -> List[List[CaptureSessionItem]]:
        if not sorted_items:
            return []
        clusters: List[List[CaptureSessionItem]] = []
        cur: List[CaptureSessionItem] = [sorted_items[0]]
        for i in range(1, len(sorted_items)):
            prev = sorted_items[i - 1]
            item = sorted_items[i]
            t_prev = _sort_key_time(prev)
            t_curr = _sort_key_time(item)
            if t_prev is None or t_curr is None:
                cur.append(item)
                continue
            gap = (t_curr - t_prev).total_seconds()
            if gap > self._max_gap:
                clusters.append(cur)
                cur = [item]
            else:
                cur.append(item)
        clusters.append(cur)
        return clusters

    def _clear_previous_assignments(
        self, session_id: str, all_items: Sequence[CaptureSessionItem], now: datetime
    ) -> None:
        for item in all_items:
            if item.group_id is not None:
                item.group_id = None
                item.updated_at = now
                self._item_repo.save(item)
        self._group_repo.delete_all_for_session(session_id)
