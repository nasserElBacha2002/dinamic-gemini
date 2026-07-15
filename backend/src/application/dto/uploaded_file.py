"""Framework-agnostic upload payload shared by aisle asset flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO


@dataclass
class UploadedFile:
    """File-like upload payload (framework-agnostic).

    Prefer a seekable temp/spool file over a full in-memory ``BytesIO`` copy.
    """

    original_filename: str
    file_obj: BinaryIO
    content_type: str
    #: Optional last-modified instant in UTC (Sprint 3 capture time precedence: file mtime).
    last_modified_at: datetime | None = None
    #: Client-generated id for correlation / idempotency within an upload batch.
    client_file_id: str | None = None
    #: Client-generated id shared by all files in one user selection (multi-request).
    upload_batch_id: str | None = None
    #: Known size in bytes when measured during ingest (optional).
    size_bytes: int | None = None
