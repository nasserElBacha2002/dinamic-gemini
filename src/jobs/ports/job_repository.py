"""
JobRepository port — load, save, update job records (Stage 2.3.B).

Implementations wrap current persistence (FS + optional DB).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from src.jobs.models import JobRecord


class JobRepository(Protocol):
    """Port for job persistence. Adapters delegate to job_store or DB."""

    def get(self, job_id: str) -> Optional[JobRecord]:
        """Load job by id; return None if not found."""
        ...

    def update(self, job_id: str, **updates: Any) -> Optional[JobRecord]:
        """Update job fields (status, progress, output, error, etc.); return updated record or None."""
        ...

    def create(self, record: JobRecord) -> JobRecord:
        """Persist a new job record; return the persisted record (prefer re-read from store)."""
        ...
