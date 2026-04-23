"""
Repository ports for capture sessions — Sprint 1 (interfaces only).

SQL implementations land in a later sprint; use cases must depend only on these ABCs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionConfirmationLedgerEntry,
    CaptureSessionGroup,
    CaptureSessionItem,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)


@dataclass(frozen=True)
class CaptureSessionGroupSummary:
    """Aggregated view of a persisted temporal group (G3/G4 API wire shape)."""

    group_id: str
    group_index: int
    item_count: int
    start_time: datetime
    end_time: datetime
    algorithm_version: str
    assigned_aisle_id: Optional[str] = None
    assignment_status: str = "unassigned"
    assigned_at: Optional[datetime] = None


class CaptureSessionRepository(ABC):
    @abstractmethod
    def save(self, session: CaptureSession) -> None:
        """Insert or update a capture session."""

    @abstractmethod
    def get_by_id(self, session_id: str) -> Optional[CaptureSession]:
        ...

    @abstractmethod
    def get_by_id_for_inventory(self, session_id: str, inventory_id: str) -> Optional[CaptureSession]:
        """Return the session only when it belongs to the given inventory."""

    @abstractmethod
    def count_open_sessions_for_aisle(self, inventory_id: str, aisle_id: str) -> int:
        """Count non-terminal sessions that are still open (``closed_at`` is null)."""

    @abstractmethod
    def list_by_inventory(
        self,
        inventory_id: str,
        *,
        aisle_id: Optional[str] = None,
        statuses: Optional[Sequence[CaptureSessionStatus]] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[Sequence[CaptureSession], int]:
        """List sessions for an inventory with filters and pagination; returns (page rows, total count)."""


class CaptureSessionItemRepository(ABC):
    @abstractmethod
    def save(self, item: CaptureSessionItem) -> None:
        ...

    @abstractmethod
    def get_by_id(self, item_id: str) -> Optional[CaptureSessionItem]:
        ...

    @abstractmethod
    def list_by_session(self, session_id: str) -> Sequence[CaptureSessionItem]:
        ...

    @abstractmethod
    def list_by_session_and_group_id(self, session_id: str, group_id: str) -> Sequence[CaptureSessionItem]:
        """Items in the session belonging to the given temporal group (``group_id``)."""

    @abstractmethod
    def list_staging_cleanup_candidates(self, session_id: str) -> Sequence[CaptureSessionItem]:
        """Items that may still have staging bytes: no linked SourceAsset, non-empty staging key."""

    @abstractmethod
    def has_item_with_content_hash(self, session_id: str, content_hash: str) -> bool:
        """True if any item in the session already records this non-empty content hash."""

    @abstractmethod
    def count_items_with_import_status(
        self, session_id: str, import_status: CaptureSessionItemImportStatus
    ) -> int:
        """Count items for a session with the given import status (bounded COUNT query)."""


class CaptureSessionGroupRepository(ABC):
    """Persisted temporal groups for a capture session (G3)."""

    @abstractmethod
    def delete_all_for_session(self, session_id: str) -> None:
        """Remove all groups for the session (G3 recompute clears rows; items ``group_id`` cleared in use case)."""

    @abstractmethod
    def insert(self, group: CaptureSessionGroup) -> None:
        """Insert a single group row (caller assigns ids and indices)."""

    @abstractmethod
    def count_groups_for_session(self, session_id: str) -> int:
        """Number of persisted group rows for the session (including unassigned)."""

    @abstractmethod
    def get_by_id_and_session(self, group_id: str, session_id: str) -> Optional[CaptureSessionGroup]:
        """Return the group when it belongs to the session, else None."""

    @abstractmethod
    def update(self, group: CaptureSessionGroup) -> None:
        """Persist assignment and other mutable fields on an existing group row."""

    @abstractmethod
    def list_summaries(self, session_id: str) -> Sequence[CaptureSessionGroupSummary]:
        """Return group summaries ordered by ``group_index`` (empty if none)."""


class CaptureSessionConfirmIdempotencyRepository(ABC):
    """Stores at-most-once outcomes per (session_id, idempotency_key) for confirm retries."""

    @abstractmethod
    def get_by_session_and_key(
        self, session_id: str, idempotency_key: str
    ) -> Optional[CaptureSessionConfirmationLedgerEntry]:
        ...

    @abstractmethod
    def insert(self, entry: CaptureSessionConfirmationLedgerEntry) -> None:
        """Insert a new ledger row; must fail on duplicate (session_id, idempotency_key)."""
