"""
Build aisle-level aggregated execution log payloads (multi-job merge) for v3 API responses.

Artifact I/O stays in the API layer: callers pass ``try_read_events`` that wraps
``read_execution_log_events_for_job`` and maps storage errors to per-job status rows.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from src.application.services.execution_log_enrichment import (
    build_enriched_aisle_aggregated_execution_log,
    merge_raw_execution_log_events_by_ts,
)
from src.domain.jobs.entities import Job

AGGREGATE_AISLE_EXECUTION_LOG_JOBS_LIMIT = 500

# (raw_events or None if skipped, log_sources row for this job)
TryReadJobEventsFn = Callable[[Job], tuple[list[dict[str, Any]] | None, dict[str, Any]]]


def job_execution_log_meta_row(job: Job) -> dict[str, Any]:
    """One row in the ``jobs`` array inside the aggregated execution log envelope."""
    return {
        "job_id": job.id,
        "provider_name": job.provider_name,
        "model_name": job.model_name,
        "prompt_key": job.prompt_key,
        "prompt_version": job.prompt_version,
        "execution_id": job.execution_id,
    }


def aggregate_aisle_execution_log_payload(
    *,
    inventory_id: str,
    aisle_id: str,
    jobs: Sequence[Job],
    try_read_events: TryReadJobEventsFn,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Merge JSONL execution logs for all ``jobs``; per-job read failures are non-fatal."""
    log_sources: list[dict[str, Any]] = []
    streams: list[tuple[str, Any, list[dict[str, Any]]]] = []

    for job in jobs:
        raw, src = try_read_events(job)
        log_sources.append(src)
        if raw is not None:
            streams.append((job.id, job.created_at, raw))

    merged_events, owners = merge_raw_execution_log_events_by_ts(streams)
    seed_ids = [j.id for j in jobs]
    jobs_meta = [job_execution_log_meta_row(j) for j in jobs]
    return build_enriched_aisle_aggregated_execution_log(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        raw_events=merged_events,
        artifact_owner_job_ids=owners,
        seed_job_ids=seed_ids,
        jobs=jobs_meta,
        log_sources=log_sources,
    )
