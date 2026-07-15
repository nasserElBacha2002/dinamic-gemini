"""Unit tests for billable multi-run cost aggregation (cost ≠ operational count)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.application.services.billable_job_cost_aggregation import (
    billable_cost_for_job,
    export_cost_strings_by_aisle_id,
    export_inventory_total_cost_string,
    format_cost_decimal,
    sum_billable_costs_by_aisle_id,
)
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository

NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _cost_snapshot(total: str, status: str = "exact") -> dict:
    return {
        "llm_cost_snapshot": {
            "provider": "gemini",
            "model": "gemini-2.0",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cached_input_tokens": 0,
                "cache_write_tokens": 0,
                "thinking_tokens": 0,
                "tool_request_count": 0,
                "image_input_count": 0,
                "audio_input_tokens": 0,
                "video_input_tokens": 0,
            },
            "pricing_snapshot": {"billing_currency": "USD"},
            "computed_cost": {"total_cost": total, "currency": "USD"},
            "capture_status": status,
            "capture_notes": [],
        }
    }


def _job(
    job_id: str,
    aisle_id: str,
    *,
    cost: str | None,
    status: JobStatus = JobStatus.SUCCEEDED,
    capture: str = "exact",
    created_offset_sec: int = 0,
) -> Job:
    created = NOW.replace(second=min(created_offset_sec % 60, 59))
    result = _cost_snapshot(cost, capture) if cost is not None else None
    return Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=status,
        payload_json={},
        created_at=created,
        updated_at=created,
        finished_at=created
        if status
        in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELED,
            JobStatus.TIMED_OUT,
        }
        else None,
        result_json=result,
    )


def test_case1_single_run_cost() -> None:
    jobs = [_job("j1", "a1", cost="10")]
    assert sum_billable_costs_by_aisle_id(jobs)["a1"] == Decimal("10")


def test_case2_multiple_runs_sum_not_last_only() -> None:
    jobs = [
        _job("j1", "a1", cost="10", created_offset_sec=1),
        _job("j2", "a1", cost="15", created_offset_sec=2),
        _job("j3", "a1", cost="12", created_offset_sec=3),
    ]
    assert sum_billable_costs_by_aisle_id(jobs)["a1"] == Decimal("37")


def test_case3_equal_costs_not_sum_distinct() -> None:
    jobs = [
        _job("j1", "a1", cost="10", created_offset_sec=1),
        _job("j2", "a1", cost="10", created_offset_sec=2),
    ]
    assert sum_billable_costs_by_aisle_id(jobs)["a1"] == Decimal("20")


def test_case4_job_listed_many_times_still_costs_once() -> None:
    """Join-inflate guard: same job id appearing twice must not multiply cost."""
    j = _job("j1", "a1", cost="10")
    assert sum_billable_costs_by_aisle_id([j, j, j])["a1"] == Decimal("10")


def test_case5_test_aisle_same_accumulation() -> None:
    """Cost accumulation is by aisle job target; test vs production is inventory.mode."""
    jobs = [
        _job("j1", "test-aisle", cost="5"),
        _job("j2", "test-aisle", cost="8"),
    ]
    assert sum_billable_costs_by_aisle_id(jobs)["test-aisle"] == Decimal("13")


def test_more_than_500_runs_all_counted() -> None:
    repo = MemoryJobRepository()
    for i in range(501):
        repo.save(_job(f"j-{i}", "a1", cost="1", created_offset_sec=i % 60))
    assert export_cost_strings_by_aisle_id(repo, ["a1"])["a1"] == "501"
    assert export_inventory_total_cost_string(repo, ["a1"]) == "501"


def test_zero_cost_is_known_not_missing() -> None:
    assert billable_cost_for_job(_job("j0", "a1", cost="0")) == Decimal("0")
    assert sum_billable_costs_by_aisle_id([_job("j0", "a1", cost="0")])["a1"] == Decimal("0")


def test_timed_out_with_snapshot_is_billable() -> None:
    assert billable_cost_for_job(
        _job("jt", "a1", cost="2.5", status=JobStatus.TIMED_OUT)
    ) == Decimal("2.5")


def test_case7_queued_and_missing_snapshot_excluded() -> None:
    jobs = [
        _job("j-ok", "a1", cost="10", created_offset_sec=1),
        _job("j-queued", "a1", cost="99", status=JobStatus.QUEUED, created_offset_sec=2),
        _job("j-running", "a1", cost="88", status=JobStatus.RUNNING, created_offset_sec=3),
        _job("j-no-snap", "a1", cost=None, created_offset_sec=4),
        _job("j-unavail", "a1", cost="7", capture="unavailable", created_offset_sec=5),
    ]
    assert sum_billable_costs_by_aisle_id(jobs)["a1"] == Decimal("10")


def test_failed_with_snapshot_is_included() -> None:
    jobs = [
        _job("j1", "a1", cost="3", status=JobStatus.FAILED),
        _job("j2", "a1", cost="4", status=JobStatus.CANCELED),
    ]
    assert sum_billable_costs_by_aisle_id(jobs)["a1"] == Decimal("7")


def test_case8_inventory_total_across_aisles() -> None:
    repo = MemoryJobRepository()
    for job in (
        _job("a1j1", "a1", cost="10"),
        _job("a1j2", "a1", cost="10"),
        _job("a2j1", "a2", cost="30"),
        _job("a3j1", "a3", cost="5"),
        _job("a3j2", "a3", cost="8"),
    ):
        repo.save(job)
    by_aisle = export_cost_strings_by_aisle_id(repo, ["a1", "a2", "a3"])
    assert by_aisle["a1"] == "20"
    assert by_aisle["a2"] == "30"
    assert by_aisle["a3"] == "13"
    assert export_inventory_total_cost_string(repo, ["a1", "a2", "a3"]) == "63"


def test_format_and_billable_helpers() -> None:
    assert format_cost_decimal(Decimal("10.50000000")) == "10.5"
    assert format_cost_decimal(None) == ""
    assert billable_cost_for_job(_job("j1", "a1", cost="1.25")) == Decimal("1.25")
    assert billable_cost_for_job(_job("j1", "a1", cost="1", status=JobStatus.QUEUED)) is None
