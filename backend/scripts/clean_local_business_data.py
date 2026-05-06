#!/usr/bin/env python3
"""Delete domain/business rows from the configured SQL Server database (local dev cleanup).

Does not drop tables or modify ``schema_migrations``. Uses the same env resolution as the app
(``SQLSERVER_CONNECTION_STRING`` or split ``SQLSERVER_*`` variables).

Default mode is dry-run (row counts per table). ``--confirm`` performs deletes inside one transaction.

Safety for ``--confirm``:

- ``DINAMIC_CONFIRM_LOCAL_BUSINESS_DATA_DELETION=1`` must be set.
- ``SERVER=`` must target loopback unless ``DINAMIC_ALLOW_REMOTE_BUSINESS_DATA_CLEANUP=1``.

Usage::

    python scripts/clean_local_business_data.py
    python scripts/clean_local_business_data.py --confirm
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent

if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _load_dotenv_layers() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_REPO_ROOT / ".env", override=False)
    load_dotenv(_BACKEND_ROOT / ".env", override=False)


def _count_if_exists(cur, schema: str, table: str) -> int:
    cur.execute(
        """
        SELECT COUNT_BIG(*)
        FROM sys.tables t
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE s.name = ? AND t.name = ?
        """,
        (schema, table),
    )
    row = cur.fetchone()
    if not row or int(row[0]) == 0:
        return 0
    cur.execute(f"SELECT COUNT_BIG(*) FROM [{schema}].[{table}]")
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


_TABLES_FOR_REPORT: tuple[tuple[str, str], ...] = (
    ("dbo", "capture_session_confirmations"),
    ("dbo", "capture_session_items"),
    ("dbo", "capture_session_groups"),
    ("dbo", "capture_sessions"),
    ("dbo", "review_actions"),
    ("dbo", "product_records"),
    ("dbo", "evidences"),
    ("dbo", "positions"),
    ("dbo", "final_count_records"),
    ("dbo", "raw_labels"),
    ("dbo", "normalized_labels"),
    ("dbo", "inventory_visual_references"),
    ("dbo", "source_assets"),
    ("dbo", "inventory_jobs"),
    ("dbo", "aisles"),
    ("dbo", "inventories"),
    ("dbo", "pallet_results"),
    ("dbo", "job_events"),
    ("dbo", "jobs"),
    ("dbo", "v3_jobs"),
)


def _delete_inventory_jobs(cur) -> None:
    """Delete inventory_jobs respecting nullable self-FK retry_of_job_id (referrer rows first)."""
    while True:
        cur.execute(
            """
            DELETE FROM dbo.inventory_jobs
            WHERE NOT EXISTS (
                SELECT 1
                FROM dbo.inventory_jobs AS child
                WHERE child.retry_of_job_id = dbo.inventory_jobs.id
            )
            """
        )
        if cur.rowcount == 0:
            break


def _exec_if_table(cur, schema: str, table: str, sql_body: str) -> None:
    cur.execute(
        f"""
        IF OBJECT_ID(N'[{schema}].[{table}]', N'U') IS NOT NULL
        BEGIN
            {sql_body}
        END
        """
    )


def _run_delete_pipeline(cur) -> None:
    _exec_if_table(
        cur,
        "dbo",
        "source_assets",
        "UPDATE dbo.source_assets SET capture_session_item_id = NULL WHERE capture_session_item_id IS NOT NULL;",
    )
    for tbl in (
        "capture_session_confirmations",
        "capture_session_items",
        "capture_session_groups",
        "capture_sessions",
        "review_actions",
        "product_records",
        "evidences",
        "positions",
        "final_count_records",
        "raw_labels",
        "normalized_labels",
        "inventory_visual_references",
        "source_assets",
    ):
        _exec_if_table(cur, "dbo", tbl, f"DELETE FROM dbo.[{tbl}];")

    _exec_if_table(
        cur,
        "dbo",
        "aisles",
        "UPDATE dbo.aisles SET operational_job_id = NULL WHERE operational_job_id IS NOT NULL;",
    )

    cur.execute(
        """
        SELECT 1
        FROM sys.tables AS t
        INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
        WHERE s.name = N'dbo' AND t.name = N'inventory_jobs'
        """
    )
    if cur.fetchone():
        _delete_inventory_jobs(cur)

    for tbl in ("aisles", "inventories"):
        _exec_if_table(cur, "dbo", tbl, f"DELETE FROM dbo.[{tbl}];")

    for tbl in ("pallet_results", "job_events"):
        _exec_if_table(cur, "dbo", tbl, f"DELETE FROM dbo.[{tbl}];")

    _exec_if_table(cur, "dbo", "jobs", "DELETE FROM dbo.jobs;")
    _exec_if_table(cur, "dbo", "v3_jobs", "DELETE FROM dbo.v3_jobs;")


def _assert_safe_to_mutate(connection_string: str) -> None:
    from src.env_settings.sqlserver_resolution import (
        resolved_sqlserver_database_name_from_env,
        sqlserver_odbc_server_targets_loopback,
    )

    if (os.getenv("DINAMIC_ALLOW_REMOTE_BUSINESS_DATA_CLEANUP") or "").strip() == "1":
        return
    if sqlserver_odbc_server_targets_loopback(connection_string):
        return
    db = resolved_sqlserver_database_name_from_env()
    raise SystemExit(
        "Refusing destructive cleanup: SQL Server SERVER= does not look like loopback. "
        "Point at localhost for development or set DINAMIC_ALLOW_REMOTE_BUSINESS_DATA_CLEANUP=1 "
        f"(database={db!r})."
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _load_dotenv_layers()

    parser = argparse.ArgumentParser(description="Clean business data from local SQL Server (dry-run by default).")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete rows (requires DINAMIC_CONFIRM_LOCAL_BUSINESS_DATA_DELETION=1).",
    )
    args = parser.parse_args()

    from src.database.sqlserver import SqlServerClient
    from src.env_settings.sqlserver_resolution import (
        resolve_sqlserver_connection_config,
        resolved_sqlserver_database_name_from_env,
        sqlserver_configuration_error_message,
    )

    res = resolve_sqlserver_connection_config()
    if not res.connection_string.strip():
        msg = sqlserver_configuration_error_message(res)
        logging.error("SQL Server not configured: %s", msg)
        return 1

    cs = res.connection_string.strip()
    db_name = resolved_sqlserver_database_name_from_env()
    logging.info("Resolved database name (for logs): %s", db_name or "(unknown)")

    client = SqlServerClient(cs)

    if args.confirm:
        if (os.getenv("DINAMIC_CONFIRM_LOCAL_BUSINESS_DATA_DELETION") or "").strip() != "1":
            logging.error(
                "Refusing --confirm: set DINAMIC_CONFIRM_LOCAL_BUSINESS_DATA_DELETION=1 in the environment."
            )
            return 2
        _assert_safe_to_mutate(cs)

    # Dry-run: counts only
    if not args.confirm:
        logging.info("Dry-run mode (default): printing row counts. Use --confirm to delete.")
        with client.cursor() as cur:
            total = 0
            for schema, table in _TABLES_FOR_REPORT:
                n = _count_if_exists(cur, schema, table)
                total += n
                logging.info("%s.%s: %s rows", schema, table, n)
            logging.info("TOTAL (sum of listed tables): %s rows", total)
        return 0

    logging.warning("Deleting business data in one transaction…")
    try:
        import pyodbc

        conn = pyodbc.connect(cs, autocommit=False)
        cur = conn.cursor()
        try:
            _run_delete_pipeline(cur)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as exc:
        logging.exception("Cleanup failed: %s", exc)
        return 3

    logging.info("Cleanup committed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
