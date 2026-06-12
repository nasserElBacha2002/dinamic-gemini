"""Retry and error classification for artifact publication outbox — Phase 3.5."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

RETRYABLE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "storage_unavailable",
        "storage_timeout",
        "network_error",
        "rate_limited",
        "transient_storage_error",
    }
)

NON_RETRYABLE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "source_missing",
        "source_unavailable",
        "checksum_mismatch",
        "invalid_destination_key",
        "unsupported_artifact_kind",
        "authorization_error",
        "object_mismatch",
    }
)

DEFAULT_BACKOFF_SECONDS: tuple[int, ...] = (0, 30, 120, 600, 1800)


def classify_publication_error(exc: BaseException) -> tuple[str, bool]:
    if isinstance(exc, FileNotFoundError):
        return "source_missing", False
    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return "storage_timeout", True
    if "rate limit" in message or "429" in message:
        return "rate_limited", True
    if "unavailable" in message or "connection" in message or "network" in message:
        return "storage_unavailable", True
    if "mismatch" in message or "checksum" in message or "etag" in message:
        return "object_mismatch", False
    if "permission" in message or "authorization" in message or "403" in message:
        return "authorization_error", False
    if "invalid" in message and "key" in message:
        return "invalid_destination_key", False
    return "transient_storage_error", True


def compute_next_attempt_at(
    *,
    attempt_count: int,
    now: datetime,
    backoff_seconds: tuple[int, ...] = DEFAULT_BACKOFF_SECONDS,
) -> datetime:
    idx = min(max(attempt_count - 1, 0), len(backoff_seconds) - 1)
    delay = backoff_seconds[idx]
    return now + timedelta(seconds=delay)


def sanitize_error_message(message: str, *, max_len: int = 500) -> str:
    return message[:max_len]
