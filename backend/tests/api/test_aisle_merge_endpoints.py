from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_get_aisle_merge_results_use_case,
    get_run_aisle_merge_use_case,
)
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.labels.entities import FinalCountRecord


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


def test_run_merge_endpoint_returns_counts() -> None:
    class StubRunMergeUseCase:
        def execute(self, _cmd):
            return SimpleNamespace(
                raw_count=3,
                normalized_count=1,
                final_count=1,
                product_records_updated=1,
            )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_run_aisle_merge_use_case] = lambda: StubRunMergeUseCase()
    try:
        client = TestClient(app)
        resp = client.post("/api/v3/inventories/inv1/aisles/a1/merge")
        assert resp.status_code == 202
        data = resp.json()
        assert data["operation_mode"] == "manual_authoritative"
        assert data["authoritative_quantity_updated"] is True
        assert data["raw_count"] == 3
        assert data["normalized_count"] == 1
        assert data["final_count"] == 1
        assert data["product_records_updated"] == 1
    finally:
        app.dependency_overrides.clear()


def test_get_merge_results_endpoint_returns_rows() -> None:
    now = datetime.now(timezone.utc)

    class StubGetMergeResultsUseCase:
        def execute(self, _cmd):
            return [
                FinalCountRecord(
                    id="fc1",
                    inventory_id="inv1",
                    aisle_id="a1",
                    position_id="p1",
                    sku="SKU-1",
                    product_name="Product 1",
                    quantity=2,
                    normalized_label_ids=["n1", "n2"],
                    review_required=False,
                    explanation_summary="2 normalized labels",
                    metadata={"source": "merge"},
                    created_at=now,
                )
            ]

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_get_aisle_merge_results_use_case] = (
        lambda: StubGetMergeResultsUseCase()
    )
    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv1/aisles/a1/merge-results")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["sku"] == "SKU-1"
        assert data["results"][0]["merged_quantity"] == 2
    finally:
        app.dependency_overrides.clear()

