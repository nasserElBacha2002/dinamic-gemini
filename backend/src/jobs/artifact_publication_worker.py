"""Autonomous artifact publication outbox worker — Phase 3.5 corrections."""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass, field

from src.application.services.artifact_publication_dispatcher import ArtifactPublicationDispatcher
from src.config import load_settings

logger = logging.getLogger(__name__)


@dataclass
class ArtifactPublicationWorkerHealth:
    last_poll_at: float | None = None
    polls: int = 0
    claimed_total: int = 0
    published_total: int = 0
    retry_total: int = 0
    permanent_failure_total: int = 0
    idle_polls: int = 0
    shutdown_requested: bool = False
    last_batch_jobs: set[str] = field(default_factory=set)


class ArtifactPublicationOutboxWorker:
    def __init__(
        self,
        *,
        dispatcher: ArtifactPublicationDispatcher,
        poll_seconds: float,
        batch_size: int,
    ) -> None:
        self._dispatcher = dispatcher
        self._poll_seconds = max(1.0, poll_seconds)
        self._batch_size = max(1, batch_size)
        self._health = ArtifactPublicationWorkerHealth()
        self._stop = False

    @property
    def health(self) -> ArtifactPublicationWorkerHealth:
        return self._health

    def request_shutdown(self) -> None:
        self._stop = True
        self._health.shutdown_requested = True

    def run_once(self) -> int:
        """Process one due batch; return number of claimed rows."""
        self._health.last_poll_at = time.time()
        self._health.polls += 1
        result = self._dispatcher.process_due_batch(limit=self._batch_size)
        claimed_count = result.claimed_count
        if claimed_count == 0:
            self._health.idle_polls += 1
            logger.debug("artifact.outbox_worker.idle poll=%s", self._health.polls)
            return 0
        self._health.claimed_total += claimed_count
        self._health.published_total += len(result.published_kinds)
        self._health.retry_total += len(result.retry_scheduled_kinds)
        self._health.permanent_failure_total += len(result.permanently_failed_kinds)
        logger.info(
            "artifact.outbox_worker.batch published=%s retry=%s permanent_fail=%s continuation=%s",
            len(result.published_kinds),
            len(result.retry_scheduled_kinds),
            len(result.permanently_failed_kinds),
            result.continuation_started,
        )
        return claimed_count

    def run_forever(self) -> None:
        logger.info(
            "artifact.outbox_worker.started poll_seconds=%s batch_size=%s",
            self._poll_seconds,
            self._batch_size,
        )
        while not self._stop:
            try:
                processed = self.run_once()
            except Exception:
                logger.exception("artifact.outbox_worker.batch_failed")
                processed = 0
            if processed == 0:
                time.sleep(self._poll_seconds)
        logger.info("artifact.outbox_worker.stopped polls=%s", self._health.polls)


def _build_dispatcher_from_container():
    from src.runtime.v3_deps import get_app_container

    return get_app_container().get_artifact_publication_dispatcher()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = load_settings()
    if not settings.artifact_publication_worker_enabled:
        logger.info("artifact.outbox_worker.disabled")
        return
    worker = ArtifactPublicationOutboxWorker(
        dispatcher=_build_dispatcher_from_container(),
        poll_seconds=float(settings.artifact_publication_poll_seconds),
        batch_size=int(settings.artifact_publication_batch_size),
    )

    def _handle_signal(signum, _frame) -> None:
        logger.info("artifact.outbox_worker.signal signum=%s", signum)
        worker.request_shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        worker.request_shutdown()
    logger.info("artifact.outbox_worker.exit health=%s", worker.health)


if __name__ == "__main__":
    main()
