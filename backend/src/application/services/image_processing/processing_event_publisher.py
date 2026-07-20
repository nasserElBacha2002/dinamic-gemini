"""Processing event publisher (Phase 7 corrections)."""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import uuid4

from src.application.ports.clock import Clock
from src.application.ports.processing_event_repository import ProcessingEventRepository
from src.application.services.image_processing.processing_evidence_sanitizer import (
    sanitize_metadata,
)
from src.config import load_settings
from src.domain.image_processing.processing_event import ProcessingEvent

logger = logging.getLogger(__name__)


class ProcessingEventPublisher(Protocol):
    def publish(
        self,
        *,
        job_id: str,
        event_type: str,
        asset_id: str | None = None,
        attempt_id: str | None = None,
        strategy: str | None = None,
        severity: str = "INFO",
        message: str | None = None,
        error_code: str | None = None,
        duration_ms: int | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...


class NoOpProcessingEventPublisher:
    def publish(self, **kwargs: Any) -> None:
        return None


class RepositoryProcessingEventPublisher:
    def __init__(
        self,
        *,
        event_repo: ProcessingEventRepository,
        clock: Clock,
    ) -> None:
        self._event_repo = event_repo
        self._clock = clock

    def publish(
        self,
        *,
        job_id: str,
        event_type: str,
        asset_id: str | None = None,
        attempt_id: str | None = None,
        strategy: str | None = None,
        severity: str = "INFO",
        message: str | None = None,
        error_code: str | None = None,
        duration_ms: int | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        settings = load_settings()
        if not bool(getattr(settings, "processing_events_persistence_enabled", False)):
            return
        try:
            self._event_repo.append(
                ProcessingEvent(
                    id=str(uuid4()),
                    job_id=job_id,
                    asset_id=asset_id,
                    attempt_id=attempt_id,
                    event_type=event_type,
                    created_at=self._clock.now(),
                    strategy=strategy,
                    severity=severity,
                    message=(message or "")[:2000] if message else None,
                    error_code=error_code,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                    metadata=sanitize_metadata(metadata or {}, level="TECHNICAL_SAFE"),
                )
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(
                "processing_event.publish_failed job_id=%s event_type=%s err=%s",
                job_id,
                event_type,
                exc,
            )


__all__ = [
    "NoOpProcessingEventPublisher",
    "ProcessingEventPublisher",
    "RepositoryProcessingEventPublisher",
]
