"""Sync ordered capture session terminal status from job outcomes (Phase 1)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.domain.jobs.entities import Job
from src.domain.ordered_capture.entities import OrderedCaptureSessionStatus

logger = logging.getLogger(__name__)

_TERMINAL_ELIGIBLE = frozenset(
    {
        OrderedCaptureSessionStatus.PROCESSING,
        OrderedCaptureSessionStatus.SEALED,
    }
)
_ALREADY_TERMINAL = frozenset(
    {
        OrderedCaptureSessionStatus.COMPLETED,
        OrderedCaptureSessionStatus.FAILED,
    }
)
_ALLOWED_TERMINAL = frozenset(
    {
        OrderedCaptureSessionStatus.COMPLETED,
        OrderedCaptureSessionStatus.FAILED,
    }
)


def resolve_ordered_capture_session_id(job: Job) -> str | None:
    """Prefer job column; fall back to payload_json.ordered_capture_session_id."""
    sid = (job.ordered_capture_session_id or "").strip()
    if sid:
        return sid
    payload = job.payload_json or {}
    raw = payload.get("ordered_capture_session_id")
    if raw is None:
        return None
    sid = str(raw).strip()
    return sid or None


def sync_ordered_session_terminal_from_job(
    session_repo: Any,
    job: Job,
    *,
    terminal_status: OrderedCaptureSessionStatus,
    now: datetime,
) -> bool:
    """Mark the ordered session COMPLETED/FAILED when the job reaches a terminal status.

    Idempotent: only PROCESSING (or SEALED) → terminal; already COMPLETED/FAILED is a no-op.
    Returns True when a status transition was persisted.
    """
    if terminal_status not in _ALLOWED_TERMINAL:
        raise ValueError(
            f"terminal_status must be COMPLETED or FAILED, got {terminal_status!r}"
        )
    if session_repo is None:
        return False
    session_id = resolve_ordered_capture_session_id(job)
    if not session_id:
        return False
    session = session_repo.get_by_id(session_id)
    if session is None:
        logger.warning(
            "ordered_session_terminal_sync_missing session_id=%s job_id=%s wanted=%s",
            session_id,
            job.id,
            terminal_status.value,
        )
        return False
    if session.status in _ALREADY_TERMINAL:
        return False
    if session.status not in _TERMINAL_ELIGIBLE:
        logger.info(
            "ordered_session_terminal_sync_skipped session_id=%s job_id=%s "
            "current_status=%s wanted=%s",
            session_id,
            job.id,
            session.status.value,
            terminal_status.value,
        )
        return False
    session.status = terminal_status
    session.completed_at = now
    session.updated_at = now
    session_repo.save(session)
    logger.info(
        "ordered_session_terminal_synced session_id=%s job_id=%s status=%s",
        session_id,
        job.id,
        terminal_status.value,
    )
    return True
