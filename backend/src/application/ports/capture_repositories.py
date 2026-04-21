"""
Repository ports for capture sessions — Sprint 1 (interfaces only).

SQL implementations land in a later sprint; use cases must depend only on these ABCs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Sequence

from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionConfirmationLedgerEntry,
    CaptureSessionItem,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)


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
