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
            errors.append(
                f"{key}: exception_type={type(exc).__name__} message={exc}\n"
                f"{traceback.format_exc()}"
            )

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
        previous = repo.get_published_by_job(ids["job_id"])
        row = PositionReconciliation(
            id=str(uuid.uuid4()),
            client_id=ids["client_id"],
            inventory_id=ids["inventory_id"],
            job_id=ids["job_id"],
            ordered_capture_session_id=None,
            input_fingerprint=f"fp-{tag}",
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
        return repo.publish_completed_revision_atomically(
            row,
            (),
            previous.id if previous else None,
            expected_input_fingerprint=row.input_fingerprint,
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
        structured_errors = all(
            "PositionReconciliationAlreadyRunningError" in error for error in errors
        )
        converged = a is not None and b is not None and a == b and not errors
        ok = active == 1 and total >= 1 and (converged or structured_errors)
        return ScenarioResult(
            name=name,
            ok=ok,
            detail=f"active={active} total={total} a={a} b={b} errors={len(errors)}",
            error="" if ok else f"errors={errors}",
        )
    finally:
        conn.close()


def scenario_failed_attempt_preserves_publication() -> ScenarioResult:
    name = "failed_attempt_preserves_published_revision"
    tag = uuid.uuid4().hex[:10]
    try:
        ids = _seed(tag)
        from src.config import load_settings
        from src.database.sqlserver import SqlServerClient
        from src.domain.position_reconciliation.entities import (
            PositionReconciliation,
            ReconciliationStatus,
        )
        from src.infrastructure.repositories.sql_position_reconciliation_repository import (
            SqlPositionReconciliationRepository,
        )

        repo = SqlPositionReconciliationRepository(
            SqlServerClient(load_settings().require_sqlserver_connection_string())
        )
        now = datetime.now(timezone.utc)
        published = PositionReconciliation(
            id=str(uuid.uuid4()),
            client_id=ids["client_id"],
            inventory_id=ids["inventory_id"],
            job_id=ids["job_id"],
            ordered_capture_session_id=None,
            input_fingerprint=f"published-{tag}",
            status=ReconciliationStatus.COMPLETED,
            started_at=now,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        repo.publish_completed_revision_atomically(
            published, (), None, published.input_fingerprint
        )
        assignments_before = len(repo.list_active_assignments(ids["job_id"]))
        failed = PositionReconciliation(
            id=str(uuid.uuid4()),
            client_id=ids["client_id"],
            inventory_id=ids["inventory_id"],
            job_id=ids["job_id"],
            ordered_capture_session_id=None,
            input_fingerprint=f"failed-{tag}",
            status=ReconciliationStatus.FAILED,
            started_at=now,
            completed_at=now,
            failure_code="HARNESS_FAILURE",
            created_at=now,
            updated_at=now,
            is_active=False,
        )
        repo.record_failed_attempt(failed)
        current = repo.get_published_by_job(ids["job_id"])
        assignments_after = len(repo.list_active_assignments(ids["job_id"]))
        ok = (
            current is not None
            and current.id == published.id
            and assignments_after == assignments_before
        )
        return ScenarioResult(
            name=name,
            ok=ok,
            detail=(
                f"published_id={current.id if current else None} "
                f"assignments_before={assignments_before} assignments_after={assignments_after}"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return ScenarioResult(
            name=name,
            ok=False,
            error=f"exception_type={type(exc).__name__} message={exc}",
        )


def _cleanup_harness_rows() -> str:
    """Best-effort delete of p4conc-* rows so harnesses do not pollute the UI."""
    conn = _connect()
    try:
        cur = conn.cursor()
        # Match harness ids only (p4conc-*) — avoid broad name patterns.
        cur.execute("SELECT id FROM clients WHERE id LIKE ?", (f"{_PREFIX}-%",))
        client_ids = [str(r[0]) for r in cur.fetchall()]
        if not client_ids:
            return "cleanup=none"
        ph = ",".join("?" * len(client_ids))
        cur.execute(f"SELECT id FROM inventories WHERE client_id IN ({ph})", client_ids)
        inv_ids = [str(r[0]) for r in cur.fetchall()]
        aisle_ids: list[str] = []
        if inv_ids:
            iph = ",".join("?" * len(inv_ids))
            cur.execute(f"SELECT id FROM aisles WHERE inventory_id IN ({iph})", inv_ids)
            aisle_ids = [str(r[0]) for r in cur.fetchall()]
        job_ids: list[str] = []
        if aisle_ids:
            aph = ",".join("?" * len(aisle_ids))
            cur.execute(f"SELECT id FROM inventory_jobs WHERE target_id IN ({aph})", aisle_ids)
            job_ids = [str(r[0]) for r in cur.fetchall()]
        if job_ids:
            jph = ",".join("?" * len(job_ids))
            cur.execute(
                f"DELETE FROM dbo.product_position_assignments WHERE job_id IN ({jph})",
                job_ids,
            )
            cur.execute(
                f"DELETE FROM dbo.position_reconciliations WHERE job_id IN ({jph})",
                job_ids,
            )
        if aisle_ids:
            aph = ",".join("?" * len(aisle_ids))
            cur.execute(f"DELETE FROM inventory_jobs WHERE target_id IN ({aph})", aisle_ids)
            cur.execute(f"DELETE FROM aisles WHERE id IN ({aph})", aisle_ids)
        if inv_ids:
            iph = ",".join("?" * len(inv_ids))
            cur.execute(f"DELETE FROM inventories WHERE id IN ({iph})", inv_ids)
        cur.execute(f"DELETE FROM clients WHERE id IN ({ph})", client_ids)
        conn.commit()
        return f"cleanup=clients:{len(client_ids)} inventories:{len(inv_ids)}"
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        return f"cleanup_error={exc}"
    finally:
        conn.close()


def main() -> int:
    _clear_polluted()
    layers = _load_dotenv()
    report = HarnessReport(notes=[f"dotenv={layers}"])
    try:
        report.results.append(scenario_one_active_revision())
        report.results.append(scenario_failed_attempt_preserves_publication())
        report.status = "PASS" if all(r.ok for r in report.results) else "FAIL"
    except Exception as exc:  # noqa: BLE001
        report.status = "FAIL"
        report.notes.append(f"error={exc}\n{traceback.format_exc()}")
    cleanup_note = _cleanup_harness_rows()
    report.notes.append(cleanup_note)
    if cleanup_note.startswith("cleanup_error="):
        report.status = "FAIL"
        report.notes.append("cleanup_failure_forces_FAIL")
    report.write()
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
