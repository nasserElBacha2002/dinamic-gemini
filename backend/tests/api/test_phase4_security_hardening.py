"""Phase 4 — HTTP security hardening (CORS, headers, API key compare)."""

from __future__ import annotations

import hashlib
import secrets

import pytest
from fastapi.testclient import TestClient

from src.api.security_headers import normalize_cors_allow_origins
from src.config import reload_settings
from src.pipeline.secret_redaction import REDACTED, redact_secrets_in_text


def test_normalize_cors_rejects_wildcard_with_credentials() -> None:
    with pytest.raises(ValueError, match="must not include"):
        normalize_cors_allow_origins("*", allow_credentials=True)


def test_normalize_cors_allows_explicit_origins() -> None:
    origins = normalize_cors_allow_origins(
        "https://app.example.com, https://admin.example.com",
        allow_credentials=True,
    )
    assert origins == ["https://app.example.com", "https://admin.example.com"]


def test_normalize_cors_default_localhost_when_empty() -> None:
    origins = normalize_cors_allow_origins("", allow_credentials=True)
    assert "http://localhost:5173" in origins


def test_security_headers_on_health() -> None:
    from src.api.server import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in (resp.headers.get("Permissions-Policy") or "")


def test_api_key_reject_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "expected-secret-key")
    reload_settings()
    from src.api.server import app

    client = TestClient(app)
    resp = client.get("/ready", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 403
    monkeypatch.delenv("API_KEY", raising=False)
    reload_settings()


def test_api_key_accept_correct_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "expected-secret-key")
    reload_settings()
    from src.api.server import app

    client = TestClient(app)
    resp = client.get("/health", headers={"X-API-Key": "expected-secret-key"})
    assert resp.status_code == 200
    resp2 = client.get("/ready", headers={"X-API-Key": "expected-secret-key"})
    assert resp2.status_code != 403
    monkeypatch.delenv("API_KEY", raising=False)
    reload_settings()


def test_api_key_compare_digest_equal_hashes() -> None:
    a = "same-key"
    b = "same-key"
    assert secrets.compare_digest(
        hashlib.sha256(a.encode()).digest(),
        hashlib.sha256(b.encode()).digest(),
    )
    assert not secrets.compare_digest(
        hashlib.sha256(b"a").digest(),
        hashlib.sha256(b"b").digest(),
    )


def test_secret_redaction_sas_and_jwt() -> None:
    sas = "https://acct.blob.core.windows.net/c/b?sv=2022-11-02&sig=DEADBEEF&se=2099-01-01"
    out = redact_secrets_in_text(sas)
    assert "DEADBEEF" not in out
    assert REDACTED in out

    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signaturepart"
    out2 = redact_secrets_in_text(f"auth {jwt}")
    assert "signaturepart" not in out2


def test_trust_server_certificate_env_no(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.env_settings.sqlserver_resolution import _sqlserver_trust_server_certificate_keyword

    monkeypatch.setenv("SQLSERVER_TRUST_SERVER_CERTIFICATE", "no")
    assert _sqlserver_trust_server_certificate_keyword() == "TrustServerCertificate=no"
    monkeypatch.setenv("SQLSERVER_TRUST_SERVER_CERTIFICATE", "yes")
    assert _sqlserver_trust_server_certificate_keyword() == "TrustServerCertificate=yes"
