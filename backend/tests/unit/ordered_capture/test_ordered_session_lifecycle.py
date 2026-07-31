"""Unit tests — ordered capture session terminal lifecycle sync."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.application.services.ordered_capture_session_lifecycle import (
    resolve_ordered_capture_session_id,
    sync_ordered_session_terminal_from_job,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.ordered_capture.entities import (
    OrderedCaptureSession,
    OrderedCaptureSessionStatus,
)
from src.infrastructure.repositories.memory_ordered_capture_session_repository import (
    MemoryOrderedCaptureSessionRepository,
)


def _now() -> datetime:
    return datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _session(
    *,
    status: OrderedCaptureSessionStatus = OrderedCaptureSessionStatus.PROCESSING,
    session_id: str = "sess-1",
) -> OrderedCaptureSession:
    now = _now()
    return OrderedCaptureSession(
        id=session_id,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        status=status,
        created_at=now,
        updated_at=now,
        sequence_version=1,
    )


def _job(*, session_id: str | None = "sess-1", payload_session: str | None = None) -> Job:
    now = _now()
    payload: dict = {"aisle_id": "aisle-1"}
    if payload_session is not None:
        payload["ordered_capture_session_id"] = payload_session
    return Job(
        id=str(uuid4()),
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json=payload,
        created_at=now,
        updated_at=now,
        ordered_capture_session_id=session_id,
        sequence_version=1,
    )


def test_resolve_prefers_job_column_over_payload() -> None:
    job = _job(session_id="from-column", payload_session="from-payload")
    assert resolve_ordered_capture_session_id(job) == "from-column"


def test_resolve_falls_back_to_payload() -> None:
    job = _job(session_id=None, payload_session="from-payload")
    assert resolve_ordered_capture_session_id(job) == "from-payload"


def test_sync_completed_from_processing() -> None:
    repo = MemoryOrderedCaptureSessionRepository()
    repo.save(_session(status=OrderedCaptureSessionStatus.PROCESSING))
    job = _job()
    now = _now()
    assert (
        sync_ordered_session_terminal_from_job(
            repo,
            job,
            terminal_status=OrderedCaptureSessionStatus.COMPLETED,
            now=now,
        )
        is True
    )
    loaded = repo.get_by_id("sess-1")
    assert loaded is not None
    assert loaded.status == OrderedCaptureSessionStatus.COMPLETED
    assert loaded.completed_at == now


def test_sync_failed_from_sealed() -> None:
    repo = MemoryOrderedCaptureSessionRepository()
    repo.save(_session(status=OrderedCaptureSessionStatus.SEALED))
    job = _job()
    now = _now()
    assert (
        sync_ordered_session_terminal_from_job(
            repo,
            job,
            terminal_status=OrderedCaptureSessionStatus.FAILED,
            now=now,
        )
        is True
    )
    loaded = repo.get_by_id("sess-1")
    assert loaded is not None
    assert loaded.status == OrderedCaptureSessionStatus.FAILED
    assert loaded.completed_at == now


def test_sync_completed_idempotent_when_already_completed() -> None:
    repo = MemoryOrderedCaptureSessionRepository()
    sess = _session(status=OrderedCaptureSessionStatus.COMPLETED)
    sess.completed_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    repo.save(sess)
    assert (
        sync_ordered_session_terminal_from_job(
            repo,
            _job(),
            terminal_status=OrderedCaptureSessionStatus.COMPLETED,
            now=_now(),
        )
        is False
    )
    loaded = repo.get_by_id("sess-1")
    assert loaded is not None
    assert loaded.status == OrderedCaptureSessionStatus.COMPLETED
    assert loaded.completed_at == datetime(2026, 7, 1, tzinfo=timezone.utc)


def test_sync_failed_idempotent_when_already_failed() -> None:
    repo = MemoryOrderedCaptureSessionRepository()
    sess = _session(status=OrderedCaptureSessionStatus.FAILED)
    sess.completed_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    repo.save(sess)
    assert (
        sync_ordered_session_terminal_from_job(
            repo,
            _job(),
            terminal_status=OrderedCaptureSessionStatus.FAILED,
            now=_now(),
        )
        is False
    )
    loaded = repo.get_by_id("sess-1")
    assert loaded is not None
    assert loaded.status == OrderedCaptureSessionStatus.FAILED
    assert loaded.completed_at == datetime(2026, 7, 2, tzinfo=timezone.utc)


def test_sync_skips_open_session() -> None:
    repo = MemoryOrderedCaptureSessionRepository()
    repo.save(_session(status=OrderedCaptureSessionStatus.OPEN))
    assert (
        sync_ordered_session_terminal_from_job(
            repo,
            _job(),
            terminal_status=OrderedCaptureSessionStatus.COMPLETED,
            now=_now(),
        )
        is False
    )
    loaded = repo.get_by_id("sess-1")
    assert loaded is not None
    assert loaded.status == OrderedCaptureSessionStatus.OPEN
    assert loaded.completed_at is None


def test_sync_noop_without_session_id() -> None:
    repo = MemoryOrderedCaptureSessionRepository()
    repo.save(_session())
    job = _job(session_id=None, payload_session=None)
    assert (
        sync_ordered_session_terminal_from_job(
            repo,
            job,
            terminal_status=OrderedCaptureSessionStatus.COMPLETED,
            now=_now(),
        )
        is False
    )
