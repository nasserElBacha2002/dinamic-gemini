"""Device-token Raspberry inventory endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_inventory_recognition_config_use_case,
    require_raspberry_device_token,
)
from src.api.deps.inventory import get_list_raspberry_inventories_use_case
from src.api.server import app
from src.application.use_cases.inventories.list_raspberry_inventories import (
    ListRaspberryInventoriesUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository

client = TestClient(app)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seeded_list_use_case() -> ListRaspberryInventoriesUseCase:
    clients = MemoryClientRepository()
    inventories = MemoryInventoryRepository()
    now = _now()
    clients.save(
        Client(
            id="client-a",
            name="A",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    inventories.save(
        Inventory(
            id="inv-a",
            name="Warehouse A",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            client_id="client-a",
        )
    )
    inventories.save(
        Inventory(
            id="inv-b",
            name="Warehouse B",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            client_id="client-b",
        )
    )
    return ListRaspberryInventoriesUseCase(
        client_repo=clients,
        inventory_repo=inventories,
    )


def test_raspberry_inventories_require_device_token() -> None:
    with patch(
        "src.config.load_settings",
        return_value=SimpleNamespace(raspberry_device_token="device-secret"),
    ):
        resp = client.get("/api/v3/raspberry/inventories", params={"client_id": "client-a"})
    assert resp.status_code == 401, resp.text


def test_raspberry_inventories_invalid_device_token() -> None:
    with patch(
        "src.config.load_settings",
        return_value=SimpleNamespace(raspberry_device_token="device-secret"),
    ):
        resp = client.get(
            "/api/v3/raspberry/inventories",
            params={"client_id": "client-a"},
            headers={"X-Device-Token": "wrong"},
        )
    assert resp.status_code == 401, resp.text


def test_raspberry_inventories_are_scoped_to_client() -> None:
    app.dependency_overrides[require_raspberry_device_token] = lambda: None
    app.dependency_overrides[get_list_raspberry_inventories_use_case] = _seeded_list_use_case
    try:
        resp = client.get(
            "/api/v3/raspberry/inventories",
            params={"client_id": "client-a"},
            headers={"X-Device-Token": "device-secret"},
        )
    finally:
        app.dependency_overrides.pop(require_raspberry_device_token, None)
        app.dependency_overrides.pop(get_list_raspberry_inventories_use_case, None)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [row["id"] for row in items] == ["inv-a"]
    assert items[0]["client_id"] == "client-a"
    assert items[0]["name"] == "Warehouse A"


def test_raspberry_inventories_unknown_client_is_404() -> None:
    app.dependency_overrides[require_raspberry_device_token] = lambda: None
    app.dependency_overrides[get_list_raspberry_inventories_use_case] = _seeded_list_use_case
    try:
        resp = client.get(
            "/api/v3/raspberry/inventories",
            params={"client_id": "missing"},
            headers={"X-Device-Token": "device-secret"},
        )
    finally:
        app.dependency_overrides.pop(require_raspberry_device_token, None)
        app.dependency_overrides.pop(get_list_raspberry_inventories_use_case, None)
    assert resp.status_code == 404, resp.text


def test_raspberry_inventory_recognition_config_mismatch_is_404() -> None:
    use_case = MagicMock()
    use_case.execute.return_value = SimpleNamespace(client_id="client-b")
    app.dependency_overrides[require_raspberry_device_token] = lambda: None
    app.dependency_overrides[get_inventory_recognition_config_use_case] = lambda: use_case
    try:
        resp = client.get(
            "/api/v3/raspberry/inventories/inv-b/recognition-config",
            params={"client_id": "client-a"},
            headers={"X-Device-Token": "device-secret"},
        )
    finally:
        app.dependency_overrides.pop(require_raspberry_device_token, None)
        app.dependency_overrides.pop(get_inventory_recognition_config_use_case, None)
    assert resp.status_code == 404, resp.text
    use_case.execute.assert_called_once()
