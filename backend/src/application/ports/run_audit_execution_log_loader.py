"""Port: best-effort execution log events for run auditability (Phase H1)."""

from __future__ import annotations

from typing import Any, Protocol

from src.domain.jobs.entities import Job


class RunAuditExecutionLogLoader(Protocol):
    def try_load_events_for_job(self, job: Job) -> list[dict[str, Any]] | None:
        """Return parsed JSONL events, or ``None`` when unavailable or on failure."""
