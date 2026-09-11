"""API contract: reprocess maps process-start ValueErrors like POST .../process."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.api.dependencies import get_access_principal, get_reprocess_aisle_positioning_use_case
from src.api.server import app
from src.application.dto.access_principal import AccessPrincipal
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


def _principal() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="admin",
        client_id=None,
        roles=frozenset({"platform_admin"}),
        is_platform=True,
    )


def test_reprocess_maps_supplier_prompt_required_to_422_not_500() -> None:
    """Regression: full reprocess used to leak StartAisleProcessing ValueError as 500."""
    uc = MagicMock()
    uc.execute.side_effect = ValueError(
        "SUPPLIER_PROMPT_REQUIRED: active non-empty supplier prompt is required "
        "when external fallback is enabled for a supplier-associated aisle"
    )
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_access_principal] = _principal
    app.dependency_overrides[get_reprocess_aisle_positioning_use_case] = lambda: uc
    client = TestClient(app, raise_server_exceptions=False)
    try:
        resp = client.post(
            "/api/v3/inventories/inv-1/aisles/aisle-1/reprocess",
            json={
                "idempotency_key": "test-key-1",
                "reprocess_mode": "REPROCESS_FULL_AISLE",
                "expected_active_job_id": None,
                "expected_result_job_id": "job-1",
                "identification_mode": None,
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "SUPPLIER_PROMPT_REQUIRED"
        assert "supplier prompt" in body["detail"].lower()
    finally:
        app.dependency_overrides.clear()
