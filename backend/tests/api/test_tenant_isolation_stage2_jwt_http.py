"""HTTP Stage 2 corrections — real JWT tokens (not dependency auth stubs)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

import src.config as config_module
from src.api.dependencies import (
    get_aisle_repo,
    get_client_repo,
    get_inventory_repo,
    get_position_repo,
)
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.security import create_access_token
from src.config import get_settings, reload_settings
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository

_PWD = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
_SECRET = "t" * 40


@pytest.fixture()
def auth_env(monkeypatch: pytest.MonkeyPatch):
    """Isolate JWT settings for this test; restore env + settings cache on exit."""
    import os

    tracked = (
        "SQLSERVER_ENABLED",
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD_HASH",
        "AUTH_TOKEN_SECRET",
        "AUTH_TOKEN_EXPIRES_MINUTES",
    )
    prior_env = {key: os.environ.get(key) for key in tracked}

    monkeypatch.setattr(config_module, "_load_dotenv_files", lambda for_reload=False: None)
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _PWD.hash("correct-password"))
    monkeypatch.setenv("AUTH_TOKEN_SECRET", _SECRET)
    monkeypatch.setenv("AUTH_TOKEN_EXPIRES_MINUTES", "30")
    reload_settings()
    # Disable API conftest fake admin — exercise real JWT path.
    app.dependency_overrides.pop(get_current_admin, None)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        for dep in (get_client_repo, get_inventory_repo, get_aisle_repo, get_position_repo):
            app.dependency_overrides.pop(dep, None)
        # Restore before monkeypatch teardown so get_settings() cache matches prior env.
        for key, val in prior_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        reload_settings()


def test_auth_env_uses_lab_secret(auth_env) -> None:
    """auth_env activates lab JWT secret for the duration of the test."""
    assert get_settings().auth_token_secret == _SECRET


def _token(*, role: str, client_id: str | None, principal_id: str = "u1") -> str:
    return create_access_token(
        "admin",
        username="lab",
        role=role,
        principal_id=principal_id,
        client_id=client_id,
        secret=_SECRET,
        expires_minutes=30,
    )


def _seed() -> tuple[MemoryClientRepository, MemoryInventoryRepository, MemoryAisleRepository]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clients = MemoryClientRepository()
    inventories = MemoryInventoryRepository()
    aisles = MemoryAisleRepository()
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
    aisles.save(
        Aisle(
            id="aisle-b",
            inventory_id="inv-b",
            code="B1",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    aisles.save(
        Aisle(
            id="aisle-a",
            inventory_id="inv-a",
            code="A1",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    return clients, inventories, aisles


def _wire(
    clients: MemoryClientRepository,
    inventories: MemoryInventoryRepository,
    aisles: MemoryAisleRepository | None = None,
) -> None:
    app.dependency_overrides[get_client_repo] = lambda: clients
    app.dependency_overrides[get_inventory_repo] = lambda: inventories
    app.dependency_overrides[get_aisle_repo] = lambda: aisles or MemoryAisleRepository()
    app.dependency_overrides[get_position_repo] = lambda: MemoryPositionRepository()


def test_jwt_company_a_scoped_and_cross_tenant_404(auth_env) -> None:
    clients, inventories, aisles = _seed()
    _wire(clients, inventories, aisles)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_token(role='company_admin', client_id='client-a')}"}

    listed = client.get("/api/v3/clients/", headers=headers)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()["items"]] == ["client-a"]

    assert client.get("/api/v3/clients/client-a", headers=headers).status_code == 200
    assert client.get("/api/v3/clients/client-b", headers=headers).status_code == 404
    assert client.get("/api/v3/clients/client-b/suppliers", headers=headers).status_code == 404

    inv_list = client.get("/api/v3/inventories/", headers=headers)
    assert inv_list.status_code == 200
    assert [row["id"] for row in inv_list.json()["items"]] == ["inv-a"]
    assert inv_list.json()["total_items"] == 1

    assert client.get("/api/v3/inventories/inv-a", headers=headers).status_code == 200
    assert client.get("/api/v3/inventories/inv-b", headers=headers).status_code == 404
    assert client.get("/api/v3/inventories/inv-b/export", headers=headers).status_code == 404
    assert client.get("/api/v3/inventories/inv-a/aisles", headers=headers).status_code == 200
    # Parent A + child aisle from B must not succeed.
    assert (
        client.get(
            "/api/v3/inventories/inv-a/aisles/aisle-b/status", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v3/clients/",
            headers=headers,
            json={"name": "Nope", "status": "active"},
        ).status_code
        == 403
    )


def test_jwt_missing_and_invalid_token_401(auth_env) -> None:
    client = TestClient(app)
    assert client.get("/api/v3/clients/").status_code == 401
    assert (
        client.get(
            "/api/v3/clients/",
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        ).status_code
        == 401
    )


def test_jwt_platform_sees_both(auth_env) -> None:
    clients, inventories, aisles = _seed()
    _wire(clients, inventories, aisles)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_token(role='platform_admin', client_id=None)}"}
    listed = client.get("/api/v3/clients/", headers=headers)
    assert {row["id"] for row in listed.json()["items"]} == {"client-a", "client-b"}
    inv_list = client.get("/api/v3/inventories/", headers=headers)
    assert {row["id"] for row in inv_list.json()["items"]} == {"inv-a", "inv-b"}


def test_jwt_company_without_client_id_fail_closed(auth_env) -> None:
    """Auth layer rejects company_admin without client_id (403) — fail closed."""
    clients, inventories, aisles = _seed()
    _wire(clients, inventories, aisles)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_token(role='company_admin', client_id=None)}"}
    assert client.get("/api/v3/clients/", headers=headers).status_code == 403
    assert client.get("/api/v3/inventories/inv-a", headers=headers).status_code == 403


def test_jwt_client_a_supplier_b_rejected(auth_env) -> None:
    """Path client A + supplier belonging to B → 404 (require_client_scope or mismatch)."""
    from src.api.dependencies import get_client_supplier_repo

    clients, inventories, aisles = _seed()
    suppliers = MemoryClientSupplierRepository()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    suppliers.save(
        ClientSupplier(
            id="sup-b",
            client_id="client-b",
            name="SuppB",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    _wire(clients, inventories, aisles)
    app.dependency_overrides[get_client_supplier_repo] = lambda: suppliers
    try:
        client = TestClient(app)
        headers = {
            "Authorization": f"Bearer {_token(role='company_admin', client_id='client-a')}"
        }
        # Cross-tenant client path blocked before supplier lookup.
        r = client.get("/api/v3/clients/client-b/suppliers/sup-b", headers=headers)
        assert r.status_code == 404
        # Own client + foreign supplier id.
        r2 = client.get("/api/v3/clients/client-a/suppliers/sup-b", headers=headers)
        assert r2.status_code == 404
    finally:
        app.dependency_overrides.pop(get_client_supplier_repo, None)
