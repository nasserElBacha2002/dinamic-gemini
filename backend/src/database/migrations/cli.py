"""CLI implementation for schema migrate / validate / status.

Invoked via ``python scripts/db_migrate.py`` (wrapper) or
``cd backend && python -m src.database.migrations``.
"""

from __future__ import annotations

import argparse
import json

from src.config import load_settings
from src.database.migrations import (
    ensure_schema_compatibility,
    get_migration_status,
    get_required_schema_version,
    run_pending_migrations,
)
from src.database.sqlserver import SqlServerClient


def _build_client() -> SqlServerClient:
    settings = load_settings()
    return SqlServerClient(settings.require_sqlserver_connection_string())


def _required_version() -> str:
    settings = load_settings()
    return settings.db_schema_required_version or get_required_schema_version() or "0000"


def _print(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False))


def cmd_status() -> int:
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
    parser.add_argument("command", choices=["status", "validate", "apply"])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "status":
        return cmd_status()
    if args.command == "validate":
        return cmd_validate()
    if args.command == "apply":
        return cmd_apply()
    return 1
