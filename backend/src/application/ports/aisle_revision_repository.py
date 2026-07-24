"""Port for aisle revisions and position versions (Phase 8)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.aisle_revision.entities import (
    AisleRevision,
    AisleRevisionItem,
    PositionVersion,
)


class AisleRevisionRepository(Protocol):
    def get_revision(self, revision_id: str) -> AisleRevision | None: ...

    def get_open_revision_for_aisle(self, aisle_id: str) -> AisleRevision | None: ...

    def list_revisions_for_aisle(
        self, *, aisle_id: str, limit: int = 50
    ) -> Sequence[AisleRevision]: ...

    def list_items(self, revision_id: str) -> Sequence[AisleRevisionItem]: ...

    def get_item(
        self, *, revision_id: str, asset_id: str
    ) -> AisleRevisionItem | None: ...

    def save_revision(
        self,
        revision: AisleRevision,
        *,
        items: Sequence[AisleRevisionItem] | None = None,
    ) -> AisleRevision: ...

    def save_item(self, item: AisleRevisionItem) -> AisleRevisionItem: ...

    def try_acquire_lock(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        owner_token: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> bool: ...

    def release_lock(self, *, aisle_id: str, owner_token: str, now: datetime) -> bool: ...

    def get_current_position_version(
        self, position_id: str
    ) -> PositionVersion | None: ...

    def max_position_version(self, position_id: str) -> int: ...

    def save_position_version(
        self,
        row: PositionVersion,
        *,
        supersede_current: bool,
    ) -> PositionVersion: ...

    def list_position_versions_for_aisle(
        self, *, aisle_id: str, limit: int = 500
    ) -> Sequence[PositionVersion]: ...
