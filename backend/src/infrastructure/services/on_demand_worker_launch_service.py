from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path

from src.application.ports.services import WorkerLaunchService
from src.config import load_settings

logger = logging.getLogger(__name__)

WORKER_LAUNCH_LOG_NAME = "worker-launch.log"
WORKER_STARTUP_GRACE_SEC = 0.2


def _backend_project_root() -> Path:
    """``backend/`` directory (parent of the ``src`` package)."""
    # .../backend/src/infrastructure/services/this_file.py
    return Path(__file__).resolve().parents[3]


def _merge_worker_pythonpath(env: dict[str, str]) -> None:
    """Prepend ``backend/`` to PYTHONPATH so ``import src`` resolves to this repo (not stale installs)."""
    root = str(_backend_project_root())
    cur = (env.get("PYTHONPATH") or "").strip()
    if not cur:
        env["PYTHONPATH"] = root
        return
    parts = [p for p in cur.split(os.pathsep) if p]
    if root in parts:
        return
    env["PYTHONPATH"] = root + os.pathsep + cur


class OnDemandWorkerLaunchService(WorkerLaunchService):
    """Launch a single-job worker process using the current runtime image/interpreter."""

    def launch(self, job_id: str) -> str:
        return self._spawn(job_id)

    def launch_job_if_not_launched(self, job_id: str, *, idempotency_key: str) -> str:
        """Suppress duplicate spawns using job state + an exclusive launch claim file.

        The claim file is durable under ``output_dir/<job_id>/`` so concurrent schedulers
        and process restarts observe the same key (not a process-local lock alone).
        """
        existing = self._existing_live_execution_id(job_id)
        if existing:
            return existing

        settings = load_settings()
        output_dir = Path(settings.output_dir)
        claim_dir = output_dir / job_id
        claim_dir.mkdir(parents=True, exist_ok=True)
        safe_key = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in idempotency_key)[
            :120
        ]
        claim_path = claim_dir / f".launch-claim-{safe_key or 'default'}"
        try:
            fd = os.open(str(claim_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing = self._existing_live_execution_id(job_id)
            if existing:
                return existing
            # Claim held but job not live yet — wait briefly then re-check / fail closed.
            time.sleep(WORKER_STARTUP_GRACE_SEC)
            existing = self._existing_live_execution_id(job_id)
            if existing:
                return existing
            raise RuntimeError(
                f"Launch claim exists for job_id={job_id} key={idempotency_key!r} "
                "but no live execution_id; another launcher may still be spawning"
            )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as claim:
                claim.write(f"key={idempotency_key}\n")
                claim.flush()
            existing = self._existing_live_execution_id(job_id)
            if existing:
                return existing
            execution_id = self._spawn(job_id)
            claim_path.write_text(
                f"key={idempotency_key}\nexecution_id={execution_id}\n",
                encoding="utf-8",
            )
            return execution_id
        except Exception:
            try:
                claim_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _existing_live_execution_id(self, job_id: str) -> str | None:
        try:
            from src.domain.jobs.entities import JobStatus
            from src.runtime.v3_deps import get_job_repo

            job = get_job_repo().get_by_id(job_id)
        except Exception:
            logger.warning("launch idempotency job lookup failed job_id=%s", job_id, exc_info=True)
            return None
        if job is None:
            return None
        if job.status in (
            JobStatus.QUEUED,
            JobStatus.STARTING,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        ) and (job.execution_id or "").strip():
            return str(job.execution_id).strip()
        return None

    def _spawn(self, job_id: str) -> str:
        execution_id = str(uuid.uuid4())
        settings = load_settings()
        command = self._build_command()
        command = [*command, "--job-id", job_id, "--execution-id", execution_id]
        env = os.environ.copy()
        _merge_worker_pythonpath(env)
        env["DINAMIC_JOB_ID"] = job_id
        env["DINAMIC_EXECUTION_ID"] = execution_id
        correlation_id = self._resolve_correlation_id(job_id)
        if correlation_id:
            env["DINAMIC_CORRELATION_ID"] = correlation_id
        cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        output_dir = Path(settings.output_dir)
        launch_log_path = output_dir / job_id / WORKER_LAUNCH_LOG_NAME
        launch_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(launch_log_path, "a", encoding="utf-8") as launch_log:
            launch_log.write(
                f"launch_requested execution_id={execution_id} job_id={job_id} cwd={cwd} "
                f"python={sys.executable} PYTHONPATH={env.get('PYTHONPATH','')} command={command}\n"
            )
            launch_log.flush()
            try:
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=launch_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except Exception as exc:
                logger.exception(
                    "on-demand worker launch failed before spawn: job_id=%s execution_id=%s log_path=%s",
                    job_id,
                    execution_id,
                    str(launch_log_path),
                )
                raise RuntimeError(
                    f"Worker spawn failed; see launch log at {launch_log_path}: {exc}"
                ) from exc

            time.sleep(WORKER_STARTUP_GRACE_SEC)
            exit_code = process.poll()
            if exit_code is not None:
                launch_log.write(
                    f"process_exited_during_startup execution_id={execution_id} job_id={job_id} pid={process.pid} exit_code={exit_code}\n"
                )
                launch_log.flush()
                logger.error(
                    "on-demand worker exited during startup: job_id=%s execution_id=%s pid=%s exit_code=%s log_path=%s",
                    job_id,
                    execution_id,
                    process.pid,
                    exit_code,
                    str(launch_log_path),
                )
                raise RuntimeError(
                    f"Worker exited during startup with code {exit_code}; see launch log at {launch_log_path}"
                )
            logger.info(
                "on-demand worker launched: job_id=%s execution_id=%s pid=%s command=%s log_path=%s",
                job_id,
                execution_id,
                process.pid,
                command,
                str(launch_log_path),
            )
            launch_log.write(
                f"process_spawn_observed execution_id={execution_id} job_id={job_id} pid={process.pid} grace_sec={WORKER_STARTUP_GRACE_SEC}\n"
            )
            launch_log.flush()
        return execution_id

    def _build_command(self) -> list[str]:
        raw_command = (os.getenv("WORKER_ON_DEMAND_COMMAND") or "").strip()
        if not raw_command:
            return [sys.executable, "-m", "src.jobs.run_worker"]
        if raw_command.startswith("["):
            try:
                parsed = json.loads(raw_command)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "WORKER_ON_DEMAND_COMMAND must be valid JSON array or a shell-style command string"
                ) from exc
            if (
                not isinstance(parsed, list)
                or not parsed
                or not all(isinstance(item, str) and item for item in parsed)
            ):
                raise RuntimeError(
                    "WORKER_ON_DEMAND_COMMAND JSON value must be a non-empty array of strings"
                )
            return parsed
        return shlex.split(raw_command)

    def _resolve_correlation_id(self, job_id: str) -> str | None:
        try:
            from src.application.use_cases.recovery.recover_stale_job import (
                CORRELATION_PAYLOAD_KEY,
                job_correlation_id,
            )
            from src.runtime.v3_deps import get_job_repo

            job = get_job_repo().get_by_id(job_id)
            if job is None:
                return None
            # Prefer explicit payload; helper generates only if missing — for env, only set if known.
            if isinstance(job.payload_json, dict):
                raw = job.payload_json.get(CORRELATION_PAYLOAD_KEY)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
            return job_correlation_id(job)
        except Exception:
            logger.warning("worker launch correlation resolve failed job_id=%s", job_id, exc_info=True)
            return None
