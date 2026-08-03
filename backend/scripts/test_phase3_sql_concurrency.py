#!/usr/bin/env python3
"""Phase 3 SQL concurrency harness (multi-connection).

Scenarios:
  1. Two concurrent atomic replaces for same job+asset → one coherent set
  2. Two jobs same asset → distinct detection rows (job-scoped identity)
  3. Concurrent upserts same identity → single row

Writes ``review/phase3-position-label-detection-sql-concurrency-report.txt``.
"""

from __future__ import annotations

import hashlib
import json
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

REPORT = _REPO_ROOT / "review" / "phase3-position-label-detection-sql-concurrency-report.txt"
_PREFIX = "p3conc"


def _load_dotenv_layers() -> list[str]:
    """Load env layers.

    Default: project ``.env`` (schema-complete local DB). Set
    ``PHASE3_SQL_USE_TEST_DB=1`` to prefer ``.env.test`` when that database
    is migration-compatible (many local test DBs are stuck pre-0080).
    """
    loaded: list[str] = []
    try:
        from dotenv import load_dotenv
    except ImportError:
        return loaded
    use_test = (os.getenv("PHASE3_SQL_USE_TEST_DB") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    layers = [
        (_REPO_ROOT / ".env", False),
        (_BACKEND_ROOT / ".env", False),
    ]
    if use_test:
        layers.extend(
            [
                (_REPO_ROOT / ".env.test", True),
                (_BACKEND_ROOT / ".env.test", True),
            ]
        )
    for path, override in layers:
        if path.is_file():
            load_dotenv(path, override=override)
            loaded.append(f"{path} (override={override})")
    return loaded


def _sqlserver_env_present() -> bool:
    if (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip():
        return True
    keys = ("SQLSERVER_SERVER", "SQLSERVER_DATABASE", "SQLSERVER_UID", "SQLSERVER_PWD")
    return all((os.getenv(k) or "").strip() for k in keys)


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

    settings = load_settings()
    cs = settings.require_sqlserver_connection_string()
    conn = pyodbc.connect(cs)
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


def _seed_job_asset(cur, *, tag: str, now: datetime, job_suffix: str = "j") -> dict[str, str]:
    client_id = f"{_PREFIX}-c-{tag}"
    inv_id = f"{_PREFIX}-i-{tag}"
    aisle_id = f"{_PREFIX}-a-{tag}"
    job_id = f"{_PREFIX}-{job_suffix}-{tag}"
    asset_id = f"{_PREFIX}-sa-{tag}"
    cur.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM clients WHERE id = ?)
        INSERT INTO clients (id, name, status, created_at, updated_at)
        VALUES (?, ?, 'active', ?, ?)
        """,
        (client_id, client_id, f"P3 Conc {tag}", now, now),
    )
    cur.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM inventories WHERE id = ?)
        INSERT INTO inventories (id, name, status, created_at, updated_at, processing_mode, client_id)
        VALUES (?, ?, 'draft', ?, ?, 'test', ?)
        """,
        (inv_id, inv_id, f"P3 Conc Inv {tag}", now, now, client_id),
    )
    cur.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM aisles WHERE id = ?)
        INSERT INTO aisles (id, inventory_id, code, status, created_at, updated_at, is_active)
        VALUES (?, ?, ?, 'created', ?, ?, 1)
        """,
        (aisle_id, aisle_id, inv_id, f"C{tag[:6]}", now, now),
    )
    cur.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM inventory_jobs WHERE id = ?)
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
        (job_id, job_id, aisle_id, "{}", now, now),
    )
    cur.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM source_assets WHERE id = ?)
        INSERT INTO source_assets (
            id, aisle_id, type, original_filename, storage_path, mime_type, uploaded_at
        ) VALUES (?, ?, 'image', ?, ?, 'image/jpeg', ?)
        """,
        (asset_id, asset_id, aisle_id, f"{tag}.jpg", f"/tmp/{tag}.jpg", now),
    )
    return {
        "client_id": client_id,
        "inventory_id": inv_id,
        "aisle_id": aisle_id,
        "job_id": job_id,
        "source_asset_id": asset_id,
    }


def _payload_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def scenario_concurrent_atomic_replace() -> ScenarioResult:
    name = "two_concurrent_atomic_replaces_same_job_asset"
    tag = uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    seed = _connect()
    try:
        cur = seed.cursor()
        ids = _seed_job_asset(cur, tag=tag, now=now)
        seed.commit()
    except Exception as exc:  # noqa: BLE001
        seed.rollback()
        return ScenarioResult(name=name, ok=False, error=f"seed_failed={exc}")
    finally:
        seed.close()

    det_version = "position-label-detection-1.0.0"
    hash_a = _payload_hash(f"A-{tag}")
    hash_b = _payload_hash(f"B-{tag}")

    def replace_one(payload_hash: str, marker: str) -> str:
        from src.config import load_settings
        from src.database.sqlserver import SqlServerClient
        from src.domain.position_label_detection.entities import (
            DETECTOR_NAME,
            DETECTOR_VERSION,
            ImagePositionLabelDetection,
            PositionLabelDetectionStatus,
            PositionLabelSignatureStatus,
        )
        from src.infrastructure.repositories.sql_image_position_label_detection_repository import (
            SqlImagePositionLabelDetectionRepository,
        )

        client = SqlServerClient(load_settings().require_sqlserver_connection_string())
        repo = SqlImagePositionLabelDetectionRepository(client)
        det_id = str(uuid.uuid4())
        row = ImagePositionLabelDetection(
            id=det_id,
            client_id=ids["client_id"],
            inventory_id=ids["inventory_id"],
            job_id=ids["job_id"],
            source_asset_id=ids["source_asset_id"],
            detection_status=PositionLabelDetectionStatus.NO_LABEL,
            signature_status=PositionLabelSignatureStatus.MISSING,
            payload_version=None,
            raw_payload_hash=payload_hash,
            detector_name=DETECTOR_NAME,
            detector_version=DETECTOR_VERSION,
            created_at=now,
            updated_at=now,
            metadata_json={"marker": marker},
        )
        out = repo.replace_asset_detections_atomically(
            job_id=ids["job_id"],
            source_asset_id=ids["source_asset_id"],
            detector_version=det_version,
            detections=[row],
        )
        return out[0].id if out else ""

    a, b, errors = _run_parallel(
        lambda: replace_one(hash_a, "a"),
        lambda: replace_one(hash_b, "b"),
    )
    if errors and a is None and b is None:
        return ScenarioResult(name=name, ok=False, error="; ".join(errors))

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM dbo.image_position_label_detections
            WHERE job_id = ? AND source_asset_id = ? AND detector_version = ?
            """,
            (ids["job_id"], ids["source_asset_id"], det_version),
        )
        count = int(cur.fetchone()[0])
        # Last writer wins atomically — expect exactly one survivor set (1 row).
        ok = count == 1
        return ScenarioResult(
            name=name,
            ok=ok,
            detail=f"rows={count} a={a} b={b} errors={len(errors)}",
            error="" if ok else f"expected 1 row, got {count}; errors={errors}",
        )
    finally:
        conn.close()


def scenario_job_scoped_identity() -> ScenarioResult:
    name = "two_jobs_same_asset_distinct_rows"
    tag = uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    seed = _connect()
    try:
        cur = seed.cursor()
        ids_a = _seed_job_asset(cur, tag=tag, now=now, job_suffix="j1")
        job_b = f"{_PREFIX}-j2-{tag}"
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
            (job_b, ids_a["aisle_id"], "{}", now, now),
        )
        seed.commit()
    except Exception as exc:  # noqa: BLE001
        seed.rollback()
        return ScenarioResult(name=name, ok=False, error=f"seed_failed={exc}")
    finally:
        seed.close()

    payload = json.dumps({"t": "DINAMIC_POSITION", "tag": tag})
    ph = _payload_hash(payload)

    def insert_for_job(job_id: str) -> str:
        from src.config import load_settings
        from src.database.sqlserver import SqlServerClient
        from src.domain.position_label_detection.entities import (
            DETECTOR_NAME,
            DETECTOR_VERSION,
            ImagePositionLabelDetection,
            PositionLabelDetectionStatus,
            PositionLabelSignatureStatus,
        )
        from src.infrastructure.repositories.sql_image_position_label_detection_repository import (
            SqlImagePositionLabelDetectionRepository,
        )

        client = SqlServerClient(load_settings().require_sqlserver_connection_string())
        repo = SqlImagePositionLabelDetectionRepository(client)
        row = ImagePositionLabelDetection(
            id=str(uuid.uuid4()),
            client_id=ids_a["client_id"],
            inventory_id=ids_a["inventory_id"],
            job_id=job_id,
            source_asset_id=ids_a["source_asset_id"],
            detection_status=PositionLabelDetectionStatus.NO_LABEL,
            signature_status=PositionLabelSignatureStatus.MISSING,
            payload_version=None,
            raw_payload_hash=ph,
            detector_name=DETECTOR_NAME,
            detector_version=DETECTOR_VERSION,
            created_at=now,
            updated_at=now,
        )
        saved = repo.upsert_idempotent(row)
        return saved.id

    a, b, errors = _run_parallel(
        lambda: insert_for_job(ids_a["job_id"]),
        lambda: insert_for_job(job_b),
    )
    if errors:
        return ScenarioResult(name=name, ok=False, error="; ".join(errors))

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT job_id, COUNT(*) FROM dbo.image_position_label_detections
            WHERE source_asset_id = ? AND raw_payload_hash = ?
            GROUP BY job_id
            """,
            (ids_a["source_asset_id"], ph),
        )
        rows = cur.fetchall()
        ok = len(rows) == 2 and all(int(r[1]) == 1 for r in rows) and a != b
        return ScenarioResult(
            name=name,
            ok=ok,
            detail=f"job_groups={[(r[0], int(r[1])) for r in rows]} a={a} b={b}",
            error="" if ok else "expected two job-scoped rows",
        )
    finally:
        conn.close()


def scenario_concurrent_same_identity() -> ScenarioResult:
    name = "two_concurrent_same_identity_upserts"
    tag = uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    seed = _connect()
    try:
        cur = seed.cursor()
        ids = _seed_job_asset(cur, tag=tag, now=now)
        seed.commit()
    except Exception as exc:  # noqa: BLE001
        seed.rollback()
        return ScenarioResult(name=name, ok=False, error=f"seed_failed={exc}")
    finally:
        seed.close()

    ph = _payload_hash(f"same-{tag}")

    def upsert_one(marker: str) -> str:
        from src.config import load_settings
        from src.database.sqlserver import SqlServerClient
        from src.domain.position_label_detection.entities import (
            DETECTOR_NAME,
            DETECTOR_VERSION,
            ImagePositionLabelDetection,
            PositionLabelDetectionStatus,
            PositionLabelSignatureStatus,
        )
        from src.infrastructure.repositories.sql_image_position_label_detection_repository import (
            SqlImagePositionLabelDetectionRepository,
        )

        client = SqlServerClient(load_settings().require_sqlserver_connection_string())
        repo = SqlImagePositionLabelDetectionRepository(client)
        row = ImagePositionLabelDetection(
            id=str(uuid.uuid4()),
            client_id=ids["client_id"],
            inventory_id=ids["inventory_id"],
            job_id=ids["job_id"],
            source_asset_id=ids["source_asset_id"],
            detection_status=PositionLabelDetectionStatus.NO_LABEL,
            signature_status=PositionLabelSignatureStatus.MISSING,
            payload_version=None,
            raw_payload_hash=ph,
            detector_name=DETECTOR_NAME,
            detector_version=DETECTOR_VERSION,
            created_at=now,
            updated_at=now,
            metadata_json={"marker": marker},
        )
        return repo.upsert_idempotent(row).id

    a, b, errors = _run_parallel(lambda: upsert_one("a"), lambda: upsert_one("b"))
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*), MIN(id), MAX(id)
            FROM dbo.image_position_label_detections
            WHERE job_id = ? AND source_asset_id = ? AND raw_payload_hash = ?
              AND detection_status = 'NO_LABEL'
            """,
            (ids["job_id"], ids["source_asset_id"], ph),
        )
        count, min_id, max_id = cur.fetchone()
        count_i = int(count)
        ok = count_i == 1 and (a == b or a == min_id or b == min_id)
        return ScenarioResult(
            name=name,
            ok=ok,
            detail=f"rows={count_i} a={a} b={b} id={min_id} errors={len(errors)}",
            error="" if ok else f"expected 1 row; errors={errors}",
        )
    finally:
        conn.close()


def _cleanup_harness_rows() -> str:
    """Best-effort delete of p3conc-* rows so harnesses do not pollute the UI."""
    conn = _connect()
    try:
        cur = conn.cursor()
        # Match harness ids only (p3conc-*) — avoid broad name patterns.
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
                f"DELETE FROM dbo.image_position_label_detections WHERE job_id IN ({jph})",
                job_ids,
            )
        if aisle_ids:
            aph = ",".join("?" * len(aisle_ids))
            cur.execute(f"DELETE FROM source_assets WHERE aisle_id IN ({aph})", aisle_ids)
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
    layers = _load_dotenv_layers()
    report = HarnessReport()
    report.notes.append(f"dotenv_layers={layers}")
    if not _sqlserver_env_present():
        report.status = "NOT_RUN"
        report.notes.append("SQLSERVER_* not configured")
        report.write()
        return 2
    try:
        report.results.append(scenario_concurrent_atomic_replace())
        report.results.append(scenario_job_scoped_identity())
        report.results.append(scenario_concurrent_same_identity())
        report.status = "PASS" if all(r.ok for r in report.results) else "FAIL"
    except Exception as exc:  # noqa: BLE001
        report.status = "FAIL"
        report.notes.append(f"harness_error={exc}\n{traceback.format_exc()}")
    cleanup_note = _cleanup_harness_rows()
    report.notes.append(cleanup_note)
    if cleanup_note.startswith("cleanup_error="):
        report.status = "FAIL"
        report.notes.append("cleanup_failure_forces_FAIL")
    report.write()
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
