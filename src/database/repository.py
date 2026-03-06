"""Stage 8 — Repository layer for jobs, pallet_results, job_events."""

import json
import logging
from typing import Any, Dict, List, Optional

from src.database.sqlserver import SqlServerClient, now_utc

logger = logging.getLogger(__name__)


def _serialize_metadata(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    if metadata is None:
        return None
    return json.dumps(metadata, ensure_ascii=False)


def _parse_metadata(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _row_to_iso(row: Any, attr: str) -> str:
    val = getattr(row, attr, None)
    if val is None:
        return ""
    if hasattr(val, "isoformat"):
        s = val.isoformat()
        if getattr(val, "tzinfo", None) is None and "Z" not in s and "+" not in s:
            s = s + "Z"
        return s.replace("+00:00", "Z")
    return str(val)


class JobsRepository:
    """CRUD for jobs table. All queries parameterized."""

    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def create_job(
        self,
        job_id: str,
        video_path: str,
        mode: str = "hybrid",
        confidence_threshold: float = 0.70,
        video_filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        engine_version: str = "v2.0",
        input_type: str = "video",
        input_manifest_path: Optional[str] = None,
        photos_dir: Optional[str] = None,
    ) -> None:
        now = now_utc()
        meta_str = _serialize_metadata(metadata)
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs (
                    id, created_at, updated_at, status, mode, confidence_threshold,
                    video_filename, video_path, engine_version, metadata,
                    input_type, input_manifest_path, photos_dir
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    now,
                    now,
                    "queued",
                    mode,
                    confidence_threshold,
                    video_filename,
                    video_path,
                    engine_version,
                    meta_str,
                    input_type,
                    input_manifest_path,
                    photos_dir,
                ),
            )

    def update_job_status(
        self,
        job_id: str,
        status: str,
        progress_stage: Optional[str] = None,
        progress_percent: Optional[int] = None,
    ) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs SET updated_at = ?, status = ?, progress_stage = ?, progress_percent = ?
                WHERE id = ?
                """,
                (now_utc(), status, progress_stage, progress_percent, job_id),
            )

    def update_job_progress(self, job_id: str, stage: str, percent: int) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET updated_at = ?, progress_stage = ?, progress_percent = ? WHERE id = ?",
                (now_utc(), stage, percent, job_id),
            )

    def set_job_outputs(
        self,
        job_id: str,
        report_json_path: Optional[str] = None,
        report_csv_path: Optional[str] = None,
        artifacts_dir: Optional[str] = None,
        frames_count_sent: Optional[int] = None,
        gemini_calls: Optional[int] = None,
        prompt_version: Optional[str] = None,
    ) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs SET updated_at = ?, status = ?,
                report_json_path = ?, report_csv_path = ?, artifacts_dir = ?,
                frames_count_sent = ?, gemini_calls = ?, prompt_version = ?
                WHERE id = ?
                """,
                (
                    now_utc(),
                    "succeeded",
                    report_json_path,
                    report_csv_path,
                    artifacts_dir,
                    frames_count_sent,
                    gemini_calls,
                    prompt_version,
                    job_id,
                ),
            )

    def set_job_error(self, job_id: str, error_code: str, error_message: str) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs SET updated_at = ?, status = ?, error_code = ?, error_message = ?
                WHERE id = ?
                """,
                (now_utc(), "failed", error_code, error_message, job_id),
            )

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return job as dict compatible with JobRecord (input, status, progress, output, error, created_at, updated_at)."""
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, updated_at, status, mode, confidence_threshold,
                       video_path, metadata, progress_stage, progress_percent,
                       error_code, error_message, report_json_path, report_csv_path, artifacts_dir,
                       input_type, input_manifest_path, photos_dir
                FROM jobs WHERE id = ?
                """,
                (job_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        meta = _parse_metadata(getattr(row, "metadata", None))
        progress_stage = getattr(row, "progress_stage", None) or ""
        progress_percent = getattr(row, "progress_percent", None)
        if progress_percent is None:
            progress_percent = 0
        report_json = getattr(row, "report_json_path", None)
        report_csv = getattr(row, "report_csv_path", None)
        artifacts_dir = getattr(row, "artifacts_dir", None)
        output = None
        if report_json or report_csv or artifacts_dir:
            output = {
                "report_json_path": report_json,
                "report_csv_path": report_csv,
                "artifacts_dir": artifacts_dir,
            }
        code = getattr(row, "error_code", None)
        msg = getattr(row, "error_message", None)
        if code and msg:
            error_msg = f"{code}: {msg}"
        else:
            error_msg = msg or code
        input_type = getattr(row, "input_type", None) or "video"
        input_manifest_path = getattr(row, "input_manifest_path", None)
        photos_dir = getattr(row, "photos_dir", None)
        return {
            "job_id": row.id,
            "input": {
                "video_path": row.video_path or "",
                "mode": row.mode or "hybrid",
                "confidence_threshold": float(row.confidence_threshold or 0.70),
                "metadata": meta,
                "input_type": input_type,
                "input_manifest_path": input_manifest_path,
                "photos_dir": photos_dir,
            },
            "status": row.status,
            "progress": {"stage": progress_stage, "percent": progress_percent},
            "output": output,
            "error": error_msg,
            "created_at": _row_to_iso(row, "created_at"),
            "updated_at": _row_to_iso(row, "updated_at"),
        }


class PalletResultsRepository:
    """Bulk insert and read pallet_results."""

    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def insert_pallet_results(self, job_id: str, pallets: List[Any]) -> None:
        """Bulk insert. Each pallet: dict or object with pallet_id, internal_code, quantity/final_quantity, source, confidence, fallback_used, estimated_visible_boxes (optional)."""
        if not pallets:
            return
        now = now_utc()
        with self._client.cursor() as cur:
            for p in pallets:
                if isinstance(p, dict):
                    pallet_id = str(p.get("pallet_id", ""))
                    internal_code = p.get("internal_code")
                    final_quantity = p.get("final_quantity")
                    quantity = p.get("quantity")
                    quantity_to_store = final_quantity if final_quantity is not None else quantity
                    source = p.get("source", "unknown")
                    confidence = p.get("confidence")
                    fallback_used = bool(p.get("fallback_used", False))
                    raw_estimated_visible_boxes = p.get("estimated_visible_boxes")
                else:
                    pallet_id = str(getattr(p, "pallet_id", ""))
                    internal_code = getattr(p, "internal_code", None)
                    final_quantity = getattr(p, "final_quantity", None)
                    quantity = getattr(p, "quantity", None)
                    quantity_to_store = final_quantity if final_quantity is not None else quantity
                    source = getattr(p, "source", "unknown")
                    confidence = getattr(p, "confidence", None)
                    fallback_used = bool(getattr(p, "fallback_used", False))
                    raw_estimated_visible_boxes = getattr(p, "estimated_visible_boxes", None)
                cur.execute(
                    """
                    INSERT INTO pallet_results (job_id, pallet_id, internal_code, quantity, source, confidence, fallback_used, raw_estimated_visible_boxes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (job_id, pallet_id, internal_code, quantity_to_store, source, confidence, fallback_used, raw_estimated_visible_boxes, now),
                )

    def get_pallet_results(self, job_id: str) -> List[Dict[str, Any]]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT pallet_id, internal_code, quantity, source, confidence, fallback_used, raw_estimated_visible_boxes, created_at
                FROM pallet_results WHERE job_id = ? ORDER BY id
                """,
                (job_id,),
            )
            rows = cur.fetchall()
        out = []
        for row in rows:
            out.append({
                "pallet_id": row.pallet_id,
                "internal_code": row.internal_code,
                "quantity": row.quantity,
                "source": row.source,
                "confidence": row.confidence,
                "fallback_used": bool(row.fallback_used),
                "raw_estimated_visible_boxes": row.raw_estimated_visible_boxes,
                "created_at": _row_to_iso(row, "created_at"),
            })
        return out


class JobEventsRepository:
    """Append-only job_events."""

    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def insert_event(self, job_id: str, event_type: str, payload_dict: Optional[Dict[str, Any]] = None) -> None:
        payload = json.dumps(payload_dict, ensure_ascii=False) if payload_dict else None
        with self._client.cursor() as cur:
            cur.execute(
                "INSERT INTO job_events (job_id, [timestamp], event_type, payload) VALUES (?, ?, ?, ?)",
                (job_id, now_utc(), event_type, payload),
            )

    def get_events(self, job_id: str) -> List[Dict[str, Any]]:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT id, job_id, [timestamp], event_type, payload FROM job_events WHERE job_id = ? ORDER BY [timestamp]",
                (job_id,),
            )
            rows = cur.fetchall()
        out = []
        for row in rows:
            payload = _parse_metadata(row.payload) if getattr(row, "payload", None) else None
            out.append({
                "id": row.id,
                "job_id": row.job_id,
                "timestamp": _row_to_iso(row, "timestamp"),
                "event_type": row.event_type,
                "payload": payload,
            })
        return out
