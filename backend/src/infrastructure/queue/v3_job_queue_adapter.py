"""
v3 JobQueue adapter.

The embedded worker consumes a simple in-memory queue of `job_id` strings.
This adapter must enqueue an already-persisted job_id (it must not generate job_id)
to avoid the race condition where the worker dequeues before the DB row exists.
"""

from __future__ import annotations

import logging

from src.config import load_settings
from src.jobs.queue import enqueue as legacy_enqueue

logger = logging.getLogger(__name__)


class V3JobQueueAdapter:
    """
    Implements application JobQueue port: enqueue(job_id) -> None.

Only job_id is enqueued to the legacy in-memory queue (local/dev compatibility).
    """

    def enqueue(self, job_id: str) -> None:
        settings = load_settings()
        if bool(
            getattr(settings, "sqlserver_enabled", False)
            and (getattr(settings, "sqlserver_connection_string", "") or "").strip()
        ):
            # In SQL mode, standalone/embedded workers claim from inventory_jobs.
            # Keep enqueue() as a no-op to avoid process-local queue coupling.
            logger.info("v3 job enqueue skipped in SQL mode: job_id=%s", str(job_id))
            return
        logger.info(
            "v3 job enqueued: job_id=%s",
            str(job_id),
        )
        legacy_enqueue(job_id)
