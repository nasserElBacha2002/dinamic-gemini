"""Scheduler for stuck local CSV import materialization recovery."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from src.application.ports.clock import Clock
from src.application.services.local_csv_import_recovery import LocalCsvImportRecoveryService

logger = logging.getLogger(__name__)


@dataclass
class LocalCsvImportRecoveryScheduler:
    service: LocalCsvImportRecoveryService
    clock: Clock
    enabled: bool
    interval_sec: int
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.interval_sec < 1:
            raise ValueError("interval_sec must be positive")

    def run_once(self) -> int:
        if not self.enabled:
            return 0
        return self.service.run_once(now=self.clock.now())

    def start(self) -> None:
        if not self.enabled or (self._thread is not None and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="local-csv-import-recovery",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout_sec: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout_sec)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("local csv import recovery iteration failed")
            self._stop.wait(self.interval_sec)


def build_local_csv_import_recovery_scheduler(
    *,
    service: LocalCsvImportRecoveryService,
    clock: Clock,
    enabled: bool,
    interval_sec: int,
) -> LocalCsvImportRecoveryScheduler:
    """Construction seam for runtime composition; starts no threads."""
    return LocalCsvImportRecoveryScheduler(
        service=service,
        clock=clock,
        enabled=enabled,
        interval_sec=interval_sec,
    )
