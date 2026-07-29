"""Phase 2 — ``/health`` and ``/ready`` must reflect real repository backend status.

``/health`` is liveness only (``ok`` always True) but must never look "all fine" when the
repository backend is unresolved — it surfaces ``repository_backend_resolved`` /
``repository_backend_healthy`` / ``repository_backend_reason_code`` and must never leak secrets
(connection strings, credentials, raw probe exception text).

``/ready`` is the actual readiness gate: 503 for schema incompatibility *or* an unresolved /
unhealthy repository backend (SQL required but unavailable, MEMORY_ONLY forbidden for the
environment, MEMORY_FALLBACK forbidden for the environment). No bare
``except Exception: return 200`` — the endpoint calls the public, non-raising
``AppContainer.get_repository_backend_status()`` API.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.schema_guard import schema_guard_state
from src.api.server import app
from src.runtime.app_container import AppContainer
from src.runtime.container.repository_backend import RepositoryBackendStatus

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_schema_guard_state() -> Iterator[None]:
    """``schema_guard_state`` is a process-wide singleton mutated by other test modules."""
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
    for key, value in saved.items():
        setattr(schema_guard_state, key, value)


def _mock_backend_status(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str | None,
    environment: str,
    resolved: bool,
    healthy: bool,
    fallback_activated: bool = False,
    reason_code: str | None = None,
) -> RepositoryBackendStatus:
    status = RepositoryBackendStatus(
        mode=mode,
        environment=environment,
        resolved=resolved,
        healthy=healthy,
        fallback_activated=fallback_activated,
        reason_code=reason_code,
    )
    monkeypatch.setattr(AppContainer, "get_repository_backend_status", lambda self: status)
    return status


def test_ready_503_production_sql_probe_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_backend_status(
        monkeypatch,
        mode=None,
        environment="production",
        resolved=False,
        healthy=False,
        reason_code="REPOSITORY_BACKEND_RESOLUTION_FAILED",
    )
    resp = client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ok"] is False
    assert body["reason"] == "REPOSITORY_BACKEND_UNAVAILABLE"
    assert body["repository_backend_reason_code"] == "REPOSITORY_BACKEND_RESOLUTION_FAILED"


def test_ready_503_staging_memory_only_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_backend_status(
        monkeypatch,
        mode="memory_only",
        environment="staging",
        resolved=False,
        healthy=False,
        reason_code="REPOSITORY_BACKEND_MODE_FORBIDDEN",
    )
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "REPOSITORY_BACKEND_UNAVAILABLE"


def test_ready_503_unknown_environment_sql_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_backend_status(
        monkeypatch,
        mode="memory_only",
        environment="unknown",
        resolved=False,
        healthy=False,
        reason_code="REPOSITORY_BACKEND_MODE_FORBIDDEN",
    )
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "REPOSITORY_BACKEND_UNAVAILABLE"


def test_ready_200_local_memory_only_when_schema_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_backend_status(
        monkeypatch,
        mode="memory_only",
        environment="local",
        resolved=True,
        healthy=True,
    )
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_ready_200_production_sql_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_backend_status(
        monkeypatch,
        mode="sql",
        environment="production",
        resolved=True,
        healthy=True,
    )
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_ready_503_schema_incompatible_even_when_backend_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema guard is checked before the repository backend — both must be green for 200."""
    _mock_backend_status(
        monkeypatch,
        mode="sql",
        environment="production",
        resolved=True,
        healthy=True,
    )
    schema_guard_state.checked = True
    schema_guard_state.compatible = False
    schema_guard_state.service = "inventory-api"
    schema_guard_state.required_version = "0003"
    schema_guard_state.current_version = "0002"
    schema_guard_state.reason = "database schema version 0002 is behind required version 0003"

    resp = client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["reason"] == "SCHEMA_INCOMPATIBLE"


def test_health_never_leaks_secrets_and_shows_resolved_false_when_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_backend_status(
        monkeypatch,
        mode=None,
        environment="production",
        resolved=False,
        healthy=False,
        reason_code="REPOSITORY_BACKEND_RESOLUTION_FAILED",
    )
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    # Liveness always True — a dead process cannot even serve this response.
    assert body["ok"] is True
    assert body["repository_backend"] is None
    assert body["repository_backend_resolved"] is False
    assert body["repository_backend_healthy"] is False
    assert body["repository_backend_reason_code"] == "REPOSITORY_BACKEND_RESOLUTION_FAILED"

    dump = json.dumps(body)
    for secret_marker in ("Pwd=", "pwd=", "Password=", "password=", "Uid=", "Driver=", "://"):
        assert secret_marker not in dump


def test_health_reports_resolved_healthy_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_backend_status(
        monkeypatch,
        mode="memory_fallback",
        environment="local",
        resolved=True,
        healthy=True,
        fallback_activated=True,
        reason_code="SQL_PROBE_FAILED_MEMORY_FALLBACK_ACTIVE",
    )
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["repository_backend"] == "memory_fallback"
    assert body["repository_backend_resolved"] is True
    assert body["repository_backend_healthy"] is True
    assert body["fallback_activated"] is True
    assert body["repository_backend_reason_code"] == "SQL_PROBE_FAILED_MEMORY_FALLBACK_ACTIVE"
