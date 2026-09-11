"""Process-wide embedded-worker runtime state (readiness + rate-limited logs).

The claim loop in ``job_store.claim_next_job`` reports success vs unavailability here.
``/ready`` reads the snapshot; it must not treat an empty job queue as unhealthy.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

REASON_REPOSITORIES_NOT_INITIALIZED = "repositories_not_initialized"
REASON_V3_JOB_REPOSITORY_UNAVAILABLE = "v3_job_repository_unavailable"
REASON_WORKER_NOT_STARTED = "worker_not_started"
REASON_WORKER_TERMINATED = "worker_terminated"
REASON_REPOSITORY_INIT_FAILED = "repository_init_failed"
REASON_CLAIM_LOOP_EXCEPTION = "claim_loop_exception"

READY_REASON_JOB_WORKER_UNAVAILABLE = "JOB_WORKER_UNAVAILABLE"

_UNAVAILABLE_LOG_INTERVAL_SEC = 30.0


@dataclass(frozen=True)
class WorkerRuntimeSnapshot:
    required: bool
    sql_mode: bool
    started: bool
    thread_alive: bool
    stopping: bool
    unavailable_reason: str | None
    last_success_monotonic: float | None
    init_error_type: str | None
    unavailable_since_monotonic: float | None


class EmbeddedWorkerRuntime:
    """Thread-safe singleton state for the in-process (embedded) worker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._required = False
        self._sql_mode = False
        self._started = False
        self._unavailable_reason: str | None = None
        self._unavailable_since: float | None = None
        self._last_unavail_log_monotonic = 0.0
        self._last_success_monotonic: float | None = None
        self._init_error_type: str | None = None

    def reset_for_tests(self) -> None:
        """Clear process state between unit tests. Does not join a live thread."""
        with self._lock:
            self._stop = threading.Event()
            self._thread = None
            self._required = False
            self._sql_mode = False
            self._started = False
            self._unavailable_reason = None
            self._unavailable_since = None
            self._last_unavail_log_monotonic = 0.0
            self._last_success_monotonic = None
            self._init_error_type = None

    def configure(self, *, required: bool, sql_mode: bool) -> None:
        with self._lock:
            self._required = required
            self._sql_mode = sql_mode

    def should_stop(self) -> bool:
        return self._stop.is_set()

    def request_stop(self) -> None:
        self._stop.set()

    def is_thread_alive(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def mark_started(self, thread: threading.Thread) -> None:
        with self._lock:
            self._thread = thread
            self._started = True
            self._stop.clear()

    def join(self, timeout_sec: float) -> None:
        thread: threading.Thread | None
        with self._lock:
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout_sec)

    def mark_thread_finished(self, *, unexpected: bool) -> None:
        if unexpected and not self._stop.is_set():
            self.mark_unavailable(REASON_WORKER_TERMINATED)

    def mark_cycle_ok(self) -> None:
        recovered_downtime: float | None = None
        with self._lock:
            now = time.monotonic()
            if self._unavailable_reason is not None and self._unavailable_since is not None:
                recovered_downtime = now - self._unavailable_since
            self._unavailable_reason = None
            self._unavailable_since = None
            self._init_error_type = None
            self._last_success_monotonic = now
        if recovered_downtime is not None:
            logger.info(
                "job_worker_recovered downtime_seconds=%.3f",
                recovered_downtime,
            )

    def mark_unavailable(self, reason: str, *, error_type: str | None = None) -> None:
        should_log = False
        with self._lock:
            now = time.monotonic()
            first = self._unavailable_reason is None
            self._unavailable_reason = reason
            if self._unavailable_since is None:
                self._unavailable_since = now
            if error_type:
                self._init_error_type = error_type
            if first or (now - self._last_unavail_log_monotonic) >= _UNAVAILABLE_LOG_INTERVAL_SEC:
                self._last_unavail_log_monotonic = now
                should_log = True
        if should_log:
            extra = f" error_type={error_type}" if error_type else ""
            logger.error("job_worker_unavailable reason=%s%s", reason, extra)

    def snapshot(self) -> WorkerRuntimeSnapshot:
        with self._lock:
            thread = self._thread
            return WorkerRuntimeSnapshot(
                required=self._required,
                sql_mode=self._sql_mode,
                started=self._started,
                thread_alive=thread is not None and thread.is_alive(),
                stopping=self._stop.is_set(),
                unavailable_reason=self._unavailable_reason,
                last_success_monotonic=self._last_success_monotonic,
                init_error_type=self._init_error_type,
                unavailable_since_monotonic=self._unavailable_since,
            )

    def readiness_problem(self) -> tuple[str, str] | None:
        """Return ``(reason_code, detail)`` when embedded worker is required but not operable."""
        snap = self.snapshot()
        if not snap.required:
            return None
        if not snap.started:
            return (READY_REASON_JOB_WORKER_UNAVAILABLE, REASON_WORKER_NOT_STARTED)
        if not snap.thread_alive and not snap.stopping:
            return (READY_REASON_JOB_WORKER_UNAVAILABLE, REASON_WORKER_TERMINATED)
        if snap.unavailable_reason:
            return (READY_REASON_JOB_WORKER_UNAVAILABLE, snap.unavailable_reason)
        return None


_RUNTIME = EmbeddedWorkerRuntime()


def get_embedded_worker_runtime() -> EmbeddedWorkerRuntime:
    return _RUNTIME


def reset_embedded_worker_runtime_for_tests() -> None:
    _RUNTIME.reset_for_tests()
