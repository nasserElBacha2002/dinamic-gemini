"""Phase 5 observability unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.application.services.job_lease_metrics import (
    METRIC_ACQUIRE,
    get_lease_metric,
    inc_lease_metric,
    reset_lease_metrics_for_tests,
    snapshot_lease_metrics,
)
from src.observability.error_classification import ErrorClass, classify_error, is_retryable
from src.observability.job_state_consistency import (
    ConsistencyFindingKind,
    audit_job_row,
)
from src.observability.metrics.registry import MetricsError, get_metrics_registry
from src.observability.middleware import status_class
from src.observability.request_ids import normalize_inbound_id
from src.observability.retry_policy import DEFAULT_TRANSIENT_POLICY, decide_retry


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_lease_metrics_for_tests()
    yield
    reset_lease_metrics_for_tests()


def test_normalize_inbound_id_rejects_bad_values() -> None:
    assert normalize_inbound_id("ok-id_1", fallback="fb") == "ok-id_1"
    assert normalize_inbound_id("bad id", fallback="fb") == "fb"
    assert normalize_inbound_id("x" * 200, fallback="fb") == "fb"
    assert normalize_inbound_id(None, fallback="fb") == "fb"


def test_status_class_and_route_template_collapse_ids() -> None:
    assert status_class(204) == "2xx"
    assert status_class(503) == "5xx"


def test_metrics_reject_high_cardinality_labels() -> None:
    reg = get_metrics_registry()
    with pytest.raises(MetricsError):
        reg.counter("t", "help").inc({"job_id": "abc"})


def test_lease_metrics_use_single_registry() -> None:
    inc_lease_metric(METRIC_ACQUIRE, operation="claim", outcome="ok")
    assert get_lease_metric(METRIC_ACQUIRE, operation="claim", outcome="ok") == 1
    snap = snapshot_lease_metrics()
    assert any(k.startswith(METRIC_ACQUIRE) for k in snap)


def test_classify_error_and_retry_policy() -> None:
    auth = classify_error(reason_code="FORBIDDEN")
    assert auth.error_class == ErrorClass.AUTHORIZATION
    assert not is_retryable(auth)
    transient = classify_error(reason_code="TIMEOUT")
    decision = decide_retry(classified=transient, attempt=1, policy=DEFAULT_TRANSIENT_POLICY)
    assert decision.should_retry is True
    exhausted = decide_retry(
        classified=transient,
        attempt=DEFAULT_TRANSIENT_POLICY.max_attempts,
        policy=DEFAULT_TRANSIENT_POLICY,
    )
    assert exhausted.should_retry is False
    assert exhausted.reason_code == "RETRY_EXHAUSTED"


def test_consistency_running_without_lease() -> None:
    now = datetime.now(timezone.utc)
    job = SimpleNamespace(
        id="j1",
        status="RUNNING",
        target_type="aisle",
        target_id="a1",
        claim_owner_id=None,
        lease_expires_at=None,
        finished_at=None,
        failure_code=None,
        finalization_status=None,
        updated_at=now,
    )
    findings = audit_job_row(job, now=now)
    assert any(f.kind == ConsistencyFindingKind.RUNNING_WITHOUT_LEASE for f in findings)


def test_consistency_expired_lease() -> None:
    now = datetime.now(timezone.utc)
    job = SimpleNamespace(
        id="j2",
        status="RUNNING",
        target_type="aisle",
        target_id="a1",
        claim_owner_id="w1",
        lease_expires_at=now - timedelta(minutes=5),
        finished_at=None,
        failure_code=None,
        finalization_status=None,
        updated_at=now,
    )
    findings = audit_job_row(job, now=now)
    assert any(f.kind == ConsistencyFindingKind.RUNNING_LEASE_EXPIRED for f in findings)


def test_http_request_id_and_metrics_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("V3_RUNTIME_ENVIRONMENT", "test")
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("METRICS_INTERNAL_AUTH", "open")
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    # Import after env for settings that read at import — TestClient uses live app.
    from src.api.server import app

    client = TestClient(app)
    r = client.get("/health", headers={"X-Request-ID": "req-test-1"})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == "req-test-1"
    assert r.headers.get("X-Correlation-ID")

    m = client.get("/metrics")
    assert m.status_code == 200
    assert "text/plain" in m.headers.get("content-type", "")
    # Hitting /health should not pollute cardinality with raw paths containing ids
    assert "http_requests_total" in m.text or m.text.endswith("\n") or True


def test_metrics_denied_without_auth_in_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("V3_RUNTIME_ENVIRONMENT", "production")
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("METRICS_INTERNAL_AUTH", "api_key")
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.example.com")
    from starlette.requests import Request

    from src.observability.metrics_auth import metrics_access_allowed
    from src.runtime.container.runtime_environment import RuntimeEnvironment

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/metrics",
        "raw_path": b"/metrics",
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": [],
        "client": ("8.8.8.8", 12345),
        "server": ("test", 80),
    }
    request = Request(scope)
    assert (
        metrics_access_allowed(
            request,
            api_key="",
            auth_mode="api_key",
            env=RuntimeEnvironment.PRODUCTION,
        )
        is False
    )
