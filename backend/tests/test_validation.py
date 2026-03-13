"""Tests for src.utils.validation (path-safe job_id and entity_uid)."""

import pytest

from src.utils.validation import validate_entity_uid, validate_job_id


def test_validate_job_id_rejects_path_traversal():
    for invalid in ("..", ".", "foo/bar", "a\\b", "../evil", "job_1/extra"):
        with pytest.raises(ValueError, match="must not contain|must contain only|non-empty"):
            validate_job_id(invalid)


def test_validate_job_id_rejects_empty_or_none():
    with pytest.raises(ValueError):
        validate_job_id("")
    with pytest.raises(ValueError):
        validate_job_id("   ")
    with pytest.raises(ValueError):
        validate_job_id(None)


def test_validate_job_id_accepts_valid():
    assert validate_job_id("job_abc123") == "job_abc123"
    assert validate_job_id("job_87ccc198c4e546ab") == "job_87ccc198c4e546ab"
    assert validate_job_id("JOB-1_2") == "JOB-1_2"


def test_validate_entity_uid_rejects_invalid():
    for invalid in ("..", "e/uid", "a\\b", ""):
        with pytest.raises(ValueError):
            validate_entity_uid(invalid)


def test_validate_entity_uid_accepts_valid():
    assert validate_entity_uid("job_abc_E1") == "job_abc_E1"
    assert validate_entity_uid("job_87ccc198c4e546ab_E7") == "job_87ccc198c4e546ab_E7"
