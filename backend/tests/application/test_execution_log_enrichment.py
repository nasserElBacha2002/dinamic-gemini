"""Unit tests for execution log envelope + per-event derivation (filter/export)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.services.execution_log_enrichment import (
    _as_attempt,
    aisle_execution_log_attachment_filename,
    build_enriched_aisle_aggregated_execution_log,
    build_enriched_execution_log,
    execution_log_attachment_filename,
    extract_event_context,
    format_execution_log_plaintext,
    merge_raw_execution_log_events_by_ts,
    parse_ts_sort_key,
    sanitize_execution_log_filename_segment,
)


def test_extract_event_context_from_payload() -> None:
    jid, att, eid = extract_event_context(
        {"job_id": "job-a", "attempt": 2, "details": {"execution_id": "ex-9"}}
    )
    assert jid == "job-a"
    assert att == 2
    assert eid == "ex-9"


def test_extract_attempt_coerces_string() -> None:
    jid, att, eid = extract_event_context({"job_id": "j1", "attempt": "1"})
    assert att == 1
    assert eid is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        (True, None),
        (False, None),
        (-1, None),
        (0, 0),
        (1, 1),
        (1.0, 1),
        (1.5, None),
        ("", None),
        ("   ", None),
        ("0", 0),
        (" 1 ", 1),
        ("-1", None),
        ("abc", None),
    ],
)
def test_as_attempt_non_negative_semantics(raw: object, expected: int | None) -> None:
    """Regression guard for payload ``attempt`` coercion (code review B8.2)."""
    assert _as_attempt(raw) == expected


def test_extract_execution_id_top_level() -> None:
    assert extract_event_context({"execution_id": "top-ex"})[2] == "top-ex"


def test_build_enriched_mixed_jobs_preserves_order_and_flags() -> None:
    raw = [
        {
            "ts": "t1",
            "stage": "S",
            "level": "info",
            "message": "a",
            "payload": {"job_id": "job-req", "attempt": 1},
        },
        {
            "ts": "t2",
            "stage": "S",
            "level": "info",
            "message": "b",
            "payload": {"job_id": "job-other", "attempt": 1},
        },
        {
            "ts": "t3",
            "stage": "S",
            "level": "info",
            "message": "c",
            "payload": None,
        },
    ]
    out = build_enriched_execution_log(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        requested_job_id="job-req",
        raw_events=raw,
    )
    assert out["inventory_id"] == "inv-1"
    assert out["aisle_id"] == "aisle-1"
    assert out["requested_job_id"] == "job-req"
    assert set(out["available_job_ids"]) == {"job-req", "job-other"}
    assert out["available_attempts"] == [1]
    evs = out["events"]
    assert len(evs) == 3
    assert evs[0]["is_requested_job_event"] is True
    assert evs[1]["is_requested_job_event"] is False
    assert evs[2]["is_requested_job_event"] is False
    assert evs[2]["event_job_id"] is None


def test_build_enriched_legacy_no_job_ids_all_requested() -> None:
    raw = [
        {
            "ts": "t1",
            "stage": "S",
            "level": "info",
            "message": "m",
            "payload": {"foo": 1},
        },
    ]
    out = build_enriched_execution_log(
        inventory_id="inv",
        aisle_id="aisle",
        requested_job_id="job-x",
        raw_events=raw,
    )
    assert out["events"][0]["is_requested_job_event"] is True
    assert out["events"][0]["event_job_id"] is None
    assert out["available_job_ids"] == ["job-x"]


def test_sanitize_filename_segment_replaces_unsafe_chars() -> None:
    assert sanitize_execution_log_filename_segment("inv/x") == "inv_x"
    assert sanitize_execution_log_filename_segment("a:b*c?d") == "a_b_c_d"
    assert sanitize_execution_log_filename_segment("") == "unknown"
    assert ".." not in sanitize_execution_log_filename_segment("../etc/passwd")


def test_attachment_filename_uses_sanitized_segments() -> None:
    fn = execution_log_attachment_filename("inv/1", 'aisle"2', "job|3")
    # Pattern is inventory_<id>_aisle_<id>_job_<id>_...; slashes/quotes/pipes become underscores.
    assert fn == "inventory_inv_1_aisle_aisle_2_job_job_3_execution_log.txt"
    assert "../" not in fn
    assert ".." not in fn


def test_merge_orders_by_ts_then_job_created_then_line() -> None:
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    same_ts = "2024-06-01T10:00:00+00:00"
    job_old = (
        "job-old",
        t0,
        [
            {"ts": same_ts, "stage": "S", "level": "info", "message": "a", "payload": None},
            {
                "ts": "2024-06-01T11:00:00+00:00",
                "stage": "S",
                "level": "info",
                "message": "c",
                "payload": None,
            },
        ],
    )
    job_new = (
        "job-new",
        t1,
        [{"ts": same_ts, "stage": "S", "level": "info", "message": "b", "payload": None}],
    )
    merged, owners = merge_raw_execution_log_events_by_ts([job_new, job_old])
    assert [e["message"] for e in merged] == ["a", "b", "c"]
    assert owners == ["job-old", "job-new", "job-old"]


def test_aisle_aggregate_suppresses_requested_flags_and_seeds_job_ids() -> None:
    raw = [
        {"ts": "t1", "stage": "S", "level": "info", "message": "x", "payload": None},
    ]
    out = build_enriched_aisle_aggregated_execution_log(
        inventory_id="inv",
        aisle_id="aisle",
        raw_events=raw,
        artifact_owner_job_ids=["job-a"],
        seed_job_ids=["job-a", "job-b"],
        jobs=[{"job_id": "job-a"}],
        log_sources=[{"job_id": "job-a", "status": "ok", "detail": None}],
    )
    assert out["requested_job_id"] is None
    assert out["events"][0]["event_job_id"] == "job-a"
    assert out["events"][0]["is_requested_job_event"] is False
    assert set(out["available_job_ids"]) == {"job-a", "job-b"}


def test_aisle_attachment_filename() -> None:
    assert (
        aisle_execution_log_attachment_filename("inv/x", 'aisle"y')
        == "inventory_inv_x_aisle_aisle_y_execution_log.txt"
    )


def test_parse_ts_sort_key_malformed_not_crashing() -> None:
    q, _, raw = parse_ts_sort_key("not-a-date")
    assert q == 2
    assert raw == "not-a-date"


def test_format_plaintext_includes_blank_separators() -> None:
    events = [
        {
            "ts": "2026-04-07T11:44:41+00:00",
            "stage": "WorkerLaunch",
            "level": "info",
            "message": "job.spawn_succeeded",
            "payload": {"job_id": "j1", "attempt": 1},
            "event_job_id": "j1",
            "event_attempt": 1,
            "event_execution_id": None,
            "is_requested_job_event": True,
        },
        {
            "ts": "2026-04-07T11:44:42+00:00",
            "stage": "X",
            "level": "warning",
            "message": "noop",
            "payload": None,
            "event_job_id": None,
            "event_attempt": None,
            "event_execution_id": None,
            "is_requested_job_event": True,
        },
    ]
    text = format_execution_log_plaintext(events)
    assert "[2026-04-07T11:44:41+00:00]" in text
    assert "stage=WorkerLaunch" in text
    assert "job_id=j1" in text
    assert "attempt=1" in text
    assert "message=job.spawn_succeeded" in text
    assert "payload=" in text
    assert "\n\n" in text
    assert "message=noop" in text
