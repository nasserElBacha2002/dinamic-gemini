"""Wall-clock execution duration helpers for benchmark compare payloads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.application.use_cases.benchmark_compare_support import (
    format_execution_duration_human,
    job_execution_duration_human,
    job_execution_duration_seconds,
)
from src.domain.jobs.entities import Job, JobStatus


def _job(
    *,
    started_at: datetime | None,
    finished_at: datetime | None,
) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id="j1",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
        started_at=started_at,
        finished_at=finished_at,
    )


def test_job_execution_duration_seconds_none_when_missing_timestamps() -> None:
    now = datetime.now(timezone.utc)
    assert job_execution_duration_seconds(_job(started_at=None, finished_at=now)) is None
    assert job_execution_duration_seconds(_job(started_at=now, finished_at=None)) is None


def test_job_execution_duration_seconds_none_when_inverted_range() -> None:
    now = datetime.now(timezone.utc)
    assert (
        job_execution_duration_seconds(
            _job(started_at=now + timedelta(seconds=10), finished_at=now),
        )
        is None
    )


def test_job_execution_duration_seconds_happy_path() -> None:
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert job_execution_duration_seconds(_job(started_at=t0, finished_at=t0 + timedelta(seconds=12.4))) == pytest.approx(
        12.4
    )


def test_format_execution_duration_human_subminute() -> None:
    assert format_execution_duration_human(12.4) == "12.4s"
    assert format_execution_duration_human(60.0) == "1m"


def test_format_execution_duration_human_minutes() -> None:
    assert format_execution_duration_human(62.0) == "1m 02s"


def test_job_execution_duration_human_matches_seconds() -> None:
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    j = _job(started_at=t0, finished_at=t0 + timedelta(seconds=5))
    assert job_execution_duration_seconds(j) == pytest.approx(5.0)
    assert job_execution_duration_human(j) == "5s"
