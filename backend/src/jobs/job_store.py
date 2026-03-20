"""Stage 7 — Persist and load job records under output/<job_id>/.
Stage 8 — When SQL Server enabled, DB is source of truth; FS kept for artifacts and optional job.json.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import load_settings
from src.jobs.models import JobInput, JobRecord, JobStatus
from src.utils.validation import validate_job_id

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
    video_path: str = "",
    mode: str = "hybrid",
    confidence_threshold: float = 0.70,
    metadata: Optional[Dict[str, Any]] = None,
    video_filename: Optional[str] = None,
    input_type: str = "video",
    input_manifest_path: Optional[str] = None,
    photos_dir: Optional[str] = None,
) -> JobRecord:
    """Create job dir and job.json; when DB enabled, insert job row. Return record.
    Stage 2.2.A: for photos jobs, video_path='', input_type='photos', input_manifest_path and photos_dir set."""
    job_id = validate_job_id(job_id)
    from datetime import datetime
    now = datetime.utcnow().isoformat() + "Z"
    record = JobRecord(
        job_id=job_id,
        input=JobInput(
            video_path=video_path,
            mode=mode,
            confidence_threshold=confidence_threshold,
            metadata=metadata,
            input_type=input_type,
            input_manifest_path=input_manifest_path,
            photos_dir=photos_dir,
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
                video_filename=video_filename or (Path(video_path).name if video_path else None),
                metadata=metadata,
                engine_version=engine_version,
                input_type=input_type,
                input_manifest_path=input_manifest_path,
                photos_dir=photos_dir,
            )
        except Exception as e:
            logger.warning("DB create_job failed (FS record created): %s", e)
    return record


def get_job(base_path: Path, job_id: str) -> Optional[JobRecord]:
    """Load job record from DB when enabled, else from FS. Return None if not found."""
    job_id = validate_job_id(job_id)
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


def claim_next_job(base_path: Path) -> Optional[JobRecord]:
    """Claim next queued job from DB (preferred) or legacy in-memory queue.

    Production path: SQL-backed atomic claim from jobs table.
    Local legacy fallback (only when SQL mode is disabled): in-memory queue + get_job().
    """
    settings = load_settings()
    db_claim_configured = bool(
        getattr(settings, "sqlserver_enabled", False)
        and (getattr(settings, "sqlserver_connection_string", "") or "").strip()
    )
    # Preferred v3 source: inventory_jobs via v3 JobRepository claim.
    try:
        from src.runtime.v3_deps import get_job_repo

        v3_repo = get_job_repo()
        claim_v3 = getattr(v3_repo, "claim_next_queued_job", None)
        if callable(claim_v3):
            claimed_v3 = claim_v3()
            if claimed_v3 is not None:
                metadata = dict(claimed_v3.payload_json or {})
                metadata.setdefault("job_type", claimed_v3.job_type)
                metadata.setdefault("target_type", claimed_v3.target_type)
                metadata.setdefault("target_id", claimed_v3.target_id)
                return JobRecord(
                    job_id=claimed_v3.id,
                    input=JobInput(
                        video_path="",
                        mode="hybrid",
                        confidence_threshold=0.7,
                        metadata=metadata,
                    ),
                    status=JobStatus(claimed_v3.status.value),
                    progress={"stage": "claimed", "percent": 1},
                    output=None,
                    error=claimed_v3.error_message,
                    created_at=claimed_v3.created_at.isoformat(),
                    updated_at=claimed_v3.updated_at.isoformat(),
                )
    except Exception:
        logger.exception("v3 DB claim_next_queued_job failed while SQL worker mode is enabled")

    # Legacy DB source: jobs table (v2 compatibility only).
    repos = _db_repos()
    if repos is not None:
        jobs_repo, _, _ = repos
        try:
            data = jobs_repo.claim_next_queued_job()
            if data is None:
                return None
            return JobRecord.model_validate(data)
        except Exception:
            # Explicitly surface DB claim failures; do not mask as a normal idle poll.
            logger.exception("DB claim_next_queued_job failed while SQL worker mode is enabled")
            return None
    if db_claim_configured:
        # SQL mode is expected but claim infrastructure is unavailable.
        logger.error("SQL worker mode configured but DB repositories are unavailable; cannot claim queued jobs")
        return None

    # Legacy/local fallback only (non-distributed).
    try:
        from src.jobs.queue import dequeue

        job_id = dequeue(timeout=0.1)
        if not job_id:
            return None
        claimed = get_job(base_path, job_id)
        if claimed is None:
            logger.warning("Dequeued legacy job %s not found in store", job_id)
        return claimed
    except Exception as e:
        logger.warning("Legacy queue claim failed: %s", e)
        return None


def update_job(base_path: Path, job_id: str, **updates: object) -> Optional[JobRecord]:
    """Update job record; when DB enabled, push status/progress/error to DB (output paths and metrics are written by the worker via set_job_outputs, not here). Then persist to FS. Returns updated record or None."""
    job_id = validate_job_id(job_id)
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


def get_pallet_results(job_id: str) -> Optional[List[Dict[str, Any]]]:
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
    job_id = validate_job_id(job_id)
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
