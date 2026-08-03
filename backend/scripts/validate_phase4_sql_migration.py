#!/usr/bin/env python3
"""Validate Phase 4 migration 0082 apply / rollback / reapply on reachable SQL."""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

REPORT = _REPO_ROOT / "review" / "phase4-position-reconciliation-migration-report.txt"
REPORT3 = _REPO_ROOT / "review" / "phase3-position-label-detection-migration-report.txt"
UP = (
    _BACKEND_ROOT
    / "src"
    / "database"
    / "migrations"
    / "versions"
    / "0082_position_reconciliation.sql"
)
DOWN = (
    _BACKEND_ROOT
    / "src"
    / "database"
    / "migrations"
    / "versions"
    / "0082_position_reconciliation.down.sql"
)


def _clear_polluted_sql_env() -> None:
    for key in (
        "SQLSERVER_DATABASE",
        "SQLSERVER_SERVER",
        "SQLSERVER_UID",
        "SQLSERVER_PWD",
        "SQLSERVER_CONNECTION_STRING",
    ):
        os.environ.pop(key, None)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for path, override in (
        (_REPO_ROOT / ".env", False),
        (_BACKEND_ROOT / ".env", False),
    ):
        if path.is_file():
            load_dotenv(path, override=override)


def _split_batches(sql: str) -> list[str]:
    batches: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        if line.strip().upper() == "GO":
            batch = "\n".join(current).strip()
            if batch:
                batches.append(batch)
            current = []
        else:
            current.append(line)
    batch = "\n".join(current).strip()
    if batch:
        batches.append(batch)
    return batches


def _run_sql_file(conn, path: Path) -> None:
    cur = conn.cursor()
    for batch in _split_batches(path.read_text(encoding="utf-8")):
        cur.execute(batch)
    conn.commit()


def _oid(conn, table: str) -> int | None:
    cur = conn.cursor()
    cur.execute(f"SELECT OBJECT_ID(N'dbo.{table}', N'U')")
    val = cur.fetchone()[0]
    return int(val) if val is not None else None


def _ensure_schema_row(conn, *, version: str, migration_name: str, checksum: str) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM schema_migrations
        WHERE service_name = 'inventory-api' AND version = ?
        """,
        (version,),
    )
    if int(cur.fetchone()[0]) > 0:
        return
    cur.execute(
        """
        INSERT INTO schema_migrations (
            service_name, version, migration_name, checksum_sha256, applied_at
        ) VALUES ('inventory-api', ?, ?, ?, SYSUTCDATETIME())
        """,
        (version, migration_name, checksum),
    )
    conn.commit()


def _delete_schema_row(conn, version: str) -> None:
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM schema_migrations WHERE service_name = 'inventory-api' AND version = ?",
        (version,),
    )
    conn.commit()


def main() -> int:
    _clear_polluted_sql_env()
    _load_dotenv()
    lines = [f"generated_at={datetime.now(timezone.utc).isoformat()}"]
    ok = False
    try:
        import pyodbc

        from src.config import load_settings

        if not UP.is_file() or not DOWN.is_file():
            lines.append("status=FAIL")
            lines.append("reason=migration files missing")
            REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return 1

        cs = load_settings().require_sqlserver_connection_string()
        conn = pyodbc.connect(cs)
        cur = conn.cursor()
        cur.execute("SELECT DB_NAME()")
        lines.append(f"database={cur.fetchone()[0]}")
        lines.append(f"up={UP.name}")
        lines.append(f"down={DOWN.name}")

        # Phase 3 presence checks
        ipld = _oid(conn, "image_position_label_detections")
        lines.append(f"phase3_ipld_object_id={ipld}")
        cur.execute(
            """
            SELECT COUNT(*) FROM sys.indexes
            WHERE name = N'UQ_ipld_job_asset_detector_hash_status'
              AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
            """
        )
        idx = int(cur.fetchone()[0])
        lines.append(f"phase3_0081_unique_index={idx == 1}")
        phase3_ok = ipld is not None and idx == 1
        lines.append(f"phase3={'PASS' if phase3_ok else 'FAIL'}")

        before = _oid(conn, "position_reconciliations")
        lines.append(f"before_object_id={before}")
        if before is None:
            _run_sql_file(conn, UP)
            checksum = hashlib.sha256(UP.read_bytes()).hexdigest()
            _ensure_schema_row(
                conn,
                version="0082",
                migration_name="position_reconciliation",
                checksum=checksum,
            )
            before = _oid(conn, "position_reconciliations")
            lines.append(f"seeded_up_object_id={before}")

        _run_sql_file(conn, DOWN)
        _delete_schema_row(conn, "0082")
        mid = _oid(conn, "position_reconciliations")
        mid_asg = _oid(conn, "product_position_assignments")
        lines.append(f"after_down_reconciliations={mid}")
        lines.append(f"after_down_assignments={mid_asg}")
        if mid is not None or mid_asg is not None:
            lines.append("status=FAIL")
            lines.append("reason=tables remain after down")
            REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(REPORT.read_text(encoding="utf-8"))
            return 1

        _run_sql_file(conn, UP)
        checksum = hashlib.sha256(UP.read_bytes()).hexdigest()
        _ensure_schema_row(
            conn,
            version="0082",
            migration_name="position_reconciliation",
            checksum=checksum,
        )
        after = _oid(conn, "position_reconciliations")
        after_asg = _oid(conn, "product_position_assignments")
        lines.append(f"after_reapply_reconciliations={after}")
        lines.append(f"after_reapply_assignments={after_asg}")
        ok = phase3_ok and after is not None and after_asg is not None
        lines.append(f"phase4={'PASS' if ok else 'FAIL'}")
        lines.append(f"status={'PASS' if ok else 'FAIL'}")
        conn.close()
    except Exception as exc:  # noqa: BLE001
        lines.append("status=FAIL")
        lines.append(f"error={exc}")
        ok = False

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(lines) + "\n"
    REPORT.write_text(body, encoding="utf-8")
    REPORT3.write_text(body, encoding="utf-8")
    print(body)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
