"""Upload limit config validation — ``LimitsAndSchemaSettings`` (bulk photo upload correction).

Constructed directly (not through full ``AppSettings``) so these are fast, isolated unit tests
that don't depend on DB/API-key env vars required elsewhere in the settings tree.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.env_settings.grouped_settings import LimitsAndSchemaSettings


def test_default_upload_limits_are_internally_consistent() -> None:
    """Whatever the effective env-derived defaults are, they must satisfy the same invariant
    enforced by the validator: request size >= file size, both positive. (Actual values may be
    overridden by a local ``.env``; the historical-safe fallback baked into the field defaults
    is 500MB/file and 1024MB/request when no env vars are set — see field descriptions.)"""
    settings = LimitsAndSchemaSettings()
    assert settings.max_upload_file_size_mb > 0
    assert settings.max_upload_request_size_mb > 0
    assert settings.max_upload_request_size_mb >= settings.max_upload_file_size_mb


def test_rejects_request_size_below_file_size() -> None:
    with pytest.raises(ValidationError, match="max_upload_request_size_mb must be >="):
        LimitsAndSchemaSettings(max_upload_file_size_mb=500, max_upload_request_size_mb=100)


def test_accepts_request_size_equal_to_file_size() -> None:
    settings = LimitsAndSchemaSettings(max_upload_file_size_mb=200, max_upload_request_size_mb=200)
    assert settings.max_upload_request_size_mb == settings.max_upload_file_size_mb == 200


def test_rejects_zero_or_negative_file_size_mb() -> None:
    with pytest.raises(ValidationError):
        LimitsAndSchemaSettings(max_upload_file_size_mb=0, max_upload_request_size_mb=1024)


def test_rejects_zero_or_negative_request_size_mb() -> None:
    with pytest.raises(ValidationError):
        LimitsAndSchemaSettings(max_upload_file_size_mb=500, max_upload_request_size_mb=0)


def test_max_files_per_upload_request_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        LimitsAndSchemaSettings(max_files_per_upload_request=0)
