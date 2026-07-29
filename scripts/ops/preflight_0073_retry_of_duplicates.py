"""Preflight for migration 0073 — list duplicate retry_of_job_id groups.

Usage:
  python -m scripts.ops.preflight_0073_retry_of_duplicates
  python -m scripts.ops.preflight_0073_retry_of_duplicates --json

Exits 0 when no duplicates exist; non-zero when duplicates block index creation.
Does NOT auto-resolve duplicates.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_DUPLICATE_PARENTS_SQL = """
SELECT retry_of_job_id, COUNT(*) AS child_count
FROM dbo.inventory_jobs
WHERE retry_of_job_id IS NOT NULL
GROUP BY retry_of_job_id
HAVING COUNT(*) > 1
ORDER BY retry_of_job_id
"""

_CHILDREN_FOR_PARENT_SQL = """
SELECT id, status, created_at
FROM dbo.inventory_jobs
WHERE retry_of_job_id = ?
ORDER BY created_at, id
"""


@dataclass(frozen=True)
class RetryChildRow:
    id: str
    status: str
    created_at: str | None


@dataclass(frozen=True)
class DuplicateRetryGroup:
    retry_of_job_id: str
    child_count: int
    children: tuple[RetryChildRow, ...]


def _row_value(row: Any, name: str, index: int) -> Any:
    value = getattr(row, name, None)
    if value is None:
        try:
            value = row[index]
        except Exception:
            value = None
    return value


def _normalize_created_at(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def fetch_duplicate_retry_groups(cursor: Any) -> list[DuplicateRetryGroup]:
    """Return duplicate retry_of_job_id groups with child detail."""
    cursor.execute(_DUPLICATE_PARENTS_SQL)
    parent_rows = cursor.fetchall()
    groups: list[DuplicateRetryGroup] = []
    for parent_row in parent_rows:
        parent_id = str(_row_value(parent_row, "retry_of_job_id", 0) or "")
        child_count = int(_row_value(parent_row, "child_count", 1) or 0)
        cursor.execute(_CHILDREN_FOR_PARENT_SQL, (parent_id,))
        children: list[RetryChildRow] = []
        for child_row in cursor.fetchall():
            children.append(
                RetryChildRow(
                    id=str(_row_value(child_row, "id", 0) or ""),
                    status=str(_row_value(child_row, "status", 1) or ""),
                    created_at=_normalize_created_at(_row_value(child_row, "created_at", 2)),
                )
            )
        groups.append(
            DuplicateRetryGroup(
                retry_of_job_id=parent_id,
                child_count=child_count,
                children=tuple(children),
            )
        )
    return groups


def format_groups_text(groups: Sequence[DuplicateRetryGroup]) -> str:
    if not groups:
        return "No duplicate retry_of_job_id groups found."
    lines = [
        f"Found {len(groups)} duplicate retry_of_job_id group(s):",
        "",
    ]
    for group in groups:
        child_ids = [c.id for c in group.children]
        lines.append(
            f"- retry_of_job_id={group.retry_of_job_id} child_count={group.child_count} "
            f"child_ids={child_ids}"
        )
        for child in group.children:
            lines.append(
                f"    id={child.id} status={child.status} created_at={child.created_at}"
            )
        lines.append("")
    lines.append("Resolve duplicates manually before applying migration 0073.")
    lines.append("See backend/src/database/migrations/versions/0073_README.md")
    return "\n".join(lines)


def groups_to_json(groups: Sequence[DuplicateRetryGroup]) -> dict[str, Any]:
    return {
        "duplicate_group_count": len(groups),
        "groups": [
            {
                "retry_of_job_id": g.retry_of_job_id,
                "child_count": g.child_count,
                "child_ids": [c.id for c in g.children],
                "children": [asdict(c) for c in g.children],
            }
            for g in groups
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preflight migration 0073 — duplicate retry_of_job_id groups"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON findings")
    args = parser.parse_args(argv)

    from src.config import load_settings
    from src.database.sqlserver import SqlServerClient

    settings = load_settings()
    connection_string = settings.sqlserver_connection_string
    if not connection_string:
        print("ERROR: SQL Server not configured (SQLSERVER_CONNECTION_STRING)", file=sys.stderr)
        return 2

    client = SqlServerClient(connection_string)
    try:
        with client.cursor() as cur:
            groups = fetch_duplicate_retry_groups(cur)
    except Exception as exc:
        print(f"ERROR: preflight query failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(groups_to_json(groups), indent=2))
    else:
        print(format_groups_text(groups))

    return 1 if groups else 0


if __name__ == "__main__":
    raise SystemExit(main())
