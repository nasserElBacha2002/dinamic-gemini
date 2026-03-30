import logging
import sys
from pathlib import Path
from typing import Any

from src.config import load_settings
from src.jobs.worker import worker_loop


logger = logging.getLogger(__name__)


def _configure_worker_logging() -> None:
    """Configure console logging for ECS/CloudWatch collection."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )


def _log_sql_worker_health() -> None:
    """Emit startup diagnostics for SQL-backed worker mode in ECS/dev."""
    settings = load_settings()
    sql_enabled = bool(getattr(settings, "sqlserver_enabled", False))
    sql_conn_configured = bool(getattr(settings, "sqlserver_effective_connection_string", ""))
    pyodbc_import_ok = False
    pyodbc_error = ""
    try:
        import pyodbc  # type: ignore

        _ = pyodbc
        pyodbc_import_ok = True
    except Exception as exc:  # pragma: no cover - defensive startup telemetry
        pyodbc_error = str(exc)

    repo_available = False
    repo_error = ""
    try:
        from src.jobs.job_store import _db_repos

        repos: Any = _db_repos()
        repo_available = repos is not None
    except Exception as exc:  # pragma: no cover - defensive startup telemetry
        repo_error = str(exc)

    logger.info(
        "Worker SQL health: sql_enabled=%s sql_conn_configured=%s pyodbc_import_ok=%s sql_repos_available=%s",
        sql_enabled,
        sql_conn_configured,
        pyodbc_import_ok,
        repo_available,
    )
    if pyodbc_error:
        logger.warning("Worker SQL health detail: pyodbc import failed: %s", pyodbc_error)
    if repo_error:
        logger.warning("Worker SQL health detail: repository init check failed: %s", repo_error)


def main() -> None:
    _configure_worker_logging()
    base_path = Path(load_settings().output_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    logger.info("Worker process starting (output_dir=%s)", str(base_path))
    logger.info("Worker code profile: v3_executor_accepts_running_status=true")
    _log_sql_worker_health()
    worker_loop(base_path)

if __name__ == "__main__":
    main()
