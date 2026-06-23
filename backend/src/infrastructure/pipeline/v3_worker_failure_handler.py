"""
V3 generic worker failure handling — Phase 6 extraction from :class:`V3JobExecutor`.

Handles unexpected exceptions during pipeline execution or finalization (not cooperative cancel).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.domain.aisle.entities import Aisle
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.pipeline.execution_log import ExecutionLogWriter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class V3WorkerFailureRequest:
    """Unexpected failure during v3 job run (pipeline or post-pipeline)."""

    job_id: str
    aisle: Aisle
    aisle_id: str
    run_dir: Path
    error: Exception


class V3WorkerFailureHandler:
    """Marks job and aisle failed after an unexpected worker exception."""

    def __init__(self, *, state_service: V3JobExecutionStateService) -> None:
        self._state = state_service

    def handle_unexpected_failure(self, req: V3WorkerFailureRequest) -> bool:
        """Log, write execution log error when possible, fail job/aisle. True => caller returns True."""
        logger.exception("v3 job %s failed: %s", req.job_id, req.error)
        if req.run_dir.is_dir():
            try:
                err_log = ExecutionLogWriter(req.run_dir)
                err_log.error(
                    "Pipeline",
                    f"Job failed: {req.error}",
                    payload={"error": str(req.error)[:500]},
                )
            except Exception:
                pass
        self._state.fail_job_and_aisle(req.job_id, req.aisle, str(req.error))
        logger.info(
            "v3 mark failed: job_id=%s inventory_id=%s aisle_id=%s error=%s",
            req.job_id,
            req.aisle.inventory_id,
            req.aisle_id,
            str(req.error),
        )
        return True
