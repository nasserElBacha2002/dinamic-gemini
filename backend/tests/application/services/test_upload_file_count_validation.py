"""Upload batch file-count validation."""

from __future__ import annotations

import pytest

from src.application.constants.upload_limits import MAX_FILES_PER_UPLOAD
from src.application.errors import TooManyFilesPerUploadError
from src.application.services.upload_file_count_validation import (
    assert_upload_file_count_within_limit,
)


def test_allows_up_to_max_files() -> None:
    assert_upload_file_count_within_limit(MAX_FILES_PER_UPLOAD)


def test_rejects_more_than_max_files() -> None:
    with pytest.raises(TooManyFilesPerUploadError):
        assert_upload_file_count_within_limit(MAX_FILES_PER_UPLOAD + 1)
