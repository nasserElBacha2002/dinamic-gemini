"""Phase 5 — cooperative stale-job recovery scheduler (uses RecoverStaleJobUseCase)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from src.application.ports.repositories import JobRepository
from src.application.use_cases.recovery.recover_stale_job import (
    RecoverStaleJobCommand,
    RecoverStaleJobOutcome,
    RecoverStaleJobUseCase,
)
from src.domain.jobs.entities import JobStatus
from src.observability.logging import log_event
from src.observability.metrics.registry import get_metrics_registry

logger = logging.getLogger(__name__)

SCHEDULER_RUNS = "stale_recovery_scheduler_runs_total"
SCHEDULER_RECOVERED = "stale_recovery_scheduler_recovered_total"


@dataclass
class StaleJobRecoveryScheduler:
    use_case: RecoverStaleJobUseCase
    job_repo: JobRepository
    enabled: bool
    interval_sec: int
    batch_size: int
    max_attempts: int
    stale_after_seconds: int
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="stale-job-recovery-scheduler",
            daemon=True,
        )
        self._thread.start()
        log_event(
            "recovery_scheduler_started",
            component="recovery",
            operation="scheduler",
            outcome="ok",
            interval_sec=self.interval_sec,
            batch_size=self.batch_size,
        )

    def stop(self, *, timeout_sec: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout_sec)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("stale recovery scheduler iteration failed")
                get_metrics_registry().inc(
                    SCHEDULER_RUNS,
                    "Stale recovery scheduler iterations",
                    {"outcome": "error"},
                )
            self._stop.wait(self.interval_sec)

    def run_once(self) -> int:
        """Scan a bounded batch of stale candidates and recover. Returns recoveries."""
        get_metrics_registry().inc(
            SCHEDULER_RUNS, "Stale recovery scheduler iterations", {"outcome": "ok"}
        )
        list_fn = self.job_repo.list_jobs_for_ops_scan
        candidates = list(
            list_fn(
                limit=self.batch_size,
                statuses=[
                    JobStatus.RUNNING.value,
                    JobStatus.STARTING.value,
                    JobStatus.CANCEL_REQUESTED.value,
                ],
            )
        )
        recovered = 0
        for job in candidates:
            result = self.use_case.execute(
                RecoverStaleJobCommand(
                    job_id=job.id,
                    actor="scheduler",
                    reason="automatic_stale_recovery",
                    dry_run=False,
                    stale_after_seconds=self.stale_after_seconds,
                    max_attempts=self.max_attempts,
                )
            )
            if result.outcome in (
                RecoverStaleJobOutcome.RECOVERED,
                RecoverStaleJobOutcome.RELAUNCHED,
            ):
                recovered += 1
                get_metrics_registry().inc(
                    SCHEDULER_RECOVERED,
                    "Jobs recovered by scheduler",
                    {"outcome": result.outcome.value.lower()},
                )
        return recovered
