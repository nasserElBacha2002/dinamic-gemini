from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import load_settings

WORKER_LAUNCH_LOG_NAME = "worker-launch.log"
BOOTSTRAP_FAILURE_CODE = "WORKER_BOOTSTRAP_FAILED"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def worker_launch_log_path(job_id: str) -> Path:
    settings = load_settings()
    return Path(settings.output_dir) / job_id / WORKER_LAUNCH_LOG_NAME


def append_worker_bootstrap_event(
    *,
    job_id: str,
    execution_id: str | None,
    event: str,
    details: dict[str, Any] | None = None,
) -> None:
    payload = {
        "ts": _utc_now().isoformat(),
        "event": event,
        "job_id": job_id,
        "execution_id": execution_id or "",
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "sys_executable": sys.executable,
        "details": details or {},
    }
    log_path = worker_launch_log_path(job_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=True, default=str))
        fh.write("\n")
        fh.flush()


def checkpoint_v3_job_bootstrap(
    *,
    job_id: str,
    execution_id: str | None,
    substep: str,
) -> None:
    try:
        from src.domain.jobs.entities import JobStatus
        from src.runtime.v3_deps import get_job_repo

        repo = get_job_repo()
        job = repo.get_by_id(job_id)
        if job is None or job.status not in (JobStatus.STARTING, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED):
            return
        now = _utc_now()
        updated = replace(
            job,
            current_stage="worker_bootstrap",
            current_substep=substep,
            current_step_started_at=now,
            updated_at=now,
            last_heartbeat_at=now,
            execution_id=job.execution_id or execution_id,
        )
        repo.save(updated)
    except Exception:
        append_worker_bootstrap_event(
            job_id=job_id,
            execution_id=execution_id,
            event="worker.bootstrap_checkpoint_failed",
            details={"substep": substep, "traceback": traceback.format_exc()},
        )


def fail_v3_job_bootstrap(
    *,
    job_id: str,
    execution_id: str | None,
    error_message: str,
    substep: str = "bootstrap_failed",
) -> None:
    append_worker_bootstrap_event(
        job_id=job_id,
        execution_id=execution_id,
        event="worker.bootstrap_failed",
        details={"substep": substep, "error": error_message, "traceback": traceback.format_exc()},
    )
    try:
        from src.domain.jobs.entities import JobStatus
        from src.runtime.v3_deps import get_job_repo

        repo = get_job_repo()
        job = repo.get_by_id(job_id)
        if job is None:
            return
        now = _utc_now()
        msg = (error_message or "worker bootstrap failed")[:2048]
        repo.save(
            replace(
                job,
                status=JobStatus.FAILED,
                current_stage="worker_bootstrap",
                current_substep=substep,
                current_step_started_at=now,
                updated_at=now,
                finished_at=now,
                last_heartbeat_at=now,
                execution_id=job.execution_id or execution_id,
                failure_code=BOOTSTRAP_FAILURE_CODE,
                failure_message=msg,
                error_message=msg,
            )
        )
    except Exception:
        append_worker_bootstrap_event(
            job_id=job_id,
            execution_id=execution_id,
            event="worker.bootstrap_fail_persist_failed",
            details={"substep": substep, "error": error_message, "traceback": traceback.format_exc()},
        )
