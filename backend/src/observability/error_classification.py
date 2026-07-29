"""Phase 5 — typed error classes for retry / recovery decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    CANCELED = "CANCELED"
    LEASE_LOST = "LEASE_LOST"
    INVALID_INPUT = "INVALID_INPUT"
    AUTHORIZATION = "AUTHORIZATION"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    UNKNOWN = "UNKNOWN"


# Permanent — never retry.
_NO_RETRY = frozenset(
    {
        ErrorClass.PERMANENT,
        ErrorClass.CANCELED,
        ErrorClass.LEASE_LOST,
        ErrorClass.INVALID_INPUT,
        ErrorClass.AUTHORIZATION,
    }
)


@dataclass(frozen=True, slots=True)
class ClassifiedError:
    error_class: ErrorClass
    reason_code: str
    retryable: bool
    detail: str | None = None


def classify_error(
    *,
    reason_code: str | None = None,
    http_status: int | None = None,
    exc: BaseException | None = None,
    hints: dict[str, Any] | None = None,
) -> ClassifiedError:
    """Central classification — avoid scattered string matching at call sites."""
    code = (reason_code or "").strip().upper() or "UNKNOWN"
    hints = hints or {}

    if code in {"CANCELED", "CANCEL_REQUESTED", "JOB_CANCELED"}:
        return ClassifiedError(ErrorClass.CANCELED, code, False)
    if code in {"LEASE_LOST", "JOB_LEASE_LOST", "FENCING_TOKEN_MISMATCH"}:
        return ClassifiedError(ErrorClass.LEASE_LOST, code, False)
    if code in {"UNAUTHORIZED", "FORBIDDEN", "AUTHZ_DENIED", "AUTHORIZATION"}:
        return ClassifiedError(ErrorClass.AUTHORIZATION, code, False)
    if code in {
        "INVALID_INPUT",
        "VALIDATION_ERROR",
        "SCHEMA_MISMATCH",
        "CONFIG_ERROR",
        "BAD_REQUEST",
    }:
        return ClassifiedError(ErrorClass.INVALID_INPUT, code, False)
    if code in {"RATE_LIMIT", "PROVIDER_RATE_LIMIT", "HTTP_429"}:
        return ClassifiedError(ErrorClass.PROVIDER_RATE_LIMIT, code, True)
    if code in {
        "TIMEOUT",
        "PROVIDER_TIMEOUT",
        "NETWORK",
        "CONNECTION_ERROR",
        "SQL_DEADLOCK",
        "SQL_TIMEOUT",
        "TRANSIENT",
    }:
        return ClassifiedError(ErrorClass.TRANSIENT, code, True)
    if code in {"INFRASTRUCTURE", "SQL_UNAVAILABLE", "STORAGE_UNAVAILABLE"}:
        return ClassifiedError(ErrorClass.INFRASTRUCTURE, code, True)
    if code in {"PERMANENT", "NOT_RETRYABLE", "CHECKSUM_MISMATCH"}:
        return ClassifiedError(ErrorClass.PERMANENT, code, False)

    if http_status == 429:
        return ClassifiedError(ErrorClass.PROVIDER_RATE_LIMIT, "HTTP_429", True)
    if http_status is not None and 500 <= http_status <= 599:
        return ClassifiedError(ErrorClass.TRANSIENT, f"HTTP_{http_status}", True)
    if http_status is not None and 400 <= http_status <= 499:
        if http_status in (401, 403):
            return ClassifiedError(ErrorClass.AUTHORIZATION, f"HTTP_{http_status}", False)
        return ClassifiedError(ErrorClass.INVALID_INPUT, f"HTTP_{http_status}", False)

    if exc is not None:
        name = type(exc).__name__
        if name in {"TimeoutError", "asyncio.TimeoutError"} or "timeout" in name.lower():
            return ClassifiedError(ErrorClass.TRANSIENT, "TIMEOUT", True)
        if "Deadlock" in name or "OperationalError" in name:
            return ClassifiedError(ErrorClass.INFRASTRUCTURE, name.upper(), True)

    if hints.get("retryable") is True:
        return ClassifiedError(ErrorClass.TRANSIENT, code, True)
    if hints.get("retryable") is False:
        return ClassifiedError(ErrorClass.PERMANENT, code, False)

    return ClassifiedError(ErrorClass.UNKNOWN, code, False)


def is_retryable(classified: ClassifiedError) -> bool:
    if classified.error_class in _NO_RETRY:
        return False
    return classified.retryable
