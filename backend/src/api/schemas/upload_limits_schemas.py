"""Wire schema for GET /api/v3/config/upload-limits."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UploadLimitsResponse(BaseModel):
    """Server-enforced upload caps plus advisory client concurrency/retry hints."""

    max_files_per_request: int = Field(
        description="Max files accepted in one multipart HTTP request (auto-batch selections larger)."
    )
    max_file_size_bytes: int = Field(description="Max size of a single uploaded file in bytes.")
    max_request_size_bytes: int = Field(
        description="Max total decoded bytes for one multipart request."
    )
    upload_batch_concurrency: int = Field(
        description="Advisory: max concurrent batch HTTP requests (client-side; not enforced)."
    )
    retry_attempts: int = Field(
        description=(
            "Advisory: number of **additional** retries after the initial attempt "
            "(0 = one request total; 3 = up to four requests). Not enforced server-side."
        )
    )
    retry_base_delay_ms: int = Field(
        description="Advisory: base backoff delay in ms between client retries (not enforced)."
    )
