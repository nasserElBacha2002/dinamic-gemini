"""Stage 7 — Persist and load job records under output/<job_id>/.
Stage 8 — When SQL Server enabled, DB is source of truth; FS kept for artifacts and optional job.json.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Tuple

from src.jobs.models import JobInput, JobRecord, JobStatus

logger = logging.getLogger(__name__)


def _db_repos() -> Optional[Tuple[Any, Any, Any]]:
    """Return (jobs_repo, pallet_repo, events_repo) when SQL Server enabled and configured; else None."""
    try:
        from src.config import load_settings
        settings = load_settings()
        if not getattr(settings, "sqlserver_enabled", False) or not (getattr(settings, "sqlserver_connection_string", "") or "").strip():
            return None
        from src.database.sqlserver import SqlServerClient
        from src.database.repository import JobsRepository, PalletResultsRepository, JobEventsRepository
        client = SqlServerClient(settings.sqlserver_connection_string)
        return (
            JobsRepository(client),
            PalletResultsRepository(client),
            JobEventsRepository(client),
        )
    except Exception as e:
        logger.warning("SQL Server repos unavailable: %s", e)
        return None


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
    video_filename: Optional[str] = None,
) -> JobRecord:
    """Create job dir and job.json; when DB enabled, insert job row. Return record."""
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

    repos = _db_repos()
    if repos is not None:
        jobs_repo, _, _ = repos
        try:
            settings = __import__("src.config", fromlist=["load_settings"]).load_settings()
            engine_version = getattr(settings, "engine_version", "v2.0")
            jobs_repo.create_job(
                job_id=job_id,
                video_path=video_path,
                mode=mode,
                confidence_threshold=confidence_threshold,
                video_filename=video_filename or Path(video_path).name,
                metadata=metadata,
                engine_version=engine_version,
            )
        except Exception as e:
            logger.warning("DB create_job failed (FS record created): %s", e)
    return record


def get_job(base_path: Path, job_id: str) -> Optional[JobRecord]:
    """Load job record from DB when enabled, else from FS. Return None if not found."""
    repos = _db_repos()
    if repos is not None:
        jobs_repo, _, _ = repos
        try:
            data = jobs_repo.get_job(job_id)
            if data is not None:
                return JobRecord.model_validate(data)
        except Exception as e:
            logger.warning("DB get_job failed, falling back to FS: %s", e)
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
    """Update job record; when DB enabled, push status/progress/error to DB (output paths and metrics are written by the worker via set_job_outputs, not here). Then persist to FS. Returns updated record or None."""
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

    repos = _db_repos()
    if repos is not None:
        jobs_repo, _, _ = repos
        try:
            if "status" in updates:
                status_val = data.get("status")
                status_str = status_val.value if hasattr(status_val, "value") else str(status_val)
                progress = data.get("progress") or {}
                stage = progress.get("stage") if isinstance(progress, dict) else getattr(progress, "stage", None)
                percent = progress.get("percent") if isinstance(progress, dict) else getattr(progress, "percent", None)
                jobs_repo.update_job_status(job_id, status_str, progress_stage=stage, progress_percent=percent)
            elif "progress" in updates:
                progress = data.get("progress") or {}
                stage = progress.get("stage", "") if isinstance(progress, dict) else getattr(progress, "stage", "")
                percent = progress.get("percent", 0) if isinstance(progress, dict) else getattr(progress, "percent", 0)
                jobs_repo.update_job_progress(job_id, stage, percent)
            if "error" in updates and updates.get("error"):
                err = str(updates["error"])
                jobs_repo.set_job_error(job_id, "ERROR", err[:2048] if len(err) > 2048 else err)
        except Exception as e:
            logger.warning("DB update_job failed (FS updated): %s", e)

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


def get_pallet_results(job_id: str) -> Optional[List[dict]]:
    """When SQL Server enabled, return pallet_results for job_id from DB; else None (caller should use report file)."""
    repos = _db_repos()
    if repos is None:
        return None
    _, pallet_repo, _ = repos
    try:
        return pallet_repo.get_pallet_results(job_id)
    except Exception as e:
        logger.warning("DB get_pallet_results failed: %s", e)
        return None


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
