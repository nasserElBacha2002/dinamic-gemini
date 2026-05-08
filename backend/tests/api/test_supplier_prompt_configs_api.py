from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.errors.structured_api_http import (
    CLIENT_SUPPLIER_CLIENT_MISMATCH,
    SUPPLIER_PROMPT_CONFIG_EMPTY_INSTRUCTIONS,
    SUPPLIER_PROMPT_CONFIG_INVALID_MODEL,
    SUPPLIER_PROMPT_CONFIG_INVALID_PROVIDER,
    SUPPLIER_PROMPT_CONFIG_INVALID_SCOPE,
    SUPPLIER_PROMPT_CONFIG_NOT_FOUND,
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


def _create_client(name: str = "Client Prompt") -> str:
    r = client.post(
        "/api/v3/clients/",
        json={"name": name, "status": "active"},
        headers=_auth_headers(),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_supplier(client_id: str, name: str = "Supplier Prompt") -> str:
    r = client.post(
        f"/api/v3/clients/{client_id}/suppliers",
        json={"name": name, "status": "active"},
        headers=_auth_headers(),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_prompt_config(
    client_id: str,
    supplier_id: str,
    *,
    provider_name: str = "gemini",
    model_name: str | None = None,
    instructions_text: str = "Priorizar etiquetas claras",
    activate: bool = True,
) -> dict:
    r = client.post(
        f"/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs",
        json={
            "provider_name": provider_name,
            "model_name": model_name,
            "instructions_text": instructions_text,
            "activate": activate,
        },
        headers=_auth_headers(),
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_post_creates_first_active_prompt_config_and_hides_protected_fields() -> None:
    cid = _create_client()
    sid = _create_supplier(cid)
    payload = _create_prompt_config(cid, sid, activate=True)
    assert payload["version"] == 1
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


def test_post_second_active_version_deactivates_previous() -> None:
    cid = _create_client("Version Client")
    sid = _create_supplier(cid, "Version Supplier")
    v1 = _create_prompt_config(cid, sid, instructions_text="v1", activate=True)
    v2 = _create_prompt_config(cid, sid, instructions_text="v2", activate=True)
    assert v2["version"] == 2
    assert v2["is_active"] is True
    r = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs",
        headers=_auth_headers(),
    )
    assert r.status_code == 200, r.text
    rows = {row["id"]: row for row in r.json()["items"]}
    assert rows[v1["id"]]["is_active"] is False
    assert rows[v2["id"]]["is_active"] is True


def test_post_inactive_version_preserves_current_active() -> None:
    cid = _create_client("Inactive Client")
    sid = _create_supplier(cid, "Inactive Supplier")
    v1 = _create_prompt_config(cid, sid, instructions_text="v1", activate=True)
    v2 = _create_prompt_config(cid, sid, instructions_text="v2", activate=False)
    assert v2["is_active"] is False
    r = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs/active",
        params={"provider_name": "gemini"},
        headers=_auth_headers(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == v1["id"]


def test_default_and_model_specific_scopes_are_independent() -> None:
    cid = _create_client("Scope Client")
    sid = _create_supplier(cid, "Scope Supplier")
    default_v1 = _create_prompt_config(
        cid, sid, provider_name="gemini", model_name=None, instructions_text="default v1"
    )
    model_v1 = _create_prompt_config(
        cid,
        sid,
        provider_name="gemini",
        model_name="gemini-2.0-flash-exp",
        instructions_text="model v1",
    )
    default_v2 = _create_prompt_config(
        cid, sid, provider_name="gemini", model_name=None, instructions_text="default v2"
    )
    r_default = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs/active",
        params={"provider_name": "gemini"},
        headers=_auth_headers(),
    )
    r_model = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs/active",
        params={"provider_name": "gemini", "model_name": "gemini-2.0-flash-exp"},
        headers=_auth_headers(),
    )
    assert r_default.status_code == 200 and r_model.status_code == 200
    assert r_default.json()["id"] == default_v2["id"]
    assert r_model.json()["id"] == model_v1["id"]
    assert default_v1["id"] != default_v2["id"]


def test_list_validation_errors_for_scope_provider_model() -> None:
    cid = _create_client("List Rules Client")
    sid = _create_supplier(cid, "List Rules Supplier")
    _create_prompt_config(cid, sid)
    r_scope = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs",
        params={"model_name": "gemini-2.0-flash-exp"},
        headers=_auth_headers(),
    )
    assert r_scope.status_code == 400
    assert r_scope.json().get("code") == SUPPLIER_PROMPT_CONFIG_INVALID_SCOPE

    r_provider = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs",
        params={"provider_name": "unsupported-provider"},
        headers=_auth_headers(),
    )
    assert r_provider.status_code == 400
    assert r_provider.json().get("code") == SUPPLIER_PROMPT_CONFIG_INVALID_PROVIDER

    r_model = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs",
        params={"provider_name": "gemini", "model_name": "gpt-4o"},
        headers=_auth_headers(),
    )
    assert r_model.status_code == 400
    assert r_model.json().get("code") == SUPPLIER_PROMPT_CONFIG_INVALID_MODEL


def test_create_validation_errors_for_provider_model_and_blank_instructions() -> None:
    cid = _create_client("Validation Client")
    sid = _create_supplier(cid, "Validation Supplier")
    r_provider = client.post(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs",
        json={
            "provider_name": "unsupported-provider",
            "model_name": None,
            "instructions_text": "x",
            "activate": True,
        },
        headers=_auth_headers(),
    )
    assert r_provider.status_code == 400
    assert r_provider.json().get("code") == SUPPLIER_PROMPT_CONFIG_INVALID_PROVIDER

    r_model = client.post(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs",
        json={
            "provider_name": "gemini",
            "model_name": "gpt-4o",
            "instructions_text": "x",
            "activate": True,
        },
        headers=_auth_headers(),
    )
    assert r_model.status_code == 400
    assert r_model.json().get("code") == SUPPLIER_PROMPT_CONFIG_INVALID_MODEL

    r_blank = client.post(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs",
        json={
            "provider_name": "gemini",
            "model_name": None,
            "instructions_text": "   ",
            "activate": True,
        },
        headers=_auth_headers(),
    )
    assert r_blank.status_code == 400
    assert r_blank.json().get("code") == SUPPLIER_PROMPT_CONFIG_EMPTY_INSTRUCTIONS


def test_ownership_mismatch_and_not_found_scope_checks() -> None:
    c1 = _create_client("Owner 1")
    c2 = _create_client("Owner 2")
    sid = _create_supplier(c1, "Shared Supplier")
    cfg = _create_prompt_config(c1, sid, instructions_text="owner 1")

    r_mismatch = client.get(
        f"/api/v3/clients/{c2}/suppliers/{sid}/prompt-configs",
        headers=_auth_headers(),
    )
    assert r_mismatch.status_code == 409
    assert r_mismatch.json().get("code") == CLIENT_SUPPLIER_CLIENT_MISMATCH

    sid2 = _create_supplier(c1, "Supplier 2")
    r_not_found = client.get(
        f"/api/v3/clients/{c1}/suppliers/{sid2}/prompt-configs/{cfg['id']}",
        headers=_auth_headers(),
    )
    assert r_not_found.status_code == 404
    assert r_not_found.json().get("code") == SUPPLIER_PROMPT_CONFIG_NOT_FOUND


def test_activate_by_id_and_trimmed_instructions() -> None:
    cid = _create_client("Activate Client")
    sid = _create_supplier(cid, "Activate Supplier")
    v1 = _create_prompt_config(cid, sid, instructions_text="v1", activate=True)
    v2 = _create_prompt_config(cid, sid, instructions_text="  line 1\nline 2  ", activate=False)
    assert v2["instructions_text"] == "line 1\nline 2"

    r_activate = client.post(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs/{v2['id']}/activate",
        headers=_auth_headers(),
    )
    assert r_activate.status_code == 200, r_activate.text
    assert r_activate.json()["id"] == v2["id"]
    assert r_activate.json()["is_active"] is True

    r_active = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs/active",
        params={"provider_name": "gemini"},
        headers=_auth_headers(),
    )
    assert r_active.status_code == 200
    assert r_active.json()["id"] == v2["id"]

    r_list = client.get(
        f"/api/v3/clients/{cid}/suppliers/{sid}/prompt-configs",
        headers=_auth_headers(),
    )
    rows = {row["id"]: row for row in r_list.json()["items"]}
    assert rows[v1["id"]]["is_active"] is False
    assert rows[v2["id"]]["is_active"] is True
