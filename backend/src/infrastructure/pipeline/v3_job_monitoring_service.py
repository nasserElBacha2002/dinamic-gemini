"""
V3 worker run monitoring — Phase 6 extraction from :class:`V3JobExecutor`.

Sets up run directory logging, execution log writer, and cooperative heartbeat thread.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)
from src.io.logging import setup_logger
from src.pipeline.execution_log import ExecutionLogWriter

logger = logging.getLogger(__name__)

RUN_ID = DEFAULT_V3_WORKER_RUN_SEGMENT


@dataclass(frozen=True)
class V3JobMonitoringRequest:
    """Arguments for run_dir logger + heartbeat."""

    base_path: Path
    job_id: str
    job_dir: Path
    job: Job
    aisle: Aisle
    aisle_id: str


@dataclass
class V3WorkerRuntimeHandles:
    """Run directory logger, execution log writer, and heartbeat thread."""

    run_dir: Path
    log: Any
    exec_log: ExecutionLogWriter
    stop_heartbeat: threading.Event
    heartbeat_thread: threading.Thread
    cancel_event_emitted: dict[str, bool]


class V3JobMonitoringService:
    """Worker run monitoring: logger, execution log, and cooperative heartbeat."""

    def __init__(
        self,
        *,
        state_service: V3JobExecutionStateService,
        heartbeat_interval_sec: int = 10,
    ) -> None:
        self._state = state_service
        self._heartbeat_interval_sec = heartbeat_interval_sec

    @contextmanager
    def session(self, req: V3JobMonitoringRequest) -> Iterator[V3WorkerRuntimeHandles]:
        """Start monitoring/heartbeat, yield runtime handles, stop and join in ``finally``."""
        handles = self._begin(req)
        try:
            yield handles
        finally:
            handles.stop_heartbeat.set()
            handles.heartbeat_thread.join(timeout=1.0)

    def _begin(self, req: V3JobMonitoringRequest) -> V3WorkerRuntimeHandles:
        """Create run_dir logger, execution log, and cooperative heartbeat thread."""
        run_dir = req.base_path / req.job_id / RUN_ID
        log = setup_logger(str(req.job_dir), req.job_id, RUN_ID, console=False)
        exec_log = ExecutionLogWriter(run_dir)
        exec_log.structured_event(
            job_id=req.job_id,
            inventory_id=req.aisle.inventory_id,
            aisle_id=req.aisle_id,
            attempt=req.job.attempt_count,
            stage="WorkerLaunch",
            substep="startup_confirmation",
            event="job.spawn_succeeded",
            details={"execution_id": req.job.execution_id},
        )
        logger.info(
            "v3 execution log initialized: job_id=%s run_dir=%s",
            req.job_id,
            str(run_dir),
        )

        stop_heartbeat = threading.Event()
        cancel_event_emitted: dict[str, bool] = {
            "requested": False,
            "detected": False,
            "cancelled": False,
        }

        def heartbeat_loop() -> None:
            while not stop_heartbeat.wait(self._heartbeat_interval_sec):
                current_job = self._state.heartbeat(req.job_id)
                if current_job is None:
                    continue
                exec_log.structured_event(
                    job_id=req.job_id,
                    inventory_id=req.aisle.inventory_id,
                    aisle_id=req.aisle_id,
                    attempt=current_job.attempt_count,
                    stage=current_job.current_stage or "Pipeline",
                    substep=current_job.current_substep,
                    event="job.heartbeat",
                )

        heartbeat_thread = threading.Thread(
            target=heartbeat_loop, name=f"job-heartbeat-{req.job_id}", daemon=True
        )
        heartbeat_thread.start()
        return V3WorkerRuntimeHandles(
            run_dir=run_dir,
            log=log,
            exec_log=exec_log,
            stop_heartbeat=stop_heartbeat,
            heartbeat_thread=heartbeat_thread,
            cancel_event_emitted=cancel_event_emitted,
        )
