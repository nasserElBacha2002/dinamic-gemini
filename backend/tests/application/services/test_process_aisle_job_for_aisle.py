"""Regression tests for ``require_process_aisle_job_for_aisle`` (Phase 11 shared helper).

Messages must stay aligned with historical Cancel/Retry inline checks so HTTP 404/422
mapping remains stable.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import AisleNotFoundError
from src.application.services.process_aisle_job_for_aisle import (
    require_process_aisle_job_for_aisle,
)
from src.domain.jobs.entities import Job, JobStatus


class _JobRepoStub:
    def __init__(self, jobs: dict[str, Job]) -> None:
        self._jobs = jobs

    def get_by_id(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)


def _job(
    *,
    job_id: str,
    target_id: str = "aisle-1",
    job_type: str = "process_aisle",
) -> Job:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Job(
        id=job_id,
        target_type="aisle",
        target_id=target_id,
        job_type=job_type,
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )


def test_require_process_aisle_job_missing_raises_with_stable_message() -> None:
    repo = _JobRepoStub({})
    with pytest.raises(
        AisleNotFoundError,
        match=r"^Job missing-id not found for aisle aisle-1$",
    ):
        require_process_aisle_job_for_aisle(repo, job_id="missing-id", aisle_id="aisle-1")


def test_require_process_aisle_job_wrong_target_raises_with_stable_message() -> None:
    repo = _JobRepoStub({"j1": _job(job_id="j1", target_id="other-aisle")})
    with pytest.raises(
        AisleNotFoundError,
        match=r"^Job j1 does not belong to aisle aisle-1$",
    ):
        require_process_aisle_job_for_aisle(repo, job_id="j1", aisle_id="aisle-1")


def test_require_process_aisle_job_wrong_type_raises_value_error_with_stable_message() -> None:
    repo = _JobRepoStub({"j1": _job(job_id="j1", job_type="other_job")})
    with pytest.raises(
        ValueError,
        match=r"^Job j1 is not a process_aisle job$",
    ):
        require_process_aisle_job_for_aisle(repo, job_id="j1", aisle_id="aisle-1")


def test_require_process_aisle_job_returns_row_when_valid() -> None:
    row = _job(job_id="j1")
    repo = _JobRepoStub({"j1": row})
    assert require_process_aisle_job_for_aisle(repo, job_id="j1", aisle_id="aisle-1") is row
