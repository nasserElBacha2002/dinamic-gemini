"""Reserve SEALED→PROCESSING + unique ordered-session job, then launch worker after commit."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from src.application.ports.ordered_capture_processing_reservation import (
    OrderedCaptureProcessingReservationUnitOfWorkFactory,
)
from src.domain.jobs.entities import Job
from src.domain.ordered_capture.entities import OrderedCaptureSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderedCaptureProcessingReservationResult:
    job: Job
    session: OrderedCaptureSession
    created: bool


@dataclass
class OrderedCaptureProcessingReservationService:
    uow_factory: OrderedCaptureProcessingReservationUnitOfWorkFactory

    def reserve(
        self,
        job_template: Job,
        sealed_session: OrderedCaptureSession,
        now: datetime,
    ) -> OrderedCaptureProcessingReservationResult:
        with self.uow_factory() as uow:
            job, session, created = uow.reserve(job_template, sealed_session, now)
            uow.commit()
        if created:
            try:
                from src.observability.metrics.instruments import (
                    JOBS_CREATED_TOTAL,
                    record_job_outcome,
                )
                from src.observability.metrics.registry import get_metrics_registry

                get_metrics_registry().inc(
                    JOBS_CREATED_TOTAL,
                    "Jobs created",
                    {"job_type": job.job_type or "process_aisle", "outcome": "created"},
                )
                if job.retry_of_job_id:
                    record_job_outcome(job_type=job.job_type or "process_aisle", outcome="retried")
            except Exception:
                logger.warning(
                    "job create metrics failed job_id=%s",
                    job.id,
                    exc_info=True,
                )
        logger.info(
            "ordered_capture.processing_reserved capture_session_id=%s job_id=%s "
            "sequence_version=%s created=%s session_status=%s",
            session.id,
            job.id,
            session.sequence_version,
            created,
            session.status.value,
        )
        return OrderedCaptureProcessingReservationResult(
            job=job,
            session=session,
            created=created,
        )
