from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.errors.structured_api_http import (
    GLOBAL_PROMPT_CONFIG_EMPTY_INSTRUCTIONS,
    GLOBAL_PROMPT_CONFIG_NOT_FOUND,
)
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.runtime.app_container import reset_app_container_for_tests

client = TestClient(app)


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


@pytest.fixture(autouse=True)
def _admin_dependency_override() -> Iterator[None]:
    app.dependency_overrides[get_current_admin] = _fake_admin
    yield
    app.dependency_overrides.pop(get_current_admin, None)


@pytest.fixture(autouse=True)
def _fresh_container() -> Iterator[None]:
    reset_app_container_for_tests()
    yield
    reset_app_container_for_tests()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-admin-token"}


def _create_global_prompt(*, instructions_text: str, activate: bool = True) -> dict:
    r = client.post(
        "/api/v3/prompt-configs/global",
        json={"instructions_text": instructions_text, "activate": activate},
        headers=_auth_headers(),
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_first_active_global_prompt_config_safe_fields_only() -> None:
    payload = _create_global_prompt(instructions_text="Global v1", activate=True)
    assert payload["version"] == 1
    assert payload["scope_type"] == "global"
    assert payload["provider_name"] is None
    assert payload["model_name"] is None
    assert payload["is_active"] is True
    for forbidden in (
        "protected_prompt",
        "system_prompt",
        "composed_prompt",
        "prompt_key",
        "prompt_profile",
        "adapter_instructions",
        "normalization_rules",
    ):
        assert forbidden not in payload


def test_create_second_active_version_deactivates_previous() -> None:
    v1 = _create_global_prompt(instructions_text="v1", activate=True)
    v2 = _create_global_prompt(instructions_text="v2", activate=True)
    assert v2["version"] == 2
    r = client.get("/api/v3/prompt-configs/global", headers=_auth_headers())
    assert r.status_code == 200, r.text
    rows = {row["id"]: row for row in r.json()["items"]}
    assert rows[v1["id"]]["is_active"] is False
    assert rows[v2["id"]]["is_active"] is True


def test_create_inactive_version_preserves_active() -> None:
    v1 = _create_global_prompt(instructions_text="v1", activate=True)
    v2 = _create_global_prompt(instructions_text="v2", activate=False)
    assert v2["is_active"] is False
    r = client.get("/api/v3/prompt-configs/global/active", headers=_auth_headers())
    assert r.status_code == 200
    assert r.json()["id"] == v1["id"]


def test_activate_existing_version() -> None:
    _ = _create_global_prompt(instructions_text="v1", activate=True)
    v2 = _create_global_prompt(instructions_text="v2", activate=False)
    r_activate = client.post(
        f"/api/v3/prompt-configs/global/{v2['id']}/activate",
        headers=_auth_headers(),
    )
    assert r_activate.status_code == 200, r_activate.text
    assert r_activate.json()["id"] == v2["id"]
    assert r_activate.json()["is_active"] is True


def test_blank_instructions_rejected() -> None:
    r = client.post(
        "/api/v3/prompt-configs/global",
        json={"instructions_text": "   ", "activate": True},
        headers=_auth_headers(),
    )
    assert r.status_code == 400
    assert r.json().get("code") == GLOBAL_PROMPT_CONFIG_EMPTY_INSTRUCTIONS


def test_get_active_returns_404_when_none_exists() -> None:
    _create_global_prompt(instructions_text="inactive only", activate=False)
    r = client.get("/api/v3/prompt-configs/global/active", headers=_auth_headers())
    assert r.status_code == 404
    assert r.json().get("code") == GLOBAL_PROMPT_CONFIG_NOT_FOUND
