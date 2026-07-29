"""SQL Server TLS / TrustServerCertificate policy (Phase 4 corrections)."""

from __future__ import annotations

import os
import re
from typing import Literal

from src.runtime.container.runtime_environment import (
    RuntimeEnvironment,
    resolve_runtime_environment,
)

_TRUST_YES = frozenset({"1", "true", "yes", "y", "on"})
_TRUST_NO = frozenset({"0", "false", "no", "n", "off"})

_TRUST_KW_RE = re.compile(r"(?i)TrustServerCertificate\s*=\s*([^;]*)")
_ENCRYPT_KW_RE = re.compile(r"(?i)Encrypt\s*=\s*([^;]*)")


class SqlServerTlsPolicyError(ValueError):
    """Raised when SQL TLS settings violate hosted fail-safe policy."""


def parse_strict_bool(raw: str, *, field_name: str) -> bool:
    token = raw.strip().lower()
    if token in _TRUST_YES:
        return True
    if token in _TRUST_NO:
        return False
    raise SqlServerTlsPolicyError(
        f"{field_name} must be a boolean "
        f"(true/false/yes/no/1/0); got {raw!r}"
    )


def _is_local_like(env: RuntimeEnvironment) -> bool:
    return env in (
        RuntimeEnvironment.TEST,
        RuntimeEnvironment.LOCAL,
        RuntimeEnvironment.DEVELOPMENT,
    )


def resolve_trust_server_certificate(*, env: RuntimeEnvironment | None = None) -> bool:
    """Return whether TrustServerCertificate should be enabled.

    * local/test/development: default **yes** (configurable)
    * staging/preproduction/production/unknown: default **no**
    * explicit env always wins after strict parse
    """
    e = env if env is not None else resolve_runtime_environment()
    raw = os.getenv("SQLSERVER_TRUST_SERVER_CERTIFICATE")
    if raw is not None and raw.strip() != "":
        return parse_strict_bool(raw, field_name="SQLSERVER_TRUST_SERVER_CERTIFICATE")
    return _is_local_like(e)


def trust_server_certificate_odbc_keyword(*, env: RuntimeEnvironment | None = None) -> str:
    enabled = resolve_trust_server_certificate(env=env)
    return "TrustServerCertificate=yes" if enabled else "TrustServerCertificate=no"


def allow_insecure_sql_trust_exception() -> bool:
    """Explicit break-glass for hosted TrustServerCertificate=yes (ops-owned)."""
    raw = (os.getenv("SQLSERVER_ALLOW_INSECURE_TRUST") or "").strip()
    if not raw:
        return False
    return parse_strict_bool(raw, field_name="SQLSERVER_ALLOW_INSECURE_TRUST")


def _odbc_kw_value(cs: str, pattern: re.Pattern[str]) -> str | None:
    m = pattern.search(cs)
    if not m:
        return None
    return m.group(1).strip()


def validate_sqlserver_connection_tls(
    connection_string: str,
    *,
    env: RuntimeEnvironment | None = None,
) -> None:
    """Enforce hosted TLS policy on a full ODBC connection string.

    Hosted/unknown: TrustServerCertificate must not be yes unless
    ``SQLSERVER_ALLOW_INSECURE_TRUST=true``. Encrypt should be present and not false.
    """
    cs = (connection_string or "").strip()
    if not cs:
        return
    e = env if env is not None else resolve_runtime_environment()
    if _is_local_like(e):
        return

    trust_raw = _odbc_kw_value(cs, _TRUST_KW_RE)
    if trust_raw is not None:
        trust_on = parse_strict_bool(trust_raw, field_name="TrustServerCertificate")
        if trust_on and not allow_insecure_sql_trust_exception():
            raise SqlServerTlsPolicyError(
                "Hosted runtimes forbid TrustServerCertificate=yes in the connection string "
                "unless SQLSERVER_ALLOW_INSECURE_TRUST=true (documented break-glass)."
            )

    encrypt_raw = _odbc_kw_value(cs, _ENCRYPT_KW_RE)
    if encrypt_raw is None:
        raise SqlServerTlsPolicyError(
            "Hosted runtimes require Encrypt=yes (or equivalent) in SQLSERVER_CONNECTION_STRING."
        )
    encrypt_on = parse_strict_bool(encrypt_raw, field_name="Encrypt")
    if not encrypt_on:
        raise SqlServerTlsPolicyError(
            "Hosted runtimes forbid Encrypt=no in SQLSERVER_CONNECTION_STRING."
        )


def ensure_encrypt_keyword(connection_string: str, *, env: RuntimeEnvironment | None = None) -> str:
    """Append Encrypt=yes for hosted split-built strings when missing."""
    e = env if env is not None else resolve_runtime_environment()
    cs = connection_string.rstrip(";")
    if _odbc_kw_value(cs, _ENCRYPT_KW_RE) is not None:
        return connection_string if connection_string.endswith(";") else cs + ";"
    if _is_local_like(e):
        # Prefer encrypt even locally when using Driver 18; still allow override via full string.
        return f"{cs};Encrypt=yes;"
    return f"{cs};Encrypt=yes;"


RuntimeTlsProfile = Literal["local_like", "hosted"]


def tls_profile(env: RuntimeEnvironment | None = None) -> RuntimeTlsProfile:
    e = env if env is not None else resolve_runtime_environment()
    return "local_like" if _is_local_like(e) else "hosted"
