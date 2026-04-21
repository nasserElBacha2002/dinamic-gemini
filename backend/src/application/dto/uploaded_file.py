"""Framework-agnostic upload payload shared by aisle asset flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO


@dataclass
class UploadedFile:
    """In-memory representation of a file to upload (framework-agnostic)."""

    original_filename: str
    file_obj: BinaryIO
    content_type: str
