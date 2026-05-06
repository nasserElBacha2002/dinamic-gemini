"""G3 — deterministic temporal grouping of capture session items (time-gap segmentation)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
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
from src.application.services.capture_flow_observability import (
    LOG_OP_G3_COMPUTE_GROUPS,
    RESULT_SUCCESS,
    emit_capture_flow_event,
    get_capture_flow_metrics,
)
from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionGroup,
    CaptureSessionItem,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)

logger = logging.getLogger(__name__)

TIME_GAP_ALGORITHM_VERSION = "time_gap_v1"

# Same HTTP code ``CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING`` — distinct stable ``detail`` for product/FE (Option A).
_MSG_GROUPING_EMPTY_SESSION = (
    "This capture session has no items; add items before temporal grouping can run."
)
_MSG_GROUPING_NO_QUALIFYING_ITEMS = (
    "This capture session has items, but none are eligible for temporal grouping "
    "(requires imported items with effective_capture_time)."
)


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

    def execute(
        self, *, inventory_id: str, session_id: str
    ) -> Sequence[CaptureSessionGroupSummary]:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError(
                "Capture session not found for this inventory (session id does not match inventory scope)."
            )
        self._ensure_grouping_allowed(session)

        all_items = list(self._item_repo.list_by_session(session_id))
        if not all_items:
            raise CaptureSessionNoItemsForGroupingError(_MSG_GROUPING_EMPTY_SESSION)

        qualifying = [
            i
            for i in all_items
            if i.import_status == CaptureSessionItemImportStatus.IMPORTED
            and i.effective_capture_time is not None
        ]
        if not qualifying:
            raise CaptureSessionNoItemsForGroupingError(_MSG_GROUPING_NO_QUALIFYING_ITEMS)

        qualifying.sort(key=lambda i: (_sort_key_time(i) or i.updated_at, i.id))

        clusters = self._cluster_by_gap(qualifying)
        now = self._clock.now()

        self._clear_previous_assignments(session_id, all_items, now)

        summaries: list[CaptureSessionGroupSummary] = []
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
                    algorithm_version=TIME_GAP_ALGORITHM_VERSION,
                    materialization_state="unassigned",
                )
            )
        total_members = sum(s.item_count for s in summaries)
        get_capture_flow_metrics().record_g3_compute()
        emit_capture_flow_event(
            logger=logger,
            inventory_id=inventory_id,
            session_id=session_id,
            operation=LOG_OP_G3_COMPUTE_GROUPS,
            result_status=RESULT_SUCCESS,
            counts={
                "groups_created": len(summaries),
                "items_assigned_to_groups": total_members,
            },
            extra={"algorithm_version": TIME_GAP_ALGORITHM_VERSION},
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

    def _cluster_by_gap(
        self, sorted_items: Sequence[CaptureSessionItem]
    ) -> list[list[CaptureSessionItem]]:
        if not sorted_items:
            return []
        clusters: list[list[CaptureSessionItem]] = []
        cur: list[CaptureSessionItem] = [sorted_items[0]]
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
