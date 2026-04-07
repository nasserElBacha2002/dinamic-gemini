"""Unit tests for execution log envelope + per-event derivation (filter/export)."""

from __future__ import annotations

from src.application.services.execution_log_enrichment import (
    build_enriched_execution_log,
    extract_event_context,
    format_execution_log_plaintext,
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
