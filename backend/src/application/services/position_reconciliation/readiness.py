"""Readiness policy for position reconciliation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.application.errors import PositionReconciliationNotReadyError
from src.application.ports.ordered_capture_session_repository import (
    OrderedCaptureSessionRepository,
)
from src.domain.jobs.entities import JobStatus
from src.domain.ordered_capture.entities import OrderedCaptureSessionStatus


class PositionReconciliationReadinessPolicy:
    """Validate that stable job inputs are available before frame loading.

    Session validation is intentionally skipped when no ordered-session repository
    is supplied, preserving compatibility in deployments that do not persist sessions.
    """

    def __init__(
        self,
        session_repo: OrderedCaptureSessionRepository | None = None,
    ) -> None:
        self._sessions = session_repo

    def require_ready(
        self,
        job: Any,
        *,
        inventory_id: str,
        aisle: Any,
        links: Sequence[Any],
        allow_in_finalization: bool = False,
    ) -> None:
        status = job.status.value if isinstance(job.status, JobStatus) else str(job.status).lower()
        allowed = {JobStatus.SUCCEEDED.value, "completed"}
        if allow_in_finalization:
            allowed.update({JobStatus.RUNNING.value, "processing", "finalizing"})
        if status not in allowed:
            raise PositionReconciliationNotReadyError(
                f"Job {job.id} status {status!r} is not ready for position reconciliation"
            )
        if aisle.inventory_id != inventory_id:
            raise PositionReconciliationNotReadyError(
                f"Aisle {aisle.id} is outside inventory {inventory_id}"
            )
        if not links:
            raise PositionReconciliationNotReadyError(
                f"Job {job.id} has no source asset links"
            )
        if job.ordered_capture_session_id and self._sessions is not None:
            session = self._sessions.get_by_id(job.ordered_capture_session_id)
            if session is None:
                raise PositionReconciliationNotReadyError(
                    f"Ordered capture session {job.ordered_capture_session_id} was not found"
                )
            if session.status is not OrderedCaptureSessionStatus.SEALED:
                raise PositionReconciliationNotReadyError(
                    f"Ordered capture session {session.id} must be SEALED; "
                    f"current status is {session.status.value}"
                )
