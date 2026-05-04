"""In-memory CaptureSessionItemRepository — Sprint 2 + Sprint 3.

Stores full ``CaptureSessionItem`` domain instances by reference (preview fields, time metadata,
etc.); same object round-trips as SQL row mapping.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.errors import CaptureSessionDuplicateItemContentError
from src.application.ports.capture_repositories import CaptureSessionItemRepository
from src.domain.capture.entities import CaptureSessionItem, CaptureSessionItemImportStatus


class MemoryCaptureSessionItemRepository(CaptureSessionItemRepository):
    def __init__(self) -> None:
        self._store: dict[str, CaptureSessionItem] = {}

    def save(self, item: CaptureSessionItem) -> None:
        h = (item.content_hash or "").strip()
        if h:
            for other in self._store.values():
                if (
                    other.session_id == item.session_id
                    and (other.content_hash or "").strip() == h
                    and other.id != item.id
                ):
                    raise CaptureSessionDuplicateItemContentError(
                        "Duplicate file content in this capture session"
                    )
        self._store[item.id] = item

    def get_by_id(self, item_id: str) -> CaptureSessionItem | None:
        return self._store.get(item_id)

    def list_by_session(self, session_id: str) -> Sequence[CaptureSessionItem]:
        rows = [i for i in self._store.values() if i.session_id == session_id]
        rows.sort(key=lambda i: (i.updated_at, i.id))
        return tuple(rows)

    def list_by_session_and_group_id(
        self, session_id: str, group_id: str
    ) -> Sequence[CaptureSessionItem]:
        gid = (group_id or "").strip()
        rows = [
            i
            for i in self._store.values()
            if i.session_id == session_id and (i.group_id or "").strip() == gid
        ]

        def _sort_key(it: CaptureSessionItem) -> tuple:
            if it.effective_capture_time is None:
                return (datetime.max.replace(tzinfo=timezone.utc), it.id)
            return (it.effective_capture_time, it.id)

        rows.sort(key=_sort_key)
        return tuple(rows)

    def list_staging_cleanup_candidates(self, session_id: str) -> Sequence[CaptureSessionItem]:
        out: list[CaptureSessionItem] = []
        for i in self._store.values():
            if i.session_id != session_id:
                continue
            if i.linked_source_asset_id:
                continue
            if not (i.staging_storage_key or "").strip():
                continue
            out.append(i)
        out.sort(key=lambda x: (x.updated_at, x.id))
        return tuple(out)

    def has_item_with_content_hash(self, session_id: str, content_hash: str) -> bool:
        h = (content_hash or "").strip()
        if not h:
            return False
        return any(
            i.session_id == session_id and (i.content_hash or "").strip() == h
            for i in self._store.values()
        )

    def count_items_with_import_status(
        self, session_id: str, import_status: CaptureSessionItemImportStatus
    ) -> int:
        return sum(
            1
            for i in self._store.values()
            if i.session_id == session_id and i.import_status == import_status
        )
