"""Unit tests for :class:`V3CancellationCoordinator` (Phase 6 Step 4)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.domain.aisle.entities import Aisle, AisleStatus
from src.infrastructure.pipeline.v3_cancellation_coordinator import V3CancellationCoordinator
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.execution_log import ExecutionLogWriter


def _aisle() -> Aisle:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


def test_checkpoint_calls_raise_if_cancellation_requested_with_metadata(tmp_path: Path) -> None:
    state = MagicMock()
    coordinator = V3CancellationCoordinator(state_service=state)
    exec_log = ExecutionLogWriter(tmp_path)
    cancel_event_emitted = {"requested": False, "detected": False, "cancelled": False}

    checkpoint = coordinator.checkpoint(
        job_id="job-1",
        exec_log=exec_log,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        cancel_event_emitted=cancel_event_emitted,
    )
    checkpoint("Pipeline", "pre_pipeline", "Job canceled before pipeline execution")

    state.raise_if_cancellation_requested.assert_called_once_with(
        "job-1",
        exec_log=exec_log,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        stage="Pipeline",
        substep="pre_pipeline",
        reason="Job canceled before pipeline execution",
        cancel_event_emitted=cancel_event_emitted,
    )


def test_checkpoint_propagates_pipeline_cancellation_requested_error(tmp_path: Path) -> None:
    state = MagicMock()
    state.raise_if_cancellation_requested.side_effect = PipelineCancellationRequestedError(
        "cancel during checkpoint"
    )
    coordinator = V3CancellationCoordinator(state_service=state)
    exec_log = ExecutionLogWriter(tmp_path)
    cancel_event_emitted = {"requested": True, "detected": False, "cancelled": False}

    checkpoint = coordinator.checkpoint(
        job_id="job-1",
        exec_log=exec_log,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        cancel_event_emitted=cancel_event_emitted,
    )

    with pytest.raises(PipelineCancellationRequestedError, match="cancel during checkpoint"):
        checkpoint("Persist", "pre_persist", "Job canceled before persistence")


def test_handle_pipeline_cancellation_calls_cancel_job_and_aisle(tmp_path: Path) -> None:
    state = MagicMock()
    coordinator = V3CancellationCoordinator(state_service=state)
    exec_log = ExecutionLogWriter(tmp_path)
    aisle = _aisle()
    cancel_event_emitted = {"requested": True, "detected": True, "cancelled": False}
    error = PipelineCancellationRequestedError("cooperative cancel")

    result = coordinator.handle_pipeline_cancellation(
        job_id="job-1",
        aisle=aisle,
        error=error,
        exec_log=exec_log,
        cancel_event_emitted=cancel_event_emitted,
    )

    assert result is True
    state.cancel_job_and_aisle.assert_called_once_with(
        "job-1",
        aisle,
        "cooperative cancel",
        exec_log=exec_log,
        cancel_event_emitted=cancel_event_emitted,
    )


def test_handle_pipeline_cancellation_passes_cancel_event_emitted_unchanged(
    tmp_path: Path,
) -> None:
    state = MagicMock()
    coordinator = V3CancellationCoordinator(state_service=state)
    exec_log = ExecutionLogWriter(tmp_path)
    aisle = _aisle()
    cancel_event_emitted = {"requested": True, "detected": True, "cancelled": True}

    coordinator.handle_pipeline_cancellation(
        job_id="job-1",
        aisle=aisle,
        error=PipelineCancellationRequestedError("done"),
        exec_log=exec_log,
        cancel_event_emitted=cancel_event_emitted,
    )

    passed = state.cancel_job_and_aisle.call_args.kwargs["cancel_event_emitted"]
    assert passed is cancel_event_emitted
