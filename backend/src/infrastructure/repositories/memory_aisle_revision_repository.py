"""In-memory aisle revision repository (unit tests / fail-closed fallback)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime

from src.domain.aisle_revision.entities import (
    AisleRevision,
    AisleRevisionItem,
    PositionVersion,
    revision_is_open,
)


class MemoryAisleRevisionRepository:
    def __init__(self) -> None:
        self._revisions: dict[str, AisleRevision] = {}
        self._items: dict[str, dict[str, AisleRevisionItem]] = {}
        self._position_versions: dict[str, PositionVersion] = {}
        self._locks: dict[str, tuple[str, str, datetime]] = {}
        self._lock = threading.Lock()

    def get_revision(self, revision_id: str) -> AisleRevision | None:
        return self._revisions.get((revision_id or "").strip())

    def get_open_revision_for_aisle(self, aisle_id: str) -> AisleRevision | None:
        aid = (aisle_id or "").strip()
        opens = [
            r
            for r in self._revisions.values()
            if r.aisle_id == aid and revision_is_open(r.status)
        ]
        if not opens:
            return None
        opens.sort(key=lambda r: r.requested_at, reverse=True)
        return opens[0]

    def list_revisions_for_aisle(
        self, *, aisle_id: str, limit: int = 50
    ) -> Sequence[AisleRevision]:
        aid = (aisle_id or "").strip()
        rows = [r for r in self._revisions.values() if r.aisle_id == aid]
        rows.sort(key=lambda r: r.requested_at, reverse=True)
        return rows[: max(1, min(int(limit), 200))]

    def list_items(self, revision_id: str) -> Sequence[AisleRevisionItem]:
        return list(self._items.get(revision_id, {}).values())

    def get_item(self, *, revision_id: str, asset_id: str) -> AisleRevisionItem | None:
        return self._items.get(revision_id, {}).get(asset_id)

    def save_revision(
        self,
        revision: AisleRevision,
        *,
        items: Sequence[AisleRevisionItem] | None = None,
    ) -> AisleRevision:
        with self._lock:
            if revision_is_open(revision.status):
                for rid, existing in list(self._revisions.items()):
                    if (
                        existing.aisle_id == revision.aisle_id
                        and rid != revision.id
                        and revision_is_open(existing.status)
                    ):
                        raise ValueError(
                            f"AISLE_REVISION_OPEN_EXISTS: aisle {revision.aisle_id} "
                            f"already has open revision {existing.id}"
                        )
            self._revisions[revision.id] = revision
            if items is not None:
                self._items[revision.id] = {i.asset_id: i for i in items}
            elif revision.id not in self._items:
                self._items[revision.id] = {}
            return revision

    def save_item(self, item: AisleRevisionItem) -> AisleRevisionItem:
        with self._lock:
            bucket = self._items.setdefault(item.revision_id, {})
            bucket[item.asset_id] = item
            return item

    def try_acquire_lock(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        owner_token: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> bool:
        with self._lock:
            existing = self._locks.get(aisle_id)
            if existing is not None:
                _inv, token, exp = existing
                if exp > now and token != owner_token:
                    return False
            self._locks[aisle_id] = (inventory_id, owner_token, lease_expires_at)
            return True

    def release_lock(self, *, aisle_id: str, owner_token: str, now: datetime) -> bool:
        del now  # unused; interface parity with SQL
        with self._lock:
            existing = self._locks.get(aisle_id)
            if existing is None:
                return True
            _inv, token, _exp = existing
            if token != owner_token:
                return False
            del self._locks[aisle_id]
            return True

    def get_current_position_version(self, position_id: str) -> PositionVersion | None:
        pid = (position_id or "").strip()
        currents = [
            v for v in self._position_versions.values() if v.position_id == pid and v.is_current
        ]
        if not currents:
            return None
        currents.sort(key=lambda v: v.version, reverse=True)
        return currents[0]

    def max_position_version(self, position_id: str) -> int:
        pid = (position_id or "").strip()
        versions = [
            v.version for v in self._position_versions.values() if v.position_id == pid
        ]
        return max(versions) if versions else 0

    def save_position_version(
        self,
        row: PositionVersion,
        *,
        supersede_current: bool,
    ) -> PositionVersion:
        with self._lock:
            if supersede_current:
                for vid, existing in list(self._position_versions.items()):
                    if existing.position_id == row.position_id and existing.is_current:
                        self._position_versions[vid] = PositionVersion(
                            **{**existing.__dict__, "is_current": False}
                        )
            self._position_versions[row.id] = row
            return row

    def list_position_versions_for_aisle(
        self, *, aisle_id: str, limit: int = 500
    ) -> Sequence[PositionVersion]:
        aid = (aisle_id or "").strip()
        rows = [v for v in self._position_versions.values() if v.aisle_id == aid]
        rows.sort(key=lambda v: (v.asset_id, v.version), reverse=True)
        return rows[: max(1, min(int(limit), 2000))]
