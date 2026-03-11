"""
v3 JobQueue adapter — implements application port enqueue(job_type, payload) -> str.

Only job_id is enqueued to the legacy queue; job_type and payload are accepted for
API compatibility but are not used by the legacy worker. Consumption of v3 jobs
by legacy workers is deferred.
"""

from __future__ import annotations

import logging
import uuid

from src.jobs.queue import enqueue as legacy_enqueue

logger = logging.getLogger(__name__)


class V3JobQueueAdapter:
    """
    Implements application JobQueue port: enqueue(job_type, payload) -> job_id.

    Only the generated job_id is enqueued; job_type and payload are not passed to
    the legacy worker. Full v3 job consumption is deferred.
    """

    def enqueue(self, job_type: str, payload: dict) -> str:
        job_id = str(uuid.uuid4())
        payload_summary = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
        logger.info(
            "v3 job enqueued: job_id=%s job_type=%s payload_keys=%s",
            job_id,
            job_type,
            payload_summary,
        )
        legacy_enqueue(job_id)
        return job_id
