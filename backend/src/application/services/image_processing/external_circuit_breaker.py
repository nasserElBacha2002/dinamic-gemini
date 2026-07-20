"""Phase 5 — process-local circuit breaker with CLOSED / OPEN / HALF_OPEN.

Limitation: not shared across worker processes. Key = provider + model + profile.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class _BreakerBucket:
    failures: int = 0
    opened_at: float | None = None
    state: CircuitState = CircuitState.CLOSED
    half_open_probe_held: bool = False


class ExternalCircuitBreaker:
    """Allows exactly one probe when transitioning OPEN → HALF_OPEN after cooldown."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        profile: str = "default",
    ) -> None:
        self._threshold = max(1, int(failure_threshold))
        self._cooldown = max(1.0, float(cooldown_seconds))
        self._profile = (profile or "default").strip().lower() or "default"
        self._states: dict[str, _BreakerBucket] = {}
        self._lock = threading.Lock()

    def _key(self, provider: str, model: str) -> str:
        return (
            f"{(provider or '').strip().lower()}:"
            f"{(model or '').strip().lower()}:"
            f"{self._profile}"
        )

    def state_of(self, provider: str, model: str) -> CircuitState:
        with self._lock:
            bucket = self._states.get(self._key(provider, model))
            if bucket is None:
                return CircuitState.CLOSED
            if bucket.state is CircuitState.OPEN and bucket.opened_at is not None:
                if (time.monotonic() - bucket.opened_at) >= self._cooldown:
                    return CircuitState.HALF_OPEN
            return bucket.state

    def is_open(self, provider: str, model: str) -> bool:
        """True when callers must not start a provider call (OPEN, cooldown not elapsed).

        Does not acquire the half-open probe — use :meth:`try_acquire_call` immediately
        before the provider invocation.
        """
        key = self._key(provider, model)
        with self._lock:
            bucket = self._states.get(key)
            if bucket is None or bucket.state is CircuitState.CLOSED:
                return False
            if bucket.state is CircuitState.HALF_OPEN:
                return bucket.half_open_probe_held
            # OPEN
            if bucket.opened_at is None:
                return True
            if (time.monotonic() - bucket.opened_at) < self._cooldown:
                return True
            # Cooldown elapsed: not blocking until probe is acquired by another caller.
            return False

    def try_acquire_call(self, provider: str, model: str) -> bool:
        """Return True if this caller may invoke the provider (grants the half-open probe)."""
        key = self._key(provider, model)
        with self._lock:
            bucket = self._states.setdefault(key, _BreakerBucket())
            now = time.monotonic()
            if bucket.state is CircuitState.CLOSED:
                return True
            if bucket.state is CircuitState.OPEN:
                if bucket.opened_at is None or (now - bucket.opened_at) < self._cooldown:
                    return False
                bucket.state = CircuitState.HALF_OPEN
                bucket.half_open_probe_held = True
                return True
            if bucket.state is CircuitState.HALF_OPEN:
                if bucket.half_open_probe_held:
                    return False
                bucket.half_open_probe_held = True
                return True
            return False

    def record_success(self, provider: str, model: str) -> None:
        key = self._key(provider, model)
        with self._lock:
            self._states[key] = _BreakerBucket(state=CircuitState.CLOSED)

    def record_failure(self, provider: str, model: str) -> None:
        key = self._key(provider, model)
        with self._lock:
            bucket = self._states.setdefault(key, _BreakerBucket())
            if bucket.state is CircuitState.HALF_OPEN:
                bucket.state = CircuitState.OPEN
                bucket.opened_at = time.monotonic()
                bucket.half_open_probe_held = False
                bucket.failures = self._threshold
                return
            bucket.failures += 1
            if bucket.failures >= self._threshold:
                bucket.state = CircuitState.OPEN
                bucket.opened_at = time.monotonic()
                bucket.half_open_probe_held = False


__all__ = ["CircuitState", "ExternalCircuitBreaker"]
