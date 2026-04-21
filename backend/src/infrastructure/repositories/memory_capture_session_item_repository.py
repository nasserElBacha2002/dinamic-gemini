"""In-memory CaptureSessionItemRepository — Sprint 2."""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from src.application.ports.capture_repositories import CaptureSessionItemRepository
from src.domain.capture.entities import CaptureSessionItem


class MemoryCaptureSessionItemRepository(CaptureSessionItemRepository):
    def __init__(self) -> None:
        self._store: Dict[str, CaptureSessionItem] = {}

    def save(self, item: CaptureSessionItem) -> None:
        self._store[item.id] = item

    def get_by_id(self, item_id: str) -> Optional[CaptureSessionItem]:
        return self._store.get(item_id)

    def list_by_session(self, session_id: str) -> Sequence[CaptureSessionItem]:
        rows = [i for i in self._store.values() if i.session_id == session_id]
        rows.sort(key=lambda i: (i.updated_at, i.id))
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
            i.session_id == session_id and (i.content_hash or "").strip() == h for i in self._store.values()
        )
