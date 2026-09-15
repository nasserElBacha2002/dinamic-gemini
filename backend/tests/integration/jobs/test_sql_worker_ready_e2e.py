"""SQL + worker_loop + /ready end-to-end readiness (Stage-1 corrections).

Skipped when SQL Server / ODBC is unavailable.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.schema_guard import schema_guard_state
from src.api.server import app
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
from src.jobs import job_store
from src.jobs.worker import worker_loop
from src.jobs.worker_runtime import (
    READY_REASON_JOB_WORKER_UNAVAILABLE,
    REASON_WORKER_STARTING,
    REASON_WORKER_STOPPING,
    WorkerLifecyclePhase,
    get_embedded_worker_runtime,
    reset_embedded_worker_runtime_for_tests,
)
from src.runtime.app_container import AppContainer
from src.runtime.container.repository_backend import RepositoryBackendStatus
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


@pytest.fixture(autouse=True)
def _reset_runtime():
    reset_embedded_worker_runtime_for_tests()
    job_store.reset_claim_throttle_for_tests()
    saved = dict(
        checked=schema_guard_state.checked,
        compatible=schema_guard_state.compatible,
        required_version=schema_guard_state.required_version,
        current_version=schema_guard_state.current_version,
        service=schema_guard_state.service,
        reason=schema_guard_state.reason,
    )
    schema_guard_state.checked = False
    schema_guard_state.compatible = True
    schema_guard_state.required_version = None
    schema_guard_state.current_version = None
    schema_guard_state.service = None
    schema_guard_state.reason = None
    yield
    runtime = get_embedded_worker_runtime()
    runtime.request_stop()
    runtime.join(timeout_sec=2.0)
    reset_embedded_worker_runtime_for_tests()
    for key, value in saved.items():
        setattr(schema_guard_state, key, value)


def test_sql_empty_inventory_jobs_worker_loop_ready_200(sql_client, monkeypatch) -> None:
    """Empty v3 queue + real SQL repo → first idle cycle → /ready 200."""
    repo = SqlJobRepository(sql_client)
    assert repo.claim_next_queued_job() is None

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: repo)
    monkeypatch.setattr(
        "src.jobs.job_store.load_settings",
        lambda: SimpleNamespace(
            sqlserver_enabled=True,
            sqlserver_connection_string=resolved_sqlserver_connection_string_for_tests(),
            legacy_stage8_sql_bridge_disabled=True,
            worker_stale_running_timeout_sec=0,
            worker_stale_reclaim_interval_sec=5,
        ),
    )
    status = RepositoryBackendStatus(
        mode="sql",
        environment="test",
        resolved=True,
        healthy=True,
        fallback_activated=False,
        reason_code=None,
    )
    monkeypatch.setattr(AppContainer, "get_repository_backend_status", lambda self: status)
    monkeypatch.setattr(
        AppContainer,
        "verify_position_materialization_recovery_schema",
        lambda self, force=False: None,
    )
    # Prevent API lifespan from starting a second embedded worker over our test thread.
    monkeypatch.setattr("src.api.server.start_worker", lambda: None)

    release_claim = threading.Event()
    real_cycle = job_store.claim_next_job_cycle

    def gated_cycle(base_path: Path):
        release_claim.wait(timeout=10.0)
        return real_cycle(base_path)

    monkeypatch.setattr("src.jobs.worker.claim_next_job_cycle", gated_cycle)

    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=True)
    thread = threading.Thread(
        target=lambda: worker_loop(Path("output"), stop=runtime.should_stop),
        daemon=True,
    )
    runtime.mark_started(thread)
    thread.start()

    client = TestClient(app)
    starting = client.get("/ready")
    assert starting.status_code == 503
    assert starting.json()["detail"] == REASON_WORKER_STARTING
    assert starting.json()["reason"] == READY_REASON_JOB_WORKER_UNAVAILABLE

    release_claim.set()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if runtime.snapshot().phase is WorkerLifecyclePhase.READY:
            break
        time.sleep(0.05)

    assert runtime.snapshot().phase is WorkerLifecyclePhase.READY
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    runtime.request_stop()
    runtime.join(timeout_sec=3.0)
    stopping = client.get("/ready")
    assert stopping.status_code == 503
    assert stopping.json()["detail"] == REASON_WORKER_STOPPING
