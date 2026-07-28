"""
V3 worker run monitoring — Phase 6 extraction from :class:`V3JobExecutor`.

Sets up run directory logging, execution log writer, and cooperative heartbeat thread.
Heartbeat proves process liveness only — a progress watchdog fails jobs stuck at
``startup_confirmed`` without advancing into a real processing substep, and signals
``runtime_abort_event`` so the worker stops construction / asset loop / persist / fallback.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job
from src.domain.jobs.lease import JobLease, LeaseRenewalOutcome
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)
from src.io.logging import setup_logger
from src.pipeline.execution_log import ExecutionLogWriter

logger = logging.getLogger(__name__)

RUN_ID = DEFAULT_V3_WORKER_RUN_SEGMENT
STARTUP_CONFIRMED_SUBSTEP = "startup_confirmed"
STARTUP_NO_PROGRESS_FAILURE_CODE = "JOB_STARTUP_NO_PROGRESS"


@dataclass(frozen=True)
class V3JobMonitoringRequest:
    """Arguments for run_dir logger + heartbeat."""

    base_path: Path
    job_id: str
    job_dir: Path
    job: Job
    aisle: Aisle
    aisle_id: str
    lease: JobLease | None = None
    lease_extension_seconds: int = 60
    #: Abort if remaining lease time after renew falls below this margin (seconds).
    renewal_safety_margin_sec: int = 20


@dataclass
class V3WorkerRuntimeHandles:
    """Run directory logger, execution log writer, and heartbeat thread."""

    run_dir: Path
    log: logging.Logger
    exec_log: ExecutionLogWriter
    stop_heartbeat: threading.Event
    heartbeat_thread: threading.Thread
    cancel_event_emitted: dict[str, bool]
    runtime_abort_event: threading.Event


class V3JobMonitoringService:
    """Worker run monitoring: logger, execution log, and cooperative heartbeat."""

    def __init__(
        self,
        *,
        state_service: V3JobExecutionStateService,
        heartbeat_interval_sec: float = 10.0,
        startup_progress_timeout_sec: float = 120.0,
    ) -> None:
        self._state = state_service
        self._heartbeat_interval_sec = heartbeat_interval_sec
        self._startup_progress_timeout_sec = float(startup_progress_timeout_sec)

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
        runtime_abort_event = threading.Event()
        cancel_event_emitted: dict[str, bool] = {
            "requested": False,
            "detected": False,
            "cancelled": False,
        }
        monitor_started_at = time.monotonic()

        def heartbeat_loop() -> None:
            active_lease = req.lease
            while not stop_heartbeat.wait(self._heartbeat_interval_sec):
                if active_lease is not None:
                    current_job, renew = self._state.heartbeat_with_lease(
                        active_lease,
                        extension_seconds=req.lease_extension_seconds,
                    )
                    if renew.outcome != LeaseRenewalOutcome.RENEWED:
                        logger.info(
                            "event=job_lease_lost job_id=%s owner_id=%s fencing_token=%s "
                            "reason=%s outcome=%s",
                            req.job_id,
                            active_lease.owner_id,
                            active_lease.fencing_token,
                            renew.reason,
                            renew.outcome.value,
                        )
                        # Do not mark job FAILED — another worker may continue.
                        runtime_abort_event.set()
                        stop_heartbeat.set()
                        break
                    if renew.lease is not None:
                        active_lease = renew.lease
                    # After renew, remaining time must clear the configured safety margin.
                    margin = max(0, int(req.renewal_safety_margin_sec or 0))
                    if margin > 0 and active_lease is not None:
                        from datetime import datetime, timezone

                        now_utc = datetime.now(timezone.utc)
                        expires = active_lease.expires_at
                        if expires.tzinfo is None:
                            expires = expires.replace(tzinfo=timezone.utc)
                        remaining = (expires - now_utc).total_seconds()
                        if remaining < margin:
                            logger.warning(
                                "event=job_lease_renewal_margin_insufficient job_id=%s "
                                "remaining_sec=%.1f margin_sec=%s",
                                req.job_id,
                                remaining,
                                margin,
                            )
                            runtime_abort_event.set()
                            stop_heartbeat.set()
                            break
                else:
                    current_job = self._state.heartbeat(req.job_id)
                if current_job is None:
                    # Job already terminal (or missing) — abort worker if still running.
                    runtime_abort_event.set()
                    continue
                if self._startup_progress_timed_out(current_job, monitor_started_at):
                    message = (
                        "Job remained at startup_confirmed without processing progress "
                        f"for {self._startup_progress_timeout_sec:.0f}s"
                    )
                    logger.error(
                        "job.startup_no_progress job_id=%s substep=%s timeout_sec=%s",
                        req.job_id,
                        current_job.current_substep,
                        self._startup_progress_timeout_sec,
                    )
                    exec_log.structured_event(
                        job_id=req.job_id,
                        inventory_id=req.aisle.inventory_id,
                        aisle_id=req.aisle_id,
                        attempt=current_job.attempt_count,
                        stage=current_job.current_stage or "WorkerLaunch",
                        substep=current_job.current_substep,
                        event="job.startup_timeout",
                        details={
                            "failure_code": STARTUP_NO_PROGRESS_FAILURE_CODE,
                            "timeout_seconds": self._startup_progress_timeout_sec,
                        },
                    )
                    # Signal abort BEFORE / with terminal transition so the worker cannot
                    # race into success finalization after a lost CAS.
                    runtime_abort_event.set()
                    try:
                        self._state.fail_job_and_aisle(
                            req.job_id,
                            req.aisle,
                            message,
                            failure_code=STARTUP_NO_PROGRESS_FAILURE_CODE,
                        )
                    except Exception:
                        logger.exception(
                            "job.startup_timeout_fail_failed job_id=%s", req.job_id
                        )
                    stop_heartbeat.set()
                    break
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
            runtime_abort_event=runtime_abort_event,
        )

    def _startup_progress_timed_out(self, job: Job, monitor_started_at: float) -> bool:
        if self._startup_progress_timeout_sec <= 0:
            return False
        substep = (job.current_substep or "").strip()
        if substep != STARTUP_CONFIRMED_SUBSTEP:
            return False
        return (time.monotonic() - monitor_started_at) >= self._startup_progress_timeout_sec
