"""Phase 5 — in-process circuit breaker for external fallback providers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class CircuitBreakerState:
    failures: int = 0
    opened_at: float | None = None


class ExternalCircuitBreaker:
    """Process-local circuit breaker keyed by ``provider:model``.

    Limitation (documented): not shared across worker processes. Sufficient for a single
    worker process / concurrency within one process.
    """

    def __init__(self, *, failure_threshold: int = 5, cooldown_seconds: float = 60.0) -> None:
        self._threshold = max(1, int(failure_threshold))
        self._cooldown = max(1.0, float(cooldown_seconds))
        self._states: dict[str, CircuitBreakerState] = {}
        self._lock = threading.Lock()

    def _key(self, provider: str, model: str) -> str:
        return f"{(provider or '').strip().lower()}:{(model or '').strip().lower()}"

    def is_open(self, provider: str, model: str) -> bool:
        key = self._key(provider, model)
        with self._lock:
            state = self._states.get(key)
            if state is None or state.opened_at is None:
                return False
            if (time.monotonic() - state.opened_at) >= self._cooldown:
                # Half-open: allow one probe by resetting open state.
                state.opened_at = None
                state.failures = 0
                return False
            return True

    def record_success(self, provider: str, model: str) -> None:
        key = self._key(provider, model)
        with self._lock:
            self._states[key] = CircuitBreakerState()

    def record_failure(self, provider: str, model: str) -> None:
        key = self._key(provider, model)
        with self._lock:
            state = self._states.setdefault(key, CircuitBreakerState())
            state.failures += 1
            if state.failures >= self._threshold and state.opened_at is None:
                state.opened_at = time.monotonic()


__all__ = ["ExternalCircuitBreaker"]
