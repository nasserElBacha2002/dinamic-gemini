"""Stage 7 — Persist and load job records under output/<job_id>/."""

import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from src.jobs.models import JobInput, JobRecord, JobStatus


def _job_dir(base: Path, job_id: str) -> Path:
    return base / job_id


def _job_file(base: Path, job_id: str) -> Path:
    return _job_dir(base, job_id) / "job.json"


def create_job(
    base_path: Path,
    job_id: str,
    video_path: str,
    mode: str = "legacy",
    confidence_threshold: float = 0.70,
    metadata: Optional[dict] = None,
) -> JobRecord:
    """Create job dir and job.json; return record."""
    from datetime import datetime
    now = datetime.utcnow().isoformat() + "Z"
    record = JobRecord(
        job_id=job_id,
        input=JobInput(
            video_path=video_path,
            mode=mode,
            confidence_threshold=confidence_threshold,
            metadata=metadata,
        ),
        status=JobStatus.QUEUED,
        progress={"stage": "", "percent": 0},
        output=None,
        error=None,
        created_at=now,
        updated_at=now,
    )
    job_dir = _job_dir(base_path, job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    _write_record(_job_file(base_path, job_id), record)
    return record


def get_job(base_path: Path, job_id: str) -> Optional[JobRecord]:
    """Load job record; return None if not found or invalid."""
    path = _job_file(base_path, job_id)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return JobRecord.model_validate(data)
    except Exception:
        return None


def update_job(base_path: Path, job_id: str, **updates: object) -> Optional[JobRecord]:
    """Update job record with given fields; persist atomically. Returns updated record or None."""
    record = get_job(base_path, job_id)
    if record is None:
        return None
    from datetime import datetime
    data = record.model_dump()
    for k, v in updates.items():
        if k in JobRecord.model_fields:
            data[k] = v
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    updated = JobRecord.model_validate(data)
    _write_record(_job_file(base_path, job_id), updated)
    return updated


def _write_record(path: Path, record: JobRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="job.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record.model_dump(), f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def list_artifacts(base_path: Path, job_id: str) -> List[str]:
    """List artifact filenames under output/<job_id>/ (sanitized; no path traversal)."""
    job_dir = _job_dir(base_path, job_id)
    if not job_dir.exists() or not job_dir.is_dir():
        return []
    out: List[str] = []
    try:
        for p in job_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(job_dir)
                parts = rel.parts
                if any(".." in part for part in parts):
                    continue
                out.append(str(rel))
    except ValueError:
        pass
    return sorted(out)
