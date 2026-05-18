"""API tests for GET /api/v3/analytics/cost-summary."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from src.api.dependencies import get_analytics_cost_summary_service
from src.api.server import app
from src.application.dto.analytics_cost_dto import (
    AnalyticsCostByCaptureStatusDTO,
    AnalyticsCostSummaryDTO,
    AnalyticsCostSummaryScopeDTO,
    AnalyticsCostTotalsDTO,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser


def _fake_admin():
    return AuthUser(id="admin", username="admin", role="admin")


class _StubCostService:
    def validate_scope(self, _filters) -> None:
        return None

    def build(self, _filters) -> AnalyticsCostSummaryDTO:
        return AnalyticsCostSummaryDTO(
            scope=AnalyticsCostSummaryScopeDTO(
                date_from="2026-03-01",
                date_to="2026-03-10",
                inventory_id="inv-1",
                aisle_id=None,
                client_id=None,
                client_supplier_id=None,
                provider_name=None,
                model_name=None,
            ),
            totals=AnalyticsCostTotalsDTO(
                jobs_total=2,
                jobs_with_cost=1,
                jobs_without_cost=1,
                jobs_with_exact_cost=1,
                total_cost=Decimal("1.5"),
                total_counted_quantity=10,
                cost_per_counted_unit=Decimal("0.15"),
            ),
            by_capture_status=[
                AnalyticsCostByCaptureStatusDTO(capture_status="exact", jobs_total=1, total_cost=Decimal("1.5")),
                AnalyticsCostByCaptureStatusDTO(capture_status="missing", jobs_total=1, total_cost=None),
            ],
            warnings=["COST_SNAPSHOT_MISSING_FOR_SOME_JOBS"],
        )


def test_cost_summary_endpoint_shape() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_analytics_cost_summary_service] = lambda: _StubCostService()
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/v3/analytics/cost-summary",
            params={"inventory_id": "inv-1", "date_from": "2026-03-01", "date_to": "2026-03-10"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["totals"]["jobs_total"] == 2
        assert body["totals"]["total_cost"] == 1.5
        assert body["totals"]["total_counted_quantity"] == 10
        assert body["scope"]["inventory_id"] == "inv-1"
        assert "COST_SNAPSHOT_MISSING_FOR_SOME_JOBS" in body["warnings"]
        assert len(body["by_capture_status"]) == 2
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_analytics_cost_summary_service, None)


def test_existing_analytics_summary_still_works() -> None:
    from src.api.dependencies import get_analytics_query_service
    from src.application.dto.analytics_dto import AnalyticsSummaryDTO

    class _StubAnalytics:
        def validate_scope(self, _filters) -> None:
            return None

        def summary(self, _filters):
            return AnalyticsSummaryDTO()

        def trends(self, _filters):
            raise AssertionError("unused")

        def inventory_performance(self, _filters):
            return []

        def aisle_issues(self, _filters):
            return []

        def quality_patterns(self, _filters):
            return []

        def manual_intervention_breakdown(self, _filters):
            raise AssertionError("unused")

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_analytics_query_service] = lambda: _StubAnalytics()
    try:
        client = TestClient(app)
        resp = client.get("/api/v3/analytics/summary")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_analytics_query_service, None)
