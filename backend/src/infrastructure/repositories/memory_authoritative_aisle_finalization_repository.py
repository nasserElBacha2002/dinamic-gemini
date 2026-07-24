"""In-memory authoritative aisle finalization repository (unit tests)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime

from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleExcludedAsset,
    AuthoritativeAisleFinalization,
    AuthoritativeAisleFinalizationItem,
)


class MemoryAuthoritativeAisleFinalizationRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, AuthoritativeAisleFinalization] = {}
        self._items: dict[str, list[AuthoritativeAisleFinalizationItem]] = {}
        self._exclusions: dict[str, AuthoritativeAisleExcludedAsset] = {}
        self._locks: dict[str, tuple[str, str, datetime]] = {}  # aisle -> (inv, token, exp)
        self._lock = threading.Lock()

    def get_by_id(self, finalization_id: str) -> AuthoritativeAisleFinalization | None:
        return self._by_id.get((finalization_id or "").strip())

    def get_current_for_aisle(self, aisle_id: str) -> AuthoritativeAisleFinalization | None:
        aid = (aisle_id or "").strip()
        currents = [r for r in self._by_id.values() if r.aisle_id == aid and r.is_current]
        if not currents:
            return None
        currents.sort(key=lambda r: r.finalization_version, reverse=True)
        return currents[0]

    def max_version_for_aisle(self, aisle_id: str) -> int:
        aid = (aisle_id or "").strip()
        versions = [r.finalization_version for r in self._by_id.values() if r.aisle_id == aid]
        return max(versions) if versions else 0

    def list_items(self, finalization_id: str) -> Sequence[AuthoritativeAisleFinalizationItem]:
        return list(self._items.get(finalization_id, []))

    def list_current_exclusions(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[AuthoritativeAisleExcludedAsset]:
        return [
            e
            for e in self._exclusions.values()
            if e.inventory_id == inventory_id
            and e.aisle_id == aisle_id
            and e.is_current
        ]

    def upsert_exclusion(
        self, row: AuthoritativeAisleExcludedAsset
    ) -> AuthoritativeAisleExcludedAsset:
        with self._lock:
            self._exclusions[row.id] = row
            return row

    def save_finalization(
        self,
        *,
        finalization: AuthoritativeAisleFinalization,
        items: Sequence[AuthoritativeAisleFinalizationItem],
        supersede_current: bool,
    ) -> AuthoritativeAisleFinalization:
        with self._lock:
            if supersede_current:
                for fid, row in list(self._by_id.items()):
                    if row.aisle_id == finalization.aisle_id and row.is_current:
                        self._by_id[fid] = AuthoritativeAisleFinalization(
                            **{**row.__dict__, "is_current": False}
                        )
            self._by_id[finalization.id] = finalization
            self._items[finalization.id] = list(items)
            return finalization

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
                inv, token, exp = existing
                if exp > now and token != owner_token:
                    return False
            self._locks[aisle_id] = (inventory_id, owner_token, lease_expires_at)
            return True

    def release_lock(self, *, aisle_id: str, owner_token: str, now: datetime) -> bool:
        with self._lock:
            existing = self._locks.get(aisle_id)
            if existing is None:
                return True
            _inv, token, _exp = existing
            if token != owner_token:
                return False
            del self._locks[aisle_id]
            return True
