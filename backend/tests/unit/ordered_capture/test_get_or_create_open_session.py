"""Unit tests — atomic get_or_create for open ordered capture sessions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from src.domain.ordered_capture.entities import (
    OrderedCaptureSession,
    OrderedCaptureSessionStatus,
)
from src.infrastructure.repositories.memory_ordered_capture_session_repository import (
    MemoryOrderedCaptureSessionRepository,
)


def _candidate(aisle_id: str = "aisle-1") -> OrderedCaptureSession:
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    return OrderedCaptureSession(
        id=str(uuid4()),
        inventory_id="inv-1",
        aisle_id=aisle_id,
        status=OrderedCaptureSessionStatus.OPEN,
        created_at=now,
        updated_at=now,
        client_id="client-1",
    )


def test_get_or_create_open_session_double_call_returns_same() -> None:
    repo = MemoryOrderedCaptureSessionRepository()
    first = repo.get_or_create_open_for_aisle(_candidate())
    second = repo.get_or_create_open_for_aisle(_candidate())
    assert first.id == second.id
    assert len(repo.list_by_aisle("aisle-1")) == 1


def test_get_or_create_open_session_concurrent_race_returns_one() -> None:
    repo = MemoryOrderedCaptureSessionRepository()

    def _create() -> str:
        return repo.get_or_create_open_for_aisle(_candidate()).id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: _create(), range(16)))
    assert len(set(ids)) == 1
    assert len(repo.list_by_aisle("aisle-1")) == 1


def test_memory_save_rejects_second_open_session_for_aisle() -> None:
    from src.application.errors import OrderedCaptureSessionConflictError

    repo = MemoryOrderedCaptureSessionRepository()
    first = _candidate()
    repo.save(first)
    second = _candidate()
    try:
        repo.save(second)
        raise AssertionError("expected OrderedCaptureSessionConflictError")
    except OrderedCaptureSessionConflictError as exc:
        assert exc.code == "ORDERED_CAPTURE_OPEN_SESSION_EXISTS"
