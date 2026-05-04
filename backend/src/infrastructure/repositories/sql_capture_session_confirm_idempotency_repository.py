"""SQL Server implementation of CaptureSessionConfirmIdempotencyRepository (ledger only; no use case wiring yet)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pyodbc

from src.application.errors import CaptureSessionConfirmLedgerDuplicateError
from src.application.ports.capture_repositories import CaptureSessionConfirmIdempotencyRepository
from src.database.sqlserver import SqlServerClient
from src.domain.capture.entities import CaptureSessionConfirmationLedgerEntry
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _is_confirm_session_key_duplicate(exc: pyodbc.IntegrityError) -> bool:
    msg = str(exc).lower()
    return "uq_capture_session_confirmations_session_key" in msg or (
        "capture_session_confirmations" in msg and "duplicate" in msg
    )


def _row_to_entry(row) -> CaptureSessionConfirmationLedgerEntry:
    eid = getattr(row, "id", "") or ""
    created = _ensure_utc(getattr(row, "created_at", None))
    if created is None:
        raise ValueError(f"capture_session_confirmations row {eid!r} missing created_at")
    raw = getattr(row, "outcome_json", None)
    outcome: Optional[Dict[str, Any]] = None
    raw_s = normalize_db_str(raw) if raw is not None else ""
    if raw_s:
        try:
            parsed = json.loads(raw_s)
            outcome = parsed if isinstance(parsed, dict) else None
            if outcome is None:
                logger.warning("outcome_json root is not an object for confirmation id=%s", eid)
        except json.JSONDecodeError as err:
            logger.warning("Invalid outcome_json for confirmation id=%s: %s", eid, err)
            outcome = None
    return CaptureSessionConfirmationLedgerEntry(
        id=eid,
        session_id=normalize_db_str(getattr(row, "session_id", None)),
        idempotency_key=normalize_db_str(getattr(row, "idempotency_key", None)),
        created_at=created,
        outcome_json=outcome,
    )


class SqlCaptureSessionConfirmIdempotencyRepository(CaptureSessionConfirmIdempotencyRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_by_session_and_key(
        self, session_id: str, idempotency_key: str
    ) -> Optional[CaptureSessionConfirmationLedgerEntry]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, session_id, idempotency_key, outcome_json, created_at
                FROM capture_session_confirmations
                WHERE session_id = ? AND idempotency_key = ?
                """,
                (session_id, idempotency_key),
            )
            row = cur.fetchone()
        return _row_to_entry(row) if row else None

    def insert(self, entry: CaptureSessionConfirmationLedgerEntry) -> None:
        created = _ensure_utc(entry.created_at)
        if created is None:
            raise ValueError("CaptureSessionConfirmationLedgerEntry.created_at is required")
        outcome_str = json.dumps(entry.outcome_json, ensure_ascii=False) if entry.outcome_json else None
        with self._client.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO capture_session_confirmations (
                        id, session_id, idempotency_key, outcome_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        entry.id,
                        entry.session_id,
                        entry.idempotency_key,
                        outcome_str,
                        created,
                    ),
                )
            except pyodbc.IntegrityError as exc:
                if _is_confirm_session_key_duplicate(exc):
                    raise CaptureSessionConfirmLedgerDuplicateError(
                        "Duplicate capture session confirmation idempotency key for this session"
                    ) from exc
                raise
