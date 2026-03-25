"""CLI implementation for schema migrate / validate / status.

Invoked via ``python scripts/db_migrate.py`` (wrapper) or
``cd backend && python -m src.database.migrations``.
"""

from __future__ import annotations

import argparse
import json
import sys

from src.config import load_settings, resolve_sqlserver_connection_config
from src.database.migrations import (
    ensure_schema_compatibility,
    get_migration_status,
    get_required_schema_version,
    run_pending_migrations,
)
from src.database.sqlserver import SqlServerClient


def _require_db_config_exit_int() -> int:
    """Return 0 if DB config is usable; print JSON and return 3 if not (preflight contract for CI)."""
    r = resolve_sqlserver_connection_config()
    if r.connection_string.strip():
        return 0
    payload = {
        "ok": False,
        "config_mode": r.mode,
        "missing_env_vars": list(r.missing_env_vars),
        "driver_resolution": r.driver_resolution,
        "hint": r.hint,
    }
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    return 3


def _build_client() -> SqlServerClient:
    settings = load_settings()
    return SqlServerClient(settings.require_sqlserver_connection_string())


def _required_version() -> str:
    settings = load_settings()
    return settings.db_schema_required_version or get_required_schema_version() or "0000"


def _print(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False))


def cmd_config_check() -> int:
    """Print JSON diagnostics (no secrets). Exit 0 if config can build a connection string; else 3."""
    r = resolve_sqlserver_connection_config()
    out = {
        "ok": bool(r.connection_string.strip()),
        "config_mode": r.mode,
        "missing_env_vars": list(r.missing_env_vars),
        "driver_resolution": r.driver_resolution,
        "hint": r.hint if not r.connection_string.strip() else None,
    }
    _print(out)
    return 0 if out["ok"] else 3


def cmd_status() -> int:
    pre = _require_db_config_exit_int()
    if pre != 0:
        return pre
    settings = load_settings()
    status = get_migration_status(
        client=_build_client(),
        service=settings.db_schema_service_name,
        required_version=_required_version(),
    )
    _print(
        {
            "service": status.service,
            "required_version": status.required_version,
            "current_version": status.current_version,
            "compatible": status.compatible,
            "pending_versions": status.pending_versions,
            "last_applied_migration": status.last_applied_migration,
        }
    )
    return 0


def cmd_validate() -> int:
    pre = _require_db_config_exit_int()
    if pre != 0:
        return pre
    settings = load_settings()
    required = _required_version()
    result = ensure_schema_compatibility(
        client=_build_client(),
        service=settings.db_schema_service_name,
        required_version=required,
    )
    _print(
        {
            "service": result.service,
            "required_version": result.required_version,
            "current_version": result.current_version,
            "compatible": result.compatible,
            "last_applied_migration": result.last_applied_migration,
            "reason": result.reason,
        }
    )
    return 0 if result.compatible else 2


def cmd_apply() -> int:
    pre = _require_db_config_exit_int()
    if pre != 0:
        return pre
    settings = load_settings()
    status = run_pending_migrations(
        client=_build_client(),
        service=settings.db_schema_service_name,
        deployment_id=settings.deployment_id,
        lock_timeout_sec=settings.db_schema_migration_lock_timeout_sec,
    )
    _print(
        {
            "service": status.service,
            "required_version": status.required_version,
            "current_version": status.current_version,
            "compatible": status.compatible,
            "pending_versions": status.pending_versions,
            "last_applied_migration": status.last_applied_migration,
        }
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DB schema migration and compatibility utility.")
    parser.add_argument(
        "command",
        choices=["config-check", "doctor", "status", "validate", "apply"],
        help="doctor is an alias for config-check",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cmd = args.command
    if cmd in ("config-check", "doctor"):
        return cmd_config_check()
    if cmd == "status":
        return cmd_status()
    if cmd == "validate":
        return cmd_validate()
    if cmd == "apply":
        return cmd_apply()
    return 1
