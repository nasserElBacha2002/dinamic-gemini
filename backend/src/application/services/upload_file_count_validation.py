"""Validate multipart upload file counts before reading bodies."""

from __future__ import annotations

from src.application.constants.upload_limits import MAX_FILES_PER_UPLOAD
from src.application.errors import TooManyFilesPerUploadError


def assert_upload_file_count_within_limit(file_count: int) -> None:
    if file_count > MAX_FILES_PER_UPLOAD:
        raise TooManyFilesPerUploadError(
            f"At most {MAX_FILES_PER_UPLOAD} file(s) allowed per upload request"
        )
