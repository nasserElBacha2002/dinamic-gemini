from __future__ import annotations

import logging
import os
from pathlib import Path
import json
import shlex
import subprocess
import sys
import time
import uuid

from src.config import load_settings

logger = logging.getLogger(__name__)

WORKER_LAUNCH_LOG_NAME = "worker-launch.log"
WORKER_STARTUP_GRACE_SEC = 0.2


class OnDemandWorkerLaunchService:
    """Launch a single-job worker process using the current runtime image/interpreter."""

    def launch(self, job_id: str) -> str:
        execution_id = str(uuid.uuid4())
        settings = load_settings()
        command = self._build_command()
        command = [*command, "--job-id", job_id, "--execution-id", execution_id]
        env = os.environ.copy()
        env["DINAMIC_JOB_ID"] = job_id
        env["DINAMIC_EXECUTION_ID"] = execution_id
        cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        output_dir = Path(settings.output_dir)
        launch_log_path = output_dir / job_id / WORKER_LAUNCH_LOG_NAME
        launch_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(launch_log_path, "a", encoding="utf-8") as launch_log:
            launch_log.write(
                f"launch_requested execution_id={execution_id} job_id={job_id} cwd={cwd} python={sys.executable} command={command}\n"
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
            if not isinstance(parsed, list) or not parsed or not all(isinstance(item, str) and item for item in parsed):
                raise RuntimeError(
                    "WORKER_ON_DEMAND_COMMAND JSON value must be a non-empty array of strings"
                )
            return parsed
        return shlex.split(raw_command)
