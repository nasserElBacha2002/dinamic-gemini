"""Run-level metadata for aisle code scan read-only matching."""

from __future__ import annotations

from typing import Any


def matching_metadata_completed(
    *,
    scope: str,
    source: str,
    job_id: str | None,
    matched_count: int,
    no_match_count: int,
    multiple_candidates_count: int,
    not_evaluated_count: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "attempted": True,
        "status": "completed",
        "scope": scope,
        "source": source,
        "matched_count": matched_count,
        "no_match_count": no_match_count,
        "multiple_candidates_count": multiple_candidates_count,
        "not_evaluated_count": not_evaluated_count,
    }
    if job_id is not None:
        payload["job_id"] = job_id
    return payload


def matching_metadata_failed(*, scope: str, source: str, job_id: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "attempted": True,
        "status": "failed",
        "scope": scope,
        "source": source,
        "error": "matching_failed",
    }
    if job_id is not None:
        payload["job_id"] = job_id
    return payload


def matching_metadata_skipped(*, reason: str) -> dict[str, Any]:
    return {
        "attempted": False,
        "status": "skipped",
        "reason": reason,
    }


def merge_matching_into_run_metadata(
    metadata: dict[str, Any] | None,
    matching: dict[str, Any],
) -> dict[str, Any]:
    base = dict(metadata or {})
    base["matching"] = matching
    return base
