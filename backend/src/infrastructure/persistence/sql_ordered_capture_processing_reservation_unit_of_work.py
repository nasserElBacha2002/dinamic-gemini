"""SQL Server UoW: SEALED→PROCESSING reservation + unique ordered-session job on one connection."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from src.application.errors import (
    OrderedCaptureSessionConflictError,
    ProcessingRejectedUnsealedSessionError,
)
from src.database.sqlserver import SqlServerClient
from src.domain.jobs.entities import Job
from src.domain.ordered_capture.entities import (
    OrderedCaptureSession,
    OrderedCaptureSessionStatus,
)
from src.infrastructure.database.sql_transaction import SqlServerTransaction, TransactionState
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
from src.infrastructure.repositories.sql_ordered_capture_session_repository import (
    SqlOrderedCaptureSessionRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class SqlOrderedCaptureProcessingReservationUnitOfWork:
    _client: SqlServerClient
    _tx: SqlServerTransaction | None = field(default=None, init=False)
    _job_repo: SqlJobRepository | None = field(default=None, init=False)
    _session_repo: SqlOrderedCaptureSessionRepository | None = field(default=None, init=False)
    _committed: bool = field(default=False, init=False)
    _rolled_back: bool = field(default=False, init=False)

    def commit(self) -> None:
        if self._rolled_back:
            raise RuntimeError("Cannot commit after rollback")
        if self._tx is None:
            raise RuntimeError("SqlOrderedCaptureProcessingReservationUnitOfWork is not active")
        self._tx.commit()
        self._committed = True
        logger.debug("SqlOrderedCaptureProcessingReservationUnitOfWork committed")

    def rollback(self) -> None:
        if self._rolled_back:
            return
        if self._tx is not None and self._tx.state == TransactionState.ACTIVE:
            self._tx.rollback()
        self._committed = False
        self._rolled_back = True
        logger.warning("SqlOrderedCaptureProcessingReservationUnitOfWork rolled back")

    def __enter__(self) -> SqlOrderedCaptureProcessingReservationUnitOfWork:
        self._tx = self._client.begin_transaction()
        self._tx.__enter__()
        conn = self._tx.connection
        self._job_repo = SqlJobRepository(self._client, connection=conn)
        self._session_repo = SqlOrderedCaptureSessionRepository(self._client, connection=conn)
        self._committed = False
        self._rolled_back = False
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if not self._committed:
                self.rollback()
        finally:
            if self._tx is not None:
                self._tx.close()
            self._tx = None
            self._job_repo = None
            self._session_repo = None

    def reserve(
        self,
        job_template: Job,
        sealed_session: OrderedCaptureSession,
        now: datetime,
    ) -> tuple[Job, OrderedCaptureSession, bool]:
        if self._job_repo is None or self._session_repo is None:
            raise RuntimeError("SqlOrderedCaptureProcessingReservationUnitOfWork is not active")

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


def build_sql_ordered_capture_processing_reservation_uow_factory(
    client: SqlServerClient,
) -> Callable[[], SqlOrderedCaptureProcessingReservationUnitOfWork]:
    def factory() -> SqlOrderedCaptureProcessingReservationUnitOfWork:
        return SqlOrderedCaptureProcessingReservationUnitOfWork(_client=client)

    return factory
