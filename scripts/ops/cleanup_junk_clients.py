#!/usr/bin/env python3
"""Delete junk clients from the developer local SQL DB; keep named originals.

Usage (repo root, uses developer ``.env`` — not ``.env.test``):

  backend/.venv/bin/python scripts/ops/cleanup_junk_clients.py --confirm

Default is dry-run. Keeps clients whose name matches (case-insensitive):
blestein, masol, rabbione.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from dotenv import load_dotenv

KEEP_NAMES = frozenset({"blestein", "masol", "rabbione"})
_BATCH = 400


def _load_developer_env(repo: Path) -> None:
    # Do not load .env.test — this script targets the local developer database.
    load_dotenv(repo / ".env", override=True)
    load_dotenv(repo / "backend" / ".env", override=True)
    os.environ.pop("DINAMIC_PYTEST_DOTENV_LOCKED", None)


def _connect():
    import pyodbc

    from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config

    cs = resolve_sqlserver_connection_config().connection_string.strip()
    if not cs:
        raise SystemExit("SQL Server is not configured in .env")
    return pyodbc.connect(cs, autocommit=False)


def _table_exists(cur, name: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM sys.tables t
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE s.name = N'dbo' AND t.name = ?
        """,
        (name,),
    )
    return cur.fetchone() is not None


def _chunks(values: Sequence[str], size: int = _BATCH) -> Iterable[Sequence[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _in_delete(cur, sql_prefix: str, ids: Sequence[str], sql_suffix: str = "") -> None:
    if not ids:
        return
    for batch in _chunks(ids):
        placeholders = ",".join("?" for _ in batch)
        cur.execute(f"{sql_prefix} ({placeholders}){sql_suffix}", list(batch))


def _in_select(cur, sql_prefix: str, ids: Sequence[str], sql_suffix: str = "") -> list[str]:
    out: list[str] = []
    if not ids:
        return out
    for batch in _chunks(ids):
        placeholders = ",".join("?" for _ in batch)
        cur.execute(f"{sql_prefix} ({placeholders}){sql_suffix}", list(batch))
        out.extend(str(r[0]) for r in cur.fetchall())
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete; without this flag only prints the plan.",
    )
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / "backend"))
    _load_developer_env(repo)

    from src.env_settings.sqlserver_resolution import resolved_sqlserver_database_name_from_env

    db = resolved_sqlserver_database_name_from_env()
    if db and "test" in db.lower():
        raise SystemExit(
            f"Refusing to run against a test-looking database ({db!r}). "
            "Unset test env / use developer .env pointing at your local DB."
        )

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM dbo.clients")
        rows = [(str(r[0]), str(r[1])) for r in cur.fetchall()]
        keep = [(i, n) for i, n in rows if n.strip().casefold() in KEEP_NAMES]
        drop = [(i, n) for i, n in rows if n.strip().casefold() not in KEEP_NAMES]
        print(f"database={db!r} clients_total={len(rows)} keep={len(keep)} drop={len(drop)}")
        for i, n in keep:
            print(f"  KEEP  {n!r} ({i})")
        for i, n in drop[:30]:
            print(f"  DROP  {n!r} ({i})")
        if len(drop) > 30:
            print(f"  ... and {len(drop) - 30} more")

        if not args.confirm:
            print("Dry-run only. Re-run with --confirm to delete.")
            return 0

        if not drop:
            print("Nothing to delete.")
            return 0

        drop_ids = [i for i, _ in drop]

        inv_ids: list[str] = []
        if _table_exists(cur, "inventories"):
            inv_ids = _in_select(
                cur,
                "SELECT id FROM dbo.inventories WHERE client_id IN",
                drop_ids,
            )

        if inv_ids:
            aisle_ids: list[str] = []
            if _table_exists(cur, "aisles"):
                aisle_ids = _in_select(
                    cur,
                    "SELECT id FROM dbo.aisles WHERE inventory_id IN",
                    inv_ids,
                )

            if aisle_ids:
                for tbl, col in (
                    ("positions", "aisle_id"),
                    ("product_records", "aisle_id"),
                    ("evidences", "aisle_id"),
                    ("source_assets", "aisle_id"),
                ):
                    if _table_exists(cur, tbl):
                        _in_delete(
                            cur,
                            f"DELETE FROM dbo.[{tbl}] WHERE [{col}] IN",
                            aisle_ids,
                        )
                if _table_exists(cur, "inventory_jobs"):
                    _in_delete(
                        cur,
                        "DELETE FROM dbo.inventory_jobs WHERE target_type = 'aisle' "
                        "AND target_id IN",
                        aisle_ids,
                    )
                if _table_exists(cur, "aisles"):
                    _in_delete(
                        cur,
                        "UPDATE dbo.aisles SET operational_job_id = NULL WHERE id IN",
                        aisle_ids,
                    )
                    _in_delete(cur, "DELETE FROM dbo.aisles WHERE id IN", aisle_ids)

            _in_delete(cur, "DELETE FROM dbo.inventories WHERE id IN", inv_ids)
            print(f"Deleted {len(inv_ids)} inventories for junk clients.")

        supplier_ids: list[str] = []
        if _table_exists(cur, "client_suppliers"):
            supplier_ids = _in_select(
                cur,
                "SELECT id FROM dbo.client_suppliers WHERE client_id IN",
                drop_ids,
            )

        if supplier_ids:
            image_ids: list[str] = []
            if _table_exists(cur, "supplier_reference_images"):
                image_ids = _in_select(
                    cur,
                    "SELECT id FROM dbo.supplier_reference_images "
                    "WHERE client_supplier_id IN",
                    supplier_ids,
                )
            if image_ids and _table_exists(cur, "supplier_reference_annotations"):
                _in_delete(
                    cur,
                    "DELETE FROM dbo.supplier_reference_annotations "
                    "WHERE template_image_id IN",
                    image_ids,
                )
            if _table_exists(cur, "supplier_reference_images"):
                _in_delete(
                    cur,
                    "DELETE FROM dbo.supplier_reference_images "
                    "WHERE client_supplier_id IN",
                    supplier_ids,
                )
            if _table_exists(cur, "supplier_prompt_configs"):
                _in_delete(
                    cur,
                    "DELETE FROM dbo.supplier_prompt_configs "
                    "WHERE client_supplier_id IN",
                    supplier_ids,
                )
            if _table_exists(cur, "supplier_extraction_profiles"):
                _in_delete(
                    cur,
                    "DELETE FROM dbo.supplier_extraction_profiles WHERE client_id IN",
                    drop_ids,
                )
                _in_delete(
                    cur,
                    "DELETE FROM dbo.supplier_extraction_profiles WHERE supplier_id IN",
                    supplier_ids,
                )
            _in_delete(cur, "DELETE FROM dbo.client_suppliers WHERE id IN", supplier_ids)
        elif _table_exists(cur, "supplier_extraction_profiles"):
            _in_delete(
                cur,
                "DELETE FROM dbo.supplier_extraction_profiles WHERE client_id IN",
                drop_ids,
            )

        _in_delete(cur, "DELETE FROM dbo.clients WHERE id IN", drop_ids)
        conn.commit()
        print(f"Deleted {len(drop_ids)} junk clients.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
