"""API tests for review actions — Épica 8."""

from __future__ import annotations

from dataclasses import replace
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
        detected_summary_json={"internal_code": "SKU-REVIEW"},
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


def test_post_review_non_operational_job_returns_403() -> None:
    """Benchmark / non-operational rows are view-only; mutations return 403."""
    client = TestClient(app)
    repos = _seed_repos()
    aisle = repos["aisle_repo"].get_by_id("aisle-review-1")
    assert aisle is not None
    repos["aisle_repo"].save(replace(aisle, operational_job_id="job-op-1"))
    pos = repos["position_repo"].get_by_id("pos-review-1")
    assert pos is not None
    repos["position_repo"].save(replace(pos, job_id="job-bench-1"))
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
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_post_review_confirm_returns_204_and_detail_includes_review() -> None:
    """Phase 6: POST confirm returns 204; list/detail reread show reviewed, needs_review false, review_actions."""
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

        list_resp = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions"
        )
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert len(list_data["positions"]) == 1
        assert list_data["positions"][0]["status"] == "reviewed"
        assert list_data["positions"][0]["needs_review"] is False

        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        data = detail.json()
        assert data["position"]["status"] == "reviewed"
        assert data["position"]["needs_review"] is False
        assert "review_actions" in data
        assert len(data["review_actions"]) == 1
        assert data["review_actions"][0]["action_type"] == "confirm"
        assert data["review_actions"][0]["after_json"].get("status") == "reviewed"
    finally:
        app.dependency_overrides.clear()


def test_post_review_update_quantity_returns_204_and_detail_updated() -> None:
    """Phase 6: POST update_quantity returns 204; list/detail show corrected_quantity, needs_review false."""
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
        positions = list_resp.json()["positions"]
        assert len(positions) == 1
        assert positions[0]["corrected_quantity"] == 10
        assert positions[0]["status"] == "corrected"
        assert positions[0]["needs_review"] is False

        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        data = detail.json()
        assert data["position"]["status"] == "corrected"
        assert data["position"]["corrected_quantity"] == 10
        assert data["position"]["needs_review"] is False
        assert len(data["review_actions"]) == 1
        assert data["review_actions"][0]["action_type"] == "update_quantity"
        assert data["review_actions"][0]["after_json"].get("corrected_quantity") == 10
    finally:
        app.dependency_overrides.clear()


def test_post_review_update_quantity_without_product_id_uses_single_product() -> None:
    """update_quantity without product_id succeeds when position has a single product (backend picks it)."""
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
        assert resp.status_code == 204
        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        assert detail.json()["position"]["corrected_quantity"] == 3
    finally:
        app.dependency_overrides.clear()


def test_post_review_mark_image_mismatch_returns_204_and_preserves_sku() -> None:
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
            json={"action_type": "mark_image_mismatch"},
        )
        assert resp.status_code == 204

        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        data = detail.json()
        assert data["position"]["status"] == "reviewed"
        assert data["position"]["needs_review"] is False
        assert data["position"]["review_resolution"] == "image_mismatch"
        assert data["position"]["sku"] == "SKU-REVIEW"
        assert len(data["review_actions"]) == 1
        assert data["review_actions"][0]["action_type"] == "mark_image_mismatch"
        assert data["review_actions"][0]["after_json"].get("review_resolution") == "image_mismatch"
    finally:
        app.dependency_overrides.clear()


def test_post_review_mark_unknown_returns_204_and_detail_exposes_terminal_resolution() -> None:
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
            json={"action_type": "mark_unknown"},
        )
        assert resp.status_code == 204

        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        data = detail.json()
        assert data["position"]["status"] == "reviewed"
        assert data["position"]["needs_review"] is False
        assert data["position"]["review_resolution"] == "unknown"
        assert len(data["review_actions"]) == 1
        assert data["review_actions"][0]["action_type"] == "mark_unknown"
        assert data["review_actions"][0]["after_json"].get("review_resolution") == "unknown"
    finally:
        app.dependency_overrides.clear()


def test_post_review_update_sku_returns_204_and_detail_updated() -> None:
    """Phase 6: POST update_sku returns 204; list/detail reread show visible sku updated, needs_review false."""
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

        list_resp = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions"
        )
        assert list_resp.status_code == 200
        positions = list_resp.json()["positions"]
        assert len(positions) == 1
        assert positions[0]["sku"] == "NEW-SKU-123"
        assert positions[0]["status"] == "corrected"
        assert positions[0]["needs_review"] is False

        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        data = detail.json()
        assert data["position"]["status"] == "corrected"
        assert data["position"]["sku"] == "NEW-SKU-123"
        assert data["position"]["needs_review"] is False
        assert len(data["review_actions"]) == 1
        assert data["review_actions"][0]["action_type"] == "update_sku"
        assert data["review_actions"][0]["after_json"].get("sku") == "NEW-SKU-123"
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
    """Phase 6: POST delete_position returns 204; list/detail show deleted, needs_review false."""
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

        list_resp = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions"
        )
        assert list_resp.status_code == 200
        positions = list_resp.json()["positions"]
        assert len(positions) == 1
        assert positions[0]["status"] == "deleted"
        assert positions[0]["needs_review"] is False

        detail = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail.status_code == 200
        data = detail.json()
        assert data["position"]["status"] == "deleted"
        assert data["position"]["needs_review"] is False
        assert len(data["review_actions"]) == 1
        assert data["review_actions"][0]["action_type"] == "delete_position"
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
        assert detail_data["position"]["needs_review"] is False
        assert positions[0]["needs_review"] is False
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
        # v3.2.5 Block 4: no evidence in seed -> has_evidence false
        assert list_data["positions"][0]["has_evidence"] is False
    finally:
        app.dependency_overrides.clear()


def _seed_repos_with_evidence():
    """Same as _seed_repos but position has primary_evidence_id set so has_evidence is true."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-review-1", "WH Review", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-review-1", "inv-review-1", "R01", AisleStatus.CREATED, now, now)
    position = Position(
        id="pos-review-1",
        aisle_id="aisle-review-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id="ev-1",
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


def test_list_and_detail_has_evidence_coherent_when_evidence_present() -> None:
    """v3.2.5 Phase 2 Block 4: When position has primary_evidence_id, list and detail both return has_evidence true."""
    client = TestClient(app)
    repos = _seed_repos_with_evidence()
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
        assert list_data["positions"][0]["has_evidence"] is True

        detail_resp = client.get(
            "/api/v3/inventories/inv-review-1/aisles/aisle-review-1/positions/pos-review-1"
        )
        assert detail_resp.status_code == 200
        assert detail_resp.json()["position"]["has_evidence"] is True
    finally:
        app.dependency_overrides.clear()
