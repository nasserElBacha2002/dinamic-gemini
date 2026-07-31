"""Ports for ordered-capture SEALED→PROCESSING + job reservation (one unit of work)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.domain.jobs.entities import Job
from src.domain.ordered_capture.entities import OrderedCaptureSession


class OrderedCaptureProcessingReservationUnitOfWork(Protocol):
    """Atomic reserve: create/get unique ordered-session job + mark session PROCESSING."""

    def reserve(
        self,
        job_template: Job,
        sealed_session: OrderedCaptureSession,
        now: datetime,
    ) -> tuple[Job, OrderedCaptureSession, bool]:
        """Return (job, session, created). Caller commits after success."""
        ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> OrderedCaptureProcessingReservationUnitOfWork: ...

    def __exit__(self, exc_type, exc, tb) -> None: ...


class OrderedCaptureProcessingReservationUnitOfWorkFactory(Protocol):
    def __call__(self) -> OrderedCaptureProcessingReservationUnitOfWork: ...
