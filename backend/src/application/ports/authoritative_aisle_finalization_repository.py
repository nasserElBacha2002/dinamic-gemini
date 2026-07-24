"""Port for authoritative aisle finalization persistence (Phase 6)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleExcludedAsset,
    AuthoritativeAisleFinalization,
    AuthoritativeAisleFinalizationItem,
)


class AuthoritativeFinalizationLockError(Exception):
    """Lock not acquired or owned by another token."""


class AuthoritativeAisleFinalizationRepository(Protocol):
    def get_by_id(self, finalization_id: str) -> AuthoritativeAisleFinalization | None: ...

    def get_current_for_aisle(self, aisle_id: str) -> AuthoritativeAisleFinalization | None: ...

    def max_version_for_aisle(self, aisle_id: str) -> int: ...

    def list_items(self, finalization_id: str) -> Sequence[AuthoritativeAisleFinalizationItem]: ...

    def list_current_exclusions(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[AuthoritativeAisleExcludedAsset]: ...

    def upsert_exclusion(self, row: AuthoritativeAisleExcludedAsset) -> AuthoritativeAisleExcludedAsset: ...

    def save_finalization(
        self,
        *,
        finalization: AuthoritativeAisleFinalization,
        items: Sequence[AuthoritativeAisleFinalizationItem],
        supersede_current: bool,
    ) -> AuthoritativeAisleFinalization: ...

    def try_acquire_lock(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        owner_token: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> bool: ...

    def release_lock(
        self, *, aisle_id: str, owner_token: str, now: datetime
    ) -> bool: ...
