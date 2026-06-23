"""
V3 cooperative cancellation — Phase 6 extraction from :class:`V3JobExecutor`.

Creates cancellation checkpoints and handles pipeline-level cancellation requests.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from src.domain.aisle.entities import Aisle
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.execution_log import ExecutionLogWriter

logger = logging.getLogger(__name__)


class V3CancellationCoordinator:
    """Orchestrates cooperative cancellation checkpoints and pipeline cancel handling."""

    def __init__(self, *, state_service: V3JobExecutionStateService) -> None:
        self._state = state_service

    def checkpoint(
        self,
        *,
        job_id: str,
        exec_log: ExecutionLogWriter,
        inventory_id: str,
        aisle_id: str,
        cancel_event_emitted: dict[str, bool],
    ) -> Callable[[str, str | None, str], None]:
        """Return a callable that raises when cooperative cancellation is requested."""

        def cancellation_checkpoint(stage: str, substep: str | None, reason: str) -> None:
            self._state.raise_if_cancellation_requested(
                job_id,
                exec_log=exec_log,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                stage=stage,
                substep=substep,
                reason=reason,
                cancel_event_emitted=cancel_event_emitted,
            )

        return cancellation_checkpoint

    def handle_pipeline_cancellation(
        self,
        *,
        job_id: str,
        aisle: Aisle,
        error: PipelineCancellationRequestedError,
        exec_log: ExecutionLogWriter,
        cancel_event_emitted: dict[str, bool],
    ) -> bool:
        """Cancel job and aisle after cooperative cancellation during pipeline execution."""
        logger.info("v3 job %s cancellation detected cooperatively: %s", job_id, error)
        self._state.cancel_job_and_aisle(
            job_id,
            aisle,
            str(error),
            exec_log=exec_log,
            cancel_event_emitted=cancel_event_emitted,
        )
        return True
