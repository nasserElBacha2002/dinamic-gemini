"""API tests for GET /api/v3/analytics/cost-summary."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.api.constants.error_wire import (
    HTTP_DETAIL_ANALYTICS_DATE_FROM_MUST_BE_ON_OR_BEFORE_DATE_TO,
)
from src.api.dependencies import get_analytics_cost_summary_service, get_aisle_repo
from src.api.server import app
from src.application.dto.analytics_cost_dto import (
    AnalyticsCostByCaptureStatusDTO,
    AnalyticsCostByProviderModelDTO,
    AnalyticsCostSummaryDTO,
    AnalyticsCostSummaryScopeDTO,
    AnalyticsCostTotalsDTO,
)
from src.application.errors import AnalyticsScopeValidationError
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository


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
            by_provider_model=[
                AnalyticsCostByProviderModelDTO(
                    provider_name="gemini",
                    model_name="gemini-2.0",
                    jobs_total=1,
                    jobs_with_cost=1,
                    total_cost=Decimal("1.5"),
                    total_counted_quantity=None,
                    cost_per_counted_unit=None,
                )
            ],
            by_capture_status=[
                AnalyticsCostByCaptureStatusDTO(capture_status="exact", jobs_total=1, total_cost=Decimal("1.5")),
                AnalyticsCostByCaptureStatusDTO(capture_status="missing", jobs_total=1, total_cost=None),
            ],
            warnings=["COST_SNAPSHOT_MISSING_FOR_SOME_JOBS"],
        )


class _ScopeFailCostService:
    def build(self, _filters) -> AnalyticsCostSummaryDTO:
        raise AnalyticsScopeValidationError("aisle_id does not belong to the given inventory_id")


@pytest.fixture
def client_with_stub():
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_analytics_cost_summary_service] = lambda: _StubCostService()
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_analytics_cost_summary_service, None)


def test_cost_summary_endpoint_shape(client_with_stub: TestClient) -> None:
    resp = client_with_stub.get(
        "/api/v3/analytics/cost-summary",
        params={"inventory_id": "inv-1", "date_from": "2026-03-01", "date_to": "2026-03-10"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["jobs_total"] == 2
    assert body["totals"]["total_cost"] == 1.5
    assert body["by_provider_model"][0]["total_counted_quantity"] is None
    assert body["by_provider_model"][0]["cost_per_counted_unit"] is None


def test_cost_summary_date_from_after_to_returns_422(client_with_stub: TestClient) -> None:
    resp = client_with_stub.get(
        "/api/v3/analytics/cost-summary",
        params={"date_from": "2026-03-10", "date_to": "2026-03-01"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == HTTP_DETAIL_ANALYTICS_DATE_FROM_MUST_BE_ON_OR_BEFORE_DATE_TO


def test_cost_summary_range_too_large_returns_422(client_with_stub: TestClient) -> None:
    resp = client_with_stub.get(
        "/api/v3/analytics/cost-summary",
        params={"date_from": "2020-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "date_range_exceeds_maximum_window"


def test_cost_summary_scope_mismatch_returns_422() -> None:
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id="inv-real",
            code="A1",
            status=AisleStatus.PROCESSED,
            created_at=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
            updated_at=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
        )
    )
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_analytics_cost_summary_service] = lambda: _ScopeFailCostService()
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/v3/analytics/cost-summary",
            params={"inventory_id": "inv-wrong", "aisle_id": "aisle-1"},
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_analytics_cost_summary_service, None)
