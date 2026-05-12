"""Shared DELETE/count helpers for SQL Server domain tables (jobs, inventories, capture, labels).

Used by ``clean_local_business_data.py`` and pytest integration cleanup. Does not touch migrations or
structural catalog tables.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_INVENTORY_JOBS_DELETE_MAX_ITERATIONS = 1000


def inventory_jobs_delete_max_iterations() -> int:
    raw = (os.getenv("DINAMIC_INVENTORY_JOBS_DELETE_MAX_ITERATIONS") or "").strip()
    if raw:
        return max(1, int(raw))
    return DEFAULT_INVENTORY_JOBS_DELETE_MAX_ITERATIONS


# Ordered list for dry-run / reporting (counts).
TABLES_FOR_REPORT: tuple[tuple[str, str], ...] = (
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
    ("dbo", "source_assets"),
    ("dbo", "inventory_jobs"),
    ("dbo", "aisles"),
    ("dbo", "inventories"),
    ("dbo", "pallet_results"),
    ("dbo", "job_events"),
    ("dbo", "jobs"),
    ("dbo", "v3_jobs"),
)


def table_full_name(schema: str, table: str) -> str:
    return f"{schema}.{table}"


# Must read zero after a successful cleanup pass (business-domain tables only).
CRITICAL_ZERO_AFTER_CLEANUP: frozenset[str] = frozenset(
    table_full_name(s, t) for s, t in TABLES_FOR_REPORT
)


def count_if_exists(cur: Any, schema: str, table: str) -> int:
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


def collect_table_counts(cur: Any) -> dict[str, int]:
    """Non-negative counts keyed ``schema.table`` for tables in ``TABLES_FOR_REPORT``."""
    out: dict[str, int] = {}
    for schema, table in TABLES_FOR_REPORT:
        key = table_full_name(schema, table)
        out[key] = count_if_exists(cur, schema, table)
    return out


def exec_if_table(cur: Any, schema: str, table: str, sql_body: str) -> None:
    cur.execute(
        f"""
        IF OBJECT_ID(N'[{schema}].[{table}]', N'U') IS NOT NULL
        BEGIN
            {sql_body}
        END
        """
    )


def delete_inventory_jobs(cur: Any, *, max_iterations: int | None = None) -> None:
    """Delete ``inventory_jobs`` leaf-first for nullable self-FK ``retry_of_job_id``."""
    cap = max_iterations if max_iterations is not None else inventory_jobs_delete_max_iterations()
    exhausted_without_finish = False
    for _ in range(cap):
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
    else:
        exhausted_without_finish = True

    remaining = count_if_exists(cur, "dbo", "inventory_jobs")
    if remaining > 0:
        raise RuntimeError(
            f"Could not fully delete dbo.inventory_jobs; remaining={remaining}. "
            "Possible self-FK cycle, orphaned retry references, or an external FK not cleared."
            + (" Maximum iteration budget exhausted." if exhausted_without_finish else "")
        )


def run_delete_pipeline(cur: Any) -> None:
    exec_if_table(
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
        "source_assets",
    ):
        exec_if_table(cur, "dbo", tbl, f"DELETE FROM dbo.[{tbl}];")

    exec_if_table(
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
        delete_inventory_jobs(cur)

    for tbl in ("aisles", "inventories"):
        exec_if_table(cur, "dbo", tbl, f"DELETE FROM dbo.[{tbl}];")

    for tbl in ("pallet_results", "job_events"):
        exec_if_table(cur, "dbo", tbl, f"DELETE FROM dbo.[{tbl}];")

    exec_if_table(cur, "dbo", "jobs", "DELETE FROM dbo.jobs;")
    exec_if_table(cur, "dbo", "v3_jobs", "DELETE FROM dbo.v3_jobs;")


def validate_critical_tables_empty(cur: Any) -> dict[str, int]:
    """Re-count tables and raise ``RuntimeError`` if any critical business table still has rows."""
    counts = collect_table_counts(cur)
    bad = {k: v for k, v in counts.items() if k in CRITICAL_ZERO_AFTER_CLEANUP and v > 0}
    if bad:
        inv_jobs = bad.get("dbo.inventory_jobs")
        hint = ""
        if inv_jobs:
            hint = (
                " dbo.inventory_jobs may indicate self-FK cycles or FK from tables outside "
                "this cleanup scope."
            )
        raise RuntimeError(
            "Cleanup verification failed: non-empty business tables after delete pass — "
            f"{bad}.{hint}"
        )
    return counts


def summarize_totals(counts: dict[str, int]) -> int:
    return sum(counts.values())
