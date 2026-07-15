"""Validate multipart upload file counts before reading bodies."""

from __future__ import annotations

from src.application.constants.upload_limits import MAX_FILES_PER_UPLOAD_REQUEST
from src.application.errors import TooManyFilesPerUploadError


def assert_upload_file_count_within_limit(
    file_count: int,
    *,
    max_files: int | None = None,
) -> None:
    limit = MAX_FILES_PER_UPLOAD_REQUEST if max_files is None else max(1, int(max_files))
    if file_count > limit:
        raise TooManyFilesPerUploadError(f"At most {limit} file(s) allowed per upload request")
