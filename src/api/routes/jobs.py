"""Stage 7 — Job endpoints."""

import json
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from src.api.schemas.responses import (
    ArtifactItem,
    ArtifactsResponse,
    JobCreateResponse,
    JobStatusResponse,
)
from src.config import load_settings
from src.jobs.job_store import create_job, get_job, list_artifacts
from src.jobs.queue import enqueue

router = APIRouter(prefix="/api/v1/inventory/jobs", tags=["jobs"])


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
    """Get job status and progress."""
    base = _base_path()
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
    """Return authoritative report JSON if succeeded."""
    base = _base_path()
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
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@router.get("/{job_id}/artifacts", response_model=ArtifactsResponse)
async def get_job_artifacts(job_id: str) -> ArtifactsResponse:
    """List artifact filenames and relative paths."""
    base = _base_path()
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
