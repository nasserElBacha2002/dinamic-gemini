"""In-memory CaptureSessionGroupRepository — G3 tests."""

from __future__ import annotations

from typing import Dict

from src.application.ports.capture_repositories import (
    CaptureSessionGroupRepository,
    CaptureSessionGroupSummary,
    CaptureSessionItemRepository,
)
from src.domain.capture.entities import CaptureSessionGroup, CaptureSessionItem


def _sort_time(item: CaptureSessionItem):
    return item.adjusted_capture_time or item.effective_capture_time


class MemoryCaptureSessionGroupRepository(CaptureSessionGroupRepository):
    """Uses ``item_repo`` to build summaries so counts match assigned items in tests."""

    def __init__(self, item_repo: CaptureSessionItemRepository) -> None:
        self._groups: Dict[str, CaptureSessionGroup] = {}
        self._item_repo = item_repo

    def delete_all_for_session(self, session_id: str) -> None:
        to_drop = [g.id for g in self._groups.values() if g.session_id == session_id]
        for gid in to_drop:
            self._groups.pop(gid, None)

    def insert(self, group: CaptureSessionGroup) -> None:
        self._groups[group.id] = group

    def list_summaries(self, session_id: str) -> tuple[CaptureSessionGroupSummary, ...]:
        groups = sorted(
            (g for g in self._groups.values() if g.session_id == session_id),
            key=lambda g: (g.group_index, g.id),
        )
        out: list[CaptureSessionGroupSummary] = []
        for g in groups:
            members = [i for i in self._item_repo.list_by_session(session_id) if i.group_id == g.id]
            if not members:
                continue
            times = [_sort_time(i) for i in members if _sort_time(i) is not None]
            if not times:
                continue
            out.append(
                CaptureSessionGroupSummary(
                    group_id=g.id,
                    group_index=g.group_index,
                    item_count=len(members),
                    start_time=min(times),
                    end_time=max(times),
                    algorithm_version=g.algorithm_version,
                )
            )
        return tuple(out)
