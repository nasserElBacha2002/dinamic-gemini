"""Infrastructure adapter for :class:`~src.application.ports.run_audit_execution_log_loader.RunAuditExecutionLogLoader`."""

from __future__ import annotations

from typing import Any

from src.application.ports.run_audit_execution_log_loader import RunAuditExecutionLogLoader
from src.domain.jobs.entities import Job
from src.infrastructure.artifacts.stored_artifact_reader import (
    try_read_execution_log_events_for_job,
)


class DefaultRunAuditExecutionLogLoader(RunAuditExecutionLogLoader):
    """Wires artifact store to best-effort execution log reads."""

    def __init__(self, artifact_store: Any) -> None:
        self._artifact_store = artifact_store

    def try_load_events_for_job(self, job: Job) -> list[dict[str, Any]] | None:
        return try_read_execution_log_events_for_job(job, artifact_store=self._artifact_store)
