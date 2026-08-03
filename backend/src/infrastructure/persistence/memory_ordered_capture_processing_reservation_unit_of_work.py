"""In-memory UoW for ordered-capture processing reservation (tests / non-SQL)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from src.application.errors import (
    OrderedCaptureSessionConflictError,
    ProcessingRejectedUnsealedSessionError,
)
from src.application.ports.repositories import JobRepository
from src.domain.jobs.entities import Job
from src.domain.ordered_capture.entities import (
    OrderedCaptureSession,
    OrderedCaptureSessionStatus,
)
from src.infrastructure.repositories.memory_ordered_capture_session_repository import (
    MemoryOrderedCaptureSessionRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class MemoryOrderedCaptureProcessingReservationUnitOfWork:
    _job_repo: JobRepository
    _session_repo: MemoryOrderedCaptureSessionRepository
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _committed: bool = field(default=False, init=False)
    _rolled_back: bool = field(default=False, init=False)
    _active: bool = field(default=False, init=False)

    def commit(self) -> None:
        if self._rolled_back:
            raise RuntimeError("Cannot commit after rollback")
        if not self._active:
            raise RuntimeError("MemoryOrderedCaptureProcessingReservationUnitOfWork is not active")
        self._committed = True

    def rollback(self) -> None:
        self._committed = False
        self._rolled_back = True

    def __enter__(self) -> MemoryOrderedCaptureProcessingReservationUnitOfWork:
        self._committed = False
        self._rolled_back = False
        self._active = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._committed:
            self.rollback()
        self._active = False

    def reserve(
        self,
        job_template: Job,
        sealed_session: OrderedCaptureSession,
        now: datetime,
    ) -> tuple[Job, OrderedCaptureSession, bool]:
        if not self._active:
            raise RuntimeError("MemoryOrderedCaptureProcessingReservationUnitOfWork is not active")
        with self._lock:
            current = self._session_repo.get_by_id_for_update(sealed_session.id)
            if current is None:
                raise ProcessingRejectedUnsealedSessionError(
                    f"Ordered capture session not found: {sealed_session.id}"
                )
            if current.status not in (
                OrderedCaptureSessionStatus.SEALED,
                OrderedCaptureSessionStatus.PROCESSING,
            ):
                raise ProcessingRejectedUnsealedSessionError(
                    "Capture session must be SEALED before processing "
                    f"(status={current.status.value})"
                )
            if int(current.sequence_version) != int(sealed_session.sequence_version):
                raise OrderedCaptureSessionConflictError(
                    "Ordered capture session sequence_version mismatch",
                    code="ORDERED_CAPTURE_SEQUENCE_VERSION_CONFLICT",
                )

            job, created = self._job_repo.create_or_get_for_ordered_session(job_template)

            if (
                current.status == OrderedCaptureSessionStatus.PROCESSING
                and (current.processing_job_id or "").strip()
                and current.processing_job_id != job.id
            ):
                raise OrderedCaptureSessionConflictError(
                    "Ordered capture session is already PROCESSING with a different job",
                    code="ORDERED_CAPTURE_PROCESSING_JOB_CONFLICT",
                )

            updated = self._session_repo.transition_sealed_to_processing(
                current.id,
                sequence_version=int(current.sequence_version),
                job_id=job.id,
                now=now,
            )
            if updated is None:
                raise OrderedCaptureSessionConflictError(
                    "Failed to reserve ordered capture session for processing",
                    code="ORDERED_CAPTURE_PROCESSING_RESERVE_CONFLICT",
                )
            return job, updated, created


def build_memory_ordered_capture_processing_reservation_uow_factory(
    job_repo: JobRepository,
    session_repo: MemoryOrderedCaptureSessionRepository,
) -> Callable[[], MemoryOrderedCaptureProcessingReservationUnitOfWork]:
    shared_lock = threading.Lock()

    def factory() -> MemoryOrderedCaptureProcessingReservationUnitOfWork:
        return MemoryOrderedCaptureProcessingReservationUnitOfWork(
            _job_repo=job_repo,
            _session_repo=session_repo,
            _lock=shared_lock,
        )

    return factory
