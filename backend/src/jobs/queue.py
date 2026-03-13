"""Stage 7 — In-memory job queue (MVP)."""

import queue
import threading
from typing import Optional

# Single global queue; worker consumes from it
job_queue: queue.Queue = queue.Queue()


def enqueue(job_id: str) -> None:
    """Add job_id to the queue."""
    job_queue.put(job_id)


def dequeue(timeout: float = 1.0) -> Optional[str]:
    """Get next job_id or None if empty (block up to timeout seconds)."""
    try:
        return job_queue.get(timeout=timeout)
    except queue.Empty:
        return None
