"""Unit tests for disposable lab attestation gate (Phase 4B)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import lab_attestation as lab_mod
from src.api.routes.lab_attestation import lab_attestation_enabled, router


@pytest.fixture
def lab_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_lab_attestation_disabled_returns_404(monkeypatch: pytest.MonkeyPatch, lab_app: FastAPI) -> None:
    monkeypatch.setenv("LAB_DISPOSABLE_ENABLED", "false")
    monkeypatch.setenv("V3_RUNTIME_ENVIRONMENT", "local")
    monkeypatch.delenv("APP_ENV", raising=False)
    assert lab_attestation_enabled() is False
    client = TestClient(lab_app)
    resp = client.get("/lab/health")
    assert resp.status_code == 404


def test_lab_attestation_production_like_returns_404_even_when_enabled(
    monkeypatch: pytest.MonkeyPatch, lab_app: FastAPI
) -> None:
    monkeypatch.setenv("LAB_DISPOSABLE_ENABLED", "true")
    monkeypatch.setenv("V3_RUNTIME_ENVIRONMENT", "production")
    monkeypatch.setenv("APP_ENV", "production")
    assert lab_attestation_enabled() is False
    client = TestClient(lab_app)
    resp = client.get("/lab/health")
    assert resp.status_code == 404


def test_lab_attestation_local_enabled_returns_200_when_mocked_healthy(
    monkeypatch: pytest.MonkeyPatch, lab_app: FastAPI
) -> None:
    monkeypatch.setenv("LAB_DISPOSABLE_ENABLED", "true")
    monkeypatch.setenv("V3_RUNTIME_ENVIRONMENT", "local")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LAB_LLM_MOCKED", "true")
    monkeypatch.setenv("LAB_SEED_LOADED", "true")
    monkeypatch.setenv("LAB_RUN_ID", "lab-test-run-1")
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "local")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    monkeypatch.setattr(lab_mod, "_sql_healthy", lambda: True)
    monkeypatch.setattr(lab_mod, "_worker_operable", lambda: True)
    monkeypatch.setattr(lab_mod, "_gemini_commit", lambda: "deadbeef")

    assert lab_attestation_enabled() is True
    client = TestClient(lab_app)
    resp = client.get("/lab/health", params={"audit_run_id": "lab-test-run-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["disposable"] is True
    assert body["llm_mocked"] is True
    assert body["storage"] == "local"
    assert body["audit_run_id"] == "lab-test-run-1"
    assert body["nonce"] == "HEALTHCHECK_lab-test-run-1"
    assert body["environment"] == "local"
    assert body["environment_class"] == "LOCAL_ISOLATED_ONLY"
    assert body["status"] == "ready"
    assert body["database"] == "healthy"
    assert body["seed_loaded"] is True
    assert body["worker_operable"] is True
    assert body["lab_run_id"] == "lab-test-run-1"
    assert body["gemini_commit"] == "deadbeef"
    # Never leak secrets
    blob = str(body).lower()
    assert "token" not in blob
    assert "secret" not in blob
    assert "password" not in blob
