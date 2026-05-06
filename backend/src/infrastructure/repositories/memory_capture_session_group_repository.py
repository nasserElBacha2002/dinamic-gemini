"""In-memory CaptureSessionGroupRepository — G3/G4 tests."""

from __future__ import annotations

from src.application.ports.capture_repositories import (
    CaptureSessionGroupRepository,
    CaptureSessionGroupSummary,
    CaptureSessionItemRepository,
)
from src.application.services.capture_group_materialization_state import (
    materialization_state_for_counts,
)
from src.domain.capture.entities import (
    CaptureSessionGroup,
    CaptureSessionItem,
    CaptureSessionItemImportStatus,
)


def _sort_time(item: CaptureSessionItem):
    return item.adjusted_capture_time or item.effective_capture_time


class MemoryCaptureSessionGroupRepository(CaptureSessionGroupRepository):
    """Uses ``item_repo`` to build summaries so counts match assigned items in tests."""

    def __init__(self, item_repo: CaptureSessionItemRepository) -> None:
        self._groups: dict[str, CaptureSessionGroup] = {}
        self._item_repo = item_repo

    def delete_all_for_session(self, session_id: str) -> None:
        to_drop = [g.id for g in self._groups.values() if g.session_id == session_id]
        for gid in to_drop:
            self._groups.pop(gid, None)

    def count_groups_for_session(self, session_id: str) -> int:
        return sum(1 for g in self._groups.values() if g.session_id == session_id)

    def get_by_id_and_session(self, group_id: str, session_id: str) -> CaptureSessionGroup | None:
        g = self._groups.get((group_id or "").strip())
        if g is None or g.session_id != session_id:
            return None
        return g

    def update(self, group: CaptureSessionGroup) -> None:
        existing = self._groups.get(group.id)
        if existing is None or existing.session_id != group.session_id:
            raise ValueError("Cannot update unknown capture session group")
        self._groups[group.id] = group

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
            imported = [
                i for i in members if i.import_status == CaptureSessionItemImportStatus.IMPORTED
            ]
            linked_imported = sum(1 for i in imported if (i.linked_source_asset_id or "").strip())
            mat_state = materialization_state_for_counts(
                assignment_status=g.assignment_status.value,
                imported_count=len(imported),
                linked_imported_count=linked_imported,
            )
            out.append(
                CaptureSessionGroupSummary(
                    group_id=g.id,
                    group_index=g.group_index,
                    item_count=len(members),
                    start_time=min(times),
                    end_time=max(times),
                    algorithm_version=g.algorithm_version,
                    assigned_aisle_id=g.assigned_aisle_id,
                    assignment_status=g.assignment_status.value,
                    assigned_at=g.assigned_at,
                    materialization_state=mat_state,
                )
            )
        return tuple(out)
