"""Stage 7 — Job endpoints. Stage 8 — DB as source of truth when sqlserver_enabled."""

import json
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from src.api.schemas.responses import (
    ArtifactItem,
    ArtifactsResponse,
    JobCreateResponse,
    JobStatusResponse,
)
from src.config import load_settings
from src.jobs.job_store import create_job, get_job, get_pallet_results, list_artifacts
from src.jobs.queue import enqueue

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
    except Exception:
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


@router.post("", response_model=JobCreateResponse, status_code=202)
async def create_inventory_job(
    video: UploadFile = File(..., description="Video file"),
    mode: str = Form("legacy"),
    confidence_threshold: float = Form(0.70),
    metadata: Optional[str] = Form(None),
) -> JobCreateResponse:
    """Upload video and create an async job. Returns 202 with job_id."""
    if mode not in ("legacy", "hybrid"):
        raise HTTPException(422, "mode must be 'legacy' or 'hybrid'")
    if not (0.0 <= confidence_threshold <= 1.0):
        raise HTTPException(422, "confidence_threshold must be between 0 and 1")
    if metadata is not None and metadata.strip():
        try:
            meta = json.loads(metadata)
        except json.JSONDecodeError as e:
            raise HTTPException(422, f"metadata must be valid JSON: {e}") from e
    else:
        meta = None

    settings = load_settings()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    job_id = _job_id()
    base = _base_path()
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
    )
    enqueue(job_id)
    return JobCreateResponse(
        job_id=job_id,
        status="queued",
        mode=mode,
        confidence_threshold=confidence_threshold,
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get job status and progress. When DB enabled, read from JobsRepository."""
    base = _base_path()
    repos = _get_db_repos()
    if repos is not None:
        jobs_repo, _, _ = repos
        try:
            data = jobs_repo.get_job(job_id)
            if data is not None:
                status = data.get("status", "queued")
                progress = data.get("progress") or {"stage": "", "percent": 0}
                return JobStatusResponse(
                    job_id=data.get("job_id", job_id),
                    status=status if isinstance(status, str) else getattr(status, "value", str(status)),
                    progress=progress,
                    created_at=data.get("created_at", ""),
                )
        except Exception:
            pass
    record = get_job(base, job_id)
    if record is None:
        raise HTTPException(404, "Job not found")
    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status.value,
        progress=_progress_dict(record),
        created_at=record.created_at,
    )


@router.get("/{job_id}/result")
async def get_job_result(job_id: str) -> Any:
    """Return authoritative report JSON if succeeded. When DB enabled, build from job + pallet_results."""
    base = _base_path()
    repos = _get_db_repos()
    if repos is not None:
        jobs_repo, pallet_repo, _ = repos
        try:
            job_data = jobs_repo.get_job(job_id)
            if job_data is not None:
                status = job_data.get("status", "")
                status_str = status if isinstance(status, str) else getattr(status, "value", str(status))
                if status_str != "succeeded":
                    raise HTTPException(409, f"Job not succeeded (status={status_str})")
                out = job_data.get("output")
                if not out:
                    raise HTTPException(404, "No result")
                pallets_data = pallet_repo.get_pallet_results(job_id)
                input_data = job_data.get("input") or {}
                report = {
                    "job_id": job_id,
                    "status": status_str,
                    "mode": input_data.get("mode", "legacy"),
                    "confidence_threshold": input_data.get("confidence_threshold", 0.70),
                    "total_pallets_detected": len(pallets_data),
                    "pallets": [
                        {
                            "pallet_id": p.get("pallet_id"),
                            "internal_code": p.get("internal_code"),
                            "quantity": p.get("quantity"),
                            "source": p.get("source"),
                            "confidence": p.get("confidence"),
                            "fallback_used": p.get("fallback_used", False),
                            "estimated_visible_boxes": p.get("raw_estimated_visible_boxes"),
                        }
                        for p in pallets_data
                    ],
                }
                report_json_path = out.get("report_json_path") if isinstance(out, dict) else getattr(out, "report_json_path", None)
                if report_json_path and Path(report_json_path).exists():
                    try:
                        with open(report_json_path, encoding="utf-8") as f:
                            file_report = json.load(f)
                        report["video"] = file_report.get("video")
                        report["prompt_version"] = file_report.get("prompt_version")
                        report["frames_selected"] = file_report.get("frames_selected")
                        report["flags"] = file_report.get("flags", {})
                        report["metrics"] = file_report.get("metrics")
                    except Exception:
                        pass
                return report
        except HTTPException:
            raise
        except Exception:
            pass

    record = get_job(base, job_id)
    if record is None:
        raise HTTPException(404, "Job not found")
    if record.status.value != "succeeded":
        raise HTTPException(409, f"Job not succeeded (status={record.status.value})")
    out = record.output
    if not out:
        raise HTTPException(404, "No result")

    pallets_data = get_pallet_results(job_id)
    if pallets_data is not None:
        report_json_path = getattr(out, "report_json_path", None) if out is not None else None
        if report_json_path is None and isinstance(out, dict):
            report_json_path = out.get("report_json_path")
        report = {
            "mode": record.input.mode,
            "confidence_threshold": record.input.confidence_threshold,
            "total_pallets_detected": len(pallets_data),
            "pallets": [
                {
                    "pallet_id": p.get("pallet_id"),
                    "internal_code": p.get("internal_code"),
                    "quantity": p.get("quantity"),
                    "source": p.get("source"),
                    "confidence": p.get("confidence"),
                    "fallback_used": p.get("fallback_used", False),
                    "estimated_visible_boxes": p.get("raw_estimated_visible_boxes"),
                }
                for p in pallets_data
            ],
        }
        if report_json_path and Path(report_json_path).exists():
            try:
                with open(report_json_path, encoding="utf-8") as f:
                    file_report = json.load(f)
                report["video"] = file_report.get("video")
                report["prompt_version"] = file_report.get("prompt_version")
                report["frames_selected"] = file_report.get("frames_selected")
                report["flags"] = file_report.get("flags", {})
                report["metrics"] = file_report.get("metrics")
            except Exception:
                pass
        return report

    report_path = getattr(out, "report_json_path", None) if out is not None else None
    if report_path is None and isinstance(out, dict):
        report_path = out.get("report_json_path")
    if not report_path:
        raise HTTPException(404, "Report path not set")
    path = Path(report_path)
    if not path.exists():
        raise HTTPException(404, "Report file not found")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
        except Exception:
            pass
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
