"""Processing event publisher (Phase 7 corrections).

Observability semantics (chosen): **A — best-effort telemetry**.

* Publish failures must not break OCR / code-scan processing.
* Failures increment ``processing_event_publish_failed_total`` (structured log metric).
* Results may mark ``observability_incomplete`` when publish fails.
* ProcessingEvent rows are **not** transactional audit evidence; do not rely on them
  for commit/rollback decisions. Prefer job/attempt/asset state for consistency.
* At most one ``asset.finalized`` per attempt/asset orchestration call.
* Do not publish OCR full text; metadata is sanitized via ``sanitize_metadata``.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import uuid4

from src.application.ports.clock import Clock
from src.application.ports.processing_event_repository import ProcessingEventRepository
from src.application.services.image_processing.processing_evidence_sanitizer import (
    sanitize_metadata,
)
from src.application.services.legacy_processing_metrics import (
    record_processing_event_publish_failed,
)
from src.config import load_settings
from src.domain.image_processing.processing_event import ProcessingEvent

logger = logging.getLogger(__name__)

_ALLOWED_SEVERITIES = frozenset({"INFO", "WARN", "ERROR"})


def normalize_processing_event_severity(raw: str | None) -> str:
    """Map caller severities onto CK_processing_events_severity values."""
    value = str(raw or "INFO").strip().upper()
    if value in {"WARNING", "WARN"}:
        return "WARN"
    if value in {"CRITICAL", "FATAL", "ERROR"}:
        return "ERROR"
    if value in _ALLOWED_SEVERITIES:
        return value
    return "INFO"


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


class CompositeProcessingEventPublisher:
    """Fan-out publisher: persist + mirror (e.g. execution_log) without coupling layers."""

    def __init__(self, *publishers: ProcessingEventPublisher) -> None:
        self._publishers = tuple(p for p in publishers if p is not None)

    def publish(self, **kwargs: Any) -> None:
        for publisher in self._publishers:
            try:
                publisher.publish(**kwargs)
            except Exception as exc:
                logger.debug(
                    "processing_event.composite_publish_skipped err=%s",
                    exc,
                )


class ExecutionLogProcessingEventPublisher:
    """Mirrors processing events into the worker execution_log.jsonl channel.

    The UI downloads this file for operator diagnostics. Without this bridge, INTERNAL_OCR
    can complete fully while the execution log only shows spawn + heartbeat.
    """

    def __init__(
        self,
        *,
        exec_log: Any,
        inventory_id: str | None,
        aisle_id: str | None,
        attempt: int,
        stage: str = "InternalOcr",
    ) -> None:
        self._exec_log = exec_log
        self._inventory_id = inventory_id
        self._aisle_id = aisle_id
        self._attempt = attempt
        self._stage = stage

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
        level = "error" if str(severity).upper() in {"ERROR", "CRITICAL"} else "info"
        if str(severity).upper() == "WARNING":
            level = "warning"
        details: dict[str, Any] = {}
        if asset_id:
            details["asset_id"] = asset_id
        if attempt_id:
            details["attempt_id"] = attempt_id
        if strategy:
            details["strategy"] = strategy
        if error_code:
            details["error_code"] = error_code
        if correlation_id:
            details["correlation_id"] = correlation_id
        if message:
            details["message"] = message[:500]
        safe_meta = sanitize_metadata(metadata or {}, level="TECHNICAL_SAFE")
        if safe_meta:
            details["metadata"] = safe_meta
        try:
            self._exec_log.structured_event(
                job_id=job_id,
                inventory_id=self._inventory_id,
                aisle_id=self._aisle_id,
                attempt=self._attempt,
                stage=self._stage,
                substep=event_type,
                event=event_type,
                duration_ms=duration_ms,
                details=details or None,
                level=level,
            )
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            logger.debug(
                "processing_event.exec_log_mirror_skipped job_id=%s event_type=%s err=%s",
                job_id,
                event_type,
                exc,
            )


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
                    severity=normalize_processing_event_severity(severity),
                    message=(message or "")[:2000] if message else None,
                    error_code=error_code,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                    metadata=sanitize_metadata(metadata or {}, level="TECHNICAL_SAFE"),
                )
            )
        except Exception as exc:
            # Best-effort telemetry: never fail the OCR asset path on publish errors.
            record_processing_event_publish_failed(
                event_type=event_type,
                err_type=type(exc).__name__,
            )
            logger.warning(
                "processing_event.publish_failed job_id=%s event_type=%s err=%s",
                job_id,
                event_type,
                type(exc).__name__,
            )


__all__ = [
    "CompositeProcessingEventPublisher",
    "ExecutionLogProcessingEventPublisher",
    "NoOpProcessingEventPublisher",
    "ProcessingEventPublisher",
    "RepositoryProcessingEventPublisher",
    "normalize_processing_event_severity",
]
