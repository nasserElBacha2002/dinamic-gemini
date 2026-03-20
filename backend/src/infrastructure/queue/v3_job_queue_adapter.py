"""
v3 JobQueue adapter.

The embedded worker consumes a simple in-memory queue of `job_id` strings.
This adapter must enqueue an already-persisted job_id (it must not generate job_id)
to avoid the race condition where the worker dequeues before the DB row exists.
"""

from __future__ import annotations

import logging

from src.jobs.queue import enqueue as legacy_enqueue

logger = logging.getLogger(__name__)


class V3JobQueueAdapter:
    """
    Implements application JobQueue port: enqueue(job_id) -> None.

Only job_id is enqueued to the legacy in-memory queue (local/dev compatibility).
    """

    def enqueue(self, job_id: str) -> None:
        logger.info(
            "v3 job enqueued: job_id=%s",
            str(job_id),
        )
        legacy_enqueue(job_id)
