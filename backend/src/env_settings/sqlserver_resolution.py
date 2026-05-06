"""SQL Server ODBC connection resolution (split from the monolithic config module for Phase 1 boundaries)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from re import Match

_sqlserver_driver_cache: str | None = None

# Prefer exact Microsoft ODBC names when installed (deterministic vs substring scan order).
_KNOWN_SQLSERVER_ODBC_DRIVERS: tuple[str, ...] = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
)


def _get_available_sqlserver_driver() -> str:
    """Return first ODBC driver name that contains 'SQL Server', or '' if none (e.g. not installed on macOS). Cached per process."""
    global _sqlserver_driver_cache
    if _sqlserver_driver_cache is not None:
        return _sqlserver_driver_cache
    try:
        import pyodbc

        for name in pyodbc.drivers():
            if "SQL Server" in name:
                _sqlserver_driver_cache = name.strip()
                return _sqlserver_driver_cache
    except Exception:
        pass
    _sqlserver_driver_cache = ""
    return _sqlserver_driver_cache


def _pick_odbc_driver_for_split_config(env_driver: str) -> tuple[str, str]:
    """Pick ODBC driver for split-var mode. Returns (driver_name, resolution_source_label)."""
    explicit = env_driver.strip()
    if explicit:
        return explicit, "SQLSERVER_DRIVER"
    try:
        import pyodbc

        installed_set = {x.strip() for x in pyodbc.drivers()}
        for cand in _KNOWN_SQLSERVER_ODBC_DRIVERS:
            if cand in installed_set:
                return cand, "installed_odbc_preference"
        for name in sorted(installed_set):
            if "SQL Server" in name:
                return name, "installed_odbc_substring"
    except Exception:
        pass
    return "", ""


def _dockerenv_present() -> bool:
    """True when running inside a typical Linux container (Docker / containerd)."""
    try:
        return Path("/.dockerenv").is_file()
    except OSError:
        return False


def _is_loopback_host_only(host: str) -> bool:
    h = host.strip()
    if h.startswith("[") and "]" in h:
        h = h[h.index("[") + 1 : h.index("]")].lower()
    else:
        h = h.lower()
    return h in ("localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1")


def _is_loopback_server_field(server_field: str) -> bool:
    """True if ODBC SERVER= value points at loopback (supports ,port and \\instance)."""
    left = server_field.strip().split(",", 1)[0].strip()
    host_only = left.split("\\", 1)[0].strip()
    return _is_loopback_host_only(host_only)


def _remap_sql_server_field(server_field: str, new_host: str) -> str:
    """Replace loopback host with new_host; preserve ,port and \\instance suffix."""
    s = server_field.strip()
    comma = s.find(",")
    if comma >= 0:
        left, right = s[:comma], s[comma + 1 :]
        return f"{_remap_sql_server_host_part(left.strip(), new_host)},{right.strip()}"
    return _remap_sql_server_host_part(s, new_host)


def _remap_sql_server_host_part(host_part: str, new_host: str) -> str:
    if "\\" in host_part:
        h, inst = host_part.split("\\", 1)
        if _is_loopback_host_only(h):
            return f"{new_host}\\{inst}"
        return host_part
    if _is_loopback_host_only(host_part):
        return new_host
    return host_part


def _docker_sql_reachable_host() -> str:
    """Host used when remapping loopback inside a container (Linux: set via SQLSERVER_DOCKER_HOST or extra_hosts)."""
    return (os.getenv("SQLSERVER_DOCKER_HOST") or "").strip() or "host.docker.internal"


def remap_sqlserver_server_for_container_if_needed(server: str) -> str:
    """If inside Docker and SERVER points at loopback, map to host gateway (see SQLSERVER_DOCKER_HOST)."""
    if not _dockerenv_present() or not _is_loopback_server_field(server):
        return server.strip()
    return _remap_sql_server_field(server, _docker_sql_reachable_host())


_ODBC_SERVER_KW_RE = re.compile(r"(?i)(SERVER\s*=\s*)([^;]+)")
_ODBC_DATABASE_KW_RE = re.compile(r"(?i)(DATABASE\s*=\s*)([^;]+)")


def remap_sqlserver_connection_string_server_if_needed(connection_string: str) -> str:
    """Rewrite SERVER= loopback targets inside Docker (full-string config mode)."""

    if not _dockerenv_present():
        return connection_string

    def repl(m: Match[str]) -> str:
        prefix, value = m.group(1), m.group(2).strip()
        if not _is_loopback_server_field(value):
            return m.group(0)
        return prefix + _remap_sql_server_field(value, _docker_sql_reachable_host())

    return _ODBC_SERVER_KW_RE.sub(repl, connection_string)


def odbc_connection_string_server_keyword_value(connection_string: str) -> str | None:
    """Parse SERVER=… from an ODBC string for safe logging (no credentials)."""
    m = _ODBC_SERVER_KW_RE.search(connection_string)
    return m.group(2).strip() if m else None


def odbc_connection_string_database_keyword_value(connection_string: str) -> str | None:
    """Parse DATABASE=… from an ODBC string (safe for logs; no credentials)."""
    m = _ODBC_DATABASE_KW_RE.search(connection_string or "")
    return m.group(2).strip() if m else None


def sqlserver_odbc_server_targets_loopback(connection_string: str) -> bool:
    """True when SERVER= in the ODBC string points at loopback (localhost / 127.0.0.1 / ::1)."""
    server_field = odbc_connection_string_server_keyword_value(connection_string)
    if not server_field:
        return False
    return _is_loopback_server_field(server_field)


def resolved_sqlserver_database_name_from_env() -> str | None:
    """Resolve the database name using the same precedence as connection string resolution.

    ``SQLSERVER_CONNECTION_STRING`` wins over split ``SQLSERVER_DATABASE`` when both are set,
    matching :func:`resolve_sqlserver_connection_config`.
    """
    raw = (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip()
    if raw:
        remapped = remap_sqlserver_connection_string_server_if_needed(raw)
        return odbc_connection_string_database_keyword_value(remapped)
    return (os.getenv("SQLSERVER_DATABASE") or "").strip() or None


@dataclass(frozen=True)
class SqlServerConnectionResolution:
    """Canonical outcome of resolving SQL Server env (no secrets)."""

    mode: str
    """``connection_string`` | ``split_env`` | ``unset`` | ``incomplete_split``."""

    connection_string: str
    missing_env_vars: tuple[str, ...] = ()
    driver_resolution: str | None = None
    """How the ODBC driver was chosen for split mode (e.g. ``SQLSERVER_DRIVER``, ``installed_odbc_preference``)."""

    hint: str | None = None
    """Actionable message when ``connection_string`` is empty (safe for logs / JSON)."""

    sql_server_connect_target: str | None = None
    """``SERVER=`` value used after Docker loopback remapping (safe for logs; no credentials)."""


class SqlServerConfigurationError(ValueError):
    """Raised when SQL Server env is incomplete for building a connection string."""

    def __init__(
        self,
        message: str,
        missing_env_vars: tuple[str, ...] = (),
        *,
        config_mode: str = "",
    ) -> None:
        super().__init__(message)
        self.missing_env_vars = missing_env_vars
        self.config_mode = config_mode


def resolve_sqlserver_connection_config() -> SqlServerConnectionResolution:
    """Single source of truth for SQL Server env → ODBC connection string (canonical resolver)."""
    raw = (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip()
    if raw:
        remapped = remap_sqlserver_connection_string_server_if_needed(raw)
        return SqlServerConnectionResolution(
            mode="connection_string",
            connection_string=remapped,
            missing_env_vars=(),
            driver_resolution="SQLSERVER_CONNECTION_STRING",
            hint=None,
            sql_server_connect_target=odbc_connection_string_server_keyword_value(remapped),
        )

    server = (os.getenv("SQLSERVER_SERVER") or "").strip()
    database = (os.getenv("SQLSERVER_DATABASE") or "").strip()
    uid = (os.getenv("SQLSERVER_UID") or "").strip()
    pwd = (os.getenv("SQLSERVER_PWD") or "").strip()
    env_driver = (os.getenv("SQLSERVER_DRIVER") or "").strip()

    core = {
        "SQLSERVER_SERVER": server,
        "SQLSERVER_DATABASE": database,
        "SQLSERVER_UID": uid,
        "SQLSERVER_PWD": pwd,
    }
    if not any(core.values()):
        return SqlServerConnectionResolution(
            mode="unset",
            connection_string="",
            missing_env_vars=(),
            driver_resolution=None,
            hint=(
                "No SQL Server settings found. Use SQLSERVER_CONNECTION_STRING or set "
                "SQLSERVER_SERVER, SQLSERVER_DATABASE, SQLSERVER_UID, SQLSERVER_PWD (and SQLSERVER_DRIVER "
                "or install Microsoft ODBC Driver for SQL Server). In CI, pass these as job env/secrets."
            ),
            sql_server_connect_target=None,
        )

    missing = tuple(name for name, val in core.items() if not val)
    if missing:
        return SqlServerConnectionResolution(
            mode="incomplete_split",
            connection_string="",
            missing_env_vars=missing,
            driver_resolution=None,
            hint=(
                "Split SQL Server config is incomplete. Set all of: SQLSERVER_SERVER, "
                "SQLSERVER_DATABASE, SQLSERVER_UID, SQLSERVER_PWD. "
                "Run `dinamic-db-migrate config-check` in CI before apply/validate."
            ),
            sql_server_connect_target=None,
        )

    driver, dsrc = _pick_odbc_driver_for_split_config(env_driver)
    if not driver:
        return SqlServerConnectionResolution(
            mode="incomplete_split",
            connection_string="",
            missing_env_vars=("SQLSERVER_DRIVER",),
            driver_resolution=None,
            hint=(
                "No ODBC driver could be resolved. Set SQLSERVER_DRIVER (e.g. 'ODBC Driver 18 for SQL Server') "
                "or install Microsoft ODBC Driver for SQL Server on the runner so pyodbc lists it."
            ),
            sql_server_connect_target=None,
        )

    server_eff = remap_sqlserver_server_for_container_if_needed(server)
    cs = (
        f"DRIVER={{{driver}}};SERVER={server_eff};DATABASE={database};UID={uid};PWD={pwd};"
        "TrustServerCertificate=yes"
    )
    return SqlServerConnectionResolution(
        mode="split_env",
        connection_string=cs,
        missing_env_vars=(),
        driver_resolution=dsrc,
        hint=None,
        sql_server_connect_target=server_eff,
    )


def resolve_sqlserver_effective_connection_string() -> tuple[str, tuple[str, ...]]:
    """Backward-compatible: ``(connection_string, missing_env_var_names)`` from :func:`resolve_sqlserver_connection_config`."""
    r = resolve_sqlserver_connection_config()
    return r.connection_string, r.missing_env_vars


def sqlserver_configuration_error_message(resolution: SqlServerConnectionResolution) -> str:
    """Human-readable, actionable error (no secrets)."""
    if resolution.connection_string.strip():
        return ""
    if resolution.mode == "unset":
        return (
            "SQL Server connection not configured (config_mode=unset). "
            "Set SQLSERVER_CONNECTION_STRING, or set all split variables: "
            "SQLSERVER_SERVER, SQLSERVER_DATABASE, SQLSERVER_UID, SQLSERVER_PWD "
            "(and SQLSERVER_DRIVER if no supported ODBC driver is installed on this host). "
            "In GitHub Actions, pass secrets into the migrate job environment (see docs). "
            "Preflight: `dinamic-db-migrate config-check`."
        )
    if resolution.mode == "incomplete_split":
        if resolution.missing_env_vars:
            return (
                f"Incomplete split SQL Server config (config_mode=incomplete_split). "
                f"Missing or empty: {', '.join(resolution.missing_env_vars)}. "
                f"Alternatively set SQLSERVER_CONNECTION_STRING. "
                f"{resolution.hint or ''}"
            ).strip()
    return resolution.hint or "SQL Server configuration invalid."


def default_sqlserver_connection_string() -> str:
    """Effective ODBC string or empty (used as Settings.sqlserver_connection_string default)."""
    return resolve_sqlserver_connection_config().connection_string
