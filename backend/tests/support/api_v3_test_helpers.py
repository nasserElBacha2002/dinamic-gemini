"""Small helpers for v3 API tests (authenticated admin assumed via conftest)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def unique_client_name(prefix: str = "TestClient") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def create_test_client(client: TestClient, name: str | None = None) -> str:
    """POST /api/v3/clients and return the new client id."""
    r = client.post("/api/v3/clients", json={"name": name or unique_client_name()})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def create_test_inventory(
    client: TestClient,
    *,
    name: str,
    client_id: str | None = None,
    **extra: object,
):
    """POST /api/v3/inventories with a valid client_id (creates a client if none passed)."""
    cid = client_id if client_id is not None else create_test_client(client)
    body: dict[str, object] = {"name": name, "client_id": cid}
    body.update(extra)
    return client.post("/api/v3/inventories", json=body)
