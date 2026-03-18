"""API tests for review actions — Épica 8."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_aisle_repo,
    get_evidence_repo,
    get_inventory_repo,
    get_position_repo,
    get_product_record_repo,
    get_review_action_repo,
)
from src.api.server import app
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository
from src.infrastructure.repositories.memory_review_action_repository import MemoryReviewActionRepository


def _seed_repos():
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-review-1", "WH Review", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-review-1", "inv-review-1", "R01", AisleStatus.CREATED, now, now)
    position = Position(
        id="pos-review-1",
        aisle_id="aisle-review-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
    )
    product = ProductRecord(
        id="prod-review-1",
        position_id="pos-review-1",
        sku="SKU-REVIEW",
        description="Product for review",
        detected_quantity=5,
        corrected_quantity=None,
        confidence=0.95,
        created_at=now,
        updated_at=now,
    )
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    review_repo = MemoryReviewActionRepository()
    inv_repo.save(inv)
    aisle_repo.save(aisle)
    position_repo.save(position)
    product_repo.save(product)
    return {
        "inv_repo": inv_repo,
        "aisle_repo": aisle_repo,
        "position_repo": position_repo,
        "product_repo": product_repo,
        "evidence_repo": evidence_repo,
        "review_repo": review_repo,
    }


def test_post_review_invalid_action_type_returns_422() -> None:
    """Unknown action_type returns 422 (Pydantic validation or route)."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        resp = client.post(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1/reviews",
            json={"action_type": "invalid"},
        )
        assert resp.status_code == 422
        detail = resp.json().get("detail", "")
        detail_str = detail if isinstance(detail, str) else str(detail)
        assert "action_type" in detail_str.lower() or "action" in detail_str.lower()
    finally:
        app.dependency_overrides.clear()


def test_post_review_position_not_found_returns_404() -> None:
    """POST review for non-existent position returns 404."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        resp = client.post(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/nonexistent-pos/reviews",
            json={"action_type": "confirm"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json().get("detail", "").lower()
    finally:
        app.dependency_overrides.clear()


def test_post_review_confirm_returns_204_and_detail_includes_review() -> None:
    """POST confirm returns 204; GET detail then returns position reviewed and review_actions."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        resp = client.post(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1/reviews",
            json={"action_type": "confirm"},
        )
        assert resp.status_code == 204

        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        data = detail.json()
        assert data["position"]["status"] == "reviewed"
        assert "review_actions" in data
        assert len(data["review_actions"]) == 1
        assert data["review_actions"][0]["action_type"] == "confirm"
        assert data["review_actions"][0]["after_json"].get("status") == "reviewed"
    finally:
        app.dependency_overrides.clear()


def test_post_review_update_quantity_returns_204_and_detail_updated() -> None:
    """POST update_quantity with product_id and corrected_quantity returns 204; detail shows corrected."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        resp = client.post(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1/reviews",
            json={
                "action_type": "update_quantity",
                "product_id": "prod-review-1",
                "corrected_quantity": 10,
            },
        )
        assert resp.status_code == 204

        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        data = detail.json()
        assert data["position"]["status"] == "corrected"
        assert data["position"]["corrected_quantity"] == 10
        assert data["position"]["qty"] == 10
        assert len(data["review_actions"]) == 1
        assert data["review_actions"][0]["action_type"] == "update_quantity"
    finally:
        app.dependency_overrides.clear()


def test_post_review_update_quantity_missing_product_id_returns_422() -> None:
    """update_quantity without product_id returns 422."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        resp = client.post(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1/reviews",
            json={"action_type": "update_quantity", "corrected_quantity": 3},
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_post_review_update_sku_returns_204_and_detail_updated() -> None:
    """POST update_sku with product_id, sku (and optional description) returns 204; detail shows corrected."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        resp = client.post(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1/reviews",
            json={
                "action_type": "update_sku",
                "product_id": "prod-review-1",
                "sku": "NEW-SKU-123",
                "description": "Updated description",
            },
        )
        assert resp.status_code == 204

        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        data = detail.json()
        assert data["position"]["status"] == "corrected"
        products = data["products"]
        assert len(products) == 1
        assert products[0]["sku"] == "NEW-SKU-123"
        assert products[0]["description"] == "Updated description"
        assert len(data["review_actions"]) == 1
        assert data["review_actions"][0]["action_type"] == "update_sku"
    finally:
        app.dependency_overrides.clear()


def test_post_review_update_quantity_wrong_product_id_returns_404() -> None:
    """update_quantity with product_id not belonging to position returns 404."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        resp = client.post(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1/reviews",
            json={
                "action_type": "update_quantity",
                "product_id": "non-existent-product-id",
                "corrected_quantity": 5,
            },
        )
        assert resp.status_code == 404
        detail = resp.json().get("detail", "")
        detail_str = detail if isinstance(detail, str) else str(detail)
        assert "product" in detail_str.lower() or "not found" in detail_str.lower()
    finally:
        app.dependency_overrides.clear()


def test_post_review_delete_position_returns_204_and_detail_deleted() -> None:
    """POST delete_position returns 204; GET detail shows status deleted."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        resp = client.post(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1/reviews",
            json={"action_type": "delete_position"},
        )
        assert resp.status_code == 204

        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        assert detail.json()["position"]["status"] == "deleted"
        assert len(detail.json()["review_actions"]) == 1
        assert detail.json()["review_actions"][0]["action_type"] == "delete_position"
    finally:
        app.dependency_overrides.clear()


def test_get_position_detail_includes_review_actions() -> None:
    """GET position detail returns review_actions array (empty when none)."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        resp = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "review_actions" in data
        assert data["review_actions"] == []
    finally:
        app.dependency_overrides.clear()


def test_list_and_detail_corrected_quantity_coherent_after_update_quantity() -> None:
    """v3.2.5 Phase 2 Block 1: After update_quantity, list and detail both expose same corrected_quantity."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        resp = client.post(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1/reviews",
            json={
                "action_type": "update_quantity",
                "product_id": "prod-review-1",
                "corrected_quantity": 10,
            },
        )
        assert resp.status_code == 204

        list_resp = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions"
        )
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert "positions" in list_data
        positions = list_data["positions"]
        ids = [pos["id"] for pos in positions]
        assert ids == ["pos-review-1"], "list must return exactly the expected position ids"
        assert len(ids) == len(set(ids)), "list must not contain duplicate position rows"
        assert len(positions) == 1
        assert positions[0]["corrected_quantity"] == 10

        detail_resp = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["position"]["corrected_quantity"] == 10
    finally:
        app.dependency_overrides.clear()


def test_list_corrected_quantity_null_when_no_manual_correction() -> None:
    """v3.2.5 Phase 2 Block 1: List returns corrected_quantity null when no manual correction exists."""
    client = TestClient(app)
    repos = _seed_repos()
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        list_resp = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions"
        )
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert len(list_data["positions"]) == 1
        # Seed product has corrected_quantity=None; list must expose null/absent per schema.
        assert list_data["positions"][0].get("corrected_quantity") is None
    finally:
        app.dependency_overrides.clear()
