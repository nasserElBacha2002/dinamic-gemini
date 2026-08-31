"""HTTP scope for GET recognition-config (cross-client denial)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.api.dependencies import get_inventory_recognition_config_use_case, get_inventory_repo
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.inventory.entities import Inventory, InventoryStatus

client = TestClient(app)


def test_recognition_config_cross_client_denied() -> None:
    """Client A must not read Client B inventory recognition-config.

    Platform convention: InventoryAccessPolicy raises InventoryNotFoundError → HTTP 404
    (anti-enumeration), not 403.
    """
    now = datetime.now(timezone.utc)
    inv_b = Inventory(
        id="inv-b",
        name="B",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id="client-b",
    )
    inv_repo = MagicMock()
    inv_repo.get_by_id.side_effect = lambda iid: inv_b if iid == "inv-b" else None

    use_case = MagicMock()
    use_case.execute.side_effect = AssertionError("use case must not run on deny")

    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="user-a",
        username="a",
        role="company_admin",
        client_id="client-a",
    )
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_inventory_recognition_config_use_case] = lambda: use_case
    try:
        resp = client.get("/api/v3/inventories/inv-b/recognition-config")
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_inventory_recognition_config_use_case, None)

    assert resp.status_code == 404, resp.text
    use_case.execute.assert_not_called()
