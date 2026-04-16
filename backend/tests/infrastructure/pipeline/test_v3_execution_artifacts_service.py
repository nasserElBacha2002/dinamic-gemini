"""Tests for :class:`V3ExecutionArtifactsService` (durable upload delegation)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.pipeline.v3_execution_artifacts_service import V3ExecutionArtifactsService


def test_require_store_raises_when_not_configured() -> None:
    svc = V3ExecutionArtifactsService(None)
    with pytest.raises(RuntimeError, match="Artifact store not configured"):
        svc.require_store()


def test_publish_worker_durables_delegates_to_publisher() -> None:
    store = MagicMock()
    svc = V3ExecutionArtifactsService(store)
    run_dir = Path("/tmp/run")
    with patch(
        "src.infrastructure.pipeline.v3_execution_artifacts_service.publish_worker_durable_artifacts",
        return_value={"execution_log": {"storage_key": "k"}},
    ) as pub:
        svc.require_store()
        out = svc.publish_worker_durables(job_id="j1", run_segment="run", run_dir=run_dir)
    pub.assert_called_once_with(store, job_id="j1", run_segment="run", run_dir=run_dir)
    assert out == {"execution_log": {"storage_key": "k"}}
