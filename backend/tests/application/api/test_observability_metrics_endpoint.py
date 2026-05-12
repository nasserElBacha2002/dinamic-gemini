"""HTTP tests for GET /api/v3/observability/metrics (Phase H5)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

if sys.version_info < (3, 10):
    pytest.skip("HTTP observability metrics tests require Python 3.10+.", allow_module_level=True)

from src.api.dependencies import get_observability_metrics_service
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser

client = TestClient(app)
_NOW = datetime(2026, 5, 11, tzinfo=timezone.utc)


def _admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


class _FixedMetricsSvc:
    def build(self, filters: Any) -> dict[str, Any]:
        return {
            "range": {"from": filters.created_from.isoformat(), "to": filters.created_to.isoformat()},
            "filters": {
                "client_id": filters.client_id,
                "client_supplier_id": filters.client_supplier_id,
                "provider_name": filters.provider_name,
                "model_name": filters.model_name,
            },
            "totals": {
                "runs_total": 2,
                "runs_succeeded": 1,
                "runs_failed": 1,
                "success_rate": 0.5,
                "failure_rate": 0.5,
                "fallback_runs": 0,
                "missing_prompt_config_runs": 0,
                "missing_reference_runs": 0,
                "legacy_runs": 1,
            },
            "by_client": [
                {
                    "client_id": "c1",
                    "runs_total": 2,
                    "runs_succeeded": 1,
                    "runs_failed": 1,
                    "failure_rate": 0.5,
                }
            ],
            "by_supplier": [
                {
                    "client_supplier_id": "s1",
                    "client_id": "c1",
                    "runs_total": 2,
                    "runs_succeeded": 1,
                    "runs_failed": 1,
                    "fallback_runs": 0,
                    "missing_reference_runs": 0,
                    "failure_rate": 0.5,
                }
            ],
            "by_provider_model": [
                {
                    "provider_name": "gemini",
                    "model_name": "m1",
                    "runs_total": 2,
                    "runs_succeeded": 1,
                    "runs_failed": 1,
                    "failure_rate": 0.5,
                }
            ],
            "data_quality": {
                "jobs_with_audit_snapshot": 1,
                "jobs_without_audit_snapshot": 1,
                "jobs_with_missing_metadata": 0,
                "artifact_dependent_jobs": 1,
            },
        }


def test_get_observability_metrics_200() -> None:
    app.dependency_overrides[get_current_admin] = _admin
    app.dependency_overrides[get_observability_metrics_service] = lambda: _FixedMetricsSvc()
    try:
        t0 = (_NOW - timedelta(days=7)).isoformat()
        t1 = _NOW.isoformat()
        r = client.get("/api/v3/observability/metrics", params={"from": t0, "to": t1})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["totals"]["runs_total"] == 2
        assert "by_client" in data and len(data["by_client"]) == 1
        assert "by_supplier" in data and len(data["by_supplier"]) == 1
        assert "by_provider_model" in data and len(data["by_provider_model"]) == 1
        assert data["data_quality"]["jobs_without_audit_snapshot"] == 1
    finally:
        app.dependency_overrides.pop(get_observability_metrics_service, None)
        app.dependency_overrides.pop(get_current_admin, None)


def test_get_observability_metrics_invalid_range_422() -> None:
    app.dependency_overrides[get_current_admin] = _admin
    app.dependency_overrides[get_observability_metrics_service] = lambda: _FixedMetricsSvc()
    try:
        t0 = _NOW.isoformat()
        t1 = (_NOW - timedelta(days=1)).isoformat()
        r = client.get("/api/v3/observability/metrics", params={"from": t0, "to": t1})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(get_observability_metrics_service, None)
        app.dependency_overrides.pop(get_current_admin, None)
