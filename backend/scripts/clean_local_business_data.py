#!/usr/bin/env python3
"""Delete domain/business rows from the configured SQL Server database (local dev cleanup).

Does not drop tables or modify ``schema_migrations``. Uses the same env resolution as the app
(``SQLSERVER_CONNECTION_STRING`` or split ``SQLSERVER_*`` variables).

Default mode is dry-run (row counts per table). ``--confirm`` performs deletes inside one transaction.

Loads ``.env`` from repo root and ``backend/.env`` only — **not** ``.env.test`` (that file is for
pytest). Use ``--use-env-test`` only if you intentionally want the same DB variables as tests.

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


def _load_dotenv_layers(*, use_env_test: bool = False) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_REPO_ROOT / ".env", override=False)
    load_dotenv(_BACKEND_ROOT / ".env", override=False)
    if use_env_test:
        load_dotenv(_REPO_ROOT / ".env.test", override=True)
        load_dotenv(_BACKEND_ROOT / ".env.test", override=True)


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

    parser = argparse.ArgumentParser(description="Clean business data from local SQL Server (dry-run by default).")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete rows (requires DINAMIC_CONFIRM_LOCAL_BUSINESS_DATA_DELETION=1).",
    )
    parser.add_argument(
        "--use-env-test",
        action="store_true",
        help="After loading .env files, also load .env.test with override (same as pytest).",
    )
    args = parser.parse_args()

    _load_dotenv_layers(use_env_test=args.use_env_test)

    from src.database.sqlserver import SqlServerClient
    from src.database.sqlserver_business_data_cleanup import (
        collect_table_counts,
        run_delete_pipeline,
        summarize_totals,
        validate_critical_tables_empty,
    )
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
            before = collect_table_counts(cur)
            total = summarize_totals(before)
            for key in sorted(before.keys()):
                logging.info("%s: %s rows", key, before[key])
            logging.info("TOTAL (sum of listed tables): %s rows", total)
        return 0

    logging.warning("Deleting business data in one transaction…")
    try:
        import pyodbc

        conn = pyodbc.connect(cs, autocommit=False)
        cur = conn.cursor()
        try:
            before = collect_table_counts(cur)
            before_total = summarize_totals(before)
            run_delete_pipeline(cur)
            after = collect_table_counts(cur)
            after_total = summarize_totals(after)
            validate_critical_tables_empty(cur)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        approx_removed = before_total - after_total
        logging.info(
            "Summary: rows_before=%s rows_after=%s approx_removed=%s",
            before_total,
            after_total,
            approx_removed,
        )

    except RuntimeError as exc:
        logging.error("Cleanup verification failed: %s", exc)
        return 4
    except Exception as exc:
        logging.exception("Cleanup failed: %s", exc)
        return 3

    logging.info("Cleanup committed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
