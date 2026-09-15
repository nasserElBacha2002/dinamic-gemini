"""Process-wide embedded-worker runtime state (readiness + rate-limited logs).

``worker_loop`` interprets :class:`~src.jobs.claim_cycle.WorkerClaimCycleResult` and
reports success vs unavailability here. ``/ready`` reads the snapshot; it must not
treat an empty job queue as unhealthy, and must not report ready before the first
healthy claim cycle or while stopping.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)

REASON_REPOSITORIES_NOT_INITIALIZED = "repositories_not_initialized"
REASON_V3_JOB_REPOSITORY_UNAVAILABLE = "v3_job_repository_unavailable"
REASON_WORKER_NOT_STARTED = "worker_not_started"
REASON_WORKER_STARTING = "worker_starting"
REASON_WORKER_STOPPING = "worker_stopping"
REASON_WORKER_TERMINATED = "worker_terminated"
REASON_REPOSITORY_INIT_FAILED = "repository_init_failed"
REASON_CLAIM_LOOP_EXCEPTION = "claim_loop_exception"
REASON_LEGACY_CLAIM_FAILED = "legacy_claim_failed"
REASON_MEMORY_QUEUE_FAILED = "memory_queue_failed"

READY_REASON_JOB_WORKER_UNAVAILABLE = "JOB_WORKER_UNAVAILABLE"

_UNAVAILABLE_LOG_INTERVAL_SEC = 30.0


class WorkerLifecyclePhase(str, Enum):
    """Explicit lifecycle for embedded-worker readiness."""

    STARTING = "STARTING"
    READY = "READY"
    UNAVAILABLE = "UNAVAILABLE"
    STOPPING = "STOPPING"
    TERMINATED = "TERMINATED"


@dataclass(frozen=True)
class WorkerRuntimeSnapshot:
    required: bool
    sql_mode: bool
    started: bool
    thread_alive: bool
    stopping: bool
    phase: WorkerLifecyclePhase | None
    unavailable_reason: str | None
    last_success_monotonic: float | None
    last_success_at: str | None
    init_error_type: str | None
    unavailable_since_monotonic: float | None
    recovery_count: int = 0
    unexpected_termination_count: int = 0
    failure_count: int = 0
    worker_available: bool = True


class EmbeddedWorkerRuntime:
    """Thread-safe singleton state for the in-process (embedded) worker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._required = False
        self._sql_mode = False
        self._started = False
        self._phase: WorkerLifecyclePhase | None = None
        self._unavailable_reason: str | None = None
        self._unavailable_since: float | None = None
        self._last_unavail_log_monotonic = 0.0
        self._last_success_monotonic: float | None = None
        self._last_success_at: datetime | None = None
        self._init_error_type: str | None = None
        self._recovery_count = 0
        self._unexpected_termination_count = 0
        self._failure_count = 0

    def reset_for_tests(self) -> None:
        """Clear process state between unit tests. Does not join a live thread."""
        with self._lock:
            self._stop = threading.Event()
            self._thread = None
            self._required = False
            self._sql_mode = False
            self._started = False
            self._phase = None
            self._unavailable_reason = None
            self._unavailable_since = None
            self._last_unavail_log_monotonic = 0.0
            self._last_success_monotonic = None
            self._last_success_at = None
            self._init_error_type = None
            self._recovery_count = 0
            self._unexpected_termination_count = 0
            self._failure_count = 0

    def configure(self, *, required: bool, sql_mode: bool) -> None:
        with self._lock:
            self._required = required
            self._sql_mode = sql_mode

    def should_stop(self) -> bool:
        return self._stop.is_set()

    def request_stop(self) -> None:
        with self._lock:
            self._stop.set()
            if self._started and self._phase is not WorkerLifecyclePhase.TERMINATED:
                self._phase = WorkerLifecyclePhase.STOPPING

    def is_thread_alive(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def mark_started(self, thread: threading.Thread) -> None:
        with self._lock:
            self._thread = thread
            self._started = True
            self._stop.clear()
            self._phase = WorkerLifecyclePhase.STARTING
            # First healthy claim/idle cycle must clear STARTING before /ready is 200.
            self._last_success_monotonic = None
            self._last_success_at = None

    def join(self, timeout_sec: float) -> None:
        thread: threading.Thread | None
        with self._lock:
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout_sec)

    def mark_thread_finished(self, *, unexpected: bool) -> None:
        requested_stop = self._stop.is_set()
        if unexpected and not requested_stop:
            with self._lock:
                self._unexpected_termination_count += 1
                self._phase = WorkerLifecyclePhase.TERMINATED
            self.mark_unavailable(REASON_WORKER_TERMINATED)
            return
        with self._lock:
            if requested_stop:
                self._phase = WorkerLifecyclePhase.STOPPING
            elif unexpected:
                self._phase = WorkerLifecyclePhase.TERMINATED

    def mark_cycle_ok(self) -> None:
        recovered_downtime: float | None = None
        with self._lock:
            now = time.monotonic()
            if self._unavailable_reason is not None and self._unavailable_since is not None:
                recovered_downtime = now - self._unavailable_since
                self._recovery_count += 1
            self._unavailable_reason = None
            self._unavailable_since = None
            self._init_error_type = None
            self._last_success_monotonic = now
            self._last_success_at = datetime.now(timezone.utc)
            if self._phase is not WorkerLifecyclePhase.STOPPING:
                self._phase = WorkerLifecyclePhase.READY
        if recovered_downtime is not None:
            logger.info(
                "job_worker_recovered downtime_seconds=%.3f",
                recovered_downtime,
            )

    def mark_unavailable(
        self,
        reason: str,
        *,
        error_type: str | None = None,
        exc_info: bool = False,
    ) -> None:
        should_log = False
        with self._lock:
            now = time.monotonic()
            first = self._unavailable_reason is None
            self._failure_count += 1
            self._unavailable_reason = reason
            if self._unavailable_since is None:
                self._unavailable_since = now
            if error_type:
                self._init_error_type = error_type
            if self._phase is not WorkerLifecyclePhase.STOPPING:
                self._phase = WorkerLifecyclePhase.UNAVAILABLE
            if first or (now - self._last_unavail_log_monotonic) >= _UNAVAILABLE_LOG_INTERVAL_SEC:
                self._last_unavail_log_monotonic = now
                should_log = True
        if should_log:
            extra = f" error_type={error_type}" if error_type else ""
            if exc_info and first:
                logger.exception("job_worker_unavailable reason=%s%s", reason, extra)
            else:
                logger.error("job_worker_unavailable reason=%s%s", reason, extra)

    def snapshot(self) -> WorkerRuntimeSnapshot:
        with self._lock:
            thread = self._thread
            unavailable = self._unavailable_reason
            thread_alive = thread is not None and thread.is_alive()
            stopping = self._stop.is_set()
            phase = self._phase
            last_at = (
                self._last_success_at.isoformat().replace("+00:00", "Z")
                if self._last_success_at is not None
                else None
            )
            # Available only after a healthy claim/idle cycle while the thread lives.
            # STOPPING / STARTING / UNAVAILABLE / TERMINATED are never "available".
            available = unavailable is None and (
                not self._required
                or (
                    self._started
                    and thread_alive
                    and not stopping
                    and phase is WorkerLifecyclePhase.READY
                    and self._last_success_monotonic is not None
                )
            )
            return WorkerRuntimeSnapshot(
                required=self._required,
                sql_mode=self._sql_mode,
                started=self._started,
                thread_alive=thread_alive,
                stopping=stopping,
                phase=phase,
                unavailable_reason=unavailable,
                last_success_monotonic=self._last_success_monotonic,
                last_success_at=last_at,
                init_error_type=self._init_error_type,
                unavailable_since_monotonic=self._unavailable_since,
                recovery_count=self._recovery_count,
                unexpected_termination_count=self._unexpected_termination_count,
                failure_count=self._failure_count,
                worker_available=available,
            )

    def observability_dict(self) -> dict[str, object]:
        """Non-secret snapshot suitable for metrics/logs."""
        snap = self.snapshot()
        return {
            "worker_available": snap.worker_available,
            "worker_unavailable_reason": snap.unavailable_reason,
            "last_success_at": snap.last_success_at,
            "last_success_monotonic": snap.last_success_monotonic,
            "recovery_count": snap.recovery_count,
            "unexpected_termination_count": snap.unexpected_termination_count,
            "failure_count": snap.failure_count,
            "phase": snap.phase.value if snap.phase is not None else None,
            "required": snap.required,
            "sql_mode": snap.sql_mode,
            "thread_alive": snap.thread_alive,
            "stopping": snap.stopping,
        }

    def readiness_problem(self) -> tuple[str, str] | None:
        """Return ``(reason_code, detail)`` when embedded worker is required but not operable."""
        snap = self.snapshot()
        if not snap.required:
            return None
        if not snap.started:
            return (READY_REASON_JOB_WORKER_UNAVAILABLE, REASON_WORKER_NOT_STARTED)
        if snap.stopping or snap.phase is WorkerLifecyclePhase.STOPPING:
            return (READY_REASON_JOB_WORKER_UNAVAILABLE, REASON_WORKER_STOPPING)
        if snap.phase is WorkerLifecyclePhase.TERMINATED or (
            not snap.thread_alive and not snap.stopping
        ):
            return (READY_REASON_JOB_WORKER_UNAVAILABLE, REASON_WORKER_TERMINATED)
        if snap.phase is WorkerLifecyclePhase.STARTING or (
            snap.last_success_monotonic is None and snap.unavailable_reason is None
        ):
            return (READY_REASON_JOB_WORKER_UNAVAILABLE, REASON_WORKER_STARTING)
        if snap.unavailable_reason:
            return (READY_REASON_JOB_WORKER_UNAVAILABLE, snap.unavailable_reason)
        if snap.phase is not WorkerLifecyclePhase.READY:
            return (READY_REASON_JOB_WORKER_UNAVAILABLE, REASON_WORKER_STARTING)
        return None


_RUNTIME = EmbeddedWorkerRuntime()


def get_embedded_worker_runtime() -> EmbeddedWorkerRuntime:
    return _RUNTIME


def reset_embedded_worker_runtime_for_tests() -> None:
    _RUNTIME.reset_for_tests()
