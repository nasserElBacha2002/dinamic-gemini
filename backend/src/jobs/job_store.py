"""Stage 7 — Persist and load job records under output/<job_id>/.
Stage 8 — When SQL Server enabled, DB is source of truth; FS kept for artifacts and optional job.json.

**Legacy SQL bridge:** when SQL Server is enabled, this module instantiates
``JobsRepository`` / ``PalletResultsRepository`` / ``JobEventsRepository`` from
``src.database.repository`` (tables ``jobs``, ``pallet_results``, ``job_events``).
That path is not the v3 ``inventory_jobs`` model; access is logged under logger ``dinamic.legacy_sql``.
"""

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional, cast

from src.config import load_settings
from src.jobs.claim_cycle import (
    LegacyBridgeMode,
    WorkerClaimCycleResult,
    WorkerClaimCycleStatus,
    resolve_legacy_bridge_mode,
)
from src.jobs.models import JobInput, JobProgress, JobRecord, JobStatus
from src.jobs.worker_runtime import (
    REASON_LEGACY_CLAIM_FAILED,
    REASON_MEMORY_QUEUE_FAILED,
    REASON_REPOSITORIES_NOT_INITIALIZED,
    REASON_V3_JOB_REPOSITORY_UNAVAILABLE,
)
from src.utils.validation import validate_job_id

logger = logging.getLogger(__name__)

# Rate-limit exception traces for claim failures (first + interval).
_CLAIM_FAIL_LOG_INTERVAL_SEC = 30.0
_claim_fail_log_lock = threading.Lock()
_last_claim_fail_log_monotonic = 0.0

# Throttle stale reclaim across polls (thread-safe; does not block recovery after timeout).
_stale_reclaim_lock = threading.Lock()
_last_stale_reclaim_monotonic = 0.0
_DEFAULT_STALE_RECLAIM_INTERVAL_SEC = 5.0


def _log_claim_source_failure(message: str, exc: BaseException) -> None:
    """First failure gets traceback; repeats are rate-limited without full traceback spam."""
    global _last_claim_fail_log_monotonic
    with _claim_fail_log_lock:
        now = time.monotonic()
        first_or_due = (
            _last_claim_fail_log_monotonic == 0.0
            or (now - _last_claim_fail_log_monotonic) >= _CLAIM_FAIL_LOG_INTERVAL_SEC
        )
        if first_or_due:
            _last_claim_fail_log_monotonic = now
            logger.exception("%s", message)
        else:
            logger.error("%s error_type=%s", message, type(exc).__name__)


def reset_claim_throttle_for_tests() -> None:
    """Clear claim/reclaim throttle state between unit tests."""
    global _last_claim_fail_log_monotonic, _last_stale_reclaim_monotonic
    with _claim_fail_log_lock:
        _last_claim_fail_log_monotonic = 0.0
    with _stale_reclaim_lock:
        _last_stale_reclaim_monotonic = 0.0


def _sqlserver_effective_cs(settings: object) -> str:
    """Compatibility shim: real :class:`~src.config.AppSettings` exposes ``sqlserver_effective_connection_string`` as a property; some tests use ``types.SimpleNamespace`` with only ``sqlserver_connection_string`` set."""
    eff = getattr(settings, "sqlserver_effective_connection_string", None)
    if eff is not None:
        return str(eff).strip()
    return (getattr(settings, "sqlserver_connection_string", "") or "").strip()


def _db_repos() -> Optional[tuple[Any, Any, Any]]:
    """Return (jobs_repo, pallet_repo, events_repo) when SQL Server enabled and configured; else None."""
    try:
        settings = load_settings()
        if not getattr(settings, "sqlserver_enabled", False) or not _sqlserver_effective_cs(
            settings
        ):
            return None
        if getattr(settings, "legacy_stage8_sql_bridge_disabled", False):
            from src.legacy.persistence_observability import (
                log_legacy_sql_bridge_bypassed_once_per_process,
            )

            log_legacy_sql_bridge_bypassed_once_per_process(
                reason="LEGACY_STAGE8_SQL_BRIDGE_DISABLED",
            )
            return None
        from src.database.repository import (
            JobEventsRepository,
            JobsRepository,
            PalletResultsRepository,
        )
        from src.database.sqlserver import SqlServerClient
        from src.legacy.persistence_observability import (
            log_legacy_sql_repositories_materialized_once_per_process,
        )

        client = SqlServerClient(settings.require_sqlserver_connection_string())
        log_legacy_sql_repositories_materialized_once_per_process(source="job_store._db_repos")
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
    metadata: Optional[dict[str, Any]] = None,
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
        progress=JobProgress(stage="", percent=0),
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
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logger.debug("get_job: unreadable job.json (job_id=%s): %s", job_id, e)
        return None
    except Exception as e:
        logger.warning("get_job: failed to parse JobRecord from FS (job_id=%s): %s", job_id, e)
        return None


def _job_record_from_v3_claimed(claimed_v3: Any) -> JobRecord:
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
        progress=JobProgress(stage="claimed", percent=1),
        output=None,
        error=claimed_v3.error_message,
        created_at=claimed_v3.created_at.isoformat(),
        updated_at=claimed_v3.updated_at.isoformat(),
    )


def _try_claim_v3_job(settings: object) -> tuple[bool, Optional[JobRecord]]:
    """Attempt v3 ``inventory_jobs`` claim.

    Returns ``(claim_path_available, job_or_none)``. ``job_or_none is None`` with
    ``claim_path_available True`` means a successful idle poll (no queued jobs).
    """
    from src.runtime.v3_deps import get_job_repo

    v3_repo = get_job_repo()
    stale_timeout_sec = int(getattr(settings, "worker_stale_running_timeout_sec", 0) or 0)
    reclaim_stale = getattr(v3_repo, "reclaim_stale_running_jobs", None)
    if callable(reclaim_stale) and stale_timeout_sec > 0:
        interval = float(
            getattr(
                settings,
                "worker_stale_reclaim_interval_sec",
                _DEFAULT_STALE_RECLAIM_INTERVAL_SEC,
            )
            or _DEFAULT_STALE_RECLAIM_INTERVAL_SEC
        )
        global _last_stale_reclaim_monotonic
        should_reclaim = False
        with _stale_reclaim_lock:
            now = time.monotonic()
            if (
                _last_stale_reclaim_monotonic == 0.0
                or (now - _last_stale_reclaim_monotonic) >= interval
            ):
                _last_stale_reclaim_monotonic = now
                should_reclaim = True
        if should_reclaim:
            reclaimed = int(reclaim_stale(stale_timeout_sec) or 0)
            if reclaimed > 0:
                logger.warning(
                    "Reclaimed stale RUNNING v3 jobs before claim: count=%s timeout_sec=%s",
                    reclaimed,
                    stale_timeout_sec,
                )
    claim_v3 = getattr(v3_repo, "claim_next_queued_job", None)
    if not callable(claim_v3):
        return False, None
    claimed_v3 = claim_v3()
    if claimed_v3 is None:
        return True, None
    return True, _job_record_from_v3_claimed(claimed_v3)


def claim_next_job_cycle(base_path: Path) -> WorkerClaimCycleResult:
    """One worker poll with an explicit cycle status (claimed / idle / unavailable).

    Pure data access: does **not** mutate :class:`~src.jobs.worker_runtime.EmbeddedWorkerRuntime`.
    ``worker_loop`` interprets the result and applies readiness transitions.

    Contract (SQL mode):
    - v3 claim with a job → ``JOB_CLAIMED``.
    - v3 idle + ``LegacyBridgeMode.DISABLED`` → ``IDLE_HEALTHY`` (bridge not consulted).
    - v3 idle + ``LegacyBridgeMode.DRAIN_REQUIRED`` → consult legacy ``jobs``;
      failure → ``CLAIM_UNAVAILABLE`` (never idle-healthy).
    - Missing/broken v3 claim path with SQL required → ``CLAIM_UNAVAILABLE``.
    """
    settings = load_settings()
    sql_mode = bool(
        getattr(settings, "sqlserver_enabled", False) and _sqlserver_effective_cs(settings)
    )
    bridge_mode = resolve_legacy_bridge_mode(settings)
    v3_claim_available = False
    v3_idle_healthy = False

    try:
        v3_claim_available, claimed = _try_claim_v3_job(settings)
        if claimed is not None:
            return WorkerClaimCycleResult(
                status=WorkerClaimCycleStatus.JOB_CLAIMED,
                job=claimed,
                detail="v3_inventory_jobs",
            )
        if v3_claim_available:
            if sql_mode:
                v3_idle_healthy = True
            # Non-SQL mode: continue to in-memory queue even if a v3 repo exists.
    except Exception as exc:
        v3_claim_available = False
        if sql_mode:
            _log_claim_source_failure(
                "v3 DB claim_next_queued_job failed while SQL worker mode is enabled",
                exc,
            )
            return WorkerClaimCycleResult(
                status=WorkerClaimCycleStatus.CLAIM_UNAVAILABLE,
                detail=REASON_V3_JOB_REPOSITORY_UNAVAILABLE,
                error_type=type(exc).__name__,
            )
        logger.exception("v3 DB claim_next_queued_job failed while SQL worker mode is enabled")

    # Legacy Stage-8 ``jobs``: only when SQL mode is on and bridge is DRAIN_REQUIRED.
    if sql_mode and bridge_mode is LegacyBridgeMode.DRAIN_REQUIRED:
        repos = _db_repos()
        if repos is None:
            if v3_idle_healthy:
                # Bridge required but repos could not be built (misconfig / missing schema).
                return WorkerClaimCycleResult(
                    status=WorkerClaimCycleStatus.CLAIM_UNAVAILABLE,
                    detail=REASON_LEGACY_CLAIM_FAILED,
                )
        else:
            jobs_repo, _, _ = repos
            try:
                data = jobs_repo.claim_next_queued_job()
                if data is None:
                    return WorkerClaimCycleResult(
                        status=WorkerClaimCycleStatus.IDLE_HEALTHY,
                        detail=(
                            "v3_idle_legacy_idle" if v3_idle_healthy else "legacy_jobs_idle"
                        ),
                    )
                return WorkerClaimCycleResult(
                    status=WorkerClaimCycleStatus.JOB_CLAIMED,
                    job=JobRecord.model_validate(data),
                    detail="legacy_stage8_jobs",
                )
            except Exception as exc:
                _log_claim_source_failure(
                    "DB claim_next_queued_job failed while SQL worker mode is enabled",
                    exc,
                )
                return WorkerClaimCycleResult(
                    status=WorkerClaimCycleStatus.CLAIM_UNAVAILABLE,
                    detail=REASON_LEGACY_CLAIM_FAILED,
                    error_type=type(exc).__name__,
                )

    if v3_idle_healthy:
        return WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.IDLE_HEALTHY,
            detail="v3_inventory_jobs_idle",
        )

    if sql_mode:
        reason = (
            REASON_V3_JOB_REPOSITORY_UNAVAILABLE
            if not v3_claim_available
            else REASON_REPOSITORIES_NOT_INITIALIZED
        )
        return WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.CLAIM_UNAVAILABLE,
            detail=reason,
        )

    try:
        from src.jobs.queue import dequeue

        job_id = dequeue(timeout=0.1)
        if not job_id:
            return WorkerClaimCycleResult(
                status=WorkerClaimCycleStatus.IDLE_HEALTHY,
                detail="memory_queue_idle",
            )
        claimed = get_job(base_path, job_id)
        if claimed is None:
            logger.warning("Dequeued legacy job %s not found in store", job_id)
            return WorkerClaimCycleResult(
                status=WorkerClaimCycleStatus.IDLE_HEALTHY,
                detail="memory_queue_missing_record",
            )
        return WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.JOB_CLAIMED,
            job=claimed,
            detail="memory_queue",
        )
    except Exception as e:
        logger.warning("Legacy queue claim failed: %s", e)
        return WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.CLAIM_UNAVAILABLE,
            detail=REASON_MEMORY_QUEUE_FAILED,
            error_type=type(e).__name__,
        )


def claim_next_job(base_path: Path) -> Optional[JobRecord]:
    """Legacy thin wrapper: return only ``.job`` from :func:`claim_next_job_cycle`.

    **Call sites (as of Stage-1 corrections):** unit tests under ``tests/jobs/``
    that have not yet migrated to the typed cycle. The primary ``worker_loop``
    must **not** use this helper — ``CLAIM_UNAVAILABLE`` would otherwise collapse
    to ``None`` and look like idle.

    **Removal plan:** migrate remaining tests to ``claim_next_job_cycle`` /
    ``worker_loop``, then delete this wrapper. Do not add new production callers.
    """
    return claim_next_job_cycle(base_path).job


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
                if status_val is None:
                    status_str = JobStatus.QUEUED.value
                elif hasattr(status_val, "value"):
                    status_str = str(getattr(status_val, "value"))
                else:
                    status_str = str(status_val)
                progress = data.get("progress") or {}
                stage = (
                    progress.get("stage")
                    if isinstance(progress, dict)
                    else getattr(progress, "stage", None)
                )
                percent = (
                    progress.get("percent")
                    if isinstance(progress, dict)
                    else getattr(progress, "percent", None)
                )
                jobs_repo.update_job_status(
                    job_id, status_str, progress_stage=stage, progress_percent=percent
                )
            elif "progress" in updates:
                progress = data.get("progress") or {}
                stage = (
                    progress.get("stage", "")
                    if isinstance(progress, dict)
                    else getattr(progress, "stage", "")
                )
                percent = (
                    progress.get("percent", 0)
                    if isinstance(progress, dict)
                    else getattr(progress, "percent", 0)
                )
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


def get_pallet_results(job_id: str) -> Optional[list[dict[str, Any]]]:
    """When SQL Server enabled, return pallet_results for job_id from DB; else None (caller should use report file)."""
    repos = _db_repos()
    if repos is None:
        return None
    _, pallet_repo, _ = repos
    try:
        return cast(Optional[list[dict[str, Any]]], pallet_repo.get_pallet_results(job_id))
    except Exception as e:
        logger.warning("DB get_pallet_results failed: %s", e)
        return None


def list_artifacts(base_path: Path, job_id: str) -> list[str]:
    """List artifact filenames under output/<job_id>/ (sanitized; no path traversal)."""
    job_id = validate_job_id(job_id)
    job_dir = _job_dir(base_path, job_id)
    if not job_dir.exists() or not job_dir.is_dir():
        return []
    out: list[str] = []
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
