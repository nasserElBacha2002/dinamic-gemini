"""Unit tests for :class:`V3JobMonitoringService` (Phase 6 Step 3)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_monitoring_service import (
    RUN_ID,
    V3JobMonitoringRequest,
    V3JobMonitoringService,
)


def _monitoring_request(tmp_path: Path) -> V3JobMonitoringRequest:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "mon-job"
    aisle_id = "aisle-1"
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
        execution_id="ex-mon",
    )
    aisle = Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return V3JobMonitoringRequest(
        base_path=tmp_path,
        job_id=job_id,
        job_dir=job_dir,
        job=job,
        aisle=aisle,
        aisle_id=aisle_id,
    )


def test_session_creates_run_dir_and_execution_log(tmp_path: Path) -> None:
    state = MagicMock()
    service = V3JobMonitoringService(state_service=state, heartbeat_interval_sec=60)
    req = _monitoring_request(tmp_path)

    with service.session(req) as handles:
        assert handles.run_dir == tmp_path / req.job_id / RUN_ID
        assert handles.exec_log is not None
        assert handles.cancel_event_emitted == {
            "requested": False,
            "detected": False,
            "cancelled": False,
        }

    log_path = handles.run_dir / "execution_log.jsonl"
    assert log_path.exists()
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert events, "execution log should contain at least one event"
    spawn_event = next(
        event for event in events if event.get("message") == "job.spawn_succeeded"
    )
    assert spawn_event["stage"] == "WorkerLaunch"
    payload = spawn_event["payload"]
    assert payload is not None
    assert payload["substep"] == "startup_confirmation"
    assert payload["event"] == "job.spawn_succeeded"
    assert payload["details"]["execution_id"] == req.job.execution_id


def test_heartbeat_thread_calls_state_heartbeat(tmp_path: Path) -> None:
    state = MagicMock()
    state.heartbeat.return_value = MagicMock(attempt_count=1, current_stage="Pipeline")
    service = V3JobMonitoringService(state_service=state, heartbeat_interval_sec=0.001)
    req = _monitoring_request(tmp_path)

    with service.session(req) as handles:
        time.sleep(0.05)
        assert handles.heartbeat_thread.is_alive()
        assert state.heartbeat.call_count >= 1
        assert handles.heartbeat_thread.name == f"job-heartbeat-{req.job_id}"
        assert handles.heartbeat_thread.daemon is True


def test_heartbeat_continues_when_state_returns_none(tmp_path: Path) -> None:
    state = MagicMock()
    state.heartbeat.return_value = None
    service = V3JobMonitoringService(state_service=state, heartbeat_interval_sec=0.001)
    req = _monitoring_request(tmp_path)

    with service.session(req) as handles:
        time.sleep(0.05)
        assert state.heartbeat.call_count >= 1
        assert handles.heartbeat_thread.is_alive()

    assert not handles.heartbeat_thread.is_alive()


def test_session_stops_and_joins_heartbeat_on_success(tmp_path: Path) -> None:
    state = MagicMock()
    service = V3JobMonitoringService(state_service=state, heartbeat_interval_sec=60)
    req = _monitoring_request(tmp_path)

    with service.session(req) as handles:
        thread = handles.heartbeat_thread
        assert thread.is_alive()

    assert not thread.is_alive()


def test_session_stops_and_joins_heartbeat_when_block_raises(tmp_path: Path) -> None:
    state = MagicMock()
    service = V3JobMonitoringService(state_service=state, heartbeat_interval_sec=60)
    req = _monitoring_request(tmp_path)
    thread = None

    with pytest.raises(RuntimeError, match="simulated failure"):
        with service.session(req) as handles:
            thread = handles.heartbeat_thread
            raise RuntimeError("simulated failure")

    assert thread is not None
    assert not thread.is_alive()
