"""Autonomous preliminary reconciliation worker (Phase 5 corrections)."""

from __future__ import annotations

import logging
import time

from src.application.use_cases.aisles.reconcile_preliminary_detections import (
    ProcessPreliminaryReconciliationsUseCase,
    ReconciliationDisabledError,
)
from src.config import load_settings

logger = logging.getLogger(__name__)


class PreliminaryReconciliationWorker:
    def __init__(
        self,
        *,
        processor: ProcessPreliminaryReconciliationsUseCase,
        poll_seconds: float = 5.0,
        batch_size: int = 50,
    ) -> None:
        self._processor = processor
        self._poll_seconds = max(1.0, poll_seconds)
        self._batch_size = max(1, min(batch_size, 50))
        self._stop = False

    def request_shutdown(self) -> None:
        self._stop = True

    def run_once(self) -> int:
        try:
            result = self._processor.process_due_batch(limit=self._batch_size)
            purged = self._processor.purge_expired(limit=100)
            if purged:
                logger.info("preliminary.reconciliation_worker.purged count=%s", purged)
            return result.claimed
        except ReconciliationDisabledError:
            return 0

    def run_forever(self) -> None:
        logger.info(
            "preliminary.reconciliation_worker.started poll_seconds=%s batch_size=%s",
            self._poll_seconds,
            self._batch_size,
        )
        while not self._stop:
            try:
                claimed = self.run_once()
            except Exception:
                logger.exception("preliminary.reconciliation_worker.batch_failed")
                claimed = 0
            if claimed == 0:
                time.sleep(self._poll_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = load_settings()
    if not getattr(settings, "server_preliminary_reconciliation_enabled", False):
        logger.warning("SERVER_PRELIMINARY_RECONCILIATION disabled — worker exiting")
        return
    from src.api.dependencies import get_process_preliminary_reconciliations_use_case

    worker = PreliminaryReconciliationWorker(
        processor=get_process_preliminary_reconciliations_use_case(),
        poll_seconds=float(
            getattr(settings, "preliminary_reconciliation_worker_poll_seconds", 5) or 5
        ),
        batch_size=int(
            getattr(settings, "preliminary_reconciliation_worker_batch_size", 50) or 50
        ),
    )
    worker.run_forever()


if __name__ == "__main__":
    main()
