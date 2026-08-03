#!/usr/bin/env python3
"""Phase 4 SQL concurrency harness — one active reconciliation per job.

Writes ``review/phase4-position-reconciliation-sql-concurrency-report.txt``.
"""

from __future__ import annotations

import os
import sys
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

REPORT = _REPO_ROOT / "review" / "phase4-position-reconciliation-sql-concurrency-report.txt"
_PREFIX = "p4conc"


def _clear_polluted() -> None:
    for key in (
        "SQLSERVER_DATABASE",
        "SQLSERVER_SERVER",
        "SQLSERVER_UID",
        "SQLSERVER_PWD",
        "SQLSERVER_CONNECTION_STRING",
    ):
        os.environ.pop(key, None)


def _load_dotenv() -> list[str]:
    loaded: list[str] = []
    try:
        from dotenv import load_dotenv
    except ImportError:
        return loaded
    for path, override in (
        (_REPO_ROOT / ".env", False),
        (_BACKEND_ROOT / ".env", False),
    ):
        if path.is_file():
            load_dotenv(path, override=override)
            loaded.append(str(path))
    return loaded


@dataclass
class ScenarioResult:
    name: str
    ok: bool
    detail: str = ""
    error: str = ""


@dataclass
class HarnessReport:
    status: str = "NOT_RUN"
    results: list[ScenarioResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def write(self) -> None:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"status={self.status}",
            f"generated_at={datetime.now(timezone.utc).isoformat()}",
            "",
        ]
        for r in self.results:
            lines.append(f"[{'PASS' if r.ok else 'FAIL'}] {r.name}: {r.detail or r.error}")
        if self.notes:
            lines.append("")
            lines.extend(self.notes)
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(REPORT.read_text(encoding="utf-8"))


def _connect():
    import pyodbc

    from src.config import load_settings

    conn = pyodbc.connect(load_settings().require_sqlserver_connection_string())
    conn.autocommit = False
    return conn


def _run_parallel(fn_a: Callable[[], Any], fn_b: Callable[[], Any]) -> tuple[Any, Any, list[str]]:
    errors: list[str] = []
    out: dict[str, Any] = {}

    def wrap(key: str, fn: Callable[[], Any]) -> None:
        try:
            out[key] = fn()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {exc}\n{traceback.format_exc()}")

    t1 = threading.Thread(target=wrap, args=("a", fn_a))
    t2 = threading.Thread(target=wrap, args=("b", fn_b))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    return out.get("a"), out.get("b"), errors


def _seed(tag: str) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    ids = {
        "client_id": f"{_PREFIX}-c-{tag}",
        "inventory_id": f"{_PREFIX}-i-{tag}",
        "aisle_id": f"{_PREFIX}-a-{tag}",
        "job_id": f"{_PREFIX}-j-{tag}",
    }
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clients (id, name, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
            (ids["client_id"], f"P4 {tag}", now, now),
        )
        cur.execute(
            """
            INSERT INTO inventories (id, name, status, created_at, updated_at, processing_mode, client_id)
            VALUES (?, ?, 'draft', ?, ?, 'test', ?)
            """,
            (ids["inventory_id"], f"P4 Inv {tag}", now, now, ids["client_id"]),
        )
        cur.execute(
            """
            INSERT INTO aisles (id, inventory_id, code, status, created_at, updated_at, is_active)
            VALUES (?, ?, ?, 'created', ?, ?, 1)
            """,
            (ids["aisle_id"], ids["inventory_id"], f"P{tag[:6]}", now, now),
        )
        cur.execute(
            """
            INSERT INTO inventory_jobs (
                id, target_type, target_id, job_type, status,
                payload_json, created_at, updated_at, attempt_count,
                identification_mode, identification_mode_source,
                configuration_snapshot_version, execution_strategy
            ) VALUES (
                ?, 'aisle', ?, 'process_aisle', 'completed', ?, ?, ?, 1,
                'LEGACY_LLM', 'LEGACY_MIGRATION', 1, 'LEGACY_LLM'
            )
            """,
            (ids["job_id"], ids["aisle_id"], "{}", now, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return ids


def scenario_one_active_revision() -> ScenarioResult:
    name = "two_workers_one_active_reconciliation"
    tag = uuid.uuid4().hex[:10]
    try:
        ids = _seed(tag)
    except Exception as exc:  # noqa: BLE001
        return ScenarioResult(name=name, ok=False, error=f"seed_failed={exc}")

    now = datetime.now(timezone.utc)

    def persist_one(marker: str) -> str:
        from src.config import load_settings
        from src.database.sqlserver import SqlServerClient
        from src.domain.position_reconciliation.entities import (
            RECONCILIATION_NAME,
            RECONCILIATION_VERSION,
            PositionReconciliation,
            ReconciliationStatus,
        )
        from src.infrastructure.repositories.sql_position_reconciliation_repository import (
            SqlPositionReconciliationRepository,
        )

        repo = SqlPositionReconciliationRepository(
            SqlServerClient(load_settings().require_sqlserver_connection_string())
        )
        previous = repo.get_active_by_job(ids["job_id"])
        row = PositionReconciliation(
            id=str(uuid.uuid4()),
            client_id=ids["client_id"],
            inventory_id=ids["inventory_id"],
            job_id=ids["job_id"],
            ordered_capture_session_id=None,
            input_fingerprint=f"fp-{marker}-{tag}",
            status=ReconciliationStatus.COMPLETED,
            started_at=now,
            completed_at=now,
            failure_code=None,
            attempt_count=1,
            assigned_count=0,
            unassigned_count=0,
            sequence_gap_count=0,
            created_at=now,
            updated_at=now,
            reconciliation_name=RECONCILIATION_NAME,
            reconciliation_version=RECONCILIATION_VERSION,
            is_active=True,
            metadata_json={"marker": marker},
        )
        return repo.persist_revision_atomically(
            row, (), previous.id if previous else None
        ).id

    a, b, errors = _run_parallel(lambda: persist_one("a"), lambda: persist_one("b"))
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM dbo.position_reconciliations
            WHERE job_id = ? AND is_active = 1
            """,
            (ids["job_id"],),
        )
        active = int(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*) FROM dbo.position_reconciliations WHERE job_id = ?",
            (ids["job_id"],),
        )
        total = int(cur.fetchone()[0])
        ok = active == 1 and total >= 1 and not (a is None and b is None and errors)
        return ScenarioResult(
            name=name,
            ok=ok,
            detail=f"active={active} total={total} a={a} b={b} errors={len(errors)}",
            error="" if ok else f"errors={errors}",
        )
    finally:
        conn.close()


def main() -> int:
    _clear_polluted()
    layers = _load_dotenv()
    report = HarnessReport(notes=[f"dotenv={layers}"])
    try:
        report.results.append(scenario_one_active_revision())
        report.status = "PASS" if all(r.ok for r in report.results) else "FAIL"
    except Exception as exc:  # noqa: BLE001
        report.status = "FAIL"
        report.notes.append(f"error={exc}\n{traceback.format_exc()}")
    report.write()
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
