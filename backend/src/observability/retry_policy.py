"""Phase 5 — retry / backoff policy (typed, bounded)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.observability.error_classification import ClassifiedError, is_retryable


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 5
    initial_backoff_sec: float = 1.0
    max_backoff_sec: float = 60.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.initial_backoff_sec < 0 or self.max_backoff_sec < 0:
            raise ValueError("backoff must be >= 0")
        if not 0.0 <= self.jitter_ratio <= 1.0:
            raise ValueError("jitter_ratio must be in [0, 1]")


# Operation-specific defaults (do not share blindly).
SQL_DEADLOCK_POLICY = RetryPolicy(max_attempts=5, initial_backoff_sec=0.2, max_backoff_sec=5.0)
PROVIDER_TIMEOUT_POLICY = RetryPolicy(max_attempts=4, initial_backoff_sec=1.0, max_backoff_sec=30.0)
UPLOAD_POLICY = RetryPolicy(max_attempts=3, initial_backoff_sec=0.5, max_backoff_sec=10.0)
ARTIFACT_PUBLICATION_POLICY = RetryPolicy(
    max_attempts=5, initial_backoff_sec=30.0, max_backoff_sec=1800.0, jitter_ratio=0.1
)
DEFAULT_TRANSIENT_POLICY = RetryPolicy()


@dataclass(frozen=True, slots=True)
class RetryDecision:
    should_retry: bool
    attempt: int
    max_attempts: int
    delay_sec: float
    reason_code: str


def decide_retry(
    *,
    classified: ClassifiedError,
    attempt: int,
    policy: RetryPolicy,
) -> RetryDecision:
    """attempt is 1-based count of tries already performed."""
    if attempt < 1:
        attempt = 1
    if not is_retryable(classified):
        return RetryDecision(
            should_retry=False,
            attempt=attempt,
            max_attempts=policy.max_attempts,
            delay_sec=0.0,
            reason_code=classified.reason_code,
        )
    if attempt >= policy.max_attempts:
        return RetryDecision(
            should_retry=False,
            attempt=attempt,
            max_attempts=policy.max_attempts,
            delay_sec=0.0,
            reason_code="RETRY_EXHAUSTED",
        )
    exp = policy.initial_backoff_sec * (2 ** max(0, attempt - 1))
    delay = min(exp, policy.max_backoff_sec)
    if policy.jitter_ratio > 0:
        jitter = delay * policy.jitter_ratio
        delay = max(0.0, delay + random.uniform(-jitter, jitter))
    return RetryDecision(
        should_retry=True,
        attempt=attempt,
        max_attempts=policy.max_attempts,
        delay_sec=delay,
        reason_code=classified.reason_code,
    )
