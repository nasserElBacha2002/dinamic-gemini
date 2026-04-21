"""Framework-agnostic upload payload shared by aisle asset flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Optional


@dataclass
class UploadedFile:
    """In-memory representation of a file to upload (framework-agnostic)."""

    original_filename: str
    file_obj: BinaryIO
    content_type: str
    #: Optional last-modified instant in UTC (Sprint 3 capture time precedence: file mtime).
    last_modified_at: Optional[datetime] = None
