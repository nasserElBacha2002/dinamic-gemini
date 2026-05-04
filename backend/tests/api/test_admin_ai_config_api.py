"""GET /api/v3/admin/ai-config — primary principal (``AuthUser.id``) gate + secret-free payload."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser


def _restore_default_admin_override() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )


def test_admin_ai_config_returns_200_for_username_admin() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.get("/api/v3/admin/ai-config")
    finally:
        _restore_default_admin_override()

    assert r.status_code == 200
    body = r.json()
    assert "generated_at" in body
    assert body["server_defaults"]["llm_provider"]
    assert isinstance(body["providers"], list)
    assert len(body["providers"]) >= 4
    keys = {p["key"] for p in body["providers"]}
    assert keys == {"gemini", "openai", "claude", "deepseek"}
    assert any(
        p["key"] == "deepseek" and p["capabilities"]["multimodal_aisle_analysis_supported"] is False
        for p in body["providers"]
    )
    assert isinstance(body["prompt_catalog"], list)
    deepseek = next(p for p in body["providers"] if p["key"] == "deepseek")
    assert isinstance(deepseek["prompt_variant_summaries"], list)
    assert len(deepseek["prompt_variant_summaries"]) >= 1
    assert "composed_prompt_text" not in json.dumps(body)
    assert "response_contract" in deepseek
    assert "global_instructions_note" in body


def test_admin_ai_config_401_without_bearer_token() -> None:
    app.dependency_overrides.pop(get_current_admin, None)
    try:
        client = TestClient(app)
        r = client.get("/api/v3/admin/ai-config")
        assert r.status_code == 401
    finally:
        _restore_default_admin_override()


def test_admin_ai_config_403_when_principal_is_secondary_jairo() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="jairo", username="Jairo", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.get("/api/v3/admin/ai-config")
    finally:
        _restore_default_admin_override()

    assert r.status_code == 403
    err = r.json().get("error", {})
    assert err.get("code") == "FORBIDDEN"


def test_admin_ai_config_200_when_primary_principal_even_if_login_username_not_literal_admin() -> (
    None
):
    """Primary principal is keyed by ``AuthUser.id``; visible username may differ from 'admin'."""
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="ops-admin", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.get("/api/v3/admin/ai-config")
    finally:
        _restore_default_admin_override()

    assert r.status_code == 200


def test_admin_ai_config_does_not_leak_credential_like_strings() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.get("/api/v3/admin/ai-config")
    finally:
        _restore_default_admin_override()

    assert r.status_code == 200
    blob = json.dumps(r.json()).lower()
    # Catalog prose may name env vars (e.g. "gemini_api_key required"); assert no material secret patterns.
    forbidden = (
        "password_hash",
        "token_secret",
        "sk-proj",
        "sk-ant",
    )
    for frag in forbidden:
        assert frag not in blob, f"unexpected secret-like fragment: {frag}"


def test_admin_ai_composed_prompt_200() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.get(
            "/api/v3/admin/ai-config/composed-prompt",
            params={
                "prompt_key": "global_v21",
                "pipeline_provider_key": "gemini",
                "prompt_parity_mode": False,
            },
        )
    finally:
        _restore_default_admin_override()

    assert r.status_code == 200
    data = r.json()
    assert data["prompt_key"] == "global_v21"
    assert data["pipeline_provider_key"] == "gemini"
    assert data["prompt_parity_mode"] is False
    assert isinstance(data.get("composed_prompt_text"), str)
    assert len(data["composed_prompt_text"]) > 0


def test_admin_ai_composed_prompt_400_invalid_profile() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.get(
            "/api/v3/admin/ai-config/composed-prompt",
            params={
                "prompt_key": "not_a_real_profile_zzzz",
                "pipeline_provider_key": "gemini",
                "prompt_parity_mode": False,
            },
        )
    finally:
        _restore_default_admin_override()

    assert r.status_code == 400


def test_admin_ai_composed_prompt_400_parity_on_non_openai() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.get(
            "/api/v3/admin/ai-config/composed-prompt",
            params={
                "prompt_key": "global_v21",
                "pipeline_provider_key": "claude",
                "prompt_parity_mode": True,
            },
        )
    finally:
        _restore_default_admin_override()

    assert r.status_code == 400


def test_admin_ai_composed_prompt_200_for_primary_principal_non_literal_admin_username() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="ops-admin", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.get(
            "/api/v3/admin/ai-config/composed-prompt",
            params={
                "prompt_key": "global_v21",
                "pipeline_provider_key": "gemini",
                "prompt_parity_mode": False,
            },
        )
    finally:
        _restore_default_admin_override()

    assert r.status_code == 200
