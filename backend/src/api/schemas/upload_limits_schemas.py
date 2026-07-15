"""Wire schema for GET /api/v3/config/upload-limits."""

from __future__ import annotations

from pydantic import BaseModel


class UploadLimitsResponse(BaseModel):
    """Server-enforced upload caps plus advisory client concurrency/retry hints."""

    max_files_per_request: int
    max_file_size_bytes: int
    max_request_size_bytes: int
    upload_batch_concurrency: int
    retry_attempts: int
    retry_base_delay_ms: int
