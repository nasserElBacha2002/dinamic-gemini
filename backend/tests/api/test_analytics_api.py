from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import get_aisle_repo, get_analytics_query_service
from src.api.server import app
from src.application.dto.analytics_dto import (
    AnalyticsSummaryDTO,
    InventoryPerformanceRowDTO,
    ManualInterventionBreakdownDTO,
    ManualInterventionCategoryDTO,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository


def _fake_admin():
    return AuthUser(id="admin", username="admin", role="admin")


class _StubAnalyticsService:
    def summary(self, _filters):
        return AnalyticsSummaryDTO(
            auto_acceptance_rate=0.6,
            manual_correction_rate=0.4,
            operator_marked_unknown_rate=0.2,
            operator_marked_unknown_count=1,
            unidentified_product_rate=0.3,
            unidentified_product_count=3,
            unknown_rate=0.2,
            unknown_count=1,
            invalid_traceability_rate=0.2,
            processing_success_rate=0.9,
            average_processing_time_seconds=600.0,
            average_processing_time_minutes=10.0,
            settling_actions_per_day=2.5,
            notes=["summary note"],
            period_day_count=2,
            settling_actions_count=5,
            positions_in_scope=10,
            total_positions_in_scope=10,
            processed_positions_count=8,
            reviewed_positions_count=5,
        )

    def trends(self, _filters):
        raise AssertionError("Not used in this test")

    def inventory_performance(self, _filters):
        now = datetime(2026, 4, 1, tzinfo=timezone.utc)
        return [
            InventoryPerformanceRowDTO(
                inventory_id="inv-1",
                inventory_name="Inventory A",
                inventory_created_at=now,
                total_aisles=3,
                aisles_count=3,
                total_positions=10,
                positions_count=10,
                processed_positions=8,
                processed_count=8,
                review_rate=0.5,
                correction_rate=0.4,
                auto_acceptance_rate=0.6,
                manual_correction_rate=0.4,
                operator_marked_unknown_rate=0.2,
                unidentified_product_rate=0.3,
                unknown_rate=0.2,
                invalid_traceability_rate=0.2,
                avg_confidence=0.9,
                processing_success_rate=0.95,
                average_processing_time_minutes=12.0,
            )
        ]

    def aisle_issues(self, _filters):
        raise AssertionError("Not used in this test")

    def quality_patterns(self, _filters):
        raise AssertionError("Not used in this test")

    def manual_intervention_breakdown(self, _filters):
        return ManualInterventionBreakdownDTO(
            reviewed_positions_count=5,
            intervention_positions_count=6,
            items=[
                ManualInterventionCategoryDTO(category="confirmed", count=2, percentage=2 / 6),
                ManualInterventionCategoryDTO(category="qty_corrected", count=1, percentage=1 / 6),
                ManualInterventionCategoryDTO(category="sku_corrected", count=1, percentage=1 / 6),
                ManualInterventionCategoryDTO(
                    category="invalid",
                    count=None,
                    percentage=None,
                    available=False,
                    notes="not available",
                ),
                ManualInterventionCategoryDTO(
                    category="operator_marked_unknown",
                    count=1,
                    percentage=1 / 6,
                    available=True,
                ),
                ManualInterventionCategoryDTO(category="deleted", count=2, percentage=2 / 6),
            ],
            notes=["breakdown note"],
        )


def test_analytics_summary_response_keeps_legacy_fields_and_adds_phase2_fields():
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_analytics_query_service] = lambda: _StubAnalyticsService()
    app.dependency_overrides[get_aisle_repo] = lambda: MemoryAisleRepository()
    try:
        client = TestClient(app)
        response = client.get("/api/v3/analytics/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["positions_in_scope"] == 10
    assert body["total_positions_in_scope"] == 10
    assert body["processed_positions_count"] == 8
    assert body["reviewed_positions_count"] == 5
    assert body["operator_marked_unknown_rate"] == 0.2
    assert body["operator_marked_unknown_count"] == 1
    assert body["unidentified_product_rate"] == 0.3
    assert body["unidentified_product_count"] == 3
    assert body["unknown_rate"] == 0.2
    assert body["unknown_count"] == 1
    assert body["average_processing_time_seconds"] == 600.0
    assert body["average_processing_time_minutes"] == 10.0


def test_analytics_inventory_performance_response_adds_phase2_fields_without_removing_legacy_fields():
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_analytics_query_service] = lambda: _StubAnalyticsService()
    app.dependency_overrides[get_aisle_repo] = lambda: MemoryAisleRepository()
    try:
        client = TestClient(app)
        response = client.get("/api/v3/analytics/inventories")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    row = response.json()["items"][0]
    assert row["total_aisles"] == 3
    assert row["aisles_count"] == 3
    assert row["total_positions"] == 10
    assert row["positions_count"] == 10
    assert row["processed_positions"] == 8
    assert row["processed_count"] == 8
    assert row["correction_rate"] == 0.4
    assert row["manual_correction_rate"] == 0.4
    assert row["operator_marked_unknown_rate"] == 0.2
    assert row["unidentified_product_rate"] == 0.3
    assert row["unknown_rate"] == 0.2
    assert row["auto_acceptance_rate"] == 0.6
    assert row["average_processing_time_minutes"] == 12.0


def test_manual_intervention_breakdown_exposes_unknown_and_keeps_invalid_explicit():
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_analytics_query_service] = lambda: _StubAnalyticsService()
    app.dependency_overrides[get_aisle_repo] = lambda: MemoryAisleRepository()
    try:
        client = TestClient(app)
        response = client.get("/api/v3/analytics/manual-interventions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["reviewed_positions_count"] == 5
    categories = {item["category"]: item for item in body["items"]}
    assert categories["confirmed"]["count"] == 2
    assert categories["qty_corrected"]["count"] == 1
    assert categories["sku_corrected"]["count"] == 1
    assert categories["deleted"]["count"] == 2
    assert categories["operator_marked_unknown"]["available"] is True
    assert categories["operator_marked_unknown"]["count"] == 1
    assert categories["invalid"]["available"] is False
