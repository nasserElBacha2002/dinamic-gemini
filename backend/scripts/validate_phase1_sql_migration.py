#!/usr/bin/env python3
"""Validate Phase 1 positioning SQL migrations (0074 / 0075 / optional 0076) safely.

Documents and runs against a **test** database:
  apply → validate objects → rollback (DOWN) → delete schema_migrations rows → reapply.

Behavior:
  - Prefers ``backend/.env.test`` / repo ``.env.test`` when present
    (typically ``SQLSERVER_DATABASE=dinamic_inventory_test``).
  - If SQL Server is not configured, exit 0 with SKIP and write the report.
  - Refuses production-ish DB names unless ``PHASE1_SQL_VALIDATE_ALLOW_NON_TEST=1``.
  - On DOWN, deletes ``schema_migrations`` rows for versions 0074/0075/(0076) so a later
    ``apply_pending`` can re-record them (DOWN scripts themselves do not touch that table).

Usage (from repo root or backend/):
  python backend/scripts/validate_phase1_sql_migration.py

Report: ``review/phase1-unblock-migration-report.txt``
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
_UP_0076 = _VERSIONS / "0076_ordered_capture_processing_job_link.sql"
_DOWN_0076 = _VERSIONS / "0076_ordered_capture_processing_job_link.down.sql"

_REPORT = _REPO_ROOT / "review" / "phase1-unblock-migration-report.txt"

_PHASE1_VERSIONS = ("0074", "0075", "0076")

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
    ) THEN 1 ELSE 0 END AS has_label_idempotency_uq,
    CASE WHEN EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'UQ_inventory_jobs_ordered_session_version'
          AND object_id = OBJECT_ID(N'dbo.inventory_jobs')
    ) THEN 1 ELSE 0 END AS has_jobs_session_version_uq,
    CASE WHEN EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'UQ_source_assets_ordered_session_client_file'
          AND object_id = OBJECT_ID(N'dbo.source_assets')
    ) THEN 1 ELSE 0 END AS has_assets_client_file_uq,
    CASE WHEN COL_LENGTH(N'dbo.ordered_capture_sessions', N'processing_job_id') IS NOT NULL
         THEN 1 ELSE 0 END AS has_processing_job_id,
    CASE WHEN EXISTS (
        SELECT 1 FROM sys.foreign_keys
        WHERE name = N'FK_ordered_capture_sessions_processing_job'
    ) THEN 1 ELSE 0 END AS has_processing_job_fk,
    CASE WHEN EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'IX_ordered_capture_sessions_processing_job'
          AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
    ) THEN 1 ELSE 0 END AS has_processing_job_ix
"""


def _load_dotenv_layers() -> list[str]:
    loaded: list[str] = []
    try:
        from dotenv import load_dotenv
    except ImportError:
        return loaded
    for path, override in (
        (_REPO_ROOT / ".env", False),
        (_BACKEND_ROOT / ".env", False),
        (_REPO_ROOT / ".env.test", True),
        (_BACKEND_ROOT / ".env.test", True),
    ):
        if path.is_file():
            load_dotenv(path, override=override)
            loaded.append(f"{path} (override={override})")
    return loaded


def _sqlserver_env_present() -> bool:
    if (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip():
        return True
    keys = ("SQLSERVER_SERVER", "SQLSERVER_DATABASE", "SQLSERVER_UID", "SQLSERVER_PWD")
    return all((os.getenv(k) or "").strip() for k in keys)


def _write_report(lines: list[str]) -> Path:
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = "\n".join([f"# Phase 1 unblock — migration validation — {stamp}", *lines, ""])
    _REPORT.write_text(body, encoding="utf-8")
    return _REPORT


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


def _assert_phase1_present(flags: dict[str, int], *, require_0076: bool) -> None:
    required_one = {
        "has_ordered_capture_sessions",
        "has_aisle_locations",
        "has_aisle_location_labels",
        "has_label_idempotency_key",
        "has_one_open_uq",
        "has_label_idempotency_uq",
        "has_jobs_session_version_uq",
        "has_assets_client_file_uq",
    }
    if require_0076:
        required_one |= {
            "has_processing_job_id",
            "has_processing_job_fk",
            "has_processing_job_ix",
        }
    missing = [k for k in required_one if flags.get(k, 0) != 1]
    if missing:
        raise RuntimeError(f"Phase 1 objects missing after apply: {missing}")
    if flags.get("has_open_aisle_key_obsolete", 0) != 0:
        raise RuntimeError(
            "obsolete column open_aisle_key still present after 0075 "
            "(filtered indexes cannot reference computed columns)"
        )


def _service_name() -> str:
    return (os.getenv("DB_SCHEMA_SERVICE_NAME") or "inventory-api").strip() or "inventory-api"


def _delete_schema_migration_rows(client, versions: list[str], lines: list[str]) -> None:
    """DOWN scripts do not touch schema_migrations; clear rows so reapply can be recorded later."""
    if not versions:
        return
    service = _service_name()
    with client.cursor() as cur:
        # Table may not exist on a brand-new empty DB before any migrate run.
        cur.execute(
            """
            SELECT CASE WHEN OBJECT_ID(N'dbo.schema_migrations', N'U') IS NOT NULL
                        THEN 1 ELSE 0 END
            """
        )
        if int(cur.fetchone()[0]) != 1:
            lines.append("schema_migrations: table absent (skip delete)")
            return
        for ver in versions:
            cur.execute(
                """
                DELETE FROM schema_migrations
                WHERE service_name = ? AND version = ?
                """,
                (service, ver),
            )
            lines.append(
                f"schema_migrations: deleted service={service!r} version={ver!r} "
                f"rowcount={cur.rowcount}"
            )


def _phase1_up_down_pairs() -> list[tuple[str, Path, Path | None]]:
    """Return (version, up_path, down_path_or_None) for present Phase 1 migrations."""
    pairs: list[tuple[str, Path, Path | None]] = [
        ("0074", _UP_0074, _DOWN_0074),
        ("0075", _UP_0075, _DOWN_0075),
    ]
    if _UP_0076.is_file():
        down = _DOWN_0076 if _DOWN_0076.is_file() else None
        pairs.append(("0076", _UP_0076, down))
    return pairs


def main() -> int:
    lines: list[str] = []
    loaded = _load_dotenv_layers()
    lines.append(f"dotenv_loaded={loaded or ['(none)']}")

    pairs = _phase1_up_down_pairs()
    for ver, up, down in pairs:
        lines.append(f"artifact UP {ver}: {'OK' if up.is_file() else 'MISSING'} ({up})")
        if down is not None:
            lines.append(f"artifact DOWN {ver}: {'OK' if down.is_file() else 'MISSING'} ({down})")
        else:
            lines.append(f"artifact DOWN {ver}: none (0076 follow-up without .down.sql)")

    required_present = all(p.is_file() for p in (_UP_0074, _DOWN_0074, _UP_0075, _DOWN_0075))
    if not required_present:
        report = _write_report([*lines, "result: FAIL (missing SQL artifacts for 0074/0075)"])
        print(f"FAIL: missing Phase 1 SQL artifacts; report={report}")
        return 1

    if not _sqlserver_env_present():
        lines.extend(
            [
                "sqlserver: not configured",
                "result: SKIP",
                "note: set SQLSERVER_* via backend/.env.test "
                "(SQLSERVER_DATABASE=dinamic_inventory_test) to run apply-validate-rollback-reapply",
            ]
        )
        report = _write_report(lines)
        print(f"SKIP: SQL Server not configured; report={report}")
        return 0

    from src.env_settings.sqlserver_resolution import (
        resolve_sqlserver_connection_config,
        resolved_sqlserver_database_name_from_env,
    )

    db_name = (resolved_sqlserver_database_name_from_env() or os.getenv("SQLSERVER_DATABASE") or "").strip()
    lines.append(f"database={db_name}")
    allow_prod = (os.getenv("PHASE1_SQL_VALIDATE_ALLOW_NON_TEST") or "").strip() == "1"
    low = db_name.lower()
    if not allow_prod and db_name and "test" not in low and "dev" not in low:
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

        conn_str = resolve_sqlserver_connection_config().connection_string
        client = SqlServerClient(conn_str)

        # Apply ascending: 0074 → 0075 → (0076)
        for ver, up, _down in pairs:
            lines.append(f"step: apply {ver} ({up.name})")
            _execute_sql_file(client, up)

        require_0076 = any(ver == "0076" for ver, _u, _d in pairs)
        flags = _validate_objects(client)
        lines.append(f"validate after apply: {flags}")
        _assert_phase1_present(flags, require_0076=require_0076)

        # Rollback descending: (0076) → 0075 → 0074
        for ver, _up, down in reversed(pairs):
            if down is None:
                lines.append(f"step: skip rollback {ver} (no .down.sql)")
                continue
            lines.append(f"step: rollback {ver} ({down.name})")
            _execute_sql_file(client, down)

        versions_touched = [ver for ver, _u, _d in pairs]
        lines.append(
            "note: DOWN SQL does not delete schema_migrations rows; "
            "script deletes them explicitly so apply_pending can re-record"
        )
        _delete_schema_migration_rows(client, versions_touched, lines)

        # Reapply ascending
        for ver, up, _down in pairs:
            lines.append(f"step: reapply {ver} ({up.name})")
            _execute_sql_file(client, up)

        flags2 = _validate_objects(client)
        lines.append(f"validate after reapply: {flags2}")
        _assert_phase1_present(flags2, require_0076=require_0076)

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
