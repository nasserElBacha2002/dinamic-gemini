"""Lightweight API wiring test: v3 inventories endpoints call use cases and return expected shape."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.api.dependencies import get_create_inventory_use_case
from src.api.server import app

client = TestClient(app)


def test_post_inventories_returns_201_and_entity() -> None:
    response = client.post("/api/v3/inventories", json={"name": "Test Inventory"})
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == "Test Inventory"
    assert data["status"] == "draft"
    assert data.get("processing_mode") == "production"
    assert data.get("client_id") is None
    assert data.get("primary_execution_config") is not None


def test_post_inventories_test_mode_and_list_row_includes_processing_mode() -> None:
    create = client.post("/api/v3/inventories", json={"name": "Lab", "processing_mode": "test"})
    assert create.status_code == 201
    created = create.json()
    assert created["processing_mode"] == "test"
    assert created.get("primary_execution_config") is None

    listed = client.get("/api/v3/inventories")
    assert listed.status_code == 200
    row = next((x for x in listed.json()["items"] if x["id"] == created["id"]), None)
    assert row is not None
    assert row["processing_mode"] == "test"


def test_get_create_inventory_use_case_factory_matches_constructor() -> None:
    """Guardrail: dependency provider must construct CreateInventoryUseCase with a single return path."""
    uc = get_create_inventory_use_case(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    assert hasattr(uc, "execute")


def test_get_inventories_returns_list_and_includes_created() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For List"})
    assert create_resp.status_code == 201
    created_id = create_resp.json()["id"]

    response = client.get("/api/v3/inventories")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert all("client_id" in item for item in data["items"])
    ids = [item["id"] for item in data["items"]]
    assert created_id in ids


def test_post_inventories_with_valid_client_id_returns_client_id() -> None:
    created_client = client.post("/api/v3/clients", json={"name": "Retail B"})
    assert created_client.status_code == 201
    client_id = created_client.json()["id"]

    response = client.post(
        "/api/v3/inventories",
        json={"name": "With Client", "client_id": client_id},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["client_id"] == client_id


def test_post_inventories_with_invalid_client_id_returns_structured_not_found() -> None:
    response = client.post(
        "/api/v3/inventories",
        json={"name": "Invalid Client", "client_id": "missing-client-id"},
    )
    assert response.status_code == 404
    payload = response.json()
    assert payload.get("code") == "CLIENT_NOT_FOUND"
    assert payload.get("detail") == "Client not found"


def test_post_inventories_with_null_client_id_keeps_legacy_behavior() -> None:
    response = client.post(
        "/api/v3/inventories",
        json={"name": "Legacy Null Client", "client_id": None},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Legacy Null Client"
    assert data["client_id"] is None


def test_post_inventories_with_empty_client_id_returns_422() -> None:
    response = client.post(
        "/api/v3/inventories",
        json={"name": "Invalid Empty Client", "client_id": ""},
    )
    assert response.status_code == 422


def test_post_inventories_with_whitespace_client_id_returns_422() -> None:
    response = client.post(
        "/api/v3/inventories",
        json={"name": "Invalid Whitespace Client", "client_id": "   "},
    )
    assert response.status_code == 422


def test_post_inventories_empty_name_returns_422() -> None:
    response = client.post("/api/v3/inventories", json={"name": ""})
    assert response.status_code == 422


def test_post_inventories_name_too_long_returns_422() -> None:
    response = client.post("/api/v3/inventories", json={"name": "x" * 256})
    assert response.status_code == 422


def test_get_aisle_asset_file_returns_404_when_asset_not_found() -> None:
    """Reference image endpoint returns 404 when aisle has no such asset."""
    create_resp = client.post("/api/v3/inventories", json={"name": "Ref Image Test"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(f"/api/v3/inventories/{inv_id}/aisles", json={"code": "A1"})
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    response = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/nonexistent-asset-id/file"
    )
    assert response.status_code == 404
    assert response.json().get("detail") == "Asset not found"


def test_get_aisle_asset_image_display_url_returns_404_when_asset_not_found() -> None:
    """image-display-url matches file endpoint when asset is missing."""
    create_resp = client.post("/api/v3/inventories", json={"name": "Display URL Test"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(f"/api/v3/inventories/{inv_id}/aisles", json={"code": "A1"})
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    response = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/nonexistent-asset-id/image-display-url"
    )
    assert response.status_code == 404
    assert response.json().get("detail") == "Asset not found"
