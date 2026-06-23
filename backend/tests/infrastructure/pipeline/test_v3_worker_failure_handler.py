"""Unit tests for :class:`V3WorkerFailureHandler` (Phase 6 Step 7)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.domain.aisle.entities import Aisle, AisleStatus
from src.infrastructure.pipeline.v3_worker_failure_handler import (
    V3WorkerFailureHandler,
    V3WorkerFailureRequest,
)


def _aisle() -> Aisle:
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


def test_handle_unexpected_failure_marks_job_and_aisle_failed(tmp_path: Path) -> None:
    state = MagicMock()
    handler = V3WorkerFailureHandler(state_service=state)
    aisle = _aisle()
    error = RuntimeError("pipeline exploded")

    result = handler.handle_unexpected_failure(
        V3WorkerFailureRequest(
            job_id="job-fail",
            aisle=aisle,
            aisle_id=aisle.id,
            run_dir=tmp_path / "missing-run-dir",
            error=error,
        )
    )

    assert result is True
    state.fail_job_and_aisle.assert_called_once_with("job-fail", aisle, "pipeline exploded")


def test_handle_unexpected_failure_writes_execution_log_error(tmp_path: Path) -> None:
    state = MagicMock()
    handler = V3WorkerFailureHandler(state_service=state)
    aisle = _aisle()
    run_dir = tmp_path / "job-fail" / "run"
    run_dir.mkdir(parents=True)

    handler.handle_unexpected_failure(
        V3WorkerFailureRequest(
            job_id="job-fail",
            aisle=aisle,
            aisle_id=aisle.id,
            run_dir=run_dir,
            error=ValueError("bad value"),
        )
    )

    log_path = run_dir / "execution_log.jsonl"
    assert log_path.is_file()
    log_text = log_path.read_text(encoding="utf-8")
    assert "Job failed: bad value" in log_text
    assert "Pipeline" in log_text


def test_handle_unexpected_failure_swallows_execution_log_write_error(tmp_path: Path) -> None:
    state = MagicMock()
    handler = V3WorkerFailureHandler(state_service=state)
    aisle = _aisle()
    run_dir = tmp_path / "job-fail" / "run"
    run_dir.mkdir(parents=True)

    with patch(
        "src.infrastructure.pipeline.v3_worker_failure_handler.ExecutionLogWriter",
        side_effect=OSError("disk full"),
    ):
        result = handler.handle_unexpected_failure(
            V3WorkerFailureRequest(
                job_id="job-fail",
                aisle=aisle,
                aisle_id=aisle.id,
                run_dir=run_dir,
                error=RuntimeError("upstream"),
            )
        )

    assert result is True
    state.fail_job_and_aisle.assert_called_once_with("job-fail", aisle, "upstream")
