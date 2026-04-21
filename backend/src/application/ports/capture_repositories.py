"""
Repository ports for capture sessions — Sprint 1 (interfaces only).

SQL implementations land in a later sprint; use cases must depend only on these ABCs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionConfirmationLedgerEntry,
    CaptureSessionItem,
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
    def list_by_inventory(
        self,
        inventory_id: str,
        *,
        aisle_id: Optional[str] = None,
        statuses: Optional[Sequence[CaptureSessionStatus]] = None,
        limit: int = 200,
    ) -> Sequence[CaptureSession]:
        """List sessions for an inventory, optionally filtered by aisle and/or status."""


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
