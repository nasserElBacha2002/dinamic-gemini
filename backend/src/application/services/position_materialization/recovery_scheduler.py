"""Lifecycle-capable scheduler for materialization association recovery."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field

from src.application.ports.clock import Clock
from src.application.services.position_materialization.recovery import (
    PositionMaterializationAssociationRecoveryService,
)
from src.domain.position_materialization.errors import PositionMaterializationError

logger = logging.getLogger(__name__)


@dataclass
class PositionMaterializationRecoveryScheduler:
    service: PositionMaterializationAssociationRecoveryService
    clock: Clock
    enabled: bool
    interval_sec: int
    owner: str = field(default_factory=lambda: f"materialization-recovery:{uuid.uuid4()}")
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.interval_sec < 1:
            raise ValueError("interval_sec must be positive")

    def run_once(self) -> int:
        if not self.enabled:
            return 0
        return self.service.run_once(owner=self.owner, now=self.clock.now())

    def start(self) -> None:
        if not self.enabled or (self._thread is not None and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="position-materialization-recovery",
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
            except PositionMaterializationError:
                logger.exception("position materialization recovery iteration failed")
            self._stop.wait(self.interval_sec)


def build_position_materialization_recovery_scheduler(
    *,
    service: PositionMaterializationAssociationRecoveryService,
    clock: Clock,
    enabled: bool,
    interval_sec: int,
) -> PositionMaterializationRecoveryScheduler:
    """Construction seam for later runtime composition; starts no threads."""
    return PositionMaterializationRecoveryScheduler(
        service=service,
        clock=clock,
        enabled=enabled,
        interval_sec=interval_sec,
    )
