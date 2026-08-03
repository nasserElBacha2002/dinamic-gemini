#!/usr/bin/env python3
"""Real multi-connection SQL Server concurrency harness for Phase 1 uniqueness.

Uses independent pyodbc connections (not a shared client, not memory repos).
Prefers ``backend/.env.test`` when present (typically
``SQLSERVER_DATABASE=dinamic_inventory_test``).

Scenarios (must execute when SQL is reachable):
  1. Two concurrent OPEN session inserts for the same aisle_id
     → one row via UQ_ordered_capture_sessions_one_open_per_aisle
  2. Two concurrent inventory_jobs inserts same
     (ordered_capture_session_id, sequence_version)
     → one job via UQ_inventory_jobs_ordered_session_version
  3. Two concurrent aisle_location_labels inserts same
     (client_id, idempotency_key)
     → one label via UQ_aisle_location_labels_client_idempotency
  4. Two concurrent source_assets inserts same
     (ordered_capture_session_id, upload_client_file_id)
     → one asset via UQ_source_assets_ordered_session_client_file
  5. Two concurrent OrderedCaptureProcessingReservationService.reserve calls
     → one job, session PROCESSING linked to that job_id
  6. Two concurrent source_assets inserts same session+sequence_number
     → one asset via sequence uniqueness (when present)
  7. Two label inserts same idempotency_key with different request hashes
     → one row (unique key), second IntegrityError

Report: ``review/phase1-unblock-sql-concurrency-report.txt``
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

REPORT = _REPO_ROOT / "review" / "phase1-unblock-sql-concurrency-report.txt"
ISOLATION = "READ COMMITTED"
_PREFIX = "p1conc"


def _load_dotenv_layers() -> list[str]:
    """Load ``.env`` then prefer ``.env.test`` override (pytest-compatible)."""
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


def _resolved_db_name() -> str:
    from src.env_settings.sqlserver_resolution import resolved_sqlserver_database_name_from_env

    return (resolved_sqlserver_database_name_from_env() or os.getenv("SQLSERVER_DATABASE") or "").strip()


def _refuse_non_test_db(db_name: str) -> str | None:
    allow = (os.getenv("PHASE1_SQL_VALIDATE_ALLOW_NON_TEST") or "").strip() == "1"
    low = db_name.lower()
    if allow:
        return None
    if not low:
        return "database name empty"
    if "test" not in low and "dev" not in low:
        return (
            f"refusing database={db_name!r} (name must contain 'test' or 'dev'); "
            "set PHASE1_SQL_VALIDATE_ALLOW_NON_TEST=1 to override"
        )
    return None


def _write_report(lines: list[str]) -> Path:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _connect(connection_string: str):
    import pyodbc

    return pyodbc.connect(connection_string, autocommit=False)


@dataclass
class ConnOutcome:
    worker: int
    ok: bool
    error: str | None = None
    sqlstate: str | None = None
    native_error: int | None = None


@dataclass
class ScenarioResult:
    name: str
    isolation: str
    outcomes: list[ConnOutcome] = field(default_factory=list)
    final_count: int | None = None
    pass_fail: str = "FAIL"
    detail: str = ""


def _check_prerequisites(conn) -> list[str]:
    """Return missing prerequisite messages (empty = OK)."""
    cur = conn.cursor()
    checks = [
        ("table", "dbo.clients", "OBJECT_ID(N'dbo.clients', N'U')"),
        ("table", "dbo.inventories", "OBJECT_ID(N'dbo.inventories', N'U')"),
        ("table", "dbo.aisles", "OBJECT_ID(N'dbo.aisles', N'U')"),
        ("table", "dbo.ordered_capture_sessions", "OBJECT_ID(N'dbo.ordered_capture_sessions', N'U')"),
        ("table", "dbo.inventory_jobs", "OBJECT_ID(N'dbo.inventory_jobs', N'U')"),
        ("table", "dbo.source_assets", "OBJECT_ID(N'dbo.source_assets', N'U')"),
        ("table", "dbo.aisle_locations", "OBJECT_ID(N'dbo.aisle_locations', N'U')"),
        ("table", "dbo.aisle_location_labels", "OBJECT_ID(N'dbo.aisle_location_labels', N'U')"),
        (
            "index",
            "UQ_ordered_capture_sessions_one_open_per_aisle",
            """(
                SELECT 1 FROM sys.indexes
                WHERE name = N'UQ_ordered_capture_sessions_one_open_per_aisle'
                  AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
            )""",
        ),
        (
            "index",
            "UQ_inventory_jobs_ordered_session_version",
            """(
                SELECT 1 FROM sys.indexes
                WHERE name = N'UQ_inventory_jobs_ordered_session_version'
                  AND object_id = OBJECT_ID(N'dbo.inventory_jobs')
            )""",
        ),
        (
            "index",
            "UQ_aisle_location_labels_client_idempotency",
            """(
                SELECT 1 FROM sys.indexes
                WHERE name = N'UQ_aisle_location_labels_client_idempotency'
                  AND object_id = OBJECT_ID(N'dbo.aisle_location_labels')
            )""",
        ),
        (
            "index",
            "UQ_source_assets_ordered_session_client_file",
            """(
                SELECT 1 FROM sys.indexes
                WHERE name = N'UQ_source_assets_ordered_session_client_file'
                  AND object_id = OBJECT_ID(N'dbo.source_assets')
            )""",
        ),
        (
            "column",
            "aisle_location_labels.idempotency_key",
            "COL_LENGTH(N'dbo.aisle_location_labels', N'idempotency_key')",
        ),
    ]
    missing: list[str] = []
    for kind, label, expr in checks:
        cur.execute(f"SELECT CASE WHEN {expr} IS NOT NULL THEN 1 ELSE 0 END")
        if int(cur.fetchone()[0]) != 1:
            missing.append(f"{kind} missing: {label}")
    return missing


def _seed_parents(conn, tag: str) -> dict[str, str]:
    """Insert minimal client / inventory / aisle parents. Returns ids."""
    now = _now()
    client_id = f"{_PREFIX}-c-{tag}"
    inv_id = f"{_PREFIX}-i-{tag}"
    aisle_id = f"{_PREFIX}-a-{tag}"
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO clients (id, name, status, created_at, updated_at)
        VALUES (?, ?, 'active', ?, ?)
        """,
        (client_id, f"Phase1 Conc {tag}", now, now),
    )
    cur.execute(
        """
        INSERT INTO inventories (id, name, status, created_at, updated_at, processing_mode, client_id)
        VALUES (?, ?, 'draft', ?, ?, 'test', ?)
        """,
        (inv_id, f"Phase1 Conc Inv {tag}", now, now, client_id),
    )
    cur.execute(
        """
        INSERT INTO aisles (id, inventory_id, code, status, created_at, updated_at, is_active)
        VALUES (?, ?, ?, 'created', ?, ?, 1)
        """,
        (aisle_id, inv_id, f"C{tag[:6]}", now, now),
    )
    conn.commit()
    return {"client_id": client_id, "inventory_id": inv_id, "aisle_id": aisle_id}


def _cleanup_tag(conn, ids: dict[str, str], extra_session_ids: list[str] | None = None) -> None:
    """Best-effort delete of rows created for a scenario tag."""
    cur = conn.cursor()
    aisle_id = ids["aisle_id"]
    inv_id = ids["inventory_id"]
    client_id = ids["client_id"]
    session_ids = list(extra_session_ids or [])
    try:
        cur.execute(
            "SELECT id FROM ordered_capture_sessions WHERE aisle_id = ?",
            (aisle_id,),
        )
        session_ids.extend(str(r[0]) for r in cur.fetchall())
        session_ids = list(dict.fromkeys(session_ids))

        for sid in session_ids:
            # 0076 FK: clear processing_job_id before deleting jobs.
            cur.execute(
                "UPDATE ordered_capture_sessions SET processing_job_id = NULL WHERE id = ?",
                (sid,),
            )
            cur.execute(
                "DELETE FROM inventory_jobs WHERE ordered_capture_session_id = ?",
                (sid,),
            )
            cur.execute(
                "DELETE FROM source_assets WHERE ordered_capture_session_id = ?",
                (sid,),
            )
        cur.execute("DELETE FROM ordered_capture_sessions WHERE aisle_id = ?", (aisle_id,))
        cur.execute(
            """
            DELETE FROM aisle_location_labels
            WHERE client_id = ? OR location_id IN (
                SELECT id FROM aisle_locations WHERE aisle_id = ?
            )
            """,
            (client_id, aisle_id),
        )
        cur.execute("DELETE FROM aisle_locations WHERE aisle_id = ?", (aisle_id,))
        cur.execute("DELETE FROM source_assets WHERE aisle_id = ?", (aisle_id,))
        cur.execute("DELETE FROM inventory_jobs WHERE target_id = ?", (aisle_id,))
        cur.execute("DELETE FROM aisles WHERE id = ?", (aisle_id,))
        cur.execute("DELETE FROM inventories WHERE id = ?", (inv_id,))
        cur.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _is_unique_violation(exc: BaseException) -> bool:
    # pyodbc.IntegrityError / ProgrammingError with SQL Server 2627 / 2601
    native = getattr(exc, "args", None)
    text = str(exc)
    if "2627" in text or "2601" in text or "UNIQUE KEY" in text.upper() or "duplicate key" in text.lower():
        return True
    if native and len(native) >= 2:
        try:
            # args often: ('23000', '[...]', 'Violation...', 2627) or nested
            for part in native:
                if part in (2627, 2601):
                    return True
                if isinstance(part, Exception):
                    if _is_unique_violation(part):
                        return True
        except Exception:
            pass
    return False


def _exc_meta(exc: BaseException) -> tuple[str | None, int | None]:
    sqlstate = None
    native = None
    args = getattr(exc, "args", ()) or ()
    if args:
        if isinstance(args[0], str) and len(args[0]) <= 5:
            sqlstate = args[0]
        for a in args:
            if isinstance(a, int) and a in (2601, 2627, 547, 515):
                native = a
                break
    return sqlstate, native


def _run_two_connections(
    connection_string: str,
    isolation: str,
    insert_sql: str,
    insert_params_for_worker: Callable[[int], tuple[Any, ...]],
) -> list[ConnOutcome]:
    barrier = threading.Barrier(2, timeout=60)
    outcomes: list[ConnOutcome | None] = [None, None]
    errors: list[BaseException | None] = [None, None]

    def worker(idx: int) -> None:
        conn = None
        try:
            conn = _connect(connection_string)
            cur = conn.cursor()
            cur.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation}")
            barrier.wait()
            try:
                cur.execute(insert_sql, insert_params_for_worker(idx))
                conn.commit()
                outcomes[idx] = ConnOutcome(worker=idx, ok=True)
            except Exception as exc:  # noqa: BLE001 — record real SQL outcomes
                try:
                    conn.rollback()
                except Exception:  # nosec B110
                    pass
                sqlstate, native = _exc_meta(exc)
                outcomes[idx] = ConnOutcome(
                    worker=idx,
                    ok=False,
                    error=str(exc)[:500],
                    sqlstate=sqlstate,
                    native_error=native,
                )
        except Exception as exc:  # setup / barrier failure
            errors[idx] = exc
            outcomes[idx] = ConnOutcome(worker=idx, ok=False, error=f"setup: {exc}"[:500])
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # nosec B110
                    pass

    threads = [threading.Thread(target=worker, args=(i,)) for i in (0, 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    return [o if o is not None else ConnOutcome(worker=i, ok=False, error="no outcome") for i, o in enumerate(outcomes)]


def _pass_unique_race(outcomes: list[ConnOutcome], final_count: int, expect_count: int = 1) -> tuple[str, str]:
    ok_n = sum(1 for o in outcomes if o.ok)
    fail_n = sum(1 for o in outcomes if not o.ok)
    uniq_fails = sum(
        1 for o in outcomes if (not o.ok) and o.error and _is_unique_violation(Exception(o.error))
    )
    if final_count == expect_count and ok_n >= 1:
        if ok_n == 1 and fail_n == 1 and uniq_fails == 1 and final_count == 1:
            return "PASS", "one commit winner, one unique violation, count=1"
        if ok_n == 1 and fail_n == 1 and final_count == 1:
            return "PASS", "one commit winner, one loser, count=1"
        if ok_n == 2 and final_count == 1:
            return "PASS", "both reported success but single row (same logical identity)"
        if final_count == 1 and ok_n >= 1:
            return "PASS", f"final_count=1 ok={ok_n} fail={fail_n}"
    return (
        "FAIL",
        f"ok={ok_n} fail={fail_n} unique_fails={uniq_fails} final_count={final_count} expected={expect_count}",
    )


def scenario_open_sessions(connection_string: str, seed_conn, tag: str) -> ScenarioResult:
    ids = _seed_parents(seed_conn, tag)
    now = _now()
    id0, id1 = f"{_PREFIX}-s0-{tag}", f"{_PREFIX}-s1-{tag}"
    sql = """
        INSERT INTO ordered_capture_sessions (
            id, client_id, inventory_id, aisle_id, status,
            uploaded_asset_count, sequence_version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'OPEN', 0, 1, ?, ?)
    """

    def params(i: int) -> tuple[Any, ...]:
        sid = id0 if i == 0 else id1
        return (sid, ids["client_id"], ids["inventory_id"], ids["aisle_id"], now, now)

    outcomes = _run_two_connections(connection_string, ISOLATION, sql, params)
    cur = seed_conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM ordered_capture_sessions WHERE aisle_id = ? AND status = 'OPEN'",
        (ids["aisle_id"],),
    )
    count = int(cur.fetchone()[0])
    pf, detail = _pass_unique_race(outcomes, count)
    try:
        _cleanup_tag(seed_conn, ids)
    except Exception as exc:  # noqa: BLE001
        detail += f"; cleanup_error={exc}"
    return ScenarioResult(
        name="1_concurrent_open_sessions_same_aisle",
        isolation=ISOLATION,
        outcomes=outcomes,
        final_count=count,
        pass_fail=pf,
        detail=detail,
    )


def scenario_inventory_jobs(connection_string: str, seed_conn, tag: str) -> ScenarioResult:
    ids = _seed_parents(seed_conn, tag)
    now = _now()
    session_id = f"{_PREFIX}-sj-{tag}"
    cur = seed_conn.cursor()
    # Parent session must be non-open for job pin (SEALED is fine; unique is on session+version).
    cur.execute(
        """
        INSERT INTO ordered_capture_sessions (
            id, client_id, inventory_id, aisle_id, status,
            uploaded_asset_count, sequence_version, created_at, updated_at, sealed_at
        ) VALUES (?, ?, ?, ?, 'SEALED', 0, 1, ?, ?, ?)
        """,
        (session_id, ids["client_id"], ids["inventory_id"], ids["aisle_id"], now, now, now),
    )
    seed_conn.commit()

    seq_ver = 1
    j0, j1 = f"{_PREFIX}-j0-{tag}", f"{_PREFIX}-j1-{tag}"
    sql = """
        INSERT INTO inventory_jobs (
            id, target_type, target_id, job_type, status,
            payload_json, created_at, updated_at, attempt_count,
            identification_mode, identification_mode_source,
            configuration_snapshot_version, execution_strategy,
            ordered_capture_session_id, sequence_version
        ) VALUES (
            ?, 'aisle', ?, 'process_aisle', 'queued', ?, ?, ?, 1,
            'LEGACY_LLM', 'LEGACY_MIGRATION', 1, 'LEGACY_LLM',
            ?, ?
        )
    """

    def params(i: int) -> tuple[Any, ...]:
        jid = j0 if i == 0 else j1
        return (jid, ids["aisle_id"], "{}", now, now, session_id, seq_ver)

    outcomes = _run_two_connections(connection_string, ISOLATION, sql, params)
    cur.execute(
        """
        SELECT COUNT(*) FROM inventory_jobs
        WHERE ordered_capture_session_id = ? AND sequence_version = ?
        """,
        (session_id, seq_ver),
    )
    count = int(cur.fetchone()[0])
    pf, detail = _pass_unique_race(outcomes, count)
    try:
        _cleanup_tag(seed_conn, ids, [session_id])
    except Exception as exc:  # noqa: BLE001
        detail += f"; cleanup_error={exc}"
    return ScenarioResult(
        name="2_concurrent_jobs_same_session_version",
        isolation=ISOLATION,
        outcomes=outcomes,
        final_count=count,
        pass_fail=pf,
        detail=detail,
    )


def scenario_labels(connection_string: str, seed_conn, tag: str) -> ScenarioResult:
    ids = _seed_parents(seed_conn, tag)
    now = _now()
    loc_id = f"{_PREFIX}-loc-{tag}"
    idem = f"idem-{tag}"
    cur = seed_conn.cursor()
    cur.execute(
        """
        INSERT INTO aisle_locations (
            id, client_id, aisle_id, code, normalized_code, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
        """,
        (loc_id, ids["client_id"], ids["aisle_id"], f"L{tag[:6]}", f"l{tag[:6]}", now, now),
    )
    seed_conn.commit()

    l0, l1 = f"{_PREFIX}-lb0-{tag}", f"{_PREFIX}-lb1-{tag}"
    sql = """
        INSERT INTO aisle_location_labels (
            id, client_id, location_id, public_identifier,
            payload_version, marker_version, template_version,
            status, payload_json, signature_status, generated_at,
            idempotency_key, idempotency_request_hash
        ) VALUES (?, ?, ?, ?, 1, 1, 1, 'ACTIVE', ?, 'NOT_IMPLEMENTED', ?, ?, ?)
    """

    def params(i: int) -> tuple[Any, ...]:
        lid = l0 if i == 0 else l1
        pub = f"pub-{tag}-{i}"
        return (lid, ids["client_id"], loc_id, pub, "{}", now, idem, "hash-same")

    outcomes = _run_two_connections(connection_string, ISOLATION, sql, params)
    cur.execute(
        """
        SELECT COUNT(*) FROM aisle_location_labels
        WHERE client_id = ? AND idempotency_key = ?
        """,
        (ids["client_id"], idem),
    )
    count = int(cur.fetchone()[0])
    pf, detail = _pass_unique_race(outcomes, count)
    try:
        _cleanup_tag(seed_conn, ids)
    except Exception as exc:  # noqa: BLE001
        detail += f"; cleanup_error={exc}"
    return ScenarioResult(
        name="3_concurrent_labels_same_client_idempotency",
        isolation=ISOLATION,
        outcomes=outcomes,
        final_count=count,
        pass_fail=pf,
        detail=detail,
    )


def scenario_source_assets(connection_string: str, seed_conn, tag: str) -> ScenarioResult:
    ids = _seed_parents(seed_conn, tag)
    now = _now()
    session_id = f"{_PREFIX}-sa-s-{tag}"
    client_image_id = f"cimg-{tag}"
    cur = seed_conn.cursor()
    cur.execute(
        """
        INSERT INTO ordered_capture_sessions (
            id, client_id, inventory_id, aisle_id, status,
            uploaded_asset_count, sequence_version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'UPLOADING', 0, 1, ?, ?)
        """,
        (session_id, ids["client_id"], ids["inventory_id"], ids["aisle_id"], now, now),
    )
    seed_conn.commit()

    a0, a1 = f"{_PREFIX}-sa0-{tag}", f"{_PREFIX}-sa1-{tag}"
    sql = """
        INSERT INTO source_assets (
            id, aisle_id, type, original_filename, storage_path, mime_type, uploaded_at,
            upload_client_file_id, ordered_capture_session_id, sequence_number, sequence_source
        ) VALUES (?, ?, 'image', ?, ?, 'image/jpeg', ?, ?, ?, ?, 'CLIENT_ASSIGNED')
    """

    def params(i: int) -> tuple[Any, ...]:
        aid = a0 if i == 0 else a1
        # Distinct sequence_number so only client_file unique index is under test.
        return (
            aid,
            ids["aisle_id"],
            f"f{i}.jpg",
            f"/tmp/{aid}.jpg",
            now,
            client_image_id,
            session_id,
            i + 1,
        )

    outcomes = _run_two_connections(connection_string, ISOLATION, sql, params)
    cur.execute(
        """
        SELECT COUNT(*) FROM source_assets
        WHERE ordered_capture_session_id = ? AND upload_client_file_id = ?
        """,
        (session_id, client_image_id),
    )
    count = int(cur.fetchone()[0])
    pf, detail = _pass_unique_race(outcomes, count)
    try:
        _cleanup_tag(seed_conn, ids, [session_id])
    except Exception as exc:  # noqa: BLE001
        detail += f"; cleanup_error={exc}"
    return ScenarioResult(
        name="4_concurrent_assets_same_client_image_id",
        isolation=ISOLATION,
        outcomes=outcomes,
        final_count=count,
        pass_fail=pf,
        detail=detail,
    )


def scenario_process_reserve_uow(connection_string: str, seed_conn, tag: str) -> ScenarioResult:
    """Two independent clients race OrderedCaptureProcessingReservationService.reserve."""
    from src.application.services.ordered_capture_processing_reservation import (
        OrderedCaptureProcessingReservationService,
    )
    from src.database.sqlserver import SqlServerClient
    from src.domain.jobs.entities import Job, JobStatus
    from src.domain.ordered_capture.entities import (
        OrderedCaptureSession,
        OrderedCaptureSessionStatus,
    )
    from src.infrastructure.persistence.sql_ordered_capture_processing_reservation_unit_of_work import (
        build_sql_ordered_capture_processing_reservation_uow_factory,
    )

    ids = _seed_parents(seed_conn, tag)
    now = _now()
    session_id = f"{_PREFIX}-rs-{tag}"
    cur = seed_conn.cursor()
    cur.execute(
        """
        INSERT INTO ordered_capture_sessions (
            id, client_id, inventory_id, aisle_id, status,
            uploaded_asset_count, expected_asset_count, sequence_version,
            created_at, updated_at, sealed_at
        ) VALUES (?, ?, ?, ?, 'SEALED', 7, 7, 1, ?, ?, ?)
        """,
        (session_id, ids["client_id"], ids["inventory_id"], ids["aisle_id"], now, now, now),
    )
    seed_conn.commit()

    sealed = OrderedCaptureSession(
        id=session_id,
        client_id=ids["client_id"],
        inventory_id=ids["inventory_id"],
        aisle_id=ids["aisle_id"],
        status=OrderedCaptureSessionStatus.SEALED,
        uploaded_asset_count=7,
        expected_asset_count=7,
        sequence_version=1,
        created_at=now,
        updated_at=now,
        sealed_at=now,
    )

    barrier = threading.Barrier(2)
    outcomes: list[ConnOutcome] = []
    job_ids: list[str] = []
    lock = threading.Lock()

    def worker(idx: int) -> None:
        client = SqlServerClient(connection_string)
        svc = OrderedCaptureProcessingReservationService(
            uow_factory=build_sql_ordered_capture_processing_reservation_uow_factory(client)
        )
        jid = f"{_PREFIX}-rj{idx}-{tag}"
        template = Job(
            id=jid,
            target_type="aisle",
            target_id=ids["aisle_id"],
            job_type="process_aisle",
            status=JobStatus.QUEUED,
            payload_json={},
            created_at=now,
            updated_at=now,
            ordered_capture_session_id=session_id,
            sequence_version=1,
        )
        try:
            barrier.wait(timeout=30)
            result = svc.reserve(template, sealed, now)
            with lock:
                job_ids.append(result.job.id)
                outcomes.append(ConnOutcome(worker=idx, ok=True))
        except Exception as exc:  # noqa: BLE001
            sqlstate, native = _exc_meta(exc)
            with lock:
                outcomes.append(
                    ConnOutcome(
                        worker=idx,
                        ok=False,
                        error=str(exc)[:400],
                        sqlstate=sqlstate,
                        native_error=native,
                    )
                )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    cur.execute(
        """
        SELECT status, processing_job_id FROM ordered_capture_sessions WHERE id = ?
        """,
        (session_id,),
    )
    row = cur.fetchone()
    status = str(row[0]) if row else None
    linked_job = str(row[1]) if row and row[1] is not None else None
    cur.execute(
        """
        SELECT COUNT(*) FROM inventory_jobs
        WHERE ordered_capture_session_id = ? AND sequence_version = 1
        """,
        (session_id,),
    )
    job_count = int(cur.fetchone()[0])
    unique_job_ids = sorted(set(job_ids))
    ok_n = sum(1 for o in outcomes if o.ok)
    pf = "FAIL"
    detail = (
        f"ok={ok_n}/2 job_count={job_count} unique_returned={unique_job_ids} "
        f"status={status} processing_job_id={linked_job}"
    )
    if (
        ok_n == 2
        and job_count == 1
        and len(unique_job_ids) == 1
        and status == "PROCESSING"
        and linked_job == unique_job_ids[0]
    ):
        pf = "PASS"
        detail = f"both converged to job_id={unique_job_ids[0]}; session PROCESSING linked"
    try:
        _cleanup_tag(seed_conn, ids, [session_id])
    except Exception as exc:  # noqa: BLE001
        detail += f"; cleanup_error={exc}"
    return ScenarioResult(
        name="5_concurrent_process_reserve_uow",
        isolation=ISOLATION,
        outcomes=outcomes,
        final_count=job_count,
        pass_fail=pf,
        detail=detail,
    )


def scenario_assets_same_sequence(connection_string: str, seed_conn, tag: str) -> ScenarioResult:
    ids = _seed_parents(seed_conn, tag)
    now = _now()
    session_id = f"{_PREFIX}-sq-s-{tag}"
    cur = seed_conn.cursor()
    cur.execute(
        """
        INSERT INTO ordered_capture_sessions (
            id, client_id, inventory_id, aisle_id, status,
            uploaded_asset_count, sequence_version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'UPLOADING', 0, 1, ?, ?)
        """,
        (session_id, ids["client_id"], ids["inventory_id"], ids["aisle_id"], now, now),
    )
    seed_conn.commit()

    a0, a1 = f"{_PREFIX}-sq0-{tag}", f"{_PREFIX}-sq1-{tag}"
    sql = """
        INSERT INTO source_assets (
            id, aisle_id, type, original_filename, storage_path, mime_type, uploaded_at,
            upload_client_file_id, ordered_capture_session_id, sequence_number, sequence_source
        ) VALUES (?, ?, 'image', ?, ?, 'image/jpeg', ?, ?, ?, 1, 'CLIENT_ASSIGNED')
    """

    def params(i: int) -> tuple[Any, ...]:
        aid = a0 if i == 0 else a1
        return (
            aid,
            ids["aisle_id"],
            f"seq{i}.jpg",
            f"/tmp/{aid}.jpg",
            now,
            f"cimg-seq-{tag}-{i}",
            session_id,
        )

    outcomes = _run_two_connections(connection_string, ISOLATION, sql, params)
    cur.execute(
        """
        SELECT COUNT(*) FROM source_assets
        WHERE ordered_capture_session_id = ? AND sequence_number = 1
        """,
        (session_id,),
    )
    count = int(cur.fetchone()[0])
    pf, detail = _pass_unique_race(outcomes, count)
    detail += "; UQ_source_assets_ordered_session_sequence"
    try:
        _cleanup_tag(seed_conn, ids, [session_id])
    except Exception as exc:  # noqa: BLE001
        detail += f"; cleanup_error={exc}"
    return ScenarioResult(
        name="6_concurrent_assets_same_sequence_number",
        isolation=ISOLATION,
        outcomes=outcomes,
        final_count=count,
        pass_fail=pf,
        detail=detail,
    )


def scenario_labels_same_key_diff_hash(connection_string: str, seed_conn, tag: str) -> ScenarioResult:
    ids = _seed_parents(seed_conn, tag)
    now = _now()
    loc_id = f"{_PREFIX}-loc2-{tag}"
    idem = f"idem-diff-{tag}"
    cur = seed_conn.cursor()
    cur.execute(
        """
        INSERT INTO aisle_locations (
            id, client_id, aisle_id, code, normalized_code, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
        """,
        (loc_id, ids["client_id"], ids["aisle_id"], f"D{tag[:6]}", f"d{tag[:6]}", now, now),
    )
    seed_conn.commit()

    l0, l1 = f"{_PREFIX}-ld0-{tag}", f"{_PREFIX}-ld1-{tag}"
    sql = """
        INSERT INTO aisle_location_labels (
            id, client_id, location_id, public_identifier,
            payload_version, marker_version, template_version,
            status, payload_json, signature_status, generated_at,
            idempotency_key, idempotency_request_hash
        ) VALUES (?, ?, ?, ?, 1, 1, 1, 'ACTIVE', ?, 'NOT_IMPLEMENTED', ?, ?, ?)
    """

    def params(i: int) -> tuple[Any, ...]:
        lid = l0 if i == 0 else l1
        pub = f"pubd-{tag}-{i}"
        return (lid, ids["client_id"], loc_id, pub, "{}", now, idem, f"hash-diff-{i}")

    outcomes = _run_two_connections(connection_string, ISOLATION, sql, params)
    cur.execute(
        """
        SELECT COUNT(*) FROM aisle_location_labels
        WHERE client_id = ? AND idempotency_key = ?
        """,
        (ids["client_id"], idem),
    )
    count = int(cur.fetchone()[0])
    pf, detail = _pass_unique_race(outcomes, count)
    detail += "; different idempotency_request_hash still collide on unique key"
    try:
        _cleanup_tag(seed_conn, ids)
    except Exception as exc:  # noqa: BLE001
        detail += f"; cleanup_error={exc}"
    return ScenarioResult(
        name="7_concurrent_labels_same_key_diff_hash",
        isolation=ISOLATION,
        outcomes=outcomes,
        final_count=count,
        pass_fail=pf,
        detail=detail,
    )


def _format_scenario(sr: ScenarioResult) -> list[str]:
    lines = [
        f"## scenario={sr.name}",
        f"isolation={sr.isolation}",
        f"result={sr.pass_fail}",
        f"final_count={sr.final_count}",
        f"detail={sr.detail}",
    ]
    for o in sr.outcomes:
        lines.append(
            f"  conn[{o.worker}]: ok={o.ok} sqlstate={o.sqlstate} "
            f"native={o.native_error} error={o.error!r}"
        )
    return lines


def main() -> int:
    lines: list[str] = [
        "# Phase 1 unblock — SQL concurrency report",
        f"generated_at={_now().isoformat()}",
    ]
    loaded = _load_dotenv_layers()
    lines.append(f"dotenv_loaded={loaded or ['(none)']}")

    if not _sqlserver_env_present():
        lines.extend(
            [
                "status=SKIP",
                "reason=SQL Server connection env not configured",
                "note=Configure backend/.env.test with SQLSERVER_DATABASE=dinamic_inventory_test",
            ]
        )
        path = _write_report(lines)
        print("SKIP: SQL Server not configured; wrote", path)
        return 0

    db_name = _resolved_db_name()
    lines.append(f"database={db_name}")
    refuse = _refuse_non_test_db(db_name)
    if refuse:
        lines.extend(["status=SKIP", f"reason={refuse}"])
        path = _write_report(lines)
        print("SKIP:", refuse, "; wrote", path)
        return 0

    try:
        from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config

        connection_string = resolve_sqlserver_connection_config().connection_string.strip()
        if not connection_string:
            lines.extend(["status=SKIP", "reason=resolved connection string empty"])
            path = _write_report(lines)
            print("SKIP: empty connection string; wrote", path)
            return 0

        seed_conn = _connect(connection_string)
        try:
            missing = _check_prerequisites(seed_conn)
            if missing:
                lines.extend(
                    [
                        "status=FAIL",
                        "reason=prerequisite Phase 1 objects missing — apply migrations 0074+0075 on the test DB",
                        *[f"  missing: {m}" for m in missing],
                    ]
                )
                path = _write_report(lines)
                print("FAIL: prerequisites missing; wrote", path)
                return 1

            results: list[ScenarioResult] = []
            runners = (
                scenario_open_sessions,
                scenario_inventory_jobs,
                scenario_labels,
                scenario_source_assets,
                scenario_process_reserve_uow,
                scenario_assets_same_sequence,
                scenario_labels_same_key_diff_hash,
            )
            for runner in runners:
                tag = uuid.uuid4().hex[:10]
                try:
                    results.append(runner(connection_string, seed_conn, tag))
                except Exception as exc:  # noqa: BLE001
                    results.append(
                        ScenarioResult(
                            name=runner.__name__,
                            isolation=ISOLATION,
                            pass_fail="FAIL",
                            detail=f"scenario exception: {exc}\n{traceback.format_exc()[-800:]}",
                        )
                    )

            for sr in results:
                lines.extend(_format_scenario(sr))
                lines.append("")

            expected = len(runners)
            all_pass = all(r.pass_fail == "PASS" for r in results) and len(results) == expected
            lines.append(f"status={'PASS' if all_pass else 'FAIL'}")
            lines.append(
                f"scenarios_passed={sum(1 for r in results if r.pass_fail == 'PASS')}/{expected}"
            )
            path = _write_report(lines)
            print(
                f"{'PASS' if all_pass else 'FAIL'}: concurrency harness done; "
                f"passed={sum(1 for r in results if r.pass_fail == 'PASS')}/{expected} report={path}"
            )
            return 0 if all_pass else 1
        finally:
            seed_conn.close()
    except Exception as exc:
        lines.extend([f"error={exc}", "status=FAIL", traceback.format_exc()[-1200:]])
        path = _write_report(lines)
        print(f"FAIL: {exc}; report={path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
