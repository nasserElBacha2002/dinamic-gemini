"""GET /api/v3/admin/ai-config — admin username gate + secret-free payload."""

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
        p["key"] == "deepseek"
        and p["overview"]["multimodal_aisle_analysis_supported"] is False
        for p in body["providers"]
    )
    assert isinstance(body["prompt_catalog"], list)
    deepseek = next(p for p in body["providers"] if p["key"] == "deepseek")
    assert isinstance(deepseek["prompt_variants"], list)
    assert len(deepseek["prompt_variants"]) >= 1
    assert "response_contract" in deepseek
    assert "global_instructions_note" in body
    assert "prompt_variants" not in body


def test_admin_ai_config_403_when_username_not_admin() -> None:
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="ops-admin", role="administrator"
    )
    try:
        client = TestClient(app)
        r = client.get("/api/v3/admin/ai-config")
    finally:
        _restore_default_admin_override()

    assert r.status_code == 403
    err = r.json().get("error", {})
    assert err.get("code") == "FORBIDDEN"


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
    forbidden = (
        "deepseek_api_key",
        "openai_api_key",
        "gemini_api_key",
        "anthropic_api_key",
        "password_hash",
        "token_secret",
        "sk-proj",
        "sk-ant",
    )
    for frag in forbidden:
        assert frag not in blob, f"unexpected secret-like fragment: {frag}"
