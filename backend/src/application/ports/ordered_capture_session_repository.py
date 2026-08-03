"""Ports for ordered capture sessions (mobile sequence spine)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.domain.ordered_capture.entities import OrderedCaptureSession


class OrderedCaptureSessionRepository(Protocol):
    def save(self, session: OrderedCaptureSession) -> None: ...

    def get_by_id(self, session_id: str) -> OrderedCaptureSession | None: ...

    def list_by_aisle(
        self,
        aisle_id: str,
        *,
        statuses: Sequence[str] | None = None,
    ) -> list[OrderedCaptureSession]: ...

    def get_open_or_uploading_for_aisle(self, aisle_id: str) -> OrderedCaptureSession | None:
        """Return the newest OPEN/UPLOADING session for the aisle, if any."""
        ...

    def get_or_create_open_for_aisle(
        self, session: OrderedCaptureSession
    ) -> OrderedCaptureSession:
        """Atomically return the existing OPEN/UPLOADING session for the aisle, or persist ``session``.

        Race-safe against concurrent creates (SQL unique index / memory lock).
        """
        ...
