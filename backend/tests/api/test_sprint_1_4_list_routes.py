"""HTTP-level tests for Sprint 1.4 list query contracts (pagination, filter, sort, response shape)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_aisle_repo,
    get_inventory_repo,
    get_position_repo,
    get_product_record_repo,
)
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository


def _admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


@pytest.fixture
def client_list_repos():
    """Memory repos + auth override for list endpoints."""
    now = datetime(2025, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()

    inv_repo.save(Inventory("inv-s14-a", "Acme Retail Chain", InventoryStatus.DRAFT, now, now))
    inv_repo.save(Inventory("inv-s14-b", "Beta Wholesale", InventoryStatus.DRAFT, now, now))

    aisle_repo.save(Aisle("aisle-s14-z", "inv-s14-a", "ZZ-Top", AisleStatus.CREATED, now, now))
    aisle_repo.save(Aisle("aisle-s14-a", "inv-s14-a", "AA-Bottom", AisleStatus.CREATED, now, now))

    pos_repo.save(
        Position(
            "pos-low",
            "aisle-s14-z",
            PositionStatus.DETECTED,
            0.2,
            False,
            None,
            now,
            now,
            detected_summary_json={"internal_code": "SKU-Z", "final_quantity": 1},
        )
    )
    pos_repo.save(
        Position(
            "pos-high",
            "aisle-s14-z",
            PositionStatus.DETECTED,
            0.99,
            False,
            None,
            now,
            now,
            detected_summary_json={"internal_code": "SKU-Y", "final_quantity": 1},
        )
    )
    pos_repo.save(
        Position(
            "pos-review-b",
            "aisle-s14-a",
            PositionStatus.DETECTED,
            0.7,
            True,
            None,
            now,
            now,
        )
    )

    overrides = {
        get_current_admin: _admin,
        get_inventory_repo: lambda: inv_repo,
        get_aisle_repo: lambda: aisle_repo,
        get_position_repo: lambda: pos_repo,
        get_product_record_repo: lambda: product_repo,
    }
    for dep, fn in overrides.items():
        app.dependency_overrides[dep] = fn
    try:
        yield TestClient(app), now
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


def _assert_paginated_inventory_shape(data: dict) -> None:
    assert set(data.keys()) >= {"items", "page", "page_size", "total_items", "total_pages"}
    assert isinstance(data["items"], list)


def test_get_inventories_paginated_shape_and_search(client_list_repos):
    client, _ = client_list_repos
    r = client.get("/api/v3/inventories")
    assert r.status_code == 200
    data = r.json()
    _assert_paginated_inventory_shape(data)
    assert data["total_items"] == 2
    assert data["total_pages"] >= 1
    assert len(data["items"]) >= 1

    r2 = client.get("/api/v3/inventories", params={"search": "beta"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["total_items"] == 1
    assert len(d2["items"]) == 1
    assert "Beta" in d2["items"][0]["name"]

    r_empty = client.get("/api/v3/inventories", params={"search": "no-such-inventory-xyz"})
    assert r_empty.status_code == 200
    d_empty = r_empty.json()
    assert d_empty["items"] == []
    assert d_empty["total_items"] == 0
    assert d_empty["total_pages"] == 0

    r_page = client.get("/api/v3/inventories", params={"page": 99, "page_size": 10})
    assert r_page.status_code == 200
    assert r_page.json()["items"] == []


def test_get_aisles_paginated_shape_and_search(client_list_repos):
    client, _ = client_list_repos
    r = client.get("/api/v3/inventories/inv-s14-a/aisles")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"items", "page", "page_size", "total_items", "total_pages"}
    assert data["total_items"] == 2

    r2 = client.get("/api/v3/inventories/inv-s14-a/aisles", params={"search": "zz"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["total_items"] == 1
    assert d2["items"][0]["code"] == "ZZ-Top"


def test_get_aisle_positions_sort_and_metadata(client_list_repos):
    client, _ = client_list_repos
    r = client.get(
        "/api/v3/inventories/inv-s14-a/aisles/aisle-s14-z/positions",
        params={"sort_by": "confidence", "sort_dir": "desc", "page": 1, "page_size": 10},
    )
    assert r.status_code == 200
    data = r.json()
    assert "positions" in data
    assert set(data.keys()) >= {
        "positions",
        "page",
        "page_size",
        "total_items",
        "total_pages",
        "raw_fetch_truncated",
    }
    assert isinstance(data["raw_fetch_truncated"], bool)
    assert data["total_items"] == 2
    assert data["total_pages"] == 1
    assert len(data["positions"]) == 2
    # Descending confidence: 0.99 first
    assert data["positions"][0]["confidence"] == pytest.approx(0.99)
    assert data["positions"][1]["confidence"] == pytest.approx(0.2)


def test_get_review_queue_pagination_filter_sort(client_list_repos):
    client, _ = client_list_repos
    r = client.get("/api/v3/review-queue/positions")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"items", "page", "page_size", "total_items", "total_pages"}
    assert data["total_items"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["inventory_id"] == "inv-s14-a"

    r_inv = client.get("/api/v3/review-queue/positions", params={"inventory_id": "inv-s14-b"})
    assert r_inv.status_code == 200
    assert r_inv.json()["total_items"] == 0
    assert r_inv.json()["items"] == []

    r_page = client.get("/api/v3/review-queue/positions", params={"page": 1, "page_size": 1})
    assert r_page.status_code == 200
    p = r_page.json()
    assert p["total_items"] == 1
    assert len(p["items"]) == 1

    r_sort = client.get(
        "/api/v3/review-queue/positions",
        params={"sort_by": "confidence", "sort_dir": "asc"},
    )
    assert r_sort.status_code == 200
    assert r_sort.json()["items"][0]["position"]["confidence"] == pytest.approx(0.7)
