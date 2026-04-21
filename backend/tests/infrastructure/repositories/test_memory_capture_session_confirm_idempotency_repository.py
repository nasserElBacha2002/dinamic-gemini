"""Unit tests for in-memory capture session confirm idempotency ledger."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.application.errors import CaptureSessionConfirmLedgerDuplicateError
from src.domain.capture.entities import CaptureSessionConfirmationLedgerEntry
from src.infrastructure.repositories.memory_capture_session_confirm_idempotency_repository import (
    MemoryCaptureSessionConfirmIdempotencyRepository,
)


def test_memory_confirm_insert_get_roundtrip() -> None:
    repo = MemoryCaptureSessionConfirmIdempotencyRepository()
    sid = "sess-1"
    t = datetime.now(timezone.utc)
    e = CaptureSessionConfirmationLedgerEntry(
        id=str(uuid.uuid4()),
        session_id=sid,
        idempotency_key="key-a",
        created_at=t,
        outcome_json={"status": "ok"},
    )
    repo.insert(e)
    got = repo.get_by_session_and_key(sid, "key-a")
    assert got is not None
    assert got.id == e.id
    assert got.outcome_json == {"status": "ok"}


def test_memory_confirm_duplicate_insert_raises() -> None:
    repo = MemoryCaptureSessionConfirmIdempotencyRepository()
    sid = "sess-2"
    t = datetime.now(timezone.utc)
    repo.insert(
        CaptureSessionConfirmationLedgerEntry(
            id="id-1",
            session_id=sid,
            idempotency_key="dup",
            created_at=t,
            outcome_json=None,
        )
    )
    with pytest.raises(CaptureSessionConfirmLedgerDuplicateError):
        repo.insert(
            CaptureSessionConfirmationLedgerEntry(
                id="id-2",
                session_id=sid,
                idempotency_key="dup",
                created_at=t,
                outcome_json={"x": 1},
            )
        )
