"""Stage 7 — Job endpoints. Stage 8 — DB as source of truth when sqlserver_enabled. Stage 2.2.A — video or photos input."""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request, UploadFile

from src.api.photos_handler import persist_photos_from_uploads
from src.review import load_reviews, merge_resolved_report
from src.api.schemas.responses import (
    ArtifactItem,
    ArtifactsResponse,
    JobCreateResponse,
    JobStatusResponse,
)
from src.config import load_settings
from src.jobs.job_store import create_job, get_job, list_artifacts
from src.jobs.queue import enqueue
from src.utils.validation import validate_job_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/inventory/jobs", tags=["jobs"])

_db_repos_cache: Optional[Tuple[Any, Any, Any]] = None


def _db_enabled(settings: Any) -> bool:
    return bool(
        getattr(settings, "sqlserver_enabled", False)
        and (getattr(settings, "sqlserver_connection_string", "") or "").strip()
    )


def _get_db_repos() -> Optional[Tuple[Any, Any, Any]]:
    """Lazy init: (JobsRepository, PalletResultsRepository, JobEventsRepository) when DB enabled."""
    global _db_repos_cache
    if _db_repos_cache is not None:
        return _db_repos_cache
    settings = load_settings()
    if not _db_enabled(settings):
        return None
    try:
        from src.database.sqlserver import SqlServerClient
        from src.database.repository import JobsRepository, PalletResultsRepository, JobEventsRepository
        client = SqlServerClient(settings.sqlserver_connection_string)
        _db_repos_cache = (
            JobsRepository(client),
            PalletResultsRepository(client),
            JobEventsRepository(client),
        )
        return _db_repos_cache
    except Exception as e:
        logger.warning("DB repos init failed: %s", e)
        return None


def _base_path() -> Path:
    return Path(load_settings().output_dir)


def _job_id() -> str:
    return f"job_{uuid.uuid4().hex[:16]}"


async def _save_upload_streaming(
    upload: UploadFile,
    dst_path: Path,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> int:
    """Stream UploadFile to dst_path. Returns bytes written. Enforces max_bytes. Raises HTTPException(413) if exceeded."""
    written = 0
    try:
        with open(dst_path, "wb") as f:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                if written + len(chunk) > max_bytes:
                    raise HTTPException(
                        413,
                        f"File exceeds {max_bytes // (1024 * 1024)} MB limit",
                    )
                f.write(chunk)
                written += len(chunk)
        return written
    except HTTPException:
        if dst_path.exists():
            dst_path.unlink(missing_ok=True)
        raise
    except Exception:
        if dst_path.exists():
            dst_path.unlink(missing_ok=True)
        raise


async def _create_job_video(
    video: UploadFile,
    mode: str,
    confidence_threshold: float,
    meta: Optional[dict],
    settings: Any,
    base: Path,
    job_id: str,
) -> JobCreateResponse:
    """Create job from multipart video upload (existing behavior)."""
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    job_dir = base / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    input_dir = job_dir / "input"
    input_dir.mkdir(exist_ok=True)
    video_filename = (video.filename or "video.mp4").strip()
    if not video_filename or "/" in video_filename or "\\" in video_filename:
        video_filename = "video.mp4"
    else:
        video_filename = Path(video_filename).name
    video_path = input_dir / video_filename
    await _save_upload_streaming(video, video_path, max_bytes)
    create_job(
        base,
        job_id,
        video_path=str(video_path),
        mode=mode,
        confidence_threshold=confidence_threshold,
        metadata=meta,
        video_filename=video_filename,
        input_type="video",
    )
    enqueue(job_id)
    return JobCreateResponse(
        job_id=job_id,
        status="queued",
        mode=mode,
        confidence_threshold=confidence_threshold,
    )


async def _create_job_photos_form(
    form: Any,
    settings: Any,
    base: Path,
    job_id: str,
) -> JobCreateResponse:
    """Create job from multipart form with input_type=photos and multiple 'photos' files."""
    if not getattr(settings, "enable_photos_input", True):
        raise HTTPException(422, "photos input is disabled (ENABLE_PHOTOS_INPUT=false)")
    mode = form.get("mode", "hybrid")
    if isinstance(mode, bytes):
        mode = mode.decode("utf-8", errors="replace")
    mode = (mode or "hybrid").strip()
    if mode == "legacy":
        raise HTTPException(422, "legacy mode has been removed as of v2.2; use mode='hybrid'.")
    if mode != "hybrid":
        raise HTTPException(422, "mode must be 'hybrid'")
    ct = form.get("confidence_threshold", 0.70)
    if isinstance(ct, (bytes, str)):
        try:
            confidence_threshold = float(ct)
        except (TypeError, ValueError):
            confidence_threshold = 0.70
    else:
        confidence_threshold = float(ct) if ct is not None else 0.70
    if not (0.0 <= confidence_threshold <= 1.0):
        raise HTTPException(422, "confidence_threshold must be between 0 and 1")
    metadata_raw = form.get("metadata")
    meta = None
    if metadata_raw is not None and str(metadata_raw).strip():
        try:
            meta = json.loads(metadata_raw if isinstance(metadata_raw, str) else metadata_raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise HTTPException(422, f"metadata must be valid JSON: {e}") from e

    photos_list = form.getlist("photos")
    uploads = [p for p in photos_list if hasattr(p, "read") and callable(getattr(p, "read"))]
    if not uploads:
        raise HTTPException(422, "at least one photo file is required (field 'photos')")
    max_photos = getattr(settings, "max_photos_per_job", 12)
    if len(uploads) > max_photos:
        raise HTTPException(422, f"too many photos: {len(uploads)} (max {max_photos})")
    max_total_bytes = getattr(settings, "photos_max_total_bytes", 25 * 1024 * 1024)

    job_dir = base / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        _manifest, input_manifest_path, photos_dir = await persist_photos_from_uploads(
            job_dir, uploads, max_total_bytes
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    create_job(
        base,
        job_id,
        video_path="",
        mode=mode,
        confidence_threshold=confidence_threshold,
        metadata=meta,
        video_filename=None,
        input_type="photos",
        input_manifest_path=input_manifest_path,
        photos_dir=photos_dir,
    )
    enqueue(job_id)
    return JobCreateResponse(
        job_id=job_id,
        status="queued",
        mode=mode,
        confidence_threshold=confidence_threshold,
    )


@router.post("", response_model=JobCreateResponse, status_code=202)
async def create_inventory_job(request: Request) -> JobCreateResponse:
    """Create job from video or photos (both via multipart/form-data). Returns 202 with job_id."""
    content_type = (request.headers.get("content-type") or "").strip().lower()
    if "multipart/form-data" not in content_type:
        raise HTTPException(415, "content-type must be multipart/form-data")

    form = await request.form()
    input_type_raw = form.get("input_type")
    if isinstance(input_type_raw, bytes):
        input_type_raw = input_type_raw.decode("utf-8", errors="replace")
    input_type = (input_type_raw or "").strip().lower()

    if input_type == "photos":
        settings = load_settings()
        job_id = _job_id()
        base = _base_path()
        return await _create_job_photos_form(form, settings, base, job_id)

    # Video (default): require 'video' file
    video = form.get("video")
    if video is None:
        raise HTTPException(422, "video file is required (field 'video'); for photos use input_type=photos and field 'photos'")
    if not hasattr(video, "read") or not callable(getattr(video, "read")):
        raise HTTPException(422, "video must be a file upload")
    mode = form.get("mode", "hybrid")
    if isinstance(mode, bytes):
        mode = mode.decode("utf-8", errors="replace")
    mode = (mode or "hybrid").strip()
    if mode == "legacy":
        raise HTTPException(422, "legacy mode has been removed as of v2.2; use mode='hybrid'.")
    if mode != "hybrid":
        raise HTTPException(422, "mode must be 'hybrid'")
    ct = form.get("confidence_threshold", 0.70)
    if isinstance(ct, (bytes, str)):
        try:
            confidence_threshold = float(ct)
        except (TypeError, ValueError):
            confidence_threshold = 0.70
    else:
        confidence_threshold = float(ct) if ct is not None else 0.70
    metadata_raw = form.get("metadata")
    meta = None
    if metadata_raw is not None and str(metadata_raw).strip():
        try:
            meta = json.loads(metadata_raw if isinstance(metadata_raw, str) else metadata_raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise HTTPException(422, f"metadata must be valid JSON: {e}") from e
    if not (0.0 <= confidence_threshold <= 1.0):
        raise HTTPException(422, "confidence_threshold must be between 0 and 1")
    settings = load_settings()
    job_id = _job_id()
    base = _base_path()
    return await _create_job_video(video, mode, confidence_threshold, meta, settings, base, job_id)


def _parse_iso_to_timestamp(iso_str: str) -> Optional[float]:
    """Parse ISO 8601 string to Unix timestamp (seconds). Returns None on parse error."""
    if not iso_str:
        return None
    try:
        from datetime import datetime, timezone
        s = (iso_str or "").strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _execution_time_seconds(created_at: str, updated_at: str, status: str) -> Optional[float]:
    """Return execution duration in seconds when job has finished (succeeded/failed)."""
    if status not in ("succeeded", "failed"):
        return None
    t0 = _parse_iso_to_timestamp(created_at)
    t1 = _parse_iso_to_timestamp(updated_at)
    if t0 is None or t1 is None or t1 < t0:
        return None
    return round(t1 - t0, 2)


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get job status and progress. When DB enabled, read from JobsRepository."""
    try:
        job_id = validate_job_id(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    base = _base_path()
    repos = _get_db_repos()
    if repos is not None:
        jobs_repo, _, _ = repos
        try:
            data = jobs_repo.get_job(job_id)
            if data is not None:
                status = data.get("status", "queued")
                status_str = status if isinstance(status, str) else getattr(status, "value", str(status))
                progress = data.get("progress") or {"stage": "", "percent": 0}
                created_at = data.get("created_at", "")
                updated_at = data.get("updated_at", "")
                return JobStatusResponse(
                    job_id=data.get("job_id", job_id),
                    status=status_str,
                    progress=progress,
                    created_at=created_at,
                    execution_time_seconds=_execution_time_seconds(created_at, updated_at, status_str),
                )
        except Exception as e:
            logger.debug("DB path failed for get_job_status, using FS: %s", e)
    record = get_job(base, job_id)
    if record is None:
        raise HTTPException(404, "Job not found")
    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status.value,
        progress=_progress_dict(record),
        created_at=record.created_at,
        execution_time_seconds=_execution_time_seconds(record.created_at, record.updated_at, record.status.value),
    )


def _merge_report_metadata(report: dict, job_id: str, status: str, mode: str, confidence_threshold: float) -> dict:
    """Merge job metadata into report. Prefer report['mode'] when present (e.g. hybrid_v2.1)."""
    out = dict(report)
    out["job_id"] = job_id
    out["status"] = status
    out["mode"] = report.get("mode") or mode
    out["confidence_threshold"] = confidence_threshold
    return out


def _resolve_report_and_run_dir(job_id: str) -> Tuple[Path, Path]:
    """Return (report_path, run_dir) for a succeeded job. Raises HTTPException 404/409 if not found or not succeeded."""
    base = _base_path()
    repos = _get_db_repos()
    if repos is not None:
        jobs_repo, _, _ = repos
        try:
            job_data = jobs_repo.get_job(job_id)
            if job_data is None:
                raise HTTPException(404, "Job not found")
            status = job_data.get("status", "")
            status_str = status if isinstance(status, str) else getattr(status, "value", str(status))
            if status_str != "succeeded":
                raise HTTPException(409, f"Job not succeeded (status={status_str})")
            out = job_data.get("output")
            if not out:
                raise HTTPException(404, "No result")
            report_path = out.get("report_json_path") if isinstance(out, dict) else getattr(out, "report_json_path", None)
            if not report_path:
                raise HTTPException(404, "Report path not set")
            path = Path(report_path)
            if not path.exists():
                raise HTTPException(404, "Report file not found")
            return (path, path.parent)
        except HTTPException:
            raise
        except Exception as e:
            logger.debug("DB path failed for _resolve_report_and_run_dir: %s", e)
    record = get_job(base, job_id)
    if record is None:
        raise HTTPException(404, "Job not found")
    if record.status.value != "succeeded":
        raise HTTPException(409, f"Job not succeeded (status={record.status.value})")
    out = record.output
    if not out:
        raise HTTPException(404, "No result")
    report_path = getattr(out, "report_json_path", None) if out is not None else None
    if report_path is None and isinstance(out, dict):
        report_path = out.get("report_json_path")
    if not report_path:
        raise HTTPException(404, "Report path not set")
    path = Path(report_path)
    if not path.exists():
        raise HTTPException(404, "Report file not found")
    return (path, path.parent)


def _job_input_from_record_or_data(record: Optional[Any], job_data: Optional[dict]) -> dict:
    """Get mode and confidence_threshold from JobRecord or DB job_data."""
    if record is not None:
        return {"mode": record.input.mode, "confidence_threshold": record.input.confidence_threshold}
    if job_data:
        inp = job_data.get("input") or {}
        return {"mode": inp.get("mode", "hybrid_v2.1"), "confidence_threshold": inp.get("confidence_threshold", 0.70)}
    return {"mode": "hybrid_v2.1", "confidence_threshold": 0.70}


@router.get("/{job_id}/result")
async def get_job_result(job_id: str) -> Any:
    """Return authoritative report JSON if succeeded. Report file is the source of truth (standard v2.1 format)."""
    try:
        job_id = validate_job_id(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    report_path, _run_dir = _resolve_report_and_run_dir(job_id)
    record = get_job(_base_path(), job_id)
    job_data = None
    if _get_db_repos() is not None:
        try:
            job_data = _get_db_repos()[0].get_job(job_id) if _get_db_repos() else None
        except Exception:
            pass
    inp = _job_input_from_record_or_data(record, job_data)
    with open(report_path, encoding="utf-8") as f:
        data = json.load(f)
    return _merge_report_metadata(
        data,
        job_id,
        "succeeded",
        inp["mode"],
        inp["confidence_threshold"],
    )


@router.get("/{job_id}/report")
async def get_job_report(job_id: str, resolved: bool = False) -> Any:
    """Return report JSON. When resolved=true, merge with reviews and recompute summary (does not modify file)."""
    try:
        job_id = validate_job_id(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    report_path, run_dir = _resolve_report_and_run_dir(job_id)
    record = get_job(_base_path(), job_id)
    job_data = None
    if _get_db_repos() is not None:
        try:
            job_data = _get_db_repos()[0].get_job(job_id) if _get_db_repos() else None
        except Exception:
            pass
    inp = _job_input_from_record_or_data(record, job_data)
    with open(report_path, encoding="utf-8") as f:
        data = json.load(f)
    if not resolved:
        return _merge_report_metadata(
            data,
            job_id,
            "succeeded",
            inp["mode"],
            inp["confidence_threshold"],
        )
    reviews = load_reviews(run_dir)
    merged = merge_resolved_report(data, reviews)
    return _merge_report_metadata(
        merged,
        job_id,
        "succeeded",
        inp["mode"],
        inp["confidence_threshold"],
    )


def _list_artifacts_under(job_dir: Path) -> list:
    """List relative paths of files under job_dir (no path traversal)."""
    if not job_dir.exists() or not job_dir.is_dir():
        return []
    out = []
    try:
        for p in job_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(job_dir)
                if any(".." in part for part in rel.parts):
                    continue
                out.append(str(rel))
    except ValueError:
        pass
    return sorted(out)


@router.get("/{job_id}/artifacts", response_model=ArtifactsResponse)
async def get_job_artifacts(job_id: str) -> ArtifactsResponse:
    """List artifact filenames and relative paths. When DB enabled, use artifacts_dir from DB if set."""
    try:
        job_id = validate_job_id(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    base = _base_path()
    repos = _get_db_repos()
    if repos is not None:
        jobs_repo, _, _ = repos
        try:
            job_data = jobs_repo.get_job(job_id)
            if job_data is not None:
                out = job_data.get("output")
                artifacts_dir = (out.get("artifacts_dir") if isinstance(out, dict) else getattr(out, "artifacts_dir", None)) if out else None
                job_dir = Path(artifacts_dir) if artifacts_dir else base / job_id
                names = _list_artifacts_under(job_dir)
                return ArtifactsResponse(job_id=job_id, artifacts=[ArtifactItem(name=n, path=n) for n in names])
        except Exception as e:
            logger.debug("DB path failed for get_job_artifacts, using FS: %s", e)
    record = get_job(base, job_id)
    if record is None:
        raise HTTPException(404, "Job not found")
    names = list_artifacts(base, job_id)
    items = [ArtifactItem(name=n, path=n) for n in names]
    return ArtifactsResponse(job_id=job_id, artifacts=items)


def _progress_dict(record: Any) -> dict:
    p = record.progress
    if hasattr(p, "model_dump"):
        return p.model_dump()
    return dict(p) if isinstance(p, dict) else {"stage": "", "percent": 0}
