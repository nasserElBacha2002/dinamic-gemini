"""Shared per-request upload size/count checks (aisle assets + capture staging)."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.constants.upload_limits import (
    MAX_FILES_PER_UPLOAD_REQUEST,
    MAX_UPLOAD_FILE_SIZE_MB,
    MAX_UPLOAD_REQUEST_SIZE_MB,
)
from src.application.errors import TooManyFilesPerUploadError


class UploadRequestTooLargeError(Exception):
    """Total decoded bytes for one multipart request exceed the configured cap."""


class UploadFileTooLargeError(Exception):
    """A single file exceeds the per-file upload size cap."""


@dataclass(frozen=True)
class UploadRequestLimitPolicy:
    max_files_per_request: int = MAX_FILES_PER_UPLOAD_REQUEST
    max_file_size_bytes: int = MAX_UPLOAD_FILE_SIZE_MB * 1024 * 1024
    max_request_size_bytes: int = MAX_UPLOAD_REQUEST_SIZE_MB * 1024 * 1024

    @classmethod
    def from_settings(cls, settings: object) -> UploadRequestLimitPolicy:
        max_files = int(getattr(settings, "max_files_per_upload_request", MAX_FILES_PER_UPLOAD_REQUEST))
        file_mb = int(getattr(settings, "max_upload_file_size_mb", MAX_UPLOAD_FILE_SIZE_MB))
        req_mb = int(getattr(settings, "max_upload_request_size_mb", MAX_UPLOAD_REQUEST_SIZE_MB))
        return cls(
            max_files_per_request=max(1, max_files),
            max_file_size_bytes=max(1, file_mb) * 1024 * 1024,
            max_request_size_bytes=max(1, req_mb) * 1024 * 1024,
        )


def assert_file_count(file_count: int, policy: UploadRequestLimitPolicy) -> None:
    if file_count > policy.max_files_per_request:
        raise TooManyFilesPerUploadError(
            f"At most {policy.max_files_per_request} file(s) allowed per upload request"
        )


def assert_file_size(size_bytes: int, policy: UploadRequestLimitPolicy) -> None:
    if size_bytes > policy.max_file_size_bytes:
        raise UploadFileTooLargeError(
            f"File exceeds maximum upload size ({policy.max_file_size_bytes} bytes)"
        )


def assert_request_total_size(total_bytes: int, policy: UploadRequestLimitPolicy) -> None:
    if total_bytes > policy.max_request_size_bytes:
        raise UploadRequestTooLargeError(
            f"Upload request exceeds maximum total size ({policy.max_request_size_bytes} bytes)"
        )
