"""Null-safe cost extraction for export summaries (no invented pricing)."""

from __future__ import annotations

from src.application.services.llm_cost_snapshot_public import llm_cost_snapshot_public_dict
from src.domain.jobs.entities import Job


def job_total_cost_string(job: Job | None) -> str:
    """Return persisted run total cost as string, or empty when unavailable."""
    if job is None:
        return ""
    result_json = job.result_json if isinstance(job.result_json, dict) else None
    snap = llm_cost_snapshot_public_dict(result_json)
    if not snap:
        return ""
    computed = snap.get("computed_cost")
    if not isinstance(computed, dict):
        return ""
    total = computed.get("total_cost")
    if total is None:
        return ""
    text = str(total).strip()
    return text
