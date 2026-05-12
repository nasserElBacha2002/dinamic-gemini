"""Phase C9: legacy inventory visual reference routes are unregistered."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app


def test_legacy_inventory_visual_reference_paths_return_404() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    assert (
        client.get("/api/v3/inventories/inv-1/visual-references").status_code == 404
    )
    assert (
        client.post("/api/v3/inventories/inv-1/visual-references").status_code == 404
    )
    assert (
        client.put("/api/v3/inventories/inv-1/visual-references/ref-1").status_code
        == 404
    )
    assert (
        client.delete("/api/v3/inventories/inv-1/visual-references/ref-1").status_code
        == 404
    )
    assert (
        client.get(
            "/api/v3/inventories/inv-1/visual-references/ref-1/file"
        ).status_code
        == 404
    )
