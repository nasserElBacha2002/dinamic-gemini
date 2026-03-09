"""
JobStoreRepositoryAdapter — implements JobRepository by delegating to job_store (Stage 2.3.B).

Migration adapter: job_store remains the implementation; this is a thin wrapper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from src.jobs.job_store import create_job, get_job, update_job
from src.jobs.models import JobRecord


class JobStoreRepositoryAdapter:
    """Implements JobRepository using create_job, get_job, update_job from job_store."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    def get(self, job_id: str) -> Optional[JobRecord]:
        return get_job(self._base_path, job_id)

    def update(self, job_id: str, **updates: Any) -> Optional[JobRecord]:
        return update_job(self._base_path, job_id, **updates)

    def create(self, record: JobRecord) -> JobRecord:
        """Persist the job, then return the persisted record (re-read from store)."""
        inp = record.input
        created = create_job(
            self._base_path,
            record.job_id,
            video_path=inp.video_path,
            mode=inp.mode,
            confidence_threshold=inp.confidence_threshold,
            metadata=inp.metadata,
            input_type=inp.input_type,
            input_manifest_path=inp.input_manifest_path,
            photos_dir=inp.photos_dir,
        )
        persisted = get_job(self._base_path, record.job_id)
        if persisted is not None:
            return persisted
        # Fallback: store may not support immediate re-read (e.g. DB eventual consistency). Return in-memory record built by create_job.
        return created
