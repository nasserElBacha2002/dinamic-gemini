"""
InMemoryJobQueue — implements JobQueue by delegating to the current queue module (Stage 2.3.B).
"""

from __future__ import annotations

from typing import Optional

from src.jobs.queue import dequeue as queue_dequeue
from src.jobs.queue import enqueue as queue_enqueue


class InMemoryJobQueue:
    """
    Implements the minimal JobQueue contract using the existing queue.enqueue / queue.dequeue.

    This is a transitional adapter for Stage B. It does not support ack/nack/retry; the current
    in-memory queue has no such semantics.
    """

    def enqueue(self, job_id: str) -> None:
        queue_enqueue(job_id)

    def dequeue(self, timeout: float = 1.0) -> Optional[str]:
        return queue_dequeue(timeout=timeout)
