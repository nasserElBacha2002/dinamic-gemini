"""
JobQueue port — enqueue, dequeue (Stage 2.3.B).

Minimal queue contract for the current system. Implementations wrap in-memory or future persistent queue.
"""

from __future__ import annotations

from typing import Protocol


class JobQueue(Protocol):
    """
    Minimal queue contract for Stage B.

    This port intentionally does not model ack/nack/retry semantics yet. It is a transitional
    abstraction for the current in-memory job queue; future stages may extend it with
    acknowledge, negative-ack, or requeue operations.
    """

    def enqueue(self, job_id: str) -> None:
        """Add job_id to the queue."""
        ...

    def dequeue(self, timeout: float = 1.0) -> str | None:
        """Get next job_id or None if empty (block up to timeout seconds)."""
        ...
