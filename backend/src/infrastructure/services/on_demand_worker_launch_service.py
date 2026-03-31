from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
import uuid

from src.config import load_settings

logger = logging.getLogger(__name__)


class OnDemandWorkerLaunchService:
    """Launch a single-job worker process using the current runtime image/interpreter."""

    def launch(self, job_id: str) -> str:
        execution_id = str(uuid.uuid4())
        settings = load_settings()
        raw_command = (os.getenv("WORKER_ON_DEMAND_COMMAND") or "").strip()
        if raw_command:
            command = shlex.split(raw_command)
        else:
            command = [sys.executable, "-m", "src.jobs.run_worker"]
        command = [*command, "--job-id", job_id, "--execution-id", execution_id]
        env = os.environ.copy()
        env["DINAMIC_JOB_ID"] = job_id
        env["DINAMIC_EXECUTION_ID"] = execution_id
        cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        stdout = subprocess.DEVNULL
        stderr = subprocess.DEVNULL
        if getattr(settings, "app_env", "").strip().lower() in {"local", "development", "dev"}:
            stdout = None
            stderr = None
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        logger.info(
            "on-demand worker launched: job_id=%s execution_id=%s pid=%s command=%s",
            job_id,
            execution_id,
            process.pid,
            command,
        )
        return execution_id
