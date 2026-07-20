"""Phase 5 — bounded concurrency for external fallback calls."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class ExternalConcurrencyLimiter:
    """Process-local semaphore for external provider calls."""

    def __init__(self, max_concurrency: int = 1) -> None:
        self._sem = threading.Semaphore(max(1, int(max_concurrency)))

    @contextmanager
    def acquire(self, timeout: float | None = None) -> Iterator[bool]:
        acquired = self._sem.acquire(timeout=timeout if timeout is not None else None)
        try:
            yield acquired
        finally:
            if acquired:
                self._sem.release()


__all__ = ["ExternalConcurrencyLimiter"]
