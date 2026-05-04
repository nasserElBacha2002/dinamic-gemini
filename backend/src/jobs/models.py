"""Stage 7 — Job record model for API inventory processing."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobInput(BaseModel):
    """Input payload for a job. Stage 2.2.A: video_path empty when input_type=photos."""

    video_path: str = ""
    mode: str = "hybrid"
    confidence_threshold: float = 0.70
    metadata: Optional[dict[str, Any]] = None
    input_type: str = "video"
    input_manifest_path: Optional[str] = None
    photos_dir: Optional[str] = None


class JobProgress(BaseModel):
    """Progress info during run."""

    stage: str = ""
    percent: int = 0


class JobOutput(BaseModel):
    """Paths written after success."""

    report_json_path: Optional[str] = None
    report_csv_path: Optional[str] = None
    artifacts_dir: Optional[str] = None


class JobRecord(BaseModel):
    """Persisted job record (output/<job_id>/job.json)."""

    job_id: str
    input: JobInput
    status: JobStatus = JobStatus.QUEUED
    progress: JobProgress = Field(default_factory=JobProgress)
    output: Optional[JobOutput] = None
    error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
