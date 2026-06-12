"""Retry and error classification for artifact publication outbox — Phase 3.5."""

from __future__ import annotations

from datetime import datetime, timedelta

INTERNAL_PROGRAMMING_ERRORS = (
    NameError,
    TypeError,
    AttributeError,
    AssertionError,
    NotImplementedError,
)

RETRYABLE_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
    OSError,
)

DEFAULT_BACKOFF_SECONDS: tuple[int, ...] = (0, 30, 120, 600, 1800)


def classify_publication_error(exc: BaseException) -> tuple[str, bool]:
    if isinstance(exc, INTERNAL_PROGRAMMING_ERRORS):
        return "internal_publication_error", False
    if isinstance(exc, FileNotFoundError):
        return "source_missing", False
    if isinstance(exc, PermissionError):
        return "authorization_error", False
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        if isinstance(exc, TimeoutError):
            return "storage_timeout", True
        return "storage_unavailable", True
    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return "storage_timeout", True
    if "rate limit" in message or "429" in message:
        return "rate_limited", True
    if "checksum" in message or "sha256" in message:
        return "checksum_mismatch", False
    if "mismatch" in message:
        return "object_mismatch", False
    if "permission" in message or "authorization" in message or "403" in message:
        return "authorization_error", False
    if "invalid" in message and "key" in message:
        return "invalid_destination_key", False
    if "unavailable" in message or "connection" in message or "network" in message:
        return "storage_unavailable", True
    return "publication_error", False


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
