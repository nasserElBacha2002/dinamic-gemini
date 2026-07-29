"""Phase 5 corrections — structured logging + correlation helpers."""

from __future__ import annotations

import json
import logging

from src.application.use_cases.recovery.recover_stale_job import (
    ensure_payload_correlation,
    job_correlation_id,
)
from src.domain.jobs.entities import Job, JobStatus
from src.observability.logging import log_event


def test_log_event_json_escapes_newlines_and_forging(caplog) -> None:
    caplog.set_level(logging.INFO, logger="dinamic.observability")
    log_event(
        "job_recovery_started",
        component="recovery",
        operation="recover",
        outcome="ok",
        actor="evil\nFAKE_EVENT actor=admin",
        reason_code="x\r\ninjected",
        password="should-never-appear",
    )
    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert "\n" not in payload["actor"]
    assert "\r" not in payload["reason_code"]
    assert "password" not in payload
    assert payload["event"] == "job_recovery_started"


def test_job_correlation_preserved_on_retry_payload() -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    job = Job(
        id="j1",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={"correlation_id": "root-corr-99", "aisle_id": "a1"},
        created_at=now,
        updated_at=now,
    )
    cid = job_correlation_id(job)
    assert cid == "root-corr-99"
    child_payload = ensure_payload_correlation({"aisle_id": "a1"}, cid)
    assert child_payload["correlation_id"] == "root-corr-99"
    # Jobs without correlation get a generated one
    job2 = Job(
        id="j2",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.QUEUED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    generated = job_correlation_id(job2)
    assert generated
    assert len(generated) >= 8
