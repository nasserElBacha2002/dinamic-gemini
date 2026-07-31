#!/usr/bin/env python3
"""Validate Phase 1 positioning SQL migrations (0074 / 0075) safely.

Documents and optionally runs: apply → validate objects → rollback → reapply.

Behavior:
  - If SQL Server is not configured (no SQLSERVER_* connection), exit 0 with SKIP
    and write a short report under ``review/`` when possible.
  - If SQL Server is configured, run a non-destructive *object presence* check after
    applying UP scripts via the migration batch splitter, then execute matching
    ``*.down.sql`` and re-apply UPs. Never defaults to production DB names.

Usage (from repo root or backend/):
  python backend/scripts/validate_phase1_sql_migration.py

Env (same as the rest of the backend):
  SQLSERVER_CONNECTION_STRING
  or SQLSERVER_SERVER + SQLSERVER_DATABASE + SQLSERVER_UID + SQLSERVER_PWD
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

_VERSIONS = _BACKEND_ROOT / "src" / "database" / "migrations" / "versions"
_UP_0074 = _VERSIONS / "0074_ordered_capture_sessions_and_positioning_foundation.sql"
_DOWN_0074 = _VERSIONS / "0074_ordered_capture_sessions_and_positioning_foundation.down.sql"
_UP_0075 = _VERSIONS / "0075_phase1_positioning_corrections.sql"
_DOWN_0075 = _VERSIONS / "0075_phase1_positioning_corrections.down.sql"

_REQUIRED_OBJECTS_SQL = """
SELECT
    CASE WHEN OBJECT_ID(N'dbo.ordered_capture_sessions', N'U') IS NOT NULL THEN 1 ELSE 0 END
        AS has_ordered_capture_sessions,
    CASE WHEN OBJECT_ID(N'dbo.aisle_locations', N'U') IS NOT NULL THEN 1 ELSE 0 END
        AS has_aisle_locations,
    CASE WHEN OBJECT_ID(N'dbo.aisle_location_labels', N'U') IS NOT NULL THEN 1 ELSE 0 END
        AS has_aisle_location_labels,
    CASE WHEN COL_LENGTH(N'dbo.ordered_capture_sessions', N'open_aisle_key') IS NOT NULL THEN 1 ELSE 0 END
        AS has_open_aisle_key_obsolete,
    CASE WHEN COL_LENGTH(N'dbo.aisle_location_labels', N'idempotency_key') IS NOT NULL THEN 1 ELSE 0 END
        AS has_label_idempotency_key,
    CASE WHEN EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'UQ_ordered_capture_sessions_one_open_per_aisle'
          AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
    ) THEN 1 ELSE 0 END AS has_one_open_uq,
    CASE WHEN EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'UQ_aisle_location_labels_client_idempotency'
          AND object_id = OBJECT_ID(N'dbo.aisle_location_labels')
    ) THEN 1 ELSE 0 END AS has_label_idempotency_uq
"""


def _sqlserver_env_present() -> bool:
    if (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip():
        return True
    keys = ("SQLSERVER_SERVER", "SQLSERVER_DATABASE", "SQLSERVER_UID", "SQLSERVER_PWD")
    return all((os.getenv(k) or "").strip() for k in keys)


def _report_path() -> Path:
    review = _REPO_ROOT / "review"
    review.mkdir(parents=True, exist_ok=True)
    return review / "phase1_sql_migration_validation.txt"


def _write_report(lines: list[str]) -> Path:
    path = _report_path()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = "\n".join([f"# Phase 1 SQL migration validation — {stamp}", *lines, ""])
    path.write_text(body, encoding="utf-8")
    return path


def _execute_sql_file(client, path: Path) -> None:
    from src.database.migrations.service import _split_sql_batches

    text = path.read_text(encoding="utf-8")
    for batch in _split_sql_batches(text):
        with client.cursor() as cur:
            cur.execute(batch)


def _validate_objects(client) -> dict[str, int]:
    with client.cursor() as cur:
        cur.execute(_REQUIRED_OBJECTS_SQL)
        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
    return {cols[i]: int(row[i]) for i in range(len(cols))}


def _assert_phase1_present(flags: dict[str, int]) -> None:
    required_one = {
        "has_ordered_capture_sessions",
        "has_aisle_locations",
        "has_aisle_location_labels",
        "has_label_idempotency_key",
        "has_one_open_uq",
        "has_label_idempotency_uq",
    }
    missing = [k for k in required_one if flags.get(k, 0) != 1]
    if missing:
        raise RuntimeError(f"Phase 1 objects missing after apply: {missing}")
    # open_aisle_key was a failed draft approach (SQL error 10609); must be gone.
    if flags.get("has_open_aisle_key_obsolete", 0) != 0:
        raise RuntimeError(
            "obsolete column open_aisle_key still present after 0075 "
            "(filtered indexes cannot reference computed columns)"
        )


def main() -> int:
    lines: list[str] = []
    for label, path in (
        ("UP 0074", _UP_0074),
        ("DOWN 0074", _DOWN_0074),
        ("UP 0075", _UP_0075),
        ("DOWN 0075", _DOWN_0075),
    ):
        lines.append(f"artifact {label}: {'OK' if path.is_file() else 'MISSING'} ({path})")

    if not all(p.is_file() for p in (_UP_0074, _DOWN_0074, _UP_0075, _DOWN_0075)):
        report = _write_report([*lines, "result: FAIL (missing SQL artifacts)"])
        print(f"FAIL: missing Phase 1 SQL artifacts; report={report}")
        return 1

    if not _sqlserver_env_present():
        lines.extend(
            [
                "sqlserver: not configured",
                "result: SKIP",
                "note: set SQLSERVER_CONNECTION_STRING or SQLSERVER_SERVER/"
                "DATABASE/UID/PWD to run apply-validate-rollback-reapply",
            ]
        )
        report = _write_report(lines)
        print(f"SKIP: SQL Server not configured; report={report}")
        return 0

    db_name = (os.getenv("SQLSERVER_DATABASE") or "").strip().lower()
    # Refuse obvious production-ish names unless explicitly overridden.
    allow_prod = (os.getenv("PHASE1_SQL_VALIDATE_ALLOW_NON_TEST") or "").strip() == "1"
    if not allow_prod and db_name and "test" not in db_name and "dev" not in db_name:
        lines.extend(
            [
                f"sqlserver: refusing database={db_name!r} (name must contain 'test' or 'dev')",
                "result: SKIP",
                "note: set PHASE1_SQL_VALIDATE_ALLOW_NON_TEST=1 to override (use with care)",
            ]
        )
        report = _write_report(lines)
        print(f"SKIP: refusing non-test database; report={report}")
        return 0

    try:
        from src.database.sqlserver import SqlServerClient
        from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config

        conn_str = resolve_sqlserver_connection_config().connection_string
        client = SqlServerClient(conn_str)

        lines.append("step: apply 0074")
        _execute_sql_file(client, _UP_0074)
        lines.append("step: apply 0075")
        _execute_sql_file(client, _UP_0075)
        flags = _validate_objects(client)
        lines.append(f"validate after apply: {flags}")
        _assert_phase1_present(flags)

        lines.append("step: rollback 0075")
        _execute_sql_file(client, _DOWN_0075)
        lines.append("step: rollback 0074")
        _execute_sql_file(client, _DOWN_0074)

        lines.append("step: reapply 0074")
        _execute_sql_file(client, _UP_0074)
        lines.append("step: reapply 0075")
        _execute_sql_file(client, _UP_0075)
        flags2 = _validate_objects(client)
        lines.append(f"validate after reapply: {flags2}")
        _assert_phase1_present(flags2)

        lines.append("result: PASS")
        report = _write_report(lines)
        print(f"PASS: Phase 1 apply-validate-rollback-reapply OK; report={report}")
        return 0
    except Exception as exc:
        lines.extend([f"error: {exc}", "result: FAIL"])
        report = _write_report(lines)
        print(f"FAIL: {exc}; report={report}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
