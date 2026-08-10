"""Phase 4 corrections — API key Model A, CORS hosted, SQL TLS, redaction."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.api_key_policy import (
    api_keys_match,
    parse_api_key_path_prefixes,
    path_requires_api_key,
)
from src.api.security_headers import (
    SAFE_CORS_ALLOW_HEADERS,
    CorsPolicyError,
    normalize_cors_allow_origins,
    resolve_hsts_enabled,
)
from src.config import reload_settings
from src.env_settings.sql_tls_policy import (
    SqlServerTlsPolicyError,
    resolve_trust_server_certificate,
    validate_sqlserver_connection_tls,
)
from src.pipeline.secret_redaction import REDACTED, redact_secrets_in_text, redact_secrets_in_value
from src.runtime.container.runtime_environment import RuntimeEnvironment


def test_model_a_api_key_not_required_globally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "expected-secret-key")
    monkeypatch.delenv("API_KEY_REQUIRED_PATH_PREFIXES", raising=False)
    reload_settings()
    from src.api.server import app

    client = TestClient(app)
    # Public readiness must not demand X-API-Key when prefixes empty (Model A).
    resp = client.get("/ready")
    assert resp.status_code != 403
    monkeypatch.delenv("API_KEY", raising=False)
    reload_settings()


def test_api_key_enforced_only_on_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "expected-secret-key")
    monkeypatch.setenv("API_KEY_REQUIRED_PATH_PREFIXES", "/api/v3/admin")
    reload_settings()
    from src.api.server import app

    client = TestClient(app)
    assert client.get("/ready").status_code != 403
    denied = client.get("/api/v3/admin/phase4-key-probe")
    assert denied.status_code == 403
    accepted = client.get(
        "/api/v3/admin/phase4-key-probe",
        headers={"X-API-Key": "expected-secret-key"},
    )
    # Key accepted → not the API-key 403 (may be 401/404 afterward).
    assert accepted.status_code != 403 or accepted.json().get("detail") != "Invalid or missing API key"
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_KEY_REQUIRED_PATH_PREFIXES", raising=False)
    reload_settings()


def test_path_requires_api_key_helpers() -> None:
    assert path_requires_api_key("/health", ["/api/v3/admin"]) is False
    assert path_requires_api_key("/ready", ["/api/v3/admin"]) is False
    assert path_requires_api_key("/api/v3/admin/x", ["/api/v3/admin"]) is True
    assert path_requires_api_key("/api/v3/clients", ["/api/v3/admin"]) is False
    assert parse_api_key_path_prefixes("") == []
    assert api_keys_match("a", "a")
    assert not api_keys_match("a", "b")


def test_cors_hosted_requires_https() -> None:
    with pytest.raises(CorsPolicyError):
        normalize_cors_allow_origins(
            "",
            allow_credentials=True,
            env=RuntimeEnvironment.PRODUCTION,
        )
    with pytest.raises(CorsPolicyError):
        normalize_cors_allow_origins(
            "http://app.example.com",
            allow_credentials=True,
            env=RuntimeEnvironment.PRODUCTION,
        )
    with pytest.raises(CorsPolicyError):
        normalize_cors_allow_origins(
            "https://localhost:5173",
            allow_credentials=True,
            env=RuntimeEnvironment.STAGING,
        )
    origins = normalize_cors_allow_origins(
        "https://app.example.com, https://app.example.com",
        allow_credentials=True,
        env=RuntimeEnvironment.PRODUCTION,
    )
    assert origins == ["https://app.example.com"]


def test_cors_local_defaults() -> None:
    origins = normalize_cors_allow_origins(
        "",
        allow_credentials=True,
        env=RuntimeEnvironment.LOCAL,
    )
    assert "http://localhost:5173" in origins


def test_hsts_requires_hosted_and_forwarded() -> None:
    on, _ = resolve_hsts_enabled(
        env=RuntimeEnvironment.PRODUCTION,
        enable_hsts_env="true",
        forwarded_trusted_hosts="*.example.com",
    )
    assert on is True
    off, _ = resolve_hsts_enabled(
        env=RuntimeEnvironment.PRODUCTION,
        enable_hsts_env="true",
        forwarded_trusted_hosts="",
    )
    assert off is False
    off_local, _ = resolve_hsts_enabled(
        env=RuntimeEnvironment.LOCAL,
        enable_hsts_env="true",
        forwarded_trusted_hosts="*",
    )
    assert off_local is False


def test_sql_tls_hosted_default_no(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SQLSERVER_TRUST_SERVER_CERTIFICATE", raising=False)
    assert resolve_trust_server_certificate(env=RuntimeEnvironment.PRODUCTION) is False
    assert resolve_trust_server_certificate(env=RuntimeEnvironment.LOCAL) is True


def test_sql_tls_invalid_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_TRUST_SERVER_CERTIFICATE", "yeah")
    with pytest.raises(SqlServerTlsPolicyError):
        resolve_trust_server_certificate(env=RuntimeEnvironment.LOCAL)


def test_sql_tls_full_string_hosted_rejects_trust_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SQLSERVER_ALLOW_INSECURE_TRUST", raising=False)
    cs = (
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=db;DATABASE=d;UID=u;PWD=p;"
        "Encrypt=yes;TrustServerCertificate=yes"
    )
    with pytest.raises(SqlServerTlsPolicyError):
        validate_sqlserver_connection_tls(cs, env=RuntimeEnvironment.PRODUCTION)


def test_sql_tls_full_string_requires_encrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    cs = "DRIVER={x};SERVER=db;DATABASE=d;UID=u;PWD=p;TrustServerCertificate=no"
    with pytest.raises(SqlServerTlsPolicyError, match="Encrypt"):
        validate_sqlserver_connection_tls(cs, env=RuntimeEnvironment.PRODUCTION)


def test_secret_redaction_preserves_sas_structure() -> None:
    sas = "https://acct.blob.core.windows.net/c/b?sv=2022-11-02&sig=DEADBEEF&se=2099-01-01"
    out = redact_secrets_in_text(sas)
    assert "DEADBEEF" not in out
    assert "sig=" + REDACTED in out
    assert "se=" + REDACTED in out
    assert "?" in out and "&" in out

    aws = "https://s3.amazonaws.com/b/k?X-Amz-Signature=AABBCC&X-Amz-Credential=AKIA"
    out2 = redact_secrets_in_text(aws)
    assert "AABBCC" not in out2
    assert "X-Amz-Signature=" + REDACTED in out2

    nested = redact_secrets_in_value(
        {"authorization": "Bearer abc", "input_tokens": 12, "url": sas}
    )
    assert nested["authorization"] == REDACTED
    assert nested["input_tokens"] == 12


def test_security_headers_on_health() -> None:
    from src.api.server import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


def test_cors_allowlist_includes_standard_idempotency_key() -> None:
    """Frontend and v3 routes use ``Idempotency-Key`` (not only ``X-Idempotency-Key``)."""
    allowed = {h.lower() for h in SAFE_CORS_ALLOW_HEADERS}
    assert "idempotency-key" in allowed
    assert "x-idempotency-key" in allowed
