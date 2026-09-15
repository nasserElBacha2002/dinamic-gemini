"""HTTP Stage 2 — company_admin cannot cross tenants on clients/inventories/exports."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_aisle_repo,
    get_client_repo,
    get_inventory_repo,
    get_position_repo,
)
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository

client = TestClient(app)


def _seed() -> tuple[MemoryClientRepository, MemoryInventoryRepository]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clients = MemoryClientRepository()
    inventories = MemoryInventoryRepository()
    for cid, name in (("client-a", "A"), ("client-b", "B")):
        clients.save(
            Client(
                id=cid,
                name=name,
                status=ClientStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
    for iid, cid in (("inv-a", "client-a"), ("inv-b", "client-b")):
        inventories.save(
            Inventory(
                id=iid,
                name=iid,
                status=InventoryStatus.DRAFT,
                created_at=now,
                updated_at=now,
                client_id=cid,
            )
        )
    return clients, inventories


def _as_company(client_id: str) -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="u",
        username="co",
        role="company_admin",
        client_id=client_id,
    )


def _as_platform() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="p",
        username="plat",
        role="platform_admin",
    )


def _clear() -> None:
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_client_repo, None)
    app.dependency_overrides.pop(get_inventory_repo, None)
    app.dependency_overrides.pop(get_aisle_repo, None)
    app.dependency_overrides.pop(get_position_repo, None)


def _wire_repos(
    clients: MemoryClientRepository, inventories: MemoryInventoryRepository
) -> None:
    app.dependency_overrides[get_client_repo] = lambda: clients
    app.dependency_overrides[get_inventory_repo] = lambda: inventories
    app.dependency_overrides[get_aisle_repo] = lambda: MemoryAisleRepository()
    app.dependency_overrides[get_position_repo] = lambda: MemoryPositionRepository()


def test_http_company_a_clients_and_inventories_scoped() -> None:
    clients, inventories = _seed()
    _wire_repos(clients, inventories)
    try:
        _as_company("client-a")
        listed = client.get("/api/v3/clients/")
        assert listed.status_code == 200
        ids = [row["id"] for row in listed.json()["items"]]
        assert ids == ["client-a"]

        assert client.get("/api/v3/clients/client-a").status_code == 200
        assert client.get("/api/v3/clients/client-b").status_code == 404

        inv_list = client.get("/api/v3/inventories/")
        assert inv_list.status_code == 200
        inv_ids = [row["id"] for row in inv_list.json()["items"]]
        assert inv_ids == ["inv-a"]
        assert inv_list.json()["total_items"] == 1

        assert client.get("/api/v3/inventories/inv-a").status_code == 200
        assert client.get("/api/v3/inventories/inv-b").status_code == 404
        assert client.get("/api/v3/inventories/inv-b/export").status_code == 404
        assert client.post(
            "/api/v3/clients/", json={"name": "Nope", "status": "active"}
        ).status_code == 403
    finally:
        _clear()


def test_http_platform_sees_both() -> None:
    clients, inventories = _seed()
    _wire_repos(clients, inventories)
    try:
        _as_platform()
        listed = client.get("/api/v3/clients/")
        assert {row["id"] for row in listed.json()["items"]} == {"client-a", "client-b"}
        inv_list = client.get("/api/v3/inventories/")
        assert {row["id"] for row in inv_list.json()["items"]} == {"inv-a", "inv-b"}
        assert client.get("/api/v3/inventories/inv-b").status_code == 200
    finally:
        _clear()


def test_http_missing_bearer_rejected_when_override_cleared() -> None:
    """With no admin override, missing Authorization must not succeed as company scope."""
    _clear()
    # Ensure dependency is the real one (other modules may leave overrides).
    app.dependency_overrides.pop(get_current_admin, None)

    def _deny():
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_admin] = _deny
    try:
        resp = client.get("/api/v3/clients/")
        assert resp.status_code == 401
    finally:
        _clear()
